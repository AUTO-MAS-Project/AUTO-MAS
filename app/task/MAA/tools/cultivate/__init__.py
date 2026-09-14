#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""MAA 干员养成计算内核（P1-A）。

分层（方案 §1）：types 为契约层，engine 为纯函数内核，providers /
yituliu 为输入适配器，service 为应用编排层与组合根。调用方
（AutoProxy / API）只 import 本包出口，不直接触碰内核内部模块。
"""

from .engine import (
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
from .providers import (
    has_oper_box_data,
    load_oper_box_index,
    load_oper_box_names,
    parse_depot_payload,
    parse_oper_box_names,
    parse_oper_box_payload,
    resolve_inventory,
    resolve_progression,
)
from .service import (
    DepotCultivateService,
    depot_cultivate_service,
    dump_cultivate_targets,
    filter_catalog_by_elite,
    get_certifying_chain,
    get_inventory_chain,
    get_progression_chain,
    parse_cultivate_targets,
)
from .types import (
    Achievement,
    CultivateDataSet,
    CultivatePlan,
    DemandEntry,
    DropEntry,
    FarmEntry,
    Goal,
    GoalKind,
    GoalRef,
    GoalState,
    OperatorTarget,
    Progression,
    ProgressionProvider,
    ProgressionSnapshot,
    ProviderContext,
    Recipe,
    Requirement,
    StageMeta,
)
from .yituliu import (
    YituliuDataError,
    dataset_from_json,
    dataset_to_json,
    download_dataset,
    get_dataset_cached,
    load_dataset,
    stage_candidates,
)

__all__ = [
    "Achievement",
    "CultivateDataSet",
    "CultivatePlan",
    "DemandEntry",
    "DepotCultivateService",
    "DropEntry",
    "FarmEntry",
    "Goal",
    "GoalKind",
    "GoalRef",
    "GoalState",
    "OperatorTarget",
    "Progression",
    "ProgressionProvider",
    "ProgressionSnapshot",
    "ProviderContext",
    "Recipe",
    "Requirement",
    "StageMeta",
    "YituliuDataError",
    "aggregate",
    "apply_achievements",
    "build_plan",
    "build_requirements",
    "dataset_from_json",
    "depot_cultivate_service",
    "dataset_to_json",
    "download_dataset",
    "dump_cultivate_targets",
    "filter_catalog_by_elite",
    "get_dataset_cached",
    "get_certifying_chain",
    "get_inventory_chain",
    "get_progression_chain",
    "has_material_gap",
    "has_oper_box_data",
    "judge_achievements",
    "load_dataset",
    "load_oper_box_index",
    "load_oper_box_names",
    "parse_cultivate_targets",
    "parse_depot_payload",
    "parse_oper_box_names",
    "parse_oper_box_payload",
    "recommend_stages",
    "resolve_inventory",
    "resolve_progression",
    "stage_candidates",
    "summarize_achievements",
    "synthesize",
]
