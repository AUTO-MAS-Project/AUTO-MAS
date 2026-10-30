"""MAS 自持的轻量 MaaFramework 截图，不加载 Resource / Tasker。"""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from threading import Event, Lock
from typing import TYPE_CHECKING

from app.utils import get_logger

if TYPE_CHECKING:
    from maa.controller import Controller
    from PIL import Image

logger = get_logger("MaaFramework 截图")

type AdbCapture = Callable[[Path | str, str], Awaitable["Image.Image | None"]]
type Win32Capture = Callable[[int], Awaitable["Image.Image | None"]]

# 原生 Job.wait 无法取消；跨用户/任务只允许一份在途工作，直到原生句柄销毁。
_CAPTURE_BUSY = Lock()


async def capture_adb(adb_path: Path | str, address: str) -> "Image.Image | None":
    """按运行时目标补截 RGB 画面；超时/取消放弃结果，不提前销毁 Controller。"""

    if not adb_path or address in ("", "Unknown"):
        return None

    # 冷导入留在事件循环，阻塞的 SDK 调用才进入执行器。
    from maa.controller import AdbController
    from maa.define import MaaAdbInputMethodEnum, MaaAdbScreencapMethodEnum

    return await _capture_controller(
        lambda: AdbController(
            adb_path=adb_path,
            address=address,
            screencap_methods=MaaAdbScreencapMethodEnum.Encode,
            input_methods=MaaAdbInputMethodEnum.AdbShell,
            # SDK 重连默认 kill-server；补截不得重启其他任务共用的 ADB 服务。
            # version 只读客户端版本，不连接服务；空命令会使 SDK 配置解析失败。
            config={"command": {"KillServer": ["{ADB}", "version"]}},
        )
    )


async def capture_win32(hwnd: int) -> "Image.Image | None":
    """以 FramePool 截取专项已确认归属的窗口，不回退到桌面截图。

    SDK 会将最小化窗口临时透明还原（不激活），销毁 Controller 时恢复状态。
    FramePool 不可用时放弃截图；调用方应传入仍属于本次任务的有效 HWND。
    """

    if not hwnd:
        return None
    from maa.controller import Win32Controller
    from maa.define import MaaWin32InputMethodEnum, MaaWin32ScreencapMethodEnum

    return await _capture_controller(
        lambda: Win32Controller(
            hWnd=hwnd,
            screencap_method=MaaWin32ScreencapMethodEnum.FramePool,
            mouse_method=MaaWin32InputMethodEnum.SendMessage,
            keyboard_method=MaaWin32InputMethodEnum.SendMessage,
        )
    )


async def _capture_controller(
    create_controller: Callable[[], "Controller"],
) -> "Image.Image | None":
    """两种目标共用原生等待与所有权；工厂只能使用调用方已导入的 SDK。"""

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
            controller = create_controller()
            # SDK 默认缩放到短边 720；诊断截图保留设备或窗口的原始尺寸。
            if not controller.set_screenshot_use_raw_size(enable=True):
                raise RuntimeError("设置原尺寸截图失败")
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
