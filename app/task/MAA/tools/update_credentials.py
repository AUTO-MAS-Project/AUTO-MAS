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
from app.services.update_transport import MirrorCdkStatus, query_mirror_cdk_status


def resolve_takeover_cdk(cdk: str) -> str:
    """专用 CDK 留空时使用全局 CDK，不写回脚本配置。"""
    return cdk.strip() or str(Config.setting.Update.MirrorChyanCDK or "").strip()


def resolve_takeover_credentials(config: MaaConfig) -> tuple[bool, str | None]:
    """脚本开启接管且有生效 CDK 才启用；脚本 CDK 留空时回退全局配置。"""
    if not config.Update.TakeoverEnabled:
        return False, None
    cdk = resolve_takeover_cdk(str(config.Update.MirrorChyanCDK or ""))
    return bool(cdk), cdk or None


async def query_takeover_cdk(cdk: str) -> MirrorCdkStatus:
    """仅校验 MAA 的有效凭据，不依赖安装目录或读取 MAA 加密配置。"""
    # CDK 的有效期不随安装版本变化；使用稳定版元数据完成无下载查询。
    return await query_mirror_cdk_status(
        "MAA", cdk=resolve_takeover_cdk(cdk), channel="stable", proxy=Config.proxy
    )
