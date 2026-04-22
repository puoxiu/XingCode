from __future__ import annotations

import sys
from pathlib import Path

from XingCode.adapters import create_model_adapter
from XingCode.core import build_system_prompt, run_agent_turn
from XingCode.security import PermissionManager
from XingCode.storage import load_runtime_config
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


def run_headless(prompt: str | None = None, cwd: str | None = None) -> str:
    """运行一次无 UI 的单轮 Agent，并返回 assistant 文本。"""

    effective_cwd = str(Path(cwd or Path.cwd()).resolve())
    effective_prompt = prompt if prompt is not None else _read_prompt_from_stdin()
    if not effective_prompt.strip():
        raise ValueError("Prompt cannot be empty.")

    runtime = load_runtime_config(effective_cwd)
    tools = create_default_tool_registry(effective_cwd, runtime=runtime)
    permissions = PermissionManager(effective_cwd, prompt=None)
    model = create_model_adapter(runtime.get("model"), tools, runtime)

    # headless 入口只做一轮，因此系统 prompt 和用户输入一次性组装即可。
    messages = [
        {
            "role": "system",
            "content": build_system_prompt(
                effective_cwd,
                tools=tools,
                permission_summary=permissions.get_summary(),
            ),
        },
        {"role": "user", "content": effective_prompt},
    ]

    try:
        result_messages = run_agent_turn(
            model=model,
            tools=tools,
            messages=messages,
            cwd=effective_cwd,
            permissions=permissions,
            runtime=runtime,
        )
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
