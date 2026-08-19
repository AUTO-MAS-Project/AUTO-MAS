#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

import asyncio
import uuid
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path

from app.core import Config
from app.models.task import TaskExecuteBase, ScriptItem, UserItem, LogRecord
from app.models.ConfigBase import MultipleConfig
from app.models.config import BetterGIConfig, BetterGIUserConfig
from app.services import Notify, System
from app.utils import get_logger, ProcessManager, ProcessInfo
from app.utils.LogMonitor import LogMonitor
from app.utils.constants import UTC4
from app.task.general.tools import execute_script_task

from .tools import push_notification

logger = get_logger("BetterGI 自动代理")

# BetterGI 项目结构固定相对路径（从 RootPath 派生，不依赖用户存储值）
# ⚠️ 与前端 BetterGIScriptEdit.vue 的 BGI_EXE_NAME 保持同步，改这里时需同步改前端
_BGI_REL_EXE = "BetterGenshinImpact.exe"
_BGI_REL_LOG_FILE = "log/better-genshin-impact.log"
_BGI_TRACK_PROCESS_NAME = "BetterGenshinImpact.exe"

# ── BetterGI 专项硬编码（不存 ConfigItem，随 MAS 版本同步）──────────────
# BetterGI 使用 Serilog 文件日志，行格式：
#   [{HH:mm:ss.fff}] [{Level:u3}] [{BgiInstance}] {SourceContext}\n{Message}
# 成功/失败判定取自 TaskRunner 的统一日志片段，BetterGI 不向用户暴露关键词配置。
_BGI_BUILTIN_FATAL: tuple[tuple[str, str], ...] = (
    ("[FTL]", "BetterGI 出现致命错误"),
    ("任务启动失败", "BetterGI 任务启动失败"),
    ("任务执行异常", "BetterGI 任务执行异常"),
    ("[ERR]", "BetterGI 任务执行异常"),
)
_BGI_SUCCESS_LOG = "任务结束"
_BGI_LOG_TIME_START = 1
_BGI_LOG_TIME_END = 13
_BGI_LOG_TIME_FORMAT = "%H:%M:%S.%f"


class AutoProxyTask(TaskExecuteBase):
    """BetterGI 自动代理：拼 `startOneDragon <configName>` 启动并监控日志"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: BetterGIConfig,
        user_config: MultipleConfig[BetterGIUserConfig],
    ):
        super().__init__()
        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config

        self.cur_user_item: UserItem = self.script_info.user_list[
            self.script_info.current_index
        ]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config: BetterGIUserConfig = self.user_config[self.cur_user_uid]
        self.cur_user_log: LogRecord | None = None
        self.bettergi_process_manager: ProcessManager | None = None
        self.wait_event: asyncio.Event | None = None
        self.script_root_path: Path | None = None
        self.script_exe_path: Path | None = None
        self.script_target_process_info: ProcessInfo | None = None
        self.script_log_path: Path | None = None
        self.log_monitor: LogMonitor | None = None

    async def check(self) -> str:
        root = Path(self.script_config.get("Info", "RootPath"))
        if not root.is_dir():
            return "请设置 BetterGI 脚本路径"
        if not (root / _BGI_REL_EXE).is_file():
            return "请设置 BetterGI 脚本路径"

        one_dragon_config = str(
            self.cur_user_config.get("Task", "OneDragonConfigName") or ""
        ).strip()
        if not one_dragon_config:
            self.cur_user_item.status = "异常"
            return "请先设置该用户的一条龙配置名"

        if (
            self.script_config.get("Run", "ProxyTimesLimit") != 0
            and self.cur_user_config.get("Data", "ProxyTimes")
            >= self.script_config.get("Run", "ProxyTimesLimit")
        ):
            self.cur_user_item.status = "跳过"
            return "今日代理次数已达上限, 跳过该用户"
        if self.cur_user_config.get("Info", "RemainedDay") == 0:
            self.cur_user_item.status = "跳过"
            return "用户剩余天数为 0, 跳过该用户"

        return "Pass"

    async def prepare(self):
        self.bettergi_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()

        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now()

        # ── 所有 Script 路径从 RootPath 实时派生，不依赖 ConfigItem 存储值 ──
        self.script_root_path = Path(self.script_config.get("Info", "RootPath"))
        self.script_exe_path = self.script_root_path / _BGI_REL_EXE

        self.script_target_process_info = ProcessInfo(
            name=_BGI_TRACK_PROCESS_NAME,
            exe=str(self.script_exe_path),
            cmdline=None,
        )

        self.script_log_path = self.script_root_path / _BGI_REL_LOG_FILE

        self.log_time_range = (_BGI_LOG_TIME_START, _BGI_LOG_TIME_END)
        self.log_time_format = _BGI_LOG_TIME_FORMAT
        self.log_monitor = LogMonitor(
            self.log_time_range,
            self.log_time_format,
            self.check_log,
        )

        self.one_dragon_config = str(
            self.cur_user_config.get("Task", "OneDragonConfigName") or ""
        ).strip()
        self.bettergi_args = ["startOneDragon", self.one_dragon_config]

        self.run_book = False

    async def _push_dispatch_log(self, line: str) -> None:
        """向调度台追加流程日志（赋值 script_info.log 会触发 WebSocket 推送）。"""

        prev = self.script_info.log
        self.script_info.log = f"{prev}\n{line}" if prev else line
        await asyncio.sleep(0)

    async def main_task(self):
        await self.prepare()
        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        if self.cur_user_config.get("Data", "LastProxyDate") != self.curdate:
            await self.cur_user_config.set("Data", "LastProxyDate", self.curdate)
            await self.cur_user_config.set("Data", "ProxyTimes", 0)

        self.cur_user_item.status = "运行"

        run_limit = int(self.script_config.get("Run", "RunTimesLimit"))
        for i in range(run_limit):
            if self.run_book:
                break
            logger.info(
                f"用户 {self.cur_user_item.name} - 尝试次数: {i + 1}/{run_limit}"
            )
            self.cur_user_item.status = "运行"
            self.log_start_time = datetime.now()
            self.cur_user_item.log_record[self.log_start_time] = LogRecord()
            self.cur_user_log = self.cur_user_item.log_record[self.log_start_time]
            self.script_info.log = ""

            if self.cur_user_config.get("Info", "IfScriptBeforeTask"):
                await execute_script_task(
                    Path(self.cur_user_config.get("Info", "ScriptBeforeTask")),
                    "脚本前任务",
                )

            await self._push_dispatch_log(
                f"启动 BetterGI: startOneDragon {self.one_dragon_config}"
            )
            logger.info(
                f"启动 BetterGI 进程: {self.script_exe_path} "
                f"{' '.join(self.bettergi_args)}"
            )

            await self.bettergi_process_manager.open_process(
                self.script_exe_path,
                *self.bettergi_args,
                target_process=self.script_target_process_info,
            )

            # 启动日志监控（文件日志）
            await asyncio.sleep(1)
            await self.log_monitor.start_monitor_file(
                self.script_log_path, self.log_start_time
            )

            self.wait_event.clear()
            await self.wait_event.wait()
            await self.log_monitor.stop()

            if self.cur_user_log.status == "Success!":
                self.run_book = True
                self.script_info.log = (
                    "检测到 BetterGI 已完成任务\n正在等待 BetterGI 自行退出"
                )
                if self.cur_user_config.get("Info", "IfScriptAfterTask"):
                    await execute_script_task(
                        Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
                        "脚本后任务",
                    )
                await asyncio.sleep(3)
                break

            logger.warning(
                f"用户 {self.cur_user_item.name} - BetterGI 代理异常: "
                f"{self.cur_user_log.status}"
            )
            self.script_info.log = (
                f"{self.cur_user_log.status}\n正在中止相关程序"
            )
            await self.kill_managed_process()
            try:
                await Notify.push_plyer(
                    "BetterGI 自动代理出现异常！",
                    f"用户 {self.cur_user_item.name} 的自动代理出现一次异常",
                    f"{self.cur_user_item.name}的自动代理出现异常",
                    3,
                )
            except Exception:
                pass
            if self.cur_user_config.get("Info", "IfScriptAfterTask"):
                await execute_script_task(
                    Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
                    "脚本后任务",
                )
            if i + 1 < run_limit:
                self.script_info.log += (
                    f"\n将在稍后重试 ({i + 1}/{run_limit})"
                )
                await asyncio.sleep(10)

    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """按内置日志判定结果，未见成功日志便退出则视为异常。"""
        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log[-4000:] if len(log) > 4000 else log

        log_status = "BetterGI 正常运行中"
        user_item_status: str | None = None

        for needle, msg in _BGI_BUILTIN_FATAL:
            if needle in log:
                log_status = msg
                user_item_status = "异常"
                break
        else:
            if _BGI_SUCCESS_LOG in log:
                log_status = "Success!"
                user_item_status = "完成"
            elif not await self.bettergi_process_manager.is_running():
                log_status = "BetterGI 在完成任务前退出"
                user_item_status = "异常"
            elif datetime.now() - latest_time > timedelta(
                minutes=self.script_config.get("Run", "RunTimeLimit")
            ):
                log_status = "BetterGI 运行超时"
                user_item_status = "异常"

        self.cur_user_log.status = log_status
        if user_item_status is not None:
            self.cur_user_item.status = user_item_status

        logger.debug(f"BetterGI 日志分析结果: {self.cur_user_log.status}")
        if self.cur_user_log.status != "BetterGI 正常运行中":
            logger.info(f"BetterGI 任务结果: {self.cur_user_log.status}, 日志锁已释放")
            self.wait_event.set()

    async def final_task(self):
        # 结束时先清理进程与监控
        if self.log_monitor is not None:
            with suppress(Exception):
                await self.log_monitor.stop()
        await self.kill_managed_process()

        # 写入历史记录（对齐 General/SRC/MaaEnd/Okww 行为）
        statistic_paths: list[Path] = []
        for t, log_item in self.cur_user_item.log_record.items():
            dt = t.replace(tzinfo=datetime.now().astimezone().tzinfo).astimezone(UTC4)
            log_path = Config.build_history_log_path(
                script_name=self.script_info.name,
                user_name=self.cur_user_item.name,
                log_time=dt,
            )

            if log_item.status == "BetterGI 正常运行中":
                log_item.status = "任务被用户手动中止"

            if len(log_item.content) == 0:
                log_item.content = ["未捕获到任何日志内容"]
                log_item.status = "未捕获到日志"

            await Config.save_general_log(log_path, log_item.content, log_item.status)
            statistic_paths.append(log_path.with_suffix(".json"))

        if statistic_paths:
            try:
                statistics = await Config.merge_statistic_info(statistic_paths)
                statistics["user_info"] = self.cur_user_item.name
                start_time = getattr(self, "user_start_time", datetime.now())
                statistics["start_time"] = start_time.strftime("%Y-%m-%d %H:%M:%S")
                statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                statistics["user_result"] = (
                    "代理任务全部完成" if self.run_book else self.cur_user_item.result
                )
                success_symbol = "√" if self.run_book else "X"
                await push_notification(
                    "统计信息",
                    f"{datetime.now().strftime('%m-%d')} |{success_symbol}|  "
                    f"{self.cur_user_item.name} 的 BetterGI 自动代理统计报告",
                    statistics,
                    self.cur_user_config,
                )
            except Exception as e:
                logger.opt(exception=True).warning(
                    f"推送 BetterGI 用户统计通知时出现异常: {e}"
                )

        await self._persist_user_run_result()

    async def _persist_user_run_result(self) -> None:
        if self.cur_user_config is None:
            return

        await self.cur_user_config.set(
            "Data", "LastOneDragonConfig", getattr(self, "one_dragon_config", "")
        )
        if self.run_book:
            if (
                self.cur_user_config.get("Data", "ProxyTimes") == 0
                and self.cur_user_config.get("Info", "RemainedDay") != -1
            ):
                await self.cur_user_config.set(
                    "Info",
                    "RemainedDay",
                    self.cur_user_config.get("Info", "RemainedDay") - 1,
                )
            await self.cur_user_config.set(
                "Data",
                "ProxyTimes",
                self.cur_user_config.get("Data", "ProxyTimes") + 1,
            )
            await self.cur_user_config.set("Data", "LastProxyStatus", "成功")
            self.cur_user_item.status = "完成"
            logger.success(f"用户 {self.cur_user_uid} 的 BetterGI 自动代理任务已完成")
        else:
            await self.cur_user_config.set("Data", "LastProxyStatus", "失败")
            if self.cur_user_item.status != "完成":
                self.cur_user_item.status = "异常"

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        if self.cur_user_log is not None:
            self.cur_user_log.status = f"BetterGI 运行异常: {e}"
        logger.opt(exception=True).warning(f"BetterGI 自动代理任务出现异常: {e}")
        if self.wait_event is not None:
            self.wait_event.set()
        with suppress(Exception):
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": f"BetterGI 自动代理任务出现异常: {e}"},
            )
        with suppress(Exception):
            await self.kill_managed_process()
        with suppress(Exception):
            await self._persist_user_run_result()

        # 推送通知（复用 Notify）
        try:
            if (
                self.cur_user_log is not None
                and self.cur_user_log.status
                and self.cur_user_log.status != "Success!"
            ):
                await Notify.push_plyer(
                    "BetterGI 运行异常",
                    f"用户 {self.cur_user_item.name}：{self.cur_user_log.status}",
                    "异常",
                    3,
                )
        except Exception:
            pass

    async def kill_managed_process(self) -> None:
        """中止 BetterGI 进程（游戏进程由 BetterGI 自身管理）。"""
        if self.bettergi_process_manager is not None:
            try:
                await self.bettergi_process_manager.kill()
            except Exception as e:
                logger.opt(exception=True).warning(
                    f"通过进程管理器中止 BetterGI 进程失败: {e}"
                )
        if self.script_exe_path is not None:
            try:
                await System.kill_process(self.script_exe_path)
            except Exception as e:
                logger.opt(exception=True).warning(
                    f"中止 BetterGI 主进程失败: {e}"
                )
