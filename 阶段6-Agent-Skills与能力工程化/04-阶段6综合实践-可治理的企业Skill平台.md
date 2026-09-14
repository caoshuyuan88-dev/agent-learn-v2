# 阶段 6 综合实践：可治理的企业 Skill 平台

## 一、项目目标

为阶段 3 的企业运维分析 Agent 或阶段 4 的研发效能 Agent 增加 Skill 能力，形成一套可注册、可发现、可授权、可评测、可观测的 Skill 管理闭环。

建议选择一个 Skill：

- `incident-analysis`：分析日志、指标和告警，生成故障分析报告；
- `code-review`：执行代码审查清单、静态检查并生成审查报告。

## 二、目标架构

```text
Skill Registry
  -> Skill Resolver（角色 / 租户 / 版本）
  -> Skill Loader（frontmatter / SKILL.md / resources）
  -> Agent Runtime（LangGraph 或 Deep Agents）
  -> Tool / MCP Gateway
  -> Approval / Sandbox
  -> Trace / Evaluation / Report
```

## 三、里程碑

### M1：创建 Skill

- 建立标准目录；
- 编写 `SKILL.md`；
- 增加一个参考文件和一个只读脚本；
- 通过格式校验。

### M2：接入 Agent

- 实现 Skill 发现和激活；
- 在 Agent 状态或 Trace 中记录 Skill 版本；
- 验证不匹配任务不会误激活 Skill。

### M3：增加治理

- 根据租户或角色过滤 Skill；
- 共享 Skill 只读；
- Skill 写入和脚本执行需要审批或沙箱；
- 增加版本、owner、digest 和撤销状态。

### M4：接入评测和观测

- 至少 20 条功能评测用例；
- 至少 5 条安全和越权用例；
- 记录 Skill 激活、资源读取和脚本执行 Trace；
- 输出无 Skill / 有 Skill 对照报告。

### M5：发布与回滚

- 新 Skill 版本先在测试环境运行；
- 评测低于阈值时阻止发布；
- 支持按租户灰度；
- 保留旧版本并验证一键回滚。

## 四、交付物

```text
skill-platform-demo/
├── skills/
│   └── incident-analysis/
│       ├── SKILL.md
│       ├── references/
│       └── scripts/
├── registry/
├── loader/
├── policies/
├── evals/
├── traces/
├── reports/
└── README.md
```

README 至少说明：

- 为什么这个能力做成 Skill；
- Skill 与 Tool、MCP、Workflow 的边界；
- 加载和权限流程；
- 版本发布和回滚方式；
- 评测集、阈值和实际结果；
- Token、延迟、任务完成率和安全用例通过率。

## 五、验收标准

- Skill 能被正确发现，并在匹配任务中激活；
- 不匹配任务的误激活可被评测发现；
- Skill 不能绕过 Tool、MCP 或人工审批权限；
- Skill 资源和脚本访问均有边界；
- Trace 能还原一次 Skill 的完整使用过程；
- 新版本必须通过评测门禁后才能发布；
- README 中的所有数字来自实际运行结果。

## 六、参考代码

下面的代码实现一个框架无关的最小 Skill 平台。它先完成 Skill 发现、权限过滤和安全加载，再由 Agent Runtime 决定是否激活和调用工具。

### 6.1 Skill 示例

```text
skills/incident-analysis/
├── SKILL.md
├── references/
│   └── incident-checklist.md
└── scripts/
  └── collect_readonly.py
```

`skills/incident-analysis/SKILL.md`：

```markdown
---
name: incident-analysis
description: Analyze service incidents from logs, metrics, and alerts. Use when the user asks for incident diagnosis or an operations report.
metadata:
  version: "1.0.0"
  owner: sre-team
  allowed_roles: sre,platform
---

# Incident Analysis

## Instructions

1. Confirm the service name and incident time window.
2. Read `references/incident-checklist.md` when classifying symptoms.
3. Use read-only diagnostic tools first.
4. Do not restart services, change configuration, or send notifications.
5. Return evidence, suspected cause, confidence, and next actions.
```

Skill 中的自然语言限制不能代替权限控制。重启服务等写操作仍必须由 Tool Gateway 和人工审批控制。

### 6.2 Loader 与安全路径解析

以下示例只依赖 Python 标准库。生产项目可以把 frontmatter 解析替换为 `PyYAML`，但权限和路径校验逻辑仍应保留。

```python
# loader.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class SkillSummary:
  name: str
  description: str
  path: Path
  version: str | None
  allowed_roles: frozenset[str]


class SkillValidationError(ValueError):
  pass


class SkillLoader:
  def __init__(self, source: Path) -> None:
    self.source = source.resolve()

  def discover(self) -> list[SkillSummary]:
    summaries: list[SkillSummary] = []
    if not self.source.is_dir():
      raise SkillValidationError(f"skill source does not exist: {self.source}")

    for skill_dir in sorted(path for path in self.source.iterdir() if path.is_dir()):
      manifest = skill_dir / "SKILL.md"
      if not manifest.is_file():
        continue
      metadata = self._read_frontmatter(manifest)
      name = metadata.get("name", "")
      description = metadata.get("description", "")
      if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        raise SkillValidationError(f"invalid skill name: {name}")
      if name != skill_dir.name:
        raise SkillValidationError(f"skill name does not match directory: {name}")
      if not description:
        raise SkillValidationError(f"missing description: {manifest}")

      summaries.append(
        SkillSummary(
          name=name,
          description=description,
          path=skill_dir.resolve(),
          version=metadata.get("version"),
          allowed_roles=frozenset(
            role.strip()
            for role in metadata.get("allowed_roles", "").split(",")
            if role.strip()
          ),
        )
      )
    return summaries

  def activate(self, skill: SkillSummary, role: str) -> str:
    if skill.allowed_roles and role not in skill.allowed_roles:
      raise PermissionError(f"role {role!r} cannot activate {skill.name}")
    manifest = skill.path / "SKILL.md"
    return manifest.read_text(encoding="utf-8")

  def resolve_resource(self, skill: SkillSummary, relative_path: str) -> Path:
    target = (skill.path / relative_path).resolve()
    if skill.path not in target.parents:
      raise PermissionError("skill resource escapes the skill directory")
    if not target.is_file():
      raise FileNotFoundError(target)
    return target

  @staticmethod
  def _read_frontmatter(manifest: Path) -> dict[str, str]:
    content = manifest.read_text(encoding="utf-8")
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
      raise SkillValidationError(f"missing frontmatter: {manifest}")
    try:
      end = lines.index("---", 1)
    except ValueError as exc:
      raise SkillValidationError(f"unterminated frontmatter: {manifest}") from exc

    metadata: dict[str, str] = {}
    for line in lines[1:end]:
      key, separator, value = line.partition(":")
      if separator:
        metadata[key.strip()] = value.strip().strip('"')
    return metadata
```

### 6.3 Resolver、评测记录和 Trace

Resolver 负责“当前请求能看到哪些 Skill”，Loader 负责“如何读取 Skill”。两者分开后，权限策略不会散落在文件读取代码中。

```python
# runtime.py
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from loader import SkillLoader, SkillSummary


@dataclass(frozen=True)
class SkillContext:
  tenant_id: str
  role: str
  allowed_skills: frozenset[str]


@dataclass
class SkillTrace:
  skill_name: str
  skill_version: str | None
  tenant_id: str
  role: str
  activated: bool
  loaded_resources: list[str]
  tool_calls: list[str]
  task_completed: bool
  error_type: str | None = None
  timestamp: str = ""

  def to_json(self) -> str:
    return json.dumps(asdict(self), ensure_ascii=False)


class SkillResolver:
  def __init__(self, loader: SkillLoader) -> None:
    self.loader = loader

  def resolve(self, context: SkillContext) -> list[SkillSummary]:
    return [
      skill
      for skill in self.loader.discover()
      if skill.name in context.allowed_skills
      and (not skill.allowed_roles or context.role in skill.allowed_roles)
    ]


def new_trace(skill: SkillSummary, context: SkillContext) -> SkillTrace:
  return SkillTrace(
    skill_name=skill.name,
    skill_version=skill.version,
    tenant_id=context.tenant_id,
    role=context.role,
    activated=False,
    loaded_resources=[],
    tool_calls=[],
    task_completed=False,
    timestamp=datetime.now(timezone.utc).isoformat(),
  )


def write_trace(trace: SkillTrace, output: Path) -> None:
  output.parent.mkdir(parents=True, exist_ok=True)
  with output.open("a", encoding="utf-8") as file:
    file.write(trace.to_json() + "\n")
```

一个最小运行入口：

```python
# run_skill.py
from pathlib import Path

from loader import SkillLoader
from runtime import SkillContext, SkillResolver, new_trace, write_trace


loader = SkillLoader(Path("skills"))
resolver = SkillResolver(loader)
context = SkillContext(
  tenant_id="demo-company",
  role="sre",
  allowed_skills=frozenset({"incident-analysis"}),
)

for skill in resolver.resolve(context):
  trace = new_trace(skill, context)
  instructions = loader.activate(skill, context.role)
  checklist = loader.resolve_resource(skill, "references/incident-checklist.md")
  trace.activated = True
  trace.loaded_resources.append(str(checklist.relative_to(skill.path)))

  # 这里接入 LangGraph、Deep Agents 或自研 Agent Runtime。
  # Tool 调用必须继续经过现有的权限、审批、超时和审计层。
  _ = instructions
  trace.task_completed = True
  write_trace(trace, Path("traces/skill-traces.jsonl"))
```

### 6.4 Deep Agents 接入

Deep Agents 可以直接接收 Skill 源目录。源目录的下一层必须是具体 Skill 目录：

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
  model="anthropic:claude-sonnet-4-6",
  skills=["/skills/"],
)

result = agent.invoke({
  "messages": [
    {
      "role": "user",
      "content": "分析 payment-api 最近一次故障，只使用只读诊断能力。",
    }
  ]
})
```

生产环境还需要配置 backend、Skill 只读权限、脚本沙箱和 checkpointer。不要把 `skills=[...]` 当成完整的授权机制。

### 6.5 LangGraph 接入

LangGraph 中可以把 Skill 加载作为显式节点。Skill 本身不应直接修改业务状态，节点只负责把已授权的指令和资源摘要写入 State：

```python
from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class AgentState(TypedDict, total=False):
  user_request: str
  skill_name: str
  skill_version: str | None
  skill_instructions: str
  answer: str


def load_incident_skill(state: AgentState) -> dict:
  # 真实实现中调用 SkillResolver，并根据用户身份过滤结果。
  return {
    "skill_name": "incident-analysis",
    "skill_version": "1.0.0",
    "skill_instructions": "Use read-only diagnostics and cite evidence.",
  }


def run_agent(state: AgentState) -> dict:
  # 这里替换为模型调用和阶段 3 的 ToolExecutor。
  return {"answer": f"request={state['user_request']}\n{state['skill_instructions']}"}


graph = StateGraph(AgentState)
graph.add_node("load_skill", load_incident_skill)
graph.add_node("agent", run_agent)
graph.add_edge(START, "load_skill")
graph.add_edge("load_skill", "agent")
graph.add_edge("agent", END)
app = graph.compile()
```

### 6.6 评测门禁

将 Skill 评测结果接入阶段 5 的评测 runner。至少同时比较无 Skill 基线和启用 Skill 的结果：

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class SkillEvalResult:
  task_completion_rate: float
  activation_accuracy: float
  tool_call_accuracy: float
  input_tokens: int
  p95_latency_ms: int
  security_pass_rate: float


def passes_gate(result: SkillEvalResult) -> bool:
  return (
    result.task_completion_rate >= 0.80
    and result.activation_accuracy >= 0.95
    and result.tool_call_accuracy >= 0.90
    and result.security_pass_rate == 1.0
  )
```

阈值只是示例，必须根据固定评测集、模型版本和实测噪声确定。评测报告至少回答：

```text
Skill 是否提高任务完成率？
是否增加了输入 Token 和延迟？
是否出现误激活或工具误调用？
Skill 内容或脚本是否造成安全失败？
新版本是否优于旧版本，是否允许灰度发布？
```
