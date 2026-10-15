"""插件通知契约和消息类型；旧全局入口按需加载以保留兼容。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

from app.models.notification import (
    DispatchResult,
    NotificationImage,
    NotifyPayload,
    image_reference,
)
from app.plugin.notifications import NotificationService

if TYPE_CHECKING:
    from app.core.notify import (
        NotifyTarget,
        dispatch,
        dispatch_task_report,
        global_target,
        statistic_targets,
        user_target,
    )
    from app.task.notify_core import push_proxy_result

_LEGACY_EXPORTS = {
    "NotifyTarget": "app.core.notify",
    "dispatch": "app.core.notify",
    "dispatch_task_report": "app.core.notify",
    "global_target": "app.core.notify",
    "statistic_targets": "app.core.notify",
    "user_target": "app.core.notify",
    "push_proxy_result": "app.task.notify_core",
}


def __getattr__(name: str) -> Any:
    module_name = _LEGACY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


__all__ = [
    "DispatchResult",
    "NotifyTarget",
    "NotificationImage",
    "NotifyPayload",
    "dispatch",
    "dispatch_task_report",
    "global_target",
    "statistic_targets",
    "user_target",
    "image_reference",
    "push_proxy_result",
    "NotificationService",
]
