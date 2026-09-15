# 阶段 9：Agent Harness 工程

目标：理解并构建让 Agent 能在真实环境中持续、可控、可验证地完成任务的 Harness。

## 一、Harness 是什么

**本节依据**：[OpenAI Harness Engineering](https://openai.com/index/harness-engineering/)，[Deep Agents Overview](https://docs.langchain.com/oss/python/deepagents/overview)

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

本阶段以企业内部 Coding Agent 为统一案例：Agent 从 Issue 获取任务，在独立 Workspace/Sandbox 中修改代码，用测试和 CI 作为事实依据，再将可审查证据交给人或发布流程。它不讨论把 Agent 直接连接到生产数据库或让 Agent 无审批自动合并代码。

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

**本节依据**：[OpenAI Symphony Spec](https://github.com/openai/symphony/blob/main/SPEC.md)，[Claude Code Best Practices](https://code.claude.com/docs/en/best-practices)

构建一个最小 Coding Agent Harness：

- 接收 Issue 或任务描述；
- 创建隔离工作区；
- 读取仓库知识和 Skill；
- 规划并执行修改；
- 运行测试、Lint 和静态检查；
- 根据失败反馈继续修复；
- 生成包含 diff、测试、Trace 和风险的交付报告；
- 失败或高风险时暂停并请求人工审批。

## 六、建议学习方式

1. 先读 01，写出你当前项目的 Harness 分层与信任边界。
2. 再读 02，在本机为单个任务创建独立临时工作区，并实现超时与取消。
3. 读 03 后，为一个真实测试失败生成结构化反馈，手动模拟 Agent 修复循环。
4. 读 04 后，给工作区、命令、网络和密钥写出默认拒绝的权限矩阵。
5. 最后按 05 实现综合实践；先只接内部测试仓库和非生产凭据。

## 七、完成标准

- 每个 Run 都能关联 `task_id`、`run_id`、`workspace_id` 和基线 revision；
- Agent 只能在授权的隔离环境中执行，不能读取宿主密钥或工作区外文件；
- “完成”必须有测试、构建、评测或审批等外部证据；
- 失败后最多有限次修复，超时、取消、权限拒绝和环境故障均有明确状态；
- 指标、Trace、审计和产物足以让另一位工程师复核一次 Run。

## 八、资料依据

- [OpenAI Harness Engineering](https://openai.com/index/harness-engineering/)
- [OpenAI Symphony](https://github.com/openai/symphony)
- [Deep Agents Overview](https://docs.langchain.com/oss/python/deepagents/overview)
- [Deep Agents Production](https://docs.langchain.com/oss/python/deepagents/going-to-production)
- [Anthropic Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)
- [SWE-bench](https://github.com/SWE-bench/SWE-bench)
