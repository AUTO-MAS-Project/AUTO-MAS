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

"""配置归档公共原语：时间戳快照 + 指纹去重 + 保留清理 + 整目录恢复。

供各适配器复用：把「运行/配置会话前会被 MAS 触碰的配置文件」在改动前归档
一份，每份是 ``store_root`` 下的一个时间戳目录，内容无变化自动跳过，超出
保留份数自动清理最旧；恢复时整目录替换目标位置。

本模块不感知任何脚本结构：归档什么文件、归档时机、恢复后的字段回填等
业务语义由调用方（适配器）决定，这里只提供脚本无关的原语。主要调用方
为 ZzzOd 的 ``app.task.ZzzOd.tools.backup_archive``。
"""

import hashlib
import re
import shutil
from datetime import datetime
from pathlib import Path

from app.utils import get_logger
from app.utils.io import force_rmtree

logger = get_logger("配置归档")

KEEP_COUNT = 10
"""默认保留的归档份数（每个 store_root 各自独立，超出清理最旧的）"""

_TIME_FORMAT = "%Y%m%d-%H%M%S"

_TS_PATTERN = re.compile(r"^\d{8}-\d{6}(?:-\d+)?$")
"""归档目录名白名单：仅接受本模块生成的时间戳命名（含同秒顺延序号后缀）"""


def config_root_key(config_path: str | Path) -> str:
    """物理配置根的稳定身份指纹。

    规范化绝对路径（盘符小写、去尾斜杠）的短哈希——同一份物理配置无论被哪
    个脚本实例引用都归同一个池，跨脚本共享原生备份、不随脚本删除；不同路径
    天然分桶，互不干扰（同路径必然同格式，格式差异不会混池）。
    """

    norm = str(Path(config_path).resolve()).casefold().rstrip("\\/")
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:12]


def list_times(root: Path) -> list[str]:
    """返回 ``root`` 下全部归档时间戳，时间倒序（目录名即时间戳）。

    排序键按 ``(基础时间戳, 同秒顺延序号)`` 解析——同秒目录名带 ``-N``
    后缀，直接按字符串倒序会让 ``-10`` 排到 ``-9`` 之前（同秒归档超过
    9 次时 ``times[0]`` 不再是最新那份）。
    """

    if not root.is_dir():
        return []

    def sort_key(name: str) -> tuple[str, int]:
        # 目录名：YYYYMMDD-HHMMSS 或 YYYYMMDD-HHMMSS-N（同秒顺延）；
        # 末段为非 6 位纯数字时视为顺延序号，按数值参与排序
        base, _, serial = name.rpartition("-")
        if serial.isdigit() and len(serial) != 6:
            return (base, int(serial))
        return (name, 0)

    return sorted(
        (p.name for p in root.iterdir() if p.is_dir()), key=sort_key, reverse=True
    )


def dir_files(source: Path) -> dict[str, Path]:
    """收集目录内全部文件集：相对路径键 → 文件路径。

    Args:
        source: 源目录。

    Returns:
        相对键到文件路径的映射，键按相对路径排序。
    """

    files: dict[str, Path] = {}
    for path in sorted(source.rglob("*")):
        if path.is_file():
            files[path.relative_to(source).as_posix()] = path
    return files


def file_set_hash(files: dict[str, Path]) -> str:
    """计算文件集指纹：相对键 + 大小 + 字节内容的组合哈希。

    文件集合的变化（增删文件）与内容变化都会使指纹改变；相对键的排序保证
    指纹与收集顺序无关。

    Args:
        files: 相对路径键 → 文件路径的映射（见 :func:`dir_files`）。

    Returns:
        十六进制 SHA-256 摘要。
    """

    digest = hashlib.sha256()
    for rel in sorted(files):
        path = files[rel]
        digest.update(f"f:{rel}:{path.stat().st_size}:".encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _archive(
    files: dict[str, Path],
    store_root: Path,
    *,
    keep: int,
    force: bool,
    protect: frozenset[str] = frozenset(),
) -> Path | None:
    """把文件集复制为 ``store_root`` 下新时间戳目录。

    内容与最近一份备份完全一致时跳过（``force=True`` 强制归档，用于恢复前
    存底——让「恢复前的配置」在列表里有明确的时间戳条目）；跳过返回
    ``None``，否则返回归档目录。指纹对比失败的边界下照常归档。

    ``protect``：保留清理时排除的时间戳集合（不在超时清理中删）。用于
    ``restore_dir`` 链路上 force 归档后立刻恢复——用户选中的那份若在
    ``keep`` 之外不能被这条 force 归档清掉，否则随后 ``restore_dir`` 报
    备份不存在。`force` 隐含 protect 包含全部现存归档（恢复前不能清掉
    任何历史条目）。
    """

    times = list_times(store_root)
    if force:
        protect = frozenset(times) | protect
    if not force and times:
        try:
            latest = dir_files(store_root / times[0])
            if file_set_hash(latest) == file_set_hash(files):
                return None
        except OSError as e:
            logger.warning(f"备份指纹对比失败，照常归档: {e}")

    dest = store_root / datetime.now().strftime(_TIME_FORMAT)
    serial = 1
    while dest.exists():  # 同秒内多次备份（理论罕见）顺延序号
        serial += 1
        dest = store_root / f"{datetime.now().strftime(_TIME_FORMAT)}-{serial}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    for rel, path in files.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)

    for old in list_times(store_root)[keep:]:
        if old in protect:  # force 归档（恢复前存底）不清任何现存归档
            continue
        shutil.rmtree(store_root / old, ignore_errors=True)

    return dest


def archive_files(
    files: dict[str, Path],
    store_root: Path,
    *,
    keep: int = KEEP_COUNT,
    force: bool = False,
) -> Path | None:
    """按文件集归档：相对键结构原样存入新时间戳目录。

    适用于备份「分散在多个目录、只挑其中一部分」的文件集合；指纹去重后
    无变化返回 ``None``，否则返回归档目录。

    Args:
        files: 相对路径键 → 文件路径的映射（见 :func:`dir_files`）。
        store_root: 归档根目录（该目录 = 一份独立的保留池）。
        keep: 保留份数，超出清理最旧；默认 :data:`KEEP_COUNT`。
        force: 强制归档，跳过指纹去重（恢复前存底用）。

    Returns:
        新归档目录；内容无变化被跳过时返回 ``None``。

    Raises:
        ValueError: ``files`` 为空（无任何文件可归档）。
    """

    if not files:
        raise ValueError("备份来源为空")
    return _archive(files, store_root, keep=keep, force=force)


def archive_dir(
    src: Path,
    store_root: Path,
    *,
    keep: int = KEEP_COUNT,
    force: bool = False,
) -> Path | None:
    """目录整份归档：``src`` 全部文件按相对路径快照到时间戳目录。

    指纹去重后无变化返回 ``None``，否则返回归档目录。

    Args:
        src: 源目录（整份备份）。
        store_root: 归档根目录（该目录 = 一份独立的保留池）。
        keep: 保留份数，超出清理最旧；默认 :data:`KEEP_COUNT`。
        force: 强制归档，跳过指纹去重（恢复前存底用）。

    Returns:
        新归档目录；内容无变化被跳过时返回 ``None``。

    Raises:
        ValueError: ``src`` 不存在或不是目录。
    """

    src = Path(src)
    if not src.is_dir():
        raise ValueError(f"备份来源不存在: {src}")
    return _archive(dir_files(src), store_root, keep=keep, force=force)


def get_backup_dir(store_root: Path, ts: str) -> Path | None:
    """取指定时间戳的归档目录；不存在返回 ``None``。

    ``ts`` 仅接受本模块生成的 ``%Y%m%d-%H%M%S(-N)`` 目录名（时间戳来自
    外部请求时防止 ``../`` 等输入拼出 store_root 之外的路径），格式非法
    一律视为不存在。

    Args:
        store_root: 归档根目录。
        ts: 归档时间戳（目录名）。

    Returns:
        归档目录路径；不存在或格式非法时返回 ``None``。
    """

    if not _TS_PATTERN.match(str(ts)):
        return None
    dest = store_root / str(ts)
    return dest if dest.is_dir() else None


def restore_dir(store_root: Path, ts: str, target: Path) -> None:
    """把归档整目录恢复到 ``target``（先删后拷，与源完全一致）。

    恢复前归档当前配置由调用方负责（在调用前以 ``force=True`` 归档当前
    内容，保证误恢复可找回）；本原语不隐含归档。

    Args:
        store_root: 归档根目录。
        ts: 归档时间戳（目录名）。
        target: 目标目录，会被整个替换。

    Raises:
        ValueError: 归档不存在或归档内容为空。
    """

    backup_dir = get_backup_dir(store_root, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    if not dir_files(backup_dir):
        raise ValueError(f"备份内容为空: {ts}")
    target = Path(target)
    # 先清再拷，copytree 加 dirs_exist_ok=True：目标残留目录被占用时
    # 不再「部分已删、备份一个没拷回」；与 #564 写法保持一致。
    # 删除走 force_rmtree：目标带只读文件（如脚本自带的 .git 对象）时
    # 普通 rmtree 删不掉，残留会让随后的 copytree 覆盖失败。
    force_rmtree(target)
    shutil.copytree(backup_dir, target, dirs_exist_ok=True)
