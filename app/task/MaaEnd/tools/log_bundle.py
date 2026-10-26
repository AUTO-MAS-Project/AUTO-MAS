#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


"""按 MXU 的导出规则把 MaaEnd 运行日志打包成分卷 ZIP。

逐条对应 MXU ``src-tauri/src/commands/file_ops.rs`` 的 ``export_logs_blocking``：

- 收集：``debug/`` 根目录的 .log/.dmp（按文件名排序）→ ``config/`` 全量递归（前缀
  ``config/``）→ ``debug/`` 每个子目录递归里的 .log/.json/.dmp（前缀是子目录名）→
  ``debug/on_error`` 与 ``debug/vision`` 的图片（只扫一层、按修改时间新→旧排在尾部）。
  没有可导出内容时视为空。
- 命名：目录 ``<项目>-logs-<版本>-<时间戳>``（版本为空时省掉），分卷
  ``<目录名>-partNN.zip``，时间戳格式 ``%Y%m%d-%H%M%S``，分卷号零填充宽度按条目数
  定（≥100 用 3 位，否则 2 位）。
- 分卷：单卷上限 24.5 MB，两阶段容量判断（先按扩展名估算压缩后大小，估算触线才用
  DEFLATE 实测一次），每卷至少写一个文件。
- 保留：只在导出根目录下按目录名末尾的时间戳留最近 ``MAX_EXPORTS_TO_KEEP`` 份，本次
  产物始终保留，解不出时间戳的目录既不删也不占名额。除分卷外不写任何附加文件。

MAS 侧与 MXU 不同、且是有意为之的几处：

- 导出根目录来自用户在脚本配置里选的目录（MXU 固定在 ``<数据目录>/debug_exports``）。
- 分卷先写 ``.tmp`` 再改名，异常中断不会把半截 ZIP 当成正式包留在目录里。
- 归档名与项目名会做一次清洗（去掉 ``..``、盘符、非法字符），MXU 直接拼接。
- 一个文件都没收集到返回 ``None``（MXU 报错）；一个文件都没写成功按失败抛出，交给
  调用方保留现场重试。

手动导出与自动保存共用本模块，前端仅选择目录并打开保存结果。
"""

import asyncio
import hashlib
import os
import re
import shutil
import zipfile
import zlib
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

if TYPE_CHECKING:
    from app.models.config import MaaEndConfig

import json5

from app.utils import get_logger

logger = get_logger("MaaEnd 日志打包")

MAX_VOLUME_BYTES = 24_500_000
"""单卷上限，与 MXU 的 MAX_VOLUME_BYTES 一致。"""

MAX_EXPORTS_TO_KEEP = 10
"""导出根目录下保留的份数，与 MXU 的 MAX_EXPORTS_TO_KEEP 一致（本次产物始终保留）。"""


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
_ROOT_LOG_SUFFIXES = {".log", ".dmp"}
_DEBUG_SUFFIXES = {".log", ".json", ".dmp"}
"""debug 子目录里的归档后缀。"""
_TEXT_SUFFIXES = {".log", ".json", ".txt", ".toml", ".yaml", ".yml", ".xml", ".csv"}
"""按四分之一体积估算的文本后缀，与 MXU 的两阶段容量判断保持一致。"""

_ZIP_CENTRAL_FIXED_BYTES = 46
"""ZIP 中央目录每条记录的固定字段大小，不含文件名。"""
_ZIP_EOCD_BYTES = 22
"""ZIP 结尾记录（EOCD）的大小。"""
_ZIP_LOCAL_HEADER_OVERHEAD = 64
"""local header 固定开销 + DEFLATE 帧头 + 余量，与 MXU 的 ZIP_LOCAL_HEADER_OVERHEAD 一致。"""
_TIMESTAMP_LEN = 15
"""导出目录名末尾时间戳 ``YYYYMMDD-HHMMSS`` 的长度。"""

_UNSAFE_NAME_CHARS = re.compile(r'[\\/:*?"<>|]')
_ARCHIVE_SEPARATORS = re.compile(r"[\\/]+")
_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


@dataclass
class LogExport:
    """一次导出的结果，对应导出根目录下的一个日志包目录。"""

    directory: Path
    volumes: list[Path] = field(default_factory=list)
    files: int = 0
    failed_files: int = 0
    bytes: int = 0


def read_project_info(root_path: Path) -> tuple[str, str]:
    """读取 MaaEnd 安装目录 ``interface.json`` 声明的项目名与版本。

    只用于压缩包命名：公开的 ``interface.json`` 与 MXU 导出时的取值口径一致。

    Args:
        root_path (Path): MaaEnd 安装目录。

    Returns:
        tuple[str, str]: 项目名与版本；读不到名称时回退 ``mxu``，版本缺失为空串。
    """

    try:
        value = json5.loads((root_path / "interface.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "mxu", ""
    if not isinstance(value, dict):
        return "mxu", ""
    name = value.get("name")
    version = value.get("version")
    return (
        safe_file_name(name) or "mxu",
        safe_file_name(version) if isinstance(version, str) else "",
    )


def safe_file_name(text: object) -> str:
    """去掉文件名非法字符，保留可读部分。"""

    if not isinstance(text, str):
        return ""
    return _UNSAFE_NAME_CHARS.sub("_", text).strip(". ")[:100]


def _sorted_files(directory: Path, suffixes: set[str]) -> list[tuple[Path, str]]:
    """列出目录下指定后缀的文件，按文件名排序。"""

    try:
        entries = sorted(
            (
                path
                for path in directory.iterdir()
                if path.is_file()
                and path.suffix.lower() in suffixes
                and not path.is_symlink()
            ),
            key=lambda path: path.name,
        )
    except OSError as error:
        logger.warning(f"读取日志目录失败 {directory}: {error}")
        return []
    return [(path, path.name) for path in entries]


def _collect_tree(directory: Path, prefix: str) -> list[tuple[Path, str]]:
    """递归收集目录下全部文件，归档名按 posix 风格拼接。"""

    if not directory.is_dir():
        return []
    entries: list[tuple[Path, str]] = []
    for path in directory.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(directory).as_posix()
        entries.append((path, f"{prefix}/{relative}"))
    return sorted(entries, key=lambda entry: entry[1])


def _collect_debug_subdirs(debug_dir: Path) -> list[tuple[Path, str]]:
    """收集 ``debug/`` 各子目录里的 .log/.json/.dmp 文件。"""

    entries: list[tuple[Path, str]] = []
    try:
        subdirs = sorted(
            (path for path in debug_dir.iterdir() if path.is_dir()),
            key=lambda p: p.name,
        )
    except OSError as error:
        logger.warning(f"读取日志子目录失败 {debug_dir}: {error}")
        return []
    for subdir in subdirs:
        for path in subdir.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            if path.suffix.lower() not in _DEBUG_SUFFIXES:
                continue
            relative = path.relative_to(subdir).as_posix()
            entries.append((path, f"{subdir.name}/{relative}"))
    return sorted(entries, key=lambda entry: entry[1])


def _collect_images(directory: Path, prefix: str) -> list[tuple[Path, str]]:
    """收集报错与识别截图，按修改时间从新到旧，保证最近的图先入卷。"""

    try:
        candidates = [
            path
            for path in directory.iterdir()
            if path.is_file()
            and path.suffix.lower() in _IMAGE_SUFFIXES
            and not path.is_symlink()
        ]
    except OSError:
        return []
    candidates.sort(key=lambda path: _mtime(path), reverse=True)
    return [(path, f"{prefix}/{path.name}") for path in candidates]


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def collect_mxu_entries(root_path: Path) -> list[tuple[Path, str]]:
    """按 MXU 的收集顺序列出待归档的日志条目。

    Args:
        root_path (Path): MaaEnd 安装目录。

    Returns:
        list[tuple[Path, str]]: ``(源文件, 归档内路径)`` 列表。

    Raises:
        FileNotFoundError: 安装目录下没有 ``debug/``。
    """

    debug_dir = root_path / "debug"
    if not debug_dir.is_dir():
        raise FileNotFoundError(f"日志目录不存在: {debug_dir}")
    return [
        *_sorted_files(debug_dir, _ROOT_LOG_SUFFIXES),
        *_collect_tree(root_path / "config", "config"),
        *_collect_debug_subdirs(debug_dir),
        *_collect_images(debug_dir / "on_error", "on_error"),
        *_collect_images(debug_dir / "vision", "vision"),
    ]


def _archive_member(name: str) -> str:
    """把收集到的归档名清洗成安全的 ZIP 成员名。

    文件名来自本机安装目录，但压缩包可能被解压到把反斜杠当路径分隔符的系统上，
    所以统一按 ``/`` 与 ``\\`` 切分后丢掉空段、``.`` 与 ``..``，再去掉盘符。
    清洗后为空的条目由调用方记为未写入。
    """

    parts: list[str] = []
    for part in _ARCHIVE_SEPARATORS.split(name):
        part = part.strip().replace("\x00", "")
        if not part or part in {".", ".."}:
            continue
        part = _DRIVE_PREFIX.sub("", part)
        if part:
            parts.append(part)
    return "/".join(parts)


def _deflate_size(path: Path) -> int:
    """估算文件压缩后的大小，只在快要超出单卷上限时用来确认。"""

    compressor = zlib.compressobj(zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, -15)
    total = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            total += len(compressor.compress(chunk))
    return total + len(compressor.flush())


def _export_dir_name(root_path: Path, *, now: datetime | None = None) -> str:
    """这次导出的目录名，口径与 MXU 的 ``dir_name`` 一致。"""

    project_name, project_version = read_project_info(root_path)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return (
        f"{project_name}-logs-{project_version}-{stamp}"
        if project_version
        else f"{project_name}-logs-{stamp}"
    )


def _create_export_dir(exports_root: Path, dir_name: str) -> Path:
    """建导出目录，语义等同 MXU 的 ``create_dir_all``：目录已存在就直接沿用。"""

    out_dir = exports_root / dir_name
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _write_volumes(
    out_dir: Path,
    dir_name: str,
    members: list[tuple[Path, str]],
    *,
    width: int,
) -> tuple[list[Path], int]:
    """把条目按 MXU 的分卷规则写成 ZIP，返回卷路径与读取失败的文件数。

    换卷判断沿用 MXU 的两阶段口径：先用体积估算快速通过大多数文件，估算触线时才用
    DEFLATE 实测一次拿精确值；每卷至少写一个文件。卷先写 ``.tmp`` 再改名，异常中断
    不会留下被当成正式包的半截 ZIP。
    """

    volumes: list[Path] = []
    failed_files = 0
    index = 0
    written = 0
    central = _ZIP_EOCD_BYTES
    handle: BinaryIO | None = None
    archive: zipfile.ZipFile | None = None
    volume_path: Path | None = None
    volume_tmp: Path | None = None

    def open_volume() -> None:
        nonlocal index, written, central, handle, archive, volume_path, volume_tmp
        index += 1
        volume_path = out_dir / f"{dir_name}-part{index:0{width}d}.zip"
        volume_tmp = volume_path.with_name(volume_path.name + ".tmp")
        volume_tmp.unlink(missing_ok=True)
        handle = volume_tmp.open("wb")
        archive = zipfile.ZipFile(handle, "w", zipfile.ZIP_DEFLATED, allowZip64=True)
        written = 0
        central = _ZIP_EOCD_BYTES

    def close_volume() -> None:
        nonlocal handle, archive
        if archive is None or handle is None or volume_path is None:
            return
        if volume_tmp is None:
            return
        archive.close()
        handle.close()
        os.replace(volume_tmp, volume_path)
        volumes.append(volume_path)
        archive = None
        handle = None

    try:
        open_volume()
        for source, member in members:
            if archive is None or handle is None:
                open_volume()
            try:
                size = source.stat().st_size
            except OSError as error:
                logger.warning(f"无法读取日志文件 {source}: {error}")
                failed_files += 1
                continue
            member_bytes = len(member.encode("utf-8")) + _ZIP_CENTRAL_FIXED_BYTES
            remaining = MAX_VOLUME_BYTES - (written + central)
            estimated = size // 4 if source.suffix.lower() in _TEXT_SUFFIXES else size
            if (
                written
                and estimated + _ZIP_LOCAL_HEADER_OVERHEAD + member_bytes > remaining
            ):
                try:
                    measured = _deflate_size(source)
                except OSError as error:
                    logger.warning(f"无法读取日志文件 {source}: {error}")
                    failed_files += 1
                    continue
                if measured + _ZIP_LOCAL_HEADER_OVERHEAD + member_bytes > remaining:
                    close_volume()
                    open_volume()
            try:
                source_handle = source.open("rb")
            except OSError as error:
                logger.warning(f"无法打开日志文件 {source}: {error}")
                failed_files += 1
                continue
            try:
                with archive.open(member, "w") as target:
                    shutil.copyfileobj(source_handle, target, 1 << 20)
            except OSError as error:
                # 已经写进去一部分，这一卷照留，但由调用方按「不完整」报告。
                logger.warning(f"写入日志文件失败 {source}: {error}")
                failed_files += 1
            finally:
                source_handle.close()
            written = handle.tell()
            central += member_bytes
        if written:
            close_volume()
    finally:
        if archive is not None:
            with suppress(Exception):
                archive.close()
        if handle is not None:
            with suppress(Exception):
                handle.close()
        if volume_tmp is not None:
            volume_tmp.unlink(missing_ok=True)
    return volumes, failed_files


def _parse_export_timestamp(dir_name: str) -> str | None:
    """从导出目录名末尾解出 ``YYYYMMDD-HHMMSS``。

    与 MXU 的 ``parse_export_timestamp`` 同口径：在字节层面取末尾 15 个字符，避免目录
    名含非 ASCII 时切到码点中间；形状不符返回 ``None``，清理时既不删也不占名额。
    """

    encoded = dir_name.encode("utf-8", "surrogatepass")
    if len(encoded) < _TIMESTAMP_LEN:
        return None
    tail = encoded[-_TIMESTAMP_LEN:]
    if not (tail[:8].isdigit() and tail[8:9] == b"-" and tail[9:].isdigit()):
        return None
    return tail.decode("ascii", "ignore")


def prune_old_exports(exports_root: Path, *, current_export: Path) -> None:
    """只保留最近 ``MAX_EXPORTS_TO_KEEP`` 份导出，本次产物始终保留。

    口径与 MXU 的 ``prune_old_exports`` 一致：枚举导出根目录下的子目录，按目录名末尾的
    时间戳从新到旧排序（不看 mtime：Windows 上目录时间不稳定，备份同步也会改写），
    删掉超出部分；解不出时间戳的目录既不删也不占名额。清理失败只告警。
    """

    candidates: list[tuple[str, Path]] = []
    try:
        for path in exports_root.iterdir():
            if path == current_export or not path.is_dir():
                continue
            stamp = _parse_export_timestamp(path.name)
            if stamp is None:
                continue
            candidates.append((stamp, path))
    except OSError as error:
        logger.warning(f"枚举导出目录失败 {exports_root}: {error}，跳过旧导出清理")
        return
    keep_others = MAX_EXPORTS_TO_KEEP - 1
    if len(candidates) <= keep_others:
        return
    candidates.sort(key=lambda item: item[0], reverse=True)
    for _, path in candidates[keep_others:]:
        try:
            shutil.rmtree(path)
        except OSError as error:
            logger.warning(f"清理旧导出失败 {path}: {error}")
        else:
            logger.info(f"已清理旧导出: {path}")


def export_failure_logs(
    exports_root: Path,
    root_path: Path,
    *,
    now: datetime | None = None,
    retain: bool = True,
) -> LogExport | None:
    """把当前失败现场导出一份 MXU 口径的日志包目录。

    Args:
        exports_root (Path): 保存日志包的根目录，不存在时创建。
        root_path (Path): MaaEnd 安装目录，读取 ``interface.json``、``debug/``、``config/``。
        now (datetime | None): 用于目录名与时间戳的时间，默认当前时间。

    Returns:
        LogExport | None: 导出结果；没有可导出的日志时返回 ``None``。

    Raises:
        OSError: 日志目录不存在、导出目录建不出来，或一个日志文件都没写成功。
    """

    entries = collect_mxu_entries(root_path)
    if not entries:
        logger.warning(f"没有可导出的日志文件: {root_path}")
        return None
    failed_files = 0
    members: list[tuple[Path, str]] = []
    for source, archive_name in entries:
        member = _archive_member(archive_name)
        if not member:
            logger.warning(f"跳过无法归档的文件名: {archive_name}")
            failed_files += 1
            continue
        members.append((source, member))
    if not members:
        logger.warning(f"没有可归档的文件: {root_path}")
        return None

    dir_name = _export_dir_name(root_path, now=now)
    out_dir = _create_export_dir(exports_root, dir_name)
    # 卷数硬上界是条目数（每个文件独占一卷的退化情形），据此选零填充宽度。
    width = 3 if len(entries) >= 100 else 2
    volumes, write_failures = _write_volumes(out_dir, dir_name, members, width=width)
    failed_files += write_failures
    if not volumes:
        shutil.rmtree(out_dir, ignore_errors=True)
        # 一个文件都没写成功说明现场没存下来：报错让调用方保留现场、收尾再试。
        raise OSError(f"没有日志文件写入成功: {root_path}")

    export = LogExport(
        directory=out_dir,
        volumes=volumes,
        files=len(members) - write_failures,
        failed_files=failed_files,
        bytes=sum(volume.stat().st_size for volume in volumes),
    )
    if retain:
        prune_old_exports(exports_root, current_export=out_dir)
    logger.success(
        f"MaaEnd 日志导出完成: {out_dir}（{len(volumes)} 卷，{export.files} 个文件）"
    )
    return export


@dataclass
class LogBundleSelection:
    directories: list[str] = field(default_factory=list)
    needs_directory: bool = False
    incomplete_count: int = 0


def _resolve_log_bundles(
    scripts: list["MaaEndConfig"], output_directory: Path | None = None
) -> LogBundleSelection:
    """每个安装优先取最新自动归档，否则保存当前现场；不修改自动保存配置。"""

    installations: dict[Path, list["MaaEndConfig"]] = {}
    for script in scripts:
        if script.Info.Path is not None:
            installations.setdefault(script.Info.Path.resolve(), []).append(script)
    if not installations:
        raise ValueError("请先配置 MaaEnd 安装路径")

    result = LogBundleSelection()
    for root_path, configs in installations.items():
        project, _ = read_project_info(root_path)
        candidates: list[Path] = []
        for config in configs:
            saved_root = config.Run.LogBundlePath
            if not config.Run.IfSaveLogBundle or saved_root is None:
                continue
            if not saved_root.is_dir():
                continue
            candidates.extend(
                directory
                for directory in saved_root.iterdir()
                if directory.is_dir()
                and directory.name.startswith(f"{project}-logs-")
                and _parse_export_timestamp(directory.name) is not None
                and any(directory.glob(f"{directory.name}-part*.zip"))
            )
        if candidates:
            latest = max(
                candidates,
                key=lambda directory: _parse_export_timestamp(directory.name),
            )
            result.directories.append(str(latest))
        elif output_directory is None:
            result.needs_directory = True
        else:
            # 各安装分开保存，避免相同项目版本在同一秒导出时互相覆盖。
            install_key = hashlib.sha256(str(root_path).encode()).hexdigest()[:12]
            export = export_failure_logs(
                output_directory / install_key, root_path, retain=False
            )
            if export is None:
                raise ValueError(f"没有可导出的 MaaEnd 日志: {root_path}")
            result.directories.append(str(export.directory))
            result.incomplete_count += export.failed_files
    result.directories = list(dict.fromkeys(result.directories))
    return result


async def resolve_log_bundles(
    scripts: list["MaaEndConfig"], output_directory: Path | None = None
) -> LogBundleSelection:
    """在线程中查询或保存日志包，避免文件扫描和压缩阻塞事件循环。"""

    return await asyncio.to_thread(_resolve_log_bundles, scripts, output_directory)
