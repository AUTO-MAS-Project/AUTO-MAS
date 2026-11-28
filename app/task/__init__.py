#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
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


from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .general import GeneralManager as GeneralManager
    from .HSR import HSRManager as HSRManager
    from .mode_worker import (
        MODE_WORKERS as MODE_WORKERS,
    )
    from .mode_worker import (
        AutoProxyWorker as AutoProxyWorker,
    )
    from .mode_worker import (
        ModeWorker as ModeWorker,
    )
    from .mode_worker import (
        ScriptConfigWorker as ScriptConfigWorker,
    )
    from .mode_worker import (
        ScriptViewWorker as ScriptViewWorker,
    )
    from .OkNte import OkNteManager as OkNteManager
    from .Okww import OkwwManager as OkwwManager
    from .user_expander import UserExpander as UserExpander

# 惰性导出（与 app/core/__init__.py 同一 idiom）：宿主启动少导入一批模块。
# 属性访问语义不变：`import app.task as task; task.MaaEndManager` 照常可用。
_LAZY_EXPORTS = {
    "UserExpander": (".user_expander", "UserExpander"),
    "ModeWorker": (".mode_worker", "ModeWorker"),
    "AutoProxyWorker": (".mode_worker", "AutoProxyWorker"),
    "ScriptConfigWorker": (".mode_worker", "ScriptConfigWorker"),
    "ScriptViewWorker": (".mode_worker", "ScriptViewWorker"),
    "MODE_WORKERS": (".mode_worker", "MODE_WORKERS"),
    "GeneralManager": (".general", "GeneralManager"),
    "OkwwManager": (".Okww", "OkwwManager"),
    "OkNteManager": (".OkNte", "OkNteManager"),
    "HSRManager": (".HSR", "HSRManager"),
    "ZzzOdManager": (".ZzzOd", "ZzzOdManager"),
}


def __getattr__(name: str):
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


__all__ = [
    "UserExpander",
    "ModeWorker",
    "AutoProxyWorker",
    "ScriptConfigWorker",
    "ScriptViewWorker",
    "MODE_WORKERS",
    "GeneralManager",
    "OkwwManager",
    "OkNteManager",
    "HSRManager",
    "ZzzOdManager",
]
