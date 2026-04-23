"""XingCode 的上下文窗口管理器。"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

# 常见模型的上下文窗口，先沿用参考项目的主流配置。
DEFAULT_CONTEXT_WINDOWS = {
    "claude-sonnet-4-20250514": 200_000,
    "claude-opus-4-20250514": 200_000,
    "claude-haiku-3-20240307": 100_000,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "o1": 200_000,
    "o1-mini": 128_000,
    "o3-mini": 200_000,
    "openrouter/auto": 200_000,
    "anthropic/claude-sonnet-4": 200_000,
    "anthropic/claude-opus-4": 200_000,
    "openai/gpt-4o": 128_000,
    "openai/gpt-4o-mini": 128_000,
    "google/gemini-2.5-pro": 1_000_000,
    "google/gemini-2.5-flash": 1_000_000,
    "default": 128_000,
}

AUTOCOMPACT_THRESHOLD = 0.95
TARGET_USAGE_AFTER_COMPACTION = 0.70
CHARS_PER_TOKEN = 4.0
MIN_RECENT_MESSAGES_TO_KEEP = 6
MIN_TRUNCATED_MESSAGE_TOKENS = 32

_CJK_PATTERN = re.compile(r"[\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF\uAC00-\uD7AF]")
_ROLE_TOKEN_OVERHEAD = {
    "system": 3,
    "user": 4,
    "assistant": 3,
    "assistant_progress": 3,
    "assistant_tool_call": 7,
    "tool_result": 6,
}
_TRUNCATION_MARKER = "\n...[context compacted]...\n"

# 高频估算使用简单缓存，避免重复扫描长文本。
_token_cache: dict[str | int, int] = {}
_TOKEN_CACHE_MAX = 1024


def estimate_tokens(text: str) -> int:
    """按中英文混合启发式估算文本 token 数。"""

    if not text:
        return 0

    cache_key: str | int = text if len(text) <= 256 else hash(text)
    cached = _token_cache.get(cache_key)
    if cached is not None:
        return cached

    cjk_count = len(_CJK_PATTERN.findall(text))
    ascii_count = len(text) - cjk_count
    tokens = max(1, int(cjk_count / 1.5 + ascii_count / CHARS_PER_TOKEN))

    if len(_token_cache) < _TOKEN_CACHE_MAX:
        _token_cache[cache_key] = tokens
    return tokens


def estimate_message_tokens(message: dict[str, Any]) -> int:
    """估算单条消息占用的 token。"""

    tokens = _ROLE_TOKEN_OVERHEAD.get(str(message.get("role", "")), 0)

    content = message.get("content", "")
    if isinstance(content, str):
        tokens += estimate_tokens(content)

    if "input" in message:
        input_value = message["input"]
        if isinstance(input_value, dict):
            serialized = json.dumps(input_value, ensure_ascii=False, sort_keys=True)
        else:
            serialized = str(input_value)
        tokens += estimate_tokens(serialized)

    return tokens


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """估算一组消息总共占用的 token。"""

    return sum(estimate_message_tokens(message) for message in messages)


@dataclass(slots=True)
class ContextStats:
    """描述当前上下文窗口使用情况的统计信息。"""

    total_tokens: int = 0
    context_window: int = 0
    usage_percentage: float = 0.0
    messages_count: int = 0
    system_tokens: int = 0
    conversation_tokens: int = 0
    tool_calls_count: int = 0
    is_near_limit: bool = False
    should_compact: bool = False


@dataclass
class ContextManager:
    """跟踪上下文使用量，并在超阈值时压缩旧消息。"""

    model: str = "default"
    context_window: int = 0
    messages: list[dict[str, Any]] = field(default_factory=list)
    compaction_history: list[dict[str, Any]] = field(default_factory=list)
    min_recent_messages: int = MIN_RECENT_MESSAGES_TO_KEEP
    target_usage_after_compaction: float = TARGET_USAGE_AFTER_COMPACTION
    _message_token_cache: dict[int, int] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        """补齐默认 context window，并初始化消息缓存。"""

        if self.context_window <= 0:
            self.context_window = DEFAULT_CONTEXT_WINDOWS.get(
                self.model,
                DEFAULT_CONTEXT_WINDOWS["default"],
            )
        self.set_messages(self.messages)

    def update_model(self, model: str) -> None:
        """更新模型名，并切换到对应的 context window。"""

        self.model = model
        self.context_window = DEFAULT_CONTEXT_WINDOWS.get(
            model,
            DEFAULT_CONTEXT_WINDOWS["default"],
        )

    def set_messages(self, messages: list[dict[str, Any]]) -> None:
        """替换当前追踪的消息列表，并刷新 token 缓存。"""

        self.messages = list(messages)
        self._message_token_cache = {
            id(message): estimate_message_tokens(message)
            for message in self.messages
        }

    def add_message(self, message: dict[str, Any]) -> None:
        """追加一条消息并缓存它的 token 数。"""

        self.messages.append(message)
        self._message_token_cache[id(message)] = estimate_message_tokens(message)

    def get_stats(self) -> ContextStats:
        """统计当前上下文窗口的占用情况。"""

        if not self.messages:
            return ContextStats(context_window=self.context_window)

        system_tokens = 0
        conversation_tokens = 0
        tool_calls_count = 0

        for message in self.messages:
            message_tokens = self._message_token_cache.get(id(message))
            if message_tokens is None:
                message_tokens = estimate_message_tokens(message)
                self._message_token_cache[id(message)] = message_tokens

            if message.get("role") == "system":
                system_tokens += message_tokens
            else:
                conversation_tokens += message_tokens

            if message.get("role") == "assistant_tool_call":
                tool_calls_count += 1

        total_tokens = system_tokens + conversation_tokens
        usage_percentage = (
            total_tokens / self.context_window * 100
            if self.context_window > 0
            else 0.0
        )

        return ContextStats(
            total_tokens=total_tokens,
            context_window=self.context_window,
            usage_percentage=usage_percentage,
            messages_count=len(self.messages),
            system_tokens=system_tokens,
            conversation_tokens=conversation_tokens,
            tool_calls_count=tool_calls_count,
            is_near_limit=usage_percentage >= 80.0,
            should_compact=usage_percentage >= AUTOCOMPACT_THRESHOLD * 100,
        )

    def should_auto_compact(self) -> bool:
        """判断当前是否需要自动压缩。"""

        return self.get_stats().should_compact

    def compact_messages(self) -> list[dict[str, Any]]:
        """压缩消息列表，只保留 system prompt 和尽量多的最近消息。"""

        stats = self.get_stats()
        if not stats.should_compact:
            return list(self.messages)

        system_messages = [
            message for message in self.messages if message.get("role") == "system"
        ]
        conversation_messages = [
            message
            for message in self.messages
            if message.get("role") not in {"system", "assistant_progress"}
        ]

        target_tokens = max(
            estimate_messages_tokens(system_messages),
            int(self.context_window * self.target_usage_after_compaction),
        )
        current_tokens = estimate_messages_tokens(system_messages)
        kept_reversed: list[dict[str, Any]] = []

        # 从最新消息开始反向保留，确保最近上下文优先级最高。
        for message in reversed(conversation_messages):
            soft_budget = max(target_tokens - current_tokens, 0)
            hard_budget = max(self.context_window - current_tokens, 0)
            must_keep_recent = len(kept_reversed) < self.min_recent_messages
            budget = hard_budget if must_keep_recent else soft_budget
            if budget <= 0:
                continue

            candidate = self._truncate_message_to_budget(message, budget)
            candidate_tokens = estimate_message_tokens(candidate)
            allowed_total = self.context_window if must_keep_recent else target_tokens

            if current_tokens + candidate_tokens > allowed_total:
                continue

            kept_reversed.append(candidate)
            current_tokens += candidate_tokens

        # 极端情况下，至少尝试保住最后一条非 system 消息。
        if not kept_reversed and conversation_messages:
            hard_budget = max(
                self.context_window - estimate_messages_tokens(system_messages),
                MIN_TRUNCATED_MESSAGE_TOKENS,
            )
            last_message = self._truncate_message_to_budget(
                conversation_messages[-1],
                hard_budget,
            )
            kept_reversed.append(last_message)

        compacted = system_messages + list(reversed(kept_reversed))
        after_tokens = estimate_messages_tokens(compacted)

        self.compaction_history.append(
            {
                "timestamp": time.time(),
                "before_tokens": stats.total_tokens,
                "after_tokens": after_tokens,
                "before_messages": len(self.messages),
                "after_messages": len(compacted),
                "removed_messages": max(0, len(self.messages) - len(compacted)),
            }
        )

        self.set_messages(compacted)
        return list(self.messages)

    def get_context_summary(self) -> str:
        """返回简短的人类可读上下文摘要。"""

        stats = self.get_stats()
        if stats.messages_count == 0:
            return "Context: empty"

        return (
            f"Context: {stats.usage_percentage:.0f}% "
            f"({stats.total_tokens}/{stats.context_window} tokens, "
            f"{stats.messages_count} messages)"
        )

    def _truncate_message_to_budget(
        self,
        message: dict[str, Any],
        token_budget: int,
    ) -> dict[str, Any]:
        """在给定预算内尽量保留一条消息的头尾内容。"""

        if token_budget <= 0:
            return message

        current_tokens = estimate_message_tokens(message)
        if current_tokens <= token_budget:
            return message

        content = message.get("content", "")
        if not isinstance(content, str) or not content:
            return message

        # 用字符数近似映射 token 预算，保留头尾信息，便于人和模型恢复最近语义。
        max_chars = max(
            64,
            int(max(token_budget - _ROLE_TOKEN_OVERHEAD.get(str(message.get("role", "")), 0), 1) * CHARS_PER_TOKEN),
        )
        if len(content) <= max_chars:
            return message

        marker_length = len(_TRUNCATION_MARKER)
        if max_chars <= marker_length + 16:
            truncated = content[:max_chars]
            return {**message, "content": truncated}

        head_chars = max(16, int(max_chars * 0.7))
        tail_chars = max(8, max_chars - head_chars - marker_length)
        truncated = content[:head_chars] + _TRUNCATION_MARKER + content[-tail_chars:]
        return {**message, "content": truncated}
