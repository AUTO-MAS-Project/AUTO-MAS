#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025 AUTO-MAS Team

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
from typing import Literal, Optional
import base64
from io import BytesIO

from app.utils.OCR.OCRtool import OCRTool
from app.utils import get_logger
from app.models.schema import OutBase

logger = get_logger("OCR API")

router = APIRouter(prefix="/api/ocr", tags=["OCR识别"])


class OCRScreenshotIn(BaseModel):
    window_title: str = Field(..., description="窗口标题（用于查找窗口）")
    should_preprocess: bool = Field(default=True, description="是否预处理图片区域，True时排除边框和标题栏，False时使用完整窗口")
    aspect_ratio_width: int = Field(default=16, description="宽高比宽度")
    aspect_ratio_height: int = Field(default=9, description="宽高比高度")
    region: Optional[tuple[int, int, int, int]] = Field(default=None, description="自定义截图区域 (left, top, width, height)")


class OCRScreenshotOut(OutBase):
    image_base64: str = Field(..., description="截图的Base64编码（PNG格式）")
    region: tuple[int, int, int, int] = Field(..., description="实际使用的截图区域 (left, top, width, height)")
    image_width: int = Field(..., description="截图宽度")
    image_height: int = Field(..., description="截图高度")


@router.post(
    "/screenshot",
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
        ocr_tool = OCRTool(width=params.aspect_ratio_width, height=params.aspect_ratio_height)

        # 获取截图区域（如果没有提供自定义区域）
        if params.region is None:
            region = OCRTool.get_screenshot_region(params.window_title, params.should_preprocess)
        else:
            region = params.region

        # 获取截图
        screenshot_image = OCRTool.get_screenshot(
            title=params.window_title,
            should_preprocess=params.should_preprocess,
            region=region
        )

        # 将PIL Image转换为Base64
        buffer = BytesIO()
        screenshot_image.save(buffer, format="PNG")
        image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        logger.info(f"成功截取窗口 [{params.window_title}] 的截图，区域: {region}")

        return OCRScreenshotOut(
            code=200,
            status="success",
            message="截图成功",
            image_base64=image_base64,
            region=region,
            image_width=screenshot_image.width,
            image_height=screenshot_image.height
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
            image_height=0
        )
