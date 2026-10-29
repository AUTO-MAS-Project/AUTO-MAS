"""日历按区服去重、持久化、完成状态与通知重试的回归。"""

import asyncio
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import game_calendar as calendar
from app.core import game_calendar_host as calendar_host
from app.models.config import BAAHConfig
from app.models.notification_channel import ChannelTarget, DispatchResult, NotifyTarget
from app.utils import UTC8


class Clock(datetime):
    current = datetime(2030, 10, 1, 12, tzinfo=UTC8)

    @classmethod
    def now(cls, tz=None):
        return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)


def script(*lines):
    users = {}
    for line, enabled in lines:
        users[str(uuid.uuid4())] = {
            "Info": {"ActivityLineType": line, "Status": enabled}
        }
    return BAAHConfig.model_validate(
        {
            "UserData": {
                "order": [{"uid": uid, "type": "BAAHUserConfig"} for uid in users],
                "data": users,
            }
        }
    )


@pytest.fixture
def host(monkeypatch, tmp_path):
    Clock.current = datetime(2030, 10, 1, 12, tzinfo=UTC8)
    monkeypatch.setattr(calendar, "datetime", Clock)
    monkeypatch.setattr(calendar_host.Config, "config_path", tmp_path)
    scripts = {
        "first": script(("CN", True), ("CN", True), ("JP", True)),
        "second": script(("CN", True), ("Globle", True), ("JP", False)),
    }
    monkeypatch.setattr(calendar_host.Config, "ScriptConfig", scripts)

    async def fetch(source):
        activity = {
            "name": source + "-event",
            "startTime": "2030-10-01T09:00:00+08:00",
            "endTime": "2030-10-08T23:00:00+08:00",
        }
        return [activity, dict(activity)]

    fetcher = AsyncMock(side_effect=fetch)
    return SimpleNamespace(fetch=fetcher, path=tmp_path)


def service(host, *channel_ids, dispatcher=None):
    target = NotifyTarget(
        channels=tuple(
            (SimpleNamespace(), ChannelTarget(id=id, label=id)) for id in channel_ids
        )
    )
    dispatcher = dispatcher or AsyncMock(
        return_value=DispatchResult(succeeded_ids=channel_ids)
    )
    return calendar.GameCalendarService(
        read_targets=calendar_host.notification_targets,
        fetch_activities=host.fetch,
        resolve_source=calendar_host.activity_source,
        schedule_path=lambda: host.path / "GameCalendarSchedule.json",
        dispatcher=dispatcher,
        prepare_target=lambda: target,
    ), dispatcher


@pytest.mark.asyncio
async def test_servers_accounts_refresh_delivery_and_restart_are_deduplicated(host):
    instance, send = service(host, "channel")
    assert instance._notification_games() == {
        ("bluearchive", "ba-cn"): "碧蓝档案（国服）",
        ("bluearchive", "ba-jp"): "碧蓝档案（日服）",
        ("bluearchive", "ba-global"): "碧蓝档案（国际服）",
    }
    await instance.refresh_schedule()
    assert [call.args[0] for call in host.fetch.await_args_list] == [
        "ba-cn",
        "ba-jp",
        "ba-global",
    ]
    await instance.send_due_reminders()
    assert send.await_count == 1
    body = send.await_args.args[0].text
    for source in ("ba-cn", "ba-jp", "ba-global"):
        assert body.count(source + "-event") == 1
    for label in ("国服", "日服", "国际服"):
        assert f"碧蓝档案（{label}）" in body
    await instance.refresh_schedule()
    await instance.send_due_reminders()
    assert send.await_count == 1
    restored, after_restart = service(host, "channel")
    assert not restored.has_due_reminders()
    await restored.send_due_reminders()
    after_restart.assert_not_awaited()


@pytest.mark.asyncio
async def test_completion_is_persisted_scoped_and_suppresses_only_its_server(host):
    instance, _ = service(host, "channel")
    await instance.refresh_schedule()
    await instance.set_activity_completed(
        game="bluearchive",
        server="jp",
        name="ba-jp-event",
        start=datetime(2030, 10, 1, 9, tzinfo=UTC8),
        end=datetime(2030, 10, 8, 23, tzinfo=UTC8),
        completed=True,
    )
    restored, send = service(host, "channel")
    assert (
        len(await restored.completed_activities(game="bluearchive", server="jp")) == 1
    )
    assert await restored.completed_activities(game="bluearchive", server="cn") == []
    await restored.send_due_reminders()
    assert "ba-jp-event" not in send.await_args.args[0].text
    assert "ba-cn-event" in send.await_args.args[0].text
    await restored.set_activity_completed(
        game="bluearchive",
        server="jp",
        name="ba-jp-event",
        start=datetime(2030, 10, 1, 9, tzinfo=UTC8),
        end=datetime(2030, 10, 8, 23, tzinfo=UTC8),
        completed=False,
    )
    await restored.send_due_reminders()
    assert send.await_count == 2
    assert "ba-jp-event" in send.await_args.args[0].text
    assert "ba-cn-event" not in send.await_args.args[0].text


@pytest.mark.asyncio
async def test_partial_delivery_retries_only_failed_channel_after_restart(host):
    send = AsyncMock(
        return_value=DispatchResult(succeeded_ids=("one",), failed=("two",))
    )
    instance, _ = service(host, "one", "two", dispatcher=send)
    await instance.refresh_schedule()
    await instance.send_due_reminders()
    restored, retry = service(host, "one", "two")
    await restored.send_due_reminders()
    retry.assert_not_awaited()
    Clock.current += timedelta(seconds=calendar.CALENDAR_RETRY_INTERVAL_SECONDS)
    await restored.send_due_reminders()
    retry.assert_awaited_once()
    assert retry.await_args.kwargs["skip_channel_ids"] == {"one"}
    assert not restored.has_due_reminders()


@pytest.mark.asyncio
async def test_refresh_failure_retains_schedule_and_cancellation_propagates(host):
    instance, send = service(host, "channel")
    await instance.refresh_schedule()
    host.fetch.side_effect = OSError("offline")
    await instance.refresh_schedule()
    await instance.send_due_reminders()
    send.assert_awaited_once()
    host.fetch.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await instance.refresh_schedule()


@pytest.mark.asyncio
async def test_cancelled_delivery_can_be_retried_without_consuming_reminders(host):
    send = AsyncMock(side_effect=asyncio.CancelledError)
    instance, _ = service(host, "channel", dispatcher=send)
    await instance.refresh_schedule()
    with pytest.raises(asyncio.CancelledError):
        await instance.send_due_reminders()
    restored, retry = service(host, "channel")
    await restored.send_due_reminders()
    retry.assert_awaited_once()


@pytest.mark.asyncio
async def test_host_reads_current_enabled_accounts_on_each_refresh(host, monkeypatch):
    instance, _ = service(host, "channel")
    await instance.refresh_schedule()
    host.fetch.reset_mock()
    monkeypatch.setattr(
        calendar_host.Config,
        "ScriptConfig",
        {"new": script(("JP", False), ("Globle", True), ("Globle", True))},
    )
    await instance.refresh_schedule()
    host.fetch.assert_awaited_once_with("ba-global")
