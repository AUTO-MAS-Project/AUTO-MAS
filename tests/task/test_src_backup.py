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

"""SRC 配置备份恢复原语的最小回归测试。

SRC 与 MAA 同构（ConfigFile 目录副本 + 页面字段侧车 + manager Temp 快照
事务）：mas 池 = ConfigFile 整目录 + Stage/Server/Mode 侧车（Mode 仅预览，
Id/Password 等执行域字段不进备份），native 池 = 安装目录 config/ 整目录。
验证侧车归档/回填、跨用户隔离、native 闭环（含 Temp.ready 恢复守卫——
待恢复快照残留时拒绝恢复，防止恢复结果被下次任务回滚覆盖）、关键字段
反读预览（关卡词表翻译），以及 service 级真实调用链（声明式快照、
基座 files 注入）与 owner 解析。
"""

import asyncio
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.core  # noqa: F401  # 初始化宿主配置
from app.task.SRC.tools.backup_archive import (
    archive_mas_backup,
    archive_native_backup,
    build_native_preview,
    build_overlay_preview,
    get_mas_backup_dir,
    group_overlay,
    list_mas_backups,
    list_native_backups,
    mas_config_dir,
    read_overlay_values,
    restore_mas_backup,
    restore_native_backup,
)

_SRC_JSON = {
    "Alas": {
        "Emulator": {"Serial": "127.0.0.1:5555", "PackageName": "com.miHoYo.hkrpg"}
    },
    "Dungeon": {
        "Scheduler": {"Enable": True},
        "Dungeon": {
            "Name": "Calyx_Golden_Treasures_Jarilo_VI",
            "NameAtDoubleCalyx": "do_not_use",
            "NameAtDoubleRelic": "Cavern_of_Corrosion_Path_of_Insight",
        },
        "TrailblazePower": {
            "ExtractReservedTrailblazePower": True,
            "UseFuel": False,
            "FuelReserve": 5,
        },
    },
    "Ornament": {
        "Scheduler": {"Enable": False},
        "Ornament": {"Dungeon": "Divergent_Universe_Eternal_Comedy"},
    },
    "Weekly": {
        "Scheduler": {"Enable": True},
        "Weekly": {"Name": "Echo_of_War_Divine_Seed"},
    },
    "Rogue": {
        "Scheduler": {"Enable": True},
        "RogueWorld": {"World": "Simulated_Universe_World_8"},
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


def _make_src_install(tmp_path: Path) -> Path:
    """搭一个最小 SRC 安装（exe 占位 + config 目录 + 主配置与部署文件）。"""

    root = tmp_path / "SRC"
    root.mkdir(parents=True)
    (root / "src.exe").write_bytes(b"")
    config_dir = root / "config"
    config_dir.mkdir()
    (config_dir / "src.json").write_text(
        json.dumps(_SRC_JSON, ensure_ascii=False), encoding="utf-8"
    )
    (config_dir / "deploy.yaml").write_text("Webui:\n  Port: 22225\n", encoding="utf-8")
    return config_dir


def _write_config_file(config_file_dir: Path) -> None:
    """搭一个最小用户 ConfigFile 目录（SRC 配置副本）。"""

    config_file_dir.mkdir(parents=True, exist_ok=True)
    (config_file_dir / "src.json").write_text(
        json.dumps(_SRC_JSON, ensure_ascii=False), encoding="utf-8"
    )
    (config_file_dir / "deploy.yaml").write_text(
        "Webui:\n  Port: 22225\n", encoding="utf-8"
    )


def test_mas_overlay_grouping_and_dedup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """侧车归档：指纹去重、Stage/Server 可回填、Mode 仅预览、执行域不进侧车。"""

    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0001", "u-0001"
    user = SimpleNamespace(
        get=lambda g, k: {
            ("Info", "Mode"): "用户",
            ("Info", "Server"): "CN-Official",
            ("Info", "Id"): "13800001234",
            ("Stage", "Channel"): "Relic",
            ("Stage", "Relic"): "Cavern_of_Corrosion_Path_of_Insight",
            ("Stage", "FuelReserve"): 5,
        }.get((g, k))
    )

    overlay = read_overlay_values(user)
    # Id（MAS 登录执行域）不进侧车；Stage/Server/Mode 进
    assert "Id" not in overlay
    assert overlay["Server"] == "CN-Official"
    assert overlay["Channel"] == "Relic"

    config_file_dir = mas_config_dir(script_id, user_id)
    _write_config_file(config_file_dir)
    first = archive_mas_backup(script_id, user_id, config_file_dir, overlay=overlay)
    assert first is not None
    # 指纹去重：同目录同侧车再归档跳过
    assert (
        archive_mas_backup(script_id, user_id, config_file_dir, overlay=overlay) is None
    )
    # 只改侧车字段（未动 ConfigFile）也要新建归档
    changed = dict(overlay, Relic="Cavern_of_Corrosion_Path_of_Aria")
    assert (
        archive_mas_backup(script_id, user_id, config_file_dir, overlay=changed)
        is not None
    )
    assert len(list_mas_backups(script_id, user_id)) == 2

    grouped = group_overlay(overlay)
    assert set(grouped) == {"Info", "Stage"}
    assert grouped["Info"]["Server"] == "CN-Official"
    assert grouped["Stage"]["Relic"] == "Cavern_of_Corrosion_Path_of_Insight"
    assert grouped["Stage"]["FuelReserve"] == 5
    assert "Mode" not in grouped["Info"]  # 仅预览不回填


def test_mas_backup_restore_loop_with_user_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mas 闭环：归档 → 改坏 → 恢复；侧车回传且不留在 ConfigFile；跨用户隔离。"""

    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0002", "u-0001"
    overlay = {
        "Channel": "Relic",
        "Relic": "Cavern_of_Corrosion_Path_of_Insight",
        "Mode": "用户",
    }
    config_file_dir = mas_config_dir(script_id, user_id)
    _write_config_file(config_file_dir)

    first = archive_mas_backup(script_id, user_id, config_file_dir, overlay=overlay)
    assert first is not None

    # ConfigFile 被改坏 → 恢复找回
    (config_file_dir / "src.json").write_text("{}", encoding="utf-8")
    restored_overlay = restore_mas_backup(
        script_id, user_id, first.name, config_file_dir, overlay=overlay
    )
    assert restored_overlay == overlay
    assert (
        json.loads((config_file_dir / "src.json").read_text("utf-8"))["Dungeon"][
            "Dungeon"
        ]["Name"]
        == _SRC_JSON["Dungeon"]["Dungeon"]["Name"]
    )
    # 侧车文件不留在 ConfigFile（不污染脚本 GUI）
    assert not (config_file_dir / "_mas_overlay.json").exists()
    assert len(list_mas_backups(script_id, user_id)) == 2  # 恢复前强制存底 +1

    # 跨用户隔离：另一个用户的池互不可见（§1.1.1 教训）
    other = "u-0002"
    assert list_mas_backups(script_id, other) == []
    other_dir = mas_config_dir(script_id, other)
    _write_config_file(other_dir)
    archive_mas_backup(script_id, other, other_dir, overlay=overlay, force=True)
    assert list_mas_backups(script_id, other) != []
    assert len(list_mas_backups(script_id, user_id)) == 2  # 用户池不被 other 影响


def test_native_backup_restore_loop_with_temp_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """native 闭环：归档 → 改坏 → 恢复；待恢复快照残留时拒绝恢复。"""

    monkeypatch.chdir(tmp_path)
    script_id = "s-0003"
    config_dir = _make_src_install(tmp_path)

    first = archive_native_backup(config_dir)
    assert first is not None
    assert list_native_backups(config_dir) == [first.name]

    # 配置被改坏（模拟误操作）→ Temp.ready 残留时恢复被拒绝
    (config_dir / "src.json").write_text("{}", encoding="utf-8")
    (tmp_path / "data" / script_id).mkdir(parents=True)
    (tmp_path / "data" / script_id / "Temp.ready").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        restore_native_backup(config_dir, first.name, script_id)
    assert json.loads((config_dir / "src.json").read_text("utf-8")) == {}

    # 快照处置完成后恢复成功，内容找回
    (tmp_path / "data" / script_id / "Temp.ready").unlink()
    restore_native_backup(config_dir, first.name, script_id)
    assert (
        json.loads((config_dir / "src.json").read_text("utf-8"))["Dungeon"]["Dungeon"][
            "Name"
        ]
        == _SRC_JSON["Dungeon"]["Dungeon"]["Name"]
    )
    assert len(list_native_backups(config_dir)) == 2  # 恢复前强制存底 +1


def test_native_preview_reads_key_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """native 预览：目标设备/包名反查/副本开关与关卡词表翻译/后备开拓力。"""

    monkeypatch.chdir(tmp_path)
    config_dir = _make_src_install(tmp_path)
    first = archive_native_backup(config_dir)
    assert first is not None

    payload = build_native_preview(config_dir, first.name)
    sections = {s["name"]: s for s in payload["sections"]}
    assert set(sections) == {"src"}
    rows = {row["key"]: row["value"] for row in sections["src"]["rows"]}
    assert rows["目标设备"] == "127.0.0.1:5555"
    assert rows["服务器"] == "官服"  # PackageName 反查
    assert rows["每日副本"] == "开启"
    assert rows["遗器关卡"] == "遗器：领航员 & 名冶（观火之径）"  # 词表翻译
    assert "材料关卡" not in rows  # do_not_use 不进预览
    assert rows["主副本关卡"] == "材料：信用点（藏珍之蕾 雅利洛-Ⅵ）"
    assert rows["饰品提取"] == "关闭"
    assert rows["饰品关卡"] == "饰品：奔狼 & 火宫（永恒笑剧）"
    assert rows["历战余响"] == "开启"
    assert rows["模拟宇宙世界"] == "第八世界"
    assert rows["使用储备开拓力"] == "开启"
    assert rows["使用燃料"] == "关闭"
    assert rows["保留燃料"] == "5"


def test_native_preview_falls_back_to_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """全新安装只有 template.json 时预览回退读模板（不显示「无法解析」）。"""

    monkeypatch.chdir(tmp_path)
    root = tmp_path / "SRC"
    root.mkdir()
    (root / "src.exe").write_bytes(b"")
    config_dir = root / "config"
    config_dir.mkdir()
    (config_dir / "template.json").write_text(
        json.dumps(_SRC_JSON, ensure_ascii=False), encoding="utf-8"
    )
    (config_dir / "deploy.template-cn.yaml").write_text(
        "Webui:\n  Port: 22225\n", encoding="utf-8"
    )

    first = archive_native_backup(config_dir)
    assert first is not None
    payload = build_native_preview(config_dir, first.name)
    rows = {row["key"]: row["value"] for row in payload["sections"][0]["rows"]}
    assert rows["服务器"] == "官服"
    assert rows["每日副本"] == "开启"


def test_overlay_preview_sections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mas 预览：分区（MAS 独有 = 配置文件来源；SRC 配置 = 页面核心字段）。"""

    monkeypatch.chdir(tmp_path)
    payload = build_overlay_preview(
        {
            "Mode": "用户",
            "Server": "CN-Official",
            "Channel": "Relic",
            "Relic": "Cavern_of_Corrosion_Path_of_Insight",
            "EchoOfWar": "-",
            "ExtractReservedTrailblazePower": True,
            "UseFuel": False,
            "FuelReserve": 5,
        }
    )
    sections = {s["name"]: s for s in payload["sections"]}
    assert set(sections) == {"mas-only", "src"}
    mas_rows = {row["key"]: row["value"] for row in sections["mas-only"]["rows"]}
    assert mas_rows == {"配置文件来源": "用户"}
    src_rows = {row["key"]: row["value"] for row in sections["src"]["rows"]}
    assert src_rows["服务器"] == "官服"
    assert src_rows["刷取类型"] == "遗器"
    assert src_rows["遗器关卡"] == "遗器：领航员 & 名冶（观火之径）"
    assert (
        src_rows["历战余响关卡"] == "禁用"
    )  # STARRAIL_STAGE_BOOK 哨兵（与 native 池同标签）
    assert src_rows["保留燃料"] == "5"


def test_restore_service_callbacks_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """service 级真实调用链：声明式 snapshot（含播种）→ preview（files 注入）
    → restore（回填）+ owner 解析。"""

    from app.task.SRC.tools.restore_service import (
        RESTORE_POOLS,
        RESTORE_SCRIPT_NAME,
    )
    from app.utils.config_restore import RestoreContext, build_restore_service

    monkeypatch.chdir(tmp_path)
    script_id = "s-0004"
    uid = uuid.uuid4()
    config_dir = _make_src_install(tmp_path)
    user = _FakeUser(
        {
            "Info.Mode": "脚本",
            "Info.Server": "CN-Official",
            "Stage.Channel": "Relic",
            "Stage.Relic": "Cavern_of_Corrosion_Path_of_Insight",
        }
    )
    script_config = SimpleNamespace(
        get=lambda g, k: str(config_dir.parent) if (g, k) == ("Info", "Path") else "",
        UserData={uid: user},
    )
    ctx = RestoreContext(
        config=None,
        script_config=script_config,
        script_id=script_id,
        user_id=str(uid),
    )
    service = build_restore_service(ctx, RESTORE_SCRIPT_NAME, RESTORE_POOLS)

    # 脚本态 owner=Default：快照播种并归档到共享 Default 目录，池按用户分桶
    created = asyncio.run(service.ensure("mas"))
    assert created["created"] is True and created["time"]
    assert mas_config_dir(script_id, "Default").is_dir()  # 播种生效
    assert [item["time"] for item in asyncio.run(service.list("mas"))] == [
        created["time"]
    ]

    payload = asyncio.run(service.preview("mas", created["time"]))
    sections = {s["name"]: s for s in payload["sections"]}
    src_rows = {row["key"]: row["value"] for row in sections["src"]["rows"]}
    assert src_rows["服务器"] == "官服"
    # 归档内文件清单由基座注入（ConfigFile 副本 + 页面字段侧车）
    assert "_mas_overlay.json" in {f["path"] for f in payload["files"]}

    # 声明式 read_file（基座从 backup_root 派生）
    content = asyncio.run(
        service.read_backup_file("mas", created["time"], "_mas_overlay.json")
    )
    assert "Relic" in content["content"]

    # 恢复前把当前终态存底 → 回填 Stage 段（Mode 排除）
    asyncio.run(service.restore("mas", created["time"]))
    assert len(user.updated) == 1
    assert user.updated[0]["Stage"]["Relic"] == "Cavern_of_Corrosion_Path_of_Insight"
    assert user.updated[0]["Info"]["Server"] == "CN-Official"
    assert "Mode" not in user.updated[0]["Info"]
    # 恢复前存底与最新份内容一致 → 跳过（不产生冗余条目）
    assert len(list_mas_backups(script_id, str(uid))) == 1

    # 直控用户：恢复报错；快照报无变化（无可归档内容）；自身池列表为空
    direct_user = _FakeUser({"Info.Mode": "直控"})
    ctx_direct = RestoreContext(
        config=None,
        script_config=SimpleNamespace(
            get=script_config.get, UserData={uid: direct_user}
        ),
        script_id=script_id,
        user_id=str(uid),
    )
    service_direct = build_restore_service(
        ctx_direct, RESTORE_SCRIPT_NAME, RESTORE_POOLS
    )
    with pytest.raises(ValueError):
        asyncio.run(service_direct.restore("mas", created["time"]))
    fresh_uid = uuid.uuid4()
    ctx_fresh_direct = RestoreContext(
        config=None,
        script_config=SimpleNamespace(
            get=script_config.get, UserData={fresh_uid: direct_user}
        ),
        script_id=script_id,
        user_id=str(fresh_uid),
    )
    service_fresh_direct = build_restore_service(
        ctx_fresh_direct, RESTORE_SCRIPT_NAME, RESTORE_POOLS
    )
    assert asyncio.run(service_fresh_direct.ensure("mas")) == {
        "created": False,
        "time": "",
    }
    assert asyncio.run(service_fresh_direct.list("mas")) == []

    # native：快照 + 恢复（守卫由 backup_archive 层测试覆盖）
    created_native = asyncio.run(service.ensure("native"))
    assert created_native["created"] is True
    payload_native = asyncio.run(service.preview("native", created_native["time"]))
    assert {f["path"] for f in payload_native["files"]} == {"src.json", "deploy.yaml"}
    asyncio.run(service.restore("native", created_native["time"]))
    assert list_native_backups(config_dir)  # 恢复成功，池有条目


def test_get_mas_backup_dir_guards_timestamp(tmp_path: Path) -> None:
    """get_mas_backup_dir 拒绝非法时间戳（路径穿越防护由公共原语保证）。"""

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0005", "u-0003"
    config_file_dir = mas_config_dir(script_id, user_id)
    _write_config_file(config_file_dir)
    archive_mas_backup(script_id, user_id, config_file_dir)
    monkeypatch.undo()

    assert get_mas_backup_dir(script_id, user_id, "..") is None
    assert get_mas_backup_dir(script_id, user_id, "20260101-000000") is None
    with pytest.raises(ValueError):
        restore_mas_backup(script_id, user_id, "..", config_file_dir)
