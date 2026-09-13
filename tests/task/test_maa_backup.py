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

"""MAA 配置备份恢复原语的最小回归测试。

用临时目录模拟 MAS 配置目录（owner：Default/用户）与 MAA 安装目录
config/，验证两池归档的指纹去重、恢复闭环（含恢复前强制存底）、运行前
归档的缺目录容错、脚本模式多用户隔离与备份预览摘要的纯逻辑。
"""

import json
from pathlib import Path

import pytest

import app.core  # noqa: F401  # 初始化宿主配置
from app.task.MAA.tools.backup_archive import (
    archive_mas_backup,
    archive_mas_runtime_backup,
    archive_native_backup,
    build_backup_file_summary,
    get_mas_backup_dir,
    list_mas_backups,
    list_native_backups,
    restore_mas_backup,
    restore_native_backup,
)


def test_mas_backup_dedup_and_restore_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mas 池：无备份即建、内容一致跳过、内容/侧车变化再建、恢复闭环。"""

    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0001", "u-0001"
    mas_dir = tmp_path / "data" / script_id / user_id / "ConfigFile"
    mas_dir.mkdir(parents=True)
    (mas_dir / "gui.json").write_text(
        json.dumps({"Current": "Default", "Global": {}}), encoding="utf-8"
    )
    overlay = {"IfFight": True, "IfInfrast": False, "ActivityStageIndex": 3}

    # 首次归档（含侧车）→ 内容一致跳过（指纹去重）
    first = archive_mas_backup(script_id, user_id, mas_dir, overlay=overlay)
    assert first is not None and (first / "gui.json").is_file()
    assert (first / "_mas_overlay.json").is_file()
    assert archive_mas_backup(script_id, user_id, mas_dir, overlay=overlay) is None
    assert len(list_mas_backups(script_id, user_id)) == 1

    # 只改侧车字段（文件未动）→ 指纹变化，新建归档
    overlay2 = {**overlay, "IfFight": False}
    second = archive_mas_backup(script_id, user_id, mas_dir, overlay=overlay2)
    assert second is not None
    assert len(list_mas_backups(script_id, user_id)) == 2

    # 只改文件（侧车同第二份）→ 同样新建归档
    (mas_dir / "gui.new.json").write_text("{}", encoding="utf-8")
    assert archive_mas_backup(script_id, user_id, mas_dir, overlay=overlay2) is not None
    assert len(list_mas_backups(script_id, user_id)) == 3

    # 恢复到第一份：文件与侧车都回到该时点，侧车不留在 ConfigFile
    restored = restore_mas_backup(
        script_id, user_id, first.name, mas_dir, overlay=overlay2
    )
    assert restored == overlay
    assert not (mas_dir / "gui.new.json").exists()
    assert not (mas_dir / "_mas_overlay.json").exists()
    assert len(list_mas_backups(script_id, user_id)) == 4  # 恢复前强制存底 +1

    # 用户池隔离：另一个用户看不到这个池
    assert list_mas_backups(script_id, "u-other") == []

    # mas 目录为空/缺失时无可归档内容，跳过不报错
    assert archive_mas_backup(script_id, user_id, tmp_path / "elsewhere") is None


def test_mas_pool_isolates_script_mode_users(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """脚本模式多用户共享 Default 目录，但池按用户隔离。"""

    monkeypatch.chdir(tmp_path)
    script_id, user_a, user_b = "s-0002", "u-aaa", "u-bbb"
    # 脚本模式：下发源是共享 Default 目录（两个用户指向同一份）
    default_dir = tmp_path / "data" / script_id / "Default" / "ConfigFile"
    default_dir.mkdir(parents=True)
    (default_dir / "gui.json").write_text(
        json.dumps({"Current": "Default"}), encoding="utf-8"
    )

    first = archive_mas_backup(script_id, user_a, default_dir)
    assert first is not None
    (default_dir / "gui.json").write_text(
        json.dumps({"Current": "方案B"}), encoding="utf-8"
    )
    second = archive_mas_backup(script_id, user_b, default_dir)
    assert second is not None

    # 两用户池完全隔离：各只看到自己的备份
    assert list_mas_backups(script_id, user_a) == [first.name]
    assert list_mas_backups(script_id, user_b) == [second.name]

    # A 恢复自己的备份：文件回滚到 Default
    restore_mas_backup(script_id, user_a, first.name, default_dir)
    assert json.loads((default_dir / "gui.json").read_text("utf-8")) == {
        "Current": "Default"
    }
    assert len(list_mas_backups(script_id, user_a)) == 2  # 恢复前强制存底 +1


def test_native_backup_folder_restore_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """native 池：整目录备份 → 修改 → 恢复闭环；缺失/空目录跳过。"""

    monkeypatch.chdir(tmp_path)

    config_dir = tmp_path / "native" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "gui.json").write_text(
        json.dumps({"Current": "Default"}), encoding="utf-8"
    )
    first = archive_native_backup(config_dir)
    assert first is not None
    (config_dir / "gui.json").write_text(
        json.dumps({"Current": "方案X"}), encoding="utf-8"
    )
    restore_native_backup(config_dir, first.name)
    assert json.loads((config_dir / "gui.json").read_text("utf-8")) == {
        "Current": "Default"
    }
    assert len(list_native_backups(config_dir)) == 2  # 恢复前强制存底 +1

    # 缺失配置/空目录跳过（无可归档内容），不产生归档条目
    assert archive_native_backup(tmp_path / "nope") is None
    empty = tmp_path / "empty"
    empty.mkdir()
    assert archive_native_backup(empty) is None
    assert list_native_backups(tmp_path / "nope") == []


def test_runtime_backup_skips_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """运行前归档：mas 目录缺失静默跳过，绝不抛错；存在则正常归档。"""

    monkeypatch.chdir(tmp_path)
    archive_mas_runtime_backup("s-0003", "u-0003", tmp_path / "nope")
    assert list_mas_backups("s-0003", "u-0003") == []

    mas_dir = tmp_path / "data" / "s-0003" / "u-0003" / "ConfigFile"
    mas_dir.mkdir(parents=True)
    (mas_dir / "a.json").write_text("{}", encoding="utf-8")
    archive_mas_runtime_backup("s-0003", "u-0003", mas_dir)
    assert len(list_mas_backups("s-0003", "u-0003")) == 1


def test_preview_summary_keeps_stable_fields(tmp_path: Path) -> None:
    """native 预览：旧/新两文件分别展示当前方案/连接地址/客户端/启动开关。"""

    backup = tmp_path / "backup"
    backup.mkdir()
    (backup / "gui.json").write_text(
        json.dumps(
            {
                "Current": "Default",
                "Configurations": {
                    "Default": {
                        "Connect.Address": "127.0.0.1:16384",
                        "Start.ClientType": "Official",
                        "Start.StartGame": "True",
                    },
                    "B": {},
                },
            }
        ),
        encoding="utf-8",
    )
    (backup / "gui.new.json").write_text(
        json.dumps(
            {
                "Current": "Default",
                "Configurations": {
                    "Default": {
                        "Gui": {
                            "ConnectSettings": {"Address": "127.0.0.1:16384"},
                            "RuntimeSettings": {"ClientType": 1, "StartGame": True},
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (backup / "broken.json").write_text("{oops", encoding="utf-8")
    (backup / "readme.txt").write_text("skip me", encoding="utf-8")
    (backup / "other_config.json").write_text(
        json.dumps({"Anything": 1}), encoding="utf-8"
    )

    files = build_backup_file_summary(backup)
    by_name = {f["name"]: f for f in files}
    # 白名单外/坏 JSON/非 JSON 文件不进预览
    assert set(by_name) == {"gui.json", "gui.new.json"}

    gui = by_name["gui.json"]
    assert gui["label"] == "MAA 设置"
    assert {row["key"]: row["value"] for row in gui["summary"]} == {
        "当前方案": "Default",
        "连接地址": "127.0.0.1:16384",
        "客户端": "官服",
        "启动游戏": "True",
    }

    gui_new = by_name["gui.new.json"]
    assert gui_new["label"] == "MAA 设置（新版）"
    assert {row["key"]: row["value"] for row in gui_new["summary"]} == {
        "当前方案": "Default",
        "连接地址": "127.0.0.1:16384",
        "客户端": "B服",
        "启动游戏": "是",
    }


def test_overlay_preview_shows_task_fields(tmp_path: Path) -> None:
    """侧车预览：展示备份时点的 MAS 页面任务配置（开关/序号翻译）。"""

    from app.task.MAA.tools.backup_archive import build_overlay_summary

    overlay = {
        "IfStartUp": True,
        "IfFight": False,
        "IfGreenTicketStore": True,
        "ActivityStageIndex": 3,
    }
    rows = {row["key"]: row["value"] for row in build_overlay_summary(overlay)}
    assert rows == {
        "自动唤醒": "是",
        "理智作战": "否",
        "绿票商店": "是",
        "活动关卡序号": "3",
    }
    # 未知键/缺失键不进摘要
    assert "不存在的字段" not in rows


def test_get_mas_backup_dir_guards_timestamp(tmp_path: Path) -> None:
    """get_mas_backup_dir 拒绝非法时间戳（路径穿越防护由公共原语保证）。"""

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0004", "u-0004"
    mas_dir = tmp_path / "data" / script_id / user_id / "ConfigFile"
    mas_dir.mkdir(parents=True)
    (mas_dir / "a.json").write_text("{}", encoding="utf-8")
    archive_mas_backup(script_id, user_id, mas_dir)
    monkeypatch.undo()

    assert get_mas_backup_dir(script_id, user_id, "20260913-000000") is None
    assert get_mas_backup_dir(script_id, user_id, "../../../evil") is None
