"""CLI command helpers for XingCode."""

from XingCode.commands.cli_commands import (
    SLASH_COMMANDS,
    SlashCommand,
    complete_slash_command,
    find_matching_slash_commands,
    format_slash_commands,
    handle_cli_input,
    parse_local_tool_shortcut,
    try_execute_local_tool_command,
    try_handle_local_command,
)
from XingCode.commands.manage_cli import maybe_handle_management_command

__all__ = [
    "SLASH_COMMANDS",
    "SlashCommand",
    "complete_slash_command",
    "find_matching_slash_commands",
    "format_slash_commands",
    "handle_cli_input",
    "maybe_handle_management_command",
    "parse_local_tool_shortcut",
    "try_execute_local_tool_command",
    "try_handle_local_command",
]
