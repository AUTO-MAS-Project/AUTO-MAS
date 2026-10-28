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

"""宿主装配专项配置能力与用户类；沿用 ScriptConfigHandler 的唯一登记入口。"""

from collections.abc import Callable
from dataclasses import replace

from app.config import ConfigEntry
from app.core.script_config import ScriptConfigHandler
from app.models.config import (
    BAAHConfig,
    BAAHUserConfig,
    BetterGIConfig,
    BetterGIUserConfig,
    GeneralConfig,
    GeneralUserConfig,
    HSRConfig,
    HSRUserConfig,
    MaaConfig,
    MaaEndConfig,
    MaaEndUserConfig,
    MaaFWConfig,
    MaaFWUserConfig,
    MaaUserConfig,
    OkNteConfig,
    OkNteUserConfig,
    OkwwConfig,
    OkwwUserConfig,
    SrcConfig,
    SrcUserConfig,
    WhimboxConfig,
    WhimboxUserConfig,
    ZzzOdConfig,
    ZzzOdUserConfig,
)
from app.task.BAAH.resources import EMULATOR_BINDING as baah_emulator_binding
from app.task.BAAH.resources import declare_task_resources as baah_task_resources
from app.task.BetterGI.api_service import (
    prepare_user_update as prepare_bettergi_user_update,
)
from app.task.general.resources import (
    EMULATOR_BINDING as general_emulator_binding,
)
from app.task.general.resources import (
    declare_task_resources as general_task_resources,
)
from app.task.MAA.resources import EMULATOR_BINDING as maa_emulator_binding
from app.task.MAA.resources import SUPPORTS_MOD_AVD as maa_supports_mod_avd
from app.task.MAA.resources import declare_task_resources as maa_task_resources
from app.task.MAA.user_update import prepare_user_update as prepare_maa_user_update
from app.task.MaaEnd.api_service import MaaEndConfigService
from app.task.MaaEnd.resources import EMULATOR_BINDING as maaend_emulator_binding
from app.task.MaaEnd.resources import declare_task_resources as maaend_task_resources
from app.task.MaaFW.tools.embedded.default_snapshot import (
    initialize_user as initialize_maafw_user,
)
from app.task.MaaFW.tools.embedded.default_snapshot import (
    prepare_user_read as prepare_maafw_user_read,
)
from app.task.MaaFW.tools.embedded.resources import (
    EMULATOR_BINDING as maafw_emulator_binding,
)
from app.task.MaaFW.tools.embedded.resources import (
    SUPPORTS_MOD_AVD as maafw_supports_mod_avd,
)
from app.task.MaaFW.tools.embedded.resources import (
    declare_task_resources as maafw_task_resources,
)
from app.task.MaaFW.tools.embedded.script_lifecycle import (
    after_script_removal as after_maafw_script_removal,
)
from app.task.MaaFW.tools.embedded.script_lifecycle import (
    cleanup_script_files as cleanup_maafw_script_files,
)
from app.task.MaaFW.tools.embedded.script_lifecycle import (
    clone_script as clone_maafw_script,
)
from app.task.MaaFW.tools.embedded.user_update import (
    prepare_user_update as prepare_maafw_user_update,
)
from app.task.Okww.tools.config_dir import (
    import_config as import_okww_config,
)
from app.task.Okww.tools.config_dir import (
    initialize_user as initialize_okww_user,
)
from app.task.SRC.resources import EMULATOR_BINDING as src_emulator_binding
from app.task.SRC.resources import declare_task_resources as src_task_resources
from app.task.SRC.user_update import prepare_user_update as prepare_src_user_update
from app.task.ZzzOd.recovery import ZzzOdRecovery
from app.task.ZzzOd.user_update import prepare_user_update as prepare_zzzod_user_update


def bind_script_config_handlers(
    bind: Callable[[type[ConfigEntry], ScriptConfigHandler], None],
    *,
    maaend: MaaEndConfigService,
    zzzod: ZzzOdRecovery,
) -> None:
    """只注入专项所需能力，不把配置总管交给专项。"""
    handlers = {
        MaaEndConfig: ScriptConfigHandler(
            user_config_class=MaaEndUserConfig,
            initialize=maaend.initialize,
            validate_update=maaend.validate_update,
            import_config=maaend.import_config,
            task_resources=maaend_task_resources,
            emulator_binding=maaend_emulator_binding,
        ),
        BetterGIConfig: ScriptConfigHandler(
            user_config_class=BetterGIUserConfig,
            prepare_user_update=prepare_bettergi_user_update,
        ),
        MaaConfig: ScriptConfigHandler(
            user_config_class=MaaUserConfig,
            prepare_user_update=prepare_maa_user_update,
            task_resources=maa_task_resources,
            emulator_binding=maa_emulator_binding,
            supports_mod_avd=maa_supports_mod_avd,
        ),
        SrcConfig: ScriptConfigHandler(
            user_config_class=SrcUserConfig,
            prepare_user_update=prepare_src_user_update,
            task_resources=src_task_resources,
            emulator_binding=src_emulator_binding,
        ),
        ZzzOdConfig: ScriptConfigHandler(
            user_config_class=ZzzOdUserConfig,
            prepare_script_removal=zzzod.prepare_script_removal,
            prepare_user_update=prepare_zzzod_user_update,
            prepare_user_removal=zzzod.prepare_user_removal,
        ),
        MaaFWConfig: ScriptConfigHandler(
            user_config_class=MaaFWUserConfig,
            clone_script=clone_maafw_script,
            after_script_removal=after_maafw_script_removal,
            prepare_user_update=prepare_maafw_user_update,
            prepare_user_read=prepare_maafw_user_read,
            initialize_user=initialize_maafw_user,
            task_resources=maafw_task_resources,
            emulator_binding=maafw_emulator_binding,
            supports_mod_avd=maafw_supports_mod_avd,
        ),
        OkwwConfig: ScriptConfigHandler(
            user_config_class=OkwwUserConfig,
            initialize_user=initialize_okww_user,
            import_config=import_okww_config,
        ),
        GeneralConfig: ScriptConfigHandler(
            user_config_class=GeneralUserConfig,
            task_resources=general_task_resources,
            emulator_binding=general_emulator_binding,
        ),
        OkNteConfig: ScriptConfigHandler(user_config_class=OkNteUserConfig),
        HSRConfig: ScriptConfigHandler(user_config_class=HSRUserConfig),
        BAAHConfig: ScriptConfigHandler(
            user_config_class=BAAHUserConfig,
            task_resources=baah_task_resources,
            emulator_binding=baah_emulator_binding,
        ),
        WhimboxConfig: ScriptConfigHandler(user_config_class=WhimboxUserConfig),
    }
    for entry_type, handler in handlers.items():
        # 沿用旧删除行为：所有脚本 UUID 都清理可能残留的 MFW 视图，只有
        # MaaFW 类型删除后触发运行池对账。具体目录和删除规则仍由 MFW 持有。
        bind(
            entry_type,
            replace(handler, cleanup_script_files=cleanup_maafw_script_files),
        )
