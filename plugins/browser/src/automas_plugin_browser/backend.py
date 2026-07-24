from __future__ import annotations

import base64
import ctypes
import os
import shutil
import sys
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil

from .errors import BrowserRuntimeError
from .models import BrowserOpenOptions, BrowserPrepareRequest
from .schema import Config


_DRIVER_QUIT_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class PreparedBinaries:
    requested_mode: str
    resolved_mode: str
    browser_path: str
    driver_path: str
    browser_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_mode": self.requested_mode,
            "resolved_mode": self.resolved_mode,
            "browser_path": self.browser_path,
            "driver_path": self.driver_path,
            "browser_version": self.browser_version,
        }


@dataclass(slots=True)
class BrowserDriverHandle:
    driver: Any
    binaries: PreparedBinaries
    driver_pid: int | None
    debugger_address: str
    session_id: str
    driver_create_time: float | None = None
    driver_executable: str = ""
    driver_name: str = ""


@dataclass(frozen=True, slots=True)
class _ProcessIdentity:
    pid: int
    created_at: float
    executable: str
    name: str


class _SessionProcessWatchdog:
    """持续跟踪 Selenium Service，并在超时后回收迟到的驱动进程。"""

    def __init__(
        self,
        *,
        backend: SeleniumBrowserBackend,
        session_id: str,
        service: Any,
        expected_driver_path: str,
        on_exit: Any,
    ) -> None:
        self._backend = backend
        self._session_id = session_id
        self._service = service
        self._expected_driver_path = expected_driver_path
        self._on_exit = on_exit
        self._identity_lock = threading.Lock()
        self._identity: _ProcessIdentity | None = None
        self._cleanup_requested = threading.Event()
        self._operation_done = threading.Event()
        self._clean = threading.Event()
        self._stop = threading.Event()
        self._finished = threading.Event()
        self._worker = threading.Thread(
            target=self._run,
            name=f"browser-process-watchdog-{session_id[:8]}",
            daemon=True,
        )
        self._worker.start()

    @property
    def identity(self) -> _ProcessIdentity | None:
        self._capture_service_identity()
        with self._identity_lock:
            return self._identity

    @property
    def operation_done(self) -> bool:
        return self._operation_done.is_set()

    @property
    def finished(self) -> bool:
        return self._finished.is_set()

    def request_cleanup(self) -> None:
        self._cleanup_requested.set()

    def mark_operation_done(self) -> None:
        self._operation_done.set()

    def wait_clean(self, timeout: float) -> bool:
        return self._clean.wait(timeout=max(0.0, timeout))

    def stop(self) -> None:
        self._stop.set()

    def _capture_service_identity(self) -> None:
        process = getattr(self._service, "process", None)
        pid = getattr(process, "pid", None)
        if not isinstance(pid, int) or pid <= 0:
            return
        identity = self._backend._capture_webdriver_identity(
            pid,
            self._expected_driver_path,
        )
        if identity is None:
            return
        with self._identity_lock:
            self._identity = identity

    def _cleanup_once(self) -> tuple[bool, bool]:
        self._capture_service_identity()
        identity = self.identity
        driver_processes = self._backend._driver_process_tree(
            identity.pid if identity is not None else None,
            identity.created_at if identity is not None else None,
            identity.executable if identity is not None else "",
            identity.name if identity is not None else "",
        )
        tagged_processes, first_scan_complete = self._backend._session_process_tree(
            self._session_id
        )
        self._backend._terminate_processes(
            self._backend._merge_processes(driver_processes, tagged_processes)
        )
        tagged_survivors, final_scan_complete = self._backend._session_process_tree(
            self._session_id
        )
        driver_survivors = self._backend._driver_process_tree(
            identity.pid if identity is not None else None,
            identity.created_at if identity is not None else None,
            identity.executable if identity is not None else "",
            identity.name if identity is not None else "",
        )
        alive = self._backend._alive_processes(
            self._backend._merge_processes(driver_survivors, tagged_survivors)
        )
        return not alive, first_scan_complete and final_scan_complete

    def _run(self) -> None:
        stable_clean_scans = 0
        try:
            while not self._stop.is_set():
                self._capture_service_identity()
                if self._cleanup_requested.is_set():
                    clean, scan_complete = self._cleanup_once()
                    if clean and scan_complete:
                        stable_clean_scans += 1
                        if stable_clean_scans >= 3:
                            self._clean.set()
                    else:
                        stable_clean_scans = 0
                        self._clean.clear()

                    # 永久卡住的 open 仍需继续守护；只有调用确实返回后才能退出。
                    if self._operation_done.is_set() and self._clean.is_set():
                        return
                self._stop.wait(0.1)
        finally:
            self._finished.set()
            self._on_exit(self)


class _PrepareProcessWatchdog:
    """持续清理某个隔离 cache 下迟到出现的 selenium-manager。"""

    def __init__(
        self,
        backend: SeleniumBrowserBackend,
        cache_root: Path,
        on_exit: Any,
    ) -> None:
        self._backend = backend
        self._cache_root = str(cache_root.resolve()).casefold()
        self._on_exit = on_exit
        self._operation_done = threading.Event()
        self._worker = threading.Thread(
            target=self._run,
            name="browser-prepare-watchdog",
            daemon=True,
        )
        self._worker.start()

    def mark_operation_done(self) -> None:
        self._operation_done.set()

    def _matching_processes(self) -> tuple[list[psutil.Process], bool]:
        matches: list[psutil.Process] = []
        scan_complete = True
        try:
            iterator = psutil.process_iter(["pid", "name", "cmdline"])
        except psutil.Error:
            return [], False
        for process in iterator:
            try:
                name = str(process.info.get("name") or "").casefold()
                if name not in {"selenium-manager", "selenium-manager.exe"}:
                    continue
                command_line = [
                    str(item).casefold()
                    for item in (process.info.get("cmdline") or [])
                ]
                if not any(self._cache_root in item for item in command_line):
                    continue
                matches.append(process)
                matches.extend(process.children(recursive=True))
            except psutil.NoSuchProcess:
                continue
            except psutil.Error:
                scan_complete = False
        return self._backend._merge_processes(matches), scan_complete

    def _run(self) -> None:
        stable_clean_scans = 0
        try:
            while True:
                processes, first_complete = self._matching_processes()
                self._backend._terminate_processes(processes)
                survivors, final_complete = self._matching_processes()
                clean = not self._backend._alive_processes(survivors)
                if clean and first_complete and final_complete:
                    stable_clean_scans += 1
                else:
                    stable_clean_scans = 0
                if self._operation_done.is_set() and stable_clean_scans >= 3:
                    return
                # 永久卡住时也持续守护隔离目录，防止迟到子进程泄漏。
                time.sleep(0.2)
        finally:
            self._on_exit(self)


class SeleniumBrowserBackend:
    """封装 Selenium、浏览器二进制和原生窗口操作。"""

    def __init__(self) -> None:
        self._tracker_lock = threading.Lock()
        self._session_trackers: dict[str, _SessionProcessWatchdog] = {}
        self._prepare_watchdogs: dict[str, _PrepareProcessWatchdog] = {}

    def abort_prepare(self, assets_root: Path) -> None:
        """隔离目录内的 prepare 超时后，持续回收 selenium-manager。"""
        key = str(assets_root.resolve()).casefold()

        def discard(completed: _PrepareProcessWatchdog) -> None:
            with self._tracker_lock:
                if self._prepare_watchdogs.get(key) is completed:
                    self._prepare_watchdogs.pop(key, None)

        with self._tracker_lock:
            if key not in self._prepare_watchdogs:
                self._prepare_watchdogs[key] = _PrepareProcessWatchdog(
                    self,
                    assets_root,
                    discard,
                )

    def mark_prepare_done(self, assets_root: Path) -> None:
        key = str(assets_root.resolve()).casefold()
        with self._tracker_lock:
            watchdog = self._prepare_watchdogs.get(key)
        if watchdog is not None:
            watchdog.mark_operation_done()

    def confirm_session_gone(self, session_id: str) -> bool:
        """跨重启恢复前，对会话标记进行两次完整扫描确认。"""
        if not session_id:
            return False
        for attempt in range(2):
            processes, scan_complete = self._session_process_tree(session_id)
            if not scan_complete or self._alive_processes(processes):
                return False
            if attempt == 0:
                time.sleep(0.1)
        return True

    def _begin_session_tracker(
        self,
        session_id: str,
        service: Any,
        driver_path: str,
    ) -> _SessionProcessWatchdog:
        def discard(completed: _SessionProcessWatchdog) -> None:
            with self._tracker_lock:
                if self._session_trackers.get(session_id) is completed:
                    self._session_trackers.pop(session_id, None)

        tracker = _SessionProcessWatchdog(
            backend=self,
            session_id=session_id,
            service=service,
            expected_driver_path=driver_path,
            on_exit=discard,
        )
        with self._tracker_lock:
            previous = self._session_trackers.get(session_id)
            self._session_trackers[session_id] = tracker
        if previous is not None:
            previous.request_cleanup()
        return tracker

    def _session_tracker(self, session_id: str) -> _SessionProcessWatchdog | None:
        with self._tracker_lock:
            return self._session_trackers.get(session_id)

    def prepare(
        self,
        config: Config,
        request: BrowserPrepareRequest,
        assets_root: Path,
    ) -> PreparedBinaries:
        requested_mode = request.browser_mode or config.browser_mode
        resolved_mode, detected_path = self._resolve_mode(
            requested_mode,
            config.browser_path,
        )
        browser_path = detected_path or config.browser_path.strip()
        driver_path = config.driver_path.strip()

        if browser_path and not Path(browser_path).is_file():
            raise BrowserRuntimeError(
                "UNAVAILABLE",
                "配置的浏览器路径不存在",
                operation="prepare",
            )
        if driver_path and not Path(driver_path).is_file():
            raise BrowserRuntimeError(
                "UNAVAILABLE",
                "配置的 WebDriver 路径不存在",
                operation="prepare",
            )
        if resolved_mode == "custom" and not browser_path:
            raise BrowserRuntimeError(
                "UNAVAILABLE",
                "custom 模式必须配置浏览器路径",
                operation="prepare",
            )

        if resolved_mode == "custom":
            resolved_mode = self._engine_from_path(browser_path)

        browser_version = ""
        if resolved_mode == "managed":
            browser_version = request.browser_version or config.managed_browser_version
        engine = "chrome" if resolved_mode == "managed" else resolved_mode

        if browser_path and driver_path:
            return PreparedBinaries(
                requested_mode=requested_mode,
                resolved_mode=engine,
                browser_path=browser_path,
                driver_path=driver_path,
                browser_version=browser_version,
            )

        assets_root.mkdir(parents=True, exist_ok=True)
        try:
            from selenium.webdriver.common.selenium_manager import SeleniumManager
        except ImportError as exc:
            raise BrowserRuntimeError(
                "UNAVAILABLE",
                "Selenium 未安装，无法准备浏览器运行时",
                operation="prepare",
            ) from exc

        manager_args = [
            "--browser",
            engine,
            "--cache-path",
            str(assets_root),
            "--timeout",
            str(config.manager_timeout_seconds),
            "--avoid-stats",
        ]
        if resolved_mode == "managed":
            manager_args.extend(
                [
                    "--browser-version",
                    browser_version,
                    "--force-browser-download",
                    "--skip-driver-in-path",
                    "--skip-browser-in-path",
                ]
            )
        else:
            manager_args.append("--avoid-browser-download")
            if browser_path:
                manager_args.extend(["--browser-path", browser_path])

        if config.browser_mirror_url:
            manager_args.extend(["--browser-mirror-url", config.browser_mirror_url])
        if config.driver_mirror_url:
            manager_args.extend(["--driver-mirror-url", config.driver_mirror_url])

        try:
            result = SeleniumManager().binary_paths(manager_args)
        except Exception as exc:
            raise BrowserRuntimeError(
                "UNAVAILABLE",
                "浏览器或 WebDriver 准备失败",
                operation="prepare",
                retryable=True,
                safe_details={"error_type": type(exc).__name__, "mode": requested_mode},
            ) from exc

        resolved_browser_path = browser_path or str(result.get("browser_path") or "")
        resolved_driver_path = driver_path or str(result.get("driver_path") or "")
        if not resolved_browser_path or not resolved_driver_path:
            raise BrowserRuntimeError(
                "UNAVAILABLE",
                "Selenium Manager 未返回完整的浏览器运行时",
                operation="prepare",
                safe_details={"mode": requested_mode},
            )

        return PreparedBinaries(
            requested_mode=requested_mode,
            resolved_mode=engine,
            browser_path=resolved_browser_path,
            driver_path=resolved_driver_path,
            browser_version=browser_version,
        )

    def open(
        self,
        config: Config,
        options: BrowserOpenOptions,
        profile_path: Path,
        binaries: PreparedBinaries,
        session_id: str,
    ) -> BrowserDriverHandle:
        profile_path.mkdir(parents=True, exist_ok=True)

        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options as ChromeOptions
            from selenium.webdriver.chrome.service import Service as ChromeService
            from selenium.webdriver.edge.options import Options as EdgeOptions
            from selenium.webdriver.edge.service import Service as EdgeService
        except ImportError as exc:
            raise BrowserRuntimeError(
                "UNAVAILABLE",
                "Selenium 未安装，无法打开浏览器",
                operation="open_session",
            ) from exc

        if binaries.resolved_mode == "edge":
            webdriver_options = EdgeOptions()
            service = EdgeService(
                executable_path=binaries.driver_path,
                log_output=os.devnull,
            )
            webdriver_factory = webdriver.Edge
        else:
            webdriver_options = ChromeOptions()
            service = ChromeService(
                executable_path=binaries.driver_path,
                log_output=os.devnull,
            )
            webdriver_factory = webdriver.Chrome

        webdriver_options.binary_location = binaries.browser_path
        arguments = [
            f"--auto-mas-browser-session={session_id}",
            f"--lang={config.language}",
            "--log-level=3",
            f"--user-data-dir={profile_path}",
            "--profile-directory=Default",
            f"--window-size={options.window_width},{options.window_height}",
        ]
        if options.app_mode:
            arguments.append(f"--app={options.initial_url}")
        if options.automation_engine != "none":
            arguments.append("--force-device-scale-factor=1")
        if options.headless:
            arguments.extend(["--headless=new", "--mute-audio"])
        arguments.extend(config.extra_arguments)
        arguments.extend(options.extra_arguments)
        for argument in arguments:
            webdriver_options.add_argument(argument)
        if options.preferences:
            webdriver_options.add_experimental_option("prefs", options.preferences)

        tracker = self._begin_session_tracker(
            session_id,
            service,
            binaries.driver_path,
        )
        driver: Any = None
        try:
            driver = webdriver_factory(service=service, options=webdriver_options)
            driver.set_page_load_timeout(options.page_load_timeout_seconds)
            if not options.app_mode:
                driver.get(options.initial_url)
            if not options.headless:
                driver.set_window_size(options.window_width, options.window_height)
            driver_pid = self._driver_pid(driver)
            identity = tracker.identity or self._capture_webdriver_identity(
                driver_pid,
                binaries.driver_path,
            )
            return BrowserDriverHandle(
                driver=driver,
                binaries=binaries,
                driver_pid=driver_pid,
                debugger_address=self._debugger_address(driver),
                session_id=session_id,
                driver_create_time=(identity.created_at if identity else None),
                driver_executable=(identity.executable if identity else ""),
                driver_name=(identity.name if identity else ""),
            )
        except Exception as exc:
            tracker.request_cleanup()
            cleanup_error: BrowserRuntimeError | None = None
            if driver is not None:
                try:
                    driver_pid = self._driver_pid(driver)
                    identity = tracker.identity or self._capture_webdriver_identity(
                        driver_pid,
                        binaries.driver_path,
                    )
                    self.close(
                        BrowserDriverHandle(
                            driver=driver,
                            binaries=binaries,
                            driver_pid=driver_pid,
                            debugger_address=self._debugger_address(driver),
                            session_id=session_id,
                            driver_create_time=(identity.created_at if identity else None),
                            driver_executable=(identity.executable if identity else ""),
                            driver_name=(identity.name if identity else ""),
                        )
                    )
                except BrowserRuntimeError as cleanup_exc:
                    cleanup_error = cleanup_exc
                except Exception as cleanup_exc:
                    cleanup_error = BrowserRuntimeError(
                        "CLOSE_FAILED",
                        "浏览器启动残留进程清理失败",
                        operation="open_session",
                        retryable=True,
                        safe_details={
                            "error_type": type(cleanup_exc).__name__,
                            "surviving_processes": [],
                            "process_scan_complete": False,
                        },
                    )
            else:
                try:
                    self.cleanup_session(session_id)
                except BrowserRuntimeError as cleanup_exc:
                    cleanup_error = cleanup_exc
                except Exception as cleanup_exc:
                    cleanup_error = BrowserRuntimeError(
                        "CLOSE_FAILED",
                        "浏览器启动残留进程清理失败",
                        operation="open_session",
                        retryable=True,
                        safe_details={
                            "error_type": type(cleanup_exc).__name__,
                            "surviving_processes": [],
                            "process_scan_complete": False,
                        },
                    )
            if cleanup_error is not None:
                raise BrowserRuntimeError(
                    "LAUNCH_CLEANUP_FAILED",
                    "浏览器启动失败且残留进程未能确认退出",
                    operation="open_session",
                    retryable=True,
                    safe_details={
                        **cleanup_error.safe_details,
                        "launch_error_type": type(exc).__name__,
                        "mode": binaries.resolved_mode,
                        "profile_quarantine_required": True,
                    },
                ) from exc
            if isinstance(exc, BrowserRuntimeError):
                raise
            raise BrowserRuntimeError(
                "LAUNCH_FAILED",
                "浏览器会话启动失败",
                operation="open_session",
                retryable=True,
                safe_details={"error_type": type(exc).__name__, "mode": binaries.resolved_mode},
            ) from exc
        finally:
            tracker.mark_operation_done()

    def cleanup_session(self, session_id: str) -> None:
        """不依赖 WebDriver RPC，按会话标记回收浏览器及驱动进程。"""
        tracker = self._session_tracker(session_id)
        if tracker is not None:
            tracker.request_cleanup()
        self._cleanup_tagged_session(session_id, operation="close_session")
        if tracker is not None and not tracker.wait_clean(5.0):
            identity = tracker.identity
            raise BrowserRuntimeError(
                "CLOSE_FAILED",
                "WebDriver 后台回收尚未完成",
                operation="close_session",
                retryable=True,
                safe_details={
                    "error_type": "CleanupPending",
                    "surviving_processes": (
                        [self._identity_descriptor(identity)] if identity else []
                    ),
                    "process_scan_complete": False,
                },
            )

    def _cleanup_tagged_session(
        self,
        session_id: str,
        *,
        operation: str = "open_session",
    ) -> None:
        processes, initial_scan_complete = self._session_process_tree(session_id)
        alive = self._alive_processes(processes)
        for process in alive:
            try:
                process.terminate()
            except psutil.Error:
                pass
        _, alive = psutil.wait_procs(alive, timeout=3)
        for process in alive:
            try:
                process.kill()
            except psutil.Error:
                pass
        _, alive = psutil.wait_procs(alive, timeout=2)

        tagged_survivors, final_scan_complete = self._session_process_tree(session_id)
        alive = self._alive_processes(
            self._merge_processes(alive, tagged_survivors)
        )
        process_scan_complete = initial_scan_complete and final_scan_complete
        if alive or not process_scan_complete:
            raise BrowserRuntimeError(
                "CLOSE_FAILED",
                "浏览器启动残留进程清理失败",
                operation=operation,
                retryable=True,
                safe_details={
                    "error_type": "ProcessAlive" if alive else "ProcessScanIncomplete",
                    "surviving_processes": self._process_descriptors(alive),
                    "process_scan_complete": process_scan_complete,
                },
            )

    def status(self, handle: BrowserDriverHandle) -> dict[str, Any]:
        try:
            return {
                "alive": True,
                "url": str(handle.driver.current_url or ""),
                "title": str(handle.driver.title or ""),
                "driver_pid": handle.driver_pid,
                "window_handle": self.get_window_handle(handle),
            }
        except Exception as exc:
            return {
                "alive": False,
                "url": "",
                "title": "",
                "driver_pid": handle.driver_pid,
                "window_handle": None,
                "error_type": type(exc).__name__,
            }

    def navigate(self, handle: BrowserDriverHandle, url: str) -> dict[str, Any]:
        try:
            handle.driver.get(url)
            return self.status(handle)
        except Exception as exc:
            raise BrowserRuntimeError(
                "NAVIGATION_FAILED",
                "浏览器页面导航失败",
                operation="navigate",
                retryable=True,
                safe_details={"error_type": type(exc).__name__},
            ) from exc

    def capture(
        self,
        handle: BrowserDriverHandle,
        image_format: str,
        quality: int,
    ) -> bytes:
        params: dict[str, Any] = {"format": image_format, "fromSurface": True}
        if image_format in {"jpeg", "webp"}:
            params["quality"] = quality
        try:
            result = handle.driver.execute_cdp_cmd("Page.captureScreenshot", params)
            encoded = str((result or {}).get("data") or "")
            if not encoded:
                raise ValueError("missing screenshot data")
            return base64.b64decode(encoded)
        except Exception as exc:
            raise BrowserRuntimeError(
                "CAPTURE_FAILED",
                "浏览器截图失败",
                operation="capture",
                retryable=True,
                safe_details={"error_type": type(exc).__name__},
            ) from exc

    def execute_script(
        self,
        handle: BrowserDriverHandle,
        script: str,
        *args: Any,
    ) -> Any:
        try:
            return handle.driver.execute_script(script, *args)
        except Exception as exc:
            raise BrowserRuntimeError(
                "SCRIPT_FAILED",
                "浏览器脚本执行失败",
                operation="execute_script",
                safe_details={"error_type": type(exc).__name__},
            ) from exc

    def execute_cdp(
        self,
        handle: BrowserDriverHandle,
        command: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            result = handle.driver.execute_cdp_cmd(command, params)
            return result if isinstance(result, dict) else {"result": result}
        except Exception as exc:
            raise BrowserRuntimeError(
                "CDP_FAILED",
                "浏览器 CDP 命令执行失败",
                operation="execute_cdp",
                safe_details={"error_type": type(exc).__name__, "command": command},
            ) from exc

    def get_window_handle(self, handle: BrowserDriverHandle) -> int | None:
        if sys.platform != "win32" or handle.driver_pid is None:
            return None
        if not self._driver_identity_matches(
            handle.driver_pid,
            handle.driver_create_time,
            handle.driver_executable,
            handle.driver_name,
        ):
            return None

        process_ids = {handle.driver_pid}
        try:
            process = psutil.Process(handle.driver_pid)
            process_ids.update(child.pid for child in process.children(recursive=True))
        except psutil.Error:
            pass

        user32 = ctypes.windll.user32
        matches: list[int] = []
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )
        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int

        def callback(hwnd: int, _lparam: int) -> bool:
            process_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            if process_id.value in process_ids and user32.IsWindowVisible(hwnd):
                title_length = user32.GetWindowTextLengthW(hwnd)
                if title_length > 0:
                    matches.append(int(hwnd))
            return True

        user32.EnumWindows(callback_type(callback), 0)
        return matches[0] if matches else None

    def activate(self, handle: BrowserDriverHandle) -> bool:
        hwnd = self.get_window_handle(handle)
        if hwnd is None or sys.platform != "win32":
            return False
        try:
            user32 = ctypes.windll.user32
            user32.ShowWindow(hwnd, 9)
            return bool(user32.SetForegroundWindow(hwnd))
        except Exception:
            return False

    def close(self, handle: BrowserDriverHandle) -> None:
        tracker = self._session_tracker(handle.session_id)
        if tracker is not None:
            tracker.request_cleanup()
        driver_processes = self._driver_process_tree(
            handle.driver_pid,
            handle.driver_create_time,
            handle.driver_executable,
            handle.driver_name,
        )
        browser_processes, initial_scan_complete = self._session_process_tree(
            handle.session_id
        )
        processes = self._merge_processes(driver_processes, browser_processes)
        quit_error = self._quit_driver(handle.driver)

        post_quit_processes, post_quit_scan_complete = self._session_process_tree(
            handle.session_id
        )
        processes = self._merge_processes(processes, post_quit_processes)
        alive = self._alive_processes(processes)
        for process in alive:
            try:
                process.terminate()
            except psutil.Error:
                pass
        _, alive = psutil.wait_procs(alive, timeout=3)
        for process in alive:
            try:
                process.kill()
            except psutil.Error:
                pass
        _, alive = psutil.wait_procs(alive, timeout=2)

        tagged_survivors, final_scan_complete = self._session_process_tree(
            handle.session_id
        )
        alive = self._alive_processes(
            self._merge_processes(alive, tagged_survivors)
        )

        driver_known_gone = not self._driver_identity_matches(
            handle.driver_pid,
            handle.driver_create_time,
            handle.driver_executable,
            handle.driver_name,
        )
        process_scan_complete = (
            initial_scan_complete
            and post_quit_scan_complete
            and final_scan_complete
        )
        if alive or (
            quit_error is not None
            and not (driver_known_gone and process_scan_complete)
        ):
            raise BrowserRuntimeError(
                "CLOSE_FAILED",
                "浏览器会话关闭失败",
                operation="close_session",
                retryable=True,
                safe_details={
                    "error_type": type(quit_error).__name__ if quit_error else "ProcessAlive",
                    "surviving_processes": self._process_descriptors(alive),
                    "process_scan_complete": process_scan_complete,
                },
            ) from quit_error
        if tracker is not None and not tracker.wait_clean(5.0):
            raise BrowserRuntimeError(
                "CLOSE_FAILED",
                "WebDriver watchdog 尚未确认进程退出",
                operation="close_session",
                retryable=True,
                safe_details={
                    "error_type": "CleanupPending",
                    "surviving_processes": self._process_descriptors(alive),
                    "process_scan_complete": False,
                },
            )
        if tracker is not None and tracker.operation_done:
            tracker.stop()

    @staticmethod
    def _quit_driver(driver: Any) -> Exception | None:
        """有限等待 WebDriver quit，超时后由进程树清理继续收尾。"""
        completed = threading.Event()
        result: dict[str, Exception] = {}

        def run() -> None:
            try:
                driver.quit()
            except Exception as exc:
                result["error"] = exc
            finally:
                completed.set()

        worker = threading.Thread(
            target=run,
            name="browser-driver-quit",
            daemon=True,
        )
        worker.start()
        if not completed.wait(timeout=_DRIVER_QUIT_TIMEOUT_SECONDS):
            return TimeoutError("WebDriver quit 超时")
        return result.get("error")

    @staticmethod
    def _driver_pid(driver: Any) -> int | None:
        process = getattr(getattr(driver, "service", None), "process", None)
        pid = getattr(process, "pid", None)
        return int(pid) if isinstance(pid, int) else None

    @staticmethod
    def _debugger_address(driver: Any) -> str:
        capabilities = getattr(driver, "capabilities", {})
        if not isinstance(capabilities, dict):
            return ""
        for key in ("goog:chromeOptions", "ms:edgeOptions"):
            options = capabilities.get(key)
            if isinstance(options, dict):
                address = str(options.get("debuggerAddress") or "").strip()
                if address:
                    return address
        return ""

    @classmethod
    def _capture_webdriver_identity(
        cls,
        driver_pid: int | None,
        expected_driver_path: str,
    ) -> _ProcessIdentity | None:
        if driver_pid is None or driver_pid <= 0:
            return None
        try:
            process = psutil.Process(driver_pid)
            name = process.name().casefold()
            executable = str(process.exe() or "")
            created_at = float(process.create_time())
            if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
                return None
        except psutil.Error:
            return None

        expected_name = Path(expected_driver_path).name.casefold()
        actual_executable_name = Path(executable).name.casefold()
        if not expected_name or name != expected_name:
            return None
        if expected_name and actual_executable_name != expected_name:
            return None
        return _ProcessIdentity(
            pid=driver_pid,
            created_at=created_at,
            executable=executable,
            name=name,
        )

    @classmethod
    def _driver_identity_matches(
        cls,
        driver_pid: int | None,
        expected_created_at: float | None,
        expected_executable: str,
        expected_name: str,
    ) -> bool:
        if driver_pid is None or expected_created_at is None:
            return False
        try:
            process = psutil.Process(driver_pid)
            current_created_at = float(process.create_time())
            current_name = process.name().casefold()
            current_executable = str(process.exe() or "")
            if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
                return False
        except psutil.Error:
            return False

        if abs(current_created_at - float(expected_created_at)) >= 0.01:
            return False
        normalized_name = str(expected_name or "").casefold()
        if not normalized_name or current_name != normalized_name:
            return False
        normalized_executable = os.path.normcase(
            os.path.abspath(str(expected_executable or ""))
        )
        if not expected_executable:
            return False
        return os.path.normcase(os.path.abspath(current_executable)) == normalized_executable

    @classmethod
    def _driver_process_tree(
        cls,
        driver_pid: int | None,
        expected_created_at: float | None = None,
        expected_executable: str = "",
        expected_name: str = "",
    ) -> list[psutil.Process]:
        # PID 可被操作系统复用；不同时匹配创建时间、名称和 exe 时绝不按 PID 清理。
        if not cls._driver_identity_matches(
            driver_pid,
            expected_created_at,
            expected_executable,
            expected_name,
        ):
            return []
        try:
            assert driver_pid is not None
            root = psutil.Process(driver_pid)
            return [*root.children(recursive=True), root]
        except psutil.Error:
            return []

    @staticmethod
    def _session_process_tree(
        session_id: str,
    ) -> tuple[list[psutil.Process], bool]:
        if not session_id:
            return [], False

        tag = f"--auto-mas-browser-session={session_id}"
        matches: list[psutil.Process] = []
        scan_complete = True
        try:
            iterator = psutil.process_iter(["pid", "cmdline"])
        except psutil.Error:
            return [], False

        for process in iterator:
            try:
                command_line = process.info.get("cmdline") or []
                if tag not in command_line:
                    continue
                matches.append(process)
                matches.extend(process.children(recursive=True))
                try:
                    parent = process.parent()
                    if parent is not None and SeleniumBrowserBackend._is_webdriver_process(parent):
                        matches.append(parent)
                except psutil.Error:
                    scan_complete = False
            except psutil.NoSuchProcess:
                continue
            except psutil.Error:
                scan_complete = False
        return SeleniumBrowserBackend._merge_processes(matches), scan_complete

    @staticmethod
    def _is_webdriver_process(process: psutil.Process) -> bool:
        try:
            name = process.name().casefold()
        except psutil.Error:
            return False
        return SeleniumBrowserBackend._is_webdriver_name(name)

    @staticmethod
    def _is_webdriver_name(name: str) -> bool:
        return str(name or "").casefold() in {
            "chromedriver",
            "chromedriver.exe",
            "msedgedriver",
            "msedgedriver.exe",
        }

    @staticmethod
    def _identity_descriptor(identity: _ProcessIdentity) -> dict[str, Any]:
        return {
            "pid": identity.pid,
            "created_at": identity.created_at,
            "executable": identity.executable,
            "name": identity.name,
        }

    @staticmethod
    def _terminate_processes(processes: list[psutil.Process]) -> list[psutil.Process]:
        alive = SeleniumBrowserBackend._alive_processes(processes)
        for process in alive:
            try:
                process.terminate()
            except psutil.Error:
                pass
        _, alive = psutil.wait_procs(alive, timeout=3)
        for process in alive:
            try:
                process.kill()
            except psutil.Error:
                pass
        _, alive = psutil.wait_procs(alive, timeout=2)
        return SeleniumBrowserBackend._alive_processes(alive)

    @staticmethod
    def _merge_processes(
        *groups: list[psutil.Process],
    ) -> list[psutil.Process]:
        result: list[psutil.Process] = []
        seen: set[tuple[int, float | None]] = set()
        for group in groups:
            for process in group:
                try:
                    key = (process.pid, process.create_time())
                except psutil.Error:
                    key = (process.pid, None)
                if key in seen:
                    continue
                seen.add(key)
                result.append(process)
        return result

    @staticmethod
    def _process_descriptors(
        processes: list[psutil.Process],
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for process in processes:
            try:
                created_at: float | None = process.create_time()
            except psutil.Error:
                created_at = None
            try:
                executable = str(process.exe() or "")
            except psutil.Error:
                executable = ""
            try:
                name = process.name().casefold()
            except psutil.Error:
                name = ""
            result.append(
                {
                    "pid": process.pid,
                    "created_at": created_at,
                    "executable": executable,
                    "name": name,
                }
            )
        return result

    @staticmethod
    def _alive_processes(processes: list[psutil.Process]) -> list[psutil.Process]:
        result: list[psutil.Process] = []
        for process in processes:
            try:
                if process.is_running() and process.status() != psutil.STATUS_ZOMBIE:
                    result.append(process)
            except psutil.Error:
                continue
        return result

    def _resolve_mode(self, requested_mode: str, configured_path: str) -> tuple[str, str]:
        if requested_mode != "auto":
            return requested_mode, configured_path.strip()
        if configured_path.strip():
            return self._engine_from_path(configured_path), configured_path.strip()

        detected = self._find_system_browser()
        if detected is None:
            return "managed", ""
        return detected

    @staticmethod
    def _engine_from_path(browser_path: str) -> str:
        name = Path(browser_path).name.lower()
        return "edge" if "edge" in name else "chrome"

    @staticmethod
    def _find_system_browser() -> tuple[str, str] | None:
        executable = shutil.which("msedge") or shutil.which("msedge.exe")
        if executable:
            return "edge", executable
        executable = (
            shutil.which("chrome")
            or shutil.which("chrome.exe")
            or shutil.which("google-chrome")
            or shutil.which("google-chrome-stable")
        )
        if executable:
            return "chrome", executable

        if sys.platform != "win32":
            return None
        roots = [
            os.environ.get("PROGRAMFILES(X86)", ""),
            os.environ.get("PROGRAMFILES", ""),
            os.environ.get("LOCALAPPDATA", ""),
        ]
        candidates = [
            ("edge", Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
            for root in roots
            if root
        ]
        candidates.extend(
            ("chrome", Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe")
            for root in roots
            if root
        )
        for mode, path in candidates:
            if path.is_file():
                return mode, str(path)
        return None
