#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

"""养成计算内核的纯逻辑回归测试（golden test，零 mock、不触网）。

夹具数据为合成的小型数据集：覆盖区间需求、聚合、合成折算、选关过滤
（时间窗/星期/黑名单）、排序不变量、缺口判定与达成状态流转。
"""

from datetime import date
from pathlib import Path

from app.task.MAA.tools.cultivate.engine import (
    aggregate,
    apply_achievements,
    build_plan,
    build_requirements,
    has_material_gap,
    judge_achievements,
    recommend_stages,
    summarize_achievements,
    synthesize,
)
from app.task.MAA.tools.cultivate.providers import (
    parse_depot_payload,
    parse_oper_box_names,
    parse_oper_box_payload,
    resolve_progression,
)
from app.task.MAA.tools.cultivate.service import (
    get_certifying_chain,
    get_inventory_chain,
    get_progression_chain,
)
from app.task.MAA.tools.cultivate.types import (
    CultivateDataSet,
    DemandEntry,
    DropEntry,
    Goal,
    OperatorTarget,
    Progression,
    ProgressionSnapshot,
    ProviderContext,
    Recipe,
    Requirement,
    StageMeta,
)
from app.task.MAA.tools.cultivate.yituliu import stage_candidates

# 2026-01-05 是周一：夹具中 PR-B-1（仅周一批次）开放、CA-5（周一不开）关闭
TODAY = date(2026, 1, 5)


def build_dataset() -> CultivateDataSet:
    """合成夹具数据集：两种可刷材料、一条合成链、一个不可获取凭证。"""

    return CultivateDataSet(
        demands={
            "char_1": (
                DemandEntry("elite", "", 1, {"30012": 5}),
                DemandEntry("elite", "", 2, {"30115": 1, "30013": 3}),
                DemandEntry("mastery", "skill_1", 1, {"3301": 4}),
                DemandEntry("mastery", "skill_1", 2, {"3302": 8, "30013": 4}),
            ),
            "char_2": (
                DemandEntry("module", "mod_1", 1, {"30012": 10, "mod_unlock_token": 2}),
            ),
        },
        drops=(
            DropEntry("st_main", "30012", 0.5, 0, None),
            DropEntry("st_alt", "30013", 0.2, 0, None),
            DropEntry("st_act", "30013", 2.0, 0, 1600000000000),  # 已过期活动窗
            DropEntry("st_chip", "3251", 0.7882, 0, None),
            DropEntry("st_ca", "3301", 0.25, 0, None),
            DropEntry("st_main", "3302", 0.5, 0, None),
        ),
        stages={
            "st_main": StageMeta("st_main", "1-7", 6, None, composite=0.5833),
            "st_alt": StageMeta("st_alt", "S-4", 15, None, composite=0.5),
            "st_chip": StageMeta("st_chip", "PR-B-1", 18, (0,), composite=0.7444),
            "st_ca": StageMeta("st_ca", "CA-5", 30, (1, 2, 4, 6), composite=0.0167),
            "st_act": StageMeta("st_act", "AC-2", 15, None, composite=3.3333),
        },
        recipes=(
            Recipe("30115", {"30013": 5}),
            Recipe("30013", {"30012": 5}),
        ),
        material_class={
            "30012": "farmable",
            "30013": "farmable",
            "3251": "farmable",
            "3301": "farmable",
            "3302": "farmable",
            "30115": "synthesizable",
            "mod_unlock_token": "unobtainable",
        },
        item_value={
            "30012": 5.0,
            "30013": 25.0,
            "3301": 2.0,
            "3302": 2.0,
            "3251": 17.0,
            "30115": 120.0,
            "mod_unlock_token": 100.0,
        },
        data_version="test",
    )


def build_targets() -> list[OperatorTarget]:
    return [
        OperatorTarget(
            "char_1",
            (
                Goal("elite", "", 2, "in_progress"),
                Goal("mastery", "skill_1", 2, "not_started"),
            ),
        ),
        OperatorTarget(
            "char_2",
            (Goal("module", "mod_1", 1, "not_started"),),
        ),
    ]


def build_snapshots() -> dict[str, ProgressionSnapshot]:
    return {
        "char_1": ProgressionSnapshot(
            source="local",
            timestamp=1000,
            data=Progression(elite=1, level=60, masteries={}, modules={}),
        ),
        # char_2 故意缺席：干员未拥有，走 default 全量起算
    }


def test_build_requirements_respects_interval_and_progression() -> None:
    """区间需求：精一消耗在 current=1 时不重复计入；未拥有干员全量起算。"""

    requirements = {
        requirement.item_id: requirement
        for requirement in build_requirements(
            build_targets(), build_snapshots(), build_dataset().demands
        )
    }
    assert requirements["30115"].amount == 1
    assert requirements["30013"].amount == 3 + 4  # 精二 3 + 专精二档 4
    assert requirements["3301"].amount == 4
    assert requirements["3302"].amount == 8
    assert requirements["30012"].amount == 10  # char_2 未拥有，精0/专0 全量
    assert requirements["mod_unlock_token"].amount == 2


def test_aggregate_sums_sources() -> None:
    requirements = build_requirements(
        build_targets(), build_snapshots(), build_dataset().demands
    )
    merged = {
        requirement.item_id: requirement for requirement in aggregate(requirements)
    }
    assert merged["30013"].amount == 7
    assert len(merged["30013"].sources) == 2


def test_synthesize_expands_synthesizable_and_separates_unobtainable() -> None:
    """单件口径成本：固源岩组合成(60 = 5×固源岩 12) 低于直刷(75 = 15/0.2) → 折算为刷固源岩。"""

    data = build_dataset()
    requirements = aggregate(
        build_requirements(build_targets(), build_snapshots(), data.demands)
    )
    farm, unobtainable = synthesize(requirements, data, TODAY)

    farm_amounts = {requirement.item_id: requirement.amount for requirement in farm}
    # 30013(×7) 与 30115(×1 → 30013×5 → 30013 组内含精二与专精两路来源)
    # 全部折叠为 30012：10(模组) + 5×7(30013 折算) + 25(30115 折算) = 70
    assert farm_amounts == {"30012": 70, "3301": 4, "3302": 8}
    assert "30013" not in farm_amounts
    assert "30115" not in farm_amounts
    assert {requirement.item_id for requirement in unobtainable} == {"mod_unlock_token"}


def test_synthesize_falls_back_to_craft_when_direct_closed_today() -> None:
    """直刷关当天不开放 → 自动折算到合成路径（大量蓝土场景）。

    复刻真实场景：固源岩组的直刷候选全是已过期限时节/复刻关（见
    §5.2 实测），今天唯一可行路径是刷固源岩×5 合成。
    """

    from dataclasses import replace

    data = build_dataset()
    # 把固源岩组的直刷关改成今天（周一）不开放的 CA-5
    drops = tuple(
        DropEntry("st_ca", "30013", 2.0, 0, None) if drop.stage_id == "st_alt" else drop
        for drop in data.drops
    )
    data = replace(data, drops=drops)

    farm, unobtainable = synthesize([Requirement("30013", 10000, ())], data, TODAY)
    amounts = {requirement.item_id: requirement.amount for requirement in farm}
    # 直刷 RI/S 复刻系候选全关 → 折算为刷固源岩 10000×5 = 50000 后合成
    assert amounts == {"30012": 50000}
    assert unobtainable == []


def test_synthesize_direct_cost_ignores_byproduct_value() -> None:
    """口径统一（单件）：直刷可行性不吃副产品红利（固源岩组案例回归）。

    st_rich 副产品豪华：综合效率口径按价值抵扣后直刷"等效"仅
    25 ÷ 1.1905 = 21 理智，会误判直刷。单件口径只看目标材料自身，
    最优直刷候选是 S-4 的 15/0.2 = 75 理智/个 > 合成 5×12 = 60 →
    折算为刷固源岩；旧口径下 21 < 60 会保直刷，断言必失败。
    """

    from dataclasses import replace

    data = build_dataset()
    drops = data.drops + (
        DropEntry("st_rich", "30013", 1.0, 0, None),
        DropEntry("st_rich", "mod_unlock_token", 1.0, 0, None),
    )
    stages = dict(data.stages)
    stages["st_rich"] = StageMeta("st_rich", "RICH-9", 105, None, composite=1.1905)
    data = replace(data, drops=drops, stages=stages)

    farm, unobtainable = synthesize([Requirement("30013", 4, ())], data, TODAY)
    amounts = {requirement.item_id: requirement.amount for requirement in farm}
    # 单件口径：最优直刷 75（S-4）> 合成 60 → 折算为刷固源岩 20；
    # st_rich 的 105 只是其中一名候选，若按综合效率口径 21 < 60 会保直刷
    assert amounts == {"30012": 20}
    assert unobtainable == []


def test_recommend_stages_filters_window_and_weekday() -> None:
    data = build_dataset()
    requirements = aggregate(
        build_requirements(build_targets(), build_snapshots(), data.demands)
    )
    farm, _ = synthesize(requirements, data, TODAY)
    entries = {entry.item_id: entry for entry in recommend_stages(farm, data, TODAY)}
    assert entries["30012"].stage_code == "1-7"
    assert entries["30012"].amount == 70
    assert entries["3302"].stage_code == "1-7"
    # CA-5 周一不开放：3301 无可用候选 → 不产条目
    assert "3301" not in entries


def test_build_plan_sorting_invariant() -> None:
    """排序不变量：精英化来源条目最前，其余按用户目标顺序。"""

    plan = build_plan(
        targets=build_targets(),
        snapshots=build_snapshots(),
        data=build_dataset(),
        today=TODAY,
    )
    entry_items = [entry.item_id for entry in plan.entries]
    # 30013/30115 折算为固源岩后与模组需求合并（精英来源排最前）
    assert entry_items == ["30012", "3302"]  # 3301 周一无可刷关
    # demands 保留全部折算后需求 + 不可获取类
    demand_items = [requirement.item_id for requirement in plan.demands]
    assert "3301" in demand_items
    assert plan.unobtainable[0].item_id == "mod_unlock_token"


def test_has_material_gap() -> None:
    data = build_dataset()
    targets = build_targets()
    snapshots = build_snapshots()
    assert has_material_gap(targets, snapshots, {}, data, TODAY)
    full_stock = {"30012": 70, "3302": 8}
    assert not has_material_gap(targets, snapshots, full_stock, data, TODAY)


def test_has_material_gap_respects_higher_tier_stock() -> None:
    """已持有的高阶材料能抵扣目标，材料备齐不再误报缺口（评论 2 回归）。

    回归：旧口径把高阶需求折算成原料后只比原料库存，用户手里已备齐的
    30115/30013 完全不参与抵扣，"材料全齐仍判缺口、库存保持被反复触发"。
    """

    data = build_dataset()
    # char_1 已精一：需求只有精二档 30115×1 + 30013×3
    targets = [OperatorTarget("char_1", (Goal("elite", "", 2, "in_progress"),))]
    snapshots = build_snapshots()
    assert not has_material_gap(
        targets, snapshots, {"30115": 1, "30013": 3}, data, TODAY
    )
    # 原料库存沿合成链恰好够：30115←30013×5←30012×25、30013×3←30012×15
    assert not has_material_gap(targets, snapshots, {"30012": 40}, data, TODAY)
    # 差一个就不够：必须刷 → 有缺口
    assert has_material_gap(targets, snapshots, {"30012": 39}, data, TODAY)


def test_has_material_gap_does_not_double_count_shared_stock() -> None:
    """多需求争用同一份库存时不重复抵扣（守住递归消耗口径）。

    需求 30013×10 与 30115×2（合成需 30013×10）、库存 30013×10：够其一
    不够其二，必有缺口。"先抵扣再折算再比库存"会把这份库存算两遍而
    漏判，递归消耗则在第一份需求扣完后按剩余库存判定。
    """

    from dataclasses import replace

    data = replace(
        build_dataset(),
        demands={
            "char_1": (
                DemandEntry("elite", "", 1, {"30013": 10}),
                DemandEntry("elite", "", 2, {"30115": 2}),
            ),
        },
    )
    targets = [OperatorTarget("char_1", (Goal("elite", "", 2, "in_progress"),))]
    snapshots = {"char_1": ProgressionSnapshot("local", 1, Progression(0, 1, {}, {}))}
    assert has_material_gap(targets, snapshots, {"30013": 10}, data, TODAY)
    # 30013×20 恰好两份需求都够（10 直用 + 30115×2 合成）→ 无缺口。
    # 旧口径把全部需求折到 30012 再比库存（本库存在 30013 上）必误报；
    # "先抵扣再折算再比库存"也会把折算目标错比原料库存而误报。
    assert not has_material_gap(targets, snapshots, {"30013": 20}, data, TODAY)


def test_apply_achievements_gap_refresh_respects_stock() -> None:
    """缺口刷新按库存抵扣：材料备齐的目标回到 not_started 而非反复刷取。"""

    data = build_dataset()
    targets = [OperatorTarget("char_1", (Goal("elite", "", 2, "in_progress"),))]
    snapshots = build_snapshots()  # char_1 已精一：需求 30115×1 + 30013×3
    refreshed = apply_achievements(
        targets, [], snapshots, {"30115": 1, "30013": 3}, data, TODAY
    )
    assert refreshed[0].goals[0].state == "not_started"
    refreshed = apply_achievements(targets, [], snapshots, {}, data, TODAY)
    assert refreshed[0].goals[0].state == "in_progress"


def test_judge_and_apply_achievements() -> None:
    targets = [
        OperatorTarget("char_1", (Goal("elite", "", 2, "in_progress"),)),
        OperatorTarget(
            "char_3", (Goal("elite", "", 1, "in_progress"),)
        ),  # 已精一：达成且可自证 → 移除
        OperatorTarget(
            "char_4", (Goal("mastery", "skill_1", 1, "in_progress"),)
        ),  # 手填来源：达成但不可自证 → pending_confirm
    ]
    snapshots = {
        "char_1": ProgressionSnapshot(
            "local", 1, Progression(elite=1, level=1, masteries={}, modules={})
        ),
        "char_3": ProgressionSnapshot(
            "local", 1, Progression(elite=1, level=1, masteries={}, modules={})
        ),
        "char_4": ProgressionSnapshot(
            "manual",
            0,
            Progression(elite=0, level=1, masteries={"skill_1": 1}, modules={}),
        ),
    }
    achievements = judge_achievements(targets, snapshots)
    by_key = {
        (achievement.operator_id, achievement.goal_index): achievement
        for achievement in achievements
    }
    assert by_key[("char_1", 0)].achieved is False
    assert by_key[("char_3", 0)].achieved and by_key[("char_3", 0)].confident
    assert by_key[("char_4", 0)].achieved and not by_key[("char_4", 0)].confident

    new_targets = {
        target.operator_id: target
        for target in apply_achievements(targets, achievements)
    }
    assert "char_3" not in new_targets  # 达成且可自证 → 移除
    assert new_targets["char_4"].goals[0].state == "pending_confirm"
    assert new_targets["char_1"].goals[0].state == "in_progress"


def test_summarize_achievements_only_reports_confident_removals() -> None:
    """推送文案只收"达成且可自证"的目标；名字缺失回退 char_id。"""

    targets = [
        OperatorTarget("char_1", (Goal("elite", "", 2, "in_progress"),)),
        OperatorTarget("char_3", (Goal("elite", "", 1, "in_progress"),)),
        OperatorTarget("char_4", (Goal("mastery", "skill_1", 1, "in_progress"),)),
    ]
    snapshots = {
        "char_3": ProgressionSnapshot(
            "local", 1, Progression(elite=1, level=1, masteries={}, modules={})
        ),
        "char_4": ProgressionSnapshot(
            "manual",
            0,
            Progression(elite=0, level=1, masteries={"skill_1": 1}, modules={}),
        ),
    }
    achievements = judge_achievements(targets, snapshots)

    assert summarize_achievements(targets, achievements, {"char_3": "名字三"}) == [
        "名字三 已达到精1"
    ]
    # 名字映射缺失：回退 char_id，不抛错
    assert summarize_achievements(targets, achievements) == ["char_3 已达到精1"]
    # 无任何达成：空文案
    assert summarize_achievements(targets, [], {"char_3": "名字三"}) == []


def test_parse_oper_box_names_reads_display_names() -> None:
    """名字映射只收有名字的干员；无 own_opers 的载荷返回空映射。"""

    payload = {
        "own_opers": [
            {"id": "char_1", "name": "小满", "elite": 0},
            {"id": "char_2", "elite": 2},  # 无名字字段：跳过
            {"id": "char_3", "name": "", "elite": 1},  # 空名字：跳过
        ]
    }
    assert parse_oper_box_names(payload) == {"char_1": "小满"}
    assert parse_oper_box_names({}) == {}


def test_parse_recipes_dual_shape() -> None:
    """双形态 schema：resolve=true 分解向逆向建边；resolve=false 合成向直读。"""

    from app.task.MAA.tools.cultivate.yituliu import parse_recipes

    raw = [
        {  # T2 分解向：1×固源岩组 分解得 5×固源岩 → 合成边 30013←{30012: 5}
            "itemId": "30012",
            "itemName": "固源岩",
            "resolve": True,
            "pathway": [{"itemId": "30013", "itemName": "固源岩组", "count": 5}],
        },
        {  # T5 合成向：三原料合成 1×聚合剂
            "itemId": "30115",
            "itemName": "聚合剂",
            "resolve": False,
            "pathway": [
                {"itemId": "30014", "count": 1},
                {"itemId": "30044", "count": 1},
                {"itemId": "30054", "count": 1},
            ],
        },
        {  # 坏条目：pathway 非列表，整体跳过
            "itemId": "bad",
            "resolve": False,
            "pathway": "x",
        },
    ]
    recipes = {recipe.result_item_id: recipe for recipe in parse_recipes(raw)}
    assert recipes["30013"].ingredients == {"30012": 5}
    assert recipes["30115"].ingredients == {"30014": 1, "30044": 1, "30054": 1}
    assert "bad" not in recipes


def test_parse_oper_box_and_depot_payload() -> None:
    progressions = parse_oper_box_payload(
        {
            "done": True,
            "own_opers": [
                {"id": "char_1", "elite": 2, "level": 90},
                {"id": "char_2", "elite": 0, "level": 1},
                "bad-entry",
            ],
        }
    )
    assert progressions["char_1"].elite == 2
    assert progressions["char_1"].masteries == {}
    inventory, sync_time = parse_depot_payload(
        {"done": True, "data": {"30012": 12, "bad": "x"}, "syncTime": "1780000000"}
    )
    assert inventory == {"30012": 12}
    assert sync_time == 1780000000


def test_local_inventory_empty_file_is_valid_stock(tmp_path) -> None:
    """合法但为空的 DepotData 返回空库存，不误报为数据缺失。

    上游据此区分"仓库确实没有"与"还没识别过"：前者显示全零库存，
    后者才提示用户去 MAA 执行仓库识别。
    """

    from app.task.MAA.tools.cultivate.providers import resolve_inventory

    (tmp_path / "DepotData.json").write_text(
        '{"done": true, "data": {}, "syncTime": 1780000000}', encoding="utf-8"
    )
    result = resolve_inventory(
        ProviderContext(maa_data_dir=tmp_path), get_inventory_chain()
    )
    assert result == ({}, 1780000000)


def test_local_inventory_missing_file_is_absent(tmp_path) -> None:
    """文件缺失仍返回 None：数据缺失语义不受空库存修复影响。"""

    from app.task.MAA.tools.cultivate.providers import resolve_inventory

    assert (
        resolve_inventory(ProviderContext(maa_data_dir=tmp_path), get_inventory_chain())
        is None
    )


def test_resolve_progression_falls_back_to_default(tmp_path) -> None:
    context = ProviderContext(maa_data_dir=tmp_path)
    # 链由调用方注入（DIP）：执行器不感知池内容
    snapshot = resolve_progression("char_missing", get_progression_chain(), context)
    assert snapshot.source == "default"
    assert snapshot.data.elite == 0


def test_certifying_chain_excludes_manual() -> None:
    names = {provider.name for provider in get_certifying_chain()}
    assert "manual" not in names
    assert "default" not in names
    assert {provider.name for provider in get_progression_chain()} >= {
        "local",
        "manual",
        "default",
    }


def test_stage_candidates_dedupes_same_stage_code() -> None:
    """同关名多组掉落统计只保留综合效率最高的一条（选择器不出现同关两项）。

    复刻真实数据：14-20、14-9 各有两组统计（不同 stage_id 同 stage_code）。
    """

    from dataclasses import replace

    from app.task.MAA.tools.cultivate.yituliu import stage_candidates

    data = build_dataset()
    # 为 30012 追加一个与 st_main（1-7，6 理智/期望 0.5 = 12 理智每件）同关名
    # 但单件理智更贵的重复关（期望同为 0.5 时 apCost 更大 → 更贵）
    drops = tuple(data.drops) + (DropEntry("st_main_dup", "30012", 0.25, 0, None),)
    stages = dict(data.stages)
    stages["st_main_dup"] = StageMeta("st_main_dup", "1-7", 6, None, composite=0.2)
    data = replace(data, drops=drops, stages=stages)

    options = stage_candidates(data).get("30012", [])
    stages_seen = [option["stage"] for option in options]
    assert len(stages_seen) == len(set(stages_seen)), "同关名残留重复项"
    # 保留的是单件理智更便宜那条
    for option in options:
        if option["stage"] == "1-7":
            assert option["expectedPerRun"] == 0.5


def test_stage_candidates_filters_expired_window() -> None:
    """now_ms 提供时过滤时间窗已结束的活动关。"""

    from app.task.MAA.tools.cultivate.yituliu import stage_candidates

    data = build_dataset()
    # st_act（AC-2，end_ms=1600000000000 已过期）在提供 now_ms 时被剔除
    closed = stage_candidates(data, now_ms=1700000000000).get("30013", [])
    assert "AC-2" not in {option["stage"] for option in closed}
    # 不提供 now_ms 时保留全部（仅结构过滤）
    all_options = stage_candidates(data).get("30013", [])
    assert "AC-2" in {option["stage"] for option in all_options}


def test_stage_candidates_sorted_by_sanity_per_item_asc() -> None:
    """候选按单件期望理智升序，首项即最优关（自动填关依赖此不变量）。"""

    from app.task.MAA.tools.cultivate.yituliu import stage_candidates

    options = stage_candidates(build_dataset()).get("30013", [])
    costs = [option["sanityPerItem"] for option in options]
    assert costs == sorted(costs), "应按单件期望理智升序"


def test_recommend_stages_prefers_sanity_per_item() -> None:
    """选关判据是单件期望理智：期望高但理智更高的关不该胜出。

    复刻真实数据：固源岩 S2-12（15 理智/2.29 期望 = 6.55 理智每件）劣于
    1-7（6 理智/1.245 期望 = 4.82 理智每件），旧判据（每次期望）会错选 S2-12。
    """

    from dataclasses import replace

    data = build_dataset()
    # 给 30012 加一个"每次期望更高但单件理智更贵"的关
    drops = tuple(data.drops) + (DropEntry("st_big", "30012", 2.0, 0, None),)
    stages = dict(data.stages)
    stages["st_big"] = StageMeta("st_big", "S2-12", 30, None, composite=0.5)
    data = replace(data, drops=drops, stages=stages)

    entries = recommend_stages([Requirement("30012", 100, ())], data, TODAY)
    # st_main(1-7): 6/0.5=12 理智每件 < st_big(S2-12): 30/2.0=15 理智每件
    assert entries[0].stage_code == "1-7"


def test_stage_candidates_sorted_by_sanity_per_item() -> None:
    """下拉排序与选关同判据（单件期望理智升序），非综合效率。

    复刻真实反例：14-20 综合效率远高于 1-7，但刷固源岩的单件理智更贵，
    不应排在前面（首项即自动填关结果）。
    """

    from dataclasses import replace

    from app.task.MAA.tools.cultivate.yituliu import stage_candidates

    data = build_dataset()
    # st_fancy：综合效率极高（副产物值钱）但固源岩单件理智贵于 1-7
    drops = tuple(data.drops) + (DropEntry("st_fancy", "30012", 0.5, 0, None),)
    stages = dict(data.stages)
    stages["st_fancy"] = StageMeta("st_fancy", "14-20", 24, None, composite=1.945)
    data = replace(data, drops=drops, stages=stages)

    options = stage_candidates(data).get("30012", [])
    assert options[0]["stage"] == "1-7", "综合效率高的关不应排在单件理智更低的关之前"
    costs = [option["sanityPerItem"] for option in options]
    assert costs == sorted(costs), "应按单件期望理智升序"


def test_dataset_json_roundtrip_preserves_item_value() -> None:
    """快照往返必须保留 item_value（缺失会让合成折算整体失效）。"""

    from app.task.MAA.tools.cultivate.yituliu import dataset_from_json, dataset_to_json

    data = build_dataset()
    restored = dataset_from_json(dataset_to_json(data))
    assert restored.item_value == data.item_value
    assert restored.item_value.get("30012") == 5.0


def test_service_accepts_injected_dataset_loader() -> None:
    """组合根可注入数据源：换实现不改内核/适配器（DIP 核心价值）。"""

    import asyncio

    from app.task.MAA.tools.cultivate.service import DepotCultivateService

    data = build_dataset()
    calls: list[tuple] = []

    async def fake_loader(config_path, proxy):
        calls.append((config_path, proxy))
        return data

    service = DepotCultivateService(dataset_loader=fake_loader)
    options = asyncio.run(
        service.stage_candidates(config_path=Path("."), item_id="30013", now_ms=1)
    )
    assert calls and calls[0][0] == Path(".")
    # 复用内核 stage_candidates 的排序与形状（与生产路径同一实现）
    assert [option["value"] for option in options] == [
        option["stage"] for option in stage_candidates(data, now_ms=1).get("30013", [])
    ]


def test_service_inventory_uses_injected_chain() -> None:
    """库存链可注入：替换后调用方拿到的就是替身数据。"""

    import asyncio

    from app.task.MAA.tools.cultivate.service import DepotCultivateService

    class StubInventoryProvider:
        name = "stub"

        def fetch(self, context):
            return {"30012": 42}, 1780000000

    service = DepotCultivateService(inventory_chain=(StubInventoryProvider(),))
    inventory = asyncio.run(service.inventory(maa_data_dir=Path(".")))
    assert inventory == {"30012": 42}


def test_composition_root_lives_in_service_not_providers() -> None:
    """组合根归属：池定义在 service，providers 只留适配器与执行器。"""

    from app.task.MAA.tools.cultivate import providers, service

    assert hasattr(service, "PROGRESSION_POOL")
    assert hasattr(service, "INVENTORY_POOL")
    # providers 不再暴露池与链选择（换实现不改适配器文件）
    assert not hasattr(providers, "PROGRESSION_POOL")
    assert not hasattr(providers, "get_progression_chain")
    # 执行器仍在 providers，且签名要求调用方显式传链
    import inspect

    sig = inspect.signature(providers.resolve_inventory)
    assert "chain" in sig.parameters


def test_fixed_source_stages_give_candidates_without_drop_data() -> None:
    """资源关固定产出：无掉落统计数据也能给出唯一候选（采购凭证 ← AP-5）。

    取货运「固定产出不计入概率掉落统计」，一图流矩阵与 MAA stages.json 都
    没有采购凭证条目，靠 fixed_source_stages 映射补齐。
    """

    from dataclasses import replace

    from app.task.MAA.tools.cultivate.yituliu import stage_candidates

    data = replace(
        build_dataset(),
        fixed_source_stages={"4006": "st_ca"},  # 借 st_ca(CA-5) 当固定产出关
        material_class={"4006": "farmable"},
    )
    options = stage_candidates(data).get("4006", [])
    assert [option["stage"] for option in options] == ["CA-5"]
    assert options[0]["fixed"] is True
    assert options[0]["sanityPerItem"] is None  # 固定产出无单件理智


def test_fixed_source_stage_yields_farm_entry() -> None:
    """固定产出材料进 recommend_stages，关卡码正确且期望值为中性 0。"""

    from dataclasses import replace

    # 借 st_chip(PR-B-1，周一开放) 当固定产出关：TODAY 是周一
    data = replace(build_dataset(), fixed_source_stages={"4006": "st_chip"})
    entries = recommend_stages([Requirement("4006", 100, ())], data, TODAY)
    assert [(entry.item_id, entry.stage_code) for entry in entries] == [
        ("4006", "PR-B-1")
    ]
    # 产出恒定但单次产量未知：不臆造期望值
    assert entries[0].expected_runs == 0.0
    assert entries[0].expected_sanity == 0.0


def test_fixed_source_stage_ignores_weekday_filter() -> None:
    """固定产出关不做星期过滤：非开放日也要给关卡，开放时间由 MAA 判断。

    CA-5 开放日 (1,2,4,6) 不含周一，但 TODAY 是周一仍须产出条目——否则
    用户在不开放的日子就选不了该材料。
    """

    from dataclasses import replace

    data = replace(build_dataset(), fixed_source_stages={"4006": "st_ca"})
    entries = recommend_stages([Requirement("4006", 100, ())], data, TODAY)
    assert [(entry.item_id, entry.stage_code) for entry in entries] == [
        ("4006", "CA-5")
    ]


def test_stage_candidates_expose_fixed_source_regardless_of_weekday() -> None:
    """编辑器候选同口径：固定产出关不受星期限制（候选随时可选）。"""

    from dataclasses import replace

    from app.task.MAA.tools.cultivate.yituliu import stage_candidates

    data = replace(build_dataset(), fixed_source_stages={"4006": "st_ca"})
    options = stage_candidates(data).get("4006", [])
    assert [option["stage"] for option in options] == ["CA-5"]


def test_fixed_source_stage_preserves_snapshot_roundtrip() -> None:
    """快照往返保留 fixed_source_stages（防重演 item_value 丢失）。"""

    from dataclasses import replace

    from app.task.MAA.tools.cultivate.yituliu import dataset_from_json, dataset_to_json

    data = replace(build_dataset(), fixed_source_stages={"4006": "st_chip"})
    restored = dataset_from_json(dataset_to_json(data))
    assert restored.fixed_source_stages == {"4006": "st_chip"}


def test_fixed_source_items_farmable_in_full_pipeline() -> None:
    """龙门币/采购凭证等固定产出材料经完整管线产出资源关条目。

    回归：synthesize 曾只认掉落统计与配方，固定产出材料在折算阶段就被
    归入"不可获取"（真实需求数据里龙门币出现在全部模组档位，单个模组
    三级就要 15 万），recommend_stages 的 fixed_source_stages 兜底因此
    永远执行不到。资源关产出只按资源关处理，不参与掉落与合成折算。
    """

    from dataclasses import replace

    data = replace(
        build_dataset(),
        demands={
            "char_1": (DemandEntry("module", "mod_1", 1, {"4001": 40000, "4006": 2}),),
        },
        material_class={"4001": "farmable", "4006": "farmable"},
        fixed_source_stages={"4001": "st_main", "4006": "st_chip"},
    )
    targets = [OperatorTarget("char_1", (Goal("module", "mod_1", 1, "not_started"),))]
    snapshots = {"char_1": ProgressionSnapshot("local", 1, Progression(0, 1, {}, {}))}
    plan = build_plan(targets=targets, snapshots=snapshots, data=data, today=TODAY)

    entries = {(entry.item_id, entry.stage_code) for entry in plan.entries}
    assert ("4001", "1-7") in entries
    assert ("4006", "PR-B-1") in entries
    assert all(
        unobtainable.item_id not in ("4001", "4006")
        for unobtainable in plan.unobtainable
    )


def test_fixed_source_item_without_item_value_still_farmable() -> None:
    """固定产出材料缺物品价值数据时仍按资源关处理。

    路由只依赖 fixed_source_stages 映射，不依赖掉落统计或物品价值——
    价值缺失不能把材料打回"不可获取"。
    """

    from dataclasses import replace

    data = replace(
        build_dataset(),
        material_class={"4006": "farmable"},
        fixed_source_stages={"4006": "st_chip"},
    )
    farm, unobtainable = synthesize([Requirement("4006", 6, ())], data, TODAY)
    assert [(requirement.item_id, requirement.amount) for requirement in farm] == [
        ("4006", 6)
    ]
    assert unobtainable == []


def test_fixed_source_stage_blacklisted_counts_unobtainable() -> None:
    """固定产出关被黑名单排除时材料归入不可获取（没有其他获取途径）。"""

    from dataclasses import replace

    data = replace(
        build_dataset(),
        material_class={"4006": "farmable"},
        fixed_source_stages={"4006": "st_chip"},
    )
    farm, unobtainable = synthesize(
        [Requirement("4006", 6, ())], data, TODAY, frozenset({"PR-B-1"})
    )
    assert farm == []
    assert [
        (requirement.item_id, requirement.amount) for requirement in unobtainable
    ] == [("4006", 6)]


def test_stage_candidates_truncates_to_limit() -> None:
    """候选按单件理智升序截断（默认 10）：首项（自动填关）不受影响，None 取全量。"""

    from dataclasses import replace

    data = build_dataset()
    # 给 30012 追加 12 个不同关卡的候选：期望同为 0.5，apCost 递增 → 单件理智递增
    drops = list(data.drops)
    stages = dict(data.stages)
    for index in range(12):
        drops.append(DropEntry(f"st_x{index}", "30012", 0.5, 0, None))
        stages[f"st_x{index}"] = StageMeta(
            f"st_x{index}", f"X-{index}", 6 + index, None
        )
    data = replace(data, drops=tuple(drops), stages=stages)

    trimmed = stage_candidates(data).get("30012", [])
    assert len(trimmed) == 10
    assert trimmed[0]["stage"] == "1-7"

    full = stage_candidates(data, limit=None).get("30012", [])
    assert len(full) == 13
    assert [option["stage"] for option in trimmed] == [
        option["stage"] for option in full[:10]
    ]


def test_normalize_dataset_excludes_maa_unnavigable_stages() -> None:
    """别传常驻（stageType=ACT_PERM）不进数据集：MAA 判其为过期活动关。

    回归：一图流把已转常驻的别传当常驻关给出（end 是远期占位时间），
    MAA 的常驻关卡表不收录，库存保持/养成计划会整条跳过；当期活动关
    （ACT）与主线保留，stageType 缺失时按 stageId 的 _perm 后缀兜底。
    """

    from app.task.MAA.tools.cultivate.yituliu import normalize_dataset

    stage_raw = {
        "data": [
            {
                "stageId": "act18d0_06_perm",
                "stageCode": "WD-6",
                "apCost": 15,
                "stageType": "ACT_PERM",
            },
            {
                "stageId": "act54side_08",
                "stageCode": "SR-8",
                "apCost": 21,
                "stageType": "ACT",
            },
            {
                "stageId": "main_01-07",
                "stageCode": "1-7",
                "apCost": 6,
                "stageType": "MAIN",
            },
            {"stageId": "legacy_01_perm", "stageCode": "LM-1", "apCost": 15},
        ]
    }
    matrix_raw = [
        {
            "stageId": stage_id,
            "itemId": "30012",
            "times": 100,
            "quantity": 50,
            "start": 1,
            "end": None,
        }
        for stage_id in (
            "act18d0_06_perm",
            "act54side_08",
            "main_01-07",
            "legacy_01_perm",
        )
    ]

    data = normalize_dataset(
        demand_raw={"char_1": {"name": "X", "rarity": 6, "elite": [{}, {"30012": 1}]}},
        matrix_raw=matrix_raw,
        stage_raw=stage_raw,
        recipe_raw=[],
        data_version="test",
    )

    assert {drop.stage_id for drop in data.drops} == {"act54side_08", "main_01-07"}


def test_dataset_from_json_drops_perm_stages_of_legacy_snapshot() -> None:
    """修复前写入的快照仍带别传常驻关：加载时按 _perm 后缀剔除。"""

    from app.task.MAA.tools.cultivate.yituliu import dataset_from_json, dataset_to_json

    payload = dataset_to_json(build_dataset())
    payload["drops"] = [
        *payload["drops"],
        {
            "stage_id": "act18d0_06_perm",
            "item_id": "30033",
            "expected_per_run": 0.465,
            "start_ms": 1,
            "end_ms": None,
        },
    ]

    data = dataset_from_json(payload)

    assert all(drop.stage_id != "act18d0_06_perm" for drop in data.drops)
