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
from typing import Literal

from app.core import Config
from app.services import Notify
from app.utils.logger import get_logger

logger = get_logger("游戏社区通知")

NOTIFICATION_SEND_ATTEMPTS = 2
NOTIFICATION_RETRY_DELAY_SECONDS = 1
_SUCCESS_STATUSES = {"成功", "已签到"}
_PLATFORM_ORDER = ("森空岛", "米游社", "库街区", "塔吉多", "云异环")
NotificationBodyFormat = Literal["text", "markdown"]


def detect_community_notification_format(content: str) -> NotificationBodyFormat:
    """识别通知正文是否包含 Markdown 块级标记。"""

    for line in content.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("# ", "## ", "### ", "- ", "* ", "> ", "```")):
            return "markdown"
    return "markdown" if "**" in content else "text"


def _result_status_text(item: dict) -> str:
    """将单条签到结果转换为模板中的短状态。"""

    status = str(item.get("status", "失败"))
    if status == "已签到":
        return "已签"
    if status == "成功":
        return "签到成功"
    if status == "风控":
        return "签到失败-风控"

    reason = str(item.get("reason", "") or "").strip()
    if not reason or reason in {"失败", "签到失败"}:
        return "签到失败"
    if reason.startswith("签到失败-"):
        return reason
    return f"签到失败-{reason}"


def _result_account(item: dict) -> str:
    """返回优先使用角色名/UID 的账号标识。"""

    account = str(item.get("account", "") or "").strip()
    if account:
        return account
    account_uid = str(item.get("account_uid", "") or "").strip()
    return account_uid or "未知用户"


def _result_identity(item: dict) -> str:
    """生成通知中的用户标识，森空岛优先显示游戏名和真实昵称。"""

    account = _result_account(item)
    platform = str(item.get("platform", "未知") or "未知")
    game = str(item.get("game", "") or "").strip()
    if platform != "森空岛" or not game:
        return account

    nickname = account.split("/", 1)[0].strip()
    if nickname and nickname != "未知用户":
        return f"{game}({nickname})"
    return game


def _notification_results(results: list[dict]) -> list[dict]:
    """过滤没有实际签到角色的平台占位结果。"""

    return [item for item in results if not item.get("_notification_only")]


def _ordered_platforms(grouped: dict[str, list[dict]]) -> list[str]:
    """按通知模板固定社区顺序，并保留未知平台结果。"""

    return [
        *[platform for platform in _PLATFORM_ORDER if platform in grouped],
        *[platform for platform in grouped if platform not in _PLATFORM_ORDER],
    ]


def _format_notification_item(item: dict) -> str:
    """格式化通知列表中的一条签到结果。"""

    platform = str(item.get("platform", "未知") or "未知")
    status = _result_status_text(item)
    identity = _result_identity(item)
    if platform == "森空岛":
        return f"{identity}:{status}"

    game = str(item.get("game", "") or "").strip()
    game_text = f" {game}" if game else ""
    reward = str(item.get("reward", "") or "").strip()
    reward_text = f" {reward}" if platform == "云异环" and reward else ""
    return f"{identity}{game_text} {status}{reward_text}"


def format_community_notification(
    results: list[dict],
    *,
    output_format: NotificationBodyFormat = "markdown",
) -> str:
    """按社区分组生成通知正文，并显式支持文本与 Markdown。"""

    results = _notification_results(results)
    if not results:
        return ""

    grouped: dict[str, list[dict]] = {}
    for item in results:
        platform = str(item.get("platform", "未知") or "未知")
        grouped.setdefault(platform, []).append(item)

    lines: list[str] = []
    for platform in _ordered_platforms(grouped):
        items = grouped[platform]
        total = len(items)
        success_count = sum(
            1 for item in items if item.get("status") in _SUCCESS_STATUSES
        )
        marker = "✅" if total and success_count == total else "❌"
        if lines:
            lines.append("")
        heading = f"{marker}{platform}({success_count}/{total}):"
        if output_format == "markdown":
            heading = f"### {heading}"
        lines.extend([heading, ""])
        for item in items:
            prefix = "- " if output_format == "markdown" else "  "
            lines.append(f"{prefix}{_format_notification_item(item)}")

    lines.extend(["", "AUTO-MAS 敬上"])
    return "\n".join(lines)


def format_community_task_summary(results: list[dict]) -> str:
    """生成附加到 MAS 任务报告末尾的一行签到汇总。"""

    results = _notification_results(results)
    if not results:
        return ""

    grouped: dict[str, list[dict]] = {}
    for item in results:
        platform = str(item.get("platform", "未知") or "未知")
        grouped.setdefault(platform, []).append(item)

    parts = []
    previous_platform = None
    for platform in _ordered_platforms(grouped):
        for item in grouped[platform]:
            platform_prefix = f"{platform}-" if platform != previous_platform else ""
            label = f"{platform_prefix}{_result_identity(item)}"
            status = _result_status_text(item)
            if platform != "森空岛":
                game = str(item.get("game", "") or "").strip()
                if game:
                    label = f"{label} {game}"
            separator = ":" if platform == "森空岛" else " "
            parts.append(f"{label}{separator}{status}")
            previous_platform = platform

    return "签到情况: " + " | ".join(parts)


def get_task_community_summary(task_info: object) -> str:
    """读取尚未发送的社区签到汇总，兼容旧任务字段。"""

    consumed = (
        getattr(task_info, "community_summary_consumed", False)
        if hasattr(task_info, "community_summary_consumed")
        else getattr(task_info, "game_sign_summary_consumed", False)
    )
    if consumed:
        return ""

    results = (
        getattr(task_info, "community_results", [])
        if hasattr(task_info, "community_results")
        else getattr(task_info, "game_sign_results", [])
    )
    if not results:
        return ""

    return format_community_task_summary(list(results))


def mark_task_community_summary_consumed(task_info: object) -> None:
    """标记社区签到汇总已由任务报告消费。"""

    if hasattr(task_info, "community_summary_consumed"):
        setattr(task_info, "community_summary_consumed", True)
    else:
        setattr(task_info, "game_sign_summary_consumed", True)


def append_task_community_summary(task_info: object, result: str) -> str:
    """将尚未发送的社区签到汇总附加到任务报告。"""

    if not Config.ToolsConfig.get("GameSign", "NotifyEnabled"):
        return result

    summary = get_task_community_summary(task_info)
    return f"{result}\n\n{summary}" if summary else result


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


async def push_community_notification(results: list[dict]) -> list[str]:
    """推送手动或启动时触发的游戏社区结果通知。"""
    results = _notification_results(results)
    if not results:
        return []

    title = "社区签到通知:"
    plain_text = format_community_notification(results, output_format="text")
    markdown_text = format_community_notification(
        results,
        output_format="markdown",
    )
    channel_text = (
        markdown_text
        if detect_community_notification_format(markdown_text) == "markdown"
        else plain_text
    )

    # 邮件按同一正文生成 HTML，角色名和原因均需要转义。
    grouped: dict[str, list[dict]] = {}
    for item in results:
        platform = str(item.get("platform", "未知") or "未知")
        grouped.setdefault(platform, []).append(item)

    html_lines = []
    for platform in _ordered_platforms(grouped):
        items = grouped[platform]
        total = len(items)
        success_count = sum(
            1 for item in items if item.get("status") in _SUCCESS_STATUSES
        )
        marker = "✅" if total and success_count == total else "❌"
        html_lines.append(
            f"<p><strong>{marker}{escape(platform)}({success_count}/{total}):</strong></p>"
        )
        html_lines.append("<ul>")
        for item in items:
            html_lines.append(f"<li>{escape(_format_notification_item(item))}</li>")
        html_lines.append("</ul>")
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
                content=channel_text,
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
                        content=channel_text,
                        webhook=webhook,
                    ),
                ):
                    failed_channels.append(channel_name)
    except Exception as e:
        logger.warning(f"读取 Webhook 通知配置失败: {e}")
        failed_channels.append("Webhook")

    # Koishi 通知
    if Config.get("Notify", "IfKoishiSupport") and not await _send_notification_channel(
        "Koishi", lambda: Notify.send_koishi(f"{title}\n{plain_text}")
    ):
        failed_channels.append("Koishi")

    return failed_channels


__all__ = [
    "append_task_community_summary",
    "detect_community_notification_format",
    "format_community_notification",
    "format_community_task_summary",
    "get_task_community_summary",
    "mark_task_community_summary_consumed",
    "push_community_notification",
]
