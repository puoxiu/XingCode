from __future__ import annotations

from pathlib import Path

from XingCode.core.tooling import ToolDefinition, ToolResult
from XingCode.security.workspace import resolve_tool_path

DEFAULT_LIST_LIMIT = 200
MAX_LIST_LIMIT = 500

# 输入校验函数：校验 list_files 工具的参数是否合法
# 作用：确保路径格式正确、limit 在安全范围内
def _validate(input_data: dict) -> dict:
    """Validate and normalize the list_files input payload."""

    path = input_data.get("path", ".")
    if not isinstance(path, str):
        raise ValueError("path must be a string")

    try:
        limit = int(input_data.get("limit", DEFAULT_LIST_LIMIT))
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc

    if limit < 1 or limit > MAX_LIST_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIST_LIMIT}")

    return {"path": path, "limit": limit}

# 工具执行函数：列出指定目录下的文件与文件夹
# 逻辑：安全解析路径 → 判断路径是否存在 → 读取目录 → 格式化输出 → 限制数量
def _run(input_data: dict, context) -> ToolResult:
    """List one directory level using the simple dir/file format from the reference project."""

    target = resolve_tool_path(context, input_data["path"], "list")
    if not target.exists():
        return ToolResult(ok=False, output=f"Path does not exist: {input_data['path']}")
    if target.is_file():
        return ToolResult(ok=True, output=f"file {Path(input_data['path']).name}")

    entries = sorted(target.iterdir(), key=lambda item: item.name.lower())
    lines = [f"{'dir' if entry.is_dir() else 'file'} {entry.name}" for entry in entries]
    if not lines:
        return ToolResult(ok=True, output="(empty)")
    limit = int(input_data.get("limit", DEFAULT_LIST_LIMIT))
    return ToolResult(ok=True, output="\n".join(lines[:limit]))

# 注册完整的目录列表工具
list_files_tool = ToolDefinition(
    name="list_files",
    description="List files and directories relative to the workspace root.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "limit": {"type": "number"},
        },
    },
    validator=_validate,
    run=_run,
)
