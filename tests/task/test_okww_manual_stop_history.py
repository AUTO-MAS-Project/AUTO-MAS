import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.config import Config
from app.models.task import LogRecord
from app.task.Okww import AutoProxy as okww_module
from app.task.Okww.AutoProxy import AutoProxyTask


def test_manual_stop_before_log_monitoring_is_saved_as_manual_stop(tmp_path) -> None:
    log_record = LogRecord()
    task = object.__new__(AutoProxyTask)
    task.log_monitor = None
    task.kill_managed_process = AsyncMock()
    task.script_config = SimpleNamespace(get=lambda _group, _key: False)
    task.cur_user_item = SimpleNamespace(
        name="测试用户",
        result="任务被用户手动中止",
        log_record={datetime.now(): log_record},
    )
    task.script_info = SimpleNamespace(name="测试脚本")
    task.run_book = False
    task.cur_user_config = None

    save_log = AsyncMock()
    with (
        patch.object(
            Config,
            "build_history_log_path",
            return_value=tmp_path / "测试.log",
        ),
        patch.object(Config, "save_general_log", new=save_log),
        patch.object(
            Config,
            "merge_statistic_info",
            new=AsyncMock(return_value={}),
        ),
        patch.object(okww_module, "push_notification", new=AsyncMock()),
    ):
        asyncio.run(task.final_task())

    assert log_record.status == "任务被用户手动中止"
    assert log_record.content == ["任务被用户手动中止"]
    assert save_log.await_args.args[1:] == (
        ["任务被用户手动中止"],
        "任务被用户手动中止",
    )
