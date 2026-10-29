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


from pydantic import BaseModel, Field


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
    cover_url: str = Field(default="", max_length=2000, description="版本封面地址")


class TaskboardVersionStoryRecord(TaskboardVersionStoryUpdate):
    first_seen: str = Field(default="", max_length=40, description="首次记录时间")
    last_seen: str = Field(default="", max_length=40, description="最近一次记录时间")


class TaskboardState(BaseModel):
    selected_games: list[str] | None = Field(
        default=None, max_length=100, description="任务台勾选的游戏；为空表示尚未保存"
    )
    weekly_games: list[str] | None = Field(
        default=None,
        max_length=100,
        description="每周任务单独勾选的游戏；为空表示跟随任务台游戏选择",
    )
    archived: list[TaskboardArchivedActivity] = Field(
        default_factory=list, max_length=2000, description="已归档活动的展示缓存"
    )
    done_at: dict[str, TaskboardDoneRecord] = Field(
        default_factory=dict, description="活动完成日期，key 为游戏与活动的组合键"
    )
    weekly: dict[str, TaskboardWeeklyRecord] = Field(
        default_factory=dict,
        max_length=100,
        description="每周任务完成状态，key 为任务台游戏标识",
    )
    version_story: dict[str, TaskboardVersionStoryRecord] = Field(
        default_factory=dict,
        max_length=500,
        description="本地积累的版本主线目录，key 为游戏与版本的组合键",
    )
    version_story_done: dict[str, TaskboardDoneRecord] = Field(
        default_factory=dict,
        max_length=500,
        description="版本主线完成记录，key 与 version_story 一致",
    )
