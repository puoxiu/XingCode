"""Core protocols and execution primitives for XingCode."""

from .agent_loop import run_agent_turn
from .prompt import build_system_prompt
from .tooling import ToolContext, ToolDefinition, ToolRegistry, ToolResult
from .types import AgentStep, ChatMessage, ModelAdapter, StepDiagnostics, ToolCall

__all__ = [
    "AgentStep",
    "ChatMessage",
    "ModelAdapter",
    "StepDiagnostics",
    "ToolCall",
    "ToolContext",
    "ToolDefinition",
    "ToolRegistry",
    "ToolResult",
    "build_system_prompt",
    "run_agent_turn",
]
