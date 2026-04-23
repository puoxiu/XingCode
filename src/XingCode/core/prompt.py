from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from XingCode.core.prompt_pipeline import PromptPipeline
from XingCode.core.tooling import ToolDefinition, ToolRegistry

# 系统提示词的固定角色说明：保持简洁，让 Phase 6 先稳定产出完整 prompt。
BASE_ROLE_SECTION = """You are XingCode, a terminal coding assistant.
Default behavior:
- Inspect the repository before making changes.
- Use tools to read files, edit code, and verify behavior.
- Make minimal, working-oriented changes that match the user's request.
- If clarification is required, prefer the ask_user tool over plain assistant questions.
- Continue after tool results until the task is complete or you need the user.
- If the user names a skill or clearly asks for a workflow matching a listed skill, call load_skill before following it."""


def _normalize_tool_definitions(
    tools: ToolRegistry | Iterable[ToolDefinition] | None,
) -> list[ToolDefinition]:
    """Normalize either a ToolRegistry or an iterable of tools into one list."""

    if tools is None:
        return []
    if isinstance(tools, ToolRegistry):
        return tools.list()
    return list(tools)


def _format_tools_section(tools: ToolRegistry | Iterable[ToolDefinition] | None) -> str:
    """Render the tool inventory so later adapters know what the agent can call."""

    tool_definitions = _normalize_tool_definitions(tools)
    if not tool_definitions:
        return "Available tools:\n- none registered yet"

    lines = ["Available tools:"]
    for tool in tool_definitions:
        lines.append(f"- {tool.name}: {tool.description}")
    return "\n".join(lines)


def _format_permission_section(permission_summary: list[str] | None) -> str:
    """Render the permission summary already computed by the permission layer."""

    summary = permission_summary or ["none recorded yet"]
    lines = ["Permission context:"]
    lines.extend(f"- {item}" for item in summary)
    return "\n".join(lines)


def _format_skills_section(skills: list[dict[str, Any]]) -> str:
    """Render the optional skills summary when the runtime exposes skills."""

    lines = ["Available skills:"]
    for skill in skills:
        name = str(skill.get("name", "unknown"))
        description = str(skill.get("description", "")).strip() or "no description"
        lines.append(f"- {name}: {description}")
    return "\n".join(lines)


def _format_mcp_server_line(server: dict[str, Any]) -> str:
    """Format one MCP server summary in a stable single-line form."""

    name = str(server.get("name", "unknown"))
    status = str(server.get("status", "unknown"))
    line = f"- {name}: {status}"

    if server.get("toolCount") is not None:
        line += f", tools={server['toolCount']}"
    if server.get("resourceCount") is not None:
        line += f", resources={server['resourceCount']}"
    if server.get("promptCount") is not None:
        line += f", prompts={server['promptCount']}"
    if server.get("protocol"):
        line += f", protocol={server['protocol']}"
    if server.get("error"):
        line += f", error={server['error']}"

    return line


def _is_sequential_thinking_server(server: dict[str, Any]) -> bool:
    """Detect MCP servers whose purpose is structured step-by-step reasoning."""

    name = str(server.get("name", "")).lower()
    return (
        server.get("status") == "connected"
        and (
            "sequential" in name
            or "branch-thinking" in name
            or "think" in name
        )
    )


def _format_mcp_section(mcp_servers: list[dict[str, Any]]) -> str:
    """Render the optional MCP summary and highlight sequential thinking servers."""

    lines = ["Configured MCP servers:"]
    lines.extend(_format_mcp_server_line(server) for server in mcp_servers)

    # 参考项目会对 sequential thinking 类型的 server 追加提醒，这里保留
    # 这个最小行为，但继续用简单字符串拼接，不引入复杂 pipeline。
    if any(_is_sequential_thinking_server(server) for server in mcp_servers):
        lines.extend(
            [
                "",
                "SEQUENTIAL THINKING MCP SERVER IS CONNECTED",
                "Use sequential_thinking for step-by-step planning, debugging, and structured investigation.",
            ]
        )

    return "\n".join(lines)


def _merge_prompt_extras(
    tools: ToolRegistry | Iterable[ToolDefinition] | None,
    extras: dict[str, Any] | None,
) -> dict[str, Any]:
    """合并显式 extras 和 ToolRegistry 自带的 metadata。"""

    merged: dict[str, Any] = {}
    if isinstance(tools, ToolRegistry):
        merged.update(tools.build_prompt_extras())
    if extras:
        merged.update(extras)
    return merged


def build_system_prompt(
    cwd: str,
    tools: ToolRegistry | Iterable[ToolDefinition] | None = None,
    permission_summary: list[str] | None = None,
    extras: dict[str, Any] | None = None,
) -> str:
    """Build the Phase 6 system prompt from cwd, tools, permissions, and extras."""

    merged_extras = _merge_prompt_extras(tools, extras)
    # 当前阶段先引入 paragraph pipeline 的组织方式，但不输出动态边界，
    # 因为 adapter 还没有真正利用该边界做 prompt cache。
    pipeline = PromptPipeline(include_dynamic_boundary=False)
    pipeline.register_static("role", BASE_ROLE_SECTION)
    pipeline.register_static("cwd", f"Current cwd: {cwd}")
    pipeline.register_dynamic(
        "permissions",
        lambda: _format_permission_section(permission_summary),
    )
    pipeline.register_dynamic(
        "tools",
        lambda: _format_tools_section(tools),
    )

    skills = merged_extras.get("skills") or []
    if skills:
        pipeline.register_dynamic(
            "skills",
            lambda: _format_skills_section(list(skills)),
        )

    mcp_servers = merged_extras.get("mcpServers") or []
    if mcp_servers:
        pipeline.register_dynamic(
            "mcp",
            lambda: _format_mcp_section(list(mcp_servers)),
        )

    return pipeline.build()
