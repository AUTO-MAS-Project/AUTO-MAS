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
import shutil
import shlex
import uuid
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path

from app.core import Config
from app.models.ConfigBase import MultipleConfig
from app.models.config import OkefConfig, OkefUserConfig
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase, UserItem
from app.services import Notify, System
from app.task.Ok.common.provider import OkScriptProvider, ok_script_mas_config_dir
from app.task.Ok.common.report import OkScriptReportHandler
from app.task.Ok.common.runtime_lock import get_ok_script_root_lock
from app.task.Ok.providers import detect_ok_script_provider
from app.task.general.tools import execute_script_task
from app.utils import ProcessInfo, ProcessManager, get_logger, is_process_running
from app.utils.LogMonitor import LogMonitor
from app.utils.constants import UTC4

logger = get_logger("ok-script 自动代理")


def _split_args(raw: object) -> list[str]:
    value = str(raw or "").strip()
    return shlex.split(value, posix=False) if value else []


def _replace_tree(src: Path, dst: Path) -> None:
    if not src.is_dir():
        raise FileNotFoundError(src)

    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp_dst = dst.with_name(dst.name + ".tmp")
    shutil.rmtree(tmp_dst, ignore_errors=True)
    shutil.copytree(src, tmp_dst, dirs_exist_ok=True)
    shutil.rmtree(dst, ignore_errors=True)
    tmp_dst.rename(dst)


class OkScriptAutoProxyTask(TaskExecuteBase):
    """ok-script 自动代理：拼 `-t N -e` 启动参数并监控日志。"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: OkefConfig,
        user_config: MultipleConfig[OkefUserConfig],
        game_manager: ProcessManager | None,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.game_manager = game_manager
        self.provider: OkScriptProvider | None = None

        self.cur_user_item: UserItem = self.script_info.user_list[
            self.script_info.current_index
        ]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config: OkefUserConfig = self.user_config[self.cur_user_uid]

        self.script_process_manager: ProcessManager = ProcessManager()
        self.script_root_path: Path = Path()
        self.script_exe_path: Path = Path()
        self.script_target_process_info: ProcessInfo | None = None
        self.script_config_path: Path = Path()
        self.mas_config_dir: Path = Path()
        self.script_config_backup_path: Path = Path()
        self.had_original_script_config = False
        self.script_config_swap_started = False
        self.script_config_injected = False
        self.script_root_lock: asyncio.Lock | None = None
        self.script_root_lock_acquired = False
        self.script_log_path: Path = Path()
        self.log_monitor: LogMonitor | None = None
        self.wait_event: asyncio.Event = asyncio.Event()
        self.log_start_time: datetime = datetime.now()
        self.task_index = 1
        self.script_args: list[str] = []
        self.game_path: Path = Path()
        self.run_book = False
        self.game_started_by_mas = False
        self.cur_user_log: LogRecord | None = None
        self.report_handler: OkScriptReportHandler | None = None
        self.curdate = ""

    async def check(self) -> str:
        root = Path(self.script_config.get("Info", "RootPath"))
        if not root.is_dir():
            return "请设置 ok-script 项目路径"
        provider = self._resolve_provider(root)
        if provider is None:
            return "当前 ok-script 项目尚未适配，请选择已支持的 ok-script 项目"
        self.provider = provider
        if not self.provider.runtime_verified:
            return self.provider.runtime_block_reason or "当前 ok-script 项目尚未完成运行验证"

        if not self.provider.exe_path(root).is_file():
            return "请设置 ok-script 项目路径"

        task_index = int(self.cur_user_config.get("Task", "TaskIndex"))
        if not self.provider.is_supported_task_index(task_index):
            return (
                f"当前任务序号 {task_index} 不属于"
                f"{self.provider.display_name} 已适配的一次性任务"
            )

        mas_config_dir = ok_script_mas_config_dir(
            self.script_info.script_id,
            self.cur_user_item.user_id,
        )
        if not mas_config_dir.is_dir() or not any(mas_config_dir.glob("*.json")):
            return f"用户 {self.cur_user_item.name} 未完成 ok-script 配置，请先在用户编辑页保存配置"

        today = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        if self.cur_user_config.get("Data", "LastProxyDate") != today:
            await self.cur_user_config.set("Data", "LastProxyDate", today)
            await self.cur_user_config.set("Data", "ProxyTimes", 0)

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

        if not Path(self.script_config.get("Game", "Path")).is_file():
            return "请设置游戏程序路径"

        return "Pass"

    async def prepare(self) -> None:
        self.script_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()
        self.script_root_path = Path(self.script_config.get("Info", "RootPath"))
        provider = self._resolve_provider(self.script_root_path)
        if provider is None:
            raise RuntimeError("当前 ok-script 项目尚未适配")
        if not provider.runtime_verified:
            raise RuntimeError(
                provider.runtime_block_reason or "当前 ok-script 项目尚未完成运行验证"
            )
        self.provider = provider
        self.script_root_lock = get_ok_script_root_lock(self.script_root_path)
        if not self.script_root_lock_acquired:
            self.script_info.log = "正在等待同一 ok-script 项目完成运行"
            await self.script_root_lock.acquire()
            self.script_root_lock_acquired = True
        self.script_exe_path = self.provider.exe_path(self.script_root_path)
        self.script_config_path = self.provider.config_path(self.script_root_path)
        self.mas_config_dir = ok_script_mas_config_dir(
            self.script_info.script_id,
            self.cur_user_item.user_id,
        )
        self.script_config_backup_path = (
            Path.cwd()
            / "data"
            / self.script_info.script_id
            / "Temp"
            / self.cur_user_item.user_id
            / "ConfigFile"
        )
        self.had_original_script_config = False
        self.script_config_swap_started = False
        self.script_config_injected = False
        self.script_target_process_info = ProcessInfo(
            name=self.provider.track_process_name,
            exe=str(self.provider.track_process_path(self.script_root_path)),
            cmdline=None,
        )
        self.script_log_path = self.provider.log_path(self.script_root_path)
        self.log_monitor = LogMonitor(
            self.provider.log_time_range,
            self.provider.log_time_format,
            self.check_log,
        )
        self.task_index = int(self.cur_user_config.get("Task", "TaskIndex"))
        self.script_args = self.provider.build_task_args(self.task_index)
        self.game_path = Path(self.script_config.get("Game", "Path"))
        self.run_book = False
        self.game_started_by_mas = False
        self.report_handler = (
            self.provider.report_handler_factory()
            if self.provider.report_handler_factory is not None
            else None
        )

    async def main_task(self) -> None:
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
            self.report_handler = (
                self.provider.report_handler_factory()
                if self.provider.report_handler_factory is not None
                else None
            )

            if self.cur_user_config.get("Info", "IfScriptBeforeTask"):
                await execute_script_task(
                    Path(self.cur_user_config.get("Info", "ScriptBeforeTask")),
                    "脚本前任务",
                )

            await self.sync_script_config()

            # 标准链路：先启动游戏，再启动 ok-script 执行任务并监察日志。
            game_result = await self._launch_game_before_task()
            if game_result != "Pass":
                await self._handle_attempt_failure(game_result, i, run_limit)
                continue

            status = await self._run_script_process()
            self.cur_user_log.status = status
            if len(self.cur_user_log.content) == 0:
                self.cur_user_log.content = [
                    f"启动 {self.provider.display_name}: {' '.join(self.script_args)}",
                    status,
                ]
            self.script_info.log = status

            if status == "Success!":
                self.run_book = True
                self.cur_user_item.status = "完成"
                await self._wait_script_exit(timeout=30)
                await self.update_config()
                await self._restore_script_config()
                if self.report_handler is not None:
                    await self.report_handler.apply(self)
                await self._run_script_after_task()
                break

            await self._handle_attempt_failure(status, i, run_limit)

    async def _handle_attempt_failure(
        self,
        status: str,
        attempt_index: int,
        run_limit: int,
    ) -> None:
        logger.error(
            f"用户 {self.cur_user_item.name} - {self.provider.display_name} 代理异常: {status}"
        )
        if self.cur_user_log is not None:
            self.cur_user_log.status = status
            if len(self.cur_user_log.content) == 0:
                self.cur_user_log.content = [status]
        self.script_info.log = status

        with suppress(Exception):
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": status},
            )

        await self.kill_managed_process(kill_game=self._should_kill_game())
        await self.update_config()
        await self._restore_script_config()
        await self._run_script_after_task()
        with suppress(Exception):
            await Notify.push_plyer(
                f"{self.provider.display_name} 自动代理出现异常！",
                f"用户 {self.cur_user_item.name} 的自动代理出现一次异常",
                f"{self.cur_user_item.name}的自动代理出现异常",
                3,
            )

        if attempt_index + 1 < run_limit:
            await asyncio.sleep(10)
        else:
            self.cur_user_item.status = "异常"

    async def _run_script_after_task(self) -> None:
        if not self.cur_user_config.get("Info", "IfScriptAfterTask"):
            return
        await execute_script_task(
            Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
            "脚本后任务",
        )

    async def sync_script_config(self) -> None:
        try:
            await self._backup_script_config()
            await asyncio.to_thread(
                _replace_tree,
                self.mas_config_dir,
                self.script_config_path,
            )
            self.script_config_injected = True
            logger.info(f"已同步 {self.provider.display_name} 用户配置到脚本目录: {self.script_config_path}")
        except Exception as e:
            logger.exception(f"同步 {self.provider.display_name} 用户配置到脚本目录失败: {e}")
            raise

    async def _backup_script_config(self) -> None:
        """备份脚本本地配置，确保 MAS 注入后可恢复原状。"""

        if self.script_config_injected:
            return

        if self.script_config_backup_path == Path():
            raise RuntimeError("ok-script 配置备份路径未初始化")

        await asyncio.to_thread(
            shutil.rmtree,
            self.script_config_backup_path,
            ignore_errors=True,
        )
        self.had_original_script_config = self.script_config_path.is_dir()
        if self.had_original_script_config:
            await asyncio.to_thread(
                shutil.copytree,
                self.script_config_path,
                self.script_config_backup_path,
            )
        self.script_config_swap_started = True

    async def _restore_script_config(self) -> None:
        """写回 MAS 配置后恢复脚本本地配置。"""

        if not self.script_config_swap_started:
            return

        try:
            if self.had_original_script_config:
                await asyncio.to_thread(
                    _replace_tree,
                    self.script_config_backup_path,
                    self.script_config_path,
                )
            else:
                await asyncio.to_thread(
                    shutil.rmtree,
                    self.script_config_path,
                    ignore_errors=True,
                )
        finally:
            try:
                if self.script_config_backup_path != Path():
                    await asyncio.to_thread(
                        shutil.rmtree,
                        self.script_config_backup_path,
                        ignore_errors=True,
                    )
            finally:
                self.had_original_script_config = False
                self.script_config_swap_started = False
                self.script_config_injected = False

    async def update_config(self) -> None:
        if self.script_config_path == Path() or self.mas_config_dir == Path():
            logger.warning("ok-script 配置路径未初始化，跳过写回")
            return

        try:
            await asyncio.to_thread(
                _replace_tree,
                self.script_config_path,
                self.mas_config_dir,
            )
            logger.info(f"已写回 {self.provider.display_name} 用户配置: {self.mas_config_dir}")
        except Exception as e:
            logger.exception(f"写回 {self.provider.display_name} 用户配置失败: {e}")
            raise

    async def _launch_game_before_task(self) -> str:
        if not self.game_path.is_file():
            return "请设置游戏程序路径"

        if self.game_manager is None:
            self.game_manager = ProcessManager()

        self.script_info.log = "正在准备由 MAS 启动游戏"
        if is_process_running(self.provider.game_process_name):
            logger.info("检测到游戏进程已在运行，跳过由 MAS 重复启动游戏")
            self.script_info.log = "检测到游戏进程已在运行，跳过启动"
            self.game_started_by_mas = True
            return "Pass"

        try:
            await self.game_manager.open_process(
                self.game_path,
                *_split_args(self.script_config.get("Game", "Arguments")),
            )
        except Exception as e:
            logger.exception(f"启动游戏失败: {e}")
            return f"游戏启动失败: {e}"

        self.game_started_by_mas = True
        wait_time = int(self.script_config.get("Game", "WaitTime"))
        self.script_info.log = f"正在等待游戏完成启动\n请等待{wait_time}s"
        await asyncio.sleep(wait_time)
        self.script_info.log = "游戏启动等待完成"
        return "Pass"

    async def _run_script_process(self) -> str:
        await self._kill_script_process()
        logger.info(
            f"启动 {self.provider.display_name} 进程: "
            f"{self.script_exe_path} {' '.join(self.script_args)}"
        )
        self.script_info.log = (
            f"启动 {self.provider.display_name}: -t {self.task_index} -e\n"
            "正在连接游戏窗口并开始运行"
        )
        monitor_started = False
        try:
            await self.script_process_manager.open_process(
                self.script_exe_path,
                *self.script_args,
                target_process=self.script_target_process_info,
            )
        except Exception as e:
            logger.exception(f"启动 {self.provider.display_name} 失败: {e}")
            with suppress(Exception):
                await self._kill_script_process()
            return f"{self.provider.display_name} 启动失败: {e}"

        try:
            deadline = datetime.now() + timedelta(seconds=60)
            while not self.script_log_path.exists() and datetime.now() < deadline:
                if not await self.script_process_manager.is_running():
                    return f"{self.provider.display_name} 在生成日志前退出"
                await asyncio.sleep(1)

            if not self.script_log_path.exists():
                return f"未找到 {self.provider.display_name} 日志文件"

            if self.log_monitor is None:
                return "ok-script 日志监控未初始化"

            self.wait_event.clear()
            self.script_info.log = "运行中，正在监察 ok-script 日志"
            await self.log_monitor.start_monitor_file(
                self.script_log_path, self.log_start_time
            )
            monitor_started = True
            await self.wait_event.wait()

            if self.cur_user_log is None:
                return f"{self.provider.display_name} 未返回运行结果"
            return self.cur_user_log.status or f"{self.provider.display_name} 未返回运行结果"
        finally:
            if monitor_started and self.log_monitor is not None:
                with suppress(Exception):
                    await self.log_monitor.stop()

    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """ok-script 日志回调：失败/成功均由当前 provider 内置字段判定。"""

        if self.cur_user_log is None:
            return

        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log[-4000:] if len(log) > 4000 else log
        if self.report_handler is not None:
            await self.report_handler.capture(self, log)

        log_status = self.provider.running_status
        user_item_status: str | None = None

        for needle, msg in self.provider.fatal_patterns:
            if needle in log:
                log_status = msg
                user_item_status = "异常"
                break
        else:
            log_lower = log.lower()
            if any(
                success.lower() in log_lower
                for success in self.provider.success_patterns
            ):
                log_status = "Success!"
                user_item_status = "完成"
            elif not await self.script_process_manager.is_running():
                log_status = f"{self.provider.display_name} 在完成任务前退出"
                user_item_status = "异常"
            elif datetime.now() - latest_time > timedelta(
                minutes=int(self.script_config.get("Run", "RunTimeLimit"))
            ):
                log_status = f"{self.provider.display_name} 运行超时"
                user_item_status = "异常"

        self.cur_user_log.status = log_status
        if user_item_status is not None:
            self.cur_user_item.status = user_item_status

        logger.debug(f"{self.provider.display_name} 日志分析结果: {self.cur_user_log.status}")
        if self.cur_user_log.status != self.provider.running_status:
            logger.info(
                f"{self.provider.display_name} 任务结果: {self.cur_user_log.status}, 日志锁已释放"
            )
            self.wait_event.set()

    async def final_task(self) -> None:
        try:
            await self._finalize_task()
        finally:
            self._release_script_root_lock()

    async def _finalize_task(self) -> None:
        with suppress(Exception):
            if self.log_monitor is not None:
                await self.log_monitor.stop()

        await self.kill_managed_process(
            kill_game=(not self.run_book) and self._should_kill_game()
        )
        try:
            await self._restore_script_config()
        except Exception as restore_error:
            logger.exception(
                f"恢复 {self.provider.display_name} 脚本本地配置失败: {restore_error}"
            )

        for t, log_item in self.cur_user_item.log_record.items():
            dt = t.replace(tzinfo=datetime.now().astimezone().tzinfo).astimezone(UTC4)
            log_path = (
                Path.cwd()
                / f"history/{dt.strftime('%Y-%m-%d')}/{self.cur_user_item.name}/{dt.strftime('%H-%M-%S')}.log"
            )

            if log_item.status == self.provider.running_status:
                log_item.status = "任务被用户手动中止"

            if len(log_item.content) == 0:
                log_item.content = ["未捕获到任何日志内容"]
                log_item.status = "未捕获到日志"

            await Config.save_general_log(log_path, log_item.content, log_item.status)

        await self._persist_user_run_result()

    async def _persist_user_run_result(self) -> None:
        await self.cur_user_config.set("Data", "LastTaskIndex", self.task_index)
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
            logger.success(
                f"用户 {self.cur_user_uid} 的 {self.provider.display_name} 自动代理任务已完成"
            )
            return

        await self.cur_user_config.set("Data", "LastProxyStatus", "失败")
        if self.cur_user_item.status not in ("完成", "跳过"):
            self.cur_user_item.status = "异常"

    async def on_crash(self, e: Exception) -> None:
        self.cur_user_item.status = "异常"
        if self.cur_user_log is not None:
            self.cur_user_log.status = f"{self.provider.display_name} 运行异常: {e}"
        self.wait_event.set()
        with suppress(Exception):
            if self.log_monitor is not None:
                await self.log_monitor.stop()
        logger.exception(f"{self.provider.display_name} 自动代理任务出现异常: {e}")
        try:
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": f"{self.provider.display_name} 自动代理任务出现异常: {e}"},
            )
        except Exception as send_error:
            logger.exception(f"发送 {self.provider.display_name} 异常通知失败: {send_error}")
        try:
            await self.kill_managed_process(kill_game=self._should_kill_game())
        except Exception as kill_error:
            logger.exception(f"清理 {self.provider.display_name} 进程失败: {kill_error}")
        try:
            if self.script_config_injected:
                await self.update_config()
        except Exception as config_error:
            logger.exception(f"崩溃后写回 {self.provider.display_name} 配置失败: {config_error}")
        try:
            await self._restore_script_config()
        except Exception as restore_error:
            logger.exception(
                f"崩溃后恢复 {self.provider.display_name} 脚本本地配置失败: {restore_error}"
            )
        try:
            await self._persist_user_run_result()
        except Exception as persist_error:
            logger.exception(
                f"写回 {self.provider.display_name} 用户运行结果失败: {persist_error}"
            )

    def _should_kill_game(self) -> bool:
        return self.game_path.is_file()

    def _resolve_provider(self, root: Path) -> OkScriptProvider | None:
        return detect_ok_script_provider(
            root,
            self.script_config.get("Info", "ResourceName"),
        )

    def _release_script_root_lock(self) -> None:
        if (
            self.script_root_lock_acquired
            and self.script_root_lock is not None
            and self.script_root_lock.locked()
        ):
            self.script_root_lock.release()
        self.script_root_lock_acquired = False

    async def _wait_script_exit(self, *, timeout: int = 30) -> None:
        deadline = datetime.now() + timedelta(seconds=timeout)
        while datetime.now() < deadline:
            if not await self.script_process_manager.is_running():
                logger.info(f"{self.provider.display_name} 已自行退出")
                return
            await asyncio.sleep(1)
        logger.warning(f"{self.provider.display_name} 未在 {timeout}s 内自行退出，兜底强杀")
        await self._kill_script_process()

    async def _kill_script_process(self) -> None:
        try:
            await self.script_process_manager.kill()
        except Exception as e:
            logger.exception(f"通过进程管理器中止 {self.provider.display_name} 进程失败: {e}")
        if self.script_exe_path.is_file():
            try:
                await System.kill_process(self.script_exe_path)
            except Exception as e:
                logger.exception(f"中止 {self.provider.display_name} 主进程失败: {e}")
        if self.script_root_path != Path():
            track_exe = self.provider.track_process_path(self.script_root_path)
            if track_exe.is_file():
                try:
                    await System.kill_process(track_exe)
                except Exception as e:
                    logger.exception(f"中止 {self.provider.display_name} 追踪进程失败: {e}")

    async def _kill_game_process(self) -> None:
        try:
            if isinstance(self.game_manager, ProcessManager):
                await self.game_manager.kill()
        except Exception as e:
            logger.exception(f"通过进程管理器关闭游戏失败: {e}")
        try:
            if self.game_path.is_file():
                await System.kill_process(self.game_path)
        except Exception as e:
            logger.exception(f"关闭游戏进程失败: {e}")
        finally:
            self.game_started_by_mas = False

    async def kill_managed_process(self, *, kill_game: bool = True) -> None:
        await self._kill_script_process()
        if kill_game:
            await self._kill_game_process()
