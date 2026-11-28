"""已登记插件包的静态头像资源。"""

import base64
import io
from pathlib import Path

from PIL import Image

from .catalog_protocol import MAX_ICON_BYTES

_MAX_SOURCE_BYTES = 256 * 1024


def read_package_icon(package: Path) -> str | None:
    """读取已登记的包根 PNG 并重编码，限制原图的字节数和像素尺寸。"""
    root = package.resolve()
    file = root / "auto_mas_icon.png"
    try:
        resolved = file.resolve(strict=True)
    except FileNotFoundError:
        return None
    if resolved.parent != root or resolved != file:
        raise ValueError("插件图标必须位于包根目录")
    if not resolved.is_file():
        raise ValueError("插件图标必须是文件")
    with resolved.open("rb") as stream:
        raw = stream.read(_MAX_SOURCE_BYTES + 1)
    if len(raw) > _MAX_SOURCE_BYTES:
        raise ValueError("插件图标文件过大")
    with Image.open(io.BytesIO(raw), formats=("PNG",)) as image:
        if max(image.size) > 1024 or getattr(image, "is_animated", False):
            raise ValueError("头像尺寸过大或包含动画")
        rgba = image.convert("RGBA")
    for size in (128, 96, 64):
        rgba.thumbnail((size, size), Image.Resampling.LANCZOS)
        clean = Image.frombytes("RGBA", rgba.size, rgba.tobytes())
        out = io.BytesIO()
        clean.save(out, format="PNG", optimize=True)
        if len(out.getbuffer()) <= MAX_ICON_BYTES:
            return base64.b64encode(out.getvalue()).decode("ascii")
    raise ValueError("头像超过目录体积限制")
