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
import hashlib
import subprocess
import time
import random
import secrets
from Crypto.Cipher import AES
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from Crypto.Util.Padding import pad, unpad

uiLoader = QUiLoader()


class MaaRunner(QtCore.QThread):

    UpGui = QtCore.Signal(str, str, str, str, str)
    UpUserInfo = QtCore.Signal(list, list, list, list)
    Accomplish = QtCore.Signal()
    ifRun = False

    def __init__(self, SetPath, LogPath, MaaPath, Routine, Annihilation, Num, data):
        super(MaaRunner, self).__init__()
        self.SetPath = SetPath
        self.LogPath = LogPath
        self.MaaPath = MaaPath
        self.Routine = Routine
        self.Annihilation = Annihilation
        self.Num = Num
        self.data = data

    def run(self):
        self.ifRun = True
        curdate = ServerDate()
        begintime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        OverUid = []
        ErrorUid = []
        AllUid = [
            self.data[i][13]
            for i in range(len(self.data))
            if (self.data[i][2] > 0 and self.data[i][3] == "y")
        ]
        # MAA预配置
        self.SetMaa(0, 0)
        # 执行情况预处理
        for i in AllUid:
            if self.data[i][4] != curdate:
                self.data[i][4] = curdate
                self.data[i][12] = 0
            self.data[i][0] += "_第" + str(self.data[i][12] + 1) + "次代理"
        # 开始代理
        for uid in AllUid:
            if not self.ifRun:
                break
            runbook = [False for k in range(2)]
            for i in range(self.Num):
                if not self.ifRun:
                    break
                for j in range(2):
                    if not self.ifRun:
                        break
                    if (j == 0 and self.data[uid][8] == "n") or runbook[j]:
                        continue
                    # 配置MAA
                    self.SetMaa(j + 1, uid)
                    # 创建MAA任务
                    maa = subprocess.Popen([self.MaaPath])
                    # 记录当前时间
                    StartTime = datetime.datetime.now()
                    # 初始化log记录列表
                    if j == 0:
                        logx = [k for k in range(self.Annihilation * 60)]
                    elif j == 1:
                        logx = [k for k in range(self.Routine * 60)]
                    logi = 0
                    # 更新运行信息
                    WaitUid = [
                        idx for idx in AllUid if (not idx in OverUid + ErrorUid + [uid])
                    ]
                    # 监测MAA运行状态
                    while True:
                        # 更新MAA日志
                        with open(self.LogPath, "r", encoding="utf-8") as f:
                            logs = []
                            for entry in f:
                                try:
                                    entry_time = datetime.datetime.strptime(
                                        entry[1:20], "%Y-%m-%d %H:%M:%S"
                                    )
                                    if entry_time > StartTime:
                                        logs.append(entry)
                                except ValueError:
                                    pass
                            log = "".join(logs)
                            if j == 0:
                                self.UpGui.emit(
                                    self.data[uid][0] + "_第" + str(i + 1) + "次_剿灭",
                                    "\n".join([self.data[k][0] for k in WaitUid]),
                                    "\n".join([self.data[k][0] for k in OverUid]),
                                    "\n".join([self.data[k][0] for k in ErrorUid]),
                                    log,
                                )
                            elif j == 1:
                                self.UpGui.emit(
                                    self.data[uid][0] + "_第" + str(i + 1) + "次_日常",
                                    "\n".join([self.data[k][0] for k in WaitUid]),
                                    "\n".join([self.data[k][0] for k in OverUid]),
                                    "\n".join([self.data[k][0] for k in ErrorUid]),
                                    log,
                                )
                            if len(logs) != 0:
                                logx[logi] = logs[-1]
                                logi = (logi + 1) % len(logx)
                        # 判断MAA程序运行状态
                        if "任务已全部完成！" in log:
                            runbook[j] = True
                            self.UpGui.emit(
                                self.data[uid][0] + "_第" + str(i + 1) + "次_日常",
                                "\n".join([self.data[k][0] for k in WaitUid]),
                                "\n".join([self.data[k][0] for k in OverUid]),
                                "\n".join([self.data[k][0] for k in ErrorUid]),
                                "检测到MAA进程完成代理任务\n正在等待相关程序结束\n请等待10s",
                            )
                            maa.wait()
                            time.sleep(10)
                            break
                        elif (
                            ("请检查连接设置或尝试重启模拟器与 ADB 或重启电脑" in log)
                            or ("已停止" in log)
                            or ("MaaAssistantArknights GUI exited" in log)
                            or self.TimeOut(logx)
                            or not self.ifRun
                        ):
                            # 打印中止信息
                            if (
                                (
                                    "请检查连接设置或尝试重启模拟器与 ADB 或重启电脑"
                                    in log
                                )
                                or ("已停止" in log)
                                or ("MaaAssistantArknights GUI exited" in log)
                            ):
                                info = "检测到MAA进程异常\n正在中止相关程序\n请等待10s"
                            elif self.TimeOut(logx):
                                info = "检测到MAA进程超时\n正在中止相关程序\n请等待10s"
                            elif not self.ifRun:
                                info = "您中止了本次任务\n正在中止相关程序\n请等待"
                            self.UpGui.emit(
                                self.data[uid][0] + "_第" + str(i + 1) + "次_日常",
                                "\n".join([self.data[k][0] for k in WaitUid]),
                                "\n".join([self.data[k][0] for k in OverUid]),
                                "\n".join([self.data[k][0] for k in ErrorUid]),
                                info,
                            )
                            os.system("taskkill /F /T /PID " + str(maa.pid))
                            maa.wait()
                            if self.ifRun:
                                time.sleep(10)
                            break
                        # 检测时间间隔
                        time.sleep(1)
                if runbook[0] and runbook[1]:
                    if self.data[uid][12] == 0:
                        self.data[uid][2] -= 1
                    self.data[uid][12] += 1
                    OverUid.append(uid)
                    break
            if not (runbook[0] and runbook[1]):
                ErrorUid.append(uid)
        # 更新用户数据
        days = [self.data[k][2] for k in AllUid]
        lasts = [self.data[k][4] for k in AllUid]
        numbs = [self.data[k][12] for k in AllUid]
        self.UpUserInfo.emit(AllUid, days, lasts, numbs)
        # 保存运行日志
        endtime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("log.txt", "w", encoding="utf-8") as f:
            print("任务开始时间：" + begintime + "，结束时间：" + endtime, file=f)
            print(
                "已完成数：" + str(len(OverUid)) + "，未完成数：" + str(len(ErrorUid)),
                file=f,
            )
            ErrorUid = [idx for idx in AllUid if (not idx in OverUid)]
            if len(ErrorUid) != 0:
                print("代理未完成的用户：", file=f)
                print("\n".join([self.data[k][0] for k in ErrorUid]), file=f)
            WaitUid = [idx for idx in AllUid if (not idx in OverUid + ErrorUid + [uid])]
            if len(WaitUid) != 0:
                print("未代理的用户：", file=f)
                print("\n".join([self.data[k][0] for k in WaitUid]), file=f)
        with open("log.txt", "r", encoding="utf-8") as f:
            EndLog = f.read()
        # 恢复GUI运行面板
        self.UpGui.emit("", "", "", "", EndLog)
        self.Accomplish.emit()
        self.ifRun = False

    # 配置MAA运行参数
    def SetMaa(self, s, uid):
        with open(self.SetPath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if s == 0:
            data["Configurations"]["Default"][
                "MainFunction.ActionAfterCompleted"
            ] = "ExitEmulatorAndSelf"  # 完成后退出MAA和模拟器
            data["Configurations"]["Default"][
                "Start.RunDirectly"
            ] = "True"  # 启动MAA后直接运行
            data["Configurations"]["Default"][
                "Start.StartEmulator"
            ] = "True"  # 启动MAA后自动开启模拟器
        elif s == 1:
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
        elif s == 2:
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
            data["Configurations"]["Default"]["MainFunction.Stage1"] = self.data[uid][
                5
            ]  # 主关卡
            data["Configurations"]["Default"]["MainFunction.Stage2"] = self.data[uid][
                6
            ]  # 备选关卡1
            data["Configurations"]["Default"]["MainFunction.Stage3"] = self.data[uid][
                7
            ]  # 备选关卡2
            data["Configurations"]["Default"][
                "Fight.RemainingSanityStage"
            ] = ""  # 剩余理智关卡
            if self.data[uid][5] == "1-7":
                data["Configurations"]["Default"][
                    "MainFunction.Series.Quantity"
                ] = "6"  # 连战次数
            else:
                data["Configurations"]["Default"][
                    "MainFunction.Series.Quantity"
                ] = "1"  # 连战次数
            data["Configurations"]["Default"][
                "Penguin.IsDrGrandet"
            ] = "False"  # 博朗台模式
            data["Configurations"]["Default"][
                "GUI.CustomStageCode"
            ] = "True"  # 手动输入关卡名
            if self.data[uid][6] == "-" and self.data[uid][7] == "-":
                data["Configurations"]["Default"][
                    "GUI.UseAlternateStage"
                ] = "False"  # 不使用备选关卡
            else:
                data["Configurations"]["Default"][
                    "GUI.UseAlternateStage"
                ] = "True"  # 使用备选关卡
            data["Configurations"]["Default"][
                "Fight.UseRemainingSanityStage"
            ] = "False"  # 使用剩余理智
            data["Configurations"]["Default"][
                "Fight.UseExpiringMedicine"
            ] = "True"  # 无限吃48小时内过期的理智药
        with open(self.SetPath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return True

    # 超时判断
    def TimeOut(self, logx):
        log0 = logx[0]
        for i in logx:
            if i != log0:
                return False
        return True


class MaaTimer(QtCore.QThread):

    GetConfig = QtCore.Signal()
    StartForTimer = QtCore.Signal()
    isMaaRun = False

    def __init__(self, config):
        super(MaaTimer, self).__init__()
        self.config = config

    def run(self):
        while True:
            self.GetConfig.emit()
            TimeSet = [
                self.config["Default"]["TimeSet.run" + str(k + 1)]
                for k in range(10)
                if self.config["Default"]["TimeSet.set" + str(k + 1)] == "True"
            ]
            curtime = datetime.datetime.now().strftime("%H:%M")
            if (curtime in TimeSet) and not self.isMaaRun:
                self.StartForTimer.emit()
            time.sleep(1)


class Main(QWidget):

    def __init__(self, PASSWARD=""):
        super().__init__()

        self.DatabasePath = "data/data.db"
        self.ConfigPath = "config/gui.json"
        self.KeyPath = "data/key"
        self.GameidPath = "data/gameid.txt"
        self.PASSWORD = PASSWARD
        self.ifUpDatabase = True
        self.ifUpConfig = True
        self.UserColumn = [
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

        self.ui = uiLoader.load("gui/ui/main.ui")
        self.ui.setWindowTitle("AUTO_MAA")
        self.ui.setWindowIcon(QIcon("res/AUTO_MAA.ico"))
        # 检查文件完整性
        if not os.path.exists(self.DatabasePath) or not os.path.exists(self.ConfigPath):
            self.initialize()
        with open(self.ConfigPath, "r") as f:
            self.config = json.load(f)
        if not os.path.exists(self.KeyPath):
            while True:
                self.PASSWORD, okPressed = QInputDialog.getText(
                    self.ui,
                    "请设置管理密钥",
                    "未检测到管理密钥，请设置您的管理密钥：",
                    QLineEdit.Password,
                    "",
                )
                if okPressed and self.PASSWORD != "":
                    self.getPASSWORD()
                    break
                else:
                    choice = QMessageBox.question(
                        self.ui, "确认", "您没有输入管理密钥，确定要暂时跳过这一步吗？"
                    )
                    if choice == QMessageBox.Yes:
                        break
        # 初始化数据库连接
        self.db = sqlite3.connect(self.DatabasePath)
        self.cur = self.db.cursor()
        # 初始化控件
        self.userlist = self.ui.findChild(QTableWidget, "tableWidget_userlist")
        self.userlist.itemChanged.connect(self.ChangeUserItem)

        self.adduser = self.ui.findChild(QPushButton, "pushButton_new")
        self.adduser.clicked.connect(self.AddUser)

        self.deluser = self.ui.findChild(QPushButton, "pushButton_del")
        self.deluser.clicked.connect(self.DelUser)

        self.readPASSWORD = self.ui.findChild(QPushButton, "pushButton_password")
        self.readPASSWORD.clicked.connect(lambda: self.read("key"))

        self.refresh = self.ui.findChild(QPushButton, "pushButton_refresh")
        self.refresh.clicked.connect(lambda: self.UpdateTable("clear"))

        self.runnow = self.ui.findChild(QPushButton, "pushButton_runnow")
        self.runnow.clicked.connect(self.RunStarter)

        self.MaaPath = self.ui.findChild(QLineEdit, "lineEdit_MAApath")
        self.MaaPath.textChanged.connect(self.ChangeConfig)

        self.routine = self.ui.findChild(QSpinBox, "spinBox_routine")
        self.routine.valueChanged.connect(self.ChangeConfig)

        self.annihilation = self.ui.findChild(QSpinBox, "spinBox_annihilation")
        self.annihilation.valueChanged.connect(self.ChangeConfig)

        self.num = self.ui.findChild(QSpinBox, "spinBox_numt")
        self.num.valueChanged.connect(self.ChangeConfig)

        self.RunText = self.ui.findChild(QTextBrowser, "textBrowser_run")
        self.WaitText = self.ui.findChild(QTextBrowser, "textBrowser_wait")
        self.OverText = self.ui.findChild(QTextBrowser, "textBrowser_over")
        self.ErrorText = self.ui.findChild(QTextBrowser, "textBrowser_error")
        self.LogText = self.ui.findChild(QTextBrowser, "textBrowser_log")

        self.StartTime = []
        for i in range(10):
            listx = []
            listx.append(self.ui.findChild(QCheckBox, "checkBox_t" + str(i + 1)))
            listx.append(self.ui.findChild(QTimeEdit, "timeEdit_" + str(i + 1)))
            self.StartTime.append(listx)
            self.StartTime[i][0].stateChanged.connect(self.ChangeConfig)
            self.StartTime[i][1].timeChanged.connect(self.ChangeConfig)

        self.ChangePassword = self.ui.findChild(
            QPushButton, "pushButton_changePASSWORD"
        )
        self.ChangePassword.clicked.connect(self.changePASSWORD)
        # 初始化线程
        self.SetPath_ = self.config["Default"]["MaaSet.path"] + "/config/gui.json"
        self.LogPath_ = self.config["Default"]["MaaSet.path"] + "/debug/gui.log"
        self.MaaPath_ = self.config["Default"]["MaaSet.path"] + "/MAA.exe"
        self.Routine_ = self.config["Default"]["TimeLimit.routine"]
        self.Annihilation_ = self.config["Default"]["TimeLimit.annihilation"]
        self.Num_ = self.config["Default"]["TimesLimit.run"]
        self.cur.execute("SELECT * FROM adminx WHERE True")
        self.data_ = self.cur.fetchall()
        self.data_ = [list(row) for row in self.data_]

        self.MaaRunner = MaaRunner(
            self.SetPath_,
            self.LogPath_,
            self.MaaPath_,
            self.Routine_,
            self.Annihilation_,
            self.Num_,
            self.data_,
        )
        self.MaaRunner.UpGui.connect(self.UpdateBoard)
        self.MaaRunner.UpUserInfo.connect(self.ChangeUserInfo)
        self.MaaRunner.Accomplish.connect(self.end)

        self.MaaTimer = MaaTimer(self.config)
        self.MaaTimer.GetConfig.connect(self.GiveConfig)
        self.MaaTimer.StartForTimer.connect(self.RunStarter)
        self.MaaTimer.start()

        # 载入GUI数据
        self.UpdateTable("normal")
        self.UpdateConfig()

    # 初始化
    def initialize(self):
        # 检查目录
        if not os.path.exists("data"):
            os.makedirs("data")
        if not os.path.exists("config"):
            os.makedirs("config")
        # 生成用户数据库
        if not os.path.exists(self.DatabasePath):
            db = sqlite3.connect(self.DatabasePath)
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
        if not os.path.exists(self.ConfigPath):
            config = {
                "Default": {
                    "TimeSet.set1": "False",
                    "TimeSet.run1": "00:00",
                    "TimeSet.set2": "False",
                    "TimeSet.run2": "00:00",
                    "TimeSet.set3": "False",
                    "TimeSet.run3": "00:00",
                    "TimeSet.set4": "False",
                    "TimeSet.run4": "00:00",
                    "TimeSet.set5": "False",
                    "TimeSet.run5": "00:00",
                    "TimeSet.set6": "False",
                    "TimeSet.run6": "00:00",
                    "TimeSet.set7": "False",
                    "TimeSet.run7": "00:00",
                    "TimeSet.set8": "False",
                    "TimeSet.run8": "00:00",
                    "TimeSet.set9": "False",
                    "TimeSet.run9": "00:00",
                    "TimeSet.set10": "False",
                    "TimeSet.run10": "00:00",
                    "MaaSet.path": "",
                    "TimeLimit.routine": 10,
                    "TimeLimit.annihilation": 40,
                    "TimesLimit.run": 3,
                }
            }
            with open(self.ConfigPath, "w") as f:
                json.dump(config, f, indent=4)

    # 配置密钥
    def getPASSWORD(self):
        # 检查目录
        if not os.path.exists("data/key"):
            os.makedirs("data/key")
        # 生成RSA密钥对
        key = RSA.generate(2048)
        public_key_local = key.publickey()
        private_key = key
        # 保存RSA公钥
        with open("data/key/public_key.pem", "wb") as f:
            f.write(public_key_local.exportKey())
        # 生成密钥转换与校验随机盐
        PASSWORDsalt = secrets.token_hex(random.randint(32, 1024))
        with open("data/key/PASSWORDsalt.txt", "w", encoding="utf-8") as f:
            print(PASSWORDsalt, file=f)
        verifysalt = secrets.token_hex(random.randint(32, 1024))
        with open("data/key/verifysalt.txt", "w", encoding="utf-8") as f:
            print(verifysalt, file=f)
        # 将管理密钥转化为AES-256密钥
        AES_password = hashlib.sha256(
            (self.PASSWORD + PASSWORDsalt).encode("utf-8")
        ).digest()
        # 生成AES-256密钥校验哈希值并保存
        AES_password_verify = hashlib.sha256(
            AES_password + verifysalt.encode("utf-8")
        ).digest()
        with open("data/key/AES_password_verify.bin", "wb") as f:
            f.write(AES_password_verify)
        # AES-256加密RSA私钥并保存密文
        AES_key = AES.new(AES_password, AES.MODE_ECB)
        private_key_local = AES_key.encrypt(pad(private_key.exportKey(), 32))
        with open("data/key/private_key.bin", "wb") as f:
            f.write(private_key_local)

    # 加密
    def encryptx(self, note):
        # 读取RSA公钥
        with open("data/key/public_key.pem", "rb") as f:
            public_key_local = RSA.import_key(f.read())
        # 使用RSA公钥对数据进行加密
        cipher = PKCS1_OAEP.new(public_key_local)
        encrypted = cipher.encrypt(note.encode("utf-8"))
        return encrypted

    # 解密
    def decryptx(self, note):
        # 读入RSA私钥密文、盐与校验哈希值
        with open("data/key/private_key.bin", "rb") as f:
            private_key_local = f.read().strip()
        with open("data/key/PASSWORDsalt.txt", "r", encoding="utf-8") as f:
            PASSWORDsalt = f.read().strip()
        with open("data/key/verifysalt.txt", "r", encoding="utf-8") as f:
            verifysalt = f.read().strip()
        with open("data/key/AES_password_verify.bin", "rb") as f:
            AES_password_verify = f.read().strip()
        # 将管理密钥转化为AES-256密钥并验证
        AES_password = hashlib.sha256(
            (self.PASSWORD + PASSWORDsalt).encode("utf-8")
        ).digest()
        AES_password_SHA = hashlib.sha256(
            AES_password + verifysalt.encode("utf-8")
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

    # 修改管理密钥
    def changePASSWORD(self):
        # 获取用户信息
        self.cur.execute("SELECT * FROM adminx WHERE True")
        data = self.cur.fetchall()
        if len(data) == 0:
            QMessageBox.information(self.ui, "验证通过", "当前无用户，验证自动通过")
            # 获取新的管理密钥
            while True:
                PASSWORDnew = self.read("newkey")
                if PASSWORDnew == 0:
                    choice = QMessageBox.question(
                        self.ui,
                        "确认",
                        "您没有输入新的管理密钥，是否取消修改管理密钥？",
                    )
                    if choice == QMessageBox.Yes:
                        break
                else:
                    # 修改管理密钥
                    self.PASSWORD = PASSWORDnew
                    self.getPASSWORD()
                    QMessageBox.information(self.ui, "操作成功", "管理密钥修改成功")
                    break
        else:
            # 验证管理密钥
            ifchange = True
            while ifchange:
                if self.read("oldkey"):
                    if self.decryptx(self.encryptx("")) == "管理密钥错误":
                        QMessageBox.critical(self.ui, "错误", "管理密钥错误")
                    else:
                        # 获取新的管理密钥
                        while True:
                            PASSWORDnew = self.read("newkey")
                            if PASSWORDnew == 0:
                                choice = QMessageBox.question(
                                    self.ui,
                                    "确认",
                                    "您没有输入新的管理密钥，是否取消修改管理密钥？",
                                )
                                if choice == QMessageBox.Yes:
                                    ifchange = False
                                    break
                            # 修改管理密钥
                            else:
                                # 使用旧管理密钥解密
                                newdata = []
                                for i in range(len(data)):
                                    newdata.append(self.decryptx(data[i][10]))
                                # 使用新管理密钥重新加密
                                self.PASSWORD = PASSWORDnew
                                self.getPASSWORD()
                                for i in range(len(data)):
                                    self.cur.execute(
                                        "UPDATE adminx SET password = ? WHERE uid = ?",
                                        (self.encryptx(newdata[i]), i),
                                    )
                                self.db.commit()
                                QMessageBox.information(
                                    self.ui, "操作成功", "管理密钥修改成功"
                                )
                                ifchange = False
                                break
                else:
                    choice = QMessageBox.question(
                        self.ui, "确认", "您没有输入管理密钥，是否取消修改管理密钥？"
                    )
                    if choice == QMessageBox.Yes:
                        break

    # 更新GUI用户列表
    def UpdateTable(self, operation):

        self.cur.execute("SELECT * FROM adminx WHERE True")
        data = self.cur.fetchall()

        if operation == "clear":
            self.PASSWORD = ""

        self.ifUpDatabase = False
        self.userlist.setRowCount(len(data))
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
                        partial(self.ChangeUserCellWidget, i, j)
                    )
                elif j == 4:
                    curdate = ServerDate()
                    if curdate != value:
                        item = QTableWidgetItem("今日未代理")
                    else:
                        item = QTableWidgetItem("今日已代理" + str(data[i][12]) + "次")
                    item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
                elif j == 9:
                    item = QTableWidgetItem(str(value))
                    item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
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
                    self.userlist.setCellWidget(i, j, item)
                else:
                    self.userlist.setItem(i, j, item)
        self.ifUpDatabase = True
        self.userlist.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # self.userlist.resizeColumnsToContents()
        # self.userlist.resizeRowsToContents()
        # self.userlist.horizontalHeader().setStretchLastSection(True)

    # 更新GUI程序配置
    def UpdateConfig(self):

        self.ifUpConfig = False
        self.MaaPath.setText(self.config["Default"]["MaaSet.path"].replace("\\", "/"))
        self.routine.setValue(self.config["Default"]["TimeLimit.routine"])
        self.annihilation.setValue(self.config["Default"]["TimeLimit.annihilation"])
        self.num.setValue(self.config["Default"]["TimesLimit.run"])
        for i in range(10):
            self.StartTime[i][0].setChecked(
                bool(self.config["Default"]["TimeSet.set" + str(i + 1)] == "True")
            )
            time = QtCore.QTime(
                int(self.config["Default"]["TimeSet.run" + str(i + 1)][:2]),
                int(self.config["Default"]["TimeSet.run" + str(i + 1)][3:]),
            )
            self.StartTime[i][1].setTime(time)
        self.ifUpConfig = True

    # 更新GUI运行面板
    def UpdateBoard(self, RunText, WaitText, OverText, ErrorText, LogText):
        self.RunText.setPlainText(RunText)
        self.WaitText.setPlainText(WaitText)
        self.OverText.setPlainText(OverText)
        self.ErrorText.setPlainText(ErrorText)
        self.LogText.setPlainText(LogText)
        self.LogText.ensureCursorVisible()
        self.LogText.verticalScrollBar().setValue(
            self.LogText.verticalScrollBar().maximum()
        )

    # 添加用户
    def AddUser(self):
        self.cur.execute(
            "INSERT INTO adminx VALUES(?,?,0,'y','2000-01-01',?,?,?,'y',?,?,'无',0,?)",
            (
                "新用户",
                "12312341234",
                "1-7",
                "-",
                "-",
                "暂不支持",
                self.encryptx("未设置"),
                self.userlist.rowCount(),
            ),
        )
        self.db.commit()
        self.UpdateTable("normal")

    # 删除用户
    def DelUser(self):
        row = self.userlist.currentRow()
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
                for i in range(row + 1, self.userlist.rowCount()):
                    self.cur.execute(
                        "UPDATE adminx SET uid = ? WHERE uid = ?", (i - 1, i)
                    )
                    self.db.commit()
                self.UpdateTable("normal")

    # 修改用户配置1
    def ChangeUserItem(self, item):
        if self.ifUpDatabase:
            text = item.text()
            if item.column() in [2, 12]:
                text = int(text)
            if item.column() in [5, 6, 7]:
                # 导入与应用特殊关卡规则
                games = {}
                if os.path.exists(self.GameidPath):
                    with open(self.GameidPath, encoding="utf-8") as f:
                        gameids = f.readlines()
                        for i in range(len(gameids)):
                            for j in range(len(gameids[i])):
                                if gameids[i][j] == "：" or gameids[i][j] == ":":
                                    gamein = gameids[i][:j]
                                    gameout = gameids[i][j + 1 :]
                                    break
                            games[gamein.strip()] = gameout.strip()
                if text in games:
                    text = games[text]
            if item.column() == 10:
                text = self.encryptx(text)
            if text != "":
                self.cur.execute(
                    f"UPDATE adminx SET {self.UserColumn[item.column()]} = ? WHERE uid = ?",
                    (text, item.row()),
                )
            self.db.commit()
            self.UpdateTable("normal")

    # 修改用户配置2
    def ChangeUserCellWidget(self, row, column, index):
        if self.ifUpDatabase:
            item = self.userlist.cellWidget(row, column)
            if index == 0:
                self.cur.execute(
                    f"UPDATE adminx SET {self.UserColumn[column]} = ? WHERE uid = ?",
                    ("y", row),
                )
            elif index == 1:
                self.cur.execute(
                    f"UPDATE adminx SET {self.UserColumn[column]} = ? WHERE uid = ?",
                    ("n", row),
                )
            self.db.commit()
            self.UpdateTable("normal")

    # 修改用户信息
    def ChangeUserInfo(self, AllUid, days, lasts, numbs):
        for i in range(len(AllUid)):
            self.cur.execute(
                "UPDATE adminx SET day=? WHERE uid=?", (days[i], AllUid[i])
            )
            self.cur.execute(
                "UPDATE adminx SET last=? WHERE uid=?", (lasts[i], AllUid[i])
            )
            self.cur.execute(
                "UPDATE adminx SET numb=? WHERE uid=?", (numbs[i], AllUid[i])
            )
        self.db.commit()
        self.UpdateTable("normal")

    # 修改程序配置
    def ChangeConfig(self):
        if self.ifUpConfig:
            self.config["Default"]["MaaSet.path"] = self.MaaPath.text().replace(
                "\\", "/"
            )
            self.config["Default"]["TimeLimit.routine"] = self.routine.value()
            self.config["Default"]["TimeLimit.annihilation"] = self.annihilation.value()
            self.config["Default"]["TimesLimit.run"] = self.num.value()
            for i in range(10):
                if self.StartTime[i][0].isChecked():
                    self.config["Default"]["TimeSet.set" + str(i + 1)] = "True"
                else:
                    self.config["Default"]["TimeSet.set" + str(i + 1)] = "False"
                time = self.StartTime[i][1].time().toString("HH:mm")
                self.config["Default"]["TimeSet.run" + str(i + 1)] = time
            with open(self.ConfigPath, "w") as f:
                json.dump(self.config, f, indent=4)
            self.UpdateConfig()

    # 读入框
    def read(self, operation):
        # 读入PASSWORD
        if operation == "key":
            self.PASSWORD, okPressed = QInputDialog.getText(
                self.ui, "请输入管理密钥", "管理密钥：", QLineEdit.Password, ""
            )
            if okPressed and self.PASSWORD != "":
                self.UpdateTable("normal")
        elif operation == "oldkey":
            self.PASSWORD, okPressed = QInputDialog.getText(
                self.ui, "请输入旧的管理密钥", "旧管理密钥：", QLineEdit.Password, ""
            )
            if okPressed and self.PASSWORD != "":
                return True
            else:
                return False
        elif operation == "newkey":
            newPASSWORD, okPressed = QInputDialog.getText(
                self.ui, "请输入新的管理密钥", "新管理密钥：", QLineEdit.Password, ""
            )
            if okPressed and newPASSWORD != "":
                return newPASSWORD
            else:
                return 0

    def closeEvent(self, event):
        self.MaaTimer.quit()
        self.MaaRunner.ifRun = False
        self.MaaRunner.wait()
        self.cur.close()
        self.db.close()
        super().closeEvent(event)

    # 中止任务
    def end(self):
        self.MaaRunner.ifRun = False
        self.MaaRunner.wait()
        self.MaaTimer.isMaaRun = False
        self.runnow.clicked.disconnect()
        self.runnow.setText("立即执行")
        self.runnow.clicked.connect(self.RunStarter)

    # 启动MaaRunner线程
    def RunStarter(self):
        if self.config["Default"]["MaaSet.path"] == "":
            QMessageBox.critical(self.ui, "错误", "MAA路径未设置！")
            return None
        # 运行过程中修改部分组件
        self.runnow.clicked.disconnect()
        self.runnow.setText("结束运行")
        self.runnow.clicked.connect(self.end)
        # 配置参数
        self.MaaRunner.SetPath = (
            self.config["Default"]["MaaSet.path"] + "/config/gui.json"
        )
        self.MaaRunner.LogPath = (
            self.config["Default"]["MaaSet.path"] + "/debug/gui.log"
        )
        self.MaaRunner.MaaPath = self.config["Default"]["MaaSet.path"] + "/MAA.exe"
        self.MaaRunner.Routine = self.config["Default"]["TimeLimit.routine"]
        self.MaaRunner.Annihilation = self.config["Default"]["TimeLimit.annihilation"]
        self.MaaRunner.Num = self.config["Default"]["TimesLimit.run"]
        self.cur.execute("SELECT * FROM adminx WHERE True")
        self.data_ = self.cur.fetchall()
        self.MaaRunner.data = [list(row) for row in self.data_]
        # 启动执行线程
        self.MaaTimer.isMaaRun = True
        self.MaaRunner.start()

    def GiveConfig(self):
        self.MaaTimer.config = self.config


class AUTO_MAA(QApplication):
    def __init__(self):
        super().__init__()

        self.main = Main()
        self.main.ui.show()


def ServerDate():
    dt = datetime.datetime.now()
    if dt.time() < datetime.datetime.min.time().replace(hour=4):
        dt = dt - datetime.timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


if __name__ == "__main__":
    app = AUTO_MAA()
    app.exec()
