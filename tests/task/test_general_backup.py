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
指纹去重、恢复闭环、两态语义，以及 service 级真实调用链（声明式快照、
基座标准 files 注入）。
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

    # 内容变化再建归档；恢复到第一份（恢复前存底与最新份一致 → 跳过）
    (mas_dir / "config.ini").write_text("[main]\nmode = 2\n", encoding="utf-8")
    assert archive_mas_backup(script_id, user_id, mas_dir) is not None
    restore_mas_backup(script_id, user_id, first.name, mas_dir)
    assert "mode = 1" in (mas_dir / "config.ini").read_text("utf-8")
    assert len(list_mas_backups(script_id, user_id)) == 2

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

    first = archive_native_backup("s-0001", config_path, "Folder")
    assert first is not None
    (config_path / "a.json").write_text('{"v": 2}', encoding="utf-8")
    restore_native_backup("s-0001", config_path, "Folder", first.name)
    assert (config_path / "a.json").read_text("utf-8") == "{}"
    assert len(list_native_backups("s-0001", config_path)) == 2  # 恢复前强制存底 +1

    assert archive_native_backup("s-0001", tmp_path / "nope", "Folder") is None


def test_native_backup_file_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """native 池 File 态：单文件备份与恢复；未知模式报错。"""

    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "native" / "settings.ini"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("a = 1\n", encoding="utf-8")

    first = archive_native_backup("s-0001", config_path, "File")
    assert first is not None
    config_path.write_text("a = 2\n", encoding="utf-8")
    restore_native_backup("s-0001", config_path, "File", first.name)
    assert config_path.read_text("utf-8") == "a = 1\n"
    assert len(list_native_backups("s-0001", config_path)) == 2

    assert archive_native_backup("s-0001", tmp_path / "nope.ini", "File") is None
    with pytest.raises(ValueError):
        restore_native_backup("s-0001", config_path, "Unknown", first.name)


def test_restore_service_callbacks_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """service 级真实调用链：声明式 snapshot → preview → restore（两态 + 守卫）。"""

    from app.task.general.tools.restore_service import (
        RESTORE_POOLS,
        RESTORE_SCRIPT_NAME,
    )
    from app.utils.config_restore import RestoreContext, build_restore_service

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
    ctx = RestoreContext(
        config=None,
        script_config=script_config,
        script_id=script_id,
        user_id=str(uid),
    )
    service = build_restore_service(ctx, RESTORE_SCRIPT_NAME, RESTORE_POOLS)

    # mas：snapshot（ConfigFile 不存在 → 不创建）→ 写入后 snapshot → preview → restore
    created = asyncio.run(service.ensure("mas"))
    assert created["created"] is False
    mas_dir = mas_config_dir(script_id, str(uid))
    mas_dir.mkdir(parents=True)
    (mas_dir / "config.ini").write_text("v = 1\n", encoding="utf-8")
    created = asyncio.run(service.ensure("mas"))
    assert created["created"] is True and created["time"]
    ts = created["time"]
    payload = asyncio.run(service.preview("mas", ts))
    # 无定制 preview：文件清单由基座统一注入标准 files 键（兜底节渲染）
    assert {f["path"] for f in payload["files"] if f["path"] != "_mas_mode"} == {
        "config.ini"
    }
    # 声明式 read_file（基座从 backup_root 派生）
    content = asyncio.run(service.read_backup_file("mas", ts, "config.ini"))
    assert content["content"] == "v = 1\n"

    (mas_dir / "config.ini").write_text("v = 2\n", encoding="utf-8")
    asyncio.run(service.restore("mas", ts))
    assert (mas_dir / "config.ini").read_text("utf-8") == "v = 1\n"
    assert len(list_mas_backups(script_id, str(uid))) == 2  # snapshot + 恢复前存底

    # native：任务级快照（Folder 态，基座注入文件清单）
    created_native = asyncio.run(service.ensure("native"))
    assert created_native["created"] is True
    payload_native = asyncio.run(service.preview("native", created_native["time"]))
    assert {f["path"] for f in payload_native["files"]} == {"cfg.json"}
    assert len(list_native_backups(script_id, config_path)) == 1


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
