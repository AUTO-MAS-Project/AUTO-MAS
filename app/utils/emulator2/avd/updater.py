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
2. **下载**：GitHub 源先按区间只取变了的文件（:mod:`.update_range`，没变的从本地复制）；变化太多或
   任何一步不行就下整包到 ``<根>\\.update\\download``（同盘、续传），按发布记录的 SHA-256 核对。
   实例开着也能下。
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
import json
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
from app.utils.update_files import native_path, replace_file, resolve_within

from . import first_install, update_range
from . import update_stage as stage
from .components import (
    MetadataUnreadable,
    emulator_self_built,
    local_sdk_root,
    manager_key_exe,
    read_metadata_strict,
    root_key,
)
from .constants import (
    MIN_MOD_AVD_BUILD,
    MODAVD_FORCE_FULL_PACKAGE_ENV,
    POWER_CLOSE_TIMEOUT_SECONDS,
    UPDATE_CHECK_CACHE_SECONDS,
    UPDATE_DIR,
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


def _swap_blocker(root: Path, *, manual: bool) -> str:
    """现在不能换上 / 回退的原因；能换返回空串。

    有实例在开机就不换：开机前检查到拉起 emulator.exe 之间有几秒，进程表里还看不到它。手动安装时
    只要有任何 MAS 任务在跑也不换（任务随时可能去开实例）；自动安装本来就只在空闲时装。
    """
    opening = _opening_instances(root)
    if opening:
        return f"实例 {'、'.join(opening)} 正在开机，等它开完、关掉后再装"
    if manual and _tasks_running():
        return "有任务正在运行，请等任务都结束后再装"
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
        [stage.describe_processes([item]) for item in stage.processes_using(root)]
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
    files = stage.extract_package(
        archive,
        stage.pkg_dir(runtime.root),
        top_dir=target["asset"]["topDir"],
        progress=extracting,
        cancelled=_cancelled(runtime),
    )
    return _verify_and_stage(runtime, target, verifying, files=files, mode="full")


def _verify_and_stage(
    runtime: _Runtime,
    target: dict[str, Any],
    verifying: stage.Progress,
    *,
    files: int,
    mode: str,
) -> dict[str, Any]:
    """``pkg`` 已经拼好（整包解出来或按区间拼出来）：核对（新写法版本必须有清单、逐文件比；模拟器的
    构建号与自编版标志），再把 ``sdk\\emulator`` 改名进 ``stage``。不写状态，由调用方核对通过后写。"""
    root = runtime.root
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
    return {"verified": verified, "files": files, "mode": mode}


def _range_allowed(root: Path, release: RemoteRelease) -> bool:
    """GitHub 源才按区间取；已经有下好的整包（或下了一半、别的根目录下好了）就直接用它。"""
    if (
        release.source != "github"
        or os.environ.get(MODAVD_FORCE_FULL_PACKAGE_ENV, "").strip()
    ):
        return False
    asset = release.asset
    folder = stage.download_dir(root)
    if (folder / asset.name).is_file() or (folder / f"{asset.name}.part").is_file():
        return False
    return not any(
        (stage.download_dir(other) / asset.name).is_file()
        for other in _managed_roots()
        if root_key(other) != root_key(root)
    )


async def _prepare_by_range(
    runtime: _Runtime, release: RemoteRelease, target: dict[str, Any]
) -> dict[str, Any] | None:
    """按区间只取变了的文件拼出新版。不能这么做（变化太多、服务器不配合、核对不过……）时丢掉这一批、
    返回 ``None``，调用方改下整包；用户取消照常往外抛。

    这条路用不上发布记录里整包的 SHA-256（asset digest）：整包没有下全，算不出它的摘要。核对靠包里的
    清单：新写法版本（``vX.Y.Z``）必须带清单，拼好后逐文件比大小和 SHA-256（:func:`_verify_and_stage`），
    和整包下载一样严；只有没有清单的旧 tag（``v37.2.10-masN``）这时只剩每个条目的 zip CRC32（取回的
    条目解压时核对、本地复制的按 CRC 比过），比整包下载少一道整包摘要。
    """
    from app.core import Config

    root = runtime.root
    try:
        async with httpx.AsyncClient(
            proxy=Config.proxy,
            follow_redirects=True,
            timeout=_DOWNLOAD_TIMEOUT,
            headers={"User-Agent": "AutoMasGui"},
        ) as client:
            plan = await update_range.plan_range(client, release.asset, root)
            message = (
                f"按区间下载变了的 {len(plan.fetch)} 个文件"
                f"（约 {plan.fetch_bytes / 1024**2:.1f} MiB，整包 {release.asset.size / 1024**2:.1f} MiB）"
            )
            logger.info(f"{root} 更新到 {release.version}：{message}")

            async def on_bytes(done: int, total: int) -> None:
                _set(
                    runtime,
                    "downloading",
                    message=message,
                    # 计划里每个条目按文件头余量估的长度，实际取回的会略多一点
                    percent=min(round(done * 100 / total, 1), 100.0) if total else None,
                    downloadedBytes=min(done, total),
                    totalBytes=total,
                )
                await _publish(runtime, force=False)

            await on_bytes(0, plan.fetch_bytes)
            await update_range.assemble_by_range(
                client,
                plan,
                root,
                stage.pkg_dir(root),
                on_bytes=on_bytes,
                cancelled=_cancelled(runtime),
            )
        files = len(plan.fetch) + len(plan.copy)
        _set(runtime, "verifying", message="正在按清单核对每个文件")
        await _publish(runtime)
        return await asyncio.to_thread(
            _verify_and_stage,
            runtime,
            target,
            _thread_progress(runtime, "verifying", "正在按清单核对每个文件"),
            files=files,
            mode="range",
        )
    except stage.UpdateCancelled:
        raise
    except (update_range.RangeUnavailable, stage.PackageError, OSError) as e:
        logger.info(f"{root} 这次不按区间取，改下整包：{e}")
    except Exception as e:  # noqa: BLE001 - 区间这一路任何意外都退回整包
        logger.opt(exception=True).warning(f"{root} 按区间取出错，改下整包：{e}")
    # 状态这时是「正在准备」，丢掉半成品不会留下可以安装的东西
    await asyncio.to_thread(stage.remove_tree, stage.pkg_dir(root))
    await asyncio.to_thread(stage.remove_tree, stage.stage_emulator_dir(root).parent)
    return None


class _NothingToDo(Exception):
    """拿到锁以后发现前提已经不成立（已经是最新、已经拼好同一版）。"""


async def _prepare(runtime: _Runtime, release: RemoteRelease) -> None:
    """下载并拼好 ``release``，结束时 ``state`` 停在 ``staged``。调用方拿着这个根目录的锁。

    前提在拿到锁之后重新判断（排队期间可能已经装上了别的版本）。动 ``pkg`` / ``stage`` 之前先把状态
    改成「正在准备」，核对通过、``stage`` 拼好后才写 ``staged``；中途取消、失败都丢掉暂存、回到空闲。
    """
    root = runtime.root
    state = await asyncio.to_thread(stage.read_state, root)
    target = release.as_dict()
    if state.get("phase") in (stage.PHASE_SWAPPING, stage.PHASE_ROLLING_BACK):
        raise RuntimeError("上一次换上 / 回退还没收尾，请重启 MAS 后再试")
    local = await asyncio.to_thread(local_version, root)
    if not _newer(release, local):
        raise _NothingToDo(f"已经是最新版本（{local}）")
    if (
        state.get("phase") == stage.PHASE_STAGED
        and (state.get("target") or {}).get("version") == target["version"]
        and stage.stage_emulator_dir(root).is_dir()
    ):
        raise _NothingToDo(f"{release.version} 已经下载并核对过，可以安装")
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
        staged = None
        if await asyncio.to_thread(_range_allowed, root, release):
            staged = await _prepare_by_range(runtime, release, target)
        if staged is None:
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
        else "旧版包没有清单，按 zip CRC 核对"
        + ("" if staged["mode"] == "range" else "并核对了整包的 SHA-256")
    )
    logger.info(
        f"{root} 的 {release.version} 已拼好（{staged['files']} 个文件，"
        f"{'按区间只取变了的' if staged['mode'] == 'range' else '整包'}，{checked}）"
    )


async def _prepare_job(
    runtime: _Runtime, release: RemoteRelease, *, auto: bool
) -> None:
    async with runtime.lock:
        runtime.cancel_requested = False
        try:
            await _prepare(runtime, release)
        except _NothingToDo as e:
            _set(runtime, "idle", "idle", str(e))
            await _publish(runtime)
            return
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
    # 上面有 await：并发的请求可能已经起了任务，起任务前再看一次（这里到 create_task 之间没有 await）
    if runtime.busy:
        return {"ok": False, "message": "正在下载或安装，请稍候"}
    runtime.job = asyncio.create_task(
        _prepare_job(runtime, release, auto=False), name=f"avd-update-prepare:{path}"
    )
    return {"ok": True, "message": f"开始下载 {release.version}"}


async def cancel(root: str) -> dict[str, Any]:
    """取消下载 / 解包（已下的部分留着，下次接着下）。换上一旦开始不能取消。首次安装的下载也走这里。"""
    runtime = _runtimes.get(root_key(str(root or "").strip()))
    if (
        runtime is None
        or not runtime.busy
        or runtime.progress.stage
        not in (
            "downloading",
            "extracting",
            "verifying",
        )
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


async def _swap_job(
    runtime: _Runtime, *, action: str, close: bool, manual: bool
) -> None:
    root = runtime.root
    key = root_key(root)
    verb = "安装" if action == "install" else "回退"
    async with runtime.lock:
        try:
            # 拿到锁之后重新判断：排队期间可能有实例开始开机、有任务开始跑。判断和登记「正在换上」
            # 之间没有 await，和开机（open 先登记自己、_launch 再看「正在换上」）互斥，先占先得
            blocker = _swap_blocker(root, manual=manual)
            if blocker:
                raise stage.SwapBlocked(blocker)
            _swapping.add(key)
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
                version = await asyncio.to_thread(
                    stage.swap_in if action == "install" else stage.rollback, root
                )
            finally:
                _swapping.discard(key)
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
    if action == "rollback":
        problem = await asyncio.to_thread(stage.previous_problem, path)
        if problem:
            return {
                "ok": False,
                "reason": "no_previous",
                "message": problem,
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
    blocker = _swap_blocker(path, manual=True)
    if blocker:
        return {
            "ok": False,
            "reason": "tasks_running" if _tasks_running() else "instances_booting",
            "message": blocker,
            "runningInstances": len(running),
        }
    if runtime.busy:
        return {
            "ok": False,
            "reason": "busy",
            "message": "正在下载或安装，请稍候",
            "runningInstances": 0,
        }
    runtime.job = asyncio.create_task(
        _swap_job(runtime, action=action, close=bool(running), manual=True),
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
            if runtime.busy:
                return
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
    # 上面有 await：再看一次任务、开机和占用（这里到 create_task 之间没有 await）
    if runtime.busy or _tasks_running() or _swap_blocker(root, manual=False):
        return
    logger.info(
        f"{root} 空闲，自动安装 {(state.get('target') or {}).get('version')}（{reason}）"
    )
    runtime.job = asyncio.create_task(
        _swap_job(runtime, action="install", close=False, manual=False),
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
    """实例冷启动到 ``sys.boot_completed`` 时调：新版第一次开机成功就删掉旧版。

    和下载、安装、回退一样拿着这个根目录的更新锁读改写 ``state.json``，不会和它们交错。
    """
    previous = stage.read_state(root).get("previous")
    if not isinstance(previous, dict) or not previous.get("awaitingBoot"):
        return
    runtime = _runtime(Path(root))

    async def confirm() -> None:
        async with runtime.lock:
            await asyncio.to_thread(stage.confirm_boot, runtime.root)

    _spawn(confirm(), "avd-update-confirm-boot")


# ---- 首次安装 --------------------------------------------------------------

#: 许可协议全文的缓存（秒）：同一次打开安装界面里反复点不用每次都去取。
_LICENSE_CACHE_SECONDS = 3600.0
_license_cache: tuple[float, dict[str, str]] | None = None


async def sdk_license() -> dict[str, str]:
    """《Android SDK 许可协议》全文（首次安装时在界面上给用户看、同意后才补全组件）。"""
    global _license_cache
    if _license_cache and time.monotonic() - _license_cache[0] < _LICENSE_CACHE_SECONDS:
        return _license_cache[1]
    from app.core import Config

    result = await first_install.fetch_sdk_license(proxy=Config.proxy)
    _license_cache = (time.monotonic(), result)
    return result


def _first_install_marker(root: Path) -> Path:
    """首次安装开始往根目录里挪文件前写下、挪完删掉：中途中断时据此认出「装到一半」，再点就重做。"""
    return stage.update_dir(root) / "first-install.json"


def _first_install_mode(root: Path) -> str:
    """``full``：空目录（或只有上次没装完留下的 ``.update``、或首次安装挪文件挪到一半），下包再补全组件；
    ``components``：已经是解压好的魔改 AVD（自编版模拟器在、组件缺着），只补全组件。"""
    from app.utils.emulator2.avd.precheck import path_item

    path_check = path_item(root)
    if not path_check.ok:
        raise ValueError(path_check.message())
    if root.exists() and not root.is_dir():
        raise ValueError(f"{root} 不是文件夹")
    if any(root_key(root) == root_key(managed) for managed in _managed_roots()):
        raise ValueError("这个目录已经加进模拟器管理了")
    if _first_install_marker(root).is_file():
        return "full"
    if not root.exists() or not any(
        child.name != UPDATE_DIR for child in root.iterdir()
    ):
        return "full"
    if (
        emulator_self_built(root)
        and (root / first_install.FETCH_COMPONENTS_SCRIPT).is_file()
    ):
        return "components"
    raise ValueError("请选一个空文件夹，MAS 会把魔改 AVD 装进去")


def _read_first_install_marker(root: Path) -> dict[str, Any] | None:
    """上次首次安装留下的标记；没有返回 ``None``，读不出返回空 dict（当作装到一半、不知道挪了哪些）。"""
    try:
        data = json.loads(_first_install_marker(root).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _clear_half_installed(root: Path, root_files: list[str]) -> None:
    """重做首次安装前清掉上次挪进来的包内东西：``sdk\\emulator`` 整个，加上标记里记的根目录文件
    （只认包内路径，``avd``、``mas-avd.json`` 等不属于包的一律不碰），删空了的目录顺手删掉。"""
    stage.remove_tree(stage.emulator_dir(root))
    anchor = Path(os.path.abspath(root))
    for rel in root_files:
        try:
            if stage.package_path(rel) != rel or stage.is_emulator_file(rel):
                continue
            target = resolve_within(anchor, rel, resolve_links=False)
        except (stage.PackageError, ValueError):
            continue
        if os.path.lexists(native_path(target)):
            os.chmod(native_path(target), 0o666)
            os.unlink(native_path(target))
        parent = target.parent
        while parent != anchor and anchor in parent.parents:
            try:
                os.rmdir(native_path(parent))
            except OSError:
                break
            parent = parent.parent


def _place_into_root(root: Path, pkg: Path, release: RemoteRelease) -> None:
    """把核对过的 ``pkg`` 挪进根目录，挪完核对。

    挪之前写下标记（版本、包、根目录里归包管的文件）：挪到一半中断，再点「下载并安装」认得出、重做。
    重做时期间可能已经出了新版，所以先清掉上次挪进来的（``sdk\\emulator`` 整个、上次记下的根目录
    文件），新旧两版的文件不会混在一起。标记里的根目录文件取新旧两次的并集，清到一半再中断也不漏。

    挪完核对：包里每个文件都在、大小对（同盘改名，内容在 ``pkg`` 里已按清单 / CRC 核对过），
    ``sdk\\emulator`` 里不许多出包里没有的文件，上一次独有的根目录文件已经不在。对不上就抛
    :class:`~.update_stage.PackageError`、留着标记，再点会重做。
    """
    files = sorted(stage.walk_files(pkg))
    sizes = {rel: os.stat(native_path(pkg / rel)).st_size for rel in files}
    new_root_files = [rel for rel in files if not stage.is_emulator_file(rel)]
    old = _read_first_install_marker(root)
    old_root_files = [
        rel for rel in (old or {}).get("rootFiles") or [] if isinstance(rel, str)
    ]
    marker = _first_install_marker(root)
    stage.write_json_atomic(
        marker,
        {
            "version": str(release.version),
            "asset": release.asset.name,
            "rootFiles": sorted({*old_root_files, *new_root_files}),
        },
    )
    if old is not None:
        logger.info(
            f"{root} 上次首次安装（{old.get('version') or '版本不明'}）没装完，先清掉挪进来的文件再装 "
            f"{release.version}"
        )
        _clear_half_installed(root, old_root_files)
    for rel in files:
        replace_file(pkg / rel, root / rel)

    problems: list[str] = []
    for rel in files:
        target = root / rel
        if not target.is_file():
            problems.append(f"缺 {rel}")
        elif os.stat(native_path(target)).st_size != sizes[rel]:
            problems.append(f"{rel} 大小不对")
    expected_emulator = {rel.lower() for rel in files if stage.is_emulator_file(rel)}
    problems += [
        f"sdk\\emulator 里多出 {rel}"
        for rel in (
            f"sdk/emulator/{item}"
            for item in stage.walk_files(stage.emulator_dir(root))
        )
        if rel.lower() not in expected_emulator
    ]
    current = {rel.lower() for rel in new_root_files}
    problems += [
        f"上一次的 {rel} 还在"
        for rel in old_root_files
        if rel.lower() not in current and os.path.lexists(native_path(root / rel))
    ]
    if problems:
        shown = "；".join(problems[:5])
        more = f" 等 {len(problems)} 项" if len(problems) > 5 else ""
        raise stage.PackageError(
            f"装进去的文件和包对不上：{shown}{more}。请再点一次「下载并安装」重做"
        )
    marker.unlink()


async def _install_package_into(runtime: _Runtime, release: RemoteRelease) -> None:
    """空目录：下整包、核对，解到 ``.update\\pkg`` 再整体挪进根目录（:func:`_place_into_root`）。"""
    root = runtime.root
    root.mkdir(parents=True, exist_ok=True)
    free = (await asyncio.to_thread(shutil.disk_usage, root)).free
    if free < UPDATE_MIN_FREE_BYTES:
        raise RuntimeError(
            f"{root.anchor or root} 剩余空间 {free / 1024**3:.1f} GB，模拟器本体要约 "
            f"{UPDATE_MIN_FREE_BYTES / 1024**3:.1f} GB（补全组件另要约 6 GB），请先清理"
        )
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
    target = release.as_dict()

    def unpack(extracting: stage.Progress, verifying: stage.Progress) -> None:
        pkg = stage.pkg_dir(root)
        stage.extract_package(
            archive,
            pkg,
            top_dir=target["asset"]["topDir"],
            progress=extracting,
            cancelled=_cancelled(runtime),
        )
        # 和更新同一套核对：新写法版本必须有清单、逐文件比；模拟器的构建号与自编版标志
        try:
            stage.verify_package(
                pkg,
                release.version,
                tag=release.tag,
                progress=verifying,
                cancelled=_cancelled(runtime),
            )
        except stage.PackageError:
            stage.remove_tree(pkg)
            raise
        _place_into_root(root, pkg, release)
        stage.remove_tree(stage.update_dir(root))

    await asyncio.to_thread(
        unpack,
        _thread_progress(runtime, "extracting", "正在解包"),
        _thread_progress(runtime, "verifying", "正在按清单核对每个文件"),
    )
    logger.info(f"已把 {release.version}（{release.asset.name}）装进 {root}")


async def _first_install_job(runtime: _Runtime) -> None:
    root = runtime.root
    async with runtime.lock:
        runtime.cancel_requested = False
        try:
            # 拿到锁之后重新判断：排队期间目录可能变了（另一次安装做完了、被加进管理了）
            mode = await asyncio.to_thread(_first_install_mode, root)
            if mode == "full":
                release = await _latest(force=False)
                required = _automas_block(release)
                if required:
                    raise RuntimeError(
                        f"{release.version} 需要 AUTO-MAS {required} 或更新的版本，请先更新 AUTO-MAS"
                    )
                await _install_package_into(runtime, release)
            _set(
                runtime,
                "components",
                message="正在补全组件（adb 与系统镜像，约 1.6 GB）",
            )
            await _publish(runtime)

            def on_line(line: str) -> None:
                runtime.progress.message = line
                if time.monotonic() - runtime.published_at >= _PUBLISH_INTERVAL_SECONDS:
                    runtime.published_at = time.monotonic()
                    _spawn(_publish(runtime), "avd-first-install-progress")

            code = await first_install.run_fetch_components(root, on_line)
            if code != 0:
                reason = first_install.FETCH_COMPONENTS_EXIT.get(code, f"退出码 {code}")
                raise RuntimeError(
                    f"补全组件没有完成：{reason}。详情见 {root / first_install.FETCH_COMPONENTS_LOG}，"
                    "可以再点一次接着补"
                )
            _set(
                runtime,
                "installed",
                "success",
                "魔改 AVD 已装好，点「添加」把它加进模拟器管理",
            )
        except stage.UpdateCancelled:
            _set(runtime, "cancelled", "idle", "已取消，下次接着下")
        except Exception as e:  # noqa: BLE001 - 失败如实交给界面
            logger.opt(exception=True).warning(f"在 {root} 安装魔改 AVD 失败: {e}")
            _set(runtime, "failed", "failed", f"安装失败：{e}")
        await _publish(runtime)


async def start_first_install(root: str, *, accept_license: bool) -> dict[str, Any]:
    """「添加魔改 AVD」选了空目录：下全量包装进去，再（用户同意许可协议后）跑包里的补全组件。
    已经解压好、只缺组件的目录只补全组件。立刻返回，进度同更新（WebSocket）。"""
    if not accept_license:
        return {"ok": False, "message": "要先阅读并同意《Android SDK 许可协议》"}
    text = str(root or "").strip()
    if not text or not Path(text).is_absolute():
        raise ValueError("请选择一个完整路径的文件夹")
    path = Path(text)
    mode = await asyncio.to_thread(_first_install_mode, path)
    runtime = _runtime(path)
    if runtime.busy:
        return {"ok": False, "message": "正在安装，请稍候"}
    runtime.job = asyncio.create_task(
        _first_install_job(runtime), name=f"avd-first-install:{path}"
    )
    return {
        "ok": True,
        "message": "开始下载魔改 AVD" if mode == "full" else "开始补全组件",
    }


def first_install_progress(root: str) -> dict[str, Any]:
    """首次安装的进度快照（根目录还没纳管，用不了更新状态）。"""
    runtime = _runtimes.get(root_key(str(root or "").strip()))
    if runtime is None:
        return {"busy": False, "progress": asdict(_Progress())}
    return {"busy": runtime.busy, "progress": asdict(runtime.progress)}


__all__ = [
    "cancel",
    "check",
    "first_install_progress",
    "install",
    "sdk_license",
    "start_first_install",
    "note_boot_completed",
    "on_tasks_idle",
    "rollback",
    "set_options",
    "start_download",
    "startup",
    "status",
    "swap_in_progress",
]
