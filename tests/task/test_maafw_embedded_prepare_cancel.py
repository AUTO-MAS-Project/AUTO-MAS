"""MaaFW 内置任务取消时，对环境准备线程的等待必须有界。

后端关机走 ``POST /api/core/close`` -> 中止任务，Runtime 只给约 5 秒；此前任务在
取消路径上无界等待 ``prepare_environment`` 线程跑完（uv 正在装依赖），后端退不出
而被强杀。现在置位取消令牌后只等 ``grace_seconds``，超时就放弃并让收尾任务在
后台继续。
"""

from __future__ import annotations

import asyncio
import time

import pytest

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW.tools.embedded import runner_task


@pytest.mark.asyncio
async def test_abandons_preparation_that_ignores_cancel_within_grace() -> None:
    loop = asyncio.get_running_loop()
    never_done: asyncio.Future[object] = loop.create_future()
    released: list[object] = []
    logs: list[str] = []

    started = time.monotonic()
    await runner_task._abandon_environment_preparation(
        never_done,
        release=released.append,
        grace_seconds=0.3,
        send_log=logs.append,
    )
    elapsed = time.monotonic() - started

    assert elapsed < 2.0
    assert released == []
    assert logs and "放弃等待" in logs[0]
    # 收尾任务转入后台并被强引用，准备一旦完成仍会释放租约。
    pending = list(runner_task._ABANDONED_PREPARATION_CLEANUPS)
    assert len(pending) == 1
    never_done.set_result("env")
    await asyncio.wait_for(pending[0], timeout=2)
    assert released == ["env"]
    assert runner_task._ABANDONED_PREPARATION_CLEANUPS == set()


@pytest.mark.asyncio
async def test_releases_environment_when_preparation_finishes_in_time() -> None:
    async def finishes_soon() -> str:
        await asyncio.sleep(0.05)
        return "prepared-env"

    released: list[object] = []
    await runner_task._abandon_environment_preparation(
        asyncio.ensure_future(finishes_soon()),
        release=released.append,
        grace_seconds=2.0,
    )
    assert released == ["prepared-env"]


@pytest.mark.asyncio
async def test_failed_preparation_returns_immediately_without_release() -> None:
    async def fails() -> str:
        raise RuntimeError("install cancelled")

    released: list[object] = []
    await runner_task._abandon_environment_preparation(
        asyncio.ensure_future(fails()),
        release=released.append,
        grace_seconds=2.0,
    )
    assert released == []
