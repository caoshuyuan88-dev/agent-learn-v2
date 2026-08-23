# Python 基础、类型注解、面向对象、异常处理与 asyncio

> 面向有 Java 后端经验、准备开发 Python Agent 服务的学习者。
>
> 本文基于 Python 3.11+，重点不是覆盖所有语法，而是建立能够读懂、编写、调试 FastAPI 和 Agent 项目的工程基础。

## 一、学习目标

完成本文后，你应该能够：

- 使用 Python 基本数据类型、流程控制、函数和模块
- 理解可变对象、不可变对象以及引用行为
- 使用类型注解描述函数、集合、联合类型和异步代码
- 使用类、继承、组合和协议组织业务代码
- 区分异常、返回值和日志的职责
- 编写可靠的异常处理和资源清理代码
- 理解同步代码、协程、任务和事件循环
- 使用 `asyncio` 并发执行 I/O 操作
- 为异步代码设置超时、取消任务和限制并发
- 避免在异步服务中阻塞事件循环

## 二、Python 与 Java 的几个关键差异

| Python | Java 中相近的概念 | 需要注意的差异 |
|---|---|---|
| 变量 | 变量 | 变量是对象的名字，不是固定类型的存储槽 |
| `list` | `ArrayList` | 可以存放不同类型，但工程代码应保持元素类型一致 |
| `dict` | `HashMap` | 键值结构灵活，常用于 JSON 数据 |
| `None` | `null` | 使用 `is None` 判断，不使用 `== None` |
| `def` | 方法 | 函数是一等对象，可以作为参数传递 |
| `async def` | 异步方法 | 返回协程对象，需要 `await` 才会执行 |
| 异常 | Exception | 不要用异常代替所有正常流程控制 |
| 模块 | 类或包 | 一个 `.py` 文件就是一个模块 |

Python 代码重视可读性和简单组合。对于 Agent 服务，常见的代码组织方式是：

```text
请求模型 / 配置
  -> 路由
  -> Service 业务逻辑
  -> 外部 API 或数据库
  -> 响应模型
```

## 三、基础语法

### 3.1 变量和基本类型

```python
name = "Alice"
age = 30
ratio = 0.85
active = True
nothing = None
```

使用 `type()` 查看运行时类型：

```python
print(type(name))
print(type(age))
```

推荐使用有意义的变量名：

```python
request_timeout_seconds = 10
max_retry_count = 3
```

不要使用单字母变量名表达业务概念，例如使用 `user_id`，不要使用 `u`。

### 3.2 字符串

优先使用 f-string：

```python
user_id = 42
message = f"正在查询用户 {user_id}"
```

常用操作：

```python
text = "  FastAPI Agent  "
cleaned = text.strip()
upper_text = text.upper()
parts = "a,b,c".split(",")
```

不要通过字符串拼接构造 SQL、Shell 命令或 HTML。涉及外部输入时，应使用对应库提供的参数化 API。

### 3.3 列表、元组、集合和字典

```python
names = ["Alice", "Bob"]
coordinates = (31.2, 121.5)
unique_tags = {"python", "agent"}
user = {"id": 1, "name": "Alice"}
```

选择容器时可以这样判断：

- `list`：有顺序、允许重复、需要增删元素
- `tuple`：有顺序、不希望修改的数据组合
- `set`：去重和集合运算
- `dict`：通过键查找值

字典读取：

```python
user_name = user["name"]
optional_email = user.get("email")
```

`user["email"]` 在键不存在时会抛出 `KeyError`，`user.get("email")` 默认返回 `None`。

### 3.4 条件和循环

```python
if age >= 18:
    category = "adult"
elif age >= 13:
    category = "teenager"
else:
    category = "child"
```

`for` 遍历：

```python
for name in names:
    print(name)

for index, name in enumerate(names, start=1):
    print(index, name)
```

字典遍历：

```python
for key, value in user.items():
    print(key, value)
```

避免在循环中修改正在遍历的列表。可以遍历副本，或者先构造新的列表。

### 3.5 推导式

列表推导式适合简单转换和过滤：

```python
numbers = [1, 2, 3, 4, 5]
squares = [number * number for number in numbers]
even_numbers = [number for number in numbers if number % 2 == 0]
```

字典推导式：

```python
lengths = {name: len(name) for name in names}
```

如果推导式包含多层循环或复杂条件，应改为普通循环或提取函数，优先保证可读性。

## 四、函数

### 4.1 定义和返回值

```python
def calculate_total(price: float, quantity: int) -> float:
    return price * quantity
```

函数应尽量做到：

- 一个函数只负责一个清晰的动作
- 参数和返回值有类型注解
- 不隐藏意外的全局状态修改
- 对外部依赖通过参数传入，便于测试

### 4.2 默认参数

```python
def greet(name: str, prefix: str = "Hello") -> str:
    return f"{prefix}, {name}"
```

不要使用可变对象作为默认参数：

```python
# 不推荐

def add_tag(tag: str, tags: list[str] = []) -> list[str]:
    tags.append(tag)
    return tags
```

正确写法：

```python
def add_tag(tag: str, tags: list[str] | None = None) -> list[str]:
    if tags is None:
        tags = []
    tags.append(tag)
    return tags
```

### 4.3 关键字参数和解包

```python
def connect(host: str, port: int, timeout: float = 10.0) -> None:
    print(host, port, timeout)


connect(host="localhost", port=5432, timeout=5.0)
```

`*` 和 `**` 可以限制或表达关键字参数：

```python
def request(url: str, *, timeout: float = 10.0) -> None:
    print(url, timeout)
```

此时 `timeout` 必须使用关键字传递，有助于避免调用时看不懂参数含义。

### 4.4 作用域和闭包

函数内部变量默认只在函数内部有效：

```python
def build_message(name: str) -> str:
    message = f"Hello, {name}"
    return message
```

尽量少使用 `global`。如果多个函数共享状态，优先使用类、数据对象或显式传参表达依赖。

## 五、模块、包和项目结构

一个 `.py` 文件就是一个模块。可以导入模块中的函数或类：

```python
from datetime import datetime

from app.services import TaskService
```

推荐使用绝对导入，并避免通配符导入：

```python
# 推荐
from app.schemas import TaskCreate

# 不推荐
from app.schemas import *
```

一个简单项目可以这样组织：

```text
app/
  __init__.py
  main.py
  schemas.py
  services.py
  clients.py
tests/
  test_services.py
```

常见职责：

- `schemas.py`：数据模型和请求响应结构
- `services.py`：业务逻辑
- `clients.py`：外部 HTTP 或数据库客户端
- `main.py`：应用入口和路由
- `tests/`：测试代码

```python
if __name__ == "__main__":
    main()
```

这段代码表示：只有直接运行当前文件时才执行 `main()`，被其他模块导入时不会执行。

## 六、类型注解

类型注解主要用于三件事：

1. 让代码意图更清楚。
2. 让 IDE 和 Pyright 发现错误。
3. 让团队在修改代码时有明确契约。

类型注解不会自动完成运行时校验。运行时数据校验应使用 Pydantic 等工具。

### 6.1 基本写法

```python
def format_user(user_id: int, name: str) -> str:
    return f"{user_id}: {name}"


user_ids: list[int] = [1, 2, 3]
user_names: dict[int, str] = {1: "Alice"}
```

Python 3.11+ 推荐使用内置泛型写法：

```python
list[str]
dict[str, int]
tuple[str, int]
set[str]
```

### 6.2 None 和联合类型

```python
def find_user(user_id: int) -> str | None:
    if user_id == 1:
        return "Alice"
    return None
```

调用时必须考虑 `None`：

```python
user_name = find_user(2)
if user_name is not None:
    print(user_name.upper())
```

不要假设返回值一定存在，也不要用 `# type: ignore` 粗暴隐藏类型问题。

### 6.3 类型别名和 Literal

```python
from typing import Literal, TypeAlias


UserId: TypeAlias = int
TaskStatus = Literal["todo", "doing", "done"]


def update_status(status: TaskStatus) -> None:
    print(status)
```

`Literal` 适合表示有限的字符串选项。更复杂的业务状态可以使用 `Enum`。

### 6.4 TypedDict

当你需要描述一个字典结构，但不需要创建运行时对象时，可以使用 `TypedDict`：

```python
from typing import TypedDict


class UserData(TypedDict):
    id: int
    name: str


def display_user(user: UserData) -> str:
    return f"{user['id']}: {user['name']}"
```

如果外部输入必须在运行时校验，优先使用 Pydantic `BaseModel`。

### 6.5 Protocol

`Protocol` 用于描述“只要具备这些方法，就可以被使用”的接口：

```python
from typing import Protocol


class MessageSender(Protocol):
    def send(self, message: str) -> None:
        ...


def notify(sender: MessageSender, message: str) -> None:
    sender.send(message)
```

这适合为外部服务定义轻量抽象，测试时可以传入假的实现。

### 6.6 类型检查

使用 Pyright 检查项目：

```bash
pyright
```

建议逐步提高代码质量：

```text
先给公共函数添加类型
  -> 修复明确的类型错误
  -> 给 Service 和 Client 添加类型
  -> 逐步减少 Any
```

## 七、面向对象编程

Python 的类适合封装状态和行为，但不是所有逻辑都必须写成类。简单转换优先使用函数；需要维护状态、替换实现或管理依赖时再使用类。

### 7.1 定义类

```python
class Task:
    def __init__(self, title: str) -> None:
        self.title = title
        self.completed = False

    def complete(self) -> None:
        self.completed = True


task = Task("学习 Python")
task.complete()
```

### 7.2 dataclass

如果一个类主要用于保存数据，可以使用 `dataclass`：

```python
from dataclasses import dataclass


@dataclass
class Point:
    x: float
    y: float
```

`dataclass` 会帮助生成初始化方法和对象表示。它不等于 Pydantic：

- `dataclass` 主要用于 Python 内部数据对象
- Pydantic 主要用于外部数据校验和序列化

### 7.3 实例方法、类方法和静态方法

```python
class User:
    user_count = 0

    def __init__(self, name: str) -> None:
        self.name = name
        User.user_count += 1

    def display_name(self) -> str:
        return self.name

    @classmethod
    def anonymous(cls) -> "User":
        return cls("anonymous")

    @staticmethod
    def normalize_name(name: str) -> str:
        return name.strip().lower()
```

常见使用场景：

- 实例方法：需要访问对象状态
- 类方法：提供替代构造方式
- 静态方法：逻辑属于类的概念，但不依赖实例或类状态

### 7.4 继承和组合

继承示例：

```python
class Animal:
    def speak(self) -> str:
        raise NotImplementedError


class Dog(Animal):
    def speak(self) -> str:
        return "woof"
```

实际业务代码通常优先组合：

```python
class OrderService:
    def __init__(self, payment_client: "PaymentClient") -> None:
        self.payment_client = payment_client
```

`OrderService` 不需要继承 `PaymentClient`，只需要持有一个客户端并调用它。组合更容易替换依赖和编写测试。

### 7.5 抽象接口

```python
from abc import ABC, abstractmethod


class LLMClient(ABC):
    @abstractmethod
    async def complete(self, prompt: str) -> str:
        raise NotImplementedError
```

Agent 项目中可以通过抽象接口隔离具体模型供应商，测试时使用 FakeLLMClient。

## 八、异常处理

### 8.1 异常的基本结构

```python
try:
    value = int("not-a-number")
except ValueError:
    value = 0
```

捕获具体异常，不要默认捕获所有异常：

```python
# 不推荐
try:
    do_work()
except Exception:
    pass
```

这种写法会隐藏真正的程序错误，使排查变得困难。

### 8.2 else 和 finally

```python
file = None
try:
    file = open("data.txt", encoding="utf-8")
    content = file.read()
except FileNotFoundError:
    content = ""
else:
    print("文件读取成功")
finally:
    if file is not None:
        file.close()
```

更推荐使用上下文管理器自动清理资源：

```python
with open("data.txt", encoding="utf-8") as file:
    content = file.read()
```

### 8.3 自定义异常

```python
class AppError(Exception):
    """应用层异常基类。"""


class UserNotFoundError(AppError):
    def __init__(self, user_id: int) -> None:
        super().__init__(f"用户不存在: {user_id}")
        self.user_id = user_id
```

自定义异常适合表达业务边界：

- `UserNotFoundError`
- `PermissionDeniedError`
- `ExternalServiceError`
- `InvalidToolArgumentsError`

### 8.4 异常链

保留原始异常原因：

```python
try:
    response = call_external_service()
except TimeoutError as error:
    raise ExternalServiceError("外部服务超时") from error
```

`from error` 可以保留异常链，日志中更容易定位根因。

### 8.5 重试边界

不是所有异常都应该重试：

- 网络暂时失败：通常可以重试
- 超时：可以有限次数重试
- 参数校验失败：不应该重试
- 权限不足：不应该重试
- 业务明确拒绝：通常不应该重试

重试必须设置：

- 最大次数
- 超时时间
- 退避间隔
- 可重试的异常类型

### 8.6 FastAPI 中的异常边界

业务层可以抛出业务异常，路由层或全局异常处理器将其转换为 HTTP 响应：

```python
from fastapi import HTTPException


async def get_task(task_id: int):
    task = find_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task
```

不要在底层 Service 中到处构造 HTTP 响应。这样可以让 Service 被命令行程序、定时任务和测试复用。

## 九、asyncio 基础

### 9.1 为什么需要 asyncio

Agent 服务通常会等待很多 I/O：

- 调用 LLM API
- 查询数据库
- 读取向量数据库
- 调用 MCP Server
- 访问内部 REST API

等待网络响应期间，CPU 通常没有工作可做。`asyncio` 可以让一个线程在等待某个 I/O 时执行其他协程。

```text
同步：请求 A 等待 -> A 完成 -> 请求 B 等待 -> B 完成
异步：请求 A 等待 -> 请求 B 等待 -> A 或 B 完成
```

`asyncio` 适合 I/O 密集型任务，不会自动让 CPU 密集型任务变快。

### 9.2 协程函数和 await

```python
import asyncio


async def fetch_data() -> str:
    await asyncio.sleep(1)
    return "data"


async def main() -> None:
    result = await fetch_data()
    print(result)


asyncio.run(main())
```

`async def` 定义协程函数，调用它时得到协程对象；只有 `await` 它，协程中的代码才会执行。

### 9.3 不要混淆协程和任务

协程：描述一段可以异步执行的工作。

任务：交给事件循环调度的协程。

```python
async def main() -> None:
    task = asyncio.create_task(fetch_data())
    result = await task
    print(result)
```

如果直接连续 `await`，任务仍然是顺序执行：

```python
first = await fetch_first()
second = await fetch_second()
```

### 9.4 并发执行

当两个任务互不依赖时，可以使用 `asyncio.gather`：

```python
async def load_context() -> str:
    await asyncio.sleep(0.2)
    return "context"


async def load_user_profile() -> str:
    await asyncio.sleep(0.2)
    return "profile"


async def main() -> None:
    context, profile = await asyncio.gather(
        load_context(),
        load_user_profile(),
    )
    print(context, profile)
```

多个独立的检索或工具调用经常可以采用这种模式。

### 9.5 TaskGroup

Python 3.11+ 推荐了解 `TaskGroup`：

```python
import asyncio


async def main() -> None:
    async with asyncio.TaskGroup() as group:
        context_task = group.create_task(load_context())
        profile_task = group.create_task(load_user_profile())

    print(context_task.result())
    print(profile_task.result())
```

`TaskGroup` 更强调结构化并发：任务属于一个明确的生命周期范围，发生异常时可以统一处理相关任务。

### 9.6 超时

外部调用必须设置超时：

```python
import asyncio


async def call_model() -> str:
    await asyncio.sleep(10)
    return "answer"


async def main() -> None:
    try:
        answer = await asyncio.wait_for(call_model(), timeout=3)
    except TimeoutError:
        answer = "模型调用超时"
    print(answer)
```

在较新的 Python 版本中，也可以使用上下文形式：

```python
async def main() -> None:
    try:
        async with asyncio.timeout(3):
            answer = await call_model()
    except TimeoutError:
        answer = "模型调用超时"
    print(answer)
```

超时不是错误处理的全部。生产代码还应记录调用目标、耗时、重试次数和请求标识。

### 9.7 取消任务

任务可能因为超时、用户断开连接或应用关闭而被取消：

```python
async def long_task() -> None:
    try:
        await asyncio.sleep(60)
    except asyncio.CancelledError:
        await release_resources()
        raise
```

捕获 `CancelledError` 后通常要继续 `raise`，否则上层无法正确知道任务已经被取消。

### 9.8 限制并发数量

同时发起太多请求可能触发供应商限流或耗尽连接池，可以使用信号量：

```python
import asyncio


async def fetch_one(item: str, semaphore: asyncio.Semaphore) -> str:
    async with semaphore:
        await asyncio.sleep(0.1)
        return item


async def fetch_all(items: list[str]) -> list[str]:
    semaphore = asyncio.Semaphore(5)
    tasks = [fetch_one(item, semaphore) for item in items]
    return await asyncio.gather(*tasks)
```

限制并发不是越小越好，应结合外部服务限制、连接池大小和实际延迟调整。

### 9.9 异步代码中不要阻塞事件循环

下面的代码会阻塞事件循环：

```python
import time


async def bad_function() -> None:
    time.sleep(3)
```

异步函数中应使用异步版本：

```python
import asyncio


async def good_function() -> None:
    await asyncio.sleep(3)
```

如果必须调用没有异步版本的阻塞函数，可以放到线程中：

```python
import asyncio


def blocking_read() -> str:
    with open("data.txt", encoding="utf-8") as file:
        return file.read()


async def read_file() -> str:
    return await asyncio.to_thread(blocking_read)
```

还要注意这些常见阻塞来源：

- `time.sleep`
- 同步 HTTP 客户端
- 大文件同步处理
- CPU 密集型循环
- 没有异步驱动的数据库客户端

### 9.10 asyncio 与 HTTPX

Agent 服务调用外部 API 时，通常使用 `httpx.AsyncClient`：

```python
import httpx


async def get_user(user_id: int) -> dict[str, object]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"https://example.com/users/{user_id}"
        )
        response.raise_for_status()
        return response.json()
```

在真实服务中，通常在应用生命周期中复用一个客户端，而不是每个函数都创建一个客户端。这样可以复用连接，并统一配置超时、认证和重试策略。

## 十、综合示例：异步任务服务

下面的示例展示类型注解、异常、类和 asyncio 的组合：

```python
import asyncio
from dataclasses import dataclass


class TaskNotFoundError(Exception):
    pass


@dataclass
class Task:
    task_id: int
    title: str
    completed: bool = False


class TaskService:
    def __init__(self) -> None:
        self._tasks: dict[int, Task] = {}

    async def create(self, title: str) -> Task:
        await asyncio.sleep(0)
        task_id = len(self._tasks) + 1
        task = Task(task_id=task_id, title=title)
        self._tasks[task_id] = task
        return task

    async def get(self, task_id: int) -> Task:
        await asyncio.sleep(0)
        task = self._tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        return task


async def main() -> None:
    service = TaskService()
    task = await service.create("学习 asyncio")
    print(await service.get(task.task_id))

    try:
        await service.get(999)
    except TaskNotFoundError:
        print("任务不存在")


if __name__ == "__main__":
    asyncio.run(main())
```

这个示例还没有数据库和 FastAPI，但已经体现了几个重要边界：

- `Task` 负责数据结构
- `TaskService` 负责业务操作
- `TaskNotFoundError` 负责表达业务异常
- `async def` 为未来接入数据库或外部 API 留出异步接口
- `main()` 负责启动异步程序

## 十一、常见错误

### 错误 1：忘记 await

```python
result = fetch_data()
```

此时 `result` 是协程对象，不是实际结果。正确写法：

```python
result = await fetch_data()
```

### 错误 2：把无关任务串行执行

```python
first = await fetch_first()
second = await fetch_second()
```

如果两者没有依赖关系，应考虑 `gather` 或 `TaskGroup`。

### 错误 3：在 async 函数中使用同步阻塞调用

```python
async def call_api() -> None:
    time.sleep(5)
```

这会阻塞同一事件循环中的其他请求。

### 错误 4：捕获异常后静默忽略

```python
try:
    await call_api()
except Exception:
    pass
```

至少应该记录日志、转换为明确异常，或返回有意义的降级结果。

### 错误 5：过度使用继承

业务对象之间只是“依赖关系”时，优先使用组合，不要为了复用几个方法建立复杂继承树。

### 错误 6：把类型注解当作运行时校验

```python
user_id: int = "wrong"
```

类型检查工具可能发现问题，但 Python 运行时不会仅因为注解而自动校验。来自 HTTP、LLM 或用户的输入应使用 Pydantic 校验。

## 十二、练习

### 练习一：同步任务管理

实现以下函数：

```python
def add_task(
    tasks: list[dict[str, object]],
    title: str,
) -> dict[str, object]:
    ...
```

要求：

- 标题不能为空
- 自动生成递增 ID
- 默认 `completed=False`
- 为函数添加完整类型注解

### 练习二：异常设计

为任务管理器增加：

- `TaskNotFoundError`
- `InvalidTaskTitleError`
- 查询不存在任务时抛出明确异常
- 编写测试验证异常类型和错误信息

### 练习三：异步并发

实现一个异步函数，同时查询三个模拟服务：

```python
async def query_service(name: str, delay: float) -> str:
    ...
```

要求：

- 使用 `asyncio.gather`
- 为整体操作设置超时
- 某个服务失败时能看到明确错误
- 使用信号量将最大并发数限制为 2

### 练习四：综合练习

实现一个异步“Agent 上下文收集器”：

```text
用户问题
  -> 并发读取用户信息
  -> 并发读取历史对话
  -> 并发读取知识库摘要
  -> 合并结果
  -> 返回结构化上下文
```

要求：

- 每个外部调用都有类型注解
- 每个调用有超时
- 失败时保留错误信息，不要静默忽略
- 使用 dataclass 或 Pydantic 表示结果
- 为正常、超时和部分失败场景编写测试

## 十三、阶段 0 验收标准

达到下面标准后，可以继续学习 FastAPI 和 HTTPX：

- 能独立写出带类型注解的 Python 模块
- 能区分 `list`、`tuple`、`set` 和 `dict` 的使用场景
- 能解释可变默认参数为什么危险
- 能使用函数、类和组合组织一个小型业务模块
- 能定义并捕获自定义异常
- 能使用 `with` 管理文件等资源
- 能区分协程、任务和事件循环
- 能使用 `gather` 或 `TaskGroup` 并发执行独立 I/O
- 能为异步调用设置超时和取消处理
- 能指出异步代码中的阻塞调用
- 能运行 `pyright` 并修复主要类型错误
- 能为核心逻辑编写 pytest 测试

## 十四、推荐学习顺序

```text
Python 基本类型和流程控制
  -> 函数和模块
  -> 容器与可变性
  -> 类型注解
  -> 类、组合和 dataclass
  -> 异常和资源管理
  -> 协程、await 和事件循环
  -> 并发、超时、取消和限流
  -> asyncio + HTTPX
  -> asyncio + FastAPI
```

学习时建议每个主题都写一个可以运行的最小示例，并主动制造一次失败：类型错误、缺失字段、超时、取消或外部服务异常。能解释失败原因，才算真正掌握。
