from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.core.task_manager import TaskManager
from app.core.ws import protocol
from app.models.task import UserItem

from .conftest import LifecycleHarness


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _task_statuses(messages: list[dict[str, Any]]) -> list[str]:
    statuses: list[str] = []
    for message in messages:
        task_info = message.get("data", {}).get("task_info")
        if message.get("type") == protocol.TASK_INFO_UPDATED and task_info:
            statuses.append(task_info[0]["status"])
    return statuses


def _user_statuses(messages: list[dict[str, Any]]) -> list[str]:
    statuses: list[str] = []
    for message in messages:
        task_info = message.get("data", {}).get("task_info")
        if message.get("type") == protocol.TASK_INFO_UPDATED and task_info:
            statuses.append(task_info[0]["userList"][0]["status"])
    return statuses


def _assert_ordered_subsequence(actual: list[str], expected: list[str]) -> None:
    position = 0
    for value in actual:
        if position < len(expected) and value == expected[position]:
            position += 1
    assert position == len(expected), f"expected ordered {expected}, got {actual}"


async def _wait_until_cleaned(task_id) -> None:
    async with asyncio.timeout(2.0):
        while task_id in TaskManager.task_info or task_id in TaskManager.task_handler:
            await asyncio.sleep(0)


async def _complete_task(harness: LifecycleHarness) -> tuple[Any, dict[str, Any]]:
    task_id = await TaskManager.add_task(mode="AutoProxy", id=harness.script_id)
    handler = TaskManager.task_handler[task_id]

    async with asyncio.timeout(2.0):
        await harness.control.started.wait()
    harness.control.release.set()

    accomplish = await harness.collector.wait_for(
        lambda message: message.get("id") == str(task_id)
        and message.get("type") == protocol.TASK_COMPLETED
    )
    async with asyncio.timeout(2.0):
        await handler.accomplish.wait()
    await _wait_until_cleaned(task_id)
    return task_id, accomplish


async def test_task_completes_with_ordered_statuses(
    lifecycle_harness: LifecycleHarness,
) -> None:
    task_id, accomplish = await _complete_task(lifecycle_harness)
    task_messages = [
        message
        for message in lifecycle_harness.collector.messages
        if message["id"] == str(task_id)
    ]

    _assert_ordered_subsequence(_task_statuses(task_messages), ["运行", "完成"])
    _assert_ordered_subsequence(
        _user_statuses(task_messages), ["等待", "运行中", "完成"]
    )
    assert accomplish["data"]["task_info"][0]["status"] == "完成"
    assert (
        sum(message["type"] == protocol.TASK_COMPLETED for message in task_messages)
        == 1
    )
    assert not any(
        message["type"] == protocol.TASK_NOTICE
        and message["data"].get("level") == "error"
        for message in task_messages
    )
    assert lifecycle_harness.control.finalized.is_set()
    assert task_id not in TaskManager.task_info
    assert task_id not in TaskManager.task_handler


async def test_task_failure_reports_abnormal_terminal_state(
    lifecycle_harness: LifecycleHarness,
) -> None:
    lifecycle_harness.control.behavior = "fail"
    task_id, accomplish = await _complete_task(lifecycle_harness)

    final_script = accomplish["data"]["task_info"][0]
    assert final_script["status"] == "异常"
    assert final_script["userList"][0]["status"] == "失败"
    assert lifecycle_harness.control.finalized.is_set()
    assert task_id not in TaskManager.task_info
    assert task_id not in TaskManager.task_handler


async def test_task_crash_runs_crash_handler_and_finalizer(
    lifecycle_harness: LifecycleHarness,
) -> None:
    lifecycle_harness.control.behavior = "crash"
    task_id = await TaskManager.add_task(
        mode="AutoProxy",
        id=lifecycle_harness.script_id,
    )
    handler = TaskManager.task_handler[task_id]

    accomplish = await lifecycle_harness.collector.wait_for(
        lambda message: message.get("id") == str(task_id)
        and message.get("type") == protocol.TASK_COMPLETED
    )
    async with asyncio.timeout(2.0):
        await handler.accomplish.wait()
    await _wait_until_cleaned(task_id)

    assert isinstance(lifecycle_harness.control.crash_error, RuntimeError)
    assert str(lifecycle_harness.control.crash_error) == "模拟运行时崩溃"
    assert lifecycle_harness.control.crashed.is_set()
    assert lifecycle_harness.control.finalized.is_set()
    assert accomplish["data"]["task_info"][0]["status"] == "异常"
    assert task_id not in TaskManager.task_info
    assert task_id not in TaskManager.task_handler


async def test_running_task_can_be_cancelled(
    lifecycle_harness: LifecycleHarness,
) -> None:
    lifecycle_harness.control.behavior = "block"
    task_id = await TaskManager.add_task(
        mode="AutoProxy",
        id=lifecycle_harness.script_id,
    )

    async with asyncio.timeout(2.0):
        await lifecycle_harness.control.started.wait()
    script_item = TaskManager.task_info[task_id].script_list[0]
    script_item.user_list.append(
        UserItem(user_id="already-failed", name="已失败用户", status="异常")
    )
    await TaskManager.stop_task(str(task_id))
    accomplish = await lifecycle_harness.collector.wait_for(
        lambda message: message.get("id") == str(task_id)
        and message.get("type") == protocol.TASK_COMPLETED
    )
    await _wait_until_cleaned(task_id)

    final_script = accomplish["data"]["task_info"][0]
    assert final_script["status"] == "取消"
    assert final_script["userList"][0]["status"] == "取消"
    assert final_script["userList"][1]["status"] == "异常"
    assert not lifecycle_harness.control.release.is_set()
    assert lifecycle_harness.control.finalized.is_set()
    assert task_id not in TaskManager.task_info
    assert task_id not in TaskManager.task_handler
