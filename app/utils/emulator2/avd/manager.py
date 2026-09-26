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
（= 静默模式，预研 §6.14）。每次开机后做四项调优（重启即失效）：解除 2 GB 测试流量套餐、
``/data`` 去 barrier、开截图共享内存并强制重绘一帧；首次开机后再做一次持久初始化（关 WiFi
与蓝牙、去全屏提示、禁用手机预装应用、换轻量桌面、记录渲染器）。
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

from ..applaunch import AppLaunchMixin, AppLaunchResult, ensure_app_running
from ..settings import FieldValue, InstanceSettings, SettingsConflictError
from ..settings import validate_changes as validate_setting_changes
from . import host
from .components import (
    component_installed,
    emulator_exe,
    launcher_apk,
    root_from_manager_exe,
    root_key,
)
from .constants import (
    CLOSE_TIMEOUT_SECONDS,
    DEBLOAT_PACKAGES,
    FOSSIFY_LAUNCHER,
    INCOMPATIBLE_PACKAGES,
    KEEP_PACKAGES,
    MAX_NATIVE_INDEX,
    PIXEL_LAUNCHER_PACKAGE,
    REQUIRED_COMPONENTS,
    SCREEN_DENSITY,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
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
    create_instance_files,
    delete_instance_files,
    instance_meta,
    list_instances,
    update_instance_meta,
    validate_options,
    write_instance_config,
)

logger = get_logger("官方模拟器管理")

#: 等 ``sys.boot_completed`` 的轮询间隔。
_BOOT_POLL_SECONDS = 1.0
#: 状态查询里单条 adb 的超时：状态轮询不能被一台卡住的实例拖住整张表。
_STATUS_ADB_TIMEOUT = 5.0
#: ``adb root`` 之后等 adbd 以 root 身份重新连上的上限。
_ROOT_RECONNECT_TIMEOUT = 30.0
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
        return code == 0 and output.strip().endswith("ok")

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
        self, idx: str, timeout: float = _STATUS_ADB_TIMEOUT
    ) -> bool:
        code, output = await host.run_adb(
            self.root,
            "shell",
            "getprop",
            "sys.boot_completed",
            serial=host.serial_of(console_port(idx)),
            timeout=timeout,
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
        if process is None:
            await self._launch(idx, instance)
        else:
            logger.info(f"官方模拟器实例 {idx} 已在运行（pid {process.pid}）")

        deadline = time.monotonic() + max_wait
        while True:
            process = await asyncio.to_thread(
                host.find_qemu_process, instance.name, port
            )
            if process is not None and await self._boot_completed(idx):
                break
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

        await self._after_boot(idx, instance)
        _start_watchdog(self.root, idx, process.pid)
        return self._device_info(idx, instance.title, DeviceStatus.ONLINE)

    _launcher = None
    _log_path: Path | None = None

    def _log_dir(self) -> Path:
        return self.root / "logs"

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
        accel = await host.check_acceleration(self.root)
        if not accel.ok:
            raise RuntimeError(f"{host.ACCEL_GUIDE}（检查结果：{accel.detail}）")
        memory_mb = instance.memory_mb or 4096
        host.check_host_memory(memory_mb)

        port = console_port(idx)
        ports = [port, port + 1, port + 2]
        busy = await asyncio.to_thread(host.busy_ports, ports)
        if busy:
            raise RuntimeError(
                f"官方模拟器实例 {idx} 要用的端口 {', '.join(map(str, busy))} 已被占用，"
                "请先关闭占用它们的程序"
            )

        await host.ensure_adb_server(self.root)
        headless = bool(instance_meta(self.root, idx).get("headless", True))
        args = [
            "-avd",
            instance.name,
            "-no-snapshot",
            "-no-boot-anim",
            "-gpu",
            "host",
            "-ports",
            f"{port},{port + 1}",
            "-grpc",
            str(port + 2),
            "-grpc-use-token",
        ]
        if headless:
            args.append("-no-window")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self._log_path = self._log_dir() / f"{instance.name}-{stamp}.log"
        logger.info(
            f"启动官方模拟器实例 {idx}（{'无头' if headless else '带窗口'}，"
            f"{memory_mb} MB / {instance.cpu} 核）: emulator {' '.join(args)}"
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

    async def _after_boot(self, idx: str, instance: AvdInstance) -> None:
        """每次开机后的调优（重启即失效）+ 首次开机的一次性初始化。失败只记警告。"""
        port = console_port(idx)
        serial = host.serial_of(port)

        # 1) 镜像自带 2 GB 测试流量套餐（EmulatorDataPlan），用满就断网；标成不计量即解除
        try:
            await host.console_command(port, "gsm meter off")
        except host.ConsoleError as e:
            logger.warning(f"实例 {idx} 解除流量上限失败: {e}")

        # 2) /data 去 barrier：游戏下载时每秒上千次 fsync，每次都要陷出到 QEMU（+55% 下载速度）
        code, output = await host.run_adb(self.root, "root", serial=serial, timeout=20)
        if code != 0:
            logger.warning(f"实例 {idx} 切换 root adbd 失败: {output}")
        else:
            await self._wait_adb_back(idx)
        code, output = await self._shell(idx, "mount -o remount,nobarrier /data")
        if code != 0:
            logger.warning(f"实例 {idx} 设置 nobarrier 失败: {output}")

        # 3) 截图共享内存：开推流才会建 SHM_videmulator<端口>，静止画面下它一直是黑帧，
        #    所以建好后强制 SurfaceFlinger 重绘一帧（预研 §6.16）
        try:
            await host.console_command(port, "screenrecord webrtc start")
        except host.ConsoleError as e:
            logger.warning(f"实例 {idx} 开启截图共享内存失败: {e}")
        await self._shell(idx, "service call SurfaceFlinger 1004")

        meta = instance_meta(self.root, idx)
        if not meta.get("initialized"):
            await self._first_boot_init(idx)

    async def _wait_adb_back(self, idx: str) -> None:
        deadline = time.monotonic() + _ROOT_RECONNECT_TIMEOUT
        await asyncio.sleep(1.0)
        while time.monotonic() < deadline:
            code, output = await self._shell(idx, "id -u", timeout=5)
            if code == 0 and output.strip() == "0":
                return
            await asyncio.sleep(1.0)
        logger.warning(f"实例 {idx} 等 root adbd 重连超时")

    async def _first_boot_init(self, idx: str) -> None:
        """首次开机后的持久设置（重启后保持），做完记进 ``mas-avd.json``。"""
        logger.info(f"官方模拟器实例 {idx} 首次开机，正在初始化")
        failures: list[str] = []

        # 虚拟 WiFi 是网络瓶颈（模拟 802.11b，6.4 MB/s），关掉走移动数据快 4.6 倍（预研 §6.10）
        base = [
            "svc wifi disable",
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
        _FROZEN.pop(_instance_key(self.root, idx), None)
        process = await asyncio.to_thread(host.find_qemu_process, instance.name, port)
        if process is None:
            return DeviceStatus.OFFLINE

        if not self.config.get("Info", "ForceKillOnClose"):
            try:
                await host.console_command(port, "kill")
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
                await asyncio.to_thread(process.wait, 10)
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
        config = instance.config
        return InstanceSettings(
            fields={
                "width": FieldValue(_int(config.get("hw.lcd.width")), "saved"),
                "height": FieldValue(_int(config.get("hw.lcd.height")), "saved"),
                "dpi": FieldValue(_int(config.get("hw.lcd.density")), "saved"),
                "cpu": FieldValue(instance.cpu, "saved"),
                "memoryMb": FieldValue(instance.memory_mb, "saved"),
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
        """只能改 CPU 与内存（下次启动生效）；分辨率固定 1920×1080 / DPI 280，帧率不可设。"""
        cleaned = validate_setting_changes(changes)
        fixed = {"width": SCREEN_WIDTH, "height": SCREEN_HEIGHT, "dpi": SCREEN_DENSITY}
        for name, value in cleaned.items():
            if name in fixed and value != fixed[name]:
                raise ValueError(
                    "官方模拟器的分辨率固定为 1920×1080、DPI 280，不能修改"
                )
            if name == "fps":
                raise ValueError("官方模拟器没有可设置的帧率")
        instance = self._instance(idx)
        memory, cpu, _ = validate_options(
            cleaned.get("memoryMb", instance.memory_mb),
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
        applied = {k: v for k, v in cleaned.items() if k in ("cpu", "memoryMb")}
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
    ) -> str:
        """新建实例，返回原生索引。不给索引就取最小的、端口也空着的那个。"""
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
            headless=headless,
        )
        logger.info(
            f"已新建官方模拟器实例 {native_index}（{memory} MB / {cores} 核 / 数据盘 {data_gb} GB）"
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
        logger.info(f"已删除官方模拟器实例 {native_index}")

    # ---- 实例选项 ------------------------------------------------------

    def instance_options(self, idx: str) -> dict[str, Any]:
        instance = self._instance(idx)
        meta = instance_meta(self.root, idx)
        return {
            "headless": bool(meta.get("headless", True)),
            "memoryMb": instance.memory_mb,
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

    def set_headless(self, idx: str, headless: bool) -> dict[str, Any]:
        self._instance(idx)
        update_instance_meta(self.root, idx, headless=bool(headless))
        return self.instance_options(idx)


def _int(raw: object) -> int | None:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


class AvdManager(AppLaunchMixin, _AvdCore):
    """一条官方模拟器安装的管理器。

    ``AppLaunchMixin.open`` 先开机再拉应用；这里在它之前挡掉已知不兼容的游戏（连模拟器都不开），
    并把拉应用改走私有 adb、先结束其它第三方游戏。
    """

    store_package = None

    async def open(self, idx: str, package_name: str = "") -> DeviceInfo:
        if package_name:
            reason = incompatible_reason(package_name)
            if reason is not None:
                raise IncompatibleGameError(reason)
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
    if not Path(manager_exe).is_file():
        raise RuntimeError(f"找不到官方模拟器程序 {manager_exe}")
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
