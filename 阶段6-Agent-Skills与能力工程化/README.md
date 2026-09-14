# 阶段 6：Agent Skills 与能力工程化

目标：把面向某类任务的知识、流程、参考资料和脚本封装成可发现、可加载、可治理的 Skill，并接入统一 Agent Runtime。

> Agent Skills 不是 Deep Agents 专属功能。Deep Agents 提供了较完整的实现方式；本阶段先学习跨框架抽象，再学习具体 Runtime 接入。

## 学习范围

- Agent Skill 的定义、边界和适用场景
- Agent Skills 开放格式与 `SKILL.md`
- 元数据、渐进式披露和按需加载
- Skill Registry、版本管理和兼容性
- Skill 与 Tool、Prompt、Workflow、Memory、MCP 的关系
- LangGraph、Deep Agents 和自研 Runtime 的接入方式
- 多租户、权限、审批、沙箱和供应链安全
- Skill 测试、轨迹评测、回归门禁与 Trace

## 学习文档

- [01 - Agent Skills 概念与开放格式](01-Agent-Skills概念与开放格式.md)
- [02 - Skill Runtime、加载器与框架接入](02-Skill-Runtime加载器与框架接入.md)
- [03 - Skill 安全、权限与质量评测](03-Skill安全权限与质量评测.md)
- [04 - 阶段 6 综合实践：可治理的企业 Skill 平台](04-阶段6综合实践-可治理的企业Skill平台.md)

## 推荐顺序

```text
01 概念与开放格式
  -> 02 Runtime、加载器与框架接入
  -> 03 安全、权限与质量评测
  -> 04 综合实践
```

## 最终产出

开发一个 `incident-analysis` 或 `code-review` Skill，并完成：

- 标准目录与 `SKILL.md`
- LangGraph 或 Deep Agents 接入
- Tool / MCP 调用边界
- 角色或租户级 Skill 可见性
- Skill 版本和发布记录
- 确定性测试与 Agent 轨迹评测
- Trace、成本和上下文消耗对比
- README 与实测报告

## 验收标准

- 能从零设计一个符合开放格式的 Skill；
- 能解释 Skill 与 Tool、Prompt、Workflow、Memory、MCP 的边界；
- 能实现 Discovery、Activation、Execution 三阶段加载；
- 能限制 Skill 的可见范围、文件访问和脚本执行权限；
- 能用评测集和 Trace 证明 Skill 的收益、成本和失败模式。

## 资料依据

- [Agent Skills Overview](https://agentskills.io/home)
- [Agent Skills Specification](https://agentskills.io/specification)
- [Deep Agents Skills](https://docs.langchain.com/oss/python/deepagents/skills)
- [MCP Tools](https://modelcontextprotocol.io/docs/concepts/tools)
- [MCP Prompts](https://modelcontextprotocol.io/docs/concepts/prompts)
