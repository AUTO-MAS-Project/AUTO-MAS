from inspect import signature
from types import SimpleNamespace
from typing import Any, get_type_hints

from app.plugin.base import (
    BasePlugin,
    ExtensionPlugin,
    GameAdapterPlugin,
    GameControl,
    GameTypeDecl,
    ScriptAdapterPlugin,
    UserExpander,
    ScriptTypeDecl,
)
from app.plugin.types import LifecycleContext, PluginState


def test_base_plugin_exposes_only_common_lifecycle() -> None:
    assert not hasattr(BasePlugin, "system_enable")
    assert not hasattr(BasePlugin, "system_disable")
    assert not hasattr(BasePlugin, "system_rollback")
    assert not hasattr(BasePlugin, "on_load")
    assert not hasattr(BasePlugin, "contributed_script_types")
    assert not hasattr(BasePlugin, "contributed_game_types")
    assert hasattr(ExtensionPlugin, "system_enable")
    assert hasattr(ExtensionPlugin, "system_disable")
    assert hasattr(ExtensionPlugin, "system_rollback")


def test_fail_cleanup_signatures_take_during_and_lifecycle_context() -> None:
    """回退钩子拿到叶子 during + record 快照 lifecycle_context。"""
    user = signature(BasePlugin.on_fail_cleanup)
    assert list(user.parameters)[1:] == ["during", "lifecycle_context", "exc"]
    user_hints = get_type_hints(BasePlugin.on_fail_cleanup)
    assert user_hints["during"] is PluginState
    assert user_hints["lifecycle_context"] is LifecycleContext

    sys = signature(ExtensionPlugin.system_rollback)
    assert list(sys.parameters)[1:] == ["during", "lifecycle_context", "exc"]
    sys_hints = get_type_hints(ExtensionPlugin.system_rollback)
    assert sys_hints["during"] is PluginState
    assert sys_hints["lifecycle_context"] is LifecycleContext


def test_base_plugin_takes_config_in_constructor() -> None:
    p = BasePlugin(config=None)
    assert p.config is None
    try:
        _ = p.record
    except RuntimeError:
        pass
    else:
        raise AssertionError("未注入 record 时应上抛")


def test_plugin_holds_record_weakly() -> None:
    import gc
    import weakref

    from app.plugin.types import LifecycleContext

    class _Record:
        pass

    record: Any = _Record()
    record.info = SimpleNamespace(
        lifecycle_context=LifecycleContext.RELOAD, plugin_name="demo"
    )
    plugin = BasePlugin(record=record)
    assert plugin.lifecycle_context is LifecycleContext.RELOAD
    assert plugin.plugin_name == "demo"
    ref = weakref.ref(record)
    del record
    gc.collect()
    assert ref() is None
    try:
        _ = plugin.record
    except RuntimeError:
        pass
    else:
        raise AssertionError("注册表项回收后访问 record 应上抛")
    try:
        _ = plugin.lifecycle_context
    except RuntimeError:
        pass
    else:
        raise AssertionError("注册表项回收后访问 lifecycle_context 应上抛")


def test_adapter_declarations_are_class_level() -> None:
    from app.models.config import GameDeviceEntry, GameEntry, ScriptEntry, UserEntry

    async def _search() -> list[GameEntry]:
        return []

    class DemoScript(ScriptEntry):
        pass

    class DemoUser(UserEntry):
        pass

    class DemoManager(UserExpander):
        pass

    class Script(ScriptAdapterPlugin):
        script_type_key = "demo"
        decl = ScriptTypeDecl(
            entry_type=DemoScript,
            user_type=DemoUser,
            expander_class=DemoManager,
        )

    class Game(GameAdapterPlugin):
        game_type_key = "demo-game"
        decl = GameTypeDecl(
            game_class=GameEntry,
            device_class=GameDeviceEntry,
            control_class=GameControl,
            search=_search,
        )

    # 两种适配同形：声明都是类级 ``decl``，不再有脚本侧的散装 ClassVar
    assert Script.script_type_key == "demo"
    assert Script.decl is not None
    assert Script.decl.entry_type is DemoScript
    assert Script.decl.user_type is DemoUser
    assert Script.decl.expander_class is DemoManager
    assert Script.decl.plan_entry_type is None
    assert Script.decl.supported_modes
    assert Game.game_type_key == "demo-game"
    assert Game.decl is not None
    assert Game.decl.game_class is GameEntry
    assert Game.decl.device_class is GameDeviceEntry
    assert callable(Game.decl.search)
    assert ScriptAdapterPlugin.decl is None
    assert ScriptAdapterPlugin.script_type_key == ""
    assert GameAdapterPlugin.game_type_key == ""
    assert GameAdapterPlugin.decl is None
