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

"""各专项通知工具共用的核心原语：代理结果推送 + 失败截图资源转换。

SRC / HSR / MaaEnd / OkNte / general / Okww / MAA / M9A / MaaFW / BetterGI 的
代理结果分支原本逐字重复，仅模板名、签名分隔符与跳过日志存在授权差异，统一
收敛到本模块。各专项的统计信息分支差异较大，保留在各自 notify 模块内。

失败截图到通知图片资源的转换原语（``load_screenshot_images`` /
``screenshot_entries``）与通知截图上限也在这里，供各专项共用。
"""

import io
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.core import Config
from app.core.notify import (
    DispatchResult,
    dispatch_task_report,
    global_target,
    should_send_result,
)
from app.models.notification import (
    NotificationImage,
    NotificationSummary,
    NotifyPayload,
    image_reference,
)
from app.tools.community_notify import get_task_community_summary
from app.utils import get_logger

logger = get_logger("任务通知核心")


async def push_proxy_result(
    *,
    title: str,
    message: dict,
    task_info: object | None = None,
    result_template: str = "general_result.html",
    signature_sep: str = "\n\n",
    logger: Any | None = None,
    skip_debug_message: str | None = None,
    images: Sequence[NotificationImage] = (),
    include_system: bool = True,
) -> DispatchResult:
    """推送全局「代理结果」报告；签到汇总与渠道级重试由 dispatch_task_report 承担。

    Args:
        title: 通知标题。
        message: 需含 start_time / end_time / completed_count /
            uncompleted_count / result 字段。
        task_info: 任务信息，用于签到汇总的渠道级重试。
        result_template: 结果 HTML 模板名，MAA 用 MAA_result.html。
        signature_sep: 签名分隔符，默认与 NotifyPayload 缺省一致；MAA 只空一行。
        logger: 调用方模块 logger，仅用于可选的跳过 debug 日志。
        skip_debug_message: SendTaskResultTime 不满足时的 debug 文案，仅 M9A 传入。
        images: 随报告提供的图片资源。HTML 模板通过稳定资源 ID 引用需要展示的图片。
        include_system: 是否弹系统通知。本轮已由专门的通知弹过（如 MaaFW 的停服维护 /
            需要更新）时传 False，免得同一件事弹两次。
    """

    if not should_send_result(message, task_info=task_info):
        if logger is not None and skip_debug_message:
            logger.debug(skip_debug_message)
        return DispatchResult()

    message_text = (
        f"任务开始时间: {message['start_time']}, 结束时间: {message['end_time']}\n"
        f"已完成数: {message['completed_count']}, 未完成数: {message['uncompleted_count']}\n\n"
        f"{message['result']}"
    )
    template = Config.notify_env.get_template(result_template)
    counts = (
        f"已完成用户数: {message['completed_count']}, "
        f"未完成用户数: {message['uncompleted_count']}"
    )
    summary_text = (
        get_task_community_summary(task_info)
        if task_info is not None and message.get("game_sign_summary")
        else ""
    )
    # 有未完成的用户时摘要标题不能再说「已完成！」；调用方显式给的摘要标题优先
    summary_title = message.get("summary_title") or title.replace(
        "报告", "存在异常" if message["uncompleted_count"] > 0 else "已完成！"
    )
    return await dispatch_task_report(
        NotifyPayload(
            title=title,
            text=message_text,
            html=template.render(message),
            signature_sep=signature_sep,
            summary=NotificationSummary(
                text=counts,
                title=summary_title,
                overflow_text=message_text,
            ),
            images=tuple(images),
        ),
        [global_target(include_system=include_system, system_timeout_seconds=10)],
        task_info,
        summary_text=summary_text,
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
) -> list[dict[str, str]]:
    """构造失败截图模板使用的资源引用和说明文字。"""

    return [
        {"image_ref": image_reference(image.id), "label": label}
        for label, image in images
    ]
