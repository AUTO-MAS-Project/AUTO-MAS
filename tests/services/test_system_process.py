import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import psutil

from app.services.system import _ProcessPathScan, _SystemHandler


class SystemProcessTest(unittest.IsolatedAsyncioTestCase):
    async def test_kill_process_by_pid_reports_taskkill_failure(self) -> None:
        handler = _SystemHandler()
        process_result = SimpleNamespace(
            returncode=5,
            stdout="",
            stderr="Access is denied.",
        )

        with (
            patch(
                "app.services.system.ProcessRunner.run_process",
                new_callable=AsyncMock,
                return_value=process_result,
            ) as run_process,
            patch("app.services.system.psutil.pid_exists", return_value=True),
        ):
            success = await handler.kill_process_by_pid(123)

        run_process.assert_awaited_once_with("taskkill", "/F", "/T", "/PID", "123")
        self.assertFalse(success)

    async def test_kill_process_by_pid_can_skip_process_tree(self) -> None:
        handler = _SystemHandler()
        process_result = SimpleNamespace(returncode=0, stdout="", stderr="")

        with (
            patch(
                "app.services.system.ProcessRunner.run_process",
                new_callable=AsyncMock,
                return_value=process_result,
            ) as run_process,
            patch("app.services.system.psutil.pid_exists", return_value=False),
        ):
            success = await handler.kill_process_by_pid(123, kill_tree=False)

        run_process.assert_awaited_once_with("taskkill", "/F", "/PID", "123")
        self.assertTrue(success)

    async def test_kill_process_preserves_process_tree_option(self) -> None:
        handler = _SystemHandler()

        with (
            patch.object(
                handler,
                "_scan_processes_by_path",
                new_callable=AsyncMock,
                return_value=_ProcessPathScan([123], [], True),
            ),
            patch.object(
                handler,
                "kill_process_by_pid",
                new_callable=AsyncMock,
                return_value=True,
            ) as kill_process_by_pid,
        ):
            success = await handler.kill_process(Path("SRC/src.exe"), kill_tree=False)

        kill_process_by_pid.assert_awaited_once_with(123, kill_tree=False)
        self.assertTrue(success)

    async def test_kill_process_by_pid_accepts_already_exited_process(self) -> None:
        handler = _SystemHandler()
        process_result = SimpleNamespace(
            returncode=128,
            stdout="",
            stderr="The process not found.",
        )

        with (
            patch(
                "app.services.system.ProcessRunner.run_process",
                new_callable=AsyncMock,
                return_value=process_result,
            ),
            patch("app.services.system.psutil.pid_exists", return_value=False),
        ):
            success = await handler.kill_process_by_pid(123)

        self.assertTrue(success)

    async def test_kill_process_aggregates_pid_results(self) -> None:
        handler = _SystemHandler()

        with (
            patch.object(
                handler,
                "_scan_processes_by_path",
                new_callable=AsyncMock,
                return_value=_ProcessPathScan([123, 456], [], True),
            ),
            patch.object(
                handler,
                "kill_process_by_pid",
                new_callable=AsyncMock,
                side_effect=[True, False],
            ) as kill_process_by_pid,
        ):
            success = await handler.kill_process(Path("SRC/src.exe"))

        self.assertEqual(kill_process_by_pid.await_count, 2)
        self.assertFalse(success)

    async def test_kill_process_continues_after_pid_exception(self) -> None:
        handler = _SystemHandler()

        with (
            patch.object(
                handler,
                "_scan_processes_by_path",
                new_callable=AsyncMock,
                return_value=_ProcessPathScan([123, 456], [], True),
            ),
            patch.object(
                handler,
                "kill_process_by_pid",
                new_callable=AsyncMock,
                side_effect=[RuntimeError("taskkill failed"), True],
            ) as kill_process_by_pid,
            patch("app.services.system.logger"),
        ):
            with self.assertRaisesRegex(RuntimeError, "taskkill failed"):
                await handler.kill_process(Path("SRC/src.exe"))

        self.assertEqual(kill_process_by_pid.await_count, 2)
        kill_process_by_pid.assert_any_await(123, kill_tree=True)
        kill_process_by_pid.assert_any_await(456, kill_tree=True)

    async def test_kill_process_skips_unreadable_same_name(self) -> None:
        handler = _SystemHandler()
        process = SimpleNamespace(info={"pid": 123, "name": "src.exe", "exe": None})

        with (
            patch("app.services.system.psutil.process_iter", return_value=[process]),
            patch.object(
                handler,
                "kill_process_by_pid",
                new_callable=AsyncMock,
            ) as kill_process_by_pid,
        ):
            success = await handler.kill_process(Path("SRC/src.exe"))

        kill_process_by_pid.assert_not_awaited()
        self.assertTrue(success)

    async def test_kill_process_ignores_readable_same_name_at_other_path(self) -> None:
        handler = _SystemHandler()
        process = SimpleNamespace(
            info={"pid": 123, "name": "src.exe", "exe": "Other/src.exe"}
        )

        with (
            patch("app.services.system.psutil.process_iter", return_value=[process]),
            patch.object(
                handler,
                "kill_process_by_pid",
                new_callable=AsyncMock,
            ) as kill_process_by_pid,
        ):
            success = await handler.kill_process(Path("SRC/src.exe"))

        kill_process_by_pid.assert_not_awaited()
        self.assertTrue(success)

    async def test_kill_process_cleans_exact_matches_despite_uncertainty(self) -> None:
        handler = _SystemHandler()
        processes = [
            SimpleNamespace(
                info={"pid": 123, "name": "src.exe", "exe": str(Path("SRC/src.exe"))}
            ),
            SimpleNamespace(info={"pid": 456, "name": "src.exe", "exe": None}),
        ]

        with (
            patch("app.services.system.psutil.process_iter", return_value=processes),
            patch.object(
                handler,
                "kill_process_by_pid",
                new_callable=AsyncMock,
                return_value=True,
            ) as kill_process_by_pid,
        ):
            success = await handler.kill_process(Path("SRC/src.exe"))

        kill_process_by_pid.assert_awaited_once_with(123, kill_tree=True)
        self.assertTrue(success)

    async def test_kill_process_reports_incomplete_scan(self) -> None:
        handler = _SystemHandler()

        with patch(
            "app.services.system.psutil.process_iter",
            side_effect=psutil.AccessDenied(pid=123),
        ):
            success = await handler.kill_process(Path("SRC/src.exe"))

        self.assertFalse(success)

    async def test_kill_process_accepts_string_path(self) -> None:
        handler = _SystemHandler()

        with patch.object(
            handler,
            "_scan_processes_by_path",
            new_callable=AsyncMock,
            return_value=_ProcessPathScan([], [], True),
        ) as scan_processes:
            success = await handler.kill_process("Game/game.exe")

        scan_processes.assert_awaited_once_with(Path("Game/game.exe"))
        self.assertTrue(success)


if __name__ == "__main__":
    unittest.main()
