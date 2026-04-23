# Phase 11：session 持久化第二版实现说明

## 本次补齐了什么

这次是在 Phase 11 第一版的基础上，继续补全指南里第二版要求的三项能力：

1. `AutosaveManager`
2. delta save
3. consolidation

现在 Phase 11 的计划已经完整覆盖：

- `SessionMetadata`
- `SessionData`
- `save_session`
- `load_session`
- `list_sessions`
- `create_new_session`
- `get_latest_session`
- `AutosaveManager`
- delta save
- consolidation

## 关键实现文件

- `src/XingCode/storage/session.py`
  - 现在不仅能完整保存/恢复 session，还支持：
    - 记录最近一次完整保存后的消息基线
    - 只为新增 `messages` / `transcript_entries` 写 delta 文件
    - 在达到阈值时自动合并 delta 回主快照
- `src/XingCode/app/main.py`
  - 交互式 CLI 里接入了 `AutosaveManager`
  - 每次本地命令或模型回合后都会同步 session 状态、标记 dirty，并按间隔自动保存
  - 退出时强制做一次完整快照保存
- `tests/unit/test_session.py`
  - 新增 delta save、consolidation、AutosaveManager 相关测试
- `tests/integration/test_headless.py`
  - 验证 headless 真实链路下第二次保存会生成 delta 文件

## 第二版的数据落盘策略

### 1. 完整快照

完整快照文件路径：

- `~/.xingcode/sessions/<session_id>.json`

完整快照里会保存：

- `messages`
- `transcript_entries`
- `history`
- `permissions_summary`
- `skills`
- `mcp_servers`
- `metadata`

### 2. delta 文件

delta 目录路径：

- `~/.xingcode/sessions/deltas/<session_id>/`

delta 文件内容只记录：

- 新增的 `messages`
- 新增的 `transcript_entries`
- 对应 offset

也就是说，delta 只负责“追加型变化”。

如果变化的是下面这些字段：

- `history`
- `permissions_summary`
- `skills`
- `mcp_servers`

那么不会走 delta，而会直接回退到完整快照保存。

## 当前保存策略的工作方式

### 第一次保存

第一次保存一定写完整快照。

原因：

- session 还没有主快照文件
- delta 必须建立在一个稳定的完整基线上

### 后续保存

如果满足下面条件：

- 已经有完整快照
- 本次变化只是新增消息 / 新增 transcript
- 未达到完整保存阈值

那么就写 delta 文件。

### consolidation

当 delta 数量达到阈值后，会自动触发：

1. 重新写完整快照
2. 把已经吸收进完整快照的 delta 文件删除
3. 重置 delta 计数

这样可以避免 delta 文件无限增长。

## AutosaveManager 在 CLI 中的作用

交互式 CLI 现在已经不是“只在退出时存一次”。

当前流程：

1. 用户输入内容
2. `main.py` 更新 `messages / history / permissions_summary`
3. `AutosaveManager.mark_dirty()`
4. 如果距离上次自动保存已超过阈值：
   - 调用 `save_session(session, force_full=False)`
   - 优先尝试 delta save
5. 退出程序时：
   - `AutosaveManager.force_save()`
   - 强制写完整快照，确保最终状态稳定可恢复

## 示例流程

### 示例 1：普通连续对话

假设已经有一个会话：

1. 第一次运行结束时，写出完整快照
2. 继续同一个会话，再新增几条消息
3. 自动保存触发时，只会把新增消息写入 delta 文件
4. `load_session()` 恢复时：
   - 先读取完整快照
   - 再按顺序应用 delta
   - 得到完整最新会话

### 示例 2：只改了 history

例如执行本地命令后：

- `messages` 没变
- `history` 变了

这时不会写 delta，而是直接写完整快照。

原因是：

- delta 这版只表达“追加消息/追加 transcript”
- `history` 属于非追加字段，必须完整保存才能避免信息丢失

### 示例 3：达到 consolidation 阈值

假设已经有主快照，之后多次自动保存都产生 delta：

1. `delta_0000.json`
2. `delta_0001.json`
3. ...

当达到完整保存阈值后：

1. 重写 `sessions/<session_id>.json`
2. 删除 `deltas/<session_id>/` 下旧 delta 文件
3. 会话重新回到“主快照为基线”的状态

## 为什么这次这样实现

这次仍然保持在 Phase 11 范围内，没有提前进入 Phase 12/13：

- 没有引入 TUI session_flow
- 没有做更复杂的 UI 恢复体验
- 没有扩展到管理命令、skills 装配增强

但已经把 Phase 11 从“能保存/能恢复”推进到了“能增量保存、能自动保存、能定期合并”的完整状态。

## 验证结果

这次新增并通过了：

- delta save 测试
- consolidation 测试
- AutosaveManager 测试
- headless 真实链路 delta 生成测试

执行：

```bash
pytest -q
```

结果：

```text
105 passed in 1.15s
```
