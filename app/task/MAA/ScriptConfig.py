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
import shutil
import uuid
from pathlib import Path

from app.core import Config
from app.core.ws import Publisher, protocol
from app.models.config import MaaConfig, MaaUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.emulator import DeviceBase
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, TaskExecuteBase
from app.services import System
from app.utils import ProcessManager, get_logger
from app.utils.io import read_file, write_file

from .AutoProxy import _build_maa_preset_task_queue
from .tools.backup_archive import (
    archive_mas_runtime_backup,
    mas_config_dir,
    read_overlay_values,
)

logger = get_logger("MAA 脚本设置")


class ScriptConfigTask(TaskExecuteBase):
    """脚本设置模式

    view_only=True 时为查看会话：只读预览（如「查看历史备份」）——用户级
    会话下发的用户目录即刚恢复的备份（所见即备份），脚本级会话跳过下发
    （原生目录即备份）；结束不回写 MAS 配置，安装 config/ 由 manager 的
    任务前快照还原（临时注入，看完还原）。
    """

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: MaaConfig,
        user_config: MultipleConfig[MaaUserConfig],
        emulator_manager: DeviceBase,
        view_only: bool = False,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        # 查看会话：只读预览（如「查看历史备份」），结束不回写 MAS 配置
        self.view_only = view_only

    async def prepare(self):

        self.maa_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()

        self.maa_root_path = Path(self.script_config.get("Info", "Path"))
        self.maa_set_path = self.maa_root_path / "config"
        self.maa_exe_path = self.maa_root_path / "MAA.exe"

    async def main_task(self):

        await self.prepare()

        await self.set_maa()
        logger.info(f"启动MAA进程: {self.maa_exe_path}")
        self.wait_event.clear()
        await self.maa_process_manager.open_process(self.maa_exe_path)
        await self.wait_event.wait()

    async def set_maa(self):
        """配置MAA运行参数"""

        logger.info(f"开始配置MAA运行参数: 设置脚本 {self.cur_user_item.user_id}")

        await self.maa_process_manager.kill()
        await System.kill_process(self.maa_exe_path)

        # 查看会话的脚本级入口：原生目录即所选备份，跳过下发与注入
        if self.view_only and self.cur_user_item.user_id == "Default":
            logger.info("MAA 查看会话跳过配置下发: 原生目录即所选备份")
            return

        # 下发前归档 MAS 配置到用户池（运行下发源；带页面任务字段侧车，
        # 指纹去重，失败不阻断会话）。native 池由 manager.prepare 在任务级
        # 一次性归档
        target_user_id = self.cur_user_item.user_id
        mas_owner = "Default"
        if target_user_id != "Default":
            mode = self.user_config[uuid.UUID(target_user_id)].get("Info", "Mode")
            mas_owner = target_user_id if mode == "用户" else "Default"
            overlay = read_overlay_values(self.user_config[uuid.UUID(target_user_id)])
        else:
            overlay = None
        archive_mas_runtime_backup(
            self.script_info.script_id,
            target_user_id,
            mas_config_dir(self.script_info.script_id, mas_owner),
            overlay=overlay,
        )

        if (
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile"
        ).exists():
            shutil.copytree(
                (
                    Path.cwd()
                    / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile"
                ),
                self.maa_set_path,
                dirs_exist_ok=True,
            )

        gui_set = read_file(self.maa_set_path / "gui.json")
        gui_new_set = read_file(self.maa_set_path / "gui.new.json")

        # 多配置使用默认配置（gui.new.json 的方案列表可能与 gui.json 不一致，缺失当前方案时保留其自有 Default）
        if gui_set["Current"] != "Default":
            gui_set["Configurations"]["Default"] = gui_set["Configurations"][
                gui_set["Current"]
            ]
            gui_new_configurations = gui_new_set.setdefault("Configurations", {})
            if gui_set["Current"] in gui_new_configurations:
                gui_new_configurations["Default"] = gui_new_configurations[
                    gui_set["Current"]
                ]
            gui_new_configurations.setdefault("Default", {})
            gui_set["Current"] = "Default"

        # 各配置部分的引用
        global_set = gui_set["Global"]
        default_set = gui_set["Configurations"]["Default"]

        # 配置 GUI 使用与 MAS 运行时一致的任务顺序，并预置合成任务。
        source_queue = gui_new_set["Configurations"]["Default"].get("TaskQueue", [])
        if not isinstance(source_queue, list):
            source_queue = []
        gui_new_set["Configurations"]["Default"]["TaskQueue"] = (
            _build_maa_preset_task_queue(source_queue)
        )

        # 任务间切换方式
        default_set["MainFunction.PostActions"] = "0"  # OLD: 即将移除
        # NEW: PostActions [Flags] 枚举 None=0
        gui_new_set.setdefault("Configurations", {}).setdefault(
            "Default", {}
        ).setdefault("Gui", {})["PostActions"] = 0

        # 不直接运行任务
        default_set["Start.StartGame"] = "True"  # OLD: 即将移除
        default_set["Start.RunDirectly"] = "False"  # OLD: 即将移除
        default_set["Start.OpenEmulatorAfterLaunch"] = "False"  # OLD: 即将移除
        # NEW:
        gui_new_set.setdefault("Configurations", {}).setdefault(
            "Default", {}
        ).setdefault("Gui", {}).setdefault("RuntimeSettings", {})["StartGame"] = True
        gui_new_set.setdefault("Configurations", {}).setdefault(
            "Default", {}
        ).setdefault("Gui", {}).setdefault("StartUpSettings", {})["RunDirectly"] = False
        gui_new_set.setdefault("Configurations", {}).setdefault(
            "Default", {}
        ).setdefault("Gui", {}).setdefault("StartUpSettings", {})[
            "StartEmulator"
        ] = False

        # 关闭所有定时
        for i in range(1, 9):
            global_set[f"Timer.Timer{i}"] = "False"  # OLD: 即将移除
        # NEW: Timers.List[*].IsEnabled = false
        if "Timers" not in gui_new_set:
            gui_new_set["Timers"] = {}
        if "List" not in gui_new_set["Timers"]:
            gui_new_set["Timers"]["List"] = []
        for timer in gui_new_set["Timers"].get("List", []):
            if isinstance(timer, dict):
                timer["IsEnabled"] = False

        # 更新配置
        global_set["VersionUpdate.ScheduledUpdateCheck"] = "False"  # OLD: 即将移除
        global_set["VersionUpdate.AutoDownloadUpdatePackage"] = "False"  # OLD: 即将移除
        global_set["VersionUpdate.AutoInstallUpdatePackage"] = "False"  # OLD: 即将移除
        # NEW:
        gui_new_set.setdefault("Update", {})["CheckOnSchedule"] = False
        gui_new_set.setdefault("Update", {})["AutoDownloadUpdatePackage"] = False
        gui_new_set.setdefault("Update", {})["AutoInstallUpdatePackage"] = False

        # 静默模式相关配置
        if Config.get("Function", "IfSilence"):
            global_set["Start.MinimizeDirectly"] = "False"  # OLD: 即将移除
            # NEW:
            gui_new_set.setdefault("Gui", {})["MinimizeOnStartup"] = False

        (self.maa_set_path / "gui.json").write_text(  # OLD: 即将移除
            json.dumps(gui_set, ensure_ascii=False, indent=4),
            encoding="utf-8",  # OLD: 即将移除
        )  # OLD: 即将移除
        write_file(self.maa_set_path / "gui.new.json", gui_new_set)
        logger.success(f"MAA运行参数配置完成: 设置脚本 {self.cur_user_item.user_id}")

    async def final_task(self):

        await self.maa_process_manager.kill()
        await System.kill_process(self.maa_exe_path)

        # 查看会话：只读预览，不把安装 config/ 回写用户目录（安装现场由
        # manager 的任务前快照还原）；GUI 内的改动一律丢弃
        if self.view_only:
            logger.success("MAA 查看结束（只读，不回写配置）")
            self.cur_user_item.status = "完成"
            return

        shutil.rmtree(
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile",
            ignore_errors=True,
        )
        (
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile"
        ).mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            self.maa_set_path,
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile",
            dirs_exist_ok=True,
        )

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"脚本设置任务出现异常: {e}")
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=f"脚本设置任务出现异常: {e}"),
        )
