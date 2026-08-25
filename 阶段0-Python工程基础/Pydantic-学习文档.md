# Pydantic 学习文档

> 面向有 Java 后端经验、正在学习 Python Agent 工程的开发者。
>
> 本文基于 Pydantic v2，目标是掌握阶段 0 中真正需要的能力：用类型注解定义数据结构，用 Pydantic 完成数据校验、转换、序列化，并为 FastAPI 接口提供可靠的数据模型。

## 一、Pydantic 是什么

Pydantic 是一个基于 Python 类型注解的数据校验和数据建模库。

可以把它理解成：

```text
外部输入
  -> Pydantic 模型
  -> 校验、类型转换
  -> 业务代码
```

在 Agent 服务中，数据来源很多：

- HTTP 请求参数
- LLM 的结构化输出
- 工具调用参数
- 环境变量配置
- 数据库查询结果
- 外部 API 响应

这些数据都不应该直接相信。Pydantic 可以把不可靠的外部数据转换成结构清晰、类型明确的 Python 对象。

## 二、学习目标

完成本文后，你应该能够：

- 使用 `BaseModel` 定义数据模型
- 为字段声明类型和默认值
- 校验必填字段、长度、范围和格式
- 定义嵌套模型和列表模型
- 编写自定义校验逻辑
- 处理校验失败异常
- 在模型、字典和 JSON 之间转换
- 从环境变量读取应用配置
- 为 FastAPI 定义请求模型和响应模型
- 为 LLM 输出定义结构化结果模型

阶段 0 暂时不需要深入：

- Pydantic 的内部实现
- 自定义核心 Schema
- 复杂的泛型设计
- Pydantic v1 兼容写法

本文示例统一使用 Pydantic v2。

## 三、安装与第一个模型

建议在项目虚拟环境中安装：

```bash
pip install pydantic
```

第一个模型：

```python
from pydantic import BaseModel


class User(BaseModel):
    name: str
    age: int


user = User(name="Alice", age=30)

print(user.name)
print(user.age)
```

`User` 是一个模型类，`name` 和 `age` 是模型字段。

与普通 Python 类相比，Pydantic 会根据类型注解检查输入数据：

```python
user = User(name="Alice", age="30")

print(user.age)
print(type(user.age))
```

在默认配置下，Pydantic 可能会把可以转换的字符串转换成整数。但不要把这种转换理解为无条件容错，严格性应根据业务需要配置。

## 四、字段、必填项和默认值

### 4.1 必填字段

```python
from pydantic import BaseModel


class TaskCreate(BaseModel):
    title: str
    description: str
```

`title` 和 `description` 都是必填字段。

```python
TaskCreate(title="学习 Pydantic")
```

上面的代码会因为缺少 `description` 而校验失败。

### 4.2 默认值

```python
from pydantic import BaseModel


class TaskCreate(BaseModel):
    title: str
    completed: bool = False
```

此时 `completed` 可以不传，默认值为 `False`。

### 4.3 可选字段

“可以不传”和“可以传空值”不是一回事。

```python
from pydantic import BaseModel


class UserProfile(BaseModel):
    nickname: str | None = None
```

这个字段可以不传，也可以传 `None`。

```python
profile_a = UserProfile()
profile_b = UserProfile(nickname=None)
```

如果字段必须传，但允许值为 `None`：

```python
class UserProfile(BaseModel):
    nickname: str | None
```

## 五、字段约束：Field

使用 `Field` 可以为字段增加长度、范围、正则表达式和描述信息。

```python
from pydantic import BaseModel, Field


class Product(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    price: float = Field(gt=0)
    stock: int = Field(ge=0)
```

常用约束：

| 约束 | 含义 |
|---|---|
| `min_length` | 字符串最小长度 |
| `max_length` | 字符串最大长度 |
| `gt` | 大于 |
| `ge` | 大于等于 |
| `lt` | 小于 |
| `le` | 小于等于 |
| `pattern` | 字符串正则表达式 |
| `min_items` | 列表最小数量，具体版本中优先使用长度注解或集合约束 |

为接口文档添加说明：

```python
class TaskCreate(BaseModel):
    title: str = Field(
        min_length=1,
        max_length=200,
        description="任务标题",
    )
```

## 六、常用类型

```python
from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class TaskStatus(str, Enum):
    TODO = "todo"
    DOING = "doing"
    DONE = "done"


class Task(BaseModel):
    id: UUID
    title: str
    status: TaskStatus = TaskStatus.TODO
    priority: int = Field(default=1, ge=1, le=5)
    owner_email: EmailStr
    created_at: datetime
    tags: list[str] = []
```

常见类型包括：

- `str`、`int`、`float`、`bool`
- `list[str]`、`dict[str, str]`
- `str | None`
- `datetime`
- `UUID`
- `Enum`
- `EmailStr`

使用 `EmailStr` 需要安装额外依赖：

```bash
pip install pydantic[email]
```

## 七、嵌套模型

复杂业务数据通常由多个模型组成：

```python
from pydantic import BaseModel


class Address(BaseModel):
    city: str
    detail: str


class User(BaseModel):
    name: str
    address: Address
```

输入数据可以是嵌套字典：

```python
user = User(
    name="Alice",
    address={
        "city": "Shanghai",
        "detail": "Pudong",
    },
)

print(user.address.city)
```

列表嵌套模型：

```python
class Team(BaseModel):
    name: str
    members: list[User]
```

嵌套模型是 FastAPI 请求体、数据库对象和 Agent 工具参数中最常见的写法之一。

## 八、模型校验

### 8.1 捕获校验异常

```python
from pydantic import BaseModel, Field, ValidationError


class TaskCreate(BaseModel):
    title: str = Field(min_length=1)
    priority: int = Field(ge=1, le=5)


try:
    TaskCreate(title="", priority=10)
except ValidationError as error:
    print(error)
```

错误信息通常包含：

- 哪个字段出错
- 出错位置
- 错误原因
- 收到的输入值

程序代码中不要只依赖打印错误，应根据业务将异常转换成合适的接口错误或日志。

### 8.2 自定义字段校验

当 `Field` 无法表达业务规则时，可以使用 `field_validator`：

```python
from pydantic import BaseModel, field_validator


class User(BaseModel):
    username: str

    @field_validator("username")
    @classmethod
    def username_must_not_contain_spaces(cls, value: str) -> str:
        if " " in value:
            raise ValueError("用户名不能包含空格")
        return value
```

校验器必须返回处理后的值，否则字段值会丢失。

### 8.3 模型级校验

当两个或多个字段需要一起判断时，可以使用 `model_validator`：

```python
from pydantic import BaseModel, model_validator


class PasswordChange(BaseModel):
    password: str
    password_confirmation: str

    @model_validator(mode="after")
    def passwords_must_match(self):
        if self.password != self.password_confirmation:
            raise ValueError("两次密码不一致")
        return self
```

## 九、序列化和反序列化

### 9.1 模型转字典

```python
class Task(BaseModel):
    title: str
    completed: bool = False


task = Task(title="学习 Pydantic")
data = task.model_dump()

print(data)
```

### 9.2 模型转 JSON

```python
json_text = task.model_dump_json()
print(json_text)
```

### 9.3 字典转模型

```python
data = {
    "title": "学习 FastAPI",
    "completed": False,
}

task = Task.model_validate(data)
```

### 9.4 JSON 转模型

```python
json_text = '{"title": "学习 HTTPX", "completed": false}'
task = Task.model_validate_json(json_text)
```

Pydantic v2 中优先使用：

| 目的 | 推荐方法 |
|---|---|
| 模型转字典 | `model_dump()` |
| 模型转 JSON | `model_dump_json()` |
| 字典转模型 | `model_validate()` |
| JSON 转模型 | `model_validate_json()` |

不要继续使用 Pydantic v1 中常见的 `dict()`、`json()`、`parse_obj()` 作为新代码的首选写法。

## 十、模型配置

### 10.0 `model_config` 是什么

`model_config` 是 Pydantic v2 中用于配置模型行为的类属性。它决定模型如何处理额外字段、是否进行类型转换、是否去除字符串首尾空白，以及如何生成 JSON Schema。

基本写法是：

```python
from pydantic import BaseModel, ConfigDict


class UserInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    username: str
```

这里的 `model_config` 不是业务数据字段，而是 Pydantic 的模型级配置。输入数据中不会出现名为 `model_config` 的接口字段；它只影响 Pydantic 如何校验和处理模型数据。

可以把它理解为“这个模型的校验规则开关”：

```text
字段类型和 Field
  -> 规定字段本身允许什么值

model_config
  -> 规定整个模型如何处理输入数据
```

例如：

```python
class UserInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str


user = UserInput(username="  alice  ")
print(user.username)
# alice
```

`str_strip_whitespace=True` 会自动执行字符串的 `strip()` 效果，只处理首尾空白，不会删除中间空格，也不会把空字符串自动变成 `None`。如果还要求字符串不能为空，需要继续使用 `Field(min_length=1)`。

### 10.0.1 常用配置项

| 配置项 | 作用 | 常见使用场景 |
|---|---|---|
| `extra="ignore"` | 忽略未声明字段，通常是默认行为 | 兼容字段可能变化的外部数据 |
| `extra="forbid"` | 未声明字段直接校验失败 | 工具参数、权限数据、严格 API 契约 |
| `extra="allow"` | 保留未声明字段 | 确实需要扩展字段的输入模型 |
| `strict=True` | 尽量禁止隐式类型转换 | 金额、权限、工具参数等敏感数据 |
| `str_strip_whitespace=True` | 去除字符串首尾空白 | 用户名、标题、搜索关键词 |
| `str_min_length` | 为字符串设置统一最小长度 | 模型中所有字符串都有最低长度时 |
| `str_max_length` | 为字符串设置统一最大长度 | 统一限制文本输入规模 |
| `validate_assignment=True` | 修改模型属性时再次校验 | 需要保证对象在运行过程中始终有效 |
| `frozen=True` | 禁止修改模型字段 | 配置对象、不可变值对象 |
| `from_attributes=True` | 允许从对象属性读取数据 | 从 ORM 对象生成响应模型 |

### 10.0.2 `model_config` 和 `Field` 的区别

`Field` 更适合配置某一个字段，`model_config` 更适合配置整个模型：

```python
class TaskCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    title: str = Field(min_length=1, max_length=200)
    priority: int = Field(ge=1, le=5)
```

两者分别负责：

- `Field`：`title` 不能为空、最多 200 个字符；`priority` 必须在 1 到 5 之间。
- `model_config`：所有字符串去除首尾空白，并禁止输入未声明的字段。

如果只写 `str_strip_whitespace=True`，输入全是空格的标题会变成空字符串，但不一定失败；因此通常要和 `Field(min_length=1)` 组合使用。

### 10.0.3 配置的作用范围和继承

配置通常只影响当前模型，也可以通过继承复用：

```python
class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class ToolArguments(StrictModel):
    user_id: int
    action: str
```

`ToolArguments` 会继承 `StrictModel` 的配置。子模型也可以重新声明 `model_config` 覆盖或补充配置。嵌套模型是否采用相同配置，要看嵌套模型自己的定义，不能假设外层配置会自动改变所有内部模型。

### 10.0.4 与 Java 的对比

`model_config` 没有一个完全等价的 Java 注解，更接近“模型类上的统一配置 + Jackson 反序列化配置”的组合：

```text
Pydantic model_config
  ≈ Jackson ObjectMapper 配置
  + DTO 上的反序列化注解
  + Bean Validation 的统一约束策略
```

例如：

| Pydantic | Java 常见对应思路 |
|---|---|
| `extra="forbid"` | Jackson 禁止未知字段，或 DTO 严格反序列化配置 |
| `strict=True` | 禁止 Jackson 宽松类型转换，并配合严格校验 |
| `str_strip_whitespace=True` | 自定义反序列化器或统一字符串清洗器 |
| `Field(min_length=1)` | `@Size(min = 1)`、`@NotBlank` |
| `Field(ge=1, le=5)` | `@Min(1)` 和 `@Max(5)` |
| `from_attributes=True` | 从 ORM 实体映射到 DTO |

区别在于：Pydantic 把类型、字段约束和部分模型行为集中写在 Python 模型中；Java 通常由 DTO、Jackson 和 Bean Validation 多个机制共同完成。

### 10.1 禁止额外字段

默认情况下，模型可能忽略输入中的额外字段。对于安全敏感或接口边界，通常建议明确配置：

```python
from pydantic import BaseModel, ConfigDict


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int
    action: str
```

这样，输入未声明的字段会触发校验错误。

### 10.2 严格模式

如果不希望 Pydantic 自动进行部分类型转换，可以使用严格模式：

```python
from pydantic import BaseModel, ConfigDict


class InputData(BaseModel):
    model_config = ConfigDict(strict=True)

    count: int
```

选择默认转换还是严格模式，要根据接口契约决定。对于工具参数、权限字段和金额等重要数据，严格校验通常更稳妥。

## 十一、Settings：读取环境变量

应用配置不要硬编码在代码中，可以使用 `pydantic-settings`：

```bash
pip install pydantic-settings
```

```python
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    app_name: str = "agent-service"
    debug: bool = False
    database_url: str
    api_key: SecretStr


settings = Settings()
print(settings.app_name)
```

`.env` 示例：

```text
DATABASE_URL=postgresql://localhost/agent
API_KEY=replace-me
DEBUG=false
```

注意：

- `.env` 不要提交到 Git
- 密钥不要打印到日志
- 生产环境应使用平台的 Secret 管理能力
- 配置对象可以在应用启动时创建一次

## 十二、Pydantic 与 FastAPI

FastAPI 会自动使用 Pydantic 完成请求校验、响应序列化和 OpenAPI 文档生成。

```python
from fastapi import FastAPI
from pydantic import BaseModel, Field


app = FastAPI()


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class TaskResponse(BaseModel):
    id: int
    title: str
    completed: bool


@app.post("/tasks", response_model=TaskResponse)
async def create_task(request: TaskCreate) -> TaskResponse:
    return TaskResponse(
        id=1,
        title=request.title,
        completed=False,
    )
```

这里有三个重要边界：

- `TaskCreate`：客户端可以提交的字段
- `TaskResponse`：接口允许返回的字段
- 数据库模型：数据库内部保存的字段

不要直接把数据库模型、请求模型和响应模型混成一个类。分别定义它们，可以避免意外暴露内部字段，例如密码哈希、内部状态和权限信息。

## 十三、Pydantic 与 Agent

### 13.1 工具参数

Agent 调用工具时，工具参数必须经过校验：

```python
from pydantic import BaseModel, Field


class SearchOrdersInput(BaseModel):
    user_id: int = Field(gt=0)
    status: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
```

这样可以限制：

- 用户 ID 必须为正数
- 返回数量不能过大
- 状态字段格式明确
- LLM 不能随意增加未声明参数

### 13.2 结构化输出

可以用模型描述 Agent 最终结果：

```python
from pydantic import BaseModel, Field


class AgentAnswer(BaseModel):
    answer: str
    confidence: float = Field(ge=0, le=1)
    needs_human_review: bool = False
    sources: list[str] = []
```

这比让模型返回一段无法可靠解析的自由文本更适合生产系统。

## 十四、一个完整练习

实现一个任务创建模块，要求：

```python
class TaskCreate(BaseModel):
    title: str
    priority: int = 1
    tags: list[str] = []
```

要求：

1. `title` 长度为 1 到 100 个字符。
2. `priority` 范围为 1 到 5。
3. `tags` 最多包含 5 个标签。
4. 标签不能为空字符串。
5. 输入额外字段时校验失败。
6. 编写正常输入和错误输入测试。
7. 将模型接入一个 FastAPI `POST /tasks` 接口。

提示：可以组合使用 `Field`、`field_validator` 和 `ConfigDict(extra="forbid")`。

## 十五、推荐项目结构

学习阶段可以使用这样的结构：

```text
app/
  __init__.py
  main.py
  schemas.py
  settings.py
  services.py
tests/
  test_schemas.py
  test_api.py
pyproject.toml
.env.example
```

建议：

- `schemas.py`：请求模型、响应模型和工具参数模型
- `settings.py`：应用配置
- `services.py`：业务逻辑
- `main.py`：FastAPI 路由
- `tests/`：模型和接口测试

## 十六、阶段 0 验收标准

你可以独立完成下面的任务，就说明 Pydantic 基础达标：

- 为一个 FastAPI 接口定义请求模型和响应模型
- 为字段添加长度、范围和枚举约束
- 定义两个层级以上的嵌套模型
- 捕获并理解 `ValidationError`
- 使用 `model_dump()` 将模型转换为字典
- 使用 `model_validate()` 从字典创建模型
- 使用 `BaseSettings` 读取环境变量
- 为 Agent 工具定义参数模型
- 为结构化输出定义结果模型
- 编写至少 5 个模型校验测试

## 十七、学习建议

推荐学习顺序：

```text
BaseModel
  -> 字段和类型
  -> Field 约束
  -> 嵌套模型
  -> ValidationError
  -> 序列化
  -> 自定义校验器
  -> Settings
  -> FastAPI 集成
  -> Agent 工具参数和结构化输出
```

每学一个主题，都用一个失败案例验证它：缺字段、类型错误、超出范围、额外字段、嵌套结构错误。理解“输入为什么失败”，比记住 API 名称更重要。

## 十八、官方参考

- [Pydantic 官方文档](https://docs.pydantic.dev/latest/)
- [Pydantic Models](https://docs.pydantic.dev/latest/concepts/models/)
- [Pydantic Fields](https://docs.pydantic.dev/latest/concepts/fields/)
- [Pydantic Validators](https://docs.pydantic.dev/latest/concepts/validators/)
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [FastAPI 中文文档](https://fastapi.tiangolo.com/zh/)
