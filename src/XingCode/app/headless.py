from __future__ import annotations

import sys
from pathlib import Path

from XingCode.adapters import create_model_adapter
from XingCode.commands import handle_cli_input
from XingCode.core import build_system_prompt, run_agent_turn
from XingCode.core.context_manager import ContextManager
from XingCode.security import PermissionManager
from XingCode.storage import (
    SessionData,
    load_history_entries,
    load_runtime_config,
    remember_history_entry,
    save_session,
)
from XingCode.tools import create_default_tool_registry


def _read_prompt_from_stdin() -> str:
    """从标准输入读取一次性 prompt。"""

    if sys.stdin.isatty():
        raise ValueError("Headless mode requires a prompt argument or piped stdin.")
    return sys.stdin.read().strip()


def _extract_last_assistant_text(messages: list[dict]) -> str:
    """从消息列表里提取最后一条 assistant 文本。"""

    last_assistant = next(
        (message for message in reversed(messages) if message.get("role") == "assistant"),
        None,
    )
    return str(last_assistant.get("content", "")) if last_assistant is not None else "(no response)"


def run_headless(
    prompt: str | None = None,
    cwd: str | None = None,
    *,
    session: SessionData | None = None,
) -> str:
    """运行一次无 UI 的单轮 Agent，并返回 assistant 文本。"""

    effective_cwd = str(Path(cwd or Path.cwd()).resolve())
    effective_prompt = prompt if prompt is not None else _read_prompt_from_stdin()
    if not effective_prompt.strip():
        raise ValueError("Prompt cannot be empty.")

    # 先创建工具与权限，再处理本地 slash 命令，这样 /help、/read、/cmd 不依赖模型配置。
    permissions = PermissionManager(effective_cwd, prompt=None)
    tools = create_default_tool_registry(effective_cwd, runtime=None)

    try:
        history_entries = remember_history_entry(load_history_entries(), effective_prompt)
        cli_output = handle_cli_input(
            effective_prompt.strip(),
            cwd=effective_cwd,
            tools=tools,
            permissions=permissions,
            history_entries=history_entries,
        )
        if cli_output is not None:
            if session is not None:
                session.history = list(history_entries)
                session.permissions_summary = list(permissions.get_summary())
                session.skills = tools.get_skills()
                session.mcp_servers = tools.get_mcp_servers()
                save_session(session)
            return cli_output

        runtime = load_runtime_config(effective_cwd)
        tools.dispose()
        # 进入真实模型链路前，用 runtime 重新创建 tools，确保 MCP 等 runtime 相关能力能接入。
        tools = create_default_tool_registry(effective_cwd, runtime=runtime)
        model = create_model_adapter(runtime.get("model"), tools, runtime)
        context_manager = ContextManager(model=runtime.get("model", "default"))

        # 如果传入了 session，则沿用历史消息继续会话；否则保持原来的单轮模式。
        messages = list(session.messages) if session is not None else []
        system_message = {
            "role": "system",
            "content": build_system_prompt(
                effective_cwd,
                tools=tools,
                permission_summary=permissions.get_summary(),
            ),
        }
        if messages and messages[0].get("role") == "system":
            messages[0] = system_message
        else:
            messages.insert(0, system_message)
        messages.append({"role": "user", "content": effective_prompt})

        result_messages = run_agent_turn(
            model=model,
            tools=tools,
            messages=messages,
            cwd=effective_cwd,
            permissions=permissions,
            context_manager=context_manager,
            runtime=runtime,
        )
        if session is not None:
            session.messages = list(result_messages)
            session.history = list(history_entries)
            session.permissions_summary = list(permissions.get_summary())
            session.skills = tools.get_skills()
            session.mcp_servers = tools.get_mcp_servers()
            save_session(session)
    finally:
        tools.dispose()

    return _extract_last_assistant_text(result_messages)


def main() -> None:
    """headless 模块的命令行入口。"""

    prompt = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else None
    try:
        response = run_headless(prompt)
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(response)


if __name__ == "__main__":
    main()
