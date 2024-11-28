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
AUTO_MAA主程序
v4.1
作者：DLmaster_361
"""

from PySide6.QtWidgets import (
    QWidget,
    QMainWindow,
    QApplication,
    QSystemTrayIcon,
    QMenu,
    QInputDialog,
    QFileDialog,
    QMessageBox,
    QLineEdit,
    QTabWidget,
    QToolBox,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
    QPushButton,
    QHeaderView,
    QSpinBox,
    QTimeEdit,
    QCheckBox,
    QTextBrowser,
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtGui import QIcon, QCloseEvent
from PySide6 import QtCore
from functools import partial
from plyer import notification
import sqlite3
import json
import datetime
import os
import sys
import ctypes
import hashlib
import subprocess
import shutil
import time
import random
import secrets
import winreg
import requests
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
from Crypto.Cipher import AES
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from Crypto.Util.Padding import pad, unpad

import Updater

uiLoader = QUiLoader()


class MaaRunner(QtCore.QThread):

    question = QtCore.Signal()
    push_notification = QtCore.Signal(str, str, str, int)
    send_mail = QtCore.Signal(str, str)
    update_gui = QtCore.Signal(str, str, str, str, str)
    update_user_info = QtCore.Signal(list, list, list, list, list, list)
    accomplish = QtCore.Signal()
    get_json = QtCore.Signal(list)
    app_path = os.path.dirname(os.path.realpath(sys.argv[0])).replace(
        "\\", "/"
    )  # 获取软件自身的路径

    def __init__(self):
        super(MaaRunner, self).__init__()

        self.config = None
        self.data = None
        self.mode = None
        self.get_json_path = [0, 0, 0]

    def configure(self):
        """提取配置信息"""

        self.set_path = f"{self.config["Default"]["MaaSet.path"]}/config/gui.json"
        self.log_path = f"{self.config["Default"]["MaaSet.path"]}/debug/gui.log"
        self.maa_path = f"{self.config["Default"]["MaaSet.path"]}/MAA.exe"
        self.json_path = f"{self.app_path}/data/MAAconfig"
        self.routine = self.config["Default"]["TimeLimit.routine"]
        self.annihilation = self.config["Default"]["TimeLimit.annihilation"]
        self.num = self.config["Default"]["TimesLimit.run"]
        self.if_send_mail = bool(self.config["Default"]["SelfSet.IfSendMail"] == "True")

    def run(self):
        """主进程，运行MAA代理进程"""

        curdate = server_date()
        begin_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.configure()

        # 整理用户数据，筛选需代理的用户
        self.data = sorted(self.data, key=lambda x: (-len(x[15]), x[16]))
        wait_index = []
        over_index = []
        error_index = []
        all_index = [
            _
            for _ in range(len(self.data))
            if (self.data[_][3] != 0 and self.data[_][4] == "y")
        ]

        # 日常代理模式
        if self.mode == "日常代理":

            # 执行情况预处理
            for _ in all_index:
                if self.data[_][5] != curdate:
                    self.data[_][5] = curdate
                    self.data[_][14] = 0
                self.data[_][0] += f"_第{str(self.data[_][14] + 1)}次代理"

            # 开始代理
            for index in all_index:

                if self.isInterruptionRequested():
                    break

                # 初始化代理情况记录和模式替换记录
                run_book = [False for _ in range(2)]
                mode_book = ["日常代理_剿灭", "日常代理_日常"]

                # 尝试次数循环
                for i in range(self.num):

                    if self.isInterruptionRequested():
                        break

                    # 剿灭-日常模式循环
                    for j in range(2):

                        if self.isInterruptionRequested():
                            break

                        if j == 0 and self.data[index][10] == "n":
                            run_book[0] = True
                            continue
                        if run_book[j]:
                            continue

                        # 配置MAA
                        self.set_maa(mode_book[j], index)
                        # 记录当前时间
                        start_time = datetime.datetime.now()
                        # 创建MAA任务
                        maa = subprocess.Popen([self.maa_path])
                        # 记录是否超时的标记
                        self.if_time_out = False
                        # 更新运行信息
                        wait_index = [
                            _
                            for _ in all_index
                            if (not _ in over_index + error_index + [index])
                        ]

                        # 监测MAA运行状态
                        while not self.isInterruptionRequested():

                            # 获取MAA日志
                            logs = self.get_maa_log(start_time)

                            # 判断是否超时
                            if len(logs) > 0:
                                last_time = datetime.datetime.now()
                                for _ in range(-1, 0 - len(logs) - 1, -1):
                                    try:
                                        last_time = datetime.datetime.strptime(
                                            logs[_][1:20], "%Y-%m-%d %H:%M:%S"
                                        )
                                        break
                                    except ValueError:
                                        pass
                                now_time = datetime.datetime.now()
                                if (
                                    j == 0
                                    and now_time - last_time
                                    > datetime.timedelta(minutes=self.annihilation)
                                ) or (
                                    j == 1
                                    and now_time - last_time
                                    > datetime.timedelta(minutes=self.routine)
                                ):
                                    self.if_time_out = True

                            # 合并日志
                            log = "".join(logs)

                            # 更新MAA日志
                            if len(logs) > 100:
                                self.update_gui.emit(
                                    f"{self.data[index][0]}_第{i + 1}次_{mode_book[j][5:7]}",
                                    "\n".join([self.data[_][0] for _ in wait_index]),
                                    "\n".join([self.data[_][0] for _ in over_index]),
                                    "\n".join([self.data[_][0] for _ in error_index]),
                                    "".join(logs[-100:]),
                                )
                            else:
                                self.update_gui.emit(
                                    f"{self.data[index][0]}_第{i + 1}次_{mode_book[j][5:7]}",
                                    "\n".join([self.data[_][0] for _ in wait_index]),
                                    "\n".join([self.data[_][0] for _ in over_index]),
                                    "\n".join([self.data[_][0] for _ in error_index]),
                                    "".join(logs),
                                )

                            # 判断MAA程序运行状态
                            result = self.if_maa_success(log, mode_book[j])
                            if result == "Success!":
                                run_book[j] = True
                                self.update_gui.emit(
                                    f"{self.data[index][0]}_第{i + 1}次_{mode_book[j][5:7]}",
                                    "\n".join([self.data[_][0] for _ in wait_index]),
                                    "\n".join([self.data[_][0] for _ in over_index]),
                                    "\n".join([self.data[_][0] for _ in error_index]),
                                    "检测到MAA进程完成代理任务\n正在等待相关程序结束\n请等待10s",
                                )
                                time.sleep(10)
                                break
                            elif result == "Wait":
                                # 检测时间间隔
                                time.sleep(1)
                            else:
                                # 打印中止信息
                                # 此时，log变量内存储的就是出现异常的日志信息，可以保存或发送用于问题排查
                                self.update_gui.emit(
                                    f"{self.data[index][0]}_第{i + 1}次_{mode_book[j][5:7]}",
                                    "\n".join([self.data[_][0] for _ in wait_index]),
                                    "\n".join([self.data[_][0] for _ in over_index]),
                                    "\n".join([self.data[_][0] for _ in error_index]),
                                    result,
                                )
                                # 无命令行中止MAA与其子程序
                                killprocess = subprocess.Popen(
                                    f"taskkill /F /T /PID {maa.pid}",
                                    shell=True,
                                    creationflags=subprocess.CREATE_NO_WINDOW,
                                )
                                killprocess.wait()
                                # 推送异常通知
                                self.push_notification.emit(
                                    "用户日常代理出现异常！",
                                    f"用户 {self.data[index][0].replace("_", " 今天的")}的{mode_book[j][5:7]}部分出现一次异常",
                                    f"{self.data[index][0].replace("_", " ")}的{mode_book[j][5:7]}出现异常",
                                    1,
                                )
                                if not self.isInterruptionRequested():
                                    time.sleep(10)
                                break

                    # 成功完成代理的用户修改相关参数
                    if run_book[0] and run_book[1]:
                        if self.data[index][14] == 0 and self.data[index][3] != -1:
                            self.data[index][3] -= 1
                        self.data[index][14] += 1
                        over_index.append(index)
                        self.push_notification.emit(
                            "成功完成一个日常代理任务！",
                            f"已完成用户 {self.data[index][0].replace("_", " 今天的")}任务",
                            f"已完成 {self.data[index][0].replace("_", " 的")}",
                            3,
                        )
                        break

                # 录入代理失败的用户
                if not (run_book[0] and run_book[1]):
                    error_index.append(index)

        # 人工排查模式
        elif self.mode == "人工排查":

            # 标记是否需要启动模拟器
            if_strat_app = True
            # 标识排查模式
            for _ in all_index:
                self.data[_][0] += "_排查模式"

            # 开始排查
            for index in all_index:

                if self.isInterruptionRequested():
                    break

                if self.data[index][15] == "beta":
                    if_strat_app = True

                run_book = [False for _ in range(2)]

                # 启动重试循环
                while not self.isInterruptionRequested():

                    # 配置MAA
                    if if_strat_app:
                        self.set_maa("人工排查_启动模拟器", index)
                        if_strat_app = False
                    else:
                        self.set_maa("人工排查_仅切换账号", index)

                    # 记录当前时间
                    start_time = datetime.datetime.now()
                    # 创建MAA任务
                    maa = subprocess.Popen([self.maa_path])
                    # 更新运行信息
                    wait_index = [
                        _
                        for _ in all_index
                        if (not _ in over_index + error_index + [index])
                    ]

                    # 监测MAA运行状态
                    while not self.isInterruptionRequested():

                        # 获取MAA日志
                        logs = self.get_maa_log(start_time)
                        # 合并日志
                        log = "".join(logs)

                        # 更新MAA日志
                        if len(logs) > 100:
                            self.update_gui.emit(
                                self.data[index][0],
                                "\n".join([self.data[_][0] for _ in wait_index]),
                                "\n".join([self.data[_][0] for _ in over_index]),
                                "\n".join([self.data[_][0] for _ in error_index]),
                                "".join(logs[-100:]),
                            )
                        else:
                            self.update_gui.emit(
                                self.data[index][0],
                                "\n".join([self.data[_][0] for _ in wait_index]),
                                "\n".join([self.data[_][0] for _ in over_index]),
                                "\n".join([self.data[_][0] for _ in error_index]),
                                "".join(logs),
                            )

                        # 判断MAA程序运行状态
                        result = self.if_maa_success(log, "人工排查")
                        if result == "Success!":
                            run_book[0] = True
                            self.update_gui.emit(
                                self.data[index][0],
                                "\n".join([self.data[_][0] for _ in wait_index]),
                                "\n".join([self.data[_][0] for _ in over_index]),
                                "\n".join([self.data[_][0] for _ in error_index]),
                                "检测到MAA进程成功登录PRTS",
                            )
                            break
                        elif result == "Wait":
                            # 检测时间间隔
                            time.sleep(1)
                        else:
                            self.update_gui.emit(
                                self.data[index][0],
                                "\n".join([self.data[_][0] for _ in wait_index]),
                                "\n".join([self.data[_][0] for _ in over_index]),
                                "\n".join([self.data[_][0] for _ in error_index]),
                                result,
                            )
                            # 无命令行中止MAA与其子程序
                            killprocess = subprocess.Popen(
                                f"taskkill /F /T /PID {maa.pid}",
                                shell=True,
                                creationflags=subprocess.CREATE_NO_WINDOW,
                            )
                            killprocess.wait()
                            if_strat_app = True
                            if not self.isInterruptionRequested():
                                time.sleep(10)
                            break

                    # 登录成功，结束循环
                    if run_book[0]:
                        break
                    # 登录失败，询问是否结束循环
                    elif not self.isInterruptionRequested():
                        self.question_title = "操作提示"
                        self.question_info = "MAA未能正确登录到PRTS，是否重试？"
                        self.question_choice = "wait"
                        self.question.emit()
                        while self.question_choice == "wait":
                            time.sleep(1)
                        if self.question_choice == "No":
                            break

                # 登录成功，录入人工排查情况
                if run_book[0] and not self.isInterruptionRequested():
                    self.question_title = "操作提示"
                    self.question_info = "请检查用户代理情况，如无异常请按下确认键。"
                    self.question_choice = "wait"
                    self.question.emit()
                    while self.question_choice == "wait":
                        time.sleep(1)
                    if self.question_choice == "Yes":
                        run_book[1] = True

                # 结果录入用户备注栏
                if run_book[0] and run_book[1]:
                    if "未通过人工排查" in self.data[index][13]:
                        self.data[index][13] = self.data[index][13].replace(
                            "未通过人工排查|", ""
                        )
                    over_index.append(index)
                elif not (run_book[0] and run_book[1]):
                    if not "未通过人工排查" in self.data[index][13]:
                        self.data[index][13] = f"未通过人工排查|{self.data[index][13]}"
                    error_index.append(index)

        # 设置MAA模式
        elif "设置MAA" in self.mode:

            # 配置MAA
            self.set_maa(self.mode, "")
            # 创建MAA任务
            maa = subprocess.Popen([self.maa_path])
            # 记录当前时间
            start_time = datetime.datetime.now()

            # 监测MAA运行状态
            while not self.isInterruptionRequested():

                # 获取MAA日志
                logs = self.get_maa_log(start_time)
                # 合并日志
                log = "".join(logs)

                # 判断MAA程序运行状态
                result = self.if_maa_success(log, "设置MAA")
                if result == "Success!":
                    break
                elif result == "Wait":
                    # 检测时间间隔
                    time.sleep(1)

            # 保存MAA配置文件
            if "全局" in self.mode:
                self.get_json.emit(["Default"])
            elif "用户" in self.mode:
                self.get_json.emit(self.get_json_path)

            self.accomplish.emit()

        # 导出结果
        if self.mode in ["日常代理", "人工排查"]:

            # 关闭可能未正常退出的MAA进程
            if self.isInterruptionRequested():
                killprocess = subprocess.Popen(
                    f"taskkill /F /T /PID {maa.pid}",
                    shell=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                killprocess.wait()

            # 更新用户数据
            modes = [self.data[_][15] for _ in all_index]
            uids = [self.data[_][16] for _ in all_index]
            days = [self.data[_][3] for _ in all_index]
            lasts = [self.data[_][5] for _ in all_index]
            notes = [self.data[_][13] for _ in all_index]
            numbs = [self.data[_][14] for _ in all_index]
            self.update_user_info.emit(modes, uids, days, lasts, notes, numbs)

            # 保存运行日志
            end_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(f"{self.app_path}/log.txt", "w", encoding="utf-8") as f:
                print(f"任务开始时间：{begin_time}，结束时间：{end_time}", file=f)
                print(
                    f"已完成数：{len(over_index)}，未完成数：{len(error_index) + len(wait_index)}\n",
                    file=f,
                )
                if len(error_index) != 0:
                    print(f"{self.mode[2:4]}未成功的用户：", file=f)
                    print("\n".join([self.data[_][0] for _ in error_index]), file=f)
                wait_index = [
                    _ for _ in all_index if (not _ in over_index + error_index)
                ]
                if len(wait_index) != 0:
                    print(f"\n未开始{self.mode[2:4]}的用户：", file=f)
                    print("\n".join([self.data[_][0] for _ in wait_index]), file=f)

            # 恢复GUI运行面板
            with open(f"{self.app_path}/log.txt", "r", encoding="utf-8") as f:
                end_log = f.read()
            self.update_gui.emit("", "", "", "", end_log)

            # 推送代理结果通知
            self.push_notification.emit(
                f"{self.mode[2:4]}任务已完成！",
                f"已完成用户数：{len(over_index)}，未完成用户数：{len(error_index) + len(wait_index)}",
                f"已完成用户数：{len(over_index)}，未完成用户数：{len(error_index) + len(wait_index)}",
                10,
            )
            if self.if_send_mail:
                self.send_mail.emit(
                    f"{self.mode[:4]}任务报告",
                    f"{end_log}\n\nAUTO_MAA 敬上\n\n我们根据您在 AUTO_MAA 中的设置发送了这封电子邮件，本邮件无需回复\n",
                )

            self.accomplish.emit()

    def get_maa_log(self, start_time):
        """获取MAA日志"""

        logs = []
        if_log_start = False
        with open(self.log_path, "r", encoding="utf-8") as f:
            for entry in f:
                if not if_log_start:
                    try:
                        entry_time = datetime.datetime.strptime(
                            entry[1:20], "%Y-%m-%d %H:%M:%S"
                        )
                        if entry_time > start_time:
                            if_log_start = True
                            logs.append(entry)
                    except ValueError:
                        pass
                else:
                    logs.append(entry)
        return logs

    def if_maa_success(self, log, mode):
        """判断MAA程序运行状态"""

        if "日常代理" in mode:
            if mode == "日常代理_日常" and "任务出错: Fight" in log:
                return "检测到MAA未能实际执行任务\n正在中止相关程序\n请等待10s"
            if "任务出错: StartUp" in log:
                return "检测到MAA未能正确登录PRTS\n正在中止相关程序\n请等待10s"
            elif "任务已全部完成！" in log:
                return "Success!"
            elif (
                ("请「检查连接设置」或「尝试重启模拟器与 ADB」或「重启电脑」" in log)
                or ("已停止" in log)
                or ("MaaAssistantArknights GUI exited" in log)
            ):
                return "检测到MAA进程异常\n正在中止相关程序\n请等待10s"
            elif self.if_time_out:
                return "检测到MAA进程超时\n正在中止相关程序\n请等待10s"
            elif self.isInterruptionRequested():
                return "您中止了本次任务\n正在中止相关程序\n请等待"
            else:
                return "Wait"

        elif mode == "人工排查":
            if "完成任务: StartUp" in log:
                return "Success!"
            elif (
                ("请「检查连接设置」或「尝试重启模拟器与 ADB」或「重启电脑」" in log)
                or ("已停止" in log)
                or ("MaaAssistantArknights GUI exited" in log)
            ):
                return "检测到MAA进程异常\n正在中止相关程序\n请等待10s"
            elif self.isInterruptionRequested():
                return "您中止了本次任务\n正在中止相关程序\n请等待"
            else:
                return "Wait"

        elif mode == "设置MAA":
            if "MaaAssistantArknights GUI exited" in log:
                return "Success!"
            else:
                return "Wait"

    def set_maa(self, mode, index):
        """配置MAA运行参数"""

        # 预导入MAA配置文件
        if mode == "设置MAA_用户":
            set_book1 = ["simple", "beta"]
            set_book2 = ["routine", "annihilation"]
            shutil.copy(
                f"{self.json_path}/{set_book1[self.get_json_path[0]]}/{self.get_json_path[1]}/{set_book2[self.get_json_path[2]]}/gui.json",
                self.set_path,
            )
        elif (mode == "设置MAA_全局") or (
            ("日常代理" in mode or "人工排查" in mode)
            and self.data[index][15] == "simple"
        ):
            shutil.copy(
                f"{self.json_path}/Default/gui.json",
                self.set_path,
            )
        elif "日常代理" in mode and self.data[index][15] == "beta":
            if mode == "日常代理_剿灭":
                shutil.copy(
                    f"{self.json_path}/beta/{self.data[index][16]}/annihilation/gui.json",
                    self.set_path,
                )
            elif mode == "日常代理_日常":
                shutil.copy(
                    f"{self.json_path}/beta/{self.data[index][16]}/routine/gui.json",
                    self.set_path,
                )
        elif "人工排查" in mode and self.data[index][15] == "beta":
            shutil.copy(
                f"{self.json_path}/beta/{self.data[index][16]}/routine/gui.json",
                self.set_path,
            )
        with open(self.set_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 人工排查配置
        if "人工排查" in mode:

            data["Current"] = "Default"  # 切换配置
            for i in range(1, 9):
                data["Global"][f"Timer.Timer{i}"] = "False"  # 时间设置
            data["Configurations"]["Default"][
                "MainFunction.PostActions"
            ] = "8"  # 完成后退出MAA
            data["Configurations"]["Default"][
                "Start.RunDirectly"
            ] = "True"  # 启动MAA后直接运行
            data["Configurations"]["Default"][
                "Start.MinimizeDirectly"
            ] = "True"  # 启动MAA后直接最小化
            # 启动MAA后自动开启模拟器
            if "启动模拟器" in mode:
                data["Configurations"]["Default"][
                    "Start.OpenEmulatorAfterLaunch"
                ] = "True"
            elif "仅切换账号" in mode:
                data["Configurations"]["Default"][
                    "Start.OpenEmulatorAfterLaunch"
                ] = "False"
            data["Configurations"]["Default"][
                "Start.MinimizingStartup"
            ] = "False"  # 最小化启动模拟器

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
                    data["Configurations"]["Default"][
                        "Start.AccountName"
                    ] = f"{self.data[index][1][:3]}****{self.data[index][1][7:]}"
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

        # 剿灭代理配置
        elif mode == "日常代理_剿灭":

            data["Current"] = "Default"  # 切换配置
            for i in range(1, 9):
                data["Global"][f"Timer.Timer{i}"] = "False"  # 时间设置
            data["Configurations"]["Default"][
                "MainFunction.PostActions"
            ] = "12"  # 完成后退出MAA和模拟器
            data["Configurations"]["Default"][
                "Start.RunDirectly"
            ] = "True"  # 启动MAA后直接运行
            data["Configurations"]["Default"][
                "Start.OpenEmulatorAfterLaunch"
            ] = "True"  # 启动MAA后自动开启模拟器

            if self.data[index][15] == "simple":

                data["Global"][
                    "VersionUpdate.ScheduledUpdateCheck"
                ] = "True"  # 定时检查更新
                data["Global"][
                    "VersionUpdate.AutoDownloadUpdatePackage"
                ] = "True"  # 自动下载更新包
                data["Global"][
                    "VersionUpdate.AutoInstallUpdatePackage"
                ] = "True"  # 自动安装更新包
                data["Configurations"]["Default"]["Start.ClientType"] = self.data[
                    index
                ][
                    2
                ]  # 客户端类型
                # 账号切换
                if self.data[index][2] == "Official":
                    data["Configurations"]["Default"][
                        "Start.AccountName"
                    ] = f"{self.data[index][1][:3]}****{self.data[index][1][7:]}"
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

        # 日常代理配置
        elif mode == "日常代理_日常":

            data["Current"] = "Default"  # 切换配置
            for i in range(1, 9):
                data["Global"][f"Timer.Timer{i}"] = "False"  # 时间设置
            data["Configurations"]["Default"][
                "MainFunction.PostActions"
            ] = "12"  # 完成后退出MAA和模拟器
            data["Configurations"]["Default"][
                "Start.RunDirectly"
            ] = "True"  # 启动MAA后直接运行
            data["Configurations"]["Default"][
                "Start.OpenEmulatorAfterLaunch"
            ] = "True"  # 启动MAA后自动开启模拟器

            if self.data[index][15] == "simple":

                data["Global"][
                    "VersionUpdate.ScheduledUpdateCheck"
                ] = "True"  # 定时检查更新
                data["Global"][
                    "VersionUpdate.AutoDownloadUpdatePackage"
                ] = "True"  # 自动下载更新包
                data["Global"][
                    "VersionUpdate.AutoInstallUpdatePackage"
                ] = "True"  # 自动安装更新包
                data["Configurations"]["Default"]["Start.ClientType"] = self.data[
                    index
                ][
                    2
                ]  # 客户端类型
                # 账号切换
                if self.data[index][2] == "Official":
                    data["Configurations"]["Default"][
                        "Start.AccountName"
                    ] = f"{self.data[index][1][:3]}****{self.data[index][1][7:]}"
                elif self.data[index][2] == "Bilibili":
                    data["Configurations"]["Default"]["Start.AccountName"] = self.data[
                        index
                    ][1]
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
                    data["Configurations"]["Default"]["GUI.UseAlternateStage"] = "False"
                else:
                    data["Configurations"]["Default"]["GUI.UseAlternateStage"] = "True"
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
                        "Infrast.DefaultInfrast"
                    ] = "user_defined"  # 内置配置
                    data["Configurations"]["Default"][
                        "Infrast.IsCustomInfrastFileReadOnly"
                    ] = "False"  # 自定义基建配置文件只读
                    data["Configurations"]["Default"][
                        "Infrast.CustomInfrastFile"
                    ] = f"{self.json_path}/simple/{self.data[index][16]}/infrastructure/infrastructure.json"  # 自定义基建配置文件地址

        # 覆写配置文件
        with open(self.set_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

        return True


class MainTimer(QtCore.QThread):

    get_config = QtCore.Signal()
    start_for_timer = QtCore.Signal()
    app_path = os.path.realpath(sys.argv[0])  # 获取软件自身的路径
    app_name = os.path.basename(app_path)  # 获取软件自身的名称
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    is_maa_run = False

    def __init__(self, config):
        super(MainTimer, self).__init__()
        self.config = config
        self.last_time = "0000-00-00 00:00"

    def run(self):
        """主功能代码，实现定时执行以及相关配置信息的实时同步"""

        while not self.isInterruptionRequested():

            # 同步程序设置
            self.get_config.emit()

            # 同步到系统设置
            self.set_system()

            # 获取定时列表
            time_set = [
                self.config["Default"][f"TimeSet.run{_ + 1}"]
                for _ in range(10)
                if self.config["Default"][f"TimeSet.set{_ + 1}"] == "True"
            ]
            # 按时间调起代理任务
            curtime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            if (
                curtime[11:16] in time_set
                and curtime != self.last_time
                and not self.is_maa_run
            ):
                self.last_time = curtime
                self.start_for_timer.emit()

            # 同步时间间隔
            time.sleep(1)

    def set_system(self):
        """设置系统相关配置"""

        # 同步系统休眠状态
        if self.config["Default"]["SelfSet.IfSleep"] == "True":
            # 设置系统电源状态
            ctypes.windll.kernel32.SetThreadExecutionState(
                self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED
            )
        elif self.config["Default"]["SelfSet.IfSleep"] == "False":
            # 恢复系统电源状态
            ctypes.windll.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS)

        # 同步开机自启
        if (
            self.config["Default"]["SelfSet.IfSelfStart"] == "True"
            and not self.is_startup()
        ):
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                winreg.KEY_SET_VALUE,
                winreg.KEY_ALL_ACCESS | winreg.KEY_WRITE | winreg.KEY_CREATE_SUB_KEY,
            )
            winreg.SetValueEx(key, self.app_name, 0, winreg.REG_SZ, self.app_path)
            winreg.CloseKey(key)
        elif (
            self.config["Default"]["SelfSet.IfSelfStart"] == "False"
            and self.is_startup()
        ):
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                winreg.KEY_SET_VALUE,
                winreg.KEY_ALL_ACCESS | winreg.KEY_WRITE | winreg.KEY_CREATE_SUB_KEY,
            )
            winreg.DeleteValue(key, self.app_name)
            winreg.CloseKey(key)

    def is_startup(self):
        """判断程序是否已经开机自启"""

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        )

        try:
            value, _ = winreg.QueryValueEx(key, self.app_name)
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            winreg.CloseKey(key)
            return False


class Main(QWidget):

    app_path = os.path.dirname(os.path.realpath(sys.argv[0])).replace(
        "\\", "/"
    )  # 获取软件自身的路径

    def __init__(self, PASSWARD=""):
        super().__init__()

        self.database_path = f"{self.app_path}/data/data.db"
        self.config_path = f"{self.app_path}/config/gui.json"
        self.key_path = f"{self.app_path}/data/key"
        self.gameid_path = f"{self.app_path}/data/gameid.txt"
        self.version_path = f"{self.app_path}/res/version.json"
        self.PASSWORD = PASSWARD
        self.if_user_list_editable = True
        self.if_update_database = True
        self.if_update_config = True
        self.user_mode_list = ["simple", "beta"]
        self.user_column = [
            "admin",
            "id",
            "server",
            "day",
            "status",
            "last",
            "game",
            "game_1",
            "game_2",
            "routines",
            "annihilation",
            "infrastructure",
            "password",
            "notes",
            "numb",
            "mode",
            "uid",
        ]
        self.userlist_simple_index = [
            0,
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            8,
            "-",
            9,
            10,
            11,
            12,
            "-",
            "-",
            "-",
        ]
        self.userlist_beta_index = [
            0,
            "-",
            "-",
            1,
            2,
            3,
            "-",
            "-",
            "-",
            4,
            5,
            "-",
            6,
            7,
            "-",
            "-",
            "-",
        ]

        # 导入ui配置
        self.ui = uiLoader.load(f"{self.app_path}/gui/ui/main.ui")
        self.ui.setWindowIcon(QIcon(f"{self.app_path}/gui/ico/AUTO_MAA.ico"))

        # 检查文件完整性
        self.initialize()
        self.check_config()
        self.check_database()

        # 初始化数据库连接
        self.db = sqlite3.connect(self.database_path)
        self.cur = self.db.cursor()

        # 初始化控件
        self.main_tab = self.ui.findChild(QTabWidget, "tabWidget_main")
        self.main_tab.currentChanged.connect(self.change_config)

        self.user_set = self.ui.findChild(QToolBox, "toolBox_userset")
        self.user_set.currentChanged.connect(self.change_userlist_method)

        self.user_list_simple = self.ui.findChild(
            QTableWidget, "tableWidget_userlist_simple"
        )
        self.user_list_simple.itemChanged.connect(
            lambda item: self.change_user_Item(item, "simple")
        )
        self.user_list_simple.setStyleSheet("background-color: rgb(255, 255, 255);")

        self.user_list_beta = self.ui.findChild(
            QTableWidget, "tableWidget_userlist_beta"
        )
        self.user_list_beta.itemChanged.connect(
            lambda item: self.change_user_Item(item, "beta")
        )
        self.user_list_beta.setStyleSheet("background-color: rgb(255, 255, 255);")

        self.user_add = self.ui.findChild(QPushButton, "pushButton_new")
        self.user_add.clicked.connect(self.add_user)

        self.user_del = self.ui.findChild(QPushButton, "pushButton_del")
        self.user_del.clicked.connect(self.del_user)

        self.user_switch = self.ui.findChild(QPushButton, "pushButton_switch")
        self.user_switch.clicked.connect(self.switch_user)

        self.user_changeset = self.ui.findChild(QPushButton, "pushButton_changeset")
        self.user_changeset.clicked.connect(self.change_user_set)

        self.read_PASSWORD = self.ui.findChild(QPushButton, "pushButton_password")
        self.read_PASSWORD.clicked.connect(lambda: self.read("key"))

        self.refresh = self.ui.findChild(QPushButton, "pushButton_refresh")
        self.refresh.clicked.connect(lambda: self.update_user_info("clear"))

        self.run_now = self.ui.findChild(QPushButton, "pushButton_runnow")
        self.run_now.clicked.connect(lambda: self.maa_starter("日常代理"))

        self.check_start = self.ui.findChild(QPushButton, "pushButton_checkstart")
        self.check_start.clicked.connect(lambda: self.maa_starter("人工排查"))

        self.maa_path = self.ui.findChild(QLineEdit, "lineEdit_MAApath")
        self.maa_path.textChanged.connect(self.change_config)
        self.maa_path.setReadOnly(True)

        self.get_maa_path = self.ui.findChild(QPushButton, "pushButton_getMAApath")
        self.get_maa_path.clicked.connect(lambda: self.read("file_path_maa"))

        self.set_maa = self.ui.findChild(QPushButton, "pushButton_setMAA")
        self.set_maa.clicked.connect(lambda: self.maa_starter("设置MAA_全局"))

        self.routine = self.ui.findChild(QSpinBox, "spinBox_routine")
        self.routine.valueChanged.connect(self.change_config)

        self.annihilation = self.ui.findChild(QSpinBox, "spinBox_annihilation")
        self.annihilation.valueChanged.connect(self.change_config)

        self.num = self.ui.findChild(QSpinBox, "spinBox_numt")
        self.num.valueChanged.connect(self.change_config)

        self.if_self_start = self.ui.findChild(QCheckBox, "checkBox_ifselfstart")
        self.if_self_start.stateChanged.connect(self.change_config)

        self.if_sleep = self.ui.findChild(QCheckBox, "checkBox_ifsleep")
        self.if_sleep.stateChanged.connect(self.change_config)

        self.if_proxy_directly = self.ui.findChild(
            QCheckBox, "checkBox_ifproxydirectly"
        )
        self.if_proxy_directly.stateChanged.connect(self.change_config)

        self.if_send_mail = self.ui.findChild(QCheckBox, "checkBox_ifsendmail")
        self.if_send_mail.stateChanged.connect(self.change_config)

        self.mail_address = self.ui.findChild(QLineEdit, "lineEdit_mailaddress")
        self.mail_address.textChanged.connect(self.change_config)

        self.if_to_tray = self.ui.findChild(QCheckBox, "checkBox_iftotray")
        self.if_to_tray.stateChanged.connect(self.change_config)

        self.check_update = self.ui.findChild(QPushButton, "pushButton_check_update")
        self.check_update.clicked.connect(self.check_version)

        self.tips = self.ui.findChild(QTextBrowser, "textBrowser_tips")
        self.tips.setOpenExternalLinks(True)

        self.run_text = self.ui.findChild(QTextBrowser, "textBrowser_run")
        self.wait_text = self.ui.findChild(QTextBrowser, "textBrowser_wait")
        self.over_text = self.ui.findChild(QTextBrowser, "textBrowser_over")
        self.error_text = self.ui.findChild(QTextBrowser, "textBrowser_error")
        self.log_text = self.ui.findChild(QTextBrowser, "textBrowser_log")

        self.start_time = []
        for i in range(10):
            listx = []
            listx.append(self.ui.findChild(QCheckBox, f"checkBox_t{i + 1}"))
            listx.append(self.ui.findChild(QTimeEdit, f"timeEdit_{i + 1}"))
            self.start_time.append(listx)
            self.start_time[i][0].stateChanged.connect(self.change_config)
            self.start_time[i][1].timeChanged.connect(self.change_config)

        self.change_password = self.ui.findChild(
            QPushButton, "pushButton_changePASSWORD"
        )
        self.change_password.clicked.connect(self.change_PASSWORD)

        # 初始化线程
        self.MaaRunner = MaaRunner()
        self.MaaRunner.question.connect(lambda: self.read("question_runner"))
        self.MaaRunner.update_gui.connect(self.update_board)
        self.MaaRunner.update_user_info.connect(self.change_user_info)
        self.MaaRunner.push_notification.connect(self.push_notification)
        self.MaaRunner.send_mail.connect(self.send_mail)
        self.MaaRunner.accomplish.connect(lambda: self.maa_ender("日常代理_结束"))
        self.MaaRunner.get_json.connect(self.get_maa_config)

        self.MainTimer = MainTimer(self.config)
        self.MainTimer.get_config.connect(self.give_config)
        self.MainTimer.start_for_timer.connect(lambda: self.maa_starter("日常代理"))
        self.MainTimer.start()

        # 载入GUI数据
        self.update_user_info("normal")
        self.update_config()
        self.change_userlist_method()

        # 启动后直接开始代理
        if self.config["Default"]["SelfSet.IfProxyDirectly"] == "True":
            self.maa_starter("日常代理")

    def initialize(self):
        """初始化程序的配置文件"""

        # 检查目录
        os.makedirs(f"{self.app_path}/data", exist_ok=True)
        os.makedirs(f"{self.app_path}/config", exist_ok=True)
        os.makedirs(f"{self.app_path}/data/MAAconfig/simple", exist_ok=True)
        os.makedirs(f"{self.app_path}/data/MAAconfig/beta", exist_ok=True)
        os.makedirs(f"{self.app_path}/data/MAAconfig/Default", exist_ok=True)

        # 生成版本信息文件
        if not os.path.exists(self.version_path):
            version = {
                "main_version": "0.0.0.0",
                "updater_version": "0.0.0.0",
            }
            with open(self.version_path, "w", encoding="utf-8") as f:
                json.dump(version, f, indent=4)

        # 生成配置文件
        if not os.path.exists(self.config_path):
            config = {"Default": {}}
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4)

        # 生成预设gameid替换方案文件
        if not os.path.exists(self.gameid_path):
            with open(self.gameid_path, "w", encoding="utf-8") as f:
                print(
                    "龙门币：CE-6\n技能：CA-5\n红票：AP-5\n经验：LS-6\n剿灭模式：Annihilation",
                    file=f,
                )

        # 生成管理密钥
        if not os.path.exists(self.key_path):
            while True:
                self.PASSWORD, ok_pressed = QInputDialog.getText(
                    self.ui,
                    "请设置管理密钥",
                    "未检测到管理密钥，请设置您的管理密钥：",
                    QLineEdit.Password,
                    "",
                )
                if ok_pressed and self.PASSWORD != "":
                    self.get_PASSWORD()
                    break
                else:
                    choice = QMessageBox.question(
                        self.ui, "确认", "您没有输入管理密钥，确定要暂时跳过这一步吗？"
                    )
                    if choice == QMessageBox.Yes:
                        break

    def check_config(self):
        """检查配置文件字段完整性并补全"""

        config_list = [
            ["TimeSet.set1", "False"],
            ["TimeSet.run1", "00:00"],
            ["TimeSet.set2", "False"],
            ["TimeSet.run2", "00:00"],
            ["TimeSet.set3", "False"],
            ["TimeSet.run3", "00:00"],
            ["TimeSet.set4", "False"],
            ["TimeSet.run4", "00:00"],
            ["TimeSet.set5", "False"],
            ["TimeSet.run5", "00:00"],
            ["TimeSet.set6", "False"],
            ["TimeSet.run6", "00:00"],
            ["TimeSet.set7", "False"],
            ["TimeSet.run7", "00:00"],
            ["TimeSet.set8", "False"],
            ["TimeSet.run8", "00:00"],
            ["TimeSet.set9", "False"],
            ["TimeSet.run9", "00:00"],
            ["TimeSet.set10", "False"],
            ["TimeSet.run10", "00:00"],
            ["MaaSet.path", ""],
            ["TimeLimit.routine", 10],
            ["TimeLimit.annihilation", 40],
            ["TimesLimit.run", 3],
            ["SelfSet.IfSelfStart", "False"],
            ["SelfSet.IfSleep", "False"],
            ["SelfSet.IfProxyDirectly", "False"],
            ["SelfSet.IfSendMail", "False"],
            ["SelfSet.MailAddress", ""],
            ["SelfSet.IfToTray", "False"],
            ["SelfSet.UIsize", "1200x700"],
            ["SelfSet.UIlocation", "100x100"],
            ["SelfSet.UImaximized", "False"],
            ["SelfSet.MainIndex", 0],
        ]

        # 导入配置文件
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        # 检查并补充缺失的字段
        for i in range(len(config_list)):
            if not config_list[i][0] in config["Default"]:
                config["Default"][config_list[i][0]] = config_list[i][1]

        # 初始化配置信息
        self.config = config

        # 导出配置文件
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)

    def check_database(self):
        """检查用户数据库文件并处理数据库版本更新"""

        # 生成用户数据库
        if not os.path.exists(self.database_path):
            db = sqlite3.connect(self.database_path)
            cur = db.cursor()
            cur.execute(
                "CREATE TABLE adminx(admin text,id text,server text,day int,status text,last date,game text,game_1 text,game_2 text,routines text,annihilation text,infrastructure text,password byte,notes text,numb int,mode text,uid int)"
            )
            cur.execute("CREATE TABLE version(v text)")
            cur.execute("INSERT INTO version VALUES(?)", ("v1.2",))
            db.commit()
            cur.close()
            db.close()

        # 数据库版本更新
        db = sqlite3.connect(self.database_path)
        cur = db.cursor()
        cur.execute("SELECT * FROM version WHERE True")
        version = cur.fetchall()
        # v1.0-->v1.1
        if version[0][0] == "v1.0":
            cur.execute("SELECT * FROM adminx WHERE True")
            data = cur.fetchall()
            cur.execute("DROP TABLE IF EXISTS adminx")
            cur.execute(
                "CREATE TABLE adminx(admin text,id text,server text,day int,status text,last date,game text,game_1 text,game_2 text,routines text,annihilation text,infrastructure text,password byte,notes text,numb int,mode text,uid int)"
            )
            for i in range(len(data)):
                cur.execute(
                    "INSERT INTO adminx VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        data[i][0],  # 0 0 0
                        data[i][1],  # 1 1 -
                        "Official",  # 2 2 -
                        data[i][2],  # 3 3 1
                        data[i][3],  # 4 4 2
                        data[i][4],  # 5 5 3
                        data[i][5],  # 6 6 -
                        data[i][6],  # 7 7 -
                        data[i][7],  # 8 8 -
                        "y",  # 9 - 4
                        data[i][8],  # 10 9 5
                        data[i][9],  # 11 10 -
                        data[i][10],  # 12 11 6
                        data[i][11],  # 13 12 7
                        data[i][12],  # 14 - -
                        "simple",  # 15 - -
                        data[i][13],  # 16 - -
                    ),
                )
                self.get_maa_config([0, data[i][13], 0])
                self.get_maa_config([0, data[i][13], 1])
            cur.execute("DELETE FROM version WHERE v = ?", ("v1.0",))
            cur.execute("INSERT INTO version VALUES(?)", ("v1.1",))
            db.commit()
        # v1.1-->v1.2
        if version[0][0] == "v1.1":
            cur.execute("SELECT * FROM adminx WHERE True")
            data = cur.fetchall()
            for i in range(len(data)):
                cur.execute(
                    "UPDATE adminx SET infrastructure = 'n' WHERE mode = ? AND uid = ?",
                    (
                        data[i][15],
                        data[i][16],
                    ),
                )
            cur.execute("DELETE FROM version WHERE v = ?", ("v1.1",))
            cur.execute("INSERT INTO version VALUES(?)", ("v1.2",))
            db.commit()
        cur.close()
        db.close()

    def get_PASSWORD(self):
        """配置管理密钥"""

        # 生成目录
        os.makedirs(f"{self.app_path}/data/key", exist_ok=True)

        # 生成RSA密钥对
        key = RSA.generate(2048)
        public_key_local = key.publickey()
        private_key = key
        # 保存RSA公钥
        with open(f"{self.app_path}/data/key/public_key.pem", "wb") as f:
            f.write(public_key_local.exportKey())
        # 生成密钥转换与校验随机盐
        PASSWORD_salt = secrets.token_hex(random.randint(32, 1024))
        with open(
            f"{self.app_path}/data/key/PASSWORDsalt.txt", "w", encoding="utf-8"
        ) as f:
            print(PASSWORD_salt, file=f)
        verify_salt = secrets.token_hex(random.randint(32, 1024))
        with open(
            f"{self.app_path}/data/key/verifysalt.txt", "w", encoding="utf-8"
        ) as f:
            print(verify_salt, file=f)
        # 将管理密钥转化为AES-256密钥
        AES_password = hashlib.sha256(
            (self.PASSWORD + PASSWORD_salt).encode("utf-8")
        ).digest()
        # 生成AES-256密钥校验哈希值并保存
        AES_password_verify = hashlib.sha256(
            AES_password + verify_salt.encode("utf-8")
        ).digest()
        with open(f"{self.app_path}/data/key/AES_password_verify.bin", "wb") as f:
            f.write(AES_password_verify)
        # AES-256加密RSA私钥并保存密文
        AES_key = AES.new(AES_password, AES.MODE_ECB)
        private_key_local = AES_key.encrypt(pad(private_key.exportKey(), 32))
        with open(f"{self.app_path}/data/key/private_key.bin", "wb") as f:
            f.write(private_key_local)

    def encryptx(self, note):
        """加密数据"""

        # 读取RSA公钥
        with open(f"{self.app_path}/data/key/public_key.pem", "rb") as f:
            public_key_local = RSA.import_key(f.read())
        # 使用RSA公钥对数据进行加密
        cipher = PKCS1_OAEP.new(public_key_local)
        encrypted = cipher.encrypt(note.encode("utf-8"))
        return encrypted

    def decryptx(self, note):
        """解密数据"""

        # 读入RSA私钥密文、盐与校验哈希值
        with open(f"{self.app_path}/data/key/private_key.bin", "rb") as f:
            private_key_local = f.read().strip()
        with open(
            f"{self.app_path}/data/key/PASSWORDsalt.txt", "r", encoding="utf-8"
        ) as f:
            PASSWORD_salt = f.read().strip()
        with open(
            f"{self.app_path}/data/key/verifysalt.txt", "r", encoding="utf-8"
        ) as f:
            verify_salt = f.read().strip()
        with open(f"{self.app_path}/data/key/AES_password_verify.bin", "rb") as f:
            AES_password_verify = f.read().strip()
        # 将管理密钥转化为AES-256密钥并验证
        AES_password = hashlib.sha256(
            (self.PASSWORD + PASSWORD_salt).encode("utf-8")
        ).digest()
        AES_password_SHA = hashlib.sha256(
            AES_password + verify_salt.encode("utf-8")
        ).digest()
        if AES_password_SHA != AES_password_verify:
            return "管理密钥错误"
        else:
            # AES解密RSA私钥
            AES_key = AES.new(AES_password, AES.MODE_ECB)
            private_key_pem = unpad(AES_key.decrypt(private_key_local), 32)
            private_key = RSA.import_key(private_key_pem)
            # 使用RSA私钥解密数据
            decrypter = PKCS1_OAEP.new(private_key)
            note = decrypter.decrypt(note)
            return note.decode("utf-8")

    def change_PASSWORD(self):
        """修改管理密钥"""

        # 获取用户信息
        self.cur.execute("SELECT * FROM adminx WHERE True")
        data = self.cur.fetchall()

        if len(data) == 0:
            QMessageBox.information(self.ui, "验证通过", "当前无用户，验证自动通过")
            # 获取新的管理密钥
            while True:
                PASSWORD_new = self.read("newkey")
                if PASSWORD_new == 0:
                    choice = QMessageBox.question(
                        self.ui,
                        "确认",
                        "您没有输入新的管理密钥，是否取消修改管理密钥？",
                    )
                    if choice == QMessageBox.Yes:
                        break
                else:
                    # 修改管理密钥
                    self.PASSWORD = PASSWORD_new
                    self.get_PASSWORD()
                    QMessageBox.information(self.ui, "操作成功", "管理密钥修改成功")
                    break
        else:
            # 验证管理密钥
            if_change = True
            while if_change:
                if self.read("oldkey"):
                    # 验证旧管理密钥
                    if self.decryptx(self.encryptx("")) == "管理密钥错误":
                        QMessageBox.critical(self.ui, "错误", "管理密钥错误")
                    else:
                        # 获取新的管理密钥
                        while True:
                            PASSWORD_new = self.read("newkey")
                            if PASSWORD_new == 0:
                                choice = QMessageBox.question(
                                    self.ui,
                                    "确认",
                                    "您没有输入新的管理密钥，是否取消修改管理密钥？",
                                )
                                if choice == QMessageBox.Yes:
                                    if_change = False
                                    break
                            # 修改管理密钥
                            else:
                                # 使用旧管理密钥解密
                                new_data = []
                                for i in range(len(data)):
                                    new_data.append(self.decryptx(data[i][12]))
                                # 使用新管理密钥重新加密
                                self.PASSWORD = PASSWORD_new
                                self.get_PASSWORD()
                                for i in range(len(data)):
                                    self.cur.execute(
                                        "UPDATE adminx SET password = ? WHERE mode = ? AND uid = ?",
                                        (
                                            self.encryptx(new_data[i]),
                                            data[i][15],
                                            data[i][16],
                                        ),
                                    )
                                self.db.commit()
                                QMessageBox.information(
                                    self.ui, "操作成功", "管理密钥修改成功"
                                )
                                if_change = False
                                break
                else:
                    choice = QMessageBox.question(
                        self.ui, "确认", "您没有输入管理密钥，是否取消修改管理密钥？"
                    )
                    if choice == QMessageBox.Yes:
                        break

    def update_user_info(self, operation):
        """将本地数据库中的用户配置同步至GUI的用户管理界面"""

        # 读入本地数据库
        self.cur.execute("SELECT * FROM adminx WHERE True")
        data = self.cur.fetchall()

        # 处理部分模式调整
        if operation == "clear":
            self.PASSWORD = ""
        elif operation == "read_only":
            self.if_user_list_editable = False
        elif operation == "editable":
            self.if_user_list_editable = True

        # 阻止GUI用户数据被立即写入数据库形成死循环
        self.if_update_database = False

        # 同步简洁用户配置列表
        data_simple = [_ for _ in data if _[15] == "simple"]
        self.user_list_simple.setRowCount(len(data_simple))

        for i, row in enumerate(data_simple):

            for j, value in enumerate(row):

                if self.userlist_simple_index[j] == "-":
                    continue

                # 生成表格组件
                if j == 2:
                    item = QComboBox()
                    item.addItems(["官服", "B服"])
                    if value == "Official":
                        item.setCurrentIndex(0)
                    elif value == "Bilibili":
                        item.setCurrentIndex(1)
                    item.currentIndexChanged.connect(
                        partial(
                            self.change_user_CellWidget,
                            data_simple[i][16],
                            self.user_column[j],
                        )
                    )
                elif j in [4, 10, 11]:
                    item = QComboBox()
                    item.addItems(["启用", "禁用"])
                    if value == "y":
                        item.setCurrentIndex(0)
                    elif value == "n":
                        item.setCurrentIndex(1)
                    item.currentIndexChanged.connect(
                        partial(
                            self.change_user_CellWidget,
                            data_simple[i][16],
                            self.user_column[j],
                        )
                    )
                elif j == 3 and value == -1:
                    item = QTableWidgetItem("无限")
                elif j == 5:
                    curdate = server_date()
                    if curdate != value:
                        item = QTableWidgetItem("今日未代理")
                    else:
                        item = QTableWidgetItem(f"今日已代理{data_simple[i][14]}次")
                    item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
                elif j == 12:
                    if self.PASSWORD == "":
                        item = QTableWidgetItem("******")
                        item.setFlags(
                            QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
                        )
                    else:
                        result = self.decryptx(value)
                        item = QTableWidgetItem(result)
                        if result == "管理密钥错误":
                            item.setFlags(
                                QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
                            )
                else:
                    item = QTableWidgetItem(str(value))

                # 组件录入表格
                if j in [2, 4, 10, 11]:
                    if not self.if_user_list_editable:
                        item.setEnabled(False)
                    self.user_list_simple.setCellWidget(
                        data_simple[i][16], self.userlist_simple_index[j], item
                    )
                else:
                    self.user_list_simple.setItem(
                        data_simple[i][16], self.userlist_simple_index[j], item
                    )

        # 同步高级用户配置列表
        data_beta = [_ for _ in data if _[15] == "beta"]
        self.user_list_beta.setRowCount(len(data_beta))

        for i, row in enumerate(data_beta):

            for j, value in enumerate(row):

                if self.userlist_beta_index[j] == "-":
                    continue

                # 生成表格组件
                if j in [4, 9, 10]:
                    item = QComboBox()
                    item.addItems(["启用", "禁用"])
                    if value == "y":
                        item.setCurrentIndex(0)
                    elif value == "n":
                        item.setCurrentIndex(1)
                    item.currentIndexChanged.connect(
                        partial(
                            self.change_user_CellWidget,
                            data_beta[i][16],
                            self.user_column[j],
                        )
                    )
                elif j == 3 and value == -1:
                    item = QTableWidgetItem("无限")
                elif j == 5:
                    curdate = server_date()
                    if curdate != value:
                        item = QTableWidgetItem("今日未代理")
                    else:
                        item = QTableWidgetItem(f"今日已代理{data_beta[i][14]}次")
                    item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
                elif j == 12:
                    if self.PASSWORD == "":
                        item = QTableWidgetItem("******")
                        item.setFlags(
                            QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
                        )
                    else:
                        result = self.decryptx(value)
                        item = QTableWidgetItem(result)
                        if result == "管理密钥错误":
                            item.setFlags(
                                QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
                            )
                else:
                    item = QTableWidgetItem(str(value))

                # 组件录入表格
                if j in [4, 9, 10]:
                    if not self.if_user_list_editable:
                        item.setEnabled(False)
                    self.user_list_beta.setCellWidget(
                        data_beta[i][16], self.userlist_beta_index[j], item
                    )
                else:
                    self.user_list_beta.setItem(
                        data_beta[i][16], self.userlist_beta_index[j], item
                    )

        # 设置列表可编辑状态
        if self.if_user_list_editable:
            self.user_list_simple.setEditTriggers(QTableWidget.AllEditTriggers)
            self.user_list_beta.setEditTriggers(QTableWidget.AllEditTriggers)
        else:
            self.user_list_simple.setEditTriggers(QTableWidget.NoEditTriggers)
            self.user_list_beta.setEditTriggers(QTableWidget.NoEditTriggers)

        # 允许GUI改变被同步到本地数据库
        self.if_update_database = True

        # 设置用户配置列表的标题栏宽度
        self.user_list_simple.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.user_list_beta.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def update_config(self):
        """将self.config中的程序配置同步至GUI界面"""

        # 阻止GUI程序配置被立即读入程序形成死循环
        self.if_update_config = False

        self.main_tab.setCurrentIndex(self.config["Default"]["SelfSet.MainIndex"])

        self.maa_path.setText(self.config["Default"]["MaaSet.path"].replace("\\", "/"))
        self.routine.setValue(self.config["Default"]["TimeLimit.routine"])
        self.annihilation.setValue(self.config["Default"]["TimeLimit.annihilation"])
        self.num.setValue(self.config["Default"]["TimesLimit.run"])
        self.mail_address.setText(self.config["Default"]["SelfSet.MailAddress"])

        self.if_self_start.setChecked(
            bool(self.config["Default"]["SelfSet.IfSelfStart"] == "True")
        )

        self.if_sleep.setChecked(
            bool(self.config["Default"]["SelfSet.IfSleep"] == "True")
        )

        self.if_proxy_directly.setChecked(
            bool(self.config["Default"]["SelfSet.IfProxyDirectly"] == "True")
        )

        self.if_send_mail.setChecked(
            bool(self.config["Default"]["SelfSet.IfSendMail"] == "True")
        )

        self.mail_address.setVisible(
            bool(self.config["Default"]["SelfSet.IfSendMail"] == "True")
        )

        self.if_to_tray.setChecked(
            bool(self.config["Default"]["SelfSet.IfToTray"] == "True")
        )

        for i in range(10):
            self.start_time[i][0].setChecked(
                bool(self.config["Default"][f"TimeSet.set{i + 1}"] == "True")
            )
            time = QtCore.QTime(
                int(self.config["Default"][f"TimeSet.run{i + 1}"][:2]),
                int(self.config["Default"][f"TimeSet.run{i + 1}"][3:]),
            )
            self.start_time[i][1].setTime(time)
        self.if_update_config = True

    def update_board(self, run_text, wait_text, over_text, error_text, log_text):
        """写入数据至GUI执行界面的调度台面板"""

        self.run_text.setPlainText(run_text)
        self.wait_text.setPlainText(wait_text)
        self.over_text.setPlainText(over_text)
        self.error_text.setPlainText(error_text)
        self.log_text.setPlainText(log_text)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

    def add_user(self):
        """添加一位新用户"""

        if not self.check_maa_path():
            QMessageBox.critical(
                self.ui,
                "错误",
                "请先正确配置MAA路径再执行添加用户操作",
            )
            return None

        if not os.path.exists(self.key_path):
            QMessageBox.critical(
                self.ui,
                "错误",
                "请先设置管理密钥再执行添加用户操作",
            )
            return None

        # 插入预设用户数据
        if self.user_set.currentIndex() == 0:
            self.cur.execute(
                "INSERT INTO adminx VALUES('新用户','手机号码（官服）/B站ID（B服）','Official',0,'y','2000-01-01','1-7','-','-','y','y','n',?,'无',0,'simple',?)",
                (
                    self.encryptx("未设置"),
                    self.user_list_simple.rowCount(),
                ),
            )
            self.get_maa_config(
                [self.user_set.currentIndex(), self.user_list_simple.rowCount(), 0]
            )
            self.get_maa_config(
                [self.user_set.currentIndex(), self.user_list_simple.rowCount(), 1]
            )
        elif self.user_set.currentIndex() == 1:
            self.cur.execute(
                "INSERT INTO adminx VALUES('新用户','手机号码（官服）/B站ID（B服）','Official',0,'y','2000-01-01','1-7','-','-','y','y','-',?,'无',0,'beta',?)",
                (
                    self.encryptx("未设置"),
                    self.user_list_beta.rowCount(),
                ),
            )
            self.get_maa_config(
                [self.user_set.currentIndex(), self.user_list_beta.rowCount(), 0]
            )
            self.get_maa_config(
                [self.user_set.currentIndex(), self.user_list_beta.rowCount(), 1]
            )
        self.db.commit()

        # 同步新用户至GUI
        self.update_user_info("normal")

    def del_user(self):
        """删除选中的首位用户"""

        # 获取对应的行索引
        if self.user_set.currentIndex() == 0:
            row = self.user_list_simple.currentRow()
        elif self.user_set.currentIndex() == 1:
            row = self.user_list_beta.currentRow()

        # 判断选择合理性
        if row == -1:
            QMessageBox.critical(self.ui, "错误", "请选中一个用户后再执行删除操作")
            return None

        # 确认待删除用户信息
        self.cur.execute(
            "SELECT * FROM adminx WHERE mode = ? AND uid = ?",
            (
                self.user_mode_list[self.user_set.currentIndex()],
                row,
            ),
        )
        data = self.cur.fetchall()
        choice = QMessageBox.question(
            self.ui, "确认", f"确定要删除用户 {data[0][0]} 吗？"
        )

        # 删除用户
        if choice == QMessageBox.Yes:
            # 删除所选用户
            self.cur.execute(
                "DELETE FROM adminx WHERE mode = ? AND uid = ?",
                (
                    self.user_mode_list[self.user_set.currentIndex()],
                    row,
                ),
            )
            self.db.commit()
            shutil.rmtree(
                f"{self.app_path}/data/MAAconfig/{self.user_mode_list[self.user_set.currentIndex()]}/{row}"
            )
            # 后续用户补位
            if self.user_set.currentIndex() == 0:
                current_numb = self.user_list_simple.rowCount()
            elif self.user_set.currentIndex() == 1:
                current_numb = self.user_list_beta.rowCount()
            for i in range(row + 1, current_numb):
                self.cur.execute(
                    "UPDATE adminx SET uid = ? WHERE mode = ? AND uid = ?",
                    (i - 1, self.user_mode_list[self.user_set.currentIndex()], i),
                )
                self.db.commit()
                os.rename(
                    f"{self.app_path}/data/MAAconfig/{self.user_mode_list[self.user_set.currentIndex()]}/{i}",
                    f"{self.app_path}/data/MAAconfig/{self.user_mode_list[self.user_set.currentIndex()]}/{i - 1}",
                )

            # 同步最终结果至GUI
            self.update_user_info("normal")

    def switch_user(self):
        """切换用户配置模式"""

        # 获取当前用户配置模式信息
        if self.user_set.currentIndex() == 0:
            row = self.user_list_simple.currentRow()
        elif self.user_set.currentIndex() == 1:
            row = self.user_list_beta.currentRow()

        # 判断选择合理性
        if row == -1:
            QMessageBox.critical(self.ui, "错误", "请选中一个用户后再执行切换操作")
            return None

        # 确认待切换用户信息
        self.cur.execute(
            "SELECT * FROM adminx WHERE mode = ? AND uid = ?",
            (
                self.user_mode_list[self.user_set.currentIndex()],
                row,
            ),
        )
        data = self.cur.fetchall()
        mode_list = ["简洁", "高级"]
        choice = QMessageBox.question(
            self.ui,
            "确认",
            f"确定要将用户 {data[0][0]} 转为{mode_list[1 - self.user_set.currentIndex()]}配置模式吗？",
        )

        # 切换用户
        if choice == QMessageBox.Yes:
            self.cur.execute("SELECT * FROM adminx WHERE True")
            data = self.cur.fetchall()
            if self.user_set.currentIndex() == 0:
                current_numb = self.user_list_simple.rowCount()
            elif self.user_set.currentIndex() == 1:
                current_numb = self.user_list_beta.rowCount()
            # 切换所选用户
            other_numb = len(data) - current_numb
            self.cur.execute(
                "UPDATE adminx SET mode = ?, uid = ? WHERE mode = ? AND uid = ?",
                (
                    self.user_mode_list[1 - self.user_set.currentIndex()],
                    other_numb,
                    self.user_mode_list[self.user_set.currentIndex()],
                    row,
                ),
            )
            self.db.commit()
            shutil.move(
                f"{self.app_path}/data/MAAconfig/{self.user_mode_list[self.user_set.currentIndex()]}/{row}",
                f"{self.app_path}/data/MAAconfig/{self.user_mode_list[1 - self.user_set.currentIndex()]}/{other_numb}",
            )
            # 后续用户补位
            for i in range(row + 1, current_numb):
                self.cur.execute(
                    "UPDATE adminx SET uid = ? WHERE mode = ? AND uid = ?",
                    (i - 1, self.user_mode_list[self.user_set.currentIndex()], i),
                )
                self.db.commit()
                os.rename(
                    f"{self.app_path}/data/MAAconfig/{self.user_mode_list[self.user_set.currentIndex()]}/{i}",
                    f"{self.app_path}/data/MAAconfig/{self.user_mode_list[self.user_set.currentIndex()]}/{i - 1}",
                )
            self.update_user_info("normal")

    def change_user_set(self):
        """执行用户配置列表的进一步配置"""

        if self.user_set.currentIndex() == 0:

            if self.user_list_simple.currentColumn() in [10]:
                self.get_maa_config([0, self.user_list_simple.currentRow(), 2])
            else:
                QMessageBox.critical(self.ui, "错误", "该项目无法进一步配置")

        elif self.user_set.currentIndex() == 1:

            if self.user_list_beta.currentColumn() in [4, 5]:
                self.MaaRunner.get_json_path = [
                    self.user_set.currentIndex(),
                    self.user_list_beta.currentRow(),
                    self.user_list_beta.currentColumn() - 4,
                ]
                self.maa_starter("设置MAA_用户")
            else:
                QMessageBox.critical(self.ui, "错误", "该项目无法进一步配置")

    def get_maa_config(self, info):
        """获取MAA配置文件"""

        set_book1 = ["simple", "beta"]
        set_book2 = ["routine", "annihilation"]

        # 获取全局MAA配置文件
        if info == ["Default"]:
            os.makedirs(
                f"{self.app_path}/data/MAAconfig/Default",
                exist_ok=True,
            )
            shutil.copy(
                f"{self.config["Default"]["MaaSet.path"]}/config/gui.json",
                f"{self.app_path}/data/MAAconfig/Default",
            )
        # 获取基建配置文件
        elif info[2] == 2:
            infrastructure_path = self.read("file_path_infrastructure")
            if infrastructure_path:
                os.makedirs(
                    f"{self.app_path}/data/MAAconfig/{set_book1[info[0]]}/{info[1]}/infrastructure",
                    exist_ok=True,
                )
                shutil.copy(
                    infrastructure_path,
                    f"{self.app_path}/data/MAAconfig/{set_book1[info[0]]}/{info[1]}/infrastructure/infrastructure.json",
                )
                return True
            else:
                QMessageBox.critical(
                    self.ui,
                    "错误",
                    "未选择自定义基建文件",
                )
                return False
        # 获取高级用户MAA配置文件
        else:
            os.makedirs(
                f"{self.app_path}/data/MAAconfig/{set_book1[info[0]]}/{info[1]}/{set_book2[info[2]]}",
                exist_ok=True,
            )
            shutil.copy(
                f"{self.config["Default"]["MaaSet.path"]}/config/gui.json",
                f"{self.app_path}/data/MAAconfig/{set_book1[info[0]]}/{info[1]}/{set_book2[info[2]]}",
            )

    def change_user_Item(self, item, mode):
        """将GUI中发生修改的用户配置表中的一般信息同步至本地数据库"""

        # 验证能否写入本地数据库
        if not self.if_update_database:
            return None

        text = item.text()
        # 简洁用户配置列表
        if mode == "simple":
            # 待写入信息预处理
            if item.column() == 3:  # 代理天数
                try:
                    text = max(int(text), -1)
                except ValueError:
                    self.update_user_info("normal")
                    return None
            if item.column() in [6, 7, 8]:  # 关卡号
                # 导入与应用特殊关卡规则
                games = {}
                with open(self.gameid_path, encoding="utf-8") as f:
                    gameids = f.readlines()
                    for line in gameids:
                        if "：" in line:
                            game_in, game_out = line.split("：", 1)
                            games[game_in.strip()] = game_out.strip()
                text = games.get(text, text)
            if item.column() == 11:  # 密码
                text = self.encryptx(text)

            # 保存至本地数据库
            if text != "":
                self.cur.execute(
                    f"UPDATE adminx SET {self.user_column[self.userlist_simple_index.index(item.column())]} = ? WHERE mode = 'simple' AND uid = ?",
                    (text, item.row()),
                )
        # 高级用户配置列表
        elif mode == "beta":
            # 待写入信息预处理
            if item.column() == 1:  # 代理天数
                try:
                    text = max(int(text), -1)
                except ValueError:
                    self.update_user_info("normal")
                    return None
            if item.column() == 6:  # 密码
                text = self.encryptx(text)

            # 保存至本地数据库
            if text != "":
                self.cur.execute(
                    f"UPDATE adminx SET {self.user_column[self.userlist_beta_index.index(item.column())]} = ? WHERE mode = 'beta' AND uid = ?",
                    (text, item.row()),
                )
        self.db.commit()

        # 同步一般用户信息更改到GUI
        self.update_user_info("normal")

    def change_user_CellWidget(self, row, column, index):
        """将GUI中发生修改的用户配置表中的CellWidget类信息同步至本地数据库"""

        # 验证能否写入本地数据库
        if not self.if_update_database:
            return None

        # 初次开启自定义基建时选择配置文件
        if (
            self.user_set.currentIndex() == 0
            and column == "infrastructure"
            and index == 0
            and not os.path.exists(
                f"{self.app_path}/data/MAAconfig/{self.user_mode_list[self.user_set.currentIndex()]}/{row}/infrastructure/infrastructure.json",
            )
        ):
            result = self.get_maa_config([0, row, 2])
            if not result:
                index = 1

        # 服务器
        if self.user_set.currentIndex() == 0 and column == "server":
            server_list = ["Official", "Bilibili"]
            self.cur.execute(
                f"UPDATE adminx SET server = ? WHERE mode = 'simple' AND uid = ?",
                (server_list[index], row),
            )
        # 其它
        else:
            index_list = ["y", "n"]
            self.cur.execute(
                f"UPDATE adminx SET {column} = ? WHERE mode = ? AND uid = ?",
                (
                    index_list[index],
                    self.user_mode_list[self.user_set.currentIndex()],
                    row,
                ),
            )
        self.db.commit()

        # 同步用户组件信息修改到GUI
        self.update_user_info("normal")

    def change_user_info(self, modes, uids, days, lasts, notes, numbs):
        """将代理完成后发生改动的用户信息同步至本地数据库"""

        for index in range(len(uids)):
            self.cur.execute(
                "UPDATE adminx SET day = ? WHERE mode = ? AND uid = ?",
                (days[index], modes[index], uids[index]),
            )
            self.cur.execute(
                "UPDATE adminx SET last = ? WHERE mode = ? AND uid = ?",
                (lasts[index], modes[index], uids[index]),
            )
            self.cur.execute(
                "UPDATE adminx SET notes = ? WHERE mode = ? AND uid = ?",
                (notes[index], modes[index], uids[index]),
            )
            self.cur.execute(
                "UPDATE adminx SET numb = ? WHERE mode = ? AND uid = ?",
                (numbs[index], modes[index], uids[index]),
            )
        self.db.commit()

        # 同步用户信息更改至GUI
        self.update_user_info("normal")

    def change_config(self):
        """将GUI中发生修改的程序配置同步至self.config变量"""

        # 验证能否写入self.config变量
        if not self.if_update_config:
            return None

        # 写入并验证MAA路径
        self.config["Default"]["MaaSet.path"] = self.maa_path.text().replace("\\", "/")
        if not self.check_maa_path():
            self.config["Default"]["MaaSet.path"] = ""
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4)
            self.update_config()
            QMessageBox.critical(
                self.ui, "错误", "未找到MAA.exe或MAA配置文件，请重新设置MAA路径！"
            )
            return None

        self.config["Default"]["SelfSet.MainIndex"] = self.main_tab.currentIndex()

        self.config["Default"]["TimeLimit.routine"] = self.routine.value()
        self.config["Default"]["TimeLimit.annihilation"] = self.annihilation.value()
        self.config["Default"]["TimesLimit.run"] = self.num.value()
        self.config["Default"]["SelfSet.MailAddress"] = self.mail_address.text()

        if self.if_sleep.isChecked():
            self.config["Default"]["SelfSet.IfSleep"] = "True"
        else:
            self.config["Default"]["SelfSet.IfSleep"] = "False"

        if self.if_self_start.isChecked():
            self.config["Default"]["SelfSet.IfSelfStart"] = "True"
        else:
            self.config["Default"]["SelfSet.IfSelfStart"] = "False"

        if self.if_proxy_directly.isChecked():
            self.config["Default"]["SelfSet.IfProxyDirectly"] = "True"
        else:
            self.config["Default"]["SelfSet.IfProxyDirectly"] = "False"

        if self.if_send_mail.isChecked():
            self.config["Default"]["SelfSet.IfSendMail"] = "True"
        else:
            self.config["Default"]["SelfSet.IfSendMail"] = "False"

        if self.if_to_tray.isChecked():
            self.config["Default"]["SelfSet.IfToTray"] = "True"
        else:
            self.config["Default"]["SelfSet.IfToTray"] = "False"

        for i in range(10):
            if self.start_time[i][0].isChecked():
                self.config["Default"][f"TimeSet.set{i + 1}"] = "True"
            else:
                self.config["Default"][f"TimeSet.set{i + 1}"] = "False"
            time = self.start_time[i][1].time().toString("HH:mm")
            self.config["Default"][f"TimeSet.run{i + 1}"] = time

        # 将配置信息同步至本地JSON文件
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=4)

        # 同步程序配置至GUI
        self.update_config()

    def change_userlist_method(self):
        """更新GUI界面使之适配用户配置模式"""

        user_switch_list = ["转为高级", "转为简洁"]
        self.user_switch.setText(user_switch_list[self.user_set.currentIndex()])
        self.update_user_info("normal")

    def read(self, operation):
        """弹出对话框组件进行读入"""

        # 读入PASSWORD
        if operation == "key":
            self.PASSWORD, ok_pressed = QInputDialog.getText(
                self.ui, "请输入管理密钥", "管理密钥：", QLineEdit.Password, ""
            )
            if ok_pressed and self.PASSWORD != "":
                self.update_user_info("normal")
        elif operation == "oldkey":
            self.PASSWORD, ok_pressed = QInputDialog.getText(
                self.ui, "请输入旧的管理密钥", "旧管理密钥：", QLineEdit.Password, ""
            )
            if ok_pressed and self.PASSWORD != "":
                return True
            else:
                return False
        elif operation == "newkey":
            new_PASSWORD, ok_pressed = QInputDialog.getText(
                self.ui, "请输入新的管理密钥", "新管理密钥：", QLineEdit.Password, ""
            )
            if ok_pressed and new_PASSWORD != "":
                return new_PASSWORD
            else:
                return None

        # 读入选择
        elif operation == "question_runner":
            choice = QMessageBox.question(
                self.ui,
                self.MaaRunner.question_title,
                self.MaaRunner.question_info,
            )
            if choice == QMessageBox.Yes:
                self.MaaRunner.question_choice = "Yes"
            elif choice == QMessageBox.No:
                self.MaaRunner.question_choice = "No"

        # 读入MAA文件目录
        elif operation == "file_path_maa":
            file_path = QFileDialog.getExistingDirectory(self.ui, "选择MAA文件夹")
            if file_path:
                self.maa_path.setText(file_path)

        # 读入自定义基建文件目录
        elif operation == "file_path_infrastructure":
            file_path, _ = QFileDialog.getOpenFileName(
                self.ui, "选择自定义基建文件", "", "JSON 文件 (*.json)"
            )
            return file_path

    def check_maa_path(self):
        """检查MAA路径是否可用"""

        if os.path.exists(
            f"{self.config["Default"]["MaaSet.path"]}/MAA.exe"
        ) and os.path.exists(
            f"{self.config["Default"]["MaaSet.path"]}/config/gui.json"
        ):
            self.get_maa_config(["Default"])
            return True
        else:
            return False

    def maa_starter(self, mode):
        """启动MaaRunner线程运行任务"""

        # 检查MAA路径是否可用
        if not self.check_maa_path():
            QMessageBox.critical(self.ui, "错误", "您还未正确配置MAA路径！")
            return None

        self.maa_running_set(f"{mode}_开始")

        # 配置参数
        self.MaaRunner.config = self.config
        self.cur.execute("SELECT * FROM adminx WHERE True")
        self.data_ = self.cur.fetchall()
        self.MaaRunner.data = [list(row) for row in self.data_]
        self.MaaRunner.mode = mode

        # 启动执行线程
        self.MainTimer.is_maa_run = True
        self.MaaRunner.start()

    def maa_ender(self, mode):
        """中止MAA线程"""

        self.MaaRunner.requestInterruption()
        self.MaaRunner.wait()

        self.MainTimer.is_maa_run = False

        self.maa_running_set(mode)

    def maa_running_set(self, mode):
        """处理MAA运行过程中的GUI组件变化"""

        if "开始" in mode:

            self.MaaRunner.accomplish.disconnect()
            self.user_add.setEnabled(False)
            self.user_del.setEnabled(False)
            self.user_switch.setEnabled(False)
            self.user_changeset.setEnabled(False)
            self.set_maa.setEnabled(False)
            # self.update_user_info("read_only")

            if mode == "日常代理_开始":
                self.MaaRunner.accomplish.connect(
                    lambda: self.maa_ender("日常代理_结束")
                )
                self.check_start.setEnabled(False)
                self.run_now.clicked.disconnect()
                self.run_now.setText("结束运行")
                self.run_now.clicked.connect(lambda: self.maa_ender("日常代理_结束"))

            elif mode == "人工排查_开始":
                self.MaaRunner.accomplish.connect(
                    lambda: self.maa_ender("人工排查_结束")
                )
                self.run_now.setEnabled(False)
                self.check_start.clicked.disconnect()
                self.check_start.setText("中止排查")
                self.check_start.clicked.connect(
                    lambda: self.maa_ender("人工排查_结束")
                )

            elif mode == "设置MAA_全局_开始" or mode == "设置MAA_用户_开始":
                self.MaaRunner.accomplish.connect(
                    lambda: self.maa_ender("设置MAA_结束")
                )
                self.run_now.setEnabled(False)
                self.check_start.setEnabled(False)

        elif "结束" in mode:

            shutil.copy(
                f"{self.app_path}/data/MAAconfig/Default/gui.json",
                f"{self.config["Default"]["MaaSet.path"]}/config",
            )
            self.user_add.setEnabled(True)
            self.user_del.setEnabled(True)
            self.user_switch.setEnabled(True)
            self.user_changeset.setEnabled(True)
            self.set_maa.setEnabled(True)
            # self.update_user_info("editable")

            if mode == "日常代理_结束":

                self.check_start.setEnabled(True)
                self.run_now.clicked.disconnect()
                self.run_now.setText("立即执行")
                self.run_now.clicked.connect(lambda: self.maa_starter("日常代理"))

            elif mode == "人工排查_结束":

                self.run_now.setEnabled(True)
                self.check_start.clicked.disconnect()
                self.check_start.setText("开始排查")
                self.check_start.clicked.connect(lambda: self.maa_starter("人工排查"))

            elif mode == "设置MAA_结束":

                self.run_now.setEnabled(True)
                self.check_start.setEnabled(True)

    def check_version(self):
        """检查版本更新，调起文件下载进程"""

        # 从本地版本信息文件获取当前版本信息
        with open(self.version_path, "r", encoding="utf-8") as f:
            version_current = json.load(f)
        main_version_current = list(
            map(int, version_current["main_version"].split("."))
        )
        updater_version_current = list(
            map(int, version_current["updater_version"].split("."))
        )
        # 检查更新器是否存在
        if not os.path.exists(f"{self.app_path}/Updater.exe"):
            updater_version_current = [0, 0, 0, 0]

        # 从远程服务器获取最新版本信息
        try:
            response = requests.get(
                "https://ghp.ci/https://github.com/DLmaster361/AUTO_MAA/blob/main/res/version.json"
            )
        except Exception as e:
            QMessageBox.critical(
                self.ui,
                "错误",
                f"获取版本信息时出错：\n{e}",
            )
            return None
        version_remote = response.json()
        main_version_remote = list(map(int, version_remote["main_version"].split(".")))
        updater_version_remote = list(
            map(int, version_remote["updater_version"].split("."))
        )

        # 有版本更新
        if (main_version_remote > main_version_current) or (
            updater_version_remote > updater_version_current
        ):
            # 询问是否开始版本更新
            choice = QMessageBox.question(
                self.ui,
                "版本更新",
                f"发现新版本：\n    主程序：{self.version_text(main_version_current)} --> {self.version_text(main_version_remote)}\n    更新器：{self.version_text(updater_version_current)} --> {self.version_text(updater_version_remote)}\n    更新说明：\n{version_remote['announcement'].replace("\n","\n        ")}\n\n是否开始更新？\n\n    注意：主程序更新时AUTO_MAA将自动关闭",
            )
            if choice == QMessageBox.No:
                return None

            # 更新更新器
            if updater_version_remote > updater_version_current:
                # 创建更新进程
                self.updater = Updater.Updater(
                    self.app_path,
                    "AUTO_MAA更新器",
                    version_remote["updater_download_url"],
                    version_remote["updater_version"],
                )
                # 完成更新器的更新后更新主程序
                if main_version_remote > main_version_current:
                    self.updater.update_process.accomplish.connect(self.update_main)
                # 显示更新页面
                self.updater.ui.show()

            # 更新主程序
            elif main_version_remote > main_version_current:
                self.update_main()

        # 无版本更新
        else:
            self.push_notification("已是最新版本~", " ", " ", 10)

    def update_main(self):
        """更新主程序"""

        subprocess.Popen(
            f"{self.app_path}/Updater.exe",
            shell=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.close()
        app.quit()

    def version_text(self, version_numb):
        """将版本号列表转为可读的文本信息"""

        if version_numb[3] == 0:
            version = f"v{'.'.join(str(_) for _ in version_numb[0:3])}"
        else:
            version = f"v{'.'.join(str(_) for _ in version_numb[0:3])}_beta"
        return version

    def push_notification(self, title, message, ticker, t):
        """推送系统通知"""

        notification.notify(
            title=title,
            message=message,
            app_name="AUTO_MAA",
            app_icon=f"{self.app_path}/gui/ico/AUTO_MAA.ico",
            timeout=t,
            ticker=ticker,
            toast=True,
        )

    def send_mail(self, title, content):
        """使用官方专用邮箱推送邮件通知"""

        # 第三方 SMTP 服务配置
        mail_host = "smtp.163.com"  # 设置服务器
        mail_sender = "AUTO_MAA_server@163.com"  # 用户名
        mail_key = "SYrq87nDLD4RNB5T"  # 授权码 24/11/15

        # 定义邮件正文
        message = MIMEText(content, "plain", "utf-8")
        message["From"] = formataddr(
            (Header("AUTO_MAA通知服务", "utf-8").encode(), "AUTO_MAA_server@163.com")
        )  # 发件人显示的名字
        message["To"] = formataddr(
            (
                Header("AUTO_MAA用户", "utf-8").encode(),
                self.config["Default"]["SelfSet.MailAddress"],
            )
        )  # 收件人显示的名字
        message["Subject"] = Header(title, "utf-8")

        try:
            smtpObj = smtplib.SMTP_SSL(mail_host, 465)  # 465为SMTP_SSL默认端口
            smtpObj.login(mail_sender, mail_key)
            smtpObj.sendmail(
                mail_sender,
                self.config["Default"]["SelfSet.MailAddress"],
                message.as_string(),
            )
        except smtplib.SMTPException as e:
            QMessageBox.critical(self.ui, "错误", f"发送邮件时出错：\n{e}")
        finally:
            smtpObj.quit()

    def give_config(self):
        """同步配置文件到子线程"""

        self.MainTimer.config = self.config


class AUTO_MAA(QMainWindow):

    def __init__(self):
        super(AUTO_MAA, self).__init__()

        # 创建主窗口
        self.main = Main()
        self.setCentralWidget(self.main.ui)
        self.setWindowIcon(QIcon(f"{self.main.app_path}/gui/ico/AUTO_MAA.ico"))
        self.setWindowTitle("AUTO_MAA")

        # 创建系统托盘及其菜单
        self.tray = QSystemTrayIcon(
            QIcon(f"{self.main.app_path}/gui/ico/AUTO_MAA.ico"), self
        )
        self.tray_menu = QMenu()

        # 显示主界面菜单项
        show_main = self.tray_menu.addAction("显示主界面")
        show_main.triggered.connect(self.show_main)

        # 开始任务菜单项
        start_task_1 = self.tray_menu.addAction("运行日常代理")
        start_task_1.triggered.connect(lambda: self.start_task("日常代理"))

        start_task_2 = self.tray_menu.addAction("运行人工排查")
        start_task_2.triggered.connect(lambda: self.start_task("人工排查"))

        # 退出主程序菜单项
        kill = self.tray_menu.addAction("退出主程序")
        kill.triggered.connect(self.kill_main)

        # 设置托盘菜单
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self.on_tray_activated)

        self.set_ui("配置")

    def show_tray(self):
        """最小化到托盘"""
        self.set_ui("保存")
        self.hide()
        self.tray.show()

    def show_main(self):
        """显示主界面"""
        self.set_ui("配置")
        self.tray.hide()

    def on_tray_activated(self, reason):
        """双击返回主界面"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_main()

    def start_task(self, mode):
        """调起对应任务"""
        if self.main.MainTimer.is_maa_run:
            self.main.push_notification(
                f"无法运行{mode}！",
                "当前已有任务正在运行，请在该任务结束后重试",
                "当前已有任务正在运行，请在该任务结束后重试",
                10,
            )
        else:
            self.main.maa_starter(mode)

    def kill_main(self):
        """退出主程序"""
        self.close()
        app.quit()

    def set_ui(self, mode):
        """设置窗口相关属性"""

        # 保存窗口相关属性
        if mode == "保存":

            self.main.config["Default"][
                "SelfSet.UIsize"
            ] = f"{self.geometry().width()}x{self.geometry().height()}"
            self.main.config["Default"][
                "SelfSet.UIlocation"
            ] = f"{self.geometry().x()}x{self.geometry().y()}"
            if self.isMaximized():
                self.main.config["Default"]["SelfSet.UImaximized"] = "True"
            else:
                self.main.config["Default"]["SelfSet.UImaximized"] = "False"
            with open(self.main.config_path, "w", encoding="utf-8") as f:
                json.dump(self.main.config, f, indent=4)

        # 配置窗口相关属性
        elif mode == "配置":

            size = list(
                map(int, self.main.config["Default"]["SelfSet.UIsize"].split("x"))
            )
            location = list(
                map(int, self.main.config["Default"]["SelfSet.UIlocation"].split("x"))
            )
            self.setGeometry(location[0], location[1], size[0], size[1])
            if self.main.config["Default"]["SelfSet.UImaximized"] == "True":
                self.showMinimized()
                self.showMaximized()
            elif self.main.config["Default"]["SelfSet.UImaximized"] == "False":
                self.showMinimized()
                self.showNormal()
            else:
                self.showMinimized()
                self.show()

    def changeEvent(self, event: QtCore.QEvent):
        """重写后的 changeEvent"""

        # 最小化到托盘功能实现
        if event.type() == QtCore.QEvent.WindowStateChange:
            if self.windowState() & QtCore.Qt.WindowMinimized:
                if self.main.config["Default"]["SelfSet.IfToTray"] == "True":
                    self.show_tray()

        # 保留其它 changeEvent 方法
        return super().changeEvent(event)

    def closeEvent(self, event: QCloseEvent):
        """清理残余进程"""

        self.set_ui("保存")

        # 清理各功能线程
        self.main.MainTimer.requestInterruption()
        self.main.MainTimer.quit()
        self.main.MainTimer.wait()
        self.main.MaaRunner.requestInterruption()
        self.main.MaaRunner.quit()
        self.main.MaaRunner.wait()

        # 关闭数据库连接
        self.main.cur.close()
        self.main.db.close()

        event.accept()


def server_date():
    """获取当前的服务器日期"""

    dt = datetime.datetime.now()
    if dt.time() < datetime.datetime.min.time().replace(hour=4):
        dt = dt - datetime.timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


if __name__ == "__main__":

    app = QApplication(sys.argv)
    window = AUTO_MAA()
    sys.exit(app.exec())
