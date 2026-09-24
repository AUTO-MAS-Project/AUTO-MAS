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
from typing import Awaitable, Callable, Collection, Mapping

import httpx

from app.utils.constants import UTC4

from .engine import apply_achievements, build_plan, has_material_gap, judge_achievements
from .providers import (
    DefaultProgressionProvider,
    LocalInventoryProvider,
    LocalProgressionProvider,
    ManualProgressionProvider,
    SklandProgressionProvider,
    has_oper_box_data,
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
    Progression,
    ProgressionProvider,
    ProgressionSnapshot,
    ProviderContext,
)
from .yituliu import (
    get_dataset_cached,
    load_operator_catalog,
    stage_candidates,
)

# 组合根：池的顺序即优先级。森空岛在练度链首（决策 37/38），快照经
# ProviderContext 注入（cultivate.skland.fetch_skland_progression，TTL
# 缓存）；未注入快照时本源返回 None，双链行为与仅本地时完全一致。
PROGRESSION_POOL: tuple[ProgressionProvider, ...] = (
    SklandProgressionProvider(),
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
        # 同一 (kind, target_id) 只保留首条：手改配置可能造出重复 goal，
        # 重复条目在编辑器里不可见却会重复计缺口（keep-first，不重排用户配置）
        goals_by_key: dict[tuple[GoalKind, str], Goal] = {}
        for item in raw_goals if isinstance(raw_goals, list) else []:
            if (goal := _parse_goal(item)) is not None:
                goals_by_key.setdefault((goal.kind, goal.target_id), goal)
        goals = list(goals_by_key.values())
        if goals:
            targets.append(OperatorTarget(operator_id, tuple(goals)))
    return tuple(targets)


def filter_catalog_by_goals(
    catalog: list[dict],
    snapshots: Mapping[str, ProgressionSnapshot],
    keep_ids: Collection[str] = (),
) -> list[dict]:
    """goal-aware 选择器过滤：剔除已无可加目标的干员（纯函数，决策 38）。

    - 观测无专精/模组维度（来源非 skland，local 识别无此类字段）：退化
      PR2 口径，已精 2 剔除；
    - skland 快照：精 2 且目录内技能专精全满(3) 且模组全满(3) 才剔除；
      目录未列出技能与模组时无法判断，保留（宁多勿少）；
    - 干员不在快照中（未拥有/未识别）保留；
    - ``keep_ids``（用户已存目标引用的干员）一律保留：目录同时是编辑行的
      名称来源，被剔除的干员会让已存目标显示成内部 ID、且无法再添加目标
      （森空岛降级回 local 链路时正会命中——决策 40 配套）。
    """

    kept: list[dict] = []
    for item in catalog:
        if item.get("value") in keep_ids:
            kept.append(item)
            continue
        snapshot = snapshots.get(item.get("value"))
        if snapshot is None:
            kept.append(item)
            continue
        progression = snapshot.data
        if snapshot.source != "skland":
            if progression.elite < 2:
                kept.append(item)
            continue
        if progression.elite < 2:
            kept.append(item)
            continue
        skills = item.get("skills") or []
        modules = item.get("modules") or []
        if not skills and not modules:
            kept.append(item)
            continue
        mastery_maxed = all(
            progression.masteries.get(skill["value"], 0) >= 3 for skill in skills
        )
        module_maxed = all(
            progression.modules.get(module["value"], 0) >= 3 for module in modules
        )
        if not (mastery_maxed and module_maxed):
            kept.append(item)
    return kept


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

    async def inventory(
        self, *, maa_data_dir: Path
    ) -> tuple[Mapping[str, int], int] | None:
        """读取 MAA 仓库库存映射与识别时间（epoch 秒）；不可用时返回 None。

        识别时间取档案 syncTime（MAA 写入的识别时刻），缺省回退档案 mtime
        （决策 31），供前端展示新鲜度；缺口判定不消费该时间。
        """

        context = ProviderContext(maa_data_dir=maa_data_dir)
        return resolve_inventory(context, self._inventory_chain)

    async def operator_catalog(
        self,
        *,
        config_path: Path,
        proxy: httpx.Proxy | str | None = None,
        maa_data_dir: Path | None = None,
        skland: tuple[Mapping[str, Progression], int] | None = None,
        keep_ids: Collection[str] = (),
    ) -> list[dict]:
        """干员选择器目录（一图流全量表，随快照缓存；方案决策 11/33/38）。

        Args:
            maa_data_dir: 用户档案目录。提供时按有效练度链过滤无可加目标
                的干员（goal-aware，决策 38）：无森空岛快照时退化 PR2 的
                "剔已精 2"，绑定后按"精2 ∧ 专精全满 ∧ 模组全满"剔除。
            skland: 森空岛整表快照 (练度映射, 拉取时刻)；None = 未绑定或
                拉取失败，过滤退化如上。
            keep_ids: 无论练度如何都保留的干员（用户已存目标引用者），
                保证编辑行始终拿得到名称与可加目标。

        Returns:
            ``[{value: char_id, label: 名称, rarity, profession, maxElite,
            dataMissing, skills, modules}]``（skills/modules 为目标编辑行展示
            用名称目录，各自带可达档位上限 maxLevel，决策 40），稀有度降序、
            名称升序；一图流不可用且无缓存时抛 YituliuDataError。
        """

        catalog = await load_operator_catalog(config_path, proxy)
        if maa_data_dir is None:
            return catalog
        context = ProviderContext(
            maa_data_dir=maa_data_dir,
            skland_progressions=skland[0] if skland else {},
            skland_captured_at=skland[1] if skland else 0,
        )
        chain = get_progression_chain()
        snapshots = {
            item["value"]: resolve_progression(item["value"], chain, context)
            for item in catalog
        }
        return filter_catalog_by_goals(catalog, snapshots, keep_ids)

    async def preview_cultivate(
        self,
        *,
        targets: tuple[OperatorTarget, ...] | list[OperatorTarget],
        maa_data_dir: Path,
        config_path: Path,
        proxy: httpx.Proxy | str | None = None,
        today: date | None = None,
        skland: tuple[Mapping[str, Progression], int] | None = None,
    ) -> tuple[
        CultivatePlan | None,
        dict[str, bool],
        dict[str, ProgressionSnapshot],
    ]:
        """养成计划预览（纯计算不落库，方案 §4.3）。

        与注入同一管线（达成拦截后的剩余目标建计划），但不做任何持久化；
        目标为空或全部达成移除时计划为 None。

        Args:
            skland: 森空岛整表快照 (练度映射, 拉取时刻)；None = 未绑定或
                拉取失败，链短路落 local（决策 37/38）。

        Returns:
            (计划, 数据可用性, 目标干员当前练度)：可用性为
            ``{"has_progression": 练度数据可用（本地识别档案或森空岛快照）,
            "has_inventory": 仓库识别档案存在}``——两者缺任一时预览按
            default 练度/空库存估算，前端须提示"以识别后为准"；练度映射
            覆盖全部目标干员（source=default 表示无实测数据），供编辑器
            展示"当前等级 → 目标等级"。
        """

        # 两类识别数据同口径判定（对齐决策 24：识别过但结果为空算"有数据"，
        # 只有缺失/损坏才算"未识别"）；context 贯穿到 prepare，共享 file_cache
        # 避免重复解析同一份识别文件
        context = ProviderContext(
            maa_data_dir=maa_data_dir,
            skland_progressions=skland[0] if skland else {},
            skland_captured_at=skland[1] if skland else 0,
        )
        availability = {
            # 练度可用 = 本地识别档案或森空岛快照（绑定后由链首提供真实练度，
            # 此时缺档案不该提示"按精 0 估算"）
            "has_progression": has_oper_box_data(context)
            or bool(context.skland_progressions),
            "has_inventory": resolve_inventory(context, self._inventory_chain)
            is not None,
        }
        # 目标干员当前练度与 prepare 共享 context 的 file_cache，不重复解析
        progressions = {
            target.operator_id: resolve_progression(
                target.operator_id, get_progression_chain(), context
            )
            for target in targets
        }
        _, plan, _ = await self.prepare_cultivate(
            targets=targets,
            maa_data_dir=maa_data_dir,
            config_path=config_path,
            proxy=proxy,
            today=today,
            context=context,
        )
        return plan, availability, progressions

    async def prepare_cultivate(
        self,
        *,
        targets: tuple[OperatorTarget, ...] | list[OperatorTarget],
        maa_data_dir: Path,
        config_path: Path,
        proxy: httpx.Proxy | str | None = None,
        today: date | None = None,
        context: ProviderContext | None = None,
        skland: tuple[Mapping[str, Progression], int] | None = None,
    ) -> tuple[list[OperatorTarget], CultivatePlan | None, bool]:
        """注入前的养成用例编排：达成拦截 → 剩余目标建计划 → 缺口判定。

        方案 §4.1 注入三步判定的数据组织：先经自证链判定达成并流转状态
        （可自证达成移除 / 不可自证转待确认），剩余目标经全量链取练度
        建计划，再按库存递归抵扣口径判定缺口。库存不可用时按 0 估算
        （视为有缺口）。

        Args:
            context: 调用方自建的 ProviderContext（AutoProxy 注入路径带
                森空岛快照时使用）；传入时 `skland` 参数被忽略。
            skland: 森空岛整表快照 (练度映射, 拉取时刻)；None = 未绑定或
                拉取失败，链短路落 local（决策 37/38）。

        Returns:
            (流转后的目标列表, 养成计划, 是否存在材料缺口)；目标全部达成
            移除时计划为 None、缺口为 False。

        Raises:
            Exception: 数据集不可用等错误原样抛出，由调用方 fail-open
            （视为不接管、不注入），本方法不吞异常。
        """

        if context is None:
            context = ProviderContext(
                maa_data_dir=maa_data_dir,
                skland_progressions=skland[0] if skland else {},
                skland_captured_at=skland[1] if skland else 0,
            )
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
