from XingCode.adapters.mock_model import MockModelAdapter

# 测试：用户输入 /read 文件名 → 调用 read_file 工具
def test_mock_model_turns_read_into_tool_call() -> None:
    """The mock model should map /read to the read_file tool."""

    adapter = MockModelAdapter()
    step = adapter.next([{"role": "user", "content": "/read README.md"}])

    assert step.type == "tool_calls"
    assert step.calls[0]["toolName"] == "read_file"
    assert step.calls[0]["input"] == {"path": "README.md"}

# 测试：用户输入 /cmd 命令 → 调用 run_command 工具
def test_mock_model_turns_cmd_into_tool_call() -> None:
    """The mock model should map /cmd to the run_command tool."""

    adapter = MockModelAdapter()
    step = adapter.next([{"role": "user", "content": "/cmd pwd"}])

    assert step.type == "tool_calls"
    assert step.calls[0]["toolName"] == "run_command"
    assert step.calls[0]["input"] == {"command": "pwd"}

# 测试：模拟模型能接收工具结果，并总结成文本回复
def test_mock_model_summarizes_tool_result() -> None:
    """The mock model should turn a tool_result back into a simple assistant summary."""

    adapter = MockModelAdapter()
    step = adapter.next(
        [
            {"role": "user", "content": "/read README.md"},
            {
                "role": "assistant_tool_call",
                "toolUseId": "1",
                "toolName": "read_file",
                "input": {"path": "README.md"},
            },
            {
                "role": "tool_result",
                "toolUseId": "1",
                "toolName": "read_file",
                "content": "FILE: README.md",
                "isError": False,
            },
        ]
    )

    assert step.type == "assistant"
    assert "README.md" in step.content
    assert "File contents" in step.content

# 测试：用户输入不匹配任何指令 → 返回默认提示文本
def test_mock_model_default_message_is_readable() -> None:
    """The fallback assistant message should explain the limited mock commands."""

    adapter = MockModelAdapter()
    step = adapter.next([{"role": "user", "content": "hello"}])

    assert step.type == "assistant"
    assert "mock model" in step.content
    assert "/read README.md" in step.content
    assert "/cmd pwd" in step.content
