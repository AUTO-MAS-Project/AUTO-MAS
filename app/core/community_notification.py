"""独立社区通知编排及装配，后台通知由运行时注册表持有。"""

import asyncio
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass
from functools import partial
from typing import Any

from app.core.config import Config
from app.core.notification_report import (
    NOTIFICATION_FAST_PATH_WAIT_SECONDS,
    NOTIFICATION_RETRY_DELAY_SECONDS,
    NOTIFICATION_SEND_ATTEMPTS,
    CommunityFailureReporter,
)
from app.core.notify import dispatch, global_target
from app.models.notification import NotifyPayload
from app.models.notification_channel import DispatchResult, NotifyTarget
from app.models.notification_report import NotificationDispatcher
from app.runtime_tasks import RuntimeTasks
from app.services.community_notification import (
    build_community_notification_payload,
    filter_community_notification_results,
)
from app.utils import get_logger

logger = get_logger("社区通知")


@dataclass(frozen=True)
class CommunityNotificationDependencies:
    dispatch: NotificationDispatcher
    prepare_targets: Callable[[], tuple[NotifyTarget, ...]]
    render: Callable[[list[dict[str, object]]], NotifyPayload]
    enabled: Callable[[], bool]
    report_failure: CommunityFailureReporter
    spawn: Callable[[Coroutine[Any, Any, list[str]]], asyncio.Task[list[str]] | None]
    fast_path_seconds: float


class CommunityNotificationCoordinator:
    def __init__(self, dependencies: CommunityNotificationDependencies) -> None:
        self.dependencies = dependencies
        self._pending: set[asyncio.Task[list[str]]] = set()

    async def dispatch(
        self,
        results: list[dict[str, object]],
        *,
        targets: Iterable[NotifyTarget] | None = None,
        skip_channel_ids: Iterable[str] = (),
        completion_notice: str = "",
    ) -> DispatchResult:
        results = filter_community_notification_results(results)
        if not results and not completion_notice:
            return DispatchResult()
        payload = (
            self.dependencies.render(results)
            if results
            else NotifyPayload(title="社区签到执行结束", text=completion_notice)
        )
        return await self.dependencies.dispatch(
            payload,
            tuple(targets)
            if targets is not None
            else self.dependencies.prepare_targets(),
            attempts=NOTIFICATION_SEND_ATTEMPTS,
            retry_delay=NOTIFICATION_RETRY_DELAY_SECONDS,
            skip_channel_ids=skip_channel_ids,
        )

    async def _send(self, results: list[dict[str, object]]) -> list[str]:
        result = await self.dispatch(results)
        if result.failed:
            await self.dependencies.report_failure(result, results_saved=bool(results))
        return list(result.failed)

    async def send(self, results: list[dict[str, object]]) -> list[str]:
        if not self.dependencies.enabled():
            return []
        return await self._send(results)

    def _completed(self, task: asyncio.Task[list[str]]) -> None:
        self._pending.discard(task)
        if task.cancelled():
            return
        try:
            failed = task.result()
        except Exception as exc:
            logger.warning(f"后台社区通知发送失败: {type(exc).__name__}")
        else:
            if failed:
                logger.warning(f"后台社区通知部分失败: {'、'.join(failed)}")

    async def submit(self, results: list[dict[str, object]]) -> list[str] | None:
        """短暂等待渠道结果；超时和请求取消均保留已注册的后台通知。"""

        if not self.dependencies.enabled():
            return []
        task = self.dependencies.spawn(self._send(results))
        if task is None:
            return ["通知服务"]
        self._pending.add(task)
        task.add_done_callback(self._completed)
        try:
            return await asyncio.wait_for(
                asyncio.shield(task), timeout=self.dependencies.fast_path_seconds
            )
        except asyncio.TimeoutError:
            logger.info("等待窗口内未返回，通知渠道仍在后台发送")
            return None
        except Exception as exc:
            logger.warning(f"社区通知服务异常: {type(exc).__name__}")
            return ["通知服务"]

    async def drain(self, timeout: float) -> bool:
        deadline = asyncio.get_running_loop().time() + timeout
        while pending := {task for task in self._pending if not task.done()}:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return False
            _, waiting = await asyncio.wait(pending, timeout=remaining)
            if waiting:
                return False
        return True


def _community_notification_enabled() -> bool:
    return Config.ToolsConfig.GameSign.NotifyEnabled


def _community_notification_targets() -> tuple[NotifyTarget, ...]:
    return (global_target(include_system=True),)


async def report_community_notification_failure(
    failed_channels: list[str], *, results_saved: bool = True
) -> None:
    await Config.push_system_notice(
        level="warning",
        title="游戏社区通知发送不完整",
        lines=[
            f"发送失败的渠道：{'、'.join(failed_channels)}",
            (
                "签到结果已保存，请检查这些渠道的通知配置后重试。"
                if results_saved
                else "请检查这些渠道的通知配置后重试。"
            ),
        ],
    )


async def _report_failure(result: DispatchResult, *, results_saved: bool) -> None:
    await report_community_notification_failure(
        list(result.failed), results_saved=results_saved
    )


_COMMUNITY_NOTIFIER = CommunityNotificationCoordinator(
    CommunityNotificationDependencies(
        dispatch=dispatch,
        prepare_targets=_community_notification_targets,
        render=build_community_notification_payload,
        enabled=_community_notification_enabled,
        report_failure=_report_failure,
        spawn=partial(RuntimeTasks.spawn, name="community-notification"),
        fast_path_seconds=NOTIFICATION_FAST_PATH_WAIT_SECONDS,
    )
)


def get_community_notifier() -> CommunityNotificationCoordinator:
    return _COMMUNITY_NOTIFIER
