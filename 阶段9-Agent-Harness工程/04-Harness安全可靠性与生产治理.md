# Harness 安全、可靠性与生产治理

## 一、Harness 的安全边界

不能依赖模型自己遵守安全规则。安全边界应由 Harness、Tool Gateway、Sandbox 和平台权限强制执行。

重点保护：

- 文件系统和代码仓库；
- API 密钥、OAuth Token 和环境变量；
- 数据库和生产系统；
- 用户数据与租户边界；
- 运行资源、费用和调用配额；
- 生成的补丁、报告和外部通知。

## 二、权限模型

建议将权限分成：

```text
身份认证
  -> 租户 / 用户 / Agent 身份
  -> Tool Scope
  -> Workspace Scope
  -> 文件路径 Scope
  -> 操作级审批
```

示例：

| 操作 | 默认策略 |
|---|---|
| 读取项目源码 | 允许工作区内读取 |
| 修改源码 | 允许但记录 Diff，或需要审批 |
| 执行测试 | 允许沙箱执行 |
| 安装依赖 | 受限，需网络策略 |
| 访问生产数据库 | 默认拒绝 |
| 删除文件 | 默认拒绝或人工审批 |
| 发布 / 发通知 | 人工审批 |

## 三、Sandbox 与密钥

Sandbox 主要解决代码和命令执行隔离，但不是万能安全边界。仍需配置：

- CPU、内存、磁盘和时间限制；
- 网络 allowlist；
- 文件系统挂载范围；
- 进程和系统调用限制；
- 依赖安装策略；
- 输出和日志脱敏。

不要把原始密钥直接写入 Sandbox 环境。优先使用受控的认证代理、短期 Token 或按请求注入。

## 四、可靠性控制

Harness 至少应具备：

- 最大循环次数；
- 最大总执行时间；
- 单工具 Timeout；
- 重试和退避；
- 限流和熔断；
- Checkpoint 和恢复；
- 幂等键；
- 取消和人工接管；
- 失败分类和死信任务。

不要把“自动重试”设计成无限循环。重试只适合临时故障，参数错误、权限错误和业务拒绝应尽快停止。

## 五、生产指标

```text
run_success_rate
run_completion_rate
verification_pass_rate
human_escalation_rate
loop_limit_rate
tool_error_rate
sandbox_failure_rate
p95_run_latency
input_output_tokens
cost_per_completed_task
workspace_cleanup_failure_rate
```

还要按模型、Agent、Skill、工具、租户和任务类型分组，否则平均数会掩盖局部问题。

## 六、审计与隐私

一次 Run 至少能追溯：

```text
谁发起
使用哪个 Agent / Model / Prompt / Skill
访问了哪些文件
调用了哪些工具
修改了什么
执行了哪些验证
谁批准了高风险动作
最终产生了什么结果
```

Trace 中不要默认保存完整 Prompt、源码、Token 或个人信息。应根据敏感级别做脱敏、采样、访问控制和保留期限管理。

## 七、练习

1. 为 Coding Agent 编写权限矩阵。
2. 设计一个 Sandbox 配置清单。
3. 模拟工具超时、Worker 崩溃、重复提交和权限拒绝。
4. 统计 100 次运行的完成率、验证通过率、P95 和成本。
5. 为一次高风险写操作实现审批和审计回放。
