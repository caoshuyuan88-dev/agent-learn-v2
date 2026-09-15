# Harness 安全、可靠性与生产治理

## 一、先画信任边界

**来源**：[Symphony Spec §15](https://github.com/openai/symphony/blob/main/SPEC.md)，[Docker Security](https://docs.docker.com/engine/security/)

至少区分五类不可信输入：用户提示、Issue 内容、仓库源码、Tool 返回和外部文档。它们都可能诱导 Agent 执行越权操作。生产系统应明确：Agent 可访问什么、可修改什么、可联网到哪里、何时必须人工确认。

```text
Untrusted Task/Repo -> Harness Policy -> Sandbox/Tool Gateway -> Protected Systems
```

Prompt 只是建议；授权必须在 Tool Gateway、IAM、Sandbox 和网络策略中执行。

## 二、最小权限与密钥隔离

**来源**：[Deep Agents Permissions](https://docs.langchain.com/oss/python/deepagents/permissions)，[GitHub Actions Secure Use](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions)

原则：默认拒绝，显式放行，权限按任务最小化。代码 Agent 不应直接读取 `.env`、云凭据、Docker socket 或生产 DB。Tool 使用服务端受控凭据，Agent 子进程只接收结果。

```python
# 顺序重要：第一条命中即生效
permissions = [
    ("deny", "read", "/workspace/.env"),
    ("allow", "read", "/workspace/**"),
    ("allow", "write", "/workspace/**"),
    ("deny", "read,write", "/**"),
]
```

CI 中 `GITHUB_TOKEN` 默认为只读，需要写权限的 job 单独提升；第三方 Action 固定到完整 commit SHA；不可信 PR 不运行带密钥的 `pull_request_target` 工作流。

## 三、审批与副作用

**来源**：[Deep Agents Production: Guardrails](https://docs.langchain.com/oss/python/deepagents/going-to-production)，[Symphony Spec §10, §15](https://github.com/openai/symphony/blob/main/SPEC.md)

操作分级：

| 风险 | 例子 | 策略 |
|---|---|---|
| 低 | 读源码、跑单测 | 自动允许 |
| 中 | 改代码、装依赖、建分支 | Sandbox + 审计 |
| 高 | 发 PR、修改云资源、发通知 | 人工审批 |
| 禁止 | 读生产密钥、删除生产数据 | 拒绝 |

审批请求必须绑定 `run_id`、操作、参数摘要、影响范围、有效期和审批人；不能只批准“这个 Agent”。

## 四、可靠性：超时、重试、幂等、恢复

**来源**：[Symphony Spec §8, §14](https://github.com/openai/symphony/blob/main/SPEC.md)，[Temporal Idempotency](https://docs.temporal.io/activity-definition)

定义四种时限：API 请求、单 Tool、无事件 stall、Run 总时长。重试前先分类：网络/5xx 可退避重试；4xx、验证失败、权限拒绝、预算超限应停止。

每个外部写入携带稳定幂等键：

```text
key = hash(tenant_id + task_id + step_name + target_id)
```

恢复时不能依据“上次可能没做完”再次写入；先查询幂等记录或下游状态。部分成功则记录补偿状态或转人工。

## 五、观测、SLO 与审计

**来源**：[OpenTelemetry Trace API](https://opentelemetry.io/docs/specs/otel/trace/api/)，[Google SRE Monitoring](https://sre.google/workbook/monitoring/)

每个 Run 建根 Span，Tool、模型、验证、审批、Sandbox 为子 Span。跨队列/远程 Agent 使用 W3C Trace Context 传播。Span 名用低基数操作名，例如 `harness.verify_test`，把 `run_id` 放 attribute，而不是拼到 span 名。

核心指标：

```text
run_completion_rate
verification_pass_rate
repair_success_rate
human_escalation_rate
tool_error_rate
sandbox_violation_count
p95_run_duration
cost_per_completed_task
```

告警使用聚合指标，排障使用 Trace/结构化日志。指标标签不要放高基数 `task_id` 或完整路径。审计记录“谁在何时批准了什么”，但日志必须脱敏并设置保留期。

## 六、上线门禁

**来源**：[GitHub Actions Secure Use](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions)，[SWE-bench](https://github.com/SWE-bench/SWE-bench)

上线前最低检查：威胁建模、Sandbox 逃逸测试、权限拒绝测试、失败重试/重复写入测试、Golden Task 回归、负载和成本上限、告警演练、回滚演练。先在受控内部仓库和非生产凭据中运行，再逐步扩大自主范围。

## 七、验收

- 写出能力-权限-审批矩阵；
- 验证 Agent 无法读取 `.env`、Docker socket 和工作区外文件；
- 模拟 timeout、重复投递、Worker 崩溃、拒绝和补偿；
- 用 Trace 还原一次失败 Run；
- 为完成率、验证通过率、P95 和安全拒绝率设置告警与负责人。
