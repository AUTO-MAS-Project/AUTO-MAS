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

"""ModAVD 实例（AVD）的配置文件。

一台实例 = ``avd\\mas_<i>.ini`` + ``avd\\mas_<i>.avd\\config.ini``；原生索引 i 就是名字里的
数字，默认端口也按它算，所以枚举只要扫 ``avd\\mas_*.ini``。这些文件由 ModAVD 命令行写，
MAS 这里只读；另外放着新建 / 改设置共用的选项校验。

实例的其它设置（内存、新建状态等）不放进 ``config.ini``，而是放在根目录的 ``mas-avd.json`` 里。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .components import avd_home, read_metadata
from .constants import (
    AVD_NAME_PREFIX,
    CPU_CHOICES,
    DATA_PARTITION_RANGE_GB,
    DEFAULT_CPU,
    DEFAULT_DATA_PARTITION_GB,
    DEFAULT_FPS,
    DEFAULT_MEMORY_MB,
    DEFAULT_RESOLUTION,
    DISPLAY_PRESETS,
    FPS_CHOICES,
    MEMORY_CHOICES_MB,
    avd_name,
)


@dataclass(frozen=True)
class AvdInstance:
    native_index: str
    name: str
    title: str
    config: dict[str, str]

    @property
    def cpu(self) -> int | None:
        return _int_or_none(self.config.get("hw.cpu.ncore"))

    @property
    def fps(self) -> int:
        """刷新率（``hw.lcd.vsync``）；没写这一项时模拟器按 60 Hz 开机。"""
        return _int_or_none(self.config.get("hw.lcd.vsync")) or DEFAULT_FPS

    @property
    def data_partition_gb(self) -> int | None:
        raw = (self.config.get("disk.dataPartition.size") or "").strip().upper()
        if raw.endswith("G"):
            return _int_or_none(raw[:-1])
        if raw.endswith("M"):
            value = _int_or_none(raw[:-1])
            return None if value is None else value // 1024
        return None


def _int_or_none(raw: object) -> int | None:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


def read_ini(path: Path) -> dict[str, str]:
    """AVD 的 ini 是扁平的 ``key=value``，保持文件里的顺序。"""
    result: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return result
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip():
            result[key.strip()] = value.strip()
    return result


def write_ini(path: Path, data: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        "".join(f"{key}={value}\n" for key, value in data.items()), encoding="utf-8"
    )
    temp.replace(path)


def ini_path(root: str | Path, native_index: int | str) -> Path:
    return avd_home(root) / f"{avd_name(native_index)}.ini"


def avd_dir(root: str | Path, native_index: int | str) -> Path:
    return avd_home(root) / f"{avd_name(native_index)}.avd"


def config_path(root: str | Path, native_index: int | str) -> Path:
    return avd_dir(root, native_index) / "config.ini"


def list_instances(root: str | Path) -> dict[str, AvdInstance]:
    """``{原生索引: 实例}``，按原生索引排序。"""
    home = avd_home(root)
    found: dict[int, AvdInstance] = {}
    if not home.is_dir():
        return {}
    for ini in home.glob(f"{AVD_NAME_PREFIX}*.ini"):
        suffix = ini.stem[len(AVD_NAME_PREFIX) :]
        if not suffix.isdecimal():
            continue
        index = int(suffix)
        config_file = avd_dir(root, index) / "config.ini"
        if not config_file.is_file():
            continue
        config = read_ini(config_file)
        name = avd_name(index)
        title = config.get("avd.ini.displayname") or name
        found[index] = AvdInstance(str(index), name, title, config)
    return {str(index): found[index] for index in sorted(found)}


def instance_meta(root: str | Path, native_index: int | str) -> dict[str, Any]:
    instances = read_metadata(root).get("instances") or {}
    meta = instances.get(str(native_index)) if isinstance(instances, dict) else None
    return dict(meta) if isinstance(meta, dict) else {}


def resolution_for(config: dict[str, str]) -> int:
    """按已有宽高识别档位，非 1080p 的旧配置保持 720p。"""
    width = _int_or_none(config.get("hw.lcd.width"))
    height = _int_or_none(config.get("hw.lcd.height"))
    return 1080 if (width, height) in ((1920, 1080), (1080, 1920)) else 720


def validate_resolution(resolution: int | None) -> int:
    value = DEFAULT_RESOLUTION if resolution is None else resolution
    if value not in DISPLAY_PRESETS:
        raise ValueError("ModAVD 的分辨率只能选 1080 或 720")
    return value


def display_changes(
    config: dict[str, str], resolution: int | None = None
) -> dict[str, str]:
    """按所选档位写宽、高、DPI，保持方向并关闭导航栏。省略档位时识别现有宽高。"""
    preset = (
        resolution_for(config)
        if resolution is None
        else validate_resolution(resolution)
    )
    width, height, density = DISPLAY_PRESETS[preset]
    old_width = _int_or_none(config.get("hw.lcd.width")) or 0
    old_height = _int_or_none(config.get("hw.lcd.height")) or 0
    if old_height > old_width:
        width, height = height, width
    return {
        "hw.lcd.width": str(width),
        "hw.lcd.height": str(height),
        "hw.lcd.density": str(density),
        "hw.mainKeys": "yes",
    }


def memory_for(meta: dict[str, Any]) -> int:
    """实例的内存，每次开机原样传 ``-memory``。

    以前有过「按游戏自动」（``mas-avd.json`` 里不存 ``memoryMb``），已经取消：这类旧实例和存了
    不在档位里的值的，一律按默认 :data:`~.constants.DEFAULT_MEMORY_MB`。"""
    explicit = meta.get("memoryMb")
    if isinstance(explicit, int) and explicit in MEMORY_CHOICES_MB:
        return explicit
    return DEFAULT_MEMORY_MB


def validate_options(
    memory_mb: int | None, cpu: int | None, data_partition_gb: int | None
) -> tuple[int, int, int]:
    """新建 / 修改实例的三项参数：内存、核数只收固定档位，不做静默吸附。"""
    memory = DEFAULT_MEMORY_MB if memory_mb is None else int(memory_mb)
    cores = DEFAULT_CPU if cpu is None else int(cpu)
    data_gb = (
        DEFAULT_DATA_PARTITION_GB
        if data_partition_gb is None
        else int(data_partition_gb)
    )
    if memory not in MEMORY_CHOICES_MB:
        raise ValueError(
            "ModAVD 的内存只能选 "
            + " / ".join(f"{value // 1024} GB" for value in MEMORY_CHOICES_MB)
        )
    if cores not in CPU_CHOICES:
        raise ValueError(
            "ModAVD 的 CPU 核数只能选 " + " / ".join(str(v) for v in CPU_CHOICES)
        )
    low, high = DATA_PARTITION_RANGE_GB
    if not low <= data_gb <= high:
        raise ValueError(f"数据盘上限只能在 {low}–{high} GB 之间")
    return memory, cores, data_gb


def validate_fps(fps: int | None) -> int:
    """刷新率只收固定档位，不给就是默认 60。"""
    value = DEFAULT_FPS if fps is None else int(fps)
    if value not in FPS_CHOICES:
        raise ValueError(
            "ModAVD 的帧率只能选 " + " / ".join(str(v) for v in FPS_CHOICES)
        )
    return value
