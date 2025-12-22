#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

import json
from pathlib import Path

from app.services import System
from app.utils import ProcessRunner, get_logger
from app.utils.constants import MAA_TASKS

logger = get_logger("MAA 更新工具")


async def update_maa(maa_path: Path):
    """更新 MAA 主程序"""

    maa_set = json.loads((maa_path / "config/gui.json").read_text(encoding="utf-8"))
    maa_update_package = maa_set.get("Global", {}).get("VersionUpdate.package", "")

    if not maa_update_package or not (maa_path / maa_update_package).exists():
        return

    await System.kill_process(maa_path / "MAA.exe")

    maa_set = json.loads((maa_path / "config/gui.json").read_text(encoding="utf-8"))
    if maa_set["Current"] != "Default":
        maa_set["Configurations"]["Default"] = maa_set["Configurations"][
            maa_set["Current"]
        ]
        maa_set["Current"] = "Default"
    for i in range(1, 9):
        maa_set["Global"][f"Timer.Timer{i}"] = "False"

    # 不直接运行任务
    maa_set["Configurations"]["Default"]["MainFunction.PostActions"] = "0"
    maa_set["Configurations"]["Default"]["Start.RunDirectly"] = "False"
    maa_set["Configurations"]["Default"]["Start.OpenEmulatorAfterLaunch"] = "False"

    # 静默模式相关配置
    maa_set["Global"]["GUI.UseTray"] = "True"
    maa_set["Global"]["GUI.MinimizeToTray"] = "True"
    maa_set["Global"]["Start.MinimizeDirectly"] = "True"

    # 更新配置
    maa_set["Global"]["VersionUpdate.package"] = maa_update_package
    maa_set["Global"]["VersionUpdate.ScheduledUpdateCheck"] = "False"
    maa_set["Global"]["VersionUpdate.AutoDownloadUpdatePackage"] = "False"
    maa_set["Global"]["VersionUpdate.AutoInstallUpdatePackage"] = "True"

    # 任务配置
    for task in MAA_TASKS:
        maa_set["Configurations"]["Default"][f"TaskQueue.{task}.IsChecked"] = "False"

    (maa_path / "config/gui.json").write_text(
        json.dumps(maa_set, ensure_ascii=False, indent=4), encoding="utf-8"
    )

    try:
        await ProcessRunner.run_process(maa_path / "MAA.exe", timeout=10)
    except Exception as e:
        logger.info(f"MAA 更新任务结束: {e}")
