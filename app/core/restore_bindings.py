#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License
#   as published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""宿主内置恢复池装配：按脚本配置选择现有专项池表。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.config import (
    BAAHConfig,
    BetterGIConfig,
    GeneralConfig,
    HSRConfig,
    MaaConfig,
    MaaEndConfig,
    MaaFWConfig,
    OkNteConfig,
    OkwwConfig,
    SrcConfig,
    WhimboxConfig,
    ZzzOdConfig,
)

if TYPE_CHECKING:
    from app.models.ConfigBase import ConfigBase
    from app.utils.config_restore import ConfigRestorePool


def resolve_restore_pools(script_config: ConfigBase) -> list[ConfigRestorePool]:
    """匹配后才导入专项池，保留继承匹配与池表顺序。"""

    if isinstance(script_config, ZzzOdConfig):
        from app.task.ZzzOd.tools.restore_service import RESTORE_POOLS
    elif isinstance(script_config, OkNteConfig):
        from app.task.OkNte.tools.restore_service import RESTORE_POOLS
    elif isinstance(script_config, OkwwConfig):
        from app.task.Okww.tools.restore_service import RESTORE_POOLS
    elif isinstance(script_config, MaaConfig):
        from app.task.MAA.tools.restore_service import RESTORE_POOLS
    elif isinstance(script_config, MaaEndConfig):
        from app.task.MaaEnd.tools.restore_service import RESTORE_POOLS
    elif isinstance(script_config, GeneralConfig):
        from app.task.general.tools.restore_service import RESTORE_POOLS
    elif isinstance(script_config, BAAHConfig):
        from app.task.BAAH.tools.restore_service import RESTORE_POOLS
    elif isinstance(script_config, SrcConfig):
        from app.task.SRC.tools.restore_service import RESTORE_POOLS
    elif isinstance(script_config, BetterGIConfig):
        from app.task.BetterGI.tools.restore_service import RESTORE_POOLS
    elif isinstance(script_config, MaaFWConfig):
        # M9A、MSS 等 MaaFW 特调沿用引擎池。
        from app.task.MaaFW.tools.restore_service import RESTORE_POOLS
    elif isinstance(script_config, HSRConfig):
        from app.task.HSR.tools.restore_service import RESTORE_POOLS
    elif isinstance(script_config, WhimboxConfig):
        from app.task.Whimbox.tools.restore_service import RESTORE_POOLS
    else:
        raise ValueError("该专项暂不支持配置恢复")
    return RESTORE_POOLS
