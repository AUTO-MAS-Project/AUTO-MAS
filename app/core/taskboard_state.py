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

from app.core.config import Config
from app.models.taskboard import (
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
_LOCK = asyncio.Lock()


def _timestamp(value: str) -> float:
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


def weekly_key(now: datetime | None = None) -> str:
    """返回当前周键；北京时间周一 04:00 换周，键为换周后周一的日期。"""

    current = now or datetime.now(tz=UTC8)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC8)
    else:
        current = current.astimezone(UTC8)
    shifted = current - timedelta(hours=WEEKLY_RESET_HOUR)
    monday = shifted.date() - timedelta(days=shifted.weekday())
    return monday.isoformat()


def _now_text() -> str:
    """完成时间统一按界面展示格式写入。"""

    return datetime.now(tz=UTC8).strftime("%Y-%m-%d %H:%M")


def _prune(state: TaskboardState) -> TaskboardState:
    """按活动结束时间清理归档、旧周任务和超出保留数量的版本记录。"""

    now = datetime.now(tz=UTC8).timestamp()
    cutoff = (datetime.now(tz=UTC8) - timedelta(days=TASKBOARD_KEEP_DAYS)).timestamp()
    state.archived = [
        item
        for item in state.archived
        if not item.end_time
        or _timestamp(item.end_time) == 0
        or _timestamp(item.end_time) >= cutoff
    ]
    state.done_at = {
        key: record
        for key, record in state.done_at.items()
        if not record.end
        or _timestamp(record.end) == 0
        or _timestamp(record.end) >= cutoff
    }

    week = weekly_key()
    state.weekly = {
        key: record for key, record in state.weekly.items() if record.week == week
    }

    grouped: dict[str, list[tuple[str, TaskboardVersionStoryRecord]]] = {}
    for key, record in state.version_story.items():
        grouped.setdefault(record.game, []).append((key, record))
    keep_keys: set[str] = set()
    for records in grouped.values():
        records.sort(key=lambda item: _timestamp(item[1].start), reverse=True)
        keep_keys.update(key for key, _ in records[:VERSION_STORY_KEEP_PER_GAME])
        # 当前版本即使起始时间较早也不能被数量上限裁掉。
        keep_keys.update(key for key, record in records if _timestamp(record.end) > now)
    state.version_story = {
        key: record for key, record in state.version_story.items() if key in keep_keys
    }
    state.version_story_done = {
        key: record
        for key, record in state.version_story_done.items()
        if key in keep_keys
    }
    return state


def state_path() -> Path:
    """任务台状态文件固定在配置目录。"""

    return Config.config_path / TASKBOARD_STATE_FILENAME


def _read() -> TaskboardState:
    """读取任务台状态；文件缺失或损坏时按空状态处理。"""

    path = state_path()
    if not path.exists():
        return TaskboardState()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return _prune(TaskboardState.model_validate(payload))
    except (OSError, ValueError, TypeError):
        logger.warning("任务台状态文件损坏，按空状态处理")
        return TaskboardState()


def _write(state: TaskboardState) -> None:
    """裁剪后原子写回任务台状态文件。"""

    _utils_io.write_file(state_path(), _prune(state).model_dump())


async def load_state() -> TaskboardState:
    """读取任务台状态；写入期间不并发读取。"""

    async with _LOCK:
        return _read()


async def save_selection(games: list[str]) -> None:
    """保存勾选的游戏。"""

    async with _LOCK:
        state = _read()
        state.selected_games = list(games)
        _write(state)


async def save_weekly_selection(games: list[str]) -> None:
    """保存每周任务单独勾选的游戏。空列表表示一个都不选；None 表示跟随任务台的勾选。"""

    async with _LOCK:
        state = _read()
        state.weekly_games = list(games)
        _write(state)


async def save_archive(archived) -> None:
    """保存归档缓存。"""

    async with _LOCK:
        state = _read()
        state.archived = list(archived)
        _write(state)


async def set_done_at(key: str, record: TaskboardDoneRecord | None) -> None:
    """记录或删除一条完成日期。"""

    async with _LOCK:
        state = _read()
        if record is None:
            state.done_at.pop(key, None)
        else:
            state.done_at[key] = record
        _write(state)


async def set_weekly_done(key: str, done: bool) -> str:
    """记录或删除本周任务完成状态，返回当前周键。"""

    async with _LOCK:
        state = _read()
        week = weekly_key()
        if done:
            state.weekly[key] = TaskboardWeeklyRecord(week=week, done_at=_now_text())
        else:
            state.weekly.pop(key, None)
        _write(state)
        return week


async def merge_version_story(records: list[TaskboardVersionStoryUpdate]) -> None:
    """把前端本次取到的版本记录合并进本地目录。"""

    if not records:
        return

    async with _LOCK:
        state = _read()
        now_text = _now_text()
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
                )
                continue
            existing.version_name = item.version_name or existing.version_name
            existing.start = item.start or existing.start
            existing.end = item.end or existing.end
            existing.cover_url = item.cover_url or existing.cover_url
            existing.last_seen = now_text
        _write(state)


async def set_version_story_done(key: str, record: TaskboardDoneRecord | None) -> None:
    """记录或删除一条版本主线完成记录。"""

    async with _LOCK:
        state = _read()
        if record is None:
            state.version_story_done.pop(key, None)
        else:
            state.version_story_done[key] = record
        _write(state)
