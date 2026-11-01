#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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

"""专项共用的简单统计正文、维护提醒与失败截图资源转换。

投递统一交注入的宿主服务；复杂统计与专项模板扩展由各自的正文适配提供。

失败截图的异步准备、模板资源引用与通知截图上限也在这里，供各专项共用。
"""

import asyncio
from collections.abc import Callable, Sequence
from functools import partial
from html import escape
from pathlib import Path

from app.core import Notify
from app.core.notify import templates as _notification_template
from app.models.notification import (
    NotificationImage,
    NotificationSummary,
    NotifyPayload,
    image_reference,
)
from app.models.notification.channel import DispatchResult
from app.models.notification.report import ReportScreenshot
from app.models.task import TaskItem
from app.utils import get_logger

logger = get_logger("任务通知核心")


def user_statistics_text(message: dict) -> str:
    """构造用户统计的四字段正文，也供复杂报告作为紧凑摘要。"""

    return (
        f"用户: {message['user_info']}\n"
        f"开始时间: {message['start_time']}\n"
        f"结束时间: {message['end_time']}\n"
        f"执行结果: {message['user_result']}"
    )


def build_user_statistics_payload(*, title: str, message: dict) -> NotifyPayload:
    """构造含用户信息的简单统计通知。"""

    message_html = _notification_template.deferred_notification_template(
        "general_statistics.html", message
    )
    return NotifyPayload(
        title=title,
        text=user_statistics_text(message),
        html=message_html,
    )


def build_script_statistics_payload(
    *, title: str, message: dict, result_label: str
) -> NotifyPayload:
    """构造使用专项结果标签的简单统计通知，沿用末尾两次换行。"""

    message_html = _notification_template.deferred_notification_template(
        "general_statistics.html", message
    )
    return NotifyPayload(
        title=title,
        text=(
            f"开始时间: {message['start_time']}\n"
            f"结束时间: {message['end_time']}\n"
            f"{result_label}: {message['user_result']}\n\n"
        ),
        html=message_html,
    )


async def push_maintenance_notice(
    *, message: str, task_info: TaskItem
) -> DispatchResult:
    """维护跳过只推送游戏状态，沿用原有通知时机与渠道。"""
    report = Notify.prepare_task_report(task_info)
    if not report.should_send(uncompleted_count=0):
        return DispatchResult()
    return await report.dispatch(
        NotifyPayload(
            title=message,
            text=message,
            html=f"<p>{escape(message)}</p>",
            summary=NotificationSummary(text=message, title=message),
        ),
        [Notify.global_target(include_system=True, system_timeout_seconds=10)],
    )


# 与各专项约定的失败截图 JPEG 质量：任务界面文字在该质量下仍清晰可读。
NOTIFY_SCREENSHOT_JPEG_QUALITY = 85

# 一份通知最多带几张失败截图，多了取最后几张（最终停在哪更要紧）。
# 邮件里每张 JPEG 约 100~300 KB；MaaFW 的 PNG 原图留在 history 目录里不动。
NOTIFY_SCREENSHOT_LIMIT = 4


def _screenshot_converter() -> Callable[[bytes], bytes] | None:
    try:
        from app.core.notify import image as _notification_image

        return partial(
            _notification_image.encode_screenshot,
            quality=NOTIFY_SCREENSHOT_JPEG_QUALITY,
        )
    except Exception as exc:
        logger.warning(f"失败截图转码不可用，改用原图: {type(exc).__name__}")
        return None


async def prepare_screenshot_images(
    shots: Sequence[tuple[str, Path | bytes]], *, image_id_prefix: str
) -> list[tuple[str, NotificationImage]]:
    """先解析图片依赖，再在线程里读取和转码；冻结字节后才能释放业务资源。

    尽量转为 JPEG；转码失败保留原图，文件无法读取时跳过该张，通知照发。
    """

    convert = _screenshot_converter()
    return await asyncio.to_thread(
        _load_screenshot_images,
        shots,
        image_id_prefix=image_id_prefix,
        convert=convert,
    )


def _load_screenshot_images(
    shots: Sequence[tuple[str, Path | bytes]],
    *,
    image_id_prefix: str,
    convert: Callable[[bytes], bytes] | None,
) -> list[tuple[str, NotificationImage]]:
    images: list[tuple[str, NotificationImage]] = []
    for index, (label, source) in enumerate(shots, start=1):
        if isinstance(source, bytes):
            data = source
        else:
            try:
                data = source.read_bytes()
            except OSError as exc:
                logger.warning(f"读取失败截图失败，通知里不带这张: {source}: {exc}")
                continue
        image_id = f"{image_id_prefix}-failure-{index}"
        try:
            if convert is None:
                raise RuntimeError("截图转码不可用")
            data_jpeg = convert(data)
            images.append(
                (
                    label,
                    NotificationImage(
                        id=image_id,
                        data=data_jpeg,
                        alt=label,
                        mime_type="image/jpeg",
                    ),
                )
            )
        except Exception as exc:  # noqa: BLE001
            source_desc = (
                source if isinstance(source, Path) else f"<{len(source)} 字节图片>"
            )
            logger.warning(f"失败截图转 JPEG 失败，改用原图: {source_desc}: {exc}")
            images.append(
                (
                    label,
                    NotificationImage(
                        id=image_id,
                        data=data,
                        alt=label,
                        mime_type="image/png",
                    ),
                )
            )
    return images


def screenshot_entries(
    images: Sequence[tuple[str, NotificationImage]],
) -> list[ReportScreenshot]:
    """构造失败截图模板使用的资源引用和说明文字。"""

    return [
        {"image_ref": image_reference(image.id), "label": label}
        for label, image in images
    ]
