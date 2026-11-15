"""活动空档可编辑上期结构，但过期关卡不得进入刷取计划。"""

import json
from datetime import datetime, timezone

import pytest

from app.task.MAA.stage_service import MaaStageCache, MaaStageService
from app.task.MAA.tools.activity_inventory import resolve_activity_inventory_plans

NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)


def _event(start: str, end: str, drops: list[str]) -> dict:
    return {
        "Activity": {
            "UtcStartTime": start,
            "UtcExpireTime": end,
            "TimeZone": 8,
        },
        "Stages": [
            {"Display": f"TEST-{i}", "Value": f"TEST-{i}", "Drop": drop}
            for i, drop in enumerate(drops, start=1)
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "now,server,template,drops",
    [
        (NOW, "Bilibili", ["material", "material", "orundum"], []),
        (datetime(2026, 11, 2, tzinfo=timezone.utc), "Official", [], ["30023"]),
    ],
)
async def test_activity_overview_never_plans_expired_templates(
    now, server, template, drops
):
    content = json.dumps(
        {
            "Official": {
                "sideStoryStage": {
                    "previous": _event(
                        "2026/10/09 12:00:00",
                        "2026/10/23 03:59:59",
                        ["30013", "30023", "搓玉"],
                    ),
                    "older": _event(
                        "2026/09/01 12:00:00", "2026/09/15 03:59:59", ["30013"]
                    ),
                    "future": _event(
                        "2026/11/01 12:00:00", "2026/11/15 03:59:59", ["30023"]
                    ),
                }
            },
            "YoStarEN": {"sideStoryStage": {}},
        }
    )

    async def unexpected_call(*args, **kwargs):
        pytest.fail("有效缓存不应触发网络请求或写回")

    service = MaaStageService(
        read_cache=lambda: MaaStageCache(content=content, etag="test", checked_at=now),
        write_cache=unexpected_call,
        fetch=unexpected_call,
        now=lambda: now,
        track_task=lambda task: None,
    )
    overview = await service.get_stage_info("Info", server=server)
    assert overview["ActivityTemplate"] == template
    assert overview["ActivityStatus"] == ("ready" if drops else "empty")
    assert [stage["Drop"] for stage in overview["Activity"]] == drops
    assert {
        option["value"]
        for option in overview["Options"]
        if option["value"].startswith("TEST-")
    } == ({"TEST-1"} if drops else set())
    other_server = await service.get_stage_info("Info", server="YoStarEN")
    assert other_server["ActivityTemplate"] == []
    saved = '[{"StageType":"material","StageIndex":1,"DropCount":200}]'
    plans, notices = resolve_activity_inventory_plans(saved, overview["Activity"])
    assert [plan["Stage"] for plan in plans] == (["TEST-1"] if drops else [])
    if not drops:
        assert notices
