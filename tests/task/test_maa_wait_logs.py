"""MAA 原生日志产生之前的等待提示，使用真实运行树和隔离设备替身。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio

from app.core import Publisher
from app.core.task_manager import _TaskManager
from app.core.ws import protocol
from app.models.config import MaaConfig
from app.task.MAA import manager as maa_manager
from app.task.MAA.AutoProxy import AutoProxyTask
from app.task.MAA.constants import ARKNIGHTS_PACKAGE_NAME
from app.task.MAA.tools import resource_update
from app.task.script_expander import ScriptExpander
from tests.runtime_support import create_runtime_tree


@pytest_asyncio.fixture
async def runtime(monkeypatch):
    root, script, user = await create_runtime_tree(script_id=str(uuid4()))
    script._manager_controls_users = True
    await script.set_current_index(0)
    manager = _TaskManager()
    manager._running[root.uid] = ScriptExpander(root, manager)
    monkeypatch.setattr("app.core.task_manager.TaskManager", manager)
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(Publisher, "send", sent)
    return root, script, user, manager, sent


def logs(sent):
    return [
        call.kwargs["data"].log
        for call in sent.await_args_list
        if call.kwargs["type"] == protocol.TASK_LOG_UPDATED
    ]


@pytest.mark.asyncio
async def test_emulator_wait_is_published_before_native_log(runtime):
    root, script, user, manager, sent = runtime
    entered = asyncio.Event()

    async def open_device(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    # 只替换外部准备和设备调用，执行 MAA 原有建记录、写提示、等待启动顺序。
    proxy = object.__new__(AutoProxyTask)
    proxy.task_info = root
    proxy.script_info = script
    proxy.cur_user_item = user
    proxy.cur_user_uid = user.user_id
    proxy.cur_user_config = SimpleNamespace(
        Info=SimpleNamespace(
            IfQuickConfig=False, Server=next(iter(ARKNIGHTS_PACKAGE_NAME))
        )
    )
    proxy.script_config = SimpleNamespace(
        Run=SimpleNamespace(RunTimesLimit=1), Emulator=SimpleNamespace(Index="0")
    )
    proxy.emulator_manager = SimpleNamespace(open=open_device)
    proxy.check = AsyncMock(return_value="Pass")
    proxy.prepare = AsyncMock()
    proxy.run_user_scripts_before = AsyncMock()
    proxy.run_book = {"GreenTicketStore": True, "Annihilation": True, "Routine": False}
    proxy._cultivate_archive_positions = {}
    proxy._cultivate_archive_versions = {}
    proxy._failed_sanity_tasks = set()
    proxy._failed_extra_tasks = set()
    proxy._non_sanity_retry = False
    task = asyncio.create_task(proxy.main_task())
    try:
        await asyncio.wait_for(entered.wait(), 3)
        assert logs(sent)[-1] == script.log
        assert logs(sent)[-1]  # 无原生日志时已经有启动提示。
        assert manager.get_runtime_snapshot().tasks[0].log == logs(sent)[-1]
        assert user.logs and all(not record.content for record in user.logs.values())
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()


@pytest.mark.asyncio
async def test_install_write_wait_is_published_before_config_lock(
    runtime, tmp_path, monkeypatch
):
    _, script, _, _, sent = runtime
    config = MaaConfig()
    await config.activate()
    config.Info.Path = tmp_path
    await config.commit()
    monkeypatch.setattr(maa_manager.Config, "ScriptConfig", {config.uid: config})
    # prepare 以业务 UUID 查询；运行节点 UUID 独立生成。
    script.info.script_id = str(config.uid)
    await script.commit()
    write_lock = asyncio.Lock()
    await write_lock.acquire()
    monkeypatch.setattr(maa_manager, "get_resource_write_lock", lambda path: write_lock)
    access = AsyncMock(side_effect=RuntimeError("stop before external access"))
    monkeypatch.setattr(maa_manager, "acquire_resource_access_lock", access)
    instance = maa_manager.MaaManager(script)
    task = asyncio.create_task(instance.prepare())
    try:
        await asyncio.sleep(0)
        assert logs(sent) and logs(sent)[-1] == script.log
        assert not task.done() and not config.is_locked
        write_lock.release()
        with pytest.raises(RuntimeError, match="stop before external access"):
            await task
        assert access.call_args.kwargs["progress"] == script.set_log
    finally:
        if write_lock.locked():
            write_lock.release()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_install_access_wait_reports_once_and_remains_cancellable(
    runtime, tmp_path, monkeypatch, cancel
):
    _, script, _, manager, sent = runtime
    retried = asyncio.Event()
    released = False
    attempts = 0

    class Access:
        contended = True

        def __enter__(self):
            nonlocal attempts
            attempts += 1
            if attempts >= 2:
                retried.set()
            return self if released else None

    monkeypatch.setattr(resource_update, "_resource_access_lock", lambda path: Access())
    task = asyncio.create_task(
        resource_update.acquire_resource_access_lock(tmp_path, progress=script.set_log)
    )
    try:
        await asyncio.wait_for(retried.wait(), 3)
        assert len(logs(sent)) == 1
        assert manager.get_runtime_snapshot().tasks[0].log == logs(sent)[0]
        if cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            released = True
            assert isinstance(await asyncio.wait_for(task, 3), Access)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
