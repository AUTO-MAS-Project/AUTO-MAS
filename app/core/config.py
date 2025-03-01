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

from loguru import logger
import sqlite3
import json
import sys
import shutil
import re
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path
from qfluentwidgets import (
    QConfig,
    ConfigItem,
    OptionsConfigItem,
    RangeConfigItem,
    FolderValidator,
    BoolValidator,
    RangeValidator,
    OptionsValidator,
    qconfig,
)
from typing import Union, Dict, List


class AppConfig:

    def __init__(self) -> None:

        self.app_path = Path(sys.argv[0]).resolve().parent  # 获取软件根目录
        self.app_path_sys = str(Path(sys.argv[0]).resolve())  # 获取软件自身的路径

        self.log_path = self.app_path / "debug/AUTO_MAA.log"
        self.database_path = self.app_path / "data/data.db"
        self.config_path = self.app_path / "config/config.json"
        self.history_path = self.app_path / "history/main.json"
        self.key_path = self.app_path / "data/key"
        self.gameid_path = self.app_path / "data/gameid.txt"
        self.version_path = self.app_path / "resources/version.json"

        self.PASSWORD = ""
        self.running_list = []
        self.silence_list = []
        self.if_database_opened = False

        # 检查文件完整性
        self.initialize()

    def initialize(self) -> None:
        """初始化程序的配置文件"""

        # 检查目录
        (self.app_path / "config").mkdir(parents=True, exist_ok=True)
        (self.app_path / "data").mkdir(parents=True, exist_ok=True)
        (self.app_path / "debug").mkdir(parents=True, exist_ok=True)
        (self.app_path / "history").mkdir(parents=True, exist_ok=True)

        # 生成版本信息文件
        if not self.version_path.exists():
            version = {
                "main_version": "0.0.0.0",
                "updater_version": "0.0.0.0",
            }
            with self.version_path.open(mode="w", encoding="utf-8") as f:
                json.dump(version, f, ensure_ascii=False, indent=4)

        # 生成预设gameid替换方案文件
        if not self.gameid_path.exists():
            self.gameid_path.write_text(
                "龙门币：CE-6\n技能：CA-5\n红票：AP-5\n经验：LS-6\n剿灭模式：Annihilation",
                encoding="utf-8",
            )

        self.init_logger()
        self.init_config()
        self.check_data()
        logger.info("程序配置管理模块初始化完成")

    def init_logger(self) -> None:
        """初始化日志记录器"""

        logger.remove(0)

        logger.add(
            sink=self.log_path,
            level="DEBUG",
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <level>{message}</level>",
            enqueue=True,
            backtrace=True,
            diagnose=True,
            rotation="1 week",
            retention="1 month",
            compression="zip",
        )
        logger.info("===================================")
        logger.info("AUTO_MAA 主程序")
        logger.info("版本号： v4.2.1.1")
        logger.info(f"根目录： {self.app_path}")
        logger.info("===================================")

        logger.info("日志记录器初始化完成")

    def init_config(self) -> None:
        """初始化配置类"""

        self.global_config = GlobalConfig()
        self.queue_config = QueueConfig()
        self.maa_config = MaaConfig()

        qconfig.load(self.config_path, self.global_config)

        config_list = self.search_config()
        for config in config_list:
            if config[0] == "Maa":
                qconfig.load(config[1], self.maa_config)
                self.maa_config.save()
            elif config[0] == "Queue":
                qconfig.load(config[1], self.queue_config)
                self.queue_config.save()

        logger.info("配置类初始化完成")

    def init_database(self, mode: str) -> None:
        """初始化用户数据库"""

        if mode == "Maa":
            self.cur.execute(
                "CREATE TABLE adminx(admin text,id text,server text,day int,status text,last date,game text,game_1 text,game_2 text,routine text,annihilation text,infrastructure text,password byte,notes text,numb int,mode text,uid int)"
            )
            self.cur.execute("CREATE TABLE version(v text)")
            self.cur.execute("INSERT INTO version VALUES(?)", ("v1.4",))
            self.db.commit()

        logger.info("用户数据库初始化完成")

    def check_data(self) -> None:
        """检查用户数据文件并处理数据文件版本更新"""

        # 生成主数据库
        if not self.database_path.exists():
            db = sqlite3.connect(self.database_path)
            cur = db.cursor()
            cur.execute("CREATE TABLE version(v text)")
            cur.execute("INSERT INTO version VALUES(?)", ("v1.4",))
            db.commit()
            cur.close()
            db.close()

        # 数据文件版本更新
        db = sqlite3.connect(self.database_path)
        cur = db.cursor()
        cur.execute("SELECT * FROM version WHERE True")
        version = cur.fetchall()

        if version[0][0] != "v1.4":
            logger.info("数据文件版本更新开始")
            if_streaming = False
            # v1.0-->v1.1
            if version[0][0] == "v1.0" or if_streaming:
                logger.info("数据文件版本更新：v1.0-->v1.1")
                if_streaming = True
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
            if version[0][0] == "v1.1" or if_streaming:
                logger.info("数据文件版本更新：v1.1-->v1.2")
                if_streaming = True
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
            if version[0][0] == "v1.2" or if_streaming:
                logger.info("数据文件版本更新：v1.2-->v1.3")
                if_streaming = True
                cur.execute("ALTER TABLE adminx RENAME COLUMN routines TO routine")
                cur.execute("DELETE FROM version WHERE v = ?", ("v1.2",))
                cur.execute("INSERT INTO version VALUES(?)", ("v1.3",))
                db.commit()
            # v1.3-->v1.4
            if version[0][0] == "v1.3" or if_streaming:
                logger.info("数据文件版本更新：v1.3-->v1.4")
                if_streaming = True
                (self.app_path / "config/MaaConfig").mkdir(parents=True, exist_ok=True)
                shutil.move(
                    self.app_path / "data/MaaConfig",
                    self.app_path / "config/MaaConfig",
                )
                (self.app_path / "config/MaaConfig/MaaConfig").rename(
                    self.app_path / "config/MaaConfig/脚本_1"
                )
                shutil.copy(
                    self.database_path,
                    self.app_path / "config/MaaConfig/脚本_1/user_data.db",
                )
                cur.execute("DROP TABLE IF EXISTS adminx")
                cur.execute("DELETE FROM version WHERE v = ?", ("v1.3",))
                cur.execute("INSERT INTO version VALUES(?)", ("v1.4",))
                db.commit()
                with (self.app_path / "config/gui.json").open(
                    "r", encoding="utf-8"
                ) as f:
                    info = json.load(f)
                maa_config = {
                    "MaaSet": {
                        "Name": "",
                        "Path": info["Default"]["MaaSet.path"],
                    },
                    "RunSet": {
                        "AnnihilationTimeLimit": info["Default"][
                            "TimeLimit.annihilation"
                        ],
                        "RoutineTimeLimit": info["Default"]["TimeLimit.routine"],
                        "RunTimesLimit": info["Default"]["TimesLimit.run"],
                    },
                }
                with (self.app_path / "config/MaaConfig/脚本_1/config.json").open(
                    "w", encoding="utf-8"
                ) as f:
                    json.dump(maa_config, f, ensure_ascii=False, indent=4)
                config = {
                    "Function": {
                        "BossKey": info["Default"]["SelfSet.BossKey"],
                        "IfAllowSleep": bool(
                            info["Default"]["SelfSet.IfSleep"] == "True"
                        ),
                        "IfSilence": bool(
                            info["Default"]["SelfSet.IfSilence"] == "True"
                        ),
                    },
                    "Notify": {
                        "IfPushPlyer": True,
                        "IfSendErrorOnly": bool(
                            info["Default"]["SelfSet.IfSendMail.OnlyError"] == "True"
                        ),
                        "IfSendMail": bool(
                            info["Default"]["SelfSet.IfSendMail"] == "True"
                        ),
                        "MailAddress": info["Default"]["SelfSet.MailAddress"],
                    },
                    "Start": {
                        "IfRunDirectly": bool(
                            info["Default"]["SelfSet.IfProxyDirectly"] == "True"
                        ),
                        "IfSelfStart": bool(
                            info["Default"]["SelfSet.IfSelfStart"] == "True"
                        ),
                    },
                    "UI": {
                        "IfShowTray": bool(
                            info["Default"]["SelfSet.IfToTray"] == "True"
                        ),
                        "IfToTray": bool(info["Default"]["SelfSet.IfToTray"] == "True"),
                        "location": info["Default"]["SelfSet.UIlocation"],
                        "maximized": bool(
                            info["Default"]["SelfSet.UImaximized"] == "True"
                        ),
                        "size": info["Default"]["SelfSet.UIsize"],
                    },
                    "Update": {"IfAutoUpdate": False},
                }
                with (self.app_path / "config/config.json").open(
                    "w", encoding="utf-8"
                ) as f:
                    json.dump(config, f, ensure_ascii=False, indent=4)
                queue_config = {
                    "QueueSet": {"Enabled": True, "Name": ""},
                    "Queue": {
                        "Member_1": "脚本_1",
                        "Member_10": "禁用",
                        "Member_2": "禁用",
                        "Member_3": "禁用",
                        "Member_4": "禁用",
                        "Member_5": "禁用",
                        "Member_6": "禁用",
                        "Member_7": "禁用",
                        "Member_8": "禁用",
                        "Member_9": "禁用",
                    },
                    "Time": {
                        "TimeEnabled_0": bool(
                            info["Default"]["TimeSet.set1"] == "True"
                        ),
                        "TimeEnabled_1": bool(
                            info["Default"]["TimeSet.set2"] == "True"
                        ),
                        "TimeEnabled_2": bool(
                            info["Default"]["TimeSet.set3"] == "True"
                        ),
                        "TimeEnabled_3": bool(
                            info["Default"]["TimeSet.set4"] == "True"
                        ),
                        "TimeEnabled_4": bool(
                            info["Default"]["TimeSet.set5"] == "True"
                        ),
                        "TimeEnabled_5": bool(
                            info["Default"]["TimeSet.set6"] == "True"
                        ),
                        "TimeEnabled_6": bool(
                            info["Default"]["TimeSet.set7"] == "True"
                        ),
                        "TimeEnabled_7": bool(
                            info["Default"]["TimeSet.set8"] == "True"
                        ),
                        "TimeEnabled_8": bool(
                            info["Default"]["TimeSet.set9"] == "True"
                        ),
                        "TimeEnabled_9": bool(
                            info["Default"]["TimeSet.set10"] == "True"
                        ),
                        "TimeSet_0": info["Default"]["TimeSet.run1"],
                        "TimeSet_1": info["Default"]["TimeSet.run2"],
                        "TimeSet_2": info["Default"]["TimeSet.run3"],
                        "TimeSet_3": info["Default"]["TimeSet.run4"],
                        "TimeSet_4": info["Default"]["TimeSet.run5"],
                        "TimeSet_5": info["Default"]["TimeSet.run6"],
                        "TimeSet_6": info["Default"]["TimeSet.run7"],
                        "TimeSet_7": info["Default"]["TimeSet.run8"],
                        "TimeSet_8": info["Default"]["TimeSet.run9"],
                        "TimeSet_9": info["Default"]["TimeSet.run10"],
                    },
                }
                (self.app_path / "config/QueueConfig").mkdir(
                    parents=True, exist_ok=True
                )
                with (self.app_path / "config/QueueConfig/调度队列_1.json").open(
                    "w", encoding="utf-8"
                ) as f:
                    json.dump(queue_config, f, ensure_ascii=False, indent=4)
                (self.app_path / "config/gui.json").unlink()
            cur.close()
            db.close()
            logger.info("数据文件版本更新完成")

    def search_config(self) -> list:
        """搜索所有子配置文件"""

        config_list = []

        if (self.app_path / "config/MaaConfig").exists():
            for subdir in (self.app_path / "config/MaaConfig").iterdir():
                if subdir.is_dir():
                    config_list.append(["Maa", subdir / "config.json"])

        if (self.app_path / "config/QueueConfig").exists():
            for json_file in (self.app_path / "config/QueueConfig").glob("*.json"):
                config_list.append(["Queue", json_file])

        return config_list

    def open_database(self, mode: str, index: str = None) -> None:
        """打开数据库"""

        self.close_database()
        self.db = sqlite3.connect(
            self.app_path / f"config/{mode}Config/{index}/user_data.db"
        )
        self.cur = self.db.cursor()
        self.if_database_opened = True

    def close_database(self) -> None:
        """关闭数据库"""

        if self.if_database_opened:
            self.cur.close()
            self.db.close()
        self.if_database_opened = False

    def change_user_info(
        self,
        data_path: Path,
        modes: list,
        uids: list,
        days: list,
        lasts: list,
        notes: list,
        numbs: list,
    ) -> None:
        """将代理完成后发生改动的用户信息同步至本地数据库"""

        db = sqlite3.connect(data_path / "user_data.db")
        cur = db.cursor()

        for index in range(len(uids)):
            cur.execute(
                "UPDATE adminx SET day = ? WHERE mode = ? AND uid = ?",
                (days[index], modes[index], uids[index]),
            )
            cur.execute(
                "UPDATE adminx SET last = ? WHERE mode = ? AND uid = ?",
                (lasts[index], modes[index], uids[index]),
            )
            cur.execute(
                "UPDATE adminx SET notes = ? WHERE mode = ? AND uid = ?",
                (notes[index], modes[index], uids[index]),
            )
            cur.execute(
                "UPDATE adminx SET numb = ? WHERE mode = ? AND uid = ?",
                (numbs[index], modes[index], uids[index]),
            )
        db.commit()
        cur.close()
        db.close()

    def save_maa_log(self, log_path: Path, logs: list, maa_result: str) -> None:
        """保存MAA日志"""

        log_path.parent.mkdir(parents=True, exist_ok=True)

        data: Dict[str, Union[str, Dict[str, Union[int, dict]]]] = {
            "recruit_statistics": defaultdict(int),
            "drop_statistics": defaultdict(dict),
            "maa_result": maa_result,
        }

        # 公招统计（仅统计招募到的）
        confirmed_recruit = False
        current_star_level = None
        i = 0
        while i < len(logs):
            if "公招识别结果:" in logs[i]:
                current_star_level = None  # 每次识别公招时清空之前的星级
                i += 1
                while i < len(logs) and "Tags" not in logs[i]:  # 读取所有公招标签
                    i += 1

                if i < len(logs) and "Tags" in logs[i]:  # 识别星级
                    star_match = re.search(r"(\d+)\s*★ Tags", logs[i])
                    if star_match:
                        current_star_level = f"{star_match.group(1)}★"

            if "已确认招募" in logs[i]:  # 只有确认招募后才统计
                confirmed_recruit = True

            if confirmed_recruit and current_star_level:
                data["recruit_statistics"][current_star_level] += 1
                confirmed_recruit = False  # 重置，等待下一次公招
                current_star_level = None  # 清空已处理的星级

            i += 1

        # 掉落统计
        current_stage = None
        stage_drops = {}

        for i, line in enumerate(logs):
            drop_match = re.search(r"([A-Za-z0-9\-]+) 掉落统计:", line)
            if drop_match:
                # 发现新关卡，保存前一个关卡数据
                if current_stage and stage_drops:
                    data["drop_statistics"][current_stage] = stage_drops

                current_stage = drop_match.group(1)
                if current_stage == "WE":
                    current_stage = "剿灭模式"
                stage_drops = {}
                continue

            if current_stage:
                item_match: List[str] = re.findall(
                    r"^(?!\[)([\u4e00-\u9fa5A-Za-z0-9\-]+)\s*:\s*([\d,]+)(?:\s*\(\+[\d,]+\))?",
                    line,
                    re.M,
                )
                for item, total in item_match:
                    # 解析数值时去掉逗号 （如 2,160 -> 2160）
                    total = int(total.replace(",", ""))

                    # 黑名单
                    if item not in [
                        "当前次数",
                        "理智",
                        "最快截图耗时",
                        "专精等级",
                        "剩余时间",
                    ]:
                        stage_drops[item] = total

        # 处理最后一个关卡的掉落数据
        if current_stage and stage_drops:
            data["drop_statistics"][current_stage] = stage_drops

        # 保存日志
        with log_path.open("w", encoding="utf-8") as f:
            f.writelines(logs)
        with log_path.with_suffix(".json").open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        logger.info(f"处理完成：{log_path}")

        self.merge_maa_logs(log_path.parent)

    def merge_maa_logs(self, logs_path: Path) -> None:
        """合并所有 .log 文件"""

        data = {
            "recruit_statistics": defaultdict(int),
            "drop_statistics": defaultdict(dict),
            "maa_result": defaultdict(str),
        }

        for json_file in logs_path.glob("*.json"):

            with json_file.open("r", encoding="utf-8") as f:
                single_data: Dict[str, Union[str, Dict[str, Union[int, dict]]]] = (
                    json.load(f)
                )

            # 合并公招统计
            for star_level, count in single_data["recruit_statistics"].items():
                data["recruit_statistics"][star_level] += count

            # 合并掉落统计
            for stage, drops in single_data["drop_statistics"].items():
                if stage not in data["drop_statistics"]:
                    data["drop_statistics"][stage] = {}  # 初始化关卡

                for item, count in drops.items():

                    if item in data["drop_statistics"][stage]:
                        data["drop_statistics"][stage][item] += count
                    else:
                        data["drop_statistics"][stage][item] = count

            # 合并MAA结果
            data["maa_result"][
                json_file.name.replace(".json", "").replace("-", ":")
            ] = single_data["maa_result"]

        # 生成汇总 JSON 文件
        with logs_path.with_suffix(".json").open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        logger.info(f"统计完成：{logs_path.with_suffix(".json")}")

    def load_maa_logs(
        self, mode: str, json_path: Path
    ) -> Dict[str, Union[str, list, Dict[str, list]]]:
        """加载MAA日志统计信息"""

        if mode == "总览":

            with json_path.open("r", encoding="utf-8") as f:
                info: Dict[str, Dict[str, Union[int, dict]]] = json.load(f)

            data = {}
            data["条目索引"] = [
                [k, "完成" if v == "Success!" else "异常"]
                for k, v in info["maa_result"].items()
            ]
            data["条目索引"].insert(0, ["数据总览", "运行"])
            data["统计数据"] = {"公招统计": list(info["recruit_statistics"].items())}

            for game_id, drops in info["drop_statistics"].items():
                data["统计数据"][f"掉落统计：{game_id}"] = list(drops.items())

            data["统计数据"]["报错汇总"] = [
                [k, v] for k, v in info["maa_result"].items() if v != "Success!"
            ]

        elif mode == "单项":

            with json_path.open("r", encoding="utf-8") as f:
                info: Dict[str, Union[str, Dict[str, Union[int, dict]]]] = json.load(f)

            data = {}

            data["统计数据"] = {"公招统计": list(info["recruit_statistics"].items())}

            for game_id, drops in info["drop_statistics"].items():
                data["统计数据"][f"掉落统计：{game_id}"] = list(drops.items())

            with json_path.with_suffix(".log").open("r", encoding="utf-8") as f:
                log = f.read()

            data["日志信息"] = log

        return data

    def search_history(self) -> dict:
        """搜索所有历史记录"""

        history_dict = {}

        for date_folder in (Config.app_path / "history").iterdir():
            if not date_folder.is_dir():
                continue  # 只处理日期文件夹

            try:

                date = datetime.strptime(date_folder.name, "%Y-%m-%d")

                history_dict[date.strftime("%Y年 %m月 %d日")] = list(
                    date_folder.glob("*.json")
                )

            except ValueError:
                logger.warning(f"非日期格式的目录: {date_folder}")

        return {
            k: v
            for k, v in sorted(
                history_dict.items(),
                key=lambda x: datetime.strptime(x[0], "%Y年 %m月 %d日"),
                reverse=True,
            )
        }

    def save_history(self, key: str, content: dict) -> None:
        """保存历史记录"""

        history = {}
        if self.history_path.exists():
            with self.history_path.open(mode="r", encoding="utf-8") as f:
                history = json.load(f)
        history[key] = content
        with self.history_path.open(mode="w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=4)

    def get_history(self, key: str) -> dict:
        """获取历史记录"""

        history = {}
        if self.history_path.exists():
            with self.history_path.open(mode="r", encoding="utf-8") as f:
                history = json.load(f)
        return history.get(
            key, {"Time": "0000-00-00 00:00", "History": "暂无历史运行记录"}
        )

    def clear_maa_config(self) -> None:
        """清空MAA配置"""

        self.maa_config.set(self.maa_config.MaaSet_Name, "")
        self.maa_config.set(self.maa_config.MaaSet_Path, ".")
        self.maa_config.set(self.maa_config.RunSet_TaskTransitionMethod, "ExitEmulator")
        self.maa_config.set(self.maa_config.RunSet_ProxyTimesLimit, 0)
        self.maa_config.set(self.maa_config.RunSet_AnnihilationTimeLimit, 40)
        self.maa_config.set(self.maa_config.RunSet_RoutineTimeLimit, 10)
        self.maa_config.set(self.maa_config.RunSet_RunTimesLimit, 3)
        self.maa_config.set(self.maa_config.MaaSet_Name, "")
        self.maa_config.set(self.maa_config.MaaSet_Name, "")
        self.maa_config.set(self.maa_config.MaaSet_Name, "")

    def clear_queue_config(self) -> None:
        """清空队列配置"""

        self.queue_config.set(self.queue_config.queueSet_Name, "")
        self.queue_config.set(self.queue_config.queueSet_Enabled, False)
        self.queue_config.set(self.queue_config.queueSet_AfterAccomplish, "None")

        self.queue_config.set(self.queue_config.time_TimeEnabled_0, False)
        self.queue_config.set(self.queue_config.time_TimeSet_0, "00:00")
        self.queue_config.set(self.queue_config.time_TimeEnabled_1, False)
        self.queue_config.set(self.queue_config.time_TimeSet_1, "00:00")
        self.queue_config.set(self.queue_config.time_TimeEnabled_2, False)
        self.queue_config.set(self.queue_config.time_TimeSet_2, "00:00")
        self.queue_config.set(self.queue_config.time_TimeEnabled_3, False)
        self.queue_config.set(self.queue_config.time_TimeSet_3, "00:00")
        self.queue_config.set(self.queue_config.time_TimeEnabled_4, False)
        self.queue_config.set(self.queue_config.time_TimeSet_4, "00:00")
        self.queue_config.set(self.queue_config.time_TimeEnabled_5, False)
        self.queue_config.set(self.queue_config.time_TimeSet_5, "00:00")
        self.queue_config.set(self.queue_config.time_TimeEnabled_6, False)
        self.queue_config.set(self.queue_config.time_TimeSet_6, "00:00")
        self.queue_config.set(self.queue_config.time_TimeEnabled_7, False)
        self.queue_config.set(self.queue_config.time_TimeSet_7, "00:00")
        self.queue_config.set(self.queue_config.time_TimeEnabled_8, False)
        self.queue_config.set(self.queue_config.time_TimeSet_8, "00:00")
        self.queue_config.set(self.queue_config.time_TimeEnabled_9, False)
        self.queue_config.set(self.queue_config.time_TimeSet_9, "00:00")

        self.queue_config.set(self.queue_config.queue_Member_1, "禁用")
        self.queue_config.set(self.queue_config.queue_Member_2, "禁用")
        self.queue_config.set(self.queue_config.queue_Member_3, "禁用")
        self.queue_config.set(self.queue_config.queue_Member_4, "禁用")
        self.queue_config.set(self.queue_config.queue_Member_5, "禁用")
        self.queue_config.set(self.queue_config.queue_Member_6, "禁用")
        self.queue_config.set(self.queue_config.queue_Member_7, "禁用")
        self.queue_config.set(self.queue_config.queue_Member_8, "禁用")
        self.queue_config.set(self.queue_config.queue_Member_9, "禁用")
        self.queue_config.set(self.queue_config.queue_Member_10, "禁用")


class GlobalConfig(QConfig):
    """全局配置"""

    function_HomeImageMode = OptionsConfigItem(
        "Function",
        "HomeImageMode",
        "默认",
        OptionsValidator(["默认", "自定义", "主题图像"]),
    )
    function_HistoryRetentionTime = OptionsConfigItem(
        "Function", "HistoryRetentionTime", 0, OptionsValidator([7, 15, 30, 60, 0])
    )
    function_IfAllowSleep = ConfigItem(
        "Function", "IfAllowSleep", False, BoolValidator()
    )
    function_IfSilence = ConfigItem("Function", "IfSilence", False, BoolValidator())
    function_BossKey = ConfigItem("Function", "BossKey", "")
    function_IfAgreeBilibili = ConfigItem(
        "Function", "IfAgreeBilibili", False, BoolValidator()
    )

    start_IfSelfStart = ConfigItem("Start", "IfSelfStart", False, BoolValidator())
    start_IfRunDirectly = ConfigItem("Start", "IfRunDirectly", False, BoolValidator())
    start_IfMinimizeDirectly = ConfigItem(
        "Start", "IfMinimizeDirectly", False, BoolValidator()
    )

    ui_IfShowTray = ConfigItem("UI", "IfShowTray", False, BoolValidator())
    ui_IfToTray = ConfigItem("UI", "IfToTray", False, BoolValidator())
    ui_size = ConfigItem("UI", "size", "1200x700")
    ui_location = ConfigItem("UI", "location", "100x100")
    ui_maximized = ConfigItem("UI", "maximized", False, BoolValidator())

    notify_IfPushPlyer = ConfigItem("Notify", "IfPushPlyer", False, BoolValidator())
    notify_IfSendMail = ConfigItem("Notify", "IfSendMail", False, BoolValidator())
    notify_IfSendErrorOnly = ConfigItem(
        "Notify", "IfSendErrorOnly", False, BoolValidator()
    )
    notify_SMTPServerAddress = ConfigItem("Notify", "SMTPServerAddress", "")
    notify_AuthorizationCode = ConfigItem("Notify", "AuthorizationCode", "")
    notify_FromAddress = ConfigItem("Notify", "FromAddress", "")
    notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
    notify_IfServerChan = ConfigItem("Notify", "IfServerChan", False, BoolValidator())
    notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
    notify_ServerChanChannel = ConfigItem("Notify", "ServerChanChannel", "")
    notify_ServerChanTag = ConfigItem("Notify", "ServerChanTag", "")
    notify_IfCompanyWebHookBot = ConfigItem(
        "Notify", "IfCompanyWebHookBot", False, BoolValidator()
    )
    notify_CompanyWebHookBotUrl = ConfigItem("Notify", "CompanyWebHookBotUrl", "")
    notify_IfPushDeer = ConfigItem("Notify", "IfPushDeer", False, BoolValidator())
    notify_IfPushDeerKey = ConfigItem("Notify", "PushDeerKey", "")

    update_IfAutoUpdate = ConfigItem("Update", "IfAutoUpdate", False, BoolValidator())
    update_UpdateType = OptionsConfigItem(
        "Update", "UpdateType", "main", OptionsValidator(["main", "dev"])
    )


class QueueConfig(QConfig):
    """队列配置"""

    queueSet_Name = ConfigItem("QueueSet", "Name", "")
    queueSet_Enabled = ConfigItem("QueueSet", "Enabled", False, BoolValidator())
    queueSet_AfterAccomplish = OptionsConfigItem(
        "QueueSet",
        "AfterAccomplish",
        "None",
        OptionsValidator(["None", "KillSelf", "Sleep", "Hibernate", "Shutdown"]),
    )

    time_TimeEnabled_0 = ConfigItem("Time", "TimeEnabled_0", False, BoolValidator())
    time_TimeSet_0 = ConfigItem("Time", "TimeSet_0", "00:00")

    time_TimeEnabled_1 = ConfigItem("Time", "TimeEnabled_1", False, BoolValidator())
    time_TimeSet_1 = ConfigItem("Time", "TimeSet_1", "00:00")

    time_TimeEnabled_2 = ConfigItem("Time", "TimeEnabled_2", False, BoolValidator())
    time_TimeSet_2 = ConfigItem("Time", "TimeSet_2", "00:00")

    time_TimeEnabled_3 = ConfigItem("Time", "TimeEnabled_3", False, BoolValidator())
    time_TimeSet_3 = ConfigItem("Time", "TimeSet_3", "00:00")

    time_TimeEnabled_4 = ConfigItem("Time", "TimeEnabled_4", False, BoolValidator())
    time_TimeSet_4 = ConfigItem("Time", "TimeSet_4", "00:00")

    time_TimeEnabled_5 = ConfigItem("Time", "TimeEnabled_5", False, BoolValidator())
    time_TimeSet_5 = ConfigItem("Time", "TimeSet_5", "00:00")

    time_TimeEnabled_6 = ConfigItem("Time", "TimeEnabled_6", False, BoolValidator())
    time_TimeSet_6 = ConfigItem("Time", "TimeSet_6", "00:00")

    time_TimeEnabled_7 = ConfigItem("Time", "TimeEnabled_7", False, BoolValidator())
    time_TimeSet_7 = ConfigItem("Time", "TimeSet_7", "00:00")

    time_TimeEnabled_8 = ConfigItem("Time", "TimeEnabled_8", False, BoolValidator())
    time_TimeSet_8 = ConfigItem("Time", "TimeSet_8", "00:00")

    time_TimeEnabled_9 = ConfigItem("Time", "TimeEnabled_9", False, BoolValidator())
    time_TimeSet_9 = ConfigItem("Time", "TimeSet_9", "00:00")

    queue_Member_1 = OptionsConfigItem("Queue", "Member_1", "禁用")
    queue_Member_2 = OptionsConfigItem("Queue", "Member_2", "禁用")
    queue_Member_3 = OptionsConfigItem("Queue", "Member_3", "禁用")
    queue_Member_4 = OptionsConfigItem("Queue", "Member_4", "禁用")
    queue_Member_5 = OptionsConfigItem("Queue", "Member_5", "禁用")
    queue_Member_6 = OptionsConfigItem("Queue", "Member_6", "禁用")
    queue_Member_7 = OptionsConfigItem("Queue", "Member_7", "禁用")
    queue_Member_8 = OptionsConfigItem("Queue", "Member_8", "禁用")
    queue_Member_9 = OptionsConfigItem("Queue", "Member_9", "禁用")
    queue_Member_10 = OptionsConfigItem("Queue", "Member_10", "禁用")


class MaaConfig(QConfig):
    """MAA配置"""

    MaaSet_Name = ConfigItem("MaaSet", "Name", "")
    MaaSet_Path = ConfigItem("MaaSet", "Path", ".", FolderValidator())

    RunSet_TaskTransitionMethod = OptionsConfigItem(
        "RunSet",
        "TaskTransitionMethod",
        "ExitEmulator",
        OptionsValidator(["NoAction", "ExitGame", "ExitEmulator"]),
    )
    RunSet_ProxyTimesLimit = RangeConfigItem(
        "RunSet", "ProxyTimesLimit", 0, RangeValidator(0, 1024)
    )
    RunSet_AnnihilationTimeLimit = RangeConfigItem(
        "RunSet", "AnnihilationTimeLimit", 40, RangeValidator(1, 1024)
    )
    RunSet_RoutineTimeLimit = RangeConfigItem(
        "RunSet", "RoutineTimeLimit", 10, RangeValidator(1, 1024)
    )
    RunSet_RunTimesLimit = RangeConfigItem(
        "RunSet", "RunTimesLimit", 3, RangeValidator(1, 1024)
    )


Config = AppConfig()
