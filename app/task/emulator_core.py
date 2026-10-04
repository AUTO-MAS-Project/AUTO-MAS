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
"""

import asyncio
import time
from typing import Any

from app.utils import get_logger

logger = get_logger("模拟器管理")

# 模拟器可能已无响应，关闭动作不能无限期挂住任务收尾
EMULATOR_CLOSE_TIMEOUT_SECONDS = 30


def resolve_device_ref(manager: Any, index: Any) -> Any | None:
    """设备号 → ``DeviceRef``（Emulator 2.0 才有；旧式管理器、查不到都返回 ``None``）。"""
    resolve_device = getattr(manager, "resolve_device", None)
    if resolve_device is None or index in (None, "", "-"):
        return None
    try:
        return resolve_device(str(index))
    except Exception as e:  # noqa: BLE001 - 认不出就按普通模拟器处理
        logger.debug(f"解析设备 {index} 失败，按普通模拟器处理: {e}")
        return None


async def script_process_env(manager: Any, index: Any) -> dict[str, str] | None:
    """为某台设备起脚本进程时要用的环境：官方模拟器实例返回「MAS 环境 + ``ANDROID_ADB_SERVER_PORT``
    = 脚本专用端口（``scriptAdbServerPort``，默认 20049）」，其余返回 ``None``（照旧继承 MAS 的环境）。

    脚本用 SDK 的新版 adb，跑在 5037 上会和雷电 / MuMu 自带的旧版 adb 互杀 server。
    """
    device_ref = resolve_device_ref(manager, index)
    if device_ref is None or getattr(device_ref, "emulator_type", None) != "avd":
        return None
    import os

    from app.utils.emulator2.avd import host
    from app.utils.emulator2.avd.components import (
        root_from_manager_exe,
        script_adb_env,
    )

    root = root_from_manager_exe(device_ref.manager_path)
    env = dict(os.environ)
    env.update(script_adb_env(root))
    try:
        # 先由 MAS 以脱离方式起好：脚本里的 adb 顺手拉起的 server 会继承脚本的输出管道
        await host.ensure_script_adb_server(root)
    except Exception as e:  # noqa: BLE001 - 起不来就交给脚本自己的 adb
        logger.warning(f"预先启动脚本专用 adb server 失败: {e}")
    logger.info(
        f"设备 {index} 是官方模拟器实例：脚本的 adb 走专用 server（端口 "
        f"{env['ANDROID_ADB_SERVER_PORT']}）"
    )
    return env


async def resolve_host_adb(
    owner: Any, *, index: str | None = None, config_key: str = "Emulator"
) -> Any | None:
    """owner 接管的设备是官方模拟器实例时，返回宿主进程对它发 adb 的通道（MAS 私有 server，
    ``await runner(*args, timeout=…)``，另有 ``screencap_png()``）；其余情况返回 ``None``。

    官方模拟器实例上宿主自己的 adb 命令（游戏更新检查、失败截图）不能落到 5037：脚本用的 SDK adb
    会和雷电 / MuMu 自带的旧版 adb 互杀 server。雷电 / MuMu 返回 ``None``，调用方照旧走
    ``get_adb_path()`` + 设备地址。查不到只当作不是官方模拟器。
    """

    emulator_manager = getattr(owner, "emulator_manager", None)
    host_adb = getattr(emulator_manager, "host_adb", None)
    if host_adb is None:
        return None
    if index is None:
        index = owner.script_config.get(config_key, "Index")
    try:
        return await host_adb(index)
    except Exception as e:  # noqa: BLE001 - 认不出就按普通模拟器处理
        logger.debug(f"查询实例 {index} 的宿主 adb 通道失败，按普通模拟器处理: {e}")
        return None


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

    emulator_manager = getattr(owner, "emulator_manager", None)
    if emulator_manager is None:
        return True

    if index is None:
        index = owner.script_config.get(config_key, "Index")

    started_at = time.monotonic()
    logger.info(
        f"开始关闭模拟器: {type(emulator_manager).__name__} - 实例 {index} - "
        f"超时: {timeout}秒"
    )
    try:
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
