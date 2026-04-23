"""XingCode 外部集成层。"""

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
    "SkillSummary",
    "discover_skills",
    "extract_description",
    "install_skill",
    "load_skill",
    "remove_managed_skill",
]
