from __future__ import annotations

from XingCode.core.tooling import ToolDefinition, ToolResult
from XingCode.security.file_review import apply_reviewed_file_change, load_existing_file
from XingCode.security.workspace import resolve_tool_path


def _validate(input_data: dict) -> dict:
    """Validate and normalize the patch_file input payload."""

    path = input_data.get("path")
    replacements = input_data.get("replacements")
    patch = input_data.get("patch")

    if not isinstance(path, str) or not path:
        raise ValueError("path is required")

    if replacements is None:
        if not isinstance(patch, str) or not patch:
            raise ValueError("patch must be a string")
        replacements = [{"search": patch, "replace": ""}]

    if not isinstance(replacements, list) or not replacements:
        raise ValueError("replacements must be a non-empty list")

    normalized: list[dict[str, object]] = []
    for replacement in replacements:
        if not isinstance(replacement, dict):
            raise ValueError("replacement entries must be objects")

        search = replacement.get("search")
        replace = replacement.get("replace")
        replace_all = bool(replacement.get("replaceAll", replacement.get("replace_all", False)))

        if not isinstance(search, str) or not search:
            raise ValueError("replacement search must be a non-empty string")
        if not isinstance(replace, str):
            raise ValueError("replacement replace must be a string")

        normalized.append(
            {
                "search": search.replace("\r\n", "\n"),
                "replace": replace.replace("\r\n", "\n"),
                "replace_all": replace_all,
            }
        )

    return {"path": path, "replacements": normalized}

    # 工具执行函数：批量文件补丁工具（核心）
    # 逻辑：读取文件 → 按顺序执行N次精确替换 → 一次性写入 → 输出结果
    # 特点：一次调用执行多次替换，中间结果不写入磁盘，效率极高
def _run(input_data: dict, context) -> ToolResult:
    """Apply multiple exact replacements and review the final combined diff once."""

    target = resolve_tool_path(context, input_data["path"], "write")
    content = load_existing_file(target)
    applied: list[str] = []

    for index, replacement in enumerate(input_data["replacements"], start=1):
        search = replacement["search"]
        replace = replacement["replace"]
        replace_all = bool(replacement.get("replace_all", replacement.get("replaceAll", False)))

        if search not in content:
            return ToolResult(ok=False, output=f"Replacement {index} not found in {input_data['path']}")

        # Apply replacements sequentially so each later replacement sees the
        # file state produced by earlier replacements in the same tool call.
        if replace_all:
            content = replace.join(content.split(search))
            applied.append(f"#{index} replaceAll")
        else:
            content = content.replace(search, replace, 1)
            applied.append(f"#{index} replaceOnce")

    result = apply_reviewed_file_change(context, input_data["path"], target, content)
    if not result.ok:
        return result

    return ToolResult(
        ok=True,
        output=f"Patched {input_data['path']} with {len(applied)} replacement(s): {', '.join(applied)}",
    )

# 定义一个完整的工具：patch_file（文件补丁工具）；功能：对文件进行多处精确文本替换；输入：文件路径、替换规则列表；输出：替换结果
patch_file_tool = ToolDefinition(
    name="patch_file",
    description="Apply multiple exact-text replacements to one file in a single operation.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "replacements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "search": {"type": "string"},
                        "replace": {"type": "string"},
                        "replaceAll": {"type": "boolean"},
                    },
                    "required": ["search", "replace"],
                },
            },
        },
        "required": ["path", "replacements"],
    },
    validator=_validate,
    run=_run,
)
