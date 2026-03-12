import asyncio
import json
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from app.core import Config
from app.models.ConfigBase import MultipleConfig
from app.models.config import MaaEndConfig, MaaEndUserConfig
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase
from app.services import Notify, System
from app.utils import LogMonitor, ProcessManager, get_logger
from app.utils.constants import UTC4

from .runtime_bridge import build_runtime_config


logger = get_logger("MaaEnd 自动代理")


class AutoProxyTask(TaskExecuteBase):
    """MaaEnd 自动代理模式"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: MaaEndConfig,
        user_config: MultipleConfig[MaaEndUserConfig],
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config

        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config = self.user_config[self.cur_user_uid]

        self.check_result = "-"
        self.run_success = False
        self.last_status = "-"

    def _split_patterns(self, value: str) -> list[str]:
        return [item.strip() for item in value.split("|") if item.strip()]

    async def check(self) -> str:
        if self.script_config.get("Run", "RunTimesLimit") <= 0:
            self.cur_user_item.status = "异常"
            return "RunTimesLimit 必须大于 0"

        return "Pass"

    async def prepare(self):
        self.maaend_root_path = Path(self.script_config.get("Info", "Path"))
        self.maaend_exe_path = self.maaend_root_path / "MaaEnd.exe"
        self.maaend_config_path = self.maaend_root_path / "config" / "mxu-MaaEnd.json"

        self.log_path = self.maaend_root_path / "debug" / "maa.log"
        self.timeout_minutes = self.script_config.get("Run", "Timeout")
        self.retry_times = self.script_config.get("Run", "Retry")

        self.success_patterns = self._split_patterns(
            str(self.script_config.get("MaaEnd", "SuccessPattern"))
        )
        self.error_patterns = self._split_patterns(
            str(self.script_config.get("MaaEnd", "ErrorPattern"))
        )

        self.wait_event = asyncio.Event()
        self.maaend_process_manager = ProcessManager()
        self.maaend_log_monitor = LogMonitor(
            (1, 20),
            "%Y-%m-%d %H:%M:%S",
            self.check_log,
        )

        self.is_realtime_task = False

    def _detect_realtime_task(self, runtime_path: Path) -> bool:
        runtime_data = json.loads(runtime_path.read_text(encoding="utf-8"))
        instances = runtime_data.get("instances", [])
        if not instances:
            return False

        active_id = runtime_data.get("lastActiveInstanceId")
        selected_instance = next(
            (item for item in instances if item.get("id") == active_id), None
        )
        if selected_instance is None:
            selected_instance = instances[0]

        for task in selected_instance.get("tasks", []):
            if not isinstance(task, dict):
                continue
            if task.get("taskName") == "RealTimeTask" and bool(task.get("enabled")):
                return True

        return False

    async def _prepare_runtime_config(self) -> Path:
        runtime_path = build_runtime_config(
            self.script_info.script_id,
            self.cur_user_item.user_id,
            self.script_config,
            self.cur_user_config,
        )
        self.maaend_config_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(runtime_path, self.maaend_config_path)
        return runtime_path

    async def _run_once(self, run_idx: int, retry_idx: int) -> bool:
        self.script_info.log = (
            f"用户 {self.cur_user_item.name} 执行中：轮次 {run_idx + 1}"
            f"，重试 {retry_idx}/{self.retry_times}"
        )

        self.log_start_time = datetime.now()
        self.cur_user_item.log_record[self.log_start_time] = self.cur_user_log = LogRecord()

        runtime_path = await self._prepare_runtime_config()
        self.is_realtime_task = self._detect_realtime_task(runtime_path)

        await self.maaend_process_manager.kill()
        await System.kill_process(self.maaend_exe_path)

        self.wait_event.clear()
        await self.maaend_process_manager.open_process(self.maaend_exe_path)
        await asyncio.sleep(1)
        await self.maaend_log_monitor.start_monitor_file(self.log_path, self.log_start_time)

        await self.wait_event.wait()
        await self.maaend_log_monitor.stop()

        if self.cur_user_log.status == "Success!":
            return True

        await self.maaend_process_manager.kill()
        await System.kill_process(self.maaend_exe_path)
        return False

    async def main_task(self):
        self.check_result = await self.check()
        if self.check_result != "Pass":
            if self.cur_user_item.status == "异常":
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={
                        "Error": f"用户 {self.cur_user_item.name} 检查未通过: {self.check_result}"
                    },
                )
            return

        await self.prepare()
        self.cur_user_item.status = "运行"

        attempts = self.script_config.get("Run", "RunTimesLimit")
        self.run_success = False
        self.last_status = "ExitCode"

        for run_idx in range(attempts):
            for retry_idx in range(self.retry_times + 1):
                self.run_success = await self._run_once(run_idx, retry_idx)

                if self.run_success:
                    self.last_status = "Success"
                    break

                if self.cur_user_log.status.startswith("PatternError"):
                    self.last_status = "PatternError"
                elif self.cur_user_log.status == "Timeout":
                    self.last_status = "Timeout"
                elif self.cur_user_log.status.startswith("ExitCode"):
                    self.last_status = "ExitCode"
                else:
                    self.last_status = "Crash"

            if self.run_success:
                break

        await self.cur_user_config.set(
            "Data", "LastRun", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        await self.cur_user_config.set(
            "Data", "RunTimes", self.cur_user_config.get("Data", "RunTimes") + 1
        )
        await self.cur_user_config.set("Data", "LastStatus", self.last_status)

        if self.run_success:
            self.cur_user_item.status = "完成"
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Info": f"用户 {self.cur_user_item.name} MaaEnd 自动代理完成"},
            )
        else:
            self.cur_user_item.status = "异常"
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={
                    "Error": (
                        f"用户 {self.cur_user_item.name} MaaEnd 自动代理失败: "
                        f"{self.cur_user_log.status}"
                    )
                },
            )

    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log

        for pattern in self.error_patterns:
            if pattern in log:
                self.cur_user_log.status = f"PatternError:{pattern}"
                self.wait_event.set()
                return

        for pattern in self.success_patterns:
            if pattern in log:
                self.cur_user_log.status = "Success!"
                self.wait_event.set()
                return

        if (
            not self.is_realtime_task
            and self.timeout_minutes > 0
            and datetime.now() - latest_time > timedelta(minutes=self.timeout_minutes)
        ):
            self.cur_user_log.status = "Timeout"
            self.wait_event.set()
            return

        process = self.maaend_process_manager.process
        if process is not None and process.returncode is not None:
            if process.returncode == 0:
                self.cur_user_log.status = "Success!"
            else:
                self.cur_user_log.status = f"ExitCode:{process.returncode}"
            self.wait_event.set()
            return

        self.cur_user_log.status = "MaaEnd 正常运行中"

    async def final_task(self):
        if self.check_result != "Pass":
            return

        await self.maaend_log_monitor.stop()
        await self.maaend_process_manager.kill()
        await System.kill_process(self.maaend_exe_path)

        for t, log_item in self.cur_user_item.log_record.items():
            dt = t.replace(tzinfo=datetime.now().astimezone().tzinfo).astimezone(UTC4)
            log_path = (
                Path.cwd()
                / f"history/{dt.strftime('%Y-%m-%d')}/{self.cur_user_item.name}/{dt.strftime('%H-%M-%S')}.log"
            )

            if log_item.status == "MaaEnd 正常运行中":
                log_item.status = "任务被用户手动中止"

            if len(log_item.content) == 0:
                log_item.content = ["未捕获到任何日志内容"]
                log_item.status = "未捕获到日志"

            await Config.save_general_log(log_path, log_item.content, log_item.status)

        if self.run_success:
            await Notify.push_plyer(
                "成功完成一个自动代理任务！",
                f"已完成用户 {self.cur_user_item.name} 的自动代理任务",
                f"已完成 {self.cur_user_item.name} 的自动代理任务",
                3,
            )
        else:
            self.cur_user_item.status = "异常"

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        await self.cur_user_config.set(
            "Data", "LastRun", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        await self.cur_user_config.set("Data", "LastStatus", "Crash")
        logger.exception(f"MaaEnd 自动代理任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"MaaEnd 自动代理任务出现异常: {e}"},
        )
