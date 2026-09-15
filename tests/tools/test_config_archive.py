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

from app.utils.config_archive import archive_files, file_set_hash


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
