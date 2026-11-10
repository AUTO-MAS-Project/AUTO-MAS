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

"""ModAVD（Android Emulator）后端的固定参数。

模拟器、平台工具、系统镜像都随模拟器内测包提供，MAS 不下载；只有模拟器本体可以由 MAS 从 ModAVD 的
GitHub Release 更新（:mod:`.updater`）。这里记它们在根目录里的位置。
"""

from dataclasses import dataclass

#: ModAVD 目前只给 MFW 脚本（MaaFW 引擎，通用项目与各特调）和 MAA 用：其它脚本选了 ModAVD 设备时，
#: 保存与运行时都用这句话拒绝，不走没测过的路。
MOD_AVD_UNSUPPORTED_MESSAGE = "ModAVD 目前只支持 MFW 脚本和 MAA"

#: 端口段：原生索引 i → 控制台 ``20000 + 10*i``，adb ``+1``，gRPC ``+2``。
#: 整段 20000–20100 由用户指定，避开雷电（5554 起）和 MuMu（16384 起）。
PORT_BASE = 20000
PORT_STEP = 10
#: 所有 ModAVD 实例共用的私有 adb server。模拟器只向它注册，**永远不碰 5037**：
#: 5037 是雷电 / MuMu / 生产 MAA 在用的，不同版本的 adb 抢 5037 会互相杀 server。
ADB_SERVER_PORT = 20050
#: 脚本（MAA、MaaFW）在 ModAVD 实例上用的 adb server。脚本用 SDK 的新版 adb，放在 5037 上会和
#: 雷电 / MuMu 自带的旧版 adb 互杀 server（用户定：单独一个端口）。``mas-avd.json`` 的
#: ``scriptAdbServerPort`` 可改。
SCRIPT_ADB_SERVER_PORT = 20049
#: 我们起的 adb server（私有、脚本专用）都带这个环境变量：关掉 adb server 对 5555–5585 本地端口的
#: 模拟器扫描。不关的话它们会自动连上同机的雷电等模拟器（10-04 实测 20058 / 20059 都挂上了生产雷电的
#: ``emulator-5560``），和生产抢同一个 adbd。ModAVD 实例在 20000 段、靠 ``host:emulator`` 登记，
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
#: 宿主显卡驱动给这条安装的模拟器用的着色器缓存（更新器不碰）。
SHADER_CACHE_DIR = "shader-cache"
#: 旧版 MAS 在本机生成的客体驱动补丁库目录（更新器不碰）。
GUEST_PATCH_DIR = "guest-patches"


def console_port(native_index: int | str) -> int:
    return PORT_BASE + PORT_STEP * int(native_index)


def adb_port(native_index: int | str) -> int:
    return console_port(native_index) + 1


@dataclass(frozen=True)
class InstancePorts:
    """一台实例的控制台 / adb / gRPC 端口与私有 server 上的序列号（``emulator-<控制台端口>``）。

    根目录可以在 ``mas-avd.json`` 里用 ``portBase`` 换一段端口（ModAVD/ModAVD#75），合不合规、怎么算
    由 modavd 决定，MAS 不重写这套规则：取 CLI ``info`` / ``list`` 返回的 ``ports``、``serial``
    （ModAVDManager v0.3.1 起才有，见 ``manager._ports_from_cli``）；更新中不起 CLI、或 CLI 太老
    不带这两项时，按默认端口段 :func:`default_instance_ports` 算（那些版本本来就不支持 ``portBase``）。
    截图共享内存 ``SHM_videmulator<控制台端口>`` 跟着控制台端口走。
    """

    console: int
    adb: int
    grpc: int
    serial: str


def default_instance_ports(native_index: int | str) -> InstancePorts:
    """默认端口段（``PORT_BASE``）上这台实例的端口。"""
    console = console_port(native_index)
    return InstancePorts(console, console + 1, console + 2, f"emulator-{console}")


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

#: Android 模拟器只认我们的自编版（用户定：必须用 ModAVD 内测包）。内测包解压出来就是一个
#: ModAVD 根目录，自带 ``sdk\emulator``；原版（谷歌发的）不支持，开机前检查直接拒绝。
#: 认自编版的办法见 ``components.emulator_self_built``；还要内测包编号够新，见 :data:`MIN_MOD_AVD_BUILD`。
#: 内测包的编号：自编模拟器在 ``sdk\emulator\source.properties`` 里写 ``Pkg.BuildId=mas-<编号>``，
#: 每出一个新包加一。编号低于这个值（或读不到编号）的内测包开机前检查拒绝开机，要用户换新包。
MIN_MOD_AVD_BUILD = 25
MOD_AVD_BUILD_PREFIX = "mas-"
EMULATOR_COMPONENT_ID = "emulator"
EMULATOR_COMPONENT_NAME = "Android 模拟器（emulator）"


# ---- 更新 -----------------------------------------------------------------

#: ModAVD 公开发布的仓库，以及查最新一版的 GitHub 接口。
MODAVD_REPOSITORY = "ModAVD/ModAVD"
MODAVD_RELEASE_API = f"https://api.github.com/repos/{MODAVD_REPOSITORY}/releases/latest"
#: 只供测试：把上面的查询地址换成本地模拟服务（不进配置、不上界面）。
MODAVD_RELEASE_API_ENV = "AUTO_MAS_MODAVD_RELEASE_API"
#: 包根上的逐文件清单（新写法版本 v0.32.1 起才有）。
MODAVD_MANIFEST_FILE = "modavd-manifest.json"
#: 本机要装的 ModAVD 平台（MAS 只在 Windows x64 上跑 ModAVD）。主包的文件名和清单的 ``platform``
#: 都带它：``ModAVD-<ver>-win-x64.zip``；源码包 ``ModAVD-<ver>-sources.zip`` 不带。以后可能有
#: ``linux-x64``，更新器只装和这里一致的包。
MODAVD_PLATFORM_OS = "win"
MODAVD_PLATFORM_ARCH = "x64"
MODAVD_PLATFORM = f"{MODAVD_PLATFORM_OS}-{MODAVD_PLATFORM_ARCH}"
#: Mirror 酱上 ModAVD 的资源 ID、请求带的 ``os`` / ``arch`` 与更新通道。10-24 实测：服务端把 os/arch
#: 存成 windows/amd64，请求带 win/x64 或 windows/amd64 都认，不带 os/arch 返回 8001。
MODAVD_MIRROR_RID = "ModAVD"
MODAVD_MIRROR_OS = MODAVD_PLATFORM_OS
MODAVD_MIRROR_ARCH = MODAVD_PLATFORM_ARCH
MODAVD_MIRROR_CHANNEL = "stable"
#: 只供测试：把 Mirror 酱的查询根地址（``https://mirrorchyan.com/api/resources``）换成本地模拟服务。
MODAVD_MIRROR_API_ENV = "AUTO_MAS_MODAVD_MIRROR_API"
#: 更新器在根目录里的工作目录：下载、解包、暂存、上一版都在这里。和根目录同一个盘，换上靠改名。
UPDATE_DIR = ".update"
#: 查更新的结果缓存多久（秒），和 MAS 自己检查更新一样 4 小时；用户点「更新」时不走缓存。
UPDATE_CHECK_CACHE_SECONDS = 4 * 3600
UPDATE_API_TIMEOUT_SECONDS = 15.0
#: 下载前根目录所在盘至少要剩这么多：暂存约 0.7 GB、下载约 0.3 GB，再留出余量（旧版是改名过去的，
#: 不另占空间）。
UPDATE_MIN_FREE_BYTES = int(1.7 * 1024**3)
#: 包里条目数与解压后总大小的上限，挡坏包和压缩炸弹（现在约 330 个条目、0.7 GB）。
UPDATE_MAX_ENTRIES = 20_000
UPDATE_MAX_UNPACKED_BYTES = 4 * 1024**3
#: ``mas-avd.json`` 的 ``updateHistory`` 只留最近这么多条。
UPDATE_HISTORY_KEEP = 20


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


# ---- 实例 -----------------------------------------------------------------

#: 实例可选的内存（MB）与 CPU 核数（预研 §6.15：3 GB 能跑、很紧）。只收这几档，每次开机用实例自己
#: 设的内存传 ``-memory``。不按游戏自动分配（用户 10-04 定）：一台实例一轮里可能先后跑好几个游戏，
#: 开机后内存就改不了了。默认 6 核 6 GB，够任何一个游戏用。
MEMORY_CHOICES_MB = (3072, 4096, 5120, 6144)
CPU_CHOICES = (2, 4, 6)
DEFAULT_MEMORY_MB = 6144
DEFAULT_CPU = 6
#: 游戏的推荐内存（MB），只用来提示：界面上的推荐值，以及开机时实例内存低于推荐值记一条日志。
#: 只列实测过内存的 1999（数据来自 ModAVD 实测）。
RECOMMENDED_MEMORY_MB: dict[str, int] = {
    "com.shenlan.m.reverse1999": 4096,
}
#: 数据盘上限（GB），按实际写入增长。游戏资源都在里面，崩坏三一款就 36 GB。
DEFAULT_DATA_PARTITION_GB = 64
DATA_PARTITION_RANGE_GB = (16, 512)

#: 两档显示，DPI 随档位切换；开机前写 ``config.ini``，不用运行时显示覆盖。
DISPLAY_PRESETS = {1080: (1920, 1080, 280), 720: (1280, 720, 240)}
DEFAULT_RESOLUTION = 1080
#: 刷新率（``config.ini`` 的 ``hw.lcd.vsync``，下次开机生效），按实例设。默认 60（用户 10-16 定：
#: 帧率影响脚本操作）；30 是低消耗档：终末地大世界 30 Hz 下稳定 30 fps、qemu 约 1.6 核，60 Hz 下
#: 54–61 fps、qemu 4 核以上（ModAVD 实测）。
FPS_CHOICES = (30, 60)
DEFAULT_FPS = 60

#: 后台游戏清理时永远不动的第三方包（桌面本身、宿主输入法由 modavd 管理）。
KEEP_PACKAGES = frozenset({LIGHT_LAUNCHER.package, "org.modavd.ime"})

#: 冻结看门狗：探活间隔、单次 adb 探活超时、连续几次「adb 不通且 qemu CPU 不动」判冻结。
WATCHDOG_INTERVAL_SECONDS = 30.0
WATCHDOG_PROBE_TIMEOUT_SECONDS = 10.0
WATCHDOG_STRIKES = 2

#: 关机 / 重启 / 注销前并发关 ModAVD 实例（每个根目录一次 ``modavd stop --all``）的总时限；到点不等，
#: 电源流程照常按进程名强杀。
POWER_CLOSE_TIMEOUT_SECONDS = 30.0
