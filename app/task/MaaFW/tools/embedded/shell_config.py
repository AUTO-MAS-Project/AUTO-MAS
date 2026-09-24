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

#   Contact: DLmaster_361@163.com

"""把 MFAAvalonia 外壳里的实例配置翻译成 MAS 的任务队列。

内嵌运行不需要外壳，但用户此前多半是在外壳里把任务和选项配好的。这里只读外壳的
文件、把它翻译成 MAS 的任务队列，供用户页「导入配置」一次性搬过来；翻译完之后
MAS 不再依赖外壳，写盘由调用方按 MAS 自己的用户配置走。

外壳配置的形状（实测自 MaaStellaSora 发行包）：

- ``<根>/appsettings.json``：``Instances.List`` 是逗号分隔的实例 ID 列表，
  ``Instances.Order`` 是显示顺序，``Instances.LastActive`` / ``LastActiveName``
  指出当前激活的是哪一个；
- ``<根>/config/instances/<实例ID>.json``：``CurrentTasks`` 是勾选与顺序，元素形如
  ``"任务名<|||>入口"``；``TaskItems[]`` 每项有 ``name`` 与 ``option[]``。

选项值的两种写法都要照顾到（外壳按 MaaFramework 的语义落盘，与 PI v2 的选项类型对应）：

- ``select`` / ``scan_select`` / ``switch``：存 cases **下标**，翻回 case 名；
  ``switch`` 也有写成布尔的情况（``true`` 就是 ``Yes``）；
- ``input``：存 ``{输入名: 值}``，原样带走；
- ``switch`` 另一个分支带出的子选项挂在 ``sub_options`` 里，与 MAS 一样是平铺的。

读不到的键一律当没有，坏掉的任务名 / 选项名只记进 ``skipped``，不猜着写。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.task.MaaFW.tools.core.interface.models import MaaFWInterface, MaaFWOption
from app.utils import get_logger
from app.utils.io import read_file

logger = get_logger("MaaFW 外壳配置")

## 外壳全局设置与实例配置目录（相对项目根）
APP_SETTINGS_NAME = "appsettings.json"
INSTANCE_DIR_RELATIVE = ("config", "instances")
INSTANCE_SUFFIX = ".json"
## 实例 ID 列表所在的键；分隔符实测为逗号
INSTANCES_LIST_KEY = "Instances.List"
INSTANCES_ORDER_KEY = "Instances.Order"
INSTANCES_ACTIVE_KEY = "Instances.LastActive"
## 实例配置文件里承载任务与选项的两个键
KEY_CURRENT_TASKS = "CurrentTasks"
KEY_TASK_ITEMS = "TaskItems"
## ``CurrentTasks`` 元素的连接符号，由外壳自己定义（实测形如 "登录游戏<|||>登录_登录"）
TASK_SEPARATOR = "<|||>"
## switch 写成布尔时的取值
SWITCH_ON = "Yes"
SWITCH_OFF = "No"


def shell_instance_dir(root: Path) -> Path:
    """返回外壳的实例配置目录（``<根>/config/instances``），不保证存在。"""

    return root.joinpath(*INSTANCE_DIR_RELATIVE)


def _instance_ids_from_settings(root: Path) -> tuple[list[str], str]:
    """读 ``appsettings.json``：返回（实例 ID 列表, 当前激活的实例 ID）。"""

    settings = read_file(root / APP_SETTINGS_NAME)
    if not isinstance(settings, dict):
        return [], ""

    raw_list = str(settings.get(INSTANCES_LIST_KEY) or "")
    raw_order = str(settings.get(INSTANCES_ORDER_KEY) or "")
    ids: list[str] = []
    ## 分隔符没有官方说明（实测样本是逗号），常见几种都切开
    for raw in (raw_order, raw_list):
        for token in raw.replace("|", ",").replace(";", ",").split(","):
            instance_id = token.strip()
            if instance_id and instance_id not in {".", ".."} and instance_id not in ids:
                ids.append(instance_id)
    return ids, str(settings.get(INSTANCES_ACTIVE_KEY) or "").strip()


def _read_instance_file(path: Path) -> dict[str, Any]:
    """读一个实例配置文件；不存在、解析不了、根不是映射都返回空字典。"""

    data = read_file(path)
    if not isinstance(data, dict):
        if path.exists():
            logger.warning("外壳实例配置不是映射，已跳过：%s", path)
        return {}
    return data


def list_shell_instances(root: Path) -> list[dict[str, Any]]:
    """列出外壳里可以导入的实例配置。

    ``appsettings.json`` 只用来定顺序和当前激活项；目录里多出来的 ``*.json`` 也列进来，
    否则用户在设置里手删过实例列表时会看不到自己的配置。

    Args:
        root: 外壳项目根目录（脚本配置里的项目来源目录）。

    Returns:
        list[dict[str, Any]]: 每项 ``{id, name, taskCount, active}``，按外壳顺序排列。
    """

    directory = shell_instance_dir(root)
    if not directory.is_dir():
        return []

    ids, active_id = _instance_ids_from_settings(root)
    found = {
        path.stem
        for path in directory.glob(f"*{INSTANCE_SUFFIX}")
        if path.is_file() and path.stem
    }
    ordered = [instance_id for instance_id in ids if instance_id in found]
    ordered.extend(sorted(found - set(ordered)))

    instances: list[dict[str, Any]] = []
    for instance_id in ordered:
        data = _read_instance_file(directory / f"{instance_id}{INSTANCE_SUFFIX}")
        raw_tasks = data.get(KEY_CURRENT_TASKS)
        task_count = len(raw_tasks) if isinstance(raw_tasks, list) else 0
        instances.append(
            {
                "id": instance_id,
                "name": instance_id,
                "taskCount": task_count,
                "active": instance_id == active_id,
            }
        )
    return instances


def _is_index(value: Any) -> bool:
    """外壳写 select 时的 cases 下标：整数，或纯数字字符串（布尔不算）。"""

    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, str) and value.strip().lstrip("-").isdigit()


def _translate_option_value(
    value: Any, definition: MaaFWOption | None
) -> tuple[bool, Any]:
    """翻译单个选项值；返回（是否认得, 值）。

    ``select`` 一类的下标翻不回 case 名时返回 ``False``，由调用方记进 skipped——
    宁可不带这一项，也不要给 MaaFW 下发一个它认不出的值。
    """

    if definition is not None and definition.cases and _is_index(value):
        cases = [case.name for case in definition.cases]
        index = int(str(value).strip())
        if 0 <= index < len(cases):
            return True, cases[index]
        return False, None

    ## switch 在外壳里可能落成布尔
    if isinstance(value, bool):
        return True, SWITCH_ON if value else SWITCH_OFF

    return True, value


def _translate_options(
    raw_options: Any, option_book: dict[str, MaaFWOption]
) -> tuple[dict[str, Any], list[str]]:
    """把 ``TaskItems[].option[]`` 翻成 MAS 的 ``{选项名: 值}``。"""

    if not isinstance(raw_options, list):
        return {}, []

    result: dict[str, Any] = {}
    skipped: list[str] = []
    for option in raw_options:
        if not isinstance(option, dict):
            continue
        name = str(option.get("name") or "").strip()
        if name:
            known, value = _translate_option_value(
                option.get("value"), option_book.get(name)
            )
            if known:
                result[name] = value
            else:
                skipped.append(name)
        ## switch 另一个分支带出的子选项，MAS 这一侧与父选项平铺
        for sub in option.get("sub_options") or []:
            if not isinstance(sub, dict):
                continue
            sub_name = str(sub.get("name") or "").strip()
            if not sub_name:
                continue
            known, value = _translate_option_value(
                sub.get("value"), option_book.get(sub_name)
            )
            if known:
                result[sub_name] = value
            else:
                skipped.append(sub_name)
    return result, skipped


def read_shell_selection(
    root: Path, instance_id: str, interface_model: MaaFWInterface
) -> dict[str, Any]:
    """读一个外壳实例，返回 MAS 要的任务队列。

    Args:
        root: 外壳项目根目录。
        instance_id: 实例 ID（``list_shell_instances`` 给的那个）。
        interface_model: 当前项目的 interface，用来校验任务名并把下标翻成 case 名。

    Returns:
        dict[str, Any]: ``{"tasks": [{"name", "options"}], "skipped": [...]}``；
        项目里没有的任务整个丢掉并记进 ``skipped``。

    Raises:
        FileNotFoundError: 实例配置文件不存在。
    """

    path = shell_instance_dir(root) / f"{instance_id}{INSTANCE_SUFFIX}"
    if not path.is_file():
        raise FileNotFoundError(f"外壳实例配置不存在：{path}")

    data = _read_instance_file(path)
    raw_tasks = data.get(KEY_CURRENT_TASKS)
    if not isinstance(raw_tasks, list):
        raw_tasks = []
    raw_items = data.get(KEY_TASK_ITEMS)
    if not isinstance(raw_items, list):
        raw_items = []

    ## 选项按任务名索引；同名任务在外壳里只有一份配置
    options_by_task: dict[str, Any] = {}
    for item in raw_items:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if name and name not in options_by_task:
                options_by_task[name] = item.get("option")

    option_book = interface_model.option or {}
    valid_names = {task.name for task in interface_model.task}

    tasks: list[dict[str, Any]] = []
    skipped: list[str] = []
    seen: set[str] = set()
    for raw in raw_tasks:
        ## "任务名<|||>入口"：入口部分只对外壳有意义，MAS 按任务名定位
        name = str(raw).split(TASK_SEPARATOR, 1)[0].strip()
        if not name:
            continue
        ## 外壳里同一个任务可以挂多个入口（实测「活动快速战斗」有两条），按任务名去重
        if name in seen:
            continue
        seen.add(name)
        if name not in valid_names:
            skipped.append(name)
            continue
        options, dropped = _translate_options(
            options_by_task.get(name), option_book
        )
        skipped.extend(dropped)
        tasks.append({"name": name, "options": options})

    return {"tasks": tasks, "skipped": skipped}


__all__ = [
    "TASK_SEPARATOR",
    "list_shell_instances",
    "read_shell_selection",
    "shell_instance_dir",
]
