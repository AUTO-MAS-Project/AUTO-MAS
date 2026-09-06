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

继承旧 ``LDManager``，启动 / 关闭 / 状态 / 实例锁 / 配置守卫**全部原样复用**，
只覆盖两处行为：

1. **不禁用游戏中心。** 旧管理器在启动流程里自己读全局「屏蔽广告」开关并执行
   ``pm disable-user com.android.flysilkworm``。实测那条命令对安卓端已观察到的两类广告
   （桌面顶部搜索栏、底部推广栏）一条都挡不住，唯一效果是杀掉用户想保留的游戏中心，
   所以这里让它变成空操作。
2. **老板键按实例读。** 旧管理器读的是配置级的 ``Info.BossKey``，而雷电的老板键是
   每个实例各一份的。认不出时**明确报错，不猜**。

配置守卫（启动前拍快照、关闭后校验回滚）**有意保留**——用户开着屏蔽广告时，
新配置也享受同样的配置保护。代价是设置写入必须拿同一把实例锁，见 :meth:`write_instance_settings`。
"""

import asyncio
import json
import os
import shutil
import time
from pathlib import Path

from app.models.config import EmulatorConfig
from app.models.emulator import DeviceRef, DeviceStatus
from app.utils import ProcessRunner, get_logger
from app.utils.emulator.ldplayer import _INSTANCE_CONFIG_SNAPSHOTS, LDManager
from app.utils.platform import IS_WINDOWS

from .bosskey import BossKey, read_boss_key
from .settings import (
    InstanceSettings,
    SettingsConflictError,
    apply_changes,
    build_settings,
    detect_conflicts,
    validate_changes,
)
from .stability import LDPLAYER_ITEMS, evaluate, safe_writes


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


class BossKeyUnavailableError(RuntimeError):
    """无法确定该实例的老板键，隐藏操作不可用。

    带上 ``reason`` 供界面区分：是认不出修饰键、认不出按键，还是配置读不出来。
    """

    def __init__(self, idx: str, reason: str) -> None:
        super().__init__(f"无法确定雷电实例 {idx} 的老板键: {reason}")
        self.idx = idx
        self.reason = reason


class LDPlayer14Manager(LDManager):
    """一条雷电 14 安装的管理器。

    构造它需要一份**合成的单安装配置**：``Info.Type`` 必须是 ``ldplayer``
    （父类构造函数会校验），``Info.Path`` 必须正好是该安装的 ``ldconsole.exe``——
    实例锁的键就是这个路径 ``resolve().casefold()`` 加原生索引，路径口径不对
    就和旧配置、和设置写入各拿各的锁，配置守卫的回滚时序就挡不住了。
    """

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

    async def read_stable_mode(self, idx: str) -> tuple[bool, list[str]]:
        """稳定模式是否已生效，以及还有哪几项不安全。"""
        config = await asyncio.to_thread(self.read_instance_config, idx)
        if config is None:
            return False, [item.field for item in LDPLAYER_ITEMS]
        current = {item.key: _dig_flat(config, item.key) for item in LDPLAYER_ITEMS}
        return evaluate(LDPLAYER_ITEMS, current)

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

    async def _block_ads_via_adb(self, idx: str) -> None:
        """空操作：不禁用游戏中心。

        旧实现禁用 ``com.android.flysilkworm``。实测（见去广告实验记录）它对安卓桌面
        顶部搜索栏与底部推广栏一条都挡不住——那两处是雷电魔改 launcher 自己联网拉的，
        与游戏中心无关——所以旧实现只是白白杀掉用户要保留的游戏中心。
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
