# Prometheus 与 Grafana：Agent 指标监控与告警

> 本文定位：阶段 5 的 [03 篇](03-Langfuse与LangSmith可观测性.md) 与 [04 篇](04-OpenTelemetry与自定义Tracing.md) 解决「**单次请求内部发生了什么**」——某条 trace 里模型调了几次、哪个工具超时了；[05 篇](05-Agent安全评测与加固.md) 补齐日志与审计。但 Trace 回答不了另一个问题：「**系统整体现在健不健康、要不要把人叫起来处理**」。这只能靠指标（Metrics）。本文讲透：Prometheus 数据模型与指标类型、`prometheus-client` 埋点（含一份 Agent 专用指标清单）、PromQL 常用查询、本地 Docker Compose 全套监控栈、Grafana 看板设计、告警规则与 Alertmanager 路由、SLO 与错误预算。核心纪律：**线上指标口径必须与 [02 篇](02-评测指标详解与实现.md) 的离线评测指标对齐**，否则「离线 92% 成功率、线上 78%」永远说不清是谁错了。前置：[02 篇](02-评测指标详解与实现.md)（指标定义）、[03](03-Langfuse与LangSmith可观测性.md)/[04 篇](04-OpenTelemetry与自定义Tracing.md)（trace 与埋点位置）。示例围绕阶段 3「企业运维分析 Agent」与阶段 4「研发效能 Agent」。

## 学习目标

学完本文，你应该能：

- 说清可观测性三支柱（Traces / Logs / Metrics）在 Agent 服务里的分工，以及为什么两者都要；
- 解释 Prometheus 数据模型（metric name + labels = 时间序列）与 pull/scrape 采集模型；
- 在 Counter / Gauge / Histogram / Summary 之间正确选型，并解释延迟为什么必须用 Histogram；
- 用 `prometheus-client` 在 FastAPI 里暴露 `/metrics`，避开多进程重复注册与基数爆炸；
- 独立设计一份 Agent 业务指标清单（请求、工具、任务、Token/成本、会话、HITL、错误分类）；
- 用 LangChain callback / LangGraph 节点钩子 / OTel SpanProcessor 自动埋点，而非到处手写 `inc()`；
- 写 ≥10 条可直接粘贴的 PromQL：速率、成功率、P95/P99、成本、Top N 失败；
- 用 docker compose 起 `agent + prometheus + grafana + alertmanager` 并端到端验证；
- 设计 Grafana 看板（面板清单、变量、单位、阈值）与分级告警规则（含 `for` 时长取舍）；
- 把「工具成功率 ≥ 95%」「P95 < 8s」写成 SLI/SLO，理解 burn rate 告警与错误预算。

## 一、可观测性三支柱与分工

### 1.1 三支柱各自回答什么

| 支柱 | 数据形态 | 回答的问题 | 成本 | 对应篇目 |
| --- | --- | --- | --- | --- |
| Traces（链路） | 结构化 span 树，单次请求全貌 | 「这一次请求为什么慢/为什么错？」 | 高（每请求一条，含 prompt） | [03](03-Langfuse与LangSmith可观测性.md)、[04 篇](04-OpenTelemetry与自定义Tracing.md) |
| Logs（日志） | 离散事件文本/JSON | 「当时发生了什么？谁在何时做了什么？」 | 中高（需采样与保留策略） | [05 篇](05-Agent安全评测与加固.md) |
| Metrics（指标） | 数值时间序列，预聚合 | 「整体健不健康？趋势如何？要不要报警？」 | 低（基数固定，可长期保留） | **本篇** |

类比：Traces 是**病历**（单个病人全过程），Logs 是**护理记录**（操作留痕），Metrics 是护士站墙上的**体温单与心率监护仪**。医生出事故要翻病历，但**值班护士看的是监护仪**——没人会为了发现「全病房都在发烧」去逐个翻病历。

### 1.2 为什么 Agent 服务两者都要

既然 [03 篇](03-Langfuse与LangSmith可观测性.md) 的 Langfuse 已经能看成功率、延迟、Token 和成本，为什么还要一套 Prometheus？

| 维度 | LLM 观测产品（Langfuse / LangSmith） | Prometheus + Grafana |
| --- | --- | --- |
| 主用途 | 调试、单条 trace 归因、Prompt 版本对比 | 监控、告警、容量与成本趋势 |
| 数据模型 | 事件/文档型，单条记录重 | 数值时间序列，单点轻 |
| 保留期 | 通常几十天，常采样 | 长期保留（月/年），可降采样 |
| 告警能力 | 偏产品内提醒；分组/抑制/静默弱 | Alertmanager 工业级：分组、抑制、静默、多级路由 |
| 与基础设施指标合流 | 难（CPU、连接池、队列深度不在它那儿） | 天然合流（`node_exporter`、`redis_exporter` 同一 PromQL） |

结论：**调试靠 trace，告警靠 metrics**。你不可能写一条规则叫「翻最近 5 分钟所有 trace，错误率超 5% 就打电话」——又慢又贵还不准。指标是**预聚合**的：无论 10 QPS 还是 10000 QPS，序列数固定，查询是常数级开销。

其次，Agent 还有基础设施层问题（阶段 4 的长任务队列积压、Checkpoint 库连接数、容器内存），Langfuse 看不见，而 Prometheus 能把两类指标放进同一张图：

```promql
# 业务侧完成速率 vs 基础设施侧 worker 内存：同一张图上才看得出
# "完成率掉下来是因为 OOM 重启"而不是"模型变笨了"
sum(rate(agent_tasks_total{status="completed"}[5m]))
container_memory_working_set_bytes{container="agent-worker"}
```

### 1.3 类比 Java

| Java 世界 | Agent 世界对应 | 说明 |
| --- | --- | --- |
| Micrometer + Actuator `/actuator/prometheus` | `prometheus-client` + FastAPI `/metrics` | 都是把进程内计数器暴露成 Prometheus 文本格式 |
| `Timer` / `DistributionSummary` | `Histogram` | Micrometer 的 `Timer` 底层就是直方图 |
| Spring 的 `@Timed` 注解（AOP 埋点） | 装饰器 / 中间件 / callback | 用钩子自动埋点，别在业务里手写 |
| Grafana + Prometheus 告警 | 完全一样 | 同一套产品 |

一句话：**你在 Java 里怎么给 Spring Boot 做监控，在 Python 里就怎么给 FastAPI + LangGraph 做监控**，只是自动埋点的钩子换成了 LangChain callback / OTel span processor。

## 二、Prometheus 数据模型与指标类型

### 2.1 Metric name + Labels = 时间序列

```text
<metric_name>{<label_name>=<label_value>, ...} -> [(timestamp, value), (timestamp, value), ...]
```

- **metric name**：测的是什么，如 `agent_requests_total`；
- **labels**：从哪个维度测的，如 `endpoint="/chat"`、`status="success"`；
- 一组**确定的** name + labels = 一条**时间序列（time series）**。

关键推论：**label 值不能随便放**。`user_id`、`session_id`、`request_id`、`trace_id` 这类取不完的值放进 label，会把一条序列炸成一百万条——**基数爆炸（cardinality explosion）**，会直接打死 Prometheus（详见 9.1）。

命名规范（官方 naming 实践）：snake_case；单位作**后缀**且用**基本单位**（秒用 `_seconds` 而非 `_milliseconds`）；计数器以 `_total` 结尾；直方图带单位后缀（`agent_request_duration_seconds`）；名字里不要重复 label 已表达的信息。

### 2.2 Pull / Scrape 采集模型

Prometheus 是**拉取式（pull）**：不是应用推数据，而是 Prometheus 每 `scrape_interval` 主动 `GET /metrics` 抓走指标文本存进时序库（TSDB）。

```text
┌────────────┐  GET /metrics（每 15s） ┌───────────────┐
│ Prometheus │ ──────────────────────> │ Agent 服务     │
│  (TSDB)    │ <────────────────────── │ :8000/metrics │
└─────┬──────┘   text/plain 指标文本     └───────────────┘
      │ 评估告警规则            ▲ PromQL 查询
      ▼                        │
┌─────────────┐  通知   ┌──────────┐
│ Alertmanager│ ──────> │ 值班人/群 │
└─────────────┘         └──────────┘
```

三条推论，写指标时必须知道：

1. **`/metrics` 必须廉价且无副作用**：每 15 秒被调一次，只能在内存里序列化已有计数器，**不能查数据库或调模型**；
2. **服务挂了立刻知道**：抓取失败会产生 `up{job="agent"} == 0`，这是最省事的存活告警；
3. **服务发现**：生产把 `static_configs` 换成 K8s SD / Consul / EC2 SD，新 Pod 自动纳入抓取。

推送式（Pushgateway）只用于短生命周期批任务。**长驻 Agent 服务用 pull，不要图省事上 Pushgateway**——它会让「实例消失」无法被检测。

### 2.3 四种指标类型与选型

| 类型 | 语义 | 只能怎么变 | Agent 用途 | PromQL 搭配 |
| --- | --- | --- | --- | --- |
| **Counter** | 单调递增累计计数 | 只能增（重启归零） | 请求数、工具调用数、Token、成本、错误数 | `rate()` / `increase()` |
| **Gauge** | 可增可减的瞬时值 | 任意 | 活跃会话、待审核数、队列深度、内存 | 直接查 / `avg_over_time()` |
| **Histogram** | 观测值分布（分桶计数） | 桶计数只增 | 请求延迟、工具耗时、任务步数 | `histogram_quantile()` |
| **Summary** | 观测值分布（客户端算分位） | 分位只增 | 不需跨实例合并的场景 | 直接查分位序列 |

**Counter 的重点是绝不用原始值**：`agent_requests_total == 1234567` 本身无意义（除非检测重启），你要的一定是 `rate(...)` = 每秒速率。**Gauge 的重点是它可能下降**，不能被 `rate()`；算平均/峰值用 `avg_over_time()` / `max_over_time()`。

### 2.4 Histogram vs Summary：延迟为什么必须用 Histogram

Histogram 在同一次 `/metrics` 里暴露三组序列：

```text
agent_request_duration_seconds_bucket{endpoint="/chat",le="2.0"} 301
agent_request_duration_seconds_bucket{endpoint="/chat",le="8.0"} 961
agent_request_duration_seconds_bucket{endpoint="/chat",le="+Inf"} 1000
agent_request_duration_seconds_sum{endpoint="/chat"} 3120.7
agent_request_duration_seconds_count{endpoint="/chat"} 1000
```

| 序列 | 含义 | 怎么用 |
| --- | --- | --- |
| `_bucket{le="X"}` | **累计计数**：耗时 ≤ X 秒的请求数（`le` = less than or equal） | `histogram_quantile()` 的输入；`_bucket{le="8"}/_count` 就是「8 秒内完成率」 |
| `_bucket{le="+Inf"}` | 全部观测值（等于 `_count`） | 兜底桶，必须有 |
| `_sum` | 所有观测值之和（秒） | `rate(_sum)/rate(_count)` = 平均值 |
| `_count` | 观测次数 | 成功率分母、吞吐分子 |

Summary 则直接暴露客户端算好的分位：`agent_request_duration_seconds{quantile="0.95"}`。看起来更省事，但在 Agent 服务里有三个致命缺陷：

1. **分位数不可聚合**。这是数学问题：8 个 Pod 各报「我的 P95 = 6.4s」，你**无法**算出整体 P95。正确值必须由全量分布算出——只有 Histogram 的桶能跨实例相加（`sum by (le)`）。而 Agent 服务必然多副本。
2. **时间窗口不可选**。Summary 的分位在进程内滑动窗口预先算好，查 `[5m]` 还是 `[1h]` 都是同一个数，**改不了**。Histogram 的窗口是查询时决定的。
3. **成本更高**。维护分位估算比「几次比较 + 计数」贵。

纪律：**耗时类指标一律用 Histogram；Summary 只在明确不需跨实例聚合、不需改窗口时才用。**

### 2.5 桶（buckets）怎么设

设错桶会让 **P95 严重失真**（见 9.2）。三条原则：覆盖真实分布（最小桶小于最快路径，最大桶大于超时）；前密后疏（延迟是长尾）；数量 10~15 个（桶数 × label 组合 = 序列数）。

```python
# 请求端到端耗时：缓存命中 <0.3s，单轮 LLM 2~6s，多工具长任务 5~30s，超时上限 60s
AGENT_LATENCY_BUCKETS = (0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 13.0, 21.0, 34.0, 60.0)
# 0.1/0.25 分辨缓存与纯计算；2/3/5 卡在单轮 LLM 区间；
# 8.0 必须是桶边界，否则「P95 < 8s」无法用 _bucket{le="8"} 精确表达；
# 8/13/21/34 覆盖多步长尾；60 对齐超时上限。
TOOL_LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0)
LLM_LATENCY_BUCKETS  = (0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0)
```

**变更桶 = 破坏历史可比性**：P95 曲线会出现断层，必须同步在看板上加 Annotation 标注。

## 三、Python 侧指标暴露

### 3.1 安装与最小例子

```bash
pip install prometheus-client fastapi uvicorn
```

`prometheus-client` 是官方 Python 客户端（GitHub `prometheus/client_python`，文档站 `prometheus.github.io/client_python`；API 细节以官方文档为准）。

```python
# metrics_demo.py
import time, random
from prometheus_client import Counter, Gauge, Histogram, start_http_server

REQUESTS = Counter("agent_requests_total", "Agent 请求总数", ["endpoint", "status"])
IN_PROGRESS = Gauge("agent_requests_in_progress", "处理中的请求数", ["endpoint"])
LATENCY = Histogram(
    "agent_request_duration_seconds", "Agent 请求端到端耗时", ["endpoint"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 13.0, 21.0, 34.0, 60.0),
)

def handle(endpoint: str) -> None:
    IN_PROGRESS.labels(endpoint=endpoint).inc()
    start = time.perf_counter()          # ✅ 单调时钟，不用 time.time()
    status = "success"
    try:
        time.sleep(random.uniform(0.05, 3.0))
        if random.random() < 0.05:
            status = "error"
    finally:
        LATENCY.labels(endpoint=endpoint).observe(time.perf_counter() - start)
        IN_PROGRESS.labels(endpoint=endpoint).dec()
        REQUESTS.labels(endpoint=endpoint, status=status).inc()

if __name__ == "__main__":
    start_http_server(8000)              # 在 :8000/metrics 暴露默认 REGISTRY
    while True:
        handle("/chat")
```

`curl localhost:8000/metrics` 得到 **exposition format** 文本（Prometheus 的抓取契约）：`# HELP` / `# TYPE` 注释行 + `指标名{label="值"} 数值`。

### 3.2 四种类型用法与易错点

```python
from prometheus_client import Counter, Gauge, Histogram

# ---- Counter：只能增 ----
tools = Counter("agent_tool_calls_total", "工具调用总数", ["tool", "result"])
tools.labels(tool="k8s_query", result="success").inc()
tools.labels(tool="k8s_query", result="success").inc(3)   # 批量 +3
# ❌ tools.labels(...).dec() / .set(0)    Counter 没有这两个方法
# 注：prometheus_client 会自动补 _total 后缀，对外暴露的都是 agent_tool_calls_total。

# ---- Gauge：可增可减 ----
hitl = Gauge("agent_hitl_pending", "待人工审核任务数", ["queue"],
             multiprocess_mode="max")     # 多进程聚合模式，见 3.4
hitl.labels(queue="approval").set(7)
hitl.labels(queue="approval").set_function(lambda: float(redis.llen("hitl:approval")))
# 其他技巧：with g.track_inprogress(): ...（自动 inc/dec，异常安全）
#           g.set_to_current_time()（记录"最后一次成功时间"，用于静默失败告警）

# ---- Histogram：观测分布 ----
lat = Histogram("agent_tool_duration_seconds", "工具耗时", ["tool"],
                buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0))
with lat.labels(tool="k8s_query").time():   # 上下文管理器自动计时
    do_query()
lat.labels(tool="k8s_query").observe(0.83)  # 或手动 observe

# ---- Summary：本文不推荐用于跨实例聚合 ----
```

| 坑 | 后果 | 正解 |
| --- | --- | --- |
| 有 label 却直接 `observe()` | 抛 `ValueError: Incorrect label names` | 先 `.labels(...)` 拿 child |
| 用 `time.time()` 计时 | 时钟跳变导致负数/巨大值 | `time.perf_counter()` |
| 只在 `try` 成功分支 observe | P95 只统计成功请求，**严重偏乐观** | 放 `finally` |
| 函数内重复 `Counter(...)` | `Duplicated timeseries` 异常 | 模块顶层定义一次 |
| 改指标名/help 文本 | `inconsistent help for metric` / 新建序列 | 视为**破坏性变更**，走变更流程 |

### 3.3 FastAPI 集成 `/metrics`

```python
# app/main.py（方式一：显式路由，推荐）
from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

app = FastAPI()

@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

# 方式二：挂载 ASGI 子应用
# from prometheus_client import make_asgi_app
# app.mount("/metrics", make_asgi_app())
```

用中间件统一埋点，比在每个 handler 里手写可靠：

```python
# app/middleware.py
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from .metrics import REQUESTS, IN_PROGRESS, LATENCY

SKIP_PATHS = {"/metrics", "/healthz", "/readyz", "/docs", "/openapi.json"}

class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in SKIP_PATHS:
            return await call_next(request)

        # ⚠️ 必须用"路由模板"（/tasks/{task_id}）而不是实例路径（/tasks/8f3a-...），
        #    否则每来一个任务就多一条时间序列 —— Agent 服务最常见的基数爆炸源
        route = request.scope.get("route")
        endpoint = getattr(route, "path", path)

        IN_PROGRESS.labels(endpoint=endpoint).inc()
        start = time.perf_counter()
        status = "success"
        try:
            response = await call_next(request)
            if response.status_code >= 500:
                status = "error"
            elif response.status_code == 429:
                status = "rate_limited"
            elif response.status_code >= 400:
                status = "client_error"
            return response
        except Exception:
            status = "exception"
            raise
        finally:
            LATENCY.labels(endpoint=endpoint).observe(time.perf_counter() - start)
            IN_PROGRESS.labels(endpoint=endpoint).dec()
            REQUESTS.labels(endpoint=endpoint, status=status).inc()
```

`/metrics` 不要加鉴权（走内网抓取），但**绝不能暴露公网**——指标名与 label 值会泄露内部结构。必须外部可达时用 `scrape_configs` 的 `basic_auth` 让 Prometheus 带凭据。

### 3.4 多进程陷阱与解法

`uvicorn --workers 4` 下每个 worker 有独立内存与 registry，Prometheus 每 15 秒随机打到其中一个，你看到的是**在几个值之间乱跳的计数器**——`rate()` 算出来是垃圾，且 counter 回退会被判定为**计数器重置**，曲线满是尖刺。

```bash
# 1) 必须在 import 任何指标定义之前设置共享目录
export PROMETHEUS_MULTIPROC_DIR=/tmp/prom_multiproc
rm -rf $PROMETHEUS_MULTIPROC_DIR && mkdir -p $PROMETHEUS_MULTIPROC_DIR
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

```python
# app/metrics_endpoint.py
import os
from fastapi import Response
from prometheus_client import (
    CollectorRegistry, CONTENT_TYPE_LATEST, generate_latest, multiprocess,
)

def metrics_response() -> Response:
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()               # 必须是"全新" registry
        multiprocess.MultiProcessCollector(registry) # 聚合所有 worker 的 mmap 文件
        data = generate_latest(registry)
    else:
        data = generate_latest()                     # 单进程：用默认 registry
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)

# 进程退出时清理自己的 mmap 文件，否则死进程的计数会一直累加
# gunicorn child_exit 钩子：multiprocess.mark_process_dead(worker.pid)
```

四条硬性纪律（细节以官方文档为准）：① `PROMETHEUS_MULTIPROC_DIR` 必须在指标定义前设置；② `/metrics` 必须用 `MultiProcessCollector` + 新 registry，不能直接 `generate_latest()` 默认 registry；③ Counter/Histogram 自动跨进程求和，**Gauge 必须显式指定 `multiprocess_mode`**（`all`/`liveall`/`min`/`max`/`livesum`/`sum`：活跃会话用 `livesum`，待审核数用 `max`）；④ 进程退出时 `mark_process_dead(pid)`。

**最省心的替代方案**：`--workers 1` + 多容器副本，每个副本各自被抓、由 `sum by (le)` 聚合。asyncio 本身能扛大量并发 I/O，中小规模 Agent 服务推荐这个姿势。

### 3.5 Agent 业务指标定义清单

两条设计约束：**每个指标都要对应一个决策**（进看板 / 进告警 / 进容量规划），没有决策用途的不要埋；**口径必须与 [02 篇](02-评测指标详解与实现.md) 对齐**。

| 指标名 | 类型 | Labels | 单位 | 口径（与 02 篇的对应） | 用途 |
| --- | --- | --- | --- | --- | --- |
| `agent_requests_total` | Counter | `endpoint`,`status` | 次 | `status` ∈ success/error/timeout/rate_limited/client_error；success = 完整返回且无未捕获异常 | 流量、成功率、错误率 |
| `agent_request_duration_seconds` | Histogram | `endpoint` | 秒 | 端到端耗时（含所有工具与 LLM 调用），对齐 02 篇「端到端延迟」 | P50/P95/P99、SLO |
| `agent_tool_calls_total` | Counter | `tool`,`result` | 次 | `result` ∈ success/error/timeout/rejected/invalid_args；success = 返回**有效结果**（非仅 HTTP 200） | 工具成功率 |
| `agent_tool_duration_seconds` | Histogram | `tool` | 秒 | 工具内部执行耗时（不含模型决策时间） | 工具 P95、慢工具定位 |
| `agent_tasks_total` | Counter | `status` | 次 | `status` ∈ completed/failed/rejected_by_human/cancelled；**完成率 = completed / 全部终态**（对齐 02 篇 Task Completion Rate） | 任务完成率 |
| `agent_task_duration_seconds` | Histogram | `status` | 秒 | 提交到终态总耗时（含 HITL 等待） | 长任务时延、容量 |
| `agent_task_steps` | Histogram | `status` | 步 | 单任务执行步数（LangGraph 节点数） | 步数异常增长 = 模型在打转 |
| `agent_llm_tokens_total` | Counter | `model`,`direction` | token | `direction` ∈ prompt/completion，取自 provider `usage` | Token 速率、上下文膨胀 |
| `agent_llm_cost_usd_total` | Counter | `model` | 美元 | 按官方定价表换算的累计成本 | 成本曲线、预算告警 |
| `agent_llm_calls_total` | Counter | `model`,`status` | 次 | 单次 LLM 调用结果 | 模型可用性、重试率 |
| `agent_llm_duration_seconds` | Histogram | `model` | 秒 | 单次调用耗时（含重试） | 模型变慢检测 |
| `agent_active_sessions` | Gauge | — | 个 | 有未过期 checkpoint 的 thread 数 | 容量、并发上限 |
| `agent_hitl_pending` | Gauge | `queue` | 个 | 待人工审核任务数（阶段 4 的 interrupt 挂起数） | 人工队列堆积 |
| `agent_hitl_oldest_wait_seconds` | Gauge | `queue` | 秒 | 最老待审核任务已等待时长 | 「没人处理」告警（比数量更准） |
| `agent_hitl_decisions_total` | Counter | `decision` | 次 | approved / rejected / timeout_rejected | 人工驳回率 |
| `agent_errors_total` | Counter | `type` | 次 | `type` ∈ llm_error/tool_error/validation_error/timeout/rate_limited/auth_error/internal_error（**与 02 篇错误分类一致**） | 错误分类 Top、错误率突增 |
| `agent_guardrail_blocks_total` | Counter | `reason` | 次 | prompt_injection / pii / rbac（对齐 [05 篇](05-Agent安全评测与加固.md)） | 安全拦截趋势 |
| `agent_last_success_timestamp_seconds` | Gauge | — | 秒 | 最后一次成功请求的 unix 时间戳（`set_to_current_time()`） | 「静默失败」检测 |

**所有 label 取值必须是封闭枚举**：异常消息、模型输出、prompt 片段一律进日志与 trace，指标只留分类。

### 3.6 完整指标模块

集中定义、全项目 import，避免重复注册与口径漂移：

```python
# app/metrics.py
"""Agent 指标定义中心。

纪律：① 所有指标只在这里定义一次；② label 取值必须来自封闭枚举；
③ 任何名字/label 变更都是破坏性变更，需同步更新 02 篇口径文档。
"""
from prometheus_client import Counter, Gauge, Histogram

# ---------- 请求层 ----------
REQUEST_STATUSES = ("success", "error", "timeout", "rate_limited", "client_error")
AGENT_REQUESTS = Counter(
    "agent_requests_total", "Agent HTTP 请求总数（endpoint 为路由模板）",
    ["endpoint", "status"])
AGENT_REQUEST_LATENCY = Histogram(
    "agent_request_duration_seconds", "Agent 请求端到端耗时（含工具与 LLM 调用）",
    ["endpoint"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 13.0, 21.0, 34.0, 60.0))
AGENT_IN_PROGRESS = Gauge(
    "agent_requests_in_progress", "正在处理中的请求数", ["endpoint"])
AGENT_LAST_SUCCESS = Gauge(
    "agent_last_success_timestamp_seconds", "最后一次成功请求的时间戳")

# ---------- 工具层 ----------
TOOL_RESULTS = ("success", "error", "timeout", "rejected", "invalid_args")
AGENT_TOOL_CALLS = Counter(
    "agent_tool_calls_total",
    "工具调用总数（result=success 为执行成功，对应 02 篇工具成功率分子）",
    ["tool", "result"])
AGENT_TOOL_LATENCY = Histogram(
    "agent_tool_duration_seconds", "工具执行耗时（不含模型决策时间）", ["tool"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0))

# ---------- 任务层 ----------
TASK_STATUSES = ("completed", "failed", "rejected_by_human", "cancelled")
AGENT_TASKS = Counter(
    "agent_tasks_total",
    "任务终态计数（完成率 = completed / 全部终态，对应 02 篇 Task Completion Rate）",
    ["status"])
AGENT_TASK_LATENCY = Histogram(
    "agent_task_duration_seconds", "任务提交到终态的总耗时（含 HITL 等待）",
    ["status"], buckets=(1, 5, 15, 30, 60, 120, 300, 900, 3600))
AGENT_TASK_STEPS = Histogram(
    "agent_task_steps", "任务执行步数（LangGraph 节点执行次数）", ["status"],
    buckets=(1, 2, 3, 5, 8, 13, 21, 34))

# ---------- LLM 层 ----------
AGENT_LLM_TOKENS = Counter(
    "agent_llm_tokens_total", "LLM token 消耗量（取自 provider usage）",
    ["model", "direction"])
AGENT_LLM_COST = Counter(
    "agent_llm_cost_usd_total", "LLM 累计成本（美元）", ["model"])
AGENT_LLM_CALLS = Counter("agent_llm_calls_total", "LLM 调用次数", ["model", "status"])
AGENT_LLM_LATENCY = Histogram(
    "agent_llm_duration_seconds", "单次 LLM 调用耗时（含重试）", ["model"],
    buckets=(0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0))

# ---------- 会话与 HITL ----------
AGENT_ACTIVE_SESSIONS = Gauge(
    "agent_active_sessions", "当前活跃会话数（有未过期 checkpoint 的 thread 数）")
AGENT_HITL_PENDING = Gauge(
    "agent_hitl_pending", "待人工审核任务数", ["queue"],
    multiprocess_mode="max")          # 各 worker 从 Redis 读到同一个值，取 max 避免被放大
AGENT_HITL_OLDEST_WAIT = Gauge(
    "agent_hitl_oldest_wait_seconds", "最老待审核任务已等待时长", ["queue"],
    multiprocess_mode="max")
AGENT_HITL_DECISIONS = Counter(
    "agent_hitl_decisions_total", "人工审核决策数", ["decision"])

# ---------- 错误与安全 ----------
ERROR_TYPES = ("llm_error", "tool_error", "validation_error", "timeout",
               "rate_limited", "auth_error", "internal_error")
AGENT_ERRORS = Counter(
    "agent_errors_total", "错误分类计数（type 口径与 02 篇评测错误分类一致）", ["type"])
AGENT_GUARDRAIL_BLOCKS = Counter(
    "agent_guardrail_blocks_total", "安全护栏拦截次数", ["reason"])
```

把「记录一次调用」收敛成薄封装，避免业务里散落 `inc()`：

```python
# app/instrument.py
import time
from contextlib import contextmanager
from .metrics import (AGENT_TOOL_CALLS, AGENT_TOOL_LATENCY, AGENT_ERRORS,
                      AGENT_LLM_TOKENS, AGENT_LLM_COST, AGENT_LLM_CALLS,
                      AGENT_LLM_LATENCY)

# 定价表：务必与财务口径一致，并定期核对官方定价页（示例值，以官方为准）
MODEL_PRICE_PER_1K = {
    "gpt-4o-mini":   {"prompt": 0.00015, "completion": 0.00060},
    "deepseek-chat": {"prompt": 0.00014, "completion": 0.00028},
}

@contextmanager
def track_tool(tool: str):
    """包住一次工具调用：成功/失败/异常都会记耗时与结果。"""
    start = time.perf_counter()
    result = "success"
    try:
        yield
    except TimeoutError:
        result = "timeout"
        AGENT_ERRORS.labels(type="timeout").inc()
        raise
    except ValueError:
        result = "invalid_args"
        AGENT_ERRORS.labels(type="validation_error").inc()
        raise
    except Exception:
        result = "error"
        AGENT_ERRORS.labels(type="tool_error").inc()
        raise
    finally:
        # ⚠️ 异常路径也要 observe，否则 P95 只统计成功请求，明显偏乐观（见 9.7）
        AGENT_TOOL_LATENCY.labels(tool=tool).observe(time.perf_counter() - start)
        AGENT_TOOL_CALLS.labels(tool=tool, result=result).inc()

def record_llm_usage(model: str, usage) -> None:
    """usage 来自 provider 响应（字段名以各家 SDK 为准）。"""
    p = getattr(usage, "prompt_tokens", 0) or 0
    c = getattr(usage, "completion_tokens", 0) or 0
    AGENT_LLM_TOKENS.labels(model=model, direction="prompt").inc(p)
    AGENT_LLM_TOKENS.labels(model=model, direction="completion").inc(c)
    price = MODEL_PRICE_PER_1K.get(model)
    if price:
        AGENT_LLM_COST.labels(model=model).inc(
            p / 1000 * price["prompt"] + c / 1000 * price["completion"])

@contextmanager
def track_llm_call(model: str):
    start = time.perf_counter()
    status = "success"
    try:
        yield
    except Exception:
        status = "error"
        AGENT_ERRORS.labels(type="llm_error").inc()
        raise
    finally:
        AGENT_LLM_LATENCY.labels(model=model).observe(time.perf_counter() - start)
        AGENT_LLM_CALLS.labels(model=model, status=status).inc()

# 用法：
#   with track_tool("k8s_query"): rows = k8s_query(namespace="prod")
#   with track_llm_call("deepseek-chat"):
#       resp = client.chat.completions.create(...)
#   record_llm_usage("deepseek-chat", resp.usage)
```

### 3.7 自动埋点：别在业务代码里到处插 `inc()`

上面的 `with` 已经比裸 `inc()` 好，但仍要求每个调用点都记得包一层。更可靠的做法是**在框架钩子上统一埋点**——与 [04 篇](04-OpenTelemetry与自定义Tracing.md) 同思路：**埋点位置由框架决定，而不是由业务作者决定**。

**路线 A：LangChain Callback Handler（管 LLM 与工具）**

```python
# app/callbacks.py
import time
from langchain_core.callbacks import BaseCallbackHandler
from .metrics import (AGENT_LLM_CALLS, AGENT_LLM_LATENCY, AGENT_LLM_TOKENS,
                      AGENT_LLM_COST, AGENT_TOOL_CALLS, AGENT_TOOL_LATENCY,
                      AGENT_ERRORS)
from .instrument import MODEL_PRICE_PER_1K

class PrometheusCallbackHandler(BaseCallbackHandler):
    """把 LangChain 的 LLM / 工具事件翻译成 Prometheus 指标。
    钩子名称与字段以官方文档为准（1.x 仍在演进）：
    关键是 on_*_start 用 run_id 记起始时间，on_*_end / on_*_error 结算。"""

    def __init__(self) -> None:
        self._llm: dict[str, float] = {}
        self._tool: dict[str, float] = {}

    def on_llm_start(self, serialized, prompts, *, run_id, **kwargs) -> None:
        self._llm[str(run_id)] = time.perf_counter()

    def on_llm_end(self, response, *, run_id, **kwargs) -> None:
        start = self._llm.pop(str(run_id), None)
        model = "unknown"
        try:
            model = response.llm_output.get("model_name") or "unknown"
        except Exception:
            pass
        if start is not None:
            AGENT_LLM_LATENCY.labels(model=model).observe(time.perf_counter() - start)
        AGENT_LLM_CALLS.labels(model=model, status="success").inc()
        try:  # token usage 字段路径以官方文档为准
            tu = response.llm_output.get("token_usage") or {}
            p, c = int(tu.get("prompt_tokens", 0)), int(tu.get("completion_tokens", 0))
            AGENT_LLM_TOKENS.labels(model=model, direction="prompt").inc(p)
            AGENT_LLM_TOKENS.labels(model=model, direction="completion").inc(c)
            price = MODEL_PRICE_PER_1K.get(model)
            if price:
                AGENT_LLM_COST.labels(model=model).inc(
                    p / 1000 * price["prompt"] + c / 1000 * price["completion"])
        except Exception:
            pass

    def on_llm_error(self, error, *, run_id, **kwargs) -> None:
        self._llm.pop(str(run_id), None)
        AGENT_LLM_CALLS.labels(model="unknown", status="error").inc()
        AGENT_ERRORS.labels(type="llm_error").inc()

    def on_tool_start(self, serialized, input_str, *, run_id, **kwargs) -> None:
        self._tool[str(run_id)] = time.perf_counter()

    def on_tool_end(self, output, *, run_id, **kwargs) -> None:
        start = self._tool.pop(str(run_id), None)
        tool = kwargs.get("name", "unknown")
        if start is not None:
            AGENT_TOOL_LATENCY.labels(tool=tool).observe(time.perf_counter() - start)
        AGENT_TOOL_CALLS.labels(tool=tool, result="success").inc()

    def on_tool_error(self, error, *, run_id, **kwargs) -> None:
        self._tool.pop(str(run_id), None)
        tool = kwargs.get("name", "unknown")
        result = "timeout" if isinstance(error, TimeoutError) else "error"
        AGENT_TOOL_CALLS.labels(tool=tool, result=result).inc()
        AGENT_ERRORS.labels(
            type="timeout" if result == "timeout" else "tool_error").inc()

# 使用：业务代码只加一行 config
#   result = await agent.ainvoke(state,
#       config={"configurable": {"thread_id": task_id}, "callbacks": [handler]})
```

**路线 B：LangGraph 节点钩子（管任务级指标）**

任务终态、步数、HITL 挂起是**图级**概念，callback 看不到，必须单独做：

```python
# app/graph_instrument.py
import time
from .metrics import (AGENT_TASKS, AGENT_TASK_LATENCY, AGENT_TASK_STEPS,
                      AGENT_HITL_PENDING, AGENT_ACTIVE_SESSIONS)

_STEPS: dict[str, int] = {}          # 进程内计数；多进程场景换成 Redis 计数器

def on_task_submit(task_id: str) -> None:
    _STEPS[task_id] = 0
    AGENT_ACTIVE_SESSIONS.inc()

def on_node_executed(task_id: str) -> None:
    _STEPS[task_id] = _STEPS.get(task_id, 0) + 1

def on_task_finish(task_id: str, *, status: str, started_at: float) -> None:
    """status ∈ completed / failed / rejected_by_human / cancelled"""
    AGENT_TASK_STEPS.labels(status=status).observe(_STEPS.pop(task_id, 0))
    AGENT_TASK_LATENCY.labels(status=status).observe(time.perf_counter() - started_at)
    AGENT_TASKS.labels(status=status).inc()
    AGENT_ACTIVE_SESSIONS.dec()

def on_hitl_interrupt(task_id: str, *, queue: str = "approval") -> None:
    AGENT_HITL_PENDING.labels(queue=queue).inc()      # 图在 interrupt 处挂起

def on_hitl_resolved(task_id: str, *, decision: str, queue: str = "approval") -> None:
    AGENT_HITL_PENDING.labels(queue=queue).dec()
```

**路线 C：OTel SpanProcessor（推荐，统一收口）**

[04 篇](04-OpenTelemetry与自定义Tracing.md) 已经给 Agent 加了 OTel tracing。**同一份 span 数据可以直接算出指标**，于是你只维护一套埋点：trace 给调试，metrics 给监控，口径天然一致。

```python
# app/otel_metrics_processor.py
from opentelemetry.sdk.trace import SpanProcessor
from .metrics import (AGENT_TOOL_CALLS, AGENT_TOOL_LATENCY, AGENT_LLM_LATENCY,
                      AGENT_REQUESTS, AGENT_REQUEST_LATENCY)

class MetricsSpanProcessor(SpanProcessor):
    """on_end 里按 span 名称与属性结算指标（span 命名约定见 04 篇）。"""

    def on_start(self, span, parent_context=None): pass

    def on_end(self, span) -> None:
        name, attrs = span.name, dict(span.attributes or {})
        duration_s = (span.end_time - span.start_time) / 1e9   # 纳秒 -> 秒
        ok = span.status.status_code.name != "ERROR"

        if name.startswith("tool."):                 # tool.<tool_name>
            tool = attrs.get("tool.name") or name.removeprefix("tool.")
            AGENT_TOOL_LATENCY.labels(tool=tool).observe(duration_s)
            AGENT_TOOL_CALLS.labels(tool=tool,
                                    result="success" if ok else "error").inc()
        elif name.startswith("llm."):
            AGENT_LLM_LATENCY.labels(model=attrs.get("llm.model") or "unknown") \
                .observe(duration_s)
        elif name.startswith(("http.", "agent.request")):
            ep = attrs.get("http.route") or attrs.get("endpoint") or "unknown"
            AGENT_REQUEST_LATENCY.labels(endpoint=ep).observe(duration_s)
            AGENT_REQUESTS.labels(endpoint=ep,
                                  status="success" if ok else "error").inc()

    def shutdown(self) -> None: pass
    def force_flush(self, timeout_millis: int = 30000) -> bool: return True

# 注册：provider.add_span_processor(MetricsSpanProcessor())
```

| 路线 | 覆盖范围 | 侵入性 | 推荐度 |
| --- | --- | --- | --- |
| A. LangChain callback | LLM、工具 | 低（一行 config） | 不想动 OTel 时用 |
| B. LangGraph 节点钩子 | 任务级（终态、步数、HITL） | 中（改图入口出口） | **必须做**（A/C 都覆盖不到任务语义） |
| C. OTel SpanProcessor | 全部（复用 04 篇埋点） | 低（一次注册） | **首选**，口径与 trace 天然一致 |

实务建议：**A/C 二选一 + B 必做**。通用埋点框架不会替你决定「什么算任务完成」。

## 四、PromQL 常用查询

### 4.1 五个必须先掌握的语法点

```promql
# 1) 时间序列选择器：支持 = / != / =~ / !~
agent_requests_total{endpoint="/chat", status!="success"}
# 2) 区间向量 [窗口]：给 rate 用；窗口内至少要有 2 个采样点
agent_requests_total{endpoint="/chat"}[5m]
# 3) 函数：rate 求每秒平均增长率（只对 Counter），increase 求窗口内增量
rate(agent_requests_total[5m])
# 4) 聚合：sum / avg / max / count / topk / quantile，配 by / without
sum by (endpoint) (rate(agent_requests_total[5m]))
# 5) 二元运算：向量按 label 精确匹配
sum(rate(A[5m])) / sum(rate(B[5m]))
```

三个语法坑：`rate()` 只能用于 **Counter**（Gauge 用 `delta()` / `avg_over_time()`）；窗口**至少是抓取间隔的 4 倍**（否则经常返回空）；二元运算要「先聚合再相除」，写成 `sum(A/B)` 会因 label 不匹配得到空值。

### 4.2 十二类查询示例（可直接粘贴）

```promql
# ① 流量：每秒请求数
sum by (endpoint) (rate(agent_requests_total[5m]))

# ② 成功率（两种口径都要会写）
# 口径 A（推荐，对外 SLO）：client_error / rate_limited 也算"不成功"
sum(rate(agent_requests_total{status="success"}[5m]))
  / sum(rate(agent_requests_total[5m]))
# 口径 B（内部技术 SLO）：只统计服务端责任的失败，避免被爬虫污染
sum(rate(agent_requests_total{status="success"}[5m]))
  / sum(rate(agent_requests_total{status=~"success|error|timeout"}[5m]))

# ③ 错误率与错误分类构成
sum(rate(agent_requests_total{status=~"error|timeout"}[5m]))
  / sum(rate(agent_requests_total[5m]))
sum by (type) (rate(agent_errors_total[5m]))

# ④ P95（全局）
histogram_quantile(0.95, sum by (le) (rate(agent_request_duration_seconds_bucket[5m])))
# ⑤ P99 按 endpoint 拆分（by 里必须同时有 le）
histogram_quantile(0.99,
  sum by (le, endpoint) (rate(agent_request_duration_seconds_bucket[5m])))

# ⑥ 平均延迟：用 _sum / _count，不要用 avg()
sum by (endpoint) (rate(agent_request_duration_seconds_sum[5m]))
  / sum by (endpoint) (rate(agent_request_duration_seconds_count[5m]))

# ⑦ "8 秒内完成率"——把 P95 < 8s 写成直接 SLI（前提：8.0 是桶边界）
sum(rate(agent_request_duration_seconds_bucket{le="8.0"}[5m]))
  / sum(rate(agent_request_duration_seconds_count[5m]))

# ⑧ 工具成功率：全局 + 按工具
sum(rate(agent_tool_calls_total{result="success"}[10m]))
  / sum(rate(agent_tool_calls_total[10m]))
sum by (tool) (rate(agent_tool_calls_total{result="success"}[10m]))
  / sum by (tool) (rate(agent_tool_calls_total[10m]))

# ⑨ 工具失败 Top 5（1 小时增量，每日巡检用）
topk(5, sum by (tool) (increase(agent_tool_calls_total{result!="success"}[1h])))

# ⑩ 任务完成率与终态构成
sum(increase(agent_tasks_total{status="completed"}[1h])) / sum(increase(agent_tasks_total[1h]))
sum by (status) (rate(agent_tasks_total[30m]))

# ⑪ Token 与成本
sum by (model, direction) (rate(agent_llm_tokens_total[5m]))
sum by (model) (rate(agent_llm_cost_usd_total[5m])) * 3600      # 美元/小时
sum(increase(agent_llm_cost_usd_total[24h]))                    # 当日累计
sum(increase(agent_llm_cost_usd_total[24h]))
  / sum(increase(agent_llm_cost_usd_total[24h] offset 24h))     # 日环比
sum(rate(agent_llm_cost_usd_total[1h]))
  / sum(rate(agent_tasks_total{status="completed"}[1h]))        # 单任务平均成本

# ⑫ 会话、HITL、容量与自身健康
sum(agent_active_sessions)
sum by (queue) (agent_hitl_pending)
max by (queue) (agent_hitl_oldest_wait_seconds)                 # 比"数量"更准
sum(rate(agent_hitl_decisions_total{decision=~"rejected|timeout_rejected"}[1h]))
  / sum(rate(agent_hitl_decisions_total[1h]))                   # 人工驳回率
sum(rate(agent_requests_total{status="rate_limited"}[5m]))
  / sum(rate(agent_requests_total[5m]))                         # 限流拒绝率
time() - agent_last_success_timestamp_seconds                   # 静默失败
up{job="agent"}                                                 # 抓取健康
sum(rate(agent_task_steps_sum[1h])) / sum(rate(agent_task_steps_count[1h]))  # 平均步数
```

| 看板显示 | 查询锚点 | 口径要点 |
| --- | --- | --- |
| 成功率 | `status="success"` / 全部 | 是否把 `client_error` 计入失败要在看板标注 |
| 错误率 | `status=~"error\|timeout"` / 全部 | 与 [02 篇](02-评测指标详解与实现.md)「错误率」定义一致 |
| P95 延迟 | `histogram_quantile(0.95, sum by (le) (rate(_bucket[5m])))` | 窗口与告警 `for` 时长同量级 |
| 平均延迟 | `rate(_sum)/rate(_count)` | **不要**用 `avg()` / `avg_over_time()` |
| 工具成功率 | `agent_tool_calls_total{result="success"}` / 全部 | 分母是工具调用次数，不是请求数 |
| 任务完成率 | `agent_tasks_total{status="completed"}` / 全部终态 | 分母**只含终态**，不含进行中 |
| 成本 | `increase(agent_llm_cost_usd_total[24h])` | 定价表变更会产生台阶，需 Annotation |
| HITL | `agent_hitl_pending` + `agent_hitl_oldest_wait_seconds` | 只看数量会漏「1 个卡了 3 天」 |

### 4.3 Recording Rules：别让看板反复重算

上面 ②④⑥⑧⑩ 会在每个面板每次刷新时重算，多面板看板一开就是几十条重查询。生产做法是固化成**记录规则（recording rules）**，命名约定 `level:metric:operations`（冒号是记录规则专用分隔符）：

```yaml
# prometheus/rules/recording.yml
groups:
  - name: agent-recording
    interval: 30s
    rules:
      - record: agent:request_success_rate:5m
        expr: |
          sum(rate(agent_requests_total{status="success"}[5m]))
            / sum(rate(agent_requests_total[5m]))
      - record: agent:request_latency_p95:5m
        expr: |
          histogram_quantile(0.95, sum by (le) (rate(agent_request_duration_seconds_bucket[5m])))
      - record: agent:tool_success_rate:10m
        expr: |
          sum(rate(agent_tool_calls_total{result="success"}[10m]))
            / sum(rate(agent_tool_calls_total[10m]))
```

## 五、本地起一套监控栈

### 5.1 目录结构

```text
agent-monitoring/
├── docker-compose.yml
├── app/{Dockerfile,main.py,metrics.py,instrument.py}    # 你的 Agent 服务（阶段 3/4 项目）
├── prometheus/
│   ├── prometheus.yml
│   └── rules/{recording.yml,alerts.yml}
├── alertmanager/alertmanager.yml
└── grafana/provisioning/
    ├── datasources/prometheus.yml
    └── dashboards/dashboards.yml
```

### 5.2 Prometheus 配置

```yaml
# prometheus/prometheus.yml
global:
  scrape_interval: 15s          # 与告警 for 时长的匹配关系见 9.4
  scrape_timeout: 10s           # 必须 < scrape_interval
  evaluation_interval: 15s      # 评估告警/记录规则的间隔
  external_labels: {env: local, cluster: dev}

rule_files:
  - /etc/prometheus/rules/*.yml

alerting:
  alertmanagers:
    - static_configs:
        - targets: ["alertmanager:9093"]

scrape_configs:
  - job_name: prometheus          # 自我监控（up / scrape_duration_seconds 等）
    static_configs: [{targets: ["localhost:9090"]}]

  - job_name: agent
    metrics_path: /metrics
    scrape_interval: 15s
    static_configs:
      - targets: ["agent:8000"]
        labels: {service: agent, component: api}

  # 生产替换为服务发现，例如 K8s：
  # - job_name: agent-k8s
  #   kubernetes_sd_configs: [{role: pod}]
  #   relabel_configs:
  #     - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
  #       action: keep
  #       regex: "true"
```

### 5.3 Docker Compose 编排

```yaml
# docker-compose.yml
# 镜像 tag 请固定为官方 Docker Hub 上的具体版本（这里用 latest 仅为演示）
name: agent-monitoring

services:
  agent:
    build: {context: ./app, dockerfile: Dockerfile}
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
    environment:
      # 若用多 worker（--workers 4），必须打开下一行并配合 3.4 的多进程模式
      # - PROMETHEUS_MULTIPROC_DIR=/tmp/prom_multiproc
      - LOG_LEVEL=INFO
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317   # 04 篇
    ports: ["8000:8000"]           # 只为本机调试；生产不要对外
    healthcheck:
      test: ["CMD", "python", "-c",
             "import urllib.request;urllib.request.urlopen('http://localhost:8000/healthz')"]
      interval: 10s
      timeout: 3s
      retries: 5
    networks: [monitoring]

  prometheus:
    image: prom/prometheus:latest
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.path=/prometheus
      - --storage.tsdb.retention.time=15d
      - --web.enable-lifecycle          # 支持热加载：curl -X POST /-/reload
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./prometheus/rules:/etc/prometheus/rules:ro
      - prometheus-data:/prometheus
    ports: ["9090:9090"]
    networks: [monitoring]

  alertmanager:
    image: prom/alertmanager:latest
    command: --config.file=/etc/alertmanager/alertmanager.yml
    volumes:
      - ./alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
      - alertmanager-data:/alertmanager
    ports: ["9093:9093"]
    networks: [monitoring]

  grafana:
    image: grafana/grafana:latest
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=admin     # 生产必须改，或用 secret 注入
      - GF_USERS_ALLOW_SIGN_UP=false
    volumes:
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
      - grafana-data:/var/lib/grafana
    ports: ["3000:3000"]
    depends_on: [prometheus]
    networks: [monitoring]

networks: {monitoring: {driver: bridge}}
volumes: {prometheus-data: {}, grafana-data: {}, alertmanager-data: {}}
```

```yaml
# grafana/provisioning/datasources/prometheus.yml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false
    jsonData:
      timeInterval: 15s      # 与 scrape_interval 一致；决定 $__rate_interval 的取值
      httpMethod: POST
---
# grafana/provisioning/dashboards/dashboards.yml
apiVersion: 1
providers:
  - name: agent-dashboards
    orgId: 1
    folder: "Agent"
    type: file
    updateIntervalSeconds: 30
    options: {path: /etc/grafana/provisioning/dashboards}
```

（Grafana provisioning 的目录结构与字段以官方文档为准。）

### 5.4 端到端验证步骤

```bash
# 0) 起栈
docker compose up -d --build && docker compose ps    # 容器都应 running/healthy

# 1) 确认 Agent 自己暴露指标（不依赖任何监控组件）
curl -s localhost:8000/metrics | head -40
#    ✅ 有 "# HELP agent_requests_total" 与 "_bucket{le=...}" 就对了
#    ❌ 404 -> /metrics 路由没注册；❌ 空 -> 指标模块没被 import

# 2) 造流量（没流量指标全 0，什么都验证不了；最好人为注入失败）
for i in $(seq 1 30); do curl -s -X POST localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"查一下 prod 命名空间异常的 pod"}' > /dev/null; done
curl -s localhost:8000/metrics | grep '^agent_requests_total'

# 3) 确认 Prometheus 抓到了
open http://localhost:9090/targets
#    ✅ job "agent" State=UP, Last Scrape 几秒前
#    ❌ DOWN: "connection refused" -> 容器名/端口/network 写错
#             "context deadline exceeded" -> /metrics 太慢（说明你在里面查了 DB！）
#             404 -> metrics_path 写错

# 4) 在 Prometheus 里跑查询
open 'http://localhost:9090/graph?g0.expr=sum(rate(agent_requests_total%5B5m%5D))'
#    逐条试 4.2 的查询；空结果多为"窗口太小"或"label 值写错"

# 5) 确认规则加载成功
open http://localhost:9090/rules
#    ❌ 规则没生效：确认 rule_files 路径与 volume 挂载路径一致（容器内路径！）
#    ❌ 语法错误：docker compose logs prometheus | grep -i error

# 6) Grafana 建面板
open http://localhost:3000     # admin/admin
#    Configuration -> Data sources 应有 Prometheus（provisioning 生效）
#    Explore -> 选数据源 -> 粘 4.2 的查询 -> Run query -> Add to dashboard
```

验证告警真的会响（练习 2 会用到）：打 50 次失败请求 → 等 `for` 时长 → `http://localhost:9090/alerts` 看 `Pending → Firing` → `http://localhost:9093` 看 Alertmanager 分组。

## 六、Grafana 看板设计

### 6.1 三个分区

按**阅读者的提问顺序**分三行，不要把所有图堆一页：

```text
【服务健康（30 秒判断能不能下班）】① QPS  ② 成功率/错误率  ③ P95/P99  ④ 任务完成率  ⑤ 告警数
【成本与容量（每天看一眼）】      ⑥ 成本曲线  ⑦ Token 速率  ⑧ 单任务平均成本  ⑨ 活跃会话
【故障定位（出问题才看）】        ⑩ 工具失败 Top 5  ⑪ 工具成功率  ⑫ 错误分类  ⑬ HITL 队列  ⑭ 限流拒绝率
```

### 6.2 面板清单（查询与配置）

| # | 面板标题 | 类型 | PromQL | 单位 | 阈值/颜色 |
| --- | --- | --- | --- | --- | --- |
| ① | 请求速率 QPS | Time series | `sum by (endpoint) (rate(agent_requests_total{endpoint=~"$endpoint"}[$__rate_interval]))` | reqps | — |
| ② | 成功率 | Stat + Time series | `sum(rate(agent_requests_total{status="success"}[$__rate_interval])) / sum(rate(agent_requests_total[$__rate_interval]))` | percent (0-1) | 绿 ≥0.95 / 黄 ≥0.90 / 红 <0.90 |
| ③ | 错误率（按类型） | Time series 堆叠 | `sum by (type) (rate(agent_errors_total[$__rate_interval]))` | reqps | 红系调色板 |
| ④ | P50/P95/P99 延迟 | Time series | `histogram_quantile(0.95, sum by (le) (rate(agent_request_duration_seconds_bucket{endpoint=~"$endpoint"}[$__rate_interval])))`（另两条改 0.5/0.99） | seconds (s) | P95 红线 8s |
| ⑤ | 任务完成率 | Stat | `sum(increase(agent_tasks_total{status="completed"}[1h])) / sum(increase(agent_tasks_total[1h]))` | percent (0-1) | 绿 ≥0.90 / 黄 ≥0.85 / 红 <0.85 |
| ⑥ | 成本速率 | Time series 柱 | `sum by (model) (rate(agent_llm_cost_usd_total{model=~"$model"}[$__rate_interval])) * 3600` | currencyUSD | 黄 20 / 红 50（$/h） |
| ⑦ | 当日累计成本 | Stat | `sum(increase(agent_llm_cost_usd_total[24h]))` | currencyUSD | 红 > 预算 |
| ⑧ | 单任务平均成本 | Time series | `sum(rate(agent_llm_cost_usd_total[$__rate_interval])) / sum(rate(agent_tasks_total{status="completed"}[$__rate_interval]))` | currencyUSD | — |
| ⑨ | Token 速率 | Time series 堆叠 | `sum by (direction) (rate(agent_llm_tokens_total{model=~"$model"}[$__rate_interval]))` | 自定义 `tok/s` | — |
| ⑩ | 工具失败 Top 5 | Bar chart | `topk(5, sum by (tool) (increase(agent_tool_calls_total{tool=~"$tool", result!="success"}[$__range])))` | short | 红 |
| ⑪ | 工具成功率（按工具） | Bar gauge | `sum by (tool) (rate(agent_tool_calls_total{result="success"}[$__rate_interval])) / sum by (tool) (rate(agent_tool_calls_total[$__rate_interval]))` | percent (0-1) | 0.95 阈值，低于变红 |
| ⑫ | 工具调用构成 | Pie chart | `sum by (result) (increase(agent_tool_calls_total{tool=~"$tool"}[$__range]))` | short | — |
| ⑬ | HITL 队列 | Stat + Time series | `sum by (queue) (agent_hitl_pending)` 与 `max by (queue) (agent_hitl_oldest_wait_seconds)` | short / seconds | 数量 >10 黄；最老等待 >1800s 红 |
| ⑭ | 限流拒绝率 | Stat | `sum(rate(agent_requests_total{status="rate_limited"}[$__rate_interval])) / sum(rate(agent_requests_total[$__rate_interval]))` | percent (0-1) | 黄 0.01 / 红 0.05 |
| ⑮ | 抓取健康 | Stat | `min(up{job="agent"})` | short | 1 绿 / 0 红 |

**面板类型选择**：随时间变化用 Time series（只看 Stat 会丢趋势）；「现在是多少」且需阈值用 Stat（Gauge 占空间大、信息密度低）；维度对比（哪些工具最差）用 Bar gauge/Bar chart；构成占比（≤6 类）用 Pie 或堆叠 Time series。

### 6.3 变量（Template Variables）

在 Dashboard settings → Variables 添加：

| 变量名 | Query | 多选 | 默认 |
| --- | --- | --- | --- |
| `endpoint` | `label_values(agent_requests_total, endpoint)` | 是（含 All） | All |
| `tool` | `label_values(agent_tool_calls_total, tool)` | 是（含 All） | All |
| `model` | `label_values(agent_llm_tokens_total, model)` | 是（含 All） | All |
| `env` | `label_values(up{job="agent"}, env)` | 否 | local |

三个要点：① 查询里用 `=~"$tool"`（正则）而非 `="$tool"`，多选与 `All` 才能工作（All 展开为 `.*`）；② **`$__rate_interval` 优于手写 `[5m]`**——Grafana 会按面板时间范围与 `scrape_interval` 自动算出「至少 4 个采样点」的窗口，避免拉到 7 天时曲线全是锯齿；③ 整个时间范围的聚合用 `$__range`（如 ⑩ 的 Top 5），让「看最近 6 小时」时 Top N 也按 6 小时统计。（变量语法与内置变量清单以官方文档为准。）

### 6.4 单位、阈值与颜色规范

| 项 | 规范 | 理由 |
| --- | --- | --- |
| 延迟 | `seconds (s)` | 后端存基本单位秒，**展示层**再换算 ms |
| 速率 | `reqps` | Grafana 内置，自适应 K/M 前缀 |
| 比率 | `percent (0-1)` | 查询返回 0.95，展示 95%，避免「0.95%」的误解 |
| 成本 | `currencyUSD` | 有货币符号，不与 Token 数混淆 |
| Token 速率 | 自定义 `tok/s` | Grafana 无内置 |
| 阈值配色 | 绿=正常 / 黄=接近 SLO / 红=已破 SLO | **必须与告警规则一致**：看板绿、告警红会摧毁值班人的信任 |
| 颜色语义 | 错误一律红、成功一律绿、延迟一律橙 | 全站统一 |

## 七、告警规则与通知

### 7.1 告警分级

第一原则：**每条告警都必须有一个「收到后要做的动作」**。没有动作的告警是噪音。

| 级别 | 定义 | 通知方式 | 响应要求 | 示例 |
| --- | --- | --- | --- | --- |
| **P1** | 用户正在受影响，SLO 快速被烧 | 电话/短信/群 @所有人 | 立即（5 分钟内） | 成功率 <90% 持续 5m；服务不可达 |
| **P2** | 用户受影响但未破 SLO，或趋势危险 | 工单 + 群消息（不 @） | 当天工作时间内 | P95 > 8s 持续 15m；HITL 积压 |
| **P3** | 需关注，无人直接受损 | 只进看板 / 每日摘要 | 每周巡检 | 单任务成本缓慢上升 |

### 7.2 告警规则文件

```yaml
# prometheus/rules/alerts.yml
groups:
  # ================= SLO 类 =================
  - name: agent-slo
    interval: 30s
    rules:
      - alert: AgentSuccessRateLow
        # for: 5m —— 成功率的分子分母都在变，瞬时抖动常见；
        # 5m ≈ 20 个抓取点，能滤掉单次抖动又不漏真实故障
        expr: |
          (sum(rate(agent_requests_total{status="success"}[5m]))
             / sum(rate(agent_requests_total[5m]))) < 0.90
        for: 5m
        labels: {severity: P1, slo: request_success_rate, team: agent-platform}
        annotations:
          summary: "Agent 成功率 {{ $value | humanizePercentage }} 低于 90%（持续 5 分钟）"
          description: "先看是否伴随 AgentLatencyP95High 或工具失败告警，再查 Grafana「工具失败 Top 5」定位下游。"
          runbook_url: "https://your-wiki.example.com/runbook/agent-success-rate"

      - alert: AgentSuccessRateBelowSLO
        expr: |
          (sum(rate(agent_requests_total{status="success"}[15m]))
             / sum(rate(agent_requests_total[15m]))) < 0.95
        for: 15m
        labels: {severity: P2, slo: request_success_rate}
        annotations:
          summary: "Agent 成功率 {{ $value | humanizePercentage }} 低于 SLO 95%"
          description: "尚未影响可用性，但正在消耗错误预算。检查最近发布（看 Grafana Annotation）或下游限流。"

      - alert: AgentErrorRateSpike
        # 用"相比 1 小时前的倍数"而非绝对阈值：低流量下绝对值噪声大；
        # 并要求错误绝对量 > 0.1 rps，避免 1->3 这种小样本触发
        expr: |
          (sum(rate(agent_requests_total{status=~"error|timeout"}[5m]))
             / sum(rate(agent_requests_total[5m])))
          > 3 * (sum(rate(agent_requests_total{status=~"error|timeout"}[5m] offset 1h))
             / sum(rate(agent_requests_total[5m] offset 1h)))
          and sum(rate(agent_requests_total{status=~"error|timeout"}[5m])) > 0.1
        for: 5m
        labels: {severity: P1, slo: error_rate}
        annotations:
          summary: "Agent 错误率相比 1 小时前激增 3 倍以上（当前 {{ $value | humanizePercentage }}）"
          description: "优先排查最近一次发布与下游依赖（LLM provider / 内部 API）。"

      - alert: AgentLatencyP95High
        # for: 15m —— 延迟天然重尾，5m 窗口会周期性抖动；15m 才能确认"持续变慢"
        expr: |
          histogram_quantile(0.95,
            sum by (le) (rate(agent_request_duration_seconds_bucket[5m]))) > 8
        for: 15m
        labels: {severity: P2, slo: latency_p95}
        annotations:
          summary: "Agent P95 延迟 {{ $value }}s 超过 SLO 阈值 8s"
          description: "先看 P50/P95/P99 面板判断是整体变慢还是长尾变慢，再看工具 P95 面板定位工具。整体变慢通常是 LLM provider 侧问题。"

  # ================= 工具与业务类 =================
  - name: agent-tools
    rules:
      - alert: AgentToolSuccessRateLow
        # for: 10m —— 工具成功率的日间波动比请求成功率大（下游抖动），
        # 给 10m 让"重试后成功"的正常波动不被误报
        expr: |
          (sum(rate(agent_tool_calls_total{result="success"}[10m]))
             / sum(rate(agent_tool_calls_total[10m]))) < 0.95
        for: 10m
        labels: {severity: P1, slo: tool_success_rate}
        annotations:
          summary: "工具成功率 {{ $value | humanizePercentage }} 低于 SLO 95%"
          description: "用「工具成功率（按工具）」面板定位是哪一个工具。"

      - alert: AgentToolFailing
        # 单工具维度，比整体成功率更早发现问题；加样本量门槛避免小样本误报
        expr: |
          (sum by (tool) (rate(agent_tool_calls_total{result="success"}[10m]))
             / sum by (tool) (rate(agent_tool_calls_total[10m]))) < 0.5
          and sum by (tool) (rate(agent_tool_calls_total[10m])) > 0.02
        for: 10m
        labels: {severity: P1, slo: tool_success_rate}
        annotations:
          summary: "工具 {{ $labels.tool }} 成功率仅 {{ $value | humanizePercentage }}"
          description: "该工具可能已不可用（凭证过期 / 接口变更 / 权限收回）。检查其健康检查与最近变更。"

      - alert: AgentTaskCompletionRateLow
        expr: |
          (sum(increase(agent_tasks_total{status="completed"}[1h]))
             / sum(increase(agent_tasks_total[1h]))) < 0.85
        for: 30m
        labels: {severity: P2, slo: task_completion_rate}
        annotations:
          summary: "任务完成率 {{ $value | humanizePercentage }} 低于 85%（1 小时窗口）"
          description: "看终态构成：failed 多 -> 技术问题；rejected_by_human 多 -> 模型质量或 Safety 策略问题。"

      - alert: AgentHumanRejectionRateHigh
        expr: |
          (sum(rate(agent_hitl_decisions_total{decision=~"rejected|timeout_rejected"}[1h]))
             / sum(rate(agent_hitl_decisions_total[1h]))) > 0.30
        for: 30m
        labels: {severity: P2}
        annotations:
          summary: "人工驳回率 {{ $value | humanizePercentage }} 超过 30%"
          description: "模型产出质量下降。若离线评测没降，说明线上输入分布变了（新场景/新数据源）。"

  # ================= HITL 与容量类 =================
  - name: agent-hitl
    rules:
      - alert: AgentHitlQueueBacklog
        # for: 10m —— 人工队列有"上班才处理"的节律，10m 能滤掉午休/夜间的正常积压
        expr: sum by (queue) (agent_hitl_pending) > 10
        for: 10m
        labels: {severity: P2}
        annotations:
          summary: "队列 {{ $labels.queue }} 有 {{ $value }} 个任务待人工审核"
          description: "确认审核人是否在线；长期积压考虑提高自动通过比例或增加审核人。"

      - alert: AgentHitlOldestWaitTooLong
        # 比"数量"更重要：1 个卡了 2 小时的任务，体验比 10 个刚提交的差得多
        expr: max by (queue) (agent_hitl_oldest_wait_seconds) > 1800
        for: 5m
        labels: {severity: P1}
        annotations:
          summary: "队列 {{ $labels.queue }} 最老任务已等待 {{ $value | humanizeDuration }}"
          description: "检查通知是否送达审核人（钉钉/邮件），以及审批系统是否故障。"

      - alert: AgentRateLimitRejectionHigh
        expr: |
          (sum(rate(agent_requests_total{status="rate_limited"}[5m]))
             / sum(rate(agent_requests_total[5m]))) > 0.05
        for: 10m
        labels: {severity: P2}
        annotations:
          summary: "限流拒绝率 {{ $value | humanizePercentage }}，可能客户端重试风暴或容量不足"
          description: "看 Top 客户端来源；单一来源多为重试风暴（阶段 3 的重试纪律），普遍则需扩容。"

  # ================= 成本类 =================
  - name: agent-cost
    rules:
      - alert: AgentCostDayOverDayHigh
        # for: 30m —— 成本是慢变量，不需快速响应；环比倍数是最灵敏的异常消耗信号；
        # 加"绝对额 > 10 美元"避免低基数（0.5 -> 2）误报
        expr: |
          (sum(increase(agent_llm_cost_usd_total[24h]))
             / sum(increase(agent_llm_cost_usd_total[24h] offset 24h))) > 2
          and sum(increase(agent_llm_cost_usd_total[24h])) > 10
        for: 30m
        labels: {severity: P2}
        annotations:
          summary: "Agent 当日成本 {{ $value }} 倍于昨日"
          description: "三个常见原因：① prompt 变长（看 Token 速率）；② 步数变多（模型打转）；③ 异常调用方在刷。"

      - alert: AgentCostPerTaskRising
        expr: |
          (sum(rate(agent_llm_cost_usd_total[1h]))
             / sum(rate(agent_tasks_total{status="completed"}[1h])))
          > 1.5 * (sum(rate(agent_llm_cost_usd_total[1h] offset 24h))
             / sum(rate(agent_tasks_total{status="completed"}[1h] offset 24h)))
        for: 1h
        labels: {severity: P3}
        annotations:
          summary: "单任务平均成本相比昨天上升超过 50%"
          description: "通常是 prompt 或工具结果变长、或模型换成了更贵的。对照 02 篇：成本上升是否换来了质量提升。"

  # ================= 自身健康 =================
  - name: agent-availability
    rules:
      - alert: AgentMetricsUnreachable
        expr: up{job="agent"} == 0            # for: 2m = 连续 8 次抓取失败，排除网络抖动
        for: 2m
        labels: {severity: P1, slo: availability}
        annotations:
          summary: "Prometheus 无法抓取 Agent 指标（{{ $labels.instance }}）"
          description: "服务可能已宕机、端口不通或 /metrics 报错。注意本告警依赖 Prometheus 活着，需另配外部黑盒探测。"

      - alert: AgentNoSuccessfulRequest
        expr: time() - agent_last_success_timestamp_seconds > 600
        for: 2m
        labels: {severity: P1, slo: availability}
        annotations:
          summary: "Agent 已超过 10 分钟没有任何成功请求"
          description: "可能全部请求都在失败（成功率告警因流量为 0 而未触发）。检查依赖与最近发布。"

      - alert: AgentRuleEvaluationFailing
        expr: increase(prometheus_rule_evaluation_failures_total[10m]) > 0
        for: 0m
        labels: {severity: P1}
        annotations:
          summary: "有告警/记录规则评估失败，监控可能已失明"
```

### 7.3 `for` 时长怎么选

`for` = 「表达式连续为真多久才真正触发」，是抑制误报的第一道闸门。

| 信号类型 | 建议 `for` | 理由 |
| --- | --- | --- |
| 瞬时状态（不可达、进程消失） | `0m`~`2m` | 二值状态不需观察期，但至少覆盖 2~8 个抓取周期 |
| 比率类（成功率、错误率） | `5m`~`15m` | 分子分母都在抖，窗口太短会被单次请求污染 |
| 重尾分布（P95/P99） | `15m`~`30m` | 延迟天然抖，5m 窗口几乎必然周期性触发 |
| 慢变量（成本、Token） | `30m`~`1h` | 滞后信号，快速响应无意义 |
| 队列积压 | `10m`~`30m` | 滤掉正常工作节律（午休、夜间） |
| 质量信号（驳回率） | `30m`~`1h` | 样本量小，需累积统计显著性 |

三条硬约束：`for ≥ 2 × scrape_interval`（建议 ≥ 4×）；**查询窗口与 `for` 取同一量级**（否则触发时看到的「原因」和「已经坏了 15 分钟」这个事实脱节）；P1 的 `for` 要短到用户还没大规模投诉。

### 7.4 Alertmanager：分组、抑制、静默、路由

Prometheus 只负责**产生**告警；**发给谁、怎么发、发几次**是 Alertmanager 的职责。

| 概念 | 一句话 | 典型用法 |
| --- | --- | --- |
| 分组（grouping） | 同类告警**打包成一条通知** | 10 个 Pod 同时挂 -> 发 1 条而不是 10 条 |
| 抑制（inhibition） | 上层故障时**静音下层**连带告警 | 服务不可达时不再报延迟（延迟已无意义） |
| 静默（silence） | 人工**临时关掉**匹配的告警 | 发布窗口 / 计划内下游维护 |
| 路由（routing） | 按 label **决定发给谁** | P1 打电话，P3 发邮件 |

```yaml
# alertmanager/alertmanager.yml
global:
  resolve_timeout: 5m

route:
  receiver: default-p3
  group_by: ["alertname", "service", "severity"]
  group_wait: 30s        # 首次发现一组告警后等 30s，看是否还有同类，凑一起发
  group_interval: 5m     # 同组有新成员加入时，多久发一次
  repeat_interval: 4h    # 未恢复的告警，多久重复提醒
  routes:
    - matchers: [severity = "P1"]
      receiver: p1-oncall
      group_wait: 10s
      group_interval: 1m
      repeat_interval: 1h
    - matchers: [severity = "P2"]
      receiver: p2-ticket
      group_wait: 1m
      group_interval: 10m
      repeat_interval: 12h
    - matchers: [severity = "P2", alertname =~ "AgentCost.*"]
      receiver: cost-channel      # 成本类走独立通道，别和可用性告警混在一个群
      repeat_interval: 24h
    - matchers: [severity = "P3"]
      receiver: daily-digest
      repeat_interval: 24h

# 抑制 = 上游故障时静音下游，避免"一挂挂一片"刷屏
inhibit_rules:
  - source_matchers: [alertname = "AgentMetricsUnreachable"]
    target_matchers: [severity =~ "P1|P2"]
    equal: ["service"]
  - source_matchers: [alertname = "AgentToolFailing"]
    target_matchers: [alertname = "AgentToolSuccessRateLow"]
    equal: ["slo"]

receivers:
  - name: default-p3
    webhook_configs:
      - {url: "http://webhook-bridge:8060/alerts/digest", send_resolved: true}

  - name: p1-oncall
    email_configs:
      - to: "agent-oncall@example.com"
        from: "alertmanager@example.com"
        smarthost: "smtp.example.com:587"
        auth_password_file: "/etc/alertmanager/smtp_password"
        send_resolved: true
        headers: {Subject: "[P1][{{ .Status | toUpper }}] {{ .CommonLabels.alertname }}"}
    # 钉钉/企业微信/飞书的消息格式是自定义 JSON，Alertmanager 原生不认，
    # 标准做法是用 prometheus-webhook-dingtalk 之类的"桥"转成机器人消息
    webhook_configs:
      - {url: "http://dingtalk-bridge:8060/dingtalk/ops/send", send_resolved: true, max_alerts: 0}

  - name: p2-ticket
    webhook_configs:
      - {url: "http://ticket-bridge:8080/api/alerts", send_resolved: true}

  - name: cost-channel
    webhook_configs:
      - {url: "http://wecom-bridge:8061/wecom/cost/send", send_resolved: false}

  - name: daily-digest
    email_configs:
      - {to: "agent-team@example.com", from: "alertmanager@example.com",
         smarthost: "smtp.example.com:587", send_resolved: false}
```

（`matchers` 是新版语法（Alertmanager ≥ 0.22 推荐），替代已废弃的 `match` / `match_re`；字段与语法以官方文档为准。）

发布窗口静默（必须有明确结束时间与发布单号）：

```bash
amtool silence add --alertmanager.url=http://localhost:9093 \
  --author="alice" --comment="agent v1.4.2 发布窗口" \
  --start="2025-01-01T14:00:00+08:00" --end="2025-01-01T15:00:00+08:00" \
  service="agent"
```

**永久静默等于关掉监控**——它会让「监控缺失」本身变得不可见。

### 7.5 告警疲劳防治

告警疲劳（Alert Fatigue）是监控体系最常见的死法：告警太多 -> 值班人不看 -> 真故障被淹没。

| 措施 | 做法 |
| --- | --- |
| 每条告警都有动作 | 建立「告警 → Runbook」一对一映射；写不出动作的直接删掉 |
| 分级 + 不同通道 | 只有 P1 打扰人；P3 只进看板 |
| 定期清理 Top 噪音 | 每月统计哪些 alertname 触发最多但「无需处理」，逐个调阈值或加 `for` |
| 用 `for` 而不是降阈值 | 想减少误报时加 `for` 比抬高阈值更安全（不牺牲灵敏度） |
| 抑制 + 分组 | 见 7.4；一次故障一大片告警是最典型的刷屏源 |
| 值班回顾（Postmortem） | 每次 P1 后问：这条告警来早了吗？晚了吗？信息够定位吗？ |

判据：**一周内同一条告警触发 >5 次且每次都被判定「无需处理」，它就是噪音**——要么修阈值要么删掉。

## 八、SLO 与错误预算

### 8.1 从 SLI 到 SLO

| 术语 | 含义 | 示例 |
| --- | --- | --- |
| SLI（Service Level Indicator） | 一个**可测量的指标** | 请求成功率、工具成功率、P95 延迟 |
| SLO（Service Level Objective） | **内部目标**（含时间窗口） | 工具成功率 ≥ 95%（30 天滚动） |
| SLA（Service Level Agreement） | **对外承诺**（通常含赔偿） | 月度可用性 ≥ 99.5%，未达赔偿 |
| 错误预算（Error Budget） | `1 - SLO`，允许失败的量 | 5% 的工具调用允许失败 |
| Burn Rate | **预算消耗速度**，1 = 按计划烧完 | 14.4 = 1 小时烧掉 30 天预算的 2% |

阶段 3/4 项目的 SLO 表（数字来自项目示范口径，**必须用实测数据重新标定**）：

| SLI | 查询来源 | SLO | 窗口 | 看板阈值（黄/红） | 告警 |
| --- | --- | --- | --- | --- | --- |
| 请求成功率 | `rate(agent_requests_total{status="success"}) / rate(all)` | ≥ 99.0% | 30d | 0.99 / 0.90 | P2 / P1 |
| 工具成功率 | `rate(agent_tool_calls_total{result="success"}) / rate(all)` | ≥ 95.0% | 30d | 0.97 / 0.95 | — / P1 |
| 任务完成率 | `increase(agent_tasks_total{status="completed"}[1h]) / increase(all)` | ≥ 90.0% | 7d | 0.90 / 0.85 | — / P2 |
| P95 端到端延迟 | `histogram_quantile(0.95, ...)` | < 8s | 7d | 6s / 8s | — / P2 |
| 可用性 | `avg_over_time(up{job="agent"}[5m])` | ≥ 99.5% | 30d | 0.995 / 0.99 | — / P1 |

### 8.2 直接 SLI 法与 burn rate 法

**直接 SLI 法**（直观，适合看板）：

```promql
# 请求成功率 SLI（30 天滚动）
sum(rate(agent_requests_total{status="success"}[30d])) / sum(rate(agent_requests_total[30d]))

# 剩余错误预算（1 = 满，0 = 耗尽，负数 = 已超标）
1 - ((1 - sum(rate(agent_requests_total{status="success"}[30d]))
        / sum(rate(agent_requests_total[30d]))) / (1 - 0.99))

# P95 < 8s 的"合规比例"写法（不要对 P95 再做平均，那是错误口径）
sum(rate(agent_request_duration_seconds_bucket{le="8.0"}[30d]))
  / sum(rate(agent_request_duration_seconds_count[30d]))
```

**Burn rate 法**（推荐用于告警）：不看「当前值是否低于 SLO」，而看「**预算烧得多快**」。

```text
burn_rate = 实际错误率 / 允许错误率 = 错误率 / (1 - SLO)
burn_rate = 1    按计划在窗口结束时刚好用完预算
burn_rate = 14.4 1 小时烧掉 30 天预算的 2%（高烧 -> P1）
burn_rate = 6    6 小时烧掉 5%（中烧 -> P2）
```

**多窗口多燃烧率**：快慢窗口必须**同时**满足，才能既灵敏又不误报。

```yaml
# prometheus/rules/slo-burn-rate.yml
groups:
  - name: agent-slo-burn-rate
    rules:
      # 快烧 P1：5m 与 1h 两个窗口的 burn rate 都 > 14.4
      # 短窗口灵敏但易误报、长窗口稳但反应慢；"同时满足" = 既快又持久
      - alert: AgentToolSuccessBurnRateFast
        expr: |
          (sum(rate(agent_tool_calls_total{result!="success"}[5m]))
             / sum(rate(agent_tool_calls_total[5m]))) / (1 - 0.95) > 14.4
          and
          (sum(rate(agent_tool_calls_total{result!="success"}[1h]))
             / sum(rate(agent_tool_calls_total[1h]))) / (1 - 0.95) > 14.4
        for: 2m
        labels: {severity: P1, slo: tool_success_rate, window: 1h}
        annotations:
          summary: "工具成功率错误预算燃烧过快（1h 窗口 burn rate > 14.4）"
          description: "按当前速率，30 天错误预算将在约 2 天内耗尽。立即排查。"

      # 慢烧 P2：6h 与 3d 两个窗口都 > 6（持续性劣化，而非突发故障）
      - alert: AgentToolSuccessBurnRateSlow
        expr: |
          (sum(rate(agent_tool_calls_total{result!="success"}[6h]))
             / sum(rate(agent_tool_calls_total[6h]))) / (1 - 0.95) > 6
          and
          (sum(rate(agent_tool_calls_total{result!="success"}[3d]))
             / sum(rate(agent_tool_calls_total[3d]))) / (1 - 0.95) > 6
        for: 30m
        labels: {severity: P2, slo: tool_success_rate, window: 3d}
        annotations:
          summary: "工具成功率持续劣化（3d 窗口 burn rate > 6）"
          description: "查最近的 Prompt 变更、下游接口变更、数据分布变化。"

      # 延迟 SLI 用"超阈值比例"当错误率：error_rate = 1 - (8s 内完成比例)
      - alert: AgentLatencyBurnRateFast
        expr: |
          (1 - (sum(rate(agent_request_duration_seconds_bucket{le="8.0"}[5m]))
                  / sum(rate(agent_request_duration_seconds_count[5m]))))
            / (1 - 0.95) > 14.4
        for: 5m
        labels: {severity: P1, slo: latency_p95}
        annotations:
          summary: "延迟错误预算燃烧过快：超过 5% 的请求慢于 8 秒"
          description: "检查 LLM provider 状态与工具耗时。"
```

**为什么 burn rate 更好**：假设 SLO 99%，阈值告警写「成功率 <99% 持续 5m」——那么一次 10 秒的完全宕机（影响 200 个请求）可能因窗口太短**没触发**，但它已烧掉可观预算；而成功率长期稳在 99.05%（刚好过线）**永远不响**，预算却在慢慢被烧。Burn rate 把「故障严重程度」换算成统一货币（错误预算），让不同故障可比较、可排序。

### 8.3 线上 SLO 与离线评测：双轨制

| 维度 | 离线评测（[01](01-评测方法论与GoldenDataset设计.md)/[02 篇](02-评测指标详解与实现.md)） | 线上监控（本篇） |
| --- | --- | --- |
| 数据 | Golden Dataset（50~200 条人工标注用例） | 真实流量（全量） |
| 频率 | 每次 PR / 发布 | 实时连续 |
| 指标 | Answer Correctness、Faithfulness、Context Recall、Tool Call Accuracy、Task Completion Rate | 成功率、工具成功率、P95、成本、完成率 |
| 优势 | 有标准答案，能测「对不对」 | 覆盖真实分布，能测「稳不稳、贵不贵」 |
| 盲区 | 分布与线上不一致 | 无标准答案，测不出「答得对不对」 |
| 用途 | 门禁（Gate）：不达标不放行 | 告警 + 容量 + 成本 |

**唯一必须守住的纪律是口径一致**。以下四项要在两边有**同一段文字定义**：

| 指标 | 离线定义（02 篇） | 线上定义（本篇） | 一致性要求 |
| --- | --- | --- | --- |
| 任务完成率 | 用例中被判定 completed 的比例 | `agent_tasks_total{status="completed"} / 全部终态` | 「completed」判定用**同一份 rubric** |
| 工具成功率 | Tool Call Accuracy 中「参数合法且执行成功」的比例 | `agent_tool_calls_total{result="success"}` / 全部 | `success` 统一为「结果有效」而非「HTTP 200」 |
| 错误率 | 因错误失败的用例比例 | `agent_requests_total{status=~"error\|timeout"}` / 全部 | 错误分类枚举一致 |
| 延迟 | 单用例端到端耗时（含重试） | `agent_request_duration_seconds` | 计时起止点一致（是否含排队？） |

**为什么重要**：如果线上完成率 78%、离线 92%，你会陷入「是不是有 bug？-> 看 trace 没有；是不是模型退化？-> 看离线没有；是不是评测集太简单？-> 怎么证明？」的死循环。口径一致时结论是唯一的：**两个数不一致只能是「数据分布不同」**——问题从无解的「找 bug」变成可解的「分析线上输入分布」。

实务闭环（呼应 [01 篇](01-评测方法论与GoldenDataset设计.md) 的数据飞轮）：

```text
线上指标异常（Prometheus 告警）-> 从对应窗口捞失败 trace（03/04 篇）
  -> 人工标注「正确答案应是什么」-> 加入 Golden Dataset（01 篇）
  -> 离线评测复现（02 篇）-> 修复 -> 发布 -> 线上指标回归（本篇验证）
```

这条闭环就是阶段 5 综合实践（[08 篇](08-阶段5综合实践-全链路观测与评测报告.md)）要交付的东西。

## 九、踩坑点

### 9.1 Label 基数爆炸（最常见的「监控把自己搞挂」）

**症状**：Prometheus 内存与磁盘暴涨、查询变慢，`/api/v1/status/tsdb` 里某指标有几百万条序列。**原因**：把高基数值塞进 label。

```python
# ❌ 灾难：每次请求都新建多条序列
REQUESTS.labels(endpoint=path, user_id=uid, session_id=sid, trace_id=tid).inc()
# ✅ 正确：只保留取值有限的维度
REQUESTS.labels(endpoint=route_template, status=status).inc()
```

**判据**：一个 label 的去重值数量应是「几十」量级，不是「几万」。

| 危险 label | 危险原因 | 替代方案 |
| --- | --- | --- |
| `user_id` / `tenant_id` | 用户数无上限 | 只留 `tier="free/pro"` 之类分类 |
| `session_id` / `thread_id` / `task_id` | 每个任务一个新值 | 只留 `task_type` |
| `trace_id` / `request_id` | 每个请求一个新值 | 用 **Exemplar** 关联到 trace（每桶存一个，不增序列） |
| 原始 URL path / `query` / `prompt` | 无限取值 | 归一化为路由模板；文本进日志 |
| `error_message` | 含堆栈与 ID | 归一化为类型枚举；详情进日志 |
| 镜像 tag / `model_version` | 每次发布一个新值 | 用 Grafana Annotation 标记发布 |

预防：CI 里扫一遍 `/metrics` 输出，统计每个指标名的序列数，超阈值（如 1000）就失败；抓取侧兜底丢弃危险 label：

```yaml
    metric_relabel_configs:
      - {action: labeldrop, regex: "user_id|session_id|request_id|trace_id"}
      - {source_labels: [__name__], regex: "agent_debug_.*", action: drop}
```

### 9.2 Histogram 桶设置不当导致 P95 失真

**症状**：P95 一直显示 5.0s（恰好等于某个桶边界），或者显示 60s（全落在 `+Inf`）。**原因**：`histogram_quantile` 是**线性插值**，桶太粗时结果被「钉」在桶边界。

```python
buckets=(1, 5, 10)            # ❌ 太粗：真实 P95=4.7s，插值误差可达 ±0.5s
buckets=(0.5, 1, 2, 5, 10)    # ❌ 范围不够：Agent 常 20~40s，慢请求全堆在 +Inf
```

自检：若 `le="10"` 与 `le="+Inf"` 之间占比超过 20%，说明桶不够用（改桶是破坏性变更，见 9.6）。另一个隐藏错误：`histogram_quantile` 前**必须** `sum by (le)`：

```promql
# ❌ 跨序列的 bucket 不能直接用
histogram_quantile(0.95, rate(agent_request_duration_seconds_bucket[5m]))
# ✅ 正确
histogram_quantile(0.95, sum by (le) (rate(agent_request_duration_seconds_bucket[5m])))
```

### 9.3 多进程下指标重复与错乱

三种症状：`Duplicated timeseries in CollectorRegistry`（模块被 import 两次，常见于 `--reload` 热重载）；计数器在 4 个 worker 间随机跳、`rate()` 是锯齿；进程重启后计数**不归零反而累加**（死进程的 mmap 文件没清理）。对应解法见 3.4：指标集中定义一次 + `PROMETHEUS_MULTIPROC_DIR` + `MultiProcessCollector` + 退出钩子 `mark_process_dead(pid)`。**最简单的规避法**是 `--workers 1` + 多容器副本。

### 9.4 抓取间隔与告警 `for` / 查询窗口不匹配

```text
查询窗口 ≥ 4 × scrape_interval      （保证窗口内至少 4 个采样点）
for 时长 ≥ 2 × scrape_interval      （保证至少观察 2 个周期）
evaluation_interval ≤ for 时长 / 2  （保证规则被评估足够多次）
```

`scrape_interval=15s` 时的典型错误：`rate(x[30s])` 只有 2 个点，结果时有时无 -> 改用 `[1m]` 以上；`for: 30s` 只评估 2 次，边界会漏报 -> 改 `1m` 以上；`evaluation_interval: 1m` 配 `for: 5m` 只评估 5 次，触发时刻抖动大 -> 评估间隔改 15~30s；`rate(...[5m])` 配 `for: 30m`，触发时看到的「原因」是 5 分钟前的，对不上 -> 窗口与 `for` 同量级。另外 `rate(x[3d])` 要扫 3 天原始点，很慢——**长窗口 SLO 查询必须配 recording rules**（4.3）。

### 9.5 只看均值（P95 才是用户感受到的东西）

Agent 请求延迟是**双峰/重尾**分布：80% 走缓存或单轮 LLM（0.5~2s），20% 要跑多轮工具 + 长上下文（15~40s）。80×1 + 20×20 = 480s，均值 4.8s 看起来还行，但**每 5 个用户就有 1 个等了 20 秒**。所以：

```promql
# ❌ 只有均值会掩盖长尾；✅ 均值 + P50 + P95 + P99 一起看，
#    均值与 P50 的差距就是"长尾严重程度"
histogram_quantile(0.50, sum by (le) (rate(agent_request_duration_seconds_bucket[5m])))
histogram_quantile(0.99, sum by (le) (rate(agent_request_duration_seconds_bucket[5m])))
```

同理「成功率 95%」也不够：如果这 5% 全集中在最重要的 `/tasks/run` 长任务接口上，业务损失远大于「5% 的 `/health` 探测失败」。**要 `by (endpoint)` 拆开看**。

### 9.6 指标名/口径与评测文档不一致

**症状**：线上叫 `agent_task_success_rate`，[02 篇](02-评测指标详解与实现.md) 文档里叫「Task Completion Rate」，代码里第三处叫 `completion_ratio`——三份文档三个名字，读者无法对齐。**解法**：建立**单一事实来源（Single Source of Truth）**——仓库里放一份指标字典：

| 业务概念 | Prometheus 指标 | 离线评测指标（02 篇） | 定义 | 口径陷阱 |
| --- | --- | --- | --- | --- |
| 任务完成率 | `agent_tasks_total{status="completed"} / 全部终态` | Task Completion Rate | ... | 分母只含终态 |

**纪律**：① 指标名一旦上线就是 API，改名等于破坏下游看板与告警，需保留新旧双写一段时间；② 改口径必须同时改[02 篇](02-评测指标详解与实现.md)定义、Grafana 看板说明、告警规则注释、Runbook 四处；③ 在指标定义代码的 docstring 里写明「本指标对应 02 篇的 XX 指标」——3.6 的代码已经这么做。

### 9.7 其他常见坑速查

| 坑 | 后果 | 对策 |
| --- | --- | --- |
| `/metrics` 里查数据库/调 API | 抓取超时 -> `up=0` 误告警，且拖慢服务 | `/metrics` 只做内存序列化 |
| 用 Pushgateway 给常驻服务推指标 | 实例挂掉后 `up` 仍是 1，检测不到 | 长驻服务用 pull；Pushgateway 只给短生命周期批任务 |
| 在 `try` 成功分支里 observe | 慢请求不进直方图，P95 偏乐观 | 放 `finally` |
| Counter 被 `set()` 或清零 | `rate()` 判定为 counter reset，出现假尖峰 | Counter 只 inc；要归零请重启进程 |
| 告警没有 Runbook | 值班人不知道做什么 | 每条告警带 `runbook_url` |
| Grafana admin 用默认密码 | 被撞库，看板被篡改 | 首登改密 + secret 注入 |

## 十、与其他篇目的关系

```text
01 Golden Dataset ─┐
02 指标详解与实现 ──┴─► 指标口径的"标准答案"（成功率/工具成功率/完成率/延迟/错误分类）
                                │  口径必须一致！
                                ▼
03 Langfuse/LangSmith ─┐   ┌──────────────────────────────┐
04 OpenTelemetry ──────┼──►│ 06 Prometheus + Grafana       │
   （单次请求怎么了）   │   │ · /metrics 埋点                │
05 安全评测与加固 ─────┘   │ · PromQL 与看板                │
   （日志/审计/拦截计数）    │ · 告警规则 + Alertmanager      │
                            │ · SLO 与错误预算               │
                            └───────────┬──────────────────┘
                                        │ 部署时带上这套栈
                                        ▼
                              07 生产化部署与 CI/CD
                                        │
                                        ▼
                              08 综合实践：全链路观测与评测报告
```

| 篇目 | 与本篇的关系 |
| --- | --- |
| [01 篇](01-评测方法论与GoldenDataset设计.md) | 提供 Golden Dataset；本篇的线上失败样本要回流到它，构成数据飞轮 |
| [02 篇](02-评测指标详解与实现.md) | **最重要**：本篇所有指标口径的上游定义，离线/线上双轨必须共用同一份定义（8.3） |
| [03 篇](03-Langfuse与LangSmith可观测性.md) | 调试层：指标报警后从这里捞 trace 归因 |
| [04 篇](04-OpenTelemetry与自定义Tracing.md) | 埋点层：3.7 路线 C 直接复用它的 span；Exemplar 可把指标点跳到 trace |
| [05 篇](05-Agent安全评测与加固.md) | 提供 `agent_guardrail_blocks_total{reason}` 的分类口径与日志规范 |
| [07 篇](07-生产化部署与CI-CD.md) | 部署时带上本文的编排：Prometheus 服务发现、发布时静默告警、健康检查与 `/metrics` 一起进镜像 |
| [08 篇](08-阶段5综合实践-全链路观测与评测报告.md) | 综合实践要求交付「Grafana 看板与告警」，就是本篇的产出物 |

## 学习自检与练习

### 练习 1：接一版指标并在 Grafana 出图

**任务**：给阶段 3「企业运维分析 Agent」或阶段 4「研发效能 Agent」的服务接入至少 8 个指标（必须含 `agent_requests_total`、`agent_request_duration_seconds`、`agent_tool_calls_total`、`agent_tasks_total`、`agent_llm_tokens_total`、`agent_llm_cost_usd_total`、`agent_hitl_pending`、`agent_errors_total`），用 5.2/5.3 的 compose 起栈，在 Grafana 建出 6.2 清单里的 ①②④⑤⑥⑬ 六个面板。

**提示**：先 `curl localhost:8000/metrics` 验证暴露，再看 Prometheus `/targets` 是否 UP；没有流量就没有数据，写脚本打 30~50 次请求，并**人为注入 10% 失败与超时**，否则成功率和错误率面板全绿看不出效果；`$__rate_interval` 依赖数据源配置里的 `timeInterval`（5.3）。

**验收标准**：`/targets` 里 `job="agent"` 是 UP；6 个面板都有数据且时间范围切到 1h 时曲线连续；`/metrics` 输出里所有指标的 label 去重值 < 100；导出看板 JSON 存进项目 `docs/`。

### 练习 2：写 3 条告警规则并实际触发验证

**任务**：写三条覆盖不同类型的规则——① 成功率低于阈值（比率类，`for: 5m`）；② 单工具成功率过低（分类类，`by (tool)`，`for: 10m`）；③ `up == 0` 或 HITL 积压（状态/Gauge 类）。然后**真的触发一次**，观察 `Pending -> Firing -> Resolved` 完整生命周期，并在 Alertmanager 确认分组与静默生效。

**提示**：触发方法是脚本持续打失败请求，或 `docker compose stop agent` 触发 `up == 0`；想快速看到效果可临时把 `for` 改小（如 `30s`），但**验证完要改回来**——这正好能体会 9.4 的「间隔与 for 的匹配」；`amtool silence add` 加静默后确认告警不再通知，删掉静默确认恢复。

**验收标准**：三条规则都在 `/rules` 可见且 `for` 正确生效（记录从表达式为真到 Firing 的时间差）；Alertmanager 里能看到正确的**分组**与**抑制**效果；交付 `docs/alerts-runbook.md`，每条告警写明触发条件、影响、第一步动作、升级路径，且每条告警的 annotation 里都有 `runbook_url`。

### 练习 3：用 PromQL 算成功率与 P95（含口径对比）

**任务**：写出并**实测**六条查询——① 请求成功率（口径 A：`status="success"` / 全部）；② 请求成功率（口径 B：排除 `client_error`），比较差值并解释来源；③ 全局 P95 与按 `endpoint` 拆分的 P95；④ 按 `tool` 拆分的工具成功率，找出最差的工具；⑤ 当日成本与日环比（`increase(...[24h])` 与 `offset 24h`）；⑥ 「8 秒内完成率」（`_bucket{le="8.0"}/_count`），在 P95 = 7.9s 与 P95 = 8.1s 两个时刻各看一次，验证它与 P95 < 8s 是否等价。

**提示**：窗口至少 `4 × scrape_interval`（9.4）；第 ⑥ 条的关键是确认 `8.0` 是桶边界（2.5），否则两者不等价——这就是桶设置的重要性；把 P50 也加上，**均值与 P50 的差距就是长尾严重程度**（9.5）。

**验收标准**：能解释口径 A/B 的差异原因；`sum(A)/sum(B)` 顺序正确、`histogram_quantile` 前有 `sum by (le)`；六条查询都返回非空；能指出「最差工具是哪个」「长尾主要出现在哪个 endpoint」；提交一张「查询 → 数值 → 口径解释」的表存进 `docs/`。

### 练习 4（进阶）：把 SLO 写成 burn rate 告警

**任务**：把 8.1 表中的两项 SLO（工具成功率 ≥ 95%、P95 < 8s）写成多窗口 burn rate 告警（快烧 P1 + 慢烧 P2），并验证：注入 3 分钟内 50% 失败后，快烧告警在 ≤7 分钟内进入 Firing；停止注入后自动 Resolved；并做一个显示「剩余错误预算百分比」的 Stat 面板。

**提示**：burn rate 公式见 8.2；SLO 95% 对应分母 `(1 - 0.95) = 0.05`；快烧用 5m+1h 双窗口，慢烧用 6h+3d 双窗口（长窗口查询请先配 recording rules，见 4.3 与 9.4）。

**验收标准**：快烧告警按时触发并能自动恢复；错误预算面板在注入期间肉眼可见地下降；能说出「为什么 burn rate 比阈值告警更早发现一次短暂全挂」。

### 自检清单

- [ ] 能说清 Traces / Logs / Metrics 的分工，以及为什么「告警不能靠翻 trace」；
- [ ] 能解释 metric name + labels = 时间序列，以及为什么 `user_id` 不能做 label；
- [ ] 能说出 pull/scrape 模型的三条推论（`/metrics` 要廉价、`up` 即存活、服务发现）；
- [ ] 能在 Counter / Gauge / Histogram / Summary 之间正确选型，并解释延迟为什么用 Histogram；
- [ ] 能说出 `_bucket` / `_sum` / `_count` 的含义，以及为什么 `8.0` 要恰好是一个桶边界；
- [ ] 能用 `prometheus-client` 在 FastAPI 里暴露 `/metrics`，并知道多进程模式的四条纪律；
- [ ] 能独立写出一份 Agent 指标清单，且每个 label 都是封闭枚举；
- [ ] 会用 LangChain callback / LangGraph 钩子 / OTel SpanProcessor 做自动埋点；
- [ ] 能写 `rate` / `increase` / `sum by` / `histogram_quantile`，并知道 `sum(A)/sum(B)` 的顺序；
- [ ] 能用 docker compose 起全套栈并跑通 5.4 的验证步骤；
- [ ] 能设计 Grafana 看板，且面板阈值与告警规则用同一套数字；
- [ ] 能写告警规则并解释每条 `for` 时长的选择理由；
- [ ] 知道 Alertmanager 的分组/抑制/静默/路由，且知道静默必须有结束时间；
- [ ] 能把 SLO 写成直接 SLI 与 burn rate 两种查询；
- [ ] 能说出线上 SLO 与离线评测「口径一致」的具体要求，以及不一致时如何缩小排查范围。

## 参考资料

官方文档优先（Prometheus / Grafana / Python 客户端）：

- Prometheus 官方文档 - 数据模型（metric name 与 labels）: https://prometheus.io/docs/concepts/data_model/
- Prometheus 官方文档 - 指标类型（Counter / Gauge / Histogram / Summary）: https://prometheus.io/docs/concepts/metric_types/
- Prometheus 官方文档 - Metric 与 label 命名实践: https://prometheus.io/docs/practices/naming/
- Prometheus 官方文档 - 查询基础（PromQL）: https://prometheus.io/docs/prometheus/latest/querying/basics/
- Prometheus 官方文档 - 查询函数（`rate` / `increase` / `histogram_quantile`）: https://prometheus.io/docs/prometheus/latest/querying/functions/
- Prometheus 官方文档 - 告警规则配置（`alert` / `expr` / `for` / `labels` / `annotations`）: https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/
- Prometheus 官方文档 - 记录规则实践（recording rules 与命名约定）: https://prometheus.io/docs/practices/rules/
- Prometheus 官方文档 - 告警实践（Alerting）: https://prometheus.io/docs/practices/alerting/
- Prometheus 官方文档 - Alertmanager: https://prometheus.io/docs/alerting/latest/alertmanager/
- Prometheus Python 客户端（prometheus-client）文档: https://prometheus.github.io/client_python/
- Prometheus Python 客户端 GitHub 仓库: https://github.com/prometheus/client_python
- Grafana 官方文档 - 告警（Alerting，含统一告警与告警规则）: https://grafana.com/docs/grafana/latest/alerting/
- Grafana 官方文档 - 看板变量（Template variables）: https://grafana.com/docs/grafana/latest/dashboards/variables/add-template-variables/
- Grafana 官方教程 - 用 provisioning 管理数据源与看板: https://grafana.com/tutorials/provision-dashboards-and-data-sources/
- OpenTelemetry 官方文档 - 规范总览（配合 04 篇与本文 3.7）: https://opentelemetry.io/docs/specs/otel/

> 提示：本文涉及的库 API、镜像 tag、Grafana 面板字段与 Alertmanager 配置语法迭代较快，动手前请以官方文档为准；示例中的阈值（90% / 95% / 8s / 14.4 等）来自阶段 3/4 项目的示范口径，**你的项目必须用实测数据重新标定**，不要照抄。
