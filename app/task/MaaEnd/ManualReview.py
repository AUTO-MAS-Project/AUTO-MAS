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


import asyncio
import json
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from app.core import Broadcast, Config
from app.models.task import TaskExecuteBase, ScriptItem
from app.models.ConfigBase import MultipleConfig
from app.models.config import MaaEndConfig, MaaEndUserConfig
from app.models.emulator import DeviceBase
from app.services import System
from app.utils import decode_bytes, get_logger, ProcessManager, is_process_running
from app.utils.constants import UTC4
from app.utils.io import read_file, write_file
from .ScriptConfig import normalize_maaend_config
from .resource_loader import load_maaend_task_i18n
from .tools import login, replace_account_switch_task

logger = get_logger("MaaEnd 人工检查")


class ManualReviewTask(TaskExecuteBase):
    """MaaEnd 人工检查模式"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: MaaEndConfig,
        user_config: MultipleConfig[MaaEndUserConfig],
        emulator_manager: DeviceBase | None,
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
        config_user_id = (
            "Default"
            if self.cur_user_config.get("Info", "Mode") == "简洁"
            else self.cur_user_uid
        )
        self.maaend_config_path = (
            Path.cwd()
            / f"data/{self.script_info.script_id}/{config_user_id}/ConfigFile"
        )
        self.check_result = "-"

    async def check(self) -> str:

        if self.emulator_manager is not None:
            return "暂不支持使用模拟器进行人工排查"

        account_id = str(self.cur_user_config.get("Info", "Id")).strip()
        if (
            self.script_config.get("Run", "AccountSwitchMethod") == "MAAEND"
            and account_id
        ):
            if len(account_id) < 4 or not account_id[-4:].isdigit():
                self.cur_user_item.status = "异常"
                return "MAAEND 内置账号切换需要账号末四位为数字"
            if not (self.maaend_config_path / "mxu-MaaEnd.json").exists():
                self.cur_user_item.status = "异常"
                return "未找到 MaaEnd 配置文件, 请先完成「MaaEnd 配置」步骤"

        return "Pass"

    async def prepare(self):

        if self.emulator_manager is None:
            self.game_process_manager = ProcessManager()
        self.maaend_process_manager = ProcessManager()
        self.maaend_root_path = Path(self.script_config.get("Info", "Path"))
        self.maaend_exe_path = self.maaend_root_path / "MaaEnd.exe"
        self.maaend_set_path = self.maaend_root_path / "config"
        self.message_queue = asyncio.Queue()
        await Broadcast.subscribe(self.message_queue)

        self.run_book = {"SignIn": False, "PassCheck": False}

    async def main_task(self):
        """人工排查模式主逻辑"""

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

        logger.info(f"开始排查用户 {self.cur_user_uid}")
        self.cur_user_item.status = "运行"

        while True:

            try:
                self.script_info.log = "正在启动游戏..."
                if self.emulator_manager is None:
                    if is_process_running("Endfield.exe"):
                        logger.info(
                            "检测到终末地客户端进程已在运行，跳过由 MAS 重复启动游戏"
                        )
                        self.script_info.log = "检测到游戏已在运行，跳过启动游戏"
                    else:
                        logger.info(
                            f"启动终末地: {self.script_config.get('Game', 'Path')} - {self.script_config.get('Game', 'Arguments')}"
                        )
                        await self.game_process_manager.open_process(
                            self.script_config.get("Game", "Path"),
                            *str(self.script_config.get("Game", "Arguments")).split(
                                " "
                            ),
                        )
                        await asyncio.sleep(
                            self.script_config.get("Game", "WaitTime")
                        )
                    emulator_info = None
                else:
                    logger.info(
                        f"启动模拟器: {self.script_config.get('Game', 'EmulatorIndex')}"
                    )
                    emulator_info = await self.emulator_manager.open(
                        self.script_config.get("Game", "EmulatorIndex"),
                        "com.hypergryph.endfield",
                    )
            except Exception as e:

                logger.opt(exception=True).warning(f"用户 {self.cur_user_item.user_id} 游戏启动失败: {e}")
                self.script_info.log = (
                    f"正在启动模拟器\n模拟器启动失败: {e}\n正在中止相关程序"
                )
                await self.kill_managed_process()

                uid = str(uuid.uuid4())
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Message",
                    data={
                        "message_id": uid,
                        "type": "Question",
                        "title": "操作提示",
                        "message": "终末地启动或登录失败, 是否重试？",
                        "options": ["是", "否"],
                    },
                )
                result = await self._wait_for_user_response(uid)
                if not result.get("data", {}).get("choice", False):
                    break
                continue

            account_id = str(self.cur_user_config.get("Info", "Id")).strip()
            account_switch_method = self.script_config.get("Run", "AccountSwitchMethod")
            self.script_info.log = "正在启动游戏...\n游戏启动成功"
            try:
                if account_id and account_switch_method == "MAS":
                    self.script_info.log += "\n正在由 MAS 切换账号..."
                    await login(account_id, emulator_info)
                elif account_id:
                    self.script_info.log += "\n正在由 MAAEND 切换账号..."
                    await self._run_maaend_account_switch(account_id)
                else:
                    logger.info(
                        f"用户 {self.cur_user_item.user_id} 未配置账号，跳过账号切换"
                    )
                self.script_info.log += "\n账号切换完成"
                self.run_book["SignIn"] = True
                break
            except Exception as e:
                logger.warning(
                    f"用户: {self.cur_user_item.user_id} - 「明日方舟：终末地」登录失败: {e}"
                )
                self.script_info.log = "正在启动模拟器\n模拟器已启动，正在登录「明日方舟：终末地」...\n「明日方舟：终末地」登录失败\n正在中止相关程序"

                await self.kill_managed_process()

                uid = str(uuid.uuid4())
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Message",
                    data={
                        "message_id": uid,
                        "type": "Question",
                        "title": "操作提示",
                        "message": "未能正确登录到「明日方舟：终末地」, 是否重试？",
                        "options": ["是", "否"],
                    },
                )
                result = await self._wait_for_user_response(uid)
                if not result.get("data", {}).get("choice", False):
                    break

        if self.run_book["SignIn"]:

            try:
                if self.emulator_manager is not None:
                    await self.emulator_manager.setVisible(
                        self.script_config.get("Game", "EmulatorIndex"), True
                    )
            except Exception as e:
                logger.opt(exception=True).warning(f"模拟器显示失败: {e}")
            uid = str(uuid.uuid4())
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Message",
                data={
                    "message_id": uid,
                    "type": "Question",
                    "title": "操作提示",
                    "message": f"请检查用户代理情况, 「{self.cur_user_item.name}」是否正确完成代理任务？",
                    "options": ["是", "否"],
                },
            )
            result = await self._wait_for_user_response(uid)
            if result.get("data", {}).get("choice", False):
                self.run_book["PassCheck"] = True

    async def _run_maaend_account_switch(self, account_id: str) -> None:
        """临时运行一个 MaaEnd 账号切换任务。"""

        await self.maaend_process_manager.kill()
        await System.kill_process(self.maaend_exe_path)

        with tempfile.TemporaryDirectory(prefix="auto-mas-maaend-login-") as temp_dir:
            backup_config_path = Path(temp_dir) / "config"
            had_local_config = self.maaend_set_path.exists()
            if had_local_config:
                shutil.copytree(self.maaend_set_path, backup_config_path)

            try:
                shutil.rmtree(self.maaend_set_path, ignore_errors=True)
                shutil.copytree(self.maaend_config_path, self.maaend_set_path)
                config_path = self.maaend_set_path / "mxu-MaaEnd.json"
                maaend_set = read_file(config_path)

                local_config = None
                backup_file = backup_config_path / "mxu-MaaEnd.json"
                if backup_file.exists():
                    local_config = read_file(backup_file)
                for field in ("version", "interfaceTaskSnapshot"):
                    maaend_set.pop(field, None)
                    if local_config is not None and field in local_config:
                        maaend_set[field] = local_config[field]

                settings = maaend_set.get("settings")
                if isinstance(settings, dict):
                    settings.pop("welcomeShownHash", None)
                if local_config is not None:
                    local_settings = local_config.get("settings")
                    if (
                        isinstance(local_settings, dict)
                        and "welcomeShownHash" in local_settings
                    ):
                        maaend_set.setdefault("settings", {})["welcomeShownHash"] = (
                            local_settings["welcomeShownHash"]
                        )

                maaend_set = normalize_maaend_config(
                    maaend_set=maaend_set,
                    controller_type=str(
                        self.script_config.get("Game", "ControllerType")
                    ),
                    fallback_set=local_config,
                )
                settings = maaend_set["settings"]
                task_i18n = await asyncio.to_thread(
                    load_maaend_task_i18n,
                    self.maaend_root_path,
                    str(settings["language"]),
                )
                account_switch_task_name = task_i18n["AccountSwitch"]
                maaend_instance = maaend_set["instances"][0]
                maaend_instance["tasks"] = []
                replace_account_switch_task(
                    tasks=maaend_instance["tasks"],
                    account_id=account_id,
                    controller_type=str(
                        self.script_config.get("Game", "ControllerType")
                    ),
                    task_id=f"mas{self.cur_user_uid.hex[:4]}",
                )
                instance_name = str(maaend_instance.get("name") or "AUTO-MAS")
                write_file(config_path, maaend_set)

                await self.maaend_process_manager.open_process(
                    self.maaend_exe_path,
                    "--autostart",
                    "--instance",
                    instance_name,
                    "--quit-after-run",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                process = self.maaend_process_manager.main_process
                if not isinstance(process, asyncio.subprocess.Process):
                    raise RuntimeError("未能启动 MAAEND 账号切换进程")

                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(),
                        timeout=self.script_config.get("Run", "RunTimeLimit") * 60,
                    )
                except asyncio.TimeoutError as e:
                    raise RuntimeError("MAAEND 账号切换超时") from e

                log = "\n".join(
                    content
                    for content in (decode_bytes(stdout), decode_bytes(stderr))
                    if content
                )
                self.script_info.log = log
                if f"任务失败: {account_switch_task_name}" in log:
                    raise RuntimeError("MAAEND 账号切换失败")
                if f"任务完成: {account_switch_task_name}" not in log:
                    raise RuntimeError("MAAEND 账号切换进程异常退出")
            finally:
                await self.maaend_process_manager.kill()
                await System.kill_process(self.maaend_exe_path)
                shutil.rmtree(self.maaend_set_path, ignore_errors=True)
                if had_local_config:
                    shutil.copytree(backup_config_path, self.maaend_set_path)

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

    async def kill_managed_process(self) -> None:
        """中止关联进程"""

        try:
            await self.maaend_process_manager.kill()
            await System.kill_process(self.maaend_exe_path)
        except Exception as e:
            logger.opt(exception=True).warning(f"关闭 MaaEnd 失败: {e}")
        try:
            if self.emulator_manager is None:
                await self.game_process_manager.kill()
                await System.kill_process(self.script_config.get("Game", "Path"))
            else:
                await self.emulator_manager.close(
                    self.script_config.get("Game", "EmulatorIndex")
                )
        except Exception as e:
            logger.opt(exception=True).warning(f"关闭游戏失败: {e}")

    async def final_task(self):

        if self.check_result != "Pass":
            return

        await self.kill_managed_process()

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
        logger.opt(exception=True).warning(f"人工排查任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"人工排查任务出现异常: {e}"},
        )
