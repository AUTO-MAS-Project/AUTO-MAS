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
from datetime import datetime, timedelta

from app.core import Config
from app.models.task import TaskExecuteBase, ScriptItem, LogRecord
from app.models.ConfigBase import MultipleConfig
from app.models.config import MaaConfig, MaaUserConfig
from app.models.emulator import DeviceInfo, DeviceBase
from app.utils.constants import MAA_RUN_MOOD_BOOK, MAA_TASK_TRANSITION_METHOD_BOOK
from app.services import Notify, System
from app.utils import get_logger, LogMonitor, ProcessManager
from app.utils.constants import UTC4, UTC8, MAA_TASKS, ARKNIGHTS_PACKAGE_NAME
from .tools import skland_sign_in, push_notification, agree_bilibili, update_maa

logger = get_logger("MAA 自动代理")


class AutoProxyTask(TaskExecuteBase):
    """自动代理模式"""

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
                / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile/gui.json"
            ).exists()
        ):
            self.cur_user_item.status = "异常"
            return "未找到用户的 MAA 配置文件，请先在用户配置页完成 「MAA配置」 步骤"
        return "Pass"

    async def prepare(self):

        self.maa_process_manager = ProcessManager()
        self.maa_log_monitor = LogMonitor((1, 20), "%Y-%m-%d %H:%M:%S", self.check_log)
        self.wait_event = asyncio.Event()
        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now()

        self.maa_root_path = Path(self.script_config.get("Info", "Path"))
        self.maa_set_path = self.maa_root_path / "config/gui.json"
        self.maa_log_path = self.maa_root_path / "debug/gui.log"
        self.maa_exe_path = self.maa_root_path / "MAA.exe"
        self.maa_tasks_path = self.maa_root_path / "resource/tasks/tasks.json"

        self.run_book = {
            "Annihilation": self.cur_user_config.get("Info", "Annihilation") == "Close",
            "Routine": False,
            "IfAnnihilationAccomplish": False,
        }

    async def main_task(self):
        """自动代理模式主逻辑"""

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

        logger.info(f"开始代理用户: {self.cur_user_uid}")
        self.cur_user_item.status = "运行"

        # 森空岛签到
        if (
            self.cur_user_config.get("Info", "IfSkland")
            and self.cur_user_config.get("Info", "SklandToken")
            and self.cur_user_config.get("Data", "LastSklandDate")
            != datetime.now(tz=UTC8).strftime("%Y-%m-%d")
        ):
            self.script_info.log = "正在执行森空岛签到"
            skland_result = await skland_sign_in(
                self.cur_user_config.get("Info", "SklandToken")
            )
            for t, user_list in skland_result.items():
                if t != "总计" and len(user_list) > 0:
                    logger.info(
                        f"用户: {self.cur_user_uid} - 森空岛签到{t}: {'、'.join(user_list)}"
                    )
                    await Config.send_websocket_message(
                        id=self.task_info.task_id,
                        type="Info",
                        data={
                            (
                                "Info" if t != "失败" else "Error"
                            ): f"用户 {self.cur_user_item.name} 森空岛签到{t}: {'、'.join(user_list)}"
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
                    "Data", "LastSklandDate", datetime.now(tz=UTC8).strftime("%Y-%m-%d")
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

        # 执行剿灭 + 日常
        for self.mode in ["Annihilation", "Routine"]:
            if self.run_book[self.mode]:
                continue
            if (
                self.mode == "Annihilation"
                and self.script_config.get("Run", "AnnihilationWeeklyLimit")
                and datetime.strptime(
                    self.cur_user_config.get("Data", "LastAnnihilationDate"),
                    "%Y-%m-%d",
                )
                .replace(tzinfo=UTC4)
                .isocalendar()[:2]
                == datetime.strptime(self.curdate, "%Y-%m-%d").isocalendar()[:2]
            ):
                logger.info(
                    f"用户: {self.cur_user_uid} - 本周剿灭模式已达上限, 跳过执行剿灭任务"
                )
                self.run_book[self.mode] = True
                continue

            self.cur_user_item.status = f"运行 - {MAA_RUN_MOOD_BOOK[self.mode]}"

            if self.mode == "Routine":
                self.task_dict = {
                    task: str(self.cur_user_config.get("Task", f"If{task}"))
                    for task in MAA_TASKS
                }
            else:  # Annihilation
                self.task_dict = {
                    task: "True" if task in ("WakeUp", "Combat") else "False"
                    for task in MAA_TASKS
                }

            logger.info(
                f"用户 {self.cur_user_item.name} - 模式: {self.mode} - 任务列表: {list(self.task_dict.values())}"
            )

            for i in range(self.script_config.get("Run", "RunTimesLimit")):
                if self.run_book[self.mode]:
                    break
                logger.info(
                    f"用户 {self.cur_user_item.name} - 模式: {self.mode} - 尝试次数: {i + 1}/{self.script_config.get('Run', 'RunTimesLimit')}"
                )
                self.log_start_time = datetime.now()
                self.cur_user_item.log_record[self.log_start_time] = (
                    self.cur_user_log
                ) = LogRecord()

                try:
                    self.script_info.log = "正在启动模拟器"
                    emulator_info = await self.emulator_manager.open(
                        self.script_config.get("Emulator", "Index"),
                        ARKNIGHTS_PACKAGE_NAME[
                            self.cur_user_config.get("Info", "Server")
                        ],
                    )
                except Exception as e:
                    logger.exception(f"用户: {self.cur_user_uid} - 模拟器启动失败: {e}")
                    await Config.send_websocket_message(
                        id=self.task_info.task_id,
                        type="Info",
                        data={"Error": f"启动模拟器时出现异常: {e}"},
                    )
                    self.cur_user_log.content = [
                        "模拟器启动失败, MAA 未实际运行, 无日志记录"
                    ]
                    self.cur_user_log.status = "模拟器启动失败"

                    await self.emulator_manager.close(
                        self.script_config.get("Emulator", "Index")
                    )

                    await Notify.push_plyer(
                        "用户自动代理出现异常！",
                        f"用户 {self.cur_user_item.name} 的{MAA_RUN_MOOD_BOOK[self.mode]}部分出现一次异常",
                        f"{self.cur_user_item.name}的{MAA_RUN_MOOD_BOOK[self.mode]}出现异常",
                        3,
                    )
                    continue

                if Config.get("Function", "IfSilence"):
                    await self.emulator_manager.setVisible(
                        self.script_config.get("Emulator", "Index"), False
                    )

                await self.set_maa(emulator_info)

                logger.info(f"启动MAA进程: {self.maa_exe_path}")
                self.wait_event.clear()
                await self.maa_process_manager.open_process(self.maa_exe_path)
                await asyncio.sleep(1)  # 等待 MAA 处理日志文件
                await self.maa_log_monitor.start_monitor_file(
                    self.maa_log_path, self.log_start_time
                )
                await self.wait_event.wait()
                await self.maa_log_monitor.stop()

                if self.cur_user_log.status == "Success!":
                    self.run_book[self.mode] = True
                    logger.info(f"用户: {self.cur_user_uid} - MAA进程完成代理任务")
                    self.script_info.log = (
                        "检测到 MAA 完成代理任务\n正在等待相关程序结束"
                    )
                else:
                    logger.error(
                        f"用户: {self.cur_user_uid} - 代理任务异常: {self.cur_user_log.status}"
                    )
                    self.script_info.log = (
                        f"{self.cur_user_log.status}\n正在中止相关程序"
                    )

                    await self.maa_process_manager.kill()
                    await self.emulator_manager.close(
                        self.script_config.get("Emulator", "Index")
                    )
                    await System.kill_process(self.maa_exe_path)

                    await Notify.push_plyer(
                        "用户自动代理出现异常！",
                        f"用户 {self.cur_user_item.name} 的{MAA_RUN_MOOD_BOOK[self.mode]}部分出现一次异常",
                        f"{self.cur_user_item.name}的{MAA_RUN_MOOD_BOOK[self.mode]}出现异常",
                        3,
                    )

                await update_maa(self.maa_root_path)
                await asyncio.sleep(3)

    async def set_maa(self, emulator_info: DeviceInfo):
        """配置MAA运行参数"""

        logger.info(f"开始配置MAA运行参数: {self.mode}")

        await self.maa_process_manager.kill()
        await System.kill_process(self.maa_exe_path)

        # 哔哩哔哩用户协议
        if self.cur_user_config.get("Info", "Server") == "Bilibili":
            await agree_bilibili(self.maa_tasks_path, True)
        else:
            await agree_bilibili(self.maa_tasks_path, False)

        # 基础配置内容
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

        # 多配置使用默认配置
        if maa_set["Current"] != "Default":
            maa_set["Configurations"]["Default"] = maa_set["Configurations"][
                maa_set["Current"]
            ]
            maa_set["Current"] = "Default"

        # 关闭所有定时
        for i in range(1, 9):
            maa_set["Global"][f"Timer.Timer{i}"] = "False"

        # 矫正 ADB 地址
        if emulator_info.adb_address != "Unknown":
            maa_set["Configurations"]["Default"][
                "Connect.Address"
            ] = emulator_info.adb_address

        # 任务间切换方式
        maa_set["Configurations"]["Default"]["MainFunction.PostActions"] = (
            MAA_TASK_TRANSITION_METHOD_BOOK[
                self.script_config.get("Run", "TaskTransitionMethod")
            ]
        )

        # 直接运行任务
        maa_set["Configurations"]["Default"]["Start.StartGame"] = "True"
        maa_set["Configurations"]["Default"]["Start.RunDirectly"] = "True"
        maa_set["Configurations"]["Default"]["Start.OpenEmulatorAfterLaunch"] = "False"

        # 更新配置
        maa_set["Global"]["VersionUpdate.ScheduledUpdateCheck"] = "False"
        maa_set["Global"]["VersionUpdate.AutoDownloadUpdatePackage"] = "True"
        maa_set["Global"]["VersionUpdate.AutoInstallUpdatePackage"] = "False"

        # 刷理智强制配置项
        maa_set["Configurations"]["Default"]["Penguin.IsDrGrandet"] = "False"
        maa_set["Configurations"]["Default"]["GUI.HideSeries"] = "False"
        maa_set["Configurations"]["Default"]["GUI.AllowUseStoneSave"] = "False"
        maa_set["Configurations"]["Default"]["GUI.HideUnavailableStage"] = "False"

        # 静默模式相关配置
        if Config.get("Function", "IfSilence"):
            maa_set["Global"]["GUI.UseTray"] = "True"
            maa_set["Global"]["GUI.MinimizeToTray"] = "True"
            maa_set["Global"]["Start.MinimizeDirectly"] = "True"

        # 服务器与账号切换
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

        # 任务配置
        for task in MAA_TASKS:
            maa_set["Configurations"]["Default"][f"TaskQueue.{task}.IsChecked"] = (
                self.task_dict[task]
            )
        maa_set["Configurations"]["Default"]["TaskQueue.WakeUp.IsChecked"] = "True"

        # 任务顺序
        if (
            self.mode == "Annihilation"
            or self.cur_user_config.get("Info", "Mode") == "简洁"
        ):
            for order, task in enumerate(MAA_TASKS):
                maa_set["Configurations"]["Default"][f"TaskQueue.Order.{task}"] = str(
                    order
                )

        # 加载关卡号配置
        if self.cur_user_config.get("Info", "StageMode") == "Fixed":
            plan_data = {
                "MedicineNumb": self.cur_user_config.get("Info", "MedicineNumb"),
                "SeriesNumb": self.cur_user_config.get("Info", "SeriesNumb"),
                "Stage": self.cur_user_config.get("Info", "Stage"),
                "Stage_1": self.cur_user_config.get("Info", "Stage_1"),
                "Stage_2": self.cur_user_config.get("Info", "Stage_2"),
                "Stage_3": self.cur_user_config.get("Info", "Stage_3"),
                "Stage_Remain": self.cur_user_config.get("Info", "Stage_Remain"),
            }
        else:
            plan = Config.PlanConfig[
                uuid.UUID(self.cur_user_config.get("Info", "StageMode"))
            ]
            plan_data = {
                "MedicineNumb": plan.get_current_info("MedicineNumb").getValue(),
                "SeriesNumb": plan.get_current_info("SeriesNumb").getValue(),
                "Stage": plan.get_current_info("Stage").getValue(),
                "Stage_1": plan.get_current_info("Stage_1").getValue(),
                "Stage_2": plan.get_current_info("Stage_2").getValue(),
                "Stage_3": plan.get_current_info("Stage_3").getValue(),
                "Stage_Remain": plan.get_current_info("Stage_Remain").getValue(),
            }

        # 刷理智相关配置项
        # 理智药相关
        maa_set["Configurations"]["Default"]["MainFunction.UseMedicine"] = (
            "False" if plan_data.get("MedicineNumb", 0) == 0 else "True"
        )
        maa_set["Configurations"]["Default"]["MainFunction.UseMedicine.Quantity"] = str(
            plan_data.get("MedicineNumb", 0)
        )
        if self.mode == "Annihilation":
            # 关卡配置
            maa_set["Configurations"]["Default"]["MainFunction.Stage1"] = "Annihilation"
            maa_set["Configurations"]["Default"]["MainFunction.Stage2"] = ""
            maa_set["Configurations"]["Default"]["MainFunction.Stage3"] = ""
            maa_set["Configurations"]["Default"]["Fight.RemainingSanityStage"] = ""
            maa_set["Configurations"]["Default"][
                "MainFunction.Annihilation.UseCustom"
            ] = "True"
            maa_set["Configurations"]["Default"]["MainFunction.Annihilation.Stage"] = (
                self.cur_user_config.get("Info", "Annihilation")
            )

            # 附加配置
            maa_set["Configurations"]["Default"]["MainFunction.TimesLimited"] = "False"
            maa_set["Configurations"]["Default"]["MainFunction.Drops.Enable"] = "False"
            maa_set["Configurations"]["Default"]["MainFunction.Series.Quantity"] = "1"

            maa_set["Configurations"]["Default"]["GUI.CustomStageCode"] = "False"
            maa_set["Configurations"]["Default"]["GUI.UseAlternateStage"] = "False"
            maa_set["Configurations"]["Default"]["Fight.UseExpiringMedicine"] = "True"
            maa_set["Configurations"]["Default"][
                "Fight.UseRemainingSanityStage"
            ] = "False"

        elif self.mode == "Routine":
            # 关卡配置
            maa_set["Configurations"]["Default"]["MainFunction.Series.Quantity"] = (
                plan_data.get("SeriesNumb", "0")
            )
            maa_set["Configurations"]["Default"]["MainFunction.Stage1"] = (
                plan_data.get("Stage") if plan_data.get("Stage", "-") != "-" else ""
            )
            maa_set["Configurations"]["Default"]["MainFunction.Stage2"] = (
                plan_data.get("Stage_1") if plan_data.get("Stage_1", "-") != "-" else ""
            )
            maa_set["Configurations"]["Default"]["MainFunction.Stage3"] = (
                plan_data.get("Stage_2") if plan_data.get("Stage_2", "-") != "-" else ""
            )
            maa_set["Configurations"]["Default"]["MainFunction.Stage4"] = (
                plan_data.get("Stage_3") if plan_data.get("Stage_3", "-") != "-" else ""
            )
            maa_set["Configurations"]["Default"]["Fight.RemainingSanityStage"] = (
                plan_data.get("Stage_Remain")
                if plan_data.get("Stage_Remain", "-") != "-"
                else ""
            )
            maa_set["Configurations"]["Default"]["GUI.UseAlternateStage"] = "True"
            maa_set["Configurations"]["Default"]["Fight.UseRemainingSanityStage"] = (
                "True" if plan_data.get("Stage_Remain", "-") != "-" else "False"
            )
            maa_set["Configurations"]["Default"]["GUI.CustomStageCode"] = "True"

            # 简洁模式下托管的配置
            if self.cur_user_config.get("Info", "Mode") == "简洁":
                maa_set["Configurations"]["Default"][
                    "MainFunction.TimesLimited"
                ] = "False"
                maa_set["Configurations"]["Default"][
                    "MainFunction.Drops.Enable"
                ] = "False"
                maa_set["Configurations"]["Default"][
                    "Fight.UseExpiringMedicine"
                ] = "True"

            # 基建配置
            if self.cur_user_config.get("Info", "InfrastMode") == "Custom":
                infrast_path = (
                    Path.cwd()
                    / f"data/{self.script_info.script_id}/{self.cur_user_uid}/Infrastructure/infrastructure.json"
                )
                if self.cur_user_config.get("Info", "InfrastIndex") != "-1":
                    infrast_path.parent.mkdir(parents=True, exist_ok=True)
                    infrast_path.write_text(
                        self.cur_user_config.get("Data", "CustomInfrast"),
                        encoding="utf-8",
                    )
                    maa_set["Configurations"]["Default"][
                        "Infrast.InfrastMode"
                    ] = "Custom"
                    maa_set["Configurations"]["Default"][
                        "Infrast.CustomInfrastPlanIndex"
                    ] = self.cur_user_config.get("Info", "InfrastIndex")
                    maa_set["Configurations"]["Default"][
                        "Infrast.DefaultInfrast"
                    ] = "user_defined"
                    maa_set["Configurations"]["Default"][
                        "Infrast.IsCustomInfrastFileReadOnly"
                    ] = "False"
                    maa_set["Configurations"]["Default"][
                        "Infrast.CustomInfrastFile"
                    ] = str(infrast_path)
                else:
                    logger.warning(
                        f"用户 {self.cur_user_item.name} 的自定义基建配置文件解析失败, 将使用普通基建模式"
                    )
                    await Config.send_websocket_message(
                        id=self.task_info.task_id,
                        type="Info",
                        data={
                            "Warning": f"未能解析用户 {self.cur_user_item.name} 的自定义基建配置文件"
                        },
                    )
                    maa_set["Configurations"]["Default"][
                        "Infrast.CustomInfrastEnabled"
                    ] = "Normal"
            else:
                maa_set["Configurations"]["Default"]["Infrast.InfrastMode"] = (
                    self.cur_user_config.get("Info", "InfrastMode")
                )

        self.maa_set_path.write_text(
            json.dumps(maa_set, ensure_ascii=False, indent=4), encoding="utf-8"
        )
        logger.success(f"MAA运行参数配置完成: {self.mode}")

    async def check_log(self, log_content: list[str]) -> None:
        """日志回调"""

        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log

        latest_time = self.log_start_time
        for line in log_content[::-1]:
            try:
                if "如果长时间无进一步日志更新, 可能需要手动干预。" in line:
                    continue
                latest_time = datetime.strptime(line[1:20], "%Y-%m-%d %H:%M:%S")
                break
            except ValueError:
                pass

        if self.mode == "Annihilation" and "任务出错: 刷理智" in log:
            self.run_book["IfAnnihilationAccomplish"] = True

        if "任务出错: StartUp" in log or "任务出错: 开始唤醒" in log:
            self.cur_user_item.log_record[self.log_start_time].status = (
                "MAA 未能正确登录 PRTS"
            )
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
                or (self.mode == "Annihilation" and "任务出错: 刷理智" in log)
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
                self.cur_user_log.status = "Success!"
            else:
                self.cur_user_log.status = "MAA 部分任务执行失败"
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
        elif datetime.now() - latest_time > timedelta(
            minutes=self.script_config.get("Run", f"{self.mode}TimeLimit")
        ):
            self.cur_user_log.status = "MAA 进程超时"
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
        if self.script_config.get("Run", "TaskTransitionMethod") == "ExitEmulator":
            logger.info("用户任务结束, 关闭模拟器")
            await self.emulator_manager.close(
                self.script_config.get("Emulator", "Index")
            )

        user_logs_list = []
        if_six_star = False
        for t, log_item in self.cur_user_item.log_record.items():

            if log_item.status == "MAA 正常运行中":
                log_item.status = "任务被用户手动中止"

            dt = t.replace(tzinfo=datetime.now().astimezone().tzinfo).astimezone(UTC4)
            log_path = (
                Path.cwd()
                / f"history/{dt.strftime('%Y-%m-%d')}/{self.cur_user_item.name}/{dt.strftime('%H-%M-%S')}.log"
            )
            user_logs_list.append(log_path.with_suffix(".json"))

            if await Config.save_maa_log(log_path, log_item.content, log_item.status):
                if_six_star = True

        if self.run_book["IfAnnihilationAccomplish"]:
            await self.cur_user_config.set("Data", "LastAnnihilationDate", self.curdate)

        statistics = await Config.merge_statistic_info(user_logs_list)
        statistics["user_info"] = self.cur_user_item.name
        statistics["start_time"] = self.user_start_time.strftime("%Y-%m-%d %H:%M:%S")
        statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        statistics["maa_result"] = (
            "代理任务全部完成"
            if (self.run_book["Annihilation"] and self.run_book["Routine"])
            else self.cur_user_item.result
        )

        # 判断是否成功
        if_success = self.run_book["Annihilation"] and self.run_book["Routine"]
        success_symbol = "√" if if_success else "X"

        try:
            if if_six_star:
                await push_notification(
                    "公招六星",
                    f"喜报: 用户 {self.cur_user_item.name} 公招出六星啦！",
                    {"user_name": self.cur_user_item.name},
                    self.cur_user_config,
                )
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

        if self.run_book["Annihilation"] and self.run_book["Routine"]:
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

            if self.cur_user_config.get("Info", "InfrastIndex") != "-1":
                await self.cur_user_config.set(
                    "Info",
                    "InfrastIndex",
                    str(
                        (int(self.cur_user_config.get("Info", "InfrastIndex")) + 1)
                        % len(
                            json.loads(
                                self.cur_user_config.get("Data", "CustomInfrast")
                            ).get("plans", [])
                        )
                    ),
                )

            self.cur_user_item.status = "完成"
            logger.success(f"用户 {self.cur_user_uid} 的自动代理任务已完成")
            await Notify.push_plyer(
                "成功完成一个自动代理任务！",
                f"已完成用户 {self.cur_user_item.name} 的自动代理任务",
                f"已完成 {self.cur_user_item.name} 的自动代理任务",
                3,
            )
        else:
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
