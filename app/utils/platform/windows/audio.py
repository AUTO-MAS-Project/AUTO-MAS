"""按 PID 静音 Windows 音频会话。

静默模式要在无人值守时关掉模拟器的声音。选「按进程」而不是「整体静音」：挂机常与
日常用机并行，整体静音会把用户自己的音乐、会议一并吞掉，还原失败的影响面还是全
系统；进程级只作用于目标进程，音频会话又随进程销毁——就算宿主被强杀没来得及还原，
目标进程下次启动也是全新的未静音会话，不会留下永久哑掉的机器。

本模块只把给定 PID 的音频会话设为指定静音状态并回报先前的状态，供调用方记录还原；
不碰系统音量、不碰其他进程。异步接口**绝不向调用方抛异常**——静音是启动流程的
附赠动作，任何失败都不应拖垮模拟器启动。

会话枚举基于 pycaw（Windows Core Audio 的 COM 封装）：COM 按线程初始化，每轮操作
各自 CoInitialize、用完即释放，COM 对象不跨线程复用。注意音频会话是**惰性**的：
进程首次发声时才建立会话，刚启动就查询扑空属预期，调用方需稍后重试。
"""

import asyncio
from collections.abc import Iterable

import comtypes
from pycaw.pycaw import AudioUtilities

from app.utils import get_logger

logger = get_logger("音频会话管理")


def _set_sessions_muted(targets: dict[int, bool]) -> dict[int, bool]:
    """把 ``targets`` 中每个进程当前已存在的音频会话设为指定静音状态。

    必须在工作线程内调用（COM 按线程初始化）。

    Returns
    -------
    dict[int, bool]
        ``{pid: 设置前的静音状态}``，只含实际找到会话的 PID；进程已退出或还没
        发过声（会话未建立）的 PID 自然不在其中。
    """
    comtypes.CoInitialize()
    try:
        result: dict[int, bool] = {}
        for session in AudioUtilities.GetAllSessions():
            try:
                pid = session.ProcessId
                if pid not in targets:
                    continue
                volume = session.SimpleAudioVolume
                if pid not in result:
                    result[pid] = bool(volume.GetMute())
                volume.SetMute(targets[pid], None)
            except Exception:  # noqa: BLE001 - 单个会话失效不应影响其余会话
                logger.opt(exception=True).debug("操作单个音频会话失败")
        return result
    finally:
        comtypes.CoUninitialize()


async def mute_once(pids: Iterable[int]) -> dict[int, bool]:
    """静音给定进程当前已存在的音频会话，返回 ``{pid: 静音前的静音状态}``。

    只做一次枚举，不做等待：返回空 dict 表示「会话尚未建立」或「本轮操作失败」，
    两者对调用方意义相同（还没静音上，稍后重试），失败细节只记 debug——轮询场景
    下按次记 warning 会在音频子系统故障时刷屏，可见信号由调用方的超时告警兜底。
    """
    targets = {int(pid): True for pid in pids}
    if not targets:
        return {}
    try:
        return await asyncio.to_thread(_set_sessions_muted, targets)
    except Exception:  # noqa: BLE001 - 静音失败不应拖垮调用方流程
        logger.opt(exception=True).debug(f"本轮静音音频会话失败: {sorted(targets)}")
        return {}


async def restore_processes(states: dict[int, bool]) -> dict[int, bool]:
    """按 ``mute_once`` 记录的先前状态还原各进程的静音状态。

    Returns
    -------
    dict[int, bool]
        实际找到会话并完成还原的 ``{pid: 还原前的静音状态}``；进程已退出的（会话
        随之销毁）不在其中。失败只记日志不外抛，返回已处理到的部分。
    """
    if not states:
        return {}
    try:
        return await asyncio.to_thread(_set_sessions_muted, dict(states))
    except Exception:  # noqa: BLE001 - 还原失败不应阻断调用方流程
        logger.opt(exception=True).warning(f"还原音频静音状态失败: {sorted(states)}")
        return {}
