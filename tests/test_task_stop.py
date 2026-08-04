import asyncio
import uuid

from app.api.dispatch import stop_task
from app.core import TaskManager
from app.models.schema import DispatchIn


def test_stopping_missing_task_is_idempotent() -> None:
    task_id = uuid.uuid4()

    assert task_id not in TaskManager.task_handler
    response = asyncio.run(stop_task(DispatchIn(taskId=str(task_id))))
    assert response.code == 200
    assert task_id not in TaskManager.task_handler
