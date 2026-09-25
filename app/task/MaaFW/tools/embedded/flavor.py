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

引擎这一侧只做四件事：按需导入并缓存那个对象、在建运行计划前调一次
``decorate_selection``、在导入项目后用 ``matches_project`` 决定脚本类型、在模拟器启动后
调一次可选的游戏更新钩子。这里不出现任何具体专项的名字；专项自己的逻辑全在它自己的包里。

可选钩子 ``ensure_game_updated``（游戏客户端更新）的契约：

- **可选**：不写进 ``MaaFWFlavor`` 协议——``runtime_checkable`` 的协议会把缺它的特调判成
  不满足协议、整个退回通用 MaaFW。引擎用 ``resolve_game_update_hook`` 按 ``getattr`` 探测，
  没实现的特调与通用 MaaFW 行为完全不变。
- **何时调**：脚本 ``Run.GameUpdateMode`` 不是 ``Off``、特调实现了钩子、本次 controller 是
  ADB 时，在 MAS 启动模拟器（连带拉起游戏）之后、第一个任务下发之前，每个用户每次运行只调
  一次（重试重新开模拟器时不再调）。在事件循环里 ``await``，不在工作线程里。
- **签名**：``async def ensure_game_updated(self, *, script_config, resource_name,
  package_name, adb_path, adb_address, if_auto_install, progress) -> GameUpdateResult``。
  ``resource_name`` 是运行计划的资源名；``package_name`` 是这次随模拟器拉起的包名（空串
  表示没拉起游戏）；``adb_path`` 为 ``None`` 时由钩子自己回退系统 adb；``if_auto_install``
  对应 ``AutoInstall``（``Check`` 为 False）；``progress`` 是写用户运行日志的异步回调。
  返回 ``app.utils.game_apk.GameUpdateResult``。
- **结果**：``NeedManualUpdate`` → 本用户本次运行判失败，失败原因就是 ``message``，发错误
  通知，**不走重试**（客户端不更新，重试多少次都一样）；其余状态照常继续，``message`` 进日志。
- **异常**：钩子抛任何 ``Exception`` 都只记警告、照常继续，不能挡住代理；``CancelledError``
  （用户停止）必须照常向上传——钩子里的下载 / 安装都要能被取消打断，不能在线程里死等。
"""

from __future__ import annotations

import importlib
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

from app.task.MaaFW.tools.core.interface.models import MaaFWInterface
from app.utils import get_logger
from app.utils.game_apk import GameUpdateResult

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


GameUpdateHook = Callable[..., Awaitable[GameUpdateResult]]
"""特调可选的游戏更新钩子，契约见模块说明"""


def resolve_game_update_hook(script_config: Any) -> GameUpdateHook | None:
    """脚本对应特调的游戏更新钩子；通用 MaaFW 或特调没实现时返回 None。"""

    flavor = resolve_flavor(script_config)
    hook = getattr(flavor, "ensure_game_updated", None) if flavor is not None else None
    return hook if callable(hook) else None


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
    "GameUpdateHook",
    "MaaFWFlavor",
    "decide_project_config_class",
    "flavored_config_classes",
    "resolve_flavor",
    "resolve_game_update_hook",
    "user_config_type_transform",
]
