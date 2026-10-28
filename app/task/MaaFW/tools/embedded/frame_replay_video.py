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
# 画面不变时 worker 不存新帧，一步可能停几十秒；视频里最多停这么久，真实时刻看字幕
_MAX_HOLD_SECONDS = 3.0
_LAST_HOLD_SECONDS = 2.0
_CAPTION_FONT_RATIO = 0.032
# 都没有时退回 Pillow 自带的 FreeType 默认字体：中文显示成方框，但不会报错
_FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("C:/Windows/Fonts/simhei.ttf"),
    Path("C:/Windows/Fonts/Deng.ttf"),
    Path("C:/Windows/Fonts/simsun.ttc"),
)


def compose_frame_replay(segment: Path) -> Path | None:
    """把一段帧序列合成 ``<段名>.webm``（与段目录同级），没有可用的帧时返回 None。

    一帧画面上记了几步就按几步出字幕，每步停到下一步（或下一帧）开始，最多 3 秒。
    """

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
    size = (width, height)
    font = _caption_font(max(14, round(height * _CAPTION_FONT_RATIO)))
    output = segment.with_name(segment.name + FRAME_REPLAY_VIDEO_SUFFIX)
    writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"VP80"), _FPS, size)
    if not writer.isOpened():
        raise RuntimeError("无法创建 VP8 视频编码器")
    try:
        for index, entry in enumerate(entries):
            next_at = (
                float(entries[index + 1]["at"]) if index + 1 < len(entries) else None
            )
            steps = [
                step for step in entry.get("steps") or [] if isinstance(step, dict)
            ]
            if not steps:
                steps = [{"at": entry["at"]}]
            base, scale, offset = _load_frame(segment / entry["file"], size)
            for position, step in enumerate(steps):
                end = (
                    float(steps[position + 1]["at"])
                    if position + 1 < len(steps)
                    else next_at
                )
                hold = (
                    end - float(step["at"]) if end is not None else _LAST_HOLD_SECONDS
                )
                frame = _annotate(base.copy(), entry, step, scale, offset, font)
                for _ in range(max(1, round(min(hold, _MAX_HOLD_SECONDS) * _FPS))):
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


def _load_frame(
    path: Path, size: tuple[int, int]
) -> tuple[Image.Image, float, tuple[int, int]]:
    """读一帧并放进视频尺寸：窗口中途改了大小时等比缩进去、四周补黑。"""

    with Image.open(path) as source:
        image = source.convert("RGB")
    if image.size == size:
        return image, 1.0, (0, 0)
    scale = min(size[0] / image.width, size[1] / image.height)
    scaled = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    )
    canvas = Image.new("RGB", size)
    offset = ((size[0] - scaled.width) // 2, (size[1] - scaled.height) // 2)
    canvas.paste(scaled, offset)
    return canvas, scale, offset


def _annotate(
    image: Image.Image,
    entry: dict[str, Any],
    step: dict[str, Any],
    scale: float,
    offset: tuple[int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> Any:
    size = image.size
    draw = ImageDraw.Draw(image, "RGBA")
    box = step.get("box")
    if isinstance(box, list) and len(box) == 4:
        x, y, w, h = (value * scale for value in box)
        # DirectHit 这类整屏的框画出来只是一圈边，不画
        if w < size[0] - 2 * offset[0] or h < size[1] - 2 * offset[1]:
            left, top = offset[0] + x, offset[1] + y
            draw.rectangle(
                (left, top, left + w, top + h),
                outline=(0, 255, 0, 255),
                width=max(2, size[1] // 360),
            )
    caption = _caption(entry, step)
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


def _caption(entry: dict[str, Any], step: dict[str, Any]) -> str:
    """字幕：时刻 · 任务 · 节点 · 动作，没有的项不写。"""

    parts = [time.strftime("%H:%M:%S", time.localtime(float(step["at"])))]
    if entry.get("task"):
        parts.append(str(entry["task"]))
    node = step.get("hit") or step.get("node")
    if node:
        parts.append(str(node))
    if entry.get("final"):
        parts.append("失败截图")
    elif step.get("action"):
        action = str(step["action"])
        parts.append(f"{action}（失败）" if step.get("actionFailed") else action)
    return " · ".join(parts)
