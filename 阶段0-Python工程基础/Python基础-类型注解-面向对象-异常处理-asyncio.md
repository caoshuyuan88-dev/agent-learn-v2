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

| 容器 | 是否有顺序 | 是否允许重复 | 是否可变 | 访问方式 | 典型用途 |
|---|---|---|---|---|---|
| `list` | 有，按位置排列 | 允许 | 可变 | 通过整数索引或切片 | 一组需要按顺序处理的数据 |
| `tuple` | 有，按位置排列 | 允许 | 不可变 | 通过整数索引或切片 | 不希望被修改的数据组合 |
| `set` | 不提供稳定的位置访问 | 不允许，自动去重 | 可变 | 通过成员判断，不能用索引 | 去重、集合运算、快速判断成员 |
| `dict` | 保持插入顺序 | 键不能重复，重复键会覆盖旧值 | 可变 | 通过键访问值 | 表示字段和值、快速查找 |

### 3.3.1 list：有顺序、可修改、允许重复

列表适合表示一组需要按顺序处理的数据。它支持索引、切片、追加、删除和排序：

```python
tasks = ["学习 Python", "学习 FastAPI", "学习 Python"]

first_task = tasks[0]
last_tasks = tasks[-2:]
tasks.append("学习 HTTPX")
tasks.remove("学习 FastAPI")
```

列表的特点：

- 元素有固定位置，可以通过 `tasks[0]` 访问第一个元素。
- 可以包含重复值，适合保留原始记录或事件序列。
- 可以修改、增加和删除元素。
- `append()` 末尾追加通常是 $O(1)$；按索引读取通常是 $O(1)$。
- 在列表中查找某个值通常是 $O(n)$；中间位置插入或删除也通常是 $O(n)$，因为后续元素需要移动。

### 3.3.2 tuple：有顺序、不可修改

元组和列表一样支持位置访问和重复值，但创建后不能修改：

```python
coordinates = (31.2, 121.5)
longitude = coordinates[0]
latitude = coordinates[1]
```

元组的特点：

- 有顺序，可以通过索引访问。
- 不能追加、删除或替换元素。
- 适合表达固定结构，例如坐标、函数返回的多个固定结果。
- 不可变本身不代表内部对象一定不可变；如果元组中放了列表，该列表仍然可以修改。
- 如果元组中的所有元素都可哈希，元组可以作为字典的键或集合元素。

```python
result = ("success", 200)
status, code = result
```

当数据代表“固定的几个位置”时使用元组；当数据需要持续增删时使用列表。

### 3.3.3 set：无重复、适合成员判断

集合主要用于去重和集合运算，不提供按位置访问：

```python
tags = {"python", "agent", "python"}
print(tags)  # "python" 只保留一份

if "agent" in tags:
    print("这是 Agent 相关标签")
```

集合的特点：

- 不允许重复元素，添加重复值不会产生第二份数据。
- 不能使用 `tags[0]`，因为集合不是按位置访问的容器。
- 可以添加和删除元素，但集合中的元素必须是可哈希对象，例如字符串、整数和不可变元组。
- 成员判断、添加和删除平均为 $O(1)$，适合频繁判断某个值是否存在。
- 不应依赖集合的遍历顺序。如果业务需要稳定顺序，应使用列表。

常用集合运算：

```python
backend_tags = {"python", "java", "sql"}
agent_tags = {"python", "agent", "rag"}

common_tags = backend_tags & agent_tags       # 交集
all_tags = backend_tags | agent_tags          # 并集
only_backend = backend_tags - agent_tags     # 差集
```

### 3.3.4 dict：键值映射

字典通过键查找值，适合表示结构化字段或建立索引：

```python
user = {
    "id": 1,
    "name": "Alice",
    "roles": ["developer"],
}

user_name = user["name"]
user["active"] = True
```

字典的特点：

- 每个键只能对应一个值；重复键会覆盖之前的值。
- Python 3.7+ 保持键的插入顺序，但字典的主要用途仍是按键查找，不是按位置访问。
- 键必须是可哈希对象，常见的是字符串、整数和不可变元组；值可以是任意对象。
- 通过键查找、插入和删除平均为 $O(1)$。
- `key in user` 判断的是键是否存在，不是值是否存在。

```python
if "name" in user:
    print(user["name"])

for key, value in user.items():
    print(key, value)
```

### 3.3.5 如何选择

可以用下面的问题快速选择容器：

1. 需要通过名称查找字段吗？使用 `dict`。
2. 需要去重或频繁判断成员是否存在吗？使用 `set`。
3. 数据按顺序排列，并且后续需要修改吗？使用 `list`。
4. 数据按顺序排列，但结构固定且不希望修改吗？使用 `tuple`。

一个常见的组合是：

```python
user = {
    "id": 1,
    "roles": {"developer", "reviewer"},
    "recent_tasks": ["学习 Python", "学习 FastAPI"],
}
```

这里用字典表示用户字段，用集合表示不重复的角色，用列表表示有顺序的任务记录。

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

# enumerate 同时返回元素的索引和值；start=1 表示索引从 1 开始
for index, name in enumerate(names, start=1):
    print(index, name)
```

如果 `names = ["Alice", "Bob"]`，上面的循环会依次得到：

```text
(1, "Alice")
(2, "Bob")
```

因此，`index` 是当前元素的编号，`name` 是当前元素本身。`enumerate` 比手动定义并递增计数器更简洁，也不容易因为忘记递增计数器而出错。`start` 默认为 `0`，如果希望编号从其他数字开始，可以传入对应的值，例如 `start=1`。

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

### 4.4.1 作用域和 LEGB 规则

作用域是变量名可以被查找的范围。Python 查找一个变量名时，通常按照下面的顺序进行：

```text
L - Local：当前函数内部的局部作用域
E - Enclosing：外层函数的作用域
G - Global：当前模块文件的全局作用域
B - Built-in：Python 内置名称，例如 len、print
```

例如：

```python
message = "模块级变量"


def show_message() -> None:
    message = "函数内变量"
    print(message)


show_message()  # 输出：函数内变量
print(message)  # 输出：模块级变量
```

函数内部定义的 `message` 会遮蔽同名的全局变量，但不会修改全局变量。局部变量和全局变量只是同名，并不是同一个变量。

### 4.4.2 读取和修改全局变量

在函数中读取全局变量通常不需要 `global`：

```python
default_timeout = 10


def get_timeout() -> int:
    return default_timeout
```

但是，如果要在函数中给全局变量重新赋值，就必须使用 `global`：

```python
request_count = 0


def record_request() -> None:
    global request_count
    request_count += 1
```

`global request_count` 的含义是：当前函数中的 `request_count` 指向模块级变量，而不是创建一个新的局部变量。

如果省略 `global`：

```python
request_count = 0


def record_request() -> None:
    request_count += 1
```

Python 会把函数中的 `request_count` 判断为局部变量。但在执行加法前它还没有局部初始值，因此会抛出 `UnboundLocalError`。

### 4.4.3 为什么不推荐滥用 global

`global` 本身不是语法错误，但会引入共享可变状态，常见问题包括：

- 函数依赖隐藏在模块变量中，调用者无法从参数看出依赖。
- 多个函数都能修改同一个值，执行顺序会影响结果。
- 测试之间可能互相污染，需要额外重置全局状态。
- 异步服务中多个请求共享状态，容易产生竞态问题。
- 多进程部署时，不同进程拥有不同的全局变量，状态不会自动同步。
- Agent 服务扩容后，使用全局变量保存会话、计数器或任务状态通常是不可靠的。

例如，不推荐用全局变量保存用户会话：

```python
current_user_id: int | None = None
```

在 FastAPI 或 Agent 服务中，更好的方案通常是：

- 通过函数参数显式传递状态。
- 使用类封装相关状态，并通过依赖注入传入。
- 使用数据库或 Redis 保存需要跨请求、跨进程共享的数据。
- 使用 `contextvars` 保存请求范围内的上下文，例如请求标识。

```python
class RequestCounter:
    def __init__(self) -> None:
        self._count = 0

    def record(self) -> int:
        self._count += 1
        return self._count


counter = RequestCounter()
```

这个例子仍然有一个对象实例，但依赖是显式的，也更容易在测试中创建新的 `RequestCounter`。

### 4.4.4 闭包

闭包是一个函数记住并使用其外层函数变量的现象。即使外层函数已经执行结束，内部函数仍然可以访问这些变量：

```python
def make_prefixer(prefix: str):
    def add_prefix(text: str) -> str:
        return f"{prefix}: {text}"

    return add_prefix


error_prefixer = make_prefixer("错误")
print(error_prefixer("请求失败"))  # 输出：错误: 请求失败
```

这里 `add_prefix` 是内部函数，它捕获了外层函数的 `prefix`。`error_prefixer` 保存的不是普通字符串，而是一个带有记忆能力的函数。

闭包适合：

- 创建带固定配置的函数
- 简单的装饰器
- 封装少量私有状态

如果闭包中需要修改外层变量，需要使用 `nonlocal`：

```python
def make_counter() -> callable:
    count = 0

    def next_count() -> int:
        nonlocal count
        count += 1
        return count

    return next_count


next_count = make_counter()
print(next_count())  # 1
print(next_count())  # 2
```

`nonlocal` 表示使用最近的外层函数变量；它和 `global` 的区别是：

| 关键字 | 修改的变量位置 | 常见用途 |
|---|---|---|
| `global` | 当前模块的全局作用域 | 访问或修改模块级变量 |
| `nonlocal` | 外层函数的作用域 | 在闭包中修改外层函数变量 |

闭包可以解决小范围状态封装问题，但对于复杂业务状态，类、数据对象、数据库或 Redis 通常更清晰。

### 4.4.5 作用域中的常见误区

1. 在函数内给外部同名变量赋值，不会自动修改外部变量。
2. 只读取全局变量不需要 `global`，重新赋值才需要。
3. `global` 只影响当前模块，不会让变量自动跨文件、跨进程共享。
4. `nonlocal` 只能用于嵌套函数，不能用于模块级变量。
5. 列表或字典即使没有 `global`，也可能通过方法修改全局对象的内容；因此可变对象仍要谨慎共享。

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

#### 6.3.1 类型别名是什么

类型别名就是给一个已有类型起一个更有业务含义的名字：

```python
from typing import TypeAlias


UserId: TypeAlias = int


def find_user(user_id: UserId) -> str | None:
    print(user_id)
    return None
```

这里的 `UserId` 本质上仍然是 `int`，它不会创建新的运行时类型，也不会自动检查传入值。它的主要作用是让代码更容易阅读，并让类型检查工具理解业务含义。

```python
TaskId: TypeAlias = int
OrderId: TypeAlias = int
```

虽然 `TaskId` 和 `OrderId` 在业务上代表不同的东西，但上面的写法不会阻止你把一个整数 ID 传给另一个函数。如果需要真正区分它们，应使用包装类或 `NewType`：

```python
from typing import NewType


UserId = NewType("UserId", int)


def find_user(user_id: UserId) -> None:
    print(user_id)
```

阶段 0 先掌握普通类型别名即可，`NewType` 了解概念就够了。

#### 6.3.2 Literal 是什么

`Literal` 可以理解为“允许值的白名单”。普通的 `str` 表示可以是任意字符串：

```python
def set_status(status: str) -> None:
    print(status)


set_status("todo")
set_status("这是一个拼写错误")  # 类型检查工具也无法判断它是不是合法状态
```

如果状态只有几个固定值，就可以用 `Literal` 明确告诉 Pyright 或 mypy：

```python
from typing import Literal


TaskStatus = Literal["todo", "doing", "done"]


def update_status(status: TaskStatus) -> None:
    print(status)


update_status("todo")  # 正确
update_status("done")  # 正确
update_status("finished")  # 类型检查错误：不在允许值列表中
```

因此：

```text
str                         -> 任意字符串
Literal["todo", "done"]    -> 只能是这两个具体字符串
```

`Literal` 不只是说明“这是字符串”，而是进一步说明“这个字符串只能取哪些具体值”。它也可以用于整数、布尔值等：

```python
RetryCount = Literal[0, 1, 2, 3]
Enabled = Literal[True, False]
```

#### 6.3.3 Literal 和运行时校验的区别

`Literal` 主要服务于静态类型检查。Python 直接运行时不会因为传入了错误字符串就自动抛异常：

```python
update_status("finished")  # 直接运行 Python 时仍可能执行
```

因此需要区分两个场景：

| 场景 | 推荐方式 |
|---|---|
| 编写代码时限制函数调用者的可选值 | `Literal` |
| HTTP、LLM 或用户输入的运行时校验 | Pydantic `Literal` 字段或 `Enum` |
| 需要成员、方法或更复杂行为的状态对象 | `Enum` |

在 Pydantic 模型中，`Literal` 会参与运行时校验：

```python
from typing import Literal

from pydantic import BaseModel


class TaskUpdate(BaseModel):
    status: Literal["todo", "doing", "done"]


TaskUpdate(status="doing")  # 校验通过
TaskUpdate(status="finished")  # ValidationError
```

这正适合 FastAPI 请求和 Agent 工具参数：模型输出的状态必须属于预先定义的集合。

#### 6.3.4 Literal 和 Enum 怎么选择

简单选项可以使用 `Literal`：

```python
SortOrder = Literal["asc", "desc"]
```

当状态需要复用、显示名称、方法或更多业务行为时，可以使用 `Enum`：

```python
from enum import Enum


class TaskStatus(str, Enum):
    TODO = "todo"
    DOING = "doing"
    DONE = "done"


def update_status(status: TaskStatus) -> None:
    if status is TaskStatus.DONE:
        print("任务已完成")
```

可以这样记忆：

```text
Literal：我只允许这几个值，简单直接
Enum：我需要一个有名字、可复用、可以承载行为的状态类型
```

在 Agent 工具参数中，查询方向、任务状态、输出格式等简单选项适合使用 `Literal`；如果状态在多个模块中反复出现，或者需要附加行为，使用 `Enum` 更合适。

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

`Protocol` 用于描述“只要具备这些方法，就可以被使用”的接口。它体现的是鸭子类型：如果一个对象像鸭子一样会走、会叫，那么代码可以按鸭子的方式使用它，而不要求这个对象必须继承某个特定的父类。

#### 6.5.1 最基本的用法

```python
from typing import Protocol


class MessageSender(Protocol):
    def send(self, message: str) -> None:
        ...


def notify(sender: MessageSender, message: str) -> None:
    sender.send(message)
```

下面的类没有继承 `MessageSender`，但它有一个符合要求的 `send` 方法，因此可以传给 `notify`：

```python
class EmailSender:
    def send(self, message: str) -> None:
        print(f"发送邮件: {message}")


class LogSender:
    def send(self, message: str) -> None:
        print(f"写入日志: {message}")


notify(EmailSender(), "任务完成")
notify(LogSender(), "任务完成")
```

这里的关键不是 `EmailSender` 和 `LogSender` 是否继承了 `MessageSender`，而是它们都具备 `send(message: str) -> None` 这个能力。Pyright 或 mypy 会根据方法签名判断它们是否符合协议。

可以把 `Protocol` 理解成一份“使用方需要什么能力”的说明：

```text
notify 不关心你具体是什么类
notify 只要求你有一个 send 方法
```

#### 6.5.2 Protocol 与继承的区别

传统继承通常要求实现类明确继承父类：

```python
from abc import ABC, abstractmethod


class MessageSenderBase(ABC):
    @abstractmethod
    def send(self, message: str) -> None:
        raise NotImplementedError


class EmailSender(MessageSenderBase):
    def send(self, message: str) -> None:
        print(message)
```

`Protocol` 和抽象基类的主要区别：

| 对比项 | `Protocol` | 抽象基类 `ABC` |
|---|---|---|
| 是否必须显式继承 | 不需要 | 通常需要 |
| 判断方式 | 看对象是否具备所需方法和属性 | 看类的继承关系和抽象方法实现 |
| 主要作用 | 静态类型检查和解耦 | 建立明确的类层次和运行时约束 |
| 适合场景 | 外部客户端、测试替身、可替换依赖 | 需要统一生命周期或强制继承关系 |

如果你只需要表达“调用方需要哪些方法”，优先考虑 `Protocol`。如果你需要共享父类实现、定义类变量，或者必须让实现类遵守明确的继承层次，可以考虑抽象基类。

#### 6.5.3 Agent 项目中的异步 Protocol

Agent 服务经常需要替换不同的模型客户端。可以定义一个异步协议：

```python
from typing import Protocol


class LLMClient(Protocol):
    async def complete(self, prompt: str) -> str:
        ...


class CloudLLMClient:
    async def complete(self, prompt: str) -> str:
        return f"云模型响应: {prompt}"


class FakeLLMClient:
    async def complete(self, prompt: str) -> str:
        return "测试响应"


class AgentService:
    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    async def answer(self, question: str) -> str:
        return await self.llm_client.complete(question)
```

`AgentService` 不依赖某一家模型供应商，只依赖 `LLMClient` 规定的能力。生产环境可以传入 `CloudLLMClient`，测试中可以传入 `FakeLLMClient`：

```python
service = AgentService(FakeLLMClient())
```

这就是依赖倒置的一个简单体现：业务服务依赖抽象能力，而不是依赖具体客户端类。

#### 6.5.4 Protocol 可以描述属性

协议不只能描述方法，也可以描述必须存在的属性：

```python
from typing import Protocol


class HasRequestId(Protocol):
    request_id: str


def log_request(request: HasRequestId) -> None:
    print(request.request_id)
```

只要传入的对象有一个 `request_id: str` 属性，类型检查工具就可以认为它满足这个协议。

#### 6.5.5 `runtime_checkable` 的限制

默认情况下，`Protocol` 主要用于静态类型检查，不能直接这样进行运行时判断：

```python
# 默认不应该用 isinstance(sender, MessageSender) 做判断
```

如果确实需要进行简单的运行时成员检查，可以使用 `runtime_checkable`：

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class MessageSender(Protocol):
    def send(self, message: str) -> None:
        ...
```

之后可以检查对象是否具有名为 `send` 的属性：

```python
is_sender = isinstance(EmailSender(), MessageSender)
```

需要注意，`runtime_checkable` 的运行时检查主要检查成员是否存在，不会完整检查参数类型和返回值类型。因此它不能代替 Pydantic 校验，也不能代替 Pyright 或 mypy。

#### 6.5.6 Protocol、TypedDict 和 Pydantic 的区别

这三个工具解决的问题不同：

| 工具 | 主要描述对象 | 是否自动进行运行时数据校验 |
|---|---|---|
| `Protocol` | 一个对象需要具备哪些方法或属性 | 否 |
| `TypedDict` | 一个字典有哪些键及其类型 | 否 |
| Pydantic `BaseModel` | 外部数据的结构和校验规则 | 是 |

可以这样选择：

```text
外部 JSON、HTTP 请求、LLM 输出
  -> Pydantic BaseModel

内部字典结构的类型提示
  -> TypedDict

外部客户端需要提供哪些方法
  -> Protocol
```

这适合为外部服务定义轻量抽象，测试时可以传入假的实现。

### 6.6 类型检查

#### 6.6.1 类型检查是什么

Python 是动态类型语言。下面的代码可以启动，但可能在运行到某一行时才失败：

```python
def add_tax(price: float) -> float:
    return price * 1.13


result = add_tax("100")
```

静态类型检查工具会在运行程序之前分析代码，并指出 `add_tax` 需要 `float`，却传入了字符串。它主要帮助发现：

- 函数参数类型传错
- 返回值类型不符合声明
- 访问了可能为 `None` 的对象
- 字典或对象使用了不存在的字段
- 列表中混入了不符合声明的元素
- 异步函数忘记 `await`
- 实现类不符合 `Protocol` 要求

类型检查不是运行时校验：

```text
Pyright / mypy：检查源代码中的类型关系
Pydantic：检查程序运行时收到的数据
pytest：验证程序行为是否符合预期
```

三者解决的问题不同，不能互相完全替代。

#### 6.6.2 Pyright 和 mypy 怎么选

Pyright 和 mypy 都是 Python 静态类型检查工具。你使用 VS Code，阶段 0 建议先选择：

```text
Pyright + Pylance
```

原因是 Pyright 与 VS Code 的类型提示、跳转和错误显示配合紧密。进入团队项目后，如果项目已经统一使用 mypy，应遵循项目现有配置，不要在同一个项目中无理由维护两套规则。

简单对比：

| 工具 | 适合场景 | 使用方式 |
|---|---|---|
| Pyright | VS Code 开发、快速反馈、Pylance 集成 | 编辑器提示或命令行 |
| mypy | 已有 mypy 配置的团队项目、CI 检查 | 命令行和 CI |

#### 6.6.3 安装和运行 Pyright

可以通过 npm 安装命令行版本：

```bash
npm install --global pyright
```

也可以直接使用 VS Code 中的 Pylance 获得编辑器内的类型诊断。项目检查命令：

```bash
pyright
```

检查指定文件或目录：

```bash
pyright app/main.py
pyright app tests
```

检查结果通常包含文件、行列位置、错误级别和原因。先修复真正的错误，再处理信息级提示，不要一开始就用注释把所有问题隐藏掉。

#### 6.6.4 类型检查级别和配置

Pyright 可以通过 `pyrightconfig.json` 配置检查范围和严格程度：

```json
{
  "include": ["app", "tests"],
  "exclude": [".venv", "build"],
  "typeCheckingMode": "basic",
  "reportMissingImports": true
}
```

常见级别：

```text
off      -> 基本不检查
basic    -> 适合刚开始学习
standard -> 更严格
strict   -> 对大型项目和关键模块要求更高
```

阶段 0 可以从 `basic` 开始，熟悉错误后逐步提高到 `standard`。如果整个项目还没有类型注解，不建议直接开启 `strict`，否则初期会出现大量噪音。

也可以用 `pyproject.toml` 配置：

```toml
[tool.pyright]
include = ["app", "tests"]
exclude = [".venv", "build"]
typeCheckingMode = "basic"
```

#### 6.6.5 常见类型错误

参数类型不匹配：

```python
def greet(name: str) -> str:
    return f"Hello, {name}"


greet(123)  # 错误：需要 str，却传入 int
```

修复方式是修正调用方，或者修正函数契约。如果函数确实要支持多种类型，应明确声明：

```python
def greet(name: str | int) -> str:
    return f"Hello, {name}"
```

可能为 `None`：

```python
def find_name(user_id: int) -> str | None:
    return None


name = find_name(1)
if name is not None:
    print(name.upper())
```

返回值不符合声明：

```python
def get_status() -> int:
    return "ok"  # 错误：声明返回 int，却返回 str
```

容器元素类型不一致：

```python
task_ids: list[int] = [1, 2]
task_ids.append("3")  # 错误：list[int] 不能添加 str
```

如果外部输入是字符串，应先明确转换并校验。来自 HTTP 或 LLM 的输入则应使用 Pydantic 模型处理运行时校验。

#### 6.6.6 类型收窄

类型检查工具可以根据条件判断缩小变量类型：

```python
def display_name(name: str | None) -> str:
    if name is None:
        return "匿名用户"
    return name.upper()
```

进入 `if` 之后，工具知道 `name` 是 `None`；进入后面的分支时，工具知道 `name` 是 `str`。常见的类型收窄方式有：

- `is None` 或 `is not None`
- `isinstance(value, str)`
- `in` 判断有限字符串选项
- `match` 或 `if` 判断 `Literal` 和 `Enum`

```python
def format_value(value: str | int) -> str:
    if isinstance(value, str):
        return value.upper()
    return str(value)
```

#### 6.6.7 Any 为什么要谨慎使用

`Any` 相当于告诉类型检查工具：“这个值可以是任何类型，请不要检查它。”

```python
from typing import Any


def process(data: Any) -> str:
    return data.not_exist().upper()
```

上面的代码可能通过类型检查，但运行时仍然会失败。`Any` 可以用于暂时迁移旧代码或类型信息缺失的第三方库边界，但不应为了快速消除错误而到处使用。

优先考虑 `object`、联合类型、`TypedDict`、`Protocol` 或 Pydantic 模型。特别是不要用 `Any` 代替 `str | None` 或外部输入模型。

#### 6.6.8 异步代码中的类型检查

异步函数的返回类型应写成函数实际返回的结果类型，而不是协程类型：

```python
async def fetch_answer() -> str:
    return "answer"


async def main() -> None:
    answer = await fetch_answer()
    print(answer)
```

如果忘记 `await`，`answer` 是协程对象，不是 `str`：

```python
async def main() -> None:
    answer = fetch_answer()
    print(answer.upper())
```

Pyright 通常会提示这里的类型不匹配。异步客户端、Protocol 和依赖注入组合使用时，类型检查尤其有价值。

#### 6.6.9 阶段 0 的实践方式

建议在项目根目录执行：

```bash
pyright
pytest
```

每次新增一个模块时：

1. 先给公共函数和类方法添加参数、返回值类型。
2. 运行 `pyright`，修复真实类型错误。
3. 用 Pydantic 校验外部输入。
4. 用 pytest 验证正常场景和异常场景。
5. 只有确认类型信息不准确时，才使用 `# pyright: ignore[错误编号]`，并留下原因。

不要把类型检查当成一次性任务。它更像编译器反馈：在代码变大之前，尽早发现接口之间的不一致。

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

这三种方法的核心区别在于：它们绑定的对象不同。

| 方法类型 | 第一个参数 | 能否访问实例属性 | 能否访问类属性 | 是否需要创建实例 | 典型用途 |
|---|---|---|---|---|---|
| 实例方法 | `self` | 可以 | 可以 | 通常需要 | 操作某个对象的具体状态 |
| 类方法 | `cls` | 不能直接访问某个实例 | 可以 | 不需要 | 替代构造器、操作类级别配置 |
| 静态方法 | 没有隐式参数 | 不能直接访问 | 不能直接访问 | 不需要 | 与类主题相关的独立工具函数 |

### 7.3.1 实例方法：操作具体对象

实例方法的第一个参数通常命名为 `self`，表示当前对象。调用时 Python 会自动传入它：

```python
user = User("Alice")
user.display_name()
```

这大致等价于：

```python
User.display_name(user)
```

因此，实例方法可以读取和修改 `self` 上的属性：

```python
class Task:
    def __init__(self, title: str) -> None:
        self.title = title
        self.completed = False

    def complete(self) -> None:
        self.completed = True

    def summary(self) -> str:
        state = "已完成" if self.completed else "未完成"
        return f"{self.title}: {state}"
```

```python
task = Task("学习 FastAPI")
task.complete()
print(task.summary())
```

如果一个方法需要知道“是哪一个用户、任务或客户端正在执行操作”，它通常应该是实例方法。

### 7.3.2 类方法：操作类或创建实例

类方法使用 `@classmethod` 装饰器，第一个参数通常命名为 `cls`，表示当前类：

```python
class User:
    def __init__(self, name: str) -> None:
        self.name = name

    @classmethod
    def anonymous(cls) -> "User":
        return cls("anonymous")


user = User.anonymous()
```

这里不需要先创建 `User` 实例，因为类方法绑定的是类本身。`cls("anonymous")` 会创建当前类的对象。

类方法最常见的用途是提供替代构造方式：

```python
from datetime import datetime


class Task:
    def __init__(self, title: str, created_at: datetime) -> None:
        self.title = title
        self.created_at = created_at

    @classmethod
    def from_title(cls, title: str) -> "Task":
        return cls(title=title, created_at=datetime.now())


task = Task.from_title("学习 Python")
```

使用 `cls` 而不是直接写类名，可以让子类继承后仍然创建子类对应的对象。

### 7.3.3 静态方法：放在类里的独立函数

静态方法使用 `@staticmethod`，没有自动传入的 `self` 或 `cls`：

```python
class User:
    @staticmethod
    def normalize_name(name: str) -> str:
        return name.strip().lower()


normalized = User.normalize_name(" Alice ")
```

它不能直接访问 `self.name` 或类属性，只能使用传入的参数和函数内部变量。如果函数与这个类没有明显关系，直接定义成模块级函数通常更容易复用和测试。

### 7.3.4 三种方法放在一起

```python
class AgentConfig:
    default_model = "default-model"

    def __init__(self, model: str, temperature: float) -> None:
        self.model = model
        self.temperature = temperature

    def describe(self) -> str:
        # 实例方法：读取当前配置对象的属性
        return f"{self.model}, temperature={self.temperature}"

    @classmethod
    def default(cls) -> "AgentConfig":
        # 类方法：通过类属性创建一个配置对象
        return cls(model=cls.default_model, temperature=0.2)

    @staticmethod
    def valid_temperature(temperature: float) -> bool:
        # 静态方法：只依赖传入参数
        return 0 <= temperature <= 2
```

调用方式：

```python
config = AgentConfig.default()              # 类方法
print(config.describe())                    # 实例方法
print(AgentConfig.valid_temperature(0.7))   # 静态方法
```

### 7.3.5 选型规则

1. 方法需要访问当前对象的属性吗？使用实例方法。
2. 方法需要创建当前类的对象，或访问类级别配置吗？使用类方法。
3. 方法只依赖传入参数，且逻辑明显属于这个类吗？使用静态方法。
4. 方法与类没有明显关系吗？直接定义成模块级函数。

在 Agent 项目中：

- `AgentService.answer()` 通常是实例方法，因为它要使用模型客户端、配置或会话状态。
- `LLMClient.from_settings()` 可以是类方法，用配置创建客户端。
- `PromptUtils.normalize()` 可以是静态方法；如果没有类关联，也可以是普通函数。

常见使用场景：

- 实例方法：需要访问对象状态
- 类方法：提供替代构造方式
- 静态方法：逻辑属于类的概念，但不依赖实例或类状态

### 7.3.6 类中下划线命名的方法

类中的函数通常称为方法。方法名称中的下划线有特殊约定，但几种写法的含义不同：

| 写法 | 常见含义 | 是否真正禁止外部访问 |
|---|---|---|
| `_method` | 内部方法，表示不建议外部直接调用 | 否，只是约定 |
| `__method` | 双下划线开头，触发名称改写，用于减少子类命名冲突 | 不是严格私有 |
| `__method__` | Python 特殊方法，也叫 dunder 方法 | 不应随意自定义 |
| `method_` | 末尾加下划线，避免与关键字或已有名称冲突 | 否 |

#### 单下划线 `_method`：内部使用约定

单下划线开头的方法表示“这是类的内部实现，不建议外部直接调用”：

```python
class TaskService:
    def create_task(self, title: str) -> None:
        clean_title = self._normalize_title(title)
        print(f"创建任务: {clean_title}")

    def _normalize_title(self, title: str) -> str:
        return title.strip()
```

`_normalize_title` 仍然可以从外部调用：

```python
service = TaskService()
service._normalize_title(" 学习 Python ")
```

Python 没有像 Java `private` 那样由语言强制执行的严格私有方法。单下划线主要是给开发者、IDE 和代码审查者的信号：这个方法属于内部实现，未来可能改变，不应作为稳定公共 API 使用。

#### 双下划线开头 `__method`：名称改写

双下划线开头、但不以双下划线结尾的方法会触发名称改写，也叫名称修饰（name mangling）：

```python
class Account:
    def __reset_token(self) -> None:
        print("重置令牌")

    def reset(self) -> None:
        self.__reset_token()
```

Python 会把 `__reset_token` 在类内部改写成类似 `_Account__reset_token` 的名称：

```python
account = Account()
account.reset()
account._Account__reset_token()  # 技术上可以访问，但不应该这样调用
```

它的主要用途不是实现绝对私有，而是避免子类中同名方法意外覆盖父类内部方法：

```python
class BaseAgent:
    def __build_context(self) -> str:
        return "基础上下文"

    def run(self) -> str:
        return self.__build_context()


class CustomAgent(BaseAgent):
    def __build_context(self) -> str:
        return "自定义上下文"


agent = CustomAgent()
print(agent.run())  # 仍然使用 BaseAgent 的内部方法
```

因为父类和子类的方法最终会被改写成不同名称，所以子类的 `__build_context` 不会意外覆盖父类的方法。这个机制也意味着，双下划线方法不适合用来表达“希望子类重写”的扩展点；这种场景应使用单下划线方法或普通方法。

#### 前后双下划线 `__method__`：特殊方法

前后都有双下划线的方法称为特殊方法，通常也叫 dunder 方法（double underscore 的简称）。它们由 Python 在特定语法或内置函数中自动调用：

```python
class Task:
    def __init__(self, title: str) -> None:
        self.title = title

    def __str__(self) -> str:
        return f"Task(title={self.title!r})"


task = Task("学习 asyncio")
print(task)  # print 会自动调用 task.__str__()
```

常见特殊方法：

| 方法 | 触发方式 | 作用 |
|---|---|---|
| `__init__` | `Class(...)` 创建对象后 | 初始化实例属性 |
| `__str__` | `str(obj)` 或 `print(obj)` | 提供面向用户的字符串表示 |
| `__repr__` | `repr(obj)` | 提供面向开发者的详细表示 |
| `__len__` | `len(obj)` | 定义对象长度 |
| `__eq__` | `obj1 == obj2` | 定义相等比较 |
| `__enter__` / `__exit__` | `with obj` | 支持上下文管理器 |
| `__aenter__` / `__aexit__` | `async with obj` | 支持异步上下文管理器 |
| `__call__` | `obj(...)` | 让对象可以像函数一样调用 |

特殊方法一般由 Python 的语法或内置函数触发，不建议直接手动调用，也不要随意创造类似 `__my_method__` 的名称，因为这可能与 Python 或第三方库未来的约定冲突。

#### 末尾单下划线 `method_`

如果想使用的名称与 Python 关键字冲突，可以在末尾加一个下划线：

```python
class Request:
    def __init__(self, class_: str, from_: str) -> None:
        self.class_ = class_
        self.from_ = from_
```

这里使用 `class_` 和 `from_`，是为了避开 `class` 和 `from` 关键字。末尾下划线没有私有含义。

可以这样记忆：

```text
_name       -> 内部实现约定
__name      -> 名称改写，减少继承冲突
__name__    -> Python 特殊方法
name_       -> 避免关键字或命名冲突
```

在 Agent 项目中，普通业务方法通常使用清晰的公开名称；内部辅助逻辑使用 `_`；需要初始化、字符串表示或异步资源管理时，才实现对应的特殊方法。

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

### 9.1 什么是 asyncio：单线程事件循环 + 协作式调度

#### 9.1.1 先看一个日常类比：餐厅点餐

想象一家餐厅只有一位服务员（一个线程）：

- **同步做法**：服务员站在 A 桌旁，等 A 想好点什么、等厨房做好、等 A 吃完结账，再去服务 B 桌。B 桌等得越久，服务员越闲——因为所有时间都花在「等」上。
- **异步做法**：服务员记下 A 的订单后立刻去服务 B、C 桌；厨房做好 A 的菜后，服务员再把菜送过去。一个人同时服务很多桌，靠的不是分身，而是**「等」的时候去做别的事**。

程序世界里的「等」就是 I/O：发起网络请求后，CPU 几乎无事可做，只是在等网卡返回数据。asyncio 的核心思想就是上面服务员的做法——**让「等」不再白白占用线程**。

#### 9.1.2 Agent 服务里到处是 I/O 等待

Agent 服务通常会等待很多 I/O：

- 调用 LLM API
- 查询数据库
- 读取向量数据库
- 调用 MCP Server
- 访问内部 REST API

同步代码的时序是「一个等完再等下一个」，而 asyncio 可以让这些等待重叠：

```text
同步：请求 A 等待 -> A 完成 -> 请求 B 等待 -> B 完成
异步：请求 A 等待 -> 请求 B 等待 -> A 或 B 完成
```

同一段时间里，异步版本完成了两件事（A 和 B 的等待重叠了）。这就是 Agent 服务高并发的来源：**不是一个请求变快，而是单位时间内能同时处理更多请求**。

#### 9.1.3 三个关键词：事件循环、协程、await

asyncio 的全部机制可以压缩成三个词：

| 概念 | 是什么 | 类比 |
| --- | --- | --- |
| **事件循环（event loop）** | 单线程的调度器，循环检查「谁准备好了」，准备好了就继续执行它 | 餐厅里安排送菜顺序的服务员 |
| **协程（coroutine）** | 可以暂停、稍后从暂停处继续的函数（`async def` 定义） | 一张「做某件事」的订单 |
| **await** | 协程里的暂停点：执行到这里就暂停，把控制权交回事件循环 | 在订单上写「等厨房出菜，好了叫我」 |

后面几节会逐个展开。先记住最核心的一句话：

> **asyncio 是用一个线程（事件循环），通过协作式调度，让成千上万个「等待中的 I/O」并发推进。**

#### 9.1.4 Java 类比：线程池 vs 事件循环

你熟悉的 Java 并发模型有两种：

1. **多线程 + 阻塞 I/O**（`ThreadPoolExecutor` + `RestTemplate`）：每个请求占一个线程，线程阻塞在 I/O 上。线程多了，上下文切换开销大；线程少了，并发上不去。
2. **事件驱动**（Netty 的 event loop、Spring WebFlux / Reactor）：少量线程驱动海量连接，I/O 不阻塞线程。

**asyncio 就是 Python 版的事件驱动模型**——和 Netty/WebFlux 是同一个思想，只是语法不同：

| 维度 | Java 线程（阻塞 I/O） | Python asyncio |
| --- | --- | --- |
| 并发单位 | 线程 | 协程 |
| 调度者 | 操作系统（抢占式） | 事件循环（协作式） |
| 切换成本 | 高（内核态上下文切换） | 极低（用户态保存/恢复局部变量） |
| 谁让出 CPU | 线程被系统打断 | 协程自己 `await` 让出 |
| 适合场景 | CPU 密集 / 阻塞式库 | I/O 密集 |

Java 里 `CompletableFuture` 可以看作「事件驱动思想在 Java 里的妥协」；而 Python 的 `async/await` 是把这件事做成了语言级语法，写起来更像同步代码。

#### 9.1.5 协作式 vs 抢占式：为什么协程不能「抢」

线程由操作系统**抢占式**调度——线程随时可能被切走，不需要自己同意。协程是**协作式**调度——只有协程自己执行到 `await` 才会让出控制权，事件循环才有机会切换别人。

这个区别带来一个重要的推论（9.9 节会重点讲）：

> **如果某个协程内部写了阻塞调用（如 `time.sleep()`、同步 requests）且没有 `await` 让出，整个事件循环都会卡住**——因为事件循环是单线程的，它正卡在这段阻塞代码里，其他所有协程都得不到执行。

#### 9.1.6 适用边界

- ✅ **适合**：I/O 密集型——网络请求、数据库、文件读写、微服务调用。Agent 服务几乎全是这种。
- ❌ **不适合**：CPU 密集型——大量计算、图像处理、加密。asyncio 不会让 CPU 密集任务变快（单线程反而更慢），这种任务应该用多进程或线程池（9.9.4 节）。

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

#### 9.2.1 运行过程逐步拆解

`asyncio.run(main())` 做了什么：

1. 创建一个事件循环，把 `main()` 这个协程交给它执行；
2. 执行到 `result = await fetch_data()` 时：**调用 `fetch_data()` 并不会执行函数体**，只是创建一个协程对象；
3. `await 协程对象` 才真正开始执行 `fetch_data()` 的函数体；
4. 执行到 `await asyncio.sleep(1)`：这是**暂停点**——`fetch_data` 暂停，控制权交回事件循环；事件循环利用这 1 秒去执行其他就绪的协程；
5. 1 秒后 `sleep` 完成，事件循环唤醒 `fetch_data`，从暂停处**继续**，返回 `"data"`；
6. `main` 拿到结果，打印，程序结束，事件循环关闭。

#### 9.2.2 `await` 的语义：两个动作

`await X` 同时做了两件事：

1. **让出**：把控制权交回事件循环，让别的协程有机会执行；
2. **等待**：挂起当前协程，直到 `X` 完成（`X` 可以是另一个协程、Task、Future 等），拿到结果后从这一行继续执行。

用一个小例子感受「让出」：

```python
import asyncio


async def worker(name: str) -> None:
    for i in range(3):
        print(f"{name}: 第 {i} 步")
        await asyncio.sleep(0)   # 暂停点：即使不等待任何东西，也把控制权交回事件循环
```

`await asyncio.sleep(0)` 是刻意让出：不等待任何真实 I/O，只是让协程轮流执行（9.4 节会看到真正的并发效果）。

#### 9.2.3 为什么不能忘记 `await`

`await` 是协程执行的「开关」：**忘记 `await`，协程对象永远不会执行，函数体一行都不会跑**（第 11 节「常见错误 1」有专门讲解）。这一点和 Java 差异很大——Java 里调用方法立即执行；Python 里「调用协程函数」和「执行协程」是两件事，中间隔着 `await`。

#### 9.2.4 一个能看见「切换」的完整例子

只看单协程确实看不出「await 后别人执行」——因为只有一个协程，没有「别人」。用两个协程跑一次，切换就一目了然。

**例子 1：两个「请求」并发（总耗时 = 最慢的那个，而不是相加）**

```python
import asyncio
import time


async def fetch(name: str, delay: float) -> str:
    print(f"[{name}] 发起请求，预计耗时 {delay}s")
    await asyncio.sleep(delay)        # 模拟网络等待：这里让出控制权
    print(f"[{name}] 请求完成")
    return f"{name} 的结果"


async def main() -> None:
    start = time.perf_counter()

    t1 = asyncio.create_task(fetch("订单服务", 2))
    t2 = asyncio.create_task(fetch("库存服务", 1))

    r1, r2 = await asyncio.gather(t1, t2)   # 两个请求的等待重叠

    print(f"结果: {r1}, {r2}")
    print(f"总耗时: {time.perf_counter() - start:.1f}s")


asyncio.run(main())
```

输出（每次运行打印顺序可能略有差异，但结构一致）：

```text
[订单服务] 发起请求，预计耗时 2s
[库存服务] 发起请求，预计耗时 1s
[库存服务] 请求完成
[订单服务] 请求完成
结果: 订单服务 的结果, 库存服务 的结果
总耗时: 2.0s
```

三个关键观察：

1. **两个「发起请求」先打印，之后才轮到「请求完成」**——两个协程都开始执行了，等待是重叠的，不是 A 全部跑完才轮到 B；
2. **库存服务（1s）比订单服务（2s）先完成**，尽管它后创建——事件循环按「谁先准备好」恢复协程，不是按创建顺序；
3. **总耗时 ≈ 2s = max(2, 1)，而不是 3s = 2 + 1**——这就是「并发」的价值：总时间由最慢的一个决定，而不是逐个相加。如果写成同步代码一个接一个 `await`，总耗时就是 3s。

**例子 2：每一步都交替（看得见 await 让出）**

把 sleep 时间调小、多跑几步，让切换像齿轮一样明显：

```python
import asyncio


async def worker(name: str, steps: int) -> None:
    for i in range(steps):
        print(f"[{name}] 第 {i} 步")
        await asyncio.sleep(0.1)   # 每次到这里就让出，另一个协程接着跑


async def main() -> None:
    await asyncio.gather(
        worker("A", 3),
        worker("B", 3),
    )


asyncio.run(main())
```

输出：

```text
[A] 第 0 步
[B] 第 0 步
[A] 第 1 步
[B] 第 1 步
[A] 第 2 步
[B] 第 2 步
```

打印每一行之间，事件循环都完成了一次完整的「A 执行到 `await` 让出 → 切换 B → B 执行到 `await` 让出 → 切回 A」的轮转。**这正是「await 后其它协程执行」的实际画面。**

> 把例子里的 `asyncio.sleep(delay)` 换成 `httpx.AsyncClient.get(...)`、`asyncpg` 查询或 `llm.ainvoke(...)`，效果完全一样——真实 I/O 的等待期间，事件循环同样在调度其他协程。区别只是真实 I/O 的耗时由网络决定，而 `sleep` 由你自己控制（所以学习时用 `sleep` 最直观）。

### 9.3 不要混淆协程和任务

协程和任务可以这样理解：

```text
协程函数：做某件事的函数定义
协程对象：调用协程函数后得到的“待执行工作”
任务 Task：把待执行工作交给事件循环，让它负责调度和跟踪
```

可以用“做饭”来类比：

- 协程函数像菜谱，描述如何做菜。
- 协程对象像已经准备好的订单，但还没有交给厨房执行。
- 任务像厨房已经接单的订单，厨房（事件循环）会安排它执行，并记录它是否完成、失败或被取消。

协程函数的调用不会立即执行函数体：

```python
async def fetch_data() -> str:
    print("开始请求")
    await asyncio.sleep(1)
    print("请求完成")
    return "data"


coroutine = fetch_data()
print(coroutine)  # 协程对象
```

上面的代码只创建了协程对象，不会打印“开始请求”。需要 `await` 它，或者把它包装成 Task：

```python
import asyncio


async def main() -> None:
    coroutine = fetch_data()
    result = await coroutine  # await 会执行它并等待结果
    print(result)


asyncio.run(main())
```

### 9.3.1 什么是 Task

`Task` 是 asyncio 用来管理协程执行的对象。使用 `asyncio.create_task()` 后，协程会被安排给当前事件循环：

```python
import asyncio


async def main() -> None:
    task = asyncio.create_task(fetch_data())
    print("任务已经提交")

    result = await task  # 等待任务完成，并取得返回值
    print(result)
```

`create_task()` 的重点是“先提交、后等待”。提交任务后，当前协程可以继续做其他事情；当遇到 `await` 或其他让出执行权的地方，事件循环就有机会运行这个 Task。

例如，下面两个任务可以交替执行：

```python
async def main() -> None:
    data_task = asyncio.create_task(fetch_data())
    profile_task = asyncio.create_task(load_user_profile())

    # 两个任务已经提交，下面分别等待它们的结果
    data = await data_task
    profile = await profile_task
    print(data, profile)
```

如果两个操作互不依赖，也可以用 `asyncio.gather` 表达这种并发关系。不要为了并发而创建 Task；只有在需要让一个工作与当前流程同时推进、稍后再取得结果时，Task 才有意义。

如果直接连续 `await`，操作仍然是顺序执行：

```python
first = await fetch_first()
second = await fetch_second()
```

执行过程是：先完整执行 `fetch_first()`，它返回后才开始 `fetch_second()`。如果两个操作互不依赖，可以改成：

```python
async def main() -> None:
    first_task = asyncio.create_task(fetch_first())
    second_task = asyncio.create_task(fetch_second())

    first, second = await first_task, await second_task
    print(first, second)
```

### 9.3.2 Task 的结果、异常和状态

任务完成后，可以使用 `result()` 取得结果：

```python
task = asyncio.create_task(fetch_data())
await task
print(task.result())
```

但 `result()` 只能用于已经完成的任务。如果任务还没完成就调用，可能会抛出 `InvalidStateError`。更常见、更安全的写法是直接 `await task`。

如果任务内部抛出异常，异常会在 `await task` 时重新抛出：

```python
try:
    result = await task
except RuntimeError as error:
    print(f"任务失败: {error}")
```

Task 常见状态可以概括为：

```text
等待调度 -> 执行中 -> 已完成
                    -> 失败
                    -> 已取消
```

可以使用这些方法观察状态：

```python
task.done()       # 是否已经结束
task.cancelled()  # 是否被取消
task.exception()  # 已结束时取得异常
```

### 9.3.3 取消 Task

不再需要任务时，可以取消它：

```python
async def main() -> None:
    task = asyncio.create_task(fetch_data())
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        print("任务已取消")
```

任务内部如果需要清理资源，应捕获取消异常、完成清理后继续抛出：

```python
async def fetch_with_cleanup() -> str:
    try:
        return await fetch_data()
    except asyncio.CancelledError:
        print("释放请求资源")
        raise
```

不要把取消当成普通业务失败，也不要捕获 `CancelledError` 后静默吞掉，否则上层可能误以为任务正常完成。

### 9.3.4 协程、Task 和 Future 的关系

阶段 0 可以先记住下面的关系：

```text
协程：描述异步工作
Task：调度并跟踪一个协程
Future：表示未来某个时间可取得的结果
```

Task 是 Future 的一种具体实现，因此 Task 可以等待、取得结果、检查完成状态和取消。日常业务代码优先使用协程、`create_task`、`gather` 和 `TaskGroup`，通常不需要手动创建 Future。

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

#### 9.9.1 事件循环为什么会被阻塞

事件循环可以理解为一个不断运行的调度器：它在某个协程等待 I/O 时，切换去运行其他协程。协程只有在执行 `await` 并把控制权交还给事件循环时，其他任务才有机会运行。

```text
协程 A 执行一小段代码
    -> await 等待网络
    -> 事件循环运行协程 B
    -> B 等待时再运行其他任务
```

如果某个协程执行了同步阻塞函数，事件循环所在的线程就会被占住，其他任务也无法运行：

```python
import time


async def bad_function() -> None:
    time.sleep(3)
```

在 `bad_function()` 执行 `time.sleep(3)` 的 3 秒内，当前事件循环线程无法处理其他请求。对于 FastAPI 服务，这可能表现为：

- 一个慢请求导致其他请求也变慢。
- 心跳、超时和取消处理无法及时执行。
- Agent 的多个工具调用不能真正并发。
- 服务吞吐量下降，延迟突然升高。

#### 9.9.2 `await` 不等于一定不会阻塞

`await` 只有在等待的对象本身是异步、并且会适时交还控制权时，才不会阻塞事件循环：

```python
async def good_sleep() -> None:
    await asyncio.sleep(3)
```

下面的写法虽然包含 `await`，但仍可能阻塞，因为 `blocking_function()` 会在返回结果前同步执行：

```python
async def still_blocking() -> str:
    return await blocking_function()
```

如果 `blocking_function()` 是普通同步函数，上面的代码本身通常还会因为不能直接 `await` 而报错；如果同步库返回了可等待包装对象，也不能因此假设内部同步工作不会阻塞。判断标准不是“代码中有没有 `await`”，而是“耗时工作是否把控制权交还给事件循环”。

异步函数中应使用真正的异步版本：

```python
import asyncio


async def good_function() -> None:
    await asyncio.sleep(3)
```

对应关系示例：

| 阻塞写法 | 异步替代 |
|---|---|
| `time.sleep()` | `await asyncio.sleep()` |
| `requests.get()` | `await httpx.AsyncClient().get()` |
| 同步数据库驱动 | 异步数据库驱动 |
| 同步文件或 SDK 调用 | `asyncio.to_thread()`，或使用异步 SDK |

#### 9.9.3 没有异步版本时使用线程

如果必须调用没有异步版本的阻塞函数，可以使用 `asyncio.to_thread()` 把它放到线程中：

```python
import asyncio


def blocking_read() -> str:
    with open("data.txt", encoding="utf-8") as file:
        return file.read()


async def read_file() -> str:
    return await asyncio.to_thread(blocking_read)
```

`to_thread()` 的作用是让事件循环线程不执行这段同步代码，而是在线程中执行并异步等待结果。它适合：

- 同步文件读写
- 同步 SDK 调用
- 轻量的阻塞 I/O
- 没有异步版本的客户端库

它不是万能方案：线程仍然消耗系统资源，也不能解决大量 CPU 计算。还要注意同步函数中的线程安全问题。

#### 9.9.4 CPU 密集任务使用进程或专用任务队列

`to_thread()` 更适合 I/O 阻塞。对于图片处理、复杂解析、加密计算或大规模数据计算等 CPU 密集任务，应考虑进程池或独立任务队列：

```python
import asyncio


def calculate_score(values: list[int]) -> int:
    return sum(value * value for value in values)


async def calculate_in_process(values: list[int]) -> int:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        calculate_score,
        values,
    )
```

在生产系统中，更重的任务通常交给 Celery、RQ、Temporal 或其他任务系统处理，API 只负责创建任务并返回任务 ID。不要让 FastAPI 请求一直等待一个很重的 CPU 计算。

#### 9.9.5 常见阻塞来源

- `time.sleep`
- `requests` 等同步 HTTP 客户端
- 同步数据库客户端
- 同步 Redis 客户端
- 没有异步版本的第三方 SDK
- 大文件同步读写
- 大规模 JSON 或文档解析
- CPU 密集型循环
- 在异步路由中执行同步 Shell 命令

文件读写是否需要线程，要结合文件大小、访问频率和部署方式判断；不能因为使用了 `async def` 就认为函数内部所有操作自动异步。

#### 9.9.6 FastAPI 中的判断原则

```python
from fastapi import FastAPI


app = FastAPI()


@app.get("/bad")
async def bad_endpoint() -> dict[str, str]:
    time.sleep(3)  # 会阻塞处理其他请求的事件循环
    return {"status": "done"}


@app.get("/good")
async def good_endpoint() -> dict[str, str]:
    await asyncio.sleep(3)
    return {"status": "done"}
```

如果必须使用同步函数，FastAPI 也可以处理普通的 `def` 路由，但应理解其执行模型，并避免在异步代码中直接调用阻塞函数。外部网络请求优先使用 HTTPX `AsyncClient`，不要在 `async def` 路由中调用同步 HTTP 客户端。

#### 9.9.7 如何排查事件循环阻塞

可以从以下方向排查：

1. 搜索 `async def` 函数中的 `time.sleep`、`requests` 和同步数据库调用。
2. 检查异步路由是否调用了同步 Service 或同步 SDK。
3. 记录请求开始时间、上游调用耗时和总耗时。
4. 在开发环境开启 asyncio 调试模式：

```bash
python -X dev main.py
```

5. 使用日志或性能分析工具找出长时间没有让出控制权的代码。

判断是否存在阻塞的一个简单信号是：某个请求执行本身并不复杂，但同时到来的其他请求也在相同时间明显卡顿。

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
