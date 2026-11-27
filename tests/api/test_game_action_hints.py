"""游戏页动作提示：ModAVD 不提供配置守卫，不下发「记录配置守卫基准」。"""

import pytest

from app.api.games import _action_hints
from app.config import ConfigCollection, config_manager
from app.core import Config
from app.core.game_manager import _GameManager

control_module = pytest.importorskip("ldplayer_adapter.control")
from ldplayer_adapter.config import LDPlayerDevice, LDPlayerGame  # noqa: E402


class ModAvdLike(control_module.Control):
    """能力与雷电相同、品牌为 ModAVD 的控制器（测试环境没有 ModAVD 适配插件）。"""

    kind = "avd"


def fields(hints, uid):
    return {hint["field"] for hint in hints[str(uid)]}


@pytest.mark.asyncio
async def test_mod_avd_has_no_config_guard_capture(
    isolated_app_paths, tmp_path, monkeypatch
):
    games = ConfigCollection.build([LDPlayerGame])
    monkeypatch.setitem(config_manager._collections, "games", games)
    monkeypatch.setattr(Config, "GameConfig", games)
    executable = tmp_path / "ldconsole.exe"
    executable.touch()
    await games.activate()
    game_uid = games.add(LDPlayerGame, payload={"info": {"path": str(executable)}})
    await games.commit()
    game = games[game_uid]
    device = game.devices.add(LDPlayerDevice, payload={"info": {"index": "0"}})
    await game.devices.commit()

    for control_class, guarded in (
        (control_module.Control, True),
        (ModAvdLike, False),
    ):
        _GameManager.create_control(config=game, control_class=control_class)
        hints = _action_hints(game)
        assert ("capture" in fields(hints, game_uid)) is guarded
        # 设备上依赖实例设置能力的入口不受影响
        assert "settings" in fields(hints, device)
