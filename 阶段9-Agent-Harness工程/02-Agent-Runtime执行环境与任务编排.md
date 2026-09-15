# Agent Runtime、执行环境与任务编排

## 一、任务领取、并发与幂等

**来源**：[Symphony Spec §7-8](https://github.com/openai/symphony/blob/main/SPEC.md)

Orchestrator 是调度状态的单一写入者。领取任务前必须原子检查：任务处于可执行状态、未被领取、存在并发槽位、未超过重试/预算上限。否则两个 Worker 会同时修改同一仓库。

```python
async def claim(task_id: str, running: set[str], limit: int) -> bool:
    if task_id in running or len(running) >= limit:
        return False
    running.add(task_id)  # 生产替换为数据库条件更新/分布式锁
    return True
```

内存 set 只适合单进程 demo；生产可用数据库唯一约束、`SELECT ... FOR UPDATE SKIP LOCKED`、队列消费者组或具租约的任务系统。

## 二、隔离 Workspace

**来源**：[Symphony Spec §9](https://github.com/openai/symphony/blob/main/SPEC.md)，[Docker Security](https://docs.docker.com/engine/security/)

每个任务必须具有隔离工作区，推荐：`workspace/<sanitized-task-id>-<stable-hash>/`。启动 Agent 前验证路径解析后仍位于根目录中，防止 `../` 逃逸。

```python
from pathlib import Path


def workspace_path(root: Path, name: str) -> Path:
    root = root.resolve()
    target = (root / name).resolve()
    if root not in target.parents:
        raise PermissionError("workspace escapes root")
    return target
```

工作区流程：固定 Git revision -> 创建 worktree/clone -> 安装锁定依赖 -> 运行 Agent -> 收集 diff/日志 -> 清理或归档。不要让并发 Run 复用有未提交改动的目录。

## 三、Sandbox 不是可选装饰

**来源**：[Deep Agents Production: Execution Environment](https://docs.langchain.com/oss/python/deepagents/going-to-production)，[Docker Resource Constraints](https://docs.docker.com/engine/containers/resource_constraints/)

Agent 能执行命令时，容器至少设置 CPU、内存、磁盘、执行时间和网络策略。容器本身不是绝对安全边界：禁止挂载 Docker socket、宿主根目录和密钥目录；以非 root 用户运行；仅挂载任务工作区；默认无网络或 allowlist。

```yaml
# 仅用于理解生产基线
services:
  agent-worker:
    image: registry.example/agent-worker@sha256:PINNED_DIGEST
    read_only: true
    user: "10001:10001"
    mem_limit: 4g
    cpus: 2.0
    security_opt: ["no-new-privileges:true"]
    cap_drop: ["ALL"]
    volumes:
      - ./workspaces/task-42:/workspace:rw
```

真实 K8s 环境还应采用 Restricted Pod Security：非 root、禁止特权容器、禁止 HostPath、关闭 privilege escalation、使用 RuntimeDefault seccomp。[Kubernetes Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)

## 四、Agent Runner 与预算

**来源**：[Deep Agents Overview](https://docs.langchain.com/oss/python/deepagents/overview)，[Symphony Spec §10](https://github.com/openai/symphony/blob/main/SPEC.md)

每次 Run 都要限制：总时间、静默时间、最大回合、最大工具调用、最大 Token、最大费用。超限不是“再试一次”，而是记录失败类型并进入重试、人工审批或终止。

```python
@dataclass
class Budget:
    max_turns: int = 12
    max_tool_calls: int = 40
    max_seconds: int = 900


def may_continue(turns: int, calls: int, budget: Budget) -> bool:
    return turns < budget.max_turns and calls < budget.max_tool_calls
```

## 五、重试、取消和恢复

**来源**：[Symphony Spec §8, §14](https://github.com/openai/symphony/blob/main/SPEC.md)

只对临时故障重试：网络超时、可恢复的服务 5xx、Worker 崩溃。参数校验、权限拒绝、测试失败和预算耗尽不应盲目重试。使用指数退避并保留错误分类：

$$delay=min(base\times2^{attempt-1}, cap)$$

取消必须向下游传播：停止 Agent、撤销等待的 Tool、标记 Run、释放租约。恢复前读取 Checkpoint 和工作区状态，且写操作要使用阶段 7 的幂等键。

## 六、验收

- 为任务领取设计单一写者或原子租约；
- 为每个 Run 创建并校验独立 Workspace；
- 为 Shell 执行配置资源、路径、网络和凭据边界；
- 定义可重试和不可重试错误表；
- 证明取消、超时和重启不会重复执行高风险动作。
