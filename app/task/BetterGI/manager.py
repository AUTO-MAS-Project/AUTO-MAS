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
import asyncio
import uuid
from contextlib import ExitStack, suppress
from datetime import datetime
from pathlib import Path

import app.core.notify.report as _node_report
from app.config import ConfigCollection, config_manager
from app.core import Config, Notify, Publisher
from app.core.script_update import ScriptUpdateRequest, run_script_update
from app.core.ws import protocol
from app.models.config import BetterGIConfig, BetterGIUserConfig
from app.models.notification.report import TaskResultReport, UserReportText
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, UserItem
from app.services import script_install
from app.task.manager_base import ScriptManagerBase
from app.utils import LOG_TYPE_ERROR, TASK_MODE_ZH, get_logger, log_box
from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed

from .AutoProxy import _BGI_REL_EXE, AutoProxyTask
from .ScriptConfig import ScriptConfigTask
from .tools import archive_native_backup, install_recovery, program_update
from .Update import BetterGIUpdateTask

logger = get_logger("BetterGI 调度器")


class BetterGIManager(ScriptManagerBase):
    """BetterGI 控制器（better-genshin-impact 线）"""

    # 重复停止也要等待配置还原与安装目录锁释放。
    wait_for_finalizer_on_cancel = True

    # 子任务失败不覆盖上游整条流程的完成结果，详情与警告在节点中展示。
    completed_user_statuses = frozenset({"完成", "部分失败"})

    def __init__(self, script_info: ScriptItem):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.check_result = "-"
        self._install_access = ExitStack()
        self._program_update_prepared = False
        self._update_root: Path | None = None
        self.user_config: ConfigCollection[BetterGIUserConfig] | None = None

    async def check(self) -> str:
        if self.execution_mode not in ("AutoProxy", "ScriptConfig", "Update"):
            return "不支持的任务模式, 请检查任务配置！"

        script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        if not isinstance(script_config, BetterGIConfig):
            return "托管配置类型错误, 不是 BetterGI 类型"

        if self.execution_mode == "ScriptConfig":
            if not script_config.Info.RootPath:
                return "请先设置有效的 BetterGI 脚本路径"
            root_path = script_config.Info.RootPath
            if not root_path.is_dir() or not (root_path / _BGI_REL_EXE).is_file():
                return "请先设置有效的 BetterGI 脚本路径"
            target_user_id = self.task_info.user_id or "Default"
            if target_user_id != "Default":
                try:
                    target_user_uid = uuid.UUID(target_user_id)
                except ValueError:
                    return "BetterGI 账号不存在，请刷新后重试"
                if target_user_uid not in script_config.UserData:
                    return "BetterGI 账号不存在，请刷新后重试"

        # 「检查更新」必须落到具体账号：游戏客户端路径可能是账号级覆盖
        if self.execution_mode == "Update":
            try:
                target_user_uid = uuid.UUID(self.task_info.user_id or "")
            except ValueError:
                return "更新任务需要指定账号，请刷新后重试"
            if target_user_uid not in script_config.UserData:
                return "BetterGI 账号不存在，请刷新后重试"

        # AutoProxy 模式只做账号列表可用性校验；逐账号配置文件检查放到 AutoProxyTask.check()
        if self.execution_mode == "AutoProxy":
            script_uid = uuid.UUID(self.script_info.script_id)
            if not self.script_info.user_list:
                await self.script_info.set_users(
                    self.build_proxy_user_list(
                        Config.ScriptConfig[script_uid].UserData.items()
                    )
                )
            if not self.script_info.user_list:
                return "当前没有可执行的账号，请先添加并启用账号"

        return "Pass"

    async def prepare(self):
        script_uid = uuid.UUID(self.script_info.script_id)
        self.config_locks[
            Config.ScriptConfig[script_uid].uid
        ] = await self.lock_script_config(Config.ScriptConfig[script_uid])
        self.script_config = Config.ScriptConfig[script_uid]
        if not isinstance(self.script_config, BetterGIConfig):
            raise TypeError("托管配置类型错误")

        root = self.script_config.Info.RootPath
        if root is not None:
            self._install_access.enter_context(script_install.installation_access(root))
            self._update_root = root
            program_update.recover_update_notice(root)

        # X 锁覆盖账号集合，运行时直接修改原配置。
        self.user_config = self.script_config.UserData
        logger.success(f"{self.script_info.script_id} 已锁定，BetterGI 账号配置已提取")

        if self.execution_mode == "Update":
            target_user_id = self.task_info.user_id or "Default"
            target_user_name = "BetterGI 更新"
            with suppress(ValueError):
                target_user_uid = uuid.UUID(target_user_id)
                if target_user_uid in self.user_config:
                    target_user_name = self.user_config[target_user_uid].Info.Name
            await self.script_info.set_users(
                [
                    UserItem(
                        user_id=target_user_id,
                        name=target_user_name,
                        status="等待",
                    )
                ]
            )
        elif self.execution_mode == "ScriptConfig":
            target_user_id = self.task_info.user_id or "Default"
            target_user_name = "BetterGI 设置"
            with suppress(ValueError):
                target_user_uid = uuid.UUID(target_user_id)
                if target_user_uid in self.user_config:
                    target_user_name = self.user_config[target_user_uid].Info.Name
            await self.script_info.set_users(
                [
                    UserItem(
                        user_id=target_user_id,
                        name=target_user_name,
                        status="等待",
                    )
                ]
            )
        else:
            await self.script_info.set_users(
                self.build_proxy_user_list(self.user_config.items())
            )

    async def _run_program_update(
        self, root: Path, *, recovery_snapshot: bytes | None = None
    ) -> str:
        await self.script_info.set_log("正在检查 BetterGI 本体更新…")

        async def progress(downloaded: int, total: int, speed: float) -> None:
            await self.script_info.set_log(
                f"BetterGI 更新下载：{downloaded / 1024**2:.1f} / {total / 1024**2:.1f} MB"
            )

        return await run_script_update(
            ScriptUpdateRequest(self.script_info.script_id, "BetterGI"),
            program_update.update_before_run,
            root,
            self.script_config,
            progress=progress,
            recovery_snapshot=recovery_snapshot,
        )

    async def _recover_unconfirmed_install(self) -> bool:
        """残留标记由用户明确决定；关闭自动接管时也允许主动重试一次。"""
        root = self._update_root
        if root is None:
            return False
        marker = script_install.workspace(root) / "bgi-install.json"
        if not marker.exists() and not marker.is_symlink():
            return False

        # 持有安装锁，但还须排除 MAS 之外手工启动的安装器和运行中的 BGI。
        await asyncio.to_thread(program_update.assert_idle, root)
        action, snapshot = await install_recovery.ask_install_recovery(
            self.task_info.task_id,
            root,
            managed_name=getattr(self.script_info, "name", "BetterGI"),
            channel=self.script_config.Update.Channel,
            takeover_enabled=self.script_config.Update.TakeoverEnabled,
        )
        if action == "skip":
            version = await install_recovery.skip_unconfirmed_install(root, snapshot)
            result = f"用户确认跳过 BetterGI 未完成安装，当前版本 {version}，继续任务"
            logger.warning(result)
            await self.script_info.set_log(result)
            with suppress(Exception):
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(level="warning", message=result),
                )
        else:
            # 用户主动选择重试：即使 TakeoverEnabled=False，也只为本次恢复调用更新器。
            # 不走普通更新失败的旧版回退：安装标记仍在时任何失败都必须停止。
            result = await self._run_program_update(
                root, recovery_snapshot=snapshot
            )
            await program_update.confirm_current_install(root)
            await self.script_info.set_log(f"BetterGI 安装恢复成功：{result}")
        return True

    async def _prepare_program_update(self) -> None:
        root = self._update_root
        if root is None:
            return
        self.check_result = "BetterGI 更新准备未完成"
        if self._program_update_prepared:
            if self.script_config.Update.TakeoverEnabled:
                await program_update.confirm_current_install(root)
            elif (script_install.workspace(root) / "bgi-install.json").exists():
                raise script_install.InstallUnsafeError(
                    "BetterGI 安装状态在任务期间发生变化，已停止启动"
                )
            self.check_result = "Pass"
            return

        if await self._recover_unconfirmed_install():
            # 无论重试还是跳过，本轮已由用户确定更新动作；不能继续自动更新第二次。
            if self.script_config.Update.TakeoverEnabled:
                program_update.suppress_update_notice(root)
            self._program_update_prepared = True
            self.check_result = "Pass"
            return

        if self.script_config.Update.TakeoverEnabled:
            try:
                result = await self._run_program_update(root)
            except (script_install.InstallUnsafeError, FluxdownCancelUnconfirmed):
                raise
            except Exception as error:
                await program_update.confirm_current_install(root)
                result = f"BetterGI 更新准备失败，沿用当前安装继续任务：{error}"
                logger.warning(result)
                with suppress(Exception):
                    await Publisher.send(
                        id=self.task_info.task_id,
                        type=protocol.TASK_NOTICE,
                        data=WSTaskNoticeData(level="warning", message=result),
                    )
            await self.script_info.set_log(result)
            program_update.suppress_update_notice(root)
        else:
            # 关闭自动接管不等于自动忽略上次更新记录；状态变化时保守停止。
            marker = script_install.workspace(root) / "bgi-install.json"
            if marker.exists():
                raise script_install.InstallUnsafeError(
                    "BetterGI 上次安装未确认，无法直接启动"
                )
        self._program_update_prepared = True
        self.check_result = "Pass"

    async def main_task(self):
        self.check_result = await self.check()
        if self.check_result != "Pass":
            await self.script_info.set_state(status="异常")
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=self.check_result),
            )
            return

        self.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await self.prepare()
        assert self.user_config is not None

        self.script_info.user_config = self.user_config

        # Update 只更新原神客户端，不启动 BetterGI；运行中的正常 BGI
        # 不应该阻断游戏更新，但未完成的本体安装必须阻断。
        root = self._update_root
        if root is not None and self.execution_mode in ("Update", "ScriptConfig"):
            await self._recover_unconfirmed_install()
            if self.execution_mode == "Update":
                await program_update.confirm_safe_game_update(root)
            else:
                await program_update.confirm_current_install(root)

        # 「检查更新」不动 BetterGI 配置，不必归档，直接进更新任务
        if self.execution_mode == "Update":
            await self.script_info.set_current_index(0)
            await self.spawn(
                BetterGIUpdateTask(
                    self.script_info,
                    self.script_config,
                    self.user_config,
                    self.task_info.user_id or "Default",
                )
            )
            return

        # 任务级归档 BetterGI 全局主配置（config.json）——运行会临时补写
        # 队伍/策略叶子、结束还原，崩溃残留会污染全局配置；持久归档提供
        # 跨会话找回（指纹去重，失败不阻断任务）。mas 池由 AutoProxy
        # 物化前按账号归档
        with suppress(Exception):
            root_path = self.script_config.Info.RootPath
            if root_path is not None:
                archive_native_backup(root_path)

        if self.execution_mode == "ScriptConfig":
            await self.script_info.set_current_index(0)
            await self.spawn(
                ScriptConfigTask(
                    self.script_info,
                    self.script_config,
                    self.user_config,
                    view_only=self.task_info.view_only,
                )
            )
            return

        has_run_user = False
        for _runtime_user_index in range(len(self.script_info.user_list)):
            await self.script_info.set_current_index(_runtime_user_index)
            current_user = self.script_info.user_list[self.script_info.current_index]
            if (
                self.execution_mode == "AutoProxy"
                and not await self.check_user_before_run(
                    current_user, self.user_config[uuid.UUID(current_user.user_id)]
                )
            ):
                continue

            await self._prepare_program_update()

            method = AutoProxyTask(
                script_info=self.script_info,
                script_config=self.script_config,
                user_config=self.user_config,
            )

            sub_check = await method.check()
            if sub_check != "Pass":
                self.check_result = sub_check
                current_user = self.script_info.user_list[
                    self.script_info.current_index
                ]
                await self.notify_user_check_failure(current_user, sub_check)
                continue

            # 下一账号通过检查才等待上一账号的游戏退出，尾部全部跳过时不空等。
            if has_run_user:
                await method.wait_game_exit_before_next_user()
            await self.run_user_task(current_user, method)
            has_run_user = True

    async def final_task(self):
        try:
            if self.check_result != "Pass" and not any(
                user.status in ("完成", "跳过") for user in self.script_info.user_list
            ):
                if self.execution_mode == "AutoProxy" and self.user_config is not None:
                    await config_manager.flush()
                await self.script_info.set_state(status="异常")
                return

            if self.execution_mode == "AutoProxy" and self.user_config is not None:
                await config_manager.flush()

            if self.script_info.status == "异常" or any(
                user.status == "异常" for user in self.script_info.user_list
            ):
                await self.script_info.set_state(status="异常")
            else:
                await self.script_info.set_state(status="完成")

            if self.execution_mode == "AutoProxy":
                task_mode = TASK_MODE_ZH[self.execution_mode]
                title = (
                    f"{datetime.now().strftime('%m-%d')} | "
                    f"{self.script_info.name or '空白'}的{task_mode}任务报告"
                )
                # 按账号交错组装「账号结果行 + 一条龙/执行层节点详情」进报告正文
                # （ScriptItem.result 是只读计算属性，报告正文用局部变量承载）
                user_result_text = self._render_user_results(
                    has_uncompleted=bool(self.collect_user_results().uncompleted_count)
                )
                # 报告正文整块镜像进调度台，未配置推送的用户也能看到节点详情
                if user_result_text:
                    await self.script_info.set_log(
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
                            level="error",
                            message=f"推送代理结果时出现异常: {e}",
                        ),
                    )
        finally:
            try:
                if self._update_root is not None:
                    program_update.recover_update_notice(self._update_root)
            except Exception:
                await self.script_info.set_state(status="异常")
                raise
            finally:
                self._install_access.close()
                script_config = getattr(self, "script_config", None)
                if script_config is not None:
                    ticket = self.config_locks.pop(script_config.uid, None)
                    if ticket is not None:
                        await script_config.unlock(ticket)

    async def on_crash(self, e: Exception):
        await self.script_info.set_state(status="异常")
        logger.opt(exception=True).warning(f"BetterGI任务出现异常: {e}")
        script_uid = uuid.UUID(self.script_info.script_id)

        try:
            script_cfg = Config.ScriptConfig[script_uid]
        except Exception:
            script_cfg = None

        if script_cfg is not None:
            try:
                if self.execution_mode == "AutoProxy" and self.user_config is not None:
                    await config_manager.flush()
            except Exception:
                logger.opt(exception=True).warning("on_crash 保存账号配置失败")

        with suppress(Exception):
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="error", message=f"BetterGI任务出现异常: {e}"
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
                for item in self.user_state(_report_user).push_log
                if (item.log_type if isinstance(item, log_box.LogEntry) else item[0])
                != LOG_TYPE_ERROR
                or has_uncompleted
            ]
            _mode = self.user_state(_report_user).push_log_mode
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
