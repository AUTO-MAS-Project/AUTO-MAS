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

"""各专项通知工具共用的核心原语：强类型报告投递与失败截图资源转换。

「代理结果」接收 ``TaskResultReport``；「统计信息」接收已生成的 ``NotifyPayload``。
模式识别、专项结果字典与模板扩展留在专项边界，共享层只消费明确的报告契约。

失败截图到通知图片资源的转换原语（``load_screenshot_images`` /
``screenshot_entries``）与通知截图上限也在这里，供各专项共用。
"""

import io
from collections.abc import Sequence
from html import escape
from pathlib import Path
from typing import Any

from app.core.notify import (
    DispatchResult,
    dispatch,
    global_target,
    statistic_targets,
)
from app.core.task_report import prepare_task_report
from app.models.notification import (
    NotificationImage,
    NotificationSummary,
    NotifyPayload,
    image_reference,
)
from app.models.notification_channel import UserNotificationConfig
from app.models.notification_report import ReportScreenshot, TaskResultReport
from app.utils import get_logger
from app.utils.notification_template import get_notification_template

logger = get_logger("任务通知核心")


async def push_statistics_report(
    *, payload: NotifyPayload, user_config: UserNotificationConfig | None
) -> DispatchResult:
    """投递专项已生成的统计内容，不接收模式或专项字典。"""

    return await dispatch(payload, statistic_targets(user_config))


async def push_proxy_result(
    *,
    title: str,
    report: TaskResultReport,
    task_info: object | None = None,
    result_template: str = "general_result.html",
    signature_sep: str = "\n\n",
    logger: Any | None = None,
    skip_debug_message: str | None = None,
    images: Sequence[NotificationImage] = (),
    include_system: bool = True,
) -> DispatchResult:
    """推送全局「代理结果」报告；签到合并和补发由报告协调器承担。

    Args:
        title: 通知标题。
        report: 已在专项边界固定公共字段的任务报告。
        task_info: 任务信息，用于签到汇总的渠道级重试。
        result_template: 结果 HTML 模板名，MAA 用 MAA_result.html。
        signature_sep: 签名分隔符，默认与 NotifyPayload 缺省一致；MAA 只空一行。
        logger: 调用方模块 logger，仅用于可选的跳过 debug 日志。
        skip_debug_message: SendTaskResultTime 不满足时的 debug 文案，仅 M9A 传入。
        images: 随报告提供的图片资源。HTML 模板通过稳定资源 ID 引用需要展示的图片。
        include_system: 是否弹系统通知。本轮已由专门的通知弹过（如 MaaFW 的停服维护 /
            需要更新）时传 False，免得同一件事弹两次。
    """

    prepared = prepare_task_report(task_info)
    if not prepared.should_send(
        uncompleted_count=report.uncompleted_count,
        embedded_summary=report.embedded_summary,
    ):
        if logger is not None and skip_debug_message:
            logger.debug(skip_debug_message)
        return DispatchResult()

    message_text = (
        f"任务开始时间: {report.start_time}, 结束时间: {report.end_time}\n"
        f"已完成数: {report.completed_count}, 未完成数: {report.uncompleted_count}\n\n"
        f"{report.result}"
    )
    template = get_notification_template(result_template)
    counts = (
        f"已完成用户数: {report.completed_count}, "
        f"未完成用户数: {report.uncompleted_count}"
    )
    summary_text = (
        prepared.community_summary().text
        if task_info is not None and report.embedded_summary
        else ""
    )
    # 有未完成的用户时摘要标题不能再说「已完成！」；调用方显式给的摘要标题优先
    summary_title = report.summary_title or title.replace(
        "报告", "存在异常" if report.uncompleted_count > 0 else "已完成！"
    )
    return await prepared.dispatch(
        NotifyPayload(
            title=title,
            text=message_text,
            html=template.render(report.template_context()),
            signature_sep=signature_sep,
            summary=NotificationSummary(
                text=counts,
                title=summary_title,
                overflow_text=message_text,
            ),
            images=tuple(images),
        ),
        [global_target(include_system=include_system, system_timeout_seconds=10)],
        summary_text=summary_text,
    )


async def push_maintenance_notice(*, message: str, task_info: object) -> DispatchResult:
    """维护跳过只推送游戏状态，沿用原有通知时机与渠道。"""
    report = prepare_task_report(task_info)
    if not report.should_send(uncompleted_count=0):
        return DispatchResult()
    return await report.dispatch(
        NotifyPayload(
            title=message,
            text=message,
            html=f"<p>{escape(message)}</p>",
            summary=NotificationSummary(text=message, title=message),
        ),
        [global_target(include_system=True, system_timeout_seconds=10)],
    )


# 与各专项约定的失败截图 JPEG 质量：任务界面文字在该质量下仍清晰可读。
NOTIFY_SCREENSHOT_JPEG_QUALITY = 85

# 一份通知最多带几张失败截图，多了取最后几张（最终停在哪更要紧）。
# 邮件里每张 JPEG 约 100~300 KB；MaaFW 的 PNG 原图留在 history 目录里不动。
NOTIFY_SCREENSHOT_LIMIT = 4


def load_screenshot_images(
    shots: Sequence[tuple[str, Path | bytes]],
    *,
    image_id_prefix: str,
) -> list[tuple[str, NotificationImage]]:
    """把失败截图读入通用图片资源，并尽量转成体积更小的 JPEG。

    源文件多为 PNG（MaaFW worker 那边没有编码器），一张 1280 宽的游戏画面
    动辄 1 MB，几张下来邮件就太胖；这里用 Pillow 转成 JPEG，体积能压到
    十分之一。转不动（Pillow 异常）就原样带 PNG；文件读不到就跳过这张，
    通知照发。

    Args:
        shots: (标签, 图片路径或已编码的图片字节) 序列，标签会显示在图片上方。
        image_id_prefix: 图片资源 ID 前缀，按专项区分（如 ``maafw`` / ``maa``）。

    Returns:
        (标签, 图片资源) 序列；读不到的文件被跳过。
    """

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
            from PIL import Image

            with Image.open(io.BytesIO(data)) as image:
                buffer = io.BytesIO()
                image.convert("RGB").save(
                    buffer, format="JPEG", quality=NOTIFY_SCREENSHOT_JPEG_QUALITY
                )
            images.append(
                (
                    label,
                    NotificationImage(
                        id=image_id,
                        data=buffer.getvalue(),
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
