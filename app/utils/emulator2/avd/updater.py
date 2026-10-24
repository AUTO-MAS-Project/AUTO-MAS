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

"""魔改 AVD 更新器：查更新，「更新」一键下载、拼新版、核对、换上，启动恢复。

流程（每个根目录各走各的）：

1. **查更新**：问 :func:`.update_source.update_sources` 里的源（现在只有 GitHub），结果缓存 4 小时；
   MAS 启动时在后台查一次，界面打开更新区时按缓存再查。失败只记日志、写在状态里，不弹窗、不挡启动。
2. **更新**（:func:`update`）：用户点一下，依次
   - 再查一次最新版本（不走缓存）；
   - 下载整包到 ``<根>\\.update\\download``（同盘、续传、可取消），按发布记录的 SHA-256 核对；
   - 解到 ``pkg``、按清单逐文件核对（旧版包没有清单，靠包的 SHA-256 + zip CRC），``sdk\\emulator``
     改名进 ``stage``（:mod:`.update_stage`）；
   - 换上。本根目录有实例开着时先返回要关几台，用户确认后才只走现有的 ``close``（安卓正常关机，
     不行再 sync + kill）关掉，不硬杀。有实例在开机、有任务在跑、还有程序开着模拟器文件时不换，
     停在「已下载好」，下次再点直接换上，不重新下载。
3. **启动恢复**：MAS 启动时（主定时器之前）按 ``state.json`` 补完或退回上次没做完的换上。

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
from pathlib import Path
from typing import Any

import httpx

from app.services.update_transport import download_resumable
from app.utils import get_logger
from app.utils.update_files import native_path

from . import update_stage as stage
from .components import (
    MetadataUnreadable,
    local_sdk_root,
    manager_key_exe,
    read_metadata_strict,
    root_key,
)
from .constants import (
    MIN_MOD_AVD_BUILD,
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
    parse_version,
    update_sources,
)

logger = get_logger("魔改 AVD 更新")

#: 查更新失败后多久之内不再自动重试（用户点「更新」不受限）。
_CHECK_FAILURE_BACKOFF_SECONDS = 600.0
#: 下载失败自动重试的次数（续传接着下）。
_DOWNLOAD_ATTEMPTS = 3
_DOWNLOAD_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
#: 进度消息最密多久发一条。
_PUBLISH_INTERVAL_SECONDS = 0.5
#: 还能取消的阶段（换上一旦开始就不能取消）。
_CANCELLABLE_STAGES = ("downloading", "extracting", "verifying")


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
    """一个根目录在本进程里的更新状态：同一时刻只跑一次更新。"""

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
#: 正在换上的根目录：这段时间不许开机。
_swapping: set[str] = set()
#: 后台小任务（启动时查更新）的引用，免得被回收。
_background: set[asyncio.Task[Any]] = set()

_remote: RemoteRelease | None = None
_remote_at = 0.0
_remote_failed_at = 0.0
_remote_error = ""
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
    try:
        # mas-avd.json 读不出时看不到 sdkRoot，换上最后还要改它：先修好再更新
        read_metadata_strict(root)
    except MetadataUnreadable as e:
        return f"{e}，先修好或删掉它再更新"
    if local_sdk_root(root) is not None:
        return "这个根目录在 mas-avd.json 里设了 sdkRoot（开发用的本地 SDK），不更新"
    if not os.path.isfile(native_path(stage.emulator_dir(root) / "emulator.exe")):
        return "这个根目录里没有 sdk\\emulator，请先放好魔改 AVD"
    return ""


def _ensure_updatable(root: Path) -> None:
    reason = _not_updatable_reason(root)
    if reason:
        raise ValueError(reason)


def _tasks_running() -> bool:
    from app.core import TaskManager

    return bool(TaskManager.task_handler)


def _opening_instances(root: Path) -> list[str]:
    """这个根目录下正在开机（``open`` 还没做完，含开机前检查到拉起 emulator.exe 之间那几秒）的实例。"""
    from .manager import _OPENING

    prefix = f"{root_key(root)}|"
    return sorted(
        key[len(prefix) :] for key in list(_OPENING) if key.startswith(prefix)
    )


def _swap_blocker(root: Path) -> str:
    """现在不能换上的原因；能换返回空串。

    有实例在开机就不换：开机前检查到拉起 emulator.exe 之间有几秒，进程表里还看不到它。有任何 MAS
    任务在跑也不换（任务随时可能去开实例）。
    """
    opening = _opening_instances(root)
    if opening:
        return f"实例 {'、'.join(opening)} 正在开机，等它开完再更新"
    if _tasks_running():
        return "有任务正在运行，请等任务都结束后再更新"
    return ""


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
    """正在换上：这段时间 ``sdk\\emulator`` 可能不在，开机前检查据此拒绝开机。"""
    return root_key(root) in _swapping


# ---- 查更新 ----------------------------------------------------------------


async def _latest(*, force: bool) -> RemoteRelease:
    """最新一版。4 小时内查过就用缓存；查失败后 10 分钟内不自动重试（``force`` 例外）。"""
    global _remote, _remote_at, _remote_failed_at, _remote_error
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
            logger.info(
                f"ModAVD 最新版本 {release.version}（{release.version.label}，"
                f"tag {release.tag}，来源 {release.source}，包 {release.asset.name}）"
            )
            return release
        _remote_failed_at, _remote_error = time.monotonic(), "；".join(errors)
        raise UpdateSourceError(_remote_error)


def _newer(release: RemoteRelease | None, local: ModAvdVersion | None) -> bool:
    return release is not None and (local is None or release.version > local)


def _automas_block(release: RemoteRelease | None) -> str:
    """这一版要求的 MAS 版本比当前高时，返回那个版本号。"""
    if release is None:
        return ""
    from app.core import Config

    return (
        release.min_automas
        if automas_too_old(release.min_automas, Config.VERSION)
        else ""
    )


def _staged_version(root: Path) -> str:
    """已经下好、核对过、比装着的新、等着换上的版本；没有返回空串。"""
    state = stage.read_state(root)
    version = parse_version((state.get("target") or {}).get("version"))
    if (
        state.get("phase") != stage.PHASE_STAGED
        or version is None
        or not stage.stage_emulator_dir(root).is_dir()
    ):
        return ""
    local = local_version(root)
    return str(version) if local is None or version > local else ""


# ---- 状态快照 --------------------------------------------------------------


def _snapshot_sync(root: Path, runtime: _Runtime) -> dict[str, Any]:
    local = local_version(root)
    reason = _not_updatable_reason(root)
    state = stage.read_state(root)
    release = _remote
    newer = not reason and _newer(release, local)
    return {
        "root": str(root),
        "updatable": not reason,
        "notUpdatableReason": reason,
        "currentVersion": str(local) if local else "",
        "currentBuild": local.label if local else "",
        "belowMinimum": local is None or local.build < MIN_MOD_AVD_BUILD,
        "minimumBuild": f"mas-{MIN_MOD_AVD_BUILD}",
        "checkError": _remote_error,
        "latestVersion": str(release.version) if release else "",
        "latestBuild": release.version.label if release else "",
        "updateAvailable": newer,
        "requiredAutoMas": _automas_block(release) if newer else "",
        "assetSize": release.asset.size if release else 0,
        "phase": state.get("phase", stage.PHASE_IDLE),
        "preparedVersion": _staged_version(root) if not reason else "",
        "runningInstances": len(_running_instances(root)) if not reason else 0,
        "busy": runtime.busy,
        "progress": asdict(runtime.progress),
        "lastResult": state.get("lastResult") or None,
    }


async def status(root: str, *, check: bool = False) -> dict[str, Any]:
    """一个根目录的更新现状。``check`` 为真时先查一次更新（走 4 小时缓存；查不到只记日志、写在
    ``checkError``，不算接口失败）。"""
    path = await _managed(root)
    if check and not _not_updatable_reason(path):
        try:
            await _latest(force=False)
        except Exception as e:  # noqa: BLE001 - 查不到不算接口失败
            logger.warning(f"检查魔改 AVD 更新失败: {e}")
    return await asyncio.to_thread(_snapshot_sync, path, _runtime(path))


# ---- 下载与拼新版 ----------------------------------------------------------


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
    """解包 → 核对（新写法版本必须有清单、逐文件比；模拟器的构建号与自编版标志）→ ``sdk\\emulator``
    改名进 ``stage``。不写状态，由调用方核对通过后写。"""
    root = runtime.root
    files = stage.extract_package(
        archive,
        stage.pkg_dir(root),
        top_dir=target["asset"]["topDir"],
        progress=extracting,
        cancelled=_cancelled(runtime),
    )
    version = parse_version(target["version"])
    assert version is not None
    verified = stage.verify_package(
        stage.pkg_dir(root),
        version,
        tag=target["tag"],
        progress=verifying,
        cancelled=_cancelled(runtime),
    )
    stage.build_stage(root, version)
    return {"verified": verified, "files": files}


class _NothingToDo(Exception):
    """拿到锁以后发现前提已经不成立（已经是最新、没有要装的）。"""


async def _prepare(runtime: _Runtime, release: RemoteRelease) -> None:
    """下载并拼好 ``release``，结束时 ``state`` 停在 ``staged``。调用方拿着这个根目录的锁。

    动 ``pkg`` / ``stage`` 之前先把状态改成「正在准备」，核对通过、``stage`` 拼好后才写 ``staged``；
    中途取消、失败都丢掉暂存、回到空闲（下载的包留着，下次接着下）。
    """
    root = runtime.root
    state = await asyncio.to_thread(stage.read_state, root)
    target = release.as_dict()
    if state.get("phase") == stage.PHASE_SWAPPING:
        raise RuntimeError("上一次换上还没收尾，请重启 MAS 后再试")
    # 上次没删完的先删（trash 里都是已经不要的），再看剩余空间
    await asyncio.to_thread(stage.purge_trash, root)
    free = (await asyncio.to_thread(shutil.disk_usage, root)).free
    if free < UPDATE_MIN_FREE_BYTES:
        left = await asyncio.to_thread(stage.trash_bytes, root)
        left_text = (
            f"{left / 1024**3:.2f} GB"
            if left >= 1024**3
            else f"{left / 1024**2:.1f} MB"
        )
        hint = (
            f"。另外 {stage.update_dir(root) / 'trash'} 里还占着 {left_text}，"
            "是之前要删、但文件被占用没删掉的，关掉占用它的程序（或重启电脑）后 MAS 会再删"
            if left
            else ""
        )
        raise RuntimeError(
            f"{root.anchor or root} 剩余空间 {free / 1024**3:.1f} GB，更新要临时占用约 "
            f"{UPDATE_MIN_FREE_BYTES / 1024**3:.1f} GB，请先清理{hint}"
        )
    await asyncio.to_thread(stage.begin_staging, root, target)
    try:
        _set(
            runtime,
            "downloading",
            message=f"正在下载 {release.asset.name}",
            totalBytes=release.asset.size,
        )
        await _publish(runtime)
        archive = await _download(runtime, release)
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
        staged = await asyncio.to_thread(stage.finish_staging, root, target, staged)
    except BaseException as e:
        reason = (
            "已取消"
            if isinstance(e, (stage.UpdateCancelled, asyncio.CancelledError))
            else str(e)
        )
        await asyncio.shield(asyncio.to_thread(stage.abort_staging, root, reason))
        raise
    checked = (
        "按清单逐文件核对"
        if staged["verified"] == "manifest"
        else "旧版包没有清单，按 zip CRC 并核对了整包的 SHA-256"
    )
    logger.info(
        f"{root} 的 {release.version} 已拼好（{staged['files']} 个文件，{checked}）"
    )


# ---- 换上 ------------------------------------------------------------------


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


async def _swap(runtime: _Runtime, *, close: bool) -> str:
    """换上拼好的新版，返回版本号。现在不能换就抛 :class:`~.update_stage.SwapBlocked`，暂存原样留着。"""
    root = runtime.root
    key = root_key(root)
    # 判断和登记「正在换上」之间没有 await，和开机（open 先登记自己、_launch 再看「正在换上」）互斥，
    # 先占先得
    blocker = _swap_blocker(root)
    if blocker:
        raise stage.SwapBlocked(blocker)
    _swapping.add(key)
    try:
        running = await asyncio.to_thread(_running_instances, root)
        if running and not close:
            raise stage.SwapBlocked(f"有 {len(running)} 台实例开着")
        if running:
            _set(runtime, "closing", message="正在关闭实例（安卓正常关机）")
            await _publish(runtime)
            await _close_instances(root)
        _set(runtime, "installing", message="正在换上新版")
        await _publish(runtime)
        return await asyncio.to_thread(stage.swap_in, root)
    finally:
        _swapping.discard(key)


async def _update_job(
    runtime: _Runtime, release: RemoteRelease | None, *, close: bool
) -> None:
    root = runtime.root
    async with runtime.lock:
        runtime.cancel_requested = False
        version = ""
        try:
            # 拿到锁之后重新判断：排队期间可能已经装上了别的版本、拼好了别的版本
            local = await asyncio.to_thread(local_version, root)
            version = await asyncio.to_thread(_staged_version, root)
            if (
                release is not None
                and _newer(release, local)
                and version != str(release.version)
            ):
                await _prepare(runtime, release)
                version = await asyncio.to_thread(_staged_version, root)
            if not version:
                raise _NothingToDo(f"已经是最新版本（{local}）")
            installed = await _swap(runtime, close=close)
            _set(runtime, "installed", "success", f"已更新到 {installed}")
        except _NothingToDo as e:
            _set(runtime, "idle", "idle", str(e))
        except stage.UpdateCancelled:
            _set(runtime, "cancelled", "idle", "已取消，下次点「更新」接着下")
        except stage.SwapBlocked as e:
            logger.info(f"{root} 的 {version} 已下载好，这次没换上: {e}")
            _set(
                runtime,
                "staged",
                "failed",
                f"{version} 已下载并核对好，但现在不能换上：{e}。处理好后再点「更新」直接换上，"
                "不用重新下载",
            )
        except Exception as e:  # noqa: BLE001 - 失败如实交给界面
            logger.opt(exception=True).warning(f"{root} 更新魔改 AVD 失败: {e}")
            _set(runtime, "failed", "failed", f"更新失败：{e}")
        await _publish(runtime)


def _action(
    reason: str, message: str, *, ok: bool = False, running: int = 0
) -> dict[str, Any]:
    return {
        "ok": ok,
        "reason": reason,
        "message": message,
        "runningInstances": running,
    }


async def update(root: str, *, close_instances: bool = False) -> dict[str, Any]:
    """「更新」：查最新版、下载整包、拼新版、按清单核对，然后换上。立刻返回，进度看 WebSocket / 状态快照。

    本根目录有实例开着且 ``close_instances`` 为假时不动手，返回要关几台；为真时换上前只走现有的
    ``close`` 关掉它们。已经下好、核对过的新版不重新下载；查不到最新版本时也照样换上它。
    """
    path = await _managed(root)
    _ensure_updatable(path)
    runtime = _runtime(path)
    if runtime.busy:
        return _action("busy", "正在更新，请稍候")
    release: RemoteRelease | None = None
    check_error = ""
    try:
        release = await _latest(force=True)
    except Exception as e:  # noqa: BLE001 - 查不到时看有没有已经下好的
        logger.warning(f"检查魔改 AVD 更新失败: {e}")
        check_error = str(e)
    local = await asyncio.to_thread(local_version, path)
    staged = await asyncio.to_thread(_staged_version, path)
    if _newer(release, local):
        required = _automas_block(release)
        if required:
            assert release is not None
            return _action(
                "automas_too_old",
                f"{release.version} 需要 AUTO-MAS {required} 或更新的版本，请先更新 AUTO-MAS",
            )
    elif not staged:
        if release is None:
            return _action("check_failed", f"查不到最新版本：{check_error}")
        return _action("up_to_date", f"已经是最新版本（{local}）")
    else:
        release = None  # 只换上已经下好的那一版
    running = await asyncio.to_thread(_running_instances, path)
    if running and not close_instances:
        return _action(
            "instances_running",
            f"需要先关闭 {len(running)} 台实例",
            running=len(running),
        )
    # 上面有 await：并发的请求可能已经起了任务，起任务前再看一次（这里到 create_task 之间没有 await）
    if runtime.busy:
        return _action("busy", "正在更新，请稍候")
    runtime.job = asyncio.create_task(
        _update_job(runtime, release, close=close_instances),
        name=f"avd-update:{path}",
    )
    return _action("started", "已开始", ok=True, running=len(running))


async def cancel(root: str) -> dict[str, Any]:
    """取消下载 / 解包 / 核对（已下的部分留着，下次接着下）。换上一旦开始不能取消。"""
    runtime = _runtimes.get(root_key(str(root or "").strip()))
    if (
        runtime is None
        or not runtime.busy
        or runtime.progress.stage not in _CANCELLABLE_STAGES
    ):
        return _action("not_cancellable", "现在没有可以取消的下载")
    runtime.cancel_requested = True
    return _action("cancelling", "正在取消", ok=True)


# ---- 启动 ------------------------------------------------------------------


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


async def startup() -> None:
    """MAS 启动时：先收拾上次没做完的换上（要在定时器拉起实例之前），再在后台查更新。"""
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


__all__ = [
    "cancel",
    "startup",
    "status",
    "swap_in_progress",
    "update",
]
