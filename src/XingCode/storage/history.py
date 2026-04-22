from __future__ import annotations

import json
from pathlib import Path

from XingCode.storage.config import XINGCODE_DIR

# 最近输入历史文件：沿用全局配置目录，和参考项目的 history.json 结构保持一致。
XINGCODE_HISTORY_PATH = XINGCODE_DIR / "history.json"
MAX_HISTORY_ENTRIES = 200


def load_history_entries(history_path: Path | None = None) -> list[str]:
    """加载最近输入历史；文件缺失或损坏时返回空列表。"""

    target = history_path or XINGCODE_HISTORY_PATH
    if not target.exists():
        return []

    try:
        parsed = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    entries = parsed.get("entries", [])
    return [str(entry) for entry in entries] if isinstance(entries, list) else []


def save_history_entries(entries: list[str], history_path: Path | None = None) -> None:
    """保存最近输入历史，并只保留最后 200 条记录。"""

    target = history_path or XINGCODE_HISTORY_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"entries": entries[-MAX_HISTORY_ENTRIES:]}, indent=2) + "\n",
        encoding="utf-8",
    )


def remember_history_entry(
    entries: list[str],
    entry: str,
    history_path: Path | None = None,
) -> list[str]:
    """把一条输入加入历史，并避免连续重复项污染最近历史。"""

    normalized = entry.strip()
    next_entries = list(entries)
    if normalized and (not next_entries or next_entries[-1] != normalized):
        next_entries.append(normalized)
        save_history_entries(next_entries, history_path)
    return next_entries


def format_history_entries(entries: list[str], limit: int = 20) -> str:
    """把最近历史格式化成带序号的多行文本。"""

    if not entries:
        return ""

    start = max(0, len(entries) - limit)
    return "\n".join(
        f"{start + index + 1}. {entry}"
        for index, entry in enumerate(entries[start:])
    )
