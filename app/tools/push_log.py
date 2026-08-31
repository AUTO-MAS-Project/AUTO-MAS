"""推送日志通用工具

供各专项（General / OK-WW / OK-NTE 等）统一聚合推送日志，避免每个适配器
重复实现相同逻辑；接入 log_box 的适配器直接复用本模块即可。

- ``build_user_result_text``：按用户交错组装「用户结果行 + 该用户节点详情」
  报告文本，多账号任务时各用户节点归属清晰；「失败」类型条目仅在任务存在
  未完成用户时纳入（与 MAS 原生推送策略一致）。
"""

from __future__ import annotations

from typing import Iterable

from app.utils.LogPatternExtractor import LOG_TYPE_ERROR


def build_user_result_text(users: Iterable, has_uncompleted: bool) -> str:
    """按用户交错组装「用户结果行 + 该用户节点详情」报告文本

    每个用户先输出 ``用户名: 用户result`` 结果行，随后紧跟该用户采集的
    节点详情（每条独占一行），用户块之间以空行分隔；没有采集到节点的
    用户只输出结果行。多账号任务时各用户节点归属清晰，避免全部平铺在
    一起无法区分。

    Args:
        users: 用户列表（元素需有 ``name``、``result``、``push_log`` 属性：
            ``push_log`` 为 ``list[tuple[log_type, text]]``）。
        has_uncompleted: 本次任务是否存在未完成用户；为 False 时「失败」
            类型条目不纳入报告。

    Returns:
        交错后的报告文本（无用户时返回空串）
    """
    return "\n\n".join(
        "\n".join(
            [f"{user.name}: {user.result}"]
            + [
                text
                for log_type, text in user.push_log
                if log_type != LOG_TYPE_ERROR or has_uncompleted
            ]
        )
        for user in users
    )
