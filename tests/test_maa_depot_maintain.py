import asyncio
import json
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from app.core.config import AppConfig
from app.models.config import MaaConfig
from app.task.MAA.AutoProxy import _build_depot_maintain_task


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
