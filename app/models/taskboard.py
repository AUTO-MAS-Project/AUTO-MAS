#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published
#   by the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import ipaddress
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator

## 与落盘裁剪共用同一组上限，避免模型校验和 _prune 各写一份数字。
TASKBOARD_GAMES_MAX_ENTRIES = 100
TASKBOARD_ARCHIVED_MAX_ENTRIES = 2000
TASKBOARD_WEEKLY_MAX_ENTRIES = 100
TASKBOARD_VERSION_STORY_MAX_ENTRIES = 500

_LOCAL_HOST_SUFFIXES = (".localhost", ".local", ".internal", ".home.arpa", ".lan")
_NON_PUBLIC_IPV6_PREFIXES = (
    "::",
    "64:ff9b:",
    "2001:db8:",
    "2002:",
    "2001:0:",
    "fec0:",
)


def _is_numeric_label(label: str) -> bool:
    """判断主机名片段是否是十进制/十六进制数字，拦截 2130706433 这类简写地址。"""

    if label.isdigit():
        return True
    lowered = label.lower()
    return lowered.startswith("0x") and all(
        char in "0123456789abcdef" for char in lowered[2:]
    )


def _safe_cover_url(value: str) -> str:
    """只保留公网 https 版本封面；非法地址置空，避免渲染进程替外部地址发请求。

    不做 DNS 解析：解析到私网的公网域名不在本校验范围内，渲染层会再用同一规则拦一次。
    """

    text = value.strip()
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
        raw_host = parsed.hostname
    except ValueError:
        return ""
    if parsed.scheme != "https" or not raw_host:
        return ""
    if parsed.username or parsed.password:
        return ""
    if any(char in raw_host for char in ("%", "\\", " ", "\t", "\r", "\n")):
        return ""
    if ":" in raw_host:
        host = raw_host.lower()
    else:
        try:
            host = raw_host.encode("idna").decode("ascii").lower().rstrip(".")
        except UnicodeError:
            return ""
    if not host:
        return ""
    if ":" in host:
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return ""
        if not address.is_global or str(address).startswith(_NON_PUBLIC_IPV6_PREFIXES):
            return ""
        return text
    if host == "localhost" or any(
        host.endswith(suffix) for suffix in _LOCAL_HOST_SUFFIXES
    ):
        return ""
    if "." not in host:
        return ""
    if all(_is_numeric_label(part) for part in host.split(".")):
        return ""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return text
    return text if address.is_global else ""


class TaskboardArchivedActivity(BaseModel):
    id: str = Field(..., min_length=1, max_length=300, description="任务台活动 id")
    game_key: str = Field(..., min_length=1, max_length=100, description="游戏标识")
    title: str = Field(..., min_length=1, max_length=500, description="活动名称")
    start_time: str = Field(default="", max_length=40, description="活动开始时间")
    end_time: str = Field(default="", max_length=40, description="活动结束时间")
    description: str = Field(default="", max_length=2000, description="活动说明")
    image_url: str = Field(default="", max_length=2000, description="封面地址")


class TaskboardDoneRecord(BaseModel):
    at: str = Field(..., min_length=1, max_length=40, description="完成时间")
    end: str = Field(default="", max_length=40, description="活动结束时间，用于裁剪")


class TaskboardWeeklyRecord(BaseModel):
    week: str = Field(
        ..., min_length=1, max_length=20, description="本周周键，北京时间周一日期"
    )
    done_at: str = Field(..., min_length=1, max_length=40, description="完成时间")


class TaskboardVersionStoryUpdate(BaseModel):
    game: str = Field(..., min_length=1, max_length=100, description="游戏标识")
    version: str = Field(..., min_length=1, max_length=100, description="版本号")
    version_name: str = Field(default="", max_length=200, description="版本名称")
    start: str = Field(default="", max_length=40, description="版本开始时间")
    end: str = Field(default="", max_length=40, description="版本结束时间")
    cover_url: str = Field(
        default="",
        max_length=2000,
        description="版本封面地址；仅接受公网 https，非法值置空",
    )

    @field_validator("cover_url")
    @classmethod
    def _validate_cover_url(cls, value: str) -> str:
        return _safe_cover_url(value)


class TaskboardVersionStoryRecord(TaskboardVersionStoryUpdate):
    first_seen: str = Field(default="", max_length=40, description="首次记录时间")
    last_seen: str = Field(default="", max_length=40, description="最近一次记录时间")
    observed_at: int = Field(
        default=0, ge=0, description="最近一次字段更新的观察时间，Unix 毫秒"
    )


class TaskboardState(BaseModel):
    selected_games: list[str] | None = Field(
        default=None,
        max_length=TASKBOARD_GAMES_MAX_ENTRIES,
        description="任务台勾选的游戏；为空表示尚未保存",
    )
    weekly_games: list[str] | None = Field(
        default=None,
        max_length=TASKBOARD_GAMES_MAX_ENTRIES,
        description="每周任务单独勾选的游戏；为空表示跟随任务台游戏选择",
    )
    archived: list[TaskboardArchivedActivity] = Field(
        default_factory=list,
        max_length=TASKBOARD_ARCHIVED_MAX_ENTRIES,
        description="已归档活动的展示缓存",
    )
    done_at: dict[str, TaskboardDoneRecord] = Field(
        default_factory=dict, description="活动完成日期，key 为游戏与活动的组合键"
    )
    weekly: dict[str, TaskboardWeeklyRecord] = Field(
        default_factory=dict,
        max_length=TASKBOARD_WEEKLY_MAX_ENTRIES,
        description="每周任务完成状态，key 为任务台游戏标识",
    )
    version_story: dict[str, TaskboardVersionStoryRecord] = Field(
        default_factory=dict,
        max_length=TASKBOARD_VERSION_STORY_MAX_ENTRIES,
        description="本地积累的版本主线目录，key 为游戏与版本的组合键",
    )
    version_story_done: dict[str, TaskboardDoneRecord] = Field(
        default_factory=dict,
        max_length=TASKBOARD_VERSION_STORY_MAX_ENTRIES,
        description="版本主线完成记录，key 与 version_story 一致",
    )
