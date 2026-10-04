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

"""官方模拟器一条安装的设备管理器。

对门面暴露的方法与雷电 / MuMu 两家后端相同（``open`` / ``close`` / ``getStatus`` /
``getInfo`` / ``list_devices`` / 四项设置 / 稳定模式 / 新建删除实例），区别在于这里没有厂商
管理器可调，每一步都是自己驱动 ``emulator.exe`` 与私有 adb。

启动 = 冷启动（``-no-snapshot``，与 MAS 对雷电 / MuMu 每轮开关一致，预研 §6.16），默认无头
（= 静默模式，预研 §6.14）。启动参数与开机后的调优逐项照 aemu-lab 的启动器 ``avd-p0.ps1``
（每个开关都真机验证过，原因写在对应函数里）：磁盘 write-through、静音、显示两档、实例内存、
空闲页上报、GuestAngle、宿主调度、截图共享内存、cpuinfo、WiFi + fastpath、客体日志落盘。
首次开机后再做一次持久初始化（关蓝牙、去全屏提示、禁用手机预装应用、换轻量桌面、记录渲染器）。

关机先 ``sync`` 再 ``kill``：控制台 ``kill`` 直接结束 qemu，客体不走关机流程，页缓存里没写回的
数据会丢（10-03 星铁 9 个热更新清单因此变成 0 字节）。
"""

from __future__ import annotations

import asyncio
import ctypes
import tempfile
import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil

from app.models.emulator import DeviceBase, DeviceInfo, DeviceRef, DeviceStatus
from app.utils import get_logger
from app.utils.paths import SOURCE_ROOT

from ..applaunch import (
    AppLaunchMixin,
    AppLaunchResult,
    ensure_app_running,
    is_package_missing,
    parse_launch_component,
)
from ..settings import FieldValue, InstanceSettings, SettingsConflictError
from ..settings import validate_changes as validate_setting_changes
from . import host, precheck
from .components import (
    component_installed,
    emulator_exe,
    launcher_apk,
    root_from_manager_exe,
    root_key,
)
from .constants import (
    ADB_SERVER_START_TIMEOUT_ON_CLOSE_SECONDS,
    APK_INSTALL_TIMEOUT_SECONDS,
    BALLOON_PAGE_REPORTING_ORDER,
    CACHE_DIR,
    CLOSE_TIMEOUT_SECONDS,
    CONSOLE_KILL_TIMEOUT_SECONDS,
    DEBLOAT_PACKAGES,
    FORCE_KILL_WAIT_SECONDS,
    FOSSIFY_LAUNCHER,
    GUEST_DIRTY_EXPIRE_CENTISECS,
    GUEST_DIRTY_WRITEBACK_CENTISECS,
    GUEST_TMP_DIR,
    INCOMPATIBLE_PACKAGES,
    KEEP_PACKAGES,
    LOGCAT_BUFFER_SIZE,
    LOGS_DIR,
    MAX_NATIVE_INDEX,
    PIXEL_LAUNCHER_PACKAGE,
    PORT_BASE,
    PORT_STEP,
    RECOMMENDED_MEMORY_MB,
    REQUIRED_COMPONENTS,
    RESOLUTIONS,
    STARTUP_GUARD_AFTER_SECONDS,
    STARTUP_GUARD_HARD_SECONDS,
    STARTUP_GUARD_IDLE_CORES,
    STARTUP_GUARD_INTERVAL_SECONDS,
    STARTUP_GUARD_PACKAGES,
    STARTUP_GUARD_RETRIES,
    STARTUP_GUARD_STALL_CORES,
    STARTUP_GUARD_STALL_SECONDS,
    STARTUP_GUARD_START_TIMEOUT_SECONDS,
    STARTUP_GUARD_STATIC_SECONDS,
    STARTUP_GUARD_WATCH_SECONDS,
    SYNC_TIMEOUT_SECONDS,
    VULKAN_ENC_FIX_SHA256,
    VULKAN_ENC_GUEST_PATH,
    VULKAN_ENC_ORIG_SHA256,
    VULKAN_FIX_PACKAGES,
    WATCHDOG_INTERVAL_SECONDS,
    WATCHDOG_PROBE_TIMEOUT_SECONDS,
    WATCHDOG_STRIKES,
    adb_port,
    avd_name,
    console_port,
    grpc_port,
    valid_native_index,
)
from .drop_caches import DROP_SCRIPT as DROP_CACHES_DROP_SCRIPT
from .drop_caches import MARK_SCRIPT as DROP_CACHES_MARK_SCRIPT
from .drop_caches import PROBE_SCRIPT as DROP_CACHES_PROBE_SCRIPT
from .drop_caches import (
    DropOutcome,
    GuestIoSample,
    parse_drop,
    parse_probe,
    run_drop_caches,
)
from .instances import (
    AvdInstance,
    apply_resolution,
    create_instance_files,
    delete_instance_files,
    instance_meta,
    instance_resolution,
    list_instances,
    memory_for,
    resolution_changes,
    update_instance_meta,
    validate_memory,
    validate_options,
    validate_resolution,
    write_instance_config,
)
from .startup_watchdog import (
    EVIDENCE_PROBE,
    ReadyStallDetector,
    ScreenDiff,
    StartupGuard,
    StartupHangDetector,
    StartupSampler,
    shm_thumb,
    su_command,
)
from .vulkanfix import UNSUPPORTED_IMAGE_MESSAGE, VulkanFixError, patch_vulkan_encoder

logger = get_logger("官方模拟器管理")

#: 仓库里推到客体跑的脚本。
GUEST_SCRIPTS_DIR = SOURCE_ROOT / "res" / "avd" / "guest"

#: 等 ``sys.boot_completed`` 的轮询间隔。
_BOOT_POLL_SECONDS = 1.0
#: 状态查询里单条 adb 的超时：状态轮询不能被一台卡住的实例拖住整张表。
_STATUS_ADB_TIMEOUT = 5.0
#: 装轻量桌面的超时。
_INSTALL_TIMEOUT = 180.0
#: 界面上「打开游戏中心」之类一次点击的上限（官方模拟器没有游戏中心，留作接口一致）。
_LAUNCH_TIMEOUT_CAP = 45.0
_BOOT_TIMEOUT_CAP = 120.0


class IncompatibleGameError(RuntimeError):
    """脚本要在官方模拟器上拉起一个已知跑不起来的游戏。"""


def incompatible_reason(package_name: str) -> str | None:
    name = INCOMPATIBLE_PACKAGES.get(package_name)
    if name is None:
        return None
    return f"该游戏暂不支持官方模拟器：{name}（{package_name}）"


def shm_exists(port: int) -> bool:
    """截图共享内存 ``SHM_videmulator<控制台端口>`` 在不在（MaaFW AVDExtras / 假 MuMu DLL 读它）。"""
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (AttributeError, OSError):
        return False
    open_mapping = kernel32.OpenFileMappingW
    open_mapping.restype = ctypes.c_void_p
    open_mapping.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p)
    handle = open_mapping(0x0004, 0, f"SHM_videmulator{port}")  # FILE_MAP_READ
    if not handle:
        return False
    kernel32.CloseHandle(ctypes.c_void_p(handle))
    return True


# ---- 启动参数 -------------------------------------------------------------


def launch_options(meta: dict[str, Any]) -> dict[str, Any]:
    """实例的 MAS 侧选项（``mas-avd.json``）→ 本次开机用的值，缺省值都在这里。"""
    return {
        "resolution": instance_resolution(meta),
        "flags": {
            "headless": bool(meta.get("headless", True)),
            # 空闲页上报默认开（10-04 定）；要自编 qemu（sdk-mas19 起）
            "balloon": bool(meta.get("balloon", True)),
            "guest_angle": bool(meta.get("guestAngle", False)),
        },
    }


def build_launch_args(
    avd: str,
    console: int,
    *,
    memory_mb: int,
    headless: bool,
    balloon: bool,
    guest_angle: bool,
) -> list[str]:
    """``emulator.exe`` 的参数，逐项照启动器 ``avd-p0.ps1``（每个开关都真机验证过）。

    - 冷启动（``-no-snapshot``），与 MAS 对雷电 / MuMu 每轮开关一致；
    - ``-audio none``：静音（用户 09-27 定），客体声卡还在，游戏只是播给空设备；
    - ``-memory``：实例设的客体内存（:func:`~.instances.memory_for`），不改 ``hw.ramSize``；
    - 气球：``QuickbootFileBacked`` 开着时冷启动也用 ``ram.img`` 文件映射当客体内存，qemu 丢不掉
      文件映射的页，空闲页上报就不生效（10-03 首测），所以关掉它；设备挂在 ``-qemu`` 最后，
      占下一个空闲 PCI 槽、不挪现有设备；
    - 磁盘 write-through：客体不再发 flush（和以前客体侧 ``nobarrier`` 一样快），但 QEMU 每次写
      都把数据和 qcow2 元数据推到宿主文件，硬杀不丢已写的数据。``nobarrier`` 硬杀 3/3 把 AVD
      弄坏（内核 panic 循环），这个设置 6/6 无损（09-26）。``-qemu`` 之后全归 QEMU，所以放最后。
    """
    args = [
        "-avd",
        avd,
        "-no-snapshot",
        "-no-boot-anim",
        "-gpu",
        "host",
        "-ports",
        f"{console},{console + 1}",
        "-grpc",
        str(console + 2),
        "-grpc-use-token",
        "-audio",
        "none",
        "-memory",
        str(int(memory_mb)),
    ]
    if guest_angle:
        args += ["-feature", "GuestAngle"]
    if headless:
        args.append("-no-window")
    if balloon:
        args += ["-feature", "-QuickbootFileBacked"]
    args += [
        "-qemu",
        "-global",
        "virtio-blk-device.write-cache=off",
        "-global",
        "virtio-blk-device.config-wce=off",
    ]
    if balloon:
        args += ["-device", "virtio-balloon-pci,free-page-reporting=on"]
    return args


def angle_overrides(current: str) -> str | None:
    """GuestAngle 要追加的 ``debug.angle.feature_overrides_disabled`` 值；已经有了返回 ``None``。

    照启动器：**只追加，不替换**。开机时模拟器把宿主显卡的变通项从
    ``ro.boot.hardware.angle_feature_overrides_disabled`` 拷进这个属性，替换掉会让它们重新生效
    （09-27 晚星铁闪烁、地面破碎）。追加 ``supportsSwapchainMaintenance1`` 关掉 ANGLE 的
    present fence，修 10–20 分钟后画面冻住（每帧漏一个 VkFence + sync_file fd，09-27）。
    ``exposeN*`` 要去掉：关掉它会藏起 GLES 3.2，星铁全紫 / 黑场景。属性值上限 91 字符，
    ANGLE 认 ``*`` 后缀通配。
    """
    if "supportsSwapchainM" in current:  # 含被缩写成通配的那种
        return None
    parts = [p for p in current.split(":") if p and not p.startswith("exposeN")]
    want = ":".join([*parts, "supportsSwapchainMaintenance1"])
    if len(want) > 91:
        want = (
            want.replace("supportsSwapchainMaintenance1", "supportsSwapchainM*")
            .replace("supportsExternalFenceFd", "supportsExternalFen*")
            .replace("supportsExternalSemaphoreFd", "supportsExternalSem*")
        )
    return want


def guest_script(name: str) -> Path:
    """仓库里的客体脚本（``res/avd/guest/``）。"""
    return GUEST_SCRIPTS_DIR / name


# ---- 冻结看门狗 -----------------------------------------------------------

#: ``{根目录键|原生索引: 看门狗任务}``。管理器会被频繁重建（状态轮询每轮一个），
#: 看门狗必须挂在模块上，跟着实例走而不是跟着管理器对象走。
_WATCHDOGS: dict[str, asyncio.Task] = {}
#: 被看门狗判冻结并强杀过的实例 → 原因。``getStatus`` 据此报 ERROR，直到下次 open / close。
_FROZEN: dict[str, str] = {}


def _instance_key(root: Path, native_index: str) -> str:
    return f"{root_key(root)}|{native_index}"


class FreezeWatchdog:
    """定期探活：adb 不通 **且** qemu 进程 CPU 时间不动，连续 N 次判冻结，强杀并记 ERROR。

    两个条件缺一不可：游戏加载时 adb 偶尔会慢（CPU 在跑），模拟器空闲时 CPU 也可能很低
    （adb 仍通）；只有两者同时成立才是预研 §6.6 / §6.20 里那种整机停摆——qemu CPU 归零、
    adb 与控制台全无响应、``emu kill`` 也没用，只能强杀。

    探测函数都可注入，单元测试不需要真实模拟器。
    """

    def __init__(
        self,
        label: str,
        *,
        probe_adb,
        cpu_seconds,
        is_alive,
        kill,
        on_frozen,
        interval: float = WATCHDOG_INTERVAL_SECONDS,
        strikes: int = WATCHDOG_STRIKES,
    ) -> None:
        self.label = label
        self._probe_adb = probe_adb
        self._cpu_seconds = cpu_seconds
        self._is_alive = is_alive
        self._kill = kill
        self._on_frozen = on_frozen
        self.interval = interval
        self.strikes = strikes

    async def run(self) -> str:
        """一直看到实例退出（返回 ``"exited"``）或判冻结并强杀（返回 ``"frozen"``）。"""
        misses = 0
        last_cpu = self._cpu_seconds()
        while True:
            await asyncio.sleep(self.interval)
            if not self._is_alive():
                return "exited"
            adb_ok = await self._probe_adb()
            cpu = self._cpu_seconds()
            cpu_idle = cpu is not None and last_cpu is not None and cpu <= last_cpu
            last_cpu = cpu
            if adb_ok or not cpu_idle:
                if misses:
                    logger.info(f"{self.label} 恢复响应")
                misses = 0
                continue
            misses += 1
            logger.warning(
                f"{self.label} 无响应（adb 不通且模拟器进程 CPU 时间 "
                f"{self.interval:.0f} 秒没有变化），第 {misses}/{self.strikes} 次"
            )
            if misses >= self.strikes:
                reason = (
                    f"模拟器已冻结（adb 与进程均无响应超过 "
                    f"{self.interval * self.strikes:.0f} 秒），已强制结束"
                )
                logger.error(f"{self.label} {reason}")
                self._kill()
                self._on_frozen(reason)
                return "frozen"


def _start_watchdog(root: Path, native_index: str, pid: int) -> None:
    key = _instance_key(root, native_index)
    existing = _WATCHDOGS.get(key)
    if existing is not None and not existing.done():
        return
    try:
        process = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    serial = host.serial_of(console_port(native_index))

    async def probe_adb() -> bool:
        code, output = await host.run_adb(
            root,
            "shell",
            "echo",
            "ok",
            serial=serial,
            timeout=WATCHDOG_PROBE_TIMEOUT_SECONDS,
        )
        ok = code == 0 and output.strip().endswith("ok")
        if ok:
            # 顺带巡检客体日志落盘：私有 server 重启等原因让它退出了就续上
            with suppress(Exception):
                await ensure_logcat(root, native_index)
        return ok

    def is_alive() -> bool:
        try:
            return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            return False

    def on_frozen(reason: str) -> None:
        _FROZEN[key] = reason

    watchdog = FreezeWatchdog(
        f"官方模拟器实例 {avd_name(native_index)}",
        probe_adb=probe_adb,
        cpu_seconds=lambda: host.process_cpu_seconds(process),
        is_alive=is_alive,
        kill=lambda: host.kill_process_tree(process),
        on_frozen=on_frozen,
    )
    task = asyncio.create_task(watchdog.run(), name=f"avd-watchdog-{key}")
    _WATCHDOGS[key] = task
    task.add_done_callback(lambda _: _WATCHDOGS.pop(key, None))


def _stop_watchdog(root: Path, native_index: str) -> None:
    task = _WATCHDOGS.pop(_instance_key(root, native_index), None)
    if task is not None and not task.done():
        task.cancel()


# ---- 开机后的一次性清缓存 ----------------------------------------------------

#: ``{实例键: 清缓存任务}``。和看门狗一样挂在模块上：管理器对象会被频繁重建。
_DROP_CACHES: dict[str, asyncio.Task] = {}


async def ensure_logcat(root: Path, idx: str) -> bool:
    """这台实例没有在落盘的 logcat 就起一个（文件 ``<根>\\logs\\logcat-mas_<i>-<时间>.txt``），返回起没起。

    按宿主进程表判断（:func:`~.host.find_logcat_processes`），不按本进程的记录：后端重启后上一个
    进程起的还在跑，不能再起第二份；私有 server 重启时 logcat 客户端会跟着退出，要能重新起来。
    开机后、重新登记成功后、冻结看门狗每轮巡检时都会调。
    """
    serial = host.serial_of(console_port(idx))
    if await asyncio.to_thread(host.find_logcat_processes, root, serial):
        return False
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = Path(root) / LOGS_DIR / f"logcat-{avd_name(idx)}-{stamp}.txt"
    try:
        await asyncio.to_thread(host.start_logcat, root, serial, path)
    except OSError as e:
        logger.warning(f"实例 {idx} 客体日志落盘没起来: {e}")
        return False
    logger.info(f"实例 {idx} 客体日志 → {path}")
    return True


async def _logcat_after_reregister(root: Path, serial: str) -> None:
    """设备重新登记回来后把落盘续上。

    要重新登记，说明私有 server 换过了：之前起的 logcat 客户端连的是已经没了的 server，不会再出
    数据，但不一定马上退出（10-04 实测重新登记 7 秒后还在），留着它会让 :func:`ensure_logcat`
    以为还在落盘。所以先结束这些旧客户端，再起一个新的。
    """
    console = int(serial.removeprefix("emulator-"))
    idx = str((console - PORT_BASE) // PORT_STEP)
    if idx not in list_instances(root):
        return
    stale = await asyncio.to_thread(host.find_logcat_processes, root, serial)
    for process in stale:
        with suppress(psutil.Error):
            process.kill()
    if stale:
        await asyncio.to_thread(psutil.wait_procs, stale, 5)
    await ensure_logcat(root, idx)


host.add_reregister_hook(_logcat_after_reregister)


def _schedule_drop_caches(manager: _AvdCore, idx: str) -> None:
    """气球开着时，开机后有突发读盘就在读完时清一次客体页缓存（规则见 :mod:`.drop_caches`）。

    每次开机最多判断一次，靠客体里的标记（重启即失效）：同一后端再次 open、后端重启后接管在跑的
    实例，都只会看到标记然后跳过。进程内另外按实例去重，免得同一时刻排两个。
    """
    key = _instance_key(manager.root, idx)
    existing = _DROP_CACHES.get(key)
    if existing is not None and not existing.done():
        return

    async def su(script: str) -> str:
        _, output = await manager._su(idx, script, timeout=20)
        return output

    async def probe() -> GuestIoSample:
        return parse_probe(await su(DROP_CACHES_PROBE_SCRIPT))

    async def drop() -> DropOutcome:
        return parse_drop(await su(DROP_CACHES_DROP_SCRIPT))

    async def mark() -> None:
        await su(DROP_CACHES_MARK_SCRIPT)

    async def run() -> None:
        result = await run_drop_caches(
            probe=probe, drop=drop, mark=mark, sleep=asyncio.sleep
        )
        if result.action == "skipped":
            logger.debug(f"实例 {idx} 客体页缓存{result.reason}，跳过")
            return
        read = (
            f"{result.read_bytes}（{result.read_bytes / 1024**3:.2f} GB）"
            if result.read_bytes is not None
            else "读不到"
        )
        line = (
            f"实例 {idx} 清客体页缓存: system_server read_bytes={read}，{result.reason}"
        )
        if result.action == "dropped":
            line += (
                f"；客体 Cached 清前 {result.cached_before_kb} kB → "
                f"清后 {result.cached_after_kb} kB"
            )
        if result.action == "failed":
            logger.warning(line)
        else:
            logger.info(line)

    task = asyncio.create_task(run(), name=f"avd-drop-caches-{key}")
    _DROP_CACHES[key] = task
    task.add_done_callback(lambda _: _DROP_CACHES.pop(key, None))


#: 星铁 Vulkan 修复：同一实例串行；镜像不对的实例记下原因，之后直接报错不再开机。
_VULKAN_LOCKS: dict[str, asyncio.Lock] = {}
_VULKAN_UNSUPPORTED: dict[str, str] = {}

#: ``{实例键: 游戏启动看门狗任务}``。启动成功后它还在后台看一段，关机 / 再次拉起时取消。
_GAME_GUARDS: dict[str, asyncio.Task] = {}


def _cancel_game_guard(key: str) -> None:
    task = _GAME_GUARDS.pop(key, None)
    if task is not None and not task.done():
        task.cancel()


def _log_guard_record(label: str, record: dict[str, Any]) -> None:
    """看门狗每个样本记 debug；判出卡死 / 死锁的那个样本记 warning。"""
    state = record.get("state") or record.get("stall")
    text = ", ".join(
        f"{k}={v}" for k, v in record.items() if k not in ("unity_main", "main_thread")
    )
    if state in ("hang", "stalled", "exited", "no_process"):
        logger.warning(
            f"{label} 启动看门狗: {text}; UnityMain={record.get('unity_main')}; "
            f"主线程={record.get('main_thread')}"
        )
    else:
        logger.debug(f"{label} 启动看门狗: {text}")


async def _run_guard(label: str, guard: StartupGuard) -> dict[str, Any]:
    """跑完一次守护拉起，把结论写进日志。看门狗自己出错不往外抛，返回 ``{"result": "error"}``。"""
    try:
        result = await guard.run()
    except asyncio.CancelledError:
        logger.info(f"{label} 启动看门狗已取消")
        raise
    except Exception as e:  # noqa: BLE001 - 看门狗失灵不能拖垮拉起流程
        logger.opt(exception=True).warning(f"{label} 启动看门狗出错，改为普通拉起: {e}")
        return {"result": "error", "error": str(e)}
    for attempt in result["attempts"]:
        if attempt["result"] != "started":
            logger.warning(
                f"{label} 第 {attempt['attempt']} 次拉起: {attempt['result']}"
                f"（{attempt.get('kind') or ''}，第 {attempt.get('t_detect')} 秒），"
                f"证据 {attempt.get('evidence') or attempt.get('evidence_error') or '无'}"
            )
    if result["result"] == "started":
        logger.info(
            f"{label} 启动看门狗结束：已启动，重开 {result['relaunches']} 次，"
            f"用时 {result['seconds']} 秒"
        )
    else:
        logger.error(
            f"{label} 启动看门狗放弃：拉起 {len(result['attempts'])} 次都卡住"
            f"（重开上限 {guard.retries} 次）"
        )
    return result


def _cancel_drop_caches(root: Path, native_index: str) -> None:
    task = _DROP_CACHES.pop(_instance_key(root, native_index), None)
    if task is not None and not task.done():
        task.cancel()


# ---- 管理器 ---------------------------------------------------------------


class _Settings:
    """``AppLaunchMixin`` 与门面只读 ``config.get("Info", ...)``；这里不需要完整的配置对象。"""

    def __init__(self, values: dict[str, Any]) -> None:
        self._values = values

    def get(self, group: str, key: str) -> Any:
        return self._values[key]


class _AvdCore(DeviceBase):
    """只负责开关机与状态，不带应用拉起（由 :class:`AvdManager` 叠上）。"""

    def __init__(
        self, manager_exe: str | Path, max_wait_time: int, force_kill_on_close: bool
    ) -> None:
        self.emulator_path = Path(manager_exe)
        self.root = root_from_manager_exe(manager_exe)
        self.config = _Settings(
            {
                "MaxWaitTime": int(max_wait_time),
                "ForceKillOnClose": bool(force_kill_on_close),
                "Type": "avd",
                "Path": str(manager_exe),
            }
        )

    # ---- 查询 -----------------------------------------------------------

    def _instances(self) -> dict[str, AvdInstance]:
        return list_instances(self.root)

    def _instance(self, idx: str) -> AvdInstance:
        instance = self._instances().get(str(idx))
        if instance is None:
            raise RuntimeError(f"官方模拟器实例 {idx} 不存在")
        return instance

    def _scan_processes(self) -> dict[str, psutil.Process]:
        """一次扫描把这条安装所有实例的 qemu 进程找齐，别每台扫一遍进程表。"""
        found: dict[str, psutil.Process] = {}
        wanted = {idx: (avd_name(idx), console_port(idx)) for idx in self._instances()}
        if not wanted:
            return found
        for process in psutil.process_iter(["name", "cmdline"]):
            try:
                name = (process.info.get("name") or "").lower()
                if not name.startswith("qemu-system"):
                    continue
                cmdline = process.info.get("cmdline") or []
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            for idx, (avd, port) in wanted.items():
                if host._cmdline_matches(cmdline, avd, port):
                    found[idx] = process
        return found

    async def _boot_completed(
        self, idx: str, timeout: float = _STATUS_ADB_TIMEOUT, *, reregister: bool = True
    ) -> bool:
        code, output = await host.run_adb(
            self.root,
            "shell",
            "getprop",
            "sys.boot_completed",
            serial=host.serial_of(console_port(idx)),
            timeout=timeout,
            reregister=reregister,
        )
        return code == 0 and output.strip() == "1"

    async def _status_of(
        self, idx: str, process: psutil.Process | None
    ) -> DeviceStatus:
        key = _instance_key(self.root, idx)
        if key in _FROZEN:
            return DeviceStatus.ERROR
        if process is None:
            return DeviceStatus.OFFLINE
        if await self._boot_completed(idx):
            return DeviceStatus.ONLINE
        return DeviceStatus.STARTING

    def _device_info(self, idx: str, title: str, status: DeviceStatus) -> DeviceInfo:
        # 给脚本的是 adb 端口的 TCP 地址：脚本用自己的 adb connect 过去，与雷电 / MuMu 一致。
        # 不给 emulator-<端口> 这个序列号——它只在我们的私有 server（20050）上存在。
        return DeviceInfo(title, status, f"127.0.0.1:{adb_port(idx)}")

    async def getStatus(self, idx: str) -> DeviceStatus:
        if str(idx) not in self._instances():
            return DeviceStatus.NOT_FOUND
        process = await asyncio.to_thread(
            host.find_qemu_process, avd_name(idx), console_port(idx)
        )
        return await self._status_of(str(idx), process)

    async def getInfo(self, idx: str | None) -> dict[str, DeviceInfo]:
        instances = self._instances()
        if idx is not None:
            instance = instances.get(str(idx))
            if instance is None:
                raise RuntimeError(f"官方模拟器实例 {idx} 不存在")
            instances = {str(idx): instance}
        processes = await asyncio.to_thread(self._scan_processes)
        result: dict[str, DeviceInfo] = {}
        for native_index, instance in instances.items():
            status = await self._status_of(native_index, processes.get(native_index))
            result[native_index] = self._device_info(
                native_index, instance.title, status
            )
        return result

    async def list_devices(self) -> dict[str, str]:
        return {idx: instance.title for idx, instance in self._instances().items()}

    def get_adb_path(self) -> Path | None:
        """返回 ``None``：让脚本回退到系统 / 脚本自带的 adb。

        SDK 里的 adb 是新版本；交给脚本去用，它会在 5037 上起一个新版 server，和雷电 / MuMu
        自带的老版本 adb 争 5037、互相杀 server，把正在跑的雷电 / MuMu 任务一起打断。
        MaaFW 那边需要一个确定的 adb 路径时由 ``runner_task`` 单独处理。
        """
        return None

    def resolve_device(self, idx: str) -> DeviceRef | None:
        return DeviceRef(
            emulator_type="avd",
            manager_path=str(self.emulator_path),
            native_index=str(idx),
        )

    def grpc_endpoint(self, idx: str) -> dict[str, Any] | None:
        """实例的 gRPC 地址与 token，给以后的画面查看窗口用（段 C）。没在跑返回 ``None``。

        模拟器带 ``-grpc-use-token`` 启动，token 写在它自己的运行时文件
        ``%TEMP%\\avd\\running\\pid_<qemu pid>.ini`` 的 ``grpc.token=`` 行里，只听 127.0.0.1。
        """
        process = host.find_qemu_process(avd_name(idx), console_port(idx))
        if process is None:
            return None
        token = ""
        candidate = (
            Path(tempfile.gettempdir()) / "avd" / "running" / f"pid_{process.pid}.ini"
        )
        with suppress(OSError):
            for line in candidate.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines():
                if line.startswith("grpc.token="):
                    token = line.split("=", 1)[1].strip()
        return {
            "host": "127.0.0.1",
            "port": grpc_port(idx),
            "token": token,
            "pid": process.pid,
        }

    async def setVisible(self, idx: str, is_visible: bool) -> DeviceStatus:
        """无头实例没有窗口可显示 / 隐藏；本阶段不做热切换，只记一笔并回报当前状态。

        不抛异常：脚本在静默模式下每轮都会调这个，抛了会把整次运行判失败。
        要看画面：在实例设置里改成「带窗口」，下次启动生效。
        """
        headless = bool(instance_meta(self.root, idx).get("headless", True))
        if is_visible and headless:
            logger.info(
                f"官方模拟器实例 {idx} 以无头方式运行，没有窗口可显示；"
                "需要看画面请在实例设置里改为带窗口，下次启动生效"
            )
        return await self.getStatus(idx)

    # ---- 启动 -----------------------------------------------------------

    def _check_components(self) -> None:
        missing = [
            c.name for c in REQUIRED_COMPONENTS if not component_installed(self.root, c)
        ]
        if missing:
            raise RuntimeError(
                "官方模拟器组件不完整，缺少：" + "、".join(missing) + "，请重新下载组件"
            )

    async def open(self, idx: str, package_name: str = "") -> DeviceInfo:
        idx = str(idx)
        instance = self._instance(idx)
        key = _instance_key(self.root, idx)
        _FROZEN.pop(key, None)
        port = console_port(idx)
        max_wait = float(self.config.get("Info", "MaxWaitTime"))

        process = await asyncio.to_thread(host.find_qemu_process, instance.name, port)
        launched = process is None
        serial = host.serial_of(port)
        try:
            if launched:
                # 开机期间所有路径（含面板每秒的状态轮询）都不替它重新登记
                host.BOOTING.add(serial)
                await self._launch(idx, instance)
            else:
                logger.info(f"官方模拟器实例 {idx} 已在运行（pid {process.pid}）")
            process = await self._wait_boot(idx, instance, launched, max_wait)
        finally:
            if launched:
                host.BOOTING.discard(serial)

        await self._after_boot(idx, instance)
        _start_watchdog(self.root, idx, process.pid)
        return self._device_info(idx, instance.title, DeviceStatus.ONLINE)

    async def _wait_boot(
        self, idx: str, instance: AvdInstance, launched: bool, max_wait: float
    ) -> psutil.Process:
        port = console_port(idx)
        deadline = time.monotonic() + max_wait
        while True:
            process = await asyncio.to_thread(
                host.find_qemu_process, instance.name, port
            )
            # 刚起的实例：开机期间 qemu 已经占着 adb 端口，模拟器却还没向私有 server 登记，这里查不到
            # 是正常的，不替它登记（否则每次冷启动都白等 5 秒、多两条警告）。本来就在跑的实例可能
            # 赶上私有 server 重启过，照常重新登记。
            if process is not None and await self._boot_completed(
                idx, reregister=not launched
            ):
                return process
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"官方模拟器实例 {idx} 启动超时（{max_wait:.0f} 秒内安卓没有启动完成）"
                    f"，日志见 {self._log_dir()}"
                )
            if process is None and self._launcher is not None:
                code = self._launcher.poll()
                if code is not None:
                    raise RuntimeError(
                        f"官方模拟器实例 {idx} 启动失败（emulator.exe 退出码 {code}）："
                        f"{self._log_tail()}"
                    )
            await asyncio.sleep(_BOOT_POLL_SECONDS)

    _launcher = None
    _log_path: Path | None = None
    #: 这次 open 要跑的游戏包名（:class:`AvdManager` 在开机前设），只用来对照推荐内存记日志。
    _open_package: str = ""

    def _log_dir(self) -> Path:
        return self.root / LOGS_DIR

    def _log_tail(self, lines: int = 8) -> str:
        if self._log_path is None:
            return ""
        try:
            text = self._log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        tail = [line for line in text.splitlines() if line.strip()][-lines:]
        return " | ".join(tail)

    async def _launch(self, idx: str, instance: AvdInstance) -> None:
        self._check_components()
        # 电脑检查用的内存就是下面 -memory 要传的值：实例自己设的，不按游戏推算
        memory_mb = memory_for(instance_meta(self.root, idx))
        recommended = RECOMMENDED_MEMORY_MB.get(self._open_package or "")
        if recommended and memory_mb < recommended:
            logger.warning(
                f"魔改 AVD 实例 {idx} 内存 {memory_mb} MB，低于 {self._open_package} 的推荐值 "
                f"{recommended} MB，可在魔改 AVD 选项里调大"
            )
        await precheck.check_before_launch(self.root, memory_mb)

        port = console_port(idx)
        ports = [port, port + 1, port + 2]
        busy = await asyncio.to_thread(host.busy_ports, ports)
        if busy:
            raise RuntimeError(
                f"官方模拟器实例 {idx} 要用的端口 {', '.join(map(str, busy))} 已被占用，"
                "请先关闭占用它们的程序"
            )

        await host.ensure_adb_server(self.root)
        meta = instance_meta(self.root, idx)
        options = launch_options(meta)
        if await asyncio.to_thread(
            apply_resolution, self.root, idx, options["resolution"]
        ):
            logger.info(
                f"实例 {idx} 显示改为 {options['resolution']}p（已写入 config.ini）"
            )
        args = build_launch_args(
            instance.name, port, memory_mb=memory_mb, **options["flags"]
        )
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self._log_path = self._log_dir() / f"{instance.name}-{stamp}.log"
        logger.info(
            f"启动官方模拟器实例 {idx}（{'无头' if options['flags']['headless'] else '带窗口'}，"
            f"{options['resolution']}p，{memory_mb} MB / {instance.cpu} 核，"
            f"气球{'开' if options['flags']['balloon'] else '关'}"
            f"{'，GuestAngle' if options['flags']['guest_angle'] else ''}）: "
            f"emulator {' '.join(args)}"
        )
        self._launcher = await asyncio.to_thread(
            host.launch_emulator, self.root, args, self._log_path
        )

    # ---- 开机后 ---------------------------------------------------------

    async def _shell(
        self, idx: str, command: str, timeout: float = 30.0
    ) -> tuple[int, str]:
        return await host.run_adb(
            self.root,
            "shell",
            command,
            serial=host.serial_of(console_port(idx)),
            timeout=timeout,
        )

    async def _su(
        self, idx: str, script: str, timeout: float = 30.0
    ) -> tuple[int, str]:
        """以 root 跑一段客体命令。这些 userdebug 镜像上 ``su 0`` 不用先 ``adb root``——
        ``adb root`` 会重启 adbd，把脚本自己那个 adb server 的连接一起断掉，所以不用。"""
        if "'" in script:
            raise ValueError("客体脚本里不能有单引号")
        return await self._shell(idx, f"su 0 sh -c '{script}'", timeout=timeout)

    async def _push(self, idx: str, local: Path, remote: str) -> bool:
        code, output = await host.run_adb(
            self.root,
            "push",
            str(local),
            remote,
            serial=host.serial_of(console_port(idx)),
            timeout=60,
        )
        if code != 0:
            logger.warning(f"实例 {idx} 推送 {local.name} 失败: {output}")
        return code == 0

    async def _after_boot(self, idx: str, instance: AvdInstance) -> None:
        """每次开机后的调优（重启即失效）+ 首次开机的一次性初始化。失败只记警告。

        逐项照启动器 ``avd-p0.ps1`` 开机后那段。**不再做**的两项：
        ``gsm meter on|off``——每调一次，镜像的 MeterService 反而装上那个 2 GB 测试套餐（用量重置成
        200 MB），没有这条调用就没有套餐、没有上限（09-26 经 ``dumpsys netpolicy`` 确认）；
        ``/data`` 的 ``nobarrier``——改由启动参数让磁盘 write-through（见 :func:`build_launch_args`）。
        """
        port = console_port(idx)
        options = launch_options(instance_meta(self.root, idx))
        flags = options["flags"]

        # 1) 宿主调度：优先级、X3D 绑核
        process = await asyncio.to_thread(host.find_qemu_process, instance.name, port)
        if process is not None:
            note = await asyncio.to_thread(host.tune_host_scheduling, process)
            logger.info(f"实例 {idx} 宿主调度: {note}")

        # 2) 截图共享内存：开推流才会建 SHM_videmulator<端口>，静止画面下它一直是黑帧，
        #    所以建好后强制 SurfaceFlinger 重绘一帧（预研 §6.16；1004 要 root）
        try:
            await host.console_command(port, "screenrecord webrtc start")
        except host.ConsoleError as e:
            logger.warning(f"实例 {idx} 开启截图共享内存失败: {e}")
        await self._shell(idx, "su 0 service call SurfaceFlinger 1004")

        # 3) GuestAngle：ANGLE 在进程初始化 EGL 时读属性，只管之后启动的进程（游戏）
        if flags["guest_angle"]:
            await self._apply_angle_overrides(idx)

        # 4) 磁盘与截图通道的现状写进日志（write_cache 要 root 才读得到）
        _, write_cache = await self._su(
            idx, "cat /sys/block/vd*/queue/write_cache | sort -u"
        )
        logger.info(
            f"实例 {idx} 磁盘缓存: {' / '.join(ln.strip() for ln in write_cache.splitlines() if ln.strip()) or '读不到'}；"
            f"截图共享内存 SHM_videmulator{port}: {'在' if shm_exists(port) else '缺失'}"
        )

        # 4b) 客体脏页回写调短（硬杀时少丢数据，依据见常量注释；不持久，每次开机都设）
        await self._setup_guest_writeback(idx)

        # 5) 空闲页上报：驱动绑定时把 order 重置成 pageblock_order，绑定之后再设
        if flags["balloon"]:
            await self._setup_balloon(idx)

        # 6) ARM 转译层的 cpuinfo：每个 vCPU 一条，Unity 才不按单核选最低画质
        if await self._push(
            idx, guest_script("cpuinfo-bind.sh"), f"{GUEST_TMP_DIR}/cpuinfo-bind.sh"
        ):
            _, cores = await self._shell(
                idx, f"su 0 sh {GUEST_TMP_DIR}/cpuinfo-bind.sh"
            )
            logger.info(f"实例 {idx} ARM 转译 cpuinfo: {cores.strip() or '?'} 核")

        # 7) 崩溃 / 无响应弹窗没人点，挡在游戏前面；关掉（持久）
        await self._shell(idx, "settings put global hide_error_dialogs 1")

        # 8) 网络：WiFi 一直开着（游戏看到 WiFi 就不弹「非 WiFi 下载」）；fastpath 把本地流量
        #    走 eth0（虚拟 WiFi 单独只有约 6 MB/s）。WiFi 开关存在 /data 里，每次开机都显式设
        await self._setup_network(idx)

        # 9) 客体日志：缓冲调到 16 MB（持久），开机后持续落盘到 <根>\logs，问题包要用
        await self._start_logcat(idx, instance)

        meta = instance_meta(self.root, idx)
        if not meta.get("initialized"):
            await self._first_boot_init(idx)

    async def _setup_guest_writeback(self, idx: str) -> tuple[int | None, int | None]:
        """把客体 ``dirty_expire_centisecs`` / ``dirty_writeback_centisecs`` 设成 200 / 100 并读回记日志。"""
        expire, writeback = (
            GUEST_DIRTY_EXPIRE_CENTISECS,
            GUEST_DIRTY_WRITEBACK_CENTISECS,
        )
        _, output = await self._su(
            idx,
            f"echo {expire} > /proc/sys/vm/dirty_expire_centisecs; "
            f"echo {writeback} > /proc/sys/vm/dirty_writeback_centisecs; "
            "cat /proc/sys/vm/dirty_expire_centisecs /proc/sys/vm/dirty_writeback_centisecs",
        )
        values = [_int(part) for part in output.split()[:2]]
        got = (values + [None, None])[:2]
        if got == [expire, writeback]:
            logger.info(
                f"实例 {idx} 客体回写: dirty_expire {got[0]} cs、dirty_writeback {got[1]} cs"
            )
        else:
            logger.warning(
                f"实例 {idx} 客体回写没设上（要 {expire}/{writeback}）: {output[-200:]}"
            )
        return got[0], got[1]

    async def _apply_angle_overrides(self, idx: str) -> None:
        _, current = await self._shell(
            idx, "getprop debug.angle.feature_overrides_disabled"
        )
        current = current.strip()
        if not current:
            _, current = await self._shell(
                idx, "getprop ro.boot.hardware.angle_feature_overrides_disabled"
            )
            current = current.strip()
        want = angle_overrides(current)
        if want is not None:
            await self._shell(
                idx, f"su 0 setprop debug.angle.feature_overrides_disabled '{want}'"
            )
            _, current = await self._shell(
                idx, "getprop debug.angle.feature_overrides_disabled"
            )
        logger.info(f"实例 {idx} ANGLE 关闭的特性: {current.strip()}")

    async def _setup_balloon(self, idx: str) -> None:
        order = BALLOON_PAGE_REPORTING_ORDER
        param = "/sys/module/page_reporting/parameters/page_reporting_order"
        _, output = await self._su(
            idx,
            "ls /sys/bus/virtio/drivers/virtio_balloon | grep -c virtio; "
            f"echo {order} > {param}; cat {param}",
        )
        parts = output.split()
        bound = parts[0] if parts else "?"
        current = parts[1] if len(parts) > 1 else "?"
        if bound in ("", "0", "?") or current != str(order):
            logger.warning(
                f"实例 {idx} 空闲页上报没就位：气球设备绑定 {bound}，"
                f"page_reporting_order {current}（要 {order}）；模拟器要 sdk-mas19 起的自编 qemu"
            )
        else:
            logger.info(
                f"实例 {idx} 空闲页上报: 气球设备绑定 {bound}，page_reporting_order {current}"
            )
        _schedule_drop_caches(self, idx)

    async def _setup_network(self, idx: str) -> None:
        await self._shell(idx, "su 0 svc wifi enable")
        remote = f"{GUEST_TMP_DIR}/mas-wifi-fastpath.sh"
        if not await self._push(idx, guest_script("mas-wifi-fastpath.sh"), remote):
            return
        await self._shell(idx, f"su 0 sh {remote} on; su 0 sh {remote} daemon")
        _, status = await self._shell(idx, f"su 0 sh {remote} status")
        lines = {
            key: value.strip()
            for key, _, value in (line.partition(":") for line in status.splitlines())
        }
        if "lookup eth0" in lines.get("rule4", ""):
            logger.info(f"实例 {idx} 网络: WiFi 开，fastpath 生效（{lines['rule4']}）")
        elif lines.get("watchers"):
            # 刚开机时 eth0 往往还没起来（没有 eth0 路由表），规则加不上；守护每 10 秒补一次
            logger.info(
                f"实例 {idx} 网络: WiFi 开，fastpath 守护已起（pid {lines['watchers']}），"
                "规则在 eth0 就绪后由守护补上"
            )
        else:
            logger.warning(f"实例 {idx} fastpath 没起来: {status[-300:]}")

    async def _start_logcat(self, idx: str, instance: AvdInstance) -> None:
        await self._shell(
            idx,
            f"su 0 setprop persist.logd.size {LOGCAT_BUFFER_SIZE}; "
            f"logcat -G {LOGCAT_BUFFER_SIZE}",
        )
        await ensure_logcat(self.root, idx)

    async def _first_boot_init(self, idx: str) -> None:
        """首次开机后的持久设置（重启后保持），做完记进 ``mas-avd.json``。"""
        logger.info(f"官方模拟器实例 {idx} 首次开机，正在初始化")
        failures: list[str] = []

        # WiFi 不在这里关：每次开机都开 WiFi + fastpath（用户 09-27 定，见 _setup_network）
        base = [
            "svc bluetooth disable",
            "settings put secure immersive_mode_confirmations confirmed",
        ]
        code, output = await self._shell(idx, " ; ".join(base))
        if code != 0:
            failures.append(f"基础设置: {output}")

        # 手机预装应用：约省 480 MB 内存（预研 §6.11），pm enable 可恢复
        disable = " ; ".join(
            f"pm disable-user --user 0 {package}" for package in DEBLOAT_PACKAGES
        )
        code, output = await self._shell(idx, disable, timeout=120)
        if code != 0:
            failures.append(f"禁用预装应用: {output[-200:]}")

        launcher = await self._install_launcher(idx)

        # 没有可用显卡驱动时会落到 SwiftShader 软件渲染：画面正常，但标题页就吃 6.6 核，
        # 实际不可用（预研 §6.15）。记下来并提示，不静默忍受。
        code, output = await self._shell(idx, "dumpsys SurfaceFlinger | grep GLES")
        # 输出第一行是「------------RE GLES------------」标题，要的是「GLES: 厂商, 渲染器, 版本」那行
        renderer = next(
            (
                line.strip()
                for line in output.splitlines()
                if code == 0 and line.strip().startswith("GLES:")
            ),
            "",
        )
        software = "swiftshader" in renderer.lower()
        if software:
            logger.warning(
                f"官方模拟器实例 {idx} 正在用软件渲染（{renderer}）：没有可用的显卡驱动，"
                "游戏会占满 CPU，请更新显卡驱动"
            )

        update_instance_meta(
            self.root,
            idx,
            initialized=not failures,
            initializedAt=datetime.now().isoformat(timespec="seconds"),
            launcher=launcher,
            renderer=renderer,
            softwareRenderer=software,
            initErrors=failures,
        )
        if failures:
            logger.warning(
                f"官方模拟器实例 {idx} 初始化有失败项，下次开机重试: {failures}"
            )
        else:
            logger.info(f"官方模拟器实例 {idx} 初始化完成（桌面: {launcher}）")

    async def _install_launcher(self, idx: str) -> str:
        """装轻量桌面并设为默认、禁用原生桌面。没下载到就保留原生桌面。"""
        apk = launcher_apk(self.root)
        if not apk.is_file():
            return "pixel"
        code, output = await host.run_adb(
            self.root,
            "install",
            "-r",
            str(apk),
            serial=host.serial_of(console_port(idx)),
            timeout=_INSTALL_TIMEOUT,
        )
        if code != 0 or "Success" not in output:
            logger.warning(f"实例 {idx} 安装轻量桌面失败: {output}")
            return "pixel"
        commands = [
            f"cmd package set-home-activity {FOSSIFY_LAUNCHER.home_activity}",
            f"pm disable-user --user 0 {PIXEL_LAUNCHER_PACKAGE}",
            "input keyevent KEYCODE_HOME",
        ]
        code, output = await self._shell(idx, " ; ".join(commands))
        if code != 0:
            logger.warning(f"实例 {idx} 设置轻量桌面失败: {output}")
            return "pixel"
        return FOSSIFY_LAUNCHER.package

    # ---- 关机 -----------------------------------------------------------

    async def close(self, idx: str) -> DeviceStatus:
        idx = str(idx)
        instance = self._instance(idx)
        port = console_port(idx)
        _stop_watchdog(self.root, idx)
        _cancel_drop_caches(self.root, idx)
        _cancel_game_guard(_instance_key(self.root, idx))
        _FROZEN.pop(_instance_key(self.root, idx), None)
        process = await asyncio.to_thread(host.find_qemu_process, instance.name, port)
        if process is None:
            return DeviceStatus.OFFLINE

        # 先 sync：控制台 kill / 强杀都直接结束 qemu，客体不走关机流程，页缓存里没写回的数据会丢
        # （10-03 星铁 9 个热更新清单变成 0 字节，表现成「网络请求超时」和黑屏）。磁盘 write-through
        # 只保证已经写到虚拟盘的数据，管不到还在客体内存里的。强制关闭也先 sync。
        # 时限：调用方（任务收尾 close_emulator）整体只给 30 秒，超了连强杀都执行不到。各步上限见
        # constants 里关机那一组（合计 27 秒）。sync 不走重新登记（会多等 5 秒）。
        started = time.monotonic()
        # 私有 server 要是没在跑，起它、替实例登记也算进预算：最多等几秒，不成就不 sync 了，直接关
        problem = await host.prepare_adb_for_close(
            self.root, port, timeout=ADB_SERVER_START_TIMEOUT_ON_CLOSE_SECONDS
        )
        if problem is None:
            code, output = await host.run_adb(
                self.root,
                "shell",
                "sync",
                serial=host.serial_of(port),
                timeout=SYNC_TIMEOUT_SECONDS,
                reregister=False,
            )
        else:
            code, output = -1, problem
        if code == 0:
            logger.info(
                f"官方模拟器实例 {idx} 关机前 sync 完成（{(time.monotonic() - started) * 1000:.0f} ms）"
            )
        else:
            logger.warning(f"官方模拟器实例 {idx} 关机前 sync 失败，照常关机: {output}")

        if not self.config.get("Info", "ForceKillOnClose"):
            try:
                await host.console_command(
                    port, "kill", timeout=CONSOLE_KILL_TIMEOUT_SECONDS
                )
            except host.ConsoleError as e:
                logger.warning(f"实例 {idx} 正常关机失败，改为强制结束: {e}")
            else:
                with suppress(psutil.TimeoutExpired):
                    await asyncio.to_thread(process.wait, CLOSE_TIMEOUT_SECONDS)
        if process.is_running():
            logger.warning(
                f"官方模拟器实例 {idx} 未在 {CLOSE_TIMEOUT_SECONDS:.0f} 秒内退出，强制结束"
            )
            host.kill_process_tree(process)
            with suppress(psutil.TimeoutExpired):
                await asyncio.to_thread(process.wait, FORCE_KILL_WAIT_SECONDS)
        logger.info(f"官方模拟器实例 {idx} 已关闭")
        return DeviceStatus.OFFLINE

    # ---- 设置 -----------------------------------------------------------

    async def read_instance_settings(self, idx: str) -> InstanceSettings:
        instance = self._instances().get(str(idx))
        if instance is None:
            return InstanceSettings(
                fields={
                    name: FieldValue(None, "unreadable")
                    for name in ("width", "height", "dpi", "cpu", "memoryMb", "fps")
                }
            )
        # 显示按实例选的档位报（开机前才写进 config.ini）
        meta = instance_meta(self.root, idx)
        display = resolution_changes(instance.config, instance_resolution(meta))
        # 报开机实际传的 -memory（实例元数据里的值；以前「按游戏自动」的旧实例按默认 6 GB）
        memory = FieldValue(memory_for(meta), "saved")
        return InstanceSettings(
            fields={
                "width": FieldValue(_int(display["hw.lcd.width"]), "saved"),
                "height": FieldValue(_int(display["hw.lcd.height"]), "saved"),
                "dpi": FieldValue(_int(display["hw.lcd.density"]), "saved"),
                "cpu": FieldValue(instance.cpu, "saved"),
                "memoryMb": memory,
                # 帧率跟着客体 60 Hz 走，没有可设的项
                "fps": FieldValue(None, "unset"),
            }
        )

    async def read_instance_overview(
        self, idx: str
    ) -> tuple[InstanceSettings, bool, list[str]]:
        return await self.read_instance_settings(idx), True, []

    async def write_instance_settings(
        self, idx: str, changes: dict, expected: dict | None = None
    ) -> dict[str, int]:
        """可改 CPU、内存与显示档位（下次启动生效）；显示只有 720p / 1080p 两档，帧率不可设。"""
        cleaned = validate_setting_changes(changes)
        if "fps" in cleaned:
            raise ValueError("官方模拟器没有可设置的帧率")
        instance = self._instance(idx)
        resolution = None
        if {"width", "height", "dpi"} & cleaned.keys():
            resolution = _resolution_of(
                cleaned.get("width", _int(instance.config.get("hw.lcd.width"))),
                cleaned.get("height", _int(instance.config.get("hw.lcd.height"))),
                cleaned.get("dpi", _int(instance.config.get("hw.lcd.density"))),
            )
        memory, cpu, _ = validate_options(
            cleaned.get("memoryMb", memory_for(instance_meta(self.root, idx))),
            cleaned.get("cpu", instance.cpu),
            instance.data_partition_gb,
        )
        if expected:
            current = (await self.read_instance_settings(idx)).values()
            conflicts = [
                name
                for name in cleaned
                if name in expected and current.get(name) != expected[name]
            ]
            if conflicts:
                raise SettingsConflictError(conflicts)
        write_instance_config(
            self.root, idx, {"hw.ramSize": f"{memory}M", "hw.cpu.ncore": str(cpu)}
        )
        # 内存每次都记进元数据：开机按它传 -memory，以前「按游戏自动」的旧实例从此有了固定值
        update_instance_meta(self.root, idx, memoryMb=memory)
        if resolution is not None:
            # 开机前才写进 config.ini（_launch），这里只记档位
            update_instance_meta(self.root, idx, resolution=resolution)
        applied = {
            k: v
            for k, v in cleaned.items()
            if k in ("cpu", "memoryMb", "width", "height", "dpi")
        }
        logger.info(f"已写入官方模拟器实例 {idx} 的设置: {applied}")
        return applied

    async def read_stable_mode(self, idx: str) -> tuple[bool, list[str]]:
        # 官方模拟器没有会干扰截图识别的厂商功能，天然就是「稳定」的
        return True, []

    async def apply_stable_mode(self, idx: str) -> list[str]:
        return []

    # ---- 实例增删 ------------------------------------------------------

    async def create_instance(
        self,
        name: str | None = None,
        *,
        memory_mb: int | None = None,
        cpu: int | None = None,
        data_partition_gb: int | None = None,
        headless: bool = True,
        native_index: int | None = None,
        resolution: str | None = None,
        balloon: bool = True,
        guest_angle: bool = False,
    ) -> str:
        """新建实例，返回原生索引。不给索引就取最小的、端口也空着的那个。

        内存、核数不给就用默认 6 GB / 6 核（:data:`~.constants.DEFAULT_MEMORY_MB` / ``DEFAULT_CPU``）。
        """
        memory, cores, data_gb = validate_options(memory_mb, cpu, data_partition_gb)
        display = validate_resolution(resolution)
        existing = {int(idx) for idx in self._instances()}
        if native_index is None:
            native_index = await asyncio.to_thread(self._free_index, existing)
        elif not valid_native_index(int(native_index)) or int(native_index) in existing:
            raise ValueError(f"原生索引 {native_index} 不可用")
        create_instance_files(
            self.root,
            int(native_index),
            title=name,
            memory_mb=memory,
            cpu=cores,
            data_partition_gb=data_gb,
            headless=headless,
            resolution=display,
            balloon=balloon,
            guest_angle=guest_angle,
        )
        logger.info(
            f"已新建官方模拟器实例 {native_index}（内存 "
            f"{memory} MB / {cores} 核 / 数据盘 {data_gb} GB / "
            f"{display}p）"
        )
        return str(native_index)

    @staticmethod
    def _free_index(existing: set[int]) -> int:
        for index in range(0, MAX_NATIVE_INDEX + 1):
            if not valid_native_index(index) or index in existing:
                continue
            port = console_port(index)
            if host.busy_ports([port, port + 1, port + 2]):
                continue
            return index
        raise RuntimeError("官方模拟器实例已满（端口段 20000–20100 最多 9 台）")

    async def delete_instance(self, native_index: str) -> None:
        status = await self.getStatus(native_index)
        if status not in (
            DeviceStatus.OFFLINE,
            DeviceStatus.NOT_FOUND,
            DeviceStatus.ERROR,
        ):
            raise RuntimeError(f"官方模拟器实例 {native_index} 未关闭，无法删除")
        if status == DeviceStatus.ERROR:
            # 被看门狗强杀过的实例进程已经不在，只剩状态标记
            _FROZEN.pop(_instance_key(self.root, str(native_index)), None)
        await asyncio.to_thread(delete_instance_files, self.root, native_index)
        # 同一索引以后新建的是另一台实例，之前「镜像不支持星铁普通模式」的结论不能沿用
        _VULKAN_UNSUPPORTED.pop(_instance_key(self.root, str(native_index)), None)
        logger.info(f"已删除官方模拟器实例 {native_index}")

    # ---- 实例选项 ------------------------------------------------------

    def instance_options(self, idx: str) -> dict[str, Any]:
        instance = self._instance(idx)
        meta = instance_meta(self.root, idx)
        options = launch_options(meta)
        return {
            "headless": options["flags"]["headless"],
            "resolution": options["resolution"],
            "balloon": options["flags"]["balloon"],
            "guestAngle": options["flags"]["guest_angle"],
            "memoryMb": memory_for(meta),
            "cpu": instance.cpu,
            "dataPartitionGb": instance.data_partition_gb,
            "initialized": bool(meta.get("initialized", False)),
            "launcher": meta.get("launcher") or "",
            "renderer": meta.get("renderer") or "",
            "softwareRenderer": bool(meta.get("softwareRenderer", False)),
            "consolePort": console_port(idx),
            "adbPort": adb_port(idx),
            "grpcPort": grpc_port(idx),
        }

    async def install_apk(self, idx: str, apk: Path) -> str:
        """在开着的实例里装一个 ``.apk``（``adb install -r``，同包名覆盖安装、保留数据）。

        只收单个 ``.apk``：``.xapk`` / 拆分包（``install-multiple``）不支持。返回 adb 的结果行。"""
        self._instance(idx)
        status = await self.getStatus(idx)
        if status != DeviceStatus.ONLINE:
            raise RuntimeError(f"魔改 AVD 实例 {idx} 没有开机，请先开机再安装 APK")
        logger.info(f"魔改 AVD 实例 {idx} 安装 APK: {apk}")
        code, output = await host.run_adb(
            self.root,
            "install",
            "-r",
            str(apk),
            serial=host.serial_of(console_port(idx)),
            timeout=APK_INSTALL_TIMEOUT_SECONDS,
        )
        lines = [line.strip() for line in (output or "").splitlines() if line.strip()]
        last = lines[-1] if lines else ""
        if code != 0 or not last.startswith("Success"):
            logger.warning(f"魔改 AVD 实例 {idx} 安装 {apk.name} 失败: {output}")
            raise RuntimeError(f"安装 {apk.name} 失败：{last or f'adb 返回 {code}'}")
        logger.info(f"魔改 AVD 实例 {idx} 已安装 {apk.name}")
        return last

    def set_headless(self, idx: str, headless: bool) -> dict[str, Any]:
        return self.set_instance_options(idx, headless=headless)

    def set_instance_options(
        self,
        idx: str,
        *,
        headless: bool | None = None,
        resolution: str | None = None,
        memory_mb: int | None = None,
        balloon: bool | None = None,
        guest_angle: bool | None = None,
    ) -> dict[str, Any]:
        """改实例的 MAS 侧选项，下次启动生效。``None`` = 不改。

        显示档位在开机前才写进 ``config.ini``（实例在跑时改配置文件没用，还可能被它自己读到一半）。
        """
        self._instance(idx)
        changes: dict[str, Any] = {}
        if headless is not None:
            changes["headless"] = bool(headless)
        if resolution is not None:
            changes["resolution"] = validate_resolution(resolution)
        if memory_mb is not None:
            changes["memoryMb"] = validate_memory(memory_mb)
        if balloon is not None:
            changes["balloon"] = bool(balloon)
        if guest_angle is not None:
            changes["guestAngle"] = bool(guest_angle)
        if changes:
            update_instance_meta(self.root, idx, **changes)
            logger.info(f"已修改官方模拟器实例 {idx} 的选项（下次启动生效）: {changes}")
        return self.instance_options(idx)


def _int(raw: object) -> int | None:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _resolution_of(width: int | None, height: int | None, dpi: int | None) -> str:
    """宽高 + DPI → 显示档位（横竖屏都认）；不是两档之一就拒绝，不做静默吸附。"""
    sides = sorted((width or 0, height or 0), reverse=True)
    for name, (long_side, short_side, density) in RESOLUTIONS.items():
        if sides == [long_side, short_side] and dpi == density:
            return name
    raise ValueError(
        "官方模拟器的显示只有两档：720p（1280×720、DPI 240）与 1080p（1920×1080、DPI 280）"
    )


class AvdHostAdb:
    """MAS 宿主进程对一台官方模拟器实例发 adb 命令的通道：私有 server ``-P <adbServerPort>
    -s emulator-<控制台端口>``。脚本的 adb server 杀不到它，丢设备时 :func:`host.run_adb` 会重新登记。

    调用约定同 :data:`~..applaunch.AdbRunner`：``await runner(*args, timeout=…)`` → ``(返回码, 输出)``。
    给游戏更新检查（:func:`app.utils.game_apk.adb_runner_scope`）与失败截图用。
    """

    def __init__(self, root: Path, native_index: str) -> None:
        self.root = Path(root)
        self.native_index = str(native_index)
        self.serial = host.serial_of(console_port(native_index))

    async def __call__(self, *args: str, timeout: float = 20.0) -> tuple[int, str]:
        return await host.run_adb(self.root, *args, serial=self.serial, timeout=timeout)

    async def screencap_png(self, timeout: float = 30.0) -> bytes:
        """``exec-out screencap -p`` 的 PNG 字节；失败抛 ``RuntimeError``。"""
        code, data, error = await host.run_adb_bytes(
            self.root,
            "exec-out",
            "screencap",
            "-p",
            serial=self.serial,
            timeout=timeout,
        )
        if code != 0 or not data.startswith(b"\x89PNG"):
            raise RuntimeError(
                f"官方模拟器实例 {self.native_index} 截图失败（返回码 {code}）: {error[-200:]}"
            )
        return data


class AvdManager(AppLaunchMixin, _AvdCore):
    """一条官方模拟器安装的管理器。

    ``AppLaunchMixin.open`` 先开机再拉应用；这里在它之前挡掉已知不兼容的游戏（连模拟器都不开），
    并把拉应用改走私有 adb、先结束其它第三方游戏。
    """

    store_package = None

    def host_adb(self, idx: str) -> AvdHostAdb:
        """宿主进程对这台实例发 adb 命令的通道（走私有 server，见 :class:`AvdHostAdb`）。"""
        self._instance(idx)
        return AvdHostAdb(self.root, str(idx))

    async def open(self, idx: str, package_name: str = "") -> DeviceInfo:
        if package_name:
            reason = incompatible_reason(package_name)
            if reason is not None:
                raise IncompatibleGameError(reason)
            known = _VULKAN_UNSUPPORTED.get(_instance_key(self.root, str(idx)))
            if known is not None and package_name in VULKAN_FIX_PACKAGES:
                raise IncompatibleGameError(known)
        # AppLaunchMixin 有意不把包名传给开机那一步；开机时要对照推荐内存记日志，所以在这里记下
        self._open_package = package_name or ""
        return await super().open(idx, package_name)

    async def launch_app(
        self,
        idx: str,
        package_name: str,
        info: DeviceInfo | None = None,
        *,
        launch_timeout: float | None = None,
    ) -> AppLaunchResult:
        reason = incompatible_reason(package_name)
        if reason is not None:
            raise IncompatibleGameError(reason)
        if package_name in VULKAN_FIX_PACKAGES:
            await self.ensure_vulkan_fix(idx)
        serial = host.serial_of(console_port(idx))
        root = self.root

        async def run_adb(*args: str, timeout: float = 20.0) -> tuple[int, str]:
            return await host.run_adb(root, *args, serial=serial, timeout=timeout)

        await self.stop_background_games(idx, keep=package_name)
        if package_name in STARTUP_GUARD_PACKAGES:
            result = await self.guarded_launch(idx, package_name)
            if result is not None:
                return result
        max_wait = float(self.config.get("Info", "MaxWaitTime"))
        return await ensure_app_running(
            run_adb,
            package_name,
            boot_timeout=min(max_wait, _BOOT_TIMEOUT_CAP),
            launch_timeout=launch_timeout or min(max_wait, _LAUNCH_TIMEOUT_CAP),
            label=str(idx),
        )

    async def guarded_launch(
        self, idx: str, package_name: str
    ) -> AppLaunchResult | None:
        """带启动看门狗拉起游戏（:mod:`.startup_watchdog`，崩坏三用）。

        强停 → 拉起 → 每 3 秒采样；启动卡死就留证据、强停、重开，最多重开 5 次。第一次启动成功就返回，
        看门狗在后台继续看到拉起后第 300 秒，期间死锁同样重开。看门狗自己出错（例如客体没有 ``su``）
        返回 ``None``，调用方按普通方式拉起。

        avd-game.ps1 拉起前丢弃客体 ping 的 iptables 规则不搬：那是给原版 slirp 的 ICMP 套接字堆积兜底的
        （崩坏三每次启动 ping 约 700 次/秒，拖垮 slirp 主循环）。这里只支持官方模拟器内测包里的自编版
        （开机前检查拒绝原版），自编版从 sdk-mas9 起已在模拟器里修好。
        """
        _, output = await self._shell(idx, f"pm path {package_name}")
        if is_package_missing(output):
            logger.warning(f"实例 {idx} 未安装 {package_name}，不再尝试启动")
            return AppLaunchResult(False, "not-installed")
        key = _instance_key(self.root, idx)
        _cancel_game_guard(key)
        port = console_port(idx)
        label = f"实例 {idx} {package_name}"

        async def shell(command: str) -> str:
            _, text = await self._shell(idx, command, timeout=20)
            return text

        async def stop() -> None:
            await self._shell(idx, f"am force-stop {package_name}")

        async def launch() -> None:
            _, resolved = await self._shell(
                idx,
                "cmd package resolve-activity --brief "
                f"-c android.intent.category.LAUNCHER {package_name}",
            )
            component = parse_launch_component(resolved, package_name)
            if component:
                await self._shell(idx, f"am start -n {component}")
            else:
                await self._shell(
                    idx,
                    f"monkey -p {package_name} -c android.intent.category.LAUNCHER 1",
                )

        async def evidence(why: str, attempt: int, pid: int | None) -> dict[str, str]:
            if not pid:
                return {}
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            path = (
                self._log_dir()
                / f"startup-{package_name}-{stamp}-a{attempt}-{why}-threads.txt"
            )
            text = await shell(su_command(EVIDENCE_PROBE.replace("@PID@", str(pid))))
            path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(path.write_text, text, encoding="utf-8")
            return {"threads": str(path)}

        guard = StartupGuard(
            StartupSampler(shell, package_name, ScreenDiff(shm_thumb(port))),
            StartupHangDetector(
                STARTUP_GUARD_AFTER_SECONDS,
                STARTUP_GUARD_STATIC_SECONDS,
                STARTUP_GUARD_IDLE_CORES,
                STARTUP_GUARD_HARD_SECONDS,
            ),
            launch=launch,
            stop=stop,
            retries=STARTUP_GUARD_RETRIES,
            interval=STARTUP_GUARD_INTERVAL_SECONDS,
            start_timeout_s=STARTUP_GUARD_START_TIMEOUT_SECONDS,
            stall=ReadyStallDetector(
                STARTUP_GUARD_STALL_SECONDS, STARTUP_GUARD_STALL_CORES
            ),
            watch_s=STARTUP_GUARD_WATCH_SECONDS,
            evidence=evidence,
            log=lambda record: _log_guard_record(label, record),
        )
        logger.info(f"{label}: 带启动看门狗拉起")
        task = asyncio.create_task(
            _run_guard(label, guard), name=f"avd-game-guard-{key}"
        )
        _GAME_GUARDS[key] = task
        task.add_done_callback(
            lambda t: (
                _GAME_GUARDS.pop(key, None) if _GAME_GUARDS.get(key) is t else None
            )
        )
        waiter = asyncio.create_task(guard.started.wait())
        try:
            await asyncio.wait({task, waiter}, return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:
            # 调用方不等了（任务被停、open 超时）：还没启动成功的看门狗不能留在后台接着强停 / 重开游戏
            if not guard.started.is_set():
                _cancel_game_guard(key)
            raise
        finally:
            waiter.cancel()
        if guard.started.is_set():
            return AppLaunchResult(True, "launched")
        result = task.result()
        if result.get("result") == "error":
            return None
        return AppLaunchResult(
            False,
            "startup-hang",
            f"启动看门狗重开 {result.get('relaunches', 0)} 次后仍未启动成功",
        )

    async def ensure_vulkan_fix(self, idx: str) -> str:
        """拉起星铁前的 Vulkan 修复：客体驱动补丁 bind mount，再重启 zygote，等 framework 回来。

        照启动器 ``-VulkanFix``。改好的库缓存在客体 ``/data/local/tmp``，下次开机直接 mount；没有
        缓存时从客体拉出原库，在这里核对 sha256、改 5 字节、推回去（:mod:`.vulkanfix`）。哈希对不上
        就不打补丁，抛 :class:`IncompatibleGameError`（「这个镜像版本不支持星铁普通模式」）。
        重启 zygote 会结束客体上所有应用，所以只在拉起星铁前做；本次开机已经做过就什么都不做。
        同一实例串行做（并发拉起时不会挂两次、重启两次 zygote）。返回客体脚本的状态词（MOUNTED / ALREADY）。
        镜像不对的结论记在进程里，之后对这台实例拉星铁直接报错、不再开机（脚本的重试会一遍遍重开模拟器）。
        """
        key = _instance_key(self.root, idx)
        async with _VULKAN_LOCKS.setdefault(key, asyncio.Lock()):
            try:
                return await self._ensure_vulkan_fix(idx)
            except IncompatibleGameError as e:
                _VULKAN_UNSUPPORTED[key] = str(e)
                raise

    async def _ensure_vulkan_fix(self, idx: str) -> str:
        remote = f"{GUEST_TMP_DIR}/vulkanfix.sh"
        if not await self._push(idx, guest_script("vulkanfix.sh"), remote):
            raise RuntimeError(f"实例 {idx} 推送星铁 Vulkan 修复脚本失败")

        async def run_fix() -> str:
            _, output = await self._shell(
                idx,
                f"su 0 sh {remote} {VULKAN_ENC_ORIG_SHA256} {VULKAN_ENC_FIX_SHA256}",
                timeout=60,
            )
            return output.strip()

        _, ui_before = await self._shell(idx, "pidof com.android.systemui")
        status = await run_fix()
        if status.startswith("NEED_UPLOAD"):
            await self._upload_patched_vulkan(idx)
            status = await run_fix()
        if status.startswith("ALREADY"):
            logger.info(f"实例 {idx} 星铁 Vulkan 修复本次开机已生效")
            return "ALREADY"
        if not status.startswith("MOUNTED"):
            logger.warning(f"实例 {idx} 星铁 Vulkan 修复没做: {status}")
            if status.startswith("SKIPPED image"):
                raise IncompatibleGameError(
                    f"{UNSUPPORTED_IMAGE_MESSAGE}（客体驱动库不是预期版本，没有打补丁）"
                )
            if status.startswith("SKIPPED patched"):
                # 客体里那份改好的库校验不对（写入失败、空间不足）：脚本已把它删掉，下次重新生成上传。
                # 不是镜像问题，可以重试
                raise RuntimeError(
                    f"实例 {idx} 星铁 Vulkan 修复没挂上：客体里改好的驱动库副本校验不对"
                    "（可能客体空间不足或写入失败），已删掉坏副本，下次拉起时重新生成"
                )
            raise RuntimeError(f"实例 {idx} 星铁 Vulkan 修复失败: {status[-200:]}")
        started = time.monotonic()
        back = await self._wait_framework_back(idx, ui_before.strip())
        logger.info(
            f"实例 {idx} 星铁 Vulkan 修复已挂上，zygote 重启后 framework "
            f"{'已回来' if back else '超时未回来'}（{time.monotonic() - started:.0f} 秒）"
        )
        return "MOUNTED"

    async def _upload_patched_vulkan(self, idx: str) -> None:
        """拉客体原库 → 核对哈希并打补丁 → 推到客体的上传位置。宿主侧临时文件用完即删。"""
        serial = host.serial_of(console_port(idx))
        work = self.root / CACHE_DIR
        work.mkdir(parents=True, exist_ok=True)
        original = work / f"libvulkan_enc-{idx}.so"
        patched = work / f"libvulkan_enc-{idx}.khrfix.so"
        try:
            code, output = await host.run_adb(
                self.root,
                "pull",
                VULKAN_ENC_GUEST_PATH,
                str(original),
                serial=serial,
                timeout=60,
            )
            if code != 0 or not original.is_file():
                raise RuntimeError(f"从客体拉驱动库失败: {output}")
            try:
                data = await asyncio.to_thread(
                    patch_vulkan_encoder, original.read_bytes()
                )
            except VulkanFixError as e:
                raise IncompatibleGameError(str(e)) from e
            patched.write_bytes(data)
            code, output = await host.run_adb(
                self.root,
                "push",
                str(patched),
                f"{GUEST_TMP_DIR}/khrfix-upload.so",
                serial=serial,
                timeout=60,
            )
            if code != 0:
                raise RuntimeError(f"推送改好的驱动库失败: {output}")
            logger.info(f"实例 {idx} 已在本机生成星铁 Vulkan 补丁库并推到客体")
        finally:
            original.unlink(missing_ok=True)
            patched.unlink(missing_ok=True)

    async def _wait_framework_back(
        self, idx: str, ui_before: str, timeout: float = 120.0
    ) -> bool:
        """zygote 重启后等 SystemUI 换了新进程，再多等 8 秒（照启动器）。"""
        deadline = time.monotonic() + timeout
        await asyncio.sleep(2.0)
        while time.monotonic() < deadline:
            _, ui = await self._shell(idx, "pidof com.android.systemui", timeout=10)
            ui = ui.strip()
            if ui and ui != ui_before:
                await asyncio.sleep(8.0)
                return True
            await asyncio.sleep(2.0)
        return False

    async def stop_background_games(self, idx: str, keep: str) -> list[str]:
        """前台只留要跑的那个游戏，其余第三方应用直接结束（用户 09-26 定）。

        只动 ``pm list packages -3``（用户装的应用）；系统包、谷歌服务不在其中。桌面与当前
        输入法另外排除。冻结不释放内存，低内存下后台游戏应当直接结束（预研 §6.11）。
        """
        code, output = await self._shell(idx, "pm list packages -3")
        if code != 0:
            logger.warning(f"实例 {idx} 列第三方应用失败，跳过后台清理: {output}")
            return []
        packages = [
            line.split(":", 1)[1].strip()
            for line in output.splitlines()
            if line.startswith("package:")
        ]
        _, ime = await self._shell(idx, "settings get secure default_input_method")
        ime_package = ime.strip().split("/", 1)[0]
        targets = [
            package
            for package in packages
            if package != keep
            and package not in KEEP_PACKAGES
            and package != ime_package
        ]
        if not targets:
            return []
        await self._shell(
            idx, " ; ".join(f"am force-stop {package}" for package in targets)
        )
        logger.info(f"实例 {idx} 已结束后台应用: {targets}")
        return targets


async def build_manager(
    manager_exe: str, max_wait_time: int, force_kill_on_close: bool = False
) -> AvdManager:
    """与雷电 / MuMu 的 ``build_manager`` 同签名。``manager_exe`` 是 ``sdk\\emulator\\emulator.exe``。"""
    exe = emulator_exe(root_from_manager_exe(manager_exe))
    if not exe.is_file():
        raise RuntimeError(f"找不到官方模拟器程序 {exe}")
    return AvdManager(manager_exe, max_wait_time, force_kill_on_close)


__all__ = [
    "AvdManager",
    "FreezeWatchdog",
    "IncompatibleGameError",
    "build_manager",
    "emulator_exe",
    "incompatible_reason",
    "shm_exists",
]
