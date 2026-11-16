"""本次真实运行中节点误报与告警丢失的回归。"""

import pytest

from app.task.Okww.push_log import OKWW_PUSH_RULES, okww_resolve
from app.utils.common.log_box import LogPipeline


def resolve(lines: list[str]) -> list[str]:
    pipeline = LogPipeline()
    for rule in OKWW_PUSH_RULES:
        pipeline.add_rule(*rule)
    pipeline.postprocessors.append(okww_resolve)
    for index, line in enumerate(lines):
        pipeline.feed(
            f"2026-11-05 09:00:00,000 INFO TaskExecutor {line}", timestamp=float(index)
        )
    return [entry.text for entry in pipeline.finish()]


@pytest.mark.parametrize("failed", [False, True])
def test_partial_nest_skips_are_deduplicated_warnings_not_final_results(failed):
    lines = [
        "opened gray_book_boss",
        "nightmare nest unreachable, skip this run: a",
        "nightmare nest unreachable, skip this run: b",
        "nightmare nest: died 3 times, skip this run: c",
    ]
    if failed:
        lines.append("NightmareNestTask Failed")
    assert resolve(lines) == [
        f"{'❌ 失败' if failed else '✅ 成功'}: 梦魇巢穴",
        "⚠ 异常: 梦魇巢穴（部分巢穴无法到达）",
        "⚠ 异常: 梦魇巢穴（部分巢穴阵亡过多）",
    ]


@pytest.mark.parametrize(
    "message", ["monthly_card found click", "检测到月卡奖励，点击领取"]
)
def test_monthly_popup_is_not_a_report_node(message):
    assert resolve([message]) == []
    assert resolve([message, "TaskExecutor:📅 Daily Task exception stopped"]) == [
        "❌ 失败: 每日完成"
    ]


def test_retry_success_replaces_previous_attempt_nodes_and_warnings():
    assert resolve(
        [
            "ok:OK start",
            "opened gray_book_boss",
            "nightmare nest unreachable, skip this run",
            "info_set current_stamina 120",
            "TaskExecutor:📅 Daily Task exception stopped",
            "ok:OK start",
            "Daily task completed, start teleport to farm 4C echo",
            "Daily Task Completed",
        ]
    ) == ["✅ 成功: 启动", "✅ 成功: 4C声骸", "✅ 成功: 每日完成"]


def test_retry_failure_remains_visible_after_previous_success():
    assert resolve(
        [
            "ok:OK start",
            "Daily Task Completed",
            "ok:OK start",
            "TaskExecutor:📅 Daily Task exception stopped",
        ]
    ) == ["✅ 成功: 启动", "❌ 失败: 每日完成"]


@pytest.mark.parametrize("name", ["👥 Multi Account Daily Task", "👥 多账号每日任务"])
def test_full_multi_account_exception_is_not_daily_exception(name):
    assert resolve([f"TaskExecutor:{name} exception stopped"]) == [
        "❌ 失败: 多账号每日任务"
    ]


@pytest.mark.parametrize(
    "warning",
    [
        "选择目标失败!请关闭显卡滤镜和锐化!",
        "Target enemy failed, please disable Nvidia/AMD Filter or Sharpening!",
    ],
)
def test_echo_target_warning_is_extra_deduplicated_and_preserves_success(warning):
    assert resolve(
        [
            "DailyTask:Daily task completed, start teleport to farm 4C echo",
            f"FarmEchoTask:{warning}",
            f"FarmEchoTask:{warning}",
            "DailyTask:Daily Task Completed",
        ]
    ) == ["✅ 成功: 4C声骸", "✅ 成功: 每日完成", "⚠ 异常: 4C声骸（选择战斗目标失败）"]
    assert (
        resolve(
            [
                f"NightmareNestTask:{warning}",
                "CombatCheck:target_enemy failed, try recheck break out of combat",
            ]
        )
        == []
    )
