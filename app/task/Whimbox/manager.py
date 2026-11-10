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
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""奇想盒控制器（BetterGI 线：编排生命周期/用户循环/报告聚合）。

本文件只装配任务对象（AutoProxyTask / ScriptConfigTask）；四边界的默认实现在
AutoProxyTask 内就地兜底构造（L1 构造注入、零容器），单测经其构造参数注入
假实现，不经过本文件。
"""

import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from app.config import ConfigCollection, config_manager
from app.core import Config, Notify, Publisher
from app.core.script_update import (
    ScriptUpdateRequest,
    run_script_update_with_safe_fallback,
    auto_recover_script_install,
    run_managed_script_install,
    run_script_update,
)
from app.services import script_install
from app.services.script_install_backup import ManagedInstallBackup
from app.core.script_update_recovery import DownloadRetryFailed, InstallInspection
from app.core.ws import protocol
from app.models.config import WhimboxConfig, WhimboxUserConfig
from app.models.notification.report import TaskResultReport
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, UserItem
from app.task.manager_base import ScriptManagerBase
from app.task.proxy_helpers import push_dispatch_log
from app.utils import TASK_MODE_ZH, get_logger
from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed
from app.utils.common.process.runner import is_process_cleanup_unconfirmed

from .AutoProxy import AutoProxyTask
from .ScriptConfig import ScriptConfigTask
from .tools import update as backend_update
from .tools.managed_recovery import WhimboxInstallAdapter
from .tools.update import (
    RECOVERY_HINT,
    WhimboxUpdateUnsafeError,
    confirm_usable_installation,
    ensure_backend_updated,
    installation_access,
    pending_marker,
)
from .tools.upstream import APP_EXE_NAME

logger = get_logger("奇想盒 调度器")


class WhimboxManager(ScriptManagerBase):
    """奇想盒控制器（无限暖暖，PC 前台原生来源线）"""

    async def prefetch_script_update(self) -> None:
        config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        if config.Update.TakeoverEnabled and config.Info.RootPath is not None:
            self._update_candidate = await backend_update.prepare_update(
                config.Info.RootPath
            )

    async def discard_prefetched_update(self) -> None:
        candidate = getattr(self, "_update_candidate", None)
        self._update_candidate = None
        if candidate is not None:
            backend_update.discard_update(candidate)

    def __init__(self, script_info: ScriptItem):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.check_result = "-"
        self.user_config: ConfigCollection[WhimboxUserConfig] | None = None

    async def check(self) -> str:
        if self.execution_mode not in ("AutoProxy", "ScriptConfig"):
            return "不支持的任务模式, 请检查任务配置！"

        script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        if not isinstance(script_config, WhimboxConfig):
            return "托管配置类型错误, 不是奇想盒类型"

        if self.execution_mode == "ScriptConfig":
            if not script_config.Info.RootPath:
                return "请先设置有效的奇想盒安装目录"
            # 只查 app 单哨兵：会话仅拉起 whimbox_app.exe、不依赖 Python 后端，
            # 后端未初始化（首启未完成）时也要能进设置会话去修环境；
            # AutoProxy 走 surface.check_install() 三哨兵——跑一条龙需要完整后端
            root_path = Path(str(script_config.Info.RootPath or ""))
            if not root_path.is_dir() or not (root_path / APP_EXE_NAME).is_file():
                return "请先设置有效的奇想盒安装目录"
            target_user_id = self.task_info.user_id or "Default"
            if target_user_id != "Default":
                try:
                    target_user_uid = uuid.UUID(target_user_id)
                except ValueError:
                    return "奇想盒账号不存在，请刷新后重试"
                if target_user_uid not in script_config.UserData:
                    return "奇想盒账号不存在，请刷新后重试"

        # AutoProxy 模式只做账号列表可用性校验；安装哨兵放到 AutoProxyTask.check()
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
        if not isinstance(self.script_config, WhimboxConfig):
            raise TypeError("托管配置类型错误")

        # X 锁覆盖账号集合，运行时直接修改原配置。
        self.user_config = self.script_config.UserData
        logger.success(f"{self.script_info.script_id} 已锁定，奇想盒账号配置已提取")

        if self.execution_mode == "ScriptConfig":
            target_user_id = self.task_info.user_id or "Default"
            target_user_name = "奇想盒设置"
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
        self.check_result = "奇想盒运行准备未完成"
        await self.prepare()
        root = self.script_config.Info.RootPath
        if root is None:
            raise RuntimeError("请先设置奇想盒安装目录")
        with installation_access(root):
            self.check_result = "Pass"
            await self._run_prepared(root)

    async def _run_prepared(self, root: Path) -> None:
        assert self.user_config is not None

        request = ScriptUpdateRequest(str(self.script_info.script_id), "Whimbox")
        marker = pending_marker(root)
        backup = ManagedInstallBackup(
            root, script_id=request.script_id, script_type="Whimbox"
        )
        if self.execution_mode == "ScriptConfig":
            await self.discard_prefetched_update()

        if self.execution_mode == "ScriptConfig":
            # 保留官方 app 的原生修复入口，未确认后端不能启动一条龙，
            # 但不应阻断用户进入 GUI 自己修复 pip 环境。
            await self.script_info.set_current_index(0)
            await self.spawn(ScriptConfigTask(self.script_info, self.script_config))
            return

        recovered = False
        if backup.read() is not None:
            # 新公共事务优先：下一轮先验证是否成功，否则重试安装，
            # 必要时由公共层执行快照回滚与任务末尾汇总。
            await self.discard_prefetched_update()
            adapter = WhimboxInstallAdapter(root)
            result = await run_managed_script_install(
                request,
                install_root=root,
                inspect=adapter.inspect,
                acknowledge=adapter.acknowledge,
                install=adapter.install,
                ensure_idle=adapter.ensure_idle,
                after_rollback=adapter.after_rollback,
            )
            await push_dispatch_log(self.script_info, f"奇想盒自动恢复：{result}")
            recovered = True
        elif marker.exists() or marker.is_symlink():
            # 兼容升级前留下的旧安装标记。这类记录没有旧版完整快照，
            # 只能强健康检查后确认或重新安装，不得伪造自动回滚。
            await self.discard_prefetched_update()
            adapter = WhimboxInstallAdapter(root)
            result = await auto_recover_script_install(
                request,
                install_root=root,
                inspect=adapter.inspect,
                acknowledge=adapter.acknowledge,
                reinstall=adapter.install,
            )
            await push_dispatch_log(self.script_info, f"奇想盒上次安装恢复：{result}")
            recovered = True

        if self.script_config.Update.TakeoverEnabled and not recovered:
            self.check_result = "奇想盒后端更新未完成"
            await push_dispatch_log(self.script_info, "正在检查奇想盒后端更新…")

            async def prepare_without_installing() -> backend_update.PreparedUpdate | str:
                try:
                    return await backend_update.prepare_update(root)
                except (
                    WhimboxUpdateUnsafeError,
                    script_install.InstallUnsafeError,
                    FluxdownCancelUnconfirmed,
                ):
                    raise
                except Exception as error:
                    if is_process_cleanup_unconfirmed(error):
                        raise
                    # 准备阶段只写隔离下载缓存，不更改安装；由公共入口
                    # 检查旧版健康后决定是否继续并纳入队列最终报告。
                    raise DownloadRetryFailed(
                        source="GitHub/PyPI",
                        reason=f"奇想盒更新包准备失败（{type(error).__name__}）",
                    ) from error

            async def inspect_healthy_previous() -> InstallInspection:
                if backup.read() is not None:
                    raise script_install.InstallUnsafeError("仍有待处理的旧版备份")
                await confirm_usable_installation(root)
                version = await backend_update.installed_version(root)
                return InstallInspection(
                    pending=False,
                    healthy=True,
                    installed_version=str(version),
                    previous_confirmed=True,
                )

            candidate = getattr(self, "_update_candidate", None)
            self._update_candidate = None
            if not isinstance(candidate, backend_update.PreparedUpdate):
                candidate = await run_script_update_with_safe_fallback(
                    request,
                    prepare_without_installing,
                    root,
                    inspect_healthy_previous,
                )
            try:
                if isinstance(candidate, str):
                    # 包准备失败已在公共入口校验、汇报；正常无更新也须核验。
                    await confirm_usable_installation(root)
                    result = candidate
                else:
                    adapter = WhimboxInstallAdapter(
                        root,
                        target=candidate.target,
                        previous=candidate.current,
                        candidate=candidate,
                    )
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
                # 备份建立失败与取消也要清理已下载包，保留未停写缓存
                # 的安全规则仍由 discard_update 统一控制。
                backend_update.discard_update(candidate)
            await push_dispatch_log(self.script_info, str(result))
            self.check_result = "Pass"
        elif marker.exists() or marker.is_symlink():
            raise WhimboxUpdateUnsafeError(RECOVERY_HINT)

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

            method = AutoProxyTask(
                script_info=self.script_info,
                script_config=self.script_config,
                user_config=self.user_config,
            )

            sub_check = await method.check()
            if sub_check != "Pass":
                self.check_result = sub_check
                await self.notify_user_check_failure(current_user, sub_check)
                continue

            await self.run_user_task(current_user, method)

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

            if any(user.status == "异常" for user in self.script_info.user_list):
                await self.script_info.set_state(status="异常")
            else:
                await self.script_info.set_state(status="完成")

            if self.execution_mode == "AutoProxy":
                task_mode = TASK_MODE_ZH[self.execution_mode]
                title = (
                    f"{datetime.now().strftime('%m-%d')} | "
                    f"{self.script_info.name or '空白'}的{task_mode}任务报告"
                )
                result = self.build_proxy_report()

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
        await self.script_info.set_state(status="异常")
        logger.opt(exception=True).warning(f"奇想盒任务出现异常: {e}")
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
                    level="error", message=f"奇想盒任务出现异常: {e}"
                ),
            )
