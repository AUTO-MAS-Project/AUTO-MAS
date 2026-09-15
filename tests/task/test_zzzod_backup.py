#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License
#   as published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""ZZZ-OD 配置备份恢复原语的最小回归测试。

用临时目录模拟一条龙安装目录（原生注册表 + 实例目录 + MAS 绑定槽），验证
onedragon 池的文件集收集（排除 MAS 槽）与恢复闭环、mas 池声明式归档
（物化 + 信息快照内存 YAML，源槽零污染）与基座派生的 list/read 能力。
预览与恢复的门面委托语义（槽占用守卫、字段回填）依赖核心门面，不在本文件覆盖。
"""

import asyncio
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.core  # noqa: F401  # 初始化宿主配置
from app.task.ZzzOd.tools.backup_archive import (
    MAS_USER_INFO_FILE,
    archive_mas_backup,
    archive_onedragon_backup,
    collect_onedragon_files,
    get_mas_backup_dir,
    list_mas_backups,
    list_onedragon_backups,
    mas_user_info_content,
    restore_mas_backup,
    restore_onedragon_backup,
)
from app.task.ZzzOd.tools.zzz_od_config import instance_dir
from app.utils.io import read_file, write_file


@pytest.fixture()
def od_root(tmp_path: Path) -> Path:
    """一条龙安装目录：原生注册表（原生实例 1 + MAS 槽 2）+ 各自实例目录。"""

    root = tmp_path / "zzzod"
    write_file(
        root / "config" / "one_dragon.yml",
        {
            "instance_list": [
                {"idx": 1, "name": "原生实例", "active": True},
                {"idx": 2, "name": "MAS-01", "active": False},
            ]
        },
    )
    write_file(instance_dir(root, 1) / "game_account.yml", {"account": "native"})
    write_file(instance_dir(root, 2) / "game_account.yml", {"account": "slot"})
    return root


def test_onedragon_collect_excludes_mas_slots(od_root: Path) -> None:
    """文件集收集：one_dragon.yml 原件 + 原生实例目录，MAS 槽排除。"""

    files = collect_onedragon_files(od_root)
    assert set(files) == {"one_dragon.yml", "1/game_account.yml"}


def test_onedragon_backup_restore_loop(
    od_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """onedragon 池：备份 → 修改 → 恢复闭环；MAS 槽目录不随备份恢复触碰。"""

    monkeypatch.chdir(od_root.parent)
    first = archive_onedragon_backup(od_root)
    assert first is not None and (first / "one_dragon.yml").is_file()
    assert archive_onedragon_backup(od_root) is None  # 指纹去重

    # 用户改坏原生注册表与实例配置 → 恢复找回
    write_file(od_root / "config" / "one_dragon.yml", {"instance_list": []})
    write_file(instance_dir(od_root, 1) / "game_account.yml", {"account": "bad"})
    restore_onedragon_backup(od_root, first.name)
    registry = read_file(od_root / "config" / "one_dragon.yml")
    assert [item["name"] for item in registry["instance_list"]] == [
        "原生实例",
        "MAS-01",
    ]
    assert read_file(instance_dir(od_root, 1) / "game_account.yml") == {
        "account": "native"
    }
    # 恢复前强制存底 +1
    assert len(list_onedragon_backups(od_root)) == 2


def test_mas_backup_meta_sidecar_in_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mas 池：信息快照以内存 YAML 入档，源槽不落 mas_user_info.yml。"""

    monkeypatch.chdir(tmp_path)
    script_id, slot = "s-0001", 2
    slot_dir = tmp_path / "zzzod" / "config" / "02"
    write_file(slot_dir / "game_account.yml", {"account": "slot"})

    meta = {"Name": "用户A", "Status": True}
    first = archive_mas_backup(script_id, slot, slot_dir, meta=meta)
    assert first is not None
    # 归档目录内有完整快照副本；源槽零污染
    assert (first / MAS_USER_INFO_FILE).is_file()
    assert not (slot_dir / MAS_USER_INFO_FILE).exists()

    # 槽内容与 meta 均未变 → 指纹去重跳过
    assert archive_mas_backup(script_id, slot, slot_dir, meta=meta) is None
    # 只改 meta → 新建归档
    second = archive_mas_backup(
        script_id, slot, slot_dir, meta={**meta, "Notes": "changed"}
    )
    assert second is not None
    assert len(list_mas_backups(script_id, slot)) == 2

    # 快照内容与 write_file 序列化一致（指纹与旧版归档连续）
    import yaml

    assert yaml.safe_load((first / MAS_USER_INFO_FILE).read_text("utf-8")) == meta
    assert (first / MAS_USER_INFO_FILE).read_bytes() == mas_user_info_content(
        meta
    ).encode("utf-8")

    # 恢复到第一份：槽内容回滚，mas_user_info.yml 随归档落回槽目录
    restore_mas_backup(script_id, slot, first.name, slot_dir, meta=meta)
    assert read_file(slot_dir / "game_account.yml") == {"account": "slot"}
    assert (slot_dir / MAS_USER_INFO_FILE).is_file()


class _FakeUser:
    def __init__(self, slot: int):
        self._slot = slot

    def get(self, section: str, key: str):
        if section == "Info":
            return {"SlotIdx": self._slot, "Name": "用户A"}.get(key)
        return None


def _ctx(root: str, uid, slot: int) -> SimpleNamespace:
    script_config = SimpleNamespace(
        get=lambda g, k: {("Info", "RootPath"): root}.get((g, k), ""),
        UserData={uid: _FakeUser(slot)},
    )
    return SimpleNamespace(
        config=None, script_config=script_config, script_id="s-0002", user_id=str(uid)
    )


def test_restore_service_declarative_pools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """service 级声明式链路：ensure → 派生 list/read；未配置/未绑定为无变化。"""

    from app.task.ZzzOd.tools import restore_service as rs
    from app.utils.config_restore import build_restore_service

    monkeypatch.chdir(tmp_path)
    uid = uuid.uuid4()
    od_root = tmp_path / "zzzod"
    write_file(
        od_root / "config" / "one_dragon.yml",
        {"instance_list": [{"idx": 1, "name": "原生实例"}]},
    )
    write_file(instance_dir(od_root, 1) / "game_account.yml", {"account": "native"})
    write_file(instance_dir(od_root, 2) / "game_account.yml", {"account": "slot"})

    ctx = _ctx(str(od_root), uid, 2)
    service = build_restore_service(ctx, rs.RESTORE_SCRIPT_NAME, rs.RESTORE_POOLS)

    # mas：物化 + 信息快照随声明式归档入档
    created = asyncio.run(service.ensure("mas"))
    assert created["created"] is True and created["time"]
    assert asyncio.run(service.list("mas")) == [created["time"]]
    content = asyncio.run(
        service.read_backup_file("mas", created["time"], MAS_USER_INFO_FILE)
    )
    assert "Name" in content["content"]

    # onedragon：原生配置归档（排除 MAS 槽）
    created_od = asyncio.run(service.ensure("onedragon"))
    assert created_od["created"] is True
    files = collect_onedragon_files(od_root)
    assert set(files) == {"one_dragon.yml", "1/game_account.yml"}
    assert len(asyncio.run(service.list("onedragon"))) == 1

    # 未绑定槽（slot<=0）：mas 池列表为空、归档报无变化
    unbound = build_restore_service(
        _ctx(str(od_root), uuid.uuid4(), 0), rs.RESTORE_SCRIPT_NAME, rs.RESTORE_POOLS
    )
    assert asyncio.run(unbound.ensure("mas")) == {"created": False, "time": ""}
    assert asyncio.run(unbound.list("mas")) == []

    # 安装路径未配置：两个池都不抛错，报无变化（mas 用未用过的槽位，池为空）
    no_path = build_restore_service(
        _ctx("", uuid.uuid4(), 3), rs.RESTORE_SCRIPT_NAME, rs.RESTORE_POOLS
    )
    assert asyncio.run(no_path.ensure("mas")) == {"created": False, "time": ""}
    assert asyncio.run(no_path.ensure("onedragon")) == {"created": False, "time": ""}

    # 原生配置不存在（路径配置了但注册表缺失）：onedragon 报无变化
    empty_root = tmp_path / "empty-zzzod"
    empty_root.mkdir()
    bare = build_restore_service(
        _ctx(str(empty_root), uuid.uuid4(), 0), rs.RESTORE_SCRIPT_NAME, rs.RESTORE_POOLS
    )
    assert asyncio.run(bare.ensure("onedragon")) == {"created": False, "time": ""}
    assert get_mas_backup_dir("s-0002", 2, "20260915-000000") is None


def test_preview_account_fields_includes_win_title() -> None:
    """门面预览账号卡：自定义窗口标题两字段进预览，开关转是否。"""

    from app.core.config import AppConfig

    # 缺失时合并默认值：开关否、标题空
    defaults = {f["key"]: f["value"] for f in AppConfig._preview_account_fields({})}
    assert defaults["use_custom_win_title"] == "否"
    assert defaults["custom_win_title"] == ""

    enabled = {
        f["key"]: f["value"]
        for f in AppConfig._preview_account_fields(
            {"use_custom_win_title": True, "custom_win_title": "我的窗口"}
        )
    }
    assert enabled["use_custom_win_title"] == "是"
    assert enabled["custom_win_title"] == "我的窗口"
