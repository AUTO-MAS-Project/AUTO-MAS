"""配置恢复失败不能使无人值守任务永久丢失设备或串行名额。"""

import asyncio

import pytest

from app.config import ConfigCollection
from app.core.game_manager import _GameManager
from app.models.config.game import GameDeviceEntry, GameEntry
from app.plugin.base.game import DeviceSubscribeError, GameControl
from tests.support.scheduler import scheduler as scheduler


class ExternalControl(GameControl):
    """替换厂商进程边界，保留真实订阅、配置锁和串行准入。"""

    fail_restore = True

    async def refresh(self):
        pass

    async def open(self, device_uid, *, ticket):
        self.check_subscription(device_uid, ticket)

    close = show = hide = minimize = maximize = open

    async def _on_device_unsubscribed(self, device_uid):
        if self.fail_restore:
            raise OSError("vendor configuration is busy")


@pytest.mark.asyncio
async def test_game_discovery_uses_the_current_adapter_call_gate(monkeypatch):
    from app.api import games as games_api
    from app.core import Config
    from app.core.plugin.manager import _PluginManager
    from app.models.config import PluginRecord
    from app.plugin.base.game import GameTypeDecl
    from app.plugin.calls import CallGate
    from app.plugin.types import PluginState

    class RetiringGame(GameEntry):
        pass

    class AvailableGame(GameEntry):
        pass

    started = asyncio.Event()
    finish = asyncio.Event()
    retiring = RetiringGame.build(info={"name": "retiring"})
    available = AvailableGame.build(info={"name": "available"})

    async def search_retiring():
        started.set()
        await finish.wait()
        return [retiring]

    async def search_available():
        return [available, retiring]

    first = PluginRecord.build(info={"plugin_name": "retiring", "state": "enabled"})
    second = PluginRecord.build(info={"plugin_name": "available", "state": "enabled"})
    await first.activate()
    await second.activate()
    games = ConfigCollection[GameEntry].build([RetiringGame, AvailableGame])
    await games.activate()
    monkeypatch.setattr(Config, "GameConfig", games)
    monkeypatch.setattr(
        Config, "plugin_registry", {first.uid: first, second.uid: second}
    )
    plugins = _PluginManager()
    plugins.game_types = {
        first.uid: GameTypeDecl(
            RetiringGame, GameDeviceEntry, ExternalControl, search_retiring
        ),
        second.uid: GameTypeDecl(
            AvailableGame, GameDeviceEntry, ExternalControl, search_available
        ),
    }
    plugins._calls = {first.uid: CallGate(), second.uid: CallGate()}
    monkeypatch.setattr("app.core.plugin.Plugin", plugins)
    monkeypatch.setattr(games_api, "GameManager", _GameManager())

    async def retire():
        async with plugins._pause_owners((first.uid,)):
            plugins.game_types.pop(first.uid)
            first.info.state = PluginState.DISABLED
            await first.commit()

    search = asyncio.create_task(games_api.search_games())
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        lifecycle = asyncio.create_task(retire())
        await asyncio.sleep(0)
        assert not lifecycle.done()
    finally:
        finish.set()
    result = await asyncio.wait_for(search, timeout=2)
    await asyncio.wait_for(lifecycle, timeout=2)
    assert set(result.data) == {str(available.uid)}


@pytest.mark.asyncio
async def test_device_action_reserves_its_game_before_execution(monkeypatch):
    from app.api.games import GameGetIn, get_games
    from app.config.core.manager import ConfigManager, TriggerUnavailable
    from app.config.fields.hints import TriggerUiState
    from app.core import Config
    from app.core.background_tasks import BackgroundTaskRegistry
    from app.models.emulator import DeviceStatus

    online = asyncio.Event()
    finish = asyncio.Event()

    class StartingControl(ExternalControl):
        async def open(self, device_uid, *, ticket):
            await super().open(device_uid, ticket=ticket)
            device = self.config.devices[device_uid]
            device.info.status = DeviceStatus.ONLINE
            await device.commit()
            online.set()
            await finish.wait()

    def action(runtime, uid, field):
        return next(
            (
                hint
                for hint in runtime.actionHints[str(uid)]
                if hint.get("field") == field
            ),
            None,
        )

    games = ConfigCollection[GameEntry].build([GameEntry])
    await games.activate()
    first_uid, other_uid = games.add(GameEntry), games.add(GameEntry)
    await games.commit()
    first, other = games[first_uid], games[other_uid]
    a_uid = first.devices.add(GameDeviceEntry)
    b_uid = first.devices.add(GameDeviceEntry)
    await first.devices.commit()
    _GameManager.create_control(config=first, control_class=StartingControl)
    _GameManager.create_control(config=other, control_class=ExternalControl)
    monkeypatch.setattr(Config, "GameConfig", games)
    background = BackgroundTaskRegistry()
    dispatcher = ConfigManager()
    dispatcher.initialize_triggers(background, max_running=2)

    try:
        task = dispatcher.submit_trigger(
            first.devices[a_uid], group="action", field="open", value=True
        )
        assert task is not None
        assert first.devices[a_uid].action.open == task
        with pytest.raises(TriggerUnavailable, match="trigger_not_editable"):
            dispatcher.submit_trigger(
                first.devices[b_uid], group="action", field="open", value=True
            )
        await asyncio.wait_for(online.wait(), timeout=2)
        status = (await get_games(GameGetIn())).runtime
        first_hints = status[str(first_uid)]
        # 已在线后启动入口通常隐藏，正在执行的启动必须保持可见。
        opening = action(first_hints, a_uid, "open")
        assert opening["state"] is TriggerUiState.BUSY
        assert opening["editable"] is False
        assert action(first_hints, a_uid, "close")["state"] is TriggerUiState.IDLE
        assert action(first_hints, b_uid, "open")["editable"] is False
        assert action(first_hints, first_uid, "refresh")["editable"] is False
        assert action(status[str(other_uid)], other_uid, "refresh")["editable"] is True
        assert dispatcher.submit_trigger(
            other, group="action", field="refresh", value=True
        )
        finish.set()
        assert await background.get_group("config-triggers").drain(2)
        status = (await get_games(GameGetIn())).runtime[str(first_uid)]
        assert action(status, a_uid, "open") is None
        assert action(status, a_uid, "close")["editable"] is True
        assert action(status, b_uid, "open")["editable"] is True

        ticket = await first.lock_x(cascade=False)
        try:
            with pytest.raises(TriggerUnavailable, match="trigger_not_editable"):
                dispatcher.submit_trigger(
                    first.devices[b_uid], group="action", field="open", value=True
                )
            status = (await get_games(GameGetIn())).runtime[str(first_uid)]
            assert action(status, b_uid, "open")["editable"] is False
        finally:
            await first.unlock(ticket)
    finally:
        finish.set()
        await dispatcher.shutdown_triggers()
        await background.shutdown(timeout=2)


@pytest.mark.asyncio
async def test_open_uses_task_resolution_then_restores_user_baseline(
    monkeypatch, tmp_path
):
    """托管开机时应实际使用本轮分辨率，退订后再还原用户基准。"""
    from app.core import Config
    from app.models.emulator import DeviceInfo, DeviceStatus
    from app.plugin.base.emulator import EmulatorExpect

    module = pytest.importorskip("ldplayer_adapter.control")
    from ldplayer_adapter.config import LDPlayerDevice, LDPlayerGame

    class VendorBoundary:
        def __init__(self):
            self.settings = {"width": 1920, "height": 1080}
            self.opened_with = None
            self.config_lock = asyncio.Lock()

        async def open(self, index, package):
            self.opened_with = self.settings.copy()

        def read_instance_config(self, index):
            return self.settings.copy()

        async def write_instance_settings(self, index, changes, expected):
            self.settings.update(changes)

        def _get_instance_config_path(self, index):
            return tmp_path / "instance.json"

        def _get_instance_lock(self, index):
            return self.config_lock

        def _replace_instance_config(self, path, backup):
            self.settings = backup.copy()

        async def getInfo(self, index):
            return {"0": DeviceInfo("fixture", DeviceStatus.ONLINE, "127.0.0.1:5555")}

    vendor = VendorBoundary()

    class Adapter(module.Control):
        async def set_block_ad(self, enabled):
            pass

        async def build_backend(self, policy):
            return vendor

    executable = tmp_path / "console.exe"
    executable.touch()
    games = ConfigCollection[GameEntry].build([LDPlayerGame])
    await games.activate()
    uid = games.add(
        LDPlayerGame,
        payload={"info": {"path": str(executable), "config_guard": True}},
    )
    await games.commit()
    entry = games[uid]
    device = entry.devices.add(LDPlayerDevice)
    await entry.devices.commit()
    entry.info.baselines = {str(device): {"width": 1920, "height": 1080}}
    await entry.commit()
    control = _GameManager.create_control(config=entry, control_class=Adapter)
    monkeypatch.setattr(Config, "GameConfig", games)
    manager = _GameManager()
    _, ticket = await manager.subscribe(uid)
    try:
        handle = await control.subscribe_device(
            ticket, device, "test round", EmulatorExpect(1280, 720)
        )
        await handle.open()
        assert vendor.opened_with == {"width": 1280, "height": 720}
    finally:
        await manager.unsubscribe(ticket)
    assert vendor.settings == {"width": 1920, "height": 1080}


@pytest.mark.asyncio
async def test_failed_restore_releases_device_config_and_serial_admission(monkeypatch):
    """真实恢复抛错后，同设备和下一托管仍可订阅，旧票不能操作新订阅。"""
    from app.core import Config

    games = ConfigCollection[GameEntry].build([GameEntry])
    await games.activate()
    uid = games.add(GameEntry, payload={"info": {"concurrent_execution": False}})
    await games.commit()
    game = games[uid]
    device_uid = game.devices.add(GameDeviceEntry)
    await game.devices.commit()
    control = _GameManager.create_control(config=game, control_class=ExternalControl)
    monkeypatch.setattr(Config, "GameConfig", games)
    manager = _GameManager()
    _, ticket = await manager.subscribe(uid)
    handle = await control.subscribe_device(ticket, device_uid, "first run")

    with pytest.raises(OSError):
        await manager.unsubscribe(ticket)

    assert not game.is_locked
    # 释放失败后旧句柄仍可幂等结束，不影响后续真实订阅。
    await handle.release()
    _, next_ticket = await asyncio.wait_for(manager.subscribe(uid), timeout=1)
    next_handle = await control.subscribe_device(next_ticket, device_uid, "next run")
    with pytest.raises(DeviceSubscribeError):
        await handle.open()
    await next_handle.open()
    control.fail_restore = False
    await manager.unsubscribe(next_ticket)
    assert not game.is_locked


@pytest.mark.asyncio
async def test_restore_failure_preserves_account_success_counts_and_runs_later_scripts(
    scheduler, monkeypatch
):
    """公共调度入口：恢复失败仅影响托管终态，成功账号仍计次并继续下一托管。"""
    from uuid import uuid4

    from pydantic import Field

    from app.config import ConfigGroup, collection, config_manager
    from app.core import Config, Plugin
    from app.models.config import ScriptEntry, UserEntry
    from app.models.task import TaskMode
    from app.plugin.base.script import ScriptTypeDecl
    from app.task.mode_worker import AutoProxyWorker
    from app.task.user_expander import UserExpander

    class Account(UserEntry):
        class Data(ConfigGroup):
            successes: int = 0

        data: Data = Field(default_factory=Data)

    class Script(ScriptEntry):
        users: ConfigCollection[Account] = collection(Account)

    class Worker(AutoProxyWorker):
        async def main_logic(self):
            self.user_config.data.successes += 1
            await self.user_config.commit()
            await self.user_info.set_state(status="完成")

    class Expander(UserExpander):
        def build_worker(self, user, config):
            return Worker(self, user, config)

    manager, scripts, _, _ = scheduler
    games = ConfigCollection[GameEntry].build([GameEntry])
    monkeypatch.setattr(Config, "GameConfig", games)
    monkeypatch.setitem(config_manager._collections, "games", games)
    monkeypatch.setattr("app.core.GameManager", _GameManager())
    await games.activate()
    gid = games.add(GameEntry)
    await games.commit()
    did = games[gid].devices.add(GameDeviceEntry)
    await games[gid].devices.commit()
    _GameManager.create_control(config=games[gid], control_class=ExternalControl)
    scripts.add_type(Script)
    await scripts.commit()
    sids = []
    for name in ("first", "later"):
        sid = scripts.add(
            Script,
            payload={
                "info": {"name": name},
                "game": {"game_id": str(gid), "device_id": str(did)},
            },
        )
        await scripts.commit()
        scripts[sid].users.add(Account, payload={"info": {"name": "account"}})
        await scripts[sid].users.commit()
        sids.append(sid)
    monkeypatch.setattr(
        manager, "plugin_expander", lambda script, config: Expander(script, config)
    )
    monkeypatch.setattr(
        Plugin,
        "script_types",
        {
            uuid4(): ScriptTypeDecl(
                script_type=Script, user_type=Account, expander_class=Expander
            )
        },
    )

    for expected_count in (1, 2):
        run_id = await manager.start(
            TaskMode.AUTO_PROXY,
            {
                0: {
                    "uid": "-",
                    "children": {i: {"uid": str(sid)} for i, sid in enumerate(sids)},
                }
            },
        )
        run = manager.task_handler[run_id]
        await asyncio.wait_for(run.accomplish.wait(), timeout=4)
        assert run.task_info.status == "error"
        assert [script.status for script in run.task_info.script_list] == [
            "异常",
            "异常",
        ]
        assert [
            u.status for script in run.task_info.script_list for u in script.user_list
        ] == ["完成", "完成"]
        assert [
            u.data.successes for sid in sids for u in scripts[sid].users.values()
        ] == [expected_count, expected_count]
        assert not games[gid].is_locked
        assert all(not scripts[sid].is_locked for sid in sids)


@pytest.mark.asyncio
@pytest.mark.parametrize("concurrent_execution", [False, True], ids=["gate", "device"])
async def test_waiting_for_game_pushes_task_log_before_acquisition(
    monkeypatch, concurrent_execution
):
    """串行准入和同一设备占用都在等待期间发布任务日志。"""
    from app.config import config_manager
    from app.core import Config, Plugin, Publisher
    from app.core.task_manager import _TaskManager
    from app.core.ws.protocol import TASK_LOG_UPDATED
    from app.models.config import ScriptEntry, UserEntry
    from app.plugin.base.script import ScriptTypeDecl
    from app.task.game import GameSession
    from app.task.script_expander import ScriptExpander
    from app.task.user_expander import UserExpander
    from tests.support.scheduler import create_runtime_tree

    games = ConfigCollection[GameEntry].build([GameEntry])
    monkeypatch.setattr(Config, "GameConfig", games)
    monkeypatch.setitem(config_manager._collections, "games", games)
    await games.activate()
    game_uid = games.add(
        GameEntry,
        payload={
            "info": {"name": "测试游戏", "concurrent_execution": concurrent_execution}
        },
    )
    await games.commit()
    game = games[game_uid]
    device_uid = game.devices.add(
        GameDeviceEntry, payload={"info": {"name": "测试实例"}}
    )
    await game.devices.commit()
    control = _GameManager.create_control(config=game, control_class=ExternalControl)
    control.fail_restore = False

    config = ScriptEntry.build(
        payload={"game": {"game_id": str(game_uid), "device_id": str(device_uid)}}
    )
    await config.activate()
    monkeypatch.setattr(Config, "ScriptConfig", {str(config.uid): config})
    monkeypatch.setattr(
        Plugin,
        "script_types",
        {config.uid: ScriptTypeDecl(ScriptEntry, UserEntry, UserExpander)},
    )
    root, script, user = await create_runtime_tree(script_id=str(config.uid))
    script.current.index = user.uid
    await script.commit()
    registry = _TaskManager()
    registry._running[root.uid] = ScriptExpander(root, registry)
    monkeypatch.setattr("app.core.task_manager.TaskManager", registry)

    game_manager = _GameManager()
    monkeypatch.setattr("app.core.GameManager", game_manager)
    _, holder = await game_manager.subscribe(game_uid)
    await control.subscribe_device(holder, device_uid, "先运行的托管")

    waiting = asyncio.Event()
    logs = []
    expected = "当前占用：先运行的托管" if concurrent_execution else "等待获取游戏实例"

    async def send(*, id, type, data):
        if type == TASK_LOG_UPDATED and id == root.task_id:
            logs.append(data.log)
            if expected in data.log:
                waiting.set()
        return True

    monkeypatch.setattr(Publisher, "send", send)
    session = GameSession(script, config)
    selection = asyncio.create_task(session.select())
    try:
        try:
            await asyncio.wait_for(waiting.wait(), timeout=2)
        except TimeoutError:
            if selection.done():
                selection.result()
            raise
        assert not selection.done()
        assert "等待获取游戏实例「测试游戏」" in "".join(logs)
        if concurrent_execution:
            assert "设备「测试实例」，当前占用：先运行的托管" in "".join(logs)
        await game_manager.unsubscribe(holder)
        await asyncio.wait_for(selection, timeout=2)
        assert "已获取游戏实例「测试游戏」" in "".join(logs)
    finally:
        selection.cancel()
        await asyncio.gather(selection, return_exceptions=True)
        await session.release()
        await game_manager.unsubscribe(holder)


@pytest.mark.asyncio
async def test_failed_preparation_and_restore_do_not_leave_device_occupied():
    """准备和补偿恢复都失败时，下一轮仍可取得同台设备。"""
    from uuid import uuid4

    from app.config import LockTicket

    class PreparationControl(ExternalControl):
        fail_prepare = True

        async def _on_device_subscribed(self, device_uid, expect):
            if self.fail_prepare:
                raise ValueError("vendor preparation failed")

    control = PreparationControl()
    uid = uuid4()
    first = LockTicket(mode="s", token=uuid4(), issuer=uuid4(), cascade=False)
    with pytest.raises(ValueError):
        await control.subscribe_device(first, uid, "first run")
    control.fail_prepare = False
    control.fail_restore = False
    second = LockTicket(mode="s", token=uuid4(), issuer=uuid4(), cascade=False)
    handle = await control.subscribe_device(second, uid, "next run")
    await handle.open()
    await handle.release()
