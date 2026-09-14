"""直控+快速配置接管与开关门控的专项运行时回归测试（t3）

锁住 S3/S4/S5 的专项落地（缺口专项 + Okww F13 修复），全部走生产代码路径：

- Okww F13：直控下（开关开与关）Basic Options.json 写入次数必须为 0；
  直控+开启只写 DailyTask.json 快速配置子集；脚本/用户来源保持现状。
- MaaFW：直控+开启=build_plan 应用用户托管值（任务快照/预设）；
  直控+关闭=纯 interface 默认。
- OkNte：直控+开启=DailyRoutine 面板子集写入原生 working 配置；
  直控+关闭=零写入。
- ZzzOd：直控+开启=用户面板字段写入绑定实例槽（备份→注入→恢复）；
  直控+关闭=裸跑零写入。
"""

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.task.OkNte.AutoProxy import AutoProxyTask as OkNteAutoProxyTask
from app.task.Okww.AutoProxy import AutoProxyTask as OkwwAutoProxyTask
from app.task.proxy_helpers import CONFIG_SOURCE_SCRIPT, resolve_config_source
from app.task.ZzzOd.AutoProxy import AutoProxyTask as ZzzOdAutoProxyTask
from app.task.ZzzOd.tools import instance_dir

UID_A = str(uuid.uuid4())


class _Cfg:
    """模拟 ConfigBase.get(group, name) 双参语义 + 直控/快速配置字段。"""

    def __init__(self, mode: Any, quick: Any = True, **extra: Any):
        self._values = {"Mode": mode, "IfQuickConfig": quick, **extra}

    def get(self, group: str, name: str) -> Any:
        if group == "Info" and name in self._values:
            return self._values[name]
        if group == "Task" and name in self._values:
            return self._values[name]
        raise AttributeError(f"配置项 ‘{group}.{name}’ 不存在")


# ── Okww F13：直控下 Basic Options.json 零写入 ──────────────────────────


def _okww_task(mode: str, quick: bool) -> OkwwAutoProxyTask:
    task = OkwwAutoProxyTask.__new__(OkwwAutoProxyTask)
    task.cur_user_config = _Cfg(
        mode,
        quick,
        WhichToFarm="无",
        WhichTacetSuppressionToFarm="无",
        WhichForgeryChallengeToFarm="无",
        MaterialSelection="无",
        FarmNightmareNestForDailyEcho=False,
        AdditionalTasks="[]",
    )
    task.script_config_path = Path("__never_created__")
    return task


def test_okww_direct_closed_writes_nothing(tmp_path: Path) -> None:
    """直控+关闭：Basic Options.json 与 DailyTask.json 都零写入（F13）。"""

    task = _okww_task("直控", quick=False)
    task.script_config_path = tmp_path / "configs"

    task._apply_mas_overrides()

    assert not (tmp_path / "configs").exists()


def test_okww_direct_quick_writes_only_daily_task(tmp_path: Path) -> None:
    """直控+开启：只写 DailyTask.json 快速配置子集，Basic Options.json 零写入。"""

    task = _okww_task("直控", quick=True)
    task.script_config_path = tmp_path / "configs"

    task._apply_mas_overrides()

    assert not (tmp_path / "configs" / "Basic Options.json").exists()
    daily = json.loads((tmp_path / "configs" / "DailyTask.json").read_text(encoding="utf-8"))
    assert daily["Which to Farm"] == "无"


def test_okww_user_source_still_writes_basic_options(tmp_path: Path) -> None:
    """脚本/用户来源保持现状：Basic Options.json 照常写入（非直控不受 F13 影响）。"""

    task = _okww_task("用户", quick=False)
    task.script_config_path = tmp_path / "configs"

    task._apply_mas_overrides()

    basic = json.loads(
        (tmp_path / "configs" / "Basic Options.json").read_text(encoding="utf-8")
    )
    assert basic["Exit App when Game Exits"] is True


# ── MaaFW：直控+开启=build_plan 应用用户托管值 ───────────────────────────


class _MaaFWScriptConfig:
    def get(self, group: str, name: str) -> Any:
        if group == "Info":
            return {"Controller": "", "Resource": ""}.get(name, "")
        if group == "Emulator":
            return "-" if name == "Id" else ""
        raise AttributeError(f"配置项 ‘{group}.{name}’ 不存在")


class _MaaFWUserConfig:
    def __init__(self, mode: str, quick: bool, snapshot: str = "", preset: str = "") -> None:
        self._mode = mode
        self._quick = quick
        self._snapshot = snapshot
        self._preset = preset

    def get(self, group: str, name: str) -> Any:
        if group == "Info":
            return {
                "Mode": self._mode,
                "IfQuickConfig": self._quick,
            }.get(name, "")
        if group == "Task":
            return {
                "TaskSnapshot": self._snapshot,
                "SelectedPreset": self._preset,
            }.get(name, "")
        raise AttributeError(f"配置项 ‘{group}.{name}’ 不存在")


def _maafw_task(mode: str, quick: bool, **task_fields: Any) -> Any:
    from app.task.MaaFW.tools.embedded.runner_task import MaaFWPluginAutoProxyTask

    task = MaaFWPluginAutoProxyTask.__new__(MaaFWPluginAutoProxyTask)
    task.cur_user_config = _MaaFWUserConfig(mode, quick, **task_fields)
    task.script_config = _MaaFWScriptConfig()
    task.project_path = Path("__project__")
    return task


def test_maafw_direct_closed_builds_interface_defaults() -> None:
    """直控+关闭：build_plan 不带用户任务快照/预设（纯 interface 默认）。"""

    from app.task.MaaFW.tools.core.automas_maafw_runner.service import (
        MaaFWRunnerService,
    )

    task = _maafw_task("直控", quick=False)
    interface = MagicMock()
    interface.controller = []
    interface.resource = []
    with patch.object(MaaFWRunnerService, "build_plan", return_value=MagicMock()) as bp:
        task._build_run_plan(interface)

    assert bp.call_count == 1
    kwargs = bp.call_args.kwargs
    assert kwargs.get("task_snapshot") is None
    assert kwargs.get("selected_preset") is None


def test_maafw_direct_quick_applies_user_values() -> None:
    """直控+开启：build_plan 应用用户托管值（任务快照/预设），与脚本/用户来源同路径。"""

    from app.task.MaaFW.tools.core.automas_maafw_runner.service import (
        MaaFWRunnerService,
    )

    task = _maafw_task(
        "直控", quick=True, snapshot='{"daily": {"enabled": true}}', preset=""
    )
    interface = MagicMock()
    interface.controller = []
    interface.resource = []
    with patch.object(MaaFWRunnerService, "build_plan", return_value=MagicMock()) as bp:
        task._build_run_plan(interface)

    kwargs = bp.call_args.kwargs
    assert kwargs.get("task_snapshot") == {"daily": {"enabled": True}}


# ── OkNte：直控+开启=DailyRoutine 面板子集写入原生 working 配置 ─────────


class _OkNteScriptConfig:
    """模拟 OkNteConfig 的 Script 组读取（Folder 模式）。"""

    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path

    def get(self, group: str, name: str) -> Any:
        if group == "Script" and name == "ConfigPath":
            return str(self._config_path)
        if group == "Script" and name == "ConfigPathMode":
            return "Folder"
        raise AttributeError(f"配置项 ‘{group}.{name}’ 不存在")


def _oknte_task(user_config: _Cfg, script_config: Any) -> OkNteAutoProxyTask:
    task = OkNteAutoProxyTask.__new__(OkNteAutoProxyTask)
    task.task_info = MagicMock()
    task.script_info = MagicMock()
    task.script_info.script_id = "script-1"
    task.script_config = script_config
    task.cur_user_item = MagicMock()
    task.cur_user_uid = uuid.UUID(UID_A)
    task.cur_user_config = user_config
    task.script_config_path = Path(script_config.get("Script", "ConfigPath"))
    task.config_mode, task.direct_control = resolve_config_source(
        user_config, CONFIG_SOURCE_SCRIPT
    )
    return task


def test_oknte_direct_quick_writes_panel_subset(tmp_path: Path) -> None:
    """直控+开启：把该用户 DailyRoutine 面板子集写入原生 working 配置（不整目录下发）。"""

    native = tmp_path / "native_configs"
    native.mkdir()
    (native / "DailyRoutineTask.json").write_text(
        json.dumps(
            {"Routine Items": [{"id": "daily_anomaly", "enabled": False}], "Exit After Task": True},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    mas_dir = tmp_path / "mas_user"
    mas_dir.mkdir(parents=True)
    (mas_dir / "DailyRoutineTask.json").write_text(
        json.dumps(
            {"Routine Items": [{"id": "daily_anomaly", "enabled": True}], "Exit After Task": False},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    task = _oknte_task(_Cfg("直控", quick=True), _OkNteScriptConfig(native))
    task.script_exe_path = tmp_path / "ok-nte.exe"
    task._ensure_oknte_mas_config_dir = MagicMock(return_value=mas_dir)  # type: ignore[method-assign]

    with patch("app.task.OkNte.AutoProxy.System.kill_process"), patch(
        "app.task.OkNte.AutoProxy.swap_in_dir"
    ) as swap, patch("app.task.OkNte.AutoProxy.archive_mas_runtime_backup") as archive:
        asyncio.run(task.set_oknte())

    swap.assert_not_called()
    archive.assert_not_called()
    data = json.loads((native / "DailyRoutineTask.json").read_text(encoding="utf-8"))
    assert data["Routine Items"][0]["enabled"] is True
    assert data["Exit After Task"] is False


# ── ZzzOd：直控+开启=面板字段写入绑定实例槽，任务后恢复 ──────────────────


class _ZzzOdCfg:
    """模拟 ZzzOdUserConfig：绑定槽 + 一条龙任务编排 + Game 字段。"""

    def __init__(self, slot_idx: int = 1, app_list: str = "[]") -> None:
        self._values: dict[str, Any] = {"Info.SlotIdx": slot_idx, "OneDragon.AppList": app_list}

    def get(self, group: str, name: str) -> Any:
        key = f"{group}.{name}"
        if key in self._values:
            return self._values[key]
        if group == "Game":
            return True if name == "UseCustomWinTitle" else ""
        return ""

    async def set(self, group: str, name: str, value: Any) -> None:
        self._values[f"{group}.{name}"] = value


def test_zzzod_direct_quick_injects_bound_slot_and_restores(tmp_path: Path) -> None:
    """直控+开启：用户面板字段（Game/OneDragon）写入绑定实例槽；恢复后现场清空。"""

    root = tmp_path / "zzzod"
    root.mkdir()
    user_item = MagicMock()
    user_item.name = "用户A"
    task = ZzzOdAutoProxyTask.__new__(ZzzOdAutoProxyTask)
    task.script_root_path = root
    task.script_info = MagicMock()
    task.script_info.script_id = "script-1"
    task.cur_user_uid = uuid.UUID(UID_A)
    task.cur_user_item = user_item
    task.cur_user_config = _ZzzOdCfg(
        slot_idx=1, app_list='[{"app_id": "daily", "enabled": true}]'
    )
    task._injected_slots = []
    task._slot_users = {}
    task._slot_records_before = {}

    with patch("app.task.ZzzOd.AutoProxy.collect_used_slot_idxs", return_value=set()):
        asyncio.run(task._prepare_direct_quick_config())

    slot_dir = instance_dir(root, 1)
    assert (slot_dir / "game_account.yml").is_file()
    assert (slot_dir / "one_dragon" / "_group.yml").is_file()
    assert task._injected_slots == [(1, None)]

    asyncio.run(task._restore_injection())

    assert task._injected_slots == []
    assert task._slot_users == {}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
