"""旧 MuMu 的辅助前台检查不能逐轮占用模拟器开机等待时间。"""

import asyncio
import sys
import time
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.emulator import DeviceInfo, DeviceStatus, EmulatorRuntimePolicy
from app.utils import emulator as _utils_emulator
from app.utils.common import process_runner

mumu = _utils_emulator.mumu
PACKAGE = "com.example.game"
FOREGROUND = f"mResumedActivity: ActivityRecord{{test {PACKAGE}/.MainActivity}}"


class Harness:
    """只替换时钟和命令边界；执行真实管理器流程，不访问真实设备。"""

    def __init__(self, monkeypatch):
        self.now = 0.0
        self.calls = []
        self.sleeps = []
        self.queries = deque()
        self.default_query = (0.2, 0, FOREGROUND)
        self.monkey = (0.2, 0, "")
        self.app_state = "running"
        self.app_launch = (0.2, 0, "")
        self.manager = object.__new__(mumu.MumuManager)
        self.manager.config = SimpleNamespace(
            Info=SimpleNamespace(MaxWaitTime=300, ForceKillBeforeLaunch=False)
        )
        self.manager.emulator_path = Path("MuMuManager-test-only")
        self.manager.runtime_policy = EmulatorRuntimePolicy(
            silence_enabled=lambda: False, block_ads_enabled=lambda: False
        )
        self.manager._audio_mute_states = {}
        monkeypatch.setattr(mumu, "time", SimpleNamespace(monotonic=lambda: self.now))
        monkeypatch.setattr(
            mumu,
            "asyncio",
            SimpleNamespace(sleep=self.sleep, CancelledError=asyncio.CancelledError),
        )
        monkeypatch.setattr(
            mumu, "ProcessRunner", SimpleNamespace(run_process=self.run)
        )
        monkeypatch.setattr(mumu, "logger", Mock())

    async def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds
        await asyncio.sleep(0)

    async def run(self, program, *args, timeout, **kwargs):
        self.calls.append((args, timeout, self.now))
        if "dumpsys" in args:
            action = self.queries.popleft() if self.queries else self.default_query
        elif "monkey" in args:
            action = self.monkey
        elif "info" in args:
            action = (0, 0, f'{{"state": "{self.app_state}"}}')
        elif "app" in args and "launch" in args:
            action = self.app_launch
        else:
            action = (0, 0, "")
        delay, code, output = action
        self.now += min(delay, timeout)
        if delay > timeout:
            raise TimeoutError
        return process_runner.ProcessResult(stdout=output, stderr="", returncode=code)

    def commands(self, name):
        return [call for call in self.calls if name in call[0]]

    async def ensure(self, idx="0"):
        return await self.manager._ensure_app_foreground(idx, PACKAGE)


@pytest.fixture
def harness(monkeypatch):
    return Harness(monkeypatch)


@pytest.mark.asyncio
async def test_fast_foreground_has_no_added_sleep(harness):
    assert await harness.ensure() is True
    assert harness.now == pytest.approx(0.2)
    assert harness.sleeps == []
    assert not harness.commands("monkey")


@pytest.mark.asyncio
async def test_one_hung_query_retries_with_short_timeout(harness):
    harness.queries.append((float("inf"), 0, ""))
    assert await harness.ensure() is True
    assert harness.now <= 6.2
    assert len(harness.commands("dumpsys")) == 2
    assert all(call[1] <= 5 for call in harness.commands("dumpsys"))


@pytest.mark.asyncio
async def test_repeated_hangs_exhaust_one_budget_without_more_commands(harness):
    harness.default_query = (float("inf"), 0, "")
    assert await harness.ensure() is False
    assert harness.now <= 30
    assert all(call[2] < 30 for call in harness.commands("dumpsys"))
    assert not harness.commands("monkey")


@pytest.mark.asyncio
@pytest.mark.parametrize("returncode", [0, 1])
async def test_failed_queries_still_use_monkey_and_recheck(harness, returncode):
    harness.queries.extend([(0.2, returncode, "not foreground")] * 6)
    assert await harness.ensure() is True
    assert len(harness.commands("monkey")) == 1
    assert len(harness.commands("dumpsys")) == 7
    assert harness.now == pytest.approx(6.6)


@pytest.mark.asyncio
@pytest.mark.parametrize("monkey_code", [0, 1])
async def test_failed_fallback_returns_false_and_keeps_finite_retries(
    harness, monkey_code
):
    harness.default_query = (0.2, 1, FOREGROUND)  # 非零退出不能当作前台成功
    harness.monkey = (0.2, monkey_code, "failed")
    assert await harness.ensure() is False
    assert len(harness.commands("dumpsys")) == 12
    assert len(harness.commands("monkey")) == 1
    assert harness.now == pytest.approx(12.6)


@pytest.mark.asyncio
async def test_monkey_timeout_uses_remaining_shared_budget(harness):
    harness.queries.extend([(0.2, 1, "")] * 6)
    harness.monkey = (float("inf"), 0, "")
    assert await harness.ensure() is False
    assert harness.now <= 30
    assert len(harness.commands("dumpsys")) == 6
    assert harness.commands("monkey")[0][1] == pytest.approx(23.8)


@pytest.mark.asyncio
async def test_post_monkey_queries_cannot_reset_budget(harness):
    harness.queries.extend([(0.2, 1, "")] * 6)
    harness.default_query = (float("inf"), 0, "")
    assert await harness.ensure() is False
    assert harness.now <= 30
    assert len(harness.commands("monkey")) == 1
    assert all(call[2] < 30 for call in harness.commands("dumpsys"))


@pytest.mark.asyncio
async def test_retry_sleep_is_clipped_to_remaining_budget(harness):
    harness.queries.extend([(0.2, 1, "")] * 6)
    harness.default_query = (4.9, 1, "")
    harness.monkey = (0.7, 0, "")
    assert await harness.ensure() is False
    assert harness.now == pytest.approx(30)
    assert harness.sleeps[-1] == pytest.approx(0.5)
    assert len(harness.commands("dumpsys")) == 10
    assert len(harness.commands("monkey")) == 1


@pytest.mark.asyncio
async def test_state_and_initial_app_launch_keep_startup_timeout(harness):
    harness.app_state = "stopped"
    harness.app_launch = (80, 0, "")
    assert await harness.ensure() is True
    assert harness.commands("info")[0][1] == 300
    assert harness.commands("launch")[0][1] == 300
    assert harness.now == pytest.approx(80.2)


@pytest.mark.asyncio
async def test_budget_does_not_leak_to_another_instance(harness):
    harness.default_query = (float("inf"), 0, "")
    assert await harness.ensure("0") is False
    harness.default_query = (0.2, 0, FOREGROUND)
    started_at = harness.now
    assert await harness.ensure("1") is True
    assert harness.now - started_at == pytest.approx(0.2)
    assert harness.commands("dumpsys")[-1][0][2] == "1"


def prepare_open(harness, monkeypatch, statuses):
    info = DeviceInfo("test", DeviceStatus.ONLINE, "127.0.0.1:16384")
    harness.manager.getStatus = AsyncMock(side_effect=statuses)
    harness.manager.getInfo = AsyncMock(return_value={"0": info})
    harness.manager.find_mumu_nx_window = AsyncMock(return_value=1)
    monkeypatch.setattr(_utils_emulator.tools, "apply_launch_audio_mute", AsyncMock())
    return info


@pytest.mark.asyncio
async def test_already_online_keeps_existing_fast_path(harness, monkeypatch):
    info = prepare_open(harness, monkeypatch, [DeviceStatus.ONLINE])
    assert await harness.manager.open("0", PACKAGE) is info
    assert harness.calls == []
    assert harness.now == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("foreground", [True, False])
async def test_slow_cold_boot_keeps_full_startup_wait(harness, monkeypatch, foreground):
    info = prepare_open(harness, monkeypatch, [])
    status_calls = 0

    async def status(idx):
        nonlocal status_calls
        status_calls += 1
        if status_calls == 1:
            return DeviceStatus.OFFLINE
        # 正常但较慢：上线等待超过新的前台辅助预算。
        return DeviceStatus.STARTING if harness.now < 80 else DeviceStatus.ONLINE

    harness.manager.getStatus.side_effect = status
    if not foreground:
        harness.default_query = (float("inf"), 0, "")
    assert await harness.manager.open("0", PACKAGE) is info
    assert 110 <= harness.now <= 140.2
    assert all(call[1] == 300 for call in harness.calls if "dumpsys" not in call[0])
    assert 30 in harness.sleeps  # 保留原有上线后的加载缓冲


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["query", "sleep", "monkey"])
async def test_cancel_propagates_without_fallback(harness, monkeypatch, stage):
    async def cancel(*args, **kwargs):
        raise asyncio.CancelledError

    original_run = harness.run

    async def run(program, *args, **kwargs):
        if (stage == "query" and "dumpsys" in args) or (
            stage == "monkey" and "monkey" in args
        ):
            raise asyncio.CancelledError
        return await original_run(program, *args, **kwargs)

    harness.default_query = (0.2, 1, "")
    monkeypatch.setattr(mumu, "ProcessRunner", SimpleNamespace(run_process=run))
    if stage == "sleep":
        monkeypatch.setattr(mumu.asyncio, "sleep", cancel)
    with pytest.raises(asyncio.CancelledError):
        await harness.ensure()
    assert not harness.commands("monkey")


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
@pytest.mark.parametrize("stage", ["query", "monkey"])
async def test_real_runner_reaps_isolated_hung_command(monkeypatch, cancelled, stage):
    """Linux/Windows 都只启动测试 Python，验证真实 ProcessRunner 的清理。"""
    manager = object.__new__(mumu.MumuManager)
    manager.emulator_path = Path("MuMuManager-test-only")
    manager.config = SimpleNamespace(Info=SimpleNamespace(MaxWaitTime=300))
    manager._get_app_state = AsyncMock(return_value="running")
    if stage == "monkey":
        manager._wait_app_foreground = AsyncMock(return_value=False)
    monkeypatch.setattr(mumu, "MUMU_FOREGROUND_QUERY_TIMEOUT", 0.1, raising=False)
    monkeypatch.setattr(mumu, "MUMU_FOREGROUND_BUDGET", 0.25, raising=False)
    created = []
    started = asyncio.Event()
    create = process_runner.create_subprocess

    async def record(*args, **kwargs):
        child = await create(*args, **kwargs)
        created.append(child)
        started.set()
        return child

    async def run(program, *args, **kwargs):
        return await process_runner.ProcessRunner.run_process(
            sys.executable, "-I", "-c", "import time; time.sleep(30)", **kwargs
        )

    monkeypatch.setattr(process_runner, "create_subprocess", record)
    monkeypatch.setattr(mumu, "ProcessRunner", SimpleNamespace(run_process=run))
    pending_before = asyncio.all_tasks()
    started_at = time.monotonic()
    task = asyncio.create_task(manager._ensure_app_foreground("0", PACKAGE))
    async with asyncio.timeout(5):
        await started.wait()
        if cancelled:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            assert await task is False
    assert time.monotonic() - started_at < 3
    assert created and all(child.returncode is not None for child in created)
    assert not (asyncio.all_tasks() - pending_before)
