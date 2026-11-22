"""通知的正文：账号级统计报告的结果标记与标题、本机提示（成功、要手动更新游戏）的三段文字，
以及脚本级「代理结果」的信号摘要标题、账号结果行与正文。

只拼字符串：吃账号名、失效任务名、运行结局这类普通数据，返回标题 / 正文 / 提示条。
``LocalNotice`` 的构造、截图准备、推送都留在调用方（各专项的账号流程与脚本级流程），先后与原来一致。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence, Set
from datetime import datetime
from typing import Any

from .signal_notice import (
    CLIENT_UPDATE_REQUIRED,
    MAINTENANCE_LAST_STATUS,
    SERVER_MAINTENANCE,
)


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


def signal_summary_title(
    title: str, signals: Set[str], *, has_error: bool, has_completed: bool
) -> str | None:
    """本轮有信号时脚本级「代理结果」的摘要标题，写明原因；没有信号返回 None（沿用默认）。

    ``title`` 是推送标题（``MM-DD | <脚本>的<模式>任务报告``），``signals`` 是本轮信号账里命中过的信号。
    """

    reasons = [
        text
        for signal, text in (
            (SERVER_MAINTENANCE, "游戏停服维护中"),
            (CLIENT_UPDATE_REQUIRED, "需要更新游戏客户端"),
        )
        if signal in signals
    ]
    if not reasons:
        return None
    if has_error:
        state = "存在异常"
    elif has_completed:
        state = "部分跳过"
    else:
        state = "已跳过"
    return title.replace("报告", f"{state}（{'、'.join(reasons)}）")


def user_results_text(
    users: Sequence[tuple[str, str, str]],
    report_lines: Mapping[str, str],
    fallback: str,
) -> str:
    """「代理结果」里每个账号一行：跑过的用账号流程给的结果（与账号级统计报告同口径，只有人话），
    没跑的（运行前检查没过、没轮到）沿用通用的账号结果。

    ``users`` 是运行树上的账号（账号 id, 名字, 通用结果），按树上的先后；``report_lines`` 是账号 id →
    账号流程给的那一行；一个账号都没有时返回 ``fallback``（脚本节点的结果）。
    """

    if not users:
        return fallback
    return "\n".join(
        f"{name}: {report_lines.get(user_id) or result}"
        for user_id, name, result in users
    )


def proxy_result_body(
    *,
    mode_zh: str,
    script_name: str,
    begin_time: str,
    end_time: str,
    completed: int,
    uncompleted: int,
    results_text: str,
    incident_lines: Sequence[str],
    missing_lines: Sequence[str],
    summary_title: str | None,
) -> dict[str, Any]:
    """脚本级「代理结果」的正文（形状同 ``TaskResultData``，截图由调用方随后补进 ``screenshots``）。

    原地打转 / 单任务超时、失效任务每个账号一行跟在账号结果后面：通用模板没有单独的块，结果框按原样
    换行。``summary_title`` 为空时不写这一项。
    """

    result: dict[str, Any] = {
        "title": f"{mode_zh}任务报告",
        "script_name": script_name,
        "start_time": begin_time,
        "end_time": end_time,
        "completed_count": completed,
        "uncompleted_count": uncompleted,
        "result": "\n\n".join(
            [
                results_text,
                *(
                    "\n".join(lines)
                    for lines in (incident_lines, missing_lines)
                    if lines
                ),
            ]
        ),
    }
    if summary_title:
        result["summary_title"] = summary_title
    return result


__all__ = [
    "game_update_notice_text",
    "proxy_result_body",
    "signal_summary_title",
    "statistics_mark",
    "statistics_title",
    "success_notice_text",
    "user_results_text",
]
