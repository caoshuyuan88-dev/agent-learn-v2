# LangChain 核心与模型工程化

> 在理解 Python 直接调用模型后，再用 LangChain 组织模型、Prompt、工具和输出解析。

## 版本路线：新版本主线，历史版本辅助

截至本文整理时，建议将 **LangChain 1.x** 作为学习和新项目的主线。不要为了“掌握 LangChain”而同时学习多个版本；企业项目通常会固定一个具体版本，例如 `langchain==1.x.y`，并在升级时阅读迁移指南和变更记录。

历史版本的价值主要是：

- 读懂公司已有的 LangChain 旧项目
- 识别网上旧教程中的 API
- 理解为什么很多旧代码需要迁移
- 在升级时定位替代 API

推荐策略：

```text
LangChain 1.x：实际学习、练习和新代码
LangChain 0.3（约 2024 年 9 月起）：理解 Pydantic v2 和包拆分迁移
LangChain 0.2（约 2024 年 5 月起）：理解 Runnable、LCEL 和 langchain-core
LangChain 0.1（约 2024 年 1 月起）：理解从旧 Chain API 到 Runnable 的转向
LangChain 0.0.x（约 2022 年至 2023 年）：只做旧项目阅读，不作为学习主线
```

### 版本断代对比

| 版本阶段 | 大致时间 | 主要开发风格 | 重要变化 | 今天如何对待 |
|---|---|---|---|---|
| `0.0.x` | 约 2022 至 2023 年 | `LLMChain`、`ConversationChain`、大量预置 Chain | 早期快速迭代，模块和 API 变化频繁 | 只用于阅读旧代码 |
| `0.1` | 约 2024 年 1 月起 | Runnable、LCEL 开始成为推荐方向 | 引入统一的 `invoke`、`ainvoke`、`stream` 等调用方式 | 重点理解迁移背景 |
| `0.2` | 约 2024 年 5 月起 | `langchain-core` + 集成包拆分 | 模型、向量库、社区集成逐渐独立安装；旧 Chain API 进入迁移期 | 重点理解包结构和 Runnable |
| `0.3` | 约 2024 年 9 月起 | 更明确的 v2 类型和 Runnable 生态 | Pydantic v2 迁移、旧接口继续清理、LangGraph 与 Agent 能力更重要 | 主要用于维护 0.x 项目 |
| `1.x` | 约 2025 年 10 月起 | `create_agent`、LangGraph 运行时、标准消息和工具接口 | Agent API 更统一，生产级状态、持久化和中断能力由 LangGraph 承担 | 新项目和学习主线 |

> 时间按大版本和架构阶段标记，使用“约”是因为不同组件、集成包和迁移指南的发布时间并不完全同步；精确版本应以官方 Releases、Changelog 和项目锁文件为准。

版本号只说明大致 API 时代，不能替代项目的精确依赖版本。阅读项目时应先查看 `pyproject.toml`、`requirements.txt` 或锁文件。

### 主要 API 的迁移关系

| 旧写法或旧思想 | 新写法或新思想 | 说明 |
|---|---|---|
| `LLMChain` | `prompt | model` | 用 Runnable/LCEL 表达组合关系 |
| `.run()` | `.invoke()` / `.ainvoke()` | 统一同步和异步调用入口 |
| `predict()` | `.invoke()` | 使用消息或明确输入结构 |
| 手动拼接 Prompt | `ChatPromptTemplate` | 统一变量和消息角色 |
| 自定义解析字符串 | `with_structured_output()` | 使用 Pydantic 或 Schema 表达输出 |
| `initialize_agent` | `create_agent` 或 LangGraph | 新 Agent 编排应使用当前 Agent API |
| 旧 Memory 类 | LangGraph checkpointer、状态和消息管理 | 长期记忆与会话状态需要更明确的持久化设计 |
| 集成全塞进 `langchain` | `langchain-core` 加供应商集成包 | 依赖更清晰，减少无关安装 |

### 旧版和新版代码对照

旧教程中经常看到：

```python
from langchain.chains import LLMChain

chain = LLMChain(llm=model, prompt=prompt)
result = chain.run(question="什么是 asyncio？")
```

当前推荐优先使用 Runnable 组合：

```python
chain = prompt | model
result = await chain.ainvoke({"question": "什么是 asyncio？"})
```

旧版 Agent 教程可能这样写：

```python
from langchain.agents import initialize_agent

agent = initialize_agent(tools, model)
result = agent.run("查询订单")
```

新项目应优先学习当前 Agent API 和 LangGraph 相关文档，不要直接复制旧教程中的 `initialize_agent`、`AgentExecutor` 或旧 Memory 示例。具体替代方式会随 1.x 小版本和集成包变化，必须以当前官方文档为准。

### 企业项目的版本管理原则

不要只写宽泛依赖：

```text
langchain>=1.0
```

更建议锁定直接依赖和关键集成包的精确版本或受控范围：

```text
langchain==1.x.y
langchain-core==1.x.y
langchain-openai==1.x.y
```

实际版本号应根据项目创建时间和兼容性测试确定，不要照抄本文示例中的 `x.y`。同时记录：

- Python 版本
- LangChain 及 `langchain-core` 版本
- 供应商集成包版本
- Pydantic 版本
- LangGraph 版本
- 模型名称和版本

升级时建议：

1. 阅读官方 changelog 和 migration guide。
2. 在独立分支升级依赖。
3. 运行 Golden Dataset 和工具调用回归测试。
4. 对比 token、延迟、错误率和任务完成率。
5. 确认流式、结构化输出、Tool Calling 和持久化行为没有变化后再发布。

### 多版本学习资料

优先阅读官方资料：

- [当前 LangChain Python 文档](https://docs.langchain.com/oss/python/langchain/overview)
- [LangChain Python Changelog](https://docs.langchain.com/oss/python/releases/changelog)
- [LangChain 迁移指南](https://python.langchain.com/docs/versions/migrating_chains/)
- [Memory 迁移指南](https://python.langchain.com/docs/versions/migrating_memory/)
- [LangChain GitHub Releases](https://github.com/langchain-ai/langchain/releases)

旧项目阅读顺序：

```text
先看依赖版本
    -> 判断属于哪个 API 时代
    -> 找对应 migration guide
    -> 理解旧代码行为
    -> 再迁移到当前 1.x 写法
```

## 一、学习目标

- 理解 Chat Model、Message 和 Prompt Template
- 使用 Runnable 和 LCEL 组合调用链
- 使用 Structured Output 和 Tool
- 使用 LangChain 1.x 的 `create_agent` 构建基础 Agent
- 使用 Callback 记录过程
- 抽象不同模型供应商
- 配置超时、重试、Fallback 和成本控制

本文正文以 LangChain 1.x 为准。文中出现的 0.x API 只用于版本迁移对照，不作为练习代码。

## LangChain 1.x 开发环境

### 安装策略

LangChain 1.x 采用核心包和集成包分离的方式。新项目按实际供应商安装集成包：

```bash
pip install -U langchain langchain-openai
```

如果使用 Anthropic、Google、Ollama 等供应商，应安装对应的集成包，而不是把所有供应商依赖都装进项目。学习项目还应固定 Python、LangChain、`langchain-core`、集成包和 Pydantic 版本。

### 1.x 的推荐学习层次

```text
langchain-core
    -> Messages、Prompt、Runnable、Tool
langchain
    -> create_agent 和高层 Agent API
langgraph
    -> 状态、持久化、中断和复杂工作流
供应商集成包
    -> ChatOpenAI、ChatAnthropic、ChatOllama 等
```

阶段 1 先掌握 `langchain-core` 的基础抽象和 `create_agent`；复杂状态、Checkpoint 和 Human-in-the-loop 在阶段 4 再深入 LangGraph。

### 1.x 的最小 Agent 示例

```python
from langchain.agents import create_agent


agent = create_agent(
        model="openai:gpt-4.1-mini",
        tools=[],
        system_prompt="你是一个严谨的 Python 助手。",
)

result = agent.invoke({
        "messages": [
                {"role": "user", "content": "什么是 asyncio？"},
        ],
})

print(result["messages"][-1].content)
```

这个示例使用 LangChain 1.x 的高层 Agent 入口。真实项目还需要配置 API Key，并根据供应商文档替换模型标识。新代码不要从旧教程复制 `initialize_agent`、`AgentExecutor` 和 `.run()`。

## 二、为什么使用 LangChain

直接调用 SDK 最透明，适合先理解底层请求。LangChain 提供了统一抽象：

```text
模型
  -> Prompt 模板
  -> Runnable 链
  -> 输出解析
  -> 工具和回调
```

LangChain 不能替代对模型 API 的理解。出现问题时，仍要知道最终发送了什么消息、调用了哪个模型以及消耗多少 token。

## 三、Messages

常见消息类型：

```python
from langchain_core.messages import HumanMessage, SystemMessage


messages = [
    SystemMessage(content="你是一个 Python 助手。"),
    HumanMessage(content="解释 asyncio。"),
]
```

常见类型：

- `SystemMessage`
- `HumanMessage`
- `AIMessage`
- `ToolMessage`

消息对象比普通字符串更适合表达多轮对话、工具调用和工具结果。

## 四、Chat Model

不同供应商的模型一般实现统一的 Chat Model 接口：

```python
from langchain_openai import ChatOpenAI


model = ChatOpenAI(
    model="your-model",
    temperature=0.2,
    timeout=30,
    max_retries=2,
)
```

具体模型类和参数会随供应商及版本变化。学习时固定依赖版本，优先查看官方文档和示例。

## 五、Prompt Template

不要在业务代码中到处拼接 Prompt：

```python
from langchain_core.prompts import ChatPromptTemplate


prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个严谨的{domain}助手。"),
    ("human", "请回答：{question}"),
])

messages = prompt.invoke({
    "domain": "Python",
    "question": "什么是 Task？",
})
```

Prompt 模板应该明确：

- 输入变量
- 角色和任务
- 输出格式
- 不确定时的行为
- 工具使用规则

## 六、Runnable 和 LCEL

Runnable 是可以被调用、批量调用、异步调用或流式调用的组件。LCEL 使用 `|` 组合组件：

```python
chain = prompt | model
response = await chain.ainvoke({
    "domain": "Python",
    "question": "什么是协程？",
})
```

常用方法：

- `invoke()`：同步调用
- `ainvoke()`：异步调用
- `batch()`：批量调用
- `abatch()`：异步批量调用
- `stream()`：同步流式调用
- `astream()`：异步流式调用

独立调用可以使用并行 Runnable：

```python
from langchain_core.runnables import RunnableParallel


parallel = RunnableParallel(
    answer=chain,
    question=lambda value: value["question"],
)
```

## 七、结构化输出

```python
from pydantic import BaseModel, Field


class Answer(BaseModel):
    answer: str
    confidence: float = Field(ge=0, le=1)


structured_model = model.with_structured_output(Answer)
result = await structured_model.ainvoke("解释 asyncio")
```

结构化输出后仍要考虑模型失败、缺字段和业务校验错误。不要因为框架返回了对象就跳过边界检查。

## 八、Tool

LangChain Tool 通常包含名称、描述、参数 Schema 和执行函数：

```python
from langchain_core.tools import tool


@tool
def search_order(order_id: int) -> str:
    """查询订单状态。"""
    return f"订单 {order_id}：处理中"
```

工具描述会影响模型选择工具的能力，但不能作为权限控制。权限检查必须在工具执行前由应用完成。

## 九、Callbacks

Callbacks 可以观察模型、链和工具执行过程，用于：

- 记录开始和结束时间
- 记录 token 用量
- 关联请求 ID
- 记录工具调用
- 发送 tracing 数据
- 统计错误和延迟

生产环境不要记录完整的敏感 Prompt、API Key 或个人信息。日志字段应脱敏并控制访问权限。

## 十、超时、重试和 Fallback

模型调用至少要考虑：

```text
超时 -> 有限重试 -> 备用模型或降级回答 -> 明确失败
```

重试规则：

- 网络临时错误可以重试
- 超时可以有限重试
- 参数错误不应重试
- 权限错误不应重试
- 写操作需要确认幂等性

Fallback 需要考虑模型能力差异：备用模型可能不支持工具调用、结构化输出或相同上下文长度，不能只替换模型名。

## 十一、模型供应商抽象

建议把模型创建集中到工厂或 Provider 层：

```python
from typing import Literal


Provider = Literal["cloud", "ollama"]


def create_model(provider: Provider):
    if provider == "cloud":
        return create_cloud_model()
    return create_ollama_model()
```

业务层依赖统一接口，配置层决定具体供应商。应统一记录模型名称、供应商、版本和参数。

## 十二、Token、延迟和成本控制

至少记录：

- 输入 token
- 输出 token
- 总 token
- 首字延迟
- 完成延迟
- 模型名称和版本
- 请求 ID
- 成功或失败
- 估算成本

降低成本的常见方法：

- 缩短 Prompt
- 限制历史消息
- 控制输出长度
- 使用合适的小模型处理简单任务
- 缓存稳定结果
- 避免无意义重试
- 用批量接口处理独立请求

## 十三、学习练习

1. 使用 Prompt Template 和 Chat Model 创建问答链。
2. 将链改成 `ainvoke` 和 `astream`。
3. 使用 Pydantic 定义结构化答案。
4. 定义一个订单查询 Tool，并增加参数校验。
5. 为模型调用添加超时、有限重试和备用模型。
6. 使用 Callback 记录模型名称、延迟和 token。
7. 用 Fake Model 为链编写测试。

## 十四、阶段 1 综合项目

实现一个 FastAPI + LangChain 聊天服务：

```text
HTTP 请求
  -> Pydantic 校验
  -> Prompt Template
  -> LangChain Chat Model
  -> Structured Output 或文本流
  -> 记录调用指标
  -> 返回响应
```

要求：

- 支持普通响应和流式响应
- 支持多轮消息
- 支持结构化结果
- 处理超时、重试和降级
- 可切换云端模型和本地 Ollama
- 使用 Fake Model 测试，不依赖真实 API Key

## 十五、验收标准

- 能说明直接 SDK 和 LangChain 抽象的关系
- 能使用消息、Prompt Template 和 Chat Model
- 能使用 LCEL 组合同步和异步调用
- 能使用结构化输出和 Tool
- 能解释 Callback 的用途
- 能实现超时、重试和 Fallback
- 能记录 token、延迟、模型和成本
- 能完成 FastAPI + LangChain 聊天接口
