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
import copy
import httpx
import shutil
import asyncio
import uvicorn
import sqlite3
import truststore
from pathlib import Path
from datetime import datetime, timedelta
from typing import Literal, Optional, Union, Dict, Any, List
import uuid
import json

from app.models.ConfigBase import ConfigBase, JSONValidator
from app.models.config import (
    CLASS_BOOK,
    GameSignAccount,
    GameSignAccountGroup,
    QueueEntry,
    QueueConfig,
    QueueItem,
    Setting,
    TimeSet,
    Tools,
    ToolsConfig,
    Webhook,
)
from app.config import ConfigCollection, config_manager
# 脚本 / 计划 / 模拟器本阶段未迁入；旧方法签名仍引用 legacy 类型
from app.models.config_legacy import (  # noqa: F401
    EmulatorConfig,
    GeneralConfig,
    M9AConfig,
    MaaConfig,
    MaaEndConfig,
    MaaFWConfig,
    MaaPlanConfig,
    OkwwConfig,
    SrcConfig,
)
from app.models.script_api import ScriptRecord, ScriptTypeDescriptor, ScriptUserRecord
from app.utils.constants import (
    UTC4,
    UTC8,
    RESOURCE_STAGE_INFO,
    RESOURCE_STAGE_DROP_INFO,
    TYPE_BOOK,
    RESOURCE_STAGE_DATE_TEXT,
)
from app.utils import get_logger
from .script_types import (
    ScriptRecordCapability,
    apply_script_type_registry_to_global_config,
    build_legacy_fallback_provider_by_script_config,
    build_legacy_fallback_provider_by_type_key,
    build_unavailable_plugin_fallback_provider,
    build_descriptor,
    is_script_config_compatible_with_type_key,
    script_type_registry,
    strip_sub_configs,
)
from .script_config_codec import form_to_storage, storage_to_form

logger = get_logger("配置管理")


class AppConfig:
    VERSION = "v5.4.0-beta.1"

    setting: Setting
    queues: ConfigCollection[QueueEntry]
    tools: Tools

    def __init__(self) -> None:
        logger.info("")
        logger.info("===================================")
        logger.info("AUTO-MAS 后端应用程序")
        logger.info(f"版本号:  {self.VERSION}")
        logger.info(f"工作目录:  {Path.cwd()}")
        logger.info("===================================")

        self.log_path = Path.cwd() / "debug/app.log"
        self.database_path = Path.cwd() / "data/data.db"
        self.config_path = Path.cwd() / "config"
        # 检查目录
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.mkdir(parents=True, exist_ok=True)

        # 新基类配置根（TOML）
        self.setting = Setting.build(file=self.config_path / "setting.toml")
        self.queues = ConfigCollection[QueueEntry].build(
            [QueueEntry],
            file=self.config_path / "queues.toml",
            name="queues",
        )
        self.tools = Tools.build(file=self.config_path / "tools.toml")

        # Git 仓库延迟初始化，避免启动时导入 GitPython
        self._repo: Any = None
        self._repo_initialized = False

        self.server: Optional[uvicorn.Server] = None
        self.power_sign: Literal[
            "NoAction",
            "Shutdown",
            "ShutdownForce",
            "Reboot",
            "Hibernate",
            "Sleep",
            "KillSelf",
            "Logoff",
        ] = "NoAction"
        self.temp_task: List[asyncio.Task] = []
        self._stage_refreshing = False

        self._inject_truststore()

    @staticmethod
    def _inject_truststore() -> None:
        """等效 truststore.inject_into_ssl()，但避免其内部导入 requests (约 460ms)。

        requests 未加载时无需 patch：注入后再导入的 requests 会基于
        已替换的 ssl.SSLContext 创建预加载上下文，效果一致。
        """
        import ssl

        ssl.SSLContext = truststore.SSLContext  # type: ignore[misc]
        try:
            import urllib3.util.ssl_ as urllib3_ssl

            urllib3_ssl.SSLContext = truststore.SSLContext  # type: ignore[assignment]
        except ImportError:
            pass
        requests_adapters = sys.modules.get("requests.adapters")
        if requests_adapters is not None and (
            getattr(requests_adapters, "_preloaded_ssl_context", None) is not None
        ):
            setattr(
                requests_adapters,
                "_preloaded_ssl_context",
                truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
            )

    def _get_repo(self) -> Any:
        """惰性初始化 Git 仓库，避免启动时导入 GitPython。"""
        if not self._repo_initialized:
            self._repo_initialized = True
            if (Path.cwd() / "environment/git/bin/git.exe").exists():
                os.environ["GIT_PYTHON_GIT_EXECUTABLE"] = str(
                    Path.cwd() / "environment/git/bin/git.exe"
                )
            try:
                from git import Repo

                self._repo = Repo(Path.cwd())
            except Exception as e:
                logger.warning(f"Git仓库初始化失败: {e}")
                self._repo = None
        return self._repo

    async def init_config(self) -> None:
        """初始化配置管理"""

        await self.check_data()

        # 激活新基类配置根（Setting / 调度队列 / 工具）
        # 现有 TOML 可能仍是旧 PascalCase Wire，字段对不齐时以默认值热化并记日志
        from app.config.errors import ConfigAggregateError

        for label, node in (
            ("setting", self.setting),
            ("queues", self.queues),
            ("tools", self.tools),
        ):
            try:
                await node.activate()
            except ConfigAggregateError as exc:
                logger.warning(f"{label} 配置激活有聚合错误（待 JSON/TOML 迁移）: {exc}")

        # 游戏签到：如果不是今天签到的，清除计划时间以便重新计算
        if self.tools.game_sign.last_sign_date != datetime.now().strftime("%Y-%m-%d"):
            self.tools.game_sign.scheduled_time = ""
            await self.tools.commit()

        self.loop = asyncio.get_running_loop()

        logger.info("程序初始化完成")

    async def check_data(self) -> None:
        """检查用户数据文件并处理数据文件版本更新"""

        # 生成主数据库
        if not self.database_path.exists():
            db = sqlite3.connect(self.database_path)
            cur = db.cursor()
            cur.execute("CREATE TABLE version(v text)")
            cur.execute("INSERT INTO version VALUES(?)", ("v1.11",))
            db.commit()
            cur.close()
            db.close()

        # 数据文件版本更新
        db = sqlite3.connect(self.database_path)
        cur = db.cursor()
        cur.execute("SELECT * FROM version WHERE True")
        version = cur.fetchall()

        if version[0][0] != "v1.11":
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
                            await self.update_script(str(uid), maa_config)

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
                                    await self.update_user(str(uid), str(user_uid), user_config)

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
                            await self.update_script(str(uid), general_config)

                            for user in (GeneralConfig / "SubData").iterdir():
                                if user.is_dir() and (user / "config.json").exists():
                                    user_config = json.loads(
                                        (user / "config.json").read_text(
                                            encoding="utf-8"
                                        )
                                    )

                                    user_uid, uc = await self.add_user(str(uid))
                                    await self.update_user(str(uid), str(user_uid), user_config)

                                    if (user / "ConfigFiles").exists():
                                        (Path.cwd() / f"data/{uid}/{user_uid}").mkdir(
                                            parents=True, exist_ok=True
                                        )
                                        shutil.move(
                                            user / "ConfigFiles",
                                            Path.cwd()
                                            / f"data/{uid}/{user_uid}/ConfigFile",
                                        )

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
            # v1.9-->v1.10
            if version[0][0] == "v1.9" or if_streaming:
                logger.info(
                    "数据文件版本更新: v1.9-->v1.10",
                )
                if_streaming = True

                if (Path.cwd() / "config/Config.json").exists():
                    data = json.loads(
                        (Path.cwd() / "config/Config.json").read_text(encoding="utf-8")
                    )
                    data["Data"]["LastStageUpdated"] = ""
                    data["Data"]["Stage"] = "{ }"
                    data["Function"]["IfBlockAd"] = data["Function"].get(
                        "IfSkipMumuSplashAds", False
                    )
                    (Path.cwd() / "config/Config.json").write_text(
                        json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8"
                    )

                cur.execute("DELETE FROM version WHERE v = ?", ("v1.9",))
                cur.execute("INSERT INTO version VALUES(?)", ("v1.10",))
                db.commit()
            # v1.10-->v1.11
            if version[0][0] == "v1.10" or if_streaming:
                logger.info(
                    "数据文件版本更新: v1.10-->v1.11",
                )
                if_streaming = True

                if (Path.cwd() / "config/ScriptConfig.json").exists():
                    data = (Path.cwd() / "config/ScriptConfig.json").read_text(
                        encoding="utf-8"
                    )
                    data.replace("IfWakeUp", "IfStartUp")
                    data.replace("IfAutoRoguelike", "IfRoguelike")
                    data.replace("IfBase", "IfInfrast")
                    data.replace("IfCombat", "IfFight")
                    data.replace("IfMission", "IfAward")
                    data.replace("IfRecruiting", "IfRecruit")
                    (Path.cwd() / "config/ScriptConfig.json").write_text(
                        data, encoding="utf-8"
                    )

                cur.execute("DELETE FROM version WHERE v = ?", ("v1.10",))
                cur.execute("INSERT INTO version VALUES(?)", ("v1.11",))
                db.commit()

            cur.close()
            db.close()
            logger.success("数据文件版本更新完成")

    async def get_git_version(self) -> tuple[bool, str, str]:
        """获取Git版本信息，如果Git不可用则返回默认值"""

        def _get_git_info():

            repo = self._get_repo()
            if repo is None:
                logger.warning("Git仓库不可用，返回默认版本信息")
                return False, "unknown", "unknown"

            # 获取当前 commit
            current_commit = repo.head.commit
            # 获取 commit 哈希
            commit_hash = current_commit.hexsha
            # 获取 commit 时间
            commit_time = datetime.fromtimestamp(current_commit.committed_date)

            # 检查是否为最新 commit
            try:
                # 获取远程分支的最新 commit
                origin = repo.remotes.origin
                origin.fetch()  # 拉取最新信息
                remote_commit = repo.commit(
                    f"origin/{repo.active_branch.name}"
                )
                is_latest = bool(current_commit.hexsha == remote_commit.hexsha)
            except Exception as e:
                logger.warning(f"无法获取远程分支信息: {e}")
                is_latest = False

            return is_latest, commit_hash, commit_time.strftime("%Y-%m-%d %H:%M:%S")

        # 在线程池中执行 Git 操作
        is_latest, commit_hash, commit_time = await self.loop.run_in_executor(
            None, _get_git_info
        )
        return is_latest, commit_hash, commit_time

    @staticmethod
    def _is_configbase_class(config_class: type[Any]) -> bool:
        return isinstance(config_class, type) and issubclass(config_class, ConfigBase)

    async def _build_provider_default_payload(self, config_class: type[Any]) -> dict[str, Any]:
        if self._is_configbase_class(config_class):
            return await config_class().toDict()
        return config_class().model_dump(mode="json")

    @staticmethod
    def _read_plugin_payload(raw: Any) -> dict[str, Any]:
        if raw is None:
            return {}
        if isinstance(raw, str):
            text = raw.strip()
            if not text or text == "{}":
                return {}
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise TypeError("PluginData.Config 必须是 JSON 对象")
            return parsed
        if isinstance(raw, dict):
            return copy.deepcopy(raw)
        raise TypeError(f"PluginData.Config 必须是 dict 或 JSON 字符串: {type(raw).__name__}")

    @staticmethod
    def _merge_plugin_form_payload(
        base: dict[str, Any],
        override: dict[str, Any],
    ) -> dict[str, Any]:
        merged = copy.deepcopy(base or {})
        for key, value in (override or {}).items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = AppConfig._merge_plugin_form_payload(merged[key], value)
            else:
                merged[key] = copy.deepcopy(value)
        return merged

    @staticmethod
    def _strip_virtual_fields_from_plugin_form_payload(
        config_class: type[Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        cleaned = copy.deepcopy(payload or {})
        field_groups = getattr(config_class, "_field_groups", ())
        for group in field_groups:
            group_data = cleaned.get(group.key)
            if not isinstance(group_data, dict):
                continue
            for field in group.fields:
                if field.virtual_handler is not None:
                    group_data.pop(field.name, None)
        return cleaned

    @staticmethod
    def _script_record_name(
        provider: Any,
        config_data: dict[str, Any],
        fallback: str | None = None,
    ) -> str:
        script_name = config_data.get("script_name")
        if isinstance(script_name, str) and script_name.strip():
            return script_name.strip()

        info = config_data.get("Info")
        if isinstance(info, dict) and isinstance(info.get("Name"), str):
            info_name = info["Name"].strip()
            if info_name:
                return info_name

        if isinstance(fallback, str) and fallback.strip():
            return fallback.strip()
        return provider.display_name

    @staticmethod
    def _normalize_plugin_script_form_payload(
        provider: Any,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        normalizer = provider.metadata.get("normalize_script_form")
        if not callable(normalizer):
            return payload

        normalized_payload = normalizer(copy.deepcopy(payload))
        if not isinstance(normalized_payload, dict):
            raise TypeError("插件脚本配置标准化器必须返回 dict")
        return normalized_payload

    @staticmethod
    def _user_record_name(config_data: dict[str, Any], fallback: str) -> str:
        user_name = config_data.get("user_name")
        if isinstance(user_name, str) and user_name.strip():
            return user_name.strip()

        info = config_data.get("Info")
        if isinstance(info, dict) and isinstance(info.get("Name"), str):
            info_name = info["Name"].strip()
            if info_name:
                return info_name

        return fallback

    def _normalize_configbase_payload_for_form(
        self,
        config_class: type[Any],
        data: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = copy.deepcopy(data or {})
        if not self._is_configbase_class(config_class):
            return normalized

        config = config_class()
        for group, items in config._config_item_index.items():
            group_data = normalized.get(group)
            if not isinstance(group_data, dict):
                continue
            for name, item in items.items():
                if not isinstance(item.validator, JSONValidator):
                    continue
                raw_value = group_data.get(name)
                if not isinstance(raw_value, str):
                    continue
                try:
                    group_data[name] = json.loads(raw_value)
                except json.JSONDecodeError:
                    group_data[name] = {} if item.validator.type is dict else []

        return normalized

    def _normalize_configbase_payload_for_storage(
        self,
        config_class: type[Any],
        data: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = copy.deepcopy(data or {})
        normalized.pop("SubConfigsInfo", None)
        if not self._is_configbase_class(config_class):
            return normalized

        config = config_class()
        for group, items in config._config_item_index.items():
            group_data = normalized.get(group)
            if not isinstance(group_data, dict):
                continue
            for name, item in items.items():
                if not isinstance(item.validator, JSONValidator) or name not in group_data:
                    continue
                value = group_data[name]
                if isinstance(value, str):
                    continue
                if value is None:
                    value = {} if item.validator.type is dict else []
                group_data[name] = json.dumps(value, ensure_ascii=False)

        return normalized

    def _is_general_script_config(self, script_config: ConfigBase) -> bool:
        """判断脚本是否属于通用脚本类型。"""

        return is_script_config_compatible_with_type_key(script_config, "General")

    @staticmethod
    def _is_okww_legacy_script_config(script_config: ConfigBase) -> bool:
        """Return whether the record is an old host-owned OkwwConfig."""

        from app.models.config import OkwwConfig

        return isinstance(script_config, OkwwConfig)

    @staticmethod
    def _pick_config_group(
        data: dict[str, Any],
        group: str,
        fields: tuple[str, ...],
    ) -> dict[str, Any]:
        source = data.get(group)
        if not isinstance(source, dict):
            return {}
        return {field: source[field] for field in fields if field in source}

    def _okww_legacy_script_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "Info": self._pick_config_group(data, "Info", ("Name", "RootPath")),
            "Game": self._pick_config_group(
                data,
                "Game",
                ("Enabled", "Path", "Arguments", "WaitTime"),
            ),
            "Run": self._pick_config_group(
                data,
                "Run",
                ("ProxyTimesLimit", "RunTimesLimit", "RunTimeLimit"),
            ),
        }

    def _okww_legacy_user_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        notify = self._pick_config_group(
            data,
            "Notify",
            (
                "Enabled",
                "IfSendStatistic",
                "IfSendMail",
                "ToAddress",
                "IfServerChan",
                "ServerChanKey",
            ),
        )
        custom_webhooks = (
            data.get("SubConfigsInfo", {})
            if isinstance(data.get("SubConfigsInfo"), dict)
            else {}
        ).get("Notify_CustomWebhooks")
        if isinstance(custom_webhooks, dict):
            notify["CustomWebhooks"] = json.dumps(custom_webhooks, ensure_ascii=False)

        return {
            "Info": self._pick_config_group(
                data,
                "Info",
                (
                    "Name",
                    "Status",
                    "Id",
                    "Password",
                    "Resource",
                    "RemainedDay",
                    "Mode",
                    "IfScriptBeforeTask",
                    "ScriptBeforeTask",
                    "IfScriptAfterTask",
                    "ScriptAfterTask",
                    "Notes",
                ),
            ),
            "Task": self._pick_config_group(data, "Task", ("TaskIndex",)),
            "Data": self._pick_config_group(
                data,
                "Data",
                ("LastProxyDate", "ProxyTimes", "LastProxyStatus", "LastTaskIndex"),
            ),
            "Notify": notify,
        }

    async def _read_general_script_payload(
        self,
        script_uid: uuid.UUID,
        *,
        if_decrypt: bool = False,
    ) -> dict[str, Any]:
        """读取通用脚本的结构化配置数据。"""

        from app.models.plugin_script_config import PluginScriptConfig

        script_config = self.ScriptConfig[script_uid]
        if not self._is_general_script_config(script_config):
            raise TypeError(f"脚本 {script_uid} 不是通用脚本配置")

        if isinstance(script_config, PluginScriptConfig):
            provider = self._resolve_record_provider(script_config)
            raw = script_config.get("PluginData", "Config")
            return await storage_to_form(provider, raw, "script")

        return strip_sub_configs(await script_config.toDict(if_decrypt=if_decrypt))

    async def _write_general_script_payload(
        self,
        script_uid: uuid.UUID,
        data: dict[str, Any],
    ) -> None:
        """写回通用脚本的结构化配置数据。"""

        from app.models.plugin_script_config import PluginScriptConfig

        script_config = self.ScriptConfig[script_uid]
        if not self._is_general_script_config(script_config):
            raise TypeError(f"脚本 {script_uid} 不是通用脚本配置")

        if isinstance(script_config, PluginScriptConfig):
            provider = self._resolve_record_provider(script_config)
            payload = await form_to_storage(provider, data, "script")
            await script_config.set(
                "PluginData",
                "Config",
                json.dumps(payload, ensure_ascii=False),
            )
            form_payload = await storage_to_form(provider, payload, "script")
            await script_config.set(
                "Info",
                "Name",
                self._script_record_name(provider, form_payload, script_config.get("Info", "Name")),
            )
            return

        await script_config.load(data)

    async def _migrate_general_scripts_to_plugin_storage(self) -> None:
        """把旧的 GeneralConfig 实例迁移到插件脚本容器。"""

        from app.models.plugin_script_config import PluginScriptConfig, PluginUserConfig

        migrate_list = [
            script_uid
            for script_uid, script_config in self.ScriptConfig.items()
            if self._is_general_script_config(script_config)
            and not isinstance(script_config, PluginScriptConfig)
        ]
        if not migrate_list:
            return

        logger.info(f"检测到 {len(migrate_list)} 个旧通用脚本，开始迁移到插件脚本容器")

        for script_uid in migrate_list:
            legacy_script = self.ScriptConfig[script_uid]
            script_payload = strip_sub_configs(
                await legacy_script.toDict(if_decrypt=False)
            )

            plugin_script = PluginScriptConfig()
            await plugin_script.set("Meta", "PluginTypeKey", "General")
            await plugin_script.set("Info", "Name", legacy_script.get("Info", "Name"))
            await plugin_script.set(
                "PluginData",
                "Config",
                json.dumps(script_payload, ensure_ascii=False),
            )

            for user_uid, legacy_user in legacy_script.UserData.items():
                user_payload = strip_sub_configs(await legacy_user.toDict(if_decrypt=False))
                plugin_user = PluginUserConfig()
                await plugin_user.set("Meta", "PluginTypeKey", "General")
                await plugin_user.set("Info", "Name", legacy_user.get("Info", "Name"))
                await plugin_user.set(
                    "PluginData",
                    "Config",
                    json.dumps(user_payload, ensure_ascii=False),
                )
                plugin_script.UserData.order.append(user_uid)
                plugin_script.UserData.data[user_uid] = plugin_user

            if self.ScriptConfig.file is not None:
                await plugin_script.add_save_method(self.ScriptConfig.save)
            for save_method in self.ScriptConfig._save_methods:
                await plugin_script.add_save_method(save_method)

            self.ScriptConfig.data[script_uid] = plugin_script

        await self.ScriptConfig.save()
        logger.success("旧通用脚本已迁移到插件脚本容器")

    async def _migrate_okww_scripts_to_plugin_storage(self) -> None:
        """Move old OkwwConfig records into the plugin storage container.

        This migration is intentionally narrow and temporary: it upgrades old
        host-owned Okww records to plugin-owned records so the legacy Okww
        provider fallback can be removed after the migration window.
        """

        from app.models.plugin_script_config import PluginScriptConfig, PluginUserConfig

        migrate_list = [
            script_uid
            for script_uid, script_config in self.ScriptConfig.items()
            if self._is_okww_legacy_script_config(script_config)
            and not isinstance(script_config, PluginScriptConfig)
        ]
        if not migrate_list:
            return

        logger.info(f"检测到 {len(migrate_list)} 个旧 Okww 脚本，开始迁移到插件脚本容器")

        # v5.3.1 简洁模式（Info.Mode=="简洁"，当时的默认值）把 OK-WW 任务配置
        # 共享存放在 data/<script>/Default/ConfigFile；插件版按用户独立存储。
        # 迁移时为每个缺失配置的用户复制一份副本，全部落盘成功后再清理共享目录。
        legacy_default_dirs: list[Path] = []

        for script_uid in migrate_list:
            legacy_script = self.ScriptConfig[script_uid]
            script_payload = self._okww_legacy_script_payload(
                await legacy_script.toDict(if_decrypt=False)
            )

            plugin_script = PluginScriptConfig()
            await plugin_script.set("Meta", "PluginTypeKey", "Okww")
            await plugin_script.set("Info", "Name", legacy_script.get("Info", "Name"))
            await plugin_script.set(
                "PluginData",
                "Config",
                json.dumps(script_payload, ensure_ascii=False),
            )

            default_config_dir = (
                Path.cwd() / "data" / str(script_uid) / "Default" / "ConfigFile"
            )

            for user_uid, legacy_user in legacy_script.UserData.items():
                user_payload = self._okww_legacy_user_payload(
                    await legacy_user.toDict(if_decrypt=False)
                )
                plugin_user = PluginUserConfig()
                await plugin_user.set("Meta", "PluginTypeKey", "Okww")
                await plugin_user.set("Info", "Name", legacy_user.get("Info", "Name"))
                await plugin_user.set(
                    "PluginData",
                    "Config",
                    json.dumps(user_payload, ensure_ascii=False),
                )
                plugin_script.UserData.order.append(user_uid)
                plugin_script.UserData.data[user_uid] = plugin_user

                user_config_dir = (
                    Path.cwd() / "data" / str(script_uid) / str(user_uid) / "ConfigFile"
                )
                if default_config_dir.is_dir() and not user_config_dir.is_dir():
                    shutil.copytree(default_config_dir, user_config_dir)
                    logger.info(
                        f"已将简洁模式共享配置复制给用户 {user_uid}: {user_config_dir}"
                    )

            if default_config_dir.is_dir():
                legacy_default_dirs.append(default_config_dir)

            if self.ScriptConfig.file is not None:
                await plugin_script.add_save_method(self.ScriptConfig.save)
            for save_method in self.ScriptConfig._save_methods:
                await plugin_script.add_save_method(save_method)

            self.ScriptConfig.data[script_uid] = plugin_script

        await self.ScriptConfig.save()
        # save 成功后才清理共享目录：迁移中途失败时保留原数据，下次启动重试。
        for default_config_dir in legacy_default_dirs:
            shutil.rmtree(default_config_dir, ignore_errors=True)
        logger.success("旧 Okww 脚本已迁移到插件脚本容器")

    async def add_script(
        self,
        script: str,
        script_id: str | None = None,
    ) -> tuple[uuid.UUID, ConfigBase]:
        """添加脚本配置。"""

        logger.info(f"添加脚本配置: {script}, 从 {script_id} 复制")

        provider = script_type_registry.get(script)
        self._require_provider_available(provider, "新增脚本配置")

        if not provider.is_builtin:
            from app.models.plugin_script_config import PluginScriptConfig

            new_uid, new_config = await self.ScriptConfig.add(PluginScriptConfig)
            await new_config.set("Meta", "PluginTypeKey", provider.type_key)

            defaults = await form_to_storage(provider, {}, "script")
            default_form = await storage_to_form(provider, defaults, "script")
            script_name = self._script_record_name(provider, default_form)
            await new_config.set("Info", "Name", script_name)
            await new_config.set(
                "PluginData", "Config",
                json.dumps(defaults, ensure_ascii=False),
            )

            if script_id is not None:
                source_uid = uuid.UUID(script_id)
                source_config = self.ScriptConfig[source_uid]
                source_provider = self._resolve_record_provider(source_config)
                if source_provider.type_key != provider.type_key:
                    raise TypeError(f"脚本配置类型不匹配: {script_id} {script}")
                if isinstance(source_config, PluginScriptConfig):
                    source_payload = self._read_plugin_payload(
                        source_config.get("PluginData", "Config")
                    )
                else:
                    source_payload = await source_config.toDict(
                        if_decrypt=False,
                        regenerate_uuids=True,
                    )
                storage_payload = await form_to_storage(provider, source_payload, "script")
                await new_config.set(
                    "PluginData", "Config",
                    json.dumps(storage_payload, ensure_ascii=False),
                )
                await new_config.set("Info", "Name", source_config.get("Info", "Name"))

            return new_uid, new_config

        if script_id is None:
            return await self.ScriptConfig.add(provider.script_config_class)

        script_uid = uuid.UUID(script_id)
        source_provider = script_type_registry.get_by_script_config(
            self.ScriptConfig[script_uid]
        )
        if source_provider.type_key != provider.type_key:
            raise TypeError(f"脚本配置类型不匹配: {script_id} {script}")

        new_uid, new_config = await self.ScriptConfig.add(provider.script_config_class)
        await new_config.load(
            await self.ScriptConfig[script_uid].toDict(regenerate_uuids=True)
        )

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

    async def get_script(self, script_id: str | None) -> tuple[list, dict]:
        """获取脚本配置。"""

        logger.info(f"获取脚本配置: {script_id}")

        if script_id is None:
            data = await self.ScriptConfig.toDict()
        else:
            data = await self.ScriptConfig.get(uuid.UUID(script_id))

        index = data.pop("instances", [])
        return list(index), data

    async def update_script(
        self, script_id: str, data: Dict[str, Any]
    ) -> None:
        """更新脚本配置"""

        logger.info(f"更新脚本配置: {script_id}")

        uid = uuid.UUID(script_id)
        config = self.ScriptConfig[uid]

        if config.is_locked:
            raise RuntimeError(f"脚本 {script_id} 正在运行, 无法更新配置项")

        from app.models.plugin_script_config import PluginScriptConfig

        if isinstance(config, PluginScriptConfig):
            provider = self._resolve_record_provider(config)
            self._require_provider_available(provider, "更新脚本配置")
            update_data = copy.deepcopy(data or {})
            plugin_data = update_data.pop("PluginData", None)
            payload_data: dict[str, Any] | None = None
            if isinstance(plugin_data, dict) and "Config" in plugin_data:
                raw = plugin_data["Config"]
                payload_data = self._read_plugin_payload(raw)
            elif update_data:
                payload_data = update_data

            if payload_data is not None:
                current_form_payload = await storage_to_form(
                    provider,
                    config.get("PluginData", "Config"),
                    "script",
                )
                current_form_payload = self._strip_virtual_fields_from_plugin_form_payload(
                    provider.script_config_class,
                    current_form_payload,
                )
                payload_data = self._merge_plugin_form_payload(
                    current_form_payload,
                    payload_data,
                )
                payload_data = self._normalize_plugin_script_form_payload(
                    provider,
                    payload_data,
                )
                payload_data = self._strip_virtual_fields_from_plugin_form_payload(
                    provider.script_config_class,
                    payload_data,
                )
                payload_data = await form_to_storage(provider, payload_data, "script")
                await config.set(
                    "PluginData", "Config",
                    json.dumps(payload_data, ensure_ascii=False),
                )

            raw_config = config.get("PluginData", "Config")
            form_payload = await storage_to_form(provider, raw_config, "script")
            await config.set(
                "Info",
                "Name",
                self._script_record_name(provider, form_payload, config.get("Info", "Name")),
            )
            return

        for group, items in data.items():
            for name, value in items.items():
                await self.ScriptConfig[uid].set(group, name, value)

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
        if not self._is_general_script_config(self.ScriptConfig[uid]):
            logger.error(f"{script_id} 不是通用脚本配置")
            raise TypeError(f"脚本 {script_id} 不是通用脚本配置")
        if not Path(file_path).exists():
            logger.error(f"文件不存在: {file_path}")
            raise FileNotFoundError(f"文件不存在: {file_path}")

        data = json.loads(file_path.read_text(encoding="utf-8"))
        await self._write_general_script_payload(uid, data)

        logger.success(f"{script_id} 配置加载成功")

    async def export_script_to_file(self, script_id: str, jsonFile: str):
        """导出脚本配置到文件"""

        logger.info(f"导出配置到文件: {script_id} - {jsonFile}")

        uid = uuid.UUID(script_id)
        file_path = Path(jsonFile)

        if uid not in self.ScriptConfig:
            logger.error(f"{script_id} 不存在")
            raise KeyError(f"脚本 {script_id} 不存在")
        if not self._is_general_script_config(self.ScriptConfig[uid]):
            logger.error(f"{script_id} 不是通用脚本配置")
            raise TypeError(f"脚本 {script_id} 不是通用脚本配置")

        temp = await self._read_general_script_payload(uid, if_decrypt=False)
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
        if not self._is_general_script_config(self.ScriptConfig[uid]):
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

        await self._write_general_script_payload(uid, data)

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
        if not self._is_general_script_config(self.ScriptConfig[uid]):
            logger.error(f"{script_id} 不是通用脚本配置")
            raise TypeError(f"脚本 {script_id} 不是通用脚本配置")

        temp = await self._read_general_script_payload(uid, if_decrypt=False)
        temp = await self.remove_privacy_info(temp, config_name)

        files = {
            "file": (
                f"{config_name}&&{int(datetime.now(tz=UTC8).timestamp() * 1000)}.json",
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

    async def remove_privacy_info(self, config: dict, name: str) -> dict:
        """移除配置中可能存在的隐私信息"""

        config["Info"]["Name"] = name
        for path in ["ScriptPath", "ConfigPath", "LogPath", "TrackProcessExe"]:
            if Path(config["Script"][path]).is_relative_to(
                Path(config["Info"]["RootPath"])
            ):
                config["Script"][path] = str(
                    Path(r"C:/脚本根目录")
                    / Path(config["Script"][path]).relative_to(
                        Path(config["Info"]["RootPath"])
                    )
                )
            if sys.platform == "win32" and Path(config["Script"][path]).is_relative_to(
                Path(os.environ["APPDATA"])
            ):
                config["Script"][
                    path
                ] = f"%APPDATA%/{Path(config['Script'][path]).relative_to(Path(os.environ['APPDATA']))}"
        config["Info"]["RootPath"] = str(Path(r"C:/脚本根目录"))

        return config

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

    async def add_user(self, script_id: str) -> tuple[uuid.UUID, ConfigBase]:
        """添加用户配置。"""

        logger.info(f"{script_id} 添加用户配置")

        script_config = self.ScriptConfig[uuid.UUID(script_id)]
        provider = self._resolve_record_provider(script_config)
        capability = await self.get_script_record_capability(script_id)
        if not capability.available:
            reason = capability.unavailable_reason or "脚本当前不可用"
            raise RuntimeError(f"无法新增用户配置: {reason}")

        from app.models.plugin_script_config import PluginScriptConfig, PluginUserConfig

        if isinstance(script_config, PluginScriptConfig):
            self._require_provider_available(provider, "新增用户配置")
            new_uid, new_user = await script_config.UserData.add(PluginUserConfig)
            await new_user.set("Meta", "PluginTypeKey", provider.type_key)
            defaults = await form_to_storage(provider, {}, "user")
            default_form = await storage_to_form(provider, defaults, "user")
            await new_user.set(
                "Info",
                "Name",
                self._user_record_name(default_form, "新用户"),
            )
            await new_user.set(
                "PluginData", "Config",
                json.dumps(defaults, ensure_ascii=False),
            )
            return new_uid, new_user

        return await script_config.UserData.add(provider.user_config_class)

    async def update_user(
        self, script_id: str, user_id: str, data: Dict[str, Any]
    ) -> None:
        """更新用户配置"""

        logger.info(f"{script_id} 更新用户配置: {user_id}")

        script_uid = uuid.UUID(script_id)
        user_uid = uuid.UUID(user_id)

        from app.models.plugin_script_config import PluginUserConfig

        user_config = self.ScriptConfig[script_uid].UserData[user_uid]
        if isinstance(user_config, PluginUserConfig):
            provider = self._resolve_record_provider(self.ScriptConfig[script_uid])
            self._require_provider_available(provider, "更新用户配置")
            update_data = copy.deepcopy(data or {})
            plugin_data = update_data.pop("PluginData", None)
            payload_data: dict[str, Any] | None = None
            if isinstance(plugin_data, dict) and "Config" in plugin_data:
                raw = plugin_data["Config"]
                payload_data = self._read_plugin_payload(raw)
            elif update_data:
                payload_data = update_data
            if payload_data is not None:
                current_form_payload = await storage_to_form(
                    provider,
                    user_config.get("PluginData", "Config"),
                    "user",
                )
                current_form_payload = self._strip_virtual_fields_from_plugin_form_payload(
                    provider.user_config_class,
                    current_form_payload,
                )
                payload_data = self._merge_plugin_form_payload(
                    current_form_payload,
                    payload_data,
                )
                payload_data = self._strip_virtual_fields_from_plugin_form_payload(
                    provider.user_config_class,
                    payload_data,
                )
                payload_data = await form_to_storage(provider, payload_data, "user")
                await user_config.set(
                    "PluginData", "Config",
                    json.dumps(payload_data, ensure_ascii=False),
                )
            raw_config = user_config.get("PluginData", "Config")
            form_payload = await storage_to_form(provider, raw_config, "user")
            await user_config.set(
                "Info",
                "Name",
                self._user_record_name(form_payload, user_config.get("Info", "Name")),
            )
            return

        for group, items in data.items():
            for name, value in items.items():
                await (
                    self.ScriptConfig[script_uid]
                    .UserData[user_uid]
                    .set(group, name, value)
                )

    async def import_script_config_file(
        self, script_id: str, user_id: Optional[str]
    ) -> None:
        """从目标脚本目录导入配置文件"""

        logger.info(f"{script_id} - {user_id or 'Default'} 导入脚本配置文件")

        script_config = self.ScriptConfig[uuid.UUID(script_id)]
        if not isinstance(script_config, MaaEndConfig):
            raise TypeError("当前脚本类型暂不支持导入配置文件")

        source_config_dir = Path(script_config.get("Info", "Path")) / "config"
        if not (source_config_dir / "mxu-MaaEnd.json").exists():
            raise FileNotFoundError(
                "MaaEnd 配置文件不存在, 请检查 MaaEnd 路径设置或先启动 MaaEnd 完成配置文件生成"
            )

        config_owner = user_id or "Default"
        target_config_dir = Path.cwd() / f"data/{script_id}/{config_owner}/ConfigFile"
        shutil.rmtree(target_config_dir, ignore_errors=True)
        target_config_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_config_dir, target_config_dir, dirs_exist_ok=True)

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

        script_uid = uuid.UUID(script_id)

        await self.ScriptConfig[script_uid].UserData.setOrder(
            list(map(uuid.UUID, index_list))
        )

    async def get_script_type_descriptors(self) -> list[ScriptTypeDescriptor]:
        """获取脚本类型描述列表。"""

        return [
            ScriptTypeDescriptor(**build_descriptor(provider))
            for provider in script_type_registry.list()
        ]

    @staticmethod
    def _provider_is_available(provider: Any) -> bool:
        """判断脚本类型 provider 当前是否可操作。"""

        return provider.metadata.get("available", True) is not False

    @classmethod
    def _require_provider_available(cls, provider: Any, action: str) -> None:
        """阻止对未启用脚本类型执行写操作。"""

        if cls._provider_is_available(provider):
            return
        raise RuntimeError(f"脚本类型 {provider.type_key} 当前未启用，无法{action}")

    def _resolve_plugin_record_provider(self, script_config: Any):
        """解析插件脚本容器对应的 provider，缺失时回退到离线描述。"""

        type_key = str(script_config.get("Meta", "PluginTypeKey") or "").strip()
        if not type_key:
            raise KeyError("插件脚本记录缺少 Meta.PluginTypeKey")
        try:
            return script_type_registry.get(type_key)
        except KeyError:
            provider = build_legacy_fallback_provider_by_type_key(type_key)
            if provider is None:
                provider = build_unavailable_plugin_fallback_provider(type_key)
            script_name = str(script_config.get("Info", "Name") or "").strip()
            label = script_name or type_key
            logger.warning(
                "插件脚本类型 provider 未启用，使用离线回退描述: "
                f"script_name={label}, type_key={type_key}"
            )
            return provider

    def _resolve_record_provider(self, script_config: ConfigBase):
        """解析脚本记录展示所需的 provider，缺失时回退到离线描述。"""

        from app.models.plugin_script_config import PluginScriptConfig

        if isinstance(script_config, PluginScriptConfig):
            return self._resolve_plugin_record_provider(script_config)

        try:
            return script_type_registry.get_by_script_config(script_config)
        except KeyError as exc:
            provider = build_legacy_fallback_provider_by_script_config(script_config)
            if provider is None:
                raise exc
            logger.warning(
                f"脚本类型 provider 未启用，使用离线回退描述: {type(script_config).__name__}"
            )
            return provider

    async def get_script_record_capability(
        self,
        script_id: str | uuid.UUID,
    ) -> ScriptRecordCapability:
        """解析指定脚本记录当前可执行的能力。"""

        from app.models.plugin_script_config import PluginScriptConfig

        script_uid = (
            script_id if isinstance(script_id, uuid.UUID) else uuid.UUID(script_id)
        )
        script_config = self.ScriptConfig[script_uid]
        provider = self._resolve_record_provider(script_config)
        if isinstance(script_config, PluginScriptConfig):
            raw = script_config.get("PluginData", "Config")
            config_data = await storage_to_form(provider, raw, "script")
        else:
            config_data = await storage_to_form(
                provider,
                await script_config.toDict(),
                "script",
            )
        return provider.resolve_record_capability(config_data)

    @staticmethod
    def _find_schema_group(schema: dict[str, Any], group_key: str) -> dict[str, Any] | None:
        from app.plugins.schema_utils import find_schema_group
        return find_schema_group(schema, group_key)

    @classmethod
    def _find_schema_field(cls, schema: dict[str, Any], field_key: str) -> dict[str, Any] | None:
        from app.plugins.schema_utils import find_schema_field
        return find_schema_field(schema, field_key)

    @classmethod
    def _set_schema_group_label(
        cls,
        schema: dict[str, Any],
        group_key: str,
        label: str,
    ) -> None:
        from app.plugins.schema_utils import set_schema_group_label
        set_schema_group_label(schema, group_key, label)

    @classmethod
    def _set_schema_field_label(
        cls,
        schema: dict[str, Any],
        field_key: str,
        label: str,
    ) -> None:
        from app.plugins.schema_utils import set_schema_field_label
        set_schema_field_label(schema, field_key, label)

    @classmethod
    def _set_schema_field_options(
        cls,
        schema: dict[str, Any],
        field_key: str,
        options: list[dict[str, Any]],
        *,
        allow_custom: bool | None = None,
    ) -> None:
        from app.plugins.schema_utils import set_schema_field_options
        set_schema_field_options(schema, field_key, options, allow_custom=allow_custom)

    @classmethod
    def _set_schema_field_state(
        cls,
        schema: dict[str, Any],
        field_key: str,
        *,
        readonly: bool | None = None,
        help_text: str | None = None,
        placeholder: str | None = None,
        rows: int | None = None,
        size: str | None = None,
    ) -> None:
        from app.plugins.schema_utils import set_schema_field_state
        set_schema_field_state(
            schema, field_key,
            readonly=readonly, help_text=help_text,
            placeholder=placeholder, rows=rows, size=size,
        )

    @classmethod
    def _append_schema_field(
        cls,
        schema: dict[str, Any],
        group_key: str,
        field_schema: dict[str, Any],
    ) -> None:
        from app.plugins.schema_utils import append_schema_field
        append_schema_field(schema, group_key, field_schema)

    async def _apply_schema_decoration(
        self,
        provider: Any,
        schema: dict[str, Any],
        config_data: dict[str, Any],
        kind: str,
    ) -> dict[str, Any]:
        schema = await self._apply_schema_options_providers(
            provider,
            schema,
            config_data,
            kind,
        )
        hooks_factory = provider.metadata.get("hooks_factory")
        if hooks_factory is None:
            return schema
        from app.plugins.schema_utils import SchemaDecorationContext

        hooks = hooks_factory()
        ctx = SchemaDecorationContext(
            get_emulator_combox=self.get_emulator_combox,
            get_emulator_devices_combox=self.get_emulator_devices_combox,
            get_plan_combox=self.get_plan_combox,
            get_stage_info=self.get_stage_info,
        )
        if kind == "script":
            return await hooks.decorate_script_schema(schema, config_data, ctx)
        return await hooks.decorate_user_schema(schema, config_data, ctx)

    async def _apply_schema_options_providers(
        self,
        provider: Any,
        schema: dict[str, Any],
        config_data: dict[str, Any],
        kind: str,
    ) -> dict[str, Any]:
        from app.plugins.schema_utils import SchemaOptionsProviderContext

        options_providers = provider.metadata.get("options_providers")
        if not isinstance(options_providers, dict):
            options_providers = {}

        config_class = (
            provider.script_config_class if kind == "script" else provider.user_config_class
        )
        ctx = SchemaOptionsProviderContext(
            kind=kind,
            provider=provider,
            global_config=self,
            related_config=getattr(config_class, "related_config", {}),
        )
        options_providers = dict(options_providers)

        async def _external_options_resolver(
            *,
            options_provider: dict[str, Any],
            field_schema: dict[str, Any],
            config_data: dict[str, Any],
            ctx: SchemaOptionsProviderContext,
        ) -> list[dict[str, Any]] | None:
            return await self._resolve_external_schema_options(
                source=str(options_provider.get("source") or "").strip(),
                options_provider=options_provider,
                field_schema=field_schema,
                config_data=config_data,
                ctx=ctx,
            )

        for external_source in ("emulator_options", "emulator_device_options"):
            options_providers.setdefault(external_source, _external_options_resolver)

        groups = schema.get("groups")
        if not isinstance(groups, list):
            return schema

        for group in groups:
            if not isinstance(group, dict):
                continue
            fields = group.get("fields")
            if not isinstance(fields, list):
                continue
            for field in fields:
                if not isinstance(field, dict):
                    continue
                options_provider = field.get("options_provider")
                if not isinstance(options_provider, dict):
                    continue
                source = str(options_provider.get("source") or "").strip()
                if not source:
                    continue
                resolver = options_providers.get(source)
                if not callable(resolver):
                    logger.warning(
                        f"动态 options provider 未注册: type={provider.type_key}, source={source}"
                    )
                    continue
                options = await resolver(
                    options_provider=copy.deepcopy(options_provider),
                    field_schema=copy.deepcopy(field),
                    config_data=copy.deepcopy(config_data),
                    ctx=ctx,
                )
                if not isinstance(options, list):
                    continue
                self._set_schema_field_options(
                    schema,
                    str(field.get("key") or ""),
                    options,
                    allow_custom=(
                        bool(options_provider.get("allow_custom"))
                        if "allow_custom" in options_provider
                        else None
                    ),
                )

        return schema

    async def _resolve_external_schema_options(
        self,
        *,
        source: str,
        options_provider: dict[str, Any],
        field_schema: dict[str, Any],
        config_data: dict[str, Any],
        ctx: Any,
    ) -> list[dict[str, Any]] | None:
        _ = field_schema, ctx
        if source not in {"emulator_options", "emulator_device_options"}:
            return None

        try:
            from app.plugins import PluginManager

            emulator_service = PluginManager.service.get("emulator")
        except Exception:
            emulator_service = None

        resolver = getattr(emulator_service, "resolve_options_provider", None)
        if not callable(resolver):
            return None

        result = resolver(
            options_provider=options_provider,
            config_data=config_data,
        )
        import inspect

        if inspect.isawaitable(result):
            result = await result
        return result if isinstance(result, list) else None

    def _resolve_script_type_label(self, script_config: ConfigBase) -> str:
        """获取脚本类型的显示标签，兼容插件脚本。"""
        class_name = type(script_config).__name__
        if class_name in TYPE_BOOK:
            return TYPE_BOOK[class_name]
        try:
            provider = self._resolve_record_provider(script_config)
            return provider.display_name
        except (KeyError, Exception):
            return class_name

    async def get_script_records(self, script_id: str | None = None) -> list[ScriptRecord]:
        """获取通用脚本记录。"""

        from app.models.plugin_script_config import PluginScriptConfig

        if script_id is None:
            script_pairs = [(uid, config) for uid, config in self.ScriptConfig.items()]
        else:
            uid = uuid.UUID(script_id)
            script_pairs = [(uid, self.ScriptConfig[uid])]

        records: list[ScriptRecord] = []
        for uid, config in script_pairs:
            provider = self._resolve_record_provider(config)

            if isinstance(config, PluginScriptConfig):
                raw = config.get("PluginData", "Config")
                config_data = await storage_to_form(provider, raw, "script")
                config_data = self._normalize_plugin_script_form_payload(
                    provider,
                    config_data,
                )
                name = self._script_record_name(
                    provider,
                    config_data,
                    config.get("Info", "Name") or provider.display_name,
                )
                if not isinstance(config_data.get("script_name"), str) or not str(
                    config_data.get("script_name") or ""
                ).strip():
                    config_data["script_name"] = name
                config_data.setdefault("Info", {})["Name"] = name
            else:
                config_data = await storage_to_form(
                    provider,
                    await config.toDict(),
                    "script",
                )
                name = provider.display_name
                if (
                    "Info" in config._config_item_index
                    and "Name" in config._config_item_index["Info"]
                ):
                    name = config.get("Info", "Name")

            schema = copy.deepcopy(provider.build_script_schema())
            schema = await self._apply_schema_decoration(
                provider, schema, config_data, "script"
            )
            capability = provider.resolve_record_capability(config_data)

            records.append(
                ScriptRecord(
                    id=str(uid),
                    type=provider.type_key,
                    name=name,
                    config=config_data,
                    schema=schema,
                    editor_kind=provider.editor_kind,
                    supported_modes=list(capability.supported_modes or ()),
                    available=capability.available,
                    unavailable_reason=capability.unavailable_reason,
                    icon=provider.icon,
                    icon_url=f"/api/script-types/{provider.type_key}/icon" if provider.icon_path else None,
                    theme_color=provider.metadata.get("theme_color"),
                    docs_url=provider.docs_url,
                    edit_hint=provider.metadata.get("script_edit_hint"),
                    user_count=len(config.UserData) if hasattr(config, "UserData") else 0,
                )
            )

        return records

    async def get_user_records(
        self, script_id: str, user_id: str | None = None
    ) -> list[ScriptUserRecord]:
        """获取通用用户记录。"""

        from app.models.plugin_script_config import PluginUserConfig

        script_uid = uuid.UUID(script_id)
        script_config = self.ScriptConfig[script_uid]
        provider = self._resolve_record_provider(script_config)

        if user_id is None:
            user_pairs = [(uid, config) for uid, config in script_config.UserData.items()]
        else:
            uid = uuid.UUID(user_id)
            user_pairs = [(uid, script_config.UserData[uid])]

        records: list[ScriptUserRecord] = []
        for uid, config in user_pairs:
            if isinstance(config, PluginUserConfig):
                raw = config.get("PluginData", "Config")
                config_data = await storage_to_form(provider, raw, "user")
                name = config.get("Info", "Name") or str(uid)
                name = self._user_record_name(config_data, name)
                if not isinstance(config_data.get("user_name"), str) or not str(
                    config_data.get("user_name") or ""
                ).strip():
                    config_data["user_name"] = name
                config_data.setdefault("Info", {})["Name"] = name
            else:
                config_data = await storage_to_form(
                    provider,
                    await config.toDict(),
                    "user",
                )
                name = str(uid)
                if (
                    "Info" in config._config_item_index
                    and "Name" in config._config_item_index["Info"]
                ):
                    name = config.get("Info", "Name")

            schema = copy.deepcopy(provider.build_user_schema())
            schema = await self._apply_schema_decoration(
                provider, schema, config_data, "user"
            )

            records.append(
                ScriptUserRecord(
                    id=str(uid),
                    script_id=str(script_uid),
                    type=provider.type_key,
                    name=name,
                    config=config_data,
                    schema=schema,
                )
            )

        return records

    async def set_infrastructure(
        self, script_id: str, user_id: str, jsonFile: str
    ) -> None:
        logger.info(f"{script_id} - {user_id} 设置基建配置: {jsonFile}")

        script_uid = uuid.UUID(script_id)
        user_uid = uuid.UUID(user_id)
        json_path = Path(jsonFile)

        if not json_path.exists():
            raise FileNotFoundError(f"文件未找到: {json_path}")

        if not is_script_config_compatible_with_type_key(
            self.ScriptConfig[script_uid], "MAA"
        ):
            raise TypeError(f"脚本 {script_id} 不是 MAA 脚本, 无法设置基建配置")

        infrast_data = json.loads(json_path.read_text(encoding="utf-8"))

        if len(infrast_data.get("plans", [])) == 0:
            raise ValueError("未找到有效的基建排班信息")

        # 如果标题为默认标题, 则使用文件名作为标题
        if infrast_data.get("title", "文件标题") == "文件标题":
            infrast_data["title"] = json_path.stem

        from app.models.plugin_script_config import PluginUserConfig

        user_config = self.ScriptConfig[script_uid].UserData[user_uid]
        if isinstance(user_config, PluginUserConfig):
            provider = self._resolve_record_provider(self.ScriptConfig[script_uid])
            self._require_provider_available(provider, "设置基建配置")
            form_payload = await storage_to_form(
                provider,
                user_config.get("PluginData", "Config"),
                "user",
            )
            form_payload.setdefault("Data", {})["CustomInfrast"] = infrast_data
            storage_payload = await form_to_storage(provider, form_payload, "user")
            await user_config.set(
                "PluginData", "Config",
                json.dumps(storage_payload, ensure_ascii=False),
            )
            return

        await user_config.set(
            "Data", "CustomInfrast", json.dumps(infrast_data, ensure_ascii=False)
        )

    async def get_user_combox_infrastructure(
        self, script_id: str, user_id: str
    ) -> list[dict]:
        logger.info(f"获取用户自定义基建排班下拉框信息: {script_id} - {user_id}")

        script_uid = uuid.UUID(script_id)
        user_uid = uuid.UUID(user_id)

        script_config = self.ScriptConfig[script_uid]

        # 根据脚本类型选择添加对应用户配置
        if not is_script_config_compatible_with_type_key(script_config, "MAA"):
            raise TypeError(f"不支持的脚本配置类型: {type(script_config)}")

        logger.info("开始获取用户自定义基建排班下拉框信息")

        from app.models.plugin_script_config import PluginUserConfig

        user_config = script_config.UserData[user_uid]
        if isinstance(user_config, PluginUserConfig):
            provider = self._resolve_record_provider(script_config)
            form_payload = await storage_to_form(
                provider,
                user_config.get("PluginData", "Config"),
                "user",
            )
            custom_infrast = form_payload.get("Data", {}).get("CustomInfrast", {})
        else:
            custom_infrast = json.loads(user_config.get("Data", "CustomInfrast"))

        data = []
        for i, plan in enumerate(custom_infrast.get("plans", [])):
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
                await self.PlanConfig[plan_uid].set(group, name, value)

    async def del_plan(self, plan_id: str) -> None:
        """删除计划表配置"""

        logger.info(f"删除计划表配置: {plan_id}")

        plan_uid = uuid.UUID(plan_id)

        user_list = []

        for script in self.ScriptConfig.values():
            if is_script_config_compatible_with_type_key(script, "MAA"):
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
        """获取模拟器配置"""
        logger.info(f"获取全局模拟器设置: {emulator_id}")

        if emulator_id is None:
            data = await self.EmulatorConfig.toDict()
        else:
            data = await self.EmulatorConfig.get(uuid.UUID(emulator_id))

        index = data.pop("instances", [])
        return list(index), data

    async def add_emulator(self) -> tuple[uuid.UUID, EmulatorConfig]:
        """添加模拟器配置"""
        logger.info("添加全局模拟器配置")

        uid, config = await self.EmulatorConfig.add(EmulatorConfig)
        return uid, config

    async def update_emulator(
        self, emulator_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新模拟器配置"""

        emulator_uid = uuid.UUID(emulator_id)

        logger.info(f"更新模拟器配置: {emulator_id}")

        for group, items in data.items():
            for name, value in items.items():
                await self.EmulatorConfig[emulator_uid].set(group, name, value)

    async def del_emulator(self, emulator_id: str) -> None:
        """删除模拟器配置"""

        emulator_uid = uuid.UUID(emulator_id)

        logger.info(f"删除全局模拟器配置: {emulator_id}")

        from app.models.plugin_script_config import PluginScriptConfig

        script_list: list[tuple[uuid.UUID, ConfigBase, str]] = []

        async def get_plugin_script_payload(script: PluginScriptConfig) -> dict[str, Any]:
            provider = self._resolve_record_provider(script)
            raw = script.get("PluginData", "Config")
            return await storage_to_form(provider, raw, "script")

        async def set_plugin_script_payload(
            script: PluginScriptConfig,
            payload: dict[str, Any],
        ) -> None:
            provider = self._resolve_record_provider(script)
            storage_payload = await form_to_storage(provider, payload, "script")
            await script.set(
                "PluginData",
                "Config",
                json.dumps(storage_payload, ensure_ascii=False),
            )

        for script_uid, script in self.ScriptConfig.items():
            if (
                is_script_config_compatible_with_type_key(script, "MAA")
                or is_script_config_compatible_with_type_key(script, "SRC")
            ):
                if isinstance(script, PluginScriptConfig):
                    script_payload = await get_plugin_script_payload(script)
                    emulator_group = script_payload.get("Emulator")
                    script_emulator_id = (
                        emulator_group.get("Id")
                        if isinstance(emulator_group, dict)
                        else None
                    )
                else:
                    script_emulator_id = script.get("Emulator", "Id")

                if script_emulator_id == str(emulator_id):
                    if script.is_locked:
                        raise RuntimeError(
                            f"脚本 {script.get('Info','Name')} 正在使用此模拟器且被锁定, 无法完成删除"
                        )
                    script_list.append((script_uid, script, "emulator_group"))
            elif is_script_config_compatible_with_type_key(script, "MaaEnd"):
                if isinstance(script, PluginScriptConfig):
                    script_payload = await get_plugin_script_payload(script)
                    game_group = script_payload.get("Game")
                    script_emulator_id = (
                        game_group.get("EmulatorId")
                        if isinstance(game_group, dict)
                        else None
                    )
                else:
                    script_emulator_id = script.get("Game", "EmulatorId")

                if script_emulator_id == str(emulator_id):
                    if script.is_locked:
                        raise RuntimeError(
                            f"脚本 {script.get('Info','Name')} 正在使用此模拟器且被锁定, 无法完成删除"
                        )
                    script_list.append((script_uid, script, "game_group"))
            elif self._is_general_script_config(script):
                general_payload = await self._read_general_script_payload(script_uid)
                game_group = general_payload.get("Game")
                if (
                    isinstance(game_group, dict)
                    and game_group.get("Type") == "Emulator"
                    and game_group.get("EmulatorId") == str(emulator_id)
                ):
                    if script.is_locked:
                        raise RuntimeError(
                            f"脚本 {script.get('Info','Name')} 正在使用此模拟器且被锁定, 无法完成删除"
                        )
                    script_list.append((script_uid, script, "general_game_group"))

        for script_uid, script, emulator_field_kind in script_list:
            if emulator_field_kind == "emulator_group":
                if isinstance(script, PluginScriptConfig):
                    script_payload = await get_plugin_script_payload(script)
                    emulator_group = script_payload.setdefault("Emulator", {})
                    if isinstance(emulator_group, dict):
                        emulator_group["Id"] = "-"
                    await set_plugin_script_payload(script, script_payload)
                else:
                    await script.set("Emulator", "Id", "-")
            elif emulator_field_kind == "game_group":
                if isinstance(script, PluginScriptConfig):
                    script_payload = await get_plugin_script_payload(script)
                    game_group = script_payload.setdefault("Game", {})
                    if isinstance(game_group, dict):
                        game_group["EmulatorId"] = "-"
                    await set_plugin_script_payload(script, script_payload)
                else:
                    await script.set("Game", "EmulatorId", "-")
            elif emulator_field_kind == "general_game_group":
                general_payload = await self._read_general_script_payload(script_uid)
                game_group = general_payload.setdefault("Game", {})
                if isinstance(game_group, dict):
                    game_group["EmulatorId"] = "-"
                await self._write_general_script_payload(script_uid, general_payload)

        await self.EmulatorConfig.remove(emulator_uid)

    async def reorder_emulator(self, index_list: list[str]) -> None:
        """重新排序模拟器"""

        logger.info(f"重新排序模拟器: {index_list}")

        await self.EmulatorConfig.setOrder(list(map(uuid.UUID, index_list)))

    async def get_webhook(
        self,
        script_id: Optional[str],
        user_id: Optional[str],
        webhook_id: Optional[str],
    ) -> tuple[list, dict]:
        """获取脚本用户 webhook 配置（全局 webhook 见 Config.setting.custom_webhooks）。"""

        if not script_id or not user_id:
            raise ValueError("脚本 webhook 须提供 script_id 与 user_id")

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
        """添加脚本用户 webhook 配置。"""

        if not script_id or not user_id:
            raise ValueError("脚本 webhook 须提供 script_id 与 user_id")

        logger.info(f"添加webhook配置: {script_id} - {user_id}")
        script_uid = uuid.UUID(script_id)
        user_uid = uuid.UUID(user_id)
        return await (
            self.ScriptConfig[script_uid]
            .UserData[user_uid]
            .Notify_CustomWebhooks.add(Webhook)
        )

    async def update_webhook(
        self,
        script_id: Optional[str],
        user_id: Optional[str],
        webhook_id: str,
        data: Dict[str, Dict[str, Any]],
    ) -> None:
        """更新脚本用户 webhook 配置。"""

        if not script_id or not user_id:
            raise ValueError("脚本 webhook 须提供 script_id 与 user_id")

        logger.info(f"更新 webhook 配置: {script_id} - {user_id} - {webhook_id}")
        script_uid = uuid.UUID(script_id)
        user_uid = uuid.UUID(user_id)
        webhook_uid = uuid.UUID(webhook_id)
        for group, items in data.items():
            for name, value in items.items():
                await (
                    self.ScriptConfig[script_uid]
                    .UserData[user_uid]
                    .Notify_CustomWebhooks[webhook_uid]
                    .set(group, name, value)
                )

    async def del_webhook(
        self, script_id: Optional[str], user_id: Optional[str], webhook_id: str
    ) -> None:
        """删除脚本用户 webhook 配置。"""

        if not script_id or not user_id:
            raise ValueError("脚本 webhook 须提供 script_id 与 user_id")

        logger.info(f"删除 webhook 配置: {script_id} - {user_id} - {webhook_id}")
        await (
            self.ScriptConfig[uuid.UUID(script_id)]
            .UserData[uuid.UUID(user_id)]
            .Notify_CustomWebhooks.remove(uuid.UUID(webhook_id))
        )

    async def reorder_webhook(
        self, script_id: Optional[str], user_id: Optional[str], index_list: list[str]
    ) -> None:
        """重新排序脚本用户 webhook。"""

        if not script_id or not user_id:
            raise ValueError("脚本 webhook 须提供 script_id 与 user_id")

        logger.info(f"重新排序 webhook: {script_id} - {user_id} - {index_list}")
        await (
            self.ScriptConfig[uuid.UUID(script_id)]
            .UserData[uuid.UUID(user_id)]
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
            logger.info(f"使用代理: {proxy_addr}")
            return httpx.Proxy(proxy_addr)
        except Exception as e:
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
    ):
        """获取关卡信息"""

        # get_stage 会立即返回缓存，网络刷新在后台进行
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
        elif type == "User":
            data = json.loads(self.get("Data", "Stage")).get("ALL", [])
            for combox in data:
                combox["label"] = RESOURCE_STAGE_DATE_TEXT.get(
                    combox["value"], combox["label"]
                )
            return data
        elif type == "Today":
            return json.loads(self.get("Data", "Stage")).get(
                datetime.now(tz=UTC4).strftime("%A"), []
            )
        else:
            return json.loads(self.get("Data", "Stage")).get(type, [])

    async def get_stage(self) -> Optional[Dict[str, List[Dict[str, str]]]]:
        """更新活动关卡信息。网络检查在后台执行，立即返回本地缓存。"""

        if datetime.now() - timedelta(hours=1) < datetime.strptime(
            self.get("Data", "LastStageUpdated"), "%Y-%m-%d %H:%M:%S"
        ):
            logger.info("一小时内已进行过一次检查, 直接使用缓存的活动关卡信息")
            return json.loads(self.get("Data", "Stage"))

        if not self._stage_refreshing:
            self._stage_refreshing = True
            task = asyncio.create_task(self._refresh_stage())
            self.temp_task.append(task)

            def _done(t: asyncio.Task) -> None:
                self._stage_refreshing = False
                if t in self.temp_task:
                    self.temp_task.remove(t)

            task.add_done_callback(_done)
        else:
            logger.info("活动关卡信息更新任务已在进行中")

        return json.loads(self.get("Data", "Stage"))

    async def _refresh_stage(self) -> None:
        """从远端刷新活动关卡信息（仅后台调用）。"""

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
        except Exception as e:
            logger.warning(f"无法从MAA服务器获取活动关卡信息: {e}")

    def _get_script_combox_label(self, script: ConfigBase) -> str:
        script_name = script.get("Info", "Name")
        if isinstance(script, MaaFWConfig):
            return script_name or "MaaFW"
        type_label = self._resolve_script_type_label(script)
        return f"{type_label} - {script_name}"

    def _get_task_combox_label(self, script: ConfigBase) -> str:
        return f"脚本 - {self._get_script_combox_label(script)}"

    async def get_script_combox(self):
        """获取脚本下拉框信息"""

        logger.info("开始获取脚本下拉框信息")
        data = [{"label": "未选择", "value": "-"}]
        for uid, script in self.ScriptConfig.items():
            capability = await self.get_script_record_capability(uid)
            if not capability.available:
                continue
            data.append(
                {
                    "label": self._get_script_combox_label(script),
                    "value": str(uid),
                    "supported_modes": list(capability.supported_modes or ()),
                }
            )
        logger.success("脚本下拉框信息获取成功")

        return data

    async def get_task_combox(self):
        """获取任务下拉框信息"""

        logger.info("开始获取任务下拉框信息")
        data = [{"label": "未选择", "value": None}]
        for uid, queue in self.QueueConfig.items():
            script_ids = [
                str(queue_item.get("Info", "ScriptId") or "").strip()
                for queue_item in queue.QueueItem.values()
                if str(queue_item.get("Info", "ScriptId") or "").strip()
                not in ("", "-")
            ]
            queue_modes: list[str] | None = None
            queue_available = True
            for script_id in script_ids:
                try:
                    capability = await self.get_script_record_capability(script_id)
                except (KeyError, ValueError):
                    queue_available = False
                    break
                if not capability.available:
                    queue_available = False
                    break
                current_modes = list(capability.supported_modes or ())
                queue_modes = (
                    current_modes
                    if queue_modes is None
                    else [mode for mode in queue_modes if mode in current_modes]
                )
            if not queue_available or (script_ids and not queue_modes):
                continue
            data.append(
                {
                    "label": f"队列 - {queue.get('Info', 'Name')}",
                    "value": str(uid),
                    "supported_modes": queue_modes,
                }
            )
        for uid, script in self.ScriptConfig.items():
            capability = await self.get_script_record_capability(uid)
            if capability.available and not script.is_locked:
                data.append(
                    {
                        "label": self._get_task_combox_label(script),
                        "value": str(uid),
                        "supported_modes": list(capability.supported_modes or ()),
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

        if self.EmulatorConfig[uuid.UUID(emulator_id)].get("Info", "Type") == "general":
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
        except Exception as e:
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


Config = AppConfig()
