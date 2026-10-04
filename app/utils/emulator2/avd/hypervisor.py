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

"""「Windows 虚拟机监控程序平台」：判断硬件虚拟化不可用的原因，以及用户点按钮后提权开启它。

**判断原因。** ``emulator -accel-check`` 不可用时只说一句 ``WHPX is either not available or not
installed.``（emulator-check.exe 里的原文），分不出是系统功能没开还是 BIOS 里没开虚拟化。所以再问一次
CPU：``IsProcessorFeaturePresent(PF_VIRT_FIRMWARE_ENABLED)`` 为真说明固件里开着虚拟化（10-04 本机 WHPX
可用时也为真），那就只差这个系统功能；为假时分不清（BIOS 没开，或别的虚拟机监控程序让它读不准），
按钮照样给，说明里把两种可能都写上。

**开启。** 只在用户点了按钮之后执行
``dism /online /enable-feature /featurename:HypervisorPlatform /all /norestart``。后端已经是管理员进程时
（正式版前端是 ``requireAdministrator``，后端随它提权）直接跑，不会有任何确认框；不是管理员时用
``runas`` 提权，会弹系统确认框由用户确认。不自动重启，完成后只告诉用户要重启。
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from app.utils import get_logger

logger = get_logger("魔改 AVD 虚拟化")

#: 前置检查里硬件虚拟化一项挂的动作：前端据此显示「开启」按钮。
ENABLE_ACTION = "enable_hypervisor_platform"
#: 写全路径：不按 PATH 找，免得同名程序被当成 dism 以管理员身份跑起来。
DISM_EXE = os.path.join(
    os.environ.get("SystemRoot", r"C:\Windows"), "System32", "dism.exe"
)
DISM_ARGS = "/online /enable-feature /featurename:HypervisorPlatform /all /norestart"
#: dism 的返回码：0 成功；3010 成功但要重启（``ERROR_SUCCESS_REBOOT_REQUIRED``）。
_DISM_OK = 0
_DISM_REBOOT = 3010
#: UAC 弹窗里点了「否」。
_ERROR_CANCELLED = 1223
#: ``IsProcessorFeaturePresent`` 的 ``PF_VIRT_FIRMWARE_ENABLED``。
_PF_VIRT_FIRMWARE_ENABLED = 21

AccelCause = Literal["feature_off", "unknown"]


def firmware_virtualization_enabled() -> bool:
    """固件里开着 CPU 虚拟化。读不到按 ``False``。"""
    if sys.platform != "win32":
        return False
    try:
        return bool(
            ctypes.windll.kernel32.IsProcessorFeaturePresent(_PF_VIRT_FIRMWARE_ENABLED)
        )
    except Exception:  # noqa: BLE001 - 读不到就当分不清
        return False


def classify_accel_failure(
    firmware_enabled: Callable[[], bool] = firmware_virtualization_enabled,
) -> AccelCause:
    """硬件虚拟化不可用时的原因：``feature_off`` 只差系统功能；``unknown`` 分不清（也可能是 BIOS）。"""
    return "feature_off" if firmware_enabled() else "unknown"


def is_elevated() -> bool:
    """当前进程是不是管理员进程（提权过）。读不到按 ``False``。"""
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001 - 读不到就按没提权，最多多弹一次确认框
        return False


def enable_hint(elevated: bool | None = None) -> str:
    """「开启」按钮旁的说法：已经是管理员进程就不会有确认框，没提权才会弹。"""
    if is_elevated() if elevated is None else elevated:
        return "点「开启」，将以管理员身份开启，完成后需要重启电脑。"
    return "点「开启」，可能会弹出系统确认框，点「是」，完成后需要重启电脑。"


@dataclass(frozen=True)
class EnableResult:
    ok: bool
    #: enabled 已开启（要重启）/ cancelled 用户在 UAC 里取消 / failed 失败
    reason: Literal["enabled", "cancelled", "failed"]
    message: str
    exit_code: int | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "restartRequired": self.ok,
            "message": self.message,
            "exitCode": self.exit_code,
        }


class ElevationCancelled(Exception):
    """用户在 UAC 弹窗里取消了。"""


def _run_elevated(program: str, parameters: str) -> int:
    """提权运行并等它结束，返回退出码。UAC 被取消抛 :class:`ElevationCancelled`。"""
    import pythoncom
    import pywintypes
    import win32con
    import win32event
    import win32process
    from win32com.shell import shell, shellcon

    # ShellExecuteEx 要求调用线程初始化过 COM（这里跑在 to_thread 的工作线程里）
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    try:
        try:
            info = shell.ShellExecuteEx(
                fMask=shellcon.SEE_MASK_NOCLOSEPROCESS,
                lpVerb="runas",
                lpFile=program,
                lpParameters=parameters,
                nShow=win32con.SW_HIDE,
            )
        except pywintypes.error as e:
            if e.winerror == _ERROR_CANCELLED:
                raise ElevationCancelled() from e
            raise
        handle = info["hProcess"]
        try:
            win32event.WaitForSingleObject(handle, win32event.INFINITE)
            return int(win32process.GetExitCodeProcess(handle))
        finally:
            handle.Close()
    finally:
        pythoncom.CoUninitialize()


def _run_direct(program: str, parameters: str) -> int:
    """已经是管理员进程：直接跑并等它结束，返回退出码。不弹窗口。"""
    completed = subprocess.run(
        [program, *parameters.split()],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    return int(completed.returncode)


def enable_hypervisor_platform(
    runner: Callable[[str, str], int] | None = None,
    *,
    elevated: bool | None = None,
) -> EnableResult:
    """开启「Windows 虚拟机监控程序平台」。同步阻塞到 dism 结束，调用方放线程里跑。

    已经是管理员进程时直接跑 dism（不会有确认框），否则 ``runas`` 提权（会弹系统确认框）。
    ``runner(程序, 参数) -> 退出码`` 与 ``elevated`` 只给测试换成假对象。"""
    elevated = is_elevated() if elevated is None else elevated
    run = runner or (_run_direct if elevated else _run_elevated)
    logger.info(
        f"用户要求开启 Windows 虚拟机监控程序平台（{'已是管理员，直接执行' if elevated else '提权执行'}）: "
        f"{DISM_EXE} {DISM_ARGS}"
    )
    try:
        code = run(DISM_EXE, DISM_ARGS)
    except ElevationCancelled:
        logger.info("开启 Windows 虚拟机监控程序平台：用户在 UAC 里取消了")
        return EnableResult(False, "cancelled", "已取消，没有改动系统设置")
    except Exception as e:  # noqa: BLE001 - 原因交给界面
        logger.warning(f"开启 Windows 虚拟机监控程序平台失败: {e}")
        return EnableResult(False, "failed", f"开启失败: {e}")
    if code in (_DISM_OK, _DISM_REBOOT):
        logger.info(
            f"Windows 虚拟机监控程序平台已开启（dism 返回 {code}），重启电脑后生效"
        )
        return EnableResult(
            True,
            "enabled",
            "已开启「Windows 虚拟机监控程序平台」，重启电脑后生效",
            code,
        )
    logger.warning(f"开启 Windows 虚拟机监控程序平台失败：dism 返回 {code}")
    return EnableResult(
        False,
        "failed",
        f"开启失败（dism 返回 {code}），可以在「启用或关闭 Windows 功能」里手动勾选",
        code,
    )


__all__ = [
    "ENABLE_ACTION",
    "EnableResult",
    "classify_accel_failure",
    "enable_hint",
    "enable_hypervisor_platform",
    "firmware_virtualization_enabled",
    "is_elevated",
]
