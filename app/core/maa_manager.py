#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import json
from ctypes import c_void_p
from pathlib import Path
from typing import Any

from maa.context import Context

# from maa.define import LoggingLevelEnum
from maa.controller import (
    AdbController,
    Job,
    JobWithResult,
    MaaAdbInputMethodEnum,
    MaaAdbScreencapMethodEnum,
    MaaWin32InputMethodEnum,
    MaaWin32ScreencapMethodEnum,
    Win32Controller,
)
from maa.custom_action import CustomAction
from maa.resource import Resource
from maa.tasker import Tasker
from maa.toolkit import AdbDevice, Toolkit

from app.models.emulator import DeviceInfo, DeviceRef
from app.utils import get_logger, resource_path

from .config import Config

logger = get_logger("MaaFW管理")


class _MaaFWManager:
    def __init__(self):

        self.resource = Resource()

        (Config.config_path / "maa_option.json").write_text(
            json.dumps(
                {
                    "logging": False,
                    "save_draw": False,
                    "stdout_level": 2,
                    "save_on_error": False,
                    "draw_quality": 85,
                },
                ensure_ascii=False,
                indent=4,
            ),
            encoding="utf-8",
        )
        Toolkit.init_option(Path.cwd())
        self.resource.post_bundle(resource_path("MaaFW")).wait()

    @staticmethod
    async def do_job(job: Job | JobWithResult) -> Any:
        """
        等待任务完成并检查结果

        Args:
            job(Job | JobWithResult): 需要执行的 MaaFW 任务对象

        Raises:
            RuntimeError: 如果任务执行失败，则抛出异常，异常信息包含任务执行失败的相关信息
        """

        result = await Config.loop.run_in_executor(None, job.wait)

        if job.failed:
            if isinstance(result, JobWithResult):
                raise RuntimeError(f"任务执行失败, 执行信息: {result.get()}")
            elif isinstance(result, Job):
                raise RuntimeError("任务执行失败")

    @staticmethod
    async def convert_adb(
        raw_info: DeviceInfo, device_ref: DeviceRef | None = None
    ) -> AdbDevice:
        """
        将设备信息转换为ADB连接所需的地址格式

        Args:
            raw_info(DeviceInfo): 包含设备信息的对象
            device_ref(DeviceRef | None): 设备在 Emulator 2.0 里的归属；是官方模拟器实例时
                不走 Toolkit 发现（它认不出），直接构造设备

        Returns:
            AdbDevice: 表示 ADB 设备的对象

        Raises:
            RuntimeError: 如果无法找到指定设备，则抛出异常，异常信息包含相关的错误信息
        """

        if device_ref is not None and device_ref.emulator_type == "avd":
            return _avd_adb_device(raw_info, device_ref)

        def get_emulator_adb_port(address: str) -> int | None:
            offset = 0
            if address.startswith("127.0.0.1:"):
                raw_port = address.removeprefix("127.0.0.1:")
            elif address.startswith("emulator-"):
                raw_port = address.removeprefix("emulator-")
                offset = 1
            else:
                return None

            try:
                return int(raw_port) + offset
            except ValueError:
                return None

        devices = Toolkit.find_adb_devices()
        for device in devices:
            if device.address == raw_info.adb_address:
                return device

        target_port = get_emulator_adb_port(raw_info.adb_address)
        if target_port is not None:
            for device in devices:
                device_port = get_emulator_adb_port(device.address)
                if device_port is not None and target_port == device_port:
                    return device

        raise RuntimeError("无法找到指定设备")

    async def get_adb_tasker(
        self,
        device_info: DeviceInfo,
        screencap_methods: int = MaaAdbScreencapMethodEnum.Default,
        input_methods: int = MaaAdbInputMethodEnum.Default,
        config: dict[str, Any] = {},
    ) -> Tasker:
        """
        创建一个连接 ADB 的 MaaFW 任务管理器

        Args:
            device_info(DeviceInfo): 包含设备信息的对象
            screencap_methods(int): 屏幕捕获方法，默认为 MaaAdbScreencapMethodEnum.Default
            input_methods(int): 输入方法，默认为 MaaAdbInputMethodEnum.Default
            config(dict[str, Any]): 其他配置项，默认为空字典
        Returns:
            Tasker: 已连接的 MaaFW 任务管理器实例
        Raises:
            RuntimeError: 如果无法连接到指定设备或初始化 MaaFW 失败，则抛出异常，异常信息包含相关的错误信息
        """

        adb_device = await self.convert_adb(device_info)

        logger.info(
            f"正在连接设备: {device_info.title}, ADB 路径: {adb_device.adb_path}, 设备地址: {adb_device.address}, 屏幕捕获方法: {screencap_methods}, 输入方法: {input_methods}"
        )

        controller = AdbController(
            adb_device.adb_path,
            adb_device.address,
            screencap_methods,
            input_methods,
            config,
        )
        await self.do_job(controller.post_connection())

        tasker = Tasker()
        tasker.bind(self.resource, controller)
        if not tasker.inited:
            raise RuntimeError("无法初始化 MaaFW tasker")

        return tasker

    async def reconnect_win32_tasker(
        self,
        tasker: Tasker,
        hwnd: c_void_p | int | None,
        screencap_method: int = MaaWin32ScreencapMethodEnum.FramePool,
        mouse_method: int = MaaWin32InputMethodEnum.Seize,
        keyboard_method: int = MaaWin32InputMethodEnum.Seize,
    ) -> Tasker:
        """
        重新连接一个 Win32 的 MaaFW 任务管理器

        Args:
            tasker(Tasker): 需要重新连接的 MaaFW 任务管理器实例
            hwnd(c_void_p | int | None): 窗口句柄，可以是整数或 ctypes 的 c_void_p 类型，如果为 None 则 MaaFW 将尝试自动查找窗口
            screencap_method(int): 屏幕捕获方法，默认为 MaaWin32ScreencapMethodEnum.FramePool
            mouse_method(int): 鼠标输入方法，默认为 MaaWin32InputMethodEnum.Seize
            keyboard_method(int): 键盘输入方法，默认为 MaaWin32InputMethodEnum.Seize
        Returns:
            Tasker: 已连接的 MaaFW 任务管理器实例
        Raises:
            RuntimeError: 如果无法连接到指定窗口或初始化 MaaFW 失败，则抛出异常，异常信息包含相关的错误信息
        """

        logger.info(
            f"正在重新连接窗口: {hwnd}, 屏幕捕获方法: {screencap_method}, 鼠标输入方法: {mouse_method}, 键盘输入方法: {keyboard_method}"
        )

        controller = Win32Controller(
            hwnd, screencap_method, mouse_method, keyboard_method
        )
        await self.do_job(controller.post_connection())

        if tasker.inited:
            await self.do_job(tasker.post_stop())
        tasker.bind(self.resource, controller)
        if not tasker.inited:
            raise RuntimeError("无法初始化 MaaFW tasker")

        return tasker


def _avd_adb_device(raw_info: DeviceInfo, device_ref: DeviceRef) -> AdbDevice:
    """官方模拟器实例的 AdbDevice：SDK 的 adb、``127.0.0.1:<adb 端口>``、只用 AVDExtras 截图（64），
    输入 Default；config 带 AVDExtras 与推流开关改走私有 server 的覆盖（与 MaaFW 运行器同一份）。
    名字取 MaaToolkit 给这类模拟器的名字 ``AVD``。"""
    from app.utils.emulator2.avd.components import (
        adb_exe,
        adb_server_port,
        root_from_manager_exe,
    )
    from app.utils.emulator2.avd.constants import console_port
    from app.utils.emulator2.avd.maafw_extras import build_maafw_avd_config

    root = root_from_manager_exe(device_ref.manager_path)
    adb_path = adb_exe(root)
    if not adb_path.is_file():
        raise RuntimeError(f"找不到官方模拟器的 adb：{adb_path}")
    return AdbDevice(
        name="AVD",
        adb_path=adb_path,
        address=raw_info.adb_address,
        screencap_methods=int(MaaAdbScreencapMethodEnum.EmulatorExtras),
        input_methods=int(MaaAdbInputMethodEnum.Default),
        config=build_maafw_avd_config(
            adb_path, adb_server_port(root), console_port(device_ref.native_index)
        ),
    )


MaaFWManager = _MaaFWManager()


@MaaFWManager.resource.custom_action("DisableLog")
class DisableLog(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        """
        自定义动作: 临时禁用日志输出

        Args:
            context(Context): 任务上下文对象，可以用于执行其他操作
            argv(CustomAction.RunArg): 包含任务详情、节点名、自定义动作名、自定义动作参数、前序识别详情和前序识别位置的参数对象

        Returns:
            bool: 动作是否执行成功
        """
        # 临时关闭日志输出
        # Tasker.set_log_dir("")
        # Tasker.set_stdout_level(LoggingLevelEnum.Off)
        return True


@MaaFWManager.resource.custom_action("EnableLog")
class EnableLog(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        """
        自定义动作: 启用日志输出

        Args:
            context(Context): 任务上下文对象，可以用于执行其他操作
            argv(CustomAction.RunArg): 包含任务详情、节点名、自定义动作名、自定义动作参数、前序识别详情和前序识别位置的参数对象

        Returns:
            bool: 动作是否执行成功
        """
        # 恢复日志输出
        # Tasker.set_log_dir("./debug")
        # Tasker.set_stdout_level(LoggingLevelEnum.Error)
        return True
