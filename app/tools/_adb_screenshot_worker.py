"""一次性 ADB 截图进程（使用 MaaFramework SDK）；原生连接或截图卡住时由宿主终止。"""

import json
import sys
from pathlib import Path
from typing import Any


def capture_screen(payload: dict[str, Any]) -> None:
    """只连接、取图，不下发任务或输入；输出原始分辨率的 RGB PNG。"""

    from maa.controller import (
        AdbController,
        MaaAdbInputMethodEnum,
        MaaAdbScreencapMethodEnum,
    )
    from maa.toolkit import Toolkit
    from PIL import Image

    output = Path(payload["output"])
    # 原生日志也留在本次临时目录，避免污染宿主的 MaaFW 日志。
    Toolkit.init_option(output.parent)
    controller = AdbController(
        adb_path=payload["adb_path"],
        address=payload["adb_address"],
        screencap_methods=(
            MaaAdbScreencapMethodEnum.EmulatorExtras
            if payload["use_extras"]
            else MaaAdbScreencapMethodEnum.Encode
            | MaaAdbScreencapMethodEnum.EncodeToFileAndPull
            | MaaAdbScreencapMethodEnum.RawWithGzip
        ),
        input_methods=MaaAdbInputMethodEnum.AdbShell,
        config=payload["config"] if payload["use_extras"] else {},
    )
    try:
        if not controller.set_screenshot_use_raw_size(enable=True):
            raise RuntimeError("设置截图原始分辨率失败")
        job = controller.post_connection().wait()
        if not job.succeeded:
            raise RuntimeError("MaaFW 连接设备失败")
        shot = controller.post_screencap().wait()
        if not shot.succeeded:
            raise RuntimeError("MaaFW 截图失败")
        frame = shot.get()
        if frame is None or frame.size == 0:
            raise RuntimeError("MaaFW 截图为空")
        # MaaFW 输出 BGR，Pillow 使用 RGB；不让通知中的红蓝色互换。
        image = Image.fromarray(frame[:, :, ::-1].copy())
        low, high = image.convert("L").getextrema()
        if high - low < 8:
            raise RuntimeError("截图为纯色画面（疑似未取到游戏渲染层）")
        image.save(output, format="PNG")
    finally:
        # Python binding 在析构时调用 MaaControllerDestroy。
        del controller


def main() -> int:
    payload = json.loads(sys.stdin.buffer.read())
    try:
        capture_screen(payload)
    except Exception as exc:  # noqa: BLE001 - 诊断旁路交由宿主降级
        Path(payload["output"]).with_suffix(".error.txt").write_text(
            f"{type(exc).__name__}: {exc}", encoding="utf-8"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
