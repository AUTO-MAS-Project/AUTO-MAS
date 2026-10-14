"""插件通知能力的宿主实现；复用现有目标选择与通知编排。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Literal

from app.models.notification import DispatchResult, NotificationImage, NotifyPayload

if TYPE_CHECKING:
    from app.models.config import UserEntry


class HostNotifications:
    """运行时解析宿主入口，避免加载插件管理器时提前初始化通知服务。"""

    async def send_global(
        self,
        payload: NotifyPayload,
        *,
        include_system: bool = False,
        empty_policy: Literal["send", "warn", "skip"] = "send",
        system_timeout_seconds: int | None = None,
        attempts: int = 1,
        retry_delay: float = 0,
    ) -> DispatchResult:
        from app.core import notify

        return await notify.dispatch(
            payload,
            [
                notify.global_target(
                    include_system=include_system,
                    empty_policy=empty_policy,
                    system_timeout_seconds=system_timeout_seconds,
                )
            ],
            attempts=attempts,
            retry_delay=retry_delay,
        )

    async def send_user(
        self,
        payload: NotifyPayload,
        user_config: UserEntry,
        *,
        attempts: int = 1,
        retry_delay: float = 0,
    ) -> DispatchResult:
        from app.core import notify

        return await notify.dispatch(
            payload,
            [notify.user_target(user_config)],
            attempts=attempts,
            retry_delay=retry_delay,
        )

    async def send_statistics(
        self,
        payload: NotifyPayload,
        user_config: UserEntry | None,
        *,
        global_empty_policy: Literal["send", "warn", "skip"] = "send",
        compact_summary: bool = False,
        attempts: int = 1,
        retry_delay: float = 0,
    ) -> DispatchResult:
        from app.core import notify

        return await notify.dispatch(
            payload,
            notify.statistic_targets(
                user_config,
                global_empty_policy=global_empty_policy,
                compact_summary=compact_summary,
            ),
            attempts=attempts,
            retry_delay=retry_delay,
        )

    async def push_proxy_result(
        self,
        *,
        title: str,
        message: dict,
        task_info: object | None = None,
        result_template: str = "general_result.html",
        signature_sep: str = "\n\n",
        logger: Any | None = None,
        skip_debug_message: str | None = None,
        images: Sequence[NotificationImage] = (),
        include_system: bool = True,
    ) -> DispatchResult:
        from app.task.notify_core import push_proxy_result

        return await push_proxy_result(
            title=title,
            message=message,
            task_info=task_info,
            result_template=result_template,
            signature_sep=signature_sep,
            logger=logger,
            skip_debug_message=skip_debug_message,
            images=images,
            include_system=include_system,
        )
