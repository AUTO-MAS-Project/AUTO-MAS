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
#: 模拟器日志、客体 logcat、看门狗证据。
LOGS_DIR = "logs"
#: 宿主显卡驱动给这条安装的模拟器用的着色器缓存。
SHADER_CACHE_DIR = "shader-cache"
#: 宿主侧临时文件（如星铁补丁拉下来的原库），用完即删。
CACHE_DIR = "cache"


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

#: 实例可选的内存（MB）与 CPU 核数（预研 §6.15：3 GB 能跑、很紧）。内存默认「按游戏自动」，
#: 见 :data:`GAME_MEMORY_MB`；用户手动指定时只收这几档。
MEMORY_CHOICES_MB = (3072, 4096, 5120, 6144)
CPU_CHOICES = (2, 4, 6)
DEFAULT_MEMORY_MB = 4096
DEFAULT_CPU = 4
#: 「按游戏自动」的内存（MB），启动时用 ``-memory`` 传入；表里没有的游戏用 :data:`DEFAULT_MEMORY_MB`。
#: 数据见 aemu-lab ``自研模拟器-动态内存.md`` 第 7.6 节：星铁 4 GB 能跑，但 zram 压了近 2 GB，偏紧。
GAME_MEMORY_MB: dict[str, int] = {
    "com.hypergryph.arknights": 4096,
    "com.hypergryph.arknights.bilibili": 4096,
    "com.shenlan.m.reverse1999": 4096,
    "com.miHoYo.enterprise.NGHSoD": 4096,
    "com.miHoYo.hkrpg": 5120,
    "com.miHoYo.hkrpg.bilibili": 5120,
}
#: 数据盘上限（GB），按实际写入增长。游戏资源都在里面，崩坏三一款就 36 GB。
DEFAULT_DATA_PARTITION_GB = 64
DATA_PARTITION_RANGE_GB = (16, 512)

#: 显示只有两档（用户 10-03 定），开机前写进 ``config.ini`` 的 ``hw.lcd.*``，不用 ``wm size``
#: （运行时覆盖出过小毛病）。档位名 → (长边, 短边, DPI)，即雷电 / MuMu 的默认值，脚本都认。
RESOLUTIONS: dict[str, tuple[int, int, int]] = {
    "720": (1280, 720, 240),
    "1080": (1920, 1080, 280),
}
DEFAULT_RESOLUTION = "720"
#: 新建实例模板的显示（= 默认档，横屏）。
SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_DENSITY = RESOLUTIONS[DEFAULT_RESOLUTION]

#: 空闲页上报（气球）开着时，开机后把客体 ``page_reporting_order`` 设成这个值（2 MiB 块，
#: 与 Hyper-V / WSL2 一致；驱动绑定时内核会把它重置成 pageblock_order 10）。
BALLOON_PAGE_REPORTING_ORDER = 9
#: 气球开着时，只在出现「突发读盘」的那次开机清一次客体页缓存（用户 10-04 定）。
#: 依据：10-04 用 iotrace 抓到，开机后 20–42 秒 ``system_server`` 读了 5.3 GB（量和已装游戏的 APK
#: 总量相当），客体缓存冲到 4–5 GB，不清就整场不还给宿主；平时开机远小于这个量。
#: 客体开机这么久开始判断：读 ``system_server`` 的 ``/proc/<pid>/io`` ``read_bytes``。
DROP_CACHES_CHECK_UPTIME_SECONDS = 60.0
#: 读到这么多才算突发读盘；不到就本次开机不清。
DROP_CACHES_BURST_BYTES = 2 * 1024**3
#: 突发读盘时每隔这么久再读一次，两次之间增量小于下面的值就算读完，读完立刻清。
DROP_CACHES_POLL_SECONDS = 5.0
DROP_CACHES_SETTLED_DELTA_BYTES = 50 * 1024**2
#: 客体开机到这时还没读完就放弃，不清（游戏多半已经起来了，不在运行中清）。
DROP_CACHES_GIVE_UP_UPTIME_SECONDS = 180.0
#: 每次开机最多清一次的标记：客体属性，重启即失效，换后端进程 / 重连也看得到。
DROP_CACHES_MARKER_PROP = "debug.mas.dropped"

#: 客体脚本（``res/avd/guest/``）推到客体的位置。
GUEST_TMP_DIR = "/data/local/tmp"
#: logcat 落盘前把客体日志缓冲调到这么大（默认 256 KB，游戏一跑几分钟就滚掉）。
LOGCAT_BUFFER_SIZE = "16M"

#: 星铁普通模式（Vulkan）要的客体驱动补丁（aemu-lab ``tools/guest/khrfix.py``）：API 34 镜像的
#: ``libvulkan_enc.so`` 把两个 KHR 入口直接交给原始编码器，描述符只发出 1 字节，GPU 读到没写过的
#: 描述符就出错。补丁把两个 KHR 入口各改成 5 字节 ``jmp`` 到核心入口。只在原库哈希对得上时打，
#: 改好的库只在用户电脑上生成、缓存在客体里，**不分发**。
VULKAN_ENC_GUEST_PATH = "/vendor/lib64/libvulkan_enc.so"
VULKAN_ENC_ORIG_SHA256 = (
    "898c0bbc38077e4b19d112f6c66e2970f1e015fc440fae091974b8f06e40fefb"
)
VULKAN_ENC_FIX_SHA256 = (
    "b3ea750a20884460ec48b0af7522c0905a7df6645c4c10da27bda97c39fef614"
)
#: ``.text`` 的虚拟地址与文件偏移之差（vaddr 0x1fcee0，文件偏移 0x1fbee0）。
VULKAN_ENC_TEXT_DELTA = 0x1000
#: ``entry_vkUpdateDescriptorSetWithTemplate``（核心入口）。
VULKAN_ENC_CORE_ENTRY = 0x3D8FA0
#: (虚拟地址, 原函数开头 8 字节, 名字)：两个要改成 ``jmp`` 核心入口的 KHR 入口。
VULKAN_ENC_PATCHES: tuple[tuple[int, str, str], ...] = (
    (0x3DA5B0, "4157415641554154", "entry_vkUpdateDescriptorSetWithTemplateKHR"),
    (
        0x3B6ED0,
        "5541574156415541",
        "dynCheck_entry_vkUpdateDescriptorSetWithTemplateKHR",
    ),
)
#: 拉起前要先做 Vulkan 修复的游戏（星铁普通模式）。
VULKAN_FIX_PACKAGES = frozenset({"com.miHoYo.hkrpg", "com.miHoYo.hkrpg.bilibili"})

#: 拉起时带启动看门狗的游戏：崩坏三偶尔卡在 miHoYo 标志页（10-04 测试里卡了 30 分钟）。
STARTUP_GUARD_PACKAGES = frozenset({"com.miHoYo.enterprise.NGHSoD"})
#: 启动看门狗的参数，取 aemu-lab ``avd-game.ps1`` 的默认值（崩坏三预设）。
STARTUP_GUARD_RETRIES = 5  # 最多重开几次（= 最多拉起 6 次）
STARTUP_GUARD_INTERVAL_SECONDS = 3.0  # 采样间隔
STARTUP_GUARD_AFTER_SECONDS = 45.0  # 规则 d 的 T：拉起后最早多久能判卡死
STARTUP_GUARD_STATIC_SECONDS = 15.0  # 规则 d 的 S：画面至少静止多久
STARTUP_GUARD_IDLE_CORES = 0.3  # 进程平均不超过这么多核算空闲
STARTUP_GUARD_HARD_SECONDS = 120.0  # 进程忙但一直没有渲染线程，到这时也判卡死
STARTUP_GUARD_START_TIMEOUT_SECONDS = 180.0  # 这么久还没启动成功就重开
STARTUP_GUARD_STALL_SECONDS = (
    60.0  # StallSec：启动后画面静止 + 空闲 + 线程停在 futex 这么久判死锁
)
STARTUP_GUARD_STALL_CORES = 0.1
STARTUP_GUARD_WATCH_SECONDS = (
    300.0  # 启动后看到拉起后第几秒（= avd-game 崩坏三的就绪超时）
)

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
#: 星铁 10 月起不在表里：普通模式靠拉起前的 Vulkan 修复（见 :data:`VULKAN_FIX_PACKAGES`）。
INCOMPATIBLE_PACKAGES: dict[str, str] = {}

#: 后台游戏清理时永远不动的第三方包（桌面本身）。输入法按当前默认输入法另外排除。
KEEP_PACKAGES = frozenset({FOSSIFY_LAUNCHER.package})

#: 冻结看门狗：探活间隔、单次 adb 探活超时、连续几次「adb 不通且 qemu CPU 不动」判冻结。
WATCHDOG_INTERVAL_SECONDS = 30.0
WATCHDOG_PROBE_TIMEOUT_SECONDS = 10.0
WATCHDOG_STRIKES = 2

#: 关机各步的上限。调用方（``app/task/emulator_core.close_emulator``）整体只给 30 秒，超时后连强杀
#: 都执行不到，所以加起来 28 秒：私有 server 没在跑时起它 2 + sync 3 + 控制台 kill 3 + 等 qemu 退出 15
#: + 强杀后等 5。sync 正常几十毫秒（实测 46–93 ms），qemu 收到 kill 后 2–3 秒退出。
ADB_SERVER_START_TIMEOUT_ON_CLOSE_SECONDS = 2.0
SYNC_TIMEOUT_SECONDS = 3.0
CONSOLE_KILL_TIMEOUT_SECONDS = 3.0
CLOSE_TIMEOUT_SECONDS = 15.0
FORCE_KILL_WAIT_SECONDS = 5.0
#: 关机 / 重启 / 注销前并发关官方模拟器实例的总时限（单台 28 秒以内，留一点余量）；到点不等，
#: 电源流程照常按进程名强杀。
POWER_CLOSE_TIMEOUT_SECONDS = 30.0
