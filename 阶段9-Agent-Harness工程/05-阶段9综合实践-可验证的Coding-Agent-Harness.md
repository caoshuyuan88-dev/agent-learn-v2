# 阶段 9 综合实践：可验证的 Coding Agent Harness

## 一、目标与范围

**来源**：[OpenAI Symphony Spec](https://github.com/openai/symphony/blob/main/SPEC.md)，[OpenAI Harness Engineering](https://openai.com/index/harness-engineering/)

交付一个内部、受控仓库使用的 Coding Agent Harness。输入为 Issue；输出不是“模型说修好了”，而是受限工作区的 patch、真实验证结果、Trace 和人工可审查报告。

不做：直接访问生产、自动合并、未隔离执行任意互联网代码、用自然语言代替权限。

## 二、架构与职责

**来源**：[Symphony Spec §3, §7, §9-10](https://github.com/openai/symphony/blob/main/SPEC.md)

```text
Issue Adapter -> Orchestrator -> Workspace/Sandbox -> Agent Runner
                    |                  |                 |
                    +-> Event Store <--+-> Verification Runner
                    +-> Policy/Approval Gateway -> Git/Tracker Tool
```

- Adapter：将 GitHub/Jira 映射成稳定的 `task_id/title/body/state`；
- Orchestrator：单一任务领取、并发、退避和取消；
- Workspace：固定 revision 的 worktree，路径必须在根目录下；
- Runner：注入短上下文、Skill 和受限工具；
- Verifier：运行确定性命令并生成结构化反馈；
- Gateway：保管凭据，执行高风险 Tool 与审批；
- Event Store：记录状态变化与证据位置。

## 三、目录与配置

**来源**：[OpenAI Harness Engineering](https://openai.com/index/harness-engineering/)，[Symphony Spec §5](https://github.com/openai/symphony/blob/main/SPEC.md)

```text
agent-harness-demo/
├── AGENTS.md
├── WORKFLOW.md
├── runtime/          # orchestrator、状态机、事件
├── workspace/        # worktree 创建与清理
├── verification/     # command runner、反馈解析
├── policies/         # 权限与审批策略
├── skills/           # 按需领域流程
├── evals/            # Golden Tasks
├── artifacts/        # 每个 run 的证据包
└── infra/            # sandbox / CI 配置
```

`WORKFLOW.md` 应版本化，包含任务过滤、并发、预算、验证命令和交付状态；配置解析必须严格校验，错误时保留最后已知可用配置而不是静默换默认值。

## 四、实施里程碑

### M1：可重复任务与工作区
**来源**：[Symphony Spec §4, §9](https://github.com/openai/symphony/blob/main/SPEC.md)

实现 `Task`、`Run`、`Workspace`；对每个 Issue 固定 revision；路径清理并加入 hash 防碰撞；任务完成后存档 diff 与 manifest。

### M2：受限 Agent 执行
**来源**：[Deep Agents Production](https://docs.langchain.com/oss/python/deepagents/going-to-production)

在容器中运行，只挂载工作区；默认拒绝网络；限制 CPU/内存/时间；不注入云密钥。允许读代码、编辑工作区、跑预定义验证命令。

### M3：验证反馈循环
**来源**：[Claude Code Best Practices](https://code.claude.com/docs/en/best-practices)

执行 `format -> lint -> typecheck -> targeted test -> full test`。将失败压缩为结构化 JSON；最多 3 次修复；第三次失败或安全门禁失败时转人工。

### M4：审批与交付
**来源**：[Deep Agents Permissions](https://docs.langchain.com/oss/python/deepagents/permissions)

创建分支、提交、PR、依赖升级、外部网络和写入 Issue 都是审批动作。审批通过后才由宿主 Gateway 执行，不让容器内 Agent 取得长期 Git/Tracker 凭据。

### M5：评测与运营
**来源**：[SWE-bench](https://github.com/SWE-bench/SWE-bench)，[Google SRE Monitoring](https://sre.google/workbook/monitoring/)

建立至少 20 条 Golden Tasks：10 条单测可验证修复、4 条多文件、3 条修复循环、2 条权限拒绝、1 条超时。比较首次成功率、修复成功率、P95 时长、成本和人工升级率。

## 五、关键接口示例

**来源**：[Symphony Spec §10, §17](https://github.com/openai/symphony/blob/main/SPEC.md)

```python
from dataclasses import dataclass
from subprocess import run


@dataclass(frozen=True)
class Verification:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str


def verify(workspace: str, command: list[str]) -> Verification:
    result = run(command, cwd=workspace, capture_output=True, text=True, timeout=300)
    return Verification(command, result.returncode, result.stdout[-8000:], result.stderr[-8000:])
```

此代码只说明验证接口；生产应使用 Sandbox 执行命令、命令 allowlist、输出脱敏、超时分类及 Artifact 存储。绝不能将 Issue 文本拼接进 shell 字符串。

## 六、Definition of Done

- 每个 Run 使用隔离工作区，且保留基线 revision；
- 验证命令实际执行并保存可复核结果；
- 失败反馈可让 Agent 有限修复，超限后转人工；
- 所有高风险副作用经过 Gateway 与审批；
- Trace 可关联任务、工作区、Tool、验证、审批与产物；
- Golden Tasks 与安全演练在 CI 中运行；
- 输出报告包含真实指标和失败分类。
