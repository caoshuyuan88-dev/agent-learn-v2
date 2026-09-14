# A2A 与 Agent-to-Agent 通信

## 一、A2A 解决什么问题

MCP 主要解决 Agent 如何发现和调用工具、资源与提示；A2A 解决不同框架、不同团队或不同服务之间的 Agent 如何发现能力、委派任务、交换结果并处理长任务。

```text
MCP：Agent -> Tool / Resource / Prompt
A2A ：Agent -> Remote Agent -> Task / Artifact
```

A2A 的核心是让远程 Agent 保持内部实现不透明，调用方只依赖能力描述和任务协议。

## 二、核心对象

| 对象 | 含义 |
|---|---|
| Agent Card | Agent 的身份、能力、接口、认证和 skills 描述 |
| Message | 客户端和远程 Agent 的通信消息 |
| Task | 有状态的任务，包含状态、历史和产物 |
| Artifact | 任务输出，如文本、文件或结构化数据 |
| Part | 消息或产物中的文本、文件或 JSON 数据片段 |
| Context ID | 把多个任务和消息归入同一上下文 |

常见任务状态包括 `submitted`、`working`、`completed`、`failed`、`canceled`、`input-required` 和 `auth-required`。具体名称和序列化格式以当前 A2A 版本规范为准。

## 三、通信方式

- 同步请求/响应：适合短任务；
- SSE 流式：适合实时状态和产物更新；
- Webhook 推送：适合客户端不保持长连接的长任务；
- 轮询：通过任务 ID 查询当前状态。

Webhook 必须做认证、超时、重试和幂等处理，不能把重复通知当成异常情况。

## 四、Agent Card 示例

```json
{
  "name": "Incident Analysis Agent",
  "description": "Analyzes service incidents and produces evidence-based reports.",
  "version": "1.0.0",
  "capabilities": {
    "streaming": true,
    "pushNotifications": true
  },
  "skills": [
    {
      "id": "incident-analysis",
      "name": "Incident Analysis",
      "description": "Analyze logs, metrics, and alerts for service incidents.",
      "tags": ["sre", "incident", "operations"],
      "examples": ["Analyze the payment-api outage from 10:00 to 10:30"]
    }
  ]
}
```

## 五、工程边界

A2A 不会替你解决：

- 远程 Agent 内部的 Tool 权限；
- 任务数据的租户隔离；
- 重复请求造成的副作用；
- 远程 Agent 的质量和安全。

调用方至少要记录 `remote_agent`、`agent_card_version`、`task_id`、`context_id`、认证主体、耗时和最终状态。

## 六、练习

1. 为阶段 4 研发效能 Agent 写一个 Agent Card。
2. 暴露 `POST /message:send` 和 `GET /tasks/{id}` 的最小 FastAPI 服务。
3. 支持 `working -> completed/failed` 状态转换。
4. 增加 `task_id` 去重，重复提交不重复执行。
5. 用一个客户端模拟同步调用、轮询和 Webhook 三种模式。

## 资料依据

- [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/)
- [A2A and MCP](https://a2a-protocol.org/latest/topics/a2a-and-mcp/)
- [A2A Python Tutorial](https://a2a-protocol.org/latest/tutorials/python/)
