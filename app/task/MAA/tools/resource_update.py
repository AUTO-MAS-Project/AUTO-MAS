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
补位：MAA 自动代理任务运行前（MaaManager._run_main_task 锁定配置之前；配置会话
不触发）按需更新启用「更新接管」脚本的 MAA 实例的资源。
由触发脚本的接管开关与生效 CDK 驱动：脚本 CDK 优先、空则回退 MAS 全局
配置；未开接管时完全不创建更新任务，检查与分发也只覆盖开了接管的安装。
不使用 GitHub 资源源。
每个 MAS 按本地日期每天最多尝试申请一次资源包，失败和取消也保留当天记账；
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

失败语义：更新失败只写日志，主动取消正常传播。阶段级进度经可选的
progress 回调上报，回调异常被忽略。重文件 I/O（进程扫描、解压、合并、逐安装复读
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

import psutil

from app.core import Config
from app.models.config import MaaConfig
from app.services.update_transport import download_file, request_mirror_resource
from app.utils import get_logger
from app.utils.io import ConfigCorruptedError, force_rmtree, read_dict_file, write_file

from .resource_package import (
    count_zip_entries,
    extract_zip,
    merge_package_tree,
    resource_tree_hashes,
)
from .update_credentials import resolve_takeover_credentials
from .update_state import attempted_today, backoff_active, load_state, parse_iso

logger = get_logger("MAA 资源更新")

# version.json last_updated 与镜像酱 version_name 的共同口径（UTC）
_CLOCK_FORMAT = "%Y-%m-%d %H:%M:%S.%f"

_QUERY_TIMEOUT = 10  # 秒
_DOWNLOAD_TIMEOUT = 10 * 60  # 秒，单次下载总上限
_QUERY_FLOOR = 10 * 60  # 秒，两次成功查询最小间隔（只作用于刷新检查）
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
    data = read_dict_file(version_file)
    raw = data.get("last_updated")
    if not isinstance(raw, str) or not raw:
        raise ConfigCorruptedError(version_file)
    try:
        return _parse_clock(raw)
    except ValueError as e:
        raise ConfigCorruptedError(version_file) from e


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
        manifest = read_dict_file(_MANIFEST_FILE)
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


def _snapshot_maa_configs() -> list[tuple[str, bool]]:
    """在事件循环采集路径和占用状态；无法确认时拒绝继续写入。

    只收集开启「更新接管」且有生效 CDK 的脚本，未满足接管条件的安装
    不参与检查与分发。
    """
    try:
        entries = list(Config.ScriptConfig.items())
        result: list[tuple[str, bool]] = []
        for _, config in entries:
            if isinstance(config, MaaConfig):
                enabled, _ = resolve_takeover_credentials(config)
                if not enabled:
                    continue
                raw = str(config.get("Info", "Path") or "")
                if raw:
                    result.append((raw, bool(config.is_locked)))
        return result
    except Exception as e:
        raise RuntimeError("无法读取 MAA 安装配置或占用状态，跳过资源写入") from e


def _locked_install_keys(configs: list[tuple[str, bool]]) -> set[str]:
    return {_path_key(raw) for raw, locked in configs if locked}


def _running_maa_exe_paths() -> set[str]:
    """正在运行的 MAA.exe / MAA.Updater.exe 的可执行文件路径（归一化）。
    覆盖 MAS 看不见的手动 GUI 与 OTA 更新器。"""
    wanted = {"maa.exe", "maa.updater.exe"}
    result: set[str] = set()
    for proc in psutil.process_iter(["name", "exe"]):
        try:
            name = (proc.info.get("name") or "").lower()
            exe = proc.info.get("exe")
            if name in wanted and exe:
                result.add(_path_key(exe))
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    return result


def _snapshot_installs(configs: list[tuple[str, bool]]) -> list[tuple[Path, datetime]]:
    """枚举 MAA 安装及其时钟；内容损坏上抛，瞬态不可读逐项跳过。

    跳过被占用的安装、缺少版本文件的安装及瞬态读取错误；版本文件损坏时
    抛 ConfigCorruptedError，由编排入口明确报告并停止本轮资源更新。
    先收集安装路径再做进程/锁定扫描，零 MAA 安装时不做全进程扫描。
    """
    installs: dict[str, Path] = {}
    for raw, _ in configs:
        installs.setdefault(_path_key(raw), Path(raw))
    if not installs:
        return []
    locked = _locked_install_keys(configs)
    running = _running_maa_exe_paths()
    result: list[tuple[Path, datetime]] = []
    for key, install in installs.items():
        if key in locked:
            logger.info(f"MAA 资源更新: 跳过被占用的安装 {install}")
            continue
        if any(exe.startswith(key + os.sep) for exe in running):
            logger.info(f"MAA 资源更新: 跳过 MAA 正在运行的安装 {install}")
            continue
        version_file = install / "resource" / "version.json"
        if not version_file.is_file():
            logger.info(
                f"MAA 资源更新: 跳过缺少 resource/version.json 的安装 {install}"
            )
            continue
        try:
            clock = _read_clock_file(version_file)
        except OSError:
            logger.warning(f"MAA 资源更新: {version_file} 暂不可读，本轮跳过该安装")
            continue
        result.append((install, clock))
    return result


def _install_busy_now(install: Path, configs: list[tuple[str, bool]]) -> bool:
    """合并前复查接管条件、配置锁和运行进程。"""
    key = _path_key(install)
    return (
        key not in {_path_key(raw) for raw, _ in configs}
        or key in _locked_install_keys(configs)
        or any(exe.startswith(key + os.sep) for exe in _running_maa_exe_paths())
    )


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
            payload = await request_mirror_resource(
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


async def _mirror_download_url(cdk: str) -> str:
    """不指定增量基线，申请全量包；地址一次性，现查现下。"""
    try:
        async with asyncio.timeout(_QUERY_TIMEOUT):
            payload = await request_mirror_resource(
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
    return str(url)


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
        async with asyncio.timeout(_DOWNLOAD_TIMEOUT):
            await download_file(
                url,
                _STAGE_ZIP,
                timeout=_DOWNLOAD_TIMEOUT,
                proxy=Config.proxy,
                progress=report_progress,
            )
    except TimeoutError as e:
        raise _DownloadError("下载超时") from e
    except Exception as e:
        raise _DownloadError(f"资源包下载失败: {e}") from e


def _build_stage(zip_path: Path, target: datetime) -> None:
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
            force_rmtree(leftover)
    try:
        extract_zip(zip_path, stage_tmp)
        root = stage_tmp / "resource"
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
        expected = count_zip_entries(zip_path)
        file_hashes = resource_tree_hashes(root)
        _MANIFEST_FILE.unlink(missing_ok=True)
        if _STAGE_DIR.exists():
            # 先原子改名再删，失败时退休目录交由孤儿清理。名字由本次
            # 唯一的 stage_tmp 派生。
            retired = _WORK_DIR / f"{stage_tmp.name}.old"
            os.rename(_STAGE_DIR, retired)
            force_rmtree(retired)
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
        write_file(
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
            force_rmtree(stage_tmp)


async def _refresh_stage(
    target: datetime, cdk: str, progress: _Progress | None = None
) -> bool:
    """取包并重建暂存。返回 False = 按设置本轮不可取包（无退避）；失败抛
    _DownloadError。"""
    url = await _mirror_download_url(cdk)
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
    return True


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


def _apply_stage(install: Path, stage_clock: datetime, cdk: str) -> bool:
    """合并前复读版本并检查暂存有效，写完核对时钟；跳过返回 False。"""
    current = read_resource_clock(install)
    if current is None or current >= stage_clock:
        return False
    manifest = _load_valid_manifest()
    if manifest is None:
        return False
    merge_package_tree(
        _STAGE_DIR / "resource",
        install / "resource",
        file_hashes=cast(dict[str, str], manifest["files"]),
    )
    done = read_resource_clock(install)
    if done is None or done < stage_clock:
        raise RuntimeError(f"合并后时钟为 {done}，期望 {stage_clock}")
    return True


_Progress = Callable[[str], Awaitable[None]]
_update_task: asyncio.Task[None] | None = None
_update_waiters: dict[object, _Progress | None] = {}


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


async def _broadcast_progress(line: str) -> None:
    await asyncio.gather(
        *(_report(progress, line) for progress in list(_update_waiters.values()))
    )


async def _report(progress: _Progress | None, line: str) -> None:
    """阶段级进度上报：回调异常只影响展示，绝不影响更新流程。"""
    if progress is None:
        return
    try:
        await progress(line)
    except Exception:
        logger.debug("MAA 资源更新: 进度回调失败（不影响更新流程）")


async def _query_resource_version(
    *,
    clocks: dict[Path, datetime],
    stage: dict[str, object] | None,
    state: dict[str, object],
) -> datetime | None:
    """免费查询版本并更新查询状态；地板或退避命中时不查询。"""
    now = datetime.now(timezone.utc)
    last_query = parse_iso(state.get("last_query_at"))
    if backoff_active(state, "query_fail_until", now) or (
        last_query is not None and now - last_query < timedelta(seconds=_QUERY_FLOOR)
    ):
        return None
    stage_target = parse_iso(stage.get("target")) if stage else None
    # 无缓存时报告最旧实例的真实时钟，不使用未实测的极旧版本哨兵。
    current = _format_clock(stage_target or min(clocks.values()))
    try:
        target = await _fetch_latest_version(current)
        state["last_query_at"] = datetime.now(timezone.utc).isoformat()
        write_file(_STATE_FILE, state)
        return target
    except _QueryError as e:
        state["query_fail_until"] = (
            datetime.now(timezone.utc) + timedelta(seconds=_RETRY_INTERVAL)
        ).isoformat()
        write_file(_STATE_FILE, state)
        logger.warning(f"MAA 资源更新: 版本查询失败（1 小时内不再尝试）: {e}")
        return None


async def _refresh_resource_stage(
    *,
    clocks: dict[Path, datetime],
    stage: dict[str, object] | None,
    target: datetime | None,
    state: dict[str, object],
    progress: _Progress | None,
    cdk: str,
) -> dict[str, object] | None:
    """按每日限额与失败退避刷新缓存；state 由编排器持有并在此记账。"""
    if (
        target is None
        or not any(clock < target for clock in clocks.values())
        or _stage_reusable(stage, target)
    ):
        return stage
    now = datetime.now(timezone.utc)
    if backoff_active(state, "download_fail_until", now):
        return stage
    if attempted_today(state, "last_download_attempt_at", now):
        await _report(progress, "今日已尝试获取资源包，明日再试；已有缓存照常分发")
        return stage
    await _report(progress, f"发现新版本 {_format_clock(target)}，下载资源包…")
    previous_attempt = state.get("last_download_attempt_at")
    # 请求前持久记账：失败、取消或进程退出都不能再次消耗当天预算。
    state["last_download_attempt_at"] = datetime.now(timezone.utc).isoformat()
    write_file(_STATE_FILE, state)
    try:
        refreshed = await _refresh_stage(target, cdk, progress)
        if not refreshed:
            # 启用条件改变且尚未请求资源包，不占用当天预算。
            if previous_attempt is None:
                state.pop("last_download_attempt_at", None)
            else:
                state["last_download_attempt_at"] = previous_attempt
            write_file(_STATE_FILE, state)
            await _report(progress, "更新源未使用 Mirror酱 或未填 Key，跳过资源更新")
        return _load_manifest()
    except _DownloadError as e:
        state["download_fail_until"] = (
            datetime.now(timezone.utc) + timedelta(seconds=_RETRY_INTERVAL)
        ).isoformat()
        write_file(_STATE_FILE, state)
        logger.warning(f"MAA 资源更新: 取包失败（退避 1 小时，仍受每日限额约束）: {e}")
        await _report(progress, "资源包下载失败；至少 1 小时后且有当日额度时重试")
        # 换位失败可能已经作废清单，按盘上现状决定是否继续分发旧缓存。
        return _load_manifest()


async def _distribute_resource_stage(
    *,
    clocks: dict[Path, datetime],
    stage: dict[str, object] | None,
    progress: _Progress | None,
    cdk: str,
) -> None:
    """以有效缓存的实际时钟分发，查询地板、退避与日限额不阻止分发。"""
    if stage is None:
        return
    try:
        stage_clock = read_resource_clock(_STAGE_DIR)
    except ValueError:
        # 真损坏（ConfigCorruptedError）：作废暂存，下轮重建
        logger.warning("MAA 资源更新: 暂存 version.json 损坏，作废暂存等待下轮重建")
        _MANIFEST_FILE.unlink(missing_ok=True)
        return
    except OSError:
        # 瞬态不可读（AV 共享冲突等）：暂存大概率完好，只跳过本轮分发
        logger.warning("MAA 资源更新: 暂存 version.json 暂不可读，本轮跳过分发")
        return
    if stage_clock is None:
        logger.warning("MAA 资源更新: 暂存资源目录缺失，作废暂存等待下轮重建")
        _MANIFEST_FILE.unlink(missing_ok=True)
        return

    candidates = [install for install, clock in clocks.items() if clock < stage_clock]

    if not candidates:
        return
    await _report(progress, f"分发资源更新到 {len(candidates)} 个实例…")
    done = failed = 0
    for install in candidates:
        try:
            # 与配置会话加锁互斥；持锁复查占用，直至写线程收尾完成才放行。
            async with get_resource_write_lock(install):
                with _resource_access_lock(install) as access:
                    if access is None:
                        logger.info(f"MAA 资源更新: 安装访问锁未取得，跳过 {install}")
                        continue
                    configs = _snapshot_maa_configs()
                    if await asyncio.to_thread(_install_busy_now, install, configs):
                        logger.info(
                            f"MAA 资源更新: 安装被占用或未满足接管条件，跳过 {install}"
                        )
                        continue
                    # 进程扫描让出事件循环，期间开关/CDK 可能变化；派发写线程
                    # 前再采集一次配置，已经关闭接管的安装不能沿用下载前的目标。
                    configs = _snapshot_maa_configs()
                    install_key = _path_key(install)
                    if install_key not in {
                        _path_key(raw) for raw, _ in configs
                    } or install_key in _locked_install_keys(configs):
                        logger.info(
                            f"MAA 资源更新: 接管条件或配置占用发生变化，跳过 {install}"
                        )
                        continue
                    applied = await _run_write_thread(
                        _apply_stage, install, stage_clock, cdk
                    )
            if not applied:
                logger.info(f"MAA 资源更新: 合并前版本已变化，跳过 {install}")
                continue
            done += 1
            logger.info(
                f"MAA 资源更新: {install} 已更新至 {_format_clock(stage_clock)}"
            )
            await _report(progress, f"资源分发进度 {done}/{len(candidates)}…")
        except Exception as e:
            failed += 1
            logger.warning(
                f"MAA 资源更新: {install} 更新失败（不影响其他实例与任务）: {e}"
            )
    if failed:
        await _report(
            progress,
            f"资源更新完成 {done}/{len(candidates)}，失败实例下轮自愈"
            if done
            else "资源更新失败，将在下轮任务前重试",
        )
    elif done:
        await _report(progress, f"资源已更新至 {_format_clock(stage_clock)}")
    else:
        await _report(progress, "本轮未完成分发，剩余实例下轮自愈")


async def _sweep(progress: _Progress | None = None, cdk: str = "") -> None:
    pairs = await asyncio.to_thread(_snapshot_installs, _snapshot_maa_configs())
    if not pairs:
        return
    clocks = dict(pairs)
    await _report(progress, "检查 MAA 资源更新…")
    state = load_state(_STATE_FILE)
    stage = await _run_write_thread(_load_valid_manifest)
    target = await _query_resource_version(clocks=clocks, stage=stage, state=state)
    stage = await _refresh_resource_stage(
        clocks=clocks,
        stage=stage,
        target=target,
        state=state,
        progress=progress,
        cdk=cdk,
    )
    await _distribute_resource_stage(
        clocks=clocks, stage=stage, progress=progress, cdk=cdk
    )


async def _run_update(cdk: str) -> None:
    try:
        with _MachineLock() as lock:
            if lock is None:
                # 仍须经过 MaaManager 的安装访问锁：允许跳过重复下载，
                # 不允许在另一个 MAS 正在写本安装时启动 MAA。
                return
            await _sweep(_broadcast_progress, cdk)
    except ConfigCorruptedError as e:
        logger.opt(exception=True).error(
            f"MAA 资源更新已停止：资源版本文件损坏：{e.path}"
        )
        await _broadcast_progress(f"MAA 资源更新已停止：请检查损坏的版本文件 {e.path}")
    except Exception:
        logger.exception("MAA 资源自动更新异常（已忽略，不影响本轮任务）")


async def prepare_queue_resources(
    progress: _Progress | None = None, *, cdk: str | None = None
) -> None:
    """MAA 任务运行前按需更新全部启用接管脚本的 MAA 实例资源。

    由 MaaManager._run_main_task 在维护判断与锁定配置之前调用：lock() 之后本安装会被
    占用过滤跳过，更新不到它自己。

    Args:
        progress: 可选的阶段级进度回调，入参为单行文本（如「检查 MAA 资源
            更新…」「分发资源更新到 3 个实例…」），可直接写进调度台日志；
            回调异常只影响展示，不影响更新流程。同一 MAS 的并行任务共享
            更新与进度，更新结束后才各自启动 MAA。
        cdk: 触发脚本解析出的生效 Mirror 酱 CDK（脚本优先、空回退全局）；
            为 None 表示该脚本未开启更新接管，不创建更新任务。

    更新失败不阻断任务；主动取消正常传播。最后一个等待者取消时中止更新，
    正在写入的线程结束后才释放机器锁。
    只有开启「更新接管」的脚本触发时才更新，且只分发到同样开启接管的
    安装；已开始的更新仍需等待收尾，避免 MAA 启动与尚未结束的写入交错。
    """
    global _update_task

    if cdk is None:
        return
    task = _update_task
    token = object()
    _update_waiters[token] = progress
    # 注册与建任务之间没有 await，并行 prepare 只会创建一轮更新。
    try:
        # 上一轮最后一个等待者刚中止时，新任务先等写入收尾，再开新一轮；
        # 不能加入那轮已取消的任务，也不能在它仍占锁时直接跳过更新。
        while task is not None and task.cancelling() and not task.done():
            await asyncio.wait({task})
            task = _update_task
        if task is None or task.done():
            task = asyncio.create_task(_run_update(cdk), name="maa-resource-update")
            _update_task = task
        await asyncio.shield(task)
    except asyncio.CancelledError:
        _update_waiters.pop(token, None)
        if not _update_waiters and task is not None and not task.done():
            task.cancel()
            await _wait_for_cleanup(task)
        raise
    finally:
        _update_waiters.pop(token, None)
