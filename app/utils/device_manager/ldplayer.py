import asyncio
from typing import Literal
from app.utils.device_manager.utils import BaseDevice, ExeRunner, DeviceStatus
from app.utils.logger import get_logger
from app.utils.device_manager.keyboard_utils import (
    vk_codes_to_key_names,
    send_key_combination,
)
import psutil
from pydantic import BaseModel
import win32gui


class EmulatorInfo(BaseModel):
    idx: int
    title: str
    top_hwnd: int
    bind_hwnd: int
    in_android: int
    pid: int
    vbox_pid: int
    width: int
    height: int
    density: int


class LDManager(BaseDevice):
    """
    基于dnconsole.exe的模拟器管理

    !需要管理员权限

    """

    def __init__(self, exe_path: str) -> None:
        """_summary_

        Args:
            exe_path (str): dnconsole.exe的绝对路径
        """
        self.runner = ExeRunner(exe_path, "gbk")
        self.logger = get_logger("雷电模拟器管理器")
        self.wait_time = 60  # 配置获取 后续改一下 单位为s

    async def start(self, idx: str, package_name="") -> tuple[bool, int, dict]:
        """
        启动指定模拟器
        Returns:
            tuple[bool, int, str]: 是否成功, 当前状态码, ADB端口信息
        """
        OK, info, status = await self.get_device_info(idx)
        if status != DeviceStatus.OFFLINE:
            self.logger.error(
                f"模拟器{idx}未处于关闭状态，当前状态码: {status}, 需求状态码: {DeviceStatus.OFFLINE}"
            )
            return False, status, {}
        if package_name:
            result = self.runner.run(
                "launch",
                "--index",
                idx,
                "--packagename",
                f'"{package_name}"',
            )
        else:
            result = self.runner.run(
                "launch",
                "--index",
                idx,
            )
        # 参考命令 dnconsole.exe launch --index 0
        self.logger.debug(f"启动结果:{result}")
        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {result}")

        i = 0
        while i < self.wait_time * 10:
            OK, info, status = await self.get_device_info(idx)
            if status == DeviceStatus.ERROR or status == DeviceStatus.UNKNOWN:
                self.logger.error(f"模拟器{idx}启动失败，状态码: {status}")
                return False, status, {}
            if status == DeviceStatus.ONLINE:
                self.logger.debug(info)
                if OK and isinstance(info, EmulatorInfo):
                    pid: int = info.vbox_pid
                    adb_port = ""
                    adb_host_ip = await self.get_adb_ports(pid)
                    print(adb_host_ip)
                    if adb_host_ip:
                        return (
                            True,
                            status,
                            {"adb_port": adb_port, "adb_host_ip": adb_host_ip},
                        )

                return True, status, {}
            await asyncio.sleep(0.1)
            i += 1
        return False, DeviceStatus.UNKNOWN, {}

    async def close(self, idx: str) -> tuple[bool, int]:
        """
        关闭指定模拟器
        Returns:
            - tuple[bool, int]: 是否成功, 当前状态码

        参考命令行:dnconsole.exe quit --index 0
        """
        OK, info, status = await self.get_device_info(idx)
        if status != DeviceStatus.ONLINE and status != DeviceStatus.STARTING:
            return False, DeviceStatus.NOT_FOUND
        result = self.runner.run(
            "quit",
            "--index",
            idx,
        )
        # 参考命令 dnconsole.exe quit --index 0
        if result.returncode != 0:
            return True, DeviceStatus.OFFLINE
        i = 0
        while i < self.wait_time * 10:
            OK, info, status = await self.get_device_info(idx)
            if status == DeviceStatus.ERROR or status == DeviceStatus.UNKNOWN:
                return False, status
            if status == DeviceStatus.OFFLINE:
                return True, DeviceStatus.OFFLINE
            await asyncio.sleep(0.1)
            i += 1

        return False, DeviceStatus.UNKNOWN

    async def get_status(self, idx: str) -> int:
        """
        获取指定模拟器当前状态
        返回值: 状态码
        """
        _, _, status = await self.get_device_info(idx)
        return status

    async def get_device_info(
        self,
        idx: str,
        data: dict[int, EmulatorInfo] | None = None,
    ) -> tuple[Literal[True], EmulatorInfo, int] | tuple[Literal[False], dict, int]:
        """
        获取指定模拟器的信息和状态
        Returns:
            - tuple[bool, EmulatorInfo | dict, int]: 是否成功, 模拟器信息或空字典, 状态码

        参考命令行:dnconsole.exe list2
        """
        if not data:
            result = await self._get_all_info()
        else:
            result = data

        try:
            emulator_info = result.get(int(idx))
            print(emulator_info)
            if not emulator_info:
                self.logger.error(f"未找到模拟器{idx}的信息")
                return False, {}, DeviceStatus.UNKNOWN

            self.logger.debug(f"获取模拟器{idx}信息: {emulator_info}")

            # 计算状态码
            if emulator_info.in_android == 1:
                status = DeviceStatus.ONLINE
            elif emulator_info.in_android == 2:
                if emulator_info.vbox_pid > 0:
                    status = DeviceStatus.STARTING
                    # 雷电启动后, vbox_pid为-1, 目前不知道有什么区别
                else:
                    status = DeviceStatus.STARTING
            elif emulator_info.in_android == 0:
                status = DeviceStatus.OFFLINE
            else:
                status = DeviceStatus.UNKNOWN

            self.logger.debug(f"获取模拟器{idx}状态: {status}")
            return True, emulator_info, status
        except:  # noqa: E722
            self.logger.error(f"获取模拟器{idx}信息失败")
            return False, {}, DeviceStatus.UNKNOWN

    async def _get_all_info(self) -> dict[int, EmulatorInfo]:
        result = self.runner.run("list2")
        # self.logger.debug(f"全部信息{result.stdout.strip()}")
        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {result}")

        emulators: dict[int, EmulatorInfo] = {}
        data = result.stdout.strip()

        for line in data.strip().splitlines():
            parts = line.strip().split(",")
            if len(parts) != 10:
                raise ValueError(f"数据格式错误: {line}")
            try:
                info = EmulatorInfo(
                    idx=int(parts[0]),
                    title=parts[1],
                    top_hwnd=int(parts[2]),
                    bind_hwnd=int(parts[3]),
                    in_android=int(parts[4]),
                    pid=int(parts[5]),
                    vbox_pid=int(parts[6]),
                    width=int(parts[7]),
                    height=int(parts[8]),
                    density=int(parts[9]),
                )
                emulators[info.idx] = info
            except Exception as e:
                self.logger.warning(f"解析失败: {line}, 错误: {e}")
                pass
        return emulators

    # ?wk雷电你都返回了什么啊

    async def get_all_info(self) -> dict[str, dict[str, str]]:
        """
        解析_emulator_info字典，提取idx和title，便于前端显示
        """
        raw_data = await self._get_all_info()
        result: dict[str, dict[str, str]] = {}
        for info in raw_data.values():
            OK, device_info, status = await self.get_device_info(
                str(info.idx), raw_data
            )
            result[str(info.idx)] = {"title": info.title, "status": str(status)}
        return result

    async def send_boss_key(
        self,
        boss_keys: list[int],
        result: EmulatorInfo,
        is_show: bool = False,
        # True: 显示, False: 隐藏
    ) -> bool:
        """
        发送BOSS键

        Args:
            idx (str): 模拟器索引
            boss_keys (list[int]): BOSS键的虚拟键码列表
            result (EmulatorInfo): 模拟器信息
            is_show (bool, optional): 将要隐藏或显示窗口，默认为 False（隐藏）。
        """
        hwnd = result.top_hwnd
        try:
            # 使用键盘工具发送按键组合
            success = await send_key_combination(vk_codes_to_key_names(boss_keys))
            if not success:
                return False

            # 等待系统处理
            await asyncio.sleep(0.5)

            # 检查窗口可见性是否符合预期
            current_visible = win32gui.IsWindowVisible(hwnd)
            expected_visible = is_show

            if current_visible == expected_visible:
                return True
            else:
                # 如果第一次没有成功，再试一次
                success = await send_key_combination(vk_codes_to_key_names(boss_keys))
                if not success:
                    return False

                await asyncio.sleep(0.5)
                current_visible = win32gui.IsWindowVisible(hwnd)
                return current_visible == expected_visible

        except Exception as e:
            self.logger.error(f"发送BOSS键失败: {e}")
            return False

    async def hide_device(
        self,
        idx: str,
        boss_keys: list[int] = [],
    ) -> tuple[bool, int]:
        """隐藏设备窗口"""
        OK, result, status = await self.get_device_info(idx)
        if not OK or not isinstance(result, EmulatorInfo):
            return False, DeviceStatus.UNKNOWN
        if status != DeviceStatus.ONLINE:
            return False, status

        return await self.send_boss_key(boss_keys, result, False), status

    async def show_device(
        self,
        idx: str,
        boss_keys: list[int] = [],
    ) -> tuple[bool, int]:
        """显示设备窗口"""
        OK, result, status = await self.get_device_info(idx)
        if not OK or not isinstance(result, EmulatorInfo):
            return False, DeviceStatus.UNKNOWN
        if status != DeviceStatus.ONLINE:
            return False, status

        return await self.send_boss_key(boss_keys, result, True), status

    async def get_adb_ports(self, pid: int) -> int:
        """使用psutil获取adb端口"""
        try:
            process = psutil.Process(pid)
            connections = process.connections(kind="inet")
            for conn in connections:
                if conn.status == psutil.CONN_LISTEN and conn.laddr.port != 2222:
                    return conn.laddr.port
            return 0  # 如果没有找到合适的端口，返回0
        except:  # noqa: E722
            return 0


if __name__ == "__main__":
    MANAGER_PATH = (
        r"C:\leidian\LDPlayer9\dnconsole.exe"  # 替换为实际的dnconsole.exe路径
    )
    idx = "0"  # 替换为实际存在的模拟器实例索

    manager = LDManager(MANAGER_PATH)
    # asyncio.run(manager._get_all_info())
    a = asyncio.run(manager.start("0"))
    print(a)
