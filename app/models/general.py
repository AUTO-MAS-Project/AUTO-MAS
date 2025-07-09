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
通用功能组件
v4.3
作者：DLmaster_361
"""

from loguru import logger
from PySide6.QtCore import QObject, Signal, QEventLoop, QFileSystemWatcher, QTimer
import os
import sys
import shutil
import subprocess
from functools import partial
from datetime import datetime, timedelta
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from typing import Union, List, Dict

from app.core import Config, GeneralConfig, GeneralSubConfig
from app.services import Notify, System
from app.utils import ProcessManager


class GeneralManager(QObject):
    """通用脚本通用控制器"""

    question = Signal(str, str)
    question_response = Signal(bool)
    update_sub_info = Signal(str, dict)
    push_info_bar = Signal(str, str, str, int)
    play_sound = Signal(str)
    create_user_list = Signal(list)
    update_user_list = Signal(list)
    update_log_text = Signal(str)
    interrupt = Signal()
    accomplish = Signal(dict)

    def __init__(
        self,
        mode: str,
        config: Dict[
            str,
            Union[
                str,
                Path,
                GeneralConfig,
                Dict[str, Dict[str, Union[Path, GeneralSubConfig]]],
            ],
        ],
        sub_config_path: Path = None,
    ):
        super(GeneralManager, self).__init__()

        self.sub_list = []
        self.mode = mode
        self.config_path = config["Path"]
        self.sub_config_path = sub_config_path

        self.game_process_manager = ProcessManager()
        self.script_process_manager = ProcessManager()

        self.log_monitor = QFileSystemWatcher()
        self.log_monitor_timer = QTimer()
        self.log_monitor_timer.timeout.connect(self.refresh_log)
        self.monitor_loop = QEventLoop()

        self.script_process_manager.processClosed.connect(
            lambda: self.log_monitor.fileChanged.emit("进程结束检查")
        )

        self.question_loop = QEventLoop()
        self.question_response.connect(self.__capture_response)
        self.question_response.connect(self.question_loop.quit)

        self.wait_loop = QEventLoop()

        self.isInterruptionRequested = False
        self.interrupt.connect(self.quit_monitor)

        self.task_dict = {}
        self.set = config["Config"].toDict()

        self.data: Dict[str, Dict[str, Union[Path, dict]]] = {}
        if self.mode != "设置通用脚本":
            for name, info in config["SubData"].items():
                self.data[name] = {
                    "Path": info["Path"],
                    "Config": info["Config"].toDict(),
                }

            self.data = dict(sorted(self.data.items(), key=lambda x: int(x[0][3:])))

    def check_config_info(self) -> bool:
        """检查配置完整性"""

        if not (
            Path(self.set["Script"]["RootPath"]).exists()
            and Path(self.set["Script"]["ScriptPath"]).exists()
            and Path(self.set["Script"]["ConfigPath"]).exists()
            and Path(self.set["Script"]["LogPath"]).exists()
            and self.set["Script"]["LogTimeFormat"]
            and self.set["Script"]["ErrorLog"]
        ) or (
            self.set["Game"]["Enabled"] and not Path(self.set["Game"]["Path"]).exists()
        ):
            logger.error("脚本配置缺失")
            self.push_info_bar.emit("error", "脚本配置缺失", "请检查脚本配置！", -1)
            return False

        return True

    def configure(self):
        """提取配置信息"""

        self.name = self.set["Script"]["Name"]
        self.script_root_path = Path(self.set["Script"]["RootPath"])
        self.script_exe_path = Path(self.set["Script"]["ScriptPath"])
        self.script_config_path = Path(self.set["Script"]["ConfigPath"])
        self.script_log_path = Path(self.set["Script"]["LogPath"])
        self.game_path = Path(self.set["Game"]["Path"])
        self.log_time_range = [
            self.set["Script"]["LogTimeStart"],
            self.set["Script"]["LogTimeEnd"],
        ]
        self.success_log = [
            _.strip() for _ in self.set["Script"]["SuccessLog"].split("|")
        ]
        print(f"Success Log: {self.success_log}")
        self.error_log = [_.strip() for _ in self.set["Script"]["ErrorLog"].split("|")]

    def run(self):
        """主进程，运行通用脚本代理进程"""

        current_date = datetime.now().strftime("%m-%d")
        curdate = Config.server_date().strftime("%Y-%m-%d")
        begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 检查配置完整性
        if not self.check_config_info():

            self.accomplish.emit(
                {"Time": begin_time, "History": "由于配置不完整，通用代理进程中止"}
            )
            return None

        self.configure()

        # 整理用户数据，筛选需代理的用户
        if self.mode != "设置通用脚本":

            self.data = dict(sorted(self.data.items(), key=lambda x: int(x[0][3:])))
            self.sub_list: List[List[str, str, str]] = [
                [_["Config"]["Info"]["Name"], "等待", index]
                for index, _ in self.data.items()
                if (
                    _["Config"]["Info"]["RemainedDay"] != 0
                    and _["Config"]["Info"]["Status"]
                )
            ]
            self.create_user_list.emit(self.sub_list)

        # 自动代理模式
        if self.mode == "自动代理":

            # 执行情况预处理
            for _ in self.sub_list:
                if self.data[_[2]]["Config"]["Data"]["LastProxyDate"] != curdate:
                    self.data[_[2]]["Config"]["Data"]["LastProxyDate"] = curdate
                    self.data[_[2]]["Config"]["Data"]["ProxyTimes"] = 0
                _[
                    0
                ] += f" - 第{self.data[_[2]]['Config']['Data']['ProxyTimes'] + 1}次代理"

            # 开始代理
            for sub in self.sub_list:

                sub_data = self.data[sub[2]]["Config"]

                if self.isInterruptionRequested:
                    break

                if (
                    self.set["Run"]["ProxyTimesLimit"] == 0
                    or sub_data["Data"]["ProxyTimes"]
                    < self.set["Run"]["ProxyTimesLimit"]
                ):
                    sub[1] = "运行"
                    self.update_user_list.emit(self.sub_list)
                else:
                    sub[1] = "跳过"
                    self.update_user_list.emit(self.sub_list)
                    continue

                logger.info(f"{self.name} | 开始代理配置: {sub[0]}")

                sub_logs_list = []
                sub_start_time = datetime.now()

                run_book = False

                if not (self.data[sub[2]]["Path"] / "ConfigFiles").exists():
                    logger.error(f"{self.name} | 配置: {sub[0]} - 未找到配置文件")
                    self.push_info_bar.emit(
                        "error",
                        "启动通用代理进程失败",
                        f"未找到{sub[0]}的配置文件！",
                        -1,
                    )
                    run_book = False
                    continue

                # 尝试次数循环
                for i in range(self.set["Run"]["RunTimesLimit"]):

                    if self.isInterruptionRequested or run_book:
                        break

                    logger.info(
                        f"{self.name} | 用户: {sub[0]} - 尝试次数: {i + 1}/{self.set['Run']['RunTimesLimit']}"
                    )

                    # 记录当前时间
                    start_time = datetime.now()
                    # 配置脚本
                    self.set_sub(sub[2])
                    # 执行任务前脚本
                    if (
                        sub_data["Info"]["IfScriptBeforeTask"]
                        and Path(sub_data["Info"]["ScriptBeforeTask"]).exists()
                    ):
                        self.execute_script_task(
                            Path(sub_data["Info"]["ScriptBeforeTask"]), "脚本前任务"
                        )

                    # 启动游戏/模拟器
                    if self.set["Game"]["Enabled"]:

                        try:
                            logger.info(
                                f"{self.name} | 启动游戏/模拟器：{self.game_path}，参数：{self.set['Game']['Arguments']}"
                            )
                            self.game_process_manager.open_process(
                                self.game_path,
                                str(self.set["Game"]["Arguments"]).split(" "),
                                0,
                            )
                        except Exception as e:
                            logger.error(
                                f"{self.name} | 启动游戏/模拟器时出现异常：{e}"
                            )
                            self.push_info_bar.emit(
                                "error",
                                "启动游戏/模拟器时出现异常",
                                "请检查游戏/模拟器路径设置",
                                -1,
                            )
                            self.script_result = "游戏/模拟器启动失败"
                            break

                        # 添加静默进程标记
                        if self.set["Game"]["Style"] == "Emulator":
                            Config.silence_list.append(self.game_path)

                        self.update_log_text.emit(
                            f"正在等待游戏/模拟器完成启动\n请等待{self.set['Game']['WaitTime']}s"
                        )

                        self.sleep(self.set["Game"]["WaitTime"])

                        # 10s后移除静默进程标记
                        if self.set["Game"]["Style"] == "Emulator":
                            QTimer.singleShot(
                                10000,
                                partial(Config.silence_list.remove, self.game_path),
                            )

                    # 运行脚本任务
                    self.script_process_manager.open_process(
                        self.script_exe_path,
                        str(self.set["Script"]["Arguments"]).split(" "),
                    )

                    # 监测运行状态
                    self.start_monitor(start_time)

                    if self.script_result == "Success!":

                        # 标记任务完成
                        run_book = True

                        # 中止相关程序
                        self.script_process_manager.kill()
                        System.kill_process(self.script_exe_path)
                        if self.set["Game"]["Enabled"]:
                            self.game_process_manager.kill()
                            if self.set["Game"]["IfForceClose"]:
                                System.kill_process(self.game_path)

                        logger.info(
                            f"{self.name} | 配置: {sub[0]} - 通用脚本进程完成代理任务"
                        )
                        self.update_log_text.emit(
                            "检测到通用脚本进程完成代理任务\n正在等待相关程序结束\n请等待10s"
                        )

                        self.sleep(10)
                    else:
                        logger.error(
                            f"{self.name} | 配置: {sub[0]} - 代理任务异常: {self.script_result}"
                        )
                        # 打印中止信息
                        # 此时，log变量内存储的就是出现异常的日志信息，可以保存或发送用于问题排查
                        self.update_log_text.emit(
                            f"{self.script_result}\n正在中止相关程序\n请等待10s"
                        )

                        # 中止相关程序
                        self.script_process_manager.kill()
                        if self.set["Game"]["Enabled"]:
                            self.game_process_manager.kill()
                            if self.set["Game"]["IfForceClose"]:
                                System.kill_process(self.game_path)

                        # 推送异常通知
                        Notify.push_plyer(
                            "用户自动代理出现异常！",
                            f"用户 {sub[0].replace("_", " 今天的")}出现一次异常",
                            f"{sub[0].replace("_", " ")}出现异常",
                            1,
                        )
                        if i == self.set["Run"]["RunTimesLimit"] - 1:
                            self.play_sound.emit("子任务失败")
                        else:
                            self.play_sound.emit(self.script_result)
                        self.sleep(10)

                    # 执行任务后脚本
                    if (
                        sub_data["Info"]["IfScriptAfterTask"]
                        and Path(sub_data["Info"]["ScriptAfterTask"]).exists()
                    ):
                        self.execute_script_task(
                            Path(sub_data["Info"]["ScriptAfterTask"]), "脚本后任务"
                        )

                    # # 保存运行日志以及统计信息
                    # Config.save_maa_log(
                    #     Config.app_path
                    #     / f"history/{curdate}/{sub_data['Info']['Name']}/{start_time.strftime("%H-%M-%S")}.log",
                    #     self.check_script_log(start_time, mode_book[mode]),
                    #     self.maa_result,
                    # )
                    sub_logs_list.append(
                        Config.app_path
                        / f"history/{curdate}/{sub_data['Info']['Name']}/{start_time.strftime("%H-%M-%S")}.json",
                    )

                # 发送统计信息
                # statistics = Config.merge_maa_logs("指定项", sub_logs_list)
                statistics = {
                    "sub_index": sub[2],
                    "sub_info": sub[0],
                    "start_time": sub_start_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "sub_result": "代理成功" if run_book else self.script_result,
                }
                self.push_notification(
                    "统计信息",
                    f"{current_date} | 配置 {sub[0]} 的自动代理统计报告",
                    statistics,
                    sub_data,
                )

                if run_book:
                    # 成功完成代理的用户修改相关参数
                    if (
                        sub_data["Data"]["ProxyTimes"] == 0
                        and sub_data["Info"]["RemainedDay"] != -1
                    ):
                        sub_data["Info"]["RemainedDay"] -= 1
                    sub_data["Data"]["ProxyTimes"] += 1
                    sub[1] = "完成"
                    Notify.push_plyer(
                        "成功完成一个自动代理任务！",
                        f"已完成配置 {sub[0].replace("_", " 今天的")}任务",
                        f"已完成 {sub[0].replace("_", " 的")}",
                        3,
                    )
                else:
                    # 录入代理失败的用户
                    sub[1] = "异常"

                self.update_user_list.emit(self.sub_list)

        # 设置通用脚本模式
        elif self.mode == "设置通用脚本":

            # 配置通用脚本
            self.set_sub()

            try:
                # 创建通用脚本任务
                logger.info(f"{self.name} | 无参数启动通用脚本：{self.script_exe_path}")
                self.script_process_manager.open_process(self.script_exe_path)

                # 记录当前时间
                start_time = datetime.now()

                # 监测通用脚本运行状态
                self.start_monitor(start_time)

                self.sub_config_path.mkdir(parents=True, exist_ok=True)
                shutil.copytree(
                    self.script_config_path, self.sub_config_path, dirs_exist_ok=True
                )

            except Exception as e:
                logger.error(f"{self.name} | 启动通用脚本时出现异常：{e}")
                self.push_info_bar.emit(
                    "error",
                    "启动通用脚本时出现异常",
                    "请检查相关设置",
                    -1,
                )

            result_text = ""

        # 导出结果
        if self.mode in ["自动代理"]:

            # 关闭可能未正常退出的通用脚本进程
            if self.isInterruptionRequested:
                self.script_process_manager.kill(if_force=True)
                System.kill_process(self.script_exe_path)
                if self.set["Game"]["Enabled"]:
                    self.game_process_manager.kill(if_force=True)
                    if self.set["Game"]["IfForceClose"]:
                        System.kill_process(self.game_path)

            # 更新用户数据
            updated_info = {_[2]: self.data[_[2]] for _ in self.sub_list}
            self.update_sub_info.emit(self.config_path.name, updated_info)

            error_index = [_[2] for _ in self.sub_list if _[1] == "异常"]
            over_index = [_[2] for _ in self.sub_list if _[1] == "完成"]
            wait_index = [_[2] for _ in self.sub_list if _[1] == "等待"]

            # 保存运行日志
            title = (
                f"{current_date} | {self.name}的{self.mode[:4]}任务报告"
                if self.name != ""
                else f"{current_date} | {self.mode[:4]}任务报告"
            )
            result = {
                "title": f"{self.mode[:4]}任务报告",
                "script_name": (self.name if self.name != "" else "空白"),
                "start_time": begin_time,
                "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "completed_count": len(over_index),
                "uncompleted_count": len(error_index) + len(wait_index),
                "failed_sub": [
                    self.data[_]["Config"]["Info"]["Name"] for _ in error_index
                ],
                "waiting_sub": [
                    self.data[_]["Config"]["Info"]["Name"] for _ in wait_index
                ],
            }

            # 生成结果文本
            result_text = (
                f"任务开始时间：{result['start_time']}，结束时间：{result['end_time']}\n"
                f"已完成数：{result['completed_count']}，未完成数：{result['uncompleted_count']}\n\n"
            )
            if len(result["failed_sub"]) > 0:
                result_text += f"{self.mode[2:4]}未成功的配置：\n{"\n".join(result['failed_sub'])}\n"
            if len(result["waiting_sub"]) > 0:
                result_text += f"\n未开始{self.mode[2:4]}的配置：\n{"\n".join(result['waiting_sub'])}\n"

            # 推送代理结果通知
            Notify.push_plyer(
                title.replace("报告", "已完成！"),
                f"已完成配置数：{len(over_index)}，未完成配置数：{len(error_index) + len(wait_index)}",
                f"已完成配置数：{len(over_index)}，未完成配置数：{len(error_index) + len(wait_index)}",
                10,
            )
            self.push_notification("代理结果", title, result)

        self.log_monitor.deleteLater()
        self.log_monitor_timer.deleteLater()
        self.accomplish.emit({"Time": begin_time, "History": result_text})

    def requestInterruption(self) -> None:
        logger.info(f"{self.name} | 收到任务中止申请")

        if len(self.log_monitor.files()) != 0:
            self.interrupt.emit()

        self.script_result = "任务被手动中止"
        self.isInterruptionRequested = True
        self.wait_loop.quit()

    def push_question(self, title: str, message: str) -> bool:

        self.question.emit(title, message)
        self.question_loop.exec()
        return self.response

    def __capture_response(self, response: bool) -> None:
        self.response = response

    def sleep(self, time: int) -> None:
        """非阻塞型等待"""

        QTimer.singleShot(time * 1000, self.wait_loop.quit)
        self.wait_loop.exec()

    def refresh_log(self) -> None:
        """刷新脚本日志"""

        with self.script_log_path.open(mode="r", encoding="utf-8") as f:
            pass

        # 一分钟内未执行日志变化检查，强制检查一次
        if (datetime.now() - self.last_check_time).total_seconds() > 60:
            self.log_monitor.fileChanged.emit("1分钟超时检查")

    def strptime(
        self, date_string: str, format: str, default_date: datetime
    ) -> datetime:
        """根据指定格式解析日期字符串"""

        # 时间字段映射表
        time_fields = {
            "%Y": "year",
            "%m": "month",
            "%d": "day",
            "%H": "hour",
            "%M": "minute",
            "%S": "second",
            "%f": "microsecond",
        }

        date = datetime.strptime(date_string, format)

        # 构建参数字典
        datetime_kwargs = {}
        for format_code, field_name in time_fields.items():
            if format_code in format:
                datetime_kwargs[field_name] = getattr(date, field_name)
            else:
                datetime_kwargs[field_name] = getattr(default_date, field_name)

        return datetime(**datetime_kwargs)

    def check_script_log(self, start_time: datetime) -> list:
        """获取脚本日志并检查以判断脚本程序运行状态"""

        self.last_check_time = datetime.now()

        # 获取日志
        logs = []
        if_log_start = False
        with self.script_log_path.open(mode="r", encoding="utf-8") as f:
            for entry in f:
                if not if_log_start:
                    try:
                        entry_time = self.strptime(
                            entry[self.log_time_range[0] : self.log_time_range[1]],
                            self.set["Script"]["LogTimeFormat"],
                            self.last_check_time,
                        )

                        if entry_time > start_time:
                            if_log_start = True
                            logs.append(entry)
                    except ValueError:
                        pass
                else:
                    logs.append(entry)
        log = "".join(logs)

        # 更新日志
        if len(logs) > 100:
            self.update_log_text.emit("".join(logs[-100:]))
        else:
            self.update_log_text.emit("".join(logs))

        if "自动代理" in self.mode:

            # 获取最近一条日志的时间
            latest_time = start_time
            for _ in logs[::-1]:
                try:
                    latest_time = self.strptime(
                        _[self.log_time_range[0] : self.log_time_range[1]],
                        self.set["Script"]["LogTimeFormat"],
                        self.last_check_time,
                    )
                    break
                except ValueError:
                    pass

            for success_sign in self.success_log:
                if success_sign in log:
                    self.script_result = "Success!"
                    break
            else:

                if self.isInterruptionRequested:
                    self.script_result = "任务被手动中止"
                elif datetime.now() - latest_time > timedelta(
                    minutes=self.set["Run"]["RunTimeLimit"]
                ):
                    self.script_result = "脚本进程超时"
                else:
                    for error_sign in self.error_log:
                        if error_sign in log:
                            self.script_result = error_sign
                            break
                    else:
                        if self.script_process_manager.is_running():
                            self.script_result = "Wait"
                        elif self.success_log:
                            self.script_result = "脚本在完成任务前退出"
                        else:
                            self.script_result = "Success!"

        elif self.mode == "设置通用脚本":
            if self.script_process_manager.is_running():
                self.script_result = "Wait"
            else:
                self.script_result = "Success!"

        if self.script_result != "Wait":

            self.quit_monitor()

        return logs

    def start_monitor(self, start_time: datetime) -> None:
        """开始监视通用脚本日志"""

        logger.info(f"{self.name} | 开始监视通用脚本日志")
        self.log_monitor.addPath(str(self.script_log_path))
        self.log_monitor.fileChanged.connect(lambda: self.check_script_log(start_time))
        self.log_monitor_timer.start(1000)
        self.last_check_time = datetime.now()
        self.monitor_loop.exec()

    def quit_monitor(self) -> None:
        """退出通用脚本日志监视进程"""

        if len(self.log_monitor.files()) != 0:

            logger.info(f"{self.name} | 退出通用脚本日志监视")
            self.log_monitor.removePath(str(self.script_log_path))
            self.log_monitor.fileChanged.disconnect()
            self.log_monitor_timer.stop()
            self.last_check_time = None
            self.monitor_loop.quit()

    def set_sub(self, index: str = "") -> dict:
        """配置通用脚本运行参数"""
        logger.info(f"{self.name} | 配置脚本运行参数: {index}")

        # 配置前关闭可能未正常退出的脚本进程
        System.kill_process(self.script_exe_path)

        # 预导入配置文件
        if self.mode == "设置通用脚本":
            if self.sub_config_path.exists():
                shutil.copytree(
                    self.sub_config_path, self.script_config_path, dirs_exist_ok=True
                )
        else:
            shutil.copytree(
                self.data[index]["Path"] / "ConfigFiles",
                self.script_config_path,
                dirs_exist_ok=True,
            )

    def execute_script_task(self, script_path: Path, task_name: str) -> bool:
        """执行脚本任务并等待结束"""

        try:
            logger.info(f"{self.name} | 开始执行{task_name}: {script_path}")

            # 根据文件类型选择执行方式
            if script_path.suffix.lower() == ".py":
                cmd = [sys.executable, script_path]
            elif script_path.suffix.lower() in [".bat", ".cmd", ".exe"]:
                cmd = [str(script_path)]
            elif script_path.suffix.lower() == "":
                logger.warning(f"{self.name} | {task_name}脚本没有指定后缀名，无法执行")
                return False
            else:
                # 使用系统默认程序打开
                os.startfile(str(script_path))
                return True

            # 执行脚本并等待结束
            result = subprocess.run(
                cmd,
                cwd=script_path.parent,
                stdin=subprocess.DEVNULL,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW
                    if Config.get(Config.function_IfSilence)
                    else 0
                ),
                timeout=600,
                capture_output=True,
                errors="ignore",
            )

            if result.returncode == 0:
                logger.info(f"{self.name} | {task_name}执行成功")
                if result.stdout.strip():
                    logger.info(f"{self.name} | {task_name}输出: {result.stdout}")
                return True
            else:
                logger.error(
                    f"{self.name} | {task_name}执行失败，返回码: {result.returncode}"
                )
                if result.stderr.strip():
                    logger.error(f"{self.name} | {task_name}错误输出: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"{self.name} | {task_name}执行超时")
            return False
        except Exception as e:
            logger.exception(f"{self.name} | 执行{task_name}时出现异常: {e}")
            return False

    def push_notification(
        self,
        mode: str,
        title: str,
        message: Union[str, dict],
        sub_data: Dict[str, Dict[str, Union[str, int, bool]]] = None,
    ) -> None:
        """通过所有渠道推送通知"""

        env = Environment(
            loader=FileSystemLoader(str(Config.app_path / "resources/html"))
        )

        if mode == "代理结果" and (
            Config.get(Config.notify_SendTaskResultTime) == "任何时刻"
            or (
                Config.get(Config.notify_SendTaskResultTime) == "仅失败时"
                and message["uncompleted_count"] != 0
            )
        ):
            # 生成文本通知内容
            message_text = (
                f"任务开始时间：{message['start_time']}，结束时间：{message['end_time']}\n"
                f"已完成数：{message['completed_count']}，未完成数：{message['uncompleted_count']}\n\n"
            )

            if len(message["failed_sub"]) > 0:
                message_text += f"{self.mode[2:4]}未成功的配置：\n{"\n".join(message['failed_sub'])}\n"
            if len(message["waiting_sub"]) > 0:
                message_text += f"\n未开始{self.mode[2:4]}的配置：\n{"\n".join(message['waiting_sub'])}\n"

            # 生成HTML通知内容
            message["failed_sub"] = "、".join(message["failed_sub"])
            message["waiting_sub"] = "、".join(message["waiting_sub"])

            template = env.get_template("general_result.html")
            message_html = template.render(message)

            # ServerChan的换行是两个换行符。故而将\n替换为\n\n
            serverchan_message = message_text.replace("\n", "\n\n")

            # 发送全局通知

            if Config.get(Config.notify_IfSendMail):
                Notify.send_mail(
                    "网页", title, message_html, Config.get(Config.notify_ToAddress)
                )

            if Config.get(Config.notify_IfServerChan):
                Notify.ServerChanPush(
                    title,
                    f"{serverchan_message}\n\nAUTO_MAA 敬上",
                    Config.get(Config.notify_ServerChanKey),
                    Config.get(Config.notify_ServerChanTag),
                    Config.get(Config.notify_ServerChanChannel),
                )

            if Config.get(Config.notify_IfCompanyWebHookBot):
                Notify.CompanyWebHookBotPush(
                    title,
                    f"{message_text}\n\nAUTO_MAA 敬上",
                    Config.get(Config.notify_CompanyWebHookBotUrl),
                )

        elif mode == "统计信息":

            message_text = (
                f"开始时间: {message['start_time']}\n"
                f"结束时间: {message['end_time']}\n"
                f"通用脚本执行结果: {message['sub_result']}\n\n"
            )

            # 生成HTML通知内容
            template = env.get_template("general_statistics.html")
            message_html = template.render(message)

            # ServerChan的换行是两个换行符。故而将\n替换为\n\n
            serverchan_message = message_text.replace("\n", "\n\n")

            # 发送全局通知
            if Config.get(Config.notify_IfSendStatistic):

                if Config.get(Config.notify_IfSendMail):
                    Notify.send_mail(
                        "网页", title, message_html, Config.get(Config.notify_ToAddress)
                    )

                if Config.get(Config.notify_IfServerChan):
                    Notify.ServerChanPush(
                        title,
                        f"{serverchan_message}\n\nAUTO_MAA 敬上",
                        Config.get(Config.notify_ServerChanKey),
                        Config.get(Config.notify_ServerChanTag),
                        Config.get(Config.notify_ServerChanChannel),
                    )

                if Config.get(Config.notify_IfCompanyWebHookBot):
                    Notify.CompanyWebHookBotPush(
                        title,
                        f"{message_text}\n\nAUTO_MAA 敬上",
                        Config.get(Config.notify_CompanyWebHookBotUrl),
                    )

            # 发送用户单独通知
            if sub_data["Notify"]["Enabled"] and sub_data["Notify"]["IfSendStatistic"]:

                # 发送邮件通知
                if sub_data["Notify"]["IfSendMail"]:
                    if sub_data["Notify"]["ToAddress"]:
                        Notify.send_mail(
                            "网页",
                            title,
                            message_html,
                            sub_data["Notify"]["ToAddress"],
                        )
                    else:
                        logger.error(
                            f"{self.name} | 用户邮箱地址为空，无法发送用户单独的邮件通知"
                        )

                # 发送ServerChan通知
                if sub_data["Notify"]["IfServerChan"]:
                    if sub_data["Notify"]["ServerChanKey"]:
                        Notify.ServerChanPush(
                            title,
                            f"{serverchan_message}\n\nAUTO_MAA 敬上",
                            sub_data["Notify"]["ServerChanKey"],
                            sub_data["Notify"]["ServerChanTag"],
                            sub_data["Notify"]["ServerChanChannel"],
                        )
                    else:
                        logger.error(
                            f"{self.name} |用户ServerChan密钥为空，无法发送用户单独的ServerChan通知"
                        )

                # 推送CompanyWebHookBot通知
                if sub_data["Notify"]["IfCompanyWebHookBot"]:
                    if sub_data["Notify"]["CompanyWebHookBotUrl"]:
                        Notify.CompanyWebHookBotPush(
                            title,
                            f"{message_text}\n\nAUTO_MAA 敬上",
                            sub_data["Notify"]["CompanyWebHookBotUrl"],
                        )
                    else:
                        logger.error(
                            f"{self.name} |用户CompanyWebHookBot密钥为空，无法发送用户单独的CompanyWebHookBot通知"
                        )

        return None
