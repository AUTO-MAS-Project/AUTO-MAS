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

"""通用脚本配置备份恢复原语的最小回归测试。

General 的 ConfigFile 目录恒按用户（无 owner 解耦、无侧车），原生配置为
用户自填的 ConfigPath（Folder 整目录 / File 单文件两态）。验证两池归档的
指纹去重、恢复闭环、两态语义、文件清单预览，以及 restore/snapshot/preview
池回调的真实调用链。
"""

import asyncio
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.core  # noqa: F401  # 初始化宿主配置
from app.task.general.tools.backup_archive import (
    archive_mas_backup,
    archive_native_backup,
    build_file_list_preview,
    get_mas_backup_dir,
    list_mas_backups,
    list_native_backups,
    mas_config_dir,
    restore_mas_backup,
    restore_native_backup,
)


def test_mas_backup_dedup_and_restore_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mas 池：目录副本归档、指纹去重、恢复闭环（恒按用户，无侧车）。"""

    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0001", "u-0001"
    mas_dir = mas_config_dir(script_id, user_id)
    mas_dir.mkdir(parents=True)
    (mas_dir / "config.ini").write_text("[main]\nmode = 1\n", encoding="utf-8")

    first = archive_mas_backup(script_id, user_id, mas_dir)
    assert first is not None
    assert archive_mas_backup(script_id, user_id, mas_dir) is None  # 指纹去重
    assert len(list_mas_backups(script_id, user_id)) == 1

    # 内容变化再建归档；恢复到第一份（恢复前强制存底 +1）
    (mas_dir / "config.ini").write_text("[main]\nmode = 2\n", encoding="utf-8")
    assert archive_mas_backup(script_id, user_id, mas_dir) is not None
    restore_mas_backup(script_id, user_id, first.name, mas_dir)
    assert "mode = 1" in (mas_dir / "config.ini").read_text("utf-8")
    assert len(list_mas_backups(script_id, user_id)) == 3

    # 空目录/缺失无可归档内容；另一用户看不到这个池
    assert archive_mas_backup(script_id, user_id, tmp_path / "empty") is None
    (tmp_path / "empty").mkdir()
    assert archive_mas_backup(script_id, user_id, tmp_path / "empty") is None
    assert list_mas_backups(script_id, "u-other") == []


def test_native_backup_folder_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """native 池 Folder 态：整目录备份 → 修改 → 恢复闭环。"""

    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "native" / "configs"
    config_path.mkdir(parents=True)
    (config_path / "a.json").write_text("{}", encoding="utf-8")

    first = archive_native_backup(config_path, "Folder")
    assert first is not None
    (config_path / "a.json").write_text('{"v": 2}', encoding="utf-8")
    restore_native_backup(config_path, "Folder", first.name)
    assert (config_path / "a.json").read_text("utf-8") == "{}"
    assert len(list_native_backups(config_path)) == 2  # 恢复前强制存底 +1

    assert archive_native_backup(tmp_path / "nope", "Folder") is None


def test_native_backup_file_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """native 池 File 态：单文件备份与恢复；未知模式报错。"""

    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "native" / "settings.ini"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("a = 1\n", encoding="utf-8")

    first = archive_native_backup(config_path, "File")
    assert first is not None
    config_path.write_text("a = 2\n", encoding="utf-8")
    restore_native_backup(config_path, "File", first.name)
    assert config_path.read_text("utf-8") == "a = 1\n"
    assert len(list_native_backups(config_path)) == 2

    assert archive_native_backup(tmp_path / "nope.ini", "File") is None
    with pytest.raises(ValueError):
        restore_native_backup(config_path, "Unknown", first.name)


def test_file_list_preview(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """预览为文件清单粒度（文件名 + 大小），不解析内容。"""

    monkeypatch.chdir(tmp_path)
    backup = tmp_path / "backup"
    (backup / "sub").mkdir(parents=True)
    (backup / "config.ini").write_text("x", encoding="utf-8")
    (backup / "sub" / "data.json").write_text("{}", encoding="utf-8")

    payload = build_file_list_preview(backup)
    files = {f["name"]: f["size"] for f in payload["files"]}
    assert set(files) == {"config.ini", "sub/data.json"}
    assert files["config.ini"] == "1 B"
    assert files["sub/data.json"].endswith("B")


def test_restore_service_callbacks_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """池回调真实调用链：snapshot → preview → restore（ConfigPath 两态 + 守卫）。"""

    from app.task.general.tools.restore_service import (
        _preview_mas,
        _restore_mas,
        _snapshot_mas,
        _snapshot_native,
    )

    monkeypatch.chdir(tmp_path)
    script_id = "s-0002"
    uid = uuid.uuid4()
    config_path = tmp_path / "native" / "config"
    config_path.mkdir(parents=True)
    (config_path / "cfg.json").write_text("{}", encoding="utf-8")
    user = SimpleNamespace()
    script_config = SimpleNamespace(
        get=lambda g, k: {
            ("Script", "ConfigPath"): str(config_path),
            ("Script", "ConfigPathMode"): "Folder",
        }.get((g, k), ""),
        UserData={uid: user},
    )
    ctx = SimpleNamespace(
        config=None,
        script_config=script_config,
        script_id=script_id,
        user_id=str(uid),
    )

    # mas：snapshot（ConfigFile 不存在 → 不创建）→ 写入后 snapshot → preview → restore
    created = asyncio.run(_snapshot_mas(ctx))
    assert created["created"] is False
    mas_dir = mas_config_dir(script_id, str(uid))
    mas_dir.mkdir(parents=True)
    (mas_dir / "config.ini").write_text("v = 1\n", encoding="utf-8")
    created = asyncio.run(_snapshot_mas(ctx))
    assert created["created"] is True and created["time"]
    ts = created["time"]
    payload = asyncio.run(_preview_mas(ctx, ts))
    assert {f["name"] for f in payload["files"]} == {"config.ini"}

    (mas_dir / "config.ini").write_text("v = 2\n", encoding="utf-8")
    asyncio.run(_restore_mas(ctx, ts))
    assert (mas_dir / "config.ini").read_text("utf-8") == "v = 1\n"
    assert len(list_mas_backups(script_id, str(uid))) == 2  # snapshot + 恢复前存底

    # native：任务级快照（Folder 态）
    created = asyncio.run(_snapshot_native(ctx))
    assert created["created"] is True
    assert len(list_native_backups(config_path)) == 1


def test_get_mas_backup_dir_guards_timestamp(tmp_path: Path) -> None:
    """get_mas_backup_dir 拒绝非法时间戳（路径穿越防护由公共原语保证）。"""

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0003", "u-0003"
    mas_dir = mas_config_dir(script_id, user_id)
    mas_dir.mkdir(parents=True)
    (mas_dir / "c.ini").write_text("x", encoding="utf-8")
    archive_mas_backup(script_id, user_id, mas_dir)
    monkeypatch.undo()

    assert get_mas_backup_dir(script_id, user_id, "..") is None
    assert get_mas_backup_dir(script_id, user_id, "20260101-000000") is None
    with pytest.raises(ValueError):
        restore_mas_backup(script_id, user_id, "..", mas_dir)
