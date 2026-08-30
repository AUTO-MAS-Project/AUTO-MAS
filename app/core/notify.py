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
`app.services.notification` 只保留具体渠道的传输实现。
"""

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal

from app.core.config import Config
from app.services.notification import Notify
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
    koishi_text: str | None = None
    system_ticker: str | None = None
    system_timeout: int = 5

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
        text = self.text.replace("\n", "\n\n")
        if not self.append_signature:
            return text
        return f"{text}{self.signature_sep}{SIGNATURE}"

    @property
    def webhook_content(self) -> str:
        """返回 Webhook 正文。"""

        return self.signed_text

    @property
    def koishi_content(self) -> str:
        """返回 Koishi 正文。"""

        if self.koishi_text is not None:
            return self.koishi_text
        return f"{self.title}\n\n{self.signed_text}"

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
    webhooks: Iterable[tuple[str, Any]] = ()
    koishi: bool = False
    empty_policy: EmptyPolicy = "send"


def _webhooks(config: Any) -> tuple[tuple[str, Any], ...]:
    """读取配置中的 Webhook，并保留可识别的 ID。"""

    return tuple((str(uid), webhook) for uid, webhook in config.items())


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
        webhooks=_webhooks(Config.Notify_CustomWebhooks),
        koishi=bool(Config.get("Notify", "IfKoishiSupport")),
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


def should_send_result(message: dict) -> bool:
    """判断代理结果是否满足全局推送时机。"""

    if message.get("game_sign_summary", False):
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


def _webhook_name(uid: str, webhook: Any) -> str:
    """返回便于定位失败配置的 Webhook 名称。"""

    try:
        return str(webhook.get("Info", "Name") or uid)
    except (AttributeError, KeyError):
        return uid


async def dispatch(
    payload: NotifyPayload,
    targets: Iterable[NotifyTarget],
    *,
    attempts: int = 1,
    retry_delay: float = 0,
) -> list[str]:
    """向所有目标分发通知，并返回发送失败的渠道名。"""

    if attempts < 1:
        raise ValueError("通知发送次数必须大于 0")

    failed: list[str] = []
    for target in targets:
        if target.system:
            channel = f"{target.name}系统"
            if not await _send(
                channel,
                lambda: Notify.push_plyer(
                    title=payload.title,
                    message=payload.system_content,
                    ticker=payload.system_ticker or payload.title,
                    t=payload.system_timeout,
                ),
                attempts=attempts,
                retry_delay=retry_delay,
            ):
                failed.append(channel)

        if target.mail_to is not None:
            channel = f"{target.name}邮件"
            should_send, missing = _recipient_action(
                target.mail_to,
                target.empty_policy,
                channel=channel,
                hint=f"{target.name}邮箱地址",
            )
            if missing:
                failed.append(channel)
            if should_send and not await _send(
                channel,
                lambda t=target: Notify.send_mail(
                    mode=payload.email_mode,
                    title=payload.title,
                    content=payload.email_content,
                    to_address=t.mail_to,
                ),
                attempts=attempts,
                retry_delay=retry_delay,
            ):
                failed.append(channel)

        if target.serverchan_key is not None:
            channel = f"{target.name} ServerChan"
            should_send, missing = _recipient_action(
                target.serverchan_key,
                target.empty_policy,
                channel=channel,
                hint=f"{target.name}ServerChan 密钥",
            )
            if missing:
                failed.append(channel)
            if should_send and not await _send(
                channel,
                lambda t=target: Notify.ServerChanPush(
                    title=payload.title,
                    content=payload.serverchan_content,
                    send_key=t.serverchan_key,
                ),
                attempts=attempts,
                retry_delay=retry_delay,
            ):
                failed.append(channel)

        for uid, webhook in target.webhooks:
            channel = f"{target.name} Webhook {_webhook_name(uid, webhook)}"
            if not await _send(
                channel,
                lambda w=webhook: Notify.WebhookPush(
                    title=payload.title,
                    content=payload.webhook_content,
                    webhook=w,
                ),
                attempts=attempts,
                retry_delay=retry_delay,
            ):
                failed.append(channel)

        if target.koishi:
            channel = f"{target.name} Koishi"
            if not await _send(
                channel,
                lambda: Notify.send_koishi(payload.koishi_content),
                attempts=attempts,
                retry_delay=retry_delay,
            ):
                failed.append(channel)

    return failed


async def send_test_notification() -> list[str]:
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
