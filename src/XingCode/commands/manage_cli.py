from __future__ import annotations

from XingCode.integrations import discover_skills, install_skill, remove_managed_skill


def _print_usage() -> None:
    """打印 Phase 12 管理命令帮助。"""

    print(
        "XingCode management commands\n\n"
        "xingcode skills list [--project]\n"
        "xingcode skills add <path-to-skill-or-dir> [--name <name>] [--project]\n"
        "xingcode skills remove <name> [--project]"
    )


def _parse_scope(args: list[str]) -> tuple[str, list[str]]:
    """解析命令作用域；默认 user，可通过 --project 切到项目级。"""

    rest = list(args)
    if "--project" in rest:
        rest.remove("--project")
        return "project", rest
    return "user", rest


def _take_option(args: list[str], name: str) -> str | None:
    """提取一个带值选项，例如 --name demo。"""

    if name not in args:
        return None

    index = args.index(name)
    if index + 1 >= len(args):
        raise RuntimeError(f"Missing value for {name}")

    value = args[index + 1]
    del args[index : index + 2]
    return value


def _handle_skills_command(cwd: str, args: list[str]) -> bool:
    """处理 skills 子命令。"""

    if not args:
        _print_usage()
        return True

    subcommand, *rest_args = args
    scope, rest = _parse_scope(rest_args)

    if subcommand == "list":
        skills = discover_skills(cwd)
        if not skills:
            print("No skills discovered.")
            return True
        for skill in skills:
            print(f"{skill.name}: {skill.description} ({skill.path}) [{skill.source}]")
        return True

    if subcommand == "add":
        if not rest:
            raise RuntimeError("Missing skill source path.")
        source_path = rest.pop(0)
        name = _take_option(rest, "--name")
        if rest:
            raise RuntimeError(f"Unknown arguments: {' '.join(rest)}")
        result = install_skill(cwd, source_path, name=name, scope=scope)
        print(f"Installed skill {result['name']} at {result['targetPath']}")
        return True

    if subcommand == "remove":
        if not rest:
            raise RuntimeError("Missing skill name.")
        name = rest.pop(0)
        if rest:
            raise RuntimeError(f"Unknown arguments: {' '.join(rest)}")
        result = remove_managed_skill(cwd, name, scope=scope)
        if not result["removed"]:
            print(f"Skill {name} not found at {result['targetPath']}")
            return True
        print(f"Removed skill {name} from {result['targetPath']}")
        return True

    _print_usage()
    return True


def maybe_handle_management_command(cwd: str, argv: list[str]) -> bool:
    """尝试处理 management command；不是则返回 False。"""

    if not argv:
        return False

    category, *rest = argv
    if category == "skills":
        return _handle_skills_command(cwd, rest)
    if category == "help":
        _print_usage()
        return True
    return False
