"""删除模拟器实例后宿主移除设备条目，指向它的绑定与配置守卫基准一并处理。"""

import asyncio
from dataclasses import dataclass

import pytest
import pytest_asyncio

from app.config import ConfigCollection, config_manager
from app.config.errors import ConfigAggregateError
from app.core import Config, GameManager, Plugin
from app.core.game_manager import _GameManager
from app.models.config import GeneralConfig, GeneralUserConfig
from app.models.config.game import DEVICE_DELETED_REASON, device_removed
from app.models.emulator import DeviceInfo, DeviceStatus
from app.task.general.registration import build_config_handler

control_module = pytest.importorskip("ldplayer_adapter.control")
from ldplayer_adapter.config import LDPlayerDevice, LDPlayerGame  # noqa: E402


class VendorBoundary:
    """替换雷电控制台进程边界，其余走真实适配插件。"""

    def __init__(self):
        self.deleted: list[str] = []
        self.fail_delete = False
        self.instances = {"0": "kept", "1": "removed"}

    async def delete_instance(self, index):
        if self.fail_delete:
            raise RuntimeError("ldconsole remove failed")
        self.deleted.append(index)
        self.instances.pop(index, None)

    async def getInfo(self, index):
        return {
            key: DeviceInfo(title, DeviceStatus.OFFLINE, "")
            for key, title in self.instances.items()
        }


@dataclass
class World:
    games: ConfigCollection
    game: LDPlayerGame
    kept: object
    removed: object
    script: GeneralConfig
    user: GeneralUserConfig
    vendor: VendorBoundary


@pytest_asyncio.fixture
async def world(isolated_app_paths, tmp_path, monkeypatch):
    vendor = VendorBoundary()

    class Adapter(control_module.Control):
        async def set_block_ad(self, enabled):
            pass

        async def build_backend(self, policy):
            return vendor

    games = ConfigCollection.build([LDPlayerGame])
    scripts = ConfigCollection.build([GeneralConfig])
    monkeypatch.setitem(config_manager._collections, "games", games)
    monkeypatch.setattr(Config, "GameConfig", games)
    monkeypatch.setattr(Config, "ScriptConfig", scripts)
    monkeypatch.setattr(Config, "PlanConfig", ConfigCollection.build())
    monkeypatch.setattr(
        Config, "_script_config_handlers", {GeneralConfig: build_config_handler()}
    )
    monkeypatch.setattr(Plugin, "script_types", {})
    executable = tmp_path / "ldconsole.exe"
    executable.touch()
    await games.activate()
    game_uid = games.add(LDPlayerGame, payload={"info": {"path": str(executable)}})
    await games.commit()
    game = games[game_uid]
    game.bind_runtime_signals()
    kept = game.devices.add(LDPlayerDevice, payload={"info": {"index": "0"}})
    removed = game.devices.add(
        LDPlayerDevice, payload={"info": {"index": "1", "slot": 1}}
    )
    await game.devices.commit()
    game.info.baselines = {
        str(kept): {"width": 1920, "height": 1080},
        str(removed): {"width": 1280, "height": 720},
    }
    await game.commit()
    _GameManager.create_control(config=game, control_class=Adapter)

    await scripts.activate()
    binding = {"game": {"game_id": str(game_uid), "device_id": str(removed)}}
    script_id = scripts.add(GeneralConfig, payload=binding)
    await scripts.commit()
    script = scripts[script_id]
    user_id = script.UserData.add(GeneralUserConfig, payload=binding)
    await script.UserData.commit()

    before = len(device_removed.receivers)
    device_removed.connect(GameManager.on_device_removed, weak=False)
    connected = len(device_removed.receivers) > before
    try:
        yield World(
            games,
            game,
            game.devices[kept],
            game.devices[removed],
            script,
            script.UserData[user_id],
            vendor,
        )
    finally:
        if connected:
            device_removed.disconnect(GameManager.on_device_removed)


async def run_trigger(entry, field_name):
    """经真实配置触发器执行，与界面按钮走同一条路径。"""
    from app.config.core.manager import ConfigManager
    from app.core.background_tasks import BackgroundTaskRegistry

    background = BackgroundTaskRegistry()
    dispatcher = ConfigManager()
    dispatcher.initialize_triggers(background, max_running=2)
    try:
        task = dispatcher.submit_trigger(
            entry, group="action", field=field_name, value=True
        )
        assert task is not None
        assert await background.get_group("config-triggers").drain(2)
        return dispatcher.trigger_result(task)
    finally:
        await dispatcher.shutdown_triggers()
        await background.shutdown(timeout=2)


def assert_cleared(owner, game):
    assert owner.game.game_id == game.uid
    assert owner.game.device_id == "-"
    assert owner.game.unavailable_reason == DEVICE_DELETED_REASON


@pytest.mark.asyncio
async def test_deleting_instance_removes_device_bindings_and_baseline(world):
    game, removed_uid = world.game, world.removed.uid

    result = await run_trigger(world.removed, "delete_instance")

    assert result is not None and result.state == "succeeded", result
    assert world.vendor.deleted == ["1"]
    assert list(game.devices.keys()) == [world.kept.uid]
    assert set(game.info.baselines) == {str(world.kept.uid)}
    # 托管级与账号级绑定保留所选目标，只清空设备并写明原因
    assert_cleared(world.script, game)
    assert_cleared(world.user, game)

    # 重新选定设备即视为已处理，原因随之消失
    await world.script.update(
        GeneralConfig.model_validate({"game": {"device_id": str(world.kept.uid)}})
    )
    assert world.script.game.device_id == world.kept.uid
    assert world.script.game.unavailable_reason == ""
    # 删掉的设备不再出现在设备列表里，也不能被选回来
    with pytest.raises(ConfigAggregateError):
        await world.user.update(
            GeneralUserConfig.model_validate({"game": {"device_id": str(removed_uid)}})
        )


@pytest.mark.asyncio
async def test_failed_vendor_delete_keeps_device_and_bindings(world):
    world.vendor.fail_delete = True

    result = await run_trigger(world.removed, "delete_instance")

    assert result is not None and result.state == "failed", result
    removed = world.game.devices[world.removed.uid]
    assert not removed.info.tombstone
    assert set(world.game.info.baselines) == {
        str(world.kept.uid),
        str(world.removed.uid),
    }
    for owner in (world.script, world.user):
        assert owner.game.device_id == world.removed.uid
        assert owner.game.unavailable_reason == ""


@pytest.mark.asyncio
async def test_existing_tombstone_is_hidden_then_removed_once_idle(world):
    from app.api.plugin import PluginGameDevicesIn, plugin_device_options

    game = world.game
    # 旧版适配或升级迁移留下的墓碑：厂商侧实例已不在
    world.vendor.instances.pop("1")
    world.removed.info.tombstone = True
    await world.removed.commit()

    manager = _GameManager()
    _, ticket = await manager.subscribe(game.uid)
    try:
        # 目标正被会话订阅：不在运行中途改设备与绑定，只是不再当作可用设备
        assert await GameManager.remove_deleted_devices(game) == []
        assert world.removed.uid in game.devices
        assert world.script.game.device_id == world.removed.uid
        options = await plugin_device_options(PluginGameDevicesIn(gameId=game.uid))
        assert [item.value for item in options.data] == [str(world.kept.uid)]
        with pytest.raises(ConfigAggregateError):
            await world.script.update(
                GeneralConfig.model_validate(
                    {"game": {"device_id": str(world.removed.uid)}}
                )
            )
    finally:
        await manager.unsubscribe(ticket)

    await GameManager.startup_maintenance()

    assert list(game.devices.keys()) == [world.kept.uid]
    assert set(game.info.baselines) == {str(world.kept.uid)}
    assert_cleared(world.script, game)
    assert_cleared(world.user, game)
    # 再次启动或刷新不再改动任何东西
    assert await GameManager.remove_deleted_devices(game) == []
    result = await run_trigger(game, "refresh")
    assert result is not None and result.state == "succeeded", result
    assert list(game.devices.keys()) == [world.kept.uid]
    assert_cleared(world.user, game)


@pytest.mark.asyncio
async def test_tombstone_bound_by_running_script_waits_for_next_refresh(world):
    """托管正在运行时它的绑定写不进去，整笔回滚，留待下次刷新。"""
    game = world.game
    world.vendor.instances.pop("1")
    world.removed.info.tombstone = True
    await world.removed.commit()
    locked, finish = asyncio.Event(), asyncio.Event()

    async def running_script():
        ticket = await world.script.lock_x(cascade=False)
        locked.set()
        try:
            await finish.wait()
        finally:
            await world.script.unlock(ticket)

    runner = asyncio.create_task(running_script())
    try:
        await asyncio.wait_for(locked.wait(), timeout=2)
        assert await GameManager.remove_deleted_devices(game) == []
        assert world.removed.uid in game.devices
        assert str(world.removed.uid) in game.info.baselines
        assert world.user.game.device_id == world.removed.uid
        assert world.user.game.unavailable_reason == ""
    finally:
        finish.set()
        await asyncio.wait_for(runner, timeout=2)

    result = await run_trigger(game, "refresh")
    assert result is not None and result.state == "succeeded", result
    assert list(game.devices.keys()) == [world.kept.uid]
    assert_cleared(world.script, game)
    assert_cleared(world.user, game)
