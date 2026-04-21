from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from importlib import import_module
from typing import Any

from XingCode.adapters.mock_model import MockModelAdapter


class Provider(str, Enum):
    """
    【核心枚举】定义当前阶段支持的AI服务提供商
    设计：仅包含基础必需的提供商类型，真实HTTP适配器将在后续阶段实现
    继承str+Enum：让枚举值同时具备字符串特性，方便比较/使用
    """
    MOCK = "mock"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class AnthropicModelAdapter:
    """
    Anthropic模型适配器【占位类】
    作用：当前阶段（Phase7）仅用于存储配置和路由参数，不实现真实API调用
    真实的HTTP请求逻辑将在 Phase8 完整实现
    """

    def __init__(self, runtime: dict[str, Any], tools: Any) -> None:
        self.runtime = dict(runtime)
        self.tools = tools

    def next(
        self,
        messages: list[dict[str, Any]],
        on_stream_chunk: Callable[[str], None] | None = None,
    ) -> Any:
        """Defer real Anthropic API work to Phase 8."""

        _ = (messages, on_stream_chunk)
        raise NotImplementedError("AnthropicModelAdapter will be implemented in Phase 8.")


class OpenAIModelAdapter:
    """Phase 7 placeholder that only stores routing inputs until Phase 8."""

    def __init__(self, runtime: dict[str, Any], tools: Any) -> None:
        self.runtime = dict(runtime)
        self.tools = tools

    def next(
        self,
        messages: list[dict[str, Any]],
        on_stream_chunk: Callable[[str], None] | None = None,
    ) -> Any:
        """Defer real OpenAI-compatible API work to Phase 8."""

        _ = (messages, on_stream_chunk)
        raise NotImplementedError("OpenAIModelAdapter will be implemented in Phase 8.")


def _coerce_provider(value: Any) -> Provider | None:
    """Convert a free-form provider hint into the local Provider enum."""

    text = str(value).strip().lower()
    if not text:
        return None
    try:
        return Provider(text)
    except ValueError:
        return None


def detect_provider(model: str, runtime: dict[str, Any] | None = None) -> Provider:
    """Detect which provider should serve the current model."""

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


def _load_adapter_class(
    module_name: str,
    class_name: str,
    fallback: type[Any],
) -> type[Any]:
    """Load the real adapter class when available, otherwise keep the Phase 7 shell."""

    try:
        module = import_module(module_name)
    except ModuleNotFoundError:
        return fallback
    return getattr(module, class_name, fallback)


def create_model_adapter(
    model: str | None,
    tools: Any,
    runtime: dict[str, Any] | None = None,
    force_mock: bool = False,
) -> Any:
    """Create the minimal model adapter selected by runtime and model name."""

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

    # 在真实 adapter 文件还未创建之前，先返回同名占位类，确保配置层和
    # 分发层能先联调起来；Phase 8 再把 next() 的真实请求逻辑接上。
    if provider is Provider.OPENAI:
        adapter_class = _load_adapter_class(
            "XingCode.adapters.openai_adapter",
            "OpenAIModelAdapter",
            OpenAIModelAdapter,
        )
        return adapter_class(enriched_runtime, tools)

    adapter_class = _load_adapter_class(
        "XingCode.adapters.anthropic_adapter",
        "AnthropicModelAdapter",
        AnthropicModelAdapter,
    )
    return adapter_class(enriched_runtime, tools)
