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

"""BetterGI 推送日志（节点详情）注入

与其他专项经由 log_box 采集会话喂规则不同，BetterGI 不新建采集会话：
BGI 日志已由 LogMonitor 按相/按轮捕获进 ``log_record``（执行层一条记录、
原生一条龙每轮重试各一条），``one_dragon_report`` 是权威解析器（含 Serilog
头行配对、致命信号判失败、任务名对齐与重试取轮），AutoProxy.final_task
本就会解析出合并分步表。本模块只做「报告注入」半环：把分步表转成
push_log 三元组，由 manager.final_task 经 ``build_user_result_text`` 聚合
进报告正文——呈现语义（三态开关、逐条/汇总）与 ok 系/ZzzOd 一致。

在这里重建一套 log_box 逐行规则只会复刻解析器的上下文判定（开始/结束
配对、头行时间戳、重试收束），与判态侧形成两份并行语义（MaaEnd 已注明
「节点聚合按任务名、判态按任务 id」的同款分叉），故不为之。
"""

from contextlib import suppress
from datetime import datetime

from app.log_box import LogType

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
    汇总式渲染按状态分组合并节点名。节点文本只保留判定、不带原因与异常计数：
    步内可恢复报错（含树脂耗尽这类预期停止）的数量与完整原因都在统计通知的
    分步表里。节点级失败一律 ``LogType.NORMAL``
    + 文本「❌ 失败:」体现（始终展示），推送时机由全局 ``SendTaskResultTime``
    控制——与 ok 系 / MaaEnd 的后置处理口径一致。

    Args:
        steps: ``one_dragon_report``（或 ``parse_one_dragon_report`` /
            ``parse_execution_layer_report``）产出的步骤字典列表。

    Returns:
        ``(LogType.NORMAL, 文本, 时间戳)`` 三元组列表；空表原样返回空表。
    """

    entries: list[tuple[str, str, float]] = []
    for step in steps:
        task = str(step.get("task") or "未知任务")
        if step.get("ok"):
            text = f"✅ 成功: {task}"
        else:
            text = f"❌ 失败: {task}"
        entries.append((LogType.NORMAL, text, _step_ts(step)))
    return entries
