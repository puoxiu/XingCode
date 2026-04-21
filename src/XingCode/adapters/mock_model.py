from __future__ import annotations

import time
from collections.abc import Callable

from XingCode.core.types import AgentStep, ChatMessage


# 辅助函数：从对话历史中，获取【最后一条用户发送的消息】
#  逻辑：倒序遍历消息列表，找到第一条 role=user 的消息，返回内容
#  参数：messages 完整的对话历史列表
# 返回：用户最后输入的文本，无则返回空字符串
def _last_user_message(messages: list[ChatMessage]) -> str:
    """Return the latest user message content, or an empty string when absent."""

    return next(
        (
            str(message.get("content", ""))
            for message in reversed(messages)
            if message.get("role") == "user"
        ),
        "",
    )

# 辅助函数：从对话历史中，获取【最后一条工具执行结果消息】
# 作用：判断是否有工具执行完成，需要模型总结结果
# 返回：最后一条 tool_result 消息，无则返回 None
def _last_tool_message(messages: list[ChatMessage]) -> ChatMessage | None:
    """Return the latest tool result message if the conversation has one."""

    return next(
        (message for message in reversed(messages) if message.get("role") == "tool_result"),
        None,
    )

# 辅助函数：获取【AI助手最后调用的工具名称】
# 作用：知道工具执行完后，是哪个工具返回的结果（read_file/run_command）
# 返回：工具名称，无则返回 None
def _latest_assistant_call(messages: list[ChatMessage]) -> str | None:
    """Return the most recent assistant tool name so tool results can be summarized."""

    call = next(
        (
            message
            for message in reversed(messages)
            if message.get("role") == "assistant_tool_call"
        ),
        None,
    )
    return str(call.get("toolName")) if call is not None and call.get("toolName") else None

# 【核心】模拟AI大模型适配器
# 作用：
# 1. 不依赖任何真实AI接口（OpenAI/Claude等）
# 2. 模拟大模型的行为：解析用户指令 → 调用工具 → 总结结果
# 3. 用于测试/调试整个工具调用闭环，验证系统流程是否正常
class MockModelAdapter:
    """Minimal mock adapter used to exercise the tool loop without any real API."""

    def next(
        self,
        messages: list[ChatMessage],    # 完整的对话历史消息列表
        on_stream_chunk: Callable[[str], None] | None = None,    # 流式输出回调函数
    ) -> AgentStep:
        """Translate a tiny slash-command subset into tool calls or assistant text."""

        _ = on_stream_chunk

        # 1. 检查是否有工具执行完成，需要模型总结结果
        tool_message = _last_tool_message(messages)
        if tool_message is not None:
            last_call = _latest_assistant_call(messages)
            tool_content = str(tool_message.get("content", ""))

            # Keep the mock model intentionally simple: it only labels a few tool
            # results so we can verify the message round-trip end to end.
            if last_call == "read_file":
                return AgentStep(type="assistant", content=f"File contents:\n\n{tool_content}")
            if last_call == "run_command":
                return AgentStep(type="assistant", content=f"Command output:\n\n{tool_content}")
            return AgentStep(type="assistant", content=f"Tool result:\n\n{tool_content}")

        # 2. 没有工具结果 → 解析【用户的最新输入指令】
        user_text = _last_user_message(messages).strip()
        tool_id = f"mock-{int(time.time() * 1000)}"

        # 规则1：用户输入 /read 文件名 → 调用 read_file 工具
        if user_text.startswith("/read "):
            return AgentStep(
                type="tool_calls",
                calls=[
                    {
                        "id": tool_id,
                        "toolName": "read_file",
                        "input": {"path": user_text[len('/read ') :].strip()},
                    }
                ],
            )

        # 规则2：用户输入 /cmd 命令 → 调用 run_command 工具
        if user_text.startswith("/cmd "):
            return AgentStep(
                type="tool_calls",
                calls=[
                    {
                        "id": tool_id,
                        "toolName": "run_command",
                        "input": {"command": user_text[len('/cmd ') :].strip()},
                    }
                ],
            )
        
        # 3. 用户输入不匹配任何指令 → 返回默认提示文本
        return AgentStep(
            type="assistant",
            content="\n".join(
                [
                    "This is the XingCode mock model.",
                    "You can try:",
                    "/read README.md",
                    "/cmd pwd",
                ]
            ),
        )
