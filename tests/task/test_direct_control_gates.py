"""直控来源与快速配置在各专项运行时的门控回归测试

锁住四件事：
- `proxy_helpers` 的来源归一：未知值绝不回落成直控（直控意味着 MAS 零写入，
  误判会让 MAS 静默放弃写入）。
- MAA/SRC manager 的 `_has_mas_config_user`：全直控用户时不要求脚本级 Default 存档。
- M9A manager 的 `_uses_direct_control`：直控时跳过 instances 清理（原生配置是
  直控的事实源，删了用户配置就没了）。
- OkNte：直控时下发（set_oknte）与回写（update_config）都被跳过——这是 WIP 里
  `Info.Mode` 只有模型字段、运行时零消费的那个缺口。

全部走生产代码路径，不在测试内复制一份判定逻辑（那等于自证）。
"""

import asyncio
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core import Config
from app.task.M9A.manager import M9AManager
from app.task.MAA.manager import MaaManager
from app.task.OkNte.AutoProxy import AutoProxyTask as OkNteAutoProxyTask
from app.task.proxy_helpers import (
    CONFIG_SOURCE_DIRECT,
    CONFIG_SOURCE_SCRIPT,
    CONFIG_SOURCE_USER,
    quick_config_takeover,
    read_config_source,
    resolve_config_source,
    user_uses_direct_control,
    user_uses_quick_config,
)
from app.task.SRC.manager import SrcManager
from app.task.ZzzOd.AutoProxy import AutoProxyTask as ZzzOdAutoProxyTask

UID_A = str(uuid.uuid4())
UID_B = str(uuid.uuid4())


class _TaskInfo:
    mode = "AutoProxy"


class _Cfg:
    """模拟 ConfigBase.get(group, name) 双参语义。"""

    def __init__(self, mode: Any, **extra: Any):
        self._values = {"Mode": mode, "Status": True, "RemainedDay": 1, **extra}

    def get(self, group: str, name: str) -> Any:
        key = f"{group}.{name}"
        if key in self._values:
            return self._values[key]
        if group == "Info" and name in self._values:
            return self._values[name]
        raise AttributeError(f"配置项 ‘{group}.{name}’ 不存在")


# ── proxy_helpers 来源归一 ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("脚本", CONFIG_SOURCE_SCRIPT),
        ("用户", CONFIG_SOURCE_USER),
        ("直控", CONFIG_SOURCE_DIRECT),
    ],
)
def test_read_config_source_accepts_three_states(raw: str, expected: str) -> None:
    """三态原样读出。"""

    assert read_config_source(_Cfg(raw)) == expected


@pytest.mark.parametrize("raw", ["", "  ", "Direct", None, "未知来源", "直控模式"])
def test_unknown_source_never_falls_back_to_direct(raw: Any) -> None:
    """未知/空值绝不回落成直控：直控=MAS 零写入，误判会静默放弃写入。"""

    assert read_config_source(_Cfg(raw)) != CONFIG_SOURCE_DIRECT
    assert read_config_source(_Cfg(raw)) == CONFIG_SOURCE_USER


def test_read_config_source_tolerates_missing_config() -> None:
    """配置缺失时用调用方给的默认值，不抛异常。"""

    assert read_config_source(None, CONFIG_SOURCE_SCRIPT) == CONFIG_SOURCE_SCRIPT
    assert read_config_source(object()) == CONFIG_SOURCE_USER


def test_resolve_and_direct_control_agree() -> None:
    """两个入口对同一份配置给出同一结论。"""

    direct = _Cfg("直控")
    assert resolve_config_source(direct) == (CONFIG_SOURCE_DIRECT, True)
    assert user_uses_direct_control(direct) is True
    assert user_uses_direct_control(_Cfg("用户")) is False


# ── MAA / SRC：脚本级存档要求 ───────────────────────────────────────────

SCRIPT_ID = "9f1c2d3e-4a5b-4c6d-8e7f-0a1b2c3d4e5f"


def _script_config(user_configs: dict[str, _Cfg]) -> MagicMock:
    """模拟脚本配置持久化的 UserData（check() 阶段唯一可用的数据源）。"""

    script_config = MagicMock()
    script_config.UserData.items = lambda: {
        uuid.UUID(uid): cfg for uid, cfg in user_configs.items()
    }.items()
    return script_config


def _manager(cls: type, user_configs: dict[str, _Cfg], monkeypatch: pytest.MonkeyPatch):
    """构造 manager 并把 Config.ScriptConfig 指到模拟脚本配置。

    走真实生产路径：_has_mas_config_user 读 Config.ScriptConfig[uid].UserData
    （check() 先于 prepare()，此时 self.user_config / user_list 尚未就绪）。
    """

    manager = cls.__new__(cls)
    manager.task_info = _TaskInfo()
    manager.task_info.is_target_user = lambda uid: True
    manager.script_info = MagicMock()
    manager.script_info.script_id = SCRIPT_ID
    monkeypatch.setattr(
        Config, "ScriptConfig", {uuid.UUID(SCRIPT_ID): _script_config(user_configs)}
    )
    return manager


def test_maa_has_mas_config_user_true_when_user_mode(monkeypatch) -> None:
    """存在「用户」来源用户时要求脚本级存档。"""

    manager = _manager(MaaManager, {UID_A: _Cfg("用户")}, monkeypatch)

    assert manager._has_mas_config_user() is True


def test_maa_has_mas_config_user_false_when_all_direct(monkeypatch) -> None:
    """全直控用户时不要求脚本级存档。"""

    manager = _manager(
        MaaManager, {UID_A: _Cfg("直控"), UID_B: _Cfg("直控")}, monkeypatch
    )

    assert manager._has_mas_config_user() is False


def test_maa_has_mas_config_user_true_when_mixed(monkeypatch) -> None:
    """只要有一个非直控用户，脚本级存档就是必需的。"""

    manager = _manager(
        MaaManager, {UID_A: _Cfg("直控"), UID_B: _Cfg("脚本")}, monkeypatch
    )

    assert manager._has_mas_config_user() is True


def test_src_has_mas_config_user_mirrors_maa(monkeypatch) -> None:
    """SRC 与 MAA 同构: 全直控时不要求脚本级存档。"""

    manager = _manager(SrcManager, {UID_A: _Cfg("直控")}, monkeypatch)

    assert manager._has_mas_config_user() is False


# ── M9A：直控时跳过 instances 清理 ──────────────────────────────────────


def _m9a_manager(user_configs: dict[str, Any]) -> M9AManager:
    manager = M9AManager.__new__(M9AManager)
    manager.task_info = _TaskInfo()
    manager.task_info.is_target_user = lambda uid: True
    manager.script_info = MagicMock()
    manager.user_config = {uuid.UUID(uid): cfg for uid, cfg in user_configs.items()}
    return manager


def test_m9a_uses_direct_control_true_when_any_direct_user() -> None:
    """任一参与运行的用户是直控即判为直控运行（走生产方法，不复制逻辑）。"""

    manager = _m9a_manager({UID_A: _Cfg("直控"), UID_B: _Cfg("用户")})

    assert manager._uses_direct_control() is True


def test_m9a_uses_direct_control_false_when_no_direct_user() -> None:
    """无直控用户时照常清理 instances。"""

    manager = _m9a_manager({UID_A: _Cfg("用户"), UID_B: _Cfg("脚本")})

    assert manager._uses_direct_control() is False


def test_m9a_uses_direct_control_ignores_disabled_and_zero_remain() -> None:
    """未启用/剩余天数为 0 的直控用户不参与本次运行，不应触发跳过清理。"""

    manager = _m9a_manager(
        {
            UID_A: _Cfg("直控", Status=False),
            UID_B: _Cfg("直控", RemainedDay=0),
        }
    )

    assert manager._uses_direct_control() is False


# ── OkNte：直控零写入（WIP 缺口）───────────────────────────────────────


class _OkNteScriptConfig:
    """模拟 OkNteConfig 的 Script 组读取。"""

    def __init__(self, config_path: Path, mode: str = "Folder") -> None:
        self._config_path = config_path
        self._mode = mode

    def get(self, group: str, name: str) -> Any:
        if group == "Script" and name == "ConfigPath":
            return str(self._config_path)
        if group == "Script" and name == "ConfigPathMode":
            return self._mode
        raise AttributeError(f"配置项 ‘{group}.{name}’ 不存在")


def _oknte_task(user_config: _Cfg, script_config: Any) -> OkNteAutoProxyTask:
    """构造一个只填了直控判定所需字段的 OkNte AutoProxyTask。"""

    user_config.master = user_config
    task = OkNteAutoProxyTask.__new__(OkNteAutoProxyTask)
    task.task_info = _TaskInfo()
    task.script_info = MagicMock()
    task.script_info.script_id = "script-1"
    task.script_config = script_config
    task.cur_user_item = MagicMock()
    task.cur_user_uid = uuid.UUID(UID_A)
    task.cur_user_config = user_config
    task.script_config_path = script_config.get("Script", "ConfigPath")
    task.config_mode, task.direct_control = resolve_config_source(
        user_config, CONFIG_SOURCE_SCRIPT
    )
    return task


def test_oknte_direct_skips_native_config_injection(tmp_path: Path) -> None:
    """直控+关闭：set_oknte 不注入原生配置（零写入，直控名称的来源就是「不写」）。"""

    target = tmp_path / "native_config"
    target.mkdir()
    script_config = _OkNteScriptConfig(target)
    task = _oknte_task(_Cfg("直控", IfQuickConfig=False), script_config)
    task.script_exe_path = tmp_path / "ok-nte.exe"

    with patch("app.task.OkNte.AutoProxy.System.kill_process"), patch(
        "app.task.OkNte.AutoProxy.swap_in_dir"
    ) as swap, patch("app.task.OkNte.AutoProxy.archive_mas_runtime_backup") as archive:
        asyncio.run(task.set_oknte())

    swap.assert_not_called()
    archive.assert_not_called()
    # 直控+关闭：DailyRoutine 面板子集也不得写入原生配置
    assert not (target / "DailyRoutineTask.json").exists()


def test_oknte_direct_skips_config_writeback(tmp_path: Path) -> None:
    """直控来源下 update_config 不把原生配置抄回 MAS 侧。"""

    target = tmp_path / "native_config"
    target.mkdir()
    task = _oknte_task(_Cfg("直控"), _OkNteScriptConfig(target))

    with patch("app.task.OkNte.AutoProxy.shutil.copytree") as copytree:
        asyncio.run(task.update_config())

    copytree.assert_not_called()


def test_oknte_direct_check_rejects_missing_native_config(tmp_path: Path) -> None:
    """直控且原生配置缺失时 check 提前报错，不静默启动未配置的脚本。"""

    missing = tmp_path / "not_there"
    task = _oknte_task(_Cfg("直控"), _OkNteScriptConfig(missing))

    assert task._native_config_ready() is False


def test_oknte_user_source_still_injects(tmp_path: Path) -> None:
    """非直控来源维持原有注入行为（三态里只有直控是「不写」）。"""

    target = tmp_path / "native_config"
    target.mkdir()
    task = _oknte_task(_Cfg("用户"), _OkNteScriptConfig(target))
    task.script_exe_path = tmp_path / "ok-nte.exe"

    with patch("app.task.OkNte.AutoProxy.System.kill_process"), patch(
        "app.task.OkNte.AutoProxy.archive_mas_runtime_backup"
    ), patch("app.task.OkNte.AutoProxy._oknte_daily_activity_enabled", return_value=True):
        with patch("app.task.OkNte.AutoProxy.swap_in_dir") as swap, patch(
            "app.task.OkNte.AutoProxy.mark_native_config_injected"
        ), patch("app.task.OkNte.AutoProxy.ensure_oknte_daily_routine_configs"):
            task._ensure_oknte_mas_config_dir = MagicMock(return_value=tmp_path / "mas")
            asyncio.run(task.set_oknte())

    swap.assert_called_once()


# ── 快速配置开关与接管统一入口（核心层）──────────────────────────────────


def _qc_cfg(mode: Any, quick: Any = True) -> _Cfg:
    """构造带 Mode + IfQuickConfig 的用户配置。"""

    return _Cfg(mode, IfQuickConfig=quick)


def test_user_uses_quick_config_is_source_independent() -> None:
    """开关按用户保存、与来源完全独立：任一来源下都能读且不随来源变化。"""

    assert user_uses_quick_config(_qc_cfg("直控")) is True
    assert user_uses_quick_config(_qc_cfg("用户", False)) is False
    assert user_uses_quick_config(_qc_cfg("脚本", False)) is False
    assert user_uses_quick_config(_qc_cfg("直控", False)) is False


def test_user_uses_quick_config_defaults_on_when_missing() -> None:
    """字段缺失/配置缺失时默认开启（与模型层 BoolValidator 默认一致）。"""

    assert user_uses_quick_config(_Cfg({"Mode": "用户"})) is True
    assert user_uses_quick_config(None, default=False) is False
    assert user_uses_quick_config(object()) is True


def test_quick_config_takeover_writes_only_direct_plus_enabled() -> None:
    """接管统一入口：只有 直控+开启 才写面板值；直控+关闭与脚本/用户零写入。

    不存在「直控=禁用快速配置」的旧早退分支——直控下是否写入完全由开关决定。
    """

    calls: list[str] = []

    def write() -> None:
        calls.append("write")

    assert quick_config_takeover(_qc_cfg("直控"), write) is True
    assert quick_config_takeover(_qc_cfg("直控", False), write) is False
    assert quick_config_takeover(_qc_cfg("用户"), write) is False
    assert quick_config_takeover(_qc_cfg("脚本"), write) is False
    assert calls == ["write"]


def test_quick_config_takeover_write_failure_is_task_failure() -> None:
    """覆写失败即任务失败：write 抛错必须向上传播，不得吞异常假装成功。"""

    class Boom(RuntimeError):
        pass

    def broken_write() -> None:
        raise Boom("写入原生配置失败")

    with pytest.raises(Boom):
        quick_config_takeover(_qc_cfg("直控"), broken_write)




# ── ZzzOd：脚本来源被 check() 接受并按用户路径校验 ───────────────────────


def test_zzzod_check_accepts_script_source(tmp_path: Path) -> None:
    """脚本来源不再被 check() 白名单拒绝，走与用户来源相同的注入校验。"""

    task = ZzzOdAutoProxyTask.__new__(ZzzOdAutoProxyTask)
    task.script_config = MagicMock()
    task.script_config.get.side_effect = lambda group, name: {
        ("Info", "RootPath"): tmp_path,
        ("Run", "ProxyTimesLimit"): 0,
    }.get((group, name), "")
    task.script_info = MagicMock()
    task.user_config = {}
    task.cur_user_config = _Cfg(
        "脚本",
        RemainedDay=5,
        **{"OneDragon.AppList": '[{"app_id": "daily", "enabled": true}]'},
    )
    task.cur_user_item = MagicMock()
    task.mode = CONFIG_SOURCE_SCRIPT
    task._reset_daily_proxy_count = AsyncMock()

    with patch(
        "app.task.ZzzOd.AutoProxy.find_launcher_exe", return_value=Path("launcher.exe")
    ):
        result = asyncio.run(task.check())

    assert result == "Pass"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))