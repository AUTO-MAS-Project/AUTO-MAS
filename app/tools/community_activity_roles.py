#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file incorporates request knowledge from the following acknowledged
#   community projects:
#
#       nonebot-plugin-mystool Copyright © 2023-2025 Ljzd-PRO
#       https://github.com/Ljzd-PRO/nonebot-plugin-mystool
#
#       gxy12345/arknights-plugin
#       https://github.com/gxy12345/arknights-plugin

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


"""社区角色发现结果和绑定响应归一化，不负责网络请求或配置保存。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from .community_activity_transport import CommunityActivityTarget

__all__ = [
    "ACTIVITY_COMMUNITY_DEFINITIONS",
    "CommunityActivityProviderDefinition",
    "CommunityActivityRole",
    "CommunityActivityRoleDiscovery",
    "normalize_miyoushe_roles",
    "normalize_skland_roles",
]


ActivityCommunity = Literal["森空岛", "米游社"]


@dataclass(frozen=True)
class CommunityActivityProviderDefinition:
    """活动查询 provider 的目标游戏登记。"""

    platform: ActivityCommunity
    games: tuple[str, ...]


ACTIVITY_COMMUNITY_DEFINITIONS = (
    CommunityActivityProviderDefinition(
        platform="森空岛",
        games=("明日方舟", "终末地"),
    ),
    CommunityActivityProviderDefinition(
        platform="米游社",
        games=("原神", "星穹铁道", "绝区零"),
    ),
)


@dataclass(frozen=True)
class CommunityActivityRole:
    """不含凭据和设备值的单个游戏角色。"""

    platform: ActivityCommunity
    game: str
    role_uid: str
    server: str = ""
    role_name: str = ""
    user_id: str = ""

    def to_target(
        self,
        *,
        account_uid: str,
        account_name: str,
        device_id: str = "",
        device_fp: str = "",
    ) -> CommunityActivityTarget:
        """转换为活动 transport 使用的脱敏目标。"""

        return CommunityActivityTarget(
            account_uid=account_uid,
            account_name=account_name,
            platform=self.platform,
            game=self.game,
            role_uid=self.role_uid,
            server=self.server,
            role_name=self.role_name,
            user_id=self.user_id,
            device_id=device_id,
            device_fp=device_fp,
        )


@dataclass(frozen=True)
class CommunityActivityRoleDiscovery:
    """一次账号组角色发现的脱敏结果。"""

    platform: ActivityCommunity
    roles: tuple[CommunityActivityRole, ...] = ()

    def roles_for_game(self, game: str) -> tuple[CommunityActivityRole, ...]:
        """按游戏筛选角色并保持上游顺序。"""

        return tuple(role for role in self.roles if role.game == game)


def _text(item: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = item.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _binding_entries(
    payload: Mapping[str, Any], *, app_code: str
) -> tuple[Mapping[str, Any], ...]:
    data = payload.get("data")
    if isinstance(data, list):
        groups: object = data
    elif isinstance(data, Mapping):
        groups = data.get("list")
        if groups is None and data.get("appCode"):
            groups = [data]
        elif groups is None and (
            isinstance(data.get("bindingList"), list)
            or isinstance(data.get("binding_list"), list)
        ):
            # 本次请求没有按 appCode 过滤，不能把无标签的同一列表同时
            # 解释为明日方舟和终末地，避免把角色映射到错误游戏。
            raise ValueError("森空岛角色列表缺少 appCode，无法安全识别游戏")
    else:
        groups = None

    if not isinstance(groups, list):
        raise ValueError("森空岛角色列表响应缺少绑定列表")

    entries: list[Mapping[str, Any]] = []
    for group in groups:
        if not isinstance(group, Mapping):
            continue
        group_app_code = _text(group, "appCode", "app_code")
        if group_app_code != app_code:
            continue
        binding_list = group.get("bindingList")
        if binding_list is None:
            binding_list = group.get("binding_list")
        if binding_list is None:
            continue
        if not isinstance(binding_list, list):
            raise ValueError("森空岛角色绑定列表响应格式无效")
        entries.extend(
            entry for entry in binding_list if isinstance(entry, Mapping)
        )
    return tuple(entries)


def _deduplicate_roles(
    roles: list[CommunityActivityRole],
) -> tuple[CommunityActivityRole, ...]:
    seen: set[tuple[str, str, str]] = set()
    result: list[CommunityActivityRole] = []
    for role in roles:
        key = (role.game, role.role_uid, role.server)
        if key in seen:
            continue
        seen.add(key)
        result.append(role)
    return tuple(result)


def normalize_skland_roles(
    payload: Mapping[str, Any],
) -> CommunityActivityRoleDiscovery:
    """归一化森空岛明日方舟和终末地绑定响应。"""

    roles: list[CommunityActivityRole] = []
    for entry in _binding_entries(payload, app_code="arknights"):
        role_uid = _text(entry, "uid")
        if role_uid:
            roles.append(
                CommunityActivityRole(
                    platform="森空岛",
                    game="明日方舟",
                    role_uid=role_uid,
                    server=_text(entry, "channelName", "channel_name"),
                    role_name=_text(entry, "nickName", "nickname", "name"),
                )
            )

    for entry in _binding_entries(payload, app_code="endfield"):
        nested_roles = entry.get("roles")
        if not isinstance(nested_roles, list):
            nested_roles = [entry] if _text(entry, "roleId", "role_id") else []
        entry_user_id = _text(entry, "userId", "user_id")
        entry_server = _text(entry, "serverId", "server_id")
        for role in nested_roles:
            if not isinstance(role, Mapping):
                continue
            role_uid = _text(role, "roleId", "role_id")
            if not role_uid:
                continue
            roles.append(
                CommunityActivityRole(
                    platform="森空岛",
                    game="终末地",
                    role_uid=role_uid,
                    server=_text(role, "serverId", "server_id") or entry_server,
                    role_name=_text(role, "nickname", "nickName", "name"),
                    user_id=_text(role, "userId", "user_id") or entry_user_id,
                )
            )

    return CommunityActivityRoleDiscovery("森空岛", _deduplicate_roles(roles))


_MIYOUSHE_GAME_NAMES = {
    "hk4e_cn": "原神",
    "hkrpg_cn": "星穹铁道",
    "nap_cn": "绝区零",
}


def normalize_miyoushe_roles(
    payload: Mapping[str, Any],
) -> CommunityActivityRoleDiscovery:
    """归一化米游社角色接口的扁平和按游戏嵌套响应。"""

    data = payload.get("data")
    data_list = data.get("list") if isinstance(data, Mapping) else None
    if not isinstance(data_list, list):
        return CommunityActivityRoleDiscovery("米游社")

    role_entries: list[Mapping[str, Any]] = []
    for item in data_list:
        if not isinstance(item, Mapping):
            continue
        nested = item.get("list")
        if isinstance(nested, list):
            role_entries.extend(
                role for role in nested if isinstance(role, Mapping)
            )
        else:
            role_entries.append(item)

    roles: list[CommunityActivityRole] = []
    for role in role_entries:
        game = _MIYOUSHE_GAME_NAMES.get(_text(role, "game_biz"))
        role_uid = _text(role, "game_uid", "gameUid")
        if not game or not role_uid:
            continue
        roles.append(
            CommunityActivityRole(
                platform="米游社",
                game=game,
                role_uid=role_uid,
                server=_text(role, "region", "server"),
                role_name=_text(role, "nickname", "nickName", "name"),
            )
        )

    return CommunityActivityRoleDiscovery("米游社", _deduplicate_roles(roles))
