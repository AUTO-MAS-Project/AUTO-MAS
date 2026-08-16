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

import json
from pathlib import Path

from app.services import System
from app.utils import ProcessRunner, get_logger
from app.utils.constants import MAA_TASKS
from app.utils.io import read_file, write_file

logger = get_logger("MAA 更新工具")


async def update_maa(maa_path: Path):
    """更新 MAA 主程序"""

    # NEW: Update.UpdatePackage 优先生效
    try:
        new_set = read_file(maa_path / "config/gui.new.json")
        maa_update_package = new_set.get("Update", {}).get("UpdatePackage", "")
    except (FileNotFoundError, json.JSONDecodeError):
        maa_update_package = ""
    # OLD: Global.VersionUpdate.package
    if not maa_update_package:
        try:
            old_set = read_file(maa_path / "config/gui.json")
            maa_update_package = old_set.get("Global", {}).get(
                "VersionUpdate.package", ""
            )
        except (FileNotFoundError, json.JSONDecodeError):
            maa_update_package = ""

    if not maa_update_package or not (maa_path / maa_update_package).exists():
        return

    await System.kill_process(maa_path / "MAA.exe")

    maa_set = read_file(maa_path / "config/gui.json")
    maa_new_set = read_file(maa_path / "config/gui.new.json")

    # 多配置使用默认配置
    if maa_set["Current"] != "Default":
        maa_set["Configurations"]["Default"] = maa_set["Configurations"][
            maa_set["Current"]
        ]
        maa_new_set["Configurations"]["Default"] = maa_new_set["Configurations"][
            maa_set["Current"]
        ]
        maa_set["Current"] = "Default"

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
    maa_new_set.setdefault("Gui", {})["UseTray"] = True
    maa_new_set.setdefault("Gui", {})["MinimizeToTray"] = True
    maa_new_set.setdefault("Gui", {})["MinimizeOnStartup"] = True

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

    (maa_path / "config/gui.json").write_text(  # OLD: 即将移除
        json.dumps(maa_set, ensure_ascii=False, indent=4),
        encoding="utf-8",  # OLD: 即将移除
    )  # OLD: 即将移除
    write_file(maa_path / "config/gui.new.json", maa_new_set)

    try:
        await ProcessRunner.run_process(maa_path / "MAA.exe", timeout=60)
    except Exception as e:
        logger.info(f"MAA 更新任务结束: {e}")
