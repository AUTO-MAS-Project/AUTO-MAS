"""社区通知装配入口；配置、渲染和后台任务在此绑定。"""

from functools import partial

from app.core.community_notification import (
    CommunityNotificationCoordinator,
    CommunityNotificationDependencies,
)
from app.core.config import Config
from app.core.notification_report import NOTIFICATION_FAST_PATH_WAIT_SECONDS
from app.core.notify import dispatch, global_target
from app.models.notification_channel import DispatchResult, NotifyTarget
from app.runtime_tasks import RuntimeTasks
from app.services.community_notification import build_community_notification_payload


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
