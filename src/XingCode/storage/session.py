from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from XingCode.storage.config import XINGCODE_DIR

# ========================= 配置常量 =========================
# 会话目录：存完整快照；delta 目录则放在 sessions/deltas/<session_id>/ 下。
SESSIONS_DIR = XINGCODE_DIR / "sessions"
SESSIONS_INDEX_PATH = XINGCODE_DIR / "sessions_index.json"
AUTOSAVE_INTERVAL_SECONDS = 30
DELTA_DIR_NAME = "deltas"
FULL_SAVE_INTERVAL = 10
MAX_DELTA_FILES = 50


@dataclass(slots=True)
class SessionMetadata:
    """会话列表页使用的轻量级元数据。"""

    session_id: str
    created_at: float
    updated_at: float
    first_message: str = ""
    last_message: str = ""
    message_count: int = 0
    workspace: str = ""


@dataclass(slots=True)
class SessionData:
    """可以完整保存和恢复的会话数据。"""

    session_id: str
    created_at: float
    updated_at: float
    workspace: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    transcript_entries: list[dict[str, Any]] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    permissions_summary: list[str] = field(default_factory=list)
    skills: list[dict[str, Any]] = field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    metadata: SessionMetadata | None = None

    # 增量保存跟踪字段：
    # 1. 最近一次已落盘的 messages/transcript 数量
    # 2. 已存在的 delta 文件数量
    # 3. 最近一次完整快照的轻量内容 hash
    _last_saved_msg_count: int = field(default=0, repr=False)
    _last_saved_transcript_count: int = field(default=0, repr=False)
    _delta_save_count: int = field(default=0, repr=False)
    _last_full_save_hash: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        """在缺省 metadata 时自动补齐，并刷新元数据字段。"""

        if self.metadata is None:
            self.metadata = SessionMetadata(
                session_id=self.session_id,
                created_at=self.created_at,
                updated_at=self.updated_at,
                workspace=self.workspace,
            )
        self.update_metadata(touch=False)

    def update_metadata(self, *, touch: bool = True) -> None:
        """根据当前会话状态刷新 metadata。"""

        if touch:
            self.updated_at = time.time()

        if self.metadata is None:
            self.metadata = SessionMetadata(
                session_id=self.session_id,
                created_at=self.created_at,
                updated_at=self.updated_at,
                workspace=self.workspace,
            )

        self.metadata.updated_at = self.updated_at
        self.metadata.workspace = self.workspace
        self.metadata.message_count = len(self.messages)
        self.metadata.first_message = _extract_first_user_message(self.messages)
        self.metadata.last_message = _extract_last_visible_message(self.messages)

    @property
    def has_delta(self) -> bool:
        """判断当前是否存在仅靠 delta 就能表示的新增消息/新增 transcript。"""

        return (
            len(self.messages) != self._last_saved_msg_count
            or len(self.transcript_entries) != self._last_saved_transcript_count
        )

    def compute_content_hash(self) -> str:
        """为最近消息生成一个轻量 hash，用于记录完整快照基线。"""

        digest = hashlib.md5(usedforsecurity=False)
        for message in self.messages[-20:]:
            digest.update(str(message.get("role", "")).encode("utf-8", errors="ignore"))
            digest.update(str(message.get("content", ""))[:500].encode("utf-8", errors="ignore"))
        for entry in self.transcript_entries[-20:]:
            digest.update(str(entry.get("kind", "")).encode("utf-8", errors="ignore"))
            digest.update(str(entry.get("body", ""))[:500].encode("utf-8", errors="ignore"))
        return digest.hexdigest()


def _extract_first_user_message(messages: list[dict[str, Any]]) -> str:
    """提取第一条用户消息，供会话列表快速预览。"""

    for message in messages:
        if message.get("role") == "user":
            return str(message.get("content", ""))[:100]
    return ""


def _extract_last_visible_message(messages: list[dict[str, Any]]) -> str:
    """提取最后一条用户或助手消息，供会话列表快速预览。"""

    for message in reversed(messages):
        if message.get("role") in {"user", "assistant"}:
            return str(message.get("content", ""))[:100]
    return ""


def _session_file(session_id: str) -> Path:
    """返回单个会话完整快照文件路径。"""

    return SESSIONS_DIR / f"{session_id}.json"


def _session_delta_dir(session_id: str) -> Path:
    """返回单个会话的 delta 目录路径。"""

    return SESSIONS_DIR / DELTA_DIR_NAME / session_id


def _serialize_metadata(metadata: SessionMetadata) -> dict[str, Any]:
    """把 SessionMetadata 转成可写入 JSON 的字典。"""

    return {
        "session_id": metadata.session_id,
        "created_at": metadata.created_at,
        "updated_at": metadata.updated_at,
        "first_message": metadata.first_message,
        "last_message": metadata.last_message,
        "message_count": metadata.message_count,
        "workspace": metadata.workspace,
    }


def _serialize_session(session: SessionData) -> dict[str, Any]:
    """把 SessionData 转成完整快照 JSON 结构。"""

    session.update_metadata()
    metadata = session.metadata or SessionMetadata(
        session_id=session.session_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        workspace=session.workspace,
    )
    return {
        "session_id": session.session_id,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "workspace": session.workspace,
        "messages": session.messages,
        "transcript_entries": session.transcript_entries,
        "history": session.history,
        "permissions_summary": session.permissions_summary,
        "skills": session.skills,
        "mcp_servers": session.mcp_servers,
        "metadata": _serialize_metadata(metadata),
    }


def _coerce_metadata(payload: dict[str, Any], fallback: dict[str, Any]) -> SessionMetadata:
    """从磁盘 JSON 恢复 SessionMetadata；缺字段时回退到主体数据。"""

    return SessionMetadata(
        session_id=str(payload.get("session_id", fallback["session_id"])),
        created_at=float(payload.get("created_at", fallback["created_at"])),
        updated_at=float(payload.get("updated_at", fallback["updated_at"])),
        first_message=str(payload.get("first_message", "")),
        last_message=str(payload.get("last_message", "")),
        message_count=int(payload.get("message_count", fallback["message_count"])),
        workspace=str(payload.get("workspace", fallback["workspace"])),
    )


def _load_session_index() -> dict[str, SessionMetadata]:
    """加载会话索引；索引文件损坏时返回空字典。"""

    if not SESSIONS_INDEX_PATH.exists():
        return {}

    try:
        parsed = json.loads(SESSIONS_INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(parsed, dict):
        return {}

    index: dict[str, SessionMetadata] = {}
    for session_id, raw_meta in parsed.items():
        if not isinstance(session_id, str) or not isinstance(raw_meta, dict):
            continue
        try:
            index[session_id] = SessionMetadata(
                session_id=str(raw_meta.get("session_id", session_id)),
                created_at=float(raw_meta.get("created_at", 0.0)),
                updated_at=float(raw_meta.get("updated_at", 0.0)),
                first_message=str(raw_meta.get("first_message", "")),
                last_message=str(raw_meta.get("last_message", "")),
                message_count=int(raw_meta.get("message_count", 0)),
                workspace=str(raw_meta.get("workspace", "")),
            )
        except (TypeError, ValueError):
            continue
    return index


def _save_session_index(index: dict[str, SessionMetadata]) -> None:
    """保存会话索引，供 list/latest 快速读取。"""

    XINGCODE_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {session_id: _serialize_metadata(metadata) for session_id, metadata in index.items()}
    SESSIONS_INDEX_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _apply_tracking_after_full_save(session: SessionData) -> None:
    """完整保存后刷新基线计数和快照 hash。"""

    session._last_saved_msg_count = len(session.messages)
    session._last_saved_transcript_count = len(session.transcript_entries)
    session._last_full_save_hash = session.compute_content_hash()


def _write_full_snapshot(session: SessionData) -> None:
    """把整个会话写成完整快照文件。"""

    _session_file(session.session_id).write_text(
        json.dumps(_serialize_session(session), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _save_delta(session: SessionData) -> bool:
    """只保存自上次落盘以来新增的消息和 transcript。"""

    new_messages = session.messages[session._last_saved_msg_count :]
    new_transcripts = session.transcript_entries[session._last_saved_transcript_count :]
    if not new_messages and not new_transcripts:
        return False

    delta_dir = _session_delta_dir(session.session_id)
    delta_dir.mkdir(parents=True, exist_ok=True)

    # delta 只记录追加部分，因此 offset 非常关键；加载时要靠它避免重复应用。
    delta_payload: dict[str, Any] = {
        "ts": time.time(),
        "msg_offset": session._last_saved_msg_count,
        "transcript_offset": session._last_saved_transcript_count,
    }
    if new_messages:
        delta_payload["messages"] = new_messages
    if new_transcripts:
        delta_payload["transcripts"] = new_transcripts

    delta_path = delta_dir / f"delta_{session._delta_save_count:04d}.json"
    delta_path.write_text(
        json.dumps(delta_payload, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    session._last_saved_msg_count = len(session.messages)
    session._last_saved_transcript_count = len(session.transcript_entries)
    session._delta_save_count += 1
    return True


def _consolidate_deltas(session: SessionData) -> None:
    """清理已经被完整快照吸收的 delta 文件。"""

    delta_dir = _session_delta_dir(session.session_id)
    if not delta_dir.exists():
        session._delta_save_count = 0
        return

    for delta_file in sorted(delta_dir.glob("delta_*.json")):
        try:
            delta_file.unlink()
        except OSError:
            pass

    try:
        delta_dir.rmdir()
    except OSError:
        pass

    parent = delta_dir.parent
    if parent.name == DELTA_DIR_NAME:
        try:
            if not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            pass

    session._delta_save_count = 0


def save_session(session: SessionData, force_full: bool = False) -> None:
    """保存会话到磁盘；默认优先使用 delta，必要时做完整快照。"""

    session.update_metadata()
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    snapshot_exists = _session_file(session.session_id).exists()

    # 只有“新增 messages/transcript”时，delta 才能完整表达状态；
    # 其他字段变化（history、permissions 等）必须走完整快照。
    can_use_delta = snapshot_exists and session.has_delta
    should_full_save = (
        force_full
        or not snapshot_exists
        or not can_use_delta
        or session._delta_save_count >= FULL_SAVE_INTERVAL
        or session._delta_save_count >= MAX_DELTA_FILES
    )

    if should_full_save:
        _write_full_snapshot(session)
        _apply_tracking_after_full_save(session)
        _consolidate_deltas(session)
    else:
        _save_delta(session)

    # 不管是 full save 还是 delta save，都要刷新索引，保证 list/latest 及时可见。
    index = _load_session_index()
    if session.metadata is not None:
        index[session.session_id] = session.metadata
    _save_session_index(index)


def _apply_delta_messages(existing: list[dict[str, Any]], delta_messages: list[dict[str, Any]], offset: int) -> None:
    """把 delta 中的新增消息按 offset 合并到现有列表。"""

    if offset >= len(existing):
        existing.extend(delta_messages)
        return

    overlap = len(existing) - offset
    if overlap < len(delta_messages):
        existing.extend(delta_messages[overlap:])


def _apply_delta_transcripts(
    existing: list[dict[str, Any]],
    delta_transcripts: list[dict[str, Any]],
    offset: int,
) -> None:
    """把 delta 中的新增 transcript 按 offset 合并到现有列表。"""

    if offset >= len(existing):
        existing.extend(delta_transcripts)
        return

    overlap = len(existing) - offset
    if overlap < len(delta_transcripts):
        existing.extend(delta_transcripts[overlap:])


def load_session(session_id: str) -> SessionData | None:
    """从完整快照加载会话，并按顺序应用所有待合并 delta。"""

    session_path = _session_file(session_id)
    if not session_path.exists():
        return None

    try:
        parsed = json.loads(session_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(parsed, dict):
        return None

    try:
        messages = parsed.get("messages", [])
        transcript_entries = parsed.get("transcript_entries", [])
        history = parsed.get("history", [])
        permissions_summary = parsed.get("permissions_summary", [])
        skills = parsed.get("skills", [])
        mcp_servers = parsed.get("mcp_servers", [])

        fallback = {
            "session_id": str(parsed["session_id"]),
            "created_at": float(parsed["created_at"]),
            "updated_at": float(parsed["updated_at"]),
            "workspace": str(parsed["workspace"]),
            "message_count": len(messages) if isinstance(messages, list) else 0,
        }
        metadata = _coerce_metadata(parsed.get("metadata", {}), fallback)

        session = SessionData(
            session_id=fallback["session_id"],
            created_at=fallback["created_at"],
            updated_at=fallback["updated_at"],
            workspace=fallback["workspace"],
            messages=messages if isinstance(messages, list) else [],
            transcript_entries=transcript_entries if isinstance(transcript_entries, list) else [],
            history=history if isinstance(history, list) else [],
            permissions_summary=permissions_summary if isinstance(permissions_summary, list) else [],
            skills=skills if isinstance(skills, list) else [],
            mcp_servers=mcp_servers if isinstance(mcp_servers, list) else [],
            metadata=metadata,
        )
    except (KeyError, TypeError, ValueError):
        return None

    delta_dir = _session_delta_dir(session_id)
    applied_delta_count = 0
    if delta_dir.exists():
        for delta_path in sorted(delta_dir.glob("delta_*.json")):
            try:
                delta = json.loads(delta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            if not isinstance(delta, dict):
                continue

            raw_messages = delta.get("messages", [])
            raw_transcripts = delta.get("transcripts", [])
            msg_offset = int(delta.get("msg_offset", len(session.messages)))
            transcript_offset = int(delta.get("transcript_offset", len(session.transcript_entries)))

            if isinstance(raw_messages, list):
                _apply_delta_messages(session.messages, raw_messages, msg_offset)
            if isinstance(raw_transcripts, list):
                _apply_delta_transcripts(session.transcript_entries, raw_transcripts, transcript_offset)
            applied_delta_count += 1

    session._last_saved_msg_count = len(session.messages)
    session._last_saved_transcript_count = len(session.transcript_entries)
    session._delta_save_count = applied_delta_count
    session._last_full_save_hash = session.compute_content_hash()
    session.update_metadata(touch=False)
    return session


def list_sessions() -> list[SessionMetadata]:
    """列出全部已保存会话，按最近更新时间倒序返回。"""

    sessions = list(_load_session_index().values())
    sessions.sort(key=lambda metadata: metadata.updated_at, reverse=True)
    return sessions


def create_new_session(workspace: str) -> SessionData:
    """创建一个新的空会话。"""

    now = time.time()
    return SessionData(
        session_id=uuid.uuid4().hex[:12],
        created_at=now,
        updated_at=now,
        workspace=workspace,
    )


def get_latest_session(workspace: str | None = None) -> SessionData | None:
    """获取最近的会话；可按 workspace 过滤。"""

    for metadata in list_sessions():
        if workspace is None or metadata.workspace == workspace:
            return load_session(metadata.session_id)
    return None


class AutosaveManager:
    """管理自动保存节流逻辑的轻量控制器。"""

    def __init__(self, session: SessionData, interval: int = AUTOSAVE_INTERVAL_SECONDS) -> None:
        """创建一个 autosave 管理器；interval 表示两次自动保存的最小间隔。"""

        self.session = session
        self.interval = interval
        self._last_save_time = time.time()
        self._dirty = False

    def mark_dirty(self) -> None:
        """标记当前会话已修改，后续允许自动保存。"""

        self._dirty = True

    def should_save(self) -> bool:
        """判断 autosave 是否应该触发。"""

        if not self._dirty:
            return False
        return (time.time() - self._last_save_time) >= self.interval

    def save_if_needed(self) -> bool:
        """在达到节流条件时执行自动保存；成功保存返回 True。"""

        if not self.should_save():
            return False

        save_session(self.session, force_full=False)
        self._last_save_time = time.time()
        self._dirty = False
        return True

    def force_save(self) -> None:
        """无视节流条件立即做一次完整快照保存。"""

        save_session(self.session, force_full=True)
        self._last_save_time = time.time()
        self._dirty = False


def format_session_list(sessions: list[SessionMetadata]) -> str:
    """把会话列表格式化成可直接打印的文本。"""

    if not sessions:
        return "No saved sessions found."

    lines = ["Saved sessions:", ""]
    for index, metadata in enumerate(sessions, start=1):
        updated = time.strftime("%Y-%m-%d %H:%M", time.localtime(metadata.updated_at))
        first_message = metadata.first_message or "(empty)"
        lines.append(
            f"{index}. [{metadata.session_id[:8]}] {updated} - {metadata.workspace or 'unknown'}"
        )
        lines.append(f"   Messages: {metadata.message_count} | First: {first_message}")
        lines.append("")
    lines.append(f"Total: {len(sessions)} session(s)")
    return "\n".join(lines)


def format_session_resume(session: SessionData) -> str:
    """把恢复提示格式化为简洁文本。"""

    return "\n".join(
        [
            f"Resuming session {session.session_id[:8]}",
            f"  Created: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(session.created_at))}",
            f"  Updated: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(session.updated_at))}",
            f"  Messages: {len(session.messages)}",
            f"  Workspace: {session.workspace}",
        ]
    )
