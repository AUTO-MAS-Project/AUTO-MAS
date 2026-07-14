#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""已迁移 OK 运行模块的惰性兼容转发工具。"""

from __future__ import annotations

from importlib import import_module
from typing import Any


def get_plugin_attribute(target_module: str, name: str) -> Any:
    """按旧模块属性名延迟读取插件实现。"""

    try:
        module = import_module(target_module)
    except ImportError as exc:
        raise RuntimeError(
            "旧 ok-script 运行模块已迁移到 ok_script_adapter 插件，请启用该插件"
        ) from exc
    return getattr(module, name)


def get_plugin_dir(target_module: str) -> list[str]:
    """返回旧模块可见的插件属性，供交互和诊断使用。"""

    try:
        return dir(import_module(target_module))
    except ImportError:
        return []
