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
from contextlib import suppress
from datetime import datetime
from pathlib import Path

import app.core.notify.report as _node_report
from app.config import config_manager
from app.core import Config, EmulatorManager, Notify, Publisher
from app.core.ws import protocol
from app.models.config import GeneralConfig
from app.models.emulator import DeviceProvider
from app.models.notification.report import TaskResultReport, UserReportText
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, UserItem
from app.task.manager_base import ScriptManagerBase
from app.task.proxy_helpers import CONFIG_BASE_NATIVE, read_config_base
from app.utils import LOG_TYPE_ERROR, TASK_MODE_ZH, ProcessManager, get_logger, log_box
from app.utils import io as _utils_io

from .AutoProxy import AutoProxyTask
from .ScriptConfig import ScriptConfigTask

logger = get_logger("通用调度器")

METHOD_BOOK: dict[str, type[AutoProxyTask | ScriptConfigTask]] = {
    "AutoProxy": AutoProxyTask,
    "ScriptConfig": ScriptConfigTask,
}


class GeneralManager(ScriptManagerBase):
    """通用脚本控制器"""

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
        self.external_config_exists = False
        self.external_config_snapshot_ready = False
        self._device_provider = device_provider

    async def check(self) -> str:
        """校验通用脚本配置是否可用"""
        if self.task_info.mode not in METHOD_BOOK:
            return "不支持的任务模式, 请检查任务配置！"
        if not isinstance(
            Config.ScriptConfig[uuid.UUID(self.script_info.script_id)], GeneralConfig
        ):
            return "脚本配置类型错误, 不是通用脚本类型"
        if not Config.ScriptConfig[
            uuid.UUID(self.script_info.script_id)
        ].Script.ScriptPath:
            return "未填写脚本路径, 请检查脚本配置中的脚本路径设置！"
        if (
            Config.ScriptConfig[
                uuid.UUID(self.script_info.script_id)
            ].Script.IfTrackProcess
            and (
                not Config.ScriptConfig[
                    uuid.UUID(self.script_info.script_id)
                ].Script.TrackProcessName
            )
            and (
                not Config.ScriptConfig[
                    uuid.UUID(self.script_info.script_id)
                ].Script.TrackProcessExe
            )
            and (
                not Config.ScriptConfig[
                    uuid.UUID(self.script_info.script_id)
                ].Script.TrackProcessCmdline
            )
        ):
            return "开启追踪子进程后, 需至少填写一项追踪进程信息！"
        # 配置路径为空时 Path("") 等价于 Path(".")，后续的快照与清理会落到
        # 程序自身的工作目录上，必须在任务开始前拦下
        if not Config.ScriptConfig[
            uuid.UUID(self.script_info.script_id)
        ].Script.ConfigPath:
            return "未填写配置路径, 请检查脚本配置中的配置路径设置！"
        # 日志路径未填时每轮尝试都会白等 60 秒日志文件再失败, 属于确定性配置错误,
        # 在任务开始前拦下; 目录不存在不在这里拦, 有的脚本首次运行才创建日志目录
        if not Config.ScriptConfig[
            uuid.UUID(self.script_info.script_id)
        ].Script.LogPath:
            return "未填写日志路径, 请检查脚本配置中的日志路径设置！"
        if Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].Game.Enabled:
            game_path = Config.ScriptConfig[
                uuid.UUID(self.script_info.script_id)
            ].Game.Path
            if Config.ScriptConfig[
                uuid.UUID(self.script_info.script_id)
            ].Game.Type == "Emulator" and (
                Config.ScriptConfig[
                    uuid.UUID(self.script_info.script_id)
                ].Game.EmulatorId
                == "-"
                or Config.ScriptConfig[
                    uuid.UUID(self.script_info.script_id)
                ].Game.EmulatorIndex
                in ["", "-"]
            ):
                return "未完成模拟器配置, 请检查脚本配置中的模拟器设置！"
            elif Config.ScriptConfig[
                uuid.UUID(self.script_info.script_id)
            ].Game.Type == "Client" and (game_path is None or not game_path.exists()):
                return "未完成游戏配置, 请检查脚本配置中的游戏设置！"
            elif Config.ScriptConfig[
                uuid.UUID(self.script_info.script_id)
            ].Game.Type == "URL" and (
                not Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].Game.URL
                or not Config.ScriptConfig[
                    uuid.UUID(self.script_info.script_id)
                ].Game.ProcessName
            ):
                return "未完成URL配置, 请检查脚本配置中的URL和进程名称设置！"

        return "Pass"

    def _remove_script_config(self) -> bool:
        """清理脚本当前配置路径，避免不同来源的目录文件互相残留。

        Returns:
            bool: 配置路径是否已被清空。目录被脚本进程占用时 rmtree 会在遍历
                途中抛出 PermissionError 并留下半删的目录，这里只忽略残留并如实
                返回结果，由调用方决定后续处理。
        """
        if self.script_config_path.is_dir():
            shutil.rmtree(self.script_config_path, ignore_errors=True)
        elif self.script_config_path.exists():
            try:
                self.script_config_path.unlink()
            except OSError as e:
                logger.opt(exception=True).warning(f"清理脚本原生配置失败: {e}")
        return not self.script_config_path.exists()

    def _recover_previous_run(self) -> None:
        """处置上次崩溃残留的原始配置快照。"""

        result = _utils_io.recover_native_config(
            self.temp_path,
            self.script_config_path,
            expected_script_id=self.script_info.script_id,
        )
        if result == "restored":
            logger.info("已恢复上次中断前的通用脚本原始配置")
        elif result == "legacy":
            logger.warning(
                "检测到上次中断残留的 通用脚本 原生配置快照由旧版本生成, 已改名保留以便手动恢复"
            )
        elif result == "skipped":
            logger.warning(
                "检测到通用脚本原生配置在中断后被改动, 已保留当前配置并丢弃旧快照"
            )

    def _snapshot_external_config(self) -> None:
        """保存脚本原生来源配置，作为用户切换和任务结束时的恢复基线。"""
        self.external_config_exists = self.script_config_path.exists()

        if self.external_config_exists:
            if self.script_config.Script.ConfigPathMode == "Folder":
                _utils_io.commit_native_config_snapshot(
                    self.temp_path,
                    self.script_config_path,
                    script_id=self.script_info.script_id,
                )
            elif self.script_config.Script.ConfigPathMode == "File":
                self.temp_path.mkdir(parents=True, exist_ok=True)
                shutil.copy(self.script_config_path, self.temp_path / "config.temp")

        self.external_config_snapshot_ready = True

    def _restore_external_config(self) -> None:
        """恢复脚本原生来源配置，隔离 MAS 用户配置的运行结果。"""
        if not self.external_config_snapshot_ready:
            return

        if not self.external_config_exists:
            # 任务前原生配置不存在: 现场内容只可能是本任务注入的 MAS 配置
            # (查看会话恢复的备份 / 非原生来源用户的下发), 删除即恢复「不存在」
            # 原状——混合用户时原生来源用户也因此拿到干净的原始现场
            self._remove_script_config()
            logger.info("脚本任务前原生配置不存在, 已清理任务注入的配置")
            return

        if self.script_config.Script.ConfigPathMode == "Folder":
            # 原子换入: 原生目录要么原样要么完整就位, 不出现半删中间态
            _utils_io.swap_in_dir(self.temp_path, self.script_config_path)
        elif self.script_config.Script.ConfigPathMode == "File":
            # 配置路径被脚本进程占用时只能清掉一部分, 此时仍要把快照覆盖回去,
            # 否则用户目录会停在半删状态
            if not self._remove_script_config():
                logger.warning(
                    f"脚本原生来源配置未清理干净, 直接覆盖恢复: {self.script_config_path}"
                )
            self.script_config_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(self.temp_path / "config.temp", self.script_config_path)

    def _cleanup_external_config_snapshot(self) -> None:
        if not self.external_config_snapshot_ready:
            return
        _utils_io.clear_native_config_snapshot(self.temp_path)
        self.external_config_snapshot_ready = False

    def _user_uses_mas_config(self) -> bool:
        user_id = self.script_info.user_list[self.script_info.current_index].user_id
        if user_id == "Default":
            return True
        user_config = self.user_config[uuid.UUID(user_id)]
        # 原生来源=不写；shared/independent 来源都写面板值
        return read_config_base(user_config) != CONFIG_BASE_NATIVE

    async def prepare(self):
        """运行前准备"""

        # 锁定脚本配置并加载用户配置
        self.config_locks[
            Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].uid
        ] = await Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].lock_x()
        self.script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        self.user_config = self.script_config.UserData
        logger.success(f"{self.script_info.script_id}已锁定, 通用脚本配置提取完成")

        script_config_path = self.script_config.Script.ConfigPath
        if script_config_path is None:
            raise ValueError("ConfigPath未配置，请检查路径设置")
        self.script_config_path = script_config_path
        self.temp_path = Path.cwd() / f"data/{self.script_info.script_id}/Temp"

        if Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].Game.Enabled:
            if (
                Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].Game.Type
                == "Emulator"
            ):
                device_provider = (
                    self._device_provider or EmulatorManager.get_emulator_instance
                )
                self.emulator_manager = await device_provider(
                    self.script_config.Game.EmulatorId
                )

            elif Config.ScriptConfig[
                uuid.UUID(self.script_info.script_id)
            ].Game.Type in ["Client", "URL"]:
                self.game_process_manager = ProcessManager()

        # 构建用户列表
        if self.task_info.mode == "ScriptConfig":
            self.script_info.user_list = [
                UserItem(
                    user_id=self.task_info.user_id or "Default", name="", status="等待"
                )
            ]
        else:
            self.script_info.user_list = self.build_proxy_user_list(
                self.user_config.items()
            )
        logger.info(
            f"用户列表加载完成, 已筛选用户数: {len(self.script_info.user_list)}"
        )

        logger.info(f"记录脚本原生来源配置: {self.script_config_path}")
        self._recover_previous_run()
        self._snapshot_external_config()

        # 任务级一次性归档脚本原生配置（脚本级池，指纹去重，失败不阻断
        # 任务）：此刻 ConfigPath 仍是任务动手前的完整现场，必须在任何
        # 换入/写入前归档
        from .tools.backup_archive import archive_native_backup

        with suppress(Exception):
            archive_native_backup(
                self.script_info.script_id,
                self.script_config_path,
                self.script_config.Script.ConfigPathMode,
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

        if not isinstance(self.script_config, GeneralConfig):
            raise RuntimeError("脚本配置类型错误, 不是通用脚本类型")

        for self.script_info.current_index in range(len(self.script_info.user_list)):
            current_user = self.script_info.user_list[self.script_info.current_index]
            if (
                self.task_info.mode == "AutoProxy"
                and not await self.check_user_before_run(
                    current_user, self.user_config[uuid.UUID(current_user.user_id)]
                )
            ):
                continue
            use_mas_config = self._user_uses_mas_config()
            user_id = self.script_info.user_list[self.script_info.current_index].user_id
            logger.info(
                f"用户 {user_id} 配置来源: "
                f"{'MAS 独立配置' if use_mas_config else '脚本原生来源配置'}"
            )
            if not use_mas_config:
                self._restore_external_config()

            task = METHOD_BOOK[self.task_info.mode](
                self.script_info,
                self.script_config,
                self.user_config,
                (
                    self.emulator_manager
                    if self.script_config.Game.Type == "Emulator"
                    else self.game_process_manager
                )
                if self.script_config.Game.Enabled
                else None,
            )

            try:
                await self.run_user_task(current_user, task)
            finally:
                # 查看会话（viewOnly）不重拍快照：用户级查看会把该用户
                # ConfigFile 下发进原生配置（GUI 所见即备份），重拍会把被
                # 污染的原生存成新快照、覆盖 prepare 时的真实原状，收尾
                # 还原时原生就被固定成备份内容
                if not use_mas_config and not self.task_info.view_only:
                    self._snapshot_external_config()

    async def final_task(self):
        """运行结束后的收尾工作"""
        try:
            if self.check_result != "Pass":
                self.script_info.status = "异常"
                return self.check_result

            logger.info("通用脚本任务已结束, 开始执行后续操作")

            self._restore_external_config()
            self._cleanup_external_config_snapshot()

            if self.task_info.mode == "AutoProxy":
                await config_manager.flush()

                summary = self.collect_user_results()

                title = f"{datetime.now().strftime('%m-%d')} | {self.script_info.name or '空白'}的{TASK_MODE_ZH[self.task_info.mode]}任务报告"
                # 按用户交错组装「用户结果行 + 该用户进程信息」：
                # 多账号任务时各用户信息归属清晰，不再全部平铺。
                # 「失败」类型条目仅在本次任务存在未完成用户时纳入报告，
                # 与 SendTaskResultTime 的「仅失败时」推送策略自然配合
                has_uncompleted = summary.uncompleted_count > 0
                user_result_text = self._render_user_results(
                    has_uncompleted=has_uncompleted
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
        logger.opt(exception=True).warning(f"通用脚本任务出现异常: {e}")
        try:
            self._restore_external_config()
            self._cleanup_external_config_snapshot()
        except Exception as restore_error:
            logger.opt(exception=True).warning(
                f"恢复脚本原生来源配置失败: {restore_error}"
            )
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=f"通用脚本任务出现异常: {e}"),
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
