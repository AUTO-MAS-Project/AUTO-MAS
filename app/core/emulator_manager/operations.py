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

"""Emulator 2.0 的应用编排：配置持久化、脚本绑定策略与删除影响分析。

设备发现、设备号解析、启停和设置能力由 ``app.utils.emulator2`` 提供；
本模块装配当前配置并保存变更，设备层无需读取各专项的脚本配置。

版本探测只在**添加路径时**做一次并持久化。``get_status()`` 每次轮询都会重建管理器，
把探测放进构造函数会变成每轮一次子进程。
"""

import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import ConfigEntry
from app.core import Config
from app.utils import emulator2 as _utils_emulator2
from app.utils import get_logger

logger = get_logger("Emulator2 服务")


@dataclass
class SearchItem:
    """一条搜索结果。``reason`` 是枚举, 文案由前端按枚举取。"""

    type: str
    version: str
    install_path: str
    alias: str
    supported: bool
    reason: str
    instance_count: int | None = None

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "version": self.version,
            "installPath": self.install_path,
            "alias": self.alias,
            "supported": self.supported,
            "reason": self.reason,
            "instanceCount": self.instance_count,
        }


@dataclass
class AffectedScript:
    """一个绑定了某设备号的脚本。"""

    script_id: str
    name: str
    slot: str
    running: bool

    def to_dict(self) -> dict:
        return {
            "scriptId": self.script_id,
            "name": self.name,
            "slot": self.slot,
            "running": self.running,
        }


#: 「打开游戏中心」各种结局对应的一句话，直接给界面用。键是 ``AppLaunchResult.reason``。
_STORE_OPEN_MESSAGES: dict[str, str] = {
    "launched": "游戏中心已打开",
    "already-running": "游戏中心已在前台",
    "resumed": "游戏中心已切回前台",
    "no-store": "这个模拟器没有游戏中心",
    "not-installed": "这台模拟器里没有游戏中心",
    "no-adb": "设备没有可用的 ADB 地址，无法打开游戏中心",
    "boot-timeout": "系统还没启动完成，稍后再试",
    "launch-timeout": "游戏中心没有进入前台，可能已被禁用",
}


#: 同一条安装下并发读设置的上限。雷电是读文件，MuMu 每台是一个子进程；
#: 全串行时十台设备就是十个来回，全放开又会同时拉起一堆 MuMuManager.exe。
_OVERVIEW_CONCURRENCY = 4


# ---- 四项设置 -------------------------------------------------------------


# ---- 实例选项 -------------------------------------------------------------


class EmulatorOperations:
    def readable_error(self, error: BaseException) -> str:
        """把异常翻译成能给用户看的一句话。

        界面上不该出现 ``ValueError: badly formed hexadecimal UUID string`` 这种东西。
        认得出的失败给中文原因；认不出的才退回类名加消息，好歹还能报 issue。
        """
        if isinstance(error, _utils_emulator2.facade.DeviceUnavailableError):
            return str(error)
        if isinstance(error, _utils_emulator2.settings.SettingsConflictError):
            return "配置在编辑期间被改动，请刷新后重试"
        if isinstance(error, ValueError):
            return str(error)

        # 魔改 AVD 这几类的消息本来就是写给用户的中文（含原因与该怎么办），不带类名前缀
        if isinstance(
            error,
            (
                _utils_emulator2.avd.precheck.PrecheckFailed,
                _utils_emulator2.avd.host.AdbPortConflict,
            ),
        ):
            return str(error)
        if isinstance(error, KeyError):
            return f"找不到对象: {error.args[0] if error.args else error}"
        if type(error) is RuntimeError:
            # 我们自己抛的 RuntimeError 消息本来就是写给用户看的中文
            # （「实例未关闭，无法删除」之类），不该再被套上类名前缀
            return str(error)
        return f"{type(error).__name__}: {error}"

    def _emulator_config(self, emulator_id: str):
        return Config.EmulatorConfig[uuid.UUID(emulator_id)]

    async def _save(
        self,
        emulator_id: str,
        paths: list[_utils_emulator2.slots.PathRecord],
        slots: _utils_emulator2.slots.SlotTable,
    ) -> None:
        await Config.update_emulator(
            emulator_id,
            {
                "Info": {
                    "Paths": _utils_emulator2.facade.dump_paths(paths),
                    "Slots": slots.to_json(),
                }
            },
        )

    async def _save_baselines(
        self, emulator_id: str, baselines: dict[str, dict[str, int]]
    ) -> None:
        await Config.update_emulator(
            emulator_id,
            {"Info": {"Baselines": _utils_emulator2.guard.dump_baselines(baselines)}},
        )

    async def capture_baselines(self, emulator_id: str) -> dict:
        """把当前所有设备的设置记成守卫基准。开启守卫时调一次。

        只记用户显式设过的字段——见 ``app.utils.common.emulator2.guard.capture``。
        """
        manager = await self.build_manager(emulator_id)

        baselines: dict[str, dict[str, int]] = {}
        for record in manager.slots.records:
            if record.state != "active":
                continue
            try:
                settings = await manager.read_settings(record.slot)
            except Exception as e:  # noqa: BLE001 - 单台读不出不该拖垮整批
                logger.warning(f"读取设备 #{record.slot} 设置失败，跳过基准: {e}")
                continue
            fields = _utils_emulator2.guard.capture(settings)
            if fields:
                baselines[record.slot] = fields

        await self._save_baselines(emulator_id, baselines)
        return {
            "slots": sorted(baselines, key=lambda x: int(x) if x.isdecimal() else 0),
            "count": len(baselines),
        }

    async def _record_baseline(
        self, emulator_id: str, slot: str, applied: dict
    ) -> None:
        """用户刚保存的设置就是新的基准——否则守卫会把他刚改的值又还原回去。"""
        manager = await self.build_manager(emulator_id)
        if not manager.config.Info.ConfigGuard:
            return
        baselines = dict(manager.baselines)
        merged = dict(baselines.get(str(slot), {}))
        merged.update({k: int(v) for k, v in applied.items()})
        baselines[str(slot)] = merged
        await self._save_baselines(emulator_id, baselines)

    async def build_manager(
        self, emulator_id: str
    ) -> _utils_emulator2.facade.Emulator2Manager:
        """按配置 id 构造门面。"""
        return _utils_emulator2.facade.Emulator2Manager(
            self._emulator_config(emulator_id), runtime_policy=self.runtime_policy
        )

    def find_affected_scripts(
        self, emulator_id: str, slots: list[str]
    ) -> list[AffectedScript]:
        """反查哪些脚本绑在这些设备号上。

        专项声明持久绑定，不能用运行期资源代替（General 禁用时仍保留引用）。
        运行中判据继续用 ``is_locked``。
        """
        wanted = {str(slot) for slot in slots}
        affected: list[AffectedScript] = []
        for script_id, script in Config.ScriptConfig.items():
            binding = Config.get_script_emulator_binding(script)
            if binding is None:
                continue
            bound_id, bound_index = binding
            if str(bound_id) != str(emulator_id) or str(bound_index) not in wanted:
                continue
            affected.append(
                AffectedScript(
                    script_id=str(script_id),
                    name=str(script.Info.Name),
                    slot=str(bound_index),
                    running=script.is_locked,
                )
            )
        return affected

    def script_supports_mod_avd(self, script: ConfigEntry) -> bool:
        """读取专项声明的魔改 AVD 支持能力。"""
        return Config.script_supports_mod_avd(script)

    async def is_mod_avd_device(self, emulator_id: Any, index: Any) -> bool:
        """这个设备号是不是魔改 AVD 实例。不是 Emulator 2.0 配置、设备号无效都返回 ``False``。"""
        if str(emulator_id) in ("", "-", "None") or str(index) in ("", "-", "None"):
            return False
        try:
            manager = await self.build_manager(str(emulator_id))
            device_ref = manager.resolve_device(str(index))
        except Exception:  # noqa: BLE001 - 不是 Emulator 2.0 配置或设备号对不上
            return False
        return device_ref is not None and device_ref.emulator_type == "avd"

    async def mod_avd_binding_error(self, script_id: str, patch: dict) -> str | None:
        """脚本保存时：不支持魔改 AVD 的脚本（目前只有 MaaFW 和 MAA 支持）要绑到魔改 AVD 设备，返回拒绝原因；否则 ``None``。

        按专项声明解析本次补丁，只在带了设备号时检查；只改设备号时合并当前模拟器配置。
        只改模拟器配置（没带设备号）不检查，避免分步保存时用旧号误拦新配置。
        """
        try:
            script = Config.ScriptConfig[uuid.UUID(str(script_id))]
        except Exception:  # noqa: BLE001 - 找不到脚本交给后面的保存逻辑报
            return None
        binding = Config.get_script_emulator_binding(script, patch=patch)
        if binding is None:
            return None
        emulator_id, index = binding
        if await self.is_mod_avd_device(
            emulator_id, index
        ) and not self.script_supports_mod_avd(script):
            return _utils_emulator2.avd.constants.MOD_AVD_UNSUPPORTED_MESSAGE
        return None

    async def search(self, emulator_id: str | None = None) -> list[SearchItem]:
        """自动搜索本机模拟器，并逐条判定能否加入 Emulator 2.0。

        不支持的**不隐藏**——用户装了雷电 9 却搜不到，会以为搜索坏了。
        """
        import asyncio

        from app.utils import emulator as _utils_emulator

        found = await asyncio.to_thread(_utils_emulator.tools.search_all_emulators)

        added: set[str] = set()
        if emulator_id is not None:
            try:
                manager = await self.build_manager(emulator_id)
                added = {record.path_id for record in manager.paths}
            except Exception as e:  # noqa: BLE001 - 拿不到已添加列表不该让搜索整个失败
                logger.warning(f"读取已添加的模拟器路径失败: {e}")

        items: list[SearchItem] = []
        for entry in found:
            manager_exe = str(entry.get("path", ""))
            emulator_type = str(entry.get("type", ""))
            result = await _utils_emulator2.detect.probe_install_path(
                manager_exe, emulator_type
            )
            install_path = result.install_path or manager_exe
            reason = result.reason
            supported = result.supported
            if supported and _utils_emulator2.slots.make_path_id(install_path) in added:
                supported, reason = False, "already_added"
            items.append(
                SearchItem(
                    type=result.type or emulator_type,
                    version=result.version,
                    install_path=install_path,
                    alias=self._default_alias(install_path),
                    supported=supported,
                    reason=reason,
                )
            )
        return items

    def _default_alias(self, install_path: str) -> str:
        name = Path(install_path).name
        return name or install_path

    async def add_path(
        self, emulator_id: str, install_path: str, alias: str | None = None
    ) -> dict:
        """添加一条模拟器路径：探测版本 → 落库 → 为它的实例分配设备号。"""
        result: _utils_emulator2.detect.DetectResult = (
            await _utils_emulator2.detect.probe_install_path(install_path)
        )
        if not result.supported:
            return {"ok": False, "reason": result.reason, "version": result.version}

        manager = await self.build_manager(emulator_id)
        resolved_path = result.install_path or install_path
        path_id = _utils_emulator2.slots.make_path_id(resolved_path)

        if manager.path_of(path_id) is not None:
            return {"ok": False, "reason": "already_added", "version": result.version}

        record = _utils_emulator2.slots.PathRecord(
            path_id=path_id,
            install_path=resolved_path,
            alias=alias or self._default_alias(resolved_path),
            type=result.type,
            version=result.version,
        )
        paths = manager.paths + [record]

        # 重新添加同一条路径时复活原来的墓碑, 沿用原设备号
        revived = manager.slots.revive_path(path_id)
        manager.paths = paths

        native_indexes = await manager.enumerate_native(record)
        added_slots: list[dict] = []
        if native_indexes is not None:
            for slot_record in manager.slots.sync_path(path_id, native_indexes):
                added_slots.append(
                    {"slot": slot_record.slot, "nativeIndex": slot_record.native_index}
                )

        await self._save(emulator_id, paths, manager.slots)

        if record.type == "avd":
            # MAS 不下载组件；解压出来的根目录可能还没有 mas-avd.json：补一份

            try:
                if await asyncio.to_thread(
                    _utils_emulator2.avd.components.ensure_metadata, resolved_path
                ):
                    logger.info(f"魔改 AVD {resolved_path} 没有 mas-avd.json，已补写")
            except OSError as e:
                logger.warning(f"魔改 AVD {resolved_path} 补写 mas-avd.json 失败: {e}")

        # 魔改 AVD 根目录里一台实例都没有（刚解压的内测包）：按默认值建第一台，
        # 测试者加完就能直接用。已经有实例的不动；建不出来不影响路径本身已经加好
        if record.type == "avd" and native_indexes is not None and not native_indexes:
            try:
                created = await self.create_instance(emulator_id, path_id, None, {})
            except Exception as e:  # noqa: BLE001 - 路径已经加好，建实例失败只记下来
                logger.warning(f"魔改 AVD {resolved_path} 自动新建第一台实例失败: {e}")
            else:
                added_slots.append(
                    {"slot": created["slot"], "nativeIndex": created["nativeIndex"]}
                )
                logger.info(
                    f"魔改 AVD {resolved_path} 还没有实例，已按默认值新建第一台"
                    f"（设备号 #{created['slot']}）"
                )

        return {
            "ok": True,
            "reason": "ok",
            "pathId": path_id,
            "alias": record.alias,
            "type": record.type,
            "version": record.version,
            "assignedSlots": added_slots,
            "revivedSlots": revived,
        }

    async def preview_remove_path(self, emulator_id: str, path_id: str) -> dict:
        """移除前的确认信息：会失效的设备号 + 受影响的脚本。"""
        manager = await self.build_manager(emulator_id)
        slots = manager.slots.slots_of(path_id)
        return {
            "slots": slots,
            "affectedScripts": [
                item.to_dict()
                for item in self.find_affected_scripts(emulator_id, slots)
            ],
        }

    async def remove_path(self, emulator_id: str, path_id: str) -> dict:
        """移除一条模拟器路径。

        设备号**写墓碑而不是回收**——号码永不分配给其他设备，
        否则以后新加的模拟器会顶掉旧脚本的绑定。
        """
        manager = await self.build_manager(emulator_id)
        affected = self.find_affected_scripts(
            emulator_id, manager.slots.slots_of(path_id)
        )
        # 先把早先删除实例留下、还挂在这条路径上的墓碑退役，
        # 否则写完路径墓碑就分不出来了，重新添加时会把已删除实例的号一起复活。
        # 只对在用路径做：路径已移除（上次移除成功但响应丢了、用户重试）时，
        # 这条路径上的墓碑都是路径墓碑，清掉就没法在重新添加时沿用原号。
        if manager.path_of(path_id) is not None:
            manager.slots.retire_tombstones(path_id)
        tombstoned = manager.slots.tombstone_path(path_id)
        paths = [record for record in manager.paths if record.path_id != path_id]

        await self._save(emulator_id, paths, manager.slots)
        return {
            "ok": True,
            "tombstonedSlots": tombstoned,
            "affectedScripts": [item.to_dict() for item in affected],
        }

    async def create_instance(
        self,
        emulator_id: str,
        path_id: str,
        name: str | None = None,
        options: dict | None = None,
    ) -> dict:
        """在某条模拟器安装下新建一个实例，并给它分配设备号。

        ``options`` 只对魔改 AVD 生效（``memory_mb`` / ``cpu`` / ``fps`` / ``data_partition_gb`` /
        ``native_index``）：
        雷电 / MuMu 新建时用的是模拟器自己的默认配置。
        """
        manager = await self.build_manager(emulator_id)
        path = manager.path_of(path_id)
        if path is None:
            return {"ok": False, "reason": "path_not_found"}

        backend = await manager.manager_for(path)
        if path.type == "avd":
            cleaned = {k: v for k, v in (options or {}).items() if v is not None}
            native_index = await backend.create_instance(name, **cleaned)
        else:
            native_index = await backend.create_instance(name)

        added = manager.slots.sync_path(path_id, [native_index])
        await self._save(emulator_id, manager.paths, manager.slots)
        slot = (
            added[0].slot if added else (manager.slots.find(path_id, native_index).slot)
        )
        return {"ok": True, "reason": "ok", "slot": slot, "nativeIndex": native_index}

    async def preview_delete_instance(self, emulator_id: str, slot: str) -> dict:
        """删除实例前的确认信息。"""
        manager = await self.build_manager(emulator_id)
        record = manager.slots.resolve(str(slot))
        if record is None or record.state != "active":
            return {"ok": False, "reason": "slot_not_found", "affectedScripts": []}
        return {
            "ok": True,
            "reason": "ok",
            "affectedScripts": [
                item.to_dict()
                for item in self.find_affected_scripts(emulator_id, [str(slot)])
            ],
        }

    async def open_store(self, emulator_id: str, slot: str) -> dict:
        """打开某台设备所属模拟器的游戏中心。

        雷电开启「大雷主人模式」之后 launcher 会把游戏中心从桌面和应用列表里过滤掉，
        用户在模拟器里没有入口；这个接口就是给界面上那个按钮用的。

        拉不起来是「这次没成」，返回 ``ok=False`` 加一句能照做的话，不抛异常——
        和 :meth:`Emulator2Manager.launch_app` 的口径一致。
        """
        manager = await self.build_manager(emulator_id)
        result = await manager.open_store(str(slot))
        return {
            "ok": result.ok,
            "reason": result.reason,
            "message": _STORE_OPEN_MESSAGES.get(result.reason, result.reason),
        }

    async def delete_instance(self, emulator_id: str, slot: str) -> dict:
        """删除一个实例，并把它的设备号退役。

        早先的做法是不写墓碑，理由是「以后在同一原生索引重建实例还能拿回同一个号」。
        实测下来那个好处远不如代价：删掉的实例会一直在设备表里占一行「未找到」，
        用户看到的是一台并不存在的模拟器。

        改成写墓碑：该行从设备表消失，但**号码仍然不回收**——回收了的话，
        以后新建的实例可能拿到同一个号，而某个脚本还绑着它，就会悄悄连到另一台设备上。
        绑定了该号的脚本下次执行直接失败，不会回退到别的设备。

        退役的号同时和路径、原生索引脱钩：雷电新建实例总是复用最小的空闲索引，墓碑占着它，
        新实例就分不到号、在设备表里看不见。脱钩后新实例拿一个新号。
        """
        manager = await self.build_manager(emulator_id)
        record = manager.slots.resolve(str(slot))
        if record is None or record.state != "active":
            return {"ok": False, "reason": "slot_not_found"}
        path = manager.path_of(record.path_id)
        if path is None:
            return {"ok": False, "reason": "path_not_found"}

        backend = await manager.manager_for(path)
        try:
            await backend.delete_instance(record.native_index)
        except RuntimeError as e:
            logger.warning(f"删除实例失败: {e}")
            return {"ok": False, "reason": "delete_failed", "message": str(e)}

        manager.slots.tombstone_slot(str(slot))
        await self._save(emulator_id, manager.paths, manager.slots)
        return {"ok": True, "reason": "ok"}

    async def list_devices(
        self, emulator_id: str, *, with_settings: bool = True
    ) -> dict:
        """合并设备列表。

        每条安装只问一次 ``getInfo``：它既是「这次枚举到了哪些实例」，也是每台的状态，
        没必要像早先那样先枚举一遍再取一遍状态。枚举失败的安装标 ``unavailable``——
        **一次枚举失败不等于实例被删除**，既不写墓碑，也不影响下次恢复。

        ``with_settings=False`` 只取状态，不读四项设置与稳定模式——状态轮询走这条，
        设置几秒变不了一次，没必要每轮把每台的配置都读一遍（MuMu 那边每台是一个子进程）。
        """
        manager = await self.build_manager(emulator_id)

        devices: list[dict] = []
        dirty = False
        for path in manager.paths:
            try:
                backend = await manager.manager_for(path)
                info = await backend.getInfo(None)
            except Exception as e:  # noqa: BLE001 - 一条安装枚举失败不影响其余
                logger.warning(f"枚举 {path.alias or path.install_path} 失败: {e}")
                for record in manager.slots.records:
                    if record.path_id != path.path_id or record.state != "active":
                        continue
                    devices.append(
                        self._device_row(
                            path, record.slot, record.native_index, None, "unavailable"
                        )
                    )
                continue

            # sync_path 里也会退役，这里先单独退一次：只退役、没新增设备号时也要落盘
            if manager.slots.retire_tombstones(path.path_id):
                dirty = True
            if manager.slots.sync_path(path.path_id, list(info)):
                dirty = True

            # 枚举成功但没有这台 = 已经确认它不在了（多半是在模拟器自己的多开器里删掉的）。
            # 列一行「未找到」的空设备只是噪音，用户看到的是一台并不存在的模拟器。
            # 设备号仍留在槽位表里：以后同一个原生索引再出现，还是这个号。
            #
            # 与 unavailable 的区别在于「查证不存在」和「没查成」：整条安装不可达时我们
            # 并不知道实例还在不在，那种照常显示并标暂时不可用。
            records = [
                record
                for record in manager.slots.records
                if record.path_id == path.path_id
                and record.state == "active"
                and record.native_index in info
            ]

            overviews: dict[str, tuple] = {}
            if with_settings:
                overviews = await self._read_overviews(backend, records)

            for record in records:
                settings, stable, unsafe = overviews.get(
                    record.native_index, ({}, False, [])
                )
                devices.append(
                    self._device_row(
                        path,
                        record.slot,
                        record.native_index,
                        info[record.native_index],
                        "ok",
                        settings,
                        stable,
                        unsafe,
                    )
                )

        if dirty:
            await self._save(emulator_id, manager.paths, manager.slots)

        return {
            "paths": [
                {
                    **path.to_dict(),
                    "slots": manager.slots.slots_of(path.path_id),
                }
                for path in manager.paths
            ],
            "devices": devices,
        }

    async def _read_overviews(
        self, backend, records
    ) -> dict[str, tuple[dict, bool, list]]:
        """并发读一条安装下各台的设置与稳定模式。读不出的那台不在结果里，整张表照常出。"""
        import asyncio

        gate = asyncio.Semaphore(_OVERVIEW_CONCURRENCY)

        async def read_one(record) -> tuple[str, tuple | None]:
            async with gate:
                try:
                    settings, stable, unsafe = await backend.read_instance_overview(
                        record.native_index
                    )
                except Exception as e:  # noqa: BLE001 - 读不出设置不该让整张表挂掉
                    logger.warning(f"读取设备 #{record.slot} 设置失败: {e}")
                    return record.native_index, None
                return record.native_index, (settings.to_dict(), stable, unsafe)

        results = await asyncio.gather(*(read_one(record) for record in records))
        return {index: overview for index, overview in results if overview is not None}

    def _device_row(
        self,
        path: _utils_emulator2.slots.PathRecord,
        slot: str,
        native_index: str,
        info,
        availability: str,
        settings: dict | None = None,
        stable_mode: bool = False,
        stable_unsafe: list[str] | None = None,
    ) -> dict:
        return {
            "slot": slot,
            "pathId": path.path_id,
            "alias": path.alias,
            # realType 是设备的真实类型, 前端不必自己按配置类型拼表
            "realType": path.type,
            "nativeIndex": native_index,
            "availability": availability,
            "title": getattr(info, "title", ""),
            "status": int(getattr(info, "status", 5)),
            "adbAddress": getattr(info, "adb_address", ""),
            # 这里给的是「已保存设置，下次启动使用」，不是运行中实例的当前配置——
            # 运行中保存后这里立刻变，但那台实例还在用旧值。
            "settings": settings or {},
            "stableMode": stable_mode,
            # 还没进入安全状态的项，界面用它告诉用户点一下会改动什么
            "stableUnsafe": stable_unsafe or [],
        }

    async def apply_settings(
        self, emulator_id: str, slot: str, changes: dict, expected: dict | None = None
    ) -> dict:
        """写一台设备的设置。冲突时不覆盖，交回被改动的字段名让界面提示刷新。"""
        manager = await self.build_manager(emulator_id)
        try:
            applied = await manager.write_settings(str(slot), changes, expected)
        except _utils_emulator2.settings.SettingsConflictError as e:
            return {
                "ok": False,
                "conflicts": e.fields,
                "message": "配置在编辑期间被改动，请刷新后重试",
            }
        await self._record_baseline(emulator_id, str(slot), applied)
        return {"ok": True, "conflicts": [], "applied": applied, "message": ""}

    async def apply_stable_mode(
        self, emulator_id: str, slots: list[str] | None = None
    ) -> dict:
        """把一台或全部设备切进稳定模式。

        ``slots`` 为空表示全部。一台失败不拖垮整批，逐台交回结果。
        """
        manager = await self.build_manager(emulator_id)

        targets = (
            [str(slot) for slot in slots]
            if slots
            else [r.slot for r in manager.slots.records if r.state == "active"]
        )

        results: list[dict] = []
        for slot in targets:
            try:
                changed = await manager.apply_stable_mode(slot)
            except Exception as e:  # noqa: BLE001 - 逐台上报
                logger.warning(f"设备 #{slot} 应用稳定模式失败: {e}")
                results.append(
                    {"slot": slot, "ok": False, "message": self.readable_error(e)}
                )
                continue
            results.append(
                {
                    "slot": slot,
                    "ok": True,
                    # 空列表表示这台本来就已经是安全状态，没有可改的
                    "message": "、".join(changed),
                }
            )

        return {
            "results": results,
            "okCount": sum(1 for item in results if item["ok"]),
            "failCount": sum(1 for item in results if not item["ok"]),
        }

    async def apply_settings_to_all(self, emulator_id: str, changes: dict) -> dict:
        """把同一组设置写到**全部**设备上。

        没有勾选、没有冲突比对：用户点这个按钮就是明确要求「所有实例都设成这组值」。
        一台失败不影响其余，逐台交回结果。
        """
        manager = await self.build_manager(emulator_id)

        # 先校验一次，参数不合法就整批拒绝，不要写到一半才报错
        cleaned = _utils_emulator2.settings.validate_changes(changes)

        results: list[dict] = []
        for record in manager.slots.records:
            if record.state != "active":
                continue
            try:
                await manager.write_settings(record.slot, cleaned, expected=None)
            except Exception as e:  # noqa: BLE001 - 逐台上报, 一台失败不拖垮整批
                logger.warning(f"设备 #{record.slot} 应用批量设置失败: {e}")
                results.append(
                    {
                        "slot": record.slot,
                        "ok": False,
                        "message": self.readable_error(e),
                    }
                )
                continue
            await self._record_baseline(emulator_id, record.slot, cleaned)
            results.append({"slot": record.slot, "ok": True, "message": ""})

        return {
            "results": results,
            "okCount": sum(1 for item in results if item["ok"]),
            "failCount": sum(1 for item in results if not item["ok"]),
        }

    async def _avd_backend(self, emulator_id: str, slot: str):

        manager = await self.build_manager(emulator_id)
        path, record = manager.resolve_slot(str(slot))
        if path.type != "avd":
            raise ValueError("该设备不是魔改 AVD")
        backend = await manager.manager_for(path)
        assert isinstance(backend, _utils_emulator2.avd.manager.AvdManager)
        return backend, record.native_index

    async def avd_instance_options(self, emulator_id: str, slot: str) -> dict[str, Any]:
        backend, native_index = await self._avd_backend(emulator_id, slot)
        return backend.instance_options(native_index)

    async def install_avd_apk(
        self, emulator_id: str, slot: str, apk_path: str
    ) -> dict[str, Any]:
        """在开着的实例里装一个本地 ``.apk``。只认 ``.apk``；``.xapk`` / 拆分包不支持。

        只收完整路径：相对路径会按后端的工作目录解析，装进去的未必是用户选的那个文件。"""
        text = str(apk_path or "").strip().strip('"')
        if not text:
            raise ValueError("请选择要安装的 APK 文件")
        apk = Path(text)
        if not apk.is_absolute():
            raise ValueError(f"请给出安装包的完整路径（{text}）")
        if apk.suffix.lower() != ".apk":
            raise ValueError(
                f"{apk.name} 不是 .apk 安装包（.xapk、拆分安装包暂不支持）"
            )
        if not await asyncio.to_thread(apk.is_file):
            raise ValueError(f"找不到安装包 {apk}")
        backend, native_index = await self._avd_backend(emulator_id, slot)
        result = await backend.install_apk(native_index, apk)
        return {
            "ok": True,
            "reason": "ok",
            "message": f"已安装 {apk.name}",
            "result": result,
        }
