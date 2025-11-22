#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
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

import os
import re
import httpx
import shutil
import asyncio
import uvicorn
import sqlite3
import calendar
import truststore
from pathlib import Path
from fastapi import WebSocket
from collections import defaultdict
from jinja2 import Environment, FileSystemLoader
from datetime import datetime, timedelta, date
from typing import Literal, Optional, Union, Dict, Any, List
import uuid
import json

from app.models.config import (
    GeneralConfig,
    MaaConfig,
    MaaPlanConfig,
    QueueConfig,
    QueueItem,
    MaaUserConfig,
    GeneralUserConfig,
    GlobalConfig,
    CLASS_BOOK,
    Webhook,
    TimeSet,
    EmulatorConfig,
)
from app.models.schema import WebSocketMessage
from app.utils.constants import (
    UTC4,
    UTC8,
    RESOURCE_STAGE_INFO,
    RESOURCE_STAGE_DROP_INFO,
    MATERIALS_MAP,
    TYPE_BOOK,
    RESOURCE_STAGE_DATE_TEXT,
)
from app.utils import get_logger
from app.utils.emulator import find_emulator_root_path

logger = get_logger("配置管理")

if (Path.cwd() / "environment/git/bin/git.exe").exists():
    os.environ["GIT_PYTHON_GIT_EXECUTABLE"] = str(
        Path.cwd() / "environment/git/bin/git.exe"
    )

try:
    from git import Repo
except ImportError:
    Repo = None


class AppConfig(GlobalConfig):
    VERSION = [5, 0, 0, 4]

    def __init__(self) -> None:
        super().__init__()

        logger.info("")
        logger.info("===================================")
        logger.info("AUTO-MAS 后端应用程序")
        logger.info(f"版本号:  {self.version()}")
        logger.info(f"工作目录:  {Path.cwd()}")
        logger.info("===================================")

        self.log_path = Path.cwd() / "debug/app.log"
        self.database_path = Path.cwd() / "data/data.db"
        self.config_path = Path.cwd() / "config"
        self.history_path = Path.cwd() / "history"
        # 检查目录
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.mkdir(parents=True, exist_ok=True)
        self.history_path.mkdir(parents=True, exist_ok=True)

        # 初始化Git仓库（如果可用）
        try:
            if Repo is not None:
                self.repo = Repo(Path.cwd())
            else:
                self.repo = None
        except Exception as e:
            logger.warning(f"Git仓库初始化失败: {e}")
            self.repo = None

        self.notify_env = Environment(
            loader=FileSystemLoader(str(Path.cwd() / "res/html"))
        )

        self.server: Optional[uvicorn.Server] = None
        self.websocket: Optional[WebSocket] = None
        self.power_sign: Literal[
            "NoAction", "Shutdown", "ShutdownForce", "Hibernate", "Sleep", "KillSelf"
        ] = "NoAction"
        self.temp_task: List[asyncio.Task] = []

        truststore.inject_into_ssl()

    def version(self) -> str:
        """获取版本号字符串"""

        if self.VERSION[3] == 0:
            return f"v{'.'.join(str(_) for _ in self.VERSION[0:3])}"
        else:
            return (
                f"v{'.'.join(str(_) for _ in self.VERSION[0:3])}-beta.{self.VERSION[3]}"
            )

    async def init_config(self) -> None:
        """初始化配置管理"""

        await self.check_data()

        await self.connect(self.config_path / "Config.json")
        await self.EmulatorConfig.connect(self.config_path / "EmulatorConfig.json")
        await self.PlanConfig.connect(self.config_path / "PlanConfig.json")
        await self.ScriptConfig.connect(self.config_path / "ScriptConfig.json")
        await self.QueueConfig.connect(self.config_path / "QueueConfig.json")

        # from .task_manager import TaskManager

        # self.task_dict = TaskManager.task_dict

        logger.info("程序初始化完成")

    async def check_data(self) -> None:
        """检查用户数据文件并处理数据文件版本更新"""

        # 生成主数据库
        if not self.database_path.exists():
            db = sqlite3.connect(self.database_path)
            cur = db.cursor()
            cur.execute("CREATE TABLE version(v text)")
            cur.execute("INSERT INTO version VALUES(?)", ("v1.9",))
            db.commit()
            cur.close()
            db.close()

        # 数据文件版本更新
        db = sqlite3.connect(self.database_path)
        cur = db.cursor()
        cur.execute("SELECT * FROM version WHERE True")
        version = cur.fetchall()

        if version[0][0] != "v1.9":
            logger.info(
                "数据文件版本更新开始",
            )
            if_streaming = False
            # v1.7-->v1.8
            if version[0][0] == "v1.7" or if_streaming:
                logger.info(
                    "数据文件版本更新: v1.7-->v1.8",
                )
                if_streaming = True

                if (Path.cwd() / "config/QueueConfig").exists():
                    for QueueConfig in (Path.cwd() / "config/QueueConfig").glob(
                        "*.json"
                    ):
                        with QueueConfig.open(encoding="utf-8") as f:
                            queue_config = json.load(f)

                        queue_config["QueueSet"]["TimeEnabled"] = queue_config[
                            "QueueSet"
                        ]["Enabled"]

                        for i in range(10):
                            queue_config["Queue"][f"Script_{i}"] = queue_config[
                                "Queue"
                            ][f"Member_{i + 1}"]
                            queue_config["Time"][f"Enabled_{i}"] = queue_config["Time"][
                                f"TimeEnabled_{i}"
                            ]
                            queue_config["Time"][f"Set_{i}"] = queue_config["Time"][
                                f"TimeSet_{i}"
                            ]

                        with QueueConfig.open("w", encoding="utf-8") as f:
                            json.dump(queue_config, f, ensure_ascii=False, indent=4)

                cur.execute("DELETE FROM version WHERE v = ?", ("v1.7",))
                cur.execute("INSERT INTO version VALUES(?)", ("v1.8",))
                db.commit()
            # v1.8-->v1.9
            if version[0][0] == "v1.8" or if_streaming:
                logger.info(
                    "数据文件版本更新: v1.8-->v1.9",
                )
                if_streaming = True

                await self.ScriptConfig.connect(self.config_path / "ScriptConfig.json")
                await self.PlanConfig.connect(self.config_path / "PlanConfig.json")
                await self.QueueConfig.connect(self.config_path / "QueueConfig.json")

                if (Path.cwd() / "config/config.json").exists():
                    (Path.cwd() / "config/config.json").rename(
                        Path.cwd() / "config/Config.json"
                    )
                await self.connect(self.config_path / "Config.json")

                plan_dict = {"固定": "Fixed"}

                if (Path.cwd() / "config/MaaPlanConfig").exists():
                    for MaaPlanConfig in (
                        Path.cwd() / "config/MaaPlanConfig"
                    ).iterdir():
                        if (
                            MaaPlanConfig.is_dir()
                            and (MaaPlanConfig / "config.json").exists()
                        ):
                            maa_plan_config = json.loads(
                                (MaaPlanConfig / "config.json").read_text(
                                    encoding="utf-8"
                                )
                            )
                            uid, pc = await self.add_plan("MaaPlan")
                            plan_dict[MaaPlanConfig.name] = str(uid)

                            await pc.load(maa_plan_config)

                    await self.PlanConfig.save()

                script_dict: Dict[str, Optional[str]] = {"禁用": None}

                if (Path.cwd() / "config/MaaConfig").exists():
                    for MaaConfig in (Path.cwd() / "config/MaaConfig").iterdir():
                        if MaaConfig.is_dir():
                            maa_config = json.loads(
                                (MaaConfig / "config.json").read_text(encoding="utf-8")
                            )
                            maa_config["Info"] = maa_config["MaaSet"]
                            maa_config["Run"] = maa_config["RunSet"]

                            uid, sc = await self.add_script("MAA")
                            script_dict[MaaConfig.name] = str(uid)
                            await sc.load(maa_config)

                            if (MaaConfig / "Default/gui.json").exists():
                                (Path.cwd() / f"data/{uid}/Default/ConfigFile").mkdir(
                                    parents=True, exist_ok=True
                                )
                                shutil.copy(
                                    MaaConfig / "Default/gui.json",
                                    Path.cwd()
                                    / f"data/{uid}/Default/ConfigFile/gui.json",
                                )

                            for user in (MaaConfig / "UserData").iterdir():
                                if user.is_dir() and (user / "config.json").exists():
                                    user_config = json.loads(
                                        (user / "config.json").read_text(
                                            encoding="utf-8"
                                        )
                                    )

                                    user_config["Info"]["StageMode"] = plan_dict.get(
                                        user_config["Info"]["StageMode"], "Fixed"
                                    )
                                    user_config["Info"]["Password"] = ""

                                    user_uid, uc = await self.add_user(str(uid))
                                    await uc.load(user_config)

                                    if (user / "Routine/gui.json").exists():
                                        (
                                            Path.cwd()
                                            / f"data/{uid}/{user_uid}/ConfigFile"
                                        ).mkdir(parents=True, exist_ok=True)
                                        shutil.copy(
                                            user / "Routine/gui.json",
                                            Path.cwd()
                                            / f"data/{uid}/{user_uid}/ConfigFile/gui.json",
                                        )
                                    if (
                                        user / "Infrastructure/infrastructure.json"
                                    ).exists():
                                        (
                                            Path.cwd()
                                            / f"data/{uid}/{user_uid}/Infrastructure"
                                        ).mkdir(parents=True, exist_ok=True)
                                        shutil.copy(
                                            user / "Infrastructure/infrastructure.json",
                                            Path.cwd()
                                            / f"data/{uid}/{user_uid}/Infrastructure/infrastructure.json",
                                        )

                if (Path.cwd() / "config/GeneralConfig").exists():
                    for GeneralConfig in (
                        Path.cwd() / "config/GeneralConfig"
                    ).iterdir():
                        if GeneralConfig.is_dir():
                            general_config = json.loads(
                                (GeneralConfig / "config.json").read_text(
                                    encoding="utf-8"
                                )
                            )
                            general_config["Info"] = {
                                "Name": general_config["Script"]["Name"],
                                "RootPath": general_config["Script"]["RootPath"],
                            }

                            general_config["Script"]["ConfigPathMode"] = (
                                "File"
                                if "所有文件"
                                in general_config["Script"]["ConfigPathMode"]
                                else "Folder"
                            )

                            uid, sc = await self.add_script("General")
                            script_dict[GeneralConfig.name] = str(uid)
                            await sc.load(general_config)

                            for user in (GeneralConfig / "SubData").iterdir():
                                if user.is_dir() and (user / "config.json").exists():
                                    user_config = json.loads(
                                        (user / "config.json").read_text(
                                            encoding="utf-8"
                                        )
                                    )

                                    user_uid, uc = await self.add_user(str(uid))
                                    await uc.load(user_config)

                                    if (user / "ConfigFiles").exists():
                                        (Path.cwd() / f"data/{uid}/{user_uid}").mkdir(
                                            parents=True, exist_ok=True
                                        )
                                        shutil.move(
                                            user / "ConfigFiles",
                                            Path.cwd()
                                            / f"data/{uid}/{user_uid}/ConfigFile",
                                        )

                await self.ScriptConfig.save()

                if (Path.cwd() / "config/QueueConfig").exists():
                    for QueueConfig in (Path.cwd() / "config/QueueConfig").glob(
                        "*.json"
                    ):
                        queue_config = json.loads(
                            QueueConfig.read_text(encoding="utf-8")
                        )

                        uid, qc = await self.add_queue()

                        queue_config["Info"] = queue_config["QueueSet"]
                        await qc.load(queue_config)

                        for i in range(10):
                            item_uid, item = await self.add_queue_item(str(uid))
                            time_uid, time = await self.add_time_set(str(uid))

                            await time.load(
                                {
                                    "Info": {
                                        "Enabled": queue_config["Time"][f"Enabled_{i}"],
                                        "Time": queue_config["Time"][f"Set_{i}"],
                                    }
                                }
                            )
                            await item.load(
                                {
                                    "Info": {
                                        "ScriptId": script_dict.get(
                                            queue_config["Queue"][f"Script_{i}"], "-"
                                        )
                                    }
                                }
                            )
                    await self.QueueConfig.save()

                if (Path.cwd() / "config/QueueConfig").exists():
                    shutil.rmtree(Path.cwd() / "config/QueueConfig")
                if (Path.cwd() / "config/MaaPlanConfig").exists():
                    shutil.rmtree(Path.cwd() / "config/MaaPlanConfig")
                if (Path.cwd() / "config/MaaConfig").exists():
                    shutil.rmtree(Path.cwd() / "config/MaaConfig")
                if (Path.cwd() / "config/GeneralConfig").exists():
                    shutil.rmtree(Path.cwd() / "config/GeneralConfig")
                if (Path.cwd() / "data/gameid.txt").exists():
                    (Path.cwd() / "data/gameid.txt").unlink()
                if (Path.cwd() / "data/key").exists():
                    shutil.rmtree(Path.cwd() / "data/key")

                cur.execute("DELETE FROM version WHERE v = ?", ("v1.8",))
                cur.execute("INSERT INTO version VALUES(?)", ("v1.9",))
                db.commit()

            cur.close()
            db.close()
            logger.success("数据文件版本更新完成")

    async def send_json(self, data: dict) -> None:
        """通过WebSocket发送JSON数据"""
        if Config.websocket is None:
            logger.warning("WebSocket 未连接")
        else:
            await Config.websocket.send_json(data)

    async def send_websocket_message(
        self,
        id: str,
        type: Literal["Update", "Message", "Info", "Signal"],
        data: Dict[str, Any],
    ) -> None:
        """通过WebSocket发送消息"""
        if Config.websocket is None:
            logger.warning("WebSocket 未连接")
        else:
            await Config.websocket.send_json(
                WebSocketMessage(id=id, type=type, data=data).model_dump()
            )

    async def get_git_version(self) -> tuple[bool, str, str]:
        """获取Git版本信息，如果Git不可用则返回默认值"""

        loop = asyncio.get_event_loop()

        def _get_git_info():

            if self.repo is None:
                logger.warning("Git仓库不可用，返回默认版本信息")
                return False, "unknown", "unknown"

            # 获取当前 commit
            current_commit = self.repo.head.commit
            # 获取 commit 哈希
            commit_hash = current_commit.hexsha
            # 获取 commit 时间
            commit_time = datetime.fromtimestamp(current_commit.committed_date)

            # 检查是否为最新 commit
            try:
                # 获取远程分支的最新 commit
                origin = self.repo.remotes.origin
                origin.fetch()  # 拉取最新信息
                remote_commit = self.repo.commit(
                    f"origin/{self.repo.active_branch.name}"
                )
                is_latest = bool(current_commit.hexsha == remote_commit.hexsha)
            except Exception as e:
                logger.warning(f"无法获取远程分支信息: {e}")
                is_latest = False

            return is_latest, commit_hash, commit_time.strftime("%Y-%m-%d %H:%M:%S")

        # 在线程池中执行 Git 操作
        is_latest, commit_hash, commit_time = await loop.run_in_executor(
            None, _get_git_info
        )
        return is_latest, commit_hash, commit_time

    async def add_script(
        self, script: Literal["MAA", "General"]
    ) -> tuple[uuid.UUID, Union[MaaConfig, GeneralConfig]]:
        """添加脚本配置"""

        logger.info(f"添加脚本配置: {script}")

        return await self.ScriptConfig.add(CLASS_BOOK[script])

    async def get_script(self, script_id: Optional[str]) -> tuple[list, dict]:
        """获取脚本配置"""

        logger.info(f"获取脚本配置: {script_id}")

        if script_id is None:
            # 获取所有脚本配置
            data = await self.ScriptConfig.toDict()
        else:
            # 获取指定脚本配置
            data = await self.ScriptConfig.get(uuid.UUID(script_id))

        index = data.pop("instances", [])
        return list(index), data

    async def update_script(
        self, script_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新脚本配置"""

        logger.info(f"更新脚本配置: {script_id}")

        uid = uuid.UUID(script_id)

        if self.ScriptConfig[uid].is_locked:
            raise RuntimeError(f"脚本 {script_id} 正在运行, 无法更新配置项")

        for group, items in data.items():
            for name, value in items.items():
                logger.debug(f"更新脚本配置: {script_id} - {group}.{name} = {value}")
                await self.ScriptConfig[uid].set(group, name, value)

        await self.ScriptConfig.save()

    async def del_script(self, script_id: str) -> None:
        """删除脚本配置"""

        logger.info(f"删除脚本配置: {script_id}")

        uid = uuid.UUID(script_id)

        if self.ScriptConfig[uid].is_locked:
            raise RuntimeError(f"脚本 {script_id} 正在运行, 无法删除")

        # 删除脚本相关的队列项
        for queue in self.QueueConfig.values():
            for key, value in queue.QueueItem.items():
                if value.get("Info", "ScriptId") == str(uid):
                    await queue.QueueItem.remove(key)

        await self.ScriptConfig.remove(uid)
        if (Path.cwd() / f"data/{uid}").exists():
            shutil.rmtree(Path.cwd() / f"data/{uid}")

    async def reorder_script(self, index_list: list[str]) -> None:
        """重新排序脚本"""

        logger.info(f"重新排序脚本: {index_list}")

        await self.ScriptConfig.setOrder([uuid.UUID(_) for _ in index_list])

    async def import_script_from_file(self, script_id: str, jsonFile: str) -> None:
        """从文件加载脚本配置"""

        logger.info(f"从文件加载脚本配置: {script_id} - {jsonFile}")
        uid = uuid.UUID(script_id)
        file_path = Path(jsonFile)

        if uid not in self.ScriptConfig:
            logger.error(f"{script_id} 不存在")
            raise KeyError(f"脚本 {script_id} 不存在")
        if not isinstance(self.ScriptConfig[uid], GeneralConfig):
            logger.error(f"{script_id} 不是通用脚本配置")
            raise TypeError(f"脚本 {script_id} 不是通用脚本配置")
        if not Path(file_path).exists():
            logger.error(f"文件不存在: {file_path}")
            raise FileNotFoundError(f"文件不存在: {file_path}")

        data = json.loads(file_path.read_text(encoding="utf-8"))
        await self.ScriptConfig[uid].load(data)
        await self.ScriptConfig.save()

        logger.success(f"{script_id} 配置加载成功")

    async def export_script_to_file(self, script_id: str, jsonFile: str):
        """导出脚本配置到文件"""

        logger.info(f"导出配置到文件: {script_id} - {jsonFile}")

        uid = uuid.UUID(script_id)
        file_path = Path(jsonFile)

        if uid not in self.ScriptConfig:
            logger.error(f"{script_id} 不存在")
            raise KeyError(f"脚本 {script_id} 不存在")
        if not isinstance(self.ScriptConfig[uid], GeneralConfig):
            logger.error(f"{script_id} 不是通用脚本配置")
            raise TypeError(f"脚本 {script_id} 不是通用脚本配置")

        temp = await self.ScriptConfig[uid].toDict(
            ignore_multi_config=True, if_decrypt=False
        )

        # 移除配置中可能存在的隐私信息
        temp["Info"]["Name"] = Path(file_path).stem
        for path in ["ScriptPath", "ConfigPath", "LogPath"]:
            if Path(temp["Script"][path]).is_relative_to(
                Path(temp["Info"]["RootPath"])
            ):
                temp["Script"][path] = str(
                    Path(r"C:/脚本根目录")
                    / Path(temp["Script"][path]).relative_to(
                        Path(temp["Info"]["RootPath"])
                    )
                )
        temp["Info"]["RootPath"] = str(Path(r"C:/脚本根目录"))

        file_path.write_text(
            json.dumps(temp, ensure_ascii=False, indent=4), encoding="utf-8"
        )

        logger.success(f"{script_id} 配置导出成功")

    async def import_script_from_web(self, script_id: str, url: str):
        """从「AUTO-MAS 配置分享中心」导入配置"""

        logger.info(f"从网络加载脚本配置: {script_id} - {url}")
        uid = uuid.UUID(script_id)

        if uid not in self.ScriptConfig:
            logger.error(f"{script_id} 不存在")
            raise KeyError(f"脚本 {script_id} 不存在")
        if not isinstance(self.ScriptConfig[uid], GeneralConfig):
            logger.error(f"{script_id} 不是通用脚本配置")
            raise TypeError(f"脚本 {script_id} 不是通用脚本配置")

        # 使用 httpx 异步请求
        async with httpx.AsyncClient(proxy=Config.get_proxy()) as client:
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                else:
                    logger.warning(
                        f"无法从 AUTO-MAS 服务器获取配置内容: {response.text}"
                    )
                    raise ConnectionError(
                        f"无法从 AUTO-MAS 服务器获取配置内容: {response.status_code}"
                    )
            except httpx.RequestError as e:
                logger.warning(f"无法从 AUTO-MAS 服务器获取配置内容: {e}")
                raise ConnectionError(f"无法从 AUTO-MAS 服务器获取配置内容: {e}")

        await self.ScriptConfig[uid].load(data)
        await self.ScriptConfig.save()

        logger.success(f"{script_id} 配置加载成功")

    async def upload_script_to_web(
        self, script_id: str, config_name: str, author: str, description: str
    ):
        """上传配置到「AUTO-MAS 配置分享中心」"""

        logger.info(f"上传配置到网络: {script_id} - {config_name} - {author}")

        uid = uuid.UUID(script_id)

        if uid not in self.ScriptConfig:
            logger.error(f"{script_id} 不存在")
            raise KeyError(f"脚本 {script_id} 不存在")
        if not isinstance(self.ScriptConfig[uid], GeneralConfig):
            logger.error(f"{script_id} 不是通用脚本配置")
            raise TypeError(f"脚本 {script_id} 不是通用脚本配置")

        temp = await self.ScriptConfig[uid].toDict(
            ignore_multi_config=True, if_decrypt=False
        )

        # 移除配置中可能存在的隐私信息
        temp["Info"]["Name"] = config_name
        for path in ["ScriptPath", "ConfigPath", "LogPath"]:
            if Path(temp["Script"][path]).is_relative_to(
                Path(temp["Info"]["RootPath"])
            ):
                temp["Script"][path] = str(
                    Path(r"C:/脚本根目录")
                    / Path(temp["Script"][path]).relative_to(
                        Path(temp["Info"]["RootPath"])
                    )
                )
        temp["Info"]["RootPath"] = str(Path(r"C:/脚本根目录"))

        files = {
            "file": (
                f"{config_name}&&{author}&&{description}&&{int(datetime.now(tz=UTC8).timestamp() * 1000)}.json",
                json.dumps(temp, ensure_ascii=False),
                "application/json",
            )
        }
        data = {"username": author, "description": description}

        async with httpx.AsyncClient(proxy=Config.get_proxy()) as client:
            try:
                response = await client.post(
                    "https://share.auto-mas.top/api/upload/share",
                    files=files,
                    data=data,
                )

                if response.status_code == 200:
                    logger.success("配置上传成功")
                else:
                    logger.error(f"无法上传配置到 AUTO-MAS 服务器: {response.text}")
                    raise ConnectionError(
                        f"无法上传配置到 AUTO-MAS 服务器: {response.status_code} - {response.text}"
                    )
            except httpx.RequestError as e:
                logger.error(f"无法上传配置到 AUTO-MAS 服务器: {e}")
                raise ConnectionError(f"无法上传配置到 AUTO-MAS 服务器: {e}")

    async def get_user(
        self, script_id: str, user_id: Optional[str]
    ) -> tuple[list, dict]:
        """获取用户配置"""

        logger.info(f"获取用户配置: {script_id} - {user_id}")

        uid = uuid.UUID(script_id)

        if user_id is None:
            # 获取全部用户配置
            data = await self.ScriptConfig[uid].UserData.toDict()
        else:
            # 获取指定用户配置
            data = await self.ScriptConfig[uid].UserData.get(uuid.UUID(user_id))

        index = data.pop("instances", [])
        return list(index), data

    async def add_user(
        self, script_id: str
    ) -> tuple[uuid.UUID, Union[MaaUserConfig, GeneralUserConfig]]:
        """添加用户配置"""

        logger.info(f"{script_id} 添加用户配置")

        script_config = self.ScriptConfig[uuid.UUID(script_id)]

        # 根据脚本类型选择添加对应用户配置
        if isinstance(script_config, MaaConfig):
            uid, config = await script_config.UserData.add(MaaUserConfig)
        elif isinstance(script_config, GeneralConfig):
            uid, config = await script_config.UserData.add(GeneralUserConfig)
        else:
            raise TypeError(f"不支持的脚本配置类型: {type(script_config)}")

        await self.ScriptConfig.save()
        return uid, config

    async def update_user(
        self, script_id: str, user_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新用户配置"""

        logger.info(f"{script_id} 更新用户配置: {user_id}")

        script_uid = uuid.UUID(script_id)
        user_uid = uuid.UUID(user_id)

        for group, items in data.items():
            for name, value in items.items():
                logger.debug(f"更新脚本配置: {script_id} - {group}.{name} = {value}")
                await (
                    self.ScriptConfig[script_uid]
                    .UserData[user_uid]
                    .set(group, name, value)
                )

        await self.ScriptConfig.save()

    async def del_user(self, script_id: str, user_id: str) -> None:
        """删除用户配置"""

        logger.info(f"{script_id} 删除用户配置: {user_id}")

        script_uid = uuid.UUID(script_id)
        user_uid = uuid.UUID(user_id)

        await self.ScriptConfig[script_uid].UserData.remove(user_uid)
        await self.ScriptConfig.save()
        if (Path.cwd() / f"data/{script_id}/{user_id}").exists():
            shutil.rmtree(Path.cwd() / f"data/{script_id}/{user_id}")

    async def reorder_user(self, script_id: str, index_list: list[str]) -> None:
        """重新排序用户"""

        logger.info(f"{script_id} 重新排序用户: {index_list}")

        script_uid = uuid.UUID(script_id)

        await self.ScriptConfig[script_uid].UserData.setOrder(
            list(map(uuid.UUID, index_list))
        )
        await self.ScriptConfig.save()

    async def set_infrastructure(
        self, script_id: str, user_id: str, jsonFile: str
    ) -> None:
        logger.info(f"{script_id} - {user_id} 设置基建配置: {jsonFile}")

        script_uid = uuid.UUID(script_id)
        user_uid = uuid.UUID(user_id)
        json_path = Path(jsonFile)

        if not json_path.exists():
            raise FileNotFoundError(f"文件未找到: {json_path}")

        if not isinstance(self.ScriptConfig[script_uid], MaaConfig):
            raise TypeError(f"脚本 {script_id} 不是 MAA 脚本, 无法设置基建配置")

        infrast_data = json.loads(json_path.read_text(encoding="utf-8"))

        if len(infrast_data.get("plans", [])) == 0:
            raise ValueError("未找到有效的基建排班信息")

        await self.ScriptConfig[script_uid].UserData[user_uid].set(
            "Data", "CustomInfrast", json.dumps(infrast_data, ensure_ascii=False)
        )
        await self.ScriptConfig.save()

    async def get_user_combox_infrastructure(
        self, script_id: str, user_id: str
    ) -> list[dict]:
        logger.info(f"获取用户自定义基建排班下拉框信息: {script_id} - {user_id}")

        script_uid = uuid.UUID(script_id)
        user_uid = uuid.UUID(user_id)

        script_config = self.ScriptConfig[script_uid]

        # 根据脚本类型选择添加对应用户配置
        if not isinstance(script_config, MaaConfig):
            raise TypeError(f"不支持的脚本配置类型: {type(script_config)}")

        logger.info("开始获取用户自定义基建排班下拉框信息")

        data = []
        for i, plan in enumerate(
            json.loads(
                script_config.UserData[user_uid].get("Data", "CustomInfrast")
            ).get("plans", [])
        ):
            data.append({"label": plan.get("name", f"排班 {i+1}"), "value": str(i)})

        logger.success("用户自定义基建排班下拉框信息获取成功")

        return data

    async def add_plan(
        self, script: Literal["MaaPlan"]
    ) -> tuple[uuid.UUID, MaaPlanConfig]:
        """添加计划表"""

        logger.info(f"添加计划表: {script}")

        return await self.PlanConfig.add(CLASS_BOOK[script])

    async def get_plan(self, plan_id: Optional[str]) -> tuple[list, dict]:
        """获取计划表配置"""

        logger.info(f"获取计划表配置: {plan_id}")

        if plan_id is None:
            data = await self.PlanConfig.toDict()
        else:
            data = await self.PlanConfig.get(uuid.UUID(plan_id))

        index = data.pop("instances", [])
        return list(index), data

    async def update_plan(self, plan_id: str, data: Dict[str, Dict[str, Any]]) -> None:
        """更新计划表配置"""

        logger.info(f"更新计划表配置: {plan_id}")

        plan_uid = uuid.UUID(plan_id)

        for group, items in data.items():
            for name, value in items.items():
                logger.debug(f"更新计划表配置: {plan_id} - {group}.{name} = {value}")
                await self.PlanConfig[plan_uid].set(group, name, value)

        await self.PlanConfig.save()

    async def del_plan(self, plan_id: str) -> None:
        """删除计划表配置"""

        logger.info(f"删除计划表配置: {plan_id}")

        plan_uid = uuid.UUID(plan_id)

        user_list = []

        for script in self.ScriptConfig.values():
            if isinstance(script, MaaConfig):
                for user in script.UserData.values():
                    if user.get("Info", "StageMode") == str(plan_uid):
                        if user.is_locked:
                            raise RuntimeError(
                                f"用户 {user.get('Info','Name')} 正在使用此计划表且被锁定, 无法完成删除"
                            )
                        user_list.append(user)

        for user in user_list:
            await user.set("Info", "StageMode", "Fixed")

        await self.PlanConfig.remove(plan_uid)

    async def reorder_plan(self, index_list: list[str]) -> None:
        """重新排序计划表"""

        logger.info(f"重新排序计划表: {index_list}")

        await self.PlanConfig.setOrder(list(map(uuid.UUID, index_list)))

    async def get_emulator(self, emulator_id: Optional[str]) -> tuple[list, dict]:
        """获取emulator配置"""
        logger.info(f"获取全局emulator设置: {emulator_id}")

        if emulator_id is None:
            data = await self.EmulatorConfig.toDict()
        else:
            data = await self.EmulatorConfig.get(uuid.UUID(emulator_id))

        index = data.pop("instances", [])
        return list(index), data

    async def add_emulator(self) -> tuple[uuid.UUID, EmulatorConfig]:
        """添加emulator配置"""
        logger.info("添加全局emulator配置")

        uid, config = await self.EmulatorConfig.add(EmulatorConfig)
        await self.EmulatorConfig.save()
        return uid, config

    async def update_emulator(
        self, emulator_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新 emulator 配置"""

        emulator_uid = uuid.UUID(emulator_id)

        logger.info(f"更新 emulator 配置: {emulator_id}")

        # 如果路径被修改,尝试自动搜索模拟器根目录
        if "Info" in data and "Path" in data["Info"]:
            input_path = data["Info"]["Path"]

            # 获取模拟器类型
            emulator_type = None
            if "Data" in data and "Type" in data["Data"]:
                # 如果本次更新中包含类型信息
                emulator_type = data["Data"]["Type"]
            else:
                # 否则从现有配置中获取
                emulator_type = await self.EmulatorConfig[emulator_uid].get(
                    "Data", "Type"
                )

            if input_path and emulator_type:
                logger.info(
                    f"检测到路径修改: {input_path}, 模拟器类型: {emulator_type}"
                )
                # 搜索并调整为正确的根目录
                found_path = await find_emulator_root_path(input_path, emulator_type)
                if found_path != input_path:
                    logger.info(f"路径已自动调整: {input_path} -> {found_path}")
                    data["Info"]["Path"] = found_path
                else:
                    logger.debug(f"路径未调整,保持原值: {input_path}")

        for group, items in data.items():
            for name, value in items.items():
                logger.debug(
                    f"更新全局 emulator:{emulator_id} - {group}.{name} = {value}"
                )
                await self.EmulatorConfig[emulator_uid].set(group, name, value)

        await self.EmulatorConfig.save()

    async def del_emulator(self, emulator_id: str) -> None:
        """删除 emulator 配置"""

        emulator_uid = uuid.UUID(emulator_id)

        logger.info(f"删除全局 emulator 配置: {emulator_id}")

        script_list = []

        for script in self.ScriptConfig.values():
            if isinstance(script, MaaConfig):
                if script.get("Emulator", "Id") == str(emulator_id):
                    if script.is_locked:
                        raise RuntimeError(
                            f"脚本 {script.get('Info','Name')} 正在使用此模拟器且被锁定, 无法完成删除"
                        )
                    script_list.append(script)
            if isinstance(script, GeneralConfig):
                if script.get("Game", "Type") == "Emulator" and script.get(
                    "Game", "EmulatorId"
                ) == str(emulator_id):
                    if script.is_locked:
                        raise RuntimeError(
                            f"脚本 {script.get('Info','Name')} 正在使用此模拟器且被锁定, 无法完成删除"
                        )
                    script_list.append(script)

        for script in script_list:
            if isinstance(script, MaaConfig):
                await script.set("Emulator", "Id", "-")
            elif isinstance(script, GeneralConfig):
                await script.set("Game", "EmulatorId", "-")

        await self.EmulatorConfig.remove(emulator_uid)
        await self.EmulatorConfig.save()

    async def reorder_emulator(self, index_list: list[str]) -> None:
        """重新排序 emulator"""

        logger.info(f"重新排序全局 emulator: {index_list}")

        await self.EmulatorConfig.setOrder(list(map(uuid.UUID, index_list)))
        await self.EmulatorConfig.save()

    async def add_queue(self) -> tuple[uuid.UUID, QueueConfig]:
        """添加调度队列"""

        logger.info("添加调度队列")

        return await self.QueueConfig.add(QueueConfig)

    async def get_queue(self, queue_id: Optional[str]) -> tuple[list, dict]:
        """获取调度队列配置"""

        logger.info(f"获取调度队列配置: {queue_id}")

        if queue_id is None:
            data = await self.QueueConfig.toDict()
        else:
            data = await self.QueueConfig.get(uuid.UUID(queue_id))

        index = data.pop("instances", [])
        return list(index), data

    async def update_queue(
        self, queue_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新调度队列配置"""

        logger.info(f"更新调度队列配置: {queue_id}")

        queue_uid = uuid.UUID(queue_id)

        for group, items in data.items():
            for name, value in items.items():
                logger.debug(f"更新调度队列配置: {queue_id} - {group}.{name} = {value}")
                await self.QueueConfig[queue_uid].set(group, name, value)

        await self.QueueConfig.save()

    async def del_queue(self, queue_id: str) -> None:
        """删除调度队列配置"""

        logger.info(f"删除调度队列配置: {queue_id}")

        await self.QueueConfig.remove(uuid.UUID(queue_id))

    async def reorder_queue(self, index_list: list[str]) -> None:
        """重新排序调度队列"""

        logger.info(f"重新排序调度队列: {index_list}")

        await self.QueueConfig.setOrder(list(map(uuid.UUID, index_list)))

    async def get_time_set(
        self, queue_id: str, time_set_id: Optional[str]
    ) -> tuple[list, dict]:
        """获取时间设置配置"""

        logger.info(f"获取队列的时间配置: {queue_id} - {time_set_id}")

        queue_uid = uuid.UUID(queue_id)

        if time_set_id is None:
            data = await self.QueueConfig[queue_uid].TimeSet.toDict()
        else:
            data = await self.QueueConfig[queue_uid].TimeSet.get(uuid.UUID(time_set_id))

        index = data.pop("instances", [])
        return list(index), data

    async def add_time_set(self, queue_id: str) -> tuple[uuid.UUID, TimeSet]:
        """添加时间设置配置"""

        logger.info(f"{queue_id} 添加时间设置配置")

        queue_uid = uuid.UUID(queue_id)
        uid, config = await self.QueueConfig[queue_uid].TimeSet.add(TimeSet)

        await self.QueueConfig.save()
        return uid, config

    async def update_time_set(
        self, queue_id: str, time_set_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新时间设置配置"""

        logger.info(f"{queue_id} 更新时间设置配置: {time_set_id}")

        queue_uid = uuid.UUID(queue_id)
        time_set_uid = uuid.UUID(time_set_id)

        for group, items in data.items():
            for name, value in items.items():
                logger.debug(f"更新时间设置配置: {queue_id} - {group}.{name} = {value}")
                await (
                    self.QueueConfig[queue_uid]
                    .TimeSet[time_set_uid]
                    .set(group, name, value)
                )

        await self.QueueConfig.save()

    async def del_time_set(self, queue_id: str, time_set_id: str) -> None:
        """删除时间设置配置"""

        logger.info(f"{queue_id} 删除时间设置配置: {time_set_id}")

        queue_uid = uuid.UUID(queue_id)
        time_set_uid = uuid.UUID(time_set_id)

        await self.QueueConfig[queue_uid].TimeSet.remove(time_set_uid)
        await self.QueueConfig.save()

    async def reorder_time_set(self, queue_id: str, index_list: list[str]) -> None:
        """重新排序时间设置"""

        logger.info(f"{queue_id} 重新排序时间设置: {index_list}")

        queue_uid = uuid.UUID(queue_id)

        await self.QueueConfig[queue_uid].TimeSet.setOrder(
            list(map(uuid.UUID, index_list))
        )
        await self.QueueConfig.save()

    async def get_queue_item(
        self, queue_id: str, queue_item_id: Optional[str]
    ) -> tuple[list, dict]:
        """获取队列项配置"""

        logger.info(f"获取队列的队列项配置: {queue_id} - {queue_item_id}")

        queue_uid = uuid.UUID(queue_id)

        if queue_item_id is None:
            data = await self.QueueConfig[queue_uid].QueueItem.toDict()
        else:
            data = await self.QueueConfig[queue_uid].QueueItem.get(
                uuid.UUID(queue_item_id)
            )

        index = data.pop("instances", [])
        return list(index), data

    async def add_queue_item(self, queue_id: str) -> tuple[uuid.UUID, QueueItem]:
        """添加队列项配置"""

        logger.info(f"{queue_id} 添加队列项配置")

        queue_uid = uuid.UUID(queue_id)

        uid, config = await self.QueueConfig[queue_uid].QueueItem.add(QueueItem)
        await self.QueueConfig.save()
        return uid, config

    async def update_queue_item(
        self, queue_id: str, queue_item_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新队列项配置"""

        logger.info(f"{queue_id} 更新队列项配置: {queue_item_id}")

        queue_uid = uuid.UUID(queue_id)
        queue_item_uid = uuid.UUID(queue_item_id)

        for group, items in data.items():
            for name, value in items.items():
                logger.debug(f"更新队列项配置: {queue_id} - {group}.{name} = {value}")
                await (
                    self.QueueConfig[queue_uid]
                    .QueueItem[queue_item_uid]
                    .set(group, name, value)
                )

        await self.QueueConfig.save()

    async def del_queue_item(self, queue_id: str, queue_item_id: str) -> None:
        """删除队列项配置"""

        logger.info(f"{queue_id} 删除队列项配置: {queue_item_id}")

        queue_uid = uuid.UUID(queue_id)
        queue_item_uid = uuid.UUID(queue_item_id)

        await self.QueueConfig[queue_uid].QueueItem.remove(queue_item_uid)
        await self.QueueConfig.save()

    async def reorder_queue_item(self, queue_id: str, index_list: list[str]) -> None:
        """重新排序队列项"""

        logger.info(f"{queue_id} 重新排序队列项: {index_list}")

        queue_uid = uuid.UUID(queue_id)

        await self.QueueConfig[queue_uid].QueueItem.setOrder(
            list(map(uuid.UUID, index_list))
        )
        await self.QueueConfig.save()

    async def get_setting(self) -> Dict[str, Any]:
        """获取全局设置"""

        logger.info("获取全局设置")

        return await self.toDict(ignore_multi_config=True)

    async def update_setting(self, data: Dict[str, Dict[str, Any]]) -> None:
        """更新全局设置"""

        logger.info("更新全局设置")

        for group, items in data.items():
            for name, value in items.items():
                logger.debug(f"更新全局设置 - {group}.{name} = {value}")
                await self.set(group, name, value)

        logger.success("全局设置更新成功")

    async def get_webhook(
        self,
        script_id: Optional[str],
        user_id: Optional[str],
        webhook_id: Optional[str],
    ) -> tuple[list, dict]:
        """获取webhook配置"""

        if script_id is None and user_id is None:
            logger.info(f"获取全局webhook设置: {webhook_id}")

            if webhook_id is None:
                data = await self.Notify_CustomWebhooks.toDict()
            else:
                data = await self.Notify_CustomWebhooks.get(uuid.UUID(webhook_id))

        else:
            logger.info(f"获取webhook设置: {script_id} - {user_id} - {webhook_id}")

            script_uid = uuid.UUID(script_id)
            user_uid = uuid.UUID(user_id)

            if webhook_id is None:
                data = (
                    await self.ScriptConfig[script_uid]
                    .UserData[user_uid]
                    .Notify_CustomWebhooks.toDict()
                )
            else:
                data = (
                    await self.ScriptConfig[script_uid]
                    .UserData[user_uid]
                    .Notify_CustomWebhooks.get(uuid.UUID(webhook_id))
                )

        index = data.pop("instances", [])
        return list(index), data

    async def add_webhook(
        self, script_id: Optional[str], user_id: Optional[str]
    ) -> tuple[uuid.UUID, Webhook]:
        """添加webhook配置"""

        if script_id is None and user_id is None:
            logger.info("添加全局webhook配置")

            uid, config = await self.Notify_CustomWebhooks.add(Webhook)
            await self.save()
            return uid, config

        else:
            logger.info(f"添加webhook配置: {script_id} - {user_id}")

            script_uid = uuid.UUID(script_id)
            user_uid = uuid.UUID(user_id)

            uid, config = (
                await self.ScriptConfig[script_uid]
                .UserData[user_uid]
                .Notify_CustomWebhooks.add(Webhook)
            )
            await self.ScriptConfig.save()
            return uid, config

    async def update_webhook(
        self,
        script_id: Optional[str],
        user_id: Optional[str],
        webhook_id: str,
        data: Dict[str, Dict[str, Any]],
    ) -> None:
        """更新 webhook 配置"""

        webhook_uid = uuid.UUID(webhook_id)

        if script_id is None and user_id is None:
            logger.info(f"更新 webhook 全局配置: {webhook_id}")

            for group, items in data.items():
                for name, value in items.items():
                    logger.debug(
                        f"更新全局 webhook:{webhook_id} - {group}.{name} = {value}"
                    )
                    await self.Notify_CustomWebhooks[webhook_uid].set(
                        group, name, value
                    )

            await self.save()

        else:
            logger.info(f"更新 webhook 配置: {script_id} - {user_id} - {webhook_id}")

            script_uid = uuid.UUID(script_id)
            user_uid = uuid.UUID(user_id)

            for group, items in data.items():
                for name, value in items.items():
                    logger.debug(
                        f"更新用户 webhook: {script_id} - {user_id} - {webhook_id} - {group}.{name} = {value}"
                    )
                    await (
                        self.ScriptConfig[script_uid]
                        .UserData[user_uid]
                        .Notify_CustomWebhooks[webhook_uid]
                        .set(group, name, value)
                    )

            await self.ScriptConfig.save()

    async def del_webhook(
        self, script_id: Optional[str], user_id: Optional[str], webhook_id: str
    ) -> None:
        """删除 webhook 配置"""

        webhook_uid = uuid.UUID(webhook_id)

        if script_id is None and user_id is None:
            logger.info(f"删除全局 webhook 配置: {webhook_id}")

            await self.Notify_CustomWebhooks.remove(webhook_uid)
            await self.save()

        else:
            logger.info(f"删除 webhook 配置: {script_id} - {user_id} - {webhook_id}")

            script_uid = uuid.UUID(script_id)
            user_uid = uuid.UUID(user_id)

            await (
                self.ScriptConfig[script_uid]
                .UserData[user_uid]
                .Notify_CustomWebhooks.remove(webhook_uid)
            )
            await self.ScriptConfig.save()

    async def reorder_webhook(
        self, script_id: Optional[str], user_id: Optional[str], index_list: list[str]
    ) -> None:
        """重新排序 webhook"""

        if script_id is None and user_id is None:
            logger.info(f"重新排序全局 webhook: {index_list}")

            await self.Notify_CustomWebhooks.setOrder(list(map(uuid.UUID, index_list)))
            await self.save()

        else:
            logger.info(f"重新排序 webhook: {script_id} - {user_id} - {index_list}")

            script_uid = uuid.UUID(script_id)
            user_uid = uuid.UUID(user_id)

            await (
                self.ScriptConfig[script_uid]
                .UserData[user_uid]
                .Notify_CustomWebhooks.setOrder(list(map(uuid.UUID, index_list)))
            )
            await self.ScriptConfig.save()

    def get_proxy(self) -> Optional[httpx.Proxy]:
        """获取代理设置，返回适用于 httpx 的代理对象"""
        proxy_addr = self.get("Update", "ProxyAddress")
        if not proxy_addr:
            return None

        # 如果地址不包含协议，默认为 http
        if not proxy_addr.startswith(("http://", "https://", "socks5://", "socks4://")):
            proxy_addr = f"http://{proxy_addr}"

        try:
            return httpx.Proxy(proxy_addr)
        except Exception as e:
            logger.warning(f"代理配置无效: {proxy_addr}, 错误: {e}")
            return None

    async def get_stage_info(
        self,
        type: Literal[
            "Today",
            "ALL",
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
            "Info",
        ],
    ):
        """获取关卡信息"""

        if json.loads(self.get("Data", "Stage")) != {}:
            task = asyncio.create_task(self.get_stage())
            self.temp_task.append(task)
            task.add_done_callback(lambda t: self.temp_task.remove(t))
        else:
            await self.get_stage()

        if type == "Info":
            today = datetime.now(tz=UTC4).isoweekday()
            res_stage_info = []
            for stage in RESOURCE_STAGE_INFO:
                if (
                    today in stage["days"]
                    and stage["value"] in RESOURCE_STAGE_DROP_INFO
                ):
                    res_stage_info.append(RESOURCE_STAGE_DROP_INFO[stage["value"]])
            return {
                "Activity": json.loads(self.get("Data", "Stage")).get("Info", []),
                "Resource": res_stage_info,
            }
        elif type == "Today":
            data = json.loads(self.get("Data", "Stage")).get(
                datetime.now(tz=UTC4).strftime("%A"), []
            )
            for combox in data:
                combox["label"] = RESOURCE_STAGE_DATE_TEXT.get(
                    combox["value"], combox["label"]
                )
            return data
        else:
            return json.loads(self.get("Data", "Stage")).get(type, [])

    async def get_proxy_overview(self) -> Dict[str, Any]:
        """获取代理情况概览信息"""

        logger.info("获取代理情况概览信息")

        history_index = await self.search_history(
            "按日合并", datetime.now(tz=UTC4).date(), datetime.now(tz=UTC4).date()
        )
        if datetime.now(tz=UTC4).strftime("%Y年 %m月 %d日") not in history_index:
            return {}
        history_data = {
            k: await self.merge_statistic_info(v)
            for k, v in history_index[
                datetime.now(tz=UTC4).strftime("%Y年 %m月 %d日")
            ].items()
        }
        overview = {}
        for user, data in history_data.items():
            last_proxy_date = max(
                datetime.strptime(_["date"], "%Y年%m月%d日 %H:%M:%S")
                for _ in data.get("index", [])
            ).strftime("%Y年%m月%d日 %H:%M:%S")
            proxy_times = len(data.get("index", []))
            error_info = data.get("error_info", {})
            error_times = len(error_info)
            overview[user] = {
                "LastProxyDate": last_proxy_date,
                "ProxyTimes": proxy_times,
                "ErrorTimes": error_times,
                "ErrorInfo": error_info,
            }
        return overview

    async def get_stage(self) -> Optional[Dict[str, List[Dict[str, str]]]]:
        """更新活动关卡信息"""

        if datetime.now() - timedelta(hours=1) < datetime.strptime(
            self.get("Data", "LastStageUpdated"), "%Y-%m-%d %H:%M:%S"
        ):
            logger.info("一小时内已进行过一次检查, 直接使用缓存的活动关卡信息")
            return json.loads(self.get("Data", "Stage"))

        logger.info("开始获取活动关卡信息")

        try:
            async with httpx.AsyncClient(proxy=self.get_proxy()) as client:
                response = await client.get(
                    "https://api.maa.plus/MaaAssistantArknights/api/stageAndTasksUpdateTime.json"
                )
                if response.status_code == 200:
                    remote_time_stamp = datetime.strptime(
                        str(response.json().get("timestamp", 20000101000000)),
                        "%Y%m%d%H%M%S",
                    ).replace(tzinfo=UTC8)
                else:
                    logger.warning(f"无法从MAA服务器获取活动关卡时间戳:{response.text}")
                    remote_time_stamp = datetime.fromtimestamp(0, tz=UTC8)
        except Exception as e:
            logger.warning(f"无法从MAA服务器获取活动关卡时间戳: {e}")
            remote_time_stamp = datetime.fromtimestamp(0, tz=UTC8)

        local_time_stamp = datetime.strptime(
            self.get("Data", "StageTimeStamp"), "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=UTC8)

        # 本地关卡信息无需更新, 直接返回本地数据
        if datetime.fromtimestamp(0, tz=UTC8) < remote_time_stamp <= local_time_stamp:
            logger.info("使用本地关卡信息")
            await self.set(
                "Data", "LastStageUpdated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            return json.loads(self.get("Data", "Stage"))

        # 需要更新关卡信息
        logger.info("从远端更新关卡信息")

        try:
            async with httpx.AsyncClient(proxy=self.get_proxy()) as client:
                response = await client.get(
                    "https://api.maa.plus/MaaAssistantArknights/api/gui/StageActivity.json"
                )
                if response.status_code == 200:
                    remote_activity_stage_info = (
                        response.json().get("Official", {}).get("sideStoryStage", [])
                    )
                    if_get_maa_stage = True
                else:
                    logger.warning(f"无法从MAA服务器获取活动关卡信息:{response.text}")
                    if_get_maa_stage = False
                    remote_activity_stage_info = []
        except Exception as e:
            logger.warning(f"无法从MAA服务器获取活动关卡信息: {e}")
            if_get_maa_stage = False
            remote_activity_stage_info = []

        activity_stage_drop_info = []
        activity_stage_combox = []

        for stage in remote_activity_stage_info:
            if (
                datetime.strptime(
                    stage["Activity"]["UtcStartTime"], "%Y/%m/%d %H:%M:%S"
                ).replace(tzinfo=UTC8)
                < datetime.now(tz=UTC8)
                < datetime.strptime(
                    stage["Activity"]["UtcExpireTime"], "%Y/%m/%d %H:%M:%S"
                ).replace(tzinfo=UTC8)
            ):
                activity_stage_combox.append(
                    {"label": stage["Display"], "value": stage["Value"]}
                )

                if "SSReopen" not in stage["Display"]:
                    raw_drop = stage["Drop"]
                    drop_id = re.sub(
                        r"[\u200b\u200c\u200d\ufeff]", "", str(raw_drop).strip()
                    )  # 去除不可见字符

                    if drop_id.isdigit():
                        drop_name = MATERIALS_MAP.get(drop_id, "未知材料")
                    else:
                        drop_name = f"DESC:{drop_id}"  # 非纯数字, 直接用文本.加一个DESC前缀方便前端区分

                    activity_stage_drop_info.append(
                        {
                            "Display": stage["Display"],
                            "Value": stage["Value"],
                            "Drop": raw_drop,
                            "DropName": drop_name,
                            "Activity": stage["Activity"],
                        }
                    )

        stage_data = {}

        for day in range(0, 8):
            res_stage = []

            for stage in RESOURCE_STAGE_INFO:
                if day in stage["days"] or day == 0:
                    res_stage.append({"label": stage["text"], "value": stage["value"]})

            stage_data[calendar.day_name[day - 1] if day > 0 else "ALL"] = (
                res_stage[0:1] + activity_stage_combox + res_stage[1:]
            )

        stage_data["Info"] = activity_stage_drop_info

        if if_get_maa_stage:
            logger.success("成功获取远端活动关卡信息")
            await self.set(
                "Data", "LastStageUpdated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            await self.set(
                "Data",
                "StageTimeStamp",
                remote_time_stamp.strftime("%Y-%m-%d %H:%M:%S"),
            )
            await self.set("Data", "Stage", json.dumps(stage_data, ensure_ascii=False))

        return stage_data

    async def get_script_combox(self):
        """获取脚本下拉框信息"""

        logger.info("开始获取脚本下拉框信息")
        data = [{"label": "未选择", "value": "-"}]
        for uid, script in self.ScriptConfig.items():
            data.append(
                {
                    "label": f"{TYPE_BOOK[type(script).__name__]} - {script.get('Info', 'Name')}",
                    "value": str(uid),
                }
            )
        logger.success("脚本下拉框信息获取成功")

        return data

    async def get_task_combox(self):
        """获取任务下拉框信息"""

        logger.info("开始获取任务下拉框信息")
        data = [{"label": "未选择", "value": None}]
        for uid, queue in self.QueueConfig.items():
            data.append(
                {
                    "label": f"队列 - {queue.get('Info', 'Name')}",
                    "value": str(uid),
                }
            )
        for uid, script in self.ScriptConfig.items():
            if not script.is_locked:
                data.append(
                    {
                        "label": f"脚本 - {TYPE_BOOK[type(script).__name__]} - {script.get('Info', 'Name')}",
                        "value": str(uid),
                    }
                )
        logger.success("任务下拉框信息获取成功")

        return data

    async def get_plan_combox(self):
        """获取计划下拉框信息"""

        logger.info("开始获取计划下拉框信息")
        data = [{"label": "固定", "value": "Fixed"}]
        for uid, plan in self.PlanConfig.items():
            data.append({"label": plan.get("Info", "Name"), "value": str(uid)})
        logger.success("计划下拉框信息获取成功")

        return data

    async def get_emulator_combox(self):
        """获取模拟器下拉框信息"""

        logger.info("开始获取模拟器下拉框信息")
        data = [{"label": "未选择", "value": "-"}]
        for uid, emulator in self.EmulatorConfig.items():
            data.append({"label": emulator.get("Info", "Name"), "value": str(uid)})
        logger.success("模拟器下拉框信息获取成功")
        return data

    async def get_emulator_devices_combox(self, emulator_id: str):
        """获取模拟器多开实例下拉框信息"""

        logger.info("开始获取模拟器下拉框信息")

        if self.EmulatorConfig[uuid.UUID(emulator_id)].get("Data", "Type") == "general":
            logger.info("通用模拟器不支持扫描多开实例, 返回空列表")
            return []

        data = [{"label": "未选择", "value": "-"}]

        from .emulator_manager import EmulatorManager

        for index, device in (
            await (await EmulatorManager.get_emulator_instance(emulator_id)).getInfo(
                None
            )
        ).items():
            data.append({"label": device.title, "value": index})

        logger.success("模拟器下拉框信息获取成功")

        return data

    async def get_notice(self) -> tuple[bool, Dict[str, str]]:
        """获取公告信息"""

        local_notice = json.loads(self.get("Data", "Notice"))
        if datetime.now() - timedelta(hours=1) < datetime.strptime(
            self.get("Data", "LastNoticeUpdated"), "%Y-%m-%d %H:%M:%S"
        ):
            logger.info("一小时内已进行过一次检查, 直接使用缓存的公告信息")
            return False, local_notice.get("notice_dict", {})

        logger.info("开始从 AUTO-MAS 服务器获取公告信息")

        try:
            async with httpx.AsyncClient(proxy=self.get_proxy()) as client:
                response = await client.get(
                    "https://download.auto-mas.top/d/AUTO-MAS/Server/notice.json"
                )
                if response.status_code == 200:
                    remote_notice = response.json()
                else:
                    logger.warning(
                        f"无法从 AUTO-MAS 服务器获取公告信息:{response.text}"
                    )
                    remote_notice = None
        except Exception as e:
            logger.warning(f"无法从 AUTO-MAS 服务器获取公告信息: {e}")
            remote_notice = None

        if remote_notice is None:
            logger.warning("使用本地公告信息")
            return False, local_notice.get("notice_dict", {})

        await self.set(
            "Data", "LastNoticeUpdated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        local_time_stamp = datetime.strptime(
            local_notice.get("time", "2000-01-01 00:00"), "%Y-%m-%d %H:%M"
        ).replace(tzinfo=UTC8)
        remote_time_stamp = datetime.strptime(
            remote_notice.get("time", "2000-01-01 00:00"), "%Y-%m-%d %H:%M"
        ).replace(tzinfo=UTC8)

        # 本地公告信息需更新且持续展示
        if local_time_stamp < remote_time_stamp < datetime.now(tz=UTC8):
            logger.info("要求展示本地公告信息")
            await self.set(
                "Data", "Notice", json.dumps(remote_notice, ensure_ascii=False)
            )
            await self.set("Data", "IfShowNotice", True)

        return self.get("Data", "IfShowNotice"), remote_notice.get("notice_dict", {})

    async def get_web_config(self):
        """获取「AUTO-MAS 配置分享中心」配置"""

        local_web_config = json.loads(self.get("Data", "WebConfig"))
        if datetime.now() - timedelta(hours=1) < datetime.strptime(
            self.get("Data", "LastWebConfigUpdated"), "%Y-%m-%d %H:%M:%S"
        ):
            logger.info("一小时内已进行过一次检查, 直接使用缓存的配置分享中心信息")
            return local_web_config

        logger.info("开始从 AUTO-MAS 服务器获取配置分享中心信息")

        try:
            async with httpx.AsyncClient(proxy=self.get_proxy()) as client:
                response = await client.get(
                    "https://share.auto-mas.top/api/list/config/general"
                )
                if response.status_code == 200:
                    remote_web_config = response.json()
                else:
                    logger.warning(
                        f"无法从 AUTO-MAS 服务器获取配置分享中心信息:{response.text}"
                    )
                    remote_web_config = None
        except Exception as e:
            logger.warning(f"无法从 AUTO-MAS 服务器获取配置分享中心信息: {e}")
            remote_web_config = None

        if remote_web_config is None:
            logger.warning("使用本地配置分享中心信息")
            return local_web_config

        await self.set(
            "Data", "LastWebConfigUpdated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        await self.set(
            "Data", "WebConfig", json.dumps(remote_web_config, ensure_ascii=False)
        )

        return remote_web_config

    async def save_maa_log(self, log_path: Path, logs: list, maa_result: str) -> bool:
        """
        保存MAA日志并生成对应统计数据

        :param log_path: 日志文件保存路径
        :type log_path: Path
        :param logs: 日志内容列表
        :type logs: list
        :param maa_result: MAA 结果
        :type maa_result: str
        :return: 是否包含6★招募
        :rtype: bool
        """

        logger.info(f"开始处理 MAA 日志, 日志长度: {len(logs)}, 日志标记: {maa_result}")

        data = {
            "recruit_statistics": defaultdict(int),
            "drop_statistics": defaultdict(dict),
            "sanity": 0,
            "sanity_full_at": "",
            "maa_result": maa_result,
        }

        if_six_star = False

        # 提取理智相关信息
        for log_line in logs:
            # 提取当前理智值：理智: 5/180
            sanity_match = re.search(r"理智:\s*(\d+)/\d+", log_line)
            if sanity_match:
                data["sanity"] = int(sanity_match.group(1))

            # 提取理智回满时间：理智将在 2025-09-26 18:57 回满。(17h 29m 后)
            sanity_full_match = re.search(
                r"(理智将在\s*\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s*回满。\(\d+h\s+\d+m\s+后\))",
                log_line,
            )
            if sanity_full_match:
                data["sanity_full_at"] = sanity_full_match.group(1)

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
                        if current_star_level == "6★":
                            if_six_star = True

            if "已确认招募" in logs[i]:  # 只有确认招募后才统计
                confirmed_recruit = True

            if confirmed_recruit and current_star_level:
                data["recruit_statistics"][current_star_level] += 1
                confirmed_recruit = False  # 重置, 等待下一次公招
                current_star_level = None  # 清空已处理的星级

            i += 1

        # 掉落统计
        # 存储所有关卡的掉落统计
        all_stage_drops = {}

        # 查找所有Fight任务的开始和结束位置
        fight_tasks = []
        for i, line in enumerate(logs):
            if "开始任务: Fight" in line or "开始任务: 刷理智" in line:
                # 查找对应的任务结束位置
                end_index = -1
                for j in range(i + 1, len(logs)):
                    if "完成任务: Fight" in logs[j] or "完成任务: 刷理智" in logs[j]:
                        end_index = j
                        break
                    # 如果遇到新的Fight任务开始, 则当前任务没有正常结束
                    if j < len(logs) and (
                        "开始任务: Fight" in logs[j] or "开始任务: 刷理智" in logs[j]
                    ):
                        break

                # 如果找到了结束位置, 记录这个任务的范围
                if end_index != -1:
                    fight_tasks.append((i, end_index))

        # 处理每个Fight任务
        for start_idx, end_idx in fight_tasks:
            # 提取当前任务的日志
            task_logs = logs[start_idx : end_idx + 1]

            # 查找任务中的最后一次掉落统计
            last_drop_stats = {}
            current_stage = None

            for line in task_logs:
                # 匹配掉落统计行, 如"1-7 掉落统计:"
                drop_match = re.search(r"([A-Za-z0-9\-]+) 掉落统计:", line)
                if drop_match:
                    # 发现新的掉落统计, 重置当前关卡的掉落数据
                    current_stage = drop_match.group(1)
                    last_drop_stats = {}
                    continue

                # 如果已经找到了关卡, 处理掉落物
                if current_stage:
                    item_match: List[str] = re.findall(
                        r"^(?!\[)(\S+?)\s*:\s*([\d,]+)(?:\s*\(\+[\d,]+\))?",
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
                            last_drop_stats[item] = total

            # 如果任务中有掉落统计, 更新总统计
            if current_stage and last_drop_stats:
                if current_stage not in all_stage_drops:
                    all_stage_drops[current_stage] = {}

                # 累加掉落数据
                for item, count in last_drop_stats.items():
                    all_stage_drops[current_stage].setdefault(item, 0)
                    all_stage_drops[current_stage][item] += count

        # 将累加后的掉落数据保存到结果中
        data["drop_statistics"] = all_stage_drops

        # 保存日志
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(logs), encoding="utf-8")
        # 保存统计数据
        log_path.with_suffix(".json").write_text(
            json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8"
        )

        logger.success(f"MAA 日志统计完成, 日志路径: {log_path}")

        return if_six_star

    async def save_general_log(
        self, log_path: Path, logs: list, general_result: str
    ) -> None:
        """
        保存通用日志并生成对应统计数据

        :param log_path: 日志文件保存路径
        :param logs: 日志内容列表
        :param general_result: 待保存的日志结果信息
        """

        logger.info(
            f"开始处理通用日志, 日志长度: {len(logs)}, 日志标记: {general_result}"
        )

        data: Dict[str, str] = {"general_result": general_result}

        # 保存日志
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.with_suffix(".log").write_text("\n".join(logs), encoding="utf-8")
        log_path.with_suffix(".json").write_text(
            json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8"
        )

        logger.success(f"通用日志统计完成, 日志路径: {log_path.with_suffix('.log')}")

    async def merge_statistic_info(self, statistic_path_list: List[Path]) -> dict:
        """
        合并指定数据统计信息文件

        :param statistic_path_list: 需要合并的统计信息文件路径列表
        :return: 合并后的统计信息字典
        """

        logger.info(f"开始合并统计信息文件, 共计 {len(statistic_path_list)} 个文件")

        data: Dict[str, Any] = {"index": {}}

        for json_file in statistic_path_list:
            try:
                single_data = json.loads(json_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(
                    f"无法解析文件 {json_file}, 错误信息: {type(e).__name__}: {str(e)}"
                )
                continue

            for key in single_data.keys():
                if key not in data:
                    data[key] = {}

                # 合并公招统计
                if key == "recruit_statistics":
                    for star_level, count in single_data[key].items():
                        if star_level not in data[key]:
                            data[key][star_level] = 0
                        data[key][star_level] += count

                # 合并掉落统计
                elif key == "drop_statistics":
                    for stage, drops in single_data[key].items():
                        if stage not in data[key]:
                            data[key][stage] = {}  # 初始化关卡

                        for item, count in drops.items():
                            if item not in data[key][stage]:
                                data[key][stage][item] = 0
                            data[key][stage][item] += count

                # 处理理智相关字段 - 使用最后一个文件的值
                elif key in ["sanity", "sanity_full_at"]:
                    data[key] = single_data[key]

                # 录入运行结果
                elif key in ["maa_result", "general_result"]:
                    actual_date = (
                        datetime.strptime(
                            f"{json_file.parent.parent.name} {json_file.stem}",
                            "%Y-%m-%d %H-%M-%S",
                        )
                        .replace(tzinfo=UTC4)
                        .astimezone()
                    )

                    if single_data[key] != "Success!":
                        if "error_info" not in data:
                            data["error_info"] = {}
                        data["error_info"][
                            actual_date.strftime("%Y年%m月%d日 %H:%M:%S")
                        ] = single_data[key]

                    data["index"][actual_date] = {
                        "date": actual_date.strftime("%Y年%m月%d日 %H:%M:%S"),
                        "status": (
                            "完成" if single_data[key] == "Success!" else "异常"
                        ),
                        "jsonFile": str(json_file),
                    }

        data["index"] = [data["index"][_] for _ in sorted(data["index"])]

        logger.success(f"统计信息合并完成, 共计 {len(data['index'])} 条记录")

        # 确保返回的字典始终包含 index 字段，即使为空
        result = {k: v for k, v in data.items() if v}
        if "index" not in result:
            result["index"] = []

        return result

    async def search_history(self, mode: str, start_date: date, end_date: date) -> dict:
        """
        搜索指定范围内的历史记录

        :param mode: 合并模式（按日合并、按周合并、按月合并）
        :param start_date: 开始日期
        :param end_date: 结束日期
        :return: 搜索到的历史记录字典
        """

        logger.info(
            f"开始搜索历史记录, 合并模式: {mode}, 日期范围: {start_date} 至 {end_date}"
        )

        history_dict = {}

        for date_folder in self.history_path.iterdir():
            if not date_folder.is_dir():
                continue  # 只处理日期文件夹

            try:
                date = datetime.strptime(date_folder.name, "%Y-%m-%d").date()

                if not (start_date <= date <= end_date):
                    continue  # 只统计在范围内的日期

                if mode == "按日合并":
                    date_name = date.strftime("%Y年 %m月 %d日")
                elif mode == "按周合并":
                    year, week, _ = date.isocalendar()
                    date_name = f"{year}年 第{week}周"
                elif mode == "按月合并":
                    date_name = date.strftime("%Y年 %m月")
                else:
                    raise ValueError("无效的合并模式")

                if date_name not in history_dict:
                    history_dict[date_name] = {}

                for user_folder in date_folder.iterdir():
                    if not user_folder.is_dir():
                        continue  # 只处理用户文件夹

                    if user_folder.stem not in history_dict[date_name]:
                        history_dict[date_name][user_folder.stem] = list(
                            user_folder.with_suffix("").glob("*.json")
                        )
                    else:
                        history_dict[date_name][user_folder.stem] += list(
                            user_folder.with_suffix("").glob("*.json")
                        )

            except ValueError:
                logger.warning(f"非日期格式的目录: {date_folder}")

        logger.success(f"历史记录搜索完成, 共计 {len(history_dict)} 条记录")

        return {
            k: v
            for k, v in sorted(history_dict.items(), key=lambda x: x[0], reverse=True)
        }

    async def clean_old_history(self):
        """删除超过用户设定天数的历史记录文件（基于目录日期）"""

        if self.get("Function", "HistoryRetentionTime") == 0:
            logger.info("历史记录永久保留, 跳过历史记录清理")
            return

        logger.info("开始清理超过设定天数的历史记录")

        deleted_count = 0

        for date_folder in self.history_path.iterdir():
            if not date_folder.is_dir():
                continue  # 只处理日期文件夹

            try:
                # 只检查 `YYYY-MM-DD` 格式的文件夹
                folder_date = datetime.strptime(date_folder.name, "%Y-%m-%d").date()
                if datetime.now(tz=UTC4).date() - folder_date > timedelta(
                    days=self.get("Function", "HistoryRetentionTime")
                ):
                    shutil.rmtree(date_folder, ignore_errors=True)
                    deleted_count += 1
                    logger.info(f"已删除超期日志目录: {date_folder}")
            except ValueError:
                logger.warning(f"非日期格式的目录: {date_folder}")

        logger.success(f"清理完成: {deleted_count} 个日期目录")


Config = AppConfig()
