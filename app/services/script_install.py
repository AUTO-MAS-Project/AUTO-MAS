#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""脚本发行包的校验、隔离展开和可恢复目录切换，不执行包内程序。"""

import asyncio
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import threading
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from app.utils import update_files


class InstallUnsafeError(RuntimeError):
    """不能确认安装完整或仍有进程访问，必须停止启动。"""


def _key(root: Path) -> str:
    return hashlib.sha256(os.path.normcase(str(root.resolve())).encode()).hexdigest()


def workspace(root: Path) -> Path:
    return root.parent / f".mas-update-{_key(root)[:24]}"


@contextmanager
def installation_access(root: Path) -> Iterator[None]:
    """跨 MAS 进程互斥；调用方须持有到任务/配置恢复结束。"""
    directory = Path(tempfile.gettempdir()) / "auto-mas-install-locks"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / f"{_key(root)}.lock").open("a+b") as handle:
        if handle.seek(0, 2) == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise InstallUnsafeError(
                "脚本安装正被另一个任务使用，请稍后重试"
            ) from error
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


async def run_worker(function: Callable, *args, **kwargs):
    """取消后等待文件操作确实停止，线程不能在任务退出后继续写入。"""
    cancelled = threading.Event()
    work = asyncio.create_task(asyncio.to_thread(function, *args, cancelled, **kwargs))
    try:
        return await asyncio.shield(work)
    except asyncio.CancelledError:
        cancelled.set()
        while not work.done():
            try:
                await asyncio.shield(work)
            except (asyncio.CancelledError, Exception):
                if work.done():
                    break
        # 取出异常，取消的任务仍以 CancelledError 收口。
        if not work.cancelled():
            work.exception()
        raise


def _check_cancel(cancelled: threading.Event) -> None:
    if cancelled.is_set():
        raise InterruptedError("更新已取消")


def _reject_link(path: Path) -> None:
    info = path.lstat()
    if (
        stat.S_ISLNK(info.st_mode)
        or getattr(info, "st_reparse_tag", 0)
        or (
            getattr(info, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        )
    ):
        raise InstallUnsafeError("安装目录包含链接或重解析点，不能自动更新")


def tree_hashes(root: Path, cancelled: threading.Event) -> dict[str, str]:
    """包括配置等保留文件，复核复制期间是否出现外部改动。"""
    _reject_link(root)
    result = {}
    for parent, directories, files in os.walk(root, followlinks=False):
        for name in [*directories, *files]:
            _check_cancel(cancelled)
            path = Path(parent) / name
            _reject_link(path)
            if path.is_file():
                with path.open("rb") as handle:
                    result[path.relative_to(root).as_posix()] = hashlib.file_digest(
                        handle, "sha256"
                    ).hexdigest()
    return result


def verify_archive(
    path: Path, size: int, digest: str, cancelled: threading.Event
) -> None:
    _check_cancel(cancelled)
    if size <= 0 or path.stat().st_size != size:
        raise ValueError("更新包大小与官方声明不符")
    if not re.fullmatch(r"[a-fA-F0-9]{64}", digest):
        raise ValueError("更新包缺少有效的 SHA256")
    with path.open("rb") as handle:
        actual = hashlib.file_digest(handle, "sha256").hexdigest()
    if actual.lower() != digest.lower():
        raise ValueError("更新包 SHA256 校验失败")
    _check_cancel(cancelled)


def _member_name(name: str) -> str:
    text = name.replace("\\", "/")
    parts = text.rstrip("/").split("/")
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if not parts or any(
        not p
        or p in {".", ".."}
        or p.endswith((".", " "))
        or re.search(r'[<>:"|?*\x00-\x1f]', p)
        or p.split(".")[0].upper() in reserved
        for p in parts
    ):
        raise ValueError("更新包包含非法路径")
    return "/".join(parts)


def extract_package(
    archive: Path,
    destination: Path,
    protected: frozenset[str],
    cancelled: threading.Event,
) -> None:
    """不信任 ZIP 路径、文件类型及声明大小；限制条目数和展开体积。"""
    destination.mkdir(parents=True)
    seen: set[str] = set()
    files: set[str] = set()
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        total = sum(item.file_size for item in entries)
        if len(entries) > 100_000 or not entries or total > 8 * 1024**3:
            raise ValueError("更新包条目数或展开体积超出限制")
        if shutil.disk_usage(destination).free < total + 256 * 1024**2:
            raise OSError("磁盘空间不足，无法安全展开更新包")
        for item in entries:
            _check_cancel(cancelled)
            name = _member_name(item.filename)
            key = name.casefold()
            mode = (item.external_attr >> 16) & 0o170000
            if mode not in (0, stat.S_IFREG, stat.S_IFDIR) or item.flag_bits & 1:
                raise ValueError("更新包包含链接、特殊文件或加密成员")
            if key in seen or any(parent in files for parent in _parents(key)):
                raise ValueError("更新包包含重名文件或文件目录冲突")
            seen.add(key)
            if key.split("/")[0] in protected:
                raise ValueError("更新包试图覆盖配置或运行数据")
            target = update_files.resolve_within(destination, name, reject_links=True)
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            files.add(key)
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(item) as source, target.open("xb") as output:
                copied = 0
                while chunk := source.read(1024 * 1024):
                    _check_cancel(cancelled)
                    copied += len(chunk)
                    if copied > item.file_size:
                        raise ValueError("更新包成员展开大小异常")
                    output.write(chunk)
            if copied != item.file_size:
                raise ValueError("更新包成员不完整")


def _parents(name: str) -> list[str]:
    parts = name.split("/")
    return ["/".join(parts[:index]) for index in range(1, len(parts))]


def _write_state(
    directory: Path, state: dict, filename: str = "transaction.json"
) -> None:
    temporary = directory / f"{filename}.tmp"
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(directory / filename)


def verify_installed_files(root: Path, cancelled: threading.Event) -> bool:
    """校验上次经可信包安装的分发文件；配置与新增运行数据不参与比较。"""
    receipt = workspace(root) / "installed.json"
    if not receipt.exists():
        return False
    try:
        _reject_link(receipt)
        files = json.loads(receipt.read_text(encoding="utf-8"))["files"]
        if not isinstance(files, dict) or not files:
            raise ValueError("empty receipt")
        for name, expected in files.items():
            _check_cancel(cancelled)
            target = update_files.resolve_within(
                root, _member_name(name), reject_links=True
            )
            with target.open("rb") as handle:
                if hashlib.file_digest(handle, "sha256").hexdigest() != expected:
                    return False
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def recover_install(
    root: Path, assert_idle: Callable[[], None], cancelled: threading.Event
) -> None:
    """不猜测损坏记录；已切换目录须匹配完整快照才能确认提交。"""
    directory = workspace(root)
    journal = directory / "transaction.json"
    if not journal.exists():
        if (directory / "previous").exists():
            raise InstallUnsafeError("安装备份存在但恢复记录缺失，请保留现场并手动恢复")
        return
    assert_idle()
    _reject_link(directory)
    _reject_link(journal)
    try:
        state = json.loads(journal.read_text(encoding="utf-8"))
        if state.get("root") != str(root.resolve()) or not isinstance(
            state.get("files"), dict
        ):
            raise ValueError("invalid transaction")
        previous = directory / "previous"
        ready = directory / "ready"
        if previous.exists():
            _reject_link(previous)
            if not root.exists():
                previous.replace(root)
            elif not ready.exists() and tree_hashes(root, cancelled) == state["files"]:
                # 原安装中的外部修改可能仅留在 previous，不能直接删掉。
                original_files = state.get("original_files")
                if (
                    not isinstance(original_files, dict)
                    or tree_hashes(previous, cancelled) != original_files
                ):
                    raise InstallUnsafeError(
                        "原安装备份发生外部修改，已保留现场，不能自动删除备份"
                    )
                _write_state(
                    directory, {"files": state["package_files"]}, "installed.json"
                )
                shutil.rmtree(previous)
            else:
                raise InstallUnsafeError(
                    "更新中断后目录发生变化，请保留原安装备份并手动恢复"
                )
        elif not root.exists():
            raise InstallUnsafeError("安装目录与备份同时缺失，不能启动")
        elif not ready.exists() and tree_hashes(root, cancelled) != state["files"]:
            raise InstallUnsafeError("更新恢复校验未通过，不能启动")
        elif not ready.exists():
            _write_state(directory, {"files": state["package_files"]}, "installed.json")
        journal.unlink()
    except InstallUnsafeError:
        raise
    except Exception as error:
        raise InstallUnsafeError("无法确认脚本更新恢复状态，已停止启动") from error


def _refresh_merged_pipelines(
    ready: Path,
    package: Path,
    directory: Path,
    cancelled: threading.Event,
) -> None:
    """重建官方已合并的 pipeline，保留旧版文件的完整独立备份。

    旧拆分 JSON 与新版 nodes.json 共存会产生同名节点，导致资源加载失败。
    只针对发行包明确包含 resource*/pipeline/nodes.json 的完整资源目录；
    旧文件备份在工作区，不会被 MaaFramework 递归加载。
    """
    backup_root: Path | None = None
    for resource in package.iterdir():
        _check_cancel(cancelled)
        if not resource.is_dir() or not resource.name.startswith("resource"):
            continue
        packaged_pipeline = resource / "pipeline"
        if not (packaged_pipeline / "nodes.json").is_file():
            continue
        existing = ready / resource.name / "pipeline"
        if not existing.exists():
            continue
        _reject_link(existing)
        if not existing.is_dir():
            raise InstallUnsafeError("原 pipeline 路径不是目录，不能安全更新")
        # 没有完整旧清单时也要识别新版已废弃的文件。
        # 即使是用户定制的 JSON 也不丢弃：备份后才从运行目录移出。
        has_obsolete = any(
            entry.is_file()
            and not (packaged_pipeline / entry.relative_to(existing)).is_file()
            for entry in existing.rglob("*")
        )
        if not has_obsolete:
            continue
        if backup_root is None:
            saved = directory / "retired-pipelines"
            saved.mkdir(exist_ok=True)
            _reject_link(saved)
            backup_root = Path(tempfile.mkdtemp(prefix="pipeline-", dir=saved))
            (backup_root / "README.txt").write_text(
                "旧版 MaaEnd pipeline 已在完整包升级时迁移到此备份。"
                "这些文件不会再由新版资源加载器读取；需要自定义配置时请手动核对后迁移。\n",
                encoding="utf-8",
            )
        previous_hashes = tree_hashes(existing, cancelled)
        saved_pipeline = backup_root / resource.name / "pipeline"
        saved_pipeline.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(existing, saved_pipeline)
        if tree_hashes(saved_pipeline, cancelled) != previous_hashes:
            raise InstallUnsafeError("旧 pipeline 备份校验失败，已停止安装")
        _check_cancel(cancelled)
        shutil.rmtree(existing)


def install_package(
    root: Path,
    archive: Path,
    size: int,
    digest: str,
    protected: frozenset[str],
    validate: Callable[[Path], None],
    assert_idle: Callable[[], None],
    cancelled: threading.Event,
    *,
    refresh_merged_pipelines: bool = False,
) -> None:
    """完整暂存后才切换目录，失败保留原安装；不根据版本文件推断完整性。"""
    recover_install(root, assert_idle, cancelled)
    assert_idle()
    verify_archive(archive, size, digest, cancelled)
    directory = workspace(root)
    directory.mkdir(exist_ok=True)
    _reject_link(directory)
    ready, package, previous = (
        directory / name for name in ("ready", "package", "previous")
    )
    for target in (ready, package):
        if target.exists():
            _reject_link(target)
            shutil.rmtree(target)
    extract_package(archive, package, protected, cancelled)
    validate(package)
    package_files = tree_hashes(package, cancelled)
    before = tree_hashes(root, cancelled)
    required = sum(path.stat().st_size for path in root.rglob("*") if path.is_file())
    if shutil.disk_usage(directory).free < required + 256 * 1024**2:
        raise OSError("磁盘空间不足，无法保留原安装并准备更新")
    shutil.copytree(root, ready)
    receipt = directory / "installed.json"
    if receipt.exists():
        old_files = json.loads(receipt.read_text(encoding="utf-8"))["files"]
        for name, digest in old_files.items():
            if name in package_files:
                continue
            if _member_name(name).split("/")[0].casefold() in protected:
                raise InstallUnsafeError("旧安装清单包含受保护数据，停止自动更新")
            obsolete = update_files.resolve_within(ready, name, reject_links=True)
            if obsolete.is_file():
                with obsolete.open("rb") as handle:
                    if hashlib.file_digest(handle, "sha256").hexdigest() != digest:
                        raise InstallUnsafeError(
                            "待移除的旧版文件曾被外部修改，已保留原安装"
                        )
                obsolete.unlink()
    if refresh_merged_pipelines:
        _refresh_merged_pipelines(ready, package, directory, cancelled)
    for source in package.rglob("*"):
        _check_cancel(cancelled)
        target = update_files.resolve_within(
            ready, source.relative_to(package), reject_links=True
        )
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            shutil.copy2(source, target)
    validate(ready)
    expected = tree_hashes(ready, cancelled)
    if any(expected.get(name) != digest for name, digest in package_files.items()):
        raise ValueError("暂存安装与已校验更新包不一致")
    if tree_hashes(root, cancelled) != before:
        raise InstallUnsafeError("准备更新期间安装内容被外部修改，已停止切换")
    _check_cancel(cancelled)
    assert_idle()
    _write_state(
        directory,
        {
            "root": str(root.resolve()),
            "files": expected,
            "original_files": before,
            "package_files": package_files,
        },
    )
    try:
        root.replace(previous)
        try:
            if tree_hashes(previous, threading.Event()) != before:
                raise InstallUnsafeError(
                    "原安装在切换前被外部修改，已回滚以保留用户数据"
                )
            ready.replace(root)
        except BaseException:
            previous.replace(root)
            (directory / "transaction.json").unlink()
            raise
        # 切换之后禁止因取消而跳过确认；完成确认或留下恢复记录后再响应取消。
        assert_idle()
        if tree_hashes(root, threading.Event()) != expected:
            raise InstallUnsafeError("更新后完整性复核失败，已保留原安装备份")
        validate(root)
        if tree_hashes(previous, threading.Event()) != before:
            raise InstallUnsafeError(
                "切换期间原安装备份被外部修改，已保留备份，请手动处理"
            )
        _write_state(directory, {"files": package_files}, "installed.json")
        shutil.rmtree(previous)
        (directory / "transaction.json").unlink()
    except BaseException as error:
        raise InstallUnsafeError(
            "安装切换未完成确认，请重试恢复；原安装备份已保留"
        ) from error
    shutil.rmtree(package)


def read_pe_architecture(executable: Path) -> str:
    with executable.open("rb") as handle:
        if handle.read(2) != b"MZ":
            raise ValueError("脚本程序不是可识别的 Windows 可执行文件")
        handle.seek(60)
        offset = int.from_bytes(handle.read(4), "little")
        if offset < 64 or offset > 16 * 1024 * 1024:
            raise ValueError("脚本程序 PE 头无效")
        handle.seek(offset)
        header = handle.read(6)
    arch = {0x8664: "x86_64", 0xAA64: "aarch64"}.get(
        int.from_bytes(header[4:6], "little")
    )
    if header[:4] != b"PE\0\0" or arch is None:
        raise ValueError("无法识别脚本程序架构")
    return arch
