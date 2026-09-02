# 后续学习路径规划（阶段 3 结束后）

> 依据《AI-Agent-工程师学习路线.md》「一、目标岗位能力模型」逐条核对阶段 0~5 现有学习资料后，重新整理从「阶段 3 学完」出发的后续学习路径。
>
> 前提说明：阶段 0/1/3/4 学习文档齐备；**阶段 2 目录内未发现学习文档**（仅 README 与外部项目链接 `hello-rag-langchain`）——若 RAG 项目已按路线要求完成（含 Hybrid/Rerank/引用溯源/权限/评测），视为已覆盖；否则需补 RAG 专项，其能力仍属于岗位能力模型第 2 块。**阶段 5 尚无学习文档**，本规划给出文档拆解建议。
>
> 路线原文 6 个月安排：第 1 月 Python/LLM 基础 → 第 2 月 RAG → 第 3 月 Tools/MCP → 第 4 月 LangGraph/HITL/Deep Agents → 第 5 月 评测/可观测/成本/安全 → 第 6 月 作品集 + Java 集成。**你当前位于第 3 月末**，本规划接续第 4 个月。

---

## 一、能力差距总览（对照岗位能力模型）

### 1. LLM 应用开发

| 能力条目 | 状态 | 覆盖位置 / 缺口 |
| --- | --- | --- |
| Chat API、System Prompt、上下文窗口、Token | ✅ | 阶段1《LLM 调用与上下文管理》 |
| Streaming 流式输出 | ✅ | 阶段1《Streaming 与结构化输出》 |
| Structured Output、JSON Schema | ✅ | 阶段1《Streaming 与结构化输出》 |
| Function Calling / Tool Calling | ✅ | 阶段1《Tool Calling》、阶段3 全部 |
| Embedding | ✅ | 阶段1《Tool Calling 与 Embedding》 |
| **多模态输入** | ❌ | **补丁包-4** |
| 模型选择、Fallback、限流和成本控制 | ✅（自核） | 阶段1《LangChain 核心与模型工程化》；限流/成本的落地监控属阶段5 |
| Prompt 模板化 | ✅ | 阶段1《LangChain 核心与模型工程化》 |
| **Prompt 版本管理** | ❌ | 阶段5-03（Langfuse Prompt 管理） |
| **Responses API**（OpenAI 新一代） | ⚠️ 未单列 | **补丁包-4**（可选） |
| Transformer/Attention/Tokenizer/SFT/DPO/RLHF/推理量化（理解层） | ⚠️ 无专文 | 可选补丁：1 篇概念综述即可 |

### 2. RAG 知识库工程（阶段 2）

⚠️ **目录内无文档，需自核**：若已完成项目，逐条确认——文档解析（PDF/Word/网页/Markdown/Excel）、切分与增量更新、向量检索 + Metadata Filter、Hybrid Search、Rerank、**Parent-Child Retrieval / Query Rewrite / Multi-Query**（这三项路线明确要求，RAG 项目若未做属缺口）、引用来源、多租户权限、**RAG 召回率/准确率/幻觉评测**（也可并入阶段 5 一起补）。

### 3. Agent 核心能力

| 能力条目 | 状态 | 覆盖位置 / 缺口 |
| --- | --- | --- |
| Tool Calling | ✅ | 阶段1/阶段3 |
| Agent State | ✅ | 阶段3-07 入门、阶段4-01/02 深入 |
| **Memory** | ❌ 无专项 | **补丁包-2**（阶段4-05 只覆盖执行状态持久化，非记忆设计） |
| Planning | ✅ | 阶段4-06 Deep Agents 规划、阶段4-03 |
| ReAct | ✅ | 阶段1/阶段3-07 |
| **Reflection（自我反思）** | ❌ | **补丁包-3** |
| Human-in-the-loop | ✅ | 阶段3-03、阶段4-04 |
| Retry、Timeout、Checkpoint | ✅ | 阶段3-02、阶段4-05 |
| Handoff、Sub-agent | ✅ | 阶段4-03、阶段4-06 |
| Parallel / Sequential / Conditional | ✅ | 阶段4-01/02 |
| 长任务恢复 | ✅ | 阶段4-05/07 |
| 幂等性 | ✅（概念） | 阶段3-02；写入工具不自动重试 |
| **补偿机制（事务性补偿）** | ⚠️ 弱 | **补丁包-5** 深化 |

### 4. MCP 与 Agent 协议

| 能力条目 | 状态 | 覆盖位置 / 缺口 |
| --- | --- | --- |
| MCP Server / Client | ✅ | 阶段3-05/06 |
| Tools / Resources / Prompts | ✅ | 阶段3-04 |
| Stdio / SSE / Streamable HTTP | ✅ | 阶段3-04/05 |
| 工具参数 Schema 与权限控制 | ✅ | 阶段3-01/03 |
| MCP Server 部署与安全隔离 | ✅ | 阶段3-05 |
| Webhook / Event-driven / Durable Workflow | ✅（Event-driven 部分） | 阶段4-07；Webhook 收发、Durable 语义可并入补丁包-1 补强 |
| **A2A、Agent-to-Agent 通信** | ❌ | **补丁包-1** |

### 5. Agent 工程化（阶段 5 主体，目前无文档）

| 能力条目 | 状态 | 说明 |
| --- | --- | --- |
| RBAC、审计日志、数据隔离 | ✅ | 阶段3-03 已强覆盖 |
| Rate Limit、熔断、重试和降级 | ✅（实现） | 阶段3-02；生产化监控与评测属阶段5 |
| OpenTelemetry、Tracing | ❌ | 阶段5-04 |
| Token、延迟、成本监控 | ❌ | 阶段5-03 |
| Prompt 和模型版本管理 | ❌ | 阶段5-03 |
| Golden Dataset 与回归测试 | ❌ | 阶段5-01 |
| 工具调用成功率、任务完成率 | ❌ | 阶段5-02 |
| 幻觉、Prompt Injection、PII 脱敏 | ⚠️ 部分 | 注入防护/PII 脱敏阶段3-02/03 有实现；**评测指标**属阶段5-05 |

### 6. Python 后端与平台能力

| 能力条目 | 状态 | 说明 |
| --- | --- | --- |
| Python 3.11+、FastAPI、Pydantic、asyncio | ✅ | 阶段0 全覆盖 |
| LangChain、LangGraph、Deep Agents | ✅ | 阶段1/3/4 |
| PostgreSQL、PGVector、Qdrant | ⚠️ | 阶段2 项目使用，无文档（自核） |
| **Redis** | ❌ | 选学包-A（缓存/限流/任务队列） |
| **Elasticsearch / OpenSearch** | ❌ | 选学包-A（企业检索、Hybrid 生产化） |
| **Celery 或 Temporal** | ❌ | 选学包-A（异步任务、Durable Execution 对照） |
| Docker | ⚠️ | 阶段2 README 提及 docker compose；部署实操属阶段5-07 |
| **Kubernetes** | ❌ | 选学包-A |
| **Prometheus、Grafana、OpenTelemetry** | ❌ | 阶段5-04/06 |
| **CI/CD 和云平台部署** | ❌ | 阶段5-07 |

### 其余路线内容（尚未安排）

- **Java 拓展练习**（Spring AI / LangChain4j Tool Calling + REST 调 Python LangGraph Agent）——未做
- **框架了解包**：LlamaIndex、OpenAI Agents SDK、CrewAI、smolagents、microsoft/agent-framework——未做
- **作品集**：项目一 RAG（阶段2）、项目二 工具调用 Agent（阶段3）、项目三 研发流程 Agent（阶段4）——阶段5 后整合 README 指标

---

## 二、后续学习路径大纲

### 阶段 4：复杂工作流与 Deep Agents（文档已就绪，约 3~4 周）

按 [阶段4 README](阶段4-复杂工作流与Deep-Agents/README.md) 顺序学习 01→08，然后开发「研发效能 Agent」（=作品集项目三）。

学习顺序：

```text
01 LangGraph 深入（Reducer 与状态设计）
  -> 02 LangGraph 进阶（并行分支与子图）
  -> 03 多 Agent 编排（Router/Supervisor/Handoff/Agent as Tool）
  -> 04 Human-in-the-loop（interrupt 与人工审批）
  -> 05 Checkpoint 持久化与长任务恢复
  -> 06 Deep Agents（规划/子 Agent/文件系统）
  -> 07 Event-driven Workflow 与异步长任务
  -> 08 综合实践：研发效能 Agent（M1 线性 -> M2 并行 -> M3 人工审核
     -> M4 持久化恢复 -> M5 异步事件驱动 -> M6 审计评测）
```

产出：研发效能 Agent 项目（作品集项目三），补齐能力模型 3 的 State 深水区/多 Agent/HITL/Checkpoint/长任务。

**验收**：能向面试官讲清「确定性工作流 + 少量 Agent 决策节点」的取舍；能用图表达并行/条件/循环；能演示 interrupt 审批与断点恢复。

### 阶段 5：评测、可观测性与生产化（文档待整理，约 4~5 周）

按阶段 1~4 的文档风格，建议拆分为 8 篇（覆盖能力模型 5 全部 + 能力模型 6 的监控与部署部分）：

| 文档 | 主题 | 覆盖能力 |
| --- | --- | --- |
| 01 | 评测方法论与 Golden Dataset：评测集设计（正常/模糊/无答案/越权/注入/长上下文/工具失败/多轮/中英）、离线 vs 在线评测 | Golden Dataset、回归测试 |
| 02 | 指标详解与评测实现：Answer Correctness / Faithfulness / Context Recall / Precision、Tool Call Accuracy、Task Completion Rate、Latency、Cost、Error Rate、Human Approval Rate | 全部评测指标 |
| 03 | Langfuse/LangSmith 可观测性：Tracing 接入、Token/延迟/成本监控、Prompt 与模型版本管理、会话回放 | 可观测性字段、版本管理 |
| 04 | OpenTelemetry 与自定义 Tracing：trace_id/span 设计、与 FastAPI/LangChain 集成 | OpenTelemetry |
| 05 | Agent 安全评测与加固：幻觉检测、Prompt Injection 红队用例、PII 脱敏验证、越权/审计复核、限流熔断降级压测 | 安全评测闭环 |
| 06 | Prometheus + Grafana：指标暴露（工具成功率/任务完成率/P95 延迟/错误率）、告警规则 | 监控与告警 |
| 07 | 生产化部署：Docker 镜像、K8s 部署要点、CI/CD 流水线、模型/Prompt 发布策略、降级与容灾 | 部署与 CI/CD |
| 08 | 阶段 5 综合实践：把阶段 3 或 4 的项目接入全链路观测 + 50~200 条评测集 + 产出评测报告 | 综合交付 |

**产出**：给已有项目（企业运维分析 Agent / 研发效能 Agent）接入 Langfuse/OTel + 评测报告 + README 实测指标。

### 能力补丁包（阶段 4/5 之后，补能力模型残留缺口，约 1~2 周）

这些是阶段 0~5 资料都没覆盖、但能力模型明确列出的条目：

| 补丁 | 主题 | 覆盖能力 | 建议形式 |
| --- | --- | --- | --- |
| 1 | **A2A 与 Agent 间通信**：A2A 协议（Agent Card/Task 生命周期）、Webhook 收发、Durable Workflow 语义、与 MCP 的定位区别（MCP=能力接入，A2A=Agent 协作） | 能力模型 4 | 概念 + 小型 demo |
| 2 | **Memory 设计**：短期/长期记忆、向量记忆（对话摘要、用户画像）、LangGraph Store、记忆读写时机与隐私边界 | 能力模型 3 | 概念 + 练习 |
| 3 | **Reflection 模式**：Self-Critique、Plan-and-Execute、ReAct + Reflection 组合、输出修正循环 | 能力模型 3 | 概念 + 模式实现 |
| 4 | **多模态与 Responses API**：图像/文档输入、OpenAI Responses API 与 Chat API 差异（含 Function Calling 演变）、多模态工具调用 | 能力模型 1 | 1 篇文档 |
| 5 | **幂等与补偿机制**：写操作幂等键、分布式事务补偿（Saga 类比）、长任务的部分成功回滚 | 能力模型 3 | 概念 + 设计题 |

### 选学包 A：平台能力扩展（按需 1~2 周/项，不进主线）

| 主题 | 学什么 | 对应能力 |
| --- | --- | --- |
| Redis | 缓存、分布式锁、限流计数器、任务队列（Agent 记忆/会话也可存） | 能力模型 6 |
| Elasticsearch / OpenSearch | 企业级检索、RAG 生产化（替换/补充向量库）、Hybrid 与聚合 | 能力模型 6 |
| Celery / Temporal | Python 侧异步任务（Celery）；Durable Execution 与长任务恢复的生产实现（Temporal，对照 LangGraph checkpoint） | 能力模型 6 |
| Docker + Kubernetes | 镜像化 Agent 服务、K8s 部署/水平扩展/配置与密钥 | 能力模型 6 |
| CI/CD + 云平台 | GitHub Actions 流水线（lint/test/build/deploy）、云上模型网关与推理成本 | 能力模型 6 |

### 框架了解包（每个 1~2 天，能讲清定位与适用场景即可）

LlamaIndex（数据/RAG 框架）、OpenAI Agents SDK（Guardrails/Handoff/Tracing）、CrewAI（角色型多 Agent）、smolagents（轻量/Code Agent）、microsoft/agent-framework（生产级 Agent/人工介入/可观测性）。建议用一张对比表沉淀：定位、编排方式、记忆/HITL 支持、何时选它 vs LangGraph。

### Java 拓展练习（投入 10%~15%，1 周内）

用 Spring AI 或 LangChain4j 实现一个简单 Tool Calling 服务，通过 REST 调用你 Python 的 LangGraph Agent——目标不是学会 Java Agent 开发，而是能讲清「Java 服务如何集成 Python Agent 能力」（企业内部集成场景）。

### 作品集整合（第 6 个月）

- 项目一：企业知识库 RAG（阶段2）
- 项目二：企业工具调用 Agent（阶段3）
- 项目三：研发流程 Agent（阶段4）
- 三个项目 README 补齐：架构图（文字版）、功能列表、**实测评测指标**（用阶段 5 的评测输出：工具调用成功率、任务完成率、P95 延迟、Token 成本、安全用例通过数）
- 简历一句话模板参考路线原文（可验证指标式描述）

---

## 三、时间表（第 4~6 个月）

| 时间 | 内容 | 里程碑 |
| --- | --- | --- |
| 第 4 个月 | 阶段 4 文档 01~08 + 研发效能 Agent | 作品集项目三完成 |
| 第 5 个月 | 阶段 5 文档 01~08 + 对已有项目做评测/观测/加固改造 | 项目 README 有实测指标 |
| 第 6 个月前半月 | 补丁包 1~5 + 框架了解包 + Java 拓展练习 | 能力模型条目全部点亮 |
| 第 6 个月后半月 | 作品集整合 + 简历指标 + 面试演练 | 三个项目可演示、可讲解 |

## 四、终点验收清单（对照能力模型逐项勾选）

- [ ] 能力模型 1：LLM 应用开发（含多模态、Prompt 版本管理）
- [ ] 能力模型 2：RAG 知识库工程（自核补齐 Parent-Child/Query Rewrite/Multi-Query/评测）
- [ ] 能力模型 3：Agent 核心能力（含 Memory、Reflection、补偿机制）
- [ ] 能力模型 4：MCP 与 Agent 协议（含 A2A、Webhook、Durable Workflow）
- [ ] 能力模型 5：Agent 工程化（评测集、指标、观测、安全评测、版本管理）
- [ ] 能力模型 6：Python 平台能力（DB/缓存/任务/监控/部署，选学项至少 Docker + 一种监控）
- [ ] Java 拓展小练习完成
- [ ] 三个作品集项目均有 README + 实测指标
