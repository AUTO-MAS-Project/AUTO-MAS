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
from jinja2 import Environment, FileSystemLoader

from app.models.config import (
    CLASS_BOOK,
    PLAN_BOOK,
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
)
from app.models.schema import PlanComboxConsumer
from app.utils import get_logger
from app.utils.constants import (
    MAA_DEPOT_EXCLUDED_ITEM_IDS,
    RESOURCE_STAGE_DATE_TEXT,
    RESOURCE_STAGE_DROP_INFO,
    RESOURCE_STAGE_INFO,
    TYPE_BOOK,
    UTC4,
    UTC8,
)
from app.utils.io import write_file
from app.utils.platform import IS_WINDOWS

# 孤儿 venv 的宽限期：刚动过的一律不碰，避免与正在准备环境的运行抢。
MAAFW_AGENT_VENV_GRACE_SECONDS = 60 * 60

logger = get_logger("配置管理")

GAME_SIGN_RESULT_FILENAME = "GameSignResult.json"


def _load_game_sign_result_snapshot(path: Path, *, result_date: str) -> dict[str, Any]:
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
    """原子保存游戏签到结果快照（走 ``app.utils.io.write_file``）。"""

    if path is None:
        return

    try:
        write_file(path, {"date": result_date, "result": result})
    except (OSError, TypeError, ValueError) as e:
        logger.warning(f"保存游戏签到结果快照失败: {e}")


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
    VERSION = "v5.5.0-beta.3"

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
        self.temp_task: List[asyncio.Task] = []
        # 正在循环运行的队列，供配置改动前的安全检查使用
        self.running_cycle_queue_ids: set[uuid.UUID] = set()
        self._stage_refresh_task: Optional[asyncio.Task] = None
        self._game_sign_result_date = ""

        self._inject_truststore()

        self.notify_env = Environment(
            loader=FileSystemLoader(str(Path.cwd() / "res/html"))
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

        def _cached_create_default_context(*args: object, **kwargs: object) -> ssl.SSLContext:
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

                self._repo = Repo(Path.cwd())
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

        # 游戏签到：连接账号组 MultipleConfig
        await self.ToolsConfig.GameSign_Accounts.connect(
            self.config_path / "GameSignAccounts.json"
        )

        # 游戏签到：恢复当天的结果快照，跨日结果不继续展示
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
        return is_latest, commit_hash, commit_time

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
        | BetterGIConfig,
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
        temp.pop("SubConfigsInfo", None)
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
        | BetterGIUserConfig,
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
            shutil.rmtree(target_config_dir, ignore_errors=True)
            temporary_path.rename(target_config_dir)
        finally:
            shutil.rmtree(temporary_path, ignore_errors=True)

        logger.info(f"已从 OK-WW 脚本默认配置初始化用户配置: {script_id} - {owner}")
        return target_config_dir

    async def update_user(
        self, script_id: str, user_id: str, data: Dict[str, Dict[str, Any]]
    ) -> None:
        """更新用户配置"""

        logger.info(f"{script_id} 更新用户配置: {user_id}")

        script_uid = uuid.UUID(script_id)
        user_uid = uuid.UUID(user_id)
        script_config = self.ScriptConfig[script_uid]
        user_config = script_config.UserData[user_uid]

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

    async def update_game_sign_results(
        self, formatted: dict[str, Any], *, replace: bool = False
    ) -> None:
        """合并、持久化并广播游戏签到结果。

        Args:
            formatted: 已按平台和账号分组的签到结果。
            replace: 是否按账号 UID 替换已有结果。
        """

        from app.tools.game_sign import merge_sign_results

        today = datetime.now(tz=UTC8).strftime("%Y-%m-%d")
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
            logger.warning(f"广播游戏签到结果失败: {e}")

    async def update_tools(self, data: Dict[str, Dict[str, Any]]) -> None:
        """更新工具设置"""

        logger.info("更新工具设置")

        await self.ToolsConfig.update(data)

        logger.success("工具设置更新成功")

    # ==================== 游戏签到账号组 CRUD ====================

    async def get_game_sign_accounts(
        self, *, if_decrypt: bool = True
    ) -> Dict[str, Any]:
        """获取所有游戏签到账号组"""

        logger.debug("获取所有游戏签到账号组")

        return await self.ToolsConfig.GameSign_Accounts.toDict(if_decrypt=if_decrypt)

    async def add_game_sign_account(self) -> tuple[uuid.UUID, Any]:
        """添加游戏签到账号组"""

        logger.info("添加游戏签到账号组")

        uid, config = await self.ToolsConfig.GameSign_Accounts.add(GameSignAccountGroup)
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
        """更新游戏签到账号组配置"""

        logger.info(f"更新游戏签到账号组: {account_id}")

        account_uid = uuid.UUID(account_id)
        account = self.ToolsConfig.GameSign_Accounts[account_uid]
        from app.tools.game_sign import GAME_SIGN_TOKEN_FIELDS

        credential_fields = set(GAME_SIGN_TOKEN_FIELDS)
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
        pull_count_statistics = self.parse_maaend_pull_count_statistics(logs)

        if maaend_result == "MaaEnd 部分任务执行失败" and failed_tasks:
            maaend_result = f"{maaend_result}: {'、'.join(failed_tasks)}"

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
            if result_value == "Success!":
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
