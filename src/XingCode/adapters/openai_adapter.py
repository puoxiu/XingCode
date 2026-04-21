from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable

from XingCode.core.tooling import ToolRegistry
from XingCode.core.types import AgentStep, ChatMessage, StepDiagnostics

REQUEST_TIMEOUT_SECONDS = 60


def _parse_assistant_text(content: str) -> tuple[str, str | None]:
    """解析 assistant 文本中的 progress/final 标记。"""

    trimmed = content.strip()
    if not trimmed:
        return "", None

    markers = [
        ("<final>", "final", "</final>"),
        ("[FINAL]", "final", None),
        ("<progress>", "progress", "</progress>"),
        ("[PROGRESS]", "progress", None),
    ]
    for prefix, kind, closing_tag in markers:
        if trimmed.startswith(prefix):
            raw = trimmed[len(prefix) :].strip()
            if closing_tag:
                raw = raw.replace(closing_tag, "").strip()
            return raw, kind
    return trimmed, None


def _status_code(response: Any) -> int:
    """兼容正常响应和 HTTPError，统一取出状态码。"""

    return int(getattr(response, "status", getattr(response, "code", 200)))


def _read_json_response(response: Any) -> Any:
    """读取 HTTP 响应体，并尽量解析成 JSON。"""

    text = response.read().decode("utf-8")
    if not text.strip():
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OpenAI-compatible endpoint returned invalid JSON: {text[:200]}") from exc


def _extract_error_message(data: Any, status: int) -> str:
    """从 OpenAI 兼容接口的错误响应中提取错误信息。"""

    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"]
    return f"OpenAI-compatible API error: {status}"


def _assistant_text_for_provider(message: ChatMessage) -> str:
    """把内部 assistant 消息转换成 OpenAI 可理解的文本内容。"""

    if message["role"] == "assistant_progress":
        return f"<progress>\n{message['content']}\n</progress>"
    return message["content"]


def _to_openai_messages(messages: list[ChatMessage]) -> tuple[str, list[dict[str, Any]]]:
    """把内部消息协议转换成 OpenAI Chat Completions 格式。"""

    system_parts: list[str] = []
    converted: list[dict[str, Any]] = []

    for message in messages:
        role = message["role"]
        if role == "system":
            system_parts.append(message["content"])
            continue
        if role == "user":
            converted.append({"role": "user", "content": message["content"]})
            continue
        if role in {"assistant", "assistant_progress"}:
            converted.append(
                {
                    "role": "assistant",
                    "content": _assistant_text_for_provider(message),
                }
            )
            continue
        if role == "assistant_tool_call":
            converted.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": message["toolUseId"],
                            "type": "function",
                            "function": {
                                "name": message["toolName"],
                                "arguments": json.dumps(message["input"]),
                            },
                        }
                    ],
                }
            )
            continue

        # tool_result 在 OpenAI 中用 role=tool 回写，关联 tool_call_id。
        converted.append(
            {
                "role": "tool",
                "tool_call_id": message["toolUseId"],
                "content": message.get("content", ""),
            }
        )

    return "\n\n".join(system_parts), converted


def _serialize_tools(tools: ToolRegistry) -> list[dict[str, Any]]:
    """把内部工具定义转换成 OpenAI function calling 工具格式。"""

    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }
        for tool in tools.list()
    ]


def _normalize_openai_content(content: Any) -> str:
    """兼容字符串或结构化内容列表，统一提取可读文本。"""

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
                text_parts.append(part["text"])
        return "\n".join(text_parts)
    return ""


class OpenAIModelAdapter:
    """真实 OpenAI 兼容适配器：负责非 streaming 请求和响应解析。"""

    def __init__(self, runtime: dict[str, Any], tools: ToolRegistry) -> None:
        # 保存 runtime 和工具注册表，后续每次 next() 直接复用。
        self.runtime = dict(runtime)
        self.tools = tools

    def _build_request_body(self, messages: list[ChatMessage]) -> dict[str, Any]:
        """构造 OpenAI Chat Completions 请求体。"""

        system_message, converted_messages = _to_openai_messages(messages)
        if system_message:
            converted_messages.insert(0, {"role": "system", "content": system_message})

        request_body: dict[str, Any] = {
            "model": self.runtime["model"],
            "messages": converted_messages,
        }
        serialized_tools = _serialize_tools(self.tools)
        if serialized_tools:
            request_body["tools"] = serialized_tools

        return request_body

    def next(
        self,
        messages: list[ChatMessage],
        on_stream_chunk: Callable[[str], None] | None = None,
    ) -> AgentStep:
        """向 OpenAI 兼容接口发起一次非 streaming 请求，并转换成内部 AgentStep。"""

        request_body = self._build_request_body(messages)
        request = urllib.request.Request(
            url=self.runtime["baseUrl"].rstrip("/") + "/v1/chat/completions",
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "Authorization": f"Bearer {self.runtime.get('apiKey') or ''}",
            },
            method="POST",
        )

        try:
            response = urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS)  # noqa: S310
        except urllib.error.HTTPError as error:
            response = error
        except urllib.error.URLError as error:
            raise RuntimeError(f"OpenAI-compatible request failed: {error.reason}") from error

        data = _read_json_response(response)
        status = _status_code(response)
        if status >= 400:
            raise RuntimeError(_extract_error_message(data, status))

        choices = data.get("choices", []) if isinstance(data, dict) else []
        if not choices:
            return AgentStep(type="assistant", content="")

        choice = choices[0]
        message = choice.get("message", {})
        text_content = _normalize_openai_content(message.get("content"))
        tool_calls_raw = message.get("tool_calls", [])

        tool_calls: list[dict[str, Any]] = []
        for tool_call in tool_calls_raw if isinstance(tool_calls_raw, list) else []:
            function_block = tool_call.get("function", {})
            arguments = function_block.get("arguments", "{}")
            try:
                parsed_input = json.loads(arguments)
            except json.JSONDecodeError:
                parsed_input = {}
            tool_calls.append(
                {
                    "id": tool_call.get("id", ""),
                    "toolName": function_block.get("name", ""),
                    "input": parsed_input if isinstance(parsed_input, dict) else {},
                }
            )

        parsed_text, kind = _parse_assistant_text(text_content.strip())
        if on_stream_chunk is not None and parsed_text:
            # Phase 8 只实现非 streaming；如果上层传了 callback，这里用一次性回调
            # 保证接口兼容，但不模拟真正的流式分块。
            on_stream_chunk(parsed_text)

        diagnostics = StepDiagnostics(
            stopReason=choice.get("finish_reason"),
            blockTypes=["tool_calls"] if tool_calls else (["text"] if text_content else []),
            ignoredBlockTypes=[],
        )

        if tool_calls:
            return AgentStep(
                type="tool_calls",
                calls=tool_calls,
                content=parsed_text,
                contentKind="progress" if kind == "progress" else None,
                diagnostics=diagnostics,
            )
        return AgentStep(
            type="assistant",
            content=parsed_text,
            kind=kind,
            diagnostics=diagnostics,
        )


__all__ = ["OpenAIModelAdapter"]
