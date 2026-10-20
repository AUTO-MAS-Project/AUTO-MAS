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

from ..base_preset import ensure_maa_default_configuration, update_maa_root_gui
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

    maa_set = read_file(maa_path / "config/gui.json")
    maa_new_set = read_file(maa_path / "config/gui.new.json")

    # 多配置使用默认配置（gui.new.json 的方案列表可能与 gui.json 不一致，缺失当前方案时保留其自有 Default）；
    # Default 本身也可能缺失——沿用安装目录配置时该文件不由 MAS 生成，兜底必须无条件执行。
    ensure_maa_default_configuration(maa_set, maa_new_set)

    # 各配置部分的引用
    global_set = maa_set["Global"]
    default_set = maa_set["Configurations"]["Default"]

    # 关闭所有定时
    for i in range(1, 9):
        global_set[f"Timer.Timer{i}"] = "False"  # OLD: 即将移除
    # NEW: Timers.List[*].IsEnabled = false
    if "Timers" not in maa_new_set:
        maa_new_set["Timers"] = {}
    if "List" not in maa_new_set["Timers"]:
        maa_new_set["Timers"]["List"] = []
    for timer in maa_new_set["Timers"].get("List", []):
        if isinstance(timer, dict):
            timer["IsEnabled"] = False

    # 不直接运行任务
    default_set["MainFunction.PostActions"] = "0"  # OLD: 即将移除
    # NEW: PostActions [Flags] 枚举 None=0
    maa_new_set.setdefault("Configurations", {}).setdefault("Default", {}).setdefault(
        "Gui", {}
    )["PostActions"] = 0
    default_set["Start.RunDirectly"] = "False"  # OLD: 即将移除
    default_set["Start.OpenEmulatorAfterLaunch"] = "False"  # OLD: 即将移除
    # NEW:
    maa_new_set.setdefault("Configurations", {}).setdefault("Default", {}).setdefault(
        "Gui", {}
    ).setdefault("StartUpSettings", {})["RunDirectly"] = False
    maa_new_set.setdefault("Configurations", {}).setdefault("Default", {}).setdefault(
        "Gui", {}
    ).setdefault("StartUpSettings", {})["StartEmulator"] = False

    # 静默模式相关配置
    global_set["GUI.UseTray"] = "True"  # OLD: 即将移除
    global_set["GUI.MinimizeToTray"] = "True"  # OLD: 即将移除
    global_set["Start.MinimizeDirectly"] = "True"  # OLD: 即将移除
    # NEW:
    update_maa_root_gui(
        maa_new_set,
        {"UseTray": True, "MinimizeToTray": True, "MinimizeOnStartup": True},
    )

    # 更新配置
    global_set["VersionUpdate.package"] = maa_update_package  # OLD: 即将移除
    global_set["VersionUpdate.ScheduledUpdateCheck"] = "False"  # OLD: 即将移除
    global_set["VersionUpdate.AutoDownloadUpdatePackage"] = "False"  # OLD: 即将移除
    global_set["VersionUpdate.AutoInstallUpdatePackage"] = "True"  # OLD: 即将移除
    # NEW:
    maa_new_set.setdefault("Update", {})["UpdatePackage"] = maa_update_package
    maa_new_set.setdefault("Update", {})["CheckOnSchedule"] = False
    maa_new_set.setdefault("Update", {})["AutoDownloadUpdatePackage"] = False
    maa_new_set.setdefault("Update", {})["AutoInstallUpdatePackage"] = True

    # 无人值守拉起装更新，公告与更新后首启的版本说明弹窗一并关闭
    global_set["Announcement.DoNotShowAnnouncement"] = "True"  # OLD: 即将移除
    global_set["VersionUpdate.doNotShowUpdate"] = "True"  # OLD: 即将移除
    # NEW:
    maa_new_set.setdefault("AnnouncementInfo", {})["DoNotShow"] = True
    maa_new_set.setdefault("Update", {})["DoNotShowUpdate"] = True

    (maa_path / "config/gui.json").write_text(  # OLD: 即将移除
        json.dumps(maa_set, ensure_ascii=False, indent=4),
        encoding="utf-8",  # OLD: 即将移除
    )  # OLD: 即将移除
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
