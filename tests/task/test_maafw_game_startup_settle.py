"""桌面游戏刚由 MAS 启动时，首个任务要等画面加载完再下发（Game.StartupSettleTime）。

worker 侧：MaaFWRunner 在初始化之后、投递第一个任务之前等到宿主给的时刻；
宿主侧：只有窗口是本轮等出来的才算「刚启动」，且剩余时间扣掉已经过去的部分。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from app.task.MaaFW.tools.core.automas_maafw_runner import runner as runner_module
from app.task.MaaFW.tools.core.automas_maafw_runner.models import (
    MaaFWDeviceConfig,
    MaaFWResourceBundlePlan,
    MaaFWRunnerJobPayload,
    MaaFWRunPlan,
    MaaFWTaskRunPlan,
)
from app.task.MaaFW.tools.core.automas_maafw_runner.runner import MaaFWRunner
from app.task.MaaFW.tools.core.automas_maafw_runner.service import MaaFWRunnerService
from app.task.MaaFW.tools.embedded import runner_task as runner_task_module
from app.task.MaaFW.tools.embedded.runner_task import MaaFWPluginAutoProxyTask

# ---------------------------------------------------------------- worker 侧


class _Job:
    failed = False

    def wait(self) -> "_Job":
        return self


class _Tasker:
    stopping = False

    def __init__(self) -> None:
        self.posted: list[str] = []

    def post_task(self, entry: str, override: Any = None) -> _Job:
        self.posted.append(entry)
        return _Job()


def _plan() -> MaaFWRunPlan:
    return MaaFWRunPlan(
        path="C:/proj",
        projectName="proj",
        controllerName="Win32-Front",
        controllerType="Win32",
        resourceName="res",
        resource=MaaFWResourceBundlePlan(name="res"),
        tasks=[MaaFWTaskRunPlan(name="送货", entry="SeizeDeliveryJobsMain")],
    )


def _runner(
    monkeypatch: pytest.MonkeyPatch, *, not_before: float | None
) -> tuple[MaaFWRunner, _Tasker, list[str], list[float]]:
    logs: list[str] = []
    waits: list[float] = []
    runner = MaaFWRunner(
        _plan(), send_log=logs.append, task_start_not_before=not_before
    )
    tasker = _Tasker()

    def fake_init(self: MaaFWRunner, _device: MaaFWDeviceConfig) -> None:
        self.tasker = tasker  # type: ignore[assignment]
        self.controller = object()

    def fake_wait(timeout: float | None = None) -> bool:
        waits.append(float(timeout or 0))
        return False

    monkeypatch.setattr(MaaFWRunner, "_ensure_initialized", fake_init)
    monkeypatch.setattr(runner._stop_requested, "wait", fake_wait)
    monkeypatch.setattr(runner_module.time, "sleep", lambda _s: None)
    monkeypatch.setattr(runner_module.time, "time", lambda: 1000.0)
    return runner, tasker, logs, waits


def test_worker_waits_remaining_seconds_before_first_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, tasker, logs, waits = _runner(monkeypatch, not_before=1000.0 + 17.4)
    result = runner.run(MaaFWDeviceConfig(type="Win32", hWnd=1))

    assert result.success is True
    assert tasker.posted == ["SeizeDeliveryJobsMain"]
    assert waits == [pytest.approx(17.4)]
    assert any("再等 17s" in line for line in logs)


@pytest.mark.parametrize("not_before", [None, 1000.0, 990.0])
def test_worker_skips_gate_when_nothing_left_to_wait(
    monkeypatch: pytest.MonkeyPatch, not_before: float | None
) -> None:
    runner, tasker, logs, waits = _runner(monkeypatch, not_before=not_before)
    result = runner.run(MaaFWDeviceConfig(type="Win32", hWnd=1))

    assert result.success is True
    assert tasker.posted == ["SeizeDeliveryJobsMain"]
    assert waits == []
    assert not any("再等" in line for line in logs)


def test_worker_gate_is_capped_against_clock_skew(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, _tasker, _logs, waits = _runner(monkeypatch, not_before=1000.0 + 86400)
    runner.run(MaaFWDeviceConfig(type="Win32", hWnd=1))
    assert waits == [runner_module.TASK_START_GATE_MAX_SECONDS]


def test_worker_gate_stops_when_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    runner, tasker, _logs, _waits = _runner(monkeypatch, not_before=1000.0 + 5)
    monkeypatch.setattr(runner._stop_requested, "wait", lambda timeout=None: True)
    result = runner.run(MaaFWDeviceConfig(type="Win32", hWnd=1))

    assert result.success is False
    assert tasker.posted == []
    assert "已停止" in str(result.errorMessage)


def test_job_payload_carries_not_before() -> None:
    service = MaaFWRunnerService()
    payload = service.create_job_payload(
        _plan(),
        MaaFWDeviceConfig(type="Win32", hWnd=1),
        task_start_not_before=1234.5,
    )
    assert payload.taskStartNotBefore == 1234.5
    # 旧 job 文件没有这个键也要能读：字段可省略
    legacy = MaaFWRunnerJobPayload.model_validate(
        {"plan": _plan().model_dump(), "deviceConfig": {"type": "Win32"}}
    )
    assert legacy.taskStartNotBefore is None


# ---------------------------------------------------------------- 宿主侧


class _ScriptConfig:
    def __init__(self, settle: int, wait_time: int = 60) -> None:
        self.values = {
            ("Game", "StartupSettleTime"): settle,
            ("Game", "WaitTime"): wait_time,
            ("Device", "HWnd"): 0,
        }

    def get(self, group: str, key: str) -> Any:
        return self.values[(group, key)]


def _host(monkeypatch: pytest.MonkeyPatch, *, settle: int) -> tuple[Any, list[str]]:
    logs: list[str] = []
    task = MaaFWPluginAutoProxyTask.__new__(MaaFWPluginAutoProxyTask)
    task.script_config = _ScriptConfig(settle)  # type: ignore[assignment]
    task.game_window_ready_at = None
    task._append_log = logs.append  # type: ignore[method-assign]
    return task, logs


def test_host_not_before_subtracts_elapsed(monkeypatch: pytest.MonkeyPatch) -> None:
    task, logs = _host(monkeypatch, settle=30)
    monkeypatch.setattr(runner_task_module.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(runner_task_module.time, "time", lambda: 5000.0)
    task.game_window_ready_at = 100.0 - 8.5  # 窗口 8.5s 前出现

    assert task._task_start_not_before() == pytest.approx(5000.0 + 21.5)
    assert any("至少等 30s" in line and "剩余约 22s" in line for line in logs)


def test_host_not_before_is_none_when_game_was_already_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task, logs = _host(monkeypatch, settle=30)
    assert task._task_start_not_before() is None
    assert logs == []


def test_host_not_before_is_none_when_settle_elapsed_or_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runner_task_module.time, "monotonic", lambda: 100.0)
    task, _logs = _host(monkeypatch, settle=30)
    task.game_window_ready_at = 100.0 - 45  # 重试轮次：窗口早就出现了
    assert task._task_start_not_before() is None

    task, logs = _host(monkeypatch, settle=0)
    task.game_window_ready_at = 100.0 - 1
    assert task._task_start_not_before() is None
    assert logs == []


def _window_wait_host(
    monkeypatch: pytest.MonkeyPatch, *, matches_at_poll: int, wait_time: int = 60
) -> tuple[Any, list[float]]:
    """让窗口在第 matches_at_poll 次探测时出现（从 0 数），并把睡眠记录下来。"""

    task, _logs = _host(monkeypatch, settle=30)
    task.script_config.values[("Game", "WaitTime")] = wait_time  # type: ignore[attr-defined]
    task.run_plan = type("Plan", (), {"controllerName": "Win32-Front"})()
    task.interface_model = object()
    polls = {"count": 0}
    slept: list[float] = []

    def fake_match(_controller: Any) -> list[Any]:
        current = polls["count"]
        polls["count"] += 1
        if current >= matches_at_poll:
            return [
                type(
                    "W",
                    (),
                    {"hWnd": 1, "className": "UnityWndClass", "windowName": "Endfield"},
                )()
            ]
        return []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(runner_task_module, "_find_controller", lambda _m, _n: object())
    monkeypatch.setattr(runner_task_module, "_match_controller_windows", fake_match)
    monkeypatch.setattr(runner_task_module, "_is_process_path_running", lambda _p: True)
    monkeypatch.setattr(runner_task_module.asyncio, "sleep", fake_sleep)
    return task, slept


def test_window_wait_reports_whether_window_appeared_during_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task, slept = _window_wait_host(monkeypatch, matches_at_poll=0)
    assert (
        asyncio.run(task._wait_for_desktop_game_ready(Path("C:/g/Endfield.exe")))
        is False
    )
    assert slept == []

    # 每轮循环探测两次（先查窗口，再查进程后再查窗口），第 3 次命中即睡过一轮
    task, slept = _window_wait_host(monkeypatch, matches_at_poll=3)
    assert (
        asyncio.run(task._wait_for_desktop_game_ready(Path("C:/g/Endfield.exe")))
        is True
    )
    assert len(slept) == 1
