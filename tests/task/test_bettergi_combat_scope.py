from app.task.BetterGI.tools.one_dragon_plan import (
    build_combat_steps,
    plan_combat_bases,
)


def test_combat_ownership_ignores_enabled_flag() -> None:
    """全部战斗行关掉时：这次不跑（build_combat_steps 为空），但仍归执行层负责。

    归属集合非空是关键——AutoProxy 用它决定原生副本剔除谁。若按 plan_mode 门控，
    全关时原生副本不会剔除，战斗项会落回原生一条龙照跑（2026-09-12 实机排障）。
    """
    steps = [
        {"uid": "e09455ecc48d", "kind": "builtin", "name": "自动地脉花", "enabled": False},
        {"uid": "5979adf582be", "kind": "builtin", "name": "自动秘境", "enabled": False},
        {"uid": "8", "kind": "builtin", "name": "领取每日奖励", "enabled": True},
    ]
    assert plan_combat_bases(steps) == {"自动地脉花", "自动秘境"}
    assert build_combat_steps(steps, [], ["自动地脉花", "自动秘境"]) == []


def test_combat_ownership_matches_enabled_steps() -> None:
    steps = [
        {"uid": "1", "kind": "builtin", "name": "自动地脉花", "enabled": True, "settings": {}},
        {"uid": "2", "kind": "builtin", "name": "自动秘境", "enabled": False, "settings": {}},
    ]
    assert plan_combat_bases(steps) == {"自动地脉花", "自动秘境"}
    taken = build_combat_steps(steps, [], ["自动地脉花", "自动秘境"])
    assert [s["name"] for s in taken] == ["自动地脉花"]


def test_combat_ownership_supports_suffix_instances() -> None:
    steps = [
        {"uid": "1", "kind": "builtin", "name": "自动秘境-3", "enabled": True},
        {"uid": "2", "kind": "builtin", "name": "自动秘境-7", "enabled": False},
    ]
    assert plan_combat_bases(steps) == {"自动秘境"}


def test_combat_ownership_ignores_non_combat_and_broken_steps() -> None:
    steps = [
        {"uid": "1", "name": "领取尘歌壶奖励"},
        {"uid": "2", "name": "OCR读取当前抽卡资源并发送通知", "kind": "js"},
        "not-a-dict",
        {},
    ]
    assert plan_combat_bases(steps) == set()
    assert plan_combat_bases([]) == set()
