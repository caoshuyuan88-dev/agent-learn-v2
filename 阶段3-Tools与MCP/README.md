# 阶段 3：Tools、MCP 与 LangGraph

目标：构建能够安全调用业务工具和 MCP 服务的 Agent。

学习范围：

- LangChain Tools 和工具注册
- 工具参数校验、超时、重试和降级
- RBAC、审计日志和权限隔离
- 只读工具、写入工具和人工确认
- MCP Server、MCP Client、Resources 和 Prompts
- MCP 传输方式、部署和安全隔离

学习文档：

- [01 - LangChain Tools 与工具注册机制](01-LangChain-Tools与工具注册机制.md)
- [02 - 工具调用工程化：校验、超时、重试、降级与审计](02-工具调用工程化-校验超时重试降级审计.md)
- [03 - 工具安全：RBAC 权限、只读/写入分离与人工确认](03-工具安全-RBAC权限与人工确认.md)
- [04 - MCP 协议与规范：Tools、Resources、Prompts 与传输方式](04-MCP协议与规范.md)
- [05 - MCP Server 开发实践：FastMCP 与两个生产级 Server](05-MCP-Server开发实践.md)
- [06 - MCP Client 与 Agent 集成](06-MCP-Client与Agent集成.md)
- [07 - LangGraph 入门：StateGraph、节点与边](07-LangGraph入门-StateGraph.md)
- [08 - 阶段 3 综合实践：企业运维分析 Agent](08-阶段3综合实践-企业运维分析Agent.md)

推荐学习顺序：

```text
01 LangChain Tools 与工具注册机制
	-> 02 工具调用工程化（校验/超时/重试/降级/审计）
	-> 03 工具安全（RBAC/读写分离/人工确认）
	-> 04 MCP 协议与规范
	-> 05 MCP Server 开发实践（database-mcp-server / service-mcp-server）
	-> 06 MCP Client 与 Agent 集成
	-> 07 LangGraph 入门（StateGraph）
	-> 08 综合实践：企业运维分析 Agent
```

学习完文档后，按 [08 综合实践](08-阶段3综合实践-企业运维分析Agent.md) 的 Milestone 计划开发项目。
