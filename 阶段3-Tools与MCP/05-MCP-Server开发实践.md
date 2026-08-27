# MCP Server 开发实践：FastMCP 与两个生产级 Server

> 定位：阶段 3「Tools 与 MCP」的第五篇动手文档。上一篇《04 - MCP 协议与规范》讲清楚了协议层（Tools / Resources / Prompts 与三种传输方式）；本篇把这些概念全部落到代码：先用 FastMCP 快速写一个能跑的 Server，再手把手实现两个生产级 Server —— **database-mcp-server**（白名单查询 + 防注入 + 审计）和 **service-mcp-server**（JWT 鉴权 + 内部 API 代理 + 数据脱敏 + 审计），最后覆盖部署隔离、测试与调试。
> 适合读者：有 7 年 Java 后端经验、正在转型 Python AI Agent 工程师的开发者。文中会反复用 Spring Boot / Bean Validation / AOP / Maven 等 Java 概念做类比，帮助你迁移已有工程经验。
> 前置要求：已完成阶段 3 前四篇学习，机器上装好了 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。

## 学习目标

学完本篇，你应该能够：

1. 用 uv 初始化一个 MCP Server 项目并正确引入 `mcp`（Python SDK，1.x）依赖；
2. 用 FastMCP 定义 Tool / Resource / Prompt，并说清三者各自的触发时机；
3. 独立写出 database-mcp-server：白名单表查询、强制 LIMIT、参数化查询、防注入检查、审计日志；
4. 独立写出 service-mcp-server：JWT 校验、内部 REST API 代理、结果脱敏、调用审计；
5. 知道 stdio 与 streamable-http 两种部署方式的安全隔离要点，会写 Dockerfile；
6. 用 pytest + stdio client 写集成测试，会用 Inspector 调试，能定位常见报错。

---

## 一、环境准备：uv 建项目

### 1.1 为什么用 uv

uv 是 Python 生态里对标 Maven/Gradle 的工程管理工具：一个 `pyproject.toml` 相当于 `pom.xml`，`uv add` 相当于 `mvn dependency:add`，`uv run` 相当于 `mvn exec`，`.venv` 相当于每个项目自己的 JDK 运行时。它解决了 Python 开发者最头疼的「依赖地狱」问题，也是 MCP 官方文档推荐的工具链。

```bash
# 安装 uv（macOS / Linux / Windows WSL 均可）
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows PowerShell 用户: powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 初始化项目（指定 Python 版本，uv 会自动下载对应解释器）
uv init database-mcp-server --python 3.12
cd database-mcp-server

# 添加运行时依赖；mcp[cli] 的 extra 提供 mcp dev / mcp run 命令
uv add "mcp>=1.2,<2" pydantic asyncpg

# 开发期依赖
uv add --dev pytest pytest-asyncio
```

### 1.2 pyproject.toml 关键片段

初始化后 `uv add` 会自动写入 `[project]` 和依赖表。手工调整后大致如下（以你锁定的依赖版本文档为准）：

```toml
[project]
name = "database-mcp-server"
version = "0.1.0"
description = "白名单数据库查询 MCP Server"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.2,<2",
    "pydantic>=2.7",
    "asyncpg>=0.29",
]

[dependency-groups]
dev = [
    "mcp[cli]>=1.2,<2",
    "pytest>=8",
    "pytest-asyncio>=0.23",
]
```

> 注意：`mcp dev` / `mcp run` 命令来自 `mcp[cli]` extra。如果你只在 `[project]` 里加了 `mcp` 而没有 cli extra，命令行工具是不存在的 —— 报 `mcp: command not found` 时先检查这里。

### 1.3 目录结构

database-mcp-server 按职责拆文件（对比 Java 项目按包分层）：

```text
database-mcp-server/
├── pyproject.toml
├── .env.example            # 环境变量样例（含敏感项说明，.env 不进 git）
├── src/database_mcp_server/
│   ├── __init__.py
│   ├── server.py           # FastMCP 实例、工具定义、入口
│   ├── config.py           # 从环境变量读配置（类比 Spring @ConfigurationProperties）
│   ├── whitelist.py        # 表/列白名单 + SQL 安全检查
│   ├── db.py               # 数据库连接与参数化查询（类比 DAO / Repository）
│   └── audit.py            # 审计日志（类比 AOP 日志切面）
└── tests/
    └── test_server.py
```

后续第 6 章的 service-mcp-server 目录结构类似，只是把 `db.py` 换成 `auth.py`（JWT 校验，类比 Spring Security 的认证过滤器）和 `service.py`（内部 REST 客户端，类比 Feign Client）。

---

## 二、FastMCP 快速上手：第一个可运行 Server

FastMCP 是官方 Python SDK 提供的高层封装：你用「装饰器 + 普通函数」声明能力，它负责把函数签名编译成 JSON Schema、处理 JSON-RPC 消息、管理会话。类比：FastMCP 之于 MCP 协议，相当于 Spring Boot 之于 Servlet 规范 —— 你只写业务方法，容器帮你处理协议细节。

### 2.1 完整代码

先理解 FastMCP 在背后做了什么：`@mcp.tool()` 装饰 `add` 时，FastMCP 会用类型注解 + 函数签名生成一段 JSON Schema（参数名、类型、是否必填、description），并在内部登记 `name -> handler` 的映射。等客户端发来 `tools/call`，它把 `arguments` 反序列化、调用你的函数、再把返回值包装成协议规定的 `content` 结构。你写的函数和协议之间隔着一层「自动映射」，这和 Spring MVC 把方法参数绑定到 HTTP 请求是同构的 —— 所以调试时如果发现参数对不上，先怀疑映射层（类型、默认值），而不是业务逻辑。

```python
# server.py
from mcp.server.fastmcp import FastMCP

# 创建 MCP Server 实例，name 会出现在 initialize 响应的 serverInfo 里
mcp = FastMCP("calc-server")


@mcp.tool()
def add(a: float, b: float) -> float:
    """两个数相加。"""
    return a + b


@mcp.tool()
def divide(a: float, b: float) -> dict:
    """两个数相除。除数为 0 时返回业务错误而不是抛异常。"""
    if b == 0:
        return {"ok": False, "error": "除数不能为 0"}
    return {"ok": True, "result": a / b}


if __name__ == "__main__":
    # 默认 transport 是 stdio：MCP 协议消息走标准输入/输出管道
    mcp.run()
```

运行方式有三种：

```bash
# 方式 1：mcp CLI（需要 mcp[cli]），stdio 运行，无 Inspector
uv run mcp run server.py

# 方式 2：直接 python 执行（上面的 __main__ 分支）
uv run python server.py

# 方式 3：mcp dev —— 开发模式，自动热重载 + 打开 Inspector 调试台
uv run mcp dev server.py
```

客户端连上后，协议层的第一件事是 `initialize` 握手：客户端发 `initialize` 请求（带协议版本与 clientInfo），Server 回 `serverInfo`（就是你 `FastMCP("calc-server")` 里的名字）和它支持的协议版本；随后客户端发 `notifications/initialized` 通知，再 `tools/list` 拉能力清单。可以观察到：**Server 永远是被动响应方**，一切能力（tools/resources/prompts）只有被 `*_/list` 或 `*_/call` 问到才会暴露 —— 这也是为什么「工具描述写得好不好」直接决定 Agent 用不用它。

### 2.2 用 mcp dev + Inspector 观察协议消息

`mcp dev` 相当于「Spring Boot devtools + Swagger UI」二合一：

1. 执行 `uv run mcp dev server.py`，终端会打印类似 `MCP Inspector is now available at http://127.0.0.1:6274` 的地址；
2. 浏览器打开该地址。Inspector 通过 stdio 拉起你的 `server.py` 进程并自动完成 `initialize` 握手；
3. 左侧面板能看到已注册的 Tools（`add`、`divide`），这是客户端调用 `tools/list` 拿到的结果；
4. 点开 `add`，面板会根据 JSON Schema 渲染参数表单，填 `1` 和 `2` 后点 Run Tool —— 右侧的 Request/Response 面板会出现两条 JSON-RPC 消息：

```json
{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
 "params": {"name": "add", "arguments": {"a": 1, "b": 2}}}
{"jsonrpc": "2.0", "id": 1,
 "result": {"content": [{"type": "text", "text": "3.0"}], "isError": false}}
```

5. 切换到 Resources / Prompts 标签页，能看到对应的 `resources/list`、`prompts/list` 消息；
6. 修改 `server.py` 保存，`mcp dev` 会热重载进程，Inspector 自动重连 —— 这就是「改代码 → 立刻在协议层验证」的开发闭环。

> 现在你看到的 JSON-RPC 消息，就是上一篇《04 - MCP 协议与规范》讲的协议内容。协议不神秘：Client 发 `method` 请求，Server 回 `result` 或 `error`。注意 `mcp dev` 与 `mcp run` 的差别：前者面向开发（热重载 + Inspector），后者面向脚本化启动；两者都走 stdio 传输。`mcp dev` 需要 `mcp[cli]` extra，`mcp run` 亦然。

---

## 三、定义 Tools（进阶）

Tool 是 Agent 的「执行能力」：有输入参数、有返回值、可能有副作用（写库、发消息）。类比 Spring Boot 的 Controller 方法，但参数契约由 JSON Schema 描述。

### 3.1 参数描述与约束：Field 就是 Bean Validation

FastMCP 会用类型注解自动生成 JSON Schema，但裸注解信息量太少：`status: str` 在客户端眼里只是一个「任意字符串」，Agent 不知道该填 `paid` 还是 `shipped`，参数校验也无从谈起。用 `pydantic.Field` 给参数加描述、枚举、范围约束 —— 这正是你在 Java 里用 `@NotBlank` / `@Pattern` / `@Min` / `@Max` 做的事：

```python
from mcp.server.fastmcp import FastMCP
from pydantic import Field

mcp = FastMCP("orders-tool-server")


@mcp.tool()
def query_orders(
    status: str = Field(
        description="订单状态",
        pattern="^(paid|shipped|closed)$",   # 类比 @Pattern(regexp=...)
    ),
    limit: int = Field(default=20, ge=1, le=100, description="返回条数上限"),  # 类比 @Min/@Max
    keyword: str | None = Field(default=None, description="订单号模糊搜索关键字"),
) -> dict:
    """查询订单列表（演示用，第 6 章会给真正的数据库实现）。"""
    return {"ok": True, "status": status, "limit": limit, "keyword": keyword}


if __name__ == "__main__":
    mcp.run()
```

约束的好处：非法参数在客户端发起调用前就会被 Schema 校验拦下（Inspector 表单、类型化客户端都会做），服务端逻辑不用再防御一遍 —— 和 Bean Validation 在 Controller 入口校验是同一个思想。注意约束写进的是 JSON Schema（`pattern`、`minimum`、`maximum`），不是运行时校验器，最终行为以你锁定的 SDK 版本为准。

一个值得养成的习惯：**description 写得越具体，Agent 的调用成功率越高**。工具描述和参数描述会原样进入模型的上下文，模型据此决定「这个工具适不适合当前任务、参数该怎么填」。类比：接口文档（Swagger/OpenAPI）写得含糊，调用方就只能靠猜。

### 3.2 返回值：str / dict / Pydantic 模型

三种返回方式按需选择：

- **str**：返回纯文本内容（`content.type = "text"`）；
- **dict**：FastMCP 自动转成结构化内容（`content.type = "text"` 且同时填充 `structuredContent`），适合机器可读的数据，客户端可据此做结构化消费；
- **Pydantic 模型**：最推荐。模型即契约，序列化和校验都免费：

```python
from pydantic import BaseModel


class OrderSummary(BaseModel):
    order_id: str
    amount: float
    status: str


@mcp.tool()
def get_order(order_id: str) -> OrderSummary:
    """按订单号查订单摘要。"""
    return OrderSummary(order_id=order_id, amount=199.0, status="paid")
```

> Java 类比：`OrderSummary` 就是 DTO（数据传输对象）。让 FastMCP 把 DTO 直接序列化给客户端，比手拼 `dict` 更不容易出错。

### 3.3 错误处理：业务错误当作结果返回

先想清楚一个模型问题：工具调用失败对 Agent 意味着什么。如果工具抛异常，协议层返回的是 error 响应，多数客户端会把这次调用标记为「失败」—— 结果就是 Agent 只知道「工具坏了」，不知道「参数不对」还是「数据不存在」，也无法据此修正下一步动作。而**业务错误作为结构化结果返回**时，`{"ok": false, "error": "订单号格式不正确"}` 就是一段普通文本，Agent 能读懂原因、调整参数、重新调用或换一个工具，整个推理循环才能继续。所以：可预期的业务错误（查无数据、参数非法、权限不足）返回结果；真正意外的异常（连接断开、空指针）才抛给协议层并记日志。

```python
@mcp.tool()
def cancel_order(order_id: str, reason: str = "") -> dict:
    try:
        # 伪代码：真实实现里调用订单服务
        if not order_id.startswith("SO"):
            return {"ok": False, "error": "订单号格式不正确", "code": "BAD_ORDER_ID"}
        if reason and len(reason) > 200:
            return {"ok": False, "error": "取消原因不能超过 200 字", "code": "BAD_REASON"}
        return {"ok": True, "order_id": order_id, "status": "cancelled"}
    except Exception as e:  # 意外异常：记日志、向上抛
        import logging
        logging.getLogger(__name__).exception("cancel_order 失败: %s", order_id)
        raise
```

统一约定一个返回结构（`{"ok": bool, "data"?: ..., "error"?: ..., "code"?: ...}`），客户端和 Agent 处理起来都有章可循。

### 3.4 异步工具：查数据库

IO 密集的工具（查库、调 HTTP）写成 `async def`，FastMCP 会放进事件循环调度，不阻塞其他工具调用。异步 + 参数化查询是第 6 章的基础：

```python
import asyncpg
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("orders-db-server")
DSN = "postgresql://mcp_ro:secret@localhost:5432/orders"


@mcp.tool()
async def recent_orders(limit: int = 10) -> list[dict]:
    """返回最近 limit 条订单。参数化查询，值永远不拼进 SQL。"""
    conn = await asyncpg.connect(DSN)
    try:
        rows = await conn.fetch(
            "SELECT id, order_no, amount, status FROM orders ORDER BY created_at DESC LIMIT $1",
            limit,
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()
```

> 类比：Java 里你用 `@Async` + `CompletableFuture` 或者 WebFlux 处理 IO；Python 里 `async def` + `await` 就是这套心智模型的简化版。

工程注意点：上面每次调用都新建一个连接，生产环境应该用连接池（asyncpg 的 `Pool`），在 Server 启动时创建、随进程常驻 —— 对应你在 Java 里用 HikariCP 管理连接。另外工具名默认取函数名；多个工具重名或想对外暴露更友好的名字时，用 `@mcp.tool(name="...")` 显式指定，命名规则以你锁定的依赖版本文档为准。

---

## 四、定义 Resources

Resource 是 Server 暴露的「可寻址数据」：通过 URI 定位、按需读取、本身没有副作用。类比 Spring Boot 暴露的静态资源目录，或配置中心里可被直接拉取的数据项。

### 4.1 URI 设计：scheme 表达数据域

URI 的 scheme 表达「这是什么数据」，路径表达「哪一份数据」。约定俗成的语义：

- `file://docs/orders-api` —— 文档/知识文件；
- `db://orders/{order_id}` —— 数据库里的订单详情；
- `log://app/{date}` —— 某天的应用日志；
- `config://risk/rules` —— 配置或规则集。

scheme 只是约定，不强制绑定实现，但它让客户端一眼看懂资源域，也便于 Server 内做路由分发。

### 4.2 定义资源

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("orders-resource-server")


@mcp.resource("db://orders/{order_id}")
async def order_resource(order_id: str) -> str:
    """模板资源：按路径参数动态读取订单详情。"""
    # 伪代码：真实实现查库
    data = {"order_id": order_id, "amount": 199.0, "status": "paid"}
    return f"订单 {order_id}：金额 {data['amount']} 元，状态 {data['status']}"
```

客户端的使用流程：先 `resources/list` 拿到资源清单（包含 URI 模板 `db://orders/{order_id}`），再 `read_resource("db://orders/SO1001")` 读取具体实例。对客户端来说，Resource 是「按地址取数据」；对 Server 来说，模板参数绑定发生在 `read_resource` 那一刻 —— 和 Spring MVC 的 `@PathVariable` 如出一辙。

再看两个更完整的例子（一个静态文档、一个带 MIME 的 JSON 资源）：

```python
@mcp.resource("file://docs/orders-api")
def orders_api_doc() -> str:
    """静态资源：订单接口说明文档。"""
    return open("docs/orders-api.md", encoding="utf-8").read()
```

```python
from mcp.server.fastmcp import Content

@mcp.resource("db://orders/{order_id}/json")
async def order_resource_json(order_id: str) -> Content:
    """带 MIME 声明的资源：返回 JSON 文本。Content 的字段以你锁定的依赖版本文档为准。"""
    return Content(
        type="text",
        text='{"order_id": "' + order_id + '", "status": "paid"}',
        mimeType="application/json",
    )
```

要点：

- 函数返回 `str` 即文本内容；需要显式声明 MIME（如 `application/json`、`text/markdown`）时返回带 `mimeType` 的 `Content` 对象；
- `{order_id}` 是模板参数：客户端 `read_resource("db://orders/SO1001")` 时，FastMCP 把 `SO1001` 绑定进函数参数，和 `@PathVariable` 绑定路径片段是同一个机制。

### 4.3 Resource 还是 Tool？决策清单

| 判断 | 用 Resource | 用 Tool |
| --- | --- | --- |
| 数据形态 | 静态/半静态数据、文档、可寻址记录 | 动作、计算、有副作用 |
| 触发方式 | 客户端主动 `read_resource`（无参数或仅路径参数） | 客户端 `tools/call`（完整参数） |
| 是否变更状态 | 否 | 可能（写库、发消息） |
| 类比 Java | 静态资源 / 只读 GET 接口 | Controller 业务方法（含 POST） |

经验法则：**「读数据」倾向 Resource，「做事情」倾向 Tool**。订单详情既可以是 Resource（`db://orders/{id}`）也可以是 Tool（`get_order(id)`），两者并存也常见 —— Resource 给客户端做上下文补充，Tool 给 Agent 做推理动作。

---

## 五、定义 Prompts

Prompt 是 Server 提供的「提示词模板」：一段结构化的指令 + 占位参数，客户端拉取后注入到对话里。类比：代码生成器的模板文件，或 Spring 的 `MessageSource` —— 模板就在那里，但**必须有人显式渲染它**。

```python
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import UserMessage, SystemMessage

mcp = FastMCP("orders-prompt-server")


@mcp.prompt("order-analysis", description="生成订单分析提示词")
def order_analysis_prompt(order_id: str, focus: str = "异常原因") -> list:
    """订单分析模板：返回 SystemMessage + UserMessage 列表。"""
    return [
        SystemMessage("你是资深订单分析师。只依据提供的订单数据回答，不要编造。"),
        UserMessage(f"请分析订单 {order_id}，重点关注：{focus}。"),
    ]
```

也可以只返回一个字符串（FastMCP 会包装成 UserMessage）。协议层交互是两条消息：客户端先 `prompts/list` 拿到模板清单（名称、描述、参数 schema），用户选中后客户端再 `prompts/get` 并携带参数，Server 返回渲染好的 `messages`（就是你上面 return 的列表）。

触发方式说明：

- Prompt **不是模型自动调用的**，也不会被 Agent 自主发现后执行；
- 它由客户端/用户显式触发：例如支持 MCP 的 IDE 里 `/order-analysis SO1001` 这样的斜杠命令，客户端先 `prompts/list` 拿到模板清单，再 `prompts/get` 按参数渲染，最后把渲染结果作为用户消息送入对话；
- 对比之下，Tool 可以被模型自主选择调用 —— 这是两者最大的心智差异。

---

## 六、实战 Server 1：database-mcp-server（重点）

### 6.1 需求与设计

**需求**：把数据库查询能力暴露给 Agent，但只能查白名单表、禁止任意 SQL、限制返回行数、记录审计。

**威胁模型**（先想清楚防谁）：这个 Server 面向的是「可能被提示注入操纵的 Agent」。模型可能被用户的恶意 prompt 诱导去构造 `SELECT * FROM users WHERE ...; DROP TABLE ...` 之类的输入。我们的防御立场是：**即使 Agent 完全失控，它也只能在受限的只读视图内查询**。所以不是「尽力过滤恶意 SQL」，而是「根本不把构造 SQL 的自由交给调用方」。

**设计**：

1. 白名单配置：每张表声明「允许查询的列」和「允许作为查询条件的列」；
2. 用户**不提交 SQL 文本**，只提交表名、列名、条件值 —— SQL 由服务端用白名单信息拼装，条件值一律参数化；
3. 拼装结果仍过一遍 `validate_select_sql` 检查函数（只允许 SELECT、拒绝多语句/注释/UNION/危险关键字）作为最终防线；
4. LIMIT 强制：`limit` 参数先校验再钳制到表级上限（如 100），客户端传 10000 也只返回 100 行；
5. 审计：调用者、最终 SQL、参数、返回行数、耗时，写入结构化日志。

> 安全模型类比：这相当于「只开放了 Controller 里写死的一组只读 GET 接口 + MyBatis 预编译 `#{}`」，而不是把 SQL 执行器本身暴露出去。参数化查询对比 `$` 拼接，就是 `#{}` 与 `${}` 的区别。白名单的价值在于「允许列表」而非「拒绝列表」：黑名单永远列不全攻击面，白名单从根上把表、列、条件都限定死了。

**执行流**（对照 6.2 的代码走一遍）：`query_orders_tool` 收到参数 → `resolve_table` 校验表名 → `check_columns` 校验列 → 校验条件列 → `query_orders` 把条件值参数化拼进 SQL → `validate_select_sql` 终检 → 钳制 LIMIT → `asyncpg.fetch` 参数化执行 → 审计。任何一个环节拒绝，都会以 `{"ok": false, "error": ...}` 返回给 Agent —— 它看到错误信息就能自行修正参数。

**表结构假设**（PostgreSQL）：

```sql
CREATE TABLE orders (
    id            BIGSERIAL PRIMARY KEY,
    order_no      VARCHAR(32) UNIQUE NOT NULL,
    customer_name VARCHAR(64) NOT NULL,
    phone         VARCHAR(20),
    amount        NUMERIC(12, 2) NOT NULL,
    status        VARCHAR(16) NOT NULL,   -- paid / shipped / closed
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 6.2 完整代码

按目录结构逐个文件给出。先说明一个命名细节：工具函数叫 `query_orders_tool` 而不是 `query_orders`，是为了和 `db.py` 里的查询函数 `query_orders` 区分 —— 工具名会暴露给 Agent，函数名只是 Python 标识符，二者解耦后重构内部实现不影响协议契约。

运行前置条件：本地起一个 PostgreSQL 并建好 `orders` 表（见 6.1 的 DDL），设置环境变量 `DB_DSN`，然后 `uv run python -m database_mcp_server.server` 或 `uv run mcp dev src/database_mcp_server/server.py`。

```python
# config.py —— 环境变量集中读取（类比 @ConfigurationProperties）
import os

DSN = os.environ.get("DB_DSN", "postgresql://mcp_ro:secret@localhost:5432/orders")
MAX_ROWS = int(os.environ.get("MAX_ROWS", "100"))
# stdio 场景下由拉起 Server 的客户端进程注入；HTTP 场景由网关注入
CALLER = os.environ.get("MCP_CALLER", "unknown")
```

```python
# whitelist.py —— 白名单 + SQL 安全检查
import re

# 表名 -> {允许的列, 可作为查询条件的列, 行数上限}
TABLES = {
    "orders": {
        "columns": {"id", "order_no", "customer_name", "phone", "amount", "status", "created_at"},
        "filterable": {"order_no", "customer_name", "status"},  # 只允许等值条件
        "max_rows": 100,
    },
}


def resolve_table(table: str) -> dict:
    """表名必须命中白名单。"""
    if table not in TABLES:
        raise ValueError(f"表 {table} 不在白名单中，可用表: {sorted(TABLES)}")
    return TABLES[table]


def check_columns(cfg: dict, columns: list[str]) -> None:
    """列名必须属于白名单列。"""
    unknown = [c for c in columns if c not in cfg["columns"]]
    if unknown:
        raise ValueError(f"不允许查询的列: {unknown}")


FORBIDDEN_KEYWORDS = re.compile(
    r"\b(UNION|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|EXEC|COPY)\b",
    re.IGNORECASE,
)


def validate_select_sql(sql: str) -> None:
    """最终防线：拼装好的 SQL 必须满足只读 + 单语句 + 无注释。"""
    stripped = sql.lstrip()
    if not stripped.upper().startswith("SELECT"):
        raise ValueError("只允许 SELECT 语句")
    if ";" in stripped:                       # 拒绝多语句
        raise ValueError("不允许多语句")
    if "--" in stripped or "/*" in stripped or "*/" in stripped:
        raise ValueError("不允许 SQL 注释")
    if FORBIDDEN_KEYWORDS.search(stripped):
        raise ValueError("SQL 包含被禁止的关键字")
```

```python
# db.py —— 参数化查询 + LIMIT 钳制 + 耗时统计
import time

import asyncpg

from . import config
from .audit import audit
from .whitelist import validate_select_sql


async def query_orders(columns: list[str], filters: dict, limit: int) -> list[dict]:
    """在白名单表 orders 上执行受控查询，返回行列表。"""
    limit = max(1, min(limit, 100))  # 强制 LIMIT：无论传什么都钳制到 [1, 100]

    col_sql = ", ".join(columns)          # 列名已过白名单，可安全拼接
    where_parts: list[str] = []
    params: list[object] = []
    for col, value in filters.items():
        where_parts.append(f"{col} = ${len(params) + 1}")   # 条件值参数化
        params.append(value)

    where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
    sql = f"SELECT {col_sql} FROM orders{where_sql} LIMIT {limit}"
    validate_select_sql(sql)              # 拼装结果再过一次检查函数

    conn = await asyncpg.connect(config.DSN)
    start = time.monotonic()
    rows: list[dict] = []
    try:
        rows = [dict(r) for r in await conn.fetch(sql, *params)]
    finally:
        await conn.close()
        audit(config.CALLER, sql, params, len(rows), (time.monotonic() - start) * 1000)
    return rows
```

```python
# audit.py —— 结构化审计日志（类比 AOP 日志切面）
import json
import logging

logger = logging.getLogger("mcp.audit")


def audit(caller: str, sql: str, params: list, rows: int, duration_ms: float) -> None:
    record = {
        "caller": caller,
        "sql": sql,
        "params": params,
        "rows": rows,
        "duration_ms": round(duration_ms, 2),
    }
    logger.info("AUDIT %s", json.dumps(record, ensure_ascii=False, default=str))
```

```python
# server.py —— FastMCP 入口
from mcp.server.fastmcp import FastMCP

from .db import query_orders
from .whitelist import check_columns, resolve_table

mcp = FastMCP("database-mcp-server")


@mcp.tool()
async def query_orders_tool(
    columns: list[str],
    filters: dict[str, str] | None = None,
    limit: int = 50,
) -> dict:
    """在白名单表 orders 上查询订单。

    - columns: 要返回的列，只能是白名单列；
    - filters: 等值查询条件，只支持 order_no / customer_name / status；
    - limit: 返回行数上限，最大 100。
    """
    try:
        cfg = resolve_table("orders")
        check_columns(cfg, columns)
        for col in (filters or {}):
            if col not in cfg["filterable"]:
                raise ValueError(f"条件列 {col} 不允许作为查询条件")
        rows = await query_orders(columns, filters or {}, limit)
        return {"ok": True, "count": len(rows), "rows": rows}
    except ValueError as e:
        # 业务/校验错误作为结果返回，Agent 能看到原因并调整参数
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    mcp.run()
```

### 6.3 防注入检查清单（对照你的实现逐条打勾）

下面 10 条从「设计层」到「执行层」再到「事后层」排列。前三条是根因防御（白名单 + 参数化），中间是纵深防御（语句形态检查），最后是运行与审计兜底。逐条核对你的实现，缺一条都要问自己为什么能接受。

1. 用户永远不直接提供 SQL 文本，只提供表名/列名/条件值；
2. 表名、列名必须命中白名单映射，禁止拼接原始输入；
3. 所有条件值走参数化占位符（`$1` / `%s` / `?`），禁止字符串拼接；
4. 生成器只产出 SELECT，且最终 SQL 再过一遍关键字黑名单（UNION / INSERT / UPDATE / DELETE / DROP / ALTER / CREATE / TRUNCATE / EXEC / COPY）；
5. 拒绝多语句：SQL 中不允许分号（驱动默认也大多不支持，但不依赖默认行为）；
6. 拒绝注释符号（`--`、`/* */`），防止注释掉 WHERE 或 LIMIT 后缀；
7. LIMIT 强制：`int` 参数先校验再钳制上限，前端传 10000 也只返回 100 行；
8. 数据库账号最小权限：只授 SELECT（见第 8 章），即使注入成功也改不了数据；
9. 审计留痕：调用者 + 最终 SQL + 参数 + 行数 + 耗时，事后可追查、可告警；
10. 回归测试：把注入样本（`' OR '1'='1`、`1;DROP TABLE orders`、`--`、`UNION SELECT`、`/* */`）写进单测，防止后续改动把漏洞放回来。

---

## 七、实战 Server 2：service-mcp-server（重点）

### 7.1 需求与设计

**需求**：把内部业务 API（订单状态查询、报表生成、通知发送）暴露给 MCP 客户端；JWT 鉴权；记录调用者、参数和结果。

**设计**：

1. 调用者身份来自工具参数里的 `token`（JWT）—— HTTP 传输场景也可以由网关把身份塞进环境变量/请求头，这里用最直白的「参数传 token」讲清鉴权逻辑；
2. JWT 校验函数（依赖 PyJWT）：验签名、验过期，返回 `payload`（含 `sub` 用户、`role` 角色）；密钥从环境变量读，禁止硬编码；
3. 内部调用用 httpx 异步客户端，把 MCP 工具参数转成内部 REST 请求；
4. 返回结果脱敏：手机号打码后再交给 Agent；
5. 审计：调用者身份、参数、结果摘要写入日志。

> 类比：`verify_token` 就是 Spring Security 里的认证过滤器；`require_role` 是 `@PreAuthorize("hasRole('ops')")`；脱敏是你平时在 Response DTO 上做的 `@JsonSerialize` 打码逻辑；审计日志是 AOP 切面。

**调用链**（对照 7.2 代码）：Agent 调用工具 → `verify_token(token)` 验签与过期 → `require_role` 校验角色 → `call_internal` 带 token 调内部 REST → 返回结果先 `mask_payload` 脱敏 → `audit` 记录调用者/参数/结果摘要 → 结构化结果回给 Agent。JWT 的好处是身份信息自包含（`sub` 用户、`role` 角色都在 payload 里），Server 无需回查用户中心 —— 和你 Java 侧用 Spring Security OAuth2 Resource Server 验 JWT 是同一个心智。

### 7.2 关键代码

先补依赖：`uv add pyjwt httpx`。PyJWT 负责签发/校验 JWT（对应 Java 侧用 `jjwt` 或 Nimbus），httpx 是异步 HTTP 客户端（对应 Spring 的 `RestTemplate` / `WebClient`）。下面按文件给出。

```python
# config.py
import os

JWT_SECRET = os.environ["JWT_SECRET"]          # 必填，缺失直接启动失败
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
INTERNAL_API_BASE = os.environ.get("INTERNAL_API_BASE", "http://internal-svc:8080")
```

```python
# auth.py —— JWT 校验（PyJWT）
import jwt


class AuthError(Exception):
    """鉴权失败，message 会作为业务错误返回给客户端。"""


def verify_token(token: str) -> dict:
    """校验 JWT 并返回 payload。失败抛 AuthError。"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise AuthError("token 已过期")
    except jwt.InvalidTokenError:
        raise AuthError("token 无效")
    # 生产环境建议再校验 iss / aud，并优先 RS256 + 公钥验签
    return payload  # {"sub": "alice", "role": "ops", "exp": ...}


def require_role(payload: dict, *roles: str) -> None:
    """角色检查，类比 @PreAuthorize。"""
    if payload.get("role") not in roles:
        raise AuthError(f"角色 {payload.get('role')} 无权限，需要: {roles}")
```

```python
# mask.py —— 数据脱敏
def mask_phone(phone: str) -> str:
    """手机号打码：138****1234。"""
    if not phone or len(phone) < 7:
        return "***"
    return phone[:3] + "****" + phone[-4:]


def mask_payload(data: dict) -> dict:
    """对返回数据里的敏感字段统一脱敏。"""
    out = dict(data)
    if "phone" in out:
        out["phone"] = mask_phone(str(out["phone"]))
    return out
```

```python
# service.py —— 内部 REST 客户端（类比 Feign Client）
import httpx

from . import config


async def call_internal(method: str, path: str, *, params: dict | None = None,
                        json_body: dict | None = None, token: str) -> dict:
    """调用内部业务 API。token 透传给内部服务做二次校验。"""
    async with httpx.AsyncClient(base_url=config.INTERNAL_API_BASE, timeout=10.0) as client:
        resp = await client.request(
            method, path, params=params, json=json_body,
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()
```

```python
# server.py
import logging

from mcp.server.fastmcp import FastMCP

from .auth import AuthError, require_role, verify_token
from .mask import mask_payload
from .service import call_internal

logger = logging.getLogger("mcp.audit")
mcp = FastMCP("service-mcp-server")


def audit(caller: dict, tool: str, args: dict, result: dict) -> None:
    """审计：调用者 + 参数 + 结果摘要。"""
    logger.info(
        "AUDIT caller=%s tool=%s args=%s result_ok=%s",
        caller.get("sub"), tool, args, result.get("ok"),
    )


@mcp.tool()
async def query_order_status(order_id: str, token: str) -> dict:
    """查询订单状态（内部 API）。token: 调用方 JWT。"""
    try:
        identity = verify_token(token)
        data = await call_internal("GET", f"/api/orders/{order_id}", token=token)
        result = {"ok": True, "order": mask_payload(data)}   # 脱敏后再返回
        audit(identity, "query_order_status", {"order_id": order_id}, result)
        return result
    except AuthError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("查询订单状态失败")
        return {"ok": False, "error": f"内部服务异常: {type(e).__name__}"}


@mcp.tool()
async def send_notification(order_id: str, message: str, token: str) -> dict:
    """给订单相关人发送通知（写入类操作，需要 ops/admin 角色）。"""
    try:
        identity = verify_token(token)
        require_role(identity, "ops", "admin")               # 角色鉴权
        body = {"order_id": order_id, "message": message[:500], "operator": identity["sub"]}
        resp = await call_internal("POST", "/api/notifications", json_body=body, token=token)
        result = {"ok": True, "notification_id": resp.get("id")}
        audit(identity, "send_notification", {"order_id": order_id, "len": len(message)}, result)
        return result
    except AuthError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("发送通知失败")
        return {"ok": False, "error": f"内部服务异常: {type(e).__name__}"}


@mcp.tool()
async def generate_daily_report(date: str, token: str) -> dict:
    """生成指定日期的订单日报（触发内部异步任务，立即返回任务 id）。"""
    try:
        identity = verify_token(token)
        require_role(identity, "admin")
        resp = await call_internal("POST", "/api/reports/daily",
                                   json_body={"date": date}, token=token)
        result = {"ok": True, "task_id": resp.get("task_id")}
        audit(identity, "generate_daily_report", {"date": date}, result)
        return result
    except AuthError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("生成日报失败")
        return {"ok": False, "error": f"内部服务异常: {type(e).__name__}"}


if __name__ == "__main__":
    mcp.run()
```

### 7.3 两个工程注意点

- **token 作为工具参数**在 schema 里会暴露一个 `token` 字段。对内部部署（stdio 或内网 HTTP）这是可接受的简化；对外部生产环境，应改用 MCP 协议层的 HTTP 鉴权（见下一章 OAuth），业务 token 由网关注入，不让 Agent 感知。另外要意识到：token 会进入审计日志和模型上下文，务必在日志里对 token 本身脱敏（只记 `sub`/`exp`，不记 token 原文），这和你平时「日志不打印 Authorization 头」是同一纪律。
- 三个工具重复了 try/except + audit 样板。可以用装饰器或公共包装函数收敛（把 `verify_token` 抽成一个 `authed_tool` 装饰器），代码量减少的同时也避免漏审计 —— 这就是你熟悉的「统一 AOP 切面」思路，实现方式以你锁定的 SDK 版本为准。

---

## 八、部署与安全隔离

### 8.1 两种传输方式的部署差异

| 维度 | stdio | streamable-http |
| --- | --- | --- |
| 谁来拉起进程 | 客户端进程（IDE、Claude Desktop、你自己的 Agent 服务） | 你部署的常驻服务（Docker / k8s） |
| 网络暴露 | 无网络端口，进程间管道通信 | 暴露 HTTP 端口（默认 8000） |
| 权限隔离 | 以客户端进程的 OS 用户运行；权限=该进程能访问的一切 | 独立容器/账号，可精确控制网络与文件权限 |
| 环境变量 | 由客户端配置注入（每会话可不同，如 MCP_CALLER） | 容器环境变量 |
| 鉴权 | 信任拉起方（进程级信任） | 需要显式鉴权（OAuth / 网关） |
| 类比 Java | 本地工具进程 / IPC | 独立部署的微服务 |

**stdio 要点**：谁拉起进程，谁就拥有该进程的全部权限。所以：(1) 用最小权限 OS 用户运行客户端；(2) 数据库账号只读；(3) 敏感配置走环境变量，避免写进代码或配置仓库。stdio 的信任模型是「进程级信任」：没有协议层的鉴权，因为可信边界就是拉起方本身 —— 类比你把一个内部 jar 进程交给某个应用去 spawn，信任的是宿主进程而不是请求。因此 stdio 只适合「客户端进程本身可信」的场景（你自己的 Agent 服务、受控的 IDE 环境）；把 stdio Server 直接挂给不可信的外部调用方是不成立的。

### 8.2 streamable-http + Docker

server.py 里改用 HTTP 传输：

```python
if __name__ == "__main__":
    # 默认端口 8000；可用环境变量 MCP_PORT 或 mcp.settings.port 调整（以你锁定的依赖版本文档为准）
    mcp.settings.port = 8000
    mcp.run(transport="streamable-http")
```

HTTP 客户端连接时访问的是服务根路径（如 `http://127.0.0.1:8000/mcp`，具体路径以你锁定的 SDK 版本为准），之后按 streamable-http 规范用 SSE 流式收发 JSON-RPC 消息。开发阶段可以直接用 `curl` 验证端口通不通，再交给真正的 MCP 客户端做协议握手。

Dockerfile：

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

COPY src ./src
ENV DB_DSN=postgresql://mcp_ro:secret@pg:5432/orders
EXPOSE 8000

CMD ["uv", "run", "python", "-m", "database_mcp_server.server"]
```

```bash
docker build -t database-mcp-server .
# 只绑定回环地址，避免直接暴露到外网；放进内网网络 mcp-internal
docker run -d --name db-mcp \
  -p 127.0.0.1:8000:8000 \
  --network mcp-internal \
  -e DB_DSN=postgresql://mcp_ro:secret@pg:5432/orders \
  -e MAX_ROWS=100 \
  database-mcp-server
```

安全清单：容器只开 8000 且回环绑定（或由网关/反代转发）；数据库账号最小权限；HTTPS 终止在网关上；streamable-http 场景按 MCP 规范支持 OAuth 2.1 授权（Server 要求 access token，客户端走授权流程），对外生产务必启用，同时网关加限流（每用户 QPS），防止 Agent 循环调用打爆内部服务。限流与鉴权放在网关/反向代理层做，而不是写死在 Server 里 —— 和你在 Spring 里用网关（如 Spring Cloud Gateway）统一做认证限流是同一个架构决策。

### 8.3 最小权限原则（数据库账号只读）

给 MCP Server 单独建只读账号，绝不复用业务写账号：

```sql
CREATE USER mcp_ro WITH PASSWORD 'strong-password';
GRANT CONNECT ON DATABASE orders TO mcp_ro;
GRANT USAGE ON SCHEMA public TO mcp_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO mcp_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO mcp_ro;
```

这样即使 SQL 注入防线被突破，数据库层面也无法写入 —— 纵深防御的最后一道闸门。

---

## 九、测试与调试

### 9.1 pytest + stdio client 集成测试

用官方客户端库把 Server 当作黑盒测：拉起进程 → initialize → list_tools → call_tool。这比 Mock 内部函数更接近真实运行形态。测试分层建议：**单元测试**（`verify_token`、`mask_phone`、`validate_select_sql` 这类纯函数，快而全）＋ **集成测试**（stdio 黑盒，覆盖协议交互与安全边界）＋ 少量**手动 Inspector 验证**（排查协议层怪问题）。

```python
# tests/test_server.py
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
async def test_query_orders_tool():
    params = StdioServerParameters(command="python", args=["-m", "database_mcp_server.server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = [t.name for t in tools]
            assert "query_orders_tool" in names

            result = await session.call_tool(
                "query_orders_tool",
                {"columns": ["id", "order_no", "amount"],
                 "filters": {"status": "paid"}, "limit": 5},
            )
            text = result.content[0].text
            assert '"ok": true' in text


@pytest.mark.asyncio
async def test_query_orders_rejects_unknown_column():
    params = StdioServerParameters(command="python", args=["-m", "database_mcp_server.server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "query_orders_tool",
                {"columns": ["password"], "limit": 5},   # 白名单外的列
            )
            assert '"ok": false' in result.content[0].text
            assert "不允许查询的列" in result.content[0].text
```

运行：`uv run pytest -q`（测试需要真实数据库，可起本地 Postgres 或给测试注入内存 SQLite 实现 —— 把 `db.py` 的查询函数做成可替换的，便于单测注入）。

> 更轻量的做法是直接用内存 transport 在同一进程内跑 FastMCP（新版 SDK 提供内存客户端，具体 API 以你锁定的依赖版本文档为准），适合纯逻辑测试；stdio 集成测试则覆盖了完整的进程级行为，二者互补。

### 9.2 用 Inspector 调试

1. `uv run mcp dev server.py` 打开 Inspector；
2. 先看左侧 Tools/Resources/Prompts 是否齐全 —— 不全说明装饰器没生效（见下文常见报错）；
3. 对每个工具用表单跑一遍正常/异常参数，在 Request 面板核对 JSON-RPC 消息，在 Response 面板核对 `content` 与 `isError`；
4. 打开 Server 端日志（终端）对照审计输出与异常堆栈；
5. 修改代码保存，热重载后重跑，形成「改 → 验」闭环。

### 9.3 常见报错与排查

如果手头没有 Inspector，还有一个「原始」调试法：`uv run python server.py > server.out` 后，用任意方式往进程 stdin 写入一条 JSON-RPC `initialize` 消息，观察 stdout 的响应 —— 虽然繁琐，但能帮你确认「是协议层问题还是业务层问题」。生产排查顺序建议：先看 Server 进程 stderr（崩溃？缺环境变量？）→ 再看审计日志（调用是否到达业务层）→ 最后才怀疑协议序列化。

| 现象 | 根因与排查 |
| --- | --- |
| `initialize` 失败 / 连接超时 | 服务端启动即崩溃：先 `uv run python server.py` 直接跑看 stderr（import 错误、缺 `JWT_SECRET` 等环境变量）；或传输方式不匹配（服务端是 streamable-http，客户端却用 stdio_client 拉起） |
| `tools/list` 里看不到某个工具 | 装饰器没执行：确认装饰的是 `def` 定义的函数而不是 lambda；确认只有一个 FastMCP 实例且 `mcp.run()` 的就是注册了工具的那个；`mcp dev` 加载的是不是当前文件 |
| 调用时报 schema 不合法 | 参数类型无法映射为 JSON Schema：裸 `dict`/`set`、未建模的自定义类型；或 `Field` 的 default 与类型注解不符。改用基础类型 + `Field` 约束或 pydantic 模型 |
| 返回内容解析失败/为空 | 返回了不可 JSON 序列化的对象（`datetime`、`bytes`、`Decimal`）：先转 `str`/`isoformat()`，或用 pydantic 模型让 FastMCP 负责序列化 |

---

## 学习自检与练习

**自检**（能答上才算过关）：

1. Tool / Resource / Prompt 各自的触发时机是什么？为什么说「Prompt 不会被模型自动调用」？
2. 为什么 database-mcp-server 不直接暴露「执行任意 SQL」的工具？参数化查询为什么能挡住 `' OR '1'='1` 这类注入？
3. 白名单设计里，列名拼接为什么是安全的？`LIMIT` 为什么要二次钳制？
4. service-mcp-server 里 `AuthError` 为什么被转成 `{"ok": false, "error": ...}` 而不是让协议层报错？
5. stdio 部署为什么「不需要网络鉴权」？它的信任边界在哪里？

**练习 1：把白名单限制从「按表」扩展为「按角色」**

给 database-mcp-server 增加 `MCP_CALLER_ROLE` 环境变量，白名单配置改为「角色 → 允许的表/列」两级：

- `ops` 角色：可查全部白名单列；
- `viewer` 角色：只能查 `order_no / status / created_at`，不能查 `customer_name / phone / amount`；
- 越权访问返回 `{"ok": false, "error": "角色无权限访问列 ..."}`。

要求补上对应集成测试（viewer 查 phone 必须失败）。

**练习 2：service-mcp-server 的 JWT 单测**

用 pytest 写单元测试覆盖 `verify_token`：

- 用 `jwt.encode`（PyJWT）生成合法 token → 校验通过、payload 正确；
- 生成已过期 token（把 `exp` 设为过去时间）→ 抛 `AuthError`，错误信息含「过期」；
- 用错误密钥签名的 token → 抛 `AuthError`；
- 再用 mock 的 httpx 客户端测试 `send_notification` 的脱敏与角色校验分支（viewer 角色调用必须失败）。

**加分项**：把 `query_orders_tool` 的注入样本（`' OR '1'='1`、`1;DROP TABLE orders`、`UNION SELECT`、`--`、`/* */`）作为参数传入，断言全部返回 `ok: false` —— 这就是你的防注入回归测试。

---

## 参考资料

- MCP 官方规范（协议、传输、OAuth）：https://modelcontextprotocol.io/specification
- MCP Python SDK 文档（含 FastMCP 章节，API 以你锁定的版本为准）：https://py.sdk.modelcontextprotocol.io/
- MCP python-sdk GitHub：https://github.com/modelcontextprotocol/python-sdk
- uv 官方文档：https://docs.astral.sh/uv/
- PyJWT 文档：https://pyjwt.readthedocs.io/
- httpx 文档：https://www.python-httpx.org/
- Pydantic v2 文档（Field 约束与模型）：https://docs.pydantic.dev/
