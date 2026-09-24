#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""BAAH 推送日志采集参数（log_box 实例的喂参方）

BAAH 专项作为 log_box 的一个实例：本模块只提供参数（规则与后置处理器），
日志获取、规则匹配、后置处理与推送全部由 log_box 完成。

BAAH 的运行日志没有需要翻译的文本，也不挂前置处理器，匹配与提取都作用于
日志原文。任务节点由三类行刻画（依据 BAAH 2.4.13 的真实运行日志），节点名
就是任务名（EnterGame / Loginin / PostAllTask 等）。

规则说明：

- ``执行任务<任务名>``：任务开始执行，作为开始标记（默认成功）
- ``任务<任务名>执行结束``：任务正常结束，明确成功
- ``任务<任务名>执行前条件不成立或超时，跳过此任务``：执行条件不成立，任务被跳过

BAAH 没有单任务失败日志：任务内抛出异常会直接终止整个运行，由顶层异常处理
输出一行 ``运行出错: <原因>``，因此这里只采集这个整体失败信号，再由
``baah_resolve`` 把失败归属到终止时仍在执行的任务上。

实测日志文案为中文，规则按中文文本匹配；上游若改动这些日志文案，规则需同步
核对。
"""

import re

from app.log_box.logtype import LogType

## BAAH 的任务目录名由字母、数字与下划线组成，用它把任务名从整行里切出来。
## 只截取任务名本身，整行中排在它后面的其它文本不会被带进节点名
_TASK_NAME = r"[A-Za-z0-9_]+"

## 整体运行失败的标记文本：与节点标记分开表示，由 baah_resolve 决定归属到
## 哪个任务节点，或在没有任务在执行时直接作为节点输出
_ERROR_MARK = "❌ 运行出错: "

## 推送规则：(匹配正则, 提取表达式)。规则顺序敏感——log_box 对同一行只取首个
## 命中的规则，所以最具体的整体失败规则必须排在最前：失败原因里可能含任务名
## （真实日志中的「运行出错: 任务InCafe执行后条件不成立或超时，且无法正确
## 返回主页，程序退出」），排在任务规则之后会被任务正则当成普通节点行吞掉
BAAH_PUSH_RULES: list[tuple[str, str]] = [
    # ── 整体运行失败（顶层异常，本次运行在执行某个任务的中途终止）──
    (r"运行出错: (.+)", rf'"{_ERROR_MARK}" + $((?:运行出错: )(.+))'),
    # ── 任务跳过（执行条件不成立或超时）──
    (
        rf"任务{_TASK_NAME}执行前条件不成立或超时",
        rf'"⏭ 跳过: " + $((?:任务)({_TASK_NAME})(?:执行前条件不成立或超时))',
    ),
    # ── 任务正常结束 ──
    (
        rf"任务{_TASK_NAME}执行结束",
        rf'"✅ 成功: " + $((?:任务)({_TASK_NAME})(?:执行结束))',
    ),
    # ── 任务开始（裸任务名 = 开始标记，最终状态由 baah_resolve 解析）──
    (rf"执行任务{_TASK_NAME}", rf"$((?:执行任务)({_TASK_NAME}))"),
]

## 状态优先级：失败 > 跳过 > 成功
_STATUS_RANK = {"✅ 成功": 1, "⏭ 跳过": 2, "❌ 失败": 3}


def baah_resolve(results: list[tuple[str, str, float]]) -> list[tuple[str, str, float]]:
    """后处理：按任务节点解析最终状态（失败 > 跳过 > 成功）

    输入/输出均为 ``(log_type, text, ts)`` 元组（与 log_box ``_PostProcessor``
    契约一致），日志类型与采集时间戳随元组一并保留。规则产出四类标记：裸任务名
    （任务开始，默认成功）、``✅ 成功: 任务名``、``⏭ 跳过: 任务名`` 与整体失败
    标记 ``❌ 运行出错: 原因``。同一节点多次出现保留最高优先级状态，节点顺序与
    时间戳都按最后一次出现排列——BAAH 会把同一任务重跑多次，报告呈现的应当是
    最后一次的流程顺序。

    BAAH 的任务是嵌套执行的（例如 InCafe 会拉起 CollectPower、ScrollSelect 等
    子任务），开始与结束标记构成后进先出的配对，这里用栈跟踪「已开始、未结束」
    的任务：

    - 运行终止时仍留在栈里的任务都没跑完（运行出错、进程被强杀、日志静默超时），
      统一标为失败，避免这些被中断的任务按开始标记的默认成功进入报告；
    - 只有栈为空（如「未检测到游戏打开」，一个任务都没进去）时，才把上游给出的
      错误原因本身作为失败节点输出。
    """
    order: list[str] = []
    states: dict[str, tuple[int, str]] = {}
    ts_of: dict[str, float] = {}
    ## 「已开始、未结束」的任务栈，元素为 (任务名, 开始时间戳)
    running: list[tuple[str, float]] = []
    error_text: str | None = None
    error_ts: float = 0.0

    def _mark(status: str, node: str, ts: float) -> None:
        rank = _STATUS_RANK[status]
        if node in states:
            order.remove(node)  # 移至末尾：保留最后一次出现顺序
        order.append(node)
        if rank >= states.get(node, (0, ""))[0]:
            states[node] = (rank, status)
            ts_of[node] = ts

    for _, text, ts in results:
        if text.startswith(_ERROR_MARK):
            error_text = text[len(_ERROR_MARK) :]
            error_ts = ts
            continue
        matched = re.match(r"^(✅ 成功|⏭ 跳过): (.*)$", text)
        if matched is not None:
            status, node = matched.group(1), matched.group(2)
            for index, (name, _) in enumerate(running):
                if name == node:
                    del running[index]  # 任务已结束或已跳过，离开执行中
                    break
        else:
            ## 裸任务名 = 开始标记：BAAH 的任务结束另有一行「任务X执行结束」，
            ## 默认按成功呈现，被中断的任务由下方的收尾判定覆盖为失败
            status, node = "✅ 成功", text
            running.append((node, ts))
        _mark(status, node, ts)

    ## 收尾：栈中剩下的任务没有结束标记，说明运行在其执行途中终止。失败时间用
    ## 整体失败的时刻，未被判定为运行出错（进程被强杀、日志超时）时退回任务开始时刻
    interrupted_ts = error_ts if error_text is not None else 0.0
    for node, started_at in running:
        _mark("❌ 失败", node, interrupted_ts or started_at)

    if error_text is not None and not running:
        _mark("❌ 失败", error_text, error_ts)

    ## 规则均为二元组，经 LogCollect.collect 后 log_type 恒为 LogType.NORMAL；
    ## 节点级失败由文本「❌ 失败:」体现，不依赖逐条类型过滤，故直接输出普通
    return [
        (LogType.NORMAL, f"{states[node][1]}: {node}", ts_of[node]) for node in order
    ]
