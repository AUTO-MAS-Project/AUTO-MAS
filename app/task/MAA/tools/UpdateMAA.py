#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
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

import asyncio
import json
from pathlib import Path

from app.services import System
from app.utils import ProcessRunner, get_logger
from app.utils.io import read_file, write_file

from ..base_preset import ensure_maa_default_configuration
from .native_config import maa_scheme_name
from .resource_update import _wait_for_cleanup

logger = get_logger("MAA 更新工具")
_UPDATER_TIMEOUT = 120  # 秒，超时保留原生备份，待官方更新结束后由用户恢复


class MaaUpdaterRunningError(RuntimeError):
    """更新相关进程未能退出，不能恢复配置或启动新的托管任务。"""


async def update_maa(maa_path: Path):
    """更新 MAA 主程序"""

    # NEW: Update.UpdatePackage 优先生效
    try:
        new_set = read_file(maa_path / "config/gui.new.json")
        maa_update_package = new_set.get("Update", {}).get("UpdatePackage", "")
    except json.JSONDecodeError:
        maa_update_package = ""
    # OLD: Global.VersionUpdate.package
    if not maa_update_package:
        try:
            old_set = read_file(maa_path / "config/gui.json")
            maa_update_package = old_set.get("Global", {}).get(
                "VersionUpdate.package", ""
            )
        except json.JSONDecodeError:
            maa_update_package = ""

    if not maa_update_package or not (maa_path / maa_update_package).exists():
        return

    if not await System.kill_process(maa_path / "MAA.exe"):
        raise MaaUpdaterRunningError(
            "无法关闭 MAA 窗口，暂不安装更新；请退出 MAA 后重试"
        )

    maa_new_set = read_file(maa_path / "config/gui.new.json")
    active_scheme = maa_scheme_name(maa_new_set)
    original_default = None
    if active_scheme != "Default":
        configurations = maa_new_set.get("Configurations")
        if isinstance(configurations, dict):
            original_default = configurations.get("Default")

    # 把生效方案归一为 Default；Default 本身也可能缺失——沿用安装目录配置时
    # 该文件不由 MAS 生成，兜底必须无条件执行。
    ensure_maa_default_configuration(maa_new_set)

    # 关闭所有定时
    if "Timers" not in maa_new_set:
        maa_new_set["Timers"] = {}
    if "List" not in maa_new_set["Timers"]:
        maa_new_set["Timers"]["List"] = []
    for timer in maa_new_set["Timers"].get("List", []):
        if isinstance(timer, dict):
            timer["IsEnabled"] = False

    # 不直接运行任务；PostActions [Flags] 枚举 None=0
    default_gui = maa_new_set["Configurations"]["Default"]["Gui"]
    default_gui["PostActions"] = 0
    default_gui["StartUpSettings"].update(
        {"RunDirectly": False, "StartEmulator": False}
    )

    # 静默模式相关配置
    root_gui = maa_new_set.setdefault("Gui", {})
    root_gui["UseTray"] = True
    root_gui["MinimizeToTray"] = True
    root_gui["MinimizeOnStartup"] = True

    # 更新配置
    update_set = maa_new_set.setdefault("Update", {})
    update_set["UpdatePackage"] = maa_update_package
    update_set["CheckOnSchedule"] = False
    update_set["AutoDownloadUpdatePackage"] = False
    update_set["AutoInstallUpdatePackage"] = True

    # 无人值守拉起装更新，公告与更新后首启的版本说明弹窗一并关闭
    maa_new_set.setdefault("AnnouncementInfo", {})["DoNotShow"] = True
    update_set["DoNotShowUpdate"] = True

    # ensure 会把活动方案折叠成 Default；更新安装目录配置时只改活动方案，
    # 再把原来的 Default 和 Current 放回去，别动用户其它方案的设置。
    if active_scheme != "Default":
        configurations = maa_new_set["Configurations"]
        configurations[active_scheme] = configurations["Default"]
        if original_default is None:
            configurations.pop("Default", None)
        else:
            configurations["Default"] = original_default
        maa_new_set["Current"] = active_scheme

    write_file(maa_path / "config/gui.new.json", maa_new_set)

    try:
        await ProcessRunner.run_process(maa_path / "MAA.exe", timeout=60)
    except Exception as e:
        logger.info(f"MAA 更新任务结束: {e}")
    finally:
        # 新版 MAA 把安装委托给独立更新器，启动进程退出不代表安装结束。
        # 安装完成前不能还原 config；更新器自动重启的 GUI 也必须在还原前退出。
        cleanup = asyncio.create_task(_wait_for_updater(maa_path))
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            await _wait_for_cleanup(cleanup)
            cleanup.result()
            raise


async def _wait_for_updater(maa_path: Path) -> None:
    try:
        async with asyncio.timeout(_UPDATER_TIMEOUT):
            while await System.is_process_running(maa_path / "MAA.Updater.exe"):
                await asyncio.sleep(0.2)
    except TimeoutError as error:
        raise MaaUpdaterRunningError(
            "MAA 官方更新器等待超时，请等待更新结束并退出 MAA 后，从原生配置备份恢复"
        ) from error
    if not await System.kill_process(maa_path / "MAA.exe"):
        raise MaaUpdaterRunningError(
            "无法关闭更新后的 MAA 窗口，请退出 MAA 后从原生配置备份恢复"
        )
