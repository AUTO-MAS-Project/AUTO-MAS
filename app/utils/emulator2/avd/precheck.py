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

"""魔改 AVD 开机前的电脑检查：目录路径、模拟器版本、硬件虚拟化、显卡 Vulkan、磁盘、内存。

每项给 ``ok``、原因、建议，``/avd/status`` 原样交给前端显示；开机路径（``AvdInstanceManager._launch``）
里不满足的拦截项直接拒绝开机并给出原因，不静默开下去。只读：不改系统设置、不装任何东西。

- **目录路径**：根目录路径不能有中文等非 ASCII 字符（模拟器和 qemu 对这类路径不可靠），空格不拦。拦截。
- **模拟器版本**：只支持魔改 AVD 内测包里的自编版（``components.emulator_self_built``），谷歌原版
  与没有模拟器都拒绝。拦截。
- **硬件虚拟化**：``emulator -accel-check``（WHPX）。拦截。不可用时带上「开启」动作，用户点了才由
  :mod:`.hypervisor` 提权开启系统功能；这里只判断原因，不执行。
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

from . import host, hypervisor
from .components import (
    avd_home,
    emulator_exe,
    emulator_present,
    emulator_self_built,
    read_emulator_version,
)
from .constants import (
    DEFAULT_MEMORY_MB,
    HOST_MEMORY_OVERHEAD_MB,
    MIN_FREE_DISK_GB_TO_BOOT,
    VULKAN_PROBE_CACHE_SECONDS,
    VULKAN_PROBE_TIMEOUT_CACHE_SECONDS,
    VULKAN_PROBE_TIMEOUT_SECONDS,
)

logger = get_logger("魔改 AVD 电脑检查")

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

#: 硬件虚拟化不可用、但 CPU 说固件里虚拟化开着：只差系统功能。
ACCEL_ADVICE_FEATURE_OFF = (
    "点「开启」，在弹出的系统确认框里点「是」，完成后重启电脑。"
    "也可以在「启用或关闭 Windows 功能」里手动勾选「Windows 虚拟机监控程序平台」"
)
#: 分不清是系统功能没开还是 BIOS 里没开虚拟化：两种都说。
ACCEL_ADVICE_UNKNOWN = (
    "可能是「Windows 虚拟机监控程序平台」没有开启：点「开启」，完成后重启电脑。"
    "重启后仍不可用的话，是 BIOS / UEFI 里没打开 CPU 虚拟化（Intel VT-x / AMD SVM，"
    "常叫 Virtualization Technology），要进 BIOS 打开"
)
VULKAN_ADVICE = (
    "安装或更新显卡驱动（NVIDIA / AMD / Intel 官网驱动自带 Vulkan）。没有可用的显卡时模拟器只能"
    "软件渲染，游戏会占满 CPU，性能会很差"
)

#: Vulkan 探测缓存：`(过期时刻 monotonic, 结果)`，过期时长按结果定（见 :func:_remember_vulkan）
_vulkan_cache: tuple[float, dict[str, Any]] | None = None


@dataclass(frozen=True)
class PrecheckItem:
    #: path / emulator / acceleration / vulkan / disk / memory
    id: str
    title: str
    #: ``None`` = 这项现在查不了（比如模拟器组件还没装）
    ok: bool | None
    #: 不满足时是否拒绝开机
    blocking: bool
    reason: str
    advice: str = ""
    #: 界面上可以一键处理的动作（目前只有 :data:`~.hypervisor.ENABLE_ACTION`），没有为空
    action: str = ""

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


async def acceleration_item(
    root: str | Path, *, use_cache: bool = True
) -> PrecheckItem:
    title = "硬件虚拟化"
    if not emulator_exe(root).is_file():
        return PrecheckItem(
            "acceleration", title, None, True, "模拟器组件还没装好，装好后再检查"
        )
    accel = await host.check_acceleration(root, use_cache=use_cache)
    summary = _accel_summary(accel.detail)
    logger.debug(f"-accel-check 输出: {summary}")
    if accel.ok:
        return PrecheckItem("acceleration", title, True, True, _accel_ok_text(summary))
    checked = f"（检查结果：{summary or '无输出'}）"
    # -accel-check 只说 WHPX 不可用，分不出原因；再问一次 CPU 固件里虚拟化开没开
    if await asyncio.to_thread(hypervisor.classify_accel_failure) == "feature_off":
        return PrecheckItem(
            "acceleration",
            title,
            False,
            True,
            f"「Windows 虚拟机监控程序平台」没有开启，魔改 AVD 无法启动{checked}",
            ACCEL_ADVICE_FEATURE_OFF,
            hypervisor.ENABLE_ACTION,
        )
    return PrecheckItem(
        "acceleration",
        title,
        False,
        True,
        f"硬件虚拟化（Windows 虚拟机监控程序平台）不可用，魔改 AVD 无法启动{checked}",
        ACCEL_ADVICE_UNKNOWN,
        hypervisor.ENABLE_ACTION,
    )


TEST_PACKAGE_ADVICE = (
    "请把魔改 AVD 内测包解压到这个目录（解压后目录里应有 sdk\\emulator）"
)


def emulator_item(root: str | Path) -> PrecheckItem:
    """模拟器必须是魔改 AVD 内测包里的自编版（用户定：不支持谷歌原版）。拦截。"""
    title = "模拟器版本"
    if not emulator_present(root):
        return PrecheckItem(
            "emulator",
            title,
            False,
            True,
            "这个目录里还没有魔改 AVD 内测包",
            TEST_PACKAGE_ADVICE,
        )
    version = read_emulator_version(root) or "版本未知"
    if emulator_self_built(root):
        return PrecheckItem("emulator", title, True, True, f"内测包（{version}）")
    return PrecheckItem(
        "emulator",
        title,
        False,
        True,
        f"这里的模拟器（{version}）不是魔改 AVD 内测包里的版本，只支持内测包",
        TEST_PACKAGE_ADVICE,
    )


def path_item(root: str | Path) -> PrecheckItem:
    """根目录路径不能有非 ASCII 字符（中文等）：模拟器和 qemu 对这类路径不可靠。拦截。空格不拦。"""
    text = str(Path(root))
    if text.isascii():
        return PrecheckItem("path", "目录路径", True, True, text)
    return PrecheckItem(
        "path",
        "目录路径",
        False,
        True,
        f"模拟器目录路径里有中文等非英文字符（{text}），模拟器在这类路径下不可靠",
        "把模拟器目录放到不含中文的路径下，再重新添加",
    )


def memory_item(memory_mb: int, available_mb: int | None = None) -> PrecheckItem:
    """``memory_mb`` 是这次开机实际要传的 ``-memory``（实例自己设的内存）。"""
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
        f"清理 {drive} 的空间，或把魔改 AVD 根目录放到空间更大的盘",
    )


def _remember_vulkan(result: dict[str, Any], *, timed_out: bool = False) -> None:
    """按结果决定缓存多久：可用的缓存 :data:`~.constants.VULKAN_PROBE_CACHE_SECONDS`；探测超时的短时
    缓存 :data:`~.constants.VULKAN_PROBE_TIMEOUT_CACHE_SECONDS`（驱动挂住时不必每次查状态、每次开机
    都等满超时）；「没有 Vulkan」与其它查不了的不缓存，用户装好驱动后再查马上就能看到。"""
    global _vulkan_cache
    if timed_out:
        ttl = VULKAN_PROBE_TIMEOUT_CACHE_SECONDS
    elif vulkan_item_from_probe(result).ok is True:
        ttl = VULKAN_PROBE_CACHE_SECONDS
    else:
        _vulkan_cache = None
        return
    _vulkan_cache = (time.monotonic() + ttl, result)


async def probe_vulkan(*, use_cache: bool = True) -> dict[str, Any]:
    """在子进程里跑 :mod:`.vulkan_probe`，返回它的 JSON；跑不起来时 ``{"probeError": ...}``。

    ``use_cache=False``（用户点「检查」）跳过缓存重新探测。"""
    if use_cache and _vulkan_cache is not None and time.monotonic() < _vulkan_cache[0]:
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
        result = {"probeError": f"探测超时（{VULKAN_PROBE_TIMEOUT_SECONDS:.0f} 秒）"}
        _remember_vulkan(result, timed_out=True)
        return result
    lines = [line for line in stdout.decode("utf-8", "replace").splitlines() if line]
    try:
        result = json.loads(lines[-1])
    except (IndexError, ValueError):
        tail = stderr.decode("utf-8", "replace").strip()[-300:]
        return {
            "probeError": f"探测进程退出码 {process.returncode}，没有结果"
            + (f"：{tail}" if tail else "")
        }
    _remember_vulkan(result)
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
    root: str | Path, *, memory_mb: int = DEFAULT_MEMORY_MB, refresh: bool = False
) -> list[PrecheckItem]:
    """六项都查，给 ``/avd/status``。``memory_mb`` 是拿来估内存的实例内存（面板上用默认档）；
    ``refresh``（用户点「检查」）时硬件加速与 Vulkan 都跳过缓存重新查。"""
    accel, vulkan = await asyncio.gather(
        acceleration_item(root, use_cache=not refresh),
        vulkan_item(use_cache=not refresh),
    )
    emulator = await asyncio.to_thread(emulator_item, root)
    memory = await asyncio.to_thread(memory_item, memory_mb)
    disk = await asyncio.to_thread(disk_item, root)
    return [path_item(root), emulator, accel, vulkan, disk, memory]


class PrecheckFailed(RuntimeError):
    """开机前检查有拦截项不满足。"""

    def __init__(self, item: PrecheckItem):
        super().__init__(item.message())
        self.item = item


async def check_before_launch(root: str | Path, memory_mb: int) -> list[PrecheckItem]:
    """开机前检查：目录路径有非 ASCII 字符、模拟器不是内测包的自编版、硬件虚拟化、内存、磁盘不满足抛 :class:`PrecheckFailed`（带原因与建议）；
    Vulkan 不满足只记警告。返回全部结果。``memory_mb`` 必须是这次要传给 ``-memory`` 的值。"""
    items = [
        path_item(root),
        await asyncio.to_thread(emulator_item, root),
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
        logger.warning(f"魔改 AVD 开机前检查：{vulkan.message()}")
    items.append(vulkan)
    logger.info(
        "魔改 AVD 开机前检查："
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
