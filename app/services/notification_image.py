"""社区通知图片绘制；由宿主在提交线程工作前加载 Pillow 及图片插件。"""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Pillow 的编码器插件也先在调用线程载入，工作线程只测量、绘制和编码。
Image.init()


def encode_screenshot(data: bytes, *, quality: int) -> bytes:
    with Image.open(BytesIO(data)) as image:
        buffer = BytesIO()
        image.convert("RGB").save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


_FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("C:/Windows/Fonts/simhei.ttf"),
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
)
_SYMBOL_FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/seguiemj.ttf"),
    Path("/System/Library/Fonts/Apple Color Emoji.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoEmoji-Regular.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
)
_SYMBOL_FALLBACK = {"✅": "[OK]", "❌": "[X]", "📥": "[+]"}


def _load_notification_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """加载可显示中文的通知字体，缺失时回退到 Pillow 内置字体。"""

    for path in _FONT_CANDIDATES:
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def _load_notification_symbol_font(size: int) -> ImageFont.FreeTypeFont | None:
    """加载通知符号字体，固定尺寸字体不可用时保留文字回退。"""

    for path in _SYMBOL_FONT_CANDIDATES:
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    return None


def _notification_text_runs(
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    symbol_font: ImageFont.FreeTypeFont | None,
) -> list[tuple[str, ImageFont.FreeTypeFont | ImageFont.ImageFont]]:
    """测量与绘制使用相同字体，避免中文字体缺少图标时产生方框。"""

    runs = []
    for part in re.split(r"([✅❌📥])", text):
        if not part:
            continue
        if part in _SYMBOL_FALLBACK:
            runs.append(
                (part, symbol_font) if symbol_font else (_SYMBOL_FALLBACK[part], font)
            )
        else:
            runs.append((part, font))
    return runs


def _wrap_notification_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
    *,
    symbol_font: ImageFont.FreeTypeFont | None = None,
) -> list[str]:
    """按像素宽度换行，兼容中文这类没有空格分隔的长文本。"""

    lines: list[str] = []
    current = ""
    for char in text:
        if char == "\n":
            lines.append(current)
            current = ""
            continue
        candidate = current + char
        candidate_width = sum(
            draw.textlength(part, font=run_font)
            for part, run_font in _notification_text_runs(
                candidate, font=font, symbol_font=symbol_font
            )
        )
        if current and candidate_width > max_width:
            lines.append(current)
            current = char
        else:
            current = candidate
    lines.append(current)
    return lines


def render_community_image(
    rows: list[tuple[str, str]],
) -> bytes:
    """把社区签到结果渲染为适合聊天渠道展示的 PNG 图片。"""

    width = 760
    card_margin = 16
    padding = 32
    inner_width = width - (card_margin + padding) * 2
    row_specs: list[tuple[str, list[str], int]] = []
    total_height = card_margin * 2 + padding * 2
    symbol_font = _load_notification_symbol_font(22)

    with Image.new("RGB", (width, 100), "#f4f4f4") as measure_image:
        measure = ImageDraw.Draw(measure_image)
        for kind, text in rows:
            if kind == "title":
                size = 32
                spacing = 16
            elif kind == "heading":
                size = 24
                spacing = 14
            elif kind == "footer":
                size = 18
                spacing = 16
            else:
                size = 22
                spacing = 8
            font = _load_notification_font(size)
            lines = _wrap_notification_text(
                measure,
                text,
                font,
                inner_width,
                symbol_font=symbol_font,
            )
            line_height = int(size * 1.55)
            row_height = len(lines) * line_height
            row_specs.append((kind, lines, row_height))
            total_height += row_height + spacing

    image = Image.new("RGB", (width, total_height), "#f4f4f4")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (card_margin, card_margin, width - card_margin, total_height - card_margin),
        radius=18,
        fill="#ffffff",
    )

    y = card_margin + padding
    for kind, lines, row_height in row_specs:
        if kind == "title":
            font = _load_notification_font(32)
            color = "#009faa"
            spacing = 16
        elif kind == "heading":
            font = _load_notification_font(24)
            color = "#009faa"
            spacing = 14
        elif kind == "footer":
            font = _load_notification_font(18)
            color = "#888888"
            spacing = 16
        else:
            font = _load_notification_font(22)
            color = "#303133"
            spacing = 8

        for line_index, line in enumerate(lines):
            x = 48.0
            line_y = y + line_index * (row_height // len(lines))
            baseline = (
                font.getmetrics()[0] if isinstance(font, ImageFont.FreeTypeFont) else 0
            )
            for part, run_font in _notification_text_runs(
                line, font=font, symbol_font=symbol_font
            ):
                draw.text(
                    (x, line_y + baseline),
                    part,
                    font=run_font,
                    fill=color,
                    anchor="ls" if baseline else None,
                    embedded_color=True,
                )
                x += draw.textlength(part, font=run_font)
        y += row_height + spacing

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
