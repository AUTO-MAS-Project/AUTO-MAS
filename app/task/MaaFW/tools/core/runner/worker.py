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

from app.task.MaaFW.tools.core.worker_protocol import (
    AUDIENCE_WORKER_LOG,
    LEVEL_INFO,
    LEVEL_WARNING,
    EventChannelClient,
    decode_job,
    error_event,
    log_event,
)

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


_EMIT_LOCK = threading.Lock()
# 宿主的事件通道（worker_protocol）。None 表示走 stdout：宿主没给端口、连不上，或连上后发送出错。
_CHANNEL: EventChannelClient | None = None


def _emit(payload: dict[str, Any]) -> None:
    """发一个事件给宿主：有事件通道走通道，否则一行一个 JSON 写 stdout（旧格式，宿主照样认）。"""

    global _CHANNEL
    with _EMIT_LOCK:
        channel = _CHANNEL
        if channel is not None:
            try:
                channel.send(payload)
                return
            except OSError as exc:
                # 宿主关了连接（读到坏数据、或正在收尾）：后面的事件全走 stdout，这一条也补发过去
                _CHANNEL = None
                with suppress(OSError):
                    channel.close()
                _write_stdout_event(
                    log_event(
                        f"MaaFW worker 事件通道发送失败（{exc!r}），之后的事件改走标准输出",
                        audience=AUDIENCE_WORKER_LOG,
                        level=LEVEL_WARNING,
                    )
                )
        _write_stdout_event(payload)


def _write_stdout_event(payload: dict[str, Any]) -> None:
    # 一行一次 write 并在锁内调用：focus 文案和失败摘要来自框架回调线程，和主线程的
    # 日志并发写 stdout；print 是内容、换行两次 write，会把两条 JSON 粘成一行，
    # 宿主 json.loads 失败就整行当框架噪声丢掉。
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    sys.stdout.write(line)
    sys.stdout.flush()


def _emit_log(
    message: str, *, audience: str | None = None, level: str = LEVEL_INFO
) -> None:
    # 去向（进界面 / 只进 .worker.log）在这里定好，宿主照 audience 办；不指定时按
    # worker_protocol.forwards_to_ui 的规则判（runner 的 send_log 只传文案）
    _emit(log_event(message, audience=audience, level=level))


def _open_event_channel(spec: Any) -> None:
    """按 job 里的参数连回宿主；连不上就留在 stdout，原因记进 .worker.log。"""

    global _CHANNEL
    if not isinstance(spec, dict):
        return
    try:
        channel = EventChannelClient.connect(spec)
    except (OSError, ValueError) as exc:
        _emit(
            log_event(
                f"MaaFW worker 连不上宿主的事件通道（{exc!r}），本次运行事件改走标准输出",
                audience=AUDIENCE_WORKER_LOG,
                level=LEVEL_WARNING,
            )
        )
        return
    with _EMIT_LOCK:
        _CHANNEL = channel


def _close_event_channel() -> None:
    global _CHANNEL
    with _EMIT_LOCK:
        channel, _CHANNEL = _CHANNEL, None
    if channel is not None:
        with suppress(OSError):
            channel.close()


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


def _cleanup_job_files(job_path: Path | None) -> None:
    # job 走 stdin 时没有文件；只有旧宿主传进来的 job 文件路径要删
    if job_path is not None:
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


def _watch_owner(
    job_path: Path | None, owner_pid: int, owner_create_time: float
) -> None:
    while _owner_is_alive(owner_pid, owner_create_time):
        time.sleep(_OWNER_CHECK_INTERVAL_SECONDS)
    _cleanup_job_files(job_path)
    _terminate_descendants()
    os._exit(75)


# -----------------------------------------------------------------------------


def _start_owner_watchdog(job_path: Path | None, payload: dict[str, Any]) -> None:
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


def _read_job() -> tuple[dict[str, Any], Path | None]:
    """读 job：宿主写在 stdin 里（不落盘：计划里可能有解密后的密码选项）。

    带一个参数时按旧宿主的 job 文件读：升级时旧的宿主进程还在跑、源码已换成新的，它拉起的
    是新 worker。那份文件读完就删，看门狗与 finally 里的删除照旧兜底。
    """

    if len(sys.argv) == 2:
        job_path = Path(sys.argv[1])
        try:
            return decode_job(job_path.read_bytes()), job_path
        finally:
            with suppress(OSError):
                job_path.unlink()
    return decode_job(sys.stdin.buffer.read()), None


def main() -> int:
    if len(sys.argv) > 2:
        _emit(
            error_event(
                "runner worker reads its job from stdin (or one legacy job json path)"
            )
        )
        return 64

    job_path: Path | None = Path(sys.argv[1]) if len(sys.argv) == 2 else None
    runner: MaaFWRunner | None = None
    try:
        payload, job_path = _read_job()
        _start_owner_watchdog(job_path, payload)
        _open_event_channel(payload.get("eventChannel"))
        plan = MaaFWRunPlan.model_validate(payload["plan"])
        device_config = MaaFWDeviceConfig.model_validate(payload["deviceConfig"])
        screenshot_dir = payload.get("failureScreenshotDir")
        not_before = payload.get("taskStartNotBefore")
        deadline_at = payload.get("runDeadlineAt")
        task_limit_seconds = payload.get("taskTimeLimitSeconds")
        task_limit_overrides = payload.get("taskTimeLimitOverrides")
        runner = MaaFWRunner(
            plan,
            send_log=_emit_log,
            failure_screenshot_dir=Path(screenshot_dir) if screenshot_dir else None,
            failure_screenshot_prefix=str(payload.get("failureScreenshotPrefix") or ""),
            task_start_not_before=float(not_before) if not_before is not None else None,
            task_start_gate_mode=str(payload.get("taskStartGateMode") or "screen"),
            run_deadline_at=float(deadline_at) if deadline_at is not None else None,
            task_time_limit_seconds=(
                int(task_limit_seconds) if task_limit_seconds is not None else 0
            ),
            task_time_limit_overrides=(
                {str(name): int(value) for name, value in task_limit_overrides.items()}
                if isinstance(task_limit_overrides, dict)
                else None
            ),
            loop_guard_enabled=payload.get("loopGuard") is True,
        )
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
            failureScreenshots=(
                runner.failure_screenshots if runner is not None else []
            ),
        )
        with suppress(Exception):
            _emit({"type": "result", "data": result.model_dump(mode="json")})
        _emit(error_event(str(exc)))
        return 1
    finally:
        if runner is not None:
            with suppress(Exception):
                runner.shutdown()
        # shutdown 里还会发日志（agent 退出等），发完再关通道：宿主随即读到 EOF
        _close_event_channel()
        # 并入自 mfwa：正常收尾也清掉 job 文件与临时 option 目录
        _cleanup_job_files(job_path)


if __name__ == "__main__":
    raise SystemExit(main())
