# Agent Legibility、验证闭环与反馈系统

## 一、Agent Legibility

**来源**：[OpenAI Harness Engineering: Repository Knowledge](https://openai.com/index/harness-engineering/)，[Claude Code Best Practices](https://code.claude.com/docs/en/best-practices)

Agent Legibility 指 Agent 能发现、读取、理解并验证完成任务所需的资料。对 Agent 不可发现的知识，等效于不存在。不要把全部规则堆进系统提示；使用短入口 + 可导航的资料库：

```text
AGENTS.md             # 100 行内：启动命令、目录、必守规则、索引
ARCHITECTURE.md        # 模块边界与依赖方向
docs/runbooks/         # 运行与排障
docs/decisions/        # ADR / 关键取舍
skills/                # 按需任务知识
scripts/verify_*.sh    # 可执行验证
```

文档是代码的一部分：应版本化、交叉链接，并用 CI 检查断链、生成物过期和缺失的必要章节。

## 二、Ground Truth 与验证层级

**来源**：[Claude Code: Give Claude a way to verify](https://code.claude.com/docs/en/best-practices)，[Anthropic Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)

Harness 的验证信号按可信度排序：

| 层级 | 例子 | 能证明什么 |
|---|---|---|
| 静态 | formatter、lint、typecheck | 格式/类型/规则 |
| 单元 | pytest/JUnit | 局部行为 |
| 集成 | DB/API/消息队列测试 | 边界协作 |
| E2E | 浏览器、真实工作流 | 用户路径 |
| 评测 | Golden Tasks | Agent 任务质量 |
| 人工 | 高风险发布/语义验收 | 业务判断 |

模型解释、评论和“看起来对”不属于 Ground Truth。

## 三、把失败变成结构化反馈

**来源**：[Claude Code Best Practices](https://code.claude.com/docs/en/best-practices)，[Symphony Spec §17](https://github.com/openai/symphony/blob/main/SPEC.md)

不要把完整的 CI 输出无筛选塞给模型。Verification Runner 应生成短、确定、可行动的反馈：

```json
{
  "command": "pytest tests/orders/test_pagination.py -q",
  "exit_code": 1,
  "category": "test_failure",
  "failed_tests": ["test_page_two_returns_twenty"],
  "expected": "20 records",
  "actual": "10 records",
  "artifact": "artifacts/junit.xml"
}
```

模型据此定位代码、修改并重跑同一检查。若连续失败超过阈值，停止并升级人工，避免无目标循环。

## 四、验证状态机

**来源**：[OpenAI Harness Engineering](https://openai.com/index/harness-engineering/)

```text
agent_changed -> verify_fast -> verify_targeted -> verify_full
                    | pass                         | pass
                    v                              v
                 next gate                       complete
                    |
                    v fail
              feedback -> repair (max N) -> verify_fast
```

建议先跑低成本检查，再跑高成本 E2E/评测。每个 gate 明确命令、超时、产物、通过条件和是否允许重试。

## 五、独立审查与证据包

**来源**：[Claude Code: Add an adversarial review step](https://code.claude.com/docs/en/best-practices)，[GitHub Actions Artifacts](https://docs.github.com/en/actions/using-workflows/storing-workflow-data-as-artifacts)

生成者不应是唯一评审者。对中高风险修改，使用独立 Reviewer Agent 或人工审查 diff、需求和测试覆盖。Run 完成时生成证据包：

```text
patch.diff
verification.json
junit.xml / coverage
agent-trace.json
review.md
workspace-manifest.json
```

CI Artifact 需要设置保留期，并禁止把 Token、`.env`、原始用户敏感内容上传。

## 六、验收

- 为一个服务创建 Agent 可读入口和验证命令；
- 将一次 pytest 失败转成结构化反馈；
- 设置最多 3 次修复和明确的升级条件；
- 让独立 Reviewer 检查 diff 与验收标准；
- 输出可由第三方复核的证据包。
