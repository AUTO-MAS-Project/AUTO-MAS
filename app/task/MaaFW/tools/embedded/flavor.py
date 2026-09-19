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

"""特调类型钩子：MaaFW 引擎认识的唯一一种"专项差异"。

某些 MaaFW 项目值得给一个自己的脚本类型（图标、创建卡、默认名，以及一点点运行前的
队列装饰——比如 M9A 的首尾任务与切号绑定）。这些类型是 ``MaaFWConfig`` 的同形子类，
用类属性 ``FLAVOR = "模块路径:属性名"`` 指向一个满足 ``MaaFWFlavor`` 协议的对象。

引擎这一侧只做三件事：按需导入并缓存那个对象、在建运行计划前调一次
``decorate_selection``、在导入项目后用 ``matches_project`` 决定脚本类型。这里不出现任何
具体专项的名字；专项自己的逻辑全在它自己的包里。
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from app.task.MaaFW.tools.core.automas_maafw_interface.models import MaaFWInterface
from app.utils import get_logger

logger = get_logger("MaaFW 特调")

_FLAVOR_CACHE: dict[str, Any] = {}


@runtime_checkable
class MaaFWFlavor(Protocol):
    """一个特调类型要提供的全部东西。"""

    type_key: str
    """脚本类型键（``CLASS_BOOK`` 的键），日志与通知里用。"""

    def matches_project(self, interface_model: MaaFWInterface) -> bool:
        """这个 interface 是不是本特调对应的项目（导入后据此决定脚本类型）。"""

    def decorate_selection(
        self,
        interface_model: MaaFWInterface,
        task_ids: list[str],
        task_options: dict[str, Any],
        *,
        script_config: Any,
        user_config: Any,
        resource_name: str | None,
        send_log: Callable[[str], None] | None,
    ) -> tuple[list[str], dict[str, Any]]:
        """在用户勾选的任务实例列表上做装饰，返回新的列表与选项。"""


def _load_flavor(spec: str) -> Any | None:
    if spec in _FLAVOR_CACHE:
        return _FLAVOR_CACHE[spec]
    module_name, _, attribute = spec.partition(":")
    try:
        flavor = getattr(importlib.import_module(module_name), attribute or "FLAVOR")
    except Exception as exc:  # noqa: BLE001 - 特调加载失败只能退回通用行为
        logger.warning(f"MaaFW 特调 {spec} 加载失败，按通用 MaaFW 处理：{exc}")
        flavor = None
    if flavor is not None and not isinstance(flavor, MaaFWFlavor):
        logger.warning(f"MaaFW 特调 {spec} 不满足协议，按通用 MaaFW 处理")
        flavor = None
    _FLAVOR_CACHE[spec] = flavor
    return flavor


def resolve_flavor(script_config: Any) -> MaaFWFlavor | None:
    """脚本配置对应的特调对象；通用 MaaFW（``FLAVOR`` 为 None）返回 None。"""

    spec = getattr(type(script_config), "FLAVOR", None)
    if not spec:
        return None
    return _load_flavor(str(spec))


def flavored_config_classes() -> list[tuple[type, MaaFWFlavor]]:
    """``CLASS_BOOK`` 里所有声明了特调的 MaaFW 子类，按登记顺序。"""

    from app.models.config import CLASS_BOOK, MaaFWConfig

    found: list[tuple[type, MaaFWFlavor]] = []
    for config_class in CLASS_BOOK.values():
        if not (
            isinstance(config_class, type) and issubclass(config_class, MaaFWConfig)
        ):
            continue
        spec = getattr(config_class, "FLAVOR", None)
        if not spec:
            continue
        flavor = _load_flavor(str(spec))
        if flavor is not None:
            found.append((config_class, flavor))
    return found


def decide_project_config_class(interface_model: MaaFWInterface) -> type:
    """按项目决定脚本类型：第一个认领它的特调，否则通用 ``MaaFWConfig``。"""

    from app.models.config import MaaFWConfig

    for config_class, flavor in flavored_config_classes():
        try:
            if flavor.matches_project(interface_model):
                return config_class
        except Exception as exc:  # noqa: BLE001 - 识别失败不该挡住导入
            logger.warning(f"MaaFW 特调 {flavor.type_key} 识别项目失败：{exc}")
    return MaaFWConfig


def user_config_type_transform(config_class: type) -> Callable[[dict], dict]:
    """``MultipleConfig.retype`` 用的字典改写：把用户子配置的类型名换成新脚本类的用户类。"""

    user_type_name = config_class.USER_CONFIG_CLASS.__name__

    def transform(payload: dict) -> dict:
        # ConfigBase.toDict 把子配置放在 SubConfigsInfo 下，用户表是其中的 UserData。
        user_data = (payload.get("SubConfigsInfo") or {}).get("UserData")
        if isinstance(user_data, dict):
            for instance in user_data.get("instances") or []:
                if isinstance(instance, dict):
                    instance["type"] = user_type_name
        return payload

    return transform


__all__ = [
    "MaaFWFlavor",
    "decide_project_config_class",
    "flavored_config_classes",
    "resolve_flavor",
    "user_config_type_transform",
]
