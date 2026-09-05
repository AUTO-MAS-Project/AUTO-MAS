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


"""历史游戏签到凭据解析兼容入口。"""

from .community_credentials import (
    CommunityCredentialInfo,
    GameSignCredentialInfo,
    is_community_credential_configured,
    is_game_sign_credential_configured,
    parse_community_credential,
    parse_game_sign_credential,
    validate_community_credential,
    validate_game_sign_credential,
)

__all__ = [
    "CommunityCredentialInfo",
    "GameSignCredentialInfo",
    "is_community_credential_configured",
    "is_game_sign_credential_configured",
    "parse_community_credential",
    "parse_game_sign_credential",
    "validate_community_credential",
    "validate_game_sign_credential",
]
