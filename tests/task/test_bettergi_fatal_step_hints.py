"""BGI 任务级异常（找不到自动战斗脚本、切队回不到主界面）不能让该步显示成「已完成」。

2026-09-19 用户实机：自动秘境进副本后「未匹配到任何战斗脚本」，BGI 直接把该任务结束掉、
仗没打人还留在副本里；紧接着领奖切队「未能返回主界面」也失败。两处 BGI 都照打
``→ "任务结束"`` 继续后面的任务，分步表却把它们报成「已完成（含 N 处异常）」、整条还判成功。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.task.BetterGI.AutoProxy import (
    _back_to_main_failed_hint,
    _combat_script_miss_hint,
)
from app.task.BetterGI.tools.one_dragon_report import parse_one_dragon_report

_INF = (
    "[{time}] [INF] [Primary:S1:P21892:T1789811012633]"
    " BetterGenshinImpact.GameTask.Common.TaskControl"
)
_ERR = (
    "[{time}] [ERR] [Primary:S1:P21892:T1789811012633]"
    " BetterGenshinImpact.GameTask.TaskRunner"
)


def _log(*rows: tuple[str, str]) -> str:
    """按 Serilog 的「头行 + 消息行 + 空行」结构拼日志；行号 0 用 [ERR] 头行。"""
    out: list[str] = []
    for time, message in rows:
        out.append((_ERR if message.startswith("!") else _INF).format(time=time))
        out.append(message.lstrip("!"))
        out.append("")
    return "\n".join(out)


def test_combat_script_miss_marks_the_step_failed():
    log = _log(
        ("17:47:23.216", "一条龙任务执行: 1/1"),
        ("17:47:23.274", '自动秘境：传送到秘境"逆悬的冰河"'),
        ("17:48:07.013", '识别到的队伍角色:"桑多涅,奥黛塔,阿罗夏,七七"'),
        ("17:48:07.226", "!未匹配到任何战斗脚本"),
        ("17:48:07.294", '→ "任务结束"'),
    )

    steps = parse_one_dragon_report(log)

    assert steps is not None and len(steps) == 1
    assert steps[0]["ok"] is False
    assert steps[0]["issue_count"] == 1
    assert steps[0]["issue_text"] == "未匹配到任何战斗脚本"
    # 内部标记不外泄给模板
    assert "fatal" not in steps[0]


def test_only_the_broken_step_fails():
    log = _log(
        ("17:46:45.341", "一条龙任务执行: 1/2"),
        ("17:46:45.347", '→ "前往合成台" 开始'),
        ("17:47:22.184", '→ "前往合成台" 结束'),
        ("17:47:23.214", '→ "任务结束"'),
        ("17:47:23.216", "一条龙任务执行: 2/2"),
        ("17:48:07.226", "!未匹配到任何战斗脚本"),
        ("17:48:07.294", '→ "任务结束"'),
    )

    steps = parse_one_dragon_report(log)

    assert [s["ok"] for s in steps or []] == [True, False]
    assert [s["index"] for s in steps or []] == [1, 2]


def test_switch_party_back_to_main_failure_marks_the_step_failed():
    log = _log(
        ("17:48:07.297", "一条龙任务执行: 1/1"),
        ("17:48:07.363", '尝试切换至队伍: "月感电"'),
        ("17:48:16.322", "!前往冒险家协会领取奖励执行异常：未能返回主界面"),
        ("17:48:16.371", '→ "任务结束"'),
    )

    steps = parse_one_dragon_report(log)

    assert steps is not None
    assert steps[0]["ok"] is False
    assert "未能返回主界面" in steps[0]["issue_text"]


def test_other_in_step_errors_still_count_as_completed():
    # 步内可恢复异常（BGI 捕获后继续）不能跟着一起判失败，否则每条龙都是「部分失败」
    log = _log(
        ("17:45:16.463", "一条龙任务执行: 1/1"),
        ("17:45:54.799", '!选项选择："当前界面不在对话选项界面"'),
        ("17:46:45.339", '→ "任务结束"'),
    )

    steps = parse_one_dragon_report(log)

    assert steps is not None
    assert steps[0]["ok"] is True
    assert steps[0]["issue_count"] == 1


def test_hints_are_actionable_and_absent_when_nothing_matched():
    miss = _log(
        ("17:48:07.013", '识别到的队伍角色:"桑多涅,奥黛塔,阿罗夏,七七"'),
        ("17:48:07.226", "!未匹配到任何战斗脚本"),
    )
    hint = _combat_script_miss_hint(miss)
    assert hint is not None
    assert "桑多涅,奥黛塔,阿罗夏,七七" in hint  # 指出是哪支队伍
    assert "自动战斗" in hint  # 告诉用户去哪配

    stuck = _log(("17:48:16.322", "!未能返回主界面"))
    stuck_hint = _back_to_main_failed_hint(stuck)
    assert stuck_hint is not None and "未能返回主界面" in stuck_hint

    healthy = _log(("17:48:07.294", '→ "任务结束"'))
    assert _combat_script_miss_hint(healthy) is None
    assert _back_to_main_failed_hint(healthy) is None
