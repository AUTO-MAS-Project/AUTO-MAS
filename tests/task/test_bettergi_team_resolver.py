"""BetterGI：队伍配置表按「战斗场景」选队（L1 精确匹配 + 随机固定 + 四层优先级）。"""

from app.task.BetterGI.tools import team_resolver


class _PickLast:
    """确定性随机桩：始终选命中列表最后一项，便于断言。"""

    @staticmethod
    def choice(seq):
        return seq[-1]


def _team(name, scenes, strategy="", enabled=True):
    return {"name": name, "strategy": strategy, "scenes": scenes, "enabled": enabled}


# ── parse_teams ────────────────────────────────────────────────────────────


def test_parse_teams_tolerates_bad_payload():
    assert team_resolver.parse_teams("") == []
    assert team_resolver.parse_teams("不是 JSON") == []
    assert team_resolver.parse_teams('{"name": "甲"}') == []


def test_parse_teams_drops_blank_name_and_normalizes():
    teams = team_resolver.parse_teams(
        '[{"name": "  ", "scenes": {}}, {"name": " 甲 ", "enabled": false}]'
    )
    assert teams == [
        {
            "name": "甲",
            "strategy": "",
            "scenes": {},
            "note": "",
            "enabled": False,
        }
    ]


# ── 自动秘境：L1 精确匹配 ──────────────────────────────────────────────────


def test_domain_exact_match_only():
    teams = [
        _team("穷举队", {"domain": [{"region": "蒙德", "domain": "塞西莉亚苗圃"}]}),
        _team("别处队", {"domain": [{"region": "蒙德", "domain": "急冻树"}]}),
    ]
    settings = {"domainName": "塞西莉亚苗圃"}
    hit = team_resolver.resolve_team_for_step(teams, "自动秘境", settings, "Monday")
    assert hit == {"team": "穷举队", "strategy": ""}


def test_domain_reward_does_not_affect_matching():
    """奖励档只作界面展示：同秘境不同奖励档仍应命中。"""
    teams = [
        _team("甲", {"domain": [{"region": "蒙德", "domain": "苗圃", "reward": "1"}]})
    ]
    settings = {"domainName": "苗圃", "sundaySelectedValue": "3"}
    assert team_resolver.resolve_team_for_step(teams, "自动秘境", settings, "Monday")


def test_domain_weekly_row_beats_step_level():
    """开每周时按「今天实际执行的秘境」匹配，而非步骤级 domainName。"""
    teams = [
        _team("周一队", {"domain": [{"domain": "周一秘境"}]}),
        _team("步骤队", {"domain": [{"domain": "步骤秘境"}]}),
    ]
    settings = {
        "weeklyDomainEnabled": True,
        "weeklyDomain": {"Monday": {"domainName": "周一秘境"}},
        "domainName": "步骤秘境",
    }
    hit = team_resolver.resolve_team_for_step(teams, "自动秘境", settings, "Monday")
    assert hit == {"team": "周一队", "strategy": ""}


def test_domain_missing_target_returns_none():
    teams = [_team("甲", {"domain": [{"domain": "苗圃"}]})]
    assert team_resolver.resolve_team_for_step(teams, "自动秘境", {}, "Monday") is None


# ── 随机与多命中 ───────────────────────────────────────────────────────────


def test_multiple_hits_pick_random_stable_in_one_run():
    teams = [
        _team("甲", {"boss": [{"boss": "急冻树"}]}),
        _team("乙", {"boss": [{"boss": "急冻树"}]}),
    ]
    settings = {"bossName": "急冻树"}
    hit = team_resolver.resolve_team_for_step(
        teams, "自动首领讨伐", settings, "Monday", rng=_PickLast()
    )
    assert hit is not None and hit["team"] == "乙"
    # 同一份 teams + 同一 rng ⇒ 结果稳定（一次运行内不换队）
    again = team_resolver.resolve_team_for_step(
        teams, "自动首领讨伐", settings, "Monday", rng=_PickLast()
    )
    assert again == hit


# ── 队伍过滤规则 ───────────────────────────────────────────────────────────


def test_disabled_team_not_matched():
    teams = [_team("甲", {"boss": [{"boss": "急冻树"}]}, enabled=False)]
    assert (
        team_resolver.resolve_team_for_step(
            teams, "自动首领讨伐", {"bossName": "急冻树"}, "Monday"
        )
        is None
    )


def test_empty_scenes_is_not_a_wildcard():
    """Q15：未勾选任何场景的队伍不参与匹配（不是万能队）。"""
    teams = [_team("万能?", {})]
    assert (
        team_resolver.resolve_team_for_step(
            teams, "自动首领讨伐", {"bossName": "急冻树"}, "Monday"
        )
        is None
    )


def test_team_matched_on_other_scene_is_ignored():
    teams = [_team("甲", {"domain": [{"domain": "急冻树"}]})]
    assert (
        team_resolver.resolve_team_for_step(
            teams, "自动首领讨伐", {"bossName": "急冻树"}, "Monday"
        )
        is None
    )


def test_stygian_never_participates():
    """Q5：幽境危战暂不纳入场景选队。"""
    teams = [_team("甲", {"boss": [{"boss": "急冻树"}]})]
    settings = {"fightTeamName": "甲", "bossNum": 1}
    assert (
        team_resolver.resolve_team_for_step(teams, "自动幽境危战", settings, "Monday")
        is None
    )


# ── 自动地脉花：地区 + 类型双字段 ──────────────────────────────────────────


def test_leyline_daily_requires_country_and_type():
    teams = [
        _team("甲", {"leyline": [{"country": "蒙德", "type": "启示之花"}]}),
        _team("乙", {"leyline": [{"country": "蒙德", "type": "藏金之花"}]}),
    ]
    settings = {
        "leyLineDailyEnabled": True,
        "country": "蒙德",
        "leyLineOutcropType": "启示之花",
    }
    hit = team_resolver.resolve_team_for_step(teams, "自动地脉花", settings, "Monday")
    assert hit == {"team": "甲", "strategy": ""}


def test_leyline_weekly_row_without_run_is_skipped():
    teams = [_team("甲", {"leyline": [{"country": "璃月", "type": "藏金之花"}]})]
    settings = {
        "leyLineDailyEnabled": False,
        "weeklyLeyLine": {
            "Monday": {"run": False, "country": "璃月", "type": "藏金之花"}
        },
    }
    assert (
        team_resolver.resolve_team_for_step(teams, "自动地脉花", settings, "Monday")
        is None
    )


def test_leyline_weekly_row_falls_back_to_default():
    teams = [_team("甲", {"leyline": [{"country": "璃月", "type": "藏金之花"}]})]
    settings = {
        "leyLineDailyEnabled": False,
        "weeklyLeyLine": {
            "Monday": {"run": True},
            "default": {"country": "璃月", "type": "藏金之花"},
        },
    }
    hit = team_resolver.resolve_team_for_step(teams, "自动地脉花", settings, "Monday")
    assert hit == {"team": "甲", "strategy": ""}


def test_leyline_weekly_falls_back_to_step_level_type():
    """每周行内类型键是 ``type``，步骤级是 ``leyLineOutcropType``，两者不可混用。"""
    teams = [_team("甲", {"leyline": [{"country": "蒙德", "type": "启示之花"}]})]
    settings = {
        "leyLineDailyEnabled": False,
        "weeklyLeyLine": {"Monday": {"run": True}, "default": {"country": "蒙德"}},
        "leyLineOutcropType": "启示之花",
    }
    hit = team_resolver.resolve_team_for_step(teams, "自动地脉花", settings, "Monday")
    assert hit == {"team": "甲", "strategy": ""}


# ── apply_teams_to_steps ───────────────────────────────────────────────────


def test_apply_writes_override_and_skips_others():
    teams = [
        _team("秘境队", {"domain": [{"domain": "苗圃"}]}, strategy="策略A"),
        _team("首领队", {"boss": [{"boss": "急冻树"}]}),
    ]
    steps = [
        {"name": "自动秘境", "settings": {"domainName": "苗圃"}},
        {"name": "自动秘境-二号", "settings": {"domainName": "别处"}},
        {"name": "自动幽境危战", "settings": {"bossNum": 1}},
        {"name": "自动首领讨伐", "settings": {"bossName": "急冻树"}},
    ]
    hit = team_resolver.apply_teams_to_steps(steps, teams, day_key="Monday")
    assert hit == 2
    assert steps[0]["settings"]["masTeamOverride"] == "秘境队"
    assert steps[0]["settings"]["masStrategyOverride"] == "策略A"
    assert "masTeamOverride" not in steps[1]["settings"]
    assert "masTeamOverride" not in steps[2]["settings"]
    assert steps[3]["settings"]["masTeamOverride"] == "首领队"
    # 队伍策略留空 ⇒ 不写策略覆盖，交由下层（右栏 → 通用全局策略）决定
    assert "masStrategyOverride" not in steps[3]["settings"]


def test_apply_returns_zero_without_teams():
    steps = [{"name": "自动秘境", "settings": {"domainName": "苗圃"}}]
    assert team_resolver.apply_teams_to_steps(steps, [], day_key="Monday") == 0
