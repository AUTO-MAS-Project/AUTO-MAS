"""模拟器恢复耗尽后的真实 MAA 入口与调度状态、持锁收尾。"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.models.config import GeneralConfig, GeneralUserConfig
from app.models.emulator import EmulatorStartupError
from app.models.task import TaskMode
from app.plugin.types import PluginCodeDrift
from app.task.mode_worker import AutoProxyWorker
from app.task.user_expander import UserExpander
from tests.support.maa_runtime import dispatch
from tests.support.maa_runtime import runtime as runtime
from tests.support.scheduler import scheduler as scheduler


@pytest.mark.asyncio
async def test_real_maa_startup_failure_keeps_reason_and_avoids_outer_retry(
    runtime,
):
    runtime.script.Run.RunTimesLimit = 10
    await runtime.script.commit()
    runtime.emulator.open.side_effect = EmulatorStartupError(
        "实例 0 errcode=-503 mainnx connect failed"
    )
    # 通过 dev 的真实插件调度入口验证，不再依赖已删除的旧 MAA 执行器。
    execution = await dispatch(runtime, TaskMode.AUTO_PROXY)
    await asyncio.wait_for(execution.accomplish.wait(), 5)
    runtime.emulator.open.assert_awaited_once()
    user = execution.task_info.script_list[0].user_list[0]
    assert user.status == "异常"
    assert "mainnx connect failed" in user.result
    assert "errcode=-503" in user.result
    assert not runtime.opened
    assert not runtime.script.is_locked and not runtime.user.is_locked
    for name, original in runtime.original.items():
        assert (runtime.install / "config" / name).read_bytes() == original


@pytest.mark.asyncio
async def test_scheduler_releases_locks_reports_error_and_runs_following_script(
    scheduler,
):
    manager, scripts, _, first_id = scheduler
    second_id = scripts.add(GeneralConfig, payload={"Info": {"Name": "正常脚本"}})
    await scripts.commit()
    scripts[second_id].UserData.add(
        GeneralUserConfig, payload={"Info": {"Status": True, "RemainedDay": -1}}
    )
    await scripts[second_id].UserData.commit()
    finalized, following = [], []
    external_open = AsyncMock(
        side_effect=EmulatorStartupError("errcode=-503 mainnx connect failed")
    )

    class Worker(AutoProxyWorker):
        async def main_logic(self):
            if self.script_info.script_id == str(first_id):
                await external_open("0")
            else:
                assert not scripts[first_id].is_locked
                assert not any(u.is_locked for u in scripts[first_id].UserData.values())
                following.append(self.user_info.uid)
                await self.user_info.set_state(status="完成")

        async def finish(self):
            assert self.user_config.is_locked
            finalized.append(self.user_info.uid)

    class Expander(UserExpander):
        def build_worker(self, user, user_config):
            return Worker(self, user, user_config)

    manager.plugin_expander = lambda script, config: Expander(script, config)
    uid = await manager.start(
        TaskMode.AUTO_PROXY,
        {
            0: {
                "uid": "-",
                "children": {
                    0: {"uid": str(first_id)},
                    1: {"uid": str(second_id)},
                },
            }
        },
    )
    run = manager.task_handler[uid]
    await asyncio.wait_for(run.accomplish.wait(), 3)
    assert run.task_info.status == "error"
    assert following and len(finalized) == 3
    assert all(not config.is_locked for config in scripts.values())
    assert all(
        not user.is_locked
        for config in scripts.values()
        for user in config.UserData.values()
    )
    assert not manager.task_handler


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "version,mode,drift,allowed",
    [
        ("0.1.3", TaskMode.AUTO_PROXY, PluginCodeDrift.NORMAL, False),
        ("0.1.4", TaskMode.AUTO_PROXY, PluginCodeDrift.NORMAL, True),
        ("0.1.3", TaskMode.SCRIPT_VIEW, PluginCodeDrift.NORMAL, True),
        pytest.param(
            "0.1.4",
            TaskMode.AUTO_PROXY,
            PluginCodeDrift.NEEDS_RELOAD,
            False,
            id="stale-installed-metadata",
        ),
    ],
)
async def test_maa_runtime_version_guard(
    runtime, monkeypatch, version, mode, drift, allowed
):
    """真实分派在创建 MAA 自动代理前拒绝旧插件，查看模式仍可使用。"""
    from maa_adapter import PLUGIN as MaaPlugin

    from app.core import Config
    from app.core.plugin.manager import _PluginManager
    from app.models.config import PluginRecord, PluginRegistryCollection
    from app.plugin.types import PluginState

    registry = PluginRegistryCollection.build([PluginRecord])
    await registry.activate()
    uid = registry.add(
        PluginRecord,
        payload={
            "info": {
                "plugin_name": "maa_adapter",
                "package_name": "auto-mas-maa-adapter",
                "version": version,
                "source": "installed",
                "state": PluginState.ENABLED,
                "code_drift": drift,
            }
        },
    )
    await registry.commit()
    registry[uid]._plugin_cls = MaaPlugin
    monkeypatch.setattr(Config, "plugin_registry", registry)
    plugins = _PluginManager()
    plugins.script_types[uid] = MaaPlugin.decl
    runtime.manager.plugin_expander = plugins.resolve_script_expander
    runtime.emulator.open.side_effect = EmulatorStartupError("errcode=-503 mainnx")

    execution = await dispatch(runtime, mode)
    await asyncio.wait_for(execution.accomplish.wait(), 5)
    script = execution.task_info.script_list[0]
    if not allowed:
        assert execution.task_info.info.status == "error"
        assert "0.1.4" in script.current.log
        runtime.emulator.open.assert_not_awaited()
        assert not runtime.opened
    elif mode == TaskMode.AUTO_PROXY:
        runtime.emulator.open.assert_awaited_once()
        assert "errcode=-503" in script.user_list[0].result
    else:
        assert execution.task_info.info.status == "success"
        assert runtime.opened
    assert not runtime.script.is_locked and not runtime.user.is_locked
