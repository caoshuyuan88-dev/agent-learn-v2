# 生产化部署：Docker、K8s、CI/CD 与发布策略

> 本文定位：阶段 5 前六篇里，[01](01-评测方法论与GoldenDataset设计.md)/[02](02-评测指标详解与实现.md) 给了你「上线前的底气」（评测门禁），[03](03-Langfuse与LangSmith可观测性.md)/[04](04-OpenTelemetry与自定义Tracing.md)/[06](06-Prometheus与Grafana监控告警.md) 给了你「上线后的眼睛」（追踪、指标、告警）。本篇补齐最后一公里：把「企业运维分析 Agent」与「研发效能 Agent」从一个能跑的 Python 进程，变成**可构建、可部署、可灰度、可回滚、可降级**的线上服务，覆盖规划表中「部署与 CI/CD」以及「模型/Prompt 发布策略、降级与容灾」两块。前置：阶段 4 的长任务与 Checkpoint、阶段 3 的工具调用与安全，以及 03 篇的 prompt 版本、06 篇的指标口径。工具口径：Docker / Docker Compose / Kubernetes / GitHub Actions，LLM 侧 OpenAI SDK + LangGraph 1.x。

## 学习目标

学完本文，你应该能：

- 说清 Agent 服务相比普通 Web 服务在生产化上的 7 类特殊挑战以及每一类的对策；
- 写出生产级多阶段 `Dockerfile`（非 root、只复制必要文件、缓存友好、带 `HEALTHCHECK`），并解释每一行为什么这么写；
- 用 `docker-compose.yml` 一键起「agent + postgres + langfuse + prometheus + grafana」本地栈，与 03/06 篇的观测体系对齐；
- 写出 Deployment / Service / Ingress / ConfigMap / Secret / HPA / PDB 最小清单，并正确区分 startup / readiness / liveness 三类探针在 Agent 场景的取值；
- 搭一条完整 GitHub Actions 流水线：lint → 单元测试 → **评测回归门禁** → 构建推送镜像 → staging 自动 / prod 人工审批；
- 设计 prompt 与模型的发布流程（影子流量 → 金丝雀 → 全量），说清每一步看什么指标、什么情况下回滚；
- 给服务做降级与容灾设计（备用模型、熔断、排队、只读模式），并写出可执行的混沌演练方案；
- 用一张上线检查清单自查，避免「把 key 打进镜像」「liveness 打死慢请求」「内存态 Checkpoint 冲突」等经典事故。

## 一、Agent 服务生产化的特殊挑战

### 1.1 本地能跑 ≠ 能上生产

本地 `uvicorn app.main:app --reload` 跑通，只证明**逻辑对**。上生产后会依次撞上：

```text
本地：单人、单请求、无限时间、key 在 .env 里、模型永远可用
生产：多租户并发、请求超时、配额限流、密钥要轮换、模型会 5xx、成本要兜底
      + 普通 Web 服务没有的东西：会话状态、长任务、prompt 与模型漂移
```

阶段 4 的研发效能 Agent 是典型：一次任务跑 1~5 分钟、中途调多个外部系统、要等人工审批、要能从崩溃恢复。这类服务天然**不适合同步 HTTP 长连接**，也**不能假设「重启 = 无状态」**。

### 1.2 七类挑战

**① 外部 LLM 依赖不稳定且有限流。** LLM API 是「别人的服务」：有 5xx、有抖动、有 RPM/TPM 配额、有区域故障，p99 可能是 p50 的 5 倍。必须假设它**一定会失败**。

**② 成本是有上限的。** 普通服务的成本随 QPS 线性增长；Agent 的成本还随「每请求 token 数」增长——而 token 数取决于 agent 循环了几轮、工具返回了多长内容。一个失控重试能让单请求成本涨 50 倍。成本必须是一等公民指标（06 篇已建好口径）。

**③ 会话与 Checkpoint 状态。** `MemorySaver` 是进程内存：多副本下「请求 A 打到 Pod 1、恢复请求打到 Pod 2」就找不到状态了。生产必须用 `PostgresSaver` + **外部** Postgres（详见 [阶段 4-05](../阶段4-复杂工作流与Deep-Agents/05-Checkpoint持久化与长任务恢复.md)）。

**④ 密钥管理。** `.env` 本地很方便，上生产就是事故源：打进镜像 = 任何能拉镜像的人都能读；提交进 Git = 永久泄露（删了也在历史里）。生产密钥必须走 Secret / 密钥管理服务，且支持轮换。

**⑤ 多实例并发与幂等。** 水平扩容后「同一件事被执行两次」的概率大幅上升：定时任务、队列重投、从 Checkpoint 重放（阶段 4-05 §5.3）。幂等从「好习惯」变成「正确性前提」。

**⑥ 长任务与请求超时的矛盾。** 网关、Ingress、客户端都有超时，5 分钟的任务塞不进 30 秒的请求。解法是**请求只负责受理**（返回 `task_id`），执行交给后台 worker，用户轮询状态接口（见 [阶段 4-07](../阶段4-复杂工作流与Deep-Agents/07-Event-driven-Workflow与异步长任务.md)）。

**⑦ 模型与 prompt 变更导致行为漂移。** 改代码有 diff、有 review、有回滚；但「换模型版本」「改 prompt 一句话」影响面可能更大，而且**不会有编译错误**，只会让 pass rate 静默下降 8%。

### 1.3 挑战 → 对策 → 本篇章节

| 挑战 | 对策 | 章节 |
| --- | --- | --- |
| LLM 不稳定 / 限流 | 超时 + 退避重试 + 熔断 + 备用供应商；readiness 不探 LLM | 六、二 |
| 成本上限 | 请求级 token 预算、循环步数上限、成本指标 + 预算告警 | 六、七 |
| 会话 / Checkpoint 状态 | 外部 Postgres + `PostgresSaver`，多副本共享 | 三、六 |
| 密钥管理 | K8s Secret / 外部密钥服务，CI 用 Secrets + 环境保护 | 三、四 |
| 多实例并发 / 幂等 | 幂等键、数据库唯一约束、队列单一消费 | 一、六 |
| 长任务 vs 请求超时 | 受理即返回 + 后台 worker + 状态查询接口 | 二、三 |
| 模型 / prompt 漂移 | 版本化 + 评测门禁 + 影子/金丝雀 + 一键回滚 | 四、五 |

### 1.4 类比 Java

| Agent 服务 | Java 后端对应物 |
| --- | --- |
| Docker 镜像 / Compose | 可执行 fat jar / 本地 compose 起 MySQL+Redis+Zipkin |
| K8s Deployment | K8s 里跑多副本 Spring Boot |
| readiness / liveness | Actuator `/health/readiness`、`/health/liveness` |
| Checkpoint（Postgres） | 分布式 Session / 状态机持久化 |
| prompt 版本（Langfuse label） | 配置中心的灰度配置（Apollo/Nacos） |
| 评测门禁 / 金丝雀发布 | 集成测试 + 性能基线门禁 / 灰度发布 |

熟悉的词一个不少，只是「被测对象」从确定性函数变成了概率性模型——**这是唯一、也是最本质的区别**。

## 二、Docker 镜像化（重点）

### 2.1 完整的生产级 Dockerfile

```dockerfile
# syntax=docker/dockerfile:1.9

########## 阶段 1：builder —— 只装依赖，不进入最终镜像 ##########
FROM python:3.12-slim AS builder
# uv 官方镜像自带 uv/uvx 二进制；COPY --from 比 curl 安装更快更稳
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /uvx /bin/
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# 关键：先只复制依赖清单。依赖没变 -> 这一层命中缓存 -> 不重装依赖
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev
# 再复制源码并安装项目自身
COPY src/ ./src/
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

########## 阶段 2：runtime —— 只带 venv + 源码，非 root 运行 ##########
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONFAULTHANDLER=1 \
    PATH="/app/.venv/bin:$PATH" TZ=Asia/Shanghai
# 探针要用的 curl + 时区数据；装完立刻清 apt 缓存，别留在层里
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl tzdata ca-certificates \
 && rm -rf /var/lib/apt/lists/*
# 非 root：固定 uid/gid，便于挂载卷时对齐权限
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app
WORKDIR /app
# 只从 builder 拷「运行需要的东西」
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/src  /app/src
COPY --chown=app:app scripts/ /app/scripts/
COPY --chown=app:app alembic.ini /app/alembic.ini
USER app
EXPOSE 8000
# 容器自身健康检查（K8s 下由探针取代，但 docker run / compose 仍有用）
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1
ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--timeout-graceful-shutdown", "25", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
```

| 写法 | 为什么 |
| --- | --- |
| 多阶段构建 | builder 里的编译器、`uv` 二进制、构建缓存不进最终镜像，体积常减 40%~60%（见 [多阶段构建](https://docs.docker.com/build/building/multi-stage/)） |
| `python:3.12-slim` | 比 full 小几百 MB，又比 `alpine` 少踩 wheel/glibc 的坑（`numpy`/`psycopg`/`grpcio` 在 musl 上常编译失败） |
| 先 COPY 依赖清单再 COPY 源码 | 层缓存按「指令 + 上下文内容」哈希：改源码不会让依赖层失效。**最重要的构建缓存纪律** |
| `--mount=type=cache` | BuildKit 缓存挂载：缓存不进镜像层但跨构建复用，装依赖从分钟级降到秒级 |
| `UV_COMPILE_BYTECODE=1` | 构建期预编译 `.pyc`，冷启动少一次编译 |
| `UV_PYTHON_DOWNLOADS=never` | 禁止 uv 在容器内再下一个 Python，只用基础镜像的 3.12 |
| `PYTHONUNBUFFERED=1` | 不加这行 stdout 被缓冲，`kubectl logs` 看不到实时日志 |
| `PYTHONFAULTHANDLER=1` | 段错误时打出 Python 调用栈，容器里排障神器 |
| 固定 uid/gid 的非 root 用户 | 默认 root 一旦被提权就是逃逸起点；固定 uid 让卷权限可预测 |
| `HEALTHCHECK` + `--start-period` | 给足启动时间，避免启动期被误判为不健康 |
| `--timeout-graceful-shutdown` | uvicorn 收到 SIGTERM 后停收新连接、给在途请求留收尾时间（uvicorn 0.22+ 支持，参数名以官方文档为准） |

纯 `pip` 的差异只有一处——利用缓存挂载：`RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt`。挂载缓存用于**下载缓存**跨构建复用，`--no-cache-dir` 只影响是否把 wheel 写进镜像层，二者不冲突；不想用 BuildKit 就退化成「先 COPY requirements.txt 再 pip install」，能拿到 90% 的收益。

### 2.2 .dockerignore

没有它，`docker build .` 会把 `.git`、`.venv`、`__pycache__`、测试数据甚至 `.env` 全打包进构建上下文：上传慢、缓存频繁失效、**密钥可能被 `COPY . .` 带进镜像**。

```text
.git
.github
.venv
venv
__pycache__
*.py[cod]
*.egg-info
.pytest_cache
.ruff_cache
.mypy_cache
tests/
docs/
*.md
!README.md
notebooks/
*.ipynb
.env
.env.*
!.env.example
*.pem
*.key
data/
*.sqlite
*.db
dist/
build/
.coverage
htmlcov/
docker-compose*.yml
Dockerfile*
```

### 2.3 体积与构建缓存优化

先量体积，再瘦身：`docker build -t ops-agent:dev .`、`docker history --no-trunc ops-agent:dev`（逐层看谁最大）、`docker run --rm ops-agent:dev du -sh /app/.venv`。

| 胖子 | 瘦身 |
| --- | --- |
| 基础镜像太大 / builder 工具链 | 用 `-slim`/`distroless`；多阶段只 COPY 产物 |
| 开发依赖（pytest/ruff/jupyter） | `--no-dev` 或独立依赖组 |
| apt 缓存 / `.git` 与测试数据 | 同层 `rm -rf /var/lib/apt/lists/*`；`.dockerignore` |
| 模型文件 baked 进镜像 | 启动时从对象存储拉取 + 缓存卷 |

加快构建的三条：① 锁定文件（`--frozen`）保证可复现且缓存键稳定；② CI 上用构建缓存后端跨机器复用层；③ 只在真需要时才多平台构建。

```bash
docker buildx build --platform linux/amd64 \
  --cache-from type=gha --cache-to type=gha,mode=max \
  --build-arg GIT_SHA="$(git rev-parse --short HEAD)" \
  -t ghcr.io/your-org/ops-agent:sha-$(git rev-parse --short HEAD) --push .
```

本地/CI runner 的构建缓存会膨胀到几十 GB，定期回收：`docker builder prune --keep-storage 10GB`（机制见 [构建缓存垃圾回收](https://docs.docker.com/build/cache/garbage-collection/) 与 [构建最佳实践](https://docs.docker.com/build/building/best-practices/)）。

### 2.4 镜像安全

按投入产出排序的四层防线：① **非 root 运行**（`USER app`）——收益最大，一行代码；② **最小依赖**——每个 apt 包都是潜在 CVE，`curl` 只为探针，能用 `python -c` 就别装；③ **漏洞扫描**——[Trivy](https://trivy.dev/) 放进 CI 当门禁：

```bash
trivy image --severity HIGH,CRITICAL --exit-code 1 ghcr.io/your-org/ops-agent:sha-abc1234
```

④ **供应链**——固定基础镜像 digest（`FROM python:3.12-slim@sha256:...`）、锁文件哈希校验。注意**镜像不是构建一次就完事**，要定期重建以吸收基础镜像的上游补丁。K8s 侧再加运行时加固（见 3.1 的 `securityContext`）；开了 `readOnlyRootFilesystem` 记得给 `/tmp` 挂 `emptyDir`。

### 2.5 docker-compose.yml：本地一键起完整栈

```yaml
name: ops-agent
services:
  postgres:
    image: postgres:16-alpine
    environment: { POSTGRES_USER: agent, POSTGRES_PASSWORD: "${POSTGRES_PASSWORD:-agent_local_pw}", POSTGRES_DB: agent, TZ: Asia/Shanghai }
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./deploy/initdb:/docker-entrypoint-initdb.d:ro   # 建 langfuse 库与 checkpoint 表
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U agent -d agent"]
      interval: 5s
      timeout: 3s
      retries: 20
    ports: ["5432:5432"]
  langfuse:                  # v3 自托管还需 ClickHouse/Redis/S3，完整清单见官方 compose
    image: langfuse/langfuse:latest
    depends_on:
      postgres: { condition: service_healthy }
    environment:
      DATABASE_URL: postgresql://agent:${POSTGRES_PASSWORD:-agent_local_pw}@postgres:5432/langfuse
      NEXTAUTH_URL: http://localhost:3000
      NEXTAUTH_SECRET: ${LANGFUSE_NEXTAUTH_SECRET:?必须显式提供}
      SALT: ${LANGFUSE_SALT:?必须显式提供}
      TELEMETRY_ENABLED: "false"
    ports: ["3000:3000"]
  prometheus:
    image: prom/prometheus:v3.1.0
    volumes:
      - ./deploy/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./deploy/prometheus/alerts.yml:/etc/prometheus/alerts.yml:ro
      - promdata:/prometheus
    command: ["--config.file=/etc/prometheus/prometheus.yml", "--storage.tsdb.retention.time=15d"]
    ports: ["9090:9090"]
  grafana:
    image: grafana/grafana:11.5.1
    depends_on: [prometheus]
    environment: { GF_SECURITY_ADMIN_PASSWORD: "${GRAFANA_ADMIN_PASSWORD:-admin}", GF_USERS_ALLOW_SIGN_UP: "false" }
    volumes:
      - grafanadata:/var/lib/grafana
      - ./deploy/grafana/provisioning:/etc/grafana/provisioning:ro
    ports: ["3001:3000"]
  agent:
    build: { context: ., dockerfile: Dockerfile, target: runtime }
    depends_on:
      postgres: { condition: service_healthy }
    env_file: [.env]                     # 本地开发用；生产改用 K8s Secret
    environment:
      DATABASE_URL: postgresql://agent:${POSTGRES_PASSWORD:-agent_local_pw}@postgres:5432/agent
      LANGFUSE_HOST: http://langfuse:3000
      OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-collector:4317
      TZ: Asia/Shanghai                  # 时区！否则时间戳对不上告警
    ports: ["8000:8000"]
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 25
    stop_grace_period: 40s
    deploy:
      resources:
        limits: { cpus: "1.5", memory: 1g }
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:8000/healthz"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 30s
  worker:                                # 长任务后台执行进程
    build: { context: ., dockerfile: Dockerfile, target: runtime }
    depends_on:
      postgres: { condition: service_healthy }
    env_file: [.env]
    environment:
      DATABASE_URL: postgresql://agent:${POSTGRES_PASSWORD:-agent_local_pw}@postgres:5432/agent
      LANGFUSE_HOST: http://langfuse:3000
    command: ["python", "-m", "app.worker"]
    stop_grace_period: 60s               # 长任务：给足收尾时间
volumes:
  pgdata:
  promdata:
  grafanadata:
```

三点说明：① **`condition: service_healthy` 才是真的等依赖就绪**，裸 `depends_on` 只保证启动顺序（见 [Compose 启动顺序](https://docs.docker.com/compose/how-tos/startup-order/)）；② **Langfuse v3 自托管还需 ClickHouse/Redis/S3**，完整文件以 [Langfuse 官方自托管文档](https://langfuse.com/self-hosting/deployment/docker-compose) 的 compose 为准，本地演示可直接用它再把 `agent` 服务并进去；③ 生产**不要把 Postgres 与 agent 放同一 Compose/Node**，数据库要独立、要备份、要 PITR。

```bash
docker compose up -d --build      # 起栈
docker compose logs -f agent      # 跟日志
docker compose ps                 # 看健康状态
docker compose down -v            # 连数据卷一起清（慎用）
```

### 2.6 启动脚本与优雅关闭

`docker-entrypoint.sh` 干三件事：等依赖、跑迁移、`exec` 主进程。

```bash
#!/usr/bin/env sh
# 注意：slim/alpine 的 /bin/sh 不支持 pipefail，用 set -eu 即可
set -eu
echo "[entrypoint] waiting for postgres..."
i=0
until python -c "
import os, sys, psycopg
try:
    psycopg.connect(os.environ['DATABASE_URL'], connect_timeout=2).close()
except Exception as e:
    print(e, file=sys.stderr); sys.exit(1)
" 2>/dev/null; do
  i=$((i + 1)); [ "$i" -ge 60 ] && { echo "postgres not ready, abort"; exit 1; }
  sleep 2
done
python -m app.db.migrate          # 迁移失败直接退出，别带病启动
exec "$@"                         # 关键：exec 让主进程直接收到 SIGTERM
```

**为什么必须 `exec`**：不加它 shell 是 PID 1，`docker stop` 的 SIGTERM 只到 shell，Python 收不到 → 10 秒后 SIGKILL → **在途请求被硬切、长任务丢失**。这是「优雅关闭失效」最常见的原因。

**Python 侧要做什么**：uvicorn 自动处理 SIGTERM，但 agent 层还有自己的资源要收尾。

```python
# app/main.py
from contextlib import asynccontextmanager
import asyncio, logging, os
from fastapi import FastAPI, Response, status
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

STATE = {"ready": False, "shutting_down": False, "pending": 0}


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncPostgresSaver.from_conn_string(os.environ["DATABASE_URL"]) as saver:
        await saver.setup()                    # 建表，幂等
        app.state.checkpointer = saver
        STATE["ready"] = True
        try:
            yield
        finally:
            # 关闭顺序：先置未就绪（K8s 把本 Pod 摘出端点），再等在途请求收尾
            STATE["ready"] = STATE["shutting_down"] = True
            for _ in range(30):
                if STATE["pending"] == 0:
                    break
                await asyncio.sleep(0.5)
            logging.info("drained, closing checkpointer pool")


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def count_inflight(request, call_next):
    STATE["pending"] += 1
    try:
        return await call_next(request)
    finally:
        STATE["pending"] -= 1


@app.get("/healthz")            # liveness：只证明「进程活着」，绝不碰 LLM/DB
async def healthz():
    return {"status": "ok"}


@app.get("/readyz")             # readiness：证明「能接新流量」
async def readyz(response: Response):
    if not STATE["ready"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "draining"}
    return {"status": "ready", "inflight": STATE["pending"]}
```

**优雅关闭的时间预算**（这个式子要背下来）：`terminationGracePeriodSeconds(60s) > preStop(10s) + 在途请求最长耗时(25s) + 收尾开销(10s)`。四处必须自洽，否则最慢的环节一定被 SIGKILL。

| 位置 | 参数 | 作用 |
| --- | --- | --- |
| K8s | `terminationGracePeriodSeconds` | 从 SIGTERM 到 SIGKILL 的总预算 |
| K8s | `preStop: sleep 10` | 等端点摘除生效（**先摘流量，再关应用**） |
| uvicorn | `--timeout-graceful-shutdown 25` | 在途请求收尾上限 |
| Compose | `stop_grace_period: 40s` | 本地等价物 |

### 2.7 踩坑点（Docker 部分）

1. **`COPY . .` 不带 `.dockerignore`** → `.env` 进镜像。上线前必查：`docker run --rm img sh -c 'ls -a /app'`。
2. **`ENV OPENAI_API_KEY=sk-...` 写在 Dockerfile 里** → `docker history` 就能看到，永久泄露。
3. **容器时区不对**：基础镜像默认 UTC，日志与告警时间对不上本地。显式设 `TZ` 并装 `tzdata`。
4. **slim 镜像没有 `curl`**，`HEALTHCHECK` 直接失败——装 curl，或用 `python -c "import urllib.request; urllib.request.urlopen(...)"`。
5. **`--workers N` 与内存**：每个 worker 是独立进程，连接与缓存不共享，`N` 要按内存与实测吞吐定。
6. **`--reload` 误入生产**：文件监听 + 单 worker，抗不住并发。
7. **只读根文件系统没挂 `emptyDir`**：`/tmp` 不可写直接崩。

## 三、Kubernetes 部署要点

### 3.1 最小可用清单

```yaml
# deploy/k8s/config.yaml
apiVersion: v1
kind: ConfigMap
metadata: { name: ops-agent-config, namespace: agent }
data:
  LOG_LEVEL: "INFO"
  TZ: "Asia/Shanghai"
  LLM_TIMEOUT_SECONDS: "60"
  LLM_MAX_RETRIES: "2"
  LLM_MAX_CONCURRENCY: "20"
  AGENT_MAX_STEPS: "25"                 # 防死循环的第一道闸
  AGENT_REQUEST_TIMEOUT_SECONDS: "120"
  OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector.observability:4317"
  LANGFUSE_HOST: "http://langfuse.observability:3000"
---
# 只放占位符：真实值用 kubectl create secret 或 External Secrets 注入
apiVersion: v1
kind: Secret
metadata: { name: ops-agent-secrets, namespace: agent }
type: Opaque
stringData:
  DATABASE_URL: "postgresql://agent:CHANGE_ME@postgres.infra:5432/agent"
  OPENAI_API_KEY: "sk-CHANGE_ME"
  LANGFUSE_PUBLIC_KEY: "pk-lf-CHANGE_ME"
  LANGFUSE_SECRET_KEY: "sk-lf-CHANGE_ME"
---
# deploy/k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: ops-agent, namespace: agent, labels: { app: ops-agent } }
spec:
  replicas: 3
  revisionHistoryLimit: 5              # 保留历史 ReplicaSet，方便 rollout undo
  strategy:
    type: RollingUpdate
    rollingUpdate: { maxSurge: 1, maxUnavailable: 0 }
  selector: { matchLabels: { app: ops-agent } }
  template:
    metadata:
      labels: { app: ops-agent }
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8000"
        prometheus.io/path: "/metrics"
    spec:
      serviceAccountName: ops-agent
      terminationGracePeriodSeconds: 60
      securityContext: { runAsNonRoot: true, runAsUser: 10001, fsGroup: 10001 }
      topologySpreadConstraints:       # 多副本散开，单节点故障不至于全挂
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector: { matchLabels: { app: ops-agent } }
      containers:
        - name: api
          image: ghcr.io/your-org/ops-agent:sha-PLACEHOLDER   # CI 用 commit sha 覆写
          ports: [{ name: http, containerPort: 8000 }]
          envFrom:
            - configMapRef: { name: ops-agent-config }
            - secretRef: { name: ops-agent-secrets }
          resources:
            requests: { cpu: 250m, memory: 512Mi }
            limits: { cpu: "1500m", memory: 1Gi }
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: { drop: ["ALL"] }
          volumeMounts: [{ name: tmp, mountPath: /tmp }]
          startupProbe:                # ① 启动：给足冷启动，最多容忍 120s
            httpGet: { path: /healthz, port: http }
            periodSeconds: 5
            failureThreshold: 24
          readinessProbe:              # ② 就绪：决定是否给流量，可查依赖，不探 LLM
            httpGet: { path: /readyz, port: http }
            periodSeconds: 10
            timeoutSeconds: 3
            failureThreshold: 3
          livenessProbe:               # ③ 存活：只证明进程没僵死，零 I/O
            httpGet: { path: /healthz, port: http }
            periodSeconds: 20
            timeoutSeconds: 5
            failureThreshold: 3
          lifecycle:
            preStop: { exec: { command: ["/bin/sh", "-c", "sleep 10"] } }
      volumes:
        - name: tmp
          emptyDir: { sizeLimit: 256Mi }
---
# deploy/k8s/service-ingress-pdb.yaml
apiVersion: v1
kind: Service
metadata: { name: ops-agent, namespace: agent }
spec:
  type: ClusterIP
  selector: { app: ops-agent }
  ports: [{ name: http, port: 80, targetPort: http }]
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ops-agent
  namespace: agent
  annotations:
    nginx.ingress.kubernetes.io/proxy-read-timeout: "180"    # 要 ≥ 应用超时
    nginx.ingress.kubernetes.io/proxy-send-timeout: "180"
    nginx.ingress.kubernetes.io/proxy-body-size: "8m"
spec:
  ingressClassName: nginx
  rules:
    - host: agent.example.com
      http:
        paths:
          - { path: /, pathType: Prefix, backend: { service: { name: ops-agent, port: { number: 80 } } } }
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata: { name: ops-agent, namespace: agent }
spec:
  minAvailable: 2                      # 节点维护/驱逐时保住可用副本
  selector: { matchLabels: { app: ops-agent } }
```

> **纪律**：`secret.yaml` 里永远只有 `CHANGE_ME`。**默认 Secret 只是 base64，不是加密**——务必读 K8s 的 [Secret 良好实践](https://kubernetes.io/docs/concepts/security/secrets-good-practices/)；PDB 用法见 [配置 PDB](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)。

### 3.2 探针：三类探针的差别与 Agent 场景取值

| 探针 | 回答的问题 | 失败后果 | Agent 服务该探什么 |
| --- | --- | --- | --- |
| `startupProbe` | 启动完了吗？ | **重启容器**（启动期其余探针暂停） | `/healthz`；阈值放宽到 60~120s，覆盖导入 + 建池 + 迁移 |
| `readinessProbe` | 能接新流量吗？ | **摘出 Service 端点**（不重启） | `/readyz`；可选轻量查 DB，**不探 LLM** |
| `livenessProbe` | 进程僵死了吗？ | **重启容器** | `/healthz`；只回 200，不做任何 I/O |

**为什么慢 LLM 请求绝不能用 liveness 兜？** 假设请求要调 LLM 60 秒，liveness 每 20 秒一次、3 次失败就重启：

```text
错误做法：liveness -> /deep-check（真的调一次 LLM）
  t=0   请求进来，agent 开始调 LLM（耗时 60s）
  t=20  liveness 也去调 LLM -> 排队 -> 超时（timeoutSeconds=5）
  t=40  第二次超时
  t=60  第三次超时 -> kubelet 判定"僵死" -> SIGTERM -> 在途请求被杀 -> 用户 502
        （更糟：token 已经烧了，结果被丢弃；新 Pod 冷启动又慢）
```

**正确做法**：liveness 只问「HTTP 服务器还能回 200 吗」；`/readyz` 反映「是否准备好接流量」（含 draining 标记）；真正的业务健康交给**指标**（06 篇的 `agent_llm_errors_total`、`agent_request_duration_seconds`）判断——**重启治不好上游限流**。进阶技巧：把「依赖故障」映射到 readiness 而非 liveness。DB 挂了 → readiness 失败 → 全部 Pod 摘流量 → 上游收到明确的 503 快速失败，比一串 30 秒超时好得多。

### 3.3 资源 requests/limits 与并发模型

**requests 决定调度，limits 决定上限**（见 [管理容器资源](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)）。Agent 服务的资源画像与普通 Web 服务不同：**CPU 大部分时间在等 I/O**（LLM 与工具调用都是等待，CPU request 可以很小）；**内存与并发数强相关**（每个在途请求持有一份消息历史，`--workers N` 又是 N 份解释器）；**LLM 限流才是真瓶颈**（CPU 打满之前你早就撞上 RPM/TPM 上限）；**突发时内存尖峰**（长上下文 + 大响应体，比如一次工具返回 2MB 日志）。

```text
并发能力 ≈ workers × (1 / 单请求平均占用时间) × 安全系数 0.7
真实上限 = min(CPU 上限, 内存上限, LLM RPM/TPM 配额, DB 连接数)
```

四条纪律：① **limits 不要远大于 requests**（request 250m / limit 4 核会让突发争抢拖垮同节点邻居），一般 limit ≤ 2~4 × request；② **内存 limit 必须设**（OOM 是容器最常见崩溃），用压测定值；③ 加 `AGENT_MAX_STEPS` 与请求级 token 预算——这是对**成本**的限制，效果等同资源限制；④ **用队列削峰而不是无限扩副本**：LLM 有配额，扩到 50 副本只会得到 50 份 429。

### 3.4 ConfigMap / Secret 注入

优先级：`镜像内默认值 < ConfigMap（非敏感） < Secret（敏感） < 命令行/环境显式覆写`。代码侧用 Pydantic Settings 统一收口，**缺关键配置时启动即失败**：

```python
# app/config.py
from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: SecretStr = Field(...)
    openai_api_key: SecretStr = Field(...)
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 2
    llm_max_concurrency: int = 20
    agent_max_steps: int = 25
    agent_request_timeout_seconds: float = 120.0
    log_level: str = "INFO"
    otel_exporter_otlp_endpoint: str | None = None


def load_settings() -> Settings:
    try:
        return Settings()                       # type: ignore[call-arg]
    except ValidationError as e:
        raise SystemExit(f"配置缺失或非法，拒绝启动：\n{e}") from e
```

**Secret 轮换**：改 Secret 后 Pod 里的环境变量**不会自动更新**（`envFrom` 是启动时快照）。轮换流程 = 更新 Secret → `kubectl rollout restart deployment/ops-agent`（滚动、不中断）。把这条写进运维手册。

### 3.5 HPA：按什么扩容

```yaml
# deploy/k8s/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata: { name: ops-agent, namespace: agent }
spec:
  scaleTargetRef: { apiVersion: apps/v1, kind: Deployment, name: ops-agent }
  minReplicas: 3
  maxReplicas: 12                      # 上限 = LLM 配额 / 单副本 QPS，别拍脑袋
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 30
      policies: [{ type: Percent, value: 100, periodSeconds: 60 }]   # 每分钟最多翻倍
    scaleDown:
      stabilizationWindowSeconds: 300  # 缩容保守，防抖动
      policies: [{ type: Percent, value: 25, periodSeconds: 60 }]
  metrics:
    - type: Resource
      resource: { name: cpu, target: { type: Utilization, averageUtilization: 60 } }
    - type: Pods                        # 自定义指标：队列积压，长任务场景最准的扩容信号
      pods:
        metric: { name: agent_queue_depth }
        target: { type: AverageValue, averageValue: "5" }
```

**LLM 限流下扩容的意义（重要认知）**：① **CPU/内存扩容对「等 LLM」几乎无效**——协程在等 I/O，CPU 不高，HPA 不触发；② 真正的扩容信号是**队列深度 / 排队延迟**，所以要么用自定义指标（由 Prometheus Adapter 从 06 篇的指标暴露），要么把并发上限做在应用层（信号量）；③ **超过供应商配额后，扩容只会把 429 放大**，正确姿势是 `minReplicas × 单副本并发 × 安全系数 ≤ 供应商 TPM/RPM 配额`，超出部分排队而非猛扩；④ **`maxReplicas` 同时是预算阀门**，配合成本告警。（完整用法与 `behavior` 语义见 [HPA 演练文档](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale-walkthrough/)。）

### 3.6 优雅终止：完整时序

```text
kubectl delete pod / 滚动更新 / 缩容
  ├─ 1. Pod 置 Terminating；从 Service Endpoints 摘除（异步，需要时间）
  ├─ 2. preStop hook: sleep 10        ← 给摘除传播留时间
  ├─ 3. kubelet 发 SIGTERM 给容器 PID 1
  ├─ 4. uvicorn 停止接受新连接，在途请求继续跑（≤ timeout-graceful-shutdown）
  ├─ 5. lifespan 收尾：关闭连接池 / Checkpointer
  └─ 6. 超过 terminationGracePeriodSeconds -> SIGKILL（硬切）
```

**长任务 worker 的额外规则**：收到 SIGTERM 时不能直接死，必须 ① 停止从队列**领取新任务**；② 把当前任务跑完，或标记为「可重投递」后交还队列；③ 依赖**幂等键**保证重投递不产生重复副作用（阶段 4-05 §5.3）。

```python
# app/worker.py（骨架）
import asyncio, signal

_shutdown = asyncio.Event()


def _on_term(*_):
    _shutdown.set()          # 信号处理器里只置标志，不做 I/O


async def main() -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _on_term)
    while not _shutdown.is_set():
        task = await queue.claim(timeout=5)      # 停止领新任务后自然退出循环
        if task is None:
            continue
        try:
            await run_graph(task, thread_id=f"task-{task.id}")   # 幂等键 = task.id
            await queue.ack(task)
        except Exception:
            # 不 ack -> 重新可见 -> 别的 worker 用同一 thread_id 续跑（Checkpoint 保证不从头）
            await queue.nack(task, requeue=True)
```

### 3.7 Checkpoint 用外部 Postgres

| 方案 | 多副本可行性 | 说明 |
| --- | --- | --- |
| `MemorySaver` | ❌ | 请求落到别的 Pod 就丢状态 |
| `SqliteSaver` + 共享卷 | ⚠️ | 单写者锁冲突；RWO 卷挂不到多节点 |
| `PostgresSaver`（独立/托管 Postgres） | ✅ | 生产唯一选择 |

四个要点：① **one-time setup 只做一次**——`saver.setup()` 是 `CREATE TABLE IF NOT EXISTS`，多副本同时启动通常安全，但更稳的是用 Job 或迁移工具跑一次，应用启动只做只读校验；② **连接池按副本数分配**：`副本数 × 每副本池大小 < Postgres max_connections`，否则扩容时连接被打满——这是很隐蔽的「一扩容就故障」；③ **Checkpoint 表会膨胀**，按 `thread_id` 做 TTL 清理（阶段 4-05 §3.3），否则千万级行拖慢 `get_state`；④ Checkpoint 里有用户输入与审批意见，**备份要加密 + 访问审计**（见 [05 篇](05-Agent安全评测与加固.md)）。

### 3.8 滚动更新

`maxSurge: 1` + `maxUnavailable: 0` 表示「先多起 1 个新 Pod，但更新期间容量绝不下降」——零停机，代价是需要额外资源且更新变慢。`maxSurge: 1` 一个个换、资源占用最小，但 12 副本要换 12 轮。

**Agent 服务的特殊考虑**：滚动更新会重启 Pod，而 Pod 上可能正跑着 5 分钟的长任务。所以 API 层（无状态、只受理）放心滚动；**worker 层要单独一个 Deployment**，配更大的 `terminationGracePeriodSeconds`（如 300s），并配合队列「不 ack 即重投递」。

**K8s 原生滚动更新是全量替换，不是金丝雀**。金丝雀要靠：① 两个 Deployment + 按权重的 Service/Ingress 分流（简单可控）；② GitOps 工具（Argo Rollouts / Flagger，提供 canary CRD + 自动分析 + 自动回滚）；③ 应用层按用户/租户分流（最灵活，见第五节）。

```bash
kubectl -n agent set image deploy/ops-agent api=ghcr.io/your-org/ops-agent:sha-abc1234
kubectl -n agent rollout status deploy/ops-agent --timeout=180s
kubectl -n agent rollout undo deploy/ops-agent                   # 回滚上一版
kubectl -n agent rollout undo deploy/ops-agent --to-revision=3
```

（机制见 [执行滚动更新](https://kubernetes.io/docs/tutorials/kubernetes-basics/update/update-intro/) 与 [Pod 生命周期](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)。）

### 3.9 日志采集与 OTel Collector

**纪律：全部打到 stdout/stderr，不要写文件**（写文件 = 容器退出就丢 + 要额外卷 + 要自己 rotate）。结构化 JSON 日志带上 `trace_id`，与 [04 篇](04-OpenTelemetry与自定义Tracing.md) 的链路对齐：

```python
import json, logging, sys
from opentelemetry import trace


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ctx = trace.get_current_span().get_span_context()
        return json.dumps({
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname, "logger": record.name, "msg": record.getMessage(),
            "trace_id": format(ctx.trace_id, "032x") if ctx.is_valid else None,
            "span_id": format(ctx.span_id, "016x") if ctx.is_valid else None,
        }, ensure_ascii=False)


logging.basicConfig(level=logging.INFO, force=True,
                    handlers=[logging.StreamHandler(sys.stdout)])
logging.getLogger().handlers[0].setFormatter(JsonFormatter())
```

```text
应用 stdout ──► 节点级日志 agent（Fluent Bit / Vector DaemonSet）──► Loki / ES
应用 OTLP  ──► OTel Collector ──► Tempo/Jaeger(traces) + Prometheus(metrics)
                              └─► 采样/脱敏后再出网（不要 100% 上报到 SaaS）
```

三种部署形态（见 [OTel Collector 安装文档](https://opentelemetry.io/docs/collector/install/kubernetes/)）：**DaemonSet** 收节点级日志 + 主机指标，每节点一份开销固定；**Deployment（Gateway）** 应用统一发到一个中心 Collector，集中采样/脱敏/批处理，但要配多副本 + PDB；**Sidecar** 隔离最好但开销 × 副本数，大集群不划算。生产推荐 **Deployment Gateway + 应用直连 OTLP**：脱敏（脱掉 prompt 里的 PII，见 [05 篇](05-Agent安全评测与加固.md)）、采样（长会话 trace 很大，头采样 + 错误全采样）、批量导出都在 Gateway 做。

## 四、CI/CD 流水线（重点）

### 4.1 流水线设计原则

```text
快反馈在前，慢验证在后；越贵的门禁越靠后；任何一步失败都不得产出可部署制品。

PR:    lint ─┐
       test ─┼─► eval（小规模 golden 子集）─► build（不推送）
       scan ─┘
main:  lint/test/eval/scan ─► build&push（sha 标签）─► deploy staging（自动）─► 冒烟+观察 ─► deploy prod（人工审批）
tag:   同上 ─► build&push（semver 标签）─► deploy prod
```

### 4.2 完整 GitHub Actions 工作流

```yaml
# .github/workflows/ci.yml
name: ci
on:
  push: { branches: [main], tags: ["v*.*.*"] }
  pull_request: { branches: [main] }
concurrency:                       # 同分支新提交取消旧运行，省额度
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
permissions:
  contents: read
  packages: write                  # 推 GHCR 需要
  id-token: write                  # OIDC，免长期密钥
env:
  IMAGE_NAME: ${{ github.repository }}
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with: { enable-cache: true }
      - run: uv sync --frozen --group lint
      - run: uv run ruff check . && uv run ruff format --check .
      - run: uv run mypy src/app --ignore-missing-imports

  test:                            # 单元/集成测试：全部 mock，不调真实 LLM
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with: { enable-cache: true }
      - run: uv sync --frozen --group dev
      - run: uv run pytest tests/unit -q --cov=src/app --cov-report=xml --cov-fail-under=70
        env:
          OPENAI_API_KEY: "sk-test-not-used"
          DATABASE_URL: "postgresql://agent:pw@localhost:5432/agent_test"
      - name: Integration tests with Postgres
        run: |
          docker run -d --name pg -e POSTGRES_PASSWORD=pw -e POSTGRES_USER=agent \
            -e POSTGRES_DB=agent_test -p 5432:5432 postgres:16-alpine
          for i in $(seq 1 30); do docker exec pg pg_isready -U agent -d agent_test && break || sleep 2; done
          uv run pytest tests/integration -q
      - uses: actions/upload-artifact@v4
        if: always()
        with: { name: coverage, path: coverage.xml }

  image-scan:                      # 镜像安全门禁
    runs-on: ubuntu-latest
    needs: [test]
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t local/ops-agent:scan .
      - uses: aquasecurity/trivy-action@0.28.0
        with:
          image-ref: local/ops-agent:scan
          severity: HIGH,CRITICAL
          exit-code: "1"
          ignore-unfixed: "true"

  eval-gate:                       # 评测回归门禁（本篇核心环节）
    runs-on: ubuntu-latest
    needs: [test]
    strategy:
      fail-fast: false
      matrix: { suite: [core, tool-calling, safety] }
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with: { enable-cache: true }
      - run: uv sync --frozen --group dev --group eval
      - name: Run evaluation subset
        env:
          OPENAI_API_KEY: ${{ secrets.EVAL_OPENAI_API_KEY }}   # 评测专用 key，额度隔离
          LANGFUSE_PUBLIC_KEY: ${{ secrets.LANGFUSE_PUBLIC_KEY }}
          LANGFUSE_SECRET_KEY: ${{ secrets.LANGFUSE_SECRET_KEY }}
          EVAL_SUITE: ${{ matrix.suite }}
          EVAL_SAMPLE_SIZE: ${{ github.event_name == 'pull_request' && '25' || '120' }}
        run: |
          uv run python -m evals.run_gate \
            --suite "$EVAL_SUITE" --sample-size "$EVAL_SAMPLE_SIZE" \
            --baseline "evals/baselines/$EVAL_SUITE.json" \
            --tolerance 0.02 --hard-floor 0.95 \
            --report "evals/reports/$EVAL_SUITE.json"
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: eval-report-${{ matrix.suite }}
          path: evals/reports/
          retention-days: 30

  build:
    runs-on: ubuntu-latest
    needs: [lint, test, image-scan, eval-gate]
    if: github.event_name != 'pull_request'      # PR 只验证，不推送制品
    outputs:
      image: ${{ steps.meta.outputs.image }}
      digest: ${{ steps.push.outputs.digest }}
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Compute tags
        id: meta
        run: |
          echo "sha_tag=sha-$(git rev-parse --short HEAD)" >> "$GITHUB_OUTPUT"
          echo "image=ghcr.io/${IMAGE_NAME}" >> "$GITHUB_OUTPUT"
      - name: Build and push
        id: push
        uses: docker/build-push-action@v6
        with:
          context: .
          target: runtime
          platforms: linux/amd64
          push: true
          # 标签策略：sha 是唯一可追溯标识；分支名只作为人类便利标签
          tags: |
            ${{ steps.meta.outputs.image }}:${{ steps.meta.outputs.sha_tag }}
            ${{ steps.meta.outputs.image }}:${{ github.ref_name }}
          build-args: GIT_SHA=${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          provenance: true          # SLSA provenance，供应链可追溯
          sbom: true                # 生成 SBOM

  deploy-staging:
    runs-on: ubuntu-latest
    needs: [build]
    if: github.ref == 'refs/heads/main'
    environment:
      name: staging                 # staging 无审批人 -> 自动通过
      url: https://staging.agent.example.com
    steps:
      - name: Roll out to staging
        run: |
          echo "${{ secrets.KUBE_CONFIG_STAGING }}" | base64 -d > /tmp/kc
          export KUBECONFIG=/tmp/kc
          kubectl -n agent-staging set image deploy/ops-agent \
            api=${{ needs.build.outputs.image }}:${{ needs.build.outputs.sha_tag }}
          kubectl -n agent-staging rollout status deploy/ops-agent --timeout=180s
      - name: Smoke test + bake
        run: |
          for i in $(seq 1 30); do
            code=$(curl -s -o /dev/null -w '%{http_code}' https://staging.agent.example.com/readyz || true)
            [ "$code" = "200" ] && break || sleep 5
          done
          [ "$code" = "200" ] || { echo "staging not ready"; exit 1; }
          sleep 600                 # 观察期：让金丝雀指标有足够样本

  deploy-prod:
    runs-on: ubuntu-latest
    needs: [build, deploy-staging]
    if: github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/tags/v')
    environment:
      name: production              # 配 Required reviewers -> 卡住等人 Approve
      url: https://agent.example.com
    steps:
      - name: Show what will be deployed
        run: |
          echo "image:  ${{ needs.build.outputs.image }}:${{ needs.build.outputs.sha_tag }}"
          echo "digest: ${{ needs.build.outputs.digest }}"
          echo "commit: ${{ github.sha }}"
      - name: Canary 1 -> 10%
        run: |
          echo "${{ secrets.KUBE_CONFIG_PROD }}" | base64 -d > /tmp/kc
          export KUBECONFIG=/tmp/kc
          kubectl -n agent set image deploy/ops-agent-canary \
            api=${{ needs.build.outputs.image }}:${{ needs.build.outputs.sha_tag }}
          kubectl -n agent scale deploy/ops-agent-canary --replicas=1
          kubectl -n agent rollout status deploy/ops-agent-canary --timeout=180s
      - name: Watch canary
        run: uv run python -m ops.canary_watch --minutes 15 --max-error-rate 0.02
      - name: Promote to 100%
        run: |
          export KUBECONFIG=/tmp/kc
          kubectl -n agent set image deploy/ops-agent \
            api=${{ needs.build.outputs.image }}:${{ needs.build.outputs.sha_tag }}
          kubectl -n agent rollout status deploy/ops-agent --timeout=300s
          kubectl -n agent scale deploy/ops-agent-canary --replicas=0
      - name: Rollback on failure
        if: failure()
        run: |
          export KUBECONFIG=/tmp/kc
          kubectl -n agent rollout undo deploy/ops-agent
          kubectl -n agent rollout status deploy/ops-agent --timeout=180s
```

### 4.3 评测回归门禁：把 01/02 篇接进 CI

这是 Agent 项目区别于普通项目的关键一步：**逻辑层测试全绿 ≠ 行为没有退化**。改一句 prompt、升一个模型版本，`pytest` 依然全过，但任务成功率可能掉 10%。

```python
# evals/run_gate.py —— 跑 golden 子集，与基线对比，不达标则 exit(1) 让 CI 失败
from __future__ import annotations
import argparse, json, random, sys
from pathlib import Path
from evals.dataset import load_golden        # 01 篇的数据集加载
from evals.metrics import evaluate_run       # 02 篇的指标计算
from app.graph import build_graph


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(int(len(values) * p), len(values) - 1)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", required=True)
    ap.add_argument("--sample-size", type=int, default=25)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--tolerance", type=float, default=0.02)    # 允许的最大回归
    ap.add_argument("--hard-floor", type=float, default=0.95)   # 绝对底线
    ap.add_argument("--report", required=True)
    ap.add_argument("--seed", type=int, default=20250101)       # 固定采样，可复现
    args = ap.parse_args()

    cases = load_golden(suite=args.suite)
    random.Random(args.seed).shuffle(cases)
    cases = cases[: args.sample_size]
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))

    graph, results = build_graph(), []
    for case in cases:
        try:
            out = graph.invoke(case.to_input(),
                               config={"configurable": {"thread_id": f"eval-{case.id}"}})
            results.append(evaluate_run(case, out))     # -> passed/latency_s/cost_usd/error
        except Exception as e:                          # 单条失败不应中断整批
            results.append({"case_id": case.id, "passed": False, "error": str(e),
                            "latency_s": 0.0, "cost_usd": 0.0})

    pass_rate = sum(r["passed"] for r in results) / len(results)
    p95 = percentile([r["latency_s"] for r in results], 0.95)
    cost = sum(r["cost_usd"] for r in results)
    report = {"suite": args.suite, "n": len(results), "pass_rate": pass_rate,
              "p95_latency_s": p95, "cost_usd_total": cost,
              "baseline_pass_rate": baseline["pass_rate"],
              "failed_cases": [r["case_id"] for r in results if not r["passed"]]}
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    failures = []
    if pass_rate < args.hard_floor:
        failures.append(f"pass_rate {pass_rate:.3f} < hard floor {args.hard_floor}")
    if pass_rate < baseline["pass_rate"] - args.tolerance:
        failures.append(f"regression: {pass_rate:.3f} vs {baseline['pass_rate']:.3f}")
    if p95 > baseline["p95_latency_s"] * 1.3:
        failures.append(f"p95 latency {p95:.1f}s > 1.3x baseline")
    if cost > baseline["cost_usd_total"] * 1.2:
        failures.append(f"cost {cost:.2f} > 1.2x baseline")
    for f in failures:
        print(f"  - {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

| 门禁设计要点 | 做法 |
| --- | --- |
| 子集要小 | PR 上 25~50 条（3~5 分钟、几毛钱），main 上 100~300 条 |
| 采样固定 | 固定 seed，否则「通过/不通过」本身有随机性 |
| 分套件 | `core`（成功率）/ `tool-calling`（工具选择正确率）/ `safety`（越权与注入，[05 篇](05-Agent安全评测与加固.md)），各自独立基线与阈值 |
| 阈值分两类 | **硬底线**（安全类，必须 ≥95%，不可放宽）+ **回归容差**（相对基线，允许 2 个百分点抖动） |
| 延迟/成本也要门禁 | 只测正确性会放过「成功率没掉但成本涨 3 倍」的变更 |
| 报告留档 | artifact 存 30 天做趋势；结果写回 Langfuse（[03 篇](03-Langfuse与LangSmith可观测性.md)） |
| 失败可诊断 | 输出失败 case id + trace 链接，而不是只给一个数字 |

**浮点抖动怎么办**：LLM 评测本身有方差（同版本两次跑可能差 1~2 个百分点）。两个手段：① 把容差设在实测噪声之上（先同版本跑 5 次算方差再定 tolerance）；② 关键用例多次采样取多数（成本与时长上升）。

### 4.4 缓存与并行

| 手段 | 效果 |
| --- | --- |
| `matrix` 拆评测套件 | 三套件并行，wall-clock 缩到约 1/3 |
| `concurrency.cancel-in-progress` | 同分支新 push 取消旧 run，省额度 |
| Docker 层缓存 `type=gha` | 镜像构建从 5 分钟降到 40 秒 |
| `needs` 精确化 | lint/test/eval/scan 并行，全过才 build |
| 脚本内限并发评测 | `asyncio.gather` + 信号量，注意供应商 RPM 上限 |

依赖缓存用 `astral-sh/setup-uv@v5` 的 `enable-cache: true`（配 `cache-dependency-glob: uv.lock`）即可；若用本地 embedding 模型再加 `actions/cache@v4` 缓存 `~/.cache/huggingface`。缓存限制见 [GitHub 缓存依赖文档](https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows)：有仓库总容量上限（默认 10 GB，超出按 LRU 淘汰）且**默认不跨仓库共享**。别把整个 `.venv` 塞进缓存——锁文件一变就完全失效，缓存**下载缓存**更划算。

### 4.5 密钥与环境保护规则

| 场景 | 做法 |
| --- | --- |
| CI 里调 LLM 做评测 | 用**独立的评测专用 key**（额度隔离），存在 repo/environment Secret |
| 云厂商认证 | 用 **OIDC**（`id-token: write`），避免长期 AK |
| 集群 kubeconfig | 只给 deploy 所需 RBAC（能 `set image`/`rollout` 特定 Deployment），不给 cluster-admin |
| fork 来的 PR | `pull_request` 事件默认**不注入 secret**；**不要**为了「让 fork PR 能跑评测」改用 `pull_request_target` + 注入 secret（严重漏洞） |
| 生产发布 | `environment: production` 配 **Required reviewers** + **Wait timer** + 限定 `deployment branches` |

环境保护规则（见 [管理部署环境文档](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)）的四个能力：**Required reviewers**（人工 Approve 才继续）、**Wait timer**（审批后强制等待，留反悔窗口）、**Deployment branches**（只允许 `main` 与 `v*` 部署生产）、**Environment secrets**（staging/prod 密钥隔离，同一 workflow 也拿不到另一环境的密钥）。**为什么生产必须人工审批**：Agent 行为是概率性的，「自动全绿就上线」会在某天把一次 prompt 调整静默推到全量用户；人工门 + 观察期 + 一键回滚，是把「不可逆事故」变成「五分钟事故」的最小成本方案。

### 4.6 制品与可追溯

| 要素 | 做法 |
| --- | --- |
| 镜像标签 | **主标签 = `sha-<short_commit>`**（唯一、不可变）；`v1.2.3` 作为发布标记；`latest`/分支名只做人类便利标签，**部署时绝不使用** |
| 部署用 digest | `image: ghcr.io/org/ops-agent@sha256:...` 才真正不可变（tag 可被覆盖） |
| 构建元数据 | `GIT_SHA`、`BUILD_TIME` 作为 build-arg 注入，并在 `/version` 暴露 |
| SBOM / provenance | `sbom: true`、`provenance: true`，合规审计时能回答「镜像里有什么」 |

```python
@app.get("/version")
async def version():
    # 排障第一问：「线上跑的是哪个 commit、哪个 prompt 版本、哪个模型？」
    return {"git_sha": os.getenv("GIT_SHA", "unknown"),
            "image_digest": os.getenv("IMAGE_DIGEST", "unknown"),
            "prompt_versions": prompt_registry.versions(),   # 03 篇的 prompt 版本
            "model": os.getenv("LLM_MODEL", "gpt-4o-mini")}
```

**把「线上跑的是哪个 prompt 版本」放进 `/version`**，是 Agent 服务排障中最被低估的一步。用户说「昨天还好好的」，你第一件事就是对比 `/version` 与昨天的记录。

### 4.7 本地等价命令（Makefile）

CI 里跑的每一步本地都要能一条命令复现，否则「CI 挂了本地查不了」会浪费大量时间。

```makefile
# Makefile —— 本地等价于 CI 的命令集
PY ?= uv run
IMAGE ?= ghcr.io/your-org/ops-agent
SHA := $(shell git rev-parse --short HEAD)

install:         ## 安装依赖（含 dev）
	uv sync --frozen
lint:            ## 等价 CI 的 lint job
	$(PY) ruff check . && $(PY) ruff format --check . && $(PY) mypy src/app --ignore-missing-imports
fmt:             ## 自动修复
	$(PY) ruff check --fix . && $(PY) ruff format .
test:            ## 等价 CI 的 test job（全部 mock，不调 LLM）
	$(PY) pytest tests/unit tests/integration -q
eval:            ## 等价 CI 的 eval-gate：小规模 golden 子集
	$(PY) python -m evals.run_gate --suite core --sample-size 25 \
	  --baseline evals/baselines/core.json --tolerance 0.02 --hard-floor 0.95 \
	  --report evals/reports/core.json
eval-full:       ## 全量评测（发布前手动跑，300 条）
	$(PY) python -m evals.run_gate --suite core --sample-size 300 \
	  --baseline evals/baselines/core.json --report evals/reports/core-full.json
build:           ## 本地构建镜像
	docker build --build-arg GIT_SHA=$(SHA) -t $(IMAGE):sha-$(SHA) .
scan:            ## 本地漏洞扫描
	trivy image --severity HIGH,CRITICAL $(IMAGE):sha-$(SHA)
run:             ## 本地直接跑 API（不用容器）
	$(PY) uvicorn app.main:app --reload --port 8000
compose-up:      ## 起完整本地栈
	docker compose up -d --build && docker compose ps
clean:
	docker builder prune -f --keep-storage 10GB
```

```bash
make lint test eval        # 提交前本地自检（等价 CI）
make compose-up            # 起栈，打开 Grafana 看指标
make build scan            # 构建 + 扫漏洞
```

（也常用 `just`（`justfile`）替代 Make，差别主要在语法与 Windows 友好度，选团队熟悉的即可。）

## 五、模型与 Prompt 的发布策略

### 5.1 三类变更的风险画像

| 变更类型 | 例子 | 可静态验证 | 影响面 | 风险 | 需要的流程 |
| --- | --- | --- | --- | --- | --- |
| **代码** | 修 bug、加工具、调重试 | ✅ 类型/单测 | 可控 | 中 | review + 单测 + 评测 + 灰度 |
| **Prompt** | 改系统提示词、改 few-shot | ❌ | **全域，无编译错误** | **高** | review + **必跑评测** + 版本化 + 可回滚 |
| **模型** | `gpt-4o-mini` → 新版本 | ❌ | 全域 + 成本/延迟同时变 | **最高** | 影子 → 金丝雀 → 全量 + 成本对照 |
| **参数** | `temperature`、`max_tokens` | ❌ | 全域 | 中高 | 评测 + 灰度 |

```text
静态可验证性：  代码 ████████  prompt ██  model █
影响面：        代码 部分      prompt 全部  model 全部 + 费用结构
回滚速度：      代码 分钟级    prompt 秒级  model 分钟级
```

**结论：prompt 与模型变更必须走完整的评测 + 灰度流程，甚至比代码更严格。**

### 5.2 Prompt 版本管理与回滚

用 [03 篇](03-Langfuse与LangSmith可观测性.md) 讲的 Langfuse Prompt Management（label 机制）：

```python
# app/prompts.py —— 代码里永远不硬编码 prompt 文本
from langfuse import Langfuse

langfuse = Langfuse()          # 读 LANGFUSE_PUBLIC_KEY / SECRET_KEY / HOST


class PromptRegistry:
    """prompt 读取入口：env 决定用哪个 label；带 TTL 缓存，拉取失败时用缓存兜底。"""

    def __init__(self, label: str | None = None, cache_ttl_seconds: int = 60) -> None:
        self._label = label or os.getenv("PROMPT_LABEL", "production")
        self._cache: dict[str, tuple[float, object]] = {}

    def get(self, name: str):                      # 以官方文档为准，API 可能演进
        return langfuse.get_prompt(name, label=self._label)

    def versions(self) -> dict[str, int]:
        """给 /version 用：报告当前使用的 prompt 版本号"""
        ...


SYSTEM_PROMPT = PromptRegistry()                   # 单例
prompt = SYSTEM_PROMPT.get("ops-agent-system")
messages = prompt.compile(tenant=tenant_name, tools=available_tool_names)
# 关键：把 prompt 版本写进 trace，否则事后无法归因
with langfuse.start_as_current_span(name="agent-run") as span:
    span.update_metadata({"prompt_version": prompt.version, "prompt_label": prompt.label})
```

**发布与回滚流程**（全部在 Langfuse 里操作，**不需要重新部署**）：

```text
1. 新 prompt 保存为 version = N+1，label = staging
2. staging 环境（PROMPT_LABEL=staging）跑评测子集 -> 达标
3. 把 label=production 从 version N 切到 N+1    ← 全量生效（秒级）
4. 观察 15 分钟指标（成功率/延迟/成本/投诉）
5. 出问题：把 label=production 切回 version N    ← 回滚（秒级）
```

**纪律**：能在 prompt 层修的问题就不要发版；反之，**任何 prompt 变更都必须能被这条流程回滚**——即 prompt 必须存在 Langfuse 里，不能硬编码进代码，否则回滚就退化成「重新部署」，要等 5 分钟。

**「prompt 也是代码」的具体要求**：

| 要求 | 做法 |
| --- | --- |
| 有 diff、有 review | prompt 变更走 PR（文本以文件形式在仓库维护），或 Langfuse 变更记录 + 双人确认 |
| 有测试 | 每条变更附评测子集 before/after 数字 |
| 有版本号 | 每次变更产生新 version，禁止「原地覆盖」 |
| 有署名 | 谁改的、为什么改、关联哪个 issue/事故 |
| 有回滚与审计 | label 切换或 Git revert；生产 prompt 变更记录是合规材料（尤其受监管行业） |

### 5.3 模型切换流程

```text
阶段 0：离线评测（不接触真实流量）——跑全量 golden（含 safety 套件），对比成功率 / p95 延迟 / 单请求成本
        硬门槛：安全类 pass rate 不得低于现役模型
阶段 1：影子流量（Shadow）——真实请求同时发给新旧模型，只记录新模型结果，不返回给用户
        目的：拿到「真实分布」下的表现（golden 集覆盖不到长尾）
        成本：约 2 倍 token 支出，只跑 1~3 天
        看什么：结果一致性率、工具调用合法率、超时率、成本分布
阶段 2：小流量金丝雀（1% → 5% → 20%）——按 tenant_id hash 分流，同一用户始终命中同一版本
        每档至少观察 30~60 分钟（跨过一个流量高峰更好）
阶段 3：全量 + 保留一键回滚——回滚 = 把流量权重切回旧模型 / 把 model env 改回旧值 + rollout
```

**金丝雀期间必须盯的指标**（衔接 [06 篇](06-Prometheus与Grafana监控告警.md)）：

| 指标 | 阈值（示例） | 含义 |
| --- | --- | --- |
| 任务成功率 `agent_task_success_rate` | 不低于现役 -2pt | 最核心：行为有没有变差 |
| 工具调用错误率 `agent_tool_error_rate` | ≤ 现役 × 1.2 | 新模型可能不遵守工具 schema |
| 格式/解析失败率 `agent_parse_error_rate` | ≤ 1% | 结构化输出能力变化 |
| p95 延迟 `agent_request_duration_seconds` | ≤ 现役 × 1.3 | 新模型可能更慢 |
| 单请求成本 `agent_cost_usd_per_request` | ≤ 现役 × 1.2 | 新模型可能更啰嗦 |
| 429/5xx 率 `agent_llm_errors_total` | ≤ 1% | 新供应商/新配额够不够 |
| **安全拦截数** / 用户显式负反馈 | 不低于现役 / 不高于现役 | 兜底信号（[05 篇](05-Agent安全评测与加固.md)） |

**分流实现**：Agent 场景优先按**用户/租户**分流，避免同一用户一会新一会旧（多轮对话体验灾难）：

```python
import hashlib


def pick_model(tenant_id: str, rollout_pct: int, new_model: str, old_model: str) -> str:
    """按 tenant_id 稳定分流：同一租户始终命中同一版本。"""
    bucket = int(hashlib.sha256(tenant_id.encode()).hexdigest()[:8], 16) % 100
    return new_model if bucket < rollout_pct else old_model
```

若用「两个 Deployment + Ingress 权重分流」，粒度是请求级随机，只适合无状态单轮任务。

### 5.4 发布前必须跑的评测集与通过标准

| 套件 | 内容 | 通过标准（示例，按业务调整） |
| --- | --- | --- |
| `core` | 30~50 条典型任务，端到端跑通 | pass_rate ≥ baseline − 2pt 且 ≥ 0.90 |
| `tool-calling` | 工具选择/参数正确性 | ≥ 0.95，且无「调用了不该调的工具」 |
| `safety` | 提示注入、越权工具、敏感信息（[05 篇](05-Agent安全评测与加固.md)） | ≥ 0.95 **硬底线，不可放宽** |
| `regression` | 历史事故的回归用例 | 100% 通过 |
| `perf` | 延迟与成本 | p95 ≤ baseline × 1.3，成本 ≤ × 1.2 |
| `long-task` | 长任务中断恢复（阶段 4 场景） | 恢复成功率 100%，无重复副作用 |

> 把**每一次线上事故都变成一条回归用例**，这个套件会越用越值钱。

## 六、降级与容灾

### 6.1 降级设计：五级阶梯

不要「要么全好要么全挂」，要设计**有损但可用**的中间态：

| 级别 | 触发条件 | 系统行为 | 用户感知 |
| --- | --- | --- | --- |
| L0 正常 | — | 全功能 | 正常 |
| L1 缩短超时 | LLM 延迟 p95 上升 | LLM 超时 60s → 20s，重试 2 → 0 | 回答略简单，偶尔「请重试」 |
| L2 换备用模型 | 主模型 429/5xx 率 > 10% | 自动切备用模型/供应商 | 质量略降，功能完整 |
| L3 返回缓存结果 | 上游全面不可用 | 返回相似问题的缓存结果，标注「可能不是最新」 | 拿到近似答案 |
| L4 排队而非失败 | 配额耗尽 | 请求入队 + 前端显示排队位置与预计时间 | 等待，但不报错 |
| L5 只读模式 | 依赖故障或成本告警 | 关闭写入类工具（改配置、重启服务），只保留查询 | 只能查不能做（安全优先） |

**为什么「排队」优于「失败」**：Agent 任务的用户预期本就偏长（几十秒到几分钟），排队 + 明确进度反馈远好于一个 429。前提是**队列要持久**（Postgres/Redis）且**任务提交后不依赖 HTTP 连接**（第三节的异步架构）。

```python
# app/degrade.py —— 降级决策集中在一处，便于测试与审计
from enum import IntEnum


class DegradeLevel(IntEnum):
    NORMAL = 0
    SHORT_TIMEOUT = 1
    FALLBACK_MODEL = 2
    CACHE_ONLY = 3
    QUEUE_ONLY = 4
    READ_ONLY = 5


def decide_level(*, llm_error_rate: float, llm_p95_seconds: float,
                 cost_ratio_of_budget: float, dependency_healthy: bool) -> DegradeLevel:
    if not dependency_healthy:
        return DegradeLevel.READ_ONLY
    if cost_ratio_of_budget >= 0.95:
        return DegradeLevel.QUEUE_ONLY
    if llm_error_rate >= 0.50:
        return DegradeLevel.CACHE_ONLY
    if llm_error_rate >= 0.10:
        return DegradeLevel.FALLBACK_MODEL
    if llm_p95_seconds >= 30:
        return DegradeLevel.SHORT_TIMEOUT
    return DegradeLevel.NORMAL
```

**降级必须可观测**：每次降级都打指标 + 日志，并在 06 篇的告警里留一条「降级持续 > 10 分钟」的规则——**静默降级 = 静默劣化**。

### 6.2 熔断与限流的上线参数

**熔断（Circuit Breaker）**：连续失败到阈值就「跳闸」，快速失败而不去撞墙。

| 参数 | 建议初值 | 理由 |
| --- | --- | --- |
| 统计窗口 | 30s 滚动 | 太短容易误跳，太长反应慢 |
| 最小请求数 | 20 | 低流量时不许跳闸（否则一个失败就 100%） |
| 错误率阈值 | 50% | 供应商抖动常见，50% 才是真故障 |
| 打开持续时间 | 30s | 供应商一般几十秒内恢复 |
| 半开试探 | 放行 3 个请求 | 恢复要验证，不能直接全放 |

```python
# 简化熔断（生产建议用成熟库，如 pybreaker / aiobreaker）
import time


class CircuitBreaker:
    def __init__(self, error_threshold=0.5, window=30.0, min_requests=20, open_seconds=30.0):
        self.error_threshold, self.window = error_threshold, window
        self.min_requests, self.open_seconds = min_requests, open_seconds
        self._results: list[tuple[float, bool]] = []
        self._opened_at: float | None = None

    def allow(self) -> bool:
        now = time.monotonic()
        if self._opened_at is not None:
            if now - self._opened_at < self.open_seconds:
                return False
            self._opened_at = None              # 进入半开，放行试探
        return True

    def record(self, ok: bool) -> None:
        now = time.monotonic()
        self._results = [(t, o) for t, o in self._results if now - t < self.window]
        self._results.append((now, ok))
        if len(self._results) >= self.min_requests:
            err = sum(1 for _, o in self._results if not o) / len(self._results)
            if err >= self.error_threshold:
                self._opened_at = now           # 跳闸
```

**限流三层**：**入口层**限每租户 QPS/并发（10 QPS、并发 5，按套餐分级）；**LLM 层**限全局 RPM/TPM（留 20% 余量：供应商给 1000 RPM，自己限 800）；**成本层**限每租户日/月 token 预算（超 80% 告警，超 100% 降级到排队）。**并发闸门最关键**：用信号量限制同时在途的 LLM 调用数，防止突发流量把配额打爆导致全员 429（雪崩）。

```python
LLM_CONCURRENCY = asyncio.Semaphore(int(os.getenv("LLM_MAX_CONCURRENCY", "20")))
```

### 6.3 多供应商容灾与配额隔离

```text
             ┌─ 主供应商（80% 流量，主力配额）
router ──────┼─ 备用供应商（20% 常态化流量；主供应商故障时接管）
             └─ 自建/本地小模型（最后兜底：只做分类、抽取等简单任务）
```

三条纪律：① **备用供应商要常态化跑小流量**（5%~20%）——从不使用的备用路径 = 故障那天才发现它不通（schema 不兼容、模型名已下线）；② **配额物理隔离**：prod / staging / CI 评测 / 开发用**不同 key 与不同配额**，否则一次 CI 全量评测就能把生产配额打光（极常见事故）；③ **抽象层要薄**：用 OpenAI 兼容层或自己一层薄适配，别把供应商特有参数散落在业务代码里，否则切换时要改几十处。

```python
# app/llm.py —— 统一 LLM 工厂：多供应商 + 分层降级
from dataclasses import dataclass
from langchain_openai import ChatOpenAI


@dataclass(frozen=True)
class ModelTarget:
    name: str
    api_key_env: str
    timeout: float
    base_url: str | None = None
    weight: int = 100


def build_llm(target: ModelTarget, *, max_retries: int = 2) -> ChatOpenAI:
    return ChatOpenAI(model=target.name, base_url=target.base_url,
                      api_key=os.environ[target.api_key_env],
                      timeout=target.timeout, max_retries=max_retries)
```

### 6.4 数据层容灾

| 数据 | 风险 | 对策 |
| --- | --- | --- |
| Checkpoint（Postgres） | 库挂 → 长任务卡死、无法恢复 | 主从/托管多可用区 + PITR；**定期演练从备份恢复**；应用侧断连时进 L4 排队而非报错 |
| 审计日志 / 审批记录 | 「写过就算数」，不能丢 | 与业务库分离或单独表 + WAL 归档；**只追加不修改**；导出对象存储做冷备 |
| 评测数据集与基线 | 丢了无法判断回归 | 数据集与基线 json 进 Git；报告进 artifact + 对象存储 |
| Prompt（Langfuse） | 服务挂 → 拉不到 prompt | 本地 TTL 缓存 + **兜底常量**（拉不到时用上一版缓存，绝不因 prompt 拉取失败导致全站不可用） |
| 镜像 | registry 挂 → 拉不到 | 多 registry 或节点镜像缓存，配合 `imagePullPolicy` |

**审计日志「不丢」的具体做法**：写入操作（工具执行、审批、配置变更）**先落库再执行**，并把 `request_id`/`thread_id` 一起写；异步导出冷备；监控「写入速率是否为 0」（写速率为 0 往往意味着静默失败，而不是真没流量）。

### 6.5 混沌演练

**每年至少一次**，每次一个故障、一次复盘，在预发或生产小流量窗口做，且有明确止损开关。

| # | 故障注入 | 期望行为 | 验证方式 |
| --- | --- | --- | --- |
| 1 | 主 LLM 100% 返回 500 | 熔断打开 → 10s 内切备用，成功率 ≥90% | `agent_llm_fallback_total` 上升、成功率曲线稳定 |
| 2 | LLM 延迟全部 +30s | L1 降级：缩短超时快速失败；readiness 正常；**Pod 不被重启** | `kubectl get pods` 的 RESTARTS 计数**不变**（证明 liveness 没误杀） |
| 3 | 主模型持续 429 十分钟 | 进入 L4 排队，前端显示排队；成本不超预算 | 队列深度与 `agent_queue_wait_seconds` 上升，用户侧无 5xx |
| 4 | Postgres 主库不可用 2 分钟 | API 层 readiness 失败摘流量；长任务进排队；恢复后自动续跑 | `/readyz` 返回 503；恢复后 `get_state` 能查到原任务并续跑 |
| 5 | 杀掉一个 API Pod | 端点摘除 → 在途请求完成 → 用户零感知 | 客户端错误率曲线是否出现尖峰；grace 时间是否足够 |
| 6 | 杀掉正在跑长任务的 worker | 任务重投递，**不重复执行副作用** | 审计日志里同一 `request_id` 只有一条副作用记录 |
| 7 | 成本突增（放大 token 上限、模拟失控循环） | 80% 预算告警触发；100% 时降级到 L4 | 告警是否收到；降级是否真的生效 |
| 8 | Prompt 服务不可用 | 走本地缓存/兜底 prompt，服务不中断 | 成功率不下降；日志出现 `prompt_fetch_failed` 警告 |
| 9 | 节点维护驱逐（`kubectl drain`） | PDB 生效，始终保持 ≥2 副本 | `kubectl get pdb` 的 ALLOWED DISRUPTIONS 变化，期间无 5xx |

演练后**必产出物**：一份「发现的问题 + 修复项 + 新增的告警/回归用例」清单。没产出修复项的演练等于没做。

### 6.6 故障场景 → 期望行为 → 验证方式（速查表）

| 故障 | 期望行为 | 验证方式 |
| --- | --- | --- |
| 上游 LLM 5xx | 重试 → 熔断 → 切备用 | 备用调用计数 + 成功率 |
| 上游 LLM 429（配额） | 排队 + 退避，不对用户报错 | 队列指标 + 429 计数 |
| LLM 变慢 | 缩短超时、降级到小模型 | p95 延迟 + 降级指标 |
| DB 不可用 | readiness 失败摘流量；读走缓存 | `/readyz` 状态 + 端点数 |
| 单 Pod 崩溃 / 单节点故障 | 重启 + 端点自动摘除；多副本 + 拓扑分散容量不掉 | 客户端错误率 + 副本数 + PDB |
| 成本超预算 | 告警 → 限流 → 排队降级 | 预算指标 + 降级日志 |
| 错误 prompt 发布 | 秒级 label 回滚 | `/version` 的 prompt 版本 + 恢复耗时 |
| 新模型版本变差 | 金丝雀超阈值 → 自动/手动回滚 | 金丝雀指标对比 + 回滚耗时 |
| 镜像有高危漏洞 | CI 门禁拦截，不进 registry | Trivy 步骤结果 |

## 七、上线检查清单

### 7.1 Checklist

**配置与密钥**

- [ ] 所有密钥来自 Secret/密钥服务；`.env` 在 `.dockerignore` 里；`git log -S<key前缀>` 查历史无泄露；
- [ ] 代码无硬编码 key/base_url（`gitleaks` 或 ruff 规则扫描）；
- [ ] 配置缺失时**启动即失败**（Pydantic Settings + fail fast）；
- [ ] 生产/staging/评测/开发**四套独立 key 与配额**；
- [ ] 密钥轮换流程已文档化（改 Secret → `rollout restart`）。

**健康检查**

- [ ] `/healthz`（liveness）零 I/O，`/readyz`（readiness）反映真实可服务状态；
- [ ] `startupProbe` 阈值覆盖最慢冷启动（有实测数据）；
- [ ] `livenessProbe` **绝不调用 LLM**；长请求压测下 RESTARTS 保持 0；
- [ ] `terminationGracePeriodSeconds` > preStop + 最长在途请求（写出式子并核对）。

**评测门禁**

- [ ] CI 跑 golden 子集（core/tool-calling/safety）并与基线对比；
- [ ] 有**硬底线**（安全类）与**回归容差**（相对基线）两类阈值；
- [ ] 采样 seed 固定，报告作为 artifact 留存；
- [ ] 历史事故都已变成回归用例。

**观测接入**

- [ ] trace 上报到 Langfuse/LangSmith（[03 篇](03-Langfuse与LangSmith可观测性.md)），`trace_id` 打进日志；
- [ ] `/metrics` 暴露且被 Prometheus 抓到（[06 篇](06-Prometheus与Grafana监控告警.md)）；
- [ ] OTel Collector 做了采样与 PII 脱敏（[04](04-OpenTelemetry与自定义Tracing.md)/[05 篇](05-Agent安全评测与加固.md)）；
- [ ] `/version` 能回答「线上是哪个 commit + 哪个 prompt 版本 + 哪个模型」。

**告警规则**

- [ ] 成功率、p95 延迟、LLM 错误率、成本、队列深度五类告警已配；
- [ ] 每条告警有 runbook 链接（先看什么、怎么回滚）；
- [ ] 阈值经压测/历史数据校准，无「上线即风暴」。

**容量与成本**

- [ ] requests/limits 由压测得出；OOMKilled 已排除；
- [ ] `maxReplicas × 单副本并发` 不超过供应商配额；
- [ ] 有请求级 token 预算、`AGENT_MAX_STEPS`、租户日成本上限；
- [ ] 成本 80% 告警 / 100% 降级，行为已演练。

**回滚方案**

- [ ] 镜像标签 = commit sha，`kubectl rollout undo` 可用且有 `revisionHistoryLimit`；
- [ ] prompt 回滚是「label 切换」（秒级），已演练；
- [ ] 模型回滚是改 env/权重 + rollout，已演练；
- [ ] **回滚耗时已实测并记录**（目标 < 5 分钟）。

**值班与演练**

- [ ] 有 on-call 与升级路径；关键告警有人接；
- [ ] 每类故障有 runbook；
- [ ] 今年已做（或已排期）至少一次混沌演练；
- [ ] 事故复盘产出会变成回归用例或告警。

### 7.2 面试讲得清的问题

| 问题 | 回答要点（结论 + 代价） |
| --- | --- |
| 为什么多阶段构建？ | builder 不进最终镜像，体积小、漏洞面小、拉取快；代价：Dockerfile 更复杂，调试多一步 |
| 为什么慢 LLM 请求用 readiness 而非 liveness？ | liveness 失败会**重启容器、杀掉在途请求**（还白烧 token）；readiness 只摘流量，让在途请求自然完成；代价：要 draining 状态 + preStop 时序配合 |
| 为什么不按 CPU 扩容？ | LLM 场景瓶颈是**等 I/O 与供应商配额**，CPU 上不去；要用队列深度等自定义指标；代价：需 Prometheus Adapter + 业务指标 |
| 长任务怎么处理？ | 请求只受理返回 `task_id`，worker 异步执行 + Checkpoint 恢复；代价：架构复杂、要幂等、前端要轮询 |
| 为什么 Checkpoint 必须放外部 Postgres？ | 多副本下内存态/本地文件无法共享；代价：多一个依赖，要管连接池与清理 |
| 为什么 prompt 变更要单独一套流程？ | 不可静态验证、影响全域、无编译错误；用评测门禁 + label 秒级回滚；代价：评测有成本与方差，要维护基线与容差 |
| 模型切换为什么先影子流量？ | golden 集覆盖不到真实长尾，影子能在零用户风险下拿真实分布表现；代价：1~3 天双倍 token 成本 |
| 怎么保证不乱花钱？ | 请求级 token 预算 + 步数上限 + 租户日预算 + 成本告警 + 超预算降级排队；代价：限流可能误伤正常用户，要调阈值 |
| 回滚要多久？ | 代码 `rollout undo` 分钟级；prompt label 切换秒级；模型改权重 + rollout 分钟级——都实测过；代价：要保留旧镜像与旧 prompt 版本 |
| 多副本怎么防重复副作用？ | 幂等键（`request_id`/`thread_id`）+ 外呼去重 + 副作用后置；代价：外部系统必须支持幂等键 |

## 八、踩坑点（汇总）

| # | 坑 | 后果 | 正确做法 |
| --- | --- | --- | --- |
| 1 | key 写进 Dockerfile / 提交进 Git | 永久泄露，删了也在历史里 | Secret 注入 + `.dockerignore` + `gitleaks` 扫描 + **泄露即轮换** |
| 2 | 镜像巨大（2 GB+）导致冷启动慢 | 滚动更新慢、HPA 扩容不及时、节点磁盘压力 | 多阶段 + `-slim` + 只 COPY 必要文件，并实测冷启动 |
| 3 | liveness 探针调用 LLM 或做重查询 | 慢请求期间容器被反复重启，用户 502，token 白烧 | liveness 只回 200；业务健康交给指标与 readiness |
| 4 | 多副本用内存/本地文件 Checkpoint | 请求落到别的 Pod 就「任务不存在」 | `PostgresSaver` + 外部 Postgres |
| 5 | 扩容后 Postgres 连接被打满 | 「一扩容就全站报错」 | `副本数 × 池大小 < max_connections`，或用 PgBouncer |
| 6 | CI 里跑真实 LLM 测试 | 方差大、慢、烧钱、偶发限流导致随机失败 | 单元测试全 mock；评测用小样本 + 固定 seed + 最多一次重试 + 独立配额 |
| 7 | 没有回滚方案就上线 | 出事只能「赶紧修」，修复时间 = 事故时长 | sha 标签 + `rollout undo` + prompt label 回滚，**且演练过** |
| 8 | 本地 compose 能跑，生产就崩 | 时区差 8 小时、编码报错、依赖版本不一致 | 显式 `TZ`+`tzdata`、`PYTHONUTF8=1`、锁文件构建、基础镜像与本地 Python 版本一致 |
| 9 | `depends_on` 没写 `condition: service_healthy` | 应用先于 DB 起来，启动即崩 | 健康条件 + entrypoint 里重试等待 |
| 10 | entrypoint 没 `exec` | SIGTERM 到不了 Python，优雅关闭失效 | `exec "$@"`，并用 `docker stop` 实测验证 |
| 11 | 长任务塞进同步 HTTP 请求 | 网关超时、用户重复提交、重复执行 | 受理即返回 + 队列 + `task_id` 查询 |
| 12 | 门禁只跑「全绿就上线」，无基线对比 | 行为静默退化，几个月后才发现 | 与基线对比 + 硬底线 + 报告留档 |
| 13 | 生产与 CI 共用 API key | CI 全量评测把生产配额打光 → 线上 429 | 配额物理隔离 |
| 14 | 用 `latest` 标签部署 | 无法确认线上版本、回滚即赌博 | 只用 `sha-<commit>` 或直接 `@digest` |
| 15 | 降级静默发生 | 用户被降级体验但没人知道 | 降级打指标 + 「降级持续 > 10 分钟」告警 |

## 学习自检与练习

### 练习 1：给阶段 3 项目写出 Dockerfile 并瘦身

**任务**：为阶段 3「企业运维分析 Agent」（FastAPI + LangChain + 若干运维工具）写出生产级 `Dockerfile` 与 `.dockerignore`：① 多阶段构建，builder 只装依赖；② 非 root 运行；③ `PYTHONUNBUFFERED=1`；④ 带 `HEALTHCHECK`；⑤ 记录**瘦身前后的镜像体积**与**依赖层缓存命中情况**（改一行业务代码后重新 build，看是否重装依赖）。

**提示**：先写「反例版」（`COPY . .` + `pip install -r requirements.txt` + `USER root`）量出体积，再改造成多阶段版对比。参考 2.1~2.3。

**验收标准**：最终镜像减幅 ≥ 30%；`docker run --rm img whoami` 不是 `root`；改业务代码后重建**不重新下载依赖**；`docker run --rm img sh -c 'ls -a /app'` 看不到 `.env`、`.git`、`tests`。

### 练习 2：把评测子集接进 CI 门禁

**任务**：基于 [01](01-评测方法论与GoldenDataset设计.md)/[02 篇](02-评测指标详解与实现.md) 的 golden 数据集做一条能真正拦住回归的门禁：① 抽 25 条组成 `ci-subset`（覆盖正常任务、工具调用、1 条安全用例）；② 写 `evals/baselines/core.json` 记录当前 pass_rate / p95 / cost；③ 实现 `evals/run_gate.py`（参考 4.3）并作为 `eval-gate` job 运行；④ **验证它真能拦住**——故意删掉系统 prompt 里「必须先确认再执行写操作」一句，确认 CI 变红；⑤ 前后各留一份 report 对比。

**提示**：方差是最大陷阱。先用同一版本连跑 3 次观察 pass_rate 波动范围，把 `--tolerance` 设在波动之上；若波动很大，关键用例改成多次采样取多数。

**验收标准**：正常版本绿灯；改坏 prompt 后红灯且报告**指名失败的 case id**；门禁耗时 < 6 分钟、成本 < 1 元；报告可下载（`retention-days` ≥ 7）。

### 练习 3：写出金丝雀发布方案（含回滚判据）

**任务**：为一个「把 `gpt-4o-mini` 换成新版本模型」的变更写完整发布方案，必须包含：① 影子阶段（怎么双发、跑多久、看什么、成本预算）；② 金丝雀档位（按 `tenant_id` hash 分流，1% → 5% → 20% → 100%，每档观察时长）；③ **自动回滚判据**，写成可执行的 PromQL 或脚本条件，至少 3 条；④ 若改用「两个 Deployment + Ingress 权重分流」，说明缺点并给替代方案；⑤ 回滚的具体命令与预计耗时。

**提示**：判据要考虑噪声——用「连续 N 个窗口都超阈值」才触发，避免抖动导致误回滚。参考 5.3 与 6.2。

**验收标准**：判据可执行不是「观察一下」；能回答「新模型只是慢 20% 但质量更好，要不要回滚」（有明确决策规则）；方案含**分流一致性**说明。

### 练习 4（选做）：写一条混沌演练脚本

**任务**：选 6.5 表的故障 #5（杀掉一个 API Pod），写可执行脚本：① 演练前记录基线（成功率、错误率、副本数）；② 注入故障（随机挑一个 Pod `kubectl delete`）；③ 演练中持续采样指标，输出「用户可见错误数」；④ 演练后自动对比基线并给出结论。

**提示**：用 `kubectl get pods -o jsonpath` 取 Pod 名；指标从 `/metrics` 或 Prometheus HTTP API 拉；脚本要有 `--dry-run`。

**验收标准**：跑完能明确回答「这次 Pod 重启对用户是否零影响」，并给出 RESTARTS 计数与错误率数字。

### 自检清单

- [ ] 能说出 Agent 服务相比普通 Web 服务的 7 类特殊挑战及对策；
- [ ] 能默写多阶段 `Dockerfile` 的关键结构，并解释「先 COPY 依赖清单」为什么能加速构建；
- [ ] 知道 `.dockerignore` 该排除什么，尤其是密钥文件；
- [ ] 能一句话说清 startup / readiness / liveness 的区别，并解释「为什么慢 LLM 请求必须用 readiness」；
- [ ] 能写出 Deployment 的关键字段（探针、resources、strategy、优雅终止）并说明取值理由；
- [ ] 知道 Checkpoint 为什么必须放外部 Postgres，以及连接池与副本数的关系；
- [ ] 能设计一条含评测门禁的 GitHub Actions 流水线，并说清硬底线与容差两类阈值的差别；
- [ ] 知道镜像标签为什么用 commit sha，以及 prompt / 模型 / 代码三种回滚各自的粒度与耗时；
- [ ] 能设计五级降级阶梯，并说明「排队优于失败」的理由；
- [ ] 能列出一张混沌演练表，且知道演练必须产出修复项；
- [ ] 记得住第八节的坑，尤其是「key 进镜像」「liveness 打死慢请求」「CI 跑真实 LLM 不稳定」。

## 参考资料

**Docker**

- Docker 官方文档 - 构建最佳实践（分层、缓存、`.dockerignore`）: https://docs.docker.com/build/building/best-practices/
- Docker 官方文档 - 多阶段构建: https://docs.docker.com/build/building/multi-stage/
- Docker 官方文档 - Dockerfile 参考（`HEALTHCHECK`/`STOPSIGNAL`/`ENTRYPOINT`）: https://docs.docker.com/reference/dockerfile/
- Docker 官方文档 - 构建缓存垃圾回收: https://docs.docker.com/build/cache/garbage-collection/
- Docker 官方文档 - Compose 启动与停止顺序（`depends_on` 健康条件）: https://docs.docker.com/compose/how-tos/startup-order/
- Docker 官方文档 - Compose 服务参考: https://docs.docker.com/reference/compose-file/services/

**Kubernetes**

- Kubernetes 官方文档 - 配置存活、就绪与启动探针: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
- Kubernetes 官方文档 - 管理容器资源（requests/limits）: https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/
- Kubernetes 官方文档 - ConfigMap: https://kubernetes.io/docs/concepts/configuration/configmap/
- Kubernetes 官方文档 - Secret: https://kubernetes.io/docs/concepts/configuration/secret/
- Kubernetes 官方文档 - Secret 良好实践: https://kubernetes.io/docs/concepts/security/secrets-good-practices/
- Kubernetes 官方文档 - HorizontalPodAutoscaler 演练: https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale-walkthrough/
- Kubernetes 官方文档 - Pod 生命周期（终止流程）: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
- Kubernetes 官方文档 - 执行滚动更新: https://kubernetes.io/docs/tutorials/kubernetes-basics/update/update-intro/
- Kubernetes 官方文档 - 配置 PodDisruptionBudget: https://kubernetes.io/docs/tasks/run-application/configure-pdb/

**CI/CD**

- GitHub Actions 官方文档 - 构建与测试 Python: https://docs.github.com/en/actions/tutorials/build-and-test-code/python
- GitHub Actions 官方文档 - 发布 Docker 镜像: https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images
- GitHub Actions 官方文档 - 管理部署环境（审批人、保护规则）: https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments
- GitHub Actions 官方文档 - 缓存依赖以加速工作流: https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows

**发布策略、安全与观测**

- Google Cloud 官方文档 - 部署策略（滚动/金丝雀/蓝绿）: https://docs.cloud.google.com/deploy/docs/deployment-strategies
- Trivy 官方网站（镜像漏洞扫描）: https://trivy.dev/
- Trivy 源码仓库: https://github.com/aquasecurity/trivy
- OpenTelemetry 官方文档 - Kubernetes 上安装 Collector: https://opentelemetry.io/docs/collector/install/kubernetes/
- OpenTelemetry 官方文档 - Kubernetes 入门: https://opentelemetry.io/docs/platforms/kubernetes/getting-started/
- Prometheus 官方文档 - 告警规则: https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/

**依赖栈与配套**

- FastAPI 官方文档 - 服务器工作进程（Uvicorn workers 与部署）: https://fastapi.tiangolo.com/deployment/server-workers/
- Langfuse 官方文档 - 自托管 Docker Compose 部署: https://langfuse.com/self-hosting/deployment/docker-compose
- LangChain 官方文档 - LangGraph Persistence（Checkpointer）: https://docs.langchain.com/oss/python/langgraph/persistence
- 阶段 5 配套：[01 篇](01-评测方法论与GoldenDataset设计.md)（Golden Dataset）、[02 篇](02-评测指标详解与实现.md)（指标与评测实现）、[03 篇](03-Langfuse与LangSmith可观测性.md)（prompt 版本与 label）、[04 篇](04-OpenTelemetry与自定义Tracing.md)（OTel 与 trace 关联）、[05 篇](05-Agent安全评测与加固.md)（安全门禁与脱敏）、[06 篇](06-Prometheus与Grafana监控告警.md)（指标与告警）、[08 篇](08-阶段5综合实践-全链路观测与评测报告.md)（综合实践）
- 前序阶段：[阶段 4-05 Checkpoint 持久化与长任务恢复](../阶段4-复杂工作流与Deep-Agents/05-Checkpoint持久化与长任务恢复.md)、[阶段 4-07 事件驱动工作流与异步长任务](../阶段4-复杂工作流与Deep-Agents/07-Event-driven-Workflow与异步长任务.md)、[阶段 3-02 工具调用工程化](../阶段3-Tools与MCP/02-工具调用工程化-校验超时重试降级审计.md)
