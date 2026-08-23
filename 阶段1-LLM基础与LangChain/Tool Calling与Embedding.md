# Tool Calling 与 Embedding

## 一、Tool Calling

Tool Calling 是让模型决定调用哪个工具、传入什么参数，但真正执行工具的是你的应用程序：

```text
用户问题
  -> 模型选择工具
  -> 应用校验参数
  -> 应用执行工具
  -> 将结果返回模型
  -> 模型生成最终答案
```

模型不应该直接拥有数据库、网络或文件系统权限。应用必须在服务端完成参数校验、权限判断和执行。

### 工具定义

```python
from pydantic import BaseModel, Field


class SearchOrderInput(BaseModel):
    user_id: int = Field(gt=0)
    limit: int = Field(default=10, ge=1, le=50)
```

工具定义至少应说明：

- 工具名称
- 工具用途
- 参数名称和类型
- 必填参数
- 参数范围
- 是否只读
- 权限要求
- 失败时的返回格式

### 工具调用循环

```python
messages = [user_message]

while True:
    response = await llm.chat(messages, tools=tools)

    if not response.tool_calls:
        return response.text

    for call in response.tool_calls:
        arguments = SearchOrderInput.model_validate(call.arguments)
        result = await execute_tool(call.name, arguments)
        messages.append(response.as_message())
        messages.append(tool_result(call.id, result))
```

必须设置最大循环次数，防止模型反复调用工具。

### 工具安全边界

- 工具参数必须运行时校验
- 工具名称必须使用白名单
- 写操作需要权限检查和人工确认
- SQL 工具禁止任意 SQL
- 限制查询数量、超时和响应大小
- 记录调用者、工具名、参数摘要和结果状态
- 不把密钥或内部错误交给模型

## 二、Embedding

Embedding 是把文本转换成向量：

```text
文本 -> [0.12, -0.31, 0.77, ...]
```

语义相近的文本，通常在向量空间中距离更近。Embedding 常用于：

- 语义搜索
- RAG 检索
- 文档去重
- 相似问题匹配
- 推荐和聚类

Embedding 模型与聊天模型是不同角色，不要把聊天模型的输出当作向量使用。

## 三、向量相似度

常见方法是余弦相似度：

$$
\text{cosine}(a,b)=\frac{a\cdot b}{||a||\ ||b||}
$$

实际项目通常由向量数据库完成索引和相似度查询，不需要手写所有计算。

## 四、Embedding 流程

```text
文档
  -> 清洗
  -> 切分
  -> 生成向量
  -> 保存文本、向量和 metadata
  -> 查询向量
  -> Top-K 检索
  -> 交给模型生成答案
```

metadata 可以包含：

- 文档 ID
- 租户 ID
- 文件名
- 页码
- 权限标签
- 更新时间

权限过滤必须在检索阶段执行，不能只依赖模型自行判断。

## 五、切分与模型版本

切分过大可能召回不精确，切分过小可能丢失上下文。阶段 1 先掌握：

- 按字符或 token 限制大小
- 保留适度 overlap
- 代码和表格使用专门切分策略
- 记录 chunk 来源

Embedding 模型更换后，旧向量和新向量可能不兼容。应记录：

- embedding 模型名称
- 模型版本
- 向量维度
- 距离度量
- 生成时间

## 六、Tool Calling 与 Embedding 的结合

Agent 可以先调用向量检索工具：

```text
用户问题
  -> 模型调用 search_knowledge
  -> 工具执行 embedding 和向量搜索
  -> 返回相关片段及来源
  -> 模型生成带引用答案
```

工具只返回与问题相关的有限片段，不要无条件返回整个知识库。

## 七、学习练习

1. 定义一个订单查询工具参数模型。
2. 实现工具白名单和最大调用次数。
3. 模拟工具成功、参数错误、无权限和超时。
4. 为三段文本生成假的向量并实现相似度排序。
5. 为检索结果添加文档 ID 和页码 metadata。

## 八、验收标准

- 能描述 Tool Calling 的完整循环
- 能区分模型决定调用和应用实际执行
- 能为工具参数定义 Pydantic 模型
- 能设计工具权限、超时、重试和审计
- 能解释 Embedding 和聊天模型的区别
- 能描述文本到向量的 RAG 前置流程
- 能理解 metadata、权限过滤和模型版本的重要性
