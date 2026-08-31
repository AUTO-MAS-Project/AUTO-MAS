#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

import importlib.util
from pathlib import Path

# 直接按文件路径加载 one_dragon_report 模块：``app.task`` 的 ``__init__`` 会急切 import 全部
# 管理器触发 app.core 循环依赖，pytest 收集时无法经包导入，故绕开走独立加载。
_SPEC = importlib.util.spec_from_file_location(
    "one_dragon_report",
    Path(__file__).resolve().parents[2]
    / "app"
    / "task"
    / "BetterGI"
    / "tools"
    / "one_dragon_report.py",
)
odr = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(odr)

_parse_one_dragon_report = odr._parse_one_dragon_report
_clean_step_task = odr._clean_step_task


def _hdr(ts: str) -> str:
    """拼一个带时间戳的 Serilog 头行；消息行紧随其下。"""
    return f"[{ts}] [INF] [Primary:S1:P24476:T1788125418672] BetterGenshinImpact.X"


def _run(steps: list[tuple[str, list[str]]], *, ended: bool = True) -> str:
    """按真实日志布局拼一段一条龙日志。

    steps 形如 [(时间戳, [消息行...]), ...]，每条消息行用该步时间戳作头行。
    ended=True 时在末尾补上整条收尾行（与成败无关，本解析不判定整条）。
    """
    out: list[str] = []
    for ts, msgs in steps:
        for m in msgs:
            out.append(_hdr(ts))
            out.append(m)
    if ended:
        out.append(_hdr("23:59:59.000"))
        out.append("一条龙和配置组任务结束")
    return "\n".join(out)


def test_clean_step_task_variants() -> None:
    """任务名清洗：去掉方向/引号/「开始结束」，只留核心名。"""
    assert _clean_step_task('→ "前往合成台" 开始') == "前往合成台"
    assert _clean_step_task('邮件："全部领取"') == "邮件"
    assert _clean_step_task('探索派遣："全部领取"') == "探索派遣"
    assert _clean_step_task('尝试切换至队伍: "好感队"') == "尝试切换至队伍"


def test_parse_clean_three_step_run() -> None:
    """一条干净的三步一条龙：每步成功，序号/任务/起止时间正确。"""
    log = _run(
        [
            ("05:32:51.876", ["一条龙任务执行: 1/3", '→ "任务启动！"', '邮件："全部领取"', '→ "任务结束"']),
            ("05:32:58.200", ["一条龙任务执行: 2/3", '→ "任务启动！"', '→ "前往合成台" 开始', '→ "前往合成台" 结束', '→ "任务结束"']),
            ("05:33:39.838", ["一条龙任务执行: 3/3", '→ "任务启动！"', '→ "前往冒险家协会领取奖励" 开始', '→ "任务结束"']),
        ]
    )
    steps = _parse_one_dragon_report(log)
    assert steps is not None
    assert len(steps) == 3
    assert [s["task"] for s in steps] == ["邮件", "前往合成台", "前往冒险家协会领取奖励"]
    assert [s["ok"] for s in steps] == [True, True, True]
    assert [s["issue_count"] for s in steps] == [0, 0, 0]
    assert [s["start"] for s in steps] == ["05:32:51.876", "05:32:58.200", "05:33:39.838"]
    assert [s["index"] for s in steps] == [1, 2, 3]
    assert [s["total"] for s in steps] == [3, 3, 3]
    # 内部 issue 装配字段已清理，不出现在结果里
    assert all("issue" not in s for s in steps)


def test_parse_step_with_recoverable_err_still_ok() -> None:
    """步内含 [ERR]（BGI 任务级可恢复异常）但走完「任务结束」→ 记成功 + 异常数。"""
    log = _run(
        [
            (
                "05:32:51.876",
                [
                    "一条龙任务执行: 1/2",
                    '→ "任务启动！"',
                    '邮件："全部领取"',
                    "[ERR] Sequence contains no elements",
                    '→ "任务结束"',
                ],
            ),
            ("05:33:00.000", ["一条龙任务执行: 2/2", '→ "任务启动！"', '自动地脉花："开始"', '→ "任务结束"']),
        ]
    )
    steps = _parse_one_dragon_report(log)
    assert steps is not None
    assert steps[0]["ok"] is True
    assert steps[0]["issue_count"] == 1
    assert "Sequence contains no elements" in steps[0]["issue_text"]
    assert steps[1]["ok"] is True
    assert steps[1]["issue_count"] == 0


def test_parse_interrupted_last_step_is_not_ok() -> None:
    """日志停留在某一步未走完「任务结束」（中途崩溃）→ 该步未完成。"""
    log = _run(
        [
            ("05:32:51.876", ["一条龙任务执行: 1/2", '→ "任务启动！"', '邮件："全部领取"', '→ "任务结束"']),
            ("05:32:58.200", ["一条龙任务执行: 2/2", '→ "任务启动！"', '→ "前往合成台" 开始']),
        ],
        ended=False,  # 没有整条收尾行，第二步也没跑完
    )
    steps = _parse_one_dragon_report(log)
    assert steps is not None
    assert steps[0]["ok"] is True
    assert steps[1]["ok"] is False


def test_parse_step_cut_short_before_next_starts() -> None:
    """没收尾就切入下一步（上一步异常中断）→ 上一步标记未完成，下一步正常解析。"""
    log = _run(
        [
            ("05:32:51.876", ["一条龙任务执行: 1/2", '→ "任务启动！"', '邮件："全部领取"', "[ERR] 崩溃"]),
            ("05:32:58.200", ["一条龙任务执行: 2/2", '→ "任务启动！"', "自动地脉花：开始", '→ "任务结束"']),
        ]
    )
    steps = _parse_one_dragon_report(log)
    assert steps is not None
    assert steps[0]["ok"] is False
    assert steps[0]["issue_count"] == 1
    assert steps[1]["ok"] is True


def test_parse_no_one_dragon_returns_none() -> None:
    """仅配置组（无「一条龙任务执行」）→ 返回 None，调用方省略分步区块。"""
    log = _run(
        [
            ("08:00:01.000", ["启用配置组任务的数量: 1", '配置组 "MAS切换账号" 加载完成，开始执行']),
        ]
    )
    assert _parse_one_dragon_report(log) is None


def test_parse_empty_log_returns_none() -> None:
    assert _parse_one_dragon_report("") is None
    assert _parse_one_dragon_report("[08:00:00] INFO 无进度\n") is None