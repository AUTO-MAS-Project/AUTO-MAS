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

"""OkScript 通用控制器。

按用户逐个以 ``-t <模块.类名> -e`` 运行所选的一次性任务，结束时统一组装任务报告并推送；
另提供打开项目原生界面的配置会话（ScriptConfig）。配置来源只有「直接使用项目
原生配置」，本控制器不下发、不回写任何项目配置。
"""

import asyncio
import uuid
from contextlib import suppress
from datetime import datetime

from app.core import Config
from app.core.ws import Publisher, protocol
from app.models.config import OkScriptConfig, OkScriptUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, TaskExecuteBase, UserItem
from app.tools.push_log import build_user_result_text
from app.utils import get_logger
from app.utils.constants import TASK_MODE_ZH

from .AutoProxy import AutoProxyTask
from .project import OkScriptProject, OkScriptProjectError, probe_project
from .ScriptConfig import ScriptConfigTask
from .tools import push_notification

logger = get_logger("OkScript 调度器")


class OkScriptManager(TaskExecuteBase):
    """OkScript 通用控制器（ok-script 线）"""

    def __init__(self, script_info: ScriptItem):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.check_result = "-"
        self.script_config: OkScriptConfig | None = None
        self.user_config: MultipleConfig[OkScriptUserConfig] | None = None
        self.project: OkScriptProject | None = None
        self.begin_time = ""

    async def check(self) -> str:
        if self.task_info.mode not in ("AutoProxy", "ScriptConfig"):
            return "不支持的任务模式, 请检查任务配置！"

        script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        if not isinstance(script_config, OkScriptConfig):
            return "脚本配置类型错误, 不是 OkScript 类型"

        try:
            self.project = await asyncio.to_thread(
                probe_project, script_config.get("Info", "RootPath")
            )
        except OkScriptProjectError as e:
            return str(e)

        if self.task_info.mode == "AutoProxy" and not any(
            config.get("Info", "Status")
            and config.get("Info", "RemainedDay") != 0
            and self.task_info.is_target_user(str(uid))
            for uid, config in script_config.UserData.items()
        ):
            return "当前没有可执行的用户，请先添加并启用用户"

        return "Pass"

    async def prepare(self):
        script_uid = uuid.UUID(self.script_info.script_id)
        await Config.ScriptConfig[script_uid].lock()
        self.script_config = Config.ScriptConfig[script_uid]
        if not isinstance(self.script_config, OkScriptConfig):
            raise TypeError("脚本配置类型错误, 不是 OkScript 类型")
        # 任务期使用独立副本，避免在 ScriptConfig 已锁时写 UserData（对齐 Okww）
        self.user_config = MultipleConfig([OkScriptUserConfig])
        await self.user_config.load(await self.script_config.UserData.toDict())
        logger.success(f"{self.script_info.script_id} 已锁定, OkScript 用户配置已提取")

        if self.task_info.mode == "ScriptConfig":
            self.script_info.user_list = [
                UserItem(
                    user_id="Default",
                    name=f"{self.project.app_name} 设置",
                    status="等待",
                )
            ]
        else:
            self.script_info.user_list = [
                UserItem(
                    user_id=str(uid), name=config.get("Info", "Name"), status="等待"
                )
                for uid, config in self.user_config.items()
                if config.get("Info", "Status")
                and config.get("Info", "RemainedDay") != 0
                and self.task_info.is_target_user(str(uid))
            ]

    async def main_task(self):
        self.check_result = await self.check()
        if self.check_result != "Pass":
            logger.warning(f"未通过配置检查: {self.check_result}")
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=self.check_result),
            )
            return

        self.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await self.prepare()

        if self.task_info.mode == "ScriptConfig":
            self.script_info.current_index = 0
            await self.spawn(ScriptConfigTask(self.script_info, self.project))
            return

        # 同一安装的进程、日志文件是共享资源，用户必须串行执行
        for self.script_info.current_index in range(len(self.script_info.user_list)):
            method = AutoProxyTask(
                script_info=self.script_info,
                script_config=self.script_config,
                user_config=self.user_config,
                project=self.project,
            )
            sub_check = await method.check()
            if sub_check != "Pass":
                current_user = self.script_info.user_list[
                    self.script_info.current_index
                ]
                if current_user.status == "等待":
                    current_user.status = "异常"
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(level="error", message=sub_check),
                )
                continue
            await self.spawn(method)

    async def final_task(self):
        script_cfg = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]

        try:
            # 先解锁，再写回 UserData（load() 在锁定状态下会抛异常）
            if script_cfg.is_locked:
                await script_cfg.unlock()

            if self.check_result != "Pass":
                self.script_info.status = "异常"
                return

            if self.task_info.mode == "AutoProxy" and self.user_config is not None:
                await script_cfg.UserData.load(await self.user_config.toDict())
                await Config.ScriptConfig.save()

            if any(user.status == "异常" for user in self.script_info.user_list):
                self.script_info.status = "异常"
            else:
                self.script_info.status = "完成"

            if self.task_info.mode == "AutoProxy":
                await self._push_task_report()
        finally:
            if script_cfg.is_locked:
                with suppress(Exception):
                    await script_cfg.unlock()

    async def _push_task_report(self) -> None:
        error_count = sum(
            1 for user in self.script_info.user_list if user.status == "异常"
        )
        over_count = sum(
            1 for user in self.script_info.user_list if user.status == "完成"
        )
        wait_count = sum(
            1 for user in self.script_info.user_list if user.status == "等待"
        )
        task_mode = TASK_MODE_ZH[self.task_info.mode]
        has_uncompleted = error_count + wait_count > 0
        result = {
            "title": f"{task_mode}任务报告",
            "script_name": self.script_info.name or "空白",
            "start_time": self.begin_time,
            "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "completed_count": over_count,
            "uncompleted_count": error_count + wait_count,
            "result": build_user_result_text(
                self.script_info.user_list, has_uncompleted
            ),
        }
        try:
            await push_notification(
                mode="代理结果",
                title=(
                    f"{datetime.now().strftime('%m-%d')} | "
                    f"{self.script_info.name or '空白'}的{task_mode}任务报告"
                ),
                message=result,
                user_config=None,
                task_info=self.task_info,
            )
        except Exception as e:
            logger.opt(exception=True).warning(f"推送代理结果时出现异常: {e}")
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="error", message=f"推送代理结果时出现异常: {e}"
                ),
            )

    async def on_crash(self, e: Exception):
        self.script_info.status = "异常"
        logger.opt(exception=True).warning(f"OkScript 任务出现异常: {e}")

        with suppress(Exception):
            script_cfg = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
            if script_cfg.is_locked:
                await script_cfg.unlock()
            if self.task_info.mode == "AutoProxy" and self.user_config is not None:
                await script_cfg.UserData.load(await self.user_config.toDict())
                await Config.ScriptConfig.save()

        with suppress(Exception):
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="error", message=f"OkScript 任务出现异常: {e}"
                ),
            )
