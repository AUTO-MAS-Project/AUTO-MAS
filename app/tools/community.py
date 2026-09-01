#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


"""游戏社区工具统一入口，旧签到标识仅在兼容层保留。"""

from contextlib import asynccontextmanager

from .community_plugins import (
    COMMUNITY_PLUGIN_REFERENCES,
    CommunityCapability,
    CommunityPluginReference,
    get_community_plugin_references,
    get_confirmed_community_capabilities,
    supports_community_capability,
)
from .community_sign_provider import (
    format_community_sign_results,
    has_community_credentials,
)
from .community_contract import CommunitySignInProgressError
from .community_activity_parser import parse_activity_snapshot
from .community_activity_provider import (
    CommunityActivityProvider,
    build_community_activity_requester,
)
from .community_activity_transport import (
    CommunityActivityRequest,
    CommunityActivityTarget,
    CommunityActivityTransportError,
    build_community_activity_requests,
    collect_community_activity,
)

__all__ = [
    "COMMUNITY_PLUGIN_REFERENCES",
    "CommunityCapability",
    "CommunityPluginReference",
    "CommunitySignInProgressError",
    "CommunityToolInProgressError",
    "CommunityActivityRequest",
    "CommunityActivityTarget",
    "CommunityActivityTransportError",
    "CommunityActivityProvider",
    "GameSignInProgressError",
    "build_community_activity_requester",
    "build_community_activity_requests",
    "collect_community_activity",
    "community_sign_flow",
    "format_community_sign_results",
    "get_community_plugin_references",
    "get_confirmed_community_capabilities",
    "has_community_credentials",
    "parse_community_activity_snapshot",
    "run_community_sign_in",
    "supports_community_capability",
]


# 旧异常名称仅供历史调用方识别同一个并发冲突类型。
CommunityToolInProgressError = CommunitySignInProgressError
GameSignInProgressError = CommunitySignInProgressError
parse_community_activity_snapshot = parse_activity_snapshot


@asynccontextmanager
async def community_sign_flow():
    """延迟进入核心社区签到流程，避免工具包初始化形成循环导入。"""

    from app.core.community_sign import community_sign_flow as core_flow

    async with core_flow():
        yield


async def run_community_sign_in(force: bool = False) -> list[dict]:
    """延迟调用核心社区签到编排。"""

    from app.core.community_sign import run_community_sign_in as core_run

    return await core_run(force=force)
