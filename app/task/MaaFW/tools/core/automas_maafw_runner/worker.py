#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

import psutil

# 并入自 mfwa：宿主进程存活探测间隔
_OWNER_CHECK_INTERVAL_SECONDS = 1.0

for stream in (sys.stdout, sys.stderr):
    with suppress(Exception):
        stream.reconfigure(encoding="utf-8", errors="replace")

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from environment import prefer_active_venv_site_packages  # type: ignore[no-redef]

    # 桌面插件目录也可能安装 MaaFW。先把项目 Runner venv 放到 sys.path 最前，
    # 避免共享插件依赖覆盖项目 requirements 声明的 MaaFW 版本。
    prefer_active_venv_site_packages()
    from run_plan import MaaFWRunPlan  # type: ignore[no-redef]
    from runner import (  # type: ignore[no-redef]
        MaaFWDeviceConfig,
        MaaFWRunner,
        MaaFWRunResult,
    )
else:
    from .environment import prefer_active_venv_site_packages

    prefer_active_venv_site_packages()
    from .run_plan import MaaFWRunPlan
    from .runner import MaaFWDeviceConfig, MaaFWRunner, MaaFWRunResult


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _emit_log(message: str) -> None:
    _emit({"type": "log", "message": message})


# --- 以下四个函数并入自 mfwa（tools/worker.py）--------------------------------
# 宿主看门狗：宿主进程消失后，worker 必须自行清理并退出，否则会留下孤儿进程
# 持有设备句柄与 Agent 子进程。createTime 与 pid 配对判定，防 pid 复用误杀。


def _owner_is_alive(owner_pid: int, owner_create_time: float) -> bool:
    try:
        process = psutil.Process(owner_pid)
        return (
            process.is_running()
            and abs(process.create_time() - owner_create_time) < 0.01
        )
    except (psutil.AccessDenied, psutil.NoSuchProcess, ValueError):
        return False


def _cleanup_job_files(job_path: Path) -> None:
    with suppress(OSError):
        job_path.unlink()
    option_dir = str(os.environ.get("AUTO_MAS_MAAFW_OPTION_DIR") or "").strip()
    if option_dir:
        with suppress(OSError):
            shutil.rmtree(option_dir)


def _terminate_descendants() -> None:
    with suppress(psutil.Error):
        descendants = psutil.Process(os.getpid()).children(recursive=True)
        for process in descendants:
            with suppress(psutil.Error):
                process.terminate()
        _gone, alive = psutil.wait_procs(descendants, timeout=3)
        for process in alive:
            with suppress(psutil.Error):
                process.kill()
        psutil.wait_procs(alive, timeout=2)


def _watch_owner(job_path: Path, owner_pid: int, owner_create_time: float) -> None:
    while _owner_is_alive(owner_pid, owner_create_time):
        time.sleep(_OWNER_CHECK_INTERVAL_SECONDS)
    _cleanup_job_files(job_path)
    _terminate_descendants()
    os._exit(75)


# -----------------------------------------------------------------------------


def _start_owner_watchdog(job_path: Path, payload: dict[str, Any]) -> None:
    owner_pid = int(payload.get("ownerPid") or 0)
    owner_create_time = float(payload.get("ownerCreateTime") or 0)
    if owner_pid <= 0 or owner_create_time <= 0:
        return
    threading.Thread(
        target=_watch_owner,
        args=(job_path, owner_pid, owner_create_time),
        name="maafw-owner-watchdog",
        daemon=True,
    ).start()


def main() -> int:
    if len(sys.argv) != 2:
        _emit({"type": "error", "message": "runner worker requires one job json path"})
        return 64

    job_path = Path(sys.argv[1])
    runner: MaaFWRunner | None = None
    try:
        payload = json.loads(job_path.read_text(encoding="utf-8"))
        _start_owner_watchdog(job_path, payload)
        plan = MaaFWRunPlan.model_validate(payload["plan"])
        device_config = MaaFWDeviceConfig.model_validate(payload["deviceConfig"])
        runner = MaaFWRunner(plan, send_log=_emit_log)
        result = runner.run(device_config)
        _emit({"type": "result", "data": result.model_dump(mode="json")})
        return 0 if result.success else 2
    except BaseException as exc:  # noqa: BLE001 - keep worker boundary explicit.
        result = MaaFWRunResult(
            success=False,
            projectName="",
            controllerName="",
            resourceName="",
            errorMessage=str(exc),
        )
        with suppress(Exception):
            _emit({"type": "result", "data": result.model_dump(mode="json")})
        _emit({"type": "error", "message": str(exc)})
        return 1
    finally:
        if runner is not None:
            with suppress(Exception):
                runner.shutdown()
        # 并入自 mfwa：正常收尾也清掉 job 文件与临时 option 目录
        _cleanup_job_files(job_path)


if __name__ == "__main__":
    raise SystemExit(main())
