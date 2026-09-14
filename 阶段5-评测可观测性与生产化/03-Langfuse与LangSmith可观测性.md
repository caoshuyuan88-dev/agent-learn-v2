# Langfuse 与 LangSmith：Agent 可观测性与版本管理

> 本文定位：阶段 3、4 你写的 Agent 都能跑，但**跑起来之后你根本不知道它内部发生了什么**——用户说「结果不对」，你手上只有三行日志；老板问「这个月花了多少钱」，你答不上来；改了 prompt 之后效果变好还是变差，只能靠感觉。本文解决这三件事：把 Agent 执行过程变成可查询的**结构化 Trace**，把 Token/成本/时延变成可聚合的数字（[02 篇](02-评测指标详解与实现.md)线上指标的来源），把 Prompt 与模型当成**有版本的代码**来管理。本篇是能力模型第 5 块「Agent 工程化」的可观测性主干，与 [04 篇](04-OpenTelemetry与自定义Tracing.md)（OTel 标准协议）、[06 篇](06-Prometheus与Grafana监控告警.md)（Prometheus 聚合指标）构成「个体 → 标准 → 总体」的观测链。前置要求：跑通过阶段 3 企业运维分析 Agent 或阶段 4 研发效能 Agent，Python 3.11+，LangChain / LangGraph 1.x 口径。

## 学习目标

学完本文，你应该能：

- 说清 LLM 应用为什么需要专门的观测方案，以及三支柱（Traces / Logs / Metrics）在 03/04/06 三篇之间的分工；
- 在 Langfuse（开源自托管）与 LangSmith（LangChain 官方 SaaS）之间做出有理有据的选型；
- 解释 Trace / Span / Generation / Session / User / Score / Dataset 的概念与层级关系；
- 列出「一条合格 Agent Trace」必须携带的字段，并知道哪些字段必须脱敏；
- 用 `CallbackHandler` 与 `@observe` 把 LangChain / LangGraph 接入 Langfuse，并写出可复用的 `obs.py`；
- 在 FastAPI 侧给每次请求挂 trace，并把 `trace_id` 回传给前端；
- 从 trace 聚合出成本 / 时延 / 失败率报表，并说清与 02 篇、06 篇的口径对齐方式；
- 用 Prompt Management 做 prompt 版本化、按用户稳定分桶的 A/B 与模型回归；
- 从失败 trace 排障并把失败样本回灌成评测用例，以及用 Docker Compose 自托管 Langfuse 并处理采样、flush、多实例问题。

## 一、为什么 LLM 应用需要专门的观测

### 1.1 一个真实场景

阶段 3 的运维 Agent 上线后收到反馈：「帮我看看 order-service 昨天为什么响应变慢」→ Agent 答「响应时间在正常范围内」→ 用户说「可 Grafana 上明明有毛刺」。

翻日志只有三行：开始处理、调用 `query_metrics`、请求完成。**你不知道**：Agent 把哪个时间窗口传给了工具？「昨天」被解析成 UTC 还是本地时区？工具返回了什么？模型在什么上下文下说出「正常范围」？这次花了多少 token 多少钱？这轮对话前面还说过什么？——传统日志只能告诉你「发生了什么动作」，而 Agent 的问题是**「模型在某段上下文下做了某个决策，然后基于某段工具输出生成回答」**，这是一条有结构、有嵌套、带 payload 的链。这就是 LLM 可观测性（LLM Observability）要解决的。

### 1.2 LLM Tracing vs 传统 APM

APM（Application Performance Monitoring，应用性能监控）工具（SkyWalking、Zipkin、Datadog APM）擅长回答「哪个接口慢」，但对 Agent 有四个先天不足：

| 维度 | 传统 APM | LLM / Agent Tracing |
| --- | --- | --- |
| 输入输出 | 结构化小字段，可索引 | Prompt / 回答是**长文本甚至多模态**，动辄上万 token，必须存原始 payload 且支持检索 |
| 调用结构 | 一次请求 = 一条扁平链路 | **多步嵌套**：Agent → 模型 → 工具 → 子 Agent → 模型，层级深且动态（循环、条件分支） |
| 计量单位 | 毫秒、字节、QPS | 毫秒 **+ token + 成本（美元）**——同一段代码因 token 数不同可差 100 倍 |
| 版本维度 | 代码版本 = 部署版本 | **Prompt 版本、模型版本、工具版本**都是运行时变量，换 prompt 行为完全不同 |
| 评测维度 | 无 | Trace 要能被打分（Score）、沉淀成数据集、被回放比对 |

一句话：**APM 观测「系统」，LLM Tracing 观测「决策」**。这不是功能多寡，而是数据模型的根本差异——所以这个品类是独立长出来的。

### 1.3 三支柱与阶段 5 的篇目分工

可观测性三支柱（Three Pillars）：

| 支柱 | 数据形态 | 回答的问题 | 成本特征 |
| --- | --- | --- | --- |
| Traces（链路） | 树状 span + payload | 这一次请求**具体**做了什么 | 最贵（存原始文本） |
| Logs（日志） | 时间戳文本行 | 系统**当时**打印了什么 | 中等，量大 |
| Metrics（指标） | 数值时间序列 | 系统**整体**健不健康 | 最便宜，可长期保留 |

三篇文档各管一层，别混为一谈：

| 篇目 | 层级 | 回答什么问题 | 数据形态 | 典型保留期 |
| --- | --- | --- | --- | --- |
| **03 本篇** | 产品级 Trace | 「8823 号请求那次为什么答错」 | 结构化 trace + 原始 payload | 天 ~ 周 |
| [04 篇](04-OpenTelemetry与自定义Tracing.md) | OTel 标准协议 | 「如何跨服务/跨语言统一追踪、怎么设计 trace_id 体系」 | OTel Span（vendor-neutral） | 取决于后端 |
| [06 篇](06-Prometheus与Grafana监控告警.md) | 聚合指标层 | 「过去 1 小时成功率是否跌破 95%」 | 数值时间序列 + 告警 | 月 ~ 年 |

关系是**「个体 → 因果 → 总体」**：Trace 是分子级证据，Metrics 是统计结论。你不可能靠翻 10 万条 trace 发现「P95 上升」，也不能靠一张 Grafana 曲线查出「第 8823 号请求为何失败」。**06 篇的指标应尽可能由 03 篇的 trace 字段聚合而来**（5.5 给口径）。

### 1.4 类比 Java

一条 Agent Trace 相当于三样东西的合体：**Sleuth/Zipkin 的分布式追踪**（trace_id/span_id 与父子层级）+ **请求响应体审计日志**（完整入参出参可检索）+ **计费埋点**（每次调用的用量与单价）。区别是：Java 里这三件事通常由三个系统承担，而在 LLM 应用里它们是**同一条链上的同一份数据**——因为「慢」「贵」「答错」的原因，往往是同一个 token。

## 二、产品选型：Langfuse vs LangSmith

**Langfuse**：开源 LLM 工程平台（开源版可完全自托管 + 商业云服务），覆盖 Observability、Prompt Management、Evaluation、Datasets，并提供 OpenTelemetry 兼容的接收端点。**LangSmith**：LangChain 官方 SaaS 平台，覆盖 Tracing、Evaluation、Prompt 管理、数据集，与 LangChain / LangGraph 的集成是「零配置级」的。

| 维度 | Langfuse | LangSmith |
| --- | --- | --- |
| 部署形态 | 云服务 + **完整开源自托管**（Docker Compose / K8s） | SaaS 为主，企业版可选混合部署；社区版无自托管 |
| 数据主权 | 数据留在自己 VPC / 内网，可满足「数据不出境」 | 默认上传官方云（可选区域，但仍是第三方） |
| 集成成本 | LangChain/LangGraph 官方集成 + OTel + 多框架 SDK；自托管需维护 Postgres/ClickHouse/Redis/S3 | LangChain/LangGraph 一个环境变量即可；其他框架需自埋点 |
| 免费额度 | 云端 Hobby 层免费；**自托管完全免费** | Developer 层免费（trace 条数受限） |
| 评测能力 | 内置 LLM-as-a-Judge、人工标注队列、Dataset 实验、Score API | 评测工作流更成熟：数据集实验、自定义 evaluator、与测试框架集成的 SDK |
| Prompt 管理 | 版本 + label + 缓存 + Playground | Prompt Hub，与 LangChain `pull` 集成 |
| OTel 兼容 | **原生 OTLP 端点**，任何 OTel 应用可接入 | 支持 OTel 摄入，生态围绕 LangChain 回调 |
| 适合谁 | 需要数据主权 / 想练自建全栈 / 作品集 | 重度 LangChain 用户 / 想最低成本起步 |

表中额度与功能边界迭代很快，**以官方定价页与文档为准**。选型判断：

- **个人学习 + 作品集：Langfuse 起步，进阶做一次自托管。** ① 能亲历「Postgres + ClickHouse + Redis + 对象存储」这套真实观测栈，面试有得聊；② 数据模型与 OTel 高度对应，可平滑迁移到 04 篇；③ OTel 兼容意味着埋点不被产品锁定。
- **企业内网 / 面向客户的交付：必须自托管。** Agent 的 input/output 几乎必然含业务数据（工单内容、日志片段、用户身份、内网 IP、生产拓扑），传到第三方云通常过不了安全评审；很多企业的合规要求是「生产数据不得出境/出内网」。但要正视**自托管隐性成本**（DevOps 投入 + ClickHouse 存储 + 升级维护）：团队只有一人时可先用 SaaS，但把接入层写成**可切换**的（本文 `obs.py` 即为此设计）。
- **LangSmith 什么时候是对的**：100% 用 LangChain/LangGraph、团队无自托管运维能力、数据敏感度可接受。

## 三、核心数据模型

### 3.1 七个核心概念

| 概念 | 定义 | 类比 |
| --- | --- | --- |
| **Trace（追踪）** | 一次端到端请求的整条链，顶层容器，有唯一 `trace_id` | 一次 HTTP 请求的调用链 |
| **Observation（观测点）** | Trace 内部的一个节点，可嵌套；分 Span / Generation / Event 三型 | 调用链上的一个 span |
| **Span（跨度）** | 一个普通步骤（图节点、工具调用、检索、业务逻辑），可嵌套 | 一个方法调用 |
| **Generation（生成）** | 一次**模型调用**，携带 `model` / `input`(messages) / `output` / `usage`(token) | 一次 SQL 执行（可计量、有成本） |
| **Event（事件）** | 瞬时标记（无时长），用于打点，如「命中缓存」「触发降级」 | 一条超时日志 |
| **Session（会话）** | 一组 trace 的集合，代表一次多轮对话 / 一个任务，靠 `session_id` 关联 | 一次 HTTP Session；一个 `thread_id` |
| **User（用户）** | trace 的归属人，靠 `user_id` 关联，用于按人分析行为与成本 | 审计日志里的操作者 |
| **Score（评分）** | 挂在 trace / observation / session / dataset run 上的打分（数值、分类、布尔） | 单元测试结果 |
| **Dataset（数据集）** | 一组 `DatasetItem`（input + expected_output），用于离线评测与回归 | 测试夹具（fixture）集合 |

Langfuse 文档以 **Observation** 作统称，Span / Generation / Event 是其子类型；别处常把「Span」当统称（OTel 只有 Span 概念）。读文档时以官方当前定义为准。

### 3.2 层级关系（文字版层级图）

```text
User "u_1024"
 └─ Session "thread-task-778"                      ← 一次任务 / 一次多轮对话
     ├─ Trace "tr_aaa"                            ← 第 1 轮
     │   └─ Span "POST /agent/chat"               ← HTTP 层（FastAPI 挂的）
     │       └─ Span "graph:ops_agent"            ← LangGraph 整图
     │           ├─ Span "node:plan"
     │           │   └─ Generation "gpt-4o-mini"  ← 模型调用（带 token / 成本）
     │           ├─ Span "node:call_tools"
     │           │   ├─ Span "tool:query_metrics" ← 工具调用
     │           │   │   └─ Event "cache_hit"     ← 打点（无时长）
     │           │   └─ Generation "gpt-4o-mini"
     │           └─ Span "node:compose_answer"
     │               └─ Generation "gpt-4o-mini"
     │   (Score "answer_correctness" = 0.8 可挂 Span / Trace / Session)
     └─ Trace "tr_bbb"                             ← 第 2 轮追问（同 session）

Dataset "ops-agent-golden" → DatasetItem × N (input / expected_output / metadata)
 └─ DatasetRun（一次实验）→ 每 item 产生一个 Trace + N 个 Score
```

三条关键规则：① **Trace 与 Session 是「一对多」**，靠 `session_id` 关联而非嵌套，这样多轮对话与阶段 4 长任务的多阶段（M1~M6）能聚合来看；② **Generation 是唯一能算钱的 Observation**，只有带 `model` + `usage` 的节点产生成本；③ **Score 可挂任意层级**——单轮质量挂 trace，会话满意度挂 session，单次工具正确性挂那个 tool span。

### 3.3 一条 Agent Trace 应该包含哪些字段

把它当作接入 checklist。带 ✅ 的必填；业务字段统一放 `metadata`。

| 字段 | 层级 | 必填 | 说明 / 示例 |
| --- | --- | --- | --- |
| `trace_id` | Trace | ✅ | SDK 生成；也可自己生成后回传前端（4.7） |
| `name` | 每个 Observation | ✅ | **要有业务含义**：`node:call_tools`、`tool:query_metrics`（10.4） |
| `input` / `output` | 每个 Observation | ✅ | 原始 payload；Generation 的是 messages 与 completion |
| `model` | Generation | ✅ | 如 `gpt-4o-mini`、`deepseek-chat`；**缺失会导致成本为 0**（10.5） |
| `model_parameters` | Generation | ⬜ | `temperature`、`top_p`、`max_tokens` |
| `usage` | Generation | ✅ | input/output/total token；LangChain 集成自动提取，自研封装需手填 |
| `cost` | Generation | ✅ | 由「模型 + token 数」按价格表算出（5.4） |
| `latency`(start/end) | 每个 Observation | ✅ | 自动记录，P95 时延报表的来源 |
| `level` | 每个 Observation | ✅ | `DEBUG`/`DEFAULT`/`WARNING`/`ERROR`，失败率报表的来源 |
| `status_message` | 每个 Observation | ⬜ | 异常摘要（截断，别塞整个 traceback） |
| `user_id` | Trace | ✅ | 生产必填：没它就无法按人排查、按人算成本 |
| `session_id` | Trace | ✅ | 多轮/长任务必填，建议直接复用阶段 4 的 `thread_id` |
| `tags` | Trace | ✅ | 受控词表 `key:value`，如 `["env:prod","agent:ops","prompt:v12"]` |
| `metadata` | 任意层级 | ⬜ | `task_id`、`tenant_id`、`tool_attempt`、`route`、`time_window` |
| 工具名与参数 | Span(tool) | ✅ | 阶段 3 的工具调用工程化尤其需要 |
| `release` | Trace / metadata | ✅ | 当前代码版本，用于「哪个版本开始变差」 |
| `environment` | Trace | ⬜ | `prod`/`staging`/`dev`，防测试数据污染生产报表 |
| `parent_observation_id` | Observation | 自动 | SDK 维护，不要手填 |

### 3.4 哪些字段必须脱敏

Trace 会全量存下原始 payload——**这是它的价值，也是最大的风险**。写入前必须处理（完整方案见 [05 篇](05-Agent安全评测与加固.md)）：

| 类别 | 例子 | 处理 |
| --- | --- | --- |
| 个人身份信息（PII） | 手机号、身份证、邮箱、姓名、地址 | 掩码为 `138****1234`、`u***@example.com` |
| 凭据与密钥 | `sk-...`、AK/SK、连接串、JWT、Cookie | **直接删除**，绝不允许进 trace |
| 内部基础设施信息 | 内网 IP、主机名、端口、K8s 命名空间 | 掩码或白名单 |
| 用户输入原文 | 工单正文、聊天记录、合同条款 | 掩码，或按授权开关决定是否存 |
| 工具原始返回 | 数据库行、日志片段、配置内容 | 截断 + 字段级掩码 |

**最小可行做法**：在 `obs.py` 里注册**一个**统一掩码函数，对所有 input/output 生效。**必须在 SDK 层做，而不是在每个业务调用点做**——否则一定有人漏。自托管时还可在服务端再叠一层。

## 四、接入 LangChain / LangGraph

### 4.1 环境变量方式

```bash
# .env（务必加进 .gitignore）
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxx
LANGFUSE_HOST=https://cloud.langfuse.com     # 自托管改成 https://langfuse.your-company.com
LANGFUSE_TRACING_ENVIRONMENT=production
```

部分较新 SDK 同时接受 `LANGFUSE_BASE_URL`（与 `LANGFUSE_HOST` 等价）。**两个变量的命名与优先级以官方文档为准，SDK 版本可能演进**；本文统一用 `LANGFUSE_HOST`。LangSmith 侧对应 `LANGSMITH_TRACING=true` / `LANGSMITH_API_KEY` / `LANGSMITH_PROJECT`（早期版本为 `LANGCHAIN_TRACING_V2` / `LANGCHAIN_API_KEY` / `LANGCHAIN_PROJECT`，旧名仍兼容）。**以官方文档为准。**

### 4.2 两种接入方式对比

| 方式 | 代码侵入 | 覆盖范围 | 适用 | 缺点 |
| --- | --- | --- | --- | --- |
| `CallbackHandler`（LangChain 回调） | **极低**，只加一个 `callbacks` | 自动覆盖 Chain、模型、Retriever、Tool、LangGraph 节点 | 主体是 LangChain/LangGraph | 只观测「框架认识的东西」；纯 Python 业务函数不被记录 |
| `@observe` / SDK 手动 span | 中，需在函数上打装饰器 | 任意 Python 函数，与框架无关 | 自研逻辑、非 LangChain 模型调用、FastAPI 端点 | 要自己决定埋点位置；嵌套错乱会画出奇怪的树 |

**结论：两个都用，分工明确。** 用 `CallbackHandler` 白拿「框架内置的完整链路」；用 `@observe` 补「框架看不见的业务函数」（路由决策、后处理、缓存、外部系统调用）；**不要给同一个函数同时套两层**——会得到重复 span，反而更难读。

### 4.3 方式 A：CallbackHandler

Langfuse 提供官方 LangChain 集成包，与 LangChain 1.x / LangGraph 1.x 兼容。**Python SDK v3 的 `CallbackHandler` 是无参构造**（凭据从环境变量读），v2 则需把 public_key / secret_key / host 传进构造函数——**这是 v2 → v3 最常见的破坏性变更，以官方文档为准**。

```bash
pip install langfuse langchain langgraph
```

```python
# Langfuse Python SDK v3 口径（v2 为 from langfuse.callback import CallbackHandler + 构造参数）
from langfuse.langchain import CallbackHandler

handler = CallbackHandler()          # 无参，自动读 LANGFUSE_* 环境变量

config = {
    "configurable": {"thread_id": task_id},   # 阶段 4 的 Checkpoint 会话
    "callbacks": [handler],
    "metadata": {                             # v3 通过 metadata 传保留键（键名以官方文档为准）
        "langfuse_session_id": task_id,       # 复用 thread_id，与 Checkpoint 天然对齐
        "langfuse_user_id": user_id,
        "langfuse_tags": ["env:prod", "agent:ops", f"release:{RELEASE}"],
    },
}
result = agent.invoke({"messages": [("user", "查一下 order-service 昨天的错误率")]}, config=config)
```

挂上后**自动**得到：整图 span → 每个节点 span → 节点内 Generation（带 token 与成本）→ 每个工具 span。

### 4.4 方式 B：`@observe` 装饰器与手动 span

`@observe` 把任意函数变成 Observation，同步 / 异步均可：

```python
from langfuse import observe, get_client

langfuse = get_client()

@observe(name="call_llm", as_type="generation")
async def call_llm(messages: list[dict], model: str) -> str:
    resp = await openai_client.chat.completions.create(model=model, messages=messages)
    langfuse.update_current_generation(          # 自研封装必须手填 model 与 usage，否则成本为 0
        model=model,
        usage_details={"input": resp.usage.prompt_tokens,
                       "output": resp.usage.completion_tokens},
    )
    return resp.choices[0].message.content
```

要点：`as_type` 取 `span` / `generation` / `event`（**具体取值以官方文档为准**）；能静态确定 `name` 就别动态改，方便检索；`get_client()` 是进程内单例，**永远不要自己 `Langfuse(...)`**（会重复初始化 OTel provider，见 10.2）。

### 4.5 LangGraph 节点级 span 与工具 span

LangGraph 节点在 `CallbackHandler` 下自动成为 span，名字取自节点函数名。**排障效率 80% 取决于命名**：节点名用「动词 + 宾语」（`fetch_logs` / `analyze_logs` / `human_review`），避免 `node1` / `step_a` / `func`。

```python
# 节点内补 metadata（框架看不到的业务上下文）
@observe(name="node:analyze_logs", as_type="span")
async def analyze_logs_node(state: AgentState, config) -> dict:
    langfuse.update_current_span(metadata={
        "attempt": state.get("attempt", 1),        # 重试第几次（阶段 3 重试纪律）
        "degraded": state.get("degraded", False),  # 是否已降级
        "window": state.get("time_window"),        # 时间窗口——"答错"的高频原因
        "thread_id": config["configurable"]["thread_id"],
    })
    ...


# 工具 span：在函数体内补参数与失败状态，而不是再包一层同名 span
@tool
def query_metrics(service: str, start: str, end: str, metric: str = "error_rate") -> str:
    """查询指定服务在时间窗口内的指标。"""
    langfuse.update_current_span(metadata={
        "service": service, "start": start, "end": end, "metric": metric, "tz": "Asia/Shanghai",
    })
    try:
        return json.dumps(_query(service, start, end, metric), ensure_ascii=False)
    except Exception as exc:
        # 失败必须显式标红，否则失败率报表统计不到
        langfuse.update_current_span(level="ERROR", status_message=str(exc)[:500])
        raise
```

> 在 `@tool` 外层再套 `@observe` 时，**装饰顺序**会影响 span 归属，可能得到两个同名 span。若出现这种情况，去掉 `@observe`、改为函数体内 `update_current_span(...)`。**具体行为以官方文档与实测为准。**

### 4.6 完整的 `obs.py` 初始化模块

```python
"""obs.py —— 阶段 5 统一可观测性初始化模块。

SDK 口径：Langfuse Python SDK v3（OTel-based）。v2 的 langfuse.trace()/span()/generation()
与 langfuse_context 已改为 v3 的 get_client() + start_as_current_span / update_current_*
风格，升级前请读官方 upgrade path。API 细节以官方文档为准。
"""
from __future__ import annotations

import atexit
import logging
import os
import re
from contextlib import contextmanager
from typing import Any, Iterator

from langfuse import Langfuse, get_client

logger = logging.getLogger(__name__)

REQUIRED_ENV = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST")
RELEASE = os.getenv("RELEASE", "dev")
ENVIRONMENT = os.getenv("APP_ENV", "development")

# ------------------------------------------------------------------ 脱敏
_MASKS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b1[3-9]\d{9}\b"), "1**********"),                          # 手机号
    (re.compile(r"\b\d{17}[\dXx]\b"), "******************"),                  # 身份证
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "u***@***"),                     # 邮箱
    (re.compile(r"(?i)\b(?:sk|pk|ak|ghp)_[A-Za-z0-9_\-]{8,}\b"), "[REDACTED_KEY]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[REDACTED_IP]"),             # 内网 IP
    (re.compile(r"(?i)(bearer\s+|password[=:]\s*)\S+"), r"\1[REDACTED]"),      # Token / 口令
]


def mask_text(value: Any) -> Any:
    """统一脱敏；非字符串原样返回（列表/字典由 SDK 逐项处理）。"""
    if not isinstance(value, str):
        return value
    for pattern, repl in _MASKS:
        value = pattern.sub(repl, value)
    return value


# ------------------------------------------------------------------ 初始化
_client: Langfuse | None = None


def init_observability(service_name: str = "ops-agent") -> Langfuse | None:
    """初始化客户端。缺凭据时返回 None（观测降级为关闭，不影响主流程）。"""
    global _client
    if _client is not None:
        return _client

    missing = [k for k in REQUIRED_ENV if not os.getenv(k)]
    if missing:
        logger.warning("Langfuse 未启用：缺少 %s（观测降级为关闭）", ", ".join(missing))
        return None

    os.environ.setdefault("LANGFUSE_TRACING_ENVIRONMENT", ENVIRONMENT)
    client = get_client()                       # v3：读环境变量 + 进程内单例

    try:
        client._mask = mask_text                # 注册统一脱敏钩子（名称与签名以官方文档为准）
    except Exception:                           # pragma: no cover
        logger.debug("当前 SDK 未暴露 mask 钩子，请在应用层调用 mask_text()")

    atexit.register(flush_observability)         # 进程退出兜底，避免丢 trace
    _client = client
    logger.info("Langfuse 已启用 service=%s env=%s release=%s", service_name, ENVIRONMENT, RELEASE)
    return client


def flush_observability() -> None:
    """强制把缓冲区数据发出去。短脚本 / 退出钩子 / 单测收尾必须调用。"""
    if _client is None:
        return
    try:
        _client.flush()
    except Exception:                            # pragma: no cover
        logger.exception("Langfuse flush 失败（可能网络不可达）")


# ------------------------------------------------------------ trace 上下文
def trace_tags(*extra: str) -> list[str]:
    """受控词表：一律 key:value，禁止自由发挥（见 10.6）。"""
    return [f"env:{ENVIRONMENT}", f"release:{RELEASE}", *[t for t in extra if t]]


@contextmanager
def trace_context(
    *,
    name: str,
    user_id: str | None = None,
    session_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> Iterator[str]:
    """为一段业务逻辑开启顶层 span，并统一补齐 trace 级字段。"""
    client = get_client()
    span_kwargs: dict[str, Any] = {"name": name}
    if trace_id:
        # v3 通过 trace_context 指定外部 trace_id（参数名以官方文档为准）
        span_kwargs["trace_context"] = {"trace_id": trace_id}

    with client.start_as_current_span(**span_kwargs) as span:
        client.update_current_trace(
            user_id=user_id,
            session_id=session_id,
            tags=trace_tags(*(tags or [])),
            metadata={"release": RELEASE, **(metadata or {})},
        )
        try:
            current = client.get_current_trace_id()   # 版本不支持时改用传入的 trace_id
        except Exception:                             # pragma: no cover
            current = trace_id or ""
        try:
            yield current
        except Exception as exc:
            span.update(level="ERROR", status_message=str(exc)[:500])
            raise
```

三个设计点：① 缺凭据时返回 `None` 而非抛异常，本地开发与 CI 单测无需真实后端也能跑；② `atexit` 兜底防丢数据（9.5 展开）；③ 脱敏收敛在 `obs.py` 一处，配合代码评审「禁止绕过 obs 模块直接构造客户端」的纪律。

### 4.7 FastAPI 侧挂 trace，并把 `trace_id` 回传给前端

用**纯 ASGI 中间件**（而非 `BaseHTTPMiddleware`），保证 contextvars 与「当前 span」在整条请求链中正确传播：

```python
# middleware.py
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from obs import get_client, trace_tags

TRACE_HEADER = "X-Trace-Id"


class LangfuseTraceMiddleware:
    """把每个 HTTP 请求包成顶层 span，并把 trace_id 写回响应头。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        client = get_client()
        trace_id = Langfuse.create_trace_id()

        async def send_with_trace_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[TRACE_HEADER] = trace_id
            await send(message)

        with client.start_as_current_span(
            name=f"{scope['method']} {scope['path']}",
            trace_context={"trace_id": trace_id},
        ) as span:
            client.update_current_trace(
                tags=trace_tags("layer:api"),
                metadata={"path": scope["path"], "method": scope["method"]},
            )
            scope.setdefault("state", {})["trace_id"] = trace_id
            try:
                await self.app(scope, receive, send_with_trace_id)
            except Exception as exc:
                span.update(level="ERROR", status_message=str(exc)[:500])
                raise
```

```python
# main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from middleware import LangfuseTraceMiddleware
from obs import flush_observability, init_observability


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_observability(service_name="ops-agent")
    yield
    flush_observability()          # 关服前刷出缓冲区，避免丢数据

app = FastAPI(lifespan=lifespan)
app.add_middleware(LangfuseTraceMiddleware)


@app.post("/agent/chat")
async def chat(req: ChatRequest, request: Request):
    trace_id = request.scope["state"]["trace_id"]
    result = await run_agent(req.question, user_id=req.user_id, session_id=req.session_id)
    return {"answer": result.answer, "trace_id": trace_id}   # 前端留存，报错时回传
```

```typescript
// 前端：把 trace_id 显示给用户，报错时贴进工单
const resp = await fetch("/agent/chat", { method: "POST", body });
const traceId = resp.headers.get("X-Trace-Id");
if (!resp.ok) showErrorDialog(`请求失败，追踪号：${traceId}`);
```

若同时要走 [04 篇](04-OpenTelemetry与自定义Tracing.md) 的 OTel 标准链路，**不要另建一套 trace_id**——应复用同一上下文，让 Langfuse 作为 OTel 的一个后端（提供 OTLP 端点）。取舍见 04 篇，**以官方文档为准**。

### 4.8 一条完整调用示例

```python
# agent.py —— 阶段 4 研发效能 Agent
from langchain.agents import create_agent            # LangChain 1.x 口径
from langfuse.langchain import CallbackHandler
from obs import flush_observability, init_observability, trace_context

init_observability(service_name="dev-efficiency-agent")
handler = CallbackHandler()


async def run_agent(question: str, *, user_id: str, session_id: str, trace_id: str | None = None):
    with trace_context(
        name="agent.run",
        user_id=user_id,
        session_id=session_id,                        # 复用阶段 4 的 thread_id
        tags=["agent:dev-efficiency", "flow:analysis"],
        metadata={"question_len": len(question)},
        trace_id=trace_id,
    ):
        return await agent.ainvoke(
            {"messages": [{"role": "user", "content": question}]},
            config={
                "configurable": {"thread_id": session_id},   # Checkpoint 会话（阶段 4）
                "callbacks": [handler],                      # ← LangChain/LangGraph 自动埋点
                "metadata": {"langfuse_session_id": session_id, "langfuse_user_id": user_id},
            },
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_agent("统计上个迭代的缺陷密度", user_id="u_1024", session_id="thread-778"))
    flush_observability()          # 短脚本不 flush 就退出 = trace 丢失
```

跑完在面板上应看到：`agent.run` span → 图节点 → 每次模型调用（带 token 与成本）→ 每个工具调用。**若只看到一个孤零零的 `agent.run`，检查 `callbacks` 是否真的传进了 `ainvoke` 的 config**——把 handler 传给 Agent 构造函数是最常见的错法。

## 五、Token、延迟、成本监控

### 5.1 数据从哪来

| 数字 | 来源 | 自动程度 |
| --- | --- | --- |
| Token 用量 | 模型响应的 `usage`（LangChain 放进 `usage_metadata`） | LangChain 集成全自动；裸 SDK 需 `update_current_generation(usage_details=...)` |
| 延迟 | span 的 start/end 时间戳 | 全自动 |
| 成本 | **模型名 + token 数 × 价格表** | 需 Langfuse 认识你的模型（5.4） |

**关键认知：成本不是模型返回的，是算出来的。** 这是「成本为 0」问题的根因（10.5）。

### 5.2 常用报表与口径

| 报表 | 口径 | 用途 |
| --- | --- | --- |
| 每日请求量 | 按天统计 trace 数 | 容量规划、增长趋势 |
| 每日成本 | 按天求和所有 Generation 的 `cost` | 预算与告警 |
| 单次任务平均成本 | 总成本 / trace 数（按 `agent:*` 分组） | 单位经济模型 |
| P50/P95/P99 时延 | 按**顶层 span** duration 分位 | 用户体验 |
| 失败率 | `level=ERROR` 的 trace 占比 | 质量水位（06 篇告警规则） |
| 按工具分布 | 按 `tool:*` 分组统计调用量/失败率/耗时 | 找出最不可靠的工具 |
| 按用户分布 | 按 `user_id` 分组统计成本与调用量 | 异常调用方、按租户计费 |
| 按模型分布 | 按 `model` 分组统计成本与 token | 降本（大模型换小模型）依据 |
| 工具调用成功率 | 工具 span 中 `level != ERROR` 的占比 | 阶段 3 Tool Call Accuracy 的线上版 |

**时延口径的坑**：一次请求的总时延 = 顶层 span 的 duration，**不等于**所有 Generation 时延之和（有并行、工具耗时、排队）。报表里务必写清是哪一个。

### 5.3 成本归属

| 归属维度 | 靠哪个字段 | 典型问题 |
| --- | --- | --- |
| 按会话 | `session_id` | 「一个长任务烧了 2 块钱，值得吗？」 |
| 按用户 | `user_id` | 「哪个租户最费钱？有没有异常刷量？」 |
| 按模型 | `model` | 「换小模型能省多少？」 |
| 按功能 | `tags` 里的 `agent:*` | 「运维 Agent 和研发效能 Agent 谁更贵？」 |
| 按版本 | `release` | 「新版本是否让成本上涨了 30%？」 |

**只要 3.3 的字段填全，成本归属就是免费的**；反之 `user_id` 忘了填，你永远算不出按用户成本。这正是「可观测性字段」被单列成能力项的原因。

### 5.4 模型价格配置

**Langfuse 云**内置主流模型（OpenAI / Anthropic / Google / Mistral 等）价格表，通常随厂商调价更新；**自托管 / 私有模型 / 国产模型**（如 `deepseek-chat`、`qwen-max`）需在 Settings → Models 里**自定义模型定义**，填 `match pattern`（正则匹配 `model` 名）、`unit`（TOKENS / CHARACTERS）与各类 token 单价。价格与折扣会变（缓存价、批量价），**一切以厂商官方价格页为准**并定期核对。单价配错，成本日报就会稳定地错——建议做一次交叉验证：一天的 token 总量 × 官方单价，与账单对账。

### 5.5 与 02 篇、06 篇的口径对齐

这是本篇作为「数据来源」的核心契约：**三处定义同一指标时口径必须完全一致**，否则 Grafana 上的数字会和评测报告互相矛盾。

| 指标 | 03 篇（Trace 层） | 02 篇（评测层） | 06 篇（Prometheus 层） |
| --- | --- | --- | --- |
| Task Completion Rate | 线上 trace 中任务成功占比（Score 或 `level` 判定） | 离线评测集完成率 | `agent_task_success_total / agent_task_total` |
| Tool Call Accuracy | 工具 span 中参数正确且调用成功的占比 | 工具序列与期望的匹配度 | `agent_tool_call_total{result="ok"\|"error"}` |
| P95 Latency | 顶层 span duration 的 P95 | 评测批次端到端耗时 P95 | `histogram_quantile(0.95, agent_request_duration_seconds_bucket)` |
| Cost | Generation `cost` 求和 | 评测批次成本估算 | `agent_cost_usd_total` |
| Error Rate | `level=ERROR` 的 trace 占比 | 评测中失败用例占比 | `agent_request_errors_total / agent_request_total` |

**落地建议**：让 06 篇的指标尽量**从 trace 派生**——(a) 应用侧观测到结果时同时 `Counter.inc()` / `Histogram.observe()`（最简单、实时）；(b) 周期性从 Langfuse 的查询能力聚合后推给 Prometheus。**时延与错误率用 (a)，成本用 (b)**（需价格表，批处理更稳）。查询接口以官方文档为准。

## 六、Prompt 与模型版本管理

### 6.1 为什么 prompt 要像代码一样版本化

Prompt 是你系统里唯一**「改了就能立刻改变行为，却没有编译错误、没有类型检查、没有测试拦住你」**的东西。它同时具备三个危险属性：**易改**（改一个词能让效果从 90% 掉到 60%）、**难测**（没人会主动跑全量评测）、**难追溯**（效果变差时你甚至不确定它何时被改过，尤其是产品同学直接在后台改）。所以 prompt 必须有：**版本号 + 标签 + 变更记录 + 评测门禁**。前三件由 Prompt Management 提供，第四件靠 [01 篇](01-评测方法论与GoldenDataset设计.md) 的评测集与 [07 篇](07-生产化部署与CI-CD.md) 的 CI 门禁。

### 6.2 Prompt Management 用法

三个动作：**创建（带 label）→ 取用（按 label 或 version）→ 编译（填变量）**。

```python
from langfuse import get_client

langfuse = get_client()

# ① 创建 / 发布新版本（在脚本或 CI 里执行，不要在请求路径里做）
langfuse.create_prompt(
    name="ops-agent-system",
    type="chat",                                   # "text" 或 "chat"
    prompt=[
        {"role": "system", "content": (
            "你是企业运维分析助手。当前时间窗口：{{window}}。\n"
            "规则：1) 只用工具返回的数据回答，不得推测；\n"
            "2) 数据不足以判断时明确说「数据不足」并说明缺什么；\n"
            "3) 涉及写操作必须先请求人工确认。"
        )},
        {"role": "user", "content": "{{question}}"},
    ],
    labels=["production"],                         # 线上取用的就是它
    tags=["ops-agent", "v12"],
    config={"model": "gpt-4o-mini", "temperature": 0.2},
    commit_message="收紧时间窗口约束，禁止推测",
)

# ② 取用（可指定 label 或 version；cache_ttl_seconds 控制本地缓存）
prompt = langfuse.get_prompt("ops-agent-system", label="production", cache_ttl_seconds=60)

# ③ 编译变量
messages = prompt.compile(window="2024-05-19 00:00~24:00 (Asia/Shanghai)", question="为什么变慢？")
```

**版本与 label 的语义**（最容易搞混的地方）：

| 概念 | 含义 | 会不会自动变 |
| --- | --- | --- |
| `version` | 每次 `create_prompt` 自增的整数，**内容不可变** | 否，永远指向同一份内容 |
| `label` | 指向某个 version 的**可移动指针**：`production`、`candidate`、`staging` | 是，重新发布即移动 |
| `latest` | 特殊标签，总指向最新版本 | 是 |

**纪律：代码里永远按 `label` 取，不按 `version` 取。** 按 version 取 = 硬编码，等于放弃「不发版就切 prompt」的能力——而那正是 prompt 管理平台的核心价值。

### 6.3 与 LangChain 集成

```python
from langchain_core.prompts import ChatPromptTemplate

prompt = langfuse.get_prompt("ops-agent-system", label="production")
lc_prompt: ChatPromptTemplate = prompt.get_langchain_prompt()   # 方法名以官方文档为准
chain = lc_prompt | llm
```

**关键收益**：用 Prompt Management 取到的 prompt 会**自动关联到 trace**（携带 name/version），于是你能直接在面板上做「按 prompt 版本对比效果」；把 prompt 写死在代码里就丢掉这层关联。**降级设计**：`get_prompt()` 失败时回退到代码内默认 prompt 并记 warning——配置服务不可用不应拖垮业务。

### 6.4 A/B 与灰度

| 方案 | 做法 | 何时用 |
| --- | --- | --- |
| **按用户稳定分桶**（推荐） | 用 `user_id` 哈希分桶，同一用户始终看同一版本 | 面向 C 端的体验型改动；同一会话行为要一致 |
| **按比例随机** | 每次请求按比例取 `candidate` / `production` | 后台任务型 Agent；样本量要求高 |
| **影子模式（Shadow）** | 线上只走 production，candidate 异步跑一份并打分 | 高风险改动（涉及写操作、审批） |

```python
import hashlib

def pick_prompt_label(user_id: str, experiment: str, treat_ratio: float = 0.1) -> str:
    """稳定分桶：同一用户永远落在同一组。"""
    digest = hashlib.sha256(f"{experiment}:{user_id}".encode()).hexdigest()
    return "candidate" if int(digest[:8], 16) % 100 < int(treat_ratio * 100) else "production"


label = pick_prompt_label(user_id, experiment="ops-prompt-v13", treat_ratio=0.1)
prompt = langfuse.get_prompt("ops-agent-system", label=label, cache_ttl_seconds=60)

# 分组信息必须写进 trace，否则事后无法对比两组指标！
tags = ["agent:ops", f"prompt_label:{label}"]
metadata = {"experiment": "ops-prompt-v13", "variant": label}
```

**灰度分析的黄金法则：打了分流，就必须把分组写进 trace。** 否则一半流量走了新 prompt，你却在面板上分不出是哪一半——这次实验等于白做。

### 6.5 模型版本切换与回归

模型升级与 prompt 改动是一件事的两面，纪律一致：① 模型名写进 trace（Generation 的 `model` 自动记录），并用 `release` tag 绑定发布版本；② **切换前必须跑评测集回归**（[01 篇](01-评测方法论与GoldenDataset设计.md) 数据集 + [02 篇](02-评测指标详解与实现.md) 指标），跨模型对比要**同时看质量与成本**（新模型可能分数持平成本减半，也可能分数高一档但 P95 翻倍）；③ 灰度按用户分桶，先 5%~10%；④ **准备好回滚**——模型回滚应是改一个 label/配置，不该需要重新部署（[07 篇](07-生产化部署与CI-CD.md) 的「配置与代码分离」）；⑤ **prompt 变更后必须重跑评测集**，这是写进 CI 的硬门禁。

```text
prompt / 模型变更流程（写进项目 README）
  create_prompt(label=candidate) → CI 跑 Golden Dataset（01/02 篇）
    → 分数不低于基线？否 → 打回
    → 是 → 人工抽查 10~20 条 diff（按 prompt 版本对比 trace）
    → label: candidate → production（或灰度 10% 用户）
    → 观察线上指标 24h（5.2 报表：失败率、成本、时延）
    → 异常 → 把 production 指回旧 version（回滚，无需发版）
```

## 七、会话回放与排障

### 7.1 从失败报告回溯

有了 `X-Trace-Id` 回传，排障从「翻日志猜」变成「直达」：

```text
用户反馈「结果不对」+ trace_id → 面板搜索 trace_id → 定位那一条 trace，自上而下看 span 树
① 顶层 span：时延多少？超时了吗？level 是否 ERROR？
② 图节点 span：哪个节点吃掉大部分时间？（往往是某个工具）
③ 工具 span：参数是什么？（90% 的「答错」源于参数错：时间窗口、服务名、单位）
④ Generation：模型看到的完整 prompt 是什么？工具返回内容进去了吗？
⑤ Score / feedback：这条被打分了吗？人工评价是什么？
```

### 7.2 按 session 看多轮上下文，按 user 看行为

- **按 Session**：把同一 `session_id`（= 阶段 4 的 `thread_id`）下的多条 trace 排成时间线，能看到「第一轮问什么、答什么、第二轮追问什么」。**上下文丢失、指代消解错误、记忆污染**这三类问题只有在这个视图下才看得见。
- **按 User**：聚合某用户所有 trace，能发现「他总是触发某个失败分支」「他的单次成本是平均值的 10 倍」。
- 阶段 4 的长任务尤其要用 session 视图：一个任务跨 M1~M6、可能中断恢复多次，session 是唯一能看清全貌的地方。

### 7.3 分层排障流程（先看哪一层）

| 症状 | 优先看的层 | 常见根因 |
| --- | --- | --- |
| 整体变慢 | 顶层 span duration 分布 | 下游工具慢 / 模型慢 / 图里多了循环 |
| 结果不对但很快 | 工具 span 的**参数** | 时间窗口、服务名、单位、时区解析错 |
| 结果不对且没调工具 | Generation 的 prompt | 工具描述改了 / prompt 里工具列表丢失 |
| 偶发失败（1%~5%） | `level=ERROR` 的 span + `status_message` | 限流、超时、上游抖动（阶段 3 重试/降级） |
| 成本突然翻倍 | 按 `model` 与 prompt version 分组 | prompt 变长 / 模型换大 / 重试次数增加 |
| 某版本后开始变差 | 按 `release` tag 分组对比 | 代码或 prompt 引入的回归 |

### 7.4 把失败 trace 回灌成评测用例

这是**打通线上与离线**的关键动作，也是本篇对 [01 篇](01-评测方法论与GoldenDataset设计.md) 的直接供给：线上发现失败 trace → 人工确认「这确实是坏 case」并给出期望答案 → input 取该 trace 的用户问题与上下文，expected_output 取正确答案 → 加入 Dataset（面板上可从 trace 直接加入）→ 打 tag / comment 记录失败类型（幻觉 / 参数错 / 越权 / 超时）→ 下次 prompt 或模型变更时，这条用例会拦住同样的错误。价值在于：**你的评测集是被真实失败「喂养」长大的**，而不是在会议室里编出来的；建议给每条回灌用例标注失败类型，报告就能给出「哪类问题在变多」的趋势。

## 八、数据集与在线评测联动

### 8.1 数据集（Dataset）

Dataset = `DatasetItem` 的集合，每项含 `input` / `expected_output` / `metadata`。三种来源：**手工设计**（按 [01 篇](01-评测方法论与GoldenDataset设计.md) 的分类逐条编，覆盖度高、能测边界）、**线上 trace**（一键加入数据集并保留原始上下文，真实分布、最有价值）、**人工标注**（对线上 trace 打分后沉淀，质量最高、成本最高）。

```python
langfuse.create_dataset(name="ops-agent-golden", description="运维分析 Agent 黄金数据集")

# 从一条线上 trace 沉淀用例
langfuse.create_dataset_item(
    dataset_name="ops-agent-golden",
    input={"question": "order-service 昨天为什么变慢？", "window": "2024-05-19"},
    expected_output="应指出 14:00~14:20 出现 P99 毛刺，并关联同期 GC 次数上升",
    metadata={"source": "prod-trace", "failure_type": "missing_anomaly"},
    # source_trace_id="tr_aaa",   # 若该版本支持关联来源 trace（以官方文档为准）
)
```

### 8.2 离线评测与打分回传

在数据集上跑实验（Experiment），每条 item 产生一个 trace，评估器对输出打分，分数自动写回 dataset run 与对应 trace。**Score 类型**：Numeric（`answer_correctness` = 0.8，便于算均值与趋势）、Categorical（`failure_type` = `hallucination`，便于统计分布）、Boolean（`tool_call_valid` = true，便于算通过率）。Score 来源分三类：**人工标注**、**规则/代码**（工具调用是否 JSON 合法、是否越权）、**LLM-as-a-Judge**。三者要**分开命名**（`correctness_human` vs `correctness_judge`），否则无法评估 judge 的可信度——[02 篇](02-评测指标详解与实现.md)会专门讲 judge 与人工的一致性校验。

```python
# SDK 方法名在 v2/v3 间有差异（v3 为 create_score，v2 为 score），以官方文档为准
langfuse.create_score(
    trace_id=trace_id,          # 也可 score session / dataset_run
    name="answer_correctness",
    value=0.8,
    data_type="NUMERIC",
    comment="异常时段定位正确，但漏了 GC 关联",
)
```

### 8.3 人工标注

Langfuse 提供标注队列（Annotation Queue）：把待评估的 trace 批量放进队列，标注员（产品、运维同事）在界面里逐条看 input/output 并打分。要点：① **队列要小**（一次 20~50 条），且**优先放低分/失败/抽样**的 trace（用 filter 筛），不要全量随机；② **评分标准写进队列描述**（Rating criteria），否则不同人的 0.8 含义不同；③ 人工标注是整条链路里最贵的一环——先用 LLM-as-a-Judge 粗筛、人工只精标边界样本，性价比最高。

## 九、自托管与生产注意

### 9.1 用 Docker Compose 起 Langfuse

```bash
git clone https://github.com/langfuse/langfuse.git
cd langfuse
# 生成随机密钥；ENCRYPTION_KEY 必须稳定保存，改了就解不开历史数据
#   NEXTAUTH_SECRET / SALT / ENCRYPTION_KEY 均为随机 64 位十六进制
docker compose up -d
# 打开 http://localhost:3000 注册首个账号，创建 organization / project，
# 拿到 PUBLIC KEY / SECRET KEY，填进业务应用 .env
```

`LANGFUSE_HOST` 指向自托管地址（如 `https://langfuse.internal.example.com`）。前面接了反向代理时，注意上传体积与超时配置（trace 里可能有大 payload）。

### 9.2 依赖组件

| 组件 | 作用 | 注意 |
| --- | --- | --- |
| Langfuse Web / Worker | API + UI（Web）；异步处理与 ingestion（Worker） | Worker 负责把写入落到 ClickHouse，别省略 |
| **PostgreSQL** | 元数据、用户、项目、prompt、数据集 | 必须持久化卷 + 定期备份 |
| **ClickHouse** | Trace / Observation 分析型存储 | **存储大头**，容量要提前规划 |
| **Redis** | 队列与缓存 | 掉了会丢在途数据，建议开持久化 |
| 对象存储（S3 / MinIO） | 大 payload 的原始 input/output | 没有它大 payload 可能落库或失败 |
| 反向代理 + TLS | 暴露给业务与浏览器 | 内网证书要装进业务容器信任链 |

**版本升级要谨慎**：Langfuse 大版本升级（尤其 v2 → v3）涉及数据模型与 SDK 的破坏性变更，务必先读官方 upgrade / self-hosting 文档并在预发演练。**SDK 版本可能演进，以官方文档为准。**

### 9.3 数据保留与合规

**保留策略分层**：原始 payload 保留 7~30 天，聚合指标长期保留（这正是 06 篇的价值）。**删除权**：用户要求删除数据时，要能按 `user_id` 删除 trace。**脱敏**：写入前脱敏（3.4），自托管可在服务端再加一层。**访问控制**：观测平台的读权限要按需授予——它等于「所有用户对话的明文库」，比生产库更敏感。**合规**：GDPR / PII 的处理要求见 [05 篇](05-Agent安全评测与加固.md)。

### 9.4 采样

| 策略 | 做法 | 适用 |
| --- | --- | --- |
| 头部采样 | 按 `trace_id` / `user_id` 哈希抽样，如 10% | 通用降本，简单 |
| **错误全留** | 抽样之外的流量，只要 `level=ERROR` 或触发降级就 100% 记录 | **必做**，否则排障无据 |
| 按用户分层 | VIP / 付费用户 100%，其余 10% | 保障重点客户可排查 |
| 按功能分层 | 高风险功能（写操作、审批）100%，查询类 10% | 按业务价值分配观测预算 |

实现上可在 `trace_context` 里先算「本次是否采样」，不采样就不创建 span（或只记 metadata 不记 payload）。**Python SDK 与 JS/TS SDK 对采样的内建支持程度不同**（JS/TS 有 `sampleRate` 参数），Python 侧通常要自己实现，**以官方文档为准**。最大陷阱是抽完发现关键 trace 没记下来——所以「错误全留」不是优化项，是底线。

### 9.5 异步 flush 与进程退出的坑

SDK 默认**异步批量上报**：span 结束 ≠ 数据已到达服务端。经典故障是脚本跑完直接退出，缓冲区里没发出去的 trace 全丢；解法是结尾显式 `flush_observability()`。

| 场景 | 对策 |
| --- | --- |
| 短脚本 / CLI 任务 | 结尾显式 `flush()`；`obs.py` 再挂 `atexit` 兜底 |
| FastAPI / 长驻服务 | lifespan 的 shutdown 阶段 `flush()`；优雅停机 |
| Celery / 后台 worker | 任务结束时 flush；worker 优雅退出钩子里 flush |
| Serverless / 容器瞬时任务 | **最危险**：容器随时被冻结回收，宁可每次调用后同步 flush |
| 单测 / CI | 不配 key（`init_observability` 返回 `None`），不产生噪声数据 |

另一个相关坑：**重复创建客户端**会重复初始化 OTel provider，导致数据重复上报或上下文分裂（Langfuse 仓库有相关 issue）。纪律：**全进程只通过 `get_client()` 取单例**。

### 9.6 多实例部署

- **无状态**：应用实例不存状态，trace 走 HTTP 上报，天然支持水平扩展；
- **Session 一致性**：同一会话的多轮请求可能落到不同实例，所以 `session_id`（= `thread_id`）必须由外部传入，不能依赖实例内存；
- **分工**：阶段 4 的 Checkpoint（Postgres）负责「状态可恢复」，Langfuse 负责「过程可观测」，两者用同一个 `thread_id` 关联——**不要用 Langfuse 当状态存储**；
- **后端容量与时钟**：ClickHouse 是写入瓶颈，实例数增加时先确认 ingestion worker 与 Redis 队列扛得住；时延计算依赖各实例时钟，务必全集群 NTP 同步，否则 P95 会莫名漂移。

## 十、踩坑点

| # | 坑 | 症状 | 解法 |
| --- | --- | --- | --- |
| 10.1 | **忘记 flush 导致 trace 丢失** | 短脚本/CI 跑完，面板上一条都没有 | 结尾 `flush_observability()`；`atexit` 兜底；lifespan shutdown 钩子 |
| 10.2 | **SDK 版本升级破坏 API** | v2→v3 后 `CallbackHandler(public_key=...)` 报错、`langfuse.trace()` 不存在 | 锁定版本；升级前读 upgrade path；接入层收敛在 `obs.py` |
| 10.3 | **把敏感信息写进 input/output** | trace 里出现真实手机号、密钥、内网 IP、合同内容 | 统一脱敏钩子（3.4/4.6）；评审禁止绕过；自托管再加服务端脱敏 |
| 10.4 | **只用默认 span 名无法排障** | 面板里全是 `RunnableSequence` / `node1`，看不出哪步慢 | 节点用动词+宾语命名；工具用 `tool:xxx`；补 metadata（4.5） |
| 10.5 | **成本字段为 0** | `cost = 0` 或总成本明显偏低 | 检查 `model` 是否被价格表匹配（自托管需自定义模型 5.4）；检查 `usage` 是否上报；核对单位（token vs 字符） |
| 10.6 | **tag 命名混乱** | `prod`/`production`/`PRD`/`线上` 并存，报表分不开 | 受控词表 `key:value` 写进团队规范；`trace_tags()` 统一前缀 |
| 10.7 | 忘了传 `callbacks` | 只有顶层 span，没有模型与工具调用 | handler 要传进 `invoke/ainvoke` 的 config，不是构造函数 |
| 10.8 | 忘了 `user_id` / `session_id` | 无法按人/按会话分析，多轮对话散成孤立 trace | 在 `metadata`（v3）或 `update_current_trace` 显式补齐 |
| 10.9 | 手工包了重复 span | 同一工具出现两个 span，时长口径混乱 | 框架已埋点处不要再套 `@observe`，改为函数内 `update_current_span` |
| 10.10 | 采样把错误也抽掉了 | 出事时发现没有 trace | 错误全留，只对成功请求采样 |
| 10.11 | 忘了记录 prompt 版本 | 效果变差却不知道是哪个版本 | 用 Prompt Management 取 prompt（自动关联），或把 version 写进 tags |
| 10.12 | 把 trace 当数据库用 | 用 Langfuse 存业务状态、任务进度 | 状态归 Checkpoint / 业务库（阶段 4），观测归 Langfuse |

## 学习自检与练习

### 练习 1：给阶段 3 项目接入 Trace，并描述面板上看到的东西

**任务**：给「企业运维分析 Agent」接入 Langfuse：写 `obs.py`（可直接用 4.6），给 FastAPI 加 trace 中间件，跑通 3 个请求——① 正常查询、② 工具返回空数据、③ 故意让工具抛异常。

**提示**：先用 `CallbackHandler` 确认能看到模型与工具 span，再用 `@observe` 补业务函数；第 3 个请求必须用 `level="ERROR"` 标红，否则失败率报表看不到；结尾记得 `flush()`，否则你会以为「接入失败」其实只是没上报。

**验收标准**：① 能贴出一条完整 trace 的 span 树并说明每层含义；② 能说出这次请求的总 token、总成本、端到端时延，并指出各自来自哪个 span；③ 前端能看到 `X-Trace-Id`（或 body 里的 `trace_id`）并用它搜到 trace；④ 三个请求按 session 聚合后属于同一会话。

### 练习 2：做一次 Prompt 版本 A/B

**任务**：为运维 Agent 建两个系统提示词版本（`production` 与 `candidate`，后者明确要求「数据不足时必须说数据不足，不得推测」）；用 `pick_prompt_label` 按 `user_id` 做 50/50 分流，跑至少 30 条来自 [01 篇](01-评测方法论与GoldenDataset设计.md) 评测集的用例（重点覆盖「无答案/数据不足」类），在面板上对比两组指标。

**提示**：必须把 `prompt_label` 写进 tags/metadata，否则两组数据分不开；用 01 篇的评测集而非随手编的问题；关注三个指标——任务完成率、**幻觉率**、平均成本（prompt 变长 = 更贵）。

**验收标准**：① 面板上能按 tag 分组对比两组并给出数字；② 写出一句结论：candidate 是否更好、在哪个维度更好、代价是什么；③ 说明分流是否稳定（同一 `user_id` 是否始终同组）及为什么这点重要。

### 练习 3：自建成本日报

**任务**：写一个脚本，每天定时从 Langfuse 拉取过去 24 小时的 trace，生成成本日报：总请求量、总成本、单次平均成本、P95 时延、失败率，以及按模型 / 按用户 / 按 tag 的前三名；成本环比增长 > 50% 时标红告警。

**提示**：数据可走 Langfuse 的 SDK/API 查询能力（**接口以官方文档为准**），也可先用 UI 导出验证口径；成本依赖价格表（5.4）；时延要明确是**顶层 span** 的 P95；数字要与面板手动筛选结果一致。

**验收标准**：① 脚本可跑通输出日报，连续两天数据能对比；② 日报数字与面板筛选结果**一致**（口径对齐）；③ 能说出这份日报的数字与 [06 篇](06-Prometheus与Grafana监控告警.md) Prometheus 告警指标的对应关系。

### 练习 4（进阶）：完整的「失败回灌 → 回归」闭环

**任务**：制造一次真实失败（如工具传错时区导致结论错误）→ 在面板定位该 trace → 加入数据集并标注失败类型 → 修改 prompt 或代码 → 重跑评测集 → 用 `create_score` 回传结果 → 在 dataset run 里对比修改前后。

**验收标准**：整条链路在项目里可复现并能画出流程图；能说明这次失败属于 7.3 表格中的哪一类。

### 自检清单

- [ ] 能说清 LLM Tracing 与传统 APM 的四个根本差异（非结构化 payload、多步嵌套、token/成本、prompt/模型版本）；
- [ ] 能画出 Traces/Logs/Metrics 三支柱，并说明 03/04/06 三篇的分工与保留期差异；
- [ ] 能说出 Langfuse 与 LangSmith 在部署、数据主权、集成成本、评测能力、OTel 兼容上的取舍并给出选型理由；
- [ ] 能画出 Trace / Span / Generation / Event / Session / User / Score / Dataset 的层级关系，知道 Session 与 Trace 是一对多；
- [ ] 能背出「一条合格 Agent Trace 的字段清单」，尤其是 `user_id`/`session_id`/`model`/`usage`/`level`/`tags`/`release`；
- [ ] 知道哪些字段必须脱敏，并能在 `obs.py` 里用一个统一钩子兜住；
- [ ] 能用 `CallbackHandler` 与 `@observe` 两种方式接入，说清各自该用在哪、为什么不要叠加；
- [ ] 能在 FastAPI 里给每次请求挂 trace，并把 `trace_id` 回传给前端；
- [ ] 能列出四类常用报表及口径，并说明与 02 篇、06 篇的口径如何对齐；
- [ ] 能用 Prompt Management 创建版本、按 `label` 取用、做按用户稳定分桶的 A/B，并知道 prompt 变更必须重跑评测集；
- [ ] 能按「失败报告 → trace_id → 分层 span」完成一次排障，并把失败 trace 回灌成评测用例；
- [ ] 知道自托管的依赖组件、采样策略（错误全留）与 flush / 进程退出丢数据的坑。

## 参考资料

> 以下链接均为撰写时检索确认存在的官方页面。Langfuse 迭代较快（Python SDK 有 v2 / v3 两代口径，v3 为 OTel-based 重写），**API 名称、参数、环境变量名与功能边界请以官方文档当前版本为准**。

Langfuse 官方文档：

- 观测数据模型（Trace / Observation / Span / Generation / Session / User）: https://langfuse.com/docs/observability/data-model
- Token 与成本追踪（Token & Cost Tracking）: https://langfuse.com/docs/observability/features/token-and-cost-tracking
- 数据脱敏（Data Masking）: https://langfuse.com/docs/observability/features/masking
- Python SDK v2 → v3 升级路径（**版本口径差异的核心参考**）: https://langfuse.com/docs/observability/sdk/python/upgrade-path
- Prompt Management 总览: https://langfuse.com/docs/prompt-management/overview
- Prompt 版本控制（按 label / version 取用）: https://langfuse.com/docs/prompt-management/features/prompt-version-control
- 评测核心概念（Dataset / DatasetItem / Score / Evaluator）: https://langfuse.com/docs/evaluation/core-concepts
- 自托管总览: https://langfuse.com/self-hosting
- Docker Compose 自托管部署: https://langfuse.com/self-hosting/deployment/docker-compose
- OpenTelemetry 原生集成（OTLP 端点，衔接 04 篇）: https://langfuse.com/integrations/native/opentelemetry

框架集成：

- LangChain 集成（CallbackHandler）: https://langfuse.com/integrations/frameworks/langchain
- LangGraph 集成（节点级 span 与 metadata）: https://langfuse.com/integrations/frameworks/langgraph

LangSmith（用于对比）：

- LangSmith Observability 文档: https://docs.langchain.com/langsmith/observability
- LangSmith Evaluation 快速开始: https://docs.langchain.com/langsmith/evaluation-quickstart

源码仓库（含 Docker Compose 文件）:

- Langfuse 开源仓库: https://github.com/langfuse/langfuse

阶段 5 关联篇目：

- [01-评测方法论与GoldenDataset设计.md](01-评测方法论与GoldenDataset设计.md)（评测集设计、失败样本回灌的去处）
- [02-评测指标详解与实现.md](02-评测指标详解与实现.md)（Trace 聚合指标的离线对应指标）
- [04-OpenTelemetry与自定义Tracing.md](04-OpenTelemetry与自定义Tracing.md)（标准 OTel 链路与 trace_id 体系）
- [05-Agent安全评测与加固.md](05-Agent安全评测与加固.md)（PII 脱敏、审计与合规）
- [06-Prometheus与Grafana监控告警.md](06-Prometheus与Grafana监控告警.md)（Trace 派生指标的聚合与告警）
- [07-生产化部署与CI-CD.md](07-生产化部署与CI-CD.md)（发布策略、Prompt 评测门禁）
- [08-阶段5综合实践-全链路观测与评测报告.md](08-阶段5综合实践-全链路观测与评测报告.md)（把本篇接入能力用到两个项目上）
- 阶段 4 关联：[05-Checkpoint持久化与长任务恢复.md](../阶段4-复杂工作流与Deep-Agents/05-Checkpoint持久化与长任务恢复.md)（`thread_id` 与 `session_id` 的对齐）
