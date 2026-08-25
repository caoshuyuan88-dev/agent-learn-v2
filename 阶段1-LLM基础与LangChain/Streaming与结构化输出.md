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

### 3.1 这段代码到底如何执行

先看一个简化的事件生产器：

```python
from dataclasses import dataclass
from collections.abc import AsyncIterator


@dataclass
class Event:
    type: str
    text: str


async def provider_stream() -> AsyncIterator[Event]:
    yield Event(type="text_delta", text="你好")
    yield Event(type="tool_call", text="查询订单")
    yield Event(type="text_delta", text="，有什么可以帮助你？")
```

`provider_stream()` 是事件生产者，`stream_answer()` 是事件过滤器和文本转发器。调用方再负责消费 `stream_answer()`：

```python
async for text in stream_answer():
    print(text)
```

完整执行路径如下：

```text
1. 调用 stream_answer()
   -> 只创建异步生成器对象，函数体尚未真正执行

2. async for 第一次向 provider_stream() 要事件
   -> 得到 Event("text_delta", "你好")
   -> 条件成立
   -> yield "你好"
   -> 暂停 stream_answer()
   -> 调用方收到 "你好"

3. 调用方继续 async for
   -> stream_answer() 从上一次 yield 后面继续
   -> async for 再向 provider_stream() 要事件
   -> 得到 Event("tool_call", "查询订单")
   -> 条件不成立
   -> 不执行 yield，继续获取下一个事件

4. 得到 Event("text_delta", "，有什么可以帮助你？")
   -> 条件成立
   -> yield "，有什么可以帮助你？"
   -> 暂停 stream_answer()
   -> 调用方收到第二个文本片段

5. provider_stream() 没有更多事件
   -> async for 结束
   -> stream_answer() 结束
   -> 调用方的 async for 结束
```

因此调用方实际收到的是两个字符串：

```text
第一次：你好
第二次：，有什么可以帮助你？
```

如果调用方需要完整答案，需要自行拼接：

```python
answer = ""

async for text in stream_answer():
    answer += text

print(answer)
# 你好，有什么可以帮助你？
```

### 3.2 `yield`、`return` 和 `await` 在这里分别做什么

```text
await provider_stream 的下一个事件
  -> 等待异步数据到达，不阻塞整个事件循环

yield event.text
  -> 把当前片段交给调用方，并暂停当前生成器

return
  -> 结束函数，不再产生后续片段
```

`yield` 并不会把所有结果一次性返回。每执行一次 `yield`，调用方就得到一个片段；调用方下一次迭代时，函数才从上次暂停的位置继续。

可以把它理解为传送带：

```text
provider_stream：生产事件
  -> stream_answer：过滤 tool_call，只留下文本
  -> async for 调用方：逐个接收文本片段
```

### 3.3 放入 FastAPI 后谁在消费它

```python
from fastapi.responses import StreamingResponse


@app.get("/chat/stream")
async def chat_stream() -> StreamingResponse:
    return StreamingResponse(
        stream_answer(),
        media_type="text/plain",
    )
```

这里的 `chat_stream()` 不会自己执行 `stream_answer()` 的循环，而是把异步生成器交给 `StreamingResponse`。真正的执行路径是：

```text
客户端请求 GET /chat/stream
  -> FastAPI 调用 chat_stream()
  -> 创建 stream_answer() 异步生成器
  -> 返回 StreamingResponse
  -> StreamingResponse 开始 async for 消费 stream_answer()
  -> stream_answer() yield "你好"
  -> StreamingResponse 立即发送 "你好"
  -> StreamingResponse 继续消费下一个片段
  -> 发送 "，有什么可以帮助你？"
  -> 生成器结束，响应结束
```

注意：`StreamingResponse(stream_answer())` 传入的是生成器对象，不是已经拼好的字符串；因此响应可以边生成边发送。

服务端需要区分：

- 文本片段
- 工具调用片段
- 完成事件
- 错误事件
- 用量事件

不要把所有事件都当作文本直接输出。

## 四、FastAPI 中的 SSE 思路
#### SSE 是什么

可以把 SSE 理解为“服务端保持一个 HTTP 响应不结束，并持续向客户端追加事件”。客户端发起一次连接后，服务端按照 SSE 协议逐条发送文本事件；每条事件以空行结束，客户端收到后即可触发对应的处理逻辑，而不必等待整个响应完成。

一个最小的 SSE 事件如下：

```text
event: token
data: {"text":"你好"}

```

其中：

- `event` 表示事件类型，客户端可以据此区分文本、进度、完成和错误。
- `data` 表示事件数据，通常使用 JSON，方便携带多个字段。
- 末尾的空行表示这一条事件已经结束，客户端可以开始处理。

SSE 的通信方向只有一条：服务端通过这条连接推送数据，客户端不能复用同一条 SSE 连接向服务端发送业务消息。客户端需要发送新问题或提交操作时，仍使用 `POST` 等普通 HTTP 请求；如果需要双向持续通信，应考虑 WebSocket。

在浏览器中可以这样接收 SSE：

```javascript
const source = new EventSource("/messages/123/events");

source.addEventListener("token", (event) => {
  const data = JSON.parse(event.data);
  console.log(data.text);
});

source.addEventListener("done", () => {
  source.close();
});
```

因此，SSE 解决的是“服务端如何持续推送事件”，并不自动解决消息持久化、断线恢复、业务幂等、权限认证或任务执行本身。这些能力需要应用层结合 `id`、`Last-Event-ID`、任务状态和结果存储自行设计。
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

### 4.1 SSE 数据格式和编码

SSE 不是把任意字符串直接写入 HTTP 响应，而是使用约定的文本格式。每个事件通常以一个或多个字段组成，并使用空行表示事件结束：

```text
event: token
data: {"text":"你好"}

event: done
data: {"request_id":"req-123"}

```

推荐让 `data` 传 JSON，而不是直接拼接不受控制的文本：

```python
import json


def sse_event(event: str, data: dict[str, object]) -> str:
  payload = json.dumps(data, ensure_ascii=False)
  return f"event: {event}\ndata: {payload}\n\n"
```

这样可以正确传递中文、引号、换行和结构化字段。生产代码还应设置 UTF-8 编码，并避免把用户输入直接拼进 SSE 控制字段，防止换行造成事件格式混乱。

### 4.2 完成事件和错误事件

客户端不能只依靠连接关闭判断模型是否正常完成。建议定义明确的事件类型：

```text
event: token       -> 一个文本片段
event: tool_start  -> 工具开始执行
event: tool_end    -> 工具执行结束
event: done        -> 正常完成
event: error       -> 发生错误
```

例如：

```python
async def answer_stream() -> AsyncIterator[str]:
  try:
    async for chunk in agent.stream("你好"):
      yield sse_event("token", {"text": chunk})
    yield sse_event("done", {"reason": "completed"})
  except Exception:
    yield sse_event(
      "error",
      {"code": "stream_failed", "message": "生成失败"},
    )
```

错误信息应返回稳定的错误码，不要把堆栈、API Key、内部 URL 或数据库信息发送给客户端。注意：如果 HTTP 响应已经开始发送，之后通常不能再修改 HTTP 状态码，只能发送一个 `error` 事件并关闭连接。

### 4.3 请求 ID、会话 ID 和消息 ID

流式响应持续时间较长，日志和故障排查必须能够关联一次请求：

- `request_id`：标识一次 HTTP 请求，用于日志和链路追踪。
- `conversation_id`：标识多轮对话，通常由客户端传入或服务端创建。
- `message_id`：标识本次生成的消息，便于重试、保存和去重。

建议在响应事件和服务端日志中都记录这些 ID：

```json
{
  "event": "token",
  "request_id": "req-123",
  "conversation_id": "conv-456",
  "message_id": "msg-789",
  "text": "你好"
}
```

不要把完整 Prompt、Token 或敏感用户内容无条件写入日志；应根据审计要求进行脱敏、截断或哈希处理。

### 4.4 客户端断开和取消传播

用户关闭页面、切换会话或网络断开后，服务端应尽快停止模型生成和工具调用，否则仍会消耗 Token、连接和计算资源。异步生成器可以捕获取消异常，并在 `finally` 中清理资源：

```python
import asyncio


async def answer_stream() -> AsyncIterator[str]:
  try:
    async for chunk in agent.stream("你好"):
      yield sse_event("token", {"text": chunk})
  except asyncio.CancelledError:
    await agent.cancel()
    raise
  finally:
    await agent.close_stream()
```

不要吞掉 `CancelledError`。捕获后完成必要清理，再继续抛出，才能让 FastAPI 和 ASGI 服务器知道请求已经被取消。工具调用也要支持超时和取消，否则文本流停止后后台任务仍可能继续运行。

### 4.5 代理服务器缓冲

即使应用每次 `yield` 一个片段，Nginx、网关或云负载均衡器也可能先缓存一批数据，导致客户端无法及时看到首字。生产部署需要检查：

- 代理是否关闭响应缓冲
- 是否正确透传 `Content-Type: text/event-stream`
- 是否使用 HTTP/1.1 或支持流式传输的 HTTP/2 配置
- 是否关闭压缩，或确保压缩不会等待过多数据
- 是否设置合理的上游读取超时

可以在响应中添加常见的 SSE 头：

```python
from fastapi.responses import StreamingResponse


return StreamingResponse(
  answer_stream(),
  media_type="text/event-stream",
  headers={
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
  },
)
```

`X-Accel-Buffering` 主要针对 Nginx，其他代理仍需单独配置。不要只在本地直连 Uvicorn 测试后就认为生产环境一定能够流式返回。

### 4.6 心跳和空闲超时

Agent 可能长时间执行检索或工具调用，没有新的文本片段。中间代理常会把长时间无数据视为连接失效，因此需要定期发送心跳：

```text
: keep-alive

```

以冒号开头的是 SSE 注释事件，客户端通常不会把它当作业务消息，但可以保持连接活跃。心跳间隔应小于代理的空闲超时时间，例如代理 60 秒无数据断开时，可以每 15 到 30 秒发送一次心跳。

同时设置两类超时：

- 首字超时：模型或工具在规定时间内没有产生第一个事件时终止请求。
- 总请求超时：限制一次 Agent 任务的最长执行时间，防止长任务无限占用资源。

超时后发送稳定的 `error` 事件，并记录实际耗时、上游状态和取消原因。

### 4.7 重连、幂等和结果保存

浏览器网络短暂中断后可能重连。SSE 支持 `id` 字段和 `Last-Event-ID`，但模型生成本身不一定能从任意位置安全恢复。生产系统应根据业务选择：

- 短回答：断线后重新请求，并使用 `message_id` 去重。
- 长任务：先把任务放入后台队列，客户端通过 SSE 订阅任务状态。
- 重要结果：边生成边发送，同时在服务端持久化最终答案和执行状态。

重试必须考虑幂等性。特别是 Agent 已经执行过写操作时，客户端重连不能导致重复扣款、重复发货或重复发送通知。

### 4.8 SSE 适用边界

SSE（Server-Sent Events）建立在普通 HTTP 连接之上，是服务端到客户端的单向事件通道。服务端持续发送事件，浏览器可以使用 `EventSource` 接收；客户端发送新消息仍然需要使用普通 HTTP 请求。

#### 适合使用 SSE 的场景

- LLM 文本生成：逐 token 推送回答，降低首字延迟。
- Agent 过程展示：推送思考阶段、工具开始、工具结束和最终结果等状态事件。
- 长任务进度：推送文档解析、批量处理、知识库构建和导出任务的进度。
- 服务端通知：推送任务完成、审核状态变化和后台处理结果。
- 读多写少的实时页面：服务端持续更新，客户端偶尔通过 HTTP 发起操作。

这些场景的共同点是：客户端主要“监听”，服务端主要“推送”，消息频率和数据量通常可控。

#### 需要谨慎使用 SSE 的场景

- 事件需要可靠恢复时，必须设计 `id`、`Last-Event-ID`、事件保存和幂等处理；连接断开后不能假设模型可以从任意 token 继续生成。
- 推送任务可能持续很久时，应让后台任务负责执行，让 SSE 只负责订阅状态，避免 HTTP 请求长期占用模型或工具资源。
- 需要携带自定义认证头时，要确认客户端实现。原生 `EventSource` 对请求配置有限，可能需要 Cookie、短期令牌，或使用支持自定义请求头的 SSE 客户端库。
- 事件量很大或单条消息很大时，应考虑限流、背压、分页或对象存储，不能把 SSE 当作大文件传输协议。

#### 不适合使用 SSE 的场景

- 需要客户端和服务端双向持续通信，例如多人实时协作、在线游戏和实时音视频控制。
- 客户端需要频繁向服务端发送消息，并要求低延迟双向响应。
- 需要传输二进制数据，或需要复杂的连接级协议协商。
- 服务端只需要返回一次结果；此时普通 HTTP 响应更简单。

此时可以选择 WebSocket；一次性结果使用普通 HTTP；简单的低频状态查询则可以使用轮询或短轮询。SSE 与 WebSocket 不是“实时性越强越好”的替代关系，而是通信方向和可靠性需求不同。

#### 选型速查

| 需求 | 推荐方式 | 原因 |
|---|---|---|
| 一次性返回完整结果 | 普通 HTTP | 协议简单，状态和错误处理直观 |
| 服务端持续推送文本或状态 | SSE | 浏览器接入简单，天然支持事件类型和自动重连 |
| 客户端与服务端双向实时通信 | WebSocket | 双向发送，适合高频交互 |
| 低频查询任务状态 | 轮询或短轮询 | 实现和部署成本较低 |
| 长任务执行与实时进度 | 后台任务 + SSE | 执行与连接解耦，断线后可重新订阅 |

#### Agent 系统中的推荐边界

```text
客户端 POST /messages
  -> 服务端创建 message_id 和后台任务
  -> 客户端 GET /messages/{message_id}/events 建立 SSE
  -> SSE 推送 token、tool_start、tool_end、done 或 error
  -> 服务端保存最终答案和执行状态
```

SSE 只负责传递事件，不负责保证业务操作成功。涉及扣款、发货、写数据库或发送通知时，必须在服务端完成最终校验，并使用 `message_id`、幂等键或任务状态防止重连导致重复执行。对于短回答，也可以直接在一次 SSE 请求中生成并发送结果；对于长任务，推荐采用上面的“后台任务 + SSE 订阅”模式。



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

普通文本可以直接把每个文本片段发送给客户端；结构化结果则不能简单地把每个片段当成完整 JSON。模型可能按下面的顺序返回：

```text
{"intent":"query_order","order_id":1001,"confidence":0.98}
   ->  {"intent":"query_
   ->  order","order_id":
   ->  1001,"confidence":0.98}
```

每次收到的内容都可能只是半截 JSON。此时直接执行下面的代码会失败：

```python
json.loads('{"intent":"query_')
# JSONDecodeError
```

因此结构化流式处理通常分为三步：

```text
接收增量片段
  -> 放入缓冲区或增量解析器
  -> 尝试得到当前可用字段
  -> 完成后使用 Pydantic 做最终校验
  -> 向客户端发送字段事件或完整结果
```

### 9.1 方案一：缓冲完整 JSON，再统一校验

这是最简单、最可靠的方案。服务端可以继续把文本片段展示给客户端，但只有在 JSON 完整后才解析：

```python
import json


async def collect_order_intent() -> OrderIntent:
  chunks: list[str] = []

  async for chunk in agent.stream_structured():
    chunks.append(chunk)

  raw_json = "".join(chunks)
  data = json.loads(raw_json)
  return OrderIntent.model_validate(data)
```

执行过程是：

```text
片段 1 -> 加入缓冲区，暂不解析
片段 2 -> 加入缓冲区，暂不解析
片段 3 -> 加入缓冲区，暂不解析
收到完成事件 -> 拼接完整 JSON
          -> json.loads()
          -> OrderIntent.model_validate()
```

适合订单意图识别、分类、数据抽取和工具参数生成等场景。优点是实现简单、容易测试；缺点是客户端必须等完整 JSON 生成后，才能使用结构化字段。

### 9.2 方案二：增量解析并发送字段事件

如果前端需要尽早展示已经生成的字段，可以保留缓冲区，每次收到新片段后使用增量 JSON 解析器尝试解析。不要自己用字符串截取花括号，因为 JSON 可能包含嵌套对象、数组、转义引号和字符串中的花括号。

示意代码如下，`parse_partial_json` 代表支持半截 JSON 的增量解析器：

```python
import json


async def stream_order_intent() -> AsyncIterator[str]:
  buffer = ""
  sent_fields: set[str] = set()

  async for chunk in agent.stream_structured():
    buffer += chunk
    partial_data = parse_partial_json(buffer)

    if partial_data is None:
      continue

    for field_name, field_value in partial_data.items():
      if field_name in sent_fields:
        continue

      sent_fields.add(field_name)
      yield json.dumps(
        {
          "field": field_name,
          "value": field_value,
        },
        ensure_ascii=False,
      )

  result = OrderIntent.model_validate(json.loads(buffer))
  yield json.dumps(
    {"complete": True, "data": result.model_dump()},
    ensure_ascii=False,
  )
```

上面的 `parse_partial_json` 不是 Python 标准库函数，实际项目应选择经过验证的增量 JSON 解析库，或使用模型 SDK 已提供的结构化流式事件。解析器返回的“部分字段”只能用于展示，不能代替最终的 Pydantic 校验。

### 9.3 方案三：使用模型 SDK 的结构化增量事件

一些模型 SDK 不直接返回 JSON 文本片段，而是返回结构化字段增量，例如：

```text
field_delta: intent = "query_order"
field_delta: order_id = 1001
field_delta: confidence = 0.98
completed: true
```

这种方式比解析半截 JSON 更可靠。应用层可以统一转换为自己的事件格式：

```python
async def normalized_structured_stream() -> AsyncIterator[dict[str, object]]:
  async for event in provider_structured_stream():
    if event.type == "field_delta":
      yield {
        "type": "field_delta",
        "field": event.field,
        "value": event.value,
      }
    elif event.type == "completed":
      yield {"type": "completed"}
```

无论使用哪种 SDK，完成事件到达后仍应把完整结果交给 Pydantic：

```python
result = OrderIntent.model_validate(final_data)
```

### 9.4 通过 SSE 向前端发送结构化事件

结构化流不建议把半截 JSON 直接拼进 `data`。可以为不同事件使用不同的 SSE `event` 类型：

```python
async def structured_sse() -> AsyncIterator[str]:
  async for event in normalized_structured_stream():
    yield sse_event(event["type"], event)
```

前端收到的事件可能是：

```text
event: field_delta
data: {"type":"field_delta","field":"intent","value":"query_order"}

event: field_delta
data: {"type":"field_delta","field":"order_id","value":1001}

event: completed
data: {"type":"completed"}
```

前端可以根据 `field` 更新界面；服务端则把最终完整数据保存或交给后续业务逻辑。对于工具调用参数，建议在完整且通过 Pydantic 校验后再执行工具，不要因为某个字段提前出现就立即执行有副作用的操作。

### 9.5 三种方案如何选择

| 方案 | 解析时机 | 优点 | 适用场景 |
|---|---|---|---|
| 缓冲后统一解析 | 完整结果到达后 | 简单、可靠 | 大多数结构化抽取和工具参数 |
| 增量 JSON 解析 | 每个片段到达时 | 可以提前展示字段 | 需要实时展示结构化进度 |
| SDK 结构化事件 | SDK 直接提供字段事件 | 不需要自行处理半截 JSON | 模型和 SDK 明确支持结构化流 |

推荐学习和落地顺序：

```text
文本 Streaming
  -> 完整结果 Structured Output
  -> 缓冲并统一 Pydantic 校验
  -> 增量 JSON 或 SDK 结构化事件
```

核心原则是：**可以增量展示，但必须在最终结果完成后做一次完整校验；未经校验的部分字段不能直接触发写数据库、扣款、发货或发送通知等副作用操作。**

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

## 十二、学习重点回顾

### 12.1 一条主线

```text
普通响应：等待完整结果后一次性返回
流式响应：模型产生片段 -> 异步生成器 yield -> 客户端逐块接收
结构化输出：模型结果 -> JSON 解析 -> Pydantic 校验 -> 业务处理
```

本章的核心不是“把文本拆成很多段”，而是同时处理两件事：

- 让结果更快到达客户端，降低用户感知延迟。
- 让结果具备稳定的数据结构，便于程序可靠消费。

### 12.2 必须掌握的概念

| 概念 | 关键理解 |
|---|---|
| `async for` | 按需向异步数据源请求下一个事件，不会一次性拿到全部结果 |
| `yield` | 交出当前片段并暂停生成器，调用方下一次迭代时继续执行 |
| `StreamingResponse` | 消费异步生成器并将片段持续写入 HTTP 响应 |
| SSE | 服务端到客户端的单向事件通道，以空行分隔事件 |
| Pydantic | 对最终结构化结果做字段、类型、枚举和范围校验 |
| JSON Schema | 用机器可读的方式描述结构，通常由 Pydantic 模型生成 |
| `CancelledError` | 客户端断开时触发，清理资源后必须继续抛出 |

### 12.3 实现时的判断顺序

1. 先确定输出是普通文本，还是需要程序消费的结构化数据。
2. 普通文本使用异步生成器逐块转发，并过滤非文本事件。
3. 需要前端实时接收时使用规范 SSE，数据放在 JSON 的 `data` 字段中。
4. 结构化文本流先缓冲；完整后执行 `json.loads()` 和 `model_validate()`。
5. 只有最终结果通过 Pydantic 校验后，才能执行有副作用的工具或业务操作。
6. 对失败设置有限次数的修复或重试，并区分格式错误、模型错误和业务校验错误。

### 12.4 生产环境检查清单

- 事件是否区分 `token`、工具事件、`done`、`error` 和用量事件？
- 是否包含 `request_id`、`conversation_id` 和 `message_id`？
- 客户端断开后，模型生成和工具调用是否会取消？资源是否在 `finally` 中释放？
- 是否配置首字超时、总请求超时、心跳和代理缓冲策略？
- 是否返回稳定错误码，并避免泄露堆栈、密钥、内部 URL 和敏感 Prompt？
- 重连是否幂等，重要结果是否持久化？
- 是否根据场景选择 SSE 或 WebSocket？

### 12.5 三种结构化流方案

```text
默认选择：缓冲完整 JSON，再统一 Pydantic 校验
需要提前展示字段：增量解析，但展示结果不能直接触发副作用
SDK 原生支持字段事件：优先使用 SDK 事件，完成后仍做最终校验
```

### 12.6 最小复习任务

完成下面的闭环，就基本掌握本章：

```text
模拟 provider_stream()
  -> 过滤 text_delta
  -> 拼接完整答案
  -> 封装为 SSE 事件
  -> 模拟客户端取消
  -> 用 Pydantic 校验订单意图
  -> 分别测试非法 JSON、缺字段、错误枚举和非法范围
```

最后记住三条原则：

1. 流式传输解决的是“结果何时到达”。
2. 结构化输出解决的是“结果能否被程序可靠理解”。
3. 增量内容可以展示，但最终结果必须完整校验，未经校验的数据不能触发副作用。
