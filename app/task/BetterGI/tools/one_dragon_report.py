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

"""BetterGI「一条龙」分步执行报告解析。

从 BetterGI Serilog 日志逐条还原「一条龙」每一步做了什么、成没成功，供统计通知的分步报告。
本模块刻意只依赖 ``re``（纯解析、零业务依赖），以便测试能像 ``one_dragon.py`` 那样经
``importlib`` 按文件路径独立加载，绕开 ``app.task`` 包急切 import 触发的循环依赖。

日志结构（真实样本，Serilog 头行 ``[HH:mm:ss.fff] [INF] ...LoggerName`` 下方紧随消息行）：
    一条龙任务执行: 1/3           ← 步开始（头行携带时间戳）
    → "任务启动！"
    邮件："全部领取"              ← 任务名/进度描述；`→ "前往合成台" 开始` 同理
    [ERR] ...                     ← 步内可恢复异常（BGI 任务级异常会跳过步内子任务继续跑）
    → "任务结束"                 ← 步正常结束
    一条龙和配置组任务结束          ← 整条收尾（成败由 AutoProxy._one_dragon_sequence_done 判定）

整条是否完成不属于本模块职责；本模块只负责「按执行顺序列出每一步 + 经过与成败」。
"""

import re

# 一条龙进度行的正则：「一条龙任务执行: X/N」（可带空格/斜杠）
_BGI_STEP_PROGRESS_RE = re.compile(r"一条龙任务执行:\s*(\d+)\s*/\s*(\d+)")
# Serilog 头行时间戳：「[HH:mm:ss(.fff)] ...」
_BGI_STEP_TIME_RE = re.compile(r"\[(\d{1,2}:\d{2}:\d{2}(?:\.\d{1,3})?)\]")
# 步内可恢复异常的信号（BGI TaskRunner 捕获后不 rethrow，一条龙继续跑下一条）。
# 真实 BGI Serilog 里级别写在头行的第二个括号（``[..] [ERR] [Primary:..]``），
# 消息/异常原因另起一行；``任务执行异常``/``执行失败`` 则直接出现在消息行。
_BGI_STEP_HEADER_ERR_HINTS = ("[ERR]", "[FTL]")
_BGI_STEP_ISSUE_HINTS = ("[ERR]", "任务执行异常", "执行失败")


def _clean_step_task(line: str) -> str:
    """把日志里的一步描述提炼成简短任务名。

    ``→ "前往合成台" 开始`` → ``前往合成台``；``邮件："全部领取"`` → ``邮件``；
    ``▶ "领取『每日委托』奖励" 未完成`` → ``领取『每日委托』奖励``。
    """
    s = line.strip()
    s = re.sub(r"^[→▶]\s*", "", s)
    s = s.replace('"', "").replace("“", "").replace("”", "")
    s = re.sub(r"\s*(?:开始|结束)\s*$", "", s)
    if "：" in s:
        s = s.split("：", 1)[0]
    elif ":" in s:
        s = s.split(":", 1)[0]
    return s.strip() or "未知任务"


def _parse_one_dragon_report(log: str) -> list[dict] | None:
    """解析「一条龙」分步执行报告，按执行顺序返回步骤字典列表。

    每步字段：``index``/``total``（第几条/共几条）、``task``（任务名）、``start``/``end``
    （起止时间 HH:MM:SS）、``ok``（是否走完 ``→ "任务结束"``）、``issue_count``/``issue_text``
    （步内可恢复异常数目与首条原因摘要，无异常为空串）。
    本会话未跑一条龙（无 ``一条龙任务执行`` 行）时返回 None，调用方据此省略分步区块。
    """
    lines = log.splitlines()
    steps: list[dict] = []
    cur: dict | None = None
    last_time = ""
    pending_err = False  # 上一条头行级别为 [ERR]/[FTL]，紧随其后的消息行即异常原因

    def finalize() -> dict:
        assert cur is not None
        return {
            **cur,
            "issue_count": len(cur["issue"]),
            "issue_text": cur["issue"][0].strip() if cur["issue"] else "",
        }

    for raw in lines:
        m = _BGI_STEP_TIME_RE.match(raw)
        if m:
            last_time = m.group(1)
            # 头行级别槽带 [ERR]/[FTL] 且当前在某条一步内 → 下一条消息行即异常原因
            pending_err = cur is not None and any(
                h in raw for h in _BGI_STEP_HEADER_ERR_HINTS
            )
            continue
        line = raw.strip()
        if not line:
            continue

        if pending_err:
            # 该消息属于上一条 [ERR] 头行：记入问题，不参与任务名解析
            pending_err = False
            if cur is not None and "任务启动" not in line and "任务结束" not in line:
                cur["issue"].append(line)
            continue

        pm = _BGI_STEP_PROGRESS_RE.match(line)
        if pm:
            if cur is not None:  # 上一步异常中断（无「任务结束」）也先收尾再开新步
                cur["end"] = cur["end"] or last_time
                cur["ok"] = False
                steps.append(finalize())
            cur = {
                "index": int(pm.group(1)),
                "total": int(pm.group(2)),
                "task": "",
                "start": last_time,
                "end": "",
                "ok": True,
                "issue": [],
            }
            continue
        if cur is None:
            continue

        if line == '→ "任务结束"':
            # 走完「任务结束」即该步成功；步内 [ERR] 是 BGI 可恢复异常，只记为 issue，
            # 不把本可完成的一条龙某步误判失败（与 _one_dragon_sequence_done 语义一致）。
            cur["end"] = last_time
            cur["ok"] = True
            steps.append(finalize())
            cur = None
        elif "任务启动" in line:
            continue
        else:
            if not cur["task"]:
                cur["task"] = _clean_step_task(line)
            if any(h in line for h in _BGI_STEP_ISSUE_HINTS):
                cur["issue"].append(line)

    if cur is not None:  # 日志结束仍停留在某一步（未收尾）→ 该步未完成
        cur["end"] = cur["end"] or last_time
        cur["ok"] = False
        steps.append(finalize())

    if not steps:
        return None
    # 移除解析过程使用的内部 issue 原始行，避免携带多余细节（已汇总为 issue_count/text）
    for s in steps:
        s.pop("issue", None)
    return steps