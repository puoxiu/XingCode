from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class SkillSummary:
    """skill 摘要：用于列表展示和 prompt 注入。"""

    name: str
    description: str
    path: str
    source: str


@dataclass(slots=True)
class LoadedSkill(SkillSummary):
    """完整加载后的 skill，额外携带 SKILL.md 原文。"""

    content: str


def extract_description(markdown: str) -> str:
    """从 SKILL.md 中抽取第一段非标题描述。"""

    normalized = markdown.replace("\r\n", "\n")
    paragraphs = [block.strip() for block in normalized.split("\n\n") if block.strip()]
    for block in paragraphs:
        if block.startswith("#"):
            continue
        for line in [part.strip() for part in block.split("\n")]:
            if line and not line.startswith("#"):
                return line.replace("`", "")
    return "No description provided."


def _home_dir() -> Path:
    """返回当前用户 home 目录。"""

    # 测试和 CLI 场景都更希望尊重显式设置的 HOME / USERPROFILE。
    for env_name in ("HOME", "USERPROFILE"):
        value = os.environ.get(env_name)
        if value:
            return Path(value)
    return Path.home()


def _skill_roots(cwd: str | Path) -> list[tuple[Path, str]]:
    """定义 XingCode 的 skill 搜索顺序。"""

    base = Path(cwd)
    home = _home_dir()
    return [
        (base / ".xingcode" / "skills", "project"),
        (home / ".xingcode" / "skills", "user"),
        (base / ".claude" / "skills", "compat_project"),
        (home / ".claude" / "skills", "compat_user"),
    ]


def _list_skill_dirs(root: Path, source: str) -> list[LoadedSkill]:
    """扫描某个根目录下所有合法的 skill 目录。"""

    if not root.exists():
        return []

    results: list[LoadedSkill] = []
    for entry in sorted(root.iterdir(), key=lambda item: item.name):
        try:
            if not entry.is_dir():
                continue
        except OSError:
            continue

        skill_path = entry / "SKILL.md"
        if not skill_path.exists():
            continue

        try:
            content = skill_path.read_text(encoding="utf-8")
        except OSError:
            continue

        results.append(
            LoadedSkill(
                name=entry.name,
                description=extract_description(content),
                path=str(skill_path),
                source=source,
                content=content,
            )
        )
    return results


def discover_skills(cwd: str | Path) -> list[SkillSummary]:
    """按 project > user > compat 的顺序发现 skills。"""

    by_name: dict[str, LoadedSkill] = {}
    for root, source in _skill_roots(cwd):
        for skill in _list_skill_dirs(root, source):
            by_name.setdefault(skill.name, skill)

    return [
        SkillSummary(
            name=skill.name,
            description=skill.description,
            path=skill.path,
            source=skill.source,
        )
        for _, skill in sorted(by_name.items(), key=lambda item: item[0])
    ]


def load_skill(cwd: str | Path, name: str) -> LoadedSkill | None:
    """按 discover 的同样顺序加载一个指定 skill。"""

    normalized_name = name.strip()
    if not normalized_name:
        return None

    for root, source in _skill_roots(cwd):
        skill_path = root / normalized_name / "SKILL.md"
        if not skill_path.exists():
            continue

        content = skill_path.read_text(encoding="utf-8")
        return LoadedSkill(
            name=normalized_name,
            description=extract_description(content),
            path=str(skill_path),
            source=source,
            content=content,
        )
    return None


def _managed_skill_root(scope: str, cwd: str | Path) -> Path:
    """返回 XingCode 自己管理的 skill 安装目录。"""

    if scope == "project":
        return Path(cwd) / ".xingcode" / "skills"
    return _home_dir() / ".xingcode" / "skills"


def install_skill(
    cwd: str | Path,
    source_path: str,
    name: str | None = None,
    scope: str = "user",
) -> dict[str, str]:
    """把一个外部 SKILL.md 安装到 XingCode 的托管目录中。"""

    source = Path(source_path)
    if not source.is_absolute():
        source = Path(cwd) / source

    if source.is_dir():
        skill_file = source / "SKILL.md"
        inferred_name = source.name
    else:
        skill_file = source if source.name == "SKILL.md" else source / "SKILL.md"
        inferred_name = skill_file.parent.name

    if not skill_file.exists():
        raise RuntimeError(f"No SKILL.md found in {source}")

    skill_name = (name or inferred_name).strip()
    if not skill_name:
        raise RuntimeError("Skill name cannot be empty.")

    target_dir = _managed_skill_root(scope, cwd) / skill_name
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(skill_file, target_dir / "SKILL.md")
    return {"name": skill_name, "targetPath": str(target_dir / "SKILL.md")}


def remove_managed_skill(cwd: str | Path, name: str, scope: str = "user") -> dict[str, object]:
    """从 XingCode 托管目录中移除一个已安装的 skill。"""

    normalized_name = name.strip()
    target_path = _managed_skill_root(scope, cwd) / normalized_name
    if not target_path.exists():
        return {"removed": False, "targetPath": str(target_path)}

    shutil.rmtree(target_path)
    return {"removed": True, "targetPath": str(target_path)}
