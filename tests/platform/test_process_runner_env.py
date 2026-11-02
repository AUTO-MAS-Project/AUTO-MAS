"""Optional child environments do not change process cleanup or host state."""

import asyncio
import os
import sys
from unittest.mock import Mock

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
