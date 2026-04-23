from __future__ import annotations

from collections.abc import Callable
from typing import Any

from XingCode.core.context_manager import ContextManager
from XingCode.core.tooling import ToolContext, ToolRegistry, ToolResult
from XingCode.core.types import AgentStep, ChatMessage, ModelAdapter

# 模型返回空响应时的提示词，用于引导模型继续输出，避免对话中断
NUDGE_AFTER_EMPTY_RESPONSE = (
    "Your last response was empty after recent tool results. Continue immediately "
    "with the next concrete step or an explicit final answer if the task is complete."
)
NUDGE_AFTER_EMPTY_NO_TOOLS = (
    "Your last response was empty. Continue immediately with a concrete next step "
    "or an explicit final answer if the task is complete."
)
NUDGE_CONTINUE = (
    "Continue immediately from your progress update with the next concrete step."
)
RESUME_AFTER_PAUSE = (
    "Resume from the previous pause and continue immediately with the next concrete step."
)
RESUME_AFTER_MAX_TOKENS = (
    "Your previous response stopped during thinking because it hit max_tokens. "
    "Resume immediately with the next concrete step."
)


def _is_empty_assistant_response(content: str) -> bool:
    """Return True when the assistant content is effectively empty."""

    return len(content.strip()) == 0

# 辅助函数：判断是否为进度更新
# 作用：用于在循环中，判断是否需要继续执行进度更新，还是直接结束循环
def _is_progress_step(step: AgentStep) -> bool:
    """Treat either kind/contentKind progress flags as a progress-only update."""

    return step.kind == "progress" or step.contentKind == "progress"

# 判断模型是否因为【可恢复的中断】而停止输出
# 满足条件：
# 1. 内容为空
# 2. 停止原因是 pause_turn 或 max_tokens
# 3. 被忽略的内容类型包含 thinking
# 作用：遇到模型意外中断时，可以重试让模型继续，而不是直接失败
def _is_recoverable_thinking_stop(step: AgentStep) -> bool:
    """Detect empty thinking stops that should be retried instead of failing the turn."""

    if not _is_empty_assistant_response(step.content):
        return False
    if step.diagnostics is None:
        return False
    if step.diagnostics.stopReason not in {"pause_turn", "max_tokens"}:
        return False
    return "thinking" in step.diagnostics.ignoredBlockTypes

# 处理并记录一条【进度消息】
# 1. 调用回调通知外部（如前端显示加载中）
# 2. 将进度消息存入对话历史（role=assistant_progress）
def _emit_progress(
    current_messages: list[ChatMessage],
    content: str,
    on_progress_message: Callable[[str], None] | None,
) -> None:
    """Record a progress message in both callbacks and the conversation transcript."""

    if on_progress_message is not None:
        on_progress_message(content)
    current_messages.append({"role": "assistant_progress", "content": content})

# 执行单个工具调用
# 参数：
# - call: 模型要求执行的工具信息（名称、参数）
# - tools: 工具注册表
# 返回：工具执行结果 ToolResult
def _execute_tool_call(
    call: dict[str, Any],
    tools: ToolRegistry,
    cwd: str,
    permissions: Any | None,
    runtime: dict[str, Any] | None,
) -> ToolResult:
    """Execute one tool call through the shared ToolRegistry wrapper."""

    return tools.execute(
        call["toolName"],
        call["input"],
        ToolContext(cwd=cwd, permissions=permissions, _runtime=runtime),
    )


def _append_tool_messages(
    current_messages: list[ChatMessage],
    call: dict[str, Any],
    result: ToolResult,
) -> None:
    """Write the assistant tool call and tool result back into the transcript."""

    current_messages.append(
        {
            "role": "assistant_tool_call",
            "toolUseId": call["id"],
            "toolName": call["toolName"],
            "input": call["input"],
        }
    )
    current_messages.append(
        {
            "role": "tool_result",
            "toolUseId": call["id"],
            "toolName": call["toolName"],
            "content": result.output,
            "isError": not result.ok,
        }
    )

# """开启一轮权限检查周期
# 只有权限管理器支持 begin_turn 时才调用
def _begin_permission_turn(permissions: Any | None) -> None:
    """Start a permission turn when the permission manager supports turn hooks."""

    if permissions is not None and hasattr(permissions, "begin_turn"):
        permissions.begin_turn()

# """结束一轮权限检查周期
# 只有权限管理器支持 end_turn 时才调用
def _end_permission_turn(permissions: Any | None) -> None:
    """Finish a permission turn when the permission manager supports turn hooks."""

    if permissions is not None and hasattr(permissions, "end_turn"):
        permissions.end_turn()


def _compact_messages_if_needed(
    current_messages: list[ChatMessage],
    context_manager: ContextManager | None,
    on_progress_message: Callable[[str], None] | None,
) -> list[ChatMessage]:
    """在模型继续思考前，必要时压缩上下文消息。"""

    if context_manager is None:
        return current_messages

    context_manager.set_messages(current_messages)
    if not context_manager.should_auto_compact():
        return current_messages

    compacted = context_manager.compact_messages()
    if on_progress_message is not None:
        on_progress_message("Context manager compacted older messages to stay within the model limit.")
    return list(compacted)


# ===================== 【核心】AI智能体主循环 =====================
def run_agent_turn(
    *,
    model: ModelAdapter,
    tools: ToolRegistry,
    messages: list[ChatMessage],
    cwd: str,
    permissions: Any | None = None,
    max_steps: int = 50,
    on_tool_start: Callable[[str, dict[str, Any]], None] | None = None,
    on_tool_result: Callable[[str, str, bool], None] | None = None,
    on_assistant_message: Callable[[str], None] | None = None,
    on_progress_message: Callable[[str], None] | None = None,
    on_assistant_stream_chunk: Callable[[str], None] | None = None,
    context_manager: ContextManager | None = None,
    runtime: dict[str, Any] | None = None,
) -> list[ChatMessage]:
    """Run one complete agent turn until final assistant output, user pause, or limit."""

    # -------------------------- 【1】初始化变量 --------------------------
    # 复制一份消息列表，避免修改外部原始数据，所有新增消息都存在这里
    current_messages = list(messages)
    # 标记：本轮是否执行过工具（用于空响应时给不同提示）
    saw_tool_result = False
    # 重试计数器：模型返回空内容时，最多重试 2 次，避免卡住
    empty_response_retry_count = 0
    # 重试计数器：模型意外中断思考（max_tokens/pause）时，最多重试 3 次
    recoverable_thinking_retry_count = 0

    _begin_permission_turn(permissions)
    try:
        # -------------------------- 【3】进入核心思考循环 --------------------------
        for _step_index in range(max_steps):
            current_messages = _compact_messages_if_needed(
                current_messages,
                context_manager,
                on_progress_message,
            )
            next_step = model.next(current_messages, on_stream_chunk=on_assistant_stream_chunk)

            if next_step.type == "assistant":
                # Progress-only assistant messages are recorded, then we nudge the
                # model to continue instead of ending the turn early.
                if _is_progress_step(next_step) and not _is_empty_assistant_response(next_step.content):
                    _emit_progress(current_messages, next_step.content, on_progress_message)
                    current_messages.append({"role": "user", "content": NUDGE_CONTINUE})
                    continue
                
                if (
                    _is_recoverable_thinking_stop(next_step)
                    and recoverable_thinking_retry_count < 3
                ):
                    recoverable_thinking_retry_count += 1
                    stop_reason = next_step.diagnostics.stopReason if next_step.diagnostics else None
                    progress_content = (
                        "Model returned pause_turn; requesting the next step."
                        if stop_reason == "pause_turn"
                        else "Model hit max_tokens during thinking; requesting the next step."
                    )
                    _emit_progress(current_messages, progress_content, on_progress_message)
                    current_messages.append(
                        {
                            "role": "user",
                            "content": (
                                RESUME_AFTER_PAUSE
                                if stop_reason == "pause_turn"
                                else RESUME_AFTER_MAX_TOKENS
                            ),
                        }
                    )
                    continue
                
                if _is_empty_assistant_response(next_step.content) and empty_response_retry_count < 2:
                    empty_response_retry_count += 1
                    current_messages.append(
                        {
                            "role": "user",
                            "content": (
                                NUDGE_AFTER_EMPTY_RESPONSE
                                if saw_tool_result
                                else NUDGE_AFTER_EMPTY_NO_TOOLS
                            ),
                        }
                    )
                    continue
                    
                if _is_empty_assistant_response(next_step.content):
                    fallback = (
                        "Model returned an empty response after tool execution and the turn was stopped."
                        if saw_tool_result
                        else "Model returned an empty response and the turn was stopped."
                    )
                    if on_assistant_message is not None:
                        on_assistant_message(fallback)
                    current_messages.append({"role": "assistant", "content": fallback})
                    return current_messages

                if on_assistant_message is not None:
                    on_assistant_message(next_step.content)
                current_messages.append({"role": "assistant", "content": next_step.content})
                return current_messages

            # tool_calls 分支：先回写这一步的可见文本，再执行工具。
            if next_step.content:
                if _is_progress_step(next_step):
                    _emit_progress(current_messages, next_step.content, on_progress_message)
                else:
                    if on_assistant_message is not None:
                        on_assistant_message(next_step.content)
                    current_messages.append({"role": "assistant", "content": next_step.content})

            if not next_step.calls:
                if _is_progress_step(next_step) and next_step.content:
                    current_messages.append({"role": "user", "content": NUDGE_CONTINUE})
                    continue
                return current_messages

            for call in next_step.calls:
                if on_tool_start is not None:
                    on_tool_start(call["toolName"], call["input"])

                result = _execute_tool_call(call, tools, cwd, permissions, runtime)

                if on_tool_result is not None:
                    on_tool_result(call["toolName"], result.output, not result.ok)

                saw_tool_result = True

                _append_tool_messages(current_messages, call, result)

                # ask_user 之类的工具会在这里中断本轮，让用户先回答。
                if result.awaitUser:
                    if on_assistant_message is not None:
                        on_assistant_message(result.output)
                    current_messages.append({"role": "assistant", "content": result.output})
                    return current_messages

        fallback = "Reached the maximum tool step limit for this turn."
        if on_assistant_message is not None:
            on_assistant_message(fallback)
        current_messages.append({"role": "assistant", "content": fallback})
        return current_messages
    finally:
        _end_permission_turn(permissions)
