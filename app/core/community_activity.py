#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
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


"""游戏社区账号组到活动快照的核心消费层。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from app.utils.constants import UTC8
from app.utils.logger import get_logger

from app.tools.community_activity_provider import CommunityActivityProvider
from app.tools.community_activity_roles import (
    ACTIVITY_COMMUNITY_DEFINITIONS,
    CommunityActivityProviderDefinition,
    CommunityActivityRole,
)
from app.tools.community_activity_transport import (
    CommunityActivityTarget,
    CommunityActivityTransportError,
    collect_community_activity,
)
from app.tools.community_contract import ActivityState, CommunityActivitySnapshot

__all__ = [
    "build_configured_community_activity_failures",
    "collect_configured_community_activity",
]


logger = get_logger("游戏社区活动")


def _account_value(account: object, name: str, default: Any = "") -> Any:
    try:
        return account.get("GameSignAccount", name)  # type: ignore[attr-defined]
    except (AttributeError, KeyError):
        return default


def _failure_state(error: Exception) -> tuple[ActivityState, str]:
    if isinstance(error, CommunityActivityTransportError):
        return error.status, error.reason
    if isinstance(error, ValueError):
        text = str(error)
        if any(marker in text for marker in ("风控", "限制", "非 JSON")):
            return "limited", "社区角色列表受到上游限制"
        return "unavailable", "社区角色列表响应无法识别"
    return "failed", "社区角色列表请求失败"


def _empty_game_snapshot(
    *,
    account_uid: str,
    account_name: str,
    definition: CommunityActivityProviderDefinition,
    game: str,
    status: ActivityState = "empty",
    reason: str = "未发现已绑定角色",
) -> CommunityActivitySnapshot:
    return CommunityActivitySnapshot(
        account=account_name,
        account_uid=account_uid,
        game=game,
        platform=definition.platform,
        status=status,
        reason=reason,
        updated_at=datetime.now(tz=UTC8).isoformat(),
    )


def _targets_for_roles(
    *,
    roles: Sequence[CommunityActivityRole],
    account_uid: str,
    account_name: str,
) -> tuple[CommunityActivityTarget, ...]:
    return tuple(
        role.to_target(account_uid=account_uid, account_name=account_name)
        for role in roles
    )


def _selected_accounts(
    account_ids: Sequence[str] | None,
) -> tuple[tuple[str, object], ...]:
    from app.core import Config

    requested_ids = {
        str(account_id).strip()
        for account_id in (account_ids or ())
        if account_id
    }
    selected: list[tuple[str, object]] = []
    matched_ids: set[str] = set()
    for raw_uid, account in Config.ToolsConfig.GameSign_Accounts.items():
        account_uid = str(raw_uid)
        if requested_ids and account_uid not in requested_ids:
            continue
        selected.append((account_uid, account))
        matched_ids.add(account_uid)
    if requested_ids and matched_ids != requested_ids:
        raise ValueError("未找到指定的游戏社区账号组")
    return tuple(selected)


def build_configured_community_activity_failures(
    account_ids: Sequence[str] | None = None,
    *,
    reason: str = "游戏社区日常查询失败",
) -> tuple[CommunityActivitySnapshot, ...]:
    """为已配置社区构造分游戏失败结果，不执行任何上游请求。"""

    from app.tools.game_sign import (
        get_community_token_field,
        read_community_token,
    )

    snapshots: list[CommunityActivitySnapshot] = []
    for account_uid, account in _selected_accounts(account_ids):
        if not _account_value(account, "Enabled", False):
            continue
        account_name = str(_account_value(account, "Name", "用户") or "用户")
        for definition in ACTIVITY_COMMUNITY_DEFINITIONS:
            token_field = get_community_token_field(definition.platform)
            try:
                configured = bool(read_community_token(account, token_field))
            except Exception:
                configured = True
            if not configured:
                continue
            snapshots.extend(
                _empty_game_snapshot(
                    account_uid=account_uid,
                    account_name=account_name,
                    definition=definition,
                    game=game,
                    status="failed",
                    reason=reason,
                )
                for game in definition.games
            )
    return tuple(snapshots)


async def collect_configured_community_activity(
    account_ids: Sequence[str] | None = None,
    *,
    proxy: str | None = None,
    max_concurrency: int = 4,
) -> tuple[CommunityActivitySnapshot, ...]:
    """读取已配置账号组并查询已登记社区的日常活动。"""

    from app.core import Config
    from app.tools.game_sign import (
        get_community_token_field,
        read_community_token,
    )

    resolved_proxy = proxy if proxy is not None else Config.proxy
    snapshots: list[CommunityActivitySnapshot] = []

    for account_uid, account in _selected_accounts(account_ids):
        account_name = str(_account_value(account, "Name", "用户") or "用户")
        if not _account_value(account, "Enabled", False):
            continue

        for definition in ACTIVITY_COMMUNITY_DEFINITIONS:
            token_field = get_community_token_field(definition.platform)
            try:
                token = read_community_token(account, token_field)
            except Exception:
                snapshots.extend(
                    _empty_game_snapshot(
                        account_uid=account_uid,
                        account_name=account_name,
                        definition=definition,
                        game=game,
                        status="failed",
                        reason="社区凭据无法读取",
                    )
                    for game in definition.games
                )
                continue
            if not token:
                continue

            provider = CommunityActivityProvider(
                platform=definition.platform,
                raw_credential=token,
                proxy=resolved_proxy,
            )
            try:
                discovered = await provider.discover_roles(
                    account_uid=account_uid,
                    account_name=account_name,
                )
            except Exception as error:
                status, reason = _failure_state(error)
                logger.warning(f"{account_name} {definition.platform}角色发现失败: {reason}")
                snapshots.extend(
                    _empty_game_snapshot(
                        account_uid=account_uid,
                        account_name=account_name,
                        definition=definition,
                        game=game,
                        status=status,
                        reason=reason,
                    )
                    for game in definition.games
                )
                continue

            targets = _targets_for_roles(
                roles=discovered.roles,
                account_uid=account_uid,
                account_name=account_name,
            )
            queried: tuple[CommunityActivitySnapshot, ...] = ()
            if targets:
                queried = await collect_community_activity(
                    targets,
                    provider.request,
                    max_concurrency=max_concurrency,
                )

            for game in definition.games:
                game_snapshots = tuple(
                    snapshot for snapshot in queried if snapshot.game == game
                )
                if game_snapshots:
                    snapshots.extend(game_snapshots)
                else:
                    snapshots.append(
                        _empty_game_snapshot(
                            account_uid=account_uid,
                            account_name=account_name,
                            definition=definition,
                            game=game,
                        )
                    )

    return tuple(snapshots)
