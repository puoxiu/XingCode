from __future__ import annotations

from typing import Any

from XingCode.core.agent_loop import run_agent_turn
from XingCode.core.tooling import ToolDefinition, ToolRegistry, ToolResult
from XingCode.core.types import AgentStep, ChatMessage, ModelAdapter, StepDiagnostics

# ===================== 脚本化模型：用于精准测试的假AI =====================
#     确定性测试模型（测试专用）
#     作用：不随机生成内容，**固定返回预设的步骤列表**，让测试完全可控
#     继承自 ModelAdapter（模型适配器标准接口）
class ScriptedModel(ModelAdapter):
    """Deterministic test double that returns a fixed sequence of agent steps."""

    def __init__(self, steps: list[AgentStep]) -> None:
        self._steps = steps
        self.calls = 0

    def next(self, messages: list[ChatMessage], on_stream_chunk=None) -> AgentStep:
        """Return the next scripted step so tests can control the agent loop."""

        _ = (messages, on_stream_chunk)
        step = self._steps[self.calls]
        self.calls += 1
        return step


# ===================== 记录式权限管理器：测试生命周期钩子 =====================
#     测试用权限管理器
#     作用：记录权限的 begin/end 事件，验证AI回合的生命周期钩子正常调用
class RecordingPermissions:
    """Small permission stub used to verify turn lifecycle hooks are called."""

    def __init__(self) -> None:
        self.events: list[str] = []

    def begin_turn(self) -> None:
        """Record the start of one agent turn."""

        self.events.append("begin")

    def end_turn(self) -> None:
        """Record the end of one agent turn."""

        self.events.append("end")

#     创建微型测试工具注册表（3个测试工具）
    # 1. echo：原样返回文本
    # 2. upper：文本转大写
    # 3. pause：暂停并等待用户输入
def _make_registry() -> ToolRegistry:
    """Create a tiny registry with echo, upper, and pause test tools."""

    def run_echo(input_data: dict[str, Any], _context) -> ToolResult:
        return ToolResult(ok=True, output=f"echo:{input_data['text']}")

    def run_upper(input_data: dict[str, Any], _context) -> ToolResult:
        return ToolResult(ok=True, output=str(input_data["text"]).upper())

    def run_pause(input_data: dict[str, Any], _context) -> ToolResult:
        return ToolResult(ok=True, output=input_data["question"], awaitUser=True)

    return ToolRegistry(
        [
            ToolDefinition(
                name="echo",
                description="Echo back test text.",
                input_schema={"type": "object"},
                validator=lambda value: value,
                run=run_echo,
            ),
            ToolDefinition(
                name="upper",
                description="Uppercase test text.",
                input_schema={"type": "object"},
                validator=lambda value: value,
                run=run_upper,
            ),
            ToolDefinition(
                name="pause",
                description="Pause the turn and ask the user something.",
                input_schema={"type": "object"},
                validator=lambda value: value,
                run=run_pause,
            ),
        ]
    )

# ===================== 测试用例：全覆盖验证AI主循环 =====================
def test_agent_turn_returns_assistant_message_directly() -> None:
    """A plain assistant response should end the turn immediately."""

    model = ScriptedModel([AgentStep(type="assistant", content="done")])

    messages = run_agent_turn(
        model=model,
        tools=ToolRegistry([]),
        messages=[{"role": "system", "content": "sys"}],
        cwd=".",
    )

    assert messages[-1] == {"role": "assistant", "content": "done"}


def test_agent_turn_executes_tool_and_returns_assistant() -> None:
    """The loop should execute one tool, write back result messages, then continue."""

    model = ScriptedModel(
        [
            AgentStep(
                type="tool_calls",
                calls=[{"id": "1", "toolName": "echo", "input": {"text": "hi"}}],
            ),
            AgentStep(type="assistant", content="done"),
        ]
    )

    messages = run_agent_turn(
        model=model,
        tools=_make_registry(),
        messages=[{"role": "system", "content": "sys"}],
        cwd=".",
    )

    assert messages[-1] == {"role": "assistant", "content": "done"}
    assert any(message["role"] == "assistant_tool_call" for message in messages)
    assert any(message["role"] == "tool_result" for message in messages)


def test_agent_turn_executes_multiple_tools_in_order() -> None:
    """Multiple tool calls should be executed serially and written back in order."""

    model = ScriptedModel(
        [
            AgentStep(
                type="tool_calls",
                calls=[
                    {"id": "1", "toolName": "echo", "input": {"text": "hi"}},
                    {"id": "2", "toolName": "upper", "input": {"text": "there"}},
                ],
            ),
            AgentStep(type="assistant", content="done"),
        ]
    )

    messages = run_agent_turn(
        model=model,
        tools=_make_registry(),
        messages=[{"role": "system", "content": "sys"}],
        cwd=".",
    )

    tool_messages = [message for message in messages if message["role"] in {"assistant_tool_call", "tool_result"}]

    assert tool_messages == [
        {"role": "assistant_tool_call", "toolUseId": "1", "toolName": "echo", "input": {"text": "hi"}},
        {"role": "tool_result", "toolUseId": "1", "toolName": "echo", "content": "echo:hi", "isError": False},
        {"role": "assistant_tool_call", "toolUseId": "2", "toolName": "upper", "input": {"text": "there"}},
        {"role": "tool_result", "toolUseId": "2", "toolName": "upper", "content": "THERE", "isError": False},
    ]


def test_agent_turn_emits_callbacks() -> None:
    """Progress, tool, and assistant callbacks should all fire on the right events."""

    events: list[tuple[str, str]] = []
    model = ScriptedModel(
        [
            AgentStep(
                type="tool_calls",
                content="working",
                contentKind="progress",
                calls=[{"id": "1", "toolName": "echo", "input": {"text": "hi"}}],
            ),
            AgentStep(type="assistant", content="done"),
        ]
    )

    run_agent_turn(
        model=model,
        tools=_make_registry(),
        messages=[{"role": "system", "content": "sys"}],
        cwd=".",
        on_tool_start=lambda name, _input: events.append(("start", name)),
        on_tool_result=lambda name, _output, _error: events.append(("result", name)),
        on_assistant_message=lambda content: events.append(("assistant", content)),
        on_progress_message=lambda content: events.append(("progress", content)),
    )

    assert ("progress", "working") in events
    assert ("start", "echo") in events
    assert ("result", "echo") in events
    assert ("assistant", "done") in events


def test_agent_turn_retries_empty_response_then_continues() -> None:
    """One empty assistant response should trigger a retry prompt instead of stopping."""

    model = ScriptedModel(
        [
            AgentStep(type="assistant", content=""),
            AgentStep(type="assistant", content="done"),
        ]
    )

    messages = run_agent_turn(
        model=model,
        tools=ToolRegistry([]),
        messages=[{"role": "system", "content": "sys"}],
        cwd=".",
    )

    assert messages[-1] == {"role": "assistant", "content": "done"}
    assert any(
        message["role"] == "user" and "last response was empty" in message["content"]
        for message in messages
    )


def test_agent_turn_handles_recoverable_pause_turn() -> None:
    """An empty pause_turn thinking stop should be retried instead of failing the turn."""

    model = ScriptedModel(
        [
            AgentStep(
                type="assistant",
                content="",
                diagnostics=StepDiagnostics(stopReason="pause_turn", ignoredBlockTypes=["thinking"]),
            ),
            AgentStep(type="assistant", content="done"),
        ]
    )
    progress_events: list[str] = []

    messages = run_agent_turn(
        model=model,
        tools=ToolRegistry([]),
        messages=[{"role": "system", "content": "sys"}],
        cwd=".",
        on_progress_message=progress_events.append,
    )

    assert messages[-1] == {"role": "assistant", "content": "done"}
    assert any("pause_turn" in event for event in progress_events)


def test_agent_turn_returns_fallback_after_repeated_empty_responses() -> None:
    """Repeated empty responses should stop with a readable fallback message."""

    model = ScriptedModel(
        [
            AgentStep(type="assistant", content=""),
            AgentStep(type="assistant", content=""),
            AgentStep(type="assistant", content=""),
        ]
    )

    messages = run_agent_turn(
        model=model,
        tools=ToolRegistry([]),
        messages=[{"role": "system", "content": "sys"}],
        cwd=".",
    )

    assert "empty response" in messages[-1]["content"].lower()


def test_agent_turn_stops_when_tool_requests_user_input() -> None:
    """awaitUser=True should stop the turn and surface the question as assistant text."""

    model = ScriptedModel(
        [
            AgentStep(
                type="tool_calls",
                calls=[{"id": "1", "toolName": "pause", "input": {"question": "Which file next?"}}],
            )
        ]
    )

    messages = run_agent_turn(
        model=model,
        tools=_make_registry(),
        messages=[{"role": "system", "content": "sys"}],
        cwd=".",
    )

    assert messages[-1] == {"role": "assistant", "content": "Which file next?"}
    assert messages[-2]["role"] == "tool_result"


def test_agent_turn_respects_max_steps_limit() -> None:
    """The loop should stop with a fallback when it keeps receiving tool calls."""

    model = ScriptedModel(
        [
            AgentStep(
                type="tool_calls",
                calls=[{"id": "1", "toolName": "echo", "input": {"text": "hi"}}],
            )
        ]
    )

    messages = run_agent_turn(
        model=model,
        tools=_make_registry(),
        messages=[{"role": "system", "content": "sys"}],
        cwd=".",
        max_steps=1,
    )

    assert messages[-1] == {
        "role": "assistant",
        "content": "Reached the maximum tool step limit for this turn.",
    }


def test_agent_turn_calls_permission_turn_hooks() -> None:
    """Each agent turn should open and close the permission manager turn scope."""

    permissions = RecordingPermissions()
    model = ScriptedModel([AgentStep(type="assistant", content="done")])

    run_agent_turn(
        model=model,
        tools=ToolRegistry([]),
        messages=[{"role": "system", "content": "sys"}],
        cwd=".",
        permissions=permissions,
    )

    assert permissions.events == ["begin", "end"]
