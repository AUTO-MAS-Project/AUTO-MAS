#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


"""「登录云游戏」：为一个 MAS 用户起云浏览器，用三月七的 ``game`` 任务登录。

三月七的 ``game`` 任务只调 ``game.start()``：云模式下就是「连浏览器 → 等用户
在窗口里登录 → 进云游戏 → 退出」，是现成的登录探针，MAS 不自己判断页面状态。
与正在运行的任务互斥（外部路径锁），三月七 config.yaml 用完即还原。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.utils import get_logger

from .account_switch import (
    HSRAccountSwitcher,
    build_platform_m7a_env,
    build_platform_m7a_patch,
    check_cloud_prerequisites,
    close_cloud_browser,
    cloud_login_timeout_minutes,
    cloud_max_queue_minutes,
    is_cloud_platform,
    merge_cloud_last_login,
)
from .external_locks import (
    HSRExternalPathBusyError,
    acquire_external_path_locks,
    resolve_external_lock_paths,
)
from .log_detect import is_cloud_login_success, is_m7a_self_browser_start
from .m7a_control import HSRM7AControl
from .m7a_runtime import M7ARunner
from .run_model import HSRRuntimeState, external_result_failure_summary

logger = get_logger("HSR 云登录")

M7A_LOGIN_TASK = "game"
# 登录等待与排队之外给三月七留的余量（启动、弹窗处理）。
LOGIN_TASK_MARGIN_MINUTES = 15
# 三月七只有在登录态检查通过后才会去读剩余时长，这行也能证明已登录
# （cloud.py:1151），用于「已登录但时长为 0 / 排队超时」这种进不了游戏的情况。
_LOGGED_IN_EVIDENCE = "正在检测云游戏剩余时长"


class HSRCloudLoginBusyError(RuntimeError):
    """脚本正在运行，或三月七目录被其他任务占用。"""


@dataclass(frozen=True, slots=True)
class CloudLoginOutcome:
    logged_in: bool
    last_login: str | None
    message: str


async def run_cloud_login(
    script_config: Any,
    *,
    script_id: str,
    user_id: str,
    user_name: str,
    log: Callable[[str], None] | None = None,
) -> CloudLoginOutcome:
    """为指定用户登录云·星穹铁道，成功后写 ``Cloud.LastLogin``。

    Raises:
        ValueError: 脚本不是云平台，或云前置不满足。
        HSRCloudLoginBusyError: 脚本正在运行或三月七目录被占用。
    """

    append_log = log or (lambda message: logger.info(message))
    if not is_cloud_platform(script_config):
        raise ValueError("该脚本的游戏平台不是云·星穹铁道")
    if getattr(script_config, "is_locked", False):
        raise HSRCloudLoginBusyError("该 HSR 脚本正在运行，请结束任务后再登录云游戏")
    error = check_cloud_prerequisites(script_config)
    if error:
        raise ValueError(error)

    try:
        lease = await acquire_external_path_locks(
            resolve_external_lock_paths(script_config, ("M7A",)), wait=False
        )
    except HSRExternalPathBusyError as e:
        raise HSRCloudLoginBusyError(
            "三月七正被其他 HSR 任务使用，请结束任务后再登录云游戏"
        ) from e

    m7a_root = Path(str(script_config.get("Info", "M7APath") or "").strip())
    config_path = m7a_root / "config.yaml"
    runtime = HSRRuntimeState(log_lines=[], completion_writebacks=[])
    switcher = HSRAccountSwitcher(
        script_config=script_config,
        runtime=runtime,
        append_log=append_log,
        script_id=script_id,
        user_id=user_id,
    )
    logged_in = False
    self_browser = False
    background: set[asyncio.Task] = set()
    result: object | None = None
    original: bytes | None = None
    try:
        if not config_path.is_file():
            raise ValueError(
                f"三月七原生配置不存在：{config_path}，请先在三月七中保存一次设置"
            )
        browser = await switcher.ensure_cloud_browser()
        original = config_path.read_bytes()
        # 与托管运行同一套：关通知、after_finish=None、平台字段带本轮端口。
        HSRM7AControl.write_m7a_patch(
            config_path,
            {},
            whitelist=frozenset(),
            platform_patch=build_platform_m7a_patch(
                script_config, debug_port=browser.port
            ),
        )

        runner: M7ARunner | None = None

        def watch(line: str) -> None:
            nonlocal logged_in, self_browser
            if is_m7a_self_browser_start(line):
                # 窗口被关掉后三月七重试时会自建浏览器，登录态不会进该用户的
                # profile：立刻终止，这次不算登录成功。
                if not self_browser and runner is not None:
                    self_browser = True
                    task = asyncio.create_task(runner.terminate_current_process())
                    background.add(task)
                    task.add_done_callback(background.discard)
                return
            if is_cloud_login_success(line) or _LOGGED_IN_EVIDENCE in line:
                logged_in = True

        runner = M7ARunner(
            m7a_root,
            log_callback=append_log,
            output_line_callback=watch,
            env_overrides=build_platform_m7a_env(script_config),
        )
        append_log(f"用户「{user_name}」：请在弹出的云·星穹铁道窗口里登录米哈游通行证")
        timeout_minutes = (
            cloud_login_timeout_minutes(script_config)
            + cloud_max_queue_minutes(script_config)
            + LOGIN_TASK_MARGIN_MINUTES
        )
        result = await runner.run_task(M7A_LOGIN_TASK, timeout=timeout_minutes * 60)
        logged_in = not self_browser and (
            logged_in or bool(getattr(result, "success", False))
        )
    finally:
        if original is not None:
            try:
                config_path.write_bytes(original)
            except OSError as e:
                logger.warning(f"还原三月七 config.yaml 失败：{e}")
                append_log(f"还原三月七 config.yaml 失败：{e}")
        # 正常关闭让 cookie 落盘；下次运行直接免登录。
        await close_cloud_browser(
            runtime, append_log, script_id=script_id, include_m7a_started=True
        )
        lease.release()

    if self_browser:
        return CloudLoginOutcome(
            logged_in=False,
            last_login=None,
            message="云游戏窗口被关闭后三月七试图自己新建浏览器，已终止；"
            "请重新点「登录云游戏」，登录完成前不要关闭弹出的窗口",
        )
    if not logged_in:
        detail = external_result_failure_summary(result) if result is not None else ""
        return CloudLoginOutcome(
            logged_in=False,
            last_login=None,
            message=f"未确认登录成功：{detail}" if detail else "未确认登录成功，请重试",
        )
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        await merge_cloud_last_login(script_config, {user_id: stamp})
    except ValueError as e:
        # 登录期间有任务开跑把配置锁了：登录态已在 profile 里，只是没记上时间。
        logger.warning(f"记录云登录时间失败：{e}")
        return CloudLoginOutcome(
            logged_in=True, last_login=stamp, message=f"已登录（未能记录登录时间：{e}）"
        )
    return CloudLoginOutcome(logged_in=True, last_login=stamp, message="已登录")


__all__ = [
    "CloudLoginOutcome",
    "HSRCloudLoginBusyError",
    "run_cloud_login",
]
