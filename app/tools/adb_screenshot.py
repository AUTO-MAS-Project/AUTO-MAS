"""公共 ADB 截图工具；实例归属由调用方提供，不依赖任何脚本适配器。"""

import asyncio
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from PIL import Image

from app.models.emulator import DeviceInfo, DeviceRef
from app.tools.adb_controller import (
    build_adb_emulator_extra_capabilities,
    build_ldplayer_extra_config,
    build_mumu_extra_config,
    same_adb_device,
)
from app.tools.python_environment import strip_host_python_environment
from app.utils import get_logger
from app.utils.platform.common.process_runner import create_subprocess
from app.utils.platform.process import platform_process

logger = get_logger("ADB 截图")
_CAPTURE_TIMEOUT = 60
_WORKER_TIMEOUT = 25
_SCREENSHOT_WORKER = Path(__file__).with_name("_adb_screenshot_worker.py").resolve()
# 按独立文件执行，便携 ._pth 不必认识源码包，也不会执行宿主包的 __init__。
_WORKER_BOOTSTRAP = (
    "import runpy, sys; runpy.run_path(sys.argv[1], run_name='__main__')"
)


async def capture_adb_screenshot(
    *,
    adb_path: Path | str | None,
    adb_address: str,
    device_ref: DeviceRef | None = None,
    emulator_info: DeviceInfo | None = None,
) -> Image.Image | None:
    """通过 MaaFramework SDK 取当前帧，增强失败退回普通 ADB。

    只复用调用方提供的实例与启动信息，不启动模拟器控制台查询；缺少启动信息时
    仅用普通 ADB。连接和取图在一次性进程内执行，超时或取消先回收进程树。
    返回独立的 RGB Pillow 图像；失败记日志并返回 None，取消继续向外传递。
    """

    if not adb_path or adb_address in ("", "Unknown"):
        return None
    try:
        with TemporaryDirectory(prefix="adb-screenshot-") as directory:
            output = Path(directory) / "screen.png"
            async with asyncio.timeout(_CAPTURE_TIMEOUT):
                config = _build_extra_config(
                    device_ref=device_ref,
                    adb_address=adb_address,
                    emulator_info=emulator_info,
                )
                modes = (True, False) if config else (False,)
                for use_extras in modes:
                    try:
                        await asyncio.wait_for(
                            _capture_in_worker(
                                adb_path=str(adb_path),
                                adb_address=adb_address,
                                config=config,
                                use_extras=use_extras,
                                output=output,
                            ),
                            timeout=_WORKER_TIMEOUT,
                        )
                        break
                    except Exception as exc:  # noqa: BLE001
                        if not use_extras:
                            raise
                        logger.warning(f"MaaFW 模拟器增强截图失败，改用普通 ADB: {exc}")
            # 复制出独立帧再清理临时文件，调用方决定怎样使用或保存。
            with Image.open(output) as image:
                return image.copy()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"ADB 截图失败: {exc}")
        return None


def _build_extra_config(
    *,
    device_ref: DeviceRef | None,
    adb_address: str,
    emulator_info: DeviceInfo | None,
) -> dict[str, Any]:
    if device_ref is None or emulator_info is None:
        return {}
    try:
        capability = build_adb_emulator_extra_capabilities().get(
            device_ref.emulator_type, {}
        )
        if not capability.get("screencap"):
            return {}
        if not same_adb_device(emulator_info.adb_address, adb_address):
            logger.warning("补截地址与所选模拟器实例不匹配，使用普通 ADB")
            return {}
        manager_path = Path(device_ref.manager_path)
        native_index = int(device_ref.native_index)
        if device_ref.emulator_type == "mumu":
            return build_mumu_extra_config(
                manager_path=manager_path, native_index=native_index
            )
        if device_ref.emulator_type == "ldplayer":
            return build_ldplayer_extra_config(
                manager_path=manager_path,
                native_index=native_index,
                pid=emulator_info.pid,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"构造截图增强配置失败，使用普通 ADB: {exc}")
    return {}


async def _capture_in_worker(
    *,
    adb_path: str,
    adb_address: str,
    config: dict[str, Any],
    use_extras: bool,
    output: Path,
) -> None:
    environment = strip_host_python_environment()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    source_root = Path(__file__).resolve().parents[2]
    # 启动途中也可能取消：保留启动任务，取回进程句柄后再回收，不能留下孤儿。
    starting = asyncio.create_task(
        create_subprocess(
            sys.executable,
            "-c",
            _WORKER_BOOTSTRAP,
            str(_SCREENSHOT_WORKER),
            cwd=source_root,
            env=environment,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            # 原生库的子进程可能继承标准句柄；不用输出管道，避免它们拖住回收。
            stderr=asyncio.subprocess.DEVNULL,
        )
    )
    process = None
    try:
        process = await asyncio.shield(starting)
        await process.communicate(
            json.dumps(
                {
                    "adb_path": adb_path,
                    "adb_address": adb_address,
                    "config": config,
                    "use_extras": use_extras,
                    "output": str(output),
                },
                ensure_ascii=False,
            ).encode("utf-8")
        )
        if process.returncode != 0:
            error_path = output.with_suffix(".error.txt")
            error = (
                error_path.read_text(encoding="utf-8") if error_path.is_file() else ""
            )
            raise RuntimeError(
                error.strip()[-2000:] or f"截图进程退出码: {process.returncode}"
            )
    finally:
        if process is None or process.returncode is None:
            cleanup = asyncio.create_task(_reap_capture_worker(starting))
            cancelled = False
            # 用户停止与总时限可能先后取消；回收必须完成，取消随后继续向外传递。
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    cancelled = True
            cleanup.result()
            if cancelled:
                raise asyncio.CancelledError


async def _reap_capture_worker(
    starting: asyncio.Task[asyncio.subprocess.Process],
) -> None:
    process = await starting
    if process.returncode is not None:
        return
    try:
        # MaaFW 可能还在等自己启动的 adb 命令；先按进程树一起回收。
        async with asyncio.timeout(5):
            killed, reason = await platform_process.kill_process(
                process.pid, kill_tree=True
            )
        if not killed:
            logger.warning(f"回收截图进程树失败，直接结束截图进程: {reason}")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"回收截图进程树失败，直接结束截图进程: {exc}")
    finally:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        await process.wait()
