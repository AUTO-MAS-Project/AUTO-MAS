"""MAA 通知：插件宿主没有完整 notify 编排时走系统通知兜底。"""

from __future__ import annotations

import io
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from auto_mas_core import Config
from auto_mas_core.services import Notify
from auto_mas_core.utils import get_logger, get_setting, resource_path

from ..shared.notify_types import NotificationImage, image_reference
from ..schema import MaaUser

logger = get_logger("MAA 通知工具")

SIGNATURE_SEP = "\n"
SIX_STAR_IMAGE_ID = "maa-six-star"
NOTIFY_SCREENSHOT_JPEG_QUALITY = 85
NOTIFY_SCREENSHOT_LIMIT = 4


@dataclass
class DispatchResult:
    attempted: int = 0
    succeeded: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()


@cache
def _six_star_image() -> bytes | None:
    try:
        return resource_path("images", "notification", "six_star.png").read_bytes()
    except OSError as exc:
        logger.warning(f"读取喜报配图失败: {exc}")
        return None


def screenshot_entries(pairs: Sequence[tuple[str, NotificationImage]]) -> list[dict]:
    return [{"label": label, "id": image.id} for label, image in pairs]


def load_screenshot_images(
    shots: Sequence[tuple[str, Path | bytes]],
    *,
    image_id_prefix: str,
) -> list[tuple[str, NotificationImage]]:
    images: list[tuple[str, NotificationImage]] = []
    for index, (label, source) in enumerate(shots, start=1):
        if isinstance(source, bytes):
            data = source
        else:
            try:
                data = source.read_bytes()
            except OSError as exc:
                logger.warning(f"读取失败截图失败: {source}: {exc}")
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
        except Exception as exc:
            images.append(
                (
                    label,
                    NotificationImage(id=image_id, data=data, alt=label),
                )
            )
            logger.warning(f"失败截图转 JPEG 失败，改用原图: {exc}")
    return images


async def push_proxy_result(*, title: str, message: dict, **kwargs) -> DispatchResult:
    text = (
        f"{title}\n"
        f"开始: {message.get('start_time')} 结束: {message.get('end_time')}\n"
        f"完成 {message.get('completed_count')} / 未完成 {message.get('uncompleted_count')}\n"
        f"{message.get('result', '')}"
    )
    logger.info(text)
    try:
        await Notify.push_plyer(title, text[:200], title, 10)
    except Exception as e:
        logger.warning(f"系统通知失败: {e}")
    return DispatchResult(attempted=1, succeeded=("plyer",))


async def push_notification(
    mode: str,
    title: str,
    message: dict,
    user_config: MaaUser | None,
    task_info: object | None = None,
    *,
    images: Sequence[NotificationImage] = (),
) -> DispatchResult:
    logger.info(f"开始推送通知, 模式: {mode}, 标题: {title}")
    if mode == "代理结果":
        return await push_proxy_result(title=title, message=message, task_info=task_info)
    text = title
    if isinstance(message, dict):
        text = f"{title}\n" + "\n".join(f"{k}: {v}" for k, v in message.items() if k != "screenshots")
    enabled_user = True
    if isinstance(user_config, MaaUser):
        enabled_user = user_config.notify.enabled
    if mode == "公招六星" and not get_setting("Notify", "IfSendSixStar", False) and not enabled_user:
        return DispatchResult()
    try:
        await Notify.push_plyer(title, text[:200], title, 8)
    except Exception as e:
        logger.warning(f"系统通知失败: {e}")
    _ = images, task_info, Config
    return DispatchResult(attempted=1, succeeded=("plyer",))
