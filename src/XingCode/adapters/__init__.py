"""Model adapters and routing helpers for XingCode."""

from .anthropic_adapter import AnthropicModelAdapter
from .mock_model import MockModelAdapter
from .openai_adapter import OpenAIModelAdapter
from .model_registry import Provider, create_model_adapter, detect_provider

__all__ = [
    "AnthropicModelAdapter",
    "MockModelAdapter",
    "OpenAIModelAdapter",
    "Provider",
    "create_model_adapter",
    "detect_provider",
]
