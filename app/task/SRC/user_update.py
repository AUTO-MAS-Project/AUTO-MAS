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

"""SRC 用户配置更新策略。"""

from typing import Any, cast

from app.config import ConfigEntry
from app.models.config import SrcConfig, SrcUserConfig
from app.utils import constants as _utils_constants


def prepare_user_update(
    script: ConfigEntry, user: ConfigEntry, *, data: dict[str, Any]
) -> None:
    """校验原生来源占用，并准备本专项的用户补丁。"""
    script_config = cast(SrcConfig, script)
    user_config = cast(SrcUserConfig, user)
    new_base = _utils_constants.normalize_base_source(
        data.get("Info", {}).get("Base", "")
    )
    if (
        new_base == _utils_constants.BASE_NATIVE
        and _utils_constants.normalize_base_source(
            user_config.Info.Base or _utils_constants.BASE_INDEPENDENT
        )
        != _utils_constants.BASE_NATIVE
        and any(
            (
                _utils_constants.normalize_base_source(
                    cfg.Info.Base or _utils_constants.BASE_INDEPENDENT
                )
                == _utils_constants.BASE_NATIVE
                for uid, cfg in script_config.UserData.items()
                if uid != user.uid
            )
        )
    ):
        raise ValueError(
            "每个脚本仅允许一个原生来源用户, 多账号请在该用户的实例管理中配置"
        )
