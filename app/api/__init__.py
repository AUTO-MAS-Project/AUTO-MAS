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


from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import APIRouter

    from .core import router as core_router
    from .info import router as info_router
    from .scripts import router as scripts_router
    from .plan import router as plan_router
    from .emulator import router as emulator_router
    from .queue import router as queue_router
    from .dispatch import router as dispatch_router
    from .history import router as history_router
    from .tools import router as tools_router
    from .setting import router as setting_router
    from .update import router as update_router
    from .ocr import router as ocr_router
    from .plugins import router as plugins_router
    from .plugin_gateway import router as plugin_gateway_router
    from .scripts2 import router as scripts2_router
    from .script_types import router as script_types_router

    qr_login_router: APIRouter | None


_ROUTER_MODULES: dict[str, str] = {
    "core_router": ".core",
    "info_router": ".info",
    "scripts_router": ".scripts",
    "plan_router": ".plan",
    "emulator_router": ".emulator",
    "queue_router": ".queue",
    "dispatch_router": ".dispatch",
    "history_router": ".history",
    "tools_router": ".tools",
    "setting_router": ".setting",
    "update_router": ".update",
    "ocr_router": ".ocr",
    "plugins_router": ".plugins",
    "plugin_gateway_router": ".plugin_gateway",
    "scripts2_router": ".scripts2",
    "script_types_router": ".script_types",
}


def __getattr__(name: str):
    if name in _ROUTER_MODULES:
        import importlib
        module = importlib.import_module(_ROUTER_MODULES[name], __package__)
        return module.router
    if name == "qr_login_router":
        try:
            from .qr_login import router
            return router
        except ImportError:
            return None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
__all__ = [
    "core_router",
    "info_router",
    "scripts_router",
    "scripts2_router",
    "script_types_router",
    "plan_router",
    "emulator_router",
    "queue_router",
    "dispatch_router",
    "history_router",
    "tools_router",
    "setting_router",
    "update_router",
    "ocr_router",
    "plugins_router",
    "plugin_gateway_router",
    "qr_login_router",
]
