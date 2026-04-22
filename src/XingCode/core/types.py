from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Protocol, TypedDict


class ChatMessage(TypedDict, total=False):
    """Internal message protocol shared by the agent loop and model adapters."""

    role: Literal[
        "system",
        "user",
        "assistant",
        "assistant_progress",
        "assistant_tool_call",
        "tool_result",
    ]
    content: str
    toolUseId: str
    toolName: str
    input: Any
    isError: bool


class ToolCall(TypedDict):
    """A single tool invocation requested by the model."""

    id: str
    toolName: str
    input: Any


@dataclass(slots=True)
class StepDiagnostics:
    """Extra metadata about why a model step ended."""

    stopReason: str | None = None
    blockTypes: list[str] = field(default_factory=list)
    ignoredBlockTypes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AgentStep:
    """Normalized model output consumed by the agent loop."""

    type: Literal["assistant", "tool_calls"]
    content: str = ""
    kind: Literal["final", "progress"] | None = None
    calls: list[ToolCall] = field(default_factory=list)
    contentKind: Literal["progress"] | None = None
    diagnostics: StepDiagnostics | None = None


class ModelAdapter(Protocol):
    """Protocol implemented by mock and real model adapters."""
    # 模型适配器协议，定义了模型适配器必须实现的方法
    def next(
        self,
        messages: list[ChatMessage],
        on_stream_chunk: Callable[[str], None] | None = None,
    ) -> AgentStep: ...
