# SPDX-License-Identifier: AGPL-3.0-or-later
"""卡池关注区服与已明确绑定的托管账号。"""

from app.core import Config
from app.models.config import CLASS_BOOK
from app.models.script_access import script_users

from .state import GAME_SERVERS, SERVER_NAMES

_MANAGED_REGIONS = {
    CLASS_BOOK["MaaEnd"]: ("endfield", "Resource", {"官服": "cn", "国际服": "global"}),
    CLASS_BOOK["Okww"]: (
        "wutheringwaves",
        "Resource",
        {"官服": "cn", "国际服": "global"},
    ),
    CLASS_BOOK["BAAH"]: (
        "bluearchive",
        "ActivityLineType",
        {"CN": "cn", "JP": "jp", "Globle": "global"},
    ),
}

_ARKNIGHTS_REGION = (
    "arknights",
    "Server",
    {"Official": "cn", "Bilibili": "cn", "YoStarJP": "jp", "YoStarEN": "global"},
)
if maa_config := CLASS_BOOK.get("MAA"):
    _MANAGED_REGIONS[maa_config] = _ARKNIGHTS_REGION


def _region_configuration(script):
    entry = _MANAGED_REGIONS.get(type(script))
    if entry is not None or "MAA" in CLASS_BOOK:
        return entry
    from app.core.plugin import Plugin

    declaration = Plugin.script_decl(script)
    if declaration is not None and declaration.activity_game == "arknights":
        return _ARKNIGHTS_REGION
    return None


def managed_regions() -> set[tuple[str, str]]:
    """区服必须来自专项的明确配置，通用脚本的名称不能确认区服。"""
    regions: set[tuple[str, str]] = set()
    for script in Config.ScriptConfig.values():
        entry = _region_configuration(script)
        if entry is None:
            continue
        game, field, mapping = entry
        for user in script_users(script).values():
            if not user.Info.Status:
                continue
            region = mapping.get(getattr(user.Info, field, None))
            if region:
                regions.add((game, region))
    return regions


def game_catalog(coverage: set[tuple[str, str]]) -> list[dict]:
    managed = managed_regions()
    return [
        {
            "id": game,
            "name": label,
            "servers": [
                {
                    "id": server,
                    "name": SERVER_NAMES[server],
                    "covered": (game, server) in coverage,
                    "managed": (game, server) in managed,
                }
                for server in regions
            ],
        }
        for game, (label, regions) in GAME_SERVERS.items()
    ]
