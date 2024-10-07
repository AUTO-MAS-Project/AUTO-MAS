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

from PySide6.QtWidgets import (
    QWidget,
    QApplication,
    QInputDialog,
    QMessageBox,
    QLineEdit,
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
from PySide6.QtGui import QIcon
from PySide6 import QtCore
from functools import partial
import sqlite3
import json
import datetime
import os
import sys
import ctypes
import hashlib
import subprocess
import time
import random
import secrets
import winreg
from Crypto.Cipher import AES
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from Crypto.Util.Padding import pad, unpad

uiLoader = QUiLoader()


class MaaRunner(QtCore.QThread):

    question = QtCore.Signal()
    update_gui = QtCore.Signal(str, str, str, str, str)
    update_user_info = QtCore.Signal(list, list, list, list, list)
    accomplish = QtCore.Signal()
    app_path = os.path.dirname(os.path.realpath(sys.argv[0])).replace(
        "\\", "/"
    )  # 获取软件自身的路径
    if_run = False

    def __init__(
        self, set_path, log_path, maa_path, routine, annihilation, num, data, mode
    ):
        super(MaaRunner, self).__init__()
        self.set_path = set_path
        self.log_path = log_path
        self.maa_path = maa_path
        self.routine = routine
        self.annihilation = annihilation
        self.num = num
        self.data = data
        self.mode = mode

    def run(self):
        """主进程，运行MAA代理进程"""
        self.if_run = True
        curdate = server_date()
        begin_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        over_uid = []
        error_uid = []
        all_uid = [
            self.data[i][13]
            for i in range(len(self.data))
            if (self.data[i][2] > 0 and self.data[i][3] == "y")
        ]
        # 日常代理模式
        if self.mode == "日常代理":
            # 执行情况预处理
            for i in all_uid:
                if self.data[i][4] != curdate:
                    self.data[i][4] = curdate
                    self.data[i][12] = 0
                self.data[i][0] += "_第" + str(self.data[i][12] + 1) + "次代理"
            # 开始代理
            for uid in all_uid:
                if not self.if_run:
                    break
                # 初始化代理情况记录和模式替换记录
                run_book = [False for _ in range(2)]
                mode_book = ["日常代理_剿灭", "日常代理_日常"]
                # 尝试次数循环
                for i in range(self.num):
                    if not self.if_run:
                        break
                    # 剿灭-日常模式循环
                    for j in range(2):
                        if not self.if_run:
                            break
                        if j == 0 and self.data[uid][8] == "n":
                            run_book[0] = True
                            continue
                        if run_book[j]:
                            continue
                        # 配置MAA
                        self.set_maa(mode_book[j], uid)
                        # 创建MAA任务
                        maa = subprocess.Popen([self.maa_path])
                        # 记录当前时间
                        start_time = datetime.datetime.now()
                        # 记录是否超时的标记
                        self.if_time_out = False
                        # 更新运行信息
                        wait_uid = [
                            _
                            for _ in all_uid
                            if (not _ in over_uid + error_uid + [uid])
                        ]
                        # 监测MAA运行状态
                        while self.if_run:
                            # 获取MAA日志
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
                            # 判断是否超时
                            if len(logs) > 0:
                                last_time = datetime.datetime.now()
                                for index in range(-1, 0 - len(logs) - 1, -1):
                                    try:
                                        last_time = datetime.datetime.strptime(
                                            logs[index][1:20], "%Y-%m-%d %H:%M:%S"
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
                            self.update_gui.emit(
                                self.data[uid][0]
                                + "_第"
                                + str(i + 1)
                                + "次_"
                                + mode_book[j][5:7],
                                "\n".join([self.data[_][0] for _ in wait_uid]),
                                "\n".join([self.data[_][0] for _ in over_uid]),
                                "\n".join([self.data[_][0] for _ in error_uid]),
                                log,
                            )
                            # 判断MAA程序运行状态
                            result = self.if_maa_success(log, mode_book[j])
                            if result == "Success!":
                                run_book[j] = True
                                self.update_gui.emit(
                                    self.data[uid][0]
                                    + "_第"
                                    + str(i + 1)
                                    + "次_"
                                    + mode_book[j][5:7],
                                    "\n".join([self.data[_][0] for _ in wait_uid]),
                                    "\n".join([self.data[_][0] for _ in over_uid]),
                                    "\n".join([self.data[_][0] for _ in error_uid]),
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
                                    self.data[uid][0]
                                    + "_第"
                                    + str(i + 1)
                                    + "次_"
                                    + mode_book[j][5:7],
                                    "\n".join([self.data[_][0] for _ in wait_uid]),
                                    "\n".join([self.data[_][0] for _ in over_uid]),
                                    "\n".join([self.data[_][0] for _ in error_uid]),
                                    result,
                                )
                                os.system("taskkill /F /T /PID " + str(maa.pid))
                                if self.if_run:
                                    time.sleep(10)
                                break
                    if run_book[0] and run_book[1]:
                        if self.data[uid][12] == 0:
                            self.data[uid][2] -= 1
                        self.data[uid][12] += 1
                        over_uid.append(uid)
                        break
                if not (run_book[0] and run_book[1]):
                    error_uid.append(uid)
        # 人工排查模式
        elif self.mode == "人工排查":
            # 标记是否需要启动模拟器
            if_strat_app = True
            # 标识排查模式
            for i in all_uid:
                self.data[i][0] += "_排查模式"
            # 开始排查
            for uid in all_uid:
                if not self.if_run:
                    break
                run_book = [False for _ in range(2)]
                # 启动重试循环
                while self.if_run:
                    # 配置MAA
                    if if_strat_app:
                        self.set_maa("人工排查_启动模拟器", uid)
                        if_strat_app = False
                    else:
                        self.set_maa("人工排查_仅切换账号", uid)
                    # 创建MAA任务
                    maa = subprocess.Popen([self.maa_path])
                    # 记录当前时间
                    start_time = datetime.datetime.now()
                    # 更新运行信息
                    wait_uid = [
                        _ for _ in all_uid if (not _ in over_uid + error_uid + [uid])
                    ]
                    # 监测MAA运行状态
                    while self.if_run:
                        # 获取MAA日志
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
                        # 合并日志
                        log = "".join(logs)
                        # 更新MAA日志
                        self.update_gui.emit(
                            self.data[uid][0],
                            "\n".join([self.data[_][0] for _ in wait_uid]),
                            "\n".join([self.data[_][0] for _ in over_uid]),
                            "\n".join([self.data[_][0] for _ in error_uid]),
                            log,
                        )
                        # 判断MAA程序运行状态
                        result = self.if_maa_success(log, "人工排查")
                        if result == "Success!":
                            run_book[0] = True
                            self.update_gui.emit(
                                self.data[uid][0],
                                "\n".join([self.data[_][0] for _ in wait_uid]),
                                "\n".join([self.data[_][0] for _ in over_uid]),
                                "\n".join([self.data[_][0] for _ in error_uid]),
                                "检测到MAA进程成功登录PRTS",
                            )
                            break
                        elif result == "Wait":
                            # 检测时间间隔
                            time.sleep(1)
                        else:
                            self.update_gui.emit(
                                self.data[uid][0],
                                "\n".join([self.data[_][0] for _ in wait_uid]),
                                "\n".join([self.data[_][0] for _ in over_uid]),
                                "\n".join([self.data[_][0] for _ in error_uid]),
                                result,
                            )
                            os.system("taskkill /F /T /PID " + str(maa.pid))
                            if_strat_app = True
                            if self.if_run:
                                time.sleep(10)
                            break
                    if run_book[0]:
                        break
                    elif self.if_run:
                        self.question_title = "操作提示"
                        self.question_info = "MAA未能正确登录到PRTS，是否重试？"
                        self.question_choice = "wait"
                        self.question.emit()
                        while self.question_choice == "wait":
                            time.sleep(1)
                        if self.question_choice == "No":
                            break
                if run_book[0] and self.if_run:
                    self.question_title = "操作提示"
                    self.question_info = "请检查用户代理情况，如无异常请按下确认键。"
                    self.question_choice = "wait"
                    self.question.emit()
                    while self.question_choice == "wait":
                        time.sleep(1)
                    if self.question_choice == "Yes":
                        run_book[1] = True
                if run_book[0] and run_book[1]:
                    if "未通过人工排查" in self.data[uid][11]:
                        self.data[uid][11] = self.data[uid][11].replace(
                            "未通过人工排查|", ""
                        )
                    over_uid.append(uid)
                elif not (run_book[0] and run_book[1]):
                    if not "未通过人工排查" in self.data[uid][11]:
                        self.data[uid][11] = "未通过人工排查|" + self.data[uid][11]
                    error_uid.append(uid)
        if not self.if_run:
            os.system("taskkill /F /T /PID " + str(maa.pid))
        # 更新用户数据
        days = [self.data[_][2] for _ in all_uid]
        lasts = [self.data[_][4] for _ in all_uid]
        notes = [self.data[_][11] for _ in all_uid]
        numbs = [self.data[_][12] for _ in all_uid]
        self.update_user_info.emit(all_uid, days, lasts, notes, numbs)
        # 保存运行日志
        end_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.app_path + "/log.txt", "w", encoding="utf-8") as f:
            print("任务开始时间：" + begin_time + "，结束时间：" + end_time, file=f)
            print(
                "已完成数："
                + str(len(over_uid))
                + "，未完成数："
                + str(len(error_uid) + len(wait_uid))
                + "\n",
                file=f,
            )
            if len(error_uid) != 0:
                print(self.mode[2:4] + "未成功的用户：", file=f)
                print("\n".join([self.data[_][0] for _ in error_uid]), file=f)
            wait_uid = [_ for _ in all_uid if (not _ in over_uid + error_uid)]
            if len(wait_uid) != 0:
                print("\n未开始" + self.mode[2:4] + "的用户：", file=f)
                print("\n".join([self.data[_][0] for _ in wait_uid]), file=f)
        # 恢复GUI运行面板
        with open(self.app_path + "/log.txt", "r", encoding="utf-8") as f:
            end_log = f.read()
        self.update_gui.emit("", "", "", "", end_log)
        self.accomplish.emit()
        self.if_run = False

    def if_maa_success(self, log, mode):
        """判断MAA程序运行状态"""
        if "日常代理" in mode:
            if mode == "日常代理_日常" and "任务出错: Fight" in log:
                return "检测到MAA未能实际执行任务\n正在中止相关程序\n请等待10s"
            elif "任务已全部完成！" in log:
                return "Success!"
            elif (
                ("请检查连接设置或尝试重启模拟器与 ADB 或重启电脑" in log)
                or ("已停止" in log)
                or ("MaaAssistantArknights GUI exited" in log)
            ):
                return "检测到MAA进程异常\n正在中止相关程序\n请等待10s"
            elif self.if_time_out:
                return "检测到MAA进程超时\n正在中止相关程序\n请等待10s"
            elif not self.if_run:
                return "您中止了本次任务\n正在中止相关程序\n请等待"
            else:
                return "Wait"
        elif mode == "人工排查":
            if "完成任务: StartUp" in log:
                return "Success!"
            elif (
                ("请检查连接设置或尝试重启模拟器与 ADB 或重启电脑" in log)
                or ("已停止" in log)
                or ("MaaAssistantArknights GUI exited" in log)
            ):
                return "检测到MAA进程异常\n正在中止相关程序\n请等待10s"
            elif not self.if_run:
                return "您中止了本次任务\n正在中止相关程序\n请等待"
            else:
                return "Wait"

    def set_maa(self, mode, uid):
        """配置MAA运行参数"""
        with open(self.set_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 人工排查配置
        if mode == "人工排查_启动模拟器":
            data["Configurations"]["Default"][
                "MainFunction.PostActions"
            ] = "8"  # 完成后退出MAA
            data["Configurations"]["Default"][
                "Start.RunDirectly"
            ] = "True"  # 启动MAA后直接运行
            data["Configurations"]["Default"][
                "Start.StartEmulator"
            ] = "True"  # 启动MAA后自动开启模拟器
            data["Configurations"]["Default"]["Start.AccountName"] = (
                self.data[uid][1][:3] + "****" + self.data[uid][1][7:]
            )  # 账号切换
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
            ] = "False"  # 生息演算        # 人工排查配置
        if mode == "人工排查_仅切换账号":
            data["Configurations"]["Default"][
                "MainFunction.PostActions"
            ] = "8"  # 完成后无退出MAA
            data["Configurations"]["Default"][
                "Start.RunDirectly"
            ] = "True"  # 启动MAA后直接运行
            data["Configurations"]["Default"][
                "Start.StartEmulator"
            ] = "False"  # 启动MAA后自动开启模拟器
            data["Configurations"]["Default"]["Start.AccountName"] = (
                self.data[uid][1][:3] + "****" + self.data[uid][1][7:]
            )  # 账号切换
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
        # 剿灭代理配置
        elif mode == "日常代理_剿灭":
            data["Configurations"]["Default"][
                "MainFunction.PostActions"
            ] = "12"  # 完成后退出MAA和模拟器
            data["Configurations"]["Default"][
                "Start.RunDirectly"
            ] = "True"  # 启动MAA后直接运行
            data["Configurations"]["Default"][
                "Start.StartEmulator"
            ] = "True"  # 启动MAA后自动开启模拟器
            data["Configurations"]["Default"]["Start.AccountName"] = (
                self.data[uid][1][:3] + "****" + self.data[uid][1][7:]
            )  # 账号切换
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
            data["Configurations"]["Default"]["MainFunction.Stage2"] = ""  # 备选关卡1
            data["Configurations"]["Default"]["MainFunction.Stage3"] = ""  # 备选关卡2
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
            data["Configurations"]["Default"][
                "MainFunction.PostActions"
            ] = "12"  # 完成后退出MAA和模拟器
            data["Configurations"]["Default"][
                "Start.RunDirectly"
            ] = "True"  # 启动MAA后直接运行
            data["Configurations"]["Default"][
                "Start.StartEmulator"
            ] = "True"  # 启动MAA后自动开启模拟器
            data["Configurations"]["Default"]["Start.AccountName"] = (
                self.data[uid][1][:3] + "****" + self.data[uid][1][7:]
            )  # 账号切换
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
            if self.data[uid][5] == "-":
                data["Configurations"]["Default"]["MainFunction.Stage1"] = ""
            else:
                data["Configurations"]["Default"]["MainFunction.Stage1"] = self.data[
                    uid
                ][5]
            # 备选关卡1
            if self.data[uid][6] == "-":
                data["Configurations"]["Default"]["MainFunction.Stage2"] = ""
            else:
                data["Configurations"]["Default"]["MainFunction.Stage2"] = self.data[
                    uid
                ][6]
            # 备选关卡2
            if self.data[uid][7] == "-":
                data["Configurations"]["Default"]["MainFunction.Stage3"] = ""
            else:
                data["Configurations"]["Default"]["MainFunction.Stage3"] = self.data[
                    uid
                ][7]
            data["Configurations"]["Default"][
                "Fight.RemainingSanityStage"
            ] = ""  # 剩余理智关卡
            # 连战次数
            if self.data[uid][5] == "1-7":
                data["Configurations"]["Default"]["MainFunction.Series.Quantity"] = "6"
            else:
                data["Configurations"]["Default"]["MainFunction.Series.Quantity"] = "1"
            data["Configurations"]["Default"][
                "Penguin.IsDrGrandet"
            ] = "False"  # 博朗台模式
            data["Configurations"]["Default"][
                "GUI.CustomStageCode"
            ] = "True"  # 手动输入关卡名
            # 备选关卡
            if self.data[uid][6] == "-" and self.data[uid][7] == "-":
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
            if self.data[uid][9] == "-":
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
                ] = self.data[uid][
                    9
                ]  # 自定义基建配置文件地址
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

    def run(self):
        """主功能代码，实现定时执行以及相关配置信息的实时同步"""
        while True:
            self.get_config.emit()
            self.set_system()
            time_set = [
                self.config["Default"]["TimeSet.run" + str(_ + 1)]
                for _ in range(10)
                if self.config["Default"]["TimeSet.set" + str(_ + 1)] == "True"
            ]
            curtime = datetime.datetime.now().strftime("%H:%M")
            if (curtime in time_set) and not self.is_maa_run:
                self.start_for_timer.emit()
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
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)


class Main(QWidget):

    app_path = os.path.dirname(os.path.realpath(sys.argv[0])).replace(
        "\\", "/"
    )  # 获取软件自身的路径

    def __init__(self, PASSWARD=""):
        super().__init__()

        self.database_path = self.app_path + "/data/data.db"
        self.config_path = self.app_path + "/config/gui.json"
        self.key_path = self.app_path + "/data/key"
        self.gameid_path = self.app_path + "/data/gameid.txt"
        self.PASSWORD = PASSWARD
        self.if_update_database = True
        self.if_update_config = True
        self.user_column = [
            "admin",
            "number",
            "day",
            "status",
            "last",
            "game",
            "game_1",
            "game_2",
            "annihilation",
            "infrastructure",
            "password",
            "notes",
            "numb",
            "uid",
        ]

        self.ui = uiLoader.load(self.app_path + "/gui/ui/main.ui")
        self.ui.setWindowTitle("AUTO_MAA")
        self.ui.setWindowIcon(QIcon(self.app_path + "/res/AUTO_MAA.ico"))
        # 检查文件完整性
        if not os.path.exists(self.database_path) or not os.path.exists(
            self.config_path
        ):
            self.initialize()
        self.check_config()
        with open(self.config_path, "r") as f:
            self.config = json.load(f)
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
        # 初始化数据库连接
        self.db = sqlite3.connect(self.database_path)
        self.cur = self.db.cursor()
        # 初始化控件
        self.user_list = self.ui.findChild(QTableWidget, "tableWidget_userlist")
        self.user_list.itemChanged.connect(self.change_user_Item)

        self.user_add = self.ui.findChild(QPushButton, "pushButton_new")
        self.user_add.clicked.connect(self.add_user)

        self.user_del = self.ui.findChild(QPushButton, "pushButton_del")
        self.user_del.clicked.connect(self.del_user)

        self.read_PASSWORD = self.ui.findChild(QPushButton, "pushButton_password")
        self.read_PASSWORD.clicked.connect(lambda: self.read("key"))

        self.refresh = self.ui.findChild(QPushButton, "pushButton_refresh")
        self.refresh.clicked.connect(lambda: self.update_user_info("clear"))

        self.run_now = self.ui.findChild(QPushButton, "pushButton_runnow")
        self.run_now.clicked.connect(self.routine_starter)

        self.check_start = self.ui.findChild(QPushButton, "pushButton_checkstart")
        self.check_start.clicked.connect(self.check_starter)

        self.maa_path = self.ui.findChild(QLineEdit, "lineEdit_MAApath")
        self.maa_path.textChanged.connect(self.change_config)

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

        self.run_text = self.ui.findChild(QTextBrowser, "textBrowser_run")
        self.wait_text = self.ui.findChild(QTextBrowser, "textBrowser_wait")
        self.over_text = self.ui.findChild(QTextBrowser, "textBrowser_over")
        self.error_text = self.ui.findChild(QTextBrowser, "textBrowser_error")
        self.log_text = self.ui.findChild(QTextBrowser, "textBrowser_log")

        self.start_time = []
        for i in range(10):
            listx = []
            listx.append(self.ui.findChild(QCheckBox, "checkBox_t" + str(i + 1)))
            listx.append(self.ui.findChild(QTimeEdit, "timeEdit_" + str(i + 1)))
            self.start_time.append(listx)
            self.start_time[i][0].stateChanged.connect(self.change_config)
            self.start_time[i][1].timeChanged.connect(self.change_config)

        self.change_password = self.ui.findChild(
            QPushButton, "pushButton_changePASSWORD"
        )
        self.change_password.clicked.connect(self.change_PASSWORD)
        # 初始化线程
        self.set_path_ = self.config["Default"]["MaaSet.path"] + "/config/gui.json"
        self.log_path_ = self.config["Default"]["MaaSet.path"] + "/debug/gui.log"
        self.maa_path_ = self.config["Default"]["MaaSet.path"] + "/MAA.exe"
        self.routine_ = self.config["Default"]["TimeLimit.routine"]
        self.annihilation_ = self.config["Default"]["TimeLimit.annihilation"]
        self.num_ = self.config["Default"]["TimesLimit.run"]
        self.cur.execute("SELECT * FROM adminx WHERE True")
        self.data_ = self.cur.fetchall()
        self.data_ = [list(row) for row in self.data_]

        self.MaaRunner = MaaRunner(
            self.set_path_,
            self.log_path_,
            self.maa_path_,
            self.routine_,
            self.annihilation_,
            self.num_,
            self.data_,
            "未知",
        )
        self.MaaRunner.question.connect(lambda: self.read("question_runner"))
        self.MaaRunner.update_gui.connect(self.update_board)
        self.MaaRunner.update_user_info.connect(self.change_user_info)
        self.MaaRunner.accomplish.connect(self.routine_ender)

        self.MainTimer = MainTimer(self.config)
        self.MainTimer.get_config.connect(self.give_config)
        self.MainTimer.start_for_timer.connect(self.routine_starter)
        self.MainTimer.start()

        # 载入GUI数据
        self.update_user_info("normal")
        self.update_config()

    def initialize(self):
        """初始化程序的配置文件"""
        # 检查目录
        if not os.path.exists(self.app_path + "/data"):
            os.makedirs(self.app_path + "/data")
        if not os.path.exists(self.app_path + "/config"):
            os.makedirs(self.app_path + "/config")
        # 生成用户数据库
        if not os.path.exists(self.database_path):
            db = sqlite3.connect(self.database_path)
            cur = db.cursor()
            cur.execute(
                "CREATE TABLE adminx(admin text,number text,day int,status text,last date,game text,game_1 text,game_2 text,annihilation text,infrastructure text,password byte,notes text,numb int,uid int)"
            )
            cur.execute("CREATE TABLE version(v text)")
            cur.execute("INSERT INTO version VALUES(?)", ("v1.0",))
            db.commit()
            cur.close()
            db.close()
        # 生成配置文件
        if not os.path.exists(self.config_path):
            config = {"Default": {}}
            with open(self.config_path, "w") as f:
                json.dump(config, f, indent=4)

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
        ]
        # 导入配置文件
        with open(self.config_path, "r") as f:
            config = json.load(f)
        # 检查并补充缺失的字段
        for i in range(len(config_list)):
            if not config_list[i][0] in config["Default"]:
                config["Default"][config_list[i][0]] = config_list[i][1]
        # 导出配置文件
        with open(self.config_path, "w") as f:
            json.dump(config, f, indent=4)

    def get_PASSWORD(self):
        """配置管理密钥"""
        # 检查目录
        if not os.path.exists(self.app_path + "/data/key"):
            os.makedirs(self.app_path + "/data/key")
        # 生成RSA密钥对
        key = RSA.generate(2048)
        public_key_local = key.publickey()
        private_key = key
        # 保存RSA公钥
        with open(self.app_path + "/data/key/public_key.pem", "wb") as f:
            f.write(public_key_local.exportKey())
        # 生成密钥转换与校验随机盐
        PASSWORD_salt = secrets.token_hex(random.randint(32, 1024))
        with open(
            self.app_path + "/data/key/PASSWORDsalt.txt", "w", encoding="utf-8"
        ) as f:
            print(PASSWORD_salt, file=f)
        verify_salt = secrets.token_hex(random.randint(32, 1024))
        with open(
            self.app_path + "/data/key/verifysalt.txt", "w", encoding="utf-8"
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
        with open(self.app_path + "/data/key/AES_password_verify.bin", "wb") as f:
            f.write(AES_password_verify)
        # AES-256加密RSA私钥并保存密文
        AES_key = AES.new(AES_password, AES.MODE_ECB)
        private_key_local = AES_key.encrypt(pad(private_key.exportKey(), 32))
        with open(self.app_path + "/data/key/private_key.bin", "wb") as f:
            f.write(private_key_local)

    def encryptx(self, note):
        """加密数据"""
        # 读取RSA公钥
        with open(self.app_path + "/data/key/public_key.pem", "rb") as f:
            public_key_local = RSA.import_key(f.read())
        # 使用RSA公钥对数据进行加密
        cipher = PKCS1_OAEP.new(public_key_local)
        encrypted = cipher.encrypt(note.encode("utf-8"))
        return encrypted

    def decryptx(self, note):
        """解密数据"""
        # 读入RSA私钥密文、盐与校验哈希值
        with open(self.app_path + "/data/key/private_key.bin", "rb") as f:
            private_key_local = f.read().strip()
        with open(
            self.app_path + "/data/key/PASSWORDsalt.txt", "r", encoding="utf-8"
        ) as f:
            PASSWORD_salt = f.read().strip()
        with open(
            self.app_path + "/data/key/verifysalt.txt", "r", encoding="utf-8"
        ) as f:
            verify_salt = f.read().strip()
        with open(self.app_path + "/data/key/AES_password_verify.bin", "rb") as f:
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
                                    new_data.append(self.decryptx(data[i][10]))
                                # 使用新管理密钥重新加密
                                self.PASSWORD = PASSWORD_new
                                self.get_PASSWORD()
                                for i in range(len(data)):
                                    self.cur.execute(
                                        "UPDATE adminx SET password = ? WHERE uid = ?",
                                        (self.encryptx(new_data[i]), i),
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

        self.cur.execute("SELECT * FROM adminx WHERE True")
        data = self.cur.fetchall()

        if operation == "clear":
            self.PASSWORD = ""

        self.if_update_database = False
        self.user_list.setRowCount(len(data))
        for i, row in enumerate(data):
            for j, value in enumerate(row):
                if j in [3, 8]:
                    item = QComboBox()
                    item.addItems(["启用", "禁用"])
                    if value == "y":
                        item.setCurrentIndex(0)
                    elif value == "n":
                        item.setCurrentIndex(1)
                    item.currentIndexChanged.connect(
                        partial(self.change_user_CellWidget, i, j)
                    )
                elif j == 4:
                    curdate = server_date()
                    if curdate != value:
                        item = QTableWidgetItem("今日未代理")
                    else:
                        item = QTableWidgetItem("今日已代理" + str(data[i][12]) + "次")
                    item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
                elif j == 9:
                    item = QTableWidgetItem(str(value).replace("\\", "/"))
                elif j == 10:
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
                if j in [3, 8]:
                    self.user_list.setCellWidget(i, j, item)
                else:
                    self.user_list.setItem(i, j, item)
        self.if_update_database = True
        self.user_list.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # self.user_list.resizeColumnsToContents()
        # self.user_list.resizeRowsToContents()
        # self.user_list.horizontalHeader().setStretchLastSection(True)

    def update_config(self):
        """将self.config中的程序配置同步至GUI界面"""

        self.if_update_config = False
        self.maa_path.setText(self.config["Default"]["MaaSet.path"].replace("\\", "/"))
        self.routine.setValue(self.config["Default"]["TimeLimit.routine"])
        self.annihilation.setValue(self.config["Default"]["TimeLimit.annihilation"])
        self.num.setValue(self.config["Default"]["TimesLimit.run"])

        self.if_self_start.setChecked(
            bool(self.config["Default"]["SelfSet.IfSelfStart"] == "True")
        )

        self.if_sleep.setChecked(
            bool(self.config["Default"]["SelfSet.IfSleep"] == "True")
        )

        for i in range(10):
            self.start_time[i][0].setChecked(
                bool(self.config["Default"]["TimeSet.set" + str(i + 1)] == "True")
            )
            time = QtCore.QTime(
                int(self.config["Default"]["TimeSet.run" + str(i + 1)][:2]),
                int(self.config["Default"]["TimeSet.run" + str(i + 1)][3:]),
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
        self.log_text.ensureCursorVisible()
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

    def add_user(self):
        """添加一位新用户"""
        self.cur.execute(
            "INSERT INTO adminx VALUES(?,?,0,'y','2000-01-01',?,?,?,'y',?,?,'无',0,?)",
            (
                "新用户",
                "12312341234",
                "1-7",
                "-",
                "-",
                "-",
                self.encryptx("未设置"),
                self.user_list.rowCount(),
            ),
        )
        self.db.commit()
        self.update_user_info("normal")

    def del_user(self):
        """删除选中的首位用户"""
        row = self.user_list.currentRow()
        self.cur.execute("SELECT * FROM adminx WHERE uid=?", (row,))
        data = self.cur.fetchall()
        if len(data) == 0:
            QMessageBox.critical(self.ui, "错误", "请选中一个用户后再执行删除操作")
        else:
            choice = QMessageBox.question(
                self.ui, "确认", "确定要删除用户 " + data[0][0] + " 吗？"
            )

            if choice == QMessageBox.Yes:
                self.cur.execute("DELETE FROM adminx WHERE uid = ?", (row,))
                self.db.commit()
                for i in range(row + 1, self.user_list.rowCount()):
                    self.cur.execute(
                        "UPDATE adminx SET uid = ? WHERE uid = ?", (i - 1, i)
                    )
                    self.db.commit()
                self.update_user_info("normal")

    def change_user_Item(self, item):
        """将GUI中发生修改的用户配置表中的一般信息同步至本地数据库"""
        if self.if_update_database:
            text = item.text()
            if item.column() in [2, 12]:
                text = int(text)
            if item.column() in [5, 6, 7]:
                # 导入与应用特殊关卡规则
                games = {}
                if os.path.exists(self.gameid_path):
                    with open(self.gameid_path, encoding="utf-8") as f:
                        gameids = f.readlines()
                        for line in gameids:
                            if "：" in line:
                                game_in, game_out = line.split("：", 1)
                                games[game_in.strip()] = game_out.strip()
                text = games.get(text, text)
            if item.column() == 9:
                text = text.replace("\\", "/")
            if item.column() == 10:
                text = self.encryptx(text)
            if text != "":
                self.cur.execute(
                    f"UPDATE adminx SET {self.user_column[item.column()]} = ? WHERE uid = ?",
                    (text, item.row()),
                )
            self.db.commit()
            self.update_user_info("normal")

    def change_user_CellWidget(self, row, column, index):
        """将GUI中发生修改的用户配置表中的CellWidget类信息同步至本地数据库"""
        if self.if_update_database:
            if index == 0:
                self.cur.execute(
                    f"UPDATE adminx SET {self.user_column[column]} = ? WHERE uid = ?",
                    ("y", row),
                )
            elif index == 1:
                self.cur.execute(
                    f"UPDATE adminx SET {self.user_column[column]} = ? WHERE uid = ?",
                    ("n", row),
                )
            self.db.commit()
            self.update_user_info("normal")

    def change_user_info(self, all_uid, days, lasts, notes, numbs):
        """将代理完成后发生改动的用户信息同步至本地数据库"""
        for i in range(len(all_uid)):
            self.cur.execute(
                "UPDATE adminx SET day=? WHERE uid=?", (days[i], all_uid[i])
            )
            self.cur.execute(
                "UPDATE adminx SET last=? WHERE uid=?", (lasts[i], all_uid[i])
            )
            self.cur.execute(
                "UPDATE adminx SET notes=? WHERE uid=?", (notes[i], all_uid[i])
            )
            self.cur.execute(
                "UPDATE adminx SET numb=? WHERE uid=?", (numbs[i], all_uid[i])
            )
        self.db.commit()
        self.update_user_info("normal")

    def change_config(self):
        """将GUI中发生修改的程序配置同步至self.config变量"""
        if self.if_update_config:
            self.config["Default"]["MaaSet.path"] = self.maa_path.text().replace(
                "\\", "/"
            )
            self.config["Default"]["TimeLimit.routine"] = self.routine.value()
            self.config["Default"]["TimeLimit.annihilation"] = self.annihilation.value()
            self.config["Default"]["TimesLimit.run"] = self.num.value()

            if self.if_sleep.isChecked():
                self.config["Default"]["SelfSet.IfSleep"] = "True"
            else:
                self.config["Default"]["SelfSet.IfSleep"] = "False"

            if self.if_self_start.isChecked():
                self.config["Default"]["SelfSet.IfSelfStart"] = "True"
            else:
                self.config["Default"]["SelfSet.IfSelfStart"] = "False"

            for i in range(10):
                if self.start_time[i][0].isChecked():
                    self.config["Default"]["TimeSet.set" + str(i + 1)] = "True"
                else:
                    self.config["Default"]["TimeSet.set" + str(i + 1)] = "False"
                time = self.start_time[i][1].time().toString("HH:mm")
                self.config["Default"]["TimeSet.run" + str(i + 1)] = time
            with open(self.config_path, "w") as f:
                json.dump(self.config, f, indent=4)
            self.update_config()

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
                return 0
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

    def closeEvent(self, event):
        """清理残余进程"""
        self.MainTimer.quit()
        self.MaaRunner.if_run = False
        self.MaaRunner.wait()
        self.cur.close()
        self.db.close()
        super().closeEvent(event)

    def routine_ender(self):
        """中止日常代理进程"""
        self.MaaRunner.if_run = False
        self.MaaRunner.wait()
        self.MainTimer.is_maa_run = False
        self.check_start.setEnabled(True)
        self.run_now.clicked.disconnect()
        self.run_now.setText("立即执行")
        self.run_now.clicked.connect(self.routine_starter)

    def routine_starter(self):
        """启动MaaRunner线程运行日常代理任务"""
        if self.config["Default"]["MaaSet.path"] == "":
            QMessageBox.critical(self.ui, "错误", "MAA路径未设置！")
            return None
        # 运行过程中修改部分组件
        self.check_start.setEnabled(False)
        self.run_now.clicked.disconnect()
        self.run_now.setText("结束运行")
        self.run_now.clicked.connect(self.routine_ender)
        # 配置参数
        self.MaaRunner.set_path = (
            self.config["Default"]["MaaSet.path"] + "/config/gui.json"
        )
        self.MaaRunner.log_path = (
            self.config["Default"]["MaaSet.path"] + "/debug/gui.log"
        )
        self.MaaRunner.maa_path = self.config["Default"]["MaaSet.path"] + "/MAA.exe"
        self.MaaRunner.routine = self.config["Default"]["TimeLimit.routine"]
        self.MaaRunner.annihilation = self.config["Default"]["TimeLimit.annihilation"]
        self.MaaRunner.num = self.config["Default"]["TimesLimit.run"]
        self.cur.execute("SELECT * FROM adminx WHERE True")
        self.data_ = self.cur.fetchall()
        self.MaaRunner.data = [list(row) for row in self.data_]
        self.MaaRunner.mode = "日常代理"
        # 启动执行线程
        self.MainTimer.is_maa_run = True
        self.MaaRunner.start()

    def check_ender(self):
        """中止人工排查进程"""
        self.MaaRunner.if_run = False
        self.MaaRunner.wait()
        self.MainTimer.is_maa_run = False
        self.run_now.setEnabled(True)
        self.check_start.clicked.disconnect()
        self.check_start.setText("开始排查")
        self.check_start.clicked.connect(self.check_starter)

    def check_starter(self):
        """启动MaaRunner线程运行人工排查任务"""
        if self.config["Default"]["MaaSet.path"] == "":
            QMessageBox.critical(self.ui, "错误", "MAA路径未设置！")
            return None
        # 运行过程中修改部分组件
        self.run_now.setEnabled(False)
        self.check_start.clicked.disconnect()
        self.check_start.setText("中止排查")
        self.check_start.clicked.connect(self.check_ender)
        # 配置参数
        self.MaaRunner.set_path = (
            self.config["Default"]["MaaSet.path"] + "/config/gui.json"
        )
        self.MaaRunner.log_path = (
            self.config["Default"]["MaaSet.path"] + "/debug/gui.log"
        )
        self.MaaRunner.maa_path = self.config["Default"]["MaaSet.path"] + "/MAA.exe"
        self.cur.execute("SELECT * FROM adminx WHERE True")
        self.data_ = self.cur.fetchall()
        self.MaaRunner.data = [list(row) for row in self.data_]
        self.MaaRunner.mode = "人工排查"
        # 启动执行线程
        self.MainTimer.is_maa_run = True
        self.MaaRunner.start()

    def give_config(self):
        """同步配置文件到子线程"""
        self.MainTimer.config = self.config


class AUTO_MAA(QApplication):
    def __init__(self):
        super().__init__()

        self.main = Main()
        self.main.ui.show()


def server_date():
    """获取当前的服务器日期"""
    dt = datetime.datetime.now()
    if dt.time() < datetime.datetime.min.time().replace(hour=4):
        dt = dt - datetime.timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


if __name__ == "__main__":
    app = AUTO_MAA()
    app.exec()
