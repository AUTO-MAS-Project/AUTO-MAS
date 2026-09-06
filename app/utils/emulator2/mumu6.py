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

"""Emulator 2.0 的 MuMu 6 后端。

继承旧 ``MumuManager``，启动 / 关闭 / 状态 / 隐藏全部原样复用；这里只补三件事：
读写四项设置、新建实例、删除实例。

**和雷电走的是完全不同的通道。** 雷电没有可用的命令行（没有帧率参数、CPU 内存只收有限
档位、而且根本不能读），只能直接改实例配置文件；MuMu 的 ``MuMuManager setting`` 读写都
齐全，所以走命令行，一个文件都不碰。

MuMu 这边有三个实测出来的坑，都在本模块里兜住：

1. **``.custom`` 键写了不一定生效。** ``resolution_mode`` / ``performance_mode`` 是枚举，
   实测用户的两台实例都是 ``tablet.3`` / ``middle``——此时 ``resolution_width.custom``
   和 ``performance_cpu.custom`` 里存着值，但跑的根本不是它们。所以写自定义值时
   **必须同时把对应的 mode 切成 ``custom``**，否则等于什么都没做。
2. **读要读裸键，不是 ``.custom``。** ``resolution_width`` 这类裸键给的才是当前生效值；
   CPU / 内存没有裸键，得按当前 mode 去读 ``performance_cpu.<mode>``。
3. **内存是 GB 浮点，而且只收固定档位。** ``performance_mem.list`` 实测是
   ``[0.75, 1, 1.5, 1.75, 2, 3, ...]``；我们对外统一用 MB，换算后不在档位表里就明确拒绝，
   **不做静默吸附**——用户以为设了 5000 MB 结果跑在 4096 上是更糟的结果。
"""

import asyncio
import json
from pathlib import Path

from app.models.config import EmulatorConfig
from app.models.emulator import DeviceRef
from app.utils import ProcessRunner, get_logger
from app.utils.emulator.mumu import MumuManager

from .settings import (
    FieldValue,
    InstanceSettings,
    SettingsConflictError,
    build_settings,
    detect_conflicts,
    validate_changes,
)
from .stability import MUMU_ITEMS, evaluate, safe_writes

logger = get_logger("Emulator2 MuMu管理")

#: 新建 / 删除实例后复核 ``info`` 的次数与间隔。
_INSTANCE_MUTATION_RETRIES = 3
_INSTANCE_MUTATION_DELAY_SECONDS = 2.0

#: 当前生效值的裸键。CPU / 内存没有裸键，见 :meth:`MuMu6Manager.read_instance_settings`。
_EFFECTIVE_KEYS = {
    "width": "resolution_width",
    "height": "resolution_height",
    "dpi": "resolution_dpi",
    "fps": "max_frame_rate",
}

#: 写入用的键。分辨率三项和 CPU / 内存两项分属两个 mode 闸门。
_WRITE_KEYS = {
    "width": "resolution_width.custom",
    "height": "resolution_height.custom",
    "dpi": "resolution_dpi.custom",
    "cpu": "performance_cpu.custom",
    "memoryMb": "performance_mem.custom",
    "fps": "max_frame_rate",
}

#: 哪些字段受哪个 mode 闸门控制。写它们就得把 mode 一起切到 custom。
_MODE_GATES = {
    "resolution_mode": ("width", "height", "dpi"),
    "performance_mode": ("cpu", "memoryMb"),
}

_MB_PER_GB = 1024


def _to_float(raw: object) -> float | None:
    """MuMu 把数值全当字符串返回，而且常带小数（``"1280.000000"``）。"""
    if raw is None:
        return None
    try:
        value = float(str(raw))
    except (TypeError, ValueError):
        return None
    # NaN / inf 后面 round() 会抛，这里就挡掉
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return value


def _to_int(raw: object) -> int | None:
    value = _to_float(raw)
    return None if value is None else round(value)


def _gb_to_mb(raw: object) -> int | None:
    """GB 浮点 → MB。

    **必须先乘再取整。** 先把 GB 取整会让所有非整数档位全错：
    1.5 GB 会被读成 2 GB = 2048 MB，而正确答案是 1536 MB——
    显示出来的值既不是实际值，也对不上拒绝提示里列的档位表。
    """
    value = _to_float(raw)
    return None if value is None else round(value * _MB_PER_GB)


def parse_mem_list(raw: str | None) -> list[int]:
    """把 ``performance_mem.list`` 解析成允许的 MB 档位。

    原文形如 ``[0.750000,1.000000,...](best=6.000000)``，单位是 GB。
    """
    if not raw:
        return []
    head, _, _ = str(raw).partition("]")
    body = head.lstrip("[")
    values: list[int] = []
    for chunk in body.split(","):
        value = _gb_to_mb(chunk.strip())
        if value is not None:
            values.append(value)
    return values


class MuMu6Manager(MumuManager):
    """一条 MuMu 6 安装的管理器。"""

    async def _run(self, *args: str) -> str:
        result = await ProcessRunner.run_process(
            self.emulator_path,
            *args,
            timeout=self.config.get("Info", "MaxWaitTime"),
            if_merge_std=True,
        )
        return str(getattr(result, "stdout", "") or "")

    async def _setting_get(self, idx: str, keys: list[str]) -> dict[str, str]:
        """读一批设置键。读不出或解析失败返回空字典。"""
        args: list[str] = ["setting", "-v", str(idx)]
        for key in keys:
            args += ["-k", key]
        try:
            output = await self._run(*args)
            data = json.loads(output[output.index("{") : output.rindex("}") + 1])
        except Exception as e:  # noqa: BLE001 - 读不出就当未知, 不该让调用方炸
            logger.warning(f"读取 MuMu 实例 {idx} 设置失败: {e}")
            return {}
        return {k: str(v) for k, v in data.items()} if isinstance(data, dict) else {}

    async def _setting_set(self, idx: str, pairs: dict[str, str]) -> None:
        """写一批设置键。

        ``MuMuManager setting`` 收多组 ``-k``/``-val``，顺序一一对应，
        所以这里一次调用写完整批，避免写到一半失败留下半套配置。
        """
        args: list[str] = ["setting", "-v", str(idx)]
        for key, value in pairs.items():
            args += ["-k", key, "-val", value]
        await self._run(*args)

    def resolve_device(self, idx: str) -> DeviceRef | None:
        """本管理器只管一条安装，索引就是原生索引。"""
        return DeviceRef(
            emulator_type="mumu",
            manager_path=str(self.emulator_path),
            native_index=str(idx),
        )

    async def read_instance_settings(self, idx: str) -> InstanceSettings:
        """读四项设置，带状态。

        分辨率 / DPI 读裸键拿生效值，再看 ``resolution_mode`` 决定这值是用户自定义的
        （``saved``）还是模拟器预设的（``default``）；CPU / 内存没有裸键，
        按当前 ``performance_mode`` 去读对应档位的键。
        """
        wanted = list(_EFFECTIVE_KEYS.values()) + [
            "resolution_mode",
            "performance_mode",
            "performance_cpu.custom",
            "performance_mem.custom",
        ]
        data = await self._setting_get(idx, wanted)
        if not data:
            return build_settings(None, None, readable=False)

        resolution_mode = data.get("resolution_mode", "")
        performance_mode = data.get("performance_mode", "")

        # CPU / 内存的生效值藏在当前档位的键里，得再问一次
        cpu_key, mem_key = (
            f"performance_cpu.{performance_mode}",
            f"performance_mem.{performance_mode}",
        )
        if not performance_mode.startswith("custom"):
            data.update(await self._setting_get(idx, [cpu_key, mem_key]))
        else:
            cpu_key, mem_key = "performance_cpu.custom", "performance_mem.custom"

        def state_for(mode: str) -> str:
            return "saved" if mode.startswith("custom") else "default"

        fields: dict[str, FieldValue] = {
            "width": FieldValue(
                _to_int(data.get("resolution_width")), state_for(resolution_mode)
            ),
            "height": FieldValue(
                _to_int(data.get("resolution_height")), state_for(resolution_mode)
            ),
            "dpi": FieldValue(
                _to_int(data.get("resolution_dpi")), state_for(resolution_mode)
            ),
            "cpu": FieldValue(_to_int(data.get(cpu_key)), state_for(performance_mode)),
            "memoryMb": FieldValue(
                _gb_to_mb(data.get(mem_key)), state_for(performance_mode)
            ),
            # 帧率没有 mode 闸门，读到就是生效值
            "fps": FieldValue(_to_int(data.get("max_frame_rate")), "saved"),
        }
        for name, item in fields.items():
            if item.value is None:
                fields[name] = FieldValue(None, "unset")
        return InstanceSettings(fields=fields)

    async def _allowed_memory_mb(self, idx: str) -> list[int]:
        data = await self._setting_get(idx, ["performance_mem.list"])
        return parse_mem_list(data.get("performance_mem.list"))

    async def write_instance_settings(
        self, idx: str, changes: dict, expected: dict | None = None
    ) -> dict[str, int]:
        """写四项设置。

        MuMu 没有雷电那套「关闭时回滚到启动前快照」的配置守卫，所以不需要共用实例锁——
        这里唯一的协同就是写前重读一次做冲突比对。
        """
        cleaned = validate_changes(changes)

        if "memoryMb" in cleaned:
            allowed = await self._allowed_memory_mb(idx)
            if allowed and cleaned["memoryMb"] not in allowed:
                raise ValueError(
                    "MuMu 只接受固定的内存档位，可选值（MB）: "
                    + ", ".join(str(item) for item in allowed)
                )

        if expected:
            current = await self.read_instance_settings(idx)
            conflicts = detect_conflicts(current, expected, list(cleaned))
            if conflicts:
                raise SettingsConflictError(conflicts)

        pairs: dict[str, str] = {}
        for name, value in cleaned.items():
            if name == "memoryMb":
                pairs[_WRITE_KEYS[name]] = f"{value / _MB_PER_GB:.6f}"
            else:
                pairs[_WRITE_KEYS[name]] = str(value)

        # 关键一步：不切 mode 的话，上面写进去的自定义值一个都不会生效
        for mode_key, owned in _MODE_GATES.items():
            if any(name in cleaned for name in owned):
                pairs[mode_key] = "custom"

        await self._setting_set(idx, pairs)
        logger.info(f"已写入 MuMu 实例 {idx} 的设置: {cleaned}")
        return cleaned

    async def read_stable_mode(self, idx: str) -> tuple[bool, list[str]]:
        """稳定模式是否已生效，以及还有哪几项不安全。"""
        data = await self._setting_get(idx, [item.key for item in MUMU_ITEMS])
        if not data:
            return False, [item.field for item in MUMU_ITEMS]
        return evaluate(MUMU_ITEMS, data)

    async def apply_stable_mode(self, idx: str) -> list[str]:
        """把不安全的项写成安全值，返回实际改动的字段名。"""
        data = await self._setting_get(idx, [item.key for item in MUMU_ITEMS])
        if not data:
            raise RuntimeError(f"MuMu 实例 {idx} 的设置读不出，拒绝写入")

        writes = safe_writes(MUMU_ITEMS, data)
        if not writes:
            return []

        await self._setting_set(idx, writes)
        changed = [item.field for item in MUMU_ITEMS if item.key in writes]
        logger.info(f"MuMu 实例 {idx} 已进入稳定模式，改动: {changed}")
        return changed

    async def _list_native(self) -> set[str]:
        info = await self.getInfo(None)
        return set(info.keys())

    async def create_instance(self, name: str | None = None) -> str:
        """新建一个实例，返回它的原生索引。

        和雷电一样按列表差异判定，不信返回码——``create`` 只说自己跑完了，
        不保证实例已经出现在 ``info`` 里。
        """
        before = await self._list_native()

        await self._run("create", "-n", "1")

        for _ in range(_INSTANCE_MUTATION_RETRIES):
            await asyncio.sleep(_INSTANCE_MUTATION_DELAY_SECONDS)
            created = await self._list_native() - before
            if created:
                native_index = min(
                    created, key=lambda x: int(x) if x.isdecimal() else 0
                )
                if name:
                    try:
                        await self._run("rename", "-v", native_index, "-n", name)
                    except Exception as e:  # noqa: BLE001 - 命名失败不该让新建算失败
                        logger.warning(f"重命名 MuMu 实例 {native_index} 失败: {e}")
                logger.info(f"已新建 MuMu 实例 {native_index}")
                return native_index

        raise RuntimeError("新建 MuMu 实例失败：实例列表里没有出现新的实例")

    async def delete_instance(self, native_index: str) -> None:
        """删除一个实例。实例必须先关闭。"""
        from app.models.emulator import DeviceStatus

        status = await self.getStatus(native_index)
        if status not in (DeviceStatus.OFFLINE, DeviceStatus.NOT_FOUND):
            raise RuntimeError(f"MuMu 实例 {native_index} 未关闭，无法删除")

        for _ in range(_INSTANCE_MUTATION_RETRIES):
            await self._run("delete", "-v", str(native_index))
            await asyncio.sleep(_INSTANCE_MUTATION_DELAY_SECONDS)
            if str(native_index) not in await self._list_native():
                logger.info(f"已删除 MuMu 实例 {native_index}")
                return

        raise RuntimeError(f"删除 MuMu 实例 {native_index} 失败：它仍然在列表中")


async def build_manager(
    manager_exe: str, max_wait_time: int, force_kill_on_close: bool = False
) -> MuMu6Manager:
    """为一条 MuMu 安装合成配置并构造管理器。

    ``manager_exe`` 必须是该安装的 ``MuMuManager.exe``。
    """
    config = EmulatorConfig()
    await config.load(
        {
            "Info": {
                "Name": Path(manager_exe).parent.name,
                "Type": "mumu",
                "Path": str(manager_exe),
                "MaxWaitTime": max_wait_time,
                "ForceKillOnClose": force_kill_on_close,
            }
        }
    )
    return MuMu6Manager(config)
