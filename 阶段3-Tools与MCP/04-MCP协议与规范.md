# MCP 协议与规范：Tools、Resources、Prompts 与传输方式

> 定位：本文讲清 MCP（Model Context Protocol）是什么、为什么需要它、协议如何工作——三层架构、三个核心原语、两种主流传输、JSON-RPC 2.0 消息与生命周期、安全模型。读完本文，你应该能读懂 MCP 官方规范、看懂 MCP Inspector 里的每一条消息，并为下一篇动手开发做好准备。代码实践（用 FastMCP 开发 Server、把 Server 接进自己的 Agent）留到本系列 [05 - MCP Server 开发实践](05-MCP-Server开发实践.md) 与 [06 - MCP Client 与 Agent 集成](06-MCP-Client与Agent集成.md)。
>
> 读者画像：7 年 Java 后端经验，已完成 Python/FastAPI/LLM API/LangChain 基础/RAG 学习。文中会频繁用 JDBC、Spring Cloud、OAuth2、RMI 等 Java 生态概念做类比；概念优先、工程导向，不粘贴大段源码。
>
> 版本提醒：MCP 演进很快，协议版本用日期字符串标识（如 2025-06-18），本文描述以 2025 年底的规范状态为主，一切细节**以官方规范最新版为准**。

## 学习目标

完成本文后，应能够：

- 用一句话向同事解释「MCP 是什么、解决什么问题」，并讲清 N×M 接入问题的由来。
- 说清 Host / Client / Server 三层架构中各自的职责，以及「Client 与 Server 是 1:1 连接」的含义。
- 区分 Tools / Resources / Prompts 三个核心原语，面对具体需求能做出正确选择。
- 说清 stdio 与 Streamable HTTP 两种传输的适用场景、安全与运维取舍。
- 读懂 JSON-RPC 2.0 的 request / response / notification 三类消息，能按正确顺序完成 initialize 握手。
- 理解 MCP 的安全模型：协议本身不鉴权、信任建立在传输层与应用层、OAuth 2.1 的角色。
- 知道 Sampling、Roots、进度通知等扩展能力是做什么的、什么时候才需要。

## 一、为什么需要 MCP：工具接入的碎片化

### 1.1 没有标准时的 N×M 问题

作为一名 Java 后端，你一定经历过「对接 N 个服务」的日子：每个服务都有自己的 SDK、鉴权方式、错误模型和文档，调用方要逐一写适配代码。在 Agent 世界里这个问题更严重——**模型不读文档**，它只知道自己被注册了哪些工具、每个工具的参数 schema 是什么。

假设你的运维分析 Agent 要访问：数据库、日志系统、内部订单 REST API、报表服务。传统做法是给每个服务手写一层适配：

```text
Agent A ──┬── 适配器：数据库（连接池 + SQL 白名单）
          ├── 适配器：日志服务（HTTP 客户端 + Token 刷新）
          ├── 适配器：订单 API（Feign 风格封装）
          └── 适配器：报表服务（SOAP/JSON 转换）

Agent B（换个场景）── 同样的适配器再写一遍
```

每新增一个 Agent，就要为每个服务再写一遍；每新增一个服务，就要为每个 Agent 提供接入。这就是 **N×M 问题**：N 个服务 × M 个应用，适配代码按乘积增长，而且每份适配代码都包含参数 schema 定义、鉴权、错误处理、调用说明（description），全是重复劳动。

### 1.2 MCP 是什么

MCP（Model Context Protocol，模型上下文协议）是 Anthropic 于 **2024 年 11 月开源**的一种开放协议，用于连接 AI 应用（Agent、IDE、聊天应用）与外部工具、数据源和提示模板。到 2025 年，它已成为 Agent 工具接入的事实标准，OpenAI、Google、Microsoft 等主流厂商的产品都宣布支持；规范治理也已移交 Linux 基金会下的项目继续演进（以官方公告为准）。

用三个 Java 世界里的类比来理解它：

- **类比 JDBC / 数据库驱动**：JDBC 之前，应用面向 Oracle、MySQL、SQL Server 各自的驱动 API 编程，换数据库等于重写数据访问层；JDBC 之后，应用只面向 `java.sql` 接口，厂商负责提供驱动实现。MCP 之于 Agent 能力接入，如同 JDBC 之于数据库访问——**应用面向统一接口，服务方提供实现**。
- **类比 USB 设备标准**：外设厂商按 USB 规范实现设备，操作系统即插即用，无需为每个外设定制协议。MCP Server 就是「按标准实现的设备」，任何支持 MCP 的 Host 插上就能用。
- **类比 Spring Cloud 的服务契约**：Feign 接口定义了调用契约，服务提供方实现它，调用方面向契约编程。MCP 把「工具/数据/模板」定义成一套标准化契约，服务提供方按契约暴露能力。

一句话版本：**MCP 是 Agent 与服务之间的「JDBC」，把服务能力标准化，让任意 Agent 即插即用。**

### 1.3 MCP 要解决的三类问题

1. **工具发现（Discovery）**：Agent 如何知道某个服务提供哪些能力？→ 协议定义 `tools/list`、`resources/list`、`prompts/list`，让能力可枚举、可查询。
2. **统一调用（Invocation）**：如何用统一的方式调用这些能力？参数如何描述、校验，结果如何返回，错误如何表达？→ 协议定义 `tools/call`、`resources/read`、`prompts/get`，参数用 JSON Schema 描述，结果与错误有统一结构。
3. **上下文传递（Context）**：模型需要的上下文（数据、提示模板、文件系统边界）如何安全、可控地进入对话？→ 协议定义 Resources（数据注入）、Prompts（模板选择）、Roots（文件系统根目录声明）等机制。

这三类问题恰好对应下一节的三个核心原语，也对应你之前学过的 Tool Calling 与 RAG：MCP 不是在发明新概念，而是把「工具、数据、模板」**协议化、标准化**。

## 二、架构与角色：Host、Client、Server

### 2.1 三个角色

MCP 是三层架构：

| 角色 | 是什么 | 职责 | Java 类比 |
|---|---|---|---|
| **MCP Host** | 用户侧的应用程序：Claude Desktop、IDE、你的 Agent 服务 | 拥有用户会话；管理多个 Client；决定是否批准工具调用 | Spring Boot 应用本身 |
| **MCP Client** | Host 内的协议组件，与一个 Server 建立 **1:1 连接** | JSON-RPC 编解码、生命周期管理、能力协商、传输层收发 | 一条 JDBC Connection（每个数据库一条） |
| **MCP Server** | 暴露能力的程序（本地子进程或远程 HTTP 服务） | 实现 Tools / Resources / Prompts，响应 Client 的请求 | 数据库服务端 / 被调用的微服务 |

两个容易记错的关键点：

- **Client 与 Server 是 1:1**：一个 Client 实例只连接一个 Server。Host 要连多个 Server，就创建多个 Client，每个 Client 各连一个。
- **模型不直接碰 Server**：模型只与 Host 交互，Host 通过 Client 与 Server 通信。所以「模型调用了哪个工具」实际上是「Host 代表模型发起了 `tools/call`」。

### 2.2 一张架构图

```text
                    MCP Host（你的 Agent 服务 / Claude Desktop）
   ┌──────────────────────────────────────────────────────────────┐
   │  用户会话 / 审批机制 / 上下文管理                               │
   │                                                              │
   │   MCP Client A        MCP Client B        MCP Client C       │
   │   （1:1 连接）          （1:1 连接）          （1:1 连接）       │
   └───────┬────────────────────┬────────────────────┬────────────┘
           │ 传输层（stdio/HTTP） │                     │
      ┌────▼─────┐          ┌────▼─────┐         ┌────▼─────┐
      │ MCP      │          │ MCP      │         │ MCP      │
      │ Server A │          │ Server B │         │ Server C │
      │ 数据库查询 │          │ 日志检索   │         │ 内部业务 API│
      └──────────┘          └──────────┘         └──────────┘
```

Host 只关心「我有哪些 Client」，每个 Client 只关心「我对应的那个 Server」——这和 Spring Boot 应用里一个数据源配一个 `DataSource`、一个 Feign 客户端配一个目标服务，是同一个心智模型。

### 2.3 SDK 帮你做了什么

你不需要手写 JSON-RPC。官方 SDK（Python SDK、TypeScript SDK）和 FastMCP 这类高层封装替你完成了：

- 消息的序列化 / 反序列化（JSON-RPC 2.0 编解码）；
- 生命周期状态机（initialize → 就绪 → 断开）；
- 能力协商与类型模型（Python 侧用 Pydantic 模型承载协议消息，类似 Java 的 DTO/POJO + Jackson）；
- 传输层：stdio 的子进程管理、HTTP 客户端 / 服务端；
- 原语注册：`@mcp.tool()` 装饰器把 Python 函数变成协议工具，自动生成 JSON Schema。

类比理解：SDK 之于 MCP，就像 Spring 的 `spring-boot-starter-jdbc` 之于 JDBC——**连接管理、协议细节都被框架吃掉，你只写业务逻辑**。这也是为什么下一篇实践文档里，几十行代码就能跑起一个 MCP Server。

## 三、核心原语：Tools、Resources、Prompts（重点）

### 3.1 总览

| 原语 | 一句话 | 谁发起 | 主要方法 | Java 类比 |
|---|---|---|---|---|
| **Tools** | 可执行的操作（可能有副作用） | 模型选择，用户/应用批准后执行 | `tools/list`、`tools/call` | 远程方法 / REST 接口 |
| **Resources** | 可读取的数据 / 上下文 | 应用读取后注入上下文 | `resources/list`、`resources/read` | Repository / 数据源 |
| **Prompts** | 可复用的提示模板 | 应用 / 用户选择 | `prompts/list`、`prompts/get` | 模板引擎 / 预制 Prompt 库 |

记忆口诀：**Tool 让模型「做事」，Resource 让应用「喂数据」，Prompt 让用户「选模板」。** 更直白一点：Tool 是模型能调的「函数」，Resource 是应用塞给模型的「数据」，Prompt 是用户点选的「模板」。

三个原语最本质的区别是**谁发起**：

```text
Tool     -> 模型发起（对话中自主选择）-> 应用批准 -> 执行 -> 结果回模型
Resource -> 应用发起（代码主动读取）  -> 内容注入上下文 -> 模型「读到」
Prompt   -> 用户/应用发起（点选模板） -> 渲染成消息序列 -> 作为初始指令喂模型
```

下面各节用 FastMCP（server 侧）和 `ClientSession`（client 侧）给出最小代码，帮助建立直觉（完整实践见 05、06 文档）。

### 3.2 Tools：让模型「做事」

Tools 对应你已学过的 Tool Calling，是三个原语里最重要、最常用的。**它是唯一由「模型发起」的原语**：对话中模型自己判断「该查订单了」，于是选中这个工具、填好参数；应用批准后执行；结果返回给模型继续推理。

Server 侧（FastMCP 定义一个工具，详见 05 文档）：

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ops-server")


@mcp.tool()
def query_order(order_id: str) -> dict:
    """按订单号查询订单状态，只读操作。"""
    return {"order_id": order_id, "status": "已发货", "eta": "2025-12-20"}
```

Client 侧（你的 Agent 服务里，详见 06 文档）：

```python
tools = await session.list_tools()
# tools.tools[0] -> name="query_order"
#                   description="按订单号查询订单状态，只读操作"
#                   inputSchema={"order_id": {"type": "string"}}

result = await session.call_tool("query_order", {"order_id": "ORD-00001234"})
# result.content -> [TextContent(text='{"order_id": ..., "status": "已发货"}')]
# result.isError -> False（False = 业务成功）
```

完整链路（对照阶段 1 的 Tool Calling）：

```text
用户："订单 ORD-00001234 到哪了？"
 1. 模型从工具清单里选中 query_order，填好参数 order_id     <- 模型发起
 2. 应用（Host）批准后，Client 发 tools/call 给 Server
 3. Server 执行查库，返回结果和 isError                      <- 真正执行
 4. 结果作为 ToolMessage 回给模型
 5. 模型基于真实数据组织最终答案
```

Java 类比：`tools/call` 像一次 RPC 调用；`inputSchema` 像 OpenAPI 的请求参数定义（或 `@RequestParam` 加校验注解）；「需要批准」像 `@PreAuthorize` 或银行转账的二次确认。

关键认知：**模型只是「提议」，真正执行的是 Server（运行在你的进程/权限下）**——所以写入类工具必须有批准与权限机制，和阶段 3 前几篇的 RBAC、人工确认一脉相承。

### 3.3 Resources：让应用「喂数据」

Resources 解决「模型如何获得上下文数据」。**它不是让模型去调用**——模型在 MCP 里没有「读取资源」这个动作；而是**由应用代码主动读取，把内容注入对话上下文**（类似 RAG 的检索注入，但把「读取」这个动作协议化了）。

Server 侧（FastMCP 定义一个资源）：

```python
@mcp.resource("db://tables")
def list_tables() -> str:
    """返回当前可查询的表清单。"""
    return "可用表：orders(订单)、inventory(库存)、users(用户)"


@mcp.resource("db://orders/{order_id}")   # URI 支持路径参数
def order_detail(order_id: str) -> str:
    return f"订单 {order_id}：金额 299.00 元，状态 已发货"
```

Client 侧（应用代码主动读取，而不是模型）：

```python
# 应用启动时读一次表清单，拼进 system prompt
res = await session.read_resource("db://tables")
tables_text = res.contents[0].text

messages = [
    {"role": "system", "content": f"你是运维分析助手。可查询的数据表：\n{tables_text}"},
    {"role": "user", "content": "订单表里都有哪些状态？"},
]
```

区别立刻可见：**模型从头到尾没调用过任何 resource**，它只是「读到了」应用塞进上下文的文本。URI 的 scheme 可以自定义（`file://`、`logs://`、`db://`、`https://` 等），具体语义由 Server 实现决定，就像 URL 的 scheme 由协议决定。订阅（`resources/subscribe`）可选：资源变化时 Server 发通知，应用可刷新上下文。

Java 类比：Resources 相当于 Repository / DAO 层——模型看不到数据访问代码，只看到应用注入好的内容；URI 就是数据源的定位符。**注意区分**：RAG 里的检索结果是应用代码注入的，Resources 则是把「检索/读取」这个动作协议化了，让不同 Server 用统一方式暴露数据。

### 3.4 Prompts：让用户「选模板」

Prompts 是可复用、参数化的提示模板。**由用户或应用主动选择**（类似点击一个「快捷指令」按钮），模型不会自动调用它。`prompts/get` 返回的是**渲染后的完整消息序列**（可含多条 system/user 消息），直接作为对话的起始指令。

Server 侧（FastMCP 定义一个提示模板）：

```python
from mcp.server.fastmcp.prompts import SystemMessage, UserMessage


@mcp.prompt("order-analysis")
def order_analysis(order_id: str):
    """按固定格式分析一个订单。"""
    return [
        SystemMessage("你是订单分析专家。输出必须包含：订单号、状态、风险、建议。"),
        UserMessage(f"请分析订单 {order_id}"),
    ]
```

Client 侧（用户点按钮 / 应用主动选择模板）：

```python
prompt = await session.get_prompt("order-analysis", {"order_id": "ORD-00001234"})
# prompt.messages -> [SystemMessage("你是订单分析专家…"), UserMessage("请分析订单 …")]
messages = prompt.messages   # 渲染结果直接作为对话的起始消息交给模型
```

Java 类比：像 Thymeleaf / FreeMarker 模板，或项目里沉淀的 prompt 常量库；`prompts/get` 就是「模板 + 参数 → 渲染结果」。

与 Tool 的区别：Tool 的结果进入模型后模型**继续推理**；Prompt 的结果是**喂给模型的初始指令**，执行权在应用侧。一句话：**Tool 是「函数」，Prompt 是「开场白」。**

### 3.5 一个贯穿例子：三者怎么配合

场景：企业运维分析 Agent（正是阶段 3 项目）。同一个 MCP Server（ops-server）同时暴露三个原语，各司其职：

```text
用户问"订单 ORD-2025-0001 到哪了？"
  -> 模型自主选中 Tool: query_order(order_id)     （模型发起）
  -> 应用批准后 call_tool，Server 查库返回状态      （执行）
  -> 模型组织答案："已发货，预计明天送达"

应用启动时主动读取 Resource: db://tables            （应用发起）
  -> 把表清单拼进 system prompt
  -> 模型"知道"有哪些表，但从未调用过 resource      （注入上下文）

用户点击"生成故障报告"按钮                          （用户发起）
  -> 应用选择 Prompt: order-analysis(order_id)
  -> 拿到模板渲染出的消息序列，作为对话起始消息       （开场白）
```

三种原语解决三种不同的问题：**Tool 让模型拿到实时数据，Resource 让应用把静态上下文喂给模型，Prompt 让用户快速套用固定格式**——它们经常在同一个 Server 里共存。

#### 共用代码示例：一个订单分析 MCP Server

下面用同一个 `order_id` 把三种原语串起来。注意：Server 负责**暴露能力**，Client/Host 负责**决定何时使用**；三种原语的调用入口不同，但可以服务于同一个业务流程。

Server 侧：同一个 Server 同时注册 Tool、Resource 和 Prompt。

```python
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import SystemMessage, UserMessage

mcp = FastMCP("order-analysis-server")


@mcp.tool()
def query_order(order_id: str) -> dict:
  """查询订单的实时状态，供模型按需调用。"""
  return {
    "order_id": order_id,
    "status": "已发货",
    "eta": "2025-12-20",
  }


@mcp.resource("db://orders/{order_id}")
def order_context(order_id: str) -> str:
  """读取订单分析所需的背景数据，供应用注入上下文。"""
  return f"订单 {order_id}：金额 299.00 元，客户等级：黄金"


@mcp.prompt("order-analysis")
def order_analysis(order_id: str):
  """生成订单分析的固定消息模板，供用户或应用选择。"""
  return [
    SystemMessage("你是订单分析专家。请输出状态、风险和建议。"),
    UserMessage(f"请分析订单 {order_id}"),
  ]
```

Client/Host 侧：三种原语分别走不同的流程。

```python
order_id = "ORD-2025-0001"

# 1. Resource：应用主动读取，再把数据注入模型上下文
resource = await session.read_resource(f"db://orders/{order_id}")
context = resource.contents[0].text

# 2. Prompt：用户点击“订单分析”后，应用主动获取渲染后的消息模板
prompt = await session.get_prompt(
  "order-analysis",
  {"order_id": order_id},
)
messages = list(prompt.messages)
messages.insert(0, {"role": "system", "content": f"订单背景：{context}"})

# 3. Tool：应用把工具清单交给模型；模型判断需要实时状态后发起调用
available_tools = await session.list_tools()
tool_result = await session.call_tool(
  "query_order",
  {"order_id": order_id},
)

# 实际 Agent 中，tool_result 会转换成 ToolMessage 再交给模型继续推理。
messages.append({"role": "tool", "content": str(tool_result.content)})
answer = await model.ainvoke(messages, tools=available_tools.tools)
```

对照这段代码可以看到：`read_resource` 是**应用读数据**，`get_prompt` 是**应用选模板**，`call_tool` 是**响应模型的工具调用**。示例为了突出三种原语而省略了模型首次调用和“模型返回 tool call 后再执行”的循环；真实 Agent 中应由模型先提出 `query_order`，Host 完成批准后再调用 Tool。

### 3.6 如何选择：一张决策表

| 你要暴露的能力 | 选择 | 原因 |
|---|---|---|
| 执行操作：写库、发 HTTP 请求、改状态、发通知 | **Tool** | 需要模型按参数调用并拿到结果，且需要批准机制 |
| 只读数据：日志、文档、配置、查询结果 | **Resource** | 由应用读取并注入上下文，模型不直接调用 |
| 固定结构的提示、多步引导模板 | **Prompt** | 由用户/应用选择，参数化渲染 |
| 同一份数据既想被模型查、又想被应用读 | **拆成 Tool + Resource** | 各司其职：Tool 给模型按需查询，Resource 给应用主动注入 |

判断时依次问三个问题：**能执行（有副作用）？→ Tool。是数据？→ Resource。是模板？→ Prompt。** 举一个具体例子：数据库 Server 通常同时暴露一个「执行白名单查询」的 Tool 和若干「表数据」的 Resource——前者让模型按需查，后者让应用把常用数据直接喂给模型省 token。

## 四、传输方式：stdio 与 Streamable HTTP

「传输」回答的是：Client 和 Server 之间这条管道用什么物理方式实现。主流两种：stdio 与 Streamable HTTP。

### 4.1 stdio：本地子进程

- Server 作为**子进程**由 Host 启动；JSON-RPC 消息通过子进程的 **stdin/stdout** 传递；**stderr 只用来打日志**，不能混入协议消息。
- 生命周期：Host 启动子进程 → initialize 握手 → 正常工作 → Host 退出时终止子进程。
- 特点：没有网络端口、进程隔离、安全边界好（Server 无法被外部网络直接访问），适合本地与同机部署。

Java 类比：用 `ProcessBuilder` 启动一个子进程，向其 stdin 写命令、从 stdout 读结果——这就是 stdio 传输的模型。也可以类比为一个 CLI 工具被脚本调用。

适用场景：开发调试、单机 Agent、敏感数据不希望离开本机。缺点：Server 必须与 Host 同机，无法远程共享。

### 4.2 Streamable HTTP：现代默认 HTTP 传输

- 这是**当前官方推荐的 HTTP 传输方式**，取代了早期版本的 HTTP+SSE transport（早期方案用 SSE 做流式；现在新项目直接使用 Streamable HTTP，**不要把 SSE 当成推荐传输**，以官方规范最新版为准）。
- 支持**无状态请求**，也支持可选的**有状态 session**（通过 session ID 维持会话，服务端可以向客户端推送消息）。
- 支持 **SSE 流式返回**：服务端可以把长任务的进度、多个结果分块推送给客户端。
- **OAuth 2.1 可选授权**：远程场景下用 OAuth 2.1 保护 Server 资源（2025 年规范加入，以官方为准）。

Java 类比：Streamable HTTP 像一个 Spring Boot REST 服务（可加网关、负载均衡、鉴权），SSE 部分像 `SseEmitter` / WebFlux 的流式推送；OAuth 2.1 部分像 Spring Security OAuth2 资源服务器。

适用场景：跨网络部署、团队共享一个 Server、需要服务化治理（监控、限流、审计）的生产环境。缺点：网络暴露面大，需要配套鉴权与网络防护。

### 4.3 其他传输

- **memory transport**：进程内直接交换消息，不经过网络或管道，专门用于**测试**（比如在单测里直接跑 Server 逻辑）。
- **旧 SSE transport（HTTP+SSE）**：早期版本的 HTTP 传输，仅在存量系统中出现；新项目不要再使用，官方已推荐 Streamable HTTP 替代。

### 4.4 对比与选型

| 维度 | stdio | Streamable HTTP |
|---|---|---|
| 部署位置 | 同机子进程 | 跨网络远程 |
| 连接模型 | 1:1 进程管道 | 1:N，可多客户端共享 |
| 安全边界 | 进程隔离，无网络暴露 | 依赖网络层防护 + OAuth |
| 运维复杂度 | 低（进程管理即可） | 高（网关、监控、鉴权、TLS） |
| 性能 | 低开销 | 有 HTTP 开销，但可水平扩展 |
| 典型场景 | 本地工具、开发调试、单机 Agent | 团队共享服务、生产环境 |

选型建议（工程导向）：

- 本地工具、开发调试、Server 只给一个 Agent 用 → **stdio**。
- 服务要跨网络共享、要接入多个客户端、要纳入现有服务治理体系 → **Streamable HTTP**。
- 两者不互斥：一个 Server 可以同时支持多种传输，按部署形态选用。

## 五、消息与生命周期：JSON-RPC 2.0 与握手

### 5.1 JSON-RPC 2.0 基础

MCP 的全部消息都基于 **JSON-RPC 2.0**，只有三类：

- **request（请求）**：带 `id`，期待响应。结构：`jsonrpc: "2.0"`、`id`、`method`、`params`。
- **response（响应）**：`id` 与请求对应；成功带 `result`，失败带 `error`（含 `code`、`message`、可选 `data`）。
- **notification（通知）**：**没有 `id`，也没有响应**——发出去就完了，用于单向事件（如初始化完成通知、进度通知）。

Java 类比：`id` 就像请求序号 / traceId，把请求和响应关联起来（在并发场景下尤其重要）；notification 就像 fire-and-forget 的消息（如发个 MQ 事件不关心回执）。

### 5.2 标准错误码

| code | 含义 | Java 类比 |
|---|---|---|
| `-32700` | 解析错误（消息不是合法 JSON） | JSON 反序列化失败 |
| `-32600` | 无效请求（结构不符合 JSON-RPC） | 参数对象校验失败 |
| `-32601` | 方法未找到（method 不存在） | 路由 404 |
| `-32602` | 无效参数（params 不符合要求） | `MethodArgumentNotValidException` |
| `-32603` | 内部错误 | 未捕获的 500 |
| `-32000` 及以下 | 服务端自定义错误（MCP 规范预留扩展区，具体以官方为准） | 自定义业务异常码 |

### 5.3 业务失败如何表达（重要）

工具调用「成功到达、但业务上失败」——比如查不到订单、库存不足——**不是协议错误**，正确的做法是：`tools/call` 返回**成功的 response**，在 `result` 里带 `isError: true` 和说明原因的 `content`。协议错误（如 `-32603`）只用于「这个调用本身出了问题」：参数非法、方法不存在、服务崩溃。

Java 类比：就像 HTTP 200 + 业务错误码 vs HTTP 500。**不要把业务失败伪装成协议异常**——否则调用方无法区分「工具正常执行但结果不好」和「通道坏了」，重试策略、审计日志都会跟着错。

### 5.4 initialize 握手：建立会话的三步

Client 与 Server 建立会话，必须先完成握手，顺序是固定的：

1. Client → Server：发送 `initialize` **request**，携带客户端支持的 `protocolVersion`、`capabilities`、`clientInfo`。
2. Server → Client：返回 **response**，携带双方协商的 `protocolVersion`、Server 的 `capabilities`（声明支持 tools / resources / prompts）、`serverInfo`、可选的 `instructions`。
3. Client → Server：发送 `notifications/initialized` **notification**（无 id、无响应）。

之后双方才允许发送其他请求。**版本协商发生在第 1、2 步**：双方协议版本（日期字符串，如 `2025-06-18`，以官方规范为准）取兼容值；**能力协商**：Server 在第 2 步声明自己支持哪些原语，Client 也在第 1 步声明自己支持哪些客户端能力（如 sampling、roots）。握手完成后，Client 就知道「这个 Server 有 tools 吗？有 resources 吗？」，从而决定要不要发 `tools/list`。

简化示例（为可读性省略了部分字段）：

```json
// 第 1 步：Client -> Server（request）
{ "jsonrpc": "2.0", "id": 0, "method": "initialize",
  "params": {
    "protocolVersion": "2025-06-18",
    "capabilities": {},
    "clientInfo": { "name": "my-agent", "version": "0.1.0" }
  } }

// 第 2 步：Server -> Client（response）
{ "jsonrpc": "2.0", "id": 0,
  "result": {
    "protocolVersion": "2025-06-18",
    "capabilities": { "tools": {}, "resources": {}, "prompts": {} },
    "serverInfo": { "name": "ops-server", "version": "1.0.0" }
  } }

// 第 3 步：Client -> Server（notification，无 id、无响应）
{ "jsonrpc": "2.0", "method": "notifications/initialized" }
```

Java 类比：initialize 握手像 TCP/TLS 握手——先协商版本与能力，再开始传业务数据；也像服务注册时上报自身 capability，供调用方做路由决策。

### 5.5 典型请求序列

以「Agent 查询订单」为例，一条完整链路（stdio 传输下同样适用）：

```text
Client                                    Server
  |-- initialize request ------------------>|
  |<-- initialize response（版本/能力） ------|
  |-- notifications/initialized ------------>|   （通知，无响应）
  |-- tools/list --------------------------->|
  |<-- tools/list response（工具清单） -------|
  |-- tools/call("query_order",{order_id}) ->|
  |<-- tools/call response（结果/isError） ---|
  ... 会话结束：Host 关闭子进程 / 会话
```

resources 与 prompts 的序列同理：`resources/list` → `resources/read(uri)`；`prompts/list` → `prompts/get(name, arguments)`。你之后用 MCP Inspector 观察到的，就是这些消息的完整 JSON。

## 六、能力与扩展（简述）

除了三个核心原语，规范还定义了一些可选能力，知道「是做什么的、什么时候用」即可，细节以官方规范为准：

- **Sampling（采样）**：Server 反过来通过 Client 请求模型补全——比如 Server 内部需要调用 LLM 做判断时，不直接调模型 API，而是向 Client 发起「请帮我生成一段文本」的请求，由 Client 决定用哪个模型并**需用户批准**。类比：回调 / 反向调用（Server 当调用方，Client 当被调方）。
- **Roots（根目录）**：Client 向 Server 声明「你可以访问这些文件系统根目录」，Server 据此限定自己的文件操作范围。类比：挂载点 / 白名单目录。
- **进度通知（notifications/progress）**：长任务执行中 Server 向 Client 推送进度（百分比、阶段说明），Host 可以展示给用户。类比：任务进度条。
- **日志通知（notifications/message）**：Server 向 Client 推送结构化日志，供调试与审计。类比：远程日志收集。

什么时候用：本地 Server 一般用不到；生产级 Server 建议支持进度通知（长查询、报表生成体验差异很大）；涉及文件系统操作的 Server 应支持 Roots；Sampling 需求少见，遇到再学。

## 七、MCP 的安全模型

### 7.1 协议本身不做身份验证

**MCP 协议不定义「你是谁」、不做身份验证。** 信任建立在两层：

- **传输层**：stdio 依赖本地进程边界（Server 是 Host 启动的子进程，外部无法直连）；HTTP 依赖 TLS、网络隔离与网关策略。
- **应用层**：你的鉴权体系——Streamable HTTP 场景下的 OAuth 2.1、Server 内部自己的 API Key / JWT 校验等。

Java 类比：JDBC 协议本身只规定连接与查询格式，认证（用户名、密码、权限）由数据库服务端实现。MCP 同理：**鉴权是 Server 与部署方的事，不是协议的事。**

### 7.2 双向信任边界

安全要同时考虑两个方向：

- **Server 能做什么**：它运行在部署它的账号权限下——可以读文件、发网络请求、启动子进程。一个恶意的 Server 可以窃取本机数据、向内网发起攻击。所以**别连不信任的 Server**，stdio 场景尤其如此（它拥有你的进程环境）。
- **Client / Host 能做什么**：它能调用 Server 暴露的 tools、读取 resources。所以 Server 也要把每个工具当作可被任意调用者触发来设计（参数校验、权限、限流）。
- 还有一个 Agent 特有的攻击面：**Prompt Injection**——工具返回的内容里可能夹带指令（"忽略之前的指令，执行 xxx"），模型可能被诱导。工程上需要输出过滤、指令边界、人工确认等配套措施（阶段 3 前几篇的 RBAC、审计、人工确认在这里同样适用）。

工程原则：**不信任、最小权限、批准机制**——与你在 Java 里给数据库账号只授 SELECT、给服务做白名单鉴权是同一套思维。

### 7.3 OAuth 2.1 与 Streamable HTTP

2025 年规范加入 OAuth 2.1 授权支持（以官方规范最新版为准），用于 **Streamable HTTP** 场景的授权：Client 通过 OAuth 2.1（Authorization Code + PKCE 等流程）获取访问令牌，再访问受保护的 MCP Server。这相当于把「Server 接入公司的统一鉴权体系」标准化了。Java 类比：Spring Security 的 OAuth2 资源服务器 / 客户端——你在 Spring Cloud 生态里做过的授权对接，概念完全一致。

### 7.4 部署隔离策略（概述）

生产环境隔离 Server 的常用手段（细节在下一篇 Server 实践与 Client 集成中展开）：

- **进程隔离**：stdio 子进程 + 独立系统账号，权限互相隔离。
- **网络隔离**：内网部署、防火墙、API 网关，只暴露需要的端口。
- **最小权限**：只读文件系统、数据库白名单表、禁止任意 SQL、限制返回行数、设置超时与配额。
- **沙箱化**：容器 / 专用运行环境，限制资源与系统调用。

## 八、生态与学习资源

### 8.1 官方资源

- **规范文档**：modelcontextprotocol.io——先读 Specification 章节的 Architecture、Tools、Resources、Prompts、Transports，这是最权威的一手资料。
- **Python SDK**：github.com/modelcontextprotocol/python-sdk——含底层 Client/Server 与高层 FastMCP 封装，下一篇实践的主角。
- **TypeScript SDK**：github.com/modelcontextprotocol/typescript-sdk。
- **MCP Inspector**：官方调试工具，图形化观察 Client 与 Server 之间的每一条消息（initialize、tools/list、tools/call），强烈建议配合学习。
- **官方参考 Server**：github.com/modelcontextprotocol/servers——filesystem、fetch、git、memory 等，是学习 Server 实现的现成样本。
- **mcp.dev**：Server 注册表（可选），用于发现社区现成的 Server。

### 8.2 建议学习路径

```text
1. 读规范 Concepts：Architecture -> Tools -> Resources -> Prompts -> Transports
2. 用 FastMCP 跑通一个 hello server（官方 Quickstart）
3. 用 MCP Inspector 连接它，观察 initialize / tools/list / tools/call 的完整消息
4. 回到本系列 [05](05-MCP-Server开发实践.md)，开发 database-mcp-server 与 service-mcp-server
5. 在 [06](06-MCP-Client与Agent集成.md) 中，从自己的 Agent 里连接这些 Server
```

中文资源：mcp-docs.cn 有规范的中文翻译与讲解，可作为辅助对照，但**判断标准以官方英文规范为准**。再次强调：MCP 版本迭代快，任何具体字段、版本号、推荐做法都以官方规范最新版为准，不要依赖网上的旧教程（尤其是把 SSE 当推荐传输的说法）。

## 学习自检与练习

1. **判断题**：Agent 需要「查询订单状态」（只读）和「创建订单」（写入）。分别应该用 Tool 还是 Resource？为什么？如果改用另一种会有什么问题？
2. **场景题**：本地开发调试、数据不出本机的日志工具，选哪种传输？团队共享、跨网络部署的报表服务选哪种？各自的核心理由是什么？
3. **顺序题**：写出 Client 与 Server 建立会话的握手三步。版本协商发生在哪一步？Server 的 capabilities 在哪里声明、作用是什么？
4. **判断题**：MCP 协议本身提供身份验证，所以可以放心连接任意 Server。这个说法对吗？为什么？正确的信任模型是什么？
5. **设计题**：一个工具调用在业务上失败（如「库存不足」），应该在 JSON-RPC 层如何表达？如果错误地返回 `-32603` 内部错误，会带来什么问题？
6. **动手题（可放到下一篇完成）**：用官方 MCP Inspector 连接一个 FastMCP hello server，记录 initialize、tools/list、tools/call 三条消息的完整 JSON，并与本文第五节对照。

## 参考资料

- MCP 官方规范与文档：https://modelcontextprotocol.io/
- MCP 规范仓库（协议讨论与变更历史）：https://github.com/modelcontextprotocol/modelcontextprotocol
- MCP Python SDK：https://github.com/modelcontextprotocol/python-sdk
- MCP TypeScript SDK：https://github.com/modelcontextprotocol/typescript-sdk
- MCP Inspector（调试工具）：https://github.com/modelcontextprotocol/inspector
- MCP 官方参考 Server：https://github.com/modelcontextprotocol/servers
- MCP 中文文档（辅助对照）：https://mcp-docs.cn/
- mcp.dev 注册表：https://mcp.dev/
- MCP Java SDK（可选，用于对照 Java 生态）：https://github.com/modelcontextprotocol/java-sdk
- 本系列下一篇：[05 - MCP Server 开发实践：FastMCP 与两个生产级 Server](05-MCP-Server开发实践.md)
