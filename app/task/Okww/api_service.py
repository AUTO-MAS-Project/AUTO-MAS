#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
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
"""Okww 安装路径识别入口。"""

import uuid
from pathlib import Path

from app.core import Config
from app.models.config import OkwwConfig as RuntimeOkwwConfig
from app.services import wuthering_waves as _service_wuthering_waves


def resolve_client_path(script_id: str) -> Path:
    script_config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(script_config, RuntimeOkwwConfig):
        raise TypeError("脚本配置类型错误, 不是 OK-WW 类型")
    launcher_path = Path(str(script_config.Game.Path or "").strip())
    client_path = _service_wuthering_waves.resolve_wuthering_waves_process_path(
        launcher_path
    )
    return client_path
