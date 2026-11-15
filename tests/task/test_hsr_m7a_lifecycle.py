"""用隔离 Python 进程验证 M7A 生命周期，不运行游戏或真实配置。"""

import asyncio
from contextlib import suppress

import psutil
import pytest

from tests.support.hsr_process import cleanup, inherited_child, wait_until
from tests.support.hsr_process import simulator as simulator


@pytest.mark.parametrize("code", [0, 3])
def test_normal_exit_and_failure(simulator, code):
    build, root, processes = simulator
    session = build(
        f"import sys\nprint('native output', flush=True)\nsys.exit({code})\n"
    )

    async def scenario():
        try:
            result = await asyncio.wait_for(session.run(3), timeout=4)
            assert result.success is (code == 0)
            assert result.returncode == code
        finally:
            await session.close()
            await cleanup(processes, root)

    asyncio.run(scenario())


@pytest.mark.parametrize("marker", ["用户原生来源已结束", "streams closed"])
def test_live_process_is_not_finished_by_source_log_or_eof(simulator, marker):
    build, root, processes = simulator
    session = build(
        "import os, pathlib, time\n"
        f"print({marker!r}, flush=True)\n"
        + ("os.close(1)\nos.close(2)\n" if marker == "streams closed" else "")
        + "pathlib.Path('ready').touch()\ntime.sleep(30)\n"
    )

    async def scenario():
        task = asyncio.create_task(session.run(5))
        try:
            await wait_until(lambda: (root / "ready").exists())
            await asyncio.sleep(0.04)
            assert processes[0].returncode is None
            assert not task.done()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=2)
            assert processes[0].returncode is not None
        finally:
            await session.close()
            await cleanup(processes, root)

    asyncio.run(scenario())


@pytest.mark.parametrize("cancel", [False, True])
def test_timeout_and_manual_cancel_cleanup_owned_resources(simulator, cancel):
    build, root, processes = simulator
    runner = build(
        "import time\nprint('running', flush=True)\ntime.sleep(30)\n", managed=True
    )

    async def scenario():
        before = set(asyncio.all_tasks())
        task = asyncio.create_task(
            runner.run_task("power", timeout=5 if cancel else 0.2)
        )
        try:
            await wait_until(lambda: bool(runner.recent_output_lines))
            if cancel:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(task, timeout=2)
            else:
                result = await asyncio.wait_for(task, timeout=2)
                assert not result.success
                assert result.error == "command timed out after 0.2s"
            assert processes[0].returncode is not None
            assert runner._process_manager.main_process is None
            await asyncio.sleep(0)
            assert not (set(asyncio.all_tasks()) - before)
        finally:
            await cleanup(processes, root)

    asyncio.run(scenario())


@pytest.mark.parametrize("error_type", [ValueError, TimeoutError])
def test_callback_error_stops_process_without_becoming_command_timeout(
    simulator, error_type
):
    build, root, processes = simulator

    async def fail(_):
        raise error_type("output callback failed")

    runner = build(
        "import time\nprint('running', flush=True)\ntime.sleep(30)\n",
        callback=fail,
        managed=True,
    )

    async def scenario():
        before = set(asyncio.all_tasks())
        try:
            result = await asyncio.wait_for(
                runner.run_task("power", timeout=3), timeout=4
            )
            assert not result.success
            assert result.error == "output callback failed"
            assert processes[0].returncode is not None
            assert runner._process_manager.main_process is None
            await asyncio.sleep(0)
            assert not (set(asyncio.all_tasks()) - before)
        finally:
            await cleanup(processes, root)

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", [False, True])
def test_duplicate_completion_signals_and_forced_exit(simulator, failure):
    build, root, processes = simulator
    session = build(
        "import time\nprint('停止运行', flush=True)\nprint('停止运行', flush=True)\n"
        + ("print('无法切换到指定游戏界面', flush=True)\n" if failure else "")
        + "time.sleep(30)\n"
    )

    async def scenario():
        try:
            result = await asyncio.wait_for(session.run(3), timeout=4)
            assert result.success is not failure
            assert processes[0].returncode is not None
            await session.close()
            await session.close()
            assert result.success is not failure
            assert session._closed
        finally:
            await cleanup(processes, root)

    asyncio.run(scenario())


def test_cancel_blocked_output_callback_leaves_no_task(simulator):
    build, root, processes = simulator

    async def scenario():
        entered = asyncio.Event()
        cancelled = asyncio.Event()

        async def block(_):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        runner = build(
            "import time\nprint('running', flush=True)\ntime.sleep(30)\n",
            callback=block,
            managed=True,
        )
        before = set(asyncio.all_tasks())
        task = asyncio.create_task(runner.run_task("power", timeout=3))
        try:
            await asyncio.wait_for(entered.wait(), timeout=2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=2)
            assert cancelled.is_set()
            assert processes[0].returncode is not None
            await asyncio.sleep(0)
            assert not (set(asyncio.all_tasks()) - before)
        finally:
            await cleanup(processes, root)

    asyncio.run(scenario())


@pytest.mark.parametrize("error_type", [OSError, TimeoutError])
def test_stream_read_error_stops_the_process(simulator, monkeypatch, error_type):
    build, root, processes = simulator
    runner = build("import time\ntime.sleep(30)\n", managed=True)
    original_open = runner._process_manager.open_process

    async def open_with_broken_reader(*args, **kwargs):
        await original_open(*args, **kwargs)

        async def broken_read(_):
            raise error_type("stream read failed")

        monkeypatch.setattr(processes[-1].stdout, "read", broken_read)

    monkeypatch.setattr(
        runner._process_manager, "open_process", open_with_broken_reader
    )

    async def scenario():
        before = set(asyncio.all_tasks())
        try:
            result = await asyncio.wait_for(
                runner.run_task("power", timeout=3), timeout=4
            )
            assert not result.success
            assert result.error == "stream read failed"
            assert processes[0].returncode is not None
            await asyncio.sleep(0)
            assert not (set(asyncio.all_tasks()) - before)
        finally:
            await cleanup(processes, root)

    asyncio.run(scenario())


def test_blocked_tail_callback_is_bounded_after_process_exit(simulator):
    build, root, processes = simulator

    async def scenario():
        cancelled = asyncio.Event()

        async def block(_):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        runner = build(
            "print('work completed', flush=True)\n", callback=block, managed=True
        )
        before = set(asyncio.all_tasks())
        try:
            result = await asyncio.wait_for(
                runner.run_task("power", timeout=3), timeout=2
            )
            assert not result.success and result.returncode == 0
            assert result.output == "work completed"
            assert "输出未完整收集" in result.error
            assert cancelled.is_set()
            await asyncio.sleep(0)
            assert not (set(asyncio.all_tasks()) - before)
        finally:
            await cleanup(processes, root)

    asyncio.run(scenario())


def test_managed_runner_can_be_reused_without_old_output(simulator):
    build, root, processes = simulator
    runner = build("import sys\nprint(sys.argv[-1], flush=True)\n", managed=True)

    async def scenario():
        try:
            first = await runner.run_task("power", timeout=3)
            second = await runner.run_task("daily", timeout=3)
            assert first.success and second.success
            assert first.output == "power"
            assert second.output == "daily"
            assert runner.recent_output_lines == ["daily"]
        finally:
            await cleanup(processes, root)

    asyncio.run(scenario())


def test_cancel_during_launch_cleans_tracked_process(simulator, monkeypatch):
    build, root, processes = simulator
    runner = build(inherited_child(code=0), managed=True)
    original_open = runner._process_manager.open_process

    async def hold_launch(*args, **kwargs):
        await original_open(*args, **kwargs)
        await asyncio.Event().wait()

    monkeypatch.setattr(runner._process_manager, "open_process", hold_launch)

    async def scenario():
        before = set(asyncio.all_tasks())
        task = asyncio.create_task(runner.run_task("power", timeout=3))
        try:
            await wait_until(lambda: (root / "child.pid").exists())
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=2)
            assert processes[0].returncode is not None
            assert runner._process_manager.main_process is None
            for fd in (1, 2):
                assert processes[0]._transport.get_pipe_transport(fd).is_closing()
            await asyncio.sleep(0)
            assert not (set(asyncio.all_tasks()) - before)
        finally:
            await cleanup(processes, root)

    asyncio.run(scenario())


@pytest.mark.parametrize("pause", ["pause_on_success", "pause_on_error"])
def test_legacy_pause_crash_keeps_existing_verdict(simulator, pause):
    build, root, processes = simulator
    session = build(
        "import sys\nprint('停止运行', flush=True)\n"
        + (
            "print('无法切换到指定游戏界面', flush=True)\n"
            if pause == "pause_on_error"
            else ""
        )
        + f"print('Traceback: utils/console.py {pause} EOF when reading a line', file=sys.stderr, flush=True)\n"
        "sys.exit(1)\n"
    )

    async def scenario():
        try:
            result = await asyncio.wait_for(session.run(3), timeout=4)
            assert result.success is (pause == "pause_on_success")
            assert result.returncode == 1
        finally:
            await session.close()
            await cleanup(processes, root)

    asyncio.run(scenario())


@pytest.mark.parametrize("cancel", [False, True])
def test_cloud_policy_terminates_the_owned_subtree(simulator, cancel):
    build, root, processes = simulator
    body = inherited_child(code=0).rsplit("sys.exit", 1)[0]
    runner = build(
        body
        + ("print('停止运行', flush=True)\n" if not cancel else "")
        + "import time\ntime.sleep(30)\n",
        managed=True,
        platform="Cloud",
    )
    assert runner.kill_tree is True

    async def scenario():
        before = set(asyncio.all_tasks())
        task = asyncio.create_task(runner.run_task("power", timeout=5))
        try:
            await wait_until(lambda: (root / "child.pid").exists())
            if cancel:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(task, timeout=10)
            else:
                result = await asyncio.wait_for(task, timeout=10)
                assert result.success
            assert processes[0].returncode is not None
            assert runner._process_manager.main_process is None
            with suppress(psutil.NoSuchProcess):
                child = psutil.Process(int((root / "child.pid").read_text()))
                # Windows 的退出句柄可能先于 PID 查询收敛；仍须确认后代确实退出。
                await wait_until(
                    lambda: (
                        not child.is_running() or child.status() == psutil.STATUS_ZOMBIE
                    )
                )
            await asyncio.sleep(0)
            assert not (set(asyncio.all_tasks()) - before)
        finally:
            await cleanup(processes, root)

    asyncio.run(scenario())
