from __future__ import annotations

from pathlib import Path

from XingCode.core.tooling import ToolContext
from XingCode.security.permissions import PermissionManager
from XingCode.tools.edit_file import edit_file_tool
from XingCode.tools.list_files import list_files_tool
from XingCode.tools.patch_file import patch_file_tool
from XingCode.tools.read_file import read_file_tool
from XingCode.tools.write_file import write_file_tool


def test_read_file_tool_supports_offset_and_limit(tmp_path: Path) -> None:
    target = tmp_path / "demo.txt"
    target.write_text("0123456789", encoding="utf-8")

    result = read_file_tool.run(
        {"path": "demo.txt", "offset": 2, "limit": 4},
        ToolContext(cwd=str(tmp_path)),
    )

    assert result.ok is True
    assert "FILE: demo.txt" in result.output
    assert "OFFSET: 2" in result.output
    assert "END: 6" in result.output
    assert "2345" in result.output


def test_list_files_tool_lists_sorted_entries(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "a-dir").mkdir()
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")

    result = list_files_tool.run({"path": "."}, ToolContext(cwd=str(tmp_path)))

    assert result.ok is True
    assert result.output.splitlines() == [
        "dir a-dir",
        "file a.txt",
        "file b.txt",
    ]


def test_write_file_tool_writes_after_review(tmp_path: Path) -> None:
    prompts: list[dict] = []

    def prompt(request: dict) -> dict:
        prompts.append(request)
        return {"decision": "allow_once"}

    permissions = PermissionManager(str(tmp_path), prompt=prompt)
    result = write_file_tool.run(
        {"path": "demo.txt", "content": "hello"},
        ToolContext(cwd=str(tmp_path), permissions=permissions),
    )

    assert result.ok is True
    assert (tmp_path / "demo.txt").read_text(encoding="utf-8") == "hello"
    assert prompts[0]["kind"] == "edit"


def test_edit_file_tool_replaces_unique_match(tmp_path: Path) -> None:
    target = tmp_path / "demo.txt"
    target.write_text("hello world\n", encoding="utf-8")
    permissions = PermissionManager(str(tmp_path), prompt=lambda _request: {"decision": "allow_once"})

    result = edit_file_tool.run(
        {"path": "demo.txt", "old": "hello world", "new": "hi world"},
        ToolContext(cwd=str(tmp_path), permissions=permissions),
    )

    assert result.ok is True
    assert target.read_text(encoding="utf-8") == "hi world\n"


def test_patch_file_tool_applies_multiple_replacements(tmp_path: Path) -> None:
    permissions = PermissionManager(str(tmp_path), prompt=lambda _request: {"decision": "allow_once"})
    target = tmp_path / "demo.txt"
    target.write_text("hello world\nhello cc\n", encoding="utf-8")

    result = patch_file_tool.run(
        {
            "path": "demo.txt",
            "replacements": [
                {"search": "hello world", "replace": "hi world"},
                {"search": "hello cc", "replace": "hi cc"},
            ],
        },
        ToolContext(cwd=str(tmp_path), permissions=permissions),
    )

    assert result.ok is True
    assert "2 replacement" in result.output
    assert target.read_text(encoding="utf-8") == "hi world\nhi cc\n"
