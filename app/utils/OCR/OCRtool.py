# ocr_tool.py
import ctypes
import cv2
import pyautogui
from PIL import Image
import win32con
import win32gui
from rapidocr_onnxruntime import RapidOCR
from mss import mss

from app.utils import get_logger
from app.utils.exception import WindowsNotFoundException, WindowsNotFocusException

# OCR入门指南！
# ┌────────────────────────────┐
# │(0,0)                       │
# │                            │
# │       [识别文字]             │
# │       ↑top=120             │
# │       ←left=80             │
# │       width=200            │
# │       height=40            │
# └────────────────────────────┘
# 字段	    类型	    含义
# left	    int	    识别到的文字区域的左上角 X 坐标（相对于输入图像的像素坐标）
# top	    int	    识别到的文字区域的左上角 Y 坐标
# width 	int	    文字区域的 宽度（像素）
# height	int	    文字区域的 高度（像素）
# 此OCR推荐在1080P（16：9）分辨率下使用，尽管可以使用其他宽高比，但是图像默认以此标准处理，可能出现问题。

# 你现在已经学会了OCR识别的基础知识了！快来试试吧！

logger = get_logger("OCR模块")
class OCRTool:
    #  默认宽高比 16:9，用于图像预处理
    aspect_ratio_width = 16
    aspect_ratio_height = 9
    zoom = 1.5  # DPI 缩放比例

    # 截图区域相关属性（初始化为 None 或默认值）
    area_width = 1920
    area_height = 1080
    area_top = 0
    area_left = 0
    screenshot_proportion = 1.0
    location_proportion = 1.0

    def __init__(self, width=16, height=9):
        """初始化 OCR 引擎"""
        self.ocr_engine = RapidOCR()
        self.aspect_ratio_width = width
        self.aspect_ratio_height = height
        self.zoom = self.get_system_dpi_scaling() or 1.5


    def get_system_dpi_scaling(self) -> float:
        """
        获取主显示器的 DPI 缩放比例。
        兼容 Python 3.13 + 最新 pywin32，使用 ctypes 直接调用 Windows API。
        """
        try:
            # 启用高 DPI 感知，避免始终返回 96
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)  # type: ignore[attr-defined]
            except (AttributeError, OSError):
                # Windows 8.1 以下系统没有该函数
                pass

            # 获取主显示器 DC
            hdc = win32gui.GetDC(0)
            try:
                # 使用 ctypes 直接调用 GetDeviceCaps
                # LOGPIXELSX = 88
                dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
            finally:
                win32gui.ReleaseDC(0, hdc)

            scaling = dpi / 96.0
            logger.debug(f"检测到系统 DPI: {dpi}, 缩放比例: {scaling:.2f}")
            return scaling

        except Exception as e:
            logger.warning(f"获取系统 DPI 失败: {e}，使用默认缩放比例 1.5")
            return 1.5


    # ========== 截图部分 ==========
    @classmethod
    def get_screenshot_region(cls, title: str, should_preprocess: bool = True) -> tuple[int, int, int, int]:
        """
        根据给定的窗口标题获取截图区域。

        该方法会查找包含指定标题的窗口，若未找到则抛出 WindowsNotFoundException 异常。
        找到唯一窗口后，会激活该窗口，并计算其截图区域。

        根据是否预处理的设置，计算方式有所区别：
        - should_preprocess=True 时，会对截图区域进行预处理，适当缩小区域以排除窗口边框和标题栏。
        - should_preprocess=False 时，使用完整窗口区域进行截图。

        Args:
            title (str): 用于查找窗口的标题。
            should_preprocess (bool): 是否预处理图片区域，True 时排除边框和标题栏，False 时使用完整窗口。

        Returns:
            tuple[int, int, int, int]: 计算后的截图区域，格式为 (left, top, width, height)。

        Raises:
            WindowsNotFoundException: 未找到包含指定标题的窗口或无法激活窗口。
        """
        import time

        # 查找窗口句柄
        hwnd = cls._find_window_with_win32gui(title)
        if hwnd is None:
            raise WindowsNotFoundException(f"未能找到标题包含 [{title}] 的窗口")

        # 激活窗口并获取区域
        try:
            # 检查窗口状态，只有在最小化时才恢复
            placement = win32gui.GetWindowPlacement(hwnd)
            if placement[1] == win32con.SW_SHOWMINIMIZED:
                # 窗口是最小化状态，需要恢复
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.05)

            # 强制激活窗口
            cls._force_activate_window(hwnd)
            time.sleep(0.15)

            # 验证激活状态（最多重试一次）
            cls._verify_window_activated(hwnd, title)

            # 获取窗口区域
            rect = win32gui.GetWindowRect(hwnd)
            left, top, right, bottom = rect
            region = (left, top, right - left, bottom - top)

            window_title = win32gui.GetWindowText(hwnd)
            logger.info(f"成功激活窗口到前台: {window_title} (句柄: {hwnd})")

        except WindowsNotFocusException:
            raise
        except Exception as e:
            logger.error(f"激活窗口失败: {e}")
            raise WindowsNotFocusException(f"无法激活窗口 [{title}] 到前台: {e}")

        # 根据是否预处理来处理区域
        if should_preprocess:
            # 计算截图区域的实际坐标和尺寸
            left, top, width, height = region

            # 计算边框偏移量
            top_offset = int(30 * cls.zoom) if top != 0 else 0
            left_offset = int(8 * cls.zoom) if left != 0 else 0

            # 扣除边框后的实际可用宽高
            available_width = width - left_offset * 2  # 左右两侧都要扣除
            available_height = height - top_offset - int(8 * cls.zoom)  # 顶部标题栏 + 底部边框

            # 计算截图区域的宽度，将宽度调整为 相应 的倍数
            cls.area_width = available_width // cls.aspect_ratio_width * cls.aspect_ratio_width
            # 计算截图区域的高度，将高度调整为 相应 的倍数
            cls.area_height = available_height // cls.aspect_ratio_height * cls.aspect_ratio_height
            # 根据缩放比例调整顶部坐标，如果顶部坐标不为 0 则加上偏移量
            cls.area_top = top + top_offset
            # 根据缩放比例调整左侧坐标，如果左侧坐标不为 0 则加上偏移量
            cls.area_left = left + left_offset
            region = (cls.area_left, cls.area_top, cls.area_width, cls.area_height)

        return region

    @classmethod
    def _verify_window_activated(cls, hwnd: int, title: str) -> None:
        """
        验证窗口是否成功激活到前台，如果失败则重试一次。

        Args:
            hwnd (int): 窗口句柄
            title (str): 窗口标题（用于错误提示）

        Raises:
            WindowsNotFocusException: 窗口激活失败
        """
        import time

        foreground_hwnd = win32gui.GetForegroundWindow()
        if foreground_hwnd == hwnd:
            return

        # 重试一次
        logger.warning(f"窗口未激活，再次尝试强制激活...")
        cls._force_activate_window(hwnd)
        time.sleep(0.2)

        foreground_hwnd = win32gui.GetForegroundWindow()
        if foreground_hwnd != hwnd:
            window_title = win32gui.GetWindowText(hwnd)
            foreground_title = win32gui.GetWindowText(foreground_hwnd)
            raise WindowsNotFocusException(
                f"无法将窗口 [{title}] 激活到前台。\n"
                f"目标窗口: {window_title} (句柄: {hwnd})\n"
                f"前台窗口: {foreground_title} (句柄: {foreground_hwnd})\n"
                f"可能原因：1) 窗口被其他程序阻止 2) 需要管理员权限 3) 系统安全策略限制"
            )

    @staticmethod
    def _force_activate_window(hwnd: int) -> None:
        """
        强制激活窗口到前台（使用线程输入附着技术）

        Args:
            hwnd: 窗口句柄
        """
        try:
            import win32process

            # 获取当前前台窗口
            foreground_hwnd = win32gui.GetForegroundWindow()

            # 如果已经是前台窗口，直接返回
            if foreground_hwnd == hwnd:
                logger.debug("目标��口已在前台")
                return

            # 获取前台窗口的线程ID和进程ID
            if foreground_hwnd:
                foreground_thread_id, _ = win32process.GetWindowThreadProcessId(foreground_hwnd)
            else:
                foreground_thread_id = 0

            # 获取目标窗口的线程ID和进程ID
            target_thread_id, _ = win32process.GetWindowThreadProcessId(hwnd)

            # 如果线程ID不同，需要附着输入线程
            attached = False
            if foreground_thread_id != target_thread_id and foreground_thread_id != 0:
                try:
                    # 附着到前台窗口的输入线程
                    win32process.AttachThreadInput(foreground_thread_id, target_thread_id, True)
                    attached = True
                    logger.debug(f"已附着输入线程: {foreground_thread_id} -> {target_thread_id}")
                except Exception as e:
                    logger.warning(f"附着输入线程失败: {e}")

            try:
                # 显示窗口
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

                # 将窗口置于前台
                win32gui.SetForegroundWindow(hwnd)

                # 设置焦点
                try:
                    win32gui.SetFocus(hwnd)
                except Exception as e:
                    logger.debug(f"SetFocus 失败（非致命）: {e}")

                # 激活窗口
                try:
                    win32gui.BringWindowToTop(hwnd)
                except Exception as e:
                    logger.debug(f"BringWindowToTop 失败（非致命）: {e}")

                logger.info(f"已执行窗口激活操作 (句柄: {hwnd})")

            finally:
                # 分离输入线程（必须在 finally 中执行，确保一定会分离）
                if attached:
                    try:
                        win32process.AttachThreadInput(foreground_thread_id, target_thread_id, False)
                        logger.debug("已分离输入线程")
                    except Exception as e:
                        logger.warning(f"分离输入线程失败: {e}")

        except Exception as e:
            logger.error(f"强制激活窗口出错: {e}")
            # 即使出错也不抛出异常，因为可能已经部分成功


    @staticmethod
    def _find_window_with_win32gui(title: str) -> int | None:
        """
        使用 win32gui 查找包含指定标题的窗口。

        Args:
            title (str): 窗口标题关键字（模糊匹配）

        Returns:
            int | None: 找到的窗口句柄，未找到返回 None
        """
        found_windows = []

        def enum_callback(hwnd, results):
            if win32gui.IsWindowVisible(hwnd):
                window_title = win32gui.GetWindowText(hwnd)
                if title.lower() in window_title.lower():
                    results.append((hwnd, window_title))

        try:
            win32gui.EnumWindows(enum_callback, found_windows)
        except Exception as e:
            logger.error(f"win32gui 枚举窗口失败: {e}")
            return None

        if found_windows:
            # 返回第一个匹配的窗口句柄
            hwnd, window_title = found_windows[0]
            logger.info(f"win32gui 找到匹配窗口: {window_title} (句柄: {hwnd})")
            return hwnd

        return None

    @classmethod
    def get_screenshot(cls, title: str, should_preprocess: bool = True, region: tuple[int, int, int, int] | None = None) -> Image.Image:
        """
        根据指定的窗口标题和区域获取截图，并对截图进行尺寸调整。

        使用 MSS 库进行截图，支持多显示器环境，能够正确处理位于副屏的窗口。

        Args:
            title (str): 用于查找窗口的标题。
            should_preprocess (bool): 是否预处理图片区域，True 时排除边框和标题栏，False 时使用完整窗口。
            region (tuple[int, int, int, int] | None): 截图区域，格式为 (left, top, width, height)。
                如果为 None，则通过 `get_screenshot_region` 方法根据标题自动计算截图区域。


        Returns:
            Image.Image: 调整尺寸后的 Pillow 图像对象。
        """
        if region is None:
            region = cls.get_screenshot_region(title, should_preprocess)

        # 使用 MSS 进行多显示器截图
        pillow_img = cls._capture_screenshot_mss(region)
        return cls._image_resize(pillow_img)

    @staticmethod
    def _capture_screenshot_mss(region: tuple[int, int, int, int]) -> Image.Image:
        """
        使用 MSS 库进行截图，支持多显示器环境。

        MSS 库能够正确处理负坐标和跨显示器的截图区域，
        相比 pyautogui 更适合多显示器场景。

        Args:
            region (tuple[int, int, int, int]): 截图区域 (left, top, width, height)。

        Returns:
            Image.Image: 截取的 Pillow 图像对象。
        """
        left, top, width, height = region

        # MSS 使用 (left, top, right, bottom) 格式的 monitor 字典
        monitor = {
            "left": left,
            "top": top,
            "width": width,
            "height": height
        }

        try:
            with mss() as sct:
                # 截取指定区域
                screenshot = sct.grab(monitor)
                # 转换为 Pillow 图像
                pillow_img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
                logger.debug(f"使用 MSS 成功截图: 区域={region}, 尺寸={pillow_img.size}")
                return pillow_img
        except Exception as e:
            logger.error(f"MSS 截图失败: {e}，尝试使用 pyautogui 作为备用方案")
            # 备用方案：使用 pyautogui（可能在副屏上失败，但至少有个降级方案）
            try:
                return pyautogui.screenshot(region=(left, top, width, height))
            except Exception as fallback_error:
                logger.error(f"pyautogui 备用截图也失败: {fallback_error}")
                raise


    @classmethod
    def _image_resize(cls, pillow_image: Image.Image) -> Image.Image:
        """
        调整 Pillow 图像的尺寸，若图像宽度已经为 全局变量的比例 则直接返回原图像，
        否则将图像调整为宽度为 1920 的图像，并保持宽高比。

        Args:
            pillow_image (Image.Image): 待调整尺寸的 Pillow 图像对象。

        Returns:
            Image.Image: 调整尺寸后的 Pillow 图像对象。
        """
        if pillow_image.width % cls.area_width==0 and pillow_image.height % cls.area_height==0:
            return pillow_image
        cls.screenshot_proportion = 1920 / pillow_image.width
        resized_image = pillow_image.resize(
            (int(pillow_image.width * cls.screenshot_proportion),
             int(pillow_image.height * cls.screenshot_proportion)),
            Image.Resampling.BICUBIC)
        return resized_image


    @classmethod
    def _location_calculator(cls, x, y):
        """
        根据截图缩放比例和截图区域偏移量，计算实际屏幕坐标。

        Args:
            x (int): 截图上的 x 坐标。
            y (int): 截图上的 y 坐标。

        Returns:
            tuple[int, int]: 实际屏幕上的坐标 (x, y)。
        """
        cls.location_proportion = 1 / cls.screenshot_proportion
        return x * cls.location_proportion + cls.area_left, y * cls.location_proportion + cls.area_top
