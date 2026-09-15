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

"""统一通知编排。

脚本和业务模块负责生成正文，本模块负责读取通知配置、选择目标渠道、失败隔离与重试；
``app.services.notification`` 只保留具体渠道的传输实现。
"""

import asyncio
import json
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, replace
from typing import Any, Literal
from urllib.parse import urlsplit

from app.core.config import Config
from app.models.config import Webhook
from app.services.notification import DEFAULT_WEBHOOK_TEMPLATE, Notify
from app.utils import get_logger

logger = get_logger("通知编排")

SIGNATURE = "AUTO-MAS 敬上"

MailMode = Literal["文本", "网页"]
EmptyPolicy = Literal["send", "warn", "skip"]


@dataclass(frozen=True)
class NotifyPayload:
    """一份已经完成业务渲染的通知正文。"""

    title: str
    text: str
    html: str | None = None
    signature_sep: str = "\n\n"
    append_signature: bool = True
    email_mode: MailMode = "网页"
    serverchan_text: str | None = None
    webhook_text: str | None = None
    markdown_text: str | None = None
    webhook_image_base64: str | None = None
    koishi_text: str | None = None
    koishi_msgtype: Literal["text", "html", "picture"] = "text"
    system_title: str | None = None
    system_message: str | None = None
    system_ticker: str | None = None
    system_timeout: int = 5
    standalone_title: str | None = None

    @property
    def signed_text(self) -> str:
        """返回默认的纯文本渠道正文。"""

        if not self.append_signature:
            return self.text
        return f"{self.text}{self.signature_sep}{SIGNATURE}"

    @property
    def email_content(self) -> str:
        """返回邮件正文。"""

        if self.email_mode == "网页" and self.html is not None:
            return self.html
        return self.text

    @property
    def serverchan_content(self) -> str:
        """返回 ServerChan 正文。"""

        if self.serverchan_text is not None:
            return self.serverchan_text
        if self.markdown_text is not None:
            return self.markdown_text
        text = self.text.replace("\n", "\n\n")
        if not self.append_signature:
            return text
        return f"{text}{self.signature_sep}{SIGNATURE}"

    @property
    def webhook_content(self) -> str:
        """返回 Webhook 正文。"""

        if self.webhook_text is not None:
            return self.webhook_text
        if self.markdown_text is not None:
            return self.markdown_text
        return self.signed_text

    def webhook_content_for(self, webhook: Webhook) -> str:
        """按模板选择正文格式；仅正文模板需要补上独立通知标题。"""

        if not self.standalone_title and (
            self.webhook_text is not None or self.markdown_text is None
        ):
            return self.webhook_content
        template_text = webhook.get("Data", "Template") or DEFAULT_WEBHOOK_TEMPLATE
        content = self.webhook_content
        markdown = False
        if self.webhook_text is None and self.markdown_text is not None:
            try:
                template = json.loads(template_text)
                host = urlsplit(webhook.get("Data", "Url")).hostname
            except (ValueError, TypeError):
                content = self.signed_text
            else:
                markdown = (
                    isinstance(template, dict)
                    and (
                        template.get("msgtype") == "markdown"
                        or template.get("template") == "markdown"
                        or "desp" in template
                    )
                ) or host in {
                    "discord.com",
                    "discordapp.com",
                    "canary.discord.com",
                    "ptb.discord.com",
                }
                content = self.markdown_text if markdown else self.signed_text
        if self.standalone_title and "{title}" not in template_text:
            heading = (
                f"**{self.standalone_title}**" if markdown else self.standalone_title
            )
            return f"{heading}\n\n{content}"
        return content

    @property
    def koishi_content(self) -> str:
        """返回 Koishi 正文。"""

        if self.koishi_text is not None:
            return self.koishi_text
        return f"{self.title}\n\n{self.signed_text}"

    @property
    def openclaw_weixin_content(self) -> str:
        """返回微信（iLink）正文。"""

        text = self.signed_text
        heading = self.standalone_title or self.title
        return text if text.startswith(f"【{self.title}】") else f"{heading}\n\n{text}"

    @property
    def openclaw_qq_content(self) -> str:
        """返回 QQ 官方机器人正文。"""

        text = self.signed_text
        heading = self.standalone_title or self.title
        return text if text.startswith(f"【{self.title}】") else f"{heading}\n\n{text}"

    @property
    def cmcc_newmsg_content(self) -> str:
        """返回中国移动新消息正文。"""

        text = self.signed_text
        heading = self.standalone_title or self.title
        return text if text.startswith(f"【{self.title}】") else f"{heading}\n\n{text}"

    @property
    def system_content(self) -> str:
        """返回系统通知正文。"""

        return self.text


@dataclass(frozen=True)
class NotifyTarget:
    """一组通知渠道及其配置来源。"""

    name: str
    system: bool = False
    mail_to: str | None = None
    serverchan_key: str | None = None
    cmcc_newmsg_api_key: str | None = None
    webhooks: Iterable[tuple[str, Any]] = ()
    koishi: bool = False
    openclaw_weixin: bool = False
    openclaw_qq: bool = False
    empty_policy: EmptyPolicy = "send"


@dataclass(frozen=True)
class DispatchResult:
    """一次通知分发的明确结果。

    ``attempted`` 是本次实际尝试投递的渠道数（被跳过的渠道不计入）；
    ``succeeded`` / ``failed`` 分别是成功与失败的渠道名。零目标或全跳过时
    ``attempted`` 为 0，切勿把该状态当作「已送达」。
    """

    attempted: int = 0
    succeeded: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    # 内部投递记录使用 ID，用户可见的 succeeded/failed 继续保留渠道名称。
    succeeded_ids: tuple[str, ...] = ()


def _webhooks(config: Any) -> tuple[tuple[str, Any], ...]:
    """读取配置中已启用的 Webhook，并保留可识别的 ID。"""

    return tuple(
        (str(uid), webhook)
        for uid, webhook in config.items()
        if bool(webhook.get("Info", "Enabled"))
    )


def global_target(
    *,
    include_system: bool = False,
    empty_policy: EmptyPolicy = "send",
) -> NotifyTarget:
    """按全局配置构造通知目标。"""

    return NotifyTarget(
        name="全局",
        system=include_system and bool(Config.get("Notify", "IfPushPlyer")),
        mail_to=(
            Config.get("Notify", "ToAddress")
            if Config.get("Notify", "IfSendMail")
            else None
        ),
        serverchan_key=(
            Config.get("Notify", "ServerChanKey")
            if Config.get("Notify", "IfServerChan")
            else None
        ),
        cmcc_newmsg_api_key=(
            Config.get("Notify", "CMCCNewMsgApiKey")
            if Config.get("Notify", "IfCMCCNewMsg")
            else None
        ),
        webhooks=_webhooks(Config.Notify_CustomWebhooks),
        koishi=bool(Config.get("Notify", "IfKoishiSupport")),
        openclaw_weixin=bool(Config.get("Notify", "IfOpenClawWeixin")),
        openclaw_qq=bool(Config.get("Notify", "IfOpenClawQQ")),
        empty_policy=empty_policy,
    )


def user_target(user_config: Any) -> NotifyTarget:
    """按用户配置构造独立通知目标。"""

    return NotifyTarget(
        name="用户",
        mail_to=(
            user_config.get("Notify", "ToAddress")
            if user_config.get("Notify", "IfSendMail")
            else None
        ),
        serverchan_key=(
            user_config.get("Notify", "ServerChanKey")
            if user_config.get("Notify", "IfServerChan")
            else None
        ),
        webhooks=_webhooks(user_config.Notify_CustomWebhooks),
        empty_policy="warn",
    )


def should_send_result(message: dict, *, task_info: object | None = None) -> bool:
    """判断代理结果是否满足全局推送时机。"""

    if message.get("game_sign_summary", False):
        return True

    if task_info is not None:
        from app.tools.community_notify import append_task_community_summary

        if append_task_community_summary(task_info, ""):
            return True

    result_time = Config.get("Notify", "SendTaskResultTime")
    if result_time == "任何时刻":
        return True

    return result_time == "仅失败时" and message["uncompleted_count"] != 0


def user_statistic_targets(user_config: Any | None) -> list[NotifyTarget]:
    """返回已启用统计通知的用户目标。"""

    if (
        user_config is None
        or not user_config.get("Notify", "Enabled")
        or not user_config.get("Notify", "IfSendStatistic")
    ):
        return []
    return [user_target(user_config)]


def statistic_targets(
    user_config: Any | None,
    *,
    global_empty_policy: EmptyPolicy = "send",
) -> list[NotifyTarget]:
    """返回全局与用户级统计通知目标。"""

    targets = []
    if Config.get("Notify", "IfSendStatistic"):
        targets.append(global_target(empty_policy=global_empty_policy))
    targets.extend(user_statistic_targets(user_config))
    return targets


def _webhook_name(uid: str, webhook: Any) -> str:
    """返回便于定位失败配置的 Webhook 名称。"""

    try:
        return str(webhook.get("Info", "Name") or uid)
    except (AttributeError, KeyError):
        return uid


def _target_channels(target: NotifyTarget) -> dict[str, str]:
    """枚举目标的投递 ID 和显示名称，避免同名 Webhook 共用补发记录。"""

    channels = {}
    if target.system:
        channel = f"{target.name}系统"
        channels[channel] = channel
    if target.mail_to is not None:
        channel = f"{target.name}邮件"
        channels[channel] = channel
    if target.serverchan_key is not None:
        channel = f"{target.name} ServerChan"
        channels[channel] = channel
    if target.cmcc_newmsg_api_key is not None:
        channel = f"{target.name} 中国移动新消息"
        channels[channel] = channel
    for uid, webhook in target.webhooks:
        channels[f"{target.name} Webhook {uid}"] = (
            f"{target.name} Webhook {_webhook_name(uid, webhook)}"
        )
    if target.koishi:
        channel = f"{target.name} Koishi"
        channels[channel] = channel
    if target.openclaw_weixin:
        channel = f"{target.name} 微信（iLink）"
        channels[channel] = channel
    if target.openclaw_qq:
        channel = f"{target.name} QQ（官方机器人）"
        channels[channel] = channel
    return channels


async def _send(
    channel: str,
    send: Callable[[], Awaitable[Any]],
    *,
    attempts: int,
    retry_delay: float,
) -> bool:
    """发送单个渠道，并把异常和显式 False 都视作失败。"""

    for attempt in range(1, attempts + 1):
        try:
            result = await send()
            if result is False:
                raise RuntimeError("通知渠道返回失败状态")
            return True
        except Exception as exc:
            if attempt == attempts:
                logger.warning(f"{channel}通知发送失败: {exc}")
                break
            logger.warning(f"{channel}通知发送失败，将重试: {exc}")
            if retry_delay > 0:
                await asyncio.sleep(retry_delay)
    return False


def _recipient_action(
    value: str,
    policy: EmptyPolicy,
    *,
    channel: str,
    hint: str,
) -> tuple[bool, bool]:
    """返回是否发送，以及跳过是否应记为失败。"""

    if value or policy == "send":
        return True, False
    if policy == "warn":
        logger.warning(f"{hint}为空，无法发送{channel}通知")
        return False, True
    return False, False


async def dispatch(
    payload: NotifyPayload,
    targets: Iterable[NotifyTarget],
    *,
    attempts: int = 1,
    retry_delay: float = 0,
    skip_channels: Iterable[str] = (),
    skip_channel_ids: Iterable[str] = (),
) -> DispatchResult:
    """向所有目标分发通知，返回实际尝试/成功/失败渠道。

    ``skip_channels`` 中的渠道不会被发送（也不计入尝试次数），用于签到汇总
    等场景只向尚未送达的渠道重试，避免已成功渠道收到重复内容。
    ``skip_channel_ids`` 按稳定 ID 跳过，不受 Webhook 同名或改名影响。
    """

    if attempts < 1:
        raise ValueError("通知发送次数必须大于 0")

    skip = set(skip_channels)
    skip_ids = set(skip_channel_ids)
    succeeded: list[str] = []
    succeeded_ids: list[str] = []
    failed: list[str] = []
    attempted = 0

    async def attempt(
        channel: str,
        send: Callable[[], Awaitable[Any]],
        *,
        channel_id: str | None = None,
    ) -> None:
        nonlocal attempted
        delivery_id = channel_id or channel
        if channel in skip or delivery_id in skip_ids:
            return
        attempted += 1
        if await _send(channel, send, attempts=attempts, retry_delay=retry_delay):
            succeeded.append(channel)
            succeeded_ids.append(delivery_id)
        else:
            failed.append(channel)

    def miss(channel: str) -> None:
        nonlocal attempted
        if channel in skip or channel in skip_ids:
            return
        attempted += 1
        failed.append(channel)

    for target in targets:
        if target.system:
            await attempt(
                f"{target.name}系统",
                lambda: Notify.push_plyer(
                    title=payload.system_title or payload.title,
                    message=payload.system_message or payload.system_content,
                    ticker=payload.system_ticker or payload.title,
                    t=payload.system_timeout,
                ),
            )

        if target.mail_to is not None:
            channel = f"{target.name}邮件"
            should_send, missing = _recipient_action(
                target.mail_to,
                target.empty_policy,
                channel=channel,
                hint=f"{target.name}邮箱地址",
            )
            if missing:
                miss(channel)
            if should_send:
                await attempt(
                    channel,
                    lambda t=target: Notify.send_mail(
                        mode=payload.email_mode,
                        title=payload.title,
                        content=payload.email_content,
                        to_address=t.mail_to,
                    ),
                )

        if target.serverchan_key is not None:
            channel = f"{target.name} ServerChan"
            should_send, missing = _recipient_action(
                target.serverchan_key,
                target.empty_policy,
                channel=channel,
                hint=f"{target.name}ServerChan 密钥",
            )
            if missing:
                miss(channel)
            if should_send:
                await attempt(
                    channel,
                    lambda t=target: Notify.ServerChanPush(
                        title=payload.title,
                        content=payload.serverchan_content,
                        send_key=t.serverchan_key,
                    ),
                )

        if target.cmcc_newmsg_api_key is not None:
            channel = f"{target.name} 中国移动新消息"
            should_send, missing = _recipient_action(
                target.cmcc_newmsg_api_key,
                target.empty_policy,
                channel=channel,
                hint=f"{target.name}中国移动新消息 API Key",
            )
            if missing:
                miss(channel)
            if should_send:
                await attempt(
                    channel,
                    lambda t=target: Notify.send_cmcc_newmsg(
                        title=payload.title,
                        content=payload.cmcc_newmsg_content,
                        api_key=t.cmcc_newmsg_api_key,
                    ),
                )

        for uid, webhook in target.webhooks:
            await attempt(
                f"{target.name} Webhook {_webhook_name(uid, webhook)}",
                lambda w=webhook: Notify.WebhookPush(
                    title=payload.title,
                    content=payload.webhook_content_for(w),
                    image_base64=payload.webhook_image_base64 or "",
                    webhook=w,
                ),
                channel_id=f"{target.name} Webhook {uid}",
            )

        if target.koishi:
            await attempt(
                f"{target.name} Koishi",
                lambda: (
                    Notify.send_koishi(
                        payload.koishi_content,
                        msgtype=payload.koishi_msgtype,
                    )
                    if payload.koishi_msgtype != "text"
                    else Notify.send_koishi(payload.koishi_content)
                ),
            )

        if target.openclaw_weixin:
            await attempt(
                f"{target.name} 微信（iLink）",
                lambda: Notify.send_openclaw_weixin(
                    title=payload.title,
                    content=payload.openclaw_weixin_content,
                ),
            )

        if target.openclaw_qq:
            await attempt(
                f"{target.name} QQ（官方机器人）",
                lambda: Notify.send_openclaw_qq(
                    title=payload.title,
                    content=payload.openclaw_qq_content,
                ),
            )

    return DispatchResult(
        attempted=attempted,
        succeeded=tuple(succeeded),
        failed=tuple(failed),
        succeeded_ids=tuple(succeeded_ids),
    )


async def dispatch_task_report(
    payload: NotifyPayload,
    targets: list[NotifyTarget],
    task_info: object | None,
    *,
    summary_text: str = "",
    attempts: int = 1,
    retry_delay: float = 0,
) -> DispatchResult:
    """统一附加社区结果，并按渠道维护任务报告的投递状态。

    专项只提供原始报告与任务信息。旧调用传入的 summary_text 继续兼容，
    已送达摘要的渠道接收后续脚本报告时不再重复摘要。
    """

    # 社区渲染器复用 NotifyPayload，按需导入以避免模块初始化循环。
    from app.tools.community_notify import (
        append_community_summary_html,
        append_task_community_summary,
        detect_community_notification_format,
        mark_task_community_summary_consumed,
    )

    delivered = set(getattr(task_info, "game_sign_summary_delivered", ()))
    if summary_text:
        clean_payload = replace(
            payload,
            text=payload.text.replace(summary_text, "").rstrip(),
            html=(
                payload.html.replace(summary_text, "").rstrip()
                if payload.html is not None
                else None
            ),
        )
    else:
        clean_payload = payload
        if task_info is not None:
            summary_text = append_task_community_summary(task_info, "").strip()
        if summary_text:
            summary_markdown = append_task_community_summary(
                task_info, "", output_format="markdown"
            ).strip()
            serverchan_body = payload.serverchan_content
            serverchan_summary = summary_markdown
            if payload.serverchan_text is None and payload.markdown_text is None:
                # 默认签名仍放在整份报告末尾，社区摘要只负责自己的格式。
                serverchan_body = replace(
                    payload, append_signature=False
                ).serverchan_content
                if payload.append_signature:
                    serverchan_summary += f"{payload.signature_sep}{SIGNATURE}"
            payload = replace(
                payload,
                text=f"{payload.text}\n\n{summary_text}",
                html=(
                    append_community_summary_html(payload.html, summary_text)
                    if payload.html is not None
                    else None
                ),
                serverchan_text=f"{serverchan_body}\n\n{serverchan_summary}",
                markdown_text=(
                    f"{payload.markdown_text}\n\n{summary_markdown}"
                    if payload.markdown_text is not None
                    else None
                ),
                webhook_text=(
                    f"{payload.webhook_text}\n\n"
                    + (
                        summary_markdown
                        if detect_community_notification_format(payload.webhook_text)
                        == "markdown"
                        else summary_text
                    )
                    if payload.webhook_text is not None
                    else None
                ),
                koishi_text=(
                    append_community_summary_html(payload.koishi_text, summary_text)
                    if payload.koishi_text is not None
                    and payload.koishi_msgtype == "html"
                    else f"{payload.koishi_text}\n\n{summary_text}"
                    if payload.koishi_text is not None
                    else None
                ),
                system_message=(
                    f"{payload.system_message}\n\n{summary_text}"
                    if payload.system_message is not None
                    else None
                ),
            )

    if not summary_text:
        result = await dispatch(
            payload, targets, attempts=attempts, retry_delay=retry_delay
        )
    else:
        channels = {
            channel for target in targets for channel in _target_channels(target)
        }
        with_summary = await dispatch(
            payload,
            targets,
            attempts=attempts,
            retry_delay=retry_delay,
            skip_channel_ids=delivered,
        )
        # 只给本轮开始前已送达摘要的渠道发原始报告，避免同一轮发送两次。
        without_summary = (
            await dispatch(
                clean_payload,
                targets,
                attempts=attempts,
                retry_delay=retry_delay,
                skip_channel_ids=channels - delivered,
            )
            if delivered & channels
            else DispatchResult()
        )
        delivered.update(with_summary.succeeded_ids)
        if task_info is not None:
            setattr(task_info, "game_sign_summary_delivered", delivered)
            setattr(task_info, "game_sign_summary_pending", with_summary.failed)
            if delivered & channels and not with_summary.failed:
                mark_task_community_summary_consumed(task_info)
        result = DispatchResult(
            attempted=with_summary.attempted + without_summary.attempted,
            succeeded=with_summary.succeeded + without_summary.succeeded,
            failed=with_summary.failed + without_summary.failed,
            succeeded_ids=with_summary.succeeded_ids + without_summary.succeeded_ids,
        )

    await _publish_task_notification_failure(task_info, result)
    return result


async def _publish_task_notification_failure(
    task_info: object | None, result: DispatchResult
) -> None:
    """把任务报告的渠道失败同步提示到当前任务页面。"""

    if not result.failed or task_info is None:
        return
    task_id = getattr(task_info, "task_id", None)
    if not task_id:
        return

    from app.core.ws import Publisher, protocol
    from app.models.schema import WSTaskNoticeData

    failed_channels = tuple(dict.fromkeys(result.failed))
    title = "部分通知发送失败" if result.succeeded else "通知发送失败"
    message = f"{title}：{'、'.join(failed_channels)}"
    try:
        await Publisher.send(
            id=str(task_id),
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="warning", message=message),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"发送通知失败提示到前端时出现异常: {exc}")


async def send_test_notification() -> DispatchResult:
    """向全部已启用的全局渠道发送测试通知。"""

    text = (
        "这是 AUTO-MAS 外部通知测试信息。如果你看到了这段内容，说明 AUTO-MAS "
        "的通知功能已经正确配置且可以正常工作！"
    )
    return await dispatch(
        NotifyPayload(
            title="AUTO-MAS测试通知",
            text=text,
            append_signature=False,
            email_mode="文本",
            koishi_text=text,
            system_ticker="测试通知",
            system_timeout=3,
        ),
        [global_target(include_system=True, empty_policy="warn")],
    )
