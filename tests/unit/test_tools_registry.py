from __future__ import annotations

from XingCode.core.tooling import ToolContext
from XingCode.tools import create_default_tool_registry

# 测 “工具箱里有没有装全工具”
def test_create_default_tool_registry_contains_phase_three_tools() -> None:
    registry = create_default_tool_registry("/tmp/workspace")
    tool_names = [tool.name for tool in registry.list()]

    assert tool_names == [
        "ask_user",
        "list_files",
        "read_file",
        "write_file",
        "edit_file",
        "patch_file",
        "run_command",
    ]

# 测 “工具箱能不能正常调用工具”
def test_registry_can_execute_ask_user_and_pause_turn() -> None:
    registry = create_default_tool_registry("/tmp/workspace")

    result = registry.execute(
        "ask_user",
        {"question": "Which file should I open next?"},
        ToolContext(cwd="."),
    )

    assert result.ok is True
    assert result.awaitUser is True
    assert result.output == "Which file should I open next?"
