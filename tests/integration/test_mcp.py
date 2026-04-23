from __future__ import annotations

from pathlib import Path

from XingCode.core.tooling import ToolContext
from XingCode.integrations import create_mcp_backed_tools


def test_create_mcp_backed_tools_supports_newline_json(tmp_path: Path) -> None:
    """MCP 集成应支持 stdio + newline-json，并暴露 tools/resources/prompts。"""

    server_script = Path(__file__).parent.parent / "fixtures" / "fake_mcp_server.py"
    mcp = create_mcp_backed_tools(
        cwd=str(tmp_path),
        mcp_servers={
            "fake": {
                "command": "python3",
                "args": [str(server_script)],
                "protocol": "newline-json",
            }
        },
    )

    tool_names = [tool.name for tool in mcp["tools"]]
    assert "mcp__fake__echo" in tool_names
    assert "list_mcp_resources" in tool_names
    assert "read_mcp_resource" in tool_names
    assert "list_mcp_prompts" in tool_names
    assert "get_mcp_prompt" in tool_names

    echo_tool = next(tool for tool in mcp["tools"] if tool.name == "mcp__fake__echo")
    assert echo_tool.input_schema == {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }
    result = echo_tool.run({"text": "hi"}, ToolContext(cwd=str(tmp_path)))
    assert result.ok is True
    assert result.output == "echo:hi"

    resource_tool = next(tool for tool in mcp["tools"] if tool.name == "read_mcp_resource")
    resource_result = resource_tool.run(
        {"server": "fake", "uri": "fake://hello"},
        ToolContext(cwd=str(tmp_path)),
    )
    assert resource_result.ok is True
    assert "hello resource" in resource_result.output

    prompt_tool = next(tool for tool in mcp["tools"] if tool.name == "get_mcp_prompt")
    prompt_result = prompt_tool.run(
        {"server": "fake", "name": "hello", "arguments": {"name": "cc"}},
        ToolContext(cwd=str(tmp_path)),
    )
    assert prompt_result.ok is True
    assert "hello cc" in prompt_result.output

    assert mcp["servers"][0]["status"] == "connected"
    assert mcp["servers"][0]["toolCount"] == 1
    assert mcp["servers"][0]["resourceCount"] == 1
    assert mcp["servers"][0]["promptCount"] == 1

    mcp["dispose"]()


def test_create_mcp_backed_tools_reports_start_errors(tmp_path: Path) -> None:
    """无效 MCP server 不应让整体崩溃，而应记录 error 状态。"""

    mcp = create_mcp_backed_tools(
        cwd=str(tmp_path),
        mcp_servers={
            "broken": {
                "command": "python3",
                "args": [str(tmp_path / "missing_fake_mcp_server.py")],
                "protocol": "newline-json",
            }
        },
    )

    assert mcp["tools"] == []
    assert mcp["servers"][0]["status"] == "error"
    assert mcp["servers"][0]["toolCount"] == 0
    assert mcp["servers"][0]["error"]

    mcp["dispose"]()
