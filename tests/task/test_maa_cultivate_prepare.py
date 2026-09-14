#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

"""PR2 养成注入编排的纯逻辑回归测试：目标解析、达成拦截、计划与缺口。

数据集经 DepotCultivateService 构造参数注入（组合根注入测试面），
练度用 tmp 目录下的真实 OperBoxData.json，库存用桩 provider，不触网。
"""

import asyncio
import json
from pathlib import Path
from typing import Mapping

import pytest
from test_maa_cultivate_engine import TODAY, build_dataset

from app.task.MAA.AutoProxy import _build_cultivate_task, _build_data_update_task
from app.task.MAA.tools.cultivate.providers import (
    LocalProgressionProvider,
    resolve_progression,
)
from app.task.MAA.tools.cultivate.service import (
    DepotCultivateService,
    parse_cultivate_targets,
)
from app.task.MAA.tools.cultivate.types import (
    CultivatePlan,
    FarmEntry,
    Goal,
    ProviderContext,
)


class _StubInventoryProvider:
    """库存桩：返回固定库存映射，替代真实 DepotData 读取。"""

    name = "stub"

    def __init__(self, inventory: Mapping[str, int]):
        self._inventory = inventory

    def fetch(self, context) -> tuple[Mapping[str, int], int]:
        return self._inventory, 1000


def _service(inventory: Mapping[str, int] | None) -> DepotCultivateService:
    async def _loader(config_path, proxy):
        return build_dataset()

    return DepotCultivateService(
        dataset_loader=_loader,
        inventory_chain=(_StubInventoryProvider(inventory or {}),),
    )


def _write_oper_box(maa_dir: Path, elite: int) -> None:
    maa_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "done": True,
        "own_opers": [{"id": "char_1", "elite": elite, "level": 30}],
    }
    (maa_dir / "OperBoxData.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def test_parse_cultivate_targets_filters_invalid() -> None:
    payload = [
        {
            "operator_id": "char_1",
            "goals": [
                {"kind": "elite", "to_level": 2},  # 合法；target_id 强制为空
                {"kind": "elite", "to_level": 3},  # elite 档位上限 2
                {"kind": "mastery", "to_level": 1},  # mastery 缺 target_id
                {"kind": "mastery", "target_id": "skill_1", "to_level": 4},  # 超上限
                {"kind": "unknown", "target_id": "x", "to_level": 1},  # 非法 kind
                {
                    "kind": "module",
                    "target_id": "mod_1",
                    "to_level": 1,
                    "state": "nope",
                },  # 非法 state 回退 not_started
                {"kind": "elite", "to_level": True},  # 布尔不算整数
            ],
        },
        {"operator_id": "", "goals": [{"kind": "elite", "to_level": 1}]},  # 空干员
        {"operator_id": "char_2", "goals": []},  # 无有效目标
        "garbage",  # 非字典
    ]

    targets = parse_cultivate_targets(payload)

    assert len(targets) == 1
    assert targets[0].operator_id == "char_1"
    assert targets[0].goals == (
        Goal("elite", "", 2, "not_started"),
        Goal("module", "mod_1", 1, "not_started"),
    )


def test_parse_cultivate_targets_keeps_state_and_non_list() -> None:
    targets = parse_cultivate_targets(
        [
            {
                "operator_id": "char_1",
                "goals": [
                    {"kind": "elite", "to_level": 1, "state": "in_progress"},
                ],
            }
        ]
    )
    assert targets[0].goals[0].state == "in_progress"

    assert parse_cultivate_targets([]) == ()
    assert parse_cultivate_targets(None) == ()
    assert parse_cultivate_targets("[]") == ()


def test_prepare_keeps_unachieved_with_gap(tmp_path: Path) -> None:
    maa_dir = tmp_path / "data"
    _write_oper_box(maa_dir, elite=0)
    targets = parse_cultivate_targets(
        [{"operator_id": "char_1", "goals": [{"kind": "elite", "to_level": 2}]}]
    )

    updated, plan, gap = asyncio.run(
        _service({}).prepare_cultivate(
            targets=targets,
            maa_data_dir=maa_dir,
            config_path=tmp_path,
            today=TODAY,
        )
    )

    assert gap is True
    assert [g.state for g in updated[0].goals] == ["in_progress"]
    assert plan is not None and plan.entries


def test_prepare_removes_achieved_elite(tmp_path: Path) -> None:
    maa_dir = tmp_path / "data"
    _write_oper_box(maa_dir, elite=2)
    targets = parse_cultivate_targets(
        [{"operator_id": "char_1", "goals": [{"kind": "elite", "to_level": 2}]}]
    )

    updated, plan, gap = asyncio.run(
        _service({}).prepare_cultivate(
            targets=targets,
            maa_data_dir=maa_dir,
            config_path=tmp_path,
            today=TODAY,
        )
    )

    assert updated == []
    assert plan is None
    assert gap is False


def test_prepare_gap_false_when_inventory_covers(tmp_path: Path) -> None:
    maa_dir = tmp_path / "data"
    _write_oper_box(maa_dir, elite=0)
    targets = parse_cultivate_targets(
        [{"operator_id": "char_1", "goals": [{"kind": "elite", "to_level": 2}]}]
    )
    # 精英 1+2 全部材料（30012×5 + 30115×1 + 30013×3）备齐
    service = _service({"30012": 5, "30115": 1, "30013": 3})

    updated, plan, gap = asyncio.run(
        service.prepare_cultivate(
            targets=targets,
            maa_data_dir=maa_dir,
            config_path=tmp_path,
            today=TODAY,
        )
    )

    assert gap is False
    assert [g.state for g in updated[0].goals] == ["not_started"]
    # 净缺口语义：材料备齐即无刷取条目，MAA 侧不会被要求补刷原料；
    # demands 仍保留目标全量需求供 UI 展示
    assert plan is not None and plan.entries == ()
    assert plan.demands


def test_prepare_plan_counts_net_gap_and_task_keeps_holdings(tmp_path: Path) -> None:
    """计划数量是净缺口（跨合成链抵扣）；MAA 保有量目标 = 净缺口 + 档案现存。"""

    maa_dir = tmp_path / "data"
    _write_oper_box(maa_dir, elite=0)
    targets = parse_cultivate_targets(
        [{"operator_id": "char_1", "goals": [{"kind": "elite", "to_level": 2}]}]
    )
    # 精英 1+2 折算后需要 30012×45；已有 20 个原料
    service = _service({"30012": 20})

    updated, plan, gap = asyncio.run(
        service.prepare_cultivate(
            targets=targets,
            maa_data_dir=maa_dir,
            config_path=tmp_path,
            today=TODAY,
        )
    )

    assert gap is True
    assert [g.state for g in updated[0].goals] == ["in_progress"]
    entries = {entry.item_id: entry for entry in plan.entries}
    # 高阶材料（30115/30013）沿合成链折算到原料，再抵扣已有库存
    assert set(entries) == {"30012"}
    assert entries["30012"].amount == 25
    assert entries["30012"].held == 20

    task = _build_cultivate_task(
        plan,
        None,
        skip_during_activity=False,
        skip_during_resource_collection=False,
    )
    # MAA 现算 need = DropCount − 现存 = 25：写保有量目标而非净缺口
    assert {item["DropId"]: item["DropCount"] for item in task["PlanList"]} == {
        "30012": 45
    }


def test_prepare_net_gap_ignores_higher_tier_stock_for_plan(tmp_path: Path) -> None:
    """高阶材料都在库里、只缺原料时，计划不会把已备齐的那部分再刷一遍。"""

    maa_dir = tmp_path / "data"
    _write_oper_box(maa_dir, elite=0)
    targets = parse_cultivate_targets(
        [{"operator_id": "char_1", "goals": [{"kind": "elite", "to_level": 2}]}]
    )
    # 30013×3 与 30115×1 都在库里：真实缺口只剩 30012×5
    service = _service({"30115": 1, "30013": 3})

    _, plan, gap = asyncio.run(
        service.prepare_cultivate(
            targets=targets,
            maa_data_dir=maa_dir,
            config_path=tmp_path,
            today=TODAY,
        )
    )

    assert gap is True
    entries = {entry.item_id: entry for entry in plan.entries}
    assert entries["30012"].amount == 5
    assert entries["30012"].held == 0


def test_prepare_propagates_dataset_error(tmp_path: Path) -> None:
    async def _boom(config_path, proxy):
        raise RuntimeError("dataset down")

    service = DepotCultivateService(
        dataset_loader=_boom, inventory_chain=(_StubInventoryProvider({}),)
    )
    targets = parse_cultivate_targets(
        [{"operator_id": "char_1", "goals": [{"kind": "elite", "to_level": 2}]}]
    )

    with pytest.raises(RuntimeError):
        asyncio.run(
            service.prepare_cultivate(
                targets=targets,
                maa_data_dir=tmp_path,
                config_path=tmp_path,
                today=TODAY,
            )
        )


def _plan() -> CultivatePlan:
    return CultivatePlan(
        entries=(
            FarmEntry(item_id="30012", amount=5, stage_code="1-7"),
            FarmEntry(item_id="30013", amount=3, stage_code="S-4"),
        )
    )


def test_build_cultivate_task_maps_entries_and_hardcodes_limits() -> None:
    source = {
        "$type": "DepotMaintainTask",
        "Name": "养成计划",
        "UpdateDepot": False,
        "PlanList": [
            # 同 Stage+DropId 的旧条目：继承未知字段、覆盖托管字段
            {"Stage": "1-7", "DropId": "30012", "DropCount": 1, "Custom": "keep"},
        ],
    }

    task = _build_cultivate_task(
        _plan(),
        source,
        skip_during_activity=True,
        skip_during_resource_collection=False,
    )

    assert task is not None
    assert task["Name"] == "养成计划"
    assert task["TaskType"] == "DepotMaintain"
    assert task["UpdateDepot"] is True  # 仓库识别随养成执行，不受旧条目影响
    assert task["IsStageManually"] is True
    assert task["OnlyFirstInsufficientPlan"] is False
    assert task["UseMedicine"] is False and task["UseStone"] is False
    assert task["UseExpiringMedicine"] is False and task["UseAutoSeries"] is False
    assert task["SkipDuringActivity"] is True
    assert task["SkipDuringResourceCollection"] is False
    assert task["PlanList"] == [
        {
            "Custom": "keep",
            "UseMedicine": False,
            "MedicineCount": 0,
            "UseStone": False,
            "StoneCount": 0,
            "Stage": "1-7",
            "DropId": "30012",
            "DropCount": 5,
        },
        {
            "UseMedicine": False,
            "MedicineCount": 0,
            "UseStone": False,
            "StoneCount": 0,
            "Stage": "S-4",
            "DropId": "30013",
            "DropCount": 3,
        },
    ]


def test_build_cultivate_task_none_without_entries() -> None:
    plan = CultivatePlan(entries=())
    assert (
        _build_cultivate_task(
            plan,
            None,
            skip_during_activity=False,
            skip_during_resource_collection=False,
        )
        is None
    )


def test_build_data_update_task_forces_managed_fields() -> None:
    source = {"UpdateOperBox": False, "UpdateDepot": False, "TriggerInterval": "Daily"}

    task = _build_data_update_task(source)

    assert task["Name"] == "更新数据"
    assert task["TaskType"] == "UserDataUpdate"
    assert task["UpdateOperBox"] is True
    assert task["UpdateDepot"] is True
    assert task["TriggerInterval"] == "EveryTime"


def test_progression_reads_file_once_per_context(tmp_path: Path) -> None:
    """双链共享同一 context 时，多干员取数只读一次磁盘（file_cache）。"""
    maa_dir = tmp_path / "data"
    maa_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "done": True,
        "own_opers": [
            {"id": "char_1", "elite": 0, "level": 30},
            {"id": "char_2", "elite": 2, "level": 60},
        ],
    }
    (maa_dir / "OperBoxData.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    context = ProviderContext(maa_data_dir=maa_dir)
    local = (LocalProgressionProvider(),)

    first = resolve_progression("char_1", local, context)
    second = resolve_progression("char_2", local, context)

    assert first is not None and first.data.elite == 0
    assert second is not None and second.data.elite == 2
    # 两条链两次取数共用缓存：整轮编排只读一次文件
    assert "oper_box" in context.file_cache


def test_filter_catalog_by_elite_keeps_unknown() -> None:
    """已精 2 的干员被剔除；精 0/精 1 与练度未知（未识别/未拥有）保留。"""

    from app.task.MAA.tools.cultivate.service import filter_catalog_by_elite
    from app.task.MAA.tools.cultivate.types import Progression

    catalog = [
        {"value": "char_e2", "label": "A"},
        {"value": "char_e1", "label": "B"},
        {"value": "char_e0", "label": "C"},
        {"value": "char_unknown", "label": "D"},
    ]
    index = {
        "char_e2": Progression(elite=2, level=60, masteries={}, modules={}),
        "char_e1": Progression(elite=1, level=30, masteries={}, modules={}),
    }

    filtered = filter_catalog_by_elite(catalog, index)

    assert [item["value"] for item in filtered] == [
        "char_e1",
        "char_e0",
        "char_unknown",
    ]


def test_preview_availability_semantics(tmp_path: Path) -> None:
    """两类识别数据同口径：识别过但结果为空算"有数据"，缺失才算"未识别"。

    回归守卫：档案存在但内容为空（新号）不得报"缺少干员识别数据"
    （对齐决策 24 的"空仓库 ≠ 数据缺失"）。
    """
    targets = parse_cultivate_targets(
        [{"operator_id": "char_1", "goals": [{"kind": "elite", "to_level": 2}]}]
    )

    # 两类文件都缺失 → 都判未识别（不注入库存链，用真实默认链读目录）
    empty_dir = tmp_path / "missing"
    empty_dir.mkdir()
    missing_service = DepotCultivateService(dataset_loader=_loader_ok())
    _, availability = asyncio.run(
        missing_service.preview_cultivate(
            targets=targets, maa_data_dir=empty_dir, config_path=tmp_path, today=TODAY
        )
    )
    assert availability == {"has_progression": False, "has_inventory": False}

    # 干员档案存在但 own_opers 为空 → 仍算有数据
    present_dir = tmp_path / "present"
    present_dir.mkdir()
    (present_dir / "OperBoxData.json").write_text(
        json.dumps({"done": True, "own_opers": []}), encoding="utf-8"
    )

    async def _inventory_ok():
        return None

    service = DepotCultivateService(
        dataset_loader=_loader_ok(),
        inventory_chain=(_StubInventoryProvider({"30012": 1}),),
    )
    _, availability = asyncio.run(
        service.preview_cultivate(
            targets=targets, maa_data_dir=present_dir, config_path=tmp_path, today=TODAY
        )
    )
    assert availability["has_progression"] is True
    assert availability["has_inventory"] is True


def _loader_ok():
    async def _loader(config_path, proxy):
        return build_dataset()

    return _loader


def test_restore_depot_maintain_only_after_suppression() -> None:
    """库存保持的开关恢复只在上一轮被接管抑制过时进行。

    回归：每次 set_maa 都无条件恢复开关值，会把上一轮已完成（check_log
    已置 False）的库存保持重新点亮，重试轮把它整个重跑一遍。
    """

    from app.task.MAA.AutoProxy import AutoProxyTask

    class _ConfigStub:
        def get(self, section: str, key: str) -> bool:
            return True

    task = AutoProxyTask.__new__(AutoProxyTask)
    task.cur_user_config = _ConfigStub()
    task.task_dict = {"DepotMaintain": False}  # 上一轮已完成：任务置 False
    task._depot_maintain_suppressed = False

    task._restore_depot_maintain()
    assert task.task_dict["DepotMaintain"] is False

    task._depot_maintain_suppressed = True
    task._restore_depot_maintain()
    assert task.task_dict["DepotMaintain"] is True
    assert task._depot_maintain_suppressed is False


def test_collect_cultivate_archive_keeps_last_depot_snapshot() -> None:
    """仓库识别以本轮最后一次为准：队列里养成计划在前、更新数据在后。

    回归：只认第一条标记会采到刷取前的库存，补齐材料后仍会多接管一轮。
    """

    from app.task.MAA.AutoProxy import AutoProxyTask

    task = AutoProxyTask.__new__(AutoProxyTask)
    task._cultivate_collected_depot = False
    task._cultivate_collected_oper_box = False
    archived: list[str] = []

    def _archive(name: str, require_fresh_sync_time: bool = False) -> bool:
        archived.append(name)
        return True

    task._archive_recognition_file = _archive  # type: ignore[method-assign]

    asyncio.run(task._collect_cultivate_archive("完成任务: 养成计划 (仓库识别)"))
    asyncio.run(task._collect_cultivate_archive("完成任务: 更新数据 (仓库识别)"))

    assert archived == ["DepotData.json", "DepotData.json"]
    assert task._cultivate_collected_depot is True
