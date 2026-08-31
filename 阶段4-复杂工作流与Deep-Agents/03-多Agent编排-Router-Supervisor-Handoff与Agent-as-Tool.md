# 多 Agent 编排：Router、Supervisor、Handoff 与 Agent as Tool

> 本文定位：学习路线对阶段 4 有句重要提醒——「**不要一开始堆多个 Agent**。生产系统通常采用『确定性工作流 + 少量 Agent 决策节点』」。本文先讲清楚多 Agent 的代价（为什么默认不要堆），再逐个拆解四种主流编排模式：**Router（路由分发）、Supervisor（主管分配）、Handoff（对话移交）、Agent as Tool（Agent 即工具）**——每种模式给出 LangGraph 图实现、适用场景和反面教材。读完本文，你能根据业务场景选对模式，而不是「为了多 Agent 而多 Agent」。前置知识：[01 篇](01-LangGraph深入-Reducer与状态设计.md)（Command）、[02 篇](02-LangGraph进阶-并行分支与子图.md)（子图）。基于 LangGraph 1.x API。

## 学习目标

学完本文，你应该能：

- 说出多 Agent 的至少四种代价，并判断「单 Agent + 好工具」何时已经够用；
- 用条件边实现 Router 模式，说出它适合/不适合的场景；
- 用「Supervisor 节点 + Command(goto) 循环」实现 Supervisor 模式，并做好结束保护；
- 解释 Handoff 模式的实现思路（模型输出 handoff 工具调用 → 路由）；
- 把编译后的子 Agent 包装成工具（Agent as Tool），并对比它与子图节点的差异；
- 用选型矩阵为一个具体场景选模式，遵守「最少 Agent」「确定性优先」纪律。

## 一、先泼冷水：多 Agent 的代价

### 1.1 四个代价

| 代价 | 说明 |
| --- | --- |
| **成本** | 每个 Agent 都是一次次 LLM 调用。Supervisor 每轮决策一次、Worker 每步执行一次，10 步任务可能烧掉几十次调用。成本 = 调用次数 × 单价，先算账再上多 Agent |
| **延迟** | 串行多 Agent 的延迟是各 Agent 延迟之和；并行虽然有改善，但 Supervisor 的「决策轮」天然串行 |
| **失控面** | Agent 越多，错误传播路径越多：A 的幻觉变成 B 的输入，B 的输出再误导 C。排查一条「谁把需求理解歪了」要翻完所有 Agent 的轨迹 |
| **工程复杂度** | State 设计、上下文传递、失败恢复、评测都要乘以 Agent 数量。多 Agent 系统的调试成本是单 Agent 的数倍 |

### 1.2 什么时候「单 Agent + 好工具」就够了

判断标准很简单：

- 任务可以被**一个模型**在**一个上下文中**完成（哪怕要多调几个工具）；
- 任务不需要「不同角色、不同 prompt、不同模型」的**专业分工**；
- 任务的每一步不需要**独立控制流**（并行、分支、人工介入点）。

研发效能 Agent 的第一版就应该这样做：**一个 ReAct Agent + 一堆工具（查需求、查代码、查测试、写报告）**。阶段 3 你已经会了（`create_react_agent`）。多 Agent 是**当单 Agent 撑不住时**再引入的演进，不是起点。

类比 Java：先写一个 Service 把活干完，再考虑拆模块；一上来就微服务化（每个 Agent 一个「服务」）只会让系统更难维护。**「确定性工作流 + 少量 Agent 决策节点」**——确定性部分（流水线、校验、汇聚）用图写死，只有真正需要模型判断的地方（意图分类、任务分配、方案生成）才放 Agent。

## 二、Router 模式：按任务类型分发

### 2.1 定义

**一个 Router 节点读 State，把任务分发给多个专用 Agent；每个 Agent 各干各的，互不相通。** 这是最简单、最可控的多 Agent 模式——没有循环、没有 Agent 间通信，本质是「意图分类 + 分支执行」。

### 2.2 图实现

```python
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import create_react_agent

class RouterState(TypedDict):
    task: str
    intent: str        # router 填写的意图
    result: str

# 三个专用 Agent（阶段 3 已会 create_react_agent，这里用占位函数）
def requirement_agent(state: RouterState) -> dict:
    return {"result": f"[需求分析] {state['task']}"}

def code_agent(state: RouterState) -> dict:
    return {"result": f"[代码检索] {state['task']}"}

def test_agent(state: RouterState) -> dict:
    return {"result": f"[测试分析] {state['task']}"}

def router(state: RouterState) -> str:
    # 简单关键词分类；真实场景用 LLM 分类（一个轻量模型调用）
    task = state["task"]
    if "测试" in task or "用例" in task:
        return "test"
    if "代码" in task or "实现" in task:
        return "code"
    return "requirement"

graph = StateGraph(RouterState)
graph.add_node("router", router)
graph.add_node("requirement", requirement_agent)
graph.add_node("code", code_agent)
graph.add_node("test", test_agent)
graph.add_edge(START, "router")
graph.add_conditional_edges("router", router,
    {"requirement": "requirement", "code": "code", "test": "test"})
for n in ("requirement", "code", "test"):
    graph.add_edge(n, END)
app = graph.compile()
```

### 2.3 适用与不适用

**适用**：

- 任务类型可以清晰分类，且**每类任务的处理方式完全不同**（查询类走 RAG、生成类走文档 Agent）；
- 各 Agent 之间不需要协作，结果互不依赖；
- 分类是「一次性」的——路由完就结束，不回头。

**不适用**：

- 任务需要**多步接力**（A 的结果是 B 的输入）——那是流水线/Supervisor 的活；
- 分类边界模糊——Router 分错类，任务就彻底跑偏，比单 Agent 更糟；
- 需要 Agent 之间交换信息——Router 天生没有通信通道。

类比 Java：Router 就是「策略选择器 / 网关」——按请求头把请求分发给不同 Service。简单、快，但只解决「分发」这一件事。

## 三、Supervisor 模式：主管分配与回收

### 3.1 定义

**一个 Supervisor Agent 反复决策「下一步交给哪个 Worker」，Worker 干完回来报告，Supervisor 判断任务是否完成、要不要换人/收尾。** 这是最接近「团队协作」的模式，也是研发效能 Agent（阶段 4 项目）的主干。

流程：

```text
用户任务
  -> Supervisor：谁来处理？
  -> Worker A 执行（需求分析）
  -> Supervisor：结果如何？下一步？
  -> Worker B 执行（技术方案）
  -> Supervisor：完成了吗？-> 完成 -> 收尾
```

### 3.2 图实现：Supervisor 节点 + Command(goto) 循环

关键机制：Supervisor 节点绑定一个「路由工具」（列出可用的 Worker 名），模型返回「交给谁」，Supervisor 节点返回 `Command(goto=worker)`；Worker 干完回到 Supervisor，形成循环，直到模型选择「结束」。

```python
from typing import TypedDict, Annotated
import operator
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.graph.message import add_messages
from langgraph.types import Command
from langchain_core.messages import HumanMessage

class TeamState(MessagesState):
    # messages 记录整个协作过程（所有 Agent 的对话都追加进来）
    next_worker: str

# 三个 Worker（这里用占位函数；真实场景是 create_react_agent 或子图）
def worker_analysis(state: TeamState) -> dict:
    return {"messages": [AIMessage(content="需求分析完成：……")]}

def worker_design(state: TeamState) -> dict:
    return {"messages": [AIMessage(content="技术方案完成：……")]}

def worker_test(state: TeamState) -> dict:
    return {"messages": [AIMessage(content="测试用例完成：……")]}

# Supervisor：绑定「选人」工具，返回 Command 路由
from langchain_core.tools import tool

@tool
def assign_to(worker: str) -> str:
    """把下一步工作交给指定 Worker。可选: analysis / design / test / finish"""
    return f"assigned to {worker}"

def supervisor(state: TeamState) -> Command:
    # 真实场景：llm_with_tools.invoke(state["messages"])，模型选择 worker
    # 这里用占位逻辑演示：按消息内容选下一步
    last = state["messages"][-1].content
    if "完成" in str(last):
        return Command(goto=END)          # 都干完了，收尾
    return Command(goto="analysis")       # 否则先让 analysis 干活

graph = StateGraph(TeamState)
graph.add_node("supervisor", supervisor)
graph.add_node("analysis", worker_analysis)
graph.add_node("design", worker_design)
graph.add_node("test", worker_test)
graph.add_edge(START, "supervisor")
for worker in ("analysis", "design", "test"):
    graph.add_edge(worker, "supervisor")   # 所有 Worker 干完都回 Supervisor（循环）
app = graph.compile()

result = app.invoke({"messages": [HumanMessage(content="分析这个需求并出方案")]})
```

关键点：

- **循环是画出来的**：`worker -> supervisor` 的边让 Supervisor 可以多次决策；
- **结束条件在 Supervisor 手里**：模型决定「finish」或轮数用尽才结束——**必须有轮数保护**（01 篇 / 02 篇的 recursion_limit 或 State 计数器），否则 Supervisor 可能无限换人；
- **消息共享**：所有 Worker 的消息追加到同一个 `messages`（`add_messages`），Supervisor 能看到完整协作历史——这既是优势（上下文完整）也是成本（上下文膨胀，需要裁剪，01 篇 4.4）。

### 3.3 适用与不适用

**适用**：

- 任务流程**不确定**，需要动态决定执行顺序和参与方；
- 多个 Worker 有**专业分工**（分析、方案、测试用不同 prompt/模型）；
- 需要一个「总指挥」统一决策和收尾。

**不适用**：

- 流程是**固定的**（先 A 再 B 再 C）——固定流程应该画成显式流水线（确定性工作流），让 Supervisor 每轮问模型「下一步干嘛」纯属浪费且引入不确定性；
- Worker 数量多且并行——Supervisor 天然串行决策，高扇出并行场景用 02 篇的扇出/子图更合适。

纪律：**能用显式边表达的流程，就别让模型决策**（呼应学习路线「确定性工作流 + 少量 Agent 决策节点」）。Supervisor 只该出现在「确实需要动态决策」的地方。

类比 Java：Supervisor 就是「工作流引擎 + 人工调度」——像 Spring Batch 的 Job/Step 框架里由调度器决定 step 顺序；但 Spring Batch 的 step 顺序是**配置死的**，Supervisor 的灵活换来的是不确定性和成本，要按需使用。

## 四、Handoff 模式：Agent 间对话移交

### 4.1 定义

**Agent 在对话过程中主动把「话头」移交给另一个 Agent**（比如客服机器人：售前 Agent 发现用户要退货，主动移交给售后 Agent，并把对话历史一起带过去）。与 Supervisor 的区别：**没有总指挥**，每个 Agent 自己决定「我处理不了，交给谁」。

### 4.2 实现思路

模型绑定一组 `handoff_*` 工具（每个工具对应一个可移交的目标），模型在回复中调用 `handoff_support` 工具 → 工具执行层识别后返回 `Command(goto="support")` 并把对话历史保留在共享 `messages` 里：

```python
from langchain_core.tools import tool

@tool
def handoff_to_support() -> str:
    """把当前对话移交给售后支持 Agent（当用户问题涉及退换货/投诉时调用）"""
    return "handing off to support"

# Agent A（售前）绑定 handoff_to_support；其工具执行结果触发路由：
def tool_router(state) -> Command:
    last = state["messages"][-1]
    for call in getattr(last, "tool_calls", []) or []:
        if call["name"] == "handoff_to_support":
            return Command(goto="support_agent")    # 移交
    return Command(goto="sales_agent")              # 继续自己处理
```

对比：OpenAI Agents SDK 的 **handoff** 也是同一思想——Agent 返回一个 handoff 对象，运行时切换到目标 Agent 并把上下文带过去。LangGraph 里用「handoff 工具 + Command(goto)」表达。

### 4.3 适用与不适用

**适用**：

- **多角色对话**场景（客服、工单流转），需要保留对话连贯性；
- 角色边界清晰、可自然交接（「这个问题归售后管」）；
- 不需要统一收尾（谁接手谁负责到底）。

**不适用**：

- 单角色任务流水线（那是 Supervisor/流水线的事）；
- 需要严格审计「谁对最终结果负责」的场景——Handoff 的职责边界靠模型自觉，容易互相甩锅。

类比 Java：Handoff 像「客服转接」——坐席 A 把工单转给坐席 B，带着完整聊天记录。而 Supervisor 像「工单调度中心」——分配、跟踪、结单都归调度中心。

## 五、Agent as Tool：把 Agent 封装成工具

### 5.1 定义

**把一个完整 Agent（编译后的图）包装成一个工具，主 Agent 像调用普通工具一样调用它。** 主 Agent 负责整体规划，子 Agent 负责「需要深度能力」的子任务，子 Agent 的执行细节对主 Agent 透明。

### 5.2 实现：子 Agent 包装成工具

```python
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import StructuredTool
from langchain_core.messages import HumanMessage

# 1. 先编译一个"代码检索 Agent"（内部可以有自己的工具集）
code_search_agent = create_react_agent(model, tools=[gitlab_search_tool, grep_tool])

# 2. 包装成工具
def run_code_search(query: str) -> str:
    result = code_search_agent.invoke(
        {"messages": [HumanMessage(content=f"搜索代码并总结：{query}")]})
    return result["messages"][-1].content

code_search_tool = StructuredTool.from_function(
    func=run_code_search,
    name="code_search_agent",
    description="深入代码仓库检索并总结。当需要理解代码实现时调用。",
)

# 3. 主 Agent 绑定这个工具
main_agent = create_react_agent(model, tools=[code_search_tool, other_tools])
```

主 Agent 视角里 `code_search_agent` 就是个黑盒工具：传入查询，返回结论。**子 Agent 的内部思考（多轮工具调用）不会污染主 Agent 的上下文**——只把最终结论传回来，这是它最大的价值（上下文隔离）。

### 5.3 对比：子图节点 vs Agent as Tool

| 维度 | 子图节点（02 篇 4 节） | Agent as Tool |
| --- | --- | --- |
| 调用方式 | 图结构决定（边/条件边） | 模型决定（tool_calls） |
| 上下文传递 | 共享 State 通道 | 参数传输入、返回值收结果（黑盒） |
| 灵活性 | 高（结构可控） | 高（模型自主决定何时调用） |
| 可控性 | 高（流程显式） | 低（依赖模型判断） |
| 典型场景 | 固定子流程、并行子任务 | 「深度能力」按需调用（代码搜索、文档分析） |

### 5.4 适用与不适用

**适用**：

- 主 Agent 需要**按需深度能力**，且子能力边界清晰（「查代码」「分析文档」）；
- 希望**隔离子任务的上下文**（子 Agent 的中间步骤不占用主 Agent 的窗口）；
- 子能力可独立测试、独立演进。

**不适用**：

- 子任务需要**和主流程共享状态**（共享的中间结果、审批状态）——子图节点更合适；
- 调用链过深（主 Agent 调子 Agent，子 Agent 又调孙 Agent）——上下文逐层丢失，错误难以追溯。**最多两级**。

## 六、选型矩阵与编排纪律

### 6.1 选型矩阵

| 场景特征 | 推荐模式 | 为什么 |
| --- | --- | --- |
| 任务类型清晰、一次性分发、Agent 互不通信 | Router | 最简单、零循环、零通信 |
| 流程固定（先 A 再 B 再 C） | 确定性流水线（显式图，不是多 Agent！） | 模型决策是浪费，显式边可控 |
| 流程动态、需要总指挥、角色分工 | Supervisor | 一个决策点 + 多个 Worker |
| 多角色对话、自然转接 | Handoff | 保留对话连贯性，无总指挥 |
| 主 Agent 需要按需深度能力 | Agent as Tool | 黑盒调用 + 上下文隔离 |
| 固定流程 + 需要并行分析 | 扇出/子图（02 篇） | 并行是结构问题，不是 Agent 问题 |

### 6.2 五条编排纪律

1. **最少 Agent**：先单 Agent + 工具，撑不住再加一个；每加一个 Agent，成本、延迟、失控面各 +1；
2. **确定性优先**：能用边、用 reducer、用显式节点表达的流程，不要让模型决策；
3. **单一决策点**：一个流程里通常只需要一个 Supervisor/Router，多个决策点互相打架；
4. **循环保护**：任何带循环的多 Agent 图，必须配轮数上限（State 计数器 / recursion_limit）；
5. **成本预算**：给整个任务设定最大 LLM 调用次数，超预算走兜底（降级回答、转人工）。

## 学习自检与练习

### 练习 1：Router 模式

用 2.2 的结构实现：输入一句话，含「测试」→ 走 test_agent，含「代码」→ 走 code_agent，其他 → requirement_agent。跑三个用例验证。再想想：如果任务同时含「代码」和「测试」（「给这段代码写测试」），你的 Router 会怎样？怎么改进？（提示：多标签 or 交给单 Agent）

### 练习 2：Supervisor 模式

用 3.2 的结构实现带两个 Worker（analysis / design）的 Supervisor 循环，并加轮数保护：State 里加 `rounds` 计数器，Supervisor 决策超过 3 轮强制 `Command(goto=END)`。用「让 Supervisor 一直选 analysis」的占位逻辑验证保护生效。

自检：如果不加轮数保护，这个图会怎样？（提示：无限循环 → GraphRecursionError）

### 练习 3：Agent as Tool

把阶段 3 的「订单查询 Agent」编译后包装成工具，再创建一个主 Agent 绑定它，问主 Agent「帮我查一下 A1001 订单状态，再给我生成一份简短的总结」，验证主 Agent 通过工具调用拿到了子 Agent 的结论。

自检：主 Agent 的 `messages` 里能看到子 Agent 内部的工具调用吗？（提示：5.2 上下文隔离）

### 自检清单

- [ ] 能说出多 Agent 的四种代价，能判断「单 Agent 何时够用」；
- [ ] 能画 Router、Supervisor、Handoff、Agent as Tool 四种模式的图结构；
- [ ] 能说出 Supervisor 循环为什么必须配轮数保护；
- [ ] 能区分「子图节点」和「Agent as Tool」的适用场景；
- [ ] 能背出五条编排纪律，并解释「确定性优先」；
- [ ] 知道阶段 4 项目（研发效能 Agent）应该以哪种模式为主干（Supervisor，08 篇详讲）。

## 参考资料

- LangGraph 官方文档 - Multi-agent 架构: https://langchain-ai.github.io/langgraph/concepts/multi_agent/
- LangGraph 官方文档 - Supervisor 示例: https://langchain-ai.github.io/langgraph/how-tos/multi-agent/supervisor/
- LangGraph 官方文档 - Handoff 示例: https://langchain-ai.github.io/langgraph/how-tos/multi-agent/handoff/
- OpenAI Agents SDK - Handoff 概念: https://openai.github.io/openai-agents-python/handoffs/
- 阶段 4 配套：[02-LangGraph进阶-并行分支与子图.md](02-LangGraph进阶-并行分支与子图.md)（子图与扇出）、[01-LangGraph深入-Reducer与状态设计.md](01-LangGraph深入-Reducer与状态设计.md)（Command）
