from __future__ import annotations

from pathlib import Path

from XingCode.storage.history import (
    format_history_entries,
    load_history_entries,
    remember_history_entry,
    save_history_entries,
)


def test_load_history_entries_returns_empty_when_file_is_missing(tmp_path: Path) -> None:
    """历史文件不存在时，应该返回空列表。"""

    assert load_history_entries(tmp_path / "missing-history.json") == []


def test_load_history_entries_returns_empty_when_json_is_invalid(tmp_path: Path) -> None:
    """历史文件损坏时，不应该让 CLI 崩掉。"""

    history_path = tmp_path / "history.json"
    history_path.write_text("{not-json}\n", encoding="utf-8")

    assert load_history_entries(history_path) == []


def test_save_history_entries_keeps_only_last_two_hundred(tmp_path: Path) -> None:
    """保存历史时，应只保留最近 200 条输入。"""

    history_path = tmp_path / "history.json"
    entries = [f"cmd-{index}" for index in range(205)]

    save_history_entries(entries, history_path)

    persisted = load_history_entries(history_path)
    assert len(persisted) == 200
    assert persisted[0] == "cmd-5"
    assert persisted[-1] == "cmd-204"


def test_remember_history_entry_skips_consecutive_duplicates(tmp_path: Path) -> None:
    """连续重复输入不应该反复写入最近历史。"""

    history_path = tmp_path / "history.json"
    entries = remember_history_entry([], "  /help  ", history_path)
    entries = remember_history_entry(entries, "/help", history_path)

    assert entries == ["/help"]
    assert load_history_entries(history_path) == ["/help"]


def test_format_history_entries_renders_recent_numbered_slice() -> None:
    """历史展示应保留原始序号，便于用户定位最近命令。"""

    rendered = format_history_entries(["/help", "build parser", "/cmd pytest -q"], limit=2)

    assert rendered == "2. build parser\n3. /cmd pytest -q"
