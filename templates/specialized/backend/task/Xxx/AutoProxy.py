"""Xxx 专项自动代理任务。

这是从 ``app/task/general/AutoProxy.py`` 收敛出的可复制基线。复制后先完成
``TODO(specialized)``，再接入真实 ScriptType；不要把这里的默认日志关键词或
启动参数直接当成上游脚本契约。
"""

from __future__ import annotations

import asyncio
import re
import shlex
import shutil
import uuid
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path

from app.core import Config
from app.models.ConfigBase import MultipleConfig
from app.models.config import XxxConfig, XxxUserConfig
from app.models.emulator import DeviceBase
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase
from app.services import Notify, System
from app.utils import (
    LogMonitor,
    ProcessInfo,
    ProcessManager,
    get_logger,
    is_process_running,
    strptime,
)
from app.utils.constants import UTC4
from app.task.general.tools import execute_script_task, push_notification


logger = get_logger("专项显示名称自动代理")

_PREFIX_SENTINEL = "******"
_STRPTIME_DIRECTIVES: dict[str, str] = {
    "%Y": r"\d{4}",
    "%y": r"\d{2}",
    "%m": r"\d{1,2}",
    "%d": r"\d{1,2}",
    "%H": r"\d{1,2}",
    "%I": r"\d{1,2}",
    "%M": r"\d{1,2}",
    "%S": r"\d{1,2}",
    "%f": r"\d+",
    "%j": r"\d{1,3}",
    "%U": r"\d{1,2}",
    "%W": r"\d{1,2}",
    "%w": r"\d",
    "%A": r"\w+",
    "%a": r"\w+",
    "%B": r"\w+",
    "%b": r"\w+",
    "%p": r"[APap][Mm]",
    "%%": r"%",
}


def _format_to_prefix_regex(fmt: str) -> re.Pattern[str]:
    """将 strptime 格式转换成日志文件名前缀正则。"""

    parts: list[str] = []
    index = 0
    while index < len(fmt):
        if fmt[index] == "%" and index + 1 < len(fmt):
            directive = fmt[index : index + 2]
            if directive in _STRPTIME_DIRECTIVES:
                parts.append(_STRPTIME_DIRECTIVES[directive])
                index += 2
                continue
        parts.append(re.escape(fmt[index]))
        index += 1
    return re.compile("^" + "".join(parts))


def _split_script_arguments(raw: str, script_path: Path) -> tuple[list[Path], list[list[str]]]:
    """解析 General 的 ``path%args|path%args`` 参数格式。"""

    executable_paths: list[Path] = []
    arguments: list[list[str]] = []
    for item in (part.strip() for part in str(raw).split("|") if part.strip()):
        parts = [part.strip() for part in item.split("%", 1) if part.strip()]
        executable_paths.append(
            (script_path / parts[0] if len(parts) > 1 else script_path).resolve()
        )
        arguments.append(shlex.split(parts[-1], posix=False))
    return executable_paths, arguments


class AutoProxyTask(TaskExecuteBase):
    """专项自动代理：一名用户串行执行多次，直到成功或达到重试上限。"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: XxxConfig,
        user_config: MultipleConfig[XxxUserConfig],
        game_manager: ProcessManager | DeviceBase | None,
    ) -> None:
        super().__init__()
        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.game_manager = game_manager
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config = self.user_config[self.cur_user_uid]
        self.use_mas_config = bool(
            self.cur_user_config.get("Info", "IfUseMasConfig")
        )

        # 跨回调、final_task 和 on_crash 使用的状态全部显式初始化。
        self.check_result = "-"
        self.run_book = False
        self.wait_event: asyncio.Event | None = None
        self.general_process_manager: ProcessManager | None = None
        self.general_log_monitor: LogMonitor | None = None
        self.script_exe_path: Path | None = None
        self.script_path: Path | None = None
        self.script_arguments: list[str] = []
        self.script_set_arguments: list[str] = []
        self.script_target_process_info: ProcessInfo | None = None
        self.script_config_path: Path | None = None
        self.script_log_path: Path | None = None
        self.log_format = ""
        self.log_use_prefix = False
        self.game_path: Path | None = None
        self.game_url = ""
        self.game_process_name = ""
        self.log_time_range = (0, 1)
        self.success_log: list[str] = []
        self.error_log: list[str] = []
        self.curdate = ""
        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now()
        self.cur_user_log: LogRecord | None = None

        # 直控配置快照：任务结束、取消、超时和异常都从这里恢复。
        self.temp_path: Path | None = None
        self.external_config_exists = False
        self.external_config_snapshot_ready = False

    async def check(self) -> str:
        """检查用户状态和专项运行前置条件。"""

        proxy_limit = self.script_config.get("Run", "ProxyTimesLimit")
        if proxy_limit != 0 and self.cur_user_config.get("Data", "ProxyTimes") >= proxy_limit:
            self.cur_user_item.status = "跳过"
            return "今日代理次数已达上限, 跳过该用户"

        if self.use_mas_config and not self._user_config_source_path().exists():
            self.cur_user_item.status = "异常"
            return "请先在用户配置页完成「专项显示名称配置」步骤"

        # TODO(specialized): 修改脚本路径校验
        script_path = Path(self.script_config.get("Script", "ScriptPath"))
        if not script_path.exists():
            self.cur_user_item.status = "异常"
            return "请设置脚本路径"
        if not self.script_config.get("Info", "RootPath"):
            self.cur_user_item.status = "异常"
            return "请设置脚本根目录"
        return "Pass"

    def _user_config_path(self) -> Path:
        return (
            Path.cwd()
            / "data"
            / self.script_info.script_id
            / str(self.cur_user_uid)
            / "ConfigFile"
        )

    def _user_config_source_path(self) -> Path:
        """返回当前用户副本中与脚本配置模式对应的源路径。"""

        user_path = self._user_config_path()
        if self.script_config.get("Script", "ConfigPathMode") == "Folder":
            return user_path
        config_path = Path(self.script_config.get("Script", "ConfigPath"))
        return user_path / config_path.name

    def _remove_path(self, path: Path) -> None:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()

    def _copy_path_atomic(self, source: Path, destination: Path, mode: str) -> None:
        """以临时路径替换配置，避免中断留下半份配置。"""

        if mode == "Folder":
            temporary = destination.with_name(destination.name + ".tmp")
            shutil.rmtree(temporary, ignore_errors=True)
            if source.exists():
                temporary.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source, temporary, dirs_exist_ok=True)
            self._remove_path(destination)
            if temporary.exists():
                temporary.rename(destination)
            return

        temporary = destination.with_name(destination.name + ".tmp")
        if temporary.exists():
            temporary.unlink()
        if source.exists():
            temporary.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, temporary)
            temporary.replace(destination)
        else:
            self._remove_path(destination)

    def _snapshot_external_config(self) -> None:
        """备份任务开始前的脚本直控配置。"""

        if self.script_config_path is None or self.temp_path is None:
            return
        shutil.rmtree(self.temp_path, ignore_errors=True)
        self.external_config_exists = self.script_config_path.exists()
        self.temp_path.mkdir(parents=True, exist_ok=True)
        if self.external_config_exists:
            mode = self.script_config.get("Script", "ConfigPathMode")
            if mode == "Folder":
                shutil.copytree(self.script_config_path, self.temp_path, dirs_exist_ok=True)
            else:
                shutil.copy2(self.script_config_path, self.temp_path / "config.temp")
        self.external_config_snapshot_ready = True

    def _restore_external_config(self) -> None:
        """恢复任务开始前的脚本直控配置。"""

        if (
            not self.external_config_snapshot_ready
            or self.script_config_path is None
            or self.temp_path is None
        ):
            return
        self._remove_path(self.script_config_path)
        if not self.external_config_exists:
            return
        mode = self.script_config.get("Script", "ConfigPathMode")
        if mode == "Folder":
            self._copy_path_atomic(self.temp_path, self.script_config_path, "Folder")
        else:
            self._copy_path_atomic(
                self.temp_path / "config.temp", self.script_config_path, "File"
            )

    def _cleanup_external_config_snapshot(self) -> None:
        if self.temp_path is not None:
            shutil.rmtree(self.temp_path, ignore_errors=True)
        self.external_config_snapshot_ready = False

    def _build_specialized_arguments(self) -> list[str]:
        # TODO(specialized): 构造专项启动参数
        return []

    async def prepare(self) -> None:
        """加载运行参数、进程追踪信息、日志判态和配置快照。"""

        self.wait_event = asyncio.Event()
        self.general_process_manager = ProcessManager()
        self.user_start_time = datetime.now()
        self.script_path = Path(self.script_config.get("Script", "ScriptPath"))
        argument_paths, argument_lists = _split_script_arguments(
            self.script_config.get("Script", "Arguments"), self.script_path
        )
        self.script_exe_path = argument_paths[0] if argument_paths else self.script_path
        self.script_arguments = (
            argument_lists[0] if argument_lists else []
        ) + self._build_specialized_arguments()
        self.script_set_arguments = argument_lists[1] if len(argument_lists) > 1 else []

        if self.script_config.get("Script", "IfTrackProcess"):
            self.script_target_process_info = ProcessInfo(
                name=self.script_config.get("Script", "TrackProcessName") or None,
                exe=self.script_config.get("Script", "TrackProcessExe") or None,
                cmdline=shlex.split(
                    self.script_config.get("Script", "TrackProcessCmdline"),
                    posix=False,
                )
                or None,
            )

        self.script_config_path = Path(self.script_config.get("Script", "ConfigPath"))
        self.temp_path = (
            Path.cwd()
            / "data"
            / self.script_info.script_id
            / "Temp"
            / str(self.cur_user_uid)
        )
        self.script_log_path = Path(self.script_config.get("Script", "LogPath"))
        self.log_format = self.script_config.get("Script", "LogPathFormat") or ""
        self.log_use_prefix = self.log_format.endswith(_PREFIX_SENTINEL)
        if self.log_use_prefix:
            prefix_re = _format_to_prefix_regex(
                self.log_format[: -len(_PREFIX_SENTINEL)]
            )
            if not prefix_re.match(self.script_log_path.stem):
                logger.warning(
                    f"LogPathFormat 与 LogPath 不匹配: {self.log_format} vs {self.script_log_path}"
                )
        elif self.log_format:
            with suppress(ValueError):
                datetime.strptime(self.script_log_path.stem, self.log_format)
                self.log_format += self.script_log_path.suffix
        else:
            self.log_format = self.script_log_path.name

        self.game_path = Path(self.script_config.get("Game", "Path"))
        self.game_url = self.script_config.get("Game", "URL")
        self.game_process_name = self.script_config.get("Game", "ProcessName")
        self.log_time_range = (
            self.script_config.get("Script", "LogTimeStart") - 1,
            self.script_config.get("Script", "LogTimeEnd"),
        )
        self.success_log = [
            item.strip()
            for item in self.script_config.get("Script", "SuccessLog").split("|")
            if item.strip()
        ]
        self.error_log = [
            item.strip()
            for item in self.script_config.get("Script", "ErrorLog").split("|")
            if item.strip()
        ]
        self.general_log_monitor = LogMonitor(
            self.log_time_range,
            self.script_config.get("Script", "LogTimeFormat"),
            self.check_log,
        )
        self._snapshot_external_config()

    async def _start_game(self) -> None:
        if self.game_manager is None:
            return
        try:
            if isinstance(self.game_manager, ProcessManager):
                if self.script_config.get("Game", "Type") == "URL":
                    if self.game_process_name and is_process_running(self.game_process_name):
                        logger.info(f"游戏进程已运行，跳过重复启动: {self.game_process_name}")
                    else:
                        await self.game_manager.open_protocol(
                            self.game_url,
                            ProcessInfo(name=self.game_process_name or None),
                        )
                else:
                    game_process_name = self.game_path.name if self.game_path else ""
                    if game_process_name and is_process_running(game_process_name):
                        logger.info(f"游戏进程已运行，跳过重复启动: {game_process_name}")
                    else:
                        await self.game_manager.open_process(
                            self.game_path,
                            *str(self.script_config.get("Game", "Arguments")).split(" "),
                        )
                await asyncio.sleep(self.script_config.get("Game", "WaitTime"))
            elif isinstance(self.game_manager, DeviceBase):
                await self.game_manager.open(
                    self.script_config.get("Game", "EmulatorIndex")
                )
        except Exception as error:
            await self.handle_pre_script_error("游戏/模拟器启动失败", error)
            raise

    async def main_task(self) -> None:
        """执行前置脚本、游戏、专项程序、日志监控和后置脚本。"""

        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        if self.cur_user_config.get("Data", "LastProxyDate") != self.curdate:
            await self.cur_user_config.set("Data", "LastProxyDate", self.curdate)
            await self.cur_user_config.set("Data", "ProxyTimes", 0)

        self.check_result = await self.check()
        if self.check_result != "Pass":
            if self.cur_user_item.status == "异常":
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={"Error": self.check_result},
                )
            return

        await self.prepare()
        self.cur_user_item.status = "运行"
        run_limit = self.script_config.get("Run", "RunTimesLimit")

        for attempt in range(run_limit):
            if self.run_book:
                break
            self.log_start_time = datetime.now()
            self.cur_user_item.log_record[self.log_start_time] = self.cur_user_log = (
                LogRecord()
            )
            logger.info(f"用户 {self.cur_user_item.name} - 尝试次数: {attempt + 1}/{run_limit}")

            if self.cur_user_config.get("Info", "IfScriptBeforeTask"):
                await execute_script_task(
                    Path(self.cur_user_config.get("Info", "ScriptBeforeTask")),
                    "脚本前任务",
                )

            try:
                await self._start_game()
                await self.set_script_config()
                if (
                    self.general_process_manager is None
                    or self.script_exe_path is None
                    or self.wait_event is None
                    or self.general_log_monitor is None
                ):
                    raise RuntimeError("专项任务未完成初始化")
                self.wait_event.clear()
                process_started_at = datetime.now()
                await self.general_process_manager.open_process(
                    self.script_exe_path,
                    *self.script_arguments,
                    target_process=self.script_target_process_info,
                )
                self.script_info.log = "正在等待脚本日志文件生成"
                log_path = await self._wait_for_log_file(process_started_at)
                if log_path is None:
                    await self.handle_pre_script_error("未找到日志文件")
                    continue
                self.script_log_path = log_path
                await self.general_log_monitor.start_monitor_file(
                    self.script_log_path, self.log_start_time
                )
                await self.wait_event.wait()
                await self.general_log_monitor.stop()
            except Exception as error:
                await self.handle_pre_script_error("专项任务启动失败", error)
                continue

            if self.cur_user_log.status == "Success!":
                self.run_book = True
                self.script_info.log = "检测到专项任务完成，正在等待相关程序结束"
                await self.kill_managed_process()
                await asyncio.sleep(1)
                if self.script_config.get("Script", "UpdateConfigMode") in (
                    "Success",
                    "Always",
                ):
                    await self.update_config()
            else:
                logger.warning(
                    f"用户 {self.cur_user_uid} - 代理任务异常: {self.cur_user_log.status}"
                )
                self.script_info.log = f"{self.cur_user_log.status}\n正在中止相关程序"
                await self.kill_managed_process()
                await Notify.push_plyer(
                    "用户自动代理出现异常！",
                    f"用户 {self.cur_user_item.name} 的自动代理出现一次异常",
                    f"{self.cur_user_item.name}的自动代理出现异常",
                    3,
                )
                if self.script_config.get("Script", "UpdateConfigMode") in (
                    "Failure",
                    "Always",
                ):
                    await self.update_config()

            if self.cur_user_config.get("Info", "IfScriptAfterTask"):
                await execute_script_task(
                    Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
                    "脚本后任务",
                )

    async def _wait_for_log_file(self, started_at: datetime) -> Path | None:
        """等待固定日志或按日期/序号生成的日志文件。"""

        if self.script_log_path is None:
            return None
        target_suffix: int | None = None
        prefix_re = (
            _format_to_prefix_regex(self.log_format[: -len(_PREFIX_SENTINEL)])
            if self.log_use_prefix
            else None
        )
        for _ in range(60):
            if self.script_log_path.exists() and not self.log_use_prefix:
                return self.script_log_path
            if prefix_re is not None and self.script_log_path.parent.exists():
                current_suffix = 0
                current_file: Path | None = None
                for candidate in self.script_log_path.parent.iterdir():
                    if not candidate.is_file():
                        continue
                    match = prefix_re.match(candidate.name)
                    if not match:
                        continue
                    with suppress(ValueError):
                        file_time = strptime(
                            match.group(0), self.log_format[: -len(_PREFIX_SENTINEL)], started_at
                        )
                        if file_time.date() != started_at.date():
                            continue
                    suffix_match = re.search(
                        r"(\d+)\s*$", candidate.name[match.end() :].rsplit(".", 1)[0]
                    )
                    suffix = int(suffix_match.group(1)) if suffix_match else 0
                    if suffix > current_suffix:
                        current_suffix = suffix
                        current_file = candidate
                if target_suffix is None:
                    target_suffix = current_suffix + 1
                if current_file is not None and current_suffix >= target_suffix:
                    return current_file
            await asyncio.sleep(1)
        return None

    async def handle_pre_script_error(
        self, error_message: str, error: Exception | None = None
    ) -> None:
        message = error_message if error is None else f"{error_message}: {error}"
        logger.warning(f"用户 {self.cur_user_uid} - {message}")
        self.script_info.log = message
        if self.cur_user_log is not None:
            self.cur_user_log.content = [f"{message}, 无日志记录"]
            self.cur_user_log.status = error_message
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": message},
        )
        await self.kill_managed_process()

    async def set_script_config(self) -> None:
        """将用户副本导入脚本配置路径。"""

        if self.script_config_path is None:
            return
        await System.kill_process(self.script_exe_path)
        if not self.use_mas_config:
            logger.info("脚本直控配置：跳过写入用户配置")
            return
        # TODO(specialized): 写入专项配置
        self._copy_path_atomic(
            self._user_config_source_path(),
            self.script_config_path,
            self.script_config.get("Script", "ConfigPathMode"),
        )

    async def update_config(self) -> None:
        """按脚本设置把运行后的配置写回用户副本。"""

        if not self.use_mas_config or self.script_config_path is None:
            return
        self._copy_path_atomic(
            self.script_config_path,
            self._user_config_source_path(),
            self.script_config.get("Script", "ConfigPathMode"),
        )
        logger.success("专项脚本配置已更新")

    async def kill_managed_process(self) -> None:
        """分别清理专项程序和游戏/模拟器，单步失败不阻塞后续清理。"""

        if self.general_process_manager is not None:
            try:
                await self.general_process_manager.kill()
            except Exception as error:
                logger.warning(f"中止专项进程管理器失败: {error}")
        if self.script_exe_path is not None:
            try:
                await System.kill_process(self.script_exe_path)
            except Exception as error:
                logger.warning(f"中止专项主进程失败: {error}")
        if self.game_manager is None:
            return
        try:
            if isinstance(self.game_manager, ProcessManager):
                await self.game_manager.kill()
                if (
                    self.script_config.get("Game", "Type") == "Client"
                    and self.script_config.get("Game", "IfForceClose")
                    and self.game_path is not None
                ):
                    await System.kill_process(self.game_path)
            elif isinstance(self.game_manager, DeviceBase):
                await self.game_manager.close(
                    self.script_config.get("Game", "EmulatorIndex")
                )
        except Exception as error:
            logger.warning(f"关闭游戏/模拟器失败: {error}")

    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """根据日志文本、时间戳和进程状态更新本轮结果。"""

        if self.cur_user_log is None or self.wait_event is None:
            return
        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log

        # TODO(specialized): 定义成功与失败条件
        if any(marker in log for marker in self.success_log):
            self.cur_user_log.status = "Success!"
        elif datetime.now() - latest_time > timedelta(
            minutes=self.script_config.get("Run", "RunTimeLimit")
        ):
            self.cur_user_log.status = "脚本进程超时"
        elif any(marker in log for marker in self.error_log):
            self.cur_user_log.status = "异常日志"
        elif self.general_process_manager and await self.general_process_manager.is_running():
            self.cur_user_log.status = "专项脚本正常运行中"
        elif self.success_log:
            self.cur_user_log.status = "脚本在完成任务前退出"
        else:
            self.cur_user_log.status = "Success!"

        if self.cur_user_log.status != "专项脚本正常运行中":
            self.wait_event.set()

    async def _stop_log_monitor(self) -> None:
        if self.general_log_monitor is not None:
            with suppress(Exception):
                await self.general_log_monitor.stop()

    async def _save_history(self) -> None:
        user_logs: list[Path] = []
        for start_time, log_item in self.cur_user_item.log_record.items():
            if log_item.status == "专项脚本正常运行中":
                log_item.status = "任务被用户手动中止"
            if not log_item.content:
                log_item.content = ["未捕获到任何日志内容"]
                log_item.status = "未捕获到日志"
            log_time = start_time.replace(
                tzinfo=datetime.now().astimezone().tzinfo
            ).astimezone(UTC4)
            history_path = Config.build_history_log_path(
                script_name=self.script_info.name,
                user_name=self.cur_user_item.name,
                log_time=log_time,
            )
            await Config.save_general_log(history_path, log_item.content, log_item.status)
            user_logs.append(history_path.with_suffix(".json"))

        statistics = await Config.merge_statistic_info(user_logs)
        statistics["user_info"] = self.cur_user_item.name
        statistics["start_time"] = self.user_start_time.strftime("%Y-%m-%d %H:%M:%S")
        statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        statistics["user_result"] = (
            "代理任务全部完成" if self.run_book else self.cur_user_item.result
        )
        try:
            await push_notification(
                "统计信息",
                f"{datetime.now().strftime('%m-%d')} |{'√' if self.run_book else 'X'}| "
                f"{self.cur_user_item.name} 的自动代理统计报告",
                statistics,
                self.cur_user_config,
            )
        except Exception as error:
            logger.warning(f"推送通知时出现异常: {error}")

    async def final_task(self) -> None:
        """停止运行、写历史记录、恢复配置并更新用户状态。"""

        await self._stop_log_monitor()
        await self.kill_managed_process()
        if self.check_result == "Pass":
            await self._save_history()
        # 回写用户副本后恢复原配置；直控配置始终不被任务结果污染。
        self._restore_external_config()
        self._cleanup_external_config_snapshot()

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
            self.cur_user_item.status = "完成"
            await Notify.push_plyer(
                "成功完成一个自动代理任务！",
                f"已完成用户 {self.cur_user_item.name} 的自动代理任务",
                f"已完成 {self.cur_user_item.name} 的自动代理任务",
                3,
            )
        elif self.check_result == "Pass":
            self.cur_user_item.status = "异常"

    async def on_crash(self, error: Exception) -> None:
        """异常路径必须可重复执行，并向调度台报告 Error。"""

        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"专项自动代理任务出现异常: {error}")
        await self._stop_log_monitor()
        await self.kill_managed_process()
        self._restore_external_config()
        self._cleanup_external_config_snapshot()
        with suppress(Exception):
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": f"专项自动代理任务出现异常: {error}"},
            )
