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

"""ModAVD 一条安装的设备管理器。

对门面暴露的方法与雷电 / MuMu 两家后端相同（``open`` / ``close`` / ``getStatus`` /
``getInfo`` / ``list_devices`` / 四项设置 / 稳定模式 / 新建删除实例）。开关机、状态、实例设置与
增删都交给根目录里的 ModAVD 命令行 ``tools\\modavd.exe``（:mod:`.cli`），怎么开机、怎么关机由
modavd 决定。没有命令行的根目录不支持（:func:`build_manager` 直接报错）。
"""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NoReturn

import psutil

from app.models.emulator import (
    DeviceBase,
    DeviceInfo,
    DeviceRef,
    DeviceStatus,
    EmulatorRuntimePolicy,
)
from app.utils import get_logger

from ..applaunch import (
    AppLaunchMixin,
    AppLaunchResult,
    ensure_app_running,
)
from ..settings import FieldValue, InstanceSettings, SettingsConflictError
from ..settings import validate_changes as validate_setting_changes
from . import cli as modavd_cli
from . import host, precheck, update_stage, updater
from .components import (
    component_installed,
    emulator_exe,
    missing_components_message,
    root_from_manager_exe,
    root_key,
)
from .constants import (
    DISPLAY_PRESETS,
    KEEP_PACKAGES,
    LOGS_DIR,
    MAX_NATIVE_INDEX,
    PORT_BASE,
    PORT_STEP,
    RECOMMENDED_MEMORY_MB,
    REQUIRED_COMPONENTS,
    WATCHDOG_INTERVAL_SECONDS,
    WATCHDOG_PROBE_TIMEOUT_SECONDS,
    WATCHDOG_STRIKES,
    InstancePorts,
    adb_port,
    avd_name,
    console_port,
    default_instance_ports,
    valid_native_index,
)
from .instances import (
    AvdInstance,
    display_changes,
    instance_meta,
    list_instances,
    memory_for,
    validate_fps,
    validate_options,
    validate_resolution,
)

logger = get_logger("ModAVD 管理")

#: 界面上「打开游戏中心」之类一次点击的上限（ModAVD 没有游戏中心，留作接口一致）。
_LAUNCH_TIMEOUT_CAP = 45.0
_BOOT_TIMEOUT_CAP = 120.0


def map_status(status: str | None, busy: str | None = "") -> DeviceStatus:
    """把 modavd 的状态字符串翻译成公共 ``DeviceStatus``（:mod:`.cli` 只交回原样的字符串）。"""

    busy_value = (busy or "").strip().lower()
    status_value = (status or "").strip().lower()
    # 新建的初始化（后台开机、装输入法和执行桥、关机）做完前一律是新建中，不管那几次开机从外面看像什么
    if status_value == "creating" or busy_value == "creating":
        return DeviceStatus.CREATING
    if busy_value == "stopping":
        return DeviceStatus.CLOSEING
    if busy_value:
        return DeviceStatus.STARTING
    if status_value == "starting":
        return DeviceStatus.STARTING
    if status_value == "create_failed":
        return DeviceStatus.CREATE_FAILED
    if status_value == "online":
        return DeviceStatus.ONLINE
    if status_value == "offline":
        return DeviceStatus.OFFLINE
    return DeviceStatus.STARTING


def _qemu_headless(process: psutil.Process) -> bool | None:
    """这台 qemu 是不是无头开的。模拟器带 ``-no-window`` 开机时起的是
    ``qemu-system-x86_64-headless.exe``，命令行里也带着 ``-no-window``；读不到进程信息返回 ``None``。"""
    try:
        name = (process.name() or "").lower()
        cmdline = process.cmdline()
    except (psutil.Error, OSError):
        return None
    return "headless" in name or "-no-window" in cmdline


def _silence_enabled(runtime_policy: EmulatorRuntimePolicy) -> bool:
    """宿主「静默模式」开没开；读不到按开，宁可无头。"""
    try:
        return bool(runtime_policy.silence_enabled())
    except Exception:  # noqa: BLE001
        return True


# ---- 冻结看门狗 -----------------------------------------------------------

#: ``{根目录键|原生索引: 看门狗任务}``。管理器会被频繁重建（状态轮询每轮一个），
#: 看门狗必须挂在模块上，跟着实例走而不是跟着管理器对象走。
_WATCHDOGS: dict[str, asyncio.Task] = {}
#: ``{根目录键|原生索引: 事件}``：这台实例有一次 open 正在开机 / 做开机后设置，做完置位。和看门狗一样
#: 挂在模块上（管理器对象会被频繁重建）。见 :meth:`_AvdCore.open`。
_OPENING: dict[str, asyncio.Event] = {}
_CLI_START_LOCKS: dict[str, asyncio.Lock] = {}
#: 等前一次 open 的上限 = 最长启动等待 + 这么多秒（modavd start 在开机之后还有设置要做，再留余量）。
_OPENING_WAIT_EXTRA_SECONDS = 300.0


def _cli_start_lock(key: str) -> asyncio.Lock:
    """只锁同一根目录的同一实例；不同实例可并行开机。"""
    return _CLI_START_LOCKS.setdefault(key, asyncio.Lock())


_SETTINGS_LOCKS: dict[str, asyncio.Lock] = {}


def _settings_lock(key: str) -> asyncio.Lock:
    """同一实例的改设置排队：对照 ``expected`` 和写入之间不能插进另一次写。"""
    return _SETTINGS_LOCKS.setdefault(key, asyncio.Lock())


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


#: ``{根目录键|原生索引: 锁}``：这台实例有一次 close 正在做（``modavd stop`` 还没返回）。同一台实例的
#: close 要排队；open 也要先等它关完，否则会把正在关机的实例当成已在运行。close 不等 open（开机中照样能关）。
_CLOSING: dict[str, asyncio.Lock] = {}


async def _wait_closing(key: str, label: str) -> None:
    """这台实例正在关机就等它关完。"""
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


def _start_watchdog(root: Path, native_index: str, pid: int, *, serial: str) -> None:
    key = _instance_key(root, native_index)
    existing = _WATCHDOGS.get(key)
    if existing is not None and not existing.done():
        return
    try:
        process = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return

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
                await ensure_logcat(root, native_index, serial=serial)
        return ok

    def is_alive() -> bool:
        try:
            return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            return False

    def on_frozen(reason: str) -> None:
        _FROZEN[key] = reason

    watchdog = FreezeWatchdog(
        f"ModAVD 实例 {avd_name(native_index)}",
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


async def ensure_logcat(root: Path, idx: str, *, serial: str | None = None) -> bool:
    """这台实例没有在落盘的 logcat 就起一个（文件 ``<根>\\logs\\logcat-mas_<i>-<时间>.txt``），返回起没起。

    按宿主进程表判断（:func:`~.host.find_logcat_processes`），不按本进程的记录：后端重启后上一个
    进程起的还在跑，不能再起第二份；私有 server 重启时 logcat 客户端会跟着退出，要能重新起来。
    开机后、重新登记成功后、冻结看门狗每轮巡检时都会调。``serial`` 不传时按默认端口段算。
    """
    if serial is None:
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
    idx = await _index_of_serial(root, serial)
    if idx is None or idx not in list_instances(root):
        return
    stale = await asyncio.to_thread(host.find_logcat_processes, root, serial)
    for process in stale:
        with suppress(psutil.Error):
            process.kill()
    if stale:
        await asyncio.to_thread(psutil.wait_procs, stale, 5)
    await ensure_logcat(root, idx, serial=serial)


async def _index_of_serial(root: Path, serial: str) -> str | None:
    """私有 server 上的序列号 → 实例编号。

    按 CLI ``list`` 返回的各实例 ``serial`` 对应（端口段由 modavd 定，根目录可以设 ``portBase``）；
    CLI 太老不带 ``serial``、或这次没问到时，按默认端口段反推（那时的 CLI 还不支持 ``portBase``）。
    根目录没有命令行时不认。
    """
    cli = modavd_cli.ModAvdCli(root)
    if not cli.executable_available:
        return None
    data: object = None
    with suppress(modavd_cli.CLIError):
        data = await cli.list()
    raw = data.get("instances") if isinstance(data, dict) else None
    items = (
        [item for item in raw if isinstance(item, dict)]
        if isinstance(raw, list)
        else []
    )
    if any("serial" in item for item in items):
        return next(
            (str(item.get("index")) for item in items if item.get("serial") == serial),
            None,
        )
    console = host._console_port_of(serial)
    if console is None:
        return None
    return str((console - PORT_BASE) // PORT_STEP)


host.add_reregister_hook(_logcat_after_reregister)


# ---- 管理器 ---------------------------------------------------------------


def _ports_from_cli(item: dict[str, Any], idx: str) -> InstancePorts:
    """``modavd list/info/status`` 的实例对象 → 端口与序列号。

    ``ports``、``serial`` 是 ModAVDManager v0.3.1（ModAVDManager#39，``portBase``）起才有的字段；
    更老的 CLI 不带，那时也还不支持 ``portBase``，按默认端口段算。
    """
    ports = item.get("ports")
    values = (
        [ports.get(key) for key in ("console", "adb", "grpc")]
        if isinstance(ports, dict)
        else []
    )
    if len(values) != 3 or not all(
        isinstance(value, int) and not isinstance(value, bool) for value in values
    ):
        return default_instance_ports(idx)
    console, adb, grpc = values
    serial = item.get("serial")
    if not isinstance(serial, str) or not serial:
        serial = host.serial_of(console)
    return InstancePorts(console, adb, grpc, serial)


class _AvdCore(DeviceBase):
    """只负责开关机与状态，不带应用拉起（由 :class:`AvdManager` 叠上）。"""

    def __init__(
        self,
        manager_exe: str | Path,
        max_wait_time: int,
        force_kill_on_close: bool,
        *,
        cli: modavd_cli.ModAvdCli,
    ) -> None:
        self.emulator_path = Path(manager_exe)
        self.root = root_from_manager_exe(manager_exe)
        self.config = SimpleNamespace(
            Info=SimpleNamespace(
                MaxWaitTime=int(max_wait_time),
                ForceKillOnClose=bool(force_kill_on_close),
                Type="avd",
                Path=str(manager_exe),
            )
        )
        #: 根目录的 ModAVD 命令行（:func:`build_manager` 给的；更新中是没做版本检查的那个，不起进程）。
        self._cli = cli

    # ---- 查询 -----------------------------------------------------------

    def _instances(self) -> dict[str, AvdInstance]:
        return list_instances(self.root)

    def _instance(self, idx: str) -> AvdInstance:
        instance = self._instances().get(str(idx))
        if instance is None:
            raise RuntimeError(f"ModAVD 实例 {idx} 不存在")
        return instance

    def _raise_cli_error(self, error: modavd_cli.CLIError) -> NoReturn:
        """把 modavd 的机读错误还原成旧管理器的异常类型。"""
        raise modavd_cli.map_cli_error(error) from error

    async def _raise_cli_precheck(
        self, error: modavd_cli.CLIError, memory_mb: int
    ) -> NoReturn:
        """用一次 check 找回 CLI 错误信封没有携带的具体阻断项。"""
        if error.code != "precheck_failed":
            self._raise_cli_error(error)
        try:
            result = await self._cli.check(memory=memory_mb)
        except modavd_cli.CLIError:
            self._raise_cli_error(error)
        self._raise_blocking_check_items(result, error.message, error.advice)
        self._raise_cli_error(error)

    async def _raise_cli_create_error(
        self, error: modavd_cli.CLIError, index: int | None
    ) -> NoReturn:
        """新建失败。v0.2.0 的 create 开机、装桥没做完会把实例留成「新建失败」，要用户删掉再建；
        没留下实例（参数错、起不了进程……）时按普通 CLI 错误报。编号交给 modavd 挑时（``None``）
        不知道是哪台，按普通 CLI 错误报。"""
        status = ""
        if index is not None:
            with suppress(modavd_cli.CLIError):
                data = await self._cli.status(str(index))
                if isinstance(data, dict):
                    status = str(data.get("status") or "").lower()
        if status in {"creating", "create_failed"}:
            advice = f"（建议：{error.advice}）" if error.advice else ""
            raise RuntimeError(
                f"新建没完成，实例 {index} 已标为新建失败，请在列表里删掉它再新建："
                f"{error.message}{advice}"
            ) from error
        self._raise_cli_error(error)

    @staticmethod
    def _raise_blocking_check_items(
        result: object, message: str, advice: str = ""
    ) -> None:
        items = result.get("items", []) if isinstance(result, dict) else []
        for item in items:
            if not isinstance(item, dict) or item.get("blocking") is not True:
                continue
            if item.get("ok") is False:
                raise precheck.PrecheckFailed(
                    precheck.PrecheckItem(
                        str(item.get("id") or "precheck"),
                        str(item.get("title") or "ModAVD 开机前检查"),
                        False,
                        True,
                        str(item.get("reason") or message),
                        str(item.get("advice") or advice),
                    )
                )

    @staticmethod
    def _cli_data_instance(data: object) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise RuntimeError("modavd 返回的实例数据不是对象")
        return data

    async def instance_ports(self, idx: str) -> InstancePorts:
        """这台实例的端口与序列号（:class:`~.constants.InstancePorts`）。

        问一次 ``modavd info``，用它给的 ``ports`` / ``serial``（根目录可能设了 ``portBase``，
        规则在 modavd 里）；一次操作里问一次，结果在这次操作里接着用，不要每算一个端口起一次进程。
        更新中（不起 CLI）时按默认端口段算。
        """
        idx = str(idx)
        if updater.update_in_progress(self.root):
            return default_instance_ports(idx)
        try:
            data = await self._cli.info(idx)
        except modavd_cli.CLIError as error:
            self._raise_cli_error(error)
        return _ports_from_cli(self._cli_data_instance(data), idx)

    def _device_info_from_cli(self, data: object) -> DeviceInfo:
        """把 ``list/info/status/start`` 的实例对象映射成公共设备信息。"""
        item = self._cli_data_instance(data)
        index = str(item.get("index", ""))
        status = map_status(item.get("status"), item.get("busy"))
        address = item.get("adb_address")
        if not isinstance(address, str) or not address:
            address = f"127.0.0.1:{adb_port(index)}" if index else ""
        pid = item.get("pid")
        if not isinstance(pid, int) or pid <= 0:
            pid = None
        running = item.get("running") is True or pid is not None
        started_at: float | None = None
        headless: bool | None = None
        if pid is not None:
            try:
                process = psutil.Process(pid)
                process_exe = Path(process.exe()).resolve()
                emulator_dir = Path(emulator_exe(self.root)).resolve().parent
                if emulator_dir not in process_exe.parents:
                    pid = None
                else:
                    started_at = process.create_time()
                    headless = _qemu_headless(process)
            except (OSError, psutil.Error):
                pid = None
        window = item.get("window")
        if isinstance(window, bool):
            # modavd 0.3.0 起 status / list 带 window：运行中有窗口时为 true
            headless = (not window) if running else None
        elif running and headless is None:
            # 旧版 modavd 没有这个字段、qemu 进程也认不出：按没有窗口算，宁可把显示置灰
            headless = True
        return DeviceInfo(
            str(item.get("title") or item.get("name") or index),
            status,
            address,
            process_id=pid,
            process_started_at=started_at,
            headless=headless,
            creation_error=(
                str(item.get("creation_error") or "")
                if status == DeviceStatus.CREATE_FAILED
                else ""
            ),
        )

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
            # 认不出是不是无头时按无头算（显示置灰），和命令行路径一致
            headless=(_qemu_headless(process) is not False)
            if process is not None
            else None,
        )

    async def getStatus(self, idx: str) -> DeviceStatus:
        if updater.update_in_progress(self.root):
            if str(idx) not in self._instances():
                return DeviceStatus.NOT_FOUND
            process = await asyncio.to_thread(
                host.find_qemu_process, avd_name(idx), console_port(idx)
            )
            return (
                DeviceStatus.STARTING if process is not None else DeviceStatus.OFFLINE
            )
        if _instance_key(self.root, str(idx)) in _FROZEN:
            return DeviceStatus.ERROR
        try:
            data = await self._cli.status(str(idx))
        except modavd_cli.CLIError as error:
            if error.code == "not_found":
                return DeviceStatus.NOT_FOUND
            self._raise_cli_error(error)
        item = self._cli_data_instance(data)
        return map_status(item.get("status"), item.get("busy"))

    async def getInfo(self, idx: str | None) -> dict[str, DeviceInfo]:
        if updater.update_in_progress(self.root):
            instances = self._instances()
            processes = await asyncio.to_thread(self._scan_processes)
            selected = [str(idx)] if idx is not None else sorted(instances)
            snapshot: dict[str, DeviceInfo] = {}
            for item_idx in selected:
                instance = instances.get(item_idx)
                if instance is None:
                    continue
                status = (
                    DeviceStatus.STARTING
                    if item_idx in processes
                    else DeviceStatus.OFFLINE
                )
                if _instance_key(self.root, item_idx) in _FROZEN:
                    status = DeviceStatus.ERROR
                snapshot[item_idx] = self._device_info(
                    item_idx, instance.title, status, processes.get(item_idx)
                )
            return snapshot
        try:
            if idx is not None:
                data = await self._cli.info(str(idx))
                item = self._cli_data_instance(data)
                key = str(item.get("index", idx))
                info = self._device_info_from_cli(item)
                if _instance_key(self.root, key) in _FROZEN:
                    info.status = DeviceStatus.ERROR
                return {key: info}
            data = await self._cli.list()
        except modavd_cli.CLIError as error:
            self._raise_cli_error(error)
        if not isinstance(data, dict) or not isinstance(data.get("instances"), list):
            raise RuntimeError("modavd list 缺少 instances")
        result: dict[str, DeviceInfo] = {}
        for raw in data["instances"]:
            item = self._cli_data_instance(raw)
            key = str(item.get("index", ""))
            if key:
                info = self._device_info_from_cli(item)
                if _instance_key(self.root, key) in _FROZEN:
                    info.status = DeviceStatus.ERROR
                result[key] = info
        return result

    async def list_devices(self) -> dict[str, str]:
        if updater.update_in_progress(self.root):
            return {idx: instance.title for idx, instance in self._instances().items()}
        try:
            data = await self._cli.list()
        except modavd_cli.CLIError as error:
            self._raise_cli_error(error)
        if not isinstance(data, dict) or not isinstance(data.get("instances"), list):
            raise RuntimeError("modavd list 缺少 instances")
        return {
            str(item.get("index")): str(
                item.get("title") or item.get("name") or item.get("index")
            )
            for item in data["instances"]
            if isinstance(item, dict) and item.get("index") is not None
        }

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

    async def setVisible(self, idx: str, is_visible: bool) -> DeviceStatus:
        """显示 / 隐藏带窗口开机的实例（``modavd window``）。

        无头开机的实例没有窗口，开机后也补不出窗口；模拟器页的显示 / 隐藏按钮对它置灰
        （:attr:`DeviceInfo.headless`）。运行中不切换有头无头，不靠重启补窗口。
        不抛异常：脚本在静默模式下每轮都会调这个，抛了会把整次运行判失败。
        """
        if updater.update_in_progress(self.root):
            return await self.getStatus(idx)
        try:
            await self._cli.window(str(idx), visible=is_visible)
        except modavd_cli.CLIError as error:
            logger.warning(f"实例 {idx} 显示窗口失败，忽略本轮设置: {error.message}")
            return DeviceStatus.UNKNOWN
        return await self.getStatus(idx)

    # ---- 启动 -----------------------------------------------------------

    def _check_components(self) -> None:
        missing = [
            c.name for c in REQUIRED_COMPONENTS if not component_installed(self.root, c)
        ]
        if missing:
            raise RuntimeError(missing_components_message(missing))

    async def open(self, idx: str, package_name: str = "") -> DeviceInfo:
        """开机（``modavd start``）。同一台实例上的 open 排队：前一次还没做完，后一次先等它，免得两次
        同时开同一台。等太久（:data:`_OPENING_WAIT_EXTRA_SECONDS` 加最长启动等待）就记日志、顶替前一次
        登记自己，照常往下走。"""
        idx = str(idx)
        key = _instance_key(self.root, idx)
        max_wait = float(self.config.Info.MaxWaitTime)
        mine = await _claim_opening(
            key, f"ModAVD 实例 {idx}", max_wait + _OPENING_WAIT_EXTRA_SECONDS
        )
        try:
            await _wait_closing(key, f"ModAVD 实例 {idx}")
            return await self._open(idx, key, max_wait)
        finally:
            mine.set()
            if _OPENING.get(key) is mine:
                del _OPENING[key]

    async def _open(self, idx: str, key: str, max_wait: float) -> DeviceInfo:
        _FROZEN.pop(key, None)
        if updater.update_in_progress(self.root):
            raise RuntimeError("ModAVD 正在更新，更新完再开机")
        if await self._cli_creating(idx):
            raise RuntimeError(
                f"ModAVD 实例 {idx} 正在新建（后台开机做初始化），等新建完成再开机"
            )
        self._check_components()
        memory_mb = memory_for(instance_meta(self.root, idx))
        recommended = RECOMMENDED_MEMORY_MB.get(self._open_package or "")
        if recommended and memory_mb < recommended:
            logger.warning(
                f"ModAVD 实例 {idx} 内存 {memory_mb} MB，低于 {self._open_package} 的推荐值 "
                f"{recommended} MB，可在实例设置里调大"
            )
        async with _cli_start_lock(key):
            try:
                data = await self._cli.start(
                    idx,
                    window=self._open_window,
                    timeout=max_wait,
                )
            except modavd_cli.CLIError as error:
                await self._raise_cli_precheck(error, memory_mb)
        if not isinstance(data, dict):
            raise RuntimeError("modavd start 返回的数据不是对象")
        warnings = data.get("warnings")
        if isinstance(warnings, list):
            for warning in warnings:
                logger.warning(f"实例 {idx} modavd start: {warning}")
        for name in ("log_file", "logcat_file"):
            if data.get(name):
                logger.debug(f"实例 {idx} modavd {name}: {data[name]}")
        if data.get("setup_pending"):
            logger.warning(f"实例 {idx} modavd start: 一次性设置仍待完成")
        if isinstance(warnings, list) and any(
            any(word in str(warning) for word in ("写客体脚本", "推送"))
            for warning in warnings
        ):
            logger.warning(f"实例 {idx} 开机脚本步骤失败，重新调用 modavd start 补做")
            async with _cli_start_lock(key):
                data = await self._cli.start(
                    idx,
                    window=self._open_window,
                    timeout=max_wait,
                )
            if not isinstance(data, dict):
                raise RuntimeError("modavd start 重试返回的数据不是对象")
        raw_instance = data.get("instance", data)
        info = self._device_info_from_cli(raw_instance)
        if info.process_id is not None:
            # 运行中不切换有没有窗口：开机后方式和这次要的不一样，就是本来就开着
            with suppress(psutil.Error):
                self._log_window_mode(idx, psutil.Process(info.process_id))
            # 端口段由 modavd 定（根目录可以设 portBase），看门狗用 start 返回的序列号
            ports = _ports_from_cli(self._cli_data_instance(raw_instance), idx)
            _start_watchdog(self.root, idx, info.process_id, serial=ports.serial)
        logger.info(
            f"ModAVD 实例 {idx} 已由 modavd start 启动"
            f"（{'带窗口' if self._open_window else '静默'}）"
        )
        return info

    #: 这次 open 要跑的游戏包名（:class:`AvdManager` 在开机前设），只用来对照推荐内存记日志。
    _open_package: str = ""
    #: 这次开机要不要窗口（:class:`AvdManager` 在开机前按启动入口设）；没人设时按无头。
    _open_window: bool = False

    def _log_window_mode(self, idx: str, process: psutil.Process | None) -> None:
        """有没有窗口只在开机那一刻定，运行中不切换（不重启、不补窗口）。实例已在运行、方式和这次要的
        不一样时照常接着用，只记一笔：静默模式的任务碰上带窗口的，随后会把窗口隐藏。"""
        if process is None:
            return
        headless = _qemu_headless(process)
        if headless is None or headless != self._open_window:
            return
        running = "无头" if headless else "带窗口"
        wanted = "带窗口" if self._open_window else "无头"
        logger.info(
            f"ModAVD 实例 {idx} 已在{running}运行，这次按{wanted}开机：运行中不切换，"
            f"接着用{running}的"
        )

    async def _cli_creating(self, idx: str) -> bool:
        """这台是不是正在新建（modavd v0.2.0 起 create 建完文件还要在后台开机做初始化）。

        先看 ``mas-avd.json`` 里的 ``creationState``（modavd 自己写的），记着 ``creating`` 再问 modavd：
        新建程序中途被结束的也留着 ``creating``，modavd 按新建失败报，不算新建中。平常一次子进程都不起。
        记着 ``creating`` 却问不到 modavd 时不放行：这时贸然关机可能正好打断新建。"""
        if instance_meta(self.root, idx).get("creationState") != "creating":
            return False
        try:
            data = await self._cli.status(idx)
        except modavd_cli.CLIError as error:
            raise RuntimeError(
                f"ModAVD 实例 {idx} 可能还在新建，但查不到 modavd 的状态（{error.message}），"
                "稍后再试"
            ) from error
        return (
            isinstance(data, dict)
            and map_status(data.get("status"), data.get("busy"))
            == DeviceStatus.CREATING
        )

    # ---- 客体命令 -------------------------------------------------------

    async def _shell(
        self,
        idx: str,
        command: str,
        timeout: float = 30.0,
        *,
        serial: str | None = None,
    ) -> tuple[int, str]:
        """``serial`` 传 :meth:`instance_ports` 给的；不传时按默认端口段算。"""
        return await host.run_adb(
            self.root,
            "shell",
            command,
            serial=serial or host.serial_of(console_port(idx)),
            timeout=timeout,
        )

    # ---- 关机 -----------------------------------------------------------

    async def close(self, idx: str) -> DeviceStatus:
        """关机（``modavd stop``）。同一台实例的 close 排队做（见 :data:`_CLOSING`）。"""
        idx = str(idx)
        key = _instance_key(self.root, idx)
        lock = _CLOSING.setdefault(key, asyncio.Lock())
        if lock.locked():
            logger.info(f"ModAVD 实例 {idx} 正由另一次关闭在关，等它关完再继续")
        async with lock:
            return await self._close(idx, key)

    async def _close(self, idx: str, key: str) -> DeviceStatus:
        _stop_watchdog(self.root, idx)
        _FROZEN.pop(key, None)
        if updater.update_in_progress(self.root):
            return DeviceStatus.OFFLINE
        # modavd stop 不拦新建中的实例，关了就把新建的初始化打断，留下一台「新建失败」
        if await self._cli_creating(idx):
            raise RuntimeError(
                f"ModAVD 实例 {idx} 正在新建（后台开机做初始化），新建完成前不能关机"
            )
        try:
            await self._cli.stop(
                idx,
                force=bool(self.config.Info.ForceKillOnClose),
            )
        except modavd_cli.CLIError as error:
            self._raise_cli_error(error)
        logger.info(f"ModAVD 实例 {idx} 已由 modavd stop 关闭")
        return DeviceStatus.OFFLINE

    # ---- 设置 -----------------------------------------------------------

    async def read_instance_settings(self, idx: str) -> InstanceSettings:
        if not updater.update_in_progress(self.root):
            try:
                raw = self._cli_data_instance(await self._cli.info(str(idx)))
            except modavd_cli.CLIError as error:
                self._raise_cli_error(error)
            config = raw.get("config")
            config = config if isinstance(config, dict) else {}

            def value(name: str) -> int | None:
                item = config.get({"memoryMb": "memory_mb"}.get(name, name))
                return (
                    item
                    if isinstance(item, int) and not isinstance(item, bool)
                    else None
                )

            return InstanceSettings(
                fields={
                    name: FieldValue(value(name), "saved")
                    for name in ("width", "height", "dpi", "cpu", "memoryMb", "fps")
                }
            )
        # 更新中不起 CLI，直接读实例文件
        instance = self._instances().get(str(idx))
        if instance is None:
            return InstanceSettings(
                fields={
                    name: FieldValue(None, "unreadable")
                    for name in ("width", "height", "dpi", "cpu", "memoryMb", "fps")
                }
            )
        # 读取当前档位，下次开机前按相同档位写回。
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
        """可改 CPU、内存与帧率（30 / 60，写 ``hw.lcd.vsync``），分辨率两档联动 DPI，保留方向，都是下次启动生效。

        同一台实例的改设置排队做：两个请求拿着同一份 ``expected`` 同时来时，后一个会看到前一个写的值、
        报冲突，不会两个都说成功、互相覆盖。"""
        async with _settings_lock(_instance_key(self.root, str(idx))):
            return await self._write_instance_settings(idx, changes, expected)

    async def _write_instance_settings(
        self, idx: str, changes: dict, expected: dict | None = None
    ) -> dict[str, int]:
        if updater.update_in_progress(self.root):
            raise RuntimeError("ModAVD 正在更新，更新完再改设置")
        data_gb: int | None = None
        setting_changes = dict(changes)
        if "dataPartitionGb" in setting_changes:
            raw_data = setting_changes.pop("dataPartitionGb")
            if isinstance(raw_data, bool):
                raise ValueError("设置项 dataPartitionGb 需要一个整数")
            _, _, data_gb = validate_options(None, None, raw_data)
        cleaned = validate_setting_changes(setting_changes) if setting_changes else {}
        current = (await self.read_instance_settings(idx)).values()
        raw_info = self._cli_data_instance(await self._cli.info(str(idx)))
        raw_config = raw_info.get("config")
        raw_config = raw_config if isinstance(raw_config, dict) else {}
        current_data = raw_config.get("data_partition_gb")
        if not isinstance(current_data, int):
            current_data = 0
        if expected:
            conflicts = [
                name
                for name in [*cleaned, "dataPartitionGb"]
                if name in expected
                and (current.get(name) if name != "dataPartitionGb" else current_data)
                != expected[name]
            ]
            if conflicts:
                raise SettingsConflictError(conflicts)
        if data_gb is not None and data_gb <= current_data:
            raise ValueError(
                f"数据盘只能改大（当前 {current_data} GB，收到 {data_gb} GB）"
            )
        display = _display_settings(current, cleaned)
        kwargs: dict[str, Any] = {}
        if "memoryMb" in cleaned:
            kwargs["memory"] = cleaned["memoryMb"]
        if "cpu" in cleaned:
            kwargs["cpu"] = cleaned["cpu"]
        if "fps" in cleaned:
            kwargs["fps"] = cleaned["fps"]
        if display and any(current.get(key) != value for key, value in display.items()):
            kwargs["resolution"] = (
                1080 if max(display["width"], display["height"]) == 1920 else 720
            )
        if data_gb is not None:
            kwargs["data_gb"] = data_gb
        if not kwargs:
            return display
        try:
            result = await self._cli.set(str(idx), **kwargs)
        except modavd_cli.CLIError as error:
            self._raise_cli_error(error)
        applied = result.get("applied", {}) if isinstance(result, dict) else {}
        if not isinstance(applied, dict):
            applied = {}
        converted = {
            {"memory_mb": "memoryMb", "data_partition_gb": "dataPartitionGb"}.get(
                key, key
            ): value
            for key, value in applied.items()
            if key in {"title", "memory_mb", "cpu", "fps", "data_partition_gb"}
        }
        result_values = {
            key: value
            for key, value in converted.items()
            if key in ("cpu", "memoryMb", "fps", "dataPartitionGb")
        }
        if data_gb is not None and "dataPartitionGb" not in result_values:
            result_values["dataPartitionGb"] = data_gb
        result_values.update(display)
        return result_values

    async def read_stable_mode(self, idx: str) -> tuple[bool, list[str]]:
        # ModAVD 没有会干扰截图识别的厂商功能，天然就是「稳定」的
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
        resolution: int | None = None,
    ) -> str:
        """新建实例，返回原生索引。不给索引就取最小的、端口也空着的那个。

        内存、核数、帧率不给就用默认 6 GB / 6 核 / 60（:data:`~.constants.DEFAULT_MEMORY_MB` /
        ``DEFAULT_CPU`` / ``DEFAULT_FPS``）；分辨率默认 1080p / DPI 280。
        """
        memory, cores, data_gb = validate_options(memory_mb, cpu, data_partition_gb)
        refresh = validate_fps(fps)
        preset = validate_resolution(resolution)
        if updater.update_in_progress(self.root):
            raise RuntimeError("ModAVD 正在更新，更新完再新建实例")
        self._check_components()
        try:
            check_result = await self._cli.check(memory=memory)
        except modavd_cli.CLIError as error:
            await self._raise_cli_precheck(error, memory)
        self._raise_blocking_check_items(check_result, "ModAVD 开机前检查未通过")
        if native_index is None:
            listing = await self._cli.list()
            raw_items = (
                listing.get("instances", []) if isinstance(listing, dict) else []
            )
            existing = {
                int(raw["index"])
                for raw in raw_items
                if isinstance(raw, dict) and str(raw.get("index", "")).isdigit()
            }
            # 根目录换了端口段（portBase，modavd 0.3.1 起 list 带 port_base）时，空闲编号由
            # modavd 按它自己的端口段挑；下面 _free_index 只认得默认端口段
            port_base = listing.get("port_base") if isinstance(listing, dict) else None
            if port_base in (None, PORT_BASE):
                native_index = await asyncio.to_thread(self._free_index, existing)
        else:
            native_index = int(native_index)
            if not valid_native_index(native_index):
                raise ValueError(f"原生索引 {native_index} 不可用")
        # 上面的检查和选编号要等几个子进程，更新可能在这期间开始：起 create 之前再看一次
        if updater.update_in_progress(self.root):
            raise RuntimeError("ModAVD 正在更新，更新完再新建实例")
        try:
            data = await self._cli.create(
                index=native_index,
                title=name,
                memory=memory,
                cpu=cores,
                data_gb=data_gb,
                fps=refresh,
                resolution=preset,
            )
        except modavd_cli.CLIError as error:
            await self._raise_cli_create_error(error, native_index)
        item = self._cli_data_instance(data)
        index = item.get("index", native_index)
        if index is None:
            raise RuntimeError("modavd create 没有返回实例编号")
        logger.info(f"已由 modavd create 新建 ModAVD 实例 {index}")
        return str(index)

    @staticmethod
    def _free_index(existing: set[int]) -> int:
        for index in range(0, MAX_NATIVE_INDEX + 1):
            if not valid_native_index(index) or index in existing:
                continue
            port = console_port(index)
            if host.busy_ports([port, port + 1, port + 2]):
                continue
            return index
        raise RuntimeError("ModAVD 实例已满（端口段 20000–20100 最多 9 台）")

    async def delete_instance(self, native_index: str) -> None:
        if updater.update_in_progress(self.root):
            raise RuntimeError("ModAVD 正在更新，更新完再删除实例")
        try:
            await self._cli.delete(str(native_index))
        except modavd_cli.CLIError as error:
            self._raise_cli_error(error)
        _FROZEN.pop(_instance_key(self.root, str(native_index)), None)
        logger.info(f"已由 modavd delete 删除 ModAVD 实例 {native_index}")

    # ---- 实例选项 ------------------------------------------------------

    async def instance_options(self, idx: str) -> dict[str, Any]:
        instance = self._instance(idx)
        meta = instance_meta(self.root, idx)
        ports = await self.instance_ports(idx)
        return {
            "memoryMb": memory_for(meta),
            "cpu": instance.cpu,
            "fps": instance.fps,
            "dataPartitionGb": instance.data_partition_gb,
            "initialized": bool(meta.get("initialized", False)),
            "launcher": meta.get("launcher") or "",
            "renderer": meta.get("renderer") or "",
            "softwareRenderer": bool(meta.get("softwareRenderer", False)),
            "consolePort": ports.console,
            "adbPort": ports.adb,
            "grpcPort": ports.grpc,
        }

    async def install_apk(self, idx: str, apk: Path) -> str:
        """在开着的实例里装一个 ``.apk``（``modavd install``，同包名覆盖安装、保留数据）。

        只收单个 ``.apk``：``.xapk`` / 拆分包不支持。返回安装结果行。"""
        if updater.update_in_progress(self.root):
            raise RuntimeError("ModAVD 正在更新，更新完再安装 APK")
        try:
            data = await self._cli.install(str(idx), apk)
        except modavd_cli.CLIError as error:
            self._raise_cli_error(error)
        if not isinstance(data, dict):
            raise RuntimeError("modavd install 返回的数据不是对象")
        output = str(data.get("output") or "Success")
        logger.info(f"已由 modavd install 给实例 {idx} 安装 {apk.name}")
        return output


def _int(raw: object) -> int | None:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _display_settings(current: dict, changes: dict[str, int]) -> dict[str, int]:
    """分辨率是宽、高、DPI 的整体档位；方向沿用实例，混合批量设置也按 AVD 的 DPI 写入。"""
    if not {"width", "height", "dpi"} & changes.keys():
        return {}
    width = changes.get("width", current.get("width"))
    height = changes.get("height", current.get("height"))
    preset = next(
        (
            key
            for key, (w, h, _) in DISPLAY_PRESETS.items()
            if (width, height) in ((w, h), (h, w))
        ),
        None,
    )
    if preset is None:
        raise ValueError("ModAVD 的分辨率只能选 1920×1080 或 1280×720")
    if (
        not {"width", "height"} & changes.keys()
        and changes.get("dpi") != DISPLAY_PRESETS[preset][2]
    ):
        raise ValueError("ModAVD 的 DPI 随分辨率档位切换，不能单独修改")
    display = display_changes(
        {
            "hw.lcd.width": str(current.get("width") or 0),
            "hw.lcd.height": str(current.get("height") or 0),
        },
        preset,
    )
    return {
        "width": int(display["hw.lcd.width"]),
        "height": int(display["hw.lcd.height"]),
        "dpi": int(display["hw.lcd.density"]),
    }


class AvdHostAdb:
    """MAS 宿主进程对一台 ModAVD 实例发 adb 命令的通道：私有 server ``-P <adbServerPort>
    -s emulator-<控制台端口>``。脚本的 adb server 杀不到它，丢设备时 :func:`host.run_adb` 会重新登记。

    调用约定同 :data:`~..applaunch.AdbRunner`：``await runner(*args, timeout=…)`` → ``(返回码, 输出)``。
    给游戏更新检查（:func:`app.utils.common.game_apk.adb_runner_scope`）与失败截图（:meth:`screencap_png`）用。
    """

    def __init__(self, root: Path, native_index: str, *, serial: str) -> None:
        self.root = Path(root)
        self.native_index = str(native_index)
        self.serial = serial

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
                f"ModAVD 实例 {self.native_index} 截图失败（返回码 {code}）: {error[-200:]}"
            )
        return data


class AvdManager(AppLaunchMixin, _AvdCore):
    """一条 ModAVD 安装的管理器。

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
        cli: modavd_cli.ModAvdCli,
    ) -> None:
        super().__init__(
            manager_exe=manager_exe,
            max_wait_time=max_wait_time,
            force_kill_on_close=force_kill_on_close,
            cli=cli,
        )
        self.runtime_policy = runtime_policy

    async def host_adb(self, idx: str) -> AvdHostAdb:
        """宿主进程对这台实例发 adb 命令的通道（走私有 server，见 :class:`AvdHostAdb`）。"""
        self._instance(idx)
        ports = await self.instance_ports(idx)
        return AvdHostAdb(self.root, str(idx), serial=ports.serial)

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

    async def restart(self, idx: str, *, manual: bool = False) -> DeviceInfo:
        """重启 = 先关机再开机（modavd 0.3.0 起没有 ``restart`` 命令）。

        开机照 :meth:`open` 按这次的入口定有没有窗口；关机和开机之间不算运行中切换。看门狗、开机错开、
        开机超时和取消的收尾都由 :meth:`close` / :meth:`open` 各自做。先把更新中、新建中、
        组件不全这几种开不了机的情况拦在关机之前，免得关掉了再开不起来。"""
        idx = str(idx)
        if updater.update_in_progress(self.root):
            raise RuntimeError("ModAVD 正在更新，更新完再重启")
        if await self._cli_creating(idx):
            raise RuntimeError(
                f"ModAVD 实例 {idx} 正在新建（后台开机做初始化），等新建完成再重启"
            )
        self._check_components()
        await self.close(idx)
        return await self.open(idx, manual=manual)

    async def launch_app(
        self,
        idx: str,
        package_name: str,
        info: DeviceInfo | None = None,
        *,
        launch_timeout: float | None = None,
    ) -> AppLaunchResult:
        serial = (await self.instance_ports(idx)).serial
        root = self.root

        async def run_adb(*args: str, timeout: float = 20.0) -> tuple[int, str]:
            return await host.run_adb(root, *args, serial=serial, timeout=timeout)

        await self.stop_background_games(idx, keep=package_name, serial=serial)
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            try:
                result = await self._cli.shell(
                    idx,
                    "test",
                    "-d",
                    "/sdcard/Android/data",
                    timeout=5,
                )
            except modavd_cli.CLIError as error:
                # 探一次失败（adb 一时连不上之类）当作还没挂好，到点照常拉游戏
                logger.debug(f"实例 {idx} 探 /sdcard 失败: {error.message}")
                result = None
            if (
                isinstance(result, dict)
                and isinstance(result.get("exit_code"), int)
                and result["exit_code"] == 0
            ):
                break
            await asyncio.sleep(1.0)
        else:
            logger.warning(
                f"实例 {idx} 的 /sdcard/Android/data 未在 30 秒内挂好，继续拉起 {package_name}"
            )
        max_wait = float(self.config.Info.MaxWaitTime)
        return await ensure_app_running(
            run_adb,
            package_name,
            boot_timeout=min(max_wait, _BOOT_TIMEOUT_CAP),
            launch_timeout=launch_timeout or min(max_wait, _LAUNCH_TIMEOUT_CAP),
            label=str(idx),
        )

    async def stop_background_games(
        self, idx: str, keep: str, *, serial: str | None = None
    ) -> list[str]:
        """前台只留要跑的那个游戏，其余第三方应用直接结束（用户 09-26 定）。

        只动 ``pm list packages -3``（用户装的应用）；系统包、谷歌服务不在其中。桌面与当前
        输入法另外排除。冻结不释放内存，低内存下后台游戏应当直接结束（预研 §6.11）。
        ``serial`` 是调用方这次已经问到的序列号（:meth:`instance_ports`）。
        """
        code, output = await self._shell(idx, "pm list packages -3", serial=serial)
        if code != 0:
            logger.warning(f"实例 {idx} 列第三方应用失败，跳过后台清理: {output}")
            return []
        packages = [
            line.split(":", 1)[1].strip()
            for line in output.splitlines()
            if line.startswith("package:")
        ]
        _, ime = await self._shell(
            idx, "settings get secure default_input_method", serial=serial
        )
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
            idx,
            " ; ".join(f"am force-stop {package}" for package in targets),
            serial=serial,
        )
        logger.info(f"实例 {idx} 已结束后台应用: {targets}")
        return targets


def opening_instances(root: Path) -> list[str]:
    """这个根目录下正在开机（``open`` 还没做完，含开机前检查到 ``modavd start`` 返回之间）的实例。"""
    prefix = f"{root_key(root)}|"
    return sorted(
        key[len(prefix) :] for key in list(_OPENING) if key.startswith(prefix)
    )


def running_instances(root: Path) -> list[str]:
    """这个根目录下开着的实例（原生索引）。

    只算 qemu 可执行文件就在这个根目录 ``sdk\\emulator`` 下的，免得把另一个根目录的同名实例算进来；
    限定了根目录，实例就只按命令行里的 ``-avd mas_<i>`` 认，不比端口：根目录可以设 ``portBase``
    换一段端口（由 modavd 决定）。
    """
    ours = {item["pid"] for item in update_stage.processes_using(root)}
    wanted = {avd_name(idx): idx for idx in list_instances(root)}
    found: set[str] = set()
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if process.info.get("pid") not in ours:
                continue
            name = (process.info.get("name") or "").lower()
            cmdline = process.info.get("cmdline") or []
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if not name.startswith("qemu-system"):
            continue
        found.update(
            wanted[avd]
            for flag, avd in zip(cmdline, cmdline[1:])
            if flag == "-avd" and avd in wanted
        )
    return sorted(found)


async def build_manager(
    manager_exe: str,
    max_wait_time: int,
    force_kill_on_close: bool = False,
    *,
    runtime_policy: EmulatorRuntimePolicy,
) -> AvdManager:
    """与雷电 / MuMu 的 ``build_manager`` 同签名。``manager_exe`` 是 ``sdk\\emulator\\emulator.exe``。

    根目录里没有命令行 ``tools\\modavd.exe`` 就报错。更新中只看它在不在，给一个没做版本检查的
    客户端（不起进程，查询都退到文件 / 进程快照）；平常先做版本检查（:func:`~.cli.resolve_cli`）。
    """
    root = root_from_manager_exe(manager_exe)
    probe = modavd_cli.ModAvdCli(root)
    if not probe.executable_available:
        raise RuntimeError(f"找不到 ModAVD 命令行 {probe.exe}")
    if updater.update_in_progress(root):
        cli = probe
    else:
        resolved = await modavd_cli.resolve_cli(root)
        if resolved is None:
            # 两次检查之间命令行被删了
            raise RuntimeError(f"找不到 ModAVD 命令行 {probe.exe}")
        cli = resolved
    return AvdManager(
        manager_exe=manager_exe,
        max_wait_time=max_wait_time,
        force_kill_on_close=force_kill_on_close,
        runtime_policy=runtime_policy,
        cli=cli,
    )


__all__ = [
    "AvdManager",
    "FreezeWatchdog",
    "build_manager",
    "opening_instances",
    "running_instances",
    "emulator_exe",
]
