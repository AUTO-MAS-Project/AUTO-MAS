"""MAA 日常失败后可恢复或耗尽重试次数，剿灭明确失败停止重试。"""

import importlib
import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import ConfigCollection
from app.core.task_manager.manager import TaskInfo
from app.models.config import MaaConfig, MaaUserConfig
from app.models.emulator import DeviceInfo, DeviceStatus
from app.models.task import ScriptItem, UserItem
from app.task.MAA.AutoProxy import AutoProxyTask
from app.task.MAA.constants import MAA_TASKS
from tests.config_support import activate_config


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("annihilation", "quick_config", "recover", "expected_modes"),
    [
        (False, True, True, ["Routine", "Routine"]),
        (False, True, False, ["Routine"] * 3),
        (True, True, True, ["Annihilation", "Routine"]),
        (False, False, True, ["Routine", "Routine"]),
    ],
    ids=[
        "daily-recovery",
        "daily-limit",
        "annihilation-stops",
        "source-queue-recovery",
    ],
)
async def test_task_failure_retry_scope(
    monkeypatch,
    isolated_app_paths,
    annihilation,
    quick_config,
    recover,
    expected_modes,
):
    module = importlib.import_module("app.task.MAA.AutoProxy")
    root = isolated_app_paths.work_path / "maa"
    root.mkdir()
    config = await activate_config(MaaConfig(Info={"Path": root}))
    users = ConfigCollection.build([MaaUserConfig])
    await users.activate()
    uid = users.add(
        MaaUserConfig,
        payload={
            "Info": {"IfQuickConfig": quick_config},
            "Task": {
                **{f"If{task}": False for task in MAA_TASKS},
                "IfStartUp": True,
                "IfInfrast": True,
                "IfRecruit": True,
                "Annihilation": "Annihilation" if annihilation else "Close",
                "AnnihilationStartWeekday": "Monday",
            },
        },
    )
    await users.commit()
    user = UserItem(str(uid), "test", "等待")
    script = ScriptItem(
        str(uuid.uuid4()), "MAA", "运行", user_list=[user], current_index=0
    )
    task_info = TaskInfo("AutoProxy", "test", "queue", None, None)
    monkeypatch.setattr(task_info, "schedule_on_change", lambda: None)
    task_info.script_list = [script]
    emulator = SimpleNamespace(
        open=AsyncMock(return_value=DeviceInfo("test", DeviceStatus.ONLINE, "")),
        close=AsyncMock(return_value=True),
    )
    proxy = AutoProxyTask(script, config, users, emulator, capture_adb=AsyncMock())
    attempts = []

    async def open_process(*args, **kwargs):
        attempts.append((proxy.mode, dict(proxy.task_dict)))

    process = SimpleNamespace(
        open_process=open_process,
        kill=AsyncMock(),
        is_running=AsyncMock(return_value=True),
        main_pid=1,
    )

    class LogMonitor:
        def __init__(self, time_stamp_range, time_stamp_format, callback, **kwargs):
            self.callback = callback

        async def start_monitor_file(self, *args, **kwargs):
            succeeded = recover and (
                proxy.mode == "Routine" and (annihilation or len(attempts) > 1)
            )
            if succeeded:
                log = (
                    "完成任务: 开始唤醒\n完成任务: 基建换班\n"
                    "完成任务: 自动公招\n任务已全部完成！"
                )
            else:
                failed_task = "理智作战" if proxy.mode == "Annihilation" else "基建换班"
                completed = "完成任务: 自动公招\n" if proxy.mode == "Routine" else ""
                log = (
                    f"完成任务: 开始唤醒\n任务出错: {failed_task}\n"
                    f"{completed}任务已结束，以下任务出现错误: {failed_task}"
                )
            await self.callback([log], datetime.now().astimezone())

        async def stop(self):
            pass

    monkeypatch.setattr(module, "ProcessManager", lambda: process)
    monkeypatch.setattr(module, "LogMonitor", LogMonitor)
    # 隔离 MAA 配置下发、进程/截图和通知边界，保留真实初始化、日志判定与重试循环。
    monkeypatch.setattr(proxy, "set_maa", AsyncMock())
    monkeypatch.setattr(proxy, "_take_failure_shot", AsyncMock(return_value=None))
    monkeypatch.setattr(module.System, "kill_process", AsyncMock())
    monkeypatch.setattr(module.Notify, "send_notice", AsyncMock())
    monkeypatch.setattr(module.Publisher, "send", AsyncMock())

    await proxy.main_task()

    assert [mode for mode, _ in attempts] == expected_modes
    assert proxy.run_book["Annihilation"] is (not annihilation)
    assert proxy.run_book["Routine"] is recover
    records = [record for _, record in user.iter_history_logs()]
    assert len(records) == len(expected_modes)
    assert records[0].status == "MAA 部分任务执行失败"
    assert records[-1].status == ("Success!" if recover else "MAA 部分任务执行失败")
    if quick_config and not annihilation:
        assert attempts[0][1]["Recruit"] is True
        assert attempts[1][1]["Recruit"] is False
        assert attempts[1][1]["Infrast"] is True
