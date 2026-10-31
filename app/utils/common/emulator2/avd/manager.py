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

"""魔改 AVD 一条安装的设备管理器。

对门面暴露的方法与雷电 / MuMu 两家后端相同（``open`` / ``close`` / ``getStatus`` /
``getInfo`` / ``list_devices`` / 四项设置 / 稳定模式 / 新建删除实例），区别在于这里没有厂商
管理器可调，每一步都是自己驱动 ``emulator.exe`` 与私有 adb。

启动 = 冷启动（``-no-snapshot``，与 MAS 对雷电 / MuMu 每轮开关一致，预研 §6.16），默认无头
（= 静默模式，预研 §6.14）。启动参数与开机后的调优逐项照 aemu-lab 的启动器 ``avd-p0.ps1``
（每个开关都真机验证过，原因写在对应函数里）：磁盘 write-through、静音且不带声卡、固定 720p、
实例内存、空闲页上报、Vulkan 描述符批量更新、宿主调度、截图共享内存、cpuinfo、WiFi + fastpath、
客体日志落盘、客体 Vulkan 驱动补丁。启动器里没有的一项：数据盘请求密集时不让 vCPU 停机
（``res/avd/guest/mas-idlepoll.sh``）。
首次开机后再做一次持久初始化（关蓝牙、去全屏提示、禁用手机预装应用、换轻量桌面、记录渲染器）。

关机默认让安卓自己正常关机、等 qemu 自己退出，不成再退回 ``sync`` + 控制台 ``kill``：控制台
``kill`` 直接结束 qemu，客体不走关机流程，页缓存里没写回的数据会丢（10-03 星铁 9 个热更新清单因此
变成 0 字节），``sync`` 之后到 qemu 退出之间游戏写的东西也会丢（见 :meth:`AvdManager.close`）。
"""

from __future__ import annotations

import asyncio
import tempfile
import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import psutil

from app.models.emulator import (
    DeviceBase,
    DeviceInfo,
    DeviceRef,
    DeviceStatus,
    EmulatorRuntimePolicy,
)
from app.utils import emulator_native, get_logger

from ..applaunch import (
    AppLaunchMixin,
    AppLaunchResult,
    ensure_app_running,
)
from ..settings import FieldValue, InstanceSettings, SettingsConflictError
from ..settings import validate_changes as validate_setting_changes
from . import host, precheck, update_stage, updater
from .components import (
    component_installed,
    emulator_exe,
    launcher_apk,
    manager_key_exe,
    missing_components_message,
    root_from_manager_exe,
    root_key,
)
from .constants import (
    ADB_SERVER_START_TIMEOUT_ON_CLOSE_SECONDS,
    APK_INSTALL_TIMEOUT_SECONDS,
    BALLOON_PAGE_REPORTING_ORDER,
    CLOSE_TIMEOUT_SECONDS,
    CONSOLE_KILL_TIMEOUT_SECONDS,
    DEBLOAT_PACKAGES,
    FALLBACK_FORCE_KILL_WAIT_SECONDS,
    FALLBACK_KILL_TIMEOUT_SECONDS,
    FALLBACK_SYNC_TIMEOUT_SECONDS,
    FORCE_KILL_WAIT_SECONDS,
    GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS,
    GUEST_DIRTY_EXPIRE_CENTISECS,
    GUEST_DIRTY_WRITEBACK_CENTISECS,
    GUEST_PATCH_DIR,
    GUEST_TMP_DIR,
    KEEP_PACKAGES,
    LIGHT_LAUNCHER,
    LIGHT_LAUNCHER_PREFS_FILE,
    LIGHT_LAUNCHER_PREFS_VERSION,
    LIGHT_LAUNCHER_PRESET_PREFS,
    LIGHT_LAUNCHER_WAKE_RECEIVER,
    LOGCAT_BUFFER_SIZE,
    LOGS_DIR,
    MAX_NATIVE_INDEX,
    PIXEL_LAUNCHER_PACKAGE,
    PORT_BASE,
    PORT_STEP,
    RECOMMENDED_MEMORY_MB,
    REQUIRED_COMPONENTS,
    SCREEN_DENSITY,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    SYNC_TIMEOUT_SECONDS,
    VULKAN_ENC_GUEST_PATH,
    VULKAN_FIX_UPLOAD_PATH,
    WATCHDOG_INTERVAL_SECONDS,
    WATCHDOG_PROBE_TIMEOUT_SECONDS,
    WATCHDOG_STRIKES,
    adb_port,
    avd_name,
    console_port,
    grpc_port,
    valid_native_index,
)
from .instances import (
    AvdInstance,
    apply_display,
    create_instance_files,
    delete_instance_files,
    display_changes,
    instance_meta,
    list_instances,
    memory_for,
    update_instance_meta,
    validate_fps,
    validate_options,
    write_instance_config,
)
from .vulkanfix import (
    VULKAN_ENC_FIX_SHA256,
    VULKAN_ENC_ORIG_SHA256,
    VulkanFixError,
    patch_vulkan_encoder,
    sha256,
)

logger = get_logger("魔改 AVD 管理")

#: ``{根目录键: 锁}``：同一条安装同时只生成一次客体驱动补丁库（几台实例一起开机时）。
_VULKAN_PATCH_LOCKS: dict[str, asyncio.Lock] = {}

#: 等 ``sys.boot_completed`` 的轮询间隔。
_BOOT_POLL_SECONDS = 1.0
#: 状态查询里单条 adb 的超时：状态轮询不能被一台卡住的实例拖住整张表。
_STATUS_ADB_TIMEOUT = 5.0
#: 装轻量桌面的超时。
_INSTALL_TIMEOUT = 180.0
#: 给申请了「安装未知应用」权限、这一项还是默认模式（没设过或设回了 default）的应用放行（``android``
#: 自己除外），逐行打出本次放行了谁。设成别的模式的（用户在设置里手动关掉或打开过，或以前开机已放行）保持不动；
#: 读不出当前模式（``appops get`` 非零）的不写，按失败算。枚举失败退出码 2；任一应用放行
#: 失败打「failed: 包名」，其余照做，最后退出码 1。包名从 ``dumpsys package packages`` 里按
#: 「Package [包名]」段落取，实测 70 ms 左右。dumpsys 找不到服务也返回 0，所以一个段落都没有就算枚举失败。
_ALLOW_INSTALL_SOURCES_SCRIPT = (
    "set -o pipefail; "
    "list=$(dumpsys package packages 2>/dev/null"
    " | awk '/^  Package \\[/ { n++; p = substr($2, 2, length($2) - 2) }"
    ' /android.permission.REQUEST_INSTALL_PACKAGES/ { if (p != "" && p != "android") print p }'
    " END { if (n == 0) exit 3 }'"
    ' | sort -u) || { echo "dumpsys package failed"; exit 2; }; '
    "fail=0; "
    "for p in $list; do"
    ' m=$(appops get "$p" REQUEST_INSTALL_PACKAGES 2>&1)'
    ' || { echo "failed: $p"; fail=1; continue; };'
    ' case "$m" in'
    ' *"REQUEST_INSTALL_PACKAGES: default"*) ;;'
    ' *"REQUEST_INSTALL_PACKAGES: "*) continue ;; esac;'
    ' if appops set "$p" REQUEST_INSTALL_PACKAGES allow; then echo "$p";'
    ' else echo "failed: $p"; fail=1; fi;'
    " done; exit $fail"
)
#: 界面上「打开游戏中心」之类一次点击的上限（魔改 AVD 没有游戏中心，留作接口一致）。
_LAUNCH_TIMEOUT_CAP = 45.0
_BOOT_TIMEOUT_CAP = 120.0


def _shared_prefs_entry(key: str, value: bool | str) -> str:
    """一条 SharedPreferences 的 XML（和 Android 自己写的格式一样，字符串里的 ``"`` 写成 ``&quot;``）。

    这一条要原样放进客体 sed 命令的双引号里，所以不收会被 shell / sed 另作解释的字符。
    """
    if isinstance(value, bool):
        text = f'<boolean name="{key}" value="{str(value).lower()}" />'
    else:
        escaped = (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
        text = f'<string name="{key}">{escaped}</string>'
    if any(char in text for char in "'#\\$`\n"):
        raise ValueError(f"偏好 {key} 里有客体命令放不下的字符")
    return text


def shm_exists(port: int) -> bool:
    return emulator_native.shm_exists(port)


def _silence_enabled(runtime_policy: EmulatorRuntimePolicy) -> bool:
    """宿主「静默模式」开没开；读不到按开，宁可无头。"""
    try:
        return bool(runtime_policy.silence_enabled())
    except Exception:  # noqa: BLE001
        return True


# ---- 启动参数 -------------------------------------------------------------


def build_launch_args(
    avd: str,
    console: int,
    *,
    memory_mb: int,
    headless: bool,
) -> list[str]:
    """``emulator.exe`` 的参数，逐项照启动器 ``avd-p0.ps1``（每个开关都真机验证过）。

    有没有窗口不是实例选项（用户 10-04 定），开机那一刻按启动入口定，见 :meth:`AvdManager.open`。
    旧 ``mas-avd.json`` 里留下的 ``headless`` / ``resolution`` / ``guestAngle`` / ``audio`` /
    ``balloon`` 一律不读：显示固定 720p、不带声卡、不开 GuestAngle、气球固定开。

    - 冷启动（``-no-snapshot``），与 MAS 对雷电 / MuMu 每轮开关一致；
    - 开机动画只在无头时关（``-no-boot-anim``）：带窗口开机时窗口里有东西看，不再黑屏到出桌面
      （用户 10-21 提）；
    - ``-audio none``：宿主不出声（用户 09-27 定）；
    - ``-feature -VirtioSndCard``：客体里不带声卡（用户 10-04 定）。本镜像的客体声卡是 virtio-snd，
      不认 ``config.ini`` 的 ``hw.audioOutput`` / ``hw.audioInput``（10-04 实测两项写 no 照样有声卡），
      只能关掉这个特性；关掉后 ``/proc/asound/cards`` 为空。1999 主界面上 qemu CPU 中位数 147% → 104%
      （单核百分比，各测一轮）；
    - ``-memory``：实例设的客体内存（:func:`~.instances.memory_for`），不改 ``hw.ramSize``；
    - 气球（空闲页上报）固定开，不是实例选项（用户 10-12 定）；要自编 qemu（sdk-mas19 起）。
      ``QuickbootFileBacked`` 开着时冷启动也用 ``ram.img`` 文件映射当客体内存，qemu 丢不掉
      文件映射的页，空闲页上报就不生效（10-03 首测），所以关掉它；设备挂在 ``-qemu`` 最后，
      占下一个空闲 PCI 槽、不挪现有设备；
    - ``-feature VulkanBatchedDescriptorSetUpdate``（固定开）：描述符集批量更新。宿主
      ``advancedFeatures.ini`` 默认关、镜像那边开着；不开时终末地渲染线程 67.5% 的时间耗在
      ``vkAllocateDescriptorSets`` 的同步往返上（每帧 159 次），开了 MaaEnd 跑任务时帧率均值
      12.8 → 30.5（aemu-lab 修复队列「终末地帧率与稳定性」）。星铁、1999 回归都带着它跑过；
    - 磁盘 write-through：客体不再发 flush（和以前客体侧 ``nobarrier`` 一样快），但 QEMU 每次写
      都把数据和 qcow2 元数据推到宿主文件，硬杀不丢已写的数据。``nobarrier`` 硬杀 3/3 把 AVD
      弄坏（内核 panic 循环），这个设置 6/6 无损（09-26）。``-qemu`` 之后全归 QEMU，所以放最后。
    """
    args = [
        "-avd",
        avd,
        "-no-snapshot",
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
    if headless:
        args += ["-no-window", "-no-boot-anim"]
    args += ["-feature", "-QuickbootFileBacked"]
    args += ["-feature", "-VirtioSndCard"]
    args += ["-feature", "VulkanBatchedDescriptorSetUpdate"]
    args += [
        "-qemu",
        "-global",
        "virtio-blk-device.write-cache=off",
        "-global",
        "virtio-blk-device.config-wce=off",
        "-device",
        "virtio-balloon-pci,free-page-reporting=on",
    ]
    return args


# ---- 冻结看门狗 -----------------------------------------------------------

#: ``{根目录键|原生索引: 看门狗任务}``。管理器会被频繁重建（状态轮询每轮一个），
#: 看门狗必须挂在模块上，跟着实例走而不是跟着管理器对象走。
_WATCHDOGS: dict[str, asyncio.Task] = {}
#: ``{根目录键|原生索引: 事件}``：这台实例有一次 open 正在开机 / 做开机后设置，做完置位。和看门狗一样
#: 挂在模块上（管理器对象会被频繁重建）。见 :meth:`_AvdCore.open`。
_OPENING: dict[str, asyncio.Event] = {}
#: 等前一次 open 的上限 = 最长启动等待 + 这么多秒（开机后设置里 zygote 重启最多等 120 秒，再留余量）。
_OPENING_WAIT_EXTRA_SECONDS = 300.0


async def _claim_opening(key: str, label: str, timeout: float) -> asyncio.Event:
    """排到这台实例的 open：前面有 open 没做完就一个个等，轮到时登记自己的标记并返回它。

    一次置位会唤醒所有等待者，所以要循环：醒来后标记已被另一个等待者抢先登记，就接着等它。
    跳出循环和登记之间没有 ``await``，不会有两个同时登记。总共最多等 ``timeout`` 秒，
    超时记日志、照样登记自己（顶替前一次的标记）再继续：「开机中」这张表是更新器判断能不能开始更新的
    依据，不能有开机却不在表里的时候。前一次做完时只删仍是它自己的标记，不会删掉这一次的。
    """
    deadline = time.monotonic() + timeout
    started = time.monotonic()
    waited = False
    while (event := _OPENING.get(key)) is not None:
        if not waited:
            logger.info(f"{label} 正由另一次启动开机或做开机后设置，等它做完再继续")
            waited = True
        remaining = deadline - time.monotonic()
        try:
            if remaining <= 0:
                raise TimeoutError
            await asyncio.wait_for(event.wait(), remaining)
        except TimeoutError:
            logger.warning(
                f"{label} 等另一次启动超过 {timeout:.0f} 秒仍没做完，不再等，照常继续"
            )
            waited = False
            break
    if waited:
        logger.info(
            f"{label} 另一次启动已做完（等了 {time.monotonic() - started:.0f} 秒）"
        )
    mine = _OPENING[key] = asyncio.Event()
    return mine


#: ``{根目录键|原生索引: 锁}``：这台实例有一次 close 正在做。正常关机要等 qemu 自己退出（最多十几秒），
#: 这段时间 qemu 还在：同一台实例的 close 要排队，否则后一次会在前一次正常关机的半途退回 kill；
#: open 也要先等它关完，否则会把正在关机的实例当成已在运行。close 不等 open（开机中照样能关）。
_CLOSING: dict[str, asyncio.Lock] = {}


async def _wait_closing(key: str, label: str) -> None:
    """这台实例正在关机就等它关完（close 自身最多 28 秒，见 constants 关机那一组）。"""
    lock = _CLOSING.get(key)
    if lock is None or not lock.locked():
        return
    logger.info(f"{label} 正在关机，等它关完再开机")
    async with lock:
        pass


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
        f"魔改 AVD 实例 {avd_name(native_index)}",
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


# ---- 客体日志落盘 ---------------------------------------------------------


async def prune_logs(root: Path, idx: str) -> None:
    """建新日志前清一次这台实例的旧日志（:func:`~.host.prune_logs`）。清理失败不影响开机。"""
    try:
        await asyncio.to_thread(host.prune_logs, root, idx)
    except Exception as e:  # noqa: BLE001 - 清日志失败不能挡住开机
        logger.warning(f"实例 {idx} 清理旧日志失败: {e}")


async def ensure_logcat(root: Path, idx: str) -> bool:
    """这台实例没有在落盘的 logcat 就起一个（文件 ``<根>\\logs\\logcat-mas_<i>-<时间>.txt``），返回起没起。

    按宿主进程表判断（:func:`~.host.find_logcat_processes`），不按本进程的记录：后端重启后上一个
    进程起的还在跑，不能再起第二份；私有 server 重启时 logcat 客户端会跟着退出，要能重新起来。
    开机后、重新登记成功后、冻结看门狗每轮巡检时都会调。
    """
    serial = host.serial_of(console_port(idx))
    if await asyncio.to_thread(host.find_logcat_processes, root, serial):
        return False
    await prune_logs(root, idx)
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


# ---- 管理器 ---------------------------------------------------------------


class _AvdCore(DeviceBase):
    """只负责开关机与状态，不带应用拉起（由 :class:`AvdManager` 叠上）。"""

    def __init__(
        self,
        manager_exe: str | Path,
        max_wait_time: int,
        force_kill_on_close: bool,
        *,
        resource_path: Path | None = None,
    ) -> None:
        self.emulator_path = Path(manager_exe)
        self.root = root_from_manager_exe(manager_exe)
        # 关闭与状态查询不需要内置资源；启动资源由宿主明确提供。
        self.resource_path = resource_path
        self.config = SimpleNamespace(
            Info=SimpleNamespace(
                MaxWaitTime=int(max_wait_time),
                ForceKillOnClose=bool(force_kill_on_close),
                Type="avd",
                Path=str(manager_exe),
            )
        )

    # ---- 查询 -----------------------------------------------------------

    def _guest_script(self, name: str) -> Path:
        if self.resource_path is None:
            raise ValueError("启动魔改 AVD 时必须提供内置资源目录")
        return self.resource_path / "avd" / "guest" / name

    def _instances(self) -> dict[str, AvdInstance]:
        return list_instances(self.root)

    def _instance(self, idx: str) -> AvdInstance:
        instance = self._instances().get(str(idx))
        if instance is None:
            raise RuntimeError(f"魔改 AVD 实例 {idx} 不存在")
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

    def _device_info(
        self,
        idx: str,
        title: str,
        status: DeviceStatus,
        process: psutil.Process | None = None,
    ) -> DeviceInfo:
        # 给脚本的是 adb 端口的 TCP 地址：脚本用自己的 adb connect 过去，与雷电 / MuMu 一致。
        # 不给 emulator-<端口> 这个序列号——它只在我们的私有 server（20050）上存在。
        started_at = None
        if process is not None:
            with suppress(psutil.Error):
                started_at = process.create_time()
        return DeviceInfo(
            title,
            status,
            f"127.0.0.1:{adb_port(idx)}",
            process_id=process.pid if process is not None else None,
            process_started_at=started_at,
        )

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
                raise RuntimeError(f"魔改 AVD 实例 {idx} 不存在")
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
        """显示 / 隐藏带窗口开机的实例（主窗口和侧边工具栏），照雷电用 ``SW_HIDE`` / ``SW_SHOW``。

        隐藏不影响渲染和截图：10-04 在 mas_6 带窗口开机、``SW_HIDE`` 30 秒，期间截图共享内存
        的帧号照常前进（约 51 帧/秒，显示时约 48 帧/秒），画面随客体操作照常变化。
        无头开机的实例没有窗口，开机后也补不出窗口，只记一笔。
        不抛异常：脚本在静默模式下每轮都会调这个，抛了会把整次运行判失败。
        """
        process = await asyncio.to_thread(
            host.find_qemu_process, avd_name(idx), console_port(idx)
        )
        if process is not None:
            try:
                set_visible = emulator_native.prepare_window_visibility()
                count = await asyncio.to_thread(
                    set_visible,
                    process.pid,
                    f"{avd_name(idx)}:{console_port(idx)}",
                    is_visible,
                )
            except Exception as e:  # noqa: BLE001 - 见 docstring
                logger.warning(
                    f"魔改 AVD 实例 {idx} {'显示' if is_visible else '隐藏'}窗口失败: {e}"
                )
            else:
                if count:
                    logger.info(
                        f"魔改 AVD 实例 {idx} 已{'显示' if is_visible else '隐藏'}窗口"
                    )
                elif is_visible:
                    logger.info(
                        f"魔改 AVD 实例 {idx} 是无头开机的，没有窗口可显示；"
                        "要窗口请关机后在模拟器页手动启动"
                    )
        return await self.getStatus(idx)

    # ---- 启动 -----------------------------------------------------------

    def _check_components(self) -> None:
        missing = [
            c.name for c in REQUIRED_COMPONENTS if not component_installed(self.root, c)
        ]
        if missing:
            raise RuntimeError(missing_components_message(missing))

    async def open(self, idx: str, package_name: str = "") -> DeviceInfo:
        """开机并做开机后设置。同一台实例上的 open 排队：前一次还没做完（开机后最后一步会重启 zygote），
        后一次先等它，免得后一次先返回在线、调用方拉起游戏，随后被前一次的 zygote 重启结束。
        等太久（:data:`_OPENING_WAIT_EXTRA_SECONDS` 加最长启动等待）就记日志、顶替前一次登记自己，照常往下走。"""
        idx = str(idx)
        instance = self._instance(idx)
        key = _instance_key(self.root, idx)
        max_wait = float(self.config.Info.MaxWaitTime)
        mine = await _claim_opening(
            key, f"魔改 AVD 实例 {idx}", max_wait + _OPENING_WAIT_EXTRA_SECONDS
        )
        try:
            await _wait_closing(key, f"魔改 AVD 实例 {idx}")
            return await self._open(idx, instance, key, max_wait)
        finally:
            mine.set()
            if _OPENING.get(key) is mine:
                del _OPENING[key]

    async def _open(
        self, idx: str, instance: AvdInstance, key: str, max_wait: float
    ) -> DeviceInfo:
        _FROZEN.pop(key, None)
        port = console_port(idx)

        process = await asyncio.to_thread(host.find_qemu_process, instance.name, port)
        launched = process is None
        serial = host.serial_of(port)
        try:
            if launched:
                # 开机期间所有路径（含面板每秒的状态轮询）都不替它重新登记
                host.BOOTING.add(serial)
                await self._launch(idx, instance)
            else:
                logger.info(f"魔改 AVD 实例 {idx} 已在运行（pid {process.pid}）")
            process = await self._wait_boot(idx, instance, launched, max_wait)
        finally:
            if launched:
                host.BOOTING.discard(serial)

        await self._after_boot(idx, instance, fresh_boot=launched)
        _start_watchdog(self.root, idx, process.pid)
        # 带上 qemu 进程号：开机后模拟器若被显卡驱动重置等原因带走（10-22 生产实例 0 就这样，
        # NVIDIA 驱动内核异常后结束了 qemu），MaaFW 等 adb 时能马上看出来，不再空等几分钟
        return self._device_info(
            idx, instance.title, DeviceStatus.ONLINE, process=process
        )

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
                    f"魔改 AVD 实例 {idx} 启动超时（{max_wait:.0f} 秒内安卓没有启动完成）"
                    f"，日志见 {self._log_dir()}"
                )
            if process is None and self._launcher is not None:
                code = self._launcher.poll()
                if code is not None:
                    raise RuntimeError(
                        f"魔改 AVD 实例 {idx} 启动失败（emulator.exe 退出码 {code}）："
                        f"{self._log_tail()}"
                    )
            await asyncio.sleep(_BOOT_POLL_SECONDS)

    _launcher = None
    _log_path: Path | None = None
    #: 这次 open 要跑的游戏包名（:class:`AvdManager` 在开机前设），只用来对照推荐内存记日志。
    _open_package: str = ""
    #: 这次开机要不要窗口（:class:`AvdManager` 在开机前按启动入口设）；没人设时按无头。
    _open_window: bool = False

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
        # 从点「更新」到更新结束都不许开机：sdk\emulator 会被换掉；用到它的脚本也就不会在更新中途启动
        if updater.update_in_progress(self.root):
            raise RuntimeError("魔改 AVD 正在更新，更新完再开机")
        self._check_components()
        # 电脑检查用的内存就是下面 -memory 要传的值：实例自己设的，不按游戏推算
        memory_mb = memory_for(instance_meta(self.root, idx))
        recommended = RECOMMENDED_MEMORY_MB.get(self._open_package or "")
        if recommended and memory_mb < recommended:
            logger.warning(
                f"魔改 AVD 实例 {idx} 内存 {memory_mb} MB，低于 {self._open_package} 的推荐值 "
                f"{recommended} MB，可在实例设置里调大"
            )
        await precheck.check_before_launch(self.root, memory_mb)

        port = console_port(idx)
        ports = [port, port + 1, port + 2]
        busy = await asyncio.to_thread(host.busy_ports, ports)
        if busy:
            raise RuntimeError(
                f"魔改 AVD 实例 {idx} 要用的端口 {', '.join(map(str, busy))} 已被占用，"
                "请先关闭占用它们的程序"
            )

        await host.ensure_adb_server(self.root)
        if await asyncio.to_thread(apply_display, self.root, idx):
            logger.info(f"实例 {idx} 显示改回 720p、不显示导航栏（已写入 config.ini）")
        headless = not self._open_window
        args = build_launch_args(
            instance.name,
            port,
            memory_mb=memory_mb,
            headless=headless,
        )
        await prune_logs(self.root, idx)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self._log_path = self._log_dir() / f"{instance.name}-{stamp}.log"
        logger.info(
            f"启动魔改 AVD 实例 {idx}（{'无头' if headless else '带窗口'}，"
            f"720p {instance.fps} Hz，{memory_mb} MB / {instance.cpu} 核，"
            "气球开，不带声卡，ANDROID_EMU_VK_HIDE_REBAR=1）: "
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

    async def _after_boot(
        self, idx: str, instance: AvdInstance, *, fresh_boot: bool = True
    ) -> None:
        """每次开机后的调优（重启即失效）+ 首次开机的一次性初始化。失败只记警告。

        ``fresh_boot``：这次 open 是不是刚把实例开起来。本来就在跑的实例不再挂客体驱动补丁
        （挂要重启 zygote，会把上面正在跑的游戏一起结束），见 :meth:`_ensure_vulkan_fix`。

        逐项照启动器 ``avd-p0.ps1`` 开机后那段。**不再做**的两项：
        ``gsm meter on|off``——每调一次，镜像的 MeterService 反而装上那个 2 GB 测试套餐（用量重置成
        200 MB），没有这条调用就没有套餐、没有上限（09-26 经 ``dumpsys netpolicy`` 确认）；
        ``/data`` 的 ``nobarrier``——改由启动参数让磁盘 write-through（见 :func:`build_launch_args`）。
        """
        port = console_port(idx)

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

        # 3) 磁盘与截图通道的现状写进日志（write_cache 要 root 才读得到）
        _, write_cache = await self._su(
            idx, "cat /sys/block/vd*/queue/write_cache | sort -u"
        )
        logger.info(
            f"实例 {idx} 磁盘缓存: {' / '.join(ln.strip() for ln in write_cache.splitlines() if ln.strip()) or '读不到'}；"
            f"截图共享内存 SHM_videmulator{port}: {'在' if shm_exists(port) else '缺失'}"
        )

        # 4) 客体脏页回写调短（硬杀时少丢数据，依据见常量注释；不持久，每次开机都设）
        await self._setup_guest_writeback(idx)

        # 5) 空闲页上报：驱动绑定时把 order 重置成 pageblock_order，绑定之后再设
        await self._setup_balloon(idx)

        # 6) ARM 转译层的 cpuinfo：每个 vCPU 一条，Unity 才不按单核选最低画质
        if await self._push(
            idx,
            self._guest_script("cpuinfo-bind.sh"),
            f"{GUEST_TMP_DIR}/cpuinfo-bind.sh",
        ):
            _, cores = await self._shell(
                idx, f"su 0 sh {GUEST_TMP_DIR}/cpuinfo-bind.sh"
            )
            logger.info(f"实例 {idx} ARM 转译 cpuinfo: {cores.strip() or '?'} 核")

        # 7) 崩溃 / 无响应弹窗没人点，挡在游戏前面；关掉（持久）
        await self._shell(idx, "settings put global hide_error_dialogs 1")

        # 7b) 关掉 NetworkWatchlistService（持久）：距上次开机满一天时，它为日报给每个 APK 整个算一遍
        #     SHA-256（明日方舟安装包一个就 1.8 GB，合计约 4 GB 读进页缓存），实例内存在宿主上整块常驻。
        #     开关在 system_server 启动时读：从下次开机起生效，第 11 步重启 zygote 后也不会再起来
        code, output = await self._shell(
            idx, "settings put global network_watchlist_enabled 0"
        )
        if code != 0:
            logger.warning(
                f"实例 {idx} 关闭 NetworkWatchlistService 失败（下次开机仍会把安装包整个读一遍）: "
                f"{output.strip()[-200:] or f'退出码 {code}'}"
            )

        # 7c) 允许从任何来源装 APK（持久，每次开机给新装的应用补上）：模拟器不是手机，浏览器里下的安装包、
        #     游戏自己下载的整包更新都不该被「出于安全考虑，不允许安装此来源的未知应用」拦下。
        #     用户在设置里手动改过的应用不动；每次安装仍由系统安装器弹窗让用户确认
        code, output = await self._shell(idx, _ALLOW_INSTALL_SOURCES_SCRIPT)
        if code != 0:
            logger.warning(
                f"实例 {idx} 放开「安装未知应用」没做完（这些来源装 APK 仍会被拦）: "
                f"{' '.join(output.split())[-300:] or f'退出码 {code}'}"
            )
        elif output.strip():
            logger.debug(f"实例 {idx} 本次允许安装未知应用: {' '.join(output.split())}")

        # 8) 网络：WiFi 一直开着（游戏看到 WiFi 就不弹「非 WiFi 下载」）；fastpath 把本地流量
        #    走 eth0（虚拟 WiFi 单独只有约 6 MB/s）。WiFi 开关存在 /data 里，每次开机都显式设
        await self._setup_network(idx)

        # 8b) 数据盘请求密集时（游戏下载每 8 KB fsync 一次）不让 vCPU 停机，省掉每次请求等 Hyper-V
        #     唤醒 vCPU 的时间；平时不动（依据见脚本头注释）
        await self._setup_idlepoll(idx)

        # 9) 客体日志：缓冲调到 16 MB（持久），开机后持续落盘到 <根>\logs，问题包要用
        await self._start_logcat(idx, instance)

        meta = instance_meta(self.root, idx)
        if not meta.get("initialized"):
            await self._first_boot_init(idx)

        # 10) 方向：显示器固定横屏（持久，每次开机设一次给老实例补上）
        await self._setup_orientation(idx)

        # 11) 客体 Vulkan 驱动补丁（bindlock2）。必须是最后一步：挂上后要重启 zygote，system_server
        #     和所有应用都会重来
        if await self._ensure_vulkan_fix(idx, fresh_boot=fresh_boot):
            # 信箱引导弹窗的开关在 system_server 内存里，跟着 zygote 重启丢了，再设一遍
            await self._setup_orientation(idx)

    async def _ensure_vulkan_fix(self, idx: str, *, fresh_boot: bool) -> bool:
        """把本机生成的客体驱动补丁库 bind mount 到 ``/vendor/lib64/libvulkan_enc.so`` 上，再重启 zygote。

        照启动器 ``avd-p0.ps1`` 的 ``-VulkanFix``，对所有实例、所有游戏统一挂（用户 10-16 定）。补丁
        （:mod:`.vulkanfix`）同时修星铁普通模式的描述符模板（khrfix）和终末地 ``vkBindImageMemory`` 查表的
        数据竞争（bindlock）；不走这两处的游戏（1999、M9A）不受影响。

        - 客体脚本 ``vulkanfix.sh`` 先看本次开机挂没挂过（挂过就什么都不做），再核对镜像原库的哈希
          （不是 ``898c0bbc…`` 就不挂）；改好的库缓存在客体 ``/data/local/tmp``，下次开机直接挂。
        - 客体里没有缓存时，从 ``<根>\\guest-patches`` 里本机生成过的那份推上去；本机也没有就从客体
          拉原库现场生成（:meth:`_patched_vulkan_library`）。改好的库**不随包分发**。
        - 本来就在跑的实例（``fresh_boot`` 为假）只查不挂：重启 zygote 会结束正在跑的游戏，下次开机再挂。

        失败只记日志，不挡开机。返回这次是否重启了 zygote。
        """
        remote = f"{GUEST_TMP_DIR}/vulkanfix.sh"
        if not fresh_boot:
            _, mounts = await self._shell(
                idx, f"grep -c ' {VULKAN_ENC_GUEST_PATH} ' /proc/self/mountinfo"
            )
            if mounts.strip() not in ("", "0"):
                logger.info(f"实例 {idx} 客体 Vulkan 驱动补丁: 本次开机已挂上")
            else:
                logger.info(
                    f"实例 {idx} 客体 Vulkan 驱动补丁: 实例已在运行且没挂，这次不挂"
                    "（要重启 zygote，会结束正在运行的应用），下次开机挂上"
                )
            return False

        if not await self._push(idx, self._guest_script("vulkanfix.sh"), remote):
            logger.warning(f"实例 {idx} 客体 Vulkan 驱动补丁没挂: 推送客体脚本失败")
            return False

        async def run_fix() -> str:
            _, output = await self._shell(
                idx,
                f"su 0 sh {remote} {VULKAN_ENC_ORIG_SHA256} {VULKAN_ENC_FIX_SHA256}",
                timeout=60,
            )
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            return lines[-1] if lines else ""

        _, ui_before = await self._shell(idx, "pidof com.android.systemui")
        status = await run_fix()
        logger.info(
            f"实例 {idx} 客体 Vulkan 驱动补丁 第 1 步（客体检查）: {status or '无输出'}"
        )
        if status.startswith("NEED_UPLOAD"):
            library = await self._patched_vulkan_library(idx)
            if library is None:
                return False
            code, output = await host.run_adb(
                self.root,
                "push",
                str(library),
                VULKAN_FIX_UPLOAD_PATH,
                serial=host.serial_of(console_port(idx)),
                timeout=60,
            )
            if code != 0:
                logger.warning(
                    f"实例 {idx} 客体 Vulkan 驱动补丁没挂: 推送补丁库失败: {output[-200:]}"
                )
                return False
            logger.info(
                f"实例 {idx} 客体 Vulkan 驱动补丁 第 2 步: 已推送 {library}"
                f"（sha256 {VULKAN_ENC_FIX_SHA256}）到 {VULKAN_FIX_UPLOAD_PATH}"
            )
            status = await run_fix()
            logger.info(
                f"实例 {idx} 客体 Vulkan 驱动补丁 第 3 步（挂载）: {status or '无输出'}"
            )

        if status.startswith("ALREADY"):
            mounted = status.partition(" ")[2]
            if mounted == VULKAN_ENC_FIX_SHA256:
                logger.info(
                    f"实例 {idx} 客体 Vulkan 驱动补丁本次开机已挂上（sha256 {mounted}）"
                )
            else:
                logger.warning(
                    f"实例 {idx} 客体驱动库上已经挂着别的文件（sha256 {mounted}），"
                    "不是这次的补丁，没有动它"
                )
            return False
        if status.startswith("VENDOR_PATCHED"):
            logger.info(f"实例 {idx} 镜像自带的客体驱动库已是补丁版，不用挂")
            return False
        if not status.startswith("MOUNTED"):
            # SKIPPED image：镜像不是预期版本；SKIPPED patched：客体缓存坏了，已删，下次重传；FAILED：挂载没成
            logger.warning(
                f"实例 {idx} 客体 Vulkan 驱动补丁没挂: {status or '客体脚本无输出'}"
            )
            return False

        started = time.monotonic()
        back = await self._wait_framework_back(idx, ui_before.strip())
        logger.info(
            f"实例 {idx} 客体 Vulkan 驱动补丁已挂上（sha256 {status.partition(' ')[2]}），"
            f"zygote 重启后系统界面{'已回来' if back else '超时未回来'}"
            f"（{time.monotonic() - started:.0f} 秒）"
        )
        return True

    async def _patched_vulkan_library(self, idx: str) -> Path | None:
        """本机缓存的补丁库 ``<根>\\guest-patches\\libvulkan_enc.khrfix-bindlock2.so``，没有就生成一份。

        生成：从客体拉原库 → 核对哈希、打补丁、核对改完的哈希（:func:`.vulkanfix.patch_vulkan_encoder`）
        → 写进缓存。任一步不成返回 ``None``（记日志，不挂）。同一条安装同时只生成一次。
        本机读写出错（盘满、文件被杀毒软件占着）也只记警告、返回 ``None``，不挡开机。
        """
        library = self.root / GUEST_PATCH_DIR / "libvulkan_enc.khrfix-bindlock2.so"
        try:
            return await self._make_patched_vulkan_library(idx, library)
        except OSError as e:
            logger.warning(
                f"实例 {idx} 客体 Vulkan 驱动补丁没挂: 本机读写补丁库失败（{library}）: "
                f"{type(e).__name__}: {e}"
            )
            with suppress(OSError):
                library.with_suffix(".tmp").unlink(missing_ok=True)
            return None

    async def _make_patched_vulkan_library(
        self, idx: str, library: Path
    ) -> Path | None:
        directory = library.parent
        async with _VULKAN_PATCH_LOCKS.setdefault(root_key(self.root), asyncio.Lock()):
            if library.is_file():
                digest = await asyncio.to_thread(lambda: sha256(library.read_bytes()))
                if digest == VULKAN_ENC_FIX_SHA256:
                    logger.info(
                        f"实例 {idx} 客体 Vulkan 驱动补丁: 用本机缓存 {library}"
                    )
                    return library
                logger.warning(
                    f"本机缓存的客体驱动补丁库哈希不对（{digest}），重新生成: {library}"
                )
            directory.mkdir(parents=True, exist_ok=True)
            original = directory / f"libvulkan_enc-{idx}.orig.so"
            try:
                code, output = await host.run_adb(
                    self.root,
                    "pull",
                    VULKAN_ENC_GUEST_PATH,
                    str(original),
                    serial=host.serial_of(console_port(idx)),
                    timeout=60,
                )
                if code != 0 or not original.is_file():
                    logger.warning(
                        f"实例 {idx} 客体 Vulkan 驱动补丁没挂: 从客体拉 {VULKAN_ENC_GUEST_PATH} 失败: "
                        f"{output[-200:]}"
                    )
                    return None
                data = await asyncio.to_thread(original.read_bytes)
                logger.info(
                    f"实例 {idx} 从客体拉到驱动原库（sha256 {sha256(data)}），本机生成补丁库"
                )
                try:
                    patched = await asyncio.to_thread(patch_vulkan_encoder, data)
                except VulkanFixError as e:
                    logger.warning(f"实例 {idx} 客体 Vulkan 驱动补丁没挂: {e}")
                    return None
                temp = library.with_suffix(".tmp")
                await asyncio.to_thread(temp.write_bytes, patched)
                temp.replace(library)
            finally:
                original.unlink(missing_ok=True)
        logger.info(
            f"实例 {idx} 已在本机生成客体驱动补丁库（sha256 {VULKAN_ENC_FIX_SHA256}）: {library}"
        )
        return library

    async def _wait_framework_back(
        self, idx: str, ui_before: str, timeout: float = 120.0
    ) -> bool:
        """zygote 重启后等系统界面（SystemUI）换成新进程，再多等 8 秒（照启动器）。"""
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

    async def _setup_orientation(self, idx: str) -> None:
        """显示器固定在 0°（横屏），不跟传感器、也不跟应用的方向请求转，横屏游戏也不会翻成 180°。

        应用要求竖屏时系统会把显示器转到 90° / 270°，模拟器窗口不跟着转，画面就是侧着画的。
        固定方向之后，竖屏页面改放进横屏中间、两边留黑（信箱模式）。

        先关信箱模式的引导弹窗（「See and do more」）：它不持久，每次开机都关；游戏里冒出竖屏页面被放进
        信箱时就不弹，不挡脚本。再固定方向：``wm fixed-to-user-rotation`` 存在 ``display_settings.xml``，
        重启后还在。最后读回当前方向记日志。
        """
        failures: list[str] = []
        code, output = await self._shell(
            idx, "wm set-letterbox-style --isEducationEnabled false"
        )
        if code != 0:
            failures.append(f"关信箱引导: {output[-200:]}")

        code, output = await self._shell(
            idx,
            "settings put system user_rotation 0 ; wm fixed-to-user-rotation enabled",
        )
        if code != 0:
            failures.append(f"固定方向: {output[-200:]}")

        _, rotation = await self._shell(
            idx,
            "dumpsys window displays | grep -m1 -oE mDisplayRotation=ROTATION_[0-9]+",
        )
        # grep -m1 提前退出时 dumpsys 会往输出里补一行「Broken pipe」，只取那一行
        current = next(
            (
                line.strip().partition("=")[2]
                for line in rotation.splitlines()
                if line.strip().startswith("mDisplayRotation=")
            ),
            "读不到",
        )
        if failures:
            logger.warning(f"实例 {idx} 方向没设好: {failures}")
        else:
            logger.info(f"实例 {idx} 方向: 固定 0°，当前 {current}")

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

    async def _setup_network(self, idx: str) -> None:
        await self._shell(idx, "su 0 svc wifi enable")
        remote = f"{GUEST_TMP_DIR}/mas-wifi-fastpath.sh"
        if not await self._push(
            idx, self._guest_script("mas-wifi-fastpath.sh"), remote
        ):
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

    async def _setup_idlepoll(self, idx: str) -> None:
        remote = f"{GUEST_TMP_DIR}/mas-idlepoll.sh"
        if not await self._push(idx, self._guest_script("mas-idlepoll.sh"), remote):
            return
        _, started = await self._shell(idx, f"su 0 sh {remote} daemon")
        _, status = await self._shell(idx, f"su 0 sh {remote} status")
        lines = {
            key: value.strip()
            for key, _, value in (line.partition(":") for line in status.splitlines())
        }
        if lines.get("watchers"):
            logger.info(
                f"实例 {idx} 密集读写加速: 守护已起（pid {lines['watchers']}，"
                f"数据盘 {lines.get('disk') or '?'}）"
            )
        else:
            logger.warning(
                f"实例 {idx} 密集读写加速没起来: {(started.strip() + ' / ' + status)[-300:]}"
            )

    async def _start_logcat(self, idx: str, instance: AvdInstance) -> None:
        await self._shell(
            idx,
            f"su 0 setprop persist.logd.size {LOGCAT_BUFFER_SIZE}; "
            f"logcat -G {LOGCAT_BUFFER_SIZE}",
        )
        await ensure_logcat(self.root, idx)

    async def _first_boot_init(self, idx: str) -> None:
        """首次开机后的持久设置（重启后保持），做完记进 ``mas-avd.json``。"""
        logger.info(f"魔改 AVD 实例 {idx} 首次开机，正在初始化")
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
                f"魔改 AVD 实例 {idx} 正在用软件渲染（{renderer}）：没有可用的显卡驱动，"
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
                f"魔改 AVD 实例 {idx} 初始化有失败项，下次开机重试: {failures}"
            )
        else:
            logger.info(f"魔改 AVD 实例 {idx} 初始化完成（桌面: {launcher}）")

    async def _install_launcher(self, idx: str) -> str:
        """装轻量桌面、预置、设为默认，再按用户卸载原生桌面。内测包里没带轻量桌面就保留原生桌面。"""
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
        await self._preset_light_launcher(idx)
        # 原生桌面按用户卸载（系统分区的安装包还在，``cmd package install-existing`` 可恢复），不用
        # ``pm disable-user``：禁用会发 PACKAGE_CHANGED，SystemUI 的 OverviewProxyService 收到后去找原生桌面的
        # 最近任务服务，找不到就空指针崩溃。崩溃打断切换桌面的过渡，轻量桌面的任务图层被留在屏幕外，
        # 第一次开机只看得到壁纸。按用户卸载发的是 PACKAGE_REMOVED，它不收（10-08 实测）。
        commands = [
            f"cmd package set-home-activity {LIGHT_LAUNCHER.home_activity}",
            f"pm uninstall --user 0 {PIXEL_LAUNCHER_PACKAGE}",
            "input keyevent KEYCODE_HOME",
        ]
        code, output = await self._shell(idx, " ; ".join(commands))
        if code != 0:
            logger.warning(f"实例 {idx} 设置轻量桌面失败: {output}")
            return "pixel"
        return LIGHT_LAUNCHER.package

    async def _preset_light_launcher(self, idx: str) -> None:
        """在第一次打开 µLauncher 之前，把它首次打开时的引导页和通知权限弹窗都预置掉。

        1) 通知权限设成拒绝并锁定（它在引导最后一页申请）。
        2) 用 root 给它发一个空广播，只为在后台拉起进程：进程启动时发现还没走过引导，会自己写出默认偏好
           （桌面时钟、上滑打开应用列表等）。``am broadcast`` 等接收器跑完才返回，这时它 ``apply`` 的偏好
           已经落盘。不能直接替它写一份只有预置项的偏好：它看到「引导已走完」就不再写默认偏好，
           桌面没有时钟、上滑也打不开应用列表。
        3) 杀掉进程，往偏好里加上「引导已走完」「打开应用列表不弹键盘」「双击桌面不做任何事」，属主、权限、
           SELinux 标签恢复成应用自己的。

        失败只记告警：最坏是第一次打开时还会走一遍引导。
        """
        package = LIGHT_LAUNCHER.package
        notification = "android.permission.POST_NOTIFICATIONS"
        code, output = await self._shell(
            idx,
            f"pm revoke {package} {notification} ; "
            f"pm set-permission-flags {package} {notification} user-set user-fixed",
        )
        if code != 0:
            logger.warning(f"实例 {idx} 轻量桌面通知权限没预设上: {output[-200:]}")

        prefs = LIGHT_LAUNCHER_PREFS_FILE
        # 0x20 = FLAG_INCLUDE_STOPPED_PACKAGES：刚装好的应用处于停止状态，不带它广播送不到
        code, output = await self._su(
            idx,
            f"am broadcast -f 0x20 -n {LIGHT_LAUNCHER_WAKE_RECEIVER} >/dev/null ; "
            f"am force-stop {package} ; cat {prefs}",
        )
        version = f'name="internal.version_code" value="{LIGHT_LAUNCHER_PREFS_VERSION}"'
        if version not in output:
            logger.warning(
                f"实例 {idx} 轻量桌面没写出默认偏好（或偏好版本不是 "
                f"{LIGHT_LAUNCHER_PREFS_VERSION}），跳过预置: {output[-200:]}"
            )
            return

        # 客体脚本整段包在单引号里、sed 参数包在双引号里：双引号要转义，``&`` 在 sed 替换串里是「匹配到的
        # 内容」也要转义
        deletes = " ".join(
            f'-e "/name=\\"{key}\\"/d"' for key, _ in LIGHT_LAUNCHER_PRESET_PREFS
        )
        inserts = (
            "".join(
                _shared_prefs_entry(key, value)
                for key, value in LIGHT_LAUNCHER_PRESET_PREFS
            )
            .replace('"', '\\"')
            .replace("&", "\\&")
        )
        prefs_dir = prefs.rpartition("/")[0]
        code, output = await self._su(
            idx,
            f'sed -i {deletes} -e "s#</map>#{inserts}</map>#" {prefs} && '
            f"chown $(stat -c %u:%g {prefs_dir}) {prefs} && chmod 660 {prefs} && "
            f"restorecon {prefs} && cat {prefs}",
        )
        missing = [
            key
            for key, value in LIGHT_LAUNCHER_PRESET_PREFS
            if _shared_prefs_entry(key, value) not in output
        ]
        if code != 0 or missing:
            logger.warning(
                f"实例 {idx} 轻量桌面偏好没预置上（{missing or code}）: {output[-200:]}"
            )
        else:
            logger.info(
                f"实例 {idx} 轻量桌面已预置: 跳过引导、应用列表不弹键盘、双击桌面不锁屏、"
                "不申请通知权限"
            )

    # ---- 关机 -----------------------------------------------------------

    async def close(self, idx: str) -> DeviceStatus:
        """关机。同一台实例的 close 排队做（见 :data:`_CLOSING`）。"""
        idx = str(idx)
        instance = self._instance(idx)
        key = _instance_key(self.root, idx)
        lock = _CLOSING.setdefault(key, asyncio.Lock())
        if lock.locked():
            logger.info(f"魔改 AVD 实例 {idx} 正由另一次关闭在关，等它关完再继续")
        async with lock:
            return await self._close(idx, instance, key)

    async def _close(self, idx: str, instance: AvdInstance, key: str) -> DeviceStatus:
        port = console_port(idx)
        _stop_watchdog(self.root, idx)
        _FROZEN.pop(key, None)
        process = await asyncio.to_thread(host.find_qemu_process, instance.name, port)
        if process is None:
            return DeviceStatus.OFFLINE

        # 默认让安卓自己正常关机（``sys.powerctl shutdown``），等 qemu 自己退出；不成再退回
        # 「sync + 控制台 kill + 强杀」。控制台 kill / 强杀都直接结束 qemu，客体不走关机流程：
        # 页缓存里没写回的数据会丢（星铁热更新清单因此变成过 0 字节，表现成「网络请求超时」和黑屏），
        # 而且 sync 之后到 qemu 真正退出之间还有 2–3 秒，这段时间里游戏写的东西 sync 也管不到。
        # 正常关机时客体 init 依次结束各个服务和应用、把页缓存写回、卸载分区，最后断电让 qemu 自己
        # 退出，和手机关机、MuMu / 雷电关机一样。
        # 磁盘 write-through 只保证已经写到虚拟盘的数据，管不到还在客体内存里的。
        # 强制关闭（ForceKillOnClose）不走正常关机，只先 sync 再强杀。
        # 时限：调用方（任务收尾 close_emulator）整体只给 30 秒，超了连强杀都执行不到。各步上限与
        # 三条路径的算式见 constants 里关机那一组（最坏 28 秒）。adb 命令都不走重新登记（会多等 5 秒），
        # 私有 server 中途没了要重起时，等它的时间也从这条命令的上限里扣（total_timeout）。
        started = time.monotonic()
        # 私有 server 要是没在跑，起它、替实例登记也算进预算：最多等几秒，不成就既不能正常关机、
        # 也不能 sync，直接用控制台关
        problem = await host.prepare_adb_for_close(
            self.root, port, timeout=ADB_SERVER_START_TIMEOUT_ON_CLOSE_SECONDS
        )

        if self.config.Info.ForceKillOnClose:
            await self._sync_before_kill(idx, port, problem, SYNC_TIMEOUT_SECONDS)
            await self._force_kill(process, FORCE_KILL_WAIT_SECONDS)
            logger.info(f"魔改 AVD 实例 {idx} 已强制关闭")
            return DeviceStatus.OFFLINE

        if problem is None:
            reason = await self._graceful_shutdown(port, process)
            if reason is None:
                logger.info(
                    f"魔改 AVD 实例 {idx} 正常关机完成"
                    f"（{time.monotonic() - started:.1f} s）"
                )
                return DeviceStatus.OFFLINE
            logger.warning(
                f"魔改 AVD 实例 {idx} 正常关机没成（{reason}），退回 sync + 控制台 kill"
            )
            await self._sync_before_kill(idx, port, None, FALLBACK_SYNC_TIMEOUT_SECONDS)
            kill_timeout = FALLBACK_KILL_TIMEOUT_SECONDS
            force_kill_wait = FALLBACK_FORCE_KILL_WAIT_SECONDS
        else:
            logger.warning(
                f"魔改 AVD 实例 {idx} 私有 adb 用不了，不能正常关机也不能 sync，"
                f"直接用控制台关: {problem}"
            )
            kill_timeout = CONSOLE_KILL_TIMEOUT_SECONDS + CLOSE_TIMEOUT_SECONDS
            force_kill_wait = FORCE_KILL_WAIT_SECONDS

        await self._console_kill(idx, port, process, kill_timeout)
        if process.is_running():
            logger.warning(
                f"魔改 AVD 实例 {idx} 未在 {kill_timeout:.0f} 秒内退出，强制结束"
            )
            await self._force_kill(process, force_kill_wait)
        logger.info(f"魔改 AVD 实例 {idx} 已关闭")
        return DeviceStatus.OFFLINE

    async def _graceful_shutdown(
        self, port: int, process: psutil.Process
    ) -> str | None:
        """让安卓正常关机，等 qemu 自己退出，发命令连同等待最多
        :data:`~.constants.GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS` 秒。退出了返回 ``None``，否则返回原因。

        ``sys.powerctl`` 只有 root 能写，这些 userdebug 镜像上用 ``su 0``（同 :meth:`_su`）。
        """
        started = time.monotonic()
        code, output = await host.run_adb(
            self.root,
            "shell",
            "su 0 setprop sys.powerctl shutdown",
            serial=host.serial_of(port),
            timeout=GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS,
            reregister=False,
            total_timeout=True,
        )
        if code != 0:
            return f"关机命令没有成功返回（返回码 {code}）: {output}"
        remaining = GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS - (time.monotonic() - started)
        if remaining > 0:
            with suppress(psutil.TimeoutExpired):
                await asyncio.to_thread(process.wait, remaining)
        if process.is_running():
            return f"{GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS:.0f} 秒内没有自己退出"
        return None

    async def _sync_before_kill(
        self, idx: str, port: int, problem: str | None, timeout: float
    ) -> None:
        """控制台 kill / 强杀前先 ``sync``，把客体页缓存写回虚拟盘。失败只记警告。"""
        started = time.monotonic()
        if problem is None:
            code, output = await host.run_adb(
                self.root,
                "shell",
                "sync",
                serial=host.serial_of(port),
                timeout=timeout,
                reregister=False,
                total_timeout=True,
            )
        else:
            code, output = -1, problem
        if code == 0:
            logger.info(
                f"魔改 AVD 实例 {idx} 关机前 sync 完成（{(time.monotonic() - started) * 1000:.0f} ms）"
            )
        else:
            logger.warning(f"魔改 AVD 实例 {idx} 关机前 sync 失败，照常关机: {output}")

    async def _console_kill(
        self, idx: str, port: int, process: psutil.Process, timeout: float
    ) -> None:
        """发控制台 ``kill`` 并等 qemu 退出，两步合计最多 ``timeout`` 秒（发命令本身最多
        :data:`~.constants.CONSOLE_KILL_TIMEOUT_SECONDS` 秒）。没退出由调用方强杀。"""
        started = time.monotonic()
        try:
            await host.console_command(
                port, "kill", timeout=min(CONSOLE_KILL_TIMEOUT_SECONDS, timeout)
            )
        except host.ConsoleError as e:
            logger.warning(f"实例 {idx} 控制台 kill 失败，改为强制结束: {e}")
            return
        remaining = timeout - (time.monotonic() - started)
        if remaining > 0:
            with suppress(psutil.TimeoutExpired):
                await asyncio.to_thread(process.wait, remaining)

    @staticmethod
    async def _force_kill(process: psutil.Process, wait: float) -> None:
        if not process.is_running():
            return
        host.kill_process_tree(process)
        with suppress(psutil.TimeoutExpired):
            await asyncio.to_thread(process.wait, wait)

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
        # 显示固定 720p（开机前核对一次写进 config.ini）
        meta = instance_meta(self.root, idx)
        display = display_changes(instance.config)
        # 报开机实际传的 -memory（实例元数据里的值；以前「按游戏自动」的旧实例按默认 6 GB）
        memory = FieldValue(memory_for(meta), "saved")
        return InstanceSettings(
            fields={
                "width": FieldValue(_int(display["hw.lcd.width"]), "saved"),
                "height": FieldValue(_int(display["hw.lcd.height"]), "saved"),
                "dpi": FieldValue(_int(display["hw.lcd.density"]), "saved"),
                "cpu": FieldValue(instance.cpu, "saved"),
                "memoryMb": memory,
                # 刷新率 hw.lcd.vsync（30 / 60，下次开机生效）
                "fps": FieldValue(instance.fps, "saved"),
            }
        )

    async def read_instance_overview(
        self, idx: str
    ) -> tuple[InstanceSettings, bool, list[str]]:
        return await self.read_instance_settings(idx), True, []

    async def write_instance_settings(
        self, idx: str, changes: dict, expected: dict | None = None
    ) -> dict[str, int]:
        """可改 CPU、内存与帧率（30 / 60，写 ``hw.lcd.vsync``），都是下次启动生效；显示固定 720p。"""
        cleaned = validate_setting_changes(changes)
        instance = self._instance(idx)
        # 只在这次要改帧率时校验：只改 CPU / 内存不该被手改过的 hw.lcd.vsync 挡住
        fps = validate_fps(cleaned["fps"]) if "fps" in cleaned else None
        if {"width", "height", "dpi"} & cleaned.keys():
            _check_display(
                cleaned.get("width", SCREEN_WIDTH),
                cleaned.get("height", SCREEN_HEIGHT),
                cleaned.get("dpi", SCREEN_DENSITY),
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
        config_changes = {"hw.ramSize": f"{memory}M", "hw.cpu.ncore": str(cpu)}
        if fps is not None:
            config_changes["hw.lcd.vsync"] = str(fps)
        write_instance_config(self.root, idx, config_changes)
        # 内存每次都记进元数据：开机按它传 -memory，以前「按游戏自动」的旧实例从此有了固定值
        update_instance_meta(self.root, idx, memoryMb=memory)
        applied = {
            k: v
            for k, v in cleaned.items()
            if k in ("cpu", "memoryMb", "fps", "width", "height", "dpi")
        }
        logger.info(f"已写入魔改 AVD 实例 {idx} 的设置: {applied}")
        return applied

    async def read_stable_mode(self, idx: str) -> tuple[bool, list[str]]:
        # 魔改 AVD 没有会干扰截图识别的厂商功能，天然就是「稳定」的
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
        native_index: int | None = None,
        fps: int | None = None,
    ) -> str:
        """新建实例，返回原生索引。不给索引就取最小的、端口也空着的那个。

        内存、核数、帧率不给就用默认 6 GB / 6 核 / 60（:data:`~.constants.DEFAULT_MEMORY_MB` /
        ``DEFAULT_CPU`` / ``DEFAULT_FPS``）。
        """
        memory, cores, data_gb = validate_options(memory_mb, cpu, data_partition_gb)
        refresh = validate_fps(fps)
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
            fps=refresh,
        )
        logger.info(
            f"已新建魔改 AVD 实例 {native_index}（内存 "
            f"{memory} MB / {cores} 核 / 数据盘 {data_gb} GB / 帧率 {refresh}）"
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
        raise RuntimeError("魔改 AVD 实例已满（端口段 20000–20100 最多 9 台）")

    async def delete_instance(self, native_index: str) -> None:
        status = await self.getStatus(native_index)
        if status not in (
            DeviceStatus.OFFLINE,
            DeviceStatus.NOT_FOUND,
            DeviceStatus.ERROR,
        ):
            raise RuntimeError(f"魔改 AVD 实例 {native_index} 未关闭，无法删除")
        if status == DeviceStatus.ERROR:
            # 被看门狗强杀过的实例进程已经不在，只剩状态标记
            _FROZEN.pop(_instance_key(self.root, str(native_index)), None)
        await asyncio.to_thread(delete_instance_files, self.root, native_index)
        logger.info(f"已删除魔改 AVD 实例 {native_index}")

    # ---- 实例选项 ------------------------------------------------------

    def instance_options(self, idx: str) -> dict[str, Any]:
        instance = self._instance(idx)
        meta = instance_meta(self.root, idx)
        return {
            "memoryMb": memory_for(meta),
            "cpu": instance.cpu,
            "fps": instance.fps,
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


def _int(raw: object) -> int | None:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _check_display(width: int | None, height: int | None, dpi: int | None) -> None:
    """魔改 AVD 的显示固定 720p（横竖屏都认）；改成别的就拒绝，不做静默吸附。"""
    if sorted((width or 0, height or 0), reverse=True) != [
        SCREEN_WIDTH,
        SCREEN_HEIGHT,
    ] or (dpi != SCREEN_DENSITY):
        raise ValueError(
            f"魔改 AVD 的显示固定 720p（{SCREEN_WIDTH}×{SCREEN_HEIGHT}、DPI {SCREEN_DENSITY}），不能修改"
        )


class AvdHostAdb:
    """MAS 宿主进程对一台魔改 AVD 实例发 adb 命令的通道：私有 server ``-P <adbServerPort>
    -s emulator-<控制台端口>``。脚本的 adb server 杀不到它，丢设备时 :func:`host.run_adb` 会重新登记。

    调用约定同 :data:`~..applaunch.AdbRunner`：``await runner(*args, timeout=…)`` → ``(返回码, 输出)``。
    给游戏更新检查（:func:`app.utils.common.game_apk.adb_runner_scope`）与失败截图（:meth:`screencap_png`）用。
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
                f"魔改 AVD 实例 {self.native_index} 截图失败（返回码 {code}）: {error[-200:]}"
            )
        return data


class AvdManager(AppLaunchMixin, _AvdCore):
    """一条魔改 AVD 安装的管理器。

    ``AppLaunchMixin.open`` 先开机再拉应用；这里把拉应用改走私有 adb、先结束其它第三方游戏。
    """

    store_package = None

    def __init__(
        self,
        manager_exe: str | Path,
        max_wait_time: int,
        force_kill_on_close: bool,
        *,
        runtime_policy: EmulatorRuntimePolicy,
    ) -> None:
        super().__init__(
            manager_exe=manager_exe,
            max_wait_time=max_wait_time,
            force_kill_on_close=force_kill_on_close,
            resource_path=runtime_policy.resource_path,
        )
        self.runtime_policy = runtime_policy

    def host_adb(self, idx: str) -> AvdHostAdb:
        """宿主进程对这台实例发 adb 命令的通道（走私有 server，见 :class:`AvdHostAdb`）。"""
        self._instance(idx)
        return AvdHostAdb(self.root, str(idx))

    async def open(
        self, idx: str, package_name: str = "", *, manual: bool = False
    ) -> DeviceInfo:
        """开机（已在线就直接用，不重开）。有没有窗口只在开机那一刻定，开着以后切换不了：

        - ``manual=True``：用户在模拟器页手动点启动（:meth:`~app.core.emulator_manager.manager._EmulatorManager.operate_emulator_task`），带窗口；
        - 任务拉起（``manual`` 不传）：跟「静默模式」走，``Function.IfSilence`` 开着无头，关着带窗口。
        """
        self._open_window = manual or not _silence_enabled(self.runtime_policy)
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
        serial = host.serial_of(console_port(idx))
        root = self.root

        async def run_adb(*args: str, timeout: float = 20.0) -> tuple[int, str]:
            return await host.run_adb(root, *args, serial=serial, timeout=timeout)

        await self.stop_background_games(idx, keep=package_name)
        max_wait = float(self.config.Info.MaxWaitTime)
        return await ensure_app_running(
            run_adb,
            package_name,
            boot_timeout=min(max_wait, _BOOT_TIMEOUT_CAP),
            launch_timeout=launch_timeout or min(max_wait, _LAUNCH_TIMEOUT_CAP),
            label=str(idx),
        )

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


def opening_instances(root: Path) -> list[str]:
    """这个根目录下正在开机（``open`` 还没做完，含开机前检查到拉起 emulator.exe 之间那几秒）的实例。"""
    prefix = f"{root_key(root)}|"
    return sorted(
        key[len(prefix) :] for key in list(_OPENING) if key.startswith(prefix)
    )


def running_instances(root: Path) -> list[str]:
    """这个根目录下开着的实例（原生索引）。

    实例按 AVD 名 + 控制台端口认，各根目录的名字和端口是同一套；只算 qemu 可执行文件就在
    这个根目录 ``sdk\\emulator`` 下的，免得把另一个根目录的同名实例算进来。
    """
    ours = {item["pid"] for item in update_stage.processes_using(root)}
    running = _AvdCore(
        manager_key_exe(root), max_wait_time=60, force_kill_on_close=False
    )._scan_processes()
    return sorted(idx for idx, process in running.items() if process.pid in ours)


async def build_manager(
    manager_exe: str,
    max_wait_time: int,
    force_kill_on_close: bool = False,
    *,
    runtime_policy: EmulatorRuntimePolicy,
) -> AvdManager:
    """与雷电 / MuMu 的 ``build_manager`` 同签名。``manager_exe`` 是 ``sdk\\emulator\\emulator.exe``。"""
    exe = emulator_exe(root_from_manager_exe(manager_exe))
    if not exe.is_file():
        raise RuntimeError(f"找不到魔改 AVD 程序 {exe}")
    return AvdManager(
        manager_exe=manager_exe,
        max_wait_time=max_wait_time,
        force_kill_on_close=force_kill_on_close,
        runtime_policy=runtime_policy,
    )


__all__ = [
    "AvdManager",
    "FreezeWatchdog",
    "build_manager",
    "opening_instances",
    "running_instances",
    "emulator_exe",
    "shm_exists",
]
