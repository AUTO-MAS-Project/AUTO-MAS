"""插件生命周期钩子到宿主脚本配置契约的转接检查。"""

from pathlib import Path
from typing import Any

import pytest

from app.core.plugin.manager import _PluginManager
from app.models.script_contracts import ScriptConfigHandler


class _Gate:
    """最小调用门：直接执行，不做启用态检查。"""

    def wrap(self, func):
        return func


class _Decl:
    supports_mod_avd = False
    game_kinds = ("client",)


class _Plugin:
    """覆盖了保存校验、导入与初始化三个钩子的最小插件。"""

    seen: list[tuple[str, Any]] = []

    def validate_update(self, data: dict[str, Any]) -> None:
        if data.get("bad"):
            raise ValueError("拒绝保存")

    async def import_config(self, script, target_directory, *, user_id=None):
        self.seen.append(("import_config", user_id))

    async def initialize(self, script):
        self.seen.append(("initialize", script))


def _handler(plugin, overridden):
    return _PluginManager._wrap_script_hooks(
        ScriptConfigHandler, _Decl(), plugin, _Gate(), overridden
    )


def test_validate_update_runs_sync_and_raises():
    """宿主保存前是同步调用，插件报错要原样抛出来。"""
    handler = _handler(_Plugin(), {"validate_update"})
    assert handler.validate_update is not None
    handler.validate_update({"Game": {"LauncherPath": "x"}})
    with pytest.raises(ValueError, match="拒绝保存"):
        handler.validate_update({"bad": True})


def test_coroutine_validate_update_is_rejected():
    """写成协程会被静默丢掉，所以转接层要直接报配置错误。"""

    class _AsyncPlugin(_Plugin):
        async def validate_update(self, data: dict[str, Any]) -> None:
            return None

    handler = _handler(_AsyncPlugin(), {"validate_update"})
    with pytest.raises(RuntimeError, match="同步实现"):
        handler.validate_update({})


@pytest.mark.asyncio
async def test_import_config_and_initialize_are_awaited():
    plugin = _Plugin()
    plugin.seen = []
    handler = _handler(plugin, {"import_config", "initialize"})
    await handler.import_config(None, Path("/tmp/x"), user_id="u1")
    await handler.initialize("script")
    assert plugin.seen == [("import_config", "u1"), ("initialize", "script")]
