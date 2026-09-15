# Agent Harness 概念与分层架构

## 一、定义与边界

**来源**：[OpenAI Harness Engineering](https://openai.com/index/harness-engineering/)，[Deep Agents Overview](https://docs.langchain.com/oss/python/deepagents/overview)

Harness 是围绕 Agent Loop 建立的工程系统：向 Agent 提供上下文、受控执行环境、可验证反馈、恢复机制和运营控制。它不是模型，不是单个 Tool，也不是只负责画流程图的 Workflow。

```text
Agent Loop：模型决定下一步，调用工具，读取结果
Harness： 为这个循环提供任务、工作区、工具、权限、验证、状态、Trace 与停止规则
```

企业中应区分：

| 层 | 回答的问题 | 典型实现 |
|---|---|---|
| Agent | 下一步做什么 | LLM + Tool Calling |
| Runtime | 一次 Run 如何执行/暂停/恢复 | LangGraph、Deep Agents |
| Harness | Agent 如何在环境中可靠完成任务 | Workspace、Sandbox、验证、反馈、调度 |
| Platform | 如何多租户部署和运营 | K8s、IAM、队列、监控、CI/CD |

## 二、为什么生产环境需要 Harness

**来源**：[OpenAI Symphony Spec §1-3](https://github.com/openai/symphony/blob/main/SPEC.md)，[Anthropic Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)

一个“LLM 调工具”的 Demo 缺少四类生产能力：

1. **任务身份**：任务重复投递时，哪个 Run 可以执行？
2. **环境隔离**：命令、文件、依赖和凭据是否只能在该任务工作区使用？
3. **客观验证**：结果是否通过测试、构建、Schema 或人工审批？
4. **恢复与可追踪**：超时、进程崩溃、取消后如何处理，事后怎样解释？

对 Coding Agent，正确闭环是：

```text
Issue -> 创建工作区 -> 探索/计划 -> 修改 -> test/lint/typecheck
      -> 读取失败 -> 有限修复 -> 生成证据 -> 审批/PR/结束
```

模型的“我已完成”不属于成功条件；验证命令的退出码、报告和审批结果才属于。

## 三、参考架构

**来源**：[Symphony Spec §3](https://github.com/openai/symphony/blob/main/SPEC.md)，[Deep Agents Production](https://docs.langchain.com/oss/python/deepagents/going-to-production)

```text
API / Issue Tracker
  -> Orchestrator: 领取、并发、重试、取消、协调
  -> Workspace Manager: worktree/容器目录、基线 revision、清理
  -> Agent Runner: prompt、session、工具事件、预算
  -> Verification Runner: lint、test、build、e2e、评测
  -> Policy Gateway: IAM、审批、命令/网络/路径限制
  -> Event Store + OTel: 事件、trace、指标、证据
```

边界纪律：Orchestrator 不理解 GitHub/Jira 的私有字段；Adapter 归一化外部任务。Agent 不直接拿生产密钥；受控 Tool 在宿主服务或专用网关执行。验证器不依赖模型文字结论。

## 四、核心状态机

**来源**：[Symphony Spec §7, §14](https://github.com/openai/symphony/blob/main/SPEC.md)

```text
queued -> preparing -> running -> verifying -> completed
                         |            |
                         v            v
                   waiting_approval  repairing -> verifying
                         |
                         v
                   canceled / failed / timed_out
```

需要分别记录 `run_id`、`task_id`、`workspace_id`、`attempt`、`base_revision`。`completed` 只表示验证与交付策略均通过，不代表 Issue 已自动关闭。

## 五、最小数据模型

**来源**：[Symphony Spec §4](https://github.com/openai/symphony/blob/main/SPEC.md)

```python
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Run:
    run_id: str
    task_id: str
    workspace_id: str
    base_revision: str
    attempt: int
    status: Literal["queued", "running", "verifying", "completed", "failed"]
```

`base_revision` 用于证明 Agent 面对的是哪一版源码；`attempt` 区分首次执行和重试；它们都是排障、幂等和审计的基础。

## 六、验收

- 能画出 Agent、Runtime、Harness、Platform 的边界；
- 能为一个代码任务定义状态、终止条件和验证证据；
- 能说明为什么“模型自评成功”不能替代测试；
- 能列出至少三个必须在 Harness 强制、不能只写 Prompt 的规则。
