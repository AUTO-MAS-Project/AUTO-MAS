#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""将 BAAH 账号的活动排期设置解释为公共日历目标。"""

from app.models.config import BAAHUserConfig
from app.tools.bluearchive_activity_source import BLUEARCHIVE_SERVERS

BAAH_CALENDAR_SERVERS = {"CN": "cn", "JP": "jp", "Globle": "global"}


def calendar_target(user: BAAHUserConfig) -> tuple[str, str]:
    """返回账号对应的活动来源与带区服的显示名称。"""
    server = BAAH_CALENDAR_SERVERS[user.Info.ActivityLineType]
    source, server_label = BLUEARCHIVE_SERVERS[server]
    return source, f"碧蓝档案（{server_label}）"
