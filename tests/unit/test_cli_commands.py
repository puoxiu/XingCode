from __future__ import annotations

from pathlib import Path

from XingCode.commands import (
    find_matching_slash_commands,
    format_slash_commands,
    handle_cli_input,
    parse_local_tool_shortcut,
)
from XingCode.security import PermissionManager
from XingCode.tools import create_default_tool_registry


def test_format_slash_commands_includes_phase_ten_commands() -> None:
    """帮助文本应覆盖 Phase 10 约定的本地命令。"""

    commands = format_slash_commands()

    assert "/help" in commands
    assert "/tools" in commands
    assert "/skills" in commands
    assert "/config" in commands
    assert "/permissions" in commands
    assert "/history" in commands
    assert "/read <path>" in commands
    assert "/cmd [cwd::]<command>" in commands


def test_find_matching_slash_commands_returns_prefixed_candidates() -> None:
    """输入前缀时，应返回可能匹配的命令用法。"""

    matches = find_matching_slash_commands("/c")

    assert "/config" in matches
    assert "/cmd [cwd::]<command>" in matches


def test_parse_local_tool_shortcut_parses_cmd_with_cwd_prefix() -> None:
    """`/cmd` 应支持 `cwd::command` 这种参考项目同款语法。"""

    shortcut = parse_local_tool_shortcut("/cmd src::git status")

    assert shortcut == {
        "toolName": "run_command",
        "input": {"command": "git status", "cwd": "src"},
    }


def test_handle_cli_input_renders_recent_history(tmp_path: Path) -> None:
    """`/history` 应返回最近输入历史，而不是进入模型。"""

    registry = create_default_tool_registry(str(tmp_path))
    permissions = PermissionManager(str(tmp_path), prompt=lambda request: {"decision": "allow_once"})

    output = handle_cli_input(
        "/history",
        cwd=str(tmp_path),
        tools=registry,
        permissions=permissions,
        history_entries=["/help", "build parser"],
    )

    assert output is not None
    assert "1. /help" in output
    assert "2. build parser" in output


def test_handle_cli_input_executes_read_shortcut(tmp_path: Path) -> None:
    """`/read` 应直接调用 read_file 工具。"""

    (tmp_path / "note.txt").write_text("hello from shortcut", encoding="utf-8")
    registry = create_default_tool_registry(str(tmp_path))
    permissions = PermissionManager(str(tmp_path), prompt=lambda request: {"decision": "allow_once"})

    output = handle_cli_input(
        "/read note.txt",
        cwd=str(tmp_path),
        tools=registry,
        permissions=permissions,
        history_entries=[],
    )

    assert output is not None
    assert "FILE: note.txt" in output
    assert "hello from shortcut" in output


def test_handle_cli_input_lists_discovered_skills(tmp_path: Path) -> None:
    """`/skills` 应直接显示当前发现的 skill 摘要。"""

    skill_file = tmp_path / ".xingcode" / "skills" / "demo" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text("# Demo\n\nProject description\n", encoding="utf-8")

    registry = create_default_tool_registry(str(tmp_path))
    permissions = PermissionManager(str(tmp_path), prompt=lambda request: {"decision": "allow_once"})

    output = handle_cli_input(
        "/skills",
        cwd=str(tmp_path),
        tools=registry,
        permissions=permissions,
        history_entries=[],
    )

    assert output is not None
    assert "demo: Project description [project]" in output


def test_handle_cli_input_suggests_similar_unknown_commands(tmp_path: Path) -> None:
    """未知 slash 命令应给出相近候选，避免用户卡住。"""

    registry = create_default_tool_registry(str(tmp_path))
    permissions = PermissionManager(str(tmp_path), prompt=lambda request: {"decision": "allow_once"})

    output = handle_cli_input(
        "/co",
        cwd=str(tmp_path),
        tools=registry,
        permissions=permissions,
        history_entries=[],
    )

    assert output == "Unknown command. Did you mean:\n/config"
