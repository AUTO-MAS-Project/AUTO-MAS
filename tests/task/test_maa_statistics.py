import asyncio

from app.core.config import _parse_maa_drop_statistics
from app.models.config import MaaUserConfig


def test_parse_maa_drop_statistics_includes_activity_and_depot_fights() -> None:
    logs = [
        "完成任务: 开始唤醒\n",
        "Start Task Chain: Fight, Task ID: 2\n",
        "TO-8 掉落统计: \n",
        "龙门币 : 756 (+756)\n",
        "沿途的点滴 : 63 (+63)\n",
        "完成任务: 理智作战\n理智: 12/180\n",
        "Completed Task Chain: Fight, Task ID: 2\n",
        "Start Task Chain: Fight, Task ID: 4\n",
        "PR-A-1 掉落统计: \n",
        "固源岩 : 2 (+2)\n",
        "完成任务: 库存保持\n",
        "Completed Task Chain: Fight, Task ID: 4\n",
        "Start Task Chain: Fight, Task ID: 5\n",
        "TO-8 掉落统计: \n",
        "龙门币 : 1512 (+1512)\n",
        "沿途的点滴 : 126 (+126)\n",
        "完成任务: 活动关优先\n理智: 0/180\n",
        "Completed Task Chain: Fight, Task ID: 5\n",
    ]

    assert _parse_maa_drop_statistics(logs) == {
        "TO-8": {"龙门币": 2268, "沿途的点滴": 189},
        "PR-A-1": {"固源岩": 2},
    }


def test_parse_maa_drop_statistics_uses_last_drop_snapshot_without_start_marker() -> None:
    logs = [
        "完成任务: 开始唤醒\n",
        "TO-8 掉落统计: \n",
        "龙门币 : 756 (+756)\n",
        "TO-8 掉落统计: \n",
        "龙门币 : 1512 (+1512)\n",
        "完成任务: 活动关优先\n",
    ]

    assert _parse_maa_drop_statistics(logs) == {"TO-8": {"龙门币": 1512}}


def test_activity_medicine_uses_legacy_medicine_for_existing_users() -> None:
    config = MaaUserConfig()

    asyncio.run(config.load({"Info": {"MedicineNumb": 5}}))

    assert config.get("Task", "ActivityMedicineNumb") == 5


def test_activity_medicine_can_override_legacy_medicine() -> None:
    config = MaaUserConfig()

    asyncio.run(
        config.load(
            {
                "Info": {"MedicineNumb": 5},
                "Task": {"ActivityMedicineNumb": 0},
            }
        )
    )

    assert config.get("Task", "ActivityMedicineNumb") == 0
