# Agent Skills 概念与开放格式

## 学习目标

学完本篇，你应该能：

- 用一句话定义 Agent Skill；
- 说明 Skill 与 Tool、Prompt、Workflow、Memory、MCP 的区别；
- 按 Agent Skills 开放格式创建一个最小 Skill；
- 解释渐进式披露为什么能减少上下文浪费；
- 判断一个能力应该做成 Skill、Tool 还是 Workflow。

## 一、Skill 是什么

Agent Skill 是面向某类任务的可复用能力包，通常包含：

- 任务说明和操作流程；
- 领域知识和参考资料；
- 输入、输出和完成标准；
- 边界条件与失败处理；
- 可选的脚本、模板和其他资源。

它解决的是“Agent 如何稳定完成一类任务”，而不是“Agent 如何执行一个具体动作”。

```text
Skill     = 任务知识 + 操作流程 + 约束 + 相关资源
Tool      = 一个可调用的动作
Workflow  = 一组有确定顺序和状态转移的步骤
MCP       = 跨进程暴露工具、资源和提示的协议
```

## 二、最小目录结构

```text
skills/code-review/
├── SKILL.md
├── references/
│   └── review-checklist.md
├── scripts/
│   └── run-checks.py
└── assets/
    └── report-template.md
```

`SKILL.md` 必须包含 YAML frontmatter 和 Markdown 指令：

```markdown
---
name: code-review
description: Review backend code for correctness, security, and performance. Use when the user asks for a code review.
license: Internal
metadata:
  version: "1.0.0"
---

# Code Review

## Instructions

1. Read the target files.
2. Run the approved static checks.
3. Report findings by severity with file references.
4. Do not modify files unless explicitly requested.
```

规范中，`name` 和 `description` 是必需字段。Skill 名称应使用小写字母、数字和连字符，并与父目录名称一致。`license`、`compatibility`、`metadata` 和 `allowed-tools` 属于可选字段，具体支持情况取决于 Runtime。

## 三、渐进式披露

Skill 不应在 Agent 启动时把所有资料全部塞进上下文。推荐分三层：

```text
Discovery  ：只加载 name 和 description
Activation ：任务匹配后加载完整 SKILL.md
Execution  ：按指令读取 references、assets 或执行 scripts
```

这样可以让 Agent 同时拥有很多候选 Skill，而不让每个请求都承担全部上下文成本。

## 四、和相邻抽象的边界

| 问题 | 优先使用 |
|---|---|
| 需要查询数据库或调用 API | Tool |
| 需要一段可复用的提示模板 | Prompt |
| 需要固定顺序、状态和审批 | Workflow |
| 需要跨会话保存用户信息 | Memory |
| 需要跨进程发现和调用能力 | MCP |
| 需要封装某类任务的知识、流程、资源 | Skill |

一个 Skill 可以引用多个 Tool，也可以要求 Agent 调用 MCP Tool；但 Skill 不应该把权限校验和业务安全寄托在自然语言说明上。

## 五、判断标准

适合做成 Skill 的信号：

- 同一类任务会重复出现；
- 任务需要多步规则和领域知识；
- 规则需要独立版本管理；
- 需要按需加载参考资料；
- 需要在多个 Agent 或项目间复用。

不适合做成 Skill 的信号：

- 只是一次性的简单提示；
- 核心是一个确定性的 API 动作；
- 必须严格控制步骤和状态转移；
- 需要强一致的权限决策。

## 练习

1. 创建 `incident-analysis` Skill，描述故障分析的输入、步骤、输出和边界。
2. 将一份详细的排障手册放入 `references/`，只在指令需要时读取。
3. 为 Skill 增加一个只读诊断脚本，并明确脚本的参数和失败处理。
4. 用 `skills-ref validate` 检查目录和 frontmatter。

## 资料依据

- [Agent Skills Overview](https://agentskills.io/home)
- [Agent Skills Specification](https://agentskills.io/specification)
