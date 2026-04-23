# Phase 12 之后的开发顺序重排说明

## 这次改了什么

这次没有实现新的运行时代码，改的是开发计划文档：

- 更新了 `XingCode/FROM_SCRATCH_IMPLEMENTATION_GUIDE.md`
- 把原来的 `Phase 12：TUI` 后移到最后
- 把 `skills`、`MCP`、`context manager`、`memory`、`observability` 前移到 TUI 之前
- 同步调整了阅读顺序、测试顺序、推荐开发节奏和最终完成判据

新的阶段顺序变成：

1. Phase 12：管理命令、skills、工具装配增强
2. Phase 13：MCP
3. Phase 14：context manager
4. Phase 15：memory
5. Phase 16：状态、成本、日志、用户画像
6. Phase 17：最后做 TUI

## 为什么这样更合适

核心判断是：

**现在 XingCode 已经做到 Phase 11，接下来先做 skills / MCP / memory，比先做 TUI 更稳。**

原因如下：

1. TUI 是 UI 外壳，不是主链路本体。
2. `skills`、`MCP`、`context manager`、`memory` 会继续影响 prompt、tool registry、session 展示数据。
3. 如果现在先做 TUI，后面这些能力一接进来，`transcript`、`event_flow`、`screen state` 很容易反复返工。
4. 当前项目已经有 `headless.py`、`main.py`、`session.py`，已经足够支撑后续非 UI 功能开发和验证。

所以这次调整的是：

- **开发顺序**

不是：

- **功能目标**

也就是说，仍然是在模仿 `MiniCode-Python`，只是把最容易返工的 UI 阶段压到最后收尾。

## 现在推荐的推进方式

### 先做 skills

这一阶段会补齐：

- skill discovery
- load skill
- install/remove skill
- manage 命令入口
- skill 注入 prompt / tools

这一步会直接影响：

- `tools/__init__.py`
- prompt 构建
- CLI 管理入口

### 再做 MCP

这一阶段会补齐：

- MCP server 配置
- 动态工具发现
- tool call
- resources / prompts / lazy init

这一步会继续影响：

- tool registry
- prompt 中的工具说明
- session 中可能记录的扩展能力信息

### 再做 context / memory / observability

这几步继续补：

- 长上下文压缩
- 跨会话记忆
- 成本、状态、日志、用户画像

这些能力稳定之后，再做 TUI，会更容易一次把 UI 的状态结构定下来。

## 一个具体例子

假设用户输入一条需求，未来完整链路可能是：

1. `main.py` 或 `headless.py` 接收输入
2. `build_system_prompt()` 注入 skills、MCP 工具摘要、memory 信息
3. `run_agent_turn()` 驱动模型与工具调用
4. `session.py` 保存消息、转录、权限摘要、扩展能力信息
5. 最后 TUI 只负责把这些已经稳定的数据结构渲染出来

如果第 2、3、4 步还在持续变化时就先写第 5 步，那么 UI 层会不断跟着改。

## 这次修改后的实际作用

这次改完之后，你后面开发时可以直接按下面顺序推进：

1. 先完成 `skills` 和 `manage_cli`
2. 再完成 `mcp`
3. 再完成 `context_manager`
4. 再完成 `memory`
5. 再完成 `state/cost/logging/user_profile`
6. 最后统一做 `tty_app.py + ui/tui/*`

这样更符合“先稳定内核和增强能力，再包 UI 外壳”的做法。
