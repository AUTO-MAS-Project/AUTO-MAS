#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""通用轻量 OCR 工具集。

基于 RapidOCR（rapidocr_onnxruntime，CPU 可跑、中文识别准确）提供纯视觉识别
能力，供各专项复用（当前由 ok-ww 强制账号切换使用；MaaEnd 登录仍为历史私有
实现，未迁移前保持现状）。窗口捕获、坐标点击等交互层由各专项自行实现，本
模块不依赖任何游戏或专项。

示例::

    from app.tools.ocr import ocr_image, ocr_texts

    items = ocr_image(frame, roi=(100, 100, 800, 600))
    texts = ocr_texts(frame)
"""

from functools import lru_cache
from typing import TypeAlias

import numpy as np
from rapidocr_onnxruntime import RapidOCR

from app.utils import get_logger

logger = get_logger("OCR 工具集")

# 识别框（相对输入图像的像素坐标）：(x, y, width, height)
Box: TypeAlias = tuple[int, int, int, int]
# 识别条目：文本 + 识别框
OCRItem: TypeAlias = tuple[str, Box]


@lru_cache(maxsize=1)
def _ocr_engine() -> RapidOCR:
    """懒加载共享 RapidOCR 引擎，进程内仅初始化一次。"""
    return RapidOCR()


def ocr_image(frame: np.ndarray, roi: Box | None = None) -> list[OCRItem]:
    """对图像执行 OCR，返回带全局坐标的文字框列表。

    Args:
        frame: 图像数据（BGR/灰度均可）。
        roi: 可选裁剪区域 (left, top, right, bottom)；识别后坐标自动加回偏移。

    Returns:
        识别条目列表，坐标为相对输入 frame 的像素坐标。
    """
    left, top = 0, 0
    crop = frame
    if roi is not None:
        left, top, right, bottom = roi
        crop = frame[top:bottom, left:right]

    result, _ = _ocr_engine()(crop)
    items: list[OCRItem] = []
    for line in result or []:
        points, text, _ = line
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        box = (
            left + round(min(xs)),
            top + round(min(ys)),
            round(max(xs) - min(xs)),
            round(max(ys) - min(ys)),
        )
        items.append(("".join(str(text).split()), box))
    return items


def ocr_texts(frame: np.ndarray, roi: Box | None = None) -> list[str]:
    """仅返回识别到的文本列表，便于快速判定文字存在性。"""
    return [text for text, _ in ocr_image(frame, roi)]
