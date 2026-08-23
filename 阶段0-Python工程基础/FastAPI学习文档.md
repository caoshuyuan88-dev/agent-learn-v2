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

FastAPI 的依赖注入可以统一提供数据库会话、当前用户、配置和外部客户端。

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
