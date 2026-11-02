"""项目信号节点（停服维护 / 需要更新客户端）在宿主侧的记账与正式通知。

worker 在 ``MaaFWRunResult.signal`` 里回报信号（见 ``core/runner/run_signal.py``）。一次运行
（一个脚本的这一轮）里按「信号 + 资源」记一条：第一位撞上的用户记进来，同一资源后面因
维护被连带跳过的用户并进同一条；收尾时全局渠道每条只发一份合并通知，不按用户各发一份。
用户的个人渠道按用户拆开、各发各的：名单只写本人、截图只带本人的——合并那份里有其他
用户的名字与游戏画面，发进个人渠道就成了跨用户外泄。账只在宿主内存里，不落配置字段。

本模块不导入 ``maa``：管理器在模块层导入它。
"""

from __future__ import annotations

import asyncio
import html
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core import Notify
from app.core.notify.task_content import (
    prepare_screenshot_images as prepare_screenshot_images,
)
from app.models.notification import NotificationImage, NotifyPayload, image_reference
from app.models.notification.channel import DispatchResult, NotifyTarget

# 信号取值与 worker 共用 worker_protocol 那一份；不经 core.runner 包导入（它的 __init__
# 会拉起 runner 子树）。
from app.task.MaaFW.tools.core.worker_protocol import (
    CLIENT_UPDATE_REQUIRED,
    SERVER_MAINTENANCE,
)
from app.utils import get_logger

logger = get_logger("MaaFW 信号通知")

# 用户日志状态、统计信息与「任务详情」里用的一句话。
# 执行器按显式信号提供历史状态；这些文案仅用于展示。
SIGNAL_USER_MESSAGES = {
    SERVER_MAINTENANCE: "游戏停服维护中，本次跳过",
    CLIENT_UPDATE_REQUIRED: "需要更新游戏客户端，请手动更新后再运行",
}
# 同一资源已确认在维护时，后续用户运行前检查返回的原因。
MAINTENANCE_SKIP_MESSAGE = "游戏停服维护中，本次跳过（同一资源已确认在维护）"
# LastProxyStatus 在 MaaFWUserConfig 里不是受限枚举（运行中也写这里），维护跳过写它。
MAINTENANCE_LAST_STATUS = "维护中"


@dataclass
class MaaFWSignalRecord:
    signal: str
    resource_name: str
    resource_label: str
    project_name: str
    node: str | None = None
    # (用户 id, 用户名)，按撞上 / 被连带跳过的先后
    users: list[tuple[str, str]] = field(default_factory=list)
    # 证据截图，只留第一张（后面的用户是同一画面），给全局渠道的合并通知用
    screenshots: list[Path | bytes] = field(default_factory=list)
    # 用户 id → 这位用户自己拍的证据截图，给个人渠道用（被连带跳过的用户没有）
    user_screenshots: dict[str, Path | bytes] = field(default_factory=dict)

    def add_user(self, user_id: str, user_name: str) -> None:
        if all(existing != user_id for existing, _ in self.users):
            self.users.append((user_id, user_name))


class MaaFWSignalTracker:
    """一次运行里的信号账：按（信号, 资源名）一条。"""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], MaaFWSignalRecord] = {}

    def record(
        self,
        signal: str,
        *,
        resource_name: str,
        resource_label: str,
        project_name: str,
        node: str | None,
        user_id: str,
        user_name: str,
        screenshot: Path | None = None,
    ) -> MaaFWSignalRecord:
        key = (signal, resource_name)
        record = self._records.get(key)
        if record is None:
            record = MaaFWSignalRecord(
                signal=signal,
                resource_name=resource_name,
                resource_label=resource_label,
                project_name=project_name,
                node=node,
            )
            self._records[key] = record
        record.add_user(user_id, user_name)
        if screenshot is not None:
            if not record.screenshots:
                record.screenshots.append(screenshot)
            record.user_screenshots.setdefault(user_id, screenshot)
        return record

    async def freeze_user_screenshots(self, user_id: str) -> None:
        """用户归档前复制证据内容，保持个人渠道的原有隔离。"""
        for record in self._records.values():
            source = record.user_screenshots.get(user_id)
            if not isinstance(source, Path):
                continue
            try:
                data = await asyncio.to_thread(source.read_bytes)
            except OSError as error:
                logger.warning(f"冻结信号截图失败：{source}: {error}")
                record.user_screenshots.pop(user_id, None)
                record.screenshots = [
                    value for value in record.screenshots if value != source
                ]
                continue
            record.user_screenshots[user_id] = data
            record.screenshots = [
                data if value == source else value for value in record.screenshots
            ]

    def maintenance(self, resource_name: str) -> MaaFWSignalRecord | None:
        """该资源本轮已确认在维护时返回那条记录。"""

        return self._records.get((SERVER_MAINTENANCE, resource_name))

    def records(self) -> list[MaaFWSignalRecord]:
        return list(self._records.values())

    def user_ids(self, signal: str) -> set[str]:
        """本轮因该信号受影响的用户 id（含维护时被连带跳过的）。"""

        return {
            user_id
            for record in self._records.values()
            if record.signal == signal
            for user_id, _ in record.users
        }


def signal_global_targets() -> list[NotifyTarget]:
    """信号通知的全局目标：与任务报告同一套开关，不绕过。

    全局渠道看「发送任务结果时机」：不推送就不发（维护 / 需更新都属于本次没跑成，
    「仅失败时」也发）；系统通知另受它自己的开关约束，且本轮的系统弹窗只由这里弹
    （代理结果那份此时不弹）。用户渠道只发给受影响、且开了个人通知与统计推送的用户
    （与用户级统计报告同一开关，``user_statistic_targets``），按用户分开发，见
    ``push_signal_notices``。
    """

    return Notify.failure_targets()


def build_signal_payload(
    record: MaaFWSignalRecord,
    *,
    script_name: str,
    images: Sequence[tuple[str, NotificationImage]] = (),
    users: Sequence[tuple[str, str]] | None = None,
) -> NotifyPayload:
    """``users`` 给了就只列这些用户（个人渠道只写本人），否则列记录里的全部。"""

    game = record.project_name
    where = " ".join(part for part in (game, record.resource_label) if part)
    listed = record.users if users is None else users
    users_text = "、".join(name for _, name in listed) or "-"
    if record.signal == SERVER_MAINTENANCE:
        head = "游戏停服维护中"
        tail = "本次已跳过，下次定时照常运行。"
    else:
        head = "需要更新游戏客户端"
        tail = "本次未能运行，请手动更新游戏客户端后再运行。"
    title = f"{head}：{game}" if game else head
    lead = f"{head}（{where}），{tail}" if where else f"{head}，{tail}"
    lines = [lead, f"脚本：{script_name}", f"受影响的用户：{users_text}"]
    text = "\n".join(lines)
    markdown = "\n\n".join(lines)
    html_body = "".join(f"<p>{html.escape(line)}</p>" for line in lines)
    for label, image in images:
        markdown += f"\n\n![{label}]({image_reference(image.id)})"
        html_body += (
            f'<p>{html.escape(label)}</p><img src="{image_reference(image.id)}" '
            f'alt="{html.escape(label)}" style="max-width:100%">'
        )
    return NotifyPayload(
        title=title,
        text=text,
        markdown=markdown,
        html=html_body,
        images=tuple(image for _, image in images),
    )


async def push_signal_notices(
    tracker: MaaFWSignalTracker,
    *,
    script_name: str,
    user_config_for: Callable[[str], Any | None],
) -> list[DispatchResult]:
    """每条信号记录：全局渠道发一份合并通知，用户渠道按用户各发一份；没有可发的目标就不发。

    个人那份只列本人、只带本人拍的证据截图（被连带跳过的用户没有截图，就不带图），
    不把别的用户的名字和游戏画面发进某个人的渠道。
    """

    results: list[DispatchResult] = []
    for record in tracker.records():
        user_targets = [
            (user_id, user_name, targets)
            for user_id, user_name in record.users
            if (config := user_config_for(user_id)) is not None
            and (targets := Notify.user_statistic_targets(config))
        ]
        global_targets = signal_global_targets()
        if not global_targets and not user_targets:
            logger.info(
                f"信号通知的全局与用户渠道都未开启，不发送：{record.signal} "
                f"{record.resource_name}"
            )
            continue
        if global_targets:
            images = await prepare_screenshot_images(
                [("证据截图", path) for path in record.screenshots],
                image_id_prefix="maafw",
            )
            payload = build_signal_payload(
                record, script_name=script_name, images=images
            )
            logger.info(f"推送 MaaFW 信号通知：{payload.title}")
            results.append(
                await Notify.dispatch_task_notification(payload, global_targets)
            )
        for user_id, user_name, targets in user_targets:
            own_shot = record.user_screenshots.get(user_id)
            images = (
                await prepare_screenshot_images(
                    [("证据截图", own_shot)],
                    image_id_prefix="maafw",
                )
                if own_shot is not None
                else []
            )
            payload = build_signal_payload(
                record,
                script_name=script_name,
                images=images,
                users=[(user_id, user_name)],
            )
            logger.info(f"推送 MaaFW 信号通知（用户 {user_name}）：{payload.title}")
            results.append(await Notify.dispatch_task_notification(payload, targets))
    return results


__all__ = [
    "CLIENT_UPDATE_REQUIRED",
    "MAINTENANCE_LAST_STATUS",
    "MAINTENANCE_SKIP_MESSAGE",
    "MaaFWSignalRecord",
    "MaaFWSignalTracker",
    "SERVER_MAINTENANCE",
    "SIGNAL_USER_MESSAGES",
    "build_signal_payload",
    "push_signal_notices",
    "signal_global_targets",
]
