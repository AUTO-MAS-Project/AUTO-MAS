#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""失败截图诊断落盘工具。

各专项（MaaEnd 登录、OK-WW / OK-NTE / BetterGI 切号、OK-NTE 启动器）失败时
把窗口截图落盘到 ``debug/<专项目录>/``，供问题包导出与人工排查。截图只给
人看、没有任何代码回读，因此统一存 JPEG——游戏画面（渐变 + 纹理）对 PNG
无损压缩极不友好，2K 窗口实测单张约 3MB；JPEG 后典型 300-500KB。超过
1080p 长边先降采样：OCR 在 1080p 基准空间识别，更高分辨率不增加诊断价值。
清理由 ``Config.clean_debug_diagnostics`` 自动扫描 ``debug/`` 子目录完成，
新专项无需登记。

示例::

    from app.tools.error_screenshot import save_error_screenshot

    save_error_screenshot(image, "bgi-account-switch", "switch-error")
"""

from datetime import datetime
from pathlib import Path

from PIL import Image

from app.utils import get_logger

logger = get_logger("失败截图")

# JPEG 有损压缩质量：登录/切号界面文字在该质量下仍清晰可读
_JPEG_QUALITY = 85
# 降采样上限（对齐 OCR 的基准识别分辨率），只缩不放
_MAX_EDGE = 1920


def save_error_screenshot(
    image: Image.Image, dir_name: str, file_prefix: str
) -> Path | None:
    """把失败截图压缩落盘到 ``debug/<dir_name>/<file_prefix>-<时间戳>.jpg``。

    诊断旁路：任何失败只记日志不抛出，不影响调用方的原始异常。

    Args:
        image: 已捕获的窗口截图（任意模式，非 RGB 自动转换）；RGB 输入会被
            原地降采样，调用后不应复用该对象。
        dir_name: ``debug/`` 下的诊断子目录名（按专项命名）。
        file_prefix: 文件名前缀（如 ``switch-error``）。

    Returns:
        落盘路径；失败时返回 ``None``。
    """

    try:
        screenshot_dir = Path.cwd() / "debug" / dir_name
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.thumbnail((_MAX_EDGE, _MAX_EDGE))
        screenshot_path = screenshot_dir / (
            f"{file_prefix}-{datetime.now():%Y%m%d-%H%M%S-%f}.jpg"
        )
        image.save(screenshot_path, format="JPEG", quality=_JPEG_QUALITY)
        logger.warning(f"失败截图已保存: {screenshot_path}")
        return screenshot_path
    except Exception as error:
        logger.warning(f"失败截图保存失败: {error}")
        return None
