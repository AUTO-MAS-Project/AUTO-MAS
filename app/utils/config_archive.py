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
import json
import re
import shutil
from collections.abc import Iterable, Mapping
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

OVERLAY_SIDECAR_NAME = "_mas_overlay.json"
"""MAS 页面字段侧车文件名（跨专项统一；只存归档内，恢复时分离回填，不落配置目录）"""


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


def file_set_hash(files: dict[str, "Path | str | bytes"]) -> str:
    """计算文件集指纹：相对键 + 大小 + 字节内容的组合哈希。

    文件集合的变化（增删文件）与内容变化都会使指纹改变；相对键的排序保证
    指纹与收集顺序无关。值为 ``str`` 按 UTF-8 编码、``bytes`` 原样参与
    （内存内容见 :func:`archive_files`）。

    Args:
        files: 相对路径键 → 文件路径或内存内容的映射。

    Returns:
        十六进制 SHA-256 摘要。
    """

    digest = hashlib.sha256()
    for rel in sorted(files):
        content = _coerce_bytes(files[rel])
        digest.update(f"f:{rel}:{len(content)}:".encode())
        digest.update(content)
    return digest.hexdigest()


def _coerce_bytes(source: "Path | str | bytes") -> bytes:
    """把文件源统一成字节内容（``Path`` 读盘，``str`` 按 UTF-8，``bytes`` 原样）。"""

    if isinstance(source, bytes):
        return source
    if isinstance(source, str):
        return source.encode("utf-8")
    return Path(source).read_bytes()


def _archive(
    files: dict[str, "Path | str | bytes"],
    store_root: Path,
    *,
    keep: int,
    force: bool,
    protect: frozenset[str] = frozenset(),
) -> Path | None:
    """把文件集复制为 ``store_root`` 下新时间戳目录。

    内容与最近一份备份完全一致时跳过（含 ``force=True``：恢复前存底在
    「恢复目标与当前内容一致」时不再产生冗余条目——当前配置已完整存放在
    该份备份中，误恢复可从它找回）；跳过返回 ``None``，否则返回归档目录。
    指纹对比失败的边界下照常归档。

    ``protect``：保留清理时排除的时间戳集合（不在超时清理中删）。用于
    ``restore_dir`` 链路上 force 归档后立刻恢复——用户选中的那份若在
    ``keep`` 之外不能被这条 force 归档清掉，否则随后 ``restore_dir`` 报
    备份不存在。`force` 隐含 protect 包含全部现存归档（恢复前不能清掉
    任何历史条目）。
    """

    times = list_times(store_root)
    if force:
        protect = frozenset(times) | protect
    if times:
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
    for rel, source in files.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(source, Path):
            shutil.copyfile(source, target)
        else:
            target.write_bytes(_coerce_bytes(source))

    for old in list_times(store_root)[keep:]:
        if old in protect:  # force 归档（恢复前存底）不清任何现存归档
            continue
        shutil.rmtree(store_root / old, ignore_errors=True)

    return dest


def archive_files(
    files: dict[str, "Path | str | bytes"],
    store_root: Path,
    *,
    keep: int = KEEP_COUNT,
    force: bool = False,
) -> Path | None:
    """按文件集归档：相对键结构原样存入新时间戳目录。

    适用于备份「分散在多个目录、只挑其中一部分」的文件集合；指纹去重后
    无变化返回 ``None``，否则返回归档目录。值支持三种来源：``Path``（拷贝
    磁盘文件）、``str``（按 UTF-8 编码写入，页面字段侧车用，免临时文件）、
    ``bytes``（原样写入）。

    Args:
        files: 相对路径键 → 文件路径或内存内容的映射。
        store_root: 归档根目录（该目录 = 一份独立的保留池）。
        keep: 保留份数，超出清理最旧；默认 :data:`KEEP_COUNT`。
        force: 恢复/覆盖前存底用：不做超时清理（protect 全部现存条目），
            但内容与最新份一致时同样跳过（不产生冗余条目）。

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
        force: 恢复/覆盖前存底用：不做超时清理（protect 全部现存条目），
            但内容与最新份一致时同样跳过（不产生冗余条目）。

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


def read_backup_text(
    backup_dir: Path, rel_path: str, *, max_bytes: int = 1024 * 1024
) -> dict:
    """只读读取归档目录内一个文本文件（预览「查看原始文件」用）。

    Args:
        backup_dir: 归档目录（:func:`get_backup_dir` 的返回值）。
        rel_path: 归档内相对路径（如 ``M7A/config.yaml``）。
        max_bytes: 允许读取的最大字节数（默认 1 MiB），超出拒绝。

    Returns:
        ``{"path": rel_path, "size": 字节数, "content": 文本内容}``。

    Raises:
        ValueError: 备份目录不存在、路径越界（防 ``../`` 穿越）、目标不是
            归档内的普通文件，或超出大小上限。
    """

    root = Path(backup_dir).resolve()
    if not root.is_dir():
        raise ValueError(f"备份不存在: {backup_dir.name}")
    target = (root / rel_path).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"非法的文件路径: {rel_path}")
    if not target.is_file():
        raise ValueError(f"文件不存在: {rel_path}")
    size = target.stat().st_size
    if size > max_bytes:
        raise ValueError(f"文件超出可查看大小上限（{size} > {max_bytes} 字节）")
    content = target.read_text(encoding="utf-8-sig", errors="replace")
    return {"path": str(rel_path), "size": size, "content": content}


def read_overlay_sidecar(
    backup_dir: Path, *, file_name: str = OVERLAY_SIDECAR_NAME
) -> dict | None:
    """读取归档内 MAS 字段侧车；不存在（旧版备份）或损坏返回 ``None``。

    Args:
        backup_dir: 归档目录（:func:`get_backup_dir` 的返回值）。
        file_name: 侧车文件名（默认 :data:`OVERLAY_SIDECAR_NAME`）。

    Returns:
        侧车字典；文件缺失或内容损坏/非对象时返回 ``None``。
    """

    sidecar = Path(backup_dir) / file_name
    if not sidecar.is_file():
        return None
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def mask_account(value) -> str:
    """账号脱敏：11 位纯数字手机号保留前 3 后 4，其余原样。"""

    text = str(value)
    if len(text) == 11 and text.isdigit():
        return f"{text[:3]}****{text[7:]}"
    return text


def restore_files(
    backup_dir: Path,
    target_root: Path,
    rel_keys: Iterable[str] | None = None,
    *,
    dir_map: Mapping[str, Path] | None = None,
) -> None:
    """按相对键把备份文件写回目标目录（replace 语义：先清理受管键再写入）。

    ``rel_keys`` 限定本次管理的相对键（默认归档内全部文件）；每个键的目标
    路径 = ``dir_map.get(顶级键, target_root)`` 下对应位置（未传 ``dir_map``
    时恒为 ``target_root / rel``，专项内相对键与目标路径同构的常规场景）。

    写回前先清理受管键管辖的既有内容，杜绝跨恢复残留：

    - 未走 ``dir_map`` 的顶级键若是目录前缀（如 ``OneDragon/``、``config/``），
      它是 target_root 下的专用子目录，整棵子树先删再写（残留的同前缀文件
      一并移除，恢复后该键下与备份完全一致）；根级文件（如 ``config.json``）
      只删该文件；
    - 走 ``dir_map`` 的顶级键（HSR 的 ``M7A/``、``SRA/`` 对应外部引擎根）：
      目标根是共享目录，绝不整根删除，只删备份内出现的相对路径文件，以及
      备份内出现的子目录（整棵，如 ``SRA/configs/``）。

    target_root 内未被管理的其它内容（备份外的用户数据）原样保留。

    Args:
        backup_dir: 归档目录（:func:`get_backup_dir` 的返回值）。
        target_root: 恢复目标根目录。
        rel_keys: 本次管理的相对键；默认归档内全部文件。
        dir_map: 顶级键 → 目标根目录映射（多根恢复场景，如 HSR 两引擎）。

    Raises:
        ValueError: 归档内无文件或受管相对键为空。
    """

    backup_dir = Path(backup_dir)
    target_root = Path(target_root)
    managed = (
        sorted(rel_keys) if rel_keys is not None else sorted(dir_files(backup_dir))
    )
    if not managed:
        raise ValueError(f"备份内容为空: {backup_dir.name}")

    # 按顶级键分组（第一段路径；无斜杠的键自身即顶级文件）
    top_keys: dict[str, list[str]] = {}
    for rel in managed:
        top, _, _ = rel.partition("/")
        top_keys.setdefault(top, []).append(rel)

    # 先清理受管键管辖的既有内容
    for top, rels in top_keys.items():
        if dir_map and top in dir_map:
            # dir_map 映射：目标根是共享目录，只删备份内出现的路径/子目录
            base = dir_map[top]
            heads: dict[str, bool] = {}
            for rel in rels:
                suffix = rel[len(top) + 1 :]
                head, _, rest = suffix.partition("/")
                heads[head] = heads.get(head, False) or bool(rest)
            for head, has_sub in heads.items():
                target = base / head
                if has_sub:  # 备份内含该子树全部文件（如 SRA/configs/）
                    force_rmtree(target)
                else:
                    target.unlink(missing_ok=True)
        elif any("/" in rel for rel in rels):
            # 默认映射 + 目录前缀：该子树完全由备份管理，整棵替换
            force_rmtree(target_root / top)
        else:
            (target_root / top).unlink(missing_ok=True)

    # 再按相对键逐文件写回
    for rel in managed:
        if dir_map and (top := rel.partition("/")[0]) in dir_map:
            target = dir_map[top] / rel[len(top) + 1 :]
        else:
            target = target_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(backup_dir / rel, target)
