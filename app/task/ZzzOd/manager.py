#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License
#   as published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from app.core import Config
from app.core.ws import Publisher, protocol
from app.models.config import ZzzOdConfig, ZzzOdUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, TaskExecuteBase, UserItem
from app.tools.push_log import build_user_result_text
from app.utils import get_logger
from app.utils.constants import TASK_MODE_ZH

from .AutoProxy import AutoProxyTask, find_launcher_exe
from .ScriptConfig import ScriptConfigTask
from .tools import push_notification

logger = get_logger("ZZZ-OD 调度器")


class ZzzOdManager(TaskExecuteBase):
    """ZZZ-OD 控制器（zzz-od 线）"""

    def __init__(self, script_info: ScriptItem):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.check_result = "-"
        self.user_config: MultipleConfig[ZzzOdUserConfig] | None = None
        self.begin_time = ""

    async def check(self) -> str:
        if self.task_info.mode not in ("AutoProxy", "ScriptConfig"):
            return "不支持的任务模式, 请检查任务配置！"

        script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        if not isinstance(script_config, ZzzOdConfig):
            return "脚本配置类型错误, 不是 ZZZ-OD 类型"

        root_path = Path(script_config.get("Info", "RootPath"))
        if not root_path.is_dir():
            return "请先设置有效的绝区零一条龙安装目录"
        try:
            find_launcher_exe(root_path)
        except ValueError as e:
            return str(e)

        if self.task_info.mode == "ScriptConfig":
            target_user_id = self.task_info.user_id or "Default"
            if target_user_id != "Default":
                try:
                    target_user_uid = uuid.UUID(target_user_id)
                except ValueError:
                    return "ZZZ-OD 用户不存在，请刷新后重试"
                if target_user_uid not in script_config.UserData:
                    return "ZZZ-OD 用户不存在，请刷新后重试"

        # AutoProxy 模式只做用户列表可用性校验；逐用户实例绑定检查放到 AutoProxyTask.check()
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
                    and self.task_info.is_target_user(str(uid))
                ]
            if not self.script_info.user_list:
                return "当前没有可执行的用户，请先添加并启用用户"

        return "Pass"

    async def prepare(self):
        script_uid = uuid.UUID(self.script_info.script_id)
        await Config.ScriptConfig[script_uid].lock()
        self.script_config = Config.ScriptConfig[script_uid]
        # 任务期使用独立副本，避免在 ScriptConfig 已锁时写 UserData（对齐 General）
        self.user_config = MultipleConfig([ZzzOdUserConfig])
        await self.user_config.load(await self.script_config.UserData.toDict())
        logger.success(f"{self.script_info.script_id} 已锁定，ZZZ-OD 用户配置已提取")

        if not isinstance(self.script_config, ZzzOdConfig):
            raise TypeError("脚本配置类型错误")

        if self.task_info.mode == "ScriptConfig":
            target_user_id = self.task_info.user_id or "Default"
            target_user_name = "ZZZ-OD 设置"
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
                and self.task_info.is_target_user(str(uid))
            ]

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

        if self.task_info.mode == "ScriptConfig":
            self.script_info.current_index = 0
            await self.spawn(
                ScriptConfigTask(
                    self.script_info,
                    self.script_config,
                    self.user_config,
                    view_only=self.task_info.view_only,
                    instance_idx=self.task_info.instance_idx,
                )
            )
            return

        # 按配置来源分派：用户模式 → 注入运行；直控模式 → 原生裸跑。
        # 直控用户绝不进入注入名单（直控=MAS 零注入零干涉）
        inject_users = [
            user
            for user in self.script_info.user_list
            if self.user_config[uuid.UUID(user.user_id)].get("Info", "Mode") != "直控"
        ]
        direct_users = [
            user
            for user in self.script_info.user_list
            if self.user_config[uuid.UUID(user.user_id)].get("Info", "Mode") == "直控"
        ]
        account_switch = str(
            self.script_config.get("Game", "AccountSwitch") or "单实例切换"
        )

        # 「多实例切换」（不推荐）：用户模式用户合并为一轮多账号注入运行
        # （一条龙内部切换账号），直控用户在其后逐个原生裸跑。
        # 失败域耦合：单槽失败/切换失败会终止整轮并全量重走（已完成任务按
        # 运行记录跳过，不重复执行，但会话重启与重新登录的代价仍在）
        if self.script_config.get("Game", "AccountSwitch") == "多实例切换":
            ran_any = False
            if inject_users:
                self.script_info.current_index = 0
                method = AutoProxyTask(
                    script_info=self.script_info,
                    script_config=self.script_config,
                    user_config=self.user_config,
                    users=inject_users,
                )
                sub_check = await method.check()
                if sub_check != "Pass":
                    for user in inject_users:
                        if user.status == "等待":
                            user.status = "异常"
                    await Publisher.send(
                        id=self.task_info.task_id,
                        type=protocol.TASK_NOTICE,
                        data=WSTaskNoticeData(level="error", message=sub_check),
                    )
                else:
                    ran_any = True
                    await self.spawn(method)
            for direct_user in direct_users:
                self.script_info.current_index = 0
                method = AutoProxyTask(
                    script_info=self.script_info,
                    script_config=self.script_config,
                    user_config=self.user_config,
                    users=[direct_user],
                )
                sub_check = await method.check()
                if sub_check != "Pass":
                    if direct_user.status == "等待":
                        direct_user.status = "异常"
                    await Publisher.send(
                        id=self.task_info.task_id,
                        type=protocol.TASK_NOTICE,
                        data=WSTaskNoticeData(level="error", message=sub_check),
                    )
                    continue
                ran_any = True
                await self.spawn(method)
            if not ran_any:
                self.check_result = "当前没有可执行的用户"
                self.script_info.status = "异常"
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(level="error", message=self.check_result),
                )
            return

        # 「MAS切换」（MAS 侧 OCR 操控游戏切号后交一条龙运行）暂未开放
        if account_switch == "MAS切换":
            self.check_result = "MAS切换暂未开放, 请改用单实例切换或多实例切换"
            self.script_info.status = "异常"
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=self.check_result),
            )
            return

        # 「单实例切换」（默认，推荐）：逐用户独立会话——注入该用户配置 →
        # 单实例运行（仅运行当前，无槽间切换）→ 跑完关闭 → 下一个用户。
        # 失败域隔离：某用户失败只重启该用户，不影响已完成的用户
        ran_any = False
        for self.script_info.current_index in range(len(self.script_info.user_list)):
            current_user = self.script_info.user_list[self.script_info.current_index]

            method = AutoProxyTask(
                script_info=self.script_info,
                script_config=self.script_config,
                user_config=self.user_config,
            )

            sub_check = await method.check()
            if sub_check != "Pass":
                if current_user.status == "等待":
                    current_user.status = "异常"
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(level="error", message=sub_check),
                )
                continue

            ran_any = True
            await self.spawn(method)

        if not ran_any:
            self.check_result = "当前没有可执行的用户"
            self.script_info.status = "异常"
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=self.check_result),
            )

    async def final_task(self):
        script_uid = uuid.UUID(self.script_info.script_id)
        script_cfg = Config.ScriptConfig[script_uid]

        try:
            # 先解锁，再写回 UserData（load() 在锁定状态下会抛异常）
            if script_cfg.is_locked:
                await script_cfg.unlock()

            if self.check_result != "Pass" and not any(
                user.status in ("完成", "跳过") for user in self.script_info.user_list
            ):
                # ScriptConfig 会话也可能产生绑定槽（Info.SlotIdx）写回
                if self.user_config is not None:
                    await script_cfg.UserData.load(await self.user_config.toDict())
                    await Config.ScriptConfig.save()
                self.script_info.status = "异常"
                return

            if self.user_config is not None:
                await script_cfg.UserData.load(await self.user_config.toDict())
                await Config.ScriptConfig.save()

            if any(user.status == "异常" for user in self.script_info.user_list):
                self.script_info.status = "异常"
            else:
                self.script_info.status = "完成"

            if self.task_info.mode == "AutoProxy":
                error_user = [
                    user.name
                    for user in self.script_info.user_list
                    if user.status == "异常"
                ]
                over_user = [
                    user.name
                    for user in self.script_info.user_list
                    if user.status == "完成"
                ]
                wait_user = [
                    user.name
                    for user in self.script_info.user_list
                    if user.status == "等待"
                ]
                task_mode = TASK_MODE_ZH[self.task_info.mode]
                title = (
                    f"{datetime.now().strftime('%m-%d')} | "
                    f"{self.script_info.name or '空白'}的{task_mode}任务报告"
                )
                # 按用户交错组装「用户结果行 + 任务节点详情」进报告正文
                # （ScriptItem.result 是只读计算属性，报告正文用局部变量承载）
                user_result_text = build_user_result_text(
                    self.script_info.user_list,
                    has_uncompleted=bool(error_user or wait_user),
                )
                result = {
                    "title": f"{task_mode}任务报告",
                    "script_name": self.script_info.name or "空白",
                    "start_time": self.begin_time,
                    "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "completed_count": len(over_user),
                    "uncompleted_count": len(error_user) + len(wait_user),
                    "result": user_result_text,
                }

                # 系统通知由 push_notification 内部的全局目标统一发送
                # （include_system=True），此处不再直接 push_plyer 以免重复
                try:
                    await push_notification(
                        mode="代理结果",
                        title=title,
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
                            level="error",
                            message=f"推送代理结果时出现异常: {e}",
                        ),
                    )
        finally:
            if script_cfg.is_locked:
                with suppress(Exception):
                    await script_cfg.unlock()

    async def on_crash(self, e: Exception):
        self.script_info.status = "异常"
        logger.opt(exception=True).warning(f"ZZZ-OD 任务出现异常: {e}")
        script_uid = uuid.UUID(self.script_info.script_id)

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
                data=WSTaskNoticeData(
                    level="error", message=f"ZZZ-OD 任务出现异常: {e}"
                ),
            )
