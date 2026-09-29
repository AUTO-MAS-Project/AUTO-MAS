#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

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

_SKIP_FILE_NAMES = frozenset({".gitignore"})
_COMMIT_FILE_DEFAULT = "version.json"
_CHUNK = 1024 * 1024
_UTF8_FLAG = 0x800


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        shutil.rmtree(dest_dir)
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


def find_package_resource_root(extract_dir: Path) -> Path | None:
    """在解压树中定位 resource 目录，兼容两种已知布局（自上而下探测）：

    - GitHub 分支归档：``<extract>/MaaResource-main/resource/``
    - 镜像酱包：``<extract>/resource/``（包根即安装目录形态，见上游
      ``DownloadFromMirrorChyanAsync`` 直接 DirectoryMerge 到 BaseDir）
    """
    for candidate in (
        extract_dir / "MaaResource-main" / "resource",
        extract_dir / "resource",
    ):
        if (candidate / "version.json").is_file():
            return candidate
    return None


def count_zip_entries(zip_path: Path, prefix: str) -> int:
    """zip 内位于 ``prefix/`` 下的非目录条目数（文件名按 _fix_zip_name 修正后比对）。

    供换位前后的暂存树核账：任何原因（并发清理、AV 删文件）造成的残缺树
    都会与条目数对不上。
    """
    with zipfile.ZipFile(zip_path) as archive:
        return sum(
            1
            for info in archive.infolist()
            if not info.is_dir() and _fix_zip_name(info).startswith(prefix + "/")
        )


def merge_package_tree(
    source_root: Path,
    dest_root: Path,
    *,
    commit_file: str = _COMMIT_FILE_DEFAULT,
    skip_names: frozenset[str] = _SKIP_FILE_NAMES,
) -> None:
    """把 source_root 覆盖合并进 dest_root。

    - 目标目录不存在则创建（含中间层，对齐上游 DirectoryMerge）；
    - commit_file 最后写入（中途失败时目标版本时钟仍是旧值）；
    - 每一层都跳过 skip_names（上游对 .gitignore 同样逐层跳过）；
    - 从不删除目标目录中源树没有的文件。
    """
    dest_root.mkdir(parents=True, exist_ok=True)
    commit_source: Path | None = None
    for entry in sorted(source_root.iterdir()):
        if entry.name in skip_names:
            continue
        target = dest_root / entry.name
        if entry.is_dir():
            merge_package_tree(
                entry, target, commit_file=commit_file, skip_names=skip_names
            )
        elif entry.name == commit_file:
            commit_source = entry
        else:
            _copy_if_changed(entry, target)
    if commit_source is not None:
        _copy_if_changed(commit_source, dest_root / commit_source.name)


def _copy_if_changed(src: Path, dst: Path) -> None:
    if dst.is_file() and _file_sha256(src) == _file_sha256(dst):
        return
    # 临时名带 pid + 单调量：取消 sweep 后合并线程可能孤儿化继续执行，
    # 同进程的下一轮合并若共用临时名会交错出混合内容（os.replace 同目录
    # 原子，名字唯一后最坏也只是各自完整落盘一次）
    tmp = dst.with_name(f"{dst.name}.mas-{os.getpid()}.{time.monotonic_ns()}.tmp")
    try:
        shutil.copyfile(src, tmp)
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
