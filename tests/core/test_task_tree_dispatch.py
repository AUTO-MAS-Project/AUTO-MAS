"""任务创建、信息树身份与内建/插件分流的隔离回归。"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from app.config import ConfigCollection, config_manager
from app.core import Config, Publisher
from app.core.background_tasks import BackgroundTaskRegistry
from app.core.ws import protocol
from app.models.config import (
    GeneralConfig,
    QueueConfig,
    QueueItem,
)
from app.models.task import TaskMode
from app.utils.common.log_box.results import LogEntry
from tests.support.scheduler import Builtin
from tests.support.scheduler import scheduler as scheduler


@pytest.mark.asyncio
async def test_repeated_queue_items_run_in_order_with_independent_identity(
    scheduler, monkeypatch
):
    manager, _, queues, sid = scheduler
    qid = queues.add(QueueConfig, payload={"Info": {"Name": "queue"}})
    await queues.commit()
    children = {}
    for position in range(3):
        item_id = queues[qid].QueueItem.add(
            QueueItem, payload={"Info": {"ScriptId": str(sid)}}
        )
        children[position] = {"uid": str(item_id), "params": {"position": position}}
    await queues[qid].QueueItem.commit()
    calls = []

    class ObservedBuiltin(Builtin):
        async def main_task(self):
            calls.append(self.context.params["position"])
            await super().main_task()

    monkeypatch.setattr(
        manager,
        "manager_factories",
        {GeneralConfig: lambda script: ObservedBuiltin(script)},
    )
    uid = await manager.start(
        TaskMode.AUTO_PROXY, {0: {"uid": str(qid), "children": children}}
    )
    assert manager.get_runtime_snapshot().tasks[0].targetId == str(qid)
    run = manager.task_handler[uid]
    await asyncio.wait_for(run.accomplish.wait(), 4)
    assert run.task_info.status == "success", (
        run.error,
        [(s.status, s.log) for s in run.task_info.script_list],
    )
    scripts = run.task_info.script_list
    assert calls == [0, 1, 2]
    assert len(scripts) == 3 and len({script.uid for script in scripts}) == 3
    assert {script.info.script_type for script in scripts} == {"General"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "failed", "expected"),
    [
        ("逐条", False, "12:16 - ✅ 成功: 领取奖励\n    12:16 - ✅ 成功: 消耗体力"),
        ("汇总", False, "✅ 成功: 领取奖励, 消耗体力"),
        ("关闭", False, None),
        ("汇总", True, "❌ 失败: 连接超时"),
    ],
)
async def test_legacy_logbox_nodes_reach_completed_task_result(
    scheduler, monkeypatch, mode, failed, expected
):
    manager, _, _, sid = scheduler
    timestamp = datetime.now().astimezone().replace(hour=12, minute=16).timestamp()

    class WithLogBoxNodes(Builtin):
        async def main_task(self):
            await super().main_task()
            first = self.script_info.user_list[0]
            await first.set_state(status="异常" if failed else "完成")
            state = self.user_state(first)
            state.push_log_mode = mode
            for item in (
                ("普通", "✅ 成功: 领取奖励", timestamp),
                LogEntry("普通", "✅ 成功: 消耗体力", timestamp),
                ("失败", "❌ 失败: 连接超时", timestamp),
            ):
                self.callbacks.submit(state.append_push_log(item))

    monkeypatch.setattr(manager, "manager_factories", {GeneralConfig: WithLogBoxNodes})
    uid = await manager.start(
        TaskMode.AUTO_PROXY, {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}}
    )
    run = manager.task_handler[uid]
    await asyncio.wait_for(run.accomplish.wait(), 4)
    completed = next(
        call.kwargs["data"]
        for call in Publisher.send.call_args_list
        if call.kwargs["id"] == str(uid)
        and call.kwargs["type"] == protocol.TASK_COMPLETED
    )

    assert completed.outcome == ("error" if failed else "success")
    assert ("领取奖励" in completed.result) == (mode != "关闭")
    assert ("连接超时" in completed.result) == failed
    if expected:
        assert expected in completed.result
        assert completed.result.index("first:") < completed.result.index(expected)
        assert completed.result.index(expected) < completed.result.index("second:")
    assert manager.get_task_status(str(uid)).detail == completed.result


@pytest.mark.asyncio
async def test_plugin_task_keeps_its_registered_script_type(scheduler, monkeypatch):
    from whimbox_adapter.plugin import Plugin as WhimboxAdapter

    from app.core.plugin import Plugin

    manager, scripts, _, _ = scheduler
    config_type = WhimboxAdapter.decl.script_type
    scripts.add_type(config_type)
    await scripts.commit()
    script_id = scripts.add(config_type)
    await scripts.commit()
    monkeypatch.setattr(
        Plugin, "script_classes", lambda: {WhimboxAdapter.script_type_key: config_type}
    )
    monkeypatch.setattr(manager, "manager_factories", {config_type: Builtin})

    uid = await manager.start(
        TaskMode.AUTO_PROXY, {0: {"uid": "-", "children": {0: {"uid": str(script_id)}}}}
    )
    run = manager.task_handler[uid]
    await asyncio.wait_for(run.accomplish.wait(), 4)
    assert run.task_info.script_list[0].info.script_type == "Whimbox"


@pytest.mark.asyncio
async def test_queue_skips_managed_of_unavailable_plugin(scheduler):
    """队列里有一项托管的所属插件不可用：跳过它，同队列其余托管照常跑。"""
    manager, scripts, queues, sid = scheduler
    ghost = uuid4()
    kept = ConfigCollection.build(
        [GeneralConfig],
        keep_unknown_types=True,
        payload={
            "order": [
                {"uid": str(sid), "type": "GeneralConfig"},
                {"uid": str(ghost), "type": "GhostConfig"},
            ],
            "data": {
                str(sid): await scripts[sid].to_dict(),
                str(ghost): {"Info": {"Name": "ghost"}},
            },
        },
    )
    with (
        patch.object(Config, "ScriptConfig", kept),
        patch.dict(config_manager._collections, {"ScriptConfig": kept}),
    ):
        await kept.activate()
        qid = queues.add(QueueConfig, payload={"Info": {"Name": "queue"}})
        await queues.commit()
        for target in (sid, ghost, sid):
            queues[qid].QueueItem.add(
                QueueItem, payload={"Info": {"ScriptId": str(target)}}
            )
        await queues[qid].QueueItem.commit()

        uid = await manager.start(TaskMode.AUTO_PROXY, {0: {"uid": str(qid)}})
        run = manager.task_handler[uid]
        await asyncio.wait_for(run.accomplish.wait(), 4)
        assert run.task_info.status == "success", run.error
        assert [s.info.script_id for s in run.task_info.script_list] == [
            str(sid),
            str(sid),
        ]


@pytest.mark.asyncio
async def test_stop_all_blocks_new_requests_and_waits_for_inflight_creation(scheduler):
    from app.models.task import TaskItem

    manager, _, _, sid = scheduler
    entered, release = asyncio.Event(), asyncio.Event()
    activate = TaskItem.activate

    async def delayed_activate(info, **kwargs):
        entered.set()
        await release.wait()
        await activate(info, **kwargs)

    with (
        patch.object(TaskItem, "activate", delayed_activate),
        patch("app.core.Power.cancel_power_task", AsyncMock()),
    ):
        creating = asyncio.create_task(
            manager.start(
                TaskMode.AUTO_PROXY,
                {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}},
            )
        )
        await asyncio.wait_for(entered.wait(), 3)
        assert not manager.prepare_restart()
        stopping = asyncio.create_task(manager.stop("ALL"))
        await asyncio.sleep(0)
        try:
            with pytest.raises(RuntimeError):
                await manager.start(TaskMode.AUTO_PROXY, {})
            assert not stopping.done()
        finally:
            release.set()
        await asyncio.wait_for(creating, 3)
        await asyncio.wait_for(stopping, 3)
    assert not manager.task_handler
    assert manager.prepare_restart()
    with pytest.raises(RuntimeError, match="准备重启"):
        await manager.start(TaskMode.AUTO_PROXY, {})
    manager.cancel_restart()
    uid = await manager.start(
        TaskMode.AUTO_PROXY, {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}}
    )
    run = manager.task_handler[uid]
    await asyncio.wait_for(run.accomplish.wait(), 4)
    assert run.task_info.status == "success"


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_prefetch_dispatch_waits_for_real_download_cleanup(
    scheduler, monkeypatch, tmp_path, cancel
):
    """通过真实调度验证预下载复查发生在配置锁内，任务结束或取消时等待下载停写并释放引用。"""
    from app.core.downloads import DownloadManager
    from app.core.notify.lifecycle import NotificationTaskBase
    from app.models.schema import DownloadRequest
    from app.task import prefetch

    manager, scripts, _, sid = scheduler
    started, cleanup, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    background = BackgroundTaskRegistry()
    downloads = DownloadManager()

    async def transfer(request, path, progress):
        """模拟可完成或等待取消的下载，并在清理阶段等待测试放行以检查真实停写时机。"""
        started.set()
        try:
            if cancel:
                await asyncio.Event().wait()
            path.write_text("artifact")
        finally:
            cleanup.set()
            if cancel:
                await release.wait()

    downloads.initialize(
        directory=tmp_path / "cache",
        max_running=1,
        attempts=1,
        retry_delay=0,
        background=background,
        transfer=transfer,
    )
    monkeypatch.setattr(prefetch, "Downloads", downloads)
    calls = []
    lock_checked = asyncio.Event()

    class PrefetchBuiltin(Builtin):
        @staticmethod
        async def check_prefetch(config):
            """记录预下载检查时是否已取得配置锁，并返回固定需求供前后两次检查对照。"""
            calls.append(config.is_locked)
            if config.is_locked:
                lock_checked.set()
            return [DownloadRequest(url="https://example.test/file")]

        async def main_task(self):
            """取得旧专项配置锁，确认预下载路径已传入后执行既有测试任务，最后释放锁。"""
            ticket = await NotificationTaskBase.lock_script_config(self, scripts[sid])
            try:
                assert self.script_info.info.params["prefetch_paths"]
                await super().main_task()
            finally:
                await scripts[sid].unlock(ticket)

    manager.manager_factories = {GeneralConfig: lambda script: PrefetchBuiltin(script)}
    try:
        uid = await manager.start(
            TaskMode.AUTO_PROXY, {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}}
        )
        run = manager.task_handler[uid]
        await asyncio.wait_for(started.wait(), 3)
        if cancel:
            await asyncio.wait_for(lock_checked.wait(), 3)
            stop = asyncio.create_task(run.stop())
            await asyncio.wait_for(cleanup.wait(), 3)
            assert not stop.done()
            release.set()
            await asyncio.wait_for(stop, 3)
            assert run.task_info.status == "cancelled"
        else:
            await asyncio.wait_for(run.accomplish.wait(), 3)
            assert run.error is None and run.task_info.status == "success"
        assert calls == [False, True]
        assert not scripts[sid].is_locked
        assert downloads.list(owner=f"task:{run.task_info.uid}") == []
    finally:
        release.set()
        await downloads.shutdown_all()
        await background.shutdown(timeout=3)


@pytest.mark.asyncio
async def test_unconfirmed_prefetch_writer_blocks_following_scripts(
    scheduler, monkeypatch, tmp_path
):
    """验证预下载无法确认停写时标记任务失败，并阻止后续专项继续运行。"""
    from app.core.downloads import DownloadManager
    from app.core.notify.lifecycle import NotificationTaskBase
    from app.models.schema import DownloadRequest
    from app.task import prefetch
    from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed

    manager, scripts, _, sid = scheduler
    background = BackgroundTaskRegistry()
    downloads = DownloadManager()

    async def transfer(*args):
        """模拟下载器无法确认后台写入已停止，驱动调度阻断分支。"""
        raise FluxdownCancelUnconfirmed("daemon may still write")

    downloads.initialize(
        directory=tmp_path / "cache",
        max_running=1,
        attempts=1,
        retry_delay=0,
        background=background,
        transfer=transfer,
    )
    monkeypatch.setattr(prefetch, "Downloads", downloads)
    entered = []

    class UnsafeBuiltin(Builtin):
        @staticmethod
        async def check_prefetch(config):
            """为未确认停写场景声明固定预下载需求。"""
            return [DownloadRequest(url="https://example.test/file")]

        async def main_task(self):
            """尝试取得专项锁并记录已进入执行，供断言不安全预下载是否阻止后续业务。"""
            ticket = await NotificationTaskBase.lock_script_config(self, scripts[sid])
            entered.append(True)
            await scripts[sid].unlock(ticket)

    manager.manager_factories = {GeneralConfig: UnsafeBuiltin}
    try:
        uid = await manager.start(
            TaskMode.AUTO_PROXY, {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}}
        )
        run = manager.task_handler[uid]
        await asyncio.wait_for(run.accomplish.wait(), 3)
        assert isinstance(run.error, FluxdownCancelUnconfirmed)
        assert run.task_info.status == "error"
        assert not entered
        assert not scripts[sid].is_locked
        assert not await downloads.shutdown_all()
    finally:
        await background.shutdown(timeout=3)


@pytest.mark.asyncio
async def test_recovery_summary_reaches_current_task_completion(
    scheduler, monkeypatch, tmp_path
):
    """通过真实任务完成流程验证安装恢复汇总进入任务快照和完成通知。"""
    from app.core import Publisher
    from app.core.script_update import ScriptUpdateRequest, auto_recover_script_install
    from app.core.script_update_recovery import InstallInspection
    from app.core.ws import protocol

    manager, _, _, sid = scheduler
    sent = []
    monkeypatch.setattr(
        Publisher, "send", AsyncMock(side_effect=lambda **message: sent.append(message))
    )

    class Recovering(Builtin):
        async def main_task(self):
            """在专项执行中调用公共安装恢复入口，确认事件暂不单独通知，再进入普通任务流程。"""
            result = await auto_recover_script_install(
                ScriptUpdateRequest(str(sid), "MAA"),
                install_root=tmp_path,
                inspect=AsyncMock(
                    side_effect=[
                        InstallInspection(
                            pending=True,
                            healthy=True,
                            installed_version="1.1.0",
                            updated_confirmed=True,
                        ),
                        InstallInspection(
                            pending=False,
                            healthy=True,
                            installed_version="1.1.0",
                            updated_confirmed=True,
                        ),
                    ]
                ),
                acknowledge=AsyncMock(),
                reinstall=AsyncMock(),
            )
            assert result == "verified"
            assert not any(message["type"] == protocol.TASK_NOTICE for message in sent)
            await super().main_task()

    manager.manager_factories = {GeneralConfig: Recovering}
    uid = await manager.start(
        TaskMode.AUTO_PROXY, {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}}
    )
    run = manager.task_handler[uid]
    await asyncio.wait_for(run.accomplish.wait(), 4)
    assert run.error is None
    assert run.task_info.info.status == "success"
    notices = [message for message in sent if message["type"] == protocol.TASK_NOTICE]
    assert len(notices) == 1
    assert "已校验安装" in notices[0]["data"].message
    completed = next(
        message["data"]
        for message in sent
        if message["type"] == protocol.TASK_COMPLETED
    )
    assert (
        completed.task.model_dump()["current"]["recovery_summary"]
        == notices[0]["data"].message
    )
    assert (
        manager.get_task(uid)["current"]["recovery_summary"]
        == notices[0]["data"].message
    )


@pytest.mark.asyncio
async def test_desktop_queue_rechecks_plugin_before_admission(
    scheduler, monkeypatch, tmp_path
):
    from dataclasses import replace

    from auto_mas_core import (
        AutoProxyWorker,
        ConfigCollection,
        DesktopSessionRunFields,
        ScriptEntry,
        ScriptTypeDecl,
        UserEntry,
        UserExpander,
        collection,
    )
    from pydantic import Field

    from app.api.info import get_script_combox
    from app.api.queue import QueueSetInBase, add_item
    from app.core import Plugin
    from app.core.desktop_session.lifecycle import _DesktopSessionLifecycle
    from app.models.config import PluginRecord
    from app.plugin.calls import CallGate
    from app.plugin.types import PluginState
    from app.utils.common.process.session import DesktopProcessTarget

    class ProbeUser(UserEntry):
        pass

    class BaseProbeScript(ScriptEntry):
        class RunFields(DesktopSessionRunFields):
            AllowDesktop: bool = True

        users: ConfigCollection[ProbeUser] = collection(ProbeUser)
        Run: RunFields = Field(default_factory=RunFields)

    class ProbeScript(BaseProbeScript):
        pass

    class ProbeWorker(AutoProxyWorker):
        async def main_logic(self):
            await self.user_info.set_state(status="完成")

    class ProbeExpander(UserExpander[ProbeScript]):
        def build_worker(self, user, config):
            return ProbeWorker(self, user, config)

    def check_desktop_session(config, elevated):
        if not elevated:
            return "admin_required"
        return None if config.Run.AllowDesktop else "unsupported_config"

    manager, scripts, queues, builtin_id = scheduler
    scripts.add_type(BaseProbeScript)
    scripts.add_type(ProbeScript)
    await scripts.commit()
    sid = scripts.add(ProbeScript, payload={"info": {"name": "Probe"}})
    await scripts.commit()
    qid = queues.add(QueueConfig)
    await queues.commit()
    record = PluginRecord.build(
        info={"plugin_name": "desktop_session_probe", "state": PluginState.ENABLED}
    )
    gate = CallGate()
    decl = ScriptTypeDecl(
        script_type=ProbeScript,
        user_type=ProbeUser,
        expander_class=ProbeExpander,
        supported_modes=(TaskMode.AUTO_PROXY,),
        desktop_session_check=check_desktop_session,
        desktop_session=lambda config: config.Run.AllowDesktop,
    )
    # 两个已启用的专项可复用配置基类，但各自声明运行能力。
    base_record = PluginRecord.build(
        info={"plugin_name": "base_probe", "state": PluginState.ENABLED}
    )
    base_decl = replace(decl, script_type=BaseProbeScript, desktop_session_check=None)
    monkeypatch.setattr(
        Plugin, "script_types", {base_record.uid: base_decl, record.uid: decl}
    )
    monkeypatch.setattr(Plugin, "script_classes", lambda: {"ProbeAdapter": ProbeScript})
    monkeypatch.setattr(Plugin, "list_plugins", lambda: [base_record, record])
    monkeypatch.setattr(
        Plugin, "_calls", {base_record.uid: CallGate(), record.uid: gate}
    )
    monkeypatch.setattr("app.core.TaskManager", manager)

    users = scripts[sid].users
    user_id = users.add(ProbeUser)
    await users.commit()
    assert Plugin.trigger_owner(users[user_id]) == record.uid

    options = await get_script_combox()
    assert options.code == 200, options.message
    assert {option.value: option.label for option in options.data}[str(sid)] == (
        "ProbeAdapter - Probe"
    )
    item = await add_item(QueueSetInBase(queueId=str(qid)))
    assert item.code == 200, item.message
    queue_item = queues[qid].QueueItem[item.queueItemId]
    snapshot = queue_item.model_dump(context={"audience": "api"})
    script_hint = next(
        hint for hint in snapshot["ui"]["hints"]["Info"] if hint["field"] == "ScriptId"
    )
    labels = {option["value"]: option.get("label") for option in script_hint["options"]}
    assert labels[str(builtin_id)] == "script"
    assert labels[str(sid)] == "Probe"
    queue_item.Info.ScriptId = sid
    await queue_item.commit()

    service = _DesktopSessionLifecycle()
    monkeypatch.setattr(
        service,
        "_connected_target",
        lambda: DesktopProcessTarget(7, tmp_path, tmp_path),
    )
    monkeypatch.setattr("app.utils.IS_ELEVATED", True)
    entries = await service.dispatch_queues(
        [qid, sid], preview_only=True, main_session_queue_ids=set()
    )
    assert all(not entry["code"] for entry in entries)
    monkeypatch.setitem(
        Plugin.script_types,
        record.uid,
        replace(decl, supported_modes=(TaskMode.SCRIPT_CONFIG,)),
    )
    entries = await service.dispatch_queues(
        [qid, sid], preview_only=True, main_session_queue_ids=set()
    )
    assert [entry["reason"] for entry in entries] == ["unsupported_config"] * 2
    legacy_decl = replace(decl, desktop_session_check=None)
    monkeypatch.setitem(Plugin.script_types, record.uid, legacy_decl)
    entries = await service.dispatch_queues(
        [qid, sid], preview_only=True, main_session_queue_ids=set()
    )
    assert all(not entry["code"] for entry in entries)
    script = scripts[sid]
    script.Run.AllowDesktop = False
    await script.commit()
    entries = await service.dispatch_queues(
        [qid, sid], preview_only=False, main_session_queue_ids=set()
    )
    assert [(entry["taskId"], entry["reason"]) for entry in entries] == [
        ("", "unsupported_config")
    ] * 2
    script.Run.AllowDesktop = True
    await script.commit()
    monkeypatch.setitem(Plugin.script_types, record.uid, decl)
    monkeypatch.setattr("app.utils.IS_ELEVATED", False)
    entries = await service.dispatch_queues(
        [qid, sid], preview_only=False, main_session_queue_ids=set()
    )
    assert [(entry["taskId"], entry["reason"]) for entry in entries] == [
        ("", "admin_required")
    ] * 2
    # 错误的同步回调可能返回协程；拒绝该任务后插件仍须能正常卸载。
    monkeypatch.setitem(
        Plugin.script_types,
        record.uid,
        replace(decl, desktop_session_check=lambda *_: asyncio.sleep(0)),
    )
    entries = await service.dispatch_queues(
        [qid], preview_only=True, main_session_queue_ids=set()
    )
    assert entries[0]["reason"] == "plugin_unavailable"
    await asyncio.wait_for(gate.drain(), timeout=1)
    monkeypatch.setitem(Plugin.script_types, record.uid, decl)
    gate.accepting = False
    entries = await service.dispatch_queues(
        [qid], preview_only=False, main_session_queue_ids=set()
    )
    assert entries[0]["reason"] == "plugin_unavailable"
    assert not manager.task_handler

    # 已受理的队列可能要等桌面或前面的托管，轮到当前项时配置已改变。
    gate.accepting = True
    monkeypatch.setattr("app.utils.IS_ELEVATED", True)
    monkeypatch.setattr(manager, "plugin_expander", Plugin.resolve_script_expander)
    ready = asyncio.Event()
    monkeypatch.setattr("app.core.desktop_guard.ensure_desktop_available", ready.wait)
    entries = await service.dispatch_queues(
        [qid], preview_only=False, main_session_queue_ids=set()
    )
    run = manager.task_handler[UUID(entries[0]["taskId"])]
    script.Run.AllowDesktop = False
    await script.commit()
    ready.set()
    await asyncio.wait_for(run.accomplish.wait(), 4)
    assert run.task_info.status == "error"
    assert "unsupported_config" in run.task_info.script_list[0].log
    script.Run.AllowDesktop = True
    await script.commit()
    entries = await service.dispatch_queues(
        [qid], preview_only=False, main_session_queue_ids=set()
    )
    run = manager.task_handler[UUID(entries[0]["taskId"])]
    await asyncio.wait_for(run.accomplish.wait(), 4)
    assert run.task_info.status == "success", run.task_info.script_list[0].log
