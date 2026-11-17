"""在桌面分身执行需要操作窗口的专项动作。"""

import base64
import os
from collections.abc import Callable
from importlib import import_module
from pathlib import Path

from app.task.Okww.tools.maintenance import GameMaintenanceDetected
from app.utils.common.process.session import DesktopProcessTarget
from app.utils.windows.desktop_session.launcher import receive, send
from app.utils.windows.desktop_session.native import process_session
from app.utils.windows.desktop_session.process_runner import (
    run_desktop_action as run_action_in_session,
)
from app.utils.windows.desktop_session.process_worker import main

_MAINTENANCE_RETURN_CODE = 2
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
    if code == _MAINTENANCE_RETURN_CODE:
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


def run_action(pipe) -> None:
    request = receive(pipe)
    from app.utils.common.process.session import configure_parent_scope
    from app.utils.windows.desktop_session.native import set_dpi_awareness

    actions = {
        "bettergi_switch_account": (
            "BetterGI.tools.account_switch_native",
            "account_switch",
        ),
        "okww_switch_account": ("Okww.tools.account_switch", "account_switch"),
        "oknte_switch_account": ("OkNte.tools.account_switch", "account_switch"),
        "okww_start_game": ("Okww.tools.launcher_start", "start_game_via_launcher"),
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
    if action == "okww_has_launcher_window":
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
    else:
        module, name = actions[action]
        operation = getattr(import_module(f"app.task.{module}"), name)
        try:
            code = int(not operation(**arguments, on_log=on_log))
        except GameMaintenanceDetected as error:
            text = error.text
            code = _MAINTENANCE_RETURN_CODE
    if text is not None:
        send(
            pipe,
            {"stdout": base64.b64encode(text.encode("utf-8")).decode("ascii")},
        )
    send(pipe, {"returnCode": code})


if __name__ == "__main__":
    main(run_action)
