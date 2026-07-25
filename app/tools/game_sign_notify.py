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


from app.core import Config
from app.services import Notify
from app.utils.logger import get_logger

logger = get_logger("游戏签到通知")


async def push_game_sign_notification(results: list[dict]) -> None:
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
    """
    if not results:
        return

    title = "📅 游戏社区签到"

    # 按别名分组（别名 = account 中 '/' 前的部分）
    grouped: dict[str, list[dict]] = {}
    for item in results:
        account = item.get("account", "未知")
        alias = account.split("/")[0] if "/" in account else account
        if alias not in grouped:
            grouped[alias] = []
        grouped[alias].append(item)

    # 构建纯文本消息
    lines = []
    success_count = 0
    fail_count = 0

    for alias, items in grouped.items():
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
    for alias, items in grouped.items():
        html_lines.append(f'<p><strong>No.{alias}:</strong></p>')
        html_lines.append('<ul>')
        for item in items:
            game = item.get("game", "未知")
            status = item.get("status", "失败")
            reward = item.get("reward", "")
            reason = item.get("reason", "")

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

    # 分发到所有已启用的渠道
    try:
        # 系统通知
        await Notify.push_plyer(title, plain_text, title, 5)
    except Exception as e:
        logger.warning(f"推送系统通知失败: {e}")

    try:
        # 邮件通知
        if Config.get("Notify", "IfSendMail"):
            to_address = Config.get("Notify", "ToAddress")
            if to_address:
                await Notify.send_mail("网页", title, html_content, to_address)
    except Exception as e:
        logger.warning(f"推送邮件通知失败: {e}")

    try:
        # Server酱通知
        if Config.get("Notify", "IfServerChan"):
            send_key = Config.get("Notify", "ServerChanKey")
            if send_key:
                await Notify.ServerChanPush(title, plain_text, send_key)
    except Exception as e:
        logger.warning(f"推送Server酱通知失败: {e}")

    try:
        # Webhook 通知
        for uid, webhook in Config.Notify_CustomWebhooks.items():
            if webhook.get("Info", "Enabled"):
                try:
                    await Notify.WebhookPush(title, plain_text, webhook)
                except Exception as e:
                    logger.warning(f"推送 Webhook {uid} 通知失败: {e}")
    except Exception as e:
        logger.warning(f"推送Webhook通知失败: {e}")

    try:
        # Koishi 通知
        if Config.get("Notify", "IfKoishiSupport"):
            await Notify.send_koishi(plain_text)
    except Exception as e:
        logger.warning(f"推送Koishi通知失败: {e}")
