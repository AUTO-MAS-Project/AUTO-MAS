"""插件级联重载恢复状态，卸载等待全部下游的在途调用结束。"""

import asyncio
import json
from types import SimpleNamespace

import pytest
import pytest_asyncio

from app.core import Notify
from app.core.background_tasks import BackgroundTaskRegistry
from app.core.log_flow.declaration import SimpleFlowDeclaration
from app.core.log_flow.push import SubmitResult
from app.core.log_flow.simple import open_custom_flow
from app.core.notify import tasks as notification_tasks
from app.core.notify.rendering import AsyncNotificationRenderer
from app.core.plugin.manager import _PluginManager
from app.models.config import GlobalConfig, PluginRecord, PluginRegistryCollection
from app.models.notification.channel import ChannelTarget, DeliveryChannel, NotifyTarget
from app.models.notification.report import TaskReportPolicy, TaskResultReport
from app.models.task import TaskUserItem
from app.plugin.errors import PluginBusyError
from app.plugin.runtime import loader
from app.plugin.types import PluginState
from tests.support.scheduler import create_runtime_tree


@pytest_asyncio.fixture
async def cascade_plugins(isolated_app_paths, monkeypatch, tmp_path):
    """从临时插件包加载真实生命周期，隔离配置和插件背景任务的归属。"""
    registry = PluginRegistryCollection.build([PluginRecord])
    setting = GlobalConfig.build()
    await registry.activate()
    await setting.activate()
    monkeypatch.setattr(isolated_app_paths, "plugin_registry", registry)
    monkeypatch.setattr(isolated_app_paths, "setting", setting)
    manager = _PluginManager()
    records = {}

    async def load(dependencies, *, source="local", adapters=()):
        """按给定服务依赖建立普通插件包，每个包记录自己的业务启停次数。"""
        for name, requires in dependencies.items():
            package = tmp_path / name
            package.mkdir()
            header = "from app.plugin.base import BasePlugin\n"
            declaration = ""
            if name in adapters:
                header = (
                    "from app.config import ConfigCollection, collection\n"
                    "from app.models.config import ScriptEntry, UserEntry\n"
                    "from app.models.task import TaskMode\n"
                    "from app.task.user_expander import UserExpander\n"
                    "from app.plugin.base.script import ScriptAdapterPlugin as BasePlugin, ScriptTypeDecl\n"
                    "class ProbeUser(UserEntry): pass\n"
                    "class ProbeExpander(UserExpander): pass\n"
                    "class ProbeScript(ScriptEntry):\n"
                    "    users: ConfigCollection[ProbeUser] = collection(ProbeUser)\n"
                )
                declaration = (
                    "    script_type_key = 'probe'\n"
                    "    decl = ScriptTypeDecl(script_type=ProbeScript, user_type=ProbeUser, expander_class=ProbeExpander, supported_modes=(TaskMode.AUTO_PROXY,))\n"
                )
            (package / "__init__.py").write_text(
                header
                + "class Adapter(BasePlugin):\n"
                + declaration
                + f"    requires = {tuple(requires)!r}\n"
                f"    provides_services = {{{name!r}: 'value', '{name}.sync': 'sync_value'}}\n"
                "    events = []\n"
                "    fail_enable = False\n"
                "    async def value(self, *, started=None, release=None, disable_self=False):\n"
                '        """可等待放行或发起自禁用，返回实例以核对调用和资源释放的先后。"""\n'
                "        if started is not None:\n"
                "            started.set()\n"
                "            await release.wait()\n"
                "            self.events.append('call-finished')\n"
                "        if disable_self:\n"
                "            from app.core.plugin import Plugin\n"
                "            await Plugin.disable(self.record)\n"
                "        return self\n"
                "    async def on_enable(self):\n"
                '        """记录启用并按插件故障开关注入业务失败。"""\n'
                "        self.events.append('enable')\n"
                "        if self.fail_enable: raise RuntimeError('plugin enable failed')\n"
                "    def sync_value(self):\n"
                '        """通过标准线程回调发起本插件禁用，验证真实线程往返的调用归属。"""\n'
                "        from asyncio import timeout\n"
                "        from anyio import from_thread\n"
                "        from app.core.plugin import Plugin\n"
                "        async def disable():\n"
                '            """给测试回调设置期限，归属回归时也能退出真实工作线程。"""\n'
                "            async with timeout(2):\n"
                "                await Plugin.disable(self.record)\n"
                "        from_thread.run(disable)\n"
                "        return {'disabled': self.record.info.state == 'disabled'}\n"
                "    async def on_disable(self):\n"
                '        """记录资源禁用，供核对共享依赖不会重复启停。"""\n'
                "        self.events.append('disable')\n"
                "PLUGIN = Adapter\n",
                encoding="utf-8",
            )
            uid = registry.add(
                PluginRecord,
                payload={
                    "info": {
                        "plugin_name": name,
                        "import_name": name,
                        "source": source,
                        "enabled": False,
                    }
                },
            )
            await registry.commit()
            record = registry[uid]
            record._project_dir = tmp_path
            records[name] = record
            await manager.load(record)
        return manager, records

    try:
        yield load
    finally:
        await manager.shutdown()
        for record in records.values():
            if record._project_dir is not None:
                loader.clear(record)


@pytest.mark.asyncio
async def test_reload_restores_complete_tree_without_enabling_inactive_descendants(
    cascade_plugins,
):
    """A→B→C 重载恢复全部服务，原本禁用的 B 下游不会被混入恢复树。"""
    manager, records = await cascade_plugins(
        {
            "cascade_a": (),
            "cascade_b": ("cascade_a",),
            "cascade_c": ("cascade_b",),
            "cascade_inactive": ("cascade_b",),
        }
    )
    await manager.enable(records["cascade_c"])
    previous = records["cascade_c"]._plugin
    result = await manager.reload(records["cascade_a"])
    expected = {"cascade_b": {"cascade_c": {}}}
    assert result["tear"] == expected
    assert result["restore"] == expected
    for name in ("cascade_a", "cascade_b", "cascade_c"):
        assert records[name].info.state == PluginState.ENABLED
        assert records[name].info.enabled
        assert await manager.services.require(name)() is records[name]._plugin
    assert records["cascade_c"]._plugin is not previous
    assert records["cascade_inactive"].info.state == PluginState.DISABLED
    assert not records["cascade_inactive"].info.enabled
    assert records["cascade_inactive"]._plugin_cls.events == []


@pytest.mark.asyncio
async def test_plugin_declaration_loads_its_own_worker_factory_after_reload(
    cascade_plugins, tmp_path
):
    manager, records = await cascade_plugins({"flow_declared": ()})
    record = records["flow_declared"]
    entry = tmp_path / "flow_declared" / "__init__.py"

    def write_plugin(prefix):
        entry.write_text(
            "from auto_mas_core.log_flow import FunctionRef, PluginFlowDeclaration, SimpleFlowDeclaration, Source, TextProcessor, TextRecord, WorkerFactorySpec\n"
            "from app.plugin.base import BasePlugin\n"
            "class Processor:\n"
            "    def process(self, line):\n"
            f"        yield '普通', {prefix!r} + line\n"
            "    def close(self): return ()\n"
            "def processor(options) -> TextProcessor: return Processor()\n"
            "class SampleSource:\n"
            "    def open(self): pass\n"
            "    def poll(self): return ()\n"
            "    def close(self): return (TextRecord(text='source tail'),)\n"
            "def source(options) -> Source: return SampleSource()\n"
            "class Adapter(BasePlugin):\n"
            "    log_flows = {'declared': PluginFlowDeclaration(\n"
            "        use_mas_log=False, accept_push=True,\n"
            "        rules=SimpleFlowDeclaration(processor=WorkerFactorySpec(factory=FunctionRef(name='declared:processor', module=__name__, attribute='processor'))),\n"
            "        source=WorkerFactorySpec(factory=FunctionRef(name='declared:source', module=__name__, attribute='source')),\n"
            "    )}\n"
            "PLUGIN = Adapter\n",
            encoding="utf-8",
        )

    async def collect():
        reports = []
        async with manager.open_log_flow(
            record._plugin,
            "declared",
            run=TaskUserItem(user_id="same"),
            mode="逐条",
            receive_report=reports.append,
        ) as flow:
            assert flow.reporter is not None
            assert flow.reporter.text("event") == SubmitResult.ACCEPTED
        return reports

    write_plugin("before:")
    await manager.reload(record)
    await manager.enable(record)
    assert await collect() == [["before:event", "before:source tail"]]
    write_plugin("after!:")
    await manager.reload(record)
    assert await collect() == [["after!:event", "after!:source tail"]]


@pytest.mark.asyncio
async def test_named_general_flow_uses_current_webui_rules(
    cascade_plugins, tmp_path, monkeypatch
):
    from auto_mas_core.log_flow import GeneralFlowDeclaration, open_log_flow

    from app import core

    manager, records = await cascade_plugins({"flow_webui": ()})
    monkeypatch.setattr(core, "Plugin", manager)
    record = records["flow_webui"]
    (tmp_path / "flow_webui" / "__init__.py").write_text(
        "from auto_mas_core import BasePlugin\n"
        "from auto_mas_core.log_flow import GeneralFlowDeclaration, PluginFlowDeclaration\n"
        "class Adapter(BasePlugin):\n"
        "    log_flows = {'webui': PluginFlowDeclaration(use_mas_log=False, accept_push=True, rules=GeneralFlowDeclaration(patterns='[]'))}\n"
        "PLUGIN = Adapter\n",
        encoding="utf-8",
    )
    await manager.reload(record)
    await manager.enable(record)
    patterns = json.dumps(
        [
            {"type": "regex", "match": ".+", "extract": '"停用"', "enabled": False},
            {"type": "regex", "match": "redacted", "extract": r"$(token=(\w+))"},
            {"type": "split", "match": "redacted"},
        ]
    )
    for replacement in ("first", "second"):
        rules = GeneralFlowDeclaration(
            patterns=patterns,
            hooks=json.dumps(
                [
                    {"type": "drop", "match": "^noise"},
                    {
                        "type": "replace",
                        "match": r"token=\w+",
                        "replace": f"token={replacement}",
                    },
                ]
            ),
        )
        async with open_log_flow(
            record._plugin, "webui", run=TaskUserItem(), general_rules=rules
        ) as flow:
            assert flow.reporter is not None
            assert (
                flow.reporter.text("noise redacted token=discarded")
                == SubmitResult.ACCEPTED
            )
            assert flow.reporter.text("redacted token=secret") == SubmitResult.ACCEPTED
        page = flow.read_nodes()
        assert page.close_reason == "complete"
        assert [node.text for node in page.nodes] == [replacement]


@pytest.mark.asyncio
async def test_declared_log_flow_delivers_one_task_report_via_notify(
    cascade_plugins, tmp_path, monkeypatch
):
    from auto_mas_core.log_flow import LogFlowTaskReport, open_log_flow

    from app import core

    manager, records = await cascade_plugins({"flow_notify": ()})
    monkeypatch.setattr(core, "Plugin", manager)
    record = records["flow_notify"]
    (tmp_path / "flow_notify" / "__init__.py").write_text(
        "from auto_mas_core.log_flow import FunctionRef, PluginFlowDeclaration, SimpleFlowDeclaration\n"
        "from app.plugin.base import BasePlugin\n"
        "from time import sleep\n"
        "def slow_report(entries): sleep(60)\n"
        "class Adapter(BasePlugin):\n"
        "    log_flows = {\n"
        "        'normal': PluginFlowDeclaration(use_mas_log=False, accept_push=True),\n"
        "        'slow': PluginFlowDeclaration(use_mas_log=False, accept_push=True, rules=SimpleFlowDeclaration(postprocess=FunctionRef(name='spec:slow', module=__name__, attribute='slow_report'))),\n"
        "    }\n"
        "PLUGIN = Adapter\n",
        encoding="utf-8",
    )
    await manager.reload(record)
    await manager.enable(record)
    task, script, first = await create_runtime_tree()
    second_uid = script.users.add(
        TaskUserItem, payload={"info": {"user_id": "second", "name": "Second"}}
    )
    muted_uid = script.users.add(
        TaskUserItem, payload={"info": {"user_id": "muted", "name": "Muted"}}
    )
    await script.users.commit()
    second, muted = script.users[second_uid], script.users[muted_uid]
    report = LogFlowTaskReport(script)
    delivered = []

    async def send_channel(*, channel, target, rendered):
        delivered.append((target.id, rendered.content))

    renderer = AsyncNotificationRenderer()
    tasks = notification_tasks.NotificationTasks()
    monkeypatch.setattr(
        notification_tasks, "BackgroundTaskManager", BackgroundTaskRegistry()
    )
    monkeypatch.setattr(Notify, "tasks", tasks)
    monkeypatch.setitem(Notify.__dict__, "_renderer", renderer)
    monkeypatch.setitem(
        Notify.__dict__, "_transport", SimpleNamespace(send_channel=send_channel)
    )
    monkeypatch.setattr(
        Notify,
        "read_task_report_policy",
        lambda: TaskReportPolicy("任何时刻", community_enabled=False, wait_seconds=0),
    )
    monkeypatch.setattr(
        Notify,
        "global_target",
        lambda **_: NotifyTarget(
            channels=(
                (DeliveryChannel("probe", None), ChannelTarget("probe", "Probe")),
            )
        ),
    )
    try:
        with Notify.task_notification_batch(task_id=task.task_id):
            for run, key, mode, text in [
                (first, "normal", "逐条", "first step"),
                (second, "slow", None, "second step"),
                (muted, "slow", "关闭", "muted step"),
            ]:
                async with open_log_flow(
                    record._plugin, key, run=run, mode=mode, task_report=report
                ) as flow:
                    assert flow.reporter is not None
                    assert flow.reporter.node("普通", text) == SubmitResult.ACCEPTED
            assert second.node_observation.read().close_reason == "timeout"
            assert muted.node_observation.read().close_reason == "complete"
            assert report.details_for(muted) == []
            result = TaskResultReport("10:00", "10:01", 3, 0, "用户任务已完成")
            assert (await report.send(title="任务报告", report=result)).queued
            duplicate = await LogFlowTaskReport(script).send(
                title="重复报告", report=result
            )
            assert not duplicate.queued and duplicate.attempted == 0
            assert delivered == []
        assert await tasks.drain_notifications(timeout=3)
        [(target, content)] = delivered
        assert target == "probe"
        assert "未完成数: 0" in content
        assert (
            "用户任务已完成\n\n【User】\nfirst step\n\n【Second】\nsecond step\n⚠️ 节点采集不完整"
            in content
        )
        assert "muted step" not in content
    finally:
        await tasks.close()
        renderer.close()


@pytest.mark.asyncio
async def test_reload_and_disable_revoke_log_flow_of_the_previous_instance(
    cascade_plugins,
):
    manager, records = await cascade_plugins({"flow_example": ()})
    record = records["flow_example"]
    await manager.enable(record)
    previous = await manager.services.require("flow_example")()
    owner = manager.log_flow_owner(previous)
    reports = []
    async with open_custom_flow(
        SimpleFlowDeclaration(),
        run=TaskUserItem(user_id="same"),
        mode="关闭",
        receive_report=reports.append,
        accept_push=True,
        owner=owner,
    ) as flow:
        assert flow.reporter is not None
        assert flow.reporter.node("普通", "before reload") == SubmitResult.ACCEPTED
        await manager.reload(record)
        assert flow.reporter.node("普通", "late") == SubmitResult.CLOSED
        assert flow.read_nodes().close_reason == "complete"
        assert [node.text for node in flow.read_nodes().nodes] == ["before reload"]
        with pytest.raises(PluginBusyError):
            manager.log_flow_owner(previous)
        with pytest.raises(PluginBusyError):
            async with open_custom_flow(
                SimpleFlowDeclaration(),
                run=TaskUserItem(user_id="same"),
                mode="关闭",
                receive_report=reports.append,
                accept_push=True,
                owner=owner,
            ):
                pytest.fail("旧实例不应开启新会话")

    current = await manager.services.require("flow_example")()
    assert current is not previous
    async with open_custom_flow(
        SimpleFlowDeclaration(),
        run=TaskUserItem(user_id="same"),
        mode="关闭",
        receive_report=reports.append,
        accept_push=True,
        owner=manager.log_flow_owner(current),
    ) as next_flow:
        assert next_flow.reporter is not None
        assert flow.reporter.node("普通", "wrong generation") == SubmitResult.CLOSED
        assert next_flow.reporter.node("普通", "after reload") == SubmitResult.ACCEPTED
        await manager.disable(record)
        assert next_flow.reporter.node("普通", "after disable") == SubmitResult.CLOSED
        assert next_flow.read_nodes().close_reason == "complete"
        assert [node.text for node in next_flow.read_nodes().nodes] == ["after reload"]


@pytest.mark.asyncio
async def test_reload_shared_descendant_is_disabled_and_restored_once(cascade_plugins):
    """菱形依赖只记录实际拆卸路径，正常启用仍能先恢复尚未轮到的上游。"""
    manager, records = await cascade_plugins(
        {
            "cascade_a": (),
            "cascade_b": ("cascade_a",),
            "cascade_d": ("cascade_a",),
            "cascade_c": ("cascade_b", "cascade_d"),
        }
    )
    await manager.enable(records["cascade_c"])
    result = await manager.reload(records["cascade_a"])
    expected = {"cascade_b": {"cascade_c": {}}, "cascade_d": {}}
    assert result["tear"] == expected
    assert result["restore"] == expected
    for name in ("cascade_b", "cascade_c", "cascade_d"):
        assert records[name].info.state == PluginState.ENABLED
        assert records[name]._plugin_cls.events == ["enable", "disable", "enable"]
        assert await manager.services.require(name)() is records[name]._plugin


@pytest.mark.asyncio
async def test_reload_restore_failure_skips_branch_and_continues_other_branches(
    cascade_plugins,
):
    """恢复失败保留故障记录，不通过其子节点重试失败分支，其他分支继续恢复。"""
    manager, records = await cascade_plugins(
        {
            "cascade_a": (),
            "cascade_b": ("cascade_a",),
            "cascade_c": ("cascade_b",),
            "cascade_d": ("cascade_a",),
        }
    )
    await manager.enable(records["cascade_c"])
    await manager.enable(records["cascade_d"])
    records["cascade_b"]._plugin_cls.fail_enable = True
    result = await manager.reload(records["cascade_a"])
    assert result["tear"] == {"cascade_b": {"cascade_c": {}}, "cascade_d": {}}
    assert result["restore"] == {"cascade_d": {}}
    assert records["cascade_a"].info.state == PluginState.ENABLED
    assert records["cascade_b"].info.state == PluginState.FAULT_RUNTIME
    assert not records["cascade_b"].info.enabled
    assert records["cascade_b"].info.last_error
    assert records["cascade_b"]._plugin_cls.events.count("enable") == 2
    assert records["cascade_c"].info.state == PluginState.DISABLED
    assert not records["cascade_c"].info.enabled
    assert records["cascade_c"]._plugin_cls.events.count("enable") == 1
    assert records["cascade_d"].info.state == PluginState.ENABLED
    assert await manager.services.require("cascade_d")() is records["cascade_d"]._plugin


@pytest.mark.asyncio
async def test_uninstall_waits_for_indirect_downstream_call_before_releasing_resources(
    cascade_plugins, monkeypatch, isolated_app_paths
):
    """卸载 A 时先停止 A→B→C 全部准入，C 的旧调用结束后才释放级联资源并卸包。"""
    from app.plugin.uv import ops

    manager, records = await cascade_plugins(
        {"cascade_a": (), "cascade_b": ("cascade_a",), "cascade_c": ("cascade_b",)},
        source="installed",
    )
    await manager.enable(records["cascade_c"])
    events = {name: record._plugin.events for name, record in records.items()}
    instance = records["cascade_c"]._plugin
    service = manager.services.require("cascade_c")
    started, release = asyncio.Event(), asyncio.Event()
    commands = []

    async def execute(*args, **kwargs):
        """隔离 uv 子进程，记录卸包请求而不修改真实安装环境。"""
        commands.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(ops, "ensure", lambda: "uv")
    monkeypatch.setattr(ops.ProcessRunner, "run_process", execute)
    call = asyncio.create_task(service(started=started, release=release))
    await started.wait()
    uninstall = asyncio.create_task(manager.uninstall(records["cascade_a"]))
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(uninstall), timeout=0.1)
        assert not commands
        assert all(history == ["enable"] for history in events.values())
        assert all(record._plugin is not None for record in records.values())
        with pytest.raises(PluginBusyError):
            await service()

        release.set()
        assert await call is instance
        assert await uninstall == {"cascade_b": {"cascade_c": {}}}
        assert events["cascade_c"] == ["enable", "call-finished", "disable"]
        assert all(record._plugin is None for record in records.values())
        assert not list(isolated_app_paths.plugin_registry.values())
        assert len(commands) == 1 and commands[0][3] == "cascade_a"
    finally:
        release.set()
        await asyncio.gather(call, uninstall, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("threaded", [False, True])
async def test_service_disables_itself_after_other_calls_finish(
    cascade_plugins, monkeypatch, threaded
):
    """服务内自禁用不等待自己，但必须等待另一服务调用退出，之后才能释放实例。"""
    from app.core import plugin

    manager, records = await cascade_plugins({"self_disable_probe": ()})
    monkeypatch.setattr(plugin, "Plugin", manager)
    record = records["self_disable_probe"]
    await manager.enable(record)
    instance = record._plugin
    service = manager.services.require("self_disable_probe")
    from fastapi import APIRouter, FastAPI
    from httpx import ASGITransport, AsyncClient

    app, router = FastAPI(), APIRouter()
    if threaded:
        router.get("/stop")(manager.services.require("self_disable_probe.sync"))
        manager.http.bind_app(app)
        manager.http.mount(
            "self_disable_probe", [], router=router, gate=manager._calls[record.uid]
        )
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def stop():
        """分别通过原异步服务或线程端点请求同一真实生命周期禁用。"""
        if threaded:
            response = await client.get("/stop")
            assert response.status_code == 200
            assert response.json() == {"disabled": True}
            return instance
        return await service(disable_self=True)

    started, release = asyncio.Event(), asyncio.Event()
    other = asyncio.create_task(service(started=started, release=release))
    await started.wait()
    stopping = asyncio.create_task(stop())
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(stopping), timeout=0.1)
        assert record._plugin is instance
        assert instance.events == ["enable"]
        with pytest.raises(PluginBusyError):
            await service()

        release.set()
        assert await asyncio.wait_for(asyncio.gather(other, stopping), timeout=2) == [
            instance,
            instance,
        ]
        assert instance.events == ["enable", "call-finished", "disable"]
        assert record.info.state == PluginState.DISABLED
        assert record._plugin is None
        with pytest.raises(PluginBusyError):
            await service()
    finally:
        release.set()
        await asyncio.gather(other, stopping, return_exceptions=True)
        await client.aclose()
        if record.info.state == PluginState.ENABLED:
            await manager.disable(record)


@pytest.mark.asyncio
async def test_reload_checks_locked_indirect_adapter_before_tearing_down(
    cascade_plugins, isolated_app_paths, monkeypatch
):
    """最下游适配器的配置仍被任务占用时，重载上游应在拆卸任何实例前拒绝。"""
    from app.config import ConfigCollection
    from app.core import plugin
    from app.models.config import PlanEntry, ScriptEntry
    from app.plugin.errors import PluginPrecheckError

    scripts = ConfigCollection[ScriptEntry].build([ScriptEntry])
    plans = ConfigCollection[PlanEntry].build([PlanEntry])
    await scripts.activate()
    await plans.activate()
    monkeypatch.setattr(isolated_app_paths, "ScriptConfig", scripts)
    monkeypatch.setattr(isolated_app_paths, "PlanConfig", plans)
    manager, records = await cascade_plugins(
        {"cascade_a": (), "cascade_b": ("cascade_a",), "cascade_c": ("cascade_b",)},
        adapters=("cascade_c",),
    )
    monkeypatch.setattr(plugin, "Plugin", manager)
    await manager.enable(records["cascade_c"])
    uid = scripts.add(records["cascade_c"]._plugin.decl.script_type)
    await scripts.commit()
    ticket = await scripts[uid].try_lock_x()
    before = {name: record._plugin for name, record in records.items()}
    try:
        with pytest.raises(PluginPrecheckError, match="已锁定"):
            await manager.reload(records["cascade_a"])
        assert all(record._plugin is before[name] for name, record in records.items())
        assert all(
            record.info.state == PluginState.ENABLED for record in records.values()
        )
        assert all(instance.events == ["enable"] for instance in before.values())
    finally:
        await scripts[uid].unlock(ticket)
        await manager.disable(records["cascade_a"])
