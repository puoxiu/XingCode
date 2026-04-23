from __future__ import annotations

import json
from pathlib import Path

import pytest

from XingCode.storage import session as session_module


@pytest.fixture
def temp_session_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把 session 读写重定向到临时目录，避免污染真实用户目录。"""

    sessions_dir = tmp_path / "sessions"
    monkeypatch.setattr(session_module, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(session_module, "SESSIONS_INDEX_PATH", tmp_path / "sessions_index.json")
    return sessions_dir


def test_create_new_session_returns_empty_data(temp_session_storage: Path) -> None:
    """新建会话时，应生成空状态和 12 位短 session id。"""

    _ = temp_session_storage
    session = session_module.create_new_session(workspace="/tmp/workspace")

    assert len(session.session_id) == 12
    assert session.workspace == "/tmp/workspace"
    assert session.messages == []
    assert session.transcript_entries == []
    assert session.history == []


def test_save_and_load_session_roundtrip(temp_session_storage: Path) -> None:
    """完整保存后，应能无损恢复当前阶段的会话主体字段。"""

    _ = temp_session_storage
    session = session_module.create_new_session(workspace="/tmp/project")
    session.messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    session.transcript_entries = [{"id": 1, "kind": "assistant", "body": "hi"}]
    session.history = ["/help", "hello"]
    session.permissions_summary = ["cwd: /tmp/project"]

    session_module.save_session(session)
    loaded = session_module.load_session(session.session_id)

    assert loaded is not None
    assert loaded.session_id == session.session_id
    assert loaded.workspace == "/tmp/project"
    assert loaded.messages == session.messages
    assert loaded.transcript_entries == session.transcript_entries
    assert loaded.history == session.history
    assert loaded.permissions_summary == session.permissions_summary


def test_save_session_writes_delta_for_appended_messages(temp_session_storage: Path) -> None:
    """已有完整快照后，新增消息和 transcript 应优先走 delta 保存。"""

    _ = temp_session_storage
    session = session_module.create_new_session(workspace="/tmp/project")
    session.messages = [{"role": "user", "content": "first"}]
    session.transcript_entries = [{"id": 1, "kind": "user", "body": "first"}]

    session_module.save_session(session, force_full=True)

    session.messages.append({"role": "assistant", "content": "second"})
    session.transcript_entries.append({"id": 2, "kind": "assistant", "body": "second"})
    session_module.save_session(session, force_full=False)

    delta_dir = temp_session_storage / session_module.DELTA_DIR_NAME / session.session_id
    delta_files = sorted(delta_dir.glob("delta_*.json"))
    assert len(delta_files) == 1

    snapshot = json.loads((temp_session_storage / f"{session.session_id}.json").read_text(encoding="utf-8"))
    assert len(snapshot["messages"]) == 1

    loaded = session_module.load_session(session.session_id)
    assert loaded is not None
    assert [message["content"] for message in loaded.messages] == ["first", "second"]
    assert [entry["body"] for entry in loaded.transcript_entries] == ["first", "second"]


def test_save_session_consolidates_delta_into_full_snapshot(
    temp_session_storage: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """达到完整保存阈值后，应把 delta 合并回主快照并清理 delta 文件。"""

    _ = temp_session_storage
    monkeypatch.setattr(session_module, "FULL_SAVE_INTERVAL", 1)
    session = session_module.create_new_session(workspace="/tmp/project")
    session.messages = [{"role": "user", "content": "one"}]

    session_module.save_session(session, force_full=True)

    session.messages.append({"role": "assistant", "content": "two"})
    session_module.save_session(session, force_full=False)
    delta_dir = temp_session_storage / session_module.DELTA_DIR_NAME / session.session_id
    assert delta_dir.exists()

    session.messages.append({"role": "user", "content": "three"})
    session_module.save_session(session, force_full=False)

    assert not delta_dir.exists()
    snapshot = json.loads((temp_session_storage / f"{session.session_id}.json").read_text(encoding="utf-8"))
    assert [message["content"] for message in snapshot["messages"]] == ["one", "two", "three"]


def test_save_session_falls_back_to_full_snapshot_when_only_history_changes(
    temp_session_storage: Path,
) -> None:
    """仅有 history 等非追加字段变化时，不能走 delta，必须完整保存。"""

    _ = temp_session_storage
    session = session_module.create_new_session(workspace="/tmp/project")
    session.messages = [{"role": "user", "content": "hello"}]
    session_module.save_session(session, force_full=True)

    session.history = ["/help", "hello"]
    session_module.save_session(session, force_full=False)

    delta_dir = temp_session_storage / session_module.DELTA_DIR_NAME / session.session_id
    assert not delta_dir.exists()

    loaded = session_module.load_session(session.session_id)
    assert loaded is not None
    assert loaded.history == ["/help", "hello"]


def test_save_session_updates_metadata_preview_fields(temp_session_storage: Path) -> None:
    """保存时应自动提取第一条用户消息和最后一条可见消息。"""

    _ = temp_session_storage
    session = session_module.create_new_session(workspace="/tmp/project")
    session.messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "first user message"},
        {"role": "assistant", "content": "assistant reply"},
    ]

    session_module.save_session(session)
    sessions = session_module.list_sessions()

    assert len(sessions) == 1
    assert sessions[0].first_message == "first user message"
    assert sessions[0].last_message == "assistant reply"
    assert sessions[0].message_count == 3


def test_load_session_returns_none_for_missing_file(temp_session_storage: Path) -> None:
    """读取不存在的会话时，应返回 None。"""

    _ = temp_session_storage
    assert session_module.load_session("missing-session") is None


def test_list_sessions_returns_newest_first(temp_session_storage: Path) -> None:
    """会话列表应按 updated_at 倒序排列。"""

    _ = temp_session_storage
    older = session_module.create_new_session(workspace="/tmp/older")
    session_module.save_session(older)

    newer = session_module.create_new_session(workspace="/tmp/newer")
    session_module.save_session(newer)

    sessions = session_module.list_sessions()

    assert [metadata.session_id for metadata in sessions] == [newer.session_id, older.session_id]


def test_get_latest_session_can_filter_by_workspace(temp_session_storage: Path) -> None:
    """latest 查询应支持按 workspace 过滤。"""

    _ = temp_session_storage
    first = session_module.create_new_session(workspace="/tmp/workspace-a")
    session_module.save_session(first)

    second = session_module.create_new_session(workspace="/tmp/workspace-b")
    session_module.save_session(second)

    latest = session_module.get_latest_session(workspace="/tmp/workspace-b")

    assert latest is not None
    assert latest.session_id == second.session_id


def test_autosave_manager_saves_after_interval(temp_session_storage: Path) -> None:
    """AutosaveManager 应在 dirty 且达到节流间隔后触发保存。"""

    _ = temp_session_storage
    session = session_module.create_new_session(workspace="/tmp/project")
    session.messages.append({"role": "user", "content": "hello autosave"})
    manager = session_module.AutosaveManager(session, interval=1)

    manager.mark_dirty()
    assert manager.should_save() is False

    manager._last_save_time -= 2
    assert manager.should_save() is True
    assert manager.save_if_needed() is True

    loaded = session_module.load_session(session.session_id)
    assert loaded is not None
    assert loaded.messages[-1]["content"] == "hello autosave"


def test_format_session_list_and_resume_are_human_readable(temp_session_storage: Path) -> None:
    """列表和恢复提示应包含关键会话信息。"""

    _ = temp_session_storage
    session = session_module.create_new_session(workspace="/tmp/project")
    session.messages = [{"role": "user", "content": "hello"}]
    session.update_metadata()

    list_text = session_module.format_session_list([session.metadata])
    resume_text = session_module.format_session_resume(session)

    assert "Saved sessions:" in list_text
    assert session.session_id[:8] in list_text
    assert "Resuming session" in resume_text
    assert "/tmp/project" in resume_text


def test_load_session_returns_none_when_json_is_invalid(
    temp_session_storage: Path,
) -> None:
    """损坏的 session 文件不应导致加载崩溃。"""

    broken = temp_session_storage / "broken.json"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text("{not-json}\n", encoding="utf-8")

    assert session_module.load_session("broken") is None
