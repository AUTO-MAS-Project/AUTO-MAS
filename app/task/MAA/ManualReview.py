#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import json
import uuid
import asyncio
import shutil
from pathlib import Path
from datetime import datetime

from app.core import Config, Broadcast
from app.models.task import TaskExecuteBase, ScriptItem, LogRecord
from app.models.ConfigBase import MultipleConfig
from app.models.config import MaaConfig, MaaUserConfig
from app.models.emulator import DeviceInfo, DeviceBase
from app.services import System
from app.utils import get_logger, LogMonitor, ProcessManager
from app.utils.constants import UTC4
from .tools import agree_bilibili

logger = get_logger("MAA 人工排查")


class ManualReviewTask(TaskExecuteBase):
    """人工排查模式"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: MaaConfig,
        user_config: MultipleConfig[MaaUserConfig],
        emulator_manager: DeviceBase,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.emulator_manager = emulator_manager
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config = self.user_config[self.cur_user_uid]
        self.check_result = "-"

    async def check(self) -> str:

        if (
            self.cur_user_config.get("Info", "Mode") == "详细"
            and not (
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile/gui.json"
            ).exists()
        ):
            self.cur_user_item.status = "异常"
            return "未找到用户的 MAA 配置文件"
        return "Pass"

    async def prepare(self):

        self.maa_process_manager = ProcessManager()
        self.maa_log_monitor = LogMonitor((1, 20), "%Y-%m-%d %H:%M:%S", self.check_log)
        self.message_queue = asyncio.Queue()
        await Broadcast.subscribe(self.message_queue)
        self.wait_event = asyncio.Event()
        self.maa_logs: list[str] = []
        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now()

        self.maa_root_path = Path(self.script_config.get("Info", "Path"))
        self.maa_set_path = self.maa_root_path / "config/gui.json"
        self.maa_log_path = self.maa_root_path / "debug/gui.log"
        self.maa_exe_path = self.maa_root_path / "MAA.exe"
        self.maa_tasks_path = self.maa_root_path / "resource/tasks/tasks.json"

        self.run_book = {"SignIn": False, "PassCheck": False}

    async def main_task(self):
        """人工排查模式主逻辑"""

        # 初始化每日代理状态
        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        if self.cur_user_config.get("Data", "LastProxyDate") != self.curdate:
            await self.cur_user_config.set("Data", "LastProxyDate", self.curdate)
            await self.cur_user_config.set("Data", "ProxyTimes", 0)

        self.check_result = await self.check()
        if self.check_result != "Pass":
            if self.cur_user_item.status == "异常":
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={
                        "Error": f"用户 {self.cur_user_item.name} 检查未通过: {self.check_result}"
                    },
                )
            return

        await self.prepare()

        logger.info(f"开始排查用户: {self.cur_user_uid}")
        self.cur_user_item.status = "运行"

        while True:

            try:
                self.script_info.log = "正在启动模拟器"
                emulator_info = await self.emulator_manager.open(
                    self.script_config.get("Emulator", "Index")
                )
            except Exception as e:

                logger.exception(
                    f"用户: {self.cur_user_item.user_id} - 模拟器启动失败: {e}"
                )
                self.script_info.log = f"模拟器启动失败: {e}\n正在中止相关程序"
                await self.emulator_manager.close(
                    self.script_config.get("Emulator", "Index")
                )

                uid = str(uuid.uuid4())
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Message",
                    data={
                        "message_id": uid,
                        "type": "Question",
                        "title": "操作提示",
                        "message": "模拟器启动失败, 是否重试？",
                        "options": ["是", "否"],
                    },
                )
                result = await self._wait_for_user_response(uid)
                if not result.get("data", {}).get("choice", False):
                    break
                continue

            await self.set_maa(emulator_info)

            logger.info(f"启动MAA进程: {self.maa_exe_path}")
            self.log_start_time = datetime.now()

            self.cur_user_item.log_record[self.log_start_time] = self.cur_user_log = (
                LogRecord()
            )
            self.wait_event.clear()
            await self.maa_process_manager.open_process(self.maa_exe_path)
            await asyncio.sleep(1)  # 等待 MAA 处理日志文件
            await self.maa_log_monitor.start_monitor_file(
                self.maa_log_path, self.log_start_time
            )
            await self.wait_event.wait()
            await self.maa_log_monitor.stop()

            if self.cur_user_log.status == "Success!":
                self.run_book["SignIn"] = True
                break
            else:

                logger.error(
                    f"用户: {self.cur_user_item.user_id} - MAA进程异常: {self.cur_user_log.status}"
                )
                self.script_info.log = f"{self.cur_user_log.status}\n正在中止相关程序"

                await self.maa_process_manager.kill()
                await self.emulator_manager.close(
                    self.script_config.get("Emulator", "Index")
                )
                await System.kill_process(self.maa_exe_path)

                uid = str(uuid.uuid4())
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Message",
                    data={
                        "message_id": uid,
                        "type": "Question",
                        "title": "操作提示",
                        "message": "MAA未能正确登录到PRTS, 是否重试？",
                        "options": ["是", "否"],
                    },
                )
                result = await self._wait_for_user_response(uid)
                if not result.get("data", {}).get("choice", False):
                    break

        if self.run_book["SignIn"]:

            await self.emulator_manager.setVisible(
                self.script_config.get("Emulator", "Index"), True
            )
            uid = str(uuid.uuid4())
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Message",
                data={
                    "message_id": uid,
                    "type": "Question",
                    "title": "操作提示",
                    "message": "请检查用户代理情况, 该用户是否正确完成代理任务？",
                    "options": ["是", "否"],
                },
            )
            result = await self._wait_for_user_response(uid)
            if result.get("data", {}).get("choice", False):
                self.run_book["PassCheck"] = True

    async def _wait_for_user_response(self, message_id: str):
        """等待用户交互响应"""
        logger.info(f"等待客户端回应消息: {message_id}")
        while True:
            message = await self.message_queue.get()
            if message.get("id") == message_id and message.get("type") == "Response":
                self.message_queue.task_done()
                logger.success(f"收到客户端回应消息: {message_id}")
                return message
            else:
                self.message_queue.task_done()

    async def set_maa(self, emulator_info: DeviceInfo):
        """配置MAA运行参数"""
        logger.info(f"开始配置MAA运行参数: 人工排查")

        await self.maa_process_manager.kill()
        await System.kill_process(self.maa_exe_path)

        if self.cur_user_config.get("Info", "Server") == "Bilibili":
            await agree_bilibili(self.maa_tasks_path, True)
        else:
            await agree_bilibili(self.maa_tasks_path, False)

        if self.cur_user_config.get("Info", "Mode") == "简洁":
            shutil.copy(
                (
                    Path.cwd()
                    / f"data/{self.script_info.script_id}/Default/ConfigFile/gui.json"
                ),
                self.maa_set_path,
            )
        elif self.cur_user_config.get("Info", "Mode") == "详细":
            shutil.copy(
                (
                    Path.cwd()
                    / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile/gui.json"
                ),
                self.maa_set_path,
            )

        maa_set = json.loads(self.maa_set_path.read_text(encoding="utf-8"))

        if maa_set["Current"] != "Default":
            maa_set["Configurations"]["Default"] = maa_set["Configurations"][
                maa_set["Current"]
            ]
            maa_set["Current"] = "Default"
        for i in range(1, 9):
            maa_set["Global"][f"Timer.Timer{i}"] = "False"

        if emulator_info.adb_address != "Unknown":
            maa_set["Configurations"]["Default"][
                "Connect.Address"
            ] = emulator_info.adb_address
        maa_set["Configurations"]["Default"]["MainFunction.PostActions"] = "8"
        maa_set["Configurations"]["Default"]["Start.RunDirectly"] = "True"
        maa_set["Global"]["Start.MinimizeDirectly"] = "True"
        maa_set["Global"]["GUI.UseTray"] = "True"
        maa_set["Global"]["GUI.MinimizeToTray"] = "True"
        maa_set["Configurations"]["Default"]["Start.OpenEmulatorAfterLaunch"] = "False"
        maa_set["Global"]["VersionUpdate.ScheduledUpdateCheck"] = "False"
        maa_set["Global"]["VersionUpdate.AutoDownloadUpdatePackage"] = "False"
        maa_set["Global"]["VersionUpdate.AutoInstallUpdatePackage"] = "False"
        maa_set["Configurations"]["Default"]["Start.ClientType"] = (
            self.cur_user_config.get("Info", "Server")
        )
        if self.cur_user_config.get("Info", "Server") == "Official":
            maa_set["Configurations"]["Default"]["Start.AccountName"] = (
                f"{self.cur_user_config.get('Info', 'Id')[:3]}****{self.cur_user_config.get('Info', 'Id')[7:]}"
                if len(self.cur_user_config.get("Info", "Id")) == 11
                else self.cur_user_config.get("Info", "Id")
            )
        elif self.cur_user_config.get("Info", "Server") == "Bilibili":
            maa_set["Configurations"]["Default"]["Start.AccountName"] = (
                self.cur_user_config.get("Info", "Id")
            )
        maa_set["Configurations"]["Default"]["TaskQueue.WakeUp.IsChecked"] = "True"
        maa_set["Configurations"]["Default"]["TaskQueue.Recruiting.IsChecked"] = "False"
        maa_set["Configurations"]["Default"]["TaskQueue.Base.IsChecked"] = "False"
        maa_set["Configurations"]["Default"]["TaskQueue.Combat.IsChecked"] = "False"
        maa_set["Configurations"]["Default"]["TaskQueue.Mission.IsChecked"] = "False"
        maa_set["Configurations"]["Default"]["TaskQueue.Mall.IsChecked"] = "False"
        maa_set["Configurations"]["Default"][
            "TaskQueue.AutoRoguelike.IsChecked"
        ] = "False"
        maa_set["Configurations"]["Default"][
            "TaskQueue.Reclamation.IsChecked"
        ] = "False"

        self.maa_set_path.write_text(
            json.dumps(maa_set, ensure_ascii=False, indent=4), encoding="utf-8"
        )
        logger.success(f"MAA运行参数配置完成: 人工排查")

    async def check_log(self, log_content: list[str]) -> None:
        """日志回调"""

        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log

        if "完成任务: StartUp" in log or "完成任务: 开始唤醒" in log:
            self.cur_user_log.status = "Success!"
        elif "请 ｢检查连接设置｣ → ｢尝试重启模拟器与 ADB｣ → ｢重启电脑｣" in log:
            self.cur_user_log.status = "MAA 的 ADB 连接异常"
        elif "未检测到任何模拟器" in log:
            self.cur_user_log.status = "MAA 未检测到任何模拟器"
        elif "已停止" in log:
            self.cur_user_log.status = "MAA 在完成任务前中止"
        elif (
            "MaaAssistantArknights GUI exited" in log
            or not await self.maa_process_manager.is_running()
        ):
            self.cur_user_log.status = "MAA 在完成任务前退出"
        else:
            self.cur_user_log.status = "MAA 正常运行中"

        logger.debug(f"MAA 日志分析结果: {self.cur_user_log.status}")
        if self.cur_user_log.status != "MAA 正常运行中":
            logger.info(f"MAA 任务结果: {self.cur_user_log.status}, 日志锁已释放")
            self.wait_event.set()

    async def final_task(self):

        if self.check_result != "Pass":
            return

        await self.maa_log_monitor.stop()
        await self.maa_process_manager.kill()
        await System.kill_process(self.maa_exe_path)
        await agree_bilibili(self.maa_tasks_path, False)

        if self.run_book["SignIn"] and self.run_book["PassCheck"]:
            logger.info(f"用户 {self.cur_user_uid} 通过人工排查")
            await self.cur_user_config.set("Data", "IfPassCheck", True)
            self.cur_user_item.status = "完成"
        else:
            logger.info(f"用户 {self.cur_user_uid} 未通过人工排查")
            await self.cur_user_config.set("Data", "IfPassCheck", False)
            self.cur_user_item.status = "异常"

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.exception(f"人工排查任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"人工排查任务出现异常: {e}"},
        )
