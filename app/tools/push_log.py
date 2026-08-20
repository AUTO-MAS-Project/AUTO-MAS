"""推送日志通用工具

供各专项（General / OK-WW 等）统一聚合与追加推送日志，避免每个适配器重复
实现相同逻辑；未来接入 log_box 的适配器直接复用本模块即可。

- ``build_push_log_text``：聚合各用户的 push_log 为报告文本；「失败」类型
  条目仅在任务存在未完成用户时纳入（与 MAS 原生推送策略一致）。
- ``append_push_log``：把推送日志追加到通知正文（默认以单个换行分隔）。
"""

from __future__ import annotations

from typing import Iterable


def build_push_log_text(users: Iterable, has_uncompleted: bool) -> str:
    """聚合各用户 push_log 为报告文本（每条条目独占一行，不附加用户名）

    Args:
        users: 用户列表（元素需有 ``push_log`` 属性：
            ``list[tuple[log_type, text]]``）。
        has_uncompleted: 本次任务是否存在未完成用户；为 False 时「失败」
            类型条目不纳入报告。

    Returns:
        聚合后的推送日志文本（无内容时返回空串）
    """
    return "\n".join(
        "\n".join(
            text
            for log_type, text in user.push_log
            if log_type != "失败" or has_uncompleted
        )
        for user in users
        if user.push_log
    )


def append_push_log(
    message_text: str, push_log: str, separator: str = "\n"
) -> str:
    """把推送日志追加到通知正文

    Args:
        message_text: 已有通知正文。
        push_log: 推送日志文本（聚合后）。
        separator: 正文与推送日志之间的分隔符（默认单个换行）。

    Returns:
        追加后的通知正文（push_log 为空时原样返回）
    """
    if not push_log:
        return message_text
    return f"{message_text}{separator}{push_log}"
