#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.
#
#   Contact: DLmaster_361@163.com


"""MAS 各更新模块共享的状态记账原语：状态文件读写与时间字段判断。

只做无业务语义的原语，不持有任何更新状态：状态文件损坏一律按无状态处理
（调用方靠重查重下自愈），时间字段统一 isoformat + UTC。记账字段名由调用
方拼装（如 ``last_download_attempt_at/{key}`` 或固定键），本模块不关心键
的格式与作用域。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.utils import get_logger
from app.utils.io import read_dict_file

logger = get_logger("MAA 更新状态")


def load_state(path: Path) -> dict[str, object]:
    """读更新模块的状态文件；缺失或损坏按无状态处理（自愈语义）。"""
    try:
        return read_dict_file(path)
    except Exception:
        logger.warning(f"MAA 更新状态: 状态文件损坏，按无状态处理: {path}")
        return {}


def parse_iso(value: object) -> datetime | None:
    """解析状态文件里的 isoformat 时间值，统一补齐 UTC 时区。"""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def backoff_active(state: dict[str, object], field: str, now: datetime) -> bool:
    """field 字段记录的退避截止时间是否仍在生效。"""
    until = parse_iso(state.get(field))
    return until is not None and now < until


def attempted_today(state: dict[str, object], field: str, now: datetime) -> bool:
    """field 字段记录的最近记账时间是否落在本地日期的今天。"""
    last_attempt = parse_iso(state.get(field))
    return (
        last_attempt is not None
        and last_attempt.astimezone().date() >= now.astimezone().date()
    )
