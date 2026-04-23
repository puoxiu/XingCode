"""XingCode 外部集成层。"""

from XingCode.integrations.mcp import McpServerSummary, StdioMcpClient, create_mcp_backed_tools
from XingCode.integrations.skills import (
    LoadedSkill,
    SkillSummary,
    discover_skills,
    extract_description,
    install_skill,
    load_skill,
    remove_managed_skill,
)

__all__ = [
    "LoadedSkill",
    "McpServerSummary",
    "SkillSummary",
    "StdioMcpClient",
    "create_mcp_backed_tools",
    "discover_skills",
    "extract_description",
    "install_skill",
    "load_skill",
    "remove_managed_skill",
]
