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
from app.task.BetterGI.api_service import (
    prepare_user_update as prepare_bettergi_user_update,
)
from app.task.MAA.user_update import prepare_user_update as prepare_maa_user_update
from app.task.MaaEnd.api_service import MaaEndConfigService
from app.task.MaaFW.tools.embedded.default_snapshot import (
    initialize_user as initialize_maafw_user,
)
from app.task.MaaFW.tools.embedded.default_snapshot import (
    prepare_user_read as prepare_maafw_user_read,
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
        ),
        BetterGIConfig: ScriptConfigHandler(
            user_config_class=BetterGIUserConfig,
            prepare_user_update=prepare_bettergi_user_update,
        ),
        MaaConfig: ScriptConfigHandler(
            user_config_class=MaaUserConfig,
            prepare_user_update=prepare_maa_user_update,
        ),
        SrcConfig: ScriptConfigHandler(
            user_config_class=SrcUserConfig,
            prepare_user_update=prepare_src_user_update,
        ),
        ZzzOdConfig: ScriptConfigHandler(
            user_config_class=ZzzOdUserConfig,
            prepare_user_update=prepare_zzzod_user_update,
            prepare_user_removal=zzzod.prepare_user_removal,
        ),
        MaaFWConfig: ScriptConfigHandler(
            user_config_class=MaaFWUserConfig,
            prepare_user_update=prepare_maafw_user_update,
            prepare_user_read=prepare_maafw_user_read,
            initialize_user=initialize_maafw_user,
        ),
        OkwwConfig: ScriptConfigHandler(
            user_config_class=OkwwUserConfig,
            initialize_user=initialize_okww_user,
            import_config=import_okww_config,
        ),
        GeneralConfig: ScriptConfigHandler(user_config_class=GeneralUserConfig),
        OkNteConfig: ScriptConfigHandler(user_config_class=OkNteUserConfig),
        HSRConfig: ScriptConfigHandler(user_config_class=HSRUserConfig),
        BAAHConfig: ScriptConfigHandler(user_config_class=BAAHUserConfig),
        WhimboxConfig: ScriptConfigHandler(user_config_class=WhimboxUserConfig),
    }
    for entry_type, handler in handlers.items():
        bind(entry_type, handler)
