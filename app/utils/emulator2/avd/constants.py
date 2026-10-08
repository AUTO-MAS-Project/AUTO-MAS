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

"""魔改 AVD（Android Emulator）后端的固定参数。

模拟器、平台工具、系统镜像都随模拟器内测包提供，MAS 不下载；这里只记它们在根目录里的位置。
"""

from dataclasses import dataclass

#: 魔改 AVD 目前只给 M9A 用（特调声明 ``supports_mod_avd``，见 MaaFW ``flavor.py``）：其它脚本选了
#: 魔改 AVD 设备时，保存与运行时都用这句话拒绝，不走没测过的路。
MOD_AVD_M9A_ONLY_MESSAGE = "魔改 AVD 目前只支持 M9A"

#: 端口段：原生索引 i → 控制台 ``20000 + 10*i``，adb ``+1``，gRPC ``+2``。
#: 整段 20000–20100 由用户指定，避开雷电（5554 起）和 MuMu（16384 起）。
PORT_BASE = 20000
PORT_STEP = 10
#: 所有魔改 AVD 实例共用的私有 adb server。模拟器只向它注册，**永远不碰 5037**：
#: 5037 是雷电 / MuMu / 生产 MAA 在用的，不同版本的 adb 抢 5037 会互相杀 server。
ADB_SERVER_PORT = 20050
#: 脚本（MAA、MaaFW）在魔改 AVD 实例上用的 adb server。脚本用 SDK 的新版 adb，放在 5037 上会和
#: 雷电 / MuMu 自带的旧版 adb 互杀 server（用户定：单独一个端口）。``mas-avd.json`` 的
#: ``scriptAdbServerPort`` 可改。
SCRIPT_ADB_SERVER_PORT = 20049
#: 我们起的 adb server（私有、脚本专用）都带这个环境变量：关掉 adb server 对 5555–5585 本地端口的
#: 模拟器扫描。不关的话它们会自动连上同机的雷电等模拟器（10-04 实测 20058 / 20059 都挂上了生产雷电的
#: ``emulator-5560``），和生产抢同一个 adbd。魔改 AVD 实例在 20000 段、靠 ``host:emulator`` 登记，
#: 本来就不在扫描范围里，关掉不影响。值小于 5555 时 adb 一个端口都不扫。
ADB_NO_LOCAL_SCAN_ENV = {"ADB_LOCAL_TRANSPORT_MAX_PORT": "5554"}
#: 原生索引上限。i=5 的端口段 20050–20052 正好压在私有 adb server 上，不能用。
MAX_NATIVE_INDEX = 9
RESERVED_NATIVE_INDEXES = frozenset({5})

#: AVD 名 = ``mas_<原生索引>``，枚举靠扫 ``avd\\mas_*.ini``。
AVD_NAME_PREFIX = "mas_"

#: 根目录布局。
SDK_DIR = "sdk"
AVD_DIR = "avd"
COMPONENTS_DIR = "components"
METADATA_FILE = "mas-avd.json"
#: 模拟器日志、客体 logcat。
LOGS_DIR = "logs"
#: 每台实例的模拟器日志、客体 logcat 各保留最新的这么多份（开机建新日志前清）。
LOG_KEEP_PER_INSTANCE = 10
#: 整个日志目录（只算上面两种日志）的总大小上限，超了从最旧的删起，不分实例。
LOGS_DIR_MAX_BYTES = 1024**3
#: 宿主显卡驱动给这条安装的模拟器用的着色器缓存。
SHADER_CACHE_DIR = "shader-cache"


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


# ---- 组件 -----------------------------------------------------------------


@dataclass(frozen=True)
class Component:
    """内测包里的一个必需组件：``target`` 是它在 SDK 里的目录。"""

    id: str
    name: str
    target: str


PLATFORM_TOOLS = Component(
    id="platform-tools",
    name="平台工具（adb）",
    target="platform-tools",
)

SYSTEM_IMAGE = Component(
    id="system-image",
    name="系统镜像 Android 14 Google APIs x86_64",
    target="system-images/android-34/google_apis/x86_64",
)

#: 内测包里除模拟器以外的必需组件（模拟器另外检查，见下）。
REQUIRED_COMPONENTS: tuple[Component, ...] = (PLATFORM_TOOLS, SYSTEM_IMAGE)

#: Android 模拟器只认我们的自编版（用户定：必须用魔改 AVD 内测包）。内测包解压出来就是一个
#: 魔改 AVD 根目录，自带 ``sdk\emulator``；原版（谷歌发的）不支持，开机前检查直接拒绝。
#: 认自编版的办法见 ``components.emulator_self_built``；还要内测包编号够新，见 :data:`MIN_MOD_AVD_BUILD`。
#: 内测包的编号：自编模拟器在 ``sdk\emulator\source.properties`` 里写 ``Pkg.BuildId=mas-<编号>``，
#: 每出一个新包加一。编号低于这个值（或读不到编号）的内测包开机前检查拒绝开机，要用户换新包。
MIN_MOD_AVD_BUILD = 25
MOD_AVD_BUILD_PREFIX = "mas-"
EMULATOR_COMPONENT_ID = "emulator"
EMULATOR_COMPONENT_NAME = "Android 模拟器（emulator）"

#: 实例配置里的 ``image.sysdir.1``，相对 SDK 根。
SYSTEM_IMAGE_SYSDIR = "system-images\\android-34\\google_apis\\x86_64\\"


@dataclass(frozen=True)
class LauncherComponent:
    """可选组件：轻量桌面，随内测包放在 ``<根>\\components``，首次开机时装进客体。"""

    id: str
    name: str
    version: str
    file_name: str
    size: int
    package: str
    home_activity: str


#: µLauncher（F-Droid 开发者签名版，MIT）。它默认按显示器的自然方向（我们是横屏）显示，不要求竖屏。
LIGHT_LAUNCHER = LauncherComponent(
    id="launcher",
    name="轻量桌面 µLauncher",
    version="0.2.12",
    file_name="de.jrpie.android.launcher_57.apk",
    size=4_099_556,
    package="de.jrpie.android.launcher",
    home_activity="de.jrpie.android.launcher/.ui.HomeActivity",
)

# 第一次打开 µLauncher 之前预置的东西，见 ``manager._preset_light_launcher``。
# 固定 µLauncher 0.2.12，换版本要对着它的源码重新核对下面这些键、文件和版本号。
#: 它的偏好文件（``PreferenceManager.getDefaultSharedPreferences``）。
LIGHT_LAUNCHER_PREFS_FILE = (
    "/data/data/de.jrpie.android.launcher/shared_prefs/"
    "de.jrpie.android.launcher_preferences.xml"
)
#: 它第一次启动时自己写出默认偏好（桌面时钟、上滑打开应用列表等），同时写进去的偏好版本号
#: （源码 ``Preferences.kt`` 的 ``PREFERENCE_VERSION``，不是 versionCode 57）。
LIGHT_LAUNCHER_PREFS_VERSION = 101
#: 预置的布尔偏好。键名取 ``res/values/donottranslate.xml`` 里的字符串值，不是 ``LauncherPreferences$Config``
#: 里的字段名：``internal.started_before`` 是「引导已走完」，``functionality.search_auto_keyboard`` 是
#: 「打开应用列表时自动弹键盘」（横屏下输入法全屏，把列表整个挡住）。
LIGHT_LAUNCHER_PRESET_PREFS: tuple[tuple[str, bool], ...] = (
    ("internal.started_before", True),
    ("functionality.search_auto_keyboard", False),
)
#: 只为在后台拉起它的进程、让它写出默认偏好：给这个接收器发一个空广播（接收器不认这个广播，什么也不做）。
LIGHT_LAUNCHER_WAKE_RECEIVER = (
    "de.jrpie.android.launcher/.actions.lock.LauncherDeviceAdmin"
)

#: 被轻量桌面替掉的原生桌面。
PIXEL_LAUNCHER_PACKAGE = "com.google.android.apps.nexuslauncher"


# ---- 实例 -----------------------------------------------------------------

#: 实例可选的内存（MB）与 CPU 核数（预研 §6.15：3 GB 能跑、很紧）。只收这几档，每次开机用实例自己
#: 设的内存传 ``-memory``。不按游戏自动分配（用户 10-04 定）：一台实例一轮里可能先后跑好几个游戏，
#: 开机后内存就改不了了。默认 6 核 6 GB，够任何一个游戏用。
MEMORY_CHOICES_MB = (3072, 4096, 5120, 6144)
CPU_CHOICES = (2, 4, 6)
DEFAULT_MEMORY_MB = 6144
DEFAULT_CPU = 6
#: 游戏的推荐内存（MB），只用来提示：界面上的推荐值，以及开机时实例内存低于推荐值记一条日志。
#: 魔改 AVD 目前只支持 M9A，只列 1999（数据见 aemu-lab ``自研模拟器-动态内存.md`` 第 7.6 节）。
RECOMMENDED_MEMORY_MB: dict[str, int] = {
    "com.shenlan.m.reverse1999": 4096,
}
#: 数据盘上限（GB），按实际写入增长。游戏资源都在里面，崩坏三一款就 36 GB。
DEFAULT_DATA_PARTITION_GB = 64
DATA_PARTITION_RANGE_GB = (16, 512)

#: 显示固定 720p（用户 10-04 定），开机前写进 ``config.ini`` 的 ``hw.lcd.*``，不用 ``wm size``
#: （运行时覆盖出过小毛病）。即雷电 / MuMu 的默认值，脚本都认。
SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_DENSITY = 1280, 720, 240

#: 空闲页上报（气球）开着时，开机后把客体 ``page_reporting_order`` 设成这个值（2 MiB 块，
#: 与 Hyper-V / WSL2 一致；驱动绑定时内核会把它重置成 pageblock_order 10）。
BALLOON_PAGE_REPORTING_ORDER = 9
#: 客体脏页回写（``/proc/sys/vm/dirty_expire_centisecs`` / ``dirty_writeback_centisecs``，单位 1/100 秒），
#: 每次开机都设（不持久）。依据 10-04 硬杀实测（aemu-lab ``AGENTS.md``「关机」，32 次冷启动）：「先删旧文件
#: 再把临时文件改名过去」这种写法，在默认 3000/500 下写完 2–34 秒内被硬杀会变成 0 字节；200/100 把窗口缩到
#: 约 5 秒，代价是普通负载多写约 14%。AOSP 自己在低内存设备上也用 200。正常关机仍要先 ``sync``。
GUEST_DIRTY_EXPIRE_CENTISECS = 200
GUEST_DIRTY_WRITEBACK_CENTISECS = 100

#: 客体脚本（``res/avd/guest/``）推到客体的位置。
GUEST_TMP_DIR = "/data/local/tmp"
#: logcat 落盘前把客体日志缓冲调到这么大（默认 256 KB，游戏一跑几分钟就滚掉）。
LOGCAT_BUFFER_SIZE = "16M"

#: 估宿主内存占用：客体内存 + 这么多（预研 §6.15：3 GB 客体工作集 3.0–3.9 GB，
#: 4 GB 客体 4.6–5.0 GB）。宿主可用内存不够就拒绝启动，不让系统开始换页。
HOST_MEMORY_OVERHEAD_MB = 1536

#: 开机前实例所在盘至少要剩这么多（GB）：数据盘是稀疏文件，随游戏写入增长（崩坏三一款 36 GB），
#: 盘写满时客体写失败、实例数据会损坏。低于这个值拒绝开机。
MIN_FREE_DISK_GB_TO_BOOT = 8
#: 电脑检查里 Vulkan「可用」的结果缓存多久（秒）：显卡驱动不会频繁变，免得每次开机都起一次子进程。
#: 「没有 Vulkan」不缓存：用户装好驱动后再查马上就能看到。
VULKAN_PROBE_CACHE_SECONDS = 600.0
#: 探测超时的结果缓存多久（秒）：驱动挂住时不必每次查状态、每次开机都等满超时。
VULKAN_PROBE_TIMEOUT_CACHE_SECONDS = 60.0
#: Vulkan 探测子进程的超时（秒）。
VULKAN_PROBE_TIMEOUT_SECONDS = 30.0

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

#: 后台游戏清理时永远不动的第三方包（桌面本身）。输入法按当前默认输入法另外排除。
KEEP_PACKAGES = frozenset({LIGHT_LAUNCHER.package})

#: 冻结看门狗：探活间隔、单次 adb 探活超时、连续几次「adb 不通且 qemu CPU 不动」判冻结。
WATCHDOG_INTERVAL_SECONDS = 30.0
WATCHDOG_PROBE_TIMEOUT_SECONDS = 10.0
WATCHDOG_STRIKES = 2

#: 关机各步的上限。调用方（``app/task/emulator_core.close_emulator``）整体只给 30 秒，超时后连强杀
#: 都执行不到，所以加起来 27 秒：私有 server 没在跑时起它并替实例登记 4 + sync 3 + 控制台 kill 3
#: + 等 qemu 退出 12 + 强杀后等 5。SDK adb 的 ``start-server`` 客户端要 2.08–2.12 秒才返回，所以起
#: server 只等端口开始监听、不等客户端退出（第三轮复核：给 2 秒时 server 起来了 sync 却被跳过）。
#: sync 正常几十毫秒（实测 46–93 ms），qemu 收到 kill 后 2–3 秒退出。
ADB_SERVER_START_TIMEOUT_ON_CLOSE_SECONDS = 4.0
SYNC_TIMEOUT_SECONDS = 3.0
CONSOLE_KILL_TIMEOUT_SECONDS = 3.0
CLOSE_TIMEOUT_SECONDS = 12.0
FORCE_KILL_WAIT_SECONDS = 5.0
#: 关机 / 重启 / 注销前并发关魔改 AVD 实例的总时限（单台 27 秒以内，留一点余量）；到点不等，
#: 电源流程照常按进程名强杀。
POWER_CLOSE_TIMEOUT_SECONDS = 30.0
#: 「安装 APK」一次 `adb install` 的时限。游戏安装包常有 1–3 GB，推送加安装在慢盘上要几分钟。
APK_INSTALL_TIMEOUT_SECONDS = 900.0
