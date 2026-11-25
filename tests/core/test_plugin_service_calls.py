"""插件之间经服务调用协作时的宿主保证。

专项的运行与收尾（停 worker、关游戏、恢复分辨率、放预约）都经上游插件的服务完成：
退出时停任务期间服务照常可用；停用上游时不打断在跑的调用，也不无限期等它；
提供方在被调用时起作业，靠调用方的进程作用域与停止检查决定能不能起进程。
"""

import asyncio

import pytest
import pytest_asyncio

from app.core.plugin.manager import _PluginManager
from app.models.config import GlobalConfig, PluginRecord, PluginRegistryCollection
from app.plugin.errors import PluginBusyError, PluginPrecheckError
from app.plugin.runtime import loader
from app.plugin.types import PluginState

PROVIDER = '''
import asyncio

from app.plugin.base import BasePlugin
from app.utils.common.process.scope import current_process_scope, current_stop_check


class Provider(BasePlugin):
    provides_services = {
        "probe.job_start": "job_start",
        "probe.ping": "ping",
        "probe.hold": "hold",
    }
    release = None

    async def ping(self):
        return "pong"

    async def hold(self):
        """运行中的长调用（例如等运行池锁的请求），测试放行后才返回。"""
        await type(self).release.wait()
        return "held"

    async def job_start(self):
        """长操作的开始：在本次调用里起作业任务，作业读它看到的进程作用域与停止检查。"""

        async def job():
            await asyncio.sleep(0)
            return current_process_scope.get(), current_stop_check.get()

        self.job = asyncio.create_task(job())
        return {"ok": True}


PLUGIN = Provider
'''

CALLER = '''
from app.plugin.base import BasePlugin
from app.plugin.errors import PluginBusyError
from app.utils.common.process.scope import current_process_scope, current_stop_check


class Caller(BasePlugin):
    requires = ("probe.job_start", "probe.ping")
    provides_services = {"probe.finish": "finish"}
    blockers = []
    probed = []

    async def teardown_blockers(self):
        """有运行没结束时拒绝拆卸；顺手调一次上游，记下预检时上游的调用门开没开。"""
        try:
            await self.services.require("probe.ping")()
            self.probed.append("open")
        except PluginBusyError:
            self.probed.append("closed")
        return list(self.blockers)

    async def finish(self):
        """专项收尾：经上游服务完成。"""
        return await self.services.require("probe.ping")()

    async def run(self, scope, stop_check):
        """专项运行：在自己的任务里设好作用域，再调上游的开始操作。"""
        scope_token = current_process_scope.set(scope)
        check_token = current_stop_check.set(stop_check)
        try:
            return await self.services.require("probe.job_start")()
        finally:
            current_stop_check.reset(check_token)
            current_process_scope.reset(scope_token)


PLUGIN = Caller
'''


@pytest_asyncio.fixture
async def pair(isolated_app_paths, monkeypatch, tmp_path):
    """真实插件管理器加载两个真实插件包：上游提供方、下游调用方；启用调用方会先启用提供方。"""
    from app.core import plugin

    registry = PluginRegistryCollection.build([PluginRecord])
    setting = GlobalConfig.build()
    for root in (registry, setting):
        await root.activate()
    monkeypatch.setattr(isolated_app_paths, "plugin_registry", registry)
    monkeypatch.setattr(isolated_app_paths, "setting", setting)
    manager = _PluginManager()
    monkeypatch.setattr(plugin, "Plugin", manager)
    source = tmp_path / "pkgs"
    records = {}
    for name, code in (("svc_provider", PROVIDER), ("svc_caller", CALLER)):
        package = source / name
        package.mkdir(parents=True)
        (package / "__init__.py").write_text(code, encoding="utf-8")
        uid = registry.add(
            PluginRecord,
            payload={
                "info": {
                    "plugin_name": name,
                    "import_name": name,
                    "source": "local",
                    "package_name": name.replace("_", "-"),
                    "enabled": False,
                }
            },
        )
        await registry.commit()
        record = registry[uid]
        record._project_dir = source
        records[name] = record
        await manager.load(record)
    await manager.enable(records["svc_caller"])
    assert all(r.info.state == PluginState.ENABLED for r in records.values())
    try:
        yield manager, records["svc_provider"], records["svc_caller"]
    finally:
        await manager.shutdown()
        for record in records.values():
            loader.clear(record)


@pytest.mark.asyncio
async def test_services_stay_usable_while_tasks_stop_and_close_after_shutdown(pair):
    """退出：先只封外部入口，停任务期间专项收尾仍能调上游；插件系统收尾之后服务一律被拒。"""
    manager, provider, caller = pair
    finish = manager.services.require("probe.finish")

    manager.seal_entries()
    # 停任务期间：专项收尾经自己的调用门进来，再调上游的服务。
    assert await finish() == "pong"
    assert await caller._plugin.services.require("probe.ping")() == "pong"
    # 外部入口已封：插件 HTTP 网关不再受理，新的生命周期操作被拒。
    assert not manager.http.accepting
    with pytest.raises(PluginBusyError, match="插件系统忙，请稍后重试"):
        await manager.disable(provider)
    assert provider.info.state == PluginState.ENABLED

    # 停完任务后由插件系统收尾封服务注册表和调用门。
    manager._initialized = True  # 等同宿主初始化已走完，走真实的退出收尾分支
    await manager.shutdown()
    with pytest.raises(PluginBusyError):
        caller._plugin.services.require("probe.ping")
    with pytest.raises(PluginBusyError):
        await finish()


async def _start_long_call(manager, provider):
    """从独立任务发起一次过调用门的长调用（运行中的托管在等上游），等它确实进了门。"""
    release = provider._plugin_cls.release = asyncio.Event()
    call = asyncio.create_task(manager.services.require("probe.hold")())
    await asyncio.sleep(0)
    return release, call


@pytest.mark.asyncio
async def test_disabling_provider_under_running_caller_is_rejected_without_pausing(
    pair,
):
    """运行中点停用上游：停用当场被拒，预检时调用门开着，在跑的长调用和新调用都不受打扰。"""
    manager, provider, caller = pair
    caller._plugin_cls.blockers = ["有 1 个运行未结束"]
    caller._plugin_cls.probed = []
    release, call = await _start_long_call(manager, provider)
    try:
        async with asyncio.timeout(5):
            with pytest.raises(PluginPrecheckError) as caught:
                await manager.disable(provider)
        assert caught.value.message == "插件 `svc_caller`：有 1 个运行未结束"
        # 只问了一次，问的时候上游的调用门开着。
        assert caller._plugin_cls.probed == ["open"]
        assert not call.done()
        assert await caller._plugin.services.require("probe.ping")() == "pong"
        assert provider.info.state == caller.info.state == PluginState.ENABLED
    finally:
        release.set()
    assert await call == "held"


@pytest.mark.asyncio
async def test_disable_gives_up_when_inflight_call_outlasts_drain_limit(
    pair, monkeypatch
):
    """在途长调用一直不结束：停用等满上限后以「插件系统忙」拒绝，准入恢复，长调用照常完成。"""
    from app.core.plugin import manager as manager_module

    # 宿主上限是 15 秒，这里缩短；旧宿主没有上限时，下面的 5 秒超时会先到。
    monkeypatch.setattr(manager_module, "_PAUSE_DRAIN_TIMEOUT", 0.3, raising=False)
    manager, provider, caller = pair
    instances = (provider._plugin, caller._plugin)
    release, call = await _start_long_call(manager, provider)
    try:
        async with asyncio.timeout(5):
            with pytest.raises(PluginBusyError) as caught:
                await manager.disable(provider)
        assert caught.value.message == "插件系统忙，请稍后重试"
        assert (provider._plugin, caller._plugin) == instances
        assert provider.info.state == caller.info.state == PluginState.ENABLED
        # 准入已恢复：上下游的服务都能再调。
        assert await caller._plugin.services.require("probe.ping")() == "pong"
        assert await manager.services.require("probe.finish")() == "pong"
        assert not call.done()
    finally:
        release.set()
    assert await call == "held"
    # 长调用结束后再停用，照常级联。
    await manager.disable(provider)
    assert provider.info.state == caller.info.state == PluginState.DISABLED


@pytest.mark.asyncio
async def test_provider_job_sees_caller_process_scope_and_stop_check(pair):
    """调用方设好进程作用域与停止检查后调上游的开始操作，上游在这次调用里起的作业读到同样的值。"""
    _, provider, caller = pair
    scope, stop_check = object(), object()

    async def run_in_task():
        """专项的运行跑在宿主为它建的任务里，和测试本身的上下文分开。"""
        return await caller._plugin.run(scope, stop_check)

    assert await asyncio.create_task(run_in_task()) == {"ok": True}
    assert await provider._plugin.job == (scope, stop_check)
