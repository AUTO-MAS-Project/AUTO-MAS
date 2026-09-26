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

"""官方模拟器实例（AVD）的配置文件。

一台实例 = ``avd\\mas_<i>.ini`` + ``avd\\mas_<i>.avd\\config.ini``；原生索引 i 就是名字里的
数字，端口也按它算，所以枚举只要扫 ``avd\\mas_*.ini``。配置只在停机时由我们写，模拟器
自己不回写（不像雷电），所以没有回写冲突。

实例的 MAS 侧设置（无头 / 带窗口、首次初始化做没做、渲染器）不放进 ``config.ini``——
模拟器不认识的键会被它自己的工具当成垃圾——而是放在根目录的 ``mas-avd.json`` 里。
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .components import avd_home, read_metadata, write_metadata
from .constants import (
    AVD_NAME_PREFIX,
    CPU_CHOICES,
    DATA_PARTITION_RANGE_GB,
    DEFAULT_CPU,
    DEFAULT_DATA_PARTITION_GB,
    DEFAULT_MEMORY_MB,
    MEMORY_CHOICES_MB,
    SCREEN_DENSITY,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    SYSTEM_IMAGE_SYSDIR,
    avd_name,
    valid_native_index,
)

#: 实例配置模板，取自预研里调好的 ``mas_p0``（``pixel_tablet`` 模板改 1920×1080 / DPI 280 /
#: 横屏 / 显卡直通），去掉了设备外框与设备型号——型号只影响窗口外框，外框也关了。
_CONFIG_TEMPLATE: tuple[tuple[str, str], ...] = (
    ("PlayStore.enabled", "no"),
    ("abi.type", "x86_64"),
    ("avd.ini.encoding", "UTF-8"),
    ("disk.cachePartition", "yes"),
    ("disk.cachePartition.size", "66MB"),
    ("fastboot.forceColdBoot", "yes"),
    ("fastboot.forceFastBoot", "no"),
    ("hw.accelerometer", "yes"),
    ("hw.arc", "false"),
    ("hw.audioInput", "no"),
    ("hw.audioOutput", "yes"),
    ("hw.battery", "yes"),
    ("hw.camera.back", "none"),
    ("hw.camera.front", "none"),
    ("hw.cpu.arch", "x86_64"),
    ("hw.dPad", "no"),
    ("hw.gps", "no"),
    ("hw.gpu.enabled", "yes"),
    ("hw.gpu.mode", "host"),
    ("hw.gsmModem", "yes"),
    ("hw.gyroscope", "yes"),
    ("hw.initialOrientation", "landscape"),
    ("hw.keyboard", "yes"),
    ("hw.keyboard.lid", "yes"),
    ("hw.lcd.depth", "32"),
    ("hw.lcd.vsync", "60"),
    ("hw.mainKeys", "no"),
    ("hw.sdCard", "no"),
    ("hw.sensors.orientation", "yes"),
    ("hw.sensors.proximity", "no"),
    ("hw.trackBall", "no"),
    ("hw.useext4", "yes"),
    ("showDeviceFrame", "no"),
    ("tag.display", "Google APIs"),
    ("tag.id", "google_apis"),
    ("target", "android-34"),
    ("vm.heapSize", "192M"),
)


@dataclass(frozen=True)
class AvdInstance:
    native_index: str
    name: str
    title: str
    config: dict[str, str]

    @property
    def memory_mb(self) -> int | None:
        return parse_memory_mb(self.config.get("hw.ramSize"))

    @property
    def cpu(self) -> int | None:
        return _int_or_none(self.config.get("hw.cpu.ncore"))

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


def parse_memory_mb(raw: object) -> int | None:
    """``hw.ramSize`` 可能写成 ``4096`` / ``4096M`` / ``4G``。"""
    text = str(raw or "").strip().upper()
    if not text:
        return None
    if text.endswith("G"):
        value = _int_or_none(text[:-1])
        return None if value is None else value * 1024
    if text.endswith("M") or text.endswith("MB"):
        return _int_or_none(text.rstrip("B").rstrip("M"))
    return _int_or_none(text)


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


def update_instance_meta(
    root: str | Path, native_index: int | str, **changes: Any
) -> dict[str, Any]:
    data = read_metadata(root)
    instances = data.get("instances")
    if not isinstance(instances, dict):
        instances = {}
    meta = instances.get(str(native_index))
    meta = dict(meta) if isinstance(meta, dict) else {}
    meta.update(changes)
    instances[str(native_index)] = meta
    data["instances"] = instances
    write_metadata(root, data)
    return meta


def remove_instance_meta(root: str | Path, native_index: int | str) -> None:
    data = read_metadata(root)
    instances = data.get("instances")
    if isinstance(instances, dict) and str(native_index) in instances:
        del instances[str(native_index)]
        write_metadata(root, data)


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
            "官方模拟器的内存只能选 "
            + " / ".join(f"{value // 1024} GB" for value in MEMORY_CHOICES_MB)
        )
    if cores not in CPU_CHOICES:
        raise ValueError(
            "官方模拟器的 CPU 核数只能选 " + " / ".join(str(v) for v in CPU_CHOICES)
        )
    low, high = DATA_PARTITION_RANGE_GB
    if not low <= data_gb <= high:
        raise ValueError(f"数据盘上限只能在 {low}–{high} GB 之间")
    return memory, cores, data_gb


def create_instance_files(
    root: str | Path,
    native_index: int,
    *,
    title: str | None,
    memory_mb: int,
    cpu: int,
    data_partition_gb: int,
    headless: bool = True,
) -> AvdInstance:
    """写 ``mas_<i>.ini`` 与 ``mas_<i>.avd\\config.ini``。实例已存在时拒绝。"""
    if not valid_native_index(native_index):
        raise ValueError(f"原生索引 {native_index} 不可用")
    if ini_path(root, native_index).exists() or avd_dir(root, native_index).exists():
        raise RuntimeError(f"实例 {avd_name(native_index)} 已存在")

    name = avd_name(native_index)
    directory = avd_dir(root, native_index)
    config = dict(_CONFIG_TEMPLATE)
    config.update(
        {
            "avd.id": name,
            "avd.name": name,
            "avd.ini.displayname": title or name,
            "disk.dataPartition.size": f"{data_partition_gb}G",
            "hw.cpu.ncore": str(cpu),
            "hw.ramSize": f"{memory_mb}M",
            "hw.lcd.width": str(SCREEN_WIDTH),
            "hw.lcd.height": str(SCREEN_HEIGHT),
            "hw.lcd.density": str(SCREEN_DENSITY),
            "image.sysdir.1": SYSTEM_IMAGE_SYSDIR,
        }
    )
    directory.mkdir(parents=True)
    write_ini(directory / "config.ini", config)
    write_ini(
        ini_path(root, native_index),
        {
            "avd.ini.encoding": "UTF-8",
            "path": str(directory),
            "path.rel": f"avd\\{name}.avd",
            "target": "android-34",
        },
    )
    update_instance_meta(
        root,
        native_index,
        headless=headless,
        initialized=False,
        createdAt=datetime.now().isoformat(timespec="seconds"),
    )
    return AvdInstance(str(native_index), name, title or name, config)


def write_instance_config(
    root: str | Path, native_index: int | str, changes: dict[str, str]
) -> None:
    path = config_path(root, native_index)
    config = read_ini(path)
    if not config:
        raise RuntimeError(f"实例 {avd_name(native_index)} 的配置读不出")
    config.update(changes)
    write_ini(path, config)


def delete_instance_files(root: str | Path, native_index: int | str) -> None:
    """删 ``mas_<i>.ini`` 与 ``mas_<i>.avd\\``（含数据盘）。调用方负责先确认已停止。"""
    directory = avd_dir(root, native_index)
    if directory.exists():
        shutil.rmtree(directory)
    ini_path(root, native_index).unlink(missing_ok=True)
    remove_instance_meta(root, native_index)
