import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.config import _parse_maa_drop_statistics
from app.models.config import MaaUserConfig
from app.models.task import LogRecord
from app.task.MAA import AutoProxy as maa_module
from app.task.MAA.AutoProxy import AutoProxyTask, _has_completed_sanity_task


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


def test_parse_maa_drop_statistics_supports_english_completion_marker() -> None:
    logs = [
        "Start Task Chain: Fight, Task ID: 2\n",
        "TO-8 掉落统计: \n",
        "龙门币 : 756 (+756)\n",
        "Completed Task Chain: Fight, Task ID: 2\n",
    ]

    assert _parse_maa_drop_statistics(logs) == {"TO-8": {"龙门币": 756}}


def test_parse_maa_drop_statistics_excludes_english_annihilation_fight() -> None:
    logs = [
        "Start Task Chain: Fight, Task ID: 2\n",
        "Annihilation Mode: 1700 / 1700\n",
        "乌萨斯 掉落统计: \n",
        "龙门币 : 140 (+140)\n",
        "Completed Task Chain: Fight, Task ID: 2\n",
    ]

    assert _parse_maa_drop_statistics(logs) == {}


def test_manual_stop_with_completed_sanity_task_is_eligible_for_statistics() -> None:
    records = [
        LogRecord(
            content=["完成任务: 理智作战\n"],
            status="任务被用户手动中止",
        )
    ]

    assert _has_completed_sanity_task(records)


def test_annihilation_completion_does_not_trigger_sanity_statistics() -> None:
    records = [
        LogRecord(
            content=[
                "剿灭模式 : 1700 / 1700\n",
                "Completed Task Chain: Fight, Task ID: 2\n",
            ],
            status="任务被用户手动中止",
        )
    ]

    assert not _has_completed_sanity_task(records)


def test_failed_maa_task_sends_statistics_even_if_six_star_notification_fails(
    tmp_path,
) -> None:
    task = object.__new__(AutoProxyTask)
    task.check_result = "Pass"
    task.maa_log_monitor = SimpleNamespace(stop=AsyncMock())
    task.maa_process_manager = SimpleNamespace(kill=AsyncMock())
    task.maa_tasks_path = tmp_path / "tasks.json"
    task.maa_exe_path = tmp_path / "MAA.exe"
    task.script_config = SimpleNamespace(get=lambda _group, _key: "DoNothing")
    task.cur_user_item = SimpleNamespace(
        name="测试用户",
        result="任务被用户手动中止",
        log_record={
            datetime.now(): LogRecord(
                content=["完成任务: 理智作战\n"],
                status="任务被用户手动中止",
            )
        },
    )
    task.cur_user_uid = "user-id"
    task.script_info = SimpleNamespace(name="测试脚本")
    task.user_start_time = datetime.now()
    task.cur_user_config = SimpleNamespace()
    task.task_info = SimpleNamespace(task_id="task-id")
    task.run_book = {"Annihilation": True, "Routine": False}

    async def save_maa_log(_path, _content, _status):
        return True

    async def merge_statistic_info(_paths):
        return {
            "drop_statistics": {"1-7": {"固源岩": 2}},
            "recruit_statistics": {},
            "sanity": 1,
            "sanity_full_at": "",
        }

    push_mock = AsyncMock(side_effect=[None, RuntimeError("六星通知失败")])

    with (
        patch.object(
            maa_module.Config,
            "build_history_log_path",
            return_value=tmp_path / "测试.log",
        ),
        patch.object(maa_module.Config, "save_maa_log", new=save_maa_log),
        patch.object(
            maa_module.Config,
            "merge_statistic_info",
            new=merge_statistic_info,
        ),
        patch.object(
            maa_module.Config,
            "send_websocket_message",
            new=AsyncMock(),
        ),
        patch.object(maa_module.System, "kill_process", new=AsyncMock()),
        patch.object(maa_module, "agree_bilibili", new=AsyncMock()),
        patch.object(maa_module, "push_notification", new=push_mock),
    ):
        asyncio.run(task.final_task())

    assert [call.args[0] for call in push_mock.await_args_list] == [
        "统计信息",
        "公招六星",
    ]
    assert push_mock.await_args_list[0].args[2]["drop_statistics"] == {
        "1-7": {"固源岩": 2}
    }


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
