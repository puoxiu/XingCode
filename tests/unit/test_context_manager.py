from pathlib import Path

from XingCode.core.agent_loop import run_agent_turn
from XingCode.core.context_manager import ContextManager, estimate_message_tokens, estimate_tokens
from XingCode.core.prompt_pipeline import (
    SYSTEM_PROMPT_DYNAMIC_BOUNDARY,
    PromptPipeline,
    read_file_cached,
)
from XingCode.core.tooling import ToolRegistry
from XingCode.core.types import AgentStep, ChatMessage, ModelAdapter


class RecordingModel(ModelAdapter):
    """记录模型收到的消息，便于验证压缩是否真实接入主循环。"""

    def __init__(self, response: str = "done") -> None:
        """初始化测试模型。"""

        self.response = response
        self.seen_messages: list[ChatMessage] = []

    def next(self, messages: list[ChatMessage], on_stream_chunk=None) -> AgentStep:
        """返回固定响应，并记录本次实际收到的消息。"""

        _ = on_stream_chunk
        self.seen_messages = list(messages)
        return AgentStep(type="assistant", content=self.response)


def test_estimate_tokens_supports_mixed_text() -> None:
    """中英文混合文本应能被稳定估算出 token。"""

    english_tokens = estimate_tokens("hello world from xingcode")
    chinese_tokens = estimate_tokens("你好，世界，来自星码")

    assert english_tokens > 0
    assert chinese_tokens > 0
    assert chinese_tokens >= english_tokens / 2


def test_estimate_message_tokens_includes_tool_input() -> None:
    """工具调用消息应计入 input 的 token。"""

    plain = {"role": "assistant", "content": "done"}
    tool_call = {
        "role": "assistant_tool_call",
        "toolName": "read_file",
        "content": "",
        "input": {"path": "README.md", "offset": 0},
    }

    assert estimate_message_tokens(tool_call) > estimate_message_tokens(plain)


def test_context_manager_compacts_to_system_and_recent_messages() -> None:
    """压缩后应保留 system prompt 和最近消息。"""

    manager = ContextManager(context_window=120)
    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "old user " * 30},
        {"role": "assistant", "content": "old assistant " * 30},
        {"role": "assistant_progress", "content": "progress note"},
        {"role": "user", "content": "recent user " * 10},
        {"role": "assistant", "content": "recent assistant " * 10},
    ]

    manager.set_messages(messages)
    compacted = manager.compact_messages()

    assert compacted[0]["role"] == "system"
    assert compacted[-1]["content"] == messages[-1]["content"]
    assert all(message.get("role") != "assistant_progress" for message in compacted)
    assert len(compacted) < len(messages)
    assert manager.compaction_history


def test_run_agent_turn_uses_context_manager_before_model_call() -> None:
    """主循环应在调用模型前真正执行上下文压缩。"""

    model = RecordingModel()
    context_manager = ContextManager(context_window=120)
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "old request " * 35},
        {"role": "assistant", "content": "old response " * 35},
        {"role": "user", "content": "latest request"},
    ]

    result = run_agent_turn(
        model=model,
        tools=ToolRegistry([]),
        messages=messages,
        cwd=".",
        context_manager=context_manager,
    )

    assert result[-1] == {"role": "assistant", "content": "done"}
    assert model.seen_messages[0]["role"] == "system"
    assert model.seen_messages[-1]["content"] == "latest request"
    assert len(model.seen_messages) < len(messages)


def test_prompt_pipeline_can_insert_dynamic_boundary() -> None:
    """Prompt pipeline 应能按参考项目风格插入动态边界。"""

    pipeline = PromptPipeline()
    pipeline.register_static("role", "role text")
    pipeline.register_dynamic("tools", lambda: "tool text")

    prompt = pipeline.build()

    assert SYSTEM_PROMPT_DYNAMIC_BOUNDARY in prompt
    assert prompt.startswith("role text")
    assert prompt.endswith("tool text")


def test_read_file_cached_reuses_previous_text(tmp_path: Path) -> None:
    """文件缓存读取应返回稳定结果。"""

    target = tmp_path / "demo.txt"
    target.write_text("hello", encoding="utf-8")

    first = read_file_cached(target, ttl=60.0)
    second = read_file_cached(target, ttl=60.0)

    assert first == "hello"
    assert second == "hello"
