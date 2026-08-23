# Streaming 与结构化输出

## 一、学习目标

- 理解流式响应和普通响应的区别
- 为聊天接口逐块返回模型输出
- 处理客户端断开、超时和错误
- 使用 JSON Schema 和 Pydantic 获取可靠结构
- 区分结构化输出与普通文本中的 JSON

## 二、普通响应和流式响应

普通响应需要等待模型生成结束后一次性返回：

```text
请求 -> 等待完整结果 -> 返回全部文本
```

流式响应则是模型生成一部分就发送一部分：

```text
请求 -> 首个片段 -> 后续片段 -> 完成事件
```

Streaming 的优点：

- 更快看到首字
- 用户感知延迟更低
- 适合长答案和 Agent 过程展示

代价：

- 客户端处理更复杂
- 中途断开需要清理资源
- 最终完整答案需要自行拼接
- 错误可能发生在响应已经开始之后

## 三、流式事件处理

不同模型 SDK 的事件名称不同，但应用层可以统一成：

```python
async def stream_answer() -> AsyncIterator[str]:
    async for event in provider_stream():
        if event.type == "text_delta":
            yield event.text
```

服务端需要区分：

- 文本片段
- 工具调用片段
- 完成事件
- 错误事件
- 用量事件

不要把所有事件都当作文本直接输出。

## 四、FastAPI 中的 SSE 思路

```python
from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse


async def answer_stream() -> AsyncIterator[str]:
    async for chunk in agent.stream("你好"):
        yield f"data: {chunk}\n\n"


@app.get("/chat/stream")
async def chat_stream() -> StreamingResponse:
    return StreamingResponse(
        answer_stream(),
        media_type="text/event-stream",
    )
```

生产环境还要考虑：

- `data` 内容的编码
- 完成标记
- 请求 ID 和会话 ID
- 客户端断开后的取消传播
- 代理服务器缓冲
- 心跳和空闲超时

## 五、结构化输出是什么

普通文本：

```text
用户意图是查询订单，订单号为 1001。
```

结构化输出：

```json
{
  "intent": "query_order",
  "order_id": 1001
}
```

结构化输出的价值是让程序可以稳定消费模型结果，而不是依赖字符串截取或正则表达式。

## 六、Pydantic 结果模型

```python
from pydantic import BaseModel, Field
from typing import Literal


class OrderIntent(BaseModel):
    intent: Literal["query_order", "cancel_order", "unknown"]
    order_id: int | None = Field(default=None, gt=0)
    confidence: float = Field(ge=0, le=1)
```

模型返回结果后进行校验：

```python
result = OrderIntent.model_validate(model_output)
```

如果结果缺字段、值不在允许范围或类型错误，应记录错误并进入重试、修复或人工处理流程。

## 七、JSON Schema

JSON Schema 用机器可读的方式描述 JSON 结构：

```json
{
  "type": "object",
  "properties": {
    "intent": {
      "type": "string",
      "enum": ["query_order", "cancel_order", "unknown"]
    },
    "order_id": {
      "type": ["integer", "null"]
    }
  },
  "required": ["intent", "order_id"]
}
```

实际开发中通常由 Pydantic 模型生成 Schema，避免同时手写两份定义。

## 八、结构化输出失败处理

可能的失败原因：

- 模型返回了缺失字段
- 枚举值拼写错误
- JSON 格式不完整
- 字段类型不正确
- 业务规则不满足

处理策略：

1. Pydantic 校验。
2. 记录原始结果和错误类型，但注意脱敏。
3. 进行有限次数的修复或重试。
4. 无法恢复时返回明确错误或请求人工审核。

不要无限重试，因为模型可能持续生成同样的错误。

## 九、Streaming 与结构化输出的关系

普通文本适合直接流式输出。结构化结果通常要等到 JSON 完整后再校验；如果要流式展示结构化结果，需要使用支持增量 JSON 的解析策略，并处理半截 JSON。

建议阶段 1 先掌握：

```text
文本 Streaming
  -> 完整结果 Structured Output
  -> 再学习结构化结果的增量流式处理
```

## 十、学习练习

1. 实现一个异步文本流生成器。
2. 将流式片段拼接为完整答案。
3. 为订单意图定义 Pydantic 模型。
4. 模拟缺字段、错误枚举和非法 JSON。
5. 为 FastAPI 添加 SSE 接口，并处理客户端取消。

## 十一、验收标准

- 能解释 Streaming 与普通响应的差异
- 能实现异步文本片段迭代
- 能理解 SSE 的基本格式
- 能使用 Pydantic 校验模型输出
- 能从 Pydantic 模型生成 JSON Schema
- 能区分模型错误、格式错误和业务校验错误
- 能设计结构化输出失败后的有限重试策略
