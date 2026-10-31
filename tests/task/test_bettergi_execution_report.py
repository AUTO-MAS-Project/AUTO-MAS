"""BetterGI 的任务失败结果优先于执行层的正常返回标记。"""

import pytest

from app.task.BetterGI.tools.one_dragon_report import parse_execution_layer_report


def log_entry(time, level, logger, message):
    return f"[{time}] [{level}] [Primary:S1:P1:T1] {logger}\n{message}\n"


@pytest.mark.parametrize(
    "task", ["自动秘境", "自动首领讨伐", "自动幽境危战", "自动地脉花"]
)
def test_dispatcher_failure_overrides_done_and_keeps_next_step(task):
    reason = "独立任务失败：配置与本次任务不匹配（invalid_parameter）"
    log = "".join(
        [
            log_entry("09:00:00.000", "INF", "Script.Log", f"MAS_STEP_BEGIN: a {task}"),
            log_entry(
                "09:00:01.000", "ERR", "Core.Script.Dependence.Dispatcher", reason
            ),
            log_entry("09:00:02.000", "INF", "Script.Log", f"MAS_STEP_DONE: a {task}"),
            log_entry(
                "09:00:03.000", "INF", "Script.Log", "MAS_STEP_BEGIN: b 自动秘境"
            ),
            log_entry("09:00:04.000", "INF", "Script.Log", "MAS_STEP_DONE: b 自动秘境"),
        ]
    )

    steps = parse_execution_layer_report(log)

    assert [step["ok"] for step in steps] == [False, True]
    assert steps[0]["issue_text"] == reason
    assert steps[0]["issue_count"] == 1
    assert steps[1]["issue_count"] == 0


@pytest.mark.parametrize(
    ("logger", "message"),
    [
        ("GameTask.TaskControl", "操作暂时失败，稍后重试"),
        ("Core.Script.Dependence.Dispatcher", "操作暂时失败，稍后重试"),
        ("Script.Log", "独立任务失败：用户脚本打印的普通消息"),
    ],
)
def test_recoverable_error_is_not_a_terminal_failure(logger, message):
    log = "".join(
        [
            log_entry("09:00:00", "INF", "Script.Log", "MAS_STEP_BEGIN: a 自动秘境"),
            log_entry("09:00:01", "ERR", logger, message),
            log_entry("09:00:02", "INF", "Script.Log", "MAS_STEP_DONE: a 自动秘境"),
        ]
    )

    steps = parse_execution_layer_report(log)

    assert steps[0]["ok"] is True
    assert steps[0]["issue_count"] == 1


def test_terminal_failure_takes_priority_over_recoverable_error():
    log = "".join(
        [
            log_entry("09:00:00", "INF", "Script.Log", "MAS_STEP_BEGIN: a 自动秘境"),
            log_entry("09:00:01", "ERR", "GameTask.TaskControl", "正在重试"),
            log_entry(
                "09:00:02",
                "ERR",
                "Core.Script.Dependence.Dispatcher",
                "独立任务失败: 无法执行",
            ),
            log_entry("09:00:03", "INF", "Script.Log", "MAS_STEP_DONE: a 自动秘境"),
        ]
    )

    steps = parse_execution_layer_report(log)

    assert steps[0]["ok"] is False
    assert steps[0]["issue_count"] == 2
    assert steps[0]["issue_text"] == "独立任务失败: 无法执行"
