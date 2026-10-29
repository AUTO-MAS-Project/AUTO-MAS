"""公共日历独立于宿主配置、专项和活动源的注入契约。"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.core import game_calendar as calendar
from app.models.notification_channel import ChannelTarget, DispatchResult, NotifyTarget
from app.utils import UTC8


def test_service_import_does_not_load_host_or_concrete_sources():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import importlib.abc
import sys

class BlockHostImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        blocked = (
            'app.core.config', 'app.core.game_calendar_host',
            'app.core.notify', 'app.models.config', 'app.task', 'app.tools',
        )
        if any(fullname == name or fullname.startswith(name + '.') for name in blocked):
            raise AssertionError('公共日历加载了宿主或具体实现: ' + fullname)

sys.meta_path.insert(0, BlockHostImports())
from app.core.game_calendar import GameCalendarService
""",
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_injected_targets_source_and_path_drive_completion_and_delivery(
    monkeypatch, tmp_path
):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2030, 10, 1, 12, tzinfo=UTC8).astimezone(tz)

    monkeypatch.setattr(calendar, "datetime", Clock)
    targets = [calendar.CalendarTarget("custom", "custom-source", "自定义来源")] * 2
    activities = [
        {
            "name": "external-event",
            "startTime": "2030-10-01T09:00:00+08:00",
            "endTime": "2030-10-03T23:00:00+08:00",
        }
    ]
    fetch = AsyncMock(return_value=activities)
    resolve = Mock(return_value="custom-source")
    path = tmp_path / "independent-calendar.json"
    dependencies = {
        "read_targets": lambda: iter(targets),
        "fetch_activities": fetch,
        "resolve_source": resolve,
        "schedule_path": lambda: path,
    }
    service = calendar.GameCalendarService(**dependencies)
    await service.refresh_schedule()
    # 目标提供方无需去重，公共日历保证同来源只查询与提醒一次。
    fetch.assert_awaited_once_with("custom-source")
    assert path.exists()
    period = {
        "game": "custom",
        "server": "custom-server",
        "name": "external-event",
        "start": datetime(2030, 10, 1, 9, tzinfo=UTC8),
        "end": datetime(2030, 10, 3, 23, tzinfo=UTC8),
    }
    await service.set_activity_completed(**period, completed=True)
    restored = calendar.GameCalendarService(**dependencies)
    assert (
        len(await restored.completed_activities(game="custom", server="custom-server"))
        == 1
    )
    resolve.assert_called_with("custom", "custom-server")
    send = AsyncMock(return_value=DispatchResult(succeeded_ids=("channel",)))
    target = NotifyTarget(
        channels=((SimpleNamespace(), ChannelTarget(id="channel", label="channel")),)
    )
    restored.bind_notifications(dispatcher=send, prepare_target=lambda: target)
    await restored.send_due_reminders()
    send.assert_not_awaited()
    await restored.set_activity_completed(**period, completed=False)
    await restored.send_due_reminders()
    await restored.send_due_reminders()
    send.assert_awaited_once()
    assert send.await_args.args[0].text.count("external-event") == 1
    targets.clear()
    fetch.reset_mock()
    await restored.refresh_schedule()
    fetch.assert_not_awaited()
