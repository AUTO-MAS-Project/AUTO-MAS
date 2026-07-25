from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.plugins import PluginHttpResponse

from ok_script_adapter.adapter.game_launch import GameLaunchController
from ok_script_adapter.common.provider import (
    GameLaunchDescriptor,
    GamePathResolution,
    resolve_game_path,
)
from ok_script_adapter.plugin import Plugin
from ok_script_adapter.providers.oknte import OKNTE_PROVIDER


class _FakeGameManager:
    def __init__(
        self,
        *,
        open_error: Exception | None = None,
        kill_error: Exception | None = None,
        launcher_exits_immediately: bool = False,
    ) -> None:
        self.open_error = open_error
        self.kill_error = kill_error
        self.launcher_exits_immediately = launcher_exits_immediately
        self.open_calls: list[tuple[Path | str, tuple[str, ...], object | None]] = []
        self.protocol_calls: list[tuple[str, object]] = []
        self.kill_calls = 0
        self.launcher_exited = False
        self.ready_target_observed = False

    async def open_process(
        self,
        program: Path | str,
        *args: str,
        **kwargs: object,
    ) -> None:
        target_process = kwargs.get("target_process")
        self.open_calls.append((program, args, target_process))
        if self.open_error is not None:
            raise self.open_error
        if self.launcher_exits_immediately:
            self.launcher_exited = True
            self.ready_target_observed = target_process is not None

    async def open_protocol(
        self,
        protocol_url: str,
        target_process: object,
    ) -> None:
        self.protocol_calls.append((protocol_url, target_process))
        if self.open_error is not None:
            raise self.open_error

    async def kill(self) -> None:
        self.kill_calls += 1
        if self.kill_error is not None:
            raise self.kill_error


def _resolution(
    root: Path,
    descriptor: GameLaunchDescriptor,
    *,
    launch_name: str | None,
    ready_name: str | None,
    cleanup_names: tuple[str, ...],
) -> GamePathResolution:
    paths: dict[str, Path] = {}

    def create(name: str | None) -> Path | None:
        if not name:
            return None
        path = paths.get(name)
        if path is None:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
            paths[name] = path
        return path

    return GamePathResolution(
        selected_input=str(root),
        descriptor=descriptor,
        launch_path=create(launch_name),
        ready_path=create(ready_name),
        cleanup_paths=tuple(
            path
            for name in cleanup_names
            if (path := create(name)) is not None
        ),
        candidates=(),
    )


class GameLaunchControllerTest(unittest.IsolatedAsyncioTestCase):
    async def test_existing_game_attaches_and_is_still_cleaned_up(self) -> None:
        descriptor = GameLaunchDescriptor(
            ready_process_name="Game.exe",
            already_running_policy="attach",
        )
        manager = _FakeGameManager()
        killed: list[Path] = []

        async def kill_process(path: Path) -> None:
            killed.append(path)

        with tempfile.TemporaryDirectory() as tmp_dir:
            resolution = _resolution(
                Path(tmp_dir),
                descriptor,
                launch_name="Game.exe",
                ready_name="Game.exe",
                cleanup_names=("Game.exe",),
            )
            controller = GameLaunchController(
                display_name="测试游戏",
                descriptor=descriptor,
                resolution=resolution,
                process_manager=manager,
                process_running=lambda name: name == "Game.exe",
                kill_process=kill_process,
            )

            result = await controller.start(arguments=[], fallback_wait_seconds=0)
            cleanup = await controller.cleanup()

        self.assertTrue(result.successful)
        self.assertEqual(result.owner, "external")
        self.assertEqual(manager.open_calls, [])
        self.assertFalse(cleanup.errors)
        self.assertEqual(manager.kill_calls, 1)
        self.assertEqual([path.name for path in killed], ["Game.exe"])

    async def test_start_timeout_is_reported_without_running_real_process(self) -> None:
        descriptor = GameLaunchDescriptor(ready_process_name="Game.exe")
        manager = _FakeGameManager(open_error=TimeoutError("等待游戏进程超时"))

        with tempfile.TemporaryDirectory() as tmp_dir:
            resolution = _resolution(
                Path(tmp_dir),
                descriptor,
                launch_name="Game.exe",
                ready_name="Game.exe",
                cleanup_names=("Game.exe",),
            )
            controller = GameLaunchController(
                display_name="测试游戏",
                descriptor=descriptor,
                resolution=resolution,
                process_manager=manager,
                process_running=lambda _name: False,
            )
            result = await controller.start(arguments=["--test"], fallback_wait_seconds=0)

        self.assertFalse(result.successful)
        self.assertIn("启动失败", result.status)
        self.assertEqual(len(manager.open_calls), 1)
        self.assertEqual(manager.open_calls[0][1], ("--test",))

    async def test_launcher_tracks_game_body_after_launcher_exits(self) -> None:
        descriptor = GameLaunchDescriptor(
            mode="launcher",
            ready_process_name="HTGame.exe",
        )
        manager = _FakeGameManager(launcher_exits_immediately=True)

        with tempfile.TemporaryDirectory() as tmp_dir:
            resolution = _resolution(
                Path(tmp_dir),
                descriptor,
                launch_name="NTEGame.exe",
                ready_name="HTGame.exe",
                cleanup_names=("HTGame.exe",),
            )
            controller = GameLaunchController(
                display_name="异环",
                descriptor=descriptor,
                resolution=resolution,
                process_manager=manager,
                process_running=lambda _name: False,
            )
            result = await controller.start(arguments=[], fallback_wait_seconds=0)

        target_process = manager.open_calls[0][2]
        self.assertTrue(result.successful)
        self.assertTrue(manager.launcher_exited)
        self.assertTrue(manager.ready_target_observed)
        self.assertEqual(getattr(target_process, "name", None), "HTGame.exe")

    async def test_script_managed_mode_skips_launch(self) -> None:
        descriptor = GameLaunchDescriptor(
            mode="script-managed",
            launch_kind="none",
            ready_process_name="Game.exe",
        )
        manager = _FakeGameManager()

        with tempfile.TemporaryDirectory() as tmp_dir:
            resolution = _resolution(
                Path(tmp_dir),
                descriptor,
                launch_name=None,
                ready_name="Game.exe",
                cleanup_names=("Game.exe",),
            )
            controller = GameLaunchController(
                display_name="测试游戏",
                descriptor=descriptor,
                resolution=resolution,
                process_manager=manager,
                process_running=lambda _name: False,
            )
            result = await controller.start(arguments=[], fallback_wait_seconds=0)

        self.assertTrue(result.successful)
        self.assertEqual(result.owner, "script")
        self.assertEqual(manager.open_calls, [])
        self.assertTrue(
            controller.should_cleanup(
                manual_stop=False,
                close_on_manual_stop=False,
            )
        )
        self.assertFalse(
            controller.should_cleanup(
                manual_stop=True,
                close_on_manual_stop=False,
            )
        )

    async def test_attach_mode_requires_existing_game_without_launching(self) -> None:
        descriptor = GameLaunchDescriptor(
            mode="attach",
            launch_kind="none",
            ready_process_name="Game.exe",
        )
        manager = _FakeGameManager()

        with tempfile.TemporaryDirectory() as tmp_dir:
            resolution = _resolution(
                Path(tmp_dir),
                descriptor,
                launch_name=None,
                ready_name="Game.exe",
                cleanup_names=("Game.exe",),
            )
            controller = GameLaunchController(
                display_name="测试游戏",
                descriptor=descriptor,
                resolution=resolution,
                process_manager=manager,
                process_running=lambda name: name == "Game.exe",
            )
            result = await controller.start(arguments=[], fallback_wait_seconds=0)

        self.assertTrue(result.successful)
        self.assertEqual(result.owner, "external")
        self.assertEqual(manager.open_calls, [])

    async def test_uri_mode_uses_ready_target(self) -> None:
        descriptor = GameLaunchDescriptor(
            mode="uri",
            launch_kind="uri",
            launch_uri="test-game://launch",
            ready_process_name="Game.exe",
        )
        manager = _FakeGameManager()

        with tempfile.TemporaryDirectory() as tmp_dir:
            resolution = _resolution(
                Path(tmp_dir),
                descriptor,
                launch_name=None,
                ready_name="Game.exe",
                cleanup_names=("Game.exe",),
            )
            controller = GameLaunchController(
                display_name="测试游戏",
                descriptor=descriptor,
                resolution=resolution,
                process_manager=manager,
                process_running=lambda _name: False,
            )
            result = await controller.start(arguments=[], fallback_wait_seconds=0)

        self.assertTrue(result.successful)
        self.assertEqual(manager.protocol_calls[0][0], "test-game://launch")
        self.assertEqual(
            getattr(manager.protocol_calls[0][1], "name", None),
            "Game.exe",
        )

    async def test_cleanup_continues_after_individual_failures(self) -> None:
        descriptor = GameLaunchDescriptor(ready_process_name="First.exe")
        manager = _FakeGameManager(kill_error=RuntimeError("manager failure"))
        attempted: list[str] = []

        async def kill_process(path: Path) -> None:
            attempted.append(path.name)
            if path.name == "First.exe":
                raise RuntimeError("first failure")

        with tempfile.TemporaryDirectory() as tmp_dir:
            resolution = _resolution(
                Path(tmp_dir),
                descriptor,
                launch_name="First.exe",
                ready_name="First.exe",
                cleanup_names=("First.exe", "Second.exe"),
            )
            controller = GameLaunchController(
                display_name="测试游戏",
                descriptor=descriptor,
                resolution=resolution,
                process_manager=manager,
                kill_process=kill_process,
            )
            cleanup = await controller.cleanup()

        self.assertTrue(cleanup.attempted)
        self.assertEqual(len(cleanup.errors), 2)
        self.assertEqual(attempted, ["First.exe", "Second.exe"])


class GameLaunchDescriptorTest(unittest.TestCase):
    def test_disabled_game_management_delegates_direct_and_attach_modes(self) -> None:
        for mode, launch_kind in (("direct", "executable"), ("attach", "none")):
            descriptor = GameLaunchDescriptor(
                mode=mode,
                launch_kind=launch_kind,
                cleanup_policy="always",
            )
            for game_enabled, launch_before_task in ((False, True), (True, False)):
                with self.subTest(
                    mode=mode,
                    game_enabled=game_enabled,
                    launch_before_task=launch_before_task,
                ):
                    effective = descriptor.with_effective_mode(
                        game_enabled=game_enabled,
                        launch_before_task=launch_before_task,
                    )
                    self.assertEqual(effective.mode, "script-managed")
                    self.assertEqual(effective.cleanup_policy, "always")


class GamePathResolutionTest(unittest.IsolatedAsyncioTestCase):
    async def test_nte_resolution_keeps_launcher_and_game_body_roles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "NTEGame.exe").touch()
            (root / "HTGame.exe").touch()

            resolution = resolve_game_path(OKNTE_PROVIDER, root)
            plugin = object.__new__(Plugin)
            response = await plugin._resolve_game_path(
                SimpleNamespace(
                    json={
                        "rootPath": str(root),
                        "selectedPath": str(root),
                        "resourceName": "ok-nte",
                    },
                    query={},
                )
            )

        self.assertFalse(resolution.ambiguous)
        self.assertEqual(resolution.launch_path.name, "NTEGame.exe")
        self.assertEqual(resolution.ready_path.name, "HTGame.exe")
        self.assertEqual([path.name for path in resolution.cleanup_paths], ["HTGame.exe"])
        self.assertEqual(response["code"], 200)
        self.assertEqual(response["data"]["path"], resolution.launch_path.as_posix())
        self.assertEqual(
            response["data"]["formPatch"],
            {"Game": {"Path": resolution.launch_path.as_posix()}},
        )
        self.assertEqual(
            response["data"]["resolution"]["readyTarget"]["path"],
            resolution.ready_path.as_posix(),
        )

    async def test_nte_ambiguous_launchers_return_diagnostic_http_409(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "NTEGame.exe").touch()
            (root / "NTEGlobalGame.exe").touch()
            (root / "HTGame.exe").touch()
            plugin = object.__new__(Plugin)
            response = await plugin._resolve_game_path(
                SimpleNamespace(
                    json={
                        "root_path": str(root),
                        "selected_path": str(root),
                        "resource_name": "ok-nte",
                    },
                    query={},
                )
            )

        self.assertIsInstance(response, PluginHttpResponse)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.body["code"], 409)
        self.assertTrue(response.body["data"]["resolution"]["ambiguous"])
        self.assertIsNone(response.body["data"]["path"])
        self.assertEqual(response.body["data"]["formPatch"], {})


if __name__ == "__main__":
    unittest.main()
