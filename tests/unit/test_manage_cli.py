from __future__ import annotations

from pathlib import Path

from XingCode.commands.manage_cli import maybe_handle_management_command


def test_manage_cli_lists_skills(tmp_path: Path, monkeypatch, capsys) -> None:
    """`skills list` 应列出当前能发现的 skills。"""

    user_home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(user_home))
    monkeypatch.setenv("USERPROFILE", str(user_home))

    skill_file = tmp_path / ".xingcode" / "skills" / "demo" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text("# Demo\n\nList description\n", encoding="utf-8")

    handled = maybe_handle_management_command(str(tmp_path), ["skills", "list"])
    captured = capsys.readouterr()

    assert handled is True
    assert "demo: List description" in captured.out


def test_manage_cli_can_add_and_remove_project_skill(tmp_path: Path, capsys) -> None:
    """`skills add/remove --project` 应在项目目录里完成安装和移除。"""

    source_dir = tmp_path / "source-skill"
    source_dir.mkdir()
    (source_dir / "SKILL.md").write_text("# Demo\n\nProject managed description\n", encoding="utf-8")

    add_handled = maybe_handle_management_command(
        str(tmp_path),
        ["skills", "add", str(source_dir), "--project", "--name", "demo-skill"],
    )
    add_output = capsys.readouterr().out

    target = tmp_path / ".xingcode" / "skills" / "demo-skill" / "SKILL.md"
    remove_handled = maybe_handle_management_command(
        str(tmp_path),
        ["skills", "remove", "demo-skill", "--project"],
    )
    remove_output = capsys.readouterr().out

    assert add_handled is True
    assert "Installed skill demo-skill" in add_output
    assert remove_handled is True
    assert "Removed skill demo-skill" in remove_output
    assert not target.exists()
