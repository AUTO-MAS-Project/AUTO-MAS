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

"""MFW 家族托管的配置回调与恢复池（宿主接缝，不归入积木）。

三种托管类型（通用 MFW、M9A、MSS）都从这里取（M9A 经自己的 ``config_hooks``）：
:func:`build_maafw_config_handler` 按确切类型与属主名各造一份配置回调，:func:`load_maafw_restore_pools`
给出 MFW 的恢复池。有自己流程的专项要换掉其中一项时用 ``dataclasses.replace``（``ScriptConfigHandler``
是 frozen dataclass），恢复池用 ``tools/restore_service`` 公开的部件自己拼，不往这里加参数。

**启动期就会被导入**（``builtin_registration`` 导入各 registration、调 ``create_config_handler()``），所以
顶层只放轻量导入，回调的实现都在函数里延迟导入。
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from app.models.script_contracts import ScriptConfigHandler

if TYPE_CHECKING:
    from app.config import ConfigEntry
    from app.utils.common.config.restore import ConfigRestorePool


def build_maafw_config_handler(
    config_type: type[ConfigEntry], *, owner: str
) -> ScriptConfigHandler:
    """一种托管类型的配置回调：保存前加密密码、读取前准备、新账号补默认队列、复制托管时克隆
    视图（新视图记本属主）、删除托管时清理视图（只删本属主的视图）与删除后的运行池对账。三种类型各造
    一份，内容相同。"""

    from app.task.MaaFW.seams.default_snapshot import (
        initialize_user as initialize_maafw_user,
    )
    from app.task.MaaFW.seams.default_snapshot import (
        prepare_user_read as prepare_maafw_user_read,
    )
    from app.task.MaaFW.seams.script_lifecycle import (
        after_script_removal as after_maafw_script_removal,
    )
    from app.task.MaaFW.seams.script_lifecycle import (
        cleanup_script_files as cleanup_maafw_script_files,
    )
    from app.task.MaaFW.seams.script_lifecycle import (
        clone_script as clone_maafw_script,
    )
    from app.task.MaaFW.seams.user_update import (
        prepare_user_update as prepare_maafw_user_update,
    )

    return ScriptConfigHandler(
        # 宿主建号先取类上的 USER_CONFIG_CLASS，这一项只是兜底
        user_config_class=getattr(config_type, "USER_CONFIG_CLASS"),
        clone_script=partial(clone_maafw_script, owner=owner),
        after_script_removal=after_maafw_script_removal,
        cleanup_script_files=partial(cleanup_maafw_script_files, owner=owner),
        prepare_user_update=prepare_maafw_user_update,
        prepare_user_read=prepare_maafw_user_read,
        initialize_user=initialize_maafw_user,
        game_kinds=("emulator", "client"),
        expected_game_kind=expected_game_kind,
        supports_mod_avd=True,
    )


def expected_game_kind(script, patch):
    """显式选择的公开 controller 决定目标类别，未导入项目时保留两类选择。"""
    from app.task.MaaFW.blocks.maafw_interface.interface.loader import (
        load_interface_model_cached,
    )
    from app.task.MaaFW.blocks.maafw_project_update.host.embedded_project import (
        resolve_maafw_project_root,
    )

    controller = patch.get("Info", {}).get("Controller", script.Info.Controller)
    if not controller:
        return None
    root = resolve_maafw_project_root(str(script.uid), script)
    if not root.is_dir():
        return None
    interface = load_interface_model_cached(root)
    selected = next(
        (item for item in interface.controller if item.name == controller), None
    )
    if selected is None:
        return None
    return "emulator" if selected.type == "Adb" else "client"


def load_maafw_restore_pools() -> list[ConfigRestorePool]:
    """MFW 的两个恢复池（MAS 账号字段池、项目配置池），见 ``tools/restore_service``。"""

    from app.task.MaaFW.seams.restore_service import RESTORE_POOLS

    return RESTORE_POOLS


__all__ = [
    "build_maafw_config_handler",
    "expected_game_kind",
    "load_maafw_restore_pools",
]
