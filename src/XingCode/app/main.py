from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from XingCode.adapters import create_model_adapter
from XingCode.app.headless import run_headless
from XingCode.core import build_system_prompt, run_agent_turn
from XingCode.security import PermissionManager
from XingCode.storage import load_runtime_config
from XingCode.tools import create_default_tool_registry


def _make_cli_permission_prompt():
    """创建一个最小命令行权限提示器，用 stdin/stdout 完成交互。
        比如 AI 要删文件、读文件，会弹出：
        [y] Yes
        [n] No
    """

    def _prompt(request: dict[str, Any]) -> dict[str, Any]:
        print()
        print(request.get("summary", "Permission Request"))
        for detail in request.get("details", []):
            if detail:
                print(detail)

        choices = request.get("choices", [])
        for choice in choices:
            print(f"[{choice.get('key', '')}] {choice.get('label', '')}")

        answer = input("Choose: ").strip()
        for choice in choices:
            if answer == choice.get("key"):
                return {"decision": choice.get("decision", "deny_once")}
        return {"decision": "deny_once"}

    return _prompt


def _extract_last_assistant_text(messages: list[dict[str, Any]]) -> str:
    """从消息列表中取出最后一条 assistant 文本。"""

    last_assistant = next(
        (message for message in reversed(messages) if message.get("role") == "assistant"),
        None,
    )
    return str(last_assistant.get("content", "")) if last_assistant is not None else "(no response)"


def _validate_runtime_config(cwd: str) -> tuple[bool, str]:
    """校验当前配置是否可用，并返回可直接打印的结果文本。"""

    try:
        runtime = load_runtime_config(cwd)
    except Exception as exc:  # noqa: BLE001
        return False, f"Configuration error: {exc}"

    lines = [
        "Configuration OK",
        f"model: {runtime.get('model', '')}",
        f"provider: {runtime.get('provider', '')}",
        f"baseUrl: {runtime.get('baseUrl', '')}",
    ]
    return True, "\n".join(lines)


def _load_runtime_or_fallback(cwd: str) -> tuple[dict[str, Any] | None, bool]:
    """尽量加载真实 runtime；失败时回退到 mock 模式，方便本地继续使用。"""
    try:
        return load_runtime_config(cwd), False
    except Exception as exc:  # noqa: BLE001
        print(
            f"Warning: failed to load runtime config: {exc}\nFalling back to mock model.",
            file=sys.stderr,
        )
        return None, True


def _run_interactive_session(cwd: str, runtime: dict[str, Any] | None, force_mock: bool) -> int:
    """运行最简单的 stdin/stdout 交互循环。"""

    prompt_handler = _make_cli_permission_prompt()
    tools = create_default_tool_registry(cwd, runtime=runtime)  # 创建默认工具注册
    permissions = PermissionManager(cwd, prompt=prompt_handler)  # 创建权限管理器
    model = create_model_adapter(
        model=runtime.get("model") if runtime else None,
        tools=tools,
        runtime=runtime,
        force_mock=force_mock,
    )

    messages: list[dict[str, Any]] = []
    try:
        while True:
            try:
                user_input = input("xingcode> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0

            if not user_input:
                continue
            if user_input in {"/exit", "/quit"}:
                return 0

            # 每轮都重建 system prompt，确保权限摘要等动态信息保持最新。
            # 必须实时刷新，不能用旧的系统提示 所以第一条永远是最新的 system 系统提示词
            system_message = {
                "role": "system",
                "content": build_system_prompt(
                    cwd,
                    tools=tools,
                    permission_summary=permissions.get_summary(),
                ),
            }
            if messages and messages[0].get("role") == "system":
                messages[0] = system_message
            else:
                messages.insert(0, system_message)

            messages.append({"role": "user", "content": user_input})
            messages = run_agent_turn(
                model=model,
                tools=tools,
                messages=messages,
                cwd=cwd,
                permissions=permissions,
                runtime=runtime,
            )
            print(_extract_last_assistant_text(messages))
    finally:
        tools.dispose()


def main(argv: list[str] | None = None) -> int:
    """主 CLI 入口：支持 help、配置校验、安装和最小交互模式。"""

    parser = argparse.ArgumentParser(
        description="XingCode - A lightweight terminal coding assistant",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Run the minimal interactive installer",
    )
    parser.add_argument(
        "--validate-config",
        action="store_true",
        help="Validate runtime config and exit",
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Optional one-shot prompt. If omitted, XingCode reads stdin or enters interactive mode.",
    )
    args = parser.parse_args(argv)  # 解析命令行参数

    cwd = str(Path.cwd())   # 当前工作目录

    if args.install:
        # 如果指定了安装参数，运行安装向导
        # python -m XingCode.app.main --install
        from XingCode.app.install import main as install_main

        install_main()
        return 0

    if args.validate_config:
        # 如果指定了校验配置参数，校验当前配置
        # python -m XingCode.app.main --validate-config
        print("校验当前配置...")
        is_valid, output = _validate_runtime_config(cwd)
        stream = sys.stdout if is_valid else sys.stderr
        print(output, file=stream)
        return 0 if is_valid else 1

    if args.prompt:
        # 如果指定了 prompt 参数，运行 headless 模式
        # python -m XingCode.app.main "你的问题"
        try:
            print(run_headless(" ".join(args.prompt), cwd=cwd))
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    if not sys.stdin.isatty():
        # 如果标准输入不是终端，运行 headless 模式
        try:
            print(run_headless(None, cwd=cwd))
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    runtime, force_mock = _load_runtime_or_fallback(cwd)
    return _run_interactive_session(cwd, runtime, force_mock)


if __name__ == "__main__":
    raise SystemExit(main())
