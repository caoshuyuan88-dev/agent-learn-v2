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

### Token 的计算方式

Token 数量不是固定的字符数。模型会使用 tokenizer 把文本切分成 Token，不同模型的 tokenizer 可能不同，因此同一段中文或代码在不同模型中得到的 Token 数也可能不同。

实际计算时可以使用以下公式：

```text
总 Token 预算 = system prompt
            + 历史消息
            + 当前用户输入
            + 工具定义和工具结果
            + 消息格式开销
            + 预留输出 Token
```

例如，模型上下文窗口为 16,000 Token，预留 2,000 Token 作为输出，则输入部分最多使用约 14,000 Token：

```text
可用输入 Token = 16,000 - 2,000 = 14,000
```

#### 方式一：使用模型对应的 tokenizer 精确计算

如果模型供应商提供 tokenizer，应优先使用它计算。以 OpenAI 兼容模型为例，可以使用 `tiktoken`：

```bash
pip install tiktoken
```

```python
import tiktoken


encoder = tiktoken.encoding_for_model("gpt-4o-mini")
text = "请总结这份企业技术文档，并列出三个风险。"
token_count = len(encoder.encode(text))

print(token_count)
```

计算消息列表时，不能只统计 `content` 的字符数，还要统计每条消息的 `role`、消息结构以及工具定义带来的开销。不同 API 对消息格式开销的计算规则可能不同，生产代码应优先使用供应商提供的 Token 统计方法或实际响应中的 `usage` 字段。

#### 方式二：没有 tokenizer 时进行粗略估算

没有对应 tokenizer 时，只能估算，不能把估算值当成精确值。可以先分别统计中文、英文和代码，再预留安全余量：

```text
估算 Token 数 ≈ 中文字符数 × 1.5
              + 英文和数字字符数 ÷ 4
              + 代码、标点和格式开销
```

这是工程上的粗略经验，不适用于所有模型。中文、JSON、代码、URL 和混合文本的 Token 比例差异较大，建议再增加 10% 到 20% 的安全余量，避免接近上下文上限时请求失败。

#### 方式三：读取模型响应中的 usage

大多数模型 API 会在响应中返回实际 Token 使用量，例如：

```python
response = await client.chat.completions.create(
    model="gpt-4o-mini",
    messages=messages,
    max_tokens=2_000,
)

usage = response.usage
print(usage.prompt_tokens)
print(usage.completion_tokens)
print(usage.total_tokens)
```

其中：

- `prompt_tokens`：输入 Token，通常包含消息、工具定义等内容
- `completion_tokens`：模型输出 Token
- `total_tokens`：输入和输出 Token 总数

`usage` 适合记录真实成本和延迟数据，但它发生在请求完成之后，不能用于提前防止超长请求。因此生产系统通常采用“请求前 tokenizer 估算 + 请求后读取 usage”的组合方式。

### Token 预算示例

可以在发送请求前建立预算：

```text
模型上下文窗口：32,000
system prompt：1,000
工具定义：3,000
历史消息：8,000
当前输入：2,000
预留输出：4,000
安全余量：2,000

预计总量 = 1,000 + 3,000 + 8,000 + 2,000 + 4,000 + 2,000
         = 20,000 Token
```

这个请求在 32,000 Token 的上下文窗口内是安全的。如果预计总量超过限制，应按顺序压缩工具结果、截断低相关历史、生成摘要或转移到 RAG，而不是简单地无限提高 `max_tokens`。

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

`top-p` 也叫 nucleus sampling（核采样），控制模型每一步生成下一个 Token 时可以考虑的候选范围。它的取值通常在 `0` 到 `1` 之间，数值越小，候选范围越集中；数值越接近 `1`，候选范围越大。

模型会先按照候选 Token 的预测概率从高到低排序，然后从最高概率开始累加，保留累计概率达到 `top-p` 的最小候选集合，最后只在这个集合中采样：

```text
候选 Token       概率       累计概率
"是"             0.60       0.60
"可以"           0.20       0.80
"通常"           0.10       0.90
"能够"           0.05       0.95
其他             0.05       1.00
```

当 `top-p=0.80` 时，主要在“是”和“可以”这两个候选中采样；当 `top-p=0.95` 时，会纳入更多候选。这里的候选集合会随着上下文和每一步的预测结果动态变化，并不是固定的词表子集。

参数的直观影响：

- `top-p=1.0`：不通过概率截断候选范围，保留全部候选。
- 较低的 `top-p`：输出更集中、更保守，但可能重复、僵硬或遗漏合理表达。
- 较高的 `top-p`：允许更多低概率候选，表达更丰富，但结果波动和偏题风险可能增加。
- `top-p` 不直接限制输出长度，也不代表“只选择前 p 个 Token”；它表示累计概率阈值。

与 `temperature` 的区别：

| 参数 | 调整方式 | 主要影响 |
|---|---|---|
| `temperature` | 改变概率分布的陡峭程度 | 所有候选的相对随机性 |
| `top-p` | 截断低概率候选，再进行采样 | 候选集合的范围 |

可以这样理解：`temperature` 负责“概率分布有多均匀”，`top-p` 负责“哪些候选有资格参加采样”。两者都会影响随机性，因此通常先固定一个参数，只调整另一个，否则很难判断输出变化来自哪里。

推荐调参方式：

1. 先固定 `top-p=1.0`，根据任务调整 `temperature`。
2. 如果仍有明显的低概率跑题内容，再尝试降低 `top-p`。
3. 每次只改变一个参数，并使用固定测试集比较准确率、格式合规率、重复率和人工偏好。

可作为实验起点，但不是通用最优值：

```text
结构化抽取 / 分类 / Tool Calling：top-p=0.8 到 1.0，低 temperature
知识问答：top-p=0.9 到 1.0，低到中等 temperature
创意写作：top-p=0.9 到 1.0，中等 temperature
```

不同模型对采样参数的实现可能存在差异；如果使用模型的确定性模式或 `temperature=0`，也不能保证所有服务商都返回完全相同的结果。最终参数应以目标模型和评测结果为准。

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
