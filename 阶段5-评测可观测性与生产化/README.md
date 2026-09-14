# 阶段 5：评测、可观测性与生产化

目标：把 Agent 交付为可测试、可监控、可控制成本的生产系统。

学习范围：

- Golden Dataset 和回归测试
- Answer Correctness、Faithfulness 和 Context Recall
- Tool Call Accuracy、Task Completion Rate 和延迟
- LangSmith、Langfuse、OpenTelemetry
- Token、成本、错误率和调用链监控
- Prompt Injection、PII 脱敏、RBAC 和审计
- Rate Limit、熔断、重试、降级和部署

学习文档：

**先读 [`00-阶段5精读路线.md`](00-阶段5精读路线.md)**：岗位导向的跳读索引，给出每篇的 🔴必做 / 🟡必懂 / ⚪用时查 三档划分、工时预算与「停止信号」。八篇合计约 10300 行，其中必做部分只占 1/4~1/3，不建议按 01→08 顺序通读。

- [01 - 评测方法论与 Golden Dataset](01-评测方法论与GoldenDataset设计.md)
- [02 - 评测指标详解与实现](02-评测指标详解与实现.md)
- [03 - Langfuse 与 LangSmith：Agent 可观测性与版本管理](03-Langfuse与LangSmith可观测性.md)
- [04 - OpenTelemetry 与自定义 Tracing](04-OpenTelemetry与自定义Tracing.md)
- [05 - Agent 安全评测与加固](05-Agent安全评测与加固.md)
- [06 - Prometheus 与 Grafana：Agent 指标监控与告警](06-Prometheus与Grafana监控告警.md)
- [07 - 生产化部署：Docker、K8s、CI/CD 与发布策略](07-生产化部署与CI-CD.md)
- [08 - 阶段 5 综合实践：全链路观测与评测报告](08-阶段5综合实践-全链路观测与评测报告.md)

推荐学习顺序：

```text
01 评测方法论与 Golden Dataset（先有评测集，再有指标）
  -> 02 评测指标详解与实现（把用例变成可计算的数字）
  -> 03 Langfuse / LangSmith 可观测性（trace、Token/成本、Prompt 版本）
  -> 04 OpenTelemetry 与自定义 Tracing（厂商中立的全链路追踪）
  -> 05 Agent 安全评测与加固（注入/越权/PII/压测的评测闭环）
  -> 06 Prometheus + Grafana（指标暴露、看板与告警）
  -> 07 生产化部署与 CI/CD（镜像、K8s、发布策略、降级容灾）
  -> 08 综合实践：全链路观测与评测报告（M1~M7，产出 README 实测指标）
```

学习完文档后，按 [08 综合实践](08-阶段5综合实践-全链路观测与评测报告.md) 的 Milestone 计划动手改造已有项目（阶段 3「企业运维分析 Agent」或阶段 4「研发效能 Agent」），最终交付：50~200 条评测集、全链路 trace、Grafana 看板与告警、安全用例通过率、评测报告与项目 README 的实测指标。

> 前置：阶段 3（工具调用工程化、工具安全、LangGraph 编排）与阶段 4（Checkpoint、HITL、长任务）。
>
> 提醒：本文档涉及的库与 API 迭代较快，具体用法以官方文档为准；参考链接集中在各篇末尾的「参考资料」小节。作品集 README 中的指标必须来自实测，不要照抄示例数字。
