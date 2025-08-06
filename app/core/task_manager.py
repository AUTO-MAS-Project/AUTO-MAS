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


import uuid
from datetime import datetime
from packaging import version
from typing import Dict, Union

from .config import Config, MaaConfig, GeneralConfig
from utils import get_logger
from task import *


logger = get_logger("业务调度")


class Task:
    """业务线程"""

    check_maa_version = Signal(str)
    push_info_bar = Signal(str, str, str, int)
    play_sound = Signal(str)
    question = Signal(str, str)
    question_response = Signal(bool)
    update_maa_user_info = Signal(str, dict)
    update_general_sub_info = Signal(str, dict)
    create_task_list = Signal(list)
    create_user_list = Signal(list)
    update_task_list = Signal(list)
    update_user_list = Signal(list)
    update_log_text = Signal(str)
    accomplish = Signal(list)

    def __init__(
        self, mode: str, name: str, info: Dict[str, Dict[str, Union[str, int, bool]]]
    ):
        super(Task, self).__init__()

        self.setObjectName(f"Task-{mode}-{name}")

        self.mode = mode
        self.name = name
        self.info = info

        self.logs = []

        self.question_response.connect(lambda: print("response"))

    @logger.catch
    def run(self):

        if "设置MAA" in self.mode:

            logger.info(f"任务开始：设置{self.name}", module=f"业务 {self.name}")
            self.push_info_bar.emit("info", "设置MAA", self.name, 3000)

            self.task = MaaManager(
                self.mode,
                Config.script_dict[self.name],
                (None if "全局" in self.mode else self.info["SetMaaInfo"]["Path"]),
            )
            self.task.check_maa_version.connect(self.check_maa_version.emit)
            self.task.push_info_bar.connect(self.push_info_bar.emit)
            self.task.play_sound.connect(self.play_sound.emit)
            self.task.accomplish.connect(lambda: self.accomplish.emit([]))

            try:
                self.task.run()
            except Exception as e:
                logger.exception(
                    f"任务异常：{self.name}，错误信息：{e}", module=f"业务 {self.name}"
                )
                self.push_info_bar.emit("error", "任务异常", self.name, -1)

        elif self.mode == "设置通用脚本":

            logger.info(f"任务开始：设置{self.name}", module=f"业务 {self.name}")
            self.push_info_bar.emit("info", "设置通用脚本", self.name, 3000)

            self.task = GeneralManager(
                self.mode,
                Config.script_dict[self.name],
                self.info["SetSubInfo"]["Path"],
            )
            self.task.push_info_bar.connect(self.push_info_bar.emit)
            self.task.play_sound.connect(self.play_sound.emit)
            self.task.accomplish.connect(lambda: self.accomplish.emit([]))

            try:
                self.task.run()
            except Exception as e:
                logger.exception(
                    f"任务异常：{self.name}，错误信息：{e}", module=f"业务 {self.name}"
                )
                self.push_info_bar.emit("error", "任务异常", self.name, -1)

        else:

            logger.info(f"任务开始：{self.name}", module=f"业务 {self.name}")
            self.task_list = [
                [
                    (
                        value
                        if Config.script_dict[value]["Config"].get_name() == ""
                        else f"{value} - {Config.script_dict[value]["Config"].get_name()}"
                    ),
                    "等待",
                    value,
                ]
                for _, value in sorted(
                    self.info["Queue"].items(), key=lambda x: int(x[0][7:])
                )
                if value != "禁用"
            ]

            self.create_task_list.emit(self.task_list)

            for task in self.task_list:

                if self.isInterruptionRequested():
                    break

                task[1] = "运行"
                self.update_task_list.emit(self.task_list)

                # 检查任务是否在运行列表中
                if task[2] in Config.running_list:

                    task[1] = "跳过"
                    self.update_task_list.emit(self.task_list)
                    logger.info(
                        f"跳过任务：{task[0]}，该任务已在运行列表中",
                        module=f"业务 {self.name}",
                    )
                    self.push_info_bar.emit("info", "跳过任务", task[0], 3000)
                    continue

                # 标记为运行中
                Config.running_list.append(task[2])
                logger.info(f"任务开始：{task[0]}", module=f"业务 {self.name}")
                self.push_info_bar.emit("info", "任务开始", task[0], 3000)

                if Config.script_dict[task[2]]["Type"] == "Maa":

                    self.task = MaaManager(
                        self.mode[0:4],
                        Config.script_dict[task[2]],
                    )

                    self.task.check_maa_version.connect(self.check_maa_version.emit)
                    self.task.question.connect(self.question.emit)
                    self.question_response.disconnect()
                    self.question_response.connect(self.task.question_response.emit)
                    self.task.push_info_bar.connect(self.push_info_bar.emit)
                    self.task.play_sound.connect(self.play_sound.emit)
                    self.task.create_user_list.connect(self.create_user_list.emit)
                    self.task.update_user_list.connect(self.update_user_list.emit)
                    self.task.update_log_text.connect(self.update_log_text.emit)
                    self.task.update_user_info.connect(self.update_maa_user_info.emit)
                    self.task.accomplish.connect(
                        lambda log: self.task_accomplish(task[2], log)
                    )

                elif Config.script_dict[task[2]]["Type"] == "General":

                    self.task = GeneralManager(
                        self.mode[0:4],
                        Config.script_dict[task[2]],
                    )

                    self.task.question.connect(self.question.emit)
                    self.question_response.disconnect()
                    self.question_response.connect(self.task.question_response.emit)
                    self.task.push_info_bar.connect(self.push_info_bar.emit)
                    self.task.play_sound.connect(self.play_sound.emit)
                    self.task.create_user_list.connect(self.create_user_list.emit)
                    self.task.update_user_list.connect(self.update_user_list.emit)
                    self.task.update_log_text.connect(self.update_log_text.emit)
                    self.task.update_sub_info.connect(self.update_general_sub_info.emit)
                    self.task.accomplish.connect(
                        lambda log: self.task_accomplish(task[2], log)
                    )

                try:
                    self.task.run()  # 运行任务业务

                    task[1] = "完成"
                    self.update_task_list.emit(self.task_list)
                    logger.info(f"任务完成：{task[0]}", module=f"业务 {self.name}")
                    self.push_info_bar.emit("info", "任务完成", task[0], 3000)

                except Exception as e:

                    self.task_accomplish(
                        task[2],
                        {
                            "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "History": f"任务异常，异常简报：{e}",
                        },
                    )

                    task[1] = "异常"
                    self.update_task_list.emit(self.task_list)
                    logger.exception(
                        f"任务异常：{task[0]}，错误信息：{e}",
                        module=f"业务 {self.name}",
                    )
                    self.push_info_bar.emit("error", "任务异常", task[0], -1)

                # 任务结束后从运行列表中移除
                Config.running_list.remove(task[2])

            self.accomplish.emit(self.logs)

    def task_accomplish(self, name: str, log: dict):
        """
        销毁任务线程并保存任务结果

        :param name: 任务名称
        :param log: 任务日志记录
        """

        logger.info(
            f"任务完成：{name}，日志记录：{list(log.values())}",
            module=f"业务 {self.name}",
        )

        self.logs.append([name, log])
        self.task.deleteLater()


class _TaskManager:
    """业务调度器"""

    def __init__(self):
        super(_TaskManager, self).__init__()

        self.task_dict: Dict[str, Task] = {}

    def add_task(self, mode: str, uid: str):
        """
        添加任务

        :param mode: 任务模式
        :param uid: 任务UID
        """

        actual_id = uuid.UUID(uid)

        if mode == "设置脚本":
            if actual_id in Config.ScriptConfig:
                task_id = actual_id
            else:
                for script_id, script in Config.ScriptConfig.items():
                    if (
                        isinstance(script, (MaaConfig | GeneralConfig))
                        and actual_id in script.UserData
                    ):
                        task_id = script_id
                        break
                else:
                    raise ValueError(
                        f"The task corresponding to UID {uid} could not be found."
                    )
        elif actual_id in Config.QueueConfig or actual_id in Config.ScriptConfig:
            task_id = actual_id
        else:
            raise ValueError(f"The task corresponding to UID {uid} could not be found.")

        if name in Config.running_list or name in self.task_dict:

            logger.warning(f"任务已存在：{name}")
            MainInfoBar.push_info_bar("warning", "任务已存在", name, 5000)
            return None

        logger.info(f"任务开始：{name}，模式：{mode}", module="业务调度")
        MainInfoBar.push_info_bar("info", "任务开始", name, 3000)
        SoundPlayer.play("任务开始")

        # 标记任务为运行中
        Config.running_list.append(name)

        # 创建任务实例并连接信号
        self.task_dict[name] = Task(mode, name, info)
        self.task_dict[name].check_maa_version.connect(self.check_maa_version)
        self.task_dict[name].question.connect(
            lambda title, content: self.push_dialog(name, title, content)
        )
        self.task_dict[name].push_info_bar.connect(MainInfoBar.push_info_bar)
        self.task_dict[name].play_sound.connect(SoundPlayer.play)
        self.task_dict[name].update_maa_user_info.connect(Config.change_maa_user_info)
        self.task_dict[name].update_general_sub_info.connect(
            Config.change_general_sub_info
        )
        self.task_dict[name].accomplish.connect(
            lambda logs: self.remove_task(mode, name, logs)
        )

        # 向UI发送信号以创建或连接GUI
        if "新调度台" in mode:
            self.create_gui.emit(self.task_dict[name])

        elif "主调度台" in mode:
            self.connect_gui.emit(self.task_dict[name])

        # 启动任务线程
        self.task_dict[name].start()

    def stop_task(self, name: str) -> None:
        """
        中止任务

        :param name: 任务名称
        """

        logger.info(f"中止任务：{name}", module="业务调度")
        MainInfoBar.push_info_bar("info", "中止任务", name, 3000)

        if name == "ALL":

            for name in self.task_dict:

                self.task_dict[name].task.requestInterruption()
                self.task_dict[name].requestInterruption()
                self.task_dict[name].quit()
                self.task_dict[name].wait()

        elif name in self.task_dict:

            self.task_dict[name].task.requestInterruption()
            self.task_dict[name].requestInterruption()
            self.task_dict[name].quit()
            self.task_dict[name].wait()

    def remove_task(self, mode: str, name: str, logs: list) -> None:
        """
        处理任务结束后的收尾工作

        :param mode: 任务模式
        :param name: 任务名称
        :param logs: 任务日志
        """

        logger.info(f"任务结束：{name}", module="业务调度")
        MainInfoBar.push_info_bar("info", "任务结束", name, 3000)
        SoundPlayer.play("任务结束")

        # 删除任务线程，移除运行中标记
        self.task_dict[name].deleteLater()
        self.task_dict.pop(name)
        Config.running_list.remove(name)

        if "调度队列" in name and "人工排查" not in mode:

            # 保存调度队列历史记录
            if len(logs) > 0:
                time = logs[0][1]["Time"]
                history = ""
                for log in logs:
                    history += f"任务名称：{log[0]}，{log[1]["History"].replace("\n","\n    ")}\n"
                Config.save_history(name, {"Time": time, "History": history})
            else:
                Config.save_history(
                    name,
                    {
                        "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "History": "没有任务被执行",
                    },
                )

            # 根据调度队列情况设置电源状态
            if (
                Config.queue_dict[name]["Config"].get(
                    Config.queue_dict[name]["Config"].QueueSet_AfterAccomplish
                )
                != "NoAction"
                and Config.power_sign == "NoAction"
            ):
                Config.set_power_sign(
                    Config.queue_dict[name]["Config"].get(
                        Config.queue_dict[name]["Config"].QueueSet_AfterAccomplish
                    )
                )

        if Config.args.mode == "cli" and Config.power_sign == "NoAction":
            Config.set_power_sign("KillSelf")


TaskManager = _TaskManager()
