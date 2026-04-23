# Phase 11：session 持久化实现说明

## 本次实现了什么

本次按 `FROM_SCRATCH_IMPLEMENTATION_GUIDE.md` 的 Phase 11 要求，完成了 session 持久化第一版。

已实现的能力：

1. `SessionMetadata`
2. `SessionData`
3. `save_session`
4. `load_session`
5. `list_sessions`
6. `create_new_session`
7. `get_latest_session`

同时为了让这一步真正可用，也把 session 恢复链路接进了 CLI 入口：

- `--list-sessions`
- `--resume`
- 交互式退出时自动保存
- headless 模式绑定 session 后自动保存

注意：

- 这一版**只做全量保存**
- **没有提前实现** autosave、delta save、consolidation

这和指南里 Phase 11 的“第一版先全量保存稳定，再补 delta”保持一致。

## 这次新增/修改的关键文件

- `src/XingCode/storage/session.py`
  - session 数据结构、完整保存、完整加载、索引维护、会话列表与恢复展示文本。
- `src/XingCode/storage/__init__.py`
  - 导出 session 相关能力。
- `src/XingCode/app/main.py`
  - 增加 `--resume`、`--list-sessions`，并在交互模式退出时保存 session。
- `src/XingCode/app/headless.py`
  - 支持传入 `session` 对象，在一次性命令执行后写回并保存。

## session 的存储结构

### 1. 文件位置

- 单个会话文件：`~/.xingcode/sessions/<session_id>.json`
- 会话索引文件：`~/.xingcode/sessions_index.json`

### 2. 保存内容

第一版会完整保存下面这些字段：

- `session_id`
- `created_at`
- `updated_at`
- `workspace`
- `messages`
- `transcript_entries`
- `history`
- `permissions_summary`
- `skills`
- `mcp_servers`
- `metadata`

其中当前项目在 Phase 11 里真正会用到的核心字段是：

- `messages`
- `history`
- `permissions_summary`
- `metadata`

## 当前 CLI 的恢复流程

### 示例 1：交互式恢复

如果你运行：

```bash
python -m XingCode.app.main --resume
```

执行流程：

1. `main.py` 解析 `--resume`
2. `_resolve_cli_session()` 尝试读取当前工作区最近一次 session
3. 如果找到，就打印恢复信息
4. 进入交互循环，并把旧 `messages` 注入到本次对话上下文
5. 退出时调用 `save_session()` 做一次全量保存

### 示例 2：列出历史 session

如果你运行：

```bash
python -m XingCode.app.main --list-sessions
```

执行流程：

1. `main.py` 调用 `list_sessions()`
2. `session.py` 读取 `sessions_index.json`
3. 把元数据按 `updated_at` 倒序排序
4. 使用 `format_session_list()` 输出人类可读文本

### 示例 3：headless 模式继续同一个 session

执行流程：

1. `main.py` 根据 `--resume` 先解析出一个 `SessionData`
2. 调用 `run_headless(..., session=session)`
3. `headless.py`
   - 读取 `session.messages`
   - 重建最新 system prompt
   - 追加本轮用户输入
   - 运行 `run_agent_turn`
4. 回写：
   - `session.messages`
   - `session.history`
   - `session.permissions_summary`
5. 调用 `save_session()`

## 这一步为什么这样实现

这次特意没有提前把参考项目里更后的能力一起搬过来：

- `AutosaveManager`
- delta save
- consolidation
- TUI 的 session_flow

原因很简单：

- Phase 11 的目标是先把“能恢复”这条主链路打通
- 当前 XingCode 还没有进入 Phase 12 的 TUI 阶段
- 过早加入 autosave / delta，会增加状态复杂度，不符合当前阶段“先稳”的要求

所以这次保持了最小但完整的实现：

- 能创建 session
- 能保存 session
- 能读取 session
- 能列出 session
- 能恢复 session

## 验证结果

本次新增 session 测试，并补了 headless 的 session 落盘/恢复集成验证。

执行：

```bash
pytest -q
```

结果：

```text
101 passed in 1.17s
```
