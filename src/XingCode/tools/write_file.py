from __future__ import annotations

from XingCode.core.tooling import ToolDefinition
from XingCode.security.file_review import apply_reviewed_file_change
from XingCode.security.workspace import resolve_tool_path


#     输入校验函数：校验 write_file 工具参数
# 确保 path 和 content 格式合法、非空
def _validate(input_data: dict) -> dict:
    """Validate and normalize the write_file input payload."""

    path = input_data.get("path")
    content = input_data.get("content")
    if not isinstance(path, str) or not path:
        raise ValueError("path is required")
    if not isinstance(content, str):
        raise ValueError("content must be a string")
    return {"path": path, "content": content}

# 工具执行函数：安全写入文本文件
# 所有写入操作必须经过安全审计与权限校验
# 不会直接写入磁盘，统一走安全网关
def _run(input_data: dict, context):
    """Write a text file only after the edit has passed the review boundary."""

    target = resolve_tool_path(context, input_data["path"], "write")
    return apply_reviewed_file_change(context, input_data["path"], target, input_data["content"])

# 注册完整的文件写入工具
write_file_tool = ToolDefinition(
    name="write_file",
    description="Write a UTF-8 text file relative to the workspace root.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    },
    validator=_validate,
    run=_run,
)
