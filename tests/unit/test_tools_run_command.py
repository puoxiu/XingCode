from __future__ import annotations

import os
import sys
from pathlib import Path

from XingCode.core.tooling import ToolContext
from XingCode.security.permissions import PermissionManager
from XingCode.tools.run_command import (
    _build_execution_command,
    _truncate_large_output,
    run_command_tool,
    split_command_line,
)

# 命令行解析是否支持引号
def test_split_command_line_supports_quotes() -> None:
    result = split_command_line("git commit -m 'hello world'")

    assert result[:3] == ["git", "commit", "-m"]
    if os.name == "nt":
        assert result[3] == "'hello world'"
    else:
        assert result[3] == "hello world"


# 验证跨平台命令构建正确
def test_build_execution_command_uses_cmd_for_windows_shell_builtins() -> None:
    command, args = _build_execution_command(
        "echo hello world",
        "echo",
        ["hello", "world"],
        use_shell=False,
        background_shell=False,
    )

    if os.name == "nt":
        assert command == "cmd"
        assert args[:3] == ["/d", "/s", "/c"]
        assert args[3] == "echo hello world"
    else:
        assert command == "echo"
        assert args == ["hello", "world"]

# 基础命令 echo 能否正常运行
def test_run_command_tool_supports_echo_on_current_platform(tmp_path: Path) -> None:
    permissions = PermissionManager(str(tmp_path), prompt=lambda _request: {"decision": "allow_once"})

    result = run_command_tool.run(
        {"command": "echo hello"},
        ToolContext(cwd=str(tmp_path), permissions=permissions),
    )

    assert result.ok is True
    assert "hello" in result.output.lower()

# 指定 cwd（工作目录）是否生效
# 在子目录执行命令
# 验证AI 可以在指定目录下执行命令
# 验证路径解析安全、不越权
def test_run_command_tool_uses_requested_cwd(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    permissions = PermissionManager(str(tmp_path), prompt=lambda _request: {"decision": "allow_once"})

    result = run_command_tool.run(
        {
            "command": sys.executable,
            "args": ["-c", "import os; print(os.getcwd())"],
            "cwd": "nested",
        },
        ToolContext(cwd=str(tmp_path), permissions=permissions),
    )

    assert result.ok is True
    assert str(nested.resolve()) in result.output

# 测试：超时机制是否生效
def test_run_command_tool_returns_timeout_error(tmp_path: Path) -> None:
    permissions = PermissionManager(str(tmp_path), prompt=lambda _request: {"decision": "allow_once"})

    result = run_command_tool.run(
        {
            "command": sys.executable,
            "args": ["-c", "import time; time.sleep(2)"],
            "timeout": 1,
        },
        ToolContext(cwd=str(tmp_path), permissions=permissions),
    )

    assert result.ok is False
    assert "timed out after 1" in result.output

# 测试：超大输出截断是否正常
def test_truncate_large_output_inserts_omission_marker() -> None:
    output = "\n".join(f"line-{index}" for index in range(200))

    truncated = _truncate_large_output(output, max_chars=120)

    assert "... [" in truncated
    assert "output was" in truncated
