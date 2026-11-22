"""账号运行要用的宿主 / 模拟器能力：为这次运行开模拟器、脚本专用 adb 环境、锁屏判定。

宿主或模拟器适配这一侧（不归入积木）：参数是宿主的模拟器入口（``BoundEmulator`` 一类，参数名
``emulator``）、模拟器实例 uid 与普通数据，输出只有返回值与和 ``plan_run`` 同形的事件出口
（``MaaFWPlanRunSink``：账号日志一行、运行进度点）。**不读脚本 / 账号配置、不碰调用方对象**：
地址校验与缓存（``MaaFWAdbDeviceState``）、「MAS 开过模拟器」的标记、要不要静默都留在流程里，
锁屏时抛不抛异常也由流程定（拿到原因后抛 ``MaaFWWorkstationLocked(WORKSTATION_LOCKED_MESSAGE)``）。
三个专项的账号流程都调它。
"""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from app.models.emulator import DeviceInfo
from app.task.MaaFW.blocks.maafw_runner.host.device_config import (
    game_launched_with_emulator,
)
from app.task.MaaFW.blocks.maafw_runner.host.plan_run import (
    MaaFWPlanRunLog,
    MaaFWPlanRunPoint,
    MaaFWPlanRunSink,
)
from app.utils import IS_WINDOWS, get_logger
from app.utils import display as _utils_display

# 与任务类同一个名字：后端日志里这段流程的行照旧记在「MaaFW 插件自动代理」下
logger = get_logger("MaaFW 插件自动代理")

# 截图和输入都要落在用户的交互式桌面上的控制器。ADB 不受锁屏影响。
DESKTOP_CONTROLLER_TYPES = frozenset({"Win32", "Gamepad"})

WORKSTATION_LOCKED_MESSAGE = (
    "电脑处于锁屏状态，Win32 控制器的项目要在解锁的桌面上才能截图和操作，"
    "本次不运行、不重试，请解锁后再运行"
)


@dataclass(frozen=True, slots=True)
class MaaFWEmulatorLaunch:
    """这次开模拟器的结果：``started_at`` 是游戏随模拟器冷启动的单调时钟时刻，没冷启动为 None。"""

    device_info: DeviceInfo
    started_at: float | None


async def open_emulator_for_run(
    emulator: Any,
    device_uid: str,
    package_name: str,
    *,
    silent: bool,
    emit: MaaFWPlanRunSink,
) -> MaaFWEmulatorLaunch:
    """开模拟器（ModAVD 也开），冷启动游戏时打 ``start_game`` 的 launched 点、记下时刻。

    ``silent`` 为真时开完把模拟器窗口藏起来（失败不管）。``started_at`` 不为 None 就表示首任务
    闸门要改按「画面有内容 + 客体读盘停下来」放行（``disk_quiet``）。地址的校验与缓存在调用方。
    """

    emit(MaaFWPlanRunLog(f"正在启动模拟器: {device_uid}"))
    device_info = await emulator.open(device_uid, package_name, allow_mod_avd=True)
    # 只有冷启动才等（判据见 game_launched_with_emulator），首任务闸门按这里记的
    # 时刻与读盘判据算（task_start_gate）
    started_at: float | None = None
    if game_launched_with_emulator(device_info):
        emit(MaaFWPlanRunPoint("start_game", "succeeded", "launched"))
        started_at = time.monotonic()
        emit(MaaFWPlanRunLog(f"已随模拟器启动游戏: {package_name}"))
    if silent:
        with suppress(Exception):
            await emulator.setVisible(device_uid, False)
    return MaaFWEmulatorLaunch(device_info=device_info, started_at=started_at)


async def script_adb_env(emulator: Any, device_uid: str) -> dict[str, str]:
    """脚本专用 adb server 的端口（ModAVD 实例），给 worker 与运行前设置的进程环境；没有返回空。"""

    if emulator is None:
        return {}
    env = await emulator.process_env(device_uid)
    return (
        {"ANDROID_ADB_SERVER_PORT": env["ANDROID_ADB_SERVER_PORT"]}
        if env is not None
        else {}
    )


async def workstation_lock_reason(
    controller_type: str | None, desktop: Any
) -> str | None:
    """要用交互式桌面的控制器此刻锁屏的原因；不用桌面、没锁、查不出来都返回 None。

    查不出来不拦：这一步是给出明确原因的改善项，不该把本来能跑的任务打掉。``desktop`` 是
    桌面分身目标（``desktop_process_target.get()``），有就到分身里查。
    """

    if not IS_WINDOWS or controller_type not in DESKTOP_CONTROLLER_TYPES:
        return None
    try:
        if desktop is None:
            reason = await asyncio.to_thread(_utils_display.input_desktop_unavailable)
        else:
            from app.utils.windows.desktop_session.process_runner import (
                run_desktop_action,
            )

            _, output, _ = await run_desktop_action(
                desktop, "input_desktop_unavailable", {}
            )
            reason = output.decode("utf-8") if output else None
    except Exception as error:
        logger.opt(exception=True).warning(f"检查锁屏状态失败，照常运行：{error}")
        return None
    if reason is None:
        return None
    logger.warning(f"MaaFW 运行前检查到锁屏：{reason}")
    return reason


__all__ = [
    "DESKTOP_CONTROLLER_TYPES",
    "WORKSTATION_LOCKED_MESSAGE",
    "MaaFWEmulatorLaunch",
    "open_emulator_for_run",
    "script_adb_env",
    "workstation_lock_reason",
]
