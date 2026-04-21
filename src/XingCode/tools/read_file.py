from __future__ import annotations

from XingCode.core.tooling import ToolDefinition, ToolResult
from XingCode.security.workspace import resolve_tool_path

DEFAULT_READ_LIMIT = 8000
MAX_READ_LIMIT = 20000

# 输入校验函数：校验 read_file 的参数是否合法
# 确保路径、偏移量、读取长度都符合安全规范
def _validate(input_data: dict) -> dict:
    """Validate and normalize the read_file input payload."""

    path = input_data.get("path")
    if not isinstance(path, str) or not path:
        raise ValueError("path is required")

    try:
        offset = int(input_data.get("offset", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("offset must be an integer") from exc

    try:
        limit = int(input_data.get("limit", DEFAULT_READ_LIMIT))
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc

    if offset < 0:
        raise ValueError("offset must be >= 0")
    if limit < 1 or limit > MAX_READ_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_READ_LIMIT}")

    return {"path": path, "offset": offset, "limit": limit}

# 工具执行函数：安全读取文本文件
# 支持分页读取、大文件截断、UTF-8 校验、安全路径校验
# 输出格式固定，方便 AI 自动续读
def _run(input_data: dict, context) -> ToolResult:
    """Read a UTF-8 file chunk and return a pagination-friendly header."""

    target = resolve_tool_path(context, input_data["path"], "read")
    if not target.exists():
        return ToolResult(ok=False, output=f"Path does not exist: {input_data['path']}")
    if not target.is_file():
        return ToolResult(ok=False, output=f"Path is not a file: {input_data['path']}")

    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ToolResult(
            ok=False,
            output=f"File {input_data['path']} appears to be binary. Cannot read as text.",
        )

    offset = input_data["offset"]
    limit = input_data["limit"]
    end = min(len(content), offset + limit)
    chunk = content[offset:end]
    truncated = end < len(content)

    # Keep the output shape stable so later agent steps can continue reading
    # from the reported END offset without guessing file state.
    header = "\n".join(
        [
            f"FILE: {input_data['path']}",
            f"OFFSET: {offset}",
            f"END: {end}",
            f"TOTAL_CHARS: {len(content)}",
            f"TRUNCATED: {'yes - call read_file again with offset ' + str(end) if truncated else 'no'}",
            "",
        ]
    )
    return ToolResult(ok=True, output=header + chunk)

# 注册完整的文件读取工具
read_file_tool = ToolDefinition(
    name="read_file",
    description="Read a UTF-8 text file relative to the workspace root.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "offset": {"type": "number"},
            "limit": {"type": "number"},
        },
        "required": ["path"],
    },
    validator=_validate,
    run=_run,
)
