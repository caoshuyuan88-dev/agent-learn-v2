# Event-driven Workflow 与异步长任务

> 本文定位：阶段 4 的长任务（研发效能 Agent 一次跑几分钟）不能阻塞 HTTP 请求；外部系统（GitLab CI 结果、Jira 状态变更、人工审批）的事件要能**唤醒**任务继续跑。本文讲清楚三件事：LangGraph 的异步 API（`ainvoke`/`astream`/`astream_events`）与流式输出、**外部事件驱动的恢复**（webhook → 队列 → 用同一 thread_id 续跑）、以及「事件驱动 Agent」的概念（Agent 让出控制权等事件）。读完本文，你能把「异步提交任务 → 查进度 → 外部事件唤醒 → 继续 → 回调结果」的生产闭环搭出来。前置：[04 篇](04-Human-in-the-loop-interrupt与人工审批.md)（审批超时自动降级）、[05 篇](05-Checkpoint持久化与长任务恢复.md)（Checkpoint 恢复）。LangGraph 的事件驱动能力较新，**以官方文档为准**。

## 学习目标

学完本文，你应该能：

- 说清「长任务为什么不能同步跑 HTTP」以及三种解法（异步流式 / 轮询 / 事件驱动）；
- 用 `astream` / `astream_events` 消费图的执行过程（SSE 推送给前端）；
- 实现「外部 webhook → 队列 → 用同一 thread_id 恢复任务」的事件驱动模式；
- 用 `update_state` 把外部事件（CI 结果、审批结果）注入状态后继续执行；
- 解释「事件驱动 Agent」与「interrupt 等人」的差别；
- 搭出「提交任务 / 查进度 / 回调结果」的生产化异步架构（队列 + worker + 状态 API）。

## 一、问题：长任务不能同步阻塞

### 1.1 场景

用户提交「分析这个需求并生成完整研发报告」——任务要调多个 Agent、读代码库、等人审，**耗时 1~10 分钟**。而：

- HTTP 请求有超时（网关通常 30~60s），同步等 10 分钟 = 必然超时；
- 用户不想干等，要能查进度、收结果。

### 1.2 三种解法

| 解法 | 做法 | 适用 |
| --- | --- | --- |
| 异步流式（SSE/WebSocket） | 任务边跑边推流，前端持续接收 | 任务 < 1 分钟、需要实时观感 |
| 轮询状态 API | 提交 → 后台跑 → 前端轮询查进度 | 简单、通用 |
| 事件驱动（webhook/队列） | 外部事件（CI 完成、人审完成）唤醒任务继续 | 任务要等外部系统、跨进程、长周期 |

生产上经常**组合**：提交走 API，执行走后台 worker，进度走轮询/SSE，完成走回调 webhook，外部事件走队列唤醒。

类比 Java：同步接口像「同步 HTTP 调用」，SSE 像「响应流式返回」，队列 + worker 像「MQ + 消费组」，事件驱动像「MQ 消息触发状态机迁移」。**你熟悉的分布式系统思路，在 Agent 世界里原样复用**。

## 二、LangGraph 异步 API

### 2.1 ainvoke 与 astream

```python
# 异步调用（不阻塞事件循环）
result = await app.ainvoke(initial_state, config=config)

# 流式执行：每次产出一步的增量
async for chunk in app.astream(initial_state, config=config, stream_mode="updates"):
    for node_name, update in chunk.items():
        print(f"[{node_name}] {update}")
```

`stream_mode` 常用值（以官方文档为准）：

- `"updates"`：每个节点返回的更新 dict（步骤粒度）；
- `"values"`：每一步后的完整 State（快照）；
- `"messages"`：LLM 生成的每条消息（token 级流式，配合 SSE 打字机效果）。

### 2.2 astream_events：细粒度事件

`astream_events` 发出所有运行事件（模型开始/结束、工具调用、节点完成……），按 `event` 类型过滤：

```python
async for event in app.astream_events(initial_state, config=config, version="v2"):
    kind = event["event"]
    if kind == "on_chat_model_stream":
        token = event["data"]["chunk"].content
        # 把 token 推给前端（SSE），实现打字机效果
    elif kind == "on_tool_start":
        print("工具开始调用：", event["name"])
```

（以你锁定的依赖版本文档为准，`version="v2"` 是当前主流。）

### 2.3 FastAPI + SSE 示例

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import json

app_fastapi = FastAPI()

@app_fastapi.post("/chat")
async def chat(request: dict):
    config = {"configurable": {"thread_id": request["thread_id"]}}

    async def event_stream():
        async for chunk in graph_app.astream(
            {"messages": [HumanMessage(content=request["message"])]},
            config=config, stream_mode="messages"):
            msg = chunk[0]
            if msg.content:
                yield f"data: {json.dumps({'token': msg.content}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

前端用 `EventSource` 或 fetch stream 消费。这是阶段 1 练过的 SSE，这里升级成「图的实时执行流」。

## 三、外部事件驱动的恢复

### 3.1 场景

研发效能 Agent 走到「等待 CI 测试结果」：图先暂停（或执行到等待点），**CI 完成后由 webhook 通知系统**，系统唤醒图继续执行。

### 3.2 核心机制：Checkpoint + 同一 thread_id + update_state 注入

第 05 篇讲过：同一 `thread_id` 再次触发 = 从 Checkpoint 继续。事件驱动的本质就是：**外部事件到达 → 用事件的 thread_id 注入状态并触发恢复**。

```python
# 外部事件处理器（如 GitLab webhook 回调）
async def on_ci_completed(payload: dict):
    thread_id = payload["task_id"]          # webhook 里带回的任务 id
    config = {"configurable": {"thread_id": thread_id}}

    # 1. 检查任务是否还在等 CI 结果
    state = graph_app.get_state(config)
    if "wait_ci" not in (state.next or ()):
        return                               # 不在等待点，忽略（幂等）

    # 2. 把 CI 结果注入状态（假装 wait_ci 节点返回了这个值）
    graph_app.update_state(config, {
        "ci_result": {"passed": payload["passed"], "duration_s": payload["duration_s"]},
    }, as_node="wait_ci")

    # 3. 触发恢复：继续执行后续节点
    graph_app.invoke(Command(resume=True), config=config)
```

流程串起来：

```text
用户提交任务（task_id=T1）
  -> worker 跑图：... -> wait_ci 节点（把"等 CI"写进状态，任务进入等待）
  -> 任务"暂停"（其实已结束，等外部触发）
GitLab CI 跑完 -> webhook(T1, passed=true)
  -> on_ci_completed: update_state 注入 ci_result -> invoke 恢复
  -> 图从 wait_ci 之后继续：生成报告 -> 回调结果 webhook
```

关键点：

- **「暂停」不是 interrupt**：这里图是**正常跑完**（跑到等待点就结束当前调用），等待状态存在 State 里，靠外部事件唤醒——这是「事件驱动」与「interrupt 等人」的本质区别；
- **幂等**：事件可能重复投递（webhook 重试），处理器必须检查「是否还在等待点」（上面的 `state.next` 判断）；
- **唤醒 = 同一 thread_id 重新 invoke**：Checkpoint 保证从正确位置继续。

### 3.3 与 interrupt 的区别

| 维度 | interrupt（04 篇） | 事件驱动（本篇） |
| --- | --- | --- |
| 等待谁 | 人等（审批者） | 系统/外部系统（CI、Jira、定时器） |
| 暂停方式 | 执行中挂起（State 停在暂停点） | 执行结束，等待状态在 State 里 |
| 恢复方式 | `Command(resume=值)` | 外部事件触发 update_state + invoke |
| 典型场景 | 人工审批 | CI 结果、消息队列、定时任务 |

生产里两者常组合：**人工审批用 interrupt 暂停；审批结果由事件驱动（审批系统 webhook）触发恢复**（04 篇 6 节 + 本篇 3.2）。

## 四、事件驱动 Agent：Agent 让出控制权

### 4.1 概念

「事件驱动 Agent」是 LangGraph 1.x 的较新能力（以官方文档为准）：**Agent 在节点内主动等待外部事件（`await_next_event` 类 API），事件到达后继续执行**——不是「跑完等唤醒」，而是「真正挂起等事件」。

```python
# 概念示例（以官方文档为准，API 可能不同）
async def wait_for_event(state) -> dict:
    event = await graph.await_next_event()   # 挂起，等外部事件
    return {"event_data": event}
```

### 4.2 适用场景

- **Agent 间通信**（A2A）：Agent A 等 Agent B 的结果；
- **外部系统长流程**：等 CI、等部署、等审批系统回调；
- **人工介入**：等用户在界面上做选择（比轮询优雅）。

### 4.3 学习建议

事件驱动 Agent 的 API 还在演进，**现阶段以理解概念为主**，实现优先用 3.2 的「Checkpoint + 外部触发」模式（稳定、可控、跨进程）。等阶段 5 接触 LangSmith/Langfuse 和生产化时，再按官方最新文档深挖事件驱动 API。

## 五、生产架构：队列 + Worker + 状态 API

### 5.1 完整架构

```text
┌────────────┐  POST /tasks   ┌────────────────────────────┐
│   前端/CLI  │ ─────────────▶ │         FastAPI 网关        │
└────────────┘                │  /tasks      提交任务       │
       ▲                      │  /tasks/{id} 查进度        │
       │  SSE/轮询             │  /tasks/{id}/result 结果   │
       │                      └───────────┬────────────────┘
       │                                  │ 投递任务
       │                      ┌───────────▼────────────────┐
       │                      │     任务队列（Redis/Celery） │
       │                      └───────────┬────────────────┘
       │                                  │ worker 消费
       │                      ┌───────────▼────────────────┐
       │                      │   Worker（跑 LangGraph 图）  │
       │                      │  thread_id = task_id        │
       │                      │  Checkpoint: PostgreSQL      │
       └──────────────────────┴───────────┬────────────────┘
                                          │ 完成回调
                                ┌─────────▼─────────┐
                                │  结果存储 + 回调    │
                                │  结果 webhook      │
                                └───────────────────┘
```

### 5.2 组件职责

| 组件 | 职责 | 关键点 |
| --- | --- | --- |
| FastAPI 网关 | 提交任务、查状态、收结果 | 不跑图，只做调度和查询 |
| 任务队列 | 解耦提交与执行、限流、重试投递 | Redis Stream / RabbitMQ / Celery |
| Worker | 消费队列，用 `thread_id=task_id` 跑图 | Checkpoint 落 Postgres，崩溃可恢复（05 篇） |
| 状态存储 | 任务状态、Checkpoint | `get_state` 查进度（05 篇 4.1） |
| 事件消费者 | 处理外部 webhook，注入事件唤醒任务 | 幂等检查（3.2） |
| 结果回调 | 任务完成后通知调用方 | webhook / 轮询结果 API |

### 5.3 实现要点

```python
# 提交任务（网关层）
@app.post("/tasks")
async def submit_task(req: TaskRequest):
    task_id = str(uuid4())
    await queue.publish({"task_id": task_id, "input": req.model_dump()})
    return {"task_id": task_id, "status": "queued"}

# Worker 消费（后台进程）
async def worker_loop():
    async for msg in queue.consume():
        task_id = msg["task_id"]
        config = {"configurable": {"thread_id": task_id}}
        result = await graph_app.ainvoke(msg["input"], config=config)
        await store_results(task_id, result)
        await notify_callback(task_id)   # 结果回调
```

- **队列消费要幂等**：worker 崩溃后消息重投，同一 `task_id` 从 Checkpoint 继续，不重复跑（05 篇 5.3 的幂等设计）；
- **并发控制**：多个 worker 处理不同 task_id，天然并行；同一 task 不会被两个 worker 同时处理（靠队列 ack 机制）；
- **进度 API**：`app.get_state(config)` 的 `next` 字段 + 自定义进度字段，供前端轮询。

## 六、与 Checkpoint 结合：Durable Execution

把 05 篇（持久化）+ 04 篇（人审）+ 本篇（事件）合起来，就是 **Durable Execution**（耐久执行）：

| 能力 | 组件 | 效果 |
| --- | --- | --- |
| 状态持久化 | Checkpoint（Postgres） | 崩溃重启不丢进度 |
| 外部触发 | webhook + 队列 | 等外部事件不阻塞 |
| 人工介入 | interrupt + 事件恢复 | 人审通过后自动继续 |
| 失败处理 | RetryPolicy + 幂等 | 自动重试、不重复副作用 |
| 超时兜底 | 外部调度 + update_state | 审批/事件超时自动降级（04 篇 6 节） |

一句话：**Checkpoint 提供「记忆」，事件提供「唤醒」，队列提供「调度」，幂等提供「安全」**——四者齐了，Agent 任务才能像数据库事务一样可靠。

## 学习自检与练习

### 练习 1：astream 消费

用 `create_react_agent` + `astream(..., stream_mode="messages")` 跑一轮问答，打印模型逐 token 输出。再改用 `stream_mode="updates"` 打印节点级增量，对比两种粒度。

自检：`"messages"` 模式和 `"updates"` 模式分别适合什么前端场景？（提示：2.1）

### 练习 2：外部事件唤醒

实现 3.2 的 `on_ci_completed`：图里加一个 `wait_ci` 节点（把 `ci_result` 写默认值），先 invoke 到该节点；然后模拟 webhook 调用 `on_ci_completed`（用假的 payload），验证图从 `wait_ci` 之后继续执行并拿到 `ci_result`。

自检：如果 webhook 重复投递（`on_ci_completed` 被调用两次），第二次会发生什么？`state.next` 的判断如何防止重复处理？

### 练习 3：提交/查进度/收结果闭环

用 5.3 的结构搭一个最小闭环（队列可以用 `asyncio.Queue` 模拟）：提交任务 → worker 后台跑（含一次 `interrupt` 暂停）→ 查进度 → 模拟审批恢复 → 收结果。跑通并记录每个环节的调用。

自检：worker 进程崩溃后重启，任务能继续吗？靠什么？（提示：05 篇 Checkpoint + 同一 thread_id）

### 自检清单

- [ ] 能说清「长任务为什么不能同步 HTTP」以及三种解法；
- [ ] 会用 `ainvoke` / `astream` / `astream_events` 消费图执行过程；
- [ ] 能实现「webhook → update_state 注入 → 同一 thread_id 恢复」的事件驱动模式；
- [ ] 能说清事件驱动与 interrupt 的差别，以及它们如何组合；
- [ ] 能画出「网关 + 队列 + worker + 状态存储 + 回调」的生产架构；
- [ ] 能解释 Durable Execution = Checkpoint（记忆）+ 事件（唤醒）+ 队列（调度）+ 幂等（安全）。

## 参考资料

- LangGraph 官方文档 - Streaming 指南: https://langchain-ai.github.io/langgraph/how-tos/streaming/
- LangGraph 官方文档 - Event-driven Agents（以最新文档为准）: https://langchain-ai.github.io/langgraph/concepts/agentic_concepts/
- LangGraph SDK（生产部署的 API 层）: https://langchain-ai.github.io/langgraph/cloud/
- 阶段 4 配套：[04-Human-in-the-loop-interrupt与人工审批.md](04-Human-in-the-loop-interrupt与人工审批.md)、[05-Checkpoint持久化与长任务恢复.md](05-Checkpoint持久化与长任务恢复.md)
