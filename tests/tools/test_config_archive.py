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
#
#   Contact: DLmaster_361@163.com

"""归档原语内存内容支持的回归：三种文件源（Path / str / bytes）的写入与
指纹一致性——12 个专项的字段侧车都压在这条路径上。"""

from pathlib import Path

from app.utils.config_archive import (
    MODE_FILE_NAME,
    archive_files,
    file_set_hash,
    list_times,
    read_backup_mode,
    restore_dir,
    restore_files,
    write_backup_mode,
)


def test_archive_files_memory_content(tmp_path: Path) -> None:
    """str 按 UTF-8、bytes 原样写入；与同内容磁盘文件指纹一致（去重互通）。"""

    text = '{"Mode": "用户"}'  # 非 ASCII，验证 UTF-8 编码而非隐式 latin-1
    disk = tmp_path / "same.json"
    disk.write_text(text, encoding="utf-8")

    root_a = tmp_path / "pool_a"
    dest_a = archive_files({"sidecar.json": text, "raw.bin": b"\x00\x01"}, root_a)
    assert dest_a is not None
    assert (dest_a / "sidecar.json").read_text("utf-8") == text
    assert (dest_a / "raw.bin").read_bytes() == b"\x00\x01"

    # 同内容的 Path 源与内存 str 源指纹一致：换源形态不产生重复归档条目
    root_b = tmp_path / "pool_b"
    archive_files({"sidecar.json": disk}, root_b)
    dest_b2 = archive_files({"sidecar.json": text}, root_b)
    assert dest_b2 is None  # 指纹去重生效

    # 指纹函数对三种源形态直接等价
    assert (
        file_set_hash({"f": disk})
        == file_set_hash({"f": text})
        == file_set_hash({"f": text.encode("utf-8")})
    )


def test_restore_dir_excludes_mode_metadata(tmp_path: Path) -> None:
    """归档含 _mas_mode 元数据时 restore_dir 不把它落回目标目录（整目录替换）。"""

    root = tmp_path / "pool"
    dest = archive_files({"a.json": '{"x": 1}'}, root)
    assert dest is not None
    write_backup_mode(dest, "脚本")
    assert read_backup_mode(dest) == "脚本"

    target = tmp_path / "target"
    target.mkdir()
    (target / "a.json").write_text("{}", encoding="utf-8")
    (target / "leftover.txt").write_text("old", encoding="utf-8")
    restore_dir(root, dest.name, target)
    assert (target / "a.json").read_text("utf-8") == '{"x": 1}'  # 内容找回
    assert not (target / MODE_FILE_NAME).exists()  # 元数据不落配置目录
    assert not (target / "leftover.txt").exists()  # 整目录替换语义不变


def test_restore_files_excludes_mode_metadata(tmp_path: Path) -> None:
    """restore_files 默认受管键排除顶级 _ 前缀元数据（_mas_mode 不落目标）。"""

    root = tmp_path / "pool"
    dest = archive_files({"a.json": '{"x": 1}'}, root)
    assert dest is not None
    write_backup_mode(dest, "脚本")

    target = tmp_path / "target"
    target.mkdir()
    restore_files(dest, target)
    assert (target / "a.json").read_text("utf-8") == '{"x": 1}'
    assert not (target / MODE_FILE_NAME).exists()


def test_list_times_only_accepts_timestamp_dirs(tmp_path: Path) -> None:
    """时间戳列表只认本模块生成的目录名，同级的其它子目录既不入选也不被裁掉。

    池内与时间戳目录同级可能存在语义不同的子目录（如 ZzzOd 回收池槽桶内的
    ``mas-backups`` 备份池快照）；混进列表会让归档去重恒失效、保留清理误裁
    真实快照。
    """

    pool = tmp_path / "pool"
    for name in (
        "20260921-225131",
        "20260921-225130",
        "20260921-225131-2",
        "20260921-225131-10",
    ):
        (pool / name).mkdir(parents=True)
    # 同级非时间戳子目录：不进列表，也不参与保留清理
    (pool / "mas-backups").mkdir()
    (pool / "not-a-time").mkdir()

    assert list_times(pool) == [
        "20260921-225131-10",
        "20260921-225131-2",
        "20260921-225131",
        "20260921-225130",
    ]


def test_list_times_keeps_full_retention_with_sibling_dir(tmp_path: Path) -> None:
    """同级非时间戳子目录不再占位：归档池保留份数仍是完整的 keep 份。"""

    pool = tmp_path / "pool"
    (pool / "mas-backups").mkdir(parents=True)

    # 11 份内容互不相同的归档，keep=10：应保留 10 份真实快照
    for i in range(11):
        archive_files({f"{i}.json": f'{{"i": {i}}}'}, pool, keep=10)

    # 直接数盘上的时间戳目录（不走 list_times，避免与实现同源自证）：
    # 保留份数不受同级非时间戳子目录占位影响
    snapshots = [p for p in pool.iterdir() if p.is_dir() and p.name[0].isdigit()]
    assert len(snapshots) == 10
    # 非时间戳子目录不参与保留清理，原样保留
    assert (pool / "mas-backups").is_dir()
