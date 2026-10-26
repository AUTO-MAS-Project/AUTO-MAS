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
"""MaaEnd 安装路径识别入口。"""

import uuid
from pathlib import Path

from app.core import Config
from app.models.config import MaaEndConfig as RuntimeMaaEndConfig
from app.services.endfield_launcher import discover_launcher_exe


def resolve_launcher_path(script_id: str) -> Path:
    script_uid = uuid.UUID(script_id)
    script_config = Config.ScriptConfig[script_uid]
    if not isinstance(script_config, RuntimeMaaEndConfig):
        raise TypeError("脚本配置类型错误, 不是 MaaEnd 类型")
    client_exe = Path(str(script_config.Game.Path or "").strip())
    if not client_exe.is_file():
        raise ValueError("请先选择终末地客户端 Endfield.exe，再自动识别启动器")
    launcher_path = discover_launcher_exe(client_exe)
    if launcher_path is None:
        raise ValueError(
            "未能从游戏客户端路径识别到终末地官方启动器, "
            "请手动选择终末地启动器的可执行文件（.exe）"
        )
    return launcher_path
