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
实例内存、空闲页上报、宿主调度、截图共享内存、cpuinfo、WiFi + fastpath、客体日志落盘。
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
)
from ..settings import FieldValue, InstanceSettings, SettingsConflictError
from ..settings import validate_changes as validate_setting_changes
from . import host, precheck
from .components import (
    component_installed,
    emulator_exe,
    launcher_apk,
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
    FORCE_KILL_WAIT_SECONDS,
    GUEST_DIRTY_EXPIRE_CENTISECS,
    GUEST_DIRTY_WRITEBACK_CENTISECS,
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
    validate_memory,
    validate_options,
    write_instance_config,
)

logger = get_logger("魔改 AVD 管理")

#: 仓库里推到客体跑的脚本。
GUEST_SCRIPTS_DIR = SOURCE_ROOT / "res" / "avd" / "guest"

#: 等 ``sys.boot_completed`` 的轮询间隔。
_BOOT_POLL_SECONDS = 1.0
#: 状态查询里单条 adb 的超时：状态轮询不能被一台卡住的实例拖住整张表。
_STATUS_ADB_TIMEOUT = 5.0
#: 装轻量桌面的超时。
_INSTALL_TIMEOUT = 180.0
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
    """截图共享内存 ``SHM_videmulator<控制台端口>`` 在不在（MaaFW AVDExtras 读它）。"""
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


def _silence_enabled() -> bool:
    """全局「静默模式」开没开；读不到（配置没加载）按开，宁可无头。"""
    try:
        from app.core import Config

        return bool(Config.get("Function", "IfSilence"))
    except Exception:  # noqa: BLE001
        return True


#: 模拟器主窗口的标题前缀（后面接 ``<avd>:<控制台端口>``）与侧边工具栏的标题。
_EMULATOR_WINDOW_PREFIX = "Android Emulator - "
_EMULATOR_TOOLBAR_TITLE = "Emulator"


def _set_emulator_windows_visible(pid: int, name_port: str, visible: bool) -> int:
    """对 qemu 进程 ``pid`` 的主窗口与侧边工具栏发 ``SW_SHOW`` / ``SW_HIDE``，返回处理的窗口数。

    只认 Qt 窗口（类名以 ``Qt`` 开头）里标题是 ``Android Emulator - <avd>:<端口>`` 的主窗口和标题为
    ``Emulator`` 的工具栏；同一进程里一大堆 OpenGL / 输入法隐藏窗口不碰。无头开机的进程没有这两个
    窗口，返回 0。用 ``ShowWindowAsync`` 只投递消息，不等模拟器界面线程。
    """
    import win32con
    import win32gui
    import win32process

    targets: list[int] = []

    def collect(hwnd: int, _: object) -> bool:
        try:
            _, owner = win32process.GetWindowThreadProcessId(hwnd)
            if owner != pid or not win32gui.GetClassName(hwnd).startswith("Qt"):
                return True
            title = win32gui.GetWindowText(hwnd)
        except Exception:  # noqa: BLE001 - 枚举途中窗口被销毁
            return True
        if (
            title == f"{_EMULATOR_WINDOW_PREFIX}{name_port}"
            or title == _EMULATOR_TOOLBAR_TITLE
        ):
            targets.append(hwnd)
        return True

    win32gui.EnumWindows(collect, None)
    from ctypes import wintypes

    # 私有一份 user32 声明原型，不影响进程里其它走 ctypes.windll.user32 的代码
    show = ctypes.WinDLL("user32").ShowWindowAsync
    show.argtypes = [wintypes.HWND, ctypes.c_int]
    show.restype = wintypes.BOOL
    for hwnd in targets:
        show(hwnd, win32con.SW_SHOW if visible else win32con.SW_HIDE)
    return len(targets)


# ---- 启动参数 -------------------------------------------------------------


def launch_options(meta: dict[str, Any]) -> dict[str, Any]:
    """实例的 MAS 侧选项（``mas-avd.json``）→ 本次开机用的值，缺省值都在这里。

    有没有窗口不是实例选项（用户 10-04 定），开机那一刻按启动入口定，见 :meth:`AvdManager.open`。
    旧 ``mas-avd.json`` 里留下的 ``headless`` / ``resolution`` / ``guestAngle`` / ``audio`` 一律不读：
    显示固定 720p、不带声卡、不开 GuestAngle。"""
    return {
        "flags": {
            # 空闲页上报默认开（10-04 定）；要自编 qemu（sdk-mas19 起）
            "balloon": bool(meta.get("balloon", True)),
        },
    }


def build_launch_args(
    avd: str,
    console: int,
    *,
    memory_mb: int,
    headless: bool,
    balloon: bool,
) -> list[str]:
    """``emulator.exe`` 的参数，逐项照启动器 ``avd-p0.ps1``（每个开关都真机验证过）。

    - 冷启动（``-no-snapshot``），与 MAS 对雷电 / MuMu 每轮开关一致；
    - ``-audio none``：宿主不出声（用户 09-27 定）；
    - ``-feature -VirtioSndCard``：客体里不带声卡（用户 10-04 定）。本镜像的客体声卡是 virtio-snd，
      不认 ``config.ini`` 的 ``hw.audioOutput`` / ``hw.audioInput``（10-04 实测两项写 no 照样有声卡），
      只能关掉这个特性；关掉后 ``/proc/asound/cards`` 为空。1999 主界面上 qemu CPU 中位数 147% → 104%
      （单核百分比，各测一轮）；
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
    if headless:
        args.append("-no-window")
    if balloon:
        args += ["-feature", "-QuickbootFileBacked"]
    args += ["-feature", "-VirtioSndCard"]
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
                count = await asyncio.to_thread(
                    _set_emulator_windows_visible,
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
                logger.info(f"魔改 AVD 实例 {idx} 已在运行（pid {process.pid}）")
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
                f"魔改 AVD 实例 {idx} 要用的端口 {', '.join(map(str, busy))} 已被占用，"
                "请先关闭占用它们的程序"
            )

        await host.ensure_adb_server(self.root)
        meta = instance_meta(self.root, idx)
        options = launch_options(meta)
        if await asyncio.to_thread(apply_display, self.root, idx):
            logger.info(f"实例 {idx} 显示改回 720p（已写入 config.ini）")
        headless = not self._open_window
        args = build_launch_args(
            instance.name,
            port,
            memory_mb=memory_mb,
            headless=headless,
            **options["flags"],
        )
        await prune_logs(self.root, idx)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self._log_path = self._log_dir() / f"{instance.name}-{stamp}.log"
        logger.info(
            f"启动魔改 AVD 实例 {idx}（{'无头' if headless else '带窗口'}，"
            f"720p，{memory_mb} MB / {instance.cpu} 核，"
            f"气球{'开' if options['flags']['balloon'] else '关'}，不带声卡）: "
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

        # 10) 方向：显示器固定横屏（持久，每次开机设一次给老实例补上）
        await self._setup_orientation(idx)

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
        idx = str(idx)
        instance = self._instance(idx)
        port = console_port(idx)
        _stop_watchdog(self.root, idx)
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
                f"魔改 AVD 实例 {idx} 关机前 sync 完成（{(time.monotonic() - started) * 1000:.0f} ms）"
            )
        else:
            logger.warning(f"魔改 AVD 实例 {idx} 关机前 sync 失败，照常关机: {output}")

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
                f"魔改 AVD 实例 {idx} 未在 {CLOSE_TIMEOUT_SECONDS:.0f} 秒内退出，强制结束"
            )
            host.kill_process_tree(process)
            with suppress(psutil.TimeoutExpired):
                await asyncio.to_thread(process.wait, FORCE_KILL_WAIT_SECONDS)
        logger.info(f"魔改 AVD 实例 {idx} 已关闭")
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
        """可改 CPU 与内存（下次启动生效）；显示固定 720p、帧率不可设。"""
        cleaned = validate_setting_changes(changes)
        if "fps" in cleaned:
            raise ValueError("魔改 AVD 没有可设置的帧率")
        instance = self._instance(idx)
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
        write_instance_config(
            self.root, idx, {"hw.ramSize": f"{memory}M", "hw.cpu.ncore": str(cpu)}
        )
        # 内存每次都记进元数据：开机按它传 -memory，以前「按游戏自动」的旧实例从此有了固定值
        update_instance_meta(self.root, idx, memoryMb=memory)
        applied = {
            k: v
            for k, v in cleaned.items()
            if k in ("cpu", "memoryMb", "width", "height", "dpi")
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
        balloon: bool = True,
    ) -> str:
        """新建实例，返回原生索引。不给索引就取最小的、端口也空着的那个。

        内存、核数不给就用默认 6 GB / 6 核（:data:`~.constants.DEFAULT_MEMORY_MB` / ``DEFAULT_CPU``）。
        """
        memory, cores, data_gb = validate_options(memory_mb, cpu, data_partition_gb)
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
            balloon=balloon,
        )
        logger.info(
            f"已新建魔改 AVD 实例 {native_index}（内存 "
            f"{memory} MB / {cores} 核 / 数据盘 {data_gb} GB）"
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
        options = launch_options(meta)
        return {
            "balloon": options["flags"]["balloon"],
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

    def set_instance_options(
        self,
        idx: str,
        *,
        memory_mb: int | None = None,
        balloon: bool | None = None,
    ) -> dict[str, Any]:
        """改实例的 MAS 侧选项（内存、气球），下次启动生效。``None`` = 不改。"""
        self._instance(idx)
        changes: dict[str, Any] = {}
        if memory_mb is not None:
            changes["memoryMb"] = validate_memory(memory_mb)
        if balloon is not None:
            changes["balloon"] = bool(balloon)
        if changes:
            update_instance_meta(self.root, idx, **changes)
            logger.info(f"已修改魔改 AVD 实例 {idx} 的选项（下次启动生效）: {changes}")
        return self.instance_options(idx)


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
    给游戏更新检查（:func:`app.utils.game_apk.adb_runner_scope`）用。
    """

    def __init__(self, root: Path, native_index: str) -> None:
        self.root = Path(root)
        self.native_index = str(native_index)
        self.serial = host.serial_of(console_port(native_index))

    async def __call__(self, *args: str, timeout: float = 20.0) -> tuple[int, str]:
        return await host.run_adb(self.root, *args, serial=self.serial, timeout=timeout)


class AvdManager(AppLaunchMixin, _AvdCore):
    """一条魔改 AVD 安装的管理器。

    ``AppLaunchMixin.open`` 先开机再拉应用；这里把拉应用改走私有 adb、先结束其它第三方游戏。
    """

    store_package = None

    def host_adb(self, idx: str) -> AvdHostAdb:
        """宿主进程对这台实例发 adb 命令的通道（走私有 server，见 :class:`AvdHostAdb`）。"""
        self._instance(idx)
        return AvdHostAdb(self.root, str(idx))

    async def open(
        self, idx: str, package_name: str = "", *, manual: bool = False
    ) -> DeviceInfo:
        """开机（已在线就直接用，不重开）。有没有窗口只在开机那一刻定，开着以后切换不了：

        - ``manual=True``：用户在模拟器页手动点启动（:meth:`~app.core.emulator_manager._EmulatorManager.operate_emulator_task`），带窗口；
        - 任务拉起（``manual`` 不传）：跟「静默模式」走，``Function.IfSilence`` 开着无头，关着带窗口。
        """
        self._open_window = manual or not _silence_enabled()
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
        max_wait = float(self.config.get("Info", "MaxWaitTime"))
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


async def build_manager(
    manager_exe: str, max_wait_time: int, force_kill_on_close: bool = False
) -> AvdManager:
    """与雷电 / MuMu 的 ``build_manager`` 同签名。``manager_exe`` 是 ``sdk\\emulator\\emulator.exe``。"""
    exe = emulator_exe(root_from_manager_exe(manager_exe))
    if not exe.is_file():
        raise RuntimeError(f"找不到魔改 AVD 程序 {exe}")
    return AvdManager(manager_exe, max_wait_time, force_kill_on_close)


__all__ = [
    "AvdManager",
    "FreezeWatchdog",
    "build_manager",
    "emulator_exe",
    "shm_exists",
]
