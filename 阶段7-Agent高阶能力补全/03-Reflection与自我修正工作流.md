# Reflection 与自我修正工作流

## 一、Reflection 是什么

Reflection 不是让模型输出更多“思考过程”，而是增加一个评审环节：对候选答案、工具轨迹或中间产物进行检查，根据结构化反馈决定接受、修正或终止。

```text
生成候选结果
  -> 评审：是否满足标准
  -> 通过：结束
  -> 不通过：带反馈重新生成
```

它适合有明确验收标准、允许迭代且结果可比较的任务，例如代码审查、报告生成、翻译和结构化数据修正。

## 二、推荐模式

### 1. Generator-Evaluator

一个节点生成，一个节点评审。评审应输出结构化结果：

```python
from typing import Literal
from pydantic import BaseModel


class Feedback(BaseModel):
    verdict: Literal["accept", "revise"]
    issues: list[str]
    suggestions: list[str]
```

### 2. Evaluator-Optimizer

```text
Generator -> Evaluator
               | accept -> END
               | revise -> Generator
```

### 3. Reflection + Tool Verification

对工具调用结果做确定性校验优先，语义评审作为补充：

```text
Tool result schema 校验
  -> 业务规则校验
  -> 必要时 LLM evaluator
```

## 三、LangGraph 示例

```python
from typing import Literal
from typing_extensions import TypedDict
from langgraph.graph import END, START, StateGraph


class State(TypedDict, total=False):
    draft: str
    feedback: str
    verdict: Literal["accept", "revise"]
    attempts: int


def generate(state: State) -> dict:
    return {
        "draft": f"draft-{state.get('attempts', 0) + 1}",
        "attempts": state.get("attempts", 0) + 1,
    }


def evaluate(state: State) -> dict:
    accepted = state["attempts"] >= 2
    return {
        "verdict": "accept" if accepted else "revise",
        "feedback": "Add evidence before finalizing" if not accepted else "",
    }


def route(state: State) -> str:
    if state["verdict"] == "accept" or state["attempts"] >= 3:
        return "finish"
    return "generate"


builder = StateGraph(State)
builder.add_node("generate", generate)
builder.add_node("evaluate", evaluate)
builder.add_edge(START, "generate")
builder.add_edge("generate", "evaluate")
builder.add_conditional_edges(
    "evaluate",
    route,
    {"generate": "generate", "finish": END},
)
graph = builder.compile()
```

示例中的上限 `3` 是防止无限循环的关键。生产系统还应设置 token、时间和费用预算。

## 四、评审器设计

优先级建议：

1. JSON Schema / Pydantic 校验；
2. 确定性业务规则；
3. 工具结果和引用证据校验；
4. LLM-as-Judge；
5. 人工抽检。

评审结果至少记录：

```text
judge_model
judge_prompt_version
criteria_version
verdict
issues
attempt
input_tokens
output_tokens
latency
```

## 五、Reflection 的风险

- 评审器和生成器使用同一错误假设；
- 循环没有最大次数；
- 每轮都重新发送巨大上下文；
- LLM 评审结果漂移；
- “更长”被误认为“更好”；
- 修正过程破坏了原本正确的内容。

## 六、练习

1. 为研发方案增加“需求覆盖、风险完整性、测试可执行性”三个评审标准。
2. 设置最多 3 轮、总 token 和总耗时预算。
3. 对比无 Reflection、1 轮和最多 3 轮的质量与成本。
4. 将失败样本回灌阶段 5 Golden Dataset。

## 资料依据

- [LangGraph Workflows and Agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents)
