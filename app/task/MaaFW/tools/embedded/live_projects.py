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

「哪些项目还在」要读脚本配置和项目副本（视图），归项目更新这一侧；算好的路径集合作为
普通数据交给 agent 环境一侧的 ``pool_reconcile`` 去对账回收。
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from pathlib import Path

from app.models.config import MaaFWConfig
from app.task.MaaFW.tools.embedded.embedded_project import resolve_maafw_project_root
from app.task.MaaFW.tools.embedded.pool_reconcile import (
    reconcile_after_project_update,
    reconcile_runtime_pool,
)
from app.utils import get_logger

# 与 ``pool_reconcile`` 同一个 logger 名：这几行原先就在那里记。
logger = get_logger("MFW 运行池回收")


def collect_live_project_paths(
    scripts: Iterable[tuple[str, MaaFWConfig]],
) -> list[str]:
    """当前配置里全部 MaaFW 类脚本的有效项目根（权威集合的输入）。

    lab（内嵌副本）口径：有效根永远是副本 ``data/mfw/<12hex>``（更新只落在副本，
    来源目录停在旧版本，照抄 ``Info.Path`` 会把副本正在用的新版本当孤儿）。副本还没
    建的脚本（升级后没打开过、新建未导入）退到来源目录——只用来算它会钉哪个
    maafw 版本，好在收割 / 回收时把那个版本保住；两边都没有的托管名下不可能有
    binding，不计入。
    """

    paths: list[str] = []
    for uid, config in scripts:
        copy_dir = resolve_maafw_project_root(str(uid), config)
        if copy_dir.is_dir():
            paths.append(str(copy_dir))
            continue
        source = str(config.Info.Path or "").strip()
        if source and Path(source).is_dir():
            paths.append(source)
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

    权威集合在**调用方线程**（事件循环）上先算好：``Config.ScriptConfig`` 只在
    事件循环上改，守护线程里去遍历它会撞上「dict changed size」。
    """

    from app.core import Config

    if not Config.script_config_loaded_intact():
        logger.warning(
            "脚本配置文件非空但没有加载出任何脚本，疑似损坏，跳过 MFW 运行池回收"
        )
        return
    project_paths = collect_live_project_paths(
        [
            (str(uid), config)
            for uid, config in Config.ScriptConfig.items()
            if isinstance(config, MaaFWConfig)
        ]
    )

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
    "collect_live_project_paths",
    "reconcile_in_background",
]
