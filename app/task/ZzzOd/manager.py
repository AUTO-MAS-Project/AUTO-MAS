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

import app.core.notify.report as _node_report
from app.config import ConfigCollection, config_manager
from app.core import Config, Notify, Publisher
from app.core.ws import protocol
from app.models.config import ZzzOdConfig, ZzzOdUserConfig
from app.models.notification.report import TaskResultReport, UserReportText
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, UserItem
from app.task.manager_base import ScriptManagerBase
from app.utils import BASE_NATIVE, LOG_TYPE_ERROR, TASK_MODE_ZH, get_logger, log_box

from .AutoProxy import AutoProxyTask, find_launcher_exe
from .ScriptConfig import ScriptConfigTask

logger = get_logger("ZZZ-OD 调度器")


class ZzzOdManager(ScriptManagerBase):
    """ZZZ-OD 控制器（zzz-od 线）"""

    def __init__(self, script_info: ScriptItem):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.check_result = "-"
        self.user_config: ConfigCollection[ZzzOdUserConfig] | None = None

    async def check(self) -> str:
        if self.task_info.mode not in ("AutoProxy", "ScriptConfig"):
            return "不支持的任务模式, 请检查任务配置！"

        script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        if not isinstance(script_config, ZzzOdConfig):
            return "脚本配置类型错误, 不是 ZZZ-OD 类型"

        if not script_config.Info.RootPath:
            return "请先设置有效的绝区零一条龙安装目录"
        root_path = script_config.Info.RootPath
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
            if not self.script_info.user_list:
                self.script_info.user_list = self.build_proxy_user_list(
                    Config.ScriptConfig[script_uid].UserData.items()
                )
            if not self.script_info.user_list:
                return "当前没有可执行的用户，请先添加并启用用户"

        return "Pass"

    async def prepare(self):
        script_uid = uuid.UUID(self.script_info.script_id)
        self.config_locks[
            Config.ScriptConfig[script_uid].uid
        ] = await Config.ScriptConfig[script_uid].lock_x()
        self.script_config = Config.ScriptConfig[script_uid]
        if not isinstance(self.script_config, ZzzOdConfig):
            raise TypeError("脚本配置类型错误")

        # X 锁覆盖用户集合，运行时直接修改原配置。
        self.user_config = self.script_config.UserData
        logger.success(f"{self.script_info.script_id} 已锁定，ZZZ-OD 用户配置已提取")

        if self.task_info.mode == "ScriptConfig":
            target_user_id = self.task_info.user_id or "Default"
            target_user_name = "ZZZ-OD 设置"
            with suppress(ValueError):
                target_user_uid = uuid.UUID(target_user_id)
                if target_user_uid in self.user_config:
                    target_user_name = self.user_config[target_user_uid].Info.Name
            self.script_info.user_list = [
                UserItem(
                    user_id=target_user_id,
                    name=target_user_name,
                    status="等待",
                )
            ]
        else:
            self.script_info.user_list = self.build_proxy_user_list(
                self.user_config.items()
            )

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
        assert self.user_config is not None

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

        # 按 base 来源分派：shared/independent → 注入运行；native → 原生裸跑。
        # 原生来源用户绝不进入注入名单（原生来源=MAS 零注入零干涉）
        inject_users = [
            user
            for user in self.script_info.user_list
            if self.user_config[uuid.UUID(user.user_id)].Info.Base != BASE_NATIVE
        ]
        direct_users = [
            user
            for user in self.script_info.user_list
            if self.user_config[uuid.UUID(user.user_id)].Info.Base == BASE_NATIVE
        ]
        account_switch = str(self.script_config.Game.AccountSwitch or "单实例切换")

        # 「多实例切换」（不推荐）：注入模式用户合并为一轮多账号注入运行
        # （一条龙内部切换账号），原生来源用户在其后逐个原生裸跑。
        # 失败域耦合：单槽失败/切换失败会终止整轮并全量重走（已完成任务按
        # 运行记录跳过，不重复执行，但会话重启与重新登录的代价仍在）
        if self.script_config.Game.AccountSwitch == "多实例切换":
            inject_users = [
                user
                for user in inject_users
                if await self.check_user_before_run(
                    user, self.user_config[uuid.UUID(user.user_id)]
                )
            ]
            direct_users = [
                user
                for user in direct_users
                if await self.check_user_before_run(
                    user, self.user_config[uuid.UUID(user.user_id)]
                )
            ]
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
                    for user in inject_users[1:]:
                        self.record_user_run_start(user)
                    await self.run_user_task(inject_users[0], method)
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
                    await self.notify_user_check_failure(direct_user, sub_check)
                    continue
                ran_any = True
                await self.run_user_task(direct_user, method)
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
            if (
                self.task_info.mode == "AutoProxy"
                and not await self.check_user_before_run(
                    current_user, self.user_config[uuid.UUID(current_user.user_id)]
                )
            ):
                continue

            method = AutoProxyTask(
                script_info=self.script_info,
                script_config=self.script_config,
                user_config=self.user_config,
            )

            sub_check = await method.check()
            if sub_check != "Pass":
                await self.notify_user_check_failure(current_user, sub_check)
                continue

            ran_any = True
            await self.run_user_task(current_user, method)

        if not ran_any:
            self.check_result = "当前没有可执行的用户"
            self.script_info.status = "异常"
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=self.check_result),
            )

    async def final_task(self):
        try:
            if self.check_result != "Pass" and not any(
                user.status in ("完成", "跳过") for user in self.script_info.user_list
            ):
                # ScriptConfig 会话也可能产生绑定槽（Info.SlotIdx）写回
                if self.user_config is not None:
                    await config_manager.flush()
                self.script_info.status = "异常"
                return

            if self.user_config is not None:
                await config_manager.flush()

            if any(user.status == "异常" for user in self.script_info.user_list):
                self.script_info.status = "异常"
            else:
                self.script_info.status = "完成"

            if self.task_info.mode == "AutoProxy":
                summary = self.collect_user_results()
                task_mode = TASK_MODE_ZH[self.task_info.mode]
                title = (
                    f"{datetime.now().strftime('%m-%d')} | "
                    f"{self.script_info.name or '空白'}的{task_mode}任务报告"
                )
                # 按用户交错组装「用户结果行 + 任务节点详情」进报告正文
                # （ScriptItem.result 是只读计算属性，报告正文用局部变量承载）
                user_result_text = self._render_user_results(
                    has_uncompleted=summary.uncompleted_count > 0
                )
                # 报告正文整块镜像进调度台，未配置推送的用户也能看到节点详情
                if user_result_text:
                    self.script_info.log = (
                        f"{self.script_info.log}\n{user_result_text}"
                        if self.script_info.log
                        else user_result_text
                    )
                result = self.build_proxy_report(result_text=user_result_text)

                # 系统通知由宿主代理结果服务的全局目标统一发送。
                # （include_system=True），此处不再直接 push_plyer 以免重复
                try:
                    await Notify.push_proxy_result(
                        title=title,
                        report=TaskResultReport.from_message(result),
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
            script_config = getattr(self, "script_config", None)
            if script_config is not None:
                ticket = self.config_locks.pop(script_config.uid, None)
                if ticket is not None:
                    await script_config.unlock(ticket)

    async def on_crash(self, e: Exception):
        self.script_info.status = "异常"
        logger.opt(exception=True).warning(f"ZZZ-OD 任务出现异常: {e}")
        script_uid = uuid.UUID(self.script_info.script_id)

        try:
            script_cfg = Config.ScriptConfig[script_uid]
        except Exception:
            script_cfg = None

        if script_cfg is not None:
            try:
                if self.task_info.mode == "AutoProxy" and self.user_config is not None:
                    await config_manager.flush()
            except Exception:
                logger.opt(exception=True).warning("on_crash 保存用户配置失败")

        with suppress(Exception):
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="error", message=f"ZZZ-OD 任务出现异常: {e}"
                ),
            )

    def _render_user_results(self, *, has_uncompleted: bool) -> str:
        """本专项选择报告条目和展示模式，公共服务只负责排版。"""
        _report_rows = []
        for _report_user in self.script_info.user_list:
            _entries = [
                item
                if isinstance(item, log_box.LogEntry)
                else log_box.LogEntry.from_legacy(item)
                for item in _report_user.push_log
                if (item.log_type if isinstance(item, log_box.LogEntry) else item[0])
                != LOG_TYPE_ERROR
                or has_uncompleted
            ]
            _mode = getattr(_report_user, "push_log_mode", "逐条")
            if _mode == "关闭":
                _details = []
            elif _mode == "汇总":
                _details = _node_report.render_aggregate_push_log(_entries)
            else:
                _details = _node_report.render_scatter_push_log(_entries)
            _report_rows.append(
                UserReportText(
                    name=_report_user.name,
                    result=_report_user.result,
                    detail_lines=tuple(_details),
                )
            )
        return _node_report.render_user_result_text(_report_rows)
