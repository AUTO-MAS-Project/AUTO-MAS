#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""魔改 AVD 更新器：查更新、下载、拼新版、换上、回退、开机确认、启动恢复、空闲时自动装。

流程（每个根目录各走各的，下载缓存可以共用）：

1. **查更新**：问 :func:`.update_source.update_sources` 里的源（现在只有 GitHub），结果缓存 4 小时；
   MAS 启动时查一次，用户点「检查更新」不走缓存。失败只记日志，不弹窗、不挡启动。
2. **下载**：到 ``<根>\\.update\\download``（同盘、续传），按发布记录的 SHA-256 核对；实例开着也能下。
3. **拼新版**：解到 ``pkg``、按清单逐文件核对（旧版包没有清单，靠包的 SHA-256 + zip CRC），
   ``sdk\\emulator`` 改名进 ``stage``（:mod:`.update_stage`）。
4. **换上**：只有没有任何进程的可执行文件在 ``sdk\\emulator`` 下时才换；要关实例只走现有的
   ``close``（安卓正常关机，不行再 sync + kill），不硬杀。
5. **确认与回退**：新版第一次开机到 ``sys.boot_completed`` 就删掉旧版；在那之前可以回退。

设了 ``sdkRoot``（开发用的本地 SDK）的根目录不更新。进度经主 WebSocket 推
（``id=EmulatorManager``、``type=emulator2.avd-update.progress``），界面另用 HTTP 快照兜底。
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from app.services.update_transport import download_resumable
from app.utils import get_logger
from app.utils.update_files import native_path

from . import update_stage as stage
from .components import local_sdk_root, manager_key_exe, root_key
from .constants import (
    MIN_MOD_AVD_BUILD,
    MODAVD_MANIFEST_FILE,
    POWER_CLOSE_TIMEOUT_SECONDS,
    UPDATE_CHECK_CACHE_SECONDS,
    UPDATE_MIN_FREE_BYTES,
)
from .update_source import (
    ModAvdVersion,
    RemoteRelease,
    UpdateSourceError,
    automas_too_old,
    local_version,
    newer_changes,
    parse_version,
    read_manifest_file,
    update_sources,
)

logger = get_logger("魔改 AVD 更新")

#: 查更新失败后多久之内不再自动重试（用户点「检查更新」不受限）。
_CHECK_FAILURE_BACKOFF_SECONDS = 600.0
#: 下载失败自动重试的次数（续传接着下）。
_DOWNLOAD_ATTEMPTS = 3
_DOWNLOAD_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
#: 进度消息最密多久发一条。
_PUBLISH_INTERVAL_SECONDS = 0.5


@dataclass
class _Progress:
    """推给界面的进度：``stage`` 是当前在做的事，``status`` 是 running / success / failed / idle。"""

    stage: str = "idle"
    status: str = "idle"
    message: str = ""
    percent: float | None = None
    downloadedBytes: int | None = None
    totalBytes: int | None = None
    speedBytesPerSec: float | None = None


class _Runtime:
    """一个根目录在本进程里的更新状态：同一时刻只跑一个下载 / 安装 / 回退。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.lock = asyncio.Lock()
        self.job: asyncio.Task[None] | None = None
        self.progress = _Progress()
        self.cancel_requested = False
        self.published_at = 0.0

    @property
    def busy(self) -> bool:
        return self.job is not None and not self.job.done()


_runtimes: dict[str, _Runtime] = {}
#: 正在换上 / 回退的根目录：这段时间不许开机。
_swapping: set[str] = set()
#: 后台小任务（开机确认、自动安装）的引用，免得被回收。
_background: set[asyncio.Task[Any]] = set()

_remote: RemoteRelease | None = None
_remote_at = 0.0
_remote_failed_at = 0.0
_remote_error = ""
_checked_at: datetime | None = None
_check_lock = asyncio.Lock()


def _runtime(root: Path) -> _Runtime:
    key = root_key(root)
    runtime = _runtimes.get(key)
    if runtime is None:
        runtime = _runtimes[key] = _Runtime(root)
    return runtime


def _spawn(coroutine: Any, name: str) -> None:
    task = asyncio.get_running_loop().create_task(coroutine, name=name)
    _background.add(task)
    task.add_done_callback(_background.discard)


# ---- 进度 ------------------------------------------------------------------


def _set(
    runtime: _Runtime,
    stage_name: str,
    status: str = "running",
    message: str = "",
    **fields: Any,
) -> None:
    runtime.progress = _Progress(
        stage=stage_name, status=status, message=message, **fields
    )


async def _publish(runtime: _Runtime, *, force: bool = True) -> None:
    now = time.monotonic()
    if not force and now - runtime.published_at < _PUBLISH_INTERVAL_SECONDS:
        return
    runtime.published_at = now
    from app.core.ws import Publisher, protocol
    from app.models.schema import WSAvdUpdateProgressData

    await Publisher.send(
        id=protocol.ID_EMULATOR_MANAGER,
        type=protocol.AVD_UPDATE_PROGRESS,
        data=WSAvdUpdateProgressData(
            root=str(runtime.root), **asdict(runtime.progress)
        ),
    )


def _thread_progress(
    runtime: _Runtime, stage_name: str, message: str
) -> stage.Progress:
    """给线程里的解包 / 核对用的进度回调：改进度，并按节流把消息投回事件循环发出去。"""
    loop = asyncio.get_running_loop()

    def report(done: int, total: int) -> None:
        _set(
            runtime,
            stage_name,
            message=message,
            percent=round(done * 100 / total, 1) if total else None,
            downloadedBytes=done,
            totalBytes=total,
        )
        now = time.monotonic()
        if now - runtime.published_at >= _PUBLISH_INTERVAL_SECONDS:
            runtime.published_at = now
            asyncio.run_coroutine_threadsafe(_publish(runtime), loop)

    return report


def _cancelled(runtime: _Runtime) -> stage.Cancelled:
    return lambda: runtime.cancel_requested


# ---- 根目录 ----------------------------------------------------------------


def _managed_roots() -> list[Path]:
    from .service import _avd_roots

    return _avd_roots()


async def _managed(root: str) -> Path:
    """只认 Emulator 2.0 里已经加进来的魔改 AVD 根目录：更新会改名目录，不能对任意路径动手。"""
    text = str(root or "").strip()
    if not text or not Path(text).is_absolute():
        raise ValueError("请给出魔改 AVD 根目录的完整路径")
    key = root_key(text)
    for managed in await asyncio.to_thread(_managed_roots):
        if root_key(managed) == key:
            return managed
    raise ValueError(f"{text} 还没有作为魔改 AVD 加进模拟器管理，不能更新")


def _not_updatable_reason(root: Path) -> str:
    if local_sdk_root(root) is not None:
        return "这个根目录在 mas-avd.json 里设了 sdkRoot（开发用的本地 SDK），不更新"
    if not os.path.isfile(native_path(stage.emulator_dir(root) / "emulator.exe")):
        return "这个根目录里没有 sdk\\emulator，请先放好魔改 AVD"
    return ""


def _tasks_running() -> bool:
    from app.core import TaskManager

    return bool(TaskManager.task_handler)


def _running_instances(root: Path) -> list[str]:
    """这个根目录下开着的实例（原生索引）。

    实例按 AVD 名 + 控制台端口认，各根目录的名字和端口是同一套；只算 qemu 可执行文件就在
    这个根目录 ``sdk\\emulator`` 下的，免得把另一个根目录的同名实例算进来、关掉。
    """
    from .manager import AvdManager

    ours = {item["pid"] for item in stage.processes_using(root)}
    running = AvdManager(manager_key_exe(root), 60, False)._scan_processes()
    return sorted(idx for idx, process in running.items() if process.pid in ours)


def swap_in_progress(root: str | Path) -> bool:
    """正在换上 / 回退：这段时间 ``sdk\\emulator`` 可能不在，开机前检查据此拒绝开机。"""
    return root_key(root) in _swapping


# ---- 查更新 ----------------------------------------------------------------


async def _latest(*, force: bool) -> RemoteRelease:
    """最新一版。4 小时内查过就用缓存；查失败后 10 分钟内不自动重试（``force`` 例外）。"""
    global _remote, _remote_at, _remote_failed_at, _remote_error, _checked_at
    async with _check_lock:
        now = time.monotonic()
        if not force:
            if _remote is not None and now - _remote_at < UPDATE_CHECK_CACHE_SECONDS:
                return _remote
            if (
                _remote_failed_at
                and now - _remote_failed_at < _CHECK_FAILURE_BACKOFF_SECONDS
            ):
                if _remote is not None:
                    return _remote
                raise UpdateSourceError(_remote_error)
        from app.core import Config

        errors: list[str] = []
        for source in update_sources():
            try:
                release = await source.latest(proxy=Config.proxy)
            except Exception as e:  # noqa: BLE001 - 一个源不行换下一个，全不行才报
                errors.append(f"{source.name}: {e}")
                continue
            _remote, _remote_at, _remote_failed_at, _remote_error = (
                release,
                time.monotonic(),
                0.0,
                "",
            )
            _checked_at = datetime.now()
            logger.info(
                f"ModAVD 最新版本 {release.version}（{release.version.label}，"
                f"tag {release.tag}，来源 {release.source}，包 {release.asset.name}）"
            )
            return release
        _remote_failed_at, _remote_error = time.monotonic(), "；".join(errors)
        _checked_at = datetime.now()
        raise UpdateSourceError(_remote_error)


def _newer(release: RemoteRelease | None, local: ModAvdVersion | None) -> bool:
    return release is not None and (local is None or release.version > local)


def _automas_block(release: RemoteRelease | None) -> str:
    """最新一版要求的 MAS 版本比当前高时，返回那个版本号。"""
    if release is None:
        return ""
    from app.core import Config

    minimum = release.notes.machine.get("min_automas")
    return str(minimum) if automas_too_old(minimum, Config.VERSION) else ""


# ---- 状态快照 --------------------------------------------------------------


def _snapshot_sync(root: Path, runtime: _Runtime) -> dict[str, Any]:
    local = local_version(root)
    reason = _not_updatable_reason(root)
    state = stage.read_state(root)
    prefs = stage.read_prefs(root)
    release = _remote
    newer = not reason and _newer(release, local)
    running = _running_instances(root) if not reason else []
    busy = (
        [f"{item['name']}（pid {item['pid']}）" for item in stage.processes_using(root)]
        if not reason and not running
        else []
    )
    target = state.get("target") or {}
    previous = state.get("previous") or {}
    result: dict[str, Any] = {
        "root": str(root),
        "updatable": not reason,
        "notUpdatableReason": reason,
        "currentVersion": str(local) if local else "",
        "currentBuild": local.label if local else "",
        "belowMinimum": local is None or local.build < MIN_MOD_AVD_BUILD,
        "minimumBuild": f"mas-{MIN_MOD_AVD_BUILD}",
        "checkedAt": _checked_at.isoformat(timespec="seconds") if _checked_at else None,
        "checkError": _remote_error,
        "latestVersion": str(release.version) if release else "",
        "latestBuild": release.version.label if release else "",
        "latestTitle": release.title if release else "",
        "releaseUrl": release.page_url if release else "",
        "updateAvailable": newer,
        "requiredAutoMas": _automas_block(release) if newer else "",
        "announcement": release.notes.announcement if newer and release else "",
        "changes": newer_changes(release.notes.machine, local)
        if newer and release
        else [],
        "assetName": release.asset.name if release else "",
        "assetSize": release.asset.size if release else 0,
        "phase": state.get("phase", stage.PHASE_IDLE),
        "preparedVersion": target.get("version", "")
        if state.get("phase") == stage.PHASE_STAGED
        else "",
        "runningInstances": len(running),
        "busyProcesses": busy,
        "canRollback": stage.can_rollback(root),
        "previousVersion": previous.get("version", "") if previous else "",
        "awaitingBoot": bool(previous.get("awaitingBoot")) if previous else False,
        "autoInstall": bool(prefs.get("autoInstall")),
        "busy": runtime.busy,
        "progress": asdict(runtime.progress),
        "lastResult": state.get("lastResult") or None,
    }
    return result


async def status(root: str) -> dict[str, Any]:
    """一个根目录的更新现状。不联网，只用缓存的查询结果。"""
    path = await _managed(root)
    runtime = _runtime(path)
    return await asyncio.to_thread(_snapshot_sync, path, runtime)


async def check(root: str, *, force: bool = False) -> dict[str, Any]:
    """查一次更新（``force`` 不走缓存），返回同 :func:`status` 的快照。查不到只记日志、写在快照里。"""
    path = await _managed(root)
    if not _not_updatable_reason(path):
        try:
            await _latest(force=force)
        except Exception as e:  # noqa: BLE001 - 查不到不算接口失败
            logger.warning(f"检查魔改 AVD 更新失败: {e}")
    return await status(str(path))


# ---- 下载与拼新版 ----------------------------------------------------------


async def _reuse_download(root: Path, release: RemoteRelease, final: Path) -> bool:
    """别的根目录已经下好同一个包：硬链接（不同盘就复制）过来，核对后直接用。"""
    asset = release.asset
    for other in await asyncio.to_thread(_managed_roots):
        if root_key(other) == root_key(root):
            continue
        candidate = stage.download_dir(other) / asset.name
        try:
            if os.path.getsize(native_path(candidate)) != asset.size:
                continue
        except OSError:
            continue
        try:
            os.link(native_path(candidate), native_path(final))
        except OSError:
            await asyncio.to_thread(
                shutil.copyfile, native_path(candidate), native_path(final)
            )
        if (
            asset.sha256
            and await asyncio.to_thread(stage.file_sha256, final) != asset.sha256
        ):
            final.unlink(missing_ok=True)
            continue
        logger.info(f"沿用 {other} 已下载的 {asset.name}")
        return True
    return False


async def _download(runtime: _Runtime, release: RemoteRelease) -> Path:
    root, asset = runtime.root, release.asset
    folder = stage.download_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    final = folder / asset.name
    part = folder / f"{asset.name}.part"
    # 别的版本留下的包不再要了
    for child in folder.iterdir():
        if child.name in (final.name, part.name):
            continue
        if child.is_dir():
            stage.remove_tree(child)
        else:
            child.unlink(missing_ok=True)
    if final.is_file():
        if final.stat().st_size == asset.size and (
            not asset.sha256
            or await asyncio.to_thread(stage.file_sha256, final) == asset.sha256
        ):
            return final
        final.unlink()
    if await _reuse_download(root, release, final):
        return final

    from app.core import Config

    received = max(part.stat().st_size, 0) if part.is_file() else 0
    window_bytes, window_start = 0, time.monotonic()
    speed: float | None = None

    async def on_bytes(count: int) -> None:
        nonlocal received, window_bytes, window_start, speed
        if runtime.cancel_requested:
            raise stage.UpdateCancelled("已取消下载")
        received = max(received + count, 0)
        window_bytes += max(count, 0)
        elapsed = time.monotonic() - window_start
        if elapsed >= 1:
            speed, window_bytes, window_start = (
                window_bytes / elapsed,
                0,
                time.monotonic(),
            )
        _set(
            runtime,
            "downloading",
            message=f"正在下载 {asset.name}",
            percent=round(received * 100 / asset.size, 1),
            downloadedBytes=received,
            totalBytes=asset.size,
            speedBytesPerSec=speed,
        )
        await _publish(runtime, force=False)

    logger.info(f"开始下载 {asset.url}（{asset.size} 字节，已有 {received} 字节）")
    digest: Any = None
    async with httpx.AsyncClient(
        proxy=Config.proxy,
        follow_redirects=True,
        timeout=_DOWNLOAD_TIMEOUT,
        headers={"User-Agent": "AutoMasGui"},
    ) as client:
        for attempt in range(1, _DOWNLOAD_ATTEMPTS + 1):
            digest = hashlib.sha256() if asset.sha256 else None
            try:
                size = await download_resumable(
                    client,
                    asset.url,
                    part,
                    expected_size=asset.size,
                    on_bytes=on_bytes,
                    digest=digest,
                )
            except (httpx.HTTPError, OSError, ValueError) as e:
                if attempt == _DOWNLOAD_ATTEMPTS:
                    raise RuntimeError(
                        f"下载 {asset.name} 失败: {type(e).__name__}: {e}"
                    ) from e
                logger.warning(f"下载 {asset.name} 出错，{attempt} 秒后续传: {e}")
                await asyncio.sleep(attempt)
                continue
            break
    if size != asset.size:
        raise RuntimeError(
            f"下载的 {asset.name} 大小不对（{size} / {asset.size} 字节）"
        )
    if asset.sha256 and digest is not None and digest.hexdigest() != asset.sha256:
        part.unlink(missing_ok=True)
        raise stage.PackageError(
            f"下载的 {asset.name} 和发布记录的 SHA-256 对不上，已删除，没有安装。请重试"
        )
    if not asset.sha256:
        logger.warning(
            f"{asset.name} 的发布记录里没有 SHA-256，只靠 zip 自带的 CRC 核对"
        )
    os.replace(part, final)
    logger.info(f"{asset.name} 下载完成，SHA-256 核对通过")
    return final


def _stage_sync(
    runtime: _Runtime,
    archive: Path,
    target: dict[str, Any],
    extracting: stage.Progress,
    verifying: stage.Progress,
) -> dict[str, Any]:
    """解包 → 按清单核对 → ``sdk\\emulator`` 改名进 ``stage``。核对不通过丢掉暂存、报错。"""
    root = runtime.root
    version = parse_version(target["version"])
    assert version is not None
    files = stage.extract_package(
        archive,
        stage.pkg_dir(root),
        top_dir=target["asset"]["topDir"],
        progress=extracting,
        cancelled=_cancelled(runtime),
    )
    manifest = read_manifest_file(stage.pkg_dir(root) / MODAVD_MANIFEST_FILE)
    if manifest is not None:
        stage.check_package_manifest(manifest, version)
        problems = stage.verify_tree(
            stage.pkg_dir(root),
            manifest,
            progress=verifying,
            cancelled=_cancelled(runtime),
        )
        if problems:
            stage.remove_tree(stage.pkg_dir(root))
            shown = "；".join(problems[:5])
            more = f" 等 {len(problems)} 项" if len(problems) > 5 else ""
            raise stage.PackageError(f"包里的文件和清单对不上：{shown}{more}")
    stage.build_stage(root, version)
    return {
        "verified": "manifest" if manifest is not None else "zip",
        "files": files,
        "mode": "full",
        "version": target["version"],
    }


async def _prepare(runtime: _Runtime, release: RemoteRelease) -> None:
    """下载并拼好 ``release``，结束时 ``state`` 停在 ``staged``。"""
    root = runtime.root
    state = await asyncio.to_thread(stage.read_state, root)
    target = release.as_dict()
    if (
        state.get("phase") == stage.PHASE_STAGED
        and (state.get("target") or {}).get("version") == target["version"]
        and stage.stage_emulator_dir(root).is_dir()
    ):
        return
    if state.get("phase") in (stage.PHASE_SWAPPING, stage.PHASE_ROLLING_BACK):
        raise RuntimeError("上一次换上 / 回退还没收尾，请重启 MAS 后再试")
    free = (await asyncio.to_thread(shutil.disk_usage, root)).free
    if free < UPDATE_MIN_FREE_BYTES:
        raise RuntimeError(
            f"{root.anchor or root} 剩余空间 {free / 1024**3:.1f} GB，更新要临时占用约 "
            f"{UPDATE_MIN_FREE_BYTES / 1024**3:.1f} GB，请先清理"
        )
    _set(
        runtime,
        "downloading",
        message=f"正在下载 {release.asset.name}",
        totalBytes=release.asset.size,
    )
    await _publish(runtime)
    archive = await _download(runtime, release)
    previous = state.get("previous")
    await asyncio.to_thread(
        stage.write_state,
        root,
        {"phase": stage.PHASE_DOWNLOADED, "target": target, "previous": previous},
    )
    _set(runtime, "extracting", message="正在解包")
    await _publish(runtime)
    staged = await asyncio.to_thread(
        _stage_sync,
        runtime,
        archive,
        target,
        _thread_progress(runtime, "extracting", "正在解包"),
        _thread_progress(runtime, "verifying", "正在按清单核对每个文件"),
    )
    await asyncio.to_thread(
        stage.write_state,
        root,
        {
            "phase": stage.PHASE_STAGED,
            "target": target,
            "staged": staged,
            "previous": previous,
        },
    )
    logger.info(
        f"{root} 的 {release.version} 已拼好（{staged['files']} 个文件，"
        f"{'按清单逐文件核对' if staged['verified'] == 'manifest' else '旧版包没有清单，按包的 SHA-256 与 zip CRC 核对'}）"
    )


async def _prepare_job(
    runtime: _Runtime, release: RemoteRelease, *, auto: bool
) -> None:
    async with runtime.lock:
        runtime.cancel_requested = False
        try:
            await _prepare(runtime, release)
        except stage.UpdateCancelled:
            _set(runtime, "cancelled", "idle", "已取消，下次接着下")
            await _publish(runtime)
            return
        except Exception as e:  # noqa: BLE001 - 失败如实交给界面
            logger.opt(exception=True).warning(
                f"准备魔改 AVD {release.version} 失败: {e}"
            )
            _set(runtime, "failed", "failed", f"准备 {release.version} 失败：{e}")
            await _publish(runtime)
            return
        _set(
            runtime,
            "staged",
            "success",
            f"{release.version}（{release.version.label}）已下载并核对，可以安装",
        )
        await _publish(runtime)
    if auto:
        # 另起一个任务：这个下载任务返回之后才算结束，在它里面接着装会被「正在下载」挡住
        _spawn(_auto_install(runtime.root, "下载完成"), "avd-update-auto-install")


def _ensure_updatable(root: Path) -> None:
    reason = _not_updatable_reason(root)
    if reason:
        raise ValueError(reason)


async def start_download(root: str) -> dict[str, Any]:
    """后台下载并拼好最新一版。立刻返回，进度看 WebSocket / 状态快照。"""
    path = await _managed(root)
    _ensure_updatable(path)
    runtime = _runtime(path)
    if runtime.busy:
        return {"ok": False, "message": "正在下载或安装，请稍候"}
    release = await _latest(force=False)
    local = await asyncio.to_thread(local_version, path)
    if not _newer(release, local):
        return {"ok": False, "message": f"已经是最新版本（{local}）"}
    required = _automas_block(release)
    if required:
        return {
            "ok": False,
            "message": f"{release.version} 需要 AUTO-MAS {required} 或更新的版本，请先更新 AUTO-MAS",
        }
    runtime.job = asyncio.create_task(
        _prepare_job(runtime, release, auto=False), name=f"avd-update-prepare:{path}"
    )
    return {"ok": True, "message": f"开始下载 {release.version}"}


async def cancel(root: str) -> dict[str, Any]:
    """取消下载 / 解包（已下的部分留着，下次接着下）。换上一旦开始不能取消。"""
    path = await _managed(root)
    runtime = _runtime(path)
    if not runtime.busy or runtime.progress.stage not in (
        "downloading",
        "extracting",
        "verifying",
    ):
        return {"ok": False, "message": "现在没有可以取消的下载"}
    runtime.cancel_requested = True
    return {"ok": True, "message": "正在取消"}


# ---- 换上与回退 ------------------------------------------------------------


async def _close_instances(root: Path) -> None:
    """只走现有的 ``close``（安卓正常关机，不行再 sync + kill），不硬杀。"""
    from .manager import AvdManager
    from .service import close_instances

    manager = AvdManager(manager_key_exe(root), 60, False)
    running = await asyncio.to_thread(_running_instances, root)
    targets = [
        (f"{root}#{idx}", lambda m=manager, i=idx: m.close(i)) for idx in running
    ]
    if targets:
        logger.info(f"更新前正常关闭 {root} 的 {len(targets)} 台魔改 AVD 实例")
        await close_instances(targets, timeout=POWER_CLOSE_TIMEOUT_SECONDS * 2)


async def _swap_job(runtime: _Runtime, *, action: str, close: bool) -> None:
    root = runtime.root
    verb = "安装" if action == "install" else "回退"
    async with runtime.lock:
        try:
            if close:
                _set(runtime, "closing", message="正在关闭实例（安卓正常关机）")
                await _publish(runtime)
                await _close_instances(root)
            _set(
                runtime,
                "installing" if action == "install" else "rolling_back",
                message=f"正在{verb}",
            )
            await _publish(runtime)
            _swapping.add(root_key(root))
            try:
                version = await asyncio.to_thread(
                    stage.swap_in if action == "install" else stage.rollback, root
                )
            finally:
                _swapping.discard(root_key(root))
            if action == "install":
                message = (
                    f"已换上 {version}。新版第一次开机成功后删除旧版；开不了机可以回退"
                )
            else:
                message = f"已回退到 {version or '上一版'}"
            _set(
                runtime,
                "installed" if action == "install" else "rolled_back",
                "success",
                message,
            )
        except Exception as e:  # noqa: BLE001 - 失败如实交给界面
            logger.opt(exception=True).warning(f"{root} {verb}魔改 AVD 失败: {e}")
            _set(runtime, "failed", "failed", f"{verb}失败：{e}")
        await _publish(runtime)


async def _start_swap(
    root: str, *, action: str, close_instances: bool
) -> dict[str, Any]:
    path = await _managed(root)
    _ensure_updatable(path)
    runtime = _runtime(path)
    if runtime.busy:
        return {
            "ok": False,
            "reason": "busy",
            "message": "正在下载或安装，请稍候",
            "runningInstances": 0,
        }
    state = await asyncio.to_thread(stage.read_state, path)
    if action == "install" and state.get("phase") != stage.PHASE_STAGED:
        return {
            "ok": False,
            "reason": "not_prepared",
            "message": "还没有下载好的新版，请先下载",
            "runningInstances": 0,
        }
    if action == "rollback" and not await asyncio.to_thread(stage.can_rollback, path):
        return {
            "ok": False,
            "reason": "no_previous",
            "message": "没有可以回退的旧版",
            "runningInstances": 0,
        }
    running = await asyncio.to_thread(_running_instances, path)
    if running and not close_instances:
        return {
            "ok": False,
            "reason": "instances_running",
            "message": f"需要先关闭 {len(running)} 台实例",
            "runningInstances": len(running),
        }
    if running and _tasks_running():
        return {
            "ok": False,
            "reason": "tasks_running",
            "message": "有任务正在运行，要关实例的话请等任务结束后再装",
            "runningInstances": len(running),
        }
    runtime.job = asyncio.create_task(
        _swap_job(runtime, action=action, close=bool(running)),
        name=f"avd-update-{action}:{path}",
    )
    return {
        "ok": True,
        "reason": "started",
        "message": "已开始",
        "runningInstances": len(running),
    }


async def install(root: str, *, close_instances: bool = False) -> dict[str, Any]:
    """换上已拼好的新版。有实例开着且 ``close_instances`` 为假时不动手，返回要关几台。"""
    return await _start_swap(root, action="install", close_instances=close_instances)


async def rollback(root: str, *, close_instances: bool = False) -> dict[str, Any]:
    """回到上一版（反过来改名两次）。规则同 :func:`install`。"""
    return await _start_swap(root, action="rollback", close_instances=close_instances)


async def set_options(root: str, *, auto_install: bool) -> dict[str, Any]:
    """「空闲时自动装」：任务都结束、实例全关时才装（任务跑完后或 MAS 启动时），不在定时任务开始前装。"""
    path = await _managed(root)
    prefs = await asyncio.to_thread(stage.read_prefs, path)
    prefs["autoInstall"] = bool(auto_install)
    await asyncio.to_thread(stage.write_prefs, path, prefs)
    return await status(str(path))


# ---- 自动安装、启动、开机确认 ----------------------------------------------


async def _auto_install(root: Path, reason: str) -> None:
    """开着「空闲时自动装」的根目录：没下就先下，下好了且任务都结束、实例全关才换上。"""
    prefs = await asyncio.to_thread(stage.read_prefs, root)
    if not prefs.get("autoInstall") or _not_updatable_reason(root):
        return
    runtime = _runtime(root)
    if runtime.busy or _tasks_running():
        return
    state = await asyncio.to_thread(stage.read_state, root)
    if state.get("phase") != stage.PHASE_STAGED:
        local = await asyncio.to_thread(local_version, root)
        if _newer(_remote, local) and not _automas_block(_remote):
            assert _remote is not None
            logger.info(
                f"{root} 开着空闲时自动装，开始下载 {_remote.version}（{reason}）"
            )
            runtime.job = asyncio.create_task(
                _prepare_job(runtime, _remote, auto=True),
                name=f"avd-update-auto:{root}",
            )
        return
    if await asyncio.to_thread(_running_instances, root) or await asyncio.to_thread(
        stage.processes_using, root
    ):
        logger.info(f"{root} 有实例或程序在用模拟器，先不自动安装（{reason}）")
        return
    logger.info(
        f"{root} 空闲，自动安装 {(state.get('target') or {}).get('version')}（{reason}）"
    )
    runtime.job = asyncio.create_task(
        _swap_job(runtime, action="install", close=False),
        name=f"avd-update-auto-install:{root}",
    )


def on_tasks_idle() -> None:
    """所有任务都结束时由调度器调：给开着「空闲时自动装」的根目录装上准备好的新版。"""

    async def run() -> None:
        for root in await asyncio.to_thread(_managed_roots):
            try:
                await _auto_install(root, "任务都已结束")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"{root} 自动安装检查失败: {e}")

    _spawn(run(), "avd-update-idle")


async def _startup_check(roots: list[Path]) -> None:
    targets = [root for root in roots if not _not_updatable_reason(root)]
    if not targets:
        return
    try:
        release = await _latest(force=False)
    except Exception as e:  # noqa: BLE001 - 启动时查不到只记日志，不弹窗、不挡启动
        logger.warning(f"启动时检查魔改 AVD 更新失败: {e}")
        return
    for root in targets:
        local = await asyncio.to_thread(local_version, root)
        if _newer(release, local):
            logger.info(
                f"{root} 的魔改 AVD 有新版本：{local or '未知'} → {release.version}"
            )
        try:
            await _auto_install(root, "MAS 启动")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"{root} 自动安装检查失败: {e}")


async def startup() -> None:
    """MAS 启动时：先收拾上次没做完的换上 / 回退（要在定时器拉起实例之前），再在后台查更新。"""
    roots = await asyncio.to_thread(_managed_roots)
    for root in roots:
        try:
            done = await asyncio.to_thread(stage.recover, root)
        except Exception as e:  # noqa: BLE001 - 一个根目录恢复失败不影响别的
            logger.opt(exception=True).error(f"{root} 的魔改 AVD 更新恢复失败: {e}")
            continue
        if done:
            logger.warning(f"{root} 的魔改 AVD 更新：{done}")
    _spawn(_startup_check(roots), "avd-update-startup-check")


def note_boot_completed(root: str | Path) -> None:
    """实例冷启动到 ``sys.boot_completed`` 时调：新版第一次开机成功就删掉旧版。"""
    previous = stage.read_state(root).get("previous")
    if isinstance(previous, dict) and previous.get("awaitingBoot"):
        _spawn(
            asyncio.to_thread(stage.confirm_boot, Path(root)), "avd-update-confirm-boot"
        )


__all__ = [
    "cancel",
    "check",
    "install",
    "note_boot_completed",
    "on_tasks_idle",
    "rollback",
    "set_options",
    "start_download",
    "startup",
    "status",
    "swap_in_progress",
]
