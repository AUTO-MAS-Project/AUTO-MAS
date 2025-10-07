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
import subprocess
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from jinja2 import Environment, FileSystemLoader

from app.core import Broadcast, Config, MaaConfig, MaaUserConfig
from app.models.schema import WebSocketMessage
from app.models.ConfigBase import MultipleConfig
from app.services import Notify, System
from app.utils import get_logger, LogMonitor, ProcessManager
from .skland import skland_sign_in
from app.core.emulator_manager import EmulatorManager

logger = get_logger("MAA 调度器")

METHOD_BOOK = {"NoAction": "8", "ExitGame": "9", "ExitEmulator": "12"}
MOOD_BOOK = {"Annihilation": "剿灭", "Routine": "日常"}


class MaaManager:
    """MAA控制器"""

    def __init__(
        self,
        mode: str,
        script_id: uuid.UUID,
        user_id: uuid.UUID | None,
        ws_id: str,
    ):
        super().__init__()
        self.mode: str = mode
        self.script_id = script_id
        self.user_id = user_id
        self.ws_id = ws_id
        self.maa_process_manager = ProcessManager()
        self.emulator_manager = EmulatorManager()
        self.wait_event = asyncio.Event()
        self.message_queue = asyncio.Queue()
        self.maa_logs = []
        self.maa_result = "Wait"
        self.log_start_time = datetime.now()
        self.maa_update_package = ""

    # ======================
    # 第一阶段：运行前准备
    # ======================

    async def prepare(self):
        """运行前准备：加载配置、校验、备份、筛选用户"""
        await Broadcast.subscribe(self.message_queue)
        await Config.ScriptConfig[self.script_id].lock()
        self.script_config = Config.ScriptConfig[self.script_id]
        self.user_config = MultipleConfig([MaaUserConfig])
        await self.user_config.load(await self.script_config.UserData.toDict())

        self.maa_root_path = Path(self.script_config.get("Info", "Path"))
        self.maa_set_path = self.maa_root_path / "config/gui.json"
        self.maa_log_path = self.maa_root_path / "debug/gui.log"
        self.maa_exe_path = self.maa_root_path / "MAA.exe"
        self.maa_tasks_path = self.maa_root_path / "resource/tasks/tasks.json"

        self.port_range = [0] + [
            (i // 2 + 1) * (-1 if i % 2 else 1)
            for i in range(0, 2 * self.script_config.get("Run", "ADBSearchRange"))
        ]

        self.maa_log_monitor = LogMonitor(
            (1, 20), "%Y-%m-%d %H:%M:%S", self._on_log_received
        )

        logger.success(f"{self.script_id}已锁定, MAA配置提取完成")

        # 配置校验
        self.check_result = self._validate_config()
        if self.check_result != "Success!":
            logger.error(f"未通过配置检查: {self.check_result}")
            await Config.send_json(
                WebSocketMessage(
                    id=self.ws_id, type="Info", data={"Error": self.check_result}
                ).model_dump()
            )
            return

        # 备份原始配置
        temp_dir = Path.cwd() / f"data/{self.script_id}/Temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        if self.maa_set_path.exists():
            shutil.copy(self.maa_set_path, temp_dir / "gui.json")

        # 筛选用户（仅非“设置脚本”模式）
        if self.mode != "设置脚本":
            self.user_list = self._filter_active_users()
            logger.info(f"用户列表创建完成, 已筛选用户数: {len(self.user_list)}")

    def _validate_config(self) -> str:
        """校验MAA配置是否可用"""
        if not isinstance(Config.ScriptConfig[self.script_id], MaaConfig):
            return "脚本配置类型错误, 不是MAA脚本类型"
        if not self.maa_exe_path.exists():
            return "MAA.exe文件不存在, 请检查MAA路径设置！"
        if not self.maa_set_path.exists():
            return "MAA配置文件不存在, 请检查MAA路径设置！"
        if (self.mode != "设置脚本" or self.user_id is not None) and not (
            Path.cwd() / f"data/{self.script_id}/Default/ConfigFile/gui.json"
        ).exists():
            return "未完成 MAA 全局设置, 请先设置 MAA！"
        return "Success!"

    def _filter_active_users(self) -> list[dict]:
        """筛选出状态为启用且剩余天数 > 0 的用户"""
        users = [
            {
                "user_id": str(uid),
                "status": "等待",
                "name": config.get("Info", "Name"),
            }
            for uid, config in self.user_config.items()
            if config.get("Info", "Status") and config.get("Info", "RemainedDay") != 0
        ]
        return sorted(
            users,
            key=lambda x: self.user_config[uuid.UUID(x["user_id"])].get("Info", "Mode"),
        )

    # ======================
    # 第二阶段：运行中执行
    # ======================

    async def execute(self):
        """根据模式执行对应任务"""
        if self.check_result != "Success!":
            return

        self.current_date = datetime.now().strftime("%m-%d")
        self.curdate = Config.server_date().strftime("%Y-%m-%d")
        self.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if self.mode == "自动代理":
            await self._run_auto_proxy()
        elif self.mode == "人工排查":
            await self._run_manual_inspection()
        elif self.mode == "设置脚本":
            await self._run_setup_mode()

    async def _run_auto_proxy(self):
        """自动代理模式主逻辑"""
        self.if_open_emulator = True

        # 初始化每日代理状态
        for user in self.user_list:
            user_data = self.user_config[uuid.UUID(user["user_id"])]
            if user_data.get("Data", "LastProxyDate") != self.curdate:
                await user_data.set("Data", "LastProxyDate", self.curdate)
                await user_data.set("Data", "ProxyTimes", 0)

        for self.index, user in enumerate(self.user_list):
            try:
                self.cur_user_data = self.user_config[uuid.UUID(user["user_id"])]
                proxy_limit = self.script_config.get("Run", "ProxyTimesLimit")
                current_times = self.cur_user_data.get("Data", "ProxyTimes")

                if proxy_limit == 0 or current_times < proxy_limit:
                    user["status"] = "运行"
                else:
                    user["status"] = "跳过"
                    await self._update_ui_user_list()
                    continue

                await self._update_ui_user_list()
                logger.info(f"开始代理用户: {user['user_id']}")

                if self.cur_user_data.get("Info", "Mode") == "详细":
                    self.if_open_emulator = True

                self.run_book = {
                    "Annihilation": self.cur_user_data.get("Info", "Annihilation")
                    == "Close",
                    "Routine": self.cur_user_data.get("Info", "Mode") == "详细"
                    and not self.cur_user_data.get("Info", "Routine"),
                }
                self.user_logs_list = []
                self.user_start_time = datetime.now()

                # 森空岛签到
                if self.cur_user_data.get(
                    "Info", "IfSkland"
                ) and self.cur_user_data.get("Info", "SklandToken"):
                    if self.cur_user_data.get(
                        "Data", "LastSklandDate"
                    ) != datetime.now().strftime("%Y-%m-%d"):
                        await Config.send_json(
                            WebSocketMessage(
                                id=self.ws_id,
                                type="Update",
                                data={"log": "正在执行森空岛签到中\n请稍候~"},
                            ).model_dump()
                        )
                        skland_result = await skland_sign_in(
                            self.cur_user_data.get("Info", "SklandToken")
                        )
                        for type_, user_list in skland_result.items():
                            if type_ != "总计" and len(user_list) > 0:
                                logger.info(
                                    f"用户: {user['user_id']} - 森空岛签到{type_}: {'、'.join(user_list)}"
                                )
                                await Config.send_json(
                                    WebSocketMessage(
                                        id=self.ws_id,
                                        type="Info",
                                        data={
                                            (
                                                "Info" if type_ != "失败" else "Error"
                                            ): f"用户 {user['name']} 森空岛签到{type_}: {'、'.join(user_list)}"
                                        },
                                    ).model_dump()
                                )
                        if skland_result["总计"] == 0:
                            logger.info(f"用户: {user['user_id']} - 森空岛签到失败")
                            await Config.send_json(
                                WebSocketMessage(
                                    id=self.ws_id,
                                    type="Info",
                                    data={
                                        "Error": f"用户 {user['name']} 森空岛签到失败"
                                    },
                                ).model_dump()
                            )
                        if (
                            skland_result["总计"] > 0
                            and len(skland_result["失败"]) == 0
                        ):
                            await self.cur_user_data.set(
                                "Data",
                                "LastSklandDate",
                                datetime.now().strftime("%Y-%m-%d"),
                            )
                elif self.cur_user_data.get("Info", "IfSkland"):
                    logger.warning(
                        f"用户: {user['user_id']} - 未配置森空岛签到Token, 跳过森空岛签到"
                    )
                    await Config.send_json(
                        WebSocketMessage(
                            id=self.ws_id,
                            type="Info",
                            data={
                                "Warning": f"用户 {user['name']} 未配置森空岛签到Token, 跳过森空岛签到"
                            },
                        ).model_dump()
                    )

                # 执行剿灭 + 日常
                for mode in ["Annihilation", "Routine"]:
                    if self.run_book[mode]:
                        continue
                    if (
                        mode == "Annihilation"
                        and self.script_config.get("Run", "AnnihilationWeeklyLimit")
                        and datetime.strptime(
                            self.cur_user_data.get("Data", "LastAnnihilationDate"),
                            "%Y-%m-%d",
                        ).isocalendar()[:2]
                        == datetime.strptime(self.curdate, "%Y-%m-%d").isocalendar()[:2]
                    ):
                        logger.info(
                            f"用户: {user['user_id']} - 本周剿灭模式已达上限, 跳过执行剿灭任务"
                        )
                        self.run_book[mode] = True
                        continue
                    else:
                        self.weekly_annihilation_limit_reached = False

                    if (
                        self.cur_user_data.get("Info", "Mode") == "详细"
                        and not (
                            Path.cwd()
                            / f"data/{self.script_id}/{user['user_id']}/ConfigFile/gui.json"
                        ).exists()
                    ):
                        logger.error(
                            f"用户: {user['user_id']} - 未找到日常详细配置文件"
                        )
                        await Config.send_json(
                            WebSocketMessage(
                                id=self.ws_id,
                                type="Info",
                                data={"Error": f"未找到 {user['name']} 的详细配置文件"},
                            ).model_dump()
                        )
                        self.run_book[mode] = False
                        break

                    await Config.send_json(
                        WebSocketMessage(
                            id=self.ws_id,
                            type="Update",
                            data={
                                "user_status": {
                                    "user_id": user["user_id"],
                                    "type": mode,
                                }
                            },
                        ).model_dump()
                    )

                    if mode == "Routine":
                        self.task_dict = {
                            "WakeUp": str(self.cur_user_data.get("Task", "IfWakeUp")),
                            "Recruiting": str(
                                self.cur_user_data.get("Task", "IfRecruiting")
                            ),
                            "Base": str(self.cur_user_data.get("Task", "IfBase")),
                            "Combat": str(self.cur_user_data.get("Task", "IfCombat")),
                            "Mission": str(self.cur_user_data.get("Task", "IfMission")),
                            "Mall": str(self.cur_user_data.get("Task", "IfMall")),
                            "AutoRoguelike": str(
                                self.cur_user_data.get("Task", "IfAutoRoguelike")
                            ),
                            "Reclamation": str(
                                self.cur_user_data.get("Task", "IfReclamation")
                            ),
                        }
                    else:  # Annihilation
                        self.task_dict = {
                            "WakeUp": "True",
                            "Recruiting": "False",
                            "Base": "False",
                            "Combat": "True",
                            "Mission": "False",
                            "Mall": "False",
                            "AutoRoguelike": "False",
                            "Reclamation": "False",
                        }

                    logger.info(
                        f"用户 {user['name']} - 模式: {mode} - 任务列表: {list(self.task_dict.values())}"
                    )

                    for i in range(self.script_config.get("Run", "RunTimesLimit")):
                        if self.run_book[mode]:
                            break
                        logger.info(
                            f"用户 {user['name']} - 模式: {mode} - 尝试次数: {i + 1}/{self.script_config.get('Run', 'RunTimesLimit')}"
                        )

                        set_config = await self.set_maa(mode)
                        self.log_start_time = datetime.now()

                        self.emulator_uuid = self.cur_user_data.get("Emulator", "uuid")
                        self.emulator_index = self.cur_user_data.get(
                            "Emulator", "index"
                        )
                        self.if_open_emulator = True

                        self.wait_time = int(
                            set_config["Configurations"]["Default"][
                                "Start.EmulatorWaitSeconds"
                            ]
                        )
                        self.ADB_path = Path(
                            set_config["Configurations"]["Default"]["Connect.AdbPath"]
                        )
                        self.ADB_path = (
                            self.ADB_path
                            if self.ADB_path.is_absolute()
                            else self.maa_root_path / self.ADB_path
                        )
                        self.ADB_address = set_config["Configurations"]["Default"][
                            "Connect.Address"
                        ]
                        self.if_kill_emulator = (
                            set_config["Configurations"]["Default"][
                                "MainFunction.PostActions"
                            ]
                            == "12"
                        )
                        self.if_open_emulator_process = (
                            set_config["Configurations"]["Default"][
                                "Start.OpenEmulatorAfterLaunch"
                            ]
                            == "True"
                        )

                        # 释放 ADB
                        await self._disconnect_adb(self.ADB_path, self.ADB_address)

                        if self.if_open_emulator_process:
                            (
                                OK,
                                e,
                                self.adb_dict,
                            ) = await self.emulator_manager.start_emulator(
                                self.emulator_uuid, self.emulator_index
                            )
                            if not OK:
                                logger.exception(f"启动模拟器时出现异常: {e}")
                                await Config.send_json(
                                    WebSocketMessage(
                                        id=self.ws_id,
                                        type="Info",
                                        data={
                                            "Error": "启动模拟器时出现异常, 请检查MAA中模拟器路径设置"
                                        },
                                    ).model_dump()
                                )
                                self.if_open_emulator = True
                                break

                        logger.info(f"启动MAA进程: {self.maa_exe_path}")
                        await self.maa_process_manager.open_process(
                            self.maa_exe_path, [], 0
                        )
                        self.log_check_mode = mode
                        await self.maa_log_monitor.start(
                            self.maa_log_path, self.log_start_time
                        )
                        self.wait_event.clear()
                        await self.wait_event.wait()
                        await self.maa_log_monitor.stop()

                        if self.maa_result == "Success!":
                            self.run_book[mode] = True
                            logger.info(
                                f"用户: {user['user_id']} - MAA进程完成代理任务"
                            )
                            await Config.send_json(
                                WebSocketMessage(
                                    id=self.ws_id,
                                    type="Update",
                                    data={
                                        "log": "检测到MAA进程完成代理任务\n正在等待相关程序结束\n请等待10s"
                                    },
                                ).model_dump()
                            )
                        else:
                            logger.error(
                                f"用户: {user['user_id']} - 代理任务异常: {self.maa_result}"
                            )
                            await Config.send_json(
                                WebSocketMessage(
                                    id=self.ws_id,
                                    type="Update",
                                    data={
                                        "log": f"{self.maa_result}\n正在中止相关程序\n请等待10s"
                                    },
                                ).model_dump()
                            )
                            await self.maa_process_manager.kill(if_force=True)
                            await System.kill_process(self.maa_exe_path)
                            logger.info("任务结束后再次中止模拟器进程:")
                            await self.emulator_manager.close_emulator(
                                self.emulator_uuid, self.emulator_index
                            )
                            self.if_open_emulator = True
                            await Notify.push_plyer(
                                "用户自动代理出现异常！",
                                f"用户 {user['name']} 的{MOOD_BOOK[mode]}部分出现一次异常",
                                f"{user['name']}的{MOOD_BOOK[mode]}出现异常",
                                3,
                            )

                        await asyncio.sleep(10)

                        await self._disconnect_adb(self.ADB_path, self.ADB_address)
                        if self.if_kill_emulator:
                            logger.info("任务结束后再次中止模拟器进程:")
                            await self.emulator_manager.close_emulator(
                                self.emulator_uuid, self.emulator_index
                            )
                            self.if_open_emulator = True

                        with self.maa_set_path.open(mode="r", encoding="utf-8") as f:
                            data = json.load(f)

                        await self.cur_user_data.set(
                            "Data",
                            "CustomInfrastPlanIndex",
                            data["Configurations"]["Default"][
                                "Infrast.CustomInfrastPlanIndex"
                            ],
                        )

                        if data["Global"]["VersionUpdate.package"]:
                            pkg = data["Global"]["VersionUpdate.package"]
                            if (self.maa_root_path / pkg).exists():
                                self.maa_update_package = pkg

                        if mode == "Annihilation" and getattr(
                            self, "weekly_annihilation_limit_reached", False
                        ):
                            await self.cur_user_data.set(
                                "Data", "LastAnnihilationDate", self.curdate
                            )

                        log_path = (
                            Path.cwd()
                            / f"history/{self.curdate}/{user['name']}/{self.log_start_time.strftime('%H-%M-%S')}.log"
                        )
                        if_six_star = await Config.save_maa_log(
                            log_path, self.maa_logs, self.maa_result
                        )
                        self.user_logs_list.append(log_path.with_suffix(".json"))

                        if if_six_star:
                            try:
                                await self.push_notification(
                                    "公招六星",
                                    f"喜报: 用户 {user['name']} 公招出六星啦！",
                                    {"user_name": user["name"]},
                                )
                            except Exception as e:
                                logger.exception(f"推送公招六星通知时出现异常: {e}")
                                await Config.send_json(
                                    WebSocketMessage(
                                        id=self.ws_id,
                                        type="Info",
                                        data={
                                            "Error": f"推送公招六星通知时出现异常: {e}"
                                        },
                                    ).model_dump()
                                )

                        if self.maa_update_package:
                            logger.info("检测到MAA更新, 正在执行更新动作")
                            await Config.send_json(
                                WebSocketMessage(
                                    id=self.ws_id,
                                    type="Update",
                                    data={
                                        "log": "检测到MAA存在更新\nMAA正在执行更新动作\n请等待10s"
                                    },
                                ).model_dump()
                            )
                            await self.set_maa("Update")
                            subprocess.Popen(
                                [self.maa_exe_path],
                                creationflags=subprocess.CREATE_NO_WINDOW,
                            )
                            await asyncio.sleep(10)
                            await System.kill_process(self.maa_exe_path)
                            self.maa_update_package = ""
                            logger.info("更新动作结束")

                    await self._record_user_result()

            except Exception as e:
                logger.exception(f"代理用户 {user['user_id']} 时出现异常: {e}")
                user["status"] = "异常"
                await Config.send_json(
                    WebSocketMessage(
                        id=self.ws_id,
                        type="Info",
                        data={"Error": f"代理用户 {user['name']} 时出现异常: {e}"},
                    ).model_dump()
                )

    async def _run_manual_inspection(self):
        """人工排查模式主逻辑"""
        logger.info("人工排查任务开始, 屏蔽静默操作")
        Config.if_ignore_silence.append(self.script_id)
        self.if_open_emulator = True

        for self.index, user in enumerate(self.user_list):
            self.cur_user_data = self.user_config[uuid.UUID(user["user_id"])]
            user["status"] = "运行"
            await self._update_ui_user_list()
            logger.info(f"开始排查用户: {user['user_id']}")

            if self.cur_user_data.get("Info", "Mode") == "详细":
                self.if_open_emulator = True

            self.run_book = {"SignIn": False, "PassCheck": False}

            while True:
                await self.set_maa("人工排查")
                self.log_start_time = datetime.now()
                await self.maa_process_manager.open_process(self.maa_exe_path, [], 0)
                self.log_check_mode = "人工排查"
                await self.maa_log_monitor.start(self.maa_log_path, self.log_start_time)
                self.wait_event.clear()
                await self.wait_event.wait()
                await self.maa_log_monitor.stop()

                if self.maa_result == "Success!":
                    self.run_book["SignIn"] = True
                    break
                else:
                    uid = str(uuid.uuid4())
                    await Config.send_json(
                        WebSocketMessage(
                            id=self.ws_id,
                            type="Message",
                            data={
                                "message_id": uid,
                                "type": "Question",
                                "title": "操作提示",
                                "message": "MAA未能正确登录到PRTS, 是否重试？",
                                "options": ["是", "否"],
                            },
                        ).model_dump()
                    )
                    result = await self._wait_for_user_response(uid)
                    if not result.get("data", {}).get("choice", False):
                        break

            if self.run_book["SignIn"]:
                uid = str(uuid.uuid4())
                await Config.send_json(
                    WebSocketMessage(
                        id=self.ws_id,
                        type="Message",
                        data={
                            "message_id": uid,
                            "type": "Question",
                            "title": "操作提示",
                            "message": "请检查用户代理情况, 该用户是否正确完成代理任务？",
                            "options": ["是", "否"],
                        },
                    ).model_dump()
                )
                result = await self._wait_for_user_response(uid)
                if result.get("data", {}).get("choice", False):
                    self.run_book["PassCheck"] = True

            await self._record_user_result()
            await self._update_ui_user_list()

    async def _run_setup_mode(self):
        """设置脚本模式：启动MAA供用户配置"""
        await self.set_maa("设置脚本")
        logger.info(f"启动MAA进程: {self.maa_exe_path}")
        await self.maa_process_manager.open_process(self.maa_exe_path, [], 0)
        self.wait_event.clear()
        await self.wait_event.wait()

    # ======================
    # 辅助方法（运行中）
    # ======================

    async def _disconnect_adb(self, adb_path: Path, address: str):
        """安全断开ADB连接"""
        try:
            subprocess.run(
                [adb_path, "disconnect", address],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception as e:
            logger.warning(f"释放ADB时出现异常: {e}")

    async def _update_ui_user_list(self):
        await Config.send_json(
            WebSocketMessage(
                id=self.ws_id, type="Update", data={"user_list": self.user_list}
            ).model_dump()
        )

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

    # ======================
    # 日志回调（原 check_maa_log）
    # ======================

    async def _on_log_received(self, log_content: list[str]) -> None:
        """日志回调（原 check_maa_log）"""
        self.maa_logs = log_content
        log = "".join(log_content)

        if await self.maa_process_manager.is_running():
            await Config.send_json(
                WebSocketMessage(
                    id=self.ws_id, type="Update", data={"log": log}
                ).model_dump()
            )

        if self.mode == "自动代理":
            latest_time = self.log_start_time
            for line in self.maa_logs[::-1]:
                try:
                    if "如果长时间无进一步日志更新, 可能需要手动干预。" in line:
                        continue
                    latest_time = datetime.strptime(line[1:20], "%Y-%m-%d %H:%M:%S")
                    break
                except ValueError:
                    pass

            if self.log_check_mode == "Annihilation" and "任务出错: 刷理智" in log:
                self.weekly_annihilation_limit_reached = True
            else:
                self.weekly_annihilation_limit_reached = False

            if "任务出错: StartUp" in log or "任务出错: 开始唤醒" in log:
                self.maa_result = "MAA未能正确登录PRTS"
            elif "任务已全部完成！" in log:
                if "完成任务: StartUp" in log or "完成任务: 开始唤醒" in log:
                    self.task_dict["WakeUp"] = "False"
                if "完成任务: Recruit" in log or "完成任务: 自动公招" in log:
                    self.task_dict["Recruiting"] = "False"
                if "完成任务: Infrast" in log or "完成任务: 基建换班" in log:
                    self.task_dict["Base"] = "False"
                if (
                    "完成任务: Fight" in log
                    or "完成任务: 刷理智" in log
                    or (
                        self.log_check_mode == "Annihilation"
                        and "任务出错: 刷理智" in log
                    )
                ):
                    self.task_dict["Combat"] = "False"
                if "完成任务: Mall" in log or "完成任务: 获取信用及购物" in log:
                    self.task_dict["Mall"] = "False"
                if "完成任务: Award" in log or "完成任务: 领取奖励" in log:
                    self.task_dict["Mission"] = "False"
                if "完成任务: Roguelike" in log or "完成任务: 自动肉鸽" in log:
                    self.task_dict["AutoRoguelike"] = "False"
                if "完成任务: Reclamation" in log or "完成任务: 生息演算" in log:
                    self.task_dict["Reclamation"] = "False"
                if all(v == "False" for v in self.task_dict.values()):
                    self.maa_result = "Success!"
                else:
                    self.maa_result = "MAA部分任务执行失败"
            elif "请 ｢检查连接设置｣ → ｢尝试重启模拟器与 ADB｣ → ｢重启电脑｣" in log:
                self.maa_result = "MAA的ADB连接异常"
            elif "未检测到任何模拟器" in log:
                self.maa_result = "MAA未检测到任何模拟器"
            elif "已停止" in log:
                self.maa_result = "MAA在完成任务前中止"
            elif (
                "MaaAssistantArknights GUI exited" in log
                or not await self.maa_process_manager.is_running()
            ):
                self.maa_result = "MAA在完成任务前退出"
            elif datetime.now() - latest_time > timedelta(
                minutes=self.script_config.get("Run", f"{self.log_check_mode}TimeLimit")
            ):
                self.maa_result = "MAA进程超时"
            else:
                self.maa_result = "Wait"

        elif self.mode == "人工排查":
            if "完成任务: StartUp" in log or "完成任务: 开始唤醒" in log:
                self.maa_result = "Success!"
            elif "请 ｢检查连接设置｣ → ｢尝试重启模拟器与 ADB｣ → ｢重启电脑｣" in log:
                self.maa_result = "MAA的ADB连接异常"
            elif "未检测到任何模拟器" in log:
                self.maa_result = "MAA未检测到任何模拟器"
            elif "已停止" in log:
                self.maa_result = "MAA在完成任务前中止"
            elif (
                "MaaAssistantArknights GUI exited" in log
                or not await self.maa_process_manager.is_running()
            ):
                self.maa_result = "MAA在完成任务前退出"
            else:
                self.maa_result = "Wait"

        logger.debug(f"MAA 日志分析结果: {self.maa_result}")
        if self.maa_result != "Wait":
            logger.info(f"MAA 任务结果: {self.maa_result}, 日志锁已释放")
            self.wait_event.set()

    # ======================
    # 第三阶段：运行结束
    # ======================

    async def finalize(self, task: asyncio.Task):
        """运行结束后的收尾工作"""
        logger.info("MAA 主任务已结束, 开始执行后续操作")
        await Config.ScriptConfig[self.script_id].unlock()
        logger.success(f"已解锁脚本配置 {self.script_id}")

        await Broadcast.unsubscribe(self.message_queue)
        await self.maa_process_manager.kill(if_force=True)
        await System.kill_process(self.maa_exe_path)
        await self.maa_log_monitor.stop()

        if self.check_result != "Success!":
            return self.check_result

        if self.mode == "人工排查" and self.script_id in Config.if_ignore_silence:
            Config.if_ignore_silence.remove(self.script_id)

        # 补录中途退出的任务
        if self.mode in ["自动代理", "人工排查"]:
            if (
                hasattr(self, "index")
                and self.user_list[self.index]["status"] == "运行"
            ):
                if self.mode == "自动代理" and not self.maa_update_package:
                    self.maa_result = "用户手动中止任务"
                    log_path = (
                        Path.cwd()
                        / f"history/{self.curdate}/{self.user_list[self.index]['name']}/{self.log_start_time.strftime('%H-%M-%S')}.log"
                    )
                    if_six_star = await Config.save_maa_log(
                        log_path, self.maa_logs, self.maa_result
                    )
                    if if_six_star:
                        try:
                            await self.push_notification(
                                "公招六星",
                                f"喜报: 用户 {self.user_list[self.index]['name']} 公招出六星啦！",
                                {
                                    "user_name": self.user_list[self.index]["name"],
                                },
                            )
                        except Exception:
                            pass
                await self._record_user_result()

        summary_text = ""
        if self.mode in ["自动代理", "人工排查"]:
            await Config.ScriptConfig[self.script_id].UserData.load(
                await self.user_config.toDict()
            )
            await Config.ScriptConfig.save()
            summary_text = self._generate_final_report()
        elif self.mode == "设置脚本":
            target_dir = (
                Path.cwd()
                / f"data/{self.script_id}/{self.user_id or 'Default'}/ConfigFile"
            )
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(self.maa_set_path, target_dir / "gui.json")

        # 还原配置
        temp_path = Path.cwd() / f"data/{self.script_id}/Temp/gui.json"
        if temp_path.exists():
            shutil.copy(temp_path, self.maa_set_path)
        shutil.rmtree(Path.cwd() / f"data/{self.script_id}/Temp", ignore_errors=True)

        self.agree_bilibili(False)
        return summary_text

    async def _generate_final_report(self) -> str:
        """生成最终任务报告文本"""
        error_user = [u["name"] for u in self.user_list if u["status"] == "异常"]
        over_user = [u["name"] for u in self.user_list if u["status"] == "完成"]
        wait_user = [u["name"] for u in self.user_list if u["status"] == "等待"]

        title = f"{self.current_date} | {self.script_config.get('Info', 'Name') or '空白'}的{self.mode}任务报告"
        result = {
            "title": f"{self.mode}任务报告",
            "script_name": self.script_config.get("Info", "Name") or "空白",
            "start_time": self.begin_time,
            "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "completed_count": len(over_user),
            "uncompleted_count": len(error_user) + len(wait_user),
            "failed_user": error_user,
            "waiting_user": wait_user,
        }

        await Notify.push_plyer(
            title.replace("报告", "已完成！"),
            f"已完成用户数: {len(over_user)}, 未完成用户数: {len(error_user) + len(wait_user)}",
            f"已完成用户数: {len(over_user)}, 未完成用户数: {len(error_user) + len(wait_user)}",
            10,
        )
        try:
            await self.push_notification("代理结果", title, result)
        except Exception as e:
            logger.exception(f"推送代理结果时出现异常: {e}")

        text = (
            f"任务开始时间: {result['start_time']}, 结束时间: {result['end_time']}\n"
            f"已完成数: {result['completed_count']}, 未完成数: {result['uncompleted_count']}\n"
        )
        if error_user:
            text += f"{self.mode[2:4]}未成功的用户: \n" + "\n".join(error_user) + "\n"
        if wait_user:
            text += f"\n未开始{self.mode[2:4]}的用户: \n" + "\n".join(wait_user)
        return text

    async def _record_user_result(self):
        """记录单个用户结果（自动代理 / 人工排查）"""
        if self.mode == "自动代理":
            statistics = await Config.merge_statistic_info(self.user_logs_list)
            statistics["user_info"] = self.user_list[self.index]["name"]
            statistics["start_time"] = self.user_start_time.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            statistics["maa_result"] = (
                "代理任务全部完成"
                if (self.run_book["Annihilation"] and self.run_book["Routine"])
                else "代理任务未全部完成"
            )
            try:
                await self.push_notification(
                    "统计信息",
                    f"{self.current_date} | 用户 {self.user_list[self.index]['name']} 的自动代理统计报告",
                    statistics,
                )
            except Exception as e:
                logger.exception(f"推送统计信息时出现异常: {e}")
                await Config.send_json(
                    WebSocketMessage(
                        id=self.ws_id,
                        type="Info",
                        data={"Error": f"推送统计信息时出现异常: {e}"},
                    ).model_dump()
                )
            if self.run_book["Annihilation"] and self.run_book["Routine"]:
                if (
                    self.cur_user_data.get("Data", "ProxyTimes") == 0
                    and self.cur_user_data.get("Info", "RemainedDay") != -1
                ):
                    await self.cur_user_data.set(
                        "Info",
                        "RemainedDay",
                        self.cur_user_data.get("Info", "RemainedDay") - 1,
                    )
                await self.cur_user_data.set(
                    "Data",
                    "ProxyTimes",
                    self.cur_user_data.get("Data", "ProxyTimes") + 1,
                )
                self.user_list[self.index]["status"] = "完成"
                logger.success(
                    f"用户 {self.user_list[self.index]['user_id']} 的自动代理任务已完成"
                )
                await Notify.push_plyer(
                    "成功完成一个自动代理任务！",
                    f"已完成用户 {self.user_list[self.index]['name']} 的自动代理任务",
                    f"已完成 {self.user_list[self.index]['name']} 的自动代理任务",
                    3,
                )
            else:
                logger.error(
                    f"用户 {self.user_list[self.index]['user_id']} 的自动代理任务未完成"
                )
                self.user_list[self.index]["status"] = "异常"
        elif self.mode == "人工排查":
            if self.run_book["SignIn"] and self.run_book["PassCheck"]:
                logger.info(
                    f"用户 {self.user_list[self.index]['user_id']} 通过人工排查"
                )
                await self.cur_user_data.set("Data", "IfPassCheck", True)
                self.user_list[self.index]["status"] = "完成"
            else:
                logger.info(
                    f"用户 {self.user_list[self.index]['user_id']} 未通过人工排查"
                )
                await self.cur_user_data.set("Data", "IfPassCheck", False)
                self.user_list[self.index]["status"] = "异常"
        await self._update_ui_user_list()

    # ======================
    # 对外兼容接口
    # ======================

    async def run(self):
        """对外统一入口（兼容旧调用）"""
        await self.prepare()
        if self.check_result == "Success!":
            await self.execute()

    async def final_task(self, task: asyncio.Task):
        return await self.finalize(task)

    # ======================
    # 原始方法
    # ======================

    async def set_maa(self, mode: str) -> dict:
        """配置MAA运行参数"""
        logger.info(f"开始配置MAA运行参数: {mode}")
        if self.mode != "设置脚本" and mode != "Update":
            if self.cur_user_data.get("Info", "Server") == "Bilibili":
                self.agree_bilibili(True)
            else:
                self.agree_bilibili(False)
        await self.maa_process_manager.kill(if_force=True)
        await System.kill_process(self.maa_exe_path)
        if self.mode in ["自动代理", "人工排查"]:
            if self.cur_user_data.get("Info", "Mode") == "简洁":
                shutil.copy(
                    (Path.cwd() / f"data/{self.script_id}/Default/ConfigFile/gui.json"),
                    self.maa_set_path,
                )
            elif self.cur_user_data.get("Info", "Mode") == "详细":
                shutil.copy(
                    (
                        Path.cwd()
                        / f"data/{self.script_id}/{self.user_list[self.index]['user_id']}/ConfigFile/gui.json"
                    ),
                    self.maa_set_path,
                )
        elif self.mode == "设置脚本":
            if (
                self.user_id is None
                and (
                    Path.cwd() / f"data/{self.script_id}/Default/ConfigFile/gui.json"
                ).exists()
            ):
                shutil.copy(
                    (Path.cwd() / f"data/{self.script_id}/Default/ConfigFile/gui.json"),
                    self.maa_set_path,
                )
            elif self.user_id is not None:
                if (
                    Path.cwd()
                    / f"data/{self.script_id}/{self.user_id}/ConfigFile/gui.json"
                ).exists():
                    shutil.copy(
                        (
                            Path.cwd()
                            / f"data/{self.script_id}/{self.user_id}/ConfigFile/gui.json"
                        ),
                        self.maa_set_path,
                    )
                else:
                    shutil.copy(
                        (
                            Path.cwd()
                            / f"data/{self.script_id}/Default/ConfigFile/gui.json"
                        ),
                        self.maa_set_path,
                    )
        with self.maa_set_path.open(mode="r", encoding="utf-8") as f:
            data = json.load(f)
        if data["Current"] != "Default":
            data["Configurations"]["Default"] = data["Configurations"][data["Current"]]
            data["Current"] = "Default"
        for i in range(1, 9):
            data["Global"][f"Timer.Timer{i}"] = "False"
        if self.mode == "自动代理" and mode in ["Annihilation", "Routine"]:
            if (self.index == len(self.user_list) - 1) or (
                self.user_config[
                    uuid.UUID(self.user_list[self.index + 1]["user_id"])
                ].get("Info", "Mode")
                == "详细"
            ):
                data["Configurations"]["Default"]["MainFunction.PostActions"] = "12"
            else:
                data["Configurations"]["Default"]["MainFunction.PostActions"] = (
                    METHOD_BOOK[self.script_config.get("Run", "TaskTransitionMethod")]
                )
            data["Configurations"]["Default"]["Start.RunDirectly"] = "True"
            data["Configurations"]["Default"]["Start.OpenEmulatorAfterLaunch"] = str(
                self.if_open_emulator
            )
            data["Global"]["VersionUpdate.ScheduledUpdateCheck"] = "False"
            data["Global"]["VersionUpdate.AutoDownloadUpdatePackage"] = "True"
            data["Global"]["VersionUpdate.AutoInstallUpdatePackage"] = "False"
            if Config.get("Function", "IfSilence"):
                data["Global"]["Start.MinimizeDirectly"] = "True"
                data["Global"]["GUI.UseTray"] = "True"
                data["Global"]["GUI.MinimizeToTray"] = "True"
            data["Configurations"]["Default"]["Start.ClientType"] = (
                self.cur_user_data.get("Info", "Server")
            )
            if self.cur_user_data.get("Info", "Server") == "Official":
                data["Configurations"]["Default"]["Start.AccountName"] = (
                    f"{self.cur_user_data.get('Info', 'Id')[:3]}****{self.cur_user_data.get('Info', 'Id')[7:]}"
                    if len(self.cur_user_data.get("Info", "Id")) == 11
                    else self.cur_user_data.get("Info", "Id")
                )
            elif self.cur_user_data.get("Info", "Server") == "Bilibili":
                data["Configurations"]["Default"]["Start.AccountName"] = (
                    self.cur_user_data.get("Info", "Id")
                )
            data["Configurations"]["Default"]["TaskQueue.WakeUp.IsChecked"] = "True"
            data["Configurations"]["Default"]["TaskQueue.Recruiting.IsChecked"] = (
                self.task_dict["Recruiting"]
            )
            data["Configurations"]["Default"]["TaskQueue.Base.IsChecked"] = (
                self.task_dict["Base"]
            )
            data["Configurations"]["Default"]["TaskQueue.Combat.IsChecked"] = (
                self.task_dict["Combat"]
            )
            data["Configurations"]["Default"]["TaskQueue.Mission.IsChecked"] = (
                self.task_dict["Mission"]
            )
            data["Configurations"]["Default"]["TaskQueue.Mall.IsChecked"] = (
                self.task_dict["Mall"]
            )
            data["Configurations"]["Default"]["TaskQueue.AutoRoguelike.IsChecked"] = (
                self.task_dict["AutoRoguelike"]
            )
            data["Configurations"]["Default"]["TaskQueue.Reclamation.IsChecked"] = (
                self.task_dict["Reclamation"]
            )
            if (
                mode == "Annihilation"
                or self.cur_user_data.get("Info", "Mode") == "简洁"
            ):
                data["Configurations"]["Default"]["TaskQueue.Order.WakeUp"] = "0"
                data["Configurations"]["Default"]["TaskQueue.Order.Recruiting"] = "1"
                data["Configurations"]["Default"]["TaskQueue.Order.Base"] = "2"
                data["Configurations"]["Default"]["TaskQueue.Order.Combat"] = "3"
                data["Configurations"]["Default"]["TaskQueue.Order.Mall"] = "4"
                data["Configurations"]["Default"]["TaskQueue.Order.Mission"] = "5"
                data["Configurations"]["Default"]["TaskQueue.Order.AutoRoguelike"] = "6"
                data["Configurations"]["Default"]["TaskQueue.Order.Reclamation"] = "7"
            if self.cur_user_data.get("Info", "StageMode") == "Fixed":
                plan_data = {
                    "MedicineNumb": self.cur_user_data.get("Info", "MedicineNumb"),
                    "SeriesNumb": self.cur_user_data.get("Info", "SeriesNumb"),
                    "Stage": self.cur_user_data.get("Info", "Stage"),
                    "Stage_1": self.cur_user_data.get("Info", "Stage_1"),
                    "Stage_2": self.cur_user_data.get("Info", "Stage_2"),
                    "Stage_3": self.cur_user_data.get("Info", "Stage_3"),
                    "Stage_Remain": self.cur_user_data.get("Info", "Stage_Remain"),
                }
            else:
                plan = Config.PlanConfig[
                    uuid.UUID(self.cur_user_data.get("Info", "StageMode"))
                ]
                plan_data = {
                    "MedicineNumb": plan.get_current_info("MedicineNumb").getValue(),
                    "SeriesNumb": plan.get_current_info("SeriesNumb").getValue(),
                    "Stage": plan.get_current_info("Ssstage").getValue(),
                    "Stage_1": plan.get_current_info("Stage_1").getValue(),
                    "Stage_2": plan.get_current_info("Stage_2").getValue(),
                    "Stage_3": plan.get_current_info("Stage_3").getValue(),
                    "Stage_Remain": plan.get_current_info("Stage_Remain").getValue(),
                }
            data["Configurations"]["Default"]["MainFunction.UseMedicine"] = (
                "False" if plan_data.get("MedicineNumb", 0) == 0 else "True"
            )
            data["Configurations"]["Default"]["MainFunction.UseMedicine.Quantity"] = (
                str(plan_data.get("MedicineNumb", 0))
            )
            data["Configurations"]["Default"]["MainFunction.Series.Quantity"] = (
                plan_data.get("SeriesNumb", "0")
            )
            if mode == "Annihilation":
                data["Configurations"]["Default"]["MainFunction.Stage1"] = (
                    "Annihilation"
                )
                data["Configurations"]["Default"]["MainFunction.Stage2"] = ""
                data["Configurations"]["Default"]["MainFunction.Stage3"] = ""
                data["Configurations"]["Default"]["Fight.RemainingSanityStage"] = ""
                data["Configurations"]["Default"]["MainFunction.Series.Quantity"] = "1"
                data["Configurations"]["Default"][
                    "MainFunction.Annihilation.UseCustom"
                ] = "True"
                data["Configurations"]["Default"]["MainFunction.Annihilation.Stage"] = (
                    self.cur_user_data.get("Info", "Annihilation")
                )
                data["Configurations"]["Default"]["Penguin.IsDrGrandet"] = "False"
                data["Configurations"]["Default"]["GUI.CustomStageCode"] = "True"
                data["Configurations"]["Default"]["GUI.UseAlternateStage"] = "False"
                data["Configurations"]["Default"]["Fight.UseRemainingSanityStage"] = (
                    "False"
                )
                data["Configurations"]["Default"]["Fight.UseExpiringMedicine"] = "True"
                data["Configurations"]["Default"]["GUI.HideSeries"] = "False"
            elif mode == "Routine":
                data["Configurations"]["Default"]["MainFunction.Stage1"] = (
                    plan_data.get("Stage") if plan_data.get("Stage", "-") != "-" else ""
                )
                data["Configurations"]["Default"]["MainFunction.Stage2"] = (
                    plan_data.get("Stage_1")
                    if plan_data.get("Stage_1", "-") != "-"
                    else ""
                )
                data["Configurations"]["Default"]["MainFunction.Stage3"] = (
                    plan_data.get("Stage_2")
                    if plan_data.get("Stage_2", "-") != "-"
                    else ""
                )
                data["Configurations"]["Default"]["MainFunction.Stage4"] = (
                    plan_data.get("Stage_3")
                    if plan_data.get("Stage_3", "-") != "-"
                    else ""
                )
                data["Configurations"]["Default"]["Fight.RemainingSanityStage"] = (
                    plan_data.get("Stage_Remain")
                    if plan_data.get("Stage_Remain", "-") != "-"
                    else ""
                )
                data["Configurations"]["Default"]["GUI.UseAlternateStage"] = "True"
                data["Configurations"]["Default"]["Fight.UseRemainingSanityStage"] = (
                    "True" if plan_data.get("Stage_Remain", "-") != "-" else "False"
                )
                if self.cur_user_data.get("Info", "Mode") == "简洁":
                    data["Configurations"]["Default"]["Penguin.IsDrGrandet"] = "False"
                    data["Configurations"]["Default"]["GUI.CustomStageCode"] = "True"
                    data["Configurations"]["Default"]["Fight.UseExpiringMedicine"] = (
                        "True"
                    )
                    if self.cur_user_data.get("Info", "InfrastMode") == "Custom":
                        infra_path = (
                            Path.cwd()
                            / f"data/{self.script_id}/{self.user_list[self.index]['user_id']}/Infrastructure/infrastructure.json"
                        )
                        if infra_path.exists():
                            data["Configurations"]["Default"]["Infrast.InfrastMode"] = (
                                "Custom"
                            )
                            data["Configurations"]["Default"][
                                "Infrast.CustomInfrastPlanIndex"
                            ] = self.cur_user_data.get("Data", "CustomInfrastPlanIndex")
                            data["Configurations"]["Default"][
                                "Infrast.DefaultInfrast"
                            ] = "user_defined"
                            data["Configurations"]["Default"][
                                "Infrast.IsCustomInfrastFileReadOnly"
                            ] = "False"
                            data["Configurations"]["Default"][
                                "Infrast.CustomInfrastFile"
                            ] = str(infra_path)
                        else:
                            logger.warning(
                                f"未选择用户 {self.cur_user_data.get('Info', 'Name')} 的自定义基建配置文件"
                            )
                            await Config.send_json(
                                WebSocketMessage(
                                    id=self.ws_id,
                                    type="Info",
                                    data={
                                        "warning": f"未选择用户 {self.cur_user_data.get('Info', 'Name')} 的自定义基建配置文件"
                                    },
                                ).model_dump()
                            )
                            data["Configurations"]["Default"][
                                "Infrast.CustomInfrastEnabled"
                            ] = "Normal"
                    else:
                        data["Configurations"]["Default"]["Infrast.InfrastMode"] = (
                            self.cur_user_data.get("Info", "InfrastMode")
                        )
                elif self.cur_user_data.get("Info", "Mode") == "详细":
                    if (
                        data["Configurations"]["Default"]["Infrast.InfrastMode"]
                        == "Custom"
                    ):
                        data["Configurations"]["Default"][
                            "Infrast.CustomInfrastPlanIndex"
                        ] = self.cur_user_data.get("Data", "CustomInfrastPlanIndex")
        elif self.mode == "人工排查" and self.cur_user_data is not None:
            data["Configurations"]["Default"]["MainFunction.PostActions"] = "8"
            data["Configurations"]["Default"]["Start.RunDirectly"] = "True"
            data["Global"]["Start.MinimizeDirectly"] = "True"
            data["Global"]["GUI.UseTray"] = "True"
            data["Global"]["GUI.MinimizeToTray"] = "True"
            data["Configurations"]["Default"]["Start.OpenEmulatorAfterLaunch"] = str(
                self.if_open_emulator
            )
            data["Global"]["VersionUpdate.ScheduledUpdateCheck"] = "False"
            data["Global"]["VersionUpdate.AutoDownloadUpdatePackage"] = "False"
            data["Global"]["VersionUpdate.AutoInstallUpdatePackage"] = "False"
            data["Configurations"]["Default"]["Start.ClientType"] = (
                self.cur_user_data.get("Info", "Server")
            )
            if self.cur_user_data.get("Info", "Server") == "Official":
                data["Configurations"]["Default"]["Start.AccountName"] = (
                    f"{self.cur_user_data.get('Info', 'Id')[:3]}****{self.cur_user_data.get('Info', 'Id')[7:]}"
                    if len(self.cur_user_data.get("Info", "Id")) == 11
                    else self.cur_user_data.get("Info", "Id")
                )
            elif self.cur_user_data.get("Info", "Server") == "Bilibili":
                data["Configurations"]["Default"]["Start.AccountName"] = (
                    self.cur_user_data.get("Info", "Id")
                )
            data["Configurations"]["Default"]["TaskQueue.WakeUp.IsChecked"] = "True"
            data["Configurations"]["Default"]["TaskQueue.Recruiting.IsChecked"] = (
                "False"
            )
            data["Configurations"]["Default"]["TaskQueue.Base.IsChecked"] = "False"
            data["Configurations"]["Default"]["TaskQueue.Combat.IsChecked"] = "False"
            data["Configurations"]["Default"]["TaskQueue.Mission.IsChecked"] = "False"
            data["Configurations"]["Default"]["TaskQueue.Mall.IsChecked"] = "False"
            data["Configurations"]["Default"]["TaskQueue.AutoRoguelike.IsChecked"] = (
                "False"
            )
            data["Configurations"]["Default"]["TaskQueue.Reclamation.IsChecked"] = (
                "False"
            )
        elif self.mode == "设置脚本":
            data["Configurations"]["Default"]["MainFunction.PostActions"] = "0"
            data["Configurations"]["Default"]["Start.RunDirectly"] = "False"
            data["Configurations"]["Default"]["Start.OpenEmulatorAfterLaunch"] = "False"
            data["Global"]["VersionUpdate.ScheduledUpdateCheck"] = "False"
            data["Global"]["VersionUpdate.AutoDownloadUpdatePackage"] = "False"
            data["Global"]["VersionUpdate.AutoInstallUpdatePackage"] = "False"
            if Config.get("Function", "IfSilence"):
                data["Global"]["Start.MinimizeDirectly"] = "False"
            data["Configurations"]["Default"]["TaskQueue.WakeUp.IsChecked"] = "False"
            data["Configurations"]["Default"]["TaskQueue.Recruiting.IsChecked"] = (
                "False"
            )
            data["Configurations"]["Default"]["TaskQueue.Base.IsChecked"] = "False"
            data["Configurations"]["Default"]["TaskQueue.Combat.IsChecked"] = "False"
            data["Configurations"]["Default"]["TaskQueue.Mission.IsChecked"] = "False"
            data["Configurations"]["Default"]["TaskQueue.Mall.IsChecked"] = "False"
            data["Configurations"]["Default"]["TaskQueue.AutoRoguelike.IsChecked"] = (
                "False"
            )
            data["Configurations"]["Default"]["TaskQueue.Reclamation.IsChecked"] = (
                "False"
            )
        elif mode == "Update":
            data["Configurations"]["Default"]["MainFunction.PostActions"] = "0"
            data["Configurations"]["Default"]["Start.RunDirectly"] = "False"
            data["Configurations"]["Default"]["Start.OpenEmulatorAfterLaunch"] = "False"
            data["Global"]["Start.MinimizeDirectly"] = "True"
            data["Global"]["GUI.UseTray"] = "True"
            data["Global"]["GUI.MinimizeToTray"] = "True"
            data["Global"]["VersionUpdate.package"] = self.maa_update_package
            data["Global"]["VersionUpdate.ScheduledUpdateCheck"] = "False"
            data["Global"]["VersionUpdate.AutoDownloadUpdatePackage"] = "False"
            data["Global"]["VersionUpdate.AutoInstallUpdatePackage"] = "True"
            data["Configurations"]["Default"]["TaskQueue.WakeUp.IsChecked"] = "False"
            data["Configurations"]["Default"]["TaskQueue.Recruiting.IsChecked"] = (
                "False"
            )
            data["Configurations"]["Default"]["TaskQueue.Base.IsChecked"] = "False"
            data["Configurations"]["Default"]["TaskQueue.Combat.IsChecked"] = "False"
            data["Configurations"]["Default"]["TaskQueue.Mission.IsChecked"] = "False"
            data["Configurations"]["Default"]["TaskQueue.Mall.IsChecked"] = "False"
            data["Configurations"]["Default"]["TaskQueue.AutoRoguelike.IsChecked"] = (
                "False"
            )
            data["Configurations"]["Default"]["TaskQueue.Reclamation.IsChecked"] = (
                "False"
            )
        if self.mode != "设置脚本" and mode != "Update" and self.if_open_emulator:
            self.if_open_emulator = False
        with self.maa_set_path.open(mode="w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logger.success(f"MAA运行参数配置完成: {mode}")
        return data

    def agree_bilibili(self, if_agree):
        """向MAA写入Bilibili协议相关任务"""
        logger.info(f"Bilibili协议相关任务状态: {'启用' if if_agree else '禁用'}")
        with self.maa_tasks_path.open(mode="r", encoding="utf-8") as f:
            data = json.load(f)
        if if_agree and Config.get("Function", "IfAgreeBilibili"):
            data["BilibiliAgreement_AUTO"] = {
                "algorithm": "OcrDetect",
                "action": "ClickSelf",
                "text": ["同意"],
                "maxTimes": 5,
                "Doc": "关闭B服用户协议",
                "next": ["StartUpThemes#next"],
            }
            if "BilibiliAgreement_AUTO" not in data["StartUpThemes"]["next"]:
                data["StartUpThemes"]["next"].insert(0, "BilibiliAgreement_AUTO")
        else:
            if "BilibiliAgreement_AUTO" in data:
                data.pop("BilibiliAgreement_AUTO")
            if "BilibiliAgreement_AUTO" in data["StartUpThemes"]["next"]:
                data["StartUpThemes"]["next"].remove("BilibiliAgreement_AUTO")
        with self.maa_tasks_path.open(mode="w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    async def push_notification(self, mode: str, title: str, message) -> None:
        """通过所有渠道推送通知"""
        logger.info(f"开始推送通知, 模式: {mode}, 标题: {title}")
        env = Environment(loader=FileSystemLoader(str(Path.cwd() / "res/html")))
        if mode == "代理结果" and (
            Config.get("Notify", "SendTaskResultTime") == "任何时刻"
            or (
                Config.get("Notify", "SendTaskResultTime") == "仅失败时"
                and message["uncompleted_count"] != 0
            )
        ):
            message_text = (
                f"任务开始时间: {message['start_time']}, 结束时间: {message['end_time']}\n"
                f"已完成数: {message['completed_count']}, 未完成数: {message['uncompleted_count']}\n"
            )
            if len(message["failed_user"]) > 0:
                message_text += (
                    f"{self.mode[2:4]}未成功的用户: \n"
                    + "\n".join(message["failed_user"])
                    + "\n"
                )
            if len(message["waiting_user"]) > 0:
                message_text += (
                    f"\n未开始{self.mode[2:4]}的用户: \n"
                    + "\n".join(message["waiting_user"])
                    + "\n"
                )
            message["failed_user"] = "、".join(message["failed_user"])
            message["waiting_user"] = "、".join(message["waiting_user"])
            template = env.get_template("MAA_result.html")
            message_html = template.render(message)
            serverchan_message = message_text.replace("\n", "\n\n")
            if Config.get("Notify", "IfSendMail"):
                await Notify.send_mail(
                    "网页", title, message_html, Config.get("Notify", "ToAddress")
                )
            if Config.get("Notify", "IfServerChan"):
                await Notify.ServerChanPush(
                    title,
                    f"{serverchan_message}\nAUTO-MAS 敬上",
                    Config.get("Notify", "ServerChanKey"),
                )
            for webhook in Config.Notify_CustomWebhooks.values():
                await Notify.WebhookPush(
                    title, f"{message_text}\nAUTO-MAS 敬上", webhook
                )
        elif mode == "统计信息":
            formatted = []
            if "drop_statistics" in message:
                for stage, items in message["drop_statistics"].items():
                    formatted.append(f"掉落统计（{stage}）:")
                    for item, quantity in items.items():
                        formatted.append(f"  {item}: {quantity}")
            drop_text = "\n".join(formatted)
            formatted = ["招募统计:"]
            if "recruit_statistics" in message:
                for star, count in message["recruit_statistics"].items():
                    formatted.append(f"  {star}: {count}")
            recruit_text = "\n".join(formatted)
            message_text = (
                f"开始时间: {message['start_time']}\n"
                f"结束时间: {message['end_time']}\n"
                f"理智剩余: {message.get('sanity', '未知')}\n"
                f"回复时间: {message.get('sanity_full_at', '未知')}\n"
                f"MAA执行结果: {message['maa_result']}\n"
                f"{recruit_text}\n"
                f"{drop_text}"
            )
            template = env.get_template("MAA_statistics.html")
            message_html = template.render(message)
            serverchan_message = message_text.replace("\n", "\n\n")
            if Config.get("Notify", "IfSendStatistic"):
                if Config.get("Notify", "IfSendMail"):
                    await Notify.send_mail(
                        "网页", title, message_html, Config.get("Notify", "ToAddress")
                    )
                if Config.get("Notify", "IfServerChan"):
                    await Notify.ServerChanPush(
                        title,
                        f"{serverchan_message}\nAUTO-MAS 敬上",
                        Config.get("Notify", "ServerChanKey"),
                    )
                for webhook in Config.Notify_CustomWebhooks.values():
                    await Notify.WebhookPush(
                        title, f"{message_text}\nAUTO-MAS 敬上", webhook
                    )
            if self.cur_user_data.get("Notify", "Enabled") and self.cur_user_data.get(
                "Notify", "IfSendStatistic"
            ):
                if self.cur_user_data.get("Notify", "IfSendMail"):
                    await Notify.send_mail(
                        "网页",
                        title,
                        message_html,
                        self.cur_user_data.get("Notify", "ToAddress"),
                    )
                if self.cur_user_data.get("Notify", "IfServerChan"):
                    await Notify.ServerChanPush(
                        title,
                        f"{serverchan_message}\nAUTO-MAS 敬上",
                        self.cur_user_data.get("Notify", "ServerChanKey"),
                    )
                for webhook in self.cur_user_data.Notify_CustomWebhooks.values():
                    await Notify.WebhookPush(
                        title, f"{message_text}\nAUTO-MAS 敬上", webhook
                    )
        elif mode == "公招六星":
            template = env.get_template("MAA_six_star.html")
            message_html = template.render(message)
            if Config.get("Notify", "IfSendSixStar"):
                if Config.get("Notify", "IfSendMail"):
                    await Notify.send_mail(
                        "网页", title, message_html, Config.get("Notify", "ToAddress")
                    )
                if Config.get("Notify", "IfServerChan"):
                    await Notify.ServerChanPush(
                        title,
                        "好羡慕~\nAUTO-MAS 敬上",
                        Config.get("Notify", "ServerChanKey"),
                    )
                for webhook in Config.Notify_CustomWebhooks.values():
                    await Notify.WebhookPush(title, "好羡慕~\nAUTO-MAS 敬上", webhook)
            if self.cur_user_data.get("Notify", "Enabled") and self.cur_user_data.get(
                "Notify", "IfSendSixStar"
            ):
                if self.cur_user_data.get("Notify", "IfSendMail"):
                    await Notify.send_mail(
                        "网页",
                        title,
                        message_html,
                        self.cur_user_data.get("Notify", "ToAddress"),
                    )
                if self.cur_user_data.get("Notify", "IfServerChan"):
                    await Notify.ServerChanPush(
                        title,
                        "好羡慕~\nAUTO-MAS 敬上",
                        self.cur_user_data.get("Notify", "ServerChanKey"),
                    )
                for webhook in self.cur_user_data.Notify_CustomWebhooks.values():
                    await Notify.WebhookPush(title, "好羡慕~\nAUTO-MAS 敬上", webhook)
