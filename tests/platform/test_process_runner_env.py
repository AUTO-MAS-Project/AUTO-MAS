"""Optional child environments do not change process cleanup or host state."""

import asyncio
import os
import sys
import threading
import time
from contextlib import suppress
from unittest.mock import AsyncMock, Mock

import psutil
import pytest

from app.utils.common.process import runner as process_runner


@pytest.mark.asyncio
async def test_environment_is_scoped_to_child_and_not_logged(monkeypatch):
    monkeypatch.setenv("MAS_RUNNER_TEST", "host-value")
    logger = Mock()
    monkeypatch.setattr(process_runner, "logger", logger)
    environment = {**os.environ, "MAS_RUNNER_TEST": "private-child-value"}
    result = await process_runner.ProcessRunner.run_process(
        sys.executable,
        "-I",
        "-c",
        "import os; print(os.environ['MAS_RUNNER_TEST'])",
        env=environment,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "private-child-value"
    assert os.environ["MAS_RUNNER_TEST"] == "host-value"
    assert "private-child-value" not in repr(logger.mock_calls)
    inherited = await process_runner.ProcessRunner.run_process(
        sys.executable, "-I", "-c", "import os; print(os.environ['MAS_RUNNER_TEST'])"
    )
    assert inherited.stdout.strip() == "host-value"


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_environment_preserves_timeout_and_cancel_cleanup(monkeypatch, cancelled):
    created = []
    create = process_runner.create_subprocess

    async def record(*args, **kwargs):
        process = await create(*args, **kwargs)
        created.append(process)
        return process

    monkeypatch.setattr(process_runner, "create_subprocess", record)
    task = asyncio.create_task(
        process_runner.ProcessRunner.run_process(
            sys.executable,
            "-I",
            "-c",
            "import time; time.sleep(30)",
            timeout=10 if cancelled else 0.1,
            env=dict(os.environ),
        )
    )
    if cancelled:
        async with asyncio.timeout(10):
            while not created:
                await asyncio.sleep(0.01)
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancelled else TimeoutError):
        await task
    assert created and created[0].returncode is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_stop", ["cancel", "timeout"])
async def test_repeated_cancel_waits_for_process_tree_cleanup(
    monkeypatch, initial_stop
):
    """依赖构建/安装取消后，清理线程未停进程之前不能交还目录。"""
    created = []
    ready = asyncio.Event()
    stopping, release = threading.Event(), threading.Event()
    create = process_runner.create_subprocess
    terminate = process_runner._terminate_process_tree

    async def record(*args, **kwargs):
        process = await create(*args, **kwargs)
        created.append(process)
        ready.set()
        return process

    def stop_tree(pid, *, grace_period):
        stopping.set()
        assert release.wait(5)
        terminate(pid, grace_period=grace_period)

    monkeypatch.setattr(process_runner, "create_subprocess", record)
    monkeypatch.setattr(process_runner, "_terminate_process_tree", stop_tree)
    task = asyncio.create_task(
        process_runner.ProcessRunner.run_process(
            sys.executable,
            "-I",
            "-c",
            "import time; time.sleep(30)",
            timeout=30 if initial_stop == "cancel" else 0.05,
            kill_tree_on_cancel=True,
        )
    )
    try:
        await asyncio.wait_for(ready.wait(), 3)
        if initial_stop == "cancel":
            task.cancel()
        assert await asyncio.to_thread(stopping.wait, 3)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=0.05)
        assert not done, "进程清理仍在执行，重复取消不能提前结束等待"
        assert created[0].returncode is None
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        for process in created:
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
            await process.wait()
    assert task.cancelled()
    assert created[0].returncode is not None


@pytest.mark.asyncio
async def test_cancel_with_full_output_pipe_finishes_cleanup(monkeypatch):
    """communicate 被取消后，必须排空并释放已填满的管道。"""
    created = []
    ready = asyncio.Event()
    stopping, release = threading.Event(), threading.Event()
    create = process_runner.create_subprocess
    terminate = process_runner._terminate_process_tree

    async def record(*args, **kwargs):
        process = await create(*args, **kwargs)
        created.append(process)
        ready.set()
        return process

    def stop_tree(pid, *, grace_period):
        stopping.set()
        assert release.wait(5)
        terminate(pid, grace_period=grace_period)

    monkeypatch.setattr(process_runner, "create_subprocess", record)
    monkeypatch.setattr(process_runner, "_terminate_process_tree", stop_tree)
    task = asyncio.create_task(
        process_runner.ProcessRunner.run_process(
            sys.executable,
            "-I",
            "-c",
            "import os\nwhile True: os.write(1, b'x' * 65536)\n",
            timeout=30,
            kill_tree_on_cancel=True,
        )
    )
    try:
        await asyncio.wait_for(ready.wait(), 3)
        task.cancel()
        assert await asyncio.to_thread(stopping.wait, 3)
        async with asyncio.timeout(3):
            while not created[0].stdout._paused:
                await asyncio.sleep(0.005)
        release.set()
        done, _ = await asyncio.wait({task}, timeout=1)
        assert done, "进程已经终止，但未排空 stdout 导致回收一直不结束"
        assert created[0]._transport.get_pipe_transport(1).is_closing()
    finally:
        release.set()
        if created and (
            not task.done()
            or not created[0]._transport.get_pipe_transport(1).is_closing()
        ):
            await created[0].communicate()
        await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()
    assert created[0].returncode is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
@pytest.mark.parametrize("kill_tree", [False, True])
async def test_stop_releases_pipes_inherited_by_a_background_service(
    monkeypatch, tmp_path, cancelled, kill_tree
):
    """命令退出后，后台服务持有管道不能阻止超时或取消完成。"""
    pid_path = tmp_path / "service.pid"
    service_code = "import time; time.sleep(30)"
    code = (
        "import subprocess, sys; from pathlib import Path; "
        f"child = subprocess.Popen([sys.executable, '-I', '-c', {service_code!r}], "
        "stdin=subprocess.DEVNULL, stdout=sys.stdout, stderr=sys.stderr, "
        "close_fds=True); Path(sys.argv[1]).write_text(str(child.pid)); sys.exit(127)"
    )
    create = process_runner.create_subprocess
    created = []
    ready = asyncio.Event()
    service = None

    async def record(*args, **kwargs):
        nonlocal service
        process = await create(*args, **kwargs)
        created.append(process)
        async with asyncio.timeout(5):
            while not pid_path.exists() or process.returncode is None:
                await asyncio.sleep(0.01)
        service = psutil.Process(int(pid_path.read_text()))
        ready.set()
        return process

    monkeypatch.setattr(process_runner, "create_subprocess", record)
    task = asyncio.create_task(
        process_runner.ProcessRunner.run_process(
            sys.executable,
            "-I",
            "-c",
            code,
            str(pid_path),
            timeout=30 if cancelled else 0.05,
            kill_tree_on_cancel=kill_tree,
        )
    )
    try:
        await asyncio.wait_for(ready.wait(), 5)
        assert created[0].returncode == 127
        if cancelled:
            task.cancel()
        done, _ = await asyncio.wait({task}, timeout=3)
        assert done, "命令已退出，后台服务持有输出管道不应阻止任务结束"
        expected = (
            asyncio.CancelledError
            if cancelled
            else process_runner.ProcessCleanupUnconfirmed
            if kill_tree
            else TimeoutError
        )
        with pytest.raises(expected) as stopped:
            await task
        assert process_runner.is_process_cleanup_unconfirmed(stopped.value) == kill_tree
        assert service is not None and service.is_running()
        for fd in (1, 2):
            assert created[0]._transport.get_pipe_transport(fd).is_closing()
    finally:
        if service is None and pid_path.exists():
            with suppress(psutil.NoSuchProcess):
                service = psutil.Process(int(pid_path.read_text()))
        if service is not None:
            with suppress(psutil.NoSuchProcess):
                service.kill()
            await asyncio.to_thread(service.wait, timeout=5)
        for process in created:
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_expired_deadline_does_not_launch_a_command(monkeypatch):
    create = AsyncMock()
    monkeypatch.setattr(process_runner, "create_subprocess", create)
    with pytest.raises(TimeoutError):
        await process_runner.ProcessRunner.run_process(sys.executable, deadline=0)
    create.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_deadline_and_cancel_cover_stalled_creation(monkeypatch, cancelled):
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def create(*args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr(process_runner, "create_subprocess", create)
    task = asyncio.create_task(
        process_runner.ProcessRunner.run_process(
            sys.executable,
            timeout=60,
            deadline=time.monotonic() + (30 if cancelled else 0.05),
        )
    )
    async with asyncio.timeout(30):
        await started.wait()
        if cancelled:
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancelled else TimeoutError):
            await task
    assert stopped.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_deadline_reaps_wrapper_and_child_holding_pipes(
    monkeypatch, tmp_path, cancelled
):
    """只有包装进程退出不能释放继承给子进程的输出管道。"""
    pid_path = tmp_path / "child.pid"
    code = (
        "import subprocess, sys, time; from pathlib import Path; "
        "child = subprocess.Popen([sys.executable, '-I', '-c', "
        "'import time; time.sleep(60)']); "
        "Path(sys.argv[1]).write_text(str(child.pid)); time.sleep(60)"
    )
    create = process_runner.create_subprocess
    created = []
    ready = asyncio.Event()
    child = None

    async def record(*args, **kwargs):
        nonlocal child
        wrapper = await create(*args, **kwargs)
        created.append(wrapper)
        while child is None:
            try:
                child = psutil.Process(int(pid_path.read_text()))
            except (OSError, ValueError):
                await asyncio.sleep(0.01)
        ready.set()
        return wrapper

    monkeypatch.setattr(process_runner, "create_subprocess", record)
    task = asyncio.create_task(
        process_runner.ProcessRunner.run_process(
            sys.executable,
            "-I",
            "-c",
            code,
            str(pid_path),
            timeout=30 if cancelled else 0.1,
            deadline=time.monotonic() + 20,
            kill_tree_on_cancel=True,
            if_merge_std=True,
        )
    )
    try:
        async with asyncio.timeout(30):
            await ready.wait()
            if cancelled:
                task.cancel()
            with pytest.raises(asyncio.CancelledError if cancelled else TimeoutError):
                await task
        assert created[0].returncode is not None
        assert child is not None
        with suppress(psutil.NoSuchProcess):
            assert child.status() == psutil.STATUS_ZOMBIE
    finally:
        if child is not None:
            with suppress(psutil.NoSuchProcess):
                child.kill()
        for wrapper in created:
            if wrapper.returncode is None:
                with suppress(ProcessLookupError):
                    wrapper.kill()
        task.cancel()
        with suppress(asyncio.CancelledError, TimeoutError):
            await task


@pytest.mark.asyncio
@pytest.mark.parametrize("stalled_creation", [False, True])
async def test_repeated_cancel_during_creation_reaps_dependency_builder(
    monkeypatch, tmp_path, stalled_creation
):
    """OS spawn precedes async pipe setup; cancellation still owns its children."""
    pid_path = tmp_path / "spawned-child.pid"
    program = (
        "import subprocess, sys, time; from pathlib import Path; "
        "child = subprocess.Popen([sys.executable, '-I', '-c', "
        "'import time; time.sleep(30)'], "
        "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
        "Path(sys.argv[1]).write_text(str(child.pid)); time.sleep(30)"
    )
    loop = asyncio.get_running_loop()
    connect = loop.connect_read_pipe
    connecting, release = asyncio.Event(), asyncio.Event()

    async def delayed_pipe(*args, **kwargs):
        if not connecting.is_set():
            connecting.set()
            await release.wait()
        return await connect(*args, **kwargs)

    monkeypatch.setattr(loop, "connect_read_pipe", delayed_pipe)
    if stalled_creation:
        monkeypatch.setattr(
            process_runner, "_PROCESS_CLEANUP_SECONDS", 0.1, raising=False
        )
    child = None
    task = asyncio.create_task(
        process_runner.ProcessRunner.run_process(
            sys.executable,
            "-I",
            "-c",
            program,
            str(pid_path),
            kill_tree_on_cancel=True,
        )
    )
    try:
        await asyncio.wait_for(connecting.wait(), 3)
        async with asyncio.timeout(3):
            while child is None:
                try:
                    child = psutil.Process(int(pid_path.read_text()))
                except (OSError, ValueError):
                    await asyncio.sleep(0.005)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0.02)
        assert not task.done(), "进程创建尚未交还句柄，取消不能遗失已启动的构建进程"
        if stalled_creation:
            done, _ = await asyncio.wait({task}, timeout=1)
            assert done, "进程创建停滞不能让用户任务一直等待"
            with pytest.raises(asyncio.CancelledError) as stopped:
                await task
            assert process_runner.is_process_cleanup_unconfirmed(stopped.value)
        release.set()
        async with asyncio.timeout(10):
            if not stalled_creation:
                with pytest.raises(asyncio.CancelledError):
                    await task
            with suppress(psutil.NoSuchProcess):
                while child.is_running() and child.status() != psutil.STATUS_ZOMBIE:
                    await asyncio.sleep(0.01)
        with suppress(psutil.NoSuchProcess):
            assert child.status() == psutil.STATUS_ZOMBIE
    finally:
        release.set()
        if child is not None:
            with suppress(psutil.NoSuchProcess):
                child.kill()
        await asyncio.gather(task, return_exceptions=True)
