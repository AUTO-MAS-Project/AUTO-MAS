"""在桌面分身执行需要操作窗口的专项动作。"""

import asyncio
import base64
import json
import os
from collections.abc import Awaitable, Callable
from importlib import import_module
from pathlib import Path
from typing import Any

from app.task.Okww.tools.maintenance import GameMaintenanceDetected
from app.utils.common.process.session import DesktopProcessTarget
from app.utils.windows.desktop_session.launcher import receive, send
from app.utils.windows.desktop_session.native import process_session
from app.utils.windows.desktop_session.process_runner import (
    run_desktop_action as run_action_in_session,
)
from app.utils.windows.desktop_session.process_worker import main

MAINTENANCE_RETURN_CODE = 2
_WORKER_MODULE = "app.task.desktop_session_worker"


async def run_desktop_action(
    desktop: DesktopProcessTarget,
    action: str,
    arguments: dict[str, str | bool | float | None],
    on_log: Callable[[str], None] | None = None,
) -> bool:
    code, stdout, _ = await run_action_in_session(
        desktop,
        action,
        arguments,
        on_log,
        worker_module=_WORKER_MODULE,
    )
    if code == MAINTENANCE_RETURN_CODE:
        raise GameMaintenanceDetected(stdout.decode("utf-8"))
    return code == 0


async def detect_desktop_maintenance(
    desktop: DesktopProcessTarget,
    action: str,
    arguments: dict[str, str | None],
) -> str | None:
    code, stdout, _ = await run_action_in_session(
        desktop, action, dict(arguments), worker_module=_WORKER_MODULE
    )
    if code != 0:
        raise RuntimeError(f"分身游戏画面检测失败 ({code})")
    return stdout.decode("utf-8") if stdout else None


async def request_desktop_action(
    desktop: DesktopProcessTarget,
    action: str,
    arguments: dict[str, str | bool | None],
    *,
    on_log: Callable[[str], None] | None = None,
    on_restart: Callable[[], Awaitable[None]] | None = None,
) -> tuple[int, Any]:
    code, stdout, _ = await run_action_in_session(
        desktop,
        action,
        arguments,
        on_log,
        worker_module=_WORKER_MODULE,
        on_restart=on_restart,
    )
    return code, json.loads(stdout) if stdout else None


def _maafw_window_matches(controller: dict[str, Any]) -> list[Any]:
    """按 interface 的窗口规则匹配分身桌面上的窗口。

    匹配规则在 MFW 解析库 ``maafw_interface`` 里，宿主不带它：分身进程的导入路径里没有插件环境时，
    从工作目录下的插件环境补上；仍找不到就报错，由发起方按查窗口失败处理。
    """
    import sys

    from maa.toolkit import Toolkit

    try:
        from maafw_interface.controller_win32 import service
    except ImportError:
        site = str(Path.cwd() / "plugins" / "pypi" / "site-packages")
        if site not in sys.path:
            sys.path.append(site)
        try:
            from maafw_interface.controller_win32 import service
        except ImportError as exc:
            raise RuntimeError(
                "桌面分身里查窗口要用 MFW 解析库 maafw_interface，没有找到："
                "请在插件中心安装 MFW 插件"
            ) from exc

    def list_windows() -> list[Any]:
        return [
            service.MaaFWWin32Window(
                hWnd=int(getattr(window.hwnd, "value", window.hwnd) or 0),
                className=str(window.class_name or ""),
                windowName=str(window.window_name or ""),
            )
            for window in Toolkit.find_desktop_windows()
        ]

    return service.MaaFWWin32ControllerService().match_controller_windows(
        controller, list_windows=list_windows
    )


def run_action(pipe) -> None:
    request = receive(pipe)
    from app.utils.common.process.session import configure_parent_scope
    from app.utils.windows.desktop_session.native import set_dpi_awareness

    actions = {
        "okww_switch_account": ("Okww.tools.account_switch", "account_switch"),
        "oknte_switch_account": ("OkNte.tools.account_switch", "account_switch"),
        "oknte_start_game": ("OkNte.tools.launcher_start", "start_game_via_launcher"),
        "oknte_wait_autoplay": ("OkNte.tools.launcher_start", "wait_autoplay_game"),
    }
    action = request["action"]
    arguments = request["arguments"]
    for field in ("launcher_path", "client_path"):
        if arguments.get(field) is not None:
            arguments[field] = Path(arguments[field])

    set_dpi_awareness()
    session_id = process_session(os.getpid())
    configure_parent_scope(lambda: session_id)
    os.chdir(request["root"])
    send(pipe, {"pid": os.getpid()})

    def on_log(line: str) -> None:
        send(pipe, {"log": line})

    text = None
    if action == "maaend_game_window":
        import win32gui

        text = json.dumps(bool(win32gui.FindWindow("UnityWndClass", "Endfield")))
        code = 0
    elif action == "maaend_failure_screenshot":
        from app.services.common.maa_capture import capture_win32
        from app.task.failure_capture_core import FailureCapture
        from app.task.MaaEnd.AutoProxy import AutoProxyTask

        hwnd = AutoProxyTask.find_failure_window(Path(arguments["game_path"]))
        screenshot = None
        if hwnd is not None:
            image = asyncio.run(capture_win32(hwnd))
            screenshot = FailureCapture(stopped=lambda: False).save(
                image, dir_name="maaend-failure"
            )
        text = json.dumps(str(screenshot) if screenshot else None)
        code = 0
    elif action == "maaend_direct_launch":
        from app.task.MaaEnd.tools.game_launcher import launch_game

        launch_game(
            arguments["launcher_path"],
            Path(arguments["game_path"]),
            arguments["game_arguments"],
        )
        code = 0
    elif action == "okww_start_game":
        from app.task.Okww.tools.launcher_start import start_game_via_launcher

        try:
            pid = start_game_via_launcher(**arguments, on_log=on_log)
        except GameMaintenanceDetected as error:
            code = MAINTENANCE_RETURN_CODE
            text = json.dumps(str(error))
        else:
            code = 0
            text = json.dumps(pid)
    elif action == "maaend_launch":
        from app.task.MaaEnd.tools.launcher_start import start_game_via_launcher

        screenshots = []
        code = int(
            not start_game_via_launcher(
                arguments["launcher_path"],
                client_path=arguments.get("client_path"),
                on_log=on_log,
                on_error_screenshot=lambda path: screenshots.append(str(path)),
            )
        )
        text = json.dumps(screenshots)
    elif action == "maaend_login":
        from app.task.MaaEnd.tools.login import LoginNotReadyError, login

        async def restart() -> None:
            send(pipe, {"restart": True})
            if not receive(pipe).get("restart"):
                raise asyncio.CancelledError

        screenshots = []
        not_ready = None
        error = None
        try:
            asyncio.run(
                login(
                    arguments["account"],
                    restart_game=restart,
                    on_error_screenshot=lambda path: screenshots.append(str(path)),
                )
            )
        except LoginNotReadyError as exc:
            not_ready = str(exc)
        except Exception as exc:
            error = type(exc).__name__
        text = json.dumps(
            {"screenshots": screenshots, "notReady": not_ready, "error": error}
        )
        code = int(error is not None)
    elif action == "list_windows":
        # 通用动作：列出分身桌面上的全部窗口，按 MaaFramework 的枚举顺序；匹配规则由调用方在本进程做。
        import win32gui
        import win32process
        from maa.toolkit import Toolkit

        rows = []
        for window in Toolkit.find_desktop_windows():
            hwnd = getattr(window.hwnd, "value", window.hwnd)
            hwnd = int(hwnd) if hwnd is not None else 0
            if not win32gui.IsWindow(hwnd):
                continue
            rows.append(
                [
                    hwnd,
                    str(window.class_name or ""),
                    str(window.window_name or ""),
                    win32process.GetWindowThreadProcessId(hwnd)[1],
                ]
            )
        text = json.dumps(rows)
        code = 0
    elif action == "window_in_session":
        import win32gui
        import win32process

        hwnd = int(arguments["hwnd"])
        pid = (
            win32process.GetWindowThreadProcessId(hwnd)[1]
            if win32gui.IsWindow(hwnd)
            else 0
        )
        text = json.dumps(bool(pid and process_session(pid) == session_id))
        code = 0
    elif action == "maafw_windows":
        # 兼容 MFW 插件 0.1.0 的运行积木：它在分身里查窗口仍发这个动作（新代码用 list_windows）。
        import win32gui
        import win32process

        hwnd = arguments.get("hwnd")
        if hwnd is not None:
            hwnd = int(hwnd)
            pid = (
                win32process.GetWindowThreadProcessId(hwnd)[1]
                if win32gui.IsWindow(hwnd)
                else 0
            )
            text = json.dumps(bool(pid and process_session(pid) == session_id))
        else:
            text = json.dumps(
                [
                    [
                        item.hWnd,
                        item.className,
                        item.windowName,
                        win32process.GetWindowThreadProcessId(item.hWnd)[1],
                    ]
                    for item in _maafw_window_matches(
                        json.loads(arguments["controller"])
                    )
                    if win32gui.IsWindow(item.hWnd)
                ]
            )
        code = 0
    elif action == "okww_has_launcher_window":
        from app.task.Okww.tools.launcher_start import has_launcher_window

        code = int(not has_launcher_window(arguments["launcher_path"]))
    elif action == "okww_detect_maintenance":
        from app.task.Okww.tools.launcher_start import (
            detect_game_maintenance_text,
            find_client_pids,
        )

        text = detect_game_maintenance_text(
            find_client_pids(arguments["client_path"], arguments["launcher_path"])
        )
        code = 0
    elif action == "oknte_detect_maintenance":
        from app.task.OkNte.tools.launcher_start import detect_game_maintenance_text

        text = detect_game_maintenance_text()
        code = 0
    elif action == "bettergi_switch_account":
        import sys

        search_path = arguments.pop("plugin_path")
        sdk = Path(__file__).resolve().parents[2] / "plugins" / "auto_mas_core" / "src"
        sys.path[:0] = [str(sdk), search_path]
        from bettergi_adapter.tools.account_switch_native import account_switch

        code = int(not account_switch(**arguments, on_log=on_log))
    else:
        module, name = actions[action]
        operation = getattr(import_module(f"app.task.{module}"), name)
        try:
            code = int(not operation(**arguments, on_log=on_log))
        except GameMaintenanceDetected as error:
            text = error.text
            code = MAINTENANCE_RETURN_CODE
    if text is not None:
        send(
            pipe,
            {"stdout": base64.b64encode(text.encode("utf-8")).decode("ascii")},
        )
    send(pipe, {"returnCode": code})


if __name__ == "__main__":
    main(run_action)
