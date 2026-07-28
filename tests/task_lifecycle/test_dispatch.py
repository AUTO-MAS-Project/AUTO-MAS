from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest
from fastapi import FastAPI

from app.api.dispatch import router as dispatch_router
from app.core.task_manager import TaskManager

from .conftest import LifecycleHarness


pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


def _dispatch_app() -> FastAPI:
    app = FastAPI()
    app.include_router(dispatch_router)
    return app


async def _wait_until_cleaned(task_id) -> None:
    async with asyncio.timeout(2.0):
        while task_id in TaskManager.task_info or task_id in TaskManager.task_handler:
            await asyncio.sleep(0)


async def test_dispatch_start_completes_with_websocket_envelope(
    lifecycle_harness: LifecycleHarness,
) -> None:
    transport = httpx.ASGITransport(app=_dispatch_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/dispatch/start",
            json={"mode": "AutoProxy", "taskId": lifecycle_harness.script_id},
        )

    assert response.status_code == 200
    assert response.json()["code"] == 200
    task_id = response.json()["taskId"]

    async with asyncio.timeout(2.0):
        await lifecycle_harness.control.started.wait()
    lifecycle_harness.control.release.set()
    accomplish = await lifecycle_harness.collector.wait_for(
        lambda message: message.get("id") == task_id
        and message.get("type") == "Signal"
        and "Accomplish" in message.get("data", {})
    )
    await _wait_until_cleaned(uuid.UUID(task_id))

    assert set(accomplish) == {"id", "type", "data"}
    assert accomplish["data"]["task_info"][0]["status"] == "完成"
    assert accomplish["data"]["task_info"][0]["userList"][0]["status"] == "完成"


async def test_dispatch_stop_cancels_running_task(
    lifecycle_harness: LifecycleHarness,
) -> None:
    lifecycle_harness.control.behavior = "block"
    transport = httpx.ASGITransport(app=_dispatch_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        start_response = await client.post(
            "/api/dispatch/start",
            json={"mode": "AutoProxy", "taskId": lifecycle_harness.script_id},
        )
        task_id = start_response.json()["taskId"]
        async with asyncio.timeout(2.0):
            await lifecycle_harness.control.started.wait()

        stop_response = await client.post(
            "/api/dispatch/stop",
            json={"taskId": task_id},
        )

    assert start_response.status_code == 200
    assert start_response.json()["code"] == 200
    assert stop_response.status_code == 200
    assert stop_response.json()["code"] == 200
    accomplish = await lifecycle_harness.collector.wait_for(
        lambda message: message.get("id") == task_id
        and message.get("type") == "Signal"
        and "Accomplish" in message.get("data", {})
    )
    final_script = accomplish["data"]["task_info"][0]
    assert final_script["status"] == "取消"
    assert final_script["userList"][0]["status"] == "取消"
