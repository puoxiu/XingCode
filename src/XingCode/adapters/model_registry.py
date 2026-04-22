from __future__ import annotations

from enum import Enum
from typing import Any

from XingCode.adapters.anthropic_adapter import AnthropicModelAdapter
from XingCode.adapters.mock_model import MockModelAdapter
from XingCode.adapters.openai_adapter import OpenAIModelAdapter


class Provider(str, Enum):
    """定义当前阶段支持的 AI 服务提供商。"""

    MOCK = "mock"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


def _coerce_provider(value: Any) -> Provider | None:
    """把自由输入的 provider 提示归一成 Provider 枚举。"""
    # 例如输入参数 provider="openai3" 或 "openai" 都会被归一化为 Provider.OPENAI, 返回 Provider.OPENAI
    text = str(value).strip().lower()
    if not text:
        return None
    try:
        return Provider(text)
    except ValueError:
        return None


def detect_provider(model: str, runtime: dict[str, Any] | None = None) -> Provider:
    """根据 runtime 和模型名推断应该走哪个 provider。"""

    # 一般情况下 直接根据 runtime 中的 provider 提示判断 provider即可
    # 如果 runtime 中没有 provider 提示，根据模型名和 baseUrl 推断 provider
    runtime = runtime or {}
    provider_hint = _coerce_provider(runtime.get("provider"))
    if provider_hint is not None:
        return provider_hint

    normalized_model = model.lower().strip()
    if normalized_model in {"mock", "mock-model"} or runtime.get("modelMode") == "mock":
        return Provider.MOCK
    if normalized_model.startswith(("gpt-", "chatgpt-", "o1", "o3", "openai/")):
        return Provider.OPENAI

    base_url = str(runtime.get("baseUrl", "")).lower()
    if "openai" in base_url:
        return Provider.OPENAI
    if "anthropic" in base_url:
        return Provider.ANTHROPIC

    return Provider.ANTHROPIC


def create_model_adapter(
    model: str | None,
    tools: Any,
    runtime: dict[str, Any] | None = None,
    force_mock: bool = False,
) -> Any:
    """按 runtime 和模型名创建对应的模型适配器实例。"""

    runtime = dict(runtime or {})
    resolved_model = str(model or runtime.get("model", "")).strip()
    if not resolved_model and not force_mock:
        raise RuntimeError("Model name is required to create a model adapter.")

    provider = Provider.MOCK if force_mock else detect_provider(resolved_model, runtime)
    if provider is Provider.MOCK:
        return MockModelAdapter()

    enriched_runtime = dict(runtime)
    enriched_runtime["model"] = resolved_model
    enriched_runtime["provider"] = provider.value

    if provider is Provider.OPENAI:
        return OpenAIModelAdapter(enriched_runtime, tools)

    return AnthropicModelAdapter(enriched_runtime, tools)
