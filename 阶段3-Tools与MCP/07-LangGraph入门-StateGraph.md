# LangGraph 入门：StateGraph、节点与边

> 本文定位：阶段 3 项目（企业运维分析 Agent）需要的最小子集——用 LangGraph 的 StateGraph 把「模型循环 + 工具调用 + 条件路由」从手写 while 循环升级为可编排、可扩展、可观测的图。读完本文，你能读懂并改写一个带条件路由和工具循环的 StateGraph，理解 State / Node / Edge 与状态更新语义。Reducer 深讲、Checkpoint 持久化、Human-in-the-loop、并行分支与子图等进阶内容留到阶段 4，本文只做预告。本文基于 LangGraph 1.x API（`langgraph` 包，2025 年底主流版本）；网上大量 0.x 旧教程（`ToolExecutor`、`langgraph.prebuilt` 旧路径、`add_conditional_edges` 旧参数名）不再适用，遇到时注意甄别。

## 学习目标

学完本文，你应该能：

- 说出手写 ReAct while 循环的三个以上痛点，并解释 LangGraph 用「图」解决什么问题；
- 用 `TypedDict` 定义 State，用 `add_node` / `add_edge` / `add_conditional_edges` 搭出一个可运行的状态图；
- 写一个根据 state 内容路由的条件边（掌握映射 dict / 直接返回节点名 / 列表三种传法）；
- 用 `bind_tools` + `ToolNode` + `tools_condition` 搭出带最大轮数保护的 Agent 工具循环；
- 解释节点返回 dict 的「覆盖」语义与 `Annotated` reducer 的「追加」语义；
- 会用 `draw_mermaid` / print 调试图，能定位三类常见报错。

## 一、为什么需要编排框架

### 1.1 纯 ReAct while 循环的痛点

在阶段 1 你写过类似这样的工具循环（伪代码）：

```python
def run_agent(user_input: str) -> str:
    messages = [HumanMessage(content=user_input)]
    for _ in range(10):                      # 拍脑袋定的轮数上限
        response = llm_with_tools.invoke(messages)
        if not response.tool_calls:
            return response.content          # 没有工具调用了，收工
        for call in response.tool_calls:
            result = TOOL_REGISTRY[call["name"]](**call["args"])
            messages.append(ToolMessage(content=result, tool_call_id=call["id"]))
    raise RuntimeError("达到最大轮数")
```

单个 Agent 时它还能跑，但一旦流程复杂起来，痛点会集中爆发：

1. **流程硬编码在循环里**：先做什么、后做什么、什么条件下做什么，全埋在 if/else 里。加一个「查询前先鉴权」「写操作前先人工确认」的环节，就要改循环体，牵一发动全身。
2. **状态不显式**：中间结果散落在局部变量和 messages 列表里，谁改了什么、当前在哪一步，只能靠 print 和想象。
3. **难以恢复与重放**：循环一旦中断（超时、异常、进程重启），整个上下文丢失，无法从「上一步」续跑，更别说回放排查。
4. **难以插桩与观测**：想统计每个环节耗时、给某一步加日志/审计，都得在循环体里手工埋点。
5. **难以并行**：多个工具调用天然可以并行（比如同时查订单和查库存），手写循环默认串行。

### 1.2 用「图」表达 Agent 流程

LangGraph 的答案：把流程画成一张**有向图**。图由三样东西构成：

- **State**：全图共享、随执行流动的数据（相当于请求上下文）；
- **Node（节点）**：一步具体处理逻辑（相当于处理器/处理器方法）；
- **Edge（边）**：节点之间的流转关系，包括无条件边和**条件边**（相当于路由表）。

画出来大概是这样（这是本文第五节要实现的 ReAct Agent）：

```text
START --> agent --(有工具调用?)--> tools --> agent
             ^                        |
             |__________(循环)________|
             |
             +-----(无工具调用)------> END
```

### 1.3 手写循环 vs LangGraph

| 维度 | 手写 while 循环 | LangGraph StateGraph |
| --- | --- | --- |
| 流程表达 | if/else 硬编码 | 图：节点 + 边，流程一目了然 |
| 状态 | 局部变量、隐式 | State 显式定义、按节点声明式更新 |
| 路由 | 分支写死在循环里 | 条件边集中管理，改路由不改节点 |
| 恢复/重放 | 不支持 | Checkpoint 持久化（阶段 4） |
| 观测 | 手工 print | 图结构可导出、每步可追踪 |
| 复用 | 复制粘贴 | 节点即函数，天然可复用、可单测 |

### 1.4 Java 类比：从硬编码 if-else 到状态机

你写过 Spring 应用，一定见过两种风格：巨大的 Service 方法里 `if (status == 1) { ... } else if (status == 2) { ... }`——状态流转散落在业务代码里；或者用状态机/工作流引擎（Spring StateMachine、Activiti、Flowable）：**状态 + 事件 + 迁移**显式建模，流程可配置、可审计。

LangGraph 就是 Agent 世界里的「工作流引擎」：`StateGraph` 类比状态机定义，`State` 类比贯穿请求的上下文对象（像 Servlet 的 request/session，或 filter/interceptor 间传递的 `Context`），节点类比 Spring 容器里的处理器（handler 方法），条件边类比 `Router`/策略模式——根据输入选一个分支执行。**把业务逻辑从流程里拆出来**，是两种世界共同的工程哲学。

## 二、核心概念：State、Node、Edge

### 2.1 State：全图共享的数据

State 就是一张贯穿全图的「共享数据表」，用 `typing.TypedDict`（或 Pydantic `BaseModel`）声明有哪些字段：

```python
from typing import TypedDict
class UploadState(TypedDict):
    file_name: str      # 上传的文件名
    file_bytes: bytes   # 文件内容
    checksum: str       # 校验结果
    record_id: str      # 入库后的记录 id
    status: str         # 当前处理阶段
```

类比 Java：一个在 filter 链 / pipeline 里传递的 `Context` 对象——每个环节可以读它、改它，改动对后续环节可见。注意两点：

- State 是**全图共享**的，不是某个节点私有的；
- 节点的输入输出都围绕 State 展开，这让每个节点可以**独立单测**（给它一个 dict，看它返回什么）。

### 2.2 Node：纯函数式处理器

节点就是一个普通函数，签名固定为「**读 state，返回要更新的 state 片段**」；也可以返回 `None`（表示本次不更新任何字段），也支持 async：

```python
def validate_node(state: UploadState) -> dict:
    return {"checksum": compute_checksum(state["file_bytes"]), "status": "validated"}

async def persist_node(state: UploadState) -> dict:
    record_id = await db.insert(...)
    return {"record_id": record_id, "status": "stored"}
```

**重要约定**：节点是「读-算-写」的纯函数，不要在里面偷偷改传入的 state（比如 `state["status"] = "x"` 再返回空 dict）——返回的 dict 才是正式的更新通道（见第六节）。类比 Java：节点就像 `Function<Context, Map<String, Object>>`，或者 pipeline 里的一个 handler，只对自己的输入输出负责。

### 2.3 Edge：普通边与条件边

- **普通边**：`add_edge("a", "b")`——a 执行完无条件走到 b；
- **条件边**：`add_conditional_edges("a", router_fn, mapping)`——a 执行完后，由 router_fn 读 state 决定去哪个节点（第四节详讲）。

类比 Java：普通边是硬编码的调用链，条件边是 `Router`/策略选择器——**把「下一步去哪」从业务代码里抽出来，集中声明**。这正是你熟悉的「路由表」思想：节点只做自己的事，流转交给图。

### 2.4 编译与执行

图定义好后调用 `compile()` 得到可执行对象 `app`，然后 `app.invoke(初始 state)` 同步执行或 `await app.ainvoke(...)` 异步执行：

```python
app = graph.compile()
result = app.invoke({"file_name": "a.txt", "file_bytes": b"..."})
```

类比 Java：`StateGraph` 是「定义」，`compile()` 等价于把 Bean 定义装配成可用的应用上下文（`ApplicationContext`），`invoke` 等价于 `handle()` 入口方法。

### 2.5 贯穿全节的例子：文档上传 -> 校验 -> 入库 -> 完成

用一条流水线把概念串起来（第四、五节的例子都长这样，只是节点内容不同）：

- `upload` 节点：读入文件名与内容，写入 state；
- `validate` 节点：算 checksum、查重，把结果写回 state；
- `store` 节点：把校验通过的内容入库，返回 record_id；
- 三条普通边把四个节点串成一条流水线。

关键点：**流程 = 节点集合 + 边集合**。要插入「先去重再入库」，只需加一个节点、改一条边，`upload`/`validate` 的代码一行不用动——这就是图编排相对硬编码循环的核心收益。也请注意：图里的节点是**声明式注册**的（`add_node`），执行顺序完全由边决定，与注册顺序无关。

## 三、StateGraph 最小示例

### 3.1 完整可运行代码

下面是最小的可运行示例：两个节点流水线（校验 -> 发货），跑一遍看结果。

```python
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
class OrderState(TypedDict):
    order_id: str
    status: str

def validate_node(state: OrderState) -> dict:
    print(f"[validate] order_id={state['order_id']}")
    return {"status": "validated"}

def ship_node(state: OrderState) -> dict:
    print(f"[ship] {state['order_id']} 状态从 {state['status']} 变为 shipped")
    return {"status": "shipped"}

graph = StateGraph(OrderState)
graph.add_node("validate", validate_node)
graph.add_node("ship", ship_node)
graph.add_edge(START, "validate")           # 入口边
graph.add_edge("validate", "ship")          # 普通边
graph.add_edge("ship", END)                 # 出口边
app = graph.compile()
result = app.invoke({"order_id": "A1001", "status": "created"})
print(result)   # {'order_id': 'A1001', 'status': 'shipped'}
```

### 3.2 运行流程解读

1. `invoke` 收到初始 state `{"order_id": "A1001", "status": "created"}`；
2. 从 `START` 进入 `validate`，该节点返回 `{"status": "validated"}`；
3. 沿 `validate -> ship` 边进入 `ship`，返回 `{"status": "shipped"}`；
4. 到达 `END`，返回**执行结束后的完整 state**（所有字段的最终值）——注意 `result` 是合并后的完整 state，而不是最后一个节点的返回值。

### 3.3 节点返回 dict 的合并语义（初窥）

节点返回的 dict **不会替换整个 state，而是按字段合并**：`ship_node` 只返回 `{"status": "shipped"}`，state 里的 `order_id` 原样保留。合并的具体规则（覆盖 vs 追加）在第六节讲，这里先记住：**返回什么就更新什么，没返回的字段不动**。

## 四、条件边与路由

### 4.1 场景：查询类 vs 报表类

运维分析 Agent 里，用户问「订单 A1001 现在什么状态」和「给我一张本月订单统计报表」显然要走不同处理逻辑。先由一个 `classify` 节点判断意图写入 state，再用**条件边**分流：

```python
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

class QueryState(TypedDict):
    question: str
    intent: str   # "query" 或 "report"
    answer: str

def classify_node(state: QueryState) -> dict:
    q = state["question"]
    if "报表" in q or "统计" in q or "汇总" in q:
        return {"intent": "report"}
    return {"intent": "query"}

def query_node(state: QueryState) -> dict:
    return {"answer": f"[查询结果] {state['question']}"}

def report_node(state: QueryState) -> dict:
    return {"answer": f"[报表已生成] {state['question']}"}

def router(state: QueryState) -> str:
    return state["intent"]   # 读 state，返回一个 key
graph = StateGraph(QueryState)
graph.add_node("classify", classify_node)
graph.add_node("query", query_node)
graph.add_node("report", report_node)

graph.add_edge(START, "classify")
# 条件边：classify 执行完后，按 router 返回值查 mapping，决定去哪个节点
graph.add_conditional_edges("classify", router, {"query": "query", "report": "report"})
graph.add_edge("query", END)
graph.add_edge("report", END)
app = graph.compile()
r1 = app.invoke({"question": "订单 A1001 什么状态？"})
r2 = app.invoke({"question": "给我一张本月报表"})
print(r1["answer"])   # [查询结果] 订单 A1001 什么状态？
print(r2["answer"])   # [报表已生成] 给我一张本月报表
```

### 4.2 add_conditional_edges 的三种传法

`add_conditional_edges(source_node, router_fn, mapping)` 的第三个参数 mapping 有四种常见写法：

1. **映射 dict（最常用）**：router_fn 返回 key，按 dict 找到目标节点——上面就是这种。key 可以是任意字符串，目标可以是节点名，也可以是 `END`（如 `{"path1": "b", "path2": END}`）。
2. **直接返回节点名**：router_fn 直接返回目标节点名字符串，不传 mapping（或传 `None`）：

   ```python
   def router(state: QueryState) -> str:
       return "report" if state["intent"] == "report" else "query"
   graph.add_conditional_edges("classify", router)   # 返回值即节点名
   ```

3. **传节点名列表（扇出）**：mapping 传一个 list，router_fn 的返回值被忽略，执行会**同时进入列表中所有节点**：

   ```python
   # classify 之后同时跑 query 和 report 两个分支（可用于并行，阶段 4 展开）
   graph.add_conditional_edges("classify", router, ["query", "report"])
   ```

4. 特殊哨兵：`END` 可以直接出现在 mapping 的值里（如上面的 `{"path2": END}`），也可以作为 router_fn 的返回值（返回字符串 `"__end__"` 同样表示结束——`tools_condition` 就是这么干的，见第五节）。

类比 Java：`router` 函数就是一个 `Router`——输入 state，输出「下一跳」；mapping 就是路由表。**把分支判断集中到一个函数里，而不是散落在各个节点内部**，是图编排的重要纪律。

## 五、Agent 节点与工具循环

### 5.1 模型节点：bind_tools 与 tool_calls

把工具绑给模型，模型在对话中可能返回「我想调用某个工具」的意图。阶段 1 你已经熟悉：

```python
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)   # 以你锁定的依赖版本文档为准
llm_with_tools = llm.bind_tools(tools)
response = llm_with_tools.invoke([HumanMessage(content="订单 A1001 什么状态？")])
print(response.tool_calls)
# [{'name': 'get_order_status', 'args': {'order_id': 'A1001'}, 'id': 'call_xxx', 'type': 'tool_call'}]
```

在 StateGraph 里，模型调用这一步就是一个普通节点（`agent` 节点）：读 state 里的 `messages`，调模型，把新产生的 AIMessage 追加回 state。

### 5.2 ToolNode 与 tools_condition

- **`ToolNode(tools)`**：预置节点，解析上一条 AIMessage 的 `tool_calls`，逐个执行对应工具，并把结果包装成 `ToolMessage` 追加进 `messages`。它相当于一个「自动执行器」——你不需要自己写 for 循环执行工具了。
- **`tools_condition`**：预置的条件路由函数，检查上一条消息**是否还有未执行的工具调用**：有 -> 返回 `"tools"`（去执行工具），没有 -> 返回 `"__end__"`（结束）。它是 `add_conditional_edges` 的 router_fn 直接拿来用。

于是 ReAct 循环变成了一张图：`agent -> (有工具调用?) -> tools -> agent -> (没有?) -> END`。

### 5.3 完整 ReAct Agent 示例（订单查询）

围绕订单查询场景，两个工具，完整可运行：

```python
from typing import TypedDict, Annotated
import operator
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI   # 以你锁定的依赖版本文档为准

# 1. 两个业务工具
def get_order_status(order_id: str) -> str:
    """查询订单当前状态"""
    db = {"A1001": "已发货", "A1002": "待支付"}
    return db.get(order_id, "未找到订单")

def get_order_items(order_id: str) -> str:
    """查询订单包含的商品"""
    db = {"A1001": "机械键盘 x1、鼠标垫 x1", "A1002": "显示器 x1"}
    return db.get(order_id, "未找到订单")

tools = [get_order_status, get_order_items]
llm_with_tools = ChatOpenAI(model="gpt-4o-mini", temperature=0).bind_tools(tools)

# 2. State：messages 用 reducer 追加（第六节讲）
class AgentState(TypedDict):
    messages: Annotated[list, operator.add]

# 3. agent 节点：调模型，返回新消息
def agent_node(state: AgentState) -> dict:
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}
graph = StateGraph(AgentState)
graph.add_node("agent", agent_node)
graph.add_node("tools", ToolNode(tools))
graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", tools_condition)   # 有工具调用 -> tools，否则 -> END
graph.add_edge("tools", "agent")                        # 工具执行完回到 agent，形成循环

app = graph.compile()
# 4. 运行
result = app.invoke({"messages": [HumanMessage(content="订单 A1001 现在什么状态？")]})
for m in result["messages"]:
    print(f"{m.type}: {m.content}")
```

运行时的消息序列大致是：

```text
human: 订单 A1001 现在什么状态？
ai:    [tool_calls: get_order_status(A1001)]
tool:  已发货
ai:    订单 A1001 当前状态为：已发货。      <- 没有新工具调用，循环结束
```

这个例子把阶段 1 手写的 while 循环整体替换成了三行图定义（`add_edge` + `add_conditional_edges` + `add_edge`）。**循环是边画出来的，不是代码写出来的**——这就是图编排的直观收益。

### 5.4 为什么需要终止条件

图的循环天然没有「自动停止」：如果模型每次都说「我还要调工具」，`agent -> tools` 会无限转圈。两个层面的保护：

1. **语义终止（tools_condition）**：模型不再返回 tool_calls 就结束——这是正常收尾；
2. **硬性上限（最大轮数）**：防止模型失控或工具死循环。LangGraph 有内置的 `recursion_limit`（默认 25 次节点执行，超限抛 `GraphRecursionError`），但业务上更可控的是在 state 里加计数器，自己决定「轮数超限后怎么办」（比如走兜底节点告诉用户「问题太复杂，无法在限制内完成」）：

```python
MAX_TURNS = 3
class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    turn: int   # 已执行的模型轮数

def agent_node(state: AgentState) -> dict:
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response], "turn": state.get("turn", 0) + 1}

def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if state.get("turn", 0) >= MAX_TURNS:
        return "end"                       # 超限：强制收尾（生产里可指向兜底节点）
    if getattr(last, "tool_calls", None):
        return "tools"
    return "end"

graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
```

注意：超限后 state 里可能残留未执行的 tool_calls，收尾节点要做「无法完成」的说明，而不是假装成功——工程上的诚实性问题。

## 六、状态更新语义（入门）

### 6.1 默认：覆盖

不加任何修饰的字段，节点返回 dict 时**整字段覆盖**：

```python
class DocState(TypedDict):
    chunks: list
    status: str
def a(state: DocState) -> dict:
    return {"chunks": ["chunk-1", "chunk-2"]}   # 写入 chunks

def b(state: DocState) -> dict:
    return {"chunks": ["chunk-3"]}              # 整字段覆盖！chunk-1/2 没了
```

这符合「后写覆盖先写」的直觉，但有两个节点都想往同一个 list 里**追加**时就出问题了。

### 6.2 追加：Annotated + reducer

给字段加一个「合并函数」（reducer），LangGraph 在写入时调用它来合并新旧值：

```python
from typing import TypedDict, Annotated
import operator

class DocState(TypedDict):
    file_name: str
    chunks: Annotated[list, operator.add]   # 新值 = 旧值 + 新值（列表拼接）
    status: str

def chunk_node(state: DocState) -> dict:
    return {"chunks": ["chunk-1", "chunk-2"]}

def enrich_node(state: DocState) -> dict:
    return {"chunks": ["chunk-3"]}          # 追加而不是覆盖

# chunk_node 和 enrich_node 依次执行后，chunks == ["chunk-1", "chunk-2", "chunk-3"]
```

类比 Java：`Annotated[list, operator.add]` 就像给字段配置了一个合并策略——类似 Java 里集合的 `addAll` 语义 vs 整体 `set` 语义，声明在哪，行为就在哪，调用方无需关心。第五节 Agent 示例里 `messages` 用的正是这种追加语义：每个节点返回的新消息都拼到消息列表尾部。

### 6.3 消息追加与 add_messages

对 `messages` 这类消息列表，LangGraph 官方提供了专用 reducer `add_messages`（按消息 id 去重合并，比 `operator.add` 更稳），也可以直接用官方预置的 `MessagesState`：

```python
from langgraph.graph.message import add_messages
from langgraph.graph import MessagesState   # 自带 messages: Annotated[list, add_messages]

class AgentState(MessagesState):
    turn: int   # 在预置消息状态上扩展自己的字段
```

（以你锁定的依赖版本文档为准。）入门阶段用 `operator.add` 理解「追加」语义即可，`add_messages` 的细节在阶段 4 展开。

### 6.4 留给阶段 4 的内容

- **自定义 reducer**：写自己的合并函数（如「取最大值」「合并去重」）；
- **Checkpoint**：`from langgraph.checkpoint.memory import MemorySaver` + `app.compile(checkpointer=MemorySaver())`，让每次执行可断点续跑、可回放，也是多轮对话记忆的基础（阶段 3 只需要知道有这个东西，深讲在阶段 4）；
- **interrupt（Human-in-the-loop）**：在节点间暂停、等人确认后继续。

## 七、给阶段 3 项目的建议用法

### 7.1 create_react_agent 与手写 StateGraph 的选择

阶段 3 项目（企业运维分析 Agent）里，大部分「查询类」交互可以**直接用预置的 `create_react_agent`**，它内部就是一个装配好的 ReAct 图（agent 节点 + ToolNode + tools_condition），几行代码就能跑：

```python
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

agent = create_react_agent(llm, tools)     # 以你锁定的依赖版本文档为准
result = agent.invoke({"messages": [HumanMessage(content="A1001 状态？")]})
```

什么场景用哪个：

| 场景 | 推荐 | 原因 |
| --- | --- | --- |
| 纯查询、只读工具、单轮问答 | `create_react_agent` | 零配置，够用 |
| 固定流水线（上传->校验->入库） | 手写 StateGraph | 节点顺序和分支是确定的，不需要模型决策 |
| 多阶段 + 条件路由 + 审计节点 | 手写 StateGraph | 每一步都是显式节点，可插桩、可单测 |
| 写操作需要人工确认 | 手写 StateGraph + 人工节点 | 预置 agent 不直接支持插入人工环节 |

经验法则：**模型该决策的地方交给 ReAct 循环，业务该固定流程的地方画成显式图**。一个 Agent 里完全可以两者共存——查询走 `create_react_agent`，写操作走一条带人工节点的子流程。

### 7.2 什么时候需要人工节点（预告）

写操作（改配置、发命令、删数据）不能直接让模型自动执行——阶段 3 的 [03 安全篇](03-工具安全-RBAC权限与人工确认.md) 已经讲过「写操作要人工确认」。在 LangGraph 里这对应「人工节点」：执行到写操作前**暂停**，把待确认内容展示给用户，确认后继续、拒绝则中止。具体实现用的是 `interrupt`（配合 Checkpoint），这是阶段 4 的内容；**现在你只需要知道：设计图的时候，为写操作预留「待确认」这个状态和分支，别把写操作直接连到 END**。

## 八、调试与可视化

### 8.1 langgraph dev

`langgraph-cli` 提供的本地开发服务（`langgraph dev`，配合项目里的 `langgraph.json`），启动后可以在浏览器里用 LangGraph Studio 可视化地观察图结构、逐步执行、查看每一步 state 变化。它相当于 Agent 版「断点调试器」。阶段 3 先用 `print` 和 `draw_mermaid` 即可，Studio 深用放在阶段 5 可观测性篇（以你锁定的依赖版本文档为准）。

### 8.2 draw_mermaid

编译后的 `app` 可以把图结构导出成 Mermaid 文本，粘到 mermaid.live 等工具里渲染成图：

```python
print(app.get_graph().draw_mermaid())
# 输出 mermaid 文本（flowchart TD 格式），可贴到 mermaid.live 渲染成图
```

`draw_mermaid_png()` 可以直接输出图片，但需要额外系统依赖（graphviz 等），以你锁定的依赖版本文档为准。**每写完一张图，先导出看一眼拓扑是否符合预期**——这是发现「边接错」的最快方式。

### 8.3 print 调试

节点是普通函数，直接在里面 print 即可，配合「节点名 + 关键字段」的日志约定：

```python
def validate_node(state: UploadState) -> dict:
    print(f"[validate] file={state['file_name']} size={len(state['file_bytes'])}")
    ...
```

注意别把敏感信息（token、SQL）打全量日志——这和你写 Java 打日志的纪律一致。

### 8.4 常见报错与排查

| 报错现象 | 原因 | 对策 |
| --- | --- | --- |
| `KeyError: 'xxx'` | 节点读取的 state 键从未写入/未初始化 | 在 invoke 初始 state 里给全字段，或节点内用 `state.get("xxx", 默认值)` |
| 节点返回非 dict 报错 | 节点返回了 str / 裸对象 | 节点必须返回 dict 或 `None`（`None` 表示不更新） |
| `GraphRecursionError: Recursion limit ... reached` | 循环没有终止条件，或轮数不够 | 确认 `tools_condition`/`should_continue` 接对了；必要时调 `config={"recursion_limit": N}` 或加 MAX_TURNS |
| `add_edge` / mapping 里引用了不存在的节点名 | 节点名拼写不一致 | 以 `add_node` 注册的名字为准，统一用常量 |

排查套路：**先导出 mermaid 看拓扑，再在关键节点加 print 看 state，最后看报错栈指向哪个节点**——和你在 Java 里「先看调用链、再打断点」是同一套方法论。

## 学习自检与练习

### 练习 1：三节点条件流程图

用 StateGraph 实现：接收一个整数 `n`，`n > 0` 走 `positive` 节点（返回 `"正数"`），`n < 0` 走 `negative` 节点（返回 `"负数"`），`n == 0` 走 `zero` 节点。要求：

- 用 `TypedDict` 定义 state（至少含 `n` 和 `label` 两个字段）；
- 用一个 `router` 函数集中判断，用映射 dict 方式接条件边；
- 跑三个用例（1、-1、0）分别验证输出。

自检：三个节点是否都可达？`router` 返回的 key 和 mapping 的 key 是否一一对应？

### 练习 2：把阶段 1 的手写工具循环改造成 StateGraph

把你在阶段 1 写的 ReAct while 循环改造为 StateGraph 版本：

- 工具注册表换成 `ToolNode(tools)`；
- 循环终止换成 `tools_condition` + `add_conditional_edges`；
- 保留你自己的业务工具（可以就用本文的订单查询两个工具）；
- 改造前后各跑一个用例，对比「循环控制逻辑」的代码量。

自检：改造后，如果新增一个工具，需要改哪些地方？（答案：只改 `tools` 列表，图定义和节点代码不用动。）

### 练习 3：给 Agent 加最大轮数保护

在第五节 5.3 的示例基础上：

- 按 5.4 的方式加 `turn` 计数和 `should_continue`（MAX_TURNS=3）；
- 故意构造一个会让模型反复调工具的 prompt（例如「把 A1001 和 A1002 的状态、商品都查一遍，再查一遍，再查一遍……」）；
- 验证：轮数达到上限后图正常结束（而不是抛 `GraphRecursionError`），并观察收尾时的消息序列。

自检：超限时最后一条消息是什么？如果它是带 tool_calls 的 AIMessage，你的收尾逻辑是否给出了明确交代？

### 自检清单

- [ ] 能画出「agent -> tools 循环 -> END」的图，并解释每个节点的输入输出；
- [ ] 能说出条件边三种传法的区别，以及 `END` 作为目标/返回值的使用方式；
- [ ] 能解释「节点返回 dict 默认覆盖；`Annotated[list, operator.add]` 追加」；
- [ ] 知道 `tools_condition` 返回 `"tools"` 或 `"__end__"` 的含义；
- [ ] 知道「查询类用 `create_react_agent`、固定流水线用手写 StateGraph」的取舍；
- [ ] 能说出 Checkpoint / interrupt 是阶段 4 的内容，但知道它们解决什么问题；
- [ ] 会用 `draw_mermaid` 导出图，能排查三类常见报错。

## 参考资料

- LangGraph 官方文档（Graphs 概念、StateGraph 指南）: https://langchain-ai.github.io/langgraph/
- LangGraph API Reference（StateGraph / add_conditional_edges / prebuilt）: https://langchain-ai.github.io/langgraph/reference/graphs/
- create_react_agent 官方指南: https://langchain-ai.github.io/langgraph/how-tos/create-react-agent/
- LangGraph 中文文档: https://langgraph-cn.com/
- 阶段 3 配套文档：[03 工具安全：RBAC 权限、只读/写入分离与人工确认](03-工具安全-RBAC权限与人工确认.md)、[06 MCP Client 与 Agent 集成](06-MCP-Client与Agent集成.md)、[08 阶段 3 综合实践：企业运维分析 Agent](08-阶段3综合实践-企业运维分析Agent.md)
