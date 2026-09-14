# Skill 安全、权限与质量评测

## 一、为什么 Skill 需要单独治理

Skill 不是普通文档。它可能影响 Agent 的决策，也可能携带脚本、模板和外部引用。恶意或过时的 Skill 可能导致：

- Agent 激活错误能力；
- 绕过已有工具权限；
- 执行未审查脚本；
- 将敏感数据写入日志或报告；
- 在 Skill 内容中注入额外指令；
- 不同租户之间读取到不应看到的能力。

因此 Skill 必须遵循最小权限、默认只读、版本固定和可审计原则。

## 二、安全控制清单

### 1. 来源与供应链

- 只加载已登记的 Skill 来源；
- 记录 owner、版本和内容 digest；
- 对外部 Skill 做代码和指令审查；
- 禁止生产环境直接跟踪未固定的分支；
- 下线或撤销存在风险的版本。

### 2. 可见性与租户隔离

```text
用户身份
  -> 角色 / 租户策略
  -> 可见 Skill 列表
  -> Skill Loader
  -> Agent
```

Skill 的 `description` 也可能暴露内部信息，因此“不可使用”通常也应意味着“不可发现”。

### 3. 文件和脚本权限

- Skill 文件默认只读；
- 脚本使用白名单和参数校验；
- 脚本在沙箱中运行；
- 限制网络、文件系统和进程权限；
- 写入、删除、外部通知等动作必须走 Tool 权限和人工审批；
- 不把 `allowed-tools` 当作唯一安全边界。

### 4. 注入防护

Skill 内容、参考资料和脚本输出都属于不可信输入，不能自动提升权限。应把：

- Skill 指令；
- 用户输入；
- Tool 返回；
- 外部文档；
- 脚本输出

在 Trace 中区分记录，并对敏感字段做脱敏。

## 三、质量评测

Skill 质量不能只看“Agent 是否读了 `SKILL.md`”，至少需要评测四层：

| 层次 | 评测问题 | 示例指标 |
|---|---|---|
| Discovery | 是否能在正确任务中被选中 | 激活准确率、误激活率 |
| Instruction | 是否按 Skill 要求执行 | 必做步骤完成率、违规率 |
| Tool / Resource | 是否正确使用相关资源 | 工具选择准确率、参数准确率 |
| Outcome | 是否改善最终任务 | 任务完成率、正确率、成本、延迟 |

推荐同时准备：

- 正常任务；
- 相似但不适用的任务；
- Skill 缺失信息的任务；
- 恶意 Skill 或注入内容；
- 工具失败和脚本失败；
- 多租户越权；
- Skill 版本升级回归。

## 四、评测记录

```json
{
  "case_id": "code-review-001",
  "skill_name": "code-review",
  "skill_version": "1.1.0",
  "activated": true,
  "loaded_resources": ["references/review-checklist.md"],
  "tool_calls": ["run_static_check"],
  "task_completed": true,
  "input_tokens": 4200,
  "latency_ms": 8300,
  "failure_type": null
}
```

与阶段 5 的评测体系衔接时，建议至少比较：

```text
无 Skill 基线
  vs
启用 Skill 结果
```

不要只报告“用了 Skill 后效果更好”，还要报告上下文 Token、延迟、误激活、工具错误和安全失败。

## 五、Trace 字段

建议增加：

```text
skill_name
skill_version
skill_source
skill_activation_reason
skill_resources
skill_script
skill_permission_decision
skill_eval_case_id
```

这样出现问题时可以回答：使用了哪个版本、由谁授权、加载了哪些文件、执行了什么脚本、最终是否改善结果。

## 六、练习

1. 为 `incident-analysis` 写 20 条评测用例。
2. 加入 5 条相似任务，验证误激活率。
3. 加入 5 条越权和 Skill 注入用例。
4. 比较 Skill 版本 `1.0.0` 和 `1.1.0` 的任务完成率与成本。
5. 把失败 Trace 回灌成回归用例。
