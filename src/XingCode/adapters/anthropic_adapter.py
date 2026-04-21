from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable

from XingCode.core.tooling import ToolRegistry
from XingCode.core.types import AgentStep, ChatMessage, StepDiagnostics

ANTHROPIC_VERSION = "2023-06-01"
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
        raise RuntimeError(f"Anthropic returned invalid JSON: {text[:200]}") from exc


def _extract_error_message(data: Any, status: int) -> str:
    """从 Anthropic 错误响应中提取人类可读的错误信息。"""

    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"]
    return f"Anthropic API error: {status}"


def _to_text_block(text: str) -> dict[str, str]:
    """把普通文本包装成 Anthropic 的 text block。"""

    return {"type": "text", "text": text}


def _assistant_text_for_provider(message: ChatMessage) -> str:
    """把内部 assistant 消息转换成 Anthropic 可理解的文本内容。"""

    if message["role"] == "assistant_progress":
        return f"<progress>\n{message['content']}\n</progress>"
    return message["content"]


def _append_role_block(messages: list[dict[str, Any]], role: str, block: dict[str, Any]) -> None:
    """按 Anthropic 的消息格式把 block 追加到最后一个同角色消息中。"""

    if messages and messages[-1]["role"] == role:
        messages[-1]["content"].append(block)
        return
    messages.append({"role": role, "content": [block]})


def _to_anthropic_messages(messages: list[ChatMessage]) -> tuple[str, list[dict[str, Any]]]:
    """把内部消息协议转换成 Anthropic Messages API 的消息结构。"""

    system_parts: list[str] = []
    converted: list[dict[str, Any]] = []

    for message in messages:
        role = message["role"]
        if role == "system":
            system_parts.append(message["content"])
            continue
        if role == "user":
            _append_role_block(converted, "user", _to_text_block(message["content"]))
            continue
        if role in {"assistant", "assistant_progress"}:
            _append_role_block(
                converted,
                "assistant",
                _to_text_block(_assistant_text_for_provider(message)),
            )
            continue
        if role == "assistant_tool_call":
            _append_role_block(
                converted,
                "assistant",
                {
                    "type": "tool_use",
                    "id": message["toolUseId"],
                    "name": message["toolName"],
                    "input": message["input"],
                },
            )
            continue

        # tool_result 在 Anthropic 中由 user 角色回传，保持和参考项目一致。
        _append_role_block(
            converted,
            "user",
            {
                "type": "tool_result",
                "tool_use_id": message["toolUseId"],
                "content": message.get("content", ""),
                "is_error": message.get("isError", False),
            },
        )

    return "\n\n".join(system_parts), converted


def _serialize_tools(tools: ToolRegistry) -> list[dict[str, Any]]:
    """把内部工具定义转换成 Anthropic tools 字段。"""

    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
        for tool in tools.list()
    ]


class AnthropicModelAdapter:
    """真实 Anthropic 适配器：负责非 streaming 请求和响应解析。"""

    def __init__(self, runtime: dict[str, Any], tools: ToolRegistry) -> None:
        # 保存 runtime 和工具注册表，后续每次 next() 直接复用。
        self.runtime = dict(runtime)
        self.tools = tools

    def _build_request_body(self, messages: list[ChatMessage]) -> dict[str, Any]:
        """构造 Anthropic `/v1/messages` 请求体。"""

        system_message, converted_messages = _to_anthropic_messages(messages)
        request_body: dict[str, Any] = {
            "model": self.runtime["model"],
            "messages": converted_messages,
        }
        if system_message:
            request_body["system"] = system_message

        serialized_tools = _serialize_tools(self.tools)
        if serialized_tools:
            request_body["tools"] = serialized_tools

        return request_body

    def next(
        self,
        messages: list[ChatMessage],
        on_stream_chunk: Callable[[str], None] | None = None,
    ) -> AgentStep:
        """向 Anthropic 发起一次非 streaming 请求，并转换成内部 AgentStep。"""

        request_body = self._build_request_body(messages)
        request = urllib.request.Request(
            url=self.runtime["baseUrl"].rstrip("/") + "/v1/messages",
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "anthropic-version": ANTHROPIC_VERSION,
                "x-api-key": str(self.runtime.get("apiKey") or ""),
            },
            method="POST",
        )

        try:
            response = urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS)  # noqa: S310
        except urllib.error.HTTPError as error:
            response = error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Anthropic request failed: {error.reason}") from error

        data = _read_json_response(response)
        status = _status_code(response)
        if status >= 400:
            raise RuntimeError(_extract_error_message(data, status))

        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        block_types: list[str] = []
        ignored_block_types: list[str] = []

        for block in data.get("content", []) if isinstance(data, dict) else []:
            block_type = block.get("type")
            block_types.append(str(block_type))

            if block_type == "text" and isinstance(block.get("text"), str):
                text_parts.append(block["text"])
                continue
            if block_type == "tool_use" and isinstance(block.get("id"), str) and isinstance(block.get("name"), str):
                tool_calls.append(
                    {
                        "id": block["id"],
                        "toolName": block["name"],
                        "input": block.get("input") if isinstance(block.get("input"), dict) else {},
                    }
                )
                continue

            ignored_block_types.append(str(block_type))

        parsed_text, kind = _parse_assistant_text("\n".join(text_parts).strip())
        if on_stream_chunk is not None and parsed_text:
            # Phase 8 只实现非 streaming；如果上层传了 callback，这里用一次性回调
            # 保证接口兼容，但不模拟真正的流式分块。
            on_stream_chunk(parsed_text)

        diagnostics = StepDiagnostics(
            stopReason=data.get("stop_reason") if isinstance(data, dict) else None,
            blockTypes=block_types,
            ignoredBlockTypes=ignored_block_types,
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


__all__ = ["AnthropicModelAdapter"]
