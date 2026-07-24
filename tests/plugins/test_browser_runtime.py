from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


# ── workspace 包 src 路径注入 ─────────────────────────────────────────────
# auto_mas_core 和 automas_plugin_browser 都是 uv workspace 包,
# 在没有 uv venv 的最小测试环境下, 需要手动把它们的 src 加到 sys.path。
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _rel in ("plugins/auto_mas_core/src", "plugins/browser/src"):
    _src_dir = _REPO_ROOT / _rel
    if _src_dir.is_dir():
        _normalized = str(_src_dir.resolve())
        if _normalized not in sys.path:
            sys.path.insert(0, _normalized)


def _load_module_from_file(module_name: str, file_path: Path):
    """按文件路径直接加载 Python 模块, 绕开 app.plugins.__init__.py 的副作用导入。

    本测试模块只用到 cache_store.PluginCacheManager 和 system.get_system_plugin_spec,
    不需要 __init__.py 中的完整 API (依赖 typing.Unpack, Python 3.11+ 才可用)。
    生产集成测试 (阶段 6) 会通过 uv venv (Python 3.12) 走完整 import 路径。
    """
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_cache_store_module = _load_module_from_file(
    "_cache_store_under_test", _REPO_ROOT / "app" / "plugins" / "cache_store.py"
)
_system_module = _load_module_from_file(
    "_system_under_test", _REPO_ROOT / "app" / "plugins" / "system.py"
)

PluginCacheManager = _cache_store_module.PluginCacheManager
get_system_plugin_spec = _system_module.get_system_plugin_spec

from auto_mas_core import BROWSER_RUNTIME_SERVICE
from automas_plugin_browser.backend import (
    BrowserDriverHandle,
    PreparedBinaries,
    SeleniumBrowserBackend,
)
from automas_plugin_browser.errors import BrowserRuntimeError
from automas_plugin_browser.models import BrowserOpenOptions, BrowserPrepareRequest
from automas_plugin_browser.plugin import Plugin
from automas_plugin_browser.schema import Config
from automas_plugin_browser.service import BrowserRuntime


PLUGIN_FIELD_MARKER = "x-auto-mas-plugin-field"


class _Logger:
    def info(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def warning(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def exception(self, *_args: Any, **_kwargs: Any) -> None:
        pass


class _Backend:
    def __init__(self) -> None:
        self.opened_paths: list[Path] = []
        self.closed = 0
        self.fail_next_open = False
        self.fail_launch_cleanup = False
        self.fail_next_close = False
        self.fail_all_closes = False
        self.prepare_delay = 0.0
        self.block_prepare = False
        self.prepare_started = threading.Event()
        self.prepare_release = threading.Event()
        self.prepare_paths: list[Path] = []
        self.aborted_prepare_paths: list[Path] = []
        self.completed_prepare_paths: list[Path] = []
        self.active_prepares = 0
        self.max_active_prepares = 0
        self.prepare_guard = threading.Lock()
        self.block_open = False
        self.open_started = threading.Event()
        self.open_release = threading.Event()
        self.block_close = False
        self.close_started = threading.Event()
        self.close_release = threading.Event()
        self.cleanup_sessions: list[str] = []
        self.block_status = False
        self.status_started = threading.Event()
        self.status_release = threading.Event()
        self.dead_status_once = False
        self.confirm_gone = False

    def prepare(
        self,
        config: Config,
        request: BrowserPrepareRequest,
        assets_root: Path,
    ) -> PreparedBinaries:
        self.prepare_paths.append(assets_root)
        with self.prepare_guard:
            self.active_prepares += 1
            self.max_active_prepares = max(
                self.max_active_prepares,
                self.active_prepares,
            )
        try:
            if self.block_prepare:
                self.prepare_started.set()
                self.prepare_release.wait()
            if self.prepare_delay:
                time.sleep(self.prepare_delay)
            mode = request.browser_mode or config.browser_mode
            return PreparedBinaries(
                requested_mode=mode,
                resolved_mode="chrome",
                browser_path="managed-chrome",
                driver_path="managed-driver",
                browser_version=request.browser_version or config.managed_browser_version,
            )
        finally:
            with self.prepare_guard:
                self.active_prepares -= 1

    def open(
        self,
        config: Config,
        options: Any,
        profile_path: Path,
        binaries: PreparedBinaries,
        session_id: str,
    ) -> BrowserDriverHandle:
        del config, options
        if self.fail_next_open:
            self.fail_next_open = False
            raise BrowserRuntimeError(
                "LAUNCH_FAILED",
                "fake launch failure",
                operation="open_session",
            )
        if self.fail_launch_cleanup:
            raise BrowserRuntimeError(
                "LAUNCH_CLEANUP_FAILED",
                "fake launch cleanup failure",
                operation="open_session",
                retryable=True,
                safe_details={
                    "surviving_processes": [],
                    "process_scan_complete": False,
                    "profile_quarantine_required": True,
                },
            )
        if self.block_open:
            self.open_started.set()
            self.open_release.wait()
        self.opened_paths.append(profile_path)
        return BrowserDriverHandle(
            driver=object(),
            binaries=binaries,
            driver_pid=1234,
            debugger_address="127.0.0.1:9222",
            session_id=session_id,
        )

    def status(self, _handle: BrowserDriverHandle) -> dict[str, Any]:
        if self.block_status:
            self.status_started.set()
            self.status_release.wait()
        if self.dead_status_once:
            self.dead_status_once = False
            return {
                "alive": False,
                "url": "",
                "title": "",
                "driver_pid": 1234,
                "window_handle": None,
                "error_type": "DeadDriver",
            }
        return {
            "alive": True,
            "url": "https://example.invalid/",
            "title": "Example",
            "driver_pid": 1234,
            "window_handle": 4321,
        }

    def navigate(self, handle: BrowserDriverHandle, url: str) -> dict[str, Any]:
        result = self.status(handle)
        result["url"] = url
        return result

    def activate(self, _handle: BrowserDriverHandle) -> bool:
        return True

    def capture(
        self,
        _handle: BrowserDriverHandle,
        image_format: str,
        quality: int,
    ) -> bytes:
        return f"{image_format}:{quality}".encode()

    def execute_script(
        self,
        _handle: BrowserDriverHandle,
        script: str,
        *args: Any,
    ) -> Any:
        return {"script": script, "args": list(args)}

    def execute_cdp(
        self,
        _handle: BrowserDriverHandle,
        command: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        return {"command": command, "params": params}

    def close(self, _handle: BrowserDriverHandle) -> None:
        if self.block_close:
            self.close_started.set()
            self.close_release.wait()
        if self.fail_all_closes or self.fail_next_close:
            self.fail_next_close = False
            raise BrowserRuntimeError(
                "CLOSE_FAILED",
                "fake close failure",
                operation="close_session",
                retryable=True,
            )
        self.closed += 1

    def cleanup_session(self, session_id: str) -> None:
        self.cleanup_sessions.append(session_id)
        if self.fail_all_closes:
            raise BrowserRuntimeError(
                "CLOSE_FAILED",
                "fake cleanup failure",
                operation="close_session",
                retryable=True,
            )
        self.close_release.set()
        self.status_release.set()

    def abort_prepare(self, assets_root: Path) -> None:
        self.aborted_prepare_paths.append(assets_root)

    def mark_prepare_done(self, assets_root: Path) -> None:
        self.completed_prepare_paths.append(assets_root)

    def confirm_session_gone(self, _session_id: str) -> bool:
        return self.confirm_gone


class _DeadDriver:
    def quit(self) -> None:
        raise RuntimeError("driver already exited")


class _BlockingDriver:
    def __init__(self) -> None:
        self.release = threading.Event()

    def quit(self) -> None:
        self.release.wait(timeout=5)


class _LaunchFailDriver:
    capabilities: dict[str, Any] = {}
    service = None

    def set_page_load_timeout(self, _seconds: int) -> None:
        raise RuntimeError("post-launch setup failed")


class _TrackedProcess:
    pid = 24680

    def __init__(self) -> None:
        self.terminated = False

    def create_time(self) -> float:
        return 123.0

    def is_running(self) -> bool:
        return True

    def status(self) -> str:
        return "running"

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.terminated = True


class _IdentityProcess:
    def __init__(
        self,
        *,
        pid: int = 24681,
        created_at: float = 123.0,
        name: str = "chromedriver.exe",
        executable: str = "C:\\tools\\chromedriver.exe",
    ) -> None:
        self.pid = pid
        self._created_at = created_at
        self._name = name
        self._executable = executable
        self.terminated = False

    def create_time(self) -> float:
        return self._created_at

    def name(self) -> str:
        return self._name

    def exe(self) -> str:
        return self._executable

    def children(self, *, recursive: bool = False) -> list[Any]:
        del recursive
        return []

    def is_running(self) -> bool:
        return not self.terminated

    def status(self) -> str:
        return "terminated" if self.terminated else "running"

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.terminated = True


class _ManagerProcess(_IdentityProcess):
    def __init__(self, cache_root: Path) -> None:
        super().__init__(
            pid=24682,
            name="selenium-manager.exe",
            executable="C:\\tools\\selenium-manager.exe",
        )
        self.info = {
            "pid": self.pid,
            "name": self.name(),
            "cmdline": [self.exe(), "--cache-path", str(cache_root)],
        }


class _FakeWebDriverOptions:
    def __init__(self) -> None:
        self.binary_location = ""

    def add_argument(self, _argument: str) -> None:
        pass

    def add_experimental_option(self, _name: str, _value: Any) -> None:
        pass


class _FakeWebDriverService:
    def __init__(self, **_kwargs: Any) -> None:
        pass


def _fake_selenium_modules() -> dict[str, types.ModuleType]:
    selenium = types.ModuleType("selenium")
    webdriver = types.ModuleType("selenium.webdriver")
    webdriver.Chrome = lambda **_kwargs: _LaunchFailDriver()  # type: ignore[attr-defined]
    webdriver.Edge = lambda **_kwargs: _LaunchFailDriver()  # type: ignore[attr-defined]
    selenium.webdriver = webdriver  # type: ignore[attr-defined]

    modules = {
        "selenium": selenium,
        "selenium.webdriver": webdriver,
    }
    for engine in ("chrome", "edge"):
        package_name = f"selenium.webdriver.{engine}"
        package = types.ModuleType(package_name)
        options = types.ModuleType(f"{package_name}.options")
        service = types.ModuleType(f"{package_name}.service")
        options.Options = _FakeWebDriverOptions  # type: ignore[attr-defined]
        service.Service = _FakeWebDriverService  # type: ignore[attr-defined]
        modules[package_name] = package
        modules[f"{package_name}.options"] = options
        modules[f"{package_name}.service"] = service
    return modules


class _Server:
    def __init__(self) -> None:
        self.paths: list[str] = []

    def http(self, path: str, _handler: Any, **_kwargs: Any) -> None:
        self.paths.append(path)


class _PluginContext:
    def __init__(self) -> None:
        self.instance_id = "browser:system"
        self.logger = _Logger()
        self.server = _Server()


class _ConfigProxy:
    def to_dict(self) -> dict[str, Any]:
        return Config().model_dump(mode="json")


class _Service:
    def __init__(self, server: _Server) -> None:
        self.server = server
        self.published: list[tuple[str, Any]] = []

    def set(self, name: str, value: Any) -> None:
        if len(self.server.paths) != 3:
            raise AssertionError("service published before all routes")
        self.published.append((name, value))


class _LifecycleContext(_PluginContext):
    def __init__(self, data_dir: Path, *, fail_route: int | None = None) -> None:
        super().__init__()
        self.config = _ConfigProxy()
        self.data_dir = data_dir
        if fail_route is not None:
            original_http = self.server.http

            def failing_http(path: str, handler: Any, **kwargs: Any) -> None:
                if len(self.server.paths) + 1 == fail_route:
                    raise RuntimeError("fake route registration failure")
                original_http(path, handler, **kwargs)

            self.server.http = failing_http  # type: ignore[method-assign]
        self.service = _Service(self.server)


class BrowserBackendTest(unittest.TestCase):
    def test_driver_quit_has_a_hard_deadline(self) -> None:
        backend = SeleniumBrowserBackend()
        driver = _BlockingDriver()
        started_at = time.perf_counter()
        with patch(
            "automas_plugin_browser.backend._DRIVER_QUIT_TIMEOUT_SECONDS",
            0.02,
        ):
            error = backend._quit_driver(driver)
        driver.release.set()

        self.assertIsInstance(error, TimeoutError)
        self.assertLess(time.perf_counter() - started_at, 0.5)

    def test_partial_launch_reports_cleanup_failure_for_profile_quarantine(self) -> None:
        backend = SeleniumBrowserBackend()
        options = BrowserOpenOptions(
            owner_instance_id="browser:system",
            namespace="default",
            profile_id="partial",
            initial_url="about:blank",
            browser_mode="managed",
            browser_version="stable",
            headless=True,
            app_mode=True,
            window_width=1920,
            window_height=1080,
            page_load_timeout_seconds=60,
            preferences={},
            extra_arguments=[],
            reuse_policy="error",
            session_token=None,
            automation_engine="none",
        )
        binaries = PreparedBinaries(
            requested_mode="managed",
            resolved_mode="chrome",
            browser_path="managed-chrome",
            driver_path="managed-driver",
            browser_version="stable",
        )
        cleanup_error = BrowserRuntimeError(
            "CLOSE_FAILED",
            "fake cleanup failure",
            operation="open_session",
            safe_details={
                "surviving_processes": [],
                "process_scan_complete": False,
            },
        )
        with tempfile.TemporaryDirectory() as profile_dir:
            with (
                patch.dict(sys.modules, _fake_selenium_modules()),
                patch.object(backend, "close", side_effect=cleanup_error),
                self.assertRaises(BrowserRuntimeError) as failed,
            ):
                backend.open(
                    Config(),
                    options,
                    Path(profile_dir),
                    binaries,
                    "partial-session",
                )

        self.assertEqual(failed.exception.code, "LAUNCH_CLEANUP_FAILED")
        self.assertTrue(
            failed.exception.safe_details["profile_quarantine_required"]
        )

    def test_close_tracks_tagged_browser_after_driver_already_exited(self) -> None:
        backend = SeleniumBrowserBackend()
        process = _TrackedProcess()
        handle = BrowserDriverHandle(
            driver=_DeadDriver(),
            binaries=PreparedBinaries(
                requested_mode="managed",
                resolved_mode="chrome",
                browser_path="managed-chrome",
                driver_path="managed-driver",
                browser_version="stable",
            ),
            driver_pid=1234,
            debugger_address="127.0.0.1:9222",
            session_id="tracked-session",
        )
        scans = [([process], True), ([process], True), ([], True)]
        with (
            patch.object(backend, "_driver_process_tree", return_value=[]),
            patch.object(backend, "_session_process_tree", side_effect=scans),
            patch(
                "automas_plugin_browser.backend.psutil.wait_procs",
                return_value=([], []),
            ),
            patch(
                "automas_plugin_browser.backend.psutil.pid_exists",
                return_value=False,
            ),
        ):
            backend.close(handle)

        self.assertTrue(process.terminated)

    def test_driver_pid_reuse_is_never_treated_as_original_webdriver(self) -> None:
        backend = SeleniumBrowserBackend()
        reused = _IdentityProcess(created_at=456.0)
        with patch(
            "automas_plugin_browser.backend.psutil.Process",
            return_value=reused,
        ):
            processes = backend._driver_process_tree(
                reused.pid,
                123.0,
                "C:\\tools\\chromedriver.exe",
                "chromedriver.exe",
            )

        self.assertEqual(processes, [])
        self.assertFalse(reused.terminated)

        wrong_executable = _IdentityProcess(
            created_at=123.0,
            executable="C:\\other\\chromedriver.exe",
        )
        with patch(
            "automas_plugin_browser.backend.psutil.Process",
            return_value=wrong_executable,
        ):
            self.assertEqual(
                backend._driver_process_tree(
                    wrong_executable.pid,
                    123.0,
                    "C:\\tools\\chromedriver.exe",
                    "chromedriver.exe",
                ),
                [],
            )
        self.assertFalse(wrong_executable.terminated)

    def test_launch_watchdog_kills_driver_that_appears_after_initial_cleanup(self) -> None:
        backend = SeleniumBrowserBackend()
        service = types.SimpleNamespace(process=None)
        process = _IdentityProcess()
        with (
            patch(
                "automas_plugin_browser.backend.psutil.Process",
                return_value=process,
            ),
            patch(
                "automas_plugin_browser.backend.psutil.process_iter",
                return_value=[],
            ),
            patch(
                "automas_plugin_browser.backend.psutil.wait_procs",
                return_value=([], []),
            ),
        ):
            tracker = backend._begin_session_tracker(
                "permanent-launch",
                service,
                "C:\\tools\\chromedriver.exe",
            )
            tracker.request_cleanup()
            time.sleep(0.35)
            service.process = types.SimpleNamespace(pid=process.pid)
            for _ in range(30):
                if process.terminated:
                    break
                time.sleep(0.05)
            tracker.mark_operation_done()
            for _ in range(30):
                if not backend._session_trackers:
                    break
                time.sleep(0.05)

        self.assertTrue(process.terminated)

    def test_restart_recovery_requires_two_complete_empty_tag_scans(self) -> None:
        backend = SeleniumBrowserBackend()
        with patch.object(
            backend,
            "_session_process_tree",
            side_effect=[([], True), ([], True)],
        ) as scan:
            self.assertTrue(backend.confirm_session_gone("restart-session"))
        self.assertEqual(scan.call_count, 2)

    def test_prepare_watchdog_kills_late_selenium_manager(self) -> None:
        backend = SeleniumBrowserBackend()
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_root = Path(temp_dir) / "isolated-attempt"
            process = _ManagerProcess(cache_root)
            visible: list[_ManagerProcess] = []
            with (
                patch(
                    "automas_plugin_browser.backend.psutil.process_iter",
                    side_effect=lambda _attrs: list(visible),
                ),
                patch(
                    "automas_plugin_browser.backend.psutil.wait_procs",
                    return_value=([], []),
                ),
            ):
                backend.abort_prepare(cache_root)
                time.sleep(0.65)
                visible.append(process)
                for _ in range(30):
                    if process.terminated:
                        break
                    time.sleep(0.05)
                backend.mark_prepare_done(cache_root)
                for _ in range(30):
                    if not backend._prepare_watchdogs:
                        break
                    time.sleep(0.05)

        self.assertTrue(process.terminated)


class BrowserRuntimeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.backend = _Backend()
        self.runtime = BrowserRuntime(
            config=Config(),
            data_dir=Path(self.temp_dir.name),
            logger=_Logger(),
            backend=self.backend,
        )

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_profile_is_single_writer_and_released_after_close(self) -> None:
        request = {
            "owner_instance_id": "hsr:system",
            "namespace": "hsr",
            "profile_id": "user-1",
            "initial_url": "https://sr.mihoyo.com/cloud",
        }
        first = await self.runtime.open_session(request)

        with self.assertRaises(BrowserRuntimeError) as raised:
            await self.runtime.open_session(request)
        self.assertEqual(raised.exception.code, "PROFILE_BUSY")

        await self.runtime.close_session(
            first["session_id"],
            session_token=first["session_token"],
        )
        second = await self.runtime.open_session(request)
        self.assertNotEqual(first["session_id"], second["session_id"])
        self.assertEqual(self.backend.opened_paths[0], self.backend.opened_paths[1])

    async def test_reuse_returns_existing_session_without_second_launch(self) -> None:
        request = {
            "owner_instance_id": "browser:system",
            "namespace": "manual",
            "profile_id": "default",
            "reuse_policy": "reuse",
        }
        first = await self.runtime.open_session(request)
        second = await self.runtime.open_session(
            {**request, "session_token": first["session_token"]}
        )

        self.assertEqual(first["session_id"], second["session_id"])
        self.assertTrue(second["reused"])
        self.assertEqual(len(self.backend.opened_paths), 1)

    async def test_failed_launch_releases_profile_reservation(self) -> None:
        self.backend.fail_next_open = True
        request = {
            "owner_instance_id": "hsr:system",
            "namespace": "hsr",
            "profile_id": "recoverable",
        }
        with self.assertRaises(BrowserRuntimeError):
            await self.runtime.open_session(request)

        result = await self.runtime.open_session(request)
        self.assertEqual(result["profile_id"], "recoverable")

    async def test_dead_on_arrival_is_launch_failed_and_fully_released(self) -> None:
        self.backend.dead_status_once = True
        request = {"profile_id": "dead-on-arrival"}
        with self.assertRaises(BrowserRuntimeError) as failed:
            await self.runtime.open_session(request)
        self.assertEqual(failed.exception.code, "LAUNCH_FAILED")
        self.assertEqual(self.runtime.list_sessions(), [])

        recovered = await self.runtime.open_session(request)
        self.assertEqual(recovered["profile_id"], "dead-on-arrival")

    async def test_partial_launch_cleanup_failure_quarantines_profile(self) -> None:
        request = {"profile_id": "partial-launch"}
        self.backend.fail_launch_cleanup = True
        with self.assertRaises(BrowserRuntimeError) as failed:
            await self.runtime.open_session(request)
        self.assertEqual(failed.exception.code, "LAUNCH_CLEANUP_FAILED")

        restarted = BrowserRuntime(
            config=Config(),
            data_dir=Path(self.temp_dir.name),
            logger=_Logger(),
            backend=_Backend(),
        )
        with self.assertRaises(BrowserRuntimeError) as quarantined:
            await restarted.open_session(request)
        self.assertEqual(quarantined.exception.code, "PROFILE_QUARANTINED")
        await restarted.shutdown()

    async def test_restart_recovers_quarantine_after_double_session_tag_scan(self) -> None:
        request = {"profile_id": "restart-recovery"}
        self.backend.fail_launch_cleanup = True
        with self.assertRaises(BrowserRuntimeError):
            await self.runtime.open_session(request)

        restart_backend = _Backend()
        restart_backend.confirm_gone = True
        restarted = BrowserRuntime(
            config=Config(),
            data_dir=Path(self.temp_dir.name),
            logger=_Logger(),
            backend=restart_backend,
        )
        recovered = await restarted.open_session(request)
        self.assertEqual(recovered["profile_id"], "restart-recovery")
        self.assertFalse(
            list(Path(self.temp_dir.name).rglob(".auto-mas-quarantine.json"))
        )
        await restarted.shutdown()

    async def test_profiles_are_isolated_and_manifest_contains_no_credentials(self) -> None:
        first = await self.runtime.open_session(
            {
                "owner_instance_id": "hsr:system",
                "namespace": "hsr",
                "profile_id": "user-a",
            }
        )
        second = await self.runtime.open_session(
            {
                "owner_instance_id": "hsr:system",
                "namespace": "hsr",
                "profile_id": "user-b",
            }
        )

        self.assertNotEqual(self.backend.opened_paths[0], self.backend.opened_paths[1])
        profiles = self.runtime.list_profiles()
        serialized = json.dumps(profiles, ensure_ascii=False).lower()
        self.assertNotIn("cookie_token", serialized)
        self.assertNotIn("password", serialized)
        self.assertEqual({item["profile_id"] for item in profiles}, {"user-a", "user-b"})
        await self.runtime.close_session(
            first["session_id"],
            session_token=first["session_token"],
        )
        await self.runtime.close_session(
            second["session_id"],
            session_token=second["session_token"],
        )

    async def test_path_traversal_and_reserved_arguments_are_rejected(self) -> None:
        with self.assertRaises(BrowserRuntimeError) as traversal:
            await self.runtime.open_session({"profile_id": "../escape"})
        self.assertEqual(traversal.exception.code, "INVALID_REQUEST")

        with self.assertRaises(BrowserRuntimeError) as reserved:
            await self.runtime.open_session(
                {"extra_arguments": ["--user-data-dir=C:\\shared-profile"]}
            )
        self.assertEqual(reserved.exception.code, "INVALID_REQUEST")

    async def test_cdp_capture_navigation_and_owner_cleanup(self) -> None:
        session = await self.runtime.open_session(
            {
                "owner_instance_id": "hsr:system",
                "namespace": "hsr",
                "profile_id": "user-1",
            }
        )
        session_id = session["session_id"]
        session_token = session["session_token"]

        navigated = await self.runtime.navigate(
            session_id,
            "https://sr.mihoyo.com/cloud",
            session_token=session_token,
        )
        self.assertEqual(navigated["url"], "https://sr.mihoyo.com/cloud")
        self.assertEqual(
            await self.runtime.capture(
                session_id,
                session_token=session_token,
                quality=88,
            ),
            b"jpeg:88",
        )
        self.assertEqual(
            await self.runtime.execute_cdp(
                session_id,
                "Emulation.setDeviceMetricsOverride",
                {"width": 1920, "height": 1080},
                session_token=session_token,
            ),
            {
                "command": "Emulation.setDeviceMetricsOverride",
                "params": {"width": 1920, "height": 1080},
            },
        )
        results = await self.runtime.close_owner_sessions("hsr:system")
        self.assertEqual(results[0]["closed"], True)
        self.assertEqual(self.runtime.list_sessions(), [])

    async def test_session_token_is_required_for_control_and_reuse(self) -> None:
        request = {
            "owner_instance_id": "hsr:system",
            "namespace": "hsr",
            "profile_id": "protected",
            "reuse_policy": "reuse",
        }
        session = await self.runtime.open_session(request)

        with self.assertRaises(BrowserRuntimeError) as forbidden:
            await self.runtime.navigate(
                session["session_id"],
                "https://sr.mihoyo.com/cloud",
                session_token="x" * 32,
            )
        self.assertEqual(forbidden.exception.code, "SESSION_FORBIDDEN")

        with self.assertRaises(BrowserRuntimeError) as busy:
            await self.runtime.open_session(request)
        self.assertEqual(busy.exception.code, "PROFILE_BUSY")
        self.assertNotIn("session_token", self.runtime.list_sessions()[0])

    async def test_m7a_handoff_is_exclusive_until_released(self) -> None:
        session = await self.runtime.open_session(
            {
                "owner_instance_id": "hsr:system",
                "namespace": "hsr",
                "profile_id": "m7a-user",
                "initial_url": "https://sr.mihoyo.com/cloud",
                "automation_engine": "m7a",
            }
        )
        handoff = await self.runtime.automation_handoff(
            session["session_id"],
            session_token=session["session_token"],
        )
        self.assertEqual(handoff["engine"], "m7a")
        self.assertEqual(handoff["debugger_port"], 9222)
        self.assertTrue(handoff["exclusive"])
        self.assertFalse(handoff["upstream_supported"])
        self.assertEqual(
            handoff["compatibility"],
            "requires-mas-external-owner-build",
        )
        self.assertNotIn("MARCH7TH_DRIVER_PATH", handoff["environment"])
        self.assertFalse(handoff["config_patch"]["browser_dump_cookies_enable"])

        with self.assertRaises(BrowserRuntimeError) as leased:
            await self.runtime.capture(
                session["session_id"],
                session_token=session["session_token"],
            )
        self.assertEqual(leased.exception.code, "SESSION_LEASED")

        released = await self.runtime.release_automation_handoff(
            session["session_id"],
            session_token=session["session_token"],
            lease_token=handoff["lease_token"],
        )
        self.assertEqual(released["automation_state"], "idle")

    async def test_sra_handoff_requires_compatible_external_session_build(self) -> None:
        session = await self.runtime.open_session(
            {
                "owner_instance_id": "hsr:system",
                "namespace": "hsr",
                "profile_id": "sra-user",
                "initial_url": "https://sr.mihoyo.com/cloud",
                "automation_engine": "sra",
            }
        )
        handoff = await self.runtime.automation_handoff(
            session["session_id"],
            session_token=session["session_token"],
        )
        self.assertEqual(handoff["engine"], "sra")
        self.assertFalse(handoff["upstream_supported"])
        self.assertEqual(
            handoff["compatibility"],
            "requires-mas-external-session-build",
        )
        self.assertEqual(
            handoff["environment"]["AUTO_MAS_BROWSER_DEBUGGER_ADDRESS"],
            "127.0.0.1:9222",
        )
        await self.runtime.release_automation_handoff(
            session["session_id"],
            session_token=session["session_token"],
            lease_token=handoff["lease_token"],
        )

    async def test_close_failure_keeps_profile_quarantined(self) -> None:
        request = {
            "owner_instance_id": "hsr:system",
            "namespace": "hsr",
            "profile_id": "orphaned",
        }
        session = await self.runtime.open_session(request)
        self.backend.fail_next_close = True
        with self.assertRaises(BrowserRuntimeError) as close_error:
            await self.runtime.close_session(
                session["session_id"],
                session_token=session["session_token"],
            )
        self.assertEqual(close_error.exception.code, "CLOSE_FAILED")
        self.assertEqual(self.runtime.list_sessions()[0]["state"], "orphaned")

        with self.assertRaises(BrowserRuntimeError) as busy:
            await self.runtime.open_session(request)
        self.assertEqual(busy.exception.code, "PROFILE_BUSY")

        await self.runtime.close_session(
            session["session_id"],
            session_token=session["session_token"],
        )
        reopened = await self.runtime.open_session(request)
        self.assertNotEqual(reopened["session_id"], session["session_id"])

    async def test_concurrent_first_open_serializes_browser_preparation(self) -> None:
        self.backend.prepare_delay = 0.05
        first, second = await asyncio.gather(
            self.runtime.open_session({"profile_id": "parallel-a"}),
            self.runtime.open_session({"profile_id": "parallel-b"}),
        )
        self.assertEqual(self.backend.max_active_prepares, 1)
        self.assertNotEqual(first["session_id"], second["session_id"])

    async def test_prepare_timeout_retries_in_a_different_cache_directory(self) -> None:
        backend = _Backend()
        backend.block_prepare = True
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = BrowserRuntime(
                config=Config(),
                data_dir=Path(temp_dir),
                logger=_Logger(),
                backend=backend,
                prepare_timeout_seconds=0.05,
                shutdown_timeout_seconds=0.2,
            )
            with self.assertRaises(BrowserRuntimeError) as failed:
                await runtime.prepare()
            self.assertEqual(failed.exception.code, "PREPARE_TIMEOUT")
            self.assertTrue(backend.prepare_started.is_set())

            backend.block_prepare = False
            prepared = await runtime.prepare()
            self.assertTrue(prepared["driver_ready"])
            self.assertEqual(len(backend.prepare_paths), 2)
            self.assertNotEqual(backend.prepare_paths[0], backend.prepare_paths[1])
            self.assertEqual(backend.aborted_prepare_paths, [backend.prepare_paths[0]])
            self.assertEqual(backend.max_active_prepares, 2)

            backend.prepare_release.set()
            for _ in range(50):
                if backend.prepare_paths[0] in backend.completed_prepare_paths:
                    break
                await asyncio.sleep(0.01)
            self.assertIn(backend.prepare_paths[0], backend.completed_prepare_paths)
            await runtime.shutdown()

    async def test_operation_timeout_background_cleanup_releases_profile(self) -> None:
        backend = _Backend()
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = BrowserRuntime(
                config=Config(),
                data_dir=Path(temp_dir),
                logger=_Logger(),
                backend=backend,
                operation_timeout_seconds=0.05,
                shutdown_timeout_seconds=0.2,
            )
            session = await runtime.open_session({"profile_id": "operation-timeout"})
            backend.block_status = True
            with self.assertRaises(BrowserRuntimeError) as failed:
                await runtime.session_status(
                    session["session_id"],
                    session_token=session["session_token"],
                )
            self.assertEqual(failed.exception.code, "OPERATION_TIMEOUT")

            for _ in range(50):
                if not runtime.list_sessions():
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(runtime.list_sessions(), [])
            self.assertFalse(list(Path(temp_dir).rglob(".auto-mas-quarantine.json")))

            backend.block_status = False
            recovered = await runtime.open_session({"profile_id": "operation-timeout"})
            self.assertTrue(recovered["session_id"])
            await runtime.shutdown()

    async def test_launch_timeout_returns_and_late_driver_is_cleaned(self) -> None:
        backend = _Backend()
        backend.block_open = True
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = BrowserRuntime(
                config=Config(),
                data_dir=Path(temp_dir),
                logger=_Logger(),
                backend=backend,
                launch_timeout_seconds=0.05,
                close_timeout_seconds=0.1,
                shutdown_timeout_seconds=0.2,
            )
            started_at = time.perf_counter()
            with self.assertRaises(BrowserRuntimeError) as raised:
                await runtime.open_session({"profile_id": "launch-timeout"})
            self.assertEqual(raised.exception.code, "LAUNCH_TIMEOUT")
            self.assertLess(time.perf_counter() - started_at, 0.5)
            for _ in range(50):
                if (
                    backend.cleanup_sessions
                    and not list(Path(temp_dir).rglob(".auto-mas-quarantine.json"))
                ):
                    break
                await asyncio.sleep(0.01)
            self.assertTrue(backend.cleanup_sessions)
            self.assertFalse(list(Path(temp_dir).rglob(".auto-mas-quarantine.json")))

            # 原 open 永久卡住时，watchdog 成功后同一 Profile 已可重新使用。
            backend.block_open = False
            replacement = await runtime.open_session({"profile_id": "launch-timeout"})
            await runtime.close_session(
                replacement["session_id"],
                session_token=replacement["session_token"],
            )
            backend.open_release.set()
            for _ in range(50):
                if backend.closed >= 2:
                    break
                await asyncio.sleep(0.01)
            self.assertGreaterEqual(backend.closed, 2)
            await runtime.shutdown()

    async def test_close_timeout_quarantines_and_continues_process_cleanup(self) -> None:
        backend = _Backend()
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = BrowserRuntime(
                config=Config(),
                data_dir=Path(temp_dir),
                logger=_Logger(),
                backend=backend,
                close_timeout_seconds=0.05,
                shutdown_timeout_seconds=0.2,
            )
            session = await runtime.open_session({"profile_id": "close-timeout"})
            backend.block_close = True
            started_at = time.perf_counter()
            with self.assertRaises(BrowserRuntimeError) as raised:
                await runtime.close_session(
                    session["session_id"],
                    session_token=session["session_token"],
                )
            self.assertEqual(raised.exception.code, "CLOSE_TIMEOUT")
            self.assertLess(time.perf_counter() - started_at, 0.5)

            for _ in range(50):
                if backend.cleanup_sessions and not runtime.list_sessions():
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(backend.cleanup_sessions, [session["session_id"]])
            self.assertEqual(runtime.list_sessions(), [])
            self.assertFalse(list(Path(temp_dir).rglob(".auto-mas-quarantine.json")))
            await runtime.shutdown()

    async def test_shutdown_deadline_does_not_wait_for_stuck_launch(self) -> None:
        backend = _Backend()
        backend.block_open = True
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = BrowserRuntime(
                config=Config(),
                data_dir=Path(temp_dir),
                logger=_Logger(),
                backend=backend,
                launch_timeout_seconds=5.0,
                close_timeout_seconds=0.05,
                shutdown_timeout_seconds=0.1,
            )
            opening = asyncio.create_task(
                runtime.open_session({"profile_id": "shutdown-timeout"})
            )
            started = await asyncio.to_thread(backend.open_started.wait, 1)
            self.assertTrue(started)

            started_at = time.perf_counter()
            await runtime.shutdown()
            self.assertLess(time.perf_counter() - started_at, 0.5)
            with self.assertRaises(asyncio.CancelledError):
                await opening

            backend.open_release.set()
            for _ in range(50):
                if backend.closed:
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(backend.closed, 1)

    async def test_shutdown_cancels_and_cleans_inflight_open(self) -> None:
        self.backend.block_open = True
        opening = asyncio.create_task(
            self.runtime.open_session({"profile_id": "stopping"})
        )
        started = await asyncio.to_thread(self.backend.open_started.wait, 2)
        self.assertTrue(started)

        shutdown = asyncio.create_task(self.runtime.shutdown())
        await asyncio.sleep(0)
        self.backend.open_release.set()
        await shutdown
        with self.assertRaises(asyncio.CancelledError):
            await opening
        self.assertEqual(self.runtime.list_sessions(), [])

    async def test_failed_inflight_cleanup_persists_profile_quarantine(self) -> None:
        request = {"profile_id": "stubborn-open"}
        self.backend.block_open = True
        self.backend.fail_all_closes = True
        opening = asyncio.create_task(self.runtime.open_session(request))
        started = await asyncio.to_thread(self.backend.open_started.wait, 2)
        self.assertTrue(started)

        shutdown = asyncio.create_task(self.runtime.shutdown())
        await asyncio.sleep(0)
        self.backend.open_release.set()
        await shutdown
        with self.assertRaises(asyncio.CancelledError):
            await opening
        for _ in range(50):
            if self.runtime.list_sessions():
                break
            await asyncio.sleep(0.01)
        self.assertEqual(self.runtime.list_sessions()[0]["state"], "orphaned")

        restarted = BrowserRuntime(
            config=Config(),
            data_dir=Path(self.temp_dir.name),
            logger=_Logger(),
            backend=_Backend(),
        )
        with self.assertRaises(BrowserRuntimeError) as quarantined:
            await restarted.open_session(request)
        self.assertEqual(quarantined.exception.code, "PROFILE_QUARANTINED")

        self.backend.fail_all_closes = False
        await self.runtime.close_all()
        reopened = await restarted.open_session(request)
        self.assertTrue(reopened["session_id"])
        await restarted.shutdown()

    async def test_http_manual_action_never_returns_session_secrets(self) -> None:
        ctx = _PluginContext()
        plugin = Plugin(ctx)
        plugin.runtime = self.runtime
        plugin.config = Config()

        response = await plugin._open_default(None)
        serialized = json.dumps(response, ensure_ascii=False).lower()
        self.assertEqual(response["code"], 200)
        self.assertNotIn("session_id", serialized)
        self.assertNotIn("session_token", serialized)
        self.assertNotIn("profile_id", serialized)
        self.assertNotIn("url", serialized)
        self.assertNotIn("title", serialized)
        await plugin._close_default(None)


class BrowserPluginLifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def test_routes_are_ready_before_service_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ctx = _LifecycleContext(Path(temp_dir))
            plugin = Plugin(ctx)
            await plugin.on_start()

            self.assertEqual(
                ctx.server.paths,
                [
                    "/browser/capabilities",
                    "/browser/open-default",
                    "/browser/close-default",
                ],
            )
            self.assertEqual(ctx.service.published[0][0], BROWSER_RUNTIME_SERVICE)
            await plugin.on_stop("test")

    async def test_route_failure_shuts_down_runtime_without_publishing_service(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ctx = _LifecycleContext(Path(temp_dir), fail_route=2)
            plugin = Plugin(ctx)
            with self.assertRaises(RuntimeError):
                await plugin.on_start()

            self.assertEqual(ctx.service.published, [])
            self.assertIsNone(plugin.runtime)
            self.assertIsNone(plugin.config)


class BrowserPluginRegistrationTest(unittest.TestCase):
    def test_browser_is_a_locked_system_plugin(self) -> None:
        spec = get_system_plugin_spec("browser")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.package_name, "automas-plugin-browser")
        self.assertEqual(BROWSER_RUNTIME_SERVICE, "browser.runtime.v1")

    def test_default_config_uses_managed_browser_and_blank_page(self) -> None:
        config = Config()
        self.assertEqual(config.browser_mode, "managed")
        self.assertEqual(config.home_url, "about:blank")

    def test_all_config_fields_use_plugin_field_metadata(self) -> None:
        for name, model_field in Config.model_fields.items():
            extra = model_field.json_schema_extra
            self.assertIsInstance(extra, dict, name)
            self.assertTrue(extra.get(PLUGIN_FIELD_MARKER), name)

        schema = Config.model_json_schema()["properties"]
        self.assertEqual(schema["browser_path"]["type"], "path")
        self.assertEqual(schema["browser_path"]["path_kind"], "file")
        self.assertEqual(schema["extra_arguments"]["json_type"], "array")
        self.assertEqual(schema["browser_mode"]["size"], "half")

    def test_data_directory_wraps_existing_cache_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = PluginCacheManager(
                plugin_name="browser",
                instance_id="browser:system",
                data_root=Path(temp_dir),
                logger=_Logger(),
            )
            self.assertEqual(
                manager.instance_cache_dir,
                manager.instance_data_dir / "plugin_cache",
            )

    def test_electron_deployment_includes_browser_plugin(self) -> None:
        source = Path(
            "frontend/electron/services/repositoryService.ts"
        ).read_text(encoding="utf-8")
        self.assertIn("'plugins/browser'", source)

    def test_http_routes_do_not_expose_global_sessions_or_profiles(self) -> None:
        ctx = _PluginContext()
        plugin = Plugin(ctx)
        plugin._register_routes()
        self.assertEqual(
            ctx.server.paths,
            [
                "/browser/capabilities",
                "/browser/open-default",
                "/browser/close-default",
            ],
        )


if __name__ == "__main__":
    unittest.main()
