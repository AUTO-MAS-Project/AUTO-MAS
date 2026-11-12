"""启动器更新不能被普通启动超时中止，也不能无限续时。"""

import asyncio
from datetime import datetime, timedelta
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

    def emit_to(name, message):
        with (log.parent / name).open("a", encoding="utf-8") as file:
            file.write(
                f"2026-11-04 INFO pyappify_lib::emitter: INFO [ok-ww]: {message}\n"
            )

    async def run(args=()):
        await startup.start_okww(
            manager,
            tmp_path / "ok-ww.exe",
            list(args),
            target=object(),
            on_log=AsyncMock(),
        )

    return SimpleNamespace(
        run=run,
        schedule=schedule,
        emit=emit,
        emit_to=emit_to,
        found=found,
        clock=clock,
        manager=manager,
        log=log,
        search_finished=search_finished,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        "ValueError: Task not found: MultiAccountConfigTask",
        "argument -t/--task: invalid int value: 'MultiAccountConfigTask'",
    ],
)
async def test_native_switch_not_supported_reports_actionable_error(launch, error):
    launch.schedule.append((1, lambda: launch.emit(error)))
    with pytest.raises(RuntimeError, match="当前ok-ww版本不支持或已移除原生账号切换"):
        await launch.run(["-t", "MultiAccountConfigTask", "-e"])
    assert launch.clock.now < 60
    assert launch.search_finished.is_set()


@pytest.mark.asyncio
async def test_update_allows_worker_to_start_after_sixty_seconds(launch):
    launch.schedule.extend(
        [(30, lambda: launch.emit("Downloading package-a")), (100, launch.found.set)]
    )
    await launch.run()
    assert launch.clock.now >= 100


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message,args",
    [
        ("Downloading old-package", []),
        (
            "ValueError: Task not found: MultiAccountConfigTask",
            ["-t", "MultiAccountConfigTask", "-e"],
        ),
    ],
)
async def test_historical_logs_do_not_affect_current_startup(launch, message, args):
    launch.emit(message)
    with pytest.raises(RuntimeError, match="60"):
        await launch.run(args)
    assert launch.clock.now == 60


@pytest.mark.asyncio
async def test_repeated_progress_does_not_extend_stall_deadline(launch):
    launch.schedule.extend(
        (at, lambda: launch.emit("Downloading same-package"))
        for at in range(10, 400, 10)
    )
    with pytest.raises(RuntimeError, match="5 分钟"):
        await launch.run()
    assert launch.clock.now == 320


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
    assert launch.clock.now == 330


@pytest.mark.asyncio
async def test_quiet_download_past_repeat_window_survives(launch):
    # 非 tty 下 pip 输出「Downloading 包名」一行后静默下载：大包慢速下载期
    # 可超过 5 分钟无完整新行，不应被判为停滞而提前中止。
    launch.schedule.extend(
        [
            (30, lambda: launch.emit("Downloading large-package")),
            (400, launch.found.set),
        ]
    )
    await launch.run()
    assert launch.clock.now >= 400


@pytest.mark.asyncio
async def test_single_repeat_then_silence_survives(launch):
    # 下载重试打印一次旧进展后转入静默下载是真实路径：单次重复不应让刷屏
    # 判定永久武装，静默窗口须继续生效。
    launch.schedule.extend(
        [
            (30, lambda: launch.emit("Downloading large-package")),
            (40, lambda: launch.emit("Downloading large-package")),
            (400, launch.found.set),
        ]
    )
    await launch.run()
    assert launch.clock.now >= 400


@pytest.mark.asyncio
async def test_late_single_repeat_then_silence_survives(launch):
    launch.schedule.extend(
        [
            (30, lambda: launch.emit("Downloading large-package")),
            (300, lambda: launch.emit("Downloading large-package")),
            (400, launch.found.set),
        ]
    )
    await launch.run()
    assert launch.clock.now >= 400


@pytest.mark.asyncio
async def test_utc_dated_log_file_is_picked_up(launch):
    # 上游按 UTC 日期滚动命名日志；北京时间凌晨 UTC 当日即本地昨天，启动前
    # 该文件不存在时启动后新建的文件也必须被发现，否则进展漏读、60 秒误判。
    utc_name = (datetime.now() - timedelta(days=1)).strftime("app.%Y-%m-%d")
    launch.schedule.extend(
        [
            (30, lambda: launch.emit_to(utc_name, "Downloading utc-package")),
            (100, launch.found.set),
        ]
    )
    await launch.run()
    assert launch.clock.now >= 100


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments,expected",
    [
        ("", ["-krqlv=hd"]),
        ("-Res=1920x1080", ["-krqlv=hd", "-Res=1920x1080"]),
        ("-krqlv=uhd -Res=1920x1080", ["-krqlv=uhd", "-Res=1920x1080"]),
        ("-krqlv=sd", ["-krqlv=sd"]),
        ("-krqlv=hd -Res=1920x1080 -KRQLV=uhd", ["-Res=1920x1080", "-KRQLV=uhd"]),
    ],
)
async def test_direct_launch_uses_explicit_resource_tier(tmp_path, arguments, expected):
    from app.models.config.script import OkwwConfig
    from app.task.Okww.AutoProxy import AutoProxyTask

    client = tmp_path / "Client-Win64-Shipping.exe"
    manager = SimpleNamespace(open_process=AsyncMock())
    task = SimpleNamespace(
        game_process_path=client,
        game_manager=manager,
        _updated_game_quality=None,
        script_config=OkwwConfig.model_validate({"Game": {"Arguments": arguments}}),
        _push_dispatch_log=AsyncMock(),
    )
    await AutoProxyTask._launch_game_direct(task)
    manager.open_process.assert_awaited_once_with(client, *expected)
