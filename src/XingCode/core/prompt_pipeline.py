"""XingCode 的系统提示词拼装流水线。"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# 动态边界标记沿用参考项目的命名，后续如果接入 prompt cache，
# 可以直接基于这个哨兵值切分静态/动态段落。
SYSTEM_PROMPT_DYNAMIC_BOUNDARY = "__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__"


@dataclass(slots=True)
class PromptSection:
    """表示一个可按条件启用、可缓存的提示词段落。"""

    name: str
    builder: Callable[[], str]
    condition: Callable[[], bool] | None = None
    cache_ttl: float = 300.0
    _cached_value: str | None = field(default=None, repr=False)
    _cached_at: float = field(default=0.0, repr=False)

    def evaluate(self) -> str | None:
        """在满足条件时生成当前段落文本。"""

        if self.condition is not None and not self.condition():
            return None

        now = time.monotonic()
        if self._cached_value is not None and (now - self._cached_at) < self.cache_ttl:
            return self._cached_value

        text = self.builder()
        self._cached_value = text
        self._cached_at = now
        return text


class PromptPipeline:
    """管理静态段落和动态段落的最小提示词流水线。"""

    def __init__(self, *, include_dynamic_boundary: bool = True) -> None:
        """初始化提示词流水线。"""

        self._include_dynamic_boundary = include_dynamic_boundary
        self._static_sections: list[PromptSection] = []
        self._dynamic_sections: list[PromptSection] = []

    def register_static(self, name: str, text: str) -> None:
        """注册稳定不变的静态段落。"""

        self._static_sections.append(
            PromptSection(
                name=name,
                builder=lambda: text,
                cache_ttl=float("inf"),
            )
        )

    def register_dynamic(
        self,
        name: str,
        builder: Callable[[], str],
        condition: Callable[[], bool] | None = None,
        cache_ttl: float = 300.0,
    ) -> None:
        """注册可能随回合变化的动态段落。"""

        self._dynamic_sections.append(
            PromptSection(
                name=name,
                builder=builder,
                condition=condition,
                cache_ttl=cache_ttl,
            )
        )

    def build(self) -> str:
        """按顺序拼装完整系统提示词。"""

        parts: list[str] = []

        for section in self._static_sections:
            text = section.evaluate()
            if text:
                parts.append(text)

        # 当前阶段的 adapter 还没有真正使用 prompt cache，
        # 所以是否输出动态边界由调用方显式控制，避免把哨兵文本直接泄露给模型。
        if self._dynamic_sections and self._include_dynamic_boundary:
            parts.append(SYSTEM_PROMPT_DYNAMIC_BOUNDARY)

        for section in self._dynamic_sections:
            text = section.evaluate()
            if text:
                parts.append(text)

        return "\n\n".join(part for part in parts if part)

    def clear_cache(self) -> None:
        """清空所有段落缓存，强制下次重新生成。"""

        for section in self._static_sections + self._dynamic_sections:
            section._cached_value = None
            section._cached_at = 0.0


# 文件内容缓存，避免频繁重复读取同一个说明文件。
_file_cache: dict[str, tuple[str, float, float]] = {}


def read_file_cached(path: Path, ttl: float = 300.0) -> str | None:
    """按 mtime + TTL 读取文件，并复用缓存结果。"""

    cache_key = str(path.resolve())
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None

    cached = _file_cache.get(cache_key)
    if cached is not None:
        cached_text, cached_mtime, cached_at = cached
        if cached_mtime == mtime and (time.monotonic() - cached_at) < ttl:
            return cached_text

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    _file_cache[cache_key] = (text, mtime, time.monotonic())
    return text


def content_hash(text: str) -> str:
    """计算短 hash，便于后续扩展缓存失效策略。"""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
