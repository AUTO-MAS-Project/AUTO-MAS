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

"""M9A 特调：MaaFW 引擎之上唯一的运行期专项逻辑，以及"这是不是 M9A 项目"的判据。

「启动游戏」（entry ``StartUp``）、「切换账号」（entry ``SwitchAccount``）、「关闭游戏」
（entry ``Close1999``）由 MAS 全权控制（规则见 ``managed.py``）。运行前先把勾选列表里这三类
全部剔掉，再按固定顺序补：启动放队首；脚本资源为官服、账号非空且没开「MAS 登录」时切号紧跟启动，
账号填进它唯一的 input 选项；关闭放队尾。用户排的顺序不影响这三项。队列里有多个有效切号的用户拒绝运行。

``Run.LoginMode`` 为 ``Mas`` 时（B 服登录由 MAS 完成，见 ``login.py``）：不再补「切换账号」，
``Info.Id`` 是 MAS 登录要选中的哔哩哔哩昵称；启动 / 关闭照常补，登录完成后 ``StartUp``
负责从标题页进游戏，随后跑用户任务。

按 entry 而不是按任务名找：任务名会随 M9A 的版本与语言变，entry 是它的 pipeline 入口，稳定。

另实现了引擎的两个可选钩子：``sanitize_task_snapshot``（写账号任务快照前按同一规则整理）与
``ensure_game_updated``（脚本开了游戏更新时，模拟器启动后比对官服客户端版本，落后就提示或
下载安装，``game_update.py``）；并给了引擎的五项可选声明：``abort_round_entries``（切号失败结束本轮）、
``nonfatal_entries``（关闭游戏失败不算失败）、
``skip_on_retry_entries``（完成过的重试不补跑）、``unselectable_entries``（五个小游戏不可选、
运行时跳过）、``no_default_fallback_inputs``（自定义兑换码没填不回落「占位」），契约都在 MaaFW ``tools/embedded/flavor.py`` 的模块说明里。除这些之外 M9A 与
通用 MaaFW 没有运行期差别。

这里只是 MFW 风味路径上的一层外壳：规则常量与项目判据在 ``rules.py``，排队列与保存前整理在
``arrange.py``，登录的两种结局在 ``startup.py``；本模块从配置里取出登录方式与账号后转调它们。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.task.M9A.arrange import arrange_m9a_queue, settle_m9a_snapshot
from app.task.M9A.managed import (
    CLOSE_ENTRY,
    MANAGED_ENTRIES,
    OFFICIAL_RESOURCE_NAME,
    STARTUP_ENTRY,
    SWITCH_ACCOUNT_ENTRY,
)
from app.task.M9A.rules import (
    FALLBACK_TASK_NAMES,
    LEGACY_ENTRY_ALIASES,
    M9A_ABORT_ROUND_ENTRIES,
    M9A_NO_DEFAULT_FALLBACK_INPUTS,
    M9A_NONFATAL_ENTRIES,
    M9A_SKIP_ON_RETRY,
    M9A_UNSELECTABLE_ENTRIES,
    TYPE_KEY,
    is_m9a_project,
)
from app.task.MaaFW.tools.core.interface.models import (
    MaaFWInterface,
    task_name_for_entry,
)
from app.task.MaaFW.tools.embedded.flavor import StartupTask
from app.task.MaaFW.tools.embedded.flavor_support import config_value

if TYPE_CHECKING:
    from app.task.MaaFW.tools.embedded.flavor_support import MaaFWSelectionContext
    from app.utils import game_update as _utils_game_update


class M9AFlavor:
    """满足 ``MaaFWFlavor`` 协议的 M9A 特调对象。

    声明属性与 ``rules.py`` 是同一份常量（说明写在那里），两个方法转调 ``arrange.py``。
    """

    type_key = TYPE_KEY
    abort_round_entries = M9A_ABORT_ROUND_ENTRIES
    nonfatal_entries = M9A_NONFATAL_ENTRIES
    skip_on_retry_entries = M9A_SKIP_ON_RETRY
    unselectable_entries = M9A_UNSELECTABLE_ENTRIES
    no_default_fallback_inputs = M9A_NO_DEFAULT_FALLBACK_INPUTS

    def matches_project(self, interface_model: MaaFWInterface) -> bool:
        return is_m9a_project(interface_model)

    def decorate_selection(
        self,
        interface_model: MaaFWInterface,
        task_ids: list[str],
        task_options: dict[str, Any],
        *,
        context: MaaFWSelectionContext,
    ) -> tuple[list[str], dict[str, Any]]:
        return arrange_m9a_queue(
            interface_model,
            task_ids,
            task_options,
            resource_name=context.resource_name,
            login_mode=_login_mode(context.script_config),
            user_account=str(
                config_value(context.user_config, "Info", "Id") or ""
            ).strip(),
            log=context.log,
        )

    def sanitize_task_snapshot(
        self,
        interface_model: MaaFWInterface,
        snapshot: dict[str, Any],
        *,
        script_config: Any,
        resource_name: str | None,
        user_info: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """引擎的可选钩子：写 ``Task.TaskSnapshot`` 前按 ``managed.py`` 的规则整理（``arrange.py``）。"""

        return settle_m9a_snapshot(
            interface_model,
            snapshot,
            resource_name=resource_name,
            login_mode=_login_mode(script_config),
            user_info=user_info,
        )

    async def ensure_logged_in(
        self,
        *,
        script_config: Any,
        user_config: Any,
        resource_name: str | None,
        package_name: str | None,
        adb_path: str | None,
        adb_address: str,
        progress: Callable[[str], Awaitable[None]] | None,
        host_adb: Any = None,
    ) -> str | StartupTask:
        """引擎的可选运行前登录钩子：B 服登录由 MAS 完成，契约见 MaaFW 的 ``flavor.py``。"""

        # 按需导入：本包在导入期不拉起 OCR / 图像与 adb 相关模块（配置回调与预览也会导入 flavor）
        from .login import ensure_logged_in
        from .startup import M9AStartupTask

        result = await ensure_logged_in(
            script_config=script_config,
            user_config=user_config,
            resource_name=resource_name,
            package_name=package_name,
            adb_path=adb_path,
            adb_address=adb_address,
            progress=progress,
            host_adb=host_adb,
        )
        # 登录模块给的是 M9A 自己的类型，引擎认的是风味的 StartupTask
        if isinstance(result, M9AStartupTask):
            return StartupTask(result.deadline, result.entry)
        return result

    async def ensure_game_updated(
        self,
        *,
        script_config: Any,
        resource_name: str | None,
        package_name: str,
        adb_path: str | None,
        adb_address: str,
        if_auto_install: bool,
        progress: Callable[[str], Awaitable[None]] | None,
    ) -> _utils_game_update.GameUpdateResult:
        """引擎的可选游戏更新钩子：只查官服，契约见 MaaFW 的 ``flavor.py`` 模块说明。"""

        # 按需导入：本包在导入期不拉起网络与 adb 相关模块（配置回调与预览也会导入 flavor）
        from .game_update import ensure_game_updated

        del script_config  # 资源名由引擎按脚本配置解析后传入
        return await ensure_game_updated(
            adb_path=Path(adb_path) if adb_path else None,
            adb_address=adb_address,
            resource_name=resource_name,
            package_name=package_name,
            official_resource_name=OFFICIAL_RESOURCE_NAME,
            apk_dir=Path.cwd() / "data/GameApk",
            if_auto_install=if_auto_install,
            progress=progress,
        )


def _login_mode(script_config: Any) -> str:
    """``Run.LoginMode``；假配置对象缺项时按项目自登录（``Project``）处理。"""

    return str(config_value(script_config, "Run", "LoginMode") or "").strip()


FLAVOR = M9AFlavor()

__all__ = [
    "CLOSE_ENTRY",
    "FALLBACK_TASK_NAMES",
    "FLAVOR",
    "LEGACY_ENTRY_ALIASES",
    "M9AFlavor",
    "MANAGED_ENTRIES",
    "OFFICIAL_RESOURCE_NAME",
    "STARTUP_ENTRY",
    "SWITCH_ACCOUNT_ENTRY",
    "TYPE_KEY",
    "is_m9a_project",
    "task_name_for_entry",
]
