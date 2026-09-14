# 阶段 9 综合实践：可验证的 Coding Agent Harness

## 一、项目目标

构建一个最小 Coding Agent Harness，让 Agent 接收 GitHub Issue 或自然语言任务，在隔离工作区中修改代码，并通过自动验证和反馈循环交付结果。

## 二、目标流程

```text
Issue / Task
  -> 创建隔离 Workspace
  -> 读取仓库地图、规范和 Skill
  -> Agent 规划
  -> 修改代码
  -> 运行测试 / Lint / 类型检查
  -> 读取失败反馈
  -> 修复并重试
  -> 生成 Diff、测试证据和 Trace
  -> 人工审批或完成交付
```

## 三、里程碑

### M1：任务与工作区

- 定义 `Task`、`Run`、`Workspace` 数据模型；
- 为每个任务固定 Git revision；
- 支持状态、取消、超时和清理；
- 记录 `run_id`、`task_id`、`workspace_id`。

### M2：Agent Loop

- 接入一个模型和只读/写入工具；
- 加入 Skill 和仓库知识地图；
- 限制工具、Token、时间和循环次数；
- 记录 Tool Call 和文件 Diff。

### M3：验证反馈

- 自动运行格式化、类型检查和测试；
- 将失败输出结构化后返回 Agent；
- 支持最多 N 轮修复；
- 通过后生成验证证据。

### M4：安全治理

- Workspace 路径隔离；
- Shell 通过 Sandbox 或 allowlist；
- 写文件、删除、发布和通知支持审批；
- 禁止访问 `.env`、密钥和工作区外路径；
- 记录完整审计事件。

### M5：观测与评测

准备至少 20 个任务：

- 10 个可通过测试验证的修复任务；
- 3 个需要多文件修改的任务；
- 3 个测试失败后需要迭代的任务；
- 2 个权限拒绝任务；
- 2 个超时或环境故障任务。

记录：

```text
task_success_rate
patch_test_pass_rate
first_attempt_success_rate
repair_success_rate
human_escalation_rate
average_tool_calls
p95_run_duration
cost_per_task
sandbox_violation_count
```

## 四、交付物

```text
agent-harness-demo/
├── runtime/
│   ├── models.py
│   ├── loop.py
│   ├── state.py
│   └── events.py
├── workspace/
├── tools/
├── sandbox/
├── skills/
├── verification/
│   ├── runner.py
│   └── feedback.py
├── policies/
├── evals/
├── traces/
└── README.md
```

README 至少说明：

- Harness 和 Agent Loop 的边界；
- 执行环境和权限模型；
- 验证反馈如何驱动修复；
- 失败如何重试、恢复或升级人工；
- 评测任务、通过率、延迟和成本；
- 如何防止 Agent 访问越权文件和密钥。

## 五、验收标准

- Agent 能在隔离工作区完成至少一类真实代码任务；
- 测试失败会形成结构化反馈并驱动有限次修复；
- 验证结果来自真实命令或测试，不由模型自报；
- 高风险动作会暂停等待人工批准；
- Run 可通过 Trace 和事件日志完整回放；
- 失败、超时、取消和重复提交都有明确处理；
- README 中的指标来自实际运行结果。

## 六、延伸基准

可以进一步了解 SWE-bench：它将真实 GitHub Issue、代码仓库和测试环境结合起来，要求系统生成可解决问题的补丁，并使用容器化环境评估结果。它适合用来理解“模型能力”和“Harness 能力”如何共同决定 Coding Agent 成功率。
