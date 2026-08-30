#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""MaaFW 第二层（内置运行 embedded）任务管理器。

第一层由 ``manager.MaaFWManager`` 启动项目自己的 UI shell；本层在 MAS 自己的
worker 子进程内加载项目的 MaaFramework 直接驱动，编排实现在
``tools/embedded/runner_task.py``。

`task_manager` 按 ``Run.Engine`` 在两者之间分派，**第一层路径完全不经过本文件**。

⚠️ 实验性：本层尚未经过真机验证，默认引擎仍是 ``external``。

``tools/embedded.runner_task`` 会经 runner 包 import ``maa``（导入即打开 DLL），
因此本模块**只在 check() 通过后才延迟导入它**，让第一层与所有不启用 embedded
的进程都不承担这个代价。
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core import Config
from app.models.ConfigBase import MultipleConfig
from app.models.config import MaaFWConfig, MaaFWUserConfig
from app.models.emulator import DeviceBase
from app.models.task import ScriptItem, TaskExecuteBase, UserItem
from app.utils import get_logger

if TYPE_CHECKING:  # pragma: no cover - 仅供类型检查，运行期不导入 maa
    from app.task.MaaFW.tools.embedded.runner_task import MaaFWPluginAutoProxyTask

logger = get_logger("MFW 内置运行")

ENGINE_VALUE = "embedded"


class MaaFWEmbeddedManager(TaskExecuteBase):
    """MaaFW 内置运行（第二层）管理器。

    只负责把脚本配置、用户配置和模拟器实例装配好，运行编排全部交给
    ``MaaFWPluginAutoProxyTask``。
    """

    wait_for_finalizer_on_cancel = True

    def __init__(self, script_info: ScriptItem):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.check_result: str = "-"

        self.script_config: MaaFWConfig | None = None
        self.user_config: MultipleConfig[MaaFWUserConfig] | None = None
        self.runnable_user_uids: list[uuid.UUID] = []
        self.emulator_manager: DeviceBase | None = None
        # 当前正在跑的那一位用户的 AutoProxy 任务；每个用户各建一个。
        self.inner_task: "MaaFWPluginAutoProxyTask | None" = None
        self._inner_finalized = True

    async def check(self) -> str:
        """校验 embedded 运行的前置条件，返回 ``"Pass"`` 或用户可读的原因。"""

        if self.task_info.mode != "AutoProxy":
            return "MFW 内置运行当前仅支持自动代理模式"

        try:
            script_uid = uuid.UUID(self.script_info.script_id)
        except (ValueError, AttributeError, TypeError):
            return "MFW 脚本 ID 无效，请刷新后重试"

        try:
            script_config = Config.ScriptConfig[script_uid]
        except (KeyError, ValueError):
            return "MFW 脚本配置不存在，请刷新后重试"

        if not isinstance(script_config, MaaFWConfig):
            return "脚本配置类型错误，不是 MFW 脚本类型"
        self.script_config = script_config

        if script_config.get("Run", "Engine") != ENGINE_VALUE:
            return "当前脚本未启用 MFW 内置运行引擎"

        project_value = str(script_config.get("Info", "Path") or "").strip()
        if not project_value:
            return "请设置 MFW 项目路径"
        if not Path(project_value).resolve().is_dir():
            return "请设置包含 interface.json 的 MFW 项目目录"

        user_config: MultipleConfig[MaaFWUserConfig] = MultipleConfig([MaaFWUserConfig])
        await user_config.load(await script_config.UserData.toDict())
        self.user_config = user_config

        # 与第一层同一套筛选口径（manager.py 的 runnable_uids）。
        self.runnable_user_uids = [
            uid
            for uid, cfg in user_config.data.items()
            if cfg.get("Info", "Status") and cfg.get("Info", "RemainedDay") != 0
        ]
        if not self.runnable_user_uids:
            return "MFW 没有可运行的用户，请在用户管理页添加并启用至少一个用户"

        self.emulator_manager = await self._resolve_emulator_manager(script_config)
        return "Pass"

    @staticmethod
    async def _resolve_emulator_manager(
        script_config: MaaFWConfig,
    ) -> DeviceBase | None:
        """按脚本级模拟器配置取实例；未配置时返回 None。

        ADB controller 缺模拟器时由 runner_task 自己抛出可读错误，这里不预判
        controller 类型 —— 判定要读 interface，属于运行编排的职责。
        """

        emulator_id = str(script_config.get("Emulator", "Id") or "").strip()
        if not emulator_id or emulator_id == "-":
            return None

        from app.core import EmulatorManager

        try:
            return await EmulatorManager.get_emulator_instance(emulator_id)
        except Exception as exc:  # noqa: BLE001 - 缺模拟器不该拦住 Win32 项目
            logger.warning(f"MFW 内置运行取模拟器实例失败，将按无模拟器继续：{exc}")
            return None

    def _build_inner_task(self) -> "MaaFWPluginAutoProxyTask":
        # 延迟导入：runner_task 经 runner 包 import maa，导入即打开 DLL。
        from app.task.MaaFW.tools.embedded.runner_task import (
            MaaFWPluginAutoProxyTask,
        )

        assert self.script_config is not None
        assert self.user_config is not None
        return MaaFWPluginAutoProxyTask(
            self.script_info,
            self.script_config,
            self.user_config.data,
            self.emulator_manager,
        )

    async def main_task(self) -> None:
        self.check_result = await self.check()
        if self.check_result != "Pass":
            self.script_info.status = "异常"
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": self.check_result},
            )
            return

        # task_manager 只放了一个「暂未加载」占位项，真实用户列表由各 manager
        # 自己填（与 manager.py 的做法一致）。AutoProxy 任务按 current_index
        # 取当前用户，这一步不做后面必然取到占位项、拿它的随机 uid 去查
        # user_config 而 KeyError。
        assert self.user_config is not None
        self.script_info.user_list = [
            UserItem(
                user_id=str(uid),
                name=self.user_config[uid].get("Info", "Name"),
                status="等待",
            )
            for uid in self.runnable_user_uids
        ]
        self.script_info.status = "运行"
        logger.info(
            f"MFW 内置运行用户列表加载完成，已筛选用户数: "
            f"{len(self.script_info.user_list)}"
        )

        # AutoProxy 的 main_task / final_task 都是**按用户**的（final_task 会
        # 结算该用户的代理次数、剩余天数并释放项目锁），因此每个用户各建一个。
        for index in range(len(self.runnable_user_uids)):
            self.script_info.current_index = index
            self.inner_task = self._build_inner_task()
            self._inner_finalized = False
            try:
                await self.inner_task.main_task()
            # 只截 Exception：CancelledError 属 BaseException，必须继续外抛，
            # 否则基类的取消路径与下面的收尾保证一起失效。
            except Exception as exc:  # noqa: BLE001
                await self.inner_task.on_crash(exc)
            finally:
                await self._finalize_inner_task()

    async def _finalize_inner_task(self) -> None:
        """收尾当前用户的 AutoProxy 任务；对同一个任务只做一次。"""

        if self.inner_task is None or self._inner_finalized:
            return
        self._inner_finalized = True
        try:
            await self.inner_task.final_task()
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=True).warning(f"MFW 内置运行收尾异常：{exc}")

    async def final_task(self) -> None:
        # 正常路径下每个用户跑完就已收尾；这里只兜取消与异常路径的最后一位用户。
        await self._finalize_inner_task()
        for user in self.script_info.user_list:
            if user.status in ("等待", "运行"):
                user.status = "异常"

    async def on_crash(self, e: Exception) -> None:
        logger.exception(f"MFW 内置运行异常：{e}")
        if self.inner_task is not None and not self._inner_finalized:
            await self.inner_task.on_crash(e)
            return
        self.script_info.status = "异常"


__all__ = ["ENGINE_VALUE", "MaaFWEmbeddedManager"]
