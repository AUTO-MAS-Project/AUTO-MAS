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

按账号逐个拉起 BAAH 自动代理任务，结束时统一组装任务报告并推送。
"""

import asyncio
import shutil
import uuid
from contextlib import ExitStack, suppress
from datetime import datetime

import app.core.notify.report as _node_report
from app.config import config_manager
from app.core import Config, EmulatorManager, Notify, Publisher
from app.core.script_update import (
    ScriptUpdateRequest,
    auto_recover_script_install,
    run_managed_script_install,
    run_script_update_with_safe_fallback,
)
from app.core.script_update_recovery import DownloadRetryFailed
from app.core.ws import protocol
from app.models.config import BAAHConfig
from app.models.emulator import DeviceBase, DeviceProvider
from app.models.notification.report import TaskResultReport, UserReportText
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem
from app.services import script_install
from app.services.script_install_backup import ManagedInstallBackup
from app.task.emulator_core import close_emulator
from app.task.manager_base import ScriptManagerBase
from app.utils import LOG_TYPE_ERROR, TASK_MODE_ZH, get_logger, log_box, update_files
from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed

from .AutoProxy import AutoProxyTask
from .tools import program_update
from .tools.managed_recovery import (
    BAAHInstallAdapter,
    acknowledge_stale_transaction,
    cleanup_original_receipts,
    inspect_stale_transaction,
    receipt_backup_path,
    snapshot_original_receipts,
)

logger = get_logger("BAAH 调度器")

METHOD_BOOK: dict[str, type[AutoProxyTask]] = {
    "AutoProxy": AutoProxyTask,
}


class BAAHManager(ScriptManagerBase):
    """BAAH 控制器"""

    wait_for_finalizer_on_cancel = True

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
        self._install_access = ExitStack()
        self._directory_lock = None
        self.emulator_manager: DeviceBase | None = None
        self._device_provider = device_provider

    async def check(self) -> str:
        """校验 BAAH 脚本配置是否可用"""

        if self.task_info.mode not in METHOD_BOOK:
            return "不支持的任务模式, 请检查任务配置！"

        script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        if not isinstance(script_config, BAAHConfig):
            return "托管配置类型错误, 不是 BAAH 托管类型"

        if script_config.Emulator.Id == "-" or script_config.Emulator.Index in [
            "",
            "-",
        ]:
            return "未完成模拟器配置, 请检查托管配置中的模拟器设置！"

        ## 程序目录、配置目录与日志目录都由 BAAHPath 派生，只需校验它
        path = script_config.Script.BAAHPath
        if path is None:
            return "未填写 BAAH 主程序路径, 请检查托管配置中的主程序路径设置！"
        if not path.is_file():
            directory = script_install.workspace(path.parent)
            receipt = script_install.record_path(path.parent, "installed.json")
            if not (directory / "transaction.json").is_file() and not receipt.is_file():
                return "BAAH 主程序不存在，且没有可信的中断安装记录，请检查安装路径"

        return "Pass"

    async def prepare(self):
        """运行前准备"""

        self.config_locks[
            Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].uid
        ] = await Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].lock_x()
        self.script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        self.user_config = self.script_config.UserData
        logger.success(f"{self.script_info.script_id} 已锁定, BAAH 托管配置提取完成")

        self.script_info.user_list = self.build_proxy_user_list(
            self.user_config.items()
        )
        logger.info(
            f"账号列表加载完成, 已筛选账号数: {len(self.script_info.user_list)}"
        )

        # 初始化模拟器管理器：模拟器的启动与关闭统一由本软件调度,
        # BAAH 自身不再负责拉起模拟器
        device_provider = self._device_provider or EmulatorManager.get_emulator_instance
        self.emulator_manager: DeviceBase = await device_provider(
            self.script_config.Emulator.Id
        )

    async def _prepare_program_update(self) -> None:
        root = self.script_config.Script.BAAHPath.parent
        self.check_result = "BAAH 更新准备未完成"
        lock = update_files.directory_lock(root.resolve())
        await lock.acquire()
        self._directory_lock = lock
        self._install_access.enter_context(script_install.installation_access(root))
        request = ScriptUpdateRequest(str(self.script_info.script_id), "BAAH")
        backup = ManagedInstallBackup(
            root, script_id=request.script_id, script_type="BAAH"
        )
        # 原生事务未完成时不能通过清除 journal 绕过正在使用的备份。
        try:
            await script_install.run_worker(
                script_install.recover_install,
                root,
                lambda: program_update.assert_idle(root),
            )
        except (script_install.InstallUnsafeError, OSError, ValueError):
            marker = script_install.workspace(root) / "transaction.json"
            if marker.is_symlink() or not marker.is_file():
                raise

            async def retry_native_rollback():
                await script_install.run_worker(
                    script_install.recover_install,
                    root,
                    lambda: program_update.assert_idle(root),
                )

            outcome = await auto_recover_script_install(
                request,
                install_root=root,
                inspect=lambda: inspect_stale_transaction(root),
                acknowledge=lambda: acknowledge_stale_transaction(root),
                reinstall=retry_native_rollback,
            )
            self.script_info.log = (
                f"BAAH 原生安装事务由公共入口恢复：{outcome}"
            )
        # 检查旧安装不写目录，可以保留 BAAH 内置的 adb server。
        await asyncio.to_thread(
            program_update.assert_idle, root, allow_background_adb=True
        )

        if backup.read() is not None:
            adapter = BAAHInstallAdapter(root, self.script_config)
            result = await run_managed_script_install(
                request,
                install_root=root,
                inspect=adapter.inspect,
                acknowledge=adapter.acknowledge,
                install=adapter.install,
                ensure_idle=adapter.ensure_idle,
                after_rollback=adapter.after_rollback,
            )
            await script_install.run_worker(cleanup_original_receipts, root)
            self.script_info.log = (f"BAAH 上次安装恢复：{result}")
            self.check_result = "Pass"
            return

        try:
            await program_update.confirm_current_install(root)
            if receipt_backup_path(root).exists():
                await script_install.run_worker(cleanup_original_receipts, root)
        except (script_install.InstallUnsafeError, OSError, ValueError) as error:
            # 损坏本体只能在已核验的 MAS 安装身份下自动完整重装。
            receipt = script_install.record_path(root, "installed.json")
            if receipt.is_symlink() or not receipt.is_file():
                raise script_install.InstallUnsafeError(
                    "BAAH 原安装不完整且缺少可信回执，不能自动修复"
                ) from error
            snapshot = receipt.read_bytes()
            program_update.verify_recovery_receipt(root, snapshot)
            adapter = BAAHInstallAdapter(
                root, self.script_config, recovery_receipt=snapshot
            )
            result = await auto_recover_script_install(
                request,
                install_root=root,
                inspect=adapter.inspect,
                acknowledge=adapter.acknowledge,
                reinstall=adapter.install,
            )
            self.script_info.log = (f"BAAH 自动修复：{result}")
            self.check_result = "Pass"
            return

        if self.script_config.Update.TakeoverEnabled:

            async def progress(downloaded: int, total: int, speed: float) -> None:
                self.script_info.log = (
                    f"BAAH 下载：{downloaded / 1024**2:.1f} / {total / 1024**2:.1f} MB"
                )

            async def prepare():
                try:
                    return await program_update.prepare_update(
                        root, self.script_config, progress=progress
                    )
                except (script_install.InstallUnsafeError, FluxdownCancelUnconfirmed):
                    raise
                except Exception as error:
                    raise DownloadRetryFailed(
                        source="BAAH GitHub/MirrorChyan",
                        reason=f"BAAH 更新准备失败（{type(error).__name__}）",
                    ) from error

            candidate = await run_script_update_with_safe_fallback(
                request,
                prepare,
                root,
                BAAHInstallAdapter(root, self.script_config).inspect,
            )
            if isinstance(candidate, program_update.PreparedUpdate):
                adapter = BAAHInstallAdapter(
                    root, self.script_config, prepared=candidate
                )
                await script_install.run_worker(snapshot_original_receipts, root)
                try:
                    result = await run_managed_script_install(
                        request,
                        install_root=root,
                        inspect=adapter.inspect,
                        acknowledge=adapter.acknowledge,
                        install=adapter.install,
                        ensure_idle=adapter.ensure_idle,
                        after_rollback=adapter.after_rollback,
                    )
                finally:
                    await adapter.ensure_idle()
                    if candidate.archive.parent.exists():
                        shutil.rmtree(candidate.archive.parent)
                    if backup.read() is None:
                        await script_install.run_worker(cleanup_original_receipts, root)
            else:
                await program_update.confirm_current_install(root)
                result = candidate or "BAAH 当前无需更新"
            self.script_info.log = (str(result))
        self.check_result = "Pass"

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
            raise RuntimeError("托管配置类型错误, 不是 BAAH 托管类型")

        await self._prepare_program_update()

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
            # manager 已按整个任务生命周期持有目录锁，避免 AutoProxy 再次
            # 获取不可重入的 asyncio.Lock，导致自身死锁。
            task.directory_reserved = True
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
                ## 按账号交错组装「账号结果行 + 该账号节点详情」，
                ## 失败类型条目仅在本次任务存在未完成账号时纳入报告
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

            # 安装准备/账号执行异常不可被常规收尾覆盖成“完成”。
            if self.script_info.status == "异常" or any(
                user.status not in {"完成", "跳过"}
                for user in self.script_info.user_list
            ):
                self.script_info.status = "异常"
            else:
                self.script_info.status = "完成"
        finally:
            try:
                self._install_access.close()
            finally:
                directory_lock = getattr(self, "_directory_lock", None)
                if directory_lock is not None:
                    self._directory_lock = None
                    directory_lock.release()
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
