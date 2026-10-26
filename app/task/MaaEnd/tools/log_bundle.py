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

规则对齐 MXU ``src-tauri/src/commands/file_ops.rs`` 的 ``export_logs``：收集
``debug/`` 根目录的 .log 与 .dmp、``config/`` 全量、``debug/`` 各子目录里的
.log/.json/.dmp，以及 ``on_error/``、``vision/`` 的截图；单卷上限 24.5 MB，
超出切成 ``-partNN.zip``。打包对象是上游安装现场的日志，MAS 自身的运行日志
走历史库，不在本模块范围内。

产物按「一次任务运行」分组：一次运行一个目录，运行里每次失败尝试各占一个子
目录，所以保存目录里的保留上限按运行次数计，不会因为一次运行的多次重试就把
之前的证据挤掉。目录里的 ``bundle.json`` 既是给人看的清单，也是清理旧包时
「这个目录是我建的」的唯一凭据。

同一套收集规则在前端还有一份实现：``frontend/electron/services/maaEndIssueReportService.ts``
（界面导出「MaaEnd 问题包」时用）。改收集范围、扩展名或单卷上限时要两边一起改，
否则自动保存的日志包和手动导出的问题包内容会不一致。
"""

import json
import os
import re
import shutil
import zipfile
import zlib
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

import json5

from app.utils import get_logger

logger = get_logger("MaaEnd 日志打包")

MAX_VOLUME_BYTES = 24_500_000
"""单卷上限，与 MXU 的 MAX_VOLUME_BYTES 一致。"""

MAX_BUNDLES_TO_KEEP = 10
"""同一目录下最多保留几次运行的日志包，口径与 MXU 的 MAX_EXPORTS_TO_KEEP 一致。"""

_MANIFEST_NAME = "bundle.json"
"""运行目录里的清单文件名，同时也是清理旧包时的自建标记。"""
_MANIFEST_TOOL = "auto-mas"
_MANIFEST_KIND = "maaend-failure-bundle"

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
_ROOT_LOG_SUFFIXES = {".log", ".dmp"}
_DEBUG_SUFFIXES = {".log", ".json", ".dmp"}
"""debug 子目录里的归档后缀。"""
_TEXT_SUFFIXES = {".log", ".json", ".txt", ".toml", ".yaml", ".yml", ".xml", ".csv"}
"""按四分之一体积估算的文本后缀，与 MXU 的两阶段容量判断保持一致。"""

_ZIP_CENTRAL_FIXED_BYTES = 46
"""ZIP 中央目录每条记录的固定字段大小，不含文件名。"""
_ZIP_EOCD_BYTES = 22
"""ZIP 结尾记录的大小。"""

_UNSAFE_NAME_CHARS = re.compile(r'[\\/:*?"<>|]')
_ARCHIVE_SEPARATORS = re.compile(r"[\\/]+")
_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


@dataclass
class BundleAttempt:
    """一次失败尝试的打包结果。"""

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


def _read_manifest(directory: Path) -> dict[str, object] | None:
    """读取运行目录清单；不是本模块建的目录返回 ``None``。"""

    try:
        value = json.loads((directory / _MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(value, dict):
        return None
    if value.get("tool") != _MANIFEST_TOOL or value.get("kind") != _MANIFEST_KIND:
        return None
    return value


def _write_manifest(directory: Path, data: dict[str, object]) -> None:
    """原子写入运行目录清单。"""

    path = directory / _MANIFEST_NAME
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporary, path)


def prepare_bundle_round(
    target_dir: Path,
    root_path: Path,
    *,
    user_name: str = "",
    now: datetime | None = None,
) -> Path:
    """为一次任务运行准备日志包目录，并写入清单。

    目录名沿用 MXU 的 ``<项目>-logs-<版本>-<时间戳>`` 形式；同一秒内撞名或多个
    安装共用同一个保存目录时依次加 ``-2``、``-3``，绝不复用已有目录。

    Args:
        target_dir (Path): 用户配置的保存目录，不存在时创建。
        root_path (Path): MaaEnd 安装目录，用于读取项目名与版本。
        user_name (str): 本次运行的用户名，只记进清单，不参与目录命名。
        now (datetime | None): 用于生成时间戳的时间，默认当前时间。

    Returns:
        Path: 本次运行的日志包目录。

    Raises:
        OSError: 保存目录不可写，或无法创建唯一的日志包目录。
    """

    project_name, project_version = read_project_info(root_path)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    base_name = (
        f"{project_name}-logs-{project_version}-{stamp}"
        if project_version
        else f"{project_name}-logs-{stamp}"
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    for index in range(1, 100):
        candidate = target_dir / (base_name if index == 1 else f"{base_name}-{index}")
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        try:
            _write_manifest(
                candidate,
                {
                    "tool": _MANIFEST_TOOL,
                    "kind": _MANIFEST_KIND,
                    "created": datetime.now()
                    .astimezone()
                    .isoformat(timespec="seconds"),
                    "project": project_name,
                    "version": project_version,
                    "user": user_name,
                    "attempts": [],
                },
            )
        except OSError:
            shutil.rmtree(candidate, ignore_errors=True)
            raise
        return candidate
    raise OSError(f"无法在 {target_dir} 创建唯一的日志包目录")


def _create_attempt_dir(round_dir: Path, attempt_no: int) -> Path:
    """在运行目录里创建这次尝试的子目录。"""

    base_name = f"attempt-{attempt_no:02d}"
    for index in range(1, 100):
        candidate = round_dir / (base_name if index == 1 else f"{base_name}-{index}")
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise OSError(f"无法在 {round_dir} 创建唯一的尝试目录")


def _write_volumes(
    attempt_dir: Path,
    base_name: str,
    members: list[tuple[Path, str]],
    *,
    width: int,
) -> tuple[list[Path], int]:
    """把条目按 MXU 的分卷规则写成 ZIP，返回卷路径与读取失败的文件数。

    卷先写成 ``.tmp`` 再改名，取消或崩溃不会留下被当成正式包的半截 ZIP。
    换卷判断沿用 MXU 的两阶段口径：先用体积估算，只有估算触线的那一份才算实际
    压缩大小确认，所以绝大多数文件只压缩一次。
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
        volume_path = attempt_dir / f"{base_name}-part{index:0{width}d}.zip"
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
            if written and estimated + 64 + member_bytes > remaining:
                try:
                    measured = _deflate_size(source)
                except OSError as error:
                    logger.warning(f"无法读取日志文件 {source}: {error}")
                    failed_files += 1
                    continue
                if measured + 64 + member_bytes > remaining:
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
        # 失败路径也把 .tmp 清掉：半截包不能被当成正式包留在目录里。
        if archive is not None:
            with suppress(Exception):
                archive.close()
        if handle is not None:
            with suppress(Exception):
                handle.close()
        if volume_tmp is not None:
            volume_tmp.unlink(missing_ok=True)
    return volumes, failed_files


def _record_attempt(
    round_dir: Path,
    *,
    attempt_no: int,
    label: str,
    stage: str | None,
    attempt: BundleAttempt,
    now: datetime | None,
) -> None:
    """把这次尝试的结果追加到运行目录清单；写不进去不影响日志包本身。"""

    manifest = _read_manifest(round_dir)
    if manifest is None:
        manifest = {"tool": _MANIFEST_TOOL, "kind": _MANIFEST_KIND}
    attempts = manifest.get("attempts")
    if not isinstance(attempts, list):
        attempts = []
        manifest["attempts"] = attempts
    attempts.append(
        {
            "attempt": attempt_no,
            "label": label,
            "stage": stage,
            "saved_at": (now or datetime.now())
            .astimezone()
            .isoformat(timespec="seconds"),
            "volumes": len(attempt.volumes),
            "files": attempt.files,
            "failed_files": attempt.failed_files,
            "bytes": attempt.bytes,
        }
    )
    try:
        _write_manifest(round_dir, manifest)
    except OSError as error:
        logger.warning(f"更新日志包清单失败 {round_dir}: {error}")


def _prune_old_bundles(target_dir: Path, *, current: Path, keep: int) -> None:
    """只保留最近 ``keep`` 次运行的日志包目录。

    只删带本模块清单且清单判定通过的目录：用户自己在保存目录里放的同名文件夹
    一律不碰，删错了没法恢复。
    """

    candidates: list[tuple[str, Path]] = []
    try:
        entries = list(target_dir.iterdir())
    except OSError as error:
        logger.warning(f"枚举日志包目录失败 {target_dir}: {error}")
        return
    for path in entries:
        if path == current or not path.is_dir() or path.is_symlink():
            continue
        manifest = _read_manifest(path)
        if manifest is None:
            continue
        candidates.append((str(manifest.get("created") or ""), path))
    if len(candidates) < keep:
        return
    candidates.sort(key=lambda item: item[0])
    for _, path in candidates[: len(candidates) - keep + 1]:
        try:
            shutil.rmtree(path)
        except OSError as error:
            logger.warning(f"清理旧日志包失败 {path}: {error}")
        else:
            logger.info(f"已清理旧 MaaEnd 日志包: {path.name}")


def build_attempt_bundle(
    round_dir: Path,
    root_path: Path,
    *,
    attempt_no: int,
    label: str = "",
    stage: str | None = None,
    now: datetime | None = None,
    keep: int = MAX_BUNDLES_TO_KEEP,
) -> BundleAttempt | None:
    """把当前失败现场的 MaaEnd 运行日志打包到运行目录下的尝试子目录。

    Args:
        round_dir (Path): 由 :func:`prepare_bundle_round` 创建的运行目录。
        root_path (Path): MaaEnd 安装目录，读取其 ``debug/`` 与 ``config/``。
        attempt_no (int): 本次运行里的第几次失败尝试，从 1 开始。
        label (str): 写进清单的尝试标识，如 ``原配置阶段第 2 次尝试``。
        stage (str | None): 写进清单的阶段名。
        now (datetime | None): 用于记录时间的时间，默认当前时间。
        keep (int): 同一保存目录保留的运行次数上限。

    Returns:
        BundleAttempt | None: 打包结果；没有可打包内容时返回 ``None``。

    Raises:
        OSError: 保存目录或运行目录不可写，或一个日志文件都没写成功。
    """

    entries = collect_mxu_entries(root_path)
    if not entries:
        logger.warning(f"没有可打包的日志文件: {root_path}")
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
        return None

    attempt_dir = _create_attempt_dir(round_dir, attempt_no)
    width = 3 if len(members) >= 100 else 2
    volumes, write_failures = _write_volumes(
        attempt_dir, round_dir.name, members, width=width
    )
    failed_files += write_failures
    if not volumes:
        shutil.rmtree(attempt_dir, ignore_errors=True)
        # 一个文件都没写成功属于打包失败，不能当成「没有内容」吞掉：调用方要留着
        # 现场、并在收尾再试一次。
        raise OSError(f"没有日志文件写入成功: {root_path}")

    attempt = BundleAttempt(
        directory=attempt_dir,
        volumes=volumes,
        files=len(members) - write_failures,
        failed_files=failed_files,
        bytes=sum(volume.stat().st_size for volume in volumes),
    )
    _record_attempt(
        round_dir,
        attempt_no=attempt_no,
        label=label,
        stage=stage,
        attempt=attempt,
        now=now,
    )
    _prune_old_bundles(round_dir.parent, current=round_dir, keep=keep)
    logger.success(f"MaaEnd 运行日志打包完成: {attempt_dir}（{len(volumes)} 卷）")
    return attempt
