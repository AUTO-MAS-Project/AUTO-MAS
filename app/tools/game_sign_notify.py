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


from html import escape

from app.core import Config
from app.core.notify import NotifyPayload, dispatch, global_target
from app.utils.logger import get_logger

logger = get_logger("游戏签到通知")

NOTIFICATION_SEND_ATTEMPTS = 2
NOTIFICATION_RETRY_DELAY_SECONDS = 1
_SUCCESS_STATUSES = {"成功", "已签到"}
_PLATFORM_ORDER = ("森空岛", "米游社", "库街区", "塔吉多", "云异环")


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


def format_game_sign_notification(results: list[dict]) -> str:
    """按社区分组生成手动/启动时签到通知正文（不含通知标题）。"""

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
        lines.extend([f"{marker}{platform}({success_count}/{total}):", ""])
        for item in items:
            lines.append(f"- {_format_notification_item(item)}")

    lines.extend(["", "AUTO-MAS 敬上"])
    return "\n".join(lines)


def format_game_sign_task_summary(results: list[dict]) -> str:
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


def get_task_game_sign_summary(task_info: object) -> str:
    """读取尚未发送的任务签到汇总。"""

    if getattr(task_info, "game_sign_summary_consumed", False):
        return ""

    results = list(getattr(task_info, "game_sign_results", []) or [])
    if not results:
        return ""

    return format_game_sign_task_summary(results)


def mark_task_game_sign_summary_consumed(task_info: object) -> None:
    """在任务报告发送完成后标记签到汇总已消费。"""

    setattr(task_info, "game_sign_summary_consumed", True)


def finalize_task_game_sign_notification(
    task_info: object,
    has_summary: bool,
    failed_channels: list[str],
) -> None:
    """记录部分失败，并在全部渠道成功后消费签到汇总。"""

    if failed_channels:
        logger.warning(f"推送代理结果部分失败: {'、'.join(failed_channels)}")
    if has_summary and not failed_channels:
        mark_task_game_sign_summary_consumed(task_info)


def append_task_game_sign_summary(task_info: object, result: str) -> str:
    """将尚未发送的签到汇总附加到任务报告。"""

    if not Config.ToolsConfig.get("GameSign", "NotifyEnabled"):
        return result

    summary = get_task_game_sign_summary(task_info)
    return f"{result}\n\n{summary}" if summary else result


async def push_game_sign_notification(results: list[dict]) -> list[str]:
    """推送手动或启动时触发的游戏签到结果通知。"""
    results = _notification_results(results)
    if not results:
        return []

    title = "社区签到通知:"
    plain_text = format_game_sign_notification(results)

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
    return await dispatch(
        NotifyPayload(
            title=title,
            text=plain_text,
            html=html_content,
            append_signature=False,
            serverchan_text=plain_text,
            koishi_text=f"{title}\n{plain_text}",
        ),
        [global_target(include_system=True, empty_policy="warn")],
        attempts=NOTIFICATION_SEND_ATTEMPTS,
        retry_delay=NOTIFICATION_RETRY_DELAY_SECONDS,
    )
