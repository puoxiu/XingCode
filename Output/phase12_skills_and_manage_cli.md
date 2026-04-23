# Phase 12：skills 与管理命令实现说明

## 本次实现了什么

这次完成的是 `FROM_SCRATCH_IMPLEMENTATION_GUIDE.md` 里的：

- `Phase 12：实现管理命令、skills 和工具装配增强`

本次补齐了 5 件事：

1. skill discovery
2. load skill
3. install/remove skill
4. 管理命令入口
5. 把 skills 注入工具注册和 prompt

## 新增和修改的关键代码

### 1. `src/XingCode/integrations/skills.py`

这里实现了 skills 系统的核心能力：

- `SkillSummary`
- `LoadedSkill`
- `extract_description()`
- `discover_skills()`
- `load_skill()`
- `install_skill()`
- `remove_managed_skill()`

当前搜索顺序是：

1. 项目级 `.xingcode/skills`
2. 用户级 `~/.xingcode/skills`
3. 兼容项目级 `.claude/skills`
4. 兼容用户级 `~/.claude/skills`

同名 skill 冲突时，优先保留前面先发现的，也就是：

- project 优先于 user

### 2. `src/XingCode/commands/manage_cli.py`

这里实现了 Phase 12 的管理命令入口。

现在支持：

- `skills list`
- `skills add <path>`
- `skills remove <name>`
- `--project`
- `--name`

也就是说，现在可以直接通过命令行管理 skills，而不是只能手动拷贝文件。

### 3. `src/XingCode/core/tooling.py`

`ToolRegistry` 这次不再只保存工具列表，也开始保存扩展 metadata：

- `skills`
- `mcp_servers`

虽然这次还没做 MCP，但接口已经留好，并且是当前 Phase 12 需要的最小形态。

新增了：

- `get_skills()`
- `get_mcp_servers()`
- `build_prompt_extras()`

这样后面 prompt、本地命令、session 都可以复用同一份 registry 数据。

### 4. `src/XingCode/tools/__init__.py`

创建默认工具注册表时，现在会先发现当前工作区可用的 skills，并把它们挂到 registry 上。

也就是说，skills 的注入点已经从“孤立模块”变成了“主运行链路的一部分”。

### 5. prompt / CLI / session 接线

这次还把 skills 真正接进了运行流程：

- `core/prompt.py`
  - `build_system_prompt()` 现在会优先读取 `ToolRegistry` 自带的 metadata
- `commands/cli_commands.py`
  - 新增 `/skills`
- `app/main.py`
  - 新增 management command 入口
  - session 同步时会保存当前 skills 摘要
- `app/headless.py`
  - 本地 `/skills` 不依赖 runtime 配置
  - 保存 session 时也会记录 skills 摘要

## 一个实际流程例子

假设项目目录里有：

```text
.xingcode/skills/code-review/SKILL.md
```

当用户运行 XingCode 时，流程会变成：

1. `create_default_tool_registry(cwd)` 先调用 `discover_skills(cwd)`
2. 发现 `code-review` skill
3. skill 摘要被挂到 `ToolRegistry`
4. `build_system_prompt()` 从 registry 中读取 skills
5. system prompt 里出现：
   - `Available skills:`
   - `code-review: ...`
6. 如果用户输入 `/skills`
   - `cli_commands.py` 会直接从 registry 输出 skill 列表
7. 如果保存 session
   - `session.skills` 也会同步记录这份摘要

## 这次实现的意义

这一步的核心不是“多了几个命令”，而是：

**skills 现在已经从磁盘目录，正式接入了 XingCode 的主运行链路。**

也就是说，现在 skills 已经同时影响：

- 管理命令
- 本地 slash 命令
- tool registry
- system prompt
- session 持久化

这正是 Phase 12 要完成的事情。
