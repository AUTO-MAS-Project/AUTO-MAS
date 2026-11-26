"""插件级联重载恢复状态，卸载等待全部下游的在途调用结束。"""

import asyncio
import json
import sys
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace

import psutil
import pytest
import pytest_asyncio
from auto_mas_core.log_flow import LogMonitor

from app.core import Notify
from app.core.background_tasks import BackgroundTaskRegistry
from app.core.notify import tasks as notification_tasks
from app.core.notify.rendering import AsyncNotificationRenderer
from app.core.plugin.manager import _PluginManager
from app.models.config import (
    GlobalConfig,
    PluginMeta,
    PluginRecord,
    PluginRegistryCollection,
)
from app.models.notification.channel import ChannelTarget, DeliveryChannel, NotifyTarget
from app.models.notification.report import TaskReportPolicy, TaskResultReport
from app.models.task import TaskUserItem
from app.plugin.errors import PluginBusyError, PluginOperationError
from app.plugin.runtime import discover, loader
from app.plugin.types import PluginState
from app.utils.common.log_flow.analysis import analyze_logs
from app.utils.common.log_flow.contracts import PipelineSpec, WorkerPluginPackage
from app.utils.common.log_flow.declaration import SimpleFlowDeclaration
from app.utils.common.log_flow.push import SubmitResult
from app.utils.common.log_flow.session import LogFlowSession
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
async def test_explicit_analysis_loads_its_worker_factories_after_plugin_reload(
    cascade_plugins, tmp_path
):
    manager, records = await cascade_plugins({"flow_declared": ()})
    record = records["flow_declared"]
    entry = tmp_path / "flow_declared" / "__init__.py"

    def write_plugin(prefix):
        entry.write_text(
            "from auto_mas_core.log_flow import FunctionRef, LineRule, SimpleFlowDeclaration, Source, TextProcessor, TextRecord, WorkerFactorySpec\n"
            "from app.plugin.base import BasePlugin\n"
            f"def prefix(text, _args): return {prefix!r} + text\n"
            "def clean(line): return line.removeprefix('raw:')\n"
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
            "class Adapter(BasePlugin): pass\n"
            "PLUGIN = Adapter\n",
            encoding="utf-8",
        )

    async def collect(name, text="event"):
        from auto_mas_core.log_flow import (
            FunctionRef,
            LineRule,
            WorkerFactorySpec,
            WorkerPluginPackage,
        )

        module = record.info.import_name
        if name == "declared":
            declaration = SimpleFlowDeclaration(
                processor=WorkerFactorySpec(
                    factory=FunctionRef(
                        name="declared:processor", module=module, attribute="processor"
                    )
                ),
            )
            source = WorkerFactorySpec(
                factory=FunctionRef(
                    name="declared:source", module=module, attribute="source"
                )
            )
        else:
            declaration = SimpleFlowDeclaration(
                rules=(
                    LineRule(
                        match="^event$", extract="$().probe:prefix()", node_type="普通"
                    ),
                ),
                preprocess=FunctionRef(
                    name="probe:clean", module=module, attribute="clean"
                ),
                functions=(
                    FunctionRef(name="probe:prefix", module=module, attribute="prefix"),
                ),
            )
            source = None
        async with analyze_logs(
            declaration,
            accept_push=True,
            source=source,
            plugin_package=WorkerPluginPackage(
                name=module,
                import_root=str(tmp_path),
                dependency_root=str(tmp_path),
                sdk_root=str(Path("plugins/auto_mas_core/src").resolve()),
            ),
        ) as flow:
            assert flow.reporter is not None
            assert flow.reporter.text(text) == SubmitResult.ACCEPTED
        return [flow.report_lines(mode="逐条")]

    write_plugin("before:")
    await manager.reload(record)
    await manager.enable(record)
    assert await collect("declared") == [["before:event", "before:source tail"]]
    assert await collect("expression", "raw:event") == [["before:event"]]
    write_plugin("after!:")
    await manager.reload(record)
    assert await collect("declared") == [["after!:event", "after!:source tail"]]
    assert await collect("expression", "raw:event") == [["after!:event"]]


@pytest.mark.asyncio
async def test_explicit_general_flow_uses_current_webui_rules():
    from auto_mas_core.log_flow import GeneralFlowDeclaration

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
        async with analyze_logs(rules, accept_push=True) as flow:
            assert flow.reporter is not None
            lines = (
                '@@LOGBOX@@{"op":"push","type":"普通","text":"旧宿主节点"}',
                "noise redacted token=discarded",
                "redacted token=secret",
                "@@LOGBOX@@ redacted token=secret",
            )
            for line in lines:
                assert flow.reporter.text(line) == SubmitResult.ACCEPTED
        page = flow.result
        assert page is not None
        assert page.reason == "complete"
        assert [node.text for node in page.nodes] == [
            replacement,
            replacement,
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True], ids=["complete", "cancel"])
async def test_autoproxy_worker_explicitly_records_analysis_for_its_account(
    cancel, tmp_path
):
    from auto_mas_core import AutoProxyWorker, UserExpander
    from auto_mas_core.log_flow import LineRule, LogFlow, LogFlowTaskReport
    from app.models.config import GeneralConfig

    _, script, account = await create_runtime_tree(user_id="default")
    report = LogFlowTaskReport(script)
    declaration = SimpleFlowDeclaration(
        rules=(LineRule(match="^done:", node_type="daily", status="success"),),
    )
    processes = []
    tail_written = tmp_path / "tail-written"

    async def capture_display(_lines, _latest_timestamp):
        pass

    async def launch():
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-u",
            "-c",
            "from pathlib import Path; import sys; print('done:claim'); sys.stdin.readline(); "
            "print('done:tail', end=''); Path(sys.argv[1]).touch(); sys.stdin.readline()",
            str(tail_written),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )
        processes.append(process)
        return process

    class Worker(AutoProxyWorker):
        async def main_logic(self):
            monitor = LogMonitor((0, 0), "", capture_display, process_factory=launch)
            flow = LogFlow(monitor, self.user_info, declaration)
            await self.spawn(flow)
            assert flow.result is not None and monitor.source_returncode == 0
            report.record(self.user_info, "汇总", flow.result)
            await self.user_info.set_state(status="完成")

    class Expander(UserExpander):
        def build_worker(self, user, config):
            return Worker(self, user, config)

    worker = Expander(script, GeneralConfig.build()).build_worker(account, None)
    worker.start()
    try:
        async with asyncio.timeout(5):
            while not account.log_analysis.nodes:
                assert not worker.accomplish.is_set(), worker.error
                await asyncio.sleep(0.01)
        assert [node.text for node in account.log_analysis.nodes] == ["done:claim"]
        assert account.log_analysis.close_reason is None
        [process] = processes
        assert process.stdin is not None
        if cancel:
            process.stdin.write(b"\n")
            await process.stdin.drain()
            async with asyncio.timeout(5):
                while not tail_written.exists():
                    await asyncio.sleep(0.01)
            assert process.returncode is None
            await asyncio.wait_for(worker.stop(), 8)
        else:
            process.stdin.close()
            await asyncio.wait_for(worker.accomplish.wait(), 8)
        assert worker.error is None, worker.error
        assert process.returncode is not None
        assert account.log_analysis.close_reason == "complete"
        if cancel:
            assert account.status == "已取消"
            assert [node.text for node in account.log_analysis.nodes] == [
                "done:claim",
                "done:tail",
            ]
        else:
            assert account.status == "完成"
            assert [node.text for node in account.log_analysis.nodes] == [
                "done:claim",
                "done:tail",
            ]
            assert report.details_for(account) == ["✅ 成功: done:claim, done:tail"]
    finally:
        if not worker.accomplish.is_set():
            await worker.stop()


@pytest.mark.asyncio
async def test_log_flow_report_retry_depends_on_notify_acceptance(monkeypatch):
    from auto_mas_core.log_flow import LogFlowTaskReport

    from app.core.notify.coordinator import TaskReportCoordinator

    _, script, _ = await create_runtime_tree()
    report = LogFlowTaskReport(script)
    result = TaskResultReport("10:00", "10:01", 1, 0, "账号执行结果")

    def fail_before_acceptance(**_):
        raise asyncio.CancelledError

    attempts = []

    async def fail_after_acceptance(self, *, request, payload):
        attempts.append(payload.text)
        raise asyncio.CancelledError

    monkeypatch.setattr(
        Notify,
        "read_task_report_policy",
        lambda: TaskReportPolicy("任何时刻", community_enabled=False, wait_seconds=0),
    )
    monkeypatch.setattr(Notify, "global_target", fail_before_acceptance)
    monkeypatch.setattr(
        TaskReportCoordinator, "_dispatch_report_payload", fail_after_acceptance
    )
    with pytest.raises(asyncio.CancelledError):
        await report.send(title="任务报告", report=result)

    monkeypatch.setattr(Notify, "global_target", lambda **_: NotifyTarget())
    with pytest.raises(asyncio.CancelledError):
        await report.send(title="任务报告", report=result)

    await report.send(title="任务报告", report=result)
    assert len(attempts) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("uncompleted", [0, 1], ids=["all-complete", "mixed-result"])
async def test_explicit_log_flow_delivers_one_task_report_via_notify(
    tmp_path, monkeypatch, uncompleted
):
    from auto_mas_core.log_flow import FunctionRef, LogFlowTaskReport, WorkerFactorySpec

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
                sink = (
                    WorkerFactorySpec(
                        factory=FunctionRef(
                            name="test:sink",
                            module="tests.support.log_flow_functions",
                            attribute="sample_sink",
                        ),
                        options={
                            "path": str(tmp_path / "slow-sink.txt"),
                            "mode": "block_close",
                        },
                    )
                    if key == "slow" and mode != "关闭"
                    else None
                )
                async with analyze_logs(
                    SimpleFlowDeclaration(),
                    accept_push=True,
                    sink=sink,
                    close_timeout=0.5,
                    prepare_report=mode != "关闭",
                ) as flow:
                    assert flow.reporter is not None
                    assert flow.reporter.node("普通", text) == SubmitResult.ACCEPTED
                    if run is first:
                        assert (
                            flow.reporter.node("普通", "step outcome", status="failed")
                            == SubmitResult.ACCEPTED
                        )
                        assert (
                            flow.reporter.node("失败", "category only")
                            == SubmitResult.ACCEPTED
                        )
                    if run is not muted:
                        assert (
                            flow.reporter.node(
                                "步骤", f"{text} diagnostic", status="exception"
                            )
                            == SubmitResult.ACCEPTED
                        )
                assert flow.result is not None
                await run.record_log_analysis(flow.result)
                report.record(run, mode or "汇总", flow.result)
            assert second.log_analysis.close_reason == "timeout"
            assert muted.log_analysis.close_reason == "complete"
            assert report.details_for(muted) == []
            result = TaskResultReport(
                "10:00", "10:01", 3 - uncompleted, uncompleted, "账号执行结果"
            )
            assert (await report.send(title="任务报告", report=result)).queued
            duplicate = await LogFlowTaskReport(script).send(
                title="重复报告", report=result
            )
            assert not duplicate.queued and duplicate.attempted == 0
            assert delivered == []
        assert await tasks.drain_notifications(timeout=3)
        [(target, content)] = delivered
        assert target == "probe"
        assert f"未完成数: {uncompleted}" in content
        rendered_details = content.split("账号执行结果\n\n【User】\n", 1)[1]
        first_block, second_block = rendered_details.split("\n\n【Second】\n", 1)
        assert first_block.splitlines() == [
            "first step",
            "❌ 失败: step outcome",
            "category only",
            "⚠ 异常: first step diagnostic",
        ]
        assert second_block.splitlines()[:3] == [
            "second step",
            "⚠ 异常: second step diagnostic",
            "⚠️ 节点采集不完整",
        ]
        assert content.count(" diagnostic") == 2
        assert "muted step" not in content
    finally:
        await tasks.close()
        renderer.close()


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
@pytest.mark.skipif(sys.platform != "win32", reason="使用真实的 Windows Job")
async def test_shared_environment_kept_until_log_flow_worker_exit_is_confirmed(
    cascade_plugins, monkeypatch
):
    from app.plugin import uv

    manager, records = await cascade_plugins({"worker_reader": ()}, source="installed")
    record = records["worker_reader"]
    await manager.enable(record)
    session = await LogFlowSession.open(
        PipelineSpec(
            accept_push=True,
            plugin_package=WorkerPluginPackage(
                name="worker_reader",
                import_root=str(record._project_dir),
                dependency_root=str(uv.site_dir(activate=False)),
                sdk_root=str(Path("plugins/auto_mas_core/src").resolve()),
            ),
        )
    )
    process = psutil.Process(session.pid)
    job = session._job
    assert job is not None
    removed = []

    async def remove(package):
        removed.append(package)

    async def prepare_install(_package, *, has_shared_environment_readers, **_kwargs):
        assert has_shared_environment_readers()
        return True

    async def keep_fixture_registry():
        pass

    def denied():
        raise PermissionError("无法结束启动器")

    def cannot_confirm():
        raise TimeoutError("无法确认采集进程退出")

    monkeypatch.setattr(uv, "uninstall", remove)
    monkeypatch.setattr(uv, "install", prepare_install)
    monkeypatch.setattr(discover, "refresh", keep_fixture_registry)
    try:
        process.suspend()
        with monkeypatch.context() as blocked:
            blocked.setattr(session._process, "kill", denied)
            blocked.setattr(job, "kill", cannot_confirm)
            summary = await session.close(timeout=0)
            assert summary.reason == "timeout" and "退出未确认" in summary.detail
            meta = PluginMeta.build(
                info={
                    "package_name": "auto-mas-worker-replacement",
                    "plugin_name": "worker_replacement",
                }
            )
            assert await manager.install(meta) == {"restart_required": True}
            with pytest.raises(PluginBusyError):
                await manager.uninstall(record)
            assert not removed and record.info.state == PluginState.ENABLED
        await manager.uninstall(record)
        assert removed == ["worker_reader"]
        assert not process.is_running()
    finally:
        await LogFlowSession.retry_unconfirmed_workers()
        with suppress(psutil.NoSuchProcess):
            process.kill()
            await asyncio.to_thread(process.wait, timeout=2)


@pytest.mark.asyncio
async def test_uninstall_blocks_new_shared_environment_readers(
    cascade_plugins, monkeypatch
):
    from app.plugin import uv

    manager, records = await cascade_plugins(
        {"being_removed": (), "separate_reader": ()}, source="installed"
    )
    await manager.enable(records["being_removed"])
    await manager.enable(records["separate_reader"])
    uninstalling = asyncio.Event()
    finish_uninstall = asyncio.Event()

    async def remove(_package):
        uninstalling.set()
        await finish_uninstall.wait()

    monkeypatch.setattr(uv, "uninstall", remove)
    removal = asyncio.create_task(manager.uninstall(records["being_removed"]))
    package = WorkerPluginPackage(
        name="separate_reader",
        import_root=str(records["separate_reader"]._project_dir),
        dependency_root=str(uv.site_dir(activate=False)),
        sdk_root=str(Path("plugins/auto_mas_core/src").resolve()),
    )
    try:
        await asyncio.wait_for(uninstalling.wait(), timeout=5)
        async with analyze_logs(
            SimpleFlowDeclaration(), accept_push=True, plugin_package=package
        ) as blocked:
            assert blocked.reporter is not None
            assert blocked.reporter.text("line") is SubmitResult.CLOSED
        assert blocked.result is not None and blocked.result.reason == "worker_error"

        async with analyze_logs(SimpleFlowDeclaration(), accept_push=True) as built_in:
            assert built_in.reporter is not None
            assert built_in.reporter.text("line") is SubmitResult.ACCEPTED
        assert built_in.result is not None and built_in.result.complete
    finally:
        finish_uninstall.set()
        await asyncio.wait_for(removal, timeout=5)

    async with analyze_logs(
        SimpleFlowDeclaration(), accept_push=True, plugin_package=package
    ) as resumed:
        assert resumed.reporter is not None
        assert resumed.reporter.text("line") is SubmitResult.ACCEPTED
    assert resumed.result is not None and resumed.result.complete


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
        # 连带停用名下还有托管的专项会被拒绝，收尾先删掉托管。
        scripts.remove(uid)
        await scripts.commit()
        await manager.disable(records["cascade_a"])


@pytest_asyncio.fixture
async def cascaded_adapter(cascade_plugins, isolated_app_paths, monkeypatch):
    """上游服务插件 cascade_a 加一个依赖它的专项 cascade_c，托管与计划表集合都是真实集合。"""
    from app.config import ConfigCollection
    from app.core import plugin
    from app.models.config import PlanEntry, ScriptEntry

    class ProbePlan(PlanEntry):
        pass

    scripts = ConfigCollection[ScriptEntry].build([ScriptEntry])
    plans = ConfigCollection[PlanEntry].build([PlanEntry, ProbePlan])
    await scripts.activate()
    await plans.activate()
    monkeypatch.setattr(isolated_app_paths, "ScriptConfig", scripts)
    monkeypatch.setattr(isolated_app_paths, "PlanConfig", plans)
    manager, records = await cascade_plugins(
        {"cascade_a": (), "cascade_c": ("cascade_a",)}, adapters=("cascade_c",)
    )
    monkeypatch.setattr(plugin, "Plugin", manager)
    await manager.enable(records["cascade_c"])
    return SimpleNamespace(
        manager=manager,
        records=records,
        scripts=scripts,
        plans=plans,
        plan_type=ProbePlan,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["disable", "unload", "uninstall"])
async def test_teardown_refuses_when_cascaded_adapter_still_has_scripts(
    cascaded_adapter, action
):
    """停用 / 卸载上游时连带的专项名下还有托管：整体拒绝，原因列出专项和托管数，什么都不动。"""
    from app.plugin.errors import PluginPrecheckError

    env = cascaded_adapter
    manager, records, scripts = env.manager, env.records, env.scripts
    uid = scripts.add(records["cascade_c"]._plugin.decl.script_type)
    await scripts.commit()
    before = {name: record._plugin for name, record in records.items()}
    with pytest.raises(PluginPrecheckError) as caught:
        await getattr(manager, action)(records["cascade_a"])
    assert "`cascade_c`（1 个托管、0 张计划表）" in caught.value.message
    assert caught.value.payload == {
        "inUse": [{"plugin": "cascade_c", "scripts": 1, "plans": 0}]
    }
    assert uid in [entry.uid for entry in scripts.values()]
    assert all(record._plugin is before[name] for name, record in records.items())
    assert all(record.info.state == PluginState.ENABLED for record in records.values())

    # 重载不删数据，照常放行；删掉托管之后停用照旧连带停用下游。
    await manager.reload(records["cascade_a"])
    assert records["cascade_c"].info.state == PluginState.ENABLED
    scripts.remove(uid)
    await scripts.commit()
    assert await manager.disable(records["cascade_a"]) == {"cascade_c": {}}
    assert records["cascade_c"].info.state == PluginState.DISABLED


@pytest.mark.asyncio
async def test_disable_refuses_when_cascaded_adapter_only_has_plans(
    cascaded_adapter, monkeypatch
):
    """连带的专项名下没有托管、只有计划表时同样拒绝。"""
    from app.plugin.errors import PluginPrecheckError

    env = cascaded_adapter
    adapter = env.records["cascade_c"]._plugin
    monkeypatch.setattr(adapter, "plan_type", env.plan_type)
    uid = env.plans.add(env.plan_type)
    await env.plans.commit()
    try:
        with pytest.raises(PluginPrecheckError) as caught:
            await env.manager.disable(env.records["cascade_a"])
        assert "`cascade_c`（0 个托管、1 张计划表）" in caught.value.message
        assert env.records["cascade_c"].info.state == PluginState.ENABLED
    finally:
        env.plans.remove(uid)
        await env.plans.commit()
        monkeypatch.setattr(adapter, "plan_type", None)
