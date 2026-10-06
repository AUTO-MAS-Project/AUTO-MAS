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
import truststore
from pathlib import Path
from datetime import datetime, timedelta
from typing import Literal, Optional, Dict, Any, List
import json

from app.config import ConfigCollection
from app.models.config import (
    GameEntry,
    PlanEntry,
    PluginMeta,
    PluginRecord,
    PluginRegistryCollection,
    QueueEntry,
    ScriptEntry,
    Setting,
    Tools,
)
from app.utils.constants import (
    UTC4,
    UTC8,
    RESOURCE_STAGE_INFO,
    RESOURCE_STAGE_DROP_INFO,
    RESOURCE_STAGE_DATE_TEXT,
)
from app.utils import get_logger
from app.utils.io import read_file, write_file

logger = get_logger("配置管理")

GAME_SIGN_RESULT_FILENAME = "GameSignResult.json"


def _load_game_sign_result_snapshot(path: Path, *, result_date: str) -> dict[str, Any]:
    """读取当天的游戏签到结果快照。"""

    if not path.exists():
        return {}

    try:
        payload = read_file(path)
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

    try:
        write_file(path, {"date": result_date, "result": result})
    except (OSError, TypeError, ValueError) as e:
        logger.warning(f"保存游戏签到结果快照失败: {e}")


class AppConfig:
    """配置总入口：持有全部配置实例，负责启动期激活顺序与复杂配置更新。"""

    VERSION = "v5.4.0-beta.1"

    def __init__(self) -> None:
        logger.info("")
        logger.info("===================================")
        logger.info("AUTO-MAS 后端启动")
        logger.info(f"版本：{self.VERSION}")
        logger.info(f"工作目录：{Path.cwd()}")
        logger.info("===================================")

        self.log_path = Path.cwd() / "debug/app.log"
        self.database_path = Path.cwd() / "data/data.db"
        self.config_path = Path.cwd() / "config"
        self.plugin_path = Path.cwd() / "plugins"
        self.i18n_path = Path.cwd() / "res/i18n"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.mkdir(parents=True, exist_ok=True)

        # 配置实例（各自独立 YAML 文件根）
        self.setting = Setting.build(file=self.config_path / "setting.yaml")
        self.plugin_registry = PluginRegistryCollection.build(
            [PluginRecord],
            file=self.config_path / "plugin_registry.yaml",
            name="plugin_registry",
        )
        self.plugin_catalog = ConfigCollection[PluginMeta].build(
            [PluginMeta],
            file=self.config_path / "plugin_catalog.yaml",
            name="plugin_catalog",
        )
        self.queues = ConfigCollection[QueueEntry].build(
            [QueueEntry],
            file=self.config_path / "queues.yaml",
            name="queues",
        )
        self.tools = Tools.build(file=self.config_path / "tools.yaml")
        self.ScriptConfig = ConfigCollection[ScriptEntry].build(
            [ScriptEntry],
            file=self.config_path / "scripts.yaml",
            name="scripts",
        )
        self.PlanConfig = ConfigCollection[PlanEntry].build(
            [PlanEntry],
            file=self.config_path / "plans.yaml",
            name="plans",
        )
        self.GameConfig = ConfigCollection[GameEntry].build(
            [GameEntry],
            file=self.config_path / "games.yaml",
            name="games",
        )
        # 任务信息不在 Config 里落脚：任务是纯运行态，唯一事实源只在任务派发层的
        # 在跑任务表（TaskDispatcher._running 的 TaskItem）。此处既不建集合也不注册
        # ref 池 —— 查询走 /api/dispatch/get 直接读派发层。

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

    async def _activate(self, nodes: tuple[tuple[str, Any], ...]) -> None:
        """逐个激活配置实例；单个实例的校验失败不阻断其余实例。"""
        from app.config.errors import ConfigAggregateError

        for label, node in nodes:
            try:
                await node.activate()
            except ConfigAggregateError as exc:
                logger.warning(f"配置 {label} 激活失败：{exc}")

    async def init_bootstrap_configs(self) -> None:
        """引导阶段：数据文件检查 + 设置 / 插件注册表 / 插件目录 + i18n。

        插件系统要读注册表才能加载，所以这三个实例必须先于 ``Plugin.initialize``。
        """
        await self.check_data()
        await self._activate(
            (
                ("setting", self.setting),
                ("plugin_registry", self.plugin_registry),
                ("plugin_catalog", self.plugin_catalog),
            )
        )
        self.loop = asyncio.get_running_loop()
        from app.core.i18n import i18n

        await i18n.initialize()
        logger.info("引导配置就绪：setting / plugin_registry / plugin_catalog")

    async def init_domain_configs(self) -> None:
        """领域阶段：插件注册完类型表后再激活各业务集合。"""
        from app.core.game_manager import GameManager

        # 热化会发 init_add，实例级订阅须早于 games.activate()
        self.GameConfig.connect(GameManager.on_add, phase="both", kind="add")
        self.GameConfig.connect(GameEntry.on_add_devices, phase="both", kind="add")
        self.ScriptConfig.connect(ScriptEntry.on_add_script, phase="both", kind="add")
        # 去广告开关是系统级的，落点在各品牌；主入口统一扇出，不等下次启动
        self.setting.connect(
            GameManager.on_block_ad,
            phase="runtime",
            group="function",
            field="if_block_ad",
        )
        # games 须先于 scripts：脚本 game_id 外键与设备归一热化时要查游戏及其 devices
        await self._activate(
            (
                ("queues", self.queues),
                ("tools", self.tools),
                ("games", self.GameConfig),
                ("scripts", self.ScriptConfig),
                ("plans", self.PlanConfig),
            )
        )

        # 签到结果快照按天有效；跨天则丢弃并清掉今日计划时刻
        today = datetime.now(tz=UTC8).date()
        self.tools.game_sign_result_data.update(
            _load_game_sign_result_snapshot(
                self.config_path / GAME_SIGN_RESULT_FILENAME,
                result_date=today.isoformat(),
            )
        )
        self._game_sign_result_date = today.isoformat()
        if self.tools.game_sign.last_sign_date != today:
            self.tools.game_sign.scheduled_time = ""
            await self.tools.commit()

        logger.info("领域配置就绪：queues / tools / scripts / plans / games")

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

                # Script/Plan/Queue 已迁 ConfigCollection；旧 MultipleConfig.connect /
                # add_script / add_plan / add_queue 路径已移除，跳过内容迁移。
                logger.warning(
                    "跳过 v1.8→v1.9 MultipleConfig 内容迁移（ConfigCollection cutover）"
                )

                if (Path.cwd() / "config/config.json").exists():
                    (Path.cwd() / "config/config.json").rename(
                        Path.cwd() / "config/Config.json"
                    )

                for stale in (
                    "config/QueueConfig",
                    "config/MaaPlanConfig",
                    "config/MaaConfig",
                    "config/GeneralConfig",
                    "data/key",
                ):
                    p = Path.cwd() / stale
                    if p.exists():
                        shutil.rmtree(p)
                gameid = Path.cwd() / "data/gameid.txt"
                if gameid.exists():
                    gameid.unlink()

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
        stored = self.tools.game_sign_result_data
        existing = dict(stored) if self._game_sign_result_date == today else {}
        result = merge_sign_results(existing, formatted, replace=replace)
        stored.clear()
        stored.update(result)
        self._game_sign_result_date = today
        _save_game_sign_result_snapshot(
            self.config_path / GAME_SIGN_RESULT_FILENAME,
            result,
            result_date=today,
        )

        try:
            from app.core.ws import Publisher

            await Publisher.send(
                id="GameSign",
                type="Update",
                data={"Result": json.dumps(result, ensure_ascii=False)},
            )
        except Exception as e:
            logger.warning(f"广播游戏签到结果失败: {e}")

    def _clear_game_sign_account_results(self, account_id: str) -> None:
        """清除指定游戏签到账号的当天结果。"""

        today = datetime.now(tz=UTC8).strftime("%Y-%m-%d")
        result = self.tools.game_sign_result_data
        if self._game_sign_result_date != today:
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

        _save_game_sign_result_snapshot(
            self.config_path / GAME_SIGN_RESULT_FILENAME,
            result,
            result_date=today,
        )

    @property
    def proxy(self) -> Optional[httpx.Proxy]:
        """获取代理设置，返回适用于 httpx 的代理对象"""
        proxy_addr = self.setting.updates.proxy_address
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

        stage = json.loads(self.setting.data.stage or "{ }")
        if type == "Info":
            today = datetime.now(tz=UTC4).isoweekday()
            res_stage_info = []
            for stage_item in RESOURCE_STAGE_INFO:
                if (
                    today in stage_item["days"]
                    and stage_item["value"] in RESOURCE_STAGE_DROP_INFO
                ):
                    res_stage_info.append(RESOURCE_STAGE_DROP_INFO[stage_item["value"]])
            return {"Activity": stage.get("Info", []), "Resource": res_stage_info}
        if type == "User":
            data = stage.get("ALL", [])
            for combox in data:
                combox["label"] = RESOURCE_STAGE_DATE_TEXT.get(
                    combox["value"], combox["label"]
                )
            return data
        if type == "Today":
            return stage.get(datetime.now(tz=UTC4).strftime("%A"), [])
        return stage.get(type, [])

    async def get_stage(self) -> Optional[Dict[str, List[Dict[str, str]]]]:
        """更新活动关卡信息。网络检查在后台执行，立即返回本地缓存。"""

        if datetime.now(tz=UTC8) - timedelta(hours=1) < self.setting.data.last_stage_updated:
            logger.info("一小时内已进行过一次检查, 直接使用缓存的活动关卡信息")
            return json.loads(self.setting.data.stage or "{ }")

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

        return json.loads(self.setting.data.stage or "{ }")

    async def _refresh_stage(self) -> None:
        """从远端刷新活动关卡信息（仅后台调用）。"""

        logger.info("开始获取活动关卡信息")
        data = self.setting.data
        try:
            async with httpx.AsyncClient(
                proxy=self.proxy, follow_redirects=True
            ) as client:
                response = await client.get(
                    "https://api.maa.plus/MaaAssistantArknights/api/gui/StageActivityV2.json",
                    headers={"If-None-Match": data.stage_etag},
                )

                if response.status_code == 304:
                    logger.info("关卡信息未更新，使用本地缓存的活动关卡信息")
                    data.last_stage_updated = datetime.now(tz=UTC8)
                elif response.status_code == 200:
                    logger.success("成功获取远端活动关卡信息")
                    data.last_stage_updated = datetime.now(tz=UTC8)
                    data.stage_etag = (
                        response.headers.get("ETag")
                        or response.headers.get("etag")
                        or ""
                    )
                    data.stage_data = json.dumps(
                        response.json().get("Official", {}).get("sideStoryStage", {}),
                        ensure_ascii=False,
                    )
                else:
                    logger.warning(f"无法从MAA服务器获取活动关卡信息:{response.text}")
                await self.setting.commit()
        except Exception as e:
            logger.warning(f"无法从MAA服务器获取活动关卡信息: {e}")

    async def get_notice(self) -> tuple[bool, Dict[str, str]]:
        """获取公告信息"""

        data = self.setting.data
        if datetime.now(tz=UTC8) - timedelta(hours=1) < data.last_notice_updated:
            logger.info("一小时内已进行过一次检查, 直接使用缓存的公告信息")
            return False, json.loads(data.notice).get("notice_dict", {})

        logger.info("开始从 AUTO-MAS 服务器获取公告信息")
        try:
            async with httpx.AsyncClient(
                proxy=self.proxy, follow_redirects=True
            ) as client:
                response = await client.get(
                    "https://api.auto-mas.top/file/Server/notice.json",
                    headers={"If-None-Match": data.notice_etag},
                )
                if response.status_code == 304:
                    logger.info("公告未更新，使用本地缓存的公告信息")
                    data.last_notice_updated = datetime.now(tz=UTC8)
                elif response.status_code == 200:
                    logger.info("公告已更新，要求展示公告信息")
                    data.last_notice_updated = datetime.now(tz=UTC8)
                    data.notice_etag = (
                        response.headers.get("ETag")
                        or response.headers.get("etag")
                        or ""
                    )
                    data.if_show_notice = True
                    data.notice = json.dumps(response.json(), ensure_ascii=False)
                else:
                    logger.warning(
                        f"无法从 AUTO-MAS 服务器获取公告信息:{response.text}"
                    )
                await self.setting.commit()
        except Exception as e:
            logger.warning(f"无法从 AUTO-MAS 服务器获取公告信息: {e}")

        return data.if_show_notice, json.loads(data.notice).get("notice_dict", {})

    async def get_web_config(self) -> list[Any]:
        """获取「AUTO-MAS 配置分享中心」配置"""

        data = self.setting.data
        local_web_config = json.loads(data.web_config)
        if datetime.now(tz=UTC8) - timedelta(hours=1) < data.last_web_config_updated:
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

        data.last_web_config_updated = datetime.now(tz=UTC8)
        data.web_config = json.dumps(remote_web_config, ensure_ascii=False)
        await self.setting.commit()

        return remote_web_config


Config = AppConfig()
