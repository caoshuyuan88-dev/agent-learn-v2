# Agent Memory 设计与实现

## 一、先区分四种“记忆”

| 类型 | 保存对象 | 生命周期 | 典型实现 |
|---|---|---|---|
| 上下文窗口 | 当前输入和消息 | 一次模型调用 | Prompt / messages |
| 短期记忆 | 单个线程的状态和对话 | 一个 thread | Checkpoint |
| 长期记忆 | 用户偏好、事实、业务资料 | 跨 thread | Store / 数据库 |
| 外部知识 | 可检索文档和证据 | 知识库生命周期 | RAG |

LangGraph 官方将 Checkpointer 用于线程级状态，将 Store 用于跨线程的应用数据。二者不能简单等同于“聊天记录”。

## 二、短期记忆

短期记忆用于多轮对话、人工审批恢复和失败重试：

```python
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, MessagesState, StateGraph


def call_model(state: MessagesState) -> dict:
    return {"messages": [{"role": "assistant", "content": "processed"}]}


builder = StateGraph(MessagesState)
builder.add_node("call_model", call_model)
builder.add_edge(START, "call_model")
graph = builder.compile(checkpointer=InMemorySaver())

config = {"configurable": {"thread_id": "thread-1"}}
graph.invoke({"messages": [{"role": "user", "content": "hello"}]}, config)
```

生产环境应使用持久化 Checkpointer，并设置数据保留和删除策略。

## 三、长期记忆

长期记忆必须绑定用户、租户或组织命名空间，不能把所有用户的事实放在一个共享键空间：

```python
from langgraph.store.memory import InMemoryStore

store = InMemoryStore()
namespace = ("tenant-a", "user-123", "memories")
store.put(namespace, "preferred-language", {"data": "Chinese"})
items = store.search(namespace, query="language preference", limit=3)
```

写入前要明确：

- 什么信息允许保存；
- 谁可以读取；
- 何时过期；
- 用户如何查看、修改和删除；
- 是否需要脱敏或加密。

## 四、记忆写入策略

不要让模型把所有对话自动写入长期记忆。推荐：

```text
识别候选事实
  -> 判断是否稳定、必要且允许保存
  -> 结构化校验
  -> 用户确认或业务策略批准
  -> 写入带版本和时间戳的记忆
```

记忆召回也要有边界：按租户和用户过滤，限制条数和长度，记录召回原因，避免把无关历史全部塞入上下文。

## 五、常见错误

- 把 Checkpoint 当用户画像；
- 把 RAG 文档当个人记忆；
- 不区分租户命名空间；
- 永久保存敏感信息；
- 没有删除和纠错机制；
- 记忆检索结果未经验证就作为事实使用。

## 六、练习

1. 为研发效能 Agent 保存用户的代码语言偏好和报告格式偏好。
2. 将 thread 状态与长期偏好分别存储。
3. 增加用户级删除接口。
4. 写 20 条记忆相关评测：正确召回、错误召回、越权读取和过期数据。

## 资料依据

- [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph Add Memory](https://docs.langchain.com/oss/python/langgraph/add-memory)
