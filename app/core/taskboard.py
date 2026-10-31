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


"""任务台状态的落盘：已选游戏、归档缓存、完成日期统一存配置目录。"""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

from pydantic import ConfigDict, Field

from app.core import Config
from app.models.taskboard import (
    TASKBOARD_ARCHIVED_MAX_ENTRIES,
    TASKBOARD_GAMES_MAX_ENTRIES,
    TASKBOARD_VERSION_STORY_MAX_ENTRIES,
    TASKBOARD_WEEKLY_MAX_ENTRIES,
    TaskboardArchivedActivity,
    TaskboardDoneRecord,
    TaskboardState,
    TaskboardVersionStoryRecord,
    TaskboardVersionStoryUpdate,
    TaskboardWeeklyRecord,
)
from app.utils import UTC8, get_logger
from app.utils import io as _utils_io

logger = get_logger("任务台状态")

TASKBOARD_STATE_FILENAME = "TaskboardData.json"
TASKBOARD_KEEP_DAYS = 45
VERSION_STORY_KEEP_PER_GAME = 24
WEEKLY_RESET_HOUR = 4


class _StoredArchivedActivity(TaskboardArchivedActivity):
    model_config = ConfigDict(extra="allow")


class _StoredDoneRecord(TaskboardDoneRecord):
    model_config = ConfigDict(extra="allow")


class _StoredWeeklyRecord(TaskboardWeeklyRecord):
    model_config = ConfigDict(extra="allow")


class _StoredVersionStoryRecord(TaskboardVersionStoryRecord):
    model_config = ConfigDict(extra="allow")


class _StoredTaskboardState(TaskboardState):
    """落盘专用模型：放宽集合上限，读写时保留未来版本写入的未知字段。"""

    model_config = ConfigDict(extra="allow")

    selected_games: list[str] | None = Field(default=None)
    weekly_games: list[str] | None = Field(default=None)
    archived: list[_StoredArchivedActivity] = Field(default_factory=list)
    done_at: dict[str, _StoredDoneRecord] = Field(default_factory=dict)
    weekly: dict[str, _StoredWeeklyRecord] = Field(default_factory=dict)
    version_story: dict[str, _StoredVersionStoryRecord] = Field(default_factory=dict)
    version_story_done: dict[str, _StoredDoneRecord] = Field(default_factory=dict)


class TaskboardManager:
    def __init__(self) -> None:
        self._LOCK = asyncio.Lock()

    def _timestamp(self, value: str) -> float:
        """解析活动时间字符串，兼容带时区与北京时间裸时间；无法解析返回 0。"""

        text = (value or "").strip()
        if not text:
            return 0.0
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC8)
        return parsed.timestamp()

    def weekly_key(self, now: datetime | None = None) -> str:
        """返回当前周键；北京时间周一 04:00 换周，键为换周后周一的日期。"""

        current = now or datetime.now(tz=UTC8)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC8)
        else:
            current = current.astimezone(UTC8)
        shifted = current - timedelta(hours=WEEKLY_RESET_HOUR)
        monday = shifted.date() - timedelta(days=shifted.weekday())
        return monday.isoformat()

    def _now_text(self) -> str:
        """完成时间统一按界面展示格式写入。"""

        return datetime.now(tz=UTC8).strftime("%Y-%m-%d %H:%M")

    def _prune(self, state: TaskboardState, week: str | None = None) -> TaskboardState:
        """按活动结束时间清理归档、旧周任务和超出保留数量的版本记录。"""

        if state.selected_games is not None:
            state.selected_games = state.selected_games[:TASKBOARD_GAMES_MAX_ENTRIES]
        if state.weekly_games is not None:
            state.weekly_games = state.weekly_games[:TASKBOARD_GAMES_MAX_ENTRIES]

        now = datetime.now(tz=UTC8).timestamp()
        cutoff = (
            datetime.now(tz=UTC8) - timedelta(days=TASKBOARD_KEEP_DAYS)
        ).timestamp()
        state.archived = [
            item
            for item in state.archived
            if not item.end_time
            or self._timestamp(item.end_time) == 0
            or self._timestamp(item.end_time) >= cutoff
        ]
        if len(state.archived) > TASKBOARD_ARCHIVED_MAX_ENTRIES:
            # 没有结束时间或无法解析的记录优先保留，其余按结束时间保留最近的。
            state.archived.sort(
                key=lambda item: self._timestamp(item.end_time) or float("inf"),
                reverse=True,
            )
            state.archived = state.archived[:TASKBOARD_ARCHIVED_MAX_ENTRIES]
        state.done_at = {
            key: record
            for key, record in state.done_at.items()
            if not record.end
            or self._timestamp(record.end) == 0
            or self._timestamp(record.end) >= cutoff
        }

        current_week = week or self.weekly_key()
        weekly_items = [
            (key, record)
            for key, record in state.weekly.items()
            if record.week == current_week
        ]
        weekly_items.sort(key=lambda item: item[1].done_at, reverse=True)
        state.weekly = dict(weekly_items[:TASKBOARD_WEEKLY_MAX_ENTRIES])

        grouped: dict[str, list[tuple[str, TaskboardVersionStoryRecord]]] = {}
        for key, record in state.version_story.items():
            grouped.setdefault(record.game, []).append((key, record))
        keep_keys: set[str] = set()
        for records in grouped.values():
            records.sort(key=lambda item: self._timestamp(item[1].start), reverse=True)
            keep_keys.update(key for key, _ in records[:VERSION_STORY_KEEP_PER_GAME])
            # 当前版本即使起始时间较早也不能被数量上限裁掉。
            keep_keys.update(
                key for key, record in records if self._timestamp(record.end) > now
            )

        # 每个游戏的上限之和仍可能超过总上限，先保当前版本，再按开始时间补足。
        active_keys = {
            key
            for key in keep_keys
            if self._timestamp(state.version_story[key].end) > now
        }
        ordered = sorted(
            keep_keys,
            key=lambda key: self._timestamp(state.version_story[key].start),
            reverse=True,
        )
        keep_keys = set(
            [key for key in ordered if key in active_keys][
                :TASKBOARD_VERSION_STORY_MAX_ENTRIES
            ]
        )
        remaining = TASKBOARD_VERSION_STORY_MAX_ENTRIES - len(keep_keys)
        if remaining > 0:
            keep_keys.update(
                [key for key in ordered if key not in active_keys][:remaining]
            )
        state.version_story = {
            key: record
            for key, record in state.version_story.items()
            if key in keep_keys
        }
        state.version_story_done = {
            key: record
            for key, record in state.version_story_done.items()
            if key in keep_keys
        }
        return state

    def state_path(self) -> Path:
        """任务台状态文件固定在配置目录。"""

        return Config.config_path / TASKBOARD_STATE_FILENAME

    def _read(self) -> TaskboardState:
        """读取任务台状态；文件缺失或损坏时按空状态处理。"""

        path = self.state_path()
        if not path.exists():
            return _StoredTaskboardState()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return self._prune(_StoredTaskboardState.model_validate(payload))
        except (OSError, ValueError, TypeError):
            logger.warning("任务台状态文件损坏，按空状态处理")
            return _StoredTaskboardState()

    def _write(self, state: TaskboardState, week: str | None = None) -> None:
        """裁剪并校验后原子写回任务台状态文件。"""

        pruned = self._prune(state, week)
        try:
            # 严格模型只用于确认裁剪后的数量仍在上限内；写盘保留 _Stored 模型的未知字段。
            TaskboardState.model_validate(pruned.model_dump())
        except ValueError:
            logger.error("任务台状态超出模型限制，本次写入已拒绝")
            raise
        _utils_io.write_file(self.state_path(), pruned.model_dump())

    async def load_state(self) -> TaskboardState:
        """读取任务台状态；写入期间不并发读取。"""

        async with self._LOCK:
            return self._read()

    async def save_selection(self, games: list[str]) -> None:
        """保存勾选的游戏。"""

        async with self._LOCK:
            state = self._read()
            state.selected_games = list(games)
            self._write(state)

    async def save_weekly_selection(self, games: list[str]) -> None:
        """保存每周任务单独勾选的游戏。空列表表示一个都不选；状态为 None 时表示跟随任务台勾选。"""

        async with self._LOCK:
            state = self._read()
            state.weekly_games = list(games)
            self._write(state)

    async def save_archive(self, archived) -> None:
        """保存归档缓存。"""

        async with self._LOCK:
            state = self._read()
            state.archived = list(archived)
            self._write(state)

    async def set_done_at(self, key: str, record: TaskboardDoneRecord | None) -> None:
        """记录或删除一条完成日期。"""

        async with self._LOCK:
            state = self._read()
            if record is None:
                state.done_at.pop(key, None)
            else:
                state.done_at[key] = record
            self._write(state)

    async def set_weekly_done(
        self, key: str, done: bool, expected_week: str = ""
    ) -> tuple[str, bool]:
        """记录或删除本周任务完成状态；客户端周键过期时不落盘。"""

        async with self._LOCK:
            state = self._read()
            week = self.weekly_key()
            if expected_week and expected_week != week:
                return week, False
            if done:
                state.weekly[key] = TaskboardWeeklyRecord(
                    week=week, done_at=self._now_text()
                )
            else:
                state.weekly.pop(key, None)
            self._write(state, week)
            return week, True

    async def merge_version_story(
        self, records: list[TaskboardVersionStoryUpdate], observed_at: int = 0
    ) -> None:
        """把前端本次取到的版本记录合并进本地目录，旧批次不覆盖新字段。"""

        if not records:
            return

        async with self._LOCK:
            state = self._read()
            now_text = self._now_text()
            for item in records:
                if not item.game or not item.version or not item.start or not item.end:
                    continue
                key = f"{item.game}|{item.version}"
                existing = state.version_story.get(key)
                if existing is None:
                    state.version_story[key] = TaskboardVersionStoryRecord(
                        **item.model_dump(),
                        first_seen=now_text,
                        last_seen=now_text,
                        observed_at=observed_at,
                    )
                    continue
                if existing.observed_at and (
                    not observed_at or observed_at < existing.observed_at
                ):
                    continue
                existing.version_name = item.version_name or existing.version_name
                existing.start = item.start or existing.start
                existing.end = item.end or existing.end
                existing.cover_url = item.cover_url or existing.cover_url
                existing.last_seen = now_text
                if observed_at > existing.observed_at:
                    existing.observed_at = observed_at
            self._write(state)

    async def set_version_story_done(
        self, key: str, record: TaskboardDoneRecord | None
    ) -> None:
        """记录或删除一条版本主线完成记录。"""

        async with self._LOCK:
            state = self._read()
            if record is None:
                state.version_story_done.pop(key, None)
            else:
                state.version_story_done[key] = record
            self._write(state)


Taskboard = TaskboardManager()

__all__ = ["Taskboard"]
