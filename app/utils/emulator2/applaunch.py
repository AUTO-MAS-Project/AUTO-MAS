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

"""Emulator 2.0 的「带包启动」：模拟器起来之后，再把应用拉起来。

**为什么不用两家「启动模拟器时带包」的参数。** 雷电的 ``ldconsole launch --packagename``
和 MuMu 的 ``control launch -pkg`` 看着能一步到位，实际有两个硬伤：

- **模拟器已经在跑时整条参数被吞掉。** 两家的 ``open`` 都是先查状态、在线就直接
  返回，包名根本没机会被用上。MAS 里模拟器常常是上一个用户留下来的，于是「带包
  启动」偏偏在最需要它的场景里一次都不生效。
- **返回码只代表命令被收下了**，不代表应用真起来了；两家都不提供「起没起来」的回执。

所以这里拆成两步：先让模拟器在线（仍交给各家原生 ``launch``，但**不带包名**），
再单独把应用拉起来，并**确认它真的到了前台**。

**第二步为什么三路齐发。** 拉应用有三条路，各有各的坑，实测（明日方舟）：

===============  ===========  ===========
路子             MuMu 6       雷电 14
===============  ===========  ===========
厂商 CLI         0.06s        0.06s
``monkey``       0.05s        **不存在**（返回码 127）
``am start``     0.03s        0.06s
===============  ===========  ===========

雷电的镜像里根本没有 ``monkey`` 这个二进制，所以任何「以 monkey 为主、其余兜底」的
排法在雷电上都要先白等一轮超时。三条都是同一个 MAIN/LAUNCHER 意图，Android 会把重复
的那几次归并成「把已有任务提到前台」——实测齐发只产生一个 task，不会重复拉起——
那就没有理由排队，一起发出去再统一等一次前台即可。

对外只有一个入口 :func:`ensure_app_running`，它接「怎么执行 adb」和「怎么调厂商 CLI」
两个回调，所以整条决策链可以脱离真实模拟器测试。
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.models.config import EmulatorConfig
from app.models.emulator import DeviceBase, DeviceInfo
from app.utils import ProcessRunner, get_logger

logger = get_logger("Emulator2 应用启动")

#: 单条 adb 命令的超时。dumpsys / pm 都是设备本地查询, 卡住基本只会是 adb 自己没起来。
_ADB_TIMEOUT = 20.0

#: ``host:port`` 形式的设备要先 connect 一次, 否则 ``-s`` 找不到设备。
_ADB_CONNECT_TIMEOUT = 20.0

#: 轮询间隔。等的是「开机完成」和「应用到前台」, 秒级足够。
_POLL_SECONDS = 1.0

#: 等 Android 起完的上限。``MaxWaitTime`` 默认 300 秒、可以设到 9999, 那是留给
#: 「模拟器进程起没起来」的; 实例报在线之后系统 boot 通常几十秒内完成, 真等不到多半是
#: adb 根本连不上, 再按用户设的上限死等只会白白拖住整条代理流程。
_BOOT_TIMEOUT_CAP = 120.0

#: 等应用进前台的上限。理由同上, Activity 恢复是秒级的事。
_LAUNCH_TIMEOUT_CAP = 45.0

#: 界面上「打开游戏中心」一次点击最多等多久。实测两家都是 1 秒内到前台; 等这么久还没到,
#: 多半是商店被禁用了（此时 ``pm path`` 仍有路径, 三路启动都不会报错, 只会等到超时）。
_STORE_LAUNCH_TIMEOUT = 10.0

#: ``dumpsys activity activities`` 里表示「这个 Activity 正在前台」的几种写法。
#: 不同 Android 版本用词不一样, 全都要认——只认一种会在某些镜像上永远判成没起来。
_FOREGROUND_MARKERS = (
    "topResumedActivity=",
    "ResumedActivity:",
    "mResumedActivity:",
    "mCurrentFocus=",
)

#: 结果的原因码。调用方只需要 ``ok``, 日志和排查要看这个。
LaunchReason = Literal[
    "already-running",
    "launched",
    "not-installed",
    "no-adb",
    "no-store",
    "boot-timeout",
    "launch-timeout",
]

#: 执行一条 adb 命令的回调: ``await run(*args, timeout=...) -> (返回码, 合并输出)``。
#: 约定**永不抛异常**——执行不了就返回一个非 0 返回码, 让上层照常走超时逻辑。
AdbRunner = Callable[..., Awaitable[tuple[int, str]]]

#: 用模拟器自己的命令启动应用的回调（雷电 ``runapp`` / MuMu ``control app launch``）。
#: 结果不看——和另外两路一样, 起没起来一律以「有没有进前台」为准。
VendorLauncher = Callable[[], Awaitable[object]]


@dataclass(frozen=True)
class AppLaunchResult:
    """一次「把应用拉起来」的结果。"""

    ok: bool
    """应用是否已经在前台。"""

    reason: LaunchReason
    """走到哪一步结束的。"""

    detail: str = ""
    """给日志看的补充信息, 通常是最后一条 adb 命令的输出。"""


# ---- 纯解析 ---------------------------------------------------------------


def is_package_foreground(dumpsys_output: str, package_name: str) -> bool:
    """从 ``dumpsys activity activities`` 的输出里判断某个包是否在前台。

    判据是同一行里既出现 ``<包名>/``, 又出现任意一个前台标记——只匹配包名会把
    「最近任务里有它」也算成在前台。
    """
    component_prefix = f"{package_name}/"
    return any(
        component_prefix in line
        and any(marker in line for marker in _FOREGROUND_MARKERS)
        for line in (dumpsys_output or "").splitlines()
    )


def is_package_missing(pm_path_output: str) -> bool:
    """从 ``pm path <包名>`` 的输出里判断这个包是否**确定没装**。

    判据是「输出彻底为空」，**不能看返回码**。实测（MuMu 6 / Android 15）：

    - 装了：返回码 0，打印 ``package:/system/system_ext/priv-app/Settings/Settings.apk``
    - 没装：返回码 **1**，输出为空
    - 设备掉线：返回码同样是 1，但会打印 ``adb.exe: device '...' not found``

    后两种返回码一样，只有输出能分开；按返回码判会把掉线误报成「没装」，
    按返回码 0 判则永远判不出没装——那条分支就成了死代码。
    """
    return not (pm_path_output or "").strip()


def is_package_present(pm_path_output: str) -> bool:
    """从 ``pm path <包名>`` 的输出里判断这个包是否**确定装了**。

    与 :func:`is_package_missing` 不是互补的：设备掉线时 adb 打印
    ``adb.exe: device 'emulator-5562' not found``——既不是「空」也不是「装了」。
    2026-09-12 生产实测就栽在这里：拿「非空」当「装了」，把所有**关着的**雷电实例
    都判成了 MuMu，缓存 30 秒后实例启动时 ADB 地址被清空、MAA 直接报连接异常。
    只有真正的 ``package:`` 行才算装了。
    """
    return any(
        line.strip().startswith("package:")
        for line in (pm_path_output or "").splitlines()
    )


def parse_launch_component(resolve_output: str, package_name: str) -> str | None:
    """从 ``cmd package resolve-activity --brief <包名>`` 的输出里取启动组件。

    ``--brief`` 会在最后一行给出 ``包名/Activity``, 前面还可能有一行
    ``priority=... isDefault=true``。取不到返回 ``None``, **不猜组件名**。
    """
    component_prefix = f"{package_name}/"
    for line in reversed((resolve_output or "").splitlines()):
        stripped = line.strip()
        if stripped.startswith(component_prefix):
            return stripped
    return None


# ---- adb 执行器 -----------------------------------------------------------


def build_adb_runner(adb_path: Path | None, adb_address: str) -> AdbRunner:
    """把「哪个 adb、哪台设备」包成一个只接命令参数的执行器。

    ``adb_path`` 为 ``None`` 时回退系统 ``adb``, 与 :meth:`DeviceBase.get_adb_path`
    的约定一致。``host:port`` 形式的地址（MuMu）会在第一条命令前先 ``connect`` 一次。

    执行器**吞掉所有异常**并转成 ``(-1, 错误文本)``: 上层是轮询逻辑, 一次执行失败
    应该继续等下一轮, 而不是把整个启动流程炸掉。
    """
    program: Path | str = adb_path if adb_path is not None else "adb"
    need_connect = ":" in adb_address

    async def run(*args: str, timeout: float = _ADB_TIMEOUT) -> tuple[int, str]:
        nonlocal need_connect
        if need_connect:
            # 连不上也照样往下走: 设备可能本来就连着, 真没连上后面的命令会自己报错
            need_connect = False
            with suppress(Exception):
                await ProcessRunner.run_process(
                    program,
                    "connect",
                    adb_address,
                    timeout=_ADB_CONNECT_TIMEOUT,
                    if_merge_std=True,
                )
        try:
            result = await ProcessRunner.run_process(
                program,
                "-s",
                adb_address,
                *args,
                timeout=timeout,
                if_merge_std=True,
            )
        except Exception as e:  # noqa: BLE001 - 见 docstring: 转成返回码, 不抛
            return -1, str(e)
        return result.returncode, result.stdout.strip()

    return run


# ---- 编排 -----------------------------------------------------------------


async def _wait_boot_completed(
    run_adb: AdbRunner, deadline: float, poll_seconds: float
) -> bool:
    """等 Android 起完。

    模拟器进程在线不等于系统可用: 各家原生 ``launch`` 一返回就报在线, 此时 adb 常常
    还连不上。这里等 ``sys.boot_completed`` 变成 ``1``, 顺带把「adb 通了没」一起等了。
    """
    while True:
        code, output = await run_adb("shell", "getprop", "sys.boot_completed")
        if code == 0 and output.strip() == "1":
            return True
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(poll_seconds)


async def _wait_foreground(
    run_adb: AdbRunner, package_name: str, deadline: float, poll_seconds: float
) -> tuple[bool, str]:
    """轮询到应用出现在前台为止, 返回 (是否到前台, 最后一次输出)。"""
    output = ""
    while True:
        code, output = await run_adb("shell", "dumpsys", "activity", "activities")
        if code == 0 and is_package_foreground(output, package_name):
            return True, output
        if time.monotonic() >= deadline:
            return False, output
        await asyncio.sleep(poll_seconds)


async def ensure_app_running(
    run_adb: AdbRunner,
    package_name: str,
    *,
    boot_timeout: float,
    launch_timeout: float,
    vendor_launch: VendorLauncher | None = None,
    poll_seconds: float = _POLL_SECONDS,
    label: str = "",
) -> AppLaunchResult:
    """确保某个包在设备上跑起来并到了前台。

    顺序: 等开机完成 → 查是否安装 → 已在前台就直接返回 → 三路齐发 → 等前台。

    三条路各有各的坑（雷电没有 ``monkey``、``am start`` 要组件名、厂商 CLI 各家不同），
    但都是同一个 LAUNCHER 意图, 一起发不会重复拉起, 见模块开头的实测表。

    Parameters
    ----------
    run_adb
        执行 adb 命令的回调, 见 :data:`AdbRunner`。
    package_name
        要启动的包名。
    boot_timeout
        等 ``sys.boot_completed`` 的秒数。
    launch_timeout
        发完启动命令之后, 等应用进前台的秒数。
    vendor_launch
        用模拟器自己的命令启动应用的回调, 见 :data:`VendorLauncher`;
        ``None`` 表示这台没有可用的厂商命令, 只发 adb 那两路。
    poll_seconds
        轮询间隔。
    label
        日志前缀, 通常是设备号。

    Returns
    -------
    AppLaunchResult
        **不抛异常**: 拉不起来是「这次没成」, 不该把已经开好的模拟器一起判失败。
    """
    prefix = f"设备 #{label} " if label else ""

    if not await _wait_boot_completed(
        run_adb, time.monotonic() + boot_timeout, poll_seconds
    ):
        logger.warning(f"{prefix}等待系统启动完成超时，跳过启动 {package_name}")
        return AppLaunchResult(False, "boot-timeout")

    # 没装就别白试一轮 monkey 再等一轮前台，直接给出能照做的结论。
    # 判据见 is_package_missing：只认「输出为空」，返回码分不开没装和掉线。
    _, output = await run_adb("shell", "pm", "path", package_name)
    if is_package_missing(output):
        logger.warning(f"{prefix}未安装 {package_name}，不再尝试启动")
        return AppLaunchResult(False, "not-installed")

    code, output = await run_adb("shell", "dumpsys", "activity", "activities")
    if code == 0 and is_package_foreground(output, package_name):
        logger.info(f"{prefix}{package_name} 已在前台，无需启动")
        return AppLaunchResult(True, "already-running")

    # am start 要组件名，先问一次；问不到就少发这一路，不猜组件名
    _, resolved = await run_adb(
        "shell", "cmd", "package", "resolve-activity", "--brief", package_name
    )
    component = parse_launch_component(resolved, package_name)

    attempts: list[Awaitable[object]] = [
        run_adb(
            "shell",
            "monkey",
            "-p",
            package_name,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
        )
    ]
    if vendor_launch is not None:
        attempts.append(vendor_launch())
    if component is not None:
        attempts.append(run_adb("shell", "am", "start", "-n", component))

    logger.info(
        f"{prefix}模拟器已就绪，{len(attempts)} 路并发启动 {package_name}"
        f"{'' if component else '（解析不出启动组件，跳过 am start）'}"
    )
    # 一起发再统一等：三条都是同一个 LAUNCHER 意图，Android 会归并成一个任务
    await asyncio.gather(*attempts, return_exceptions=True)

    arrived, detail = await _wait_foreground(
        run_adb, package_name, time.monotonic() + launch_timeout, poll_seconds
    )
    if arrived:
        logger.info(f"{prefix}{package_name} 已启动")
        return AppLaunchResult(True, "launched")

    logger.warning(f"{prefix}启动 {package_name} 超时，应用未进入前台")
    return AppLaunchResult(False, "launch-timeout", detail)


# ---- 后端接线 -------------------------------------------------------------


class AppLaunchMixin(DeviceBase):
    """给 Emulator 2.0 的后端补上「模拟器起来之后再启动应用」。

    放在 MRO 里各家原生管理器**前面**，:meth:`open` 里的 ``super().open(idx)``
    落到原生实现，并**有意不把包名传下去**——理由见模块开头。

    继承 ``DeviceBase`` 只是为了让 ``getInfo`` / ``get_adb_path`` 这些依赖在签名上
    可见；``config`` 由两家后端各自的构造函数赋值，这里只声明类型。
    """

    config: EmulatorConfig

    #: 这家模拟器自带的游戏中心 / 应用商店的包名，``None`` 表示没有。
    #: 界面上「打开游戏中心」按钮走 :meth:`open_store`，靠它决定拉哪个包。
    store_package: str | None = None

    async def vendor_launch_app(self, idx: str, package_name: str) -> object:
        """用这家模拟器自己的命令启动应用。

        默认不实现，返回 ``None`` 表示这台只走 adb 两路。两家后端各自覆盖它
        （雷电 ``runapp``、MuMu ``control app launch``）。
        """
        return None

    async def prepare_launch(self, idx: str) -> None:
        """启动模拟器之前的一步。默认什么都不做，两家后端各自覆盖（雷电在这里应用「大雷主人模式」）。

        这一步失败不该拦住模拟器启动：覆盖时自己记警告；万一漏了抛出来，
        :meth:`open` 也只记一条警告继续往下走。
        """

    async def after_boot(self, idx: str, info: DeviceInfo) -> None:
        """模拟器在线之后、拉应用之前的一步。默认什么都不做（MuMu 在这里应用「大雷主人模式」）。

        约束同 :meth:`prepare_launch`。
        """

    async def open(self, idx: str, package_name: str = "") -> DeviceInfo:
        """启动设备；给了包名就在设备就绪后把应用也拉起来。

        不给包名时行为与原生实现完全一致，只开模拟器——中间多出的两个钩子默认是空的。
        """
        try:
            await self.prepare_launch(idx)
        except Exception as e:  # noqa: BLE001 - 钩子失败不拦启动
            logger.warning(f"启动前钩子失败，实例 {idx} 照常启动: {e}")
        info = await super().open(idx)
        try:
            await self.after_boot(idx, info)
        except Exception as e:  # noqa: BLE001 - 同上
            logger.warning(f"启动后钩子失败，实例 {idx} 继续: {e}")
        if package_name:
            await self.launch_app(idx, package_name, info)
        return info

    async def launch_app(
        self,
        idx: str,
        package_name: str,
        info: DeviceInfo | None = None,
        *,
        launch_timeout: float | None = None,
    ) -> AppLaunchResult:
        """在**已经在线**的设备上把应用拉起来。

        单独暴露出来是为了「模拟器本来就开着」这种场景——调用方不必为了拉个应用
        再走一遍 :meth:`open`。

        拉不起来只记警告并把结果返回，**不抛异常**：模拟器已经开好了，把整次启动
        判成失败反而更糟，脚本自己那套启动流程还有机会兜住。

        ``launch_timeout`` 是等应用进前台的秒数；不给就按 ``MaxWaitTime`` 与
        :data:`_LAUNCH_TIMEOUT_CAP` 取小。界面上一次点击触发的启动应该传一个短得多的值——
        用户在盯着按钮转圈，等不起 45 秒。
        """
        if info is None:
            info = (await self.getInfo(idx))[idx]

        if not info.adb_address:
            # 没地址就别拿 `-s ""` 去碰运气：多半是序列号被别家模拟器占了，
            # 具体原因 getInfo 已经记过一条，这里只说明本次没启动
            logger.warning(f"设备 #{idx} 没有可用的 ADB 地址，跳过启动 {package_name}")
            return AppLaunchResult(False, "no-adb")

        # 两个上限都取 min：这一步是加在原有启动流程后面的，等不到就该让位给
        # 脚本自己的启动流程，不能按 MaxWaitTime 把整条代理拖住
        max_wait = float(self.config.get("Info", "MaxWaitTime"))
        if launch_timeout is None:
            launch_timeout = min(max_wait, _LAUNCH_TIMEOUT_CAP)
        return await ensure_app_running(
            build_adb_runner(self.get_adb_path(), info.adb_address),
            package_name,
            boot_timeout=min(max_wait, _BOOT_TIMEOUT_CAP),
            launch_timeout=launch_timeout,
            vendor_launch=lambda: self.vendor_launch_app(idx, package_name),
            label=str(idx),
        )

    async def open_store(self, idx: str) -> AppLaunchResult:
        """打开这家模拟器自带的游戏中心 / 应用商店。

        给界面上的「打开游戏中心」按钮用：雷电开启「大雷主人模式」之后 launcher 会把游戏中心
        从桌面和应用列表里过滤掉（包没禁、``am start`` 照常），用户没有别的入口。
        没有商店的后端直接返回 ``no-store``，不去碰设备。
        """
        if not self.store_package:
            logger.warning(f"设备 #{idx} 所属的模拟器没有游戏中心，无法打开")
            return AppLaunchResult(False, "no-store")
        return await self.launch_app(
            idx, self.store_package, launch_timeout=_STORE_LAUNCH_TIMEOUT
        )


__all__ = [
    "AdbRunner",
    "AppLaunchMixin",
    "AppLaunchResult",
    "LaunchReason",
    "build_adb_runner",
    "ensure_app_running",
    "is_package_foreground",
    "is_package_missing",
    "parse_launch_component",
]
