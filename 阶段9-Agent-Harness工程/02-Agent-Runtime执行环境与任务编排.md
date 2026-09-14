# Agent Runtime、执行环境与任务编排

## 一、Runtime 负责什么

Runtime 是 Harness 的运行骨架，通常负责：

- 接收任务和运行上下文；
- 调用模型并解析工具请求；
- 注册和调度 Tool/MCP；
- 管理线程、状态和 Checkpoint；
- 处理超时、重试、取消和中断；
- 运行子 Agent；
- 发出事件和 Trace；
- 控制递归深度、Token、时间和费用预算。

## 二、任务状态模型

```python
from typing import Literal
from typing_extensions import TypedDict


class RunState(TypedDict, total=False):
    run_id: str
    task_id: str
    status: Literal[
        "queued",
        "running",
        "waiting_approval",
        "verifying",
        "repairing",
        "completed",
        "failed",
        "canceled",
    ]
    attempt: int
    workspace: str
    result: str
```

状态机比“让模型自己决定什么时候结束”更可靠。Agent 可以负责提出下一步，但 Runtime 负责限制合法状态转移。

## 三、执行环境

Coding Agent 或数据分析 Agent 通常需要：

```text
Workspace
  ├── source files
  ├── dependencies
  ├── test data
  ├── logs
  └── generated artifacts
```

执行环境需要明确：

- 工作区是否每个任务独立；
- 是否允许网络；
- 是否允许安装依赖；
- 是否允许写入仓库外路径；
- 是否可以访问密钥；
- 任务结束后是否销毁；
- 如何上传输入和下载产物。

生产环境中，涉及代码执行、安装依赖和 Shell 的 Agent 应优先使用隔离 Sandbox，不能默认把宿主机暴露给模型。

## 四、工作区生命周期

```text
创建 workspace
  -> checkout 固定 revision
  -> 注入任务和只读上下文
  -> Agent 修改
  -> 执行验证
  -> 生成 diff / artifact
  -> 保留审计材料
  -> 清理或归档 workspace
```

每个任务应绑定 `workspace_id` 和基线 revision，避免不同任务共享未提交修改。

## 五、任务编排

固定流程适合用 Workflow：

```text
读取需求 -> 修改代码 -> 测试 -> 报告
```

开放式 Coding Agent 可以由 Agent 决定步骤，但 Harness 仍需施加外部约束：

- 最大步骤数；
- 最大工具调用数；
- 最大执行时间；
- 最大 Token 或费用；
- 允许的命令和目录；
- 必须通过的验证门禁。

## 六、事件模型

建议统一记录：

```text
RunStarted
PlanCreated
ToolCallRequested
ToolCallCompleted
FileChanged
TestStarted
TestFinished
ApprovalRequested
CheckpointSaved
RunCompleted
RunFailed
```

事件既用于实时 UI，也用于 Trace、重放和故障分析。

## 七、练习

1. 为 Coding Agent 设计状态机和合法转移表。
2. 实现一个线程安全的任务队列，支持并发上限。
3. 给每个任务创建独立临时目录，并在结束时清理。
4. 加入取消、超时、最大循环次数和人工审批。
5. 设计一份 Run Event JSONL 日志格式。
