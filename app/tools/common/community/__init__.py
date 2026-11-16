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


"""社区工具：协议、凭据、签到结果和活动采集。"""

from app.tools.common.community.activity.parser import parse_activity_snapshot
from app.tools.common.community.activity.provider import (
    CommunityActivityProvider,
    build_community_activity_requester,
)
from app.tools.common.community.activity.transport import (
    CommunityActivityRequest,
    CommunityActivityTarget,
    CommunityActivityTransportError,
    build_community_activity_requests,
    collect_community_activity,
)
from app.tools.common.community.contracts import CommunitySignInProgressError
from app.tools.common.community.plugins import (
    COMMUNITY_PLUGIN_REFERENCES,
    CommunityCapability,
    CommunityPluginReference,
    get_community_plugin_references,
    get_confirmed_community_capabilities,
    supports_community_capability,
)
from app.tools.common.community.sign import (
    format_community_sign_results,
    has_community_credentials,
)

__all__ = [
    "parse_activity_snapshot",
    "COMMUNITY_PLUGIN_REFERENCES",
    "CommunityCapability",
    "CommunityPluginReference",
    "CommunitySignInProgressError",
    "CommunityActivityRequest",
    "CommunityActivityTarget",
    "CommunityActivityTransportError",
    "CommunityActivityProvider",
    "build_community_activity_requester",
    "build_community_activity_requests",
    "collect_community_activity",
    "format_community_sign_results",
    "get_community_plugin_references",
    "get_confirmed_community_capabilities",
    "has_community_credentials",
    "supports_community_capability",
]
