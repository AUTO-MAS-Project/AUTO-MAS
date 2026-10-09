#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.
#
#   Contact: DLmaster_361@163.com


"""MAA 本体自动更新：Mirror 酱检查下载（MAS 领域）+ 驱动上游官方安装链。

上游 MAA 自带完整的检查-下载-安装链，但下载要求用户在 MAA 内自配 Mirror 酱
CDK（加密私有字段，MAS 不可读写），且无人值守的托管会话里由 MAA 自行下载
会与任务窗口、资源更新互相争抢。本模块按黑箱边界的「驱动」模式接入（见
mas-script-specialized-adapter/references/blackbox-boundary.md）：自动代理
开始时预检查并按当前安装的通道下载完整包进 MAS 共享缓存（下载编排属 MAS
领域，用 MAS 自己的全局 CDK，一个通道架构只留一份，多个安装目录复用），
在原有 update_maa() 调用点前把包复制进安装目录并登记 Update.Name/
Update.UpdatePackage——与上游自家 Mirror 酱下载器和拖拽导入写的是同一组
字段——安装完全由 MAA 官方更新器执行（Bootstrapper 启动应用 → MaaUpdater
换血，上游 PendingUpdateApplier.cs / main.cpp），执行与成败判定全程归上游。

这不是临时补位：上游没有缺失被 MAS 代劳的领域能力，安装机制本就是上游
自己的入口，唯一的自建部分（检查与下载）属 MAS 领域，作为常驻编排存在
（对比：资源更新 #1135 是真补位——上游没有任何程序化资源导入入口）。
上游契约依赖点：登记字段生效依赖 gui.new.json 的 Update 组与上游启动应用
流程；上游若变更该机制，失效表现为「更新不再发生」，不影响任务执行、
不会误判成功。上游未来若提供程序化更新入口（CLI 参数或配置字段），应改用
该入口并删除本模块的字段写入路径。

更新通道：MAA 配置的偏好优先（gui.new.json 的 Update.VersionType / 旧
gui.json 的 Global.VersionUpdate.VersionType），配置未表达时按实际安装
版本通道兜底。Mirror 酱高通道会回落低通道版本（beta/alpha 通道返回正式
版），若跟随实际安装通道，beta 用户会在第一次「正式版超过最新 beta」的
更新后永久漂移进正式版轨道，因此配置表达了偏好就必须跟随；响应版本与
请求通道不一致不拦截（回落是预期行为），「不降级」由版本比较守卫。

合规边界：不读取/解密 MAA 配置内的 MirrorChyanCdk；版本信号只用 MAA.dll 的
版本资源与 PE 头（不执行任何被检测文件）；通道偏好读上游配置字段（值经手
语义不过手）；登记只写上游配置字段；安装成败取上游结果面
（pending-update-*.txt 标志文件、安装目录实际版本），不自建判定。

失败语义：检查、下载或登记失败只写日志，不影响用户任务；主动取消正常
传播。每日下载记账、查询地板与失败退避对齐 resource_update（Mirror 酱按
CDK 计下载次数，alpha 通道每天出新版，不设限额会稳定消耗额度）。

只支持 Mirror 酱完整包：查询不带 current_version（无增量基线，服务端只回
完整包，对齐上游修复路径语义），响应 update_type 非 full 或包内含 OTA 清单
一律拒收——上游启动应用路径不校验包基准版本，本模块的拒收是唯一防线。

下载与落盘校验全部走异步流式/线程，不阻塞 MAS 主事件循环。
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import sys
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

from app.core import Config
from app.services.update_transport import download_file, request_mirror_resource
from app.utils import get_logger
from app.utils.io import read_dict_file, write_file

# 同包族内复用既有原语，避免第二套实现：启用条件、反滥用识别码、进程扫描
# 与路径归一化与资源更新保持同一事实源，状态记账原语在 update_state。下划线
# 名限定在同一 tools 包族内使用。
from .resource_update import (
    _path_key,
    _resolve_source,
    _running_maa_exe_paths,
    _sp_id,
)
from .software_package import (
    cache_zip_matches,
    load_cache_manifest,
    register_pending_update,
    software_cache_dir,
    store_cache,
    validate_software_zip,
)
from .update_state import attempted_today, backoff_active, load_state, parse_iso

logger = get_logger("MAA 本体更新")

_MIRROR_RESOURCE_ID = "MAA"

_WORK_DIR = Path.cwd() / "data" / "maa_update" / "software"
_STATE_FILE = _WORK_DIR / "state.json"

_QUERY_TIMEOUT = 10  # 秒
_DOWNLOAD_TIMEOUT = 30 * 60  # 秒，完整包远大于资源包，放宽总时限
_QUERY_FLOOR = 10 * 60  # 秒，两次成功查询最小间隔
_RETRY_INTERVAL = 60 * 60  # 秒，失败退避
_PRECHECK_GRACE = 60  # 秒，收尾等待预检查下载收尾的上限，超时本轮跳过

# 通道映射对齐上游 GetUpdateChannel：Stable/Beta/Nightly → stable/beta/alpha
_CHANNEL_BOOK = {"beta": "beta", "alpha": "alpha", "nightly": "alpha"}
# PE 头 Machine 域 → 官方包命名中的架构段（MAA-vX-win-{arch}.zip）
_PE_MACHINE_BOOK = {0x8664: "x64", 0xAA64: "arm64"}

# 宽松 SemVer：可选 v 前缀、三段核心、可选连字符预发布与 + 构建（构建不参与比较）
_VERSION_RE = re.compile(
    r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$"
)


class _UpdateError(RuntimeError):
    """版本查询失败（进固定 1 小时退避）。"""


# --------------------------------------------------------------------------
# 版本与通道
# --------------------------------------------------------------------------


class _Version(NamedTuple):
    core: tuple[int, int, int]
    prerelease: tuple[str, ...]  # 空元组 = 正式版


def parse_version(raw: str) -> _Version | None:
    """解析版本串；不符合宽松 SemVer（含 Nightly 未知形态）返回 None。"""
    match = _VERSION_RE.match(raw.strip())
    if match is None:
        return None
    core = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    prerelease = tuple(match.group(4).split(".")) if match.group(4) else ()
    return _Version(core=core, prerelease=prerelease)


def _identifier_order(identifier: str) -> tuple[int, int | str]:
    """SemVer 预发布标识排序键：纯数字按数值且小于字母标识。"""
    return (0, int(identifier)) if identifier.isdigit() else (1, identifier)


def compare_versions(left: _Version, right: _Version) -> int:
    """按 SemVer 2.0 优先级比较，返回 -1/0/1。预发布规则确定性可比较，
    不做字符串大小比较。"""
    if left.core != right.core:
        return -1 if left.core < right.core else 1
    if left.prerelease != right.prerelease:
        if not left.prerelease:
            return 1
        if not right.prerelease:
            return -1
        for a, b in zip(left.prerelease, right.prerelease):
            ka, kb = _identifier_order(a), _identifier_order(b)
            if ka != kb:
                return -1 if ka < kb else 1
        return -1 if len(left.prerelease) < len(right.prerelease) else 1
    return 0


def detect_channel(version_text: str) -> str | None:
    """从版本串推导更新通道；无法识别的预发布形态一律返回 None（不猜）。"""
    parsed = parse_version(version_text)
    if parsed is None:
        return None
    if not parsed.prerelease:
        return "stable"
    return _CHANNEL_BOOK.get(parsed.prerelease[0].lower())


# --------------------------------------------------------------------------
# 安装信息识别（只读文件元数据，不执行任何 DLL）
# --------------------------------------------------------------------------


def _read_file_product_version(path: Path) -> str | None:
    """读 PE 版本资源字符串表的 ProductVersion（即 .NET 的
    AssemblyInformationalVersion，含 Beta/Nightly 后缀）。"""
    try:
        import ctypes

        version = ctypes.windll.version
        size = version.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return None
        data = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(str(path), 0, size, data):
            return None
        pointer = ctypes.c_void_p()
        length = ctypes.c_uint()
        if (
            not version.VerQueryValueW(
                data,
                "\\VarFileInfo\\Translation",
                ctypes.byref(pointer),
                ctypes.byref(length),
            )
            or length.value < 4
        ):
            return None
        lang, codepage = ctypes.cast(
            pointer, ctypes.POINTER(ctypes.c_uint16 * 2)
        ).contents
        key = f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\ProductVersion"
        if not version.VerQueryValueW(
            data, key, ctypes.byref(pointer), ctypes.byref(length)
        ):
            return None
        text = ctypes.wstring_at(pointer.value, max(length.value - 1, 0)).strip()
        return text or None
    except Exception:
        return None


def _read_pe_machine(path: Path) -> str | None:
    """读 PE 头 Machine 域判定架构；MAA 可能以 x64 模拟运行于 ARM64 Windows，
    用 MAS 进程的 platform.machine() 会误判，必须看目标文件本身。"""
    try:
        with path.open("rb") as fh:
            dos = fh.read(64)
            if len(dos) < 64 or dos[:2] != b"MZ":
                return None
            fh.seek(int.from_bytes(dos[60:64], "little"))
            pe = fh.read(6)
        if len(pe) < 6 or pe[:4] != b"PE\x00\x00":
            return None
        return _PE_MACHINE_BOOK.get(int.from_bytes(pe[4:6], "little"))
    except OSError:
        return None


def read_installed_release(maa_root: Path) -> tuple[str, str] | None:
    """读 MAA 安装目录的实际版本与架构，返回 (版本串, 架构)。

    版本取 MAA.dll 的版本资源——上游 CI 用原生启动器顶替 MAA.exe，版本后缀
    只在托管程序集 MAA.dll 上；架构读同一文件的 PE 头。任何一环无法可靠
    确认都返回 None：不允许拿猜测的版本/架构去挑安装包。
    （更新通道不在这里推导：MAA 配置里的偏好优先，见 resolve_update_channel。）
    """
    if sys.platform != "win32":
        return None
    dll = maa_root / "MAA.dll"
    if not dll.is_file():
        logger.info(f"MAA 本体更新: 未找到 {dll}，无法识别安装信息")
        return None
    version_text = _read_file_product_version(dll)
    arch = _read_pe_machine(dll)
    if version_text is None or arch is None:
        logger.info(
            f"MAA 本体更新: 无法可靠识别安装信息（版本={version_text!r}, 架构={arch!r}），跳过"
        )
        return None
    return version_text, arch


# 上游 UpdateVersionType 枚举序为 Nightly=0, Beta=1, Stable=2；gui.new.json
# 实测以字符串存储（"Stable"/"Beta"/"Nightly"），旧 gui.json 同为字符串，
# 兼容两种形态
_CONFIG_CHANNEL_BOOK = {
    "stable": "stable",
    "beta": "beta",
    "nightly": "alpha",
    "alpha": "alpha",
}
_CONFIG_VERSION_TYPE_INT_BOOK = {0: "Nightly", 1: "Beta", 2: "Stable"}


def read_config_channel(config_dir: Path) -> str | None:
    """读 MAA 配置里表达的更新通道偏好；未表达或无法识别返回 None。

    新版 gui.new.json 的 Update.VersionType 与旧版 gui.json 的
    Global.VersionUpdate.VersionType 均为字符串（兼容整数形态）。
    配置存在但损坏时告警并按未表达处理——这里读的是可选偏好，不是守卫，
    回落到实际安装通道不构成误判。
    """
    for path, section, key in (
        (config_dir / "gui.new.json", "Update", "VersionType"),
        (config_dir / "gui.json", "Global", "VersionUpdate.VersionType"),
    ):
        if not path.is_file():
            continue
        try:
            # read_dict_file 对非映射根节点响亮失败（#877 教训），此处捕获
            # 后告警并按未表达处理——读的是可选偏好，不是守卫
            data = read_dict_file(path)
        except Exception as e:
            logger.warning(f"MAA 本体更新: 配置文件无法解析，跳过通道读取 {path}: {e}")
            continue
        section_data = data.get(section)
        original = section_data.get(key) if isinstance(section_data, dict) else None
        if original is None or original == "":
            continue
        raw = original
        if isinstance(raw, int) and not isinstance(raw, bool):
            raw = _CONFIG_VERSION_TYPE_INT_BOOK.get(raw)
        channel = (
            _CONFIG_CHANNEL_BOOK.get(raw.strip().lower())
            if isinstance(raw, str)
            else None
        )
        if channel is not None:
            return channel
        # bool 会被 int 误映射（True == 1），与未知值一并告警
        logger.warning(f"MAA 本体更新: 无法识别的更新通道配置 {path} → {original!r}")
    return None


def resolve_update_channel(
    version_text: str, config_dirs: Sequence[Path | None]
) -> str | None:
    """解析更新通道：MAA 配置的偏好优先，配置未表达时按实际安装版本兜底。

    Mirror 酱高通道会回落低通道版本（beta/alpha 通道返回正式版），跟随
    实际安装通道会让 beta 用户在第一次「正式版超过最新 beta」的更新后永久
    漂移进正式版轨道，因此配置表达了偏好就必须跟随。版本串推导只作兜底。
    """
    for config_dir in config_dirs:
        if config_dir is None:
            continue
        channel = read_config_channel(config_dir)
        if channel is not None:
            return channel
    return detect_channel(version_text)


def software_update_enabled() -> bool:
    """MAS 更新源为 Mirror 酱且已填 CDK 时启用本体更新接管。"""
    return _resolve_source() is not None


# --------------------------------------------------------------------------
# 状态（每日下载记账 + 退避；损坏按无状态处理，靠重查重下自愈）。
# 记账原语（load_state/parse_iso/backoff_active/attempted_today）在
# update_state，与资源更新共用。不同缓存键（通道/架构）的预检查任务可能
# 并发，状态文件的读-改-写必须持 _state_lock：下载预算按键记账，否则双
# 通道会互相挤占或重复消耗 CDK 额度。
# --------------------------------------------------------------------------

_state_lock = asyncio.Lock()


# --------------------------------------------------------------------------
# Mirror 酱检查与缓存
# --------------------------------------------------------------------------


class _Latest(NamedTuple):
    version: str
    url: str


async def _fetch_latest(channel: str, arch: str) -> _Latest:
    """按通道架构查询最新完整包。不带 current_version：无增量基线，服务端
    只回完整包（上游修复路径同款语义）。"""
    cdk = _resolve_source()
    if cdk is None:
        raise _UpdateError("MAS 未配置 Mirror 酱 CDK")
    try:
        async with asyncio.timeout(_QUERY_TIMEOUT):
            payload = await request_mirror_resource(
                _MIRROR_RESOURCE_ID,
                params={
                    "cdk": cdk,
                    "channel": channel,
                    "os": "win",
                    "arch": arch,
                    "sp_id": _sp_id(),
                },
                proxy=Config.proxy,
                timeout=_QUERY_TIMEOUT,
            )
    except TimeoutError as e:
        raise _UpdateError("镜像酱版本查询超时") from e
    except Exception as e:
        raise _UpdateError(f"镜像酱版本查询失败: {e}") from e
    data = payload.get("data")
    data = data if isinstance(data, dict) else {}
    version = str(data.get("version_name") or "")
    url = str(data.get("url") or "")
    if not version or not url:
        raise _UpdateError("镜像酱响应缺少版本或下载地址")
    if str(data.get("update_type") or "") != "full":
        raise _UpdateError(
            f"镜像酱未返回完整包（update_type={data.get('update_type')!r}），只支持完整包"
        )
    return _Latest(version=version, url=url)


def _store_verified_cache(
    cache_dir: Path, part: Path, latest: _Latest, channel: str, arch: str
) -> None:
    """下载完成后的落盘校验与入缓存（线程内执行）。"""
    validate_software_zip(part)
    with part.open("rb") as fh:
        sha256 = hashlib.file_digest(fh, "sha256").hexdigest()
    store_cache(
        cache_dir,
        part,
        {
            "version": latest.version,
            "channel": channel,
            "os": "win",
            "arch": arch,
            "package_type": "full",
            "source": "mirrorchyan",
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
        },
        sha256,
    )
    logger.info(f"MAA 本体完整包已缓存: {latest.version}（win/{arch}/{channel}）")


async def _ensure_cache(latest: _Latest, channel: str, arch: str) -> None:
    """确保共享缓存里是目标版本：命中直接复用，否则下载并校验入缓存。

    下载预算按缓存键记账（不同通道架构互不挤占），记账读写持模块锁且锁内
    无网络等待。下载失败在此记账退避并返回，不外抛——查询失败与取包失败
    的退避互不牵连。
    """
    cache_dir = software_cache_dir("win", arch, channel)
    manifest = load_cache_manifest(cache_dir)
    if (
        manifest is not None
        and manifest["version"] == latest.version
        and await asyncio.to_thread(cache_zip_matches, cache_dir, manifest)
    ):
        logger.info(f"MAA 本体更新: 目标版本 {latest.version} 已在缓存，跳过下载")
        return
    cdk = _resolve_source()
    if cdk is None:
        return
    key = _cache_key(arch, channel)
    async with _state_lock:
        state = load_state(_STATE_FILE)
        now = datetime.now(timezone.utc)
        if backoff_active(state, f"download_fail_until/{key}", now):
            logger.info("MAA 本体更新: 取包退避期内，本轮跳过下载")
            return
        if attempted_today(state, f"last_download_attempt_at/{key}", now):
            logger.info(
                "MAA 本体更新: 今日已尝试获取该通道的本体包，明日再试；已有缓存照常使用"
            )
            return
        # 请求前持久记账：失败、取消或进程退出都不能再次消耗当天预算
        state[f"last_download_attempt_at/{key}"] = now.isoformat()
        write_file(_STATE_FILE, state)
    part = cache_dir / "package.zip.part"
    try:
        async with asyncio.timeout(_DOWNLOAD_TIMEOUT):
            await download_file(
                latest.url, part, timeout=_DOWNLOAD_TIMEOUT, proxy=Config.proxy
            )
        await asyncio.to_thread(
            _store_verified_cache, cache_dir, part, latest, channel, arch
        )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        async with _state_lock:
            state = load_state(_STATE_FILE)
            state[f"download_fail_until/{key}"] = (
                datetime.now(timezone.utc) + timedelta(seconds=_RETRY_INTERVAL)
            ).isoformat()
            write_file(_STATE_FILE, state)
        logger.warning(f"MAA 本体更新: 取包失败（退避 1 小时，仍受每日限额约束）: {e}")
    finally:
        part.unlink(missing_ok=True)


# --------------------------------------------------------------------------
# 编排入口
# --------------------------------------------------------------------------


def _cache_key(arch: str, channel: str) -> str:
    return f"win/{arch}/{channel}"


_precheck_tasks: dict[str, asyncio.Task[None]] = {}


async def _precheck_flow(maa_root: Path, channel: str, arch: str) -> None:
    """预检查主体：查询 → 版本判断 → 取包入缓存。失败语义见各调用。"""
    try:
        await _precheck_inner(maa_root, channel, arch)
    except asyncio.CancelledError:
        raise
    except _UpdateError as e:
        async with _state_lock:
            state = load_state(_STATE_FILE)
            state["query_fail_until"] = (
                datetime.now(timezone.utc) + timedelta(seconds=_RETRY_INTERVAL)
            ).isoformat()
            write_file(_STATE_FILE, state)
        logger.warning(f"MAA 本体更新: 版本查询失败（1 小时内不再尝试）: {e}")
    except Exception:
        logger.exception("MAA 本体更新: 预检查异常（已忽略，不影响本轮任务）")


async def _precheck_inner(maa_root: Path, channel: str, arch: str) -> None:
    async with _state_lock:
        state = load_state(_STATE_FILE)
        now = datetime.now(timezone.utc)
        if backoff_active(state, "query_fail_until", now):
            logger.info("MAA 本体更新: 查询退避期内，本轮跳过检查")
            return
        last_query = parse_iso(state.get("last_query_at"))
        if last_query is not None and now - last_query < timedelta(
            seconds=_QUERY_FLOOR
        ):
            logger.info("MAA 本体更新: 距上次查询不足 10 分钟，本轮跳过检查")
            return
    latest = await _fetch_latest(channel, arch)
    async with _state_lock:
        state = load_state(_STATE_FILE)
        state["last_query_at"] = datetime.now(timezone.utc).isoformat()
        write_file(_STATE_FILE, state)

    # 高通道回落低通道版本（beta/alpha 返回正式版）是预期行为，不按响应
    # 版本的通道拦截；方向由下面的版本比较守卫（不降级）
    release = read_installed_release(maa_root)
    if release is None:
        return
    current = parse_version(release[0])
    target = parse_version(latest.version)
    if current is None or target is None:
        logger.warning(
            "MAA 本体更新: 版本无法比较"
            f"（当前 {release[0]!r} → 目标 {latest.version!r}），跳过"
        )
        return
    if compare_versions(target, current) <= 0:
        logger.info(f"MAA 本体更新: 已是最新（{release[0]}，{channel} 通道）")
        return
    await _ensure_cache(latest, channel, arch)


def start_maa_software_update_precheck(
    maa_root: Path, *, config_dir: Path | None = None
) -> None:
    """自动代理开始时启动本体更新预检查：检查版本并把完整包预下载进共享
    缓存，供收尾 prepare_maa_software_update 消费。

    同一缓存键的任务进程内去重（多个用户轮次共享一轮检查）；MAS 未启用
    Mirror 酱、安装信息无法识别时不创建任务。本函数不等待网络，任何失败
    只写日志。

    Args:
        maa_root: MAA 安装目录。
        config_dir: 优先读取更新通道偏好的配置目录。会话内应传任务前的
            原生配置快照——安装目录当时的 config 是 MAS 托管副本；缺省时
            读安装目录 config。
    """
    try:
        if not software_update_enabled():
            return
        release = read_installed_release(maa_root)
        if release is None:
            return
        version_text, arch = release
        channel = resolve_update_channel(
            version_text, [config_dir, maa_root / "config"]
        )
        if channel is None:
            logger.info(
                f"MAA 本体更新: 无法识别更新通道（版本={version_text!r}，配置未表达），跳过"
            )
            return
        key = _cache_key(arch, channel)
        existing = _precheck_tasks.get(key)
        if existing is not None and not existing.done():
            return
        _precheck_tasks[key] = asyncio.create_task(
            _precheck_flow(maa_root, channel, arch),
            name=f"maa-software-update-{_path_key(maa_root)}-{key}",
        )
    except Exception as e:
        logger.warning(f"MAA 本体更新: 预检查未能启动（不影响任务）: {e}")


async def prepare_maa_software_update(
    maa_root: Path, *, config_dir: Path | None = None
) -> None:
    """用户轮次收尾、原有 update_maa() 之前调用。

    等待预检查收尾（有上限，超时本轮跳过），复核当前安装仍需要更新后，把
    共享缓存中的完整包复制进安装目录并登记上游待更新字段；安装由未改动的
    update_maa() → MAA 官方更新链完成。任何失败只写日志，不改变 update_maa()
    对既有合法待更新包的处理；主动取消正常传播。

    Args:
        maa_root: MAA 安装目录。
        config_dir: 优先读取更新通道偏好的配置目录，同
            start_maa_software_update_precheck。
    """
    try:
        if not software_update_enabled():
            return
        release = read_installed_release(maa_root)
        if release is None:
            return
        version_text, arch = release
        channel = resolve_update_channel(
            version_text, [config_dir, maa_root / "config"]
        )
        if channel is None:
            return
        key = _cache_key(arch, channel)
        cache_dir = software_cache_dir("win", arch, channel)
        task = _precheck_tasks.get(key)
        if task is not None and not task.done():
            try:
                async with asyncio.timeout(_PRECHECK_GRACE):
                    await asyncio.shield(task)
            except TimeoutError:
                logger.info("MAA 本体更新: 包尚未缓存完成，本轮跳过登记，下轮继续")
                return
        if _precheck_tasks.get(key) is task:
            _precheck_tasks.pop(key, None)
        manifest = load_cache_manifest(cache_dir)
        if manifest is None:
            return
        # 消费前复核缓存内容与清单一致（清理、杀毒删文件等都会造成残缺包）
        if not await asyncio.to_thread(cache_zip_matches, cache_dir, manifest):
            logger.warning("MAA 本体更新: 缓存包与清单不一致，作废缓存等待重建")
            (cache_dir / "manifest.json").unlink(missing_ok=True)
            return
        current = parse_version(version_text)
        target = parse_version(manifest["version"])
        if current is None or target is None or compare_versions(target, current) <= 0:
            return
        # MAA 自有更新器仍在跑时登记，包会在下一轮任务启动 MAA 时被上游
        # 启动应用抢先消费（见 Bootstrapper 启动流程），必须避开
        running = await asyncio.to_thread(_running_maa_exe_paths)
        install_key = _path_key(maa_root)
        if any(exe.startswith(install_key + os.sep) for exe in running):
            logger.warning("MAA 本体更新: 检测到 MAA/更新器进程仍在运行，本轮跳过登记")
            return
        registered = await asyncio.to_thread(
            register_pending_update,
            maa_root,
            version=manifest["version"],
            package_zip=cache_dir / "package.zip",
            package_sha256=manifest["sha256"],
        )
        if registered:
            logger.info(
                f"MAA 本体更新: 已登记 {manifest['version']}，交由 MAA 官方更新器安装"
            )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("MAA 本体更新: 准备异常（已忽略，不影响本轮任务）")
