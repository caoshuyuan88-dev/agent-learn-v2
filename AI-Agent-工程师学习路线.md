# Java 开发者转型 Python AI Agent 工程师学习路线

> 面向拥有 7 年 Java 后端开发经验、希望转型 Agent 开发的工程师。
>
> 核心策略：**Python 主线 + Agent 工程化优先 + Java 企业集成拓展**。

## 一、目标岗位能力模型

### 1. LLM 应用开发

- Chat API、Responses API
- System Prompt、上下文窗口、Token
- Streaming 流式输出
- Structured Output、JSON Schema
- Function Calling / Tool Calling
- Embedding 与多模态输入
- 模型选择、Fallback、限流和成本控制
- Prompt 模板化与版本管理

需要理解但不必一开始深入训练模型：

- Transformer 基本原理
- Attention、Tokenizer
- 预训练、SFT、DPO、RLHF
- 推理、量化和模型部署

### 2. RAG 知识库工程

- PDF、Word、网页、Markdown、Excel 解析
- 文档清洗、切分和增量更新
- Embedding 与向量数据库
- 相似度检索、Metadata Filter
- Hybrid Search、Reranker
- Parent-Child Retrieval、Query Rewrite、Multi-Query
- Citation、来源追踪和回答溯源
- RAG 召回率、准确率和幻觉评测

### 3. Agent 核心能力

```text
用户目标
  -> 任务规划
  -> 选择工具
  -> 执行工具
  -> 观察结果
  -> 判断是否继续
  -> 输出结果
```

重点掌握：

- Tool Calling
- Agent State
- Memory
- Planning、ReAct、Reflection
- Human-in-the-loop
- Retry、Timeout、Checkpoint
- Handoff、Sub-agent
- Parallel、Sequential、Conditional Workflow
- 长任务恢复、幂等性和补偿机制

### 4. MCP 与 Agent 协议

- MCP Server、MCP Client
- Tools、Resources、Prompts
- Stdio、SSE、Streamable HTTP
- 工具参数 Schema 和权限控制
- MCP Server 部署与安全隔离
- A2A、Agent-to-Agent 通信
- Webhook、Event-driven Agent、Durable Workflow

### 5. Agent 工程化

- OpenTelemetry、Tracing
- Token、延迟、成本监控
- Prompt 和模型版本管理
- Golden Dataset 与回归测试
- 工具调用成功率、任务完成率
- 幻觉、Prompt Injection、PII 脱敏
- RBAC、审计日志、数据隔离
- Rate Limit、熔断、重试和降级

### 6. Python 后端与平台能力

- Python 3.11+、FastAPI、Pydantic、asyncio
- LangChain、LangGraph、Deep Agents
- Redis、PostgreSQL、PGVector、Qdrant
- Elasticsearch / OpenSearch
- Celery 或 Temporal、Docker、Kubernetes
- Prometheus、Grafana、OpenTelemetry
- CI/CD 和云平台部署

Java 只作为拓展能力：Spring Boot、Spring AI、LangChain4j、WebFlux 和企业内部 Java 服务集成。

## 二、学习路线

### 阶段 0：Python 工程基础，1 到 2 周

目标是达到可以独立开发、调试和部署 Python Agent 服务的程度。

学习内容：

- Python 基础、类型注解、面向对象和异常处理
- `asyncio`
- Pydantic、FastAPI、HTTPX
- pytest、ruff、mypy 或 pyright
- uv、虚拟环境和依赖锁定
- Git、Docker 和 Linux 常用命令

目标结果：

- 能独立编写异步 FastAPI 接口
- 能运行、调试并修改 Python Agent 项目
- 能为 Agent 编写单元测试和集成测试

推荐课程：

- [AI Python for Beginners](https://www.deeplearning.ai/courses/ai-python-for-beginners)
- [Hugging Face AI Agents Course](https://huggingface.co/learn/agents-course)

中文资源补充：

- [廖雪峰的 Python 教程](https://liaoxuefeng.com/books/python/introduction/index.html)
- [FastAPI 中文文档](https://fastapi.tiangolo.com/zh/)
- [Python 官方中文文档](https://docs.python.org/zh-cn/3/)
- [Datawhale：Hello Agents《从零开始构建智能体》](https://github.com/datawhalechina/hello-agents)

### 阶段 1：LLM 基础与 LangChain，2 到 3 周

使用 Python 直接调用模型，再用 LangChain 封装一遍。

学习内容：

- Chat API、Prompt、多轮对话
- Streaming
- Structured Output
- Function Calling
- Token、上下文管理
- Embedding
- temperature、top-p、max tokens
- LangChain Chat Models、Messages、Prompt Templates
- Runnable、LCEL、Callbacks
- 模型服务商抽象、切换和降级

Python 练习：

- FastAPI + LangChain 实现聊天接口
- 支持 SSE 流式返回
- 使用 Pydantic 接收结构化输出
- 添加模型超时、重试和降级
- 接入云端模型或本地 Ollama

推荐资料：

- [LangChain Python 文档](https://docs.langchain.com/oss/python/langchain/overview)
- [LangChain Academy](https://academy.langchain.com/)
- [DeepLearning.AI Agentic AI](https://www.deeplearning.ai/courses/agentic-ai)
- [Pydantic for LLM Workflows](https://www.deeplearning.ai/courses/pydantic-for-llm-workflows)

中文资源补充：

- [Datawhale：动手学大模型应用开发](https://github.com/datawhalechina/llm-cookbook)
- [LangChain-Chatchat：基于 LangChain 的中文 RAG 项目](https://github.com/chatchat-space/Langchain-Chatchat)
- [魔搭社区：大模型相关教程与课程](https://modelscope.cn/learn)

### 阶段 2：RAG 知识库，3 到 5 周

#### 推荐项目：企业技术文档智能问答系统

技术栈：

- Python 3.11+
- FastAPI
- LangChain
- PostgreSQL + PGVector
- Qdrant，可选
- LangSmith 或 Langfuse
- Ollama 或云端模型
- Docker Compose

功能目标：

- 上传 PDF、Markdown、Word 文档
- 文档解析、切分、Embedding
- 向量检索和 Metadata Filter
- Hybrid Search、Rerank
- 流式回答和引用来源
- 对话历史
- 多租户知识库和文档权限
- 知识库增量更新
- 评测数据集和测试报告

建议实现顺序：

```text
单文档问答
  -> 多文档问答
  -> Metadata Filter
  -> Hybrid Search
  -> Rerank
  -> 引用来源
  -> 权限控制
  -> 自动评测
```

推荐课程：

- [Retrieval Augmented Generation](https://www.deeplearning.ai/courses/retrieval-augmented-generation)
- [Embedding Models: From Architecture to Implementation](https://www.deeplearning.ai/courses/embedding-models-from-architecture-to-implementation)

中文资源补充：

- [Datawhale：大模型应用开发实践](https://github.com/datawhalechina/llm-universe)
- [Milvus 中文文档：向量数据库与 RAG](https://milvus.io/docs/zh)
- [RAGFlow：开源 RAG 引擎与中文实践](https://github.com/infiniflow/ragflow)

### 阶段 3：Tools、MCP 与 LangGraph，3 到 4 周

#### 推荐项目：企业运维分析 Agent

让 Agent 安全调用：

- 订单查询
- 库存查询
- 用户信息查询
- 日志查询
- 数据库查询
- 内部 REST API
- 报表生成
- 通知发送

使用 LangChain Tools 和 LangGraph StateGraph 实现，并设计：

- 工具注册机制
- 工具参数校验
- 工具权限控制
- 工具超时、重试和降级
- 工具调用审计
- 只读工具和写入工具分离
- 写操作人工确认

#### MCP 实践

建议实现两个 MCP Server：

1. `database-mcp-server`
   - 只允许查询白名单表
   - 禁止任意 SQL
   - 限制返回行数

2. `service-mcp-server`
   - 暴露内部业务 API
   - 使用 OAuth 或 JWT
   - 记录调用者、参数和结果

推荐资料：

- [LangGraph 文档](https://docs.langchain.com/oss/python/langgraph/overview)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP 官方规范](https://modelcontextprotocol.io/)

中文资源补充：

- [LangGraph 中文文档](https://langgraph-cn.com/)
- [MCP 中文文档](https://mcp-docs.cn/)
- [Model Context Protocol 中文社区](https://github.com/modelcontextprotocol)

### 阶段 4：Deep Agents 与复杂工作流，3 到 4 周

不要一开始堆多个 Agent。生产系统通常采用：

```text
确定性工作流 + 少量 Agent 决策节点
```

学习内容：

- Deep Agents 的规划、子 Agent 和文件系统能力
- LangGraph State、Node、Edge 和 Reducer
- Sequential、Parallel、Router、Supervisor
- Handoff、Agent as Tool
- Human Approval
- Checkpoint
- Long-running Task
- Event-driven Workflow

#### 推荐项目：研发效能 Agent

```text
需求输入
  -> 需求分析 Agent
  -> 技术方案 Agent
  -> 风险检查 Agent
  -> 测试用例 Agent
  -> 人工审核
  -> 输出 Markdown 报告
```

可继续接入：

- Jira、GitLab、GitHub 工具
- 代码仓库检索
- 数据库查询
- 测试结果读取
- 人工审批
- 失败恢复
- 结果评测

建议对比学习：LangGraph 负责可控编排，Deep Agents 负责更高层的长任务 Agent 能力；不要在一个项目中无理由混用多个编排框架。

### 阶段 5：评测、可观测性与生产化，3 到 5 周

#### 评测数据集

建议准备 50 到 200 条测试样本，包含：

- 正常问题
- 模糊问题
- 无答案问题
- 越权问题
- Prompt Injection
- 长上下文问题
- 工具调用失败
- 多轮追问
- 中文和英文问题

#### 评测指标

- Answer Correctness
- Faithfulness
- Context Recall
- Context Precision
- Tool Call Accuracy
- Task Completion Rate
- Latency
- Token Cost
- Error Rate
- Human Approval Rate

#### 可观测性字段

```text
trace_id
conversation_id
agent_name
model_name
prompt_version
tool_name
input_tokens
output_tokens
latency
retrieved_documents
final_answer
error_type
cost
```

推荐工具：

- [Langfuse](https://github.com/langfuse/langfuse)
- [Arize Phoenix](https://github.com/Arize-ai/phoenix)
- [LangSmith](https://smith.langchain.com/)
- OpenTelemetry
- Prometheus + Grafana

推荐课程：

- [Evaluating AI Agents](https://www.deeplearning.ai/courses/evaluating-ai-agents)
- [LangChain Academy](https://academy.langchain.com/)
- [Hugging Face Agents Course：Observability 与 Evaluation](https://huggingface.co/learn/agents-course)

中文资源补充：

- [Langfuse 中文文档](https://langfuse.com/zh/docs)
- [OpenTelemetry 中文文档](https://opentelemetry.io/zh/docs/)
- [Datawhale：Hello Agents 性能评估章节](https://github.com/datawhalechina/hello-agents)

## 三、Python 主线与 Java 拓展

### Python 主线：LangChain + LangGraph + Deep Agents

建议学习顺序：

1. LangChain：模型、Prompt、Tools、Structured Output 和 RAG 基础。
2. LangGraph：状态、节点、边、持久化、Checkpoint 和 Human-in-the-loop。
3. Deep Agents：规划、子 Agent、文件系统、长任务和更高层 Agent 抽象。
4. LangSmith：Tracing、调试、评测和部署。

补充了解：

- LlamaIndex：文档处理、数据连接和 RAG
- OpenAI Agents SDK：Guardrails、Handoff 和 Tracing
- CrewAI：角色型多 Agent 协作
- smolagents：轻量 Agent 和 Code Agent

### Java 拓展：用于企业集成和迁移

Java 不作为首要学习方向，仅投入 10% 到 15% 的时间，用于以下场景：

- 在现有 Spring Boot 系统中接入模型能力
- 调用 Python Agent 服务
- 使用 Spring AI 或 LangChain4j 维护企业内部服务
- 对比 Java 与 Python 的部署、性能和团队协作方式

推荐只完成一个小练习：

使用 Spring AI 或 LangChain4j 实现一个简单 Tool Calling 服务，并通过 REST 调用 Python LangGraph Agent。

资源：

- [LangChain4j GitHub](https://github.com/langchain4j/langchain4j)
- [LangChain4j Documentation](https://docs.langchain4j.dev/)
- [Spring AI Reference](https://docs.spring.io/spring-ai/reference/)

中文资源补充：

- [Spring AI Alibaba 文档](https://java2ai.com/)
- [LangChain4j 中文教程](https://github.com/langchain4j/langchain4j-examples)
- [Spring AI 中文参考](https://springdoc.cn/spring-ai/)

## 四、GitHub 学习仓库

### Python Agent 主线

| 仓库 | 学习重点 |
|---|---|
| [langchain-ai/langchain](https://github.com/langchain-ai/langchain) | Python LLM、Prompt、Tools、RAG 基础 |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | 有状态 Agent、图工作流、Checkpoint |
| [langchain-ai/deepagents](https://github.com/langchain-ai/deepagents) | 规划、子 Agent、文件系统和长任务 |
| [langchain-ai/langsmith-sdk](https://github.com/langchain-ai/langsmith-sdk) | Tracing、评测和调试集成 |
| [openai/openai-agents-python](https://github.com/openai/openai-agents-python) | Agent、Tools、Handoff、Guardrails、Tracing |
| [run-llama/llama_index](https://github.com/run-llama/llama_index) | RAG、数据连接、文档 Agent |
| [huggingface/smolagents](https://github.com/huggingface/smolagents) | 轻量 Agent、Code Agent、工具调用 |

### Java 拓展

| 仓库 | 学习重点 |
|---|---|
| [spring-projects/spring-ai](https://github.com/spring-projects/spring-ai) | Spring AI 官方实现 |
| [langchain4j/langchain4j](https://github.com/langchain4j/langchain4j) | Java LLM、RAG、Tools、Agents |
| [langchain4j/langchain4j-examples](https://github.com/langchain4j/langchain4j-examples) | Java 示例项目 |
| [alibaba/spring-ai-alibaba](https://github.com/alibaba/spring-ai-alibaba) | Spring AI 企业级扩展与 Agent 示例 |
| [modelcontextprotocol/java-sdk](https://github.com/modelcontextprotocol/java-sdk) | Java MCP Client/Server |
| [quarkiverse/quarkus-langchain4j](https://github.com/quarkiverse/quarkus-langchain4j) | Quarkus + LangChain4j |

### 其他 Agent 框架

| 仓库 | 学习重点 |
|---|---|
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | 有状态 Agent、图工作流、Checkpoint |
| [openai/openai-agents-python](https://github.com/openai/openai-agents-python) | Agent、Tools、Handoff、Guardrails、Tracing |
| [microsoft/agent-framework](https://github.com/microsoft/agent-framework) | 生产级 Agent、工作流、人工介入、可观测性 |
| [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | 多角色 Agent、Crews、Flows |
| [run-llama/llama_index](https://github.com/run-llama/llama_index) | RAG、数据连接、文档 Agent |
| [huggingface/smolagents](https://github.com/huggingface/smolagents) | 轻量 Agent、Code Agent、工具调用 |

### MCP 与协议

| 仓库 | 学习重点 |
|---|---|
| [modelcontextprotocol/modelcontextprotocol](https://github.com/modelcontextprotocol/modelcontextprotocol) | MCP 规范与设计 |
| [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk) | MCP 官方 Python SDK |
| [modelcontextprotocol/inspector](https://github.com/modelcontextprotocol/inspector) | MCP 调试和检查 |
| [a2aproject/A2A](https://github.com/a2aproject/A2A) | Agent-to-Agent 协议 |

### RAG、向量库和观测

| 仓库 | 学习重点 |
|---|---|
| [qdrant/qdrant](https://github.com/qdrant/qdrant) | 向量数据库 |
| [pgvector/pgvector](https://github.com/pgvector/pgvector) | PostgreSQL 向量搜索 |
| [elastic/elasticsearch](https://github.com/elastic/elasticsearch) | 混合检索和企业搜索 |
| [langfuse/langfuse](https://github.com/langfuse/langfuse) | LLM Tracing、Prompt、评测 |
| [Arize-ai/phoenix](https://github.com/Arize-ai/phoenix) | LLM 和 Agent 可观测性 |
| [promptfoo/promptfoo](https://github.com/promptfoo/promptfoo) | Prompt 和模型评测 |

## 五、作品集项目

建议完成三个项目，并将架构、指标和技术取舍写入 GitHub README。

### 项目一：企业知识库 RAG

必须包含：

- Python、FastAPI、LangChain
- LangGraph，可用于带状态的问答流程
- PostgreSQL + PGVector
- 文档上传和解析
- 文档切分和向量检索
- Rerank
- 引用来源
- 多轮对话
- 多租户权限
- 评测数据集
- LangSmith 或 Langfuse
- Docker Compose

### 项目二：企业工具调用 Agent

必须包含：

- 多个业务工具
- 工具参数校验
- RBAC 权限控制
- 只读和写入操作区分
- 写操作人工确认
- 工具调用审计
- 超时、重试和降级
- MCP Server
- Python MCP SDK

### 项目三：研发流程 Agent

必须包含：

- GitHub/GitLab 工具
- 需求分析
- 代码检索
- 测试结果分析
- LangGraph 工作流或 Deep Agents
- 人工审批
- Checkpoint
- OpenTelemetry
- 任务完成率评估

简历描述建议使用可验证的工程指标，例如：

> 基于 Python、LangChain、LangGraph、PGVector 和 Reranker 构建企业知识库 Agent，支持多租户文档权限、流式响应、引用溯源和增量索引；通过 150 条 Golden Dataset 评测，提升 Context Recall，并将平均响应延迟控制在目标范围内。

## 六、6 个月安排

| 时间 | 目标 |
|---|---|
| 第 1 个月 | Python、FastAPI、Pydantic、LLM API、LangChain |
| 第 2 个月 | RAG、Embedding、向量数据库、文档处理 |
| 第 3 个月 | LangChain Tools、MCP、API 集成、权限控制 |
| 第 4 个月 | LangGraph、Checkpoint、Human-in-the-loop、Deep Agents |
| 第 5 个月 | Agent 评测、LangSmith/Langfuse、成本监控、安全 |
| 第 6 个月 | 完成 2 到 3 个 Python 作品集项目，补充 Java 集成练习 |

## 七、学习优先级

```text
Python 工程基础
  > LangChain
  > RAG
  > Tool Calling
  > LangGraph
  > MCP
  > Deep Agents
  > Agent 评测
  > 可观测性
  > 安全与部署
  > Java 集成
```

```text
LLM API 与结构化输出
  > RAG
  > Tool Calling
  > MCP
  > 工作流
  > Agent 评测
  > 可观测性
  > 安全与部署
  > 多 Agent
  > 模型微调
```

不建议一开始花大量时间学习：

- 从零训练大模型
- 复杂数学推导
- 复杂多 Agent 协作
- 只做 Prompt 技巧
- 追逐每天更新的框架
- 只看 Demo 不做评测

Agent 工程师的核心价值是：

> 把不稳定的模型能力，封装成稳定、可测试、可监控、可控成本的业务系统。

## 八、推荐能力栈

```text
Python 3.11+
FastAPI
Pydantic
LangChain
LangGraph
Deep Agents
LangSmith / Langfuse
MCP Python SDK
RAG
PGVector / Elasticsearch
OpenTelemetry
Docker
Kubernetes
LLM Evaluation
Agent Security

# Java 拓展
Java 21
Spring Boot
Spring AI
LangChain4j
```

> Agent Framework、MCP 和模型 SDK 更新较快。学习时优先查看官方文档、`README`、`examples`、`docs` 和 `tests`，并固定依赖版本，避免直接依赖未稳定 API。
