#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""读 MSS 项目根目录的 ``interface.json``，整理出任务清单与选项定义。

复用 MaaFW 的通用 Project Interface V2 加载器
（``app/task/MaaFW/tools/core/automas_maafw_interface/loader.load_interface_model``）：
它已经是纯解析、零宿主耦合的既有实现，会递归展开 ``import`` 片段。MSS 侧
**不再自己解析 JSON**，也不去读上游的私有资源文件——只把 PI V2 的公开字段
（``name`` / ``entry`` / ``option`` / ``cases`` / ``inputs``）整理成列表，
供任务队列界面与实例配置改写使用。

实测样本（MSS v1.1.0，``D:\\jiao_ben\\maa\\mss``）：13 个任务、40 个选项、
选项类型只有 ``input`` 与 ``select``，选项定义与任务定义都拆在
``resource/tasks/*.json`` 里由 ``import`` 引入。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.task.MaaFW.tools.core.automas_maafw_interface.loader import (
    load_interface_model,
)
from app.task.MaaFW.tools.core.automas_maafw_interface.models import MaaFWInterface
from app.utils import get_logger

from .instance_config import build_default_option_items

logger = get_logger("MSS 任务清单")

## PI V2 清单文件名（在 MSS 根目录下）
INTERFACE_NAME = "interface.json"


def _normalize_document(value: Any) -> str:
    """把 PI V2 的文档字段（``str | list[str]``）折成一段文本。

    Args:
        value: ``description`` / ``desc`` / ``doc`` 之一。

    Returns:
        str: 文本；无法识别时为空串。
    """

    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(str(item) for item in value if str(item).strip())
    return ""


@dataclass(slots=True)
class MssTaskCatalog:
    """MSS 的任务清单与选项定义（由 PI V2 ``interface.json`` 整理而来）。

    Attributes:
        name: 项目名（``interface.json`` 的 ``name``）。
        version: 项目版本（``interface.json`` 的 ``version``，可能为空）。
        tasks: 任务列表，元素为 ``{name, entry, description, option: [选项名]}``。
        options: 选项名 → ``{type, label, default_case, cases, inputs}``。
    """

    name: str
    version: str
    tasks: list[dict[str, Any]] = field(default_factory=list)
    options: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def task_count(self) -> int:
        """任务数量。"""

        return len(self.tasks)

    @property
    def option_count(self) -> int:
        """选项定义数量。"""

        return len(self.options)

    def _index(self) -> dict[str, dict[str, Any]]:
        """按 entry 与显示名建立任务索引（entry 优先）。"""

        index: dict[str, dict[str, Any]] = {}
        for task in self.tasks:
            name = str(task.get("name") or "")
            entry = str(task.get("entry") or "")
            if name:
                index.setdefault(name, task)
            if entry:
                index[entry] = task
        return index

    def find_task(self, key: str) -> dict[str, Any] | None:
        """按 entry 或显示名查任务定义。

        Args:
            key: 任务 entry 或显示名。

        Returns:
            dict[str, Any] | None: 任务定义；找不到返回 None。
        """

        return self._index().get(str(key or "").strip())

    def option_names(self, key: str) -> list[str]:
        """取某个任务的选项名列表。

        Args:
            key: 任务 entry 或显示名。

        Returns:
            list[str]: 选项名；任务不存在时为空列表。
        """

        task = self.find_task(key)
        if task is None:
            return []
        return [str(name) for name in (task.get("option") or []) if str(name).strip()]

    def task_definitions(self) -> dict[str, dict[str, Any]]:
        """导出「entry / 显示名 → 任务定义」的索引（供实例配置改写使用）。

        Returns:
            dict[str, dict[str, Any]]: 任务定义索引。
        """

        return self._index()

    def available_tasks(self) -> list[dict[str, Any]]:
        """导出可下发给用户配置 ``Task.AvailableTasks`` 的任务清单。

        形状与用户队列项对齐（``name`` / ``entry`` / ``description`` /
        ``option``），前端可以直接拿来渲染任务勾选表。

        Returns:
            list[dict[str, Any]]: 任务清单。
        """

        return [
            {
                "name": task.get("name", ""),
                "entry": task.get("entry", ""),
                "description": task.get("description", ""),
                "option": list(task.get("option") or []),
            }
            for task in self.tasks
        ]

    def build_option_items(self, key: str) -> list[dict[str, Any]]:
        """按任务定义生成一份默认选项项（``select`` 写 index，``input`` 写 data）。

        Args:
            key: 任务 entry 或显示名。

        Returns:
            list[dict[str, Any]]: 默认选项项列表。
        """

        return build_default_option_items(self.option_names(key), self.options)


def _build_catalog(interface: MaaFWInterface) -> MssTaskCatalog:
    """把 ``MaaFWInterface`` 整理成 :class:`MssTaskCatalog`。

    Args:
        interface: 通用 PI V2 加载器的解析结果。

    Returns:
        MssTaskCatalog: MSS 任务清单。
    """

    tasks: list[dict[str, Any]] = []
    for task in interface.task:
        description = _normalize_document(task.description)
        if not description:
            description = _normalize_document(task.desc) or _normalize_document(
                task.doc
            )
        tasks.append(
            {
                "name": task.name,
                "entry": task.entry,
                "description": description,
                "option": [
                    str(name) for name in (task.option or []) if str(name).strip()
                ],
            }
        )

    options: dict[str, dict[str, Any]] = {}
    for name, option in interface.option.items():
        definition: dict[str, Any] = {"type": option.type}
        if option.label:
            definition["label"] = option.label
        if option.default_case is not None:
            definition["default_case"] = option.default_case
        cases = [
            {
                "name": case.name,
                "label": case.label,
                "option": [str(sub) for sub in (case.option or []) if str(sub).strip()],
            }
            for case in (option.cases or [])
        ]
        if cases:
            definition["cases"] = cases
        inputs = [
            {
                "name": input_case.name,
                "default": input_case.default,
                "pipeline_type": input_case.pipeline_type,
            }
            for input_case in (option.inputs or [])
        ]
        if inputs:
            definition["inputs"] = inputs
        options[name] = definition

    return MssTaskCatalog(
        name=str(interface.name or ""),
        version=str(interface.version or ""),
        tasks=tasks,
        options=options,
    )


def load_task_catalog(root: str | Path) -> MssTaskCatalog:
    """读 MSS 根目录的 ``interface.json`` 得到任务清单。

    纯解析、无缓存：MSS 一次任务只加载一次，13 个碎片文件的解析开销可以忽略；
    加缓存反而要在上游发新版本后处理失效。

    Args:
        root: MSS 根目录（含 ``interface.json``）。

    Returns:
        MssTaskCatalog: 任务清单与选项定义。

    Raises:
        MaaFWInterfaceLoadError: 目录或清单不可用时（错误消息可直接展示给用户）。
    """

    interface = load_interface_model(root)
    catalog = _build_catalog(interface)
    logger.info(
        f"已读取 MSS 任务清单: {catalog.name} {catalog.version} - "
        f"任务 {catalog.task_count} 个, 选项 {catalog.option_count} 个"
    )
    return catalog


def load_task_catalog_or_error(root: str | Path) -> tuple[MssTaskCatalog | None, str]:
    """宽容版加载：把加载失败折成一句可展示的错误文案。

    Args:
        root: MSS 根目录。

    Returns:
        tuple[MssTaskCatalog | None, str]: ``(清单, 错误文案)``；成功时错误文案为空串。
    """

    try:
        return load_task_catalog(root), ""
    except Exception as e:
        logger.opt(exception=True).warning(f"读取 MSS 任务清单失败: {e}")
        return None, f"读取 MSS 任务清单失败: {e}"


def interface_exists(root: str | Path) -> bool:
    """判断根目录下是否存在 ``interface.json``。

    Args:
        root: MSS 根目录。

    Returns:
        bool: 文件存在时为真；内容是否可解析由 :func:`load_task_catalog` 负责。
    """

    return (Path(root) / INTERFACE_NAME).is_file()
