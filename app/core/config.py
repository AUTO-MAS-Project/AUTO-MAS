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
import json
import os
import re
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
    from app.utils import config_restore as _utils_config_restore

from app.config import ConfigCollection, ConfigEntry, NodeState, config_manager
from app.core.config_upgrade import (
    CONFIG_FILES,
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
from app.task.M9A.migration import (
    migrate_legacy_m9a_scripts,
    normalize_m9a_managed_entries,
    repair_m9a_migration_losses,
)
from app.utils import IS_WINDOWS, get_logger, is_supervised
from app.utils import community as _utils_community
from app.utils import constants as _utils_constants
from app.utils import io as _utils_io
from app.utils import paths as _utils_paths

# 孤儿 venv 的宽限期：刚动过的一律不碰，避免与正在准备环境的运行抢。
MAAFW_AGENT_VENV_GRACE_SECONDS = 60 * 60
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

        self._restore_pool_resolver: (
            Callable[["ConfigEntry"], list["_utils_config_restore.ConfigRestorePool"]]
            | None
        ) = None

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
            if (Path.cwd() / "environment/git/bin/git.exe").exists():
                os.environ["GIT_PYTHON_GIT_EXECUTABLE"] = str(
                    Path.cwd() / "environment/git/bin/git.exe"
                )
            try:
                from git import Repo

                # .git 随源码走：受 AUTO-MAS-Runtime 监督时源码在 <app-root>/repo/，
                # 工作目录（app-root）下没有仓库，不能再按 Path.cwd() 打开
                self._repo = Repo(_utils_paths.SOURCE_ROOT)
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
        from app.services.telemetry import set_telemetry_enabled

        async def on_self_start(sender, event):
            await System.set_SelfStart(event.value)

        async def on_allow_sleep(sender, event):
            await System.set_Sleep(event.value)

        def on_telemetry(sender, event):
            set_telemetry_enabled(event.value)

        async def on_video_limit(sender, event):
            from app.core.history import history_store

            try:
                report = await history_store.set_video_limit(
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
        from app.core.community_activity import connect_community_activity_cache

        connect_community_activity_cache(self.ToolsConfig, setting=self.setting)
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
        set_telemetry_enabled(self.setting.Function.IfEnableTelemetry)

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
                await self._archive_legacy_hsr_direct_snapshots(script_path)
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
        for script in self.ScriptConfig.values():
            if (
                isinstance(script, MaaEndConfig)
                and script.Info.Path
                and script._preload_task is None
            ):
                script._preload_task = asyncio.create_task(script.preload_resource())
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

                if (Path.cwd() / "config/config.json").exists():
                    (Path.cwd() / "config/config.json").rename(
                        Path.cwd() / "config/Config.json"
                    )
                # 保留尚待后续阶段转换的旧键；不提前按新字段表加载和裁剪。
                legacy_setting = LegacyConfig()
                await legacy_setting.connect(self.config_path / "Config.json")

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
                            uid = legacy_uid(MaaPlanConfig)
                            await legacy_plans.put(
                                uid=uid,
                                type_name="MaaPlanConfig",
                                payload=maa_plan_config,
                            )
                            plan_dict[MaaPlanConfig.name] = str(uid)

                # 旧引用校验器会把“禁用”纠正为 '-'；中间文档直接使用该标记。
                script_dict: dict[str, str] = {"禁用": "-"}

                if (Path.cwd() / "config/MaaConfig").exists():
                    for MaaConfig in (Path.cwd() / "config/MaaConfig").iterdir():
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
                    data.setdefault("Data", {})["LastStageUpdated"] = (
                        "2000-01-01 00:00:00"
                    )
                    data["Data"]["Stage"] = "{ }"
                    function = data.setdefault("Function", {})
                    function["IfBlockAd"] = function.get(
                        "IfBlockAd", function.get("IfSkipMumuSplashAds", False)
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
            _config_uid = self.ScriptConfig.add(CLASS_BOOK[script], payload=payload)
            await self.ScriptConfig.commit()
            _config_entry = self.ScriptConfig[_config_uid]
            return _config_uid, _config_entry
        else:
            script_uid = uuid.UUID(script_id)

            if not isinstance(self.ScriptConfig[script_uid], CLASS_BOOK[script]):
                raise TypeError(f"脚本配置类型不匹配: {script_id} {script}")

            document = self.ScriptConfig[script_uid].model_dump(
                context={"audience": "persist"}
            )
            new_uid = self.ScriptConfig.add(
                CLASS_BOOK[script], payload=document, regenerate_uuids=True
            )
            await self.ScriptConfig.commit()
            new_config = self.ScriptConfig[new_uid]
            user_ids = {
                item["uid"]: uid
                for item, uid in zip(
                    document["UserData"]["order"], new_config.UserData.keys()
                )
            }

            # 复制内嵌副本：来源目录允许被删，只复制配置的话新脚本可能无处可跑。
            if isinstance(new_config, MaaFWConfig):
                # 开发者模式（跟随来源目录）不随复制带过去：复制出来的是普通脚本，挂源脚本原
                # 渠道组的版本（见 _clone_embedded_copy_for_script）。
                await new_config.update(
                    type(new_config).model_validate(
                        {"Embedded": {"FollowSource": False}}
                    ),
                    check_visibility=False,
                )
                await self._clone_embedded_copy_for_script(
                    str(script_id),
                    str(new_uid),
                    source_config=self.ScriptConfig[script_uid],
                )

            # 复制用户数据
            if (Path.cwd() / f"data/{script_id}").exists():
                shutil.copytree(
                    Path.cwd() / f"data/{script_id}",
                    Path.cwd() / f"data/{new_uid}",
                    dirs_exist_ok=True,
                )
                for old_user, new_user in user_ids.items():
                    if (Path.cwd() / f"data/{new_uid}/{old_user}").exists():
                        (Path.cwd() / f"data/{new_uid}/{old_user}").rename(
                            Path.cwd() / f"data/{new_uid}/{new_user}"
                        )

            return new_uid, new_config

    async def _clone_embedded_copy_for_script(
        self, source_script_id: str, target_script_id: str, *, source_config: Any
    ) -> None:
        """复制脚本时连视图一起建：从源脚本挂着的载荷物化（载荷不可变，不需要源空闲、
        不带源的运行期状态）。失败不让复制脚本本身失败，下次运行前按来源 / 载荷重建。

        源开着开发者模式时取它原渠道（源的 ``Update.Channel``）组的 latest；组里还没有载荷
        （或源是源码形态）就先不建视图，复制出来的脚本第一次运行前按来源目录导入（来源也不在时
        按同来源兄弟 / 已登记的版本重建，与视图丢了是同一条路）。
        """

        from app.task.MaaFW.tools.embedded.embedded_project import (
            FollowSourceCloneUnavailable,
            clone_embedded_copy,
            embedded_project_dir,
            is_source_form,
        )
        from app.task.MaaFW.tools.embedded.project_path import (
            release_project_path,
            try_reserve_project_path,
        )

        group_channel = str(source_config.Update.Channel or "stable")
        source_form = is_source_form(source_config)

        target_key = await try_reserve_project_path(
            embedded_project_dir(target_script_id)
        )
        if target_key is None:
            return
        try:
            await asyncio.to_thread(
                lambda: clone_embedded_copy(
                    source_script_id,
                    target_script_id,
                    group_channel=group_channel,
                    source_form=source_form,
                )
            )
        except FollowSourceCloneUnavailable as exc:
            logger.info(f"复制脚本时先不建视图，第一次运行前按来源目录导入: {exc}")
        except Exception as exc:  # noqa: BLE001 - 失败下次运行会按来源 / 载荷重建
            logger.warning(f"复制脚本时建视图失败，将按需重建: {exc}")
        finally:
            await release_project_path(target_key)

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

    async def get_maaend_options(self, script_id: str) -> dict[str, Any]:
        """读取指定 MaaEnd 安装目录中的动态选项。"""

        script_config = self.ScriptConfig[uuid.UUID(script_id)]
        if not isinstance(script_config, MaaEndConfig):
            raise TypeError("脚本配置类型错误, 不是 MaaEnd 类型")
        root_path = str(script_config.Info.Path or "").strip()
        if not root_path:
            raise ValueError("MaaEnd 路径未配置")

        options = script_config.get_loaded_resource()
        game_path = str(script_config.Game.Path or "").strip()
        if game_path:
            from app.task.MaaFW.tools.embedded.game_resolution import (
                read_unity_display_type,
                read_unity_resolution,
            )

            exe_path = Path(game_path)
            original = await asyncio.to_thread(read_unity_resolution, exe_path)
            if original is not None:
                options["originalResolution"] = f"{original[0]}x{original[1]}"
            options["originalDisplayType"] = await asyncio.to_thread(
                read_unity_display_type,
                exe_path,
                preferred_value_name="video_full_screen_h1998742411",
            )
        return options

    def get_baah_config_names(self, script_id: str) -> list[str]:
        """读取指定 BAAH 安装目录下已有的配置文件名（不含 .json 后缀）。"""

        script_config = self.ScriptConfig[uuid.UUID(script_id)]
        if not isinstance(script_config, BAAHConfig):
            raise TypeError("脚本配置类型错误, 不是 BAAH 类型")

        from app.task.BAAH.tools import CONFIG_DIR_NAME, list_config_names

        baah_path = script_config.Script.BAAHPath
        if baah_path is None:
            return []
        return list_config_names(baah_path.parent / CONFIG_DIR_NAME)

    async def update_script(
        self, script_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新脚本配置"""

        logger.info(f"更新脚本配置: {script_id}")

        uid = uuid.UUID(script_id)

        if self.ScriptConfig[uid].is_locked:
            raise RuntimeError(f"脚本 {script_id} 正在运行, 无法更新配置项")

        if isinstance(self.ScriptConfig[uid], MaaEndConfig):
            from app.services.endfield_launcher import is_launcher_exe

            launcher_path = (data.get("Game") or {}).get("LauncherPath")
            if launcher_path and not is_launcher_exe(Path(launcher_path)):
                raise ValueError(
                    "终末地启动器路径无效，请选择鹰角官方启动器 Launcher.exe 或 Games.exe"
                )

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
        was_maafw = isinstance(script_config, MaaFWConfig)
        if isinstance(script_config, ZzzOdConfig):
            from app.task.ZzzOd.api_service import get_service

            await get_service(self).recovery.recycle_script_slots(script_id)

        self.ScriptConfig.remove(uid)
        await self.ScriptConfig.commit()
        if was_maafw:
            # 它的共享 runtime 可能就此无人引用；后台对账一轮，不拖慢删除响应。
            from app.task.MaaFW.tools.embedded.pool_reconcile import (
                reconcile_in_background,
            )

            reconcile_in_background("script-deleted")
        # 数据目录里可能有只读文件（如脚本配置目录快照带进来的 .git 对象）：裸
        # rmtree 删到它们会抛 PermissionError，而此时配置已经移除，目录残留在磁盘上、
        # 再点这个脚本还会报「配置项不存在」。目录删除是阻塞 IO（force_rmtree 内部
        # 还有 sleep 重试），放线程里跑，别让事件循环跟着等。
        script_data_dir = Path.cwd() / f"data/{uid}"
        if script_data_dir.exists():
            await asyncio.to_thread(_utils_io.force_rmtree, script_data_dir)
        # MFW 内嵌副本跟着脚本 ID 走，不放在 data/<uid>/ 下（那里会被配置备份整目录
        # 快照），所以这里单独删。
        from app.task.MaaFW.tools.embedded.embedded_project import embedded_project_dir

        embedded_copy = embedded_project_dir(str(uid))
        if embedded_copy.exists():
            await asyncio.to_thread(_utils_io.force_rmtree, embedded_copy)

    async def reorder_script(self, index_list: list[str]) -> None:
        """重新排序脚本"""

        logger.info(f"重新排序脚本: {index_list}")

        self.ScriptConfig.set_order([uuid.UUID(_) for _ in index_list])
        await self.ScriptConfig.commit()

    async def import_script_from_share(
        self, script_id: str, config_key: str, version_no: Optional[int]
    ) -> None:
        """从「AUTO-MAS 配置中心」导入通用脚本配置。

        Args:
            script_id: 目标通用脚本ID。
            config_key: 配置中心的配置标识。
            version_no: 版本号, 为空表示已发布的最新版本。

        Raises:
            KeyError: 脚本不存在。
            TypeError: 脚本不是通用脚本配置。
            ConfigCenterError: 下载失败或内容不是通用脚本配置。
        """

        from app.services import ConfigCenter

        logger.info(f"从配置中心加载脚本配置: {script_id} - {config_key}")
        uid = uuid.UUID(script_id)

        if uid not in self.ScriptConfig:
            logger.error(f"{script_id} 不存在")
            raise KeyError(f"脚本 {script_id} 不存在")
        if not isinstance(self.ScriptConfig[uid], GeneralConfig):
            logger.error(f"{script_id} 不是通用脚本配置")
            raise TypeError(f"脚本 {script_id} 不是通用脚本配置")

        data = await ConfigCenter.download_template(config_key, version_no)
        await self.ScriptConfig[uid].update(
            GeneralConfig.model_validate(GeneralConfig.normalize_payload(data)),
            check_visibility=False,
        )

        logger.success(f"{script_id} 配置加载成功")

    async def build_share_config(
        self, script_id: str, config_name: str
    ) -> tuple[dict, List[Dict[str, str]]]:
        """整理待分享的通用脚本配置。

        用户数据（SubConfigsInfo）整体丢弃, 路径类配置项做占位替换, 剩下仍然可疑的内容
        以风险项返回, 由用户确认后才允许上传。

        Args:
            script_id: 目标通用脚本ID。
            config_name: 分享时使用的配置名称。

        Returns:
            脱敏后的配置字典, 以及仍需用户确认的风险项列表。

        Raises:
            KeyError: 脚本不存在。
            TypeError: 脚本不是通用脚本配置。
        """

        uid = uuid.UUID(script_id)

        if uid not in self.ScriptConfig:
            logger.error(f"{script_id} 不存在")
            raise KeyError(f"脚本 {script_id} 不存在")
        if not isinstance(self.ScriptConfig[uid], GeneralConfig):
            logger.error(f"{script_id} 不是通用脚本配置")
            raise TypeError(f"脚本 {script_id} 不是通用脚本配置")

        temp = self.ScriptConfig[uid].model_dump(context={"audience": "persist"})
        temp.pop("UserData", None)
        temp.pop("Notify_CustomWebhooks", None)
        temp.pop("ui", None)
        temp = await self.remove_privacy_info(temp, config_name)

        return temp, self.scan_privacy_risks(temp)

    async def upload_script_to_share(
        self, script_id: str, config_name: str, description: str, acknowledged: bool
    ) -> None:
        """以当前授权用户的身份把配置提交到「AUTO-MAS 配置中心」等待审核。

        Args:
            script_id: 目标通用脚本ID。
            config_name: 配置名称。
            description: 配置描述。
            acknowledged: 用户是否已确认分享前检查出的风险项。

        Raises:
            ConfigCenterError: 未授权、存在未确认的风险项或上传被拒绝。
        """

        from app.services import ConfigCenter, ConfigCenterError

        logger.info(f"上传配置到配置中心: {script_id} - {config_name}")

        config, risks = await self.build_share_config(script_id, config_name)
        if risks and not acknowledged:
            logger.warning(f"分享前检查到 {len(risks)} 项待确认内容, 已阻止上传")
            raise ConfigCenterError("配置中仍有可能泄露隐私的内容, 请确认后再分享")

        await ConfigCenter.upload_config(config_name, description, config)

    async def remove_privacy_info(self, config: dict, name: str) -> dict:
        """移除配置中可能存在的隐私信息"""

        config["Info"]["Name"] = name
        root_value = config["Info"]["RootPath"]
        root_path = Path(root_value) if root_value else None
        for path in ["ScriptPath", "ConfigPath", "LogPath", "TrackProcessExe"]:
            path_value = config["Script"][path]
            if not path_value:
                continue
            script_path = Path(path_value)
            if root_path is not None and script_path.is_relative_to(root_path):
                config["Script"][path] = str(
                    Path(r"C:/脚本根目录") / script_path.relative_to(root_path)
                )
            elif IS_WINDOWS and script_path.is_relative_to(Path(os.environ["APPDATA"])):
                config["Script"][path] = (
                    f"%APPDATA%/{script_path.relative_to(Path(os.environ['APPDATA']))}"
                )
        if root_path is not None:
            config["Info"]["RootPath"] = str(Path(r"C:/脚本根目录"))

        # 上面只覆盖脚本自身的路径项；游戏路径、命令行等自由文本同样会带出本机用户名，统一打码
        for items in config.values():
            if not isinstance(items, dict):
                continue
            for key, value in items.items():
                if isinstance(value, str) and value:
                    items[key] = self._mask_home_path(value)

        return config

    @staticmethod
    def _mask_home_path(value: str) -> str:
        """把值里出现的本机用户目录替换成占位符"""

        home = str(Path.home())
        if not home:
            return value

        masked = value
        for candidate in {home, home.replace("\\", "/")}:
            # 要求用户目录后面是分隔符或行尾, 否则 C:\Users\qiyin 会切掉 C:\Users\qiyinxi 的一截
            masked = re.sub(
                rf"{re.escape(candidate)}(?=[\\/]|$)",
                "%USERPROFILE%",
                masked,
                flags=re.IGNORECASE,
            )
        return masked

    def scan_privacy_risks(self, config: dict) -> List[Dict[str, str]]:
        """检查脱敏后的配置里是否还残留不该分享的内容。

        自动脱敏只能处理已知的路径项, 命令行参数、日志规则这类自由文本仍可能带出账号、
        密码、令牌或本机绝对路径, 这里把它们挑出来交给用户确认。

        Args:
            config: 已经过 remove_privacy_info 处理的配置字典。

        Returns:
            风险项列表, 每项包含配置项名称与风险说明。
        """

        placeholders = ("C:\\脚本根目录", "C:/脚本根目录", "%APPDATA%", "%USERPROFILE%")
        user_name = Path.home().name
        risks: List[Dict[str, str]] = []

        for group, items in config.items():
            if not isinstance(items, dict):
                continue
            for key, value in items.items():
                if not isinstance(value, str) or not value.strip():
                    continue

                field = f"{group}.{key}"
                if re.search(
                    r"(?i)(password|passwd|pwd|token|secret|api[_-]?key|cookie|session"
                    r"|密码|密钥|口令)\s*[=:\s]\s*\S",
                    value,
                ):
                    risks.append({"field": field, "reason": "疑似包含账号、密码或令牌"})
                    continue
                if re.search(r"://[^/\s:@]+:[^/\s@]+@", value):
                    risks.append({"field": field, "reason": "链接中带有账号密码"})
                    continue
                if len(user_name) > 2 and user_name.lower() in value.lower():
                    risks.append({"field": field, "reason": "包含本机用户名"})
                    continue

                probe = value
                for placeholder in placeholders:
                    probe = probe.replace(placeholder, "")
                # 盘符前不能再跟字母, 否则 https:// 这类协议头会被当成 C:\ 一样的盘符路径
                if re.search(r"(?<![A-Za-z])[A-Za-z]:[\\/]", probe) or "\\\\" in probe:
                    risks.append({"field": field, "reason": "包含本机绝对路径"})

        return risks

    async def get_user(
        self, script_id: str, user_id: Optional[str]
    ) -> tuple[list, dict]:
        """获取用户配置"""

        logger.info(f"获取用户配置: {script_id} - {user_id}")

        uid = uuid.UUID(script_id)

        script_config = self.ScriptConfig[uid]
        if isinstance(script_config, MaaFWConfig):
            # 新用户的空任务队列按项目默认写成实打实的队列（含特调 M9A / MSS）：用户页
            # 看到的就是运行时会跑的。建用户时项目可能还没导入，所以读的时候再补一次
            from app.task.MaaFW.tools.embedded.default_snapshot import (
                fill_default_task_snapshots,
            )

            await fill_default_task_snapshots(
                script_id,
                script_config,
                None if user_id is None else [str(uuid.UUID(user_id))],
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

        # 根据脚本类型选择添加对应用户配置
        if isinstance(script_config, MaaConfig):
            uid = script_config.UserData.add(MaaUserConfig, payload=payload)
            await script_config.UserData.commit()
            config = script_config.UserData[uid]
        elif isinstance(script_config, SrcConfig):
            uid = script_config.UserData.add(SrcUserConfig, payload=payload)
            await script_config.UserData.commit()
            config = script_config.UserData[uid]
        elif isinstance(script_config, GeneralConfig):
            uid = script_config.UserData.add(GeneralUserConfig, payload=payload)
            await script_config.UserData.commit()
            config = script_config.UserData[uid]
        elif isinstance(script_config, OkwwConfig):
            uid = script_config.UserData.add(OkwwUserConfig, payload=payload)
            await script_config.UserData.commit()
            config = script_config.UserData[uid]
            try:
                from app.task.Okww.tools.config_dir import ensure_user_config_dir

                await ensure_user_config_dir(
                    script_id=script_id,
                    user_id=str(uid),
                    base=str(config.Info.Base or _utils_constants.BASE_SHARED),
                )
            except Exception:
                # 配置初始化失败时回滚用户，避免留下无法运行的半成品用户。
                script_config.UserData.remove(uid)
                await script_config.UserData.commit()
                raise
        elif isinstance(script_config, OkNteConfig):
            uid = script_config.UserData.add(OkNteUserConfig, payload=payload)
            await script_config.UserData.commit()
            config = script_config.UserData[uid]
        elif isinstance(script_config, MaaEndConfig):
            uid = script_config.UserData.add(MaaEndUserConfig, payload=payload)
            await script_config.UserData.commit()
            config = script_config.UserData[uid]
        elif isinstance(script_config, MaaFWConfig):
            # 含特调子类（M9A / MSS）：用户类由脚本类的 USER_CONFIG_CLASS 决定。
            uid = script_config.UserData.add(
                script_config.USER_CONFIG_CLASS, payload=payload
            )
            await script_config.UserData.commit()
            config = script_config.UserData[uid]
            # 空任务队列按项目默认写成实打实的队列；项目还没导入时留到读用户、运行前再补
            from app.task.MaaFW.tools.embedded.default_snapshot import (
                fill_default_task_snapshots,
            )

            await fill_default_task_snapshots(script_id, script_config, [str(uid)])
        elif isinstance(script_config, HSRConfig):
            uid = script_config.UserData.add(HSRUserConfig, payload=payload)
            await script_config.UserData.commit()
            config = script_config.UserData[uid]
        elif isinstance(script_config, BetterGIConfig):
            uid = script_config.UserData.add(BetterGIUserConfig, payload=payload)
            await script_config.UserData.commit()
            config = script_config.UserData[uid]
        elif isinstance(script_config, ZzzOdConfig):
            uid = script_config.UserData.add(ZzzOdUserConfig, payload=payload)
            await script_config.UserData.commit()
            config = script_config.UserData[uid]
        elif isinstance(script_config, BAAHConfig):
            uid = script_config.UserData.add(BAAHUserConfig, payload=payload)
            await script_config.UserData.commit()
            config = script_config.UserData[uid]
        elif isinstance(script_config, WhimboxConfig):
            uid = script_config.UserData.add(WhimboxUserConfig, payload=payload)
            await script_config.UserData.commit()
            config = script_config.UserData[uid]
        else:
            raise TypeError(f"不支持的脚本配置类型: {type(script_config)}")

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

        from app.utils import config_restore as _utils_config_restore

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

        # 来源策略由专项持有；MAA/SRC 仍保留已有的单原生用户守卫。
        if isinstance(script_config, ZzzOdConfig):
            from app.task.ZzzOd.api_service import get_service

            get_service(self).prepare_user_update(
                script_id=script_id, user_id=user_id, data=data
            )
        elif isinstance(script_config, (MaaConfig, SrcConfig)):
            new_base = _utils_constants.normalize_base_source(
                data.get("Info", {}).get("Base", "")
            )
            if (
                new_base == _utils_constants.BASE_NATIVE
                and _utils_constants.normalize_base_source(
                    user_config.Info.Base or _utils_constants.BASE_INDEPENDENT
                )
                != _utils_constants.BASE_NATIVE
                and any(
                    (
                        _utils_constants.normalize_base_source(
                            cfg.Info.Base or _utils_constants.BASE_INDEPENDENT
                        )
                        == _utils_constants.BASE_NATIVE
                        for uid, cfg in script_config.UserData.items()
                        if uid != user_uid
                    )
                )
            ):
                raise ValueError(
                    "每个脚本仅允许一个原生来源用户, 多账号请在该用户的实例管理中配置"
                )

        # MFW 任务选项里的密码字段（PI v2.10.0）必须加密落盘：前端提交的是新填的明文，
        # 已保存的是密文，按项目 interface 只加密前者。加密前把只属于全局的选项双写到各任务上
        # （降级兼容，见 task_config.mirror_global_options_to_tasks）。
        task_data = data.get("Task")
        if (
            isinstance(script_config, MaaFWConfig)
            and isinstance(task_data, dict)
            and "TaskSnapshot" in task_data
        ):
            from app.task.MaaFW.tools.embedded.flavor import sanitize_user_task_update
            from app.task.MaaFW.tools.embedded.option_secrets import (
                prepare_user_task_snapshot,
            )

            # 特调收归自己管的任务（如 M9A 的启动 / 切号 / 关闭）不进用户队列，写入前按特调整理
            await asyncio.to_thread(
                sanitize_user_task_update, script_id, script_config, user_config, data
            )

            task_data["TaskSnapshot"] = await asyncio.to_thread(
                prepare_user_task_snapshot,
                script_id,
                script_config,
                task_data["TaskSnapshot"],
            )

        # 养成接管提示只在运行注入准备时重写（AutoProxy._prepare_cultivate_injection）。
        # 养成被关到不可能接管的状态后，上一轮写入的提示会残留到下次运行，前端把
        # 它展示得像当前状态。判定口径归专项（与注入早退分支同源），这里只在
        # 用户配置写入漏斗里应用其结论
        if isinstance(script_config, MaaConfig) and isinstance(data.get("Task"), dict):
            from app.task.MAA.tools.cultivate.service import takeover_notice_patch_value

            task_patch = data["Task"]
            notice = takeover_notice_patch_value(
                task_patch.get("IfCultivate", user_config.Task.IfCultivate),
                task_patch.get("CultivateTargets", user_config.Task.CultivateTargets),
            )
            if notice is not None:
                data.setdefault("Data", {})["CultivateNotice"] = notice

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

        # OK-WW 的配置目录布局与导入语义由专项维护
        # （app/task/Okww/tools/config_dir.py），core 只做分派。
        if isinstance(script_config, OkwwConfig):
            from app.task.Okww.tools.config_dir import import_script_config_dir

            await import_script_config_dir(script_id, user_id)
            return

        if not isinstance(script_config, MaaEndConfig):
            raise TypeError("当前脚本类型暂不支持导入配置文件")

        script_root = script_config.Info.Path
        if script_root is None:
            raise ValueError("Path未配置，请检查路径设置")
        source_config_dir = script_root / "config"
        if not (source_config_dir / "mxu-MaaEnd.json").exists():
            raise FileNotFoundError(
                "MaaEnd 配置文件不存在, 请检查 MaaEnd 路径设置或先启动 MaaEnd 完成配置文件生成"
            )

        config_owner = user_id or "Default"
        target_config_dir = Path.cwd() / f"data/{script_id}/{config_owner}/ConfigFile"
        # 目录里可能有只读文件（如脚本自带的 .git 对象），rmtree(ignore_errors)
        # 静默残留会让随后的覆盖写入抛 PermissionError。
        _utils_io.force_rmtree(target_config_dir)
        target_config_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_config_dir, target_config_dir, dirs_exist_ok=True)

    async def del_user(self, script_id: str, user_id: str) -> None:
        """删除用户配置"""

        logger.info(f"{script_id} 删除用户配置: {user_id}")

        script_uid = uuid.UUID(script_id)
        user_uid = uuid.UUID(user_id)
        script_config = self.ScriptConfig[script_uid]

        if isinstance(script_config, ZzzOdConfig):
            from app.task.ZzzOd.api_service import get_service

            await get_service(self).recovery.remove_user(script_id, user_id)
        else:
            script_config.UserData.remove(user_uid)
            await script_config.UserData.commit()

        # 与 del_script 同理：用户数据目录里可能有只读文件，裸 rmtree 删不干净还抛异常。
        user_data_dir = Path.cwd() / f"data/{script_id}/{user_id}"
        if user_data_dir.exists():
            await asyncio.to_thread(_utils_io.force_rmtree, user_data_dir)

    async def get_user_config_dir(self, script_id: str, user_id: str) -> Path:
        """获取用户配置目录, 不存在时创建"""

        logger.info(f"{script_id} 获取用户配置目录: {user_id}")

        script_uid = uuid.UUID(script_id)
        user_uid = uuid.UUID(user_id)
        if user_uid not in self.ScriptConfig[script_uid].UserData:
            raise ValueError("用户不存在")

        user_config_dir = Path.cwd() / f"data/{script_id}/{user_id}"
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

        for script in self.ScriptConfig.values():
            if isinstance(script, MaaConfig):
                if script.Emulator.Id == emulator_uid:
                    if script.is_locked:
                        raise RuntimeError(
                            f"脚本 {script.Info.Name} 正在使用此模拟器且被锁定, 无法完成删除"
                        )
            elif isinstance(script, GeneralConfig):
                if (
                    script.Game.Type == "Emulator"
                    and script.Game.EmulatorId == emulator_uid
                ):
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

        from app.tools.community_sign_provider import merge_community_sign_results

        today = datetime.now(tz=_utils_constants.UTC8).strftime("%Y-%m-%d")
        existing = (
            self.ToolsConfig._game_sign_result_data
            if self._game_sign_result_date == today
            else {}
        )
        result = merge_community_sign_results(existing, formatted, replace=replace)
        self.ToolsConfig._game_sign_result_data = result
        self._game_sign_result_date = today
        _save_game_sign_result_snapshot(
            self.config_path / GAME_SIGN_RESULT_FILENAME,
            result,
            result_date=today,
        )

        try:
            from app.core.ws import Publisher, protocol
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
            existing_names = []
            for account in self.ToolsConfig.GameSign_Accounts.values():
                try:
                    existing_names.append(account.GameSignAccount.Name)
                except (AttributeError, KeyError):
                    continue
            account_name = _utils_community.next_community_account_name(existing_names)
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
        from app.tools.community_sign_provider import COMMUNITY_TOKEN_FIELDS

        credential_fields = set(COMMUNITY_TOKEN_FIELDS)
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
        from app.services.obs_replay import ObsReplayOptions

        return ObsReplayOptions(
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
            logger.info(f"使用代理: {proxy_addr}")
            return httpx.Proxy(proxy_addr)
        except Exception as e:
            logger.warning(f"代理配置无效: {proxy_addr}, 错误: {e}")
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

        from app.core.history import history_store

        users = await history_store.get_overview(
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

        from .emulator_manager import EmulatorManager

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

    async def clean_maafw_agent_venvs(self) -> None:
        """清掉已无脚本引用的 MFW agent 隔离 venv。

        这些 venv 每个几十到上百 MB，此前没有任何回收——只有「同一项目依赖变了
        就重建」那一条。用户删脚本、改项目路径、或项目升级换了目录，旧 venv 都会
        永远留着。

        放在启动清理里而不是运行前：判定依赖「当前全部脚本配置」这个全局状态，
        只有真实启动时它才可信。挂在 check() 上曾把测试替身当成真配置，
        把开发者磁盘上的真 venv 删掉了。

        隔离 venv 按依赖清单 + maafw 版本 + 宿主身份跨视图共用，目录名不再由项目路径推出：
        存活集合按各存活脚本的引用记录（准备时写在 ``.refs/`` 下）、建计划时会算出的目录、
        以及还没准备过的脚本升级前按路径建的老目录算，不读 venv 目录内的清单；存活脚本的
        引用记录读不出来就整轮不回收（见 ``agent_env.planner.collect_orphan_agent_venvs``）。
        再加两道保护——刚动过的一律不碰；正被准备（锁文件被占）的也不碰，避免与正在
        准备环境的运行抢。不属于任何存活脚本的引用记录一并删掉。
        """

        from app.models.config import MaaFWConfig
        from app.task.MaaFW.tools.core.agent_env.planner import (
            collect_orphan_agent_venvs,
        )
        from app.task.MaaFW.tools.core.agent_env.venv_share import (
            collect_stale_venv_refs,
            discard_venv_lock_file,
            isolated_venv_guard,
        )
        from app.task.MaaFW.tools.embedded.embedded_project import (
            resolve_maafw_project_root,
        )

        root = Path.cwd() / "config" / "maafw_agent_venvs"
        if not root.is_dir():
            return

        # 按有效根算存活集合：内嵌脚本的 venv 是按副本路径哈希的，拿来源目录去算
        # 会把副本的 venv 当孤儿删掉。
        live_paths = [
            path
            for uid, config in self.ScriptConfig.items()
            if isinstance(config, MaaFWConfig)
            and (path := str(resolve_maafw_project_root(str(uid), config)).strip())
        ]

        # 有效根都是本机 data/ 下的副本：不存在只说明这个脚本还没导入过（新建未选目录、
        # 升级后没打开过），它名下不可能有 venv，从存活集合里去掉即可；不能像路径模式
        # 那样「一个不可达就整轮弃权」，否则任何一个空脚本都会永久关掉回收。
        missing = [path for path in live_paths if not Path(path).exists()]
        if missing:
            logger.debug(
                f"MFW 隔离 venv 清理：{len(missing)} 个脚本还没有副本，不计入存活"
            )
            live_paths = [path for path in live_paths if Path(path).exists()]

        try:
            orphans = collect_orphan_agent_venvs(root, live_paths)
        except Exception as exc:
            logger.warning(f"MFW 隔离 venv 孤儿扫描失败: {exc}")
            return

        cutoff = time.time() - MAAFW_AGENT_VENV_GRACE_SECONDS
        for venv_path in orphans:
            try:
                if venv_path.stat().st_mtime > cutoff:
                    continue  # 刚动过，可能有运行正在用它
                with isolated_venv_guard(venv_path, blocking=False) as locked:
                    if not locked:
                        logger.info(
                            f"MFW 隔离 venv 正在被准备，本次不清理: {venv_path}"
                        )
                        continue
                    shutil.rmtree(venv_path)
            except OSError as exc:
                logger.warning(f"MFW 隔离 venv 清理失败: {venv_path} - {exc}")
                continue
            # 锁文件出了锁才删得掉（Windows 上开着的文件删不了）
            discard_venv_lock_file(venv_path)
            logger.info(f"已清理无人引用的 MFW 隔离 venv: {venv_path}")

        try:
            stale_refs = collect_stale_venv_refs(root, live_paths)
        except Exception as exc:
            logger.warning(f"MFW 隔离 venv 引用记录扫描失败: {exc}")
            return
        for ref_path in stale_refs:
            try:
                ref_path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning(f"MFW 隔离 venv 引用记录清理失败: {ref_path} - {exc}")
                continue
            logger.debug(f"已清理无主的 MFW 隔离 venv 引用记录: {ref_path}")

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
            legacy_pool = Path.cwd() / "data" / uid_text / "M9ABackups"
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

    async def _archive_legacy_hsr_direct_snapshots(
        self, script_config_path: Path
    ) -> None:
        """HSR 旧直控快照停用前的留档，结果攒成启动通知；见 ``app.task.HSR.tools.legacy_direct``。

        没有 HSR 脚本时不导入 HSR 专项（导入要近 1 秒），先按字节找一次类型标签。
        """

        def _has_hsr_script() -> bool:
            try:
                return b'"HSRConfig"' in script_config_path.read_bytes()
            except OSError:
                return False

        try:
            if not await asyncio.to_thread(_has_hsr_script):
                return
            from app.task.HSR.tools.legacy_direct import (
                archive_legacy_direct_snapshots,
            )

            report = await asyncio.to_thread(
                archive_legacy_direct_snapshots, script_config_path
            )
        except Exception as exc:  # noqa: BLE001 - 留档失败不该挡住启动
            logger.opt(exception=True).warning(f"HSR 旧直控快照留档失败：{exc}")
            return
        if report.needs_notice:
            self.startup_notices.append(report.notice())

    async def push_system_notice(
        self, *, level: str, title: str, lines: list[str]
    ) -> None:
        """发一条系统通知；主连接还没建立就先攒着，连上时随启动通知一起发。"""

        from app.core.ws import Publisher, protocol
        from app.models.schema import WSSystemNoticeData

        notice = {"level": level, "title": title, "lines": list(lines)}
        try:
            sent = await Publisher.send(
                id=protocol.ID_MAIN,
                type=protocol.SYSTEM_NOTICE,
                data=WSSystemNoticeData(**notice),
            )
        except Exception as exc:  # noqa: BLE001 - 通知发不出去不该影响业务
            logger.warning(f"系统通知发送失败，改为下次连接时发送：{exc}")
            sent = False
        if not sent:
            self.startup_notices.append(notice)

    async def flush_startup_notices(self) -> None:
        """主 WebSocket 连上后把启动期攒下的系统通知发出去，发成功的只发一次。

        连接刚建立就被替换 / 断开时发送返回 False，断开还会取消这个回调；没发出去的
        （含正在发的那条）按原顺序放回队列，由下一次连接再发，不在这里重试。
        """

        from app.core.ws import Publisher, protocol
        from app.models.schema import WSSystemNoticeData

        pending, self.startup_notices = self.startup_notices, []
        try:
            while pending:
                try:
                    sent = await Publisher.send(
                        id=protocol.ID_MAIN,
                        type=protocol.SYSTEM_NOTICE,
                        data=WSSystemNoticeData(**pending[0]),
                    )
                except Exception as exc:  # noqa: BLE001 - 与 push_system_notice 一致
                    logger.warning(f"系统通知发送失败，改为下次连接时发送：{exc}")
                    sent = False
                if not sent:
                    break
                pending.pop(0)
        finally:
            # 发送期间 push_system_notice 可能又攒进来新的，放在它们前面保持顺序
            self.startup_notices[:0] = pending

    async def clean_maafw_embedded_copies(self) -> None:
        """清掉内嵌副本目录下的两类垃圾：staging 半成品、脚本已不存在的副本。

        导入在 ``.staging/`` 里投影完再换入，进程中途退出会留下半成品；删脚本时
        副本删除失败（只读、被占用）也会留下孤儿。两者都是 MAS 自己铺的，不含用户
        内容，启动期没有任务在跑，直接清。目录名必须是副本目录名的形状才会被当作副本。
        """

        from app.models.config import MaaFWConfig
        from app.task.MaaFW.tools.embedded.embedded_project import (
            STAGING_DIR_NAME,
            embedded_copy_dir_name,
            embedded_projects_root,
            is_embedded_copy_dir_name,
            recover_switches,
            remove_tree,
            switch_root,
        )
        from app.task.MaaFW.tools.embedded.project_path import (
            release_project_path,
            try_reserve_project_path,
        )

        root = embedded_projects_root()
        if not root.is_dir():
            return
        # 先按 journal 收尾被打断的视图切换：切换的 old / staging 都在 .staging 里，
        # 不先恢复的话下面的半成品清理会把「rename 了一半」时暂存的原视图当垃圾删掉。
        try:
            # 本进程起来之后才写的 journal、拿不到视图预约的（正在切换 / 运行）不碰：
            # 后台初始化时 API 已经在服务，可能正有一次切换在建 staging。
            await asyncio.to_thread(
                lambda: recover_switches(started_at=_PROCESS_STARTED_AT, reserve=True)
            )
        except Exception as exc:  # noqa: BLE001 - 恢复失败不该影响启动，journal 留着下次再试
            logger.warning(f"MFW 视图切换恢复失败: {exc}")
        staging = root / STAGING_DIR_NAME
        if staging.is_dir():
            for leftover in staging.iterdir():
                # 后台初始化时 API 已在服务，preview / reimport 可能正往 .staging 里写：
                # 本进程起来之后才出现的、或该脚本的副本路径正被预约的，都不是半成品。
                try:
                    if leftover.stat().st_mtime >= _PROCESS_STARTED_AT:
                        continue
                except OSError:
                    continue
                # 半成品叫 <副本目录名>-<8 位随机>、<副本目录名>-old-/-sw-<8 位随机>
                # 或 payload-<谱系>-<8 位随机>
                prefix = leftover.name.split("-", 1)[0]
                if (switch_root() / f"{prefix}.json").exists():
                    # 恢复没收尾的切换：它的 old 目录可能就是原视图，留着待查
                    continue
                reservation = await try_reserve_project_path(root / prefix)
                if reservation is None:
                    continue
                await release_project_path(reservation)
                try:
                    remove_tree(leftover)
                except OSError as exc:
                    logger.warning(
                        f"MFW 内嵌 staging 半成品清理失败: {leftover} - {exc}"
                    )
                    continue
                logger.info(f"已清理 MFW 内嵌导入半成品: {leftover}")
        # 存活的副本：脚本还在。删脚本时删副本可能因文件被占用而失败（与别的副本
        # 共用的库正被映射着），那份留下的副本也在这里收掉。
        # 但脚本表本身没加载起来（ScriptConfig.json 损坏时 _load_json_file 留下
        # .corrupt 副本后按空表继续）就不能扫：那会把所有副本当孤儿删光，来源目录
        # 已被用户清掉的项目从此没得修。
        if not self._script_config_loaded_intact():
            logger.warning(
                "脚本配置文件非空但没有加载出任何脚本，疑似损坏，跳过 MFW 内嵌副本孤儿清理"
            )
            return
        live = {
            embedded_copy_dir_name(str(uid))
            for uid, config in self.ScriptConfig.items()
            if isinstance(config, MaaFWConfig)
        }
        for child in root.iterdir():
            if child.name == STAGING_DIR_NAME or not child.is_dir():
                continue
            if not is_embedded_copy_dir_name(child.name) or child.name in live:
                continue
            try:
                remove_tree(child)
            except OSError as exc:
                logger.warning(f"MFW 内嵌副本孤儿清理失败: {child} - {exc}")
                continue
            logger.info(f"已清理无脚本引用的 MFW 内嵌副本: {child}")
        # 视图没了的脚本（下次运行前要按载荷重建）：它的导入来源在事件循环线程上抄出来，
        # 回收据此保住对应的谱系。
        from app.task.MaaFW.tools.embedded.embedded_project import (
            embedded_project_dir,
            follow_source_enabled,
            imported_source_path,
            read_view_marker,
        )

        live_sources = [
            imported_source_path(config) or str(config.Info.Path or "")
            for uid, config in self.ScriptConfig.items()
            if isinstance(config, MaaFWConfig)
            and read_view_marker(embedded_project_dir(str(uid))) is None
        ]
        # 开着开发者模式的脚本：它们私有渠道的 latest 保住，其余私有渠道（关了开关、删了
        # 脚本）摘掉，留下的开发者载荷随后按普通规则回收。
        follow_views = [
            embedded_copy_dir_name(str(uid))
            for uid, config in self.ScriptConfig.items()
            if isinstance(config, MaaFWConfig) and follow_source_enabled(config)
        ]
        await asyncio.to_thread(
            self._collect_unreferenced_payloads, live_sources, follow_views
        )

    @staticmethod
    def _collect_unreferenced_payloads(
        live_sources: list[str], follow_views: list[str]
    ) -> None:
        """删掉没人引用的载荷；谱系里一个视图都不剩（最后一个脚本已删）时整个谱系一起删
        （§3.1 第 10 步，``embedded_project.collect_payload_garbage``）。

        引用集 = 所有视图标记的 ``payload`` ∪ 未完成 journal 的 ``to``；``latest[*]`` 只在
        谱系还有视图时算引用（开发者模式的私有渠道只在脚本还开着开关时算）。本进程起来
        之后才建的不收。载荷删掉之后，它独有的 blob 只剩库里一个链接，紧接着的
        ``clean_maafw_runtime_blobs`` 收走。
        """

        from app.task.MaaFW.tools.embedded.embedded_project import (
            collect_payload_garbage,
        )

        try:
            report = collect_payload_garbage(
                started_at=_PROCESS_STARTED_AT,
                live_sources=live_sources,
                follow_source_views=follow_views,
            )
        except Exception as exc:  # noqa: BLE001 - 回收失败不影响启动
            logger.warning(f"MFW 载荷回收失败: {exc}")
            return
        if not (report.payloads or report.lineages):
            return
        parts = []
        if report.payloads:
            parts.append(f"{report.payloads} 个无人引用的项目版本（载荷）")
        if report.lineages:
            parts.append(
                f"{len(report.lineages)} 个不再有脚本使用的项目（整个谱系: "
                + ", ".join(report.lineages)
                + "）"
            )
        # 与共用库共享的大文件由紧接着的共用库回收释放（那一行另报 MB）。
        logger.info(
            f"已回收 MFW {'、'.join(parts)}，释放 {report.freed_bytes / 2**20:.1f} MB"
        )

    async def migrate_maafw_embedded_copies_to_payloads(self) -> None:
        """启动期一次性迁移：把没有标记的老副本采纳成「载荷 + 视图」（附录 B）。

        逐副本持视图预约、各自失败隔离（不写标记、日志点名、下次启动再试）。**全部采纳完
        再统一决定同版本的 latest**（``settle_adopted_latest``：有更新器清单的、文件集合是
        超集的、文件多的优先，与脚本顺序无关），然后每个谱系每个渠道统一到 latest（附录 B
        第 8 条），切过的视图连同预约交给后台确认运行环境。之后收掉老的原地更新留下的清单、
        预检备忘与作废的更新流水（还有没采纳的副本时留着它们要用的那部分）。配置一个字段
        都不写；脚本表没加载起来（疑似损坏）整轮弃权。

        迁移在后台跑、不挡主定时器：期间拿不到视图预约的运行在运行前检查里按「正在切换
        版本」跳过一次（``embedded_project.migration_active``）。
        """

        from app.task.MaaFW.tools.embedded.embedded_project import set_migration_active

        set_migration_active(True)
        try:
            await self._migrate_maafw_embedded_copies()
        finally:
            set_migration_active(False)

    async def _migrate_maafw_embedded_copies(self) -> None:
        from app.models.config import MaaFWConfig
        from app.task.MaaFW.tools.embedded.embedded_project import (
            GroupMember,
            adopt_view,
            copy_is_healthy,
            effective_channel,
            embedded_project_dir,
            imported_source_path,
            read_view_marker,
            settle_adopted_latest,
        )
        from app.task.MaaFW.tools.embedded.project_path import (
            release_project_path,
            try_reserve_project_path,
        )
        from app.task.MaaFW.tools.embedded.update_credentials import (
            resolve_update_proxy_url,
        )

        if not self._script_config_loaded_intact():
            logger.warning(
                "脚本配置文件非空但没有加载出任何脚本，疑似损坏，跳过 MFW 副本迁移"
            )
            return
        entries: list[tuple[str, str, str, str, str | None]] = []
        for uid, config in self.ScriptConfig.items():
            if not isinstance(config, MaaFWConfig):
                continue
            entries.append(
                (
                    str(uid),
                    effective_channel(str(uid), config),
                    imported_source_path(config) or str(config.Info.Path or ""),
                    str(config.Info.Name or str(uid)[:8]),
                    resolve_update_proxy_url(config) or None,
                )
            )
        pending = [
            entry
            for entry in entries
            if copy_is_healthy(embedded_project_dir(entry[0]))
            and read_view_marker(embedded_project_dir(entry[0])) is None
        ]
        if not pending:
            # 没有待采纳的副本：老的原地更新留下的清单与更新记录都没用了（每次启动都收，
            # 不只在「刚迁移完且全部成功」那一次）。
            await asyncio.to_thread(
                self._discard_legacy_update_state, keep_adoption_baseline=False
            )
            return
        started = time.monotonic()
        adopted: list[str] = []
        failed: list[str] = []
        for script_id, channel, source, name, _proxy in pending:
            view = embedded_project_dir(script_id)
            key = await try_reserve_project_path(view)
            if key is None:
                failed.append(name)
                logger.warning(
                    f"MFW 副本迁移：脚本「{name}」的副本正被占用，下次启动再试"
                )
                continue
            began = time.monotonic()
            try:
                if await asyncio.to_thread(read_view_marker, view) is not None:
                    # 迁移在后台跑：它自己开跑时的运行前检查已经就地采纳过了。
                    continue
                result = await asyncio.to_thread(
                    lambda sid=script_id, ch=channel, src=source: adopt_view(
                        sid, channel=ch, source=src
                    )
                )
                adopted.append(script_id)
                logger.info(
                    f"MFW 副本迁移：脚本「{name}」已登记为 {result.version}（{result.payload_id}），"
                    f"私有文件 {result.carried} 个，采纳用时 {time.monotonic() - began:.1f} s"
                )
            except Exception as exc:  # noqa: BLE001 - 逐副本隔离，下次启动再试
                failed.append(name)
                logger.opt(exception=True).warning(
                    f"MFW 副本迁移：脚本「{name}」采纳失败，下次启动再试：{exc}"
                )
            finally:
                await release_project_path(key)
        # 全部登记完才定同版本的 latest（登记本身是「同版本保留先来的」），再统一切换。
        await asyncio.to_thread(settle_adopted_latest)
        switched, held = await self._unify_maafw_views_to_group(entries)
        logger.info(
            f"MFW 副本迁移完成：采纳 {len(adopted)} 个、失败 {len(failed)} 个、"
            f"统一到组版本 {len(switched)} 个，用时 {time.monotonic() - started:.1f} s"
        )
        from app.task.MaaFW.tools.embedded.view_update import (
            confirm_environments_in_background,
        )

        # 切换时拿的预约直接交给确认线程（两步之间不留空档）；没切的不确认。
        confirm_environments_in_background(
            [
                GroupMember(sid, channel, name=name, proxy_url=proxy)
                for sid, channel, _src, name, proxy in entries
                if sid in set(switched)
            ],
            held=held,
        )
        # 采纳失败的副本下次启动还要靠老的更新清单（committed 记录 + 状态目录里的包内
        # 清单）认出哪些文件没改过，那部分留着；其余作废记录照收。
        await asyncio.to_thread(
            self._discard_legacy_update_state, keep_adoption_baseline=bool(failed)
        )

    async def _unify_maafw_views_to_group(
        self, entries: list[tuple[str, str, str, str, str | None]]
    ) -> tuple[list[str], dict[str, str]]:
        """附录 B 第 8 条：每个视图切到它所在组（谱系 + 渠道）的 latest。

        返回（切过的脚本, 它们还没放的预约）：预约交给环境确认线程放。
        """

        from app.task.MaaFW.tools.embedded.embedded_project import (
            MIGRATION_SWITCHED_BY,
            embedded_project_dir,
        )
        from app.task.MaaFW.tools.embedded.project_path import (
            release_project_path,
            try_reserve_project_path,
        )
        from app.task.MaaFW.tools.embedded.view_update import sync_view_to_group

        switched: list[str] = []
        held: dict[str, str] = {}
        for script_id, channel, _source, name, _proxy in entries:
            # 迁移在后台跑、主定时器已经起来：运行中的脚本在「运行前检查结束 → 第一个用户」
            # 与用户之间不持视图预约，只看预约会在空档里把它切走（同一轮前后用户跑不同版本、
            # 下一个用户被「同一路径正在运行」跳过）。与其它传播路径同一口径：脚本配置锁着
            # （is_locked）就跳过，留给它的收尾同步或下次运行前检查。在事件循环上查。
            try:
                config = self.ScriptConfig[uuid.UUID(script_id)]
            except (KeyError, ValueError):
                continue
            if getattr(config, "is_locked", False):
                logger.info(
                    f"MFW 副本迁移：脚本「{name}」正在运行，统一到组版本留给它跑完后再做"
                )
                continue
            key = await try_reserve_project_path(embedded_project_dir(script_id))
            if key is None:
                continue
            if getattr(config, "is_locked", False):
                # 等预约的那一下它开跑了（锁在预约之后才上，这里再看一眼）。
                await release_project_path(key)
                continue
            result = None
            try:
                result = await sync_view_to_group(
                    script_id,
                    channel,
                    reservation_held=True,
                    # 记下是迁移切的：确认期间它开跑会在运行前检查里得到「正在切换版本」，
                    # 下次运行打一行「启动期迁移时统一到 vX」。
                    switched_by=MIGRATION_SWITCHED_BY,
                )
            except Exception as exc:  # noqa: BLE001 - 留在原版本，下次运行前再同步
                logger.warning(f"MFW 副本迁移：脚本「{name}」统一到组版本失败：{exc}")
            finally:
                if result is None:
                    await release_project_path(key)
            if result is not None:
                switched.append(script_id)
                held[script_id] = key
                logger.info(
                    f"MFW 副本迁移：脚本「{name}」{result.from_payload} → {result.payload_id}"
                )
        return switched, held

    @staticmethod
    def _discard_legacy_update_state(*, keep_adoption_baseline: bool) -> None:
        """收掉更新留下的作废记录。

        - ``data/maafw_update_operations``：本进程起来之前写的记录。新流程里它只是一次
          下载 + 登记的流水（登记后标 ``registered``，失败 / 取消各有终态），没有谁再读，
          一律删；老的原地更新留下的 ``committed`` 除外——还有没采纳的老副本时
          （``keep_adoption_baseline``），采纳要靠它找包内清单。
        - ``data/maafw_project_state`` 各视图状态目录里除 ``local-modified`` 之外的文件
          （老的包内清单、预检备忘）：同样只在不再需要采纳基线时删。
        """

        operations = Path.cwd() / "data" / "maafw_update_operations"
        if operations.is_dir():
            for record in operations.iterdir():
                state_file = record / "state.json"
                try:
                    if state_file.stat().st_mtime >= _PROCESS_STARTED_AT:
                        continue
                    status = json.loads(state_file.read_text(encoding="utf-8")).get(
                        "status"
                    )
                except (OSError, ValueError, AttributeError):
                    continue
                if status == "committed" and keep_adoption_baseline:
                    continue
                try:
                    shutil.rmtree(record)
                except OSError as exc:
                    logger.warning(f"清理作废的更新记录失败: {record} - {exc}")
        if keep_adoption_baseline:
            return
        state_root = Path.cwd() / "data" / "maafw_project_state"
        if state_root.is_dir():
            for state_dir in state_root.iterdir():
                if not state_dir.is_dir():
                    continue
                for child in state_dir.iterdir():
                    if child.name == "local-modified":
                        continue
                    try:
                        if child.is_dir():
                            shutil.rmtree(child)
                        else:
                            child.unlink()
                    except OSError as exc:
                        logger.warning(f"清理老的更新状态失败: {child} - {exc}")

    def _script_config_loaded_intact(self) -> bool:
        """脚本表是空的时候，看配置文件本身是不是真的空：解析失败或文件里明明有
        脚本却一个都没加载出来，都算没加载起来。"""

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

    async def clean_maafw_runtime_blobs(self) -> None:
        """回收没有任何内嵌副本引用的共用运行时文件（只剩库里这一个硬链接的）。

        放在副本清理之后：副本删掉，它引用的 blob 才会变成孤儿。
        """

        from app.task.MaaFW.tools.core.project_update.blob_store import (
            RuntimeBlobStore,
        )

        try:
            report = RuntimeBlobStore.default().collect_garbage()
        except Exception as exc:  # noqa: BLE001 - 回收失败不该影响启动
            logger.warning(f"MFW 共用运行时库回收失败: {exc}")
            return
        if report.removed_blobs or report.removed_temps:
            logger.info(
                f"已回收 MFW 共用运行时库: {report.removed_blobs} 个文件、"
                f"{report.removed_bytes / 2**20:.1f} MB，半成品 {report.removed_temps} 个"
            )

    async def clean_maafw_update_cache(self) -> None:
        """回收 7 天没人碰过的 MFW 项目更新包缓存。

        下载好的包留在 ``data/maafw_update_cache`` 里给同一项目的其它副本命中，
        一份 200 MB 的全量包只下一次；但此前从不回收，每个下过的版本都永久留着。
        正在下载 / 落地的条目持有文件锁，会被跳过。
        """

        from app.task.MaaFW.tools.core.project_update.transport import (
            prune_update_cache,
        )

        try:
            report = await asyncio.to_thread(prune_update_cache)
        except Exception as exc:  # noqa: BLE001 - 回收失败不该影响启动
            logger.warning(f"MFW 更新包缓存回收失败: {exc}")
            return
        if report.removed_artifacts:
            logger.info(
                f"已回收 MFW 更新包缓存: {report.removed_artifacts} 个、"
                f"{report.removed_bytes / 2**20:.1f} MB"
            )

    async def clean_maafw_runtime_pool(self) -> None:
        """按引用对账回收 MFW 运行池里无人引用的共享 runtime。

        与 ``clean_maafw_agent_venvs`` 同一个道理放在启动清理里：判定依赖「当前
        全部脚本配置」这个全局状态，只有真实启动时它才可信。规则与保守条件见
        ``tools/embedded/pool_reconcile.py``；这里只负责把权威集合（全部 MaaFW 类
        脚本的项目目录）交过去，并在脚本表疑似没加载起来时弃权。
        """

        from app.task.MaaFW.tools.embedded.pool_reconcile import (
            collect_live_project_paths,
            reconcile_runtime_pool,
            runtime_pool_root,
            script_config_loaded_intact,
        )

        if not (runtime_pool_root() / "runtimes").is_dir():
            return
        if not script_config_loaded_intact():
            logger.warning(
                "脚本配置文件非空但没有加载出任何脚本，疑似损坏，跳过 MFW 运行池回收"
            )
            return
        try:
            await asyncio.to_thread(
                reconcile_runtime_pool,
                collect_live_project_paths(),
                reason="startup",
            )
        except Exception as exc:  # noqa: BLE001 - 回收失败不该影响启动
            logger.warning(f"MFW 运行池回收失败: {exc}")

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

        debug_root = Path.cwd() / "debug"
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

    def clean_maafw_native_debug_logs(self) -> None:
        """清掉 MFW 项目里过期的 MaaFramework 原生日志备份。

        MaaFramework 把 ``debug/maafw.log`` 写到一定大小就整体挪成
        ``debug/maafw.bak.<时间戳>.log`` 再开新的，但从不回收旧的——一个每天跑
        的项目几天就能堆出几百 MB。每次运行的完整内容已经另存进历史记录的
        ``*.maafw.log``，所以这里只删备份，正在写的 ``maafw.log`` 不动。
        保留时长沿用历史记录的保留天数设置。

        纯同步文件 IO，调用方在事件循环里请经 ``asyncio.to_thread`` 执行。
        """

        # 只读一次 + 集合快照：每日任务在工作线程跑本函数，主循环可能并发改
        # 设置（guard 与 cutoff 之间翻到 0 会让 cutoff 变成 now、删光全部备份）
        # 和增删脚本。items() 是 zip(order 列表, data 逐项查找) 的惰性结构，
        # list() 消费它并非原子拷贝、并发增删仍可 KeyError 中止本轮；直接对
        # data 的 dict 视图做 list() 才是单条 C 级拷贝的真原子快照
        retention_days = self.setting.Function.HistoryRetentionTime
        if retention_days == 0:
            logger.info("原生日志永久保留, 跳过 MFW 原生日志备份清理")
            return

        from app.models.config import MaaFWConfig
        from app.task.MaaFW.tools.embedded.embedded_project import (
            resolve_maafw_project_root,
        )

        cutoff = time.time() - retention_days * 86400
        deleted_count = 0
        for uid, script_config in list(self.ScriptConfig.data.items()):
            if not isinstance(script_config, MaaFWConfig):
                continue
            # runner 把原生日志写在有效根下：内嵌脚本是副本，不是来源目录。
            project_path = str(
                resolve_maafw_project_root(str(uid), script_config)
            ).strip()
            if not project_path:
                continue
            debug_folder = Path(project_path) / "debug"
            if not debug_folder.is_dir():
                continue
            # 备份文件名由 MaaFramework 决定，与 runner_task 里
            # _iter_rotated_native_debug_logs 认的是同一套。
            for file in debug_folder.glob("maafw.bak.*.log"):
                try:
                    if file.stat().st_mtime >= cutoff:
                        continue
                    file.unlink()
                except OSError as exc:
                    logger.warning(f"MFW 原生日志备份清理失败: {file} - {exc}")
                    continue
                deleted_count += 1
        if deleted_count:
            logger.success(f"清理完成: {deleted_count} 个过期 MFW 原生日志备份")


Config = AppConfig()
