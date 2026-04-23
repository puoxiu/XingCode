# Phase 12 补充：真正接入 skill 全文加载机制

## 为什么这次要继续补

前一版 Phase 12 已经完成了：

- skill discovery
- install/remove
- `/skills`
- skill 摘要注入 prompt

但还缺了参考项目里真正关键的一步：

- **让大模型可以按需读取某个 skill 的完整 `SKILL.md` 内容**

也就是说，之前大模型只能看到：

- skill 名字
- skill 一句简介

看不到：

- `SKILL.md` 全文
- 里面的步骤、约束、示例

这次补的就是这一步。

## 这次新增了什么

### 1. 新增 `load_skill` 工具

文件：

- `src/XingCode/tools/load_skill.py`

它的作用和参考项目一致：

1. 接收 `name`
2. 调用 `integrations/skills.py` 里的 `load_skill()`
3. 读取对应 skill 的完整 `SKILL.md`
4. 返回：
   - `SKILL: <name>`
   - `SOURCE: <source>`
   - `PATH: <path>`
   - skill 全文内容

### 2. 把 `load_skill` 装进默认工具注册表

文件：

- `src/XingCode/tools/__init__.py`

现在创建默认 `ToolRegistry` 时，不只是带着：

- `ask_user`
- `read_file`
- `run_command`

还会带上：

- `load_skill`

这样真实大模型就可以在回合中主动调用它。

### 3. 在 system prompt 中明确告诉模型如何使用

文件：

- `src/XingCode/core/prompt.py`

这次补了一条非常关键的规则：

- 如果用户点名某个 skill
- 或者用户明显要求一个和某个 skill 对应的 workflow
- **先调用 `load_skill`，再按那个 skill 执行**

这正是参考项目当前采用的机制。

## 现在的完整 skill 机制是什么样

### 以前

以前的流程是：

1. 启动时发现 skills
2. 把 skill 摘要放进 prompt
3. 大模型只能“猜”这个 skill 该怎么做

### 现在

现在的流程是：

1. 启动时发现 skills
2. 把 skill 摘要放进 prompt
3. system prompt 告诉模型：
   - 用户提到 skill 时，先调用 `load_skill`
4. 大模型调用 `load_skill`
5. `load_skill` 返回完整 `SKILL.md`
6. 模型再根据完整 skill 内容继续工作

## 一个具体例子

假设项目里有：

```text
.xingcode/skills/code-review/SKILL.md
```

用户输入：

```text
请用 code-review skill 帮我检查 src/foo.py
```

现在推荐的真实运行链路会变成：

1. system prompt 里已经列出：
   - `code-review: ...`
2. system prompt 还明确要求：
   - 用户点名 skill 时先调用 `load_skill`
3. 大模型先发起工具调用：
   - `load_skill({"name": "code-review"})`
4. 工具返回完整 `SKILL.md`
5. 模型读取 skill 全文后，再决定是否继续调用：
   - `read_file`
   - `list_files`
   - `run_command`
6. 最后再输出更贴近 skill 规则的回答

## 这次补完后，Phase 12 才真正闭环

现在 Phase 12 已经不只是：

- “能看到 skills”

而是已经变成：

- “能发现 skills”
- “能管理 skills”
- “能把 skill 摘要告诉模型”
- “能让模型按需读取 skill 全文”

这才更接近 `MiniCode-Python` 当前源码里的真实设计。
