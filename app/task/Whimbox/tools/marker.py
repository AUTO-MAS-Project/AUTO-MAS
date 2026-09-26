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
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""奇想盒日志面 marker 表与判定器（IRunResultParser 默认实现）。

marker 表按上游 v3.0.5 源码定稿（whimbox/main.py、task/task_template.py、
task/daily_task/all_in_one_task.py），全部取自上游用户可见输出（黑箱「允许依赖」
白名单）。上游版本微调时只改本表数据、不改逻辑。

行格式（loguru 默认 format）::

    2026-09-13 21:27:00.123 | INFO     | all_in_one_task:step_dig:330 - 美鸭梨挖掘
    └ 时间列 (0,23)                        └ 模块:函数:行号 - 消息

判定语义（源码级实锤）：

- 顶层任务无论成败都会走完 main.py:80-81 两行——``一条龙任务完成: {message}``
  与 ``任务结束，程序退出``，所以**收尾行只证明进程正常走完，不证明任务成功**；
- ``message`` 是顶层 ``TaskResult.message``：正常完成时由 step8 组装成
  ``任务结果如下：`` 块（all_in_one_task.py:458/468），提前中止时是失败原因
  （如「自动启动游戏」失败即 ``update_task_result(FAILED)`` 后直接跳到结束，
  见 all_in_one_task.py:315-316）；**结果块头出不出现就是上游自己的成败面**，
  MAS 只读它、不自造判定信号。
- ⚠️ step8 不是最后一步：适配层恒写 ``auto_close_game=true``，上游因此必定把
  ``step_close_game`` 排在 step8 之后（all_in_one_task.py:135-136）；它失败时用
  ``update_task_result(FAILED, "关闭游戏失败")``（:501-502）**覆盖掉刚写入的结果块**。
  该路径下结果块在上游那里根本没打印出来，MAS 判 failed（与上游自身状态一致），
  但分步 ✅/❌ 不可得——所以失败文案只陈述上游给的原因，不断言完成度。
- traceback 不得当进程级致命：每个 TaskTemplate 的 catch-all 都会打印
  （task_template.py:259-267），**单步子任务的异常同样会打**，而上游的处理是
  「记 ❌ 后继续跑下一步」；顶层异常则由「完成行消息不含结果块头」自然判负，
  不需要关键词兜底。按关键词判 fatal 会杀掉上游本来会继续跑完的一轮。

⚠️ 不得把结果块里的单步 ❌ 行当进程级失败（对齐 BetterGI「[ERR] 不判 fatal」
教训——单步失败 ≠ 进程失败）。
"""

from app.task.Whimbox.contracts import WhimboxRunVerdict

# 进程级致命（判异常）：出现即失败，不再等收尾行。
# 仅收录「起跑即退出、不可能再有收尾行」的形态——上层任务自身判负由完成行消息
# 承载（见模块注释），不在此列。
WHIMBOX_FATAL_MARKERS: tuple[tuple[str, str], ...] = (
    (
        "请用管理员权限运行",
        "奇想盒需要管理员权限运行（请保持脚本设置中「以管理员运行」开启，"
        "或以管理员身份运行 MAS）",
    ),
)

# 权威收尾行：无论成败都会打印（main.py:81），出现即整条一条龙序列走完
WHIMBOX_SEQUENCE_DONE_MARKER = "任务结束，程序退出"

# 「非失败提示」：上游用 ❌ 前缀打出、但其实是正常状态的文案——收进报告的
# 「未完成原因」段会把正常情况说成故障，故按本表排除（**不改写上游结果块原文**）。
# 依据是上游语义而非猜测：``dig_task_v2.step2`` 在「挖掘位仍在冷却（n>0）」时
# ``update_task_result(FAILED, "正在挖掘，无法收获")``——对用户是「今日没得收」，
# 不是故障（同文件 v1 那一版用的还是 STOP）。上游改文案时同步改本表。
WHIMBOX_BENIGN_MARKERS: tuple[str, ...] = ("正在挖掘，无法收获",)


def is_benign_marker(text: str) -> bool:
    """该提示是否属「非失败」表（上游以 ❌ 打出、实为正常状态）。"""

    return any(marker in text for marker in WHIMBOX_BENIGN_MARKERS)


# 完成行锚点与结果块头：main.py:80 打出顶层任务结果 message，正常完成时其首行
# 为「任务结果如下：」，其后逐行 ✅/⏭️/❌ 结果（多账号按「账号N：」分组）
WHIMBOX_COMPLETION_MARKER = "一条龙任务完成:"
WHIMBOX_RESULT_BLOCK_HEAD = "任务结果如下："

# 中止原因的展示上限：完成行中断时 message 可能是长异常文本，状态行不该被撑爆
_ABORT_REASON_MAX_CHARS = 200


def extract_completion_message(log: str) -> str | None:
    """取上游完成行消息原文（自「一条龙任务完成:」起至收尾行前）。

    正常完成时即结果块（含各步 ✅/⏭️/❌ 行与多账号分组）；提前中止时是失败原因。

    Args:
        log: 累计日志文本。

    Returns:
        完成行消息文本；未见完成行返回 None。
    """

    head = log.find(WHIMBOX_COMPLETION_MARKER)
    if head < 0:
        return None
    message = log[head + len(WHIMBOX_COMPLETION_MARKER) :].lstrip()
    # 去掉消息内可能混入的收尾行（正常收尾行在其后单独打印，不在消息内）。
    # 收尾行自带 loguru 前缀「时间 | 级别 | 模块:行 - 」，必须按**行首**截断，
    # 否则这半截前缀会作为垃圾行留在结果块末尾（真机报告里出现过
    # 「… | INFO     | main:run_one_dragon:81 - 」这样的尾行）。
    tail = message.find(WHIMBOX_SEQUENCE_DONE_MARKER)
    if tail >= 0:
        line_start = message.rfind("\n", 0, tail)
        message = message[:line_start] if line_start >= 0 else message[:tail]
    return message.strip() or None


def extract_result_block(log: str) -> str | None:
    """提取上游结果块原文（自「任务结果如下：」起至收尾行前）。

    结果块由一条 loguru.info 打出、保留消息内换行，块内续行没有独立时间列；
    顶层任务结果不走 log_to_gui，该块是其在文件中的唯一载体。

    Args:
        log: 累计日志文本。

    Returns:
        结果块文本（含各步 ✅/⏭️/❌ 行与多账号分组）；未见块头返回 None。
    """

    message = extract_completion_message(log)
    if message is None:
        return None
    head = message.find(WHIMBOX_RESULT_BLOCK_HEAD)
    if head < 0:
        return None
    return message[head:].strip() or None


def _abort_reason(message: str) -> str:
    """取完成行消息首行作为中止原因（过长时截断，供状态行展示）。"""

    first = next((line.strip() for line in message.splitlines() if line.strip()), "")
    return (first or message)[:_ABORT_REASON_MAX_CHARS]


class WhimboxMarkerParser:
    """IRunResultParser 默认实现：marker 表逐条匹配的纯函数判定器。"""

    def evaluate(
        self,
        log: str,
        *,
        process_running: bool,
        stalled_minutes: float | None = None,
        stalled: bool = False,
    ) -> WhimboxRunVerdict:
        """按 marker 表判定：fatal → 完成/中止 → 早退/停滞 → 运行中。

        Args:
            log: 累计日志文本。
            process_running: 无头进程是否仍在运行。
            stalled_minutes: 停滞阈值（分钟），仅供拼装文案。
            stalled: 是否已停滞超时（由持有单调时钟的一方判定）。
        """

        for needle, message in WHIMBOX_FATAL_MARKERS:
            if needle in log:
                return WhimboxRunVerdict(status="fatal", message=message)

        if WHIMBOX_SEQUENCE_DONE_MARKER in log:
            message = extract_completion_message(log)
            if message is None or WHIMBOX_RESULT_BLOCK_HEAD in message:
                # 完整走完：整体=序列完成，单步成败由结果块透传。
                # message is None 属日志截断（两行本就相邻打印），此时无从判负，
                # 按成功收口并留空结果块，避免把「日志没读全」说成任务失败。
                return WhimboxRunVerdict(
                    status="success",
                    message="奇想盒一条龙序列已完成",
                    result_block=extract_result_block(log),
                )
            # 收尾行照打但完成消息不是结果块：上游自己把顶层任务判成了失败/中止。
            # 文案只陈述上游给出的原因，不断言完成度（step8 之后的收尾步骤失败
            # 同样落在这里，那种情形下步骤其实已跑完，见模块注释）。
            return WhimboxRunVerdict(
                status="failed",
                message=f"奇想盒运行失败：{_abort_reason(message)}",
            )

        if not process_running:
            return WhimboxRunVerdict(
                status="exited_early", message="奇想盒在完成任务前退出"
            )

        if stalled:
            minutes_text = int(stalled_minutes) if stalled_minutes else ""
            return WhimboxRunVerdict(
                status="stalled",
                message=f"奇想盒运行超时（{minutes_text} 分钟无日志进展）",
            )

        return WhimboxRunVerdict(status="running", message="奇想盒正常运行中")
