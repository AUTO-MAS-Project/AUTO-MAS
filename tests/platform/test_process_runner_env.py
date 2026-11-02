"""Optional child environments do not change process cleanup or host state."""

import asyncio
import os
import sys
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
async def test_deadline_ends_communication_before_execution_timeout(monkeypatch):
    process = Mock(pid=None)
    process.wait = AsyncMock(return_value=-9)

    async def communicate():
        await asyncio.Event().wait()

    process.communicate = communicate

    async def create(*args, **kwargs):
        return process

    monkeypatch.setattr(process_runner, "create_subprocess", create)
    async with asyncio.timeout(30):
        with pytest.raises(TimeoutError):
            await process_runner.ProcessRunner.run_process(
                sys.executable, timeout=60, deadline=time.monotonic() + 0.1
            )
    process.kill.assert_called_once()
    process.wait.assert_awaited_once()


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
