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

"""已迁移到 ok-script 插件的旧 Provider 导入兼容层。"""

from __future__ import annotations

from typing import Any

from .._plugin_compat import get_plugin_attribute, get_plugin_dir


_TARGET_MODULE = "ok_script_adapter.common.provider"


def __getattr__(name: str) -> Any:
    return get_plugin_attribute(_TARGET_MODULE, name)


def __dir__() -> list[str]:
    return sorted({*globals(), *get_plugin_dir(_TARGET_MODULE)})
