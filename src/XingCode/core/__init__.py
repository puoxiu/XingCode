"""Core protocols and execution primitives for XingCode."""

from .agent_loop import run_agent_turn
from .context_manager import ContextManager, ContextStats, estimate_message_tokens, estimate_messages_tokens, estimate_tokens
from .prompt import build_system_prompt
from .prompt_pipeline import PromptPipeline, PromptSection, SYSTEM_PROMPT_DYNAMIC_BOUNDARY
from .tooling import ToolContext, ToolDefinition, ToolRegistry, ToolResult
from .types import AgentStep, ChatMessage, ModelAdapter, StepDiagnostics, ToolCall

__all__ = [
    "AgentStep",
    "ChatMessage",
    "ContextManager",
    "ContextStats",
    "ModelAdapter",
    "PromptPipeline",
    "PromptSection",
    "SYSTEM_PROMPT_DYNAMIC_BOUNDARY",
    "StepDiagnostics",
    "ToolCall",
    "ToolContext",
    "ToolDefinition",
    "ToolRegistry",
    "ToolResult",
    "build_system_prompt",
    "estimate_message_tokens",
    "estimate_messages_tokens",
    "estimate_tokens",
    "run_agent_turn",
]
