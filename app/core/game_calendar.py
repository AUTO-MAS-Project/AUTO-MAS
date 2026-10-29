#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""统一管理游戏活动日程、完成状态和通知；目标与取数能力由宿主注入。"""

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path

from pydantic import AwareDatetime, TypeAdapter

from app.models.notification import NotifyPayload
from app.models.notification_channel import NotifyTarget
from app.models.notification_report import NotificationDispatcher
from app.utils import UTC8, get_logger
from app.utils import io as _utils_io

logger = get_logger("游戏日历")
CALENDAR_REFRESH_INTERVAL_SECONDS = 60 * 60
CALENDAR_RETRY_INTERVAL_SECONDS = 10 * 60


@dataclass(frozen=True)
class CalendarTarget:
    """宿主已解释的游戏、活动来源及显示名称。"""

    game: str
    source: str
    label: str


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
    next_attempt_at: AwareDatetime | None = None
    activity_key: str = ""


@dataclass
class CalendarActivityCompletion:
    game: str
    source: str
    name: str
    start_at: AwareDatetime
    end_at: AwareDatetime


_SCHEDULE_ADAPTER = TypeAdapter(list[CalendarReminder])
_COMPLETIONS_ADAPTER = TypeAdapter(list[CalendarActivityCompletion])


def _activity_key(*, source: str, name: str, start: datetime) -> str:
    identity = [source, name.strip(), start.astimezone(UTC8).isoformat()]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


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
            # 同场活动的重复条目只登记一次。
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
                activity_key=_activity_key(
                    source=source or game, name=name, start=start
                ),
                payload=NotifyPayload(
                    title=f"{label}活动提醒：{reason}",
                    body_title=f"【{label}活动提醒】",
                    text=f"{name}：{reason}",
                ),
            )
    return list(reminders.values())


class GameCalendarService:
    def __init__(
        self,
        *,
        read_targets: Callable[[], Iterable[CalendarTarget]],
        fetch_activities: Callable[
            [str], Awaitable[Sequence[Mapping[str, object]] | None]
        ],
        resolve_source: Callable[[str, str], str],
        schedule_path: Callable[[], Path],
        dispatcher: NotificationDispatcher | None = None,
        prepare_target: Callable[[], NotifyTarget] | None = None,
    ) -> None:
        self._read_targets = read_targets
        self._fetch_activities = fetch_activities
        self._resolve_source = resolve_source
        self._schedule_path = schedule_path
        self._dispatcher = dispatcher
        self._prepare_target = prepare_target
        self._lock = asyncio.Lock()
        self._loaded = False
        self._reminders: dict[str, CalendarReminder] = {}
        self._completions: dict[str, CalendarActivityCompletion] = {}
        self._dirty = False
        self._save_retry_at: datetime | None = None

    def bind_notifications(
        self,
        *,
        dispatcher: NotificationDispatcher,
        prepare_target: Callable[[], NotifyTarget],
    ) -> None:
        self._dispatcher = dispatcher
        self._prepare_target = prepare_target

    def _load_schedule(self) -> None:
        """恢复已生成的日程，启动后的推送不等待活动接口。"""

        if self._loaded:
            return
        path = self._schedule_path()
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            reminders = _SCHEDULE_ADAPTER.validate_python(data["reminders"])
            self._reminders = {reminder.key: reminder for reminder in reminders}
            completions = _COMPLETIONS_ADAPTER.validate_python(
                data.get("completed_activities", [])
            )
            self._completions = {
                _activity_key(
                    source=item.source, name=item.name, start=item.start_at
                ): item
                for item in completions
                if item.end_at > datetime.now(tz=UTC8)
            }
        self._loaded = True

    async def completed_activities(
        self, *, game: str, server: str = "cn"
    ) -> list[CalendarActivityCompletion]:
        """读取用户完成记录；通知渠道的送达记录不代表活动已完成。"""
        self._load_schedule()
        source = self._resolve_source(game, server)
        async with self._lock:
            now = datetime.now(tz=UTC8)
            return [
                item
                for item in self._completions.values()
                if item.game == game and item.source == source and item.end_at > now
            ]

    async def set_activity_completed(
        self,
        *,
        game: str,
        name: str,
        start: datetime,
        end: datetime,
        completed: bool,
        server: str = "cn",
    ) -> None:
        """保存用户手动标记，与通知派发共用日程锁。"""
        self._load_schedule()
        source = self._resolve_source(game, server)
        key = _activity_key(source=source, name=name, start=start)
        async with self._lock:
            previous = self._completions.get(key)
            if completed:
                now = datetime.now(tz=UTC8)
                if not start <= now < end:
                    raise ValueError("只能完成进行中的活动")
                self._completions[key] = CalendarActivityCompletion(
                    game=game,
                    source=source,
                    name=name.strip(),
                    start_at=start.astimezone(UTC8),
                    end_at=end.astimezone(UTC8),
                )
            else:
                self._completions.pop(key, None)
            try:
                self._save_schedule()
            except (OSError, TypeError, ValueError):
                if previous is None:
                    self._completions.pop(key, None)
                else:
                    self._completions[key] = previous
                raise

    def _activity_completed(self, reminder: CalendarReminder) -> bool:
        if reminder.activity_key:
            item = self._completions.get(reminder.activity_key)
            return item is not None and item.end_at > datetime.now(tz=UTC8)
        # 旧日程没有活动键，按来源、名称及本场时间范围匹配，离线时也能停止提醒。
        name = reminder.payload.text.split("\n开始时间：", 1)[0].rsplit("：", 1)[0]
        return any(
            item.game == reminder.game
            and item.source == (reminder.source or reminder.game)
            and item.name == name
            and datetime.combine(item.start_at.date(), time.min, tzinfo=UTC8)
            <= reminder.due_at
            < item.end_at
            for item in self._completions.values()
        )

    def _notification_games(self) -> dict[tuple[str, str], str]:
        # 同一游戏的不同服分别登记，多个托管账号命中同一服时只提醒一次。
        return {
            (target.game, target.source): target.label
            for target in self._read_targets()
        }

    async def refresh_schedule(self) -> None:
        """定期获取活动并登记新日程，已登记日程保持不变。"""

        self._load_schedule()
        games = self._notification_games()
        for (game, source), label in games.items():
            try:
                # 取数在日程锁外，到点的已登记日程不受慢请求或断网影响。
                activities = await self._fetch_activities(source)
                if activities is None:
                    continue
                now = datetime.now(tz=UTC8)
                reminders = calendar_reminders(
                    activities, game=game, source=source, label=label, now=now
                )
                async with self._lock:
                    self._reminders = {
                        key: reminder
                        for key, reminder in self._reminders.items()
                        if reminder.expires_at > now
                    }
                    # 活动排期固定：只补充新日程，保留已有日程与各渠道送达记录。
                    for reminder in reminders:
                        self._reminders.setdefault(reminder.key, reminder)
                    self._save_schedule()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.opt(exception=error).warning(
                    f"登记{label}活动日程失败，保留已有日程"
                )

    def has_due_reminders(self) -> bool:
        """供主定时器按已登记日程派发后台推送，不查询活动源。"""

        self._load_schedule()
        now = datetime.now(tz=UTC8)
        if self._dirty:
            return self._save_retry_at is None or now >= self._save_retry_at
        return any(
            not reminder.completed
            and not self._activity_completed(reminder)
            and (reminder.next_attempt_at or reminder.due_at)
            <= now
            < reminder.expires_at
            for reminder in self._reminders.values()
        )

    async def send_due_reminders(self) -> None:
        """汇总所有游戏已到点的日程，按渠道保存送达状态与重试时刻。"""
        if self._dispatcher is None or self._prepare_target is None:
            raise RuntimeError("游戏日历的通知依赖尚未装配")

        self._load_schedule()
        async with self._lock:
            if self._dirty:
                self._save_schedule()
            games = self._notification_games()
            target = self._prepare_target()
            target_ids = {channel_target.id for _, channel_target in target.channels}
            now = datetime.now(tz=UTC8)
            reminders: list[CalendarReminder] = []
            for reminder in self._reminders.values():
                if (
                    reminder.completed
                    or self._activity_completed(reminder)
                    or not (
                        (reminder.next_attempt_at or reminder.due_at)
                        <= now
                        < reminder.expires_at
                    )
                ):
                    continue
                if (reminder.game, reminder.source) not in games or not target_ids:
                    reminder.next_attempt_at = now + timedelta(
                        seconds=CALENDAR_RETRY_INTERVAL_SECONDS
                    )
                    self._save_schedule()
                    continue
                if target_ids.issubset(reminder.delivered):
                    reminder.completed = not target.unresolved
                    if not reminder.completed:
                        reminder.next_attempt_at = now + timedelta(
                            seconds=CALENDAR_RETRY_INTERVAL_SECONDS
                        )
                    self._save_schedule()
                    continue
                reminders.append(reminder)

            # 每个渠道只汇总尚未送达的活动，内容相同的渠道一起分发。
            channel_groups: dict[tuple[str, ...], set[str]] = {}
            reminders_by_key = {reminder.key: reminder for reminder in reminders}
            for channel_id in target_ids:
                pending = tuple(
                    reminder.key
                    for reminder in reminders
                    if channel_id not in reminder.delivered
                )
                if pending:
                    channel_groups.setdefault(pending, set()).add(channel_id)
            for keys, channel_ids in channel_groups.items():
                batch = [reminders_by_key[key] for key in keys]
                game_sections: dict[tuple[str, str], list[str]] = {}
                for reminder in batch:
                    # 兼容已保存的旧提醒，正文只保留活动名称与提醒原因。
                    game_sections.setdefault(
                        (reminder.game, reminder.source), []
                    ).append(reminder.payload.text.split("\n开始时间：", 1)[0])
                payload = NotifyPayload(
                    title="游戏活动提醒",
                    text="\n\n".join(
                        f"【{games[game]}】\n" + "\n".join(activities)
                        for game, activities in game_sections.items()
                    ),
                )
                try:
                    result = await self._dispatcher(
                        payload,
                        [target],
                        skip_channel_ids=target_ids - channel_ids,
                        attempts=3,
                        retry_delay=3,
                    )
                    for reminder in batch:
                        reminder.delivered = tuple(
                            dict.fromkeys((*reminder.delivered, *result.succeeded_ids))
                        )
                        reminder.completed = (
                            not target.unresolved
                            and target_ids.issubset(reminder.delivered)
                        )
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
                for reminder in batch:
                    reminder.next_attempt_at = now + timedelta(
                        seconds=CALENDAR_RETRY_INTERVAL_SECONDS
                    )
                self._save_schedule()

    def _save_schedule(self) -> None:
        self._dirty = True
        now = datetime.now(tz=UTC8)
        self._completions = {
            key: item for key, item in self._completions.items() if item.end_at > now
        }
        try:
            _utils_io.write_file(
                self._schedule_path(),
                {
                    "reminders": _SCHEDULE_ADAPTER.dump_python(
                        list(self._reminders.values()), mode="json"
                    ),
                    "completed_activities": _COMPLETIONS_ADAPTER.dump_python(
                        list(self._completions.values()), mode="json"
                    ),
                },
            )
        except (OSError, TypeError, ValueError):
            self._save_retry_at = datetime.now(tz=UTC8) + timedelta(minutes=1)
            raise
        self._dirty = False
        self._save_retry_at = None
