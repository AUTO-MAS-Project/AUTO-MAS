from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
import uuid
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from ok_script_adapter.adapter.autoproxy import OkScriptAutoProxyTask
from ok_script_adapter.adapter import config_session as config_session_module
from ok_script_adapter.adapter.config_session import OkScriptConfigSession
from ok_script_adapter.adapter.execution import (
    ExecutionPlan,
    ExecutionPlanner,
    ResultObserver,
    RunObservation,
    RunObservationPolicy,
    WHOLE_RUN_RETRY_SCOPE,
)
from ok_script_adapter.adapter.run_controller import (
    AttemptPreparation,
    RunController,
    RunControllerResult,
    RunControllerUpdate,
)
from ok_script_adapter.common.events import (
    OkScriptRunEvent,
    OkScriptRunFailure,
)
from ok_script_adapter.common.provider import OkScriptRuntimeConfigOverride
from ok_script_adapter.providers.okww import OKWW_PROVIDER
from ok_script_adapter.shell.descriptor import (
    PROTOCOL_FRAMEWORK_CLI,
    PROTOCOL_LEGACY_EXE,
)
from ok_script_adapter.shell.manifest import inspect_ok_project
from ok_script_adapter.shell.runtime import OkConfigStore, OkShellRunner

from project_fixtures import PROJECT_FIXTURE_SPECS, build_project_fixture


class _FakeStream:
    async def readline(self) -> bytes:
        await asyncio.sleep(0)
        return b""


class _FakeProcess:
    def __init__(self) -> None:
        self.stdout = _FakeStream()
        self.stderr = _FakeStream()
        self.returncode: int | None = None


class _FakeProcessManager:
    def __init__(self, *, start_error: Exception | None = None) -> None:
        self.process: _FakeProcess | None = None
        self.start_error = start_error
        self.open_calls = 0
        self.kill_calls = 0
        self.running = False
        self.terminal_delivered = False
        self.opened = asyncio.Event()

    async def open_process(self, program, *args, **kwargs) -> None:
        self.open_calls += 1
        self.opened.set()
        if self.start_error is not None:
            raise self.start_error
        self.process = _FakeProcess()
        self.running = True
        self.terminal_delivered = False

    async def is_running(self) -> bool:
        if self.terminal_delivered:
            self.running = False
        return self.running

    async def kill(self) -> None:
        self.kill_calls += 1
        self.running = False
        if self.process is not None and self.process.returncode is None:
            self.process.returncode = -15


class _SequencedEventReader:
    def __init__(
        self,
        manager: _FakeProcessManager,
        events: tuple[OkScriptRunEvent, ...],
    ) -> None:
        self.manager = manager
        self.events = events
        self.delivered_attempts: set[int] = set()

    def __call__(self, path: Path, offset: int):
        attempt = self.manager.open_calls
        if attempt <= 0 or attempt in self.delivered_attempts:
            return [], offset
        if attempt > len(self.events):
            return [], offset

        event = self.events[attempt - 1]
        self.delivered_attempts.add(attempt)
        self.manager.terminal_delivered = event.is_terminal
        if self.manager.process is not None and event.is_terminal:
            self.manager.process.returncode = 0 if event.success is not False else 1
        return [event], offset


class _FakeDelegate:
    def __init__(self) -> None:
        self.prepared: list[int] = []
        self.completed: list[RunControllerResult] = []
        self.failed: list[tuple[RunControllerResult, bool]] = []
        self.cancelled = 0
        self.game_kills = 0
        self.updates: list[RunControllerUpdate] = []

    async def prepare_attempt(
        self,
        attempt: int,
        total_attempts: int,
    ) -> AttemptPreparation:
        self.prepared.append(attempt)
        return AttemptPreparation(started_at=datetime.now())

    async def complete_attempt(self, result: RunControllerResult) -> None:
        self.completed.append(result)

    async def fail_attempt(
        self,
        result: RunControllerResult,
        *,
        will_retry: bool,
    ) -> None:
        self.failed.append((result, will_retry))

    async def cancel_run(self) -> None:
        self.cancelled += 1

    def should_kill_game(self) -> bool:
        return True

    async def kill_game(self) -> None:
        self.game_kills += 1

    async def on_run_update(self, update: RunControllerUpdate) -> None:
        self.updates.append(update)


class _ConfigSessionDelegate(_FakeDelegate):
    def __init__(self, session: OkScriptConfigSession) -> None:
        super().__init__()
        self.session = session

    async def prepare_attempt(
        self,
        attempt: int,
        total_attempts: int,
    ) -> AttemptPreparation:
        self.prepared.append(attempt)
        await self.session.inject()
        return AttemptPreparation(started_at=datetime.now())

    async def cancel_run(self) -> None:
        await super().cancel_run()
        await self.session.restore()


class _FakeConfig:
    def __init__(self, values: dict[tuple[str, str], object]) -> None:
        self.values = values
        self.set_calls: list[tuple[str, str, object]] = []

    def get(self, group: str, name: str) -> object:
        return self.values[(group, name)]

    async def set(self, group: str, name: str, value: object) -> None:
        self.values[(group, name)] = value
        self.set_calls.append((group, name, value))


class _FakeConfigSession:
    def __init__(self) -> None:
        self.injected = True
        self.write_back_calls = 0
        self.restore_calls = 0

    async def write_back(self) -> None:
        self.write_back_calls += 1

    async def restore(self) -> None:
        self.restore_calls += 1


def _event(
    name: str,
    *,
    success: bool | None = None,
    message: str = "",
    task: str = "",
    failures: tuple[OkScriptRunFailure, ...] = (),
) -> OkScriptRunEvent:
    return OkScriptRunEvent(
        event=name,
        message=message,
        task=task,
        success=success,
        failures=failures,
    )


def _policy() -> RunObservationPolicy:
    return RunObservationPolicy(
        display_name="测试项目",
        running_status="运行中",
        fatal_patterns=(("fatal", "测试项目异常"),),
        success_patterns=("success marker",),
        log_time_range=(0, 19),
        log_time_format="%Y-%m-%d %H:%M:%S",
    )


def _build_plan(root: Path, *, attempt_limit: int = 1) -> ExecutionPlan:
    spec = next(
        item for item in PROJECT_FIXTURE_SPECS if item.name == "okww-source"
    )
    fixture = build_project_fixture(root, spec)
    descriptor = inspect_ok_project(
        fixture.root,
        python_executable=sys.executable,
    )
    planner = ExecutionPlanner(
        descriptor,
        OKWW_PROVIDER,
        provider_registered=True,
    )
    plan = planner.build(
        task_index=1,
        available_protocols=(PROTOCOL_FRAMEWORK_CLI,),
        attempt_limit=attempt_limit,
        run_timeout_minutes=1,
        retry_delay_seconds=0,
    )
    return replace(
        plan,
        log_start_timeout_seconds=0.05,
        exit_wait_timeout_seconds=0.05,
    )


class ExecutionPlannerTest(unittest.TestCase):
    def test_explicit_protocols_keep_planner_process_free(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(
                OkShellRunner,
                "available_protocols",
                side_effect=AssertionError("planner must not probe subprocesses"),
            ):
                plan = _build_plan(Path(tmp_dir))

        self.assertEqual(plan.retry_scope, WHOLE_RUN_RETRY_SCOPE)
        self.assertEqual(plan.invocation.task_index, 1)
        self.assertEqual(plan.invocation.protocol, PROTOCOL_FRAMEWORK_CLI)
        self.assertIn("ok.cli", plan.invocation.command)
        self.assertIsInstance(plan.invocation.environment, tuple)

    def test_empty_pythonw_path_does_not_track_project_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            spec = next(
                item
                for item in PROJECT_FIXTURE_SPECS
                if item.name == "okww-source"
            )
            fixture = build_project_fixture(root, spec)
            executable = fixture.root / "ok-ww.exe"
            executable.write_bytes(b"")
            descriptor = replace(
                inspect_ok_project(
                    fixture.root,
                    python_executable=sys.executable,
                ),
                executable=executable,
                protocols=(PROTOCOL_LEGACY_EXE,),
                default_protocol=PROTOCOL_LEGACY_EXE,
            )
            provider = replace(
                OKWW_PROVIDER,
                pythonw_path="",
                track_process_name="",
            )
            plan = ExecutionPlanner(
                descriptor,
                provider,
                provider_registered=True,
            ).build(
                task_index=1,
                available_protocols=(PROTOCOL_LEGACY_EXE,),
                attempt_limit=1,
                run_timeout_minutes=1,
            )

        self.assertIsNone(plan.invocation.target_process)


class ResultObserverTest(unittest.TestCase):
    def test_non_terminal_event_does_not_suppress_legacy_success(self) -> None:
        observer = ResultObserver(_policy())

        self.assertIsNone(
            observer.observe_event(
                _event(
                    "task_failed",
                    task="可选步骤",
                    message="本步骤失败",
                )
            )
        )
        result = observer.observe_text(
            "success marker",
            source="legacy-log",
        )

        self.assertTrue(observer.event_protocol_active)
        self.assertFalse(observer.event_terminal_received)
        self.assertIsNotNone(result)
        self.assertTrue(result.successful)

    def test_structured_terminal_is_unique_and_authoritative(self) -> None:
        observer = ResultObserver(_policy())
        result = observer.observe_event(
            _event("run_failed", success=False, message="结构化失败")
        )

        self.assertIsNotNone(result)
        self.assertFalse(result.successful)
        self.assertEqual(result.status, "结构化失败")
        self.assertIsNone(
            observer.observe_text("success marker", source="stdout")
        )

    def test_run_completed_keeps_partial_failure_details(self) -> None:
        observer = ResultObserver(_policy())
        failure = OkScriptRunFailure(task="领取奖励", message="网络错误")
        observer.observe_event(
            _event("task_failed", failures=(failure,))
        )
        result = observer.observe_event(
            _event("run_completed", success=True)
        )

        self.assertIsNotNone(result)
        self.assertTrue(result.successful)
        self.assertEqual(result.failures, (failure,))
        self.assertIn("领取奖励", result.status)


class ConfigSessionTest(unittest.IsolatedAsyncioTestCase):
    async def test_write_back_then_restore_preserves_both_owners(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            mas_dir = root / "mas"
            project_dir = root / "project"
            backup_dir = root / "backup"
            OkConfigStore(mas_dir).write(
                "task.json",
                {"value": "mas", "runtime": False},
                merge=False,
            )
            OkConfigStore(project_dir).write(
                "task.json",
                {"value": "original", "local": 1},
                merge=False,
            )
            session = OkScriptConfigSession(
                mas_config_dir=mas_dir,
                project_config_dir=project_dir,
                backup_dir=backup_dir,
                runtime_overrides=(
                    OkScriptRuntimeConfigOverride(
                        "task.json",
                        "runtime",
                        True,
                    ),
                ),
            )

            await session.inject()
            self.assertEqual(
                OkConfigStore(project_dir).read("task.json"),
                {"value": "mas", "runtime": True},
            )
            OkConfigStore(project_dir).write(
                "task.json",
                {"value": "changed", "runtime": True, "script": 2},
                merge=False,
            )
            await session.write_back()
            await session.restore()

            self.assertEqual(
                OkConfigStore(mas_dir).read("task.json"),
                {"value": "changed", "runtime": False, "script": 2},
            )
            self.assertEqual(
                OkConfigStore(project_dir).read("task.json"),
                {"value": "original", "local": 1},
            )
            self.assertFalse(backup_dir.exists())

    async def test_restore_removes_task_created_project_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            mas_dir = root / "mas"
            project_dir = root / "project"
            OkConfigStore(mas_dir).write(
                "task.json",
                {"enabled": True},
                merge=False,
            )
            session = OkScriptConfigSession(
                mas_config_dir=mas_dir,
                project_config_dir=project_dir,
                backup_dir=root / "backup",
            )

            await session.inject()
            self.assertTrue(project_dir.is_dir())
            await session.restore()

            self.assertFalse(project_dir.exists())

    async def test_missing_runtime_override_target_keeps_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            mas_dir = root / "mas"
            OkConfigStore(mas_dir).write(
                "task.json",
                {"enabled": True},
                merge=False,
            )
            session = OkScriptConfigSession(
                mas_config_dir=mas_dir,
                project_config_dir=root / "project",
                backup_dir=root / "backup",
                runtime_overrides=(
                    OkScriptRuntimeConfigOverride(
                        "missing.json",
                        "reportEnabled",
                        False,
                    ),
                ),
            )

            with patch.object(
                config_session_module.logger,
                "warning",
            ) as warning:
                await session.inject()
            await session.restore()

        warning.assert_called_once()
        self.assertIn("missing.json", warning.call_args.args[0])


class AutoProxyDelegateTest(unittest.IsolatedAsyncioTestCase):
    def _build_task(self, root_path: Path) -> OkScriptAutoProxyTask:
        user_id = str(uuid.uuid4())
        user_item = SimpleNamespace(
            user_id=user_id,
            name="测试用户",
            status="等待",
            log_record={},
        )
        script_info = SimpleNamespace(
            task_info=SimpleNamespace(
                task_id="task-id",
                mode="AutoProxy",
                queue_id="queue-id",
            ),
            user_list=[user_item],
            current_index=0,
            script_id=str(uuid.uuid4()),
            name="测试脚本",
            log="",
        )
        script_config = _FakeConfig(
            {
                ("Info", "RootPath"): str(root_path),
                ("Game", "KillGameOnManualStop"): True,
            }
        )
        user_config = _FakeConfig(
            {
                ("Info", "IfScriptAfterTask"): False,
                ("Info", "RemainedDay"): 3,
                ("Data", "ProxyTimes"): 0,
            }
        )
        return OkScriptAutoProxyTask(
            script_info=script_info,
            script_config=script_config,
            user_config={uuid.UUID(user_id): user_config},
            game_manager=None,
        )

    async def test_check_failure_cleanup_does_not_require_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            task = self._build_task(Path(tmp_dir) / "missing-project")
            result = await task.check()

            self.assertNotEqual(result, "Pass")
            self.assertIsNone(task.provider)
            with patch(
                "ok_script_adapter.adapter.autoproxy.Publisher.send",
                new=AsyncMock(),
            ):
                await task.on_crash(RuntimeError("check failed"))
                await task.final_task()

        self.assertFalse(task.attempt_started)
        self.assertFalse(task.run_result_persisted)

    async def test_observation_and_success_cleanup_map_to_adapter_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            task = self._build_task(Path(tmp_dir))
            task.provider = OKWW_PROVIDER
            task.attempt_started = True
            task.config_session = _FakeConfigSession()
            task.cur_user_log = SimpleNamespace(status="运行中", content=[])
            task._push_dispatch_log = AsyncMock()
            observation = RunObservation(
                status="Success!",
                successful=True,
                user_status="完成",
                source="event",
            )

            await task.on_run_update(
                RunControllerUpdate(
                    kind="observation",
                    observation=observation,
                )
            )
            await task.complete_attempt(
                RunControllerResult(observation=observation, attempts=1)
            )

        self.assertTrue(task.run_book)
        self.assertEqual(task.cur_user_item.status, "完成")
        self.assertEqual(task.cur_user_log.status, "Success!")
        self.assertEqual(task.config_session.write_back_calls, 1)
        self.assertEqual(task.config_session.restore_calls, 1)

    async def test_run_result_persistence_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            task = self._build_task(Path(tmp_dir))
            task.provider = OKWW_PROVIDER
            task.attempt_started = True
            task.run_book = True

            await task._persist_user_run_result()
            await task._persist_user_run_result()

        self.assertEqual(task.cur_user_config.get("Data", "ProxyTimes"), 1)
        self.assertEqual(task.cur_user_config.get("Info", "RemainedDay"), 2)
        self.assertTrue(task.run_result_persisted)


class RunControllerTest(unittest.IsolatedAsyncioTestCase):
    async def test_whole_run_retry_starts_one_process_per_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            plan = _build_plan(Path(tmp_dir), attempt_limit=2)
            manager = _FakeProcessManager()
            reader = _SequencedEventReader(
                manager,
                (
                    _event("run_failed", success=False, message="第一次失败"),
                    _event("run_completed", success=True),
                ),
            )
            delegate = _FakeDelegate()

            async def yield_sleep(delay: float) -> None:
                await asyncio.sleep(0)

            controller = RunController(
                plan,
                process_manager_factory=lambda: manager,
                event_reader=reader,
                sleep=yield_sleep,
                process_poll_interval_seconds=0,
                event_poll_interval_seconds=0,
                exit_event_grace_seconds=0,
            )
            result = await controller.run(delegate)

        self.assertTrue(result.successful)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(manager.open_calls, 2)
        self.assertEqual(delegate.prepared, [1, 2])
        self.assertEqual(len(delegate.failed), 1)
        self.assertTrue(delegate.failed[0][1])
        self.assertEqual(len(delegate.completed), 1)
        self.assertEqual(delegate.game_kills, 1)

    async def test_start_failure_returns_failure_and_cleans_up(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            plan = _build_plan(Path(tmp_dir))
            manager = _FakeProcessManager(
                start_error=RuntimeError("fake start failure")
            )
            delegate = _FakeDelegate()
            controller = RunController(
                plan,
                process_manager_factory=lambda: manager,
                event_reader=lambda path, offset: ([], offset),
                exit_event_grace_seconds=0,
            )

            result = await controller.run(delegate)

        self.assertFalse(result.successful)
        self.assertEqual(result.observation.source, "process-start")
        self.assertEqual(manager.open_calls, 1)
        self.assertGreaterEqual(manager.kill_calls, 1)
        self.assertEqual(delegate.game_kills, 1)
        self.assertEqual(len(delegate.failed), 1)

    async def test_missing_logs_and_events_times_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            plan = replace(
                _build_plan(Path(tmp_dir)),
                log_start_timeout_seconds=0,
                run_timeout_seconds=0.01,
            )
            manager = _FakeProcessManager()
            delegate = _FakeDelegate()
            controller = RunController(
                plan,
                process_manager_factory=lambda: manager,
                event_reader=lambda path, offset: ([], offset),
                process_poll_interval_seconds=0.001,
                event_poll_interval_seconds=0.001,
                exit_event_grace_seconds=0,
            )

            result = await controller.run(delegate)

        self.assertFalse(result.successful)
        self.assertEqual(result.observation.source, "timeout")
        self.assertFalse(manager.running)
        self.assertGreaterEqual(manager.kill_calls, 1)

    async def test_cancel_stops_script_without_overriding_game_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            plan = replace(
                _build_plan(Path(tmp_dir)),
                log_start_timeout_seconds=10,
            )
            manager = _FakeProcessManager()
            delegate = _FakeDelegate()
            controller = RunController(
                plan,
                process_manager_factory=lambda: manager,
                event_reader=lambda path, offset: ([], offset),
                process_poll_interval_seconds=0.05,
                event_poll_interval_seconds=0.05,
            )

            run_task = asyncio.create_task(controller.run(delegate))
            await manager.opened.wait()
            run_task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await run_task

        self.assertFalse(manager.running)
        self.assertGreaterEqual(manager.kill_calls, 1)
        self.assertEqual(delegate.cancelled, 1)
        self.assertEqual(delegate.game_kills, 0)

    async def test_cancel_restores_real_config_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            plan = replace(
                _build_plan(root / "fixture"),
                log_start_timeout_seconds=10,
            )
            mas_dir = root / "mas"
            project_dir = root / "project"
            backup_dir = root / "backup"
            OkConfigStore(mas_dir).write(
                "task.json",
                {"owner": "mas"},
                merge=False,
            )
            OkConfigStore(project_dir).write(
                "task.json",
                {"owner": "project"},
                merge=False,
            )
            session = OkScriptConfigSession(
                mas_config_dir=mas_dir,
                project_config_dir=project_dir,
                backup_dir=backup_dir,
            )
            manager = _FakeProcessManager()
            delegate = _ConfigSessionDelegate(session)
            controller = RunController(
                plan,
                process_manager_factory=lambda: manager,
                event_reader=lambda path, offset: ([], offset),
                process_poll_interval_seconds=0.05,
                event_poll_interval_seconds=0.05,
            )

            run_task = asyncio.create_task(controller.run(delegate))
            await manager.opened.wait()
            self.assertEqual(
                OkConfigStore(project_dir).read("task.json"),
                {"owner": "mas"},
            )
            run_task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await run_task

            self.assertEqual(
                OkConfigStore(project_dir).read("task.json"),
                {"owner": "project"},
            )
            self.assertFalse(backup_dir.exists())

        self.assertEqual(delegate.cancelled, 1)
        self.assertFalse(session.swap_started)


if __name__ == "__main__":
    unittest.main()
