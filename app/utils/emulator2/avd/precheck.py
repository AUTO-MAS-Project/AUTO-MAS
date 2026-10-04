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

"""官方模拟器开机前的电脑检查：硬件虚拟化、显卡 Vulkan、磁盘、内存。

每项给 ``ok``、原因、建议，``/avd/status`` 原样交给前端显示；开机路径（``AvdInstanceManager._launch``）
里不满足的拦截项直接拒绝开机并给出原因，不静默开下去。只读：不改系统设置、不装任何东西。

- **硬件虚拟化**：``emulator -accel-check``（WHPX）。拦截。
- **内存**：宿主可用内存 ≥ 这次要传的 ``-memory`` + 1.5 GB。拦截。
- **磁盘**：实例所在盘剩余 ≥ :data:`~.constants.MIN_FREE_DISK_GB_TO_BOOT`。拦截。
- **显卡 Vulkan**：子进程加载 ``vulkan-1.dll`` 枚举物理设备（:mod:`.vulkan_probe`）。**只提示不拦截**：
  没有硬件 Vulkan 时模拟器自动落到 SwiftShader 软件渲染，能开机、画面正常，只是游戏占满 CPU。
  开机后的渲染器检测（``dumpsys SurfaceFlinger``）对软件渲染也是只记录、提示，这里保持一致；
  探测本身也可能误判（加载器异常、远程桌面会话），拦下会让本来能用的电脑开不了机。
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import psutil

from app.utils import get_logger

from . import host
from .components import avd_home, emulator_exe
from .constants import (
    DEFAULT_MEMORY_MB,
    HOST_MEMORY_OVERHEAD_MB,
    MIN_FREE_DISK_GB_TO_BOOT,
    VULKAN_PROBE_CACHE_SECONDS,
    VULKAN_PROBE_TIMEOUT_SECONDS,
)

logger = get_logger("官方模拟器电脑检查")

PROBE_SCRIPT = Path(__file__).with_name("vulkan_probe.py")
#: ``VkPhysicalDeviceType``：4 = CPU（软件实现），其余（集成 / 独立 / 虚拟显卡）都算硬件。
_VK_DEVICE_TYPE_CPU = 4
_VK_DEVICE_TYPE_NAMES = {
    0: "其他",
    1: "集成显卡",
    2: "独立显卡",
    3: "虚拟显卡",
    4: "CPU",
}

ACCEL_ADVICE = (
    "先在 BIOS / UEFI 里打开 CPU 虚拟化（Intel VT-x / AMD SVM，常叫 Virtualization Technology），"
    "再在「启用或关闭 Windows 功能」里勾选「Windows 虚拟机监控程序平台」，然后重启电脑"
)
VULKAN_ADVICE = (
    "安装或更新显卡驱动（NVIDIA / AMD / Intel 官网驱动自带 Vulkan）。没有可用的显卡时模拟器只能"
    "软件渲染，游戏会占满 CPU，性能会很差"
)

_vulkan_cache: tuple[float, dict[str, Any]] | None = None


@dataclass(frozen=True)
class PrecheckItem:
    #: acceleration / vulkan / disk / memory
    id: str
    title: str
    #: ``None`` = 这项现在查不了（比如模拟器组件还没装）
    ok: bool | None
    #: 不满足时是否拒绝开机
    blocking: bool
    reason: str
    advice: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def message(self) -> str:
        return f"{self.reason}。{self.advice}" if self.advice else self.reason


# ---- 各项 ------------------------------------------------------------------


def _accel_summary(detail: str) -> str:
    """``-accel-check`` 的输出夹着 ``accel:`` / 返回码 / ``accel`` 这几行框架，只留说明那几行。"""
    lines = [
        line.strip()
        for line in (detail or "").splitlines()
        if line.strip()
        and line.strip() not in ("accel", "accel:")
        and not line.strip().lstrip("-").isdigit()
    ]
    return " ".join(lines) or (detail or "").strip()


_ACCEL_NAME_VERSION = re.compile(r"(\w+)\s*\(([\d.]+)\)")


def _accel_ok_text(summary: str) -> str:
    """可用时的中文说法：``WHPX(10.0.26200) is installed and usable.`` → ``可用（WHPX 10.0.26200）``。
    认不出加速器名和版本就只说「可用」；``-accel-check`` 原文记在调试日志里。"""
    match = _ACCEL_NAME_VERSION.search(summary or "")
    return f"可用（{match.group(1)} {match.group(2)}）" if match else "可用"


async def acceleration_item(root: str | Path) -> PrecheckItem:
    title = "硬件虚拟化"
    if not emulator_exe(root).is_file():
        return PrecheckItem(
            "acceleration", title, None, True, "模拟器组件还没装好，装好后再检查"
        )
    accel = await host.check_acceleration(root)
    summary = _accel_summary(accel.detail)
    logger.debug(f"-accel-check 输出: {summary}")
    if accel.ok:
        return PrecheckItem("acceleration", title, True, True, _accel_ok_text(summary))
    return PrecheckItem(
        "acceleration",
        title,
        False,
        True,
        f"硬件虚拟化（Windows 虚拟机监控程序平台）不可用，官方模拟器无法启动"
        f"（检查结果：{summary or '无输出'}）",
        ACCEL_ADVICE,
    )


def memory_item(memory_mb: int, available_mb: int | None = None) -> PrecheckItem:
    """``memory_mb`` 是这次开机实际要传的 ``-memory``（按游戏自动时也是算好的值）。"""
    if available_mb is None:
        available_mb = psutil.virtual_memory().available // (1024 * 1024)
    needed_mb = int(memory_mb) + HOST_MEMORY_OVERHEAD_MB
    text = (
        f"实例内存 {memory_mb / 1024:.0f} GB，启动约需 {needed_mb / 1024:.1f} GB，"
        f"当前可用 {available_mb / 1024:.1f} GB"
    )
    if available_mb >= needed_mb:
        return PrecheckItem("memory", "内存", True, True, text)
    return PrecheckItem(
        "memory",
        "内存",
        False,
        True,
        f"电脑可用内存不足：{text}",
        "请关闭部分程序，或在实例设置里调小内存",
    )


def _existing_ancestor(path: Path) -> Path:
    current = path
    while not current.exists() and current.parent != current:
        current = current.parent
    return current


def disk_item(root: str | Path, free_bytes: int | None = None) -> PrecheckItem:
    """实例所在盘（``<根>\\avd``）的剩余空间。数据盘稀疏增长，剩得太少开机后会写满。"""
    target = _existing_ancestor(avd_home(root))
    drive = target.anchor or str(target)
    if free_bytes is None:
        try:
            free_bytes = shutil.disk_usage(target).free
        except OSError as e:
            return PrecheckItem(
                "disk", "磁盘", None, True, f"查不了 {drive} 的剩余空间: {e}"
            )
    threshold = MIN_FREE_DISK_GB_TO_BOOT * 1024**3
    text = f"实例所在盘 {drive} 剩余 {free_bytes / 1024**3:.1f} GB"
    if free_bytes >= threshold:
        return PrecheckItem("disk", "磁盘", True, True, text)
    return PrecheckItem(
        "disk",
        "磁盘",
        False,
        True,
        f"{text}，低于开机所需的 {MIN_FREE_DISK_GB_TO_BOOT} GB：数据盘随游戏写入增长，"
        "盘写满时实例数据会损坏",
        f"清理 {drive} 的空间，或把官方模拟器根目录放到空间更大的盘",
    )


async def probe_vulkan(*, use_cache: bool = True) -> dict[str, Any]:
    """在子进程里跑 :mod:`.vulkan_probe`，返回它的 JSON；跑不起来时 ``{"error": ...}``。"""
    global _vulkan_cache
    if (
        use_cache
        and _vulkan_cache is not None
        and time.monotonic() - _vulkan_cache[0] < VULKAN_PROBE_CACHE_SECONDS
    ):
        return _vulkan_cache[1]
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(PROBE_SCRIPT),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:  # noqa: BLE001 - 查不了就如实说查不了
        return {"probeError": f"{type(e).__name__}: {e}"}
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=VULKAN_PROBE_TIMEOUT_SECONDS
        )
    except (asyncio.TimeoutError, TimeoutError):
        if process.returncode is None:
            process.kill()
            await process.wait()
        return {"probeError": f"探测超时（{VULKAN_PROBE_TIMEOUT_SECONDS:.0f} 秒）"}
    lines = [line for line in stdout.decode("utf-8", "replace").splitlines() if line]
    try:
        result = json.loads(lines[-1])
    except (IndexError, ValueError):
        tail = stderr.decode("utf-8", "replace").strip()[-300:]
        return {
            "probeError": f"探测进程退出码 {process.returncode}，没有结果"
            + (f"：{tail}" if tail else "")
        }
    _vulkan_cache = (time.monotonic(), result)
    return result


def vulkan_item_from_probe(result: dict[str, Any]) -> PrecheckItem:
    title = "显卡 Vulkan"
    if "probeError" in result:
        return PrecheckItem(
            "vulkan", title, None, False, f"查不了 Vulkan：{result['probeError']}"
        )
    if not result.get("loaded"):
        return PrecheckItem(
            "vulkan",
            title,
            False,
            False,
            f"这台电脑没有 Vulkan 运行库（vulkan-1.dll 加载失败：{result.get('error') or '未知'}）",
            VULKAN_ADVICE,
        )
    devices = result.get("devices") or []
    if result.get("result") not in (0, None) and not devices:
        return PrecheckItem(
            "vulkan",
            title,
            False,
            False,
            f"没有支持 Vulkan 的显卡驱动（{result.get('error') or 'Vulkan'} 返回 {result.get('result')}）",
            VULKAN_ADVICE,
        )
    hardware = [d for d in devices if d.get("type") != _VK_DEVICE_TYPE_CPU]
    listed = "、".join(
        f"{d.get('name')}（{_VK_DEVICE_TYPE_NAMES.get(d.get('type'), '未知')}，Vulkan {d.get('apiVersion')}）"
        for d in devices
    )
    if hardware:
        return PrecheckItem("vulkan", title, True, False, f"可用显卡：{listed}")
    if devices:
        reason = f"Vulkan 只有软件实现（{listed}），没有可用的显卡"
    else:
        reason = "Vulkan 没有枚举到任何显卡"
    return PrecheckItem("vulkan", title, False, False, reason, VULKAN_ADVICE)


async def vulkan_item(*, use_cache: bool = True) -> PrecheckItem:
    return vulkan_item_from_probe(await probe_vulkan(use_cache=use_cache))


# ---- 汇总 ------------------------------------------------------------------


async def run_prechecks(
    root: str | Path, *, memory_mb: int = DEFAULT_MEMORY_MB
) -> list[PrecheckItem]:
    """四项都查，给 ``/avd/status``。``memory_mb`` 是拿来估内存的实例内存（面板上用默认档）。"""
    accel, vulkan = await asyncio.gather(acceleration_item(root), vulkan_item())
    memory = await asyncio.to_thread(memory_item, memory_mb)
    disk = await asyncio.to_thread(disk_item, root)
    return [accel, vulkan, disk, memory]


class PrecheckFailed(RuntimeError):
    """开机前检查有拦截项不满足。"""

    def __init__(self, item: PrecheckItem):
        super().__init__(item.message())
        self.item = item


async def check_before_launch(root: str | Path, memory_mb: int) -> list[PrecheckItem]:
    """开机前检查：硬件虚拟化、内存、磁盘不满足抛 :class:`PrecheckFailed`（带原因与建议）；
    Vulkan 不满足只记警告。返回全部结果。``memory_mb`` 必须是这次要传给 ``-memory`` 的值。"""
    items = [
        await acceleration_item(root),
        await asyncio.to_thread(memory_item, memory_mb),
        await asyncio.to_thread(disk_item, root),
    ]
    for item in items:
        # 组件没装（ok=None）由组件完整性检查先拦下，这里只拦明确不满足的
        if item.blocking and item.ok is False:
            raise PrecheckFailed(item)
    vulkan = await vulkan_item()
    if vulkan.ok is False:
        logger.warning(f"官方模拟器开机前检查：{vulkan.message()}")
    items.append(vulkan)
    logger.info(
        "官方模拟器开机前检查："
        + "；".join(
            f"{item.title}{'通过' if item.ok else '未通过' if item.ok is False else '未查'}"
            f"（{item.reason}）"
            for item in items
        )
    )
    return items


__all__ = [
    "PrecheckFailed",
    "PrecheckItem",
    "acceleration_item",
    "check_before_launch",
    "disk_item",
    "memory_item",
    "probe_vulkan",
    "run_prechecks",
    "vulkan_item",
    "vulkan_item_from_probe",
]
