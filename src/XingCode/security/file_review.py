from __future__ import annotations

import difflib
from pathlib import Path

from XingCode.core.tooling import ToolContext, ToolResult


def build_unified_diff(file_path: str, before: str, after: str) -> str:
    """Build a compact unified diff preview for one file edit."""

    if before == after:
        return f"(no changes for {file_path})"

    diff = difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        lineterm="",
        n=3,
    )
    lines = [line for line in diff if not (line.startswith("=") and set(line.strip()) == {"="})]
    return "\n".join(lines)


def load_existing_file(target_path: str | Path) -> str:
    """Load an existing UTF-8 text file, or return an empty string for new files."""

    file_path = Path(target_path)
    if not file_path.exists():
        return ""
    return file_path.read_text(encoding="utf-8")


def apply_reviewed_file_change(
    context: ToolContext,
    file_path: str,
    target_path: str | Path,
    next_content: str,
) -> ToolResult:
    """Review a file change with diff approval and write only after approval passes."""

    target = Path(target_path)
    previous_content = load_existing_file(target)
    if previous_content == next_content:
        return ToolResult(ok=True, output=f"No changes needed for {file_path}")

    diff = build_unified_diff(file_path, previous_content, next_content)
    if context.permissions is not None:
        context.permissions.ensure_edit(str(target), diff)

    # Every write-capable tool reuses this helper so the diff review boundary
    # stays centralized in one place instead of being reimplemented per tool.
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(next_content, encoding="utf-8")
    return ToolResult(ok=True, output=f"Applied reviewed changes to {file_path}")
