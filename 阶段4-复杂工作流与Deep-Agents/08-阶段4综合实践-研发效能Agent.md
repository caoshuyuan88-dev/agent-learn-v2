# 阶段 4 综合实践：研发效能 Agent

> 本文是阶段 4 的**项目设计文档 + 分步实施指南**：把前七篇学到的 Reducer 与状态设计、并行分支与子图、多 Agent 编排、Human-in-the-loop、Checkpoint 持久化、Deep Agents、事件驱动工作流全部串进一个可运行、可演示、可写进作品集的项目。学习完前七篇后，按本文的 Milestone 顺序动手开发，每个 Milestone 都有验收标准，做完一个再进入下一个。**项目主干采用「LangGraph 可控编排 + 少量 Agent 决策节点」**（呼应学习路线：确定性工作流 + 少量 Agent 决策节点；不无理由混用多个编排框架）。

## 一、项目目标与需求范围

### 1.1 项目一句话

构建一个「研发效能 Agent」：研发人员输入需求描述，Agent 依次完成**需求分析 → 技术方案 → 风险检查 → 测试用例设计**，产出带人工审核环节的 **Markdown 报告**；任务支持**异步提交、进度查询、断点恢复、外部事件唤醒（CI 结果）**，所有写操作（生成报告、发送通知）经过**人工审批**。

### 1.2 流程（学习路线原版 + 扩展）

```text
需求输入
  -> 需求分析 Agent
  -> 技术方案 Agent
  -> 风险检查 Agent
  -> 测试用例 Agent
  -> 人工审核
  -> 输出 Markdown 报告
```

可扩展接入（M5/M6 逐步做）：

- Jira / GitLab / GitHub 工具（需求同步、代码变更）
- 代码仓库检索（Deep Agent 能力）
- 数据库查询
- 测试结果读取（CI 事件驱动）
- 人工审批（HITL）
- 失败恢复（Checkpoint）
- 结果评测（阶段 5 铺路）

### 1.3 功能需求（必须全部覆盖）

| 编号 | 功能 | 涉及技术（前七篇） |
| --- | --- | --- |
| F1 | 需求分析：把需求拆成目标/范围/约束 | LangGraph 流水线、Reducer 状态设计（01） |
| F2 | 技术方案：基于需求生成方案 | Supervisor/流水线中的 Worker Agent（03） |
| F3 | 风险检查：与方案**并行**做合规/性能/安全检查 | 扇出 + 汇聚（02） |
| F4 | 测试用例：生成测试用例清单 | 确定性节点 + LLM（01/02） |
| F5 | 人工审核：报告生成前暂停，批准/拒绝/意见回传 | interrupt + Command(resume)（04） |
| F6 | 报告输出：生成 Markdown 文件 | 文件系统工具 + 安全约束（06） |
| F7 | 长任务：异步提交、查进度、崩溃恢复 | Checkpoint + thread_id（05） |
| F8 | 外部事件：CI 测试结果到达后自动继续 | 事件驱动 + update_state（07） |
| F9 | 审计与幂等：写操作留痕、重放不重复 | 幂等键、审计字段（05/阶段 3） |

### 1.4 非功能需求

- **可控**：整个任务 LLM 调用次数有预算上限，超限走兜底节点（03 篇纪律 5）；
- **可恢复**：worker 进程崩溃后，重启能用同一 `task_id` 从 Checkpoint 继续（05 篇）；
- **可审计**：审批意见、事件注入、写操作全部留痕（可查 `get_state_history`）；
- **安全**：文件写入限定工作目录、写操作必须人工审批、工具调用记审计（阶段 3 纪律复用）；
- **可评测**（阶段 5 铺路）：任务完成率、审批通过率、耗时、token 成本留字段（05 篇可观测字段预告）。

### 1.5 用户故事（5 条）

1. 作为研发，我输入「实现订单查询接口并评估风险」，Agent 自动完成分析/方案/风险/测试用例四步，停在**人工审核**处等我校验方案。
2. 作为研发，我在审核界面看到方案，发现「缺限流设计」，**拒绝并附意见**；Agent 带着意见修改后**重新提交审核**。
3. 作为研发，我批准后，Agent 生成 `report.md` 写入工作目录，并回调结果。
4. 作为平台，任务提交后我在**任意时刻查进度**（当前跑到哪一步）；worker 崩溃重启后任务自动续跑，不重复。
5. 作为平台，任务停在「等待 CI 测试结果」时，**GitLab CI 完成事件到达后**任务自动继续生成最终报告。

## 二、系统架构设计

### 2.1 架构图（文字版）

```text
┌────────────┐  POST /tasks        ┌──────────────────────────────────┐
│  前端/CLI   │ ──────────────────▶ │           FastAPI 网关           │
└────────────┘                     │ /tasks           提交            │
       ▲                           │ /tasks/{id}      查进度          │
       │ 轮询/SSE                  │ /tasks/{id}/approve 审批         │
       │                           │ /tasks/{id}/report 下载报告      │
       │                           └──────────────┬───────────────────┘
       │                                          │ 投递
       │                            ┌─────────────▼───────────────────┐
       │                            │      任务队列（Redis Stream）    │
       │                            └─────────────┬───────────────────┘
       │                                          │ 消费
       │                            ┌─────────────▼───────────────────┐
       │                            │  Worker（LangGraph 图）          │
       │                            │  thread_id = task_id            │
       │                            │  状态/Checkpoint: PostgreSQL     │
       │                            └──────┬──────────────┬───────────┘
       │                                   │              │ 文件写入
       │                                   │              ▼
       │                          ┌────────▼─────┐  ┌──────────────┐
       │                          │ 事件消费者    │  │ 工作目录      │
       │                          │ (CI webhook) │  │ (report.md)  │
       │                          └──────────────┘  └──────────────┘
       │
       ▼
┌──────────────┐    ┌──────────────────────────────────────────────┐
│  LLM 模型服务 │    │  外部模拟服务：GitLab API / Jira API / CI 事件 │
└──────────────┘    └──────────────────────────────────────────────┘
```

### 2.2 核心组件清单

| 组件 | 职责 | 所在模块 |
| --- | --- | --- |
| LangGraph 图 | 四步流水线 + 并行风险检查 + 人审 + 报告 | `app/graph/` |
| State 定义 | `RDAgentState`（任务上下文 + 各 Agent 私有章节 + 审批 + 审计字段） | `app/graph/state.py` |
| 四个 Worker | 需求分析 / 技术方案 / 风险检查 / 测试用例（01~03 篇） | `app/agents/` |
| 并行风险检查 | 合规/性能/安全三路扇出 + 汇聚（02 篇） | `app/graph/risk_node.py` |
| 人工审核节点 | interrupt 暂停、结构化审批意见（04 篇） | `app/graph/approval_node.py` |
| 文件系统工具 | 写报告到工作目录（路径白名单，06 篇） | `app/tools/fs_tools.py` |
| Checkpointer | PostgreSQL 持久化（05 篇） | `app/graph/checkpointer.py` |
| 队列 + Worker | 异步执行、崩溃恢复（05/07 篇） | `app/worker/`、`app/queue/` |
| 事件消费者 | CI webhook → update_state → 恢复（07 篇） | `app/events/ci_listener.py` |
| 模拟外部服务 | GitLab/Jira/CI 的模拟实现（便于本地开发） | `mock_ext/` |

### 2.3 关键设计决策表

| 设计决策 | 选择 | 理由 |
| --- | --- | --- |
| 编排框架 | **LangGraph 显式流水线 + 少量 Agent 决策节点** | 流程固定（四步 + 人审），需要人工审批、审计、恢复——LangGraph 可控；不用 deepagents 做主框架（06 篇选型纪律） |
| 多 Agent 模式 | **流水线（确定性）+ 风险检查并行**；Supervisor 只用在「方案需要动态分派」的可选扩展（03 篇） | 流程确定，显式边最可控、最省 token；不为了多 Agent 而多 Agent |
| 各 Agent 章节存储 | `report: Annotated[dict, merge_dict]`（01 篇 3.4） | 各 Agent 并行/串行写自己的章节，互不覆盖 |
| 人工审核 | `interrupt()` 动态中断 + 结构化 resume | 只有方案产出后才审，审核意见回传修改（04 篇） |
| 长任务恢复 | Checkpoint 落 PostgreSQL，`thread_id = task_id` | 崩溃重启续跑、跨 worker 共享（05 篇） |
| CI 事件唤醒 | webhook → update_state 注入 → 同一 thread_id 恢复 | 外部事件驱动，不轮询（07 篇 3.2） |
| 写报告 | 文件系统工具 + 路径白名单 | 深 Agent 能力（06 篇 4.2），但写入限定工作目录 |
| 幂等 | 写操作带幂等键、事件处理器检查等待点 | 重放/重投不重复副作用（05 篇 5.3、07 篇 3.2） |

## 三、数据模型设计

### 3.1 LangGraph State（RDAgentState）

```python
from typing import TypedDict, Annotated, Literal
from langgraph.graph import MessagesState

def merge_dict(current: dict, update: dict) -> dict:
    out = dict(current); out.update(update); return out

class RDAgentState(MessagesState):
    # ---- 任务上下文 ----
    task_id: str
    requirement: str

    # ---- 各 Agent 产出（分章节，01 篇 3.4 merge_dict）----
    report: Annotated[dict, merge_dict]   # {"analysis": ..., "design": ..., "risk": ..., "test": ...}

    # ---- 并行风险检查 ----
    risk_errors: list[str]

    # ---- 人工审核（04 篇）----
    approval_status: Literal["pending", "approved", "rejected"]
    approval_comment: str
    review_rounds: int

    # ---- 长任务/事件驱动（05/07 篇）----
    ci_result: dict | None        # CI 测试结果（外部事件注入）
    status: str                   # queued / running / waiting_approval / waiting_ci / done / failed
    progress: list[str]           # 已完成步骤（审计/展示）
```

### 3.2 持久化表（PostgreSQL）

| 表 | 用途 |
| --- | --- |
| `checkpoints`（LangGraph 建） | 每个 super-step 的 State 快照（05 篇） |
| `tasks` | 任务元数据：task_id、requirement、status、created_at |
| `approvals` | 审批记录：task_id、round、action、comment、approver、time（审计） |
| `events` | 外部事件记录：task_id、event_type、payload、处理时间（幂等去重） |

### 3.3 审计字段（阶段 5 可观测性铺路）

State 里保留：`trace_id`（= task_id）、`agent_name`、`model_name`、`tool_name`、`input_tokens`、`output_tokens`、`latency`、`final_answer`——阶段 5 接 Langfuse/OpenTelemetry 时直接映射。

## 四、图结构设计（核心）

### 4.1 主图

```text
START
  -> analyze_node（需求分析）
  -> design_node（技术方案）
  -> risk_fanout（扇出）──┬─ compliance_check
                         ├─ performance_check      （02 篇并行）
                         └─ security_check
  -> risk_merge（汇聚，写 report["risk"]）
  -> test_node（测试用例）
  -> human_review（interrupt，04 篇）
      ├─ approved -> wait_ci（可选，07 篇）-> write_report -> END
      └─ rejected -> review_rounds+1 -> design_node（带意见重做，轮数保护）
```

### 4.2 关键节点要点

- **analyze/design/test 节点**：内部是 LLM 调用（绑定工具可选），产出写 `report[key]`；
- **risk_fanout**：三路并行（02 篇 2.1），各写 `report["risk"]` 不同子 key 或 `merge_dict` 合并；
- **human_review**：`interrupt({...待审内容...})`，resume 传 `{"action": "approved"|"rejected", "comment": "..."}`（04 篇 3.2）；`review_rounds >= 3` 强制收尾；
- **wait_ci**（M5 加）：把 `ci_result` 写默认值后节点结束，等待外部事件（07 篇 3.2）；
- **write_report**：调文件系统工具写 `report.md`（06 篇 4.2 安全约束），带幂等键。

### 4.3 图结构代码骨架

```python
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command

graph = StateGraph(RDAgentState)
graph.add_node("analyze", analyze_node)
graph.add_node("design", design_node)
graph.add_node("risk_fanout", risk_fanout)
graph.add_node("compliance", compliance_check)
graph.add_node("performance", performance_check)
graph.add_node("security", security_check)
graph.add_node("risk_merge", risk_merge)
graph.add_node("test", test_node)
graph.add_node("human_review", human_review)
graph.add_node("write_report", write_report)

graph.add_edge(START, "analyze")
graph.add_edge("analyze", "design")
graph.add_edge("design", "risk_fanout")
# 并行扇出（02 篇）
graph.add_edge("risk_fanout", "compliance")
graph.add_edge("risk_fanout", "performance")
graph.add_edge("risk_fanout", "security")
graph.add_edge("compliance", "risk_merge")
graph.add_edge("performance", "risk_merge")
graph.add_edge("security", "risk_merge")
graph.add_edge("risk_merge", "test")
graph.add_edge("test", "human_review")
# 人审分支（04 篇）
graph.add_conditional_edges("human_review", after_review, {"rework": "design", "finalize": "write_report"})
graph.add_edge("write_report", END)

app = graph.compile(checkpointer=pg_saver)
```

## 五、Milestone 实施计划

> 每个 Milestone 有明确的**验收标准**。按顺序做，别跳。每个 M 完成时把图导出 Mermaid 看一眼拓扑（阶段 3 的调试习惯）。

### M1：单 Agent 线性流水线（确定性工作流）

- 只做 analyze → design → test 三个节点 + 一个简单的 risk 节点，**串行**，不并行、不人审；
- State 用 `report: Annotated[dict, merge_dict]`，每个节点写自己的章节；
- 输出：`invoke` 后打印 `report` 各章节。

验收标准：输入一条需求，四步串行跑通，`report` 四个章节齐全；`draw_mermaid()` 导出图拓扑正确。

### M2：并行风险检查

- 把 risk 拆成 compliance / performance / security 三路并行 + risk_merge 汇聚（02 篇）；
- 故意让一路抛异常，验证「局部兜底」写法（02 篇 2.3）后图仍正常完成；
- 实测串行版 vs 并行版耗时对比。

验收标准：三路并行执行（日志里能看出并发），汇聚后的 `report["risk"]` 含三部分内容；单路失败不拖垮整体。

### M3：人工审核（HITL）

- 加 `human_review` 节点：`interrupt` 暂停，resume 传结构化审批结果；
- 批准 → write_report（先写死内容）；拒绝 → 回 design 重做，`review_rounds` 计数，>=3 强制收尾（04 篇 3.2）；
- 配 `MemorySaver` 先跑通，再切 `SqliteSaver`。

验收标准：批准/拒绝两条分支都跑通；拒绝意见出现在下一轮 design 的输入里；三轮不过强制收尾。

### M4：Checkpoint 持久化与恢复

- 换 `PostgresSaver`（本地 Docker 起 Postgres，或先 SQLite）；
- `thread_id = task_id`；任务执行到一半模拟进程退出（脚本重跑），重启后同一 `task_id` 续跑（05 篇 5.2）；
- 用 `get_state` / `get_state_history` 查进度与历史；`update_state` 修复一个错误结果后继续。

验收标准：崩溃重启后从 Checkpoint 继续（不从头跑）；`get_state_history` 能看到每一步快照；`update_state` 修复生效。

### M5：异步执行与事件驱动

- FastAPI 网关：`POST /tasks`（入队）、`GET /tasks/{id}`（查进度）、审批接口（resume）；
- 队列 + Worker（Redis Stream 或 `asyncio.Queue` 模拟）；worker 用 `thread_id=task_id` 跑图；
- CI 事件：图加 `wait_ci` 节点；模拟 CI webhook → `update_state` 注入 `ci_result` → 恢复（07 篇 3.2）；
- 写报告节点接真实文件系统工具（路径白名单）。

验收标准：提交任务后立即返回 `task_id`；任务停在 `waiting_ci` 时模拟 CI 事件到达，图自动继续到 `write_report` 并生成 `report.md`；webhook 重复投递不重复处理（幂等）。

### M6：审计、评测字段与报告美化（阶段 5 铺路）

- 审批记录落 `approvals` 表；事件记录落 `events` 表（幂等去重键）；
- State 补齐审计/评测字段（token、耗时、每步结果，3.3）；
- 用 `get_state_history` 写一个简单的「任务执行轨迹」页面/脚本；
- 准备 10~20 条测试需求，记录任务完成率、审批通过率、平均耗时（阶段 5 评测数据集雏形）。

验收标准：每条任务有完整可查的轨迹（含审批、事件）；能输出一份简单的评测统计（完成率/通过率/耗时）。

## 六、可扩展方向（做完 M1~M6 后选做）

| 扩展 | 做法 | 关联篇章 |
| --- | --- | --- |
| GitLab/GitHub 工具 | 包成工具接入：拉变更、读代码（Deep Agent 探索能力） | 06 |
| 代码仓库检索 Agent | `create_react_agent` 作为子 Agent 工具，供 design 节点调用 | 03/06 |
| 数据库查询 | 复用阶段 3 的 database-mcp-server（白名单表） | 阶段 3 |
| 测试结果读取 | CI 事件里带测试摘要，注入 `ci_result` 后在报告中引用 | 07 |
| 失败恢复增强 | 节点级 RetryPolicy + 幂等键完善 | 02/05 |
| 结果评测 | 对报告质量打分（LLM-as-judge），进阶段 5 评测体系 | 阶段 5 |
| 多轮人审细化 | 支持「部分通过 + 指定修改章节」 | 04 |

## 七、学习自检清单（项目验收总纲）

- [ ] M1~M6 全部验收通过，图拓扑清晰（每张图都导出过 Mermaid）；
- [ ] 能说出这个项目里「确定性工作流」和「Agent 决策节点」各自在哪（分析/方案/测试是 LLM 决策，流程/并行/人审是确定性结构）；
- [ ] 能解释为什么项目主干用 LangGraph 而不是 deepagents 或纯 Supervisor（06/03 篇选型纪律）；
- [ ] 能演示：提交 → 并行风险检查 → 人审拒绝带意见重做 → 批准 → 等 CI 事件 → 写报告 的完整链路；
- [ ] 能演示崩溃恢复（kill worker 后重启续跑）且无重复副作用（幂等）；
- [ ] 能把每个核心概念对应到实际代码位置：reducer（01）、并行（02）、编排（03）、interrupt（04）、checkpoint（05）、文件系统（06）、事件驱动（07）。

## 参考资料

- 阶段 4 全部前七篇（本目录 01~07）
- 阶段 3 综合实践（项目方法论的参考）：[08-阶段3综合实践-企业运维分析Agent.md](../阶段3-Tools与MCP/08-阶段3综合实践-企业运维分析Agent.md)
- LangGraph 官方 How-to 集（Multi-agent / HITL / Persistence / Streaming）: https://langchain-ai.github.io/langgraph/how-tos/
