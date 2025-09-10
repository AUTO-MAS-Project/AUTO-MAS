#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025 ClozyA

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


import base64
import hashlib
from pathlib import Path

from PIL import Image


class ImageUtils:
    @staticmethod
    def get_base64_from_file(image_path):
        """从本地文件读取并返回base64编码字符串"""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    @staticmethod
    def calculate_md5_from_file(image_path):
        """从本地文件读取并返回md5值（hex字符串）"""
        with open(image_path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()

    @staticmethod
    def calculate_md5_from_base64(base64_content):
        """从base64字符串计算md5"""
        image_data = base64.b64decode(base64_content)
        return hashlib.md5(image_data).hexdigest()

    @staticmethod
    def compress_image_if_needed(image_path: Path, max_size_mb=2) -> Path:
        """
        如果图片大于max_size_mb, 则压缩并覆盖原文件, 返回原始路径（Path对象）
        """

        RESAMPLE = Image.Resampling.LANCZOS  # Pillow 9.1.0及以后

        max_size = max_size_mb * 1024 * 1024
        if image_path.stat().st_size <= max_size:
            return image_path

        img = Image.open(image_path)
        suffix = image_path.suffix.lower()
        quality = 90 if suffix in [".jpg", ".jpeg"] else None
        step = 5

        if quality is not None:
            while True:
                img.save(image_path, quality=quality, optimize=True)
                if image_path.stat().st_size <= max_size or quality <= 10:
                    break
                quality -= step
        elif suffix == ".png":
            width, height = img.size
            while True:
                img.save(image_path, optimize=True)
                if (
                    image_path.stat().st_size <= max_size
                    or width <= 200
                    or height <= 200
                ):
                    break
                width = int(width * 0.95)
                height = int(height * 0.95)
                img = img.resize((width, height), RESAMPLE)
        else:
            raise ValueError("仅支持JPG/JPEG和PNG格式图片的压缩")

        return image_path
