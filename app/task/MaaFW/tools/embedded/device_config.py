"""把模拟器或窗口信息换算成下发给 worker 的设备配置，以及首任务下发闸门的计算。

运行这一侧对外的「设备配置」调用：通用 MFW 与各专项的流程各自调这里的函数，不经任务类。
参数一律是普通数据（模拟器 uid、地址、ADB 路径、配置里的原值、interface 的控制器模型）；
要模拟器能力时，按 uid 调宿主现有的设备入口（``app.task.game.BoundEmulator``，参数名
``emulator``）。缓存归调用方：ADB 地址、路径与控制档案放在 :class:`MaaFWAdbDeviceState` 里，
由调用方持有、决定何时清。

不在这里做：开关模拟器、桌面游戏启停、登录与游戏更新钩子、起 worker。ModAVD 的 MaaFramework
版本门槛在起 worker 之前（要等借到运行环境才知道版本），也不在这里。
"""

from __future__ import annotations

import asyncio
import re
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from app.task.MaaFW.tools.core.controller_win32.service import (
    MaaFWWin32ControllerService,
    MaaFWWin32Window,
    controller_has_window_rules,
)
from app.task.MaaFW.tools.core.interface.models import (
    MaaFWController,
    MaaFWInterface,
)
from app.task.MaaFW.tools.core.interface.preview import (
    build_adb_emulator_extra_capabilities,
)
from app.task.MaaFW.tools.core.runner.models import MaaFWDeviceConfig, MaaFWRunPlan
from app.utils import get_logger
from app.utils.common.process.session import desktop_process_target

from .game_package import resolve_game_package

if TYPE_CHECKING:
    from app.models.emulator import DeviceInfo

# 与任务类同一个日志名：搬过来的告警在 app.log 里的模块列不变
logger = get_logger("MaaFW 插件自动代理")

Log = Callable[[str], None]

# MaaFW 的 ADB 截图/输入方法枚举（EmulatorExtras 硬件加速相关）在此镜像为整型常量，
# 而非 `from maa.controller import MaaAdb*Enum`。本模块受导入边界约束
# （tests/plugins/test_maafw_import_boundaries.py 禁止导入时把 maa 载入 sys.modules），
# 直接 import maa 会加载原生绑定，故改为对齐 plugins/pypi/site-packages/maa/define.py
# 的取值：
#   screencap Default = All & ~RawByNetcat & ~MinicapDirect & ~MinicapStream = -57
#   screencap EmulatorExtras = 1 << 6 (64)
#   input Default = All & ~EmulatorExtras = -9；input All = ~0 = -1；EmulatorExtras = 1 << 3 (8)
_ADB_SCREENCAP_DEFAULT = -57
_ADB_SCREENCAP_EMULATOR_EXTRAS = 1 << 6
_ADB_INPUT_DEFAULT = -9
_ADB_INPUT_ALL = -1
_ADB_INPUT_EMULATOR_EXTRAS = 1 << 3
# 雷电专用：MinitouchAndAdbKey(2) | AdbShell(1)，故意不带 Maatouch(4)。
#
# MaaFW 的 ADB 文本输入只有两条实现：Maatouch 走 MaaTouch 的 `t` 命令，
# AdbShell / MinitouchAndAdbKey 走 adb config 里可替换的 `InputText` 命令
# （默认 `input text`）。前者按键盘映射逐字符注入，`input text` 也只认 ASCII，
# 两条都打不进中文——2026-09-12 生产实测 M9A 兑换码「魔精小A邀泥收看1999泡面番」
# 被 Maatouch 重打 265 次、输入框始终为空，整次运行撞硬超时。
# 雷电自己的 `ldconsole action --key call.input --value <文本>` 能把任意文本
# 提交到当前焦点的输入框（实测中文 35 ms 落地），所以在雷电上把 Maatouch 从
# 候选里摘掉，让文本走 MinitouchAndAdbKey 的 `InputText` 命令并替换成 ldconsole。
# 触控仍是 minitouch 协议，雷电 adbd 本身是 root，minitouch 可用（实测 init 508 ms）。
_ADB_INPUT_LDPLAYER_CONSOLE_TEXT = (1 << 1) | 1
# 名字与取值照抄 MaaFramework 绑定库 ``maa/define.py``（main 分支）。Foreground /
# Background 是组合名：原生层在组合里按顺序择一可用的方式，FOS、MaaNTE、mpa 的默认
# Win32 控制器写的就是 Background。运行时绑定库 / 原生库认不认得某个值由 worker 再判一次
# （runner._supported_win32_method），这里只负责把名字翻成数。
_WIN32_SCREENCAP_METHODS = {
    "GDI": 1,
    "FramePool": 1 << 1,
    "DXGI_DesktopDup": 1 << 2,
    "DXGI_DesktopDup_Window": 1 << 3,
    "PrintWindow": 1 << 4,
    "ScreenDC": 1 << 5,
    "Foreground": (1 << 3) | (1 << 5),
    "Background": (1 << 1) | (1 << 4),
}
_WIN32_INPUT_METHODS = {
    "Seize": 1,
    "SendMessage": 1 << 1,
    "PostMessage": 1 << 2,
    "LegacyEvent": 1 << 3,
    "PostThreadMessage": 1 << 4,
    "SendMessageWithCursorPos": 1 << 5,
    "PostMessageWithCursorPos": 1 << 6,
    "SendMessageWithWindowPos": 1 << 7,
    "PostMessageWithWindowPos": 1 << 8,
    "Interception": 1 << 9,
    "AnchoredTouch": 1 << 10,
}
# 托管页没有填窗口句柄的入口，提示不能让用户去找一个不存在的设置。
WIN32_NO_WINDOW_RULES_MESSAGE = (
    "该项目的这个 Win32 控制器没有声明窗口匹配规则（interface 里的 class_regex / "
    "window_regex），MAS 无法确定要控制哪个窗口，为避免控制错窗口不运行；请换用项目的"
    "其他控制器，或请项目方在 interface 里补上窗口匹配规则"
)

TASK_START_GATE_DISK_QUIET = "disk_quiet"
TASK_START_GATE_SCREEN = "screen"


@dataclass(frozen=True)
class MaaFWAdbControlProfile:
    """描述某模拟器实例的 ADB EmulatorExtras 能力与 controller extras 配置。"""

    emulator_type: str | None
    screencap_extra: bool
    input_extra: bool
    config: dict[str, Any]


@dataclass
class MaaFWAdbDeviceState:
    """调用方持有的 ADB 设备缓存：同一次模拟器启动内不重复解析。

    ``address`` / ``device_info`` 随这次启动拿到；``profile`` 里雷电的 extras 带着这次启动的
    dnplayer pid，关掉模拟器后都要清（:meth:`forget_emulator_launch`）。``adb_path`` 与哪次
    启动无关，关模拟器不清。
    """

    address: str | None = None
    device_info: DeviceInfo | None = None
    adb_path: str | None = None
    profile: MaaFWAdbControlProfile | None = None

    def forget_emulator_launch(self) -> None:
        # 地址是随这次启动缓存的，关掉后下一轮要重新开、重新拿。
        self.address = None
        self.device_info = None
        # 雷电截图增强的 extras 里带着这次启动的 dnplayer pid；重开后还用旧 pid，
        # MaaFW 建不出截图实例（Failed to create ld inst），这一轮当场 connect 失败。
        self.profile = None


@dataclass(frozen=True)
class MaaFWTaskStartGate:
    """首任务下发闸门：最早下发的墙钟时刻（None 表示不等）与 worker 的放行判据。"""

    not_before: float | None
    mode: str


# ---------------------------------------------------------------------------
# 首任务下发闸门
# ---------------------------------------------------------------------------


def game_launched_with_emulator(device_info: Any) -> bool:
    """模拟器这次是不是把游戏冷启动了（进程原本不在，``launched``）。

    只有冷启动才等：进程本来就在（在前台 already-running、从后台切回 resumed）、没给包名、
    拉起失败都不等；旧式模拟器管理器不回报拉应用结果，同样不等。
    """

    return getattr(device_info, "app_launch", "") == "launched"


def task_start_gate(
    *,
    started_at: float | None,
    disk_quiet: bool,
    wait_seconds: Any,
    log: Log,
) -> MaaFWTaskStartGate:
    """本轮刚启动的游戏，第一个任务最晚可下发的墙钟时刻与放行判据。

    ``started_at`` 是游戏刚起来的单调时钟时刻（None 表示游戏早就在跑），``disk_quiet`` 表示
    是模拟器把游戏冷启动的，``wait_seconds`` 是 ``Game.WaitTime`` 的原值。

    沿用 ``Game.WaitTime``，用户只需要理解一个「启动等待时间」：桌面游戏等窗口出现
    用的就是它，等画面稳定再用一次同样的上限；模拟器上从 MAS 随模拟器把游戏拉到
    前台起算。起算时刻之后已经过去的部分（窗口前置、ADB 路径解析、运行池租约、准备 job）
    先扣掉；剩下的交给 worker 在初始化完成后补足，这样 MaaFW 加载资源、连 controller、
    起 agent 的几秒到十几秒也算在等待里。worker 看到画面稳定会提前放行，这个时刻只是
    上限。游戏早就在跑时剩余为负，直接不等。

    模拟器冷启动（``disk_quiet``）时 worker 按「画面有内容、读盘停下来」提前放行，到这个
    时刻还是黑屏就继续等。这时剩余为负也照样给时刻，让 worker 做黑屏检查。
    """

    return MaaFWTaskStartGate(
        not_before=_task_start_not_before(started_at, disk_quiet, wait_seconds, log),
        mode=TASK_START_GATE_DISK_QUIET if disk_quiet else TASK_START_GATE_SCREEN,
    )


def _task_start_not_before(
    started_at: float | None, disk_quiet: bool, wait_seconds: Any, log: Log
) -> float | None:
    if started_at is None:
        return None
    settle = max(0, int(wait_seconds or 0))
    if settle <= 0:
        return None
    remaining = settle - (time.monotonic() - started_at)
    if disk_quiet:
        log(
            f"模拟器冷启动游戏，最多等 {settle}s 再下发任务，画面出来且读盘停下来即提前；"
            f"剩余约 {max(remaining, 0):.0f}s（与 MaaFW 初始化并行）"
        )
        return time.time() + remaining
    if remaining <= 0:
        return None
    log(
        f"游戏窗口出现后最多等 {settle}s 再下发任务，画面稳定即提前；"
        f"剩余约 {remaining:.0f}s（与 MaaFW 初始化并行）"
    )
    return time.time() + remaining


# ---------------------------------------------------------------------------
# ADB：游戏包名、adb 路径、控制档案、截图与输入方式
# ---------------------------------------------------------------------------


async def choose_game_package(
    manual_package: Any, plan: MaaFWRunPlan | None, *, log: Log
) -> str:
    """这次要不要顺带把游戏拉起来，拉哪个包。返回空串表示只开模拟器。

    ``manual_package`` 是脚本配置 ``Game.PackageName`` 的原值。填了就以它为准：从项目里认
    包名是启发式的（``StartApp`` 只是约定，不是 interface 规格里的字段），用户必须有办法
    推翻它。

    认不出来不是错误——很多项目本来就自己在 pipeline 里开游戏。但要让用户看得见
    为什么没启动，否则「填了没反应」和「没填也没反应」在界面上长得一模一样。
    """
    manual = str(manual_package or "").strip()
    if manual:
        log(f"游戏包名: {manual}（脚本配置）")
        return manual

    if plan is None:
        return ""

    resolution = await asyncio.to_thread(
        resolve_game_package,
        [
            Path(item.resolved)
            for item in plan.resource.paths
            if item.exists and item.isDir
        ],
        [task.pipelineOverride for task in plan.tasks if task.pipelineOverride],
    )

    if resolution.reason == "resolved":
        log(f"游戏包名: {resolution.package}（从项目识别）")
        return resolution.package

    if resolution.reason == "ambiguous":
        log(
            f"项目里识别到多个游戏包名（{'、'.join(resolution.candidates)}），"
            "无法确定用哪个，本次不随模拟器启动游戏；"
            "需要的话在托管管理页填写游戏包名"
        )
    else:
        log(
            "未能从项目里识别出游戏包名，本次不随模拟器启动游戏；"
            "需要的话在托管管理页填写游戏包名"
        )
    return ""


async def resolve_adb_path(
    emulator: Any,
    device_uid: str,
    *,
    configured_path: Any,
    device_info: DeviceInfo | None,
    log: Log,
) -> str | None:
    """宿主这边能定下的 adb 路径：脚本配置、模拟器管理器、模拟器安装目录，依次试。

    ``configured_path`` 是脚本配置 ``Device.AdbPath`` 的原值，``device_info`` 只用来在日志里
    带上模拟器标题。都不成时返回 None，交给 MaaFW Runner 按设备地址发现；调用方只缓存
    非 None 的结果。
    """
    configured = str(configured_path or "").strip()
    if configured and Path(configured).exists():
        log(f"ADB 路径选择: 脚本配置; 路径={configured}")
        return configured
    if configured:
        log(f"脚本配置的 ADB 路径不存在，继续自动解析: {configured}")

    get_adb_path = getattr(emulator, "get_adb_path", None)
    if callable(get_adb_path):
        with suppress(Exception):
            manager_adb_path = get_adb_path()
            if manager_adb_path is not None:
                manager_adb_path = Path(manager_adb_path)
                if manager_adb_path.exists():
                    path = str(manager_adb_path)
                    log(f"ADB 路径选择: MAS 模拟器管理器; 路径={path}")
                    return path

    derived_path = await _derive_adb_path_from_emulator(emulator, device_uid)
    if derived_path is not None and derived_path.exists():
        path = str(derived_path)
        log(f"ADB 路径选择: 模拟器安装目录; 路径={path}")
        return path

    title = f"（{device_info.title}）" if device_info else ""
    log(f"主程序未解析到 ADB 路径{title}，将由 MaaFW Runner 按设备地址发现")
    return None


async def _derive_adb_path_from_emulator(emulator: Any, device_uid: str) -> Path | None:
    if emulator is None:
        return None
    ref = emulator.resolve_device(device_uid)
    if ref.emulator_type == "avd":
        info = await emulator.avd_adb_info(device_uid)
        return Path(info.adb_exe)
    return emulator.get_adb_path()


async def resolve_login_adb_path(
    address: str, adb_path: str | None, *, ask_toolkit: bool, log: Log
) -> str | None:
    """在宿主统一解析登录钩子和 worker 使用的 ADB 路径。

    ``ask_toolkit`` 由调用方算好：有地址、宿主没定下路径、且这个托管类型有运行前登录钩子
    时为真，这时按地址问 MaaFW Toolkit 要一个；否则原样返回 ``adb_path``。
    """
    if ask_toolkit:
        adb_path = await asyncio.to_thread(find_adb_path_by_toolkit, address)
        if adb_path:
            log(f"ADB 路径选择: MaaFW Toolkit 按地址发现; 路径={adb_path}")

    return adb_path


def find_adb_path_by_toolkit(address: str) -> str | None:
    """按设备地址问 MaaFW Toolkit 要 adb 路径（与 worker 的发现规则同一套）。

    :func:`resolve_adb_path` 只认脚本配置、模拟器管理器与安装目录；通用模拟器把 adb 放在
    别的文件名下（BlueStacks 的 ``HD-Adb.exe``）时推不出来，而 MaaFW Runner 本来就会
    按地址发现。登录钩子跑在 Runner 之前，先在这里补上，别让钩子退回 PATH 里的 ``adb``。
    拿不到（没装 Toolkit、列表里没有这个地址）就返回 ``None``，调用方保持原行为。
    """

    if not address:
        return None
    try:
        from maa.toolkit import Toolkit
    except Exception:  # noqa: BLE001 - 没有 Toolkit 时交给 Runner 自己发现
        return None
    with suppress(Exception):
        for device in Toolkit.find_adb_devices():
            if str(getattr(device, "address", "")) != address:
                continue
            path = Path(str(getattr(device, "adb_path", "") or ""))
            if path.name and path.exists():
                return str(path)
    return None


async def build_adb_control_profile(
    emulator: Any, *, target_id: str, device_uid: str, log: Log
) -> MaaFWAdbControlProfile:
    """解析当前模拟器的 EmulatorExtras 能力，并构造 MuMu/雷电 controller extras 配置。

    ``target_id`` / ``device_uid`` 是托管绑定的游戏目标与设备 uid（未选为 ``-``）。
    """
    if target_id == "-" or device_uid in ("", "-"):
        return MaaFWAdbControlProfile(None, False, False, {})

    # ModAVD 在下面的 try 之外：它没有退回默认配置这条路（截图不许回落到普通 adb），
    # 构造不出 AVDExtras 配置就直接报错
    avd_ref = None
    with suppress(Exception):
        resolve_device = getattr(emulator, "resolve_device", None)
        avd_ref = resolve_device(device_uid) if resolve_device else None
    if avd_ref is not None and avd_ref.emulator_type == "avd":
        return await build_avd_adb_profile(emulator, device_uid, log=log)

    try:
        # 先问管理器这个设备号的真实归属。持久化的 Info.Type 在纳管多个安装时
        # 不等于设备的真实类型, 直接读它会让雷电专用截图被跳过——而雷电上普通
        # ADB 截图取不到游戏的 GPU 渲染层, 识别会全程无命中。
        device_ref = emulator.resolve_device(device_uid)
        emulator_type = device_ref.emulator_type
        emulator_path = Path(device_ref.manager_path)
        native_index = device_ref.native_index
        # build_adb_emulator_extra_capabilities 通过 find_spec 探测运行时 maa，
        # 不会把 maa 载入 sys.modules，满足导入边界约束；返回 {type: {screencap,input}}。
        capabilities = build_adb_emulator_extra_capabilities()
        capability = capabilities.get(emulator_type, {})
        screencap_extra = bool(capability.get("screencap", False))
        input_extra = bool(capability.get("input", False))
        if emulator_type == "ldplayer":
            # 没有截图增强也要进来：文本输入改走 ldconsole 与截图增强无关
            config = await ldplayer_maafw_adb_extra(
                emulator,
                device_uid,
                manager_path=emulator_path,
                native_index=native_index,
                with_extras=screencap_extra,
            )
            return MaaFWAdbControlProfile(
                emulator_type, screencap_extra, input_extra, config
            )
        if emulator_type == "mumu" and (screencap_extra or input_extra):
            config = mumu_maafw_adb_extra(
                device_uid, manager_path=emulator_path, native_index=native_index
            )
            return MaaFWAdbControlProfile(
                emulator_type, screencap_extra, input_extra, config
            )
        return MaaFWAdbControlProfile(emulator_type, screencap_extra, input_extra, {})
    except Exception as exc:
        logger.warning(f"构造 MaaFW ADB extra 配置失败，使用默认配置: {exc}")

    return MaaFWAdbControlProfile(None, False, False, {})


async def build_avd_adb_profile(
    emulator: Any, device_uid: str, *, log: Log
) -> MaaFWAdbControlProfile:
    """ModAVD：只给 AVDExtras 截图，推流开关走私有 adb server。任何一步不成立都抛错。

    adb 程序、私有 server 端口、控制台端口都问 modavd（``modavd list``；根目录可以设 ``portBase``
    换一段端口），截图共享内存按控制台端口命名。额外配置本身由模拟器插件经
    ``maafw_adb_extra`` 给出。
    """
    capability = build_adb_emulator_extra_capabilities().get("avd", {})
    if not capability.get("screencap"):
        raise RuntimeError(
            "当前 MaaFW 运行时不带模拟器截图增强（MaaAdbControlUnit），"
            "ModAVD 上截图不能回落到普通 adb，本次不运行"
        )
    adb_info = await emulator.avd_adb_info(device_uid)
    if adb_info is None:
        raise RuntimeError(f"设备 {device_uid} 不是 ModAVD 实例")
    adb_path = Path(adb_info.adb_exe)
    if not adb_path.is_file():
        raise RuntimeError(f"找不到 ModAVD 的 adb：{adb_path}")
    console = adb_info.ports.console
    config = await emulator.maafw_adb_extra(device_uid)
    log(f"ModAVD 截图走 AVDExtras（共享内存 SHM_videmulator{console}），不回落普通 adb")
    return MaaFWAdbControlProfile("avd", True, False, config)


async def ldplayer_maafw_adb_extra(
    emulator: Any,
    device_uid: str,
    *,
    manager_path: Path,
    native_index: str | None = None,
    with_extras: bool = True,
) -> dict[str, Any]:
    """雷电的 ADB controller config：截图增强 extras + 走 ldconsole 的文本输入。

    与 SDK 的 ``maafw_adb_extra`` 同形（输入设备 uid，输出额外配置的普通数据），以后原样
    交给雷电的模拟器适配插件；``manager_path`` / ``native_index`` 是 ``resolve_device`` 给的
    安装与原生实例号，插件自己按 uid 就拿得到。

    ``with_extras`` 为 False（运行时 maa 没有雷电截图增强）时不写 ``extras``，
    但文本输入命令照写：它只依赖安装目录里的 ``ldconsole.exe``。
    """
    emulator_root = manager_path.parent
    # 兜底必须用原生索引: 雷电 extras 的 index 与 ADB 序列号都按它算,
    # 纳管多个安装时设备号与原生索引不是一回事。
    index = int(native_index if native_index is not None else device_uid)
    pid = 0

    # get_device_info 仅存在于部分模拟器管理器（雷电有，MuMu 无），
    # 且 list2 可能超时/异常，故整体兜底为实例索引 + pid=0。
    if emulator is not None:
        try:
            devices = await emulator.get_device_info(device_uid)
            device = devices.get(device_uid)
            if device is not None:
                index = device.idx
                pid = device.pid
        except Exception as exc:
            logger.warning(f"获取雷电模拟器 extra 信息失败，使用实例索引兜底: {exc}")

    ld_config: dict[str, Any] = {
        "enable": True,
        "index": index,
        "path": str(emulator_root).replace("\\", "/"),
        "pid": pid,
    }
    ld_library = emulator_root / "ldopengl64.dll"
    if ld_library.exists():
        ld_config["lib"] = str(ld_library).replace("\\", "/")

    config: dict[str, Any] = {}
    if with_extras:
        config["extras"] = {"ld": ld_config}
    command = _ldplayer_input_text_command(emulator_root, index)
    if command is not None:
        config["command"] = {"InputText": command}
    return config


def mumu_maafw_adb_extra(
    device_uid: str,
    *,
    manager_path: Path,
    native_index: str | None = None,
) -> dict[str, Any]:
    """MuMu 的 ADB controller config（截图 / 输入增强 extras）。

    与 SDK 的 ``maafw_adb_extra`` 同形，以后原样交给 MuMu 的模拟器适配插件；
    ``manager_path`` / ``native_index`` 同 :func:`ldplayer_maafw_adb_extra`。
    """
    emulator_root = manager_path.parent.parent
    # 与雷电分支同口径: MuMu extras 的 index 也按原生索引算,
    # 纳管多个安装时设备号与原生索引不是一回事。
    mumu_config: dict[str, Any] = {
        "enable": True,
        "index": int(native_index if native_index is not None else device_uid),
        "path": str(emulator_root).replace("\\", "/"),
    }
    for library in (
        emulator_root / "nx_main" / "sdk" / "external_renderer_ipc.dll",
        emulator_root / "shell" / "sdk" / "external_renderer_ipc.dll",
    ):
        if library.exists():
            mumu_config["lib"] = str(library).replace("\\", "/")
            break

    return {
        "extras": {
            "mumu": mumu_config,
        },
    }


def adb_ready_timeout(emulator: Any) -> int | None:
    """按该模拟器自己的 Info.MaxWaitTime 决定等 adb 的耐心。

    LDPlayer.open() 在 in_android==1 之后只 sleep 3 秒就返回「启动完成」
    （不传 package_name 时不走 30 秒分支），此时 Android 里的 adbd 常常还
    没起来。第一层把等待交给项目外壳，内置运行这条等待是唯一的缓冲，
    插件版固定 30 秒在冷启动的雷电上不够用。

    取不到模拟器配置时返回 None，由 runner 用自己的常量兜底。
    """

    config = getattr(emulator, "config", None) if emulator is not None else None
    if config is None:
        return None
    try:
        value = int(config.Info.MaxWaitTime)
    except Exception:  # noqa: BLE001 - 取不到就交给 runner 兜底
        return None
    return value if value > 0 else None


def adb_screencap_methods(profile: MaaFWAdbControlProfile, configured: Any) -> int:
    """截图方式位掩码。``configured`` 是 ``Device.AdbScreencapMethods`` 的原值，只在
    非 MuMu / 雷电 / ModAVD 时用。"""
    extra_method = _ADB_SCREENCAP_EMULATOR_EXTRAS
    if profile.emulator_type == "avd":
        # ModAVD 只给 AVDExtras，不让测速有机会选普通 adb（约 250 ms）
        return extra_method
    if profile.emulator_type in {"ldplayer", "mumu"}:
        default_methods = _ADB_SCREENCAP_DEFAULT
        if profile.screencap_extra:
            # 只给模拟器增强这一种，与第一层写死的 ScreencapMethods=64 一致。
            #
            # 此前返回的是 default_methods | extra_method，而 -57 本身已含
            # 1<<6，等于把全部方法交给 MaaFW 测速。雷电上 ADB 系截图
            # （RawWithGzip 等）拿不到游戏的 GPU 渲染层：图有正常的
            # 1280x720，内容却是空的，于是识别全程无命中、一次点击都发不出，
            # 每个任务空转到超时。测速只比快慢、不比对不对，必然选错。
            return extra_method
        return _remove_method(default_methods, extra_method, default_methods)
    return _remove_method(
        int(configured),
        extra_method,
        _remove_method(_ADB_SCREENCAP_DEFAULT, extra_method, _ADB_SCREENCAP_DEFAULT),
    )


def adb_input_methods(profile: MaaFWAdbControlProfile, configured: Any) -> int:
    """输入方式位掩码。``configured`` 是 ``Device.AdbInputMethods`` 的原值，只在
    非 MuMu / 雷电 / ModAVD 时用。"""
    extra_input_method = _ADB_INPUT_EMULATOR_EXTRAS
    if profile.emulator_type == "mumu" and profile.input_extra:
        return _ADB_INPUT_ALL
    if profile.emulator_type == "ldplayer" and _has_input_text_command(profile.config):
        # 文本已改走 ldconsole，见 _ADB_INPUT_LDPLAYER_CONSOLE_TEXT
        return _ADB_INPUT_LDPLAYER_CONSOLE_TEXT
    if profile.emulator_type in {"ldplayer", "mumu", "avd"}:
        # ModAVD：AVDExtras 没有输入，默认会选中 Maatouch（官方镜像上 minitouch 不可用）
        return _ADB_INPUT_DEFAULT

    configured_methods = int(configured)
    if not profile.input_extra:
        return _remove_method(
            configured_methods,
            extra_input_method,
            _ADB_INPUT_DEFAULT,
        )
    return configured_methods


def build_adb_device_config(
    *,
    address: str,
    adb_path: str | None,
    profile: MaaFWAdbControlProfile,
    device_info: DeviceInfo | None,
    configured_screencap_methods: Any,
    configured_input_methods: Any,
    ready_timeout: int | None,
) -> MaaFWDeviceConfig:
    """ADB 设备配置。两个 ``configured_*`` 是脚本配置里截图 / 输入方式的原值。"""
    return MaaFWDeviceConfig(
        type="Adb",
        adbPath=adb_path,
        address=address,
        screencapMethods=adb_screencap_methods(profile, configured_screencap_methods),
        inputMethods=adb_input_methods(profile, configured_input_methods),
        config=profile.config,
        adbReadyTimeout=ready_timeout,
        emulatorPid=getattr(device_info, "process_id", None),
        emulatorStartedAt=getattr(device_info, "process_started_at", None),
    )


def _remove_method(methods: int, method: int, fallback: int) -> int:
    """从位掩码中剔除 method 位；若结果为 0（无可用方法）则回退到 fallback。"""
    filtered = methods & ~method
    return filtered or fallback


def _ldplayer_input_text_command(emulator_root: Path, index: int) -> list[str] | None:
    """雷电文本输入改走 ``ldconsole action --key call.input`` 的 adb config 命令。

    MaaFW 的 ``AdbShellInput`` 按 ``config.command.InputText`` 的 argv 起子进程，
    ``{TEXT}`` 由它替换成待输入文本；首元素不必是 adb。ldconsole 成功时无输出、
    返回 0，正好满足 MaaFW「输出为空即成功」的判据；索引错了它会打印错误，
    MaaFW 就把这次 InputText 判失败，让节点失败而不是像 Maatouch 那样静默重打。
    索引必须是雷电原生实例号（与 extras 同口径）。找不到 ldconsole 就返回 None，
    调用方维持原来的 Maatouch 路径。
    """
    console = emulator_root / "ldconsole.exe"
    if not console.is_file():
        return None
    return [
        str(console).replace("\\", "/"),
        "action",
        "--index",
        str(index),
        "--key",
        "call.input",
        "--value",
        "{TEXT}",
    ]


def _has_input_text_command(config: dict[str, Any]) -> bool:
    command = config.get("command")
    return isinstance(command, dict) and bool(command.get("InputText"))


# ---------------------------------------------------------------------------
# Win32：窗口句柄、截图 / 鼠标 / 键盘方式
# ---------------------------------------------------------------------------


def find_controller(
    interface_model: MaaFWInterface, controller_name: str
) -> MaaFWController:
    controller = next(
        (item for item in interface_model.controller if item.name == controller_name),
        None,
    )
    if controller is None:
        raise RuntimeError(f"未找到 controller: {controller_name}")
    return controller


def match_controller_windows(controller: MaaFWController) -> list[Any]:
    # 插件形态下先查 maafw.controller.win32 服务契约再回退到直接实例化；
    # 树内没有服务契约层，直连实现（移植指南 §4 规则 4）
    service = MaaFWWin32ControllerService()
    controller_payload = controller.model_dump(mode="json", by_alias=True)
    return list(service.match_controller_windows(controller_payload))


async def list_desktop_window_matches(controller: MaaFWController):
    from app.task.desktop_session_worker import request_desktop_action

    desktop = desktop_process_target.get()
    if desktop is None:
        raise RuntimeError("桌面分身会话未配置")
    _, matches = await request_desktop_action(
        desktop,
        "maafw_windows",
        {"controller": controller.model_dump_json(by_alias=True)},
    )
    return matches


async def match_windows_in_session(controller: MaaFWController):
    if desktop_process_target.get() is None:
        return await asyncio.to_thread(match_controller_windows, controller)
    return [
        MaaFWWin32Window(*item[:3])
        for item in await list_desktop_window_matches(controller)
    ]


async def resolve_window_handle(
    controller: MaaFWController, configured_hwnd: Any, *, log: Log
) -> int:
    """要控制的窗口句柄：配置里填了句柄就用它（桌面分身里先确认它在分身内），否则按
    interface 的窗口规则匹配，取第一个。``configured_hwnd`` 是 ``Device.HWnd`` 的原值。"""
    parsed_hwnd = optional_int(configured_hwnd)
    if parsed_hwnd:
        if (desktop := desktop_process_target.get()) is not None:
            from app.task.desktop_session_worker import request_desktop_action

            _, exists = await request_desktop_action(
                desktop, "maafw_windows", {"hwnd": str(parsed_hwnd)}
            )
            if not exists:
                raise RuntimeError("配置的窗口句柄不在桌面分身内")
        return parsed_hwnd
    if not controller_has_window_rules(controller):
        raise RuntimeError(WIN32_NO_WINDOW_RULES_MESSAGE)
    matches = await match_windows_in_session(controller)
    if not matches:
        raise RuntimeError("未找到匹配 MaaFW Win32 controller 的窗口")
    if len(matches) > 1:
        # 仍取第一个（行为不变），但让用户看得见：多开、同名的启动器 / 浏览器
        # 标签页都会命中同一条正则，接错窗口时日志里要能找到原因。
        candidates = "; ".join(
            f"hWnd={item.hWnd}, class={item.className}, title={item.windowName}"
            for item in matches
        )
        log(
            f"控制器 {controller.name} 的窗口规则匹配到 {len(matches)} 个窗口，"
            f"本次使用第一个（hWnd={matches[0].hWnd}）。候选: {candidates}。"
            "接错窗口时请先关掉多余的同名窗口再运行"
        )
    return int(matches[0].hWnd)


def build_win32_device_config(
    controller: MaaFWController,
    hwnd: int,
    *,
    configured_screencap_method: Any,
    configured_mouse_method: Any,
    configured_keyboard_method: Any,
    log: Log,
) -> MaaFWDeviceConfig:
    """Win32 设备配置。三个 ``configured_*`` 是脚本配置里截图 / 鼠标 / 键盘方式的原值，
    非 0 时优先于 interface 里写的。"""
    win32_config = controller.win32
    mouse = win32_config.mouse if win32_config else None
    keyboard = win32_config.keyboard if win32_config else None
    if mouse is None and keyboard is None and win32_config is not None:
        # MFAA 的写法：只写 input 时鼠标、键盘都用它
        mouse = keyboard = win32_config.input
    return MaaFWDeviceConfig(
        type="Win32",
        hWnd=hwnd,
        screencapMethod=resolve_win32_method(
            configured_screencap_method,
            win32_config.screencap if win32_config else None,
            _WIN32_SCREENCAP_METHODS,
            "DXGI_DesktopDup",
            label=f"controller {controller.name} 的 Win32 截图方式",
            warn=log,
            combinable=True,
        ),
        mouseMethod=resolve_win32_method(
            configured_mouse_method,
            mouse,
            _WIN32_INPUT_METHODS,
            "Seize",
            label=f"controller {controller.name} 的 Win32 鼠标输入方式",
            warn=log,
        ),
        keyboardMethod=resolve_win32_method(
            configured_keyboard_method,
            keyboard,
            _WIN32_INPUT_METHODS,
            "Seize",
            label=f"controller {controller.name} 的 Win32 键盘输入方式",
            warn=log,
        ),
    )


def optional_int(value: Any) -> int | None:
    if value in (None, "", "-"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def resolve_win32_method(
    configured_value: Any,
    interface_method: str | list[Any] | int | None,
    method_values: dict[str, int],
    default_name: str,
    *,
    label: str = "Win32 控制方式",
    warn: Callable[[str], None] | None = None,
    combinable: bool = False,
) -> int:
    """托管级配置的数值优先，其次 interface 里写的名字，最后是默认方式。

    名字不认识时退回默认方式并**告警**：以前是静默换成 DXGI_DesktopDup / Seize，
    项目要的后台截图 / 后台输入悄悄变成前台，用户只看到游戏被抢了鼠标。

    名字大小写不敏感（MFAA 用 ``Enum.TryParse(ignoreCase)``）；可以写成数组（MXU）
    或逗号 / ``|`` 分隔（MFAA 的组合名写法），也可以是旧版整数。截图方式
    （``combinable``）按位或合并；输入方式原生层只能选一个，给了多个取第一个并告警。
    认得的值是不是当前原生库支持的，仍由 worker 的 ``_supported_win32_method`` 再判。
    """

    default = method_values[default_name]
    configured = optional_int(configured_value) or 0
    if configured:
        return configured
    tokens = _win32_method_tokens(interface_method)
    if not tokens:
        return default
    report = warn or logger.warning
    by_name = {name.casefold(): (name, value) for name, value in method_values.items()}
    resolved: list[tuple[str, int]] = []
    unknown: list[str] = []
    for token in tokens:
        if isinstance(token, int):
            if token > 0:
                resolved.append((str(token), token))
            else:
                unknown.append(str(token))
            continue
        if token.isascii() and token.isdigit():
            # 与整数写法同口径：0 不是任何方式（worker 对 <= 0 直接放行，交下去就是
            # 「没有输入方式」），按无法识别处理。
            if int(token) > 0:
                resolved.append((token, int(token)))
            else:
                unknown.append(token)
            continue
        hit = by_name.get(token.casefold())
        if hit is None:
            unknown.append(token)
        else:
            resolved.append(hit)
    if not resolved:
        report(
            f"MaaFW interface 里 {label}「{_describe_win32_method(interface_method)}」"
            f"无法识别，已改用默认的 {default_name}"
        )
        return default
    if unknown:
        report(
            f"MaaFW interface 里 {label}中的「{'、'.join(unknown)}」无法识别，已忽略"
        )
    if combinable:
        value = 0
        for _, item in resolved:
            value |= item
        return value
    if len(resolved) > 1:
        report(
            f"MaaFW interface 里 {label}写了多个（"
            f"{'、'.join(name for name, _ in resolved)}），输入方式只能选一个，"
            f"已取第一个 {resolved[0][0]}"
        )
    return resolved[0][1]


def _win32_method_tokens(value: Any) -> list[str | int]:
    """把 interface 里的 Win32 方法声明拆成一个个名字 / 整数（空的丢掉）。"""

    if value is None or isinstance(value, bool):
        return []
    if isinstance(value, int):
        return [value]
    items = value if isinstance(value, list) else [value]
    tokens: list[str | int] = []
    for item in items:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            tokens.append(item)
            continue
        for part in re.split(r"[,|]", str(item)):
            part = part.strip()
            if part:
                tokens.append(part)
    return tokens


def _describe_win32_method(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    return str(value)
