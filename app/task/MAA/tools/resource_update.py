#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
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


"""MAA 资源自动更新（临时补位）。

上游 MAA 把资源自动下载压在 MirrorChyan CDK 之后（ResourceUpdater.cs 的
CheckAndDownloadResourceUpdate 只在 UpdateSource==MirrorChyan 且 CDK 非空时
下载），GitHub 源只保留 GUI 手动入口（设置页按钮 / 主窗口拖拽导入），且没有
任何程序化触发方式（Bootstrapper.ParseArgs 无相关 flag）。本模块在 MAS 侧
补位：MAA 自动代理任务运行前经 prepare_install_resources 更新本次安装的资源。
由触发脚本的接管开关与生效 CDK 驱动：脚本 CDK 优先、空则回退 MAS 全局
配置。GitHub 全量资源包无 CDK 时由脚本更新开关启用；下载器独立跟随全局
FluxDown 接管开关。
Mirror 酱路径按本地日期对同一资源版本每天最多尝试一次，新版本可再次取包；
失败和取消也保留当天记账；
免费版本查询与有效缓存分发不受每日限额影响。

移除条件（任一落地即改为复用上游并删除本模块，见 .agents/skills/
mas-script-specialized-adapter/references/blackbox-boundary.md）：
1. 上游提供程序化导入入口（CLI 参数或 Update 组配置字段）；
2. 上游提供 CDK 无关的自动资源更新入口。
合规上应同步向上游推进「程序化导入 flag」PR（复用其
ImportLocalResourcePackageAsync 即可），受理落地后本模块按存量越界处理退役。

合规边界：不读取/解密 MAA 配置内的 MirrorChyanCdk（上游加密私有字段）；
版本信号只用上游口径的 resource/version.json last_updated（所有客户端唯一
更新时钟，外服亦然，见 VersionUpdateSettingsUserControlModel.cs 的
GetResourceVersionByClientType——外服分支读 defaultJsonPath）与镜像酱
MaaResource/latest 的 version_name；包文件只整体覆盖不解析；不判断资源与
本体版本的兼容性。

失败语义：启动前入口失败则停止本轮启动。
主动取消正常传播。阶段级进度经可选的
progress 回调上报，回调异常被忽略。重文件 I/O（解压、合并、复读
时钟）一律运行在 asyncio.to_thread 内、下载写盘用 aiofiles——MAS 后端是
单事件循环 uvicorn，阻塞 I/O 会冻结整个后端；KB 级状态/清单文件是唯一
例外（与仓库现状一致）。
"""

from __future__ import annotations

import asyncio
import errno
import hashlib
import os
import shutil
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import httpx

from app.core import Config
from app.core.script_update import download_script_package
from app.core.update import download_file
from app.services.common.update import transport as _service_update_transport
from app.utils import get_logger
from app.utils import io as _utils_io

from .resource_package import (
    count_zip_entries,
    extract_zip,
    merge_package_tree,
    resource_tree_hashes,
)
from .update_errors import MaaUpdateUnsafeError
from .update_state import attempted_today, backoff_active, load_state, parse_iso

logger = get_logger("MAA 资源更新")

# version.json last_updated 与镜像酱 version_name 的共同口径（UTC）
_CLOCK_FORMAT = "%Y-%m-%d %H:%M:%S.%f"

_QUERY_TIMEOUT = 10  # 秒
_DOWNLOAD_TIMEOUT = 10 * 60  # 秒，单次网络操作上限（无下载总时限，停滞由操作超时兜底）
_RESOURCE_LOCK_TIMEOUT = 60
_RETRY_INTERVAL = 60 * 60  # 秒，更新失败后的重试间隔
_MB = 1024 * 1024

# data/ 是每个 MAS 实例私有的（双实例各自一份暂存，双下载已接受）；
# 锁文件放 %LOCALAPPDATA%，同一 Windows 用户的多个 MAS 进程互斥；
# 不协调不同 Windows 用户共享安装或未参与锁协议的外部手动启动。
_WORK_DIR = Path.cwd() / "data" / "maa_resource_update"
_STAGE_DIR = _WORK_DIR / "stage"
_STAGE_ZIP = _WORK_DIR / "package.zip"
_MANIFEST_FILE = _WORK_DIR / "manifest.json"
_STATE_FILE = _WORK_DIR / "state.json"
_LOCK_FILE = (
    Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    / "AUTO-MAS"
    / "maa_resource_sync.lock"
)


class _QueryError(RuntimeError):
    """版本查询失败（进固定 1 小时退避）。"""


class _DownloadError(RuntimeError):
    """下载/校验失败（1 小时后重试）。"""


# --------------------------------------------------------------------------
# 时钟（唯一更新时钟：resource/version.json 的 last_updated，UTC）
# --------------------------------------------------------------------------


def _parse_clock(raw: str) -> datetime:
    return datetime.strptime(raw, _CLOCK_FORMAT).replace(tzinfo=timezone.utc)


def _format_clock(value: datetime) -> str:
    """镜像酱 current_version 口径：空格分隔 + 三位毫秒。urlencode 后空格
    变 ``+``、冒号变 ``%3A``，解码后与上游 C# 的 yyyy-MM-dd+HH:mm:ss.fff
    等价（服务器按标准查询解码）。"""
    return f"{value:%Y-%m-%d %H:%M:%S}.{value.microsecond // 1000:03d}"


def _read_clock_file(version_file: Path) -> datetime:
    data = _utils_io.read_dict_file(version_file)
    raw = data.get("last_updated")
    if not isinstance(raw, str) or not raw:
        raise _utils_io.ConfigCorruptedError(version_file)
    try:
        return _parse_clock(raw)
    except ValueError as e:
        raise _utils_io.ConfigCorruptedError(version_file) from e


def read_resource_clock(base: Path) -> datetime | None:
    """读 base（安装目录或暂存树）的更新时钟。文件缺失 → None（无法判定）；
    文件存在但损坏 → ConfigCorruptedError（响亮失败，禁止静默当空）。"""
    version_file = base / "resource" / "version.json"
    if not version_file.is_file():
        return None
    return _read_clock_file(version_file)


# --------------------------------------------------------------------------
# 状态（原子写；损坏一律按无状态处理，靠重查/重下自愈）
# --------------------------------------------------------------------------


def _load_manifest() -> dict[str, object] | None:
    try:
        manifest = _utils_io.read_dict_file(_MANIFEST_FILE)
        # 旧增量缓存及无内容摘要的旧清单不能安全分发，统一重新下载。
        if (
            manifest.get("full") is not True
            or not isinstance(manifest.get("files"), dict)
            or "version.json" not in manifest["files"]
        ):
            return None
        return manifest
    except Exception:
        logger.warning(f"MAA 资源更新: 暂存清单损坏，按无暂存处理: {_MANIFEST_FILE}")
        return None


def _load_valid_manifest() -> dict[str, object] | None:
    """线程内复核缓存内容与版本；不一致时作废，读取异常交由调用方处理。"""
    manifest = _load_manifest()
    if manifest is None:
        return None
    valid = manifest["files"] == resource_tree_hashes(_STAGE_DIR / "resource")
    if valid:
        try:
            clock = read_resource_clock(_STAGE_DIR)
        except (OSError, ValueError):
            clock = None
        valid = clock is not None and parse_iso(manifest.get("target")) == clock
    if not valid:
        _MANIFEST_FILE.unlink(missing_ok=True)
        logger.warning("MAA 资源更新: 暂存内容或版本与清单不一致，作废缓存等待重建")
        return None
    return manifest


# --------------------------------------------------------------------------
# 枚举与占用（配置快照在事件循环采集，进程扫描与磁盘探测在线程执行）
# --------------------------------------------------------------------------


def _path_key(value: Path | str) -> str:
    return os.path.normcase(os.path.normpath(str(Path(value).resolve(strict=False))))


_install_write_locks: dict[str, asyncio.Lock] = {}


def get_resource_write_lock(install: Path) -> asyncio.Lock:
    """同一安装的资源写入与配置会话加锁互斥，不阻塞会话等待网络下载。"""
    return _install_write_locks.setdefault(_path_key(install), asyncio.Lock())


# --------------------------------------------------------------------------
# 查询与取包
# --------------------------------------------------------------------------


def _sp_id() -> str:
    """镜像酱反滥用的稳定识别码；无敏感信息。"""
    seed = os.environ.get("COMPUTERNAME", "auto-mas")
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


async def _fetch_latest_version(current: str) -> datetime:
    """免费版本查询（无 CDK、不带 os/arch），返回目标时钟。

    Raises:
        _QueryError: 网络、响应解析或业务码的任何失败。
    """
    try:
        # HTTPX 只限制单次网络操作；持续回字节也必须在总时限内结束。
        async with asyncio.timeout(_QUERY_TIMEOUT):
            payload = await _service_update_transport.request_mirror_resource(
                "MaaResource",
                params={"current_version": current, "sp_id": _sp_id()},
                proxy=Config.proxy,
                timeout=_QUERY_TIMEOUT,
            )
    except TimeoutError as e:
        raise _QueryError("镜像酱版本查询超时") from e
    except Exception as e:
        raise _QueryError(f"镜像酱版本查询失败: {e}") from e
    name = None
    if isinstance(payload.get("data"), dict):
        name = payload["data"].get("version_name")
    if not name:
        raise _QueryError("响应缺少 version_name")
    try:
        return _parse_clock(str(name))
    except ValueError as e:
        raise _QueryError(f"version_name 无法解析: {name}") from e


async def _request_resource_package(cdk: str) -> tuple[str, datetime | None]:
    """申请全量包，返回一次性地址与响应版本；版本损坏由调用方记账后报错。"""
    try:
        async with asyncio.timeout(_QUERY_TIMEOUT):
            payload = await _service_update_transport.request_mirror_resource(
                "MaaResource",
                params={"cdk": cdk, "sp_id": _sp_id()},
                proxy=Config.proxy,
                timeout=_QUERY_TIMEOUT,
            )
    except TimeoutError as e:
        raise _DownloadError("镜像酱下载地址获取超时") from e
    except Exception as e:
        raise _DownloadError(f"镜像酱下载地址获取失败: {e}") from e
    url = None
    if isinstance(payload.get("data"), dict):
        url = payload["data"].get("url")
    if not url:
        raise _DownloadError("镜像酱未返回下载地址")
    if payload["data"].get("update_type") != "full":
        raise _DownloadError("镜像酱未返回全量资源包，跳过以避免多实例重复取包")
    try:
        version = _parse_clock(str(payload["data"].get("version_name") or ""))
    except ValueError:
        version = None
    return str(url), version


def _download_line(downloaded: int, total: int, speed: float) -> str:
    """下载进度行：有 Content-Length 时带 x/y MB，速度按量级选单位。"""
    label = "下载 Mirror酱 全量资源包"
    speed_text = (
        f"{speed / _MB:.1f} MB/s" if speed >= _MB else f"{speed / 1024:.0f} KB/s"
    )
    if total:
        return f"{label} {downloaded / _MB:.1f}/{total / _MB:.1f} MB（{speed_text}）…"
    return f"{label} {downloaded / _MB:.1f} MB（{speed_text}）…"


async def _stream_download(url: str, progress: _Progress | None) -> None:
    async def report_progress(downloaded: int, total: int, speed: float) -> None:
        await _report(progress, _download_line(downloaded, total, speed))

    try:
        # Mirror 酱临时授权 URL 显式声明来源并锁定内置下载器，不依赖全局
        # Source/Downloader：FluxDown 不接短期授权链接（凭证泄漏风险）
        # 不设外层总时限：timeout 只限单次网络操作，慢速但持续的下载不该被掐断
        await download_file(
            url,
            _STAGE_ZIP,
            timeout=_DOWNLOAD_TIMEOUT,
            proxy=Config.proxy,
            progress=report_progress,
            source="MirrorChyan",
            downloader="builtin",
        )
    except TimeoutError as e:
        raise _DownloadError("下载超时") from e
    except Exception as e:
        raise _DownloadError(f"资源包下载失败: {e}") from e


def _build_stage(zip_path: Path, target: datetime, *, github: bool = False) -> None:
    """解压 → 校验 → 单调把关 → 换位 → 核账 → manifest。线程内执行；任何
    失败都抛 _DownloadError（进下载退避）。

    暂存保持安装目录形态（resource/ 在 _STAGE_DIR 下），消费方才能用
    read_resource_clock / merge_package_tree 以同一形态读写。解压目录名带
    pid + 单调量；取消时等待本线程结束后才释放机器锁。换位顺序是关键不变式：

    1. 动旧暂存**之前**先删 manifest——半途死掉时盘上「无 manifest」，
       下一轮按无暂存重建，绝不会拿旧 manifest 去分发半删的树；
    2. 换位后按 zip 条目数与内容摘要核账——残缺树（并发清理、AV 删文件）即使带着
       合法 version.json 也会在这里被拒，防止「缺文件但时钟已 bump」
       这种哈希比对永远救不回的静默损坏被分发。
    """
    stage_tmp = _WORK_DIR / f"stage.tmp.{os.getpid()}.{time.monotonic_ns()}"
    # 调用方持有机器锁，且取消会等待写入线程结束：历史目录不可能仍在使用。
    work_root = _WORK_DIR.resolve()
    for leftover in _WORK_DIR.glob("stage.tmp.*"):
        if leftover.is_dir() and leftover.resolve().is_relative_to(work_root):
            _utils_io.force_rmtree(leftover)
    try:
        extract_zip(zip_path, stage_tmp)
        prefix = "MaaResource-main/resource/" if github else "resource/"
        root = stage_tmp / prefix
        # 当前上游的 Mirror 酱导入同样使用 MaaResource-main/resource；
        # 保留对既有平铺缓存包的兼容，只接受这两种已知发行目录结构。
        if not github and not (root / "version.json").is_file():
            prefix = "MaaResource-main/resource/"
            root = stage_tmp / prefix
        if not (root / "version.json").is_file():
            raise _DownloadError("资源包内未找到 resource/version.json")
        new_clock = _read_clock_file(root / "version.json")
        # 查询与取包期间可能又有新版本：全量包不旧于查询目标即可。
        if new_clock < target:
            raise _DownloadError(
                f"资源包版本({_format_clock(new_clock)})与查询目标({_format_clock(target)})"
                "不一致，疑似缓存滞后"
            )
        old_clock_file = _STAGE_DIR / "resource" / "version.json"
        # 损坏缓存的时钟不能阻止重建；只有完整缓存参与防倒退判断。
        if _load_valid_manifest() is not None and old_clock_file.is_file():
            try:
                old_clock = _read_clock_file(old_clock_file)
            except (OSError, ValueError):
                old_clock = None
            if old_clock is not None and new_clock < old_clock:
                raise _DownloadError(
                    f"资源包版本({_format_clock(new_clock)})旧于现有暂存"
                    f"({_format_clock(old_clock)})，拒绝替换"
                )
        expected = count_zip_entries(zip_path, prefix=prefix)
        file_hashes = resource_tree_hashes(root)
        _MANIFEST_FILE.unlink(missing_ok=True)
        if _STAGE_DIR.exists():
            # 先原子改名再删，失败时退休目录交由孤儿清理。名字由本次
            # 唯一的 stage_tmp 派生。
            retired = _WORK_DIR / f"{stage_tmp.name}.old"
            os.rename(_STAGE_DIR, retired)
            _utils_io.force_rmtree(retired)
        _STAGE_DIR.mkdir(parents=True)
        shutil.move(str(root), str(_STAGE_DIR / "resource"))
        actual = sum(1 for p in (_STAGE_DIR / "resource").rglob("*") if p.is_file())
        if (
            actual != expected
            or resource_tree_hashes(_STAGE_DIR / "resource") != file_hashes
        ):
            raise _DownloadError(
                f"暂存树不完整（{actual}/{expected} 个文件），拒绝提交"
            )
        # manifest 最后写：它是暂存自身的提交标记，半途失败视为无暂存
        _utils_io.write_file(
            _MANIFEST_FILE,
            {
                "target": new_clock.isoformat(),
                "full": True,
                "files": file_hashes,
            },
        )
    except _DownloadError:
        raise
    except Exception as e:
        raise _DownloadError(f"暂存重建失败: {e}") from e
    finally:
        if stage_tmp.exists():
            _utils_io.force_rmtree(stage_tmp)


async def _refresh_stage(
    target: datetime, url: str, progress: _Progress | None = None
) -> None:
    """下载已取得地址的资源包并重建暂存；失败抛 _DownloadError。"""
    await _stream_download(url, progress)
    await _report(progress, "校验并暂存资源包…")
    await _run_write_thread(
        _build_stage,
        zip_path=_STAGE_ZIP,
        target=target,
    )
    # zip 是可弃缓存，删不掉（AV 隔离等）也无妨——下次下载按 "wb" 截断重写
    with suppress(OSError):
        _STAGE_ZIP.unlink(missing_ok=True)


# --------------------------------------------------------------------------
# 机器级锁（双 MAS 实例共存；进程死亡由 OS 释放）
# --------------------------------------------------------------------------


class _MachineLock:
    def __init__(self, *, lock_file: Path | None = None) -> None:
        self._lock_file = lock_file or _LOCK_FILE
        self._fh = None
        self.contended = False

    def __enter__(self) -> "_MachineLock | None":
        self.contended = False
        try:
            self._lock_file.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(self._lock_file, "a+b")
            self._fh.seek(0, 2)
            if self._fh.tell() == 0:
                self._fh.write(b"\0")
                self._fh.flush()
            self._fh.seek(0)
            import msvcrt

            try:
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as e:
                self.contended = e.errno in (errno.EACCES, errno.EDEADLK)
                raise
            return self
        except ImportError:
            return self  # 非 Windows：无锁运行（MAS 仅发 Windows，此处只为不崩溃）
        except OSError as e:
            if not self.contended:
                logger.warning(f"MAA 资源更新: 文件锁不可用（跳过资源写入）: {e}")
            if self._fh is not None:
                self._fh.close()
                self._fh = None
            return None
        except ValueError:
            if self._fh is not None:
                self._fh.close()
                self._fh = None
            return None

    def __exit__(self, *exc_info: object) -> None:
        if self._fh is None:
            return
        try:
            import msvcrt

            self._fh.seek(0)
            msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:
            pass
        finally:
            self._fh.close()
            self._fh = None


def _resource_access_lock(install: Path) -> _MachineLock:
    key = hashlib.sha256(_path_key(install).encode("utf-8")).hexdigest()
    return _MachineLock(
        lock_file=_LOCK_FILE.with_name(f"maa_resource_access_{key}.lock")
    )


async def acquire_resource_access_lock(install: Path) -> _MachineLock | None:
    """取得本安装的跨进程访问锁；调用方负责在子任务结束后释放。

    运行与配置会话持有至 MAA 子任务结束，其他 MAS 更新器跳过被持有的安装。
    争用只作用于本安装，下载阶段不持有访问锁；锁不可用时更新器也不会写入。
    """
    while True:
        lock = _resource_access_lock(install)
        acquired = lock.__enter__()
        if acquired is not None:
            return acquired
        if not lock.contended:
            return None
        await asyncio.sleep(0.1)


# --------------------------------------------------------------------------
# 编排入口
# --------------------------------------------------------------------------


def _stage_reusable(stage: dict[str, object] | None, target: datetime) -> bool:
    """全量暂存达到目标即可复用。"""
    if stage is None:
        return False
    stage_target = parse_iso(stage.get("target"))
    if stage_target is None:
        return False
    return stage_target >= target


def has_incomplete_resource_update(install: Path) -> bool:
    """安装目录曾开始覆盖资源但尚未完成校验；跨任务保留，不能按旧时钟放行。"""
    return (install / ".automas-resource-update.json").exists()


def _apply_stage(install: Path, stage_clock: datetime, cdk: str) -> bool:
    """合并前复读版本并检查暂存有效，写完核对时钟；跳过返回 False。"""
    current = read_resource_clock(install)
    incomplete = has_incomplete_resource_update(install)
    if current is None or (current >= stage_clock and not incomplete):
        return False
    if current > stage_clock:
        raise MaaUpdateUnsafeError("资源修复缓存早于当前安装，请重新下载资源")
    marker = install / ".automas-resource-update.json"
    if incomplete:
        interrupted_target = parse_iso(_utils_io.read_dict_file(marker).get("target"))
        if interrupted_target is None or stage_clock < interrupted_target:
            raise MaaUpdateUnsafeError(
                "资源修复缓存未达到上次中断的目标，请重新下载资源"
            )
    manifest = _load_valid_manifest()
    if manifest is None:
        return False
    # 标记先于第一次覆盖落盘；异常、取消或进程退出均不得清除。
    _utils_io.write_file(marker, {"target": stage_clock.isoformat()})
    merge_package_tree(
        _STAGE_DIR / "resource",
        install / "resource",
        file_hashes=cast(dict[str, str], manifest["files"]),
    )
    done = read_resource_clock(install)
    if done is None or done < stage_clock:
        raise RuntimeError(f"合并后时钟为 {done}，期望 {stage_clock}")
    # merge_package_tree 已逐文件验证摘要及清单，版本复核通过后才提交完成。
    marker.unlink()
    return True


_Progress = Callable[[str], Awaitable[None]]


async def _wait_for_cleanup(task: asyncio.Task[object]) -> None:
    """重复中止也必须等清理完成，避免后台写入失去锁保护。"""
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
        except Exception:
            break
    with suppress(asyncio.CancelledError, Exception):
        task.result()


async def _run_write_thread[T](
    operation: Callable[..., T], *args: object, **kwargs: object
) -> T:
    """取消不能停止线程：保留等待和外层机器锁，直到写入结束。"""
    worker = asyncio.create_task(asyncio.to_thread(operation, *args, **kwargs))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        await _wait_for_cleanup(worker)
        raise


async def _report(progress: _Progress | None, line: str) -> None:
    """阶段级进度上报：回调异常只影响展示，绝不影响更新流程。"""
    if progress is None:
        return
    try:
        await progress(line)
    except Exception:
        logger.debug("MAA 资源更新: 进度回调失败（不影响更新流程）")


async def _refresh_resource_stage(
    *,
    clocks: dict[Path, datetime],
    stage: dict[str, object] | None,
    target: datetime | None,
    state: dict[str, object],
    progress: _Progress | None,
    cdk: str,
) -> dict[str, object] | None:
    """按版本每日限额与失败退避刷新缓存；state 由编排器持有并在此记账。"""
    if (
        target is None
        or not any(clock < target for clock in clocks.values())
        or _stage_reusable(stage, target)
    ):
        return stage
    now = datetime.now(timezone.utc)
    credential_key = hashlib.sha256(cdk.encode("utf-8")).hexdigest()[:16]
    attempt_field = f"last_download_attempt_at/{credential_key}"
    version_field = f"last_download_attempt_version/{credential_key}"
    failure_field = f"download_fail_until/{credential_key}"
    if backoff_active(state, failure_field, now):
        return stage
    previous = parse_iso(state.get(version_field))
    # 旧状态没有版本记录时允许一次，随后与尝试时间一起补记。
    if (
        attempted_today(state, attempt_field, now)
        and previous is not None
        and target <= previous
    ):
        await _report(
            progress, "今日已尝试获取此版本资源包，出现新版或明日再试；已有缓存照常分发"
        )
        return stage
    await _report(progress, f"发现新版本 {_format_clock(target)}，下载资源包…")
    try:
        # 凭据被拒、尚未取得下载地址时不消耗当天取包次数；不同 CDK 独立退避。
        url, actual = await _request_resource_package(cdk)
        state[attempt_field] = datetime.now(timezone.utc).isoformat()
        state[version_field] = max(target, actual or target).isoformat()
        _utils_io.write_file(_STATE_FILE, state)
        if actual is None or actual < target:
            raise _DownloadError("镜像酱资源包未达到已确认的目标版本，请稍后重试")
        await _refresh_stage(target=actual, url=url, progress=progress)
        return _load_manifest()
    except _DownloadError as e:
        state[failure_field] = (
            datetime.now(timezone.utc) + timedelta(seconds=_RETRY_INTERVAL)
        ).isoformat()
        _utils_io.write_file(_STATE_FILE, state)
        logger.warning(f"MAA 资源更新: 取包失败（退避 1 小时，仍受每日限额约束）: {e}")
        await _report(progress, "资源包下载失败；至少 1 小时后且有当日额度时重试")
        # 换位失败可能已经作废清单，按盘上现状决定是否继续分发旧缓存。
        return _load_manifest()


_prepare_install_lock = asyncio.Lock()


async def latest_resource_clock(*, github: bool, current: datetime) -> datetime:
    """重新查询上游资源版本，供更新与启动前最终核对共用。"""
    if not github:
        return await _fetch_latest_version(_format_clock(current))
    async with httpx.AsyncClient(proxy=Config.proxy, timeout=10) as client:
        response = await client.get(
            "https://raw.githubusercontent.com/MaaAssistantArknights/"
            "MaaResource/main/resource/version.json"
        )
        response.raise_for_status()
        return _parse_clock(response.json()["last_updated"])


async def prepare_install_resources(
    install: Path,
    *,
    cdk: str | None,
    github: bool,
    progress: _Progress | None = None,
) -> None:
    """本体安装之后、账号启动之前补齐资源；调用方已持有安装访问锁。

    GitHub 复用上游公开的 MaaResource-main 整包与既有临时合并入口。
    上游仍无程序化资源导入入口；提供 CLI 后删除此补位并改用官方导入。
    普通准备失败由调用方处理；实际写入失败必须阻止启动，不延后到运行中下载。
    """
    if not github and cdk is None:
        return
    try:
        async with asyncio.timeout(_RESOURCE_LOCK_TIMEOUT):
            if _prepare_install_lock.locked():
                await _report(progress, "正在等待其他 MAA 资源更新完成…")
            await _prepare_install_lock.acquire()
    except TimeoutError as error:
        raise RuntimeError("等待 MAA 资源更新超时，请稍后重试") from error
    try:
        deadline = time.monotonic() + _RESOURCE_LOCK_TIMEOUT
        waiting = False
        while True:
            machine = _MachineLock()
            access = machine.__enter__()
            if access is not None:
                break
            if not machine.contended:
                raise RuntimeError("无法取得 MAA 资源缓存锁，请稍后重试")
            if not waiting:
                await _report(progress, "正在等待其他 MAS 实例释放资源更新锁…")
                waiting = True
            if time.monotonic() >= deadline:
                raise RuntimeError("等待 MAA 资源锁超时，请等待其他实例完成更新后重试")
            await asyncio.sleep(0.1)
        try:
            current = await asyncio.to_thread(read_resource_clock, install)
            if current is None:
                raise RuntimeError("MAA 缺少资源版本，请先在 MAA 内完成修复")
            await _report(progress, "启动前检查 MAA 资源更新…")
            target = await latest_resource_clock(github=github, current=current)
            if current >= target and not has_incomplete_resource_update(install):
                return
            stage = await asyncio.to_thread(_load_valid_manifest)
            if not _stage_reusable(stage, target):
                if github:
                    _WORK_DIR.mkdir(parents=True, exist_ok=True)
                    await _report(progress, "启动前下载 GitHub 全量资源包…")
                    await download_script_package(
                        "https://github.com/MaaAssistantArknights/MaaResource/"
                        "archive/refs/heads/main.zip",
                        _STAGE_ZIP,
                        proxy=Config.proxy,
                        timeout=_DOWNLOAD_TIMEOUT,
                        source="GitHub",
                    )
                    try:
                        await _run_write_thread(
                            _build_stage, _STAGE_ZIP, target, github=True
                        )
                    finally:
                        # _run_write_thread 在取消时也会等写盘结束，之后才可删除归档。
                        _STAGE_ZIP.unlink(missing_ok=True)
                else:
                    _WORK_DIR.mkdir(parents=True, exist_ok=True)
                    stage = await _refresh_resource_stage(
                        clocks={install: current},
                        stage=stage,
                        target=target,
                        state=load_state(_STATE_FILE),
                        progress=progress,
                        cdk=cdk,
                    )
                    if not _stage_reusable(stage, target):
                        raise RuntimeError(
                            "MAA 资源包未准备完成，请检查 CDK、额度或网络后重试"
                        )
            await _report(progress, "启动前安装 MAA 资源更新…")
            stage_clock = await asyncio.to_thread(read_resource_clock, _STAGE_DIR)
            if stage_clock is None or stage_clock < target:
                raise RuntimeError("MAA 资源缓存未达到目标版本，请重新运行")
            try:
                await _run_write_thread(_apply_stage, install, stage_clock, cdk or "")
                installed = await asyncio.to_thread(read_resource_clock, install)
                if (
                    installed is None
                    or installed < target
                    or has_incomplete_resource_update(install)
                ):
                    raise RuntimeError("MAA 资源更新未完成，已停止启动")
            except Exception as error:
                raise MaaUpdateUnsafeError(
                    "MAA 资源写入未确认完成，不能安全启动任务"
                ) from error
        finally:
            machine.__exit__(None, None, None)
    finally:
        _prepare_install_lock.release()
