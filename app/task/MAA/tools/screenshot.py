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
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""MAA 失败画面取图工具。

两个来源，优先级从高到低：

1. 上游产物：MAA（MaaCore）在任务链没跑完时会把当时的画面存进安装目录
   ``debug/interface/``（子任务失败或被停止各落一张；开始唤醒链不落图，
   上游自会按数量上限清理旧图）。只在通知需要附图时读取本轮最新的一张，
   属于对上游产物的透传读取，不写 MAA 目录。
2. MAS 补截：上游没落图的场景（登录链失败、进程超时等）通过 adb 截一张
   当前画面兜底，复用失败截图工具存入 MAS 的 ``debug/maa-failure/``，
   供通知与问题包共用。

``not_before`` 传本轮尝试的开始时刻：目录长期累积，不用时间窗会把上一次
运行的旧图当成这次的现场。
"""

import asyncio
from datetime import datetime
from pathlib import Path

from app.tools.error_screenshot import save_error_screenshot
from app.utils import get_logger

logger = get_logger("MAA 失败截图")

_FAILURE_IMAGE_SUFFIXES = frozenset({".png"})


def collect_maa_failure_image(
    maa_root_path: Path | str, *, not_before: datetime
) -> Path | None:
    """读取 MAA 上游本轮运行中落的最后一张失败画面。

    Args:
        maa_root_path: MAA 安装目录（脚本配置的 ``Info.Path``）。
        not_before: 本轮尝试的开始时刻，只认它之后修改的图。

    Returns:
        图片路径；目录不存在、本轮没有图或读取失败时返回 ``None``。
        截图是诊断旁路，任何失败只记日志，不抛出。
    """

    image_dir = Path(maa_root_path) / "debug" / "interface"
    try:
        entries = tuple(image_dir.iterdir())
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as exc:
        logger.warning(f"读取 MAA 失败截图目录失败: {exc}")
        return None

    not_before_ts = not_before.timestamp()
    candidates: list[tuple[float, Path]] = []
    for image_path in entries:
        if (
            image_path.suffix.lower() not in _FAILURE_IMAGE_SUFFIXES
            or image_path.is_symlink()
        ):
            continue
        try:
            if not image_path.is_file():
                continue
            stat = image_path.stat()
        except OSError as exc:
            logger.warning(f"读取 MAA 失败截图信息失败: {image_path.name} - {exc}")
            continue
        if stat.st_size > 0 and stat.st_mtime >= not_before_ts:
            candidates.append((stat.st_mtime, image_path))

    if not candidates:
        return None

    image_path = max(candidates, key=lambda item: item[0])[1]
    logger.info(f"使用 MAA 上游失败截图: {image_path.name}")
    return image_path


async def capture_current_screen(
    *, adb_path: Path | str | None, adb_address: str
) -> Path | None:
    """通过 adb 补截当前画面并保存为诊断图片，上游没留图时的兜底。

    只在 MAA 已退出之后调用（如收尾阶段）：登录链失败、进程超时这些上游
    不落图的场景，截到的是"此刻的屏幕"，不保证是异常发生瞬间——MAA 的
    结束动作可能已把游戏退掉。

    adb 路径传模拟器自带的 adb（MAA 自动探测的通常也是它，同一份二进制
    不会触发 adb server 版本重启）；路径取不到、地址为空或截图/画面异常
    （空、纯色——雷电上普通 adb 截图拿不到游戏渲染层）时返回 ``None``。
    截图是诊断旁路，任何失败只记日志，不抛出。
    """

    if not adb_path or adb_address in ("", "Unknown"):
        return None
    try:
        # 冷导入放在事件循环上完成，再进线程跑阻塞 IO
        from app.utils.OCR.OCRtool import OCRTool
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"加载 ADB 截图工具失败，通知不带图: {exc}")
        return None

    def _capture() -> Path | None:
        image = OCRTool.get_screenshot_with_adb(str(adb_path), adb_address)
        low, high = image.convert("L").getextrema()
        if high - low < 8:
            raise RuntimeError("截图为纯色画面（疑似未取到游戏渲染层），放弃")
        return save_error_screenshot(
            image=image, dir_name="maa-failure", file_prefix="failure"
        )

    try:
        return await asyncio.to_thread(_capture)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"MAA 补截当前画面失败，通知不带图: {exc}")
        return None
