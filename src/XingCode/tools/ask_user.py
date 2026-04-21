from __future__ import annotations

from XingCode.core.tooling import ToolDefinition, ToolResult


def _validate(input_data: dict) -> dict:
    """Validate and normalize the ask_user input payload."""

    question = input_data.get("question")
    # 校验：必须是字符串 + 不能为空
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question is required")
    return {"question": question.strip()}

# 工具执行逻辑：真正干活的地方;
def _run(input_data: dict, _context) -> ToolResult:
    """Return awaitUser=True so the current agent turn pauses for clarification."""

    return ToolResult(ok=True, output=input_data["question"], awaitUser=True)

# 定义一个完整的工具：ask_user（向用户提问）
ask_user_tool = ToolDefinition(
    name="ask_user",
    description="Pause the turn and ask the user a clarifying question.",
    input_schema={
        "type": "object",
        "properties": {"question": {"type": "string"}},
        "required": ["question"],
    },
    validator=_validate,
    run=_run,
)
