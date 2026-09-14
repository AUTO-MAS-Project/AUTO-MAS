#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, version 3 or (at your option)
#   any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public
#   License along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""HSR 配置备份恢复原语的最小回归测试。

HSR 是一对多专项（M7A + SRA 两引擎）：mas 池是纯字段侧车（Info.Mode 仅
预览 + Managed.TaskMapping/Options + Direct 快照元数据，不含加密快照内容），
native 池 = M7A config.yaml + SRA settings.json/cache.json/configs/（按 SRA
appdata 根分桶）。验证侧车归档/回填、native 闭环、预览分区，以及池回调
真实调用链（回调层 monkeypatch SRA appdata 指向 tmp，避免污染真实共享目录）。
"""

import asyncio
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.core  # noqa: F401  # 初始化宿主配置
from app.task.HSR.tools.backup_archive import (
    archive_mas_backup,
    archive_native_backup,
    build_native_preview,
    build_overlay_preview,
    group_overlay,
    list_mas_backups,
    list_native_backups,
    read_overlay_values,
    restore_mas_backup,
    restore_native_backup,
)

_SRA_SETTINGS = {"gamePath": "G:/games/SR"}
_SRA_CACHE = {"notificationsDisabled": True}
# M7A config.yaml 为平铺键（现场核实 config.example.yaml；无 loginAccount 字段）
_M7A_CONFIG = (
    "power_enable: true\n"
    "instance_type: 侵蚀隧洞\n"
    "instance_names:\n"
    "  侵蚀隧洞: 睿治之径\n"
    "  历战余响: 毁灭的开端\n"
    "use_reserved_trailblaze_power: false\n"
    "use_fuel: false\n"
    "echo_of_war_enable: true\n"
    "reward_enable: true\n"
    "reward_dispatch_enable: true\n"
    "reward_mail_enable: false\n"
    "weekly_divergent_enable: false\n"
    "currencywars_enable: true\n"
    "currencywars_type: overclock\n"
)
# SRA 档案为顶层 camelCase 段 + 段内平铺点号键（SRACore/models/tasks_config.py
# @ v2.22.0-beta.4，与 MAS _build_sra_base_config 写出口径一致）
_SRA_PROFILE = {
    "name": "Default",
    "version": 0,
    "startGame": {"enabled": True, "game.channel": 0},
    "trailblazePower": {
        "enabled": True,
        "replenish.enabled": True,
        "replenish.way": 1,
        "replenish.times": 3,
        "tasklist": [
            {
                "name": "历战余响",
                "id": "echo_of_war",
                "level": 9,
                "levelName": "毁灭的开端",
                "count": 3,
                "runtimes": 1,
                "autoDetect": True,
            }
        ],
    },
    "receiveRewards": {
        "enabled": True,
        "redeemCodes": "",
        "rewards": [True, True, False, True, True, True, False],
    },
    "cosmicStrife": {
        "enabled": False,
        "divergentUniverse.enabled": True,
        "divergentUniverse.mode": 1,
        "divergentUniverse.runtimes": 20,
        "currencyWars.enabled": False,
    },
    "missionAccomplished": {"enabled": False, "exitGame": True, "logout": False},
}


class _FakeUser:
    """鸭子类型用户配置（read_overlay_values / update 回填验证）。"""

    def __init__(self, values: dict):
        self._values = values
        self.updated: list[dict] = []

    def get(self, group: str, key: str):
        return self._values.get(f"{group}.{key}")

    async def update(self, grouped: dict):
        self.updated.append(grouped)


def _make_sra_appdata(tmp_path: Path) -> Path:
    """搭一个最小 SRA appdata 目录（settings/cache/configs）。"""

    sra = tmp_path / "sra_appdata"
    (sra / "configs").mkdir(parents=True)
    (sra / "settings.json").write_text(
        json.dumps(_SRA_SETTINGS, ensure_ascii=False), encoding="utf-8"
    )
    (sra / "cache.json").write_text(
        json.dumps(_SRA_CACHE, ensure_ascii=False), encoding="utf-8"
    )
    (sra / "configs" / "Default.json").write_text(
        json.dumps(_SRA_PROFILE, ensure_ascii=False), encoding="utf-8"
    )
    return sra


def _make_m7a_root(tmp_path: Path) -> Path:
    """搭一个最小 M7A 安装根（config.yaml）。"""

    m7a = tmp_path / "m7a"
    m7a.mkdir(parents=True)
    (m7a / "config.yaml").write_text(_M7A_CONFIG, encoding="utf-8")
    return m7a


def test_mas_overlay_grouping_and_dedup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """侧车归档：全量字段分组、指纹去重、Mode 仅预览、敏感内容不进。"""

    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0001", "u-0001"
    user = SimpleNamespace(
        get=lambda g, k: {
            ("Info", "Mode"): "用户",
            ("Info", "Name"): "新用户",
            ("Info", "Status"): True,
            ("Info", "Server"): "CN-Official",
            ("Info", "RemainedDay"): -1,
            ("Info", "Notes"): "无",
            ("TaskSwitch", "Daily"): True,
            ("TaskSwitch", "ReceiveRewards"): True,
            ("TaskSwitch", "DivergentUniverse"): False,
            ("TaskSwitch", "CurrencyWars"): False,
            ("Stage", "Channel"): "CalyxGolden",
            ("Stage", "ScriptStage"): json.dumps(
                {"label": "回忆之蕾", "sra": {"id": "calyx_golden", "level": 3}}
            ),
            ("Stage", "ScriptEchoOfWar"): json.dumps(
                {"label": "毁灭的开端", "sra": {"id": "echo_of_war", "level": 9}}
            ),
            ("TaskOpt", "EchoOfWarWeekday"): "Monday",
            ("Notify", "Enabled"): False,
            ("Control", "SRA"): True,
            ("Control", "M7A"): False,
            ("Managed", "TaskMapping"): json.dumps(
                {"每日清体力": "M7A", "刷圣遗物": "SRA"}
            ),
            ("Managed", "Options"): json.dumps({"每日清体力次数": 3}),
            ("Direct", "SRAImportedAt"): "2026-01-01T00:00:00",
            ("Direct", "SRASource"): "my-profile",
            ("Direct", "SRAConfig"): "encrypted-secret",  # 加密内容不进侧车
            ("Info", "Id"): "user1",  # 加密凭据不进侧车
            ("Data", "ProxyTimes"): 3,  # 运行统计不进侧车
        }.get((g, k))
    )

    overlay = read_overlay_values(user)
    assert "Direct.SRAConfig" not in overlay  # 加密快照内容不进
    assert "Info.Id" not in overlay  # 加密凭据不进
    assert "Data.ProxyTimes" not in overlay  # 运行统计不进
    assert overlay["Managed.TaskMapping"]  # 原始 JSON 串
    assert overlay["TaskSwitch.Daily"] is True

    first = archive_mas_backup(script_id, user_id, overlay)
    assert first is not None
    assert archive_mas_backup(script_id, user_id, overlay) is None  # 指纹去重
    changed = dict(overlay, **{"Direct.SRAImportedAt": "2026-02-01T00:00:00"})
    assert archive_mas_backup(script_id, user_id, changed) is not None
    assert len(list_mas_backups(script_id, user_id)) == 2

    grouped = group_overlay(overlay)
    assert set(grouped) == {
        "Info",
        "TaskSwitch",
        "Stage",
        "TaskOpt",
        "Notify",
        "Control",
        "Managed",
        "Direct",
    }
    assert "Mode" not in grouped["Info"]  # 配置来源仅预览不回填
    assert grouped["TaskSwitch"]["Daily"] is True
    assert grouped["Stage"]["Channel"] == "CalyxGolden"


def test_mas_restore_roundtrip_with_user_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mas 恢复：侧车回传、跨用户隔离。"""

    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0002", "u-0001"
    overlay = {
        "Managed.TaskMapping": json.dumps({"每日清体力": "M7A"}),
        "TaskSwitch.Daily": True,
        "Direct.SRAImportedAt": "2026-01-01T00:00:00",
        "Info.Mode": "用户",
        "legacy-orphan": "no-dot",  # 旧格式无组前缀：不回填
    }
    first = archive_mas_backup(script_id, user_id, overlay)
    assert first is not None

    restored = restore_mas_backup(script_id, user_id, first.name)
    assert restored == overlay
    grouped = group_overlay(restored)
    assert "TaskMapping" in grouped["Managed"]
    assert grouped["TaskSwitch"]["Daily"] is True
    assert "SRAImportedAt" in grouped["Direct"]
    assert "Info" not in grouped  # Mode 仅预览
    assert "legacy-orphan" not in grouped  # 无组前缀不回填

    other = "u-0002"
    assert list_mas_backups(script_id, other) == []
    archive_mas_backup(script_id, other, overlay, force=True)
    assert list_mas_backups(script_id, other) != []
    assert len(list_mas_backups(script_id, user_id)) == 1  # 用户池不被 other 影响


def test_native_backup_restore_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """native 闭环：归档两引擎配置 → 改坏 → 恢复找回。"""

    monkeypatch.chdir(tmp_path)
    m7a = _make_m7a_root(tmp_path)
    sra = _make_sra_appdata(tmp_path)

    first = archive_native_backup(m7a, sra)
    assert first is not None
    assert (first / "M7A" / "config.yaml").is_file()
    assert (first / "SRA" / "settings.json").is_file()
    assert (first / "SRA" / "cache.json").is_file()
    assert (first / "SRA" / "configs" / "Default.json").is_file()

    # 两引擎配置均被改坏 → 恢复找回
    (m7a / "config.yaml").write_text("broken", encoding="utf-8")
    (sra / "settings.json").write_text("{}", encoding="utf-8")
    (sra / "configs" / "Default.json").write_text("{}", encoding="utf-8")
    restore_native_backup(m7a, sra, first.name)
    assert (m7a / "config.yaml").read_text("utf-8") == _M7A_CONFIG
    assert json.loads((sra / "settings.json").read_text("utf-8")) == _SRA_SETTINGS
    assert (
        json.loads((sra / "configs" / "Default.json").read_text("utf-8"))
        == _SRA_PROFILE
    )
    assert len(list_native_backups(sra)) == 2  # 恢复前存底 +1

    # 全缺失时跳过归档
    assert archive_native_backup(None, sra) is not None  # SRA 仍在
    assert archive_native_backup(None, tmp_path / "nope") is None


def test_native_preview_field_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """native 预览：M7A/SRA 常用字段反读 + settings/cache 只进文件清单。"""

    monkeypatch.chdir(tmp_path)
    m7a = _make_m7a_root(tmp_path)
    sra = _make_sra_appdata(tmp_path)
    first = archive_native_backup(m7a, sra)
    assert first is not None

    payload = build_native_preview(sra, first.name)
    sections = {s["name"]: s for s in payload["sections"]}
    assert set(sections) == {"m7a", "sra:Default", "files"}

    m7a_rows = {row["key"]: row["value"] for row in sections["m7a"]["rows"]}
    assert m7a_rows["清体力"] == "开启"
    assert m7a_rows["副本"] == "侵蚀隧洞 · 睿治之径"
    assert m7a_rows["历战余响"] == "开启 · 毁灭的开端"
    assert m7a_rows["体力补充"] == "无"
    assert m7a_rows["领取奖励"] == "委托"
    assert m7a_rows["差分宇宙"] == "关闭"
    assert m7a_rows["货币战争"] == "超频博弈"

    sra_rows = {row["key"]: row["value"] for row in sections["sra:Default"]["rows"]}
    assert sra_rows["游戏渠道"] == "国服"
    assert "毁灭的开端" in sra_rows["清体力任务清单"]
    assert sra_rows["补充开拓力"] == "燃料 ×3"
    assert sra_rows["领取奖励"] == (
        "签证（支援）奖励、委托奖励、每日实训奖励、无名勋礼奖励、巡星之礼"
    )
    assert sra_rows["差分宇宙"] == "周期演算 ×20"
    assert sra_rows["货币战争"] == "关闭"
    assert sra_rows["完成后动作"] == "退出游戏"

    file_rows = {row["key"] for row in sections["files"]["rows"]}
    assert file_rows == {
        "M7A/config.yaml",
        "SRA/cache.json",
        "SRA/configs/Default.json",
        "SRA/settings.json",
    }


def test_sra_reward_values_named_and_legacy() -> None:
    """SRA 奖励开关读取：命名键优先、索引式回退、两类都缺失不渲染。"""

    from app.task.HSR.tools.backup_archive import _sra_reward_values

    # 命名键（新版），个别缺失回退 legacy 列表
    named = _sra_reward_values(
        {
            "rewards.trailblazeProfile": True,
            "rewards.mail": False,
            "rewards": [False, False, True, True, True, True, True],
        }
    )
    assert named == [True, False, False, True, True, True, True]

    # 仅索引式（旧版）
    legacy = _sra_reward_values({"rewards": [True, False]})
    assert legacy == [True, False, False, False, False, False, False]

    # 两类都没有 → None
    assert _sra_reward_values({"enabled": True}) is None


def test_overlay_preview_sections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mas 预览：全量分区（MAS 独有 / 任务配置 / 通知 / 托管 / 直控快照）。"""

    monkeypatch.chdir(tmp_path)
    payload = build_overlay_preview(
        {
            "Info.Mode": "用户",
            "Info.Server": "CN-Official",
            "Info.RemainedDay": 30,
            "Info.IfScriptBeforeTask": True,
            "Info.ScriptBeforeTask": "scripts/pre.bat",
            "Control.SRA": True,
            "Control.M7A": False,
            "Info.Notes": "无",
            "TaskSwitch.Daily": True,
            "TaskSwitch.ReceiveRewards": True,
            "TaskSwitch.DivergentUniverse": False,
            "TaskSwitch.CurrencyWars": False,
            "Stage.Channel": "Relic",
            "Stage.ScriptStage": json.dumps(
                {
                    "stages": {
                        "Relic": {
                            "label": "睿治之径",
                            "sra": {"id": "caver", "level": 3},
                        }
                    }
                }
            ),
            "Stage.ScriptEchoOfWar": json.dumps({"label": "毁灭的开端"}),
            "TaskOpt.EchoOfWarWeekday": "Monday",
            "Notify.Enabled": True,
            "Notify.IfSendMail": True,
            "Notify.ToAddress": "user@example.com",
            "Managed.TaskMapping": json.dumps({"每日清体力": "M7A", "刷圣遗物": "SRA"}),
            "Managed.Options": json.dumps({"每日清体力次数": 3}),
            "Direct.SRAImportedAt": "2026-01-01T00:00:00",
        }
    )
    sections = {s["name"]: s for s in payload["sections"]}
    assert set(sections) == {"mas-only", "tasks", "notify", "managed", "direct"}

    mas_rows = {row["key"]: row["value"] for row in sections["mas-only"]["rows"]}
    assert mas_rows["配置来源"] == "用户"
    assert mas_rows["服务器"] == "官服"
    assert mas_rows["剩余天数"] == "30"
    assert mas_rows["任务前脚本"] == "启用 · scripts/pre.bat"
    assert mas_rows["直控引擎"] == "SRA"

    task_rows = {row["key"]: row["value"] for row in sections["tasks"]["rows"]}
    assert task_rows["任务开关"] == "每日、领取奖励"
    assert task_rows["体力类型"] == "侵蚀隧洞"
    assert task_rows["主副本"] == "睿治之径"
    assert task_rows["历战余响副本"] == "毁灭的开端"
    assert task_rows["历战余响开始星期"] == "周一"

    notify_rows = {row["key"]: row["value"] for row in sections["notify"]["rows"]}
    assert notify_rows["通知"] == "邮件"
    assert notify_rows["收件地址"] == "已设置（不显示）"  # 敏感值脱敏

    managed_rows = {row["key"]: row["value"] for row in sections["managed"]["rows"]}
    assert "每日清体力→M7A" in managed_rows["任务映射"]

    direct_rows = {row["key"]: row["value"] for row in sections["direct"]["rows"]}
    assert direct_rows == {"SRA 快照导入时间": "2026-01-01T00:00:00"}


def test_restore_service_callbacks_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """池回调真实调用链：snapshot → preview → restore（回填 + native 闭环）。"""

    from app.task.HSR.tools import restore_service as rs

    monkeypatch.chdir(tmp_path)
    script_id = "s-0003"
    uid = uuid.uuid4()
    m7a = _make_m7a_root(tmp_path)
    sra = _make_sra_appdata(tmp_path)
    # 回调层 SRA appdata 指向 tmp，避免污染真实共享目录
    monkeypatch.setattr(rs, "get_sra_app_data_dir", lambda: sra)

    user = _FakeUser(
        {
            "Info.Mode": "用户",
            "Managed.TaskMapping": json.dumps({"每日清体力": "M7A"}),
            "Direct.SRAImportedAt": "2026-01-01T00:00:00",
        }
    )
    script_config = SimpleNamespace(
        get=lambda g, k: {
            ("Info", "M7APath"): str(m7a),
            ("Info", "SRAPath"): str(m7a),  # SRA 路径仅用于解析，appdata 由 patch 决定
        }.get((g, k), ""),
        UserData={uid: user},
    )
    ctx = SimpleNamespace(
        config=None,
        script_config=script_config,
        script_id=script_id,
        user_id=str(uid),
    )

    created = asyncio.run(rs._snapshot_mas(ctx))
    assert created["created"] is True and created["time"]
    payload = asyncio.run(rs._preview_mas(ctx, created["time"]))
    assert "managed" in {s["name"] for s in payload["sections"]}

    asyncio.run(rs._restore_mas(ctx, created["time"]))
    assert len(user.updated) == 1
    assert "TaskMapping" in user.updated[0]["Managed"]
    assert "Info" not in user.updated[0]  # Mode 仅预览

    # native：快照 + 恢复闭环
    created_native = asyncio.run(rs._snapshot_native(ctx))
    assert created_native["created"] is True
    asyncio.run(rs._restore_native(ctx, created_native["time"]))
    assert list_native_backups(sra)
