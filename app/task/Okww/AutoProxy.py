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
import shlex
import shutil
import uuid
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path

import psutil

from app.core import Config
from app.models.task import TaskExecuteBase, ScriptItem, UserItem, LogRecord
from app.models.ConfigBase import MultipleConfig
from app.models.config import OkwwConfig, OkwwUserConfig
from app.services import Notify, System
from app.utils import get_logger, ProcessManager, ProcessInfo
from app.utils.LogMonitor import LogMonitor
from app.utils.constants import UTC4

logger = get_logger("OK-WW 自动代理")

# 鸣潮 PC 客户端窗口进程名固定，MAS 接管启动前据此避免重复拉起
_WUWA_CLIENT_PROCESS = "Client-Win64-Shipping.exe"


def _wuthering_waves_client_running() -> bool:
    for proc in psutil.process_iter(["name"]):
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            if proc.info.get("name") == _WUWA_CLIENT_PROCESS:
                return True
    return False


def _yes_no(value: bool) -> str:
    return "是" if value else "否"

# 对齐 MaaEnd：专项内置致命日志片段（非用户 Success/Error 配置）；`Script.ErrorLog` 仅追加补充子串
_OKWW_BUILTIN_FATAL: tuple[tuple[str, str], ...] = (
    ("connected:False", "OK-WW 未连接游戏客户端"),
    ("游戏更新成功, 游戏即将重启", "游戏更新成功，即将重启任务"),
    ("失败", "OK-WW 任务失败"),
)

# prepare 中 ErrorLog 经清洗后为空时回退（与 OkwwConfig 默认串一致）
_DEFAULT_OKWW_ERROR_LOG = "connected:False|游戏更新成功, 游戏即将重启|错误"

def _sanitize_okww_error_log_tokens(tokens: list[str]) -> list[str]:
    return [t for raw in tokens if (t := raw.strip())]


def _okww_log_indicates_success(log: str, success_log: list[str]) -> bool:
    if "任务执行完成" in log or "task completed" in log.lower():
        return True
    return any(k in log for k in success_log if k)


class AutoProxyTask(TaskExecuteBase):
    """OK-WW 自动代理：拼 `-t N -e` 启动参数并监控日志"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: OkwwConfig,
        user_config: MultipleConfig[OkwwUserConfig],
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

        self.cur_user_item: UserItem = self.script_info.user_list[self.script_info.current_index]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config: OkwwUserConfig | None = None

    async def check(self) -> str:
        if not Path(self.script_config.get("Info", "RootPath")).exists():
            return "OK-WW 根目录不存在，请检查脚本根目录"
        if not Path(self.script_config.get("Script", "ScriptPath")).exists():
            return "OK-WW 可执行文件不存在，请检查主程序路径"
        return "Pass"

    async def prepare(self):
        self.okww_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()

        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now()

        self.script_root_path = Path(self.script_config.get("Info", "RootPath"))
        self.script_exe_path = Path(self.script_config.get("Script", "ScriptPath"))
        self.script_target_process_info: ProcessInfo | None = None
        if self.script_config.get("Script", "IfTrackProcess"):
            track_name = self.script_config.get("Script", "TrackProcessName") or "pythonw.exe"
            track_exe = self.script_config.get("Script", "TrackProcessExe") or ""
            if not track_exe:
                track_exe = str(
                    self.script_root_path / "data/apps/ok-ww/python/pythonw.exe"
                )
            track_cmdline = (
                shlex.split(
                    self.script_config.get("Script", "TrackProcessCmdline"), posix=False
                )
                or None
            )
            self.script_target_process_info = ProcessInfo(
                name=track_name or None,
                exe=track_exe or None,
                cmdline=track_cmdline,
            )

        self.script_log_path = Path(self.script_config.get("Script", "LogPath"))
        self.log_format = self.script_config.get("Script", "LogPathFormat") or ""
        if self.log_format:
            with suppress(ValueError):
                datetime.strptime(self.script_log_path.stem, self.log_format)
                self.log_format = f"{self.log_format}{self.script_log_path.suffix}"
        else:
            self.log_format = self.script_log_path.name

        self.log_time_range = (
            self.script_config.get("Script", "LogTimeStart") - 1,
            self.script_config.get("Script", "LogTimeEnd"),
        )
        self.log_time_format = self.script_config.get("Script", "LogTimeFormat")
        self.log_monitor = LogMonitor(
            self.log_time_range,
            self.log_time_format,
            self.check_log,
        )
        self.success_log = [
            _.strip()
            for _ in str(self.script_config.get("Script", "SuccessLog")).split("|")
            if _.strip()
        ]
        raw_error_tokens = [
            _.strip()
            for _ in str(self.script_config.get("Script", "ErrorLog")).split("|")
            if _.strip()
        ]
        self.error_log = _sanitize_okww_error_log_tokens(raw_error_tokens)
        if not self.error_log:
            self.error_log = [
                _.strip()
                for _ in _DEFAULT_OKWW_ERROR_LOG.split("|")
                if _.strip()
            ]
            logger.warning(
                "OK-WW ErrorLog 去掉过宽容词后为空，已回退为内置默认失败关键词"
            )

        # 当前用户配置
        self.cur_user_config = self.user_config[self.cur_user_uid]

        self.task_index = int(self.cur_user_config.get("Task", "TaskIndex"))
        self.exit_on_finish = bool(self.cur_user_config.get("Task", "ExitOnFinish"))

        extra_args = []
        raw_extra = str(self.script_config.get("Script", "Arguments")).strip()
        if raw_extra:
            extra_args.extend(shlex.split(raw_extra, posix=False))

        self.okww_args = ["-t", str(self.task_index)]
        if self.exit_on_finish:
            self.okww_args.append("-e")
        self.okww_args.extend(extra_args)

        # 游戏配置（对齐通用脚本逻辑）
        self.game_path = Path(self.script_config.get("Game", "Path"))
        self.game_url = self.script_config.get("Game", "URL")
        self.game_process_name = self.script_config.get("Game", "ProcessName")
        self.script_config_path = Path(self.script_config.get("Script", "ConfigPath"))

        self.run_book = False

    def _okww_mas_config_dir(self) -> Path:
        mode = str(self.cur_user_config.get("Info", "Mode") or "简洁")
        config_owner = (
            "Default" if mode == "简洁" else str(self.cur_user_uid)
        )
        return Path.cwd() / f"data/{self.script_info.script_id}/{config_owner}/ConfigFile"

    async def set_okww(self) -> None:
        """将 MAS 侧 OK-WW 任务配置下发到脚本 working 目录（对齐 General.set_general）。"""

        logger.info("开始配置 OK-WW 运行参数: 自动代理")
        await System.kill_process(self.script_exe_path)

        mas_config_dir = self._okww_mas_config_dir()
        if self.script_config.get("Script", "ConfigPathMode") == "Folder":
            tmp_dst = self.script_config_path.with_name(
                self.script_config_path.name + ".tmp"
            )
            shutil.rmtree(tmp_dst, ignore_errors=True)
            shutil.copytree(mas_config_dir, tmp_dst, dirs_exist_ok=True)
            shutil.rmtree(self.script_config_path, ignore_errors=True)
            tmp_dst.rename(self.script_config_path)
        elif self.script_config.get("Script", "ConfigPathMode") == "File":
            shutil.copy(
                mas_config_dir / self.script_config_path.name,
                self.script_config_path,
            )
        logger.info(f"OK-WW 运行参数配置完成: 自动代理")

    async def update_config(self) -> None:
        """将脚本侧配置回写 MAS ConfigFile（对齐 General.update_config）。"""

        mas_config_dir = self._okww_mas_config_dir()
        if self.script_config.get("Script", "ConfigPathMode") == "Folder":
            shutil.copytree(
                self.script_config_path, mas_config_dir, dirs_exist_ok=True
            )
        elif self.script_config.get("Script", "ConfigPathMode") == "File":
            shutil.copy(
                self.script_config_path,
                mas_config_dir / self.script_config_path.name,
            )
        logger.success("OK-WW 配置文件已更新")

    def _game_config_summary_lines(self) -> list[str]:
        """游戏配置摘要行（调度台展示用）。"""

        game_args = str(self.script_config.get("Game", "Arguments") or "").strip()
        return [
            f"[游戏配置] 用户: {self.cur_user_item.name}",
            f"  启用游戏配置: {_yes_no(bool(self.script_config.get('Game', 'Enabled')))}",
            f"  任务前启动游戏: {_yes_no(bool(self.script_config.get('Game', 'LaunchBeforeTask')))}",
            f"  任务后关闭游戏: {_yes_no(bool(self.script_config.get('Game', 'CloseOnFinish')))}",
            f"  启动参数: {game_args or '（无）'}",
        ]

    async def _push_dispatch_log(self, line: str) -> None:
        """向调度台追加流程日志（赋值 script_info.log 会触发 WebSocket 推送）。"""

        prev = self.script_info.log
        self.script_info.log = f"{prev}\n{line}" if prev else line
        await asyncio.sleep(0)

    async def _log_game_config_summary(self) -> None:
        """在调度台开头输出当前脚本的游戏相关配置，便于用户确认与问题排查。"""

        self.script_info.log = "\n".join(self._game_config_summary_lines())
        await asyncio.sleep(0)

    async def _mas_launch_game_before_task(self) -> None:
        """MAS 接管启动游戏，并将各步骤写入调度台日志。"""

        game_type = self.script_config.get("Game", "Type")
        await self._push_dispatch_log("正在准备由 MAS 启动游戏...")

        if isinstance(self.game_manager, ProcessManager) and game_type == "Client":
            await self._push_dispatch_log(
                f"正在检查鸣潮客户端进程 ({_WUWA_CLIENT_PROCESS})..."
            )
            if _wuthering_waves_client_running():
                logger.info(
                    "检测到鸣潮客户端进程已在运行，跳过由 MAS 重复启动游戏"
                )
                await self._push_dispatch_log("检测到客户端已在运行，跳过启动")
                return

            await self._push_dispatch_log("未检测到运行中的客户端，正在拉起游戏...")
            await self.game_manager.open_process(
                self.game_path,
                *str(self.script_config.get("Game", "Arguments")).split(" "),
            )
            wait_time = int(self.script_config.get("Game", "WaitTime"))
            await self._push_dispatch_log(
                f"正在等待游戏完成启动（{wait_time}s）..."
            )
            await asyncio.sleep(wait_time)
            await self._push_dispatch_log("游戏启动完成")
            return

        if isinstance(self.game_manager, ProcessManager) and game_type == "URL":
            await self._push_dispatch_log("正在通过 URL 协议启动游戏...")
            await self.game_manager.open_protocol(
                self.game_url,
                ProcessInfo(name=self.game_process_name or None),
            )
            await asyncio.sleep(2)
            await self._push_dispatch_log("游戏启动指令已发送")
            return

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

            await self._log_game_config_summary()

            # 总开关开启且勾选「任务前启动」时由 MAS 拉起游戏
            if (
                self.script_config.get("Game", "Enabled")
                and self.script_config.get("Game", "LaunchBeforeTask")
                and self.game_manager is not None
            ):
                try:
                    await self._mas_launch_game_before_task()
                except Exception as e:
                    await self._push_dispatch_log(f"游戏启动失败: {e}")
                    self.cur_user_log.status = f"游戏启动失败: {e}"
                    self.cur_user_log.content = [f"游戏启动失败: {e}"]
                    await Config.send_websocket_message(
                        id=self.task_info.task_id,
                        type="Info",
                        data={"Error": f"游戏启动失败: {e}"},
                    )
                    await self.kill_managed_process(
                        kill_game=self._mas_should_close_game_on_retry()
                    )
                    try:
                        await Notify.push_plyer(
                            "OK-WW 自动代理出现异常！",
                            f"用户 {self.cur_user_item.name} 游戏启动失败",
                            f"{self.cur_user_item.name}的自动代理出现异常",
                            3,
                        )
                    except Exception:
                        pass
                    if i + 1 < run_limit:
                        await self._push_dispatch_log(
                            f"游戏启动失败，将在稍后重试 ({i + 1}/{run_limit})"
                        )
                        await asyncio.sleep(10)
                    else:
                        self.cur_user_item.status = "异常"
                    continue

            await self.set_okww()
            await self._push_dispatch_log(
                f"启动 OK-WW: -t {self.task_index}"
                + (" -e" if self.exit_on_finish else "")
            )
            logger.info(
                f"启动 OK-WW 进程: {self.script_exe_path} {' '.join(self.okww_args)}"
            )

            await self.okww_process_manager.open_process(
                self.script_exe_path,
                *self.okww_args,
                target_process=self.script_target_process_info,
            )

            # 启动日志监控（文件日志）
            await asyncio.sleep(1)
            await self.log_monitor.start_monitor_file(
                self._resolve_log_path(), self.log_start_time
            )

            self.wait_event.clear()
            await self.wait_event.wait()
            await self.log_monitor.stop()

            if self.cur_user_log.status == "Success!":
                self.run_book = True
                self.script_info.log = (
                    "检测到 OK-WW 已完成任务\n正在等待相关进程结束"
                )
                # 对齐 MaaEnd：成功时先只结束 ok-ww；是否关游戏由 Game.CloseOnFinish 在 final_task 决定
                await self._kill_okww_process()
                if self.script_config.get("Script", "UpdateConfigMode") in (
                    "Success",
                    "Always",
                ):
                    await self.update_config()
                await asyncio.sleep(3)
                break

            logger.error(
                f"用户 {self.cur_user_item.name} - OK-WW 代理异常: {self.cur_user_log.status}"
            )
            self.script_info.log = (
                f"{self.cur_user_log.status}\n正在中止相关程序"
            )
            await self.kill_managed_process(
                kill_game=self._mas_should_close_game_on_retry()
            )
            try:
                await Notify.push_plyer(
                    "OK-WW 自动代理出现异常！",
                    f"用户 {self.cur_user_item.name} 的自动代理出现一次异常",
                    f"{self.cur_user_item.name}的自动代理出现异常",
                    3,
                )
            except Exception:
                pass
            if self.script_config.get("Script", "UpdateConfigMode") in (
                "Failure",
                "Always",
            ):
                await self.update_config()
            if i + 1 < run_limit:
                self.script_info.log += (
                    f"\n将在稍后重试 ({i + 1}/{run_limit})"
                )
                await asyncio.sleep(10)

    def _game_management_enabled(self) -> bool:
        return bool(self.script_config.get("Game", "Enabled"))

    def _mas_should_close_game_after_success(self) -> bool:
        return self._game_management_enabled() and bool(
            self.script_config.get("Game", "CloseOnFinish")
        )

    def _mas_should_close_game_on_retry(self) -> bool:
        """失败/重试/启动游戏失败：总开关开启且任一生周期子项启用时结束游戏"""
        return self._game_management_enabled() and bool(
            self.script_config.get("Game", "LaunchBeforeTask")
            or self.script_config.get("Game", "CloseOnFinish")
        )

    def _resolve_log_path(self) -> Path:
        # 若用户给了带日期模板的日志路径，则按启动时间格式化文件名
        if self.log_format and self.script_log_path.name != self.log_format:
            try:
                filename = self.log_start_time.strftime(self.log_format)
                return self.script_log_path.with_name(filename)
            except Exception:
                return self.script_log_path
        return self.script_log_path

    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """与 MaaEnd 类似：内置致命片段优先，再读配置补充；成功；进程结束；超时；否则为运行中。

        `Script.ErrorLog` / `SuccessLog` 仅在 AutoProxy.prepare → 本回调中使用，全仓无第二处运行时判据，
        避免「配置一套、代码另一套」的分裂；内置项保证未改配置时也有基线行为。
        """
        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log[-4000:] if len(log) > 4000 else log

        log_status = "OK-WW 正常运行中"
        user_item_status: str | None = None

        for needle, msg in _OKWW_BUILTIN_FATAL:
            if needle in log:
                log_status = msg
                user_item_status = "异常"
                break
        else:
            for k in self.error_log:
                if k and k in log:
                    log_status = f"OK-WW：{k}"
                    user_item_status = "异常"
                    break
            else:
                if _okww_log_indicates_success(log, self.success_log):
                    log_status = "Success!"
                    user_item_status = "完成"
                elif not await self.okww_process_manager.is_running():
                    log_status = "OK-WW 在完成任务前退出"
                    user_item_status = "异常"
                elif datetime.now() - latest_time > timedelta(
                    minutes=self.script_config.get("Run", "RunTimeLimit")
                ):
                    log_status = "OK-WW 运行超时"
                    user_item_status = "异常"

        self.cur_user_log.status = log_status
        if user_item_status is not None:
            self.cur_user_item.status = user_item_status

        logger.debug(f"OK-WW 日志分析结果: {self.cur_user_log.status}")
        if self.cur_user_log.status != "OK-WW 正常运行中":
            logger.info(f"OK-WW 任务结果: {self.cur_user_log.status}, 日志锁已释放")
            self.wait_event.set()

    async def final_task(self):
        # 结束时先清理进程与监控
        with suppress(Exception):
            await self.log_monitor.stop()
        if self.run_book and not self._mas_should_close_game_after_success():
            await self._kill_okww_process()
        else:
            kill_game = (
                self._mas_should_close_game_after_success()
                if self.run_book
                else self._mas_should_close_game_on_retry()
            )
            await self.kill_managed_process(kill_game=kill_game)

        # 写入历史记录（对齐 General/SRC/MaaEnd 行为）
        for t, log_item in self.cur_user_item.log_record.items():
            dt = t.replace(tzinfo=datetime.now().astimezone().tzinfo).astimezone(UTC4)
            log_path = (
                Path.cwd()
                / f"history/{dt.strftime('%Y-%m-%d')}/{self.cur_user_item.name}/{dt.strftime('%H-%M-%S')}.log"
            )

            if log_item.status == "OK-WW 正常运行中":
                log_item.status = "任务被用户手动中止"

            if len(log_item.content) == 0:
                log_item.content = ["未捕获到任何日志内容"]
                log_item.status = "未捕获到日志"

            await Config.save_general_log(log_path, log_item.content, log_item.status)

        await self._persist_user_run_result()

    async def _persist_user_run_result(self) -> None:
        if self.cur_user_config is None:
            return

        await self.cur_user_config.set("Data", "LastTaskIndex", getattr(self, "task_index", 0))
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
            logger.success(f"用户 {self.cur_user_uid} 的 OK-WW 自动代理任务已完成")
        else:
            await self.cur_user_config.set("Data", "LastProxyStatus", "失败")
            if self.cur_user_item.status != "完成":
                self.cur_user_item.status = "异常"

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        if hasattr(self, "cur_user_log"):
            self.cur_user_log.status = f"OK-WW 运行异常: {e}"
        logger.exception(f"OK-WW 自动代理任务出现异常: {e}")
        if hasattr(self, "wait_event"):
            self.wait_event.set()
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"OK-WW 自动代理任务出现异常: {e}"},
        )
        await self.kill_managed_process(
            kill_game=self._mas_should_close_game_on_retry()
        )
        await self._persist_user_run_result()

        # 推送通知（复用 Notify）
        try:
            if (
                hasattr(self, "cur_user_log")
                and self.cur_user_log.status
                and self.cur_user_log.status != "Success!"
            ):
                await Notify.push_plyer(
                    "OK-WW 运行异常",
                    f"用户 {self.cur_user_item.name}：{self.cur_user_log.status}",
                    "异常",
                    3,
                )
        except Exception:
            pass

    async def _kill_okww_process(self) -> None:
        try:
            await self.okww_process_manager.kill()
            await System.kill_process(self.script_exe_path)
        except Exception:
            pass

    async def _kill_game_process(self) -> None:
        """结束游戏：不依赖 LaunchBeforeTask（可自行开游戏，由 CloseOnFinish/失败重试触发）"""
        game_type = self.script_config.get("Game", "Type")
        try:
            if isinstance(self.game_manager, ProcessManager):
                await self.game_manager.kill()
            if game_type == "Client":
                gp = self.game_path
                if gp.is_file():
                    await System.kill_process(gp)
        except Exception:
            pass

    async def kill_managed_process(self, *, kill_game: bool = True) -> None:
        """中止 ok-ww；kill_game 为真时结束游戏（失败重试恒为真；成功收尾看 CloseOnFinish）"""
        await self._kill_okww_process()
        if kill_game:
            await self._kill_game_process()

