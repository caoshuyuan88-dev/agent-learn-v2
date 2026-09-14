# 阶段 9：Agent Harness 工程

目标：理解并构建让 Agent 能在真实环境中持续、可控、可验证地完成任务的 Harness。

## 一、Harness 是什么

Agent Harness 不是单独的模型、Tool 或 Workflow，而是包围 Agent Loop 的工程运行层：

```text
任务输入
  -> Context / Repository Knowledge
  -> Agent Loop
  -> Tools / MCP / Filesystem / Sandbox
  -> Ground Truth / Tests / Logs / Metrics
  -> Feedback / Retry / Human Approval
  -> Checkpoint / Trace / Evaluation
  -> 最终结果或升级人工
```

可以把它理解为：

```text
Agent = 决策者
Harness = 让决策者能够安全工作、验证结果并持续恢复的工作环境
```

Deep Agents 是 Agent Harness 的一个具体实现；OpenAI Harness Engineering 更偏向一套面向 Agent 的软件工程方法和运行环境设计。

## 二、学习文档

- [01 - Agent Harness 概念与分层架构](01-Agent-Harness概念与分层架构.md)
- [02 - Agent Runtime、执行环境与任务编排](02-Agent-Runtime执行环境与任务编排.md)
- [03 - Agent Legibility、验证闭环与反馈系统](03-Agent-Legibility验证闭环与反馈系统.md)
- [04 - Harness 安全、可靠性与生产治理](04-Harness安全可靠性与生产治理.md)
- [05 - 阶段 9 综合实践：可验证的 Coding Agent Harness](05-阶段9综合实践-可验证的Coding-Agent-Harness.md)

## 三、推荐顺序

```text
01 Harness 分层与边界
  -> 02 Runtime、执行环境和任务编排
  -> 03 Agent Legibility 与验证反馈
  -> 04 安全、可靠性和生产治理
  -> 05 综合实践
```

## 四、和已有阶段的关系

| 已有阶段 | 在 Harness 中的位置 |
|---|---|
| 阶段 3 Tools/MCP | 执行动作和外部能力接入 |
| 阶段 4 LangGraph/Deep Agents | 状态编排、长任务和子 Agent |
| 阶段 5 评测/可观测性 | 验证结果和观察运行过程 |
| 阶段 6 Skills | 可复用任务知识与操作流程 |
| 阶段 7 高阶能力 | A2A、Memory、Reflection、可靠执行 |
| 阶段 8 模型工程 | 模型适配和推理能力 |
| 阶段 9 Harness | 将这些能力组织成可运行、可验证、可治理的 Agent 系统 |

## 五、最终产出

构建一个最小 Coding Agent Harness：

- 接收 Issue 或任务描述；
- 创建隔离工作区；
- 读取仓库知识和 Skill；
- 规划并执行修改；
- 运行测试、Lint 和静态检查；
- 根据失败反馈继续修复；
- 生成包含 diff、测试、Trace 和风险的交付报告；
- 失败或高风险时暂停并请求人工审批。

## 资料依据

- [OpenAI Harness Engineering](https://openai.com/index/harness-engineering/)
- [OpenAI Symphony](https://github.com/openai/symphony)
- [Deep Agents Overview](https://docs.langchain.com/oss/python/deepagents/overview)
- [Deep Agents Production](https://docs.langchain.com/oss/python/deepagents/going-to-production)
- [Anthropic Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)
- [SWE-bench](https://github.com/SWE-bench/SWE-bench)
