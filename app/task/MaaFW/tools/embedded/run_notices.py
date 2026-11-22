"""账号级通知的正文：统计报告的结果标记与标题、本机提示（成功、要手动更新游戏）的三段文字。

只拼字符串：吃账号名、失效任务名、运行结局这类普通数据，返回标题 / 正文 / 提示条。
``LocalNotice`` 的构造、截图准备、推送都留在调用方（各专项的账号流程），先后与原来一致。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from .signal_notice import MAINTENANCE_LAST_STATUS


def statistics_mark(*, run_complete: bool, has_missing: bool, maintenance: bool) -> str:
    """账号级统计报告标题里的结果标记：完成但有失效任务 ``!``、完成 ``√``、停服维护跳过
    ``维护中``、其余 ``X``。"""

    if run_complete and has_missing:
        return "!"
    if run_complete:
        return "√"
    if maintenance:
        return MAINTENANCE_LAST_STATUS
    return "X"


def statistics_title(now: datetime, mark: str, user_name: str) -> str:
    """账号级统计报告的标题：``MM-DD |标记|  <账号> 的自动代理统计报告``（``now`` 取本机时间）。"""

    return f"{now.strftime('%m-%d')} |{mark}|  {user_name} 的自动代理统计报告"


def success_notice_text(
    user_name: str, missing_names: Sequence[str]
) -> tuple[str, str, str]:
    """账号跑完后的本机提示（标题, 正文, 提示条）；队列里有 interface 已没有的任务时说明跳过了哪些。"""

    if missing_names:
        names = "、".join(missing_names)
        return (
            "MaaFW 自动代理任务完成，但有失效任务",
            f"账号 {user_name} 的队列里有 interface 内已没有的任务，已跳过：{names}",
            f"{user_name} 有失效任务：{names}",
        )
    return (
        "MaaFW 自动代理任务完成",
        f"已完成账号 {user_name} 的 MaaFW 自动代理任务",
        f"已完成 {user_name} 的 MaaFW 自动代理任务",
    )


def game_update_notice_text(user_name: str, message: str) -> tuple[str, str, str]:
    """游戏客户端要手动更新时的本机提示（标题, 正文, 提示条）；``message`` 是更新检查给的那句。"""

    return (
        "游戏需要手动更新！",
        message,
        f"{user_name}的游戏需要手动更新",
    )


__all__ = [
    "game_update_notice_text",
    "statistics_mark",
    "statistics_title",
    "success_notice_text",
]
