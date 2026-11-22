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
"""MaaEnd 用到的 MFW interface 解析代码，调用时才导入。

解析代码是已发布的库 ``maafw_interface``，不是宿主依赖：装了 MFW 插件才在插件环境里。导入 MaaEnd
不需要它，只有真正拼游戏启动设置时才要；它不在时抛 ``RuntimeError``，走 MaaEnd 现有的运行前失败提示。
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maafw_interface.embedded_labels import Labels, Translate
    from maafw_interface.interface.models import (
        MaaFWController,
        MaaFWInterface,
        MaaFWOption,
        MaaFWResource,
        MaaFWTaskOptionsByTask,
        MaaFWTaskOptionValue,
    )
    from maafw_interface.runner.models import MaaFWPretaskRunPlan

_LOADER = "maafw_interface.interface.loader"
_TASK_CONFIG = "maafw_interface.interface.task_config"
_RUN_PLAN = "maafw_interface.runner.run_plan"
_EMBEDDED_LABELS = "maafw_interface.embedded_labels"


def _module(name: str) -> ModuleType:
    try:
        return importlib.import_module(name)
    except ImportError as error:
        raise RuntimeError(
            "MaaEnd 的游戏启动设置要用 MFW 解析库 maafw_interface，当前没有装上："
            f"请在插件中心安装 MFW 插件（auto-mas-maafw-adapter）后重试（{error}）"
        ) from error


def load_interface_model(base_dir: str | Path) -> MaaFWInterface:
    return _module(_LOADER).load_interface_model(base_dir)


def build_task_option_maps(
    interface_model: MaaFWInterface,
) -> dict[str, dict[str, MaaFWOption]]:
    return _module(_TASK_CONFIG).build_task_option_maps(interface_model)


def normalize_task_options_by_task(
    raw_task_options: dict[str, Any] | None,
    task_ids: list[str],
    interface_model: MaaFWInterface,
    *,
    controller_name: str | None = None,
    resource_name: str | None = None,
) -> MaaFWTaskOptionsByTask:
    return _module(_TASK_CONFIG).normalize_task_options_by_task(
        raw_task_options,
        task_ids,
        interface_model,
        controller_name=controller_name,
        resource_name=resource_name,
    )


def select_resource(
    interface_model: MaaFWInterface,
    resource_name: str | None,
    controller: MaaFWController,
) -> MaaFWResource:
    return _module(_RUN_PLAN)._select_resource(
        interface_model, resource_name, controller
    )


def build_pretask_plans(
    base_dir: Path,
    interface_model: MaaFWInterface,
    controller: MaaFWController,
    resource: MaaFWResource,
    selected_ids: list[str],
    task_options: MaaFWTaskOptionsByTask,
    i18n_mapping: dict[str, Any],
) -> list[MaaFWPretaskRunPlan]:
    return _module(_RUN_PLAN)._build_pretask_plans(
        base_dir=base_dir,
        interface_model=interface_model,
        controller=controller,
        resource=resource,
        selected_ids=selected_ids,
        task_options=task_options,
        i18n_mapping=i18n_mapping,
    )


def labels(interface: MaaFWInterface, translate: Translate | None) -> Labels:
    return _module(_EMBEDDED_LABELS).Labels(interface, translate)


def mxu_option_values(
    option_values: Mapping[str, Any],
    option_map: Mapping[str, MaaFWOption],
    owner_prefix: str,
    labels: Labels,
    skipped: list[str],
) -> dict[str, MaaFWTaskOptionValue]:
    return _module(_EMBEDDED_LABELS).mxu_option_values(
        option_values, option_map, owner_prefix, labels, skipped
    )
