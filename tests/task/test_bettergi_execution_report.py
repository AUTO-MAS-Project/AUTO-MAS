"""执行层（MASOneDragon/main.js）分步报告解析。

背景：main.js 不打原生「一条龙任务执行: X/N」进度行，只打 MAS_STEP_* 标记，因此走执行层
的运行此前在通知里完全没有流程表格（只有「成功」）。本测试按 2026-09-15 实机日志的真实
格式覆盖：正常完成、单步失败、树脂耗尽、必填项缺失、未走执行层、多步混合。
"""

from app.task.BetterGI.tools.one_dragon_report import (
    parse_execution_layer_report,
    parse_one_dragon_report,
)

# 真实日志形态：Serilog 头行（含时间戳与级别）下方跟随消息行
_HDR = "[{time}] [INF] [Primary:S1:P10896:T1789484744830] BetterGenshinImpact.Core.Script.Dependence.Log"


def _log(*rows: tuple[str, str]) -> str:
    out: list[str] = []
    for time, message in rows:
        out.append(_HDR.format(time=time))
        out.append(message)
        out.append("")
    return "\n".join(out)


def test_single_step_failure_is_reported_with_reason():
    log = _log(
        ("23:06:36.703", "MAS_PLAN_BEGIN 1"),
        ("23:06:36.738", "MAS_STEP_BEGIN: 0732102e356b48b78fdcd0a847f3f09e 自动地脉花"),
        (
            "23:07:28.851",
            "MAS_STEP_FAIL: 0732102e356b48b78fdcd0a847f3f09e 自动地脉花 "
            "寻找地脉花失败：未在地图上识别到地脉花图标",
        ),
        ("23:07:28.852", "MAS_PLAN_DONE_WITH_FAILURES 1"),
    )

    steps = parse_execution_layer_report(log)

    assert steps is not None and len(steps) == 1
    step = steps[0]
    assert (step["index"], step["total"]) == (1, 1)
    assert step["task"] == "自动地脉花"
    assert step["ok"] is False
    assert step["issue_count"] == 1
    assert "寻找地脉花失败" in step["issue_text"]
    assert step["start"] == "23:06:36.738"
    assert step["end"] == "23:07:28.851"


def test_two_steps_one_done_one_failed():
    log = _log(
        ("10:00:00.000", "MAS_PLAN_BEGIN 2"),
        ("10:00:01.000", "MAS_STEP_BEGIN: uid-a 自动秘境"),
        ("10:01:00.000", "MAS_STEP_DONE: uid-a 自动秘境"),
        ("10:01:01.000", "MAS_STEP_BEGIN: uid-b 自动地脉花"),
        ("10:02:00.000", "MAS_STEP_FAIL: uid-b 自动地脉花 识别失败"),
        ("10:02:01.000", "MAS_PLAN_DONE_WITH_FAILURES 1"),
    )

    steps = parse_execution_layer_report(log)

    assert steps is not None and len(steps) == 2
    assert (steps[0]["index"], steps[0]["total"], steps[0]["ok"]) == (1, 2, True)
    assert (steps[1]["index"], steps[1]["total"], steps[1]["ok"]) == (2, 2, False)
    assert steps[0]["issue_count"] == 0


def test_resin_exhaustion_counts_as_normal_end_with_note():
    log = _log(
        ("10:00:00.000", "MAS_PLAN_BEGIN 2"),
        ("10:00:01.000", "MAS_STEP_BEGIN: uid-a 自动地脉花"),
        ("10:00:30.000", "MAS_STEP_RESIN_END: uid-a 自动地脉花 树脂耗尽，任务结束"),
        ("10:00:31.000", "MAS_PLAN_RESIN_END"),
        ("10:00:31.000", "MAS_PLAN_DONE"),
    )

    steps = parse_execution_layer_report(log)

    assert steps is not None and len(steps) == 1
    assert steps[0]["ok"] is True
    assert steps[0]["issue_count"] == 1
    assert "树脂耗尽" in steps[0]["issue_text"]


def test_missing_required_config_is_listed_as_failed():
    # 标记打在 BEGIN 之前（该步根本没进 BGI），且整条仍会打 MAS_PLAN_DONE
    log = _log(
        ("10:00:00.000", "MAS_PLAN_BEGIN 1"),
        ("10:00:00.100", "MAS_STEP_MISSING_CONFIG: uid-a 自动首领讨伐 首领"),
        ("10:00:00.200", "MAS_PLAN_DONE"),
    )

    steps = parse_execution_layer_report(log)

    assert steps is not None and len(steps) == 1
    assert steps[0]["ok"] is False
    assert steps[0]["issue_text"] == "首领"


def test_interrupted_step_without_done_marker_is_failed():
    # MAS_PLAN_FAIL 中断在步内：没有 DONE/FAIL，按未完成处理
    log = _log(
        ("10:00:00.000", "MAS_PLAN_BEGIN 1"),
        ("10:00:01.000", "MAS_STEP_BEGIN: uid-a 自动秘境"),
        ("10:00:02.000", "MAS_PLAN_FAIL 脚本异常终止"),
    )

    steps = parse_execution_layer_report(log)

    assert steps is not None and len(steps) == 1
    assert steps[0]["ok"] is False


def test_skipped_steps_are_not_listed():
    log = _log(
        ("10:00:00.000", "MAS_PLAN_BEGIN 3"),
        ("10:00:00.100", "MAS_STEP_SKIP: uid-off"),
        ("10:00:00.200", "MAS_STEP_DAILY: uid-daily 领取邮件"),
        ("10:00:00.300", "MAS_STEP_BEGIN: uid-on 自动地脉花"),
        ("10:00:10.000", "MAS_STEP_DONE: uid-on 自动地脉花"),
        ("10:00:10.100", "MAS_PLAN_DONE"),
    )

    steps = parse_execution_layer_report(log)

    assert steps is not None and len(steps) == 1
    assert steps[0]["task"] == "自动地脉花"
    assert (steps[0]["index"], steps[0]["total"]) == (1, 1)


def test_native_one_dragon_log_has_no_execution_layer_report():
    # 原生一条龙日志：只有进度行，执行层解析必须返回 None（由原生解析器负责）
    native = _log(
        ("10:00:00.000", "一条龙任务执行: 1/1"),
        ("10:00:01.000", '→ "任务启动！"'),
        ("10:00:05.000", '→ "任务结束"'),
    )

    assert parse_execution_layer_report(native) is None
    assert parse_one_dragon_report(native) is not None
