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
import re
import sys
import copy
import hashlib
import httpx
import shutil
import asyncio
import uvicorn
import sqlite3
import truststore
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta, date
from typing import Literal, Optional, Union, Dict, Any, List
import uuid
import json
import inspect
from contextlib import asynccontextmanager
from contextvars import ContextVar
from functools import wraps
from collections.abc import AsyncIterator, Callable, Coroutine, Mapping

from app.models.ConfigBase import ConfigBase, JSONValidator
from app.models.config import (
    MaaConfig,
    MaaPlanConfig,
    QueueConfig,
    QueueItem,
    GlobalConfig,
    ConfigBase,
    CLASS_BOOK,
    Webhook,
    TimeSet,
    EmulatorConfig,
    GameSignAccountGroup,
    MaaFWConfig,
)
from app.models.script_api import ScriptRecord, ScriptTypeDescriptor, ScriptUserRecord
from app.utils.constants import (
    UTC4,
    UTC8,
    RESOURCE_STAGE_INFO,
    RESOURCE_STAGE_DROP_INFO,
    TYPE_BOOK,
    RESOURCE_STAGE_DATE_TEXT,
    MAA_DEPOT_EXCLUDED_ITEM_IDS,
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

GAME_SIGN_RESULT_FILENAME = "GameSignResult.json"


def _load_game_sign_result_snapshot(
    path: Path, *, result_date: str
) -> dict[str, Any]:
    """读取当天的游戏签到结果快照。"""

    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"读取游戏签到结果快照失败: {e}")
        return {}

    if not isinstance(payload, dict) or payload.get("date") != result_date:
        return {}

    result = payload.get("result")
    if not isinstance(result, dict):
        logger.warning("游戏签到结果快照格式无效，已忽略")
        return {}
    return result


def _save_game_sign_result_snapshot(
    path: Path | None, result: dict[str, Any], *, result_date: str
) -> None:
    """原子保存游戏签到结果快照。"""

    if path is None:
        return

    temporary_path = path.with_name(f"{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_text(
            json.dumps(
                {"date": result_date, "result": result},
                ensure_ascii=False,
                indent=4,
            ),
            encoding="utf-8",
        )
        temporary_path.replace(path)
    except (OSError, TypeError, ValueError) as e:
        logger.warning(f"保存游戏签到结果快照失败: {e}")


async def _run_to_thread_with_cancellation_drain(
    function: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Drain a blocking worker before propagating task cancellation.

    Configuration write scopes own process-wide locks.  Cancelling an ordinary
    ``await asyncio.to_thread(...)`` releases those locks while the worker is
    still mutating the filesystem, allowing a following request to observe a
    half-finished delete.  Keep the worker attached to this task until it has
    reached a terminal state, then preserve cancellation priority.
    """

    worker = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    cancellation_requested = False
    while not worker.done():
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            cancellation_requested = True
        except BaseException:
            # The worker reached a terminal failure; consume its authoritative
            # result below so cancellation keeps priority when requested.
            break

    try:
        result = worker.result()
    except BaseException:
        if cancellation_requested:
            raise asyncio.CancelledError
        raise
    if cancellation_requested:
        raise asyncio.CancelledError
    return result


class ScriptTypeConversionCASMismatch(RuntimeError):
    """The source record changed before a type conversion could commit."""

    conversion_state = "source_changed"


def _script_config_write(
    *,
    script_id_argument: str | None = None,
    owner_reentrant: bool = False,
) -> Callable:
    """串行化一个公开的脚本或用户配置写操作。"""

    def decorate(method: Callable[..., Coroutine[Any, Any, Any]]) -> Callable:
        signature = inspect.signature(method)

        @wraps(method)
        async def wrapped(self: "AppConfig", *args: Any, **kwargs: Any) -> Any:
            script_id: str | None = None
            if script_id_argument is not None:
                bound = signature.bind(self, *args, **kwargs)
                raw_script_id = bound.arguments[script_id_argument]
                script_id = (
                    None if raw_script_id is None else str(raw_script_id)
                )

            async with self._script_config_write_scope(
                script_id,
                owner_reentrant=owner_reentrant,
            ):
                return await method(self, *args, **kwargs)

        return wrapped

    return decorate


class AppConfig(GlobalConfig):
    VERSION = "v5.4.0-beta.1"

    def __init__(self) -> None:
        super().__init__()
        apply_script_type_registry_to_global_config(self)

        logger.info("")
        logger.info("===================================")
        logger.info("AUTO-MAS 后端应用程序")
        logger.info(f"版本号:  {self.VERSION}")
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
        self._game_sign_result_date = ""
        self._script_config_write_lock = asyncio.Lock()
        self._script_config_transaction: ContextVar[
            tuple[str, str, asyncio.Task[Any]] | None
        ] = ContextVar(
            f"script_config_transaction_{id(self)}",
            default=None,
        )
        self._script_config_write_task: ContextVar[
            asyncio.Task[Any] | None
        ] = ContextVar(
            f"script_config_write_task_{id(self)}",
            default=None,
        )
        self._script_execution_reservations: dict[str, str] = {}

        self._inject_truststore()

    @asynccontextmanager
    async def script_config_transaction(
        self,
        script_id: str,
        *,
        owner: str,
    ) -> AsyncIterator[str]:
        """为单个脚本持有 owner-aware 配置维护事务。

        事务会先等待已在途的公开配置写完成，再阻止新的公开配置写，直到上下文
        退出。持有事务的任务可以重入同一脚本的 ``update_script`` 和
        ``update_user``，不会产生自锁。

        Args:
            script_id: 要维护的脚本及其全部用户配置。
            owner: 用于诊断和重入校验的非空操作标识。

        Yields:
            规范化后的 owner 标识。

        Raises:
            KeyError: 取得写锁后目标脚本已不存在。
            RuntimeError: 嵌套事务切换了 owner、脚本或 asyncio task，或尝试
                从普通写作用域升级为维护事务。
            ValueError: owner 为空。
        """

        normalized_script_id = str(uuid.UUID(script_id))
        normalized_owner = str(owner).strip()
        if not normalized_owner:
            raise ValueError("脚本配置维护事务 owner 不能为空")

        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("脚本配置维护事务必须在 asyncio task 中运行")

        active = self._script_config_transaction.get()
        if active is not None:
            active_script_id, active_owner, active_task = active
            if (
                active_script_id == normalized_script_id
                and active_owner == normalized_owner
                and active_task is task
            ):
                yield normalized_owner
                return
            raise RuntimeError(
                "脚本配置维护事务不可跨 owner、script_id 或 asyncio task 重入: "
                f"active_owner={active_owner}, active_script_id={active_script_id}"
            )

        active_write_task = self._script_config_write_task.get()
        if active_write_task is not None:
            raise RuntimeError("普通脚本配置写作用域中不能启动配置维护事务")

        async with self._script_config_write_lock:
            script_uid = uuid.UUID(normalized_script_id)
            if script_uid not in self.ScriptConfig:
                raise KeyError(f"脚本 {normalized_script_id} 不存在")
            reservation_owner = self._script_execution_reservations.get(
                normalized_script_id
            )
            if reservation_owner is not None:
                raise RuntimeError(
                    "脚本已进入任务启动或运行阶段，无法开始配置维护事务: "
                    f"script_id={normalized_script_id}, owner={reservation_owner}"
                )
            script_config = self.ScriptConfig[script_uid]
            script_config.begin_maintenance(task)

            token = self._script_config_transaction.set(
                (normalized_script_id, normalized_owner, task)
            )
            try:
                yield normalized_owner
            finally:
                try:
                    script_config.end_maintenance(task)
                finally:
                    self._script_config_transaction.reset(token)

    @asynccontextmanager
    async def _script_config_write_scope(
        self,
        script_id: str | None,
        *,
        owner_reentrant: bool,
    ) -> AsyncIterator[None]:
        """门控一个普通脚本或用户配置写操作。"""

        normalized_script_id = (
            str(uuid.UUID(script_id)) if script_id is not None else None
        )
        active = self._script_config_transaction.get()
        if active is not None:
            active_script_id, active_owner, active_task = active
            if (
                owner_reentrant
                and normalized_script_id == active_script_id
                and asyncio.current_task() is active_task
            ):
                yield
                return
            raise RuntimeError(
                "脚本配置维护事务期间不允许执行当前写操作: "
                f"owner={active_owner}, script_id={active_script_id}"
            )

        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("脚本配置写操作必须在 asyncio task 中运行")
        active_write_task = self._script_config_write_task.get()
        if active_write_task is task:
            yield
            return
        if active_write_task is not None:
            raise RuntimeError("普通脚本配置写作用域不可跨 asyncio task 继承")

        async with self._script_config_write_lock:
            token = self._script_config_write_task.set(task)
            try:
                yield
            finally:
                self._script_config_write_task.reset(token)

    @asynccontextmanager
    async def script_config_write_scope(
        self,
        script_id: str | None,
    ) -> AsyncIterator[None]:
        """串行执行插件存储写入，并允许同一 task 内重入。"""

        async with self._script_config_write_scope(
            script_id,
            owner_reentrant=True,
        ):
            yield

    async def try_reserve_script_execution(
        self,
        script_id: str,
        *,
        owner: str,
    ) -> bool:
        """Atomically reserve a record before resolving its execution provider.

        The reservation closes the gap between TaskManager provider resolution and
        the manager's normal runtime lock.  Configuration maintenance (including
        MaaFW Managed conversion) rejects the record until the task releases it.
        """

        normalized_script_id = str(uuid.UUID(script_id))
        normalized_owner = str(owner).strip()
        if not normalized_owner:
            raise ValueError("脚本运行 reservation owner 不能为空")
        async with self._script_config_write_lock:
            script_uid = uuid.UUID(normalized_script_id)
            if script_uid not in self.ScriptConfig:
                raise KeyError(f"脚本 {normalized_script_id} 不存在")
            if self.ScriptConfig[script_uid].is_locked:
                return False
            if normalized_script_id in self._script_execution_reservations:
                return False
            self._script_execution_reservations[normalized_script_id] = (
                normalized_owner
            )
            return True

    async def release_script_execution(
        self,
        script_id: str,
        *,
        owner: str,
    ) -> None:
        """Release a TaskManager execution reservation idempotently."""

        normalized_script_id = str(uuid.UUID(script_id))
        normalized_owner = str(owner).strip()
        async with self._script_config_write_lock:
            current_owner = self._script_execution_reservations.get(
                normalized_script_id
            )
            if current_owner is None:
                return
            if current_owner != normalized_owner:
                raise RuntimeError(
                    "脚本运行 reservation owner 不匹配: "
                    f"script_id={normalized_script_id}, "
                    f"expected={current_owner}, actual={normalized_owner}"
                )
            self._script_execution_reservations.pop(normalized_script_id, None)

    @_script_config_write(script_id_argument="script_id")
    async def lock_script_config(self, script_id: str) -> ConfigBase:
        """在宿主写门内锁定一个运行中的脚本配置。"""

        script_config = self.ScriptConfig[uuid.UUID(script_id)]
        await script_config.lock()
        return script_config

    @_script_config_write(script_id_argument="script_id")
    async def unlock_script_config(self, script_id: str) -> None:
        """在宿主写门内解锁一个运行结束的脚本配置。"""

        await self.ScriptConfig[uuid.UUID(script_id)].unlock()

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

        await asyncio.gather(
            self.connect(self.config_path / "Config.json"),
            self.EmulatorConfig.connect(self.config_path / "EmulatorConfig.json"),
            self.PlanConfig.connect(self.config_path / "PlanConfig.json"),
            self.ScriptConfig.connect(self.config_path / "ScriptConfig.json"),
            self.QueueConfig.connect(self.config_path / "QueueConfig.json"),
            self.ToolsConfig.connect(self.config_path / "ToolsConfig.json"),
            self.PluginConfig.connect(self.config_path / "PluginConfig.json"),
        )

        migration_marker = self.config_path / ".migrated_script_storage"
        if not migration_marker.exists():
            await self._migrate_general_scripts_to_plugin_storage()
            await self._migrate_okww_scripts_to_plugin_storage()
            try:
                migration_marker.touch()
            except OSError:
                logger.warning("无法创建迁移标记文件，下次启动仍会检查迁移")

        # 游戏签到：连接账号组 MultipleConfig
        await self.ToolsConfig.GameSign_Accounts.connect(
            self.config_path / "GameSignAccounts.json"
        )

        # 游戏签到：恢复当天的结果快照，跨日结果不继续展示
        today = datetime.now().strftime("%Y-%m-%d")
        self.ToolsConfig._game_sign_result_data = _load_game_sign_result_snapshot(
            self.config_path / GAME_SIGN_RESULT_FILENAME,
            result_date=today,
        )
        self._game_sign_result_date = today

        # 游戏签到：如果不是今天签到的，清除计划时间以便重新计算
        last_sign_date = self.ToolsConfig.get("GameSign", "LastSignDate")
        if last_sign_date != today:
            await self.ToolsConfig.set("GameSign", "ScheduledTime", "")

        from app.services import System

        self.bind("Start", "IfSelfStart", System.set_SelfStart)
        self.bind("Function", "IfAllowSleep", System.set_Sleep)
        asyncio.create_task(System.set_SelfStart(self.get("Start", "IfSelfStart")))
        await System.set_Sleep(self.get("Function", "IfAllowSleep"))

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

    @_script_config_write()
    async def add_script(
        self,
        script: str,
        script_id: str | None = None,
    ) -> tuple[uuid.UUID, ConfigBase]:
        """添加脚本配置。"""

        logger.info(f"添加脚本配置: {script}, 从 {script_id} 复制")

        provider = script_type_registry.get(script)
        self._require_provider_available(provider, "新增脚本配置")
        self._require_provider_creatable(provider)

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

    @staticmethod
    def _canonical_payload_fingerprint(payload: Mapping[str, Any]) -> str:
        """Return a stable fingerprint without persisting payload plaintext."""

        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _write_json_atomically(path: Path, payload: Mapping[str, Any]) -> None:
        """Durably replace one JSON file without exposing a partial document."""

        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        encoded = json.dumps(payload, ensure_ascii=False, indent=4).encode("utf-8")
        with temp_path.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)

    @staticmethod
    def _conversion_journal_identity(journal: Mapping[str, Any]) -> dict[str, Any]:
        """Whitelist non-sensitive fields accepted by conversion journals."""

        allowed = (
            "schemaVersion",
            "kind",
            "operationId",
            "scriptId",
            "sourceType",
            "targetType",
            "sourceFingerprint",
            "projectReference",
            "projectId",
            "version",
            "state",
            "createdAt",
        )
        return {
            key: copy.deepcopy(journal[key])
            for key in allowed
            if key in journal
        }

    def _plugin_script_type_conversion_snapshot(
        self,
        script_id: str | uuid.UUID,
    ) -> dict[str, Any]:
        """Capture one plugin record in storage form for conversion CAS."""

        from app.models.plugin_script_config import PluginScriptConfig

        script_uid = (
            script_id if isinstance(script_id, uuid.UUID) else uuid.UUID(script_id)
        )
        script_config = self.ScriptConfig[script_uid]
        if not isinstance(script_config, PluginScriptConfig):
            raise TypeError(f"脚本 {script_uid} 不是插件脚本配置")

        user_order = [str(user_uid) for user_uid in script_config.UserData.order]
        users: dict[str, dict[str, Any]] = {}
        for user_uid in script_config.UserData.order:
            user_config = script_config.UserData[user_uid]
            users[str(user_uid)] = {
                "id": str(user_uid),
                "type": str(user_config.get("Meta", "PluginTypeKey") or ""),
                "name": str(user_config.get("Info", "Name") or ""),
                "config": self._read_plugin_payload(
                    user_config.get("PluginData", "Config")
                ),
            }

        return {
            "script": {
                "id": str(script_uid),
                "type": str(script_config.get("Meta", "PluginTypeKey") or ""),
                "name": str(script_config.get("Info", "Name") or ""),
                "config": self._read_plugin_payload(
                    script_config.get("PluginData", "Config")
                ),
            },
            "userOrder": user_order,
            "users": users,
        }

    async def get_plugin_script_type_conversion_snapshot(
        self,
        script_id: str,
    ) -> dict[str, Any]:
        """Expose an encrypted-at-rest snapshot for a subsequent conversion CAS."""

        async with self.script_config_write_scope(script_id):
            return copy.deepcopy(
                self._plugin_script_type_conversion_snapshot(script_id)
            )

    @staticmethod
    def _conversion_target_snapshot(
        source_snapshot: Mapping[str, Any],
        *,
        target_type: str,
        target_script_storage: Mapping[str, Any],
        target_user_storage: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        script = source_snapshot.get("script")
        users = source_snapshot.get("users")
        user_order = source_snapshot.get("userOrder")
        if not isinstance(script, Mapping) or not isinstance(users, Mapping):
            raise TypeError("脚本转换快照结构无效")
        if not isinstance(user_order, list):
            raise TypeError("脚本转换快照缺少用户顺序")

        target_users: dict[str, dict[str, Any]] = {}
        for user_id in user_order:
            source_user = users.get(user_id)
            if not isinstance(source_user, Mapping):
                raise ValueError(f"脚本转换快照缺少用户 {user_id}")
            target_users[str(user_id)] = {
                "id": str(user_id),
                "type": target_type,
                "name": str(source_user.get("name") or ""),
                "config": copy.deepcopy(target_user_storage[str(user_id)]),
            }

        return {
            "script": {
                "id": str(script.get("id") or ""),
                "type": target_type,
                "name": str(script.get("name") or ""),
                "config": copy.deepcopy(target_script_storage),
            },
            "userOrder": [str(user_id) for user_id in user_order],
            "users": target_users,
        }

    @staticmethod
    def _validate_conversion_target_snapshot(
        target_snapshot: Mapping[str, Any],
        *,
        source_snapshot: Mapping[str, Any],
        target_type: str,
    ) -> dict[str, Any]:
        """Validate a decrypted durable target artifact before replay."""

        candidate = copy.deepcopy(dict(target_snapshot))
        source_script = source_snapshot.get("script")
        source_users = source_snapshot.get("users")
        source_order = source_snapshot.get("userOrder")
        script = candidate.get("script")
        users = candidate.get("users")
        order = candidate.get("userOrder")
        if not all(
            isinstance(item, Mapping)
            for item in (source_script, source_users, script, users)
        ) or not isinstance(source_order, list) or not isinstance(order, list):
            raise RuntimeError("脚本转换 target artifact 结构无效")
        normalized_order = [str(item) for item in order]
        if (
            order != source_order
            or len(users) != len(normalized_order)
            or set(users) != set(normalized_order)
        ):
            raise RuntimeError("脚本转换 target artifact 的用户顺序无效")
        if (
            script.get("id") != source_script.get("id")
            or script.get("name") != source_script.get("name")
            or script.get("type") != target_type
            or not isinstance(script.get("config"), Mapping)
        ):
            raise RuntimeError("脚本转换 target artifact 的脚本身份无效")
        for user_id in order:
            source_user = source_users.get(user_id)
            target_user = users.get(user_id)
            if not isinstance(source_user, Mapping) or not isinstance(
                target_user, Mapping
            ):
                raise RuntimeError(
                    f"脚本转换 target artifact 缺少用户 {user_id}"
                )
            if (
                target_user.get("id") != user_id
                or target_user.get("name") != source_user.get("name")
                or target_user.get("type") != target_type
                or not isinstance(target_user.get("config"), Mapping)
            ):
                raise RuntimeError(
                    f"脚本转换 target artifact 的用户 {user_id} 身份无效"
                )
        return candidate

    def _load_conversion_target_artifact(
        self,
        path: Path,
        *,
        operation_id: str,
        source_fingerprint: str,
        source_snapshot: Mapping[str, Any],
        target_type: str,
    ) -> tuple[dict[str, Any], str]:
        """Load a DPAPI-protected exact storage target for deterministic replay."""

        from app.utils.security import dpapi_decrypt

        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise RuntimeError("脚本转换 target artifact 已损坏")
        expected_identity = {
            "schemaVersion": 1,
            "kind": "maafw.managed-conversion-target",
            "operationId": operation_id,
            "sourceFingerprint": source_fingerprint,
        }
        for key, value in expected_identity.items():
            if raw.get(key) != value:
                raise RuntimeError(f"脚本转换 target artifact 冲突: {key}")
        ciphertext = raw.get("ciphertext")
        if not isinstance(ciphertext, str) or not ciphertext:
            raise RuntimeError("脚本转换 target artifact 缺少 DPAPI 密文")
        try:
            plaintext = dpapi_decrypt(
                ciphertext,
                entropy=b"AUTO-MAS script type conversion v1",
            )
            decrypted = json.loads(plaintext)
        except Exception as exc:
            raise RuntimeError("脚本转换 target artifact 无法解密") from exc
        if not isinstance(decrypted, dict):
            raise RuntimeError("脚本转换 target artifact 解密结果无效")
        snapshot = self._validate_conversion_target_snapshot(
            decrypted,
            source_snapshot=source_snapshot,
            target_type=target_type,
        )
        fingerprint = self._canonical_payload_fingerprint(snapshot)
        if raw.get("targetFingerprint") != fingerprint:
            raise RuntimeError("脚本转换 target artifact fingerprint 不匹配")
        return snapshot, fingerprint

    def _write_conversion_target_artifact(
        self,
        path: Path,
        *,
        operation_id: str,
        source_fingerprint: str,
        target_snapshot: Mapping[str, Any],
        target_fingerprint: str,
    ) -> None:
        """Persist exact storage ciphertext encrypted as one DPAPI artifact."""

        from app.utils.security import dpapi_encrypt

        plaintext = json.dumps(
            target_snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        artifact = {
            "schemaVersion": 1,
            "kind": "maafw.managed-conversion-target",
            "operationId": operation_id,
            "sourceFingerprint": source_fingerprint,
            "targetFingerprint": target_fingerprint,
            "ciphertext": dpapi_encrypt(
                plaintext,
                description="AUTO-MAS script type conversion target",
                entropy=b"AUTO-MAS script type conversion v1",
            ),
        }
        self._write_json_atomically(path, artifact)

    async def convert_plugin_script_type(
        self,
        script_id: str,
        *,
        source_type: str,
        target_type: str,
        expected_snapshot: Mapping[str, Any],
        target_script_config: Mapping[str, Any],
        target_user_configs: Mapping[str, Mapping[str, Any]],
        journal: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Atomically retype one plugin script record in its maintenance transaction.

        The caller must already hold ``script_config_transaction`` for this script.
        The source snapshot is compared in storage form, then the complete parent and
        user record is replaced in one filesystem operation.  A non-sensitive journal
        makes retries after a process interruption deterministic.
        """

        normalized_script_id = str(uuid.UUID(script_id))
        normalized_source_type = str(source_type).strip()
        normalized_target_type = str(target_type).strip()
        if not normalized_source_type or not normalized_target_type:
            raise ValueError("脚本转换的 source_type 和 target_type 不能为空")
        if normalized_source_type == normalized_target_type:
            raise ValueError("脚本转换的源类型与目标类型不能相同")

        task = asyncio.current_task()
        active = self._script_config_transaction.get()
        if (
            task is None
            or active is None
            or active[0] != normalized_script_id
            or active[2] is not task
        ):
            raise RuntimeError(
                "convert_plugin_script_type 必须在同一脚本的配置维护事务中调用"
            )

        script_uid = uuid.UUID(normalized_script_id)
        current_config = self.ScriptConfig[script_uid]
        if current_config.is_locked:
            raise RuntimeError(f"脚本 {normalized_script_id} 正在运行，无法转换")

        source_provider = script_type_registry.get(normalized_source_type)
        target_provider = script_type_registry.get(normalized_target_type)
        if source_provider.is_builtin or target_provider.is_builtin:
            raise TypeError(
                "convert_plugin_script_type 仅支持 PluginScriptConfig provider 之间换型"
            )
        self._require_provider_available(target_provider, "转换脚本配置")

        current_snapshot = self._plugin_script_type_conversion_snapshot(script_uid)
        source_user_order = expected_snapshot.get("userOrder")
        if not isinstance(source_user_order, list):
            raise TypeError("expected_snapshot.userOrder 必须是列表")
        normalized_user_ids = [str(uuid.UUID(str(item))) for item in source_user_order]
        supplied_user_ids = {str(uuid.UUID(str(item))) for item in target_user_configs}
        if supplied_user_ids != set(normalized_user_ids):
            raise ValueError("目标用户配置必须与源用户 UUID 集合完全一致")

        current_type = str(current_snapshot["script"]["type"] or "")
        if current_type == normalized_source_type:
            if current_snapshot != dict(expected_snapshot):
                raise ScriptTypeConversionCASMismatch(
                    "脚本配置在转换前已变化，CAS 校验失败"
                )
            if any(
                user["type"] != normalized_source_type
                for user in current_snapshot["users"].values()
            ):
                raise RuntimeError(
                    "脚本包含与 source_type 不一致的用户配置，拒绝转换"
                )
            if normalized_user_ids != current_snapshot["userOrder"]:
                raise ScriptTypeConversionCASMismatch(
                    "脚本用户顺序在转换前已变化，CAS 校验失败"
                )
        elif current_type != normalized_target_type:
            raise RuntimeError(
                "脚本当前类型既不是转换源类型，也不是可恢复的目标类型"
            )

        target_script_storage = await form_to_storage(
            target_provider,
            dict(target_script_config),
            "script",
        )

        target_user_storage: dict[str, dict[str, Any]] = {}
        for user_id in normalized_user_ids:
            raw_target_user = target_user_configs.get(user_id)
            if raw_target_user is None:
                for raw_key, value in target_user_configs.items():
                    if str(uuid.UUID(str(raw_key))) == user_id:
                        raw_target_user = value
                        break
            if not isinstance(raw_target_user, Mapping):
                raise TypeError(f"目标用户配置 {user_id} 必须是对象")
            target_user_storage[user_id] = await form_to_storage(
                target_provider,
                dict(raw_target_user),
                "user",
            )

        target_snapshot = self._conversion_target_snapshot(
            expected_snapshot,
            target_type=normalized_target_type,
            target_script_storage=target_script_storage,
            target_user_storage=target_user_storage,
        )
        source_fingerprint = self._canonical_payload_fingerprint(expected_snapshot)
        target_fingerprint = self._canonical_payload_fingerprint(target_snapshot)

        journal_data = self._conversion_journal_identity(journal)
        if journal_data.get("schemaVersion") != 1:
            raise ValueError("脚本转换 journal.schemaVersion 必须为 1")
        if journal_data.get("kind") != "maafw.managed-conversion":
            raise ValueError("脚本转换 journal.kind 无效")
        operation_id = str(uuid.UUID(str(journal_data.get("operationId") or "")))
        expected_journal_fields = {
            "scriptId": normalized_script_id,
            "sourceType": normalized_source_type,
            "targetType": normalized_target_type,
            "sourceFingerprint": source_fingerprint,
        }
        for key, expected_value in expected_journal_fields.items():
            actual_value = journal_data.get(key)
            if actual_value != expected_value:
                raise ValueError(
                    f"脚本转换 journal.{key} 不匹配: {actual_value!r}"
                )
        if journal_data.get("state") != "project_imported":
            raise ValueError("脚本转换必须从 project_imported 状态开始")

        journal_dir = self.config_path / "script_config_transactions"
        journal_path = journal_dir / f"{operation_id}.json"
        target_artifact_path = journal_dir / f"{operation_id}.target.json"
        if target_artifact_path.is_file():
            target_snapshot, target_fingerprint = (
                self._load_conversion_target_artifact(
                    target_artifact_path,
                    operation_id=operation_id,
                    source_fingerprint=source_fingerprint,
                    source_snapshot=expected_snapshot,
                    target_type=normalized_target_type,
                )
            )
            target_script_storage = copy.deepcopy(
                target_snapshot["script"]["config"]
            )
            target_user_storage = {
                user_id: copy.deepcopy(target_snapshot["users"][user_id]["config"])
                for user_id in normalized_user_ids
            }
        else:
            self._write_conversion_target_artifact(
                target_artifact_path,
                operation_id=operation_id,
                source_fingerprint=source_fingerprint,
                target_snapshot=target_snapshot,
                target_fingerprint=target_fingerprint,
            )
        persisted_journal: dict[str, Any] | None = None
        if journal_path.is_file():
            raw_persisted = json.loads(journal_path.read_text(encoding="utf-8"))
            if not isinstance(raw_persisted, dict):
                raise RuntimeError("脚本转换 journal 已损坏")
            persisted_journal = raw_persisted
            for key, expected_value in {
                **expected_journal_fields,
                "operationId": operation_id,
                "kind": "maafw.managed-conversion",
                "targetFingerprint": target_fingerprint,
            }.items():
                if persisted_journal.get(key) != expected_value:
                    raise RuntimeError(f"脚本转换 journal 冲突: {key}")

        current_fingerprint = self._canonical_payload_fingerprint(current_snapshot)
        if current_fingerprint == target_fingerprint:
            if persisted_journal is None:
                raise RuntimeError("目标脚本已转换，但缺少匹配的恢复 journal")
            committed_journal = {
                **persisted_journal,
                "state": "committed",
                "recovered": persisted_journal.get("state") != "committed",
            }
            self._write_json_atomically(journal_path, committed_journal)
            return {
                "converted": True,
                "idempotent": True,
                "recovered": bool(committed_journal["recovered"]),
                "scriptId": normalized_script_id,
                "sourceType": normalized_source_type,
                "targetType": normalized_target_type,
                "journal": committed_journal,
            }

        if current_type != normalized_source_type:
            raise RuntimeError(
                "脚本目标状态与 conversion artifact 不匹配，拒绝覆盖"
            )

        prepared_journal = {
            **journal_data,
            "operationId": operation_id,
            "sourceFingerprint": source_fingerprint,
            "targetFingerprint": target_fingerprint,
            "state": "project_imported",
        }
        self._write_json_atomically(journal_path, prepared_journal)

        from app.models.plugin_script_config import (
            PluginScriptConfig,
            PluginUserConfig,
        )

        record_payload: dict[str, Any] = {
            "Meta": {"PluginTypeKey": normalized_target_type},
            "Info": {"Name": current_snapshot["script"]["name"]},
            "PluginData": {
                "Config": json.dumps(target_script_storage, ensure_ascii=False),
            },
            "SubConfigsInfo": {"UserData": {"instances": []}},
        }
        user_payload = record_payload["SubConfigsInfo"]["UserData"]
        for user_id in normalized_user_ids:
            user_payload["instances"].append(
                {"uid": user_id, "type": PluginUserConfig.__name__}
            )
            user_payload[user_id] = {
                "Meta": {"PluginTypeKey": normalized_target_type},
                "Info": {"Name": current_snapshot["users"][user_id]["name"]},
                "PluginData": {
                    "Config": json.dumps(
                        target_user_storage[user_id],
                        ensure_ascii=False,
                    ),
                },
            }

        replacement = PluginScriptConfig()
        await replacement.load(record_payload)
        for save_method in self.ScriptConfig._save_methods:
            await replacement.add_save_method(save_method)
        if self.ScriptConfig.file is not None:
            await replacement.add_save_method(self.ScriptConfig.save)

        root_payload = await self.ScriptConfig.toDict(if_decrypt=False)
        root_payload[normalized_script_id] = await replacement.toDict(if_decrypt=False)
        if self.ScriptConfig.file is None:
            raise RuntimeError("ScriptConfig 尚未连接持久化文件")
        self._write_json_atomically(self.ScriptConfig.file, root_payload)
        self.ScriptConfig.data[script_uid] = replacement

        committed_journal = {
            **prepared_journal,
            "state": "committed",
            "recovered": False,
        }
        self._write_json_atomically(journal_path, committed_journal)
        return {
            "converted": True,
            "idempotent": False,
            "recovered": False,
            "scriptId": normalized_script_id,
            "sourceType": normalized_source_type,
            "targetType": normalized_target_type,
            "journal": committed_journal,
        }

    @_script_config_write(
        script_id_argument="script_id",
        owner_reentrant=True,
    )
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

    @_script_config_write(script_id_argument="script_id")
    async def del_script(self, script_id: str) -> str:
        """删除脚本配置并返回提交前解析出的脚本类型键。"""

        logger.info(f"删除脚本配置: {script_id}")

        uid = uuid.UUID(script_id)

        reservation_owner = self._script_execution_reservations.get(str(uid))
        if reservation_owner is not None:
            raise RuntimeError(
                "脚本正在启动或运行，无法删除: "
                f"script_id={uid}, owner={reservation_owner}"
            )
        if self.ScriptConfig[uid].is_locked:
            raise RuntimeError(f"脚本 {script_id} 正在运行, 无法删除")

        # 读取类型必须位于同一写作用域内；调用方据此决定删除后的资源回收，
        # 不能在取得写锁前通过 get_script_records() 预读，否则换型或删除会造成 TOCTOU。
        deleted_type = self._resolve_record_provider(self.ScriptConfig[uid]).type_key

        # 删除脚本相关的队列项
        for queue in self.QueueConfig.values():
            for key, value in queue.QueueItem.items():
                if value.get("Info", "ScriptId") == str(uid):
                    await queue.QueueItem.remove(key)

        await self.ScriptConfig.remove(uid)
        data_path = Path.cwd() / f"data/{uid}"
        if data_path.exists():
            # Keep recursive deletion off the event loop. Project checkouts
            # and user snapshots can be large on Windows, making the UI look
            # frozen while the filesystem walk releases file handles.
            await _run_to_thread_with_cancellation_drain(
                shutil.rmtree,
                data_path,
            )
        return deleted_type

    @_script_config_write()
    async def reorder_script(self, index_list: list[str]) -> None:
        """重新排序脚本"""

        logger.info(f"重新排序脚本: {index_list}")

        await self.ScriptConfig.setOrder([uuid.UUID(_) for _ in index_list])

    @_script_config_write(script_id_argument="script_id")
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

    @_script_config_write(script_id_argument="script_id")
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

    @_script_config_write(
        script_id_argument="script_id",
        owner_reentrant=True,
    )
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

    @_script_config_write(
        script_id_argument="script_id",
        owner_reentrant=True,
    )
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

    @_script_config_write(script_id_argument="script_id")
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

    @_script_config_write(
        script_id_argument="script_id",
        owner_reentrant=True,
    )
    async def del_user(self, script_id: str, user_id: str) -> None:
        """删除用户配置"""

        logger.info(f"{script_id} 删除用户配置: {user_id}")

        script_uid = uuid.UUID(script_id)
        user_uid = uuid.UUID(user_id)

        await self.ScriptConfig[script_uid].UserData.remove(user_uid)
        if (Path.cwd() / f"data/{script_id}/{user_id}").exists():
            shutil.rmtree(Path.cwd() / f"data/{script_id}/{user_id}")

    @_script_config_write(script_id_argument="script_id")
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

    @staticmethod
    def _provider_is_creatable(provider: Any) -> bool:
        """判断脚本类型 provider 是否允许用户创建。"""

        return provider.metadata.get("creatable", True) is not False

    @classmethod
    def _require_provider_available(cls, provider: Any, action: str) -> None:
        """阻止对未启用脚本类型执行写操作。"""

        if cls._provider_is_available(provider):
            return
        raise RuntimeError(f"脚本类型 {provider.type_key} 当前未启用，无法{action}")

    @classmethod
    def _require_provider_creatable(cls, provider: Any) -> None:
        """阻止通过通用创建入口新增内部脚本类型。"""

        if cls._provider_is_creatable(provider):
            return
        raise RuntimeError(f"脚本类型 {provider.type_key} 不支持直接创建")

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
            try:
                uid = uuid.UUID(script_id)
                config = self.ScriptConfig[uid]
            except (ValueError, KeyError):
                return []
            script_pairs = [(uid, config)]

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

    @_script_config_write(script_id_argument="script_id")
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

    async def get_maa_depot_items(self, script_id: str) -> list[dict[str, str]]:
        """获取 MAA 库存保持物品选项。"""

        script_config = self.ScriptConfig[uuid.UUID(script_id)]
        if not isinstance(script_config, MaaConfig):
            raise TypeError(f"脚本 {script_id} 不是 MAA 脚本")

        item_index_path = (
            Path(script_config.get("Info", "Path")) / "resource" / "item_index.json"
        )
        if not item_index_path.exists():
            raise FileNotFoundError(
                f"未找到 MAA 物品资源: {item_index_path}，请更新 MAA 后重试"
            )

        items = json.loads(item_index_path.read_text(encoding="utf-8"))
        return [
            {"label": item.get("name") or item_id, "value": item_id}
            for item_id, item in sorted(
                (
                    (item_id, item)
                    for item_id, item in items.items()
                    if item_id.isdigit()
                    and item_id not in MAA_DEPOT_EXCLUDED_ITEM_IDS
                    and isinstance(item, dict)
                ),
                key=lambda entry: int(entry[0]),
            )
        ]

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

    @_script_config_write()
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

    @_script_config_write()
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
                await self.QueueConfig[queue_uid].set(group, name, value)

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
                await (
                    self.QueueConfig[queue_uid]
                    .TimeSet[time_set_uid]
                    .set(group, name, value)
                )

    async def del_time_set(self, queue_id: str, time_set_id: str) -> None:
        """删除时间设置配置"""

        logger.info(f"{queue_id} 删除时间设置配置: {time_set_id}")

        queue_uid = uuid.UUID(queue_id)
        time_set_uid = uuid.UUID(time_set_id)

        await self.QueueConfig[queue_uid].TimeSet.remove(time_set_uid)

    async def reorder_time_set(self, queue_id: str, index_list: list[str]) -> None:
        """重新排序时间设置"""

        logger.info(f"{queue_id} 重新排序时间设置: {index_list}")

        queue_uid = uuid.UUID(queue_id)

        await self.QueueConfig[queue_uid].TimeSet.setOrder(
            list(map(uuid.UUID, index_list))
        )

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
                await (
                    self.QueueConfig[queue_uid]
                    .QueueItem[queue_item_uid]
                    .set(group, name, value)
                )

    async def del_queue_item(self, queue_id: str, queue_item_id: str) -> None:
        """删除队列项配置"""

        logger.info(f"{queue_id} 删除队列项配置: {queue_item_id}")

        queue_uid = uuid.UUID(queue_id)
        queue_item_uid = uuid.UUID(queue_item_id)

        await self.QueueConfig[queue_uid].QueueItem.remove(queue_item_uid)

    async def reorder_queue_item(self, queue_id: str, index_list: list[str]) -> None:
        """重新排序队列项"""

        logger.info(f"{queue_id} 重新排序队列项: {index_list}")

        queue_uid = uuid.UUID(queue_id)

        await self.QueueConfig[queue_uid].QueueItem.setOrder(
            list(map(uuid.UUID, index_list))
        )

    async def get_tools(self) -> Dict[str, Any]:
        """获取工具设置"""

        logger.debug("获取工具设置")

        today = datetime.now().strftime("%Y-%m-%d")
        if self._game_sign_result_date != today:
            self.ToolsConfig._game_sign_result_data = {}
            self._game_sign_result_date = today

        return await self.ToolsConfig.toDict()

    async def update_game_sign_results(
        self, formatted: dict[str, Any], *, replace: bool = False
    ) -> None:
        """合并、持久化并广播游戏签到结果。

        Args:
            formatted: 已按平台和账号分组的签到结果。
            replace: 是否按账号 UID 替换已有结果。
        """

        from app.tools.game_sign import merge_sign_results

        today = datetime.now().strftime("%Y-%m-%d")
        existing = (
            self.ToolsConfig._game_sign_result_data
            if self._game_sign_result_date == today
            else {}
        )
        result = merge_sign_results(existing, formatted, replace=replace)
        self.ToolsConfig._game_sign_result_data = result
        self._game_sign_result_date = today
        _save_game_sign_result_snapshot(
            self.config_path / GAME_SIGN_RESULT_FILENAME,
            result,
            result_date=today,
        )

        try:
            await self.send_websocket_message(
                id="GameSign",
                type="Update",
                data={"Result": json.dumps(result, ensure_ascii=False)},
            )
        except Exception as e:
            logger.warning(f"广播游戏签到结果失败: {e}")

    async def update_tools(self, data: Dict[str, Dict[str, Any]]) -> None:
        """更新工具设置"""

        logger.info("更新工具设置")

        for group, items in data.items():
            for name, value in items.items():
                await self.ToolsConfig.set(group, name, value)

        logger.success("工具设置更新成功")

    # ==================== 游戏签到账号组 CRUD ====================

    async def get_game_sign_accounts(
        self, *, if_decrypt: bool = True
    ) -> Dict[str, Any]:
        """获取所有游戏签到账号组"""

        logger.debug("获取所有游戏签到账号组")

        return await self.ToolsConfig.GameSign_Accounts.toDict(
            if_decrypt=if_decrypt
        )

    async def add_game_sign_account(self) -> tuple[uuid.UUID, Any]:
        """添加游戏签到账号组"""

        logger.info("添加游戏签到账号组")

        uid, config = await self.ToolsConfig.GameSign_Accounts.add(
            GameSignAccountGroup
        )
        return uid, config

    async def get_game_sign_account(
        self, account_id: str, *, if_decrypt: bool = True
    ) -> Dict[str, Any]:
        """获取游戏签到账号组详情"""

        logger.debug(f"获取游戏签到账号组: {account_id}")

        account_uid = uuid.UUID(account_id)
        return await self.ToolsConfig.GameSign_Accounts[account_uid].toDict(
            if_decrypt=if_decrypt
        )

    def _clear_game_sign_account_results(self, account_id: str) -> None:
        """清除指定游戏签到账号的结果。"""

        today = datetime.now().strftime("%Y-%m-%d")
        result = self.ToolsConfig._game_sign_result_data
        if getattr(self, "_game_sign_result_date", today) != today:
            result.clear()
            self._game_sign_result_date = today

        for platform in list(result):
            result[platform] = [
                group
                for group in result[platform]
                if group.get("account_uid") != account_id
            ]
            if not result[platform]:
                del result[platform]

        tools_file = getattr(self.ToolsConfig, "file", None)
        snapshot_path = (
            tools_file.with_name(GAME_SIGN_RESULT_FILENAME)
            if isinstance(tools_file, Path)
            else None
        )
        _save_game_sign_result_snapshot(
            snapshot_path,
            result,
            result_date=today,
        )

    async def update_game_sign_account(
        self, account_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新游戏签到账号组配置"""

        logger.info(f"更新游戏签到账号组: {account_id}")

        account_uid = uuid.UUID(account_id)
        account = self.ToolsConfig.GameSign_Accounts[account_uid]
        credential_fields = {"MiyousheToken", "KuroToken", "SklandToken"}
        credential_changed = False

        for group, items in data.items():
            for name, value in items.items():
                if (
                    group == "GameSignAccount"
                    and name in credential_fields
                    and account.get(group, name) != value
                ):
                    credential_changed = True
                await account.set(group, name, value)

        if credential_changed:
            await account.set("GameSignAccount", "LastSignDate", "2000-01-01")
            self._clear_game_sign_account_results(account_id)

    async def delete_game_sign_account(self, account_id: str) -> None:
        """删除游戏签到账号组"""

        logger.info(f"删除游戏签到账号组: {account_id}")

        account_uid = uuid.UUID(account_id)
        await self.ToolsConfig.GameSign_Accounts.remove(account_uid)
        self._clear_game_sign_account_results(account_id)

    async def reorder_game_sign_accounts(self, order: list[str]) -> None:
        """调整游戏签到账号组顺序"""

        logger.info("调整游戏签到账号组顺序")

        await self.ToolsConfig.GameSign_Accounts.setOrder(
            [uuid.UUID(_) for _ in order]
        )

    async def get_setting(self) -> Dict[str, Any]:
        """获取全局设置"""

        logger.info("获取全局设置")

        return await self.toDict()

    async def update_setting(self, data: Dict[str, Dict[str, Any]]) -> None:
        """更新全局设置"""

        logger.info("更新全局设置")

        for group, items in data.items():
            for name, value in items.items():
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

    @_script_config_write(script_id_argument="script_id")
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

    @_script_config_write(script_id_argument="script_id")
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
                    await self.Notify_CustomWebhooks[webhook_uid].set(
                        group, name, value
                    )

        else:
            logger.info(f"更新 webhook 配置: {script_id} - {user_id} - {webhook_id}")

            script_uid = uuid.UUID(script_id)
            user_uid = uuid.UUID(user_id)

            for group, items in data.items():
                for name, value in items.items():
                    await (
                        self.ScriptConfig[script_uid]
                        .UserData[user_uid]
                        .Notify_CustomWebhooks[webhook_uid]
                        .set(group, name, value)
                    )

    @_script_config_write(script_id_argument="script_id")
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

    @_script_config_write(script_id_argument="script_id")
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

    async def get_proxy_overview(self) -> Dict[str, Any]:
        """获取代理情况概览信息"""

        logger.info("获取代理情况概览信息")

        history_index = await self.search_history(
            "DAILY", datetime.now(tz=UTC4).date(), datetime.now(tz=UTC4).date()
        )
        if datetime.now(tz=UTC4).strftime("%Y-%m-%d") not in history_index:
            return {}
        history_data = {
            k: await self.merge_statistic_info(v)
            for k, v in history_index[
                datetime.now(tz=UTC4).strftime("%Y-%m-%d")
            ].items()
        }
        overview = {}
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

    async def save_maa_log(self, log_path: Path, logs: list, maa_result: str) -> bool:
        """
        保存MAA日志并生成对应统计数据

        Args:
            log_path (Path): 日志文件保存路径
            logs (list): 日志列表
            maa_result (str): MAA任务结果
        Returns:
            bool: 是否存在高资
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
            if "开始任务: Fight" in line or "开始任务: 理智作战" in line:
                # 查找对应的任务结束位置
                end_index = -1
                for j in range(i + 1, len(logs)):
                    if "完成任务: Fight" in logs[j] or "完成任务: 理智作战" in logs[j]:
                        end_index = j
                        break
                    # 如果遇到新的Fight任务开始, 则当前任务没有正常结束
                    if j < len(logs) and (
                        "开始任务: Fight" in logs[j] or "开始任务: 理智作战" in logs[j]
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
                drop_match = re.search(r"([\u4e00-\u9fffA-Za-z0-9\-]+) 掉落统计:", line)
                if drop_match:
                    # 发现新的掉落统计, 重置当前关卡的掉落数据
                    current_stage = drop_match.group(1)
                    last_drop_stats = {}
                    continue

                # 如果已经找到了关卡, 处理掉落物
                if current_stage:
                    item_match: List[str] = re.findall(
                        r"^(?!\[)(\S+?)\s*:\s*([\d,]+[kK]?)(?:\s*\(\+[\d,]+[kK]?\))?",
                        line,
                        re.M,
                    )
                    for item, total in item_match:
                        total = total.replace(",", "")
                        if total.lower().endswith("k"):
                            total = int(total[:-1]) * 1000
                        else:
                            total = int(total)

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
        log_path.write_text("".join(logs), encoding="utf-8")
        # 保存统计数据
        log_path.with_suffix(".json").write_text(
            json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8"
        )

        logger.success(f"MAA 日志统计完成, 日志路径: {log_path}")

        return if_six_star

    def parse_maaend_failed_tasks(self, logs: list[str]) -> List[str]:
        """
        解析MaaEnd失败任务名称

        Args:
            logs (list[str]): 日志列表

        Returns:
            List[str]: 失败任务名称列表
        """

        failed_tasks: List[str] = []
        ignored_tasks = {"停止任务", "⛔ 结束进程", "__MXU_KILLPROC__", "StopTask"}

        for log_line in logs:
            match = re.search(r"任务失败:\s*(.+)", log_line)
            if match is None:
                continue

            task_name = match.group(1).strip()
            if (
                task_name
                and task_name not in ignored_tasks
                and task_name not in failed_tasks
            ):
                failed_tasks.append(task_name)

        return failed_tasks

    def parse_maaend_matrix_statistics(
        self, logs: list[str]
    ) -> tuple[Optional[Dict[str, str]], bool]:
        """
        解析MaaEnd基质刷取统计

        Args:
            logs (list[str]): 日志列表

        Returns:
            tuple[Optional[Dict[str, str]], bool]: 基质统计数据与是否识别到基质流程
        """

        matrix_statistics: Dict[str, str] = {}
        pending_statistics: Dict[str, str] = {}
        current_matrix_skill = ""
        has_matrix_flow = False
        locked_count = 0

        for log_line in logs:
            skill_match = re.search(r"OCR到技能：(.+)", log_line)
            if skill_match:
                current_matrix_skill = skill_match.group(1).strip()
                continue

            weapon_match = re.search(r"匹配到武器：(.+)", log_line)
            if weapon_match and current_matrix_skill:
                pending_statistics[current_matrix_skill] = (
                    weapon_match.group(1).strip()
                )
                current_matrix_skill = ""
                continue

            completed_match = re.search(
                r"筛选完成！共历遍物品：\d+[，,]\s*确认锁定物品：(\d+)",
                log_line,
            )
            if completed_match is None:
                continue

            has_matrix_flow = True
            current_locked_count = int(completed_match.group(1))
            locked_count += current_locked_count
            if current_locked_count > 0:
                matched_items = list(pending_statistics.items())[
                    -current_locked_count:
                ]
                matrix_statistics.update(matched_items)

            pending_statistics = {}
            current_matrix_skill = ""

        if not has_matrix_flow:
            return None, False

        if locked_count == 0:
            return {}, True

        return (matrix_statistics or None), True

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

        logger.info(
            f"开始处理MaaEnd日志, 日志长度: {len(logs)}, 日志标记: {maaend_result}"
        )

        failed_tasks = self.parse_maaend_failed_tasks(logs)
        matrix_statistics, has_matrix_flow = self.parse_maaend_matrix_statistics(logs)

        if maaend_result == "MaaEnd 部分任务执行失败" and failed_tasks:
            maaend_result = f"{maaend_result}: {'、'.join(failed_tasks)}"

        data: Dict[str, Any] = {"maaend_result": maaend_result}
        if has_matrix_flow and matrix_statistics is not None:
            data["matrix_statistics"] = matrix_statistics

        # 保存日志
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.with_suffix(".log").write_text("".join(logs), encoding="utf-8")
        log_path.with_suffix(".json").write_text(
            json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8"
        )

        logger.success(f"MaaEnd日志统计完成, 日志路径: {log_path.with_suffix('.log')}")

    async def save_src_log(self, log_path: Path, logs: list, src_result: str) -> None:
        """
        保存SRC日志并生成对应统计数据

        Args:
            log_path (Path): 日志文件保存路径
            logs (list): 日志内容列表
            src_result (str): 待保存的日志结果信息
        """

        logger.info(f"开始处理SRC日志, 日志长度: {len(logs)}, 日志标记: {src_result}")

        data: Dict[str, str] = {"src_result": src_result}

        # 保存日志
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.with_suffix(".log").write_text("".join(logs), encoding="utf-8")
        log_path.with_suffix(".json").write_text(
            json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8"
        )

        logger.success(f"SRC日志统计完成, 日志路径: {log_path.with_suffix('.log')}")

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
        log_path.with_suffix(".log").write_text("".join(logs), encoding="utf-8")
        log_path.with_suffix(".json").write_text(
            json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8"
        )

        logger.success(f"通用日志统计完成, 日志路径: {log_path.with_suffix('.log')}")

    async def merge_statistic_info(self, statistic_path_list: List[Path]) -> dict:
        """
        合并指定数据统计信息文件

        Args:
            statistic_path_list (List[Path]): 数据统计信息文件列表

        Returns:
            dict: 合并后的数据统计信息
        """

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

                # 合并基质统计
                elif key == "matrix_statistics":
                    for skill, weapon in single_data[key].items():
                        data[key][skill] = weapon

                # 处理理智相关字段 - 使用最后一个文件的值
                elif key in ["sanity", "sanity_full_at"]:
                    data[key] = single_data[key]

                # 录入运行结果
                elif key in [
                    "maa_result",
                    "maaend_result",
                    "src_result",
                    "general_result",
                ]:
                    actual_date = (
                        datetime.strptime(
                            f"{json_file.parent.parent.name} {json_file.stem}",
                            "%Y-%m-%d %H-%M-%S",
                        )
                        .replace(tzinfo=UTC4)
                        .astimezone()
                    )

                    success = single_data[key] == "Success!"

                    if not success:
                        if "error_info" not in data:
                            data["error_info"] = {}
                        data["error_info"][
                            actual_date.strftime("%Y-%m-%d %H:%M:%S")
                        ] = single_data[key]

                    data["index"][actual_date] = {
                        "date": actual_date.strftime("%Y-%m-%d %H:%M:%S"),
                        "status": "DONE" if success else "ERROR",
                        "jsonFile": str(json_file),
                    }

        data["index"] = [data["index"][_] for _ in sorted(data["index"])]

        # 确保返回的字典始终包含 index 字段，即使为空
        result = {
            k: v
            for k, v in data.items()
            if v or (k == "matrix_statistics" and isinstance(v, dict))
        }
        if "index" not in result:
            result["index"] = []

        return result

    async def search_history(
        self,
        mode: Literal["DAILY", "WEEKLY", "MONTHLY"],
        start_date: date,
        end_date: date,
    ) -> dict:
        """
        搜索指定时间范围内的历史记录

        Args:
            mode (Literal["DAILY", "WEEKLY", "MONTHLY"]): 合并模式
            start_date (date): 开始日期
            end_date (date): 结束日期
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

                if mode == "DAILY":
                    date_name = date.strftime("%Y-%m-%d")
                elif mode == "WEEKLY":
                    date_name = date.strftime("%G-W%V")
                elif mode == "MONTHLY":
                    date_name = date.strftime("%Y-%m")
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
                logger.exception(f"非日期格式的目录: {date_folder}")

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
                    logger.debug(f"已删除超期日志目录: {date_folder}")
            except ValueError:
                logger.warning(f"非日期格式的目录: {date_folder}")

        logger.success(f"清理完成: {deleted_count} 个日期目录")


Config = AppConfig()
