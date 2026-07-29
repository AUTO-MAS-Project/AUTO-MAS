#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
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

#   Contact: DLmaster_361@163.com


import asyncio
from collections.abc import Awaitable, Callable
from html import escape

from app.core import Config
from app.services import Notify
from app.utils.logger import get_logger

logger = get_logger("游戏签到通知")

NOTIFICATION_SEND_ATTEMPTS = 2
NOTIFICATION_RETRY_DELAY_SECONDS = 1


async def _send_notification_channel(
    channel_name: str,
    send: Callable[[], Awaitable[bool | None]],
) -> bool:
    """发送单个通知渠道，失败时重试一次。"""
    for attempt in range(1, NOTIFICATION_SEND_ATTEMPTS + 1):
        try:
            result = await send()
            if result is False:
                raise RuntimeError("通知渠道返回失败状态")
            return True
        except Exception as e:
            if attempt < NOTIFICATION_SEND_ATTEMPTS:
                logger.warning(f"{channel_name}通知发送失败，将重试: {e}")
                await asyncio.sleep(NOTIFICATION_RETRY_DELAY_SECONDS)
            else:
                logger.warning(f"{channel_name}通知重试后仍失败: {e}")
    return False


async def push_game_sign_notification(results: list[dict]) -> list[str]:
    """推送游戏签到结果通知

    遵循 Skland-Sign-In 通知格式风格：
    - 标题：📅 游戏社区签到
    - 按别名分组：No.{别名}:
    - 成功：✅ 游戏名: 成功 (奖励)
    - 失败：❌ 游戏名: 失败 (原因)
    - 已签到：✅ 游戏名: 已签
    - 底部：AUTO-MAS 敬上

    Args:
        results: 签到结果列表

    Returns:
        重试后仍发送失败的通知渠道。
    """
    if not results:
        return []

    title = "📅 游戏社区签到"

    # 按账号 UID 和别名分组，避免同名账号合并
    grouped: dict[tuple[str, str], list[dict]] = {}
    for item in results:
        account = str(item.get("account", "未知"))
        alias = account.split("/")[0] if "/" in account else account
        account_uid = str(item.get("account_uid", ""))
        grouped.setdefault((account_uid, alias), []).append(item)

    # 构建纯文本消息
    lines = []
    success_count = 0
    fail_count = 0

    for (_, alias), items in grouped.items():
        lines.append(f"No.{alias}:")
        for item in items:
            game = item.get("game", "未知")
            status = item.get("status", "失败")
            reward = item.get("reward", "")
            reason = item.get("reason", "")

            if status == "成功":
                reward_text = f" ({reward})" if reward else ""
                lines.append(f"  ✅ {game}: 成功{reward_text}")
                success_count += 1
            elif status == "已签到":
                lines.append(f"  ✅ {game}: 已签")
                success_count += 1
            else:
                reason_text = f" ({reason})" if reason else ""
                lines.append(f"  ❌ {game}: 失败{reason_text}")
                fail_count += 1

    lines.append(f"\n共 {len(grouped)} 个账号，成功 {success_count}，失败 {fail_count}")
    lines.append("AUTO-MAS 敬上")

    plain_text = "\n".join(lines)

    # 构建 HTML 版本（用于邮件）
    html_lines = []
    for (_, alias), items in grouped.items():
        html_lines.append(f'<p><strong>No.{escape(alias)}:</strong></p>')
        html_lines.append('<ul>')
        for item in items:
            game = escape(str(item.get("game", "未知")))
            status = item.get("status", "失败")
            reward = escape(str(item.get("reward", "")))
            reason = escape(str(item.get("reason", "")))

            if status == "成功":
                reward_text = f" ({reward})" if reward else ""
                html_lines.append(
                    f'<li><span style="background:green;color:white;padding:2px 6px;'
                    f'border-radius:3px;">✅</span> '
                    f"{game}: 成功{reward_text}</li>"
                )
            elif status == "已签到":
                html_lines.append(
                    f'<li><span style="background:green;color:white;padding:2px 6px;'
                    f'border-radius:3px;">✅</span> '
                    f"{game}: 已签</li>"
                )
            else:
                reason_text = f" ({reason})" if reason else ""
                html_lines.append(
                    f'<li><span style="background:red;color:white;padding:2px 6px;'
                    f'border-radius:3px;">❌</span> '
                    f"{game}: 失败{reason_text}</li>"
                )
        html_lines.append('</ul>')

    html_lines.append(
        f"<p>共 {len(grouped)} 个账号，成功 {success_count}，失败 {fail_count}</p>"
    )
    html_lines.append("<p>AUTO-MAS 敬上</p>")
    html_content = "".join(html_lines)
    failed_channels: list[str] = []

    # 分发到所有已启用的渠道
    if not await _send_notification_channel(
        "系统",
        lambda: Notify.push_plyer(
            title=title,
            message=plain_text,
            ticker=title,
            t=5,
        ),
    ):
        failed_channels.append("系统")

    # 邮件通知
    if Config.get("Notify", "IfSendMail"):
        to_address = Config.get("Notify", "ToAddress")
        if not to_address:
            logger.warning("邮件通知已启用，但未配置收件地址")
            failed_channels.append("邮件")
        elif not await _send_notification_channel(
            "邮件",
            lambda: Notify.send_mail(
                mode="网页",
                title=title,
                content=html_content,
                to_address=to_address,
            ),
        ):
            failed_channels.append("邮件")

    # Server酱通知
    if Config.get("Notify", "IfServerChan"):
        send_key = Config.get("Notify", "ServerChanKey")
        if not send_key:
            logger.warning("Server酱通知已启用，但未配置 SendKey")
            failed_channels.append("Server酱")
        elif not await _send_notification_channel(
            "Server酱",
            lambda: Notify.ServerChanPush(
                title=title,
                content=plain_text,
                send_key=send_key,
            ),
        ):
            failed_channels.append("Server酱")

    # Webhook 通知
    try:
        for uid, webhook in Config.Notify_CustomWebhooks.items():
            if webhook.get("Info", "Enabled"):
                channel_name = f"Webhook {uid}"
                if not await _send_notification_channel(
                    channel_name,
                    lambda webhook=webhook: Notify.WebhookPush(
                        title=title,
                        content=plain_text,
                        webhook=webhook,
                    ),
                ):
                    failed_channels.append(channel_name)
    except Exception as e:
        logger.warning(f"读取 Webhook 通知配置失败: {e}")
        failed_channels.append("Webhook")

    # Koishi 通知
    if Config.get(
        "Notify", "IfKoishiSupport"
    ) and not await _send_notification_channel(
        "Koishi", lambda: Notify.send_koishi(plain_text)
    ):
        failed_channels.append("Koishi")

    return failed_channels
