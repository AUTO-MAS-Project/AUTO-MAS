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
补位：MAA 自动代理任务运行前（MaaManager.prepare 锁定配置之前；配置会话
不触发）按需更新全部 MAA 实例的资源。

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

失败语义：本模块对外的唯一入口 prepare_queue_resources() 永不抛异常；任何
失败只写日志。阶段级进度经可选的 progress 回调上报（回调异常被忽略，见
prepare_queue_resources）。重文件 I/O（进程扫描、解压、合并、逐安装复读
时钟）一律运行在 asyncio.to_thread 内、下载写盘用 aiofiles——MAS 后端是
单事件循环 uvicorn，阻塞 I/O 会冻结整个后端；KB 级状态/清单文件是唯一
例外（与仓库现状一致）。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import aiofiles
import httpx
import psutil

from app.core import Config
from app.models.config import MaaConfig
from app.utils import get_logger
from app.utils.constants import MIRROR_ERROR_INFO
from app.utils.io import ConfigCorruptedError, read_dict_file

from .resource_package import (
    count_zip_entries,
    extract_zip,
    find_package_resource_root,
    merge_package_tree,
)

logger = get_logger("MAA 资源更新")

_MIRROR_LATEST_URL = "https://mirrorchyan.com/api/resources/MaaResource/latest"
_GITHUB_RESOURCE_ZIP = (
    "https://github.com/MaaAssistantArknights/MaaResource/archive/refs/heads/main.zip"
)
_USER_AGENT = "AutoMasGui"
# version.json last_updated 与镜像酱 version_name 的共同口径（UTC）
_CLOCK_FORMAT = "%Y-%m-%d %H:%M:%S.%f"

_QUERY_TIMEOUT = 10              # 秒
_DOWNLOAD_TIMEOUT = 10 * 60      # 秒，单次下载总上限
_DISTRIBUTE_DEADLINE = 15 * 60   # 秒，单轮扫描软上限（查询/下载/解压也消耗预算；下载另有 10 分钟硬上限）
_QUERY_FLOOR = 10 * 60           # 秒，两次成功查询最小间隔（只作用于刷新检查）
_BACKOFF_BASE = 60 * 60          # 秒，下载失败退避基数
_BACKOFF_CAP = 24 * 60 * 60      # 秒，退避封顶
_ORPHAN_TTL = 60 * 60            # 秒，解压孤儿目录的安全清理门槛
_FREE_SPACE_REQUIRED = 300 * 1024 * 1024
_MB = 1024 * 1024
_CHUNK = _MB

# data/ 是每个 MAS 实例私有的（双实例各自一份暂存，双下载已接受）；
# 锁文件放 %LOCALAPPDATA%，同一 Windows 用户的多个 MAS 进程互斥（跨用户
# 会话共享同一 MAA 安装的场景极罕见，且后果只是交错重写、可自愈）。
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
    """下载/校验失败（进指数退避）。"""


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


def _parse_iso(value: object) -> datetime | None:
    """解析本模块自产的 isoformat 状态值，统一补齐 UTC 时区。"""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# 状态（原子写；损坏一律按无状态处理，靠重查/重下自愈）
# --------------------------------------------------------------------------

def _load_state() -> dict[str, object]:
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception:
        logger.warning(f"MAA 资源更新: 状态文件损坏，按无状态处理: {_STATE_FILE}")
        return {}


def _save_state(state: dict[str, object]) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, _STATE_FILE)


def _load_manifest() -> dict[str, object] | None:
    try:
        return json.loads(_MANIFEST_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception:
        logger.warning(f"MAA 资源更新: 暂存清单损坏，按无暂存处理: {_MANIFEST_FILE}")
        return None


def _write_manifest(manifest: dict[str, object]) -> None:
    _MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _MANIFEST_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, _MANIFEST_FILE)


# --------------------------------------------------------------------------
# 枚举与占用（线程内执行：进程扫描与磁盘探测都是阻塞 I/O）
# --------------------------------------------------------------------------

def _path_key(value: Path | str) -> str:
    return os.path.normcase(os.path.normpath(str(Path(value).resolve(strict=False))))


def _locked_install_keys() -> set[str]:
    keys: set[str] = set()
    try:
        entries = list(Config.ScriptConfig.items())
    except Exception:
        return keys
    for _, config in entries:
        try:
            if isinstance(config, MaaConfig) and config.is_locked:
                raw = str(config.get("Info", "Path") or "")
                if raw:
                    keys.add(_path_key(raw))
        except Exception:
            continue
    return keys


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


def _snapshot_installs() -> list[tuple[Path, datetime]]:
    """全部可判定的 MAA 安装及其时钟，按归一化路径去重、逐条容错。

    跳过：被占用（is_locked / MAA 进程运行中）、缺 resource/version.json、
    version.json 损坏（记警告——单个坏文件只跳过该安装，不瘫痪整轮扫描）。
    先收集安装路径再做进程/锁定扫描，零 MAA 安装时不做全进程扫描。
    """
    installs: dict[str, Path] = {}
    try:
        entries = list(Config.ScriptConfig.items())
    except Exception:
        return []
    for _, config in entries:
        try:
            if not isinstance(config, MaaConfig):
                continue
            raw = str(config.get("Info", "Path") or "")
            if raw:
                installs.setdefault(_path_key(raw), Path(raw))
        except Exception:
            continue
    if not installs:
        return []
    locked = _locked_install_keys()
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
            logger.info(f"MAA 资源更新: 跳过缺少 resource/version.json 的安装 {install}")
            continue
        try:
            clock = _read_clock_file(version_file)
        except (OSError, ValueError):
            logger.warning(f"MAA 资源更新: {version_file} 损坏，本轮跳过该安装")
            continue
        result.append((install, clock))
    return result


def _install_busy(install: Path, locked: set[str], running: set[str]) -> bool:
    key = _path_key(install)
    if key in locked:
        return True
    return any(exe.startswith(key + os.sep) for exe in running)


def _install_busy_now(install: Path) -> bool:
    """合并前的单安装占用复查（现取锁定键与进程快照，线程内执行）。"""
    return _install_busy(install, _locked_install_keys(), _running_maa_exe_paths())


# --------------------------------------------------------------------------
# 查询与取包
# --------------------------------------------------------------------------

def _sp_id() -> str:
    """镜像酱反滥用的稳定识别码；无敏感信息。"""
    seed = os.environ.get("COMPUTERNAME", "auto-mas")
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _mirror_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=_QUERY_TIMEOUT, proxy=Config.proxy, follow_redirects=True
    )


async def _fetch_latest_version(current: str) -> datetime:
    """免费版本查询（无 CDK、不带 os/arch），返回目标时钟。

    Raises:
        _QueryError: 网络、响应解析或业务码的任何失败。
    """
    query = urlencode(
        {
            "current_version": current,
            "user_agent": _USER_AGENT,
            "sp_id": _sp_id(),
        }
    )
    try:
        async with _mirror_client() as client:
            resp = await client.get(f"{_MIRROR_LATEST_URL}?{query}")
        payload = resp.json()
    except Exception as e:
        raise _QueryError(f"镜像酱版本查询失败: {e}") from e
    if not isinstance(payload, dict):
        raise _QueryError(f"镜像酱版本查询响应非对象: {type(payload).__name__}")
    code = payload.get("code")
    if not isinstance(code, int) or isinstance(code, bool):
        raise _QueryError(f"响应 code 非整数: {code!r}")
    if code != 0:
        info = MIRROR_ERROR_INFO.get(code, str(payload.get("msg", "")))
        raise _QueryError(f"code={code}: {info}")
    name = None
    if isinstance(payload.get("data"), dict):
        name = payload["data"].get("version_name")
    if not name:
        raise _QueryError("响应缺少 version_name")
    try:
        return _parse_clock(str(name))
    except ValueError as e:
        raise _QueryError(f"version_name 无法解析: {name}") from e


def _resolve_source() -> tuple[str, str | None] | None:
    """按全局设置解析取包方式。None = 本轮不可取包且不退避（Mirror 无 CDK）。"""
    source = Config.get("Update", "Source")
    if source == "MirrorChyan":
        cdk = str(Config.get("Update", "MirrorChyanCDK") or "").strip()
        if not cdk:
            logger.info("MAA 资源更新: 更新源为 Mirror酱 但未填 CDK，本轮跳过（不自动换源）")
            return None
        return "mirror", cdk
    # GitHub / AutoSite / CNB（后两个是 MAS 自有源，对 MAA 资源无意义）→ GitHub 全量
    return "github", None


async def _mirror_download_url(base_clock: datetime, cdk: str) -> str:
    """取增量包下载地址（url 一次性，现查现下，不缓存）。"""
    query = urlencode(
        {
            "current_version": _format_clock(base_clock),
            "cdk": cdk,
            "user_agent": _USER_AGENT,
            "sp_id": _sp_id(),
        }
    )
    try:
        async with _mirror_client() as client:
            resp = await client.get(f"{_MIRROR_LATEST_URL}?{query}")
        payload = resp.json()
    except Exception as e:
        raise _DownloadError(f"镜像酱下载地址获取失败: {e}") from e
    if not isinstance(payload, dict):
        raise _DownloadError(f"镜像酱响应非对象: {type(payload).__name__}")
    code = payload.get("code")
    if not isinstance(code, int) or isinstance(code, bool):
        raise _DownloadError(f"响应 code 非整数: {code!r}")
    if code != 0:
        info = MIRROR_ERROR_INFO.get(code, str(payload.get("msg", "")))
        raise _DownloadError(f"code={code}: {info}")
    url = None
    if isinstance(payload.get("data"), dict):
        url = payload["data"].get("url")
    if not url:
        raise _DownloadError("镜像酱未返回下载地址")
    return str(url)


def _download_line(label: str, downloaded: int, total: int, speed: float) -> str:
    """下载进度行：有 Content-Length 时带 x/y MB，速度按量级选单位。"""
    speed_text = (
        f"{speed / _MB:.1f} MB/s" if speed >= _MB else f"{speed / 1024:.0f} KB/s"
    )
    if total:
        return f"{label} {downloaded / _MB:.1f}/{total / _MB:.1f} MB（{speed_text}）…"
    return f"{label} {downloaded / _MB:.1f} MB（{speed_text}）…"


async def _stream_download(
    url: str, dest: Path, progress: _Progress | None, label: str
) -> None:
    async def _run() -> None:
        client = httpx.AsyncClient(
            timeout=_DOWNLOAD_TIMEOUT, proxy=Config.proxy, follow_redirects=True
        )
        async with client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                # 总量只用于进度展示：坏代理可能给非数字头，解析失败按未知处理；
                # Content-Length 是压缩口径而 aiter_bytes 产出解码后字节，经压缩
                # CDN 时可能显示 x>y（同 update.py 先例，仅文案影响）
                try:
                    total = int(resp.headers.get("content-length") or 0)
                except ValueError:
                    total = 0
                # 连接建立即上报一次（0 进度），让进度行立刻出现；其后每秒
                # 至多一次，速度按滑动 1 秒窗口计算（同 update.py 先例）
                await _report(progress, _download_line(label, 0, total, 0.0))
                downloaded = 0
                window_bytes = 0
                window_start = time.monotonic()
                async with aiofiles.open(dest, "wb") as fh:
                    async for chunk in resp.aiter_bytes(_CHUNK):
                        await fh.write(chunk)
                        downloaded += len(chunk)
                        window_bytes += len(chunk)
                        now = time.monotonic()
                        if now - window_start >= 1.0:
                            speed = window_bytes / (now - window_start)
                            await _report(
                                progress,
                                _download_line(label, downloaded, total, speed),
                            )
                            window_bytes = 0
                            window_start = now

    try:
        await asyncio.wait_for(_run(), timeout=_DOWNLOAD_TIMEOUT)
    except asyncio.TimeoutError as e:
        raise _DownloadError("下载超时") from e
    except Exception as e:
        raise _DownloadError(f"资源包下载失败: {e}") from e


def _build_stage(
    zip_path: Path, target: datetime, base_clock: datetime | None, full: bool
) -> None:
    """解压 → 校验 → 单调把关 → 换位 → 核账 → manifest。线程内执行；任何
    失败都抛 _DownloadError（进下载退避）。

    暂存保持安装目录形态（resource/ 在 _STAGE_DIR 下），消费方才能用
    read_resource_clock / merge_package_tree 以同一形态读写。解压目录名带
    pid + 单调量：任务取消会让本函数的线程孤儿化继续执行，同进程的下一轮
    sweep 用新目录，不与孤儿互相覆盖。换位顺序是关键不变式：

    1. 动旧暂存**之前**先删 manifest——半途死掉时盘上「无 manifest」，
       下一轮按无暂存重建，绝不会拿旧 manifest 去分发半删的树；
    2. 换位后按 zip 条目数核账——残缺树（并发清理、AV 删文件）即使带着
       合法 version.json 也会在这里被拒，防止「缺文件但时钟已 bump」
       这种哈希比对永远救不回的静默损坏被分发。
    """
    stage_tmp = _WORK_DIR / f"stage.tmp.{os.getpid()}.{time.monotonic_ns()}"
    # 只清理足够老的孤儿目录：1 小时 TTL 远大于正常解压时长，正常构建
    # 绝不会被误删；病态超长解压被误删的残余由换位核账兜住
    if _WORK_DIR.is_dir():
        cutoff = time.time() - _ORPHAN_TTL
        for leftover in _WORK_DIR.glob("stage.tmp.*"):
            if leftover == stage_tmp:
                continue
            try:
                if leftover.stat().st_mtime < cutoff:
                    shutil.rmtree(leftover, ignore_errors=True)
            except OSError:
                continue
    try:
        extract_zip(zip_path, stage_tmp)
        root = find_package_resource_root(stage_tmp)
        if root is None:
            raise _DownloadError(
                "资源包内未找到 resource 目录（预期 MaaResource-main/resource 或 resource）"
            )
        new_clock = _read_clock_file(root / "version.json")
        # 全量包只要求不旧于查询目标：GitHub HEAD 与镜像酱 version_name 由
        # 两个主体独立推进，镜像酱同步滞后的窗口里 GitHub 包可能更新鲜，
        # 恒等校验会把整包误杀；差分包是按 target 精确构造的，必须恒等。
        if new_clock < target or (not full and new_clock != target):
            raise _DownloadError(
                f"资源包版本({_format_clock(new_clock)})与查询目标({_format_clock(target)})"
                "不一致，疑似缓存滞后"
            )
        old_clock_file = _STAGE_DIR / "resource" / "version.json"
        if old_clock_file.is_file():
            try:
                old_clock = _read_clock_file(old_clock_file)
            except (OSError, ValueError):
                old_clock = None
            if old_clock is not None and new_clock < old_clock:
                raise _DownloadError(
                    f"资源包版本({_format_clock(new_clock)})旧于现有暂存"
                    f"({_format_clock(old_clock)})，拒绝替换"
                )
        expected = count_zip_entries(zip_path, root.relative_to(stage_tmp).as_posix())
        _MANIFEST_FILE.unlink(missing_ok=True)
        if _STAGE_DIR.exists():
            # 先原子改名再删：rmtree 数千文件有数秒级「半删树」窗口，
            # 会与取消遗留的孤儿线程交错出「混树 + 新时钟」；rename 一次
            # 完成，退休目录走孤儿清理（TTL 后被 glob 收走）。名字由本次
            # 唯一的 stage_tmp 派生，不依赖单调钟刻度（Windows 粒度 ~15ms）
            retired = _WORK_DIR / f"{stage_tmp.name}.old"
            os.rename(_STAGE_DIR, retired)
            shutil.rmtree(retired, ignore_errors=True)
        _STAGE_DIR.mkdir(parents=True)
        shutil.move(str(root), str(_STAGE_DIR / "resource"))
        shutil.rmtree(stage_tmp, ignore_errors=True)
        actual = sum(1 for p in (_STAGE_DIR / "resource").rglob("*") if p.is_file())
        if actual != expected:
            raise _DownloadError(f"暂存树不完整（{actual}/{expected} 个文件），拒绝提交")
        # manifest 最后写：它是暂存自身的提交标记，半途失败视为无暂存
        _write_manifest(
            {
                "target": target.isoformat(),
                "from_clock": None
                if full
                else (base_clock.isoformat() if base_clock is not None else None),
                "full": full,
            }
        )
    except _DownloadError:
        raise
    except Exception as e:
        raise _DownloadError(f"暂存重建失败: {e}") from e


async def _refresh_stage(
    base_clock: datetime | None, target: datetime, progress: _Progress | None = None
) -> bool:
    """取包并重建暂存。返回 False = 按设置本轮不可取包（无退避）；失败抛
    _DownloadError。"""
    try:
        if shutil.disk_usage(_WORK_DIR.anchor).free < _FREE_SPACE_REQUIRED:
            raise _DownloadError("磁盘剩余空间不足（需约 300MB）")
    except OSError as e:
        raise _DownloadError(f"磁盘余量检查失败: {e}") from e
    resolved = _resolve_source()
    if resolved is None:
        return False
    kind, cdk = resolved
    if kind == "github":
        url = _GITHUB_RESOURCE_ZIP
        label = "下载 GitHub 全量资源包"
    else:
        url = await _mirror_download_url(base_clock, cdk)
        label = "下载 Mirror酱 增量资源包"
    await _stream_download(url, _STAGE_ZIP, progress, label)
    await _report(progress, "校验并暂存资源包…")
    await asyncio.to_thread(_build_stage, _STAGE_ZIP, target, base_clock, kind == "github")
    # zip 是可弃缓存，删不掉（AV 隔离等）也无妨——下次下载按 "wb" 截断重写
    with suppress(OSError):
        _STAGE_ZIP.unlink(missing_ok=True)
    return True


# --------------------------------------------------------------------------
# 机器级锁（双 MAS 实例共存；进程死亡由 OS 释放）
# --------------------------------------------------------------------------

class _MachineLock:
    def __init__(self) -> None:
        self._fh = None

    def __enter__(self) -> "_MachineLock | None":
        try:
            _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(_LOCK_FILE, "a+b")
            self._fh.seek(0, 2)
            if self._fh.tell() == 0:
                self._fh.write(b"\0")
                self._fh.flush()
            self._fh.seek(0)
            import msvcrt

            msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            return self
        except ImportError:
            return self          # 非 Windows：无锁运行（MAS 仅发 Windows，此处只为不崩溃）
        except OSError as e:
            if self._fh is None:
                # 连锁文件都建不了：环境异常，明说并跳过，不与「被他人持有」混淆
                logger.warning(f"MAA 资源更新: 机器锁不可用（本轮跳过）: {e}")
            else:
                # 锁被其他 MAS 实例持有：正常现象，不刷日志
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


# --------------------------------------------------------------------------
# 编排入口
# --------------------------------------------------------------------------

def _backoff_active(state: dict[str, object], key: str, now: datetime) -> bool:
    until = _parse_iso(state.get(key))
    return until is not None and now < until


def _stage_reusable(
    stage: dict[str, object] | None, target: datetime, min_clock: datetime | None
) -> bool:
    """暂存可复用 = 目标一致，且（全量包，或增量包恰好从当前最旧落后钟起算）。

    增量包按上游协议是「from_clock → target 的差分」，只有 from_clock 恰为
    当前最旧落后钟时才能覆盖全部落后实例；出现更旧的实例就得重建。
    """
    if stage is None or _parse_iso(stage.get("target")) != target:
        return False
    if bool(stage.get("full")):
        return True
    return min_clock is not None and _parse_iso(stage.get("from_clock")) == min_clock


def _stage_applies(stage: dict[str, object], clock: datetime) -> bool:
    """增量差分只安全作用于时钟恰为 from_clock 的实例（文件级差分对中间
    版本可能漏「改了又改回」的文件）；全量包对任何落后实例安全。
    实测镜像酱增量包若经真 CDK 验证为全量快照，可放宽为 from_clock <= clock。"""
    if bool(stage.get("full")):
        return True
    return _parse_iso(stage.get("from_clock")) == clock


def _apply_stage(install: Path, stage_clock: datetime) -> None:
    """线程体：合并 + 重读验证。提交文件最后写，时钟必须到位才算成功。"""
    merge_package_tree(_STAGE_DIR / "resource", install / "resource")
    done = read_resource_clock(install)
    if done is None or done < stage_clock:
        raise RuntimeError(f"合并后时钟为 {done}，期望 {stage_clock}")


_Progress = Callable[[str], Awaitable[None]]


async def _report(progress: _Progress | None, line: str) -> None:
    """阶段级进度上报：回调异常只影响展示，绝不影响更新流程。"""
    if progress is None:
        return
    try:
        await progress(line)
    except Exception:
        logger.debug("MAA 资源更新: 进度回调失败（不影响更新流程）")


async def _sweep(progress: _Progress | None = None) -> None:
    deadline = time.monotonic() + _DISTRIBUTE_DEADLINE
    pairs = await asyncio.to_thread(_snapshot_installs)
    if not pairs:
        return
    clocks = dict(pairs)
    await _report(progress, "检查 MAA 资源更新…")

    state: dict[str, object] = _load_state()
    now = datetime.now(timezone.utc)
    stage = _load_manifest()

    # 1. 查询（地板 + 固定退避只作用于刷新检查；判定/分发照做）
    target: datetime | None = None
    last_query = _parse_iso(state.get("last_query_at"))
    query_blocked = _backoff_active(state, "query_fail_until", now) or (
        last_query is not None and now - last_query < timedelta(seconds=_QUERY_FLOOR)
    )
    if not query_blocked:
        stage_target = _parse_iso(stage.get("target")) if stage else None
        if stage_target is not None:
            current = _format_clock(stage_target)
        else:
            # 无暂存时送最旧实例的真实时钟（与上游「报本地版本」同口径），
            # 不用 epoch 哨兵——镜像酱对极旧 current_version 的行为未实测
            current = _format_clock(min(clocks.values()))
        try:
            target = await _fetch_latest_version(current)
            state["last_query_at"] = now.isoformat()
            _save_state(state)
        except _QueryError as e:
            state["query_fail_until"] = (now + timedelta(hours=1)).isoformat()
            _save_state(state)
            logger.warning(f"MAA 资源更新: 版本查询失败（1 小时内不再尝试）: {e}")

    # 2. 刷新检查（下载退避命中则跳过刷新；判定/分发不受影响）
    if target is not None:
        behind = {i: c for i, c in clocks.items() if c < target}
        min_clock = min(behind.values(), default=None)
        if behind and not _stage_reusable(stage, target, min_clock) and not _backoff_active(
            state, "download_fail_until", now
        ):
            await _report(progress, f"发现新版本 {_format_clock(target)}，下载资源包…")
            try:
                refreshed = await _refresh_stage(min_clock, target, progress)
                if refreshed:
                    state["download_fail_streak"] = 0   # 成功即复位退避连击
                    _save_state(state)
                else:
                    await _report(progress, "更新源为 Mirror酱 且未填 CDK，跳过资源更新")
                stage = _load_manifest()
            except _DownloadError as e:
                try:
                    streak = int(state.get("download_fail_streak") or 0) + 1
                except (TypeError, ValueError):
                    streak = 1
                delay = min(_BACKOFF_BASE * (2 ** (streak - 1)), _BACKOFF_CAP)
                state["download_fail_streak"] = streak
                state["download_fail_until"] = (
                    now + timedelta(seconds=delay)
                ).isoformat()
                _save_state(state)
                logger.warning(f"MAA 资源更新: 取包失败（退避 {delay} 秒）: {e}")
                await _report(progress, f"资源包下载失败（{delay // 3600} 小时后重试）")
                # 换位失败可能已把盘上 manifest 作废，按盘上现状决定本轮
                # 是否仍分发旧暂存，不沿用内存里的旧值
                stage = _load_manifest()

    # 3. 以暂存为镜判定并分发（判定比暂存不比远端，地板期/失败期照常）
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

    # 先筛出本轮真正要写的实例。合并前逐安装复查占用：快照之后可能过了
    # 最长 10 分钟的下载期，前面的合并也要跑分钟级，中途拉起的 MAA /
    # 新锁定的脚本不该被写入
    candidates: list[Path] = []
    for install, clock in clocks.items():
        if time.monotonic() > deadline:
            logger.warning("MAA 资源更新: 达到单轮时限，剩余实例交由下一轮自愈")
            break
        if clock >= stage_clock:
            continue
        if await asyncio.to_thread(_install_busy_now, install):
            logger.info(f"MAA 资源更新: 分发前复查到占用，跳过 {install}")
            continue
        if not _stage_applies(stage, clock):
            continue
        candidates.append(install)

    if not candidates:
        return
    await _report(progress, f"分发资源更新到 {len(candidates)} 个实例…")
    done = failed = 0
    for install in candidates:
        if time.monotonic() > deadline:
            logger.warning("MAA 资源更新: 达到单轮时限，剩余实例交由下一轮自愈")
            break
        # 筛选后的占用快照可能已过期（前面的合并可达分钟级），合并前再查一次
        if await asyncio.to_thread(_install_busy_now, install):
            logger.info(f"MAA 资源更新: 合并前复查到占用，跳过 {install}")
            continue
        try:
            await asyncio.to_thread(_apply_stage, install, stage_clock)
            done += 1
            logger.info(f"MAA 资源更新: {install} 已更新至 {_format_clock(stage_clock)}")
            await _report(progress, f"资源分发进度 {done}/{len(candidates)}…")
        except Exception as e:
            failed += 1
            logger.warning(f"MAA 资源更新: {install} 更新失败（不影响其他实例与任务）: {e}")
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


async def prepare_queue_resources(progress: _Progress | None = None) -> None:
    """MAA 任务运行前按需更新全部 MAA 实例资源。

    必须在 MaaManager.prepare 锁定脚本配置之前调用：lock() 之后本安装会被
    占用过滤跳过，更新不到它自己。

    Args:
        progress: 可选的阶段级进度回调，入参为单行文本（如「检查 MAA 资源
            更新…」「分发资源更新到 3 个实例…」），可直接写进调度台日志；
            回调异常只影响展示，不影响更新流程。忙（锁被其他实例持有）与
            零可更新实例时不回调。

    契约：永不抛异常；任何失败只写日志并进入退避；调用方无需 try/except。
    """
    try:
        with _MachineLock() as lock:
            if lock is None:
                return
            await _sweep(progress)
    except Exception:
        logger.exception("MAA 资源自动更新异常（已忽略，不影响本轮任务）")
