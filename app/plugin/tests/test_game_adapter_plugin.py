"""游戏适配：类型表、锁定预检、订阅与搜索目录。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import ConfigCollection, LockTicket, NodeState
from app.config.shortcuts import collection
from app.models.config import GameDeviceEntry, GameEntry
from app.plugin.base.game import GameAdapterPlugin, GameControl, GameTypeDecl
from app.plugin.errors import PluginPrecheckError
from app.plugin.types import LifecycleContext, PluginState

_PLUGINS = Path(__file__).resolve().parents[3] / "plugins"


class _Ctrl(GameControl):
    async def refresh(self) -> None:
        return None

    async def open(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        return None

    async def close(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        return None

    async def show(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        return None

    async def hide(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        return None

    async def minimize(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        return None

    async def maximize(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        return None


class DemoGame(GameEntry):
    pass


class DemoDevice(GameDeviceEntry):
    pass


async def _empty_search() -> list[DemoGame]:
    return []


def _record(ctx: LifecycleContext, name: str = "demo") -> Any:
    class _Record:
        pass

    record = _Record()
    record.uid = uuid4()
    record.info = SimpleNamespace(lifecycle_context=ctx, plugin_name=name)
    return record


def _plugin(ctx: LifecycleContext, name: str = "demo") -> GameAdapterPlugin:
    class Demo(GameAdapterPlugin):
        game_type_key = name
        decl = GameTypeDecl(
            game_class=DemoGame,
            device_class=DemoDevice,
            control_class=_Ctrl,
            search=_empty_search,
        )

    record = _record(ctx, name)
    plugin = Demo(record=record)
    plugin._test_record = record
    return plugin


def test_list_entry_types_follows_type_table() -> None:
    class Item(GameEntry):
        pass

    col = ConfigCollection[GameEntry]([GameEntry])

    async def run() -> None:
        await col.activate()
        names = [row["name"] for row in col.list_entry_types()]
        assert names == ["GameEntry"]
        col.add_type(Item)
        await col.commit()
        assert "Item" in [row["name"] for row in col.list_entry_types()]
        col.remove_type(Item)
        await col.commit()
        assert "Item" not in [row["name"] for row in col.list_entry_types()]

    asyncio.run(run())


def test_games_types_and_add_are_siblings(monkeypatch) -> None:
    from app.api import games as games_api
    from app.core.plugin_manager import Plugin

    class Extra(GameEntry):
        pass

    col = ConfigCollection[GameEntry]([GameEntry])

    async def activate() -> None:
        await col.activate()
        col.add_type(Extra)
        await col.commit()

    asyncio.run(activate())
    monkeypatch.setattr(
        Plugin,
        "game_types",
        {
            uuid4(): GameTypeDecl(
                game_class=Extra,
                device_class=DemoDevice,
                control_class=_Ctrl,
                search=_empty_search,
            )
        },
    )

    class _Config:
        GameConfig = col

    previous = games_api.Config
    games_api.Config = _Config  # type: ignore[misc]
    app = FastAPI()
    app.include_router(games_api.router)
    client = TestClient(app)
    try:
        listed = client.post("/api/games/types")
        assert listed.status_code == 200
        body = listed.json()
        assert body["code"] == 200
        names = [row["name"] for row in body["data"]]
        assert names == ["Extra"]

        default_created = client.post("/api/games/add", json={})
        assert default_created.json()["code"] == 200

        created = client.post("/api/games/add", json={"type": "Extra"})
        assert created.json()["code"] == 200
        assert created.json()["gameId"]

        base_type = client.post("/api/games/add", json={"type": "GameEntry"})
        assert base_type.json()["code"] == 400

        unknown = client.post("/api/games/add", json={"type": "NotAGame"})
        assert unknown.json()["code"] == 400
    finally:
        games_api.Config = previous


def test_subscribe_locks_only_root() -> None:
    from app.core import Config

    entry = GameEntry()
    entry._game_control = _Ctrl(config=entry)

    class _Games:
        def get(self, uid: object) -> GameEntry | None:
            return entry if uid == entry.uid else None

    previous = Config.GameConfig
    Config.GameConfig = _Games()  # type: ignore[assignment]
    from app.core.game_manager import GameManager

    async def run() -> None:
        await entry.activate()
        ctrl, ticket = await GameManager.subscribe(entry.uid)
        assert ctrl is entry._game_control
        assert ticket.cascade is False
        assert entry.is_locked
        await GameManager.unsubscribe(ticket)
        assert not entry.is_locked

    try:
        asyncio.run(run())
    finally:
        Config.GameConfig = previous


def test_precheck_blocks_only_locked_created_instance() -> None:
    from app.core import Config

    class LockedGame:
        def __init__(self, locked: bool) -> None:
            self.uid = uuid4()
            self.is_locked = locked

    class Demo(GameAdapterPlugin):
        game_type_key = "locked-demo"
        decl = GameTypeDecl(
            game_class=cast(type[GameEntry], LockedGame),
            device_class=DemoDevice,
            control_class=_Ctrl,
            search=_empty_search,
        )

    record = _record(LifecycleContext.NORMAL, "locked-demo")
    plugin = Demo(record=record)
    plugin._test_record = record

    class _Games:
        def __init__(self, rows: list[object]) -> None:
            self._rows = rows

        def values(self) -> list[object]:
            return self._rows

    previous = Config.GameConfig
    try:
        Config.GameConfig = _Games(
            [LockedGame(False), SimpleNamespace(uid=uuid4(), is_locked=True)]
        )  # type: ignore[assignment]
        plugin.precheck_locks()
        Config.GameConfig = _Games([LockedGame(True)])  # type: ignore[assignment]
        try:
            plugin.precheck_locks()
        except PluginPrecheckError:
            pass
        else:
            raise AssertionError("已锁定的本类游戏配置应拦截预检")
    finally:
        Config.GameConfig = previous


def test_enable_before_activate_injects_class() -> None:
    plugin = _plugin(LifecycleContext.NORMAL, "demo-inject")
    games = SimpleNamespace(
        activation_state=NodeState.INACTIVE,
        _entry_types={},
    )

    class _Plugin:
        game_types: dict = {}

    class _Config:
        GameConfig = games

    import app.core as core
    import app.core.plugin_manager as plugin_manager

    previous_config = core.Config
    previous_plugin = plugin_manager.Plugin
    core.Config = _Config()  # type: ignore[misc]
    plugin_manager.Plugin = _Plugin()  # type: ignore[misc]
    try:
        asyncio.run(plugin.system_enable())
        assert games._entry_types["DemoGame"] is DemoGame
        assert plugin._system_rollback is not None
        assert plugin._system_rollback.game_type_added is True
        assert plugin_manager.Plugin.game_types[plugin._test_record.uid] is plugin.decl
    finally:
        core.Config = previous_config
        plugin_manager.Plugin = previous_plugin


def test_reload_disable_does_not_remove_type() -> None:
    plugin = _plugin(LifecycleContext.RELOAD, "demo-reload")
    uid = plugin._test_record.uid

    class Games:
        def remove_type(self, _entry_type: object) -> None:
            raise AssertionError("重载禁用不得 remove_type")

    class _Plugin:
        game_types = {uid: plugin.decl}

    class _Config:
        GameConfig = Games()

    import app.core as core
    import app.core.plugin_manager as plugin_manager

    previous = core.Config
    previous_plugin = plugin_manager.Plugin
    core.Config = _Config()  # type: ignore[misc]
    plugin_manager.Plugin = _Plugin()  # type: ignore[misc]
    try:
        asyncio.run(plugin.system_disable())
        # 重载禁用保留目录，供随后 enable 覆盖
        assert uid in plugin_manager.Plugin.game_types
    finally:
        core.Config = previous
        plugin_manager.Plugin = previous_plugin


def test_disable_removes_type_then_catalog_then_snapshot() -> None:
    """禁用顺序：类型表 → Plugin.game_types → 清 _system_rollback。"""
    from app.plugin.base.game import _SystemRollback

    plugin = _plugin(LifecycleContext.NORMAL, "demo-disable-order")
    uid = plugin._test_record.uid
    plugin._system_rollback = _SystemRollback(
        lifecycle=LifecycleContext.NORMAL, game_type_added=True
    )
    steps: list[str] = []

    class Games:
        activation_state = NodeState.ACTIVE

        def remove_type(self, entry_type: object) -> None:
            steps.append(f"remove:{getattr(entry_type, '__name__', entry_type)}")

        async def commit(self) -> None:
            steps.append("commit")

    catalog: dict = {uid: plugin.decl}

    class _PluginMgr:
        game_types = catalog

    class _Config:
        GameConfig = Games()

    import app.core as core
    import app.core.plugin_manager as plugin_manager

    previous = core.Config
    previous_plugin = plugin_manager.Plugin
    core.Config = _Config()  # type: ignore[misc]
    plugin_manager.Plugin = _PluginMgr()  # type: ignore[misc]
    try:
        asyncio.run(plugin.system_disable())
    finally:
        core.Config = previous
        plugin_manager.Plugin = previous_plugin
    assert steps == ["remove:DemoGame", "commit"]
    assert uid not in catalog
    assert plugin._system_rollback is None


def test_enabling_normal_rollback_type_then_catalog() -> None:
    """启用失败回滚：先卸类型表，再摘目录，最后清快照。"""
    from app.plugin.base.game import _SystemRollback

    plugin = _plugin(LifecycleContext.NORMAL, "demo-enabling-rb")
    uid = plugin._test_record.uid
    plugin._system_rollback = _SystemRollback(
        lifecycle=LifecycleContext.NORMAL, game_type_added=True
    )
    steps: list[str] = []
    catalog: dict = {uid: plugin.decl}

    class Games:
        activation_state = NodeState.ACTIVE

        def remove_type(self, entry_type: object) -> None:
            steps.append(f"remove:{getattr(entry_type, '__name__', entry_type)}")

        async def commit(self) -> None:
            steps.append("commit")

    class _PluginMgr:
        game_types = catalog

    class _Config:
        GameConfig = Games()

    import app.core as core
    import app.core.plugin_manager as plugin_manager

    previous = core.Config
    previous_plugin = plugin_manager.Plugin
    core.Config = _Config()  # type: ignore[misc]
    plugin_manager.Plugin = _PluginMgr()  # type: ignore[misc]
    try:
        asyncio.run(
            plugin.system_rollback(
                PluginState.ENABLING,
                LifecycleContext.NORMAL,
                RuntimeError("boom"),
            )
        )
    finally:
        core.Config = previous
        plugin_manager.Plugin = previous_plugin
    assert steps == ["remove:DemoGame", "commit"]
    assert uid not in catalog
    assert plugin._system_rollback is None


def test_enabling_reload_rollback_restores_class() -> None:
    from app.plugin.base.game import _SystemRollback

    plugin = _plugin(LifecycleContext.RELOAD, "demo-rollback")
    uid = plugin._test_record.uid
    previous_cls = type("OldDemoGame", (), {})
    plugin._system_rollback = _SystemRollback(
        lifecycle=LifecycleContext.RELOAD,
        prev_game_class=cast(type[GameEntry], previous_cls),
    )
    calls: list[object] = []
    catalog: dict = {uid: plugin.decl}

    class Games:
        activation_state = NodeState.ACTIVE

        def values(self) -> list[object]:
            return []

        def reload_type(self, entry_type: object) -> None:
            calls.append(entry_type)

        def remove_type(self, _entry_type: object) -> None:
            raise AssertionError("重载回滚不得 remove_type 游戏主配置")

        async def commit(self) -> None:
            return None

    class _PluginMgr:
        game_types = catalog

    class _Config:
        GameConfig = Games()

    import app.core as core
    import app.core.plugin_manager as plugin_manager

    previous = core.Config
    previous_plugin = plugin_manager.Plugin
    core.Config = _Config()  # type: ignore[misc]
    plugin_manager.Plugin = _PluginMgr()  # type: ignore[misc]
    try:
        asyncio.run(
            plugin.system_rollback(
                PluginState.ENABLING,
                LifecycleContext.RELOAD,
                RuntimeError("boom"),
            )
        )
    finally:
        core.Config = previous
        plugin_manager.Plugin = previous_plugin
    assert calls == [previous_cls]
    assert uid not in catalog
    assert plugin._system_rollback is None


def test_reload_enable_swaps_device_by_remove_add() -> None:
    """reload 启用时设备类走 remove + add，不走 reload_type。"""
    plugin = _plugin(LifecycleContext.RELOAD, "demo-swap")
    device_ops: list[str] = []
    old_device = type("OldDevice", (), {})

    class _Devices:
        def __init__(self) -> None:
            self._entry_types: dict[str, type] = {"OldDevice": old_device}

        @property
        def effective(self) -> _Devices:
            return self

        def list_entry_types(self) -> list[dict[str, str]]:
            return [{"name": n} for n in self._entry_types]

        def remove_type(self, entry_type: object) -> None:
            device_ops.append(f"remove:{getattr(entry_type, '__name__', entry_type)}")
            name = getattr(entry_type, "__name__", "")
            self._entry_types.pop(name, None)

        def add_type(self, entry_type: type) -> None:
            device_ops.append(f"add:{entry_type.__name__}")
            self._entry_types[entry_type.__name__] = entry_type

        def reload_type(self, _entry_type: object) -> None:
            device_ops.append("reload")
            raise AssertionError("设备类不得 reload_type")

        async def commit(self) -> None:
            return None

    entry = DemoGame()
    object.__setattr__(entry, "devices", _Devices())
    entry._game_control = None

    class Games:
        activation_state = NodeState.ACTIVE
        effective = SimpleNamespace(_entry_types={"DemoGame": DemoGame})

        def values(self) -> list[object]:
            return [entry]

        def reload_type(self, _entry_type: object) -> None:
            return None

        async def commit(self) -> None:
            return None

    class _Plugin:
        game_types: dict = {}

    class _Config:
        GameConfig = Games()

    import app.core as core
    import app.core.plugin_manager as plugin_manager

    previous_config = core.Config
    previous_plugin = plugin_manager.Plugin
    core.Config = _Config()  # type: ignore[misc]
    plugin_manager.Plugin = _Plugin()  # type: ignore[misc]
    try:
        asyncio.run(plugin.system_enable())
    finally:
        core.Config = previous_config
        plugin_manager.Plugin = previous_plugin
    assert "remove:OldDevice" in device_ops
    assert f"add:{DemoDevice.__name__}" in device_ops
    assert "reload" not in device_ops


def test_search_returns_catalog_and_keeps_instances() -> None:
    from app.core.game_manager import GameManager

    class Found:
        def __init__(self) -> None:
            self.uid = uuid4()
            self.info = SimpleNamespace(
                name="MuMu",
                type="emulator",
                concurrent_execution=False,
            )

    row = Found()

    async def search() -> list[Found]:
        return [row]

    decl = GameTypeDecl(
        game_class=DemoGame,
        device_class=DemoDevice,
        control_class=_Ctrl,
        search=search,
    )

    class _Plugin:
        game_types = {uuid4(): decl}

    import app.core.plugin_manager as plugin_manager

    previous = plugin_manager.Plugin
    previous_found = GameManager._found
    plugin_manager.Plugin = _Plugin()  # type: ignore[misc]
    try:
        catalog = asyncio.run(GameManager.search())
        assert catalog[str(row.uid)] == {
            "name": "MuMu",
            "type": "emulator",
            "concurrent_execution": False,
        }
        assert GameManager._found[row.uid] is row
    finally:
        plugin_manager.Plugin = previous
        GameManager._found = previous_found


def test_add_found_add_then_update() -> None:
    """搜索缓存入库：add 占位 + update 同步已赋值 Group。"""
    from app.core import Config
    from app.core.game_manager import GameManager
    import app.core.plugin_manager as plugin_manager

    found = DemoGame(info=DemoGame.Info(name="MuMu", type="emulator"))
    uid = found.uid
    col = ConfigCollection[GameEntry]([GameEntry, DemoGame])
    decl = GameTypeDecl(
        game_class=DemoGame,
        device_class=DemoDevice,
        control_class=_Ctrl,
        search=_empty_search,
    )

    class _Plugin:
        game_types = {uuid4(): decl}

    previous_config = Config.GameConfig
    previous_plugin = plugin_manager.Plugin
    previous_found = dict(GameManager._found)

    async def run() -> None:
        await col.activate()
        col.connect(GameManager.on_add, phase="both", kind="add")
        Config.GameConfig = col  # type: ignore[assignment]
        plugin_manager.Plugin = _Plugin()  # type: ignore[misc]
        GameManager._found = {uid: found}
        entry = await GameManager.add_found(uid)
        assert entry.uid == uid
        assert entry.info.name == "MuMu"
        assert entry._game_control is not None
        assert uid not in GameManager._found

    try:
        asyncio.run(run())
    finally:
        Config.GameConfig = previous_config
        plugin_manager.Plugin = previous_plugin
        GameManager._found = previous_found


def test_add_found_missing_raises() -> None:
    from app.core.game_manager import GameManager

    previous_found = dict(GameManager._found)
    GameManager._found = {}
    try:
        asyncio.run(GameManager.add_found(uuid4()))
    except KeyError:
        pass
    else:
        raise AssertionError("缺失搜索 uid 应上抛 KeyError")
    finally:
        GameManager._found = previous_found


def test_script_reload_uses_reload_type() -> None:
    from app.models.config import ScriptEntry, UserEntry
    from app.plugin.base.script import ScriptAdapterPlugin, ScriptTypeDecl
    from app.task import UserExpander

    class DemoUser(UserEntry):
        pass

    class Item(ScriptEntry):
        # users 的类型域由类体收窄（见 ScriptAdapterPlugin._validate_decl）
        users: ConfigCollection[DemoUser] = collection(DemoUser)

    class DemoManager(UserExpander):
        pass

    class Col:
        # 桩集合：只记调用序，activation_state 装 ACTIVE 以走热态分支
        activation_state = NodeState.ACTIVE

        def __init__(self) -> None:
            self.calls: list[str] = []

        @property
        def effective(self) -> "Col":
            return self

        _entry_types: dict[str, type] = {}

        def reload_type(self, _entry_type: object) -> None:
            self.calls.append("reload")

        def add_type(self, _entry_type: object) -> None:
            self.calls.append("add")

        def remove_type(self, _entry_type: object) -> None:
            self.calls.append("remove")

        async def commit(self) -> None:
            return None

        def values(self) -> list[object]:
            return []

        def connect(self, *_a: object, **_k: object) -> None:
            return None

    col = Col()

    class _Config:
        ScriptConfig = col
        PlanConfig = col

    class _Plugin:
        script_types: dict[UUID, object] = {}

    class Demo(ScriptAdapterPlugin):
        script_type_key = "demo-script"
        decl = ScriptTypeDecl(
            entry_type=Item,
            user_type=DemoUser,
            expander_class=DemoManager,
        )

    record = _record(LifecycleContext.RELOAD, "demo-script")
    plugin = Demo(record=record)
    plugin._test_record = record

    import app.core as core
    import app.core.plugin_manager as plugin_manager

    previous_config = core.Config
    previous_plugin = plugin_manager.Plugin
    core.Config = _Config()  # type: ignore[misc]
    plugin_manager.Plugin = _Plugin()  # type: ignore[misc]
    try:
        asyncio.run(plugin.system_enable())
    finally:
        core.Config = previous_config
        plugin_manager.Plugin = previous_plugin
    assert col.calls == ["reload"]
    assert _Plugin.script_types[record.uid] is Demo.decl


def test_three_game_adapters_declare_type() -> None:
    core_src = _PLUGINS / "auto_mas_core" / "src"
    paths = [
        str(core_src),
        str(_PLUGINS / "win_process_adapter" / "src"),
        str(_PLUGINS / "mumu_adapter" / "src"),
        str(_PLUGINS / "ldplayer_adapter" / "src"),
    ]
    for p in reversed(paths):
        sys.path.insert(0, p)
    try:
        from ldplayer_adapter import PLUGIN as LDPLUGIN
        from ldplayer_adapter.handle import LDPlayerControl
        from mumu_adapter import PLUGIN as MuMuPLUGIN
        from mumu_adapter.control import MuMuControl
        from win_process_adapter import PLUGIN as WinPLUGIN
        from win_process_adapter.handle import WinProcessControl

        for plugin, key, control in (
            (WinPLUGIN, "general", WinProcessControl),
            (MuMuPLUGIN, "mumu", MuMuControl),
            (LDPLUGIN, "ldplayer", LDPlayerControl),
        ):
            assert plugin.game_type_key == key
            assert plugin.decl is not None
            assert plugin.decl.game_class is not None
            assert plugin.decl.device_class is not None
            assert plugin.decl.control_class is control
            assert callable(plugin.decl.search)
            assert issubclass(control, GameControl)
    finally:
        for p in paths:
            while p in sys.path:
                sys.path.remove(p)
