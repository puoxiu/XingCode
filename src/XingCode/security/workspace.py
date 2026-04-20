from __future__ import annotations

from pathlib import Path

from XingCode.core.tooling import ToolContext

# 作用：把用户输入路径 → 转成安全、可控、不会越权的绝对路径
def resolve_tool_path(context: ToolContext, input_path: str, intent: str) -> Path:
    """Resolve a tool path relative to the current cwd and enforce access checks."""

    candidate = Path(input_path)
    target = candidate if candidate.is_absolute() else Path(context.cwd) / candidate
    normalized = target.resolve()

    # 有权限系统则进行权限检查 没有则检查目标路径是否在 workspace 内部
    if context.permissions is not None:
        context.permissions.ensure_path_access(str(normalized), intent)
    else:
        workspace_root = Path(context.cwd).resolve()
        try:
            normalized.relative_to(workspace_root)
        except ValueError as exc:
            raise PermissionError(f"Path escapes workspace: {input_path}") from exc

    return normalized
