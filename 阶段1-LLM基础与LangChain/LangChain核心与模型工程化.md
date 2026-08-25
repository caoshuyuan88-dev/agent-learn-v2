# LangChain 核心与模型工程化

> 本文以 LangChain 1.x 为唯一学习和新项目开发主线，0.3.x 只用于阅读存量项目和理解迁移方向。

## 一、学习目标

完成本文后，应能够：

- 理解 LangChain 1.x、LangGraph、模型集成包之间的关系。
- 使用统一的 Chat Model、Message、Prompt 和 Runnable 抽象。
- 使用 `create_agent` 创建带工具的基础 Agent。
- 使用 `response_format` 获取经过校验的结构化结果。
- 使用 Middleware、Runtime、Checkpointer 处理上下文、记忆、重试和人工干预。
- 设计流式输出、观测、测试、超时、成本和模型切换方案。
- 读懂 LangChain 0.3.x 的 Chain、AgentExecutor 和解析器代码，并判断迁移方向。

## 二、版本路线：1.x 主线，0.3.x 对照

### 2.1 本文的版本规则

- **LangChain 1.x**：本文所有新代码、练习和综合项目的默认版本。
- **LangChain 0.3.x**：只用于识别旧项目、对照 API 和辅助迁移。
- **0.2、0.1、0.0.x**：保留历史差异，用于定位更早的旧代码，不作为学习主线。

版本号不能替代精确依赖版本。实际项目应先查看 `pyproject.toml`、`requirements.txt` 或锁文件，再对照官方迁移文档。

### 2.2 版本断代对比

| 版本阶段 | 大致时间 | 主要开发风格 | 重要变化 | 今天如何对待 |
|---|---|---|---|---|
| `0.0.x` | 约 2022 至 2023 年 | `LLMChain`、`ConversationChain`、大量预置 Chain | 早期快速迭代，模块和 API 变化频繁 | 只用于阅读旧代码 |
| `0.1` | 约 2024 年 1 月起 | Runnable、LCEL 开始成为推荐方向 | 引入统一的 `invoke`、`ainvoke`、`stream` 等调用方式 | 重点理解迁移背景 |
| `0.2` | 约 2024 年 5 月起 | `langchain-core` + 集成包拆分 | 模型、向量库、社区集成逐渐独立安装；旧 Chain API 进入迁移期 | 重点理解包结构和 Runnable |
| `0.3` | 约 2024 年 9 月起 | 更明确的 v2 类型和 Runnable 生态 | Pydantic v2 迁移、旧接口继续清理、LangGraph 与 Agent 能力更重要 | 主要用于维护 0.x 项目 |
| `1.x` | 约 2025 年 10 月起 | `create_agent`、LangGraph 运行时、标准消息和工具接口 | Agent API 更统一，生产级状态、持久化和中断能力由 LangGraph 承担 | 新项目和学习主线 |

> 时间按大版本和架构阶段标记。不同组件、集成包和迁移指南的发布时间并不完全同步，精确行为以官方文档和锁定版本为准。

### 2.3 主要 API 迁移关系

| 旧写法或旧思想 | LangChain 1.x 主线 | 迁移理解 |
|---|---|---|
| `LLMChain` | `prompt | model` 或显式 Runnable | 从预置 Chain 转为可组合组件 |
| `.run()` | `.invoke()` / `.ainvoke()` | 使用统一的同步、异步调用入口 |
| `predict()` | `.invoke()` | 以消息或明确输入结构调用模型 |
| 手动拼接 Prompt | `ChatPromptTemplate` 或 Agent 的 `system_prompt` | 明确消息角色和变量 |
| `PydanticOutputParser` | `with_structured_output()` 或 Agent `response_format` | 优先使用模型或 Agent 的结构化能力 |
| `initialize_agent` / `AgentExecutor` | `create_agent` | 1.x 使用 LangGraph 运行时管理 Agent 循环 |
| 旧 Memory 类 | Checkpointer、Agent State、Store | 区分线程内短期记忆和跨线程长期存储 |
| `InjectedState` 等旧注入方式 | `ToolRuntime` | 通过 Runtime 访问 state、context、store 等运行时信息 |
| 集成全塞进 `langchain` | `langchain` + 供应商集成包 | 只安装实际使用的模型和工具集成 |

### 2.4 如何阅读 0.3.x 代码

```text
先看锁文件
  -> 判断依赖版本
  -> 识别 LLMChain、AgentExecutor、旧 Memory 等入口
  -> 保留业务意图和输入输出契约
  -> 用 create_agent、messages、Runtime 和 checkpointer 重建
  -> 运行回归测试，确认工具、结构化输出和状态行为一致
```

0.3.x 的代码示例只用于迁移阅读，不要和 1.x API 混写在同一个新业务模块中。

## 三、LangChain 1.x 的整体结构

LangChain 1.x 提供高层 Agent 和底层可组合抽象；LangGraph 提供 Agent 背后的状态运行时和持久化能力；供应商集成包负责具体模型通信。

```text
供应商集成包
  -> Chat Model / Embedding Model
  -> langchain-core：Message、Prompt、Runnable、Tool
  -> langchain：create_agent、结构化输出、Middleware
  -> LangGraph：State、Runtime、Checkpointer、中断和恢复
  -> LangSmith：Tracing、调试、评测和监控
```

Agent 可以理解为：

```text
Agent = Model + Tools + System Prompt + Middleware + State
```

不要把 LangChain 当成模型本身。出现问题时，仍然要知道实际发送的消息、使用的模型、工具调用参数和 token 消耗。

### 0.3.x 对比

0.3.x 也有 `langchain-core`、Runnable 和 LangGraph，但常见应用仍通过 `LLMChain`、`AgentExecutor` 或旧 Memory 组织流程。迁移时先区分“模型能力没有变化”和“编排入口已经变化”，不要只批量替换导入路径。

## 四、开发环境与模型初始化

### 4.1 安装策略

按实际供应商安装集成包，并锁定直接依赖：

```bash
pip install -U langchain langchain-openai
```

使用 Anthropic、Google、Ollama 等模型时，安装相应集成包。不要为了学习一次性安装所有供应商依赖。

新项目至少记录：

- Python 版本
- `langchain`、`langchain-core` 和 `langgraph` 版本
- 供应商集成包版本
- Pydantic 版本
- 模型名称和版本

### 4.2 推荐的模型初始化

1.x 可以使用 `init_chat_model` 以统一方式初始化模型，也可以使用供应商专用类：

```python
from langchain.chat_models import init_chat_model


model = init_chat_model(
    "openai:gpt-5.5",
    temperature=0,
    timeout=30,
    max_retries=2,
)

response = model.invoke("什么是 asyncio？")
print(response.text)
```

模型的常用调用方式：

- `invoke()`：等待完整结果。
- `ainvoke()`：异步等待完整结果。
- `stream()`：同步获取输出片段。
- `astream()`：异步获取输出片段。
- `batch()` / `abatch()`：批量处理相互独立的输入。

### 0.3.x 对比

0.3.x 通常也使用 `ChatOpenAI`、`ChatAnthropic` 等集成类，模型调用和 `invoke()`、`ainvoke()` 的思路大多可以延续。差异主要来自集成包版本、模型参数和返回字段，因此迁移时要以项目锁文件和供应商文档为准。

## 五、Messages：模型交互的基本数据

Chat Model 的输入和输出应理解为消息，而不是简单字符串。常见消息类型：

- `SystemMessage`：系统规则和行为约束。
- `HumanMessage`：用户输入。
- `AIMessage`：模型回复或工具调用请求。
- `ToolMessage`：工具执行结果。

```python
from langchain.messages import HumanMessage, SystemMessage


messages = [
    SystemMessage(content="你是一个严谨的 Python 助手。"),
    HumanMessage(content="解释 asyncio。"),
]

response = model.invoke(messages)
print(response.text)
```

生产系统应保留工具调用对应的 `tool_call_id`，否则模型无法可靠地把工具结果和原始调用对应起来。

### 0.3.x 对比

0.3.x 已经采用标准消息类型，基本思想没有改变。旧 Chain 或 Agent 常把输入包装为 `input`、`chat_history` 等字段；1.x Agent 的主要状态是 `messages`。迁移时需要重新确认输入 Schema，而不是只修改消息类的导入路径。

## 六、Prompt 与 Runnable/LCEL

### 6.1 Prompt Template

Prompt 模板负责组织消息角色和输入变量：

```python
from langchain_core.prompts import ChatPromptTemplate


prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个严谨的 {domain} 助手。"),
    ("human", "请回答：{question}"),
])

chain = prompt | model
result = await chain.ainvoke({
    "domain": "Python",
    "question": "什么是 Task？",
})
print(result.text)
```

Prompt 应明确：

- 输入变量和类型
- 角色、目标和输出格式
- 不确定时的行为
- 是否允许调用工具
- 可能的安全边界

### 6.2 Runnable 与 LCEL

#### Runnable 是什么

Runnable 是 LangChain 中统一的可执行组件接口。Prompt、Chat Model、输出解析器、普通函数和多个组件组成的链，都可以作为 Runnable 使用。它们通常提供一致的调用方法：

- `invoke(input)`：同步执行一次。
- `ainvoke(input)`：异步执行一次。
- `batch(inputs)`：批量同步执行。
- `abatch(inputs)`：批量异步执行。
- `stream(input)`：同步逐块输出。
- `astream(input)`：异步逐块输出。

统一接口的价值是：更换链中的某个组件时，上下游仍可以使用相同的调用方式；同一条链也可以根据场景选择同步、异步、批量或流式执行。

#### LCEL 组合语法

LCEL（LangChain Expression Language）使用 `|` 声明组件之间的数据流向。`|` 表示把前一个组件的输出交给下一个组件：

```text
输入字典 -> ChatPromptTemplate -> Chat Model -> AIMessage
```

最基本的固定流程如下：

```python
chain = prompt | model
result = await chain.ainvoke({
    "domain": "Python",
    "question": "什么是 asyncio？",
})
print(result.text)
```

这段写法从 0.1 开始成为推荐方向，在 0.2、0.3.x 和 1.x 中都能见到。它适合问答、摘要、分类和信息抽取等步骤基本确定的任务。

#### 串行组合

可以把 Prompt、模型和解析器串成一条流水线：

```python
from langchain_core.output_parsers import StrOutputParser


chain = prompt | model | StrOutputParser()
text = await chain.ainvoke({
    "domain": "Python",
    "question": "什么是 asyncio？",
})
```

此时数据依次经过：

```text
输入字典 -> PromptValue/消息 -> AIMessage -> str
```

#### 并行组合

当多个任务相互独立时，可以使用 `RunnableParallel` 同时执行：

```python
from langchain_core.runnables import RunnableParallel


parallel = RunnableParallel(
    answer=prompt | model,
    original_question=lambda value: value["question"],
)

result = await parallel.ainvoke({
    "domain": "Python",
    "question": "什么是 asyncio？",
})
```

返回结果类似：

```python
{
    "answer": AIMessage(...),
    "original_question": "什么是 asyncio？",
}
```

并行适合相互独立的模型调用或数据处理；如果后一个步骤依赖前一个步骤的结果，就应使用串行组合，而不是强行并行。

#### 运行时配置

Runnable 调用时可以通过 `config` 传递运行名称、标签、metadata、Callback 和并发限制：

```python
result = await chain.ainvoke(
    {
        "domain": "Python",
        "question": "什么是 asyncio？",
    },
    config={
        "run_name": "python_question",
        "tags": ["learning"],
        "metadata": {"request_id": "req-123"},
    },
)
```

这些配置用于追踪、调试、统计和控制资源，不应把 API Key 或完整敏感 Prompt 放入 metadata。

#### Runnable 与 `create_agent` 的区别

| 对比项 | Runnable/LCEL | `create_agent` |
|---|---|---|
| 流程类型 | 开发者预先定义的固定流程 | 模型动态决定是否调用工具和继续循环 |
| 主要输入 | 普通字典、字符串或消息 | 以 `messages` 为核心的 Agent 状态 |
| 是否自动执行工具循环 | 否，需要自己编排 | 是 |
| 适合任务 | 问答、摘要、分类、抽取 | 搜索、订单查询、多工具协作、动态决策 |
| 状态与持久化 | 需要自行设计 | 可结合 State、Runtime 和 Checkpointer |

二者不是竞争关系。`Runnable/LCEL` 是 LangChain 的基础组合方式，`create_agent` 是 1.x 面向 Agent 场景的高层编排入口；Agent 内部仍然依赖 Runnable、消息和 LangGraph 运行时。

### 0.3.x 对比

0.3.x 已经成熟支持 Runnable/LCEL，因此 `prompt | model`、`ainvoke()`、`astream()` 通常可以继续理解和迁移。但旧教程仍可能使用：

```python
from langchain.chains import LLMChain


chain = LLMChain(llm=model, prompt=prompt)
result = chain.run(question="什么是 asyncio？")
```

1.x 学习和新代码统一优先使用 Runnable 调用方法，不要把 `LLMChain` 和 `.run()` 当成当前主线。

## 七、创建 LangChain 1.x Agent

### 7.1 最小 Agent

`create_agent` 是 1.x 的高层入口，内部运行在 LangGraph 运行时之上：

```python
from langchain.agents import create_agent


def get_weather(city: str) -> str:
    """获取指定城市的天气。"""
    return f"{city} 今天是晴天。"


agent = create_agent(
    model="openai:gpt-5.5",
    tools=[get_weather],
    system_prompt="你是一个简洁、准确的助手。",
)

result = agent.invoke({
    "messages": [
        {"role": "user", "content": "旧金山天气怎么样？"},
    ],
})

print(result["messages"][-1].text)
```

Agent 的基本循环是：

```text
用户消息
  -> 模型判断是否调用工具
  -> 执行工具
  -> 工具结果写回 messages
  -> 模型继续判断
  -> 返回最终消息
```

### 7.2 什么时候不需要 Agent

如果流程是固定的，例如“提取字段 -> 校验 -> 保存”，优先使用 Prompt、Model 和 Runnable 组合。只有当模型需要根据上下文动态选择工具或步骤时，才引入 Agent。

### 0.3.x 对比

0.3.x 中，创建 Tool Calling Agent 通常需要分别准备消息 Prompt、工具、Agent 和 `AgentExecutor`：

```python
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个简洁、准确的助手。"),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

# model 可以是 0.3.x 兼容的 ChatOpenAI、ChatAnthropic 等聊天模型。
legacy_agent = create_tool_calling_agent(
    llm=model,
    tools=[get_weather],
    prompt=prompt,
)


executor = AgentExecutor(
    agent=legacy_agent,
    tools=[get_weather],
    verbose=True,
    max_iterations=5,
)

result = await executor.ainvoke({
    "input": "旧金山天气怎么样？",
})
print(result["output"])
```

这段代码中的 `create_tool_calling_agent` 负责构造 Agent，`AgentExecutor` 负责执行 Agent 循环、调用工具并限制最大迭代次数。`agent_scratchpad` 用于放置 Agent 的中间步骤，调用输入通常使用 `input`，最终文本通常从 `result["output"]` 读取。

更早的项目还可能使用 `initialize_agent` 和 `.run()`。这些代码有助于识别旧项目，但 1.x 新代码使用 `create_agent`，以 `messages` 作为主要输入和状态。0.3.x 示例中的 `model`、`get_weather` 和 `prompt` 也必须来自同一个 0.3.x 依赖环境，不能直接与 1.x 的 Agent 入口混用。

## 八、Tools 与 Tool Calling

### 8.1 工具定义

工具是带有输入 Schema 和执行函数的能力。函数类型注解用于生成参数 Schema，文档字符串用于帮助模型理解用途：

```python
from langchain.tools import tool


@tool
def search_order(order_id: int) -> str:
    """查询订单状态。"""
    if order_id <= 0:
        raise ValueError("order_id 必须大于 0")
    return f"订单 {order_id}：处理中"
```

模型只提出工具调用请求，应用负责真正执行：

```text
模型选择工具和参数
  -> 应用校验参数和权限
  -> 应用执行工具
  -> 返回 ToolMessage
  -> 模型生成最终答案
```

### 8.2 工具安全边界

- 工具名称使用白名单。
- 参数必须在运行时校验。
- 权限检查必须在工具执行前完成。
- 写操作需要确认、幂等键和审计记录。
- SQL 工具不能执行模型任意生成的 SQL，应使用固定查询和结构化参数。
- 限制调用次数、查询数量、超时和返回大小。
- 不把密钥、堆栈和内部错误直接交给模型。

### 0.3.x 对比

0.3.x 通常使用 `@tool` 定义工具，再通过 `create_tool_calling_agent`、`AgentExecutor` 或 `initialize_agent` 组织工具循环。工具 Schema 的思想可以延续，但 Agent 入口、状态和错误处理方式应按 1.x 重建。

## 九、Structured Output

### 9.1 独立调用模型时

对不需要 Agent 循环的抽取任务，可以直接给模型绑定结构化输出：

```python
from pydantic import BaseModel, Field


class OrderIntent(BaseModel):
    """订单意图。"""

    intent: str
    order_id: int | None = Field(default=None, gt=0)
    confidence: float = Field(ge=0, le=1)


structured_model = model.with_structured_output(OrderIntent)
result = await structured_model.ainvoke("用户想查询订单 1001")
print(result)
```

### 9.2 Agent 中使用 `response_format`

1.x Agent 可以把 Schema 直接交给 `response_format`。LangChain 会根据模型能力选择 Provider Strategy 或 Tool Strategy，最终结果放在 `structured_response`：

```python
from langchain.agents import create_agent
from pydantic import BaseModel, Field


class Answer(BaseModel):
    answer: str
    confidence: float = Field(ge=0, le=1)


agent = create_agent(
    model="openai:gpt-5.5",
    tools=[],
    response_format=Answer,
)

result = agent.invoke({
    "messages": [{"role": "user", "content": "解释 asyncio"}],
})

answer = result["structured_response"]
```

Provider 原生支持时可靠性通常更高；不支持时可以使用 Tool Strategy。无论框架是否返回对象，都要继续做业务校验。

### 0.3.x 对比

0.3.x 的部分模型集成支持 `with_structured_output()`，旧项目也常见 `PydanticOutputParser`：模型先输出文本，再由解析器转换。迁移到 1.x 时优先使用 `response_format` 或 `with_structured_output()`，并保留字段范围、业务规则和失败处理。

## 十、Runtime、State、Context 与 Memory

### 10.1 Runtime 是什么

Runtime 是 Agent 执行期间提供给工具和 Middleware 的运行时对象。它把一次执行所需的状态、依赖和执行信息集中起来，避免工具依赖全局变量。

Runtime 通常可以提供：

- `runtime.state`：当前线程的可变状态，例如消息和自定义字段。
- `runtime.context`：本次调用传入的不可变依赖，例如用户 ID、租户和配置。
- `runtime.store`：跨线程持久化的长期数据存储。
- `runtime.stream_writer`：向 `custom` 流式模式发送进度。
- `runtime.execution_info`：线程 ID、运行 ID 和重试信息。
- `runtime.server_info`：在 LangGraph Server 上运行时的服务端和用户信息。

工具通过 `ToolRuntime` 参数访问 Runtime，Middleware 通常通过 `Runtime` 或 `ModelRequest.runtime` 访问它。

### 10.2 四种数据范围

- **State**：当前线程内会变化的数据，通常包括 `messages` 和自定义字段。
- **Context**：一次调用传入的不可变依赖，例如用户 ID、租户或数据库客户端。
- **Store**：跨线程、跨会话持久化的数据，例如用户偏好和长期记忆。
- **Checkpointer**：保存某个线程的 State 快照，使对话可以跨调用恢复。

```text
Agent 执行
    -> context：本次调用的依赖
    -> state：当前 thread 的消息和过程数据
    -> checkpointer：保存该 thread 的状态快照
    -> store：跨 thread 的长期数据
```

可以用下面的方式区分：

| 对象 | 生命周期 | 典型内容 | 是否随对话自动保存 |
|---|---|---|---|
| State | 当前线程和运行过程 | `messages`、计数器、临时结果 | 配置 Checkpointer 后保存 |
| Context | 单次调用 | `user_id`、租户、数据库连接、功能开关 | 否 |
| Store | 多个线程和多个会话 | 用户偏好、长期记忆、业务档案 | 通过 `store.put()` 主动保存 |
| Checkpointer | 多次调用之间的线程 | State 的历史快照和恢复信息 | 是，按 `thread_id` 保存 |

`thread_id` 是 Checkpointer 的会话键，不能代替用户身份校验；同一用户可以拥有多个 thread，一个 thread 也不应被不同用户共享。

### 10.3 在 Tool 中使用 Runtime

```python
from dataclasses import dataclass
from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool


@dataclass
class Context:
    user_id: str


@tool
def get_user_id(runtime: ToolRuntime[Context]) -> str:
    """获取当前用户 ID。"""
    return runtime.context.user_id


agent = create_agent(
    model="openai:gpt-5.5",
    tools=[get_user_id],
    context_schema=Context,
)

result = agent.invoke(
    {"messages": [{"role": "user", "content": "告诉我当前用户 ID"}]},
    context=Context(user_id="user-123"),
)
```

`runtime` 是注入给工具的运行时参数，不会作为模型可见的工具参数。它可以访问 `state`、`context`、`store`、流式写入器和执行信息。

### 10.4 自定义 State

默认 Agent State 至少包含 `messages`。如果工具或 Middleware 需要保存用户 ID、工具调用次数或业务阶段，可以扩展 `AgentState`，并通过 `state_schema` 注册：

```python
from langchain.agents import AgentState, create_agent


class CustomState(AgentState):
    user_id: str
    tool_call_count: int


agent = create_agent(
    model="openai:gpt-5.5",
    tools=[],
    state_schema=CustomState,
)
```

State 是 Agent 的工作数据，不等于数据库中的长期业务数据。需要跨会话访问的数据，应写入 Store 或业务数据库。

### 10.5 短期记忆与 Checkpointer

要跨同一线程保留消息历史，需要配置 Checkpointer，并在每次调用时传入同一个 `thread_id`：

```python
from langgraph.checkpoint.memory import InMemorySaver


agent = create_agent(
    model="openai:gpt-5.5",
    tools=[],
    checkpointer=InMemorySaver(),
)

config = {"configurable": {"thread_id": "conversation-1"}}
agent.invoke({"messages": [{"role": "user", "content": "我叫小林"}]}, config)
agent.invoke({"messages": [{"role": "user", "content": "我叫什么？"}]}, config)
```

生产环境应使用持久化 Checkpointer。`thread_id` 标识一段对话，不等同于用户 ID；用户身份等请求依赖应通过认证上下文传入。

### 10.6 长期记忆与 Store

Store 用于保存跨线程、跨会话仍然需要使用的数据。它不会因为配置了 Checkpointer 就自动保存，应用必须显式读写：

```python
from langgraph.store.memory import InMemoryStore


store = InMemoryStore()
store.put(("users",), "user-123", {"language": "zh-CN"})

memory = store.get(("users",), "user-123")
if memory:
    print(memory.value["language"])
```

学习时可以使用 `InMemoryStore`；生产环境应使用持久化 Store。用户偏好、长期业务档案和知识库元数据适合放入 Store 或专门数据库，而不是无限追加到 `messages`。

### 10.7 1.x 中的使用选择

```text
只需要本次请求的数据       -> context
需要当前对话继续使用的数据   -> state + checkpointer
需要跨对话长期使用的数据     -> store 或业务数据库
需要向前端报告过程           -> runtime.stream_writer
```

不要用 Prompt 模拟数据库，不要把认证信息只放在模型可见的 `messages` 中，也不要把 `thread_id` 当作权限凭证。工具执行前仍要从可信的认证上下文或服务端数据源确认权限。

### 0.3.x 对比

0.3.x 旧项目常使用 `ConversationBufferMemory`、`ConversationSummaryMemory` 或 `AgentExecutor` 的 `memory` 参数。它们通常把对话历史作为 Chain 或 Agent 的附加内存处理；1.x 则把线程状态纳入 LangGraph Runtime，并用 Checkpointer 持久化。

0.3.x 没有与 1.x `Runtime`、`context_schema`、`ToolRuntime` 完全等价的统一入口。迁移时应把旧 Memory 拆分为：消息历史迁移到 State/Checkpointer，用户偏好迁移到 Store，请求级依赖迁移到 Context。

## 十一、Streaming

### 11.1 选择流式模式

流式不是只有“把最终答案拆成 token”这一种形式。Agent 运行时可能经历模型调用、工具调用和多次循环，因此首先要明确你想把哪类过程发送给客户端。

可以先记住下面这张图：

```text
Agent 运行
  -> 模型生成消息或工具调用
  -> 工具执行并返回结果
  -> 模型继续生成

updates  ：告诉你 Agent 每一步状态发生了什么
messages ：告诉你模型正在生成哪些消息片段
custom   ：告诉你工具或节点主动报告了什么进度
```

1.x Agent 可以按不同目的流式输出：

- `updates`：每个 Agent 步骤后的状态更新，适合展示工具开始和结束。
- `messages`：模型消息片段及其 metadata，适合展示 token。
- `custom`：工具或节点主动发送的自定义进度。

#### `updates`：看 Agent 走到了哪一步

`updates` 返回的是状态更新，通常可以看到 `model`、`tools` 等节点产生的消息。它适合前端显示“正在调用搜索工具”“工具已返回”“正在生成答案”等过程，但不保证每个 token 都单独到达。

典型事件可以理解为：

```text
updates
  -> model：AIMessage，包含工具调用请求
  -> tools：ToolMessage，包含工具结果
  -> model：AIMessage，包含最终回答
```

使用场景：

- 展示 Agent 步骤和工具状态。
- 调试 Agent 是否选对工具。
- 只关心节点结果，不需要逐 token 打字效果。

#### `messages`：看模型正在生成什么

`messages` 返回模型生成的消息片段和 metadata，最适合聊天界面逐字显示。模型生成工具调用时，收到的也可能是逐步拼接的 `tool_call_chunk`，不能把它们直接当作完整工具参数执行。

```python
for chunk in agent.stream(
    {"messages": [{"role": "user", "content": "旧金山天气怎么样？"}]},
    stream_mode="messages",
    version="v2",
):
    if chunk["type"] != "messages":
        continue

    token, metadata = chunk["data"]
    if token.text:
        print(token.text, end="", flush=True)
```

使用场景：

- 聊天回答的逐 token 展示。
- 读取模型输出的 metadata，例如节点名称或模型调用信息。
- 观察工具调用参数的生成过程，但完成后仍需使用完整工具调用。

#### `custom`：看应用主动报告的进度

`custom` 不会自动产生业务进度，需要工具或图节点主动写入。它适合报告“已处理 30%”“正在查询数据库”等模型 token 之外的信息。

```python
from langgraph.config import get_stream_writer


def load_orders(user_id: str) -> str:
    """加载用户订单。"""
    writer = get_stream_writer()
    writer({"status": "started", "message": "开始查询订单"})
    # 实际项目在这里访问数据库或其他服务。
    writer({"status": "finished", "message": "订单查询完成"})
    return f"用户 {user_id} 有 3 个订单"


agent = create_agent(
    model="openai:gpt-5.5",
    tools=[load_orders],
)

for chunk in agent.stream(
    {"messages": [{"role": "user", "content": "查询我的订单"}]},
    stream_mode="custom",
    version="v2",
):
    if chunk["type"] == "custom":
        print(chunk["data"])
```

使用场景：

- 长时间工具调用的进度条或状态提示。
- 文件处理、批量任务和检索阶段的自定义信息。
- 不希望把内部过程伪装成模型回答时的独立业务事件。

#### 如何选择

| 你想让客户端看到什么 | 推荐模式 |
|---|---|
| 模型回答逐 token 出现 | `messages` |
| Agent 调用了什么工具、工具返回了什么 | `updates` |
| 工具或节点的自定义进度 | `custom` |
| 聊天 token 和工具步骤都要 | `messages` + `updates` |
| 聊天 token、工具步骤和自定义进度都要 | `messages` + `updates` + `custom` |

多个模式可以一起传入：

```python
for chunk in agent.stream(
    {"messages": [{"role": "user", "content": "查询并总结订单"}]},
    stream_mode=["messages", "updates", "custom"],
    version="v2",
):
    if chunk["type"] == "messages":
        token, metadata = chunk["data"]
        print(token.text, end="", flush=True)
    elif chunk["type"] == "updates":
        print("Agent 状态更新：", chunk["data"])
    elif chunk["type"] == "custom":
        print("业务进度：", chunk["data"])
```

`version="v2"` 是事件格式版本：它让每个事件统一为包含 `type`、`ns` 和 `data` 的字典；真正决定事件内容的是 `stream_mode`。学习时建议先分别练习单个模式，再组合多个模式。

`invoke()` 返回完整结果，`stream()` 返回多个片段。流式结构化输出不能把每个片段直接当成完整 JSON，应累积后再校验，或使用模型/Agent 提供的结构化事件。

### 11.2 与 HTTP/SSE 的关系

LangChain 负责产生流式事件，FastAPI、ASGI 或其他 Web 层负责把事件传给客户端。生产环境还要处理客户端断开、取消传播、心跳、代理缓冲、错误事件、重连和幂等。

### 0.3.x 对比

0.3.x 常见 `stream()`、`astream()` 和 `astream_events()`，但 Agent 事件结构、版本参数和状态输出可能不同。迁移时不要直接假设旧事件字典与 1.x 的 `version="v2"` 结构兼容，应写适配层并测试 token、工具事件和最终状态。

## 十二、Middleware 与可靠性

### 12.1 Middleware 的职责

Middleware 是插入 Agent 执行循环的可组合扩展。它不替代模型、工具或业务服务，而是在这些组件执行前后统一处理横切逻辑：

```text
收到请求
    -> Middleware：检查、修改或记录
    -> 模型调用
    -> Middleware：检查模型结果
    -> 工具调用
    -> Middleware：处理工具结果或错误
    -> 模型继续循环或结束
```

Middleware 可以在模型调用前后、工具执行前后或整个 Agent 运行前后介入：

- 动态 Prompt 和模型选择
- 参数检查、PII 脱敏和 Guardrail
- 模型或工具重试
- 工具动态筛选
- 人工审批和中断
- 日志、限流和自定义状态更新

Middleware 适合封装横切逻辑；业务规则和权限仍应在工具或业务服务内部再次校验。

### 12.2 常见 Middleware 类型

1.x 提供了一些可直接组合的 Middleware：

| 类型 | 作用 | 适合处理的问题 |
|---|---|---|
| Model Retry | 重试模型临时失败 | 网络错误、限流、服务端 5xx、超时 |
| Tool Retry | 重试工具临时失败 | 外部 API 暂时不可用、数据库连接抖动 |
| Summarization | 压缩过长的消息历史 | 上下文接近模型限制 |
| PII/Guardrail | 检测、脱敏或拦截敏感内容 | 隐私、合规和输出安全 |
| Human-in-the-loop | 在高风险工具前暂停 | 发邮件、退款、删除和写入操作 |
| 动态模型或工具选择 | 根据状态、权限和上下文改变能力 | 成本控制和最小权限 |

例如，给 Agent 添加有限的模型和工具重试：

```python
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware, ToolRetryMiddleware


agent = create_agent(
        model="openai:gpt-5.5",
        tools=[get_weather],
        middleware=[
                ModelRetryMiddleware(max_retries=2),
                ToolRetryMiddleware(max_retries=1),
        ],
)
```

重试次数是总尝试次数之外的额外次数还是总次数，可能受具体 Middleware 版本配置影响；生产环境应查看当前版本 API，并通过测试确认实际请求次数。

### 12.3 模型重试和工具重试的区别

- **模型重试**：模型请求没有成功返回，通常还没有产生新的业务副作用。
- **工具重试**：工具可能已经执行了一部分操作，重试前必须判断它是否幂等。

只读查询通常可以有限重试；扣款、发货、发邮件和写数据库等操作必须使用幂等键、业务状态检查或人工确认，不能因为网络超时就盲目再次执行。

```text
模型超时
    -> 确认错误可重试
    -> 有限退避重试

写操作超时
    -> 查询幂等键对应的执行状态
    -> 已成功：直接返回已完成
    -> 未执行：按业务规则重试或请求人工处理
    -> 状态未知：不要直接重复执行
```

### 12.4 超时、重试和降级

```text
可重试的网络错误或限流
  -> 有限重试和退避
  -> 备用模型或降级回答
  -> 稳定错误码
```

不要重试参数错误、权限错误或不可幂等的写操作。备用模型可能不支持相同的工具、结构化输出、上下文长度或多模态能力，切换前应做能力检查。

可以按错误类型决定处理方式：

| 错误类型 | 是否重试 | 推荐处理 |
|---|---:|---|
| 网络断开、限流、服务端 5xx | 通常可以 | 退避后有限重试 |
| 模型超时 | 通常可以 | 缩短请求或有限重试 |
| 401/403 认证或权限错误 | 不应 | 修复凭证或返回权限错误 |
| 400 参数或 Schema 错误 | 不应盲目 | 修正输入或代码 |
| 上下文超限 | 不应 | 摘要、裁剪或减少检索内容 |
| 工具写操作状态未知 | 不应直接重试 | 查询幂等状态或人工处理 |

Fallback 不是简单地换一个模型名。降级前至少确认：

- 备用模型是否支持当前工具调用协议。
- 是否支持当前结构化输出策略。
- 上下文窗口是否足够。
- 是否支持流式输出和所需模态。
- 输出质量是否满足当前业务风险等级。

低风险问答可以降级为更小模型或固定提示；高风险写操作在主模型失败时，更适合暂停并返回人工处理，而不是自动换模型继续执行。

### 12.5 Middleware 的边界与执行顺序

Middleware 可以做统一拦截，但不能成为唯一安全边界：

```text
Middleware：统一过滤和记录
    -> Tool：再次校验参数、身份和权限
    -> 业务服务：执行最终规则和事务
    -> 数据库：使用约束、事务和幂等键兜底
```

多个 Middleware 按注册顺序组成处理链。顺序会影响行为，例如应先完成身份和权限上下文准备，再进行动态工具筛选；敏感信息脱敏应发生在日志和模型上下文输出之前。

### 0.3.x 对比

0.3.x 常见在 Runnable 上使用 `.with_retry()`，或在 Chain、AgentExecutor 外层捕获异常。它们主要包裹某个 Runnable 或整个执行器，难以统一表达 1.x Agent 的模型前后、工具前后和中断节点。

这个写法有助于阅读旧代码；1.x 可以使用当前 Middleware 处理 Agent 循环级逻辑，但必须验证重试不会重复执行工具或重复写入业务数据。迁移时保留旧代码的错误分类和业务幂等规则，再将通用部分放入 Middleware。

## 十三、模型供应商抽象

业务层不应直接散落 `ChatOpenAI`、`ChatAnthropic` 等具体类。可以把模型创建集中到 Provider 工厂：

```python
from typing import Literal
from langchain.chat_models import init_chat_model


Provider = Literal["openai", "ollama"]


def create_model(provider: Provider):
    if provider == "openai":
        return init_chat_model("openai:gpt-5.5", timeout=30)
    return init_chat_model("ollama:llama3.2", timeout=30)
```

业务层依赖统一的 Chat Model 接口，配置层决定供应商、模型名称、参数和认证方式。工厂还应记录模型能力，例如工具调用、结构化输出、上下文长度和流式支持。

### 0.3.x 对比

0.3.x 的 Provider 抽象通常由项目自行封装，模型类和集成包导入方式可能与 1.x 相近。迁移时保留工厂边界，替换模型创建和能力探测，不要让业务层依赖 `LLMChain` 或具体 AgentExecutor。

## 十四、观测、Token、延迟与成本

### 14.1 LangSmith 观测

LangChain Agent 可以通过 LangSmith 记录模型调用、工具调用、状态变化、错误和延迟。常见配置：

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your-key
LANGSMITH_PROJECT=agent-learning
```

生产日志建议记录：

- `request_id`、用户或租户标识的脱敏值
- 模型名称、供应商和版本
- 输入、输出和总 token
- 首字延迟和完成延迟
- 工具名称、耗时和结果状态
- 重试次数、错误类型和最终结果

不要无条件记录完整 Prompt、API Key、个人信息和敏感工具返回值。

### 14.2 成本控制

- 缩短和复用稳定 Prompt。
- 限制历史消息并使用摘要或检索。
- 控制最大输出长度。
- 简单任务使用合适的小模型。
- 缓存稳定结果，避免无意义重试。
- 对相互独立的请求使用批量调用。
- 按用户、租户、模型和功能统计成本。

### 0.3.x 对比

0.3.x 也可以使用 Callback 和 LangSmith，但回调事件、字段和集成返回结构可能不同。迁移到 1.x 时应重新验证流式调用、工具调用和重试产生的 token 是否被重复统计。

## 十五、测试策略

### 15.1 不依赖真实 API 的测试

学习和单元测试优先使用 Fake Model 或 Mock：

- 固定模型输出，测试 Prompt 到结果的转换。
- 模拟工具成功、参数错误、权限错误和超时。
- 测试模型连续调用工具时是否触发最大次数限制。
- 测试结构化输出缺字段、非法枚举和范围错误。
- 测试流式片段拼接、取消和错误事件。
- 测试 Checkpointer 是否能按 `thread_id` 隔离会话。

真实模型测试应单独作为集成测试，并控制调用频率和成本。

### 0.3.x 对比

0.3.x 项目可能围绕 Chain 或 AgentExecutor 编写测试。迁移时保留业务输入输出用例，将测试对象替换为 1.x Agent、Runnable 或 Middleware，并增加对 `messages`、`structured_response` 和状态的断言。

## 十六、阶段 1 学习路径与综合项目

### 16.1 推荐顺序

```text
直接调用模型
  -> 1.x Chat Model 与 Messages
  -> Prompt Template
  -> Runnable 与 LCEL
  -> Tool 和 create_agent
  -> Structured Output
  -> Runtime、State、Checkpointer
  -> Streaming 与 Web 层
  -> Middleware、观测和测试
```

每完成一个 1.x 主题，再用对应的 0.3.x 对比小节识别旧代码。不要反过来先学旧 Agent API。

### 16.2 综合项目

实现一个 FastAPI + LangChain 1.x 聊天服务：

```text
HTTP 请求
  -> Pydantic 请求校验
  -> create_agent
  -> messages 状态
  -> Tool / Structured Output / Streaming
  -> Middleware 和权限检查
  -> Checkpointer 保存线程状态
  -> LangSmith 记录指标
  -> 返回普通响应或流式响应
```
- [Hello-Agent-LangChain](https://github.com/caoshuyuan88-dev/hello-agent-langchain.git)


要求：

- 支持普通响应和流式响应。
- 支持多轮消息，并使用 `thread_id` 隔离会话。
- 支持至少一个带参数校验的只读 Tool。
- 支持一个 Pydantic 结构化结果。
- 处理超时、有限重试、工具错误和稳定错误码。
- 支持 Fake Model 测试，不依赖真实 API Key。
- 记录模型、token、延迟、工具调用和错误指标。
- 需要兼容 0.3.x 时，通过单独适配层迁移，不在业务模块混用两套 Agent 入口。

## 十七、验收标准

- 能说明直接 SDK、LangChain、LangGraph 和供应商集成包的关系。
- 能使用 1.x 的 Messages、Prompt Template、Chat Model 和 Runnable。
- 能说明 `prompt | model` 与 `ainvoke()` 的版本定位。
- 能使用 `create_agent`、工具和 `messages` 状态构建基础 Agent。
- 能使用 `response_format` 或 `with_structured_output()` 获取结构化结果。
- 能区分 State、Context、Store、Checkpointer 和 `thread_id`。
- 能根据目的选择 `updates`、`messages` 或 `custom` 流式模式。
- 能使用 Middleware 处理重试、Guardrail、权限和人工审批边界。
- 能记录 token、延迟、模型、工具调用、错误和成本。
- 能用 Fake Model 完成不依赖真实 API 的测试。
- 能读懂 0.3.x 的 `LLMChain`、`AgentExecutor`、旧 Memory 和解析器代码，并说出迁移到 1.x 的方向。

## 十八、官方资料

- [LangChain Python Overview](https://docs.langchain.com/oss/python/langchain/overview)
- [Agents](https://docs.langchain.com/oss/python/langchain/agents)
- [Models](https://docs.langchain.com/oss/python/langchain/models)
- [Tools](https://docs.langchain.com/oss/python/langchain/tools)
- [Structured Output](https://docs.langchain.com/oss/python/langchain/structured-output)
- [Streaming](https://docs.langchain.com/oss/python/langchain/streaming)
- [Runtime](https://docs.langchain.com/oss/python/langchain/runtime)
- [Short-term Memory](https://docs.langchain.com/oss/python/langchain/short-term-memory)
- [LangSmith Observability](https://docs.langchain.com/oss/python/langchain/observability)
- [LangChain Releases](https://docs.langchain.com/oss/python/releases/changelog)
