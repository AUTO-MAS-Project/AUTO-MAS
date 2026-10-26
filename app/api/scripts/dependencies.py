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
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.
#   Contact: DLmaster_361@163.com

"""脚本路由的依赖组装：连接通用编辑用例与具体专项策略。"""

from app.core import Config, emulator2
from app.core.script_settings import ScriptSettings
from app.models.config import BetterGIConfig
from app.task.BetterGI.api_service import prepare_user_update

_script_settings = ScriptSettings(
    gateway=Config,
    validate_binding=emulator2.mod_avd_binding_error,
    user_preparers={BetterGIConfig: prepare_user_update},
)


def get_script_settings() -> ScriptSettings:
    return _script_settings
