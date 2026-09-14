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

"""练度与库存的输入适配器与链执行器。

provider 本身保持无状态，运行时数据（MAA data 目录、手填练度）由
ProviderContext 注入。链执行器只依赖契约端口，接收调用方给的链；
池的定义（选哪些实现、什么优先级）属组合根职责，见 service.py
（组合点唯一，规则 1.3-6）。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .types import (
    InventoryProvider,
    Progression,
    ProgressionProvider,
    ProgressionSnapshot,
    ProviderContext,
)


def parse_oper_box_payload(payload: Mapping[str, Any]) -> dict[str, Progression]:
    """把 MAA OperBoxData.json 原始数据解析为全量练度（纯函数）。

    API 预览路径与 check_log 采集路径共用本函数（规则 1.3-3）。
    OperBoxData 无专精/模组字段，相应维度恒为空。
    """

    progressions: dict[str, Progression] = {}
    for oper in payload.get("own_opers") or []:
        if not isinstance(oper, dict) or not oper.get("id"):
            continue
        progressions[str(oper["id"])] = Progression(
            elite=oper.get("elite") or 0,
            level=oper.get("level") or 0,
            masteries={},
            modules={},
        )
    return progressions


def parse_oper_box_names(payload: Mapping[str, Any]) -> dict[str, str]:
    """把 MAA OperBoxData.json 原始数据解析为干员名字映射（纯函数）。

    名字仅用于用户可见文案（推送报告等），不进练度契约 Progression；
    达成判定可自证即干员必在识别数据中，名字因此总能随判定取到。
    """

    names: dict[str, str] = {}
    for oper in payload.get("own_opers") or []:
        if not isinstance(oper, dict) or not oper.get("id"):
            continue
        name = oper.get("name")
        if isinstance(name, str) and name:
            names[str(oper["id"])] = name
    return names


def parse_depot_payload(payload: Mapping[str, Any]) -> tuple[dict[str, int], int]:
    """把 MAA DepotData.json 原始数据解析为 (库存映射, 时间戳)。

    syncTime 兼容 epoch 秒与 ISO 8601 字符串两种格式（MAA 以
    ``ToLocalTime().ToString("o")`` 写 ISO，方案决策 26/31）。
    """

    data = payload.get("data")
    inventory = {
        item_id: count
        for item_id, count in (data or {}).items()
        if isinstance(item_id, str) and isinstance(count, int)
    }
    sync_time = payload.get("syncTime")
    if isinstance(sync_time, (int, float)) and not isinstance(sync_time, bool):
        return inventory, int(sync_time)
    if isinstance(sync_time, str):
        if sync_time.isdigit():
            return inventory, int(sync_time)
        try:
            return inventory, int(datetime.fromisoformat(sync_time).timestamp())
        except ValueError:
            pass
    return inventory, 0


def load_oper_box_index(context: ProviderContext) -> dict[str, Progression]:
    """读取（带 context 级缓存）干员练度索引：char_id → Progression。

    供 LocalProgressionProvider 逐干员取数与需要全量练度的编排方（如
    选择器过滤）共用同一份解析结果；同一 context 内只读一次磁盘。
    文件缺失或损坏返回空索引（消费方按"练度未知"处理，宁缺勿滥）。
    """

    return _load_oper_box(context)[1]


def load_oper_box_names(context: ProviderContext) -> dict[str, str]:
    """读取（带 context 级缓存）干员名字映射：char_id → 名称。

    与练度索引共用同一份磁盘读取与缓存（_load_oper_box 三元组）。
    """

    return _load_oper_box(context)[2]


def has_oper_box_data(context: ProviderContext) -> bool:
    """干员识别数据是否可用：文件存在且可解析。

    与库存的"空仓库 ≠ 数据缺失"（决策 24）同口径——识别过但结果为空
    （新号/无干员）算作"有数据"，只有缺失/损坏才算"未识别"。消费方据此
    区分"按精 0 估算"与"确实没有干员"。
    """

    return _load_oper_box(context)[0] is not None


def _load_oper_box(
    context: ProviderContext,
) -> tuple[float | None, dict[str, Progression], dict[str, str]]:
    """读取干员识别文件，返回 (mtime, 练度索引, 名字映射)；缺失/损坏时 mtime 为 None。"""

    cached = context.file_cache.get("oper_box")
    if cached is None:
        index: dict[str, Progression] = {}
        names: dict[str, str] = {}
        mtime: float | None = None
        if context.maa_data_dir is not None:
            path = Path(context.maa_data_dir) / "OperBoxData.json"
            if path.exists():
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    pass
                else:
                    mtime = path.stat().st_mtime
                    index = parse_oper_box_payload(payload)
                    names = parse_oper_box_names(payload)
        cached = (mtime, index, names)
        context.file_cache["oper_box"] = cached
    return cached


class LocalProgressionProvider:
    """MAA 本地干员识别数据（OperBoxData.json），可自证精英化等级。"""

    name = "local"
    self_certifying = True

    def fetch(
        self, operator_id: str, context: ProviderContext
    ) -> ProgressionSnapshot | None:
        if context.maa_data_dir is None:
            return None
        mtime, index = _load_oper_box(context)[:2]
        progression = index.get(operator_id)
        if progression is None:
            return None
        return ProgressionSnapshot(
            source="local", timestamp=int(mtime or 0), data=progression
        )


class ManualProgressionProvider:
    """用户手填练度；只参与需求计算，达成检测链过滤掉本适配器。"""

    name = "manual"
    self_certifying = False

    def fetch(
        self, operator_id: str, context: ProviderContext
    ) -> ProgressionSnapshot | None:
        progression = context.manual_progressions.get(operator_id)
        if progression is None:
            return None
        # 手填无观测时间，timestamp=0 仅作占位
        return ProgressionSnapshot(source="manual", timestamp=0, data=progression)


class DefaultProgressionProvider:
    """链尾兜底：精0/专0/无模组，等价全量起算（宁多勿少），恒可用。"""

    name = "default"
    self_certifying = False

    def fetch(
        self, operator_id: str, context: ProviderContext
    ) -> ProgressionSnapshot | None:
        return ProgressionSnapshot(
            source="default", timestamp=0, data=Progression.default()
        )


class LocalInventoryProvider:
    """MAA 本地仓库识别数据（DepotData.json，安装级单文件）。"""

    name = "local"

    def fetch(self, context: ProviderContext) -> tuple[Mapping[str, int], int] | None:
        if context.maa_data_dir is None:
            return None
        path = Path(context.maa_data_dir) / "DepotData.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        # 合法但为空的库存原样返回：空映射是"仓库确实没有"（新号、刚清空），
        # None 是"还没识别过"，上游据此区分是否提示重新识别
        return parse_depot_payload(payload)


# 池的定义（选哪些实现、什么顺序）属组合根职责，见 service.py。
# 本模块只提供适配器与链执行器：执行器依赖契约端口，不关心池内容。


def resolve_progression(
    operator_id: str,
    chain: tuple[ProgressionProvider, ...],
    context: ProviderContext | None = None,
) -> ProgressionSnapshot:
    """链执行器：短路取首个可用观测；default 链尾恒可用，返回值非 None。"""

    context = context or ProviderContext()
    for provider in chain:
        snapshot = provider.fetch(operator_id, context)
        if snapshot is not None:
            return snapshot
    return ProgressionSnapshot(
        source="default", timestamp=0, data=Progression.default()
    )


def resolve_inventory(
    context: ProviderContext,
    chain: tuple[InventoryProvider, ...],
) -> tuple[Mapping[str, int], int] | None:
    """库存链执行器；全部不可用时返回 None（调用方按 0 估算兜底）。"""

    for provider in chain:
        result = provider.fetch(context)
        if result is not None:
            return result
    return None
