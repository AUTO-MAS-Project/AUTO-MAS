from app.task.BetterGI.tools.drop_statistics import (
    format_drop_statistics,
    parse_drop_lines,
)

# 采样自实机日志（better-genshin-impact*.log，2026-09-11/14）：BGI 把明细段整体包在一对
# ASCII 双引号里，首领那行的来源名也带引号。日志文件里消息独占一行，这里同时覆盖带前缀
# 与裸行两种形态。
DOMAIN_LINES = [
    "[10:01:02.100] [INF] [Primary:S1:P1:T1] BetterGenshinImpact.GameTask.AutoDomain.AutoDomainTask",
    "",
    "自动秘境：开始奖励识别",
    "",
    '自动秘境：本轮奖励识别结果 "摩拉 x1000, 大英雄的经验 x5"',
    "",
    '自动秘境：本轮奖励识别结果 "摩拉 x800, 精锻用魔矿 x3"',
    "",
]

BOSS_LINES = [
    '"自动首领讨伐"：本轮奖励识别结果 "冒险家的经验 x2, 摩拉 x600"',
]

EMPTY_LINES = [
    "自动秘境：本轮奖励识别结果为空",
    "自动秘境：奖励识别失败，已跳过本轮奖励汇总",
]


def test_parse_merges_items_across_rounds() -> None:
    assert parse_drop_lines(DOMAIN_LINES) == {
        "摩拉": 1800,
        "大英雄的经验": 5,
        "精锻用魔矿": 3,
    }


def test_parse_merges_across_sources() -> None:
    """跨来源（秘境 + 首领）按物品合并 —— 通知表格就是「物品 + 数量」两列。"""
    assert parse_drop_lines(DOMAIN_LINES + BOSS_LINES) == {
        "摩拉": 2400,
        "大英雄的经验": 5,
        "精锻用魔矿": 3,
        "冒险家的经验": 2,
    }


def test_parse_ignores_empty_and_unrelated_lines() -> None:
    assert parse_drop_lines(EMPTY_LINES) == {}
    assert parse_drop_lines([]) == {}
    assert parse_drop_lines(["自动秘境：点击 「单人挑战」"]) == {}


def test_parse_supports_fullwidth_and_uppercase_markers() -> None:
    assert parse_drop_lines(["自动秘境：本轮奖励识别结果 摩拉 ×100, 甜甜花 X2"]) == {
        "摩拉": 100,
        "甜甜花": 2,
    }


def test_format_is_item_then_count_sorted_by_count() -> None:
    text = format_drop_statistics({"摩拉": 1800, "精锻用魔矿": 3})
    assert text.splitlines() == ["【掉落统计】", "摩拉: 1800", "精锻用魔矿: 3"]
    assert format_drop_statistics({}) == ""
    assert format_drop_statistics(None) == ""


def test_parse_strips_wrapping_quotes_from_first_item() -> None:
    """明细段两侧的引号不能污染首条物品名（曾解析出 `"好感经验` 这种键）。"""
    assert parse_drop_lines(
        ['自动秘境：本轮奖励识别结果 "好感经验 x60, 摩拉 x10575"']
    ) == {"好感经验": 60, "摩拉": 10575}


def test_parse_merges_same_item_across_quoted_lines() -> None:
    """同一物品在首位与非首位出现时必须合并成一条（引号污染会把它拆成两个键）。"""
    lines = [
        '"自动首领讨伐"：本轮奖励识别结果 "角色经验 x200, 好感经验 x45"',
        '自动秘境：本轮奖励识别结果 "好感经验 x60, 摩拉 x10575"',
    ]
    assert parse_drop_lines(lines) == {
        "角色经验": 200,
        "好感经验": 105,
        "摩拉": 10575,
    }


def test_parse_keeps_corner_bracket_in_item_name() -> None:
    """物品名本身可能以「开头，剥包裹引号时不能把「」一并剥掉。"""
    assert parse_drop_lines(
        ['自动秘境：本轮奖励识别结果 "「久雨莲」的种子 x2, 摩拉 x100"']
    ) == {"「久雨莲」的种子": 2, "摩拉": 100}
