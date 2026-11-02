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
from app.core.ws import protocol
from app.models.config import WhimboxConfig, WhimboxUserConfig
from app.models.notification.report import TaskResultReport
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, UserItem
from app.task.manager_base import ScriptManagerBase
from app.task.proxy_helpers import push_dispatch_log
from app.utils import TASK_MODE_ZH, get_logger
from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed

from .AutoProxy import AutoProxyTask
from .ScriptConfig import ScriptConfigTask
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

    def __init__(self, script_info: ScriptItem):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.check_result = "-"
        self.user_config: ConfigCollection[WhimboxUserConfig] | None = None

    async def check(self) -> str:
        if self.task_info.mode not in ("AutoProxy", "ScriptConfig"):
            return "不支持的任务模式, 请检查任务配置！"

        script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        if not isinstance(script_config, WhimboxConfig):
            return "脚本配置类型错误, 不是奇想盒类型"

        if self.task_info.mode == "ScriptConfig":
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
                    return "奇想盒用户不存在，请刷新后重试"
                if target_user_uid not in script_config.UserData:
                    return "奇想盒用户不存在，请刷新后重试"

        # AutoProxy 模式只做用户列表可用性校验；安装哨兵放到 AutoProxyTask.check()
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
        if not isinstance(self.script_config, WhimboxConfig):
            raise TypeError("脚本配置类型错误")

        # X 锁覆盖用户集合，运行时直接修改原配置。
        self.user_config = self.script_config.UserData
        logger.success(f"{self.script_info.script_id} 已锁定，奇想盒用户配置已提取")

        if self.task_info.mode == "ScriptConfig":
            target_user_id = self.task_info.user_id or "Default"
            target_user_name = "奇想盒设置"
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

        if self.task_info.mode == "ScriptConfig":
            self.script_info.current_index = 0
            await self.spawn(
                ScriptConfigTask(
                    self.script_info,
                    self.script_config,
                )
            )
            return

        if self.script_config.Update.TakeoverEnabled:
            self.check_result = "奇想盒后端更新未完成"
            await push_dispatch_log(self.script_info, "正在检查奇想盒后端更新…")
            try:
                result = await ensure_backend_updated(root)
            except (WhimboxUpdateUnsafeError, FluxdownCancelUnconfirmed):
                raise
            except Exception as error:
                await confirm_usable_installation(root)
                result = f"奇想盒更新未完成，沿用当前后端继续任务。原因：{error}"
                self.script_info.log = result
                logger.warning(result)
                with suppress(Exception):
                    await Publisher.send(
                        id=self.task_info.task_id,
                        type=protocol.TASK_NOTICE,
                        data=WSTaskNoticeData(level="warning", message=result),
                    )
            else:
                await push_dispatch_log(self.script_info, result)
            self.check_result = "Pass"
        elif pending_marker(root).exists():
            self.check_result = RECOVERY_HINT
            raise RuntimeError(self.check_result)

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
                self.check_result = sub_check
                await self.notify_user_check_failure(current_user, sub_check)
                continue

            await self.run_user_task(current_user, method)

    async def final_task(self):
        try:
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
            else:
                self.script_info.status = "完成"

            if self.task_info.mode == "AutoProxy":
                task_mode = TASK_MODE_ZH[self.task_info.mode]
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
        self.script_info.status = "异常"
        logger.opt(exception=True).warning(f"奇想盒任务出现异常: {e}")
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
                    level="error", message=f"奇想盒任务出现异常: {e}"
                ),
            )
