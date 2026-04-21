from __future__ import annotations

import os
import shlex
import subprocess
from typing import Sequence

from XingCode.core.tooling import ToolDefinition, ToolResult
from XingCode.security.workspace import resolve_tool_path

COMMAND_TIMEOUT = 300
MAX_OUTPUT_CHARS = 200_000

READONLY_COMMANDS = {
    "pwd",
    "ls",
    "find",
    "rg",
    "grep",
    "cat",
    "head",
    "tail",
    "wc",
    "sed",
    "echo",
    "df",
    "du",
    "whoami",
    "dir",
    "type",
    "where",
    "findstr",
    "more",
    "hostname",
}

DEVELOPMENT_COMMANDS = {
    "git",
    "npm",
    "node",
    "python",
    "python3",
    "pytest",
    "bash",
    "sh",
    "pip",
    "pip3",
    "cargo",
    "go",
    "make",
    "cmake",
    "dotnet",
    "powershell",
    "pwsh",
    "cmd",
}


def _truncate_large_output(output: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    """Trim very large command output while preserving useful head and tail context."""

    if len(output) <= max_chars:
        return output

    lines = output.split("\n")
    total_lines = len(lines)
    head_lines = max(1, int(total_lines * 0.6))
    tail_lines = max(1, total_lines - head_lines)
    if head_lines + tail_lines > total_lines:
        tail_lines = max(1, total_lines - head_lines)

    head = "\n".join(lines[:head_lines])
    tail = "\n".join(lines[-tail_lines:])
    omitted = max(0, total_lines - head_lines - tail_lines)
    return f"{head}\n\n... [{omitted} lines omitted, output was {len(output):,} chars] ...\n\n{tail}"


def split_command_line(command_line: str) -> list[str]:
    """Split a shell-style command line into tokens on the current platform."""

    if os.name == "nt":
        try:
            return shlex.split(command_line, posix=False)
        except ValueError:
            return command_line.split()
    return shlex.split(command_line, posix=True)


def _is_allowed_command(command: str) -> bool:
    """Check whether a command is in the built-in read-only or development sets."""

    normalized = command.lower() if os.name == "nt" else command
    return normalized in READONLY_COMMANDS or normalized in DEVELOPMENT_COMMANDS


def _is_read_only_command(command: str) -> bool:
    """Check whether a command belongs to the read-only subset."""

    normalized = command.lower() if os.name == "nt" else command
    return normalized in READONLY_COMMANDS


def _looks_like_shell_snippet(command: str, args: list[str]) -> bool:
    """Detect commands that should run through the shell rather than direct exec."""

    return not args and any(char in command for char in "|&;<>()$`")


def _is_background_shell_snippet(command: str, args: list[str]) -> bool:
    """Detect a trailing '&' background shell snippet."""

    trimmed = command.strip()
    return not args and trimmed.endswith("&") and not trimmed.endswith("&&")


def _strip_trailing_background_operator(command: str) -> str:
    """Remove one trailing background operator before building the actual shell command."""

    return command.strip().removesuffix("&").strip()


def _normalize_command_input(input_data: dict) -> tuple[str, list[str]]:
    """Resolve the effective command and args from either command+args or command text."""

    command = str(input_data.get("command", "")).strip()
    raw_args = input_data.get("args") or []
    if raw_args:
        return command, [str(arg) for arg in raw_args]
    parsed = split_command_line(command) if command else []
    return (parsed[0], parsed[1:]) if parsed else ("", [])


def _is_windows_shell_builtin(command: str) -> bool:
    """Detect Windows builtins that must run through cmd.exe."""

    return os.name == "nt" and command.lower() in {
        "cd",
        "chdir",
        "cls",
        "copy",
        "date",
        "del",
        "dir",
        "echo",
        "erase",
        "md",
        "mkdir",
        "mklink",
        "move",
        "rd",
        "ren",
        "rename",
        "rmdir",
        "time",
        "type",
        "ver",
        "vol",
    }


def _build_execution_command(
    raw_command: str,
    normalized_command: str,
    normalized_args: Sequence[str],
    *,
    use_shell: bool,
    background_shell: bool,
) -> tuple[str, list[str]]:
    """Build the final executable plus argv after shell/builtin normalization."""

    if use_shell:
        shell_command = _strip_trailing_background_operator(raw_command) if background_shell else raw_command
        if os.name == "nt":
            return "cmd", ["/d", "/s", "/c", shell_command]
        shell = os.environ.get("SHELL", "/bin/sh")
        return shell, ["-lc", shell_command]

    if _is_windows_shell_builtin(normalized_command):
        quoted_args = subprocess.list2cmdline(list(normalized_args))
        shell_command = normalized_command if not quoted_args else f"{normalized_command} {quoted_args}"
        return "cmd", ["/d", "/s", "/c", shell_command]

    return normalized_command, list(normalized_args)


def _validate(input_data: dict) -> dict:
    """Validate and normalize the run_command input payload."""

    command = input_data.get("command")
    args = input_data.get("args") or []
    cwd = input_data.get("cwd")

    if not isinstance(command, str):
        raise ValueError("command is required")
    if not isinstance(args, list):
        raise ValueError("args must be a list")
    if cwd is not None and not isinstance(cwd, str):
        raise ValueError("cwd must be a string")

    timeout = input_data.get("timeout")
    if timeout is not None:
        try:
            timeout = max(1, min(600, int(timeout)))
        except (TypeError, ValueError):
            timeout = None

    return {
        "command": command,
        "args": [str(arg) for arg in args],
        "cwd": cwd,
        "timeout": timeout,
    }

def _coerce_timeout_output(value: str | bytes | None) -> str:
    """Normalize timeout partial output into a safe UTF-8 string."""

    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    return value.strip()

#     【核心】安全执行命令 1) 路径安全校验 2) 命令白名单校验 3) 权限校验 4) 跨平台执行 5) 超时保护 6) 输出截断
def _run(input_data: dict, context) -> ToolResult:
    """Execute a command with cwd, permission checks, timeout handling, and output truncation."""

    effective_cwd = (
        str(resolve_tool_path(context, input_data["cwd"], "command_cwd"))
        if input_data.get("cwd")
        else context.cwd
    )
    normalized_command, normalized_args = _normalize_command_input(input_data)
    if not normalized_command:
        return ToolResult(ok=False, output="Command not allowed: empty command")

    raw_args = input_data.get("args") or []
    use_shell = _looks_like_shell_snippet(input_data["command"], raw_args)
    background_shell = _is_background_shell_snippet(input_data["command"], raw_args)
    if background_shell:
        return ToolResult(ok=False, output="Background commands are not supported yet.")

    known_command = _is_allowed_command(normalized_command)
    command, args = _build_execution_command(
        input_data["command"],
        normalized_command,
        normalized_args,
        use_shell=use_shell,
        background_shell=background_shell,
    )
    force_prompt_reason = (
        None
        if use_shell or known_command
        else f"Unknown command '{normalized_command}' is not in the built-in read-only/development set"
    )

    # Keep command approval separate from path approval: the cwd is reviewed
    # through the workspace boundary first, then the command itself is checked.
    if context.permissions is not None:
        if force_prompt_reason:
            context.permissions.ensure_command(command, args, effective_cwd, force_prompt_reason=force_prompt_reason)
        elif use_shell or not _is_read_only_command(normalized_command):
            context.permissions.ensure_command(command, args, effective_cwd)

    effective_timeout = input_data.get("timeout") or COMMAND_TIMEOUT
    try:
        completed = subprocess.run(
            [command, *args],
            cwd=effective_cwd,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=effective_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        # Return partial output when possible so later agent steps still have
        # some execution context instead of a bare timeout message.
        partial_stdout = _coerce_timeout_output(exc.stdout)
        partial_stderr = _coerce_timeout_output(exc.stderr)
        partial = "\n".join(part for part in [partial_stdout, partial_stderr] if part)
        if partial:
            partial = f"\nPartial output:\n{_truncate_large_output(partial)}"
        return ToolResult(
            ok=False,
            output=f"Command timed out after {effective_timeout} seconds (process killed).{partial}",
        )

    output = "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part).strip()
    output = _truncate_large_output(output)
    return ToolResult(ok=completed.returncode == 0, output=output)

# 注册命令执行工具
run_command_tool = ToolDefinition(
    name="run_command",
    description="Run a common development command with optional cwd and timeout.",
    input_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "args": {"type": "array", "items": {"type": "string"}},
            "cwd": {"type": "string"},
            "timeout": {"type": "integer"},
        },
        "required": ["command"],
    },
    validator=_validate,
    run=_run,
)
