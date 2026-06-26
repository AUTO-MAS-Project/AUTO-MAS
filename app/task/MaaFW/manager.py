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


import asyncio
import uuid
from datetime import datetime
from pathlib import Path

from app.core import Config, EmulatorManager
from app.models.ConfigBase import MultipleConfig
from app.models.config import MaaFWConfig, MaaFWUserConfig
from app.models.emulator import DeviceBase
from app.models.task import ScriptItem, TaskExecuteBase, UserItem
from app.services import Notify
from app.utils import get_logger
from app.utils.constants import TASK_MODE_ZH

from .AutoProxy import AutoProxyTask
from .interface_loader import MaaFWInterfaceLoadError, load_interface_model_cached
from .project_updater import update_maafw_project_if_needed
from .runner import prepare_maafw_agent_python_envs


logger = get_logger("MaaFW 调度器")

METHOD_BOOK: dict[str, type[AutoProxyTask]] = {
    "AutoProxy": AutoProxyTask,
}


class MaaFWManager(TaskExecuteBase):
    """MaaFW 项目调度器"""

    def __init__(self, script_info: ScriptItem):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config: MaaFWConfig | None = None
        self.user_config: MultipleConfig[MaaFWUserConfig] | None = None
        self.emulator_manager: DeviceBase | None = None
        self.check_result = "-"
        self.begin_time = ""

    async def check(self) -> str:
        """校验 MaaFW 项目配置是否可用"""
        script_id = uuid.UUID(self.script_info.script_id)
        script_config = Config.ScriptConfig[script_id]

        if self.task_info.mode not in METHOD_BOOK:
            return "不支持的任务模式，请检查任务配置"
        if not isinstance(script_config, MaaFWConfig):
            return "脚本配置类型错误，不是 MaaFW 项目类型"

        raw_project_path = str(script_config.get("Info", "Path") or "").strip()
        if not raw_project_path:
            return "请设置 MaaFW 项目路径"
        project_path = Path(raw_project_path)
        if not project_path.exists():
            return "请设置 MaaFW 项目路径"

        try:
            interface = load_interface_model_cached(project_path)
        except MaaFWInterfaceLoadError as exc:
            return f"无法读取 MaaFW interface，请检查项目路径: {exc}"

        if not interface.controller:
            return "MaaFW interface 未声明 controller，请检查项目目录"
        if not interface.resource:
            return "MaaFW interface 未声明 resource，请检查项目目录"
        if not interface.task:
            return "MaaFW interface 未声明 task，请检查项目目录"

        emulator_id = script_config.get("Emulator", "Id")
        emulator_index = script_config.get("Emulator", "Index")
        if emulator_id != "-" and emulator_index in ("", "-"):
            return "请在 MaaFW 脚本配置中选择模拟器实例"

        return "Pass"

    async def prepare(self) -> None:
        """运行前准备"""
        script_id = uuid.UUID(self.script_info.script_id)
        await Config.ScriptConfig[script_id].lock()

        self.script_config = Config.ScriptConfig[script_id]
        self.user_config = MultipleConfig([MaaFWUserConfig])
        await self.user_config.load(await self.script_config.UserData.toDict())
        logger.success(f"{self.script_info.script_id} 已锁定，MaaFW 配置提取完成")

        await self._update_project_before_run()

        emulator_id = self.script_config.get("Emulator", "Id")
        if emulator_id != "-":
            self.emulator_manager = await EmulatorManager.get_emulator_instance(
                emulator_id
            )

        self.script_info.user_list = [
            UserItem(
                user_id=str(uid),
                name=config.get("Info", "Name"),
                status="等待",
            )
            for uid, config in self.user_config.items()
            if config.get("Info", "Status")
            and config.get("Info", "RemainedDay") != 0
        ]
        logger.info(
            f"用户列表加载完成，已筛选用户数: {len(self.script_info.user_list)}"
        )

    async def _update_project_before_run(self) -> None:
        """在 MaaFW resource 加载前尝试更新项目目录。"""

        if self.script_config is None:
            return
        if not self.script_config.get("Update", "IfAutoUpdate"):
            self._send_update_log("MaaFW 项目运行前自动更新已关闭")
            return

        project_path = Path(self.script_config.get("Info", "Path")).resolve()
        try:
            interface_model = load_interface_model_cached(project_path)
        except MaaFWInterfaceLoadError as exc:
            self._send_update_log(f"MaaFW 项目更新跳过，interface 读取失败: {exc}")
            return

        mirror_cdk = (
            self.script_config.get("Update", "MirrorChyanCDK")
            or Config.get("Update", "MirrorChyanCDK")
        )
        source = self.script_config.get("Update", "Source") or Config.get("Update", "Source")
        channel = self.script_config.get("Update", "Channel") or Config.get("Update", "Channel")
        try:
            update_result = await update_maafw_project_if_needed(
                project_path,
                interface_model,
                source=source,
                mirror_cdk=mirror_cdk,
                channel=channel,
                proxy=Config.proxy,
                send_log=self._send_update_log,
            )
            if update_result.updated:
                refreshed_interface = load_interface_model_cached(
                    project_path,
                    force_reload=True,
                )
                self._send_update_log("MaaFW project updated, preparing agent Python env")
                await asyncio.to_thread(
                    prepare_maafw_agent_python_envs,
                    project_path,
                    refreshed_interface,
                    send_log=self._send_update_log,
                )
        except Exception as exc:
            self._send_update_log(f"MaaFW 项目更新失败，继续使用当前目录: {exc}")

    def _send_update_log(self, message: str) -> None:
        logger.info(message)
        self.script_info.log = message

    async def main_task(self):
        self.check_result = await self.check()
        if self.check_result != "Pass":
            logger.error(f"未通过配置检查: {self.check_result}")
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": self.check_result},
            )
            return

        self.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await self.prepare()

        if self.script_config is None or self.user_config is None:
            raise RuntimeError("MaaFW 配置未完成初始化")

        for self.script_info.current_index in range(len(self.script_info.user_list)):
            task = METHOD_BOOK[self.task_info.mode](
                self.script_info,
                self.script_config,
                self.user_config,
                self.emulator_manager,
            )
            await self.spawn(task)

    async def final_task(self):
        """运行结束后的收尾工作"""
        script_id = uuid.UUID(self.script_info.script_id)
        script_cfg = Config.ScriptConfig[script_id]

        if script_cfg.is_locked:
            await script_cfg.unlock()

        if self.check_result != "Pass":
            self.script_info.status = "异常"
            return self.check_result

        if self.user_config is not None and self.task_info.mode == "AutoProxy":
            await script_cfg.UserData.load(await self.user_config.toDict())

        error_user = [u.name for u in self.script_info.user_list if u.status == "异常"]
        over_user = [u.name for u in self.script_info.user_list if u.status == "完成"]
        wait_user = [u.name for u in self.script_info.user_list if u.status == "等待"]
        skip_user = [u.name for u in self.script_info.user_list if u.status == "跳过"]

        if error_user:
            self.script_info.status = "异常"
        elif over_user:
            self.script_info.status = "完成"
        else:
            self.script_info.status = "跳过" if skip_user else "完成"

        title = (
            f"{datetime.now().strftime('%m-%d')} | "
            f"{self.script_info.name or '空白'}的{TASK_MODE_ZH[self.task_info.mode]}任务报告"
        )
        try:
            await Notify.push_plyer(
                title.replace("报告", "已完成！"),
                f"已完成用户数: {len(over_user)}, 未完成用户数: {len(error_user) + len(wait_user)}",
                f"已完成用户数: {len(over_user)}, 未完成用户数: {len(error_user) + len(wait_user)}",
                10,
            )
        except Exception as exc:
            logger.warning(f"MaaFW 桌面通知发送失败: {exc}")

    async def on_crash(self, e: Exception):
        self.script_info.status = "异常"
        logger.exception(f"MaaFW 任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"MaaFW 任务出现异常: {e}"},
        )
