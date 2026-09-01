"""推送日志通用工具

供各专项（General / OK-WW / OK-NTE 等）统一聚合推送日志，避免每个适配器
重复实现相同逻辑；接入 log_box 的适配器直接复用本模块即可。

- ``build_user_result_text``：按用户交错组装「用户结果行 + 该用户节点详情」
  报告文本，多账号任务时各用户节点归属清晰；「失败」类型条目仅在任务存在
  未完成用户时纳入（与 MAS 原生推送策略一致）。节点详情按用户级推送模式
  （``user.push_log_mode``）呈现：关闭 = 不输出；逐条 = 逐条带时间戳；
  汇总 = 按状态聚合为一行。未设置模式的用户（如通用脚本）保持逐条原样输出。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable

from app.utils.LogPatternExtractor import LOG_TYPE_ERROR

# 推送模式（与用户配置 Notify.PushLogMode / 前端下拉框取值一致）
PUSH_LOG_MODE_OFF = "关闭"
PUSH_LOG_MODE_SCATTER = "逐条"
PUSH_LOG_MODE_AGGREGATE = "汇总"

# 节点状态行：前缀（状态标记） + ": " + 节点名，用于汇总聚合分组
_PUSH_STATUS_RE = re.compile(r"^(✅ 成功|⏭ 跳过|❌ 失败): (.*)$")


def _render_scatter(entries: list[tuple]) -> list[str]:
    """逐条式渲染：每条结果独占一行，加采集时间（HH:MM）前缀

    无时间戳（通用脚本等旧式二元组条目）时仅输出文本原样，保持兼容。
    """
    lines: list[str] = []
    for entry in entries:
        text = entry[1]
        ts = entry[2] if len(entry) > 2 else None
        if ts is not None:
            text = f"{datetime.fromtimestamp(ts).strftime('%H:%M')} - {text}"
        lines.append(text)
    return lines


def _render_aggregate(entries: list[tuple]) -> list[str]:
    """汇总式渲染：按状态前缀分组合并节点名，同一状态合并为一行

    不具状态前缀的条目（如「⚡ 剩余体力: 30」）原样独占一行；分组顺序按状态首次
    出现排列。
    """
    groups: dict[str, list[str]] = {}
    order: list[str] = []
    plain: list[str] = []
    for entry in entries:
        text = entry[1]
        m = _PUSH_STATUS_RE.match(text)
        if m:
            status, node = m.group(1), m.group(2)
            if status not in groups:
                order.append(status)
                groups[status] = []
            groups[status].append(node)
        else:
            plain.append(text)
    return [f"{status}: {', '.join(groups[status])}" for status in order] + plain


def build_user_result_text(users: Iterable, has_uncompleted: bool) -> str:
    """按用户交错组装「用户结果行 + 该用户节点详情」报告文本

    每个用户先输出 ``用户名: 用户result`` 结果行，随后紧跟该用户采集的
    节点详情，用户块之间以空行分隔；没有采集到节点的用户只输出结果行。
    节点详情按用户级 ``push_log_mode`` 呈现：关闭 = 不输出；逐条 = 带采集
    时间戳一行一条；汇总 = 按状态聚合为一行。多账号任务时各用户节点归属清晰，
    避免全部平铺在一起无法区分。

    Args:
        users: 用户列表（元素需有 ``name``、``result``、``push_log`` 属性：
            ``push_log`` 为 ``list[tuple]``，元素可为 ``(log_type, text)``
            或 ``(log_type, text, ts)``）。
        has_uncompleted: 本次任务是否存在未完成用户；为 False 时「失败」
            类型条目不纳入报告。

    Returns:
        交错后的报告文本（无用户时返回空串）
    """
    blocks: list[str] = []
    for user in users:
        entries = [
            item
            for item in user.push_log
            if item[0] != LOG_TYPE_ERROR or has_uncompleted
        ]
        mode = getattr(user, "push_log_mode", PUSH_LOG_MODE_SCATTER)
        if mode == PUSH_LOG_MODE_OFF:
            node_lines: list[str] = []
        elif mode == PUSH_LOG_MODE_AGGREGATE:
            node_lines = _render_aggregate(entries)
        else:
            node_lines = _render_scatter(entries)
        blocks.append("\n".join([f"{user.name}: {user.result}"] + node_lines))
    return "\n\n".join(blocks)
