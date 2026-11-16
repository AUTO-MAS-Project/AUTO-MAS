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


"""云崽社区插件能力目录，不负责网络请求、凭据保存或任务执行。"""

from dataclasses import dataclass
from typing import Literal

__all__ = [
    "COMMUNITY_PLUGIN_REFERENCES",
    "CommunityCapability",
    "CommunityPluginReference",
    "get_community_plugin_references",
    "get_confirmed_community_capabilities",
    "supports_community_capability",
]


CommunityCapability = Literal[
    "credential",
    "sign",
    "community_task",
    "daily_activity",
    "role_profile",
    "announcement",
    "activity_calendar",
    "gacha_record",
    "game_data",
    "notification",
]


@dataclass(frozen=True)
class CommunityPluginReference:
    """记录外部社区插件已展示的能力，不能直接视为 AUTO-MAS 已接入。"""

    name: str
    provider: str
    games: tuple[str, ...]
    capabilities: frozenset[CommunityCapability]
    evidence: tuple[str, ...]
    interface_confirmed: bool = True


# 只记录参考项目中已看到的能力；接口接入仍需单独完成协议和凭据审查。
COMMUNITY_PLUGIN_REFERENCES = (
    CommunityPluginReference(
        name="Yunzai-Kuro-Plugin",
        provider="库街区",
        games=("战双帕弥什", "鸣潮"),
        capabilities=frozenset(
            {
                "credential",
                "sign",
                "community_task",
                "daily_activity",
                "role_profile",
                "gacha_record",
                "notification",
            }
        ),
        evidence=(
            "apps/gameEnergy.js",
            "apps/bbsActivityTask.js",
            "model/gameCard.js",
        ),
    ),
    CommunityPluginReference(
        name="ZZZ-Plugin",
        provider="米游社",
        games=("绝区零",),
        capabilities=frozenset(
            {
                "credential",
                "daily_activity",
                "role_profile",
                "gacha_record",
                "game_data",
            }
        ),
        evidence=("dist/apps/note.js", "dist/lib/mysapi/api.js"),
    ),
    CommunityPluginReference(
        name="zmd-plugin",
        provider="森空岛",
        games=("明日方舟", "终末地"),
        capabilities=frozenset(
            {
                "credential",
                "sign",
                "daily_activity",
                "role_profile",
                "announcement",
                "activity_calendar",
                "gacha_record",
            }
        ),
        evidence=(
            "model/skland/api.js",
            "apps/status.js",
            "resources/enduid/daily.html",
        ),
    ),
    CommunityPluginReference(
        name="bh3-plugin",
        provider="米游社",
        games=("崩坏3",),
        capabilities=frozenset(
            {"credential", "daily_activity", "role_profile", "game_data"}
        ),
        evidence=("lib/api.js", "apps/main.js"),
    ),
    CommunityPluginReference(
        name="1999-plugin",
        provider="未确认",
        games=("重返未来：1999",),
        capabilities=frozenset(),
        evidence=("README.md",),
        interface_confirmed=False,
    ),
    CommunityPluginReference(
        name="skland-plugin",
        provider="森空岛",
        games=("明日方舟",),
        capabilities=frozenset(
            {
                "credential",
                "sign",
                "daily_activity",
                "role_profile",
                "gacha_record",
                "notification",
            }
        ),
        evidence=("components/Code.js", "apps/Sanity.js", "apps/SignIn.js"),
    ),
)


def get_community_plugin_references(
    *,
    provider: str | None = None,
    game: str | None = None,
    confirmed_only: bool = False,
) -> tuple[CommunityPluginReference, ...]:
    """按社区或游戏筛选参考插件能力。"""

    provider_value = provider.strip() if provider else None
    game_value = game.strip() if game else None
    return tuple(
        item
        for item in COMMUNITY_PLUGIN_REFERENCES
        if (not confirmed_only or item.interface_confirmed)
        and (provider_value is None or item.provider == provider_value)
        and (game_value is None or game_value in item.games)
    )


def get_confirmed_community_capabilities(
    provider: str, game: str
) -> frozenset[CommunityCapability]:
    """合并已确认参考插件对指定社区/游戏展示的能力。"""

    capabilities: set[CommunityCapability] = set()
    for item in get_community_plugin_references(
        provider=provider,
        game=game,
        confirmed_only=True,
    ):
        capabilities.update(item.capabilities)
    return frozenset(capabilities)


def supports_community_capability(
    provider: str,
    game: str,
    capability: CommunityCapability,
) -> bool:
    """判断参考项目是否展示过指定社区能力。"""

    return capability in get_confirmed_community_capabilities(provider, game)
