# 测试 Skill：demo-sequence-file

## 本次新增了什么

新增了一个项目级测试 skill：

- `XingCode/.xingcode/skills/demo-sequence-file/SKILL.md`

它的定位不是读代码，也不是复杂工作流，而是专门用于验证 skill 机制本身。

## 这个 skill 做什么

它支持两类非常容易验证的任务：

1. 按顺序输出一组步骤
2. 生成一个简单测试文件

这两个动作都不依赖代码分析，所以很适合测试：

- skill discovery
- skill 摘要注入 prompt
- `load_skill` 工具是否会被调用
- skill 全文是否会影响大模型后续行为

## 设计思路

这个 skill 故意写得很克制：

- 默认不读仓库
- 默认不执行命令
- 只在“生成测试文件”时使用 `write_file`
- 如果用户没有指定文件路径，则默认使用 `skill_demo_output.txt`

这样做的好处是：

- 触发简单
- 结果容易观察
- 不容易和项目里的其他代码逻辑混在一起

## 你可以怎么测试

### 场景 1：测试按序输出

你可以直接问：

```text
请使用 demo-sequence-file skill，按顺序输出一个 3 步的测试流程
```

预期：

- 模型先识别这是一个 skill 场景
- 按需要会调用 `load_skill`
- 然后直接输出 1/2/3 列表

### 场景 2：测试生成文件

你可以问：

```text
请使用 demo-sequence-file skill，生成一个测试文件，内容是发布前检查清单
```

预期：

- 模型按需要调用 `load_skill`
- 然后调用 `write_file`
- 默认输出文件为 `skill_demo_output.txt`

### 场景 3：测试指定路径

你可以问：

```text
请使用 demo-sequence-file skill，把测试内容写入 outputs/checklist.txt
```

预期：

- 使用用户给定路径
- 不再使用默认路径

## 为什么这个 skill 适合当前阶段

当前 XingCode 已经支持：

- 发现 project skills
- 把 skill 摘要注入 prompt
- 通过 `load_skill` 读取完整 `SKILL.md`

所以现在最需要的是一个：

- 内容简单
- 触发明确
- 行为稳定

的 skill，来帮助你验证这一整条链路。

`demo-sequence-file` 就是为这个目的准备的。
