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

"""Emulator 2.0 的雷电 14 后端。

继承旧 ``LDManager`` 的启动、关闭、状态、实例锁和配置守卫。
「大雷主人模式」沿用旧版全局开关，在启动前应用安装级设置，保留游戏中心入口。
老板键按实例读取；设置写入与配置守卫使用同一把实例锁。
启动后多一道「虚拟机真的起来了吗」的核对，VBox 服务卡住时自愈一次，见 :mod:`.vbox`。
"""

import asyncio
import json
import os
import shutil
import time
from pathlib import Path

import psutil

from app.models.config import EmulatorConfig
from app.models.emulator import DeviceInfo, DeviceRef, DeviceStatus
from app.utils import ProcessRunner, get_logger
from app.utils.emulator.ldplayer import _INSTANCE_CONFIG_SNAPSHOTS, LDManager
from app.utils.platform import IS_WINDOWS

from .adb import parse_adb_devices, resolve_serial
from .applaunch import AppLaunchMixin, is_package_missing, is_package_present
from .bosskey import BossKey, read_boss_key
from .master_mode import is_master_mode_enabled, ldplayer_clean_mode_args
from .settings import (
    InstanceSettings,
    SettingsConflictError,
    apply_changes,
    build_settings,
    detect_conflicts,
    validate_changes,
)
from .stability import LDPLAYER_ITEMS, evaluate, safe_writes
from .vbox import (
    VBOX_SERVICE_PROCESS,
    VmProbe,
    complete_vbox_runtime,
    live_vm_pids,
    missing_runtime_sentinels,
    resolve_vbox_runtime_dir,
    restart_vbox_service,
    vm_is_missing,
)


def _dig_flat(config: dict, key: str) -> str | None:
    """取一个平铺键的值。

    雷电这几项是真正的布尔（``true`` / ``false``），
    :mod:`.stability` 统一按字符串比，所以这里直接转成字符串。
    """
    if key not in config:
        return None
    return str(config[key])


if IS_WINDOWS:
    import keyboard
    import win32gui

logger = get_logger("Emulator2 雷电管理")

#: 新建 / 删除实例后复核 list2 的次数与间隔。
#: 雷电对这两个操作既不给可靠返回码, 也不保证立刻生效。
_INSTANCE_MUTATION_RETRIES = 3
_INSTANCE_MUTATION_DELAY_SECONDS = 2.0

#: adb devices 的缓存时长与超时。状态轮询几秒一次, 不缓存会每轮起一次子进程。
_ADB_CACHE_SECONDS = 5.0
_ADB_QUERY_TIMEOUT = 10

#: 别家模拟器独有的系统应用。装着其中任何一个, 就说明这个序列号背后不是雷电。
#:
#: 用「认出别人」而不是「认出自己」: 雷电游戏中心 ``com.android.flysilkworm``
#: 用户可以卸掉（旧实现还专门 ``pm disable-user`` 过它）, 拿它当雷电的身份证会误伤;
#: 反过来, MuMu 在自己镜像里一定有这两个包, 认出来就能确定「这台不是雷电」。
_FOREIGN_MARKER_PACKAGES = ("com.mumu.store", "com.netease.mumu.cloner")

#: 序列号归属的缓存时长。别家模拟器关掉之后端口会回到雷电手上, 不能永久缓存;
#: 但它也不会几秒一变, 所以比 adb devices 的缓存放宽一些。
_OWNERSHIP_CACHE_SECONDS = 30.0

#: 自愈前先 ``quit`` 那个只有窗口没有虚拟机的实例，等它从 list2 里下线的上限。
#: 僵尸窗口对 quit 的响应不可靠，超时就直接结束播放器进程。
_ZOMBIE_QUIT_TIMEOUT = 15.0
#: 雷电修复工具的提示，自愈做不了或做了没用时都指到这里。
_REPAIR_HINT = "请关闭所有雷电实例后运行雷电修复工具（安装目录下的 dnrepairer.exe）"


class BossKeyUnavailableError(RuntimeError):
    """无法确定该实例的老板键，隐藏操作不可用。

    带上 ``reason`` 供界面区分：是认不出修饰键、认不出按键，还是配置读不出来。
    """

    def __init__(self, idx: str, reason: str) -> None:
        super().__init__(f"无法确定雷电实例 {idx} 的老板键: {reason}")
        self.idx = idx
        self.reason = reason


class LDPlayer14Manager(AppLaunchMixin, LDManager):
    """一条雷电 14 安装的管理器。

    构造它需要一份**合成的单安装配置**：``Info.Type`` 必须是 ``ldplayer``
    （父类构造函数会校验），``Info.Path`` 必须正好是该安装的 ``ldconsole.exe``——
    实例锁的键就是这个路径 ``resolve().casefold()`` 加原生索引，路径口径不对
    就和旧配置、和设置写入各拿各的锁，配置守卫的回滚时序就挡不住了。

    ``AppLaunchMixin`` 必须排在 ``LDManager`` 前面：带包启动改走
    「先开模拟器、再用 adb 拉应用」两步，不再依赖 ``launch --packagename``。
    """

    #: 游戏中心 / 应用商店的包名，供「打开游戏中心」按钮使用。
    store_package = "com.android.flysilkworm"

    #: adb devices 的缓存：adb 路径 -> (在线序列号, 缓存到什么时候)。
    #: 放类属性而不是覆写 __init__，免得和父类的构造契约纠缠；按路径而不是按实例存，
    #: 因为管理器本身每个请求都会重建（见 :mod:`.service`），挂在实例上的缓存永远不会命中。
    _adb_cache: dict[str, tuple[list[str], float]] = {}

    #: 序列号 -> (是不是别家的, 缓存到什么时候)。同上放类属性；
    #: 「谁占着这个端口」本来就是整机的事实，几个管理器实例共用一份反而更对。
    _ownership_cache: dict[str, tuple[bool, float]] = {}

    async def _open_locked(self, idx: str, package_name: str) -> DeviceInfo:
        """在父类启动流程之上核对虚拟机是否真的起来，没起来就自愈一次。

        父类只看 ``list2`` 的「Android 已启动」标志。VBox 服务卡住时这个标志照样会置 1，
        而虚拟机进程根本不存在、adb 也看不到它，MAA 一连就是 ADB 异常；另一种形态是
        标志停在 2、父类等到超时。两种都在这里接住：确认整机没有别的虚拟机在跑之后，
        关掉僵尸窗口、重启 VBox 服务、再启动一次。详见 :mod:`.vbox`。

        启动前先查一眼 VBox 运行时是否被修复工具修残（缺 GPU 库），缺了就从雷电安装目录
        补回去；补不了就直接报错，不去启动一台注定几十秒内崩掉的虚拟机。
        """
        await self._ensure_vbox_runtime(idx)
        try:
            info = await super()._open_locked(idx, package_name)
        except RuntimeError as e:
            if not await self._vm_missing(idx):
                raise
            reason = str(e)
        else:
            if not await self._vm_missing(idx):
                return info
            reason = "雷电报告 Android 已启动，但没有虚拟机进程，adb 也看不到它"

        await self._recover_vbox_service(idx, reason)

        info = await super()._open_locked(idx, package_name)
        if await self._vm_missing(idx):
            raise RuntimeError(
                f"雷电实例 {idx} 重启 {VBOX_SERVICE_PROCESS} 后仍然起不来，{_REPAIR_HINT}"
            )
        logger.info(f"雷电实例 {idx} 在重启 {VBOX_SERVICE_PROCESS} 后已正常启动")
        return info

    async def _ensure_vbox_runtime(self, idx: str) -> None:
        """VBox 运行时缺 GPU 库时从雷电安装目录补回；补不回就报错。详见 :mod:`.vbox`。"""
        runtime_dir = await asyncio.to_thread(resolve_vbox_runtime_dir)
        if runtime_dir is None:
            return
        missing = await asyncio.to_thread(missing_runtime_sentinels, runtime_dir)
        if not missing:
            return

        install_dir = self.emulator_path.parent
        logger.warning(
            f"雷电 VBox 运行时 {runtime_dir} 缺少 {missing}，多半是雷电修复工具没修完；"
            f"尝试从 {install_dir} 补回"
        )
        try:
            copied = await asyncio.to_thread(
                complete_vbox_runtime, runtime_dir, install_dir
            )
        except PermissionError as e:
            raise RuntimeError(
                f"雷电实例 {idx} 无法启动：VBox 运行时 {runtime_dir} 缺少 {missing}"
                f"（雷电修复工具没修完），MAS 没有权限把文件补回去（{e}）。"
                f"请以管理员身份运行，或{_REPAIR_HINT}"
            ) from e

        still_missing = await asyncio.to_thread(missing_runtime_sentinels, runtime_dir)
        if still_missing:
            raise RuntimeError(
                f"雷电实例 {idx} 无法启动：VBox 运行时 {runtime_dir} 缺少 {still_missing}，"
                f"雷电安装目录里也找不到可补的副本（已补 {len(copied)} 个），{_REPAIR_HINT}"
            )
        logger.warning(
            f"已向雷电 VBox 运行时 {runtime_dir} 补回 {len(copied)} 个文件，继续启动实例 {idx}"
        )

    async def _probe_instances(self) -> dict[str, VmProbe]:
        """给这条安装的每台实例做一次「虚拟机在不在」探测。查不到 list2 时返回空表。"""
        try:
            devices = await self.get_device_info(None)
        except Exception as e:  # noqa: BLE001 - 探测本身失败就不做自愈判断
            logger.debug(f"探测雷电实例状态失败: {e}")
            return {}

        # 越过 adb devices 的缓存：这里要的是「现在」有没有，不是几秒前的视图
        serials = await self._list_adb_serials(fresh=True)
        probes: dict[str, VmProbe] = {}
        for idx, device in devices.items():
            others = [i for i in devices if str(i) != str(idx)]
            outcome = resolve_serial(idx, serials, others)
            probes[str(idx)] = VmProbe(
                in_android=device.in_android,
                vbox_pid=device.vbox_pid,
                serial_online=outcome.source != "formula",
            )
        return probes

    async def _vm_missing(self, idx: str) -> bool:
        """这台实例是不是「有窗口没虚拟机」。查不到时按不缺处理，不扩大事故。"""
        probe = (await self._probe_instances()).get(str(idx))
        return probe is not None and vm_is_missing(probe)

    async def _recover_vbox_service(self, idx: str, reason: str) -> None:
        """关掉僵尸窗口并重启 VBox 服务。

        只在**所有开着的实例都已经是僵尸**时才动手：服务一重启，它名下所有虚拟机一起死，
        任何一台还好好的（或正在启动、状态说不清的）实例都会被强关。两道闸门：

        - 整机没有任何 ``Ld9BoxHeadless.exe``——这条不分安装、不分归属，
          启动早期 list2 的 VBox pid 也可能是 -1，进程在就当它活着
        - 这条安装里其他开着的实例都是「Android 已启动但没虚拟机」的僵尸态；
          「正在启动」（in_android=2）说不清是刚起还是卡住，一律按还活着处理
        """
        running = live_vm_pids()
        if running:
            raise RuntimeError(
                f"雷电实例 {idx} 启动异常（{reason}），像是 {VBOX_SERVICE_PROCESS} 卡住了；"
                f"但整机仍有 {len(running)} 个雷电虚拟机进程在运行（可能包括本实例尚未就绪的），"
                f"重启该服务会把它们一起关掉。只有所有实例都异常时才会自动修复，"
                f"请关闭所有雷电实例后再重试，或{_REPAIR_HINT}"
            )

        probes = await self._probe_instances()
        healthy_others = sorted(
            other
            for other, probe in probes.items()
            if other != str(idx)
            and probe.in_android != 0
            and not (probe.in_android == 1 and vm_is_missing(probe))
        )
        if healthy_others:
            raise RuntimeError(
                f"雷电实例 {idx} 启动异常（{reason}），像是 {VBOX_SERVICE_PROCESS} 卡住了；"
                f"但实例 {', '.join(healthy_others)} 还在运行或正在启动，"
                f"重启该服务会把它们一起关掉。只有所有实例都异常时才会自动修复，"
                f"请关闭它们后再重试，或{_REPAIR_HINT}"
            )

        logger.warning(
            f"雷电实例 {idx} 启动异常（{reason}），整机没有任何雷电虚拟机在运行、"
            f"其他开着的实例也都是僵尸窗口，关闭该实例并重启 {VBOX_SERVICE_PROCESS} 后重试"
        )
        await self._quit_zombie_instance(idx)
        try:
            await restart_vbox_service()
        except PermissionError as e:
            raise RuntimeError(
                f"雷电实例 {idx} 启动异常（{reason}），{e}；请以管理员身份运行，或{_REPAIR_HINT}"
            ) from e

    async def _quit_zombie_instance(self, idx: str) -> None:
        """让只剩窗口的实例下线：先走 ``quit``，等不到就结束播放器进程。

        必须等到 list2 真的变成关机再返回：父类启动流程先查状态，只要那行还是
        「已启动」它就不 launch、直接当在线返回，自愈就成了空转。两手都没让它下线
        时抛错，而不是让后面报一句会误导的「重启后仍起不来」。
        """
        try:
            await ProcessRunner.run_process(
                self.emulator_path,
                "quit",
                "--index",
                idx,
                timeout=self.config.get("Info", "MaxWaitTime"),
                if_merge_std=True,
                breakaway=True,
            )
        except Exception as e:  # noqa: BLE001 - quit 失败还有下面的兜底
            logger.warning(f"雷电实例 {idx} quit 失败: {e}")

        deadline = time.monotonic() + _ZOMBIE_QUIT_TIMEOUT
        while time.monotonic() < deadline:
            if await self.getStatus(idx) == DeviceStatus.OFFLINE:
                return
            await asyncio.sleep(0.5)

        try:
            device = (await self.get_device_info(idx))[idx]
        except Exception as e:  # noqa: BLE001 - 取不到 pid 就没法再兜底
            raise RuntimeError(
                f"雷电实例 {idx} 对 quit 无响应，且取不到进程信息: {e}"
            ) from e
        if device.pid > 0:
            try:
                proc = psutil.Process(device.pid)
                proc.kill()
                await asyncio.to_thread(proc.wait, 10)
                logger.warning(
                    f"雷电实例 {idx} 对 quit 无响应，已结束播放器进程 {device.pid}"
                )
            except psutil.NoSuchProcess:
                pass
            except Exception as e:  # noqa: BLE001 - 下面按 list2 复核, 这里只记原因
                logger.warning(
                    f"结束雷电实例 {idx} 的播放器进程 {device.pid} 失败: {e}"
                )

        deadline = time.monotonic() + _ZOMBIE_QUIT_TIMEOUT
        while time.monotonic() < deadline:
            if await self.getStatus(idx) == DeviceStatus.OFFLINE:
                return
            await asyncio.sleep(0.5)
        raise RuntimeError(f"雷电实例 {idx} 的窗口关不掉，无法自愈，{_REPAIR_HINT}")

    async def vendor_launch_app(self, idx: str, package_name: str) -> object:
        """``ldconsole runapp``。

        与被否掉的 ``launch --packagename`` 不是同一条命令：那条只在冷启动模拟器时
        生效，这条是对**已经在跑**的实例启动应用。实测 0.06 秒到前台，而雷电镜像里
        没有 ``monkey``（返回码 127），所以这条在雷电上是主力之一。
        """
        return await ProcessRunner.run_process(
            self.emulator_path,
            "runapp",
            "--index",
            idx,
            "--packagename",
            package_name,
            timeout=self.config.get("Info", "MaxWaitTime"),
            if_merge_std=True,
            breakaway=True,
        )

    def read_instance_config(self, idx: str) -> dict | None:
        """只读地取一份 ``leidianN.config``。读不出返回 ``None``。"""
        config_path = self._get_instance_config_path(idx)
        if config_path is None:
            return None
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001 - 读不出就当未知, 不该让调用方炸
            logger.warning(f"读取雷电实例 {idx} 配置失败: {e}")
            return None
        return data if isinstance(data, dict) else None

    def get_boss_key(self, idx: str) -> BossKey:
        """取该实例的老板键。"""
        return read_boss_key(self.read_instance_config(idx))

    def _get_instance_vbox_path(self, idx: str) -> Path | None:
        idx_text = str(idx)
        if not idx_text.isdecimal():
            return None
        return self.emulator_path.parent / "vms" / f"leidian{idx_text}" / "leidian.vbox"

    def _read_instance_vbox(self, idx: str) -> str | None:
        """只读地取一份 ``leidian.vbox``。

        它只用来分辨「雷电默认值」和「用户保存的值」：28 键的实例配置里没有
        ``cpuCount``，但 ``.vbox`` 里写着 6 核——那 6 核是默认，不是用户设的。
        **我们从不写这个文件**，它每次启动都由实例配置重新生成。
        """
        vbox_path = self._get_instance_vbox_path(idx)
        if vbox_path is None:
            return None
        try:
            return vbox_path.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - 没启动过的实例根本没有这个文件
            return None

    async def read_instance_settings(self, idx: str) -> InstanceSettings:
        """读四项设置，带状态。

        读不出配置文件时整表报 ``unreadable``，而不是谎报「未设置」——
        那两种处境对用户来说要做的事完全不同。
        """
        config = await asyncio.to_thread(self.read_instance_config, idx)
        if config is None:
            return build_settings(None, None, readable=False)
        vbox_text = await asyncio.to_thread(self._read_instance_vbox, idx)
        return build_settings(config, vbox_text)

    async def write_instance_settings(
        self, idx: str, changes: dict, expected: dict | None = None
    ) -> dict[str, int]:
        """把改动写进实例配置，返回真正落盘的字段。

        **整个流程都在实例锁内**，这不是可选的。旧配置守卫的恢复逻辑是
        「取快照 → sleep 3 秒 → 写回」且全程在 ``_close_locked`` 里，
        中途不重查字典；不共用同一把锁的话就存在这个时序：
        关闭流程取到旧快照并进入等待 → 我们写入新值 → 关闭流程把旧快照写回，
        **用户刚保存的设置无声丢失**。原子写和备份都挡不住，只有共用锁能挡。

        锁的键是 ``(loop, ldconsole.exe 路径, 原生索引)``，所以这里传进来的
        ``idx`` 必须是原生索引，且构造本管理器的 ``Info.Path`` 必须正好是
        该安装的 ``ldconsole.exe``——门面负责保证这两条。
        """
        cleaned = validate_changes(changes)

        async with self._get_instance_lock(idx):
            config_path = self._get_instance_config_path(idx)
            if config_path is None:
                raise RuntimeError(f"雷电实例 {idx} 的索引无效，无法定位配置文件")

            # 锁内重读：表单打开到现在这段时间里，雷电自己的窗口可能整体写回过配置
            current_raw = await asyncio.to_thread(self.read_instance_config, idx)
            if current_raw is None:
                raise RuntimeError(f"雷电实例 {idx} 的配置文件读不出，拒绝写入")

            if expected:
                vbox_text = await asyncio.to_thread(self._read_instance_vbox, idx)
                current = build_settings(current_raw, vbox_text)
                conflicts = detect_conflicts(current, expected, list(cleaned))
                if conflicts:
                    raise SettingsConflictError(conflicts)

            merged = apply_changes(current_raw, cleaned)
            await asyncio.to_thread(self._replace_instance_config, config_path, merged)

            # 作废配置守卫的快照：用户显式保存的设置必须赢过「关闭后回滚到启动前」。
            # 在锁内 pop，关闭流程随后拿到锁时 get() 到 None，不会再写回旧值。
            _INSTANCE_CONFIG_SNAPSHOTS.pop(self._get_instance_key(idx), None)

        logger.info(f"已写入雷电实例 {idx} 的设置: {cleaned}")
        return cleaned

    async def _list_adb_serials(self, *, fresh: bool = False) -> list[str]:
        """``adb devices`` 的在线设备列表，带 5 秒缓存。

        状态轮询每几秒就调一次 :meth:`getInfo`，不缓存的话每轮都要起一次子进程。
        缓存到期前多台设备共用同一份结果，这正是 :func:`resolve_serial`
        排除其他实例候选时需要的一致视图。``fresh`` 越过缓存，给需要「现在」的探测用。
        """
        adb_path = self.get_adb_path()
        if adb_path is None:
            return []
        cache_key = str(adb_path)

        now = time.monotonic()
        cached = self._adb_cache.get(cache_key)
        if not fresh and cached is not None and now < cached[1]:
            return cached[0]

        try:
            result = await ProcessRunner.run_process(
                adb_path, "devices", timeout=_ADB_QUERY_TIMEOUT, if_merge_std=True
            )
            serials = parse_adb_devices(str(getattr(result, "stdout", "") or ""))
        except Exception as e:  # noqa: BLE001 - 查不到就退回公式, 不该让状态轮询挂掉
            logger.debug(f"执行 adb devices 失败: {e}")
            return []

        self._adb_cache[cache_key] = (serials, now + _ADB_CACHE_SECONDS)
        return serials

    async def _is_foreign_serial(self, serial: str) -> bool:
        """这个序列号背后连的是不是别家的模拟器。

        **为什么需要这一步。** ``emulator-NNNN`` 是 adb 的全局别名，谁占住回环上的
        ``5554 + 2N`` 端口就归谁。实测 MuMu 6 除了自己的 ``127.0.0.1:16384``，
        还会绑 ``127.0.0.1:5555``——正好是雷电 0 号的端口；而雷电绑的是
        ``0.0.0.0:5555``，Windows 上更具体的绑定赢，回环流量因此进了 MuMu。
        归属取决于两家的启动顺序，两个方向都实测到过，此时
        :func:`~.adb.resolve_serial` 照样会把它标成「核对通过」。

        判据用「认出别人」而不是「认出自己」，理由见 :data:`_FOREIGN_MARKER_PACKAGES`。
        查不动（没有 adb、命令失败、设备掉线）时一律返回 ``False`` **且不缓存**：
        拿不准就维持原样，不要凭一次查询失败把一台好设备判死。只有 ``pm path``
        真打出 ``package:`` 行才算「装着别家的包」。
        """
        now = time.monotonic()
        cached = self._ownership_cache.get(serial)
        if cached is not None and now < cached[1]:
            return cached[0]

        adb_path = self.get_adb_path()
        if adb_path is None:
            return False

        foreign = False
        for package in _FOREIGN_MARKER_PACKAGES:
            try:
                result = await ProcessRunner.run_process(
                    adb_path,
                    "-s",
                    serial,
                    "shell",
                    "pm",
                    "path",
                    package,
                    timeout=_ADB_QUERY_TIMEOUT,
                    if_merge_std=True,
                )
            except Exception as e:  # noqa: BLE001 - 查不动就不下结论, 见 docstring
                logger.debug(f"核对 {serial} 的归属失败: {e}")
                return False
            output = str(getattr(result, "stdout", "") or "")
            if is_package_present(output):
                foreign = True
                break
            if not is_package_missing(output):
                # 「device not found」「offline」这类：设备根本没连上，判不了归属，
                # 也不能把这个结论缓存起来——它可能几秒后就上线了
                logger.debug(f"核对 {serial} 的归属无结论: {output.strip()[:120]}")
                return False

        self._ownership_cache[serial] = (foreign, now + _OWNERSHIP_CACHE_SECONDS)
        if foreign:
            # 只在缓存未命中时说一次：getInfo 会被状态接口反复轮询，
            # 每轮都记一条会把日志刷满
            logger.warning(
                f"ADB 序列号 {serial} 实际连到的是别家模拟器，不能当作雷电实例使用。"
                f"MuMu 会占用回环 5555 端口，正好是雷电 0 号的端口；"
                f"请避免与 MuMu 同时运行，或改用 1 号及以后的实例"
            )
        return foreign

    async def getInfo(self, idx: str | None) -> dict[str, DeviceInfo]:
        """在父类结果之上，把 ADB 地址换成核对过的序列号。

        父类的做法是 ``get_adb_ports(vbox_pid)`` 查不到就回落公式。实测雷电 14 的
        ``Ld9BoxHeadless.exe`` 一个端口都不监听（端口归所有实例共用的 ``VBoxNetNAT``），
        那条查询**永远查不到**，等于一直在用没核过的公式值。这里改成拿
        ``adb devices`` 的真实结果核对，核不上就明确记一笔，而不是默默当成对的。
        """
        result = await super().getInfo(idx)
        if not result:
            return result

        serials = await self._list_adb_serials()
        if not serials:
            return result

        # 排除其他实例的候选时要看全量索引，不能只看本次查询的那一台。
        # 查全部时父类已经把全量给了，别再跑一遍 list2——这条路径是状态轮询走的
        if idx is None:
            all_indexes = list(result)
        else:
            try:
                all_indexes = list((await self.get_device_info(None)).keys())
            except Exception:  # noqa: BLE001 - 拿不到全量就不做认领, 只做核对
                all_indexes = list(result)

        resolved: dict[str, DeviceInfo] = {}
        for native_index, info in result.items():
            others = [i for i in all_indexes if str(i) != str(native_index)]
            outcome = resolve_serial(native_index, serials, others)
            address = outcome.serial

            # 只核对在线实例：关着的和正在启动的 adb 连不上，查了只会得到
            # 「device not found」；而且启动期间查出的结论会被缓存，等它真上线时
            # 反而把地址清空。
            if info.status == DeviceStatus.ONLINE and await self._is_foreign_serial(
                address
            ):
                # 宁可交白卷也不交错的：把别家的设备当成本实例发出去，后面每一条
                # adb 操作（连接、装包、启动应用）都会打到另一台模拟器上，
                # 而日志还显示「核对通过」。原因由 _is_foreign_serial 记一次。
                address = ""
            elif outcome.source == "recovered":
                logger.warning(
                    f"雷电实例 {native_index} 的 ADB 序列号与约定不符，"
                    f"按实际连接认领为 {address}"
                )

            resolved[native_index] = DeviceInfo(
                title=info.title, status=info.status, adb_address=address
            )
        return resolved

    async def read_stable_mode(self, idx: str) -> tuple[bool, list[str]]:
        """稳定模式是否已生效，以及还有哪几项不安全。"""
        config = await asyncio.to_thread(self.read_instance_config, idx)
        return self._stable_mode_of(config)

    @staticmethod
    def _stable_mode_of(config: dict | None) -> tuple[bool, list[str]]:
        if config is None:
            return False, [item.field for item in LDPLAYER_ITEMS]
        current = {item.key: _dig_flat(config, item.key) for item in LDPLAYER_ITEMS}
        return evaluate(LDPLAYER_ITEMS, current)

    async def read_instance_overview(
        self, idx: str
    ) -> tuple[InstanceSettings, bool, list[str]]:
        """四项设置和稳定模式一次读完：设备表每行都要这两样，分开读就是把同一个文件读两遍。"""
        config = await asyncio.to_thread(self.read_instance_config, idx)
        stable, unsafe = self._stable_mode_of(config)
        if config is None:
            return build_settings(None, None, readable=False), stable, unsafe
        vbox_text = await asyncio.to_thread(self._read_instance_vbox, idx)
        return build_settings(config, vbox_text), stable, unsafe

    async def apply_stable_mode(self, idx: str) -> list[str]:
        """把不安全的项写成安全值，返回实际改动的字段名。

        与四项设置共用同一把实例锁和同一套原子写——理由见
        :meth:`write_instance_settings`。
        """
        async with self._get_instance_lock(idx):
            config_path = self._get_instance_config_path(idx)
            if config_path is None:
                raise RuntimeError(f"雷电实例 {idx} 的索引无效，无法定位配置文件")

            current_raw = await asyncio.to_thread(self.read_instance_config, idx)
            if current_raw is None:
                raise RuntimeError(f"雷电实例 {idx} 的配置文件读不出，拒绝写入")

            current = {
                item.key: _dig_flat(current_raw, item.key) for item in LDPLAYER_ITEMS
            }
            writes = safe_writes(LDPLAYER_ITEMS, current)
            if not writes:
                return []

            merged = dict(current_raw)
            for key, value in writes.items():
                # 雷电这几项在配置里是真正的布尔，不是字符串
                merged[key] = value == "true"
            await asyncio.to_thread(self._replace_instance_config, config_path, merged)
            _INSTANCE_CONFIG_SNAPSHOTS.pop(self._get_instance_key(idx), None)

        changed = [item.field for item in LDPLAYER_ITEMS if item.key in writes]
        logger.info(f"雷电实例 {idx} 已进入稳定模式，改动: {changed}")
        return changed

    def _discard_config_backup(self, idx: str) -> None:
        """实例没了，它的设置备份也就没有意义了。

        不清的话 ``vms\\config`` 里会慢慢攒下一堆 ``leidianN.config.bak`` 孤儿，
        而且下次这个索引被复用时，留着的是上一台实例的备份，更容易误导人。
        """
        config_path = self._get_instance_config_path(idx)
        if config_path is None:
            return
        for suffix in (".bak", ".tmp"):
            leftover = config_path.with_suffix(config_path.suffix + suffix)
            try:
                leftover.unlink(missing_ok=True)
            except OSError as e:  # noqa: PERF203 - 清不掉只是留个垃圾, 不该让删除算失败
                logger.warning(f"清理 {leftover.name} 失败: {e}")

    @staticmethod
    def _replace_instance_config(config_path: Path, data: dict) -> None:
        """原子替换 + 留一份 ``.bak``。

        先写同目录临时文件再 ``os.replace``——中途断电也不会留下半份 JSON
        让雷电读到。备份只保留最近一次。
        """
        payload = json.dumps(data, ensure_ascii=False, indent=4)
        temp_path = config_path.with_suffix(config_path.suffix + ".tmp")
        temp_path.write_text(payload, encoding="utf-8")

        if config_path.exists():
            backup_path = config_path.with_suffix(config_path.suffix + ".bak")
            shutil.copy2(config_path, backup_path)

        os.replace(temp_path, config_path)

    def resolve_device(self, idx: str) -> DeviceRef | None:
        """本管理器只管一条安装，索引就是原生索引。"""
        return DeviceRef(
            emulator_type="ldplayer",
            manager_path=str(self.emulator_path),
            native_index=str(idx),
        )

    async def create_instance(self, name: str | None = None) -> str:
        """新建一个实例，返回它的原生索引。

        **不能看返回码。** 实测 ``ldconsole add`` 成功时返回 4，
        所以判据是「跑完之后 list2 里多出来的那个索引」。
        """
        before = set((await self.get_device_info(None)).keys())

        await ProcessRunner.run_process(
            self.emulator_path,
            "add",
            *(["--name", name] if name else []),
            timeout=self.config.get("Info", "MaxWaitTime"),
            if_merge_std=True,
            breakaway=True,
        )

        for _ in range(_INSTANCE_MUTATION_RETRIES):
            await asyncio.sleep(_INSTANCE_MUTATION_DELAY_SECONDS)
            after = set((await self.get_device_info(None)).keys())
            created = after - before
            if created:
                # 一次只会新建一个；真出现多个就取最小的那个，行为可预期
                native_index = min(
                    created, key=lambda x: int(x) if x.isdecimal() else 0
                )
                logger.info(f"已新建雷电实例 {native_index}")
                return native_index

        raise RuntimeError("新建雷电实例失败：list2 里没有出现新的实例")

    async def delete_instance(self, native_index: str) -> None:
        """删除一个实例。

        两个坑都在这里兜住：

        - 实例在线时不删——先让调用方关掉，避免删一台正在跑任务的设备
        - **雷电会在删除后自动重建一个空实例**（默认名「雷电模拟器-N」，配置只有 8 个键），
          所以删完必须复核 ``list2``，需要时再删一次
        """
        status = await self.getStatus(native_index)
        if status not in (DeviceStatus.OFFLINE, DeviceStatus.NOT_FOUND):
            raise RuntimeError(f"雷电实例 {native_index} 未关闭，无法删除")

        for attempt in range(_INSTANCE_MUTATION_RETRIES):
            await ProcessRunner.run_process(
                self.emulator_path,
                "remove",
                "--index",
                native_index,
                timeout=self.config.get("Info", "MaxWaitTime"),
                if_merge_std=True,
                breakaway=True,
            )
            await asyncio.sleep(_INSTANCE_MUTATION_DELAY_SECONDS)
            remaining = set((await self.get_device_info(None)).keys())
            if native_index not in remaining:
                self._discard_config_backup(native_index)
                logger.info(f"已删除雷电实例 {native_index}")
                return
            logger.warning(
                f"雷电实例 {native_index} 删除后仍在列表中"
                f"（雷电会自动重建空实例），第 {attempt + 1} 次复核后重试"
            )

        raise RuntimeError(f"删除雷电实例 {native_index} 失败：它仍然在列表中")

    async def prepare_launch(self, idx: str) -> None:
        """启动前按旧版全局开关应用「大雷主人模式」。

        ``globalsetting --cleanmode`` 是**整个安装**的全局开关，宿主只在 VM 冷启动时把它
        作为 ``phone.cleanmode`` 推进客户机，所以放在启动前、每次都设：开着设 1、关着设 0，
        和旧配置的处理口径一致。已经在跑的其他实例要到它们下次冷启动才会跟着变。
        设不上只记警告，不拦启动。
        """
        enabled = is_master_mode_enabled()
        try:
            result = await ProcessRunner.run_process(
                self.emulator_path,
                *ldplayer_clean_mode_args(enabled),
                timeout=self.config.get("Info", "MaxWaitTime"),
                if_merge_std=True,
                breakaway=True,
            )
        except Exception as e:  # noqa: BLE001 - 见 docstring
            logger.warning(f"设置雷电「大雷主人模式」失败，实例 {idx} 照常启动: {e}")
            return
        if result.returncode != 0:
            logger.warning(
                f"设置雷电「大雷主人模式」返回 {result.returncode}，实例 {idx} 照常启动: "
                f"{result.stdout.strip()}"
            )
            return
        logger.info(
            f"雷电「大雷主人模式」已{'开启' if enabled else '关闭'}，实例 {idx} 冷启动后生效"
        )

    async def _block_ads_via_adb(self, idx: str) -> None:
        """保留父类兼容入口，但不禁用游戏中心。

        模式由 :meth:`prepare_launch` 统一处理，整包禁用会让「打开游戏中心」失效。
        """
        return None

    async def setVisible(self, idx: str, is_visible: bool) -> DeviceStatus:
        """用**该实例自己的**老板键切换窗口可见性。

        与父类的差别只在老板键从哪来：父类读配置级的 ``Info.BossKey``，
        这里读 ``leidianN.config`` 的 ``hotkeySettings.bossKey``。
        认不出时抛 :class:`BossKeyUnavailableError`，**不回落任何猜测组合**。
        """
        if not IS_WINDOWS:
            raise RuntimeError("切换模拟器窗口可见性仅支持 Windows 平台")

        status = await self.getStatus(idx)
        if status != DeviceStatus.ONLINE:
            logger.warning(f"设备{idx}未在线，当前状态码: {status}")
            return status

        boss_key = self.get_boss_key(idx)
        hotkey = boss_key.hotkey
        if hotkey is None:
            raise BossKeyUnavailableError(idx, boss_key.reason)
        if boss_key.reason == "default":
            logger.info(f"雷电实例 {idx} 未自定义老板键，使用雷电默认 {hotkey}")

        device = (await self.get_device_info(idx))[idx]

        deadline = time.monotonic() + self.config.get("Info", "MaxWaitTime")
        while time.monotonic() < deadline:
            if win32gui.IsWindowVisible(device.top_hwnd) == is_visible:
                return status
            try:
                keyboard.press_and_release(hotkey)
            except Exception as e:  # noqa: BLE001 - 与父类一致, 单次发送失败不终止重试
                logger.error(f"发送老板键失败: {e}")
            await asyncio.sleep(0.5)

        raise RuntimeError(f"隐藏设备{idx}窗口超时")


async def build_manager(
    manager_exe: str, max_wait_time: int, force_kill_on_close: bool = False
) -> LDPlayer14Manager:
    """为一条雷电安装合成配置并构造管理器。

    ``manager_exe`` 必须是该安装的 ``ldconsole.exe``——实例锁的键靠它。
    """
    config = EmulatorConfig()
    await config.load(
        {
            "Info": {
                "Name": Path(manager_exe).parent.name,
                "Type": "ldplayer",
                "Path": str(manager_exe),
                "MaxWaitTime": max_wait_time,
                "ForceKillOnClose": force_kill_on_close,
            }
        }
    )
    return LDPlayer14Manager(config)
