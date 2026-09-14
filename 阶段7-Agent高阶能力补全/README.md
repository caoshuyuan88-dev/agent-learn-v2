# 阶段 7：Agent 高阶能力补全

目标：补齐阶段 0~6 后仍未形成独立学习闭环的 Agent 高阶能力，并把协议、记忆、推理模式、多模态和可靠执行放回统一的 Agent 工程体系。

> 本阶段不是继续堆框架，而是补齐五类跨项目能力。每篇先学习概念和官方规范，再做一个可验证的小练习。

## 学习范围

- A2A 与 Agent-to-Agent 通信
- 短期记忆、长期记忆与 Memory 治理
- Reflection、Evaluator-Optimizer 与输出修正
- 多模态输入与 Responses API
- 幂等、补偿、Saga 与长任务可靠执行

## 学习文档

- [01 - A2A 与 Agent-to-Agent 通信](01-A2A与Agent-to-Agent通信.md)
- [02 - Agent Memory 设计与实现](02-Agent-Memory设计与实现.md)
- [03 - Reflection 与自我修正工作流](03-Reflection与自我修正工作流.md)
- [04 - 多模态输入与 Responses API](04-多模态输入与Responses-API.md)
- [05 - 幂等、补偿与可靠执行](05-幂等补偿与可靠执行.md)
- [06 - 阶段 7 综合实践：可靠的多 Agent 研发流程](06-阶段7综合实践-可靠的多Agent研发流程.md)

## 推荐顺序

```text
01 A2A 协议
  -> 02 Memory 设计
  -> 03 Reflection 工作流
  -> 04 多模态与 Responses API
  -> 05 幂等、补偿与可靠执行
  -> 06 综合实践
```

## 阶段产出

为阶段 4 的研发效能 Agent 增加：

- 一个 A2A 远程分析 Agent；
- 用户级长期 Memory 和线程级短期 Memory；
- 一个带评审循环的 Reflection 节点；
- 一个图像或 PDF 输入流程；
- 写操作幂等键和失败补偿；
- 端到端任务报告、Trace 和故障演练记录。

## 验收标准

- 能解释 MCP 与 A2A 的边界，并实现任务型 A2A 调用；
- 能区分 Checkpoint、短期记忆、长期记忆和 RAG；
- 能设计带停止条件和预算上限的 Reflection 循环；
- 能处理文本、图片或文档输入，并记录输入模态；
- 能为写操作设计幂等键、重试策略和补偿状态；
- 能在评测和 Trace 中证明这些能力没有引入不可控成本或安全漏洞。

## 资料依据

- [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/)
- [A2A and MCP](https://a2a-protocol.org/latest/topics/a2a-and-mcp/)
- [LangGraph Memory](https://docs.langchain.com/oss/python/langgraph/add-memory)
- [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph Workflows and Agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents)
- [OpenAI Responses API migration](https://developers.openai.com/api/docs/guides/migrate-to-responses)
- [OpenAI Images and Vision](https://developers.openai.com/api/docs/guides/images-vision)
- [Temporal Activity Definition](https://docs.temporal.io/activity-definition)
- [Temporal Workflows](https://docs.temporal.io/workflows)
