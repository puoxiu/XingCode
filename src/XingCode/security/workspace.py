from __future__ import annotations
from pathlib import Path

from XingCode.core.tooling import ToolContext

def resolve_tool_path(context: ToolContext, input_path: str, intent: str) -> Path:
    """
    【核心安全函数】工具路径解析与权限校验
    作用：把 AI 传入的任意路径 → 标准化 → 校验是否越权 → 返回安全路径
    是整个 AI 文件系统的**安全大门**，防止目录穿越攻击！
    """

    # 1. 将输入字符串转为 Path 对象
    candidate = Path(input_path)

    # 2. 拼接绝对路径：
    #    - 输入是绝对路径 → 直接用
    #    - 输入是相对路径 → 基于当前工作目录 context.cwd 拼接
    target = candidate if candidate.is_absolute() else Path(context.cwd) / candidate

    # 3. 标准化路径（解析 . / .. 符号链接，得到最终绝对路径）
    normalized = target.resolve()

    # ===================== 核心安全逻辑 =====================
    # 如果系统启用了权限模块 → 通过权限模块校验路径访问
    if context.permissions is not None:
        # 权限中心统一校验：读/写/执行 权限
        context.permissions.ensure_path_access(str(normalized), intent)
    
    # 如果没有权限模块 → 启用兜底安全策略：禁止访问工作区外文件
    else:
        # 获取当前工作区根目录（绝对路径）
        workspace_root = Path(context.cwd).resolve()
        
        try:
            # 关键校验：检查标准化后的路径 是否在 工作区目录内部
            normalized.relative_to(workspace_root)
        except ValueError as exc:
            # 一旦路径跳出工作区 → 直接抛出权限异常
            raise PermissionError(f"Path escapes workspace: {input_path}") from exc

    # 所有校验通过 → 返回安全合法的路径给工具使用
    return normalized