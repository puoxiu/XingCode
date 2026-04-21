from XingCode.adapters.mock_model import MockModelAdapter
from XingCode.adapters.model_registry import (
    AnthropicModelAdapter,
    OpenAIModelAdapter,
    Provider,
    create_model_adapter,
    detect_provider,
)
from XingCode.core.tooling import ToolRegistry


def test_detect_provider_returns_mock_for_mock_model() -> None:
    """
    【测试】Mock模型名称应始终路由到Mock提供程序
    验证：输入"mock"，返回Provider.MOCK
    """
    assert detect_provider("mock") is Provider.MOCK


def test_detect_provider_returns_openai_for_gpt_models() -> None:
    """GPT and reasoning model names should route to the OpenAI family."""

    assert detect_provider("gpt-4o") is Provider.OPENAI
    assert detect_provider("o3-mini") is Provider.OPENAI


def test_detect_provider_returns_anthropic_for_claude_models() -> None:
    """Claude-style model names should route to Anthropic by default."""

    assert detect_provider("claude-sonnet-4-20250514") is Provider.ANTHROPIC


def test_detect_provider_prefers_runtime_provider_hint() -> None:
    """An explicit runtime provider hint should override name-based detection."""

    provider = detect_provider("claude-sonnet-4-20250514", {"provider": "openai"})

    assert provider is Provider.OPENAI


def test_create_model_adapter_returns_mock_adapter_when_forced() -> None:
    """force_mock should bypass provider detection and always return the mock adapter."""

    adapter = create_model_adapter("gpt-4o", ToolRegistry([]), {"provider": "openai"}, force_mock=True)

    assert isinstance(adapter, MockModelAdapter)


def test_create_model_adapter_returns_openai_adapter_placeholder() -> None:
    """OpenAI models should currently route to the Phase 7 OpenAI adapter shell."""

    registry = ToolRegistry([])
    runtime = {"baseUrl": "https://api.openai.com", "apiKey": "key"}

    adapter = create_model_adapter("gpt-4o", registry, runtime)

    assert isinstance(adapter, OpenAIModelAdapter)
    assert adapter.tools is registry
    assert adapter.runtime["model"] == "gpt-4o"
    assert adapter.runtime["provider"] == "openai"


def test_create_model_adapter_returns_anthropic_adapter_placeholder() -> None:
    """Claude models should currently route to the Phase 7 Anthropic adapter shell."""

    registry = ToolRegistry([])
    runtime = {"baseUrl": "https://api.anthropic.com", "apiKey": "key"}

    adapter = create_model_adapter("claude-sonnet-4-20250514", registry, runtime)

    assert isinstance(adapter, AnthropicModelAdapter)
    assert adapter.tools is registry
    assert adapter.runtime["model"] == "claude-sonnet-4-20250514"
    assert adapter.runtime["provider"] == "anthropic"


def test_create_model_adapter_uses_runtime_model_when_argument_is_missing() -> None:
    """The runtime dict should be enough to create an adapter when model arg is omitted."""

    adapter = create_model_adapter(
        None,
        ToolRegistry([]),
        {"model": "mock", "provider": "mock"},
    )

    assert isinstance(adapter, MockModelAdapter)


def test_create_model_adapter_raises_when_model_is_missing() -> None:
    """Adapter creation should fail fast when neither arg nor runtime provides a model."""

    try:
        create_model_adapter(None, ToolRegistry([]), {})
    except RuntimeError as exc:
        assert "Model name is required" in str(exc)
    else:
        raise AssertionError("Expected create_model_adapter() to raise RuntimeError")
