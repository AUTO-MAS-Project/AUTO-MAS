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
import asyncio
import inspect
import json
import os
import shutil
import sqlite3
import sys
import time
import uuid
from collections.abc import Callable
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Literal,
    Optional,
    cast,
)

import httpx
import truststore

# 仅用于类型标注的顶层依赖移到 TYPE_CHECKING，避免启动导入开销
if TYPE_CHECKING:
    import uvicorn

    from app.config import ConfigEntry
    from app.models.task import ScriptTaskResources
    from app.utils.common.config import restore as _utils_config_restore

from app.config import ConfigCollection, ConfigEntry, NodeState, config_manager
from app.core.config.upgrade import (
    CONFIG_FILES,
    LegacyEntryMigrations,
    contains_legacy_type,
    convert_legacy,
    is_blank_file,
    preserve_pre_upgrade,
    upgrade_json_configs,
)
from app.models.config import (
    CLASS_BOOK,
    PLAN_BOOK,
    BAAHConfig,
    BAAHPlanConfig,
    BAAHUserConfig,
    BetterGIConfig,
    BetterGIUserConfig,
    EmulatorConfig,
    GameSignAccountGroup,
    GeneralConfig,
    GeneralUserConfig,
    GlobalConfig,
    HSRConfig,
    HSRUserConfig,
    M9AConfig,
    M9AUserConfig,
    MaaConfig,
    MaaEndConfig,
    MaaEndPlanConfig,
    MaaEndUserConfig,
    MaaFWConfig,
    MaaFWUserConfig,
    MaaPlanConfig,
    MaaUserConfig,
    MSSConfig,
    MSSPlanConfig,
    MSSUserConfig,
    OkNteConfig,
    OkNteUserConfig,
    OkwwConfig,
    OkwwUserConfig,
    QueueConfig,
    QueueItem,
    SrcConfig,
    SrcUserConfig,
    TimeSet,
    Webhook,
    WhimboxConfig,
    WhimboxUserConfig,
    ZzzOdConfig,
    ZzzOdUserConfig,
)
from app.models.schema import PlanComboxConsumer
from app.models.script_contracts import ScriptConfigHandler
from app.task.M9A.migration import (
    migrate_legacy_m9a_scripts,
    normalize_m9a_managed_entries,
    repair_m9a_migration_losses,
)
from app.utils import constants as _utils_constants
from app.utils import get_logger, is_supervised
from app.utils import io as _utils_io

# 各专项失败诊断目录里参与保留期清理的文件后缀（诊断日志与截图）；
# 不在集合内的文件（如未来的标记/锁文件）不被自动清理触碰
DIAGNOSTIC_FILE_SUFFIXES = frozenset({".log", ".png", ".jpg"})
# 失败截图后缀（旧专项存量 PNG 与现行 JPEG 同口径）
DIAGNOSTIC_SCREENSHOT_SUFFIXES = frozenset({".png", ".jpg"})
# 单个诊断目录的失败截图总量上限，超出后按时间从旧到新回收；
# 每目录独立结算，一个专项的截图风暴不会挤掉其他专项的证据
DIAGNOSTIC_SCREENSHOT_MAX_BYTES = 10 * 1024 * 1024
# 诊断文件的统一保留天数：诊断文件不是用户数据，用固定保留期兜住无界
# 累积，不跟随历史记录保留时间设置
DIAGNOSTIC_RETENTION_DAYS = 15

#: 本进程启动时刻；启动清理只碰比它更早的半成品。
_PROCESS_STARTED_AT = time.time()

logger = get_logger("配置管理")

GAME_SIGN_RESULT_FILENAME = "GameSignResult.json"


def _load_game_sign_result_snapshot(path: Path, *, result_date: str) -> dict[str, Any]:
    """读取当天的游戏社区结果快照。"""

    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"读取游戏社区结果快照失败: {e}")
        return {}

    if not isinstance(payload, dict) or payload.get("date") != result_date:
        return {}

    result = payload.get("result")
    if not isinstance(result, dict):
        logger.warning("游戏社区结果快照格式无效，已忽略")
        return {}
    return result


def _save_game_sign_result_snapshot(
    path: Path | None, result: dict[str, Any], *, result_date: str
) -> None:
    """原子保存游戏社区结果快照（走 ``app.utils.common.io.write_file``）。"""

    if path is None:
        return

    try:
        _utils_io.write_file(path, {"date": result_date, "result": result})
    except (OSError, TypeError, ValueError) as e:
        logger.warning(f"保存游戏社区结果快照失败: {e}")


_PROXY_URL_SCHEMES = ("http://", "https://", "socks5://", "socks5h://", "socks4://")


def normalize_proxy_address(raw: str | None) -> str | None:
    """把 ``Update.ProxyAddress`` 规范成带协议的代理地址字符串。

    去首尾空白，空 → ``None``；没有协议前缀时补 ``http://``；``user:pw@`` 原样保留
    ——这是要写进子进程 ``HTTP_PROXY`` 的字符串，不是 ``httpx.Proxy``（后者会把
    userinfo 剥到 ``.auth``，``str(proxy.url)`` 会丢凭据）。
    """

    text = str(raw or "").strip()
    if not text:
        return None
    if not text.lower().startswith(_PROXY_URL_SCHEMES):
        text = f"http://{text}"
    return text


def _clear_legacy_history() -> None:
    """清理旧版历史存储的目录、升级标记和整数主键数据库。"""

    for path in (Path.cwd() / "history", Path.cwd() / "data/replays"):
        if path.exists():
            shutil.rmtree(path)
    (Path.cwd() / "data/history-storage.json").unlink(missing_ok=True)
    for name in (
        "data/history.db",
        "data/history.db-journal",
        "data/history.db-shm",
        "data/history.db-wal",
    ):
        (Path.cwd() / name).unlink(missing_ok=True)


class QueueNotFoundError(LookupError):
    """查询的调度队列已不存在。"""


class QueueItemNotFoundError(LookupError):
    """查询的队列项已不存在。"""


class AppConfig:
    VERSION = "v5.8.0-beta.2"

    def __init__(self) -> None:

        # Runtime 的用户目录与源码目录分离：资源随源码更新，用户文件留在工作目录。
        self.work_path = Path.cwd()
        self.source_path = Path(__file__).resolve().parents[3]
        self.resource_path = self.source_path / "res"
        self.config_path = self.work_path / "config"
        self.data_path = self.work_path / "data"
        self.debug_path = self.work_path / "debug"
        self.history_path = self.work_path / "history"
        self.script_path = self.work_path / "script"
        self.plugins_path = self.work_path / "plugins"
        self.install_path = (
            Path(sys.executable).parent
            if getattr(sys, "frozen", False)
            else self.work_path
        )

        self._script_config_handlers: dict[
            type[ConfigEntry], ScriptConfigHandler | None
        ] = {}
        self._restore_pool_resolver: (
            Callable[["ConfigEntry"], list["_utils_config_restore.ConfigRestorePool"]]
            | None
        ) = None

        logger.info("")
        logger.info("===================================")
        logger.info("AUTO-MAS 后端应用程序")
        logger.info(f"版本号:  {self.VERSION}")
        logger.info(f"工作目录:  {self.work_path}")
        logger.info("===================================")

        self.log_path = self.debug_path / "app.log"
        self.database_path = self.data_path / "data.db"
        # 检查目录
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.mkdir(parents=True, exist_ok=True)

        # 所有集合先登记，随后按引用依赖激活；迁移完成前不登记持久化根。
        self.setting = GlobalConfig.build()
        self.EmulatorConfig = ConfigCollection.build(
            [EmulatorConfig], name="EmulatorConfig"
        )
        self.PlanConfig = ConfigCollection.build(
            [item["config_class"] for item in PLAN_BOOK.values()], name="PlanConfig"
        )
        self.ScriptConfig = ConfigCollection.build(
            list(CLASS_BOOK.values()), name="ScriptConfig"
        )
        self.QueueConfig = ConfigCollection.build([QueueConfig], name="QueueConfig")
        from app.models.config import ToolsConfig

        self.ToolsConfig = ToolsConfig.build()
        self.startup_notices = self.setting.startup_notices
        self._config_nodes = {
            "setting": self.setting,
            "EmulatorConfig": self.EmulatorConfig,
            "PlanConfig": self.PlanConfig,
            "ScriptConfig": self.ScriptConfig,
            "QueueConfig": self.QueueConfig,
            "ToolsConfig": self.ToolsConfig,
            "GameSignAccounts": self.ToolsConfig.GameSign_Accounts,
        }
        self._m9a_migration = None
        self._m9a_repair = None
        self._m9a_managed = None
        # ACTIVE 也可能是部分激活的结果；只有加载成功返回后才允许按引用回收。
        self._script_configs_loaded = False
        from app.task.MaaFW.tools.embedded.maintenance import MaaFWMaintenanceService

        self.maafw_maintenance = MaaFWMaintenanceService(
            script_configs=lambda: tuple(
                (str(uid), config) for uid, config in self.ScriptConfig.data.items()
            ),
            scripts_loaded_intact=self.script_config_loaded_intact,
            retention_days=lambda: self.setting.Function.HistoryRetentionTime,
            process_started_at=_PROCESS_STARTED_AT,
        )
        for model in (
            *CLASS_BOOK.values(),
            MaaUserConfig,
            MaaEndUserConfig,
            BAAHUserConfig,
            MSSUserConfig,
            HSRUserConfig,
            QueueItem,
        ):
            if hasattr(model, "related_config"):
                model.related_config.update(
                    {
                        "EmulatorConfig": self.EmulatorConfig,
                        "PlanConfig": self.PlanConfig,
                        "ScriptConfig": self.ScriptConfig,
                    }
                )

        # Git 仓库延迟初始化，避免启动时导入 GitPython
        self._repo: Any = None
        self._repo_initialized = False

        self.server: Optional["uvicorn.Server"] = None
        self.power_sign: Literal[
            "NoAction",
            "Shutdown",
            "ShutdownForce",
            "Reboot",
            "Hibernate",
            "Sleep",
            "KillSelf",
            "RestartSelf",
            "Logoff",
        ] = "NoAction"
        # 电源操作前的静默延时秒数, 与 power_sign 一同由队列配置写入
        self.power_delay: int = 0
        self.temp_task: List[asyncio.Task] = []
        # 正在循环运行的队列，供配置改动前的安全检查使用
        self.running_cycle_queue_ids: set[uuid.UUID] = set()
        self._game_sign_result_date = ""
        self._community_account_add_lock = asyncio.Lock()

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

        # 缓存 SSL 上下文：httpx 为每个 AsyncClient 都调用 create_default_context()，
        # truststore 场景下会全量加载 Windows 证书库（实测一次 5~15s，且发生在
        # 事件循环上时冻结全部请求）。按参数缓存后全程只加载一次，
        # 首次加载由启动预热线程完成，见 main.py。
        _original_create_default_context = ssl.create_default_context
        _ssl_context_cache: dict[tuple, ssl.SSLContext] = {}

        def _cached_create_default_context(
            *args: object, **kwargs: object
        ) -> ssl.SSLContext:
            key = (args, tuple(sorted(kwargs.items())))
            context = _ssl_context_cache.get(key)
            if context is None:
                context = _original_create_default_context(*args, **kwargs)
                _ssl_context_cache[key] = context
            return context

        ssl.create_default_context = _cached_create_default_context

    def _get_repo(self) -> Any:
        """惰性初始化 Git 仓库，避免启动时导入 GitPython。"""
        if not self._repo_initialized:
            self._repo_initialized = True
            if (self.work_path / "environment/git/bin/git.exe").exists():
                os.environ["GIT_PYTHON_GIT_EXECUTABLE"] = str(
                    self.work_path / "environment/git/bin/git.exe"
                )
            try:
                from git import Repo

                # .git 随源码走：受 AUTO-MAS-Runtime 监督时源码在 <app-root>/repo/，
                # 工作目录（app-root）下没有仓库，不能再按 Path.cwd() 打开
                self._repo = Repo(self.source_path)
            except Exception as e:
                logger.warning(f"Git仓库初始化失败: {e}")
                self._repo = None
        return self._repo

    async def init_config(self) -> None:
        """初始化配置管理"""

        await self.check_data()
        # 配置已按依赖激活；存量 MAA 的更新接管仅迁移一次。
        for script in self.ScriptConfig.values():
            if isinstance(script, MaaConfig) and await script.migrate_update_takeover(
                global_cdk=str(self.setting.Update.MirrorChyanCDK or "")
            ):
                logger.info("MAA 更新接管迁移：已为配置 CDK 的旧脚本开启接管")
            if (
                isinstance(script, MaaConfig)
                and not script.Update.ChannelMigrationVersion
            ):
                from app.task.MAA.tools.software_update import (
                    migrate_maa_update_channel,
                )

                await migrate_maa_update_channel(script)
        if self._m9a_migration is not None:
            if self._m9a_migration.changed or self._m9a_migration.failure:
                await self._settle_m9a_migration(self._m9a_migration)
        for result in (self._m9a_repair, self._m9a_managed):
            if result is not None and result.needs_notice:
                self.startup_notices.append(result.notice())

        # 游戏社区：恢复当天的结果快照，跨日结果不继续展示
        today = datetime.now(tz=_utils_constants.UTC8).strftime("%Y-%m-%d")
        self.ToolsConfig._game_sign_result_data = _load_game_sign_result_snapshot(
            self.config_path / GAME_SIGN_RESULT_FILENAME,
            result_date=today,
        )
        self._game_sign_result_date = today

        from app.services import System
        from app.services import telemetry as _service_telemetry

        async def on_self_start(sender, event):
            await System.set_SelfStart(event.value)

        async def on_allow_sleep(sender, event):
            await System.set_Sleep(event.value)

        def on_telemetry(sender, event):
            _service_telemetry.set_telemetry_enabled(event.value)

        async def on_video_limit(sender, event):
            from app.core import History

            try:
                report = await History.set_video_limit(
                    limit_bytes=event.value * 1024 * 1024
                )
                for issue in report.errors:
                    logger.warning(f"历史视频容量维护失败：{issue.message}")
            except Exception as error:
                logger.opt(exception=True).warning(f"历史视频容量维护失败：{error}")

        # connect 默认弱引用，配置管理器持有回调直至应用退出。
        self._config_receivers = (
            on_self_start,
            on_allow_sleep,
            on_telemetry,
            on_video_limit,
        )
        self.setting.connect(
            on_self_start, phase="runtime", group="Start", field="IfSelfStart"
        )
        self.setting.connect(
            on_allow_sleep, phase="runtime", group="Function", field="IfAllowSleep"
        )
        self.setting.connect(
            on_telemetry, phase="runtime", group="Function", field="IfEnableTelemetry"
        )
        self.setting.connect(
            on_video_limit,
            phase="runtime",
            group="Replay",
            field="VideoStorageLimitMiB",
        )

        from app.core import Community

        Community.connect_community_activity_cache(
            self.ToolsConfig, setting=self.setting
        )
        # 注册自启动会读写注册表, 不阻塞初始化; 持有引用避免被 GC 且异常不被静默吞掉
        self_start_task = asyncio.create_task(
            System.set_SelfStart(self.setting.Start.IfSelfStart)
        )
        self.temp_task.append(self_start_task)

        def _self_start_done(t: asyncio.Task) -> None:
            if t in self.temp_task:
                self.temp_task.remove(t)
            if not t.cancelled() and t.exception() is not None:
                logger.warning(f"设置开机自启动失败: {t.exception()}")

        self_start_task.add_done_callback(_self_start_done)
        await System.set_Sleep(self.setting.Function.IfAllowSleep)
        _service_telemetry.set_telemetry_enabled(
            self.setting.Function.IfEnableTelemetry
        )

        self.loop = asyncio.get_running_loop()

        logger.info("程序初始化完成")

    async def check_data(self) -> None:
        """历史升级按段提交；v1.11→v2.0 须全部配置激活并落盘后推进。

        后续迁移失败不回退已完成的历史版本，下次从该检查点及逐文件记录继续。
        """
        if self.database_path.exists():
            with closing(sqlite3.connect(self.database_path)) as database:
                version = database.execute("SELECT v FROM version").fetchone()[0]
        else:
            version = "v1.11"
        if version not in {
            "v1.7",
            "v1.8",
            "v1.9",
            "v1.10",
            "v1.11",
            "v2.0",
            "v2.1",
        }:
            raise ValueError(f"不支持的数据版本：{version}，配置文件未迁移")
        if version not in {"v2.0", "v2.1"}:
            await asyncio.to_thread(preserve_pre_upgrade, self.config_path)
            await self._upgrade_legacy_data()
            if self.setting.activation_state == NodeState.INACTIVE:
                source = self.config_path / "Config.json"
                if source.exists() and not is_blank_file(source):
                    # 空白主配置没有可迁数据，跳过转换；随后统一升级会按默认
                    # 配置生成 setting.yaml 并照常归档，激活走下方统一分支。

                    self.setting = GlobalConfig.build(
                        payload=convert_legacy(
                            _utils_io.read_dict_file(source), self.setting
                        )
                    )
                    self._config_nodes["setting"] = self.setting
                    self.startup_notices = self.setting.startup_notices
                    await self.setting.activate(fast_init=True)

            entry_migrations: LegacyEntryMigrations = {}
            script_path = self.config_path / "ScriptConfig.json"
            if script_path.exists():
                self._m9a_migration = await asyncio.to_thread(
                    migrate_legacy_m9a_scripts,
                    script_path,
                    global_mirror_cdk=str(self.setting.Update.MirrorChyanCDK or ""),
                )
                self._m9a_repair = await asyncio.to_thread(
                    repair_m9a_migration_losses,
                    script_path,
                    skip_uids=set(self._m9a_migration.migrated_uids),
                )
                self._m9a_managed = await asyncio.to_thread(
                    normalize_m9a_managed_entries, script_path
                )
                if await asyncio.to_thread(
                    contains_legacy_type, script_path, HSRConfig.__name__
                ):
                    from app.task.HSR.migration import (
                        archive_legacy_direct_for_upgrade,
                        migrate_legacy_user_payload,
                    )

                    entry_migrations = {HSRUserConfig: migrate_legacy_user_payload}
                    notice = await archive_legacy_direct_for_upgrade(script_path)
                    if notice is not None:
                        self.startup_notices.append(notice)
            prepared = {
                key: await node.to_dict()
                for key, node in self._config_nodes.items()
                if node.activation_state == NodeState.ACTIVE
            }
            await asyncio.to_thread(
                upgrade_json_configs,
                self.config_path,
                self._config_nodes,
                prepared_documents=prepared,
                entry_migrations=entry_migrations,
            )
        if self._m9a_managed is None:
            self._m9a_managed = await asyncio.to_thread(
                normalize_m9a_managed_entries, self.config_path / "scripts.yaml"
            )
        for _old, new, key in CONFIG_FILES:
            config_manager.register_root(
                self._config_nodes[key], self.config_path / new
            )
        for _old, _new, key in CONFIG_FILES:
            node = self._config_nodes[key]
            if node.activation_state == NodeState.INACTIVE:
                await node.activate(fast_init=True)
                if key == "ScriptConfig":
                    self._script_configs_loaded = True
        for script in self.ScriptConfig.values():
            await self._initialize_script_config(script)
        await config_manager.flush()
        if version not in {"v2.0", "v2.1"}:
            # 本次迁移、全部配置激活及最终保存均成功后，才标记 v2.0。
            with closing(sqlite3.connect(self.database_path)) as database:
                database.execute("UPDATE version SET v = ?", ("v2.0",))
                database.commit()
            version = "v2.0"
        if version == "v2.0":
            await asyncio.to_thread(_clear_legacy_history)
            with closing(sqlite3.connect(self.database_path)) as database:
                database.execute("UPDATE version SET v = ?", ("v2.1",))
                database.commit()

    async def _upgrade_legacy_data(self) -> None:
        """沿用历史分段升级策略，每段成功后提交对应版本检查点。"""

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

                if (self.config_path / "QueueConfig").exists():
                    for QueueConfig in (self.config_path / "QueueConfig").glob(
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

                # 仅历史阶段临时使用旧基类。此时新配置尚无持久化根，不能用
                # 新 commit 代替旧 load 的同步保存，再删除来源或推进检查点。
                from app.models.legacy_config import LegacyCollection, LegacyConfig

                legacy_emulators = LegacyCollection()
                legacy_plans = LegacyCollection()
                legacy_scripts = LegacyCollection()
                legacy_queues = LegacyCollection()
                for node, filename in (
                    (legacy_emulators, "EmulatorConfig.json"),
                    (legacy_plans, "PlanConfig.json"),
                    (legacy_scripts, "ScriptConfig.json"),
                    (legacy_queues, "QueueConfig.json"),
                ):
                    await node.connect(self.config_path / filename)

                def legacy_uid(path: Path) -> uuid.UUID:
                    # 旧目录没有 UUID；使用相对来源身份，阶段中断重试不会重复导入。
                    return uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"auto-mas:legacy-v1.8:{path.relative_to(self.config_path).as_posix()}",
                    )

                if (self.config_path / "config.json").exists():
                    (self.config_path / "config.json").rename(
                        self.config_path / "Config.json"
                    )
                # 保留尚待后续阶段转换的旧键；不提前按新字段表加载和裁剪。
                legacy_setting = LegacyConfig()
                await legacy_setting.connect(self.config_path / "Config.json")

                plan_dict = {"固定": "Fixed"}

                if (self.config_path / "MaaPlanConfig").exists():
                    for MaaPlanConfig in (self.config_path / "MaaPlanConfig").iterdir():
                        if (
                            MaaPlanConfig.is_dir()
                            and (MaaPlanConfig / "config.json").exists()
                        ):
                            maa_plan_config = json.loads(
                                (MaaPlanConfig / "config.json").read_text(
                                    encoding="utf-8"
                                )
                            )
                            uid = legacy_uid(MaaPlanConfig)
                            await legacy_plans.put(
                                uid=uid,
                                type_name="MaaPlanConfig",
                                payload=maa_plan_config,
                            )
                            plan_dict[MaaPlanConfig.name] = str(uid)

                # 旧引用校验器会把“禁用”纠正为 '-'；中间文档直接使用该标记。
                script_dict: dict[str, str] = {"禁用": "-"}

                if (self.config_path / "MaaConfig").exists():
                    for MaaConfig in (self.config_path / "MaaConfig").iterdir():
                        if MaaConfig.is_dir():
                            maa_config = json.loads(
                                (MaaConfig / "config.json").read_text(encoding="utf-8")
                            )
                            maa_config["Info"] = maa_config["MaaSet"]
                            maa_config["Run"] = maa_config["RunSet"]

                            uid = legacy_uid(MaaConfig)
                            sc = await legacy_scripts.put(
                                uid=uid, type_name="MaaConfig", payload=maa_config
                            )
                            script_dict[MaaConfig.name] = str(uid)

                            if (MaaConfig / "Default/gui.json").exists():
                                (self.data_path / f"{uid}/Default/ConfigFile").mkdir(
                                    parents=True, exist_ok=True
                                )
                                shutil.copy(
                                    MaaConfig / "Default/gui.json",
                                    self.work_path
                                    / f"data/{uid}/Default/ConfigFile/gui.json",
                                )

                            for user in (MaaConfig / "UserData").iterdir():
                                if user.is_dir() and (user / "config.json").exists():
                                    user_config = json.loads(
                                        (user / "config.json").read_text(
                                            encoding="utf-8"
                                        )
                                    )

                                    stage_cfg = user_config.setdefault("Stage", {})
                                    plan_name = user_config["Info"]["StageMode"]
                                    if (
                                        isinstance(plan_name, str)
                                        and plan_name not in plan_dict
                                    ):
                                        # 清理旧目录中断时，计划目录可能已删，但聚合文件已保存。
                                        plan_uid = legacy_uid(
                                            self.config_path
                                            / "MaaPlanConfig"
                                            / plan_name
                                        )
                                        if plan_uid in legacy_plans:
                                            plan_dict[plan_name] = str(plan_uid)
                                    stage_cfg["StageMode"] = plan_dict.get(
                                        plan_name, "Fixed"
                                    )
                                    user_config["Info"]["Password"] = ""

                                    user_uid = legacy_uid(user)
                                    users = await sc.get_collection("UserData")
                                    await users.put(
                                        uid=user_uid,
                                        type_name="MaaUserConfig",
                                        payload=user_config,
                                    )

                                    if (user / "Routine/gui.json").exists():
                                        (
                                            self.work_path
                                            / f"data/{uid}/{user_uid}/ConfigFile"
                                        ).mkdir(parents=True, exist_ok=True)
                                        shutil.copy(
                                            user / "Routine/gui.json",
                                            self.work_path
                                            / f"data/{uid}/{user_uid}/ConfigFile/gui.json",
                                        )
                                    if (
                                        user / "Infrastructure/infrastructure.json"
                                    ).exists():
                                        (
                                            self.work_path
                                            / f"data/{uid}/{user_uid}/Infrastructure"
                                        ).mkdir(parents=True, exist_ok=True)
                                        shutil.copy(
                                            user / "Infrastructure/infrastructure.json",
                                            self.work_path
                                            / f"data/{uid}/{user_uid}/Infrastructure/infrastructure.json",
                                        )

                if (self.config_path / "GeneralConfig").exists():
                    for GeneralConfig in (self.config_path / "GeneralConfig").iterdir():
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

                            uid = legacy_uid(GeneralConfig)
                            sc = await legacy_scripts.put(
                                uid=uid,
                                type_name="GeneralConfig",
                                payload=general_config,
                            )
                            script_dict[GeneralConfig.name] = str(uid)

                            for user in (GeneralConfig / "SubData").iterdir():
                                if user.is_dir() and (user / "config.json").exists():
                                    user_config = json.loads(
                                        (user / "config.json").read_text(
                                            encoding="utf-8"
                                        )
                                    )

                                    user_uid = legacy_uid(user)
                                    users = await sc.get_collection("UserData")
                                    await users.put(
                                        uid=user_uid,
                                        type_name="GeneralUserConfig",
                                        payload=user_config,
                                    )

                                    if (user / "ConfigFiles").exists():
                                        (self.data_path / f"{uid}/{user_uid}").mkdir(
                                            parents=True, exist_ok=True
                                        )
                                        shutil.move(
                                            user / "ConfigFiles",
                                            self.work_path
                                            / f"data/{uid}/{user_uid}/ConfigFile",
                                        )

                if (self.config_path / "QueueConfig").exists():
                    for QueueConfig in (self.config_path / "QueueConfig").glob(
                        "*.json"
                    ):
                        queue_config = json.loads(
                            QueueConfig.read_text(encoding="utf-8")
                        )

                        queue_config["Info"] = queue_config["QueueSet"]
                        uid = legacy_uid(QueueConfig)
                        qc = await legacy_queues.put(
                            uid=uid, type_name="QueueConfig", payload=queue_config
                        )

                        times = await qc.get_collection("TimeSet")
                        items = await qc.get_collection("QueueItem")
                        for i in range(10):
                            script_name = queue_config["Queue"][f"Script_{i}"]
                            if (
                                isinstance(script_name, str)
                                and script_name not in script_dict
                            ):
                                for folder in ("GeneralConfig", "MaaConfig"):
                                    script_uid = legacy_uid(
                                        self.config_path / folder / script_name
                                    )
                                    if script_uid in legacy_scripts:
                                        script_dict[script_name] = str(script_uid)
                                        break
                            await times.put(
                                uid=legacy_uid(QueueConfig / f"TimeSet/{i}"),
                                type_name="TimeSet",
                                payload={
                                    "Info": {
                                        "Enabled": queue_config["Time"][f"Enabled_{i}"],
                                        "Time": queue_config["Time"][f"Set_{i}"],
                                    }
                                },
                            )
                            await items.put(
                                uid=legacy_uid(QueueConfig / f"QueueItem/{i}"),
                                type_name="QueueItem",
                                payload={
                                    "Info": {
                                        "ScriptId": script_dict.get(script_name, "-")
                                    }
                                },
                            )

                # 旧保存链已逐笔写入聚合 JSON；最终再次等待全部文件落盘，
                # 才允许清理来源并推进版本。后续 YAML 失败可从这些 JSON 继续。
                for node in (
                    legacy_emulators,
                    legacy_plans,
                    legacy_scripts,
                    legacy_queues,
                ):
                    await node.save()

                if (self.config_path / "QueueConfig").exists():
                    shutil.rmtree(self.config_path / "QueueConfig")
                if (self.config_path / "MaaPlanConfig").exists():
                    shutil.rmtree(self.config_path / "MaaPlanConfig")
                if (self.config_path / "MaaConfig").exists():
                    shutil.rmtree(self.config_path / "MaaConfig")
                if (self.config_path / "GeneralConfig").exists():
                    shutil.rmtree(self.config_path / "GeneralConfig")
                if (self.data_path / "gameid.txt").exists():
                    (self.data_path / "gameid.txt").unlink()
                if (self.data_path / "key").exists():
                    shutil.rmtree(self.data_path / "key")

                cur.execute("DELETE FROM version WHERE v = ?", ("v1.8",))
                cur.execute("INSERT INTO version VALUES(?)", ("v1.9",))
                db.commit()
            # v1.9-->v1.10
            if version[0][0] == "v1.9" or if_streaming:
                logger.info(
                    "数据文件版本更新: v1.9-->v1.10",
                )
                if_streaming = True

                if (self.config_path / "Config.json").exists():
                    data = json.loads(
                        (self.config_path / "Config.json").read_text(encoding="utf-8")
                    )
                    data.setdefault("Data", {})["LastStageUpdated"] = (
                        "2000-01-01 00:00:00"
                    )
                    data["Data"]["Stage"] = "{ }"
                    function = data.setdefault("Function", {})
                    function["IfBlockAd"] = function.get(
                        "IfBlockAd", function.get("IfSkipMumuSplashAds", False)
                    )
                    (self.config_path / "Config.json").write_text(
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

                cur.execute("DELETE FROM version WHERE v = ?", ("v1.10",))
                cur.execute("INSERT INTO version VALUES(?)", ("v1.11",))
                db.commit()

            logger.success("数据文件版本更新完成")

        cur.close()
        db.close()

    async def get_git_version(self) -> tuple[bool, str, str]:
        """获取Git版本信息，如果Git不可用则返回默认值。

        受 AUTO-MAS-Runtime 监督时后端不是更新主体：更新由 Runtime 整体替换
        repo/ 完成、不在旧仓库上 fetch，比对远端分支判定“需要更新”没有意义，
        一律视为最新。managed 模式直接回显 Runtime 从校验过的仓库注入的 HEAD，
        不依赖 Runtime 布局里并不存在的 git 命令行；development 模式无注入
        身份，仍从源码目录读取 Git 信息用于展示。
        """

        supervised = is_supervised()
        expected_commit = os.getenv("AUTO_MAS_EXPECTED_COMMIT", "")
        if supervised and expected_commit:
            return True, expected_commit, "unknown"

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
                # 仅比对本地已缓存的远程引用，不在请求路径上调用 origin.fetch()。
                # fetch 是联网操作（弱网/VPN 下耗时 5~15s），以同步 GitPython 子进程
                # 形式执行会阻塞事件循环，期间所有请求排队无响应；远程引用由
                # 版本更新等流程自行维护，此处只读本地。
                remote_commit = repo.commit(f"origin/{repo.active_branch.name}")
                is_latest = bool(current_commit.hexsha == remote_commit.hexsha)
            except Exception as e:
                logger.warning(f"无法获取远程分支信息: {e}")
                is_latest = False

            return is_latest, commit_hash, commit_time.strftime("%Y-%m-%d %H:%M:%S")

        # 在线程池中执行 Git 操作
        is_latest, commit_hash, commit_time = await self.loop.run_in_executor(
            None, _get_git_info
        )
        return is_latest or supervised, commit_hash, commit_time

    async def add_script(
        self,
        script: Literal[
            "MAA",
            "SRC",
            "General",
            "MaaEnd",
            "M9A",
            "MaaFW",
            "Okww",
            "OkNte",
            "HSR",
            "BetterGI",
            "ZzzOd",
            "BAAH",
            "Whimbox",
            "MSS",
        ],
        script_id: str | None = None,
        *,
        payload: dict[str, Any] | None = None,
    ) -> tuple[
        uuid.UUID,
        MaaConfig
        | SrcConfig
        | GeneralConfig
        | MaaEndConfig
        | M9AConfig
        | MaaFWConfig
        | OkwwConfig
        | OkNteConfig
        | HSRConfig
        | BetterGIConfig
        | ZzzOdConfig
        | BAAHConfig
        | WhimboxConfig
        | MSSConfig,
    ]:
        """添加脚本配置"""

        logger.info(f"添加脚本配置: {script}, 从 {script_id} 复制")

        if script_id is None:
            async with config_manager.transaction():
                _config_uid = self.ScriptConfig.add(CLASS_BOOK[script], payload=payload)
                await self.ScriptConfig.commit()
                _config_entry = self.ScriptConfig[_config_uid]
                await self._initialize_script_config(_config_entry)
            return _config_uid, _config_entry
        else:
            script_uid = uuid.UUID(script_id)

            if not isinstance(self.ScriptConfig[script_uid], CLASS_BOOK[script]):
                raise TypeError(f"脚本配置类型不匹配: {script_id} {script}")

            document = self.ScriptConfig[script_uid].model_dump(
                context={"audience": "persist"}
            )
            async with config_manager.transaction():
                new_uid = self.ScriptConfig.add(
                    CLASS_BOOK[script], payload=document, regenerate_uuids=True
                )
                await self.ScriptConfig.commit()
                new_config = self.ScriptConfig[new_uid]
                await self._initialize_script_config(new_config)
            user_ids = {
                item["uid"]: uid
                for item, uid in zip(
                    document["UserData"]["order"], new_config.UserData.keys()
                )
            }

            # 专项副本在配置事务成功后、通用用户数据复制前准备。
            handler = self._get_script_config_handler(new_config)
            if handler is not None and handler.clone_script is not None:
                await handler.clone_script(self.ScriptConfig[script_uid], new_config)

            # 复制用户数据
            if (self.data_path / f"{script_id}").exists():
                shutil.copytree(
                    self.data_path / f"{script_id}",
                    self.data_path / f"{new_uid}",
                    dirs_exist_ok=True,
                )
                for old_user, new_user in user_ids.items():
                    if (self.data_path / f"{new_uid}/{old_user}").exists():
                        (self.data_path / f"{new_uid}/{old_user}").rename(
                            self.data_path / f"{new_uid}/{new_user}"
                        )

            return new_uid, new_config

    async def get_script(self, script_id: str | None) -> tuple[list, dict]:
        """获取脚本配置"""

        logger.info(f"获取脚本配置: {script_id}")

        if script_id is None:
            # 获取所有脚本配置
            data = self.ScriptConfig.model_dump(context={"audience": "api"})
        else:
            # 获取指定脚本配置
            entry = self.ScriptConfig[uuid.UUID(script_id)]
            return (
                [{"uid": str(entry.uid), "type": type(entry).__name__}],
                {str(entry.uid): entry.model_dump(context={"audience": "api"})},
            )

        index = data["order"]
        return list(index), data["data"]

    async def update_script_settings(
        self, script_id: str, data: Dict[str, Dict[str, Any]]
    ) -> str | None:
        """编辑保存先检查设备绑定，再按原有锁和提交规则更新配置。"""
        from app.core import EmulatorManager

        refusal = await EmulatorManager.mod_avd_binding_error(script_id, data)
        if refusal:
            return refusal
        await self.update_script(script_id, data)
        return None

    async def create_data_backup(self) -> Path:
        """导出当前配置与历史的一致快照后生成整包备份。"""
        from app.core.config.backup import create_data_backup

        return await create_data_backup()

    async def update_script(
        self, script_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新脚本配置"""

        logger.info(f"更新脚本配置: {script_id}")

        uid = uuid.UUID(script_id)

        if self.ScriptConfig[uid].is_locked:
            raise RuntimeError(f"脚本 {script_id} 正在运行, 无法更新配置项")

        handler = self._get_script_config_handler(self.ScriptConfig[uid])
        if handler is not None and handler.validate_update is not None:
            handler.validate_update(data)

        await self.ScriptConfig[uid].update(
            type(self.ScriptConfig[uid]).model_validate(data)
        )

    async def del_script(self, script_id: str) -> None:
        """删除脚本配置"""

        logger.info(f"删除脚本配置: {script_id}")

        uid = uuid.UUID(script_id)

        if self.ScriptConfig[uid].is_locked:
            raise RuntimeError(f"脚本 {script_id} 正在运行, 无法删除")

        # 删脚本会顺带删掉引用它的队列项；正在循环运行的队列靠下标回写状态，
        # 结构一变就会跑错脚本，两轮之间脚本没锁也要拦住。
        for queue_uid, queue in self.QueueConfig.items():
            if any((item.Info.ScriptId == uid for item in queue.QueueItem.values())):
                self._ensure_cycle_safe(queue_uid, "删除它引用的脚本")

        # 删除脚本相关的队列项
        for queue in self.QueueConfig.values():
            for key, value in queue.QueueItem.items():
                if value.Info.ScriptId == uid:
                    queue.QueueItem.remove(key)
                    await queue.QueueItem.commit()

        script_config = self.ScriptConfig[uid]
        handler = self._get_script_config_handler(script_config)
        if handler is not None and handler.prepare_script_removal is not None:
            await handler.prepare_script_removal(script_config)

        self.ScriptConfig.remove(uid)
        await self.ScriptConfig.commit()
        if handler is not None and handler.after_script_removal is not None:
            handler.after_script_removal()
        # 数据目录里可能有只读文件（如脚本配置目录快照带进来的 .git 对象）：裸
        # rmtree 删到它们会抛 PermissionError，而此时配置已经移除，目录残留在磁盘上、
        # 再点这个脚本还会报「配置项不存在」。目录删除是阻塞 IO（force_rmtree 内部
        # 还有 sleep 重试），放线程里跑，别让事件循环跟着等。
        script_data_dir = self.data_path / f"{uid}"
        if script_data_dir.exists():
            await asyncio.to_thread(_utils_io.force_rmtree, script_data_dir)
        if handler is not None and handler.cleanup_script_files is not None:
            await handler.cleanup_script_files(str(uid))

    async def reorder_script(self, index_list: list[str]) -> None:
        """重新排序脚本"""

        logger.info(f"重新排序脚本: {index_list}")

        self.ScriptConfig.set_order([uuid.UUID(_) for _ in index_list])
        await self.ScriptConfig.commit()

    async def get_user(
        self, script_id: str, user_id: Optional[str]
    ) -> tuple[list, dict]:
        """获取用户配置"""

        logger.info(f"获取用户配置: {script_id} - {user_id}")

        uid = uuid.UUID(script_id)

        script_config = self.ScriptConfig[uid]
        handler = self._get_script_config_handler(script_config)
        if handler is not None and handler.prepare_user_read is not None:
            await handler.prepare_user_read(
                script_config,
                user_ids=None if user_id is None else [str(uuid.UUID(user_id))],
            )

        if user_id is None:
            # 获取全部用户配置
            data = self.ScriptConfig[uid].UserData.model_dump(
                context={"audience": "api"}
            )
        else:
            # 获取指定用户配置
            entry = self.ScriptConfig[uid].UserData[uuid.UUID(user_id)]
            return (
                [{"uid": str(entry.uid), "type": type(entry).__name__}],
                {str(entry.uid): entry.model_dump(context={"audience": "api"})},
            )

        index = data["order"]
        return list(index), data["data"]

    async def add_user(
        self, script_id: str, *, payload: dict[str, Any] | None = None
    ) -> tuple[
        uuid.UUID,
        MaaUserConfig
        | SrcUserConfig
        | GeneralUserConfig
        | MaaEndUserConfig
        | M9AUserConfig
        | MaaFWUserConfig
        | OkwwUserConfig
        | OkNteUserConfig
        | HSRUserConfig
        | BetterGIUserConfig
        | ZzzOdUserConfig
        | BAAHUserConfig
        | WhimboxUserConfig
        | MSSUserConfig,
    ]:
        """添加用户配置"""

        logger.info(f"{script_id} 添加用户配置")

        script_config = self.ScriptConfig[uuid.UUID(script_id)]

        handler = self._get_script_config_handler(script_config)
        # 特调脚本自行声明的用户类优先，不能被 MaaFW 父类型处理器覆盖。
        user_class = getattr(script_config, "USER_CONFIG_CLASS", None)
        if user_class is None and handler is not None:
            user_class = handler.user_config_class
        if user_class is None:
            raise TypeError(f"不支持的脚本配置类型: {type(script_config)}")

        uid = script_config.UserData.add(user_class, payload=payload)
        await script_config.UserData.commit()
        config = script_config.UserData[uid]
        if handler is not None and handler.initialize_user is not None:

            async def rollback() -> None:
                # 只撤回本次集合成员，不递归走完整删除生命周期或碰共享目录。
                script_config.UserData.remove(uid)
                await script_config.UserData.commit()

            await handler.initialize_user(script_config, config, rollback=rollback)

        return uid, config

    async def flush(self) -> None:
        """等待已提交配置落盘，供注入的专项服务使用。"""
        await config_manager.flush()

    # ════════════ 配置恢复（宿主注入池解析，门面绑定上下文） ════════════

    def set_restore_pool_resolver(
        self,
        resolver: Callable[
            ["ConfigEntry"], list["_utils_config_restore.ConfigRestorePool"]
        ],
    ) -> None:
        """由宿主装配恢复池解析函数，绑定仅作用于当前配置实例。"""

        self._restore_pool_resolver = resolver

    def restore_service(
        self, script_id: str, user_id: str, *, force: bool = False
    ) -> "_utils_config_restore.ConfigRestoreService":
        """通过注入的解析函数取得恢复池，绑定上下文构建运行时服务。

        专项只声明池表（普通函数，显式收 :class:`RestoreContext`），由宿主
        负责选择。``force`` 随上下文下发，供专项池的恢复函数读取
        （当前仅 ZzzOd 消费）。
        """

        from app.utils.common.config import restore as _utils_config_restore

        script_config = self.ScriptConfig[uuid.UUID(script_id)]
        if self._restore_pool_resolver is None:
            raise RuntimeError("配置恢复未初始化：请先由宿主装配恢复池解析函数")
        pools = self._restore_pool_resolver(script_config)
        return _utils_config_restore.build_restore_service(
            _utils_config_restore.RestoreContext(
                config=self,
                script_config=script_config,
                script_id=script_id,
                user_id=user_id,
                force=force,
            ),
            pools,
        )

    async def list_config_backups(
        self, script_id: str, user_id: str, target: str
    ) -> dict:
        """列出配置备份（时间倒序，每项带 base 来源标注）与当前 base 来源。

        返回 ``{"items": [{"time", "base"}], "base": 当前来源或 None}``；
        当前来源只在三态池返回（前端据此比对是否需要跨来源提示）。
        target 取值由专项池定义。
        """

        service = self.restore_service(script_id, user_id)
        return {
            "items": await service.list(target),
            "base": await service.current_base(target),
        }

    async def ensure_config_backup(
        self, script_id: str, user_id: str, target: str
    ) -> dict:
        """按需归档目标池当前配置（指纹去重，无变化自动跳过）。

        编辑界面三时机的统一入口：进入/退出编辑页（前端触发）、运行前
        （各专项任务流程调用专项归档函数，不经本方法）。
        """

        return await self.restore_service(script_id, user_id).ensure(target)

    async def restore_config_backup(
        self, script_id: str, user_id: str, ts: str, target: str, *, force: bool = False
    ) -> dict:
        """把指定备份恢复到目标位置（恢复前存底、跨来源切换由服务层自理）。

        恢复是覆盖性写配置操作：脚本锁着（任务/配置会话运行中）时拒绝，
        否则 mas 池「先换目录再回填 UserData」会在 update 处撞锁，留下
        目录已换、字段未回填的半恢复现场。

        ``force`` 随上下文下发到专项池恢复函数（当前仅 ZzzOd 消费：跳过
        注册表依赖步骤——恢复前存底 / 占用守卫），其余专项忽略。源配置
        损坏（``ConfigCorruptedError``）原样抛出，API 层转 409 交前端二次
        确认。
        """

        uid = uuid.UUID(script_id)
        if self.ScriptConfig[uid].is_locked:
            raise RuntimeError(f"脚本 {script_id} 正在运行, 无法恢复配置")

        await self.restore_service(script_id, user_id, force=force).restore(target, ts)
        return {"target": target}

    async def get_config_backup_preview(
        self, script_id: str, user_id: str, ts: str, target: str
    ) -> dict:
        """读取指定备份的配置摘要（纯读不恢复）；载荷结构由专项定义。"""

        payload = await self.restore_service(script_id, user_id).preview(target, ts)
        return {"time": ts, "target": target, "data": payload}

    async def get_config_backup_file(
        self, script_id: str, user_id: str, ts: str, target: str, path: str
    ) -> dict:
        """只读读取指定备份内一个文本文件（预览「查看原始文件」用）。

        路径限归档内相对路径（防穿越）、大小受限（1 MiB），由
        ``config_archive.read_backup_text`` 与专项池函数保证。
        """

        content = await self.restore_service(script_id, user_id).read_backup_file(
            target, ts, path
        )
        return {"time": ts, "target": target, **content}

    async def update_user(
        self,
        script_id: str,
        user_id: str,
        data: Dict[str, Dict[str, Any]],
        *,
        precondition: Callable[[], bool] | None = None,
    ) -> bool:
        """更新用户配置，返回是否写入

        ``precondition``：预处理（特调整理、密码加密等，要让出事件循环）做完、真正写入
        之前再判一次，不成立就不写。判断与写入之间不让出，期间插不进别的写入。
        """

        logger.info(f"{script_id} 更新用户配置: {user_id}")

        script_uid = uuid.UUID(script_id)
        user_uid = uuid.UUID(user_id)
        script_config = self.ScriptConfig[script_uid]
        user_config = script_config.UserData[user_uid]

        handler = self._get_script_config_handler(script_config)
        if handler is not None and handler.prepare_user_update is not None:
            prepared = handler.prepare_user_update(
                script_config, user_config, data=data
            )
            if inspect.isawaitable(prepared):
                await prepared

        if precondition is not None and not precondition():
            return False
        await user_config.update(type(user_config).model_validate(data))
        return True

    async def import_script_config_file(
        self, script_id: str, user_id: Optional[str]
    ) -> None:
        """从目标脚本目录导入配置文件"""

        logger.info(f"{script_id} - {user_id or 'Default'} 导入脚本配置文件")

        script_config = self.ScriptConfig[uuid.UUID(script_id)]

        if script_config.is_locked:
            raise RuntimeError(f"脚本 {script_id} 正在运行，无法导入配置文件")

        handler = self._get_script_config_handler(script_config)
        if handler is None or handler.import_config is None:
            raise TypeError("当前脚本类型暂不支持导入配置文件")

        config_owner = user_id or "Default"
        target_config_dir = self.data_path / f"{script_id}/{config_owner}/ConfigFile"
        imported = handler.import_config(
            script_config, target_config_dir, user_id=user_id
        )
        if inspect.isawaitable(imported):
            await imported

    def bind_script_config_handler(
        self, entry_type: type[ConfigEntry], handler: ScriptConfigHandler | None
    ) -> None:
        """由宿主将专项操作绑定到当前配置实例。"""
        if entry_type in self._script_config_handlers:
            raise ValueError(f"重复的配置处理器登记: {entry_type.__name__}")
        self._script_config_handlers[entry_type] = handler

    def _get_script_config_handler(
        self, script: ConfigEntry
    ) -> ScriptConfigHandler | None:
        for entry_type, handler in self._script_config_handlers.items():
            if isinstance(script, entry_type):
                return handler
        raise RuntimeError(f"专项配置处理器未登记: {type(script).__name__}")

    def get_script_task_resources(self, script: ConfigEntry) -> "ScriptTaskResources":
        """读取专项资源声明，不提交配置或访问脚本资源文件。"""
        from app.models.task import ScriptTaskResources

        handler = self._get_script_config_handler(script)
        if handler is None or handler.task_resources is None:
            return ScriptTaskResources()
        return handler.task_resources(script)

    def get_script_emulator_binding(
        self, script: ConfigEntry, *, patch: dict[str, Any] | None = None
    ) -> tuple[Any, Any] | None:
        """读取持久绑定；传入补丁时只返回本次提交设备号所形成的候选。"""
        handler = self._get_script_config_handler(script)
        if handler is None or handler.emulator_binding is None:
            return None
        if patch is not None:
            return handler.emulator_binding.read_patch(script, patch)
        return handler.emulator_binding.read(script)

    def script_supports_mod_avd(self, script: ConfigEntry) -> bool:
        """读取专项声明的设备能力；MaaFW 特调沿用基类处理器。"""
        handler = self._get_script_config_handler(script)
        return handler is not None and handler.supports_mod_avd

    async def _initialize_script_config(self, script: ConfigEntry) -> None:
        handler = self._get_script_config_handler(script)
        if handler is not None and handler.initialize is not None:
            await handler.initialize(script)

    async def del_user(self, script_id: str, user_id: str) -> None:
        """删除用户配置"""

        logger.info(f"{script_id} 删除用户配置: {user_id}")

        script_uid = uuid.UUID(script_id)
        user_uid = uuid.UUID(user_id)
        script_config = self.ScriptConfig[script_uid]

        handler = self._get_script_config_handler(script_config)
        cleanup = None
        if handler is not None and handler.prepare_user_removal is not None:
            cleanup = handler.prepare_user_removal(script_config, user_uid)

        script_config.UserData.remove(user_uid)
        await script_config.UserData.commit()
        if cleanup is not None:
            await cleanup()

        # 与 del_script 同理：用户数据目录里可能有只读文件，裸 rmtree 删不干净还抛异常。
        user_data_dir = self.data_path / f"{script_id}/{user_id}"
        if user_data_dir.exists():
            await asyncio.to_thread(_utils_io.force_rmtree, user_data_dir)

    async def get_user_config_dir(self, script_id: str, user_id: str) -> Path:
        """获取用户配置目录, 不存在时创建"""

        logger.info(f"{script_id} 获取用户配置目录: {user_id}")

        script_uid = uuid.UUID(script_id)
        user_uid = uuid.UUID(user_id)
        if user_uid not in self.ScriptConfig[script_uid].UserData:
            raise ValueError("用户不存在")

        user_config_dir = self.data_path / f"{script_id}/{user_id}"
        user_config_dir.mkdir(parents=True, exist_ok=True)

        return user_config_dir

    async def reorder_user(self, script_id: str, index_list: list[str]) -> None:
        """重新排序用户"""

        logger.info(f"{script_id} 重新排序用户: {index_list}")

        script_uid = uuid.UUID(script_id)

        self.ScriptConfig[script_uid].UserData.set_order(
            list(map(uuid.UUID, index_list))
        )
        await self.ScriptConfig[script_uid].UserData.commit()

    async def add_plan(
        self,
        script: Literal["MaaPlan", "MaaEndPlan", "BAAHPlan", "MSSPlan"],
        *,
        payload: dict[str, Any] | None = None,
    ) -> tuple[
        uuid.UUID, MaaPlanConfig | MaaEndPlanConfig | BAAHPlanConfig | MSSPlanConfig
    ]:
        """添加计划表"""

        logger.info(f"添加计划表: {script}")

        plan_class = next(
            item["config_class"]
            for item in PLAN_BOOK.values()
            if item["create_type"] == script
        )
        _config_uid = self.PlanConfig.add(plan_class, payload=payload)
        await self.PlanConfig.commit()
        _config_entry = self.PlanConfig[_config_uid]
        return _config_uid, _config_entry

    async def get_plan(self, plan_id: Optional[str]) -> tuple[list, dict]:
        """获取计划表配置"""

        logger.info(f"获取计划表配置: {plan_id}")

        if plan_id is None:
            data = self.PlanConfig.model_dump(context={"audience": "api"})
        else:
            entry = self.PlanConfig[uuid.UUID(plan_id)]
            return (
                [{"uid": str(entry.uid), "type": type(entry).__name__}],
                {str(entry.uid): entry.model_dump(context={"audience": "api"})},
            )

        index = data["order"]
        return list(index), data["data"]

    async def update_plan(self, plan_id: str, data: Dict[str, Dict[str, Any]]) -> None:
        """更新计划表配置"""

        logger.info(f"更新计划表配置: {plan_id}")

        plan_uid = uuid.UUID(plan_id)

        await self.PlanConfig[plan_uid].update(
            type(self.PlanConfig[plan_uid]).model_validate(data)
        )

    async def del_plan(self, plan_id: str) -> None:
        """删除计划表配置"""

        logger.info(f"删除计划表配置: {plan_id}")

        plan_uid = uuid.UUID(plan_id)

        plan_config = self.PlanConfig[plan_uid]
        plan_type = type(plan_config).__name__
        if plan_type not in PLAN_BOOK:
            raise TypeError(f"不支持的计划表配置类型: {plan_type}")

        consumer_config = PLAN_BOOK[plan_type]
        user_list: list[
            MaaUserConfig | MaaEndUserConfig | BAAHUserConfig | MSSUserConfig
        ] = []

        for script in self.ScriptConfig.values():
            if not isinstance(script, consumer_config["script_class"]):
                continue
            for user in script.UserData.values():
                if (
                    getattr(
                        getattr(user, consumer_config["field_group"]),
                        consumer_config["field_name"],
                    )
                    != plan_uid
                ):
                    continue
                if user.is_locked:
                    raise RuntimeError(
                        f"用户 {user.Info.Name} 正在使用此计划表且被锁定, 无法完成删除"
                    )
                user_list.append(user)

        for user in user_list:
            entry = cast(ConfigEntry, user)
            await entry.update(
                type(entry).model_validate(
                    {
                        consumer_config["field_group"]: {
                            consumer_config["field_name"]: "Fixed"
                        }
                    }
                ),
                check_visibility=False,
            )

        self.PlanConfig.remove(plan_uid)
        await self.PlanConfig.commit()

    async def reorder_plan(self, index_list: list[str]) -> None:
        """重新排序计划表"""

        logger.info(f"重新排序计划表: {index_list}")

        self.PlanConfig.set_order(list(map(uuid.UUID, index_list)))
        await self.PlanConfig.commit()

    async def get_emulator(self, emulator_id: Optional[str]) -> tuple[list, dict]:
        """获取模拟器配置"""
        logger.info(f"获取全局模拟器设置: {emulator_id}")

        if emulator_id is None:
            data = self.EmulatorConfig.model_dump(context={"audience": "api"})
        else:
            entry = self.EmulatorConfig[uuid.UUID(emulator_id)]
            return (
                [{"uid": str(entry.uid), "type": type(entry).__name__}],
                {str(entry.uid): entry.model_dump(context={"audience": "api"})},
            )

        index = data["order"]
        return list(index), data["data"]

    async def add_emulator(self) -> tuple[uuid.UUID, EmulatorConfig]:
        """添加模拟器配置"""
        logger.info("添加全局模拟器配置")

        uid = self.EmulatorConfig.add(EmulatorConfig)
        await self.EmulatorConfig.commit()
        config = self.EmulatorConfig[uid]
        return uid, config

    async def update_emulator(
        self, emulator_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新模拟器配置"""

        emulator_uid = uuid.UUID(emulator_id)

        logger.info(f"更新模拟器配置: {emulator_id}")

        await self.EmulatorConfig[emulator_uid].update(
            type(self.EmulatorConfig[emulator_uid]).model_validate(data)
        )

    async def del_emulator(self, emulator_id: str) -> None:
        """删除模拟器配置"""

        emulator_uid = uuid.UUID(emulator_id)

        logger.info(f"删除全局模拟器配置: {emulator_id}")

        async with config_manager.transaction():
            for script in self.ScriptConfig.values():
                binding = self.get_script_emulator_binding(script)
                # 持久引用与运行占用不同：General 禁用游戏时也不能绕过被锁定的引用。
                if binding is not None and str(binding[0]) == str(emulator_uid):
                    if script.is_locked:
                        raise RuntimeError(
                            f"脚本 {script.Info.Name} 正在使用此模拟器且被锁定, 无法完成删除"
                        )

            # 关联绑定由删除信号统一清理，任一运行锁拒绝时随删除一起回退。
            self.EmulatorConfig.remove(emulator_uid)
            await self.EmulatorConfig.commit()

    async def add_queue(
        self, *, payload: dict[str, Any] | None = None
    ) -> tuple[uuid.UUID, QueueConfig]:
        """添加调度队列"""

        logger.info("添加调度队列")

        _config_uid = self.QueueConfig.add(QueueConfig, payload=payload)
        await self.QueueConfig.commit()
        _config_entry = self.QueueConfig[_config_uid]
        return _config_uid, _config_entry

    async def get_queue(self, queue_id: Optional[str]) -> tuple[list, dict]:
        """获取调度队列配置"""

        logger.info(f"获取调度队列配置: {queue_id}")

        if queue_id is None:
            data = self.QueueConfig.model_dump(context={"audience": "api"})
        else:
            entry = self.QueueConfig.get(uuid.UUID(queue_id))
            if entry is None:
                raise QueueNotFoundError("队列不存在或已删除，请重新选择")
            return (
                [{"uid": str(entry.uid), "type": type(entry).__name__}],
                {str(entry.uid): entry.model_dump(context={"audience": "api"})},
            )

        index = data["order"]
        return list(index), data["data"]

    async def update_queue(
        self, queue_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新调度队列配置"""

        logger.info(f"更新调度队列配置: {queue_id}")

        queue_uid = uuid.UUID(queue_id)
        # 队列名、完成后操作这类字段改了不影响正在跑的循环，放行；
        # 只有循环开关本身不能在运行中动。
        if "CycleEnabled" in data.get("Info", {}):
            self._ensure_cycle_safe(queue_uid, "切换循环开关")

        await self.QueueConfig[queue_uid].update(
            type(self.QueueConfig[queue_uid]).model_validate(data)
        )

    async def del_queue(self, queue_id: str) -> None:
        """删除调度队列配置"""

        logger.info(f"删除调度队列配置: {queue_id}")

        queue_uid = uuid.UUID(queue_id)
        self._ensure_cycle_safe(queue_uid, "删除")

        self.QueueConfig.remove(queue_uid)
        await self.QueueConfig.commit()

    async def get_time_set(
        self, queue_id: str, time_set_id: Optional[str]
    ) -> tuple[list, dict]:
        """获取时间设置配置"""

        logger.info(f"获取队列的时间配置: {queue_id} - {time_set_id}")

        queue_uid = uuid.UUID(queue_id)

        if time_set_id is None:
            data = self.QueueConfig[queue_uid].TimeSet.model_dump(
                context={"audience": "api"}
            )
        else:
            entry = self.QueueConfig[queue_uid].TimeSet[uuid.UUID(time_set_id)]
            return (
                [{"uid": str(entry.uid), "type": type(entry).__name__}],
                {str(entry.uid): entry.model_dump(context={"audience": "api"})},
            )

        index = data["order"]
        return list(index), data["data"]

    async def add_time_set(
        self, queue_id: str, *, payload: dict[str, Any] | None = None
    ) -> tuple[uuid.UUID, TimeSet]:
        """添加时间设置配置"""

        logger.info(f"{queue_id} 添加时间设置配置")

        queue_uid = uuid.UUID(queue_id)
        uid = self.QueueConfig[queue_uid].TimeSet.add(TimeSet, payload=payload)
        await self.QueueConfig[queue_uid].TimeSet.commit()
        config = self.QueueConfig[queue_uid].TimeSet[uid]

        return uid, config

    async def update_time_set(
        self, queue_id: str, time_set_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新时间设置配置"""

        logger.info(f"{queue_id} 更新时间设置配置: {time_set_id}")

        queue_uid = uuid.UUID(queue_id)
        time_set_uid = uuid.UUID(time_set_id)

        await (
            self.QueueConfig[queue_uid]
            .TimeSet[time_set_uid]
            .update(
                type(self.QueueConfig[queue_uid].TimeSet[time_set_uid]).model_validate(
                    data
                )
            )
        )

    async def del_time_set(self, queue_id: str, time_set_id: str) -> None:
        """删除时间设置配置"""

        logger.info(f"{queue_id} 删除时间设置配置: {time_set_id}")

        queue_uid = uuid.UUID(queue_id)
        time_set_uid = uuid.UUID(time_set_id)

        self.QueueConfig[queue_uid].TimeSet.remove(time_set_uid)
        await self.QueueConfig[queue_uid].TimeSet.commit()

    async def reorder_time_set(self, queue_id: str, index_list: list[str]) -> None:
        """重新排序时间设置"""

        logger.info(f"{queue_id} 重新排序时间设置: {index_list}")

        queue_uid = uuid.UUID(queue_id)

        self.QueueConfig[queue_uid].TimeSet.set_order(list(map(uuid.UUID, index_list)))
        await self.QueueConfig[queue_uid].TimeSet.commit()

    async def get_queue_item(
        self, queue_id: str, queue_item_id: Optional[str]
    ) -> tuple[list, dict]:
        """获取队列项配置"""

        logger.info(f"获取队列的队列项配置: {queue_id} - {queue_item_id}")

        queue_uid = uuid.UUID(queue_id)
        queue = self.QueueConfig.get(queue_uid)
        if queue is None:
            raise QueueNotFoundError("队列不存在或已删除，请重新选择")

        if queue_item_id is None:
            data = queue.QueueItem.model_dump(context={"audience": "api"})
        else:
            entry = queue.QueueItem.get(uuid.UUID(queue_item_id))
            if entry is None:
                raise QueueItemNotFoundError("队列项不存在或已删除，请刷新列表")
            return (
                [{"uid": str(entry.uid), "type": type(entry).__name__}],
                {str(entry.uid): entry.model_dump(context={"audience": "api"})},
            )

        index = data["order"]
        return list(index), data["data"]

    async def add_queue_item(
        self, queue_id: str, *, payload: dict[str, Any] | None = None
    ) -> tuple[uuid.UUID, QueueItem]:
        """添加队列项配置"""

        logger.info(f"{queue_id} 添加队列项配置")

        queue_uid = uuid.UUID(queue_id)
        self._ensure_cycle_safe(queue_uid, "增删队列项")

        uid = self.QueueConfig[queue_uid].QueueItem.add(QueueItem, payload=payload)
        await self.QueueConfig[queue_uid].QueueItem.commit()
        config = self.QueueConfig[queue_uid].QueueItem[uid]

        return uid, config

    async def update_queue_item(
        self, queue_id: str, queue_item_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新队列项配置"""

        logger.info(f"{queue_id} 更新队列项配置: {queue_item_id}")

        queue_uid = uuid.UUID(queue_id)
        queue_item_uid = uuid.UUID(queue_item_id)
        # 循环调度参数每轮都会重读，运行中改没问题；换脚本会让任务的脚本列表
        # 与队列对不上号，必须拦住。
        if "Info" in data:
            self._ensure_cycle_safe(queue_uid, "更换队列项的脚本")

        await (
            self.QueueConfig[queue_uid]
            .QueueItem[queue_item_uid]
            .update(
                type(
                    self.QueueConfig[queue_uid].QueueItem[queue_item_uid]
                ).model_validate(data)
            )
        )

    async def del_queue_item(self, queue_id: str, queue_item_id: str) -> None:
        """删除队列项配置"""

        logger.info(f"{queue_id} 删除队列项配置: {queue_item_id}")

        queue_uid = uuid.UUID(queue_id)
        queue_item_uid = uuid.UUID(queue_item_id)
        self._ensure_cycle_safe(queue_uid, "增删队列项")

        self.QueueConfig[queue_uid].QueueItem.remove(queue_item_uid)
        await self.QueueConfig[queue_uid].QueueItem.commit()

    async def reorder_queue_item(self, queue_id: str, index_list: list[str]) -> None:
        """重新排序队列项"""

        logger.info(f"{queue_id} 重新排序队列项: {index_list}")

        queue_uid = uuid.UUID(queue_id)
        self._ensure_cycle_safe(queue_uid, "调整队列项顺序")

        self.QueueConfig[queue_uid].QueueItem.set_order(
            list(map(uuid.UUID, index_list))
        )
        await self.QueueConfig[queue_uid].QueueItem.commit()

    def _ensure_cycle_safe(self, queue_uid: uuid.UUID, action: str) -> None:
        """拦住会打乱正在运行的循环的改动。

        任务的脚本列表在创建时就冻结了，循环靠下标回写状态；队列项的增删、
        排序、换脚本都会让下标对不上号。只拦这些，改名、改完成后操作、改循环
        周期都不受影响。
        """

        if queue_uid not in self.running_cycle_queue_ids:
            return

        queue_name = (
            self.QueueConfig[queue_uid].Info.Name
            if queue_uid in self.QueueConfig
            else str(queue_uid)
        )
        raise RuntimeError(f"循环队列 {queue_name} 正在运行，无法{action}")

    async def get_tools(self) -> Dict[str, Any]:
        """获取工具设置"""

        logger.debug("获取工具设置")

        today = datetime.now(tz=_utils_constants.UTC8).strftime("%Y-%m-%d")
        if self._game_sign_result_date != today:
            self.ToolsConfig._game_sign_result_data = {}
            self._game_sign_result_date = today

        return self.ToolsConfig.model_dump(context={"audience": "api"})

    async def update_community_results(
        self, formatted: dict[str, Any], *, replace: bool = False
    ) -> None:
        """合并、持久化并广播游戏社区结果。

        Args:
            formatted: 已按平台和账号分组的签到结果。
            replace: 是否按账号 UID 替换已有结果。
        """

        from app.tools.common.community import sign as _tool_community_sign_provider

        today = datetime.now(tz=_utils_constants.UTC8).strftime("%Y-%m-%d")
        existing = (
            self.ToolsConfig._game_sign_result_data
            if self._game_sign_result_date == today
            else {}
        )
        result = _tool_community_sign_provider.merge_community_sign_results(
            existing, formatted, replace=replace
        )
        self.ToolsConfig._game_sign_result_data = result
        self._game_sign_result_date = today
        _save_game_sign_result_snapshot(
            self.config_path / GAME_SIGN_RESULT_FILENAME,
            result,
            result_date=today,
        )

        try:
            from app.core import Publisher
            from app.core.ws import protocol
            from app.models.schema import WSGameSignResultData

            await Publisher.send(
                id=protocol.ID_GAME_SIGN,
                type=protocol.GAMESIGN_RESULT_UPDATED,
                data=WSGameSignResultData(
                    result=json.dumps(result, ensure_ascii=False)
                ),
            )
        except Exception as e:
            logger.warning(f"广播游戏社区结果失败: {e}")

    async def update_tools(self, data: Dict[str, Dict[str, Any]]) -> None:
        """更新工具设置"""

        logger.info("更新工具设置")

        await self.ToolsConfig.update(type(self.ToolsConfig).model_validate(data))

        logger.success("工具设置更新成功")

    # ==================== 游戏社区账号组 CRUD ====================

    async def get_game_sign_accounts(
        self, *, if_decrypt: bool = True
    ) -> Dict[str, Any]:
        """获取所有游戏社区账号组"""

        logger.debug("获取所有游戏社区账号组")

        return self.ToolsConfig.GameSign_Accounts.model_dump(
            context={"audience": "api" if if_decrypt else "persist"}
        )

    async def add_game_sign_account(self) -> tuple[uuid.UUID, Any]:
        """添加游戏社区账号组"""

        logger.info("添加游戏社区账号组")

        async with self._community_account_add_lock:
            from app.tools.common.community.accounts import next_community_account_name

            existing_names = []
            for account in self.ToolsConfig.GameSign_Accounts.values():
                try:
                    existing_names.append(account.GameSignAccount.Name)
                except (AttributeError, KeyError):
                    continue
            account_name = next_community_account_name(existing_names)
            uid = self.ToolsConfig.GameSign_Accounts.add(GameSignAccountGroup)
            await self.ToolsConfig.GameSign_Accounts.commit()
            config = self.ToolsConfig.GameSign_Accounts[uid]
            await config.update(
                type(config).model_validate(
                    {"GameSignAccount": {"Name": account_name}}
                ),
                check_visibility=False,
            )
            return uid, config

    def _clear_game_sign_account_results(self, account_id: str) -> None:
        """清除指定游戏社区账号的结果。"""

        today = datetime.now(tz=_utils_constants.UTC8).strftime("%Y-%m-%d")
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

        tools_file = self.ToolsConfig.persist_path
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
        """更新游戏社区账号组配置"""

        logger.info(f"更新游戏社区账号组: {account_id}")

        account_uid = uuid.UUID(account_id)
        account = self.ToolsConfig.GameSign_Accounts[account_uid]
        from app.tools.common.community import sign as _tool_community_sign_provider

        credential_fields = set(_tool_community_sign_provider.COMMUNITY_TOKEN_FIELDS)
        credential_changed = False

        for group, items in data.items():
            for name, value in items.items():
                if (
                    group == "GameSignAccount"
                    and name in credential_fields
                    and getattr(getattr(account, group), name) != value
                ):
                    credential_changed = True
                await account.update(
                    type(account).model_validate({group: {name: value}}),
                    check_visibility=False,
                )

        if credential_changed:
            await account.update(
                type(account).model_validate(
                    {
                        "GameSignAccount": {
                            "LastSignDate": datetime(
                                2000, 1, 1, tzinfo=_utils_constants.UTC8
                            )
                        }
                    }
                ),
                check_visibility=False,
            )
            self._clear_game_sign_account_results(account_id)

    async def delete_game_sign_account(self, account_id: str) -> None:
        """删除游戏社区账号组"""

        logger.info(f"删除游戏社区账号组: {account_id}")

        account_uid = uuid.UUID(account_id)
        self.ToolsConfig.GameSign_Accounts.remove(account_uid)
        await self.ToolsConfig.GameSign_Accounts.commit()
        self._clear_game_sign_account_results(account_id)

    async def reorder_game_sign_accounts(self, order: list[str]) -> None:
        """调整游戏社区账号组顺序"""

        logger.info("调整游戏社区账号组顺序")

        self.ToolsConfig.GameSign_Accounts.set_order([uuid.UUID(_) for _ in order])
        await self.ToolsConfig.GameSign_Accounts.commit()

    def obs_replay_options(self):
        """读取 OBS 连接与保留策略，服务层不依赖全局配置。"""
        from app.services import obs_replay as _service_obs_replay

        return _service_obs_replay.ObsReplayOptions(
            port=self.setting.Replay.Port,
            password=self.setting.Replay.Password,
        )

    async def get_setting(self) -> Dict[str, Any]:
        """获取全局设置"""

        logger.info("获取全局设置")

        data = self.setting.model_dump(context={"audience": "api"})
        return data

    async def update_setting(self, data: Dict[str, Dict[str, Any]]) -> None:
        """更新全局设置"""

        logger.info("更新全局设置")

        replay = data.get("Replay")
        if replay is not None:
            replay = {
                key: value
                for key, value in replay.items()
                if value is not None and key != "PasswordConfigured"
            }
            data = {**data, "Replay": replay}
        await self.setting.update(type(self.setting).model_validate(data))

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
                data = self.setting.Notify_CustomWebhooks.model_dump(
                    context={"audience": "api"}
                )
            else:
                entry = self.setting.Notify_CustomWebhooks[uuid.UUID(webhook_id)]
                return (
                    [{"uid": str(entry.uid), "type": type(entry).__name__}],
                    {str(entry.uid): entry.model_dump(context={"audience": "api"})},
                )

        else:
            logger.info(f"获取webhook设置: {script_id} - {user_id} - {webhook_id}")

            script_uid = uuid.UUID(script_id)
            user_uid = uuid.UUID(user_id)

            if webhook_id is None:
                data = (
                    self.ScriptConfig[script_uid]
                    .UserData[user_uid]
                    .Notify_CustomWebhooks.model_dump(context={"audience": "api"})
                )
            else:
                entry = (
                    self.ScriptConfig[script_uid]
                    .UserData[user_uid]
                    .Notify_CustomWebhooks[uuid.UUID(webhook_id)]
                )
                return (
                    [{"uid": str(entry.uid), "type": type(entry).__name__}],
                    {str(entry.uid): entry.model_dump(context={"audience": "api"})},
                )

        index = data["order"]
        return list(index), data["data"]

    async def add_webhook(
        self, script_id: Optional[str], user_id: Optional[str]
    ) -> tuple[uuid.UUID, Webhook]:
        """添加webhook配置"""

        if script_id is None and user_id is None:
            logger.info("添加全局webhook配置")

            uid = self.setting.Notify_CustomWebhooks.add(Webhook)
            await self.setting.Notify_CustomWebhooks.commit()
            config = self.setting.Notify_CustomWebhooks[uid]
            return uid, config

        else:
            logger.info(f"添加webhook配置: {script_id} - {user_id}")

            script_uid = uuid.UUID(script_id)
            user_uid = uuid.UUID(user_id)

            uid = (
                self.ScriptConfig[script_uid]
                .UserData[user_uid]
                .Notify_CustomWebhooks.add(Webhook)
            )
            await (
                self.ScriptConfig[script_uid]
                .UserData[user_uid]
                .Notify_CustomWebhooks.commit()
            )
            config = (
                self.ScriptConfig[script_uid]
                .UserData[user_uid]
                .Notify_CustomWebhooks[uid]
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

            for group, items in data.items():
                for name, value in items.items():
                    await self.setting.Notify_CustomWebhooks[webhook_uid].update(
                        type(
                            self.setting.Notify_CustomWebhooks[webhook_uid]
                        ).model_validate({group: {name: value}}),
                        check_visibility=False,
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
                        .update(
                            type(
                                self.ScriptConfig[script_uid]
                                .UserData[user_uid]
                                .Notify_CustomWebhooks[webhook_uid]
                            ).model_validate({group: {name: value}}),
                            check_visibility=False,
                        )
                    )

    async def del_webhook(
        self, script_id: Optional[str], user_id: Optional[str], webhook_id: str
    ) -> None:
        """删除 webhook 配置"""

        webhook_uid = uuid.UUID(webhook_id)

        if script_id is None and user_id is None:
            logger.info(f"删除全局 webhook 配置: {webhook_id}")

            self.setting.Notify_CustomWebhooks.remove(webhook_uid)
            await self.setting.Notify_CustomWebhooks.commit()

        else:
            logger.info(f"删除 webhook 配置: {script_id} - {user_id} - {webhook_id}")

            script_uid = uuid.UUID(script_id)
            user_uid = uuid.UUID(user_id)

            self.ScriptConfig[script_uid].UserData[
                user_uid
            ].Notify_CustomWebhooks.remove(webhook_uid)
            await (
                self.ScriptConfig[script_uid]
                .UserData[user_uid]
                .Notify_CustomWebhooks.commit()
            )

    @property
    def proxy(self) -> Optional[httpx.Proxy]:
        """获取代理设置，返回适用于 httpx 的代理对象"""
        proxy_addr = normalize_proxy_address(self.setting.Update.ProxyAddress)
        if not proxy_addr:
            return None

        try:
            proxy = httpx.Proxy(proxy_addr)
            logger.info(f"使用代理: {proxy.url}")
            return proxy
        except Exception:
            logger.warning("代理配置无效，请检查代理地址")
            return None

    @property
    def proxy_url(self) -> Optional[str]:
        """代理地址字符串（含协议、保留 userinfo），给子进程环境变量用；不打日志。

        MFW 运行池的 uv / pip、worker 与项目 agent 都经
        ``host_environment.subprocess_proxy_scope`` 拿到它；每次准备环境都会读，
        这里不像 ``proxy`` 那样每次访问都记一行「使用代理」。
        """

        return normalize_proxy_address(self.setting.Update.ProxyAddress)

    async def get_proxy_overview(self) -> Dict[str, Any]:
        """获取代理情况概览信息"""

        logger.info("获取代理情况概览信息")

        from app.core import History

        users = await History.get_overview(
            day=datetime.now(tz=_utils_constants.UTC4).date()
        )
        return {
            username: {
                "LastProxyDate": (
                    entry.latest_time.isoformat()
                    if entry.latest_time
                    else "暂无代理数据"
                ),
                "ProxyTimes": entry.execute_count,
                "ErrorTimes": entry.error_count,
                "ErrorInfo": {
                    str(key): value for key, value in entry.error_info.items()
                },
            }
            for username, entry in users.items()
        }

    async def get_script_combox(self):
        """获取脚本下拉框信息"""

        logger.info("开始获取脚本下拉框信息")
        data = [{"label": "未选择", "value": "-"}]
        for uid, script in self.ScriptConfig.items():
            data.append(
                {
                    "label": f"{_utils_constants.TYPE_BOOK[type(script).__name__]} - {script.Info.Name}",
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
            data.append({"label": f"队列 - {queue.Info.Name}", "value": str(uid)})
        for uid, script in self.ScriptConfig.items():
            if not script.is_locked:
                data.append(
                    {
                        "label": f"脚本 - {_utils_constants.TYPE_BOOK[type(script).__name__]} - {script.Info.Name}",
                        "value": str(uid),
                    }
                )
        logger.success("任务下拉框信息获取成功")

        return data

    async def get_plan_combox(self, consumer: PlanComboxConsumer):
        """获取指定消费方的计划下拉框信息"""

        consumer_config = next(
            (item for item in PLAN_BOOK.values() if item["consumer"] == consumer), None
        )
        if consumer_config is None:
            raise TypeError(f"不支持的计划表消费方类型: {consumer}")

        plan_class = consumer_config["config_class"]
        logger.info(f"开始获取 {consumer} 计划下拉框信息")
        data = [{"label": "固定", "value": "Fixed"}]
        for uid, plan in self.PlanConfig.items():
            if isinstance(plan, plan_class):
                data.append({"label": plan.Info.Name, "value": str(uid)})
        logger.success(f"{consumer} 计划下拉框信息获取成功")

        return data

    async def get_emulator_combox(self):
        """获取模拟器下拉框信息"""

        logger.info("开始获取模拟器下拉框信息")
        data = [{"label": "未选择", "value": "-"}]
        for uid, emulator in self.EmulatorConfig.items():
            data.append({"label": emulator.Info.Name, "value": str(uid)})
        logger.success("模拟器下拉框信息获取成功")
        return data

    async def get_emulator_devices_combox(self, emulator_id: str):
        """获取模拟器多开实例下拉框信息"""

        logger.info("开始获取模拟器下拉框信息")

        if emulator_id == "-":
            return []

        if self.EmulatorConfig[uuid.UUID(emulator_id)].Info.Type == "general":
            logger.info("通用模拟器不支持扫描多开实例, 返回空列表")
            return []

        data = [{"label": "未选择", "value": "-"}]

        from app.core import EmulatorManager

        devices = await (
            await EmulatorManager.get_emulator_instance(emulator_id)
        ).list_devices()
        for index, title in devices.items():
            data.append({"label": title, "value": index})

        logger.success("模拟器下拉框信息获取成功")

        return data

    async def get_notice(self) -> tuple[bool, Dict[str, str]]:
        """获取公告信息"""

        if (
            datetime.now().astimezone() - timedelta(hours=1)
            < self.setting.Data.LastNoticeUpdated
        ):
            logger.info("一小时内已进行过一次检查, 直接使用缓存的公告信息")
            return (False, json.loads(self.setting.Data.Notice).get("notice_dict", {}))

        logger.info("开始从 AUTO-MAS 服务器获取公告信息")
        try:
            async with httpx.AsyncClient(
                proxy=self.proxy, follow_redirects=True
            ) as client:
                response = await client.get(
                    "https://data.auto-mas.top/api/v1/files/auto-mas/Client/notice/download",
                    headers={"If-None-Match": self.setting.Data.NoticeETag},
                )
                if response.status_code == 304:
                    logger.info("公告未更新，使用本地缓存的公告信息")
                    await self.setting.update(
                        type(self.setting).model_validate(
                            {"Data": {"LastNoticeUpdated": datetime.now().astimezone()}}
                        ),
                        check_visibility=False,
                    )
                elif response.status_code == 200:
                    logger.info("公告已更新，要求展示公告信息")
                    await self.setting.update(
                        type(self.setting).model_validate(
                            {"Data": {"LastNoticeUpdated": datetime.now().astimezone()}}
                        ),
                        check_visibility=False,
                    )
                    await self.setting.update(
                        type(self.setting).model_validate(
                            {
                                "Data": {
                                    "NoticeETag": response.headers.get("ETag")
                                    or response.headers.get("etag")
                                    or ""
                                }
                            }
                        ),
                        check_visibility=False,
                    )
                    await self.setting.update(
                        type(self.setting).model_validate(
                            {"Data": {"IfShowNotice": True}}
                        ),
                        check_visibility=False,
                    )
                    await self.setting.update(
                        type(self.setting).model_validate(
                            {
                                "Data": {
                                    "Notice": json.dumps(
                                        response.json(), ensure_ascii=False
                                    )
                                }
                            }
                        ),
                        check_visibility=False,
                    )
                else:
                    logger.warning(
                        f"无法从 AUTO-MAS 服务器获取公告信息:{response.text}"
                    )
        except Exception as e:
            logger.warning(f"无法从 AUTO-MAS 服务器获取公告信息: {e}")

        return (
            self.setting.Data.IfShowNotice,
            json.loads(self.setting.Data.Notice).get("notice_dict", {}),
        )

    async def _settle_m9a_migration(self, report: Any) -> None:
        """旧 M9A 配置迁完之后的两件收尾：原先有归档的脚本用 MaaFW 池归档一次；结果攒成系统通知。

        旧 M9A 池（``data/<sid>/M9ABackups/``）不再被列出也不支持恢复，目录原地保留。此时
        副本还没建，native 池按来源目录归档；引擎首次运行前还会按有效根再归档一次，指纹去重。
        """

        from app.task.MaaFW.tools.backup_archive import (
            archive_mas_runtime_backup,
            archive_native_backup,
            read_overlay_values,
        )

        archived: list[str] = []
        for uid_text in report.migrated_uids:
            legacy_pool = self.data_path / uid_text / "M9ABackups"
            if not legacy_pool.is_dir():
                continue
            try:
                script_config = self.ScriptConfig[uuid.UUID(uid_text)]
            except (KeyError, ValueError):
                continue
            source = str(script_config.Info.Path or "").strip()
            try:
                if source and Path(source).is_dir():
                    await asyncio.to_thread(
                        archive_native_backup, uid_text, Path(source)
                    )
                for user_uid, user_config in script_config.UserData.items():
                    await asyncio.to_thread(
                        archive_mas_runtime_backup,
                        uid_text,
                        str(user_uid),
                        read_overlay_values(user_config),
                    )
                archived.append(str(script_config.Info.Name or uid_text[:8]))
            except Exception as exc:  # noqa: BLE001 - 归档失败不该挡住启动
                logger.warning(f"M9A 迁移后归档失败（{uid_text[:8]}）：{exc}")
        lines = list(report.summary_lines())
        if report.failure:
            lines.insert(
                0,
                "旧 M9A 配置迁移失败，旧脚本的任务队列与周期记录可能已被重置；"
                f"迁移前的原文件已备份为 {report.backup_path.name if report.backup_path else '（备份也失败）'}，"
                f"原因：{report.failure}",
            )
        if archived:
            lines.append("原先有归档的脚本已按新格式归档一次：" + "、".join(archived))
        # 失败行已经带了备份文件名（或「备份也失败」），不再重复一遍
        if report.backup_path is not None and not report.failure:
            lines.append(f"迁移前的配置已备份为 {report.backup_path.name}")
        self.startup_notices.append(
            {
                "level": "warning" if report.needs_attention else "info",
                "title": (
                    "M9A 脚本迁移失败"
                    if report.failure
                    else (
                        "M9A 脚本已并入 MFW 引擎"
                        if report.migrated_scripts
                        else "已按项目识别出 M9A 脚本"
                    )
                ),
                "lines": lines,
            }
        )

    def script_config_loaded_intact(self) -> bool:
        """确认脚本集合加载成功；空表再核对持久文件，避免把损坏配置当成无引用。"""

        if not self._script_configs_loaded:
            return False
        if len(self.ScriptConfig) > 0:
            return True
        path = self.ScriptConfig.persist_path
        if path is None or not path.is_file():
            return True
        try:
            data = _utils_io.read_dict_file(path, allow_empty=True)
        except (OSError, ValueError):
            return False
        return not bool(data.get("order"))

    def clean_debug_diagnostics(self) -> None:
        """清理 debug 目录下过期的失败诊断文件。

        自动扫描 ``debug/`` 下全部子目录（各专项的登录/切号/启动器失败诊断，
        新专项落盘即纳入清理，无需登记名单）：诊断日志与截图统一按固定保留
        天数清理，不跟随历史记录保留时间——诊断文件不是用户数据，解绑后任何
        配置下都不会无界累积。失败截图另受每目录独立的大小上限约束，超限
        从旧到新回收——一个专项的截图风暴不会挤掉其他专项的证据。

        纯同步文件 IO，调用方在事件循环里请经 ``asyncio.to_thread`` 执行。
        """

        cutoff = time.time() - DIAGNOSTIC_RETENTION_DAYS * 86400

        debug_root = self.debug_path
        if not debug_root.is_dir():
            return

        deleted_count = 0
        screenshot_deleted_count = 0
        for folder in debug_root.iterdir():
            if not folder.is_dir():
                continue

            screenshot_files: list[tuple[Path, float, int]] = []
            screenshot_size = 0
            for file in folder.iterdir():
                if (
                    not file.is_file()
                    or file.suffix.lower() not in DIAGNOSTIC_FILE_SUFFIXES
                ):
                    continue
                try:
                    file_stat = file.stat()
                except OSError as exc:
                    logger.warning(f"诊断文件清理失败: {file} - {exc}")
                    continue
                if file_stat.st_mtime < cutoff:
                    try:
                        file.unlink()
                    except OSError as exc:
                        logger.warning(f"诊断文件清理失败: {file} - {exc}")
                    else:
                        deleted_count += 1
                    continue
                if file.suffix.lower() in DIAGNOSTIC_SCREENSHOT_SUFFIXES:
                    screenshot_files.append(
                        (file, file_stat.st_mtime, file_stat.st_size)
                    )
                    screenshot_size += file_stat.st_size

            for file, _, file_size in sorted(
                screenshot_files, key=lambda item: item[1]
            ):
                if screenshot_size <= DIAGNOSTIC_SCREENSHOT_MAX_BYTES:
                    break
                try:
                    file.unlink()
                except OSError as exc:
                    logger.warning(f"失败截图清理失败: {file} - {exc}")
                    continue
                screenshot_size -= file_size
                screenshot_deleted_count += 1

        if deleted_count:
            logger.success(f"清理完成: {deleted_count} 个过期诊断文件")
        if screenshot_deleted_count:
            logger.success(f"清理完成: {screenshot_deleted_count} 个超限失败截图")
