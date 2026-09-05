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


"""旧游戏签到调度模块兼容入口，实际策略由社区调度模块承载。"""

from .community_scheduler import (
    AccountCredentialChecker,
    CommunityTriggerSource,
    TASK_COMMUNITY_SOURCES,
    all_community_accounts_signed,
    has_pending_community_account,
    should_run_community_for_source,
)


# Keep historical imports working while new callers use community semantics.
GameSignSource = CommunityTriggerSource
TASK_GAME_SIGN_SOURCES = TASK_COMMUNITY_SOURCES
has_pending_game_sign_account = has_pending_community_account
all_game_sign_accounts_signed = all_community_accounts_signed
should_run_game_sign_for_source = should_run_community_for_source

__all__ = [
    "AccountCredentialChecker",
    "GameSignSource",
    "TASK_GAME_SIGN_SOURCES",
    "all_game_sign_accounts_signed",
    "has_pending_game_sign_account",
    "should_run_game_sign_for_source",
]
