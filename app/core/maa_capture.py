"""MAS 自持的轻量 MaaFramework 截图，不加载 Resource / Tasker。"""

import asyncio
from pathlib import Path
from threading import Event, Lock
from typing import TYPE_CHECKING

from app.utils import get_logger

if TYPE_CHECKING:
    from PIL import Image

logger = get_logger("MaaFramework 截图")

# 原生 Job.wait 无法取消；跨用户/任务只允许一份在途工作，直到原生句柄销毁。
_CAPTURE_BUSY = Lock()


async def capture_adb(adb_path: Path | str, address: str) -> "Image.Image | None":
    """按运行时目标补截 RGB 画面；超时/取消放弃结果，不提前销毁 Controller。"""

    if not adb_path or address in ("", "Unknown"):
        return None

    # 冷导入留在事件循环，阻塞的 SDK 调用才进入执行器。
    from maa.controller import AdbController
    from maa.define import MaaAdbInputMethodEnum, MaaAdbScreencapMethodEnum
    from PIL import Image

    if not _CAPTURE_BUSY.acquire(blocking=False):
        logger.warning("上一张截图仍未结束，跳过补截")
        return None
    abandoned = Event()

    def capture() -> Image.Image | None:
        controller = None
        try:
            if abandoned.is_set():
                return None
            controller = AdbController(
                adb_path=adb_path,
                address=address,
                screencap_methods=MaaAdbScreencapMethodEnum.Encode,
                input_methods=MaaAdbInputMethodEnum.AdbShell,
            )
            if not controller.post_connection().wait().succeeded:
                raise RuntimeError("连接设备失败")
            if abandoned.is_set():
                return None
            if not controller.post_screencap().wait().succeeded:
                raise RuntimeError("获取设备画面失败")
            if abandoned.is_set():
                return None
            # SDK 返回 BGR；复制为 PIL RGB，画面不再依赖原生 Controller。
            return Image.fromarray(controller.cached_image[:, :, ::-1]).copy()
        except Exception as exc:
            logger.warning(f"设备截图失败: {exc}")
            return None
        finally:
            # SDK 没有 close()，由 __del__ 销毁；必须在所有原生等待结束之后。
            del controller
            _CAPTURE_BUSY.release()

    try:
        pending = asyncio.get_running_loop().run_in_executor(None, capture)
    except BaseException:
        _CAPTURE_BUSY.release()
        raise
    try:
        return await asyncio.wait_for(asyncio.shield(pending), timeout=60)
    finally:
        # wait_for 只停止等待。线程继续持有 Controller 和锁，迟到画面不再使用。
        abandoned.set()
