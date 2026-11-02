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

"""BAAH 控制器。

按用户逐个拉起 BAAH 自动代理任务，结束时统一组装任务报告并推送。
"""

import uuid
from datetime import datetime

import app.core.notify.report as _node_report
from app.config import config_manager
from app.core import Config, EmulatorManager, Notify, Publisher
from app.core.ws import protocol
from app.models.config import BAAHConfig
from app.models.emulator import DeviceBase, DeviceProvider
from app.models.notification.report import TaskResultReport, UserReportText
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem
from app.task.emulator_core import close_emulator
from app.task.manager_base import ScriptManagerBase
from app.utils import LOG_TYPE_ERROR, TASK_MODE_ZH, get_logger, log_box

from .AutoProxy import AutoProxyTask

logger = get_logger("BAAH 调度器")

METHOD_BOOK: dict[str, type[AutoProxyTask]] = {
    "AutoProxy": AutoProxyTask,
}


class BAAHManager(ScriptManagerBase):
    """BAAH 控制器"""

    def __init__(
        self,
        script_info: ScriptItem,
        *,
        device_provider: DeviceProvider | None = None,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.check_result = "-"
        self.emulator_manager: DeviceBase | None = None
        self._device_provider = device_provider

    async def check(self) -> str:
        """校验 BAAH 脚本配置是否可用"""

        if self.task_info.mode not in METHOD_BOOK:
            return "不支持的任务模式, 请检查任务配置！"

        script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        if not isinstance(script_config, BAAHConfig):
            return "脚本配置类型错误, 不是 BAAH 脚本类型"

        if script_config.Emulator.Id == "-" or script_config.Emulator.Index in [
            "",
            "-",
        ]:
            return "未完成模拟器配置, 请检查脚本配置中的模拟器设置！"

        ## 程序目录、配置目录与日志目录都由 BAAHPath 派生，只需校验它
        if not str(script_config.Script.BAAHPath or "").strip():
            return "未填写 BAAH 主程序路径, 请检查脚本配置中的主程序路径设置！"

        return "Pass"

    async def prepare(self):
        """运行前准备"""

        self.config_locks[
            Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].uid
        ] = await Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].lock_x()
        self.script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        self.user_config = self.script_config.UserData
        logger.success(f"{self.script_info.script_id} 已锁定, BAAH 脚本配置提取完成")

        self.script_info.user_list = self.build_proxy_user_list(
            self.user_config.items()
        )
        logger.info(
            f"用户列表加载完成, 已筛选用户数: {len(self.script_info.user_list)}"
        )

        # 初始化模拟器管理器：模拟器的启动与关闭统一由本软件调度,
        # BAAH 自身不再负责拉起模拟器
        device_provider = self._device_provider or EmulatorManager.get_emulator_instance
        self.emulator_manager: DeviceBase = await device_provider(
            self.script_config.Emulator.Id
        )

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

        if not isinstance(self.script_config, BAAHConfig):
            raise RuntimeError("脚本配置类型错误, 不是 BAAH 脚本类型")

        for self.script_info.current_index in range(len(self.script_info.user_list)):
            current_user = self.script_info.user_list[self.script_info.current_index]
            if (
                self.task_info.mode == "AutoProxy"
                and not await self.check_user_before_run(
                    current_user, self.user_config[uuid.UUID(current_user.user_id)]
                )
            ):
                continue
            task = METHOD_BOOK[self.task_info.mode](
                self.script_info,
                self.script_config,
                self.user_config,
                self.emulator_manager,
            )
            await self.run_user_task(current_user, task)

    async def final_task(self):
        """运行结束后的收尾工作"""
        try:
            if self.check_result != "Pass":
                self.script_info.status = "异常"
                return self.check_result

            logger.info("BAAH 任务已结束, 开始执行后续操作")

            if self.task_info.mode == "AutoProxy":
                await close_emulator(self)
                await config_manager.flush()

                summary = self.collect_user_results()

                title = (
                    f"{datetime.now().strftime('%m-%d')} | "
                    f"{self.script_info.name or '空白'}的"
                    f"{TASK_MODE_ZH[self.task_info.mode]}任务报告"
                )
                ## 按用户交错组装「用户结果行 + 该用户节点详情」，
                ## 失败类型条目仅在本次任务存在未完成用户时纳入报告
                has_uncompleted = summary.uncompleted_count > 0
                user_result_text = self._render_user_results(
                    has_uncompleted=has_uncompleted
                )
                # 报告正文整块镜像进调度台，未配置推送的用户也能看到节点详情
                if user_result_text:
                    self.script_info.log = (
                        f"{self.script_info.log}\n{user_result_text}"
                        if self.script_info.log
                        else user_result_text
                    )
                result = self.build_proxy_report(result_text=user_result_text)

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
                            level="error", message=f"推送代理结果时出现异常: {e}"
                        ),
                    )

            self.script_info.status = "完成"
        finally:
            script_config = getattr(self, "script_config", None)
            if script_config is not None:
                ticket = self.config_locks.pop(script_config.uid, None)
                if ticket is not None:
                    await script_config.unlock(ticket)

    async def on_crash(self, e: Exception):

        self.script_info.status = "异常"
        logger.opt(exception=True).warning(f"BAAH 任务出现异常: {e}")
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=f"BAAH 任务出现异常: {e}"),
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
