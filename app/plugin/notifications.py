"""插件消费的宿主通知契约；渠道、渲染和投递由宿主负责。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Literal, Protocol

from app.models.notification import DispatchResult, NotificationImage, NotifyPayload

if TYPE_CHECKING:
    from app.models.config import UserEntry


class NotificationService(Protocol):
    """插件提交内容和配置归属；宿主复用现有通知策略与发送流程。"""

    async def send_global(
        self,
        payload: NotifyPayload,
        *,
        include_system: bool = False,
        empty_policy: Literal["send", "warn", "skip"] = "send",
        system_timeout_seconds: int | None = None,
        attempts: int = 1,
        retry_delay: float = 0,
    ) -> DispatchResult: ...

    async def send_user(
        self,
        payload: NotifyPayload,
        user_config: UserEntry,
        *,
        attempts: int = 1,
        retry_delay: float = 0,
    ) -> DispatchResult: ...

    async def send_statistics(
        self,
        payload: NotifyPayload,
        user_config: UserEntry | None,
        *,
        global_empty_policy: Literal["send", "warn", "skip"] = "send",
        compact_summary: bool = False,
        attempts: int = 1,
        retry_delay: float = 0,
    ) -> DispatchResult: ...

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
    ) -> DispatchResult: ...
