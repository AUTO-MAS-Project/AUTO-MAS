"""执行层（MASOneDragon/main.js）分步报告解析。

背景：main.js 不打原生「一条龙任务执行: X/N」进度行，只打 MAS_STEP_* 标记，因此走执行层
的运行此前在通知里完全没有流程表格（只有「成功」）。本测试按 2026-09-15 实机日志的真实
格式覆盖：正常完成、单步失败、树脂耗尽、必填项缺失、未走执行层、多步混合，以及执行层与
原生一条龙两相拼成一张表。
"""

from app.task.BetterGI.AutoProxy import _merge_one_dragon_reports
from app.task.BetterGI.tools.one_dragon_report import (
    count_failed_custom_items,
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


# 原生一条龙真实日志形态（2026-09-09 实机，4 个日常任务）：进度行不带任务名，且步内第一条
# 日志往往是传送/切换区域/子步骤开始之类的过程日志——按「取第一行」得到的名字并不是任务名。
_NATIVE_LOG = _log(
    ("01:26:44.167", "一条龙任务执行: 1/4"),
    ("01:26:44.169", '→ "任务启动！"'),
    ("01:26:47.310", '邮件："全部领取"'),
    ("01:26:50.490", '→ "任务结束"'),
    ("01:26:50.491", "一条龙任务执行: 2/4"),
    ("01:26:50.491", '→ "任务启动！"'),
    ("01:26:53.232", '切换到区域："尘歌壶"'),
    ("01:26:53.260", '领取尘歌壶奖励:"洞天名称：清琼岛"'),
    ("01:27:55.809", '→ "任务结束"'),
    ("01:27:55.810", "一条龙任务执行: 3/4"),
    ("01:27:55.810", '→ "任务启动！"'),
    ("01:27:55.813", '→ "前往合成台" 开始'),
    ("01:28:20.090", "无需合成浓缩树脂"),
    ("01:28:22.033", '→ "前往合成台" 结束'),
    ("01:28:23.053", '→ "任务结束"'),
    ("01:28:23.054", "一条龙任务执行: 4/4"),
    ("01:28:23.054", '→ "任务启动！"'),
    ("01:28:23.058", '→ "前往冒险家协会领取奖励" 开始'),
    ("01:29:20.000", '→ "任务结束"'),
)

_NATIVE_NAMES = ["领取邮件", "领取尘歌壶奖励", "合成树脂", "领取每日奖励"]


def test_native_log_without_config_names_falls_back_to_log_line_guess():
    # 回归基线：没有配置顺序表时只能按步内第一行推断，多数步骤拿到的不是任务名
    # （2026-09-19 实机：通知分步表出现「区域选择动画等待达到上限」这类过程日志当任务名）
    steps = parse_one_dragon_report(_NATIVE_LOG)

    assert steps is not None
    assert [s["task"] for s in steps] == [
        "邮件",
        "切换到区域",
        "前往合成台",
        "前往冒险家协会领取奖励",
    ]


def test_native_steps_take_task_names_from_config_order():
    # 有配置顺序表时按进度行序号取用：不依赖步内日志，过程日志不再冒充任务名
    steps = parse_one_dragon_report(_NATIVE_LOG, _NATIVE_NAMES)

    assert steps is not None
    assert [s["task"] for s in steps] == _NATIVE_NAMES
    # 其余字段仍来自日志行
    assert (steps[1]["index"], steps[1]["total"]) == (2, 4)
    assert (steps[1]["start"], steps[1]["end"]) == ("01:26:50.491", "01:27:55.809")
    assert all(s["ok"] for s in steps)


def test_native_steps_ignore_mismatched_config_names():
    # 表长与进度行 N 不符（运行期间配置被改过）时不得错位贴名，退回日志推断
    steps = parse_one_dragon_report(_NATIVE_LOG, ["领取邮件", "领取尘歌壶奖励"])

    assert steps is not None
    assert [s["task"] for s in steps][:2] == ["邮件", "切换到区域"]


def test_native_interrupted_run_still_maps_names_by_progress_index():
    # 中断在第 2 步（无「任务结束」）：序号照旧，名字仍按序号取，不会整体前移
    log = _log(
        ("01:26:44.167", "一条龙任务执行: 1/4"),
        ("01:26:44.169", '→ "任务启动！"'),
        ("01:26:47.310", '邮件："全部领取"'),
        ("01:26:50.490", '→ "任务结束"'),
        ("01:26:50.491", "一条龙任务执行: 2/4"),
        ("01:26:53.232", '切换到区域："尘歌壶"'),
    )

    steps = parse_one_dragon_report(log, _NATIVE_NAMES)

    assert steps is not None
    assert [s["task"] for s in steps] == ["领取邮件", "领取尘歌壶奖励"]
    assert [s["ok"] for s in steps] == [True, False]


# 分步表两相拼接（2026-09-19 实机）：一次任务先跑执行层（战斗 4 项）再跑原生一条龙（日常），
# 此前只取一相，通知里只剩后跑的原生 3 项，执行层那 4 项看不见。以下按当天真实日志形态覆盖。
_EXEC_LOG = _log(
    ("13:41:08.217", "MAS_STEP_BEGIN: uid-a 自动幽境危战"),
    ("13:41:13.509", "MAS_STEP_DONE: uid-a 自动幽境危战"),
    ("13:41:13.510", "MAS_STEP_BEGIN: uid-b 自动地脉花"),
    ("13:42:31.205", "MAS_STEP_FAIL: uid-b 自动地脉花 开启地脉花失败，已达最大重试次数"),
    ("13:42:31.205", "MAS_STEP_BEGIN: uid-c 自动首领讨伐"),
    ("13:44:01.863", "MAS_STEP_DONE: uid-c 自动首领讨伐"),
    ("13:44:01.894", "MAS_STEP_BEGIN: uid-d 自动秘境"),
    ("13:46:13.879", "MAS_STEP_DONE: uid-d 自动秘境"),
    ("13:46:13.880", "MAS_PLAN_DONE_WITH_FAILURES 1"),
)


def test_merge_lists_exec_phase_then_native_phase_with_single_numbering():
    exec_steps = parse_execution_layer_report(_EXEC_LOG)
    native_steps = parse_one_dragon_report(_NATIVE_LOG, _NATIVE_NAMES)

    merged = _merge_one_dragon_reports(exec_steps, native_steps)

    assert merged is not None
    # 执行层在前、原生一条龙在后；相内顺序不变（各自的实际执行顺序）
    assert [s["task"] for s in merged] == [
        "自动幽境危战",
        "自动地脉花",
        "自动首领讨伐",
        "自动秘境",
        *_NATIVE_NAMES,
    ]
    # 两相各自都从 1 开始编号，拼接后必须重编号成同一条 1/N…N/N
    assert [s["index"] for s in merged] == list(range(1, 9))
    assert {s["total"] for s in merged} == {8}
    assert [s["ok"] for s in merged][:4] == [True, False, True, True]


def test_merge_keeps_single_phase_as_is():
    native_steps = parse_one_dragon_report(_NATIVE_LOG, _NATIVE_NAMES)

    # 没走执行层（或那一相没解析出步骤）时，原生这一相原样进表
    assert _merge_one_dragon_reports(None, native_steps) == native_steps


def test_merge_returns_none_without_any_steps():
    assert _merge_one_dragon_reports(None, None) is None
    assert _merge_one_dragon_reports([], []) is None


# ── 自定义项（配置组 / 脚本 / 路径 / 录制）：不经 main.js，只能靠 BGI 项目行还原 ──
# 2026-09-19 实机：一条龙队列里全是自定义项时通知整块分步表缺失（只有起始/结束时间），
# 因为执行层那一相此前只认 MAS_STEP_* 标记，而这些条目由 --startGroups 直连 BGI 配置组执行。
_ERR_HDR = (
    "[{time}] [ERR] [Primary:S1:P26956:T1788994819148]"
    " BetterGenshinImpact.GameTask.Common.TaskControl"
)


def _raw(*lines: str) -> str:
    """直接拼日志行（需要 [ERR] 头行或自定义记录器名时用；普通用例走 ``_log``）。"""
    out: list[str] = []
    for line in lines:
        out.append(line)
        out.append("")
    return "\n".join(out)


# 当天真实日志形态：段1 三个脚本（js 项）、段2 一个脚本（配置组项内部的 js 项目）
_CUSTOM_ONLY_LOG = _log(
    ("16:46:26.184", '配置组 "MAS-79878431-执行层段1" 加载完成，共3个脚本，开始执行'),
    ("16:46:26.358", '→ 开始执行JS脚本: "读取当前树脂"'),
    ("16:46:44.101", '→ 脚本执行结束: "读取当前树脂", 耗时: 0分17.743秒'),
    ("16:46:45.114", '→ 开始执行JS脚本: "读取当前摩拉记录并发送通知"'),
    ("16:46:48.887", '→ 脚本执行结束: "读取当前摩拉记录并发送通知", 耗时: 0分3.773秒'),
    ("16:46:49.901", '→ 开始执行JS脚本: "读取当前树脂"'),
    ("16:47:05.984", '→ 脚本执行结束: "读取当前树脂", 耗时: 0分16.083秒'),
    ("16:47:07.031", '配置组 "MAS-79878431-执行层段1" 执行结束'),
    ("16:47:09.050", '配置组 "MAS-79878431-执行层段2" 加载完成，共1个脚本，开始执行'),
    ("16:47:09.051", '→ 开始执行JS脚本: "提瓦特记事本"'),
    ("16:47:35.212", '→ 脚本执行结束: "提瓦特记事本", 耗时: 0分26.161秒'),
    ("16:47:36.222", '配置组 "MAS-79878431-执行层段2" 执行结束'),
)


def test_custom_items_alone_still_produce_a_report():
    steps = parse_execution_layer_report(_CUSTOM_ONLY_LOG)

    assert steps is not None
    assert [s["task"] for s in steps] == [
        "读取当前树脂",
        "读取当前摩拉记录并发送通知",
        "读取当前树脂",
        "提瓦特记事本",
    ]
    assert [s["index"] for s in steps] == [1, 2, 3, 4]
    assert {s["total"] for s in steps} == {4}
    assert all(s["ok"] for s in steps)
    assert steps[0]["start"] == "16:46:26.358"
    assert steps[0]["end"] == "16:46:44.101"
    assert steps[3]["start"] == "16:47:09.051"
    assert steps[3]["end"] == "16:47:35.212"


def test_custom_items_and_combat_steps_share_one_table_in_log_order():
    log = _raw(
        _HDR.format(time="16:46:26.358"),
        '→ 开始执行JS脚本: "读取当前树脂"',
        _HDR.format(time="16:46:44.101"),
        '→ 脚本执行结束: "读取当前树脂", 耗时: 0分17.743秒',
        # 段2 就是战斗段：MASOneDragon 本身也是 BGI 项目，内部打 MAS_STEP_* 标记
        _HDR.format(time="16:47:09.051"),
        '→ 开始执行JS脚本: "MAS一条龙执行层"',
        _HDR.format(time="16:47:20.000"),
        "MAS_STEP_BEGIN: uid-a 自动秘境",
        _HDR.format(time="16:48:20.000"),
        "MAS_STEP_DONE: uid-a 自动秘境",
        _HDR.format(time="16:48:21.000"),
        "MAS_STEP_BEGIN: uid-b 自动地脉花",
        _HDR.format(time="16:49:21.000"),
        "MAS_STEP_FAIL: uid-b 自动地脉花 寻找地脉花失败",
        _HDR.format(time="16:49:22.000"),
        "MAS_PLAN_DONE_WITH_FAILURES 1",
        _HDR.format(time="16:49:30.000"),
        '→ 脚本执行结束: "MAS一条龙执行层", 耗时: 2分21.000秒',
    )

    steps = parse_execution_layer_report(log)

    # 自定义项在前（实际先跑），战斗步随后；MASOneDragon 本体不再重复出一行总账
    assert [s["task"] for s in steps] == ["读取当前树脂", "自动秘境", "自动地脉花"]
    assert [s["index"] for s in steps] == [1, 2, 3]
    assert {s["total"] for s in steps} == {3}
    assert [s["ok"] for s in steps] == [True, True, False]
    assert "寻找地脉花失败" in steps[2]["issue_text"]


def test_pathing_and_keymouse_items_are_listed_one_row_per_project():
    log = _log(
        ("07:02:56.343", '→ 开始执行地图追踪任务: "214璃月-轻策庄3.json"'),
        ("07:05:20.000", '→ 脚本执行结束: "214璃月-轻策庄3.json", 耗时: 2分23.033秒'),
        ("07:05:21.000", '→ 开始执行键鼠脚本: "BetterGI_GCM_202609101957221239.json"'),
        ("07:05:48.164", '→ 脚本执行结束: "BetterGI_GCM_202609101957221239.json", 耗时: 0分27.415秒'),
    )

    steps = parse_execution_layer_report(log)

    assert steps is not None
    assert [s["task"] for s in steps] == [
        "214璃月-轻策庄3.json",
        "BetterGI_GCM_202609101957221239.json",
    ]
    assert all(s["ok"] for s in steps)


def test_failed_route_is_reported_failed_even_with_a_faked_end_line():
    # BGI 在路线失败时会「伪造」收尾行（耗时 0分0.000秒），成败只能看步内 [ERR]
    log = _raw(
        _HDR.format(time="07:02:56.343"),
        '→ 开始执行地图追踪任务: "214璃月-轻策庄3.json"',
        _ERR_HDR.format(time="07:03:24.298"),
        '执行地图追踪时候发生错误: "传送失败"',
        _HDR.format(time="07:03:24.312"),
        '→ 脚本执行结束: "214璃月-轻策庄3.json", 耗时: 0分0.000秒',
        _HDR.format(time="07:03:34.169"),
        '→ 开始执行地图追踪任务: "216璃月-珉林北4.json"',
        _HDR.format(time="07:05:00.000"),
        '→ 脚本执行结束: "216璃月-珉林北4.json", 耗时: 1分25.831秒',
    )

    steps = parse_execution_layer_report(log)

    assert [s["ok"] for s in steps] == [False, True]
    assert steps[0]["issue_count"] == 1
    assert '执行地图追踪时候发生错误: "传送失败"' == steps[0]["issue_text"]
    assert steps[1]["issue_count"] == 0


def test_item_interrupted_without_end_line_is_incomplete():
    log = _log(
        ("16:47:09.051", '→ 开始执行JS脚本: "提瓦特记事本"'),
        ("16:47:10.000", "全部启用项目执行完毕"),
    )

    steps = parse_execution_layer_report(log)

    assert steps is not None and len(steps) == 1
    assert steps[0]["ok"] is False
    assert steps[0]["end"] == "16:47:10.000"


# ── 自定义项失败要计入「部分失败」──────────────────────────────
# BGI 的判定是组级的：单个脚本/路线失败不会让配置组失败，也不打 MAS_PLAN_DONE_WITH_FAILURES，
# 只认 MAS 汇总标记会把这类失败整段漏掉（2026-09-19 实机：脚本项失败仍报成功）。


def test_failed_custom_items_are_counted():
    assert count_failed_custom_items(_CUSTOM_ONLY_LOG) == 0

    log = _raw(
        _HDR.format(time="07:02:56.343"),
        '→ 开始执行地图追踪任务: "214璃月-轻策庄3.json"',
        _ERR_HDR.format(time="07:03:24.298"),
        '执行地图追踪时候发生错误: "传送失败"',
        _HDR.format(time="07:03:24.312"),
        '→ 脚本执行结束: "214璃月-轻策庄3.json", 耗时: 0分0.000秒',
        _HDR.format(time="07:03:34.169"),
        '→ 开始执行地图追踪任务: "216璃月-珉林北4.json"',
        _HDR.format(time="07:05:00.000"),
        '→ 脚本执行结束: "216璃月-珉林北4.json", 耗时: 1分25.831秒',
    )

    assert count_failed_custom_items(log) == 1


def test_mas_step_failures_are_not_counted_as_custom_items():
    # 战斗步失败由 main.js 的 MAS_PLAN_DONE_WITH_FAILURES 汇总，不能在这里重复计数
    assert count_failed_custom_items(_EXEC_LOG) == 0

    # 混合场景：自定义项 1 个失败 + 战斗步 1 个失败 → 只数自定义项
    log = _raw(
        _HDR.format(time="16:47:09.051"),
        '→ 开始执行JS脚本: "读取当前树脂"',
        _ERR_HDR.format(time="16:47:10.000"),
        '执行脚本时发生异常: "Error: 树脂耗尽，任务结束"',
        _HDR.format(time="16:47:11.000"),
        '→ 脚本执行结束: "读取当前树脂", 耗时: 0分0.000秒',
        _HDR.format(time="16:47:20.000"),
        "MAS_STEP_BEGIN: uid-a 自动秘境",
        _HDR.format(time="16:48:20.000"),
        "MAS_STEP_FAIL: uid-a 自动秘境 寻路失败",
        _HDR.format(time="16:48:21.000"),
        "MAS_PLAN_DONE_WITH_FAILURES 1",
    )

    assert count_failed_custom_items(log) == 1


def test_custom_item_rows_are_tagged_for_the_caller():
    # 标记是 AutoProxy 区分「自定义项失败」与「战斗步失败」的依据
    steps = parse_execution_layer_report(_CUSTOM_ONLY_LOG)

    assert all(s.get("bgi_project") is True for s in steps or [])
