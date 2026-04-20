from __future__ import annotations

from pathlib import Path

from XingCode.core.tooling import ToolContext
from XingCode.security.file_review import (
    apply_reviewed_file_change,
    build_unified_diff,
    load_existing_file,
)
from XingCode.security.permissions import PermissionManager


def test_build_unified_diff_returns_no_changes_marker() -> None:
    diff = build_unified_diff("demo.txt", "same", "same")

    assert diff == "(no changes for demo.txt)"


def test_build_unified_diff_includes_headers_and_hunks() -> None:
    diff = build_unified_diff("demo.txt", "old line\nstay", "new line\nstay")

    assert "--- a/demo.txt" in diff
    assert "+++ b/demo.txt" in diff
    assert "-old line" in diff
    assert "+new line" in diff


def test_load_existing_file_returns_empty_for_missing_file(tmp_path: Path) -> None:
    content = load_existing_file(tmp_path / "missing.txt")

    assert content == ""


def test_apply_reviewed_file_change_writes_file_after_permission_review(tmp_path: Path) -> None:
    requests: list[dict] = []

    def prompt(request: dict) -> dict:
        requests.append(request)
        return {"decision": "allow_once"}

    context = ToolContext(
        cwd=str(tmp_path),
        permissions=PermissionManager(str(tmp_path), prompt=prompt),
    )

    result = apply_reviewed_file_change(
        context,
        "demo.txt",
        tmp_path / "demo.txt",
        "hello world",
    )

    assert result.ok is True
    assert (tmp_path / "demo.txt").read_text(encoding="utf-8") == "hello world"
    assert requests[0]["kind"] == "edit"
    assert "--- a/demo.txt" in requests[0]["details"][2]


def test_apply_reviewed_file_change_returns_early_when_content_is_identical(tmp_path: Path) -> None:
    target = tmp_path / "demo.txt"
    target.write_text("hello world", encoding="utf-8")
    context = ToolContext(cwd=str(tmp_path))

    result = apply_reviewed_file_change(
        context,
        "demo.txt",
        target,
        "hello world",
    )

    assert result.ok is True
    assert result.output == "No changes needed for demo.txt"
