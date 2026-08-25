#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""通知渠道分发（各脚本 notify.py 共用）。

由 app/task/M9A/tools/notify.py 的 _send_to_all_global_channels /
_send_to_user_channels 提升而来。各脚本的「消息文本构造」与「模板选择」是真实业务
差异, 仍留在各自的 notify.py 里; 这里只负责「查开关 → 发邮件 / ServerChan /
遍历 webhook / Koishi」这段 8 个脚本逐行同构的 fan-out。

三个关键字参数的默认值 = 迁移前的多数派行为, 少数派显式传值, 因此迁移是行为等价的:

- ``sig_sep``: 签名前的分隔符。MAA 用 ``"\\n"``, 其余 7 个用默认 ``"\\n\\n"``。
- ``isolate_failures``: 单渠道抛异常时是否吞掉并继续后续渠道。仅 M9A 传 ``True``。
- ``require_recipient``: 全局邮件/ServerChan 是否要求收件人非空才发。仅 HSR 传 ``True``。

这三处差异都由 tests/task/test_notify_channels_parity.py 的基线锁定。要统一它们
（例如让所有脚本都用双换行、都开失败隔离）属于**行为变更**, 请单独提 PR 并重新生成基线。
"""

from typing import Any, Awaitable

from app.core import Config
from app.services import Notify
from app.utils import get_logger

logger = get_logger("通知渠道")

SIGNATURE = "AUTO-MAS 敬上"


async def _send(channel: str, coro: Awaitable[None], isolate: bool) -> None:
    """发送单个渠道; ``isolate`` 为真时失败只记日志, 不影响后续渠道。"""

    if not isolate:
        await coro
        return
    try:
        await coro
    except Exception as e:
        logger.warning(f"{channel} 通知发送失败: {e}")


async def send_to_global_channels(
    title: str,
    message_text: str,
    message_html: str,
    *,
    sig_sep: str = "\n\n",
    isolate_failures: bool = False,
    require_recipient: bool = False,
) -> None:
    """向所有已启用的全局通知渠道推送。

    Args:
        title: 通知标题。
        message_text: 纯文本正文。
        message_html: HTML 正文（邮件用）。
        sig_sep: 签名前的分隔符, 见模块 docstring。
        isolate_failures: 单渠道失败是否隔离, 见模块 docstring。
        require_recipient: 邮件/ServerChan 是否要求收件人非空, 见模块 docstring。
    """

    # ServerChan 的换行是两个换行符, 故而将 \n 替换为 \n\n
    text_sig = f"{message_text}{sig_sep}{SIGNATURE}"
    serverchan_sig = f"{message_text.replace('\n', '\n\n')}{sig_sep}{SIGNATURE}"

    to_address = Config.get("Notify", "ToAddress")
    if Config.get("Notify", "IfSendMail") and (not require_recipient or to_address):
        await _send(
            "全局邮件",
            Notify.send_mail("网页", title, message_html, to_address),
            isolate_failures,
        )

    serverchan_key = Config.get("Notify", "ServerChanKey")
    if Config.get("Notify", "IfServerChan") and (
        not require_recipient or serverchan_key
    ):
        await _send(
            "全局 ServerChan",
            Notify.ServerChanPush(title, serverchan_sig, serverchan_key),
            isolate_failures,
        )

    for webhook in Config.Notify_CustomWebhooks.values():
        await _send(
            "全局自定义 Webhook",
            Notify.WebhookPush(title, text_sig, webhook),
            isolate_failures,
        )

    if Config.get("Notify", "IfKoishiSupport"):
        await _send(
            "全局 Koishi",
            Notify.send_koishi(f"{title}\n\n{text_sig}"),
            isolate_failures,
        )


async def send_to_user_channels(
    title: str,
    message_text: str,
    message_html: str,
    user_config: Any,
    *,
    sig_sep: str = "\n\n",
    isolate_failures: bool = False,
) -> None:
    """向用户独立配置的通知渠道推送。

    调用方负责先校验 ``Notify.Enabled`` 与对应的内容开关（如 ``IfSendStatistic``）;
    这里只做渠道分发。收件人为空时记 warning 并跳过该渠道——8 个脚本行为一致。

    Args:
        title: 通知标题。
        message_text: 纯文本正文。
        message_html: HTML 正文（邮件用）。
        user_config: 用户配置对象, 需支持 ``get(group, key)`` 与 ``Notify_CustomWebhooks``。
        sig_sep: 签名前的分隔符, 见模块 docstring。
        isolate_failures: 单渠道失败是否隔离, 见模块 docstring。
    """

    text_sig = f"{message_text}{sig_sep}{SIGNATURE}"
    serverchan_sig = f"{message_text.replace('\n', '\n\n')}{sig_sep}{SIGNATURE}"

    if user_config.get("Notify", "IfSendMail"):
        to_address = user_config.get("Notify", "ToAddress")
        if to_address:
            await _send(
                "用户邮件",
                Notify.send_mail("网页", title, message_html, to_address),
                isolate_failures,
            )
        else:
            logger.warning("用户邮箱地址为空, 无法发送用户单独的邮件通知")

    if user_config.get("Notify", "IfServerChan"):
        serverchan_key = user_config.get("Notify", "ServerChanKey")
        if serverchan_key:
            await _send(
                "用户 ServerChan",
                Notify.ServerChanPush(title, serverchan_sig, serverchan_key),
                isolate_failures,
            )
        else:
            logger.warning("用户ServerChan密钥为空, 无法发送用户单独的ServerChan通知")

    for webhook in user_config.Notify_CustomWebhooks.values():
        await _send(
            "用户自定义 Webhook",
            Notify.WebhookPush(title, text_sig, webhook),
            isolate_failures,
        )
