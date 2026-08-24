from fast_api_test_app.schemas import TaskCreateRequest, TaskResponse


_tasks: dict[int, TaskResponse] = {
    1: TaskResponse(
        id=1,
        title="Task 1",
        description="Description 1",
        completed=False,
    ),
    2: TaskResponse(
        id=2,
        title="Task 2",
        description="Description 2",
        completed=True,
    ),
}
_next_task_id = 3


def list_tasks() -> list[TaskResponse]:
    return list(_tasks.values())


def find_task_by_id(task_id: int) -> TaskResponse | None:
    return _tasks.get(task_id)


def create_task(task: TaskCreateRequest) -> TaskResponse:
    global _next_task_id

    created_task = TaskResponse(id=_next_task_id, **task.model_dump())
    _tasks[_next_task_id] = created_task
    _next_task_id += 1
    return created_task


def update_task(
    task_id: int,
    task: TaskCreateRequest,
) -> TaskResponse | None:
    if task_id not in _tasks:
        return None

    updated_task = TaskResponse(id=task_id, **task.model_dump())
    _tasks[task_id] = updated_task
    return updated_task


def delete_task(task_id: int) -> bool:
    return _tasks.pop(task_id, None) is not None


def reset_tasks() -> None:
    global _next_task_id

    _tasks.clear()
    _tasks.update(
        {
            1: TaskResponse(
                id=1,
                title="Task 1",
                description="Description 1",
                completed=False,
            ),
            2: TaskResponse(
                id=2,
                title="Task 2",
                description="Description 2",
                completed=True,
            ),
        }
    )
    _next_task_id = 3