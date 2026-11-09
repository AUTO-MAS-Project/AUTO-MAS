"""任务结果由运行树虚拟字段动态聚合，不依赖完成时生成的文本副本。"""

from datetime import datetime, timezone

import pytest

from app.models.schema import TaskTreeData
from app.models.task import LogRecord, TaskItem, TaskUserItem
from tests.runtime_support import create_runtime_tree


@pytest.mark.asyncio
async def test_result_follows_committed_logs_and_user_status_without_cache():
    root, script, user = await create_runtime_tree()
    at = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
    record = await user.add_log_record(at, LogRecord(status="运行中"))
    initial = root.info.result
    assert "Script" in initial and "运行中" in initial
    assert "未完成用户数：1" in initial

    await record.set_state(status="最终结果")
    await user.set_state(status="完成")
    current = root.info.result
    assert "最终结果" in current and "运行中" not in current
    assert "已完成用户数：1；未完成用户数：0" in current
    assert (
        current
        == TaskTreeData.model_validate(root.model_dump()).model_dump()["info"]["result"]
    )

    assert root.info.result == current
    document = TaskTreeData.model_validate(root.model_dump()).model_dump(mode="json")
    script_document = document["scripts"]["data"][str(script.uid)]
    user_document = script_document["users"]["data"][str(user.uid)]
    assert not (
        {"locked", "maintenance_skipped", "push_log", "push_log_mode"}
        & user_document["info"].keys()
    )
    assert "progress" not in user_document["info"]
    assert "current" not in user_document


@pytest.mark.asyncio
async def test_skipped_user_and_empty_collections_use_dynamic_results():
    empty = TaskItem()
    await empty.activate()
    assert empty.info.result == "任务未加载"

    root, script, user = await create_runtime_tree()
    await user.set_state(status="跳过")
    await user.add_log_record(datetime.now().astimezone(), LogRecord(status="维护跳过"))
    assert "维护跳过" in root.info.result
    assert "未完成用户数：1" in root.info.result

    uid = script.users.add(TaskUserItem, payload={"info": {"name": "待执行用户"}})
    await script.users.commit()
    assert "未完成用户数：2" in root.info.result
    assert "待执行用户" in root.info.result
    script.users.remove(uid)
    script.users.remove(user.uid)
    await script.users.commit()
    assert script.info.result == "用户未加载"
    assert "用户未加载" in root.info.result
