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
        worker_module="app.task.desktop_session_worker",
    )
    if code == _MAINTENANCE_RETURN_CODE:
        raise GameMaintenanceDetected(stdout.decode("utf-8"))
    return code == 0


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
    module, name = actions[request["action"]]
    arguments = request["arguments"]
    if "launcher_path" in arguments:
        arguments["launcher_path"] = Path(arguments["launcher_path"])

    set_dpi_awareness()
    session_id = process_session(os.getpid())
    configure_parent_scope(lambda: session_id)
    os.chdir(request["root"])
    send(pipe, {"pid": os.getpid()})

    def on_log(line: str) -> None:
        send(pipe, {"log": line})

    operation = getattr(import_module(f"app.task.{module}"), name)
    try:
        success = operation(**arguments, on_log=on_log)
    except GameMaintenanceDetected as error:
        send(
            pipe,
            {"stdout": base64.b64encode(error.text.encode("utf-8")).decode("ascii")},
        )
        send(pipe, {"returnCode": _MAINTENANCE_RETURN_CODE})
    else:
        send(pipe, {"returnCode": int(not success)})


if __name__ == "__main__":
    main(run_action)
