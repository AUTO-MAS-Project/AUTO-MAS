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
- 保留：只在导出根目录下按目录名末尾的时间戳留最近 10 份，本次
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
import re
import shutil
import zipfile
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.config import MaaEndConfig

import json5

from app.utils import get_logger

logger = get_logger("MaaEnd 日志打包")

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


def _collect_files(
    directory: Path,
    prefix: str,
    *,
    suffixes: set[str] | None = None,
    recursive: bool = False,
) -> list[tuple[Path, str]]:
    """收集指定目录；可选目录缺失时跳过，读取失败直接向调用方报错。"""

    try:
        children = sorted(directory.iterdir())
    except FileNotFoundError:
        return []
    entries = []
    for path in children:
        if path.is_symlink():
            continue
        member = f"{prefix}/{path.name}" if prefix else path.name
        if recursive and path.is_dir():
            entries.extend(
                _collect_files(path, member, suffixes=suffixes, recursive=True)
            )
        elif path.is_file() and (suffixes is None or path.suffix.lower() in suffixes):
            entries.append((path, member))
    return sorted(entries, key=lambda entry: entry[1])


def collect_mxu_entries(root_path: Path) -> list[tuple[Path, str]]:
    """按 MXU 顺序收集：根日志、配置、子目录日志、由新到旧的截图。"""

    debug_dir = root_path / "debug"
    subdirs = sorted(
        path for path in debug_dir.iterdir() if path.is_dir() and not path.is_symlink()
    )
    entries = [
        *_collect_files(debug_dir, "", suffixes={".log", ".dmp"}),
        *_collect_files(root_path / "config", "config", recursive=True),
    ]
    entries.extend(
        sorted(
            (
                entry
                for subdir in subdirs
                for entry in _collect_files(
                    subdir,
                    subdir.name,
                    suffixes={".log", ".json", ".dmp"},
                    recursive=True,
                )
            ),
            key=lambda entry: entry[1],
        )
    )
    for name in ("on_error", "vision"):
        images = _collect_files(
            debug_dir / name, name, suffixes={".png", ".jpg", ".jpeg"}
        )
        entries.extend(
            sorted(images, key=lambda entry: entry[0].stat().st_mtime, reverse=True)
        )
    return entries


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


def _write_volumes(
    out_dir: Path,
    dir_name: str,
    members: list[tuple[Path, str]],
    *,
    width: int,
) -> tuple[list[Path], int]:
    """按 MXU 两阶段容量判断换卷；单个超大文件独占一卷，不截断。

    卷先写 .tmp 再改名。文件读写失败计入不完整结果；导出文件的创建和收尾失败
    直接抛出，由调用方保留现场。上下文管理器负责关闭压缩流和文件。
    """

    max_volume_bytes = 24_500_000  # 与 MXU 的单卷上限一致。
    central_fixed_bytes = 46  # ZIP 中央目录每条记录，不含文件名。
    eocd_bytes = 22  # ZIP 结尾记录。
    local_header_overhead = 64  # local header + DEFLATE 帧头及余量，与 MXU 一致。
    # 文本先按四分之一体积估算，触线后再实测压缩大小。
    text_suffixes = {".log", ".json", ".txt", ".toml", ".yaml", ".yml", ".xml", ".csv"}
    volumes: list[Path] = []
    failed_files = 0
    index = 0
    while index < len(members):
        volume = out_dir / f"{dir_name}-part{len(volumes) + 1:0{width}d}.zip"
        temporary = volume.with_name(volume.name + ".tmp")
        try:
            with (
                temporary.open("wb") as handle,
                zipfile.ZipFile(
                    handle,
                    "w",
                    zipfile.ZIP_DEFLATED,
                    allowZip64=True,
                    strict_timestamps=False,
                ) as archive,
            ):
                written = 0
                central = eocd_bytes
                while index < len(members):
                    source, member = members[index]
                    member_bytes = len(member.encode("utf-8")) + central_fixed_bytes
                    before = len(archive.filelist)
                    try:
                        size = source.stat().st_size
                        estimated = (
                            size // 4
                            if source.suffix.lower() in text_suffixes
                            else size
                        )
                        remaining = max_volume_bytes - (written + central)
                        overhead = local_header_overhead + member_bytes
                        if (
                            written
                            and estimated + overhead > remaining
                            and _deflate_size(source) + overhead > remaining
                        ):
                            break
                        archive.write(source, member)
                    except OSError as error:
                        logger.warning(f"写入日志文件失败 {source}: {error}")
                        failed_files += 1
                    index += 1
                    written = handle.tell()
                    if len(archive.filelist) > before:
                        central += member_bytes
            if written:
                temporary.replace(volume)
                volumes.append(volume)
        finally:
            temporary.unlink(missing_ok=True)
    return volumes, failed_files


def _parse_export_timestamp(dir_name: str) -> str | None:
    """取名称末尾的 ASCII 时间戳；无时间戳的目录不参与保留策略。"""

    match = re.search(r"[0-9]{8}-[0-9]{6}\Z", dir_name)
    return match.group() if match else None


def prune_old_exports(exports_root: Path, *, current_export: Path) -> None:
    """按名称时间戳保留最近 10 份，本次产物始终保留；清理失败仅告警。"""

    max_exports_to_keep = 10
    timestamp_length = 15  # YYYYMMDD-HHMMSS。
    try:
        candidates = sorted(
            (
                path
                for path in exports_root.iterdir()
                if path != current_export
                and path.is_dir()
                and _parse_export_timestamp(path.name) is not None
            ),
            key=lambda path: path.name[-timestamp_length:],
            reverse=True,
        )
    except OSError as error:
        logger.warning(f"枚举导出目录失败 {exports_root}: {error}，跳过旧导出清理")
        return
    for path in candidates[max_exports_to_keep - 1 :]:
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

    project_name, project_version = read_project_info(root_path)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    dir_name = (
        f"{project_name}-logs-{project_version}-{stamp}"
        if project_version
        else f"{project_name}-logs-{stamp}"
    )
    out_dir = exports_root / dir_name
    out_dir.mkdir(parents=True, exist_ok=True)
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
            if not config.Run.IfSaveLogBundle:
                continue
            saved_root = config.Run.LogBundlePath or Path.cwd() / "debug/maaend"
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
