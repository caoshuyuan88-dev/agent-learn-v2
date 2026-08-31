# LangGraph 深入：Reducer 与状态设计

> 本文定位：阶段 3 的 [07-LangGraph入门-StateGraph.md](../阶段3-Tools与MCP/07-LangGraph入门-StateGraph.md) 只用了 `Annotated[list, operator.add]` 这一个 reducer 就搭出了 ReAct 循环。但到了阶段 4，你要面对的是**多 Agent、并行分支、Checkpoint 恢复**——这些场景下 State 的合并语义、字段粒度、可序列化约束会直接决定你的图是「几天就能跑通」还是「上生产就翻车」。本文把 State 与 Reducer 讲透：完整合并语义、自定义 reducer、消息列表合并、状态设计原则、`Command` 更新机制。读完本文，你能设计出生产可用的 Agent State，并能解释「并行节点写同一个字段到底会发生什么」。本文基于 LangGraph 1.x API，网上 0.x 旧教程的写法（`Annotated[Any, reducer]` 旧用法、`add_edge` 旧参数）注意甄别。

## 学习目标

学完本文，你应该能：

- 说出 reducer 的签名（`reducer(current_value, update_value) -> new_value`）和调用时机；
- 区分「整字段覆盖」「列表追加」「自定义合并」三种更新语义，并说清并行写入同一字段时的行为；
- 手写 2~3 个自定义 reducer（取最大、去重合并、消息窗口裁剪）；
- 说清 `add_messages` 的合并规则与 `RemoveMessage` 的用途；
- 按生产要求设计 State：字段粒度、可序列化、与 Checkpoint 的兼容性；
- 用 `Command(update=..., goto=...)` 在一步内完成「改状态 + 路由」；
- 用 `get_state` / `update_state` 调试和修复运行中的图。

## 一、为什么阶段 4 要重新讲 State

阶段 3 你学到的 State 是「最小够用版」：一个 `TypedDict`、一个 `Annotated[list, operator.add]`。那时你的图只有一条主线（agent -> tools -> agent），节点串行执行，`operator.add` 覆盖了所有「追加」需求。

阶段 4 的场景会把这些假设逐个击破：

| 新场景 | 对 State 的冲击 |
| --- | --- |
| 并行分支（扇出） | 多个节点同时向 State 写数据，合并顺序不再确定 |
| 多 Agent（Supervisor/子 Agent） | 需要「共享上下文 + 各 Agent 私有结果」的分层结构 |
| Checkpoint 恢复 | State 里所有字段必须**可序列化**，否则断点续跑直接炸 |
| 长对话/长任务 | 消息列表无限膨胀，需要**裁剪**而非无脑追加 |
| 人工审批 | 审批结果、拒绝原因要作为状态的一部分被记录和重放 |

一句话：**阶段 3 的 State 是「给图跑的变量」，阶段 4 的 State 是「可以被持久化、回放、修复的数据模型」**。这一层认知的转变，是本文的核心。

类比 Java：阶段 3 的 State 像 Service 方法里的局部 `Context` 对象；阶段 4 的 State 更像**领域模型 + 事件溯源日志**——不仅要描述「当前是什么」，还要能被序列化存库、按历史回放、在异常后重建。

## 二、Reducer 的完整语义

### 2.1 回顾：节点返回 dict 是「字段级更新」

节点返回的 dict **不会替换整个 State**，而是按字段合并：每个 key 独立更新，没出现在返回 dict 里的字段原样保留。这是 LangGraph 一切状态行为的根基。

```python
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

class ReviewState(TypedDict):
    requirement: str      # 需求原文
    analysis: str         # 需求分析结果
    status: str           # 当前阶段

def analyze_node(state: ReviewState) -> dict:
    return {"analysis": "这是一个订单查询需求", "status": "analyzed"}
    # 只更新 analysis 和 status，requirement 原样保留

graph = StateGraph(ReviewState)
graph.add_node("analyze", analyze_node)
graph.add_edge(START, "analyze")
graph.add_edge("analyze", END)
app = graph.compile()
result = app.invoke({"requirement": "实现订单查询", "analysis": "", "status": ""})
# result == {"requirement": "实现订单查询", "analysis": "这是一个订单查询需求", "status": "analyzed"}
```

### 2.2 reducer 的签名与调用时机

给某个字段声明了 reducer（`Annotated[T, reducer_fn]`）后，**每次有节点向该字段写入更新值时**，LangGraph 调用：

```text
new_value = reducer_fn(current_value, update_value)
```

- `current_value`：State 里该字段的现值；
- `update_value`：节点返回 dict 里携带的新值；
- 返回值写入 State。

两个关键点：

1. **reducer 是字段级的**——每个字段独立声明、独立合并，互不影响；
2. **没有声明 reducer 的字段**，默认合并行为就是「覆盖」（`new_value = update_value`），可以理解为每个字段都自带一个默认 reducer `lambda current, update: update`。

```python
from typing import TypedDict, Annotated
import operator

class DocState(TypedDict):
    title: str                                    # 默认覆盖
    tags: Annotated[list[str], operator.add]      # 追加（列表拼接）
    score: Annotated[int, max]                    # 取最大（自定义 reducer，见第三节）
```

### 2.3 默认行为：覆盖

不加 `Annotated` 的字段，后写覆盖先写。这在「单一写入者」的流程里完全够用，但**同一字段如果被两个节点都想「加一点东西」，覆盖就会丢数据**——这正是 `Annotated` 存在的原因。

### 2.4 operator.add 的语义与陷阱

`operator.add` 是内置的加法函数，作为 reducer 时：

- 字段是 `list`：新值 = 旧列表 + 新列表（**拼接**）；
- 字段是 `int` / `float`：新值 = 旧值 + 新值（**求和**）；
- 字段是 `str`：字符串拼接（一般没人这么用）。

```python
# list 拼接
"tags": Annotated[list[str], operator.add]
# 旧值 ["a", "b"] + 新值 ["c"] == ["a", "b", "c"]

# int 求和
"tokens_used": Annotated[int, operator.add]
# 旧值 100 + 新值 50 == 150（多个节点各上报自己消耗的 token，最后得到总量）
```

陷阱：

- **对 `list` 来说 `operator.add` 满足交换律**（`a + b == b + a`），所以多个并行节点追加的顺序不影响最终集合内容——这是它能用于并行场景的原因；
- 但对**带顺序语义**的列表（比如消息列表），拼接顺序会乱——所以消息列表要用专门的 `add_messages`（第四节），而不是 `operator.add`；
- 对 `dict` 用 `operator.add` 会直接报错（`dict` 不支持 `+`）——嵌套结构的合并要用自定义 reducer（3.4）。

### 2.5 并行写入：顺序不确定，reducer 必须「稳」

这是阶段 4 最重要的语义之一。当多个节点从同一个上游节点扇出（并行执行）时，它们的返回 dict 会**逐个**应用合并。**谁先谁后不保证**。因此：

- 并行写**不同字段**：完全安全，互不干扰；
- 并行写**同一字段**：最终结果依赖 reducer 的「交换律/结合律」——`operator.add`（list）和 `max` 都是安全的；而「覆盖」型字段在并行写同一字段时，结果 = 最后被应用的那个，**不确定**，业务上属于设计缺陷。

```python
# 反例：两个并行节点都写 status 覆盖型字段
def node_a(state) -> dict: return {"status": "a-done"}   # 可能是最终值，也可能被覆盖
def node_b(state) -> dict: return {"status": "b-done"}   # 不确定
```

设计纪律：**同一字段只允许一个写入者，或者该字段的 reducer 保证交换律**。后面第 05 篇讲 Checkpoint 时你还会看到，合并顺序不确定也会影响「重放一致性」。

## 三、自定义 Reducer

reducer 就是普通 Python 函数，`Annotated[T, fn]` 里的 `fn` 可以是任何 `(current, update) -> new` 的函数。下面四个是最常用的模式。

### 3.1 取最大/最小

```python
class EvalState(TypedDict):
    max_score: Annotated[int, max]   # 直接用内置 max
    best_plan: Annotated[str, lambda c, u: c if c and len(c) >= len(u) else u]
```

注意 `max` 和 `min` 是内置函数，可直接引用（`Annotated[int, max]` 合法）。

### 3.2 去重合并（集合语义）

```python
class CodeScanState(TypedDict):
    touched_files: Annotated[set[str], lambda c, u: c | u]   # set 并集
```

多个并行节点各自扫描一批文件，最终汇总去重后的文件集合。如果状态要被 Checkpoint 持久化，注意 `set` 需要可序列化（见 5.3）。

### 3.3 追加但只保留最近 N 条（消息窗口裁剪）

长对话里消息列表无限增长会撑爆上下文窗口。一个经典 reducer：**只保留最近 N 条**：

```python
from typing import TypedDict, Annotated

MAX_MESSAGES = 20

def keep_last_n(current: list, update: list) -> list:
    merged = current + update
    return merged[-MAX_MESSAGES:]

class ChatState(TypedDict):
    messages: Annotated[list, keep_last_n]
```

这样无论节点怎么追加，State 里的消息永远不超过 20 条。**但注意**：裁剪发生在写入时，模型看到的是裁剪后的列表——如果模型回复引用了被裁掉的消息，可能产生幻觉。更稳的做法是在**给模型前**显式裁剪（见 4.4 的裁剪节点），而不是在 reducer 里粗暴截断。

### 3.4 嵌套结构的合并（dict 字段的部分更新）

State 字段是 `dict` 时，默认「覆盖」意味着更新整个字典。如果想让多个节点各自更新 dict 里的不同 key：

```python
from typing import TypedDict, Annotated

def merge_dict(current: dict, update: dict) -> dict:
    out = dict(current)          # 复制，别改原对象
    out.update(update)
    return out

class ReportState(TypedDict):
    # 各 agent 把自己负责的章节写进 report 的不同 key
    report: Annotated[dict, merge_dict]

def analysis_agent(state) -> dict:
    return {"report": {"analysis": "需求分析结果……"}}

def risk_agent(state) -> dict:
    return {"report": {"risk": "风险清单……"}}
```

这样需求分析 Agent 和风险检查 Agent **并行**执行时，各自往 `report` 里写不同章节，互不覆盖。这是阶段 4 项目（研发效能 Agent）里最常用的状态结构。

### 3.5 reducer 的注意事项

- **不要修改入参**：`current` 和 `update` 可能是共享对象，务必复制后再改（上面 `merge_dict` 先 `dict(current)`）；
- **保持简单**：reducer 会被反复调用（每次写入都调），不要在里面做 IO；
- **可序列化**：reducer 的输入输出都要能被 Checkpoint 存下来（见 5.3）；
- **函数名即文档**：给 reducer 起能说明语义的名字，别写一堆匿名 lambda。

## 四、消息列表：add_messages 与 MessagesState

### 4.1 为什么消息列表不用 operator.add

消息列表（`messages`）的追加不是简单拼接：模型回复带 `id`，工具结果要**挂到对应的 tool_call 上**，重试/修复时还要能**替换**某条消息。`operator.add` 只会无脑拼接，处理不了这些。

`add_messages` 是 LangGraph 官方提供的消息专用 reducer，规则：

- 新消息**没有 id**：直接追加到末尾；
- 新消息**带 id**：若列表里已存在同 id 消息，**替换**它（而不是再追加一条）；
- 消息里带 `RemoveMessage`（`delete` 类型）：**删除**对应 id 的消息。

```python
from langgraph.graph.message import add_messages
from langchain_core.messages import AIMessage, HumanMessage

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
```

### 4.2 MessagesState：官方预置的消息状态

`MessagesState` 自带 `messages: Annotated[list, add_messages]` 字段，直接继承扩展即可：

```python
from langgraph.graph import MessagesState

class RDAgentState(MessagesState):
    requirement: str        # 需求原文（自定义字段）
    plan: list[str]         # 当前计划
    report: str             # 最终报告
```

这也和阶段 3 用到的 `create_react_agent` 内部结构一致——它内部就是 `MessagesState` 的子类。

### 4.3 RemoveMessage：删消息

长任务里某些消息不该继续给模型看（比如超时的审批请求、已撤回的中间产物）。用 `RemoveMessage` 显式删除：

```python
from langgraph.graph.message import RemoveMessage

def prune_node(state: RDAgentState) -> dict:
    # 删除前 2 条消息（比如旧的 system 指令或已失效的中间消息）
    return {"messages": [RemoveMessage(id=m.id) for m in state["messages"][:2]]}
```

`RemoveMessage` 本身也是一条「消息」，`add_messages` 看到它会执行删除——所以返回 dict 里把它放进 `messages` 列表即可。

### 4.4 上下文裁剪与摘要（长任务必备）

长任务（研发效能 Agent 一次要跑几十轮）必须管理上下文。两种策略：

**策略 A：窗口裁剪**——只保留最近 N 条消息：

```python
def trim_node(state: RDAgentState) -> dict:
    messages = state["messages"]
    if len(messages) > 30:
        return {"messages": messages[-20:]}   # 只留最近 20 条
    return {}
```

**策略 B：摘要压缩**——把早期消息压缩成一段摘要，替换原消息：

```python
def summarize_node(state: RDAgentState, llm) -> dict:
    messages = state["messages"]
    if len(messages) < 40:
        return {}
    early = messages[:-20]                      # 要被压缩的部分
    summary = llm.invoke(f"把以下对话压缩成 200 字以内的摘要：\n{early}")
    # 用摘要消息替换 early 部分，保留最近 20 条原文
    return {"messages": [SystemMessage(content=f"历史摘要：{summary.content}")] + messages[-20:]}
```

工程建议：**裁剪/摘要节点放在「给模型之前」的位置**，而不是在 reducer 里偷偷截断——这样你随时知道模型到底看到了什么，出问题能排查（阶段 5 可观测性会用到这个思路）。

## 五、State 设计原则

### 5.1 字段粒度：单值 vs 列表 vs 结构化

| 字段形态 | 适用场景 | 合并方式 |
| --- | --- | --- |
| 单值（str/int/bool） | 一次性结果、状态标记 | 默认覆盖 |
| 列表 | 追加式结果（消息、错误列表） | `operator.add` / `add_messages` |
| 集合 | 去重汇总（文件列表、影响范围） | set 并集 reducer |
| dict | 分章节/分模块的聚合结果 | `merge_dict` reducer |

经验法则：**一个字段只承载一种语义**。「结果列表」和「最终结果」分开存（`results: list` 收集 + `final_answer: str` 汇总），比挤在一个字段里清晰得多，也方便 Checkpoint 后调试。

### 5.2 共享 State 与私有 State（分层）

多 Agent 场景：所有 Agent 共享「任务上下文」（需求、约束、最终报告），但各 Agent 的**中间思考**不应该互相污染。两种做法：

- **子图自带私有 State**（第 02 篇详讲）：子图内部字段对外不可见，父图只看到子图返回的更新；
- **命名空间字段**：给每个 Agent 一个独立 key，如 `analysis_report`、`risk_report`（配合 3.4 的 `merge_dict`）。

类比 Java：共享 State 是 `ThreadLocal`/请求上下文，私有 State 是方法局部变量——**能局部就别全局**，减少字段间的隐式耦合。

### 5.3 只存可序列化数据（Checkpoint 硬约束）

一旦 `compile(checkpointer=...)`（第 05 篇），**State 里每个字段都会被序列化存库**。这意味着：

- ❌ 不能存：文件句柄、数据库连接、模型实例、函数对象、`asyncio` 任务；
- ✅ 可以存：str、int、float、bool、list、dict、Pydantic 模型、`BaseMessage`（LangChain 消息自带序列化）。

```python
# 反例：把 llm 实例塞进 state —— checkpointer 序列化时直接炸
class BadState(TypedDict):
    llm: ChatOpenAI   # ❌ 不可序列化

# 正例：节点内部创建/获取 llm，state 只存数据
class GoodState(TypedDict):
    model_name: str   # ✅ 存「用什么模型」的配置名，节点内部再去查
```

同理，节点函数本身**不要**把大对象闭包进 reducer 或 State——reducer 是纯函数，别带 IO。

### 5.4 敏感信息不进 State（或进 State 前脱敏）

State 会被序列化、持久化、回放——把 API Key、密码、个人 PII 放进去等于写进日志。规则：

- 工具执行结果进 State 前**脱敏**（阶段 3 的工具审计已有类似纪律）；
- 审批意见、用户身份这类**需要留痕**的信息，进 State 但标记脱敏字段，或走独立审计表（阶段 5 可观测性展开）。

### 5.5 状态演进与兼容

Checkpoint 存的是**历史版本**的 State（每个 step 一份）。如果 State schema 改了（比如新增字段、改字段类型），旧 checkpoint 恢复时可能字段缺失。两条纪律：

- 节点读字段一律 `state.get("field", 默认值)`，不假设字段一定存在；
- 新增字段给默认值语义（用 `TypedDict` 的 `total=False` 或节点内兜底）。

## 六、Command：更新与路由合一

### 6.1 为什么需要 Command

普通节点「返回 dict」只能更新 State，**不能决定下一步去哪**——路由必须靠条件边（`add_conditional_edges`）。但有些场景「改状态 + 选路由」是同一件事：Supervisor 决定把任务交给哪个 Worker 时，要同时「记录交给了谁」和「跳到对应 Worker」。

`Command`（`from langgraph.types import Command`）让节点返回一个对象，同时携带更新和路由：

```python
from langgraph.types import Command

def supervisor_node(state: RDAgentState) -> Command:
    # 读 state 决定下一步（真实场景是问模型）
    next_agent = decide_next(state)
    return Command(
        update={"last_agent": next_agent, "status": "running"},  # 先更新状态
        goto=next_agent,                                          # 再路由
    )
```

### 6.2 Command 与返回 dict 的对比

| 能力 | 返回 dict | 返回 Command |
| --- | --- | --- |
| 更新 State | ✅ | ✅（`update` 字段） |
| 路由到下一节点 | ❌（靠条件边） | ✅（`goto` 字段） |
| 作为条件边的返回值 | 不能 | ✅（`Command` 可直接作为 `add_conditional_edges` 的返回值） |
| 恢复 interrupt | ❌ | ✅（`Command(resume=...)`，第 04 篇） |

在 `add_conditional_edges` 里，router 函数也可以返回 `Command`——LangGraph 会优先处理 `goto`。这是 Supervisor 模式（第 03 篇）的核心写法。

### 6.3 Command 的典型用法

```python
from langgraph.types import Command
from langgraph.graph import StateGraph, START, END

class WorkState(TypedDict):
    todo: str
    done_by: str

def worker_a(state: WorkState) -> dict:
    return {"done_by": "worker-a"}

def worker_b(state: WorkState) -> dict:
    return {"done_by": "worker-b"}

def router(state: WorkState) -> Command:
    # 需要"查询"类任务给 a，其余给 b；同时记录选择
    goto = "worker_a" if state["todo"].startswith("query") else "worker_b"
    return Command(update={"done_by": "pending"}, goto=goto)

graph = StateGraph(WorkState)
graph.add_node("worker_a", worker_a)
graph.add_node("worker_b", worker_b)
graph.add_edge(START, "router")
graph.add_conditional_edges("router", router)   # 返回 Command，自动按 goto 路由
graph.add_edge("worker_a", END)
graph.add_edge("worker_b", END)
app = graph.compile()
print(app.invoke({"todo": "query order status", "done_by": ""}))
# {'todo': 'query order status', 'done_by': 'worker-a'}
```

注意 `goto` 也可以指向 `END`（`Command(update=..., goto=END)`），直接结束。

## 七、调试 State

### 7.1 get_state / get_state_history

配合 Checkpointer（第 05 篇），你可以随时查看图当前状态和每一步的历史：

```python
config = {"configurable": {"thread_id": "task-001"}}
app.invoke({"requirement": "……"}, config=config)

current = app.get_state(config)
print(current.values)      # 当前 State 全部字段
print(current.next)        # 下一步要执行的节点（中断/暂停时很有用）

history = app.get_state_history(config)
for snapshot in history:
    print(snapshot.config["configurable"]["checkpoint_id"], snapshot.values.keys())
```

### 7.2 update_state：手工注入

不重跑图，直接改 State（比如人工修正一个错误的工具结果，然后让图继续）：

```python
app.update_state(config, {"analysis": "修正后的分析"}, as_node="analyze_node")
# 等价于：假装 analyze_node 返回了这个值，后续节点照常执行
```

`update_state` 是「人工审批/外部事件注入」的基础（第 04、07 篇会反复用到）。

### 7.3 stream 观察

用 `stream` 看每一步的更新增量（`stream_mode="updates"` 只输出每个节点返回的 dict，不含全量 state）：

```python
for chunk in app.stream({"requirement": "……"}, config=config, stream_mode="updates"):
    for node_name, update in chunk.items():
        print(f"[{node_name}] 更新了: {list(update.keys())}")
```

## 学习自检与练习

### 练习 1：自定义 reducer——合并 JSON 片段

实现一个 reducer `merge_dict`（3.4 版），然后用它设计一个 `ReportState`：`report: Annotated[dict, merge_dict]`。写两个并行节点（`analysis_agent`、`risk_agent`），各自写 `report` 的不同 key，跑一遍验证两个 key 都在。

自检：如果换成默认覆盖，结果会怎样？为什么？

### 练习 2：消息窗口裁剪节点

用 4.4 的策略 A 写一个 `trim_node`：当 `messages` 超过 30 条时，只保留最近 20 条。把它接在 agent 节点前面（`agent -> trim -> ...`）。用 50 条模拟消息验证裁剪生效。

自检：裁剪节点返回空 dict 时（消息没超限），图是否照常运行？

### 练习 3：用 Command 重构路由

用第六节的例子，把「返回 dict + 条件边」的写法改成「router 返回 `Command(goto=...)`」的写法，对比两种写法的代码量差异。

自检：`Command(update=..., goto=END)` 和 `Command(goto=END)` 的区别是什么？

### 自检清单

- [ ] 能说出 reducer 的签名和调用时机（每次字段被写入时调用）；
- [ ] 能解释「并行节点写同一覆盖型字段 → 结果不确定」，并给出两种规避方法；
- [ ] 能手写取最大、去重合并、dict 部分更新三个自定义 reducer；
- [ ] 能说出 `add_messages` 按 id 替换、`RemoveMessage` 删除的规则；
- [ ] 能列出三类不能放进 State 的数据（连接、文件句柄、模型实例）；
- [ ] 能解释 `Command` 与返回 dict 的能力差异（能否路由）；
- [ ] 会用 `get_state` / `get_state_history` / `update_state` 调试。

## 参考资料

- LangGraph 官方文档 - State 概念与 Reducer: https://langchain-ai.github.io/langgraph/concepts/low_level/#reducers
- LangGraph 官方文档 - MessagesState / add_messages: https://langchain-ai.github.io/langgraph/reference/graphs/#langgraph.graph.message.add_messages
- LangGraph 官方文档 - Command: https://langchain-ai.github.io/langgraph/reference/types/#langgraph.types.Command
- LangGraph 官方文档 - 状态管理 How-to: https://langchain-ai.github.io/langgraph/how-tos/
- 阶段 3 配套：[07-LangGraph入门-StateGraph.md](../阶段3-Tools与MCP/07-LangGraph入门-StateGraph.md)（第 2、6 节是本文的前置知识）
