#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public
#   License along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""BAAH 配置备份恢复原语的最小回归测试。

BAAH 的用户身份 = BAAH 侧 JSON 文件名（Info.ConfigName），MAS 不持有配置
本体：mas 池是元字段侧车（ConfigName 可回填，Mode/IfQuickConfig 仅预览），
native 池按当前 ConfigName 动态解析目标文件（用户配置 + 软件配置）。
验证侧车归档/回填、native 闭环（含配置名改名后恢复覆盖语义）、关键字段
反读预览，以及池回调真实调用链。
"""

import asyncio
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.core  # noqa: F401  # 初始化宿主配置
from app.task.BAAH.tools.backup_archive import (
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


class _FakeUser:
    """鸭子类型用户配置（read_overlay_values / update 回填验证）。"""

    def __init__(self, values: dict):
        self._values = values
        self.updated: list[dict] = []

    def get(self, group: str, key: str):
        return self._values.get(f"{group}.{key}")

    async def update(self, grouped: dict):
        self.updated.append(grouped)


_USER_CONFIG = {
    "CLOSE_BAAH_FINISH": True,
    "CLOSE_EMULATOR_FINISH": False,
    "TARGET_IP_PATH": "127.0.0.1",
    "TARGET_PORT": 5555,
    "TASK_ORDER": ["清momotalk", "普通推图", "咖啡馆"],
    "TASK_ACTIVATE": [True, True, False],
}


def _make_baah_install(tmp_path: Path) -> Path:
    """搭一个最小 BAAH 安装（exe 占位 + 配置目录 + 软件配置）。"""

    root = tmp_path / "BAAH"
    root.mkdir(parents=True)
    (root / "BAAH.exe").write_bytes(b"")
    config_dir = root / "BAAH_CONFIGS"
    config_dir.mkdir()
    software_dir = root / "DATA" / "CONFIGS"
    software_dir.mkdir(parents=True)
    (software_dir / "software_config.json").write_text(
        json.dumps({"SAVE_LOG_TO_FILE": True}), encoding="utf-8"
    )
    return config_dir


def test_mas_overlay_grouping_and_dedup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """侧车归档：指纹去重、ConfigName 可回填、Mode/IfQuickConfig 仅预览。"""

    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0001", "u-0001"
    user = SimpleNamespace(
        get=lambda g, k: {
            ("Info", "Mode"): "用户",
            ("Info", "IfQuickConfig"): True,
            ("Info", "ConfigName"): "account1",
        }.get((g, k))
    )

    overlay = read_overlay_values(user)
    first = archive_mas_backup(script_id, user_id, overlay)
    assert first is not None
    assert archive_mas_backup(script_id, user_id, overlay) is None  # 指纹去重
    assert len(list_mas_backups(script_id, user_id)) == 1

    grouped = group_overlay(overlay)
    assert set(grouped) == {"Info"}
    assert grouped["Info"]["ConfigName"] == "account1"  # 可回填
    assert "Mode" not in grouped["Info"]
    assert "IfQuickConfig" not in grouped["Info"]


def test_native_backup_restore_loop_with_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """native 闭环：归档 → 修改 → 恢复；配置改名后恢复写到新名文件。"""

    monkeypatch.chdir(tmp_path)
    config_dir = _make_baah_install(tmp_path)
    user_id = "u-0001"
    (config_dir / "account1.json").write_text(
        json.dumps(_USER_CONFIG, ensure_ascii=False), encoding="utf-8"
    )

    first = archive_native_backup(config_dir, "account1", user_id)
    assert first is not None
    assert list_native_backups(config_dir, user_id) == [first.name]

    # 托管键被改坏（模拟 jsoneditor 误改）→ 恢复找回
    (config_dir / "account1.json").write_text(
        json.dumps({"CLOSE_BAAH_FINISH": False}), encoding="utf-8"
    )
    archived_name = restore_native_backup(config_dir, "account1", user_id, first.name)
    assert archived_name == "account1"
    assert json.loads((config_dir / "account1.json").read_text("utf-8")) == _USER_CONFIG
    assert len(list_native_backups(config_dir, user_id)) == 2  # 恢复前强制存底 +1

    # 改名后恢复：备份内容写到新名文件（覆盖语义）
    (config_dir / "account2.json").write_text("{}", encoding="utf-8")
    restore_native_backup(config_dir, "account2", user_id, first.name)
    assert json.loads((config_dir / "account2.json").read_text("utf-8")) == _USER_CONFIG

    # 缺失/非法目标跳过
    assert archive_native_backup(config_dir, "ghost", user_id) is None  # 未创建
    assert archive_native_backup(config_dir, "", user_id) is None  # 空名
    assert archive_native_backup(config_dir, "../escape", user_id) is None  # 路径穿越

    # 跨用户隔离：另一个用户的池互不可见（§1.1.1 教训）
    other = "u-0002"
    assert list_native_backups(config_dir, other) == []
    (config_dir / "account1.json").write_text(
        json.dumps(_USER_CONFIG, ensure_ascii=False), encoding="utf-8"
    )
    archive_native_backup(config_dir, "account1", other, force=True)
    assert list_native_backups(config_dir, other) != []
    assert len(list_native_backups(config_dir, user_id)) == 3  # 用户池不被 other 影响


def test_native_preview_reads_key_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """native 预览：目标设备/已启用任务/BAAH 行为键/软件配置反读。"""

    monkeypatch.chdir(tmp_path)
    config_dir = _make_baah_install(tmp_path)
    user_id = "u-0001"
    (config_dir / "account1.json").write_text(
        json.dumps(_USER_CONFIG, ensure_ascii=False), encoding="utf-8"
    )
    first = archive_native_backup(config_dir, "account1", user_id)
    assert first is not None

    payload = build_native_preview(config_dir, user_id, first.name)
    sections = {s["name"]: s for s in payload["sections"]}
    assert set(sections) == {"baah", "software", "details"}
    rows = {row["key"]: row["value"] for row in sections["baah"]["rows"]}
    assert rows["配置文件名"] == "account1"  # 备份内实际文件名（与当前名无关）
    assert rows["目标设备"] == "127.0.0.1:5555"
    # 已启用任务 = TASK_ORDER + TASK_ACTIVATE 对位过滤（咖啡馆禁用不出现）
    assert rows["已启用任务"] == "清momotalk、普通推图"
    detail = {g["name"]: g for g in sections["details"]["groups"]}
    behavior = {row["key"]: row["value"] for row in detail["BAAH 行为"]["rows"]}
    assert behavior["运行结束自动关闭 BAAH"] == "开启"
    assert behavior["结束自动关闭模拟器"] == "关闭"
    software = {row["key"]: row["value"] for row in sections["software"]["rows"]}
    assert software["日志写文件"] == "开启"


def test_overlay_preview_sections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mas 预览：分区（MAS 独有 / BAAH 配置）。"""

    monkeypatch.chdir(tmp_path)
    payload = build_overlay_preview(
        {"Mode": "用户", "IfQuickConfig": True, "ConfigName": "account1"}
    )
    sections = {s["name"]: s for s in payload["sections"]}
    assert set(sections) == {"mas-only", "baah"}
    mas_rows = {row["key"]: row["value"] for row in sections["mas-only"]["rows"]}
    assert mas_rows == {"配置文件来源": "用户", "启用快速配置": "开启"}
    baah_rows = {row["key"]: row["value"] for row in sections["baah"]["rows"]}
    assert baah_rows == {"BAAH 配置文件名": "account1"}


def test_restore_service_callbacks_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """池回调真实调用链：snapshot → preview → restore（签名回归 + 回填）。"""

    from app.task.BAAH.tools.restore_service import (
        _preview_mas,
        _restore_mas,
        _snapshot_mas,
        _snapshot_native,
    )

    monkeypatch.chdir(tmp_path)
    script_id = "s-0002"
    uid = uuid.uuid4()
    config_dir = _make_baah_install(tmp_path)
    (config_dir / "account1.json").write_text(
        json.dumps(_USER_CONFIG, ensure_ascii=False), encoding="utf-8"
    )
    user = _FakeUser(
        {
            "Info.Mode": "用户",
            "Info.IfQuickConfig": True,
            "Info.ConfigName": "account1",
        }
    )
    script_config = SimpleNamespace(
        get=lambda g, k: (
            str(config_dir.parent / "BAAH.exe")
            if (g, k) == ("Script", "BAAHPath")
            else ""
        ),
        UserData={uid: user},
    )
    ctx = SimpleNamespace(
        config=None,
        script_config=script_config,
        script_id=script_id,
        user_id=str(uid),
    )

    # mas：snapshot → preview → restore 回填（Mode/IfQuickConfig 排除）
    created = asyncio.run(_snapshot_mas(ctx))
    assert created["created"] is True and created["time"]
    payload = asyncio.run(_preview_mas(ctx, created["time"]))
    assert "baah" in {s["name"] for s in payload["sections"]}

    asyncio.run(_restore_mas(ctx, created["time"]))
    assert len(user.updated) == 1
    assert user.updated[0]["Info"]["ConfigName"] == "account1"
    assert "Mode" not in user.updated[0]["Info"]
    assert len(list_mas_backups(script_id, str(uid))) == 2  # snapshot + 恢复前存底

    # native：snapshot（按 ConfigName 动态解析）+ 空名用户报错
    created = asyncio.run(_snapshot_native(ctx))
    assert created["created"] is True
    empty_user = SimpleNamespace(
        get=lambda g, k: {("Info", "ConfigName"): ""}.get((g, k))
    )
    ctx_empty = SimpleNamespace(
        config=None,
        script_config=SimpleNamespace(
            get=lambda g, k: str(config_dir.parent / "BAAH.exe"),
            UserData={uid: empty_user},
        ),
        script_id=script_id,
        user_id=str(uid),
    )
    with pytest.raises(ValueError):
        asyncio.run(_snapshot_native(ctx_empty))


def test_get_mas_backup_dir_guards_timestamp(tmp_path: Path) -> None:
    """get_mas_backup_dir 拒绝非法时间戳（路径穿越防护由公共原语保证）。"""

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0003", "u-0003"
    archive_mas_backup(script_id, user_id, {"ConfigName": "a"})
    monkeypatch.undo()

    assert get_mas_backup_dir(script_id, user_id, "..") is None
    assert get_mas_backup_dir(script_id, user_id, "20260101-000000") is None
    with pytest.raises(ValueError):
        restore_mas_backup(script_id, user_id, "..")
