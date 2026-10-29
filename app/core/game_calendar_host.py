#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""装配游戏日历的账号解释、活动来源和持久化位置。"""

from collections.abc import Iterable

from app.core.config import Config
from app.core.game_calendar import CalendarTarget, GameCalendarService
from app.models.config import CLASS_BOOK
from app.task.BAAH.calendar_service import calendar_target as baah_calendar_target
from app.tools.bluearchive_activity_source import BLUEARCHIVE_SERVERS
from app.tools.game_calendar import CALENDAR_GAMES, fetch_calendar_activities

SCRIPT_CALENDAR_GAMES = {
    CLASS_BOOK[script]: game
    for script, game in {
        "MAA": "arknights",
        "MaaEnd": "endfield",
        "SRC": "starrail",
        "HSR": "starrail",
        "BetterGI": "genshin",
        "ZzzOd": "zenless",
        "Okww": "wutheringwaves",
        "OkNte": "nte",
        "M9A": "reverse1999",
        "BAAH": "bluearchive",
        "MSS": "stellasora",
        "Whimbox": "infinitynikki",
    }.items()
}


def notification_targets() -> Iterable[CalendarTarget]:
    """读取当前启用的托管账号，专项配置由对应领域解释。"""
    for script in Config.ScriptConfig.values():
        game = SCRIPT_CALENDAR_GAMES.get(type(script))
        if game is None:
            continue
        for user in script.UserData.values():
            if not user.Info.Status:
                continue
            source, label = CALENDAR_GAMES[game]
            if game == "bluearchive":
                source, label = baah_calendar_target(user)
            yield CalendarTarget(game=game, source=source, label=label)


def activity_source(game: str, server: str) -> str:
    """将公开完成状态请求中的游戏与区服解释为原有来源标识。"""
    if game == "bluearchive":
        return BLUEARCHIVE_SERVERS[server][0]
    return CALENDAR_GAMES[game][0] or game


GameCalendar = GameCalendarService(
    read_targets=notification_targets,
    fetch_activities=fetch_calendar_activities,
    resolve_source=activity_source,
    schedule_path=lambda: Config.config_path / "GameCalendarSchedule.json",
)
