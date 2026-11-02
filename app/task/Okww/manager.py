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
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path

import app.core.notify.report as _node_report
from app.config import ConfigCollection, config_manager
from app.core import Config, Notify, Publisher
from app.core.ws import protocol
from app.models.config import OkwwConfig, OkwwUserConfig
from app.models.notification.report import TaskResultReport, UserReportText
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, UserItem
from app.task.manager_base import ScriptManagerBase
from app.utils import (
    BASE_NATIVE,
    BASE_SHARED,
    BASE_SOURCE_LABELS,
    LOG_TYPE_ERROR,
    TASK_MODE_ZH,
    ProcessManager,
    get_logger,
    log_box,
)
from app.utils import io as _utils_io

from .AutoProxy import (
    _OKWW_REL_APP_JSON,
    _OKWW_REL_CONFIG_DIR,
    _OKWW_REL_EXE,
    AutoProxyTask,
    _okww_config_base,
)
from .ScriptConfig import ScriptConfigTask
from .tools.backup_archive import archive_native_backup
from .Update import WuwaUpdateTask

logger = get_logger("OK-WW 调度器")


class OkwwManager(ScriptManagerBase):
    """OK-WW 控制器（ok-script 线）"""

    maintenance_message = "鸣潮正在维护"

    def __init__(self, script_info: ScriptItem):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.check_result = "-"
        self.user_config: ConfigCollection[OkwwUserConfig] | None = None
        self.temp_path: Path | None = None
        self.script_config_path: Path | None = None
        self.had_original_script_config = False
        self.script_config_base = BASE_SHARED

    async def check(self) -> str:
        if self.task_info.mode not in ("AutoProxy", "ScriptConfig", "Update"):
            return "不支持的任务模式, 请检查任务配置！"

        script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        if not isinstance(script_config, OkwwConfig):
            return "脚本配置类型错误, 不是 OK-WW 类型"

        if self.task_info.mode == "ScriptConfig":
            root_path = script_config.Info.RootPath
            if root_path is None:
                return "请先设置有效的 OK-WW 脚本路径"
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
            if not script_config.Game.Enabled:
                return "请先在脚本配置中启用游戏配置"
            launcher = Path(str(script_config.Game.Path or "").strip())
            if not launcher.is_file():
                return "请先在脚本配置中导入有效的鸣潮官方启动器"

        # AutoProxy 模式只做用户列表可用性校验；逐用户配置文件检查放到 AutoProxyTask.check()
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
        if not isinstance(self.script_config, OkwwConfig):
            raise TypeError("脚本配置类型错误")

        # X 锁覆盖用户集合，运行时直接修改原配置。
        self.user_config = self.script_config.UserData
        logger.success(f"{self.script_info.script_id} 已锁定，OK-WW 用户配置已提取")

        if self.task_info.mode == "Update":
            target_user_id = self.task_info.user_id or "Default"
            target_user_name = "OK-WW 更新"
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
        elif self.task_info.mode == "ScriptConfig":
            target_user_id = self.task_info.user_id or "Default"
            target_user_name = "OK-WW 设置"
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
            if target_user_id != "Default":
                self.script_config_base = _okww_config_base(
                    self.user_config[uuid.UUID(target_user_id)].Info.Base
                )
        else:
            self.script_info.user_list = self.build_proxy_user_list(
                self.user_config.items()
            )

        # Enabled=游戏管理总开关；开启后任务前始终启动游戏，任务结束/失败时始终关闭游戏
        self.game_manager: ProcessManager | None = None
        if self.task_info.mode == "AutoProxy" and self.script_config.Game.Enabled:
            self.game_manager = ProcessManager()

        if self.task_info.mode in ("AutoProxy", "ScriptConfig"):
            root_path = self.script_config.Info.RootPath
            if root_path is None:
                raise ValueError("RootPath未配置，请检查路径设置")
            self.script_config_path = root_path / _OKWW_REL_CONFIG_DIR
            self.temp_path = Path.cwd() / f"data/{self.script_info.script_id}/Temp"
            self._recover_previous_run()
            if _utils_io.commit_native_config_snapshot(
                self.temp_path,
                self.script_config_path,
                script_id=self.script_info.script_id,
            ):
                self.had_original_script_config = True

            # 任务级一次性归档 ok-ww 原生配置（项目级池，指纹去重，失败不
            # 阻断任务）：原生配置物理上跨用户共享，只代表「本轮任务动手前」
            # 的脚本原生状态——下发/覆盖处按用户归档会把上一轮下发的 MAS
            # 配置误当原生内容挤进保留池，必须在任何下发前归档这一次
            with suppress(Exception):
                archive_native_backup(self.script_config_path)

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
            _utils_io.force_rmtree(self.script_config_path)
        else:
            logger.info(f"复原 OK-WW 脚本配置文件: {self.temp_path}")
            _utils_io.swap_in_dir(self.temp_path, self.script_config_path)

    def _recover_previous_run(self) -> None:
        """处置上次崩溃残留的原始配置快照。"""

        result = _utils_io.recover_native_config(
            self.temp_path,
            self.script_config_path,
            expected_script_id=self.script_info.script_id,
        )
        if result == "restored":
            logger.info("已恢复上次中断前的 OK-WW 原始配置")
        elif result == "legacy":
            logger.warning(
                "检测到上次中断残留的 OK-WW 原生配置快照由旧版本生成, 已改名保留以便手动恢复"
            )
        elif result == "skipped":
            logger.warning(
                "检测到 OK-WW 原生配置在中断后被改动, 已保留当前配置并丢弃旧快照"
            )

    def _cleanup_script_config_temp(self) -> None:
        if self.temp_path:
            _utils_io.clear_native_config_snapshot(self.temp_path)

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

        if self.task_info.mode == "Update":
            self.script_info.current_index = 0
            target_user_id = self.task_info.user_id or "Default"
            resource = str(self.user_config[uuid.UUID(target_user_id)].Info.Resource)
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
                    # 查看会话（view_only）仅 ScriptConfig 模式支持：只读打开原生 GUI
                    view_only=self.task_info.view_only,
                )
            )
            return

        for self.script_info.current_index in range(len(self.script_info.user_list)):
            current_user = self.script_info.user_list[self.script_info.current_index]
            if (
                self.task_info.mode == "AutoProxy"
                and not await self.check_user_before_run(
                    current_user, self.user_config[uuid.UUID(current_user.user_id)]
                )
            ):
                continue
            current_config = self.user_config[uuid.UUID(current_user.user_id)]
            config_base = _okww_config_base(current_config.Info.Base)
            logger.info(
                f"用户 {current_user.user_id} 配置来源: "
                f"{BASE_SOURCE_LABELS.get(config_base, config_base)}"
            )
            if config_base == BASE_NATIVE:
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
                await self.notify_user_check_failure(current_user, sub_check)
                continue

            # OK-WW 的工作目录、脚本进程和日志文件属于安装级共享资源，用户必须串行执行。
            try:
                await self.run_user_task(current_user, method)
            finally:
                # 每个用户任务结束后立即恢复快照，overlay 不得残留到脚本原配置。
                await self._restore_script_config_from_temp()

    async def final_task(self):
        try:
            if not self._keep_script_config_changes():
                await self._restore_script_config_from_temp()
            else:
                logger.info("原生来源配置会话成功，保留脚本原生配置")
            self._cleanup_script_config_temp()

            if self.check_result != "Pass" and not any(
                user.status in ("完成", "跳过") for user in self.script_info.user_list
            ):
                if self.task_info.mode == "AutoProxy" and self.user_config is not None:
                    await config_manager.flush()
                self.script_info.status = "异常"
                return

            if self.task_info.mode == "AutoProxy" and self.user_config is not None:
                await config_manager.flush()

            if any(user.status == "异常" for user in self.script_info.user_list):
                self.script_info.status = "异常"
            elif self.all_users_maintenance_skipped:
                # 画面检测把全部用户判为维护跳过时，整体状态记「跳过」而非「完成」
                self.script_info.status = "跳过"
            else:
                self.script_info.status = "完成"

            if self.task_info.mode == "AutoProxy":
                summary = self.collect_user_results()
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
                    if self.all_users_maintenance_skipped:
                        # 全员维护跳过：推维护通知而非常规代理报告（对齐 MaaEnd）
                        await self.notify_maintenance()
                    else:
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

    def _keep_script_config_changes(self) -> bool:
        """原生来源配置会话成功后保留脚本原生 GUI 写回的配置。

        查看会话（view_only）不在此列：只读预览结束后原生现场必须按任务前
        快照还原，不能把 GUI 里的临时改动当作直控保存保留下来。
        """

        return (
            self.task_info.mode == "ScriptConfig"
            and not self.task_info.view_only
            and self.script_config_base == BASE_NATIVE
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
            try:
                if self.task_info.mode == "AutoProxy" and self.user_config is not None:
                    await config_manager.flush()
            except Exception:
                logger.opt(exception=True).warning("on_crash 保存用户配置失败")

        with suppress(Exception):
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=f"OK-WW任务出现异常: {e}"),
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
