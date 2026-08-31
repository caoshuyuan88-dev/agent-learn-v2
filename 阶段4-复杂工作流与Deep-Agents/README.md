# 阶段 4：复杂工作流与 Deep Agents

目标：设计可恢复、可控、支持人工介入的长任务 Agent 工作流。

学习范围：

- LangGraph State、Node、Edge 和 Reducer（深入）
- Sequential、Parallel、Router 和 Supervisor
- Handoff、Sub-agent 和 Agent as Tool
- Human-in-the-loop、Checkpoint 和长任务恢复
- Event-driven Workflow
- Deep Agents 的规划、文件系统和长任务能力

学习文档：

- [01 - LangGraph 深入：Reducer 与状态设计](01-LangGraph深入-Reducer与状态设计.md)
- [02 - LangGraph 进阶：并行分支与子图](02-LangGraph进阶-并行分支与子图.md)
- [03 - 多 Agent 编排：Router、Supervisor、Handoff 与 Agent as Tool](03-多Agent编排-Router-Supervisor-Handoff与Agent-as-Tool.md)
- [04 - Human-in-the-loop：interrupt 与人工审批](04-Human-in-the-loop-interrupt与人工审批.md)
- [05 - Checkpoint 持久化与长任务恢复](05-Checkpoint持久化与长任务恢复.md)
- [06 - Deep Agents：规划、子 Agent 与文件系统](06-Deep-Agents-规划子Agent与文件系统.md)
- [07 - Event-driven Workflow 与异步长任务](07-Event-driven-Workflow与异步长任务.md)
- [08 - 阶段 4 综合实践：研发效能 Agent](08-阶段4综合实践-研发效能Agent.md)

推荐学习顺序：

```text
01 LangGraph 深入（Reducer 与状态设计）
	-> 02 LangGraph 进阶（并行分支与子图）
	-> 03 多 Agent 编排（Router/Supervisor/Handoff/Agent as Tool）
	-> 04 Human-in-the-loop（interrupt 与人工审批）
	-> 05 Checkpoint 持久化与长任务恢复
	-> 06 Deep Agents（规划/子 Agent/文件系统）
	-> 07 Event-driven Workflow 与异步长任务
	-> 08 综合实践：研发效能 Agent
```

学习完文档后，按 [08 综合实践](08-阶段4综合实践-研发效能Agent.md) 的 Milestone 计划开发项目（M1 线性流水线 → M2 并行 → M3 人工审核 → M4 持久化恢复 → M5 异步与事件驱动 → M6 审计评测）。

> 提醒：项目主干采用「LangGraph 可控编排 + 少量 Agent 决策节点」，不无理由混用多个编排框架（参见 [06 篇](06-Deep-Agents-规划子Agent与文件系统.md) 第七节选型纪律）。
