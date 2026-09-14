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


import asyncio
import shutil
import uuid
from pathlib import Path
from typing import Any

from app.core.ws import Publisher, protocol
from app.models.config import MaaEndConfig, MaaEndUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.emulator import DeviceBase
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, TaskExecuteBase
from app.services import System
from app.utils import ProcessManager, get_logger
from app.utils.io import (
    mark_native_config_injected,
    read_file,
    replace_dir,
    swap_in_dir,
    write_file,
)

from .tools.backup_archive import archive_mas_runtime_backup, read_overlay_values

logger = get_logger("MaaEnd 脚本设置")


def maaend_config_mode(raw: object) -> str:
    """读取 MaaEnd 配置来源，并兼容旧版名称。"""

    mode = str(raw or "脚本")
    return {"简洁": "脚本", "详细": "用户", "自定义": "用户"}.get(mode, mode)


def maaend_mas_config_dir(script_id: str, user_id: str, mode: str) -> Path:
    """返回脚本共享或用户独立配置目录。"""

    mode = maaend_config_mode(mode)
    if mode == "直控":
        raise ValueError("直控配置不使用 MAS 配置目录")
    owner = "Default" if mode == "脚本" else user_id
    return Path.cwd() / "data" / script_id / owner / "ConfigFile"


def normalize_maaend_config(
    maaend_set: dict[str, Any],
    controller_type: str,
    fallback_set: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """将 MaaEnd 配置收束为 AUTO-MAS 单实例配置"""

    def select_instance(source_set: dict[str, Any]) -> dict[str, Any] | None:
        instances = source_set.get("instances")
        if not isinstance(instances, list) or len(instances) == 0:
            return None

        last_active_instance_id = source_set.get("lastActiveInstanceId")
        for instance in instances:
            if instance.get("id") == "automas" or instance.get("name") == "AUTO-MAS":
                return instance
            if (
                isinstance(instance, dict)
                and instance.get("id") == last_active_instance_id
            ):
                return instance

        for instance in instances:
            if isinstance(instance, dict):
                return instance
        return None

    selected_instance = select_instance(maaend_set)
    if selected_instance is None and fallback_set is not None:
        selected_instance = select_instance(fallback_set)
    if selected_instance is None:
        raise ValueError("MaaEnd 配置文件中未找到可用实例")

    selected_instance["id"] = "automas"
    selected_instance["name"] = "AUTO-MAS"
    selected_instance.pop("customName", None)
    selected_instance["controllerName"] = controller_type
    selected_instance.setdefault("tasks", [])

    maaend_set["instances"] = [selected_instance]
    maaend_set["lastActiveInstanceId"] = "automas"
    return maaend_set


class ScriptConfigTask(TaskExecuteBase):
    """MaaEnd 脚本设置模式

    会话包络（下发源 + 回写目标）与运行下发同一套 owner 规则
    （:func:`maaend_mas_config_dir`：脚本态=Default 共享、用户态=独立目录）。
    view_only=True 时为查看会话：只读预览（如「查看历史备份」）——用户级
    会话下发的 owner 目录即刚恢复的备份（所见即备份），脚本级会话跳过
    下发（原生目录即备份）；结束不回写 MAS 配置，安装 config/ 由 manager
    的任务前快照还原（临时注入，看完还原）。
    """

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: MaaEndConfig,
        user_config: MultipleConfig[MaaEndUserConfig],
        emulator_manager: DeviceBase | None,
        view_only: bool = False,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.crashed = False
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        # 查看会话：只读预览（如「查看历史备份」），结束不回写 MAS 配置
        self.view_only = view_only
        target_user_id = self.cur_user_item.user_id
        self.config_mode = "脚本"
        if target_user_id != "Default":
            self.config_mode = maaend_config_mode(
                self.user_config[uuid.UUID(target_user_id)].get("Info", "Mode")
            )
        self.use_mas_config = self.config_mode != "直控"
        self.config_file_path = (
            maaend_mas_config_dir(
                self.script_info.script_id,
                target_user_id,
                self.config_mode,
            )
            if self.use_mas_config
            else None
        )

    async def prepare(self):

        self.maaend_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()

        self.maaend_root_path = Path(self.script_config.get("Info", "Path"))
        self.maaend_set_path = self.maaend_root_path / "config"
        self.maaend_exe_path = self.maaend_root_path / "MaaEnd.exe"

    async def main_task(self):

        await self.prepare()

        await self.set_maaend()
        logger.info(f"启动 MaaEnd 进程: {self.maaend_exe_path}")
        self.wait_event.clear()
        await self.maaend_process_manager.open_process(self.maaend_exe_path)
        await self.wait_event.wait()

    async def set_maaend(self):
        """配置 MaaEnd 运行参数"""

        logger.info(f"开始配置 MaaEnd 运行参数: 设置脚本 {self.cur_user_item.user_id}")

        await self.maaend_process_manager.kill()
        await System.kill_process(self.maaend_exe_path)

        # 查看会话的脚本级入口：原生目录即所选备份，跳过下发与注入
        if self.view_only and self.cur_user_item.user_id == "Default":
            logger.info("MaaEnd 查看会话跳过配置下发: 原生目录即所选备份")
            return

        if (
            self.use_mas_config
            and self.config_file_path
            and (self.config_file_path / "mxu-MaaEnd.json").exists()
        ):
            replace_dir(self.config_file_path, self.maaend_set_path)
            mark_native_config_injected(
                Path.cwd() / f"data/{self.script_info.script_id}/Temp",
                self.maaend_set_path,
                script_id=self.script_info.script_id,
            )
        elif (
            self.use_mas_config
            and self.config_file_path
            and self.maaend_set_path.exists()
        ):
            shutil.copytree(
                self.maaend_set_path,
                self.config_file_path,
                dirs_exist_ok=True,
            )

        # 下发前归档 MAS 配置到用户池（下发源，会话保存会覆盖它；带快速
        # 配置覆盖层字段侧车，指纹去重，失败不阻断会话）。native 池由
        # manager.prepare 在任务级一次性归档
        if self.use_mas_config and self.config_file_path:
            target_user_id = self.cur_user_item.user_id
            overlay = (
                read_overlay_values(self.user_config[uuid.UUID(target_user_id)])
                if target_user_id != "Default"
                else None
            )
            archive_mas_runtime_backup(
                self.script_info.script_id,
                target_user_id,
                self.config_file_path,
                overlay=overlay,
            )

        maaend_set_path = self.maaend_set_path / "mxu-MaaEnd.json"
        if not maaend_set_path.exists():
            raise FileNotFoundError(
                "未找到 MaaEnd 配置文件, 请检查 MaaEnd 路径设置或先启动 MaaEnd 完成配置文件生成"
            )

        if self.use_mas_config:
            maaend_set = read_file(maaend_set_path)
            maaend_set = normalize_maaend_config(
                maaend_set,
                self.script_config.get("Game", "ControllerType"),
            )
            write_file(maaend_set_path, maaend_set)
        logger.success(f"MaaEnd 运行参数配置完成: {self.config_mode}配置")

    async def final_task(self):

        await self.maaend_process_manager.kill()
        await System.kill_process(self.maaend_exe_path)

        # 查看会话：只读预览，不把安装 config/ 回写 MAS 目录（安装现场由
        # manager 的任务前快照还原）；GUI 内的改动一律丢弃
        if self.view_only:
            logger.success("MaaEnd 查看结束（只读，不回写配置）")
            self.cur_user_item.status = "完成"
            return

        # 配置会话没有自然结束点: main_task 里的 wait_event 没有任何设置方,
        # 用户在配置窗口点「保存配置」发起的中止就是唯一出口, 因此这里不能按
        # 中止丢弃改动, 否则 MaaEnd GUI 的编辑永远落不回 MAS 配置目录。
        # 但 main_task 已经失败(如 MaaEnd 配置目录不存在)时没有任何可回写的
        # 内容, 再换入只会把不存在的目录当源头再报一次错, 盖住真正的原因。
        if not self.crashed and self.use_mas_config and self.config_file_path:
            swap_in_dir(self.maaend_set_path, self.config_file_path)
            config_path = self.config_file_path / "mxu-MaaEnd.json"
            maaend_set = read_file(config_path)
            maaend_set = normalize_maaend_config(
                maaend_set, self.script_config.get("Game", "ControllerType")
            )
            write_file(config_path, maaend_set)
            logger.success(f"MaaEnd 配置已保存到: {self.config_file_path}")
            self.cur_user_item.status = "完成"
        elif not self.crashed:
            logger.success("MaaEnd 直控配置已由脚本原生 GUI 保存")
            self.cur_user_item.status = "完成"

    async def on_crash(self, e: Exception):
        self.crashed = True
        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"脚本设置任务出现异常: {e}")
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=f"脚本设置任务出现异常: {e}"),
        )
