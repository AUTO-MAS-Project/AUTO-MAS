"""任务报告编排；外部发送、策略读取、任务注册和反馈均由宿主注入。"""

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from typing import Any, Protocol

from app.models.notification import NotifyPayload
from app.models.notification.channel import DispatchResult, NotifyTarget
from app.models.notification.community import CommunityNotificationResult
from app.models.notification.report import (
    NotificationDispatcher,
    ReportRenderer,
    TaskNotificationState,
    TaskReportPolicy,
    TaskReportRequest,
    TaskReportSummary,
)
from app.utils import get_logger

logger = get_logger("任务报告")

NOTIFICATION_SEND_ATTEMPTS = 2
NOTIFICATION_RETRY_DELAY_SECONDS = 1
# 快路径覆盖一次重试后仍失败的最早返回时间；更慢的通知继续由后台任务持有。
NOTIFICATION_FAST_PATH_WAIT_SECONDS = (
    NOTIFICATION_RETRY_DELAY_SECONDS * (NOTIFICATION_SEND_ATTEMPTS - 1) + 0.1
)
COMMUNITY_SIGN_RESULT_UNAVAILABLE_TEXT = (
    "社区签到流程异常结束，无法确认最终结果，请查看日志。"
)
COMMUNITY_SIGN_EMPTY_RESULT_TEXT = "本次社区签到已结束，没有新的签到结果。"


def schedule_notification_feedback[T](
    feedback: Callable[[], Awaitable[None]],
    *,
    spawn: Callable[[Coroutine[Any, Any, T]], asyncio.Task[T] | None],
    result: T,
    logger: Any,
    label: str,
) -> asyncio.Task[T] | None:
    """统一注册与隔离反馈；后台返回值和任务所有权沿用调用方契约。"""

    async def report() -> T:
        try:
            await feedback()
        except Exception as exc:
            logger.warning(f"{label}反馈失败: {type(exc).__name__}")
        return result

    coroutine = report()
    try:
        return spawn(coroutine)
    except Exception as exc:
        coroutine.close()
        logger.warning(f"{label}反馈注册失败: {type(exc).__name__}")
        return None


class CommunityFailureReporter(Protocol):
    async def __call__(
        self, result: DispatchResult, *, results_saved: bool
    ) -> None: ...


@dataclass(frozen=True)
class TaskReportDependencies:
    dispatch: NotificationDispatcher
    renderer: ReportRenderer
    read_policy: Callable[[], TaskReportPolicy]
    prepare_targets: Callable[[], tuple[NotifyTarget, ...]]
    report_failure: Callable[[DispatchResult], Awaitable[None]]
    report_supplement_failure: CommunityFailureReporter
    spawn: Callable[[Coroutine[Any, Any, None]], asyncio.Task[None] | None]


class TaskReportCoordinator:
    """只持有通知状态，协调报告合并、渠道去重和迟到签到补发。"""

    def __init__(
        self,
        *,
        state: TaskNotificationState,
        dependencies: TaskReportDependencies,
        community_pending: bool = False,
    ) -> None:
        self.state = state
        self.dependencies = dependencies
        self.community_pending = community_pending
        self.completed = asyncio.Event()
        self.lock = asyncio.Lock()
        self.targets: tuple[NotifyTarget, ...] | None = None
        self.report_sent = False
        self.wait_expired = False
        self.result_unavailable = False
        self.task_finished = False
        self.delivery_task: asyncio.Task[None] | None = None
        self.reports_pending = 0

    def receive(self, results: tuple[CommunityNotificationResult, ...] | None) -> None:
        """先保存结果再发布完成事件；报告等待超时不取消签到。"""

        self.result_unavailable = results is None
        # 占位项不参与实际通知，空结果仍能结清已发出的待确认提示。
        self.state.results = results or ()
        self.completed.set()
        self.schedule_supplement()

    @property
    def completion_notice(self) -> str:
        """异常不推断签到失败，正常空结果只结清先前的待确认提示。"""

        if self.result_unavailable:
            return COMMUNITY_SIGN_RESULT_UNAVAILABLE_TEXT
        if self.wait_expired and self.completed.is_set() and not self.state.results:
            return COMMUNITY_SIGN_EMPTY_RESULT_TEXT
        return ""

    def community_summary(self) -> TaskReportSummary:
        if self.state.summary_consumed:
            return TaskReportSummary()
        if not self.state.results:
            return TaskReportSummary(
                text=self.completion_notice, markdown=self.completion_notice
            )
        return self.dependencies.renderer.community_summary(self.state.results)

    def should_send_result(
        self,
        *,
        policy: TaskReportPolicy,
        uncompleted_count: int,
    ) -> bool:
        if policy.community_enabled and (
            self.community_summary().text
            or (self.community_pending and not self.completed.is_set())
        ):
            return True
        return policy.result_time == "任何时刻" or (
            policy.result_time == "仅失败时" and uncompleted_count != 0
        )

    def finish(self) -> None:
        """没有脚本报告（如预检失败或手动停止）时也保留签到通知出口。"""

        self.task_finished = True
        self.schedule_supplement()

    def schedule_supplement(self) -> None:
        if self.reports_pending:
            return
        if not self.completed.is_set() or not (
            self.task_finished or (self.report_sent and self.wait_expired)
        ):
            return
        if not self.state.results and not self.completion_notice:
            return
        if self.delivery_task is not None and not self.delivery_task.done():
            return
        self.delivery_task = self.dependencies.spawn(self._send_supplement())

    async def _send_supplement(self) -> None:
        # 与报告共用锁，即使签到在报告发送中到达，也只补发未收到摘要的渠道。
        async with self.lock:
            policy = self.dependencies.read_policy()
            if self.state.summary_consumed or not policy.community_enabled:
                return
            payload = (
                self.dependencies.renderer.community_payload(self.state.results)
                if self.state.results
                else NotifyPayload(
                    title="社区签到执行结束", text=self.completion_notice
                )
            )
            targets = (
                self.targets
                if self.targets is not None
                else self.dependencies.prepare_targets()
            )
            result = await self.dependencies.dispatch(
                payload,
                targets,
                attempts=NOTIFICATION_SEND_ATTEMPTS,
                retry_delay=NOTIFICATION_RETRY_DELAY_SECONDS,
                skip_channel_ids=self.state.delivered,
            )
            self.state.delivered.update(result.succeeded_ids)
            if result.attempted and not result.failed:
                self.state.summary_consumed = True
            if result.failed:
                results_saved = bool(self.state.results)
                schedule_notification_feedback(
                    lambda: self.dependencies.report_supplement_failure(
                        result, results_saved=results_saved
                    ),
                    spawn=self.dependencies.spawn,
                    result=None,
                    logger=logger,
                    label="任务通知",
                )

    async def dispatch_report(
        self,
        request: TaskReportRequest,
    ) -> DispatchResult:
        """使用入口固定的策略；迟到补发会重新读取下一次通知的策略。"""

        async with self.lock:
            self.targets = request.targets
            payload = request.payload
            if self.community_pending:
                if (
                    request.policy.community_enabled
                    and not self.completed.is_set()
                    and not self.wait_expired
                ):
                    try:
                        await asyncio.wait_for(
                            self.completed.wait(), timeout=request.policy.wait_seconds
                        )
                    except asyncio.TimeoutError:
                        self.wait_expired = True
                        logger.info(
                            "签到结果尚未返回，先发送任务报告，完成后补发签到结果"
                        )
                if request.policy.community_enabled and not self.completed.is_set():
                    pending = "社区签到结果待确认，完成后另行通知。"
                    payload = self.dependencies.renderer.append_summary(
                        payload, TaskReportSummary(text=pending, markdown=pending)
                    )
            try:
                return await self._dispatch_report_payload(
                    request=request, payload=payload
                )
            finally:
                if self.community_pending:
                    self.report_sent = True
                    self.schedule_supplement()

    async def _dispatch_report_payload(
        self,
        *,
        request: TaskReportRequest,
        payload: NotifyPayload,
    ) -> DispatchResult:
        summary = (
            self.community_summary()
            if request.policy.community_enabled
            else TaskReportSummary()
        )
        if not summary.text:
            result = await self.dependencies.dispatch(
                payload,
                request.targets,
            )
        else:
            delivered = set(self.state.delivered)
            channels = {
                ct.id for target in request.targets for _, ct in target.channels
            }
            with_summary = await self.dependencies.dispatch(
                self.dependencies.renderer.append_summary(payload, summary),
                request.targets,
                skip_channel_ids=delivered,
            )
            # 本轮开始前收到过摘要的渠道只收原始报告，避免同一轮重复投递。
            without_summary = (
                await self.dependencies.dispatch(
                    payload,
                    request.targets,
                    skip_channel_ids=channels - delivered,
                )
                if delivered & channels
                else DispatchResult()
            )
            self.state.delivered.update(with_summary.succeeded_ids)
            if self.state.delivered & channels and not with_summary.failed:
                self.state.summary_consumed = True
            unresolved = {
                failure for target in request.targets for failure in target.unresolved
            }
            result = DispatchResult(
                attempted=with_summary.attempted + without_summary.attempted,
                succeeded=with_summary.succeeded + without_summary.succeeded,
                failed=with_summary.failed
                + tuple(f for f in without_summary.failed if f not in unresolved),
                succeeded_ids=with_summary.succeeded_ids
                + without_summary.succeeded_ids,
                failures=with_summary.failures
                + tuple(
                    failure
                    for failure in without_summary.failures
                    if failure.label not in unresolved
                ),
            )
        if result.failed:
            schedule_notification_feedback(
                lambda: self.dependencies.report_failure(result),
                spawn=self.dependencies.spawn,
                result=None,
                logger=logger,
                label="任务通知",
            )
        return result
