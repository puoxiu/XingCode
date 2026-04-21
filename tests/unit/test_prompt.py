from pathlib import Path

from XingCode.core.prompt import build_system_prompt
from XingCode.core.tooling import ToolDefinition, ToolRegistry, ToolResult


def _build_registry() -> ToolRegistry:
    """Create a small registry so the prompt builder can render tool inventory."""

    return ToolRegistry(
        [
            ToolDefinition(
                name="read_file",
                description="Read file content.",
                input_schema={"type": "object"},
                validator=lambda value: value,
                run=lambda _input, _context: ToolResult(ok=True, output="ok"),
            ),
            ToolDefinition(
                name="run_command",
                description="Run a local command.",
                input_schema={"type": "object"},
                validator=lambda value: value,
                run=lambda _input, _context: ToolResult(ok=True, output="ok"),
            ),
        ]
    )


def test_build_system_prompt_includes_base_sections(tmp_path: Path) -> None:
    """The base prompt should include role, cwd, permissions, and tools."""

    prompt = build_system_prompt(
        str(tmp_path),
        tools=_build_registry(),
        permission_summary=["cwd: /tmp/demo", "extra allowed dirs: none"],
    )

    assert "You are XingCode" in prompt
    assert f"Current cwd: {tmp_path}" in prompt
    assert "Permission context:" in prompt
    assert "cwd: /tmp/demo" in prompt
    assert "Available tools:" in prompt
    assert "read_file: Read file content." in prompt
    assert "run_command: Run a local command." in prompt


def test_build_system_prompt_includes_skills_and_mcp(tmp_path: Path) -> None:
    """Optional skills and MCP summaries should be appended when provided."""

    prompt = build_system_prompt(
        str(tmp_path),
        tools=[],
        permission_summary=[],
        extras={
            "skills": [{"name": "demo", "description": "demo skill"}],
            "mcpServers": [
                {
                    "name": "fake",
                    "status": "connected",
                    "toolCount": 1,
                    "resourceCount": 1,
                    "promptCount": 1,
                    "protocol": "newline-json",
                }
            ],
        },
    )

    assert "Available skills:" in prompt
    assert "demo: demo skill" in prompt
    assert "Configured MCP servers:" in prompt
    assert "fake: connected, tools=1, resources=1, prompts=1, protocol=newline-json" in prompt


def test_build_system_prompt_mentions_sequential_thinking_server(tmp_path: Path) -> None:
    """Sequential thinking MCP servers should add a focused usage hint."""

    prompt = build_system_prompt(
        str(tmp_path),
        tools=[],
        permission_summary=[],
        extras={
            "mcpServers": [
                {"name": "SequentialThinking", "status": "connected", "toolCount": 1}
            ]
        },
    )

    assert "SEQUENTIAL THINKING MCP SERVER IS CONNECTED" in prompt
    assert "sequential_thinking" in prompt


def test_build_system_prompt_handles_missing_optional_sections(tmp_path: Path) -> None:
    """The prompt builder should still produce a complete prompt without extras."""

    prompt = build_system_prompt(str(tmp_path))

    assert f"Current cwd: {tmp_path}" in prompt
    assert "Permission context:" in prompt
    assert "none recorded yet" in prompt
    assert "Available tools:" in prompt
    assert "none registered yet" in prompt
