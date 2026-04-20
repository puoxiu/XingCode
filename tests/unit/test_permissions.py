from __future__ import annotations

from pathlib import Path

import pytest

from XingCode.core.tooling import ToolContext
from XingCode.security.permissions import PermissionManager
from XingCode.security.workspace import resolve_tool_path

# 访问本级目录 正常应该被允许
def test_resolve_tool_path_resolves_relative_path_inside_workspace(tmp_path: Path) -> None:
    context = ToolContext(cwd=str(tmp_path))

    resolved = resolve_tool_path(context, "nested/demo.txt", "read")

    assert resolved == (tmp_path / "nested" / "demo.txt").resolve()

# 测试访问上级目录，正确情况下被拦截
def test_resolve_tool_path_blocks_escape_without_permissions(tmp_path: Path) -> None:
    context = ToolContext(cwd=str(tmp_path))

    with pytest.raises(PermissionError, match="Path escapes workspace"):
        resolve_tool_path(context, "../outside.txt", "read")

# 访问外部路径 → 触发用户确认弹窗
def test_permission_manager_uses_prompt_for_external_path(tmp_path: Path) -> None:
    requests: list[dict] = []
    external = tmp_path.parent / "outside.txt"

    def prompt(request: dict) -> dict:
        requests.append(request)
        return {"decision": "allow_once"}

    manager = PermissionManager(str(tmp_path), prompt=prompt)
    manager.ensure_path_access(str(external), "read")

    assert requests[0]["kind"] == "path"
    assert requests[0]["scope"] == str(external.parent.resolve())

# 没有弹窗交互时，直接拒绝外部路径
def test_permission_manager_denies_external_path_without_prompt(tmp_path: Path) -> None:
    external = tmp_path.parent / "outside.txt"
    manager = PermissionManager(str(tmp_path))

    with pytest.raises(RuntimeError, match="outside cwd"):
        manager.ensure_path_access(str(external), "read")

# 危险命令必须弹窗确认
def test_permission_manager_allows_safe_command_without_prompt(tmp_path: Path) -> None:
    manager = PermissionManager(str(tmp_path))

    manager.ensure_command("rg", ["needle"], str(tmp_path))

# 安全命令（如 rg 搜索）不需要确认
def test_permission_manager_requires_prompt_for_dangerous_command(tmp_path: Path) -> None:
    manager = PermissionManager(str(tmp_path))

    with pytest.raises(RuntimeError, match="Command requires approval"):
        manager.ensure_command("python", ["-c", "print(1)"], str(tmp_path))

# 危险命令必须弹窗确认
def test_permission_manager_uses_prompt_for_dangerous_command(tmp_path: Path) -> None:
    requests: list[dict] = []

    def prompt(request: dict) -> dict:
        requests.append(request)
        return {"decision": "allow_once"}

    manager = PermissionManager(str(tmp_path), prompt=prompt)
    manager.ensure_command("python", ["-c", "print(1)"], str(tmp_path))

    assert requests[0]["kind"] == "command"
    assert "python -c print(1)" in requests[0]["scope"]
    assert "arbitrary local code" in requests[0]["details"][2]

# 
def test_permission_manager_force_prompt_reason_prompts_for_safe_command(tmp_path: Path) -> None:
    requests: list[dict] = []

    def prompt(request: dict) -> dict:
        requests.append(request)
        return {"decision": "allow_once"}

    manager = PermissionManager(str(tmp_path), prompt=prompt)
    manager.ensure_command("echo", ["hello"], str(tmp_path), force_prompt_reason="manual review")

    assert requests[0]["kind"] == "command"
    assert requests[0]["details"][2] == "reason: manual review"

# 修改文件必须弹窗确认
def test_permission_manager_requires_prompt_for_edit(tmp_path: Path) -> None:
    manager = PermissionManager(str(tmp_path))

    with pytest.raises(RuntimeError, match="Edit requires approval"):
        manager.ensure_edit(str(tmp_path / "demo.txt"), "@@")

# 弹窗时显示文件修改 diff，让用户确认修改内容
def test_permission_manager_passes_diff_preview_to_edit_prompt(tmp_path: Path) -> None:
    requests: list[dict] = []
    diff_preview = "--- a/demo.txt\n+++ b/demo.txt\n@@\n-old\n+new"

    def prompt(request: dict) -> dict:
        requests.append(request)
        return {"decision": "allow_once"}

    manager = PermissionManager(str(tmp_path), prompt=prompt)
    manager.ensure_edit(str(tmp_path / "demo.txt"), diff_preview)

    assert requests[0]["kind"] == "edit"
    assert requests[0]["details"][2] == diff_preview

# 用户拒绝修改，并发送指导意见给 AI
def test_permission_manager_allow_all_turn_skips_second_prompt(tmp_path: Path) -> None:
    prompts: list[dict] = []

    def prompt(request: dict) -> dict:
        prompts.append(request)
        return {"decision": "allow_all_turn"}

    manager = PermissionManager(str(tmp_path), prompt=prompt)
    manager.begin_turn()
    manager.ensure_edit(str(tmp_path / "one.txt"), "@@")
    manager.ensure_edit(str(tmp_path / "two.txt"), "@@")

    assert len(prompts) == 1


def test_permission_manager_denies_edit_with_feedback(tmp_path: Path) -> None:
    manager = PermissionManager(
        str(tmp_path),
        prompt=lambda _request: {
            "decision": "deny_with_feedback",
            "feedback": "Please update the file header first.",
        },
    )

    with pytest.raises(RuntimeError, match="Please update the file header first."):
        manager.ensure_edit(str(tmp_path / "demo.txt"), "@@")
