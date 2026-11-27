"""游戏页动作提示：「记录配置守卫基准」跟着插件是否实现守卫走，不按模拟器类型。"""

import pytest

from app.api.games import _action_hints
from app.config import ConfigCollection, config_manager
from app.core import Config
from app.core.game_manager import _GameManager
from app.plugin.base.emulator import EmulatorControl

control_module = pytest.importorskip("ldplayer_adapter.control")
from ldplayer_adapter.config import LDPlayerDevice, LDPlayerGame  # noqa: E402


class GuardedAvd(control_module.Control):
    """品牌为 ModAVD、仍带配置守卫的控制器（相当于 ModAVD 适配 0.1.1）。"""

    kind = "avd"


class UnguardedAvd(control_module.Control):
    """品牌为 ModAVD、已去掉配置守卫的控制器（相当于 ModAVD 适配 0.1.2）。"""

    kind = "avd"
    capture_baseline = EmulatorControl.capture_baseline


def fields(hints, uid):
    return {hint["field"] for hint in hints[str(uid)]}


@pytest.mark.asyncio
async def test_capture_hint_follows_plugin_guard_support(
    isolated_app_paths, tmp_path, monkeypatch
):
    games = ConfigCollection.build([LDPlayerGame])
    monkeypatch.setitem(config_manager._collections, "games", games)
    monkeypatch.setattr(Config, "GameConfig", games)
    executable = tmp_path / "ldconsole.exe"
    executable.touch()
    await games.activate()
    game_uid = games.add(
        LDPlayerGame,
        payload={"info": {"path": str(executable), "config_guard": True}},
    )
    await games.commit()
    game = games[game_uid]
    device = game.devices.add(LDPlayerDevice, payload={"info": {"index": "0"}})
    await game.devices.commit()
    game.info.baselines = {str(device): {"resolution_width": 1280}}
    await games.commit()

    for control_class, guarded in (
        (control_module.Control, True),
        (GuardedAvd, True),
        (UnguardedAvd, False),
    ):
        _GameManager.create_control(config=game, control_class=control_class)
        hints = _action_hints(game)
        assert ("capture" in fields(hints, game_uid)) is guarded
        # 设备上依赖实例设置能力的入口不受影响
        assert "settings" in fields(hints, device)
