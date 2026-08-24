# FastAPI 学习文档

> 面向正在学习 Python Agent 工程的后端开发者。
>
> 本文基于 FastAPI 和 Pydantic v2，重点掌握如何构建异步 HTTP API，而不是覆盖所有 Web 开发细节。

## 一、FastAPI 是什么

FastAPI 是一个基于 Python 类型注解构建 API 的 Web 框架。它通常与以下组件一起使用：

- Starlette：Web 层和异步能力
- Pydantic：请求数据校验和响应序列化
- Uvicorn：ASGI 服务器

在 Agent 服务中，典型调用链是：

```text
HTTP 请求
  -> FastAPI 路由
  -> Pydantic 请求模型
  -> 依赖注入
  -> Service 业务逻辑
  -> LLM / 数据库 / 外部 API
  -> Pydantic 响应模型
  -> HTTP 响应
```

## 二、安装和启动

```bash
pip install fastapi uvicorn
```

创建 `main.py`：

```python
from fastapi import FastAPI


app = FastAPI(title="Agent Service")


@app.get("/")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
```

启动开发服务器：

```bash
uvicorn main:app --reload
```

访问：

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/redoc`

`main:app` 表示加载 `main.py` 中名为 `app` 的对象。

## 三、第一个接口

```python
from fastapi import FastAPI


app = FastAPI()


@app.get("/hello/{name}")
async def hello(name: str) -> dict[str, str]:
    return {"message": f"Hello, {name}"}
```

FastAPI 会根据函数签名识别：

- `GET /hello/{name}` 是路由
- `name` 是路径参数
- `str` 是参数类型
- 返回值是字典
- 类型信息会用于 OpenAPI 文档

## 四、路径参数和查询参数

### 4.1 路径参数

```python
@app.get("/tasks/{task_id}")
async def get_task(task_id: int) -> dict[str, int]:
    return {"task_id": task_id}
```

请求 `/tasks/10` 时，`task_id` 会被解析为整数。如果传入无法转换为整数的值，FastAPI 会返回校验错误。

### 4.2 查询参数

```python
@app.get("/tasks")
async def list_tasks(
    completed: bool | None = None,
    limit: int = 20,
) -> dict[str, object]:
    return {
        "completed": completed,
        "limit": limit,
    }
```

请求示例：

```text
GET /tasks?completed=false&limit=10
```

查询参数适合表达过滤、分页、排序和搜索条件。

### 4.3 参数约束

```python
from fastapi import Query


@app.get("/search")
async def search(
    keyword: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    return {"keyword": keyword, "limit": limit}
```

## 五、请求体和响应模型

请求体通常使用 Pydantic 模型：

```python
from fastapi import FastAPI
from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    priority: int = Field(default=1, ge=1, le=5)


class TaskResponse(BaseModel):
    id: int
    title: str
    priority: int
    completed: bool


app = FastAPI()


@app.post("/tasks", response_model=TaskResponse)
async def create_task(request: TaskCreate) -> TaskResponse:
    return TaskResponse(
        id=1,
        title=request.title,
        priority=request.priority,
        completed=False,
    )
```

请求示例：

```json
{
  "title": "学习 FastAPI",
  "priority": 2
}
```

`response_model` 的作用包括：

- 校验返回数据
- 过滤未声明的字段
- 生成 OpenAPI 文档
- 明确接口输出契约

请求模型和响应模型不要随意共用。响应中不应该意外暴露内部字段，例如密码哈希、内部权限标记和数据库字段。

## 六、状态码和异常

### 6.1 设置状态码

```python
from fastapi import FastAPI, status


@app.post(
    "/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_task(request: TaskCreate) -> TaskResponse:
    ...
```

常见状态码：

- `200 OK`：请求成功
- `201 Created`：创建成功
- `204 No Content`：成功但没有响应体
- `400 Bad Request`：请求格式或业务参数错误
- `401 Unauthorized`：未认证
- `403 Forbidden`：无权限
- `404 Not Found`：资源不存在
- `409 Conflict`：资源冲突
- `500 Internal Server Error`：服务器内部错误
- `502 Bad Gateway`：上游服务返回异常
- `504 Gateway Timeout`：上游服务超时

### 6.2 HTTPException

```python
from fastapi import HTTPException


@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int) -> TaskResponse:
    task = find_task(task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail="任务不存在",
        )
    return task
```

不要使用 `return {"error": "任务不存在"}` 代替正确的 HTTP 状态码，否则客户端无法可靠判断请求是否失败。

## 七、依赖注入

依赖注入（Dependency Injection，DI）是把对象需要的协作者从外部传入，而不是在对象内部直接创建。这样路由只负责 HTTP 适配，业务代码不需要知道数据库、认证组件或模型客户端的具体创建方式。

在 Agent 服务中，常见依赖包括：

- 配置对象：API Key、模型名称、超时时间和功能开关
- 当前用户：解析 JWT、Session 或 API Key，并完成权限检查
- 数据库会话：保证一次请求内的查询和事务边界
- 外部客户端：HTTPX、Redis、向量数据库和 LLM 客户端
- 业务 Service：组合仓储、权限校验和 Agent 编排逻辑

### 7.1 `Depends` 的基本用法

依赖就是一个可调用对象，FastAPI 会在处理请求前调用它，并把返回值传给路由参数。推荐使用 `Annotated` 为依赖声明命名类型：

```python
from typing import Annotated

from fastapi import Depends, FastAPI


class Settings:
    app_name = "agent-service"


app = FastAPI()


def get_settings() -> Settings:
    return Settings()


SettingsDependency = Annotated[Settings, Depends(get_settings)]


@app.get("/info")
async def get_info(settings: SettingsDependency) -> dict[str, str]:
    return {"app_name": settings.app_name}
```

一个依赖也可以依赖另一个依赖，FastAPI 会构建并解析依赖树。例如认证依赖可以复用配置依赖，当前用户依赖再复用认证依赖：

```python
from typing import Annotated

from fastapi import Depends, HTTPException, status


class CurrentUser:
    def __init__(self, user_id: str, roles: set[str]) -> None:
        self.user_id = user_id
        self.roles = roles


def get_current_user() -> CurrentUser:
    token = "从请求 Header 读取的 token"
    if token != "valid-token":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未认证",
        )
    return CurrentUser(user_id="user-1", roles={"reader"})


CurrentUserDependency = Annotated[
    CurrentUser,
    Depends(get_current_user),
]


@app.get("/profile")
async def get_profile(
    current_user: CurrentUserDependency,
) -> dict[str, str]:
    return {"user_id": current_user.user_id}
```

依赖可以声明在路由参数中，也可以声明在路由、`APIRouter` 或整个应用级别：

```python
from fastapi import APIRouter, Depends


router = APIRouter(
    prefix="/admin",
    dependencies=[Depends(require_admin)],
)
```

路由参数中的依赖适合需要使用返回值的场景；`dependencies` 适合只需要执行校验、而不需要把结果传给路由的场景。

### 7.2 数据库会话和 `yield`

数据库会话通常需要“创建、使用、关闭”三个步骤，可以用 `yield` 依赖表达资源释放逻辑：

```python
from collections.abc import Generator


def get_db() -> Generator[DatabaseSession, None, None]:
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()


DatabaseDependency = Annotated[
    DatabaseSession,
    Depends(get_db),
]


@app.get("/tasks")
async def list_tasks(
    db: DatabaseDependency,
) -> list[TaskResponse]:
    return await task_service.list_tasks(db)
```

`yield` 之前的代码负责准备资源，`yield` 之后的代码负责清理资源。数据库事务的提交和回滚应由 Service 或专门的事务边界统一管理，不要在每个路由里重复编写。

### 7.3 生命周期依赖与请求依赖的区别

不要把所有客户端都写成普通依赖中的 `Client()`：

- 应用级共享资源：HTTPX 客户端、数据库连接池、Redis 客户端和模型客户端，通常在 `lifespan` 中创建，在应用关闭时释放。
- 请求级资源：数据库 Session、当前用户、请求上下文，通常使用 `Depends`，每次请求独立创建或解析。
- 纯计算依赖：分页参数、权限判断和配置读取，可以直接使用普通函数。

依赖注入负责“如何提供给当前请求”，`lifespan` 负责“应用级资源何时创建和销毁”，两者不要混为一谈。大型项目可以让依赖从 `request.app.state` 读取共享客户端：

```python
from fastapi import Request


def get_llm_client(request: Request) -> LLMClient:
    return request.app.state.llm_client
```

### 7.4 Service 层也要注入依赖

DI 不应该只停留在路由层。Service 的构造函数也应接收仓储或客户端，这样业务逻辑可以脱离 FastAPI 单独测试：

```python
class TaskService:
    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository

    async def create(self, request: TaskCreate) -> TaskResponse:
        task = await self.repository.create(request)
        return TaskResponse.model_validate(task)


def get_task_service(
    db: DatabaseDependency,
) -> TaskService:
    return TaskService(TaskRepository(db))


TaskServiceDependency = Annotated[
    TaskService,
    Depends(get_task_service),
]


@app.post("/tasks", response_model=TaskResponse)
async def create_task(
    request: TaskCreate,
    service: TaskServiceDependency,
) -> TaskResponse:
    return await service.create(request)
```

对于简单项目，可以直接使用函数依赖；对于依赖配置复杂、需要明确生命周期的组件，可以使用类作为依赖。不要为了“使用 DI”把每个简单函数都包装成类。

### 7.5 测试时替换真实依赖

FastAPI 可以通过 `app.dependency_overrides` 在测试中替换依赖。例如不连接真实数据库，改用 Fake Service：

```python
from collections.abc import Iterator
from fastapi.testclient import TestClient


def get_fake_task_service() -> Iterator[TaskService]:
    yield FakeTaskService()


app.dependency_overrides[get_task_service] = get_fake_task_service

client = TestClient(app)
response = client.post(
    "/tasks",
    json={"title": "测试任务", "priority": 2},
)

assert response.status_code == 201
app.dependency_overrides.clear()
```

测试中应替换外部边界，而不是替换被测试的业务规则：数据库、LLM、支付、邮件和第三方 HTTP API 可以使用 Fake 或 Mock；Service 内部的权限判断、重试策略和状态转换仍应真实执行。

### 7.6 和 Java Spring 的对比

| 对比项 | FastAPI | Spring Boot |
|---|---|---|
| 注入入口 | 函数参数、`Depends`、`Annotated` | 构造器参数、`@Autowired`、`@Bean`、组件扫描 |
| 依赖解析 | FastAPI 在请求处理时解析依赖树 | Spring 容器启动时创建并装配 Bean，部分作用域按请求解析 |
| 默认生命周期 | 函数依赖通常按请求缓存一次；可用 `use_cache=False` 关闭 | Bean 默认 Singleton；也有 Prototype、Request、Session 等作用域 |
| 资源释放 | `yield` 依赖或 `lifespan` | `@PreDestroy`、`DisposableBean`、`try-with-resources` 等 |
| 请求级对象 | `Depends(get_db)`、当前用户依赖 | `@RequestScope` Bean、过滤器、拦截器或方法参数 |
| 全局共享客户端 | `app.state` 配合 `lifespan` | Singleton Bean，通常通过 `@Bean` 声明 |
| 测试替换 | `app.dependency_overrides` | `@MockBean`、测试配置、Profile 或替换 Bean |
| 认证与横切逻辑 | 依赖、Middleware、Security 工具 | Spring Security、Filter、Interceptor、AOP |

Java 开发者可以这样建立映射：

```text
FastAPI Depends(get_service)
  ≈ Spring 构造器注入 TaskService

FastAPI get_db() + yield
  ≈ Spring 注入请求级事务资源并在作用域结束后释放

FastAPI lifespan + app.state
  ≈ Spring @Bean(singleton) + 应用生命周期回调

FastAPI dependency_overrides
  ≈ Spring 测试配置中替换 Bean 或 @MockBean
```

但两者不是完全相同的容器模型：FastAPI 的依赖主要围绕请求处理函数组织，依赖是显式的函数调用图；Spring 则是完整的 IoC 容器，支持组件扫描、条件装配、多个 Bean 候选、复杂作用域和 AOP。FastAPI 项目通常不需要照搬 Spring 的大量注解和容器配置，优先使用显式函数依赖和构造器注入即可。

### 7.7 使用场景总结

- 认证和权限：解析当前用户，并在路由或 Router 级别复用权限校验。
- 多租户：从用户或请求头解析 `tenant_id`，让 Service 和仓储自动带上租户过滤条件。
- 数据库访问：每个请求获得独立 Session，并确保异常时释放资源。
- LLM 和工具客户端：从应用共享客户端中注入，避免每个请求重复建立连接。
- 配置切换：开发、测试、生产环境注入不同 Settings 或模型配置。
- 可测试架构：用 Fake LLM、Fake Repository 替换真实外部服务，稳定验证 Agent 业务逻辑。
- 统一审计：注入当前用户和请求标识，记录工具调用者、参数摘要和执行结果。

依赖注入的好处：

- 路由函数更容易测试
- 统一管理认证、配置和数据库连接
- 可以替换真实依赖为 Fake 实现
- 避免在每个路由中重复创建客户端

## 八、路由与 Service 分层

不要把所有逻辑都写在路由函数中：

```text
路由层：解析请求、调用 Service、返回响应
Service 层：业务规则和流程编排
Client 层：调用外部 API、数据库或模型
Schema 层：请求和响应数据结构
```

示例：

```python
from fastapi import APIRouter


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse)
async def create_task(request: TaskCreate) -> TaskResponse:
    task = await task_service.create(request)
    return task
```

### 8.1 `@router.post` 和 `@app.get` 的区别

这两个装饰器都用于注册 HTTP 路由，主要区别在于**路由注册到谁，以及路由是否可以被组合复用**：

| 写法 | 注册对象 | 常见位置 | 适用场景 |
|---|---|---|---|
| `@app.get("/answer")` | FastAPI 应用实例 `app` | `main.py` | 健康检查、简单接口、应用级入口 |
| `@router.post("", response_model=TaskResponse)` | `APIRouter` 实例 `router` | `routers/tasks.py` | 按业务模块拆分路由，配合前缀、标签和通用依赖 |

`app` 是最终运行的应用，Uvicorn 启动的就是它；`router` 是一组待装配的路由，必须通过 `app.include_router()` 注册到应用后才会生效。

直接注册到 `app`：

```python
app = FastAPI()


@app.get("/answer")
async def answer() -> dict[str, str]:
        return {"answer": "ok"}
```

这里的最终请求路径就是 `GET /answer`。`@app.get()` 里的路径通常写完整路径，因为它直接挂在应用上。

使用 `APIRouter` 分层：

```python
# routers/tasks.py
from fastapi import APIRouter


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse)
async def create_task(request: TaskCreate) -> TaskResponse:
        task = await task_service.create(request)
        return task
```

```python
# main.py
from fastapi import FastAPI

from app.routers.tasks import router as tasks_router


app = FastAPI()
app.include_router(tasks_router)
```

此时最终路径是 `POST /tasks`：

```text
APIRouter(prefix="/tasks") + @router.post("")
    = /tasks
```

`@router.post("")` 中的空字符串表示“当前 Router 的根路径”，不是没有路径。也可以写成 `@router.post("/")`，但通常要统一风格，避免不同路由产生尾部斜杠重定向差异。

`include_router` 还可以在装配时增加前缀、标签和通用依赖：

```python
app.include_router(
        tasks_router,
        prefix="/api/v1",
        tags=["v1-tasks"],
        dependencies=[Depends(require_login)],
)
```

如果 Router 自身已有 `prefix="/tasks"`，上面的最终路径就是 `POST /api/v1/tasks`。最终路径由 Router 前缀、`include_router` 前缀和装饰器路径拼接得到。

### 8.2 为什么业务路由优先使用 `APIRouter`

推荐按业务模块拆分：

```text
main.py                 -> 创建 app，注册各个 Router
routers/tasks.py        -> 任务相关接口
routers/chat.py         -> Agent 对话接口
routers/admin.py        -> 管理接口和管理员权限
services/task_service.py -> 任务业务逻辑
```

这样做的好处是：

- `main.py` 不会堆积所有接口。
- 每个模块可以独立设置 `prefix`、OpenAPI `tags` 和权限依赖。
- Router 可以在测试或不同版本 API 中重复装配。
- 业务路由更容易和 Service、Schema、Client 分离。

`@app.get` 并不是错误写法。小型项目或健康检查使用它很直接；当接口按用户、任务、对话等业务域增长时，应使用 `APIRouter` 管理模块边界。

### 8.3 和 Java Spring MVC 的对比

可以把它们大致对应为：

```text
FastAPI app
    ≈ Spring Boot 应用上下文和最终 Web 应用

FastAPI APIRouter
    ≈ 一个按业务拆分的 @RestController 模块

@app.get("/answer")
    ≈ @GetMapping("/answer") 直接声明完整接口路径

APIRouter(prefix="/tasks") + @router.post("")
    ≈ @RequestMapping("/tasks") + @PostMapping

app.include_router(router, prefix="/api/v1")
    ≈ 在 Controller 类或统一 Web 配置上增加 /api/v1 前缀
```

但 `APIRouter` 不是 Spring 的 IoC 容器，也不是一个独立运行的应用。它主要负责路由分组和装配；Service、数据库和 LLM 客户端仍应通过依赖注入提供给接口。

推荐项目结构：

```text
app/
  main.py
  schemas.py
  dependencies.py
  routers/
    tasks.py
  services/
    task_service.py
  clients/
    llm_client.py
```

## 九、异步路由

如果路由内部调用的是异步客户端，可以使用 `async def`：

```python
@app.get("/answer")
async def answer(question: str) -> dict[str, str]:
    result = await llm_client.complete(question)
    return {"answer": result}
```

不要在异步路由中调用阻塞操作：

```python
import time


@app.get("/bad")
async def bad_endpoint() -> dict[str, str]:
    time.sleep(3)
    return {"status": "done"}
```

应使用异步库，或者把确实无法异步化的阻塞函数放到线程中：

```python
import asyncio


@app.get("/file")
async def read_file() -> dict[str, str]:
    content = await asyncio.to_thread(load_file)
    return {"content": content}
```

## 十、生命周期和资源管理

需要在应用启动时创建、关闭资源时，可以使用 lifespan：

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = create_http_client()
    yield
    await app.state.http_client.aclose()


app = FastAPI(lifespan=lifespan)
```

适合放在生命周期中的资源：

- HTTPX `AsyncClient`
- 数据库连接池
- Redis 客户端
- 模型客户端
- 向量数据库客户端

## 十一、中间件和请求标识

中间件可以统一处理跨请求逻辑，例如请求日志、耗时统计和请求标识：

```python
import time

from fastapi import Request


@app.middleware("http")
async def add_process_time(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time"] = str(
        time.perf_counter() - start
    )
    return response
```

生产环境还应考虑：

- `trace_id` 或 `request_id`
- 结构化日志
- 敏感字段脱敏
- 请求体大小限制
- 认证和权限检查
- 超时和异常记录

## 十二、测试 FastAPI 接口

安装测试依赖：

```bash
pip install pytest httpx
```

使用 `TestClient`：

```python
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

测试创建任务：

```python
def test_create_task() -> None:
    response = client.post(
        "/tasks",
        json={"title": "测试任务", "priority": 2},
    )

    assert response.status_code == 201
    assert response.json()["title"] == "测试任务"
```

至少测试：

- 正常请求
- 缺少必填字段
- 字段值超出范围
- 不存在的资源
- 无权限请求
- 外部服务超时
- 外部服务返回错误

## 十三、Agent 接口设计示例

```python
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    answer = await agent_service.answer(
        message=request.message,
        conversation_id=request.conversation_id,
    )
    return answer
```

Agent API 还需要考虑：

- 流式响应和断开连接
- 对话 ID 和幂等性
- Token 和成本限制
- 工具调用超时
- Prompt Injection 防护
- 用户权限与数据隔离
- 日志中不记录敏感信息

## 十四、阶段 0 练习

实现一个任务 API：

- `POST /tasks`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `PATCH /tasks/{task_id}`
- `DELETE /tasks/{task_id}`

要求：

1. 请求和响应使用 Pydantic 模型。
2. 使用正确的状态码。
3. 不存在的任务返回 `404`。
4. 使用 Service 层保存业务逻辑。
5. 为接口编写 pytest 测试。
6. 使用 Pyright 和 Ruff 检查代码。

## 十五、验收标准

- 能创建带路径参数、查询参数和请求体的接口
- 能使用 Pydantic 校验请求和响应
- 能理解依赖注入并测试替换依赖
- 能区分同步路由和异步路由
- 能正确返回状态码和异常
- 能使用 lifespan 管理外部客户端
- 能使用 TestClient 编写接口测试
- 能设计一个基础 Agent `/chat` 接口

## 十六、常用命令

```bash
uvicorn app.main:app --reload
pytest
ruff check .
ruff format --check .
pyright
```

官方资源：[FastAPI 中文文档](https://fastapi.tiangolo.com/zh/)

## 十七、FastAPI 重点回顾

### 必须掌握

- **路由定义**：理解 `@app.get()`、`@router.post()` 和 `app.include_router()` 的区别，能够根据 `prefix` 拼出最终请求路径。
- **请求参数**：区分路径参数、查询参数和请求体，并使用类型注解声明参数类型。
- **Pydantic 模型**：使用 `BaseModel`、`Field` 和 `model_config` 校验请求数据、定义响应结构，避免直接接收和返回任意字典。
- **HTTP 语义**：正确使用 `200`、`201`、`204`、`400`、`401`、`403`、`404`、`422` 和 `500` 等状态码。
- **异常处理**：使用 `HTTPException` 返回客户端可以识别的错误，不用普通字典伪装错误响应。
- **依赖注入**：使用 `Depends` 提供认证用户、配置、数据库 Session、Service 和外部客户端。
- **分层设计**：路由层负责 HTTP 适配，Service 层负责业务规则，Client 层负责外部系统调用。

### 工程实践重点

- **同步与异步**：异步路由中使用异步客户端；无法异步化的阻塞操作使用 `asyncio.to_thread()`，避免阻塞事件循环。
- **资源生命周期**：应用级客户端使用 `lifespan` 创建和关闭，请求级资源使用带 `yield` 的依赖管理。
- **数据安全**：响应模型只暴露必要字段，认证、权限、租户隔离和敏感信息脱敏不能省略。
- **接口稳定性**：为接口设置超时、重试、幂等性和合理的错误处理，避免上游异常直接扩散。
- **路由拆分**：按照任务、对话、用户、管理等业务模块使用 `APIRouter`，不要把所有接口堆在 `main.py`。
- **自动文档**：利用 `/docs`、`/redoc` 和 OpenAPI 检查接口契约是否清晰、参数是否正确。
- **代码质量**：使用 pytest 验证行为，使用 Pyright 检查类型，使用 Ruff 检查代码风格和常见问题。

### Agent 接口重点

- 使用 Pydantic 限制消息长度、对话 ID 和请求字段格式。
- 对流式响应正确处理客户端断开和上游超时。
- 为模型调用设置 Token、时间和成本限制。
- 对工具调用进行参数校验、权限检查、超时、重试和审计。
- 记录 `request_id`、`conversation_id`、`agent_name`、模型名称、延迟和错误类型。
- 对 Prompt Injection、越权访问、敏感数据泄露和多租户数据混淆进行防护。

### 推荐掌握顺序

```text
路由和参数
    -> Pydantic 校验
    -> 状态码和异常
    -> APIRouter 分层
    -> Depends 依赖注入
    -> Service 业务层
    -> asyncio 异步编程
    -> lifespan 生命周期
    -> pytest、Pyright、Ruff
    -> Agent 接口生产化
```

判断是否真正掌握 FastAPI，可以独立完成一个任务或 Agent API，并同时做到：请求可校验、错误可识别、依赖可替换、资源能释放、代码可测试、接口可观测。
