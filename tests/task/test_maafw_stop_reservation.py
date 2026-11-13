"""MFW 账号收尾保留历史，停止后同一项目仍可再次运行。"""

import asyncio
import sys
import threading
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.config import MaaFWConfig, MaaFWUserConfig
from app.task.MaaFW.tools.embedded.project_path import (
    release_project_path,
    try_reserve_project_path,
)
from app.task.MaaFW.tools.embedded.runner_task import MaaFWPluginAutoProxyTask
from app.utils.common.process.runner import create_subprocess, stop_process
from app.utils.common.process.scope import current_process_scope
from tests.config_support import activate_config
from tests.task_stop_support import StopTask, add_script


@pytest.mark.asyncio
async def test_manager_built_account_finishes_and_saves_history(
    isolated_app_paths, monkeypatch, tmp_path
):
    from app.core.history import HistoryStore
    from app.models.task import TaskItem
    from app.task import history_core
    from app.task.MaaFW import embedded_manager
    from app.task.MaaFW.tools.embedded import runner_task
    from app.utils import UTC4

    config = await activate_config(MaaFWConfig())
    user_id = config.UserData.add(
        MaaFWUserConfig, payload={"Notify": {"Enabled": False}}
    )
    await config.UserData.commit()
    info = TaskItem()
    script = await add_script(
        info=info, script_id=str(config.uid), user_id=str(user_id)
    )
    manager = embedded_manager.MaaFWEmbeddedManager(script)
    manager.script_config = config
    manager.user_config = config.UserData
    manager.history = history_core.TaskHistorySession(info)
    storage = HistoryStore()
    await storage.initialize(video_limit_bytes=0)
    monkeypatch.setattr(history_core, "History", storage)
    monkeypatch.setattr(runner_task.Notify, "send_notice", AsyncMock())
    monkeypatch.setattr(runner_task.Notify, "push_statistics_report", AsyncMock())
    account = manager._build_inner_task(
        SimpleNamespace(root=tmp_path / "runtime-pool", pool_id="test")
    )
    manager.inner_task = account
    manager._inner_finalized = False
    temporary_history = Path(account._history_temp.name)
    try:
        # 只隔离游戏执行，使用真实的账号装配、日志、收尾与历史存储。
        await account.prepare()
        account.check_result = "Pass"
        account.run_complete = True
        account._history_statuses[id(account.cur_user_log)] = "success"
        account._append_log("completed account log")
        await manager.callbacks.drain()
        assert "completed account log" in "".join(account.cur_user_log.content)
        await manager._finalize_inner_task()
        await manager._finalize_inner_task()
        assert script.user_list[0].status == "完成"
        assert config.UserData[user_id].Data.ProxyTimes == 1
        assert not temporary_history.exists()
        day = account.cur_user_log_started_at.astimezone(UTC4).date()
        groups = await storage.search(start_date=day, end_date=day, mode="DAILY")
        records = [
            record
            for users in groups.values()
            for bucket in users.values()
            for record in bucket.index
        ]
        assert len(records) == 1
        assert records[0].status == "success"
        detail = await storage.get_detail(record_id=records[0].id)
        assert "completed account log" in detail.log_content
    finally:
        await account.callbacks.close()
        await manager.callbacks.close()
        await manager.history.close()
        await storage.close()
        await account._release_project_path()
        account._history_temp.cleanup()


@pytest.mark.asyncio
async def test_stopped_account_releases_project_after_emulator_close_is_cancelled(
    isolated_app_paths,
):
    entered, close_attempted = asyncio.Event(), asyncio.Event()
    account = None
    user_id = uuid.uuid4()
    config = await activate_config(
        MaaFWConfig.build(payload={"Emulator": {"Index": "1"}})
    )
    user = await activate_config(
        MaaFWUserConfig.build(payload={"Notify": {"Enabled": False}})
    )

    class Emulator:
        async def close(self, index):
            # 真实的设备关闭命令应在停止确认中执行完，再释放项目预约。
            scope = current_process_scope.get()
            assert scope is not None and scope.requested
            close_attempted.set()
            process = await create_subprocess(sys.executable, "-I", "-c", "pass")
            await process.wait()

    class RunningAccount(MaaFWPluginAutoProxyTask):
        async def main_task(self):
            # 隔离游戏执行，只建立真实账号运行时持有的项目预约与设备状态。
            assert await self._try_enter_project_path()
            self.check_result = "Pass"
            self.opened_emulator = True
            entered.set()
            await asyncio.Event().wait()

    class Task(StopTask):
        async def main_task(self):
            nonlocal account
            script = await add_script(
                info=self.task_info, script_id=str(config.uid), user_id=str(user_id)
            )
            account = RunningAccount(
                script_info=script,
                script_config=config,
                user_config={user_id: user},
                emulator_manager=Emulator(),
            )
            await self.spawn(account)

    task = Task()
    task.start()
    try:
        await asyncio.wait_for(entered.wait(), timeout=3)
        await asyncio.wait_for(task.stop(), timeout=3)
        assert close_attempted.is_set()
        assert account is not None
        key = await try_reserve_project_path(account.project_path)
        try:
            assert key is not None, "停止后项目仍被占用，下一次运行将被跳过"
        finally:
            await release_project_path(key)
    finally:
        await task.stop()
        if account is not None:
            await account._release_project_path()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "force_process_fallback", [False, True] if sys.platform == "win32" else [False]
)
async def test_unconfirmed_pretask_stop_keeps_project_reserved(
    monkeypatch, isolated_app_paths, force_process_fallback
):
    from app.task.MaaFW.tools.embedded import runner_task as module

    ready = asyncio.Event()
    entered, release, thread_done = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
    account = process = None
    config = await activate_config(MaaFWConfig())
    user = await activate_config(
        MaaFWUserConfig.build(payload={"Notify": {"Enabled": False}})
    )
    user_id = uuid.uuid4()

    def snapshot(pid):
        entered.set()
        try:
            assert release.wait(5)
            return []
        finally:
            thread_done.set()

    def refuse_kill():
        raise PermissionError("injected native termination failure")

    monkeypatch.setattr(module, "_snapshot_pretask_script_descendants", snapshot)

    class RunningAccount(MaaFWPluginAutoProxyTask):
        async def main_task(self):
            nonlocal process
            assert await self._try_enter_project_path()
            self.check_result = "Pass"
            process = await create_subprocess(
                sys._base_executable, "-I", "-c", "import time; time.sleep(30)"
            )
            self.pretask_process = process
            ready.set()
            await asyncio.Event().wait()

    class Task(StopTask):
        STOP_CHECK_TIMEOUTS = {"update": 1.0, "finalize": 0.05}

        async def main_task(self):
            nonlocal account
            script = await add_script(
                info=self.task_info, script_id=str(config.uid), user_id=str(user_id)
            )
            account = RunningAccount(
                script_info=script,
                script_config=config,
                user_config={user_id: user},
                emulator_manager=None,
            )
            await self.spawn(account)

    task = Task()
    task.start()
    stopping = None
    try:
        await asyncio.wait_for(ready.wait(), timeout=3)
        scope = task._stop_scope
        if force_process_fallback:
            scope._job.close()
            scope._job = None
        with monkeypatch.context() as native:
            if scope._job is not None:
                native.setattr(scope._job, "kill", refuse_kill)
            else:
                native.setattr(scope._processes[id(process)][1], "kill", refuse_kill)
            stopping = task.request_stop()
            await asyncio.wait_for(task.accomplish.wait(), timeout=3)
            assert scope.cleanup_failed
            assert entered.is_set() and not thread_done.is_set()
            assert process.returncode is None
            key = await try_reserve_project_path(account.project_path)
            try:
                assert key is None, "尚未确认写进程停止，不能允许下一次操作项目"
            finally:
                await release_project_path(key)
    finally:
        release.set()
        if process is not None:
            await stop_process(process, kill_tree=True)
        if stopping is not None:
            await asyncio.gather(stopping, return_exceptions=True)
        if account is not None:
            await account._release_project_path()
        await asyncio.to_thread(thread_done.wait, 2)


@pytest.mark.asyncio
async def test_confirmed_force_stop_releases_project_after_pretask_snapshot_finishes(
    monkeypatch, isolated_app_paths
):
    """A retained native cleanup must eventually release the reservation after force stop."""
    from app.task.MaaFW.tools.embedded import runner_task as module

    entered, unblock, snapshot_done = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
    account = process = None
    config = await activate_config(MaaFWConfig())
    user = await activate_config(
        MaaFWUserConfig.build(payload={"Notify": {"Enabled": False}})
    )
    user_id = uuid.uuid4()
    running = asyncio.Event()

    def snapshot(pid):
        entered.set()
        try:
            assert unblock.wait(5)
            return []
        finally:
            snapshot_done.set()

    monkeypatch.setattr(module, "_snapshot_pretask_script_descendants", snapshot)

    class RunningAccount(MaaFWPluginAutoProxyTask):
        async def main_task(self):
            nonlocal process
            assert await self._try_enter_project_path()
            self.check_result = "Pass"
            process = await create_subprocess(
                sys._base_executable, "-I", "-c", "import time; time.sleep(30)"
            )
            self.pretask_process = process
            running.set()
            await asyncio.Event().wait()

    class Task(StopTask):
        STOP_CHECK_TIMEOUTS = {"update": 1.0, "finalize": 0.05}

        async def main_task(self):
            nonlocal account
            script = await add_script(
                info=self.task_info, script_id=str(config.uid), user_id=str(user_id)
            )
            account = RunningAccount(
                script_info=script,
                script_config=config,
                user_config={user_id: user},
                emulator_manager=None,
            )
            await self.spawn(account)

    task = Task()
    task.start()
    try:
        await asyncio.wait_for(running.wait(), 3)
        stopping = task.request_stop()
        async with asyncio.timeout(3):
            while not entered.is_set():
                await asyncio.sleep(0.01)
        await asyncio.wait_for(task.accomplish.wait(), 3)
        assert task._stop_scope.finished.is_set()
        assert not task._stop_scope.cleanup_failed
        assert not snapshot_done.is_set()
        assert process is not None
        # Windows 的 Job 终止与 asyncio 退出通知不同步；保持快照屏障，
        # 有界等待进程退出后再检查预约，不能把通知时序当作锁未释放。
        async with asyncio.timeout(1):
            while process.returncode is None:
                await asyncio.sleep(0.01)
        assert account is not None
        key = await try_reserve_project_path(account.project_path)
        try:
            assert key is None, "snapshot is still reading; reservation must stay held"
        finally:
            await release_project_path(key)
        unblock.set()
        async with asyncio.timeout(4):
            while (key := await try_reserve_project_path(account.project_path)) is None:
                await asyncio.sleep(0.01)
        await release_project_path(key)
        assert snapshot_done.is_set()
        await asyncio.gather(stopping, return_exceptions=True)
    finally:
        unblock.set()
        if process is not None and process.returncode is None:
            await stop_process(process, kill_tree=True)
        task.request_stop()
        await asyncio.gather(task._task, return_exceptions=True)
        if account is not None:
            await account._release_project_path()
        await asyncio.to_thread(snapshot_done.wait, 2)


@pytest.mark.asyncio
async def test_cancelled_release_check_releases_project_after_stop(
    tmp_path, monkeypatch, isolated_app_paths
):
    """Stopping a real release check waiting on another update must permit rerun."""
    import json

    from app.task.MaaFW.tools.embedded import embedded_project, view_update

    monkeypatch.chdir(tmp_path)
    config = await activate_config(MaaFWConfig())
    user = await activate_config(
        MaaFWUserConfig.build(payload={"Notify": {"Enabled": False}})
    )
    user_id = uuid.uuid4()
    source = tmp_path / "source"
    (source / "resource").mkdir(parents=True)
    (source / "interface.json").write_text(
        json.dumps(
            {
                "interface_version": 2,
                "name": "StopCheck",
                "version": "1.0",
                "github": "https://github.com/audit/stop-check",
                "resource": [{"name": "Default", "path": ["resource"]}],
                "task": [],
            }
        ),
        encoding="utf-8",
    )
    (source / "resource/data.json").write_text("{}", encoding="utf-8")
    await asyncio.to_thread(
        embedded_project.import_embedded_project,
        str(config.uid),
        source,
        verify_release=False,
    )
    view = embedded_project.embedded_project_dir(str(config.uid))
    marker = embedded_project.read_view_marker(view)
    assert marker is not None
    lock = view_update.lineage_update_lock(str(marker["lineage"]))
    account = None

    class RunningAccount(MaaFWPluginAutoProxyTask):
        async def main_task(self):
            assert await self._try_enter_project_path()
            self.check_result = "Pass"
            await self._recover_resource_failure("load_failed")

    class Task(StopTask):
        async def main_task(self):
            nonlocal account
            script = await add_script(
                info=self.task_info, script_id=str(config.uid), user_id=str(user_id)
            )
            account = RunningAccount(
                script_info=script,
                script_config=config,
                user_config={user_id: user},
                emulator_manager=None,
            )
            await self.spawn(account)

    await lock.acquire()
    task = Task()
    task.start()
    try:
        # Keep the other update's lock held until the check actually waits on it.
        async with asyncio.timeout(3):
            while not lock._waiters:
                await asyncio.sleep(0.01)
        await asyncio.wait_for(task.stop(), 3)
        assert task._stop_scope.finished.is_set()
        assert not task._stop_scope.cleanup_failed
        assert account is not None
        assert account._release_check_task.cancelled()
        # Deferred release may finish on the next loop turn after stop returns.
        key = None
        try:
            async with asyncio.timeout(1):
                while (key := await try_reserve_project_path(view)) is None:
                    await asyncio.sleep(0.01)
        finally:
            await release_project_path(key)
    finally:
        lock.release()
        await task.stop()
        if account is not None:
            await account._release_project_path()
