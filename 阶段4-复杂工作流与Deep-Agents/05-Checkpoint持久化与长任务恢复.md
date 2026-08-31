# Checkpoint 持久化与长任务恢复

> 本文定位：阶段 3 只在结尾预告了一句「`MemorySaver` 让每次执行可断点续跑」。阶段 4 的长任务（研发效能 Agent 一次跑几分钟、要跨进程重启、要支持人工审批后恢复）把 Checkpoint 从「彩蛋」变成「基础设施」。本文讲透：Checkpoint 存什么、三种 Checkpointer 怎么选、`thread_id` 与会话管理、状态查询/回放/修复、进程崩溃恢复、幂等与补偿。读完本文，你能把一张图变成「断点续跑、可回放、可修复」的持久化工作流。前置：[01 篇](01-LangGraph深入-Reducer与状态设计.md)（State 序列化约束）。基于 LangGraph 1.x API。

## 学习目标

学完本文，你应该能：

- 解释 Checkpoint 机制（每个 super-step 存 State + 执行位置），以及恢复 = 从 Checkpoint 续跑；
- 在 MemorySaver / SqliteSaver / PostgresSaver 之间选型，说出各自的适用场景；
- 用 `thread_id` 管理会话（多轮对话记忆、独立任务、生命周期）；
- 用 `get_state` / `get_state_history` / `update_state` 做查询、回放与修复；
- 设计「进程崩溃 → 重启 → 恢复」的长任务方案，并处理外部副作用的重复问题（幂等）；
- 理解写入操作「不自动重试 + 补偿」的纪律在 Checkpoint 场景的体现。

## 一、Checkpoint 机制

### 1.1 存什么

Checkpoint = **每个执行步（super-step）之后的完整 State 快照 + 下一步执行位置**。执行过程中，图每走完一批节点，就把：

- 所有 State 字段的当前值（01 篇讲过：字段必须可序列化，否则存不了）；
- 当前执行位置（下一步该执行哪些节点）；

写入 Checkpointer。执行被打断（进程崩溃、超时、`interrupt` 暂停）后，用**同一个 `thread_id`** 再次触发执行，LangGraph 从最近一个 Checkpoint 恢复，而不是从头跑。

```text
执行过程（每个 ✓ 都是一个 Checkpoint）：
START -> 节点A -> 节点B -> 节点C -> END
          ✓        ✓        ✓        ✓
崩溃点在这里 ──────────┘
重启后用同一 thread_id 继续 -> 从"节点B 之后"的 Checkpoint 恢复 -> 节点C -> END
```

### 1.2 类比 Java

Checkpoint 最像**数据库事务日志（WAL）+ 事件溯源**：每一笔变更都落盘，系统崩溃后重放日志重建状态。也像微服务里的 **Saga/补偿**思想——每一步都有记录，任何一步失败都能从已知状态继续或回滚。区别：LangGraph 把「执行进度」也存了（不只要状态，还要知道下一步去哪）。

### 1.3 没有 Checkpoint 会怎样

- 多轮对话记忆：每次调用都从空 State 开始，记不住上一轮；
- `interrupt` 人工审批：直接报错（04 篇讲过，暂停位置没地方存）；
- 长任务：进程一重启，任务从头跑，还可能重复执行外部副作用。

## 二、Checkpointer 选型

LangGraph 官方提供三类 Checkpointer（以官方文档为准，API 可能演进）：

| Checkpointer | 存储 | 适用场景 | 特点 |
| --- | --- | --- | --- |
| `MemorySaver` | 进程内存 | 测试、单进程 demo | 快，但重启即丢 |
| `SqliteSaver` / `AiosqliteSaver` | SQLite 文件 | 单机生产、单 worker | 重启不丢；单写者友好，多进程并发要小心 |
| `PostgresSaver` / `AsyncPostgresSaver` | PostgreSQL | 多实例生产、分布式 | 支持多进程并发恢复、共享任务状态 |

```python
# 测试：内存
from langgraph.checkpoint.memory import MemorySaver
app = graph.compile(checkpointer=MemorySaver())

# 单机持久化：SQLite
from langgraph.checkpoint.sqlite import SqliteSaver
with SqliteSaver.from_conn_string("checkpoints.sqlite") as saver:
    app = graph.compile(checkpointer=saver)
    app.invoke(initial_state, config=config)   # 进程退出后，checkpoints.sqlite 还在

# 生产：PostgreSQL（需数据库连接串，以官方文档为准）
from langgraph.checkpoint.postgres import PostgresSaver
# 连接串示例：postgresql://user:pass@host:5432/db
with PostgresSaver.from_conn_string(CONN_STRING) as saver:
    saver.setup()                              # 建表（首次）
    app = graph.compile(checkpointer=saver)
```

选型建议（阶段 4 项目）：

- 开发调试：`MemorySaver`；
- 本地跑通/演示：`SqliteSaver`（零依赖，重启不丢）；
- 上生产/多 worker：`PostgresSaver`（阶段 5 部署篇还会展开 Docker Compose 起 Postgres）。

## 三、thread 与会话管理

### 3.1 thread_id 的语义

`thread_id` 是 Checkpoint 的**主键**：同一个 `thread_id` 的所有执行共享一条 Checkpoint 链。语义由你定义：

| 语义 | thread_id 怎么取 | 典型场景 |
| --- | --- | --- |
| 多轮对话 | 用户会话 id | 记忆：同一用户多次提问，历史都在 |
| 单个长任务 | 任务 id | 恢复：任务中断后从上次位置继续 |
| 人工审批 | 审批单 id | 暂停/恢复：等人审完接着跑 |

```python
config = {"configurable": {"thread_id": f"task-{task_id}"}}
```

**注意**：不同 thread 之间 State 完全隔离——这是天然的「多租户/多任务」隔离（阶段 2 的多租户思想在这里复用）。

### 3.2 多轮对话记忆

同一个 thread 多次 invoke，`messages` 自动累积：

```python
app.invoke({"messages": [HumanMessage(content="第一轮问题")]}, config={"configurable": {"thread_id": "user-001"}})
app.invoke({"messages": [HumanMessage(content="还记得上一轮吗？")]}, config={"configurable": {"thread_id": "user-001"}})
# 第二次调用时，State 里已有第一轮的 messages（从 Checkpoint 读出）
```

这比阶段 1 手工存历史简单得多——**对话记忆 = 用同一个 thread_id 跑图**。

### 3.3 thread 生命周期

Checkpoint 会无限累积，需要管理：

- **TTL/清理**：定期删除过期 thread 的 Checkpoint（Postgres 表按 `thread_id` 删；或任务完成后显式清理）；
- **归档**：任务结束的 thread 归档（审计需要时保留，阶段性删除中间 checkpoint）；
- **上限**：`get_state_history` 返回完整历史，别在 UI 里全量渲染。

## 四、状态查询、回放与修复

### 4.1 查询与回放

```python
config = {"configurable": {"thread_id": "task-001"}}

# 当前状态 + 下一步
state = app.get_state(config)
print(state.values, state.next)       # {'...'} ('node_x',)

# 历史（从新到旧）
for snap in app.get_state_history(config):
    print(snap.config["configurable"]["checkpoint_id"], snap.values.get("status"))
```

回放价值：**出了问题的任务，你能翻出每一步的 State 快照，定位「哪一步开始错的」**——这是阶段 5 可观测性的基础能力。

### 4.2 修复（update_state）

发现问题后不重跑整个任务，而是**修复某个节点的输出，从修复点继续**：

```python
app.update_state(config, {"analysis": "修正后的分析"}, as_node="analyze_node")
# 等价于：analyze_node 这次返回了这个值，后续节点继续执行
```

配合 04 篇：人工审批发现方案有问题 → `update_state` 修正 → 恢复。**修复 = 改历史，续跑 = 从修复点继续**。

## 五、长任务恢复实战

### 5.1 场景与架构

研发效能 Agent 跑一个任务要 1~5 分钟，中间要调多个外部系统。HTTP 请求等不了这么久——任务在**后台 worker** 执行，用户通过**状态 API** 查进度（07 篇展开队列方案，这里聚焦恢复机制）。

```text
API 网关 -> 提交任务（生成 task_id）-> 队列 -> worker 用 thread_id=task_id 跑图
用户查进度 -> get_state(thread_id=task_id) 看跑到哪了
进程重启 -> worker 从队列取回 task_id -> 用同一 thread_id 继续跑（自动从 Checkpoint 恢复）
```

### 5.2 崩溃恢复的验证

```python
# worker 进程 1：开始任务，执行到一半（模拟崩溃，直接退出）
app.invoke(initial_state, config=config)
# （进程 1 被杀）

# worker 进程 2：重新启动，同一个 thread_id 继续
app.invoke(Command(resume=None), config=config)  # 或直接 invoke 同一 config
# 从上次 Checkpoint 继续，不会从头跑
```

只要 Checkpointer 是持久的（SQLite/Postgres），**换进程、换机器都能恢复**——这就是「长任务可恢复」的工程含义。

### 5.3 重放与外部副作用：幂等性问题

**关键陷阱**：从 Checkpoint 恢复时，图会**重放**恢复点之后的节点——如果这些节点有外部副作用（发通知、写数据库、调 API），可能**执行两次**！

```python
def send_notification(state) -> dict:
    # 假设这条边之后崩溃了，恢复时会重新执行本节点
    notify("方案已完成")      # ❌ 可能发两次通知
```

对策（阶段 3 已立规矩，这里强化）：

1. **写入类操作不自动重试**（RetryPolicy 只给只读节点，02 篇 5.1）；
2. **工具幂等键**：外部调用带 `request_id`（幂等键），服务端去重——同一 request_id 只执行一次副作用；
3. **副作用后置**：把「发通知」这类动作放在图的**最后**（END 前），中间步骤失败重放时不会触达它；
4. **补偿动作**：检测到重复执行时主动撤销（如「取消已发送的重复通知」）。

```python
def send_notification(state) -> dict:
    # 带幂等键的调用：即使被重放，服务端也会去重
    notify("方案已完成", idempotency_key=f"{state['thread_id']}-final-notify")
    return {"notified": True}
```

## 六、幂等性与补偿（Checkpoint 视角）

| 概念 | 定义 | 在 Checkpoint 场景 |
| --- | --- | --- |
| 幂等 | 同一操作执行 N 次 = 执行 1 次 | 工具带幂等键；只读操作天然幂等 |
| 重放 | 从 Checkpoint 重新执行后续节点 | 恢复的必经机制，必须假设可能重放 |
| 补偿 | 对已发生副作用进行撤销/修正 | 检测重复 → 撤销；审批超时 → 自动拒绝（04 篇 6 节） |
| 不重试 | 写入类节点失败不自动重试 | RetryPolicy 只配只读节点 |

工程结论一句话：**「可恢复」必须和「幂等」一起设计**——没有幂等性的恢复，等于把「一次失败」变成「两次副作用」。

## 七、生产注意事项

### 7.1 State 可序列化（复习 01 篇 5.3）

Checkpoint 会把 State **整个序列化**存库。连接、文件句柄、模型实例放 State 里 → 存的时候直接炸或存出垃圾。写图前先过一遍：State 里只能有 str/int/float/bool/list/dict/Pydantic/BaseMessage。

### 7.2 Schema 演进

Checkpoint 存的是**历史版本的 State**。改字段名/类型后，旧 Checkpoint 恢复可能缺字段。纪律（01 篇 5.5）：节点读字段用 `state.get("field", 默认)`；新增字段给默认值。

### 7.3 并发控制

- SQLite 单写者：多 worker 并发写同一 SQLite 文件会锁冲突——**单机单 worker 用 SQLite，多 worker 用 Postgres**；
- Postgres 天然支持并发：多个 worker 各自处理不同 thread_id，互不干扰；同一 thread 并发写由数据库行锁保证。

### 7.4 备份与清理

- Checkpoint 表是「执行日志」，包含**敏感数据**（用户输入、审批意见）——备份策略和清理策略要跟上（阶段 5 安全篇展开）；
- 定期清理过期 thread（3.3）。

## 学习自检与练习

### 练习 1：MemorySaver 多轮记忆

用 `create_react_agent` + `MemorySaver`，同一个 `thread_id` 连续问两轮（第二轮问「我刚才说了什么」），验证模型记得上一轮内容；换个 `thread_id` 再问，验证记忆隔离。

自检：不配 checkpointer 时，第二轮还能记得吗？（提示：1.3）

### 练习 2：SQLite 崩溃恢复

用 `SqliteSaver` 跑 04 篇的审批流：第一次 invoke 暂停在 `human_review`，**模拟进程退出（重新运行脚本）**，然后用同一个 thread 恢复并批准，验证任务从暂停点继续。

自检：换一个完全新的进程（脚本重跑），Checkpoint 还在吗？（提示：SQLite 落盘）

### 练习 3：幂等设计

给「发通知」工具加幂等键（`idempotency_key`），用「崩溃在发通知之后、恢复重放」的场景验证：通知只实际发送一次（用打印计数模拟服务端去重）。

自检：如果通知工具没有幂等键，恢复重放会导致什么？（提示：5.3 发两次）

### 自检清单

- [ ] 能解释 Checkpoint 存什么、恢复 = 从 Checkpoint 续跑；
- [ ] 能在 MemorySaver / SqliteSaver / PostgresSaver 之间选型；
- [ ] 会用 thread_id 做多轮记忆、任务恢复、多任务隔离；
- [ ] 会用 get_state / get_state_history / update_state 查询、回放、修复；
- [ ] 能说出「恢复 = 重放」与「外部副作用重复」的关系，并给出幂等方案；
- [ ] 知道 SQLite 与 Postgres 在并发场景的选型边界；
- [ ] 知道「可恢复必须与幂等一起设计」。

## 参考资料

- LangGraph 官方文档 - Persistence 概念: https://langchain-ai.github.io/langgraph/concepts/persistence/
- LangGraph 官方文档 - Checkpointer 指南: https://langchain-ai.github.io/langgraph/how-tos/persistence/
- langgraph-checkpoint 包（Memory/Sqlite/Postgres）: https://github.com/langchain-ai/langgraph-checkpoint
- 阶段 4 配套：[01-LangGraph深入-Reducer与状态设计.md](01-LangGraph深入-Reducer与状态设计.md)（State 序列化约束）、[04-Human-in-the-loop-interrupt与人工审批.md](04-Human-in-the-loop-interrupt与人工审批.md)（interrupt 依赖 Checkpoint）、[07-Event-driven-Workflow与异步长任务.md](07-Event-driven-Workflow与异步长任务.md)（任务队列 + 恢复）
