#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.
#
#   Contact: DLmaster_361@163.com

"""MAA 本体与资源更新共用的接管凭据，避免两个更新器的启用条件分歧。"""

from app.core import Config
from app.models.config import MaaConfig


def resolve_takeover_credentials(config: MaaConfig) -> tuple[bool, str | None]:
    """脚本开启接管且有生效 CDK 才启用；脚本 CDK 留空时回退全局配置。"""
    if not config.get("Update", "TakeoverEnabled"):
        return False, None
    cdk = str(config.get("Update", "MirrorChyanCDK") or "").strip()
    if not cdk:
        cdk = str(Config.get("Update", "MirrorChyanCDK") or "").strip()
    return bool(cdk), cdk or None
