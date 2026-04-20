from XingCode.core.types import AgentStep, StepDiagnostics


def test_step_diagnostics_defaults() -> None:
    diagnostics = StepDiagnostics()

    assert diagnostics.stopReason is None
    assert diagnostics.blockTypes == []
    assert diagnostics.ignoredBlockTypes == []


def test_agent_step_defaults() -> None:
    step = AgentStep(type="assistant", content="done")

    assert step.type == "assistant"
    assert step.content == "done"
    assert step.kind is None
    assert step.calls == []
    assert step.contentKind is None
    assert step.diagnostics is None


def test_agent_step_supports_tool_calls() -> None:
    step = AgentStep(
        type="tool_calls",
        calls=[{"id": "call-1", "toolName": "echo", "input": {"text": "hi"}}],
        content="working",
        kind="progress",
    )

    assert step.type == "tool_calls"
    assert step.calls[0]["toolName"] == "echo"
    assert step.kind == "progress"
