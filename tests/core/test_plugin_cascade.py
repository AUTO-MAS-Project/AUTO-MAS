"""插件级联重载恢复状态，卸载等待全部下游的在途调用结束。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from app.config import ConfigCollection, config_manager
from app.core.plugin.manager import _PluginManager
from app.models.config import GlobalConfig, PluginRecord, PluginRegistryCollection
from app.plugin.errors import PluginBusyError, PluginOperationError, PluginPrecheckError
from app.plugin.runtime import loader
from app.plugin.types import PluginState
from app.utils import io


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
                    "from app.models.config import PlanEntry, ScriptEntry, UserEntry\n"
                    "from app.models.task import TaskMode\n"
                    "from app.task.user_expander import UserExpander\n"
                    "from app.plugin.base.script import ScriptAdapterPlugin as BasePlugin, ScriptTypeDecl\n"
                    "class ProbePlan(PlanEntry): pass\n"
                    "class ProbeUser(UserEntry): pass\n"
                    "class ProbeExpander(UserExpander): pass\n"
                    "class ProbeScript(ScriptEntry):\n"
                    "    users: ConfigCollection[ProbeUser] = collection(ProbeUser)\n"
                )
                declaration = (
                    "    script_type_key = 'probe'\n"
                    "    decl = ScriptTypeDecl(script_type=ProbeScript, user_type=ProbeUser, expander_class=ProbeExpander, plan_type=ProbePlan, supported_modes=(TaskMode.AUTO_PROXY,))\n"
                    "    async def on_script_removed(self, script_id):\n"
                    "        self.events.append(('removed', script_id))\n"
                )
            (package / "__init__.py").write_text(
                header
                + "class Adapter(BasePlugin):\n"
                + declaration
                + f"    requires = {tuple(requires)!r}\n"
                f"    provides_services = {{{name!r}: 'value', '{name}.sync': 'sync_value'}}\n"
                "    events = []\n"
                "    fail_enable = False\n"
                "    fail_disable = False\n"
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
                '        """记录资源禁用；按插件故障开关注入收尾失败。"""\n'
                "        self.events.append('disable')\n"
                "        if self.fail_disable: raise RuntimeError('plugin disable failed')\n"
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
    """恢复失败保留故障记录与启用意图，不通过其子节点重试失败分支，其他分支继续恢复。"""
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
    # 故障态只说明这次没恢复起来，不说明用户不要它：启用意图必须留着。
    assert records["cascade_b"].info.enabled
    assert records["cascade_b"].info.last_error
    assert records["cascade_b"]._plugin_cls.events.count("enable") == 2
    assert records["cascade_c"].info.state == PluginState.DISABLED
    # 被跳过的子树同样保留启用意图，否则故障排除后要逐个手工重新启用。
    assert records["cascade_c"].info.enabled
    assert records["cascade_c"]._plugin_cls.events.count("enable") == 1
    assert records["cascade_d"].info.state == PluginState.ENABLED
    assert await manager.services.require("cascade_d")() is records["cascade_d"]._plugin


@pytest.mark.asyncio
async def test_reload_restore_failure_keeps_enable_intent_for_restricted_plugin(
    cascade_plugins, monkeypatch
):
    """受控插件在依赖重载里没恢复起来，仍算「用户要它开着」：故障排除后重新启用不再要解锁。"""
    import app.core.plugin.manager as plugin_manager

    manager, records = await cascade_plugins(
        {"cascade_a": (), "signflow_token": ("cascade_a",)}
    )
    unlocked = True
    monkeypatch.setattr(plugin_manager, "is_unlocked", lambda: unlocked)

    await manager.enable(records["signflow_token"])
    record = records["signflow_token"]
    assert record.info.state == PluginState.ENABLED
    assert record.info.enabled

    # 依赖重载会先拆下游再恢复，这次让恢复失败：只有走真实这段代码才盖得住。
    record._plugin_cls.fail_enable = True
    result = await manager.reload(records["cascade_a"])
    assert result["tear"] == {"signflow_token": {}}
    assert result["restore"] == {}
    assert record.info.state == PluginState.FAULT_RUNTIME
    assert record.info.last_error
    assert record.info.enabled

    # 故障排除但当日未解锁：老用户点「启用」不能被当成首次使用。
    unlocked = False
    record._plugin_cls.fail_enable = False
    await manager.enable(record)
    assert record.info.state == PluginState.ENABLED
    assert record.info.enabled


@pytest.mark.asyncio
async def test_disable_on_faulty_record_only_cancels_next_start(cascade_plugins):
    """故障记录没有可拆的实例：显式停用只取消下次启动，不改状态也不跑插件收尾。"""
    manager, records = await cascade_plugins({"cascade_a": ()})
    record = records["cascade_a"]
    await manager.enable(record)
    # 模拟运行期故障：实例已被失败分支摘掉，只剩故障态与启用意图。
    record.info.state = PluginState.FAULT_RUNTIME
    record.info.last_error = "plugin crashed"
    await record.commit()

    assert await manager.disable(record) == {}

    assert record.info.state == PluginState.FAULT_RUNTIME
    assert not record.info.enabled
    # 没有实例可收尾，钩子不能为「停用一个出错的东西」再跑一遍。
    assert record._plugin_cls.events == ["enable"]


@pytest.mark.asyncio
async def test_reload_failure_keeps_enable_intent_of_torn_down_downstream(
    cascade_plugins, tmp_path
):
    """重载自身失败也要还回已拆下游的启用意图，否则故障排除后得逐个手工重开。"""
    manager, records = await cascade_plugins(
        {"cascade_a": (), "cascade_b": ("cascade_a",)}
    )
    await manager.enable(records["cascade_b"])
    assert records["cascade_b"].info.enabled

    # 让被重载的插件在重新加载时失败：下游此时已被拆掉，正卡在失败路径上。
    (tmp_path / "cascade_a" / "__init__.py").write_text(
        "raise RuntimeError('plugin reload failed')\n", encoding="utf-8"
    )
    with pytest.raises(PluginOperationError):
        await manager.reload(records["cascade_a"])

    assert records["cascade_a"].info.state == PluginState.FAULT_RUNTIME
    assert records["cascade_b"].info.state == PluginState.DISABLED
    # 拆下游是重载的内部动作，不是用户选择停用，启用意图必须留着。
    assert records["cascade_b"].info.enabled


@pytest.mark.asyncio
async def test_reload_teardown_failure_keeps_enable_intent_of_already_stopped_branch(
    cascade_plugins, monkeypatch
):
    """重载拆到一半失败：已经停稳的最下层不在父层名单里，也不能被当成用户主动停用。"""
    import app.core.plugin.manager as plugin_manager

    manager, records = await cascade_plugins(
        {
            "cascade_a": (),
            "cascade_b": ("cascade_a",),
            "signflow_token": ("cascade_b",),
        }
    )
    monkeypatch.setattr(plugin_manager, "is_unlocked", lambda: True)
    await manager.enable(records["signflow_token"])
    assert records["signflow_token"].info.enabled

    # 中间层收尾失败：最下层已经停稳并把结果交给了它，但中间层抛错后，
    # 最外层收到的名单里没有这一支，事后补不回来。
    records["cascade_b"]._plugin_cls.fail_disable = True
    with pytest.raises(PluginOperationError):
        await manager.reload(records["cascade_a"])

    assert records["signflow_token"].info.state == PluginState.DISABLED
    # 临时停一下不等于用户说关掉：意图留着，故障排除后还能自己起来。
    assert records["signflow_token"].info.enabled

    # 当日未解锁也照样能重新启用：它不是首次启用，不该被门禁拦下。
    records["cascade_b"]._plugin_cls.fail_disable = False
    monkeypatch.setattr(plugin_manager, "is_unlocked", lambda: False)
    await manager.enable(records["signflow_token"])
    assert records["signflow_token"].info.state == PluginState.ENABLED


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


@pytest_asyncio.fixture
async def cascaded_adapter(cascade_plugins, isolated_app_paths, monkeypatch):
    from app import core
    from app.core import plugin
    from app.models.config import PlanEntry, QueueConfig, ScriptEntry

    config = isolated_app_paths
    scripts = ConfigCollection[ScriptEntry].build(
        file=config.config_path / "scripts.yaml", keep_unknown_types=True
    )
    plans = ConfigCollection[PlanEntry].build(
        file=config.config_path / "plans.yaml", keep_unknown_types=True
    )
    queues = ConfigCollection.build(
        [QueueConfig], file=config.config_path / "queues.yaml"
    )
    for name, collection in (
        ("PlanConfig", plans),
        ("ScriptConfig", scripts),
        ("QueueConfig", queues),
    ):
        monkeypatch.setitem(config_manager._collections, name, collection)
        monkeypatch.setattr(config, name, collection)
        await collection.activate()
    manager, records = await cascade_plugins(
        {"cascade_a": (), "cascade_c": ("cascade_a",)},
        adapters=("cascade_c",),
        source="installed",
    )
    monkeypatch.setattr(plugin, "Plugin", manager)
    monkeypatch.setattr(core, "Plugin", manager)
    config_manager.register_root(config.setting, config.config_path / "setting.yaml")
    adapter = records["cascade_c"]
    await manager.enable(adapter)
    decl = adapter._plugin.decl
    pid = plans.add(decl.plan_type)
    await plans.commit()
    sid = scripts.add(decl.script_type)
    await scripts.commit()
    users = scripts[sid].users
    uid = users.add(
        decl.user_type, payload={"info": {"name": "原账号", "plan_id": str(pid)}}
    )
    await users.commit()
    qid, queue = await config.add_queue()
    await config.add_queue_item(str(qid), payload={"Info": {"ScriptId": str(sid)}})
    data = config.data_path / str(sid)
    data.mkdir()
    (data / "account.txt").write_bytes(b"account data")
    settings = config.config_path / "plugins" / "cascade_c.yaml"
    settings.parent.mkdir(exist_ok=True)
    settings.write_bytes(b"saved: value\n")
    await config_manager.flush()
    return SimpleNamespace(
        manager=manager,
        provider=records["cascade_a"],
        adapter=adapter,
        scripts=scripts,
        plans=plans,
        queue=queue,
        sid=sid,
        pid=pid,
        uid=uid,
        data=data,
        settings=settings,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "locked"), [("disable", "plans"), ("uninstall", "scripts")]
)
async def test_teardown_prechecks_locked_descendant(cascaded_adapter, action, locked):
    env = cascaded_adapter
    entry = next(getattr(env, locked).values())
    ticket = await entry.lock_s()
    try:
        with pytest.raises(PluginPrecheckError, match="已锁定"):
            if action == "disable":
                await env.manager.disable(env.provider)
            else:
                await env.manager.uninstall(env.provider, purge_config=True)
        assert env.adapter.info.state == env.provider.info.state == PluginState.ENABLED
        assert env.sid in env.scripts and env.pid in env.plans
        assert not env.scripts.unresolved() and not env.plans.unresolved()
        assert (env.data / "account.txt").is_file()
    finally:
        await entry.unlock(ticket)


@pytest.mark.asyncio
async def test_disable_and_enable_preserve_managed_documents(cascaded_adapter):
    env = cascaded_adapter
    old = env.scripts[env.sid]
    files = [col.persist_path for col in (env.scripts, env.plans)]
    before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in files]
    await env.manager.disable(env.provider)
    await config_manager.flush()
    assert old.deleted and old.users.deleted
    for col, uid, path in zip(
        (env.scripts, env.plans), (env.sid, env.pid), files, strict=True
    ):
        (item,) = col.unresolved()
        assert (
            item.uid == uid
            and item.payload == io.read_dict_file(path)["data"][str(uid)]
        )
    assert [(path.read_bytes(), path.stat().st_mtime_ns) for path in files] == before
    assert next(env.queue.QueueItem.values()).Info.ScriptId == env.sid
    assert (env.data / "account.txt").read_bytes() == b"account data"
    assert env.settings.read_bytes() == b"saved: value\n"

    await env.manager.enable(env.adapter)
    await config_manager.flush()
    assert [(path.read_bytes(), path.stat().st_mtime_ns) for path in files] == before
    for col, path in zip((env.scripts, env.plans), files, strict=True):
        assert not col.unresolved()
        assert await col.to_dict() == io.read_dict_file(path)
    assert env.scripts[env.sid].users[env.uid].info.plan_id == env.pid


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("purge", "disabled", "upstream"),
    [
        (False, False, False),
        (True, False, False),
        (True, True, False),
        (True, False, True),
    ],
)
async def test_uninstall_only_purges_selected_adapter(
    cascaded_adapter, monkeypatch, purge, disabled, upstream
):
    import httpx
    from fastapi import FastAPI

    from app.api import plugin as api
    from app.plugin import uv

    env = cascaded_adapter
    uninstall = AsyncMock()
    monkeypatch.setattr(uv, "uninstall", uninstall)
    events = env.adapter._plugin.events
    if disabled:
        await env.manager.disable(env.adapter)
    target = env.provider if upstream else env.adapter
    package = target.info.plugin_name
    app = FastAPI()
    app.include_router(api.router)
    monkeypatch.setattr(api, "Plugin", env.manager)
    body = {"recordId": str(target.uid)}
    if purge:
        body["purge_config"] = True
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/plugin/uninstall", json=body)
    assert response.json()["status"] == "success", response.text
    uninstall.assert_awaited_once_with(package)
    await config_manager.flush()

    assert (
        package
        in io.read_dict_file(env.settings.parents[1] / "setting.yaml")["plugin"][
            "uninstalled"
        ]
    )
    keep = not purge or upstream
    for col, uid in ((env.scripts, env.sid), (env.plans, env.pid)):
        assert col.is_unresolved(uid) == keep
        assert (str(uid) in io.read_dict_file(col.persist_path)["data"]) == keep
    assert [item.Info.ScriptId for item in env.queue.QueueItem.values()] == (
        [env.sid] if keep else []
    )
    assert (env.data / "account.txt").exists() == keep
    assert env.settings.exists() == keep
    assert (("removed", str(env.sid)) in events) == (
        purge and not disabled and not upstream
    )
