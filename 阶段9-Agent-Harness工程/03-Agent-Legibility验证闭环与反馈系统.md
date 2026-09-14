# Agent Legibility、验证闭环与反馈系统

## 一、Agent Legibility 是什么

Agent Legibility 指系统中的代码、文档、日志、指标、测试、架构和运行状态能够被 Agent 直接理解和查询。

对 Agent 来说：

```text
无法发现、无法读取、无法执行验证 = 实际上不存在
```

因此 Harness 的任务不是无限增加 Prompt，而是让仓库和运行环境成为结构化、可导航的知识与验证系统。

## 二、知识地图

推荐仓库提供短入口和深层文档：

```text
AGENTS.md / README.md
  -> ARCHITECTURE.md
  -> docs/index.md
  -> design docs
  -> execution plans
  -> runbooks
  -> generated schemas
  -> tests / scripts
```

入口文件应该像目录，而不是一千页规则的集合。每条规则最好能链接到真正的代码、测试或生成物。

## 三、机械化不变量

以下规则适合放进 Lint、结构测试或 CI：

- 依赖方向不能反向；
- 某些模块不能直接访问数据库；
- 所有外部输入必须经过 Schema 校验；
- 写操作必须经过权限和审计；
- 每个 Tool 必须有超时和错误分类；
- 每个 Agent Run 必须有 `run_id` 和 `trace_id`；
- PR 必须包含测试或明确豁免原因。

Prompt 可以解释规则，但只有自动化检查才能稳定阻止违规。

## 四、验证闭环

```text
Agent 修改
  -> 格式化 / 类型检查
  -> 单元测试
  -> 集成测试
  -> 业务验收
  -> 评测集回归
  -> 生成证据
  -> 失败反馈回 Agent
```

验证输出必须可被 Agent 读取，不能只打印“失败”。好的错误信息包括：

```text
失败位置
失败类型
复现命令
期望行为
实际行为
可能原因
下一步建议
```

## 五、Coding Agent 示例

```text
任务：修复订单查询接口的分页 Bug

验证命令：pytest tests/orders/test_pagination.py -q
失败反馈：expected page=2 to return 20 records, got 10
Agent 动作：检查分页边界 -> 修改实现 -> 重新运行测试
成功证据：1 passed
```

测试结果是 Ground Truth，不是模型自评。模型可以解释结果，但不能自行宣布测试通过。

## 六、反馈分类

| 反馈 | 处理方式 |
|---|---|
| 格式错误 | 自动修复并重跑 |
| 类型错误 | 读取诊断并修改 |
| 单测失败 | 根据失败输出迭代 |
| 安全门禁失败 | 阻断并升级人工 |
| 评测退化 | 阻止发布或回滚 |
| 环境故障 | 重试、换环境或人工接管 |

## 七、Entropy 与持续清理

Agent 会复制仓库中已有的模式，也会复制坏模式。Harness 需要持续清理：

- 定期扫描过期文档；
- 检查重复实现；
- 追踪架构违规；
- 把人工 Review 意见转成规则或测试；
- 保持生成代码、文档、Schema 和运行行为一致。

## 八、练习

1. 为现有项目创建一份 Agent 可读的文档目录。
2. 把 5 条人工 Review 意见转换为自动检查。
3. 设计一个失败反馈格式，并接入 Agent 修复循环。
4. 构建“失败 Trace -> 回归用例 -> CI 门禁”的闭环。
