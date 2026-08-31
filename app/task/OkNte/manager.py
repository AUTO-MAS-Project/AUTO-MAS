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
from app.models.config import OkNteConfig, OkNteUserConfig
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

logger = get_logger("OK-NTE 调度器")

METHOD_BOOK: dict[str, type[AutoProxyTask | ScriptConfigTask]] = {
    "AutoProxy": AutoProxyTask,
    "ScriptConfig": ScriptConfigTask,
}


class OkNteManager(TaskExecuteBase):
    """OK-NTE 控制器（ok-script 线）"""

    def __init__(self, script_info: ScriptItem):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.check_result = "-"
        self.temp_path: Path | None = None
        self.script_config_path: Path | None = None
        self.script_config: OkNteConfig | None = None
        self.user_config: MultipleConfig[OkNteUserConfig] | None = None
        self.game_manager: ProcessManager | None = None
        self.had_original_script_config = False
        self.crashed = False
        self.begin_time = ""

    async def check(self) -> str:
        if self.task_info.mode not in METHOD_BOOK:
            return "不支持的任务模式, 请检查任务配置！"

        script_uid = uuid.UUID(self.script_info.script_id)
        script_config = Config.ScriptConfig[script_uid]
        if not isinstance(script_config, OkNteConfig):
            return "脚本配置类型错误, 不是 OK-NTE 类型"

        if self.task_info.mode == "ScriptConfig":
            if not Path(script_config.get("Info", "RootPath")).is_dir():
                return "请设置 OK-NTE 脚本路径"
            if not Path(script_config.get("Script", "ScriptPath")).is_file():
                return "请设置 OK-NTE 脚本路径"
            if not str(script_config.get("Script", "ConfigPath") or "").strip():
                return "请设置 OK-NTE 配置路径"
            if self.task_info.user_id and self.task_info.user_id != "Default":
                try:
                    user_uid = uuid.UUID(self.task_info.user_id)
                except ValueError:
                    return "OK-NTE 用户不存在，请刷新后重试"
                if user_uid not in script_config.UserData:
                    return "OK-NTE 用户不存在，请刷新后重试"

        # AutoProxy 模式只做用户列表可用性校验；逐用户配置文件检查放到 AutoProxyTask.check()
        if self.task_info.mode == "AutoProxy":
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
        self.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        script_uid = uuid.UUID(self.script_info.script_id)
        await Config.ScriptConfig[script_uid].lock()
        script_config = Config.ScriptConfig[script_uid]
        if not isinstance(script_config, OkNteConfig):
            raise TypeError("脚本配置类型错误")

        self.script_config = script_config
        # 任务期使用独立副本，避免在 ScriptConfig 已锁时写 UserData（对齐 General）
        self.user_config = MultipleConfig([OkNteUserConfig])
        await self.user_config.load(await self.script_config.UserData.toDict())
        logger.success(f"{self.script_info.script_id} 已锁定，OK-NTE 用户配置已提取")

        if self.task_info.mode == "ScriptConfig":
            target_user_id = self.task_info.user_id or "Default"
            target_user_name = ""
            with suppress(ValueError):
                target_user_uid = uuid.UUID(target_user_id)
                if target_user_uid in self.user_config:
                    target_user_name = self.user_config[target_user_uid].get(
                        "Info", "Name"
                    )
            self.script_info.user_list = [
                UserItem(user_id=target_user_id, name=target_user_name, status="等待")
            ]
        else:
            # 构建用户列表：遍历脚本用户，筛选启用且剩余天数不为 0 的
            self.script_info.user_list = [
                UserItem(
                    user_id=str(uid), name=config.get("Info", "Name"), status="等待"
                )
                for uid, config in self.user_config.items()
                if config.get("Info", "Status")
                and config.get("Info", "RemainedDay") != 0
            ]

        # Enabled=游戏管理总开关；LaunchBeforeTask/CloseOnFinish=启动与收尾子项（可单独开启）
        self.game_manager = None
        if self.script_config.get("Game", "Enabled") and (
            self.script_config.get("Game", "LaunchBeforeTask")
            or self.script_config.get("Game", "CloseOnFinish")
        ):
            self.game_manager = ProcessManager()

        if self.task_info.mode in ("AutoProxy", "ScriptConfig"):
            self.script_config_path = Path(
                self.script_config.get("Script", "ConfigPath")
            )
            self.temp_path = Path.cwd() / f"data/{self.script_info.script_id}/Temp"
            shutil.rmtree(self.temp_path, ignore_errors=True)
            self.temp_path.mkdir(parents=True, exist_ok=True)
            if self.script_config_path.exists():
                self.had_original_script_config = True
                if self.script_config.get("Script", "ConfigPathMode") == "Folder":
                    shutil.copytree(
                        self.script_config_path, self.temp_path, dirs_exist_ok=True
                    )
                elif self.script_config.get("Script", "ConfigPathMode") == "File":
                    shutil.copy(self.script_config_path, self.temp_path / "config.temp")

    async def _restore_script_config_from_temp(self) -> None:
        if not (
            self.task_info.mode in ("AutoProxy", "ScriptConfig")
            and self.temp_path
            and self.temp_path.exists()
            and self.script_config_path
            and self.script_config
        ):
            return
        if self.script_config.get("Script", "ConfigPathMode") == "Folder":
            if not self.had_original_script_config:
                logger.info(
                    f"清理任务期写入的 OK-NTE 脚本配置目录: {self.script_config_path}"
                )
                shutil.rmtree(self.script_config_path, ignore_errors=True)
            else:
                logger.info(f"复原 OK-NTE 脚本配置文件: {self.temp_path}")
                tmp_dst = self.script_config_path.with_name(
                    self.script_config_path.name + ".tmp"
                )
                shutil.rmtree(tmp_dst, ignore_errors=True)
                shutil.copytree(self.temp_path, tmp_dst, dirs_exist_ok=True)
                shutil.rmtree(self.script_config_path, ignore_errors=True)
                tmp_dst.rename(self.script_config_path)
        elif self.script_config.get("Script", "ConfigPathMode") == "File":
            if (self.temp_path / "config.temp").exists():
                logger.info(
                    f"复原 OK-NTE 脚本配置文件: {self.temp_path / 'config.temp'}"
                )
                shutil.copy(self.temp_path / "config.temp", self.script_config_path)
            elif not self.had_original_script_config:
                logger.info(
                    f"清理任务期写入的 OK-NTE 脚本配置文件: {self.script_config_path}"
                )
                with suppress(FileNotFoundError):
                    self.script_config_path.unlink()
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

        await self.prepare()
        if self.script_config is None or self.user_config is None:
            raise RuntimeError("OK-NTE 用户配置未完成初始化")

        method_cls = METHOD_BOOK[self.task_info.mode]
        for self.script_info.current_index in range(len(self.script_info.user_list)):
            method = method_cls(
                script_info=self.script_info,
                script_config=self.script_config,  # type: ignore[arg-type]
                user_config=self.user_config,  # type: ignore[arg-type]
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

            await self.spawn(method)

    async def final_task(self):
        script_uid = uuid.UUID(self.script_info.script_id)
        script_cfg = Config.ScriptConfig[script_uid]

        try:
            await self._restore_script_config_from_temp()

            # 先解锁，再写回 UserData（load() 在锁定状态下会抛异常）
            if script_cfg.is_locked:
                await script_cfg.unlock()

            if self.task_info.mode == "AutoProxy" and self.user_config is not None:
                await script_cfg.UserData.load(await self.user_config.toDict())

            if self.crashed:
                self.script_info.status = "异常"
                return

            if self.check_result != "Pass" and not any(
                user.status == "完成" for user in self.script_info.user_list
            ):
                self.script_info.status = "异常"
                return

            if any(user.status == "异常" for user in self.script_info.user_list):
                self.script_info.status = "异常"
            else:
                self.script_info.status = "完成"

            if self.task_info.mode == "AutoProxy":
                error_user = [
                    u.name for u in self.script_info.user_list if u.status == "异常"
                ]
                over_user = [
                    u.name for u in self.script_info.user_list if u.status == "完成"
                ]
                wait_user = [
                    u.name for u in self.script_info.user_list if u.status == "等待"
                ]

                title = f"{datetime.now().strftime('%m-%d')} | {self.script_info.name or '空白'}的{TASK_MODE_ZH[self.task_info.mode]}任务报告"
                # 按用户交错组装「用户结果行 + 该用户节点详情」：
                # 多账号任务时各用户节点归属清晰，不再全部平铺。
                # 「失败」类型仅在本次任务存在未完成用户时纳入报告，
                # 与 SendTaskResultTime 的「仅失败时」推送策略自然配合（对齐 ok-ww/通用脚本）。
                # 关闭「是否采集节点详情」的用户在 AutoProxy 侧未启 log_box，push_log
                # 为空，自然只有结果行。
                has_uncompleted = len(error_user) + len(wait_user) > 0
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
                    "completed_count": len(over_user),
                    "uncompleted_count": len(error_user) + len(wait_user),
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

    async def on_crash(self, e: Exception):
        self.crashed = True
        self.script_info.status = "异常"
        logger.opt(exception=True).warning(f"OK-NTE任务出现异常: {e}")
        script_uid = uuid.UUID(self.script_info.script_id)

        await self._restore_script_config_from_temp()

        # 先解锁，再写回 UserData（load() 在锁定状态下会抛异常）
        script_cfg = Config.ScriptConfig[script_uid]
        if script_cfg.is_locked:
            with suppress(Exception):
                await script_cfg.unlock()

        try:
            if self.task_info.mode == "AutoProxy" and self.user_config is not None:
                await script_cfg.UserData.load(await self.user_config.toDict())
        except Exception:
            logger.opt(exception=True).warning(
                "on_crash 写回 UserConfig 失败，放弃本次状态变更"
            )
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=f"OK-NTE任务出现异常: {e}"),
        )
