from __future__ import annotations

import asyncio
import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.api.dispatch import router as dispatch_router
from app.api.scripts2 import router as scripts_router
from app.core.task_manager import TaskManager
from app.core.ws import protocol

from .conftest import SpecializedLifecycleHarness


SPECIALIZED_ADAPTERS = ("SRC", "MaaEnd", "OkScript", "Okww")
pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


def _specialized_app() -> FastAPI:
    app = FastAPI()
    app.include_router(scripts_router)
    app.include_router(dispatch_router)
    return app


async def _create_script_and_user(
    client: httpx.AsyncClient,
    harness: SpecializedLifecycleHarness,
) -> tuple[str, str, str]:
    script_response = await client.post(
        "/api/scripts2/add",
        json={"type": harness.adapter_type},
    )
    assert script_response.status_code == 200
    assert script_response.json()["code"] == 200
    script_record = script_response.json()["record"]
    assert script_record["type"] == harness.adapter_type
    assert script_record["available"] is True
    assert "AutoProxy" in script_record["supported_modes"]
    assert script_record["schema"]["groups"]

    script_id = script_record["id"]
    user_response = await client.post(
        "/api/scripts2/users/add",
        json={"scriptId": script_id},
    )
    assert user_response.status_code == 200
    assert user_response.json()["code"] == 200
    user_record = user_response.json()["record"]
    assert user_record["script_id"] == script_id
    assert user_record["type"] == harness.adapter_type
    assert user_record["schema"]["groups"]

    get_response = await client.post(
        "/api/scripts2/get",
        json={"scriptId": script_id},
    )
    assert get_response.status_code == 200
    assert get_response.json()["records"][0]["user_count"] == 1
    return script_id, user_record["id"], user_record["name"]


async def _start_task(client: httpx.AsyncClient, script_id: str) -> str:
    response = await client.post(
        "/api/dispatch/start",
        json={"mode": "AutoProxy", "taskId": script_id},
    )
    assert response.status_code == 200
    assert response.json()["code"] == 200
    return response.json()["taskId"]


async def _wait_for_accomplish(
    harness: SpecializedLifecycleHarness,
    task_id: str,
) -> dict[str, Any]:
    accomplish = await harness.collector.wait_for(
        lambda message: message.get("id") == task_id
        and message.get("type") == protocol.TASK_COMPLETED
    )
    task_uuid = uuid.UUID(task_id)
    async with asyncio.timeout(2.0):
        while (
            task_uuid in TaskManager.task_info
            or task_uuid in TaskManager.task_handler
        ):
            await asyncio.sleep(0)
    return accomplish


def _error_message(
    harness: SpecializedLifecycleHarness,
    task_id: str,
) -> dict[str, Any] | None:
    return next(
        (
            message
            for message in harness.collector.messages
            if message.get("id") == task_id
            and message.get("type") == protocol.TASK_NOTICE
            and message.get("data", {}).get("level") == "error"
        ),
        None,
    )


@pytest.mark.parametrize(
    "specialized_lifecycle_harness",
    SPECIALIZED_ADAPTERS,
    indirect=True,
)
async def test_specialized_adapter_task_completes(
    specialized_lifecycle_harness: SpecializedLifecycleHarness,
) -> None:
    harness = specialized_lifecycle_harness
    transport = httpx.ASGITransport(app=_specialized_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        script_id, user_id, user_name = await _create_script_and_user(client, harness)
        task_id = await _start_task(client, script_id)
        async with asyncio.timeout(2.0):
            await harness.control.started.wait()
        harness.control.release.set()

    accomplish = await _wait_for_accomplish(harness, task_id)
    final_script = accomplish["data"]["task_info"][0]
    assert final_script["script_id"] == script_id
    assert final_script["status"] == "完成"
    assert final_script["userList"] == [
        {"user_id": user_id, "name": user_name, "status": "完成"}
    ]
    assert _error_message(harness, task_id) is None
    assert harness.control.finalized.is_set()


@pytest.mark.parametrize(
    "specialized_lifecycle_harness",
    SPECIALIZED_ADAPTERS,
    indirect=True,
)
async def test_specialized_adapter_task_failure_returns_error(
    specialized_lifecycle_harness: SpecializedLifecycleHarness,
) -> None:
    harness = specialized_lifecycle_harness
    harness.control.behavior = "fail"
    transport = httpx.ASGITransport(app=_specialized_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        script_id, user_id, user_name = await _create_script_and_user(client, harness)
        task_id = await _start_task(client, script_id)
        async with asyncio.timeout(2.0):
            await harness.control.started.wait()
        harness.control.release.set()

    accomplish = await _wait_for_accomplish(harness, task_id)
    final_script = accomplish["data"]["task_info"][0]
    error = _error_message(harness, task_id)
    assert final_script["status"] == "异常"
    assert final_script["userList"] == [
        {"user_id": user_id, "name": user_name, "status": "失败"}
    ]
    assert error is not None
    assert error["data"]["message"] == f"模拟 {harness.adapter_type} 任务失败"
    assert harness.control.finalized.is_set()


@pytest.mark.parametrize(
    "specialized_lifecycle_harness",
    SPECIALIZED_ADAPTERS,
    indirect=True,
)
async def test_specialized_adapter_running_task_can_be_stopped(
    specialized_lifecycle_harness: SpecializedLifecycleHarness,
) -> None:
    harness = specialized_lifecycle_harness
    harness.control.behavior = "block"
    transport = httpx.ASGITransport(app=_specialized_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        script_id, user_id, user_name = await _create_script_and_user(client, harness)
        task_id = await _start_task(client, script_id)
        async with asyncio.timeout(2.0):
            await harness.control.started.wait()
        stop_response = await client.post(
            "/api/dispatch/stop",
            json={"taskId": task_id},
        )

    assert stop_response.status_code == 200
    assert stop_response.json()["code"] == 200
    accomplish = await _wait_for_accomplish(harness, task_id)
    final_script = accomplish["data"]["task_info"][0]
    assert final_script["status"] == "取消"
    assert final_script["userList"] == [
        {"user_id": user_id, "name": user_name, "status": "取消"}
    ]
    assert not harness.control.release.is_set()
    assert harness.control.finalized.is_set()


@pytest.mark.parametrize(
    "specialized_lifecycle_harness",
    SPECIALIZED_ADAPTERS,
    indirect=True,
)
async def test_specialized_adapter_runtime_exception_ends_abnormally(
    specialized_lifecycle_harness: SpecializedLifecycleHarness,
) -> None:
    harness = specialized_lifecycle_harness
    harness.control.behavior = "crash"
    transport = httpx.ASGITransport(app=_specialized_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        script_id, user_id, user_name = await _create_script_and_user(client, harness)
        task_id = await _start_task(client, script_id)

    accomplish = await _wait_for_accomplish(harness, task_id)
    final_script = accomplish["data"]["task_info"][0]
    error = _error_message(harness, task_id)
    assert final_script["status"] == "异常"
    assert final_script["userList"] == [
        {"user_id": user_id, "name": user_name, "status": "异常"}
    ]
    assert isinstance(harness.control.crash_error, RuntimeError)
    assert error is not None
    assert error["data"]["message"] == (
        f"RuntimeError: 模拟 {harness.adapter_type} 运行时异常"
    )
    assert harness.control.crashed.is_set()
    assert harness.control.finalized.is_set()
