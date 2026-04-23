# XingCode

XingCode 是一个用 Python 逐步复现的轻量级终端 Coding Agent，参考项目是 MiniCode Python。

这个项目的目标不是一次性写出一个复杂框架，而是按阶段拆解并实现一个终端编程助手的核心能力：理解项目、读取文件、修改代码、运行命令、保存会话、加载 skills、接入 MCP 工具，并在长会话中管理模型上下文长度。


## 当前状态

XingCode 当前已经实现到从零复现计划的 Phase 14。

已经实现的能力包括：

- Agent 核心协议和主循环
- 工具注册表和内置工具
- 工作区路径安全检查和权限控制
- 文件读取、写入、编辑、patch 工具
- 本地命令执行工具
- 用于本地测试的 Mock 模型适配器
- Anthropic 模型适配器
- OpenAI 兼容模型适配器
- 运行时配置加载
- Headless 单轮运行模式
- 交互式 CLI 模式
- `/help`、`/tools`、`/read`、`/cmd` 等本地 slash 命令
- 输入历史和可恢复的 session 保存
- skill 发现和 `load_skill` 工具
- MCP server 接入，并作为普通工具暴露给 Agent
- 长会话 context manager

暂未实现的能力：

- 完整 TUI 界面
- 跨会话 memory 系统
- 对压缩上下文的高级语义摘要

## 为什么做这个项目

XingCode 不是为了重新发明一套全新的 Agent 架构。

它的目标是：在保留 Claude Code 核心思想的基础上，用更清晰的目录结构和更适合学习的方式，一步一步复现一个终端 Coding Agent。

当前代码按功能分层：

- `core/`：Agent 协议、prompt、context manager、主循环
- `tools/`：暴露给模型调用的本地工具
- `security/`：路径安全和权限边界
- `adapters/`：不同模型服务商的适配器
- `storage/`：配置、历史记录、session 持久化
- `integrations/`：skills 和 MCP 集成
- `app/`：CLI 和 headless 入口

所以这个项目既可以作为一个可运行的终端助手，也可以作为学习 Coding Agent 内部实现的参考项目。

## 快速开始

需要 Python 3.11 或更高版本。

```bash
git clone <your-repo-url>
cd XingCode
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -q
```

也可以使用 conda：

```bash
conda create -n xingcode python=3.11 -y
conda activate xingcode
python -m pip install -e ".[dev]"
python -m pytest -q
```

## 配置

XingCode 会从下面几个地方读取配置：

- 全局配置：`~/.xingcode/settings.json`
- 项目配置：`.xingcode/settings.json`
- 环境变量

环境变量优先级最高。

### Mock 模式

Mock 模式不需要 API Key，适合本地开发和测试。

```bash
export XINGCODE_MODEL=mock
python -m XingCode.app.main "hello"
```

### OpenAI 兼容模式

```bash
export XINGCODE_MODEL=gpt-4o-mini
export XINGCODE_PROVIDER=openai
export XINGCODE_API_KEY=your_api_key
python -m XingCode.app.main "解释这个项目结构"
```

### Anthropic 模式

```bash
export XINGCODE_MODEL=claude-sonnet-4-20250514
export XINGCODE_PROVIDER=anthropic
export XINGCODE_API_KEY=your_api_key
python -m XingCode.app.main "检查当前项目结构"
```

也可以把配置写入 `~/.xingcode/settings.json`：

```json
{
  "model": "gpt-4o-mini",
  "provider": "openai",
  "apiKey": "your_api_key"
}
```

## 使用方式

### 单轮运行

```bash
python -m XingCode.app.main "总结这个项目"
```

### Headless 模式

```bash
python -m XingCode.app.headless "列出主要模块"
```

### 交互式 CLI

```bash
python -m XingCode.app.main
```

进入后可以直接输入自然语言请求：

```text
xingcode> 阅读 README 并解释当前功能
xingcode> 找到 session 是在哪里保存的
xingcode> 运行单元测试
```

### 本地 Slash 命令

交互模式中支持：

```text
/help
/tools
/skills
/config
/permissions
/history
/read README.md
/cmd pytest -q
/exit
```

其中 `/read` 和 `/cmd` 会直接执行本地工具，不经过模型推理。

## 内置工具

默认工具注册表当前包含：

- `ask_user`
- `load_skill`
- `list_files`
- `read_file`
- `write_file`
- `edit_file`
- `patch_file`
- `run_command`
- 配置 MCP 后动态接入的 MCP 工具

所有工具都通过统一的 `ToolRegistry` 执行，文件和命令相关操作会经过工作区安全检查和权限层。

## Session 和历史记录

XingCode 会把会话状态保存在 `~/.xingcode/` 下。

当前支持：

- 最近输入历史
- session 完整快照
- delta 增量保存
- 恢复最近 session
- 恢复指定 session

常用命令：

```bash
python -m XingCode.app.main --list-sessions
python -m XingCode.app.main --resume
python -m XingCode.app.main --resume <SESSION_ID>
```

## Skills

XingCode 可以从下面这些位置发现 skills：

- `~/.xingcode/skills/<name>/SKILL.md`
- `.xingcode/skills/<name>/SKILL.md`
- `~/.claude/skills/<name>/SKILL.md`
- `.claude/skills/<name>/SKILL.md`

发现的 skills 会被注入 system prompt，也可以通过 `load_skill` 工具加载完整内容。

## MCP 集成

全局配置或项目配置中可以写入 `mcpServers`。

配置后，XingCode 会启动启用的 MCP server，并把 MCP tools 暴露到普通工具注册表中。

示例配置结构：

```json
{
  "mcpServers": {
    "demo": {
      "command": "python",
      "args": ["tests/fixtures/fake_mcp_server.py"],
      "protocol": "newline-json",
      "enabled": true
    }
  }
}
```

## 上下文管理

长会话可能会超过模型的 context window。XingCode 现在实现了第一版 context manager，会在每次调用模型前检查上下文长度。

当前策略包括：

- 估算文本和消息 token
- 统计当前上下文窗口使用量
- 接近模型上限时触发压缩
- 永远保留 system prompt
- 丢弃价值较低的 progress 消息
- 优先保留最近消息
- 对超长消息保留头尾并截断中间内容

当前版本不会调用 LLM 来总结旧消息，而是使用可预测的本地压缩策略。

## 开发

运行全部测试：

```bash
python -m pytest -q
```

运行单个测试文件：

```bash
python -m pytest tests/unit/test_context_manager.py -q
```

校验配置：

```bash
python -m XingCode.app.main --validate-config
```

## 项目结构

```text
src/XingCode/
├── adapters/       # 模型服务商适配器
├── app/            # CLI 和 headless 入口
├── commands/       # 本地 slash 命令
├── core/           # Agent loop、prompt、context manager、协议
├── integrations/   # Skills 和 MCP
├── security/       # 工作区和权限边界
├── storage/        # 配置、历史记录、session
└── tools/          # 内置工具
```

## License

暂未选择许可证。
