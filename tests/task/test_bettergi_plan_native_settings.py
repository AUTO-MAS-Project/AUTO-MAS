"""BetterGI：Plan 战斗步骤 settings → BGI 原生键的反向映射。

用于直控来源 + 快速配置开启时把面板值写进原生配置（一条龙文件 / 全局段）。
映射表是 one_dragon_plan.RIGHTBAR_TO_PLAN，本文件锁住它的对外行为：

- 只收白名单键；
- 只收非空值（留空必须被过滤，否则会把面板空值灌进原生配置）；
- 同名多实例按其基名归集到同一组；
- 未知组、非 dict settings、非 dict 步骤一律忽略。
"""

from app.task.BetterGI.tools.one_dragon_plan import plan_steps_to_native_settings


def test_autoboss_step_maps_to_native_keys() -> None:
    steps = [
        {
            "name": "自动首领讨伐",
            "settings": {
                "bossName": "爆炎树",
                "runCount": 1,
                "specifyRunCount": True,
                "rviveRetryCount": 3,
                "rewardRecognitionEnabled": True,
            },
        }
    ]

    assert plan_steps_to_native_settings(steps) == {
        "自动首领讨伐": {
            "AutoBossName": "爆炎树",
            "AutoBossRunCount": 1,
            "AutoBossSpecifyRunCount": True,
            "AutoBossReviveRetryCount": 3,
            "AutoBossRewardRecognitionEnabled": True,
        }
    }


def test_domain_step_maps_resin_and_name() -> None:
    steps = [
        {
            "name": "自动秘境",
            "settings": {
                "specifyResinUse": True,
                "condensedResinUseCount": 2,
                "domainName": "逆悬的冰河",
                "sundaySelectedValue": "0",
            },
        }
    ]

    out = plan_steps_to_native_settings(steps)["自动秘境"]

    assert out["specifyResinUse"] is True
    assert out["condensedResinUseCount"] == 2
    assert out["DomainName"] == "逆悬的冰河"
    # 每日行的奖励档位走 SundayEverySelectedValue（每周表默认行是另一个键，不在此表内）
    assert out["SundayEverySelectedValue"] == "0"


def test_leyline_step_maps_country_and_count() -> None:
    steps = [{"name": "自动地脉花", "settings": {"count": 1, "country": "蒙德"}}]

    assert plan_steps_to_native_settings(steps) == {
        "自动地脉花": {"LeyLineRunCount": 1, "country": "蒙德"}
    }


def test_stygian_step_maps_panel_keys() -> None:
    steps = [
        {"name": "自动幽境危战", "settings": {"bossNum": 1, "fightTeamName": "首发"}}
    ]

    assert plan_steps_to_native_settings(steps) == {
        "自动幽境危战": {"bossNum": 1, "fightTeamName": "首发"}
    }


def test_empty_values_are_skipped() -> None:
    steps = [
        {
            "name": "自动首领讨伐",
            "settings": {"bossName": "", "teamName": None, "runCount": 1},
        }
    ]

    assert plan_steps_to_native_settings(steps) == {
        "自动首领讨伐": {"AutoBossRunCount": 1}
    }


def test_keys_outside_whitelist_are_dropped() -> None:
    steps = [
        {
            "name": "自动秘境",
            "settings": {"domainName": "逆悬的冰河", "weeklyDomain": {"Monday": {}}},
        }
    ]

    assert plan_steps_to_native_settings(steps) == {
        "自动秘境": {"DomainName": "逆悬的冰河"}
    }


def test_instance_suffix_step_merges_into_base_group() -> None:
    """同名多实例（自动秘境-副本A）按基名归集；原生存储是单值，故后写者胜。"""

    steps = [
        {"name": "自动秘境", "settings": {"domainName": "逆悬的冰河"}},
        {"name": "自动秘境-副本A", "settings": {"domainName": "昏识塔"}},
    ]

    assert plan_steps_to_native_settings(steps) == {
        "自动秘境": {"DomainName": "昏识塔"}
    }


def test_unknown_group_and_malformed_input_are_ignored() -> None:
    steps = [
        {"name": "领取邮件", "settings": {"anything": 1}},
        {"name": "自动秘境", "settings": "不是 dict"},
        "not-a-step",
        {"name": "自动地脉花"},
    ]

    assert plan_steps_to_native_settings(steps) == {}
    assert plan_steps_to_native_settings([]) == {}
    assert plan_steps_to_native_settings(None) == {}
