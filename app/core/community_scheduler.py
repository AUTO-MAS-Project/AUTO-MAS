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


"""社区工具调度策略，明确隔离签到和日常查询的执行边界。"""

import asyncio
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from typing import Literal


CommunityTriggerSource = Literal[
    "scheduled",
    "startup",
    "task_scheduled",
    "task_manual",
    "task_startup",
]
TASK_COMMUNITY_SOURCES = frozenset(
    {"task_scheduled", "task_manual", "task_startup"}
)
AccountCredentialChecker = Callable[[object], bool]


def _default_credential_checker(account: object) -> bool:
    from app.tools.community import has_community_credentials

    return has_community_credentials(account)


def has_pending_community_account(
    account: object,
    today: str,
    *,
    has_credentials: AccountCredentialChecker | None = None,
) -> bool:
    """判断账号是否启用、配置凭据且尚未完成今日社区签到。"""

    if not account.get("GameSignAccount", "Enabled"):  # type: ignore[attr-defined]
        return False
    checker = has_credentials or _default_credential_checker
    if not checker(account):
        return False
    return account.get("GameSignAccount", "LastSignDate") != today  # type: ignore[attr-defined]


def all_community_accounts_signed(
    accounts: Mapping[object, object],
    today: str,
    *,
    has_credentials: AccountCredentialChecker | None = None,
) -> bool:
    """判断所有具备凭据的启用账号是否已完成今日社区签到。"""

    return not any(
        has_pending_community_account(
            account,
            today,
            has_credentials=has_credentials,
        )
        for _, account in accounts.items()
    )


def should_run_community_for_source(
    *,
    enabled: bool,
    run_on_startup: bool,
    source: CommunityTriggerSource,
) -> bool:
    """判断当前配置是否允许指定触发来源执行社区签到。"""

    if not enabled:
        return False
    if source == "startup":
        return bool(run_on_startup)
    return source in TASK_COMMUNITY_SOURCES

__all__ = [
    "TASK_COMMUNITY_SOURCES",
    "CommunityActivityInProgressError",
    "CommunityTriggerSource",
    "all_community_accounts_signed",
    "community_activity_flow",
    "has_pending_community_account",
    "should_run_community_for_source",
]


class CommunityActivityInProgressError(RuntimeError):
    """社区日常查询已在执行。"""


_community_activity_lock = asyncio.Lock()


@asynccontextmanager
async def community_activity_flow():
    """保护社区日常查询自身，不占用签到流程锁。"""

    if _community_activity_lock.locked():
        raise CommunityActivityInProgressError("社区日常查询正在执行，请稍后重试")

    await _community_activity_lock.acquire()
    try:
        yield
    finally:
        _community_activity_lock.release()
