"""删除模拟器实例后条目留作墓碑并占住槽位，指向它的绑定改为「设备已删除」。"""

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import uuid4, uuid5

import pytest
import pytest_asyncio

from app.config import ConfigCollection, config_manager
from app.config.errors import ConfigAggregateError
from app.core import Config, GameManager, Plugin
from app.core.config.game_upgrade import migrate_game_documents
from app.core.game_manager import _GameManager
from app.models.config import GeneralConfig, GeneralUserConfig
from app.models.config.game import DEVICE_DELETED_REASON, device_removed
from app.models.emulator import DeviceInfo, DeviceStatus
from app.models.task import TaskScriptItem
from app.task.game import GameSession
from app.task.general.registration import build_config_handler
from app.utils import io
from tests.config_support import activate_config

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

    async def create_instance(self, name):
        """与厂商控制台一样取最小的空闲原生编号。"""
        index = next(
            str(i)
            for i in range(len(self.instances) + 1)
            if str(i) not in self.instances
        )
        self.instances[index] = name or "new"
        return index

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


def adapter_for(vendor):
    class Adapter(control_module.Control):
        async def set_block_ad(self, enabled):
            pass

        async def build_backend(self, policy):
            return vendor

    return Adapter


def install_collections(monkeypatch):
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
    return games, scripts


@contextmanager
def device_removed_connected():
    before = len(device_removed.receivers)
    device_removed.connect(GameManager.on_device_removed, weak=False)
    connected = len(device_removed.receivers) > before
    try:
        yield
    finally:
        if connected:
            device_removed.disconnect(GameManager.on_device_removed)


async def discovered_game(monkeypatch, tmp_path, vendor):
    """由适配插件刷新发现设备：设备 uid 按插件自己的槽位算法分配。"""
    games, _ = install_collections(monkeypatch)
    await games.activate()
    executable = tmp_path / "ldconsole.exe"
    executable.touch()
    game_uid = games.add(LDPlayerGame, payload={"info": {"path": str(executable)}})
    await games.commit()
    game = games[game_uid]
    game.bind_runtime_signals()
    _GameManager.create_control(config=game, control_class=adapter_for(vendor))
    await game._control.refresh()
    return game


@pytest_asyncio.fixture
async def world(isolated_app_paths, tmp_path, monkeypatch):
    vendor = VendorBoundary()
    Adapter = adapter_for(vendor)
    games, scripts = install_collections(monkeypatch)
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

    with device_removed_connected():
        yield World(
            games,
            game,
            game.devices[kept],
            game.devices[removed],
            script,
            script.UserData[user_id],
            vendor,
        )


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
async def test_deleting_instance_keeps_tombstone_and_clears_bindings(world):
    from app.api.plugin import PluginGameDevicesIn, plugin_device_options

    game, removed_uid = world.game, world.removed.uid

    result = await run_trigger(world.removed, "delete_instance")

    assert result is not None and result.state == "succeeded", result
    assert world.vendor.deleted == ["1"]
    # 条目留作墓碑占住槽位，但不再列出
    assert set(game.devices.keys()) == {world.kept.uid, removed_uid}
    assert game.devices[removed_uid].info.tombstone
    options = await plugin_device_options(PluginGameDevicesIn(gameId=game.uid))
    assert [item.value for item in options.data] == [str(world.kept.uid)]
    assert str(world.kept.uid) in game.info.baselines
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
async def test_host_marks_tombstone_when_adapter_does_not(world):
    """适配插件删除成功却没写墓碑：宿主补写，同一原生编号新建的实例拿到新 uid。"""
    from app.api.plugin import PluginGameDevicesIn, plugin_device_options

    class NoTombstoneAdapter(adapter_for(world.vendor)):
        async def delete_instance(self, device_uid, *, ticket):
            self.check_subscription(device_uid, ticket)
            backend = await self.backend()
            await backend.delete_instance(self.device(device_uid).info.index)

    game, removed_uid = world.game, world.removed.uid
    await game._control.teardown()
    _GameManager.create_control(config=game, control_class=NoTombstoneAdapter)

    result = await run_trigger(world.removed, "delete_instance")

    assert result is not None and result.state == "succeeded", result
    assert world.vendor.deleted == ["1"]
    assert game.devices[removed_uid].info.tombstone
    assert_cleared(world.script, game)
    assert_cleared(world.user, game)

    result = await run_trigger(game, "create_instance")
    assert result is not None and result.state == "succeeded", result
    (new_uid,) = (
        device.uid
        for device in game.devices.values()
        if device.info.index == "1" and not device.info.tombstone
    )
    assert new_uid != removed_uid
    options = await plugin_device_options(PluginGameDevicesIn(gameId=game.uid))
    assert sorted(item.value for item in options.data) == sorted(
        [str(world.kept.uid), str(new_uid)]
    )


@pytest.mark.asyncio
async def test_tombstone_with_leftover_backup_is_not_recovery_pending(world):
    """墓碑带着恢复失败留下的备份时不报「待恢复」：列表里没有这一行可恢复。"""
    from app.api.games import GameGetIn, get_games

    game = world.game
    world.removed.session.backup = {"cpu": 4}
    world.removed.info.tombstone = True
    await world.removed.commit()
    world.kept.session.backup = {"cpu": 2}
    await world.kept.commit()

    out = await get_games(GameGetIn(gameId=game.uid))

    pending = out.runtime[str(game.uid)].recoveryPending
    assert world.removed.uid not in pending
    assert world.kept.uid in pending


@pytest.mark.asyncio
async def test_existing_tombstone_stays_hidden(world):
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

    assert game.devices[world.removed.uid].info.tombstone
    assert_cleared(world.script, game)
    assert_cleared(world.user, game)
    # 再次刷新不再改动任何东西，墓碑仍在
    result = await run_trigger(game, "refresh")
    assert result is not None and result.state == "succeeded", result
    assert game.devices[world.removed.uid].info.tombstone
    assert len(game.devices) == 2
    assert_cleared(world.user, game)


@pytest.mark.asyncio
async def test_tombstone_bound_by_running_script_waits_for_next_startup(world):
    """托管正在运行时它的绑定写不进去，留待下次启动维护。"""
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
        await GameManager.startup_maintenance()
        assert world.removed.uid in game.devices
        assert world.user.game.device_id == world.removed.uid
        assert world.user.game.unavailable_reason == ""
    finally:
        finish.set()
        await asyncio.wait_for(runner, timeout=2)

    await GameManager.startup_maintenance()
    assert game.devices[world.removed.uid].info.tombstone
    assert_cleared(world.script, game)
    assert_cleared(world.user, game)


@pytest.mark.asyncio
async def test_delete_while_target_subscribed_marks_tombstone_and_clears_idle_bindings(
    world,
):
    """同一安装下别的实例在跑时删除实例：留下墓碑，空闲托管的绑定立即改为「设备已删除」。"""
    game = world.game
    _, ticket = await GameManager.subscribe(game.uid)
    try:
        result = await run_trigger(world.removed, "delete_instance")

        assert result is not None and result.state == "succeeded", result
        assert world.vendor.deleted == ["1"]
        assert game.devices[world.removed.uid].info.tombstone
        assert_cleared(world.script, game)
        assert_cleared(world.user, game)
    finally:
        await GameManager.unsubscribe(ticket)
    assert game.devices[world.removed.uid].info.tombstone


@pytest.mark.asyncio
async def test_run_refuses_deleted_device(world):
    """运行前检查：墓碑设备报「设备实例已删除」，规整后继承托管的账号同样如此。"""
    script, game = world.script, world.game
    await script.update(GeneralConfig.model_validate({"Game": {"Enabled": True}}))
    inherited_id = script.UserData.add(GeneralUserConfig)
    await script.UserData.commit()
    inherited = script.UserData[inherited_id]
    world.vendor.instances.pop("1")
    world.removed.info.tombstone = True
    await world.removed.commit()

    session = GameSession(TaskScriptItem.build(), script)
    try:
        with pytest.raises(ValueError, match=DEVICE_DELETED_REASON):
            await session.select()
    finally:
        await session.release()
    await GameManager.startup_maintenance()

    assert game.devices[world.removed.uid].info.tombstone
    assert_cleared(script, game)
    assert inherited.game.game_id == "-"
    for owner in (inherited, world.user):
        session = GameSession(TaskScriptItem.build(), script)
        try:
            with pytest.raises(ValueError, match=DEVICE_DELETED_REASON):
                await session.select(owner)
        finally:
            await session.release()
        assert session.game_uid is None


@pytest.mark.asyncio
async def test_upgraded_tombstone_binding_becomes_device_deleted_on_startup(
    isolated_app_paths, tmp_path, monkeypatch
):
    """旧 Emulator 2.0 墓碑槽位经升级迁移成墓碑设备，启动维护后绑定改为「设备已删除」。"""
    root = tmp_path / "upgrade"
    root.mkdir()
    console = root / "ldconsole.exe"
    console.touch()
    emulator, script_id, user_id = (str(uuid4()) for _ in range(3))
    slots = [
        {"slot": 1, "pathId": "ld", "nativeIndex": "0", "state": "active"},
        {"slot": 2, "pathId": "ld", "nativeIndex": "1", "state": "tombstone"},
    ]
    path = {"pathId": "ld", "type": "ldplayer", "installPath": str(console)}
    io.write_file(
        root / "emulators.yaml",
        {
            "order": [{"uid": emulator, "type": "EmulatorConfig"}],
            "data": {
                emulator: {
                    "Info": {"Type": "emulator2", "Paths": [path], "Slots": slots}
                }
            },
        },
    )
    io.write_file(
        root / "scripts.yaml",
        {
            "order": [{"uid": script_id, "type": "GeneralConfig"}],
            "data": {
                script_id: {
                    "Game": {"Enabled": True},
                    "Emulator": {"Id": emulator, "Index": "2"},
                    "UserData": {
                        "order": [{"uid": user_id, "type": "GeneralUserConfig"}],
                        "data": {user_id: {}},
                    },
                }
            },
        },
    )
    migrate_game_documents(root)

    games, scripts = install_collections(monkeypatch)
    vendor = VendorBoundary()
    vendor.instances = {"0": "kept"}
    await activate_config(games, root / "games.yaml")
    (game,) = games.values()
    game.bind_runtime_signals()
    _GameManager.create_control(config=game, control_class=adapter_for(vendor))
    await activate_config(scripts, root / "scripts.yaml")
    script = scripts[script_id]
    deleted = script.game.device_id
    assert script.game.game_id == game.uid
    assert game.devices[deleted].info.tombstone

    with device_removed_connected():
        await GameManager.startup_maintenance()

    assert game.devices[deleted].info.tombstone
    assert len(game.devices) == 2
    assert_cleared(script, game)
    assert script.UserData[user_id].game.game_id == "-"


def write_scripts(path, binding):
    """盘上一条托管：托管与一个账号指向 ``binding``，另一个账号继承托管。"""
    script_id, own_id, inherited_id = (str(uuid4()) for _ in range(3))
    io.write_file(
        path,
        {
            "order": [{"uid": script_id, "type": "GeneralConfig"}],
            "data": {
                script_id: {
                    "Game": {"Enabled": True},
                    "game": binding,
                    "UserData": {
                        "order": [
                            {"uid": own_id, "type": "GeneralUserConfig"},
                            {"uid": inherited_id, "type": "GeneralUserConfig"},
                        ],
                        "data": {own_id: {"game": binding}, inherited_id: {}},
                    },
                }
            },
        },
    )
    return script_id, own_id, inherited_id


async def load_sidelined_then_restore(monkeypatch, path, before_restore=None):
    """专项插件没加载时托管旁挂；插件恢复后经宿主还原入口转正。"""
    scripts = ConfigCollection.build([], keep_unknown_types=True)
    monkeypatch.setattr(Config, "ScriptConfig", scripts)
    plans = ConfigCollection.build(keep_unknown_types=True)
    monkeypatch.setattr(Config, "PlanConfig", plans)
    await plans.activate()
    await activate_config(scripts, path)
    assert [item.reason for item in scripts.unresolved()] == ["type_unregistered"]
    if before_restore is not None:
        await before_restore()
    scripts.add_type(GeneralConfig)
    await scripts.commit()
    await Config.restore_unavailable_managed()
    return scripts


async def load_on_startup(monkeypatch, path):
    """与正式启动一样：托管集合保留读不了的成员，激活后跑启动维护。"""
    scripts = ConfigCollection.build([GeneralConfig], keep_unknown_types=True)
    monkeypatch.setattr(Config, "ScriptConfig", scripts)
    await activate_config(scripts, path)
    await GameManager.startup_maintenance()
    return scripts


async def assert_run_refused(script, owner, reason):
    session = GameSession(TaskScriptItem.build(), script)
    try:
        with pytest.raises(ValueError, match=reason):
            await session.select(owner)
    finally:
        await session.release()


async def assert_loaded_as_device_deleted(scripts, path, ids, game):
    """托管照常读进来，绑定在内存与盘上都是「设备已删除」，运行被拒；再跑一遍不改动。"""
    script_id, own_id, inherited_id = ids
    assert scripts.unresolved() == ()
    script = scripts[script_id]
    own, inherited = script.UserData[own_id], script.UserData[inherited_id]
    assert_cleared(script, game)
    assert_cleared(own, game)
    assert inherited.game.game_id == "-"
    await config_manager.flush()
    saved = io.read_dict_file(path)["data"][script_id]
    assert saved["game"]["device_id"] == "-"
    assert saved["game"]["unavailable_reason"] == DEVICE_DELETED_REASON
    for owner in (None, own, inherited):
        await assert_run_refused(script, owner, DEVICE_DELETED_REASON)

    # 再跑一遍不再改动任何东西
    before = path.read_bytes()
    await GameManager.startup_maintenance()
    await config_manager.flush()
    assert path.read_bytes() == before
    assert_cleared(own, game)


@pytest.mark.asyncio
@pytest.mark.parametrize("path_kind", ["restore", "startup"])
async def test_binding_to_removed_device_still_loads_as_device_deleted(
    world, tmp_path, monkeypatch, path_kind
):
    """托管旁挂期间删掉它绑定的实例：插件恢复或下次启动时托管照常读进来，
    绑定改为「设备已删除」，墓碑仍在。"""
    game, removed_uid = world.game, world.removed.uid
    path = tmp_path / f"dangling-{path_kind}.yaml"
    ids = write_scripts(path, {"game_id": str(game.uid), "device_id": str(removed_uid)})

    async def delete_instance():
        result = await run_trigger(world.removed, "delete_instance")
        assert result is not None and result.state == "succeeded", result
        assert game.devices[removed_uid].info.tombstone

    if path_kind == "restore":
        scripts = await load_sidelined_then_restore(
            monkeypatch, path, before_restore=delete_instance
        )
    else:
        await delete_instance()
        scripts = await load_on_startup(monkeypatch, path)

    await assert_loaded_as_device_deleted(scripts, path, ids, game)
    assert game.devices[removed_uid].info.tombstone


@pytest.mark.asyncio
@pytest.mark.parametrize("path_kind", ["restore", "startup"])
async def test_binding_to_unknown_device_still_loads_as_device_deleted(
    world, tmp_path, monkeypatch, path_kind
):
    """盘上绑定指向目标里根本不存在的设备：同样照常读进来，改为「设备已删除」。"""
    game = world.game
    path = tmp_path / f"unknown-{path_kind}.yaml"
    ids = write_scripts(path, {"game_id": str(game.uid), "device_id": str(uuid4())})

    if path_kind == "restore":
        scripts = await load_sidelined_then_restore(monkeypatch, path)
    else:
        scripts = await load_on_startup(monkeypatch, path)

    await assert_loaded_as_device_deleted(scripts, path, ids, game)


@pytest.mark.asyncio
@pytest.mark.parametrize("path_kind", ["restore", "startup"])
async def test_recreated_instance_never_inherits_sidelined_binding(
    isolated_app_paths, tmp_path, monkeypatch, path_kind
):
    """专项插件不可用期间删掉最后一台实例、再以相同原生编号新建：
    旧托管恢复（或下次启动）后绑定改为「设备已删除」，不会指向新实例。"""
    from app.api.plugin import PluginGameDevicesIn, plugin_device_options

    vendor = VendorBoundary()
    vendor.instances = {"0": "kept", "1": "old"}
    game = await discovered_game(monkeypatch, tmp_path, vendor)
    by_index = {device.info.index: device.uid for device in game.devices.values()}
    kept_uid, old_uid = by_index["0"], by_index["1"]
    # 删的正好是槽位最大的一台：去掉它的条目后 max(slot)+1 会回退到它的槽位
    assert old_uid == uuid5(game.uid, "1:1")
    path = tmp_path / f"recreate-{path_kind}.yaml"
    script_id, own_id, inherited_id = write_scripts(
        path, {"game_id": str(game.uid), "device_id": str(old_uid)}
    )
    created: dict[str, object] = {}

    async def delete_then_recreate():
        result = await run_trigger(game.devices[old_uid], "delete_instance")
        assert result is not None and result.state == "succeeded", result
        result = await run_trigger(game, "create_instance")
        assert result is not None and result.state == "succeeded", result
        created["uid"] = next(
            device.uid
            for device in game.devices.values()
            if device.info.index == "1" and not device.info.tombstone
        )

    with device_removed_connected():
        if path_kind == "restore":
            scripts = await load_sidelined_then_restore(
                monkeypatch, path, before_restore=delete_then_recreate
            )
        else:
            await delete_then_recreate()
            scripts = await load_on_startup(monkeypatch, path)

        new_uid = created["uid"]
        assert new_uid != old_uid
        assert new_uid == uuid5(game.uid, "1:2")
        assert game.devices[new_uid].info.slot == 2
        # 墓碑保留并占住槽位，但不列出；新实例照常可见可选
        assert game.devices[old_uid].info.tombstone
        options = await plugin_device_options(PluginGameDevicesIn(gameId=game.uid))
        assert sorted(item.value for item in options.data) == sorted(
            [str(kept_uid), str(new_uid)]
        )

        assert scripts.unresolved() == ()
        script = scripts[script_id]
        own, inherited = script.UserData[own_id], script.UserData[inherited_id]
        for owner in (script, own):
            assert_cleared(owner, game)
            assert owner.game.device_id != new_uid
        assert inherited.game.game_id == "-"
        await config_manager.flush()
        saved = io.read_dict_file(path)["data"][script_id]
        assert saved["game"]["device_id"] == "-"
        assert saved["game"]["unavailable_reason"] == DEVICE_DELETED_REASON
        for owner in (None, own, inherited):
            await assert_run_refused(script, owner, DEVICE_DELETED_REASON)

        before = path.read_bytes()
        await GameManager.startup_maintenance()
        await config_manager.flush()
        assert path.read_bytes() == before
        assert game.devices[old_uid].info.tombstone


@pytest.mark.asyncio
@pytest.mark.parametrize("path_kind", ["restore", "startup"])
async def test_binding_to_missing_game_target_still_loads_unbound(
    world, tmp_path, monkeypatch, path_kind
):
    """盘上绑定指向已不存在的游戏目标：照删除整个目标的口径清空绑定，托管照常读进来。"""
    path = tmp_path / f"missing-game-{path_kind}.yaml"
    script_id, own_id, _ = write_scripts(
        path, {"game_id": str(uuid4()), "device_id": str(uuid4())}
    )

    if path_kind == "restore":
        scripts = await load_sidelined_then_restore(monkeypatch, path)
    else:
        scripts = await load_on_startup(monkeypatch, path)

    assert scripts.unresolved() == ()
    script = scripts[script_id]
    for owner in (script, script.UserData[own_id]):
        assert owner.game.game_id == "-"
        assert owner.game.device_id == "-"
        assert owner.game.unavailable_reason == ""
    await config_manager.flush()
    saved = io.read_dict_file(path)["data"][script_id]["game"]
    assert saved["game_id"] == "-" and saved["device_id"] == "-"


@pytest.mark.asyncio
async def test_user_save_still_rejects_missing_device_or_target(world):
    """加载放行不放松保存：用户选不存在的设备或目标仍被拒绝，原绑定不变。"""
    script, game = world.script, world.game
    with pytest.raises(ConfigAggregateError):
        await script.update(
            GeneralConfig.model_validate(
                {"game": {"game_id": str(game.uid), "device_id": str(uuid4())}}
            )
        )
    assert script.game.game_id == game.uid
    assert script.game.device_id == world.removed.uid
    with pytest.raises(ConfigAggregateError):
        await script.update(
            GeneralConfig.model_validate(
                {"game": {"game_id": str(uuid4()), "device_id": str(world.kept.uid)}}
            )
        )
    assert script.game.device_id == world.removed.uid


@pytest.mark.asyncio
async def test_dangling_binding_of_running_script_waits(world, tmp_path, monkeypatch):
    """托管正在运行时不改它的绑定，写不进去就留到下次。"""
    game, removed_uid = world.game, world.removed.uid
    result = await run_trigger(world.removed, "delete_instance")
    assert result is not None and result.state == "succeeded", result
    path = tmp_path / "running.yaml"
    script_id, own_id, _ = write_scripts(
        path, {"game_id": str(game.uid), "device_id": str(removed_uid)}
    )
    scripts = ConfigCollection.build([GeneralConfig], keep_unknown_types=True)
    monkeypatch.setattr(Config, "ScriptConfig", scripts)
    await activate_config(scripts, path)
    script = scripts[script_id]
    locked, finish = asyncio.Event(), asyncio.Event()

    async def running_script():
        ticket = await script.lock_x(cascade=False)
        locked.set()
        try:
            await finish.wait()
        finally:
            await script.unlock(ticket)

    runner = asyncio.create_task(running_script())
    try:
        await asyncio.wait_for(locked.wait(), timeout=2)
        await GameManager.startup_maintenance()
        assert script.game.device_id == removed_uid
        assert script.UserData[own_id].game.device_id == removed_uid
    finally:
        finish.set()
        await asyncio.wait_for(runner, timeout=2)

    await GameManager.startup_maintenance()
    assert_cleared(script, game)
    assert_cleared(script.UserData[own_id], game)
