import base64
import hashlib
import os
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
    def compress_image_if_needed(image_path, max_size_mb=2):
        """
        如果图片大于max_size_mb（默认2MB），则压缩到max_size_mb以内，
        返回压缩后文件路径（压缩文件与原图同目录，命名为xxx_compressed.xxx），
        如果不超过则返回原文件路径
        """

        if hasattr(Image, "Resampling"):  # Pillow 9.1.0及以后
            RESAMPLE = Image.Resampling.LANCZOS
        else:  # Pillow 老版本
            RESAMPLE = Image.ANTIALIAS

        max_size = max_size_mb * 1024 * 1024
        file_size = os.path.getsize(image_path)
        if file_size <= max_size:
            return image_path  # 小于2MB，直接返回原路径

        # 只支持JPEG、PNG压缩
        file_root, file_ext = os.path.splitext(image_path)
        compressed_path = f"{file_root}_compressed{file_ext}"

        img = Image.open(image_path)
        quality = 90 if file_ext.lower() in ['.jpg', '.jpeg'] else None
        step = 5  # 每次降低5质量或5%尺寸

        # 如果是JPG/JPEG
        if file_ext.lower() in ['.jpg', '.jpeg']:
            while True:
                img.save(compressed_path, quality=quality, optimize=True)
                if os.path.getsize(compressed_path) <= max_size or quality <= 10:
                    break
                quality -= step
        # PNG 只能调整尺寸来压缩
        elif file_ext.lower() == '.png':
            width, height = img.size
            while True:
                img.save(compressed_path, optimize=True)
                if os.path.getsize(compressed_path) <= max_size or width <= 200 or height <= 200:
                    break
                width = int(width * 0.95)
                height = int(height * 0.95)
                img = img.resize((width, height), RESAMPLE)
        else:
            raise ValueError("仅支持JPG/JPEG和PNG格式图片的压缩。")

        return compressed_path
