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

"""官方模拟器（Android Emulator）后端的固定参数。

版本一律写死：官方仓库每隔几周就出新模拟器，自动追最新等于让用户替我们做兼容性测试。
以后要升级，改这里的常量并重新实测一遍（预研文档记录的就是这组版本）。
"""

from dataclasses import dataclass

#: 端口段：原生索引 i → 控制台 ``20000 + 10*i``，adb ``+1``，gRPC ``+2``。
#: 整段 20000–20100 由用户指定，避开雷电（5554 起）和 MuMu（16384 起）。
PORT_BASE = 20000
PORT_STEP = 10
#: 所有官方模拟器实例共用的私有 adb server。模拟器只向它注册，**永远不碰 5037**：
#: 5037 是雷电 / MuMu / 生产 MAA 在用的，不同版本的 adb 抢 5037 会互相杀 server。
ADB_SERVER_PORT = 20050
#: 原生索引上限。i=5 的端口段 20050–20052 正好压在私有 adb server 上，不能用。
MAX_NATIVE_INDEX = 9
RESERVED_NATIVE_INDEXES = frozenset({5})

#: AVD 名 = ``mas_<原生索引>``，枚举靠扫 ``avd\\mas_*.ini``。
AVD_NAME_PREFIX = "mas_"

#: 根目录布局。
SDK_DIR = "sdk"
AVD_DIR = "avd"
DOWNLOADS_DIR = "downloads"
COMPONENTS_DIR = "components"
MUMU_SHIM_DIR = "mumu-shim"
METADATA_FILE = "mas-avd.json"


def console_port(native_index: int | str) -> int:
    return PORT_BASE + PORT_STEP * int(native_index)


def adb_port(native_index: int | str) -> int:
    return console_port(native_index) + 1


def grpc_port(native_index: int | str) -> int:
    return console_port(native_index) + 2


def avd_name(native_index: int | str) -> str:
    return f"{AVD_NAME_PREFIX}{int(native_index)}"


def valid_native_index(native_index: int) -> bool:
    return (
        0 <= native_index <= MAX_NATIVE_INDEX
        and native_index not in RESERVED_NATIVE_INDEXES
    )


# ---- 下载源 ---------------------------------------------------------------


@dataclass(frozen=True)
class DownloadSource:
    """一个 SDK 仓库镜像。三家的目录结构已实测一致（09-26）。"""

    id: str
    name: str
    root: str


DOWNLOAD_SOURCES: tuple[DownloadSource, ...] = (
    DownloadSource(
        "googledownloads_cn",
        "Google 中国下载（googledownloads.cn）",
        "https://googledownloads.cn/android/repository/",
    ),
    DownloadSource(
        "tencent",
        "腾讯云镜像",
        "https://mirrors.cloud.tencent.com/AndroidSDK/",
    ),
    DownloadSource(
        "google",
        "Google 官方（dl.google.com）",
        "https://dl.google.com/android/repository/",
    ),
)

#: 许可证全文所在的清单（``<license id="android-sdk-license">``）。
LICENSE_MANIFEST = "repository2-3.xml"
LICENSE_ID = "android-sdk-license"


# ---- 组件 -----------------------------------------------------------------


@dataclass(frozen=True)
class Component:
    """一个要下载的组件。

    ``target`` 是解压后在 ``sdk\\`` 下的目录，``archive_root`` 是压缩包里的顶层目录——
    系统镜像包里顶层叫 ``x86_64``，要落到 ``system-images\\android-34\\google_apis\\x86_64``。
    ``source_properties`` 是包里缺这个文件时补写的内容（模拟器靠它认版本）。
    """

    id: str
    name: str
    version: str
    url: str
    size: int
    sha1: str
    target: str
    archive_root: str
    source_properties: str
    license: str = "Apache-2.0 / Android SDK License"


EMULATOR = Component(
    id="emulator",
    name="Android 模拟器（emulator）",
    version="37.1.11",
    url="emulator-windows_x64-15917651.zip",
    size=441_926_448,
    sha1="54fa750822ff462d57e04fc8e98e60f08df2bb61",
    target="emulator",
    archive_root="emulator",
    source_properties=(
        "Pkg.UserSrc=false\n"
        "Pkg.Revision=37.1.11\n"
        "Pkg.Path=emulator\n"
        "Pkg.Desc=Android Emulator\n"
        "Pkg.BuildId=15917651\n"
    ),
)

PLATFORM_TOOLS = Component(
    id="platform-tools",
    name="平台工具（adb）",
    version="37.0.1",
    url="platform-tools_r37.0.1-win.zip",
    size=8_044_989,
    sha1="e03e78b1d80b396f1c3358e31251cb31740e1110",
    target="platform-tools",
    archive_root="platform-tools",
    source_properties="Pkg.UserSrc=false\nPkg.Revision=37.0.1\n",
)

SYSTEM_IMAGE = Component(
    id="system-image",
    name="系统镜像 Android 14 Google APIs x86_64",
    version="android-34 google_apis x86_64 r14",
    url="sys-img/google_apis/x86_64-34_r14.zip",
    size=1_563_721_130,
    sha1="e0f6c9a0691aa27bd597d0deb1bcfdc943ac8ca7",
    target="system-images/android-34/google_apis/x86_64",
    archive_root="x86_64",
    source_properties=(
        "Pkg.Desc=System Image x86_64 with Google APIs.\n"
        "Pkg.Revision=14\n"
        "Pkg.Dependencies=emulator#34.2.16\n"
        "AndroidVersion.ApiLevel=34\n"
        "AndroidVersion.ExtensionLevel=7\n"
        "AndroidVersion.IsBaseSdk=true\n"
        "SystemImage.Abi=x86_64\n"
        "SystemImage.TagId=google_apis\n"
        "SystemImage.TagDisplay=Google APIs\n"
        "SystemImage.GpuSupport=true\n"
        "Addon.VendorId=google\n"
        "Addon.VendorDisplay=Google Inc.\n"
    ),
)

#: 必需组件，按下载顺序（小的先下，adb 先到位便于排查）。
REQUIRED_COMPONENTS: tuple[Component, ...] = (PLATFORM_TOOLS, EMULATOR, SYSTEM_IMAGE)

#: 实例配置里的 ``image.sysdir.1``，相对 SDK 根。
SYSTEM_IMAGE_SYSDIR = "system-images\\android-34\\google_apis\\x86_64\\"


@dataclass(frozen=True)
class LauncherComponent:
    """可选组件：轻量桌面。不是 Google 的包，走 F-Droid，按 sha256 校验。"""

    id: str
    name: str
    version: str
    file_name: str
    size: int
    sha256: str
    urls: tuple[str, ...]
    package: str
    home_activity: str
    license: str


FOSSIFY_LAUNCHER = LauncherComponent(
    id="launcher",
    name="轻量桌面 Fossify Launcher（F-Droid）",
    version="1.10.0",
    file_name="org.fossify.home_16.apk",
    size=5_222_266,
    sha256="a603d3d510482feafd73d52a93a1ea9baefd2ca0aae329a14cbf0e21f43638e3",
    urls=(
        "https://f-droid.org/repo/org.fossify.home_16.apk",
        "https://mirrors.tuna.tsinghua.edu.cn/fdroid/repo/org.fossify.home_16.apk",
        "https://mirrors.nju.edu.cn/fdroid/repo/org.fossify.home_16.apk",
    ),
    package="org.fossify.home",
    home_activity="org.fossify.home/.activities.MainActivity",
    license="GPL-3.0",
)

#: 被 Fossify 替掉的原生桌面。
PIXEL_LAUNCHER_PACKAGE = "com.google.android.apps.nexuslauncher"


# ---- 实例 -----------------------------------------------------------------

#: 新建实例可选的内存（MB）与 CPU 核数，默认 4 GB / 4 核（预研 §6.15：3 GB 能跑、很紧）。
MEMORY_CHOICES_MB = (3072, 4096, 6144)
CPU_CHOICES = (2, 4, 6)
DEFAULT_MEMORY_MB = 4096
DEFAULT_CPU = 4
#: 数据盘上限（GB），按实际写入增长。游戏资源都在里面，崩坏三一款就 36 GB。
DEFAULT_DATA_PARTITION_GB = 64
DATA_PARTITION_RANGE_GB = (16, 512)
#: 分辨率固定：1920×1080 横屏、DPI 280（预研里调好的 mas_p0）。
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
SCREEN_DENSITY = 280

#: 估宿主内存占用：客体内存 + 这么多（预研 §6.15：3 GB 客体工作集 3.0–3.9 GB，
#: 4 GB 客体 4.6–5.0 GB）。宿主可用内存不够就拒绝启动，不让系统开始换页。
HOST_MEMORY_OVERHEAD_MB = 1536

#: 首次开机后禁用的手机预装应用（``pm disable-user --user 0``，``pm enable`` 可逆）。
#: 谷歌服务、WebView、Chrome、键盘、文件选择器、安装器、网络与电话组件都保留（预研 §6.11）。
DEBLOAT_PACKAGES: tuple[str, ...] = (
    "com.google.android.googlequicksearchbox",
    "com.google.android.youtube",
    "com.google.android.apps.youtube.music",
    "com.google.android.gm",
    "com.google.android.apps.messaging",
    "com.google.android.dialer",
    "com.google.android.contacts",
    "com.google.android.apps.photos",
    "com.google.android.apps.maps",
    "com.google.android.apps.docs",
    "com.google.android.calendar",
    "com.google.android.deskclock",
    "com.google.android.apps.wellbeing",
    "com.google.android.as",
    "com.google.android.as.oss",
    "com.google.android.projection.gearhead",
    "com.google.android.marvin.talkback",
    "com.google.android.apps.restore",
    "com.google.android.feedback",
    "com.google.android.printservice.recommendation",
    "com.google.android.markup",
)

#: 已知在官方模拟器上跑不起来的游戏：包名 → 说明。脚本要拉起它们时直接报错，不去启动。
INCOMPATIBLE_PACKAGES: dict[str, str] = {
    # 预研 §6.20：GLES 下游戏图形线程崩溃，强制 Vulkan 则模拟器冻结 / 退出（emulator 37.1.11）
    "com.miHoYo.hkrpg": "崩坏：星穹铁道",
}

#: 后台游戏清理时永远不动的第三方包（桌面本身）。输入法按当前默认输入法另外排除。
KEEP_PACKAGES = frozenset({FOSSIFY_LAUNCHER.package})

#: 冻结看门狗：探活间隔、单次 adb 探活超时、连续几次「adb 不通且 qemu CPU 不动」判冻结。
WATCHDOG_INTERVAL_SECONDS = 30.0
WATCHDOG_PROBE_TIMEOUT_SECONDS = 10.0
WATCHDOG_STRIKES = 2

#: ``close`` 等 ``emu kill`` 生效的上限，超时强杀该实例的 qemu 进程。
CLOSE_TIMEOUT_SECONDS = 20.0
