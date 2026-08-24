from fastapi import APIRouter, HTTPException, status

from fast_api_test_app import schemas
from fast_api_test_app.services import task_service

router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
)


@router.get("", response_model=list[schemas.TaskResponse])
async def get_tasks() -> list[schemas.TaskResponse]:
    return task_service.list_tasks()


@router.post(
    "",
    response_model=schemas.TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_task(
    task: schemas.TaskCreateRequest,
) -> schemas.TaskResponse:
    return task_service.create_task(task)


@router.get("/{task_id}", response_model=schemas.TaskResponse)
async def get_task(task_id: int) -> schemas.TaskResponse:
    task = task_service.find_task_by_id(task_id)
    if (task is None):
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/{task_id}", response_model=schemas.TaskResponse)
async def update_task(
    task_id: int,
    task: schemas.TaskCreateRequest,
) -> schemas.TaskResponse:
    updated_task = task_service.update_task(task_id, task)
    if updated_task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return updated_task


@router.delete("/{task_id}", response_model=dict[str, str])
async def delete_task(task_id: int) -> dict[str, str]:
    if not task_service.delete_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": f"Task {task_id} deleted successfully"}