from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable, Literal

# ====================== 类型定义 ======================
# 权限决策枚举：用户可以选择的所有操作
PermissionDecision = Literal[
    "allow_once",         # 允许一次
    "allow_always",       # 永久允许
    "allow_turn",         # 本回合允许这个文件
    "allow_all_turn",     # 本回合允许所有编辑
    "deny_once",          # 拒绝一次
    "deny_always",        # 永久拒绝
    "deny_with_feedback", # 拒绝并给AI反馈指导
]
# 弹窗回调函数类型：接收请求信息，返回用户决策
PromptHandler = Callable[[dict[str, Any]], dict[str, Any]]

_IS_WINDOWS = sys.platform == "win32"

# ====================== 工具函数 ======================

def _normalize_path(target_path: str) -> str:
    """Resolve a path once so later permission checks compare normalized values."""

    return str(Path(target_path).resolve())


def _is_within_directory(root: str, target: str) -> bool:
    """Check whether the target path stays inside the given root directory."""

    root_value = root.lower() if _IS_WINDOWS else root
    target_value = target.lower() if _IS_WINDOWS else target
    return target_value == root_value or target_value.startswith(root_value + os.sep)


def _matches_directory_prefix(target_path: str, directories: set[str]) -> bool:
    """Check whether a path matches any approved or denied directory prefix."""

    return any(_is_within_directory(directory, target_path) for directory in directories)


def _format_command_signature(command: str, args: list[str]) -> str:
    """Build the stable command signature used for session command decisions."""

    return " ".join([command, *args]).strip()


def _classify_dangerous_command(command: str, args: list[str]) -> str | None:
    """Return a human-readable reason when a command should require approval."""

    normalized_args = [arg.strip() for arg in args if arg.strip()]
    signature = _format_command_signature(command, normalized_args)

    if command == "git":
        if "reset" in normalized_args and "--hard" in normalized_args:
            return f"git reset --hard can discard local changes ({signature})"
        if "clean" in normalized_args:
            return f"git clean can delete untracked files ({signature})"
        if "checkout" in normalized_args and "--" in normalized_args:
            return f"git checkout -- can overwrite working tree files ({signature})"
        if "push" in normalized_args and any(arg in {"--force", "-f"} for arg in normalized_args):
            return f"git push --force rewrites remote history ({signature})"

    if command == "npm" and "publish" in normalized_args:
        return f"npm publish affects a registry outside this machine ({signature})"

    if command == "rm":
        combined_flags = "".join(arg for arg in normalized_args if arg.startswith("-")).lower()
        if "r" in combined_flags and "f" in combined_flags:
            return f"rm -rf can cause catastrophic data loss ({signature})"

    if command in {
        "node",
        "python",
        "python3",
        "pythonw",
        "bash",
        "sh",
        "zsh",
        "fish",
        "powershell",
        "pwsh",
    }:
        return f"{command} can execute arbitrary local code ({signature})"

    return None

# ====================== 权限管理器核心类 ======================
class PermissionManager:
    """In-memory permission manager for path, command, and edit approvals."""

    def __init__(self, workspace_root: str, prompt: PromptHandler | None = None) -> None:
        """Create one in-memory permission manager for the current runtime session."""

        # 工作区根目录（AI 只能默认访问这里）
        self.workspace_root = _normalize_path(workspace_root)
        self.prompt = prompt
        self.allowed_directory_prefixes: set[str] = set()
        self.denied_directory_prefixes: set[str] = set()
        self.session_allowed_paths: set[str] = set()
        self.session_denied_paths: set[str] = set()
        self.allowed_command_patterns: set[str] = set()
        self.denied_command_patterns: set[str] = set()
        self.session_allowed_commands: set[str] = set()
        self.session_denied_commands: set[str] = set()
        self.allowed_edit_patterns: set[str] = set()
        self.denied_edit_patterns: set[str] = set()
        self.session_allowed_edits: set[str] = set()
        self.session_denied_edits: set[str] = set()
        self.turn_allowed_edits: set[str] = set()
        self.turn_allow_all_edits = False

    def begin_turn(self) -> None:
        """Reset turn-scoped edit approvals at the start of a model turn."""
        # 在每一轮 AI 推理开始时，清空“本轮临时权限”，确保每次推理都是独立的
        self.turn_allowed_edits.clear()
        self.turn_allow_all_edits = False

    def end_turn(self) -> None:
        """Reset turn-scoped edit approvals at the end of a model turn."""

        self.begin_turn()

    def get_summary(self) -> list[str]:
        """Return a compact summary for later prompt/context injection."""

        summary = [f"cwd: {self.workspace_root}"]
        extra_dirs = ", ".join(sorted(self.allowed_directory_prefixes)[:4]) or "none"
        summary.append(f"extra allowed dirs: {extra_dirs}")
        dangerous_allowlist = ", ".join(sorted(self.allowed_command_patterns)[:4]) or "none"
        summary.append(f"dangerous allowlist: {dangerous_allowlist}")
        if self.allowed_edit_patterns:
            trusted = ", ".join(sorted(self.allowed_edit_patterns)[:2])
            summary.append(f"trusted edit targets: {trusted}")
        return summary

    def ensure_path_access(self, target_path: str, intent: str) -> None:
        """Allow cwd-local paths automatically and prompt for external paths."""

        # 检查路径是否允许访问：
        # 1. 在工作区内 → 放行
        # 2. 已在允许/拒绝列表 → 按规则处理
        # 3. 否则弹窗让用户确认
        normalized_target = _normalize_path(target_path)

        if _is_within_directory(self.workspace_root, normalized_target):
            return

        # Denials are checked before approvals so previously rejected paths fail
        # fast without showing the same prompt again.
        if (
            normalized_target in self.session_denied_paths
            or _matches_directory_prefix(normalized_target, self.denied_directory_prefixes)
        ):
            raise RuntimeError(f"Access denied for path outside cwd: {normalized_target}")

        if (
            normalized_target in self.session_allowed_paths
            or _matches_directory_prefix(normalized_target, self.allowed_directory_prefixes)
        ):
            return

        if self.prompt is None:
            raise RuntimeError(
                f"Path {normalized_target} is outside cwd {self.workspace_root}. "
                "Start XingCode in TTY mode to approve it."
            )

        scope_directory = normalized_target if intent in {"list", "command_cwd"} else str(Path(normalized_target).parent)
        result = self.prompt(
            {
                "kind": "path",
                "summary": f"XingCode wants {intent.replace('_', ' ')} access outside the current cwd",
                "details": [
                    f"cwd: {self.workspace_root}",
                    f"target: {normalized_target}",
                    f"scope directory: {scope_directory}",
                ],
                "scope": scope_directory,
                "choices": [
                    {"key": "y", "label": "allow once", "decision": "allow_once"},
                    {"key": "a", "label": "allow this directory", "decision": "allow_always"},
                    {"key": "n", "label": "deny once", "decision": "deny_once"},
                    {"key": "d", "label": "deny this directory", "decision": "deny_always"},
                ],
            }
        )
        decision = result.get("decision")

        if decision == "allow_once":
            self.session_allowed_paths.add(normalized_target)
            return
        if decision == "allow_always":
            self.allowed_directory_prefixes.add(scope_directory)
            return
        if decision == "deny_always":
            self.denied_directory_prefixes.add(scope_directory)
        else:
            self.session_denied_paths.add(normalized_target)

        raise RuntimeError(f"Access denied for path outside cwd: {normalized_target}")

    def ensure_command(
        self,
        command: str,
        args: list[str],
        command_cwd: str,
        force_prompt_reason: str | None = None,
    ) -> None:
        """Review a dangerous or unknown command after its cwd has been approved."""

        self.ensure_path_access(command_cwd, "command_cwd")
        reason = force_prompt_reason or _classify_dangerous_command(command, args)
        if not reason:
            return

        signature = _format_command_signature(command, args)
        if signature in self.session_denied_commands or signature in self.denied_command_patterns:
            raise RuntimeError(f"Command denied: {signature}")
        if signature in self.session_allowed_commands or signature in self.allowed_command_patterns:
            return

        if self.prompt is None:
            raise RuntimeError(
                f"Command requires approval: {signature}. "
                "Start XingCode in TTY mode to approve it."
            )

        summary = (
            "XingCode wants to run a dangerous command"
            if force_prompt_reason is None
            else "XingCode wants approval for this command"
        )
        result = self.prompt(
            {
                "kind": "command",
                "summary": summary,
                "details": [f"cwd: {command_cwd}", f"command: {signature}", f"reason: {reason}"],
                "scope": signature,
                "choices": [
                    {"key": "y", "label": "allow once", "decision": "allow_once"},
                    {"key": "a", "label": "always allow this command", "decision": "allow_always"},
                    {"key": "n", "label": "deny once", "decision": "deny_once"},
                    {"key": "d", "label": "always deny this command", "decision": "deny_always"},
                ],
            }
        )
        decision = result.get("decision")

        if decision == "allow_once":
            self.session_allowed_commands.add(signature)
            return
        if decision == "allow_always":
            self.allowed_command_patterns.add(signature)
            return
        if decision == "deny_always":
            self.denied_command_patterns.add(signature)
        else:
            self.session_denied_commands.add(signature)

        raise RuntimeError(f"Command denied: {signature}")

    def ensure_edit(self, target_path: str, diff_preview: str) -> None:
        """Require edit approval and always show the diff preview to the user."""

        normalized_target = _normalize_path(target_path)

        if (
            normalized_target in self.session_denied_edits
            or normalized_target in self.denied_edit_patterns
        ):
            raise RuntimeError(f"Edit denied: {normalized_target}")

        if (
            normalized_target in self.session_allowed_edits
            or normalized_target in self.turn_allowed_edits
            or self.turn_allow_all_edits
            or normalized_target in self.allowed_edit_patterns
        ):
            return

        if self.prompt is None:
            raise RuntimeError(
                f"Edit requires approval: {normalized_target}. "
                "Start XingCode in TTY mode to review it."
            )

        # File edits are approved against the actual diff so the user can judge
        # what content change will be written, not only which file is touched.
        result = self.prompt(
            {
                "kind": "edit",
                "summary": "XingCode wants to apply a file modification",
                "details": [f"target: {normalized_target}", "", diff_preview],
                "scope": normalized_target,
                "choices": [
                    {"key": "1", "label": "apply once", "decision": "allow_once"},
                    {"key": "2", "label": "allow this file in this turn", "decision": "allow_turn"},
                    {"key": "3", "label": "allow all edits in this turn", "decision": "allow_all_turn"},
                    {"key": "4", "label": "always allow this file", "decision": "allow_always"},
                    {"key": "5", "label": "reject once", "decision": "deny_once"},
                    {"key": "6", "label": "reject and send guidance to model", "decision": "deny_with_feedback"},
                    {"key": "7", "label": "always reject this file", "decision": "deny_always"},
                ],
            }
        )
        decision = result.get("decision")

        if decision == "allow_once":
            self.session_allowed_edits.add(normalized_target)
            return
        if decision == "allow_turn":
            self.turn_allowed_edits.add(normalized_target)
            return
        if decision == "allow_all_turn":
            self.turn_allow_all_edits = True
            return
        if decision == "allow_always":
            self.allowed_edit_patterns.add(normalized_target)
            return
        if decision == "deny_with_feedback":
            guidance = str(result.get("feedback", "")).strip()
            if guidance:
                raise RuntimeError(f"Edit denied: {normalized_target}\nUser guidance: {guidance}")
        if decision == "deny_always":
            self.denied_edit_patterns.add(normalized_target)
        else:
            self.session_denied_edits.add(normalized_target)

        raise RuntimeError(f"Edit denied: {normalized_target}")
