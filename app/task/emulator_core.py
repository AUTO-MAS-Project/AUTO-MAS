#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""各专项共用的模拟器关闭动作。

MAA / M9A / BAAH / MaaEnd / MaaFW / SRC 在任务收尾与各条失败分支上都可能关闭
本次接管的模拟器实例，原本各自内联调用、失败日志各写一份，且多数漏了超时与
判空。这里只做「取实例索引 → 限时关闭 → 记录结果」这一件事：是否要关、以及
关闭失败算不算异常，由调用方自己决定。

另有 ModAVD 实例上用的几个小工具：门面 ``open`` 的放行参数、脚本进程的 adb 环境、宿主 adb 通道。
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, TypedDict
from uuid import UUID

from app.task.game import game_device_id
from app.task.run_flow import operation
from app.utils import get_logger

if TYPE_CHECKING:
    from app.models.emulator import DeviceRef, HostAdb
    from app.task.game import BoundEmulator

logger = get_logger("模拟器管理")

# 模拟器可能已无响应，关闭动作不能无限期挂住任务收尾
EMULATOR_CLOSE_TIMEOUT_SECONDS = 30


class _ModAvdOpenOptions(TypedDict):
    allow_mod_avd: bool


def mod_avd_open_kwargs(manager: Any, *, allowed: bool) -> _ModAvdOpenOptions:
    """[兼容旧专项] 明确交接调用方对 ModAVD 的支持能力。"""
    return {"allow_mod_avd": allowed}


def resolve_device_ref(
    manager: BoundEmulator | None, index: str | UUID | int | None
) -> DeviceRef | None:
    if manager is None or index in (None, "", "-"):
        return None
    return manager.resolve_device(str(index))


async def script_process_env(
    manager: BoundEmulator | None, index: str | UUID | int | None
) -> dict[str, str] | None:
    if manager is None or index in (None, "", "-"):
        return None
    return await manager.process_env(str(index))


async def resolve_host_adb(
    owner: Any, *, index: str | None = None, config_key: str = "Emulator"
) -> HostAdb | None:
    manager = owner.emulator
    if manager is None:
        return None
    if index is None:
        index = game_device_id(owner.script_config)
    return await manager.host_adb(str(index))


async def close_emulator(
    owner: Any,
    *,
    index: str | None = None,
    config_key: str = "Emulator",
    timeout: float = EMULATOR_CLOSE_TIMEOUT_SECONDS,
    log_failure: bool = True,
) -> bool:
    """关闭 owner 接管的模拟器实例，返回关闭动作是否成功。

    未接管模拟器（实例为 None）视为无需关闭，返回 True，以免调用方把
    「没有模拟器可关」误判成关闭失败。

    Args:
        owner: 提供 emulator_manager 与 script_config 的任务对象。
        index: 模拟器实例索引；省略时按 config_key 段的 "Index" 读取。
        config_key: 省略 index 时读取 "Index" 的配置段。特殊键名应显式传入 index。
        timeout: 关闭动作的超时秒数。
        log_failure: 失败时是否记录警告日志。
    """

    emulator_manager = owner.emulator
    if emulator_manager is None:
        return True

    if index is None:
        index = game_device_id(owner.script_config)

    started_at = time.monotonic()
    logger.info(
        f"开始关闭模拟器: {type(emulator_manager).__name__} - 实例 {index} - "
        f"超时: {timeout}秒"
    )
    try:
        with operation(owner, "stop_game"):
            await asyncio.wait_for(emulator_manager.close(index), timeout=timeout)
        logger.success(
            f"模拟器已关闭: {type(emulator_manager).__name__} - 实例 {index} - "
            f"用时: {time.monotonic() - started_at:.3f}秒"
        )
        return True
    except Exception as e:
        if log_failure:
            logger.opt(exception=True).warning(
                f"关闭模拟器失败: {type(emulator_manager).__name__} - "
                f"实例 {index} - 用时: "
                f"{time.monotonic() - started_at:.3f}秒 - {e}"
            )
        return False
