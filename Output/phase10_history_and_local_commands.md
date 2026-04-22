# Phase 10：history 和本地命令实现说明

## 本次实现了什么

本次按 `FROM_SCRATCH_IMPLEMENTATION_GUIDE.md` 的 Phase 10 要求，完成了下面两块能力：

1. 最近输入历史的读写与展示。
2. CLI 本地 slash 命令层，包括：
   - `/help`
   - `/tools`
   - `/config`
   - `/permissions`
   - `/history`
   - `/read <path>`
   - `/cmd [cwd::]<command>`

这一步的目标是让 XingCode 的 CLI 不再只是“把输入扔给模型”的 demo，而是开始具备可直接使用的开发工具感。

## 这次新增/修改的关键文件

- `src/XingCode/storage/history.py`
  - 负责最近历史的加载、保存、裁剪、格式化。
- `src/XingCode/commands/cli_commands.py`
  - 负责本地命令注册、帮助输出、本地命令处理、工具快捷命令解析。
- `src/XingCode/app/main.py`
  - 在交互式 CLI 中接入 history 与本地命令层。
- `src/XingCode/app/headless.py`
  - 在 headless 模式中优先处理本地命令，使 `/help`、`/read`、`/cmd` 不依赖 runtime 配置。

## 具体行为说明

### 1. history 的行为

- 历史文件路径：`~/.xingcode/history.json`
- 存储格式：`{"entries": [...]}`
- 最多保留最近 `200` 条输入
- 连续重复输入不会重复写入
- `/history` 会显示最近历史，并保留原始序号

### 2. 本地命令层的行为

本地命令会先于 Agent 主链路执行：

- 如果输入是 `/help`、`/tools`、`/config`、`/permissions`、`/history`
  - 直接在本地返回文本结果
  - 不进入模型推理
- 如果输入是 `/read <path>`
  - 直接调用 `read_file` 工具
- 如果输入是 `/cmd [cwd::]<command>`
  - 直接调用 `run_command` 工具
- 如果输入是未知 slash 命令
  - 返回命令建议或提示用户用 `/help`
- 如果输入是普通自然语言
  - 继续进入 `build_system_prompt -> run_agent_turn` 的主链路

## 示例流程

### 示例 1：输入 `/history`

执行流程：

1. `src/XingCode/app/main.py` 读取用户输入
2. `remember_history_entry()` 把本次输入写入最近历史
3. `handle_cli_input()` 识别出这是本地命令
4. `try_handle_local_command()` 命中 `/history`
5. `format_history_entries()` 把最近记录格式化成文本
6. CLI 直接打印结果，不进入 Agent

### 示例 2：输入 `/read README.md`

执行流程：

1. `main.py` 或 `headless.py` 接收输入
2. `handle_cli_input()` 先尝试本地命令
3. `try_execute_local_tool_command()` 识别 `/read`
4. `parse_local_tool_shortcut()` 解析出：
   - `toolName = read_file`
   - `input = {"path": "README.md"}`
5. 通过 `ToolRegistry.execute()` 执行 `read_file`
6. `src/XingCode/tools/read_file.py` 完成安全路径解析与文件读取
7. CLI 直接输出文件内容结果

### 示例 3：输入 `/cmd src::git status`

执行流程：

1. `parse_local_tool_shortcut()` 解析出：
   - `toolName = run_command`
   - `input = {"command": "git status", "cwd": "src"}`
2. `ToolRegistry.execute()` 调用 `run_command`
3. `src/XingCode/tools/run_command.py`
   - 解析命令和参数
   - 校验命令工作目录
   - 根据权限规则判断是否需要审批
   - 执行命令并返回输出
4. CLI 直接打印命令结果

## 这一步为什么这样实现

这次严格遵守了当前阶段要求，没有提前实现下面这些后续能力：

- session 持久化
- TTY/TUI 历史导航
- 更复杂的 slash 命令体系
- skills / MCP / 管理命令增强

也就是说，这一版只补“高频本地命令 + 最近历史”这条最短主链路，尽量贴着参考项目当前阶段的范围。

## 验证结果

本次新增并通过了 history、cli_commands、headless 相关测试。

本地执行：

```bash
pytest -q
```

结果：

```text
92 passed in 1.14s
```
