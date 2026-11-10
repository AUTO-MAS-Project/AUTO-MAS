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

开关机、端口、adb server、组件都由根目录里的 ModAVD 命令行 ``tools\\modavd.exe`` 管（:mod:`.cli`），
整个 ModAVD 包可以在 MAS 里经 ``modavd update`` 更新（:mod:`.updater`）。这里只留 MAS 自己要用的
参数：实例档位的校验、给脚本的 adb 环境、看门狗与关机时限。
"""

from dataclasses import dataclass

#: ModAVD 目前只给 MFW 脚本（MaaFW 引擎，通用项目与各特调）和 MAA 用：其它脚本选了 ModAVD 设备时，
#: 保存与运行时都用这句话拒绝，不走没测过的路。
MOD_AVD_UNSUPPORTED_MESSAGE = "ModAVD 目前只支持 MFW 脚本和 MAA"

#: 给脚本进程（MAA、MaaFW）叠加的环境变量：关掉脚本的 adb 万一自己拉起 server 时对 5555–5585 本地端口
#: 的模拟器扫描。不关的话会自动连上同机的雷电等模拟器（10-04 实测连上了生产雷电的 ``emulator-5560``），
#: 和生产抢同一个 adbd。值小于 5555 时 adb 一个端口都不扫。
ADB_NO_LOCAL_SCAN_ENV = {"ADB_LOCAL_TRANSPORT_MAX_PORT": "5554"}
#: 原生索引的范围（新建时指定编号的校验；端口由 modavd 定）。
MAX_NATIVE_INDEX = 9
RESERVED_NATIVE_INDEXES = frozenset({5})

#: AVD 名 = ``mas_<原生索引>``。
AVD_NAME_PREFIX = "mas_"

#: 根目录布局：MAS 认根目录、算实例锁的键（``sdk\\emulator\\emulator.exe``，见
#: ``components.manager_key_exe``）只用到这一级目录名，不读里面的文件。
SDK_DIR = "sdk"


@dataclass(frozen=True)
class InstancePorts:
    """一台实例的控制台 / adb / gRPC 端口与私有 server 上的序列号（``emulator-<控制台端口>``）。

    端口段由 modavd 定（根目录可以设 ``portBase``），MAS 不算：一律取 CLI ``info`` / ``list`` 返回的
    ``ports``、``serial``（见 ``manager._ports_from_cli``）。截图共享内存 ``SHM_videmulator<控制台端口>``
    跟着控制台端口走。
    """

    console: int
    adb: int
    grpc: int
    serial: str


@dataclass(frozen=True)
class AvdAdbInfo:
    """给脚本（MAA、MaaFW）配 adb 用的一份数据，取自一次 ``modavd list``：这条安装的 adb 程序、私有
    adb server 的端口（MaaFW 截图通道开关推流走它），和这台实例的端口。"""

    adb_exe: str
    adb_server_port: int
    ports: InstancePorts


def avd_name(native_index: int | str) -> str:
    return f"{AVD_NAME_PREFIX}{int(native_index)}"


def valid_native_index(native_index: int) -> bool:
    return (
        0 <= native_index <= MAX_NATIVE_INDEX
        and native_index not in RESERVED_NATIVE_INDEXES
    )


#: µLauncher（ModAVD 首次开机装进客体的轻量桌面）的包名：清后台时不动它。
LIGHT_LAUNCHER_PACKAGE = "de.jrpie.android.launcher"


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
KEEP_PACKAGES = frozenset({LIGHT_LAUNCHER_PACKAGE, "org.modavd.ime"})

#: 冻结看门狗：探活间隔、单次 adb 探活超时、连续几次「adb 不通且 qemu CPU 不动」判冻结。
WATCHDOG_INTERVAL_SECONDS = 30.0
WATCHDOG_PROBE_TIMEOUT_SECONDS = 10.0
WATCHDOG_STRIKES = 2

#: 关机 / 重启 / 注销前并发关 ModAVD 实例（每个根目录一次 ``modavd stop --all``）的总时限；到点不等，
#: 电源流程照常按进程名强杀。
POWER_CLOSE_TIMEOUT_SECONDS = 30.0
