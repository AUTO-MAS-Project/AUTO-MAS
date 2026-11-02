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

import traceback
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from typing import TYPE_CHECKING

import httpx

from app.tools.common.community import contracts as _tool_community_contract
from app.tools.common.community.activity import (
    provider as _tool_community_activity_provider,
)
from app.tools.common.community.activity import roles as _tool_community_activity_roles
from app.tools.common.community.activity import (
    transport as _tool_community_activity_transport,
)
from app.utils import UTC8, format_exception_reason, get_logger

if TYPE_CHECKING:
    from app.models.config import GlobalConfig, ToolsConfig


logger = get_logger("游戏社区活动")

_ACTIVITY_CACHE_SECONDS = 300.0
_ACTIVITY_RETRY_SECONDS = 30.0
type _ActivityCacheKey = tuple[int, str]


@dataclass(frozen=True)
class _ActivityCacheEntry:
    snapshots: tuple[_tool_community_contract.CommunityActivitySnapshot, ...]
    expires_at: float


class CommunityActivityOperations:
    def __init__(self) -> None:
        self._activity_cache: dict[_ActivityCacheKey, _ActivityCacheEntry] = {}
        self._activity_cache_revision = 0

        def invalidate_activity_cache(sender: object, event: object) -> None:
            """配置变动后清除快照，并作废尚未完成的旧查询。"""

            self._activity_cache_revision += 1
            self._activity_cache.clear()

        # 信号机制在接收函数上记录订阅元数据；保留稳定函数，避免绑定方法不能写属性。
        self._invalidate_activity_cache = invalidate_activity_cache

    def connect_community_activity_cache(
        self, tools_config: ToolsConfig, *, setting: GlobalConfig
    ) -> None:
        """订阅账号、便笺开关和代理设置，覆盖编辑与后台凭据更新。"""

        from app.models.config import GameSignAccountGroup

        # 初始化重试时复用同一接收者，避免重复订阅使启动失败。
        GameSignAccountGroup.disconnect(
            self._invalidate_activity_cache, phase="runtime", group="GameSignAccount"
        )
        GameSignAccountGroup.connect(
            self._invalidate_activity_cache, phase="runtime", group="GameSignAccount"
        )
        tools_config.GameSign_Accounts.disconnect(
            self._invalidate_activity_cache, phase="runtime"
        )
        tools_config.GameSign_Accounts.connect(
            self._invalidate_activity_cache, phase="runtime"
        )
        tools_config.disconnect(
            self._invalidate_activity_cache,
            phase="runtime",
            group="GameSign",
            field="ActivityEnabled",
        )
        tools_config.connect(
            self._invalidate_activity_cache,
            phase="runtime",
            group="GameSign",
            field="ActivityEnabled",
        )
        setting.disconnect(
            self._invalidate_activity_cache,
            phase="runtime",
            group="Update",
            field="ProxyAddress",
        )
        setting.connect(
            self._invalidate_activity_cache,
            phase="runtime",
            group="Update",
            field="ProxyAddress",
        )
        self._invalidate_activity_cache(tools_config, None)

    async def query_configured_community_activity(
        self,
        account_ids: Sequence[str] | None = None,
        *,
        proxy: str | httpx.Proxy | None = None,
    ) -> tuple[_tool_community_contract.CommunityActivitySnapshot, ...]:
        """按账号缓存便笺；并发查询等待后仅补查尚未缓存的账号。"""

        from app.core import Config

        async with self.community_activity_flow():
            while True:
                if Config.ToolsConfig.GameSign.ActivityEnabled is False:
                    return ()
                config_id = id(Config.ToolsConfig)
                selected_ids = tuple(
                    uid for uid, _ in self._selected_accounts(account_ids)
                )
                results: dict[
                    str, tuple[_tool_community_contract.CommunityActivitySnapshot, ...]
                ] = {}
                missing_ids: list[str] = []
                now = monotonic()
                for uid in selected_ids:
                    entry = self._activity_cache.get((config_id, uid))
                    if entry is not None and now < entry.expires_at:
                        results[uid] = entry.snapshots
                    else:
                        missing_ids.append(uid)
                if not missing_ids:
                    return tuple(item for uid in selected_ids for item in results[uid])

                revision = self._activity_cache_revision
                resolved_proxy = proxy if proxy is not None else Config.proxy
                try:
                    snapshots = await self.collect_configured_community_activity(
                        missing_ids, proxy=resolved_proxy
                    )
                except ValueError:
                    raise
                except Exception as error:
                    if revision != self._activity_cache_revision:
                        continue
                    logger.warning(
                        format_exception_reason(
                            error, stage="游戏社区日常查询失败", include_message=False
                        )
                    )
                    if error.__traceback__ is not None:
                        # 仅保留定位信息，避免异常原文、源码或局部变量泄露凭据。
                        frames = traceback.extract_tb(error.__traceback__)
                        logger.warning(
                            "社区调用位置: "
                            + " -> ".join(
                                f"{frame.filename}:{frame.lineno} in {frame.name}"
                                for frame in frames
                            )
                        )
                    snapshots = self.build_configured_community_activity_failures(
                        missing_ids
                    )
                    if not snapshots:
                        raise

                # 等待上游期间账号可能被删除、修改；旧响应不能进入新配置的缓存。
                if revision != self._activity_cache_revision:
                    continue
                by_account: dict[
                    str, list[_tool_community_contract.CommunityActivitySnapshot]
                ] = {uid: [] for uid in missing_ids}
                for item in snapshots:
                    by_account[item.account_uid].append(item)
                completed_at = monotonic()
                for uid, items in by_account.items():
                    ttl = (
                        _ACTIVITY_RETRY_SECONDS
                        if any(
                            item.status not in ("success", "empty") for item in items
                        )
                        else _ACTIVITY_CACHE_SECONDS
                    )
                    results[uid] = tuple(items)
                    self._activity_cache[(config_id, uid)] = _ActivityCacheEntry(
                        snapshots=results[uid], expires_at=completed_at + ttl
                    )
                return tuple(item for uid in selected_ids for item in results[uid])

    def _account_value(
        self, account: object, name: str, default: object = ""
    ) -> object:
        try:
            return getattr(account.GameSignAccount, name)  # type: ignore[attr-defined]
        except (AttributeError, KeyError):
            return default

    def _failure_state(
        self,
        error: Exception,
    ) -> tuple[_tool_community_contract.ActivityState, str]:
        if isinstance(
            error, _tool_community_activity_transport.CommunityActivityTransportError
        ):
            return error.status, error.reason
        if isinstance(error, ValueError):
            text = str(error)
            if any(marker in text for marker in ("风控", "限制", "非 JSON")):
                return "limited", "社区角色列表受到上游限制"
            return "unavailable", "社区角色列表响应无法识别"
        return "failed", "社区角色列表请求失败"

    def _empty_game_snapshot(
        self,
        *,
        account_uid: str,
        account_name: str,
        definition: _tool_community_activity_roles.CommunityActivityProviderDefinition,
        game: str,
        status: _tool_community_contract.ActivityState = "empty",
        reason: str = "未发现已绑定角色",
        role: _tool_community_activity_roles.CommunityActivityRole | None = None,
    ) -> _tool_community_contract.CommunityActivitySnapshot:
        return _tool_community_contract.CommunityActivitySnapshot(
            account=account_name,
            account_uid=account_uid,
            game=game,
            platform=definition.platform,
            status=status,
            reason=reason,
            updated_at=datetime.now(tz=UTC8).isoformat(),
            role_name=role.role_name if role is not None else "",
            role_uid=role.role_uid if role is not None else "",
            server=role.server if role is not None else "",
        )

    def _targets_for_roles(
        self,
        *,
        roles: Sequence[_tool_community_activity_roles.CommunityActivityRole],
        account_uid: str,
        account_name: str,
        miyoushe_device_id: str = "",
        miyoushe_device_fp: str = "",
    ) -> tuple[_tool_community_activity_transport.CommunityActivityTarget, ...]:
        return tuple(
            role.to_target(
                account_uid=account_uid,
                account_name=account_name,
                device_id=(
                    miyoushe_device_id
                    if role.platform == "米游社" and role.game == "绝区零"
                    else ""
                ),
                device_fp=(
                    miyoushe_device_fp
                    if role.platform == "米游社" and role.game == "绝区零"
                    else ""
                ),
            )
            for role in roles
        )

    def _selected_accounts(
        self,
        account_ids: Sequence[str] | None,
    ) -> tuple[tuple[str, object], ...]:
        from app.core import Config

        requested_ids = {
            str(account_id).strip() for account_id in (account_ids or ()) if account_id
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
        self,
        account_ids: Sequence[str] | None = None,
        *,
        reason: str = "游戏社区日常查询失败",
    ) -> tuple[_tool_community_contract.CommunityActivitySnapshot, ...]:
        """为已配置社区构造分游戏失败结果，不执行任何上游请求。"""

        from app.tools.common.community import sign as _tool_community_sign_provider

        snapshots: list[_tool_community_contract.CommunityActivitySnapshot] = []
        for account_uid, account in self._selected_accounts(account_ids):
            if not self._account_value(account, "Enabled", False):
                continue
            account_name = str(self._account_value(account, "Name", "用户") or "用户")
            for (
                definition
            ) in _tool_community_activity_roles.ACTIVITY_COMMUNITY_DEFINITIONS:
                token_field = _tool_community_sign_provider.get_community_token_field(
                    definition.platform
                )
                try:
                    configured = bool(
                        _tool_community_sign_provider.read_community_token(
                            account, token_field
                        )
                    )
                except Exception:
                    configured = True
                if not configured:
                    continue
                snapshots.extend(
                    self._empty_game_snapshot(
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
        self,
        account_ids: Sequence[str] | None = None,
        *,
        proxy: str | httpx.Proxy | None = None,
        max_concurrency: int = 4,
    ) -> tuple[_tool_community_contract.CommunityActivitySnapshot, ...]:
        """读取已配置账号组并查询已登记社区的日常活动。"""

        from app.core import Config
        from app.tools.common.community import sign as _tool_community_sign_provider

        resolved_proxy = proxy if proxy is not None else Config.proxy
        snapshots: list[_tool_community_contract.CommunityActivitySnapshot] = []

        for account_uid, account in self._selected_accounts(account_ids):
            account_name = str(self._account_value(account, "Name", "用户") or "用户")
            if not self._account_value(account, "Enabled", False):
                continue
            try:
                miyoushe_device_id = str(
                    self._account_value(account, "MiyousheDeviceId", "") or ""
                ).strip()
                miyoushe_device_fp = str(
                    self._account_value(account, "MiyousheDeviceFp", "") or ""
                ).strip()
            except Exception:
                # 设备字段读取失败只限制绝区零便笺，不影响同账号的其他游戏。
                miyoushe_device_id = ""
                miyoushe_device_fp = ""

            for (
                definition
            ) in _tool_community_activity_roles.ACTIVITY_COMMUNITY_DEFINITIONS:
                token_field = _tool_community_sign_provider.get_community_token_field(
                    definition.platform
                )
                try:
                    token = _tool_community_sign_provider.read_community_token(
                        account, token_field
                    )
                except Exception:
                    snapshots.extend(
                        self._empty_game_snapshot(
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

                provider = _tool_community_activity_provider.CommunityActivityProvider(
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
                    status, reason = self._failure_state(error)
                    logger.warning(
                        f"{account_name} {definition.platform}角色发现失败: {reason}"
                    )
                    snapshots.extend(
                        self._empty_game_snapshot(
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

                capability = discovered.activity_capability
                if capability.status == "limited":
                    for game in definition.games:
                        game_roles = discovered.roles_for_game(game)
                        if game_roles:
                            snapshots.extend(
                                self._empty_game_snapshot(
                                    account_uid=account_uid,
                                    account_name=account_name,
                                    definition=definition,
                                    game=game,
                                    status="limited",
                                    reason=capability.reason,
                                    role=role,
                                )
                                for role in game_roles
                            )
                        else:
                            snapshots.append(
                                self._empty_game_snapshot(
                                    account_uid=account_uid,
                                    account_name=account_name,
                                    definition=definition,
                                    game=game,
                                )
                            )
                    continue

                targets = self._targets_for_roles(
                    roles=discovered.roles,
                    account_uid=account_uid,
                    account_name=account_name,
                    miyoushe_device_id=miyoushe_device_id,
                    miyoushe_device_fp=miyoushe_device_fp,
                )
                queried: tuple[
                    _tool_community_contract.CommunityActivitySnapshot, ...
                ] = ()
                if targets:
                    queried = await _tool_community_activity_transport.collect_community_activity(
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
                            self._empty_game_snapshot(
                                account_uid=account_uid,
                                account_name=account_name,
                                definition=definition,
                                game=game,
                            )
                        )

        return tuple(snapshots)
