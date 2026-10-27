#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, version 3 or (at your option)
#   any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


"""各专项自动代理共用的日志推送与进程查询小工具。

BAAH / Okww / OkNte / BetterGI / ZzzOd 在调度台日志与 log_box 采集上做的是同一
件事（向调度台追加一行、把采集节点写进当前用户推送日志），此前每家各存一份逐字
相同的实现；Okww / OkNte / ZzzOd 还各自复制了启动参数拆分与按进程名查 PID。这里
按统一语义各留一份。

``push_dispatch_log`` / ``append_push_log`` 只要求传入持有对应属性的对象，不引入
基类继承——``script_info`` 与 ``cur_user_item`` 由各专项自己持有（见各 AutoProxy 的
``self.script_info = ...``），放进 TaskExecuteBase 会把专项语义上提到共享模型层。
"""

from __future__ import annotations

import asyncio
import shlex
from collections.abc import Callable, Iterable

import psutil

from app.services import System
from app.utils import constants as _utils_constants
from app.utils import get_logger

logger = get_logger("专项进程清理")

__all__ = [
    "append_push_log",
    "find_pids_by_name",
    "kill_pids",
    "kill_pids_by_name",
    "push_dispatch_log",
    "quick_config_takeover",
    "read_config_base",
    "resolve_config_base",
    "split_args",
    "user_uses_native_base",
    "user_uses_quick_config",
]


def split_args(raw: object) -> list[str]:
    """按 shell 规则拆分启动参数（引号只用于分组，反斜杠原样保留，空串返回空列表）。

    ``shlex.split(posix=False)`` 会把引号留在词元里（``"a b"`` 拆成 ``'"a b"'``），
    交给 CreateProcess 后游戏收到的是一个带引号的参数，多半当无效参数丢掉；而配置
    校验用的 ``ArgumentValidator`` 走的是 posix 模式，界面上看着一切正常，于是这类
    参数只在运行时静默失效。这里改成 posix 解析但关掉转义处理——Windows 路径里的
    反斜杠不能被当转义符吃掉。
    """

    value = str(raw or "").strip()
    if not value:
        return []

    lexer = shlex.shlex(value, posix=True)
    lexer.whitespace_split = True
    lexer.escape = ""
    return list(lexer)


def find_pids_by_name(process_name: str) -> list[int]:
    """按进程名收集 PID（同步全进程扫描，调用方放到线程里跑）。"""

    pids: list[int] = []
    for process in psutil.process_iter(["name"]):
        try:
            if process.info["name"] == process_name:
                pids.append(process.pid)
        except psutil.Error:
            continue
    return pids


async def kill_pids(pids: Iterable[int]) -> int:
    """逐个结束已确认归属的进程，返回失败数；单个失败不阻断后续清理。"""

    failed = 0
    for pid in pids:
        try:
            if not await System.kill_process_by_pid(pid):
                failed += 1
        except Exception as exc:
            failed += 1
            logger.opt(exception=True).warning(f"结束进程失败 PID: {pid}, {exc}")
    return failed


async def kill_pids_by_name(process_name: str) -> int:
    """在线程中按名收集 PID，再结束进程并返回失败数。"""

    return await kill_pids(await asyncio.to_thread(find_pids_by_name, process_name))


async def push_dispatch_log(script_info: object, line: str) -> None:
    """向调度台追加流程日志（赋值 script_info.log 会触发 WebSocket 推送）。"""

    prev = script_info.log
    script_info.log = f"{prev}\n{line}" if prev else line
    # 让出事件循环：WebSocket 推送由赋值触发，不等待可能把多行攒成一次推送
    await asyncio.sleep(0)


def append_push_log(cur_user_item: object, log_type: str, text: str, ts: float) -> None:
    """sink：把 log_box 采集结果写入当前用户的推送日志（供调度器聚合到报告）"""

    cur_user_item.push_log.append((log_type, text, ts))


# ── base 来源三态（shared / independent / native）与快速配置 ───────────────
# 来源决定「谁拥有本次运行的配置」：shared=脚本级共享配置，independent=MAS 侧
# 按用户独立配置，native=直接用脚本安装目录里的原生配置。快速配置
# （Info.IfQuickConfig）是**独立于来源**的用户级开关：按用户保存、不随来源派生，
# 任何来源下都可开关。开启时把该用户面板值覆盖到所选 base，关闭时保留 base 配置；
# 必要的启动、模拟器与恢复流程不属于快速配置。写入和恢复仍由各专项按自身架构负责。
# （旧字面量 脚本/用户/直控 与更早的「简洁/详细/自定义」由模型层
# Base 字段声明加载时归一，见 app/models/config/script.py。）
#
# 例外：BetterGI 用户页已隐藏该开关，改由 Info.Base 派生（native=关，
# shared/independent=开），见 app/models/config.py 的 BetterGIUserConfig.load。
# 即 native 下它恒为关 ⇒ AutoProxy 的 writes_native_config 不可达
# （保留实现，将来恢复开关可直接复用）。

# 取值只在 app.utils.constants 定义一处，这里按专项层习惯名再导出
CONFIG_BASE_SHARED = _utils_constants.BASE_SHARED
CONFIG_BASE_INDEPENDENT = _utils_constants.BASE_INDEPENDENT
CONFIG_BASE_NATIVE = _utils_constants.BASE_NATIVE


def read_config_base(config: object, default: str = CONFIG_BASE_INDEPENDENT) -> str:
    """读取用户配置的 Info.Base，未知值回落到 shared/independent（绝不回落成 native）。

    native 跳过 MAS 来源导入，因此未知值不能静默解释成 native。
    """

    if config is None:
        return default
    try:
        raw = config.Info.Base  # type: ignore[attr-defined]
    except (AttributeError, KeyError, TypeError):
        return default
    # 存量配置里可能还是旧来源字面量（脚本/用户/直控），一并归一
    base = _utils_constants.normalize_base_source(raw)
    if base in (CONFIG_BASE_SHARED, CONFIG_BASE_INDEPENDENT, CONFIG_BASE_NATIVE):
        return base
    return default


def resolve_config_base(
    config: object, default: str = CONFIG_BASE_INDEPENDENT
) -> tuple[str, bool]:
    """返回 (base 来源, 是否原生)，供各专项在同一处同时判定两件事。"""

    base = read_config_base(config, default)
    return base, base == CONFIG_BASE_NATIVE


def user_uses_native_base(config: object) -> bool:
    """该用户是否使用外侧原生配置作为 base。"""

    return read_config_base(config, CONFIG_BASE_SHARED) == CONFIG_BASE_NATIVE


def user_uses_quick_config(config: object, default: bool = True) -> bool:
    """读取用户级快速配置开关（Info.IfQuickConfig），与配置来源完全独立。

    按用户保存的独立布尔字段，不随来源派生；默认开启（与模型层
    BoolValidator 默认一致）。这里只判定开关本身，来源导入由各专项负责。
    """

    if config is None:
        return default
    try:
        raw = config.Info.IfQuickConfig  # type: ignore[attr-defined]
    except (AttributeError, KeyError, TypeError):
        return default
    return bool(raw) if raw is not None else default


def quick_config_takeover(
    config: object,
    write: Callable[[], None],
    *,
    enabled_default: bool = True,
) -> bool:
    """开启时覆盖面板值，关闭时保留来源配置，与来源模式无关。

    write 抛出的异常一律向上传播：覆写失败即任务失败，由调用方按各自的
    handle_pre_*_error 转成任务失败提示，本入口不吞异常、不假装成功。
    """

    if not user_uses_quick_config(config, enabled_default):
        return False
    write()
    return True
