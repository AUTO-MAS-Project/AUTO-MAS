"""PR #1719 的退出边界、命令归属和平台装配回归。"""

import asyncio
from contextlib import suppress
from unittest.mock import Mock

import psutil
import pytest

from app.models.config import HSRConfig
from app.task.HSR.tools.account_switch import configure_m7a_runner
from app.task.HSR.tools.m7a_runtime import M7ARunner
from tests.task.test_hsr_m7a_lifecycle import cleanup, inherited_child, wait_until
from tests.task.test_hsr_m7a_lifecycle import simulator as simulator


@pytest.mark.parametrize("tail_stream", ["stdout", "stderr"])
def test_deadline_exit_drains_already_written_failure(
    simulator, monkeypatch, tail_stream
):
    build, root, processes = simulator
    other = "stderr" if tail_stream == "stdout" else "stdout"
    runner = build(
        "import sys, time\n"
        f"print('native output', file=sys.{other}, flush=True)\n"
        "time.sleep(0.25)\n"
        f"print('无法切换到指定游戏界面', file=sys.{tail_stream}, flush=True)\n",
        managed=True,
    )
    original_open = runner._process_manager.open_process

    async def scenario():
        release_reader = asyncio.Event()

        async def open_with_delayed_reader(*args, **kwargs):
            await original_open(*args, **kwargs)
            stream = getattr(processes[-1], tail_stream)
            original_readline = stream.readline

            async def delayed_readline():
                await release_reader.wait()
                return await original_readline()

            monkeypatch.setattr(stream, "readline", delayed_readline)

        monkeypatch.setattr(
            runner._process_manager, "open_process", open_with_delayed_reader
        )
        before = set(asyncio.all_tasks())
        task = asyncio.create_task(runner.run_task("power", timeout=0.35))

        async def release_after_exit():
            await wait_until(lambda: processes and processes[0].returncode is not None)
            await asyncio.sleep(0.12)
            release_reader.set()

        releaser = asyncio.create_task(release_after_exit())
        try:
            result = await asyncio.wait_for(task, timeout=2)
            assert processes[0].returncode == 0
            assert not result.success
            assert "无法切换到指定游戏界面" in result.error
            await releaser
            await asyncio.sleep(0)
            assert not (set(asyncio.all_tasks()) - before)
        finally:
            release_reader.set()
            releaser.cancel()
            await asyncio.gather(releaser, return_exceptions=True)
            await cleanup(processes, root)

    asyncio.run(scenario())


@pytest.mark.parametrize("cancel", [None, "waiting", "active"])
def test_concurrent_commands_own_their_processes(simulator, cancel):
    build, root, processes = simulator
    runner = build(
        "import pathlib, sys, time\n"
        "name = sys.argv[-1]\n"
        "pathlib.Path(name + '.started').touch()\n"
        "print(name, flush=True)\n"
        "while not pathlib.Path(name + '.release').exists(): time.sleep(0.005)\n",
        managed=True,
    )

    async def scenario():
        before = set(asyncio.all_tasks())
        first = asyncio.create_task(runner.run_task("first", timeout=5))
        second = None
        try:
            await wait_until(lambda: (root / "first.started").exists())
            second = asyncio.create_task(runner.run_task("second", timeout=5))
            await asyncio.sleep(0.05)
            assert processes[0].returncode is None
            assert not (root / "second.started").exists()
            if cancel == "waiting":
                second.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await second
                assert processes[0].returncode is None
                (root / "first.release").touch()
                assert (await first).success
                assert len(processes) == 1
            else:
                if cancel == "active":
                    first.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await first
                else:
                    (root / "first.release").touch()
                    assert (await first).output == "first"
                await wait_until(lambda: (root / "second.started").exists())
                assert processes[0].returncode is not None
                assert processes[1].returncode is None
                (root / "second.release").touch()
                result = await second
                assert result.success and result.output == "second"
            assert runner._process_manager.main_process is None
            await asyncio.sleep(0)
            assert not (set(asyncio.all_tasks()) - before)
        finally:
            for name in ("first", "second"):
                (root / f"{name}.release").touch()
            for task in (first, second):
                if task is not None:
                    task.cancel()
            await asyncio.gather(
                *(t for t in (first, second) if t), return_exceptions=True
            )
            await cleanup(processes, root)

    asyncio.run(scenario())


def test_next_command_waits_for_previous_cleanup(simulator, monkeypatch):
    build, root, processes = simulator
    runner = build("import sys\nprint(sys.argv[-1], flush=True)\n", managed=True)
    original_cleanup = runner._cleanup_process

    async def scenario():
        cleaning = asyncio.Event()
        release = asyncio.Event()

        async def delayed_cleanup(proc):
            cleaning.set()
            await release.wait()
            await original_cleanup(proc)

        monkeypatch.setattr(runner, "_cleanup_process", delayed_cleanup)
        first = asyncio.create_task(runner.run_task("first", timeout=3))
        second = None
        try:
            await asyncio.wait_for(cleaning.wait(), timeout=2)
            second = asyncio.create_task(runner.run_task("second", timeout=3))
            await asyncio.sleep(0.05)
            assert len(processes) == 1
            assert not second.done()
            release.set()
            assert (await first).output == "first"
            assert (await second).output == "second"
        finally:
            release.set()
            for task in (first, second):
                if task is not None:
                    task.cancel()
            await asyncio.gather(
                *(t for t in (first, second) if t), return_exceptions=True
            )
            await cleanup(processes, root)

    asyncio.run(scenario())


@pytest.mark.parametrize("platform", ["Cloud", "Client"])
def test_observed_descendant_after_parent_exit_uses_platform_policy(
    simulator, platform
):
    build, root, processes = simulator
    runner = build(
        inherited_child(code=7).rsplit("sys.exit", 1)[0] + "import time\n"
        "while not pathlib.Path('exit').exists(): time.sleep(0.005)\n"
        "sys.exit(7)\n",
        managed=True,
        platform=platform,
    )
    assert runner.kill_tree is (platform == "Cloud")

    async def scenario():
        task = asyncio.create_task(runner.run_task("power", timeout=5))
        try:
            await wait_until(lambda: (root / "child.pid").exists())
            # 给真实树快照留出时间，模拟正常执行一段时间后才异常退出的 M7A。
            await asyncio.sleep(0.4)
            child = psutil.Process(int((root / "child.pid").read_text()))
            (root / "exit").touch()
            result = await asyncio.wait_for(task, timeout=3)
            assert not result.success and result.returncode == 7
            if platform == "Cloud":
                with suppress(psutil.NoSuchProcess):
                    assert (
                        not child.is_running() or child.status() == psutil.STATUS_ZOMBIE
                    )
            else:
                assert child.is_running() and child.status() != psutil.STATUS_ZOMBIE
            assert runner._process_manager.main_process is None
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await cleanup(processes, root)

    asyncio.run(scenario())


def test_failed_result_keeps_both_native_streams(simulator):
    build, root, processes = simulator
    runner = build(
        "import sys\nprint('native stdout failure', flush=True)\n"
        "print('native stderr detail', file=sys.stderr, flush=True)\nsys.exit(7)\n",
        managed=True,
    )

    async def scenario():
        try:
            result = await runner.run_task("power", timeout=3)
            assert not result.success and result.returncode == 7
            assert result.output == "native stdout failure"
            assert "native stdout failure" in result.error
            assert "native stderr detail" in result.error
        finally:
            await cleanup(processes, root)

    asyncio.run(scenario())


def test_reused_descendant_identity_is_never_killed(tmp_path, monkeypatch):
    # 无法安全制造系统 PID 复用；注入 psutil 对既存进程身份的否定结果。
    runner = M7ARunner(tmp_path)
    configure_m7a_runner(runner, HSRConfig(Game={"Platform": "Cloud"}))
    old_child = Mock(spec=psutil.Process)
    old_child.is_running.return_value = False
    runner._tree_children.add(old_child)

    def no_pid_lookup(_):
        raise AssertionError("禁止根据缓存 PID 重新定位并终止进程")

    monkeypatch.setattr(psutil, "Process", no_pid_lookup)
    asyncio.run(runner.terminate_process_tree())
    old_child.is_running.assert_called_once()
    old_child.kill.assert_not_called()


def test_unobserved_orphan_is_not_guessed_from_pid(simulator, monkeypatch):
    build, root, processes = simulator
    runner = build(inherited_child(code=7), managed=True, platform="Cloud")
    original_remember = runner._remember_process_tree

    async def miss_parent_lifetime(proc):
        await wait_until(lambda: proc.returncode is not None)
        await original_remember(proc)

    monkeypatch.setattr(runner, "_remember_process_tree", miss_parent_lifetime)

    async def scenario():
        try:
            result = await runner.run_task("power", timeout=3)
            assert not result.success and result.returncode == 7
            child = psutil.Process(int((root / "child.pid").read_text()))
            # 从未观测到的孤儿不具有安全归属证据，由测试自身清理，不能扩大扫描。
            assert child.is_running() and child.status() != psutil.STATUS_ZOMBIE
        finally:
            await cleanup(processes, root)

    asyncio.run(scenario())


def test_tree_cleanup_error_still_stops_parent_and_is_reported(simulator, monkeypatch):
    build, root, processes = simulator
    runner = build(
        inherited_child(code=0).rsplit("sys.exit", 1)[0]
        + "print('停止运行', flush=True)\nimport time\ntime.sleep(30)\n",
        managed=True,
        platform="Cloud",
    )
    original_wait = psutil.wait_procs

    def fail_wait(*args, **kwargs):
        raise RuntimeError("tree wait failed")

    monkeypatch.setattr(psutil, "wait_procs", fail_wait)

    async def scenario():
        try:
            result = await asyncio.wait_for(
                runner.run_task("power", timeout=3), timeout=8
            )
            assert not result.success and result.error == "tree wait failed"
            assert processes[0].returncode is not None
            assert runner._process_manager.main_process is None
        finally:
            monkeypatch.setattr(psutil, "wait_procs", original_wait)
            await cleanup(processes, root)

    asyncio.run(scenario())


def test_owned_descendant_access_denied_is_reported(tmp_path):
    runner = M7ARunner(tmp_path)
    configure_m7a_runner(runner, HSRConfig(Game={"Platform": "Cloud"}))
    child = Mock(spec=psutil.Process)
    child.is_running.return_value = True
    child.status.return_value = psutil.STATUS_SLEEPING
    child.kill.side_effect = psutil.AccessDenied(pid=123)
    runner._tree_children.add(child)
    with pytest.raises(RuntimeError, match="后代未能终止"):
        asyncio.run(runner.terminate_process_tree())
    child.kill.assert_called_once()


def test_cancel_stops_process_before_slow_callback_cleanup(simulator):
    build, root, processes = simulator

    async def scenario():
        entered = asyncio.Event()
        cleaning = asyncio.Event()
        release = asyncio.Event()

        async def callback(_):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaning.set()
                await release.wait()

        runner = build(
            "import time\nprint('running', flush=True)\ntime.sleep(30)\n",
            managed=True,
            callback=callback,
        )
        task = asyncio.create_task(runner.run_task("power", timeout=5))
        try:
            await asyncio.wait_for(entered.wait(), timeout=2)
            task.cancel()
            await asyncio.wait_for(cleaning.wait(), timeout=2)
            await wait_until(lambda: processes[0].returncode is not None)
            assert not task.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)
            await cleanup(processes, root)

    asyncio.run(scenario())
