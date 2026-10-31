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

from collections.abc import Sequence
from functools import cache

from app.core import Config
from app.core.notify import templates as _notification_template
from app.models.notification import (
    DeferredContent,
    NotificationImage,
    NotifyPayload,
    image_reference,
)
from app.utils import get_logger

logger = get_logger("MAA 通知工具")

# MAA 的签名只空一行, 与其余脚本不同
SIGNATURE_SEP = "\n"

# 喜报图片同时提供本地资源和官网 URL；缺少本地文件时，仍可在支持 URL 的表达中展示。
SIX_STAR_IMAGE_ID = "maa-six-star"
SIX_STAR_IMAGE_URL = "https://data.auto-mas.top/api/v1/files/auto-mas/Resource/arknights-six-star/download"


@cache
def _six_star_image() -> bytes | None:
    try:
        return (
            Config.resource_path / "images" / "notification" / "six_star.png"
        ).read_bytes()
    except OSError as exc:
        logger.warning(f"读取喜报配图失败，通知将使用可用的替代图片来源: {exc}")
        return None


def _statistic_text(message: dict) -> str:
    """拼装掉落、招募、培养进展与养成达成统计的纯文本正文。"""

    formatted = []
    if "drop_statistics" in message:
        for stage, items in message["drop_statistics"].items():
            formatted.append(f"掉落统计（{stage}）:")
            for item, quantity in items.items():
                formatted.append(f"  {item}: {quantity}")
    drop_text = "\n".join(formatted)

    formatted = ["招募统计:"]
    if "recruit_statistics" in message:
        for star, count in message["recruit_statistics"].items():
            formatted.append(f"  {star}: {count}")
    recruit_text = "\n".join(formatted)

    progress_text = (
        f"培养进展: {message['cultivate_progress']}\n"
        if message.get("cultivate_progress")
        else ""
    )
    # 本轮有干员达成养成目标时附一行；无则不占位
    cultivate_text = (
        f"养成达成: {message['cultivate_achievement']}\n"
        if message.get("cultivate_achievement")
        else ""
    )

    return (
        f"开始时间: {message['start_time']}\n"
        f"结束时间: {message['end_time']}\n"
        f"理智剩余: {message.get('sanity', '未知')}\n"
        f"回复时间: {message.get('sanity_full_at', '未知')}\n"
        f"MAA执行结果: {message['maa_result']}\n"
        f"{progress_text}"
        f"{cultivate_text}"
        f"{recruit_text}\n"
        f"{drop_text}"
    )


def build_statistics_payload(
    *, title: str, message: dict, images: Sequence[NotificationImage] = ()
) -> NotifyPayload:
    """构造专项统计正文，投递由注入的通知服务负责。"""

    return NotifyPayload(
        title=title,
        text=_statistic_text(message),
        html=_notification_template.deferred_notification_template(
            "MAA_statistics.html", message
        ),
        signature_sep=SIGNATURE_SEP,
        images=images,
    )


def build_recruitment_payload(*, title: str, message: dict) -> NotifyPayload:
    """构造固定喜报正文及按需加载的配图。"""

    return NotifyPayload(
        title=title,
        text="好羡慕~",
        markdown=f"好羡慕~\n\n![喜报]({image_reference(SIX_STAR_IMAGE_ID)})",
        html=_notification_template.deferred_notification_template(
            "MAA_six_star.html", message
        ),
        signature_sep=SIGNATURE_SEP,
        images=DeferredContent(
            lambda: (
                NotificationImage(
                    id=SIX_STAR_IMAGE_ID,
                    data=_six_star_image(),
                    url=SIX_STAR_IMAGE_URL,
                    alt="喜报",
                ),
            )
        ),
        presentation="announcement",
    )
