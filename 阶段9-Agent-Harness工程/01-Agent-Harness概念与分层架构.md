# Agent Harness 概念与分层架构

## 一、为什么需要 Harness

一个简单 Agent 可以是：

```text
LLM -> Tool -> Tool Result -> LLM -> Final Answer
```

但真实任务会遇到：

- 需要读取大量仓库或业务上下文；
- 工具和文件操作有权限边界；
- 任务运行数分钟甚至数小时；
- 工具调用会超时、失败或产生副作用；
- 结果必须通过测试或业务检查；
- Agent 需要在失败后继续，而不是从头开始；
- 多用户和多任务必须隔离；
- 运行结果需要可审计、可回放和可评测。

Harness 就是为这些问题提供共同运行机制的层。

## 二、Harness 与相邻概念

| 概念 | 主要职责 |
|---|---|
| Model | 生成决策、文本或工具调用 |
| Agent Loop | 根据模型和工具结果循环执行 |
| Tool / MCP | 提供具体动作或外部能力 |
| Workflow | 编排固定步骤、分支和状态 |
| Runtime | 执行 Agent、管理上下文和生命周期 |
| Harness | 在 Runtime 外组织工具、环境、反馈、验证、恢复和治理 |
| Agent Platform | 提供部署、租户、资源、配置和运营能力 |

不同厂商对 Harness 的边界可能不同，但核心思想是：**模型不是完整产品，模型周围的执行和反馈系统决定了 Agent 能否可靠完成任务。**

## 三、典型分层

```text
Product / Task Layer
  任务、验收标准、用户体验

Harness Layer
  Agent Loop、Planning、Skills、Context、Verification、Recovery

Runtime Layer
  State、Checkpoint、Streaming、Subagent、Middleware

Execution Layer
  Tools、MCP、Filesystem、Sandbox、Browser、Repository

Governance Layer
  Auth、Permissions、Approval、Audit、Limits、Policy

Observability / Evaluation Layer
  Traces、Logs、Metrics、Golden Tasks、Regression、Reports
```

## 四、Harness 的最小闭环

```text
Understand
  -> Plan
  -> Act
  -> Observe
  -> Verify
  -> Repair or Finish
```

其中 `Verify` 是关键：没有测试、编译、Schema 校验、业务断言或人工确认，Agent 只是“生成了一个看起来合理的结果”。

## 五、Harness 的设计原则

### 1. 让能力可发现

工具、Skill、仓库结构、运行命令和验收标准必须能被 Agent 找到。不要把所有信息塞进一份巨大 Prompt，应该提供目录、索引、链接和渐进式披露。

### 2. 让行为可验证

把“做好这个任务”转换成可执行检查：测试、Lint、类型检查、截图、指标、Schema、Diff 检查或人工审批。

### 3. 让边界可执行

权限不能只写在 Prompt 中。文件路径、工具操作、网络访问、命令、密钥和写入动作都应由 Runtime 或 Sandbox 强制执行。

### 4. 让失败可恢复

保存状态、工具结果、检查点和失败原因，允许重试、回滚、补偿或人工接管。

### 5. 让运行可解释

记录模型版本、Prompt、Skill、工具、输入输出摘要、验证结果和最终决策，保证问题能够回放。

## 六、练习

1. 画出阶段 4 研发效能 Agent 的 Harness 分层图。
2. 为一个“修复测试失败”的任务写出 Understand/Plan/Act/Observe/Verify 闭环。
3. 列出当前项目中仍依赖自然语言、没有被机械强制的 10 条规则。
4. 区分哪些能力应该放在 Agent 内，哪些应该放在 Harness 或平台层。
