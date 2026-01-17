#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from fastapi import APIRouter, Body
from pydantic import BaseModel, Field
from typing import Optional
import base64
from io import BytesIO

from app.utils.OCR.OCRtool import OCRTool
from app.utils import get_logger
from app.models.schema import OutBase

logger = get_logger("OCR API")

router = APIRouter(prefix="/api/ocr", tags=["OCR识别"])


# ========== 截图相关模型 ==========
class OCRScreenshotIn(BaseModel):
    window_title: str = Field(..., description="窗口标题（用于查找窗口）")
    should_preprocess: bool = Field(
        default=True,
        description="是否预处理图片区域，True时排除边框和标题栏，False时使用完整窗口",
    )
    aspect_ratio_width: int = Field(default=16, description="宽高比宽度")
    aspect_ratio_height: int = Field(default=9, description="宽高比高度")
    region: Optional[tuple[int, int, int, int]] = Field(
        default=None, description="自定义截图区域 (left, top, width, height)"
    )


class OCRScreenshotOut(OutBase):
    image_base64: str = Field(..., description="截图的Base64编码（PNG格式）")
    region: tuple[int, int, int, int] = Field(
        ..., description="实际使用的截图区域 (left, top, width, height)"
    )
    image_width: int = Field(..., description="截图宽度")
    image_height: int = Field(..., description="截图高度")


class ADBScreenshotIn(BaseModel):
    adb_path: str = Field(..., description="ADB 可执行文件的路径")
    serial: str = Field(
        ..., description="设备序列号，格式如 '127.0.0.1:5555' 或 'emulator-5554'"
    )
    use_screencap: bool = Field(
        default=True,
        description="是否使用 screencap PNG 方法，False 时使用 screencap raw 方法",
    )


class ADBScreenshotOut(OutBase):
    image_base64: str = Field(..., description="截图的Base64编码（PNG格式）")
    image_width: int = Field(..., description="截图宽度")
    image_height: int = Field(..., description="截图高度")
    serial: str = Field(..., description="设备序列号")


# ========== 测试相关模型 ==========
class CheckImageIn(BaseModel):
    window_title: str = Field(..., description="窗口标题（用于查找窗口）")
    image_path: str = Field(..., description="要查找的图片路径")
    interval: float = Field(default=0, description="截图间隔时间（秒）", ge=0)
    retry_times: int = Field(default=1, description="重复截图次数", ge=1)
    threshold: float = Field(
        default=0.8, description="图像匹配阈值，范围 0-1", ge=0, le=1
    )


class CheckImageAnyIn(BaseModel):
    window_title: str = Field(..., description="窗口标题（用于查找窗口）")
    image_paths: list[str] = Field(..., description="要查找的图片路径列表")
    interval: float = Field(default=0, description="截图间隔时间（秒）", ge=0)
    retry_times: int = Field(default=1, description="重复截图次数", ge=1)
    threshold: float = Field(
        default=0.8, description="图像匹配阈值，范围 0-1", ge=0, le=1
    )


class CheckImageAllIn(BaseModel):
    window_title: str = Field(..., description="窗口标题（用于查找窗口）")
    image_paths: list[str] = Field(..., description="要查找的图片路径列表")
    interval: float = Field(default=0, description="截图间隔时间（秒）", ge=0)
    retry_times: int = Field(default=1, description="重复截图次数", ge=1)
    threshold: float = Field(
        default=0.8, description="图像匹配阈值，范围 0-1", ge=0, le=1
    )


class CheckImageOut(OutBase):
    found: bool = Field(..., description="是否找到图像")
    attempts: int = Field(..., description="实际尝试次数")


class ClickImageIn(BaseModel):
    window_title: str = Field(..., description="窗口标题（用于查找窗口）")
    image_path: str = Field(..., description="要查找并点击的图片路径")
    interval: float = Field(default=0, description="截图间隔时间（秒）", ge=0)
    retry_times: int = Field(default=1, description="重复截图次数", ge=1)
    threshold: float = Field(
        default=0.8, description="图像匹配阈值，范围 0-1", ge=0, le=1
    )


class ClickTextIn(BaseModel):
    window_title: str = Field(..., description="窗口标题（用于查找窗口）")
    text: str = Field(..., description="要查找并点击的文字内容")
    interval: float = Field(default=0, description="截图间隔时间（秒）", ge=0)
    retry_times: int = Field(default=1, description="重复截图次数", ge=1)


class ClickOut(OutBase):
    success: bool = Field(..., description="是否成功点击")
    attempts: int = Field(..., description="实际尝试次数")


# ========== 截图接口 ==========
@router.post(
    "/screenshot",
    tags=["Get"],
    summary="获取窗口截图",
    response_model=OCRScreenshotOut,
    status_code=200,
)
async def get_screenshot(params: OCRScreenshotIn = Body(...)) -> OCRScreenshotOut:
    """
    根据窗口标题获取截图，返回Base64编码的图像数据

    Args:
        params: 截图参数
            - window_title: 窗口标题关键字
            - should_preprocess: 是否预处理图片区域（默认True）
            - aspect_ratio_width: 宽高比宽度（默认16）
            - aspect_ratio_height: 宽高比高度（默认9）
            - region: 自定义截图区域，格式为 (left, top, width, height)

    Returns:
        OCRScreenshotOut: 包含Base64编码的截图和区域信息
    """
    try:
        # 初始化OCRTool
        ocr_tool = OCRTool(
            width=params.aspect_ratio_width, height=params.aspect_ratio_height
        )

        # 获取截图区域（如果没有提供自定义区域）
        if params.region is None:
            region = OCRTool.get_screenshot_region(
                params.window_title, params.should_preprocess
            )
        else:
            region = params.region

        # 获取截图
        screenshot_image = OCRTool.get_screenshot_with_pc(
            title=params.window_title,
            should_preprocess=params.should_preprocess,
            region=region,
        )

        # 将PIL Image转换为Base64
        buffer = BytesIO()
        screenshot_image.save(buffer, format="PNG")
        image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        logger.info(f"成功截取窗口 [{params.window_title}] 的截图，区域: {region}")

        return OCRScreenshotOut(
            code=200,
            status="success",
            message="截图成功",
            image_base64=image_base64,
            region=region,
            image_width=screenshot_image.width,
            image_height=screenshot_image.height,
        )

    except Exception as e:
        logger.error(f"截图失败: {type(e).__name__}: {str(e)}")
        return OCRScreenshotOut(
            code=500,
            status="error",
            message=f"截图失败: {type(e).__name__}: {str(e)}",
            image_base64="",
            region=(0, 0, 0, 0),
            image_width=0,
            image_height=0,
        )


@router.post(
    "/screenshot/adb",
    tags=["Get"],
    summary="通过ADB获取设备截图",
    response_model=ADBScreenshotOut,
    status_code=200,
)
async def get_screenshot_adb(params: ADBScreenshotIn = Body(...)) -> ADBScreenshotOut:
    """
    通过 ADB 端口获取 Android 设备/模拟器截图，返回Base64编码的图像数据

    支持两种截图方法：
    1. screencap PNG 方法（推荐）：速度快，直接获取 PNG 图像
    2. screencap raw 方法：获取原始像素数据，适用于某些不支持 PNG 的设备

    Args:
        params: ADB 截图参数
            - adb_path: ADB 可执行文件的路径
            - serial: 设备序列号，格式如 "127.0.0.1:5555" 或 "emulator-5554"
            - use_screencap: 是否使用 screencap PNG 方法（默认True）

    Returns:
        ADBScreenshotOut: 包含Base64编码的截图和设备信息
    """
    try:
        # 使用 OCRTool 通过 ADB 获取截图
        screenshot_image = OCRTool.get_screenshot_with_adb(
            adb_path=params.adb_path,
            serial=params.serial,
            use_screencap=params.use_screencap,
        )

        # 将PIL Image转换为Base64
        buffer = BytesIO()
        screenshot_image.save(buffer, format="PNG")
        image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        logger.info(
            f"成功通过 ADB 截取设备 [{params.serial}] 的截图，尺寸: {screenshot_image.size}"
        )

        return ADBScreenshotOut(
            code=200,
            status="success",
            message="ADB 截图成功",
            image_base64=image_base64,
            image_width=screenshot_image.width,
            image_height=screenshot_image.height,
            serial=params.serial,
        )

    except FileNotFoundError as e:
        logger.error(f"ADB 文件未找到: {str(e)}")
        return ADBScreenshotOut(
            code=404,
            status="error",
            message=f"ADB 文件未找到: {str(e)}",
            image_base64="",
            image_width=0,
            image_height=0,
            serial=params.serial,
        )
    except RuntimeError as e:
        logger.error(f"ADB 截图运行时错误: {str(e)}")
        return ADBScreenshotOut(
            code=500,
            status="error",
            message=f"ADB 截图失败: {str(e)}",
            image_base64="",
            image_width=0,
            image_height=0,
            serial=params.serial,
        )
    except Exception as e:
        logger.error(f"ADB 截图失败: {type(e).__name__}: {str(e)}")
        return ADBScreenshotOut(
            code=500,
            status="error",
            message=f"ADB 截图失败: {type(e).__name__}: {str(e)}",
            image_base64="",
            image_width=0,
            image_height=0,
            serial=params.serial,
        )


# ========== 测试接口：检查图像 ==========
@router.post(
    "/check/image",
    tags=["Get"],
    summary="检查是否存在指定图像",
    response_model=CheckImageOut,
    status_code=200,
)
async def check_image(params: CheckImageIn = Body(...)) -> CheckImageOut:
    """
    截图并查找是否存在图片内的内容

    Args:
        params: 检查图像参数
            - window_title: 窗口标题关键字
            - image_path: 要查找的图片路径
            - interval: 截图间隔时间（秒），默认为 0
            - retry_times: 重复截图次数，默认为 1
            - threshold: 图像匹配阈值，范围 0-1，默认 0.8

    Returns:
        CheckImageOut: 包含查找结果和尝试次数
    """
    try:
        # 设置全局窗口标题
        OCRTool.set_title(params.window_title)

        # 调用 check 方法
        found = OCRTool.check(
            image_path=params.image_path,
            interval=params.interval,
            retry_times=params.retry_times,
            threshold=params.threshold,
        )

        logger.info(f"图像检查完成: {params.image_path}, 结果: {found}")

        return CheckImageOut(
            code=200,
            status="success",
            message=f"图像检查完成，{'找到' if found else '未找到'}图像",
            found=found,
            attempts=params.retry_times,
        )

    except Exception as e:
        logger.error(f"图像检查失败: {type(e).__name__}: {str(e)}")
        return CheckImageOut(
            code=500,
            status="error",
            message=f"图像检查失败: {type(e).__name__}: {str(e)}",
            found=False,
            attempts=0,
        )


@router.post(
    "/check/image/any",
    tags=["Get"],
    summary="检查是否存在任意一个指定图像",
    response_model=CheckImageOut,
    status_code=200,
)
async def check_image_any(params: CheckImageAnyIn = Body(...)) -> CheckImageOut:
    """
    截图并查找是否存在列表中任意一张图片的内容

    Args:
        params: 检查图像参数
            - window_title: 窗口标题关键字
            - image_paths: 要查找的图片路径列表
            - interval: 截图间隔时间（秒），默认为 0
            - retry_times: 重复截图次数，默认为 1
            - threshold: 图像匹配阈值，范围 0-1，默认 0.8

    Returns:
        CheckImageOut: 包含查找结果和尝试次数
    """
    try:
        # 设置全局窗口标题
        OCRTool.set_title(params.window_title)

        # 调用 check_any 方法
        found = OCRTool.check_any(
            image_paths=params.image_paths,
            interval=params.interval,
            retry_times=params.retry_times,
            threshold=params.threshold,
        )

        logger.info(f"多图像检查（ANY）完成: {params.image_paths}, 结果: {found}")

        return CheckImageOut(
            code=200,
            status="success",
            message=f"多图像检查完成，{'找到任意一个' if found else '未找到任何'}图像",
            found=found,
            attempts=params.retry_times,
        )

    except Exception as e:
        logger.error(f"多图像检查（ANY）失败: {type(e).__name__}: {str(e)}")
        return CheckImageOut(
            code=500,
            status="error",
            message=f"多图像检查失败: {type(e).__name__}: {str(e)}",
            found=False,
            attempts=0,
        )


@router.post(
    "/check/image/all",
    tags=["Get"],
    summary="检查是否存在所有指定图像",
    response_model=CheckImageOut,
    status_code=200,
)
async def check_image_all(params: CheckImageAllIn = Body(...)) -> CheckImageOut:
    """
    截图并查找是否存在列表中所有图片的内容

    Args:
        params: 检查图像参数
            - window_title: 窗口标题关键字
            - image_paths: 要查找的图片路径列表
            - interval: 截图间隔时间（秒），默认为 0
            - retry_times: 重复截图次数，默认为 1
            - threshold: 图像匹配阈值，范围 0-1，默认 0.8

    Returns:
        CheckImageOut: 包含查找结果和尝试次数
    """
    try:
        # 设置全局窗口标题
        OCRTool.set_title(params.window_title)

        # 调用 check_all 方法
        found = OCRTool.check_all(
            image_paths=params.image_paths,
            interval=params.interval,
            retry_times=params.retry_times,
            threshold=params.threshold,
        )

        logger.info(f"多图像检查（ALL）完成: {params.image_paths}, 结果: {found}")

        return CheckImageOut(
            code=200,
            status="success",
            message=f"多图像检查完成，{'找到所有' if found else '未找到所有'}图像",
            found=found,
            attempts=params.retry_times,
        )

    except Exception as e:
        logger.error(f"多图像检查（ALL）失败: {type(e).__name__}: {str(e)}")
        return CheckImageOut(
            code=500,
            status="error",
            message=f"多图像检查失败: {type(e).__name__}: {str(e)}",
            found=False,
            attempts=0,
        )


# ========== 测试接口：点击操作 ==========
@router.post(
    "/click/image",
    tags=["Action"],
    summary="点击指定图像位置",
    response_model=ClickOut,
    status_code=200,
)
async def click_image(params: ClickImageIn = Body(...)) -> ClickOut:
    """
    截图、查找并点击与图像一致的位置

    Args:
        params: 点击图像参数
            - window_title: 窗口标题关键字
            - image_path: 要查找并点击的图片路径
            - interval: 截图间隔时间（秒），默认为 0
            - retry_times: 重复截图次数，默认为 1
            - threshold: 图像匹配阈值，范围 0-1，默认 0.8

    Returns:
        ClickOut: 包含点击结果和尝试次数
    """
    try:
        # 设置全局窗口标题
        OCRTool.set_title(params.window_title)

        # 调用 click_img 方法
        success = OCRTool.click_img(
            image_path=params.image_path,
            interval=params.interval,
            retry_times=params.retry_times,
            threshold=params.threshold,
        )

        logger.info(f"图像点击完成: {params.image_path}, 结果: {success}")

        return ClickOut(
            code=200,
            status="success",
            message=f"图像点击{'成功' if success else '失败'}",
            success=success,
            attempts=params.retry_times,
        )

    except Exception as e:
        logger.error(f"图像点击失败: {type(e).__name__}: {str(e)}")
        return ClickOut(
            code=500,
            status="error",
            message=f"图像点击失败: {type(e).__name__}: {str(e)}",
            success=False,
            attempts=0,
        )


@router.post(
    "/click/text",
    tags=["Action"],
    summary="点击指定文字位置",
    response_model=ClickOut,
    status_code=200,
)
async def click_text(params: ClickTextIn = Body(...)) -> ClickOut:
    """
    截图、OCR识别并点击与文字一致的位置

    Args:
        params: 点击文字参数
            - window_title: 窗口标题关键字
            - text: 要查找并点击的文字内容
            - interval: 截图间隔时间（秒），默认为 0
            - retry_times: 重复截图次数，默认为 1

    Returns:
        ClickOut: 包含点击结果和尝试次数
    """
    try:
        # 设置全局窗口标题
        OCRTool.set_title(params.window_title)

        # 调用 click_txt 方法
        success = OCRTool.click_txt(
            text=params.text, interval=params.interval, retry_times=params.retry_times
        )

        logger.info(f"文字点击完成: '{params.text}', 结果: {success}")

        return ClickOut(
            code=200,
            status="success",
            message=f"文字点击{'成功' if success else '失败'}",
            success=success,
            attempts=params.retry_times,
        )

    except Exception as e:
        logger.error(f"文字点击失败: {type(e).__name__}: {str(e)}")
        return ClickOut(
            code=500,
            status="error",
            message=f"文字点击失败: {type(e).__name__}: {str(e)}",
            success=False,
            attempts=0,
        )
