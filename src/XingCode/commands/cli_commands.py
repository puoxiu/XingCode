from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from XingCode.core.tooling import ToolContext, ToolRegistry
from XingCode.security import PermissionManager
from XingCode.storage.config import (
    XINGCODE_SETTINGS_PATH,
    load_effective_settings,
    load_runtime_config,
    project_settings_path,
)
from XingCode.storage.history import XINGCODE_HISTORY_PATH, format_history_entries


@dataclass(frozen=True, slots=True)
class SlashCommand:
    """描述一个本地 slash 命令的帮助信息。"""

    name: str
    usage: str
    description: str


# 第一版只暴露指南要求的高频命令，避免提前把后续 Phase 的命令塞进来。
SLASH_COMMANDS = [
    SlashCommand("/help", "/help", "显示本地 slash 命令帮助。"),
    SlashCommand("/tools", "/tools", "显示当前已注册工具和快捷命令。"),
    SlashCommand("/skills", "/skills", "显示当前发现的 skills。"),
    SlashCommand("/config", "/config", "显示当前配置诊断信息。"),
    SlashCommand("/permissions", "/permissions", "显示当前权限状态摘要。"),
    SlashCommand("/history", "/history", "显示最近输入历史。"),
    SlashCommand("/read", "/read <path>", "直接调用 read_file 工具读取文件。"),
    SlashCommand("/cmd", "/cmd [cwd::]<command>", "直接调用 run_command 工具执行本地命令。"),
    SlashCommand("/exit", "/exit", "退出交互式 XingCode。"),
]


def format_slash_commands() -> str:
    """把 Phase 10 支持的本地命令渲染为帮助文本。"""

    lines = ["XingCode Phase 10 本地命令：", ""]
    for command in SLASH_COMMANDS:
        lines.append(f"{command.usage:<28} {command.description}")
    lines.extend(
        [
            "",
            "说明：",
            "- `/read` 和 `/cmd` 会直接执行本地工具，不经过模型推理。",
            "- `/skills` 会显示当前工作区和用户目录中发现的 skills。",
            "- 普通自然语言输入仍会进入 Agent 主链路。",
        ]
    )
    return "\n".join(lines)


def find_matching_slash_commands(user_input: str) -> list[str]:
    """根据用户输入前缀，返回可能想输入的 slash 命令用法。"""

    return [command.usage for command in SLASH_COMMANDS if command.usage.startswith(user_input)]


def complete_slash_command(line: str) -> tuple[list[str], str]:
    """返回补全候选；无命中时返回全部命令，便于后续 UI 直接复用。"""

    hits = find_matching_slash_commands(line)
    return (hits if hits else [command.usage for command in SLASH_COMMANDS], line)


def _format_tools_summary(tools: ToolRegistry) -> str:
    """显示当前工具注册表和可直接使用的本地快捷命令。"""

    lines = ["当前已注册工具：", ""]
    for tool in tools.list():
        lines.append(f"- {tool.name}: {tool.description}")
    lines.extend(
        [
            "",
            "本地快捷命令：",
            "- /read <path>  -> read_file",
            "- /cmd [cwd::]<command>  -> run_command",
        ]
    )
    return "\n".join(lines)


def _format_skills_summary(tools: ToolRegistry) -> str:
    """显示当前 registry 中已经发现的 skill 摘要。"""

    skills = tools.get_skills()
    if not skills:
        return (
            "No skills discovered. Add skills under "
            "~/.xingcode/skills/<name>/SKILL.md, .xingcode/skills/<name>/SKILL.md, "
            ".claude/skills/<name>/SKILL.md, or ~/.claude/skills/<name>/SKILL.md."
        )

    lines = ["当前发现的 skills：", ""]
    for skill in skills:
        name = str(skill.get("name", "unknown"))
        description = str(skill.get("description", "")).strip() or "no description"
        source = str(skill.get("source", "unknown"))
        lines.append(f"- {name}: {description} [{source}]")
    return "\n".join(lines)


def _format_config_diagnostic(cwd: str) -> str:
    """显示当前工作区的配置路径、合并结果和 runtime 诊断。"""

    lines = [
        "XingCode 配置诊断",
        f"workspace: {Path(cwd).resolve()}",
        f"global settings: {XINGCODE_SETTINGS_PATH}",
        f"project settings: {project_settings_path(cwd)}",
        f"history file: {XINGCODE_HISTORY_PATH}",
    ]

    try:
        effective = load_effective_settings(cwd)
    except Exception as exc:  # noqa: BLE001
        lines.append(f"effective settings: not available ({exc})")
    else:
        lines.append(f"effective settings keys: {', '.join(sorted(effective)) or '(none)'}")

    try:
        runtime = load_runtime_config(cwd)
    except Exception as exc:  # noqa: BLE001
        lines.append(f"runtime: not available ({exc})")
        return "\n".join(lines)

    lines.extend(
        [
            "runtime:",
            f"- model: {runtime.get('model', '')}",
            f"- provider: {runtime.get('provider', '')}",
            f"- baseUrl: {runtime.get('baseUrl', '')}",
        ]
    )
    return "\n".join(lines)


def _format_permissions_summary(permissions: PermissionManager) -> str:
    """显示当前内存态权限摘要；本阶段不做磁盘持久化。"""

    lines = [
        "XingCode 权限状态（当前进程内存态）",
        "说明：Phase 10 只实现运行期权限，不做权限文件持久化。",
        f"workspace root: {permissions.workspace_root}",
        "",
        "summary:",
    ]
    lines.extend(f"- {item}" for item in permissions.get_summary())
    return "\n".join(lines)


def _format_recent_history(entries: list[str], limit: int = 20) -> str:
    """显示最近输入历史；没有记录时返回友好提示。"""

    rendered = format_history_entries(entries, limit=limit)
    if not rendered:
        return f"最近历史为空：{XINGCODE_HISTORY_PATH}"
    return "\n".join(
        [
            f"最近历史（{XINGCODE_HISTORY_PATH}）：",
            rendered,
        ]
    )


def parse_local_tool_shortcut(user_input: str) -> dict[str, Any] | None:
    """把 `/read`、`/cmd` 解析成可直接交给工具注册表执行的输入。"""

    if user_input.startswith("/read "):
        file_path = user_input[len("/read ") :].strip()
        return {"toolName": "read_file", "input": {"path": file_path}} if file_path else None

    if user_input.startswith("/cmd "):
        payload = user_input[len("/cmd ") :].strip()
        cwd, separator, command_text = payload.partition("::")
        text = command_text.strip() if separator else payload
        command_cwd = cwd.strip() if separator else None
        if not text:
            return None
        return {
            "toolName": "run_command",
            "input": {"command": text, "cwd": command_cwd or None},
        }

    return None


def try_handle_local_command(
    user_input: str,
    *,
    cwd: str,
    tools: ToolRegistry,
    permissions: PermissionManager,
    history_entries: list[str],
) -> str | None:
    """处理不需要进入模型的本地命令；不是本地命令时返回 `None`。"""

    if user_input in {"/", "/help"}:
        return format_slash_commands()
    if user_input == "/tools":
        return _format_tools_summary(tools)
    if user_input == "/skills":
        return _format_skills_summary(tools)
    if user_input == "/config":
        return _format_config_diagnostic(cwd)
    if user_input == "/permissions":
        return _format_permissions_summary(permissions)
    if user_input == "/history":
        return _format_recent_history(history_entries)
    if user_input == "/exit":
        return "Use /exit in interactive mode to close XingCode."
    if user_input == "/read":
        return "Usage: /read <path>"
    if user_input == "/cmd":
        return "Usage: /cmd [cwd::]<command>"
    return None


def try_execute_local_tool_command(
    user_input: str,
    *,
    cwd: str,
    tools: ToolRegistry,
    permissions: PermissionManager,
) -> str | None:
    """处理 `/read`、`/cmd` 这类工具快捷命令，并返回工具输出。"""

    shortcut = parse_local_tool_shortcut(user_input)
    if shortcut is None:
        return None

    result = tools.execute(
        shortcut["toolName"],
        shortcut["input"],
        ToolContext(cwd=cwd, permissions=permissions),
    )
    return result.output


def handle_cli_input(
    user_input: str,
    *,
    cwd: str,
    tools: ToolRegistry,
    permissions: PermissionManager,
    history_entries: list[str],
) -> str | None:
    """统一处理 Phase 10 的本地 slash 命令和工具快捷命令。"""

    local_result = try_handle_local_command(
        user_input,
        cwd=cwd,
        tools=tools,
        permissions=permissions,
        history_entries=history_entries,
    )
    if local_result is not None:
        return local_result

    tool_result = try_execute_local_tool_command(
        user_input,
        cwd=cwd,
        tools=tools,
        permissions=permissions,
    )
    if tool_result is not None:
        return tool_result

    if user_input.startswith("/"):
        matches = find_matching_slash_commands(user_input)
        if matches:
            return "Unknown command. Did you mean:\n" + "\n".join(matches)
        return "Unknown command. Type /help to see available commands."

    return None
