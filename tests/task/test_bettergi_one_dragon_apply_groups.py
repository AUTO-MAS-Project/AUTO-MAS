"""BetterGI 一条龙 apply_groups：组开关关闭时不应仍被运行时纳入。

回归测试：前端在「用户独立配置」下关闭战斗组（如自动幽境危战）开关时，
只把队列条目的 enabled 置 false，基名仍保留在 Groups 纳入；apply_groups
此前仅凭 Groups 置位判定启停，导致「界面关了、原生一条龙仍跑」。修复后
战斗 4 项需同时看 Groups 纳入与队列条目 enabled。
"""

from app.task.BetterGI.tools import one_dragon


def _enabled_by_name(result):
    out = {}
    for uid in result["TaskOrder"]:
        name = result["TaskDefinitions"][uid]
        out[name] = result["TaskEnabledList"][uid]
    return out


def _queue_with(names_with_enabled):
    return [{"name": n, "enabled": on} for n, on in names_with_enabled]


def test_combat_step_off_in_queue_but_in_groups_is_disabled():
    # 自动幽境危战 在 Groups 纳入(enabled 列表)，但队列条目 enabled=False
    result = one_dragon.apply_groups(
        config={},
        enabled=["自动幽境危战"],
        queue=_queue_with([("自动幽境危战", False)]),
    )
    assert _enabled_by_name(result)["自动幽境危战"] is False


def test_combat_step_on_in_queue_and_groups_is_enabled():
    result = one_dragon.apply_groups(
        config={},
        enabled=["自动幽境危战"],
        queue=_queue_with([("自动幽境危战", True)]),
    )
    assert _enabled_by_name(result)["自动幽境危战"] is True


def test_combat_step_not_in_groups_is_disabled_regardless_of_queue():
    # 未纳入 Groups：即便队列条目 enabled=True 也不应启用
    result = one_dragon.apply_groups(
        config={},
        enabled=[],
        queue=_queue_with([("自动幽境危战", True)]),
    )
    assert _enabled_by_name(result)["自动幽境危战"] is False


def test_non_combat_builtin_ignores_queue_enabled():
    # 非战斗内置组（领取邮件）只看 Groups 纳入，不受队列条目 enabled 影响
    result = one_dragon.apply_groups(
        config={},
        enabled=["领取邮件"],
        queue=_queue_with([("领取邮件", False)]),
    )
    assert _enabled_by_name(result)["领取邮件"] is True


def test_combat_step_missing_enabled_key_defaults_on():
    # 存量队列数据无 per-instance enabled：回退默认开启，保持原行为
    result = one_dragon.apply_groups(
        config={},
        enabled=["自动幽境危战"],
        queue=[{"name": "自动幽境危战"}],
    )
    assert _enabled_by_name(result)["自动幽境危战"] is True
