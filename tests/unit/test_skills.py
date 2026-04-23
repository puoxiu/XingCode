from __future__ import annotations

from pathlib import Path

from XingCode.integrations import discover_skills, install_skill, load_skill, remove_managed_skill
from XingCode.tools import create_default_tool_registry


def test_discover_skills_prefers_project_root(tmp_path: Path, monkeypatch) -> None:
    """同名 skill 同时出现在 project/user 时，应优先选择 project。"""

    project_skill = tmp_path / ".xingcode" / "skills" / "demo" / "SKILL.md"
    project_skill.parent.mkdir(parents=True)
    project_skill.write_text("# Demo\n\nProject description\n", encoding="utf-8")

    user_home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(user_home))
    monkeypatch.setenv("USERPROFILE", str(user_home))
    user_skill = user_home / ".xingcode" / "skills" / "demo" / "SKILL.md"
    user_skill.parent.mkdir(parents=True)
    user_skill.write_text("# Demo\n\nUser description\n", encoding="utf-8")

    skills = discover_skills(tmp_path)
    loaded = load_skill(tmp_path, "demo")

    assert len(skills) == 1
    assert skills[0].description == "Project description"
    assert loaded is not None
    assert loaded.content.startswith("# Demo")
    assert loaded.source == "project"


def test_install_and_remove_managed_skill_in_user_scope(tmp_path: Path, monkeypatch) -> None:
    """install/remove 应能在用户级 .xingcode/skills 下完成闭环。"""

    user_home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(user_home))
    monkeypatch.setenv("USERPROFILE", str(user_home))

    source_dir = tmp_path / "source-skill"
    source_dir.mkdir()
    (source_dir / "SKILL.md").write_text("# Demo\n\nInstalled description\n", encoding="utf-8")

    result = install_skill(tmp_path, str(source_dir))
    target = user_home / ".xingcode" / "skills" / "source-skill" / "SKILL.md"

    assert result["name"] == "source-skill"
    assert target.exists()

    removed = remove_managed_skill(tmp_path, "source-skill")

    assert removed == {"removed": True, "targetPath": str(target.parent)}
    assert not target.parent.exists()


def test_default_tool_registry_exposes_discovered_skills(tmp_path: Path) -> None:
    """增强版 registry 应携带 skills metadata，供 prompt 和本地命令复用。"""

    skill_file = tmp_path / ".xingcode" / "skills" / "demo" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text("# Demo\n\nRegistry description\n", encoding="utf-8")

    registry = create_default_tool_registry(str(tmp_path))
    skills = registry.get_skills()

    assert len(skills) == 1
    assert skills[0]["name"] == "demo"
    assert skills[0]["description"] == "Registry description"
    assert registry.build_prompt_extras()["skills"][0]["source"] == "project"
