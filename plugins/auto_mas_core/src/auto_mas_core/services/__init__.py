"""再导出宿主 ``app.services``（整包；与 ``auto_mas_core.plugin.services`` 路径区分）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services import Matomo, Notify, System, Updater

__all__ = ["Matomo", "Notify", "System", "Updater"]


def __getattr__(name: str) -> Any:
    import app.services as host_services

    return getattr(host_services, name)


def __dir__() -> list[str]:
    return list(__all__)
