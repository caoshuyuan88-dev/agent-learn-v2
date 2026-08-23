# LLM 调用与上下文管理

> 阶段 1 第一份文档：先用 Python 理解模型调用，再进入 LangChain。

## 一、学习目标

完成本文后，你应该能够：

- 理解 Chat API 的请求和响应结构
- 区分 system、user、assistant 消息
- 管理多轮对话和上下文窗口
- 理解 token、temperature、top-p、max tokens
- 设计超长上下文的截断和摘要策略
- 使用 Pydantic 表示请求和响应

## 二、Chat API 的基本结构

一次聊天请求通常包含模型名和消息列表：

```python
messages = [
    {"role": "system", "content": "你是一个严谨的 Python 助手。"},
    {"role": "user", "content": "解释什么是 asyncio。"},
]
```

角色含义：

- `system`：应用规则、角色和安全边界
- `user`：用户输入
- `assistant`：模型历史回复
- `tool`：工具执行结果

多轮对话本质上是把历史消息再次发送给模型：

```python
messages = [
    {"role": "system", "content": "你是 Python 助手。"},
    {"role": "user", "content": "什么是列表？"},
    {"role": "assistant", "content": "列表是有序、可变的容器。"},
    {"role": "user", "content": "它允许重复元素吗？"},
]
```

模型本身不会自动记住上一轮请求。记忆通常由应用保存并重新组装消息。

## 三、直接调用模型的通用方式

不同供应商的 SDK 名称不同，但基本流程相近：

```text
准备消息
  -> 发送请求
  -> 等待响应
  -> 读取文本或结构化结果
  -> 记录 token、延迟和错误
```

建议将供应商 SDK 隔离在一个 Client 类中：

```python
class LLMClient:
    async def chat(self, messages: list[dict[str, str]]) -> str:
        response = await self.provider.chat(messages=messages)
        return response.text
```

业务层只依赖 `LLMClient` 的能力，不直接依赖某个供应商 SDK，后续更容易切换云端模型或 Ollama。

## 四、Token 和上下文窗口

Token 是模型处理文本的基本单位，不等同于字符或单词。上下文窗口限制的是一次请求中可处理的 token 总量，通常包括：

- system prompt
- 历史消息
- 当前用户输入
- 工具定义和工具结果
- 模型输出预留空间

可以粗略理解为：

```text
输入 token + 输出 token <= 模型上下文窗口
```

上下文超长可能导致请求失败、成本增加或模型注意力下降。

### 上下文管理策略

- 限制历史消息数量
- 按 token 而不是字符估算长度
- 保留 system 消息和最近几轮对话
- 将旧消息压缩成摘要
- 将长期知识移到 RAG 检索
- 工具结果只保留必要字段
- 为模型输出预留 token 空间

## 五、temperature、top-p 和 max tokens

### temperature

控制输出随机性：

- 较低：更稳定，适合抽取、分类、代码和工具参数
- 较高：更有变化，适合创意生成

### top-p

控制采样候选范围。通常不需要同时大幅调整 `temperature` 和 `top-p`，先固定一个，只调整另一个。

### max tokens

限制模型输出长度。它不是上下文窗口大小，而是输出部分的上限。

推荐起点：

```text
结构化抽取 / Tool Calling：较低 temperature
知识问答：低到中等 temperature
创意文本：中等 temperature
```

参数需要通过实验和评测确定，不能只凭直觉。

## 六、System Prompt 设计

一个实用的 system prompt 通常包含：

```text
角色：你是谁
目标：要完成什么任务
边界：不能做什么
输入格式：用户会提供什么
输出格式：必须返回什么
工具规则：什么时候调用工具
不确定性：没有依据时怎么回答
```

不要把安全边界只放在用户消息中。用户消息属于不可信输入，system prompt 和服务端权限检查才是控制边界的重要位置。

## 七、上下文窗口中的信息优先级

建议优先保留：

1. 系统规则和安全约束
2. 当前任务目标
3. 与当前问题直接相关的检索结果
4. 最近几轮对话
5. 较早的低相关历史

不要无条件把所有历史、工具返回值和检索文档塞给模型。上下文越多不代表答案越好。

## 八、结构化请求模型

可以用 Pydantic 描述聊天请求：

```python
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)
    conversation_id: str | None = None
    temperature: float = Field(default=0.2, ge=0, le=2)
```

这可以在进入模型调用前拦截空消息、超长消息和非法参数。

## 九、学习练习

1. 实现一个消息列表构建函数，支持 system、历史消息和当前问题。
2. 添加最大历史轮数限制。
3. 当历史超过限制时，只保留 system 消息和最近 3 轮。
4. 使用 Pydantic 校验 `ChatRequest`。
5. 设计一个 `LLMClient` Protocol，并实现一个 Fake 客户端。

## 十、验收标准

- 能解释 Chat API 的消息角色
- 能实现基本多轮对话消息组装
- 能说明模型为什么不会自动记住历史
- 能解释 token、上下文窗口和输出上限
- 能根据任务选择基本采样参数
- 能设计上下文截断、摘要和 RAG 分流策略
- 能将供应商 SDK 隔离在 Client 层
