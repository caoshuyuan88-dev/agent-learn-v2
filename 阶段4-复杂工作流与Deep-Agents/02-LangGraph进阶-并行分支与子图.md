# LangGraph 进阶：并行分支、动态图与子图

> 本文定位：阶段 3 的图是「一条主线 + 条件分支」。阶段 4 的工作流要处理**并行**：同时查多个数据源、同时对多个文件做分析、把大任务拆给多个子 Agent。本文讲三件事：静态扇出/汇聚、`Send` 动态扇出、子图（图作为节点），外加并行场景的保护与容错（RetryPolicy、轮数限制、超时）。读完本文，你能把「一个任务拆成多个并行子任务，再合并结果」用 LangGraph 正确地画出来，并知道并行写入 State 的合并规则（承接 [01 篇](01-LangGraph深入-Reducer与状态设计.md)）。基于 LangGraph 1.x API。

## 学习目标

学完本文，你应该能：

- 用「扇出（fan-out）+ 汇聚（fan-in）」实现静态并行，并解释并行节点返回值的合并规则；
- 用 `Send` API 实现动态扇出（子任务数量和内容在执行期才知道）；
- 把编译后的图作为子图嵌进父图，处理父子 State 的通道映射；
- 给节点配置 `RetryPolicy` 重试，理解 `recursion_limit` 与轮数保护；
- 说出「并行写同一覆盖字段」的风险，并用 reducer 或字段拆分规避（复习 01 篇 2.5）。

## 一、为什么需要并行

### 1.1 三个典型场景

1. **多数据源并行查询**：研发效能 Agent 要同时查「Jira 需求状态」「GitLab 代码变更」「CI 测试结果」——三个独立调用，串行做浪费时间，并行做把延迟从「三者之和」降到「三者之最」；
2. **多路分析**：同一个需求文档，同时让「合规检查」「性能风险」「安全风险」三个检查器分析，结果合并成一份报告；
3. **动态子任务**：对「本次变更涉及的 12 个文件」逐个做 Code Review——文件数量在运行期才知道。

### 1.2 并行 ≠ 复杂

在 LangGraph 里，并行不需要引入线程池/队列——**图的结构本身就能表达并行**：一个节点连出多条边，下游节点就并行执行。你不需要手动 `asyncio.gather`（LangGraph 内部对 async 节点天然并发调度）。你要做的只是：画对边、合并好返回值、保护好失败。

类比 Java：串行是 `for` 循环逐个处理，并行是 `CompletableFuture` / 虚拟线程 + `join`；LangGraph 的「扇出」相当于一次性 `submit` 多个任务，**汇聚节点**相当于 `join` 所有任务——区别是并行和汇聚都由图结构声明，不用你写线程代码。

## 二、静态并行：扇出与汇聚

### 2.1 最小示例：三个并行分析器

```python
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END

def merge_dict(current: dict, update: dict) -> dict:
    out = dict(current)
    out.update(update)
    return out

class ReportState(TypedDict):
    requirement: str
    # 各分析器把结果写进 report 的不同 key（用 01 篇 3.4 的 merge_dict）
    report: Annotated[dict, merge_dict]

def compliance_check(state: ReportState) -> dict:
    return {"report": {"compliance": "合规检查：通过（无敏感数据）"}}

def performance_check(state: ReportState) -> dict:
    return {"report": {"performance": "性能检查：查询接口无索引，建议加索引"}}

def security_check(state: ReportState) -> dict:
    return {"report": {"security": "安全检查：登录接口缺限流，建议补充"}}

def merge_report(state: ReportState) -> dict:
    # 汇聚节点：把各章节拼成最终报告（这里只是示例）
    report = state["report"]
    return {"final_report": "\n".join(f"- {k}: {v}" for k, v in report.items())}

class FullState(ReportState):
    final_report: str

graph = StateGraph(FullState)
graph.add_node("compliance", compliance_check)
graph.add_node("performance", performance_check)
graph.add_node("security", security_check)
graph.add_node("merge", merge_report)

graph.add_edge(START, "compliance")
graph.add_edge(START, "performance")      # 从 START 直接扇出到三个节点
graph.add_edge(START, "security")

graph.add_edge("compliance", "merge")     # 三条边汇聚到 merge
graph.add_edge("performance", "merge")
graph.add_edge("security", "merge")
graph.add_edge("merge", END)

app = graph.compile()
result = app.invoke({"requirement": "实现用户登录", "report": {}, "final_report": ""})
print(result["final_report"])
```

关键点：

- **扇出**：从同一个节点（这里是 `START`）连出多条边，下游节点并行执行；
- **汇聚**：多个上游节点都连到同一个下游节点，**所有上游完成后**才执行汇聚节点（LangGraph 自动做「等所有入边都到达」的同步）；
- **并行写 State**：三个分析器各自写 `report` 的不同 key，靠 `merge_dict` 合并（01 篇 3.4）——**不同 key 并行写是安全的**。

### 2.2 并行写入的合并规则（承接 01 篇 2.5）

| 并行写入情况 | 是否安全 | 说明 |
| --- | --- | --- |
| 写不同字段 | ✅ 安全 | 字段级合并，互不影响 |
| 写同一字段，reducer 满足交换律（`operator.add`/`max`/set 并集） | ✅ 安全 | 顺序无关，结果确定 |
| 写同一字段，默认覆盖 | ⚠️ 不确定 | 最后应用者胜，取决于调度顺序 |

工程结论：**并行分支之间，要么写不同字段，要么给共享字段配交换律 reducer**。你在 2.1 里看到的就是「写不同 key」的典范。

### 2.3 并行分支各自出错的隔离

并行分支中一个节点抛异常，LangGraph 默认**整个执行失败**（异常传播）。如果你希望「一个分支失败不拖垮整体」，两种做法：

1. 分支内 try/except，把错误写成状态（推荐——错误也是分析结果）：

```python
def compliance_check(state: ReportState) -> dict:
    try:
        result = run_compliance(state["requirement"])
        return {"report": {"compliance": result}}
    except Exception as e:
        return {"report": {"compliance": f"检查失败：{e}"}, "errors": ["compliance"]}
```

2. 汇聚节点里容忍缺失 key（读不到就当没结果）：

```python
def merge_report(state: ReportState) -> dict:
    report = state["report"]
    sections = [f"- {k}: {v}" for k, v in report.items()]
    if not sections:
        sections = ["- （所有分析均未返回结果）"]
    return {"final_report": "\n".join(sections)}
```

类比 Java：这就像 `CompletableFuture` 里每个任务自己 `exceptionally` 兜底，而不是让整个 `allOf` 抛异常。

## 三、动态扇出：Send API

### 3.1 什么时候用 Send

2.1 的扇出是**静态**的：三个节点写死在图定义里。但研发效能场景经常是：**要处理多少个文件、多少个子任务，运行期才知道**。比如「对变更涉及的 12 个文件逐个 Review」——你不能为 12 个文件画 12 个节点。

`Send`（`from langgraph.types import Send`）解决这个问题：它让你**在执行期**决定「往同一个节点发多少个任务、每个任务带什么 payload」。

### 3.2 Send 的用法

`Send(node_name, payload)`：`payload` 是该节点这次执行要收到的「输入」。在条件边（或节点返回）里批量返回 `Send` 列表，LangGraph 会为每个 `Send` 创建一次独立的节点执行。

```python
from typing import TypedDict, Annotated
import operator
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

class ReviewState(TypedDict):
    files: list[str]                              # 变更文件清单（运行期才知道）
    reviews: Annotated[list[str], operator.add]   # 收集每个文件的 review 结果

def distribute(state: ReviewState) -> list[Send]:
    # 关键：返回 Send 列表，为每个文件创建一次 file_review 执行
    return [Send("file_review", {"file": f}) for f in state["files"]]

def file_review(state: dict) -> dict:
    # 注意：这里收到的 state 是 Send 的 payload（{"file": "..."}），不是全量 ReviewState
    file = state["file"]
    review = f"[{file}] 代码质量良好，建议补充单元测试"
    return {"reviews": [review]}

graph = StateGraph(ReviewState)
graph.add_node("distribute", distribute)
graph.add_node("file_review", file_review)
graph.add_edge(START, "distribute")
# 关键：distribute 的出口是条件边，返回 Send 列表 -> 动态扇出
graph.add_conditional_edges("distribute", lambda s: s)   # 返回什么就用什么（这里是 Send 列表）
graph.add_edge("file_review", END)
app = graph.compile()

result = app.invoke({"files": ["a.py", "b.py", "c.py"], "reviews": []})
print(result["reviews"])
# ['[a.py] 代码质量良好，建议补充单元测试', '[b.py] ...', '[c.py] ...']
```

关键理解：

- `distribute` 节点返回 **`Send` 列表**（而不是 dict）——LangGraph 认出这是动态扇出指令；
- 每个 `Send("file_review", {"file": f})` 创建一次**独立的** `file_review` 执行，payload 是 `{"file": f}`；
- `file_review` 看到的 `state` 是 **payload**（`{"file": ...}`），不是父图的完整 State；
- 每个 `file_review` 的返回值照常走字段合并——`reviews` 用 `operator.add` 收集（交换律，顺序无关，安全）。

### 3.3 Send 的注意点

- **汇聚**：所有 `Send` 执行完成后，图才继续往下走（可以像 2.1 一样加汇聚节点）；
- **数量保护**：一次扇出几千个 `Send` 会瞬间打爆并发——生产上分批（一次 50 个）或加数量上限检查；
- **payload 即局部状态**：想往子任务传「上下文」，把需要的字段复制进 payload，别指望子任务能读父图全量 State。

类比 Java：`Send` 就像 `ExecutorService.submit(task)` 的批量版本——每个 task 带自己的输入，结果收集回一个列表；区别是 LangGraph 帮你管理并发和结果合并。

## 四、子图：图作为节点

### 4.1 基本用法

编译后的图（`app`）本身可以被当作一个节点加进另一张图。这让你可以**复用**整段流程（比如把「需求分析流程」做成子图，多个入口复用）。

```python
# 先定义子图（一段独立流程）
def sub_analyze(state) -> dict:
    return {"analysis": f"子图分析：{state['requirement']}"}

sub = StateGraph(...)  # 子图有自己的 State 定义
sub.add_node("analyze", sub_analyze)
...
sub_app = sub.compile()

# 再定义父图，把子图当节点
class ParentState(TypedDict):
    requirement: str
    analysis: str
    report: str

parent = StateGraph(ParentState)
parent.add_node("sub_analyzer", sub_app)     # 编译后的图作为节点
parent.add_edge(START, "sub_analyzer")
parent.add_edge("sub_analyzer", END)
```

### 4.2 父子 State 的通道映射

子图作为节点时，LangGraph 按 **State 字段名**做映射：**父 State 里和子 State 同名的字段**会传入子图，子图的最终 State 里同名字段会更新回父 State。所以：

- 子图需要的输入、要输出的结果，字段名必须和父 State 一致（或手动包装节点转换）；
- 子图内部独有的字段，父图看不见（隐私/隔离），执行完也不回写。

```python
# 父 State 字段: requirement / analysis / report
# 子 State 字段: requirement / analysis   （子图只看输入、只回写 analysis）
# 效果：requirement 传入子图，子图更新 analysis，父图的 report 不受影响
```

如果字段名对不上，包一层适配节点：

```python
def adapt_for_sub(state: ParentState) -> dict:
    return {"sub_input": state["requirement"]}   # 转成子图要的字段名

parent.add_node("adapt", adapt_for_sub)
parent.add_edge("adapt", "sub_analyzer")          # 子图读 sub_input
```

### 4.3 子图的价值

| 价值 | 说明 |
| --- | --- |
| 复用 | 同一段流程多处使用，只维护一份定义 |
| 隔离 | 子图内部状态对外不可见，降低多 Agent 间的状态污染（01 篇 5.2） |
| 参数化 | 用工厂函数按需生成不同配置的子图（不同的工具集、不同的模型） |
| 测试 | 子图可以独立 `invoke` 单测，不用跑完整父图 |

### 4.4 参数化子图（工厂函数）

```python
def build_review_subgraph(llm_model: str):
    class SubState(TypedDict):
        file: str
        review: str
    def review_node(state: SubState) -> dict:
        return {"review": f"[{state['file']}] 用 {llm_model} 评审完成"}
    sub = StateGraph(SubState)
    sub.add_node("review", review_node)
    sub.add_edge(START, "review")
    sub.add_edge("review", END)
    return sub.compile()

parent.add_node("review_a", build_review_subgraph("gpt-4o-mini"))
parent.add_node("review_b", build_review_subgraph("gpt-4o"))
```

类比 Java：子图就是可组合的「流程组件/模块」，工厂函数相当于 Bean 工厂——**一个组件（子图）可以被不同配置实例化、被多处复用**。

## 五、保护与容错

### 5.1 RetryPolicy：节点级自动重试

`RetryPolicy`（`from langgraph.pregel.retry import RetryPolicy`）给单个节点配置重试策略——比阶段 1 的「LLM 调用层重试」更细粒度，只管这一个节点的失败：

```python
from langgraph.pregel.retry import RetryPolicy

def unstable_check(state) -> dict:
    ...  # 可能偶发失败（网络抖动、第三方 API 超时）

graph.add_node(
    "unstable_check", unstable_check,
    retry=RetryPolicy(max_attempts=3, initial_interval=0.5, backoff_factor=2.0),
)
```

- `max_attempts`：最多尝试次数（含首次）；
- `initial_interval` / `backoff_factor`：指数退避的初始间隔和倍数；
- 默认**只对可重试异常**生效（网络错误等），业务异常（`ValueError`）默认不重试（可通过 `retry_on` 参数定制，以官方文档为准）。

纪律（延续阶段 3）：**只读/幂等节点可自动重试；写入类节点绝不自动重试**（防重复副作用，见第 05 篇幂等性）。

### 5.2 recursion_limit 与轮数保护

并行扇出会**消耗更多节点执行次数**：一次扇出 50 个 `Send`，就是 50 次节点执行。默认 `recursion_limit`（25）很容易被打爆。两个层面处理：

1. 图调用时调大上限：

```python
app.invoke(initial_state, config={"recursion_limit": 200})
```

2. **业务层自己计数**（更可控，阶段 3 的 5.4 已示范）：State 里加计数器，超限走兜底节点——而不是靠框架异常收尾。

并行场景尤其要算清楚：`recursion_limit` 是「节点执行总次数」，不是「轮数」。扇出 × 轮数 = 实际消耗，做预算时按乘法算。

### 5.3 节点超时

LangGraph 没有内置的 per-node timeout（以官方文档为准），通用做法是 async 包装：

```python
import asyncio

async def guarded_check(state) -> dict:
    try:
        result = await asyncio.wait_for(run_check(state), timeout=10.0)
        return {"check": result}
    except asyncio.TimeoutError:
        return {"check": "超时", "errors": ["timeout"]}
```

（阶段 3 的工具层超时依旧保留——工具级超时兜底 LLM 决策，节点级超时兜底整段逻辑。）

### 5.4 并行分支的失败策略总结

| 策略 | 做法 | 适用 |
| --- | --- | --- |
| 快速失败 | 不处理，让异常传播 | 依赖强、失败即重来（配合 RetryPolicy） |
| 局部兜底 | 分支内 try/except 写错误状态 | 分析类任务（错误也是产出） |
| 汇聚兜底 | 汇聚节点容忍缺失 | 结果可降级（缺一个源也能出报告） |

## 六、性能与并发

- **async 节点天然并发**：扇出的多个节点如果是 `async def`，LangGraph 并发调度；同步 `def` 节点并行时由线程池执行（以官方文档为准）。
- **IO 密集是主要收益**：并行查询 API、并行 LLM 调用收益最大；纯 CPU 计算并行收益有限。
- **控制扇出规模**：并发不是越多越好——给扇出数量设上限，配合分批 `Send`。
- **实测验证**：同一流程串行版和并行版各跑一次，记录耗时对比（研发效能 Agent 的验收指标会用到，见 08 篇）。

## 学习自检与练习

### 练习 1：静态并行

用 2.1 的结构实现「三个并行检查器 + 汇聚」，但把三个检查器改成**都写 `report` 的不同 key**（`compliance`/`performance`/`security`），并故意让其中一个检查器抛异常，验证「局部兜底」写法（2.3 方案 1）能让整个图正常完成。

自检：如果三个检查器都写同一个覆盖型字段 `report: str`，结果会怎样？（提示：01 篇 2.5）

### 练习 2：动态扇出

用 3.2 的结构实现「对文件清单逐个生成 review」：`files` 从 1 个到 10 个变化，`reviews` 用 `operator.add` 收集。跑 1 个和 10 个文件两种输入验证。

自检：`distribute` 返回空列表（没有文件）时，图能否正常结束？

### 练习 3：子图复用

把「需求分析」做成子图（输入 `requirement`，输出 `analysis`），然后在父图里用两次：第一次做「需求分析」，第二次做「方案分析」（用不同的子图实例或不同 prompt），验证父 State 的 `analysis` 被正确回写。

自检：子图内部新增一个字段 `sub_notes`，父图能否读到？（提示：4.2 通道映射）

### 自检清单

- [ ] 能画出「扇出 + 汇聚」的图，并解释汇聚节点「等所有上游完成」的语义；
- [ ] 能说出并行写同一覆盖字段的风险，以及两种规避方法；
- [ ] 会用 `Send` 做动态扇出，理解 payload 即子任务局部状态；
- [ ] 会把编译后的图作为子图节点，处理字段名映射；
- [ ] 会配 `RetryPolicy`，理解「写入节点不自动重试」的纪律；
- [ ] 能解释 `recursion_limit` 与扇出数量的关系（乘法预算）。

## 参考资料

- LangGraph 官方文档 - 并行执行（fan-out/fan-in）: https://langchain-ai.github.io/langgraph/how-tos/branching/
- LangGraph 官方文档 - Send API（动态扇出）: https://langchain-ai.github.io/langgraph/reference/types/#langgraph.types.Send
- LangGraph 官方文档 - 子图: https://langchain-ai.github.io/langgraph/how-tos/subgraph/
- LangGraph 官方文档 - RetryPolicy: https://langchain-ai.github.io/langgraph/reference/pregel/#langgraph.pregel.retry.RetryPolicy
- 阶段 4 配套：[01-LangGraph深入-Reducer与状态设计.md](01-LangGraph深入-Reducer与状态设计.md)（本文的 State 合并语义前置）
