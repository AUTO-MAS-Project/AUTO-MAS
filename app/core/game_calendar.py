#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""按首页显示设置推送游戏活动开始与结束提醒。"""

import asyncio
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from app.core.config import Config
from app.core.notify import dispatch, global_target
from app.models.notification import NotifyPayload
from app.tools.game_calendar import (
    BLUEARCHIVE_SERVERS,
    CALENDAR_GAMES,
    fetch_calendar_activities,
)
from app.utils import get_logger
from app.utils.constants import UTC8
from app.utils.io import write_file

logger = get_logger("游戏日历")
CALENDAR_CHECK_INTERVAL_SECONDS = 10 * 60


@dataclass(frozen=True)
class CalendarReminder:
    key: str
    payload: NotifyPayload


def visible_calendar_games(config: Mapping[str, object]) -> dict[str, tuple[str, str]]:
    """与首页一致：轮播总开关和游戏开关同时生效，缺省显示全部游戏。"""

    layout = config.get("homeLayout")
    hidden = layout.get("hiddenModules", []) if isinstance(layout, dict) else []
    if not isinstance(hidden, list):
        hidden = []
    hidden = [key for key in hidden if isinstance(key, str)]
    # 兼容轮播上线前「所有游戏都隐藏」的旧布局迁移。
    order = layout.get("moduleOrder", []) if isinstance(layout, dict) else []
    old_games = set(CALENDAR_GAMES) - {"stellasora"}
    if "activities" in hidden or (
        isinstance(order, list)
        and "activities" not in order
        and old_games.issubset(hidden)
    ):
        return {}
    games = {key: value for key, value in CALENDAR_GAMES.items() if key not in hidden}
    if "bluearchive" in games:
        server = config.get("homeBlueArchiveServer", "cn")
        source, label = BLUEARCHIVE_SERVERS.get(str(server), BLUEARCHIVE_SERVERS["cn"])
        games["bluearchive"] = (source, f"碧蓝档案（{label}）")
    return games


def _activity_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    # 公开源的裸时间按北京时间解释，不依赖设备的本地时区。
    return (
        parsed.replace(tzinfo=UTC8)
        if parsed.tzinfo is None
        else parsed.astimezone(UTC8)
    )


def calendar_reminders(
    activities: Sequence[Mapping[str, object]],
    *,
    game: str,
    label: str,
    now: datetime,
) -> list[CalendarReminder]:
    """只生成开始当天和结束日期前三天的提醒，不补发已错过日期的消息。"""

    today = now.astimezone(UTC8).date()
    reminders: dict[str, CalendarReminder] = {}
    for activity in activities:
        name = str(activity.get("name") or "").strip()
        start = _activity_time(activity.get("startTime"))
        end = _activity_time(activity.get("endTime"))
        if not name or start is None or end is None or end <= start or now >= end:
            continue
        due = []
        if today == start.date():
            due.append(("start", "今日开始"))
        if today == end.date() - timedelta(days=3) and today >= start.date():
            due.append(("end", "三天后结束"))
        for kind, reason in due:
            # 开始提醒不随结束时间调整而重发；同场活动重复条目只分发一次。
            identity = [game, name, start.isoformat(), kind, today.isoformat()]
            key = hashlib.sha256(
                json.dumps(identity, ensure_ascii=False).encode()
            ).hexdigest()
            reminders[key] = CalendarReminder(
                key=key,
                payload=NotifyPayload(
                    title=f"{label}活动提醒：{reason}",
                    body_title=f"【{label}活动提醒】",
                    text=(
                        f"{name}：{reason}\n"
                        f"开始时间：{start:%Y-%m-%d %H:%M}\n"
                        f"结束时间：{end:%Y-%m-%d %H:%M}\n"
                        "（北京时间）"
                    ),
                ),
            )
    return list(reminders.values())


class _GameCalendar:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._date = ""
        self._delivered: dict[str, list[str]] = {}
        self._dirty = False

    async def check(self) -> None:
        """读取当前显示设置，独立检查每个游戏并记录实际送达的渠道。"""

        async with self._lock:
            frontend_path = Config.config_path / "frontend_config.json"
            config = (
                json.loads(frontend_path.read_text(encoding="utf-8"))
                if frontend_path.exists()
                else {}
            )
            games = visible_calendar_games(config)
            target = global_target(include_system=True, empty_policy="skip")
            if not games or not target.channels:
                return
            now = datetime.now(tz=UTC8)
            today = now.date().isoformat()
            ledger_path = Config.config_path / "GameCalendarNotify.json"
            if self._date != today:
                self._delivered = self._load_delivered(ledger_path, today=today)
                self._date = today
                self._dirty = False
            # 落盘暂时失败后先重试保存，不能因为渠道已送达就永远跳过写盘。
            if self._dirty:
                self._save_delivered(ledger_path)

            for game, (source, label) in games.items():
                # 老版本的服务器偏好在浏览器里，先等首页迁移，不能猜成国服发送。
                if game == "bluearchive" and "homeBlueArchiveServer" not in config:
                    continue
                try:
                    activities = await fetch_calendar_activities(source)
                    if activities is None:
                        continue
                    # 网络等待可能跨日，下一轮按新日期重新检查，不发送旧日期消息。
                    checked_at = datetime.now(tz=UTC8)
                    if checked_at.date() != now.date():
                        return
                    for reminder in calendar_reminders(
                        activities, game=source or game, label=label, now=checked_at
                    ):
                        delivered = self._delivered.setdefault(reminder.key, [])
                        result = await dispatch(
                            reminder.payload,
                            [target],
                            skip_channel_ids=tuple(delivered),
                            attempts=3,
                            retry_delay=3,
                        )
                        if result.succeeded_ids:
                            delivered.extend(result.succeeded_ids)
                            self._dirty = True
                            self._save_delivered(ledger_path)
                        if result.failed:
                            logger.warning(
                                f"{label}活动提醒部分发送失败：{'、'.join(result.failed)}"
                            )
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    logger.opt(exception=error).warning(
                        f"检查{label}活动提醒失败，下次重试"
                    )

    def _save_delivered(self, path: Path) -> None:
        write_file(path, {"date": self._date, "delivered": self._delivered})
        self._dirty = False

    @staticmethod
    def _load_delivered(path: Path, *, today: str) -> dict[str, list[str]]:
        if not path.exists():
            return {}
        # 记录损坏时保留原文件并停止本轮，避免把已发送的通知当成未发送反复推送。
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("游戏日历通知记录格式无效")
        if data.get("date") != today:
            return {}
        delivered = data.get("delivered")
        if not isinstance(delivered, dict) or any(
            not isinstance(ids, list) or any(not isinstance(uid, str) for uid in ids)
            for ids in delivered.values()
        ):
            raise ValueError("游戏日历通知记录格式无效")
        return delivered


GameCalendar = _GameCalendar()
