import asyncio
import json
from datetime import datetime

import app.core.taskboard as state
from app.core import Taskboard
from app.models.taskboard import (
    TaskboardState,
    TaskboardVersionStoryUpdate,
    TaskboardWeeklyRecord,
)


def _record(name: str, version: str = "1.0") -> TaskboardVersionStoryUpdate:
    return TaskboardVersionStoryUpdate(
        game="genshin",
        version=version,
        version_name=name,
        start="2026-01-01T00:00:00+08:00",
        end="2026-02-01T00:00:00+08:00",
    )


def test_weekly_key_switches_at_monday_0400_beijing_time():
    assert (
        Taskboard.weekly_key(datetime.fromisoformat("2026-10-26T03:59:59+08:00"))
        == "2026-10-19"
    )
    assert (
        Taskboard.weekly_key(datetime.fromisoformat("2026-10-26T04:00:00+08:00"))
        == "2026-10-26"
    )


def test_prune_caps_weekly_and_version_maps():
    week = Taskboard.weekly_key()
    weekly = TaskboardState()
    for index in range(101):
        weekly.weekly[f"game{index}"] = TaskboardWeeklyRecord(
            week=week, done_at=f"2026-10-26 10:{index % 60:02d}"
        )
    Taskboard._prune(weekly)
    assert len(weekly.weekly) == 100

    versions = TaskboardState()
    for game in range(30):
        for version in range(20):
            key = f"game{game}|{version}"
            versions.version_story[key] = state.TaskboardVersionStoryRecord(
                game=f"game{game}",
                version=f"{version}",
                start=f"2025-{(version % 12) + 1:02d}-01T00:00:00+08:00",
                end="2025-12-31T00:00:00+08:00",
            )
    active_key = "game0|active"
    versions.version_story[active_key] = state.TaskboardVersionStoryRecord(
        game="game0",
        version="active",
        start="2020-01-01T00:00:00+08:00",
        end="2027-01-01T00:00:00+08:00",
    )
    Taskboard._prune(versions)
    assert len(versions.version_story) == 500
    assert active_key in versions.version_story


def test_merge_version_story_ignores_older_batch(tmp_path, monkeypatch):
    monkeypatch.setattr(
        Taskboard, "state_path", lambda: tmp_path / "TaskboardData.json"
    )

    async def run():
        await Taskboard.merge_version_story([_record("new")], 200)
        await Taskboard.merge_version_story([_record("old")], 100)
        await Taskboard.merge_version_story([_record("second", "2.0")], 100)

    asyncio.run(run())
    data = json.loads((tmp_path / "TaskboardData.json").read_text(encoding="utf-8"))
    assert data["version_story"]["genshin|1.0"]["version_name"] == "new"
    assert data["version_story"]["genshin|2.0"]["version_name"] == "second"
