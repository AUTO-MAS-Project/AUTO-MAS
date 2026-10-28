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
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""ZZZ-OD 用户更新策略，不接触原生文件或提交配置。"""

from typing import Any, cast

from app.config import ConfigEntry
from app.models.config import ZzzOdConfig, ZzzOdUserConfig
from app.utils import constants as _utils_constants


def prepare_user_update(
    script: ConfigEntry, user: ConfigEntry, *, data: dict[str, Any]
) -> None:
    """原生来源只保留一个用户，并关闭不参与原生运行的注入配置。"""
    script_config = cast(ZzzOdConfig, script)
    user_config = cast(ZzzOdUserConfig, user)
    new_base = _utils_constants.normalize_base_source(data.get("Info", {}).get("Base"))
    if new_base == _utils_constants.BASE_NATIVE:
        data.setdefault("OneDragon", {})["AppList"] = "[]"
        # 直控恒为纯原生裸跑，旧快速配置开关归关。
        data.setdefault("Info", {})["IfQuickConfig"] = False
    if (
        new_base == _utils_constants.BASE_NATIVE
        and _utils_constants.normalize_base_source(
            user_config.Info.Base or _utils_constants.BASE_INDEPENDENT
        )
        != _utils_constants.BASE_NATIVE
        and any(
            _utils_constants.normalize_base_source(
                cfg.Info.Base or _utils_constants.BASE_INDEPENDENT
            )
            == _utils_constants.BASE_NATIVE
            for other_uid, cfg in script_config.UserData.items()
            if other_uid != user.uid
        )
    ):
        raise ValueError(
            "每个脚本仅允许一个原生来源用户, 多账号请在该用户的实例管理中配置"
        )
