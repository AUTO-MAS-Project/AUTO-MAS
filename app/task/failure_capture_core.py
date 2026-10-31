"""失败补截的尝试去重、停止和超时控制；取图目标由专项提供。"""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

from app.tools import error_screenshot as _tool_error_screenshot
from app.utils import get_logger

if TYPE_CHECKING:
    from PIL import Image

logger = get_logger("失败补截")


class FailureCapture:
    """持有一次补截等待，手动停止后不消费迟到结果。"""

    def __init__(self, *, stopped: Callable[[], bool]) -> None:
        self._stopped = stopped
        self._attempted = False
        self._task: asyncio.Task[Path | None] | None = None

    def reset(self) -> None:
        """开始新的业务尝试，允许重新补截。"""
        self._attempted = False

    def cancel(self) -> None:
        if self._task is not None:
            self._task.cancel()

    def save(self, image: "Image.Image | None", *, dir_name: str) -> Path | None:
        """在保存前复核停止状态，取消后返回的画面不再落盘。"""
        if image is None or self._stopped():
            return None
        low, high = image.convert("L").getextrema()
        if high - low < 8:
            logger.warning("失败补截为纯色画面，放弃保存")
            return None
        return _tool_error_screenshot.save_error_screenshot(
            image=image, dir_name=dir_name, file_prefix="failure"
        )

    async def run(
        self,
        capture: Callable[[], Awaitable[Path | None]],
        *,
        once: bool = False,
    ) -> Path | None:
        """诊断异常只记日志；外部取消仍交回任务生命周期处理。"""
        if self._stopped() or (once and self._attempted):
            return None
        self._attempted = True
        self._task = asyncio.create_task(capture())
        try:
            result = await asyncio.wait_for(self._task, timeout=60)
            return None if self._stopped() else result
        except asyncio.CancelledError:
            if not self._stopped():
                self._attempted = False
                raise
            return None
        except TimeoutError:
            logger.warning("失败补截超过 60 秒，放弃等待")
            return None
        except Exception as error:
            logger.warning(f"获取失败画面失败: {error}")
            return None
        finally:
            self._task = None
