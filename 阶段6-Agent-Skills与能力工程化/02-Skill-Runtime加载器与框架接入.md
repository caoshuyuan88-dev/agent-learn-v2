# Skill Runtime、加载器与框架接入

## 学习目标

- 设计与框架无关的 Skill Loader；
- 实现 Discovery、Activation、Execution；
- 理解 Skill Registry、版本和兼容性；
- 将同一个 Skill 接入 LangGraph、Deep Agents 或自研 Runtime；
- 记录 Skill 使用轨迹和资源读取过程。

## 一、统一运行模型

```text
用户请求
  -> Skill Resolver：根据任务和权限筛选候选 Skill
  -> Discovery：注入 name/description
  -> Agent 决策：判断是否激活
  -> Activation：读取 SKILL.md
  -> Execution：读取资源、调用 Tool、运行批准的脚本
  -> Evaluation / Trace：记录结果和成本
```

Skill Loader 不应直接决定业务权限。它负责解析和加载；权限服务负责决定“当前用户是否可以看到或使用这个 Skill”。

## 二、Loader 的核心接口

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class SkillSummary:
    name: str
    description: str
    path: Path
    version: str | None = None

class SkillLoader:
    def discover(self, source: Path) -> list[SkillSummary]:
        """扫描 source 下的 Skill，并只读取 frontmatter。"""
        raise NotImplementedError

    def activate(self, skill: SkillSummary) -> str:
        """读取并返回 SKILL.md 正文。"""
        raise NotImplementedError

    def resolve_resource(self, skill: SkillSummary, relative_path: str) -> Path:
        """只允许解析 Skill 目录内的相对路径。"""
        raise NotImplementedError
```

生产实现至少应检查：

- `name` 是否符合规范；
- `name` 是否与目录名称一致；
- `description` 是否存在且足够具体；
- 路径是否发生目录逃逸；
- Skill 是否处于允许的版本和兼容环境；
- 支持文件是否在 Skill 根目录内。

## 三、Registry 与版本

Skill Registry 可以是 Git 仓库、对象存储、数据库或配置中心。建议保存：

```text
skill_name
version
owner
status              # draft / approved / deprecated
compatibility
allowed_roles
digest
created_at
updated_at
```

推荐使用不可变版本发布：

```text
code-review@1.0.0
code-review@1.1.0
```

默认使用已批准版本，新版本先进入测试和灰度，不要让线上 Agent 自动读取未审查内容。

## 四、Deep Agents 接入

Deep Agents 官方支持把包含 Skill 子目录的源目录传给 `skills`：

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",
    skills=["/skills/"],
)
```

Runtime 会先发现 frontmatter，任务匹配后读取 `SKILL.md`，再由 Agent 按指令访问支持文件。真实项目还需要配置 backend、文件权限、检查点和脚本沙箱。

## 五、LangGraph 接入思路

LangGraph 不要求使用某一种 Skill 格式，可以把 Skill Loader 做成节点或 middleware：

```text
resolve_skills
  -> load_skill_instructions
  -> agent_decision
  -> tool_or_subgraph_execution
  -> record_skill_trace
```

关键是把 `skill_name`、`skill_version`、`activated`、`loaded_resources` 放进状态或 Trace，避免出现“结果变了但不知道加载了哪个 Skill”的问题。

## 六、练习

1. 实现一个只读本地目录的 `SkillLoader`。
2. 增加 YAML frontmatter 解析和目录逃逸测试。
3. 实现按用户角色筛选 Skill。
4. 使用同一个 `code-review` Skill 接入一个 LangGraph 节点和一个 Deep Agent。
5. 对比全部预加载与渐进式加载的输入 Token 和任务耗时。
