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

"""通知中间层: 桥接各脚本的任务报告与具体推送渠道。

各脚本 `tools/notify.py` 只负责把自己的 message 字典渲染成 `NotifyPayload`（纯文本
正文 + HTML 正文）, 本模块负责决定推给谁（全局 / 用户）以及怎么发。渠道扇出、签名
拼接、ServerChan 换行变换、单渠道失败隔离都只在这里实现一份。
"""

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal

from app.core import Config
from app.services import Notify
from app.utils import get_logger

logger = get_logger("通知中间层")

SIGNATURE = "AUTO-MAS 敬上"


@dataclass
class NotifyPayload:
    """一份已渲染完成的报告正文。"""

    title: str
    text: str
    html: str
    # MAA 的签名只空一行, 其余脚本空两行; 保持各自历史行为
    signature_sep: str = "\n\n"

    @property
    def signed_text(self) -> str:
        """纯文本正文 + 签名, 用于 Webhook。"""

        return f"{self.text}{self.signature_sep}{SIGNATURE}"

    @property
    def signed_serverchan(self) -> str:
        """ServerChan 的换行是两个换行符, 故而将 \\n 替换为 \\n\\n。"""

        serverchan_text = self.text.replace("\n", "\n\n")
        return f"{serverchan_text}{self.signature_sep}{SIGNATURE}"

    @property
    def signed_koishi(self) -> str:
        """标题 + 纯文本正文 + 签名, 用于 Koishi。"""

        return f"{self.title}\n\n{self.text}{self.signature_sep}{SIGNATURE}"


# 收件人配置为空时的处理策略。send 为历史全局行为（照发, 由渠道自己报错）,
# warn 用于用户级配置（提示用户没填）, skip 用于已经做过非空校验的全局渠道。
EmptyPolicy = Literal["send", "warn", "skip"]


@dataclass
class NotifyTarget:
    """一组推送渠道及其配置来源。

    `mail_to` / `serverchan_key` 为 None 表示该渠道未启用; 为空字符串表示已启用但
    没填配置, 具体怎么处理由 `empty_policy` 决定。
    """

    name: str
    mail_to: str | None = None
    serverchan_key: str | None = None
    webhooks: Iterable[Any] = ()
    koishi: bool = False
    empty_policy: EmptyPolicy = "send"


def global_target(*, skip_empty_recipient: bool = False) -> NotifyTarget:
    """全局通知渠道, 是唯一支持 Koishi 的一级。

    Args:
        skip_empty_recipient: 收件人为空时静默跳过而非照发, 供 HSR 保持原有校验。
    """

    return NotifyTarget(
        name="全局",
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
        webhooks=Config.Notify_CustomWebhooks.values(),
        koishi=bool(Config.get("Notify", "IfKoishiSupport")),
        empty_policy="skip" if skip_empty_recipient else "send",
    )


def user_target(user_config: Any) -> NotifyTarget:
    """用户独立通知渠道; 不含 Koishi。"""

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
        webhooks=user_config.Notify_CustomWebhooks.values(),
        empty_policy="warn",
    )


def should_send_result(message: dict) -> bool:
    """代理结果是否满足全局推送时机; 有待发的签到汇总时无条件推送。"""

    if message.get("game_sign_summary", False):
        return True

    result_time = Config.get("Notify", "SendTaskResultTime")
    if result_time == "任何时刻":
        return True

    return result_time == "仅失败时" and message["uncompleted_count"] != 0


def user_statistic_targets(user_config: Any | None) -> list[NotifyTarget]:
    """用户级统计目标; 用户未启用统计通知时为空。"""

    if (
        user_config is None
        or not user_config.get("Notify", "Enabled")
        or not user_config.get("Notify", "IfSendStatistic")
    ):
        return []

    return [user_target(user_config)]


def statistic_targets(
    user_config: Any | None, *, skip_empty_recipient: bool = False
) -> list[NotifyTarget]:
    """统计信息的推送目标: 全局受 IfSendStatistic 控制, 用户级需自行启用。"""

    targets = []
    if Config.get("Notify", "IfSendStatistic"):
        targets.append(global_target(skip_empty_recipient=skip_empty_recipient))
    targets.extend(user_statistic_targets(user_config))
    return targets


async def _send(channel: str, send: Callable[[], Awaitable[Any]]) -> bool:
    """发送单个渠道; 失败只记录, 不影响后续渠道。"""

    try:
        await send()
        return True
    except Exception as e:
        logger.warning(f"{channel}通知发送失败: {e}")
        return False


def _should_send(value: str, policy: EmptyPolicy, channel: str, hint: str) -> bool:
    """按空值策略判断某个已启用渠道是否真的要发。"""

    if value or policy == "send":
        return True
    if policy == "warn":
        logger.warning(f"{hint}为空, 无法发送{channel}通知")
    return False


async def dispatch(
    payload: NotifyPayload, targets: Iterable[NotifyTarget]
) -> list[str]:
    """把一份报告推送到给定的所有目标。

    Args:
        payload: 已渲染的报告正文。
        targets: 推送目标, 通常来自 `global_target` / `statistic_targets`。

    Returns:
        发送失败的渠道名列表; 全部成功时为空。
    """

    failed: list[str] = []

    for target in targets:
        mail_channel = f"{target.name}邮件"
        if target.mail_to is not None and _should_send(
            target.mail_to, target.empty_policy, mail_channel, f"{target.name}邮箱地址"
        ):
            if not await _send(
                mail_channel,
                lambda t=target: Notify.send_mail(
                    "网页", payload.title, payload.html, t.mail_to
                ),
            ):
                failed.append(mail_channel)

        serverchan_channel = f"{target.name} ServerChan"
        if target.serverchan_key is not None and _should_send(
            target.serverchan_key,
            target.empty_policy,
            serverchan_channel,
            f"{target.name}ServerChan密钥",
        ):
            if not await _send(
                serverchan_channel,
                lambda t=target: Notify.ServerChanPush(
                    payload.title, payload.signed_serverchan, t.serverchan_key
                ),
            ):
                failed.append(serverchan_channel)

        webhook_channel = f"{target.name}自定义 Webhook"
        for webhook in target.webhooks:
            if not await _send(
                webhook_channel,
                lambda w=webhook: Notify.WebhookPush(
                    payload.title, payload.signed_text, w
                ),
            ):
                failed.append(webhook_channel)

        if target.koishi:
            koishi_channel = f"{target.name} Koishi"
            if not await _send(
                koishi_channel,
                lambda: Notify.send_koishi(payload.signed_koishi),
            ):
                failed.append(koishi_channel)

    return failed
