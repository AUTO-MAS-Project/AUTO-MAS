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


import re
import uuid
import json
import json5
import shutil
import asyncio
from pathlib import Path
from datetime import datetime, timedelta

from app.core import Config
from app.models.task import TaskExecuteBase, ScriptItem, LogRecord
from app.models.ConfigBase import MultipleConfig
from app.models.config import MaaEndConfig, MaaEndUserConfig
from app.models.emulator import DeviceBase, DeviceInfo
from app.services import Notify, System
from app.utils import get_logger, LogMonitor, ProcessManager
from app.tools import skland_sign_in
from app.utils.constants import UTC4, UTC8, MAAEND_KILLPROC_TASK
from .tools import login, push_notification

logger = get_logger("MaaEnd 自动代理")


class AutoProxyTask(TaskExecuteBase):
    """MaaEnd 自动代理模式"""

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
        self.check_result = "-"

    async def check(self) -> str:

        if self.script_config.get(
            "Run", "ProxyTimesLimit"
        ) != 0 and self.cur_user_config.get(
            "Data", "ProxyTimes"
        ) >= self.script_config.get(
            "Run", "ProxyTimesLimit"
        ):
            self.cur_user_item.status = "跳过"
            return "今日代理次数已达上限, 跳过该用户"

        if (
            self.cur_user_config.get("Info", "Mode") == "详细"
            and not (
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile"
            ).exists()
        ):
            self.cur_user_item.status = "异常"
            return (
                "未找到用户的 MaaEnd 配置文件, 请先在用户配置页完成「MaaEnd 配置」步骤"
            )

        return "Pass"

    async def prepare(self):

        self.maaend_process_manager = ProcessManager()
        if self.emulator_manager is None:
            self.game_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()
        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now()

        self.maaend_root_path = Path(self.script_config.get("Info", "Path"))
        self.maaend_exe_path = self.maaend_root_path / "MaaEnd.exe"
        self.maaend_set_path = self.maaend_root_path / "config"
        self.maaend_log_path = self.maaend_root_path / "debug/maa.log"

        self.maaend_log_monitor = LogMonitor(
            (1, 23), "%Y-%m-%d %H:%M:%S.%f", self.check_log
        )

        self.run_book = False

    async def main_task(self):
        """自动代理模式主逻辑"""

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

        logger.info(f"开始代理用户 {self.cur_user_uid}")
        self.cur_user_item.status = "运行"

        self.task_dict: dict[str, dict[str, bool]] | None = None
        self.unique_task: dict[str, str] = {}

        if (
            self.cur_user_config.get("Info", "IfSkland")
            and self.cur_user_config.get("Info", "SklandToken")
            and self.cur_user_config.get("Data", "LastSklandDate")
            != datetime.now(tz=UTC8).strftime("%Y-%m-%d")
        ):
            self.script_info.log = "正在执行森空岛签到"
            skland_result = await skland_sign_in(
                self.cur_user_config.get("Info", "SklandToken"),
                app_code="endfield",
            )
            for result_type, user_list in skland_result.items():
                if result_type != "总计" and len(user_list) > 0:
                    logger.info(
                        f"用户: {self.cur_user_uid} - 森空岛签到{result_type}: {'、'.join(user_list)}"
                    )
                    await Config.send_websocket_message(
                        id=self.task_info.task_id,
                        type="Info",
                        data={
                            (
                                "Info" if result_type != "失败" else "Error"
                            ): f"用户 {self.cur_user_item.name} 森空岛签到{result_type}: {'、'.join(user_list)}"
                        },
                    )
            if skland_result["总计"] == 0:
                logger.info(f"用户: {self.cur_user_uid} - 森空岛签到失败")
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={"Error": f"用户 {self.cur_user_item.name} 森空岛签到失败"},
                )
            if skland_result["总计"] > 0 and len(skland_result["失败"]) == 0:
                await self.cur_user_config.set(
                    "Data",
                    "LastSklandDate",
                    datetime.now(tz=UTC8).strftime("%Y-%m-%d"),
                )
        elif self.cur_user_config.get("Info", "IfSkland") and self.cur_user_config.get(
            "Data", "LastSklandDate"
        ) != datetime.now(tz=UTC8).strftime("%Y-%m-%d"):
            logger.warning(
                f"用户: {self.cur_user_uid} - 未配置森空岛签到Token, 跳过森空岛签到"
            )
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={
                    "Warning": f"用户 {self.cur_user_item.name} 未配置森空岛签到Token, 跳过森空岛签到"
                },
            )

        for i in range(self.script_config.get("Run", "RunTimesLimit")):
            if self.run_book:
                break
            logger.info(
                f"用户 {self.cur_user_item.name} - 尝试次数: {i + 1}/{self.script_config.get('Run', 'RunTimesLimit')}"
            )
            self.log_start_time = datetime.now()
            self.cur_user_item.log_record[self.log_start_time] = self.cur_user_log = (
                LogRecord()
            )

            self.script_info.log = "正在启动游戏..."
            # 启动游戏
            try:
                if self.emulator_manager is None:
                    logger.info(
                        f"启动终末地: {self.script_config.get('Game', 'Path')} - {self.script_config.get('Game', 'Arguments')}"
                    )
                    await self.game_process_manager.open_process(
                        self.script_config.get("Game", "Path"),
                        *str(self.script_config.get("Game", "Arguments")).split(" "),
                    )
                    emulator_info = None
                    await asyncio.sleep(self.script_config.get("Game", "WaitTime"))
                else:
                    logger.info(
                        f"启动模拟器: {self.script_config.get('Game', 'EmulatorIndex')}"
                    )
                    emulator_info = await self.emulator_manager.open(
                        self.script_config.get("Game", "EmulatorIndex"),
                        "com.hypergryph.endfield",
                    )
            except Exception as e:
                await self.handle_pre_maaend_error("模拟器启动失败", e)
                continue

            self.script_info.log = (
                "正在启动游戏...\n游戏启动成功\n正在登录「明日方舟：终末地」..."
            )

            if self.cur_user_config.get("Info", "Id") == "" or await login(
                self.cur_user_config.get("Info", "Id"),
                self.cur_user_config.get("Info", "Password"),
                emulator_info,
            ):
                logger.info(f"用户 {self.cur_user_item.user_id} 登录成功")
            else:
                await self.handle_pre_maaend_error("「明日方舟：终末地」登录失败")
                continue

            self.script_info.log = "正在启动游戏...\n游戏启动成功\n正在登录「明日方舟：终末地」\n「明日方舟：终末地」登录成功"

            await self.set_maaend(emulator_info)

            logger.info(f"运行脚本任务: {self.maaend_exe_path}")
            self.wait_event.clear()
            await self.maaend_process_manager.open_process(
                self.maaend_exe_path, stdout=asyncio.subprocess.PIPE
            )
            await asyncio.sleep(3)  # 等待 MaaEnd 启动完成
            # 静默模式隐藏 MaaEnd 窗口
            if Config.get("Function", "IfSilence"):
                if await self.maaend_process_manager.minimize_window():
                    logger.success("静默模式: 成功隐藏 MaaEnd 窗口")
                else:
                    logger.error("静默模式: 隐藏 MaaEnd 窗口失败")
            if self.script_config.get("Game", "ControllerType") == "Win32-Front":
                if await self.game_process_manager.activate_window():
                    logger.success("前置 Endfield 窗口成功")
                else:
                    logger.error("前置 Endfield 窗口失败")

            await asyncio.sleep(1)
            if isinstance(
                self.maaend_process_manager.main_process, asyncio.subprocess.Process
            ):
                await self.maaend_log_monitor.start_monitor_process(
                    self.maaend_process_manager.main_process, "stdout"
                )
            await self.wait_event.wait()
            await self.maaend_log_monitor.stop()

            if self.cur_user_log.status == "Success!":
                self.run_book = True
                self.script_info.log = (
                    "检测到 MaaEnd 完成代理任务\n正在等待相关程序结束"
                )

                # 中止相关程序
                await self.maaend_process_manager.kill()
                await System.kill_process(self.maaend_exe_path)

            else:
                logger.error(
                    f"用户: {self.cur_user_uid} - 代理任务异常: {self.cur_user_log.status}"
                )
                self.script_info.log = f"{self.cur_user_log.status}\n正在中止相关程序"

                # 中止相关程序
                await self.kill_managed_process()

                await Notify.push_plyer(
                    "用户自动代理出现异常！",
                    f"用户 {self.cur_user_item.name} 的自动代理出现一次异常",
                    f"{self.cur_user_item.name}的自动代理出现异常",
                    3,
                )
                if "游戏分辨率设置错误" in self.cur_user_log.status:
                    logger.info("检测到游戏分辨率设置错误，跳过后续重试")
                    break

    async def handle_pre_maaend_error(
        self, error_message: str, e: Exception | None = None
    ):

        if e is None:
            logger.error(f"用户: {self.cur_user_uid} - {error_message}")
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": error_message},
            )
        else:
            logger.exception(f"用户: {self.cur_user_uid} - {error_message}: {e}")
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": f"{error_message}: {e}"},
            )
        self.cur_user_log.content = [f"{error_message}, 无日志记录"]
        self.cur_user_log.status = error_message

        await self.kill_managed_process()

        await Notify.push_plyer(
            "用户自动代理出现异常！",
            f"用户 {self.cur_user_item.name} 自动代理时{error_message}",
            f"{self.cur_user_item.name}的自动代理出现异常",
            3,
        )

    async def kill_managed_process(self) -> None:
        """中止关联进程"""

        try:
            logger.info(f"中止 MaaEnd 进程: {self.maaend_exe_path}")
            await self.maaend_process_manager.kill()
            await System.kill_process(self.maaend_exe_path)
        except Exception as e:
            logger.exception(f"中止 MaaEnd 进程失败: {e}")
        try:
            if self.emulator_manager is None:
                logger.info("中止终末地进程")
                await self.game_process_manager.kill()
                await System.kill_process(self.script_config.get("Game", "Path"))
            else:
                logger.info("中止模拟器进程")
                await self.emulator_manager.close(
                    self.script_config.get("Game", "EmulatorIndex")
                )
        except Exception as e:
            logger.exception(f"关闭模拟器失败: {e}")

    async def set_maaend(self, device_info: DeviceInfo | None) -> None:
        """写入 MaaEnd 运行前配置"""

        logger.info("开始配置 MaaEnd 运行参数: 自动代理")

        # 配置前关闭可能未正常退出的脚本进程
        await self.maaend_process_manager.kill()
        await System.kill_process(self.maaend_exe_path)

        # 基础配置内容
        maaend_config_path = (
            Path.cwd()
            / f"data/{self.script_info.script_id}/{'Default' if self.cur_user_config.get('Info', 'Mode') == '简洁' else self.cur_user_uid}/ConfigFile"
        )
        shutil.rmtree(self.maaend_set_path, ignore_errors=True)
        shutil.copytree(maaend_config_path, self.maaend_set_path)

        # 初始化任务实例
        maaend_set = json.loads(
            (self.maaend_set_path / "mxu-MaaEnd.json").read_text(encoding="utf-8")
        )

        # 获取任务项单例
        for instance in maaend_set["instances"]:
            if instance["id"] == "automas":
                maaend_instance = instance
                break
        else:
            maaend_instance = {"id": "automas", "name": "AUTO-MAS", "tasks": []}
        maaend_set["instances"] = [maaend_instance]
        maaend_tasks = maaend_instance["tasks"]

        # 建立全局设置引用
        settings = maaend_set["settings"]

        # 移除冗余任务项信息
        maaend_set["recentlyClosed"] = []

        # 直接运行任务
        settings["autoStartInstanceId"] = "automas"
        settings["autoRunOnLaunch"] = True
        settings.pop("autoStartRemovedInstanceName", None)

        # 模拟器相关配置
        maaend_instance["controllerName"] = self.script_config.get(
            "Game", "ControllerType"
        )
        if device_info is not None:

            from app.core import MaaFWManager

            maaend_instance["savedDevice"] = {
                "adbDeviceName": (await MaaFWManager.convert_adb(device_info)).name
            }

        # 加载 i18n 配置
        if settings["language"] == "system":
            settings["language"] = "zh-CN"
        maaend_i18n_raw = json.loads(
            (
                self.maaend_root_path
                / f"locales/interface/{settings['language'].lower().replace('-', '_')}.json"
            ).read_text(encoding="utf-8")
        )
        maaend_i18n = {}
        for task_definition_file in self.maaend_root_path.glob("tasks/*.json"):
            task_definition = json5.loads(  # type: ignore
                task_definition_file.read_text(encoding="utf-8")
            )["task"][0]
            if task_definition["label"].startswith("$"):
                maaend_i18n[task_definition["name"]] = maaend_i18n_raw[
                    task_definition["label"].lstrip("$")
                ]
            else:
                maaend_i18n[task_definition["name"]] = task_definition["label"]

        # 配置任务启用状态
        if self.task_dict is None:
            # 任务列表为空则记录任务
            self.task_dict = {}
            task = {}
            for task in maaend_tasks:
                if (
                    task["taskName"] == "__MXU_KILLPROC__"
                    and task["optionValues"]["__MXU_KILLPROC_SELF_OPTION__"]["value"]
                ):
                    continue
                task_name = maaend_i18n.get(task["taskName"], task["taskName"])
                if task_name not in self.task_dict:
                    self.task_dict[task_name] = {}
                self.task_dict[task_name][task["id"]] = task["enabled"]
        else:
            # 任务列表不为空则配置任务
            for task in maaend_tasks:
                task_name = maaend_i18n.get(task["taskName"], task["taskName"])
                if task_name in self.task_dict:
                    task["enabled"] = self.task_dict[task_name][task["id"]]

        # 配置协议空间
        for task in maaend_tasks:
            if task["taskName"] == "ProtocolSpace":
                task["optionValues"]["ProtocolSpaceTab"] = {
                    "type": "select",
                    "caseName": self.cur_user_config.get("Task", "ProtocolSpaceTab"),
                }
                task["optionValues"]["OperatorProgression"] = {
                    "type": "select",
                    "caseName": self.cur_user_config.get("Task", "OperatorProgression"),
                }
                task["optionValues"]["WeaponProgression"] = {
                    "type": "select",
                    "caseName": self.cur_user_config.get("Task", "WeaponProgression"),
                }
                task["optionValues"]["CrisisDrills"] = {
                    "type": "select",
                    "caseName": self.cur_user_config.get("Task", "CrisisDrills"),
                }
                task["optionValues"]["RewardsSetOption"] = {
                    "type": "select",
                    "caseName": self.cur_user_config.get("Task", "RewardsSetOption"),
                }
                break

        # 完成任务后退出脚本
        if (
            maaend_tasks[-1]["taskName"] == "__MXU_KILLPROC__"
            and maaend_tasks[-1]["optionValues"]["__MXU_KILLPROC_SELF_OPTION__"][
                "value"
            ]
        ):
            maaend_tasks[-1] = MAAEND_KILLPROC_TASK
        else:
            maaend_tasks.append(MAAEND_KILLPROC_TASK)

        (self.maaend_set_path / "mxu-MaaEnd.json").write_text(
            json.dumps(maaend_set, ensure_ascii=False, indent=4), encoding="utf-8"
        )
        logger.success("MaaEnd 运行参数配置完成: 自动代理")

    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """日志回调"""

        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log
        if "资源加载失败" in log:
            self.cur_user_log.status = "MaaEnd 资源加载失败"
        elif "快捷键开始任务：失败" in log:
            self.cur_user_log.status = "MaaEnd 任务启动失败"
        elif "resolution check failed" in log or "分辨率不符合要求" in log:
            self.cur_user_log.status = "游戏分辨率设置错误，请重设分辨率比例为16:9"
        elif (
            "任务完成: 停止任务" in log
            or "任务完成: ⛔ 结束进程" in log
            or "任务完成: __MXU_KILLPROC__" in log
            or "任务完成: StopTask" in log
            or not await self.maaend_process_manager.is_running()
        ):
            if self.task_dict is None:
                self.cur_user_log.status = "MaaEnd 未加载任何任务"
            else:
                try:
                    task_name = ""
                    task_index = {
                        k: {"index": 0, "list": list(v.keys())}
                        for k, v in self.task_dict.items()
                    }
                    for log_line in self.cur_user_log.content:
                        match = re.search(r"任务开始:\s*(.+)", log_line)
                        task_name = match.group(1) if match else task_name
                        if (
                            task_name in self.task_dict
                            and f"任务完成: {task_name}" in log_line
                        ):
                            self.task_dict[task_name][
                                task_index[task_name]["list"][
                                    task_index[task_name]["index"]
                                ]
                            ] = False
                            task_index[task_name]["index"] += 1
                        elif f"任务失败: {task_name}" in log_line:
                            task_index[task_name]["index"] += 1

                    if any(any(_.values()) for _ in self.task_dict.values()):
                        self.cur_user_log.status = "MaaEnd 部分任务执行失败"
                    else:
                        self.cur_user_log.status = "Success!"
                except:
                    self.cur_user_log.status = "MaaEnd 任务执行情况解析失败"

        elif datetime.now() - latest_time > timedelta(
            minutes=self.script_config.get("Run", "RunTimeLimit")
        ):
            self.cur_user_log.status = "MaaEnd 进程超时"
        else:
            self.cur_user_log.status = "MaaEnd 正常运行中"

        logger.debug(f"MaaEnd 日志分析结果: {self.cur_user_log.status}")
        if self.cur_user_log.status != "MaaEnd 正常运行中":
            logger.info(f"MaaEnd 任务结果: {self.cur_user_log.status}, 日志锁已释放")
            self.wait_event.set()

    async def final_task(self):

        if self.check_result != "Pass":
            return

        await self.maaend_log_monitor.stop()
        if (
            self.script_info.current_index == len(self.script_info.user_list) - 1
            and self.run_book
            and not self.script_config.get("Game", "CloseOnFinish")
        ):
            try:
                logger.info(f"中止 MaaEnd 进程: {self.maaend_exe_path}")
                await self.maaend_process_manager.kill()
                await System.kill_process(self.maaend_exe_path)
            except Exception as e:
                logger.exception(f"中止 MaaEnd 进程失败: {e}")
        else:
            await self.kill_managed_process()

        user_logs_list = []
        for t, log_item in self.cur_user_item.log_record.items():

            dt = t.replace(tzinfo=datetime.now().astimezone().tzinfo).astimezone(UTC4)
            log_path = (
                Path.cwd()
                / f"history/{dt.strftime('%Y-%m-%d')}/{self.cur_user_item.name}/{dt.strftime('%H-%M-%S')}.log"
            )
            user_logs_list.append(log_path.with_suffix(".json"))

            if log_item.status == "MaaEnd 正常运行中":
                log_item.status = "任务被用户手动中止"

            if len(log_item.content) == 0:
                log_item.content = ["未捕获到任何日志内容"]
                log_item.status = "未捕获到日志"

            await Config.save_maaend_log(log_path, log_item.content, log_item.status)

        statistics = await Config.merge_statistic_info(user_logs_list)
        statistics["user_info"] = self.cur_user_item.name
        statistics["start_time"] = self.user_start_time.strftime("%Y-%m-%d %H:%M:%S")
        statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        statistics["user_result"] = (
            "代理任务全部完成" if self.run_book else self.cur_user_item.result
        )

        success_symbol = "√" if self.run_book else "X"

        try:
            await push_notification(
                "统计信息",
                f"{datetime.now().strftime('%m-%d')} |{success_symbol}|  {self.cur_user_item.name} 的自动代理统计报告",
                statistics,
                self.cur_user_config,
            )
        except Exception as e:
            logger.exception(f"推送通知时出现异常: {e}")
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": f"推送通知时出现异常: {e}"},
            )

        if self.run_book:
            if (
                self.cur_user_config.get("Data", "ProxyTimes") == 0
                and self.cur_user_config.get("Info", "RemainedDay") != -1
            ):
                await self.cur_user_config.set(
                    "Info",
                    "RemainedDay",
                    self.cur_user_config.get("Info", "RemainedDay") - 1,
                )
            await self.cur_user_config.set(
                "Data",
                "ProxyTimes",
                self.cur_user_config.get("Data", "ProxyTimes") + 1,
            )
            await self.cur_user_config.set("Data", "LastProxyStatus", "成功")
            self.cur_user_item.status = "完成"
            logger.success(f"用户 {self.cur_user_uid} 的自动代理任务已完成")
            await Notify.push_plyer(
                "成功完成一个自动代理任务！",
                f"已完成用户 {self.cur_user_item.name} 的 MaaEnd 自动代理任务",
                f"已完成 {self.cur_user_item.name} 的 MaaEnd 自动代理任务",
                3,
            )
        else:
            await self.cur_user_config.set("Data", "LastProxyStatus", "失败")
            logger.error(f"用户 {self.cur_user_uid} 的自动代理任务未完成")
            self.cur_user_item.status = "异常"

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.exception(f"自动代理任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"自动代理任务出现异常: {e}"},
        )
