"""Minimal toolset for the XingCode main execution path."""

from dataclasses import asdict

from XingCode.core.tooling import ToolRegistry
from XingCode.integrations import discover_skills
from XingCode.tools.ask_user import ask_user_tool
from XingCode.tools.edit_file import edit_file_tool
from XingCode.tools.list_files import list_files_tool
from XingCode.tools.load_skill import create_load_skill_tool
from XingCode.tools.patch_file import patch_file_tool
from XingCode.tools.read_file import read_file_tool
from XingCode.tools.run_command import run_command_tool
from XingCode.tools.write_file import write_file_tool


def create_default_tool_registry(cwd: str, runtime: dict | None = None) -> ToolRegistry:
    """Assemble the minimal Phase 3 registry used by the main agent path."""

    _ = (cwd, runtime)
    skills = [asdict(skill) for skill in discover_skills(cwd)]
    return ToolRegistry(
        [
            ask_user_tool,
            create_load_skill_tool(cwd),
            list_files_tool,
            read_file_tool,
            write_file_tool,
            edit_file_tool,
            patch_file_tool,
            run_command_tool,
        ],
        skills=skills,
    )


__all__ = [
    "ask_user_tool",
    "create_default_tool_registry",
    "create_load_skill_tool",
    "edit_file_tool",
    "list_files_tool",
    "patch_file_tool",
    "read_file_tool",
    "run_command_tool",
    "write_file_tool",
]
