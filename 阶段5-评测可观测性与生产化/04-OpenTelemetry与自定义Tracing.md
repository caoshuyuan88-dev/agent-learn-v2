# OpenTelemetry 与自定义 Tracing

> 本文定位：阶段 5 的 03 篇讲了 Langfuse / LangSmith 这类**产品级** LLM 观测平台——它们看得清 prompt、token、评分，但那是「LLM 视角」。当 Agent 要和公司既有的 Java 微服务链路打通、要把 trace 关联到 ELK 日志、要把同一份数据同时送到公司统一监控体系时，你需要一套**厂商中立的观测标准**：OpenTelemetry（简称 OTel）。本文讲 OTel 的四件套（规范 / SDK / Collector / OTLP）、Python SDK 上手、为 Agent 设计 span 与属性、与 FastAPI 和 LangChain / LangGraph 的集成、上下文传播与日志关联、导出与部署。它与 [03 篇](03-Langfuse与LangSmith可观测性.md) 互补：**03 篇看 LLM 细节，04 篇看全链路**；并为 [06 篇](06-Prometheus与Grafana监控告警.md)（从 trace 派生指标）与 [07 篇](07-生产化部署与CI-CD.md)（部署 Collector）铺路。前置：Python 3.11+、FastAPI、LangChain / LangGraph 1.x（阶段 1~4），以及读完 03 篇理解 trace 基本概念。

## 学习目标

学完本文，你应该能：

- 说清 OTel 四件套（规范 / SDK / Collector / OTLP）的分工，以及它解决「厂商中立 / 跨语言 / 统一上下文传播」的原理；
- 说清 OTel 与 Langfuse / LangSmith 的定位差异，并设计「两者共存」的接入方案；
- 解释 Trace / Span / SpanContext / trace_id / span_id / Resource / Sampler / Exporter 及相互关系；
- 用 Python SDK 写出可复用的 `telemetry.py`，并用环境变量控制行为；
- 按 semconv 口径为节点 / LLM 调用 / 工具调用设计 span 名与属性，写出 `@traced_node` 与工具包装器；
- 给 FastAPI 接自动埋点，把 trace_id 回写响应头与日志，并解释为什么必须依赖 contextvars；
- 用两种思路给 LangChain / LangGraph 接 OTel，写出 OTel callback handler 骨架，并避免重复埋点；
- 用 W3C traceparent 做跨语言（Python ↔ Java ↔ MCP）传播与日志-trace 关联；
- 部署 Collector、选择采样策略，避开丢 span / 串链路 / 塞 PII 等典型坑。

## 一、OTel 是什么

### 1.1 四件套

OpenTelemetry 不是某个软件，而是一套**标准 + 工具链**。拆成四块最好记：

| 组成 | 英文 | 是什么 | 类比 Java |
| --- | --- | --- | --- |
| 规范 | Specification | 定义 trace / metric / log 的数据模型、API、属性命名 | JDBC 规范 |
| SDK | SDK | 各语言实现（Python / Java / Go / JS…），负责采样、加工、导出 | JDBC 驱动 |
| Collector | Collector | 独立边车/网关进程：接收、处理、扇出遥测数据 | Logstash / API Gateway |
| 协议 | OTLP | Collector 与后端之间的传输协议（gRPC / HTTP） | HTTP + Protobuf |

一句话：**应用用 SDK 产生数据，用 OTLP 发给 Collector，Collector 扇出到任意后端；规范保证所有环节对「一条 trace 长什么样」的理解一致。**

```text
应用进程（Python / Java / Go …）
  └─ OTel SDK：TracerProvider + Sampler + SpanProcessor
        └─ OTLP（gRPC :4317 / HTTP :4318）
              └─ OTel Collector：receiver → processor → exporter
                    ├─ Jaeger / Tempo（链路查询）
                    ├─ Langfuse（LLM 观测）
                    ├─ Prometheus（从 span 派生指标）
                    └─ 公司自建 / 云厂商 APM
```

### 1.2 它解决什么

1. **厂商中立**：今天用 Langfuse，明天换 LangSmith、后天公司要求接入云厂商 APM——如果埋点直接调各家 SDK，换一次重写一次。OTel 的做法是**埋点一次、扇出多处**，切换后端只改 Collector 配置。
2. **跨语言 / 跨服务**：企业运维分析 Agent（Python）后面挂着 Java 写的指标查询服务，再往后是 MCP Server。三个进程语言框架都不同，只要能读写同一个 `traceparent` 头，就能组成一条完整 trace——这是「LLM 视角」平台做不到的。
3. **统一上下文传播**：OTel 把「当前正在处理哪个 span」抽象成 context（Python 里基于 contextvars），日志、HTTP 客户端、数据库驱动都能从 context 拿到同一个 trace_id，于是**日志、指标、链路可互相跳转**。

### 1.3 与 Langfuse / LangSmith 的定位差异

两者不是竞争关系，是**层次不同**：

| 维度 | OpenTelemetry | Langfuse / LangSmith |
| --- | --- | --- |
| 定位 | 观测**标准与管道** | LLM 应用的**观测产品** |
| 数据模型 | Trace + Span + Metric + Log 通用模型 | LLM 特化：prompt / completion / token / 评分 / 数据集 |
| 跨服务能力 | 强（W3C traceparent 天然跨语言） | 弱（主要覆盖 LLM 应用自身） |
| 与 Java / 公司监控打通 | 原生支持 | 需自建桥接 |
| Prompt 管理与评测数据集 | 不提供 | 核心能力（见 [01 篇](01-评测方法论与GoldenDataset设计.md)、[02 篇](02-评测指标详解与实现.md)） |
| 后端可替换性 | 完全可替换 | 平台锁定 |

**结论**：用 OTel 做**骨架**（全链路、跨服务、进公司监控），用 Langfuse 做**皮肤**（prompt / 评分 / 数据集 / 人工标注）。

### 1.4 共存方式：三个层次

| 方案 | 做法 | 适合 |
| --- | --- | --- |
| A. 双写 | 应用同时用 OTel SDK 与 Langfuse SDK 埋点 | 快速起步，埋点重复 |
| B. 桥接 | 用 Langfuse 的 OTel 接入（LLM 平台提供 OTLP 兼容入口），应用只发 OTLP | 埋点一次，两边都能看 |
| C. 扇出 | 应用只发 OTLP 到 Collector，Collector 同时导出到 Jaeger 与 Langfuse | 生产推荐，应用零感知后端变化 |

阶段 3 项目的演进路径：**先 A 跑通（03 篇已做）→ 迁到 C**。C 方案下 Langfuse 只是 Collector 的一个 exporter，未来加 Tempo、加云厂商 APM 都不用改应用代码。

> **类比 Java**：OTel 之于可观测性很像 SLF4J + Logback 之于日志——SLF4J 是门面（规范），Logback 是实现（SDK），Collector 相当于 Filebeat：应用只管产生数据，管道负责投递到哪。

## 二、核心概念

### 2.1 Trace、Span、SpanContext

| 概念 | 含义 | 关键点 |
| --- | --- | --- |
| Trace | 一次完整请求的调用链 | 全局唯一 `trace_id`（128 位） |
| Span | 一次操作（一个节点 / 一次 LLM 调用 / 一次工具调用） | `span_id`（64 位）、起止时间、属性、事件、状态 |
| SpanContext | span 的身份：`trace_id` + `span_id` + 采样标志 + tracestate | **这是唯一需要跨进程传播的东西** |
| Parent Span | 父 span；没有父就是 root span | 父子关系决定树形结构 |

```text
trace_id = 4bf92f3577b34da6a3ce929d0e0e4736      ← 整条链路共享
  span_id = 00f067aa0ba902b7  (root: POST /agent/run)
      └─ span_id = a1b2c3d4e5f60718  (agent.node.plan)
            └─ span_id = 1122334455667788  (chat gpt-4o)
```

### 2.2 父子关系与 context 传播

同进程里父子关系靠 **context** 自动建立：

```python
with tracer.start_as_current_span("parent") as parent:
    with tracer.start_as_current_span("child") as child:
        ...      # child 的父自动是 parent，不用手写 parent 参数
```

跨进程靠 **propagator**（默认 W3C TraceContext）注入/提取：

```python
from opentelemetry import propagate

headers = {}
propagate.inject(headers)     # {'traceparent': '00-4bf92f35...-00f067aa0ba902b7-01'}

ctx = propagate.extract(incoming_headers)          # 下游：还原 SpanContext
with tracer.start_as_current_span("handle", context=ctx):
    ...
```

**这是 OTel 最关键的机制**：链路能连成一条，靠的不是「传个 trace_id 字符串」，而是标准化的注入/提取。用生态里的 instrumentation（httpx / requests / FastAPI）时这两步是自动的。

### 2.3 Attributes、Events、Status

| 元素 | 用途 | 示例 |
| --- | --- | --- |
| Attributes | span 上的键值对，**用于筛选聚合** | `gen_ai.request.model="gpt-4o"`、`tool.name="query_metrics"` |
| Events | span 内带时间戳的记录点 | `tool.call.retry`、`cache.hit`、`prompt.compiled` |
| Status | 该 span 的成功/失败结论 | `StatusCode.OK` / `StatusCode.ERROR` |
| Links | 关联其他 trace 的 span（非父子） | 批处理任务关联被处理的请求 |

纪律：**属性只放低基数、可聚合的值**。整段 prompt / 响应正文 / 用户输入**不要**放属性——会被 SDK 截断、被后端拒收、且按属性建索引成本极高（第九节）。

### 2.4 Resource、Sampler、Exporter

| 组件 | 作用 | 典型配置 |
| --- | --- | --- |
| Resource | 描述**数据是谁产生的**，附加到该进程所有 span | `service.name`、`service.version`、`deployment.environment` |
| Sampler | 决定**哪些 trace 被记录**（决策粒度为 trace） | `ParentBased(root=TraceIdRatioBased(0.1))` |
| Exporter | 决定数据**发到哪** | `OTLPSpanExporter` + `BatchSpanProcessor` |

`service.name` 是所有后端的**第一分组维度**——没设好，在 Jaeger 里连自己的服务都找不到。

### 2.5 一张层级图（Agent 场景）

```text
[HTTP] POST /agent/run                           span: POST /agent/run          (SERVER)
  └─ [graph] ops-agent                           span: invoke_agent ops-agent   (INTERNAL)
      ├─ [node] planner                          span: agent.node.planner       (INTERNAL)
      │    └─ [llm] chat gpt-4o                  span: chat gpt-4o              (CLIENT, gen_ai.*)
      ├─ [node] executor                         span: agent.node.executor      (INTERNAL)
      │    ├─ [llm] chat gpt-4o                  span: chat gpt-4o              (CLIENT)
      │    ├─ [tool] query_metrics               span: execute_tool query_metrics
      │    │    └─ [http] GET metrics-svc/api    span: GET                      (CLIENT → Java，跨进程)
      │    └─ [tool] search_runbook              span: execute_tool search_runbook
      │         └─ [mcp] tools/call              span: tools/call               (CLIENT → MCP Server)
      └─ [node] reporter                         span: agent.node.reporter
```

读图要点：每层都是 `start_as_current_span` 的结果，父子关系由 context 自动建立；跨进程那两支（→ Java、→ MCP）**在下游延续同一个 trace_id**，这就是「打通公司监控体系」的具体含义；span 名要**稳定且低基数**。

## 三、Python SDK 快速上手

### 3.1 安装与环境变量

```bash
pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc \
            opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-httpx
```

> 版本口径：OTel Python SDK 仍在 1.x 快速迭代（`opentelemetry-api` / `opentelemetry-sdk` 常一起升级）。本文按 **SDK 1.2x ~ 1.3x** 的常见 API 书写，**具体签名以官方文档为准**。生产请锁版本。

OTel 的一大好处是**行为可用环境变量控制，不改代码**：

| 环境变量 | 含义 | 示例 |
| --- | --- | --- |
| `OTEL_SERVICE_NAME` | 服务名（等价 Resource 的 `service.name`） | `ops-agent` |
| `OTEL_RESOURCE_ATTRIBUTES` | 额外 Resource 属性（`k=v,k=v`） | `deployment.environment=prod,service.version=1.4.0` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP 端点（gRPC 默认 4317 / HTTP 默认 4318） | `http://otel-collector:4317` |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | 传输协议 | `grpc` / `http/protobuf` |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | 只针对 traces 的端点（优先级更高） | `http://collector:4318/v1/traces` |
| `OTEL_EXPORTER_OTLP_HEADERS` | 导出附加请求头（鉴权） | `Authorization=Bearer xxx` |
| `OTEL_TRACES_SAMPLER` | 采样器 | `always_on` / `parentbased_traceidratio` / `always_off` |
| `OTEL_TRACES_SAMPLER_ARG` | 采样器参数 | `0.1` |
| `OTEL_PROPAGATORS` | 传播器 | `tracecontext,baggage` |
| `OTEL_SDK_DISABLED` | 完全关闭 SDK（测试用） | `true` |
| `OTEL_LOG_LEVEL` | SDK 自身日志级别 | `debug` |

**关键细节**：`OTLPSpanExporter()` **不带参数**构造时会读取上述环境变量；若代码里显式传了 `endpoint=` 就以代码为准。所以推荐**代码只写开发默认值，生产靠环境变量覆盖**。

### 3.2 `telemetry.py`：可复用的初始化模块

```python
# app/telemetry.py
from __future__ import annotations

import atexit
import os

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_INITIALIZED = False
_provider: TracerProvider | None = None


def _build_exporter():
    """按环境变量决定导出目标；本地无 Collector 时给个默认端点。"""
    protocol = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc").lower()
    if protocol.startswith("http"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    else:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    # 不传 endpoint：由 OTEL_EXPORTER_OTLP_ENDPOINT 决定（生产用环境变量覆盖）
    os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    return OTLPSpanExporter()


def setup_telemetry(service_name: str | None = None) -> TracerProvider:
    """初始化全局 TracerProvider。幂等：重复调用只生效一次。"""
    global _INITIALIZED, _provider
    if _INITIALIZED:
        return _provider  # type: ignore[return-value]

    resource = Resource.create({
        SERVICE_NAME: service_name or os.getenv("OTEL_SERVICE_NAME", "ops-agent"),
        "service.version": os.getenv("APP_VERSION", "0.0.0"),
        "deployment.environment": os.getenv("APP_ENV", "local"),
    })
    # 采样器不写死：交给 OTEL_TRACES_SAMPLER 环境变量（见 8.3）
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(
        _build_exporter(), max_queue_size=2048, schedule_delay_millis=5000,
        max_export_batch_size=512, export_timeout_millis=30000,
    ))
    trace.set_tracer_provider(provider)
    atexit.register(provider.shutdown)   # 关键：不 flush 会丢 span（见 9.1）
    _INITIALIZED, _provider = True, provider
    return provider


def get_tracer(name: str = "agent.ops", version: str | None = None):
    return trace.get_tracer(name, version or os.getenv("APP_VERSION"))
```

要点三条：

- **幂等**：`_INITIALIZED` 保护，避免 `main` 与测试 fixture 各注册一次 processor（重复注册会让每条 span 发两遍）；
- **`BatchSpanProcessor`**：异步批量导出，不阻塞业务；`schedule_delay_millis` 越小越实时、开销越大；
- **`atexit.register(provider.shutdown)`**：最容易被忽略、也最容易导致「Jaeger 里缺最后几条 span」的一行。

### 3.3 一个手动 span 的完整示例

```python
# scripts/manual_span_demo.py
from opentelemetry.trace import Status, StatusCode

from app.telemetry import get_tracer, setup_telemetry

setup_telemetry(service_name="ops-agent-demo")
tracer = get_tracer("agent.ops", "1.0.0")


def call_llm(prompt: str) -> str:
    """LLM 调用：按 gen_ai 语义约定命名与打属性。"""
    with tracer.start_as_current_span("chat gpt-4o") as span:
        span.set_attribute("gen_ai.operation.name", "chat")
        span.set_attribute("gen_ai.system", "openai")       # 新版可能为 gen_ai.provider.name
        span.set_attribute("gen_ai.request.model", "gpt-4o")
        span.set_attribute("gen_ai.usage.input_tokens", 812)     # 旧口径 prompt_tokens
        span.set_attribute("gen_ai.usage.output_tokens", 137)
        return "伪响应"


def run_tool(name: str) -> dict:
    with tracer.start_as_current_span(f"execute_tool {name}") as span:
        span.set_attribute("gen_ai.tool.name", name)
        span.add_event("tool.call.start")
        try:
            if name == "broken_tool":
                raise TimeoutError("tool timeout after 30s")
        except TimeoutError as exc:
            span.record_exception(exc)                          # 记录堆栈
            span.set_status(Status(StatusCode.ERROR, str(exc)))  # 结论：失败
            raise
        span.set_status(Status(StatusCode.OK))
        return {"ok": True}


if __name__ == "__main__":
    with tracer.start_as_current_span("agent.task.run") as root:
        root.set_attribute("task.id", "task-20250101-001")
        for step in ("query_metrics", "search_runbook"):
            call_llm(f"请用 {step} 工具处理")
            run_tool(step)
    # setup_telemetry 里注册了 atexit -> shutdown，会自动 flush
```

跑完后到 Jaeger（`http://localhost:16686`）按 `service.name=ops-agent-demo` 查询，应能看到一棵四层的树。**第一次跑通「在 Jaeger 里看到自己的 Agent 调用树」，是这一篇的核心成就感。**

> **类比 Java**：`start_as_current_span(...)` 之于业务代码很像 `@Transactional`——进入一段代码就做一件横切的事，退出时收尾。区别是事务回滚是强一致的，而 span 出错只是**标记状态**，不影响业务逻辑（除非你自己 `raise` 出去）。

## 四、为 Agent 设计 span 与属性（本篇重点）

### 4.1 命名约定

Span 名是**聚合的第一维度**。约定模板：

| 层级 | 命名模板 | 示例 |
| --- | --- | --- |
| HTTP 入口 | 框架默认（方法 + 路由模板） | `POST /agent/run` |
| Agent 图 | `invoke_agent {agent.name}` | `invoke_agent ops-agent` |
| 图节点 | `agent.node.{node_name}` | `agent.node.planner` |
| LLM 调用 | `{operation} {model}`（semconv 口径） | `chat gpt-4o`、`embeddings text-embedding-3-small` |
| 工具调用 | `execute_tool {tool.name}` | `execute_tool query_metrics` |
| 外部 HTTP | `{method} {host}`（框架默认） | `GET metrics-svc` |

三条纪律：**① 不要把变量拼进 span 名**（`agent.node.planner_task_123` 会让 Jaeger 里出现上万个 operation，聚合视图直接废掉）；**② 同类操作在所有服务里用同一个名字**；**③ 大小写与分隔符统一**（本文一律小写 + 点分隔）。

### 4.2 必需属性：按 semconv 口径

OTel 为生成式 AI 定义了**语义约定（Semantic Conventions for Gen AI）**：按它打属性，所有兼容 OTel 的 LLM 后端都能直接识别，不用为每家写适配。

| 属性 | 含义 | 稳定度 |
| --- | --- | --- |
| `gen_ai.operation.name` | 操作类型：`chat` / `text_completion` / `embeddings` / `execute_tool` / `invoke_agent` | 发展中 |
| `gen_ai.system`（较新版本为 `gen_ai.provider.name`） | 供应商：`openai` / `anthropic` / `azure.ai.openai` | 发展中，**新旧并存** |
| `gen_ai.request.model` | 请求的模型名 | 发展中 |
| `gen_ai.response.model` | 实际响应的模型（可能与请求不同） | 发展中 |
| `gen_ai.request.temperature` / `max_tokens` / `top_p` | 请求参数 | 发展中 |
| `gen_ai.usage.input_tokens` | 输入 token（旧口径 `gen_ai.usage.prompt_tokens`） | 发展中 |
| `gen_ai.usage.output_tokens` | 输出 token（旧口径 `gen_ai.usage.completion_tokens`） | 发展中 |
| `gen_ai.response.finish_reasons` / `gen_ai.response.id` | 结束原因数组 / 响应 id | 发展中 |
| `gen_ai.tool.name` / `gen_ai.tool.call.id` | 工具名 / 调用 id | 发展中 |
| `gen_ai.agent.name` / `gen_ai.agent.id` | Agent 名 / id | 发展中 |

**稳定度提醒（必读）**：Gen AI 语义约定整体仍标记为 **开发中（development / experimental）**，属性名在版本间发生过重命名（最典型的是 `gen_ai.system` → `gen_ai.provider.name`、`prompt_tokens` → `input_tokens`）。工程做法：

1. **属性名只在一处写**——定义常量，重命名时改一处；
2. 升级 SDK 时**同时确认后端是否已支持新名**（很多后端做新旧兼容）；
3. 过渡期**新旧属性短期双写**（多几个属性，远好过丢数据）。**具体口径以官方 semconv 文档为准。**

```python
# app/semconv.py —— 属性名的单一来源
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_SYSTEM = "gen_ai.system"
GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_TOOL_NAME = "gen_ai.tool.name"


def gen_ai_llm_attributes(*, system: str, model: str, temperature: float = 0.2) -> dict[str, object]:
    return {
        GEN_AI_SYSTEM: system,          # 旧口径，保留一行兼容
        GEN_AI_PROVIDER_NAME: system,   # 新口径
        GEN_AI_REQUEST_MODEL: model,
        "gen_ai.request.temperature": temperature,
    }


def gen_ai_usage_attributes(*, input_tokens: int, output_tokens: int) -> dict[str, int]:
    return {GEN_AI_USAGE_INPUT_TOKENS: input_tokens, GEN_AI_USAGE_OUTPUT_TOKENS: output_tokens}
```

### 4.3 业务属性

semconv 管 LLM 通用口径，业务语义自己定。建议的最小业务属性集：

| 属性 | 含义 | 基数 | 用途 |
| --- | --- | --- | --- |
| `task.id` | 任务 id（== Checkpoint 的 `thread_id`） | 高 | 定位单个任务、串联日志 |
| `conversation.id` | 会话 id | 高 | 多轮对话聚合 |
| `user.id.hash` | 用户标识（**哈希后**） | 中高 | 按用户排障 |
| `tenant.id` | 租户 | 低 | 多租户隔离与计费 |
| `agent.node.name` | 节点名 | 低 | 节点级耗时/失败率 |
| `tool.name` / `tool.status` | 工具名 / 结果状态 | 低 | 工具级成功率与耗时 |
| `retry.count` | 重试次数 | 低 | 观察重试放大 |
| `cost.usd` | 本次调用估算成本 | 连续值 | 从 trace 派生成本指标（[06 篇](06-Prometheus与Grafana监控告警.md)） |
| `error.type` | 低基数错误分类 | 低 | 错误率分桶 |

```python
span.set_attribute("task.id", state["task_id"])
span.set_attribute("conversation.id", state["thread_id"])
span.set_attribute("tenant.id", state["tenant_id"])
span.set_attribute("cost.usd", est_cost)          # 数值型，别写成字符串
```

**反例**：`span.set_attribute("prompt", full_prompt_text)`、`span.set_attribute("user.email", "a@b.com")`（见 9.3 / 9.4）。

### 4.4 Span 粒度取舍

| 位置 | 是否开 span | 理由 |
| --- | --- | --- |
| 每个图节点 | ✅ 一个 | 定位「哪一步慢/错」的最小单元（阶段 4 的节点边界天然对齐） |
| 每次工具调用 | ✅ 一个 | 工具最容易超时/失败/被重试（阶段 3 重点） |
| 每次 LLM 调用 | ✅ 一个 generation span | token、模型、延迟、成本都挂这里 |
| 每次 HTTP / RPC 出站 | ✅ 交给 instrumentation 自动开 | 打通跨服务链路的关键 |
| 每次数据库 / 缓存访问 | ⚠️ 视情况 | instrumentation 打开后再决定是否过滤，噪音大 |
| 函数内部循环 | ❌ 不开 | 用 Events 或计数属性代替 |

**经验数值**：一次「企业运维分析 Agent」任务（1 个 HTTP 入口 + 6 个节点 + 2 次 LLM + 5 次工具 + 8 次出站 HTTP）约产生 **20~30 个 span**。按每天 1 万次任务算就是 20~30 万 span/天——所以**采样不是可选项**（见 8.3）。

### 4.5 事件与异常记录

```python
# 事件：不需要独立 span 的中间状态
span.add_event("cache.miss", {"cache.key.prefix": "metrics"})
span.add_event("retry", {"attempt": 2, "reason": "timeout"})

# 异常：优先用 record_exception（把 type/message/stacktrace 写成标准 exception 事件）
try:
    risky_call()
except TimeoutError as exc:
    span.record_exception(exc)
    span.set_status(Status(StatusCode.ERROR, "tool timeout"))
    raise
```

三条纪律：**① `record_exception` 与 `set_status(ERROR)` 要一起做**（只 record 不设状态，后端按错误率筛不出来；只 set_status 会丢堆栈）；**② 不要把异常对象塞进属性**（不可序列化）；**③ 预期的业务失败**（如工具返回空结果）不要标 ERROR，用属性或事件表达，否则错误率告警会被噪音淹没（[06 篇](06-Prometheus与Grafana监控告警.md) 按这个口径建告警）。

### 4.6 `@traced_node`：给 LangGraph 节点加 span

阶段 4 的图节点是最自然的埋点位置。用装饰器包一层，业务代码保持干净（同步节点同理，去掉 `await` 即可）：

```python
# app/tracing.py
import functools

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

_tracer = trace.get_tracer("agent.ops")


def traced_node(name: str | None = None):
    """给 LangGraph 异步节点函数加 span。用法：@traced_node("planner")"""
    def decorator(fn):
        span_name = f"agent.node.{name or fn.__name__}"

        @functools.wraps(fn)
        async def wrapper(state, *args, **kwargs):
            with _tracer.start_as_current_span(span_name) as span:
                span.set_attribute("agent.node.name", name or fn.__name__)
                if isinstance(state, dict):
                    for key in ("task_id", "thread_id", "tenant_id"):
                        if key in state:
                            span.set_attribute(key.replace("_", "."), str(state[key]))
                try:
                    result = await fn(state, *args, **kwargs)
                except Exception as exc:                      # noqa: BLE001
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    raise
                span.set_status(Status(StatusCode.OK))
                return result

        return wrapper

    return decorator
```

接到阶段 4 的图上（同步节点同理，去掉 `await` 即可）：

```python
from langgraph.graph import END, START, StateGraph
from app.tracing import traced_node

@traced_node("planner")
async def planner_node(state: TaskState) -> dict: ...

@traced_node("executor")
async def executor_node(state: TaskState) -> dict: ...

builder = StateGraph(TaskState)
builder.add_node("planner", planner_node)     # 注意：注册的是被装饰后的函数
builder.add_node("executor", executor_node)
builder.add_edge(START, "planner")
builder.add_edge("planner", "executor")
builder.add_edge("executor", END)
graph = builder.compile()
```

**踩坑提示**：装饰器返回的是新函数，`add_node` 必须注册**装饰后**的对象；实现里用了 `@functools.wraps` 保留函数元信息。若节点内用 `asyncio.gather` 并发子任务，每个子任务各自复制 context，父子关系仍正确；但用 `run_in_executor` 丢线程池时会丢 context（见 5.3 与 9.2）。

### 4.7 工具包装器

工具是阶段 3 的核心资产，也是最需要观测的地方：

```python
# app/tool_tracing.py
import functools
import time

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

_tracer = trace.get_tracer("agent.tools")


def traced_tool(fn=None, *, tool_name: str | None = None):
    """工具调用埋点：span 名遵循 semconv 的 execute_tool {name} 口径。"""

    def decorator(func):
        name = tool_name or func.__name__
        span_name = f"execute_tool {name}"

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            started = time.perf_counter()
            with _tracer.start_as_current_span(span_name) as span:
                span.set_attribute("gen_ai.operation.name", "execute_tool")
                span.set_attribute("gen_ai.tool.name", name)
                span.set_attribute("tool.name", name)
                # 只记参数名与耗时，绝不记参数正文
                span.set_attribute("tool.arg.keys", ",".join(sorted(kwargs)))
                try:
                    result = await func(*args, **kwargs)
                except Exception as exc:                      # noqa: BLE001
                    span.set_attribute("tool.status", "error")
                    span.set_attribute("error.type", type(exc).__name__)
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    raise
                span.set_attribute("tool.status", "ok")
                span.set_attribute("tool.duration_ms", round((time.perf_counter() - started) * 1000, 2))
                span.set_status(Status(StatusCode.OK))
                return result

        return wrapper

    return decorator if fn is None else decorator(fn)
```

```python
from langchain_core.tools import tool

from app.tool_tracing import traced_tool


@tool
@traced_tool(tool_name="query_metrics")
async def query_metrics(service: str, window: str = "1h") -> dict:
    """查询指定服务在时间窗口内的指标。"""
    return await _call_metrics_service(service, window)
```

**装饰顺序**：`@tool` 在最外层、`@traced_tool` 在内层——LangChain 拿到的是同一个函数对象，工具元数据（name / schema）不变，而调用会经过你的 span 包装。反过来 `@tool` 可能包装掉你的 wrapper。

## 五、与 FastAPI 集成

### 5.1 自动埋点（可运行示例）

```python
# app/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from app.telemetry import setup_telemetry


@asynccontextmanager
async def lifespan(app: FastAPI):
    provider = setup_telemetry("ops-agent")
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        excluded_urls="health,healthz,metrics",   # 健康检查别进 trace，纯噪音
    )
    HTTPXClientInstrumentor().instrument()        # 出站 httpx 自动注入 traceparent
    yield
    provider.shutdown()                           # 优雅退出：flush 剩余 span


app = FastAPI(title="Ops Agent API", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
```

要点：**`excluded_urls` 必配**（否则 K8s 探针每秒灌满 trace 存储）；**初始化放 `lifespan`**（比 `atexit` 更可控，两者可同时保留）；**出站埋点靠 `HTTPXClientInstrumentor`**，它会在请求时自动 `inject` 头，Java 侧只要也装了 OTel agent，链路自动接上——**这是「与 Java 侧打通」最省力的一步**。非 FastAPI 的纯 ASGI 应用用 `OpenTelemetryMiddleware`，Starlette 用 `StarletteInstrumentor`；**具体参数名以官方文档为准**。

### 5.2 回写 trace_id 到响应头与日志

```python
# app/middleware/trace_header.py
from fastapi import Request, Response
from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware


def current_trace_id() -> str:
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else ""


class TraceHeaderMiddleware(BaseHTTPMiddleware):
    """把 trace_id 放进响应头，便于调用方报障时直接给出。"""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        trace_id = current_trace_id()
        if trace_id:
            response.headers["X-Trace-Id"] = trace_id
        return response
```

```python
app.add_middleware(TraceHeaderMiddleware)   # 先加 = 更外层
FastAPIInstrumentor.instrument_app(app)     # 后加 = 更内层
```

Starlette 中间件是**洋葱模型（后加的更靠外）**，OTel 的 ASGI 中间件必须在**外层**，才能保证 `call_next` 之后用户中间件仍处于 span context 中；顺序反了 `current_trace_id()` 会拿到空值（见 9.7）。

### 5.3 为什么必须用 contextvars

**核心问题**：Agent 服务是异步的，同一时刻几十个请求在同一个事件循环里交错执行。如果「当前 span」存在全局变量里，A 请求开 span 后 `await` 让出控制权，B 请求覆盖了全局变量，A 唤醒后拿到的就是 B 的 span——**链路彻底串了**。

OTel Python 用的是标准库 **`contextvars.ContextVar`**：每个 asyncio Task 拥有自己的 context 副本。

| 场景 | context 行为 | 结果 |
| --- | --- | --- |
| 同一协程链 `await` | 共享同一 context | ✅ 父子关系正确 |
| `asyncio.create_task(...)` | 复制当前 context | ✅ 子任务继承父 span |
| `asyncio.gather(...)` | 各任务各自复制 | ✅ 并行分支挂到同一父 span |
| `loop.run_in_executor(...)` | 线程池里**没有** context | ❌ 需显式传递 |
| Celery / 多进程 worker | 各自独立 | ⚠️ 靠消息头传 traceparent |

```python
import asyncio
import contextvars


async def run_blocking(fn, *args):
    """线程池里执行的同步函数：手动带上 context。"""
    ctx = contextvars.copy_context()
    return await asyncio.get_running_loop().run_in_executor(None, lambda: ctx.run(fn, *args))
```

> **类比 Java**：Java 里对应的是 `ThreadLocal` / MDC——同步阻塞模型够用，但线程池复用与响应式（Reactor）下会串，所以 Java 生态也在往显式 Context 传播走。Python 的 `contextvars` 是语言级原生方案，比 `threading.local` 更贴合 async。

**结论**：用官方 SDK 与 instrumentation 时，同一异步任务链里的 span 不会串；但**自建线程池、自起独立 Task、跨进程传递**这三处要额外注意。这也是「不能用全局变量 + 手写 trace_id 字符串」的根本原因。

## 六、与 LangChain / LangGraph 集成

### 6.1 两种思路

| 思路 | 做法 | 优点 | 缺点 |
| --- | --- | --- | --- |
| ① 用 OTel 兼容后端 | 框架回调直接发给支持 OTLP 的后端（如 Langfuse 的 OTel 接入），或用社区 instrumentation 包自动埋点 | 几乎零代码、覆盖全 | LLM 属性口径由第三方定义，跨服务定制受限 |
| ② 自建 callback handler | 实现 `BaseCallbackHandler` / `AsyncCallbackHandler`，在每个 LLM / 工具调用起止开 span | 完全可控、属性与业务对齐 | 需自己维护，易与 instrumentation 重复埋点 |

**推荐**：生产用 **① 打底 + ② 补充**——用现成方案拿覆盖度，再用手写 span（4.6 / 4.7）补充**框架看不见的业务节点语义**。

```text
图节点（自建 span：agent.node.*）            ← ② 你写的，业务语义
  ├─ LLM 调用（框架回调 span：chat gpt-4o）    ← ① 自动/平台提供，LLM 语义
  └─ 工具调用（自建 span：execute_tool *）     ← ② 你写的，工具语义
```

现成方案举例：**Langfuse** 官方提供 OTel 接入（把 OTLP 数据送进 Langfuse，或让应用用 OTel SDK 而 Langfuse 作后端）；**LangSmith** 提供与 OpenTelemetry 的对接文档；**Arize OpenInference** 提供 LangChain instrumentation（`openinference-instrumentation-langchain`）；Galileo、Fiddler 等也提供 LangGraph 的 OTel instrumentation。**版本与支持范围以各自官方文档为准**——这块生态变化很快，选型先确认「支不支持你用的 LangChain / LangGraph 大版本」。

### 6.2 一个 OTel callback handler 骨架

关键难点：**回调是「开始/结束分离」的**，不像 `with` 语句能自动收尾。做法是用 `run_id` 做键存 span，结束时取出并 `end()`。

```python
# app/langchain_otel.py
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode

_tracer = trace.get_tracer("agent.langchain")


class OTelCallbackHandler(AsyncCallbackHandler):
    """LLM 与工具建 span；链回调刻意不实现，避免与 @traced_node 重复（见 6.3）。"""

    def __init__(self) -> None:
        super().__init__()
        self._spans: dict[str, Span] = {}

    def _start(self, run_id: UUID, name: str, attrs: dict[str, Any] | None = None) -> None:
        # start_span 继承「当前 context」，因此自动成为调用方 span 的子 span
        span = _tracer.start_span(name)
        if attrs:
            span.set_attributes({k: v for k, v in attrs.items() if v is not None})
        self._spans[str(run_id)] = span

    def _end(self, run_id: UUID, *, attrs: dict | None = None, error: BaseException | None = None) -> None:
        span = self._spans.pop(str(run_id), None)
        if span is None:
            return
        if attrs:
            span.set_attributes({k: v for k, v in attrs.items() if v is not None})
        if error is not None:
            span.record_exception(error)
            span.set_status(Status(StatusCode.ERROR, str(error)))
        else:
            span.set_status(Status(StatusCode.OK))
        span.end()          # 必须 end，否则这个 span 永远不会被导出

    # ---------- LLM ----------
    async def on_llm_start(self, serialized, prompts, *, run_id, metadata=None, **kwargs):
        metadata = metadata or {}
        model = metadata.get("ls_model_name") or (serialized or {}).get("kwargs", {}).get("model_name")
        self._start(run_id, f"chat {model or 'unknown'}", {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": model,
            "gen_ai.system": metadata.get("ls_provider"),
            "prompt.count": len(prompts or []),
        })

    async def on_llm_end(self, response, *, run_id, **kwargs):
        self._end(run_id, attrs=_extract_usage(response))

    async def on_llm_error(self, error, *, run_id, **kwargs):
        self._end(run_id, error=error)

    # ---------- 工具 ----------
    async def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
        name = (serialized or {}).get("name", "unknown")
        self._start(run_id, f"execute_tool {name}", {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": name,
            "tool.input.length": len(input_str or ""),     # 只记长度，不记正文
        })

    async def on_tool_end(self, output, *, run_id, **kwargs):
        self._end(run_id, attrs={"tool.status": "ok"})

    async def on_tool_error(self, error, *, run_id, **kwargs):
        self._end(run_id, attrs={"tool.status": "error", "error.type": type(error).__name__}, error=error)

    # 链（on_chain_*）刻意不实现：节点 span 由 @traced_node 负责（见 6.3）


def _extract_usage(response: Any) -> dict[str, Any]:
    """尽力提取 token 用量；不同提供商字段不一致，缺失就返回空。字段名以官方文档为准。"""
    try:
        usage = getattr(response.generations[0][0].message, "usage_metadata", None) or {}
    except Exception:                                # noqa: BLE001
        return {}
    return {
        "gen_ai.usage.input_tokens": usage.get("input_tokens"),
        "gen_ai.usage.output_tokens": usage.get("output_tokens"),
        "gen_ai.response.model": (getattr(response, "llm_output", None) or {}).get("model_name"),
    }
```

挂载方式：`ChatOpenAI(model="gpt-4o", callbacks=[handler])`，或整图执行时统一传入 `config={"callbacks": [handler], ...}`。

### 6.3 如何避免重复埋点

重复埋点的表现：Jaeger 里同一个工具调用出现**两个** `execute_tool query_metrics` span（一个来自装饰器、一个来自 callback handler），span 数量翻倍、成本翻倍、聚合口径算重。三条对策：

1. **按层分工（推荐）**：自建 span 管图节点与业务语义（`agent.node.*`），callback handler 管 LLM 与工具（`gen_ai.*` / `execute_tool *`）。骨架里**干脆不实现 `on_chain_*`**，就是这个分工。
2. **用 metadata 判重**：LangGraph 回调 metadata 里有 `langgraph_node` / `langgraph_step`，可据此决定是否建 span；或在自己的装饰器里 `span.set_attribute("traced.by", "decorator")`，handler 里检查后跳过。
3. **只保留一个来源**：若同时装了社区 LangChain instrumentation，就把自己的 `on_llm_start` / `on_tool_start` **关掉**，只留节点级自建 span。

**验证方法**：拿一次典型任务在 Jaeger 里数 span 个数，与 4.4 的「20~30 个」估算对比，数量异常翻倍基本就是重复埋点。

## 七、上下文传播与日志关联

### 7.1 W3C traceparent

跨进程传播的事实标准是 **W3C Trace Context**，核心是一个 HTTP 头：

```text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             │  │                                │                │
             │  │                                │                └─ flags（01 = sampled）
             │  │                                └─ parent-id（16 hex = 64 bit span_id）
             │  └─ trace-id（32 hex = 128 bit）
             └─ version（00）
```

配套还有 `tracestate`（厂商扩展键值对）与可选的 `baggage`（跨服务携带业务键值对，**谨慎用：会随每次请求传播，可能泄露信息**）。Python 侧出站注入一行搞定：

```python
from opentelemetry import propagate

headers: dict[str, str] = {}
propagate.inject(headers)          # headers == {"traceparent": "00-...-...-01"}
async with httpx.AsyncClient() as client:
    await client.get("http://metrics-svc/api/v1/query", headers=headers)
```

（用 `HTTPXClientInstrumentor` 后连这段都不用写。）

### 7.2 跨服务传播示例

```text
[Python Agent]  POST /agent/run
   trace_id = 4bf92f35...        ← FastAPI instrumentation 生成
        │  httpx 出站（自动 inject）
        ▼
[Java 指标服务]  GET /api/v1/query
   traceparent: 00-4bf92f35...-a1b2c3d4...-01
   → Java 用 OTel Java Agent 或 Micrometer Tracing 提取，生成 server span，trace_id 不变 ✅
        │
        ▼
[MCP Server]  tools/call search_runbook
   traceparent 由 MCP client 注入到请求 meta（若实现支持），同一 trace_id 延续
```

三个要点：

1. **跨语言只要都遵守 W3C Trace Context**：Java 侧用 OTel Java Agent（`-javaagent:opentelemetry-javaagent.jar`）或 Micrometer Tracing，基本是零改造接入；
2. **MCP 场景要留意**：MCP 协议本身不一定原生携带 HTTP 头（stdio 传输时更没有），需要在 MCP 的 metadata / arguments 里显式传 `traceparent`，或用 HTTP 传输时靠 instrumentation 自动完成——**具体做法以 MCP 规范与所用 SDK 文档为准**；
3. **代理与网关可能丢头**：如果 Nginx / API 网关配了头白名单，记得把 `traceparent`、`tracestate`、`baggage` 加进去。

> **类比 Java**：这套机制等价于 Dubbo / Spring Cloud Sleuth 的 RPC 上下文透传，区别是 Sleuth 当年的 B3 头是自成一套，而 W3C traceparent 是跨厂商标准。如果公司既有系统还在用 B3 头，OTel 提供 `b3` / `b3multi` propagator，可**同时启用多个**做过渡：`OTEL_PROPAGATORS=tracecontext,b3multi,baggage`。

### 7.3 日志注入 trace_id

日志与 trace 一关联，排障效率提升是数量级的：**在 Kibana 搜一个 task_id，就能拿到同一时刻所有服务的日志，并直接点进 Jaeger 看链路。**

更省事的做法是装 `opentelemetry-instrumentation-logging` 并 `LoggingInstrumentor().instrument(set_logging_format=True)`，之后日志格式里可直接用 `%(otelTraceID)s` / `%(otelSpanID)s`。下面这个手写方案更可控（字段名、空值都由你决定），生产环境推荐用它：

```python
# app/logging_setup.py
import json
import logging
from contextvars import ContextVar

from opentelemetry import trace

task_id_var: ContextVar[str | None] = ContextVar("task_id", default=None)


class TraceContextFilter(logging.Filter):
    """把 trace_id / span_id / task_id 注入每条日志记录。"""

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = trace.get_current_span().get_span_context()
        record.trace_id = format(ctx.trace_id, "032x") if ctx.is_valid else ""
        record.span_id = format(ctx.span_id, "016x") if ctx.is_valid else ""
        record.trace_sampled = bool(ctx.trace_flags.sampled) if ctx.is_valid else False
        record.task_id = task_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """结构化 JSON 日志：字段名与 03 / 06 篇口径对齐。"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "service": getattr(record, "service", "ops-agent"),
            "message": record.getMessage(),
            # 链路关联字段
            "trace_id": getattr(record, "trace_id", ""),
            "span_id": getattr(record, "span_id", ""),
            "trace_sampled": getattr(record, "trace_sampled", False),
            # 业务关联字段
            "task_id": getattr(record, "task_id", None),
            "conversation_id": getattr(record, "conversation_id", None),
            "user_id_hash": getattr(record, "user_id_hash", None),   # 脱敏后，不落原始标识
            "node": getattr(record, "node", None),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(TraceContextFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
```

业务侧带上业务字段：

```python
logger.info("tool call finished", extra={"node": "executor", "conversation_id": cid})
task_id_var.set(state["task_id"])      # 此后同一 async 任务的日志都带上 task_id
```

输出示例：

```json
{"ts":"2025-01-01T10:00:00+0800","level":"INFO","logger":"app.executor","service":"ops-agent",
 "message":"tool call finished","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736",
 "span_id":"1122334455667788","trace_sampled":true,"task_id":"task-20250101-001","node":"executor"}
```

### 7.4 结构化日志字段约定

阶段 5 的 03 / 04 / 06 三篇共用一套字段名，避免「日志叫 `traceId`、指标标签叫 `trace_id`」的割裂：

| 字段 | 类型 | 说明 | 同时出现在 |
| --- | --- | --- | --- |
| `trace_id` / `span_id` | string（hex） | 链路关联 | 日志、span 属性 |
| `task_id` | string | 任务 id（== Checkpoint 的 `thread_id`） | 日志、span 属性、指标标签 |
| `conversation_id` | string | 会话 id | 日志、span 属性 |
| `user_id_hash` | string | 用户标识哈希（**不落原始值**） | 日志、span 属性 |
| `node` | string | 图节点名 | 日志、span 属性 |
| `tool_name` | string | 工具名 | 日志、span 属性、指标标签 |
| `model` | string | 模型名 | 日志、span 属性、成本指标标签 |
| `cost_usd` | number | 成本估算 | 日志、span 属性、成本指标值 |
| `error_type` | string | 低基数错误分类 | 日志、span 属性、错误率指标标签 |

**原则**：**日志里能高基数的字段（task_id、user_id_hash），在指标标签里必须砍掉**（[06 篇](06-Prometheus与Grafana监控告警.md) 会讲标签基数爆炸）。trace 是两者之间的桥梁——它保留高基数细节，同时能聚合成低基数指标。

## 八、导出与部署

### 8.1 Collector 的作用

| 阶段 | 组件 | 干什么 |
| --- | --- | --- |
| 接收 | receiver | `otlp`（gRPC 4317 / HTTP 4318）、`prometheus`、`jaeger`、`filelog` |
| 处理 | processor | `batch`、`memory_limiter`、`attributes`（增删改）、`tail_sampling`、`transform`（脱敏） |
| 导出 | exporter | `otlp/jaeger`、`otlp/tempo`、`otlphttp/langfuse`、`prometheusremotewrite`、`debug` |
| 扩展 | connector | 把 trace 转成 metric（spanmetrics）、service graph |

**为什么不让应用直接发给后端？** ① **解耦**：后端换了、加了，应用不改代码不改配置；② **集中治理**：统一做 PII 脱敏、属性重命名、采样；③ **卸载**：批量、压缩、重试都在 Collector 做，应用侧开销更小；④ **协议适配**：把 OTLP 转成后端认识的格式（如 Prometheus remote write）。

### 8.2 OTLP/gRPC vs HTTP

| 维度 | OTLP/gRPC（:4317） | OTLP/HTTP（:4318） |
| --- | --- | --- |
| 性能 | 更高（长连接、二进制流） | 略低 |
| 兼容性 | 需要 HTTP/2，部分代理/网关不友好 | 走标准 HTTP/1.1，穿透性好 |
| 适用 | 内网服务 → Collector | 跨公网、经网关/CDN、浏览器 SDK |
| Python 包 | `opentelemetry-exporter-otlp-proto-grpc` | `opentelemetry-exporter-otlp-proto-http` |
| 端点写法 | `http://collector:4317` | `http://collector:4318/v1/traces` |

**实践建议**：应用 → Collector 用 gRPC（同集群内网），Collector → 外部后端用 HTTP（穿透性好、便于配鉴权头）。

### 8.3 采样策略

**头部采样（Head Sampling）**：trace 开始时决定，**决策随 traceparent 传播，整条链路一致**。

```python
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased, TraceIdRatioBased

sampler = ParentBased(root=TraceIdRatioBased(0.1))   # 有父跟随父，无父按 10% 抽
# 也可以用环境变量：OTEL_TRACES_SAMPLER=parentbased_traceidratio + OTEL_TRACES_SAMPLER_ARG=0.1
```

| 采样器 | 行为 |
| --- | --- |
| `AlwaysOn` / `AlwaysOff` | 全采 / 全不采（开发 / 关闭） |
| `TraceIdRatioBased(p)` | 按 trace_id 哈希比例采样（确定性，同一 trace 结论一致） |
| `ParentBased(root=...)` | 有父时跟随父决策，无父时用 `root` 采样器 |
| `ParentBased(root=..., remote_parent_sampled=...)` | 对「远端父级」单独定制（跨服务细节，**以官方文档为准**） |

**尾部采样（Tail Sampling）**：数据先全收，在 Collector 里等 trace 完整后**再决定保留哪些**。好处是能做「错误全留、慢的全留、正常抽 1%」，代价是需要 `decision_wait` 窗口与内存。

```yaml
processors:
  tail_sampling:
    decision_wait: 10s              # 等 trace 完整的最长时间
    num_traces: 100000              # 内存中保留的 trace 上限
    policies:
      - name: errors
        type: status_code
        status_code: {status_codes: [ERROR]}      # 有错误的全留
      - name: slow
        type: latency
        latency: {threshold_ms: 5000}             # 慢请求全留
      - name: baseline
        type: probabilistic
        probabilistic: {sampling_percentage: 1}   # 其余抽 1%
```

**高流量下 Agent 全量 trace 的成本**：一次任务 20~30 个 span，全量存 30 天、每天 10 万次任务的量级，存储与后端费用非常可观。推荐分层策略：

| 环境 | 策略 | 理由 |
| --- | --- | --- |
| 开发 / 测试 | `AlwaysOn` + `ConsoleSpanExporter` 或本地 Jaeger | 要看全貌 |
| 预发 | `ParentBased(root=TraceIdRatioBased(1.0))` | 全量但量小 |
| 生产 | 头部 `TraceIdRatioBased(0.05~0.2)`，或 Collector 尾部采样（错误/慢全留 + 基线抽样） | 成本与可观测性的平衡 |
| 特定客户 | 用属性/baggage 标记 VIP 租户，在 `tail_sampling` 里按属性全留 | 大客户问题必须能查 |

### 8.4 docker compose：Collector + Jaeger

`otel-collector-config.yaml`：

```yaml
receivers:
  otlp:
    protocols:
      grpc: {endpoint: 0.0.0.0:4317}
      http: {endpoint: 0.0.0.0:4318}

processors:
  memory_limiter:                 # 不能省：防流量尖峰把 Collector 打 OOM
    check_interval: 1s
    limit_percentage: 75
    spike_limit_percentage: 20
  attributes/cleanup:             # 属性治理：删掉潜在 PII
    actions:
      - {key: user.email, action: delete}
      - {key: http.request.header.authorization, action: delete}
  batch: {send_batch_size: 512, timeout: 5s}

exporters:
  otlp/jaeger: {endpoint: jaeger:4317, tls: {insecure: true}}

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, attributes/cleanup, batch]
      exporters: [otlp/jaeger]
```

`docker-compose.yaml`：

```yaml
services:
  jaeger:
    image: jaegertracing/all-in-one:1.62
    environment:
      - COLLECTOR_OTLP_ENABLED=true
    ports:
      - "16686:16686"        # Jaeger UI

  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.120.0
    command: ["--config=/etc/otel/config.yaml"]
    volumes:
      - ./otel-collector-config.yaml:/etc/otel/config.yaml:ro
    ports:
      - "4317:4317"          # OTLP gRPC
      - "4318:4318"          # OTLP HTTP
      - "13133:13133"        # health_check
    depends_on:
      - jaeger

  agent-api:
    build: .
    environment:
      OTEL_SERVICE_NAME: ops-agent
      OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-collector:4317
      OTEL_EXPORTER_OTLP_PROTOCOL: grpc
      OTEL_TRACES_SAMPLER: parentbased_traceidratio
      OTEL_TRACES_SAMPLER_ARG: "1.0"
    ports:
      - "8000:8000"
    depends_on:
      - otel-collector
```

```bash
docker compose up -d
# Jaeger UI: http://localhost:16686 → Service 选 ops-agent → Find Traces
```

**注意**：镜像 tag（`jaegertracing/all-in-one:1.62`、`otel/opentelemetry-collector-contrib:0.120.0`）会随时间演进，且 **Jaeger 1.x → 2.x 有架构变化**（2.x 基于 OTel Collector 构建，配置方式不同）——**具体版本与配置以官方文档为准**。本地学习用 `all-in-one` 最省事，生产建议直接把数据发到持久化后端（Tempo / Jaeger + 对象存储）。

## 九、踩坑点

| # | 坑 | 症状 | 对策 |
| --- | --- | --- | --- |
| 9.1 | 忘了 shutdown / flush | Jaeger 里最后几条 span（往往是报错那次）没有；短脚本一条 trace 都没有 | `BatchSpanProcessor` 是异步批量的，进程直退就丢队列。用 `atexit.register(provider.shutdown)`、FastAPI 里放 `lifespan`，关键节点 `force_flush()` |
| 9.2 | 异步任务丢 context | Celery / 线程池 / `create_task` 起的任务在 Jaeger 里是独立根 trace | `contextvars.copy_context()` + `ctx.run(fn)`；Celery 用其 instrumentation 或手动 `propagate.extract`；确实该独立的就接受它是根 trace，但**打上 `task.id` 属性**做关联 |
| 9.3 | 属性里塞大文本 | 属性值被截断、后端费用暴涨、Collector 丢数据 | 属性只放低基数；大文本用 Events 或专门字段；**完整 prompt / 响应正文交给 Langfuse（03 篇）**，OTel 里只留 `prompt.length` / `prompt.hash` |
| 9.4 | 属性里塞 PII | 合规审计发现 trace 里有邮箱、手机号、完整 SQL 参数 | 三道防线：① 入口白名单（不做全透传）；② Collector 侧 `attributes` / `transform` processor 删敏感 key；③ 哈希与截断（`user.id.hash`）。详见 [05 篇](05-Agent安全评测与加固.md) |
| 9.5 | 采样后 trace 不成链 | 只看到半截链路，或下游自己成了根 | 采样决策随 traceparent 传播。**所有服务统一 `ParentBased`**，只在真正入口配根采样比例；`OTEL_PROPAGATORS` 保持一致 |
| 9.6 | span 名不统一 | Jaeger 的 operation 列表几千条、平均耗时没法看 | 用 4.1 模板 + 常量集中定义 + 评审检查；**变量信息放属性，不放名字** |
| 9.7 | 中间件顺序错 | `X-Trace-Id` 时有时无、日志 `trace_id` 为空 | Starlette 中间件「后加的更外层」，OTel ASGI 中间件必须在外层（5.2）；用最小请求验证响应头 |
| 9.8 | 版本升级 API 迁移 | 升级后 `ImportError` / `AttributeError`，或属性名后端不认 | 锁版本（`pip-compile` / `uv lock`）；升级前看 CHANGELOG；属性名集中一处；**新旧属性短期双写**；semconv 仍是 experimental，**以官方文档为准** |
| 9.9 | 其他常见漏项 | `unknown_service`、探针灌满存储、span 只 start 不 end 泄漏、重复埋点、本地无 Collector 时日志刷屏 | 设 `OTEL_SERVICE_NAME`；配 `excluded_urls`；一律用 `with` / `start_as_current_span`，callback handler 里务必 `end()`；6.3 分工；测试用 `OTEL_SDK_DISABLED=true` 或 `ConsoleSpanExporter` |

## 十、与其他篇目关系

| 篇目 | 关系 |
| --- | --- |
| [03 篇](03-Langfuse与LangSmith可观测性.md) | **互补**：03 讲产品级 LLM 观测（prompt / token / 评分 / 数据集），04 讲厂商中立的链路标准（跨服务 / 跨语言 / 日志关联），二者通过「Collector 扇出」共存 |
| [06 篇](06-Prometheus与Grafana监控告警.md) | **下游**：本文的 span 属性（`cost.usd`、`error.type`、`tool.name`、`gen_ai.usage.*`）正是 06 篇从 trace 派生指标的数据源，字段口径在 7.4 已对齐 |
| [05 篇](05-Agent安全评测与加固.md) | **交叉**：9.4 的 PII 治理、审计 trace（谁在何时调了什么工具）属 05 篇，哈希化与白名单要两边一致 |
| [07 篇](07-生产化部署与CI-CD.md) | **下游**：Collector 的部署形态（sidecar / DaemonSet / Gateway）、环境变量注入、镜像版本管理属 07 篇 |
| [01 篇](01-评测方法论与GoldenDataset设计.md) / [02 篇](02-评测指标详解与实现.md) | **数据来源**：trace 里的真实请求可作为评测数据集素材，线上 trace 回放是评测与灰度的常见做法 |
| [08 篇](08-阶段5综合实践-全链路观测与评测报告.md) | **汇总**：把 03 + 04 + 06 的观测能力整合成「全链路观测 + 评测报告」 |
| 阶段 3 `../阶段3-Tools与MCP/02-工具调用工程化-校验超时重试降级审计.md` | 4.7 的工具埋点是其「审计」要求的可观测性落地 |
| 阶段 4 `../阶段4-复杂工作流与Deep-Agents/05-Checkpoint持久化与长任务恢复.md` | `thread_id` 与本文 `task.id` 同义，配合可做「task_id → checkpoint 历史 → trace」三向定位 |

## 学习自检与练习

### 练习 1：给阶段 3 项目接 OTel 并导出到 Jaeger

**任务**：把阶段 3「企业运维分析 Agent」接上 OTel，能在 Jaeger 里看到一条完整调用树。

1. 用 8.4 的 compose 起 Collector + Jaeger；
2. 落地 3.2 的 `telemetry.py`，在 FastAPI `lifespan` 里初始化与关闭；
3. `FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")` + `HTTPXClientInstrumentor().instrument()`；
4. 用 `@traced_node` 装饰全部图节点，用 `traced_tool` 包装 2~3 个高频工具；
5. 发一次真实请求，在 `http://localhost:16686` 按 `service.name` 查询。

**提示**：节点装饰器要装饰**注册进 `add_node` 的那个函数**；工具装饰器要在 `@tool` **内层**。

**验收标准**：① Jaeger 里能看到 4 层以上的树（`POST /agent/run` → 节点 span → `chat <model>` / `execute_tool <name>`）；② 节点 span 上有 `agent.node.name`、`task.id`，LLM span 上有 `gen_ai.request.model` 与 token 用量；③ 人为让工具抛异常，该 span 在 Jaeger 里显示为 **error** 且能看到堆栈；④ 杀掉进程重启后，最后一次请求的 span **仍然完整**（验证 flush 生效）。

### 练习 2：实现 trace_id 注入日志

**任务**：让每条日志都带 `trace_id` / `span_id` / `task_id`，并能从日志跳回 trace。

1. 实现 7.3 的 `TraceContextFilter` 与 `JsonFormatter`（或直接用 `LoggingInstrumentor`）；
2. 用 `task_id_var` 在任务入口设置 `task_id`；
3. 复现一个「工具超时」错误，从响应头 `X-Trace-Id` 取出该请求的 trace_id；
4. 在日志里 grep 这个 trace_id（应能一次拿到该请求全部日志），再在 Jaeger 里按同一 trace_id 查询定位同一条链路。

**提示**：filter 要挂在**真正在用的 handler** 上（挂在 root logger 上而 handler 在别处时不生效）；异步场景 `task_id` 用 `ContextVar`，不要用全局变量。

**验收标准**：① 每条日志都是合法 JSON，含 `trace_id` / `span_id` / `task_id` / `service`；② 一次请求内所有模块的日志 `trace_id` **完全相同**；③ 20 并发压测下**不同请求的 trace_id 不串**（验证 contextvars 正确性）；④ 用一个脚本把「日志取 trace_id → 拼 Jaeger 查询 URL」自动化，贴出最终 URL。

### 练习 3：写一个 OTel callback handler

**任务**：基于 6.2 的骨架写一个可用的 LangChain callback handler，并验证不重复埋点。

1. 实现 `OTelCallbackHandler`（LLM 与工具建 span，链回调刻意不实现）；
2. 挂在 `ChatOpenAI` 或整图 `config["callbacks"]` 上，同时保留练习 1 的 `@traced_node`；
3. 跑一次包含 2 次 LLM + 2 次工具调用的任务，在 Jaeger 里数 span 个数；
4. 自行补上 `on_chain_start` / `on_chain_end` 建链级 span，再跑一次，对比 span 个数变化。

**提示**：token 用量在不同提供商 / 不同 LangChain 版本里的字段位置不同（`usage_metadata` / `llm_output`），要做好缺失兜底（骨架里的 `_extract_usage` 已 try/except）；`start_span` 不 `end` 会导致 span 永不导出，`on_*_error` 里也必须 `end`。

**验收标准**：① LLM span 名形如 `chat gpt-4o` 且带 `gen_ai.*` 属性，工具 span 名形如 `execute_tool query_metrics`；② 与练习 1 的装饰器 span **没有重复**；③ LLM 抛异常时 span 状态为 ERROR 且带堆栈；④ 能写出「span 数 = 节点数 + LLM 次数 + 工具次数 + 出站 HTTP 次数 + 2」的等式解释你看到的结果。

### 自检清单

- [ ] 能说清 OTel 四件套（规范 / SDK / Collector / OTLP）各自职责；
- [ ] 能说出 OTel 与 Langfuse / LangSmith 的定位差异，并画出「Collector 扇出」的共存架构；
- [ ] 能解释 Trace / Span / SpanContext / trace_id / span_id / Resource / Sampler / Exporter；
- [ ] 能写出带 `Resource` + `BatchSpanProcessor` + `OTLPSpanExporter` + `shutdown` 的 `telemetry.py`；
- [ ] 记住 `OTEL_SERVICE_NAME` / `OTEL_EXPORTER_OTLP_ENDPOINT` / `OTEL_TRACES_SAMPLER` 的作用；
- [ ] 能按 semconv 口径设计 span 名与 `gen_ai.*` 属性，并知道它仍是 experimental；
- [ ] 能写出 `@traced_node` 与 `traced_tool`，且知道 `record_exception` 与 `set_status(ERROR)` 要一起用；
- [ ] 能给 FastAPI 接自动埋点，把 trace_id 回写响应头与日志，并解释 contextvars 的作用；
- [ ] 能写出 OTel callback handler 骨架，并说清如何避免重复埋点；
- [ ] 能解释 W3C traceparent 的格式与跨语言传播，并能说出 MCP 场景的特殊性；
- [ ] 能配置 Collector（receiver / processor / exporter / pipeline）与采样策略，且知道 `memory_limiter` 不能省；
- [ ] 能列出至少 6 个踩坑点及其对策（丢 span、context 丢失、大文本、PII、断链、命名不统一、版本迁移）。

## 参考资料

- OpenTelemetry 官方文档 - Python Getting Started: https://opentelemetry.io/docs/languages/python/getting-started/
- OpenTelemetry 官方文档 - Python Instrumentation（手动埋点 API）: https://opentelemetry.io/docs/languages/python/instrumentation/
- OpenTelemetry 官方文档 - Python Instrumenting Libraries: https://opentelemetry.io/docs/languages/python/libraries/
- OpenTelemetry 官方文档 - General SDK Configuration（`OTEL_SERVICE_NAME` 等环境变量）: https://opentelemetry.io/docs/languages/sdk-configuration/general/
- OpenTelemetry 官方文档 - Semantic Conventions for Gen AI: https://opentelemetry.io/docs/specs/semconv/gen-ai/
- OpenTelemetry 官方文档 - Recording Exceptions（`record_exception` 与状态约定）: https://opentelemetry.io/docs/specs/otel/trace/exceptions/
- OpenTelemetry 官方文档 - Sampling（头部 / 尾部采样概念）: https://opentelemetry.io/docs/concepts/sampling/
- OpenTelemetry 官方文档 - Collector: https://opentelemetry.io/docs/collector/
- OpenTelemetry Python - OTLP Exporter API: https://opentelemetry-python.readthedocs.io/en/latest/exporter/otlp/otlp.html
- opentelemetry-python-contrib - FastAPI Instrumentation: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html
- opentelemetry-python 仓库（SDK 源码与 CHANGELOG，升级前必看）: https://github.com/open-telemetry/opentelemetry-python
- opentelemetry-collector-contrib - Tail Sampling Processor 配置: https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/tailsamplingprocessor/README.md
- W3C Trace Context 规范（`traceparent` / `tracestate` 格式）: https://www.w3.org/TR/trace-context/
- Jaeger 官方文档 - Getting Started（含 OTLP 接入）: https://www.jaegertracing.io/docs/2.17/getting-started/
- Langfuse 官方文档 - OpenTelemetry 集成: https://langfuse.com/integrations/native/opentelemetry
