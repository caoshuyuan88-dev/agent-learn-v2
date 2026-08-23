# HTTPX 学习文档

> 面向正在开发 FastAPI 和 Python Agent 服务的学习者。
>
> HTTPX 是一个支持同步和异步 HTTP 请求的 Python 客户端。Agent 服务通常需要调用 LLM、内部 REST API、MCP Server、搜索服务和数据库网关，因此必须正确处理超时、异常、连接复用和测试。

## 一、HTTPX 是什么

HTTPX 提供两种使用方式：

- 同步客户端：`httpx.Client`
- 异步客户端：`httpx.AsyncClient`

在 FastAPI 异步路由中，优先使用 `AsyncClient`：

```text
FastAPI async route
  -> HTTPX AsyncClient
  -> 外部 API
  -> 返回结果
```

## 二、安装

```bash
pip install httpx
```

## 三、第一个请求

### 3.1 同步请求

```python
import httpx


response = httpx.get(
    "https://example.com/api/users/1",
    timeout=10.0,
)

print(response.status_code)
print(response.json())
```

### 3.2 异步请求

```python
import httpx


async def get_user(user_id: int) -> dict[str, object]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"https://example.com/api/users/{user_id}"
        )
        response.raise_for_status()
        return response.json()
```

异步请求必须使用 `await`。调用异步函数时，不要把协程对象误当成最终结果。

## 四、常用请求方法

```python
async with httpx.AsyncClient() as client:
    response = await client.get(url, params={"limit": 20})
    response = await client.post(url, json={"name": "Alice"})
    response = await client.put(url, json={"name": "Bob"})
    response = await client.patch(url, json={"active": True})
    response = await client.delete(url)
```

常用参数：

- `params`：查询参数
- `json`：JSON 请求体
- `data`：表单数据
- `headers`：请求头
- `cookies`：Cookie
- `files`：文件上传
- `timeout`：超时时间

不要手动把字典拼接到 URL 中，查询参数使用 `params` 更安全：

```python
params = {"keyword": "python agent", "limit": 10}
response = await client.get(url, params=params)
```

## 五、请求头、认证和 JSON

```python
headers = {
    "Authorization": "Bearer replace-me",
    "Accept": "application/json",
}

async with httpx.AsyncClient(headers=headers) as client:
    response = await client.post(
        "https://example.com/api/messages",
        json={"message": "hello"},
    )
```

不要把 API Key 硬编码到源代码中，应从环境变量或配置对象中读取：

```python
import os


api_key = os.environ["API_KEY"]
```

在真实项目中，可以使用 Pydantic Settings 管理配置。

## 六、状态码和响应内容

### 6.1 检查状态码

```python
response = await client.get(url)
response.raise_for_status()
```

`raise_for_status()` 会在 4xx 或 5xx 状态码时抛出 `HTTPStatusError`。

如果需要分别处理状态码：

```python
if response.status_code == 404:
    return None

if response.status_code >= 500:
    raise RuntimeError("上游服务异常")

response.raise_for_status()
```

### 6.2 读取响应

```python
json_data = response.json()
text_data = response.text
bytes_data = response.content
```

外部响应也不应该完全相信。对于重要数据，建议使用 Pydantic 模型校验：

```python
from pydantic import BaseModel


class UserResponse(BaseModel):
    id: int
    name: str


user = UserResponse.model_validate(response.json())
```

## 七、超时

外部 HTTP 请求必须设置超时。HTTPX 支持连接、读取、写入和连接池超时：

```python
import httpx


timeout = httpx.Timeout(
    connect=3.0,
    read=20.0,
    write=10.0,
    pool=5.0,
)

async with httpx.AsyncClient(timeout=timeout) as client:
    response = await client.get(url)
```

不同操作可以设置不同时间：

- `connect`：建立连接允许等待的时间
- `read`：读取响应允许等待的时间
- `write`：发送请求体允许等待的时间
- `pool`：从连接池获取连接允许等待的时间

LLM 生成响应可能比普通接口慢，`read` 超时应根据模型和是否流式输出合理设置，但不能无限等待。

## 八、异常处理

HTTPX 常见异常层级：

```text
httpx.HTTPError
  -> RequestError
     -> ConnectError
     -> ReadTimeout
     -> WriteTimeout
     -> PoolTimeout
  -> HTTPStatusError
```

处理示例：

```python
import httpx


async def fetch_data(url: str) -> dict[str, object]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException as error:
        raise RuntimeError("外部服务超时") from error
    except httpx.HTTPStatusError as error:
        raise RuntimeError(
            f"外部服务返回错误状态码: {error.response.status_code}"
        ) from error
    except httpx.RequestError as error:
        raise RuntimeError("外部服务连接失败") from error
```

不要只捕获 `Exception` 后静默忽略，也不要把所有外部错误都伪装成成功响应。

## 九、Client 与连接复用

简单脚本可以使用 `async with` 创建客户端。长时间运行的 FastAPI 服务应复用客户端：

```python
import httpx


class UserClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def get_user(self, user_id: int) -> dict[str, object]:
        response = await self.client.get(f"/users/{user_id}")
        response.raise_for_status()
        return response.json()
```

使用 `base_url` 和统一请求头：

```python
client = httpx.AsyncClient(
    base_url="https://example.com/api",
    headers={"Accept": "application/json"},
    timeout=10.0,
)
```

不要在每次业务调用时都创建一个长期客户端。频繁创建会浪费连接，难以统一关闭，也会降低连接复用效果。

在 FastAPI 中，可以用 lifespan 管理：

```python
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(
        base_url="https://example.com/api",
        timeout=10.0,
    )
    yield
    await app.state.http_client.aclose()


app = FastAPI(lifespan=lifespan)
```

## 十、重试和幂等性

网络临时失败可以有限重试，但不要无条件重试所有请求。

通常更适合重试：

- 连接失败
- 临时网络错误
- 读取超时
- 某些 `5xx` 响应
- `429 Too Many Requests`，并遵守 `Retry-After`

通常不应该重试：

- `400` 参数错误
- `401` 或 `403` 权限错误
- 明确的业务拒绝
- 未确认是否幂等的写操作

`GET` 通常是幂等的。支付、创建订单、发送通知等写操作重试前必须设计幂等键，否则可能重复执行。

示例重试策略的关键配置：

```text
最大重试次数：不要无限重试
退避时间：逐渐增加等待时间
随机抖动：避免大量请求同时重试
总超时：限制一次业务调用的最长时间
```

## 十一、流式响应

LLM 常用流式返回。HTTPX 可以逐块读取响应：

```python
async with httpx.AsyncClient(timeout=None) as client:
    async with client.stream("GET", url) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if line:
                print(line)
```

流式请求仍然要考虑：

- 建立连接超时
- 首字节等待时间
- 长时间没有数据的读取超时
- 客户端断开后的资源清理
- 上游错误如何传递给调用方

不要简单地把所有流式响应内容一次性读入内存。

## 十二、文件上传

```python
files = {
    "file": ("document.txt", b"hello", "text/plain"),
}

async with httpx.AsyncClient() as client:
    response = await client.post(upload_url, files=files)
    response.raise_for_status()
```

生产环境上传文件时需要额外限制：

- 文件大小
- 文件类型
- 文件名和路径
- 病毒扫描
- 上传超时
- 临时文件清理

## 十三、测试 HTTPX 调用

HTTP 调用不应该在单元测试中真正访问互联网。HTTPX 提供 `MockTransport`：

```python
import httpx


def mock_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/users/1":
        return httpx.Response(
            200,
            json={"id": 1, "name": "Alice"},
        )
    return httpx.Response(404, json={"detail": "not found"})


async def test_get_user() -> None:
    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://test.local",
    ) as client:
        response = await client.get("/users/1")

    assert response.status_code == 200
    assert response.json()["name"] == "Alice"
```

测试中应覆盖：

- 正常响应
- `404` 或 `400`
- `500`
- 连接错误
- 读取超时
- 返回 JSON 格式错误
- 重试次数和最终失败结果

## 十四、FastAPI + HTTPX 集成

```python
import httpx
from fastapi import FastAPI


app = FastAPI()


@app.get("/proxy/user/{user_id}")
async def proxy_user(user_id: int) -> dict[str, object]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(
            f"https://example.com/users/{user_id}"
        )
        response.raise_for_status()
        return response.json()
```

这个示例适合学习，但正式服务应把客户端放入 lifespan，并通过依赖注入传给 Service，避免每个请求都创建客户端。

## 十五、Agent 服务中的安全注意事项

使用 HTTPX 调用外部地址时，至少考虑：

- 不允许用户输入直接决定任意 URL，防止 SSRF
- 使用允许访问的域名白名单
- 限制重定向次数或关闭不必要的重定向
- 限制响应体大小
- 设置连接、读取和总超时
- 日志中隐藏 Authorization 和 API Key
- 对外部 JSON 使用 Pydantic 校验
- 对写操作使用幂等键和审计日志
- 不把上游完整错误内容直接返回给最终用户

## 十六、阶段 0 练习

实现一个 `WeatherClient`：

```python
class WeatherClient:
    async def get_weather(self, city: str) -> WeatherResponse:
        ...
```

要求：

1. 使用 `httpx.AsyncClient`。
2. 配置连接和读取超时。
3. 对响应调用 `raise_for_status()`。
4. 使用 Pydantic 校验响应 JSON。
5. 将 HTTPX 异常转换为业务异常。
6. 使用 `MockTransport` 测试成功、超时和 `500`。
7. 在 FastAPI 路由中调用这个客户端。

## 十七、验收标准

- 能发送 GET、POST 请求
- 能正确使用 `params`、`json` 和 `headers`
- 能区分 `response.json()`、`response.text` 和 `response.content`
- 能使用 `raise_for_status()`
- 能配置不同类型的超时
- 能区分连接异常和 HTTP 状态码异常
- 能在 FastAPI lifespan 中管理异步客户端
- 能理解连接复用和客户端关闭
- 能设计有限重试和幂等策略
- 能使用 MockTransport 测试外部 HTTP 调用
- 能识别 Agent 服务中的 SSRF、密钥泄露和无限等待风险

## 十八、常用命令

```bash
pytest
ruff check .
ruff format --check .
pyright
```

官方资源：[HTTPX 官方文档](https://www.python-httpx.org/)
