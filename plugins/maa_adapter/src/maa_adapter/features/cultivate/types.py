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

"""养成计算内核的契约类型与端口协议。

本模块是内核包的最底层：领域类型、provider 端口协议与外部数据契约全部
定义在这里，engine / providers / yituliu 只依赖本模块（DIP：抽象归内核
所有，适配器反向依赖契约）。本模块自身零 IO、零 app.* 依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping, Protocol, runtime_checkable

GoalKind = Literal["elite", "mastery", "module"]

GoalState = Literal[
    "not_started",  # 攒材料等待（材料已齐或尚未开刷）
    "in_progress",  # 进行中（存在缺口，刷取进行中）
    "achieved",  # 已达成（计划已移除，档案保留）
    "pending_confirm",  # 待确认（达成但来源不可自证，等用户确认）
    "cultivating",  # P5 预留：MAA AutoRaise 自动养成中
]

MaterialClass = Literal["farmable", "synthesizable", "unobtainable"]

ProgressionSource = Literal["skland", "local", "manual", "default"]


@dataclass(frozen=True)
class Goal:
    """实例级养成目标（精英化 1 条；技能按 skillId；模组按 uniEquipId）。"""

    kind: GoalKind
    target_id: str  # mastery=skillId；module=uniEquipId；elite 固定 ""
    to_level: int  # elite: 1|2；mastery/module: 1..3
    state: GoalState = "not_started"


@dataclass(frozen=True)
class GoalRef:
    """条目档案：单个目标对某项材料的贡献量（重聚合与 UI 展开用）。"""

    operator_id: str
    goal_index: int
    amount: int


@dataclass(frozen=True)
class OperatorTarget:
    """一名干员 + 其全部养成目标。"""

    operator_id: str
    goals: tuple[Goal, ...]


@dataclass(frozen=True)
class Progression:
    """干员练度（中立表达，与 MAA/森空岛字段解耦）。"""

    elite: int
    level: int
    masteries: Mapping[str, int]  # skillId -> 专精等级
    modules: Mapping[str, int]  # uniEquipId -> 模组等级

    @staticmethod
    def default() -> "Progression":
        """精0/专0/无模组的兜底练度（等价全量起算，宁多勿少）。"""

        return Progression(elite=0, level=1, masteries={}, modules={})


@dataclass(frozen=True)
class ProgressionSnapshot:
    """一次练度观测：来源、观测时间（epoch 秒）与数据。"""

    source: ProgressionSource
    timestamp: int
    data: Progression


@dataclass(frozen=True)
class Requirement:
    """聚合后的单项材料需求。"""

    item_id: str
    amount: int  # 保有量目标（MAA DropCount 语义：库存补到此值即达标）
    sources: tuple[GoalRef, ...] = ()  # 条目档案：哪些目标贡献了多少


@dataclass(frozen=True)
class FarmEntry:
    """折算后的可刷取条目，直接对应 MAA PlanList 的一项。"""

    item_id: str
    amount: int  # 净缺口：按库存抵扣后还需刷取的数量
    stage_code: str  # 推荐关卡码；auto 语义由构建时的最新数据解析
    held: int = 0  # 档案现存：MAA 保有量目标 = amount + held（构建器叠加）
    expected_runs: float = 0.0  # 期望次数（概率期望，非保证值）
    expected_sanity: float = 0.0  # 期望理智
    sources: tuple[GoalRef, ...] = ()


@dataclass(frozen=True)
class CultivatePlan:
    """内核输出的中性养成计划（MAA 形状映射发生在 AutoProxy 构建器）。"""

    entries: tuple[FarmEntry, ...]  # 已按刷取优先级排序（见 engine 排序不变量）
    demands: tuple[Requirement, ...] = ()  # 完整材料清单（含不可直刷/不可获取，供 UI）
    unobtainable: tuple[Requirement, ...] = ()  # 不可获取类子集（UI 单列"需另行获取"）


@dataclass(frozen=True)
class Achievement:
    """单目标达成判定结果。"""

    operator_id: str
    goal_index: int
    achieved: bool
    confident: bool  # False = 判定来源不可自证，转 pending_confirm 由用户确认


@dataclass(frozen=True)
class ProviderContext:
    """链执行器传给各 provider 的运行时上下文（provider 本身保持无状态）。

    ``file_cache`` 供 provider 在单次编排内缓存识别文件解析结果（同目录
    多干员多次取数只读一次磁盘）；provider 不跨调用持有状态，缓存随
    context 生命周期走。森空岛整表快照由异步驱动层（cultivate/skland.py）
    拉取后注入，skland 适配器只做同步查表（决策 38）。
    """

    maa_data_dir: Path | None = None  # MAA 安装目录 data/，local 适配器读取用
    manual_progressions: Mapping[str, Progression] = field(default_factory=dict)
    file_cache: dict[str, Any] = field(default_factory=dict)
    skland_progressions: Mapping[str, Progression] = field(
        default_factory=dict
    )  # player/info 整表解析结果；空映射 = 未拉取/不可用，链短路落 local
    skland_captured_at: int = 0  # 快照拉取时刻（epoch 秒）


@runtime_checkable
class ProgressionProvider(Protocol):
    """练度源端口：组合根按序调用，取首个可用观测。"""

    name: ProgressionSource
    self_certifying: bool  # 能否用于达成检测（手填/兜底为 False）

    def fetch(
        self, operator_id: str, context: ProviderContext
    ) -> ProgressionSnapshot | None:
        """取单个干员的练度观测；不可用时返回 None。"""
        ...  # pragma: no cover


class InventoryProvider(Protocol):
    """库存源端口（参与缺口预览与接管判定，无 self_certifying 概念）。"""

    name: str

    def fetch(self, context: ProviderContext) -> tuple[Mapping[str, int], int] | None:
        """返回 (itemId→数量, 时间戳 epoch 秒)；不可用时返回 None。"""
        ...  # pragma: no cover


@dataclass(frozen=True)
class DemandEntry:
    """单干员单档养成消耗（来自需求表，按实例分级存储）。"""

    kind: GoalKind
    target_id: str  # mastery=skillId；module=uniEquipId；elite=""
    level: int  # 该档把对应维度升到的等级；区间求和按 current < level <= to 取用
    items: Mapping[str, int]  # itemId -> 数量


@dataclass(frozen=True)
class DropEntry:
    """单关单材料掉落期望（占位 ID 已在数据层过滤）。"""

    stage_id: str
    item_id: str
    expected_per_run: float  # quantity/times，每次期望掉落
    start_ms: int  # 时间窗下界（epoch 毫秒，0 = 不限）
    end_ms: int | None  # 时间窗上界（epoch 毫秒，None = 不限）


@dataclass(frozen=True)
class StageMeta:
    """关卡元数据；资源本/芯片本由 13 关常量表补齐（yituliu 数据层）。"""

    stage_id: str
    stage_code: str
    ap_cost: int
    open_weekdays: tuple[int, ...] | None  # 0=周一..6=周日；None = 无星期限制
    composite: float = 0.0  # 综合效率：Σ(每次掉落期望×物品价值)/理智，展示时 ×100%


@dataclass(frozen=True)
class Recipe:
    """合成关系：1 个 result 由 ingredients 合成（composite 表的逆向边）。"""

    result_item_id: str
    ingredients: Mapping[str, int]


@dataclass(frozen=True)
class CultivateDataSet:
    """内核消费的数据集契约；一图流适配器与未来 MAA raise_demand 适配器都产出它。"""

    demands: Mapping[str, tuple[DemandEntry, ...]]  # char_id -> 档位列表
    drops: tuple[DropEntry, ...]
    stages: Mapping[str, StageMeta]  # stage_id -> 元数据
    recipes: tuple[Recipe, ...]
    material_class: Mapping[str, MaterialClass]  # 物品三分类（数据层预计算）
    fixed_source_stages: Mapping[str, str] = field(
        default_factory=dict
    )  # itemId -> stageId：资源关固定产出（无掉落统计，如采购凭证 ← AP-5）
    item_value: Mapping[str, float] = field(
        default_factory=dict
    )  # 物品价值（理智等价）
    data_version: str = ""  # 快照版本（抓取日期 + 源标识）
