#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 ClozyA
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

"""MAA 配置共用的关卡字段、开放日与游戏日规则。"""

from datetime import datetime, timedelta, timezone

from app.utils.common.constants import UTC4

MAA_STAGE_KEY = [
    "MedicineNumb",
    "SeriesNumb",
    "Stage",
    "Stage_1",
    "Stage_2",
    "Stage_3",
]
"""MAA关卡键表"""

ARKNIGHTS_GAME_DAY_TZ = {
    "Official": UTC4,
    "Bilibili": UTC4,
    "txwy": UTC4,
    "YoStarEN": timezone(timedelta(hours=-11)),
    "YoStarJP": timezone(timedelta(hours=5)),
    "YoStarKR": timezone(timedelta(hours=5)),
}
"""明日方舟各区服的游戏日时区：服务器当地 04:00 换日，即服务器时区减 4 小时

来源 MAA `src/MaaWpfGui/Extensions/DateTimeExtension.cs`：`_clientTypeTimezone`
中 Official / Bilibili / txwy 为 UTC+8，YoStarEN 为 UTC-7（固定偏移，不随夏令时），
YoStarJP / YoStarKR 为 UTC+9；`YjDayStartHour = 4`。
前端 `frontend/src/views/MAAUserEdit/periodMarkers.ts` 的 ARKNIGHTS_GAME_DAY_OFFSET
是同一张表，改动时两边同步。
"""


def get_game_day_tz(server: str | None) -> timezone:
    """按明日方舟区服取游戏日时区，未知或空区服回落到东4区。"""

    return ARKNIGHTS_GAME_DAY_TZ.get(server or "", UTC4)


def game_now(server: str | None) -> datetime:
    """按明日方舟区服的游戏日时区取当前时间，其日期即当前游戏日。"""

    return datetime.now(tz=get_game_day_tz(server))


RESOURCE_STAGE_INFO = [
    {"value": "-", "text": "禁用", "days": [1, 2, 3, 4, 5, 6, 7]},
    {"value": "*", "text": "当前/上次", "days": [1, 2, 3, 4, 5, 6, 7]},
    {"value": "1-7", "text": "1-7", "days": [1, 2, 3, 4, 5, 6, 7]},
    {"value": "R8-11", "text": "R8-11", "days": [1, 2, 3, 4, 5, 6, 7]},
    {"value": "12-17-HARD", "text": "12-17-HARD", "days": [1, 2, 3, 4, 5, 6, 7]},
    {"value": "LS-6", "text": "经验-6/5", "days": [1, 2, 3, 4, 5, 6, 7]},
    {"value": "CE-6", "text": "龙门币-6/5", "days": [2, 4, 6, 7]},
    {"value": "AP-5", "text": "红票-5", "days": [1, 4, 6, 7]},
    {"value": "CA-5", "text": "技能-5", "days": [2, 3, 5, 7]},
    {"value": "SK-5", "text": "碳-5", "days": [1, 3, 5, 6]},
    {"value": "PR-A-1", "text": "奶/盾芯片", "days": [1, 4, 5, 7]},
    {"value": "PR-A-2", "text": "奶/盾芯片组", "days": [1, 4, 5, 7]},
    {"value": "PR-B-1", "text": "术/狙芯片", "days": [1, 2, 5, 6]},
    {"value": "PR-B-2", "text": "术/狙芯片组", "days": [1, 2, 5, 6]},
    {"value": "PR-C-1", "text": "先/辅芯片", "days": [3, 4, 6, 7]},
    {"value": "PR-C-2", "text": "先/辅芯片组", "days": [3, 4, 6, 7]},
    {"value": "PR-D-1", "text": "近/特芯片", "days": [2, 3, 6, 7]},
    {"value": "PR-D-2", "text": "近/特芯片组", "days": [2, 3, 6, 7]},
]
"""常规资源关信息"""
