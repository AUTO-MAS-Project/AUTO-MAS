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
from app.models.taskboard import TaskboardDoneRecord, TaskboardState
from app.utils import UTC8, get_logger
from app.utils import io as _utils_io

logger = get_logger("任务台状态")

TASKBOARD_STATE_FILENAME = "TaskboardData.json"
TASKBOARD_KEEP_DAYS = 45
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


def _prune(state: TaskboardState) -> TaskboardState:
    """按活动结束时间清理归档与完成日期，保留 45 天。"""

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
