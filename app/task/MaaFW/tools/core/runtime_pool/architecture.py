"""本机架构的唯一判定来源，以及 MFW 选包时各外部约定的写法。

MFW 里凡是和本机架构有关的选择（Mirror 酱的 arch、GitHub 资产、wheel 平台标签、
uv 装哪种解释器、运行池身份）都从这里取。MFW 目前只适配 x64：别的架构（含 32 位）
一律给「MaaFW 目前只支持 x64」，不悄悄按 x64 去选包。

只用标准库，放在运行池这一层是为了让 runtime_pool / project_update 能在模块层导入；
``runner.environment`` 原样转出这里的公开名字。
"""

from __future__ import annotations

import platform as platform_module
import struct
import sysconfig
from dataclasses import dataclass

# .NET RID 架构段的各种写法 -> ``host_architecture()`` 的取值。发行包用的是 .NET 的
# 规范写法（win-x64 / win-arm64），别名兜住 Python 与 Linux 的叫法。
RID_ARCHITECTURE_ALIASES = {
    "x64": "x64",
    "amd64": "x64",
    "x86_64": "x64",
    "arm64": "arm64",
    "aarch64": "arm64",
    "x86": "x86",
    "i386": "x86",
    "i686": "x86",
}


def architecture_from_build_platform(build_platform: str | None) -> str | None:
    """解释器构建平台（``sysconfig.get_platform()``）→ ``host_architecture()`` 的取值。

    ``win-amd64`` → x64、``win-arm64`` → arm64、``win32``（32 位 Windows 构建）→ x86；
    ``universal2`` 这类看不出架构的给 None。运行池解释器在另一个进程里，只能拿它探针
    报回来的构建平台走同一张表。
    """

    text = str(build_platform or "").strip().casefold()
    if text == "win32":
        return "x86"
    return RID_ARCHITECTURE_ALIASES.get(text.rpartition("-")[2])


def host_architecture() -> str:
    """当前解释器进程的架构（DLL 由本进程加载，要的是进程而不是系统的架构）。

    按解释器的构建平台判断（``sysconfig.get_platform()``：``win-amd64`` / ``win-arm64``
    / ``linux-x86_64`` / ``linux-aarch64``）。不能看 ``platform.machine()``：3.12 在
    Windows 上先问 WMI 的 CPU 架构，arm64 机器上仿真跑的 x64 解释器会得到 ARM64。
    构建平台看不出架构时（macOS 的 ``universal2``）才退回 ``platform.machine()``。
    """

    if struct.calcsize("P") != 8:
        return "x86"
    architecture = architecture_from_build_platform(sysconfig.get_platform())
    if architecture is not None:
        return architecture
    machine = platform_module.machine().casefold()
    return "arm64" if "arm" in machine or "aarch" in machine else "x64"


#: MFW 目前只适配 x64。非 x64 的进程 / 运行池解释器一律按「不支持」提示，不按 x64 去选包。
SUPPORTED_ARCHITECTURE = "x64"
#: 「只支持 x64」提示里一定有它；也在 ``runner.environment.ARCHITECTURE_MISMATCH_MARKERS``
#: 里，宿主据此不重试。
UNSUPPORTED_ARCHITECTURE_MARKER = "MaaFW 目前只支持 x64"


class MaaFWUnsupportedArchitectureError(RuntimeError):
    """本机进程或运行池解释器不是 x64。文案面向用户，调用方原样带出。"""


@dataclass(frozen=True)
class ArchitectureTarget:
    """一种受支持架构在各外部约定里的写法。"""

    #: Mirror 酱 ``/latest`` 的 ``os`` / ``arch`` 参数。
    mirrorchyan_os: str
    mirrorchyan_arch: str
    #: GitHub Release 资产名里的架构段（多个 zip 时按它收窄）。
    github_asset_pattern: str
    #: 官方 maafw wheel 的平台标签。
    wheel_platform: str
    #: uv 的 python request 里 ``<os>-<arch>-<libc>`` 那一段。
    uv_python_platform: str
    #: 便携版缺 uv 时提示用户下载的 uv 发行包名。
    uv_release_asset: str


_ARCHITECTURE_TARGETS = {
    "x64": ArchitectureTarget(
        mirrorchyan_os="win",
        mirrorchyan_arch="x86_64",
        github_asset_pattern=r"(?<![a-z0-9])(?:x86[-_]?64|x64|amd64)(?![a-z0-9])",
        wheel_platform="win_amd64",
        uv_python_platform="windows-x86_64-none",
        uv_release_asset="uv-x86_64-pc-windows-msvc.zip",
    ),
}


def describe_unsupported_architecture(
    architecture: str | None = None, *, subject: str = "本机进程"
) -> str | None:
    """架构不是 x64 时的提示（``architecture`` 缺省取 :func:`host_architecture`）；是 x64 时 None。"""

    actual = architecture if architecture is not None else host_architecture()
    if actual == SUPPORTED_ARCHITECTURE:
        return None
    return f"{UNSUPPORTED_ARCHITECTURE_MARKER}（{subject}是 {actual or '未知架构'}）"


def supported_architecture_target(
    architecture: str | None = None, *, subject: str = "本机进程"
) -> ArchitectureTarget:
    """本机（或给定架构）对应的选包参数；不是 x64 时抛 :class:`MaaFWUnsupportedArchitectureError`。"""

    actual = architecture if architecture is not None else host_architecture()
    message = describe_unsupported_architecture(actual, subject=subject)
    if message is not None:
        raise MaaFWUnsupportedArchitectureError(message)
    return _ARCHITECTURE_TARGETS[actual]


# 运行池身份的 architecture 字段沿用 Windows 上 ``platform.machine()`` 的写法。
_WINDOWS_MACHINE_NAMES = {"x64": "AMD64", "arm64": "ARM64", "x86": "x86"}


def runtime_identity_architecture(build_platform: str | None, machine: str) -> str:
    """运行池身份（runtimeId 的输入）里的 ``architecture``：按解释器的构建平台取。

    写法沿用 Windows 上的 ``platform.machine()``（``AMD64`` / ``ARM64``），所以 x64 上与
    改之前逐字相同、已有运行池的 runtimeId 不变；arm64 机器上仿真跑的 x64 解释器记成
    AMD64 而不是 ARM64。不是 Windows 构建、或构建平台看不出架构时原样用 ``machine``。
    """

    text = str(build_platform or "").strip().casefold()
    architecture = architecture_from_build_platform(text)
    if text.startswith("win") and architecture in _WINDOWS_MACHINE_NAMES:
        return _WINDOWS_MACHINE_NAMES[architecture]
    return str(machine or "").strip() or "unknown"


__all__ = [
    "RID_ARCHITECTURE_ALIASES",
    "SUPPORTED_ARCHITECTURE",
    "UNSUPPORTED_ARCHITECTURE_MARKER",
    "ArchitectureTarget",
    "MaaFWUnsupportedArchitectureError",
    "architecture_from_build_platform",
    "describe_unsupported_architecture",
    "host_architecture",
    "runtime_identity_architecture",
    "supported_architecture_target",
]
