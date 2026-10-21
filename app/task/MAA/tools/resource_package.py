#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


"""MAA 资源包应用原语：把「包树」以覆盖不删除的方式合并进目标目录。

与上游 MAA ``ResourceUpdater.DirectoryMerge`` 的公开行为语义对齐的独立实现
（非逐行翻译）：
- 逐文件哈希比对，只写内容不同的文件（上游为无条件覆盖，此处是写入量优化，
  最终树状态一致）；
- 提交文件（version.json）最后写入——中途失败时目标目录的版本时钟仍是
  旧值，下一轮能重新发现并重试，避免「半新半旧却自认最新」；
- 从不删除目标目录中源树没有的文件；
- 每文件原子写：同目录临时文件 + os.replace（防目标正被进程读到半截）。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import time
import zipfile
from pathlib import Path

from app.utils.io import force_rmtree

_COMMIT_FILE = "version.json"
_CHUNK = 1024 * 1024
_UTF8_FLAG = 0x800


def _file_sha256(path: Path) -> str:
    with path.open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def resource_tree_hashes(root: Path) -> dict[str, str]:
    """记录待分发文件的相对路径与内容摘要，逐层忽略 .gitignore。"""
    return {
        path.relative_to(root).as_posix(): _file_sha256(path)
        for path in root.rglob("*")
        if path.is_file() and ".gitignore" not in path.relative_to(root).parts
    }


def _fix_zip_name(info: zipfile.ZipInfo) -> str:
    """修正未置 UTF-8 标志位（bit 11）的非 ASCII 文件名。

    部分打包工具漏置标志位时 Python 按 cp437 解码出乱码名，合并时会把它当
    「新文件」写入而真名文件滞留旧内容。能无损往返 cp437→utf-8 时按 utf-8
    重解码修复；ASCII 名字往返不变，不受影响。
    """
    if info.flag_bits & _UTF8_FLAG:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


def extract_zip(zip_path: Path, dest_dir: Path) -> None:
    """解压 zip 到 dest_dir（先清空该目录）。

    zip 损坏或条目路径越界（绝对路径 / ``..``）时抛异常，由调用方兜底。
    """
    if dest_dir.exists():
        force_rmtree(dest_dir)
    dest_dir.mkdir(parents=True)
    root = dest_dir.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            target = (dest_dir / _fix_zip_name(info)).resolve(strict=False)
            if not target.is_relative_to(root):
                raise ValueError(f"资源包内路径越界: {info.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst, _CHUNK)


def count_zip_entries(zip_path: Path) -> int:
    """zip 内位于 ``resource/`` 下的非目录条目数。

    供换位前后的暂存树核账：任何原因（并发清理、AV 删文件）造成的残缺树
    都会与条目数对不上。
    """
    with zipfile.ZipFile(zip_path) as archive:
        return sum(
            1
            for info in archive.infolist()
            if not info.is_dir() and _fix_zip_name(info).startswith("resource/")
        )


def merge_package_tree(
    source_root: Path,
    dest_root: Path,
    *,
    file_hashes: dict[str, str] | None = None,
) -> None:
    """把 source_root 覆盖合并进 dest_root。

    - 目标目录不存在则创建（含中间层，对齐上游 DirectoryMerge）；
    - 根目录 version.json 最后写入（中途失败时目标版本时钟仍是旧值）；
    - 每一层都跳过 .gitignore（与上游一致）；
    - 从不删除目标目录中源树没有的文件。
    - 提供清单时校验实际写入内容及文件集合，通过后才提交版本。
    """
    commit_source = source_root / _COMMIT_FILE
    copied: set[str] = set()

    def copy_file(src: str, dst: str) -> str:
        relative = Path(src).relative_to(source_root).as_posix()
        result = _copy_if_changed(
            src,
            dst,
            expected_sha256=file_hashes[relative] if file_hashes is not None else None,
        )
        copied.add(relative)
        return result

    def ignore(directory: str, _names: list[str]) -> set[str]:
        skipped = {".gitignore"}
        if Path(directory) == source_root and commit_source.is_file():
            skipped.add(_COMMIT_FILE)
        return skipped

    shutil.copytree(
        source_root,
        dest_root,
        dirs_exist_ok=True,
        ignore=ignore,
        copy_function=copy_file,
    )
    if file_hashes is not None and copied != set(file_hashes) - {_COMMIT_FILE}:
        raise ValueError("资源文件集合与暂存清单不一致，拒绝提交版本")
    if commit_source.is_file():
        copy_file(str(commit_source), str(dest_root / commit_source.name))
    elif file_hashes is not None and _COMMIT_FILE in file_hashes:
        raise ValueError("暂存版本文件缺失，拒绝提交版本")


def _copy_if_changed(
    src: str | Path, dst: str | Path, *, expected_sha256: str | None = None
) -> str:
    src, dst = Path(src), Path(dst)
    if dst.is_file() and (expected_sha256 or _file_sha256(src)) == _file_sha256(dst):
        return str(dst)
    # 临时名带 pid + 单调量，避免其他写入或异常残留共用临时文件。
    tmp = dst.with_name(f"{dst.name}.mas-{os.getpid()}.{time.monotonic_ns()}.tmp")
    try:
        shutil.copyfile(src, tmp)
        if expected_sha256 is not None and _file_sha256(tmp) != expected_sha256:
            raise ValueError(f"资源内容与暂存清单不一致: {src}")
        try:
            os.replace(tmp, dst)
        except PermissionError:
            # Windows 只读目标会让 replace 失败：清只读位重试一次（对齐
            # app.utils.io 的同病灶处理）
            if dst.exists():
                os.chmod(dst, stat.S_IWRITE)
            os.replace(tmp, dst)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return str(dst)
