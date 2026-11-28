"""已登记插件包的静态头像资源。"""

import base64
import io
from pathlib import Path
from struct import unpack_from

from PIL import Image

from .catalog_protocol import MAX_ICON_BYTES

_MAX_SOURCE_BYTES = 256 * 1024


def _check_static_png(raw: bytes) -> None:
    """解码前检查画布尺寸并拒绝动画块。"""
    if (
        len(raw) < 33
        or raw[:16] != b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR"
        or not all(0 < edge <= 1024 for edge in unpack_from(">II", raw, 16))
    ):
        raise ValueError("invalid PNG signature or canvas size")
    offset = 8
    while offset + 12 <= len(raw):
        length, chunk = unpack_from(">I4s", raw, offset)
        offset += length + 12
        if offset > len(raw):
            break
        if chunk in {b"acTL", b"fcTL", b"fdAT"}:
            raise ValueError("animated icons are unsupported")
        if chunk == b"IEND" and length == 0 and offset == len(raw):
            return
    raise ValueError("incomplete PNG")


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
    _check_static_png(raw)
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
