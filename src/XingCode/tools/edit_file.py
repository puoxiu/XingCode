from __future__ import annotations

from XingCode.core.tooling import ToolDefinition, ToolResult
from XingCode.security.file_review import apply_reviewed_file_change, load_existing_file
from XingCode.security.workspace import resolve_tool_path

# 输入校验函数：校验 edit_file 工具的参数是否合法
# 作用：确保 AI 传入的参数格式正确、内容非空
def _validate(input_data: dict) -> dict:
    """Validate and normalize the edit_file input payload."""

    path = input_data.get("path")
    search = input_data.get("search", input_data.get("old"))
    replace = input_data.get("replace", input_data.get("new"))
    replace_all = bool(input_data.get("replaceAll", input_data.get("replace_all", False)))

    if not isinstance(path, str) or not path:
        raise ValueError("path is required")
    if not isinstance(search, str) or not search:
        raise ValueError("search must be a non-empty string")
    if not isinstance(replace, str):
        raise ValueError("replace must be a string")

    return {
        "path": path,
        "search": search.replace("\r\n", "\n"),
        "replace": replace.replace("\r\n", "\n"),
        "replace_all": replace_all,
    }

# 工具执行逻辑：精确文本替换编辑文件; 逻辑：读取文件 → 匹配文本 → 替换（单次/全部）→ 安全写入
def _run(input_data: dict, context) -> ToolResult:
    """Replace one exact match, or all matches when replace_all is explicitly requested."""

    target = resolve_tool_path(context, input_data["path"], "write")
    content = load_existing_file(target)
    search = str(input_data.get("search", input_data.get("old", ""))).replace("\r\n", "\n")
    replace = str(input_data.get("replace", input_data.get("new", ""))).replace("\r\n", "\n")
    replace_all = bool(input_data.get("replace_all", input_data.get("replaceAll", False)))

    match_count = content.count(search)

    if match_count == 0:
        return ToolResult(ok=False, output=f"Search string not found in {input_data['path']}")
    if match_count > 1 and not replace_all:
        return ToolResult(
            ok=False,
            output=(
                f"Found {match_count} matches for the search string. "
                "Use replace_all=true to replace every occurrence, or provide more context."
            ),
        )

    # Keep the first implementation deliberately strict so later model behavior
    # is predictable and aligned with the reference project's exact-text edits.
    if replace_all:
        next_content = replace.join(content.split(search))
    else:
        next_content = content.replace(search, replace, 1)

    return apply_reviewed_file_change(context, input_data["path"], target, next_content)

# 文件编辑工具
edit_file_tool = ToolDefinition(
    name="edit_file",
    description="Replace exact text in a file. Use replace_all=true when the search string appears multiple times.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old": {"type": "string"},
            "new": {"type": "string"},
            "replace_all": {"type": "boolean"},
        },
        "required": ["path", "old", "new"],
    },
    validator=_validate,
    run=_run,
)
