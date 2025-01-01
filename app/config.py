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
AUTO_MAA配置管理
v4.2
作者：DLmaster_361
"""

import sqlite3
import json
import os
import sys
from pathlib import Path
from typing import Dict, Union


class AppConfig:

    def __init__(self) -> None:

        self.app_path = Path.cwd()  # 获取软件根目录
        self.app_path_sys = os.path.realpath(sys.argv[0])  # 获取软件自身的路径
        self.app_name = os.path.basename(self.app_path)  # 获取软件自身的名称

        self.database_path = self.app_path / "data/data.db"
        self.config_path = self.app_path / "config/gui.json"
        self.key_path = self.app_path / "data/key"
        self.gameid_path = self.app_path / "data/gameid.txt"
        self.version_path = self.app_path / "resources/version.json"

        # 检查文件完整性
        self.initialize()
        self.check_config()
        self.check_database()

    def initialize(self) -> None:
        """初始化程序的配置文件"""

        # 检查目录
        (self.app_path / "config").mkdir(parents=True, exist_ok=True)
        (self.app_path / "data/MAAconfig/simple").mkdir(parents=True, exist_ok=True)
        (self.app_path / "data/MAAconfig/beta").mkdir(parents=True, exist_ok=True)
        (self.app_path / "data/MAAconfig/Default").mkdir(parents=True, exist_ok=True)

        # 生成版本信息文件
        if not self.version_path.exists():
            version = {
                "main_version": "0.0.0.0",
                "updater_version": "0.0.0.0",
            }
            with self.version_path.open(mode="w", encoding="utf-8") as f:
                json.dump(version, f, indent=4)

        # 生成配置文件
        if not self.config_path.exists():
            config = {"Default": {}}
            with self.config_path.open(mode="w", encoding="utf-8") as f:
                json.dump(config, f, indent=4)

        # 生成预设gameid替换方案文件
        if not self.gameid_path.exists():
            self.gameid_path.write_text(
                "龙门币：CE-6\n技能：CA-5\n红票：AP-5\n经验：LS-6\n剿灭模式：Annihilation",
                encoding="utf-8",
            )

    def check_config(self) -> None:
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
            ["SelfSet.IfSendMail.OnlyError", "False"],
            ["SelfSet.IfSilence", "False"],
            ["SelfSet.BossKey", ""],
            ["SelfSet.IfToTray", "False"],
            ["SelfSet.UIsize", "1200x700"],
            ["SelfSet.UIlocation", "100x100"],
            ["SelfSet.UImaximized", "False"],
            ["SelfSet.MainIndex", 2],
        ]

        # 导入配置文件
        with self.config_path.open(mode="r", encoding="utf-8") as f:
            config = json.load(f)

        # 检查并补充缺失的字段
        for i in range(len(config_list)):
            if not config_list[i][0] in config["Default"]:
                config["Default"][config_list[i][0]] = config_list[i][1]

        # 初始化配置信息
        self.content: Dict[str, Dict[str, Union[str, int]]] = config

        # 导出配置文件
        self.save_config()

    def check_database(self) -> None:
        """检查用户数据库文件并处理数据库版本更新"""

        # 生成用户数据库
        if not self.database_path.exists():
            db = sqlite3.connect(self.database_path)
            cur = db.cursor()
            cur.execute(
                "CREATE TABLE adminx(admin text,id text,server text,day int,status text,last date,game text,game_1 text,game_2 text,routine text,annihilation text,infrastructure text,password byte,notes text,numb int,mode text,uid int)"
            )
            cur.execute("CREATE TABLE version(v text)")
            cur.execute("INSERT INTO version VALUES(?)", ("v1.3",))
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
        # v1.2-->v1.3
        if version[0][0] == "v1.2":
            cur.execute("ALTER TABLE adminx RENAME COLUMN routines TO routine")
            cur.execute("DELETE FROM version WHERE v = ?", ("v1.2",))
            cur.execute("INSERT INTO version VALUES(?)", ("v1.3",))
            db.commit()
        cur.close()
        db.close()

    def open_database(self) -> None:
        """打开数据库"""

        self.db = sqlite3.connect(self.database_path)
        self.cur = self.db.cursor()

    def close_database(self) -> None:
        """关闭数据库"""

        self.cur.close()
        self.db.close()

    def save_config(self) -> None:
        """保存配置文件"""

        with self.config_path.open(mode="w", encoding="utf-8") as f:
            json.dump(self.content, f, indent=4)
