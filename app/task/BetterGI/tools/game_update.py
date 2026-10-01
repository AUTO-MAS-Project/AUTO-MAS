#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""BetterGI 的原神客户端更新。

原神客户端由 BetterGI 自己启停，MAS 这边只经 ``game_info`` 拿到生效的游戏程序路径
（用户级 ``Switch.GamePath`` 优先，否则透传 BGI 全局配置），**不读 BGI 的其他私有
状态**。

本文件只做「取生效路径 → 判渠道 → 推调度台 → 决定本次任务是否继续」，查版本、下载、
打补丁与落盘都在 :mod:`app.services.genshin_updater`；**更新过程的所有叙述都由编排层
写进 app.log**，这里只把影响本轮任务命运的少数几行推到调度台，免得刷掉专项自己的日志。
两种入口共用同一条判定链：

- **自动入口**（:func:`ensure_game_updated` 默认）：任务启动游戏前按 ``Game.IfAutoUpdate``
  开关检查，查不到 / 环境不允许就放行，确知需要更新却做不了才阻断；
- **手动入口**（``manual=True``）：用户页「检查更新」由用户主动触发，跳过开关，凡 MAS
  无法自动完成的都直接抛错，由用户自己决定后续处理。

两种入口共同的行为策略：

- **开关没开就什么都不做**，连日志都不写——否则每次无关任务都要刷一行；
- **只自动应用增量包**：拿不到差分（全新安装、逐文件全量比对）时编排层会停手并给出
  明确原因，无人值守的任务不该顺手吃掉一整份客户端的流量；
- **判不出来就放行**：问不出结论、路径解析不出、渠道认不出都属于「无法判定」，旧客户端
  通常仍能登录，不该因为查不到版本就拦住用户；B 服与游戏正在运行同理，跳过而不是判失败；
- **需要更新却更新失败则阻断**：拿旧客户端撞登录只会白跑一轮，用户要先看一眼原因。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from app.models.config import BetterGIConfig, BetterGIUserConfig
from app.services.genshin_updater import UpdateKind, update_genshin_client
from app.task.BetterGI.tools import game_info
from app.utils import get_logger

logger = get_logger("原神更新 BetterGI")

__all__ = ["LogHook", "ensure_game_updated", "task_stopped"]

#: 一行面向用户的进度文案
LogHook = Callable[[str], Awaitable[None]]

#: 中止判定；为真时更新在文件批次边界收工
AbortHook = Callable[[], bool]


def task_stopped(task: object) -> bool:
    """用户是否已要求停止本任务（供更新途中在批次边界轮询）。

    只认 ``stopped_manually``：它由核心层在取消异常冒出任务主体时置位，顶层任务与 ``spawn()``
    出的子任务都走这一条路径。子任务身上没有可提前读的停止标志（顶层那个任务对象只在顶层
    ``execute()`` 里赋值），所以真按下停止时生效的是取消异常本身——它在下一个等待点打断本轮，
    已落盘的合法文件保留、版本号不写。
    """
    return bool(getattr(task, "stopped_manually", False))


#: 客户端渠道 -> 更新接口区服；不在表里的渠道不接管
_CHANNEL_TO_REGION: dict[str, str] = {
    game_info.CHANNEL_OFFICIAL: "cn",
    game_info.CHANNEL_GLOBAL: "global",
}

#: 本地客户端进程名（与 BGI 侧口径一致），用来判「游戏正在运行」
_LOCAL_PROCESS_NAMES: tuple[str, ...] = ("YuanShen.exe", "GenshinImpact.exe")


async def ensure_game_updated(
    script_config: BetterGIConfig,
    user_config: BetterGIUserConfig,
    *,
    on_log: LogHook | None = None,
    manual: bool = False,
    should_abort: AbortHook | None = None,
) -> bool:
    """接管原神客户端更新，返回本次任务能否继续。

    Args:
        manual: 是否为用户页「检查更新」手动触发。``True`` 时忽略
            ``Game.IfAutoUpdate`` 开关，且凡 MAS 无法自动完成的都抛
            ``RuntimeError``——用户主动发起就该得到明确的失败原因，而不是像自动
            流程那样静默放行。
    Returns:
        是否可以继续本次任务。``True`` 含更新成功、无需更新、以及「判不出来所以不
        打扰」；``False`` 表示确知需要更新却没做成，要用户先处理。``manual=True``
        时不会返回 ``False``，这类情况一律抛错。

    Raises:
        RuntimeError: ``manual=True`` 且无法自动完成时（路径 / 渠道不可用、游戏运行中、
            问不出结论、只能全量更新、更新失败）。
    """
    if not manual and not script_config.get("Game", "IfAutoUpdate"):
        # 开关没开是常态，什么都不写：否则每次无关任务都要刷一行
        return True

    root_path = Path(str(script_config.get("Info", "RootPath") or "."))
    user_game_path = str(user_config.get("Switch", "GamePath") or "")
    try:
        game_exe = game_info.resolve_game_exe(root_path, user_game_path)
    except Exception as error:  # noqa: BLE001
        if manual:
            raise RuntimeError(f"无法确定游戏路径：{error}") from error
        logger.warning("原神更新：解析游戏路径失败，本轮跳过 - {}", error)
        return True

    channel = game_info.detect_channel(game_exe)
    if channel == game_info.CHANNEL_BILIBILI:
        # B 服是独立渠道、版本节奏与官服不同，用官服清单更新会写坏客户端
        message = f"{channel}客户端不支持自动更新，请用官方启动器更新"
        if manual:
            raise RuntimeError(message)
        await _report(on_log, f"原神更新：{message}")
        return True

    resource = {"cn": "官服", "global": "国际服"}.get(
        _CHANNEL_TO_REGION.get(channel or "", "")
    )
    if resource is None:
        if manual:
            raise RuntimeError(
                f"未能识别客户端渠道（{game_exe}），请用官方启动器确认版本"
            )
        logger.warning("原神更新：未能识别客户端渠道（{}），本轮跳过", game_exe)
        return True

    running = game_info.find_running_game_exe(_LOCAL_PROCESS_NAMES)
    if running is not None:
        message = f"检测到游戏正在运行（{running}）"
        if manual:
            raise RuntimeError(f"{message}，请先完全退出游戏")
        await _report(on_log, f"原神更新：{message}，跳过更新以免写坏文件")
        return True

    async def report(line: str) -> None:
        """只进调度台：更新过程的日志由编排层统一写 app.log，这里不再复述。"""
        await _report(on_log, line)

    result = await update_genshin_client(
        str(game_exe.parent),
        resource=resource,
        on_progress=report,
        should_abort=should_abort,
    )

    if result.kind == UpdateKind.Unknown.value:
        # 问不出结论：自动流程已由编排层放行并留了 app.log，手动入口是用户当面来问的，
        # 查不出就是查不出，要把原因摊开而不是回一句「已是最新」
        if manual:
            raise RuntimeError(result.message)
        return True

    if result.success:
        if result.noop:
            # 「已是最新」对手动入口是必须当面回答的结论；自动流程只留 app.log 一行。
            # 编排层附带的结论（例如官方开了预下载）一并说全，用户才知道下一步去哪
            if manual:
                await _report(
                    on_log,
                    f"当前为最新版本（{result.local_version or '?'}），无需更新"
                    + (f"；{result.message}" if result.message else ""),
                )
        else:
            await report(
                f"原神客户端更新完成 {result.local_version or '?'} -> "
                f"{result.remote_version or '?'}"
            )
        return True

    if manual:
        raise RuntimeError(f"更新未完成：{result.message}")
    await report(f"原神客户端更新未完成：{result.message}")
    return False


async def _report(on_log: LogHook | None, line: str) -> None:
    """记一行日志并按需推给调度台。"""
    logger.info(line)
    if on_log is not None:
        await on_log(line)
