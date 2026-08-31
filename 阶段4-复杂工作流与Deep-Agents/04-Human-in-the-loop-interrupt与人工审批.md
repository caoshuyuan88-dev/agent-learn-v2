# Human-in-the-loop：interrupt 与人工审批

> 本文定位：阶段 3 的 [03 安全篇](../阶段3-Tools与MCP/03-工具安全-RBAC权限与人工确认.md) 立了规矩——写操作必须人工确认；[07 入门篇](../阶段3-Tools与MCP/07-LangGraph入门-StateGraph.md) 预告了 LangGraph 的 `interrupt` 机制。本文把它完整落地：`interrupt()` 暂停执行、恢复执行、完整审批流（批准/拒绝/意见）、静态断点、`update_state` 修正、审批超时自动降级、多轮人工输入。读完本文，你能在 LangGraph 工作流里实现「执行到关键步骤暂停 → 人审 → 批准继续/拒绝中止」的完整闭环。这是阶段 4 项目（研发效能 Agent 的人工审核环节）的核心技术。前置：[01 篇](01-LangGraph深入-Reducer与状态设计.md)（Command）、[05 篇](05-Checkpoint持久化与长任务恢复.md)（Checkpoint——interrupt 依赖它，建议先看第 05 篇前两节再回来）。基于 LangGraph 1.x API。

## 学习目标

学完本文，你应该能：

- 解释 `interrupt()` 的原理（暂停 → 保存 checkpoint → 恢复时返回 resume 值）及为什么必须配 Checkpointer；
- 用 `thread_id` 实现「暂停 → 人工审批 → 恢复」的完整闭环；
- 实现批准/拒绝两种分支（含结构化审批意见），拒绝后走修改或中止节点；
- 用 `interrupt_before` / `interrupt_after` 做**静态断点**（不改节点代码）；
- 用 `update_state` 人工修正状态后让图继续；
- 设计审批超时自动降级（配合外部调度，为 07 篇铺垫）。

## 一、为什么需要 Human-in-the-loop

### 1.1 模型不该自作主张的事

| 操作类型 | 例子 | 风险 |
| --- | --- | --- |
| 不可逆写操作 | 发布版本、删除数据、发送通知 | 错了无法挽回 |
| 有外部副作用 | 提交 Jira、创建 PR、调用生产 API | 影响真实系统 |
| 成本敏感操作 | 跑长任务、调贵模型、批量执行 | 钱花错了 |
| 合规敏感 | 越权数据、PII、外包内容 | 法律/安全风险 |

阶段 3 的 RBAC 解决「**谁有权限调**」，HITL 解决「**调用前让人把关**」——权限管「能不能」，人审管「这次该不该」。

### 1.2 HITL 的两种形态

1. **静态断点**（`interrupt_before`/`interrupt_after`）：编译图时声明「执行到某节点前/后暂停」，所有走到这里的执行都会停；
2. **动态中断**（`interrupt()` 函数）：节点内部按业务条件决定是否暂停——「需要审批的写操作才停，只读查询不停」。

生产系统以**动态中断**为主（暂停是业务规则，不是图结构），静态断点用于调试和兜底。本文重点讲动态中断。

类比 Java：HITL 像审批流（Activiti/Flowable 里的 userTask）——流程走到用户任务节点挂起，等人提交审批意见后流程继续；`interrupt` 就是 LangGraph 里的 userTask。

## 二、interrupt 基础

### 2.1 原理

在节点内部调用 `interrupt(payload)`：

```python
from langgraph.types import interrupt

def approval_node(state: State) -> str:
    # 暂停，把"要审什么"展示给人
    user_decision = interrupt({"action": "publish_version", "version": "v1.2.0", "reason": "发布 1.2.0 到生产"})
    # 恢复执行时，interrupt() 返回人审的结果
    return {"approval": user_decision}
```

执行流程：

1. 图执行到 `interrupt(payload)`，**立即暂停**（抛内部异常被框架捕获），当前 State 已存进 Checkpoint；
2. 外部拿到 payload（要审的内容）和人审入口（恢复方式）；
3. 人审结束后，用**同一 thread_id** 恢复执行，传入 resume 值；
4. `interrupt()` 调用点**返回 resume 值**，节点继续往下执行。

**硬性前提**：`compile(checkpointer=...)` 必须配 Checkpointer——没有 Checkpoint 就无法保存暂停位置和状态，`interrupt` 会直接报错。

### 2.2 最小可运行示例

```python
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver

class PublishState(TypedDict):
    version: str
    approval: str

def request_approval(state: PublishState) -> dict:
    decision = interrupt({"action": "publish", "version": state["version"]})
    return {"approval": decision}

def publish(state: PublishState) -> dict:
    return {"approval": f"已发布 {state['version']}（审批：{state['approval']}）"}

def rejected(state: PublishState) -> dict:
    return {"approval": f"发布被拒绝：{state['approval']}"}

graph = StateGraph(PublishState)
graph.add_node("request_approval", request_approval)
graph.add_node("publish", publish)
graph.add_node("rejected", rejected)
graph.add_edge(START, "request_approval")

# request_approval 执行完（interrupt 返回后），按审批结果路由
def after_approval(state: PublishState) -> str:
    return "publish" if state["approval"] == "approved" else "rejected"

graph.add_conditional_edges("request_approval", after_approval, {"publish": "publish", "rejected": "rejected"})
graph.add_edge("publish", END)
graph.add_edge("rejected", END)

app = graph.compile(checkpointer=MemorySaver())
config = {"configurable": {"thread_id": "pub-001"}}

# 第一次调用：执行到 interrupt 暂停
result = app.invoke({"version": "v1.2.0"}, config=config)
# result["approval"] 还没写入（interrupt 前返回），
# 但可以通过 app.get_state(config) 查看暂停点和待审内容：
snapshot = app.get_state(config)
print(snapshot.next)                    # ('request_approval',) —— 下一步要执行这个节点
# 从 snapshot 里取待审内容：interrupt 的 payload 存在 state 的 __interrupt__ 里
print(snapshot.values)                  # {'version': 'v1.2.0', 'approval': ''}

# 人工审批：批准 -> 恢复执行
app.invoke(Command(resume="approved"), config=config)
# 内部：interrupt() 返回 "approved" -> after_approval -> publish -> END

final = app.get_state(config).values
print(final["approval"])   # 已发布 v1.2.0（审批：approved）
```

### 2.3 恢复的两种方式

```python
# 方式 1（推荐）：Command(resume=...) —— 显式"恢复 + 传值"
app.invoke(Command(resume={"action": "approved", "comment": "版本已验证，放行"}), config=config)

# 方式 2：invoke 一个普通输入 —— 如果图有入口边，也可以直接 invoke 触发恢复
# （但语义不直观，生产用方式 1）
```

resume 值可以是任意可序列化对象：字符串（`"approved"`）、字典（结构化审批意见）、Pydantic 模型。**建议用结构化值**——审批不只是「行/不行」，还要带意见、审批人、时间（这些会进审计）。

## 三、完整审批流：研发效能场景

### 3.1 场景

研发效能 Agent 生成完「技术方案」后，要人工审核才能产出最终报告。审核不通过要带着意见回去修改（改方案 → 再审），通过才继续。

### 3.2 实现

```python
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.types import interrupt, Command

class ReviewState(TypedDict):
    requirement: str
    proposal: str           # 技术方案
    review_result: str      # 审批结论（approved / rejected）
    review_comment: str     # 审批意见
    rounds: int             # 审核轮数（防止无限改）

def generate_proposal(state: ReviewState) -> dict:
    # 真实场景：LLM 生成方案；这里占位
    return {"proposal": f"方案：基于 {state['requirement']} 的技术设计 v{state['rounds']}"}

def human_review(state: ReviewState) -> dict:
    decision = interrupt({
        "step": "proposal_review",
        "requirement": state["requirement"],
        "proposal": state["proposal"],
        "round": state["rounds"],
    })
    # 结构化的审批结果：{"action": "approved"|"rejected", "comment": "..."}
    return {"review_result": decision["action"], "review_comment": decision["comment"]}

def should_continue(state: ReviewState) -> str:
    if state["review_result"] == "approved":
        return "finalize"
    if state["rounds"] >= 3:
        return "finalize"          # 改了 3 轮还没过，强制收尾（防止死循环）
    return "rework"                # 带意见回去改

def rework(state: ReviewState) -> dict:
    return {"rounds": state["rounds"] + 1}   # 下一轮带着意见重新生成方案

def finalize(state: ReviewState) -> dict:
    status = "通过" if state["review_result"] == "approved" else "未通过（已达最大轮数）"
    return {"proposal": f"{state['proposal']}\n[审核{status}，意见：{state['review_comment']}]"}

graph = StateGraph(ReviewState)
graph.add_node("generate_proposal", generate_proposal)
graph.add_node("human_review", human_review)
graph.add_node("rework", rework)
graph.add_node("finalize", finalize)
graph.add_edge(START, "generate_proposal")
graph.add_edge("generate_proposal", "human_review")
graph.add_conditional_edges("human_review", should_continue,
    {"rework": "rework", "finalize": "finalize"})
graph.add_edge("rework", "generate_proposal")   # 回到生成节点，循环
graph.add_edge("finalize", END)

app = graph.compile(checkpointer=MemorySaver())
config = {"configurable": {"thread_id": "rd-001"}}

# 第一轮：生成方案 -> 暂停等人审
app.invoke({"requirement": "实现登录鉴权", "proposal": "", "review_result": "", "review_comment": "", "rounds": 0}, config=config)

# 人审：拒绝，带意见
app.invoke(Command(resume={"action": "rejected", "comment": "缺少限流设计"}), config=config)
# -> rework -> 重新生成方案 -> 又暂停

# 人审：这次通过
app.invoke(Command(resume={"action": "approved", "comment": "补充限流后可以"}), config=config)
final = app.get_state(config).values
print(final["proposal"])
```

要点：

- **轮数保护**：`rounds >= 3` 强制收尾——人审也可能反复拒，不能让任务无限循环（呼应 03 篇「循环保护」纪律）；
- **结构化审批**：resume 传 dict，把 `action` 和 `comment` 都记进 State（后续进审计/报告）；
- **意见闭环**：拒绝意见通过 State 传回生成节点（`review_comment` 是下一轮生成的输入）。

## 四、静态断点：interrupt_before / interrupt_after

不改节点代码，在编译时声明断点：

```python
app = graph.compile(
    checkpointer=MemorySaver(),
    interrupt_before=["publish"],     # 执行到 publish 之前暂停
    # interrupt_after=["generate_proposal"],   # 或者执行完后暂停
)
```

- `interrupt_before=["publish"]`：每次执行到 `publish` 前都暂停（适合「所有写操作统一人审」）；
- 恢复方式同上：`Command(resume=...)` 或 `app.invoke(Command(resume=...), config)`。

**适用**：统一拦截某个高风险节点、调试观察、为「所有 X 操作强制人审」的合规需求兜底。**不适用**：需要按业务条件区分「这次要审、下次不用」——那是动态 `interrupt()` 的活。

## 五、update_state：人工修正后继续

有时候人审不只是「行/不行」，而是**直接修改内容**（比如把方案里的一句话改掉）。用 `update_state` 注入修正值，图从修正后的状态继续：

```python
# 暂停在 human_review 时，人工直接修改方案内容
app.update_state(config, {"proposal": "修正后的方案（人工改动）"}, as_node="generate_proposal")
# 假装 generate_proposal 产出了修正版；然后恢复
app.invoke(Command(resume={"action": "approved", "comment": "已人工修改"}), config=config)
```

场景：人工发现方案有笔误、工具返回了脏数据、外部系统状态变了——**修复状态再重放**，而不是从头跑（也见 05 篇的状态回放）。

## 六、审批超时自动降级

人审可能**永远不来**（审批人休假、接口挂掉）。生产上必须给审批设超时：超时自动按「拒绝」或「降级」处理。

做法（07 篇详讲，这里给思路）：

1. 图暂停后，**外部调度器**（定时任务 / 任务队列）盯着这个 thread；
2. 超时后调用 `app.update_state(config, {"review_result": "rejected", "review_comment": "审批超时，自动拒绝"}, as_node="human_review")`，再 `Command(resume=...)` 继续；
3. 图走到 `rejected` 分支，任务以「超时拒绝」收尾（审计里留痕：超时自动处理）。

```python
# 伪代码：外部定时任务
async def timeout_guard(thread_id: str, timeout_s: int = 3600):
    await asyncio.sleep(timeout_s)
    state = app.get_state(config)
    if state.next and "human_review" in state.next:   # 还停在审批节点
        app.update_state(config, {"review_result": "rejected",
                                  "review_comment": "审批超时，自动拒绝"}, as_node="human_review")
        app.invoke(Command(resume={"action": "rejected", "comment": "审批超时"}), config=config)
```

## 七、多轮人工输入（表单收集）

`interrupt` 可以连续多次使用，收集多段输入（像填表单）：

```python
def collect_info(state) -> dict:
    project = interrupt({"step": "input_project", "question": "请输入项目名："})
    owner = interrupt({"step": "input_owner", "question": "请输入负责人："})
    return {"project": project, "owner": owner}
```

每次 `interrupt` 暂停一次，外部依次 `Command(resume=...)` 填值。注意：**每次恢复都是独立的外部调用**，前端要按 `step` 字段区分当前在等哪一项。

## 学习自检与练习

### 练习 1：最小 interrupt

跑通 2.2 的最小示例：第一次 invoke 后确认 `get_state(config).next` 指向 `request_approval`；用 `Command(resume="approved")` 和 `Command(resume="rejected")` 各跑一次，验证两条分支。

自检：如果不配 `checkpointer`，`interrupt` 会怎样？（提示：直接报错，interrupt 依赖 checkpoint）

### 练习 2：审批闭环

用 3.2 的完整审批流，模拟「拒绝 → 修改 → 再拒绝 → 再修改 → 通过」全流程，并验证 `rounds >= 3` 时强制收尾。

自检：`should_continue` 里 `rounds >= 3` 返回 `finalize` 时，`review_result` 还是 `"rejected"`——`finalize` 节点是怎么区分「通过收尾」和「超轮数收尾」的？（提示：3.2 里 status 的写法）

### 练习 3：静态断点

把 2.2 的图改成 `interrupt_before=["publish"]`（去掉节点内的 `interrupt()`），验证执行到 publish 前暂停、`Command(resume=...)` 后继续。

自检：静态断点和动态 `interrupt()` 各自的适用场景是什么？

### 自检清单

- [ ] 能解释 interrupt 的「暂停 → 存 checkpoint → 恢复返回 resume 值」原理；
- [ ] 知道 interrupt 为什么必须配 Checkpointer；
- [ ] 能实现「审批 → 批准/拒绝分支 → 意见回传修改」完整闭环；
- [ ] 知道审批轮数保护和审批超时自动降级两种兜底手段；
- [ ] 能区分 `interrupt_before/after`（静态）与 `interrupt()`（动态）的适用场景；
- [ ] 会用 `update_state` 人工修正状态后恢复执行。

## 参考资料

- LangGraph 官方文档 - Human-in-the-loop 概念: https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/
- LangGraph 官方文档 - interrupt 指南: https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/interrupt/
- LangGraph 官方文档 - 静态断点指南: https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/breakpoints/
- 阶段 3 配套：[03-工具安全-RBAC权限与人工确认.md](../阶段3-Tools与MCP/03-工具安全-RBAC权限与人工确认.md)（权限与人工确认的业务规则）
- 阶段 4 配套：[05-Checkpoint持久化与长任务恢复.md](05-Checkpoint持久化与长任务恢复.md)（interrupt 的基础设施）、[07-Event-driven-Workflow与异步长任务.md](07-Event-driven-Workflow与异步长任务.md)（审批超时自动降级）
