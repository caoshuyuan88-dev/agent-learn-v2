# Deep Agents：规划、子 Agent 与文件系统

> 本文定位：学习路线把 Deep Agents 列为阶段 4 的核心内容，并强调「**建议对比学习：LangGraph 负责可控编排，Deep Agents 负责更高层的长任务 Agent 能力；不要在一个项目中无理由混用多个编排框架**」。本文讲清楚：Deep Agents 是什么（规划、子 Agent、文件系统、长任务）、它和普通 ReAct Agent 的差别、官方 `deepagents` 库怎么用、以及在 LangGraph 里手搓一个「深 Agent」作为对照。读完本文，你能判断「这个长任务该用 LangGraph 显式编排，还是交给 Deep Agent 自主探索」，并能在阶段 4 项目里正确地二选一或分层组合。基于 LangChain 生态（`deepagents` 库较新，API 以官方 README/文档为准）。

## 学习目标

学完本文，你应该能：

- 说出 Deep Agents 的四个核心能力（规划、子 Agent、文件系统、长任务）和典型适用场景；
- 解释 Plan-and-Execute 与 ReAct 的差别，以及何时用哪个；
- 说出「子 Agent」在 Deep Agent 里的角色（上下文隔离、专业分工）；
- 用 `deepagents` 的 `create_deep_agent` 跑通一个带文件系统能力的 Agent；
- 在 LangGraph 里手搓一个「规划 + 执行循环」的深 Agent，并对比与 `deepagents` 库的取舍；
- 遵守「LangGraph vs Deep Agents」的选型纪律，不无理由混用。

## 一、Deep Agents 是什么

### 1.1 一个场景引入

让 Agent 完成「分析这个 Git 仓库的订单模块，找出潜在的性能问题，并输出一份 Markdown 报告」。这个任务：

- 要**探索**：先看目录结构、再定位订单模块、再读关键文件；
- 要**写文件**：把报告写成 `report.md`；
- 可能要**跑命令**：grep、跑测试；
- 步骤数**不确定**：取决于仓库长什么样，可能 10 步也可能 30 步；
- **失败要重来**：读错文件、找错目录要能自我纠正。

普通 ReAct Agent 也能做，但它是「一步一决策」，没有「整体计划」，容易在岔路上越走越偏。**Deep Agent** 面向这类任务：**先规划、再执行、边执行边修正计划，能操作文件系统，必要时派出子 Agent 分头探索**。

### 1.2 官方定位

[deepagents](https://github.com/langchain-ai/deepagents) 是 LangChain 推出的「深层 Agent」库（`create_deep_agent`），核心特性（以官方 README 为准）：

- **规划（Planning）**：先输出计划，执行中可修订；
- **子 Agent（Sub-agents）**：把任务拆给多个子 Agent 并行/分工执行；
- **文件系统（FileSystem）**：内置安全的文件读写、浏览、搜索工具；
- **命令行（CLI）/ 代码执行**：可执行命令、跑代码（按需配置）；
- **长任务**：面向需要很多步骤、很长时间的任务设计。

学习路线把它放在 LangGraph 之后学，用意很清楚：**LangGraph 是「你能完全控制的编排引擎」，Deep Agents 是「更自主的高层 Agent」**——先把可控的学好，再学自主的，最后学会组合。

类比 Java：LangGraph 像 Spring Batch（Job 定义、Step 编排、重启恢复，全在掌控）；Deep Agents 像一个「自动写代码的脚本助手」——给它目标和工具箱，它自己决定步骤。**前者适合固定流程，后者适合探索型任务**。

## 二、规划能力：Plan-and-Execute

### 2.1 两种决策范式

| 范式 | 决策粒度 | 特点 | 适用 |
| --- | --- | --- | --- |
| ReAct（阶段 3） | 每步一个「思考 + 行动」 | 灵活、单步决策、无全局计划 | 工具调用链较短、流程相对直接 |
| Plan-and-Execute | 先出整体计划，逐步执行，可修订计划 | 有全局视角、长任务不跑偏、但首步决策慢 | 探索型、多步骤、长任务 |

### 2.2 图实现：Planner + Executor 循环

```python
from typing import TypedDict, Annotated
import operator
from langgraph.graph import StateGraph, START, END, MessagesState

class DeepAgentState(MessagesState):
    plan: list[str]                    # 当前计划（可修订）
    done: Annotated[list[str], operator.add]   # 已完成步骤
    report: str

def planner(state: DeepAgentState) -> dict:
    # 真实场景：LLM 读任务，输出步骤列表；这里占位
    plan = [
        "1. 浏览仓库结构，定位订单模块",
        "2. 读取订单模块关键文件",
        "3. 分析性能问题",
        "4. 生成 Markdown 报告",
    ]
    return {"plan": plan}

def executor(state: DeepAgentState) -> dict:
    # 真实场景：LLM 决定执行哪一步（调工具），然后标记完成或修订计划
    if not state["plan"]:
        return {"report": "任务完成：" + "\n".join(state["done"])}
    step = state["plan"][0]
    # ... 执行 step（调文件系统/代码工具）...
    return {"done": [f"✔ {step}"], "plan": state["plan"][1:]}

def should_continue(state: DeepAgentState) -> str:
    return "executor" if state["plan"] else "finalize"

graph = StateGraph(DeepAgentState)
graph.add_node("planner", planner)
graph.add_node("executor", executor)
graph.add_edge(START, "planner")
graph.add_edge("planner", "executor")
graph.add_conditional_edges("executor", should_continue, {"executor": "executor", "finalize": END})
app = graph.compile()
```

关键：**计划是 State 的一部分**（`plan` 字段），可以随时被修订（executor 发现计划不对 → 更新 `plan`）。这就是「边执行边修正」。

## 三、子 Agent：分而治之

### 3.1 为什么需要子 Agent

任务太大时，一个 Agent 的上下文窗口装不下全部探索过程。子 Agent 的价值（03 篇 Agent as Tool 已讲过）：**隔离上下文**——每个子 Agent 只在自己的上下文里探索，只把结论传回主 Agent。

Deep Agent 里子 Agent 的典型用法：

```text
主 Agent（总控）
 ├── 子 Agent A：探索订单模块代码，返回结构摘要
 ├── 子 Agent B：搜索性能相关的历史问题，返回结论
 └── 主 Agent 汇总 A、B 的结论 -> 写报告
```

### 3.2 在 LangGraph 里就是「子图 / Agent as Tool」

你在 02 篇（子图）和 03 篇（Agent as Tool）已经学过两种实现。Deep Agent 的子 Agent 能力，本质就是**把编译好的子 Agent 包装成工具**，让主 Agent 按需调用：

```python
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import StructuredTool

module_explorer = create_react_agent(model, tools=[file_tools])

def explore_module(module: str) -> str:
    result = module_explorer.invoke({"messages": [HumanMessage(content=f"探索 {module} 并总结结构")]})
    return result["messages"][-1].content

explorer_tool = StructuredTool.from_function(
    func=explore_module, name="explore_module",
    description="探索指定模块的代码结构并返回摘要。")
```

**纪律**：子 Agent 最多两层（主 → 子），不要「主 → 子 → 孙」——上下文逐层丢失，错误难追溯（03 篇 5.4）。

## 四、文件系统与代码能力（研发效能核心）

### 4.1 为什么文件系统对深 Agent 重要

探索型任务（分析代码库、写文档、生成报告）天然需要：

- **读文件**：看源码、看配置；
- **写文件**：输出报告、修改代码；
- **搜索**：`grep` / `glob` 定位关键内容；
- **浏览目录**：理解项目结构；
- **执行命令**：跑测试、跑静态检查（可选，风险高）。

没有文件系统工具的 Agent 只能「想」，有了文件系统工具的 Agent 才能「做」。

### 4.2 安全约束（重要）

文件系统工具是**高权限能力**，必须约束（阶段 3 的工具安全思想直接复用）：

| 约束 | 做法 |
| --- | --- |
| 路径白名单 | 只允许读写指定工作目录（如 `./workspace`），禁止 `../`、绝对路径逃逸 |
| 只读模式 | 默认只读，写操作走审批（04 篇 HITL） |
| 命令白名单 | 只允许 `git status`、`pytest` 等白名单命令，禁止 `rm -rf` 等破坏性命令 |
| 大小限制 | 读文件限大小（防把超大文件灌进上下文） |
| 审计 | 所有文件操作记录到日志（阶段 3 审计纪律） |

```python
# 例：路径校验（伪代码，生产要做得更严）
ALLOWED_ROOT = Path("/workspace")

def safe_read(rel_path: str) -> str:
    target = (ALLOWED_ROOT / rel_path).resolve()
    if not str(target).startswith(str(ALLOWED_ROOT.resolve())):
        raise PermissionError("路径越界")
    if target.stat().st_size > 100_000:
        raise ValueError("文件过大")
    return target.read_text()
```

## 五、deepagents 库实战

### 5.1 安装与最小示例

```bash
pip install deepagents   # 依赖 langchain 生态；以官方 README 为准
```

```python
from deepagents import create_deep_agent   # 以官方文档为准
from langchain_openai import ChatOpenAI

model = ChatOpenAI(model="gpt-4o")          # 你锁定的模型

# 创建深 Agent：默认自带规划、文件系统等能力
agent = create_deep_agent(model=model)

result = agent.invoke({
    "messages": [{"role": "user", "content": "在工作目录里创建一个 notes.md，写入本周计划，然后读出来给我看"}]
})
print(result["messages"][-1].content)
```

`create_deep_agent` 的主要参数（以官方 README 为准）：

- `model`：LLM；
- `tools`：额外业务工具（默认已有规划/文件系统等内置工具）；
- `system_prompt`：自定义角色；
- 子 Agent / 代码执行等能力按需配置。

### 5.2 加业务工具

```python
from langchain_core.tools import tool

@tool
def query_requirement(req_id: str) -> str:
    """查询需求详情"""
    return f"需求 {req_id}：实现订单查询，优先级 P1"

agent = create_deep_agent(model=model, tools=[query_requirement])
```

### 5.3 注意

- **库较新**：`deepagents` 迭代快，API 可能变动，**以官方 GitHub README / docs 为准**，别信过期教程；
- **能力和成本**：Deep Agent 的自主性 = 更多的 LLM 调用，跑长任务前设好预算和轮数上限；
- **可控性弱**：`create_deep_agent` 内部流程由库决定，你想插入「人工审批节点」这类定制，就得回到 LangGraph 手搓（下一节）。

## 六、LangGraph 手搓 Deep Agent

### 6.1 核心结构

Deep Agent 的三个能力在 LangGraph 里都能手搓：

| Deep Agent 能力 | LangGraph 实现 | 参考章节 |
| --- | --- | --- |
| 规划 | `planner` 节点 + State 里的 `plan` 字段 | 本文 2.2 |
| 子 Agent | 子图 / Agent as Tool | 02 篇 4 节、03 篇 5 节 |
| 文件系统 | 文件系统工具（4.2 的安全约束） | 本文 4.2 |
| 长任务恢复 | Checkpoint + thread_id | 05 篇 |
| 人工审批 | interrupt | 04 篇 |

也就是说：**Deep Agent = 你学过的所有能力的组合**。手搓的好处是每个环节都可控、可插桩、可审批；代价是代码量大。

### 6.2 什么时候手搓，什么时候用库

| 需求 | 选择 |
| --- | --- |
| 快速验证「探索型任务」可行性 | `create_deep_agent`（开箱即用） |
| 需要人工审批、固定流程、审计插桩 | LangGraph 手搓（可控） |
| 深度定制（自定义规划算法、自定义子 Agent 调度） | LangGraph 手搓 |
| 探索型任务 + 只要「能跑」 | `create_deep_agent` |

## 七、选型纪律：LangGraph vs Deep Agents

学习路线的原话再强调一次：**「建议对比学习：LangGraph 负责可控编排，Deep Agents 负责更高层的长任务 Agent 能力；不要在一个项目中无理由混用多个编排框架」**。

实操上的三条原则：

1. **一个项目一个编排框架**：要么以 LangGraph 为主线（阶段 4 项目默认选它——要人工审批、要固定流水线、要审计），要么以 `deepagents` 为主线；
2. **分层不混用**：如果真要结合，也是「LangGraph 大图里把 `create_deep_agent` 当子 Agent 用」（03 篇 Agent as Tool），而不是两套框架各管一半流程；
3. **先可控后自主**：阶段 4 项目（研发效能 Agent）有明确流程（需求 → 方案 → 风险 → 测试 → 人审），**选 LangGraph 显式编排**，Deep Agent 能力（探索代码库）作为其中的一个工具/子 Agent 存在。

## 学习自检与练习

### 练习 1：Plan-and-Execute

用 2.2 的结构实现一个最小「规划 → 执行 → 完成」循环（占位逻辑即可），跑一遍验证 `plan` 逐步清空、`done` 逐步累积、最后进入 `finalize`。

自检：如果 executor 发现计划不合理要「插入新步骤」，State 里要改哪个字段？（提示：`plan`）

### 练习 2：文件系统工具 + 安全约束

实现 4.2 的 `safe_read`（路径白名单 + 大小限制），并包成 `@tool`，测试：正常读取、越界路径（`../`）、超大文件的三种行为。

自检：`(ALLOWED_ROOT / "../secret.txt").resolve()` 会被白名单拦住吗？（提示：4.2 的 startswith 判断）

### 练习 3：deepagents 或手搓二选一

方案 A：`pip install deepagents` 跑通 `create_deep_agent` 的「创建文件 + 读取」示例。方案 B（无网环境）：用 2.2 的图 + 4.2 的文件工具手搓一个「探索工作目录 → 生成清单报告」的 Agent。任选一个完成，并记录「从安装到跑通」的步骤。

自检：你选的方案里，「人工审批文件写入」该怎么加？（提示：04 篇 interrupt 或工具层人工确认）

### 自检清单

- [ ] 能说出 Deep Agent 的四个核心能力（规划、子 Agent、文件系统、长任务）；
- [ ] 能对比 Plan-and-Execute 与 ReAct，说出各自适用场景；
- [ ] 能解释子 Agent 的上下文隔离价值，并遵守「最多两层」纪律；
- [ ] 会给文件系统工具加安全约束（路径白名单、只读、大小限制）；
- [ ] 会用 `create_deep_agent` 或 LangGraph 手搓实现一个深 Agent；
- [ ] 能背出「一个项目一个编排框架」的选型纪律，并说出阶段 4 项目为什么选 LangGraph 主线。

## 参考资料

- deepagents 官方仓库: https://github.com/langchain-ai/deepagents
- Deep Agents 官方文档（Python Quickstart）: https://docs.langchain.com/oss/python/deepagents/quickstart
- 阶段 4 配套：[02-LangGraph进阶-并行分支与子图.md](02-LangGraph进阶-并行分支与子图.md)（子图）、[03-多Agent编排-Router-Supervisor-Handoff与Agent-as-Tool.md](03-多Agent编排-Router-Supervisor-Handoff与Agent-as-Tool.md)（Agent as Tool）、[04-Human-in-the-loop-interrupt与人工审批.md](04-Human-in-the-loop-interrupt与人工审批.md)（人工审批）、[05-Checkpoint持久化与长任务恢复.md](05-Checkpoint持久化与长任务恢复.md)（长任务恢复）
