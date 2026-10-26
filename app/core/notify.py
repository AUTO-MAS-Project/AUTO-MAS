#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
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

"""宿主通知服务；目标选择、投递和任务报告消费同一组显式依赖。"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from contextlib import AbstractContextManager
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, Any

from app.config import ConfigManager
from app.core.community_notification import (
    CommunityNotificationCoordinator,
    CommunityNotificationDependencies,
)
from app.core.notification_report import (
    NOTIFICATION_FAST_PATH_WAIT_SECONDS,
    TaskReportCoordinator,
)
from app.core.notification_tasks import NotificationTasks
from app.core.notify_channels import RuntimeConfigView, TargetConfigView
from app.models.notification import (
    NotificationImage,
    NotificationSummary,
    NotifyPayload,
    WebhookTargetSnapshot,
)
from app.models.notification_channel import (
    ChannelTarget,
    DeliveryChannel,
    DispatchResult,
    EmptyPolicy,
    NotificationSourceConfig,
    NotificationTransportSnapshot,
    NotifyChannel,
    NotifyTarget,
    RecruitmentNotificationConfig,
    UserNotificationConfig,
)
from app.models.notification_ports import LocalNotice
from app.models.notification_report import TaskReportPolicy, TaskResultReport
from app.runtime_tasks import OwnedTaskRegistry
from app.services.community_notification import build_community_notification_payload
from app.services.notification import Notification
from app.services.notification_dispatch import dispatch as dispatch_notification
from app.services.notification_rendering import AsyncNotificationRenderer
from app.utils import get_logger
from app.utils.notification_template import deferred_notification_template

if TYPE_CHECKING:
    from app.core.config import AppConfig
    from app.core.task_report import PreparedTaskReport
    from app.models.task import TaskItem

logger = get_logger("通知编排")


class HostNotificationService:
    """应用持有实例；业务和插件只能消费注入的通知能力。"""

    def __init__(
        self,
        *,
        config: AppConfig,
        transactions: ConfigManager,
        channels: tuple[NotifyChannel, ...],
        catalog_failures: tuple[str, ...],
        transport: Notification,
        renderer: AsyncNotificationRenderer,
        runtime: OwnedTaskRegistry,
        runtime_config: RuntimeConfigView,
    ) -> None:
        self.config = config
        self.transactions = transactions
        self._channels = channels
        self._catalog_failures = catalog_failures
        self._transport = transport
        self._renderer = renderer
        self._runtime_config = runtime_config
        self._closed = False
        self.tasks = NotificationTasks(
            runtime=runtime, push_system_notice=config.push_system_notice
        )
        self.community = CommunityNotificationCoordinator(
            CommunityNotificationDependencies(
                dispatch=self.dispatch,
                prepare_targets=lambda: (self.global_target(include_system=True),),
                render=build_community_notification_payload,
                enabled=lambda: self.config.ToolsConfig.GameSign.NotifyEnabled,
                report_failure=self.report_community_failure,
                spawn=partial(runtime.spawn, name="community-notification"),
                fast_path_seconds=NOTIFICATION_FAST_PATH_WAIT_SECONDS,
            )
        )

    async def start(self) -> None:
        await self._transport.start()

    async def close(self) -> None:
        """宿主先回收运行时任务，再释放渲染、渠道和配置订阅。"""
        if self._closed:
            return
        self._closed = True
        self._renderer.close()
        try:
            await self._transport.stop()
        finally:
            self._runtime_config.close()

    def channel_sender(self, key: str) -> Any:
        return self._transport.channel_sender(key)

    async def send_notice(self, notice: LocalNotice) -> None:
        await self._transport.send_notice(notice)

    async def test_webhook(
        self, payload: NotifyPayload, webhook: WebhookTargetSnapshot
    ) -> None:
        await self._transport.test_webhook(payload, webhook)

    async def report_community_failure(
        self, result: DispatchResult, *, results_saved: bool
    ) -> None:
        await self.config.push_system_notice(
            level="warning",
            title="游戏社区通知发送不完整",
            lines=[
                f"发送失败的渠道：{'、'.join(result.failed)}",
                "签到结果已保存，请检查这些渠道的通知配置后重试。"
                if results_saved
                else "请检查这些渠道的通知配置后重试。",
            ],
        )

    def read_task_report_policy(self) -> TaskReportPolicy:
        """报告入口固定一次策略，迟到补发作为下一次通知重新读取。"""
        return TaskReportPolicy(
            result_time=self.config.setting.Notify.SendTaskResultTime,
            community_enabled=self.config.ToolsConfig.GameSign.NotifyEnabled,
            wait_seconds=NOTIFICATION_FAST_PATH_WAIT_SECONDS,
        )

    def prepare_task_report(
        self, task_info: TaskItem | None = None
    ) -> PreparedTaskReport:
        from app.core.task_report import prepare_task_report

        return prepare_task_report(task_info, notifications=self)

    def create_task_report_coordinator(
        self, task_info: TaskItem
    ) -> TaskReportCoordinator:
        from app.core.task_report import create_task_report_coordinator

        return create_task_report_coordinator(task_info, notifications=self)

    async def push_statistics_report(
        self,
        *,
        payload: NotifyPayload,
        user_config: UserNotificationConfig | None,
        task_info: TaskItem,
        compact_summary: bool = False,
    ) -> DispatchResult:
        """按任务原有托管与失败反馈规则投递统计正文。"""

        logger.info(f"开始推送通知, 模式: 统计信息, 标题: {payload.title}")
        return await self.dispatch_task_notification(
            payload,
            self.statistic_targets(user_config, compact_summary=compact_summary),
            task_info=task_info,
        )

    async def dispatch_task_notification(
        self,
        payload: NotifyPayload,
        targets: list[NotifyTarget],
        *,
        task_info: TaskItem | None = None,
    ) -> DispatchResult:
        from app.core.task_report import dispatch_task_notification

        return await dispatch_task_notification(
            payload,
            targets,
            notifications=self,
            task_info=task_info,
        )

    def task_notification_batch(
        self, *, task_id: str | None
    ) -> AbstractContextManager[None]:
        return self.tasks.task_notification_batch(task_id=task_id)

    async def send_global(
        self,
        payload: NotifyPayload,
        *,
        include_system: bool = False,
        empty_policy: EmptyPolicy = "send",
        system_timeout_seconds: int | None = None,
        attempts: int = 1,
        retry_delay: float = 0,
    ) -> DispatchResult:
        return await self.dispatch(
            payload,
            [
                self.global_target(
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
        user_config: NotificationSourceConfig,
        *,
        attempts: int = 1,
        retry_delay: float = 0,
    ) -> DispatchResult:
        return await self.dispatch(
            payload,
            [self.user_target(user_config)],
            attempts=attempts,
            retry_delay=retry_delay,
        )

    async def send_statistics(
        self,
        payload: NotifyPayload,
        user_config: UserNotificationConfig | None,
        *,
        global_empty_policy: EmptyPolicy = "send",
        compact_summary: bool = False,
        attempts: int = 1,
        retry_delay: float = 0,
    ) -> DispatchResult:
        return await self.dispatch(
            payload,
            self.statistic_targets(
                user_config,
                global_empty_policy=global_empty_policy,
                compact_summary=compact_summary,
            ),
            attempts=attempts,
            retry_delay=retry_delay,
        )

    def global_target(
        self,
        *,
        include_system: bool = False,
        empty_policy: EmptyPolicy = "send",
        system_timeout_seconds: int | None = None,
    ) -> NotifyTarget:
        """按全局配置构造通知目标。"""

        return self._resolve_target(
            config=self.config.setting,
            scope="global",
            include_system=include_system,
            empty_policy=empty_policy,
            system_timeout_seconds=system_timeout_seconds,
        )

    def user_target(self, user_config: NotificationSourceConfig) -> NotifyTarget:
        """按用户配置构造独立通知目标。"""
        return self._resolve_target(
            config=user_config, scope="user", empty_policy="warn"
        )

    def _resolve_target(
        self,
        *,
        config: NotificationSourceConfig,
        scope: str,
        empty_policy: EmptyPolicy,
        include_system: bool = False,
        system_timeout_seconds: int | None = None,
    ) -> NotifyTarget:
        """逐渠道解析快照；一个渠道失败时保留其不确定性并继续其他渠道。"""
        pairs: list[tuple[DeliveryChannel, ChannelTarget]] = []
        failures: list[str] = []
        for channel in self._channels:
            try:
                channel_targets = channel.targets(TargetConfigView(config), scope=scope)
                resolved = []
                for target in channel_targets:
                    if target.is_local and not include_system:
                        continue
                    if target.is_local and system_timeout_seconds is not None:
                        target = replace(target, timeout_seconds=system_timeout_seconds)
                    resolved.append((channel.delivery(), target))
                if resolved and channel.transport_fields is not None:
                    transport = NotificationTransportSnapshot(
                        values=tuple(
                            (name, getattr(self.config.setting.Notify, name))
                            for name in channel.transport_fields
                        ),
                        proxy=self._runtime_config.read_proxy(),
                    )
                    resolved = [
                        (delivery, replace(target, transport=transport))
                        for delivery, target in resolved
                    ]
                pairs.extend(resolved)
            except Exception as exc:
                prefix = "全局" if scope == "global" else "用户"
                failure = f"{prefix}通知渠道 {channel.key} 目标准备失败"
                failures.append(failure)
                logger.warning(f"{failure}: {type(exc).__name__}")
        return NotifyTarget(
            channels=tuple(pairs),
            empty_policy=empty_policy,
            catalog_failures=self._catalog_failures,
            preparation_failures=tuple(failures),
        )

    def user_statistic_targets(
        self,
        user_config: UserNotificationConfig | None,
    ) -> list[NotifyTarget]:
        """返回已启用统计通知的用户目标。"""

        if (
            user_config is None
            or not user_config.Notify.Enabled
            or not user_config.Notify.IfSendStatistic
        ):
            return []
        return [self.user_target(user_config)]

    def recruitment_targets(
        self,
        user_config: RecruitmentNotificationConfig | None,
    ) -> list[NotifyTarget]:
        """按全局和个人订阅准备喜报目标，不识别具体传输渠道。"""

        targets = []
        if self.config.setting.Notify.IfSendSixStar:
            targets.append(self.global_target())
        if (
            user_config is not None
            and user_config.Notify.Enabled
            and user_config.Notify.IfSendSixStar
        ):
            targets.append(self.user_target(user_config))
        return targets

    def failure_targets(
        self,
    ) -> list[NotifyTarget]:
        """任务失败信号沿用任务结果开关，包含受自身开关约束的本地提示。"""

        if self.config.setting.Notify.SendTaskResultTime == "不推送":
            return []
        return [self.global_target(include_system=True, system_timeout_seconds=10)]

    def statistic_targets(
        self,
        user_config: UserNotificationConfig | None,
        *,
        global_empty_policy: EmptyPolicy = "send",
        compact_summary: bool = False,
    ) -> list[NotifyTarget]:
        """返回全局与用户级统计通知目标。"""

        targets = []
        if self.config.setting.Notify.IfSendStatistic:
            targets.append(self.global_target(empty_policy=global_empty_policy))
        targets.extend(self.user_statistic_targets(user_config))
        if compact_summary:
            targets = [self._prefer_compact_summaries(target) for target in targets]
        return targets

    def _prefer_compact_summaries(self, target: NotifyTarget) -> NotifyTarget:
        """按渠道目标声明应用业务提供的紧凑摘要偏好。"""

        channels = []
        for channel, channel_target in target.channels:
            if channel_target.compact_summary_policy is not None:
                channel_target = replace(
                    channel_target, summary_policy=channel_target.compact_summary_policy
                )
            channels.append((channel, channel_target))
        return replace(
            target,
            channels=tuple(channels),
        )

    async def dispatch(
        self,
        payload: NotifyPayload,
        targets: Iterable[NotifyTarget],
        *,
        attempts: int = 1,
        retry_delay: float = 0,
        skip_channel_ids: Iterable[str] = (),
    ) -> DispatchResult:
        """使用本实例的发送器与渲染器，底层投递只接受显式依赖。"""
        return await dispatch_notification(
            payload=payload,
            targets=targets,
            attempts=attempts,
            retry_delay=retry_delay,
            skip_channel_ids=skip_channel_ids,
            notifier=self._transport,
            renderer=self._renderer,
            concurrent=not self.transactions.in_transaction,
        )

    async def send_test_notification(
        self,
    ) -> DispatchResult:
        """向全部已启用的全局渠道发送测试通知。"""

        text = (
            "这是 AUTO-MAS 外部通知测试信息。如果你看到了这段内容，说明 AUTO-MAS "
            "的通知功能已经正确配置且可以正常工作！"
        )
        return await self.dispatch(
            NotifyPayload(
                title="AUTO-MAS测试通知",
                text=text,
                append_signature=False,
            ),
            [
                self.global_target(
                    include_system=True,
                    empty_policy="warn",
                    system_timeout_seconds=3,
                )
            ],
        )

    async def push_proxy_result(
        self,
        *,
        title: str,
        report: TaskResultReport,
        task_info: TaskItem | None = None,
        result_template: str = "general_result.html",
        signature_sep: str = "\n\n",
        images: Sequence[NotificationImage] = (),
        include_system: bool = True,
    ) -> DispatchResult:
        """推送全局「代理结果」报告；签到合并和补发由报告协调器承担。

        Args:
            title: 通知标题。
            report: 已在专项边界固定公共字段的任务报告。
            task_info: 任务信息，用于签到汇总的渠道级重试。
            result_template: 结果 HTML 模板名，MAA 用 MAA_result.html。
            signature_sep: 签名分隔符，默认与 NotifyPayload 缺省一致；MAA 只空一行。
            images: 随报告提供的图片资源。HTML 模板通过稳定资源 ID 引用需要展示的图片。
            include_system: 是否弹系统通知。本轮已由专门的通知弹过（如 MaaFW 的停服维护 /
                需要更新）时传 False，免得同一件事弹两次。
        """

        logger.info(f"开始推送通知, 模式: 代理结果, 标题: {title}")
        prepared = self.prepare_task_report(task_info)
        if not prepared.should_send(
            uncompleted_count=report.uncompleted_count,
        ):
            return DispatchResult()

        message_text = (
            f"任务开始时间: {report.start_time}, 结束时间: {report.end_time}\n"
            f"已完成数: {report.completed_count}, 未完成数: {report.uncompleted_count}\n\n"
            f"{report.result}"
        )
        counts = (
            f"已完成用户数: {report.completed_count}, "
            f"未完成用户数: {report.uncompleted_count}"
        )
        # 有未完成的用户时摘要标题不能再说「已完成！」；调用方显式给的摘要标题优先
        summary_title = report.summary_title or title.replace(
            "报告", "存在异常" if report.uncompleted_count > 0 else "已完成！"
        )
        return await prepared.dispatch(
            NotifyPayload(
                title=title,
                text=message_text,
                html=deferred_notification_template(
                    result_template, report.template_context()
                ),
                signature_sep=signature_sep,
                summary=NotificationSummary(
                    text=counts,
                    title=summary_title,
                    overflow_text=message_text,
                ),
                images=tuple(images),
            ),
            [
                self.global_target(
                    include_system=include_system, system_timeout_seconds=10
                )
            ],
        )
