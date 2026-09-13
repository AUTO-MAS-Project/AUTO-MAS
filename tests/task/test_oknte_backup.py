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

"""OK-NTE 配置备份恢复原语的最小回归测试。

用临时目录模拟 MAS 用户 ConfigFile 与 ok-nte 原生配置（Folder/File 两种
模式），验证两池归档的指纹去重、恢复闭环（含恢复前强制存底）、运行前
归档的缺目录容错与备份预览摘要的纯逻辑。
"""

import json
from pathlib import Path

import pytest

from app.task.OkNte.tools.backup_archive import (
    archive_mas_backup,
    archive_mas_runtime_backup,
    archive_native_backup,
    build_backup_file_summary,
    collect_config_files,
    list_mas_backups,
    list_native_backups,
    restore_mas_backup,
    restore_native_backup,
)
from app.utils.config_archive import _archive


def test_collect_config_files_folder_and_file(tmp_path: Path) -> None:
    """文件集收集：Folder 整目录、File 单文件、缺失返回 None。"""

    folder = tmp_path / "configs"
    folder.mkdir()
    (folder / "a.json").write_text("{}", encoding="utf-8")
    files = collect_config_files(folder, "Folder")
    assert files is not None and list(files) == ["a.json"]

    single = tmp_path / "conf.json"
    single.write_text("{}", encoding="utf-8")
    files = collect_config_files(single, "File")
    assert files is not None and list(files) == ["conf.json"]

    assert collect_config_files(tmp_path / "missing", "Folder") is None
    assert collect_config_files(tmp_path / "missing.json", "File") is None
    empty = tmp_path / "empty"
    empty.mkdir()
    assert collect_config_files(empty, "Folder") is None
    # 空配置路径解析为当前目录（Path('') → '.'），绝不整树归档
    assert collect_config_files(Path(""), "Folder") is None
    assert collect_config_files(Path(""), "File") is None


def test_mas_backup_dedup_and_restore_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mas 池：无备份即建、内容一致跳过、内容变化再建、恢复闭环可找回。"""

    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0001", "u-0001"
    mas_dir = tmp_path / "data" / script_id / user_id / "ConfigFile"
    mas_dir.mkdir(parents=True)
    (mas_dir / "DailyRoutineTask.json").write_text(
        json.dumps({"Routine Items": [], "Exit After Task": True}),
        encoding="utf-8",
    )

    # 首次归档 → 内容一致跳过（指纹去重）
    first = archive_mas_backup(script_id, user_id, mas_dir)
    assert first is not None and (first / "DailyRoutineTask.json").is_file()
    assert archive_mas_backup(script_id, user_id, mas_dir) is None
    assert len(list_mas_backups(script_id, user_id)) == 1

    # 内容变化（用户改坏配置）→ 新建归档
    (mas_dir / "CoffeeTask.json").write_text("{}", encoding="utf-8")
    assert archive_mas_backup(script_id, user_id, mas_dir) is not None
    assert len(list_mas_backups(script_id, user_id)) == 2

    # 恢复到第一份：CoffeeTask.json 回到不存在；恢复前的当前态被强制存底
    restore_mas_backup(script_id, user_id, first.name, mas_dir)
    assert not (mas_dir / "CoffeeTask.json").exists()
    assert len(list_mas_backups(script_id, user_id)) == 3

    # mas 目录为空/缺失时无可归档内容，跳过不报错
    empty_dir = tmp_path / "elsewhere"
    assert archive_mas_backup(script_id, user_id, empty_dir) is None


def test_native_backup_folder_and_file_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """native 池：Folder 整目录恢复、File 单文件写回；缺失跳过。"""

    monkeypatch.chdir(tmp_path)

    # Folder 模式：备份 → 修改 → 恢复闭环
    config_dir = tmp_path / "native" / "configs"
    config_dir.mkdir(parents=True)
    (config_dir / "Basic Options.json").write_text("{}", encoding="utf-8")
    first = archive_native_backup(config_dir, "Folder")
    assert first is not None
    (config_dir / "Basic Options.json").write_text('{"bad": true}', encoding="utf-8")
    restore_native_backup(config_dir, first.name, "Folder")
    assert json.loads((config_dir / "Basic Options.json").read_text("utf-8")) == {}
    assert len(list_native_backups(config_dir)) == 2  # 恢复前强制存底 +1

    # File 模式：单文件备份与写回
    config_file = tmp_path / "native" / "conf.json"
    config_file.write_text('{"v": 1}', encoding="utf-8")
    file_backup = archive_native_backup(config_file, "File")
    assert file_backup is not None
    config_file.write_text('{"v": 999}', encoding="utf-8")
    restore_native_backup(config_file, file_backup.name, "File")
    assert json.loads(config_file.read_text("utf-8")) == {"v": 1}

    # 缺失配置跳过（无可归档内容），不产生归档条目
    assert archive_native_backup(tmp_path / "nope", "Folder") is None
    assert archive_native_backup(tmp_path / "nope.json", "File") is None


def test_runtime_backups_skip_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """运行前归档：mas 目录 / 原生配置任一缺失都静默跳过，绝不抛错。"""

    monkeypatch.chdir(tmp_path)
    missing_native = tmp_path / "no-config-path"
    # mas 目录不存在：不抛错、不产生归档
    archive_mas_runtime_backup("s-0003", "u-0003")
    assert list_mas_backups("s-0003", "u-0003") == []

    # 原生配置缺失：native 归档（manager.prepare 调用）同样跳过
    assert archive_native_backup(missing_native, "Folder") is None
    assert list_native_backups(missing_native) == []

    # mas 存在：正常归档（native 仍缺失，互不影响）
    mas_dir = tmp_path / "data" / "s-0003" / "u-0003" / "ConfigFile"
    mas_dir.mkdir(parents=True)
    (mas_dir / "a.json").write_text("{}", encoding="utf-8")
    archive_mas_runtime_backup("s-0003", "u-0003")
    assert len(list_mas_backups("s-0003", "u-0003")) == 1
    assert list_native_backups(missing_native) == []


def test_force_archive_protects_selected_backup(tmp_path: Path) -> None:
    """恢复前 force 存底不清掉用户选中的 keep 之外的最旧备份。"""

    from app.utils.config_archive import list_times

    store = tmp_path / "pool"
    ts_book: list[str] = []
    for i in range(3):
        src = tmp_path / f"src{i}"
        src.mkdir()
        (src / "a.json").write_text(f"v{i}", encoding="utf-8")
        dest = _archive({"a.json": src / "a.json"}, store, keep=2, force=True)
        assert dest is not None
        ts_book.append(dest.name)

    (tmp_path / "src3").mkdir()
    (tmp_path / "src3" / "a.json").write_text("v3", encoding="utf-8")
    assert (
        _archive({"a.json": tmp_path / "src3" / "a.json"}, store, keep=2, force=True)
        is not None
    )
    assert ts_book[0] in list_times(store)


def test_backup_file_summary(tmp_path: Path) -> None:
    """预览摘要：Routine Items 展开、标量截断、非 JSON 与空摘要文件跳过。"""

    backup = tmp_path / "backup"
    backup.mkdir()
    (backup / "DailyRoutineTask.json").write_text(
        json.dumps(
            {
                "Routine Items": [
                    {"id": "daily_anomaly", "enabled": True},
                    {"id": "coffee", "enabled": True},
                    {"id": "gift", "enabled": False},
                ],
                "Exit After Task": True,
                "_enabled": True,
            }
        ),
        encoding="utf-8",
    )
    (backup / "CoffeeTask.json").write_text(
        json.dumps({"模式": "自动化", "领取收益": False}), encoding="utf-8"
    )
    (backup / "nested.json").write_text(
        json.dumps({"only": {"nested": 1}}), encoding="utf-8"
    )
    (backup / "broken.json").write_text("{oops", encoding="utf-8")
    (backup / "readme.txt").write_text("skip me", encoding="utf-8")

    files = build_backup_file_summary(backup, {})
    by_name = {f["name"]: f for f in files}
    # 未知/坏/纯嵌套/非 JSON 文件不进摘要
    assert set(by_name) == {"CoffeeTask.json", "DailyRoutineTask.json"}

    routine = by_name["DailyRoutineTask.json"]
    rows = {row["key"]: row["value"] for row in routine["summary"]}
    assert routine["label"] == "日常任务流程"
    assert rows["已启用任务"] == "异象界域、一咖舍"
    assert rows["Exit After Task"] == "是"
    assert "_enabled" not in rows

    coffee = by_name["CoffeeTask.json"]
    assert coffee["label"] == "一咖舍"
    assert {row["key"]: row["value"] for row in coffee["summary"]} == {
        "模式": "自动化",
        "领取收益": "否",
    }


def test_preview_payload_is_dict(tmp_path: Path) -> None:
    """预览只保留任务配置两件套（日常任务流程+子任务配置），载荷挂 files 键。"""

    from app.task.OkNte.tools.restore_service import _preview_payload

    class _FakeScriptConfig:
        """最小脚本配置桩：只支撑 ``get(section, key)`` 读取。"""

        _data = {"Info": {"RootPath": ""}}

        def get(self, section: str, key: str):
            return self._data.get(section, {}).get(key)

    class _Ctx:
        config = None
        script_config = _FakeScriptConfig()
        script_id = "s-1"
        user_id = "u-1"

    backup = tmp_path / "backup"
    backup.mkdir()
    (backup / "CoffeeTask.json").write_text(
        json.dumps({"模式": "自动化"}), encoding="utf-8"
    )
    (backup / "DailyRoutineTask.json").write_text(
        json.dumps(
            {
                "Routine Items": [{"id": "daily_anomaly", "enabled": True}],
                "Exit After Task": True,
            }
        ),
        encoding="utf-8",
    )
    (backup / "DailyRoutineTaskConfigs.json").write_text(
        json.dumps({"daily_anomaly": {"目标消耗体力": 180}}), encoding="utf-8"
    )
    payload = _preview_payload(_Ctx(), "20260910-215808", backup)
    assert set(payload) == {"files"}
    # 其余配置文件不进预览（经「查看详细配置」恢复后在 ok-nte GUI 查看）
    assert [f["name"] for f in payload["files"]] == [
        "DailyRoutineTask.json",
        "DailyRoutineTaskConfigs.json",
    ]
    routine_rows = {r["key"]: r["value"] for r in payload["files"][0]["summary"]}
    assert routine_rows["已启用任务"] == "异象界域"
    configs_rows = {r["key"]: r["value"] for r in payload["files"][1]["summary"]}
    assert configs_rows["异象界域·目标消耗体力"] == "180"

    # 备份不存在仍抛 ValueError
    try:
        _preview_payload(_Ctx(), "missing", None)
        raise AssertionError("应当抛出 ValueError")
    except ValueError:
        pass
