#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

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
from app.services import Notify, System
from app.utils import get_logger, LogMonitor, ProcessManager
from app.utils.constants import (
    UTC4,
    UTC8,
    MAA_TASKS,
    MAA_TASKS_ZH,
    MAA_STAGE_KEY,
    MAA_ANNIHILATION_FIGHT_BASE,
    MAA_REMAIN_FIGHT_BASE,
    ARKNIGHTS_PACKAGE_NAME,
    MAA_RUN_MOOD_BOOK,
    MAA_TASK_TRANSITION_METHOD_BOOK,
)
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
                / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile"
            ).exists()
        ):
            self.cur_user_item.status = "异常"
            return "未找到用户的 MAA 配置文件，请先在用户配置页完成 「MAA配置」 步骤"
        return "Pass"

    async def prepare(self):

        self.maa_process_manager = ProcessManager()
        self.maa_log_monitor = LogMonitor(
            (1, 20),
            "%Y-%m-%d %H:%M:%S",
            self.check_log,
            except_logs=["如果长时间无进一步日志更新，可能需要手动干预。"],
        )
        self.wait_event = asyncio.Event()
        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now()

        self.maa_root_path = Path(self.script_config.get("Info", "Path"))
        self.maa_set_path = self.maa_root_path / "config"
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
                    task: self.cur_user_config.get("Task", f"If{task}")
                    for task in MAA_TASKS
                }
            else:  # Annihilation
                self.task_dict = {
                    task: bool(task in ("StartUp", "Fight")) for task in MAA_TASKS
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
            shutil.copytree(
                (Path.cwd() / f"data/{self.script_info.script_id}/Default/ConfigFile"),
                self.maa_set_path,
                dirs_exist_ok=True,
            )
        elif self.cur_user_config.get("Info", "Mode") == "详细":
            shutil.copytree(
                (
                    Path.cwd()
                    / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile"
                ),
                self.maa_set_path,
                dirs_exist_ok=True,
            )

        gui_set = json.loads(
            (self.maa_set_path / "gui.json").read_text(encoding="utf-8")
        )
        gui_new_set = json.loads(
            (self.maa_set_path / "gui.new.json").read_text(encoding="utf-8")
        )

        # 多配置使用默认配置
        if gui_set["Current"] != "Default":
            gui_set["Configurations"]["Default"] = gui_set["Configurations"][
                gui_set["Current"]
            ]
            gui_new_set["Configurations"]["Default"] = gui_new_set["Configurations"][
                gui_set["Current"]
            ]
            gui_set["Current"] = "Default"

        # 各配置部分的引用
        global_set = gui_set["Global"]
        default_set = gui_set["Configurations"]["Default"]

        task_set = {}
        # 每个任务类型匹配第一个配置作为配置基础
        for task_type in MAA_TASKS:

            for task_item in gui_new_set["Configurations"]["Default"]["TaskQueue"]:
                if task_item.get("TaskType", "") == task_type:
                    task_set[task_type] = task_item
                    break
            else:
                task_set[task_type] = {
                    "$type": f"{task_type}Task",
                    "Name": f"{task_type} - 默认配置",
                    "IsEnable": False,
                    "TaskType": task_type,
                }

        # 关闭所有定时
        for i in range(1, 9):
            global_set[f"Timer.Timer{i}"] = "False"

        # 矫正 ADB 地址
        if emulator_info.adb_address != "Unknown":
            default_set["Connect.Address"] = emulator_info.adb_address

        # 任务间切换方式
        default_set["MainFunction.PostActions"] = MAA_TASK_TRANSITION_METHOD_BOOK[
            self.script_config.get("Run", "TaskTransitionMethod")
        ]

        # 直接运行任务
        default_set["Start.StartGame"] = "True"
        default_set["Start.RunDirectly"] = "True"
        default_set["Start.OpenEmulatorAfterLaunch"] = "False"

        # 更新配置
        global_set["VersionUpdate.ScheduledUpdateCheck"] = "False"
        global_set["VersionUpdate.AutoDownloadUpdatePackage"] = "True"
        global_set["VersionUpdate.AutoInstallUpdatePackage"] = "False"

        # 理智作战强制配置项
        task_set["Fight"]["IsDrGrandet"] = False
        task_set["Fight"]["HideSeries"] = False
        task_set["Fight"]["UseStoneAllowSave"] = False
        task_set["Fight"]["UseOptionalStage"] = True

        # 静默模式相关配置
        if Config.get("Function", "IfSilence"):
            global_set["GUI.UseTray"] = "True"
            global_set["GUI.MinimizeToTray"] = "True"
            global_set["Start.MinimizeDirectly"] = "True"

        # 服务器与账号切换
        default_set["Start.ClientType"] = self.cur_user_config.get("Info", "Server")
        if self.cur_user_config.get("Info", "Server") == "Official":
            task_set["StartUp"]["AccountName"] = (
                f"{self.cur_user_config.get('Info', 'Id')[:3]}****{self.cur_user_config.get('Info', 'Id')[7:]}"
                if len(self.cur_user_config.get("Info", "Id")) == 11
                else self.cur_user_config.get("Info", "Id")
            )
        elif self.cur_user_config.get("Info", "Server") == "Bilibili":
            task_set["StartUp"]["AccountName"] = self.cur_user_config.get("Info", "Id")

        # 加载关卡号配置
        if self.cur_user_config.get("Info", "StageMode") == "Fixed":
            plan_data = {
                stage_key: self.cur_user_config.get("Info", stage_key)
                for stage_key in MAA_STAGE_KEY
            }
        else:
            plan = Config.PlanConfig[
                uuid.UUID(self.cur_user_config.get("Info", "StageMode"))
            ]
            plan_data = {
                stage_key: plan.get_current_info(stage_key).getValue()
                for stage_key in MAA_STAGE_KEY
            }

        # 理智作战相关配置项
        if self.mode == "Annihilation":
            # 关卡配置
            task_set["Fight"] = MAA_ANNIHILATION_FIGHT_BASE.copy()
            task_set["Fight"]["UseMedicine"] = bool(
                plan_data.get("MedicineNumb", 0) != 0
            )
            task_set["Fight"]["MedicineCount"] = plan_data.get("MedicineNumb", 0)
            task_set["Fight"]["AnnihilationStage"] = self.cur_user_config.get(
                "Info", "Annihilation"
            )

        elif self.mode == "Routine":
            # 理智药配置
            task_set["Fight"]["UseMedicine"] = bool(
                plan_data.get("MedicineNumb", 0) != 0
            )
            task_set["Fight"]["MedicineCount"] = plan_data.get("MedicineNumb", 0)
            # 关卡配置
            task_set["Fight"]["Series"] = int(plan_data.get("SeriesNumb", "0"))
            task_set["Fight"]["StagePlan"] = [
                (
                    ""
                    if plan_data.get(stage_key, "-") == "*"
                    else plan_data.get(stage_key, "-")
                )
                for stage_key in ("Stage", "Stage_1", "Stage_2", "Stage_3")
                if plan_data.get(stage_key, "-") != "-"
            ]
            task_set["Fight"]["IsStageManually"] = True
            task_set["Fight"]["UseOptionalStage"] = True

            # 简洁模式下托管的配置
            if self.cur_user_config.get("Info", "Mode") == "简洁":
                task_set["Fight"]["EnableTimesLimit"] = False
                task_set["Fight"]["EnableTargetDrop"] = False

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
                    task_set["Infrast"]["Mode"] = "Custom"
                    task_set["Infrast"]["Filename"] = str(infrast_path)
                    task_set["Infrast"]["InfrastPlan"] = [
                        {
                            "Index": index,
                            "Name": infrast.get("name", f"第 {index + 1} 班"),
                            "Description": infrast.get("description", ""),
                            "DescriptionPost": infrast.get("description_post", ""),
                            "Period": infrast.get("period", []),
                        }
                        for index, infrast in enumerate(
                            json.loads(
                                self.cur_user_config.get("Data", "CustomInfrast")
                            ).get("plans", [])
                        )
                    ]
                    task_set["Infrast"]["PlanSelect"] = int(
                        self.cur_user_config.get("Info", "InfrastIndex")
                    )
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
                    task_set["Infrast"]["Mode"] = "Normal"
            else:
                task_set["Infrast"]["Mode"] = self.cur_user_config.get(
                    "Info", "InfrastMode"
                )

        # 导出任务配置
        self.task_dict["StartUp"] = True
        task_queue = gui_new_set["Configurations"]["Default"]["TaskQueue"] = []
        for task_type in MAA_TASKS:

            task_set[task_type]["IsEnable"] = self.task_dict[task_type]
            task_queue.append(task_set[task_type])

            # 剩余理智关卡配置
            if (
                self.mode == "Routine"
                and task_type == "Fight"
                and self.task_dict["Fight"]
                and plan_data.get("Stage_Remain", "-") != "-"
            ):
                remain_fight = MAA_REMAIN_FIGHT_BASE.copy()
                remain_fight["StagePlan"] = [
                    (
                        ""
                        if plan_data.get("Stage_Remain", "-") == "*"
                        else plan_data.get("Stage_Remain", "-")
                    )
                ]
                task_queue.append(remain_fight)

        (self.maa_set_path / "gui.json").write_text(
            json.dumps(gui_set, ensure_ascii=False, indent=4), encoding="utf-8"
        )
        (self.maa_set_path / "gui.new.json").write_text(
            json.dumps(gui_new_set, ensure_ascii=False, indent=4), encoding="utf-8"
        )

        logger.success(f"MAA运行参数配置完成: {self.mode}")

    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """日志回调"""

        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log

        if self.mode == "Annihilation" and "任务出错: 理智作战" in log:
            self.run_book["IfAnnihilationAccomplish"] = True

        if "未选择任务" in log:
            self.cur_user_log.status = "MAA 未选择任何任务"
        elif "任务出错: StartUp" in log or "任务出错: 开始唤醒" in log:
            self.cur_user_log.status = "MAA 未能正确登录 PRTS"
        elif "任务已全部完成！" in log:

            for en_task, zh_task in zip(MAA_TASKS, MAA_TASKS_ZH):

                if f"完成任务: {en_task}" in log or f"完成任务: {zh_task}" in log:
                    self.task_dict[en_task] = False
                if self.mode == "Annihilation" and "任务出错: 理智作战" in log:
                    self.task_dict["Fight"] = False

            if any(self.task_dict.values()):
                self.cur_user_log.status = "MAA 部分任务执行失败"
            else:
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
