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

"""Emulator 2.0 的设备管理器门面。

对外仍然是一个 ``DeviceBase``，所以脚本适配器那套 ``open`` / ``close`` / ``setVisible``
调用一行都不用改；对内把设备号翻译成「哪条安装的第几个原生实例」，转发给复用旧实现的
后端管理器。

两条不能破的口径：

- **对外的键一律是设备号**（``getInfo`` / ``get_device_info`` / ``list_devices`` 的字典键），
  因为脚本存的 ``EmulatorIndex`` 就是设备号。
- **``LDPlayerDevice.idx`` 保持原生索引**。调用方拿它算 ADB 端口
  （``emulator-{5554 + 2 * idx}``）与雷电专用连接参数，填设备号会连错实例。

设备号解析不出、或对应实例这次没枚举到时，一律报「不可用」，
**绝不回退到第一台或任何其他设备**。
"""

import asyncio
from pathlib import Path

from app.models.config import EmulatorConfig
from app.models.emulator import DeviceBase, DeviceInfo, DeviceRef, DeviceStatus
from app.utils import get_logger

from .applaunch import AppLaunchResult
from .guard import drift, load_baselines
from .ldplayer14 import LDPlayer14Manager
from .ldplayer14 import build_manager as build_ldplayer_manager
from .mumu6 import MuMu6Manager
from .mumu6 import build_manager as build_mumu_manager
from .settings import InstanceSettings
from .slots import PathRecord, SlotRecord, SlotTable

#: 一条安装的后端管理器。两家各自继承旧实现, 对门面暴露同一组方法。
Backend = LDPlayer14Manager | MuMu6Manager

#: 类型 -> 构造函数。加一家模拟器只要在这里加一行。
_BACKEND_BUILDERS = {
    "ldplayer": build_ldplayer_manager,
    "mumu": build_mumu_manager,
}

logger = get_logger("Emulator2 设备管理")


class DeviceUnavailableError(RuntimeError):
    """设备号解析不到可用设备。

    只在明确知道「这个号没有对应设备」时抛，调用方不得据此改用别的设备。
    """

    def __init__(self, slot: str, reason: str) -> None:
        super().__init__(f"设备 #{slot} 不可用: {reason}")
        self.slot = slot
        self.reason = reason


def load_paths(raw: str | None) -> list[PathRecord]:
    """从配置里的 JSON 串还原纳管的安装列表。内容不可用时按空列表处理。"""
    import json

    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    records = []
    for item in data:
        if isinstance(item, dict) and item.get("installPath"):
            records.append(PathRecord.from_dict(item))
    return records


def dump_paths(records: list[PathRecord]) -> str:
    import json

    return json.dumps([record.to_dict() for record in records], ensure_ascii=False)


class Emulator2Manager(DeviceBase):
    """纳管多条模拟器安装的设备管理器。"""

    def __init__(self, config: EmulatorConfig) -> None:
        if config.get("Info", "Type") != "emulator2":
            raise ValueError("配置的模拟器类型不是 emulator2")

        self.config = config
        self.paths: list[PathRecord] = load_paths(config.get("Info", "Paths"))
        self.slots: SlotTable = SlotTable.from_json(config.get("Info", "Slots"))
        #: 配置守卫的基准：{设备号: {字段: 值}}。只读，写由服务层负责。
        self.baselines = load_baselines(config.get("Info", "Baselines"))

        self._managers: dict[str, Backend] = {}
        self._manager_lock = asyncio.Lock()
        #: ``get_adb_path()`` 签名里没有索引, 多安装时天然有歧义。
        #: 记住最近一次解析命中的安装, 只有一条安装时直接用那条, 否则回退系统 adb。
        self._last_path_id: str | None = None

    # ---- 解析 -----------------------------------------------------------

    def path_of(self, path_id: str) -> PathRecord | None:
        for record in self.paths:
            if record.path_id == path_id:
                return record
        return None

    def resolve_slot(self, slot: str) -> tuple[PathRecord, SlotRecord]:
        """设备号 → （安装, 槽位记录）。解析不出直接抛，不做任何回退。"""
        record = self.slots.resolve(str(slot))
        if record is None:
            raise DeviceUnavailableError(str(slot), "设备号不存在")
        if record.state == "tombstone":
            raise DeviceUnavailableError(str(slot), "该设备所属的模拟器已被移除")
        path = self.path_of(record.path_id)
        if path is None:
            raise DeviceUnavailableError(str(slot), "该设备所属的模拟器已被移除")
        self._last_path_id = path.path_id
        return path, record

    def resolve_device(self, idx: str) -> DeviceRef | None:
        """覆盖默认实现：持久化的类型是 ``emulator2``，不是设备的真实类型。

        脚本适配器靠这个方法决定要不要启用模拟器专用能力，所以必须回报真实类型
        与该安装的管理器路径，而不是本配置的类型和空路径。
        """
        try:
            path, record = self.resolve_slot(idx)
        except DeviceUnavailableError:
            return None
        manager_exe = self._manager_exe(path)
        if manager_exe is None:
            return None
        return DeviceRef(
            emulator_type=path.type,
            manager_path=str(manager_exe),
            native_index=record.native_index,
        )

    @staticmethod
    def _manager_exe(path: PathRecord) -> Path | None:
        """安装目录 → 主管理器程序。实例锁的键就是它，口径不能变。"""
        from .detect import resolve_manager_exe

        return resolve_manager_exe(path.install_path, path.type)

    async def manager_for(self, path: PathRecord) -> Backend:
        """取（必要时构造）某条安装的后端管理器。按安装缓存，避免重复构造。"""
        async with self._manager_lock:
            cached = self._managers.get(path.path_id)
            if cached is not None:
                return cached
            manager_exe = self._manager_exe(path)
            if manager_exe is None:
                raise DeviceUnavailableError(
                    "-", f"找不到 {path.alias or path.install_path} 的模拟器程序"
                )
            builder = _BACKEND_BUILDERS.get(path.type)
            if builder is None:
                raise DeviceUnavailableError("-", f"暂不支持的模拟器类型: {path.type}")
            manager = await builder(
                str(manager_exe),
                max_wait_time=int(self.config.get("Info", "MaxWaitTime")),
                force_kill_on_close=bool(self.config.get("Info", "ForceKillOnClose")),
            )
            self._managers[path.path_id] = manager
            return manager

    async def _dispatch(self, slot: str) -> tuple[Backend, str]:
        """设备号 → （后端管理器, 原生索引）。"""
        path, record = self.resolve_slot(slot)
        manager = await self.manager_for(path)
        return manager, record.native_index

    # ---- DeviceBase ------------------------------------------------------

    async def enforce_baseline(self, slot: str, when: str) -> list[str]:
        """按基准核验一台设备的设置，对不上就写回去。

        启动前和关闭后各调一次：模拟器可能在这两个时刻之外改掉用户的设置
        （升级、崩溃恢复、在多开器里手滑，某些版本关机时还会按内存态整体写回）。
        没开守卫、或这台没有基准时什么都不做。
        """
        if not self.config.get("Info", "ConfigGuard"):
            return []
        baseline = self.baselines.get(str(slot))
        if not baseline:
            return []

        try:
            manager, native_index = await self._dispatch(slot)
            current = await manager.read_instance_settings(native_index)
            changes = drift(baseline, current)
            if not changes:
                return []
            # 不传 expected：这里就是要以基准覆盖现状，冲突比对反而会拦住我们
            await manager.write_instance_settings(native_index, changes)
        except Exception as e:  # noqa: BLE001 - 守卫失败不该拦住启动或关闭
            logger.warning(f"设备 #{slot} {when}核验配置失败: {e}")
            return []

        logger.info(f"设备 #{slot} {when}发现配置偏离基准，已还原: {changes}")
        return list(changes)

    async def open(self, idx: str, package_name: str = "") -> DeviceInfo:
        """启动设备；``package_name`` 非空时在设备就绪后把该应用也拉起来。

        应用那一步由后端的 :class:`~.applaunch.AppLaunchMixin` 走纯 adb 完成，
        **模拟器本来就开着时同样生效**——两家原生的带包启动参数在那种情况下会被
        整条吞掉，见 :mod:`.applaunch`。拉不起来只记警告，不影响本方法的返回。
        """
        manager, native_index = await self._dispatch(idx)

        # 守卫先于稳定模式：两者管的字段不重叠，但都要在实例真正起来之前写完
        await self.enforce_baseline(idx, "启动前")

        # 稳定模式是配置级开关，启动前顺带确保一次：这样在模拟器自己那边新建的实例，
        # 或者用户后来改回去的项，都会在真正跑任务之前被压住，而不是只在点开关的
        # 那一刻生效。已经安全时 apply 不写任何键，代价只是一次读。
        if self.config.get("Info", "StableMode"):
            try:
                changed = await manager.apply_stable_mode(native_index)
                if changed:
                    logger.info(f"设备 #{idx} 启动前已进入稳定模式，改动: {changed}")
            except Exception as e:  # noqa: BLE001 - 压不住不该拦住启动
                logger.warning(f"设备 #{idx} 应用稳定模式失败，继续启动: {e}")

        return await manager.open(native_index, package_name)

    async def launch_app(self, idx: str, package_name: str) -> AppLaunchResult:
        """在**已经在线**的设备上把应用拉起来，不重开模拟器。

        给「模拟器本来就开着，只是应用没起来」准备的入口，:meth:`open` 内部走的
        也是同一条路。拉不起来返回 ``ok=False``，不抛异常。
        """
        manager, native_index = await self._dispatch(idx)
        return await manager.launch_app(native_index, package_name)

    async def open_store(self, idx: str) -> AppLaunchResult:
        """打开设备所属模拟器自带的游戏中心，不重开模拟器。

        包名由后端自己决定（雷电 ``com.android.flysilkworm``、MuMu ``com.mumu.store``），
        这里只负责按设备号找到后端。拉不起来返回 ``ok=False``，不抛异常。
        """
        manager, native_index = await self._dispatch(idx)
        return await manager.open_store(native_index)

    async def close(self, idx: str) -> DeviceStatus:
        manager, native_index = await self._dispatch(idx)
        status = await manager.close(native_index)

        # 关闭之后再核一次：雷电旧配置守卫的还原也在 close 里做，
        # 放在它后面才能保证最终以用户在 MAS 里定的值为准。
        await self.enforce_baseline(idx, "关闭后")
        return status

    async def getStatus(self, idx: str) -> DeviceStatus:
        try:
            manager, native_index = await self._dispatch(idx)
        except DeviceUnavailableError as e:
            logger.warning(str(e))
            return DeviceStatus.NOT_FOUND
        return await manager.getStatus(native_index)

    async def setVisible(self, idx: str, is_visible: bool) -> DeviceStatus:
        manager, native_index = await self._dispatch(idx)
        return await manager.setVisible(native_index, is_visible)

    def get_adb_path(self) -> Path | None:
        candidates = self.paths
        if self._last_path_id is not None:
            hit = self.path_of(self._last_path_id)
            if hit is not None:
                candidates = [hit]
        if len(candidates) != 1:
            # 多条安装且还没解析过任何设备号——回退系统 adb 比猜一条安全
            return None
        manager_exe = self._manager_exe(candidates[0])
        if manager_exe is None:
            return None
        adb_path = manager_exe.parent / "adb.exe"
        return adb_path if adb_path.exists() else None

    async def getInfo(self, idx: str | None) -> dict[str, DeviceInfo]:
        """单个设备号或全部设备。**返回字典的键是设备号。**"""
        if idx is not None:
            manager, native_index = await self._dispatch(idx)
            info = await manager.getInfo(native_index)
            return {str(idx): info[native_index]}

        merged: dict[str, DeviceInfo] = {}
        for path in self.paths:
            try:
                manager = await self.manager_for(path)
                native_info = await manager.getInfo(None)
            except Exception as e:  # noqa: BLE001 - 一条安装枚举失败不影响其余
                logger.warning(f"枚举 {path.alias or path.install_path} 失败: {e}")
                continue
            for record in self.slots.records:
                if record.path_id != path.path_id or record.state != "active":
                    continue
                info = native_info.get(record.native_index)
                if info is not None:
                    merged[record.slot] = info
        return merged

    async def get_device_info(self, idx: str | None) -> dict:
        """转发雷电专属的 ``get_device_info``。

        **键是设备号，而条目里的 ``idx`` 保持原生索引**——调用方拿它算 ADB 端口
        和雷电专用连接参数，换成设备号会连错实例。
        """
        if idx is not None:
            path, record = self.resolve_slot(str(idx))
            if path.type != "ldplayer":
                # 同下：这个方法是雷电专属的，别的家返回的东西形状都不一样
                return {}
            manager = await self.manager_for(path)
            native = await manager.get_device_info(record.native_index)
            return {str(idx): native[record.native_index]}

        merged: dict = {}
        for path in self.paths:
            if path.type != "ldplayer":
                # get_device_info 是雷电专属的（调用方拿 idx / pid 算 ADB 参数）。
                # MuMu 的同名方法返回一段字符串，混进来只会得到假条目。
                continue
            try:
                manager = await self.manager_for(path)
                native = await manager.get_device_info(None)
            except Exception as e:  # noqa: BLE001 - 同上
                logger.warning(f"枚举 {path.alias or path.install_path} 失败: {e}")
                continue
            for record in self.slots.records:
                if record.path_id != path.path_id or record.state != "active":
                    continue
                device = native.get(record.native_index)
                if device is not None:
                    merged[record.slot] = device
        return merged

    # ---- 四项设置 --------------------------------------------------------

    async def read_settings(self, slot: str) -> InstanceSettings:
        """读一台设备的四项设置。"""
        manager, native_index = await self._dispatch(slot)
        return await manager.read_instance_settings(native_index)

    async def write_settings(
        self, slot: str, changes: dict, expected: dict | None = None
    ) -> dict[str, int]:
        """写一台设备的设置。

        ``expected`` 是表单打开时看到的值；对不上就抛
        :class:`~.settings.SettingsConflictError`，不盲目覆盖。
        批量设置不传它——那本来就是「全部设成这一组值」的明确覆盖语义。
        """
        manager, native_index = await self._dispatch(slot)
        return await manager.write_instance_settings(native_index, changes, expected)

    async def read_stable_mode(self, slot: str) -> tuple[bool, list[str]]:
        """稳定模式是否已生效，以及还有哪几项不安全。"""
        manager, native_index = await self._dispatch(slot)
        return await manager.read_stable_mode(native_index)

    async def read_overview(
        self, slot: str
    ) -> tuple[InstanceSettings, bool, list[str]]:
        """四项设置 + 稳定模式，一次读完。设备表每行都要，分开读等于把同一份配置读两遍。"""
        manager, native_index = await self._dispatch(slot)
        return await manager.read_instance_overview(native_index)

    async def apply_stable_mode(self, slot: str) -> list[str]:
        """把这台设备切进稳定模式，返回实际改动的字段名。"""
        manager, native_index = await self._dispatch(slot)
        return await manager.apply_stable_mode(native_index)

    async def list_devices(self) -> dict[str, str]:
        """设备号 → 显示名。给脚本编辑页的实例下拉用。

        只要名字，所以走各家的轻量列表（一条 ``list2`` / ``info``），不走 ``getInfo``——
        那条还要核对 adb 序列号、逐台查归属，下拉框等不起。显示名带上设备号：
        脚本绑的是设备号，实例名（雷电默认就叫 0、1、2）单独看不出对应哪台。
        """
        merged: dict[str, str] = {}
        for path in self.paths:
            try:
                manager = await self.manager_for(path)
                titles = await manager.list_devices()
            except Exception as e:  # noqa: BLE001 - 一条安装枚举失败不影响其余
                logger.warning(f"枚举 {path.alias or path.install_path} 失败: {e}")
                continue
            for record in self.slots.records:
                if record.path_id != path.path_id or record.state != "active":
                    continue
                title = titles.get(record.native_index)
                if title is not None:
                    merged[record.slot] = f"#{record.slot} {title}"
        return merged

    # ---- 枚举与槽位同步 ---------------------------------------------------

    async def enumerate_native(self, path: PathRecord) -> list[str] | None:
        """枚举一条安装当前的原生实例索引。失败返回 ``None``。

        ``None`` 与空列表是两回事：前者是「这次没问到」，后者是「确实一个实例都没有」。
        槽位表只能靠前者之外的结果推进，否则一次枚举失败会被当成实例被删。
        """
        try:
            manager = await self.manager_for(path)
            # 两家的 list_devices 都返回 {原生索引: 名称}，一条命令就够；
            # get_device_info 是雷电专属的，MuMu 那边返回的是一段字符串，不能用。
            devices = await manager.list_devices()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"枚举 {path.alias or path.install_path} 失败: {e}")
            return None
        return list(devices.keys())
