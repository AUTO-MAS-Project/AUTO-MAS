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


import mimetypes
from collections.abc import Sequence
from html import escape
from pathlib import Path

from app.core.notify import templates as _notification_template
from app.models.notification import NotificationImage, NotifyPayload
from app.utils import get_logger

logger = get_logger("MaaEnd 通知工具")
_ERROR_IMAGE_LIMIT = 3
_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp"})


def collect_recent_error_images(
    maaend_root_path: str | Path,
    *,
    started_at_ns: int,
    ended_at_ns: int,
    diagnostic_paths: Sequence[Path] = (),
) -> tuple[NotificationImage, ...]:
    """读取本轮 MaaEnd 错误截图与 MAS 实际保存的诊断图，原样附到通知。"""

    # MaaEnd 的日志根目录是 debug/，save_on_error 截图保存在其 on_error/ 子目录。
    error_dir = Path(maaend_root_path) / "debug" / "on_error"
    entries = list(diagnostic_paths)
    try:
        entries.extend(error_dir.iterdir())
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning(f"读取 MaaEnd 错误截图目录失败: {exc}")

    candidates: list[tuple[int, Path]] = []
    for image_path in entries:
        if image_path.suffix.lower() not in _IMAGE_SUFFIXES or image_path.is_symlink():
            continue
        try:
            if image_path.is_file():
                modified_at_ns = image_path.stat().st_mtime_ns
                if started_at_ns <= modified_at_ns <= ended_at_ns:
                    candidates.append((modified_at_ns, image_path))
        except OSError as exc:
            logger.warning(f"读取 MaaEnd 错误截图信息失败: {image_path.name} - {exc}")

    images: list[NotificationImage] = []
    for _, image_path in sorted(candidates, key=lambda item: item[0], reverse=True):
        if len(images) >= _ERROR_IMAGE_LIMIT:
            break
        try:
            image_data = image_path.read_bytes()
        except OSError as exc:
            logger.warning(f"读取 MaaEnd 错误截图失败: {image_path.name} - {exc}")
            continue
        if not image_data:
            continue

        mime_type = mimetypes.guess_type(image_path.name)[0]
        if not mime_type or not mime_type.startswith("image/"):
            continue
        images.append(
            NotificationImage(
                id=f"maaend-error-{len(images) + 1}",
                data=image_data,
                alt="MaaEnd 报错截图",
                mime_type=mime_type,
            )
        )

    if images:
        logger.info(f"已附带 {len(images)} 张 MaaEnd 报错图片")
    return tuple(images)


def _statistic_sections(message: dict) -> list[str]:
    """拼装抽数与基质统计段落; 无对应数据时返回空列表。"""

    matrix_lines = []
    # matrix_statistics 键存在但为空表示「查过了, 没有合适的」, 与键不存在语义不同
    if "matrix_statistics" in message and message["matrix_statistics"]:
        matrix_lines.append("基质统计:")
        for skill, weapon in message["matrix_statistics"].items():
            matrix_lines.append(f"  {skill}: {weapon}")
    elif "matrix_statistics" in message:
        matrix_lines.append("基质统计: 无合适的基质")

    pull_count_lines = []
    pull_count = message.get("pull_count_statistics")
    if pull_count:
        pull_count_lines.extend(
            [
                "抽数统计:",
                f"  当前池可用: {pull_count['current_pool_total']} 抽",
                f"  下版本池子总计: {pull_count['next_pool_total']} 抽",
                f"  资源折算: {pull_count['resource_pulls']} 抽",
                f"  可留到下版本的券: {pull_count['carry_over_pulls']} 抽",
            ]
        )

    return [
        section
        for section in ("\n".join(pull_count_lines), "\n".join(matrix_lines))
        if section
    ]


def build_statistics_payload(
    *, title: str, message: dict, images: Sequence[NotificationImage] = ()
) -> NotifyPayload:
    """构造专项统计正文，投递由注入的通知服务负责。"""

    message_text = (
        f"开始时间: {message['start_time']}\n"
        f"结束时间: {message['end_time']}\n"
        f"MaaEnd执行结果: {message['user_result']}"
    )
    sections = _statistic_sections(message)
    if sections:
        message_text += "\n\n" + "\n\n".join(sections)

    return NotifyPayload(
        title=title,
        text=message_text,
        html=_notification_template.deferred_notification_template(
            "MaaEnd_statistics.html", message
        ),
        images=tuple(images),
    )


def build_inventory_payload(*, title: str, message: dict) -> NotifyPayload:
    """展示本轮材料获得记录和上游状态，不附带全量库存。"""
    lines = message["inventory_report"] or [
        "本轮未收到养成材料获得记录；不代表实际获得数量为 0。"
    ]
    text = "\n".join(
        [
            f"账号：{message['user_info']}",
            f"开始时间：{message['start_time']}",
            f"结束时间：{message['end_time']}",
            *lines,
        ]
    )
    return NotifyPayload(title=title, text=text, html=f"<pre>{escape(text)}</pre>")
