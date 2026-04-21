from __future__ import annotations

import json
from typing import Any

from XingCode.adapters.anthropic_adapter import AnthropicModelAdapter
from XingCode.core.tooling import ToolDefinition, ToolRegistry, ToolResult


class DummyResponse:
    """最小假响应对象：模拟 urllib 返回的 HTTP 响应。"""

    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._payload = payload
        self.status = status

    def read(self) -> bytes:
        """把预设 JSON 负载编码成字节串。"""

        return json.dumps(self._payload).encode("utf-8")


def _tool_registry() -> ToolRegistry:
    """构造一个最小工具表，供适配器序列化 tools 字段。"""

    return ToolRegistry(
        [
            ToolDefinition(
                name="read_file",
                description="Read file",
                input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
                validator=lambda value: value,
                run=lambda _input, _context: ToolResult(ok=True, output="unused"),
            )
        ]
    )


def test_anthropic_adapter_builds_request_and_parses_tool_use(monkeypatch) -> None:
    """Anthropic 适配器应正确构造请求体，并把 tool_use 解析回 tool_calls。"""

    captured: dict[str, Any] = {}
    payload = {
        "stop_reason": "tool_use",
        "content": [
            {"type": "text", "text": "<progress>thinking</progress>"},
            {"type": "tool_use", "id": "tool-1", "name": "read_file", "input": {"path": "README.md"}},
        ],
    }

    def fake_urlopen(request, timeout=60):  # noqa: ANN001
        captured["url"] = request.full_url
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return DummyResponse(payload)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    adapter = AnthropicModelAdapter(
        {"model": "claude-sonnet-4-20250514", "baseUrl": "https://api.anthropic.com", "apiKey": "test-key"},
        _tool_registry(),
    )
    step = adapter.next(
        [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "read me"},
            {"role": "assistant_tool_call", "toolUseId": "old-tool", "toolName": "read_file", "input": {"path": "OLD.md"}},
            {"role": "tool_result", "toolUseId": "old-tool", "toolName": "read_file", "content": "FILE: OLD.md", "isError": False},
        ]
    )

    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["timeout"] == 60
    assert captured["headers"]["x-api-key"] == "test-key"
    assert captured["body"]["system"] == "sys"
    assert captured["body"]["tools"][0]["name"] == "read_file"
    flat_blocks = [block for message in captured["body"]["messages"] for block in message["content"]]
    assert any(block.get("type") == "tool_use" for block in flat_blocks)
    assert any(block.get("type") == "tool_result" for block in flat_blocks)

    assert step.type == "tool_calls"
    assert step.content == "thinking"
    assert step.contentKind == "progress"
    assert step.calls[0]["toolName"] == "read_file"
    assert step.calls[0]["input"] == {"path": "README.md"}


def test_anthropic_adapter_parses_final_text(monkeypatch) -> None:
    """Anthropic 适配器应把最终文本回复解析成 assistant step。"""

    payload = {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": "<final>done</final>"}],
    }
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=60: DummyResponse(payload),
    )

    adapter = AnthropicModelAdapter(
        {"model": "claude-sonnet-4-20250514", "baseUrl": "https://api.anthropic.com", "apiKey": "test-key"},
        _tool_registry(),
    )
    step = adapter.next([{"role": "system", "content": "sys"}, {"role": "user", "content": "finish"}])

    assert step.type == "assistant"
    assert step.content == "done"
    assert step.kind == "final"
