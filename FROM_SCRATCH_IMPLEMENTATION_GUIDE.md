# MiniCode Python 从零模仿实现指南

## 文档目标

这份文档回答 3 个问题：

1. 如果你要从零模仿这个项目，推荐采用什么目录结构。
2. 你应该按什么顺序读原项目代码。
3. 你应该按什么顺序创建自己的文件，并一步步实现完整功能。

这份文档现在明确采用一个原则：

**可以优化目录结构，但不要打乱原项目真正的依赖顺序。**

也就是说，你完全可以在自己的项目里把目录设计得更清楚、更易维护；但在实现顺序上，仍然要遵守原项目的真实主链路：

- 先协议
- 再安全边界和核心工具
- 再 agent loop
- 再 prompt、配置、模型接入
- 再 headless / main 入口
- 再 history、session 这些可验证的持久化能力
- 再 skills、MCP、context、memory、observability 这些增强能力
- 最后再做 TUI 这层交互外壳

---

## 先回答你的问题：要不要优化目录结构

答案是：**要，而且建议从第一天就优化。**

原因很简单：

- 原仓库是一个“不断长出来”的项目，功能很多，但目录已经有些扁平。
- 你现在是从零写，不需要背历史包袱。
- 你如果一开始就把“核心执行层、工具层、适配器层、UI 层、存储层”分开，后面会轻松很多。

但要注意：

**你现在优化的是目录，不是架构行为。**

不要在第一阶段就重构原项目思想，不要提前发明自己的抽象体系。目录可以更清晰，但执行逻辑仍然要尽量贴着原项目。

---

## 推荐目录结构

我建议你不要直接照搬 `minicode/*.py` 的扁平布局，而是采用 `src` 布局，并把功能分层。

建议结构如下：

```text
your-agent/
├── pyproject.toml
├── README.md
├── docs/
│   └── FROM_SCRATCH_IMPLEMENTATION_GUIDE.md
├── src/
│   └── your_agent/
│       ├── __init__.py
│       ├── app/
│       │   ├── __init__.py
│       │   ├── main.py
│       │   ├── headless.py
│       │   └── install.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── types.py
│       │   ├── tooling.py
│       │   ├── agent_loop.py
│       │   ├── prompt.py
│       │   ├── context_manager.py
│       │   └── prompt_pipeline.py
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── mock_model.py
│       │   ├── model_registry.py
│       │   ├── anthropic_adapter.py
│       │   └── openai_adapter.py
│       ├── security/
│       │   ├── __init__.py
│       │   ├── workspace.py
│       │   ├── permissions.py
│       │   ├── file_review.py
│       │   └── safe_execution.py
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── read_file.py
│       │   ├── list_files.py
│       │   ├── write_file.py
│       │   ├── edit_file.py
│       │   ├── patch_file.py
│       │   ├── run_command.py
│       │   ├── ask_user.py
│       │   ├── grep_files.py
│       │   ├── git.py
│       │   ├── task.py
│       │   └── ...
│       ├── storage/
│       │   ├── __init__.py
│       │   ├── config.py
│       │   ├── history.py
│       │   ├── session.py
│       │   ├── memory.py
│       │   └── user_profile.py
│       ├── commands/
│       │   ├── __init__.py
│       │   ├── cli_commands.py
│       │   └── manage_cli.py
│       ├── integrations/
│       │   ├── __init__.py
│       │   ├── skills.py
│       │   └── mcp.py
│       ├── observability/
│       │   ├── __init__.py
│       │   ├── logging_config.py
│       │   ├── state.py
│       │   └── cost_tracker.py
│       └── ui/
│           ├── __init__.py
│           ├── tty_app.py
│           └── tui/
│               ├── __init__.py
│               ├── state.py
│               ├── types.py
│               ├── transcript.py
│               ├── input_parser.py
│               ├── navigation.py
│               ├── tool_lifecycle.py
│               ├── event_flow.py
│               ├── renderer.py
│               ├── screen.py
│               ├── chrome.py
│               ├── theme.py
│               ├── session_flow.py
│               ├── input_handler.py
│               ├── runtime_control.py
│               └── tool_helpers.py
└── tests/
    ├── unit/
    └── integration/
```

---

## 为什么这个目录结构更合适

### `app/`

只放启动和装配逻辑，不放核心算法。

### `core/`

只放 Agent 的内核协议和执行引擎。

### `adapters/`

专门放模型 provider 适配器，避免和 core 混在一起。

### `security/`

把路径解析、权限、diff 审批放在一起，这些本质上是“安全边界”。

### `tools/`

工具必须集中，不能散落在根目录。

### `storage/`

所有和磁盘持久化有关的能力放一起：config、history、session、memory、profile。

### `commands/`

本地 slash commands 和管理命令是“入口层附属逻辑”，不属于 core。

### `integrations/`

skills、MCP 都属于外部扩展能力，单独放。

### `observability/`

日志、成本、状态是观测层，不属于业务主链路。

### `ui/`

TTY 和 TUI 必须和核心执行分开，否则后期很难维护。

---

## 目录依赖规则

你自己的项目最好遵守下面这些依赖方向：

1. `core/` 不能依赖 `ui/`。
2. `core/` 不能依赖 `app/`。
3. `tools/` 可以依赖 `core/` 和 `security/`，但不能依赖 `ui/`。
4. `adapters/` 可以依赖 `core/`，但不能依赖 `ui/`。
5. `storage/` 尽量不要依赖 `ui/`。
6. `app/` 可以装配所有层。
7. `ui/` 可以依赖 `core/`、`tools/`、`storage/`、`commands/`，但没有任何人应该反向依赖 `ui/`。
8. `integrations/` 应当被看成附加能力，不要让 `core/` 强依赖它们。

如果你一直守住这几条，目录优化就不会变成“假优化”。

---

## 原仓库文件到你新目录的映射

下面这张映射表最重要，你后面每个阶段都要反复看。

- `minicode/types.py` -> `src/your_agent/core/types.py`
- `minicode/tooling.py` -> `src/your_agent/core/tooling.py`
- `minicode/agent_loop.py` -> `src/your_agent/core/agent_loop.py`
- `minicode/prompt.py` -> `src/your_agent/core/prompt.py`
- `minicode/context_manager.py` -> `src/your_agent/core/context_manager.py`
- `minicode/prompt_pipeline.py` -> `src/your_agent/core/prompt_pipeline.py`
- `minicode/mock_model.py` -> `src/your_agent/adapters/mock_model.py`
- `minicode/model_registry.py` -> `src/your_agent/adapters/model_registry.py`
- `minicode/anthropic_adapter.py` -> `src/your_agent/adapters/anthropic_adapter.py`
- `minicode/openai_adapter.py` -> `src/your_agent/adapters/openai_adapter.py`
- `minicode/workspace.py` -> `src/your_agent/security/workspace.py`
- `minicode/permissions.py` -> `src/your_agent/security/permissions.py`
- `minicode/file_review.py` -> `src/your_agent/security/file_review.py`
- `minicode/tools/*.py` -> `src/your_agent/tools/*.py`
- `minicode/config.py` -> `src/your_agent/storage/config.py`
- `minicode/history.py` -> `src/your_agent/storage/history.py`
- `minicode/session.py` -> `src/your_agent/storage/session.py`
- `minicode/memory.py` -> `src/your_agent/storage/memory.py`
- `minicode/user_profile.py` -> `src/your_agent/storage/user_profile.py`
- `minicode/cli_commands.py` -> `src/your_agent/commands/cli_commands.py`
- `minicode/manage_cli.py` -> `src/your_agent/commands/manage_cli.py`
- `minicode/skills.py` -> `src/your_agent/integrations/skills.py`
- `minicode/mcp.py` -> `src/your_agent/integrations/mcp.py`
- `minicode/state.py` -> `src/your_agent/observability/state.py`
- `minicode/cost_tracker.py` -> `src/your_agent/observability/cost_tracker.py`
- `minicode/logging_config.py` -> `src/your_agent/observability/logging_config.py`
- `minicode/headless.py` -> `src/your_agent/app/headless.py`
- `minicode/main.py` -> `src/your_agent/app/main.py`
- `minicode/install.py` -> `src/your_agent/app/install.py`
- `minicode/tty_app.py` -> `src/your_agent/ui/tty_app.py`
- `minicode/tui/*.py` -> `src/your_agent/ui/tui/*.py`

---

## 阅读原项目代码的顺序

不要从 `main.py` 开始读，也不要先读 `tty_app.py`。正确顺序如下。

### 第 1 轮：只看主链路

按这个顺序读：

1. `minicode/types.py`
2. `minicode/tooling.py`
3. `minicode/workspace.py`
4. `minicode/permissions.py`
5. `minicode/tools/read_file.py`
6. `minicode/tools/write_file.py`
7. `minicode/tools/run_command.py`
8. `minicode/tools/ask_user.py`
9. `minicode/mock_model.py`
10. `minicode/agent_loop.py`

这一轮的目的只有一个：

**在脑中跑通一轮 Agent 执行流程。**

### 第 2 轮：看模型和启动

按这个顺序读：

1. `minicode/prompt.py`
2. `minicode/model_registry.py`
3. `minicode/anthropic_adapter.py`
4. `minicode/openai_adapter.py`
5. `minicode/headless.py`
6. `minicode/config.py`
7. `minicode/history.py`
8. `minicode/main.py`

这一轮的目的：

**弄清系统如何真正启动，以及模型如何接入。**

### 第 3 轮：先看会话持久化

按这个顺序读：

1. `minicode/session.py`
2. `minicode/tui/session_flow.py`

这一轮的目的：

**先把“会话如何创建、保存、恢复、自动保存”看明白；这里看 `session_flow.py` 只是为了理解 session 未来怎样被 UI 消费，不代表现在就要先做 TUI。**

### 第 4 轮：看增强系统

按这个顺序读：

1. `minicode/skills.py`
2. `minicode/mcp.py`
3. `minicode/context_manager.py`
4. `minicode/memory.py`
5. `minicode/state.py`
6. `minicode/cost_tracker.py`
7. `minicode/user_profile.py`
8. `minicode/manage_cli.py`
9. `minicode/cli_commands.py`

这一轮的目的：

**理解完整产品体验是如何在主链路之外叠出来的。**

### 第 5 轮：最后看 TUI

按这个顺序读：

1. `minicode/tui/state.py`
2. `minicode/tui/types.py`
3. `minicode/tui/transcript.py`
4. `minicode/tui/input_parser.py`
5. `minicode/tui/navigation.py`
6. `minicode/tui/tool_lifecycle.py`
7. `minicode/tui/event_flow.py`
8. `minicode/tui/renderer.py`
9. `minicode/tui/screen.py`
10. `minicode/tui/chrome.py`
11. `minicode/tui/theme.py`
12. `minicode/tui/session_flow.py`
13. `minicode/tui/input_handler.py`
14. `minicode/tui/runtime_control.py`
15. `minicode/tui/tool_helpers.py`
16. `minicode/tty_app.py`

这一轮的目的：

**在 core、session、skills、MCP 等接口都稳定后，再理解全屏 TTY 是怎样把这些能力统一包起来的。**

---

## 一个非常重要的提醒：以源码为准，不以 README 为准

你模仿实现时，必须优先对齐源码，不要优先对齐 README。

原因是这个仓库里有一些“文档先行”的痕迹。例如：

- `pyproject.toml` 暴露了 `minicode-gateway` 和 `minicode-cron`
- `docker-compose.yml` 也声明了 `gateway` 和 `cron`
- 但当前源码里没有对应完整实现文件

所以你在自己项目里：

- 先实现源码真实存在的主链路
- 不要因为 README 写了什么，就提前补自己没看懂的外围功能

---

## 总实现原则

你整个开发过程都按这 7 条原则推进：

1. 每一阶段只解决一个层级的问题。
2. 先做最小闭环，再做增强版。
3. 先做 headless，再做 TTY/TUI。
4. 先做 mock model，再接真实 API。
5. 工具前先有权限系统。
6. 每一阶段结束前，先补测试，再进入下一阶段。
7. 对 XingCode 当前进度来说，TUI 放在最后收尾，等 skills、MCP、context、memory 稳定后再做。

---

## Phase 0：搭项目骨架，不写功能

### 本阶段目标

把你自己的工程骨架搭出来，先确定目录，而不是急着写逻辑。

### 需要创建的文件

- `pyproject.toml`
- `README.md`
- `src/your_agent/__init__.py`
- `src/your_agent/app/__init__.py`
- `src/your_agent/core/__init__.py`
- `src/your_agent/adapters/__init__.py`
- `src/your_agent/security/__init__.py`
- `src/your_agent/tools/__init__.py`
- `src/your_agent/storage/__init__.py`
- `src/your_agent/commands/__init__.py`
- `src/your_agent/integrations/__init__.py`
- `src/your_agent/observability/__init__.py`
- `src/your_agent/ui/__init__.py`
- `src/your_agent/ui/tui/__init__.py`
- `tests/unit/__init__.py`
- `tests/integration/__init__.py`
- `docs/FROM_SCRATCH_IMPLEMENTATION_GUIDE.md`

### 需要重点阅读/模仿的源码

- `pyproject.toml`
- `minicode/main.py`
- `minicode/headless.py`
- `minicode/tools/__init__.py`

### 本阶段要做的事

1. 确定你的包名，例如 `your_agent`。
2. 采用 `src` 布局，不要把包直接放在仓库根目录。
3. 建立上面那套空目录和空 `__init__.py`。
4. 在 `README.md` 里写下你的阶段目标和暂缓目标。

### 暂时不要做

- 不要写 TUI
- 不要接 API
- 不要做工具
- 不要做 session

### 本阶段验收标准

- 你的仓库目录已经稳定
- `python -c "import your_agent"` 能通过

---

## Phase 1：实现协议层

### 本阶段目标

定义整个系统的消息协议和工具协议。

### 需要创建的文件

- `src/your_agent/core/types.py`
- `src/your_agent/core/tooling.py`
- `tests/unit/test_types.py`
- `tests/unit/test_tooling.py`

### 需要重点阅读/模仿的源码

- `minicode/types.py`
- `minicode/tooling.py`
- `tests/test_agent_loop.py`
- `tests/test_tools.py`

### 本阶段要实现的内容

在 `core/types.py` 中先实现：

- `ChatMessage`
- `ToolCall`
- `StepDiagnostics`
- `AgentStep`
- `ModelAdapter`

在 `core/tooling.py` 中实现：

- `ToolResult`
- `ToolContext`
- `ToolDefinition`
- `ToolRegistry`

### 实现要求

1. 模型输出必须统一成 `assistant` 或 `tool_calls` 两种 `AgentStep`。
2. 工具注册必须统一成 `validator + run` 模式。
3. `ToolRegistry.find()` 必须是 O(1)。
4. `ToolRegistry.execute()` 必须吞掉工具异常并返回错误结果，而不是把进程炸掉。

### 暂时不要做

- 背景任务
- 并发工具执行
- 高级 metadata
- 大量输出智能截断

### 本阶段验收标准

- 你能注册一个假工具并成功执行
- 参数错误会返回 `ToolResult(ok=False, ...)`

---

## Phase 2：实现安全边界

### 本阶段目标

把路径解析、权限审批、diff 审批做出来。

### 需要创建的文件

- `src/your_agent/security/workspace.py`
- `src/your_agent/security/permissions.py`
- `src/your_agent/security/file_review.py`
- `tests/unit/test_permissions.py`
- `tests/unit/test_file_review.py`

### 需要重点阅读/模仿的源码

- `minicode/workspace.py`
- `minicode/permissions.py`
- `minicode/file_review.py`
- `tests/test_permissions.py`
- `tests/test_tools.py`

### 本阶段要实现的内容

1. `resolve_tool_path`
2. `PermissionManager.ensure_path_access`
3. `PermissionManager.ensure_command`
4. `build_unified_diff`
5. `PermissionManager.ensure_edit`

### 实现顺序

1. 先做 `workspace.py`
2. 再做 `permissions.py` 里的路径审批
3. 再做命令审批
4. 最后做文件编辑审批

### 实现要求

1. cwd 内路径默认允许。
2. cwd 外路径需要 prompt handler。
3. 没有 prompt handler 时直接拒绝。
4. 文件编辑必须显示 diff preview。
5. 命令审批和路径审批必须分开。

### 暂时不要做

- auto mode
- 风险等级系统
- 复杂 turn/session 永久权限模型

### 本阶段验收标准

- 所有需要读/写/执行命令的工具未来都能统一走安全边界

---

## Phase 3：实现最小工具集

### 本阶段目标

只实现主链路必需的工具，不做 30+ 工具。

### 需要创建的文件

- `src/your_agent/tools/read_file.py`
- `src/your_agent/tools/list_files.py`
- `src/your_agent/tools/write_file.py`
- `src/your_agent/tools/edit_file.py`
- `src/your_agent/tools/patch_file.py`
- `src/your_agent/tools/run_command.py`
- `src/your_agent/tools/ask_user.py`
- `src/your_agent/tools/__init__.py`
- `tests/unit/test_tools_read_write.py`
- `tests/unit/test_tools_run_command.py`
- `tests/unit/test_tools_registry.py`

### 需要重点阅读/模仿的源码

- `minicode/tools/read_file.py`
- `minicode/tools/list_files.py`
- `minicode/tools/write_file.py`
- `minicode/tools/edit_file.py`
- `minicode/tools/patch_file.py`
- `minicode/tools/run_command.py`
- `minicode/tools/ask_user.py`
- `minicode/tools/__init__.py`
- `tests/test_tools.py`

### 本阶段要实现的内容

#### 第一批

- `read_file`
- `list_files`
- `write_file`

#### 第二批

- `edit_file` 或 `patch_file`
- `run_command`
- `ask_user`

#### 第三批

- 在 `tools/__init__.py` 中组装最小 registry

### 实现要求

1. `read_file` 要支持 `offset + limit`。
2. `write_file` 要走 `file_review + ensure_edit`。
3. `run_command` 要支持 cwd、timeout、输出截断。
4. `ask_user` 要通过 `awaitUser=True` 终止本轮。

### 暂时不要做

- Git 工具
- Web 工具
- MCP 工具
- Code review 工具
- 批量文件工具

### 本阶段验收标准

- 你已经拥有一组足以支撑 Agent 主链路的最小工具集

---

## Phase 4：实现 Mock Model

### 本阶段目标

在不接真实 API 的前提下，打通“模型 -> 工具 -> 消息”的最小闭环。

### 需要创建的文件

- `src/your_agent/adapters/mock_model.py`
- `tests/unit/test_mock_model.py`

### 需要重点阅读/模仿的源码

- `minicode/mock_model.py`
- `tests/test_mock_model.py`
- `tests/test_agent_loop.py`

### 本阶段要实现的内容

1. 用户输入 `/read xxx` 时返回 `read_file` tool call。
2. 用户输入 `/cmd xxx` 时返回 `run_command` tool call。
3. 收到 `tool_result` 后，生成一条最简单的 assistant 总结。

### 实现要求

1. 不要让 mock model 太聪明。
2. 它的职责只是帮你联调，不是替代真实模型。

### 暂时不要做

- 真正自然语言理解
- streaming
- provider 判断

### 本阶段验收标准

- 在没有任何 API key 的情况下，你已经能调通完整工具链路

---

## Phase 5：实现 agent loop

### 本阶段目标

做出整个项目真正的执行引擎。

### 需要创建的文件

- `src/your_agent/core/agent_loop.py`
- `tests/unit/test_agent_loop.py`

### 需要重点阅读/模仿的源码

- `minicode/agent_loop.py`
- `tests/test_agent_loop.py`
- `minicode/types.py`
- `minicode/tooling.py`

### 本阶段要实现的内容

1. `run_agent_turn()`
2. assistant 分支处理
3. tool_calls 分支处理
4. tool result 回写 messages
5. `max_steps` 死循环保护

### 第一版的实现顺序

1. 先支持 `assistant` 直接结束
2. 再支持单个工具调用
3. 再支持多个工具调用
4. 再补 callback
5. 最后补空响应重试

### 暂时不要做

- 并发只读工具
- hooks
- store 状态更新
- 高级 diagnostics

### 本阶段验收标准

- 你已经完成整个 Agent 的主内核

---

## Phase 6：实现 prompt builder

### 本阶段目标

让系统可以稳定构造 system prompt。

### 需要创建的文件

- `src/your_agent/core/prompt.py`
- `tests/unit/test_prompt.py`

### 需要重点阅读/模仿的源码

- `minicode/prompt.py`
- `tests/test_prompt.py`

### 本阶段要实现的内容

1. 基础角色说明
2. cwd 注入
3. 权限摘要注入
4. 工具列表注入
5. 可选技能/MCP 摘要注入

### 实现要求

1. 第一版只要字符串拼接清楚即可。
2. 不要一开始就做复杂 PromptPipeline。

### 暂时不要做

- CLAUDE.md 读取
- 动态缓存
- 复杂治理规则大段落系统

### 本阶段验收标准

- `headless` 入口未来已经能构造一份完整 prompt

---

## Phase 7：实现配置和模型注册

### 本阶段目标

统一 runtime 配置，并为不同模型适配器做分发。

### 需要创建的文件

- `src/your_agent/storage/config.py`
- `src/your_agent/adapters/model_registry.py`
- `tests/unit/test_config.py`
- `tests/unit/test_model_registry.py`

### 需要重点阅读/模仿的源码

- `minicode/config.py`
- `minicode/model_registry.py`
- `tests/test_config.py`

### 本阶段要实现的内容

在 `storage/config.py` 中先做：

- `load_effective_settings`
- `load_runtime_config`
- `save_settings`
- 缺失配置时报错

在 `adapters/model_registry.py` 中做：

- provider detection
- `create_model_adapter`

### 实现要求

1. 第一版只支持最小配置。
2. 先支持 model、base_url、一个 API key。
3. `runtime` 字典应该稳定，后续 adapter 只消费它。

### 暂时不要做

- 配置诊断美化
- model 模糊提示
- mcp 合并逻辑
- 太复杂的兼容层

### 本阶段验收标准

- 你能通过 `runtime` 正确创建 mock / anthropic / openai adapter

---

## Phase 8：实现真实模型适配器

### 本阶段目标

把内核接到真实 LLM API。

### 需要创建的文件

- `src/your_agent/adapters/anthropic_adapter.py`
- `src/your_agent/adapters/openai_adapter.py`
- `tests/integration/test_anthropic_adapter.py`
- `tests/integration/test_openai_adapter.py`

### 需要重点阅读/模仿的源码

- `minicode/anthropic_adapter.py`
- `minicode/openai_adapter.py`
- `tests/test_anthropic_adapter.py`

### 本阶段要实现的内容

#### 先做 Anthropic

1. 内部消息 -> Anthropic messages
2. 工具定义 -> Anthropic tools
3. 非 streaming 请求
4. 解析 text 和 tool_use

#### 再做 OpenAI

1. 内部消息 -> Chat Completions 格式
2. 工具定义 -> function calling 格式
3. 解析 `tool_calls`
4. 解析普通回答

### 实现要求

1. 第一版先做非 streaming。
2. 成功后再补 streaming、retry、usage。

### 暂时不要做

- OpenRouter
- 自定义 endpoint 细节
- 全 provider 一次性统一抽象

### 本阶段验收标准

- mock model 和真实 adapter 都能接入同一个 agent loop

---

## Phase 9：先做 headless，再做 main

### 本阶段目标

先做最小可运行入口，再做正式 CLI 入口。

### 需要创建的文件

- `src/your_agent/app/headless.py`
- `src/your_agent/app/main.py`
- `src/your_agent/app/install.py`
- `tests/integration/test_headless.py`

### 需要重点阅读/模仿的源码

- `minicode/headless.py`
- `minicode/main.py`
- `minicode/install.py`

### 本阶段要实现的内容

#### 先做 `headless.py`

1. 接收 prompt
2. 读取 config
3. 创建 tools
4. 创建 permissions
5. 创建 model
6. 构造 system prompt
7. 调用 `run_agent_turn`

#### 再做 `main.py`

1. `--help`
2. `--validate-config`
3. `--install`
4. 最简单的 stdin/stdout 交互

### 暂时不要做

- 全屏 TTY
- transcript UI
- 复杂 slash 补全

### 本阶段验收标准

- 你已经可以在无 UI 条件下真实使用 Agent

---

## Phase 10：实现 history 和本地命令

### 本阶段目标

让 CLI 入口开始具备“产品感”。

### 需要创建的文件

- `src/your_agent/storage/history.py`
- `src/your_agent/commands/cli_commands.py`
- `tests/unit/test_history.py`
- `tests/unit/test_cli_commands.py`

### 需要重点阅读/模仿的源码

- `minicode/history.py`
- `minicode/cli_commands.py`
- `tests/test_cli_commands.py`

### 本阶段要实现的内容

1. recent history 读写
2. `/help`
3. `/tools`
4. `/config`
5. `/permissions`
6. `/history`
7. `/read`
8. `/cmd`

### 实现要求

1. 第一版的 slash commands 只做高频命令。
2. 不要一次实现原仓库全部命令。

### 本阶段验收标准

- 你的 CLI 已经不是纯 demo，而是能用的开发工具

---

## Phase 11：实现 session 持久化

### 本阶段目标

让程序具备保存、恢复、自动保存会话的能力。

### 需要创建的文件

- `src/your_agent/storage/session.py`
- `tests/unit/test_session.py`

### 需要重点阅读/模仿的源码

- `minicode/session.py`
- `tests/test_session.py`
- `minicode/tui/session_flow.py`

### 本阶段要实现的内容

#### 第一版

1. `SessionMetadata`
2. `SessionData`
3. `save_session`
4. `load_session`
5. `list_sessions`
6. `create_new_session`
7. `get_latest_session`

#### 第二版

8. `AutosaveManager`
9. delta save
10. consolidation

### 实现要求

1. 第一版可以先全量保存。
2. 全量保存稳定后，再补 delta 机制。

### 本阶段验收标准

- 你可以关掉程序再恢复会话

---

## 到 Phase 11 之后的顺序调整建议

如果 XingCode 已经开发到 Phase 11，那么建议把原来的 TUI 阶段后移到最后。

原因有 3 个：

1. TUI 是交互外壳，不是主链路本体；它不应该反过来驱动 core 设计。
2. `skills`、`MCP`、`context manager`、`memory` 会继续改变 prompt、工具装配、session 展示信息；如果先做 TUI，后面很容易反复修改 transcript、event flow、screen state。
3. 你现在已经有 `headless.py`、`main.py` 和 `session.py`，完全可以先把非 UI 能力做完，再用稳定接口一次性接到 TUI。

因此，后面的推荐顺序改成：

1. 先做 skills 和管理命令
2. 再做 MCP
3. 再做 context manager
4. 再做 memory
5. 再做 observability / user profile
6. 最后做 TUI

这属于**开发顺序调整**，不是**功能范围调整**。

你仍然是在模仿 MiniCode-Python，只是把最容易返工的 UI 外壳压到最后收尾。

---

## Phase 12：实现管理命令、skills 和工具装配增强

### 本阶段目标

补齐开发者管理能力和技能系统。

### 需要创建的文件

- `src/your_agent/commands/manage_cli.py`
- `src/your_agent/integrations/skills.py`
- `src/your_agent/tools/__init__.py` 增强版
- `tests/unit/test_skills.py`
- `tests/unit/test_manage_cli.py`

### 需要重点阅读/模仿的源码

- `minicode/manage_cli.py`
- `minicode/skills.py`
- `minicode/tools/__init__.py`
- `tests/test_skills.py`

### 本阶段要实现的内容

1. skill discovery
2. load skill
3. install/remove skill
4. 管理命令入口
5. 把 skills 注入工具注册和 prompt

### 实现要求

1. skills 先服务 headless 和 main，不要为了 TUI 先发明 UI 状态结构。
2. 先把发现、加载、安装、移除这条主链路做稳，再补更多管理命令。
3. tools 和 prompt 中的 skill 注入要复用同一份 discovery 结果。

### 本阶段验收标准

- 你可以发现 skill、加载 skill，并通过 CLI 管理它们

---

## Phase 13：实现 MCP

### 本阶段目标

让外部 MCP server 能被当成动态工具源接入系统。

### 需要创建的文件

- `src/your_agent/integrations/mcp.py`
- `tests/integration/test_mcp.py`

### 需要重点阅读/模仿的源码

- `minicode/mcp.py`
- `tests/test_mcp.py`

### 本阶段要实现的内容

#### 第一版

1. stdio client
2. 静态 server config
3. list tools
4. call tool

#### 第二版

5. resources
6. prompts
7. lazy init
8. 错误恢复

### 暂时不要做

- 一开始就做全部协议分支
- 一开始就做复杂缓存

### 本阶段验收标准

- MCP server 已经能作为普通工具源接进系统

---

## Phase 14：实现 context manager

### 本阶段目标

防止长会话把上下文打爆。

### 需要创建的文件

- `src/your_agent/core/context_manager.py`
- `src/your_agent/core/prompt_pipeline.py`
- `tests/unit/test_context_manager.py`

### 需要重点阅读/模仿的源码

- `minicode/context_manager.py`
- `minicode/prompt_pipeline.py`

### 本阶段要实现的内容

1. token 估算
2. message token 估算
3. context window tracking
4. compact 策略

### 实现要求

1. 第一版只要能保 system prompt + 最近消息。
2. 复杂的多层摘要可以后补。

### 本阶段验收标准

- 长会话不会直接失控

---

## Phase 15：实现 memory

### 本阶段目标

让 Agent 跨会话记住项目约定和历史决策。

### 需要创建的文件

- `src/your_agent/storage/memory.py`
- `tests/unit/test_memory.py`

### 需要重点阅读/模仿的源码

- `minicode/memory.py`

### 本阶段要实现的内容

#### 第一版

1. memory scopes
2. memory entry
3. 文件持久化
4. 简单搜索
5. prompt 注入

#### 第二版

6. TF-IDF
7. usage_count
8. recency bonus

### 本阶段验收标准

- 新会话能读取旧决策

---

## Phase 16：实现状态、成本、日志、用户画像

### 本阶段目标

补齐观测能力和个性化能力。

### 需要创建的文件

- `src/your_agent/observability/state.py`
- `src/your_agent/observability/cost_tracker.py`
- `src/your_agent/observability/logging_config.py`
- `src/your_agent/storage/user_profile.py`
- `tests/unit/test_state.py`
- `tests/unit/test_cost_tracker.py`
- `tests/unit/test_user_profile.py`

### 需要重点阅读/模仿的源码

- `minicode/state.py`
- `minicode/cost_tracker.py`
- `minicode/logging_config.py`
- `minicode/user_profile.py`
- `tests/test_new_features.py`

### 本阶段要实现的内容

1. store
2. app state
3. cost tracking
4. logging
5. user profile merge

### 本阶段验收标准

- 你已经拥有完整产品级辅助能力

---

## Phase 17：最后再做 TUI

### 本阶段目标

在前面的核心能力和增强能力都稳定后，把内核包上一层全屏终端 UI。

### 需要创建的文件

- `src/your_agent/ui/tty_app.py`
- `src/your_agent/ui/tui/state.py`
- `src/your_agent/ui/tui/types.py`
- `src/your_agent/ui/tui/transcript.py`
- `src/your_agent/ui/tui/input_parser.py`
- `src/your_agent/ui/tui/navigation.py`
- `src/your_agent/ui/tui/tool_lifecycle.py`
- `src/your_agent/ui/tui/event_flow.py`
- `src/your_agent/ui/tui/renderer.py`
- `src/your_agent/ui/tui/screen.py`
- `src/your_agent/ui/tui/chrome.py`
- `src/your_agent/ui/tui/theme.py`
- `src/your_agent/ui/tui/session_flow.py`
- `src/your_agent/ui/tui/input_handler.py`
- `src/your_agent/ui/tui/runtime_control.py`
- `src/your_agent/ui/tui/tool_helpers.py`
- `tests/unit/test_tty_app.py`
- `tests/unit/test_tui.py`

### 需要重点阅读/模仿的源码

- `minicode/tty_app.py`
- `minicode/tui/state.py`
- `minicode/tui/types.py`
- `minicode/tui/transcript.py`
- `minicode/tui/input_parser.py`
- `minicode/tui/navigation.py`
- `minicode/tui/tool_lifecycle.py`
- `minicode/tui/event_flow.py`
- `minicode/tui/renderer.py`
- `tests/test_tty_app.py`
- `tests/test_tui.py`

### 实现顺序

1. 先 `tui/state.py` 和 `tui/types.py`
2. 再 `tui/transcript.py`
3. 再 `tui/input_parser.py`
4. 再 `tui/navigation.py`
5. 再 `tui/tool_lifecycle.py`
6. 再 `tui/renderer.py`
7. 再 `tui/event_flow.py`
8. 再 `tui/session_flow.py`
9. 最后 `tty_app.py`

### 实现要求

1. 第一版先保证稳定，不要追求炫。
2. transcript 是中心，不是装饰。
3. TUI 只是外壳，不应该改变 core 的行为。
4. 这一阶段尽量只做“接线”和“渲染”，不要再回头改 core 协议。

### 暂时不要做

- 复杂动画
- 很重的性能优化
- 过早的 UI 主题系统

### 本阶段验收标准

- 用户已经可以通过全屏终端稳定使用 Agent

---

## 每个阶段结束后的测试顺序

建议按下面的节奏跑测试。

### 第一组：协议、安全、工具

- `tests/unit/test_types.py`
- `tests/unit/test_tooling.py`
- `tests/unit/test_permissions.py`
- `tests/unit/test_file_review.py`
- `tests/unit/test_tools_read_write.py`
- `tests/unit/test_tools_run_command.py`

### 第二组：执行内核

- `tests/unit/test_mock_model.py`
- `tests/unit/test_agent_loop.py`
- `tests/unit/test_prompt.py`
- `tests/unit/test_config.py`
- `tests/unit/test_model_registry.py`

### 第三组：启动和会话

- `tests/integration/test_headless.py`
- `tests/unit/test_history.py`
- `tests/unit/test_cli_commands.py`
- `tests/unit/test_session.py`

### 第四组：增强系统

- `tests/unit/test_manage_cli.py`
- `tests/unit/test_skills.py`
- `tests/integration/test_mcp.py`
- `tests/unit/test_context_manager.py`
- `tests/unit/test_memory.py`
- `tests/unit/test_state.py`
- `tests/unit/test_cost_tracker.py`
- `tests/unit/test_user_profile.py`

### 第五组：UI 收尾

- `tests/unit/test_tty_app.py`
- `tests/unit/test_tui.py`

---

## 推荐开发节奏

### 第 1 周

完成：

- Phase 0
- Phase 1
- Phase 2
- Phase 3
- Phase 4
- Phase 5

目标：

- 拥有可运行内核

### 第 2 周

完成：

- Phase 6
- Phase 7
- Phase 8
- Phase 9
- Phase 10

目标：

- 拥有真实可用的 CLI/headless 工具

### 第 3 周

完成：

- Phase 11
- Phase 12
- Phase 13

目标：

- 拥有会话、skills 和 MCP 基础扩展能力

### 第 4 周

完成：

- Phase 14
- Phase 15
- Phase 16

目标：

- 拥有 context、memory、observability 的增强链路

### 第 5 周及以后

完成：

- Phase 17

目标：

- 最后收尾 TUI，补齐完整交互体验

---

## 你最容易犯的 7 个错误

1. 在 session、skills、MCP 还没稳定时就先写 TUI。
2. 一上来就接真实 API。
3. 一上来就实现全部工具。
4. 把权限系统放到最后。
5. 看到 README 的功能就先实现，而不是先看源码。
6. 没有稳定目录结构就开始大写特写。
7. 每一阶段不补测试就往后走。

---

## 最终完成判据

### 最小可用版

你至少要完成这些：

- `core/types.py`
- `core/tooling.py`
- `security/workspace.py`
- `security/permissions.py`
- `security/file_review.py`
- `tools/read_file.py`
- `tools/write_file.py`
- `tools/run_command.py`
- `tools/ask_user.py`
- `adapters/mock_model.py`
- `core/agent_loop.py`
- `core/prompt.py`
- `storage/config.py`
- `adapters/model_registry.py`
- `adapters/anthropic_adapter.py` 或 `adapters/openai_adapter.py`
- `app/headless.py`
- `app/main.py`

### 完整版

你再继续完成这些：

- `storage/session.py`
- `commands/manage_cli.py`
- `integrations/skills.py`
- `integrations/mcp.py`
- `core/context_manager.py`
- `storage/memory.py`
- `observability/state.py`
- `observability/cost_tracker.py`
- `observability/logging_config.py`
- `storage/user_profile.py`
- `ui/tty_app.py`
- `ui/tui/*`

---

## 最后一句话

如果你严格照这份文档走，请永远记住：

**你现在优化的是目录，不是执行顺序；你现在模仿的是主链路，不是 README 里的全部梦想。**

所以最稳的路径永远是：

**先建干净目录，再做协议，再做工具和权限，再做 agent loop，再做模型和入口，再做 session 和各类增强能力，最后再用 TUI 收尾。**
