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
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from __future__ import annotations
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from fastapi import APIRouter

    from .core import router as core_router
    from .info import router as info_router
    from .scripts import router as scripts_router
    from .plan import router as plan_router
    from .games import router as games_router
    from .queue import router as queue_router
    from .dispatch import router as dispatch_router
    from .history import router as history_router
    from .tools import router as tools_router
    from .setting import router as setting_router
    from .update import router as update_router
    from .ocr import router as ocr_router
    from .plugin import router as plugin_router
    from .i18n import router as i18n_router

    qr_login_router: APIRouter | None


class OutBase(BaseModel):
    """所有 HTTP 响应共用的状态外壳；业务字段由各路由的子类补充。"""

    code: int = Field(default=200, description="状态码")
    status: str = Field(default="success", description="操作状态")
    message: str = Field(default="操作成功", description="操作消息")


_ROUTER_MODULES: dict[str, str] = {
    "core_router": ".core",
    "info_router": ".info",
    "scripts_router": ".scripts",
    "plan_router": ".plan",
    "games_router": ".games",
    "queue_router": ".queue",
    "dispatch_router": ".dispatch",
    "history_router": ".history",
    "tools_router": ".tools",
    "setting_router": ".setting",
    "update_router": ".update",
    "ocr_router": ".ocr",
    "plugin_router": ".plugin",
    "i18n_router": ".i18n",
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
    "OutBase",
    "core_router",
    "info_router",
    "scripts_router",
    "plan_router",
    "games_router",
    "queue_router",
    "dispatch_router",
    "history_router",
    "tools_router",
    "setting_router",
    "update_router",
    "ocr_router",
    "plugin_router",
    "i18n_router",
    "qr_login_router",
]
