#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.
#
#   Contact: DLmaster_361@163.com

"""BetterGI 分步结果来源与节点转换。

BGI 日志已由 LogMonitor 按相/按轮捕获进 ``log_record``（执行层一条记录、
原生一条龙每轮重试各一条），``one_dragon_report`` 是权威解析器（含 Serilog
头行配对、致命信号判失败、任务名对齐与重试取轮），AutoProxy.final_task
本就会解析出合并分步表。本模块只负责将现有分步表转换成报告条目，
异步执行、异常隔离和用户交付由 BetterGI AutoProxy 负责。manager 与统计通知仍共用
原有文本，不重建一份节点判定。

在这里重建一套 log_box 逐行规则只会复刻解析器的上下文判定（开始/结束
配对、头行时间戳、重试收束），与判态侧形成两份并行语义（MaaEnd 已注明
「节点聚合按任务名、判态按任务 id」的同款分叉），故不为之。
"""

from contextlib import suppress
from datetime import datetime

from app.utils import LOG_TYPE_NORMAL

# 步骤 start 只有 HH:MM(:SS) 形态的本地时刻（Serilog 头行时间戳，无日期），
# 转成当天时刻的时间戳供逐条式推送显示 HH:MM 前缀；解析失败回退当前时刻。
_STEP_TIME_FORMAT = "%H:%M:%S"


def _step_ts(step: dict) -> float:
    """把步骤的开始时刻换算成时间戳；缺失或解析失败时回退当前时刻。

    时刻本身无日期，按今天组合——不能直接给 naive datetime 调
    ``timestamp()``（strptime 缺省补 1900 年，Windows 上会抛 OSError）。
    """

    with suppress(ValueError):
        parsed = datetime.strptime(
            str(step.get("start") or "").split(".")[0], _STEP_TIME_FORMAT
        ).time()
        return datetime.combine(datetime.now().date(), parsed).timestamp()
    return datetime.now().timestamp()


def steps_to_push_log(steps: list[dict]) -> list[tuple[str, str, float]]:
    """把合并分步表转成 ``(log_type, text, ts)`` 三元组列表，保持执行顺序。

    文本形态与 ``_PUSH_STATUS_RE`` 的状态行契约对齐（状态标记 + ": " + 节点名），
    汇总式渲染按状态分组合并节点名。成功/失败节点只保留判定；失败步骤的实际报错、
    未确认结果与白名单异常参考 ZZZ-OD 输出「⚠ 异常:」并保留原因，不改变整体成败。
    步内可恢复报错（含树脂耗尽这类预期停止）的数量与完整原因都在统计通知的
    分步表里。节点级失败与警告一律 ``LOG_TYPE_NORMAL``
    + 文本「❌ 失败:」体现（始终展示），推送时机由全局 ``SendTaskResultTime``
    控制——与 ok 系 / MaaEnd 的后置处理口径一致。

    Args:
        steps: ``one_dragon_report``（或 ``parse_one_dragon_report`` /
            ``parse_execution_layer_report``）产出的步骤字典列表。

    Returns:
        ``(LOG_TYPE_NORMAL, 文本, 时间戳)`` 三元组列表；空表原样返回空表。
    """

    entries: list[tuple[str, str, float]] = []
    for step in steps:
        task = str(step.get("task") or "未知任务")
        if not step.get("ok"):
            text = f"❌ 失败: {task}"
        elif step.get("skipped"):
            text = f"⏭ 跳过: {task}"
            if step.get("skip_text"):
                text += f"（{step['skip_text']}）"
        elif step.get("warning_text"):
            text = f"⚠ 异常: {task}（{step['warning_text']}）"
        else:
            text = f"✅ 成功: {task}"
        entries.append((LOG_TYPE_NORMAL, text, _step_ts(step)))
        if not step.get("ok") and (reason := str(step.get("issue_text") or "").strip()):
            entries.append(
                (
                    LOG_TYPE_NORMAL,
                    f"⚠ 异常: {task}（{reason}）",
                    _step_ts(step),
                )
            )
    return entries
