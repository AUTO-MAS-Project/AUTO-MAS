#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""养成内核的应用编排层与组合根。

分层职责（DIP）：
- `types`     契约层，零依赖；
- `engine`    纯函数内核，只依赖契约；
- `providers` / `yituliu`  输入适配器与链执行器，只实现/依赖契约端口；
- 本模块     组合根与用例编排：决定用哪些适配器、如何取数据、如何组装成
  消费方（API / AutoProxy）要的形状。

组合根位于库边界：适配器不再知道自己是否被使用——换实现 = 改本模块的
池定义，或由调用方注入 chain / 数据源（见 `DepotCultivateService` 构造
参数），内核与适配器零改动。
"""

from __future__ import annotations

import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

import httpx

from app.utils.constants import UTC4

from .engine import apply_achievements, build_plan, has_material_gap, judge_achievements
from .providers import (
    DefaultProgressionProvider,
    LocalInventoryProvider,
    LocalProgressionProvider,
    ManualProgressionProvider,
    has_oper_box_data,
    load_oper_box_index,
    resolve_inventory,
    resolve_progression,
)
from .types import (
    CultivateDataSet,
    CultivatePlan,
    Goal,
    GoalKind,
    GoalState,
    InventoryProvider,
    OperatorTarget,
    ProgressionProvider,
    ProviderContext,
)
from .yituliu import (
    get_dataset_cached,
    load_operator_catalog,
    stage_candidates,
)

# 组合根：池的顺序即优先级。P4 森空岛接入 = 在 PROGRESSION_POOL 链首
# 插入 SklandProvider（self_certifying=True），双链自动生效，消费方零改动。
PROGRESSION_POOL: tuple[ProgressionProvider, ...] = (
    LocalProgressionProvider(),
    ManualProgressionProvider(),
    DefaultProgressionProvider(),
)

INVENTORY_POOL: tuple[InventoryProvider, ...] = (LocalInventoryProvider(),)


def get_progression_chain() -> tuple[ProgressionProvider, ...]:
    """需求计算链：全量池（含手填与兜底）。"""

    return PROGRESSION_POOL


def get_certifying_chain() -> tuple[ProgressionProvider, ...]:
    """达成检测链：按 self_certifying 过滤派生（手填不能自证达成）。"""

    return tuple(provider for provider in PROGRESSION_POOL if provider.self_certifying)


def get_inventory_chain() -> tuple[InventoryProvider, ...]:
    """库存链（预览与接管缺口判定用）。"""

    return INVENTORY_POOL


# 数据集加载端口签名：(配置目录, 代理) -> 数据集
DatasetLoader = Callable[
    [Path, "httpx.Proxy | str | None"], Awaitable[CultivateDataSet]
]

_VALID_GOAL_KINDS: tuple[GoalKind, ...] = ("elite", "mastery", "module")
_VALID_GOAL_STATES: tuple[GoalState, ...] = (
    "not_started",
    "in_progress",
    "achieved",
    "pending_confirm",
    "cultivating",
)


def _parse_goal(payload: object) -> Goal | None:
    """解析单条养成目标；非法条目返回 None（配置面宽容，坏条目不炸注入）。"""

    if not isinstance(payload, dict):
        return None
    kind = payload.get("kind")
    if kind not in _VALID_GOAL_KINDS:
        return None
    goal_kind: GoalKind = kind  # 已按字面量集合校验
    to_level = payload.get("to_level")
    if not isinstance(to_level, int) or isinstance(to_level, bool):
        return None
    # elite 上限 2；mastery/module 上限 3
    if not 1 <= to_level <= (2 if goal_kind == "elite" else 3):
        return None
    if goal_kind == "elite":
        target_id = ""
    else:
        target_id = payload.get("target_id")
        if not isinstance(target_id, str) or not target_id:
            return None
    state = payload.get("state")
    goal_state: GoalState = state if state in _VALID_GOAL_STATES else "not_started"
    return Goal(goal_kind, target_id, to_level, goal_state)


def parse_cultivate_targets(payload: object) -> tuple[OperatorTarget, ...]:
    """把用户配置的养成目标 JSON 解析为契约目标（宽容：跳过非法条目）。

    字段与内核对齐：``operator_id`` + ``goals[{kind, target_id, to_level,
    state}]``。结构保留三类 goal（决策 32 接口预留），档位上限按 kind
    校验（elite 1-2，mastery/module 1-3）。
    """

    if not isinstance(payload, list):
        return ()
    targets: list[OperatorTarget] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        operator_id = entry.get("operator_id")
        if not isinstance(operator_id, str) or not operator_id:
            continue
        raw_goals = entry.get("goals")
        goals = [
            goal
            for item in (raw_goals if isinstance(raw_goals, list) else [])
            if (goal := _parse_goal(item)) is not None
        ]
        if goals:
            targets.append(OperatorTarget(operator_id, tuple(goals)))
    return tuple(targets)


def filter_catalog_by_elite(
    catalog: list[dict],
    progression_index: Mapping[str, Any],
    *,
    max_elite: int = 2,
) -> list[dict]:
    """从选择器目录剔除练度已达上限的干员（纯函数）。

    PR2 目标只有精英化（决策 32），已精 2 的干员无可设目标，选了也会在
    注入时被达成拦截移除，直接从源头剔除；练度未知（未识别/未拥有）的
    干员保留——宁多勿少。P4 森空岛接入后目标扩展到专精/模组，本过滤
    随之放开（方案决策 32 的配套 UX）。
    """

    def _known_elite(item: dict) -> int | None:
        progression = progression_index.get(item.get("value"))
        if progression is None:
            return None
        return progression.elite

    return [
        item
        for item in catalog
        if (elite := _known_elite(item)) is None or elite < max_elite
    ]


def dump_cultivate_targets(
    targets: tuple[OperatorTarget, ...] | list[OperatorTarget],
) -> list[dict]:
    """把契约目标序列化回用户配置 JSON（与 parse_cultivate_targets 对称）。"""

    return [
        {
            "operator_id": target.operator_id,
            "goals": [
                {
                    "kind": goal.kind,
                    "target_id": goal.target_id,
                    "to_level": goal.to_level,
                    "state": goal.state,
                }
                for goal in target.goals
            ],
        }
        for target in targets
    ]


class DepotCultivateService:
    """MAA 库存保持编辑器的数据编排服务（组合根 + 用例）。

    依赖以端口形式注入，默认实现为生产装配：
    - `dataset_loader`：取养成数据集（默认一图流缓存加载，带磁盘/进程缓存）；
    - `progressions` / `inventory_chain`：练度与库存来源链。

    测试或未来接入第二个数据源时替换构造参数即可，本类之外零改动。
    """

    def __init__(
        self,
        *,
        dataset_loader: DatasetLoader | None = None,
        inventory_chain: tuple[InventoryProvider, ...] | None = None,
    ) -> None:
        self._dataset_loader = dataset_loader
        self._inventory_chain = inventory_chain or get_inventory_chain()

    async def stage_candidates(
        self,
        *,
        config_path: Path,
        item_id: str,
        proxy: httpx.Proxy | str | None = None,
        now_ms: int | None = None,
    ) -> list[dict[str, str]]:
        """掉落指定材料的关卡候选，按单件期望理智升序（UI 下拉形状）。

        资源关固定产出材料（采购凭证等）无单件理智，label 只展示关卡名
        与产出性质（见 yituliu._FIXED_SOURCE_STAGES）。
        """

        dataset = await self._load_dataset(config_path, proxy)
        options = stage_candidates(
            dataset,
            now_ms=now_ms if now_ms is not None else int(time.time() * 1000),
        ).get(item_id, [])
        return [
            {
                "label": (
                    f"{option['stage']}（固定产出）"
                    if option.get("fixed")
                    else f"{option['stage']}（{option['sanityPerItem']} 理智/件）"
                ),
                "value": option["stage"],
            }
            for option in options
        ]

    async def inventory(self, *, maa_data_dir: Path) -> Mapping[str, int] | None:
        """读取 MAA 仓库库存映射；数据不可用时返回 None（调用方决定兜底）。"""

        context = ProviderContext(maa_data_dir=maa_data_dir)
        result = resolve_inventory(context, self._inventory_chain)
        return result[0] if result is not None else None

    async def operator_catalog(
        self,
        *,
        config_path: Path,
        proxy: httpx.Proxy | str | None = None,
        maa_data_dir: Path | None = None,
    ) -> list[dict]:
        """干员选择器目录（一图流全量表，随快照缓存；方案决策 11/33）。

        Args:
            maa_data_dir: 用户档案目录。提供时按其中 OperBoxData 剔除已
                精 2 的干员（PR2 仅精英化目标，决策 32）；缺失或未识别时
                不过滤（练度未知宁多勿少）。

        Returns:
            ``[{value: char_id, label: 名称, rarity, profession}]``，稀有度
            降序、名称升序；一图流不可用且无缓存时抛 YituliuDataError。
        """

        catalog = await load_operator_catalog(config_path, proxy)
        if maa_data_dir is None:
            return catalog
        index = load_oper_box_index(ProviderContext(maa_data_dir=maa_data_dir))
        return filter_catalog_by_elite(catalog, index)

    async def preview_cultivate(
        self,
        *,
        targets: tuple[OperatorTarget, ...] | list[OperatorTarget],
        maa_data_dir: Path,
        config_path: Path,
        proxy: httpx.Proxy | str | None = None,
        today: date | None = None,
    ) -> tuple[CultivatePlan | None, dict[str, bool]]:
        """养成计划预览（纯计算不落库，方案 §4.3）。

        与注入同一管线（达成拦截后的剩余目标建计划），但不做任何持久化；
        目标为空或全部达成移除时计划为 None。

        Returns:
            (计划, 数据可用性)：``{"has_progression": 干员识别档案存在,
            "has_inventory": 仓库识别档案存在}``——两者缺任一时预览按
            default 练度/空库存估算，前端须提示"以识别后为准"。
        """

        # 两类识别数据同口径判定（对齐决策 24：识别过但结果为空算"有数据"，
        # 只有缺失/损坏才算"未识别"）；context 贯穿到 prepare，共享 file_cache
        # 避免重复解析同一份识别文件
        context = ProviderContext(maa_data_dir=maa_data_dir)
        availability = {
            "has_progression": has_oper_box_data(context),
            "has_inventory": resolve_inventory(context, self._inventory_chain)
            is not None,
        }
        _, plan, _ = await self.prepare_cultivate(
            targets=targets,
            maa_data_dir=maa_data_dir,
            config_path=config_path,
            proxy=proxy,
            today=today,
            context=context,
        )
        return plan, availability

    async def prepare_cultivate(
        self,
        *,
        targets: tuple[OperatorTarget, ...] | list[OperatorTarget],
        maa_data_dir: Path,
        config_path: Path,
        proxy: httpx.Proxy | str | None = None,
        today: date | None = None,
        context: ProviderContext | None = None,
    ) -> tuple[list[OperatorTarget], CultivatePlan | None, bool]:
        """注入前的养成用例编排：达成拦截 → 剩余目标建计划 → 缺口判定。

        方案 §4.1 注入三步判定的数据组织：先经自证链判定达成并流转状态
        （可自证达成移除 / 不可自证转待确认），剩余目标经全量链取练度
        建计划，再按库存递归抵扣口径判定缺口。库存不可用时按 0 估算
        （视为有缺口）。

        Returns:
            (流转后的目标列表, 养成计划, 是否存在材料缺口)；目标全部达成
            移除时计划为 None、缺口为 False。

        Raises:
            Exception: 数据集不可用等错误原样抛出，由调用方 fail-open
            （视为不接管、不注入），本方法不吞异常。
        """

        context = context or ProviderContext(maa_data_dir=maa_data_dir)
        dataset = await self._load_dataset(config_path, proxy)
        today = today or datetime.now(tz=UTC4).date()

        # 达成拦截：自证链（local）判定；全量链（local+手填+兜底）供需求计算
        certifying_snapshots = {
            target.operator_id: resolve_progression(
                target.operator_id, get_certifying_chain(), context
            )
            for target in targets
        }
        snapshots = {
            target.operator_id: resolve_progression(
                target.operator_id, get_progression_chain(), context
            )
            for target in targets
        }
        inventory_result = resolve_inventory(context, self._inventory_chain)
        inventory: Mapping[str, int] = inventory_result[0] if inventory_result else {}

        updated_targets = apply_achievements(
            targets,
            judge_achievements(targets, certifying_snapshots),
            snapshots=snapshots,
            inventory=inventory,
            data=dataset,
            today=today,
        )
        if not updated_targets:
            return [], None, False

        plan = build_plan(
            targets=updated_targets,
            snapshots=snapshots,
            data=dataset,
            today=today,
            inventory=inventory,
        )
        gap = has_material_gap(updated_targets, snapshots, inventory, dataset, today)
        return updated_targets, plan, gap

    async def _load_dataset(
        self, config_path: Path, proxy: httpx.Proxy | str | None
    ) -> CultivateDataSet:
        if self._dataset_loader is not None:
            return await self._dataset_loader(config_path, proxy)
        return await get_dataset_cached(config_path, proxy)


# 生产装配的单例：消费方复用同一实例，保证数据集进程内缓存与池决策唯一。
depot_cultivate_service = DepotCultivateService()

__all__ = [
    "DepotCultivateService",
    "depot_cultivate_service",
    "get_certifying_chain",
    "get_inventory_chain",
    "get_progression_chain",
    "dump_cultivate_targets",
    "parse_cultivate_targets",
]
