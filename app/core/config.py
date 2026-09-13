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
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional

import httpx
import truststore

# 仅用于类型标注的顶层依赖移到 TYPE_CHECKING，避免启动导入开销
if TYPE_CHECKING:
    import uvicorn

    from app.utils.config_restore import ConfigRestoreService
from jinja2 import Environment, FileSystemLoader

from app.models.config import (
    CLASS_BOOK,
    PLAN_BOOK,
    BAAHConfig,
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
    ZzzOdConfig,
    ZzzOdUserConfig,
)
from app.models.schema import PlanComboxConsumer
from app.utils import get_logger, is_supervised, resource_path
from app.utils.community import next_community_account_name
from app.utils.constants import (
    MAA_DEPOT_EXCLUDED_ITEM_IDS,
    RESOURCE_STAGE_DATE_TEXT,
    RESOURCE_STAGE_DROP_INFO,
    RESOURCE_STAGE_INFO,
    TYPE_BOOK,
    UTC4,
    UTC8,
)
from app.utils.io import force_rmtree, write_file
from app.utils.paths import SOURCE_ROOT
from app.utils.platform import IS_WINDOWS

# 孤儿 venv 的宽限期：刚动过的一律不碰，避免与正在准备环境的运行抢。
MAAFW_AGENT_VENV_GRACE_SECONDS = 60 * 60

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
    """原子保存游戏社区结果快照（走 ``app.utils.io.write_file``）。"""

    if path is None:
        return

    try:
        write_file(path, {"date": result_date, "result": result})
    except (OSError, TypeError, ValueError) as e:
        logger.warning(f"保存游戏社区结果快照失败: {e}")


def _parse_maa_drop_statistics(logs: list[str]) -> dict[str, dict[str, int]]:
    """按理智任务边界解析 MAA 日志中的关卡掉落统计。

    Args:
        logs: MAA 日志行列表。

    Returns:
        按关卡汇总的掉落统计。
    """

    target_task_names = {
        "Fight",
        "理智作战",
        "活动关优先",
        "库存保持",
        "剩余理智",
    }
    annihilation_markers = ("剿灭", "剿滅", "Annihilation", "殲滅", "섬멸")
    fight_start_markers = (
        "开始任务: Fight",
        "开始任务: 理智作战",
        "Start Task Chain: Fight",
    )

    def is_task_boundary(line: str) -> bool:
        return "完成任务:" in line or "Completed Task Chain:" in line

    def get_completed_task_name(line: str) -> str | None:
        match = re.search(r"完成任务:\s*([^\r\n]+)", line)
        if match is not None:
            return match.group(1).strip() or None

        match = re.search(r"Completed Task Chain:\s*([^,\r\n]+)", line)
        if match is None:
            return None
        return match.group(1).strip() or None

    task_ranges: list[tuple[int, int]] = []
    for end_index, line in enumerate(logs):
        task_name = get_completed_task_name(line)
        if task_name not in target_task_names:
            continue

        previous_boundary = max(
            (
                index
                for index, item in enumerate(logs[:end_index])
                if is_task_boundary(item)
            ),
            default=-1,
        )
        start_candidates = [
            index
            for index, item in enumerate(logs[:end_index])
            if index > previous_boundary
            and any(marker in item for marker in fight_start_markers)
        ]
        start_index = max(start_candidates, default=previous_boundary + 1)

        if task_name == "Fight" and any(
            marker in item
            for item in logs[start_index : end_index + 1]
            for marker in annihilation_markers
        ):
            continue

        task_ranges.append((start_index, end_index))

    all_stage_drops: dict[str, dict[str, int]] = {}
    for start_index, end_index in task_ranges:
        current_stage = None
        last_drop_stats: dict[str, int] = {}

        for line in logs[start_index : end_index + 1]:
            drop_match = re.search(r"([\u4e00-\u9fffA-Za-z0-9\-]+) 掉落统计:", line)
            if drop_match:
                current_stage = drop_match.group(1)
                last_drop_stats = {}
                continue

            if not current_stage:
                continue

            item_match: list[tuple[str, str]] = re.findall(
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

                if item not in [
                    "当前次数",
                    "理智",
                    "最快截图耗时",
                    "专精等级",
                    "剩余时间",
                ]:
                    last_drop_stats[item] = total

        if current_stage and last_drop_stats:
            stage_drops = all_stage_drops.setdefault(current_stage, {})
            for item, count in last_drop_stats.items():
                stage_drops[item] = stage_drops.get(item, 0) + count

    return all_stage_drops


class AppConfig(GlobalConfig):
    VERSION = "v5.5.0-beta.6"

    def __init__(self) -> None:
        super().__init__()

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

        self.server: Optional["uvicorn.Server"] = None
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
        # 电源操作前的静默延时秒数, 与 power_sign 一同由队列配置写入
        self.power_delay: int = 0
        self.temp_task: List[asyncio.Task] = []
        # 正在循环运行的队列，供配置改动前的安全检查使用
        self.running_cycle_queue_ids: set[uuid.UUID] = set()
        self._stage_refresh_task: Optional[asyncio.Task] = None
        # MAA item_index.json 解析缓存: 路径 -> (mtime_ns, 物品选项)
        self._maa_depot_items_cache: dict[Path, tuple[int, list[dict[str, str]]]] = {}
        self._game_sign_result_date = ""
        self._community_account_add_lock = asyncio.Lock()

        self._inject_truststore()

        self.notify_env = Environment(
            loader=FileSystemLoader(str(resource_path("html")))
        )

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
                self._repo = Repo(SOURCE_ROOT)
            except Exception as e:
                logger.warning(f"Git仓库初始化失败: {e}")
                self._repo = None
        return self._repo

    async def init_config(self) -> None:
        """初始化配置管理"""

        await self.check_data()

        await self.connect(self.config_path / "Config.json")
        await self.EmulatorConfig.connect(self.config_path / "EmulatorConfig.json")
        await self.PlanConfig.connect(self.config_path / "PlanConfig.json")
        await self.ScriptConfig.connect(self.config_path / "ScriptConfig.json")
        await self.QueueConfig.connect(self.config_path / "QueueConfig.json")
        await self.ToolsConfig.connect(self.config_path / "ToolsConfig.json")

        # 游戏社区：连接账号组 MultipleConfig
        await self.ToolsConfig.GameSign_Accounts.connect(
            self.config_path / "GameSignAccounts.json"
        )

        # 游戏社区：恢复当天的结果快照，跨日结果不继续展示
        today = datetime.now(tz=UTC8).strftime("%Y-%m-%d")
        self.ToolsConfig._game_sign_result_data = _load_game_sign_result_snapshot(
            self.config_path / GAME_SIGN_RESULT_FILENAME,
            result_date=today,
        )
        self._game_sign_result_date = today

        from app.services import System
        from app.services.telemetry import set_telemetry_enabled

        self.bind("Start", "IfSelfStart", System.set_SelfStart)
        self.bind("Function", "IfAllowSleep", System.set_Sleep)
        self.bind("Function", "IfEnableTelemetry", set_telemetry_enabled)
        # 注册自启动会读写注册表, 不阻塞初始化; 持有引用避免被 GC 且异常不被静默吞掉
        self_start_task = asyncio.create_task(
            System.set_SelfStart(self.get("Start", "IfSelfStart"))
        )
        self.temp_task.append(self_start_task)

        def _self_start_done(t: asyncio.Task) -> None:
            if t in self.temp_task:
                self.temp_task.remove(t)
            if not t.cancelled() and t.exception() is not None:
                logger.warning(f"设置开机自启动失败: {t.exception()}")

        self_start_task.add_done_callback(_self_start_done)
        await System.set_Sleep(self.get("Function", "IfAllowSleep"))
        set_telemetry_enabled(self.get("Function", "IfEnableTelemetry"))

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

                cur.execute("DELETE FROM version WHERE v = ?", ("v1.10",))
                cur.execute("INSERT INTO version VALUES(?)", ("v1.11",))
                db.commit()

            cur.close()
            db.close()
            logger.success("数据文件版本更新完成")

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
        ],
        script_id: str | None = None,
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
        | BAAHConfig,
    ]:
        """添加脚本配置"""

        logger.info(f"添加脚本配置: {script}, 从 {script_id} 复制")

        if script_id is None:
            return await self.ScriptConfig.add(CLASS_BOOK[script])
        else:
            script_uid = uuid.UUID(script_id)

            if not isinstance(self.ScriptConfig[script_uid], CLASS_BOOK[script]):
                raise TypeError(f"脚本配置类型不匹配: {script_id} {script}")

            new_uid, new_config = await self.ScriptConfig.add(CLASS_BOOK[script])

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

    async def get_script(self, script_id: str | None) -> tuple[list, dict]:
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

    async def get_maaend_options(self, script_id: str) -> dict[str, Any]:
        """读取指定 MaaEnd 安装目录中的动态选项。"""

        script_config = self.ScriptConfig[uuid.UUID(script_id)]
        if not isinstance(script_config, MaaEndConfig):
            raise TypeError("脚本配置类型错误, 不是 MaaEnd 类型")
        root_path = str(script_config.get("Info", "Path")).strip()
        if not root_path:
            raise ValueError("MaaEnd 路径未配置")

        return script_config.get_loaded_resource()

    async def update_script(
        self, script_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新脚本配置"""

        logger.info(f"更新脚本配置: {script_id}")

        uid = uuid.UUID(script_id)

        if self.ScriptConfig[uid].is_locked:
            raise RuntimeError(f"脚本 {script_id} 正在运行, 无法更新配置项")

        await self.ScriptConfig[uid].update(data)

    async def del_script(self, script_id: str) -> None:
        """删除脚本配置"""

        logger.info(f"删除脚本配置: {script_id}")

        uid = uuid.UUID(script_id)

        if self.ScriptConfig[uid].is_locked:
            raise RuntimeError(f"脚本 {script_id} 正在运行, 无法删除")

        # 删脚本会顺带删掉引用它的队列项；正在循环运行的队列靠下标回写状态，
        # 结构一变就会跑错脚本，两轮之间脚本没锁也要拦住。
        for queue_uid, queue in self.QueueConfig.items():
            if any(
                item.get("Info", "ScriptId") == str(uid)
                for item in queue.QueueItem.values()
            ):
                self._ensure_cycle_safe(queue_uid, "删除它引用的脚本")

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
        temp.pop("SubConfigsInfo", None)
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
            if IS_WINDOWS and Path(config["Script"][path]).is_relative_to(
                Path(os.environ["APPDATA"])
            ):
                config["Script"][path] = (
                    f"%APPDATA%/{Path(config['Script'][path]).relative_to(Path(os.environ['APPDATA']))}"
                )
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

    async def add_user(
        self, script_id: str
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
        | BAAHUserConfig,
    ]:
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
        elif isinstance(script_config, OkwwConfig):
            uid, config = await script_config.UserData.add(OkwwUserConfig)
            try:
                await self.ensure_okww_user_config(
                    script_id=script_id,
                    user_id=str(uid),
                    mode=str(config.get("Info", "Mode") or "脚本"),
                )
            except Exception:
                # 配置初始化失败时回滚用户，避免留下无法运行的半成品用户。
                await script_config.UserData.remove(uid)
                raise
        elif isinstance(script_config, OkNteConfig):
            uid, config = await script_config.UserData.add(OkNteUserConfig)
        elif isinstance(script_config, MaaEndConfig):
            uid, config = await script_config.UserData.add(MaaEndUserConfig)
        elif isinstance(script_config, M9AConfig):
            uid, config = await script_config.UserData.add(M9AUserConfig)
        elif isinstance(script_config, MaaFWConfig):
            uid, config = await script_config.UserData.add(MaaFWUserConfig)
        elif isinstance(script_config, HSRConfig):
            uid, config = await script_config.UserData.add(HSRUserConfig)
        elif isinstance(script_config, BetterGIConfig):
            uid, config = await script_config.UserData.add(BetterGIUserConfig)
        elif isinstance(script_config, ZzzOdConfig):
            uid, config = await script_config.UserData.add(ZzzOdUserConfig)
        elif isinstance(script_config, BAAHConfig):
            uid, config = await script_config.UserData.add(BAAHUserConfig)
        else:
            raise TypeError(f"不支持的脚本配置类型: {type(script_config)}")

        return uid, config

    async def ensure_okww_user_config(
        self,
        script_id: str,
        user_id: str,
        mode: str,
    ) -> Path:
        """从 OK-WW 脚本当前配置初始化 MAS 用户配置目录。

        已存在配置文件时保留用户配置；仅当目标目录为空时复制脚本目录中的默认配置。
        脚本来源使用脚本共享目录，用户来源使用当前用户独立目录。

        Args:
            script_id: OK-WW 脚本 ID。
            user_id: OK-WW 用户 ID。
            mode: 配置来源，支持“脚本”或“用户”；“简洁”/“详细”仅兼容旧配置。

        Returns:
            MAS 用户配置目录路径。

        Raises:
            TypeError: 脚本不是 OK-WW 类型。
            ValueError: 配置模式非法或目标路径冲突。
            FileNotFoundError: OK-WW 默认配置目录不存在或为空。
        """

        script_uid = uuid.UUID(script_id)
        script_config = self.ScriptConfig[script_uid]
        if not isinstance(script_config, OkwwConfig):
            raise TypeError(f"脚本配置类型错误: {script_id} 不是 OK-WW 类型")
        mode = {"简洁": "脚本", "详细": "用户"}.get(mode, mode)
        if mode not in ("脚本", "用户"):
            raise ValueError(f"不支持的 OK-WW 配置模式: {mode}")

        owner = "Default" if mode == "脚本" else user_id
        target_config_dir = Path.cwd() / "data" / script_id / owner / "ConfigFile"
        if target_config_dir.exists() and not target_config_dir.is_dir():
            raise ValueError(f"OK-WW 用户配置路径不是目录: {target_config_dir}")
        if target_config_dir.is_dir() and any(
            item.is_file() for item in target_config_dir.rglob("*")
        ):
            return target_config_dir

        script_root = Path(script_config.get("Info", "RootPath")).expanduser()
        source_config_dir = script_root / "data/apps/ok-ww/working/configs"
        if not source_config_dir.is_dir() or not any(
            item.is_file() for item in source_config_dir.rglob("*")
        ):
            raise FileNotFoundError(
                "未找到 OK-WW 默认设置，请先运行一次 OK-WW 并保存设置"
            )

        temporary_path = target_config_dir.with_name(
            f".{target_config_dir.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            shutil.copytree(source_config_dir, temporary_path)
            target_config_dir.parent.mkdir(parents=True, exist_ok=True)
            force_rmtree(target_config_dir)
            temporary_path.rename(target_config_dir)
        finally:
            force_rmtree(temporary_path)

        logger.info(f"已从 OK-WW 脚本默认配置初始化用户配置: {script_id} - {owner}")
        return target_config_dir

    def _zzzod_script_config(self, script_id: str) -> ZzzOdConfig:
        """解析 ZZZ-OD 脚本配置并拒绝跨类型 ID 访问。"""

        script_config = self.ScriptConfig[uuid.UUID(script_id)]
        if not isinstance(script_config, ZzzOdConfig):
            raise TypeError("脚本配置类型错误, 不是 ZZZ-OD 类型")
        return script_config

    def _zzzod_root(self, script_config: ZzzOdConfig) -> Path:
        """返回 zzz-od 安装根目录并按哨兵文件校验有效。

        三层防线（与 FolderValidator 非空分支、自动发现/check() 同一组哨兵）：
        1. 拒绝空串——``FolderValidator`` 对空串放行，``Path("").is_dir()``
           在 cwd 下为真，用户态保存会把 ``config/01/`` 建进 MAS 工作目录；
        2. 拒绝非绝对路径 / 不存在的目录 / ``Path.cwd()``；
        3. ``validate_install`` 安装哨兵（``src`` 目录）——任意随机目录
           （如 D:\\）只要 is_dir 就放行会在其下建出 config/01。不要求
           ``config/one_dragon.yml``：它由一条龙首次运行生成，全新安装
           尚未初始化时不应卡住启动器下拉/实例列表/任务目录等发现能力
           （读写路径自身会按需初始化；完整初始化校验用 validate_root）。
        """

        raw = str(script_config.get("Info", "RootPath") or "").strip()
        if not raw:
            raise ValueError("请先在脚本设置中配置绝区零一条龙安装目录")
        root = Path(raw).expanduser()
        if not root.is_absolute() or not root.is_dir():
            raise ValueError("请先在脚本设置中配置绝区零一条龙安装目录")
        resolved = root.resolve()
        if resolved == Path.cwd().resolve():
            raise ValueError("绝区零一条龙安装目录不能为 MAS 工作目录")

        from app.task.ZzzOd.tools import validate_install

        validate_install(resolved)
        return resolved

    def get_zzzod_root(self, script_id: str) -> Path:
        """zzz-od 安装根目录（哨兵校验后返回；供 API 层统一复用）。"""

        return self._zzzod_root(self._zzzod_script_config(script_id))

    def get_zzzod_instances(self, script_id: str) -> list[dict]:
        """列出 zzz-od 实例（供用户配置「快速导入」选择来源实例）。"""

        script_config = self._zzzod_script_config(script_id)
        root = self._zzzod_root(script_config)
        from app.task.ZzzOd.tools import list_instances

        return [
            {
                "idx": int(item.get("idx", 0)),
                "name": str(item.get("name", "")),
                "active": bool(item.get("active")),
                "active_in_od": bool(item.get("active_in_od")),
                "force_login_before_run": bool(
                    item.get("force_login_before_run")
                ),
            }
            for item in list_instances(root)
        ]

    def add_zzzod_instance(self, script_id: str, name: str) -> list[dict]:
        """直控：新建一条龙实例（最小空闲槽避开原生与跨脚本 MAS 绑定槽）。

        变更注册表与实例目录前先归档原生配置（指纹去重），保证可恢复。
        """

        script_config = self._zzzod_script_config(script_id)
        root = self._zzzod_root(script_config)

        from app.task.ZzzOd.AutoProxy import collect_used_slot_idxs
        from app.task.ZzzOd.tools import add_instance

        self.ensure_zzzod_direct_backup(script_id)
        idx = add_instance(root, name, collect_used_slot_idxs())
        logger.info(f"ZZZ-OD 直控新建实例: 槽 {idx:02d} (名称 {name})")
        return self.get_zzzod_instances(script_id)

    def rename_zzzod_instance(self, script_id: str, instance_idx: int, name: str) -> list[dict]:
        """直控：重命名实例（只改注册表 name，实例目录不变）。"""

        script_config = self._zzzod_script_config(script_id)
        root = self._zzzod_root(script_config)

        from app.task.ZzzOd.tools import rename_instance

        self.ensure_zzzod_direct_backup(script_id)
        rename_instance(root, instance_idx, name)
        logger.info(f"ZZZ-OD 直控重命名实例: {instance_idx:02d} → {name}")
        return self.get_zzzod_instances(script_id)

    def set_zzzod_instance_active_in_od(
        self, script_id: str, instance_idx: int, value: bool
    ) -> list[dict]:
        """直控：切换实例是否参与「全部实例」运行模式（active_in_od）。"""

        script_config = self._zzzod_script_config(script_id)
        root = self._zzzod_root(script_config)

        from app.task.ZzzOd.tools import set_instance_active_in_od

        self.ensure_zzzod_direct_backup(script_id)
        set_instance_active_in_od(root, instance_idx, value)
        logger.info(
            f"ZZZ-OD 直控实例 {instance_idx:02d} 参与全部实例 → {bool(value)}"
        )
        return self.get_zzzod_instances(script_id)

    def set_zzzod_instance_active(self, script_id: str, instance_idx: int) -> list[dict]:
        """直控：把所选实例设为当前活跃（「仅运行当前」运行的就是它）。"""

        script_config = self._zzzod_script_config(script_id)
        root = self._zzzod_root(script_config)

        from app.task.ZzzOd.tools import set_active_instance

        self.ensure_zzzod_direct_backup(script_id)
        set_active_instance(root, instance_idx)
        logger.info(f"ZZZ-OD 直控实例 {instance_idx:02d} 已设为当前活跃")
        return self.get_zzzod_instances(script_id)

    def set_zzzod_instance_run_mode(self, script_id: str, instance_run: str) -> None:
        """直控：设置运行实例（one_dragon.yml 全局 instance_run，白名单校验）。

        运行实例是脚本级全局设置，与直控页当前编辑哪个实例无关。
        """

        script_config = self._zzzod_script_config(script_id)
        root = self._zzzod_root(script_config)

        from app.task.ZzzOd.tools import save_native_instance_run

        self.ensure_zzzod_direct_backup(script_id)
        save_native_instance_run(root, instance_run)
        logger.info(f"ZZZ-OD 直控运行实例 → {instance_run}")

    def set_zzzod_instance_force_login(
        self, script_id: str, instance_idx: int, value: bool
    ) -> list[dict]:
        """直控：切换实例「运行前切换账号」（映射一条龙原生能力，MAS 不干涉）。"""

        script_config = self._zzzod_script_config(script_id)
        root = self._zzzod_root(script_config)

        from app.task.ZzzOd.tools import set_instance_force_login

        self.ensure_zzzod_direct_backup(script_id)
        set_instance_force_login(root, instance_idx, value)
        logger.info(
            f"ZZZ-OD 直控实例 {instance_idx:02d} 运行前切换账号 → {bool(value)}"
        )
        return self.get_zzzod_instances(script_id)

    def delete_zzzod_instance(self, script_id: str, instance_idx: int) -> list[dict]:
        """直控：删除实例（注册表 + 实例目录；MAS 绑定槽与最后实例受保护）。"""

        script_config = self._zzzod_script_config(script_id)
        root = self._zzzod_root(script_config)

        from app.task.ZzzOd.AutoProxy import collect_used_slot_idxs
        from app.task.ZzzOd.tools import remove_instance

        self.ensure_zzzod_direct_backup(script_id)
        remove_instance(
            root, instance_idx, protected_idxs=collect_used_slot_idxs()
        )
        logger.info(f"ZZZ-OD 直控删除实例: {instance_idx:02d}")
        return self.get_zzzod_instances(script_id)

    def _zzzod_user(
        self, script_id: str, user_id: str
    ) -> tuple[ZzzOdConfig, Path, ZzzOdUserConfig, uuid.UUID]:
        """解析 ZZZ-OD 脚本/安装目录/用户配置对象，拒绝无效 ID。"""

        script_config = self._zzzod_script_config(script_id)
        root = self._zzzod_root(script_config)
        uid = uuid.UUID(user_id)
        if uid not in script_config.UserData:
            raise ValueError("用户不存在")
        return script_config, root, script_config.UserData[uid], uid

    async def get_zzzod_app_config(
        self,
        script_id: str,
        user_id: str,
        app_id: str,
        instance_idx: int | None = None,
    ) -> dict:
        """任务级配置（字段元数据 + 当前值）。

        instance_idx 给定时（直控模式）读取该原生实例的 per-app YAML；
        否则读取用户绑定槽（未分配槽时取元数据默认值）。
        """

        from app.task.ZzzOd.tools import (
            get_task_app_fields,
            instance_dir,
            read_app_config,
            resolve_field_options,
        )

        fields_meta = get_task_app_fields(app_id)
        if fields_meta is None:
            raise ValueError(f"任务 {app_id} 不支持在 MAS 侧配置")

        if instance_idx is not None:
            root, _ = self._zzzod_native_instance(script_id, instance_idx)
            slot = int(instance_idx)
        else:
            _, root, user_cfg, _ = self._zzzod_user(script_id, user_id)
            slot = int(user_cfg.get("Info", "SlotIdx") or -1)
        current = read_app_config(root, slot, app_id) if slot > 0 else {}
        # 预备编队等选项随槽而异（team.yml 在实例目录），无槽时无动态选项
        config_dir = instance_dir(root, slot) if slot > 0 else None

        def _show_when_out(sw: dict | list | None) -> dict:
            """show_when 透传：单条件 dict 或条件列表（{field, value, not?}）。"""

            if not sw:
                return {}
            conds = sw if isinstance(sw, list) else [sw]
            return {
                "showWhen": [
                    {
                        "field": str(c["field"]),
                        "value": str(c["value"]),
                        **({"not": True} if c.get("not") else {}),
                    }
                    for c in conds
                ]
            }

        fields = []
        for meta in fields_meta:
            ftype = str(meta.get("type") or "select")
            field_out: dict = {
                "field": str(meta["field"]),
                "title": str(meta["title"]),
                "type": ftype,
            }
            if ftype == "plan_list":
                # 计划列表：当前值整表返回；列元数据内联（动态列选项服务端解析），
                # 级联列选项由前端从任务选项端点的训练副本树取
                value = current.get(meta["field"])
                field_out["value"] = value if isinstance(value, list) else []
                field_out["options"] = []
                field_out["columns"] = [
                    {
                        "field": str(c["field"]),
                        "title": str(c["title"]),
                        "type": str(c.get("type") or "select"),
                        "options": [
                            {"label": str(o["label"]), "value": str(o["value"])}
                            for o in resolve_field_options(root, c, config_dir)
                        ],
                        **_show_when_out(c.get("show_when")),
                    }
                    for c in meta.get("columns") or []
                ]
                field_out["newItem"] = dict(meta.get("new_item") or {})
            else:
                options = resolve_field_options(root, meta, config_dir)
                default = meta.get("default")
                if default is None and options:
                    default = str(options[0]["value"])
                value = current.get(meta["field"], default)
                if ftype == "bool":
                    value = bool(value)
                elif ftype == "number":
                    try:
                        value = int(value)
                    except (TypeError, ValueError):
                        value = int(default or 0)
                else:
                    # select / team：展示为字符串（team 与选项 value 同型，保存转 int）
                    value = None if value is None else str(value)
                field_out["value"] = value
                field_out["options"] = [
                    {"label": str(o["label"]), "value": str(o["value"])}
                    for o in options
                ]
            fields.append(field_out)
        return {"appId": app_id, "fields": fields}

    async def save_zzzod_app_config(
        self,
        script_id: str,
        user_id: str,
        app_id: str,
        values: dict,
        instance_idx: int | None = None,
    ) -> dict:
        """保存任务级配置到目标位置（字段白名单校验后写入）。

        instance_idx 给定时（直控模式）直接写该原生实例的 per-app YAML；
        否则写用户绑定槽（首次编辑会自动分配绑定槽）。值按字段类型转换
        （select→str / bool→bool / number→int），plan_list 整表合并写入并
        按 plan_id 保留既有 run_times。
        """

        from app.task.ZzzOd.tools import (
            get_task_app_fields,
            merge_plan_list,
            read_app_config,
            write_app_config,
        )

        fields_meta = get_task_app_fields(app_id)
        if fields_meta is None:
            raise ValueError(f"任务 {app_id} 不支持在 MAS 侧配置")
        meta_by_field = {str(m["field"]): m for m in fields_meta}
        unknown = {str(k) for k in values} - set(meta_by_field)
        if unknown:
            raise ValueError(f"不支持的配置字段: {', '.join(sorted(unknown))}")

        script_config = self._zzzod_script_config(script_id)
        root = self._zzzod_root(script_config)

        if instance_idx is not None:
            self._zzzod_native_instance(script_id, instance_idx)
            slot = int(instance_idx)
        else:
            from app.task.ZzzOd.AutoProxy import (
                collect_used_slot_idxs,
                ensure_user_slot,
            )

            _, _, user_cfg, uid = self._zzzod_user(script_id, user_id)
            used = collect_used_slot_idxs(exclude_uids={uid})
            slot = await ensure_user_slot(root, user_cfg, used)

        current = read_app_config(root, slot, app_id) if slot > 0 else {}
        patch: dict = {}
        for key, raw in values.items():
            meta = meta_by_field[str(key)]
            ftype = str(meta.get("type") or "select")
            if ftype == "plan_list":
                columns = meta.get("columns") or []
                patch[str(key)] = merge_plan_list(
                    columns,
                    dict(meta.get("new_item") or {}),
                    current.get(str(key)) if isinstance(current.get(str(key)), list) else [],
                    raw if isinstance(raw, list) else [],
                )
            elif ftype == "bool":
                patch[str(key)] = bool(raw)
            elif ftype == "number":
                patch[str(key)] = int(raw)
            elif ftype == "team":
                # 预备编队下标：上游按 int 消费（-1=游戏内配队），下拉提交字符串
                try:
                    patch[str(key)] = int(raw)
                except (TypeError, ValueError):
                    patch[str(key)] = -1
            else:
                # select：按声明选项的原始类型还原——GET 侧选项 value 已被
                # str() 抹平，前端回传字符串；选项声明为 int 的字段（周挑战
                # 起始日）落盘必须是 int，否则上游 `>=` 比较抛 TypeError
                raw_str = str(raw)
                matched = next(
                    (
                        o.get("value")
                        for o in meta.get("options") or []
                        if str(o.get("value")) == raw_str
                    ),
                    None,
                )
                if isinstance(matched, int) and not isinstance(matched, bool):
                    patch[str(key)] = matched
                else:
                    patch[str(key)] = raw_str

        config = write_app_config(root, slot, app_id, patch)
        if instance_idx is not None:
            logger.info(
                f"ZZZ-OD 实例 {slot:02d} 任务 {app_id} 配置已由直控页面保存: {values}"
            )
        else:
            logger.info(
                f"ZZZ-OD 用户 {uid} 任务 {app_id} 配置已保存到槽 {slot:02d}: {values}"
            )
        return config

    async def get_zzzod_task_options(self, script_id: str, app_id: str) -> dict:
        """任务计划的动态选项（副本级联树 / 配队方案 / 挑战配置等）。

        全部从安装目录静态读取（compendium_data.yml + 配置目录扫描），
        与一条龙原生 GUI 选项同源，上游升级后无需改 MAS。
        """

        from app.task.ZzzOd.tools import (
            auto_battle_options,
            get_task_app_fields,
            lost_void_challenge_options,
            lost_void_missions,
            train_categories,
        )

        if get_task_app_fields(app_id) is None:
            raise ValueError(f"任务 {app_id} 不支持在 MAS 侧配置")

        script_config = self._zzzod_script_config(script_id)
        root = self._zzzod_root(script_config)
        return {
            "appId": app_id,
            "trainCategories": train_categories(root),
            "lostVoidMissions": lost_void_missions(root),
            "autoBattle": auto_battle_options(root),
            "challenge": lost_void_challenge_options(root),
        }

    async def get_zzzod_teams(
        self, script_id: str, user_id: str, instance_idx: int | None = None
    ) -> dict:
        """预备编队完整列表（固定 20 个，与一条龙原生编队页一致）。

        team.yml：名称 + 绑定配队方案 + 成员（agent_id → 代理人下拉可选）。
        缺失项按上游规则补「编队N」默认编队。
        instance_idx 给定时（直控模式）读该原生实例；否则读用户绑定槽。
        附带配队方案与代理人选项（静态数据，不含识别能力）供前端渲染。
        """

        from app.task.ZzzOd.tools import (
            agent_id_options,
            auto_battle_options,
            expand_team_list,
            instance_dir,
        )

        if instance_idx is not None:
            root, _ = self._zzzod_native_instance(script_id, instance_idx)
            slot = int(instance_idx)
        else:
            _, root, user_cfg, _ = self._zzzod_user(script_id, user_id)
            slot = int(user_cfg.get("Info", "SlotIdx") or -1)

        teams = []
        if slot > 0:
            for item in expand_team_list(instance_dir(root, slot)):
                teams.append(
                    {
                        "idx": int(item["idx"]),
                        "name": str(item["name"]),
                        "autoBattle": str(item["auto_battle"]),
                        "agents": [str(a) for a in item["agent_id_list"]],
                    }
                )
        return {
            "teams": teams,
            "autoBattle": auto_battle_options(self._zzzod_script_root(script_id)),
            "agentOptions": agent_id_options(self._zzzod_script_root(script_id)),
        }

    async def save_zzzod_teams(
        self,
        script_id: str,
        user_id: str,
        teams: list,
        instance_idx: int | None = None,
    ) -> list:
        """整表保存预备编队（名称 + 绑定配队方案，成员按行保留）。"""

        from app.task.ZzzOd.tools import instance_dir, write_team_list

        if instance_idx is not None:
            self._zzzod_native_instance(script_id, instance_idx)
            slot = int(instance_idx)
        else:
            from app.task.ZzzOd.AutoProxy import (
                collect_used_slot_idxs,
                ensure_user_slot,
            )

            _, root, user_cfg, uid = self._zzzod_user(script_id, user_id)
            used = collect_used_slot_idxs(exclude_uids={uid})
            slot = await ensure_user_slot(root, user_cfg, used)

        saved = write_team_list(instance_dir(self._zzzod_script_root(script_id), slot), teams)
        logger.info(f"ZZZ-OD 预备编队已保存到槽 {slot:02d}: {len(saved)} 个编队")
        return saved

    def _zzzod_script_root(self, script_id: str) -> Path:
        """脚本安装根目录（供 teams 等实例级配置读写复用）。"""

        return self._zzzod_root(self._zzzod_script_config(script_id))

    async def ensure_zzzod_mas_backup(
        self, script_id: str, user_id: str
    ) -> dict:
        """确保 MAS 用户绑定槽有当前状态的备份（指纹去重，无变化跳过）。

        供编辑界面退出时机调用（MAS 侧配置终态）。用户尚未绑定槽时跳过
        （没有可恢复的内容），返回 ``created=False``。
        """

        from app.task.ZzzOd.tools import (
            archive_mas_config_backup,
            collect_mas_user_info,
            instance_dir,
            list_mas_backups,
        )

        _, _, user_cfg, _ = self._zzzod_user(script_id, user_id)
        slot = int(user_cfg.get("Info", "SlotIdx") or -1)
        slot_dir = instance_dir(self._zzzod_script_root(script_id), slot)
        if slot <= 0 or not slot_dir.is_dir():
            return {"created": False, "time": ""}

        # 统一入口：归档前物化本页账号+编排进槽（账号/编排只存在 UserData，
        # 槽要注入才带；不物化会漏、恢复会把本页字段清空），见文档 §3.1 陷阱
        dest = archive_mas_config_backup(
            script_id,
            slot,
            slot_dir,
            user_cfg,
            meta=collect_mas_user_info(user_cfg),
        )
        times = list_mas_backups(script_id, slot)
        return {
            "created": dest is not None,
            "time": times[0] if times else "",
        }

    async def restore_zzzod_backup(
        self, script_id: str, user_id: str, ts: str, target: str
    ) -> int:
        """把指定备份恢复到目标位置，返回关联槽 idx（-1 表示不涉及槽）。

        - target="onedragon"：把一条龙原生配置备份（one_dragon.yml + 原生
          实例目录）恢复到一条龙本身——只写回备份中的文件，MAS 槽目录永不
          触碰；恢复前自动归档当前原生配置，误恢复可找回；
        - target="mas"：把 MAS 用户槽备份恢复到绑定槽，并从恢复后的槽内容
          把账号字段与任务编排全量回填到 MAS 本页字段（表单随即刷新）——
          配队等 MAS 不管的内容随槽内容回到该时点。
        """

        from app.task.ZzzOd.tools import (
            MAS_USER_INFO_FILE,
            collect_mas_user_info,
            get_mas_backup_dir,
            get_onedragon_backup_dir,
            instance_dir,
            materialize_user_fields,
            normalize_app_group_entries,
            read_app_group,
            read_game_account,
            restore_mas_backup,
            restore_onedragon_backup,
        )
        from app.utils.config_archive import dir_files
        from app.utils.io import read_file

        _, root, user_cfg, uid = self._zzzod_user(script_id, user_id)

        if target == "onedragon":
            # 恢复守卫：备份内的原生实例 idx 若已被任一 MAS 用户绑定为配置槽
            # （任何脚本、含本用户——恢复会整目录替换槽目录），中止并点名，
            # 避免把绑定槽内容覆盖成原生实例；原生注册表不在此列，恢复本就
            # 是把原生世界拉回该时点（恢复前已强制存底）
            backup_dir = get_onedragon_backup_dir(root, ts)
            if backup_dir is None:
                raise ValueError(f"备份不存在: {ts}")
            backup_idxs = {
                int(rel.split("/", 1)[0])
                for rel in dir_files(backup_dir)
                if "/" in rel and rel.split("/", 1)[0].isdigit()
            }
            for bound_script in self.ScriptConfig.values():
                if not isinstance(bound_script, ZzzOdConfig):
                    continue
                for bound_uid, bound_cfg in bound_script.UserData.items():
                    bound_slot = int(bound_cfg.get("Info", "SlotIdx") or -1)
                    if bound_slot not in backup_idxs:
                        continue
                    if bound_uid == uid:
                        who = "本用户"
                    else:
                        who = (
                            f"脚本「{str(bound_script.get('Info', 'Name') or '未知脚本')}」"
                            f"的用户「{str(bound_cfg.get('Info', 'Name') or '未知用户')}」"
                        )
                    raise ValueError(
                        f"备份含原生实例 {bound_slot:02d}，已被{who}绑定为配置槽，"
                        "恢复会覆盖其内容，已中止"
                    )
            restore_onedragon_backup(root, ts)
            logger.info(f"ZZZ-OD 用户 {uid} 已把备份 {ts} 恢复到一条龙原生配置")
            return -1

        slot = int(user_cfg.get("Info", "SlotIdx") or -1)
        if slot <= 0:
            raise ValueError("该用户还没有生成过配置备份")
        # 恢复守卫：目标槽必须仍归本用户或空闲，被其他实体占用则拦截并点名，
        # 避免把别人的槽内容覆盖掉（覆盖前也不归档他人内容）
        occupant = self._zzzod_slot_occupant(root, script_id, uid, slot)
        if occupant is not None:
            raise ValueError(
                f"目标槽 {slot:02d} 当前已被「{occupant}」占用，"
                "为避免覆盖他人配置已中止恢复，请先处理占用后再试"
            )
        # 恢复前先物化本页账号+编排进槽，再走 restore_mas_backup 内部「强制
        # 归档当前」——这份「恢复前存底」才能回到本页配置状态（否则缺账号，
        # 误恢复想找回时会把本页账号清空）
        slot_dir = instance_dir(root, slot)
        materialize_user_fields(slot_dir, user_cfg)
        restore_mas_backup(
            script_id,
            slot,
            ts,
            slot_dir,
            meta=collect_mas_user_info(user_cfg),
        )

        # 恢复后的槽内容 = 该时点的 MAS 配置；把 MAS 管理的字段全量回填本页
        account = read_game_account(slot_dir)
        # 任务编排整表回填（含未启用项原位保留顺序，运行侧只消费启用项）
        all_apps = normalize_app_group_entries(read_app_group(slot_dir))
        await user_cfg.set(
            "Game", "GameRegion", str(account.get("game_region") or "cn")
        )
        await user_cfg.set("Game", "GamePath", str(account.get("game_path") or ""))
        await user_cfg.set(
            "Game", "GameLanguage", str(account.get("game_language") or "cn")
        )
        await user_cfg.set(
            "Game", "BilibiliAccountName",
            str(account.get("bilibili_account_name") or ""),
        )
        await user_cfg.set("Game", "Account", str(account.get("account") or ""))
        await user_cfg.set("Game", "Password", str(account.get("password") or ""))
        await user_cfg.set(
            "OneDragon", "AppList", json.dumps(all_apps, ensure_ascii=False)
        )
        # 信息字段回填（用户名/启用/模式/启动器/剩余天数/备注/节点详情推送）：
        # 旧备份可能没有该快照，缺失字段跳过，保持向前兼容
        backup_dir = get_mas_backup_dir(script_id, slot, ts)
        if backup_dir is not None:
            info = read_file(backup_dir / MAS_USER_INFO_FILE) or {}
            for field in ("Name", "Status", "Mode", "LauncherMode",
                          "RemainedDay", "Notes"):
                if field in info:
                    await user_cfg.set("Info", field, info[field])
            if "PushLogMode" in info:
                await user_cfg.set("Notify", "PushLogMode", info["PushLogMode"])
        await self.ScriptConfig.save()
        logger.info(
            f"ZZZ-OD 用户 {uid} 已把备份 {ts} 恢复到 MAS 配置 "
            f"(槽 {slot:02d} + 字段回填, 任务 {len(all_apps)} 项)"
        )
        return slot

    async def import_zzzod_config(
        self, script_id: str, user_id: str, instance_idx: int
    ) -> dict:
        """基于一条龙已有实例快速生成当前用户配置（账号信息 + 已启用任务编排 + 实例级配置）。

        覆盖前强制归档当前 MAS 槽配置（与「配置恢复」一致：即使内容与最近
        备份一致也生成新时间戳条目）——导入前的状态可在配置恢复中按 MAS
        配置找回。账号字段只回填来源实例的非空值（密码留空=沿用登录态），
        任务编排只取来源实例当前启用的应用（对齐 _group.yml 缺席=不加入）。
        实例级配置随导入对齐来源实例写入绑定槽：notify.yml（应用通知，
        zzz-od 默认开启，不搬会让「来源关着」变开着）、team.yml（预备编队）、
        game.yml（按键配置：键盘/手柄按键、后台模式、输入方式、HDR、启动
        参数、分辨率等，MAS 不托管、注入不触碰，只能靠导入对齐）、
        one_dragon/ 全部 per-app 配置（体力计划/咖啡店/随便观等任务级 yml）。
        """

        from app.task.ZzzOd.AutoProxy import (
            collect_used_slot_idxs,
            ensure_user_slot,
        )
        from app.task.ZzzOd.tools import (
            archive_mas_config_backup,
            collect_mas_user_info,
            instance_dir,
            normalize_app_group_entries,
            read_app_group,
            read_game_account,
        )

        _, root, user_cfg, uid = self._zzzod_user(script_id, user_id)
        slot = int(user_cfg.get("Info", "SlotIdx") or -1)
        if slot > 0:
            slot_dir = root / "config" / f"{slot:02d}"
            if slot_dir.is_dir():
                # 覆盖前存底走统一入口（先物化再快照）：不物化的「导入前」
                # 备份缺账号，恢复它会把本页账号清空
                archive_mas_config_backup(
                    script_id,
                    slot,
                    slot_dir,
                    user_cfg,
                    force=True,
                    meta=collect_mas_user_info(user_cfg),
                )

        native_root, instance = self._zzzod_native_instance(script_id, instance_idx)
        source_dir = instance_dir(native_root, int(instance_idx))
        game_account = read_game_account(source_dir)
        # 任务编排整表导入（含未启用项原位保留顺序，运行侧只消费启用项）
        all_apps = normalize_app_group_entries(read_app_group(source_dir))

        field_map = {
            "GameRegion": "game_region",
            "GamePath": "game_path",
            "GameLanguage": "game_language",
            "Account": "account",
            "Password": "password",
            "BilibiliAccountName": "bilibili_account_name",
            "Platform": "platform",
            "CustomWinTitle": "custom_win_title",
        }
        imported_accounts = 0
        for user_key, native_key in field_map.items():
            value = str(game_account.get(native_key) or "").strip()
            if not value:
                continue
            await user_cfg.set("Game", user_key, value)
            imported_accounts += 1
        if "use_custom_win_title" in game_account:
            await user_cfg.set(
                "Game", "UseCustomWinTitle",
                bool(game_account.get("use_custom_win_title")),
            )
            imported_accounts += 1

        await user_cfg.set(
            "OneDragon", "AppList", json.dumps(all_apps, ensure_ascii=False)
        )

        # 实例级持久配置对齐来源实例：
        # - notify.yml（应用通知）在实例根
        # - team.yml（预备编队：名称 + 绑定配队方案 + 成员）在实例根
        # - game.yml（GameConfig 按键配置：键盘/手柄按键、后台模式、输入方式、
        #   HDR、启动参数、分辨率）在实例根——MAS 不托管该文件，注入运行也
        #   不触碰，导入不对齐会导致按键配置永远停留在 zzz-od 默认值
        # - one_dragon/ 全部 per-app 配置（charge_plan.yml 体力计划、coffee.yml
        #   咖啡店、suibian_temple.yml 随便观等）随导入整目录对齐
        # _group.yml 例外：任务编排走上面的 AppList 整表语义（含未启用项），不整搬。
        # 均不经 MAS 用户字段承载，直接对齐到绑定槽（注入运行的实例目录）；
        # 用户尚无绑定槽时按全局查重分配（语义与运行注入的 ensure_user_slot
        # 一致）。来源缺失的文件对齐为删除 = 沿用 zzz-od 默认
        slot = int(user_cfg.get("Info", "SlotIdx") or -1)
        if slot <= 0:
            slot = await ensure_user_slot(
                root, user_cfg, collect_used_slot_idxs(exclude_uids={uid})
            )
        target_dir = instance_dir(root, slot)
        target_dir.mkdir(parents=True, exist_ok=True)

        def _align_yml(rel_parts: list[str]) -> None:
            source_yml = source_dir.joinpath(*rel_parts)
            target_yml = target_dir.joinpath(*rel_parts)
            target_yml.parent.mkdir(parents=True, exist_ok=True)
            if source_yml.is_file():
                shutil.copyfile(source_yml, target_yml)
            else:
                target_yml.unlink(missing_ok=True)

        _align_yml(("notify.yml",))
        _align_yml(("team.yml",))
        _align_yml(("game.yml",))

        source_one_dragon = source_dir / "one_dragon"
        target_one_dragon = target_dir / "one_dragon"
        if target_one_dragon.is_dir():
            for target_yml in target_one_dragon.glob("*.yml"):
                if target_yml.name != "_group.yml" and not (
                    source_one_dragon / target_yml.name
                ).is_file():
                    target_yml.unlink(missing_ok=True)
        if source_one_dragon.is_dir():
            target_one_dragon.mkdir(parents=True, exist_ok=True)
            for source_yml in source_one_dragon.glob("*.yml"):
                if source_yml.name == "_group.yml":
                    continue
                shutil.copyfile(source_yml, target_one_dragon / source_yml.name)

        await self.ScriptConfig.save()
        logger.info(
            f"ZZZ-OD 用户 {uid} 已从实例 {int(instance_idx):02d} 导入配置"
            f"(账号字段 {imported_accounts} 项, 任务 {len(all_apps)} 项, "
            f"应用通知/按键配置/体力计划已对齐槽 {slot:02d})"
        )
        return {
            "instanceIdx": int(instance_idx),
            "instanceName": str(instance.get("name", "")),
            "importedAccountCount": imported_accounts,
            "importedTaskCount": len(all_apps),
            "slot": slot,
        }

    def _zzzod_slot_occupant(
        self, root: Path, script_id: str, user_uid: uuid.UUID, slot: int
    ) -> str | None:
        """判定目标实例槽当前被谁占用（返回可读描述；空闲/仅本用户时 None）。

        占用者可能是：其他 ZzzOd 脚本/同脚本其他用户（按 ``Info.SlotIdx``
        绑定）或一条龙原生实例（按原生注册表）。注册表源走原生原件（合成
        视图在盘时读 sidecar），与备份口径一致。仅本用户绑定或槽目录虽在但
        无人认领（孤儿槽）视为空闲——孤儿槽可被恢复重新认领。
        """

        from app.task.ZzzOd.tools import native_registry_file
        from app.utils.io import read_file

        # 1) 其他 ZzzOd 用户（含其他脚本）按 SlotIdx 绑定占用
        for script_config in self.ScriptConfig.values():
            if not isinstance(script_config, ZzzOdConfig):
                continue
            script_name = str(
                script_config.get("Info", "Name") or "未知脚本"
            )
            for other_uid, cfg in script_config.UserData.items():
                if other_uid == user_uid:
                    continue
                if int(cfg.get("Info", "SlotIdx") or -1) == slot:
                    user_name = str(cfg.get("Info", "Name") or "未知用户")
                    return f"脚本「{script_name}」的用户「{user_name}」"

        # 2) 一条龙原生实例（按原生注册表）
        data = read_file(native_registry_file(root)) or {}
        for item in data.get("instance_list") or []:
            if not isinstance(item, dict):
                continue
            if int(item.get("idx", -1)) == slot:
                return str(item.get("name") or f"原生实例 {slot:02d}")
        return None

    @staticmethod
    def _preview_account_fields(account: dict) -> list[dict]:
        """备份预览用的账号字段列表；密码一律掩码、不返回明文。

        预览是纯展示（恢复直接回写备份文件内容，不经此值），密码明文没有
        理由出现在响应里；其余字段缺失时合并默认值（无值前端兜底 ``—``）。
        mas 与 onedragon 两个预览分支共用。
        """

        from app.task.ZzzOd.tools.zzz_od_config import DEFAULT_GAME_ACCOUNT

        return [
            {
                "key": key,
                "value": (
                    "••••••••"
                    if key == "password" and account.get(key)
                    else str(
                        account[key]
                        if account.get(key) is not None
                        else DEFAULT_GAME_ACCOUNT.get(key, "")
                    )
                ),
            }
            for key in (
                "game_region",
                "game_path",
                "game_language",
                "account",
                "password",
                "bilibili_account_name",
            )
        ]

    def get_zzzod_backup_preview(
        self, script_id: str, user_id: str, ts: str, target: str
    ) -> dict:
        """读取指定备份的配置摘要（纯读不恢复），供「预览配置」快速展示。

        - target="mas"：基本信息卡信息字段（用户名/启用/模式/启动器/剩余天数/
          备注/节点详情推送，来自备份内信息快照）+ 账号字段（缺失合并默认值，
          密码掩码）+ 任务编排（应用目录并入中文名）；
        - target="onedragon"：备份内 one_dragon.yml 注册表的实例列表。
        """

        from app.task.ZzzOd.tools import (
            MAS_USER_INFO_FILE,
            get_mas_backup_dir,
            get_onedragon_backup_dir,
            list_app_catalog,
            read_app_group,
            read_game_account,
        )
        from app.utils.io import read_file

        # 脚本安装根目录（onedragon/mas 两条分支都要用：实例名书、槽目录）
        root = self._zzzod_root(self._zzzod_script_config(script_id))

        if target == "onedragon":
            backup = get_onedragon_backup_dir(root, ts)
            if backup is None:
                raise ValueError(f"备份不存在: {ts}")
            data = read_file(backup / "one_dragon.yml") or {}
            name_book = {
                str(item.get("app_id")): str(item.get("app_name") or "")
                for item in list_app_catalog(root)
            }
            instances = []
            for item in data.get("instance_list") or []:
                if not isinstance(item, dict):
                    continue
                idx = int(item.get("idx", 0))
                # 实例明细来自备份目录内的 {idx}/（备份按原生注册表逐 idx 归档，
                # 目录名不带零填充，与一条龙原生实例目录同构）
                backup_idx_dir = backup / str(idx)
                account = read_game_account(backup_idx_dir)
                account_fields = self._preview_account_fields(account)
                task_fields = []
                for task in read_app_group(backup_idx_dir):
                    app_id = str(task.get("app_id") or "").strip()
                    if not app_id:
                        continue
                    task_fields.append(
                        {
                            "app_id": app_id,
                            "app_name": name_book.get(app_id) or app_id,
                            "enabled": bool(task.get("enabled")),
                        }
                    )
                instances.append(
                    {
                        "idx": idx,
                        "name": str(item.get("name", "")),
                        "active": bool(item.get("active")),
                        "active_in_od": bool(item.get("active_in_od")),
                        "account": account_fields,
                        "tasks": task_fields,
                    }
                )
            return {
                "time": ts,
                "target": target,
                "info": [],
                "account": [],
                "tasks": [],
                "instances": instances,
            }

        _, root, user_cfg, _ = self._zzzod_user(script_id, user_id)
        slot = int(user_cfg.get("Info", "SlotIdx") or -1)
        if slot <= 0:
            raise ValueError("该用户还没有生成过配置备份")
        backup = get_mas_backup_dir(script_id, slot, ts)
        if backup is None:
            raise ValueError(f"备份不存在: {ts}")

        info = read_file(backup / MAS_USER_INFO_FILE) or {}
        info_fields = []
        for key, field in (
            ("name", "Name"),
            ("status", "Status"),
            ("mode", "Mode"),
            ("launcher_mode", "LauncherMode"),
            ("remained_day", "RemainedDay"),
            ("notes", "Notes"),
            ("push_log_mode", "PushLogMode"),
        ):
            if field not in info:
                continue
            info_fields.append({"key": key, "value": str(info[field])})

        account = read_game_account(backup)
        account_fields = self._preview_account_fields(account)

        name_book = {
            str(item.get("app_id")): str(item.get("app_name") or "")
            for item in list_app_catalog(root)
        }
        tasks = []
        for item in read_app_group(backup):
            app_id = str(item.get("app_id") or "").strip()
            if not app_id:
                continue
            tasks.append(
                {
                    "app_id": app_id,
                    "app_name": name_book.get(app_id) or app_id,
                    "enabled": bool(item.get("enabled")),
                }
            )
        return {
            "time": ts,
            "target": target,
            "info": info_fields,
            "account": account_fields,
            "tasks": tasks,
            "instances": [],
        }

    def _zzzod_native_instance(
        self, script_id: str, instance_idx: int
    ) -> tuple[Path, dict]:
        """解析 zzz-od 安装根目录与原生实例，校验实例存在（直控编辑目标）。"""

        script_config = self._zzzod_script_config(script_id)
        root = self._zzzod_root(script_config)

        from app.task.ZzzOd.tools import list_instances

        instance = next(
            (
                item
                for item in list_instances(root)
                if int(item.get("idx", -1)) == int(instance_idx)
            ),
            None,
        )
        if instance is None:
            raise ValueError(f"实例 {int(instance_idx):02d} 不存在")
        return root, instance

    async def get_zzzod_native_config(
        self, script_id: str, instance_idx: int
    ) -> dict:
        """读取实例原生配置（账号字段 + 任务编排 + 运行实例），供直控页面表单渲染。

        account 条目含默认值合并与可选项；tasks 为原生 app_list 与应用目录
        合并后的任务卡片数据（enabled 保持原生状态）；instanceRun 为
        one_dragon.yml 的 instance_run 原值（仅运行当前/全部实例）。
        """

        root, instance = self._zzzod_native_instance(script_id, instance_idx)
        slot = int(instance_idx)

        from app.task.ZzzOd.tools import (
            get_task_app_fields,
            get_task_app_jump,
            list_app_catalog,
            read_native_account_fields,
            read_native_instance_run,
            read_native_tasks,
        )

        catalog = [
            {
                **item,
                "configurable": get_task_app_fields(str(item["app_id"]))
                is not None,
                "jump": get_task_app_jump(str(item["app_id"])),
            }
            for item in list_app_catalog(root)
        ]
        return {
            "instanceIdx": slot,
            "instanceName": str(instance.get("name", "")),
            "account": read_native_account_fields(root, slot),
            "tasks": read_native_tasks(root, slot, catalog),
            "instanceRun": read_native_instance_run(root),
        }

    async def save_zzzod_native_config(
        self,
        script_id: str,
        instance_idx: int,
        account: dict | None = None,
        tasks: list[dict] | None = None,
        instance_run: str | None = None,
    ) -> dict:
        """把直控页面改动直接写回所选实例原生配置（可选增量，缺省字段不写回）。

        账号字段白名单过滤 + 只写非默认值；任务编排保留完整顺序（含未启用项）；
        instance_run 白名单校验。由调用方按需传参：任务开关/运行实例等
        即时写入只传对应字段，避免把未确认的账号草稿一并落盘。
        """

        root, instance = self._zzzod_native_instance(script_id, instance_idx)
        slot = int(instance_idx)

        from app.task.ZzzOd.tools import (
            read_native_instance_run,
            save_native_account_fields,
            save_native_instance_run,
            save_native_tasks,
        )

        if account is not None:
            save_native_account_fields(root, slot, account)
        if tasks is not None:
            save_native_tasks(root, slot, tasks)
        if instance_run is not None:
            # 等于原生文件当前值时跳过写：避免直控页保存账号/任务时把
            # 用户没改过的运行实例值写死（review 提的：从没动过下拉的多
            # 实例用户会被「仅运行当前」覆盖 → 一条龙从跑全部变成只跑当前）
            current = read_native_instance_run(root)
            if instance_run != current:
                save_native_instance_run(root, instance_run)
        logger.info(f"ZZZ-OD 实例 {slot:02d} 原生配置已由直控页面保存")
        return {
            "instanceIdx": slot,
            "instanceName": str(instance.get("name", "")),
            "savedAccountCount": len(account) if account is not None else 0,
        }

    def ensure_zzzod_direct_backup(self, script_id: str) -> dict:
        """直控前置保护：确保一条龙原生配置已有最新备份（指纹去重）。

        对当前一条龙原生配置（one_dragon.yml + 原生实例目录，排除 MAS 槽）
        与最近一份备份做指纹对比：无任何备份或内容已变化则立即归档——让
        用户在直控页误操作改坏原生配置前，始终存在一个「切换时点」的恢复点。

        Returns:
            {"created": 是否本次新建, "time": 最新备份时间戳}。
        """

        script_config = self._zzzod_script_config(script_id)
        root = self._zzzod_root(script_config)

        from app.task.ZzzOd.tools import (
            archive_onedragon_backup,
            list_onedragon_backups,
        )

        dest = archive_onedragon_backup(root)
        times = list_onedragon_backups(root)
        return {
            "created": dest is not None,
            "time": times[0] if times else "",
        }

    def get_zzzod_launchers(self, script_id: str) -> dict:
        """返回 zzz-od 两种启动器的安装情况（启动器下拉/禁用未安装项用）。

        Returns:
            {"original_available": bool, "integrated_available": bool}
        """

        script_config = self._zzzod_script_config(script_id)
        root = self._zzzod_root(script_config)

        from app.task.ZzzOd.AutoProxy import find_launchers

        available = find_launchers(root)
        return {
            "original_available": "原始" in available,
            "integrated_available": "集成" in available,
        }

    # ════════════ 配置恢复（基座统一分发，池声明见各专项 tools/restore_service） ════════════

    def restore_service(self, script_id: str, user_id: str) -> "ConfigRestoreService":
        """按脚本类型分发到专项恢复池，绑定上下文构建运行时服务。

        专项只声明池表（普通函数，显式收 :class:`RestoreContext`），本方法
        与下方四个通用门面方法就是全部接线——新专项接入不再改 HTTP 层
        与 schema，只在分发链加一个分支。
        """

        from app.utils.config_restore import RestoreContext, build_restore_service

        script_config = self.ScriptConfig[uuid.UUID(script_id)]
        if isinstance(script_config, ZzzOdConfig):
            from app.task.ZzzOd.tools.restore_service import (
                RESTORE_POOLS,
                RESTORE_SCRIPT_NAME,
            )
        elif isinstance(script_config, OkNteConfig):
            from app.task.OkNte.tools.restore_service import (
                RESTORE_POOLS,
                RESTORE_SCRIPT_NAME,
            )
        else:
            raise ValueError("该专项暂不支持配置恢复")
        return build_restore_service(
            RestoreContext(
                config=self,
                script_config=script_config,
                script_id=script_id,
                user_id=user_id,
            ),
            RESTORE_SCRIPT_NAME,
            RESTORE_POOLS,
        )

    async def list_config_backups(
        self, script_id: str, user_id: str, target: str
    ) -> list[dict]:
        """列出配置备份（时间倒序）。target 取值由专项池定义。"""

        service = self.restore_service(script_id, user_id)
        return [{"time": ts} for ts in await service.list(target)]

    async def ensure_config_backup(
        self, script_id: str, user_id: str, target: str
    ) -> dict:
        """按需归档目标池当前配置（指纹去重，无变化自动跳过）。

        编辑界面三时机的统一入口：进入/退出编辑页（前端触发）、运行前
        （各专项任务流程调用专项归档函数，不经本方法）。
        """

        return await self.restore_service(script_id, user_id).ensure(target)

    async def restore_config_backup(
        self, script_id: str, user_id: str, ts: str, target: str
    ) -> dict:
        """把指定备份恢复到目标位置（恢复前存底由专项池函数自理）。"""

        await self.restore_service(script_id, user_id).restore(target, ts)
        return {"target": target}

    async def get_config_backup_preview(
        self, script_id: str, user_id: str, ts: str, target: str
    ) -> dict:
        """读取指定备份的配置摘要（纯读不恢复）；载荷结构由专项定义。"""

        payload = await self.restore_service(script_id, user_id).preview(target, ts)
        return {"time": ts, "target": target, "data": payload}

    async def update_user(
        self, script_id: str, user_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新用户配置"""

        logger.info(f"{script_id} 更新用户配置: {user_id}")

        script_uid = uuid.UUID(script_id)
        user_uid = uuid.UUID(user_id)
        script_config = self.ScriptConfig[script_uid]
        user_config = script_config.UserData[user_uid]

        # ZzzOd 专项守卫：每脚本仅允许一个直控用户——直控是脚本级全局视图
        # （实例/活跃/运行实例都在一份 one_dragon.yml），多直控用户共享同一
        # 份状态互相干扰，多账号由直控页实例管理直接配置。
        # 切入直控时同步清空任务编排残留：直控不消费 AppList，残留会让
        # 注入名单误把直控用户卷入多账号运行（直控=MAS 零注入零干涉）。
        if isinstance(script_config, ZzzOdConfig):
            new_mode = str(data.get("Info", {}).get("Mode", "") or "")
            if new_mode == "直控":
                data.setdefault("OneDragon", {})["AppList"] = "[]"
            if (
                new_mode == "直控"
                and str(user_config.get("Info", "Mode") or "用户") != "直控"
                and any(
                    str(cfg.get("Info", "Mode") or "用户") == "直控"
                    for uid, cfg in script_config.UserData.items()
                    if uid != user_uid
                )
            ):
                raise ValueError(
                    "每个脚本仅允许一个直控用户, 多账号请在该用户的实例管理中配置"
                )

        await user_config.update(data)

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
        script_config = self.ScriptConfig[script_uid]

        await script_config.UserData.remove(user_uid)
        if (Path.cwd() / f"data/{script_id}/{user_id}").exists():
            shutil.rmtree(Path.cwd() / f"data/{script_id}/{user_id}")

    async def reorder_user(self, script_id: str, index_list: list[str]) -> None:
        """重新排序用户"""

        logger.info(f"{script_id} 重新排序用户: {index_list}")

        script_uid = uuid.UUID(script_id)

        await self.ScriptConfig[script_uid].UserData.setOrder(
            list(map(uuid.UUID, index_list))
        )

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
            data.append({"label": plan.get("name", f"排班 {i + 1}"), "value": str(i)})

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

        # 220 KB 的物品表每次打开用户编辑页都要解析, 按文件 mtime 缓存
        mtime_ns = item_index_path.stat().st_mtime_ns
        cached = self._maa_depot_items_cache.get(item_index_path)
        if cached is not None and cached[0] == mtime_ns:
            return cached[1]

        items = json.loads(item_index_path.read_text(encoding="utf-8"))
        options = [
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
        self._maa_depot_items_cache[item_index_path] = (mtime_ns, options)
        return options

    async def get_maa_depot_stage_candidates(
        self, script_id: str, item_id: str
    ) -> list[dict[str, str]]:
        """获取掉落指定材料的关卡候选（按单件期望理智升序，即 xx 理智/件）。

        编排逻辑在 task 域（cultivate.service）；本方法只做脚本解析与转发，
        保持既有对外契约不变。
        """

        script_config = self.ScriptConfig[uuid.UUID(script_id)]
        if not isinstance(script_config, MaaConfig):
            raise TypeError(f"脚本 {script_id} 不是 MAA 脚本")

        # 惰性导入：避免 core 层在模块加载期依赖 task 域
        from app.task.MAA.tools.cultivate import depot_cultivate_service

        return await depot_cultivate_service.stage_candidates(
            config_path=self.config_path,
            item_id=item_id,
            proxy=self.proxy,
        )

    async def get_maa_depot_inventory(self, script_id: str) -> list[dict[str, str]]:
        """获取 MAA 仓库库存（安装级 DepotData；label=数量，value=物品ID）。"""

        script_config = self.ScriptConfig[uuid.UUID(script_id)]
        if not isinstance(script_config, MaaConfig):
            raise TypeError(f"脚本 {script_id} 不是 MAA 脚本")

        from app.task.MAA.tools.cultivate import depot_cultivate_service

        data_dir = Path(script_config.get("Info", "Path")) / "data"
        inventory = await depot_cultivate_service.inventory(maa_data_dir=data_dir)
        if inventory is None:
            raise FileNotFoundError(
                f"未找到 MAA 仓库数据: {data_dir / 'DepotData.json'}，"
                "请先在 MAA 中执行一次仓库识别"
            )
        return [
            {"label": str(count), "value": item_id}
            for item_id, count in sorted(inventory.items())
        ]

    async def add_plan(
        self, script: Literal["MaaPlan", "MaaEndPlan"]
    ) -> tuple[uuid.UUID, MaaPlanConfig | MaaEndPlanConfig]:
        """添加计划表"""

        logger.info(f"添加计划表: {script}")

        plan_class = next(
            item["config_class"]
            for item in PLAN_BOOK.values()
            if item["create_type"] == script
        )
        return await self.PlanConfig.add(plan_class)

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

        await self.PlanConfig[plan_uid].update(data)

    async def del_plan(self, plan_id: str) -> None:
        """删除计划表配置"""

        logger.info(f"删除计划表配置: {plan_id}")

        plan_uid = uuid.UUID(plan_id)

        plan_config = self.PlanConfig[plan_uid]
        plan_type = type(plan_config).__name__
        if plan_type not in PLAN_BOOK:
            raise TypeError(f"不支持的计划表配置类型: {plan_type}")

        consumer_config = PLAN_BOOK[plan_type]
        user_list: list[MaaUserConfig | MaaEndUserConfig] = []

        for script in self.ScriptConfig.values():
            if not isinstance(script, consumer_config["script_class"]):
                continue
            for user in script.UserData.values():
                if user.get("Info", consumer_config["field_name"]) != str(plan_uid):
                    continue
                if user.is_locked:
                    raise RuntimeError(
                        f"用户 {user.get('Info', 'Name')} 正在使用此计划表且被锁定, 无法完成删除"
                    )
                user_list.append(user)

        for user in user_list:
            await user.set("Info", consumer_config["field_name"], "Fixed")

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

        await self.EmulatorConfig[emulator_uid].update(data)

    async def del_emulator(self, emulator_id: str) -> None:
        """删除模拟器配置"""

        emulator_uid = uuid.UUID(emulator_id)

        logger.info(f"删除全局模拟器配置: {emulator_id}")

        script_list = []

        for script in self.ScriptConfig.values():
            if isinstance(script, MaaConfig):
                if script.get("Emulator", "Id") == str(emulator_id):
                    if script.is_locked:
                        raise RuntimeError(
                            f"脚本 {script.get('Info', 'Name')} 正在使用此模拟器且被锁定, 无法完成删除"
                        )
                    script_list.append(script)
            elif isinstance(script, GeneralConfig):
                if script.get("Game", "Type") == "Emulator" and script.get(
                    "Game", "EmulatorId"
                ) == str(emulator_id):
                    if script.is_locked:
                        raise RuntimeError(
                            f"脚本 {script.get('Info', 'Name')} 正在使用此模拟器且被锁定, 无法完成删除"
                        )
                    script_list.append(script)

        for script in script_list:
            if isinstance(script, MaaConfig):
                await script.set("Emulator", "Id", "-")
            elif isinstance(script, GeneralConfig):
                await script.set("Game", "EmulatorId", "-")

        await self.EmulatorConfig.remove(emulator_uid)

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
        # 队列名、完成后操作这类字段改了不影响正在跑的循环，放行；
        # 只有循环开关本身不能在运行中动。
        if "CycleEnabled" in data.get("Info", {}):
            self._ensure_cycle_safe(queue_uid, "切换循环开关")

        await self.QueueConfig[queue_uid].update(data)

    async def del_queue(self, queue_id: str) -> None:
        """删除调度队列配置"""

        logger.info(f"删除调度队列配置: {queue_id}")

        queue_uid = uuid.UUID(queue_id)
        self._ensure_cycle_safe(queue_uid, "删除")

        await self.QueueConfig.remove(queue_uid)

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

        await self.QueueConfig[queue_uid].TimeSet[time_set_uid].update(data)

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
        self._ensure_cycle_safe(queue_uid, "增删队列项")

        uid, config = await self.QueueConfig[queue_uid].QueueItem.add(QueueItem)

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

        await self.QueueConfig[queue_uid].QueueItem[queue_item_uid].update(data)

    async def del_queue_item(self, queue_id: str, queue_item_id: str) -> None:
        """删除队列项配置"""

        logger.info(f"{queue_id} 删除队列项配置: {queue_item_id}")

        queue_uid = uuid.UUID(queue_id)
        queue_item_uid = uuid.UUID(queue_item_id)
        self._ensure_cycle_safe(queue_uid, "增删队列项")

        await self.QueueConfig[queue_uid].QueueItem.remove(queue_item_uid)

    async def reorder_queue_item(self, queue_id: str, index_list: list[str]) -> None:
        """重新排序队列项"""

        logger.info(f"{queue_id} 重新排序队列项: {index_list}")

        queue_uid = uuid.UUID(queue_id)
        self._ensure_cycle_safe(queue_uid, "调整队列项顺序")

        await self.QueueConfig[queue_uid].QueueItem.setOrder(
            list(map(uuid.UUID, index_list))
        )

    def _ensure_cycle_safe(self, queue_uid: uuid.UUID, action: str) -> None:
        """拦住会打乱正在运行的循环的改动。

        任务的脚本列表在创建时就冻结了，循环靠下标回写状态；队列项的增删、
        排序、换脚本都会让下标对不上号。只拦这些，改名、改完成后操作、改循环
        周期都不受影响。
        """

        if queue_uid not in self.running_cycle_queue_ids:
            return

        queue_name = (
            self.QueueConfig[queue_uid].get("Info", "Name")
            if queue_uid in self.QueueConfig
            else str(queue_uid)
        )
        raise RuntimeError(f"循环队列 {queue_name} 正在运行，无法{action}")

    async def get_tools(self) -> Dict[str, Any]:
        """获取工具设置"""

        logger.debug("获取工具设置")

        today = datetime.now(tz=UTC8).strftime("%Y-%m-%d")
        if self._game_sign_result_date != today:
            self.ToolsConfig._game_sign_result_data = {}
            self._game_sign_result_date = today

        return await self.ToolsConfig.toDict()

    async def update_community_results(
        self, formatted: dict[str, Any], *, replace: bool = False
    ) -> None:
        """合并、持久化并广播游戏社区结果。

        Args:
            formatted: 已按平台和账号分组的签到结果。
            replace: 是否按账号 UID 替换已有结果。
        """

        from app.tools.community_sign_provider import merge_community_sign_results

        today = datetime.now(tz=UTC8).strftime("%Y-%m-%d")
        existing = (
            self.ToolsConfig._game_sign_result_data
            if self._game_sign_result_date == today
            else {}
        )
        result = merge_community_sign_results(
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

        await self.ToolsConfig.update(data)

        logger.success("工具设置更新成功")

    # ==================== 游戏社区账号组 CRUD ====================

    async def get_game_sign_accounts(
        self, *, if_decrypt: bool = True
    ) -> Dict[str, Any]:
        """获取所有游戏社区账号组"""

        logger.debug("获取所有游戏社区账号组")

        return await self.ToolsConfig.GameSign_Accounts.toDict(if_decrypt=if_decrypt)

    async def add_game_sign_account(self) -> tuple[uuid.UUID, Any]:
        """添加游戏社区账号组"""

        logger.info("添加游戏社区账号组")

        async with self._community_account_add_lock:
            existing_names = []
            for account in self.ToolsConfig.GameSign_Accounts.values():
                try:
                    existing_names.append(account.get("GameSignAccount", "Name"))
                except (AttributeError, KeyError):
                    continue
            account_name = next_community_account_name(existing_names)
            uid, config = await self.ToolsConfig.GameSign_Accounts.add(
                GameSignAccountGroup
            )
            await config.set("GameSignAccount", "Name", account_name)
            return uid, config

    def _clear_game_sign_account_results(self, account_id: str) -> None:
        """清除指定游戏社区账号的结果。"""

        today = datetime.now(tz=UTC8).strftime("%Y-%m-%d")
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
                    and account.get(group, name) != value
                ):
                    credential_changed = True
                await account.set(group, name, value)

        if credential_changed:
            await account.set("GameSignAccount", "LastSignDate", "2000-01-01")
            self._clear_game_sign_account_results(account_id)

    async def delete_game_sign_account(self, account_id: str) -> None:
        """删除游戏社区账号组"""

        logger.info(f"删除游戏社区账号组: {account_id}")

        account_uid = uuid.UUID(account_id)
        await self.ToolsConfig.GameSign_Accounts.remove(account_uid)
        self._clear_game_sign_account_results(account_id)

    async def reorder_game_sign_accounts(self, order: list[str]) -> None:
        """调整游戏社区账号组顺序"""

        logger.info("调整游戏社区账号组顺序")

        await self.ToolsConfig.GameSign_Accounts.setOrder([uuid.UUID(_) for _ in order])

    async def get_setting(self) -> Dict[str, Any]:
        """获取全局设置"""

        logger.info("获取全局设置")

        return await self.toDict()

    async def update_setting(self, data: Dict[str, Dict[str, Any]]) -> None:
        """更新全局设置"""

        logger.info("更新全局设置")

        await self.update(data)

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
        refresh: bool = False,
        server: str = "Official",
    ):
        """获取关卡信息"""

        stage_by_server = await self.get_stage(refresh=refresh)
        server = "Official" if server == "Bilibili" else server
        stage_data = stage_by_server.get(server, {})

        if type == "Info":
            today = datetime.now(tz=UTC4).isoweekday()
            res_stage_info = []
            for stage in RESOURCE_STAGE_INFO:
                if (
                    today in stage["days"]
                    and stage["value"] in RESOURCE_STAGE_DROP_INFO
                ):
                    res_stage_info.append(RESOURCE_STAGE_DROP_INFO[stage["value"]])
            stage_options = [dict(item) for item in stage_data.get("ALL", [])]
            for combox in stage_options:
                combox["label"] = RESOURCE_STAGE_DATE_TEXT.get(
                    combox["value"], combox["label"]
                )
            return {
                "Activity": stage_data.get("Info", []),
                "Resource": res_stage_info,
                "Options": stage_options,
            }
        elif type == "User":
            data = stage_data.get("ALL", [])
            for combox in data:
                combox["label"] = RESOURCE_STAGE_DATE_TEXT.get(
                    combox["value"], combox["label"]
                )
            return data
        elif type == "Today":
            return stage_data.get(datetime.now(tz=UTC4).strftime("%A"), [])
        else:
            return stage_data.get(type, [])

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

    async def get_stage(self, refresh: bool = False) -> Dict[str, Any]:
        """更新活动关卡信息；需要最新数据时等待刷新，否则立即返回缓存。"""

        raw_stage_data = json.loads(self.get("Data", "StageData"))
        has_server_data = isinstance(raw_stage_data.get("Official"), dict) and (
            "sideStoryStage" in raw_stage_data["Official"]
        )
        refresh = refresh or not has_server_data
        if not refresh and datetime.now() - timedelta(hours=1) < datetime.strptime(
            self.get("Data", "LastStageUpdated"), "%Y-%m-%d %H:%M:%S"
        ):
            logger.info("一小时内已进行过一次检查, 直接使用缓存的活动关卡信息")
            return json.loads(self.get("Data", "Stage"))

        if self._stage_refresh_task is None:
            task = asyncio.create_task(self._refresh_stage())
            self._stage_refresh_task = task
            self.temp_task.append(task)

            def _done(t: asyncio.Task) -> None:
                if self._stage_refresh_task is t:
                    self._stage_refresh_task = None
                if t in self.temp_task:
                    self.temp_task.remove(t)

            task.add_done_callback(_done)
        else:
            logger.info("活动关卡信息更新任务已在进行中")

        refresh_task = self._stage_refresh_task
        if refresh and refresh_task is not None:
            await asyncio.shield(refresh_task)

        return json.loads(self.get("Data", "Stage"))

    async def _refresh_stage(self) -> None:
        """从远端刷新活动关卡信息（仅后台调用）。"""

        logger.info("开始获取活动关卡信息")
        try:
            raw_stage_data = json.loads(self.get("Data", "StageData"))
            has_server_data = isinstance(raw_stage_data.get("Official"), dict) and (
                "sideStoryStage" in raw_stage_data["Official"]
            )
            headers = (
                {"If-None-Match": self.get("Data", "StageETag")}
                if has_server_data
                else {}
            )
            async with httpx.AsyncClient(
                proxy=self.proxy, follow_redirects=True
            ) as client:
                response = await client.get(
                    "https://api.maa.plus/MaaAssistantArknights/api/gui/StageActivityV2.json",
                    headers=headers,
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
                        json.dumps(response.json(), ensure_ascii=False),
                    )
                else:
                    logger.warning(f"无法从MAA服务器获取活动关卡信息:{response.text}")
        except Exception as e:
            logger.warning(f"无法从MAA服务器获取活动关卡信息: {e}")

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
                data.append({"label": plan.get("Info", "Name"), "value": str(uid)})
        logger.success(f"{consumer} 计划下拉框信息获取成功")

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

        if emulator_id == "-":
            return []

        if self.EmulatorConfig[uuid.UUID(emulator_id)].get("Info", "Type") == "general":
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

    def build_history_log_path(
        self, *, script_name: str, user_name: str, log_time: datetime
    ) -> Path:
        """构建带脚本名称前缀的历史日志路径。

        Args:
            script_name: 脚本名称。
            user_name: 用户名称。
            log_time: 日志开始时间。

        Returns:
            历史日志文件路径。
        """

        safe_script_name = re.sub(r'[<>:"/\\|?*]', "_", str(script_name or "").strip())
        safe_script_name = safe_script_name.rstrip(" .") or "空白"
        time_suffix = f"-{log_time.strftime('%H-%M-%S')}.log"
        safe_script_name = safe_script_name[: 255 - len(time_suffix)]

        return (
            self.history_path
            / log_time.strftime("%Y-%m-%d")
            / user_name
            / f"{safe_script_name}{time_suffix}"
        )

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

        # 掉落统计收集所有由理智任务产生的有效 Fight 任务链，包括活动关优先、
        # 库存保持和剩余理智任务。
        data["drop_statistics"] = _parse_maa_drop_statistics(logs)

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
                pending_statistics[current_matrix_skill] = weapon_match.group(1).strip()
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
                matched_items = list(pending_statistics.items())[-current_locked_count:]
                matrix_statistics.update(matched_items)

            pending_statistics = {}
            current_matrix_skill = ""

        if not has_matrix_flow:
            return None, False

        if locked_count == 0:
            return {}, True

        return (matrix_statistics or None), True

    def parse_maaend_pull_count_statistics(
        self, logs: list[str]
    ) -> Optional[Dict[str, int]]:
        """解析 MaaEnd 抽数计算任务输出的统计结果。"""

        content = "".join(logs)
        field_patterns = {
            "resource_pulls": (
                r'"ResourcePulls"\s*:\s*(\d+)',
                r"资源折算[：:]\s*(\d+)\s*抽",
            ),
            "carry_over_pulls": (
                r'"CarryToNextPulls"\s*:\s*(\d+)',
                r"可留到下版本的券[：:]\s*(\d+)\s*抽",
            ),
            "next_pool_shop_pulls": (
                r'"NextPoolShopPulls"\s*:\s*(\d+)',
                r"下版本商店[：:]\s*(\d+)\s*抽",
            ),
            "next_pool_signin_pulls": (
                r'"NextPoolSigninPulls"\s*:\s*(\d+)',
                r"下版本签到[：:]\s*(\d+)\s*抽",
            ),
            "current_pool_total": (
                r'"CurrentPoolTotal"\s*:\s*(\d+)',
                r"当前池可用[：:]\s*(\d+)\s*抽",
            ),
            "next_pool_total": (
                r'"NextPoolTotal"\s*:\s*(\d+)',
                r"下版本池子总计[：:]\s*(\d+)\s*抽",
            ),
        }

        statistics: Dict[str, int] = {}
        for field, patterns in field_patterns.items():
            matches = [
                match for pattern in patterns for match in re.finditer(pattern, content)
            ]
            if matches:
                statistics[field] = int(matches[-1].group(1))

        return statistics if len(statistics) == len(field_patterns) else None

    async def save_maaend_log(
        self, log_path: Path, logs: list[str], maaend_result: str, phase_label: str = ""
    ) -> None:
        """
        Save MaaEnd logs and generate basic statistics data.

        Args:
            log_path (Path): Target log file path.
            logs (list[str]): Log lines.
            maaend_result (str): Result label for this run.
            phase_label (str): 运行阶段标签（送货/日常/自动采集），作为历史结果前缀。
        """

        logger.info(
            f"开始处理MaaEnd日志, 日志长度: {len(logs)}, 日志标记: {maaend_result}"
        )

        failed_tasks = self.parse_maaend_failed_tasks(logs)
        matrix_statistics, has_matrix_flow = self.parse_maaend_matrix_statistics(logs)
        pull_count_statistics = self.parse_maaend_pull_count_statistics(logs)

        if maaend_result == "MaaEnd 部分任务执行失败" and failed_tasks:
            maaend_result = f"{maaend_result}: {'、'.join(failed_tasks)}"

        if phase_label:
            maaend_result = f"[{phase_label}] {maaend_result}"

        data: Dict[str, Any] = {"maaend_result": maaend_result}
        if has_matrix_flow and matrix_statistics is not None:
            data["matrix_statistics"] = matrix_statistics
        if pull_count_statistics is not None:
            data["pull_count_statistics"] = pull_count_statistics

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

    async def save_hsr_log(self, log_path: Path, logs: list, hsr_result: str) -> None:
        """
        保存 HSR 专项日志并生成对应统计数据

        :param log_path: 日志文件保存路径
        :param logs: 日志内容列表
        :param hsr_result: 待保存的日志结果信息
        """

        logger.info(
            f"开始处理 HSR 专项日志, 日志长度: {len(logs)}, 日志标记: {hsr_result}"
        )

        data: Dict[str, str] = {"hsr_result": hsr_result}

        # 保存日志
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.with_suffix(".log").write_text("".join(logs), encoding="utf-8")
        log_path.with_suffix(".json").write_text(
            json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8"
        )

        logger.success(
            f"HSR 专项日志统计完成, 日志路径: {log_path.with_suffix('.log')}"
        )

    async def merge_statistic_info(self, statistic_path_list: List[Path]) -> dict:
        """
        合并指定数据统计信息文件

        Args:
            statistic_path_list (List[Path]): 数据统计信息文件列表

        Returns:
            dict: 合并后的数据统计信息
        """

        data: Dict[str, Any] = {"index": {}}
        hsr_success_results = {
            "HSR 任务结束",
            "HSR 用户任务完成",
            "HSR 失败任务补跑完成",
            "HSR 本轮无需执行，已跳过",
            "HSR 脚本直控完成",
        }

        def is_success_result(result_key: str, result_value: Any) -> bool:
            # 结果文本可能带运行阶段前缀（如 "[送货] Success!"），比对前先剥离
            if not isinstance(result_value, str):
                return False
            value = re.sub(r"^\[[^\]]+\]\s*", "", result_value)
            if value == "Success!":
                return True
            if result_key == "hsr_result" and result_value in hsr_success_results:
                return True
            return False

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

                # 抽数是当前资源快照，合并时使用最新一条记录
                elif key == "pull_count_statistics":
                    data[key] = single_data[key]

                # 处理理智相关字段 - 使用最后一个文件的值
                elif key in ["sanity", "sanity_full_at"]:
                    data[key] = single_data[key]

                # 录入运行结果
                elif key in [
                    "maa_result",
                    "maaend_result",
                    "src_result",
                    "general_result",
                    "hsr_result",
                ]:
                    history_time = "-".join(json_file.stem.rsplit("-", 3)[-3:])
                    actual_date = (
                        datetime.strptime(
                            f"{json_file.parent.parent.name} {history_time}",
                            "%Y-%m-%d %H-%M-%S",
                        )
                        .replace(tzinfo=UTC4)
                        .astimezone()
                    )

                    success = is_success_result(key, single_data[key])

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
                        "result": single_data[key],
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

    async def clean_maafw_agent_venvs(self) -> None:
        """清掉已无脚本引用的 MFW agent 隔离 venv。

        这些 venv 每个几十到上百 MB，此前没有任何回收——只有「同一项目依赖变了
        就重建」那一条。用户删脚本、改项目路径、或项目升级换了目录，旧 venv 都会
        永远留着。

        放在启动清理里而不是运行前：判定依赖「当前全部脚本配置」这个全局状态，
        只有真实启动时它才可信。挂在 check() 上曾把测试替身当成真配置，
        把开发者磁盘上的真 venv 删掉了。

        判定不读目录内的清单：目录名就是项目路径的哈希，凡不属于任何存活脚本的
        即孤儿；再加一道保护——刚动过的一律不碰，避免与正在准备环境的运行抢。
        """

        from app.models.config import MaaFWConfig
        from app.task.MaaFW.tools.core.automas_maafw_agent_env.planner import (
            collect_orphan_agent_venvs,
        )

        root = Path.cwd() / "config" / "maafw_agent_venvs"
        if not root.is_dir():
            return

        live_paths = [
            path
            for config in self.ScriptConfig.values()
            if isinstance(config, MaaFWConfig)
            and (path := str(config.get("Info", "Path") or "").strip())
        ]

        # 目录名是 Path.resolve() 之后的路径哈希，而 resolve() 只在路径**当下
        # 存在**时才展开映射盘 / junction / 符号链接；不存在时原样返回。建 venv
        # 时项目必然在，算的是展开后的真实路径；开机自启动早于网络盘挂载时，
        # 这里却只能算出字面路径——名字对不上，存活 venv 就会被当成孤儿删掉。
        # 分不清的时候不删：只要有一个存活项目此刻不可达，整轮弃权。
        unreachable = [path for path in live_paths if not Path(path).exists()]
        if unreachable:
            logger.info(
                "MFW 隔离 venv 清理已跳过：以下项目路径当前不可达，"
                f"无法可靠判定归属: {unreachable[:3]}"
            )
            return

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
                shutil.rmtree(venv_path)
            except OSError as exc:
                logger.warning(f"MFW 隔离 venv 清理失败: {venv_path} - {exc}")
                continue
            logger.info(f"已清理无人引用的 MFW 隔离 venv: {venv_path}")

    async def clean_debug_diagnostics(self) -> None:
        """清理 debug 目录下过期的失败诊断文件。

        终末地登录失败截图与 OK-WW / OK-NTE 切号诊断只会随失败新增，
        此前没有任何回收；保留时长沿用历史记录的保留天数设置。
        """

        if self.get("Function", "HistoryRetentionTime") == 0:
            logger.info("诊断文件永久保留, 跳过诊断文件清理")
            return

        cutoff = time.time() - self.get("Function", "HistoryRetentionTime") * 86400
        deleted_count = 0
        for name in ("maaend-login", "okww-account-switch", "oknte-account-switch"):
            folder = Path.cwd() / "debug" / name
            if not folder.is_dir():
                continue
            for file in folder.iterdir():
                if not file.is_file():
                    continue
                try:
                    if file.stat().st_mtime >= cutoff:
                        continue
                    file.unlink()
                except OSError as exc:
                    logger.warning(f"诊断文件清理失败: {file} - {exc}")
                    continue
                deleted_count += 1
        if deleted_count:
            logger.success(f"清理完成: {deleted_count} 个过期诊断文件")

    async def clean_maafw_native_debug_logs(self) -> None:
        """清掉 MFW 项目里过期的 MaaFramework 原生日志备份。

        MaaFramework 把 ``debug/maafw.log`` 写到一定大小就整体挪成
        ``debug/maafw.bak.<时间戳>.log`` 再开新的，但从不回收旧的——一个每天跑
        的项目几天就能堆出几百 MB。每次运行的完整内容已经另存进历史记录的
        ``*.maafw.log``，所以这里只删备份，正在写的 ``maafw.log`` 不动。
        保留时长沿用历史记录的保留天数设置。
        """

        if self.get("Function", "HistoryRetentionTime") == 0:
            logger.info("原生日志永久保留, 跳过 MFW 原生日志备份清理")
            return

        from app.models.config import MaaFWConfig

        cutoff = time.time() - self.get("Function", "HistoryRetentionTime") * 86400
        deleted_count = 0
        for script_config in self.ScriptConfig.values():
            if not isinstance(script_config, MaaFWConfig):
                continue
            project_path = str(script_config.get("Info", "Path") or "").strip()
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
