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

"""已迁移到 ok-script 插件的旧任务导入兼容层。"""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    """延迟暴露插件执行器，避免应用启动期加载可选插件包。"""

    if name.startswith("__"):
        raise AttributeError(name)
    try:
        from ok_script_adapter.adapter import autoproxy
    except ImportError as exc:
        raise RuntimeError(
            "旧 ok-script 执行器已迁移到 ok_script_adapter 插件，"
            "请启用该插件后再运行旧 OK-EF 配置"
        ) from exc
    return getattr(autoproxy, name)


def __dir__() -> list[str]:
    try:
        from ok_script_adapter.adapter import autoproxy
    except ImportError:
        return sorted(globals())
    return sorted({*globals(), *dir(autoproxy)})
