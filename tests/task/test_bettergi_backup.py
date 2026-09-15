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

"""BetterGI 配置备份恢复原语的最小回归测试。

BetterGI 用户配置分两块：per-user 副本目录（data/{script_id}/{user_id}/ 的
OneDragon/ScriptGroup/GlobalDomain，前端端点直接读写）+ UserData 字段侧车
（OneDragon 段 + Task.OneDragonConfigName + Switch.Resource + Info.Mode 仅
预览）；native 池 = BetterGI 全局主配置 User/config.json（单文件，被运行时
临时补写叶子）。验证 mas 归档/恢复/回填、跨用户隔离、native 闭环、预览分区，
以及池回调真实调用链。
"""

import asyncio
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.core  # noqa: F401  # 初始化宿主配置
from app.task.BetterGI.tools.backup_archive import (
    archive_mas_backup,
    archive_native_backup,
    build_mas_preview,
    build_native_preview,
    get_mas_backup_dir,
    group_overlay,
    list_mas_backups,
    list_native_backups,
    mas_user_dir,
    read_overlay_values,
    restore_mas_backup,
    restore_native_backup,
)

_GLOBAL_CONFIG = {
    "autoFightConfig": {"strategyName": "根据队伍自动选择"},
    "autoDomainConfig": {"partyName": "", "autoArtifactSalvage": False},
    "autoBossConfig": {"teamName": "", "strategyName": ""},
    "autoPickConfig": {"enabled": True},
    "selectedOneDragonFlowConfigName": "默认配置",
}

_ONE_DRAGON_CONFIG = {"TaskEnabledList": {"自动秘境": True, "自动地脉花": False}}

# BGI 一条龙实配（截图口径）：任务编排 = TaskOrder(uid 序) + TaskEnabledList
# (uid→bool) + TaskDefinitions(uid→任务名)
_ONE_DRAGON_FLOW_CONFIG = {
    "TaskOrder": ["t1", "t2", "t3", "t4"],
    "TaskEnabledList": {"t1": True, "t2": True, "t3": False, "t4": True},
    "TaskDefinitions": {
        "t1": "领取邮件",
        "t2": "自动秘境",
        "t3": "合成树脂",
        "t4": "自动首领讨伐",
    },
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


_USER_VALUES = {
    "Info.Mode": "用户",
    "Task.OneDragonConfigName": "默认配置",
    "OneDragon.Groups": ["自动秘境", "自动地脉花"],
    "OneDragon.PartyName": "默认队伍",
    "OneDragon.IfUseCustomGroups": False,
    "Switch.Resource": "官服",
}


def _write_per_user_copies(script_id: str, user_id: str) -> Path:
    """搭 per-user 副本（OneDragon/ScriptGroup/GlobalDomain 三个子目录）。"""

    user_root = mas_user_dir(script_id, user_id)
    one = user_root / "OneDragon"
    one.mkdir(parents=True)
    (one / "MAS独立配置.json").write_text(
        json.dumps(_ONE_DRAGON_CONFIG, ensure_ascii=False), encoding="utf-8"
    )
    sg = user_root / "ScriptGroup"
    sg.mkdir(parents=True)
    (sg / "锄大地.json").write_text(json.dumps({"name": "锄大地"}), encoding="utf-8")
    gd = user_root / "GlobalDomain"
    gd.mkdir(parents=True)
    (gd / "settings.json").write_text(json.dumps({"resinCount": 2}), encoding="utf-8")
    return user_root


def _make_bgi_root(tmp_path: Path) -> Path:
    """搭一个最小 BetterGI 安装根（全局 config.json + 一条龙实配目录）。"""

    root = tmp_path / "BGI"
    user_dir = root / "User"
    user_dir.mkdir(parents=True)
    (user_dir / "config.json").write_text(
        json.dumps(_GLOBAL_CONFIG, ensure_ascii=False), encoding="utf-8"
    )
    dragon_dir = user_dir / "OneDragon"
    dragon_dir.mkdir()
    (dragon_dir / "默认配置.json").write_text(
        json.dumps(_ONE_DRAGON_FLOW_CONFIG, ensure_ascii=False), encoding="utf-8"
    )
    (dragon_dir / "MAS独立配置.json").write_text(
        json.dumps({"TaskOrder": []}), encoding="utf-8"
    )
    return root


def test_mas_overlay_grouping_and_dedup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """侧车归档：指纹去重、OneDragon 段可回填、Mode 仅预览、执行域不进侧车。"""

    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0001", "u-0001"
    user = SimpleNamespace(
        get=lambda g, k: {
            ("Info", "Mode"): "用户",
            ("Task", "OneDragonConfigName"): "默认配置",
            ("OneDragon", "Groups"): ["自动秘境", "自动地脉花"],
            ("OneDragon", "PartyName"): "默认队伍",
            ("OneDragon", "IfUseCustomGroups"): False,
            ("Switch", "Resource"): "官服",
            ("Info", "Id"): "13800001234",
            ("Info", "Password"): "secret",
        }.get((g, k))
    )

    overlay = read_overlay_values(user)
    assert "Id" not in overlay  # 登录执行域不进侧车
    assert "Password" not in overlay
    assert overlay["Mode"] == "用户"
    assert overlay["Groups"] == ["自动秘境", "自动地脉花"]

    _write_per_user_copies(script_id, user_id)
    first = archive_mas_backup(script_id, user_id, overlay=overlay)
    assert first is not None
    assert archive_mas_backup(script_id, user_id, overlay=overlay) is None  # 指纹去重
    # 只改页面字段（副本未动）→ 同样新建归档
    changed = dict(overlay, PartyName="备用队伍")
    assert archive_mas_backup(script_id, user_id, overlay=changed) is not None
    assert len(list_mas_backups(script_id, user_id)) == 2

    grouped = group_overlay(overlay)
    # Mode 仅预览不回填：Info 组无回填字段，整组不出现
    assert set(grouped) == {"Task", "OneDragon", "Switch"}
    assert grouped["OneDragon"]["Groups"] == ["自动秘境", "自动地脉花"]
    assert grouped["Switch"]["Resource"] == "官服"


def test_mas_backup_restore_loop_with_user_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mas 闭环：归档 → 副本被改坏 → 恢复；侧车回传且不留在副本；跨用户隔离。"""

    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0002", "u-0001"
    overlay = {"Groups": ["自动秘境"], "PartyName": "默认队伍", "Mode": "用户"}
    _write_per_user_copies(script_id, user_id)

    first = archive_mas_backup(script_id, user_id, overlay=overlay)
    assert first is not None

    # 副本被改坏（模拟前端误保存/误操作）→ 恢复找回
    bad = json.dumps({"TaskEnabledList": {}}, ensure_ascii=False)
    (mas_user_dir(script_id, user_id) / "OneDragon" / "MAS独立配置.json").write_text(
        bad, encoding="utf-8"
    )
    restored_overlay = restore_mas_backup(
        script_id, user_id, first.name, overlay=overlay
    )
    assert restored_overlay == overlay
    restored = json.loads(
        (mas_user_dir(script_id, user_id) / "OneDragon" / "MAS独立配置.json").read_text(
            "utf-8"
        )
    )
    assert restored == _ONE_DRAGON_CONFIG
    # 侧车文件不留在 per-user 根（不污染副本目录）
    assert not (mas_user_dir(script_id, user_id) / "_mas_overlay.json").exists()
    assert len(list_mas_backups(script_id, user_id)) == 2  # 恢复前存底与最新一致 → 跳过

    # 跨用户隔离：另一个用户的池互不可见（§1.1.1 教训）
    other = "u-0002"
    assert list_mas_backups(script_id, other) == []
    _write_per_user_copies(script_id, other)
    archive_mas_backup(script_id, other, overlay=overlay, force=True)
    assert list_mas_backups(script_id, other) != []
    assert len(list_mas_backups(script_id, user_id)) == 2  # 用户池不被 other 影响


def test_native_backup_restore_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """native 闭环：归档 config.json + 一条龙实配 → 被改坏 → 恢复找回。"""

    monkeypatch.chdir(tmp_path)
    root = _make_bgi_root(tmp_path)

    first = archive_native_backup(root)
    assert first is not None
    assert list_native_backups(root) == [first.name]
    # 归档含 config.json 与一条龙实配；MAS 运行时槽位被排除
    assert (first / "config.json").is_file()
    assert (first / "OneDragon" / "默认配置.json").is_file()
    assert not (first / "OneDragon" / "MAS独立配置.json").exists()

    # config.json 与实配均被改坏（BGI GUI 内误操作）→ 恢复找回
    (root / "User" / "config.json").write_text(
        json.dumps({"oneDragonConfig": {"partyName": "污染"}}), encoding="utf-8"
    )
    (root / "User" / "OneDragon" / "默认配置.json").write_text(
        json.dumps({"TaskOrder": []}), encoding="utf-8"
    )
    restore_native_backup(root, first.name)
    assert (
        json.loads((root / "User" / "config.json").read_text("utf-8")) == _GLOBAL_CONFIG
    )
    assert (
        json.loads((root / "User" / "OneDragon" / "默认配置.json").read_text("utf-8"))
        == _ONE_DRAGON_FLOW_CONFIG
    )
    assert len(list_native_backups(root)) == 2  # 恢复前存底（内容已变 → 新增）

    # 两类都缺失时跳过归档
    assert archive_native_backup(tmp_path / "nope") is None


def test_native_preview_reads_key_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """native 预览：已启用任务（实配反读）+ 战斗配置叶子（config.json）。"""

    monkeypatch.chdir(tmp_path)
    root = _make_bgi_root(tmp_path)
    first = archive_native_backup(root)
    assert first is not None

    payload = build_native_preview(root, first.name)
    sections = {s["name"]: s for s in payload["sections"]}
    assert set(sections) == {"bgi"}
    rows = {row["key"]: row["value"] for row in sections["bgi"]["rows"]}
    # 任务列表：TaskOrder 顺序 + TaskEnabledList 过滤（合成树脂禁用不出现）
    assert rows["已启用任务"] == "领取邮件、自动秘境、自动首领讨伐"
    # 与 mas 池同口径：只收 MAS 侧有对应概念的战斗配置叶子
    assert rows["战斗策略"] == "根据队伍自动选择"
    assert rows["自动秘境队伍"] == "未设置"  # 空值显示「未设置」
    assert rows["秘境·分解圣遗物"] == "关闭"
    assert rows["自动首领队伍"] == "未设置"  # 空段也出队/策略行（段存在即展示）
    # mas 侧无对应概念的段（一键开关等）不进预览
    assert "自动拾取" not in rows


def test_overlay_and_mas_preview_sections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mas 预览：字段分区（MAS 独有 = 配置来源；BetterGI 对应）+ 副本文件摘要。"""

    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0003", "u-0001"
    overlay = {
        "Mode": "用户",
        "OneDragonConfigName": "默认配置",
        "Groups": ["自动秘境"],
        "PartyName": "默认队伍",
        "UseExecutionLayer": True,
        "Resource": "官服",
        "Queue": json.dumps(
            [
                {"kind": "builtin", "name": "领取邮件"},
                {"kind": "builtin", "name": "自动秘境"},
            ]
        ),
        "Plan": json.dumps(
            [
                {"uid": "a", "kind": "builtin", "name": "自动秘境", "enabled": True},
                {"uid": "b", "kind": "builtin", "name": "自动地脉花", "enabled": False},
            ]
        ),
    }
    _write_per_user_copies(script_id, user_id)
    first = archive_mas_backup(script_id, user_id, overlay=overlay)
    assert first is not None

    payload = build_mas_preview(
        get_mas_backup_dir(script_id, user_id, first.name), overlay
    )
    sections = {s["name"]: s for s in payload["sections"]}
    assert set(sections) == {"mas-only", "bgi", "copies"}
    mas_rows = {row["key"]: row["value"] for row in sections["mas-only"]["rows"]}
    assert mas_rows == {"配置来源": "用户"}
    bgi_rows = {row["key"]: row["value"] for row in sections["bgi"]["rows"]}
    assert bgi_rows["游戏服务器"] == "官服"
    assert bgi_rows["已启用任务"] == "自动秘境"  # 罗列行（与 native 同标签同口径）
    assert bgi_rows["直连执行层"] == "开启"
    assert bgi_rows["一条龙队列"] == "领取邮件、自动秘境"  # JSON 字符串解析罗列
    assert bgi_rows["一条龙执行计划"] == "自动秘境"  # 启用步骤罗列（禁用的不出现）
    copy_rows = {row["key"]: row["value"] for row in sections["copies"]["rows"]}
    assert set(copy_rows) == {
        "GlobalDomain/settings.json",
        "OneDragon/MAS独立配置.json",
        "ScriptGroup/锄大地.json",
    }


def test_overlay_teams_fields_in_sidecar_and_preview() -> None:
    """队伍配置 2 字段进侧车，预览 BetterGI 对应区含队伍行（Teams 只给数量）。"""

    from app.task.BetterGI.tools.backup_archive import build_overlay_preview

    overlay = {
        "Mode": "用户",
        "IfUseTeams": True,
        "Teams": json.dumps(
            [
                {
                    "name": "上半主力",
                    "strategy": "根据队伍自动选择",
                    "scenes": {"domain": True, "leyline": True, "boss": False},
                    "note": "",
                    "enabled": True,
                },
                {
                    "name": "下半主力",
                    "strategy": "",
                    "scenes": {"domain": False, "leyline": False, "boss": True},
                    "note": "",
                    "enabled": True,
                },
            ],
            ensure_ascii=False,
        ),
    }
    sections = {s["name"]: s for s in build_overlay_preview(overlay)["sections"]}
    bgi_rows = {row["key"]: row["value"] for row in sections["bgi"]["rows"]}
    assert bgi_rows["使用队伍配置"] == "开启"
    assert bgi_rows["队伍配置"] == "已配置 2 支队伍"

    # 空队伍表 / 坏 JSON 兜底
    empty = build_overlay_preview({"IfUseTeams": False, "Teams": json.dumps([])})[
        "sections"
    ]
    empty_rows = {row["key"]: row["value"] for row in empty[0]["rows"]}
    assert empty_rows["使用队伍配置"] == "关闭"
    assert empty_rows["队伍配置"] == "无"

    # 侧车读取与分组：IfUseTeams/Teams 都在 OneDragon 段
    user = SimpleNamespace(
        get=lambda g, k: {
            ("OneDragon", "IfUseTeams"): True,
            ("OneDragon", "Teams"): overlay["Teams"],
        }.get((g, k))
    )
    values = read_overlay_values(user)
    assert set(values) == {"IfUseTeams", "Teams"}
    assert group_overlay(values)["OneDragon"]["IfUseTeams"] is True


def test_restore_service_callbacks_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """service 级真实调用链：声明式 snapshot → preview（files 注入）→ restore。"""

    from app.task.BetterGI.tools.restore_service import (
        RESTORE_POOLS,
        RESTORE_SCRIPT_NAME,
    )
    from app.utils.config_restore import RestoreContext, build_restore_service

    monkeypatch.chdir(tmp_path)
    script_id = "s-0004"
    uid = uuid.uuid4()
    user_id = str(uid)
    _write_per_user_copies(script_id, user_id)
    root = _make_bgi_root(tmp_path)
    user = _FakeUser(
        {
            "Info.Mode": "用户",
            "Task.OneDragonConfigName": "默认配置",
            "OneDragon.Groups": ["自动秘境"],
            "Switch.Resource": "官服",
        }
    )
    script_config = SimpleNamespace(
        get=lambda g, k: str(root) if (g, k) == ("Info", "RootPath") else "",
        UserData={uid: user},
    )
    ctx = RestoreContext(
        config=None,
        script_config=script_config,
        script_id=script_id,
        user_id=user_id,
    )
    service = build_restore_service(ctx, RESTORE_SCRIPT_NAME, RESTORE_POOLS)

    # mas：snapshot → preview（files 注入）→ restore 回填（Mode 排除）
    created = asyncio.run(service.ensure("mas"))
    assert created["created"] is True and created["time"]
    payload = asyncio.run(service.preview("mas", created["time"]))
    assert "bgi" in {s["name"] for s in payload["sections"]}
    assert "_mas_overlay.json" in {f["path"] for f in payload["files"]}

    asyncio.run(service.restore("mas", created["time"]))
    assert len(user.updated) == 1
    assert user.updated[0]["OneDragon"]["Groups"] == ["自动秘境"]
    assert user.updated[0]["Switch"]["Resource"] == "官服"
    # Mode 仅预览不回填：Info 组无回填字段，整组不出现
    assert "Info" not in user.updated[0]
    # 恢复前存底与最新份内容一致 → 跳过（不产生冗余条目）
    assert len(list_mas_backups(script_id, user_id)) == 1

    # 用户不存在于 UserData：恢复报错（守卫）；ghost 在 UserData 但无字段
    # 时 snapshot 报无变化（无可归档内容）
    ghost_uid = uuid.uuid4()
    ctx_ghost = RestoreContext(
        config=None,
        script_config=SimpleNamespace(
            get=script_config.get, UserData={ghost_uid: _FakeUser({})}
        ),
        script_id=script_id,
        user_id=str(ghost_uid),
    )
    service_ghost = build_restore_service(ctx_ghost, RESTORE_SCRIPT_NAME, RESTORE_POOLS)
    ghost_created = asyncio.run(service_ghost.ensure("mas"))
    assert ghost_created == {"created": False, "time": ""}
    with pytest.raises(ValueError):
        asyncio.run(service_ghost.restore("mas", created["time"]))

    # native：snapshot + 恢复闭环
    created_native = asyncio.run(service.ensure("native"))
    assert created_native["created"] is True
    payload_native = asyncio.run(service.preview("native", created_native["time"]))
    assert {f["path"] for f in payload_native["files"]} >= {"config.json"}
    asyncio.run(service.restore("native", created_native["time"]))
    assert list_native_backups(root)

    # 未配置 RootPath：native 列表为空（backup_root 返回 None，不抛错）
    ctx_no_root = RestoreContext(
        config=None,
        script_config=SimpleNamespace(get=lambda g, k: "", UserData={uid: user}),
        script_id=script_id,
        user_id=user_id,
    )
    service_no_root = build_restore_service(
        ctx_no_root, RESTORE_SCRIPT_NAME, RESTORE_POOLS
    )
    assert asyncio.run(service_no_root.list("mas")) == [created["time"]]
    assert asyncio.run(service_no_root.list("native")) == []


def test_get_mas_backup_dir_guards_timestamp(tmp_path: Path) -> None:
    """get_mas_backup_dir 拒绝非法时间戳（路径穿越防护由公共原语保证）。"""

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0005", "u-0003"
    _write_per_user_copies(script_id, user_id)
    archive_mas_backup(script_id, user_id, overlay={"Groups": []})
    monkeypatch.undo()

    assert get_mas_backup_dir(script_id, user_id, "..") is None
    assert get_mas_backup_dir(script_id, user_id, "20260101-000000") is None
    with pytest.raises(ValueError):
        restore_mas_backup(script_id, user_id, "..")
