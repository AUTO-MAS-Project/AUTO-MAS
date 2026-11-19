"""通用脚本自动代理必须执行所选日期模板，并保留原生与账号固定配置。"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

from app.config import ConfigCollection, config_manager
from app.core.config import universal_plan
from app.models.config import UniversalPlanConfig
from app.task.general.AutoProxy import AutoProxyTask
from app.task.general.manager import GeneralManager
from tests.support.scheduler import create_runtime_tree
from tests.support.scheduler import scheduler as scheduler


@pytest_asyncio.fixture
async def account(scheduler, isolated_app_paths, tmp_path, monkeypatch):
    config = isolated_app_paths
    _, scripts, _, sid = scheduler
    script = scripts[sid]
    uid, user = next(iter(script.UserData.items()))
    runtime = tmp_path / "mas"
    runtime.mkdir()
    monkeypatch.chdir(runtime)
    native = tmp_path / "external" / "settings.ini"
    native.parent.mkdir()
    native.write_text("native")
    executable = tmp_path / "script.exe"
    executable.touch()
    script.Script.ScriptPath = executable
    script.Script.ConfigPath = native
    script.Script.LogPath = tmp_path / "script.log"
    script.Script.UpdateConfigMode = "Always"
    await script.commit()
    plans = ConfigCollection.build([UniversalPlanConfig])
    await plans.activate()
    monkeypatch.setitem(config_manager._collections, "PlanConfig", plans)
    monkeypatch.setattr(config, "PlanConfig", plans)
    pid, plan = await config.add_plan("UniversalPlan", script_id=str(sid))
    user.Info.PlanMode = pid
    user.Info.Base = "native"
    await user.commit()
    task, info, _ = await create_runtime_tree(script_id=str(sid), user_id=str(uid))
    await info.set_current_index(0)
    clock = Mock(wraps=datetime)
    clock.now.return_value = datetime(2026, 11, 3, 3, 59)
    monkeypatch.setattr(universal_plan, "datetime", clock)
    monkeypatch.setattr("app.task.general.AutoProxy.process.kill_process", AsyncMock())
    monkeypatch.setattr(
        "app.task.general.manager.Notify.push_proxy_result", AsyncMock()
    )
    return GeneralManager(info), script, user, plan, native, clock


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["File", "Folder"])
async def test_plan_run_keeps_its_day_and_restores_native(
    account, isolated_app_paths, monkeypatch, mode
):
    manager, script, user, plan, native, clock = account
    script.Script.ConfigPathMode = mode
    script.Script.ConfigPath = native if mode == "File" else native.parent
    await script.commit()
    script_root = isolated_app_paths.data_path / str(script.uid)
    day = script_root / "Plans" / str(plan.uid) / "Monday"
    template = day / "ConfigFile" / native.name
    fixed = script_root / str(user.uid) / "ConfigFile" / native.name
    runtime = day / "Users" / str(user.uid) / "ConfigFile" / native.name
    for path, text in ((template, "Monday"), (fixed, "fixed"), (runtime, "old run")):
        path.parent.mkdir(parents=True)
        path.write_text(text)

    observed = []

    async def run_config_phases(_user, proxy):
        assert await proxy.check() == "Pass"
        clock.now.return_value = datetime(2026, 11, 3, 4, 1)
        await proxy.prepare()
        for attempt in range(2):
            await proxy.set_general()
            observed.append((native.read_text(), plan.is_locked))
            native.write_text(f"script result {attempt}")
            await proxy.update_config()

    monkeypatch.setattr(manager, "run_user_task", run_config_phases)
    try:
        await manager.main_task()
    finally:
        await manager.final_task()

    assert observed == [("Monday", True), ("Monday", True)]
    assert [p.read_text() for p in (native, fixed, template, runtime)] == [
        "native",
        "fixed",
        "Monday",
        "Monday",
    ]
    assert not plan.is_locked


@pytest.mark.asyncio
async def test_missing_plan_day_skips_with_reason_in_report(account):
    manager, script, user, _, native, _ = account
    run = AutoProxyTask(manager.script_info, script, script.UserData, None)
    reason = await run.check()
    assert reason != "Pass"
    await run.main_task()
    item = manager.script_info.user_list[0]
    assert item.status == "跳过" and reason in item.result
    assert reason in manager.script_info.log
    assert user.Data.ProxyTimes == 0 and native.read_text() == "native"
