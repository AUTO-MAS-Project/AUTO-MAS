#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""存活项目集合与运行池后台对账的触发（宿主侧，项目更新这一块）。

「哪些项目还在」要读托管和项目副本（视图），归项目更新这一侧；托管只经属主登记
（``owners``）问，算好的路径集合作为普通数据交给 agent 环境一侧的 ``pool_reconcile`` 去对账回收。

**应保留的视图** = 已登记属主确认仍在的托管的视图，加上盘上所有判定不了「已经不在」的视图：没有
标记、标记里没有属主、属主没登记（或这一轮没答上来）、属主记录与目录名对不上的都算。只有「属主
已登记、且属主名下没有这个托管」的视图才算不在（:func:`classify_views`）。这个集合算不出来（托管
没完整加载、任何一个属主答不上来）时调用方整轮跳过，不拿半截集合去回收。
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from app.task.MaaFW.tools.embedded import owners
from app.task.MaaFW.tools.embedded.embedded_project import (
    embedded_projects_root,
    is_embedded_copy_dir_name,
    resolve_maafw_project_root,
    view_owner,
)
from app.task.MaaFW.tools.embedded.pool_reconcile import (
    reconcile_after_project_update,
    reconcile_runtime_pool,
)
from app.utils import get_logger

# 与 ``pool_reconcile`` 同一个 logger 名：这几行原先就在那里记。
logger = get_logger("MFW 运行池回收")


@dataclass
class ViewClassification:
    """``data/mfw`` 下每个视图目录归哪一类（目录名）。"""

    # 属主确认仍在的托管的视图（盘上在的）
    alive: list[str] = field(default_factory=list)
    # 判定不了「已经不在」的：没标记 / 没属主 / 属主没登记 / 记录对不上目录名
    undetermined: list[str] = field(default_factory=list)
    # 属主已登记、且属主名下没有这个托管
    gone: list[str] = field(default_factory=list)
    # 视图上记着、这一轮却没有答上来的属主名（插件没装 / 没加载起来）
    unanswered_owners: set[str] = field(default_factory=set)


def classify_views(
    current: owners.LiveSnapshot, root: Path | None = None
) -> ViewClassification:
    """按属主的回答给盘上每个视图目录分类。碰磁盘（读标记），调用方自己决定在哪个线程。"""

    root = root if root is not None else embedded_projects_root()
    result = ViewClassification()
    if not root.is_dir():
        return result
    alive = current.alive_view_names()
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if not is_embedded_copy_dir_name(child.name) or not child.is_dir():
            continue
        if child.name in alive:
            result.alive.append(child.name)
            continue
        recorded = view_owner(child)
        if recorded is None:
            result.undetermined.append(child.name)
            continue
        owner_name, _script_id = recorded
        if owner_name not in current.by_owner:
            result.unanswered_owners.add(owner_name)
            result.undetermined.append(child.name)
            continue
        # 目录名由记录里的 uuid 推出、且不在任何属主的名单里：属主确认它已经不在
        result.gone.append(child.name)
    return result


def keep_view_paths(current: owners.LiveSnapshot) -> list[str]:
    """应保留的视图目录（盘上在的），交给 agent 环境对账隔离 venv。"""

    root = embedded_projects_root()
    views = classify_views(current, root)
    alive = {name for name in views.alive}
    paths = [
        str(resolve_maafw_project_root(record.uid, None))
        for record in current.records()
        if record.view_name in alive
    ]
    listed = {Path(path).name for path in paths}
    # 被多个属主认领的托管不在 records() 里，但它的视图照样保留
    paths.extend(str(root / name) for name in views.alive if name not in listed)
    paths.extend(str(root / name) for name in views.undetermined)
    return paths


def collect_live_project_paths(
    records: Iterable[owners.ManagedRecord],
) -> list[str]:
    """属主确认仍在的托管的有效项目根（权威集合的输入）。

    lab（内嵌副本）口径：有效根永远是副本 ``data/mfw/<12hex>``（更新只落在副本，
    来源目录停在旧版本，照抄 ``Info.Path`` 会把副本正在用的新版本当孤儿）。副本还没
    建的脚本（升级后没打开过、新建未导入）退到来源目录——只用来算它会钉哪个
    maafw 版本，好在收割 / 回收时把那个版本保住；两边都没有的托管名下不可能有
    binding，不计入。
    """

    paths: list[str] = []
    for record in records:
        copy_dir = resolve_maafw_project_root(record.uid, None)
        if copy_dir.is_dir():
            paths.append(str(copy_dir))
            continue
        source = str(record.source_path or "").strip()
        if source and Path(source).is_dir():
            paths.append(source)
    return paths


def keep_project_paths(current: owners.LiveSnapshot) -> list[str]:
    """运行池对账的权威集合：仍在的托管的有效根（视图不在时退到来源目录），加上判定不了
    「已经不在」的视图。"""

    root = embedded_projects_root()
    views = classify_views(current, root)
    paths = collect_live_project_paths(
        record for record in current.records() if record.uid not in current.conflicts
    )
    listed = {Path(path).name for path in paths if Path(path).parent == root}
    paths.extend(str(root / name) for name in views.alive if name not in listed)
    paths.extend(str(root / name) for name in views.undetermined)
    return paths


def reconcile_in_background(
    reason: str,
    *,
    updated_project_path: str | Path | None = None,
    previous_version: str | None = None,
) -> None:
    """起一个守护线程跑一轮回收，调用方不等结果。

    删脚本、项目更新提交这类路径都不该被回收拖慢（解释器探针 + 可能的
    ``uv cache clean`` 要几秒）。给了 ``updated_project_path`` 就走
    ``reconcile_after_project_update``，把被替换掉的旧版本一并豁免宽限。

    权威集合在**调用方线程**（事件循环）上先算好：托管表只在事件循环上改，守护线程里
    去问属主会撞上「dict changed size」。托管没完整加载、或有属主答不上来时整轮跳过。
    """

    if not owners.managed_loaded():
        logger.warning(
            "脚本配置文件非空但没有加载出任何脚本，疑似损坏，跳过 MFW 运行池回收"
        )
        return
    current = owners.snapshot(require_ready=True)
    if current is None:
        logger.warning("MFW 托管属主的回答这次不算数，跳过 MFW 运行池回收")
        return
    project_paths = keep_project_paths(current)

    def _run() -> None:
        try:
            if updated_project_path is not None:
                reconcile_after_project_update(
                    project_paths,
                    updated_project_path,
                    previous_version,
                    reason=reason,
                )
            else:
                reconcile_runtime_pool(project_paths, reason=reason)
        except Exception:  # noqa: BLE001 - 后台维护，失败只记日志
            logger.opt(exception=True).warning(f"MFW 运行池后台回收失败（{reason}）")

    threading.Thread(
        target=_run, name=f"maafw-pool-reconcile:{reason}", daemon=True
    ).start()


__all__ = [
    "ViewClassification",
    "classify_views",
    "collect_live_project_paths",
    "keep_project_paths",
    "keep_view_paths",
    "reconcile_in_background",
]
