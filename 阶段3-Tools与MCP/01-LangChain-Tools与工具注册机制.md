# LangChain Tools 与工具注册机制

> 面向已完成 Python/FastAPI/LLM API/LangChain 基础与 RAG 学习、正在转型 Python AI Agent 工程师的 7 年 Java 后端开发者，本文讲解 LangChain 1.x 中工具（Tool）的核心机制：Agent 为什么需要工具、工具的三要素、定义工具的三种方式、`bind_tools` 手动工具调用循环，以及面向工程化的工具注册机制（ToolRegistry）与命名规范。全文基于 LangChain 1.x、Python 3.11+、Pydantic v2，版本敏感的 API 处均标注「以你锁定的依赖版本文档为准」。

## 学习目标

> 完成本文后，你将能够：
>
> 1. 说清「工具」在 Agent 架构中的位置，以及它和 Java 世界里「接口 + 适配器 + Spring Bean」的对应关系；
> 2. 用 `@tool`、`StructuredTool.from_function`、`BaseTool` 三种方式定义业务工具，并说清各自的适用场景；
> 3. 手写一个完整的 `bind_tools` 工具调用循环（含 `ToolMessage` 回传、最大轮数保护、无工具调用时优雅结束）；
> 4. 设计并实现一个带元数据管理能力的 `ToolRegistry`，与 `bind_tools` 集成；
> 5. 遵守团队级工具命名与描述规范，能定位并规避最常见的工具调用坑。

## 一、为什么需要 Tool：Agent 与外部世界的边界

### 1.1 模型的能力边界：只会「生成」，不会「执行」

LLM 的本质是一个概率语言模型：给定上下文，它生成**看起来合理**的文本。它没有数据库连接、没有 HTTP 客户端、不会真的去改库存、查物流。你可以让模型「假装」调用了订单服务并输出一段像模像样的 JSON——但这只是文本生成，不是事实。

这带来 Agent 架构里最重要的一条原则：

> **模型负责「决策」，应用负责「执行」。** 模型决定调用哪个工具、传什么参数；真正执行工具（查库、调接口、写文件）的，永远是你的 Python 进程。

### 1.2 「编答案」 vs 「调工具」

| 维度 | 模型直接编答案 | 调用真实工具 |
| --- | --- | --- |
| 数据来源 | 训练数据 + 上下文推断（可能过时、可能幻觉） | 真实业务系统返回 |
| 时效性 | 无法感知实时状态（如「已发货」「库存 3 件」） | 实时查询 |
| 可审计 | 无法追踪数据从哪来 | 每次调用可记录参数、结果、耗时 |
| 可控制 | 无法做权限、限流、超时 | 全在应用侧控制 |
| Java 类比 | 方法里 `return "成功";` 硬编码 | 通过 Feign Client 调真实下游服务 |

同一个问题「订单 ORD-00001234 到哪了？」，模型编答案是「大概在运输中吧」，调工具则是「订单服务返回：已出库，顺丰 SF1234567890，预计明天送达」。前者是「写作文」，后者是「查系统」。

### 1.3 Java 类比：从方法调用到接口适配

如果你是 Java 后端，其实早就写过「工具」：

- 写死逻辑、直接 `new` 一个实现类 —— 相当于把业务逻辑写死在 prompt 里，模型只能「背」答案；
- 面向接口编程 + 适配器（如 Feign Client、`RestTemplate`、消息生产者）—— 调用方不关心下游实现细节，只依赖「接口契约」；
- **Agent + Tool 就是这套思路的镜像**：LLM 是调用方，工具是下游服务；`tool_calls` 是调用协议，参数校验是 DTO 校验，工具结果是下游响应。

两者的关键差异只有一个：Java 里调用方是**程序员写的代码**（确定性），Agent 里调用方是**模型**（概率性）。所以工具要写得比 Java 接口更「啰嗦」——模型只能靠 description 猜你的意图，不像 IDE 能看 javadoc。

### 1.4 本节踩坑点

- **坑：指望模型「记住」数据。** 会话里的数据是模型「生成」的，不是「查到」的。要拿真实数据，必须走工具。
- **坑：把工具设计成模型不可控。** 例如工具参数写死、或 description 语焉不详，模型要么不调用，要么传错参数。工具的每一处信息最终都会影响模型行为。

## 二、工具的三要素：name / description / args_schema

一个可被模型调用的工具，本质是给 LLM 看的一份「接口文档」，包含三个要素。

### 2.1 name：工具的唯一标识

- 模型通过 `tool_calls` 里的 `name` 字段告诉你要调用谁；
- 在同一批 `bind_tools(tools)` 里必须**全局唯一**，否则模型会困惑、路由会歧义；
- 命名风格建议：小写 + 下划线（`query_order`），动词开头，带业务前缀（详见第六章规范）。

### 2.2 description：模型选工具的依据

这是**给模型看**的，不是给人看的。模型在每次推理时读所有工具的 description，判断「哪个工具能回答用户的问题」。因此：

- 第一句话就要说清「这个工具做什么、什么时候用」；
- 写清输入输出的业务含义、边界、反例（什么情况**不要**用它）；
- 长度适中：太短说不清，太长稀释注意力（详见第七章坑 1）。

### 2.3 args_schema：参数的契约

- 定义参数名、类型、是否必填、默认值、取值范围；
- 用 Pydantic v2 的 `Field(description=...)` 给每个参数写说明——模型靠它生成正确的参数值；
- 参数校验在**应用侧**执行（Pydantic 负责），不要让模型「自觉」遵守约束。

### 2.4 Java 类比：javadoc 与接口文档

| Tool 三要素 | Java 对应物 |
| --- | --- |
| `name` | 方法名 / `@FeignClient(name=...)` 的服务名 |
| `description` | javadoc 的方法说明（但这个 javadoc 的读者是模型，不是 IDE） |
| `args_schema` | 方法签名 + DTO 的 `@NotNull`、`@Min` 等校验注解 |

区别在于：Java 编译期就强制签名正确；而模型「读」工具契约是概率行为，所以 description 和 Field description 写得好不好，直接决定调用质量。

## 三、定义工具的三种方式

以下围绕「订单查询」业务场景，展示三种定义方式。先准备一个模拟的订单服务（真实项目中替换为数据库访问或 HTTP 调用）：

```python
# mock_order_service.py —— 真实项目里替换成 DAO / HTTP Client
class OrderNotFoundError(Exception):
    pass


def fetch_order(order_id: str) -> dict:
    """模拟订单中心返回。真实场景：查库或调订单服务 HTTP 接口。"""
    if not order_id.startswith("ORD-"):
        raise OrderNotFoundError(f"订单不存在: {order_id}")
    return {
        "order_id": order_id,
        "status": "已发货",
        "tracking_no": "SF1234567890",
        "eta": "2025-12-20",
        "amount": 299.00,
    }
```

### 3.1 `@tool` 装饰器：最快的方式

`@tool` 是 LangChain 1.x 定义工具的首选方式：把一个普通 Python 函数变成 `BaseTool` 实例。**函数 docstring 的第一行会自动成为工具 description**（多行 docstring 的其余部分也会被拼入）。

```python
from langchain.tools import tool


@tool
def query_order_status(order_id: str) -> str:
    """查询订单当前状态，返回处理阶段与预计送达时间。仅用于已支付订单。"""
    data = fetch_order(order_id)
    return f"订单 {data['order_id']} 状态：{data['status']}，预计 {data['eta']} 送达"
```

要点：

- docstring 首行即 description，命名 → description 一步到位；
- 参数类型注解 + docstring 中的参数说明会被自动解析成 args_schema（Pydantic v2）；
- 需要更精确的参数约束时，用 `@tool(args_schema=...)` 显式指定：

```python
from typing import Literal
from pydantic import BaseModel, Field


class QueryOrderInput(BaseModel):
    """查询订单所需的参数。"""

    order_id: str = Field(description="订单 ID，格式为 ORD- 开头的 8 位字符串，如 ORD-00001234")
    mode: Literal["simple", "detail"] = Field(
        default="simple",
        description="查询模式：simple 只返回状态；detail 返回完整明细",
    )


@tool(args_schema=QueryOrderInput)
def query_order(order_id: str, mode: str = "simple") -> str:
    """查询订单状态或完整明细。"""
    data = fetch_order(order_id)
    if mode == "detail":
        return (f"订单 {data['order_id']}：状态 {data['status']}，"
                f"金额 {data['amount']} 元，物流 {data['tracking_no']}，预计 {data['eta']} 送达")
    return f"订单 {data['order_id']} 状态：{data['status']}"
```

`@tool` 完整支持 async 函数（当你的工具内部要 `await` 异步客户端时）：

```python
@tool
async def query_order_status_async(order_id: str) -> str:
    """异步查询订单当前状态。"""
    data = await async_fetch_order(order_id)  # 真实场景：await httpx / async DB client
    return f"订单 {data['order_id']} 状态：{data['status']}"
```

> 关于 `@tool` 的更多参数（如 `return_direct`、`parse_docstring` 等行为细节），以你锁定的 LangChain 版本文档为准。

### 3.2 `StructuredTool.from_function`：需要自定义 name/description 时

函数名不好看、或想给模型展示一个与函数名不同的工具名时，用 `StructuredTool.from_function`：

```python
from langchain.tools import StructuredTool


def get_order_detail(order_id: str) -> str:
    """（这个 docstring 在这里不生效，description 以显式参数为准）"""
    data = fetch_order(order_id)
    return (f"订单 {data['order_id']}：状态 {data['status']}，"
            f"金额 {data['amount']} 元，物流 {data['tracking_no']}")


order_detail_tool = StructuredTool.from_function(
    func=get_order_detail,
    name="order_detail",
    description=(
        "查询订单完整明细（状态、金额、物流单号、预计送达）。"
        "当用户问『订单详情/花了多少钱/物流单号』时使用；"
        "仅查状态请用 query_order。"
    ),
    args_schema=QueryOrderInput,  # 复用上面定义好的 Pydantic 模型
)
```

适用场景：函数名与对外工具名解耦、复用已有函数、需要精细控制暴露给模型的 description。

### 3.3 `BaseTool` 子类：需要状态 / 生命周期 / 自定义校验时

工具内部要持有状态（如数据库连接池、HTTP Session、缓存），或在调用前后做统一处理（鉴权、限流、埋点）时，继承 `BaseTool` 重写 `_run` / `_arun`：

```python
from typing import Type
from langchain.tools import BaseTool
from pydantic import BaseModel, Field


class QueryOrderInput(BaseModel):
    order_id: str = Field(description="订单 ID，如 ORD-00001234")


class QueryOrderTool(BaseTool):
    """带内部状态的订单查询工具。"""

    name: str = "query_order"
    description: str = "查询订单当前状态，返回处理阶段与预计送达时间。"
    args_schema: Type[BaseModel] = QueryOrderInput

    # 类字段即「状态」：真实项目中放 DB 连接池 / 鉴权客户端
    service: object = None

    def _run(self, order_id: str, **kwargs) -> str:
        # 同步执行路径：模型调用 tool.invoke() 时走这里
        # 可在此做自定义校验、鉴权、日志
        if not order_id.startswith("ORD-"):
            return '{"ok": false, "error": "invalid_order_id", "message": "订单 ID 格式不正确"}'
        data = fetch_order(order_id)
        return f"订单 {data['order_id']} 状态：{data['status']}"

    async def _arun(self, order_id: str, **kwargs) -> str:
        # 异步执行路径：async 环境调用 tool.ainvoke() 时走这里
        data = await async_fetch_order(order_id)
        return f"订单 {data['order_id']} 状态：{data['status']}"
```

要点：

- 继承自 `BaseTool` 后，模型看到的契约 = `name` + `description` + `args_schema` 三个类字段；
- **至少实现 `_run`**；若会被异步调用，同时实现 `_arun`（LangChain 会根据调用方式自动路由，`_arun` 未实现时异步调用会报错，以你锁定的版本文档为准）；
- `_run` 接收的是**已按 args_schema 校验后的参数**（`**kwargs` 方式接收），异常要自己捕获并返回结构化结果（见第七章坑 4）。

### 3.4 三种方式怎么选

| 方式 | 代码量 | 适用场景 |
| --- | --- | --- |
| `@tool` | 最少 | 80% 的常规业务工具：无状态、参数简单、函数即工具 |
| `StructuredTool.from_function` | 中 | 复用已有函数、需要自定义 name/description 与现有函数解耦 |
| `BaseTool` 子类 | 最多 | 需要内部状态、统一前后置处理、自定义校验逻辑的「重」工具 |

工程建议：**默认 `@tool`，需要元数据管理再包一层**——本阶段第 5 章会把工具统一收进 `ToolRegistry`，注册的是这三者产出的「工具实例」，对上层无差别。

## 四、把工具交给模型：bind_tools 与工具调用循环

### 4.1 `llm.bind_tools(tools)`

定义好工具后，用 `bind_tools` 把工具「挂」到模型上，模型在推理时就会看到工具列表并可能返回 `tool_calls`：

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o", temperature=0)  # 模型名以你实际可用的为准
llm_with_tools = llm.bind_tools([query_order, order_detail_tool])
```

注意：`bind_tools` 之后，模型**只是多了一个「可以调用工具」的能力**，它不会自动执行工具——执行永远在你的代码里。这是整个机制的核心心智模型。

### 4.2 手动工具调用循环（完整示例）

一次完整的「模型 → 工具 → 模型」交互称为一轮（iteration）。手动循环的标准写法：

```python
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

# 1. 工具路由表：name -> 工具实例（真实项目从这里换成 ToolRegistry，见第五章）
tools_by_name = {t.name: t for t in [query_order, order_detail_tool]}

messages = [
    SystemMessage(content="你是电商客服助手。只依据工具返回的真实数据回答，不要编造订单信息。"),
    HumanMessage(content="帮我查一下 ORD-00001234 这个订单到哪了？"),
]

MAX_ROUNDS = 10  # 最大轮数保护：防止模型反复调用工具死循环

for step in range(MAX_ROUNDS):
    response = llm_with_tools.invoke(messages)

    # 2. 模型没有要求调用工具 -> 它给出最终回答，循环结束
    if not response.tool_calls:
        print("模型最终回答：", response.content)
        break

    # 3. 模型要求调用工具：把带 tool_calls 的 AIMessage 放回消息列表（对话历史必须保留）
    messages.append(response)

    # 4. 逐个执行工具，并把结果以 ToolMessage 回传给模型
    for tc in response.tool_calls:
        print(f"调用工具: {tc['name']} args={tc['args']}")
        tool = tools_by_name[tc["name"]]
        result = tool.invoke(tc["args"])  # 同步执行；异步环境用 await tool.ainvoke(...)
        messages.append(ToolMessage(content=result, tool_call_id=tc["id"]))

else:
    # for...else：循环正常走完（达到 MAX_ROUNDS）时执行
    print("达到最大轮数，强制结束。")
```

必须理解的三件事：

1. **`response.tool_calls` 的结构**：每个元素是一个 dict，含 `name`（工具名）、`args`（参数字典，已由模型按 args_schema 生成）、`id`（这次调用的唯一 ID，回传结果时必须原样带回去，否则模型无法把结果和调用对应上）；
2. **`ToolMessage` 必须带 `tool_call_id`**：它把工具执行结果「钉」回对应的那次调用，这是 LangChain 消息协议的一部分；
3. **AIMessage 必须回放**：`messages.append(response)` 把模型那次「要调工具」的决策也写进历史，模型下一轮才能看到上下文是连续的。

### 4.3 工具结果回传格式建议

模型要「读懂」工具返回的字符串，然后组织成最终答案。因此回传内容要**结构化、可读、错误明确**：

```python
@tool
def query_order(order_id: str) -> str:
    """查询订单状态。"""
    try:
        data = fetch_order(order_id)
    except OrderNotFoundError:
        # 错误也要结构化：让模型知道「查不到」而不是「系统坏了」
        return '{"ok": false, "error": "order_not_found", "message": "订单不存在，请核对订单 ID"}'
    return ('{"ok": true, "status": "已发货", "eta": "2025-12-20", '
            '"tracking_no": "SF1234567890"}')
```

建议清单：

- **成功/失败都返回 JSON 字符串**，含 `ok` 标志与 `error` 码——模型可以据此向用户解释原因；
- 失败信息里写**用户可执行的下一步**（「请核对订单 ID」），而不是只写「调用失败」；
- 不要返回巨大原始数据（如整张表），截断/汇总后再回传，控制上下文占用；
- **绝不把密钥、堆栈、内部 SQL 等敏感信息放进结果**（它会被模型看到，也可能被模型复述给用户）。

### 4.4 create_agent：LangChain 1.x 的快速通道（简介）

LangChain 1.x 在 `langchain.agents` 下提供统一入口 `create_agent`（1.0 引入），把上面的循环、历史管理、轮数保护都封装好，是快速搭建带工具 Agent 的最短路径：

```python
from langchain.agents import create_agent

agent = create_agent(
    llm=llm,
    tools=[query_order, order_detail_tool],
    system_prompt="你是电商客服助手，只依据工具返回的真实数据回答。",
    max_iterations=10,  # 轮数上限，等价于手动循环里的 MAX_ROUNDS
)

result = agent.invoke(
    {"messages": [HumanMessage(content="订单 ORD-00001234 到哪了？")]}
)
print(result["messages"][-1].content)
```

> 本阶段以理解机制为主：`create_agent` 内部做的正是 4.2 节手动循环的事。先把手动循环写熟，再切换到 `create_agent` 就不会有黑盒感。`create_agent` 的参数与返回结构随 1.x 小版本演进，以你锁定的依赖版本文档为准。

### 4.5 运行时参数注入：`InjectedToolArg`

#### 4.5.1 问题：有些参数，模型根本不该碰

回想 4.2 节的循环：工具签名里的**每个参数**都会被编译进发给模型的 schema——模型看到什么，就会尝试填什么。但有一类参数**永远不该由模型生成**：

- **「当前调用者是谁」**（`user_id`、角色）——必须来自登录会话 / JWT，而不是模型「猜」一个；
- **程序内部依赖**——数据库连接、HTTP 客户端、密钥、配置对象，模型既看不到也不该看到；
- **平台运行时上下文**——租户 ID、`trace_id`、审计上下文。

如果把这些参数直接暴露给模型，会出两类问题：

1. **安全漏洞**：模型可以伪造任意值。比如工具签名是 `def query_order(order_id: str, user_id: str)`，模型完全可能填一个**别人的** `user_id`——这等于把「越权查他人订单」的通道亲手交给了一个概率模型；
2. **浪费与混乱**：模型对内部依赖一无所知，只能硬编一个「看起来合理」的字符串塞进去，既占用上下文又产生垃圾参数。

#### 4.5.2 是什么：一个「从模型 schema 里移除参数」的标记

`InjectedToolArg`（`from langchain_core.tools import InjectedToolArg`）是一个**类型标记**。用 `Annotated[类型, InjectedToolArg]` 标注参数后：

- LangChain 在生成发给模型的工具 schema 时，会**跳过这个参数**——模型完全看不到它，也就永远不会生成它的值；
- 参数仍然存在于工具的真实签名里，只是从「模型可见」变成「**应用注入**」。

```python
from typing import Annotated
from langchain_core.tools import InjectedToolArg, tool


@tool
def query_order(
    order_id: str,                              # 模型可见 -> 模型生成
    user_id: Annotated[str, InjectedToolArg],   # 模型不可见 -> 应用注入
) -> str:
    """查询订单状态。"""
    return f"用户 {user_id} 查询订单 {order_id}：已发货"
```

| 视角 | 看到什么 |
| --- | --- |
| **模型**（`bind_tools` 之后） | schema 里只有 `order_id` 一个参数，`user_id` 根本不存在 |
| **应用**（真正执行时） | 必须自己提供 `user_id`；不传会直接报错（Pydantic 校验失败：缺少必填字段） |

完整链路（对比 4.2 节的循环）：

```text
1. bind_tools([query_order]) -> 发给模型的 schema 只含 order_id
2. 模型生成 tool_call: {"name": "query_order", "args": {"order_id": "ORD-00001234"}}
   # 注意：args 里只有 order_id，没有 user_id
3. 应用执行工具时补上注入参数：
   query_order.invoke({"order_id": "ORD-00001234", "user_id": "u_10086"})
   # user_id 来自当前登录用户的会话/令牌，绝不是模型给的
```

#### 4.5.3 Java 类比：`@AuthenticationPrincipal`

写过 Spring Security 的话，这个模式你其实很熟：

```java
@GetMapping("/orders/{orderId}")
public Order getOrder(
        @PathVariable String orderId,                              // 调用方（模型）提供的参数
        @AuthenticationPrincipal User currentUser) {               // 框架从 SecurityContext 注入
    return orderService.getOrder(orderId, currentUser);
}
```

- `orderId` 来自请求路径——相当于模型生成的参数，框架只是把它绑定进方法；
- `currentUser` **不是**从请求里取的：客户端根本没机会传，框架从 SecurityContext 里拿出当前登录用户注入。**客户端想伪造也伪造不了**，因为请求里压根没有这个参数。

`InjectedToolArg` 就是这个 `@AuthenticationPrincipal`：模型是「客户端」，只能提供它看得到的那部分参数；身份、依赖这类参数由你的应用（框架）在执行时注入，模型既看不到、也伪造不了。

#### 4.5.4 典型用途

| 注入内容 | 来源 | 用途 |
| --- | --- | --- |
| `user_id` / 角色 | 登录会话 / JWT | **工具级权限**：查谁的数据、能不能执行写操作（与第 03 篇 RBAC 配合） |
| 租户 ID | 请求上下文 | 多租户数据隔离，模型永远无法指定租户 |
| 数据库连接 / HTTP 客户端 | 应用容器（连接池） | 工具不需要自己建连接，模型更不可能传入 |
| `trace_id` / 审计上下文 | 平台中间件 | 让审计日志贯穿整条调用链（结合第 02 篇） |

#### 4.5.5 在 Agent 执行时，注入值从哪来

手动 `invoke` 时最简单：执行代码把值写进参数字典即可（4.5.2 的示例）。在真实 Agent 里，注入值的来源通常有两处：

- **Agent 执行器 / 你自己的执行层**：像 5.2 节 `ToolRegistry.execute()` 那样，在执行前统一把「当前用户」从会话里取出来塞进参数——**注入收口到一个地方**，比每个工具自己取更可控；
- **LangGraph 的 `ToolNode`**：支持从图的状态（state）里按同名 key 取值注入，或用 `InjectedState`（`langchain_core.tools.InjectedState`）显式声明「从 state 的哪个字段注入」。具体行为随 LangGraph 小版本演进，以你锁定的版本文档为准。

不管走哪条路，原则不变：**注入值永远来自应用的信任边界（会话、令牌、配置），而不是模型输出。**

#### 4.5.6 小结

- 普通参数 = **模型填**；`InjectedToolArg` 参数 = **应用填**；
- 它是「工具级权限」的第一步：身份不进模型 schema，越权通道就少一条；
- 忘记提供注入参数时，工具调用会**明确报错**（缺少必填字段），不会带着空身份偷偷执行——这是框架替你强制保证的。

## 五、工具注册机制（ToolRegistry）

### 5.1 为什么需要集中注册

当工具从 3 个涨到 30 个，直接 `bind_tools([...])` 会出现三件事：

1. **不可发现**：没人说得清系统里有哪些工具、干什么用；
2. **不可审计**：谁在什么角色下调了什么工具，无据可查；
3. **不可控制**：超时、权限、只读约束散落在每个工具内部，无法统一治理。

集中注册（Registry）把「工具是什么」和「工具怎么用」分开：定义工具时只关心业务逻辑；注册时统一挂上元数据（超时、角色、审计、只读）。后续第 02、03 篇的工程化（超时/重试/降级）与安全（RBAC/人工确认）都会在这层展开。

### 5.2 ToolRegistry 类设计

```python
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ToolMeta:
    """工具的注册元数据。"""

    name: str                       # 工具名（与 tool.name 一致）
    description: str                # 给运维/审计人看的说明（非给模型的）
    required_role: Optional[str] = None   # 所需角色，如 "user"/"admin"；None 表示无限制
    timeout: float = 10.0                 # 超时秒数（执行层负责 enforce）
    audit: bool = False                   # 是否记录审计日志
    readonly: bool = True                 # 是否只读（写工具须显式声明）


class ToolRegistry:
    """工具注册表：注册 / 查询 / 列举 / 统一执行入口。"""

    def __init__(self) -> None:
        self._tools: Dict[str, Any] = {}
        self._metas: Dict[str, ToolMeta] = {}

    def register(self, tool: Any, meta: ToolMeta) -> None:
        if tool.name in self._tools:
            raise ValueError(f"工具名冲突: {tool.name}，请检查命名规范")
        if tool.name != meta.name:
            raise ValueError(f"元数据名称与工具名不一致: {meta.name} != {tool.name}")
        self._tools[tool.name] = tool
        self._metas[tool.name] = meta

    def get(self, name: str) -> Any:
        if name not in self._tools:
            raise KeyError(f"未注册的工具: {name}")
        return self._tools[name]

    def list(self) -> List[ToolMeta]:
        return list(self._metas.values())

    def execute(self, name: str, args: dict, role: str = "guest") -> str:
        """统一执行入口：做权限校验 + 审计，再真正调用工具。"""
        meta = self._metas[name]
        if meta.required_role and role != meta.required_role:
            return (f'{{"ok": false, "error": "forbidden", '
                    f'"message": "工具 {name} 需要角色 {meta.required_role}"}}')
        tool = self._tools[name]
        if meta.audit:
            log_audit(name=name, args=args, role=role)  # 真实项目写审计表/日志
        # 超时执行（用 asyncio.wait_for / concurrent.futures），详见第 02 篇
        return tool.invoke(args)
```

设计说明：

- `ToolMeta` 用 dataclass 描述**注册元数据**，与 Pydantic 的 args_schema 是两回事——前者给平台治理用，后者给模型选参用；
- `register()` 做两项校验：名字冲突检查、元数据与工具一致性检查——把错误挡在启动期，而不是运行期；
- `execute()` 是统一收口：角色校验、审计、超时都在这里做，工具内部不需要重复实现。

### 5.3 注册表 + bind_tools 集成

注册表不影响「模型侧」——模型看到的依然是工具列表，只是路由和执行的来源从手写 dict 换成了注册表：

```python
registry = ToolRegistry()
registry.register(
    query_order,
    ToolMeta(name="query_order", description="查询订单状态",
             required_role="user", timeout=5.0, audit=True),
)
registry.register(
    order_detail_tool,
    ToolMeta(name="order_detail", description="查询订单完整明细",
             required_role="user", timeout=8.0, audit=True, readonly=True),
)

# 模型侧：从注册表取全部工具交给 bind_tools
tools = [registry.get(m.name) for m in registry.list()]
llm_with_tools = llm.bind_tools(tools)

# 执行侧：走统一入口（自动做角色校验与审计）
result = registry.execute("query_order", {"order_id": "ORD-00001234"}, role="user")
```

### 5.4 Java 类比：Spring 容器与 BeanFactory

| ToolRegistry | Spring 容器 |
| --- | --- |
| `register(tool, meta)` | `@Component` / `@Bean` 注册（+ `@Order`、`@Qualifier` 等元数据） |
| `get(name)` | `BeanFactory.getBean(name)` |
| `list()` | `ApplicationContext.getBeansOfType(...)` |
| `execute()` 里的统一校验/审计 | AOP 切面（`@Around` 统一做鉴权与日志） |
| 启动期查重（名字冲突即报错） | 容器启动时 bean 名冲突直接启动失败 |

如果你在 Spring 项目里写过「统一异常处理 + 切面审计」，你对 ToolRegistry 的价值会秒懂：它就是把分散在 30 个工具里的横切关注点，收拢到一个可控的入口。

## 六、工具命名与描述规范

工具多了之后，命名混乱是模型调用错误的第一来源。以下是可直接抄进团队规范的清单。

### 6.1 命名规范

- **动词开头 + 宾语**：`query_order`、`cancel_order`、`get_user_profile`，一眼看出动作与对象；
- **业务前缀分组**：`order_`、`user_`、`inventory_`——既防命名冲突，也方便 `registry.list()` 按前缀过滤；
- **禁止歧义缩写**：`get_ord`、`qo` 这种模型猜不出意图的名字不要用；
- **语义上区分「查」与「改」**：`query_order`（只读）vs `cancel_order`（写），这是后续做只读/写入分离（第 03 篇）的基础；
- **版本化**：破坏性变更不要改旧工具，而是注册新版本 `order_query_v2`，灰度后下架旧版——工具是线上契约，不是内部私有方法。

### 6.2 描述规范

- 首句 = 一句话说清「做什么 + 何时用」；
- 写明**输入输出语义**：参数是什么格式、返回什么结构；
- 写明**反例/边界**：什么情况不要用它（「仅查状态请用 query_order，查明细用 order_detail」）；
- **禁止在 description 里放敏感信息**：内网地址、库名、表名、密钥、内部错误码，都不要写——description 会原样发给模型（可能经第三方模型厂商处理），且模型可能复述给用户。

### 6.3 团队规范清单（checklist）

```text
□ name 唯一、动词开头、带业务前缀
□ description 首句说明用途，包含边界与反例
□ 每个参数有 Field(description=...)
□ 敏感信息（内网/密钥/表名）不出现在任何 description 里
□ 只读工具与写工具从命名上可区分
□ 破坏性变更走新版本工具，不原地修改
□ 所有工具注册进 ToolRegistry 并填写 ToolMeta
```

## 七、常见坑

### 7.1 description 太长或太短

- **太长**：模型上下文被稀释，可能「看不到」关键工具，或选错工具。超过 3~4 句话就考虑精简，或拆分工具。
- **太短**：`查询订单` 这种描述无法让模型判断该不该用、何时用。至少包含：用途、何时用、边界。
- 原则：**让模型在一句话内能判断「要不要用我」**。

### 7.2 参数没有 Field 描述，模型传错参数

```python
# 反例：模型只能看到类型，猜不出业务含义
class BadInput(BaseModel):
    order_id: str   # 没有 Field(description=...)
```

模型看到 `order_id: str` 时不知道格式是 `ORD-00001234`，可能传 `1234`、`订单号` 之类。**给每个参数写 `Field(description=...)`，写明格式、示例、取值范围**——这就是给模型看的「参数文档」。

### 7.3 同步阻塞工具阻塞事件循环

FastAPI 是 asyncio 事件循环驱动的。如果一个工具内部用了**同步**阻塞调用（`requests.get`、同步 DB 驱动），而你在 async 路径里直接 `await tool.ainvoke(...)`，会卡住整个事件循环，拖垮所有并发请求。

- 工具本身是 async 的：内部用 `httpx.AsyncClient` / async DB 驱动；
- 工具是同步的但跑在 async 环境：用 `asyncio.to_thread(tool.invoke, args)` 丢到线程池，或依赖执行层统一处理（第 02 篇会讲超时与并发治理）。

```python
import asyncio

# async 环境里调用同步工具的正确姿势
result = await asyncio.to_thread(query_order.invoke, {"order_id": "ORD-00001234"})
```

### 7.4 工具内部异常导致循环中断

```python
# 反例：异常直接抛出，整个工具调用循环崩溃
@tool
def query_order(order_id: str) -> str:
    data = fetch_order(order_id)   # 订单不存在 -> 抛异常 -> 循环挂掉
    return f"状态：{data['status']}"
```

工具运行在你的进程里，异常会沿着调用栈炸掉整个循环。正确做法：**工具自己捕获已知异常，返回结构化错误**（见 4.3 节），让模型读到「order_not_found」后向用户解释并给出下一步，而不是整个对话中断。

```python
# 正例
@tool
def query_order(order_id: str) -> str:
    """查询订单状态。"""
    try:
        data = fetch_order(order_id)
    except OrderNotFoundError:
        return '{"ok": false, "error": "order_not_found", "message": "订单不存在，请核对订单 ID"}'
    except Exception as exc:  # 兜底：未知异常也转成结构化结果
        return f'{{"ok": false, "error": "internal_error", "message": "查询失败：{exc.__class__.__name__}"}}'
    return f'{{"ok": true, "status": "{data["status"]}"}}'
```

## 学习自检与练习

1. **概念题**：一句话说明「模型生成 tool_calls」和「应用执行工具」分别由谁负责，为什么执行必须落在应用侧？
2. **编码题**：为「库存查询」写一个 `@tool`：参数 `sku_id`（必填，带 Field 描述）、`warehouse`（可选，默认 `"main"`），docstring 首行写明用途，返回含 `ok` 标志的 JSON 字符串。
3. **编码题**：实现 `ToolRegistry`，注册 3 个工具（如 `query_order`、`get_user_profile`、`query_stock`），调用 `list()` 打印元数据，用 `execute()` 分别以合法角色与非法角色调用一次，观察权限校验行为。
4. **编码题**：写一个 `bind_tools` 手动循环，让模型从「查订单状态」和「查订单明细」两个工具中自动选择；故意输入一个两个工具都不匹配的问题（如「今天天气如何」），验证循环能在**无工具调用**时正常结束而不是死循环。
5. **规范题**：下面这段 description 有什么问题？试着改写。`get_order_info`：`description="获取订单信息，接口地址 http://192.168.1.10:8080/order/get，参数 orderId 必填。"`
6. **进阶题**（可选）：把 `InjectedToolArg` 注入的 `user_id` 与 `ToolMeta.required_role` 结合起来：在 `execute()` 中校验调用者角色后，再把身份注入工具参数。

## 参考资料

- LangChain 官方文档 · Tools：https://python.langchain.com/docs/concepts/tools/
- LangChain 官方文档 · Tool Calling：https://python.langchain.com/docs/concepts/tool_calling/
- LangChain 官方文档 · Tool 定义与自定义：https://python.langchain.com/docs/how_to/custom_tools/
- LangChain 官方文档 · 传给模型的工具参数（InjectedToolArg）：https://python.langchain.com/docs/how_to/tool_runtime/
- LangChain 官方文档 · create_agent：https://python.langchain.com/docs/how_to/agent_create/
- LangChain Academy（官方免费课程）：https://academy.langchain.com/
- Pydantic v2 官方文档（Field 描述与校验）：https://docs.pydantic.dev/latest/
- 本文档配套的上一阶段文档：《Tool Calling 与 Embedding》（阶段 1），以及后续《工具调用工程化：校验、超时、重试、降级与审计》（阶段 3 第 02 篇）
