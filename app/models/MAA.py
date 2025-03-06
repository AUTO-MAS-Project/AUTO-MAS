#   <AUTO_MAA:A MAA Multi Account Management and Automation Tool>
#   Copyright © <2024> <DLmaster361>

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

#   DLmaster_361@163.com

"""
AUTO_MAA
MAA功能组件
v4.2
作者：DLmaster_361
"""

from loguru import logger
from PySide6.QtCore import QObject, Signal, QEventLoop, QFileSystemWatcher, QTimer
import json
import sqlite3
from datetime import datetime, timedelta
import subprocess
import shutil
import time
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from typing import Union, List

from app.core import Config
from app.services import Notify, System


class MaaManager(QObject):
    """MAA控制器"""

    question = Signal(str, str)
    question_response = Signal(bool)
    update_user_info = Signal(list, list, list, list, list, list)
    push_info_bar = Signal(str, str, str, int)
    create_user_list = Signal(list)
    update_user_list = Signal(list)
    update_log_text = Signal(str)
    interrupt = Signal()
    accomplish = Signal(dict)

    isInterruptionRequested = False

    def __init__(
        self,
        mode: str,
        config_path: Path,
        user_config_path: Path = None,
    ):
        super(MaaManager, self).__init__()

        self.mode = mode
        self.config_path = config_path
        self.user_config_path = user_config_path
        self.log_monitor = QFileSystemWatcher()
        self.log_monitor_timer = QTimer()
        self.log_monitor_timer.timeout.connect(self.refresh_maa_log)
        self.monitor_loop = QEventLoop()

        self.interrupt.connect(self.quit_monitor)

        with (self.config_path / "config.json").open("r", encoding="utf-8") as f:
            self.set = json.load(f)

        if "设置MAA" not in self.mode:

            db = sqlite3.connect(self.config_path / "user_data.db")
            cur = db.cursor()
            cur.execute("SELECT * FROM adminx WHERE True")
            self.data = cur.fetchall()
            self.data = [list(row) for row in self.data]
            cur.close()
            db.close()

        else:
            self.data = []

    def configure(self):
        """提取配置信息"""

        self.name = self.set["MaaSet"]["Name"]
        self.maa_root_path = Path(self.set["MaaSet"]["Path"])
        self.maa_set_path = self.maa_root_path / "config/gui.json"
        self.maa_log_path = self.maa_root_path / "debug/gui.log"
        self.maa_exe_path = self.maa_root_path / "MAA.exe"
        self.maa_tasks_path = self.maa_root_path / "resource/tasks.json"

    def run(self):
        """主进程，运行MAA代理进程"""

        curdate = self.server_date()
        begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.configure()
        # 检查MAA路径是否可用
        if not self.maa_exe_path.exists() or not self.maa_set_path.exists():

            logger.error("未正确配置MAA路径，MAA代理进程中止")
            self.push_info_bar.emit(
                "error", "启动MAA代理进程失败", "您还未正确配置MAA路径！", -1
            )
            self.accomplish.emit(
                {
                    "Time": begin_time,
                    "History": "由于未正确配置MAA路径，MAA代理进程中止",
                }
            )
            return None

        # 整理用户数据，筛选需代理的用户
        if "设置MAA" not in self.mode:

            self.data = sorted(self.data, key=lambda x: (-len(x[15]), x[16]))
            self.user_list: List[List[str, str, int]] = [
                [_[0], "等待", index]
                for index, _ in enumerate(self.data)
                if (_[3] != 0 and _[4] == "y")
            ]
            self.create_user_list.emit(self.user_list)

        # 自动代理模式
        if self.mode == "自动代理":

            # 标记是否需要重启模拟器
            self.if_open_emulator = True
            # 执行情况预处理
            for _ in self.user_list:
                if self.data[_[2]][5] != curdate:
                    self.data[_[2]][5] = curdate
                    self.data[_[2]][14] = 0
                _[0] += f" - 第{self.data[_[2]][14] + 1}次代理"

            # 开始代理
            for user in self.user_list:

                if self.isInterruptionRequested:
                    break

                if (
                    self.set["RunSet"]["ProxyTimesLimit"] == 0
                    or self.data[user[2]][14] < self.set["RunSet"]["ProxyTimesLimit"]
                ):
                    user[1] = "运行"
                    self.update_user_list.emit(self.user_list)
                else:
                    user[1] = "跳过"
                    self.update_user_list.emit(self.user_list)
                    continue

                logger.info(f"{self.name} | 开始代理用户: {user[0]}")

                # 初始化代理情况记录和模式替换记录
                run_book = [False for _ in range(2)]
                mode_book = ["自动代理_剿灭", "自动代理_日常"]

                # 简洁模式用户默认开启日常选项
                if self.data[user[2]][15] == "simple":
                    self.data[user[2]][9] = "y"
                elif self.data[user[2]][15] == "beta":
                    check_book = [
                        [True, "annihilation", "剿灭"],
                        [True, "routine", "日常"],
                    ]

                user_logs_list = []
                user_start_time = datetime.now()

                # 尝试次数循环
                for i in range(self.set["RunSet"]["RunTimesLimit"]):

                    if self.isInterruptionRequested:
                        break

                    logger.info(
                        f"{self.name} | 用户: {user[0]} - 尝试次数: {i + 1}/{self.set["RunSet"]["RunTimesLimit"]}"
                    )

                    # 剿灭-日常模式循环
                    for j in range(2):

                        if self.isInterruptionRequested:
                            break

                        if self.data[user[2]][10 - j] == "n":
                            run_book[j] = True
                            continue
                        if run_book[j]:
                            continue

                        logger.info(
                            f"{self.name} | 用户: {user[0]} - 模式: {mode_book[j]}"
                        )

                        if self.data[user[2]][15] == "beta":

                            self.if_open_emulator = True

                            if (
                                check_book[j][0]
                                and not (
                                    self.config_path
                                    / f"beta/{self.data[user[2]][16]}/{check_book[j][1]}/gui.json"
                                ).exists()
                            ):
                                logger.error(
                                    f"{self.name} | 用户: {user[0]} - 未找到{check_book[j][2]}配置文件"
                                )
                                self.push_info_bar.emit(
                                    "error",
                                    "启动MAA代理进程失败",
                                    f"未找到{user[0]}的{check_book[j][2]}配置文件！",
                                    -1,
                                )
                                check_book[j][0] = False
                                continue
                            elif not check_book[j][0]:
                                continue

                        # 配置MAA
                        self.set_maa(mode_book[j], user[2])
                        # 记录当前时间
                        start_time = datetime.now()
                        # 创建MAA任务
                        maa = subprocess.Popen(
                            [self.maa_exe_path],
                            shell=True,
                            creationflags=subprocess.CREATE_NO_WINDOW,
                        )
                        # 添加静默进程标记
                        with self.maa_set_path.open(mode="r", encoding="utf-8") as f:
                            set = json.load(f)
                        self.emulator_path = Path(
                            set["Configurations"]["Default"]["Start.EmulatorPath"]
                        )
                        Config.silence_list.append(self.emulator_path)

                        # 监测MAA运行状态
                        self.start_monitor(start_time, mode_book[j])

                        if self.maa_result == "Success!":
                            logger.info(
                                f"{self.name} | 用户: {user[0]} - MAA进程完成代理任务"
                            )
                            run_book[j] = True
                            self.update_log_text.emit(
                                "检测到MAA进程完成代理任务\n正在等待相关程序结束\n请等待10s"
                            )
                            for _ in range(10):
                                if self.isInterruptionRequested:
                                    break
                                time.sleep(1)
                        else:
                            logger.error(
                                f"{self.name} | 用户: {user[0]} - 代理任务异常: {self.maa_result}"
                            )
                            # 打印中止信息
                            # 此时，log变量内存储的就是出现异常的日志信息，可以保存或发送用于问题排查
                            self.update_log_text.emit(
                                f"{self.maa_result}\n正在中止相关程序\n请等待10s"
                            )
                            # 无命令行中止MAA与其子程序
                            System.kill_process(self.maa_exe_path)
                            self.if_open_emulator = True
                            # 推送异常通知
                            Notify.push_plyer(
                                "用户自动代理出现异常！",
                                f"用户 {user[0].replace("_", " 今天的")}的{mode_book[j][5:7]}部分出现一次异常",
                                f"{user[0].replace("_", " ")}的{mode_book[j][5:7]}出现异常",
                                1,
                            )
                            for _ in range(10):
                                if self.isInterruptionRequested:
                                    break
                                time.sleep(1)

                        # 移除静默进程标记
                        Config.silence_list.remove(self.emulator_path)

                        # 保存运行日志以及统计信息
                        if_six_star = Config.save_maa_log(
                            Config.app_path
                            / f"history/{curdate}/{self.data[user[2]][0]}/{start_time.strftime("%H-%M-%S")}.log",
                            self.check_maa_log(start_time, mode_book[j]),
                            self.maa_result,
                        )
                        user_logs_list.append(
                            Config.app_path
                            / f"history/{curdate}/{self.data[user[2]][0]}/{start_time.strftime("%H-%M-%S")}.json",
                        )

                        if (
                            Config.global_config.get(
                                Config.global_config.notify_IfSendSixStar
                            )
                            and if_six_star
                        ):

                            self.push_notification(
                                "公招六星",
                                f"喜报：用户 {user[0]} 公招出六星啦！",
                                {"user_name": self.data[user[2]][0]},
                            )

                    # 成功完成代理的用户修改相关参数
                    if run_book[0] and run_book[1]:
                        if self.data[user[2]][14] == 0 and self.data[user[2]][3] != -1:
                            self.data[user[2]][3] -= 1
                        self.data[user[2]][14] += 1
                        user[1] = "完成"
                        Notify.push_plyer(
                            "成功完成一个自动代理任务！",
                            f"已完成用户 {user[0].replace("_", " 今天的")}任务",
                            f"已完成 {user[0].replace("_", " 的")}",
                            3,
                        )
                        break

                if Config.global_config.get(
                    Config.global_config.notify_IfSendStatistic
                ):

                    statistics = Config.merge_maa_logs("指定项", user_logs_list)
                    statistics["user_info"] = user[0]
                    statistics["start_time"] = user_start_time.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    statistics["end_time"] = datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    statistics["maa_result"] = (
                        "代理任务全部完成"
                        if (run_book[0] and run_book[1])
                        else "代理任务未全部完成"
                    )
                    self.push_notification(
                        "统计信息", f"用户 {user[0]} 的自动代理统计报告", statistics
                    )

                # 录入代理失败的用户
                if not (run_book[0] and run_book[1]):
                    user[1] = "异常"

                self.update_user_list.emit(self.user_list)

        # 人工排查模式
        elif self.mode == "人工排查":

            # 标记是否需要启动模拟器
            self.if_open_emulator = True
            # 标识排查模式
            for _ in self.user_list:
                _[0] += "_排查模式"

            # 开始排查
            for user in self.user_list:

                if self.isInterruptionRequested:
                    break

                logger.info(f"{self.name} | 开始排查用户: {user[0]}")

                user[1] = "运行"
                self.update_user_list.emit(self.user_list)

                if self.data[user[2]][15] == "beta":
                    self.if_open_emulator = True

                run_book = [False for _ in range(2)]

                # 启动重试循环
                while not self.isInterruptionRequested:

                    # 配置MAA
                    self.set_maa("人工排查", user[2])

                    # 记录当前时间
                    start_time = datetime.now()
                    # 创建MAA任务
                    maa = subprocess.Popen(
                        [self.maa_exe_path],
                        shell=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )

                    # 监测MAA运行状态
                    self.start_monitor(start_time, "人工排查")

                    if self.maa_result == "Success!":
                        logger.info(
                            f"{self.name} | 用户: {user[0]} - MAA进程成功登录PRTS"
                        )
                        run_book[0] = True
                        self.update_log_text.emit("检测到MAA进程成功登录PRTS")
                    else:
                        logger.error(
                            f"{self.name} | 用户: {user[0]} - MAA未能正确登录到PRTS: {self.maa_result}"
                        )
                        self.update_log_text.emit(
                            f"{self.maa_result}\n正在中止相关程序\n请等待10s"
                        )
                        # 无命令行中止MAA与其子程序
                        System.kill_process(self.maa_exe_path)
                        self.if_open_emulator = True
                        for _ in range(10):
                            if self.isInterruptionRequested:
                                break
                            time.sleep(1)

                    # 登录成功，结束循环
                    if run_book[0]:
                        break
                    # 登录失败，询问是否结束循环
                    elif not self.isInterruptionRequested:

                        if not self.push_question(
                            "操作提示", "MAA未能正确登录到PRTS，是否重试？"
                        ):
                            break

                # 登录成功，录入人工排查情况
                if run_book[0] and not self.isInterruptionRequested:

                    if self.push_question(
                        "操作提示", "请检查用户代理情况，该用户是否正确完成代理任务？"
                    ):
                        run_book[1] = True

                # 结果录入用户备注栏
                if run_book[0] and run_book[1]:
                    logger.info(f"{self.name} | 用户 {user[0]} 通过人工排查")
                    if "未通过人工排查" in self.data[user[2]][13]:
                        self.data[user[2]][13] = self.data[user[2]][13].replace(
                            "未通过人工排查|", ""
                        )
                    user[1] = "完成"
                else:
                    logger.info(f"{self.name} | 用户 {user[0]} 未通过人工排查")
                    if not "未通过人工排查" in self.data[user[2]][13]:
                        self.data[user[2]][
                            13
                        ] = f"未通过人工排查|{self.data[user[2]][13]}"
                    user[1] = "异常"

                self.update_user_list.emit(self.user_list)

        # 设置MAA模式
        elif "设置MAA" in self.mode:

            # 配置MAA
            self.set_maa(self.mode, "")
            # 创建MAA任务
            maa = subprocess.Popen(
                [self.maa_exe_path],
                shell=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            # 记录当前时间
            start_time = datetime.now()

            # 监测MAA运行状态
            self.start_monitor(start_time, "设置MAA")

            if "全局" in self.mode:
                (self.config_path / "Default").mkdir(parents=True, exist_ok=True)
                shutil.copy(self.maa_set_path, self.config_path / "Default")

            elif "用户" in self.mode:
                self.user_config_path.mkdir(parents=True, exist_ok=True)
                shutil.copy(self.maa_set_path, self.user_config_path)

            result_text = ""

        # 导出结果
        if self.mode in ["自动代理", "人工排查"]:

            # 关闭可能未正常退出的MAA进程
            if self.isInterruptionRequested:
                System.kill_process(self.maa_exe_path)

            # 更新用户数据
            modes = [self.data[_[2]][15] for _ in self.user_list]
            uids = [self.data[_[2]][16] for _ in self.user_list]
            days = [self.data[_[2]][3] for _ in self.user_list]
            lasts = [self.data[_[2]][5] for _ in self.user_list]
            notes = [self.data[_[2]][13] for _ in self.user_list]
            numbs = [self.data[_[2]][14] for _ in self.user_list]
            self.update_user_info.emit(modes, uids, days, lasts, notes, numbs)

            error_index = [_[2] for _ in self.user_list if _[1] == "异常"]
            over_index = [_[2] for _ in self.user_list if _[1] == "完成"]
            wait_index = [_[2] for _ in self.user_list if _[1] == "等待"]

            # 保存运行日志
            title = (
                f"{self.set["MaaSet"]["Name"]}的{self.mode[:4]}任务报告"
                if self.set["MaaSet"]["Name"] != ""
                else f"{self.mode[:4]}任务报告"
            )
            result = {
                "title": f"{self.mode[:4]}任务报告",
                "script_name": (
                    self.set["MaaSet"]["Name"]
                    if self.set["MaaSet"]["Name"] != ""
                    else "空白"
                ),
                "start_time": begin_time,
                "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "completed_count": len(over_index),
                "uncompleted_count": len(error_index) + len(wait_index),
                "failed_user": [self.data[_][0] for _ in error_index],
                "waiting_user": [self.data[_][0] for _ in wait_index],
            }
            # 推送代理结果通知
            Notify.push_plyer(
                title.replace("报告", "已完成！"),
                f"已完成用户数：{len(over_index)}，未完成用户数：{len(error_index) + len(wait_index)}",
                f"已完成用户数：{len(over_index)}，未完成用户数：{len(error_index) + len(wait_index)}",
                10,
            )
            if Config.global_config.get(
                Config.global_config.notify_SendTaskResultTime
            ) == "任何时刻" or (
                Config.global_config.get(Config.global_config.notify_SendTaskResultTime)
                == "仅失败时"
                and len(error_index) + len(wait_index) != 0
            ):
                result_text = self.push_notification("代理结果", title, result)
            else:
                result_text = self.push_notification(
                    "代理结果", title, result, if_get_text_only=True
                )

        self.agree_bilibili(False)
        self.log_monitor.deleteLater()
        self.log_monitor_timer.deleteLater()
        self.accomplish.emit({"Time": begin_time, "History": result_text})

    def requestInterruption(self) -> None:
        logger.info(f"{self.name} | 收到任务中止申请")

        if len(self.log_monitor.files()) != 0:
            self.interrupt.emit()

        self.maa_result = "任务被手动中止"
        self.isInterruptionRequested = True

    def push_question(self, title: str, message: str) -> bool:

        self.question.emit(title, message)
        loop = QEventLoop()
        self.question_response.connect(self._capture_response)
        self.question_response.connect(loop.quit)
        loop.exec()
        return self.response

    def _capture_response(self, response: bool) -> None:
        self.response = response

    def refresh_maa_log(self) -> None:
        """刷新MAA日志"""

        with self.maa_log_path.open(mode="r", encoding="utf-8") as f:
            pass

    def check_maa_log(self, start_time: datetime, mode: str) -> list:
        """获取MAA日志并检查以判断MAA程序运行状态"""

        # 获取日志
        logs = []
        if_log_start = False
        with self.maa_log_path.open(mode="r", encoding="utf-8") as f:
            for entry in f:
                if not if_log_start:
                    try:
                        entry_time = datetime.strptime(entry[1:20], "%Y-%m-%d %H:%M:%S")
                        if entry_time > start_time:
                            if_log_start = True
                            logs.append(entry)
                    except ValueError:
                        pass
                else:
                    logs.append(entry)
        log = "".join(logs)

        # 更新MAA日志
        if len(logs) > 100:
            self.update_log_text.emit("".join(logs[-100:]))
        else:
            self.update_log_text.emit("".join(logs))

        if "自动代理" in mode:

            # 获取最近一条日志的时间
            latest_time = start_time
            for _ in logs[::-1]:
                try:
                    latest_time = datetime.strptime(_[1:20], "%Y-%m-%d %H:%M:%S")
                    break
                except ValueError:
                    pass

            time_book = {
                "自动代理_剿灭": "AnnihilationTimeLimit",
                "自动代理_日常": "RoutineTimeLimit",
            }

            if mode == "自动代理_日常" and "任务出错: Fight" in log:
                self.maa_result = "检测到MAA未能实际执行任务"
            if "任务出错: StartUp" in log:
                self.maa_result = "检测到MAA未能正确登录PRTS"
            elif "任务已全部完成！" in log:
                self.maa_result = "Success!"
            elif (
                ("请「检查连接设置」或「尝试重启模拟器与 ADB」或「重启电脑」" in log)
                or ("未检测到任何模拟器" in log)
                or ("已停止" in log)
                or ("MaaAssistantArknights GUI exited" in log)
            ):
                self.maa_result = "检测到MAA进程异常"
            elif datetime.now() - latest_time > timedelta(
                minutes=self.set["RunSet"][time_book[mode]]
            ):
                self.maa_result = "检测到MAA进程超时"
            elif self.isInterruptionRequested:
                self.maa_result = "任务被手动中止"
            else:
                self.maa_result = "Wait"

        elif mode == "人工排查":
            if "完成任务: StartUp" in log:
                self.maa_result = "Success!"
            elif (
                ("请「检查连接设置」或「尝试重启模拟器与 ADB」或「重启电脑」" in log)
                or ("未检测到任何模拟器" in log)
                or ("已停止" in log)
                or ("MaaAssistantArknights GUI exited" in log)
            ):
                self.maa_result = "检测到MAA进程异常"
            elif self.isInterruptionRequested:
                self.maa_result = "任务被手动中止"
            else:
                self.maa_result = "Wait"

        elif mode == "设置MAA":
            if "MaaAssistantArknights GUI exited" in log:
                self.maa_result = "Success!"
            else:
                self.maa_result = "Wait"

        if self.maa_result != "Wait":

            self.quit_monitor()

        return logs

    def start_monitor(self, start_time: datetime, mode: str) -> None:
        """开始监视MAA日志"""

        logger.info(f"{self.name} | 开始监视MAA日志")
        self.log_monitor.addPath(str(self.maa_log_path))
        self.log_monitor.fileChanged.connect(
            lambda: self.check_maa_log(start_time, mode)
        )
        self.log_monitor_timer.start(1000)
        self.monitor_loop.exec()

    def quit_monitor(self) -> None:
        """退出MAA日志监视进程"""

        if len(self.log_monitor.files()) != 0:

            logger.info(f"{self.name} | 退出MAA日志监视")
            self.log_monitor.removePath(str(self.maa_log_path))
            self.log_monitor.fileChanged.disconnect()
            self.log_monitor_timer.stop()
            self.monitor_loop.quit()

    def set_maa(self, mode, index):
        """配置MAA运行参数"""
        logger.info(f"{self.name} | 配置MAA运行参数: {mode}/{index}")

        # 配置MAA前关闭可能未正常退出的MAA进程
        System.kill_process(self.maa_exe_path)

        # 预导入MAA配置文件
        if mode == "设置MAA_用户":
            if self.user_config_path.exists():
                shutil.copy(self.user_config_path / "gui.json", self.maa_set_path)
            else:
                shutil.copy(
                    self.config_path / "Default/gui.json",
                    self.maa_set_path,
                )
        elif (mode == "设置MAA_全局") or (
            ("自动代理" in mode or "人工排查" in mode)
            and self.data[index][15] == "simple"
        ):
            shutil.copy(
                self.config_path / "Default/gui.json",
                self.maa_set_path,
            )
        elif "自动代理" in mode and self.data[index][15] == "beta":
            if mode == "自动代理_剿灭":
                shutil.copy(
                    self.config_path
                    / f"beta/{self.data[index][16]}/annihilation/gui.json",
                    self.maa_set_path,
                )
            elif mode == "自动代理_日常":
                shutil.copy(
                    self.config_path / f"beta/{self.data[index][16]}/routine/gui.json",
                    self.maa_set_path,
                )
        elif "人工排查" in mode and self.data[index][15] == "beta":
            shutil.copy(
                self.config_path / f"beta/{self.data[index][16]}/routine/gui.json",
                self.maa_set_path,
            )
        with self.maa_set_path.open(mode="r", encoding="utf-8") as f:
            data = json.load(f)

        if "设置MAA" not in mode and (
            (self.data[index][15] == "simple" and self.data[index][2] == "Bilibili")
            or (
                self.data[index][15] == "beta"
                and data["Configurations"]["Default"]["Start.ClientType"] == "Bilibili"
            )
        ):
            self.agree_bilibili(True)
        else:
            self.agree_bilibili(False)

        # 自动代理配置
        if "自动代理" in mode:

            data["Current"] = "Default"  # 切换配置
            for i in range(1, 9):
                data["Global"][f"Timer.Timer{i}"] = "False"  # 时间设置

            if (
                [i for i, _ in enumerate(self.user_list) if _[2] == index][0]
                == len(self.user_list) - 1
            ) or (
                self.data[
                    self.user_list[
                        [i for i, _ in enumerate(self.user_list) if _[2] == index][0]
                        + 1
                    ][2]
                ][15]
                == "beta"
            ):
                data["Configurations"]["Default"][
                    "MainFunction.PostActions"
                ] = "12"  # 完成后退出MAA和模拟器
            else:
                method_dict = {"NoAction": "8", "ExitGame": "9", "ExitEmulator": "12"}
                data["Configurations"]["Default"]["MainFunction.PostActions"] = (
                    method_dict[self.set["RunSet"]["TaskTransitionMethod"]]
                )  # 完成后行为

            data["Configurations"]["Default"][
                "Start.RunDirectly"
            ] = "True"  # 启动MAA后直接运行
            data["Configurations"]["Default"]["Start.OpenEmulatorAfterLaunch"] = (
                "True" if self.if_open_emulator else "False"
            )  # 启动MAA后自动开启模拟器

            if Config.global_config.get(Config.global_config.function_IfSilence):
                data["Global"]["Start.MinimizeDirectly"] = "True"  # 启动MAA后直接最小化
                data["Global"]["GUI.UseTray"] = "True"  # 显示托盘图标
                data["Global"]["GUI.MinimizeToTray"] = "True"  # 最小化时隐藏至托盘

            if self.data[index][15] == "simple":

                data["Global"][
                    "VersionUpdate.ScheduledUpdateCheck"
                ] = "False"  # 定时检查更新
                data["Global"][
                    "VersionUpdate.AutoDownloadUpdatePackage"
                ] = "False"  # 自动下载更新包
                data["Global"][
                    "VersionUpdate.AutoInstallUpdatePackage"
                ] = "False"  # 自动安装更新包
                data["Configurations"]["Default"]["Start.ClientType"] = self.data[
                    index
                ][
                    2
                ]  # 客户端类型
                # 账号切换
                if self.data[index][2] == "Official":
                    data["Configurations"]["Default"]["Start.AccountName"] = (
                        f"{self.data[index][1][:3]}****{self.data[index][1][7:]}"
                        if len(self.data[index][1]) == 11
                        else self.data[index][1]
                    )
                elif self.data[index][2] == "Bilibili":
                    data["Configurations"]["Default"]["Start.AccountName"] = self.data[
                        index
                    ][1]

                if "剿灭" in mode:

                    data["Configurations"]["Default"][
                        "TaskQueue.WakeUp.IsChecked"
                    ] = "True"  # 开始唤醒
                    data["Configurations"]["Default"][
                        "TaskQueue.Recruiting.IsChecked"
                    ] = "False"  # 自动公招
                    data["Configurations"]["Default"][
                        "TaskQueue.Base.IsChecked"
                    ] = "False"  # 基建换班
                    data["Configurations"]["Default"][
                        "TaskQueue.Combat.IsChecked"
                    ] = "True"  # 刷理智
                    data["Configurations"]["Default"][
                        "TaskQueue.Mission.IsChecked"
                    ] = "False"  # 领取奖励
                    data["Configurations"]["Default"][
                        "TaskQueue.Mall.IsChecked"
                    ] = "False"  # 获取信用及购物
                    data["Configurations"]["Default"][
                        "TaskQueue.AutoRoguelike.IsChecked"
                    ] = "False"  # 自动肉鸽
                    data["Configurations"]["Default"][
                        "TaskQueue.Reclamation.IsChecked"
                    ] = "False"  # 生息演算
                    data["Configurations"]["Default"][
                        "MainFunction.Stage1"
                    ] = "Annihilation"  # 主关卡
                    data["Configurations"]["Default"][
                        "MainFunction.Stage2"
                    ] = ""  # 备选关卡1
                    data["Configurations"]["Default"][
                        "MainFunction.Stage3"
                    ] = ""  # 备选关卡2
                    data["Configurations"]["Default"][
                        "Fight.RemainingSanityStage"
                    ] = ""  # 剩余理智关卡
                    data["Configurations"]["Default"][
                        "MainFunction.Series.Quantity"
                    ] = "1"  # 连战次数
                    data["Configurations"]["Default"][
                        "Penguin.IsDrGrandet"
                    ] = "False"  # 博朗台模式
                    data["Configurations"]["Default"][
                        "GUI.CustomStageCode"
                    ] = "True"  # 手动输入关卡名
                    data["Configurations"]["Default"][
                        "GUI.UseAlternateStage"
                    ] = "False"  # 使用备选关卡
                    data["Configurations"]["Default"][
                        "Fight.UseRemainingSanityStage"
                    ] = "False"  # 使用剩余理智
                    data["Configurations"]["Default"][
                        "Fight.UseExpiringMedicine"
                    ] = "True"  # 无限吃48小时内过期的理智药
                    data["Configurations"]["Default"][
                        "GUI.HideSeries"
                    ] = "False"  # 隐藏连战次数

                elif "日常" in mode:

                    data["Configurations"]["Default"][
                        "TaskQueue.WakeUp.IsChecked"
                    ] = "True"  # 开始唤醒
                    data["Configurations"]["Default"][
                        "TaskQueue.Recruiting.IsChecked"
                    ] = "True"  # 自动公招
                    data["Configurations"]["Default"][
                        "TaskQueue.Base.IsChecked"
                    ] = "True"  # 基建换班
                    data["Configurations"]["Default"][
                        "TaskQueue.Combat.IsChecked"
                    ] = "True"  # 刷理智
                    data["Configurations"]["Default"][
                        "TaskQueue.Mission.IsChecked"
                    ] = "True"  # 领取奖励
                    data["Configurations"]["Default"][
                        "TaskQueue.Mall.IsChecked"
                    ] = "True"  # 获取信用及购物
                    data["Configurations"]["Default"][
                        "TaskQueue.AutoRoguelike.IsChecked"
                    ] = "False"  # 自动肉鸽
                    data["Configurations"]["Default"][
                        "TaskQueue.Reclamation.IsChecked"
                    ] = "False"  # 生息演算
                    # 主关卡
                    if self.data[index][6] == "-":
                        data["Configurations"]["Default"]["MainFunction.Stage1"] = ""
                    else:
                        data["Configurations"]["Default"]["MainFunction.Stage1"] = (
                            self.data[index][6]
                        )
                    # 备选关卡1
                    if self.data[index][7] == "-":
                        data["Configurations"]["Default"]["MainFunction.Stage2"] = ""
                    else:
                        data["Configurations"]["Default"]["MainFunction.Stage2"] = (
                            self.data[index][7]
                        )
                    # 备选关卡2
                    if self.data[index][8] == "-":
                        data["Configurations"]["Default"]["MainFunction.Stage3"] = ""
                    else:
                        data["Configurations"]["Default"]["MainFunction.Stage3"] = (
                            self.data[index][8]
                        )
                    data["Configurations"]["Default"][
                        "Fight.RemainingSanityStage"
                    ] = ""  # 剩余理智关卡
                    # 连战次数
                    if self.data[index][6] == "1-7":
                        data["Configurations"]["Default"][
                            "MainFunction.Series.Quantity"
                        ] = "6"
                    else:
                        data["Configurations"]["Default"][
                            "MainFunction.Series.Quantity"
                        ] = "1"
                    data["Configurations"]["Default"][
                        "Penguin.IsDrGrandet"
                    ] = "False"  # 博朗台模式
                    data["Configurations"]["Default"][
                        "GUI.CustomStageCode"
                    ] = "True"  # 手动输入关卡名
                    # 备选关卡
                    if self.data[index][7] == "-" and self.data[index][8] == "-":
                        data["Configurations"]["Default"][
                            "GUI.UseAlternateStage"
                        ] = "False"
                    else:
                        data["Configurations"]["Default"][
                            "GUI.UseAlternateStage"
                        ] = "True"
                    data["Configurations"]["Default"][
                        "Fight.UseRemainingSanityStage"
                    ] = "False"  # 使用剩余理智
                    data["Configurations"]["Default"][
                        "Fight.UseExpiringMedicine"
                    ] = "True"  # 无限吃48小时内过期的理智药
                    # 自定义基建配置
                    if self.data[index][11] == "n":
                        data["Configurations"]["Default"][
                            "Infrast.CustomInfrastEnabled"
                        ] = "False"  # 禁用自定义基建配置
                    else:
                        data["Configurations"]["Default"][
                            "Infrast.CustomInfrastEnabled"
                        ] = "True"  # 启用自定义基建配置
                        data["Configurations"]["Default"][
                            "Infrast.CustomInfrastPlanIndex"
                        ] = "1"  # 自定义基建配置索引
                        data["Configurations"]["Default"][
                            "Infrast.DefaultInfrast"
                        ] = "user_defined"  # 内置配置
                        data["Configurations"]["Default"][
                            "Infrast.IsCustomInfrastFileReadOnly"
                        ] = "False"  # 自定义基建配置文件只读
                        data["Configurations"]["Default"][
                            "Infrast.CustomInfrastFile"
                        ] = str(
                            self.config_path
                            / f"simple/{self.data[index][16]}/infrastructure/infrastructure.json"
                        )  # 自定义基建配置文件地址

        # 人工排查配置
        elif "人工排查" in mode:

            data["Current"] = "Default"  # 切换配置
            for i in range(1, 9):
                data["Global"][f"Timer.Timer{i}"] = "False"  # 时间设置
            data["Configurations"]["Default"][
                "MainFunction.PostActions"
            ] = "8"  # 完成后退出MAA
            data["Configurations"]["Default"][
                "Start.RunDirectly"
            ] = "True"  # 启动MAA后直接运行
            data["Global"]["Start.MinimizeDirectly"] = "True"  # 启动MAA后直接最小化
            # 启动MAA后直接运行
            data["Configurations"]["Default"]["Start.OpenEmulatorAfterLaunch"] = "True"
            # 启动MAA后自动开启模拟器
            data["Configurations"]["Default"]["Start.RunDirectly"] = "True"

            data["Global"]["GUI.UseTray"] = "True"  # 显示托盘图标
            data["Global"]["GUI.MinimizeToTray"] = "True"  # 最小化时隐藏至托盘
            data["Configurations"]["Default"]["Start.OpenEmulatorAfterLaunch"] = (
                "True" if self.if_open_emulator else "False"
            )  # 启动MAA后自动开启模拟器

            if self.data[index][15] == "simple":

                data["Global"][
                    "VersionUpdate.ScheduledUpdateCheck"
                ] = "False"  # 定时检查更新
                data["Global"][
                    "VersionUpdate.AutoDownloadUpdatePackage"
                ] = "False"  # 自动下载更新包
                data["Global"][
                    "VersionUpdate.AutoInstallUpdatePackage"
                ] = "False"  # 自动安装更新包
                data["Configurations"]["Default"]["Start.ClientType"] = self.data[
                    index
                ][
                    2
                ]  # 客户端类型
                # 账号切换
                if self.data[index][2] == "Official":
                    data["Configurations"]["Default"]["Start.AccountName"] = (
                        f"{self.data[index][1][:3]}****{self.data[index][1][7:]}"
                        if len(self.data[index][1]) == 11
                        else self.data[index][1]
                    )
                elif self.data[index][2] == "Bilibili":
                    data["Configurations"]["Default"]["Start.AccountName"] = self.data[
                        index
                    ][1]

            data["Configurations"]["Default"][
                "TaskQueue.WakeUp.IsChecked"
            ] = "True"  # 开始唤醒
            data["Configurations"]["Default"][
                "TaskQueue.Recruiting.IsChecked"
            ] = "False"  # 自动公招
            data["Configurations"]["Default"][
                "TaskQueue.Base.IsChecked"
            ] = "False"  # 基建换班
            data["Configurations"]["Default"][
                "TaskQueue.Combat.IsChecked"
            ] = "False"  # 刷理智
            data["Configurations"]["Default"][
                "TaskQueue.Mission.IsChecked"
            ] = "False"  # 领取奖励
            data["Configurations"]["Default"][
                "TaskQueue.Mall.IsChecked"
            ] = "False"  # 获取信用及购物
            data["Configurations"]["Default"][
                "TaskQueue.AutoRoguelike.IsChecked"
            ] = "False"  # 自动肉鸽
            data["Configurations"]["Default"][
                "TaskQueue.Reclamation.IsChecked"
            ] = "False"  # 生息演算

        # 设置MAA配置
        elif "设置MAA" in mode:

            data["Current"] = "Default"  # 切换配置
            for i in range(1, 9):
                data["Global"][f"Timer.Timer{i}"] = "False"  # 时间设置
            data["Configurations"]["Default"][
                "MainFunction.PostActions"
            ] = "0"  # 完成后无动作
            data["Configurations"]["Default"][
                "Start.RunDirectly"
            ] = "False"  # 启动MAA后直接运行
            data["Configurations"]["Default"][
                "Start.OpenEmulatorAfterLaunch"
            ] = "False"  # 启动MAA后自动开启模拟器

            if Config.global_config.get(Config.global_config.function_IfSilence):
                data["Global"][
                    "Start.MinimizeDirectly"
                ] = "False"  # 启动MAA后直接最小化

            if "全局" in mode:

                data["Global"][
                    "VersionUpdate.ScheduledUpdateCheck"
                ] = "False"  # 定时检查更新
                data["Global"][
                    "VersionUpdate.AutoDownloadUpdatePackage"
                ] = "False"  # 自动下载更新包
                data["Global"][
                    "VersionUpdate.AutoInstallUpdatePackage"
                ] = "False"  # 自动安装更新包
                data["Configurations"]["Default"][
                    "TaskQueue.WakeUp.IsChecked"
                ] = "False"  # 开始唤醒
                data["Configurations"]["Default"][
                    "TaskQueue.Recruiting.IsChecked"
                ] = "False"  # 自动公招
                data["Configurations"]["Default"][
                    "TaskQueue.Base.IsChecked"
                ] = "False"  # 基建换班
                data["Configurations"]["Default"][
                    "TaskQueue.Combat.IsChecked"
                ] = "False"  # 刷理智
                data["Configurations"]["Default"][
                    "TaskQueue.Mission.IsChecked"
                ] = "False"  # 领取奖励
                data["Configurations"]["Default"][
                    "TaskQueue.Mall.IsChecked"
                ] = "False"  # 获取信用及购物
                data["Configurations"]["Default"][
                    "TaskQueue.AutoRoguelike.IsChecked"
                ] = "False"  # 自动肉鸽
                data["Configurations"]["Default"][
                    "TaskQueue.Reclamation.IsChecked"
                ] = "False"  # 生息演算

        # 启动模拟器仅生效一次
        if (
            "设置MAA" not in mode
            and self.if_open_emulator
            and self.set["RunSet"]["TaskTransitionMethod"] != "ExitEmulator"
        ):
            self.if_open_emulator = False

        # 覆写配置文件
        with self.maa_set_path.open(mode="w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        return True

    def agree_bilibili(self, if_agree):
        """向MAA写入Bilibili协议相关任务"""
        logger.info(
            f"{self.name} | Bilibili协议相关任务状态: {"启用" if if_agree else "禁用"}"
        )

        with self.maa_tasks_path.open(mode="r", encoding="utf-8") as f:
            data = json.load(f)

        if if_agree and Config.global_config.get(
            Config.global_config.function_IfAgreeBilibili
        ):
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

    def get_emulator_path(self):
        """获取模拟器路径"""

        # 读取配置文件
        with self.maa_set_path.open(mode="r", encoding="utf-8") as f:
            set = json.load(f)
        # 获取模拟器路径
        return Path(set["Configurations"]["Default"]["Start.EmulatorPath"])

    def server_date(self):
        """获取当前的服务器日期"""

        dt = datetime.now()
        if dt.time() < datetime.min.time().replace(hour=4):
            dt = dt - timedelta(days=1)
        return dt.strftime("%Y-%m-%d")

    def push_notification(
        self,
        mode: str,
        title: str,
        message: Union[str, dict],
        if_get_text_only: bool = False,
    ) -> str:
        """通过所有渠道推送通知"""

        env = Environment(
            loader=FileSystemLoader(str(Config.app_path / "resources/html"))
        )

        if mode == "代理结果":

            # 生成文本通知内容
            message_text = (
                f"任务开始时间：{message["start_time"]}，结束时间：{message["end_time"]}\n"
                f"已完成数：{message["completed_count"]}，未完成数：{message["uncompleted_count"]}\n\n"
            )

            if len(message["failed_user"]) > 0:
                message_text += f"{self.mode[2:4]}未成功的用户：\n{"\n".join(message["failed_user"])}\n"
            if len(message["waiting_user"]) > 0:
                message_text += f"\n未开始{self.mode[2:4]}的用户：\n{"\n".join(message["waiting_user"])}\n"

            if if_get_text_only:
                return message_text

            # 生成HTML通知内容
            message["failed_user"] = "、".join(message["failed_user"])
            message["waiting_user"] = "、".join(message["waiting_user"])

            template = env.get_template("MAA_result.html")
            message_html = template.render(message)

            Notify.send_mail("网页", title, message_html)
            Notify.ServerChanPush(title, f"{message_text}\n\nAUTO_MAA 敬上")
            Notify.CompanyWebHookBotPush(title, f"{message_text}\n\nAUTO_MAA 敬上")

            return message_text

        elif mode == "统计信息":

            # 生成文本通知内容
            formatted = []
            for stage, items in message["drop_statistics"].items():
                formatted.append(f"掉落统计（{stage}）:")
                for item, quantity in items.items():
                    formatted.append(f"  {item}: {quantity}")
            drop_text = "\n".join(formatted)

            formatted = ["招募统计:"]
            for star, count in message["recruit_statistics"].items():
                formatted.append(f"  {star}: {count}")
            recruit_text = "\n".join(formatted)

            message_text = (
                f"开始时间: {message['start_time']}\n"
                f"结束时间: {message['end_time']}\n"
                f"MAA执行结果: {message['maa_result']}\n\n"
                f"{recruit_text}\n"
                f"{drop_text}"
            )

            # 生成HTML通知内容
            template = env.get_template("MAA_statistics.html")
            message_html = template.render(message)

            Notify.send_mail("网页", title, message_html)
            Notify.ServerChanPush(title, f"{message_text}\n\nAUTO_MAA 敬上")
            Notify.CompanyWebHookBotPush(title, f"{message_text}\n\nAUTO_MAA 敬上")

        elif mode == "公招六星":

            # 生成HTML通知内容
            template = env.get_template("MAA_six_star.html")
            message_html = template.render(message)

            Notify.send_mail("网页", title, message_html)
            Notify.ServerChanPush(title, "好羡慕~\n\nAUTO_MAA 敬上")
            Notify.CompanyWebHookBotPush(title, "好羡慕~\n\nAUTO_MAA 敬上")
