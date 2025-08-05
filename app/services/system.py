#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361

#   This file is part of AUTO_MAA.

#   AUTO_MAA is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO_MAA is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO_MAA. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""
AUTO_MAA
AUTO_MAA系统服务
v4.4
作者：DLmaster_361
"""

from PySide6.QtWidgets import QApplication
import sys
import ctypes
import win32gui
import win32process
import psutil
import subprocess
import tempfile
import getpass
from datetime import datetime
from pathlib import Path

from app.core import Config


class _SystemHandler:

    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001

    def __init__(self):

        self.set_Sleep()
        self.set_SelfStart()

    def set_Sleep(self) -> None:
        """同步系统休眠状态"""

        if Config.get(Config.function_IfAllowSleep):
            # 设置系统电源状态
            ctypes.windll.kernel32.SetThreadExecutionState(
                self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED
            )
        else:
            # 恢复系统电源状态
            ctypes.windll.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS)

    def set_SelfStart(self) -> None:
        """同步开机自启"""

        if Config.get(Config.start_IfSelfStart) and not self.is_startup():

            # 创建任务计划
            try:

                # 获取当前用户和时间
                current_user = getpass.getuser()
                current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

                # XML 模板
                xml_content = f"""<?xml version="1.0" encoding="UTF-16"?>
                <Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
                    <RegistrationInfo>
                        <Date>{current_time}</Date>
                        <Author>{current_user}</Author>
                        <Description>AUTO_MAA自启动服务</Description>
                        <URI>\\AUTO_MAA_AutoStart</URI>
                    </RegistrationInfo>
                    <Triggers>
                        <LogonTrigger>
                            <StartBoundary>{current_time}</StartBoundary>
                            <Enabled>true</Enabled>
                        </LogonTrigger>
                    </Triggers>
                    <Principals>
                        <Principal id="Author">
                            <LogonType>InteractiveToken</LogonType>
                            <RunLevel>HighestAvailable</RunLevel>
                        </Principal>
                    </Principals>
                    <Settings>
                        <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
                        <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
                        <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
                        <AllowHardTerminate>false</AllowHardTerminate>
                        <StartWhenAvailable>true</StartWhenAvailable>
                        <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
                        <IdleSettings>
                            <StopOnIdleEnd>false</StopOnIdleEnd>
                            <RestartOnIdle>false</RestartOnIdle>
                        </IdleSettings>
                        <AllowStartOnDemand>true</AllowStartOnDemand>
                        <Enabled>true</Enabled>
                        <Hidden>false</Hidden>
                        <RunOnlyIfIdle>false</RunOnlyIfIdle>
                        <WakeToRun>false</WakeToRun>
                        <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
                        <Priority>7</Priority>
                    </Settings>
                    <Actions Context="Author">
                        <Exec>
                            <Command>"{Config.app_path_sys}"</Command>
                        </Exec>
                    </Actions>
                </Task>"""

                # 创建临时 XML 文件并执行
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".xml", delete=False, encoding="utf-16"
                ) as f:
                    f.write(xml_content)
                    xml_file = f.name

                try:
                    result = subprocess.run(
                        [
                            "schtasks",
                            "/create",
                            "/tn",
                            "AUTO_MAA_AutoStart",
                            "/xml",
                            xml_file,
                            "/f",
                        ],
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        text=True,
                    )

                    if result.returncode == 0:
                        logger.success(
                            f"程序自启动任务计划已创建: {Config.app_path_sys}",
                            module="系统服务",
                        )
                    else:
                        logger.error(
                            f"程序自启动任务计划创建失败: {result.stderr}",
                            module="系统服务",
                        )

                finally:
                    # 删除临时文件
                    try:
                        Path(xml_file).unlink()
                    except:
                        pass

            except Exception as e:
                logger.exception(f"程序自启动任务计划创建失败: {e}", module="系统服务")

        elif not Config.get(Config.start_IfSelfStart) and self.is_startup():

            try:

                result = subprocess.run(
                    ["schtasks", "/delete", "/tn", "AUTO_MAA_AutoStart", "/f"],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0:
                    logger.success("程序自启动任务计划已删除", module="系统服务")
                else:
                    logger.error(
                        f"程序自启动任务计划删除失败: {result.stderr}",
                        module="系统服务",
                    )

            except Exception as e:
                logger.exception(f"程序自启动任务计划删除失败: {e}", module="系统服务")

    def set_power(self, mode) -> None:
        """
        执行系统电源操作

        :param mode: 电源操作模式，支持 "NoAction", "Shutdown", "Hibernate", "Sleep", "KillSelf", "ShutdownForce"
        """

        if sys.platform.startswith("win"):

            if mode == "NoAction":

                logger.info("不执行系统电源操作", module="系统服务")

            elif mode == "Shutdown":

                self.kill_emulator_processes()
                logger.info("执行关机操作", module="系统服务")
                subprocess.run(["shutdown", "/s", "/t", "0"])

            elif mode == "ShutdownForce":
                logger.info("执行强制关机操作", module="系统服务")
                subprocess.run(["shutdown", "/s", "/t", "0", "/f"])

            elif mode == "Hibernate":

                logger.info("执行休眠操作", module="系统服务")
                subprocess.run(["shutdown", "/h"])

            elif mode == "Sleep":

                logger.info("执行睡眠操作", module="系统服务")
                subprocess.run(
                    ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]
                )

            elif mode == "KillSelf":

                logger.info("执行退出主程序操作", module="系统服务")
                Config.main_window.close()
                QApplication.quit()
                sys.exit(0)

        elif sys.platform.startswith("linux"):

            if mode == "NoAction":

                logger.info("不执行系统电源操作", module="系统服务")

            elif mode == "Shutdown":

                logger.info("执行关机操作", module="系统服务")
                subprocess.run(["shutdown", "-h", "now"])

            elif mode == "Hibernate":

                logger.info("执行休眠操作", module="系统服务")
                subprocess.run(["systemctl", "hibernate"])

            elif mode == "Sleep":

                logger.info("执行睡眠操作", module="系统服务")
                subprocess.run(["systemctl", "suspend"])

            elif mode == "KillSelf":

                logger.info("执行退出主程序操作", module="系统服务")
                Config.main_window.close()
                QApplication.quit()
                sys.exit(0)

    def kill_emulator_processes(self):
        """这里暂时仅支持 MuMu 模拟器"""

        logger.info("正在清除模拟器进程", module="系统服务")

        keywords = ["Nemu", "nemu", "emulator", "MuMu"]
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                pname = proc.info["name"].lower()
                if any(keyword.lower() in pname for keyword in keywords):
                    proc.kill()
                    logger.info(
                        f"已关闭 MuMu 模拟器进程: {proc.info['name']}",
                        module="系统服务",
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        logger.success("模拟器进程清除完成", module="系统服务")

    def is_startup(self) -> bool:
        """判断程序是否已经开机自启"""

        try:
            result = subprocess.run(
                ["schtasks", "/query", "/tn", "AUTO_MAA_AutoStart"],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except Exception as e:
            logger.exception(f"检查任务计划程序失败: {e}", module="系统服务")
            return False

    def get_window_info(self) -> list:
        """获取当前前台窗口信息"""

        def callback(hwnd, window_info):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                process = psutil.Process(pid)
                window_info.append((win32gui.GetWindowText(hwnd), process.exe()))
            return True

        window_info = []
        win32gui.EnumWindows(callback, window_info)
        return window_info

    def kill_process(self, path: Path) -> None:
        """
        根据路径中止进程

        :param path: 进程路径
        """

        logger.info(f"开始中止进程: {path}", module="系统服务")

        for pid in self.search_pids(path):
            killprocess = subprocess.Popen(
                f"taskkill /F /T /PID {pid}",
                shell=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            killprocess.wait()

        logger.success(f"进程已中止: {path}", module="系统服务")

    def search_pids(self, path: Path) -> list:
        """
        根据路径查找进程PID

        :param path: 进程路径
        :return: 匹配的进程PID列表
        """

        logger.info(f"开始查找进程 PID: {path}", module="系统服务")

        pids = []
        for proc in psutil.process_iter(["pid", "exe"]):
            try:
                if proc.info["exe"] and proc.info["exe"].lower() == str(path).lower():
                    pids.append(proc.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                # 进程可能在此期间已结束或无法访问，忽略这些异常
                pass
        return pids


System = _SystemHandler()
