"""Optional child environments do not change process cleanup or host state."""

import asyncio
import os
import sys
import threading
import time
from contextlib import suppress

import psutil
import pytest

from app.utils.common.process import runner as process_runner


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_stop", ["cancel", "timeout"])
async def test_repeated_stop_waits_for_tree_cleanup_and_closes_full_output_pipes(
    monkeypatch, initial_stop
):
    """依赖构建/安装取消后，清理线程未停进程之前不能交还目录。"""
    created = []
    ready = asyncio.Event()
    communicating = asyncio.Event()
    stopping, release = threading.Event(), threading.Event()
    release_pipes = asyncio.Event()
    create = process_runner.create_subprocess
    terminate = process_runner._terminate_process_tree

    async def record(*args, **kwargs):
        process = await create(*args, **kwargs)
        created.append(process)
        communicate = process.communicate
        reads = 0

        async def held_output():
            nonlocal reads
            reads += 1
            if reads == 1:
                communicating.set()
                return await communicate()
            # 写入进程退出不代表输出 EOF；收尾不能再次等待这条管道。
            await release_pipes.wait()
            return b"", b""

        process.communicate = held_output
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
            timeout=30 if initial_stop == "cancel" else 0.05,
            kill_tree_on_cancel=True,
        )
    )
    try:
        await asyncio.wait_for(ready.wait(), 3)
        await asyncio.wait_for(communicating.wait(), 3)
        if initial_stop == "cancel":
            task.cancel()
        assert await asyncio.to_thread(stopping.wait, 3)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=0.05)
        assert not done, "进程清理仍在执行，重复取消不能提前结束等待"
        assert created[0].returncode is None
        async with asyncio.timeout(3):
            while not created[0].stdout._paused:
                await asyncio.sleep(0.005)
        release.set()
        done, _ = await asyncio.wait({task}, timeout=1)
        assert done, "写入进程已停止，取消不应再等待输出 EOF"
        for fd in (1, 2):
            assert created[0]._transport.get_pipe_transport(fd).is_closing()
    finally:
        release.set()
        release_pipes.set()
        await asyncio.gather(task, return_exceptions=True)
        for process in created:
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
            await process.wait()
    assert task.cancelled()
    assert created[0].returncode is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,cancelled,with_deadline",
    [
        ("single", False, False),
        ("single", True, False),
        ("owned", False, False),
        ("owned", True, False),
        ("owned", False, True),
        ("owned", True, True),
        ("service", False, False),
        ("service", True, False),
    ],
)
async def test_runner_stop_closes_pipes_and_preserves_process_ownership(
    monkeypatch, tmp_path, kind, cancelled, with_deadline
):
    """带环境变量的停止仍须回收受管树，同时保留继承管道的独立服务。"""
    pid_path = tmp_path / "child.pid"
    if kind == "single":
        code = "import time; time.sleep(60)"
    else:
        code = (
            "import subprocess, sys, time; from pathlib import Path; "
            "child = subprocess.Popen([sys.executable, '-I', '-c', "
            "'import time; time.sleep(60)'], stdin=subprocess.DEVNULL, "
            "stdout=sys.stdout, stderr=sys.stderr, close_fds=True); "
            "Path(sys.argv[1]).write_text(str(child.pid)); "
            + ("sys.exit(127)" if kind == "service" else "time.sleep(60)")
        )
    create = process_runner.create_subprocess
    created = []
    ready = asyncio.Event()
    child = None

    async def record(*args, **kwargs):
        nonlocal child
        wrapper = await create(*args, **kwargs)
        created.append(wrapper)
        if kind != "single":
            async with asyncio.timeout(5):
                while child is None or (
                    kind == "service" and wrapper.returncode is None
                ):
                    try:
                        if child is None:
                            child = psutil.Process(int(pid_path.read_text()))
                    except (OSError, ValueError):
                        pass
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
            timeout=30 if cancelled else (0.05 if kind == "service" else 0.1),
            deadline=time.monotonic() + 20 if with_deadline else None,
            kill_tree_on_cancel=kind == "owned",
            if_merge_std=kind == "owned",
            env=dict(os.environ),
        )
    )
    try:
        async with asyncio.timeout(30):
            await ready.wait()
            if cancelled:
                task.cancel()
            done, _ = await asyncio.wait({task}, timeout=3)
            assert done, "停止不能等待被子进程或服务持有的管道 EOF"
            with pytest.raises(asyncio.CancelledError if cancelled else TimeoutError):
                await task
        assert created[0].returncode is not None
        if kind == "service":
            assert created[0].returncode == 127
            assert child is not None and child.is_running()
            assert child.status() != psutil.STATUS_ZOMBIE
        elif kind == "owned":
            assert child is not None
            with suppress(psutil.NoSuchProcess):
                await asyncio.to_thread(child.wait, timeout=3)
        assert created[0]._transport.get_pipe_transport(1).is_closing()
        if kind != "owned":
            assert created[0]._transport.get_pipe_transport(2).is_closing()
    finally:
        if child is None and pid_path.exists():
            with suppress(psutil.NoSuchProcess):
                child = psutil.Process(int(pid_path.read_text()))
        if child is not None:
            with suppress(psutil.NoSuchProcess):
                child.kill()
                await asyncio.to_thread(child.wait, timeout=5)
        for wrapper in created:
            if wrapper.returncode is None:
                with suppress(ProcessLookupError):
                    wrapper.kill()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_repeated_cancel_during_creation_reaps_dependency_builder(
    monkeypatch, tmp_path
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
        release.set()
        async with asyncio.timeout(10):
            with pytest.raises(asyncio.CancelledError):
                await task
        with suppress(psutil.NoSuchProcess):
            assert child.status() == psutil.STATUS_ZOMBIE
    finally:
        release.set()
        if child is not None:
            with suppress(psutil.NoSuchProcess):
                child.kill()
        await asyncio.gather(task, return_exceptions=True)
