"""worker 被强杀后，它启动的 agent 不能留成孤儿。

MaaFW 的 AgentClient 以 IPC 模式启动项目 agent，生命周期本该随 worker：
worker 正常结束时 `MaaFWRunner.shutdown()` 会 terminate 它们，owner 看门狗
触发时 `_terminate_descendants()` 也会。

漏的是**宿主强杀 worker** 这条：用户中止任务时宿主调 `process.terminate()`，
Windows 上那是 `TerminateProcess`——立即且不可捕获，worker 的 shutdown()
根本没机会跑。

实测后果：进程表里残留二十多个 agent.exe / python.exe，最老的二十二小时，
占内存也占文件句柄——曾导致 venv 目录因 `[WinError 5] Access is denied` 删不掉。

关键是**顺序**：必须在 terminate 之前把后代记下来。父进程一死子进程就被重新
挂到别处，事后再按父子关系已经查不到它们。
"""

import ast
import unittest
from pathlib import Path
from unittest import mock

import psutil

import app.core  # noqa: F401  # 初始化宿主配置

SOURCE_PATH = (
    Path(__file__).resolve().parents[2] / "app/task/MaaFW/tools/embedded/runner_task.py"
)
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")


def load():
    import importlib
    import sys

    patcher = mock.patch.dict(
        sys.modules,
        {
            name: mock.MagicMock()
            for name in (
                "maa",
                "maa.agent_client",
                "maa.context",
                "maa.controller",
                "maa.custom_action",
                "maa.custom_recognition",
                "maa.define",
                "maa.event_sink",
                "maa.job",
                "maa.library",
                "maa.notification_handler",
                "maa.resource",
                "maa.tasker",
                "maa.toolkit",
            )
        },
    )
    patcher.start()
    return (
        importlib.import_module("app.task.MaaFW.tools.embedded.runner_task"),
        patcher,
    )


class SnapshotBeforeTerminateTest(unittest.TestCase):
    """顺序错了整个机制就失效，所以直接钉住源码里的先后。"""

    def _body(self) -> str:
        body = SOURCE[SOURCE.index("async def _terminate_runner_process") :]
        return body[: body.index(chr(10) + "    def ", 10)]

    def test_the_snapshot_is_taken_before_terminating(self) -> None:
        body = self._body()
        self.assertLess(
            body.index("_snapshot_descendants"),
            body.index("process.terminate()"),
            "必须先记下后代再 terminate，否则事后查不到它们",
        )

    def test_survivors_are_cleaned_after_the_worker_exits(self) -> None:
        body = self._body()
        self.assertLess(
            body.index("process.terminate()"), body.index("_terminate_snapshot")
        )

    def test_cleanup_runs_off_the_event_loop(self) -> None:
        """psutil 的遍历与等待是阻塞调用，不能占着事件循环。"""

        body = self._body()
        for call in ("_snapshot_descendants", "_terminate_snapshot"):
            with self.subTest(call=call):
                self.assertIn(f"asyncio.to_thread({call}", body)


class SnapshotTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module, patcher = load()
        self.addCleanup(patcher.stop)

    def test_snapshot_records_pid_and_create_time(self) -> None:
        child = mock.Mock(pid=4242)
        child.create_time.return_value = 1000.0
        with mock.patch.object(
            self.module.psutil,
            "Process",
            return_value=mock.Mock(children=mock.Mock(return_value=[child])),
        ):
            self.assertEqual(self.module._snapshot_descendants(1), [(4242, 1000.0)])

    def test_a_vanished_parent_yields_nothing(self) -> None:
        with mock.patch.object(
            self.module.psutil, "Process", side_effect=psutil.NoSuchProcess(1)
        ):
            self.assertEqual(self.module._snapshot_descendants(1), [])


class TerminateSnapshotTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module, patcher = load()
        self.addCleanup(patcher.stop)

    def _process(self, create_time: float):
        proc = mock.Mock()
        proc.create_time.return_value = create_time
        return proc

    def test_matching_processes_are_terminated(self) -> None:
        proc = self._process(1000.0)
        with (
            mock.patch.object(self.module.psutil, "Process", return_value=proc),
            mock.patch.object(
                self.module.psutil, "wait_procs", return_value=([proc], [])
            ),
        ):
            self.module._terminate_snapshot([(4242, 1000.0)])
        proc.terminate.assert_called_once()

    def test_a_reused_pid_is_left_alone(self) -> None:
        """pid 可能已被别的进程占用——创建时间对不上就不能碰。"""

        proc = self._process(9999.0)
        with (
            mock.patch.object(self.module.psutil, "Process", return_value=proc),
            mock.patch.object(self.module.psutil, "wait_procs") as wait_procs,
        ):
            self.module._terminate_snapshot([(4242, 1000.0)])
        proc.terminate.assert_not_called()
        wait_procs.assert_not_called()

    def test_stubborn_processes_are_killed(self) -> None:
        proc = self._process(1000.0)
        with (
            mock.patch.object(self.module.psutil, "Process", return_value=proc),
            mock.patch.object(
                self.module.psutil, "wait_procs", return_value=([], [proc])
            ),
        ):
            self.module._terminate_snapshot([(4242, 1000.0)])
        proc.kill.assert_called_once()

    def test_an_already_gone_process_is_not_an_error(self) -> None:
        with mock.patch.object(
            self.module.psutil, "Process", side_effect=psutil.NoSuchProcess(4242)
        ):
            self.module._terminate_snapshot([(4242, 1000.0)])  # 不得抛

    def test_an_empty_snapshot_does_nothing(self) -> None:
        with mock.patch.object(self.module.psutil, "wait_procs") as wait_procs:
            self.module._terminate_snapshot([])
        wait_procs.assert_not_called()


class ExistingPathsStillCleanUpTest(unittest.TestCase):
    """另外两条本来就覆盖的路径不能被改坏。"""

    def test_runner_shutdown_still_terminates_agents(self) -> None:
        runner = (
            Path(__file__).resolve().parents[2]
            / "app/task/MaaFW/tools/core/automas_maafw_runner/runner.py"
        ).read_text(encoding="utf-8")
        body = runner[runner.index("def shutdown(self)") :]
        body = body[: body.index(chr(10) + "    def ", 10)]
        self.assertIn("process.terminate()", body)
        self.assertIn("agent_client.disconnect()", body)

    def test_owner_watchdog_still_kills_descendants_before_exiting(self) -> None:
        worker = (
            Path(__file__).resolve().parents[2]
            / "app/task/MaaFW/tools/core/automas_maafw_runner/worker.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(worker)
        watch = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_watch_owner"
        )
        calls = [
            node.func.id
            for node in ast.walk(watch)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        self.assertIn("_terminate_descendants", calls)


if __name__ == "__main__":
    unittest.main()
