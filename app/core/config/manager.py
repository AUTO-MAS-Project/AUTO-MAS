#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

import os
import sys
import httpx
import shutil
import asyncio
import uvicorn
import sqlite3
import tomllib
import truststore
from pathlib import Path
from fastapi import WebSocket
from jinja2 import Environment, FileSystemLoader
from datetime import datetime, timedelta, date
from typing import Literal, Optional, Dict, Any, List, ClassVar, cast
import uuid
import json

from app.models.common import EmulatorConfig, QueueConfig, QueueItem, TimeSet, Webhook
from app.models.general import GeneralConfig, GeneralUserConfig
from app.models.global_config import GlobalConfig
from app.models.maa import MaaConfig, MaaPlanConfig, MaaUserConfig
from app.models.maaend import MaaEndConfig, MaaEndUserConfig
from app.models.src import SrcConfig, SrcUserConfig
from .base import dump_toml
from app.models.shared import WebSocketMessage
from app.utils.constants import (
    UTC4,
    UTC8,
    RESOURCE_STAGE_INFO,
    RESOURCE_STAGE_DROP_INFO,
    TYPE_BOOK,
    RESOURCE_STAGE_DATE_TEXT,
)
from app.utils import get_logger
from app.services.git_service import GitService
from app.services.log_service import LogService
from app.services.migration import MigrationService

logger = get_logger("配置管理")

ScriptConfigClass = (
    type[MaaConfig] | type[SrcConfig] | type[GeneralConfig] | type[MaaEndConfig]
)
ScriptConfigData = MaaConfig | SrcConfig | GeneralConfig | MaaEndConfig

if (Path.cwd() / "environment/git/bin/git.exe").exists():
    os.environ["GIT_PYTHON_GIT_EXECUTABLE"] = str(
        Path.cwd() / "environment/git/bin/git.exe"
    )

try:
    from git import Repo
except ImportError:
    Repo = None


class AppConfig(GlobalConfig):
    VERSION: ClassVar[str] = "v5.2.0-beta.1"

    def __init__(self) -> None:
        super().__init__()

        logger.info("")
        logger.info("===================================")
        logger.info("AUTO-MAS 后端应用程序")
        logger.info(f"版本号:  {self.VERSION}")
        logger.info(f"工作目录:  {Path.cwd()}")
        logger.info("===================================")

        object.__setattr__(self, "log_path", Path.cwd() / "debug/app.log")
        object.__setattr__(self, "database_path", Path.cwd() / "data/data.db")
        object.__setattr__(self, "config_path", Path.cwd() / "config")
        object.__setattr__(self, "history_path", Path.cwd() / "history")
        # 检查目录
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.mkdir(parents=True, exist_ok=True)
        self.history_path.mkdir(parents=True, exist_ok=True)

        # 初始化Git仓库（如果可用）
        try:
            if Repo is not None:
                object.__setattr__(self, "repo", Repo(Path.cwd()))
            else:
                object.__setattr__(self, "repo", None)
        except (OSError, ValueError) as e:
            logger.warning(f"Git仓库初始化失败: {e}")
            object.__setattr__(self, "repo", None)

        object.__setattr__(
            self,
            "notify_env",
            Environment(loader=FileSystemLoader(str(Path.cwd() / "res/html"))),
        )

        object.__setattr__(self, "server", None)
        object.__setattr__(self, "websocket", None)
        object.__setattr__(self, "web_connections", set())
        object.__setattr__(self, "power_sign", "NoAction")
        object.__setattr__(self, "temp_task", [])

        object.__setattr__(self, "_migration_service", MigrationService(self))
        object.__setattr__(self, "_log_service", LogService(self.history_path))

        truststore.inject_into_ssl()

    def _resolve_config_path(self, stem: str) -> Path:
        """返回运行期 TOML 配置路径。"""

        return self.config_path / f"{stem}.toml"

    async def _connect_runtime_configs(self) -> None:
        """连接运行期主配置文件。"""

        await self.connect(self._resolve_config_path("Config"))
        await self.EmulatorConfig.connect(self._resolve_config_path("EmulatorConfig"))
        await self.PlanConfig.connect(self._resolve_config_path("PlanConfig"))
        await self.ScriptConfig.connect(self._resolve_config_path("ScriptConfig"))
        await self.PluginConfig.connect(self._resolve_config_path("PluginConfig"))
        await self.QueueConfig.connect(self._resolve_config_path("QueueConfig"))
        await self.ToolsConfig.connect(self._resolve_config_path("ToolsConfig"))

    def _read_mapping_config(self, path: Path) -> dict[str, Any]:
        """读取 TOML/JSON 字典配置文件并返回映射对象。"""

        if not path.exists():
            return {}

        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return {}

        if path.suffix == ".toml":
            data = tomllib.loads(text)
        else:
            data = json.loads(text)
        if isinstance(data, dict):
            return cast(dict[str, Any], data)
        return {}

    def _write_mapping_config(self, path: Path, data: dict[str, Any]) -> None:
        """将字典配置写入 TOML/JSON 文件。"""

        if path.suffix == ".toml":
            path.write_text(dump_toml(data), encoding="utf-8")
            return

        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8"
        )

    async def init_config(self) -> None:
        """初始化配置管理"""

        await self.check_data()

        await self._connect_runtime_configs()

        from app.services import System

        self.bind("Start", "IfSelfStart", System.set_SelfStart)
        self.bind("Function", "IfAllowSleep", System.set_Sleep)
        await System.set_SelfStart(self.get("Start", "IfSelfStart"))
        await System.set_Sleep(self.get("Function", "IfAllowSleep"))

        self.loop = asyncio.get_running_loop()
        object.__setattr__(
            self, "_git_service", GitService(self.repo, self.loop)
        )

        logger.info("程序初始化完成")

    async def check_data(self) -> None:
        """检查用户数据文件并处理数据文件版本更新"""

        await self._migration_service.check_data()

    async def send_json(self, data: dict[str, Any]) -> None:
        """通过WebSocket发送JSON数据（桌面 + 所有 Web 连接）"""
        if Config.websocket is None and not Config.web_connections:
            logger.warning("WebSocket 未连接")
            return

        if Config.websocket is not None:
            try:
                await Config.websocket.send_json(data)
            except Exception:
                logger.warning("桌面 WebSocket 发送失败")

        dead: list[WebSocket] = []
        for ws in Config.web_connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            Config.web_connections.discard(ws)

    async def send_websocket_message(
        self,
        id: str,
        type: Literal["Update", "Message", "Info", "Signal"],
        data: Dict[str, Any],
    ) -> None:
        """通过WebSocket发送消息（桌面 + 所有 Web 连接）"""
        msg = WebSocketMessage(id=id, type=type, data=data).model_dump()
        await self.send_json(msg)

    async def get_git_version(self) -> tuple[bool, str, str]:
        """获取Git版本信息，如果Git不可用则返回默认值"""

        return await self._git_service.get_git_version()

    async def add_script(
        self,
        script: Literal["MAA", "SRC", "General", "MaaEnd"],
        script_id: str | None = None,
    ) -> tuple[uuid.UUID, Any]:
        """添加脚本配置"""

        logger.info(f"添加脚本配置: {script}, 从 {script_id} 复制")

        script_class_map: dict[
            Literal["MAA", "SRC", "General", "MaaEnd"], ScriptConfigClass
        ] = {
            "MAA": MaaConfig,
            "SRC": SrcConfig,
            "General": GeneralConfig,
            "MaaEnd": MaaEndConfig,
        }
        script_class = script_class_map[script]

        if script_id is None:
            return await self.ScriptConfig.add(script_class)
        else:
            script_uid = uuid.UUID(script_id)

            if type(self.ScriptConfig[script_uid]) is not script_class:
                raise TypeError(f"脚本配置类型不匹配: {script_id} {script}")

            new_uid, new_config = await self.ScriptConfig.add(script_class)

            await new_config.load(
                await self.ScriptConfig[script_uid].toDict(regenerate_uuids=True)
            )

            # 复制用户数据
            if (Path.cwd() / f"data/{script_id}").exists():
                shutil.copytree(
                    Path.cwd() / f"data/{script_id}",
                    Path.cwd() / f"data/{new_uid}",
                    dirs_exist_ok=True,
                )
                for old_user, new_user in zip(
                    self.ScriptConfig[script_uid].UserData.keys(),
                    new_config.UserData.keys(),
                ):
                    if (Path.cwd() / f"data/{new_uid}/{old_user}").exists():
                        (Path.cwd() / f"data/{new_uid}/{old_user}").rename(
                            Path.cwd() / f"data/{new_uid}/{new_user}"
                        )

            return new_uid, new_config

    async def get_script(
        self, script_id: str | None
    ) -> tuple[list[dict[str, str]], dict[str, Any]]:
        """获取脚本配置"""

        logger.info(f"获取脚本配置: {script_id}")
        return await self.ScriptConfig.get_item(script_id)

    async def update_script(
        self, script_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新脚本配置"""

        logger.info(f"更新脚本配置: {script_id}")

        uid = uuid.UUID(script_id)

        if self.ScriptConfig[uid].is_locked:
            raise RuntimeError(f"脚本 {script_id} 正在运行, 无法更新配置项")

        await self.ScriptConfig.update_item(script_id, data)

    async def del_script(self, script_id: str) -> None:
        """删除脚本配置"""

        logger.info(f"删除脚本配置: {script_id}")

        uid = uuid.UUID(script_id)

        if self.ScriptConfig[uid].is_locked:
            raise RuntimeError(f"脚本 {script_id} 正在运行, 无法删除")

        await self.ScriptConfig.del_item(script_id)
        if (Path.cwd() / f"data/{uid}").exists():
            shutil.rmtree(Path.cwd() / f"data/{uid}")

    async def reorder_script(self, index_list: list[str]) -> None:
        """重新排序脚本"""

        logger.info(f"重新排序脚本: {index_list}")

        await self.ScriptConfig.reorder_items(index_list)

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

        temp = await self.ScriptConfig[uid].toDict(if_decrypt=False)
        temp.pop("sub_configs_info", None)
        temp = await self.remove_privacy_info(temp, Path(file_path).stem)

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
        async with httpx.AsyncClient(
            proxy=Config.proxy, follow_redirects=True
        ) as client:
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

        if data.get("code", 200) == 500:
            logger.error(f"从 AUTO-MAS 服务器获取配置内容失败: {data.get('message')}")
            raise ConnectionError(
                f"从 AUTO-MAS 服务器获取配置内容失败: {data.get('message')}"
            )

        await self.ScriptConfig[uid].load(data)

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

        temp = await self.ScriptConfig[uid].toDict(if_decrypt=False)
        temp.pop("sub_configs_info", None)
        temp = await self.remove_privacy_info(temp, config_name)

        files = {
            "file": (
                f"{config_name}&&{author}&&{description}&&{int(datetime.now(tz=UTC8).timestamp() * 1000)}.json",
                json.dumps(temp, ensure_ascii=False),
                "application/json",
            )
        }
        data = {"username": author, "description": description}

        async with httpx.AsyncClient(
            proxy=Config.proxy, follow_redirects=True
        ) as client:
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

    async def remove_privacy_info(
        self, confg: dict[str, Any], name: str
    ) -> dict[str, Any]:
        """移除配置中可能存在的隐私信息"""

        confg["info"]["name"] = name
        for path in ["script_path", "config_path", "log_path", "track_process_exe"]:
            if Path(confg["script"][path]).is_relative_to(
                Path(confg["info"]["root_path"])
            ):
                confg["script"][path] = str(
                    Path(r"C:/脚本根目录")
                    / Path(confg["script"][path]).relative_to(
                        Path(confg["info"]["root_path"])
                    )
                )
            if sys.platform == "win32" and Path(confg["script"][path]).is_relative_to(
                Path(os.environ["APPDATA"])
            ):
                confg["script"][path] = (
                    f"%APPDATA%/{Path(confg['script'][path]).relative_to(Path(os.environ['APPDATA']))}"
                )
        confg["info"]["root_path"] = str(Path(r"C:/脚本根目录"))

        return confg

    async def get_user(
        self, script_id: str, user_id: Optional[str]
    ) -> tuple[list[dict[str, str]], dict[str, Any]]:
        """获取用户配置"""

        logger.info(f"获取用户配置: {script_id} - {user_id}")

        return await self.ScriptConfig[uuid.UUID(script_id)].UserData.get_item(user_id)

    async def add_user(self, script_id: str) -> tuple[uuid.UUID, Any]:
        """添加用户配置"""

        logger.info(f"{script_id} 添加用户配置")

        script_config = self.ScriptConfig[uuid.UUID(script_id)]

        # 根据脚本类型选择添加对应用户配置
        if isinstance(script_config, MaaConfig):
            uid, config = await script_config.UserData.add(MaaUserConfig)
        elif isinstance(script_config, SrcConfig):
            uid, config = await script_config.UserData.add(SrcUserConfig)
        elif isinstance(script_config, GeneralConfig):
            uid, config = await script_config.UserData.add(GeneralUserConfig)
        else:
            uid, config = await script_config.UserData.add(MaaEndUserConfig)

        return uid, config

    async def update_user(
        self, script_id: str, user_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新用户配置"""

        logger.info(f"{script_id} 更新用户配置: {user_id}")

        await self.ScriptConfig[uuid.UUID(script_id)].UserData.update_item(user_id, data)

    async def del_user(self, script_id: str, user_id: str) -> None:
        """删除用户配置"""

        logger.info(f"{script_id} 删除用户配置: {user_id}")

        script_uid = uuid.UUID(script_id)
        user_uid = uuid.UUID(user_id)

        await self.ScriptConfig[script_uid].UserData.remove(user_uid)
        if (Path.cwd() / f"data/{script_id}/{user_id}").exists():
            shutil.rmtree(Path.cwd() / f"data/{script_id}/{user_id}")

    async def reorder_user(self, script_id: str, index_list: list[str]) -> None:
        """重新排序用户"""

        logger.info(f"{script_id} 重新排序用户: {index_list}")

        await self.ScriptConfig[uuid.UUID(script_id)].UserData.reorder_items(index_list)

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

        # 如果标题为默认标题, 则使用文件名作为标题
        if infrast_data.get("title", "文件标题") == "文件标题":
            infrast_data["title"] = json_path.stem

        await (
            self.ScriptConfig[script_uid]
            .UserData[user_uid]
            .set("Data", "CustomInfrast", json.dumps(infrast_data, ensure_ascii=False))
        )

    async def get_user_combox_infrastructure(
        self, script_id: str, user_id: str
    ) -> list[dict[str, str]]:
        logger.info(f"获取用户自定义基建排班下拉框信息: {script_id} - {user_id}")

        script_uid = uuid.UUID(script_id)
        user_uid = uuid.UUID(user_id)

        script_config = self.ScriptConfig[script_uid]

        # 根据脚本类型选择添加对应用户配置
        if not isinstance(script_config, MaaConfig):
            raise TypeError(f"不支持的脚本配置类型: {type(script_config)}")

        logger.info("开始获取用户自定义基建排班下拉框信息")

        data: list[dict[str, str]] = []
        for i, plan in enumerate(
            json.loads(
                script_config.UserData[user_uid].get("Data", "CustomInfrast")
            ).get("plans", [])
        ):
            plan_mapping = cast(dict[str, Any], plan)
            data.append(
                {"label": str(plan_mapping.get("name", f"排班 {i+1}")), "value": str(i)}
            )

        logger.success("用户自定义基建排班下拉框信息获取成功")

        return data

    async def add_plan(
        self, script: Literal["MaaPlan"]
    ) -> tuple[uuid.UUID, MaaPlanConfig]:
        """添加计划表"""

        logger.info(f"添加计划表: {script}")

        return await self.PlanConfig.add(MaaPlanConfig)

    async def get_plan(
        self, plan_id: Optional[str]
    ) -> tuple[list[dict[str, str]], dict[str, Any]]:
        """获取计划表配置"""

        logger.info(f"获取计划表配置: {plan_id}")

        return await self.PlanConfig.get_item(plan_id)

    async def update_plan(self, plan_id: str, data: Dict[str, Dict[str, Any]]) -> None:
        """更新计划表配置"""

        logger.info(f"更新计划表配置: {plan_id}")

        await self.PlanConfig.update_item(plan_id, data)

    async def del_plan(self, plan_id: str) -> None:
        """删除计划表配置"""

        logger.info(f"删除计划表配置: {plan_id}")

        await self.PlanConfig.del_item(plan_id)

    async def reorder_plan(self, index_list: list[str]) -> None:
        """重新排序计划表"""

        logger.info(f"重新排序计划表: {index_list}")

        await self.PlanConfig.reorder_items(index_list)

    async def get_emulator(
        self, emulator_id: Optional[str]
    ) -> tuple[list[dict[str, str]], dict[str, Any]]:
        """获取模拟器配置"""
        logger.info(f"获取全局模拟器设置: {emulator_id}")

        return await self.EmulatorConfig.get_item(emulator_id)

    async def add_emulator(self) -> tuple[uuid.UUID, EmulatorConfig]:
        """添加模拟器配置"""
        logger.info("添加全局模拟器配置")

        uid, config = await self.EmulatorConfig.add(EmulatorConfig)
        return uid, config

    async def update_emulator(
        self, emulator_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新模拟器配置"""

        logger.info(f"更新模拟器配置: {emulator_id}")

        await self.EmulatorConfig.update_item(emulator_id, data)

    async def del_emulator(self, emulator_id: str) -> None:
        """删除模拟器配置"""

        logger.info(f"删除全局模拟器配置: {emulator_id}")

        await self.EmulatorConfig.del_item(emulator_id)

    async def reorder_emulator(self, index_list: list[str]) -> None:
        """重新排序模拟器"""

        logger.info(f"重新排序模拟器: {index_list}")

        await self.EmulatorConfig.reorder_items(index_list)

    async def add_queue(self) -> tuple[uuid.UUID, QueueConfig]:
        """添加调度队列"""

        logger.info("添加调度队列")

        return await self.QueueConfig.add(QueueConfig)

    async def get_queue(
        self, queue_id: Optional[str]
    ) -> tuple[list[dict[str, str]], dict[str, Any]]:
        """获取调度队列配置"""

        logger.info(f"获取调度队列配置: {queue_id}")

        return await self.QueueConfig.get_item(queue_id)

    async def update_queue(
        self, queue_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新调度队列配置"""

        logger.info(f"更新调度队列配置: {queue_id}")

        await self.QueueConfig.update_item(queue_id, data)

    async def del_queue(self, queue_id: str) -> None:
        """删除调度队列配置"""

        logger.info(f"删除调度队列配置: {queue_id}")

        await self.QueueConfig.del_item(queue_id)

    async def reorder_queue(self, index_list: list[str]) -> None:
        """重新排序调度队列"""

        logger.info(f"重新排序调度队列: {index_list}")

        await self.QueueConfig.reorder_items(index_list)

    async def get_time_set(
        self, queue_id: str, time_set_id: Optional[str]
    ) -> tuple[list[dict[str, str]], dict[str, Any]]:
        """获取时间设置配置"""

        logger.info(f"获取队列的时间配置: {queue_id} - {time_set_id}")

        return await self.QueueConfig[uuid.UUID(queue_id)].TimeSet.get_item(time_set_id)

    async def add_time_set(self, queue_id: str) -> tuple[uuid.UUID, TimeSet]:
        """添加时间设置配置"""

        logger.info(f"{queue_id} 添加时间设置配置")

        queue_uid = uuid.UUID(queue_id)
        uid, config = await self.QueueConfig[queue_uid].TimeSet.add(TimeSet)

        return uid, config

    async def update_time_set(
        self, queue_id: str, time_set_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新时间设置配置"""

        logger.info(f"{queue_id} 更新时间设置配置: {time_set_id}")

        await self.QueueConfig[uuid.UUID(queue_id)].TimeSet.update_item(time_set_id, data)

    async def del_time_set(self, queue_id: str, time_set_id: str) -> None:
        """删除时间设置配置"""

        logger.info(f"{queue_id} 删除时间设置配置: {time_set_id}")

        await self.QueueConfig[uuid.UUID(queue_id)].TimeSet.del_item(time_set_id)

    async def reorder_time_set(self, queue_id: str, index_list: list[str]) -> None:
        """重新排序时间设置"""

        logger.info(f"{queue_id} 重新排序时间设置: {index_list}")

        await self.QueueConfig[uuid.UUID(queue_id)].TimeSet.reorder_items(index_list)

    async def get_queue_item(
        self, queue_id: str, queue_item_id: Optional[str]
    ) -> tuple[list[dict[str, str]], dict[str, Any]]:
        """获取队列项配置"""

        logger.info(f"获取队列的队列项配置: {queue_id} - {queue_item_id}")

        return await self.QueueConfig[uuid.UUID(queue_id)].QueueItem.get_item(queue_item_id)

    async def add_queue_item(self, queue_id: str) -> tuple[uuid.UUID, QueueItem]:
        """添加队列项配置"""

        logger.info(f"{queue_id} 添加队列项配置")

        queue_uid = uuid.UUID(queue_id)

        uid, config = await self.QueueConfig[queue_uid].QueueItem.add(QueueItem)

        return uid, config

    async def update_queue_item(
        self, queue_id: str, queue_item_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新队列项配置"""

        logger.info(f"{queue_id} 更新队列项配置: {queue_item_id}")

        await self.QueueConfig[uuid.UUID(queue_id)].QueueItem.update_item(queue_item_id, data)

    async def del_queue_item(self, queue_id: str, queue_item_id: str) -> None:
        """删除队列项配置"""

        logger.info(f"{queue_id} 删除队列项配置: {queue_item_id}")

        await self.QueueConfig[uuid.UUID(queue_id)].QueueItem.del_item(queue_item_id)

    async def reorder_queue_item(self, queue_id: str, index_list: list[str]) -> None:
        """重新排序队列项"""

        logger.info(f"{queue_id} 重新排序队列项: {index_list}")

        await self.QueueConfig[uuid.UUID(queue_id)].QueueItem.reorder_items(index_list)

    async def get_tools(self) -> Dict[str, Any]:
        """获取工具设置"""

        logger.debug("获取工具设置")

        return await self.ToolsConfig.toDict()

    async def update_tools(self, data: Dict[str, Dict[str, Any]]) -> None:
        """更新工具设置"""

        logger.info("更新工具设置")

        await self.ToolsConfig.set_many(data)

        logger.success("工具设置更新成功")

    async def get_setting(self) -> Dict[str, Any]:
        """获取全局设置"""

        logger.info("获取全局设置")

        return await self.toDict()

    async def update_setting(self, data: Dict[str, Dict[str, Any]]) -> None:
        """更新全局设置"""

        logger.info("更新全局设置")

        await self.set_many(data)

        logger.success("全局设置更新成功")

    async def get_webhook(
        self,
        script_id: Optional[str],
        user_id: Optional[str],
        webhook_id: Optional[str],
    ) -> tuple[list[dict[str, str]], dict[str, Any]]:
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

            await self.Notify_CustomWebhooks[webhook_uid].set_many(data)

        else:
            logger.info(f"更新 webhook 配置: {script_id} - {user_id} - {webhook_id}")

            script_uid = uuid.UUID(script_id)
            user_uid = uuid.UUID(user_id)

            await (
                self.ScriptConfig[script_uid]
                .UserData[user_uid]
                .Notify_CustomWebhooks[webhook_uid]
                .set_many(data)
            )

    async def del_webhook(
        self, script_id: Optional[str], user_id: Optional[str], webhook_id: str
    ) -> None:
        """删除 webhook 配置"""

        webhook_uid = uuid.UUID(webhook_id)

        if script_id is None and user_id is None:
            logger.info(f"删除全局 webhook 配置: {webhook_id}")

            await self.Notify_CustomWebhooks.remove(webhook_uid)

        else:
            logger.info(f"删除 webhook 配置: {script_id} - {user_id} - {webhook_id}")

            script_uid = uuid.UUID(script_id)
            user_uid = uuid.UUID(user_id)

            await (
                self.ScriptConfig[script_uid]
                .UserData[user_uid]
                .Notify_CustomWebhooks.remove(webhook_uid)
            )

    async def reorder_webhook(
        self, script_id: Optional[str], user_id: Optional[str], index_list: list[str]
    ) -> None:
        """重新排序 webhook"""

        if script_id is None and user_id is None:
            logger.info(f"重新排序全局 webhook: {index_list}")

            await self.Notify_CustomWebhooks.setOrder(list(map(uuid.UUID, index_list)))

        else:
            logger.info(f"重新排序 webhook: {script_id} - {user_id} - {index_list}")

            script_uid = uuid.UUID(script_id)
            user_uid = uuid.UUID(user_id)

            await (
                self.ScriptConfig[script_uid]
                .UserData[user_uid]
                .Notify_CustomWebhooks.setOrder(list(map(uuid.UUID, index_list)))
            )

    @property
    def proxy(self) -> Optional[httpx.Proxy]:
        """获取代理设置，返回适用于 httpx 的代理对象"""
        proxy_addr = self.get("Update", "ProxyAddress")
        if not proxy_addr:
            return None

        # 如果地址不包含协议，默认为 http
        if not proxy_addr.startswith(("http://", "https://", "socks5://", "socks4://")):
            proxy_addr = f"http://{proxy_addr}"

        try:
            return httpx.Proxy(proxy_addr)
        except ValueError as e:
            logger.warning(f"代理配置无效: {proxy_addr}, 错误: {e}")
            return None

    async def get_stage_info(
        self,
        type: Literal[
            "User",
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
    ) -> dict[str, Any] | list[dict[str, str]]:
        """获取关卡信息"""

        stage_cache = cast(dict[str, Any], json.loads(self.get("Data", "Stage")))
        if stage_cache != {}:
            task = asyncio.create_task(self.get_stage())
            self.temp_task.append(task)
            task.add_done_callback(
                lambda t: self.temp_task.remove(t) if t in self.temp_task else None
            )
        else:
            refreshed = await self.get_stage()
            stage_cache = cast(
                dict[str, Any], refreshed if refreshed is not None else {}
            )

        if type == "Info":
            today = datetime.now(tz=UTC4).isoweekday()
            res_stage_info: list[dict[str, Any]] = []
            for stage in RESOURCE_STAGE_INFO:
                days = stage.get("days")
                if (
                    isinstance(days, list)
                    and today in days
                    and stage["value"] in RESOURCE_STAGE_DROP_INFO
                ):
                    res_stage_info.append(RESOURCE_STAGE_DROP_INFO[stage["value"]])
            return {
                "Activity": stage_cache.get("Info", []),
                "Resource": res_stage_info,
            }
        elif type == "User":
            data = cast(list[dict[str, str]], stage_cache.get("ALL", []))
            for combox in data:
                combox["label"] = RESOURCE_STAGE_DATE_TEXT.get(
                    combox["value"], combox["label"]
                )
            return data
        elif type == "Today":
            return cast(
                list[dict[str, str]],
                stage_cache.get(datetime.now(tz=UTC4).strftime("%A"), []),
            )
        else:
            return cast(list[dict[str, str]], stage_cache.get(type, []))

    async def get_proxy_overview(self) -> Dict[str, Any]:
        """获取代理情况概览信息"""

        logger.info("获取代理情况概览信息")

        history_index = await self.search_history(
            "DAILY", datetime.now(tz=UTC4).date(), datetime.now(tz=UTC4).date()
        )
        if datetime.now(tz=UTC4).strftime("%Y-%m-%d") not in history_index:
            return {}
        today_records = history_index[datetime.now(tz=UTC4).strftime("%Y-%m-%d")]
        merged_list = await asyncio.gather(
            *(self.merge_statistic_info(v) for v in today_records.values())
        )
        history_data = {
            user: merged
            for user, merged in zip(today_records.keys(), merged_list, strict=False)
        }
        overview: dict[str, dict[str, Any]] = {}
        for user, data in history_data.items():
            index_data = data.get("index", [])
            if index_data:
                last_proxy_date = max(
                    datetime.strptime(_["date"], "%Y-%m-%d %H:%M:%S")
                    for _ in index_data
                ).strftime("%Y-%m-%d %H:%M:%S")
            else:
                last_proxy_date = "暂无代理数据"
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
            async with httpx.AsyncClient(
                proxy=self.proxy, follow_redirects=True
            ) as client:
                response = await client.get(
                    "https://api.maa.plus/MaaAssistantArknights/api/gui/StageActivityV2.json",
                    headers={"If-None-Match": self.get("Data", "StageETag")},
                )

                if response.status_code == 304:
                    logger.info("关卡信息未更新，使用本地缓存的活动关卡信息")
                    await self.set(
                        "Data",
                        "LastStageUpdated",
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    )
                elif response.status_code == 200:
                    logger.success("成功获取远端活动关卡信息")
                    await self.set(
                        "Data",
                        "LastStageUpdated",
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    await self.set(
                        "Data",
                        "StageETag",
                        response.headers.get("ETag")
                        or response.headers.get("etag")
                        or "",
                    )
                    await self.set(
                        "Data",
                        "StageData",
                        json.dumps(
                            response.json()
                            .get("Official", {})
                            .get("sideStoryStage", {}),
                            ensure_ascii=False,
                        ),
                    )
                else:
                    logger.warning(f"无法从MAA服务器获取活动关卡信息:{response.text}")
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as e:
            logger.warning(f"无法从MAA服务器获取活动关卡信息: {e}")

        return json.loads(self.get("Data", "Stage"))

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

    async def get_emulator_devices_combox(
        self, emulator_id: str
    ) -> list[dict[str, str]]:
        """获取模拟器多开实例下拉框信息"""

        logger.info("开始获取模拟器下拉框信息")

        if self.EmulatorConfig[uuid.UUID(emulator_id)].get("Info", "Type") == "general":
            logger.info("通用模拟器不支持扫描多开实例, 返回空列表")
            return []

        data: list[dict[str, str]] = [{"label": "未选择", "value": "-"}]

        from ..emulator_manager import EmulatorManager

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

        if datetime.now() - timedelta(hours=1) < datetime.strptime(
            self.get("Data", "LastNoticeUpdated"), "%Y-%m-%d %H:%M:%S"
        ):
            logger.info("一小时内已进行过一次检查, 直接使用缓存的公告信息")
            return False, json.loads(self.get("Data", "Notice")).get("notice_dict", {})

        logger.info("开始从 AUTO-MAS 服务器获取公告信息")
        try:
            async with httpx.AsyncClient(
                proxy=self.proxy, follow_redirects=True
            ) as client:
                response = await client.get(
                    "https://api.auto-mas.top/file/Server/notice.json",
                    headers={"If-None-Match": self.get("Data", "NoticeETag")},
                )
                if response.status_code == 304:
                    logger.info("公告未更新，使用本地缓存的公告信息")
                    await self.set(
                        "Data",
                        "LastNoticeUpdated",
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    )
                elif response.status_code == 200:
                    logger.info("公告已更新，要求展示公告信息")
                    await self.set(
                        "Data",
                        "LastNoticeUpdated",
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    await self.set(
                        "Data",
                        "NoticeETag",
                        response.headers.get("ETag")
                        or response.headers.get("etag")
                        or "",
                    )
                    await self.set("Data", "IfShowNotice", True)
                    await self.set(
                        "Data",
                        "Notice",
                        json.dumps(response.json(), ensure_ascii=False),
                    )
                else:
                    logger.warning(
                        f"无法从 AUTO-MAS 服务器获取公告信息:{response.text}"
                    )
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as e:
            logger.warning(f"无法从 AUTO-MAS 服务器获取公告信息: {e}")

        return self.get("Data", "IfShowNotice"), json.loads(
            self.get("Data", "Notice")
        ).get("notice_dict", {})

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
            async with httpx.AsyncClient(
                proxy=self.proxy, follow_redirects=True
            ) as client:
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
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as e:
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

    async def save_maa_log(
        self, log_path: Path, logs: list[str], maa_result: str
    ) -> bool:
        """
        保存MAA日志并生成对应统计数据

        Args:
            log_path (Path): 日志文件保存路径
            logs (list): 日志列表
            maa_result (str): MAA任务结果
        Returns:
            bool: 是否存在高资
        """

        return await self._log_service.save_maa_log(log_path, logs, maa_result)

    async def save_maaend_log(
        self, log_path: Path, logs: list[str], maaend_result: str
    ) -> None:
        """
        Save MaaEnd logs and generate basic statistics data.

        Args:
            log_path (Path): Target log file path.
            logs (list[str]): Log lines.
            maaend_result (str): Result label for this run.
        """

        await self._log_service.save_maaend_log(log_path, logs, maaend_result)

    async def save_src_log(
        self, log_path: Path, logs: list[str], src_result: str
    ) -> None:
        """
        保存SRC日志并生成对应统计数据

        Args:
            log_path (Path): 日志文件保存路径
            logs (list): 日志内容列表
            src_result (str): 待保存的日志结果信息
        """

        await self._log_service.save_src_log(log_path, logs, src_result)

    async def save_general_log(
        self, log_path: Path, logs: list[str], general_result: str
    ) -> None:
        """
        保存通用日志并生成对应统计数据

        :param log_path: 日志文件保存路径
        :param logs: 日志内容列表
        :param general_result: 待保存的日志结果信息
        """

        await self._log_service.save_general_log(log_path, logs, general_result)

    async def merge_statistic_info(
        self, statistic_path_list: List[Path]
    ) -> dict[str, Any]:
        """
        合并指定数据统计信息文件

        Args:
            statistic_path_list (List[Path]): 数据统计信息文件列表

        Returns:
            dict: 合并后的数据统计信息
        """

        return await self._log_service.merge_statistic_info(statistic_path_list)

    async def search_history(
        self,
        mode: Literal["DAILY", "WEEKLY", "MONTHLY"],
        start_date: date,
        end_date: date,
    ) -> dict[str, dict[str, list[Path]]]:
        """
        搜索指定时间范围内的历史记录

        Args:
            mode (Literal["DAILY", "WEEKLY", "MONTHLY"]): 合并模式
            start_date (date): 开始日期
            end_date (date): 结束日期
        """

        return await self._log_service.search_history(mode, start_date, end_date)

    async def clean_old_history(self):
        """删除超过用户设定天数的历史记录文件（基于目录日期）"""

        await self._log_service.clean_old_history(self.get("Function", "HistoryRetentionTime"))


Config = AppConfig()
