"""失败回放的宿主侧：把 worker 写出的帧序列合成 VP8 WebM，历史页的 ``<video>`` 直接放。

后端环境的 opencv-python 自带 libvpx：VP8 能写，H.264 缺 libopenh264 打不开，VP9 太慢
（2026-10-27 实测 60 帧 1280×720：VP8 6.6 s、5.3 MB）。``cv2.putText`` 写不了中文，
字幕和识别框用 Pillow 画。worker 侧见 ``tools/core/runner/frame_replay.py``。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.task.MaaFW.tools.core.runner.frame_replay import FRAME_REPLAY_TIMELINE

# Pillow 的解码插件在导入线程载入，合成在工作线程里跑
Image.init()

FRAME_REPLAY_VIDEO_SUFFIX = ".webm"
# worker 流水线取帧上限就是每秒 2 帧
_FPS = 2
# 画面不变时 worker 不存新帧，一帧可能停几十秒；视频里最多停这么久，真实时刻看字幕
_MAX_HOLD_SECONDS = 3.0
_LAST_HOLD_SECONDS = 2.0
_CAPTION_FONT_RATIO = 0.032
_FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("C:/Windows/Fonts/simhei.ttf"),
)


def compose_frame_replay(segment: Path) -> Path | None:
    """把一段帧序列合成 ``<段名>.webm``（与段目录同级），没有可用的帧时返回 None。"""

    timeline = json.loads((segment / FRAME_REPLAY_TIMELINE).read_text(encoding="utf-8"))
    entries = [
        entry
        for entry in timeline
        if isinstance(entry, dict) and (segment / str(entry.get("file"))).is_file()
    ]
    if not entries:
        return None
    with Image.open(segment / entries[0]["file"]) as first:
        # VP8 要偶数宽高；MaaEnd 截图就是 1283×720
        width, height = first.width // 2 * 2, first.height // 2 * 2
    font = _caption_font(max(14, round(height * _CAPTION_FONT_RATIO)))
    output = segment.with_name(segment.name + FRAME_REPLAY_VIDEO_SUFFIX)
    writer = cv2.VideoWriter(
        str(output), cv2.VideoWriter_fourcc(*"VP80"), _FPS, (width, height)
    )
    if not writer.isOpened():
        raise RuntimeError("无法创建 VP8 视频编码器")
    try:
        for index, entry in enumerate(entries):
            if index + 1 < len(entries):
                hold = float(entries[index + 1]["at"]) - float(entry["at"])
            else:
                hold = _LAST_HOLD_SECONDS
            repeats = max(1, round(min(hold, _MAX_HOLD_SECONDS) * _FPS))
            frame = _render_frame(segment / entry["file"], entry, (width, height), font)
            for _ in range(repeats):
                writer.write(frame)
    finally:
        writer.release()
    if not output.is_file() or output.stat().st_size == 0:
        return None
    return output


def _caption_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def _render_frame(
    path: Path,
    entry: dict[str, Any],
    size: tuple[int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> Any:
    with Image.open(path) as source:
        image = source.convert("RGB")
    source_size = image.size
    scale = 1.0
    if image.size != size:
        # 窗口中途改了大小：等比缩进第一帧的尺寸，四周补黑
        scale = min(size[0] / image.width, size[1] / image.height)
        scaled = image.resize(
            (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        )
        canvas = Image.new("RGB", size)
        offset = ((size[0] - scaled.width) // 2, (size[1] - scaled.height) // 2)
        canvas.paste(scaled, offset)
        image = canvas
    else:
        offset = (0, 0)
    draw = ImageDraw.Draw(image, "RGBA")
    box = entry.get("box")
    # DirectHit 这类整屏的框画出来只是一圈边，不画
    full_screen = (
        isinstance(box, list)
        and len(box) == 4
        and box[2] >= source_size[0]
        and box[3] >= source_size[1]
    )
    if isinstance(box, list) and len(box) == 4 and not full_screen:
        x, y, w, h = (value * scale for value in box)
        left, top = offset[0] + x, offset[1] + y
        draw.rectangle(
            (left, top, left + w, top + h),
            outline=(0, 255, 0, 255),
            width=max(2, size[1] // 360),
        )
    caption = _caption(entry)
    margin = max(4, size[1] // 120)
    text_box = draw.textbbox((0, 0), caption, font=font)
    bar_height = text_box[3] - text_box[1] + margin * 2
    draw.rectangle((0, size[1] - bar_height, size[0], size[1]), fill=(0, 0, 0, 160))
    draw.text(
        (margin, size[1] - bar_height + margin - text_box[1]),
        caption,
        font=font,
        fill=(255, 255, 255, 255),
    )
    return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)


def _caption(entry: dict[str, Any]) -> str:
    """字幕：时刻 · 任务 · 节点 · 动作，没有的项不写。"""

    parts = [time.strftime("%H:%M:%S", time.localtime(float(entry["at"])))]
    if entry.get("task"):
        parts.append(str(entry["task"]))
    node = entry.get("hit") or entry.get("node")
    if node:
        parts.append(str(node))
    if entry.get("final"):
        parts.append("失败截图")
    elif entry.get("action"):
        action = str(entry["action"])
        parts.append(f"{action}（失败）" if entry.get("actionFailed") else action)
    return " · ".join(parts)
