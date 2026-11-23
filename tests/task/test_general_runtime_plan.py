import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

from app.config import ConfigCollection, config_manager
from app.core.config import universal_plan
from app.models.config import GeneralConfig, UniversalPlanConfig
from app.models.task import TaskMode
from app.task.general import AutoProxy
from app.task.general.manager import GeneralManager
from tests.support.scheduler import create_runtime_tree
from tests.support.scheduler import scheduler as scheduler


@pytest_asyncio.fixture
async def plan(scheduler, isolated_app_paths, monkeypatch):
    _, scripts, _, sid = scheduler
    plans = ConfigCollection.build([UniversalPlanConfig])
    await plans.activate()
    monkeypatch.setitem(config_manager._collections, "PlanConfig", plans)
    monkeypatch.setattr(isolated_app_paths, "PlanConfig", plans)
    pid, plan = await isolated_app_paths.add_plan("UniversalPlan", script_id=str(sid))
    first = next(iter(scripts[sid].UserData.values()))
    first.Info.PlanMode = pid
    first.Info.Base = "native"
    await first.commit()
    return plan


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["File", "Folder"])
async def test_plan_retry_and_next_account_read_their_own_config(
    scheduler, isolated_app_paths, plan, tmp_path, monkeypatch, mode
):
    manager, scripts, _, sid = scheduler
    script = scripts[sid]
    native = tmp_path / "external" / "settings.ini"
    native.parent.mkdir()
    native.write_text("native")
    exe = tmp_path / "script.exe"
    exe.touch()
    log = tmp_path / "script.log"
    script.Script.ScriptPath = exe
    script.Script.ConfigPathMode = mode
    script.Script.ConfigPath = native if mode == "File" else native.parent
    script.Script.LogPath = log
    script.Script.LogPathFormat = ""
    script.Script.LogTimeFormat = "%Y-%m-%d %H:%M:%S.%f"
    script.Script.LogTimeEnd = 26
    script.Script.SuccessLog = "DONE"
    script.Script.ErrorLog = "FAIL"
    script.Script.UpdateConfigMode = "Always"
    script.Run.RunTimesLimit = 2
    await script.commit()

    data = isolated_app_paths.data_path / str(sid)
    first, second = script.UserData.keys()
    fixed = data / str(first) / "ConfigFile" / native.name
    fixed.parent.mkdir(parents=True)
    fixed.write_text("first fixed")
    template = data / "Plans" / str(plan.uid) / "Monday" / "ConfigFile" / native.name
    template.parent.mkdir(parents=True)
    template.write_text("Monday")
    clock = Mock()
    clock.now.return_value = datetime(2026, 11, 3, 3, 59)
    monkeypatch.setattr(universal_plan, "datetime", clock)
    observed = []

    async def launch(*args, **kwargs):
        observed.append(native.read_text())
        native.write_text(f"{observed[-1]} edited")
        clock.now.return_value = datetime(2026, 11, 3, 4, 1)
        lines = ["FAIL"] if len(observed) == 1 else ["running", "DONE"]
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        log.write_text("".join(f"{stamp} {line}\n" for line in lines))

    monkeypatch.chdir(isolated_app_paths.data_path)
    monkeypatch.setattr(AutoProxy.ProcessManager, "open_process", launch)
    monkeypatch.setattr(AutoProxy.process, "kill_process", AsyncMock())
    monkeypatch.setattr(AutoProxy, "Notify", AsyncMock())
    monkeypatch.setattr("app.task.general.manager.Notify", AsyncMock())
    sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda delay: sleep(min(delay, 0.01)))
    monkeypatch.setattr(manager, "manager_factories", {GeneralConfig: GeneralManager})
    uid = await manager.start(
        TaskMode.AUTO_PROXY, {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}}
    )
    run = manager.task_handler[uid]
    await asyncio.wait_for(run.accomplish.wait(), timeout=10)

    assert observed == ["Monday", "Monday", "native"]
    assert native.read_text() == "native"
    assert template.read_text() == "Monday"
    assert fixed.read_text() == "first fixed"
    assert (
        data / str(second) / "ConfigFile" / native.name
    ).read_text() == "native edited"


@pytest.mark.asyncio
async def test_missing_plan_day_explains_skip_in_account_report(
    scheduler, plan, tmp_path
):
    _, scripts, _, sid = scheduler
    script = scripts[sid]
    first = next(iter(script.UserData.values()))
    script.Script.ConfigPath = tmp_path / "settings.ini"
    await script.commit()
    root, info, user = await create_runtime_tree(
        script_id=str(sid), user_id=str(first.uid)
    )
    await info.set_current_index(0)
    await AutoProxy.AutoProxyTask(info, script, script.UserData, None).execution.run()
    assert user.status == "跳过"
    assert "计划表尚未配置" in user.result
    assert first.Data.ProxyTimes == 0
