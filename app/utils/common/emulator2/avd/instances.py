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

"""ModAVD 实例选项的校验：新建 / 改设置共用。

实例的配置文件（``avd\\*.ini``、``config.ini``、``mas-avd.json``）由 ModAVD 命令行读写，MAS 不碰；
这里只做参数校验和分辨率档位的换算，都不读文件。
"""

from __future__ import annotations

from .constants import (
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
)


def _int_or_none(raw: object) -> int | None:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


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
    """按所选档位给出宽、高、DPI，保持方向。省略档位时识别现有宽高。"""
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
    }


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
