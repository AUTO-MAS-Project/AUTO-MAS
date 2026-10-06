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

"""雷电 VBox 服务卡住的识别与自愈。

**故障形态**（2026-09-12 生产实测）。雷电 9 / 14 共用 ``C:\\Program Files\\ldplayer9box\\``
里的 VirtualBox 运行时，其中 ``Ld9BoxSVC.exe`` 是整机唯一的 COM 服务，每台实例的虚拟机
``Ld9BoxHeadless.exe`` 都由它拉起。它卡住之后，**已经在跑的实例不受影响，新实例却一台都
起不来**：``ldconsole launch`` 正常返回，播放器窗口也开了，``list2`` 里却一直是
``VBox pid = -1``、adb 永远看不到 ``emulator-NNNN``。更坏的一种是「Android 已启动」标志
照样置 1，MAS 以为它在线，MAA 一连就报 ADB 异常，三轮重试三轮都是同一个结果。

雷电自己的修复工具最终做的也只是重启这个服务（修复前后安装目录没有任何文件变化），
但它是纯图形程序、没有命令行开关，MAS 调不动，只能自己做同样的事。

**必须守住的一条**：``Ld9BoxSVC.exe`` 一死，它名下所有虚拟机一起死。当天的修复就把另一
台正在跑的实例打成了僵尸窗口。所以只有整机没有任何 ``Ld9BoxHeadless.exe`` 在跑时才允许
重启服务，否则宁可报错让用户自己决定。

**第二种故障：修复工具把运行时修残**（同日实测）。用户在实例还开着时点「修复」，修复工具
走「全量重装」：删 ``ldplayer9box`` 时被占用的文件删不掉，往 Program Files 解压又失败
（``unzip vbox error = 1015``），退而解压到 ``<雷电目录>\vbox\``——但 COM 注册和 dnplayer
仍从 ``ldplayer9box`` 拉虚拟机。结果那里只剩删不掉的核心文件，缺了 ``libOpenglRender2.dll``
``fastpipe2.dll`` ``GLES_V2.dll`` 这一整套 GPU 库：VBox.log ``fastpipe: load host failed err=126``，
客户机一开始画图 ``Ld9BoxHeadless.exe`` 就以 ``0x80000003`` 中止，MAS 这边看到的又是 ADB 异常。
运行时里缺的文件雷电自己的安装目录都有（``vbox64\`` 随安装自带，``vbox\`` 是修复工具解压
出来的），启动前查一眼、缺了就补回去，只补不覆盖。
"""

import asyncio
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import psutil

from app.utils import get_logger
from app.utils.platform import IS_WINDOWS

logger = get_logger("Emulator2 雷电 VBox 自愈")

#: 整机共用的 VBox COM 服务；杀它等于关掉所有雷电虚拟机。
VBOX_SERVICE_PROCESS = "Ld9BoxSVC.exe"
#: 每台实例一个的虚拟机进程。
VBOX_VM_PROCESS = "Ld9BoxHeadless.exe"

#: 等服务进程退出的上限。它退得很快，等不到多半是没权限杀。
_SERVICE_EXIT_TIMEOUT = 10.0

#: VBox COM 服务的 CLSID；它的 LocalServer32 指向哪个目录，dnplayer 就从哪个目录拉虚拟机。
VBOX_SERVICE_CLSID = "{20191216-47b9-4a1e-82b2-07ccd5323c3f}"
#: 注册表读不到时的默认安装位置。
VBOX_RUNTIME_DEFAULT_DIR = (
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "ldplayer9box"
)
#: 运行时残缺的判据：fastpipe 在客户机画第一帧前要从运行时目录加载的宿主库。
#: 缺任意一个，虚拟机都会在启动后几秒到几十秒内中止。
VBOX_RUNTIME_SENTINELS = (
    "libOpenglRender2.dll",
    "host_manager2.dll",
    "fastpipe2.dll",
    "GLES_V2.dll",
)
#: 雷电安装目录下能拿来补文件的来源，按优先级：``vbox`` 是修复工具解压出的完整运行时
#: （只在修复过之后才有），``vbox64`` 随安装自带、只有 GPU 那一套。
VBOX_RUNTIME_SOURCE_DIRS = ("vbox", "vbox64")


@dataclass(frozen=True)
class VmProbe:
    """一次「虚拟机到底在不在」的探测输入，全部来自 ``list2`` 和 ``adb devices``。"""

    in_android: int
    vbox_pid: int
    serial_online: bool


def vm_is_missing(probe: VmProbe) -> bool:
    """播放器窗口在、VBox 进程不在、adb 也看不到——虚拟机没起来或已经死了。

    三个条件缺一不可：

    - ``in_android == 0`` 是根本没开，不是这里要管的
    - ``vbox_pid > 0`` 说明虚拟机进程在，哪怕 adb 暂时没核上也只是还没就绪
    - adb 能核上说明虚拟机活着；``list2`` 那列在个别版本上可能不可靠，靠 adb 兜底
    """
    if probe.in_android == 0:
        return False
    if probe.vbox_pid > 0:
        return False
    return not probe.serial_online


def _processes_named(name: str) -> list[psutil.Process]:
    wanted = name.casefold()
    found = []
    for proc in psutil.process_iter(["name"]):
        try:
            if (proc.info["name"] or "").casefold() == wanted:
                found.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return found


def live_vm_pids() -> list[int]:
    """整机上还在跑的雷电虚拟机进程。不为空就绝不能重启服务。"""
    return [proc.pid for proc in _processes_named(VBOX_VM_PROCESS)]


async def restart_vbox_service() -> bool:
    """杀掉 ``Ld9BoxSVC.exe`` 并等它退出；下一次 ``launch`` 会由雷电自己重新拉起服务。

    返回是否真的杀了一个。没找到进程返回 ``False``（服务本来就没在跑，不算失败）；
    没权限杀直接抛 ``PermissionError``——调用方要把它翻译成给用户看的话。
    """
    targets = _processes_named(VBOX_SERVICE_PROCESS)
    if not targets:
        logger.info(f"{VBOX_SERVICE_PROCESS} 没有在运行，无需重启")
        return False

    for proc in targets:
        try:
            proc.kill()
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied as e:
            raise PermissionError(
                f"没有权限结束 {VBOX_SERVICE_PROCESS}（pid {proc.pid}）"
            ) from e

    def _wait() -> None:
        psutil.wait_procs(targets, timeout=_SERVICE_EXIT_TIMEOUT)

    await asyncio.to_thread(_wait)
    survivors = [proc.pid for proc in targets if proc.is_running()]
    if survivors:
        raise RuntimeError(f"{VBOX_SERVICE_PROCESS} 结束后仍未退出: {survivors}")
    logger.warning(
        f"已结束 {VBOX_SERVICE_PROCESS}（pid {[p.pid for p in targets]}），"
        "下一次启动实例时由雷电重新拉起"
    )
    return True


# ---- 运行时残缺 ---------------------------------------------------------------


def resolve_vbox_runtime_dir() -> Path | None:
    """VBox 运行时目录：按 COM 注册的 LocalServer32 找，读不到退回默认安装位置。

    非 Windows 直接返回 ``None``（没有雷电）。目录不存在也返回 ``None``——没装过就没法判残缺。
    """
    if not IS_WINDOWS:
        return None
    candidate: Path | None = None
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT, rf"CLSID\{VBOX_SERVICE_CLSID}\LocalServer32"
        ) as key:
            value, _ = winreg.QueryValueEx(key, "")
        text = str(value).strip().strip('"')
        if text:
            candidate = Path(text).parent
    except OSError:
        candidate = None
    if candidate is None or not candidate.is_dir():
        candidate = VBOX_RUNTIME_DEFAULT_DIR
    return candidate if candidate.is_dir() else None


def missing_runtime_sentinels(runtime_dir: Path) -> list[str]:
    """运行时目录里缺了哪些哨兵文件；空列表就是完整。"""
    return [
        name for name in VBOX_RUNTIME_SENTINELS if not (runtime_dir / name).is_file()
    ]


def complete_vbox_runtime(runtime_dir: Path, install_dir: Path) -> list[str]:
    """把雷电安装目录里有、运行时目录里没有的文件补过去，返回补上的相对路径。

    **只补不覆盖**：运行时里已有的文件一个不碰（在跑的虚拟机正映射着它们）。
    没权限写运行时目录时抛 ``PermissionError``，由调用方翻译成给用户的话。
    """
    copied: list[str] = []
    for source_name in VBOX_RUNTIME_SOURCE_DIRS:
        source = install_dir / source_name
        if not source.is_dir():
            continue
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source)
            target = runtime_dir / relative
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            copied.append(str(relative))
    return copied
