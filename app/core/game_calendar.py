#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""按首页显示设置推送游戏活动开始与结束提醒。"""

import asyncio
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path

from pydantic import AwareDatetime, TypeAdapter

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
CALENDAR_REFRESH_INTERVAL_SECONDS = 60 * 60
CALENDAR_RETRY_INTERVAL_SECONDS = 10 * 60


@dataclass
class CalendarReminder:
    key: str
    game: str
    source: str
    due_at: AwareDatetime
    expires_at: AwareDatetime
    payload: NotifyPayload
    delivered: tuple[str, ...] = ()
    completed: bool = False
    active: bool = True
    next_attempt_at: AwareDatetime | None = None


_SCHEDULE_ADAPTER = TypeAdapter(list[CalendarReminder])


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
    source: str,
    label: str,
    now: datetime,
) -> list[CalendarReminder]:
    """按活动日期提前生成两条日程，过期日程不再登记。"""

    reminders: dict[str, CalendarReminder] = {}
    for activity in activities:
        name = str(activity.get("name") or "").strip()
        start = _activity_time(activity.get("startTime"))
        end = _activity_time(activity.get("endTime"))
        if not name or start is None or end is None or end <= start or now >= end:
            continue
        due = [("start", "今日开始", start.date())]
        ending_date = end.date() - timedelta(days=3)
        if ending_date >= start.date():
            due.append(("end", "三天后结束", ending_date))
        for kind, reason, reminder_date in due:
            due_at = datetime.combine(reminder_date, time.min, tzinfo=UTC8)
            expires_at = min(due_at + timedelta(days=1), end)
            if now >= expires_at:
                continue
            # 开始提醒不随结束时间调整而重发；同场活动重复条目只分发一次。
            identity = [
                source or game,
                name,
                start.isoformat(),
                kind,
                reminder_date.isoformat(),
            ]
            key = hashlib.sha256(
                json.dumps(identity, ensure_ascii=False).encode()
            ).hexdigest()
            reminders[key] = CalendarReminder(
                key=key,
                game=game,
                source=source,
                due_at=due_at,
                expires_at=expires_at,
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
        self._loaded = False
        self._reminders: dict[str, CalendarReminder] = {}
        self._legacy_delivered: dict[str, list[str]] = {}
        self._dirty = False
        self._save_retry_at: datetime | None = None

    def _load_schedule(self) -> None:
        """恢复已生成的日程，启动后的推送不等待活动接口。"""

        if self._loaded:
            return
        path = Config.config_path / "GameCalendarSchedule.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            reminders = _SCHEDULE_ADAPTER.validate_python(data["reminders"])
            self._reminders = {reminder.key: reminder for reminder in reminders}
        # 兼容此前按当天记账的发送记录，迁移后仍按相同活动和渠道去重。
        self._legacy_delivered = self._load_delivered(
            Config.config_path / "GameCalendarNotify.json",
            today=datetime.now(tz=UTC8).date().isoformat(),
        )
        self._loaded = True

    @staticmethod
    def _visible_games() -> dict[str, tuple[str, str]]:
        path = Config.config_path / "frontend_config.json"
        config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        games = visible_calendar_games(config)
        # 老版本的服务器偏好在浏览器里，先等首页迁移，不能猜成国服发送。
        if "homeBlueArchiveServer" not in config:
            games.pop("bluearchive", None)
        return games

    async def refresh_schedule(self) -> None:
        """刷新活动并更新未来日程；此入口只登记日程，不发送通知。"""

        self._load_schedule()
        games = self._visible_games()
        for game, (source, label) in games.items():
            try:
                # 取数在日程锁外，到点的已登记日程不受慢请求或断网影响。
                activities = await fetch_calendar_activities(source)
                if activities is None:
                    continue
                now = datetime.now(tz=UTC8)
                reminders = calendar_reminders(
                    activities, game=game, source=source, label=label, now=now
                )
                async with self._lock:
                    updated = {
                        key: reminder
                        for key, reminder in self._reminders.items()
                        if reminder.expires_at > now
                    }
                    # 撤下的活动取消日程，但当天的送达记录保留，重新出现也不重复推送。
                    for previous in updated.values():
                        if previous.game == game:
                            previous.active = False
                    for reminder in reminders:
                        previous = self._reminders.get(reminder.key)
                        if previous is not None:
                            reminder.delivered = previous.delivered
                            reminder.completed = previous.completed
                            reminder.next_attempt_at = previous.next_attempt_at
                        else:
                            reminder.delivered = tuple(
                                self._legacy_delivered.get(reminder.key, ())
                            )
                        updated[reminder.key] = reminder
                    self._reminders = updated
                    self._save_schedule()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.opt(exception=error).warning(
                    f"更新{label}活动日程失败，保留已有日程"
                )

    def has_due_reminders(self) -> bool:
        """供主定时器按已登记日程派发后台推送，不查询活动源。"""

        self._load_schedule()
        now = datetime.now(tz=UTC8)
        if self._dirty:
            return self._save_retry_at is None or now >= self._save_retry_at
        return any(
            reminder.active
            and not reminder.completed
            and (reminder.next_attempt_at or reminder.due_at)
            <= now
            < reminder.expires_at
            for reminder in self._reminders.values()
        )

    async def send_due_reminders(self) -> None:
        """执行已到点的日程，按渠道保存送达状态与下次重试时刻。"""

        self._load_schedule()
        async with self._lock:
            if self._dirty:
                self._save_schedule()
            games = self._visible_games()
            target = global_target(include_system=True, empty_policy="skip")
            target_ids = {channel_target.id for _, channel_target in target.channels}
            for reminder in self._reminders.values():
                now = datetime.now(tz=UTC8)
                if (
                    not reminder.active
                    or reminder.completed
                    or not (
                        (reminder.next_attempt_at or reminder.due_at)
                        <= now
                        < reminder.expires_at
                    )
                ):
                    continue
                current_game = games.get(reminder.game)
                if (
                    current_game is None
                    or current_game[0] != reminder.source
                    or not target_ids
                ):
                    reminder.next_attempt_at = now + timedelta(
                        seconds=CALENDAR_RETRY_INTERVAL_SECONDS
                    )
                    self._save_schedule()
                    continue
                try:
                    if target_ids.issubset(reminder.delivered):
                        reminder.completed = True
                    else:
                        result = await dispatch(
                            reminder.payload,
                            [target],
                            skip_channel_ids=reminder.delivered,
                            attempts=3,
                            retry_delay=3,
                        )
                        reminder.delivered = tuple(
                            dict.fromkeys((*reminder.delivered, *result.succeeded_ids))
                        )
                        reminder.completed = result.attempted > 0 and not result.failed
                        if result.failed:
                            logger.warning(
                                f"游戏日历提醒部分发送失败：{'、'.join(result.failed)}"
                            )
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    logger.opt(exception=error).warning(
                        "执行游戏日历日程失败，下次重试"
                    )
                reminder.next_attempt_at = now + timedelta(
                    seconds=CALENDAR_RETRY_INTERVAL_SECONDS
                )
                self._save_schedule()

    def _save_schedule(self) -> None:
        self._dirty = True
        try:
            write_file(
                Config.config_path / "GameCalendarSchedule.json",
                {
                    "reminders": _SCHEDULE_ADAPTER.dump_python(
                        list(self._reminders.values()), mode="json"
                    )
                },
            )
        except (OSError, TypeError, ValueError):
            self._save_retry_at = datetime.now(tz=UTC8) + timedelta(minutes=1)
            raise
        self._dirty = False
        self._save_retry_at = None

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
