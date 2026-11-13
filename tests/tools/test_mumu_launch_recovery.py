"""MuMu 启动恢复：所有命令、窗口和进程操作均为 Mock，不触碰模拟器数据。"""

import asyncio
import json
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.config import EmulatorConfig
from app.models.emulator import DeviceStatus, EmulatorRuntimePolicy
from app.utils.common.emulator import mumu
from app.utils.common.emulator.mumu import MumuManager
from app.utils.common.process.runner import ProcessResult


class FakeMuMu:
    def __init__(self):
        self.states = {"0": DeviceStatus.OFFLINE, "1": DeviceStatus.ONLINE}
        self.launch_results = deque()
        self.setting_results = deque()
        self.calls = []
        self.after_info = None

    async def run(self, program, *args, **kwargs):
        self.calls.append(args)
        idx = args[args.index("-v") + 1]
        assert idx in self.states
        if args[0] == "info":
            state = self.states[idx]
            entry = {
                "index": int(idx),
                "name": f"MuMu-{idx}",
                "is_process_started": state
                in (DeviceStatus.STARTING, DeviceStatus.ONLINE),
                "is_android_started": state == DeviceStatus.ONLINE,
                "adb_host_ip": "127.0.0.1",
                "adb_port": 16384 + int(idx) * 32,
                "player_state": "start_finished"
                if state == DeviceStatus.ONLINE
                else "stopped",
            }
            if self.after_info:
                self.after_info(idx)
            return ProcessResult(json.dumps(entry), "", 0)
        if args[0] == "setting":
            return self.setting_results.popleft() if self.setting_results else ok()
        if args[0] == "control" and args[3] == "launch":
            result, state = (
                self.launch_results.popleft()
                if self.launch_results
                else (ok(), DeviceStatus.ONLINE)
            )
            self.states[idx] = state
            return result
        pytest.fail(f"不允许执行其他操作: {args}")

    def launches(self, idx="0"):
        return [c for c in self.calls if c[:4] == ("control", "-v", idx, "launch")]


def ok():
    return ProcessResult('{"errcode": 0, "errmsg": ""}', "", 0)


def failed(code=-503, returncode=4294966793):
    return ProcessResult(
        json.dumps({"errcode": code, "errmsg": "mainnx connect failed"}), "", returncode
    )


@pytest.fixture
def harness(tmp_path, monkeypatch):
    exe = tmp_path / "MuMuManager.exe"
    exe.touch()
    settings = {
        "Path": str(exe),
        "Type": "mumu",
        "MaxWaitTime": 5,
        "ForceKillBeforeLaunch": False,
        "ForceKillOnClose": False,
    }
    config = EmulatorConfig.model_validate({"Info": settings})
    policy = EmulatorRuntimePolicy(lambda: False, lambda: False, tmp_path)
    manager = MumuManager(config, runtime_policy=policy)

    class Settings(dict):
        def __setitem__(self, key, value):
            setattr(config.Info, key, value)
            super().__setitem__(key, value)

        def update(self, **values):
            for key, value in values.items():
                self[key] = value

    settings = Settings(settings)
    fake = FakeMuMu()
    monkeypatch.setattr(
        mumu.ProcessRunner, "run_process", AsyncMock(side_effect=fake.run)
    )
    monkeypatch.setattr(MumuManager, "find_mumu_nx_window", AsyncMock(return_value=123))
    monkeypatch.setattr(MumuManager, "_resolve_audio_pids", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        MumuManager,
        "_force_clear_before_launch",
        AsyncMock(side_effect=AssertionError("不得全局清理")),
    )
    monkeypatch.setattr(
        MumuManager,
        "_force_kill_mumu_processes",
        Mock(side_effect=AssertionError("不得结束进程")),
    )
    monkeypatch.setattr(
        mumu._utils_emulator.tools, "apply_launch_audio_mute", AsyncMock()
    )
    monkeypatch.setattr(mumu, "logger", Mock())
    real_sleep = asyncio.sleep
    sleeps = []

    async def fast_sleep(seconds):
        sleeps.append(seconds)
        await real_sleep(0)

    monkeypatch.setattr(mumu.asyncio, "sleep", fast_sleep)
    return SimpleNamespace(
        manager=manager,
        fake=fake,
        settings=settings,
        sleeps=sleeps,
        real_sleep=real_sleep,
    )


@pytest.mark.asyncio
async def test_normal_launch(harness):
    info = await harness.manager.open("0")
    assert info.status == DeviceStatus.ONLINE
    assert info.adb_address == "127.0.0.1:16384"
    assert len(harness.fake.launches()) == 1
    assert not harness.manager._get_instance_lock("0").locked()


@pytest.mark.asyncio
async def test_running_instance_is_not_launched_again(harness):
    harness.fake.states["0"] = DeviceStatus.ONLINE
    assert (await harness.manager.open("0")).status == DeviceStatus.ONLINE
    assert all(c[0] == "info" for c in harness.fake.calls)


@pytest.mark.asyncio
async def test_temporary_503_recovers(harness):
    harness.fake.launch_results.extend(
        [(failed(), DeviceStatus.OFFLINE), (ok(), DeviceStatus.ONLINE)]
    )
    assert (await harness.manager.open("0")).status == DeviceStatus.ONLINE
    assert len(harness.fake.launches()) == 2
    assert harness.sleeps.count(mumu.MUMU_LAUNCH_RETRY_SECONDS) == 1
    calls = harness.fake.calls
    first, second = [i for i, c in enumerate(calls) if c in harness.fake.launches()]
    assert sum(c[0] == "info" for c in calls[first + 1 : second]) >= 2


@pytest.mark.asyncio
async def test_persistent_503_is_bounded_and_close_does_not_kill(harness):
    harness.settings.update(ForceKillBeforeLaunch=True, ForceKillOnClose=True)
    harness.fake.launch_results.extend([(failed(), DeviceStatus.OFFLINE)] * 5)
    with pytest.raises(RuntimeError, match="errcode=-503") as exc:
        await harness.manager.open("0")
    assert "4294966793" in str(exc.value) and "mainnx connect failed" in str(exc.value)
    assert len(harness.fake.launches()) == mumu.MUMU_LAUNCH_ATTEMPTS == 3
    assert harness.sleeps.count(mumu.MUMU_LAUNCH_RETRY_SECONDS) == 2
    assert not harness.manager._get_instance_lock("0").locked()
    assert await harness.manager.close("0") == DeviceStatus.OFFLINE
    assert harness.fake.states["1"] == DeviceStatus.ONLINE
    assert all(c[2] == "0" for c in harness.fake.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [DeviceStatus.ONLINE, DeviceStatus.STARTING])
async def test_command_errors_but_instance_started(harness, state):
    harness.fake.launch_results.append((failed(), state))
    if state == DeviceStatus.STARTING:

        def after_info(idx):
            if harness.fake.states[idx] == DeviceStatus.STARTING:
                harness.fake.states[idx] = DeviceStatus.ONLINE

        harness.fake.after_info = after_info
    assert (await harness.manager.open("0")).status == DeviceStatus.ONLINE
    assert len(harness.fake.launches()) == 1


@pytest.mark.asyncio
async def test_instance_started_during_retry_delay(harness):
    harness.fake.launch_results.append((failed(), DeviceStatus.OFFLINE))
    original_sleep = mumu.asyncio.sleep

    async def sleep(seconds):
        if seconds == mumu.MUMU_LAUNCH_RETRY_SECONDS:
            harness.fake.states["0"] = DeviceStatus.ONLINE
        await original_sleep(seconds)

    from unittest.mock import patch

    with patch.object(mumu.asyncio, "sleep", sleep):
        assert (await harness.manager.open("0")).status == DeviceStatus.ONLINE
    assert len(harness.fake.launches()) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [failed(-503, 0), ProcessResult("", "", 4294966793), ProcessResult("", "", -503)],
)
async def test_json_and_signed_exit_codes_are_recognized(harness, result):
    harness.fake.launch_results.append((result, DeviceStatus.OFFLINE))
    assert (await harness.manager.open("0")).status == DeviceStatus.ONLINE
    assert len(harness.fake.launches()) == 2


@pytest.mark.asyncio
async def test_non_retryable_error_is_reported_once(harness):
    harness.fake.launch_results.append((failed(-999, 123), DeviceStatus.OFFLINE))
    with pytest.raises(RuntimeError, match="errcode=-999"):
        await harness.manager.open("0")
    assert len(harness.fake.launches()) == 1


@pytest.mark.asyncio
async def test_setting_503_also_has_bounded_recovery(harness):
    harness.fake.setting_results.extend([failed(), ok()])
    assert (await harness.manager.open("0")).status == DeviceStatus.ONLINE
    assert len(harness.fake.launches()) == 1


@pytest.mark.asyncio
async def test_initial_starting_instance_is_only_observed(harness):
    harness.fake.states["0"] = DeviceStatus.STARTING
    reads = 0

    def after_info(idx):
        nonlocal reads
        reads += 1
        if reads >= 3:
            harness.fake.states[idx] = DeviceStatus.ONLINE

    harness.fake.after_info = after_info
    assert (await harness.manager.open("0")).status == DeviceStatus.ONLINE
    assert not harness.fake.launches()
    assert all(c[0] == "info" for c in harness.fake.calls)


@pytest.mark.asyncio
async def test_same_physical_instance_is_serialized_across_managers(harness):
    second = MumuManager(
        harness.manager.config, runtime_policy=harness.manager.runtime_policy
    )
    first_info, second_info = await asyncio.gather(
        harness.manager.open("0"), second.open("00")
    )
    assert first_info == second_info
    assert len(harness.fake.launches()) == 1
    assert harness.manager._get_instance_lock("0") is second._get_instance_lock("00")


@pytest.mark.asyncio
async def test_failure_on_one_instance_does_not_block_another(harness):
    harness.fake.launch_results.extend([(failed(), DeviceStatus.OFFLINE)] * 3)
    results = await asyncio.gather(
        harness.manager.open("0"), harness.manager.open("1"), return_exceptions=True
    )
    assert isinstance(results[0], RuntimeError)
    assert results[1].status == DeviceStatus.ONLINE
    assert harness.fake.states["1"] == DeviceStatus.ONLINE
    assert not harness.fake.launches("1")


@pytest.mark.asyncio
async def test_total_timeout_bounds_polling_and_releases_lock(harness):
    harness.settings["MaxWaitTime"] = 1
    harness.fake.states["0"] = DeviceStatus.STARTING
    with pytest.raises(RuntimeError, match="总时限|启动超时"):
        await asyncio.wait_for(harness.manager.open("0"), 2)
    assert not harness.manager._get_instance_lock("0").locked()
    assert not harness.fake.launches()


@pytest.mark.asyncio
async def test_cancel_releases_lock_and_next_open_can_recover(harness):
    entered = asyncio.Event()

    async def hang(program, *args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    mumu.ProcessRunner.run_process.side_effect = hang
    task = asyncio.create_task(harness.manager.open("0"))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not harness.manager._get_instance_lock("0").locked()
    mumu.ProcessRunner.run_process.side_effect = harness.fake.run
    assert (await harness.manager.open("0")).status == DeviceStatus.ONLINE
    assert "0" not in harness.manager._failed_launches


@pytest.mark.asyncio
async def test_missing_target_is_not_confused_with_another_instance(harness):
    mumu.ProcessRunner.run_process.return_value = ProcessResult(
        json.dumps({"index": 1, "name": "other", "is_android_started": True}), "", 0
    )
    mumu.ProcessRunner.run_process.side_effect = None
    assert await harness.manager.getStatus("0") == DeviceStatus.NOT_FOUND
    with pytest.raises(RuntimeError, match="未找到"):
        await harness.manager.open("0")


@pytest.mark.asyncio
async def test_unreadable_state_never_triggers_launch(harness):
    harness.settings["MaxWaitTime"] = 1
    mumu.ProcessRunner.run_process.side_effect = None
    mumu.ProcessRunner.run_process.return_value = failed()
    with pytest.raises(RuntimeError):
        await harness.manager.open("0")
    assert all(
        call.args[1] == "info" for call in mumu.ProcessRunner.run_process.call_args_list
    )


@pytest.mark.asyncio
async def test_failed_start_does_not_claim_starting_instance_was_closed(harness):
    harness.manager._failed_launches.add("0")
    harness.settings["ForceKillOnClose"] = True
    harness.fake.states["0"] = DeviceStatus.STARTING
    with pytest.raises(RuntimeError, match="未自动关闭"):
        await harness.manager.close("0")
    assert harness.fake.states["1"] == DeviceStatus.ONLINE
    assert all(c[0] == "info" for c in harness.fake.calls)


@pytest.mark.asyncio
async def test_retry_delay_is_part_of_total_budget(harness):
    harness.settings["MaxWaitTime"] = 1
    harness.fake.launch_results.append((failed(), DeviceStatus.OFFLINE))
    from unittest.mock import patch

    with patch.object(mumu.asyncio, "sleep", harness.real_sleep):
        with pytest.raises(RuntimeError, match="总时限.*errcode=-503"):
            await asyncio.wait_for(harness.manager.open("0"), 2)
    assert len(harness.fake.launches()) == 1
    assert not harness.manager._get_instance_lock("0").locked()


@pytest.mark.asyncio
async def test_unknown_state_after_error_stops_recovery(harness):
    harness.fake.launch_results.append((failed(), DeviceStatus.OFFLINE))
    original = harness.manager.getStatus

    async def status(idx):
        if harness.fake.launches():
            return DeviceStatus.UNKNOWN
        return await original(idx)

    from unittest.mock import patch

    with patch.object(harness.manager, "getStatus", status):
        with pytest.raises(RuntimeError, match="复查状态=UNKNOWN"):
            await harness.manager.open("0")
    assert len(harness.fake.launches()) == 1


@pytest.mark.asyncio
async def test_close_waits_for_inflight_launch(harness):
    entered, release = asyncio.Event(), asyncio.Event()
    original = harness.fake.run

    async def run(program, *args, **kwargs):
        if args[:4] == ("control", "-v", "0", "launch"):
            entered.set()
            await release.wait()
        return await original(program, *args, **kwargs)

    mumu.ProcessRunner.run_process.side_effect = run
    from unittest.mock import patch

    with patch.object(
        harness.manager, "_close_locked", AsyncMock(return_value=DeviceStatus.OFFLINE)
    ) as close:
        opening = asyncio.create_task(harness.manager.open("0"))
        await entered.wait()
        closing = asyncio.create_task(harness.manager.close("0"))
        await harness.real_sleep(0)
        close.assert_not_awaited()
        release.set()
        await opening
        assert await closing == DeviceStatus.OFFLINE
        close.assert_awaited_once_with("0")


@pytest.mark.asyncio
async def test_queued_start_timeout_cannot_close_another_successful_start(harness):
    entered, release = asyncio.Event(), asyncio.Event()
    original = harness.fake.run

    async def run(program, *args, **kwargs):
        if args[:4] == ("control", "-v", "0", "launch"):
            entered.set()
            await release.wait()
        return await original(program, *args, **kwargs)

    mumu.ProcessRunner.run_process.side_effect = run
    opening = asyncio.create_task(harness.manager.open("0"))
    await entered.wait()
    harness.settings["MaxWaitTime"] = 1
    try:
        with pytest.raises(RuntimeError, match="等待实例锁失败"):
            await harness.manager.open("0")
        closing = asyncio.create_task(harness.manager.close("0"))
        release.set()
        assert (await opening).status == DeviceStatus.ONLINE
        with pytest.raises(RuntimeError, match="未自动关闭"):
            await closing
        assert harness.fake.states["0"] == DeviceStatus.ONLINE
        assert not any(
            call[:4] == ("control", "-v", "0", "shutdown")
            for call in harness.fake.calls
        )
    finally:
        release.set()
        await opening


@pytest.mark.asyncio
async def test_confirmed_low_integrity_keeps_manual_hint_and_stops_retries(
    harness, monkeypatch
):
    monkeypatch.setattr(mumu, "IS_WINDOWS", True)
    monkeypatch.setattr(
        mumu,
        "platform_integrity",
        SimpleNamespace(
            INTEGRITY_LOW=0x1000,
            mandatory_label_rid=Mock(return_value=0x1000),
        ),
    )
    harness.fake.launch_results.append((failed(), DeviceStatus.OFFLINE))
    with pytest.raises(RuntimeError, match="icacls"):
        await harness.manager.open("0")
    assert len(harness.fake.launches()) == 1
    assert all(call[0] in ("info", "setting", "control") for call in harness.fake.calls)
