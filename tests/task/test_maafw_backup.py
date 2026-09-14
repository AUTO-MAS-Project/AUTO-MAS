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

"""MaaFW 配置备份恢复原语的最小回归测试。

MaaFW 与 M9A 同属 MaaFramework 线：mas 池是纯字段侧车（无 per-user 目录，
用户配置是字段），native 池 = 项目 config/ + interface.json。验证侧车
归档/回填、跨用户隔离、native 闭环、预览分区，以及池回调真实调用链。
"""

import asyncio
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.core  # noqa: F401  # 初始化宿主配置
from app.task.MaaFW.tools.backup_archive import (
    archive_mas_backup,
    archive_native_backup,
    build_native_preview,
    build_overlay_preview,
    get_mas_backup_dir,
    group_overlay,
    list_mas_backups,
    list_native_backups,
    read_overlay_values,
    restore_mas_backup,
    restore_native_backup,
)

_INTERFACE = {
    "version": "1.0",
    "tasks": {
        "每日清体力": {"name": "每日清体力"},
        "刷圣遗物": {"name": "刷圣遗物"},
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


def _make_project(tmp_path: Path) -> Path:
    """搭一个最小 MaaFW 项目（interface.json + config/maa_option.json）。"""

    project = tmp_path / "MaaFWProject"
    (project / "config").mkdir(parents=True)
    (project / "interface.json").write_text(
        json.dumps(_INTERFACE, ensure_ascii=False), encoding="utf-8"
    )
    (project / "config" / "maa_option.json").write_text(
        json.dumps({"controller": "Adb"}), encoding="utf-8"
    )
    return project


def test_mas_overlay_grouping_and_dedup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """侧车归档：指纹去重、Task/Device 可回填、Mode 仅预览。"""

    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0001", "u-0001"
    user = SimpleNamespace(
        get=lambda g, k: {
            ("Info", "Mode"): "用户",
            ("Info", "IfQuickConfig"): True,
            ("Info", "Account"): "13800001234",
            ("Task", "SelectedPreset"): "__auto_mas_custom_preset__",
            ("Task", "TaskSnapshot"): json.dumps(
                {
                    "taskOrder": ["每日清体力", "刷圣遗物"],
                    "taskChecked": {"每日清体力": True, "刷圣遗物": False},
                }
            ),
            ("Device", "AdbAddress"): "127.0.0.1:5555",
        }.get((g, k))
    )

    overlay = read_overlay_values(user)
    first = archive_mas_backup(script_id, user_id, overlay)
    assert first is not None
    assert archive_mas_backup(script_id, user_id, overlay) is None  # 指纹去重
    changed = dict(overlay, AdbAddress="127.0.0.1:5556")
    assert archive_mas_backup(script_id, user_id, changed) is not None
    assert len(list_mas_backups(script_id, user_id)) == 2

    grouped = group_overlay(overlay)
    # Mode 仅预览不回填；Info 组保留 IfQuickConfig
    assert set(grouped) == {"Info", "Task", "Device"}
    assert grouped["Info"]["IfQuickConfig"] is True
    assert "Mode" not in grouped["Info"]
    assert grouped["Task"]["SelectedPreset"] == "__auto_mas_custom_preset__"
    assert grouped["Device"]["AdbAddress"] == "127.0.0.1:5555"


def test_mas_restore_roundtrip_with_user_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mas 恢复：侧车回传、回填分组、跨用户隔离。"""

    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0002", "u-0001"
    overlay = {
        "SelectedPreset": "p1",
        "TaskSnapshot": json.dumps({"taskOrder": ["刷圣遗物"], "taskChecked": {"刷圣遗物": True}}),
        "AdbAddress": "127.0.0.1:5555",
        "Mode": "用户",
    }
    first = archive_mas_backup(script_id, user_id, overlay)
    assert first is not None

    restored = restore_mas_backup(script_id, user_id, first.name)
    assert restored == overlay
    grouped = group_overlay(restored)
    # Mode 仅预览不回填：Info 组无回填字段，整组不出现
    assert set(grouped) == {"Task", "Device"}
    assert grouped["Task"]["SelectedPreset"] == "p1"
    assert grouped["Device"]["AdbAddress"] == "127.0.0.1:5555"

    other = "u-0002"
    assert list_mas_backups(script_id, other) == []
    archive_mas_backup(script_id, other, overlay, force=True)
    assert list_mas_backups(script_id, other) != []
    assert len(list_mas_backups(script_id, user_id)) == 1  # 用户池不被 other 影响


def test_native_backup_restore_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """native 闭环：归档项目 config/ + interface.json → 改坏 → 恢复找回。"""

    monkeypatch.chdir(tmp_path)
    project = _make_project(tmp_path)

    first = archive_native_backup(project)
    assert first is not None
    assert (first / "interface.json").is_file()
    assert (first / "config" / "maa_option.json").is_file()

    (project / "interface.json").write_text('{"broken": true}', encoding="utf-8")
    (project / "config" / "maa_option.json").write_text(
        json.dumps({"controller": "坏"}), encoding="utf-8"
    )
    restore_native_backup(project, first.name)
    assert json.loads((project / "interface.json").read_text("utf-8")) == _INTERFACE
    assert json.loads(
        (project / "config" / "maa_option.json").read_text("utf-8")
    ) == {"controller": "Adb"}
    assert len(list_native_backups(project)) == 2  # 恢复前存底 +1

    # 项目缺 config/ 与 interface.json 时跳过
    assert archive_native_backup(tmp_path / "nope") is None


def test_native_preview_reads_interface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """native 预览：反读 interface.json 的任务/版本概览。"""

    monkeypatch.chdir(tmp_path)
    project = _make_project(tmp_path)
    first = archive_native_backup(project)
    assert first is not None

    payload = build_native_preview(project, first.name)
    sections = {s["name"]: s for s in payload["sections"]}
    rows = {row["key"]: row["value"] for row in sections["maafw"]["rows"]}
    assert rows["interface 版本"] == "1.0"
    assert rows["任务"] == "每日清体力、刷圣遗物"


def test_overlay_preview_sections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mas 预览：分区（MAS 独有 / MaaFW 配置 / 设备覆盖）+ 已启用任务罗列。"""

    monkeypatch.chdir(tmp_path)
    payload = build_overlay_preview(
        {
            "Mode": "用户",
            "IfQuickConfig": True,
            "Account": "13800001234",
            "SelectedPreset": "p1",
            "TaskSnapshot": json.dumps(
                {
                    "taskOrder": ["每日清体力", "刷圣遗物"],
                    "taskChecked": {"每日清体力": True, "刷圣遗物": False},
                }
            ),
            "AdbAddress": "127.0.0.1:5555",
        }
    )
    sections = {s["name"]: s for s in payload["sections"]}
    assert set(sections) == {"mas-only", "maafw", "device"}
    mas_rows = {row["key"]: row["value"] for row in sections["mas-only"]["rows"]}
    assert mas_rows == {"配置来源": "用户", "启用快速配置": "开启"}
    task_rows = {row["key"]: row["value"] for row in sections["maafw"]["rows"]}
    assert task_rows["当前方案"] == "p1"
    assert task_rows["已启用任务"] == "每日清体力"  # 刷圣遗物禁用不出现
    assert task_rows["账号"] == "138****1234"  # 脱敏
    device_rows = {row["key"]: row["value"] for row in sections["device"]["rows"]}
    assert device_rows == {"ADB 地址": "127.0.0.1:5555"}


def test_restore_service_callbacks_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """池回调真实调用链：snapshot → preview → restore（回填 + native 闭环）。"""

    from app.task.MaaFW.tools.restore_service import (
        _preview_mas,
        _restore_mas,
        _restore_native,
        _snapshot_mas,
        _snapshot_native,
    )

    monkeypatch.chdir(tmp_path)
    script_id = "s-0003"
    uid = uuid.uuid4()
    project = _make_project(tmp_path)
    user = _FakeUser(
        {
            "Info.Mode": "用户",
            "Task.SelectedPreset": "__auto_mas_custom_preset__",
            "Task.TaskSnapshot": json.dumps(
                {"taskOrder": ["刷圣遗物"], "taskChecked": {"刷圣遗物": True}}
            ),
        }
    )
    script_config = SimpleNamespace(
        get=lambda g, k: str(project) if (g, k) == ("Info", "Path") else "",
        UserData={uid: user},
    )
    ctx = SimpleNamespace(
        config=None,
        script_config=script_config,
        script_id=script_id,
        user_id=str(uid),
    )

    created = asyncio.run(_snapshot_mas(ctx))
    assert created["created"] is True and created["time"]
    payload = asyncio.run(_preview_mas(ctx, created["time"]))
    assert "maafw" in {s["name"] for s in payload["sections"]}

    asyncio.run(_restore_mas(ctx, created["time"]))
    assert len(user.updated) == 1
    assert user.updated[0]["Task"]["SelectedPreset"] == "__auto_mas_custom_preset__"
    # Mode 仅预览不回填：Info 组无回填字段，整组不出现
    assert "Info" not in user.updated[0]

    # native：快照 + 恢复闭环
    created_native = asyncio.run(_snapshot_native(ctx))
    assert created_native["created"] is True
    asyncio.run(_restore_native(ctx, created_native["time"]))
    assert list_native_backups(project)


def test_get_mas_backup_dir_guards_timestamp(tmp_path: Path) -> None:
    """get_mas_backup_dir 拒绝非法时间戳（路径穿越防护由公共原语保证）。"""

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0004", "u-0003"
    archive_mas_backup(script_id, user_id, {"SelectedPreset": "p1"})
    monkeypatch.undo()

    assert get_mas_backup_dir(script_id, user_id, "..") is None
    assert get_mas_backup_dir(script_id, user_id, "20260101-000000") is None
    with pytest.raises(ValueError):
        restore_mas_backup(script_id, user_id, "..")
