#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

import shutil
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from app.core import Config
from app.core.ws import Publisher, protocol
from app.models.config import OkwwConfig, OkwwUserConfig
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

from .AutoProxy import (
    _OKWW_REL_APP_JSON,
    _OKWW_REL_CONFIG_DIR,
    _OKWW_REL_EXE,
    AutoProxyTask,
    _okww_config_mode,
)
from .ScriptConfig import ScriptConfigTask
from .tools import push_notification
from .Update import WuwaUpdateTask

logger = get_logger("OK-WW 调度器")


class OkwwManager(TaskExecuteBase):
    """OK-WW 控制器（ok-script 线）"""

    def __init__(self, script_info: ScriptItem):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.check_result = "-"
        self.user_config: MultipleConfig[OkwwUserConfig] | None = None
        self.temp_path: Path | None = None
        self.script_config_path: Path | None = None
        self.had_original_script_config = False
        self.script_config_mode = "脚本"
        self.begin_time = ""

    async def check(self) -> str:
        if self.task_info.mode not in ("AutoProxy", "ScriptConfig", "Update"):
            return "不支持的任务模式, 请检查任务配置！"

        script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        if not isinstance(script_config, OkwwConfig):
            return "脚本配置类型错误, 不是 OK-WW 类型"

        if self.task_info.mode == "ScriptConfig":
            root_path = Path(script_config.get("Info", "RootPath"))
            if (
                not root_path.is_dir()
                or not (root_path / _OKWW_REL_EXE).is_file()
                or not (root_path / _OKWW_REL_APP_JSON).is_file()
            ):
                return "请先设置有效的 OK-WW 脚本路径"

        if self.task_info.mode in ("ScriptConfig", "Update"):
            target_user_id = self.task_info.user_id or "Default"
            if target_user_id != "Default":
                try:
                    target_user_uid = uuid.UUID(target_user_id)
                except ValueError:
                    return "OK-WW 用户不存在，请刷新后重试"
                if target_user_uid not in script_config.UserData:
                    return "OK-WW 用户不存在，请刷新后重试"

        if self.task_info.mode == "Update":
            if not script_config.get("Game", "Enabled"):
                return "请先在脚本配置中启用游戏配置"
            launcher = Path(str(script_config.get("Game", "Path") or "").strip())
            if not launcher.is_file():
                return "请先在脚本配置中导入有效的鸣潮官方启动器"

        # AutoProxy 模式只做用户列表可用性校验；逐用户配置文件检查放到 AutoProxyTask.check()
        if self.task_info.mode == "AutoProxy":
            script_uid = uuid.UUID(self.script_info.script_id)
            if (not self.script_info.user_list) or (
                self.script_info.user_list
                and self.script_info.user_list[0].name == "暂未加载"
            ):
                self.script_info.user_list = [
                    UserItem(
                        user_id=str(uid), name=config.get("Info", "Name"), status="等待"
                    )
                    for uid, config in Config.ScriptConfig[script_uid].UserData.items()
                    if config.get("Info", "Status")
                    and config.get("Info", "RemainedDay") != 0
                ]
            if not self.script_info.user_list:
                return "当前没有可执行的用户，请先添加并启用用户"

        return "Pass"

    async def prepare(self):
        script_uid = uuid.UUID(self.script_info.script_id)
        await Config.ScriptConfig[script_uid].lock()
        self.script_config = Config.ScriptConfig[script_uid]
        # 任务期使用独立副本，避免在 ScriptConfig 已锁时写 UserData（对齐 General）
        self.user_config = MultipleConfig([OkwwUserConfig])
        await self.user_config.load(await self.script_config.UserData.toDict())
        logger.success(f"{self.script_info.script_id} 已锁定，OK-WW 用户配置已提取")

        if not isinstance(self.script_config, OkwwConfig):
            raise TypeError("脚本配置类型错误")

        if self.task_info.mode == "Update":
            target_user_id = self.task_info.user_id or "Default"
            target_user_name = "OK-WW 更新"
            with suppress(ValueError):
                target_user_uid = uuid.UUID(target_user_id)
                if target_user_uid in self.user_config:
                    target_user_name = self.user_config[target_user_uid].get(
                        "Info", "Name"
                    )
            self.script_info.user_list = [
                UserItem(
                    user_id=target_user_id,
                    name=target_user_name,
                    status="等待",
                )
            ]
        elif self.task_info.mode == "ScriptConfig":
            target_user_id = self.task_info.user_id or "Default"
            target_user_name = "OK-WW 设置"
            with suppress(ValueError):
                target_user_uid = uuid.UUID(target_user_id)
                if target_user_uid in self.user_config:
                    target_user_name = self.user_config[target_user_uid].get(
                        "Info", "Name"
                    )
            self.script_info.user_list = [
                UserItem(
                    user_id=target_user_id,
                    name=target_user_name,
                    status="等待",
                )
            ]
            if target_user_id != "Default":
                self.script_config_mode = _okww_config_mode(
                    self.user_config[uuid.UUID(target_user_id)].get("Info", "Mode")
                )
        else:
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

        # Enabled=游戏管理总开关；开启后任务前始终启动游戏，任务结束/失败时始终关闭游戏
        self.game_manager: ProcessManager | None = None
        if self.task_info.mode == "AutoProxy" and self.script_config.get(
            "Game", "Enabled"
        ):
            self.game_manager = ProcessManager()

        if self.task_info.mode in ("AutoProxy", "ScriptConfig"):
            self.script_config_path = (
                Path(self.script_config.get("Info", "RootPath")) / _OKWW_REL_CONFIG_DIR
            )
            self.temp_path = Path.cwd() / f"data/{self.script_info.script_id}/Temp"
            shutil.rmtree(self.temp_path, ignore_errors=True)
            self.temp_path.mkdir(parents=True, exist_ok=True)
            if self.script_config_path.exists():
                self.had_original_script_config = True
                shutil.copytree(
                    self.script_config_path, self.temp_path, dirs_exist_ok=True
                )

    async def _restore_script_config_from_temp(self) -> None:
        if not (
            self.task_info.mode in ("AutoProxy", "ScriptConfig")
            and self.temp_path
            and self.temp_path.exists()
            and self.script_config_path
        ):
            return
        if not self.had_original_script_config:
            logger.info(
                f"清理任务期写入的 OK-WW 脚本配置目录: {self.script_config_path}"
            )
            shutil.rmtree(self.script_config_path, ignore_errors=True)
        else:
            logger.info(f"复原 OK-WW 脚本配置文件: {self.temp_path}")
            tmp_dst = self.script_config_path.with_name(
                self.script_config_path.name + ".tmp"
            )
            shutil.rmtree(tmp_dst, ignore_errors=True)
            shutil.copytree(self.temp_path, tmp_dst, dirs_exist_ok=True)
            shutil.rmtree(self.script_config_path, ignore_errors=True)
            tmp_dst.rename(self.script_config_path)

    def _cleanup_script_config_temp(self) -> None:
        if self.temp_path:
            shutil.rmtree(self.temp_path, ignore_errors=True)

    async def main_task(self):
        self.check_result = await self.check()
        if self.check_result != "Pass":
            self.script_info.status = "异常"
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=self.check_result),
            )
            return

        self.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await self.prepare()

        if self.task_info.mode == "Update":
            self.script_info.current_index = 0
            target_user_id = self.task_info.user_id or "Default"
            resource = str(
                self.user_config[uuid.UUID(target_user_id)].get("Info", "Resource")
            )
            await self.spawn(
                WuwaUpdateTask(
                    self.script_info,
                    self.script_config,
                    resource,
                )
            )
            return

        if self.task_info.mode == "ScriptConfig":
            self.script_info.current_index = 0
            await self.spawn(
                ScriptConfigTask(
                    self.script_info,
                    self.script_config,
                    self.user_config,
                )
            )
            return

        for self.script_info.current_index in range(len(self.script_info.user_list)):
            current_user = self.script_info.user_list[self.script_info.current_index]
            current_config = self.user_config[uuid.UUID(current_user.user_id)]
            config_mode = _okww_config_mode(current_config.get("Info", "Mode"))
            logger.info(f"用户 {current_user.user_id} 配置来源: {config_mode}")
            if config_mode == "直控":
                await self._restore_script_config_from_temp()

            method = AutoProxyTask(
                script_info=self.script_info,
                script_config=self.script_config,
                user_config=self.user_config,
                game_manager=self.game_manager,
            )

            sub_check = await method.check()
            if sub_check != "Pass":
                self.check_result = sub_check
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

            # OK-WW 的工作目录、脚本进程和日志文件属于安装级共享资源，用户必须串行执行。
            try:
                await self.spawn(method)
            finally:
                # 每个用户任务结束后立即恢复快照，快速配置不得残留到脚本原配置。
                await self._restore_script_config_from_temp()

    async def final_task(self):
        script_uid = uuid.UUID(self.script_info.script_id)
        script_cfg = Config.ScriptConfig[script_uid]

        try:
            if not self._keep_script_config_changes():
                await self._restore_script_config_from_temp()
            else:
                logger.info("直控配置会话成功，保留脚本原生配置")
            self._cleanup_script_config_temp()

            # 先解锁，再写回 UserData（load() 在锁定状态下会抛异常）
            if script_cfg.is_locked:
                await script_cfg.unlock()

            if self.check_result != "Pass" and not any(
                user.status in ("完成", "跳过") for user in self.script_info.user_list
            ):
                if self.task_info.mode == "AutoProxy" and self.user_config is not None:
                    await script_cfg.UserData.load(await self.user_config.toDict())
                    await Config.ScriptConfig.save()
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
                title = (
                    f"{datetime.now().strftime('%m-%d')} | "
                    f"{self.script_info.name or '空白'}的{task_mode}任务报告"
                )
                # 按用户交错组装「用户结果行 + 该用户节点详情」：
                # 多账号任务时各用户节点归属清晰，不再全部平铺。
                # 「失败」类型仅在本次任务存在未完成用户时纳入报告，
                # 与 SendTaskResultTime 的「仅失败时」推送策略自然配合（对齐通用脚本）。
                # 关闭「是否采集节点详情」的用户在 AutoProxy 侧未启 log_box，
                # push_log 为空，自然只有结果行。
                has_uncompleted = error_count + wait_count > 0
                user_result_text = build_user_result_text(
                    self.script_info.user_list, has_uncompleted
                )
                task_result = append_task_game_sign_summary(
                    self.task_info, user_result_text
                )
                has_game_sign_summary = task_result != user_result_text
                result = {
                    "title": f"{task_mode}任务报告",
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
                            level="error",
                            message=f"推送代理结果时出现异常: {e}",
                        ),
                    )
        finally:
            if script_cfg.is_locked:
                with suppress(Exception):
                    await script_cfg.unlock()

    def _keep_script_config_changes(self) -> bool:
        """直控配置会话成功后保留脚本原生 GUI 写回的配置。"""

        return (
            self.task_info.mode == "ScriptConfig"
            and self.script_config_mode == "直控"
            and bool(self.script_info.user_list)
            and self.script_info.user_list[0].status == "完成"
        )

    async def on_crash(self, e: Exception):
        self.script_info.status = "异常"
        logger.opt(exception=True).warning(f"OK-WW任务出现异常: {e}")
        script_uid = uuid.UUID(self.script_info.script_id)

        with suppress(Exception):
            await self._restore_script_config_from_temp()
        self._cleanup_script_config_temp()

        try:
            script_cfg = Config.ScriptConfig[script_uid]
        except Exception:
            script_cfg = None

        if script_cfg is not None:
            if script_cfg.is_locked:
                with suppress(Exception):
                    await script_cfg.unlock()

            try:
                if self.task_info.mode == "AutoProxy" and self.user_config is not None:
                    await script_cfg.UserData.load(await self.user_config.toDict())
                    await Config.ScriptConfig.save()
            except Exception:
                logger.opt(exception=True).warning(
                    "on_crash 写回 UserConfig 失败，放弃本次状态变更"
                )

        with suppress(Exception):
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=f"OK-WW任务出现异常: {e}"),
            )
