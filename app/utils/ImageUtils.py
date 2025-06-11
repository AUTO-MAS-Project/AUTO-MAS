import base64
import hashlib

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
