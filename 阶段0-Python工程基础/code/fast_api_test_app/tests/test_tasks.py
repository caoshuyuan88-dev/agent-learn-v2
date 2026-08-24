import pytest
from fastapi.testclient import TestClient

from fast_api_test_app.main import app
from fast_api_test_app.services import task_service


@pytest.fixture(autouse=True)
def reset_task_store() -> None:
    task_service.reset_tasks()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_list_tasks(client: TestClient) -> None:
    response = client.get("/tasks")

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.json()[0]["id"] == 1


def test_create_task(client: TestClient) -> None:
    response = client.post(
        "/tasks",
        json={"title": "测试任务", "description": "描述"},
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": 3,
        "title": "测试任务",
        "description": "描述",
        "completed": False,
    }


def test_get_task_and_missing_task(client: TestClient) -> None:
    found_response = client.get("/tasks/1")
    missing_response = client.get("/tasks/999")

    assert found_response.status_code == 200
    assert found_response.json()["title"] == "Task 1"
    assert missing_response.status_code == 404


def test_update_task(client: TestClient) -> None:
    response = client.patch(
        "/tasks/1",
        json={"title": "已更新", "completed": True},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "已更新"
    assert response.json()["completed"] is True


def test_delete_task(client: TestClient) -> None:
    response = client.delete("/tasks/1")
    missing_response = client.get("/tasks/1")

    assert response.status_code == 200
    assert missing_response.status_code == 404


def test_validation_error_for_missing_title(client: TestClient) -> None:
    response = client.post("/tasks", json={"completed": False})

    assert response.status_code == 422