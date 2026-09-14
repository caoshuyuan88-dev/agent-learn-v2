# Transformer、Tokenizer 与语言模型基础

## 一、学习目标

- 解释 Transformer 的输入、注意力、前馈网络和残差连接；
- 理解 Tokenizer、词表、Embedding 和上下文长度；
- 区分预训练、推理和微调；
- 能解释模型为什么会有上下文、成本和长度限制。

## 二、Transformer 结构

### 2.1 从文本到下一个 Token

以 Decoder-only 模型为例，一次生成请求大致经过下面的路径：

```text
原始文本
  -> Chat Template
  -> Tokenizer
  -> input_ids: [batch, sequence_length]
  -> Token Embedding
  -> Position Information
  -> Transformer Blocks
  -> hidden_states: [batch, sequence_length, hidden_size]
  -> LM Head
  -> logits: [batch, sequence_length, vocabulary_size]
  -> Softmax / Sampling
  -> 下一个 Token
```

### 2.1.1 每一步在做什么

#### 1. 原始文本

这是用户、系统或工具产生的字符串，例如：

```text
请查询 payment-api 最近 10 分钟的错误率。
```

模型不能直接处理字符串，最终接收的是数字 Tensor，因此必须先经过消息格式化和 Tokenizer。

#### 2. Chat Template

Chat Template 把结构化消息转换成目标模型训练时熟悉的格式。它会表达角色、消息边界、工具调用和结束位置，概念上可能类似：

```text
<system>你是运维助手</system>
<user>请查询 payment-api 最近 10 分钟的错误率。</user>
<assistant>
```

真实格式由具体模型决定。不同模型的角色标记、工具调用标记和结束 Token 可能不同，因此不能随意复用其他模型的模板。

#### 3. Tokenizer

Tokenizer 将格式化后的文本切分成 Token，并把每个 Token 映射成词表中的整数 ID：

```text
文本 -> [Token 片段] -> [整数 ID]
```

例如，下面只是示意，不代表特定模型的真实 ID：

```text
"hello world" -> ["hello", " world"] -> [15339, 1917]
```

Token 不一定等于字、词或字符。英文、中文、代码、JSON 和 URL 的切分方式都可能不同。

#### 4. `input_ids: [batch, sequence_length]`

`input_ids` 是送入模型的整数矩阵，每一行是一条样本，每一列是该样本中的一个 Token：

```text
input_ids.shape = [batch, sequence_length]
```

如果 `batch=2`、每条输入有 128 个 Token，那么形状就是 `[2, 128]`。不同样本长度不一致时，批处理通常用 Padding 补齐，并配合 `attention_mask` 告诉模型哪些位置是真实 Token。

#### 5. Token Embedding

模型维护一个 Embedding 矩阵：

```text
Embedding.shape = [vocabulary_size, hidden_size]
```

每个 Token ID 被用作行索引，查出一个长度为 `hidden_size` 的向量。于是 `input_ids` 的 `[2, 128]` 会变成隐藏状态的 `[2, 128, 4096]`。这一步本质上是查表，不是把整数 ID 当普通数值进行运算。

#### 6. Position Information

Self-Attention 可以同时处理一组 Token，但本身不知道 Token 的先后顺序。Position Information 用来表达“先付款，再发货”和“先发货，再付款”的顺序差异。

早期 Transformer 常使用固定或可学习的位置 Embedding，许多现代 LLM 使用 RoPE 等旋转位置编码。实现方式不同，目标都是让模型感知位置关系。

#### 7. Transformer Blocks

隐藏状态会依次通过多个 Transformer Block。每个 Block 通常包含：

```text
Normalization
  -> Masked Self-Attention：Token 之间交换信息
  -> Residual Add
  -> Feed Forward / MLP：逐位置做非线性变换
  -> Residual Add
```

经过多层处理后，一个 Token 的表示会融合上下文中的语法、语义、代码结构和对话状态。

#### 8. `hidden_states: [batch, sequence_length, hidden_size]`

这是 Transformer 最后一层输出的上下文表示：

```text
hidden_states.shape = [2, 128, 4096]
```

含义是：2 条样本、每条 128 个位置、每个位置用 4096 个浮点数表示。这里的向量包含上下文信息，但还不是词表概率，必须经过 LM Head。

#### 9. LM Head

LM Head 通常是一个从 `hidden_size` 映射到 `vocabulary_size` 的线性层：

```text
[batch, sequence_length, hidden_size]
  -> Linear(hidden_size, vocabulary_size)
  -> [batch, sequence_length, vocabulary_size]
```

它为每一个位置、词表中的每一个候选 Token 生成一个分数。这个分数叫 `logit`，还不是概率。

#### 10. `logits: [batch, sequence_length, vocabulary_size]`

假设 `batch=2`、`sequence_length=128`、`hidden_size=4096`、`vocabulary_size=128000`：

```text
hidden_states.shape = [2, 128, 4096]
logits.shape        = [2, 128, 128000]
```

最后一个维度的 128000 个数字分别对应词表中的 128000 个候选 Token 的分数。

#### 11. Softmax / Sampling

Softmax 将 logits 转成概率分布，然后按照生成策略选择一个 Token：

- Greedy：选择概率最高的 Token；
- Temperature：调整分布的尖锐程度；
- Top-k：只在概率最高的 k 个 Token 中选择；
- Top-p：只在累计概率达到 p 的候选集合中选择。

选择结果会追加到输入序列末尾，模型继续预测下一个 Token，直到产生结束 Token、达到最大输出长度或触发停止条件。

### 2.1.2 这些指标分别是什么意思

| 指标 | 含义 | 主要影响 |
|---|---|---|
| `batch` / `batch_size` | 一次并行处理多少条样本或请求 | 吞吐、显存、并发能力 |
| `sequence_length` | 每条样本包含多少个 Token | 上下文容量、Attention 计算量、KV Cache |
| `hidden_size` | 每个 Token 的内部向量维度 | 表示能力、参数量、矩阵计算量 |
| `vocabulary_size` | 模型词表中候选 Token 的数量 | Embedding/LM Head 参数量和 logits 大小 |
| `num_heads` | Multi-Head Attention 的头数 | 注意力表示子空间数量 |
| `head_size` | 每个注意力头的维度，通常为 `hidden_size / num_heads` | 单头计算规模 |

可以这样区分：

```text
batch             = 同时处理几条样本
sequence_length   = 每条样本有多长
hidden_size       = 每个 Token 表示得多宽
vocabulary_size   = 每个位置有多少个候选 Token
```

### 2.1.3 为什么示例是 `[2, 128, 128000]`

```text
[2, 128, 128000]
 |   |      |
 |   |      +-- 每个位置对 128000 个候选 Token 打分
 |   +--------- 每条输入有 128 个 Token 位置
 +------------- 同时处理 2 条输入
```

这个 logits Tensor 包含：

$$
2\times128\times128000=32,768,000
$$

个标量。如果使用 FP16，每个标量占 2 bytes，仅这一块数据就约为 62.5 MiB；这还没有计算模型权重、Attention 中间结果、KV Cache 和其他临时 Tensor。

### 2.1.4 为什么生成时只取最后一个位置

假设输入是：

```text
[我, 喜欢, 学习]
```

训练时可以同时学习：

```text
我     -> 喜欢
喜欢   -> 学习
学习   -> Python
```

所以训练会使用所有位置的 logits。

生成时真正要做的是根据完整上下文预测下一个 Token，因此通常只取最后一个位置：

```python
next_token_logits = logits[:, -1, :]
```

形状从 `[batch, sequence_length, vocabulary_size]` 变成 `[batch, vocabulary_size]`。选择并追加 Token 后，再进入下一轮生成；KV Cache 会帮助后续轮次避免重复计算全部历史 Key/Value。

### 2.2 Embedding 与隐藏状态

Tokenizer 输出的是整数 Token ID，整数本身没有语义。Embedding 矩阵把每个 ID 映射成连续向量：

```text
Token ID 42 -> Embedding[42] -> [0.12, -0.08, ...]
```

如果词表大小为 $V$、隐藏维度为 $d$，Embedding 矩阵的形状就是 $[V,d]$，参数量为 $V\times d$。许多 Decoder-only 模型会让输入 Embedding 和输出 LM Head 共享权重，但这不是所有模型都强制采用的设计。

### 2.3 Transformer Block

典型 Decoder-only LLM 的数据流：

```text
文本
  -> Tokenizer
  -> token ids
  -> Embedding + Position Information
  -> Masked Self-Attention
  -> Feed Forward
  -> Residual + Normalization
  -> 重复多个 Transformer Block
  -> LM Head
  -> 下一个 Token 概率
```

### 2.3.1 Transformer Block 的输入和输出

设输入隐藏状态为：

```text
X.shape = [batch, sequence_length, hidden_size]
```

例如：

```text
X.shape = [2, 128, 4096]
```

它表示同时处理 2 条样本，每条样本有 128 个 Token，每个 Token 当前用 4096 维向量表示。一个 Transformer Block 不会改变这三个主要维度，通常仍然输出：

```text
output.shape = [2, 128, 4096]
```

Block 的作用不是改变序列长度，而是不断更新每个位置的表示，让它融合越来越丰富的上下文信息。

### 2.3.2 第一步：Normalization

```text
x -> Norm(x)
```

Normalization 对每个 Token 的隐藏向量做尺度调整，让不同层、不同样本之间的数值范围更稳定。常见实现有 LayerNorm 和 RMSNorm。

它主要解决的是优化稳定性问题：如果某些层的激活值越来越大或分布剧烈变化，后续矩阵乘法和 Softmax 可能变得难以训练。Normalization 不负责理解语义，也不会增加序列信息。

Pre-Norm 结构通常写成：

$$
h=x+Attention(Norm(x))
$$

### 2.3.3 第二步：Masked Self-Attention

这一层让序列中的 Token 互相读取信息。例如：

```text
“小明因为下雨带了雨伞”
```

“雨伞”这个位置可以关注“下雨”，从而获得更完整的语义表示。在 Decoder-only 模型中，第 $i$ 个位置只能读取位置 $0$ 到 $i$，不能读取未来 Token。

Self-Attention 的输出形状仍然是：

```text
[batch, sequence_length, hidden_size]
```

但每个位置的向量已经不再只代表当前 Token，而是融合了允许访问的上下文。

### 2.3.4 第三步：Residual Add

```text
x -> Attention(Norm(x)) -> 与原始 x 相加
```

形式为：

$$
h=x+Attention(Norm(x))
$$

残差连接有两个重要作用：

- 保留原始表示，避免每一层都必须重新学习全部信息；
- 为梯度提供更直接的传播路径，使很多层 Transformer 更容易训练。

可以把 Attention 理解为“对原始表示做一次上下文相关的增量更新”，而不是完全替换原始表示。

### 2.3.5 第四步：第二次 Normalization

Attention 的结果和原始输入相加后，再进行一次归一化，准备交给 MLP：

```text
h -> Norm(h)
```

此时每个位置已经拥有上下文信息，但仍需要进一步进行非线性变换。

### 2.3.6 第五步：Feed Forward / MLP

```text
h -> MLP(Norm(h))
```

Attention 主要负责“Token 之间交换信息”，MLP 主要负责“对每个位置的表示进行加工”。MLP 通常先把维度扩大，再经过激活函数，最后投影回 `hidden_size`：

$$
MLP(x)=W_2\,\sigma(W_1x)
$$

例如，输入维度为 4096，MLP 中间维度可能是 11008 或更大，最终再映射回 4096。MLP 对每个位置独立计算，不直接让不同 Token 互相通信。

现代模型经常使用 SwiGLU 等门控结构，具体公式可能不同，但共同点是：通过非线性变换提高表示能力。

### 2.3.7 第六步：第二次 Residual Add

```text
output = h + MLP(Norm(h))
```

最终输出仍然是：

```text
[batch, sequence_length, hidden_size]
```

多个 Transformer Block 堆叠后，最后一层输出再交给 LM Head，转换成词表中每个候选 Token 的 logits。

### 2.3.8 一句话理解 Transformer Block

```text
Attention：让不同 Token 交换上下文信息
MLP：      对每个 Token 的表示做非线性加工
Residual： 保留旧信息并学习增量
Norm：     稳定数值分布和训练过程
```

Self-Attention 的基本形式为：

$$
Attention(Q,K,V)=softmax\left(\frac{QK^T}{\sqrt{d_k}}+M\right)V
$$

其中 $M$ 在 Decoder-only 模型中用于屏蔽未来 Token。多头注意力让模型在不同表示子空间中捕捉不同关系。

### 2.3.9 自注意力公式逐项解释

公式：

$$
Attention(Q,K,V)=softmax\left(\frac{QK^T}{\sqrt{d_k}}+M\right)V
$$

可以把它理解为：**每个位置先计算自己应该关注序列中哪些位置，再按照关注程度对这些位置的信息加权求和。**

#### 第 1 步：生成 Q、K、V

给定输入隐藏状态 $X$，通过三个不同的线性层生成：

$$
Q=XW_Q,\quad K=XW_K,\quad V=XW_V
$$

- $Q$，Query：当前位置正在寻找什么信息；
- $K$，Key：每个位置具有什么可匹配的特征；
- $V$，Value：匹配后真正读取的内容。

这三个向量都来自同一个输入 $X$，所以叫 Self-Attention。若 Query 来自一个序列、Key/Value 来自另一个序列，则属于 Cross-Attention。

#### 第 2 步：计算匹配分数 $QK^T$

Query 和 Key 做点积：

$$
score_{ij}=q_i\cdot k_j
$$

其中 $score_{ij}$ 表示第 $i$ 个位置对第 $j$ 个位置的匹配程度：

- 分数较大：第 $i$ 个位置更可能关注第 $j$ 个位置；
- 分数较小：第 $i$ 个位置较少读取第 $j$ 个位置。

如果序列长度是 $S$，则会得到一个 $[S,S]$ 的分数矩阵：

```text
             被关注的位置 j
             0      1      2      3
当前位置 i 0  score  score  score  score
          1  score  score  score  score
          2  score  score  score  score
          3  score  score  score  score
```

对整个 batch 和多个头来说，形状通常是：

```text
[batch, num_heads, sequence_length, sequence_length]
```

#### 第 3 步：除以 $\sqrt{d_k}$

公式中的缩放是：

$$
\frac{QK^T}{\sqrt{d_k}}
$$

当 Key/Query 维度 $d_k$ 变大时，点积的绝对值通常也会变大。如果不缩放，Softmax 输入可能过大，导致概率几乎变成“一边倒”：最大值接近 1，其他值接近 0，梯度变得很小。

除以 $\sqrt{d_k}$ 可以让分数维持更合适的数值范围，帮助训练稳定。

#### 第 4 步：加入 Mask $M$

在 Decoder-only 模型中，当前位置不能偷看未来 Token。Causal Mask 通常写成：

```text
允许读取 = 0
禁止读取 = -inf
```

例如长度为 4 的序列，其 Mask 效果类似：

```text
             位置 0  位置 1  位置 2  位置 3
位置 0          0    -inf    -inf    -inf
位置 1          0      0     -inf    -inf
位置 2          0      0       0     -inf
位置 3          0      0       0       0
```

加上 Mask 后，未来位置经过 Softmax 会得到接近 0 的权重。这样训练“预测下一个 Token”时，模型不能直接看到正确答案。

Padding Mask 是另一种 Mask：它屏蔽的是补齐位置。Causal Mask 防止读取未来，Padding Mask 防止读取无效填充，两者作用不同，有时需要同时使用。

#### 第 5 步：Softmax 变成注意力权重

对每个当前位置的分数做 Softmax：

$$
\alpha_{ij}=softmax_j(score_{ij})
$$

Softmax 后，同一个 Query 对所有 Key 的权重之和为 1：

```text
[0.05, 0.70, 0.25] -> 权重总和为 1
```

这些权重不是最终输出，而是“从每个位置读取多少信息”的比例。

#### 第 6 步：对 V 加权求和

最后将注意力权重乘以 Value：

$$
output_i=\sum_j\alpha_{ij}v_j
$$

如果当前位置对第 2 个位置的权重最高，那么输出向量就会更多地包含第 2 个位置的 Value 信息。整个过程类似：

```text
匹配谁 -> 计算关注比例 -> 按比例汇总信息
QK^T   -> Softmax      -> 权重 × V
```

### 2.3.10 一个极小的数值直觉例子

假设某个位置经过 Mask 后的分数是：

```text
[2.0, 1.0, -inf]
```

第三个位置是未来 Token，被 Mask。Softmax 后大致得到：

```text
[0.73, 0.27, 0.00]
```

如果对应的 Value 是 $v_0,v_1,v_2$，输出就是：

$$
0.73v_0+0.27v_1+0.00v_2
$$

这说明当前位置主要读取第 0 个位置的信息，同时少量读取第 1 个位置的信息，完全不读取未来的第 2 个位置。

一个简化的 Transformer Block 可以表示为：

```text
x
 -> Norm
 -> Self-Attention
 -> Residual Add
 -> Norm
 -> Feed Forward / MLP
 -> Residual Add
 -> output
```

现代模型常见 Pre-Norm 结构，即先做 LayerNorm/RMSNorm，再进入 Attention 或 MLP。残差连接让每一层只需要学习对已有表示的增量更新，改善深层网络的优化稳定性。

### 2.4 Q、K、V 的直观含义

给定输入隐藏状态 $X$，模型通过不同的线性投影得到：

$$
Q=XW_Q,\quad K=XW_K,\quad V=XW_V
$$

- Query：当前位置想寻找什么信息；
- Key：每个位置可以被什么特征匹配；
- Value：匹配成功后真正取回的内容。

$QK^T$ 计算位置之间的相关性，除以 $\sqrt{d_k}$ 是为了控制数值尺度，避免 Softmax 过早饱和。Causal Mask 将未来位置的分数设为负无穷，使当前位置不能读取未来 Token。

如果序列长度为 $S$、注意力头数为 $H$、每个头的维度为 $d_h$，注意力分数矩阵大致包含 $H\times S\times S$ 个元素。这解释了为什么标准 Self-Attention 对长上下文的计算和显存压力会快速增加。

### 2.5 Multi-Head Attention

单个注意力头只能在一个表示子空间中建立关系。Multi-Head Attention 将隐藏维度拆成多个头，每个头独立计算注意力，再拼接并投影：

```text
hidden_states
  -> split into H heads
  -> attention per head
  -> concatenate
  -> output projection
```

不同头可能分别关注：

- 近距离语法关系；
- 长距离指代关系；
- 代码括号或结构边界；
- 对话角色和格式标记。

这些解释是帮助理解的工程直觉，不应当把每个注意力头简单等同于一个固定的人类语义功能。

### 2.6 Feed Forward / MLP

Attention 主要负责 Token 之间的信息交互，MLP 负责对每个位置的表示做非线性变换。典型形式是：

$$
MLP(x)=W_2\,\sigma(W_1x)
$$

现代模型常使用 SwiGLU 等门控结构。MLP 的中间维度通常大于隐藏维度，因此它也是模型参数量的重要来源。

## 三、Tokenizer

### 3.1 为什么不直接按字符或单词切分

纯字符切分会导致序列过长，纯单词切分又难以覆盖新词、代码、拼写变化和多语言文本。现代 Tokenizer 通常使用 BPE、WordPiece、Unigram 等子词方法，在词表大小和序列长度之间做折中。

以子词 Tokenizer 为例：

```text
unhappiness -> un + happiness
payment_api -> payment + _ + api
```

实际切分结果取决于具体模型的词表和算法，不能跨模型假设 Token ID 或切分结果相同。

### 3.2 Tokenizer 的组成

- Vocabulary：Token 到整数 ID 的映射；
- Merge Rules：子词合并规则，常见于 BPE；
- Special Tokens：BOS、EOS、PAD、UNK、角色标记等；
- Chat Template：把 system/user/assistant/tool 消息转换为模型训练格式。

同一段消息，如果 Chat Template 不一致，模型看到的序列就可能完全不同。做微调时，训练数据格式必须和推理时使用的模板一致，否则会出现“训练 Loss 正常、线上行为异常”。

### 3.3 Token 数、成本与上下文

模型计费和上下文限制通常以 Token 为单位。一个粗略的工程估算流程是：

```text
输入字符数
  -> 使用目标模型 Tokenizer 实测
  -> 加上 system prompt、工具 schema、历史消息
  -> 预留输出 Token
  -> 判断是否接近上下文上限
```

不能用“中文字符数约等于 Token 数”这类固定比例作为生产逻辑。代码、JSON、URL、表格和中英文混合文本的 Token 比例可能差异很大。

### 3.4 Padding 与 Attention Mask

批量训练时，不同样本长度通常需要 Padding 到同一长度：

```text
sample A: [t1, t2, t3, PAD, PAD]
sample B: [t1, t2, t3, t4, t5]
```

Padding Token 不应参与 Attention 和 Loss，因此需要：

- `attention_mask`：告诉模型哪些位置是真实输入；
- label mask：通常将 Padding 或不参与训练的位置设为 `-100`，让交叉熵忽略它们。

### 3.5 Chat Template 与工具调用

工具调用并不是模型天然理解的 Python 函数调用，而是训练格式、特殊 Token、工具 schema 和运行时解析共同构成的协议：

```text
messages
  -> chat template
  -> model emits tool-call structure
  -> runtime parses arguments
  -> tool executes
  -> tool result converted back to messages
```

因此微调 Tool Calling 模型时，必须保留真实的工具消息格式、工具名、参数 schema 和错误恢复样本。

Tokenizer 把字符串映射成模型词表中的 Token。一个中文词、英文单词、标点或代码片段都可能被拆成不同数量的 Token，因此：

- Token 数决定输入和输出成本；
- 上下文窗口限制的是 Token，不是字符数；
- 训练和推理必须使用匹配的 Tokenizer；
- 特殊 Token 用于区分系统消息、用户消息、结束标记等。

## 四、训练目标

### 4.1 Causal Language Modeling

Decoder-only 模型通常使用因果语言建模：给定前面的 Token，预测下一个 Token。

$$
\mathcal{L}=-\sum_{t=1}^{T}\log p(x_t|x_{<t})
$$

预训练学习通用语言和知识；SFT 学习任务格式和行为；偏好优化进一步调整输出偏好。

训练时通常将目标序列右移一位：

```text
输入:  [我, 喜欢, 学习, Python]
标签:  [喜欢, 学习, Python, <eos>]
```

模型在每个位置预测下一个 Token，交叉熵将预测分布与真实标签进行比较。推理时则没有真实标签，模型根据当前分布选择下一个 Token，再把新 Token 拼回上下文继续生成。

### 4.2 Logits、概率与采样

模型输出的 logits 不是概率。经过 Softmax 后才得到词表分布：

$$
p_i=\frac{e^{z_i/T}}{\sum_j e^{z_j/T}}
$$

其中 $T$ 是 temperature：

- $T<1$：分布更尖锐，输出更确定；
- $T=1$：保持原始分布尺度；
- $T>1$：分布更平坦，随机性更高。

实际生成还可能使用 Top-k、Top-p、重复惩罚和停止 Token。结构化输出和工具调用场景通常应优先保证格式可靠性，而不是盲目提高随机性。

### 4.3 训练、验证、推理的区别

| 阶段 | 是否计算梯度 | 是否使用标签 | 目标 |
|---|---:|---:|---|
| 训练 | 是 | 是 | 更新参数或适配器 |
| 验证 | 否 | 是 | 观察泛化和过拟合 |
| 推理 | 否 | 否 | 根据分布生成结果 |

推理时使用 `model.eval()` 只是关闭 Dropout 等训练行为，不等于模型变聪明；生成质量主要取决于模型、输入格式、采样参数和运行时约束。

## 五、必须掌握的工程概念

### 5.1 Batch、Sequence 与显存

#### 5.1.1 三个量分别是什么

```text
batch_size       = 一次并行处理多少条样本
sequence_length  = 每条样本包含多少个 Token
hidden_size      = 每个 Token 的隐藏向量有多少个数值
```

例如：

```text
batch_size = 2
sequence_length = 128
hidden_size = 4096
```

输入 Token ID 的形状是：

```text
[2, 128]
```

经过 Embedding 后，隐藏状态的形状是：

```text
[2, 128, 4096]
```

也就是同时处理 2 条序列，每条序列有 128 个 Token，每个 Token 用 4096 个数表示。

#### 5.1.2 Batch Size 的作用

`batch_size` 表示一次前向计算同时放入多少条样本。增大它通常可以提高 GPU 利用率和训练吞吐，但会增加显存：

```text
batch_size = 1  -> 一次处理 1 条样本
batch_size = 8  -> 一次处理 8 条样本
```

在训练中，Batch Size 影响梯度估计：

- 较大的 Batch：梯度更平滑，吞吐可能更高，但显存需求更大；
- 较小的 Batch：显存压力较低，但梯度噪声更大，训练可能更不稳定；
- 过大的 Batch：不一定带来更好的效果，可能需要重新调整学习率和训练步数。

在推理服务中，Batch 还表示同时处理多少个请求。动态 Batch 或 Continuous Batching 可以把不同请求合并，提高吞吐，但会增加排队和调度复杂度。

#### 5.1.3 Sequence Length 的作用

`sequence_length` 是一条样本中的 Token 数，不是字符数，也不是模型层数：

```text
"请查询订单状态" -> 可能是若干个 Token
```

实际长度由目标模型的 Tokenizer 决定。Sequence Length 影响：

- 能放入多少上下文；
- Attention 的计算量；
- 训练激活值大小；
- 推理时 KV Cache 的大小；
- 输入 Token 成本和首 Token 延迟。

标准 Self-Attention 会产生大致为 $S\times S$ 的注意力分数矩阵，其中 $S$ 是序列长度。因此：

```text
sequence_length 从 1,000 增加到 2,000
Token 数约增加 2 倍
Attention 分数矩阵约增加 4 倍
```

这就是长上下文显存和计算压力增长很快的主要原因之一。实际模型可能使用滑动窗口、稀疏注意力、Paged Attention 或其他优化，不能简单地把所有模型都视为标准全量 Attention。

#### 5.1.4 Hidden Size 的作用

`hidden_size` 是每个 Token 的内部表示宽度。它越大，单个 Token 能携带的表示维度通常越丰富，但矩阵乘法、参数量和显存也会增加。

若隐藏状态形状为 `[B, S, H]`，其元素数量为：

$$
B\times S\times H
$$

例如：

$$
2\times128\times4096=1,048,576
$$

如果使用 FP16，每个元素约占 2 bytes，这一份隐藏状态约占 2 MiB。实际运行中，每一层还会产生 Q、K、V、MLP 中间结果、残差和反向传播所需的保存值。

#### 5.1.5 显存到底存了什么

训练和推理的显存构成不同。

训练时通常包括：

```text
模型权重
+ 梯度
+ Optimizer States，例如 Adam 的一阶和二阶动量
+ 前向激活值
+ Attention / MLP 临时张量
+ CUDA 工作区和通信缓冲区
```

推理时通常不保存梯度和优化器状态，但仍需要：

```text
模型权重
+ KV Cache
+ 当前请求的隐藏状态和临时张量
+ Batch 中其他请求的中间数据
```

因此，同一个模型“能推理”不代表“能训练”。训练通常需要远多于权重本身的显存。

#### 5.1.6 一个粗略例子

假设：

```text
batch_size = 4
sequence_length = 2048
hidden_size = 4096
```

仅一个 `[B, S, H]` 隐藏状态的元素数量就是：

$$
4\times2048\times4096=33,554,432
$$

若使用 FP16，仅这一份 Tensor 约占 64 MiB。但一个 Transformer 有很多层，每层可能同时保留多个激活和中间结果，因此不能用这一个数字代表总显存。

#### 5.1.7 Batch 与 Sequence 的权衡

在固定显存下，通常存在这样的取舍：

```text
增大 batch_size       -> 吞吐增加，但并发显存增加
增大 sequence_length  -> 上下文变长，但 Attention 和激活开销增加
减小 batch_size       -> 可以容纳更长序列，但吞吐下降
```

训练时常见策略是：

- 减小物理 Batch Size；
- 使用 Gradient Accumulation 保持较大的有效 Batch；
- 使用混合精度；
- 使用 Gradient Checkpointing 减少激活保存；
- 按 Token 数而不是样本条数控制 Batch；
- 使用 LoRA/QLoRA 减少可训练参数和优化器状态。

推理时常见策略是：

- 限制最大输入和输出长度；
- 对长上下文做摘要或检索裁剪；
- 使用 Continuous Batching；
- 使用量化和高效 KV Cache 管理；
- 区分 TTFT 和 Decode 阶段优化。

训练显存不只包含模型权重，还包含梯度、优化器状态和激活值：

```text
训练显存
≈ 参数权重
 + 梯度
 + Optimizer States
 + Activations
 + 临时张量
```

增加 `batch_size` 会增加吞吐，但也会增加显存；增加 `sequence_length` 不仅增加 Token 数，还会显著增加 Attention 相关开销。显存不足时可以考虑 Gradient Accumulation、梯度检查点、混合精度、缩短序列或 LoRA/QLoRA，但每种方法都有吞吐或精度代价。

### 5.2 Gradient Accumulation

当显存只能容纳小批次时，可以多次计算小批次梯度，在累积若干步后再更新参数：

```text
micro_batch 1 -> backward
micro_batch 2 -> backward
micro_batch 3 -> backward
micro_batch 4 -> optimizer.step()
```

有效 Batch Size 近似为：

$$
effective\_batch=batch\_size\times gradient\_accumulation\_steps\times data\_parallel\_world\_size
$$

梯度累积不等于真正扩大单次前向的序列长度，LayerNorm、BatchNorm 和随机性相关行为也可能存在差异。

### 5.3 Loss、Perplexity 与过拟合

Perplexity 常定义为平均交叉熵的指数：

$$
PPL=\exp\left(-\frac{1}{T}\sum_{t=1}^{T}\log p(x_t|x_{<t})\right)
$$

它更适合比较相同 Tokenizer、相近数据分布下的语言建模表现。不能直接用不同 Tokenizer、不同领域数据的 PPL 做简单横向结论。Agent 任务最终仍需看工具准确率、任务完成率和安全指标。

### 5.4 KV Cache、Prefill 与 Decode

推理通常分为：

- Prefill：一次性处理已有输入上下文；
- Decode：逐个生成输出 Token。

为了避免每生成一个 Token 都重新计算整个历史上下文，模型会缓存历史 Key/Value，这就是 KV Cache。长输入主要增加 Prefill 成本和 KV Cache 占用；长输出主要增加 Decode 时间。

因此应分别观测：

```text
TTFT = 请求开始 -> 第一个 Token
ITL  = 相邻输出 Token 之间的时间
E2E  = 请求开始 -> 最后一个 Token
```

### 5.5 参数量与显存的粗略估算

仅保存权重时，显存可以粗略估算为：

```text
weight_memory ~= parameter_count * bytes_per_parameter
```

但训练时还要加梯度、优化器状态和激活值；推理时还要加 KV Cache、批处理和运行时临时空间。因此“模型参数量乘以 2 字节”只能作为权重下界，不能直接当作 GPU 选型结果。

- Batch size、Gradient Accumulation、Learning Rate；
- Loss、Perplexity 与过拟合；
- FP32、FP16、BF16；
- KV Cache、Prefill、Decode、吞吐和 TTFT；
- Context Window、RoPE 或其他位置编码；
- 参数量、显存和序列长度之间的关系。

## 六、练习

1. 使用 Tokenizer 统计同一问题在中文、英文和代码输入下的 Token 数。
2. 画出一个 Decoder-only Transformer Block 的数据流。
3. 解释为什么增加上下文长度会影响显存和延迟。
4. 对比 base model、instruct model 和 embedding model 的用途。

5. 使用 PyTorch 手写一个极小的 causal self-attention，验证未来位置的 attention score 被 Mask。
6. 打印一个 batch 的 `input_ids`、`attention_mask`、logits 和 labels 形状，并说明每个维度含义。
7. 固定 Prompt，分别测试 temperature、Top-k 和 Top-p 对结构化输出合法率的影响。
8. 估算不同序列长度和 batch size 下的权重、激活和 KV Cache 增长趋势。

## 七、最小实践：Causal Self-Attention

下面的代码只用于理解张量形状和因果 Mask，不是生产实现，也不包含完整 Transformer Block：

```python
import torch
from torch import nn


class CausalSelfAttention(nn.Module):
  def __init__(self, hidden_size: int, num_heads: int) -> None:
    super().__init__()
    if hidden_size % num_heads != 0:
      raise ValueError("hidden_size must be divisible by num_heads")
    self.num_heads = num_heads
    self.head_size = hidden_size // num_heads
    self.qkv = nn.Linear(hidden_size, hidden_size * 3)
    self.output = nn.Linear(hidden_size, hidden_size)

  def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
    batch_size, sequence_length, hidden_size = hidden_states.shape
    qkv = self.qkv(hidden_states)
    qkv = qkv.view(
      batch_size,
      sequence_length,
      3,
      self.num_heads,
      self.head_size,
    )
    qkv = qkv.permute(2, 0, 3, 1, 4)
    query, key, value = qkv.unbind(0)

    scores = query @ key.transpose(-2, -1)
    scores = scores / (self.head_size ** 0.5)
    causal_mask = torch.triu(
      torch.ones(sequence_length, sequence_length, dtype=torch.bool),
      diagonal=1,
    )
    scores = scores.masked_fill(causal_mask, float("-inf"))
    weights = torch.softmax(scores, dim=-1)
    context = weights @ value
    context = context.transpose(1, 2).contiguous()
    context = context.view(batch_size, sequence_length, hidden_size)
    return self.output(context)


layer = CausalSelfAttention(hidden_size=64, num_heads=4)
hidden_states = torch.randn(2, 8, 64)
output = layer(hidden_states)
print(output.shape)  # torch.Size([2, 8, 64])
```

需要验证：

- `scores` 的形状是 `[batch, heads, sequence, sequence]`；
- 第 $i$ 个位置不能读取大于 $i$ 的位置；
- 多头拼接后回到 `[batch, sequence, hidden_size]`；
- 增大序列长度会使 score 矩阵按平方增长。

## 八、学习验收

完成本篇后，应该能回答：

1. 为什么 Decoder-only 模型需要 Causal Mask？
2. 为什么 Tokenizer 变化会影响训练、推理和成本？
3. 为什么训练显存远大于权重显存？
4. 为什么长输入影响 TTFT，长输出影响 Decode 时间？
5. 为什么 Tool Calling 模型不能只用普通问答数据训练？
6. 为什么 PPL 下降不一定代表 Agent 任务完成率提高？
7. 为什么量化、RAG、Prompt 优化和微调应该通过统一评测比较？

## 资料依据

- [Transformers Documentation](https://huggingface.co/docs/transformers/index)
- [The Annotated Transformer](https://nlp.seas.harvard.edu/annotated-transformer/)
- [Attention Is All You Need](https://arxiv.org/abs/1706.03762)
