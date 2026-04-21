from __future__ import annotations

import json
from typing import Any

from XingCode.adapters.openai_adapter import OpenAIModelAdapter
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
                name="run_command",
                description="Run command",
                input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
                validator=lambda value: value,
                run=lambda _input, _context: ToolResult(ok=True, output="unused"),
            )
        ]
    )


def test_openai_adapter_builds_request_and_parses_tool_calls(monkeypatch) -> None:
    """OpenAI 兼容适配器应正确构造请求体，并把 tool_calls 解析回内部调用。"""

    captured: dict[str, Any] = {}
    payload = {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "content": "<progress>thinking</progress>",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "run_command",
                                "arguments": "{\"command\": \"pwd\"}",
                            },
                        }
                    ],
                },
            }
        ]
    }

    def fake_urlopen(request, timeout=60):  # noqa: ANN001
        captured["url"] = request.full_url
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return DummyResponse(payload)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    adapter = OpenAIModelAdapter(
        {"model": "gpt-4o", "baseUrl": "https://api.openai.com", "apiKey": "test-key"},
        _tool_registry(),
    )
    step = adapter.next(
        [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "run pwd"},
            {"role": "assistant_tool_call", "toolUseId": "old-call", "toolName": "run_command", "input": {"command": "ls"}},
            {"role": "tool_result", "toolUseId": "old-call", "toolName": "run_command", "content": "old output", "isError": False},
        ]
    )

    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["timeout"] == 60
    assert captured["headers"]["authorization"] == "Bearer test-key"
    assert captured["body"]["messages"][0] == {"role": "system", "content": "sys"}
    assert captured["body"]["tools"][0]["function"]["name"] == "run_command"
    assert any(message.get("tool_calls") for message in captured["body"]["messages"] if message["role"] == "assistant")
    assert any(message["role"] == "tool" for message in captured["body"]["messages"])

    assert step.type == "tool_calls"
    assert step.content == "thinking"
    assert step.contentKind == "progress"
    assert step.calls[0]["toolName"] == "run_command"
    assert step.calls[0]["input"] == {"command": "pwd"}


def test_openai_adapter_parses_final_text(monkeypatch) -> None:
    """OpenAI 兼容适配器应把最终文本回复解析成 assistant step。"""

    payload = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": "<final>done</final>"},
            }
        ]
    }
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=60: DummyResponse(payload),
    )

    adapter = OpenAIModelAdapter(
        {"model": "gpt-4o", "baseUrl": "https://api.openai.com", "apiKey": "test-key"},
        _tool_registry(),
    )
    step = adapter.next([{"role": "system", "content": "sys"}, {"role": "user", "content": "finish"}])

    assert step.type == "assistant"
    assert step.content == "done"
    assert step.kind == "final"
