"""启动器更新不能被普通启动超时中止，也不能无限续时。"""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.task.Okww.tools import startup


@pytest.fixture
def launch(tmp_path, monkeypatch):
    log = tmp_path / "logs" / datetime.now().strftime("app.%Y-%m-%d")
    log.parent.mkdir()
    log.write_text("", encoding="utf-8")
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(
        startup, "time", SimpleNamespace(time=lambda: 1000, monotonic=lambda: clock.now)
    )
    original_sleep = asyncio.sleep
    found = asyncio.Event()
    search_finished = asyncio.Event()
    schedule = []

    async def search(*args, **kwargs):
        try:
            await found.wait()
        finally:
            search_finished.set()

    manager = SimpleNamespace(
        open_process=AsyncMock(), search_process=AsyncMock(side_effect=search)
    )

    async def sleep(delay):
        clock.now += delay
        for at, action in list(schedule):
            if clock.now >= at:
                schedule.remove((at, action))
                action()
        await original_sleep(0)

    monkeypatch.setattr(startup.asyncio, "sleep", sleep)

    def emit(message):
        with log.open("a", encoding="utf-8") as file:
            file.write(
                f"2026-11-04 INFO pyappify_lib::emitter: INFO [ok-ww]: {message}\n"
            )

    async def run():
        await startup.start_okww(
            manager, tmp_path / "ok-ww.exe", [], target=object(), on_log=AsyncMock()
        )

    return SimpleNamespace(
        run=run,
        schedule=schedule,
        emit=emit,
        found=found,
        clock=clock,
        manager=manager,
        log=log,
        search_finished=search_finished,
    )


@pytest.mark.asyncio
async def test_update_allows_worker_to_start_after_sixty_seconds(launch):
    launch.schedule.extend(
        [(30, lambda: launch.emit("Downloading package-a")), (100, launch.found.set)]
    )
    await launch.run()
    assert launch.clock.now >= 100


@pytest.mark.asyncio
async def test_historical_logs_do_not_extend_startup(launch):
    launch.emit("Downloading old-package")
    with pytest.raises(RuntimeError, match="60"):
        await launch.run()
    assert launch.clock.now == 60


@pytest.mark.asyncio
async def test_repeated_progress_does_not_extend_stall_deadline(launch):
    launch.schedule.extend(
        (at, lambda: launch.emit("Downloading same-package"))
        for at in range(10, 400, 10)
    )
    with pytest.raises(RuntimeError, match="5 分钟"):
        await launch.run()
    assert launch.clock.now == 310


@pytest.mark.asyncio
async def test_unrelated_output_does_not_extend_startup(launch):
    launch.schedule.append((30, lambda: launch.emit("Repository already exists")))
    with pytest.raises(RuntimeError, match="60"):
        await launch.run()


@pytest.mark.asyncio
async def test_progress_cannot_exceed_total_limit(launch):
    launch.schedule.extend(
        (at, lambda at=at: launch.emit(f"Downloading package-{at}"))
        for at in range(10, 2000, 100)
    )
    with pytest.raises(RuntimeError, match="30 分钟"):
        await launch.run()
    assert launch.clock.now == 1800


@pytest.mark.asyncio
async def test_cancellation_waits_for_process_search_cleanup(launch):
    launch.schedule.append((10, lambda: asyncio.current_task().cancel()))
    with pytest.raises(asyncio.CancelledError):
        await launch.run()
    assert launch.search_finished.is_set()


@pytest.mark.asyncio
async def test_alternating_retries_do_not_extend_stall_deadline(launch):
    # 下载依赖失败后重试同一组包，没有新的包或下载进度，不应续时。
    launch.schedule.extend(
        (at, lambda at=at: launch.emit(f"Downloading package-{at % 20}"))
        for at in range(10, 400, 10)
    )
    with pytest.raises(RuntimeError, match="5 分钟"):
        await launch.run()
    assert launch.clock.now == 320


@pytest.mark.asyncio
async def test_normal_start_returns_without_waiting_for_timeout(launch):
    launch.schedule.append((2, launch.found.set))
    await launch.run()
    assert launch.clock.now < 3


@pytest.mark.asyncio
async def test_log_replacement_keeps_update_progress(launch):
    def rotate():
        launch.log.rename(launch.log.with_suffix(".previous"))
        launch.emit("Downloading new-package")

    launch.schedule.extend([(30, rotate), (100, launch.found.set)])
    await launch.run()
    assert launch.clock.now >= 100


@pytest.mark.asyncio
async def test_dependency_installation_progress_extends_wait(launch):
    launch.schedule.extend(
        [
            (
                30,
                lambda: launch.emit(
                    "Content of 'requirements.txt' changed. Syncing dependencies."
                ),
            ),
            (300, lambda: launch.emit("Installing collected packages: package-a")),
            (500, launch.found.set),
        ]
    )
    await launch.run()
    assert launch.clock.now >= 500
