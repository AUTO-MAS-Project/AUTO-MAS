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


import shutil
import uuid
from datetime import datetime
from pathlib import Path

from app.core import Config, EmulatorManager
from app.core.ws import Publisher, protocol
from app.models.config import GeneralConfig, GeneralUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, TaskExecuteBase, UserItem
from app.tools.game_sign_notify import (
    append_task_game_sign_summary,
    finalize_task_game_sign_notification,
)
from app.tools.push_log import build_user_result_text
from app.utils import ProcessManager, get_logger
from app.utils.constants import TASK_MODE_ZH

from .AutoProxy import AutoProxyTask
from .ScriptConfig import ScriptConfigTask
from .tools import push_notification

logger = get_logger("通用调度器")

METHOD_BOOK: dict[str, type[AutoProxyTask | ScriptConfigTask]] = {
    "AutoProxy": AutoProxyTask,
    "ScriptConfig": ScriptConfigTask,
}


class GeneralManager(TaskExecuteBase):
    """通用脚本控制器"""

    def __init__(self, script_info: ScriptItem):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.check_result = "-"
        self.external_config_exists = False
        self.external_config_snapshot_ready = False

    async def check(self) -> str:
        """校验通用脚本配置是否可用"""
        if self.task_info.mode not in METHOD_BOOK:
            return "不支持的任务模式, 请检查任务配置！"
        if not isinstance(
            Config.ScriptConfig[uuid.UUID(self.script_info.script_id)], GeneralConfig
        ):
            return "脚本配置类型错误, 不是通用脚本类型"
        if (
            Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                "Script", "IfTrackProcess"
            )
            and not Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                "Script", "TrackProcessName"
            )
            and not Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                "Script", "TrackProcessExe"
            )
            and not Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                "Script", "TrackProcessCmdline"
            )
        ):
            return "开启追踪子进程后, 需至少填写一项追踪进程信息！"
        if Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
            "Game", "Enabled"
        ):
            if (
                Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                    "Game", "Type"
                )
                == "Emulator"
            ) and (
                Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                    "Game", "EmulatorId"
                )
                == "-"
                or Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                    "Game", "EmulatorIndex"
                )
                in ["", "-"]
            ):
                return "未完成模拟器配置, 请检查脚本配置中的模拟器设置！"
            elif (
                Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                    "Game", "Type"
                )
                == "Client"
            ) and not Path(
                Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                    "Game", "Path"
                )
            ).exists():
                return "未完成游戏配置, 请检查脚本配置中的游戏设置！"
            elif (
                Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                    "Game", "Type"
                )
                == "URL"
            ) and (
                not Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                    "Game", "URL"
                )
                or not Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                    "Game", "ProcessName"
                )
            ):
                return "未完成URL配置, 请检查脚本配置中的URL和进程名称设置！"

        return "Pass"

    def _remove_script_config(self) -> None:
        """清理脚本当前配置路径，避免不同来源的目录文件互相残留。"""
        if self.script_config_path.is_dir():
            shutil.rmtree(self.script_config_path)
        elif self.script_config_path.exists():
            self.script_config_path.unlink()

    def _snapshot_external_config(self) -> None:
        """保存脚本直控配置，作为用户切换和任务结束时的恢复基线。"""
        shutil.rmtree(self.temp_path, ignore_errors=True)
        self.external_config_exists = self.script_config_path.exists()
        self.temp_path.mkdir(parents=True, exist_ok=True)

        if self.external_config_exists:
            if self.script_config.get("Script", "ConfigPathMode") == "Folder":
                shutil.copytree(
                    self.script_config_path, self.temp_path, dirs_exist_ok=True
                )
            elif self.script_config.get("Script", "ConfigPathMode") == "File":
                shutil.copy(self.script_config_path, self.temp_path / "config.temp")

        self.external_config_snapshot_ready = True

    def _restore_external_config(self) -> None:
        """恢复脚本直控配置，隔离 MAS 用户配置的运行结果。"""
        if not self.external_config_snapshot_ready:
            return

        self._remove_script_config()
        if not self.external_config_exists:
            logger.info("脚本直控配置不存在，保持配置路径为空")
            return

        if self.script_config.get("Script", "ConfigPathMode") == "Folder":
            shutil.copytree(self.temp_path, self.script_config_path, dirs_exist_ok=True)
        elif self.script_config.get("Script", "ConfigPathMode") == "File":
            self.script_config_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(self.temp_path / "config.temp", self.script_config_path)

    def _cleanup_external_config_snapshot(self) -> None:
        if not self.external_config_snapshot_ready:
            return
        shutil.rmtree(self.temp_path, ignore_errors=True)
        self.external_config_snapshot_ready = False

    def _user_uses_mas_config(self) -> bool:
        user_id = self.script_info.user_list[self.script_info.current_index].user_id
        if user_id == "Default":
            return True
        return bool(self.user_config[uuid.UUID(user_id)].get("Info", "IfUseMasConfig"))

    async def prepare(self):
        """运行前准备"""

        # 锁定脚本配置并加载用户配置
        await Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].lock()
        self.script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        self.user_config = MultipleConfig([GeneralUserConfig])
        await self.user_config.load(await self.script_config.UserData.toDict())
        logger.success(f"{self.script_info.script_id}已锁定, 通用脚本配置提取完成")

        self.script_config_path = Path(self.script_config.get("Script", "ConfigPath"))
        self.temp_path = Path.cwd() / f"data/{self.script_info.script_id}/Temp"

        if Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
            "Game", "Enabled"
        ):
            if (
                Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                    "Game", "Type"
                )
                == "Emulator"
            ):
                self.emulator_manager = await EmulatorManager.get_emulator_instance(
                    self.script_config.get("Game", "EmulatorId")
                )

            elif Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                "Game", "Type"
            ) in ["Client", "URL"]:
                self.game_process_manager = ProcessManager()

        # 构建用户列表
        if self.task_info.mode == "ScriptConfig":
            self.script_info.user_list = [
                UserItem(
                    user_id=self.task_info.user_id or "Default", name="", status="等待"
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
            ]
        logger.info(
            f"用户列表加载完成, 已筛选用户数: {len(self.script_info.user_list)}"
        )

        logger.info(f"记录脚本直控配置: {self.script_config_path}")
        self._snapshot_external_config()

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

        if not isinstance(self.script_config, GeneralConfig):
            raise RuntimeError("脚本配置类型错误, 不是通用脚本类型")

        for self.script_info.current_index in range(len(self.script_info.user_list)):
            use_mas_config = self._user_uses_mas_config()
            user_id = self.script_info.user_list[self.script_info.current_index].user_id
            logger.info(
                f"用户 {user_id} 配置来源: "
                f"{'MAS 独立配置' if use_mas_config else '脚本直控配置'}"
            )
            if not use_mas_config:
                self._restore_external_config()

            task = METHOD_BOOK[self.task_info.mode](
                self.script_info,
                self.script_config,
                self.user_config,
                (
                    (
                        self.emulator_manager
                        if (self.script_config.get("Game", "Type") == "Emulator")
                        else self.game_process_manager
                    )
                    if self.script_config.get("Game", "Enabled")
                    else None
                ),
            )

            try:
                await self.spawn(task)
            finally:
                if not use_mas_config:
                    self._snapshot_external_config()

    async def final_task(self):
        """运行结束后的收尾工作"""

        if self.check_result != "Pass":
            self.script_info.status = "异常"
            return self.check_result

        logger.info("通用脚本任务已结束, 开始执行后续操作")

        self._restore_external_config()
        self._cleanup_external_config_snapshot()

        await Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].unlock()
        logger.success(f"已解锁脚本配置 {self.script_info.script_id}")

        if self.task_info.mode == "AutoProxy":
            await Config.ScriptConfig[
                uuid.UUID(self.script_info.script_id)
            ].UserData.load(await self.user_config.toDict())
            await Config.ScriptConfig.save()

            error_count = sum(
                1 for u in self.script_info.user_list if u.status == "异常"
            )
            over_count = sum(
                1 for u in self.script_info.user_list if u.status == "完成"
            )
            wait_count = sum(
                1 for u in self.script_info.user_list if u.status == "等待"
            )

            title = f"{datetime.now().strftime('%m-%d')} | {self.script_info.name or '空白'}的{TASK_MODE_ZH[self.task_info.mode]}任务报告"
            # 按用户交错组装「用户结果行 + 该用户进程信息」：
            # 多账号任务时各用户信息归属清晰，不再全部平铺。
            # 「失败」类型条目仅在本次任务存在未完成用户时纳入报告，
            # 与 SendTaskResultTime 的「仅失败时」推送策略自然配合
            has_uncompleted = error_count + wait_count > 0
            user_result_text = build_user_result_text(
                self.script_info.user_list, has_uncompleted
            )
            task_result = append_task_game_sign_summary(
                self.task_info, user_result_text
            )
            has_game_sign_summary = task_result != user_result_text
            result = {
                "title": f"{TASK_MODE_ZH[self.task_info.mode]}任务报告",
                "script_name": self.script_info.name or "空白",
                "start_time": self.begin_time,
                "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "completed_count": over_count,
                "uncompleted_count": error_count + wait_count,
                "result": task_result,
                "game_sign_summary": has_game_sign_summary,
            }

            try:
                push_result = await push_notification(
                    mode="代理结果",
                    title=title,
                    message=result,
                    user_config=None,
                    task_info=self.task_info,
                )
                finalize_task_game_sign_notification(
                    self.task_info, has_game_sign_summary, push_result
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

        self.script_info.status = "完成"

    async def on_crash(self, e: Exception):

        self.script_info.status = "异常"
        logger.opt(exception=True).warning(f"通用脚本任务出现异常: {e}")
        try:
            self._restore_external_config()
            self._cleanup_external_config_snapshot()
        except Exception as restore_error:
            logger.opt(exception=True).warning(f"恢复脚本直控配置失败: {restore_error}")
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=f"通用脚本任务出现异常: {e}"),
        )
