"""宿主装配保持原有游戏来源和所有生产入口共用一个日历实例。"""

import pytest

from app.api import info
from app.api.scripts import management
from app.core import game_calendar_host as host
from app.core import timer


def test_http_timer_and_script_metadata_share_host_composition():
    assert info.GameCalendar is timer.GameCalendar is host.GameCalendar
    assert management.SCRIPT_CALENDAR_GAMES is host.SCRIPT_CALENDAR_GAMES


@pytest.mark.parametrize(
    "game,server,source",
    [
        ("bluearchive", "cn", "ba-cn"),
        ("bluearchive", "jp", "ba-jp"),
        ("bluearchive", "global", "ba-global"),
        ("reverse1999", "cn", "reverse1999"),
        ("arknights", "global", "ak"),
        ("endfield", "jp", "end"),
    ],
)
def test_completion_source_keeps_server_scope_and_legacy_identity(game, server, source):
    assert host.activity_source(game, server) == source
