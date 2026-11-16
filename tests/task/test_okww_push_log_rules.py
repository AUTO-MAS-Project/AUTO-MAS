"""OK-WW 节点详情规则回归测试。

规则直接匹配上游原始日志：中文界面输出中文译文，英文界面输出源文案，
`info_set` 行在两种界面下都是英文键。这里覆盖每条节点规则的中英文形态，
确保去掉 ok.po 前置翻译后，报告里该出现的节点与状态不丢失、不新增误判。

规则顺序敏感（例如「先约电台已结束」必须先于「先约电台」），因此按真实
运行顺序喂入开始标记与结果标记。
"""

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


NODE_CASES = [
    ("启动", "ok:OK start", "ok:OK start", "✅ 成功: 启动"),
    ("每周乐园", "检查每周乐园任务", "check weekly garden", "✅ 成功: 每周乐园"),
    (
        "邮件",
        "info_set current task claim mail",
        "info_set current task claim mail",
        "✅ 成功: 邮件",
    ),
    (
        "活跃奖励",
        "通过坐标领取每日奖励",
        "claim daily reward via  coordinate",
        "✅ 成功: 活跃奖励",
    ),
    ("梦魇巢穴", "已打开残象探寻", "opened gray_book_boss", "✅ 成功: 梦魇巢穴"),
    (
        "合并声骸",
        "检查已弃置声骸",
        "check discarded echo",
        "⏭ 跳过: 合并声骸",
    ),
    (
        "切换账号",
        "正在返回登录界面",
        "Switching back to login screen",
        "✅ 成功: 切换账号",
    ),
    ("先约电台", "领取先约电台奖励", "battle pass", "✅ 成功: 先约电台"),
    ("每日完成", "每日任务已完成", "Daily Task Completed", "✅ 成功: 每日完成"),
    ("登录", "登录成功", "Login successful", "✅ 成功: 登录"),
    (
        "每周乐园完成",
        "乐园任务完成, 已达到上限",
        "Garden task completed; limit reached",
        "✅ 成功: 每周乐园",
    ),
    (
        "剩余体力",
        "info_set current_stamina 120",
        "info_set current_stamina 120",
        "⚡ 剩余体力: 120",
    ),
]


@pytest.mark.parametrize("label,chinese,english,expected", NODE_CASES)
def test_node_rules_cover_chinese_and_english_logs(label, chinese, english, expected):
    assert resolve([chinese]) == [expected], label
    assert resolve([english]) == [expected], label


FAILURE_CASES = [
    ("梦魇巢穴", "梦魇巢穴任务失败", "NightmareNestTask Failed", "❌ 失败: 梦魇巢穴"),
    ("每周乐园", "乐园任务失败", "GardenTask Failed", "❌ 失败: 每周乐园"),
    ("合并声骸", "声骸合成任务失败", "MergeEchoTask Failed", "❌ 失败: 合并声骸"),
    (
        "合并声骸开包失败",
        "无法使用快捷键 b 打开背包",
        "can not open bag with hotkey b",
        "❌ 失败: 合并声骸",
    ),
    ("切换账号", "切换账号失败", "Failed to switch account", "❌ 失败: 切换账号"),
    (
        "账号选择失败",
        "账号选择失败，已重试 5 次仍未显示 1234，继续尝试登录",
        "Account selection failed after 5 retries; 1234 is still not displayed. Continuing login attempt",
        "❌ 失败: 切换账号",
    ),
    ("下拉无效", "点击下拉列表无效", "click drop down no effect", "❌ 失败: 切换账号"),
    (
        "多账号每日任务",
        "👥 多账号每日任务 exception stopped",
        "👥 Multi Account Daily Task exception stopped",
        "❌ 失败: 多账号每日任务",
    ),
]


@pytest.mark.parametrize("label,chinese,english,expected", FAILURE_CASES)
def test_failure_rules_cover_chinese_and_english_logs(
    label, chinese, english, expected
):
    assert resolve([chinese]) == [expected], label
    assert resolve([english]) == [expected], label


def test_weekly_garden_skip_before_completion():
    assert resolve(["检查每周乐园", "每周乐园已完成"]) == ["⏭ 跳过: 每周乐园"]
    assert resolve(["检查每周乐园", "每周乐园任务已完成"]) == ["⏭ 跳过: 每周乐园"]
    assert resolve(["check weekly garden", "weekly garden already completed"]) == [
        "⏭ 跳过: 每周乐园"
    ]


def test_battle_pass_ended_is_skip_with_reason():
    assert resolve(["领取先约电台奖励", "无法领取先约电台奖励，可能已结束"]) == [
        "⏭ 跳过: 先约电台（已结束）"
    ]
    assert resolve(["battle pass", "can not battle pass, maybe ended"]) == [
        "⏭ 跳过: 先约电台（已结束）"
    ]


def test_insufficient_discarded_echo_is_skip_with_reason():
    assert resolve(["检查已弃置声骸", "Must have 1000 discarded Echo to Run"]) == [
        "⏭ 跳过: 合并声骸（已弃置声骸不足 1000）"
    ]
    assert resolve(["检查已弃置声骸", "需要至少 1000 个已弃置声骸才能运行"]) == [
        "⏭ 跳过: 合并声骸（已弃置声骸不足 1000）"
    ]


def test_traceback_source_line_no_longer_infers_skip():
    assert resolve(["检查已弃置声骸", "if self.click_dialog_left_button():"]) == [
        "⏭ 跳过: 合并声骸"
    ]


def test_stamina_after_farming_uses_last_reading():
    assert resolve(
        [
            "info_set current_stamina 180",
            "must_use completed current stamina: 120",
        ]
    ) == ["✅ 成功: 体力刷本", "⚡ 剩余体力: 120"]


def test_daily_preview_produces_echo_but_not_daily_completion():
    """farm 4C 预告行含「每日任务已完成」子串，行尾锚定保证不提前产出节点。"""
    assert resolve(["每日任务已完成，开始传送并刷取4C声骸"]) == ["✅ 成功: 4C声骸"]
    assert resolve(["Daily task completed, start teleport to farm 4C echo"]) == [
        "✅ 成功: 4C声骸"
    ]


@pytest.mark.parametrize(
    "start,done",
    [
        ("DailyTask:每日任务已完成，开始传送并刷取4C声骸", "DailyTask:每日任务已完成"),
        (
            "DailyTask:Daily task completed, start teleport to farm 4C echo",
            "DailyTask:Daily Task Completed",
        ),
    ],
)
def test_daily_completion_preserves_extra_echo_node(start, done):
    assert resolve([start]) == ["✅ 成功: 4C声骸"]
    assert resolve([start, done]) == ["✅ 成功: 4C声骸", "✅ 成功: 每日完成"]
    assert resolve([done]) == ["✅ 成功: 每日完成"]
    assert resolve([start, "ok:OK start", done]) == [
        "✅ 成功: 启动",
        "✅ 成功: 每日完成",
    ]


@pytest.mark.parametrize(
    "message,expected",
    [
        ("所有满批次的已弃置声骸均已合成。", "✅ 成功: 合并声骸"),
        ("All full batches of discarded Echoes have been merged.", "✅ 成功: 合并声骸"),
        (
            "nightmare nest unreachable, skip this run",
            "⚠ 异常: 梦魇巢穴（部分巢穴无法到达）",
        ),
        ("梦魇巢穴：阵亡 3 次，跳过本次：nest", "⚠ 异常: 梦魇巢穴（部分巢穴阵亡过多）"),
        (
            "nightmare nest: died 3 times, skip this run: nest",
            "⚠ 异常: 梦魇巢穴（部分巢穴阵亡过多）",
        ),
        ("梦魇巢穴无法到达，跳过本次", "⚠ 异常: 梦魇巢穴（部分巢穴无法到达）"),
    ],
)
def test_new_native_result_messages(message, expected):
    assert resolve([message]) == [expected]


@pytest.mark.parametrize(
    "failure",
    [
        "四费声骸刷取：超过恢复重试上限（3），停止刷取",
        "farm 4c: exceeded recovery retries (3), stop farming",
        "TaskExecutor:📅 Daily Task exception stopped",
        "TaskExecutor:📅 每日任务 exception stopped",
    ],
)
def test_extra_echo_failure_is_not_hidden_by_daily_completion(failure):
    output = resolve(
        [
            "Daily task completed, start teleport to farm 4C echo",
            failure,
            "Daily Task Completed",
        ]
    )
    assert "❌ 失败: 4C声骸" in output
    assert "✅ 成功: 4C声骸" not in output


@pytest.mark.parametrize(
    "target,name",
    [
        ("Teleport to Tacet Suppression", "无音区"),
        ("Teleport to Forgery Challenge", "凝素领域"),
        ("Target Simulation Challenge", "模拟领域"),
    ],
)
def test_stamina_target_and_terminal_branches(target, name):
    start = f"info_set {target} 0"
    assert resolve([start, "current stamina: 20 not enough to continue"]) == [
        f"✅ 成功: 体力刷本（{name}）",
        "⚡ 剩余体力: 20",
    ]
    assert resolve(
        [start, "farm_domain: exceeded recovery retries (3), stop farming"]
    ) == [f"❌ 失败: 体力刷本（{name}）"]


def test_merge_completion_and_failure_override_check_only_result():
    start = "检查已弃置声骸"
    assert resolve(
        [start, "All full batches of discarded Echoes have been merged."]
    ) == ["✅ 成功: 合并声骸"]
    assert resolve([start, "MergeEchoTask Failed"]) == ["❌ 失败: 合并声骸"]


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
