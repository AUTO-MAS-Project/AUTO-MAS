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
"""奇想盒任务目录读取入口。"""

import uuid
from pathlib import Path

from app.core import Config
from app.models.config import WhimboxConfig as RuntimeWhimboxConfig
from app.task.Whimbox.contracts import WhimboxCatalog
from app.task.Whimbox.tools.upstream import WheelAssetsConfigSurface


class WhimboxInstallError(ValueError):
    """安装不完整，向编辑页透传安装检查提示。"""


def _whimbox_script_config(script_id: str) -> RuntimeWhimboxConfig:
    """Resolve a Whimbox script and reject cross-type IDs before domain access."""

    script_config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(script_config, RuntimeWhimboxConfig):
        raise TypeError("脚本配置类型错误, 不是奇想盒类型")
    return script_config


def read_task_catalog(script_id: str) -> WhimboxCatalog:
    script_config = _whimbox_script_config(script_id)
    surface = WheelAssetsConfigSurface(Path(str(script_config.Info.RootPath or "")))
    install_error = surface.check_install()
    if install_error:
        raise WhimboxInstallError(install_error)
    return surface.read_catalog()
