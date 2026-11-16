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

"""从 Config 指定的资源目录读取内置通知模板，共享渲染环境。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import cache
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from app.core import Config
from app.models.notification import DeferredContent, NotificationContentError

if TYPE_CHECKING:
    from jinja2 import Environment, Template


@cache
def _notification_environment() -> Environment:
    from jinja2 import Environment, FileSystemLoader

    return Environment(loader=FileSystemLoader(str(Config.resource_path / "html")))


def get_notification_template(name: str) -> Template:
    """读取内置通知模板，沿用 Jinja 默认缓存与渲染设置。"""
    return _notification_environment().get_template(name)


def deferred_notification_template(
    name: str, context: Mapping[str, object]
) -> DeferredContent[str]:
    """固定模板数据，在目标选择 HTML 时才读取模板并渲染。"""

    error_type = None
    try:
        snapshot = _snapshot_template_context(context)
    except Exception as exc:
        snapshot = {}
        error_type = type(exc).__name__

    def render() -> str:
        if error_type is not None:
            raise NotificationContentError(error_type)
        return get_notification_template(name).render(snapshot)

    def prepare() -> Callable[[], str]:
        if error_type is not None:
            raise NotificationContentError(error_type)
        template = get_notification_template(name)
        return lambda: template.render(snapshot)

    return DeferredContent(render, prepare_factory=prepare)


def _snapshot_template_context(context: Mapping[str, object]) -> dict[str, object]:
    """复制普通容器及只读字典；不透明扩展保持原有 Jinja 渲染语义。"""

    memo: dict[int, object] = {}

    def snapshot(value: object) -> object:
        if id(value) in memo:
            return memo[id(value)]
        if type(value) is dict or isinstance(value, MappingProxyType):
            copied: dict[object, object] = {}
            memo[id(value)] = copied
            copied.update((key, snapshot(item)) for key, item in value.items())
            return copied
        if type(value) is list:
            items: list[object] = []
            memo[id(value)] = items
            items.extend(snapshot(item) for item in value)
            return items
        if type(value) is tuple:
            # 元组可经列表间接引用自身，递归中可能已登记最终元组。
            items_tuple = tuple(snapshot(item) for item in value)
            return memo.setdefault(id(value), items_tuple)
        return value

    return cast(dict[str, object], snapshot(dict(context)))
