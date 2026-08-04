import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from app.core.config import AppConfig
from app.models.config import MaaConfig
from app.task.MAA.AutoProxy import (
    AutoProxyTask,
    _build_depot_maintain_task,
    _resolve_activity_stage,
)
from app.utils.constants import MAA_TASKS


def test_build_depot_maintain_task_filters_invalid_plans() -> None:
    task = _build_depot_maintain_task(
        json.dumps(
            [
                {"Stage": "1-7", "DropId": "30012", "DropCount": 100},
                {"Stage": "CE-6", "DropId": "4001", "DropCount": 0},
                {"Stage": "", "DropId": "2001", "DropCount": 50},
                "invalid",
            ]
        )
    )

    assert task["TaskType"] == "DepotMaintain"
    assert task["UseAutoSeries"] is True
    assert MAA_TASKS.index("DepotMaintain") < MAA_TASKS.index("Fight")
    assert task["PlanList"] == [
        {
            "Stage": "1-7",
            "DropId": "30012",
            "DropCount": 100,
            "UseMedicine": False,
            "MedicineCount": 0,
            "UseStone": False,
            "StoneCount": 0,
        }
    ]


def test_get_maa_depot_items_uses_numeric_farmable_items() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        resource = root / "resource"
        resource.mkdir()
        (resource / "item_index.json").write_text(
            json.dumps(
                {
                    "1stact": {"name": "活动道具"},
                    "4002": {"name": "源石"},
                    "30012": {"name": "固源岩"},
                    "2001": {"name": "基础作战记录"},
                }
            ),
            encoding="utf-8",
        )

        script_id = uuid.uuid4()
        script_config = MaaConfig()
        script_config.Info_Path.setValue(str(root))
        owner = SimpleNamespace(ScriptConfig={script_id: script_config})

        items = asyncio.run(AppConfig.get_maa_depot_items(owner, str(script_id)))

    assert items == [
        {"label": "基础作战记录", "value": "2001"},
        {"label": "固源岩", "value": "30012"},
    ]


def test_resolve_activity_stage_keeps_the_selected_position() -> None:
    current_stages = [
        {"Value": "TO-9"},
        {"Value": "TO-8"},
        {"Value": "TO-7"},
        {"Value": "TO-5"},
    ]
    next_stages = [
        {"Value": "AS-10"},
        {"Value": "AS-9"},
        {"Value": "AS-8"},
        {"Value": "AS-3"},
    ]

    assert _resolve_activity_stage(current_stages, 2) == "TO-8"
    assert _resolve_activity_stage(next_stages, 2) == "AS-9"
    assert _resolve_activity_stage(next_stages, 99) == "AS-10"
    assert _resolve_activity_stage([], 2) is None


def test_stage_info_uses_the_selected_maa_server_and_activity_timezone() -> None:
    def make_activity(server_timezone: int, stage: str) -> dict:
        now = datetime.now(tz=timezone(timedelta(hours=server_timezone)))
        return {
            "Activity": {
                "Tip": "",
                "StageName": stage.split("-")[0],
                "UtcStartTime": (now - timedelta(hours=1)).strftime(
                    "%Y/%m/%d %H:%M:%S"
                ),
                "UtcExpireTime": (now + timedelta(hours=1)).strftime(
                    "%Y/%m/%d %H:%M:%S"
                ),
                "TimeZone": server_timezone,
            },
            "Stages": [
                {
                    "Display": stage,
                    "Value": stage,
                    "Drop": "30012",
                }
            ],
        }

    raw_stage_data = {
        "Official": {
            "sideStoryStage": {"TO": make_activity(8, "TO-9")},
        },
        "YoStarEN": {
            "sideStoryStage": {"TA": make_activity(-7, "TA-9")},
        },
    }

    class RawStageConfigStub:
        def get(self, _group: str, _key: str) -> str:
            return json.dumps(raw_stage_data)

    parsed_stage_data = AppConfig.getStage(RawStageConfigStub())

    class StageInfoConfigStub:
        async def get_stage(self, refresh: bool = False) -> dict:
            return json.loads(parsed_stage_data)

        def get(self, _group: str, key: str) -> str:
            if key == "StageData":
                return json.dumps(raw_stage_data)
            return parsed_stage_data

    stage_config = StageInfoConfigStub()
    en_info = asyncio.run(
        AppConfig.get_stage_info(stage_config, "Info", server="YoStarEN")
    )
    bilibili_info = asyncio.run(
        AppConfig.get_stage_info(stage_config, "Info", server="Bilibili")
    )

    assert [stage["Value"] for stage in en_info["Activity"]] == ["TA-9"]
    assert "TA-9" in [stage["value"] for stage in en_info["Options"]]
    assert "TO-9" not in [stage["value"] for stage in en_info["Options"]]
    assert [stage["Value"] for stage in bilibili_info["Activity"]] == ["TO-9"]


def test_forced_stage_refresh_waits_for_latest_activity_data() -> None:
    class StageConfigStub:
        def __init__(self) -> None:
            self._stage_refresh_task = None
            self.temp_task = []
            self.stage = json.dumps({"Info": [{"Value": "TO-9"}]})

        def get(self, _group: str, key: str) -> str:
            if key == "LastStageUpdated":
                return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return self.stage

        async def _refresh_stage(self) -> None:
            self.stage = json.dumps({"Info": [{"Value": "AS-10"}]})

    stage_config = StageConfigStub()

    result = asyncio.run(AppConfig.get_stage(stage_config, refresh=True))

    assert result == {"Info": [{"Value": "AS-10"}]}


def test_fight_failure_keeps_fight_pending_after_another_fight_completes() -> None:
    for failure_log in (
        "任务出错: 理智作战\n",
        "理智作战: 活动关优先 添加任务失败\n",
    ):
        task = object.__new__(AutoProxyTask)
        task.cur_user_log = SimpleNamespace(content=[], status="")
        task.script_info = SimpleNamespace(log="")
        task.task_dict = dict.fromkeys(MAA_TASKS, False)
        task.mode = "Routine"
        task.wait_event = SimpleNamespace(set=lambda: None)

        asyncio.run(
            task.check_log(
                ["完成任务: 理智作战\n", failure_log, "任务已全部完成！\n"],
                datetime.now(),
            )
        )

        assert task.task_dict["Fight"] is True
        assert task.cur_user_log.status == "MAA 部分任务执行失败"
