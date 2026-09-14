# 阶段 7 综合实践：可靠的多 Agent 研发流程

## 一、项目目标

在阶段 4 的研发效能 Agent 基础上，增加远程 Agent 协作、记忆、多模态输入、Reflection 和可靠写入，形成可以恢复、可验证、可观测的高阶 Agent 流程。

## 二、目标流程

```text
用户提交需求 / 图片 / PDF
  -> 主 Agent
  -> A2A 调用需求分析 Agent
  -> Memory 读取用户偏好和项目约束
  -> 方案生成
  -> Reflection 评审
  -> 人工审批
  -> 幂等创建 Issue / 分支
  -> 失败时补偿或转人工
  -> 输出报告和 Trace
```

## 三、里程碑

### M1：A2A Agent

- 暴露 Agent Card；
- 支持提交和查询任务；
- 支持 `working`、`completed`、`failed`；
- 对重复 message 做幂等处理。

### M2：Memory

- Checkpoint 保存线程状态；
- Store 保存用户或项目级长期记忆；
- 加入租户隔离、删除和过期策略。

### M3：Reflection

- 生成技术方案；
- 评审需求覆盖、风险和测试完整性；
- 最多循环 3 次；
- 评审反馈和每轮成本写入 Trace。

### M4：多模态

- 接收架构图或需求 PDF；
- 校验文件类型、大小和权限；
- 提取结构化信息并保留来源；
- 对 OCR 或视觉提取错误进行评测。

### M5：可靠写入

- 为创建 Issue、分支和通知设计幂等键；
- 模拟超时、重复调用和 Worker 崩溃；
- 为部分成功步骤实现补偿；
- 无法补偿时进入人工审批。

### M6：评测与观测

至少准备：

- 10 条正常流程；
- 5 条 A2A 超时或失败；
- 5 条记忆越权和错误召回；
- 5 条 Reflection 超限；
- 5 条恶意或超大文件；
- 5 条重复写入和补偿场景。

记录：

```text
trace_id
agent_name
remote_agent
task_id
memory_namespace
reflection_attempt
input_modalities
idempotency_key
compensation_status
final_status
latency
cost
```

## 四、交付物

```text
stage7-capstone/
├── a2a/
│   ├── agent_card.json
│   └── server.py
├── memory/
│   ├── checkpoint.py
│   └── store.py
├── reflection/
│   └── workflow.py
├── multimodal/
│   └── input_validation.py
├── reliability/
│   ├── idempotency.py
│   └── compensation.py
├── evals/
├── traces/
└── README.md
```

## 五、验收标准

- A2A 任务在同步、轮询或推送模式下能完成并恢复；
- Memory 不发生跨用户或跨租户泄露；
- Reflection 会停止，不会无限消耗模型调用；
- 多模态输入经过安全和 Schema 校验；
- 写操作重复执行不会产生重复副作用；
- 部分成功后能执行补偿或转人工；
- 报告包含真实的成功率、P95 延迟、Token 成本和失败分类。
