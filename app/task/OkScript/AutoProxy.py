#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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

"""OkScript 自动代理：以 ``-t <模块.类名> -e`` 启动 ok-script 项目并按框架日志判定结果。

任务按 ``模块.类名`` 指定而不是按列表序号：启动器可能在拉起项目前先自动更新，更新若调换了
``onetime_tasks`` 的顺序，启动前算出的序号会跑到别的任务上，而完成标记不带任务名，无法
事后识别（详见 ``project.py``）。

配置来源只有「直接使用项目原生配置」：运行前不下发、不覆盖任何任务配置，唯一的写入是
启动器 ``app.json`` 的 ``auto_start``（缺省才补，否则启动器停在自己的界面上不拉起项目，
与 Okww 相同）。

结果只取上游结果面（ok-script 框架日志，1.0.x 到 2.0.x 文案一致）：

- ``Successfully Executed Task, Exiting Game and App!``：一次性任务正常返回、且带 ``-e``
  时才会打出，是唯一的完成依据；
- ``<任务名> exception stopped``：任务抛异常中止 → 失败；
- ``TaskDisabledException, continue <任务对象>``：任务在项目界面里被停止 → 中止；
- 进程在完成标记前退出 → 失败；单次运行超过 ``Run.RunTimeLimit`` 分钟仍无完成标记 →
  结束进程树并判为无法确认完成（兜住会一直运行的任务与卡死的进程）。

进程退出码与日志最后一行都不作为完成依据。
"""

import asyncio
import time
import uuid
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from app.core import Config
from app.core.ws import Publisher, protocol
from app.models.config import OkScriptConfig, OkScriptUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.schema import WSTaskNoticeData
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase, UserItem
from app.services import Notify, System
from app.task.proxy_helpers import push_dispatch_log
from app.utils import ProcessInfo, ProcessManager, get_logger
from app.utils.constants import UTC4
from app.utils.io import read_dict_file, write_file
from app.utils.LogMonitor import LogMonitor

from .project import OkScriptProject, OkScriptTask
from .tools import push_notification

logger = get_logger("OkScript 自动代理")

# ok-script 框架日志（ok/task/TaskExecutor.py，1.0.190 与 2.0.x 一致）
OK_SCRIPT_SUCCESS_LOG = "Successfully Executed Task, Exiting Game and App!"
OK_SCRIPT_TASK_ERROR_LOG = "exception stopped"
OK_SCRIPT_TASK_STOPPED_LOG = "TaskDisabledException"
# ok-script 日志格式 ``%(asctime)s %(levelname)s %(threadName)s %(message)s``
_LOG_TIME_RANGE = (0, 23)
_LOG_TIME_FORMAT = "%Y-%m-%d %H:%M:%S,%f"
# 运行结果（写入 LogRecord.status；完成沿用全局统计认的 Success!）
SUCCESS_STATUS = "Success!"
MANUAL_STOP_STATUS = "任务被用户手动中止"
# 启动器可能先自动更新再拉起项目进程，给足等待时间
_TRACK_PROCESS_SECONDS = 300
# 项目进程退出后，再给日志监控读完最后几行留的时间
_EXIT_GRACE_SECONDS = 5
# 看到完成标记后等项目按 -e 自行关闭游戏与程序的上限（框架自身约需 10 秒）
_SELF_EXIT_SECONDS = 60
# 不依赖日志回调的兜底轮询间隔：日志文件一直不出现时回调不会触发
_WATCHDOG_SECONDS = 5


@dataclass(frozen=True)
class RunVerdict:
    """一次运行的判定结果。"""

    result: Literal["完成", "失败", "中止", "无法确认"]
    message: str

    @property
    def completed(self) -> bool:
        return self.result == "完成"


def judge_run(
    log_lines: Sequence[str],
    *,
    app_name: str,
    task: OkScriptTask,
    process_exited: bool,
    timed_out: bool,
    time_limit_minutes: int,
) -> RunVerdict | None:
    """按 ok-script 框架日志判定一次运行；仍在运行时返回 None。

    Args:
        log_lines: 本次运行开始后的日志行。
        app_name: 项目名，用于提示文案。
        task: 本次运行的任务。
        process_exited: 项目进程是否已退出（已扣除读日志的宽限时间）。
        timed_out: 本次运行是否已超过 ``time_limit_minutes`` 分钟。
        time_limit_minutes: 单次运行时间上限（分钟），用于提示文案。
    """

    class_name = task.task_id.rsplit(".", 1)[-1]
    error_markers = {
        f"{task.name} {OK_SCRIPT_TASK_ERROR_LOG}",
        f"{class_name} {OK_SCRIPT_TASK_ERROR_LOG}",
    }

    for line in log_lines:
        if OK_SCRIPT_SUCCESS_LOG in line:
            return RunVerdict("完成", SUCCESS_STATUS)
    for line in log_lines:
        if any(marker in line for marker in error_markers):
            detail = line[_LOG_TIME_RANGE[1] :].strip()[:200]
            return RunVerdict("失败", f"{app_name} 任务出错中止：{detail}")
        if OK_SCRIPT_TASK_STOPPED_LOG in line and task.task_id in line:
            return RunVerdict("中止", f"任务在 {app_name} 界面中被停止")
    if process_exited:
        return RunVerdict("失败", f"{app_name} 在任务完成前退出，日志中没有完成标记")
    if timed_out:
        return RunVerdict(
            "无法确认",
            f"{app_name} 运行超过 {time_limit_minutes} 分钟仍没有完成标记，"
            "已结束进程，无法确认任务是否完成",
        )
    return None


def ensure_launcher_auto_start(project: OkScriptProject) -> bool:
    """补齐启动器的自动启动设置（缺省才补、无事零写入）。

    pyappify 启动器关闭自动启动时只显示自己的界面，不会拉起项目，``-t/-e`` 也就不会
    生效。与 Okww 的启动器默认值补齐同口径，只动 ``auto_start`` 一项。

    Returns:
        bool: 是否写入了改动。
    """

    app_json = read_dict_file(project.app_json_path)
    if app_json.get("auto_start") is True:
        return False
    app_json["auto_start"] = True
    write_file(project.app_json_path, app_json)
    logger.info(f"已开启 {project.app_name} 启动器的自动启动")
    return True


async def kill_project_processes(
    project: OkScriptProject, process_manager: ProcessManager | None
) -> None:
    """结束本安装的全部项目进程（含子进程树）；每步独立，失败不阻断后续。

    只按本安装目录下的可执行文件路径结束，不碰其他安装。先按路径连树结束 Python
    与启动器，再收掉进程管理器里的句柄：若先结束被跟踪的 Python 进程，它的子进程
    会失去父进程，按树就找不到了。
    """

    for path in (
        project.python_dir / "pythonw.exe",
        project.python_dir / "python.exe",
        project.exe_path,
    ):
        try:
            await System.kill_process(path)
        except Exception as e:
            logger.opt(exception=True).warning(f"中止进程失败 ({path}): {e}")
    if process_manager is not None:
        try:
            await process_manager.kill()
        except Exception as e:
            logger.opt(exception=True).warning(f"通过进程管理器中止失败: {e}")


class AutoProxyTask(TaskExecuteBase):
    """OkScript 自动代理：一个用户一次一次性任务。"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: OkScriptConfig,
        user_config: MultipleConfig[OkScriptUserConfig],
        project: OkScriptProject,
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
        self.cur_user_config: OkScriptUserConfig = self.user_config[self.cur_user_uid]
        self.cur_user_log: LogRecord | None = None
        self.user_start_time = datetime.now()

        self.project = project
        self.task: OkScriptTask | None = None
        self.process_manager: ProcessManager | None = None
        self.launched_at = 0.0
        # 本次运行拉起项目时的单调时钟读数，单次运行时间上限从这里起算
        self.run_started_at = 0.0
        self.log_monitor: LogMonitor | None = None
        self.wait_event: asyncio.Event | None = None
        self.verdict: RunVerdict | None = None
        self.exit_seen_at: float | None = None
        self.run_book = False

    async def check(self) -> str:
        # 单独运行脚本是用户主动指定的一次性运行，不受单日代理次数上限约束
        if (
            self.task_info.is_queue_task
            and self.script_config.get("Run", "ProxyTimesLimit") != 0
            and self.cur_user_config.get("Data", "ProxyTimes")
            >= self.script_config.get("Run", "ProxyTimesLimit")
        ):
            self.cur_user_item.status = "跳过"
            return "今日代理次数已达上限, 跳过该用户"
        if self.cur_user_config.get("Info", "RemainedDay") == 0:
            self.cur_user_item.status = "跳过"
            return "用户剩余天数为 0, 跳过该用户"

        task_id = str(self.cur_user_config.get("Task", "TaskId") or "").strip()
        if not task_id:
            return "请先在用户配置中选择要运行的任务"
        task = self.project.find_task(task_id)
        if task is None:
            task_name = self.cur_user_config.get("Task", "TaskName") or task_id
            return (
                f"所选任务「{task_name}」在当前 {self.project.app_name} "
                f"{self.project.version} 中已不存在，请在用户配置中重新选择"
            )
        self.task = task
        return "Pass"

    async def main_task(self):
        if self.task is None:
            raise RuntimeError("OkScript 自动代理未通过检查")

        curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        if self.cur_user_config.get("Data", "LastProxyDate") != curdate:
            await self.cur_user_config.set("Data", "LastProxyDate", curdate)
            await self.cur_user_config.set("Data", "ProxyTimes", 0)
        # 显示名跟随项目当前版本（上游改名后标签同步）
        if self.cur_user_config.get("Task", "TaskName") != self.task.name:
            await self.cur_user_config.set("Task", "TaskName", self.task.name)

        app_name = self.project.app_name
        run_limit = int(self.script_config.get("Run", "RunTimesLimit"))
        for i in range(run_limit):
            logger.info(
                f"用户 {self.cur_user_item.name} - 尝试次数: {i + 1}/{run_limit}"
            )
            self.cur_user_item.status = "运行"
            self.log_start_time = datetime.now()
            self.cur_user_item.log_record[self.log_start_time] = LogRecord()
            self.cur_user_log = self.cur_user_item.log_record[self.log_start_time]
            self.cur_user_log.status = self._running_status
            self.script_info.log = ""
            self.verdict = None
            self.exit_seen_at = None

            await self._run_once()
            verdict = self.verdict
            if verdict is None:
                raise RuntimeError("OkScript 运行结束但没有判定结果")

            if verdict.completed:
                self.run_book = True
                self.script_info.log = (
                    f"检测到 {app_name} 已完成任务\n正在等待 {app_name} 自行退出"
                )
                await self._wait_self_exit()
                break

            logger.warning(
                f"用户 {self.cur_user_item.name} - {app_name} 代理未完成: {verdict.message}"
            )
            self.script_info.log = f"{verdict.message}\n正在中止相关程序"
            await self.kill_managed_process()
            with suppress(Exception):
                await Notify.push_plyer(
                    f"{app_name} 自动代理出现异常！",
                    f"用户 {self.cur_user_item.name}：{verdict.message}",
                    f"{self.cur_user_item.name}的自动代理出现异常",
                    3,
                )
            # 在项目界面里被停止是用户的决定，不重试
            if verdict.result == "中止":
                break
            if i + 1 < run_limit:
                self.script_info.log += f"\n将在稍后重试 ({i + 1}/{run_limit})"
                await asyncio.sleep(10)

    @property
    def _running_status(self) -> str:
        return f"{self.project.app_name} 正常运行中"

    async def _run_once(self) -> None:
        """启动一次项目并等到判定结果（结果写在 self.verdict）。"""

        project = self.project
        task = self.task
        await self.kill_managed_process()
        try:
            ensure_launcher_auto_start(project)
        except Exception as e:
            logger.opt(exception=True).warning(f"补齐启动器设置失败: {e}")
            self._set_verdict(
                RunVerdict("失败", f"无法写入 {project.app_name} 启动器设置：{e}")
            )
            return

        # 按「模块.类名」指定任务，不传列表序号（见模块说明）
        args = ["-t", task.task_id, "-e"]
        await push_dispatch_log(
            self.script_info,
            f"启动 {project.app_name}：{task.name}（-t {task.task_id} -e）",
        )
        logger.info(f"启动 {project.app_name}: {project.exe_path} {' '.join(args)}")

        self.process_manager = ProcessManager()
        launched_at = time.time()
        try:
            await self.process_manager.open_process(project.exe_path, *args)
            self.run_started_at = time.monotonic()
        except Exception as e:
            logger.opt(exception=True).warning(f"启动 {project.app_name} 失败: {e}")
            self._set_verdict(RunVerdict("失败", f"启动 {project.app_name} 失败：{e}"))
            return

        if not await self._track_project_process(launched_at):
            self._set_verdict(
                RunVerdict(
                    "失败",
                    f"{_TRACK_PROCESS_SECONDS // 60} 分钟内没有等到 {project.app_name} "
                    "启动，请打开它的界面确认能否正常运行",
                )
            )
            return

        self.wait_event = asyncio.Event()
        self.log_monitor = LogMonitor(_LOG_TIME_RANGE, _LOG_TIME_FORMAT, self.check_log)
        await self.log_monitor.start_monitor_file(
            lambda: project.log_path, self.log_start_time
        )
        try:
            while self.verdict is None:
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        self.wait_event.wait(), timeout=_WATCHDOG_SECONDS
                    )
                if self.verdict is None:
                    await self._evaluate(
                        self.log_monitor.log_contents, self.log_monitor.latest_time
                    )
        finally:
            await self.log_monitor.stop()

    async def _track_project_process(self, launched_at: float) -> bool:
        """找到启动器拉起的项目 Python 进程并改为跟踪它。"""

        self.launched_at = launched_at
        deadline = time.monotonic() + _TRACK_PROCESS_SECONDS
        while time.monotonic() < deadline:
            if await self._track_once(0.5):
                return True
        return False

    async def _track_once(self, timeout: float) -> bool:
        """在本安装的运行时里找一个本次启动后出现、仍存活的 Python 进程并跟踪它。

        启动器更新依赖时也会短暂运行同一目录下的 python.exe，被跟踪的进程退出后
        先重找一次，避免把「依赖安装结束」误当成项目退出。
        """

        python_dir = self.project.python_dir
        for candidate in (
            ProcessInfo(exe=str(python_dir / "pythonw.exe")),
            ProcessInfo(exe=str(python_dir / "python.exe")),
        ):
            try:
                await self.process_manager.search_process(
                    candidate, timeout, min_create_time=self.launched_at
                )
            except RuntimeError:
                continue
            return True
        return False

    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """LogMonitor 回调：同步调度台日志并判定结果。"""

        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log[-4000:] if len(log) > 4000 else log
        await self._evaluate(log_content, latest_time)

    async def _evaluate(self, log_content: list[str], latest_time: datetime) -> None:
        if self.verdict is not None or self.process_manager is None:
            return

        if await self.process_manager.is_running() or await self._track_once(0.2):
            self.exit_seen_at = None
        elif self.exit_seen_at is None:
            self.exit_seen_at = time.monotonic()
        process_exited = (
            self.exit_seen_at is not None
            and time.monotonic() - self.exit_seen_at >= _EXIT_GRACE_SECONDS
        )
        time_limit = int(self.script_config.get("Run", "RunTimeLimit"))
        verdict = judge_run(
            log_content,
            app_name=self.project.app_name,
            task=self.task,
            process_exited=process_exited,
            timed_out=time.monotonic() - self.run_started_at > time_limit * 60,
            time_limit_minutes=time_limit,
        )
        if verdict is not None:
            self._set_verdict(verdict)

    def _set_verdict(self, verdict: RunVerdict) -> None:
        self.verdict = verdict
        self.cur_user_log.status = verdict.message
        self.cur_user_item.status = "完成" if verdict.completed else "异常"
        logger.info(f"OkScript 任务结果: {verdict.result} - {verdict.message}")
        if self.wait_event is not None:
            self.wait_event.set()

    async def _wait_self_exit(self) -> None:
        """等项目按 -e 自行退出，超时兜底强杀。"""

        deadline = time.monotonic() + _SELF_EXIT_SECONDS
        while time.monotonic() < deadline:
            if not await self.process_manager.is_running():
                logger.info(f"{self.project.app_name} 已自行退出")
                return
            await asyncio.sleep(1)
        logger.warning(
            f"{self.project.app_name} 未在 {_SELF_EXIT_SECONDS}s 内自行退出，兜底强杀"
        )
        await self.kill_managed_process()

    async def kill_managed_process(self) -> None:
        await kill_project_processes(self.project, self.process_manager)

    async def final_task(self):
        if self.log_monitor is not None:
            with suppress(Exception):
                await self.log_monitor.stop()
        await self.kill_managed_process()

        # 写入历史记录（对齐 Okww / General）
        statistic_paths: list[Path] = []
        for t, log_item in self.cur_user_item.log_record.items():
            dt = t.astimezone(UTC4)
            log_path = Config.build_history_log_path(
                script_name=self.script_info.name,
                user_name=self.cur_user_item.name,
                log_time=dt,
            )
            if log_item.status == self._running_status:
                log_item.status = MANUAL_STOP_STATUS
            if not log_item.content:
                log_item.content = [log_item.status]
            await Config.save_general_log(log_path, log_item.content, log_item.status)
            statistic_paths.append(log_path.with_suffix(".json"))

        if statistic_paths:
            app_name = self.project.app_name
            try:
                statistics = await Config.merge_statistic_info(statistic_paths)
                statistics["user_info"] = self.cur_user_item.name
                statistics["start_time"] = self.user_start_time.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                statistics["user_result"] = (
                    "代理任务全部完成" if self.run_book else self.cur_user_item.result
                )
                success_symbol = "√" if self.run_book else "X"
                await push_notification(
                    "统计信息",
                    f"{datetime.now().strftime('%m-%d')} |{success_symbol}|  "
                    f"{self.cur_user_item.name} 的 {app_name} 自动代理统计报告",
                    statistics,
                    self.cur_user_config,
                )
            except Exception as e:
                logger.opt(exception=True).warning(f"推送用户统计通知时出现异常: {e}")

        await self._persist_user_run_result()

    async def _persist_user_run_result(self) -> None:
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
            logger.success(f"用户 {self.cur_user_uid} 的 OkScript 自动代理任务已完成")
        else:
            await self.cur_user_config.set("Data", "LastProxyStatus", "失败")
            if self.cur_user_item.status != "完成":
                self.cur_user_item.status = "异常"

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        if self.cur_user_log is not None:
            self.cur_user_log.status = f"OkScript 运行异常: {e}"
        logger.opt(exception=True).warning(f"OkScript 自动代理任务出现异常: {e}")
        if self.wait_event is not None:
            self.wait_event.set()
        with suppress(Exception):
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="error", message=f"OkScript 自动代理任务出现异常: {e}"
                ),
            )
        with suppress(Exception):
            await self.kill_managed_process()
