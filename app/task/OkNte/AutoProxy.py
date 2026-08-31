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

import ast
import asyncio
import json
import re
import shlex
import shutil
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from app.core import Config
from app.core.ws import Publisher, protocol
from app.models.schema import WSTaskNoticeData
from app.models.task import TaskExecuteBase, ScriptItem, UserItem, LogRecord
from app.models.ConfigBase import MultipleConfig
from app.models.config import OkNteConfig, OkNteUserConfig
from app.services import Notify, System
from app.utils import get_logger, ProcessManager, ProcessInfo, is_process_running
from app.utils.io import read_file
from app.utils.LogMonitor import LogMonitor
from app.utils.LogPatternExtractor import (
    SIGN_MODE_SPLIT,
    LogSignMatcher,
    compile_log_signs,
)
from app.utils.constants import UTC4
from app.task.general.tools import execute_script_task
from app.log_box import LogType, log_box
from .config_schema import (
    DAILY_ROUTINE_TASK_FILE,
    LEGACY_DAILY_TASK_FILE,
    ensure_oknte_daily_routine_configs,
)
from .push_log import OKNTE_PUSH_RULES, oknte_resolve
from .tools import push_notification

logger = get_logger("OK-NTE 自动代理")

# 异环 PC 客户端进程名固定，MAS 接管启动前据此避免重复拉起
_NTE_CLIENT_PROCESS = "HTGame.exe"
_NTE_LAUNCHER_RELATIVE_PATH = Path("Neverness To Everness/NTELauncher/NTEGame.exe")


def _load_nte_launcher_path(config_path: Path) -> Path | None:
    launcher_config_path = (
        config_path / "LauncherTask.json" if config_path.is_dir() else config_path
    )
    config = read_file(launcher_config_path)
    if not isinstance(config, dict):
        return None

    launcher_path = Path(str(config.get("Launcher Path") or "").strip())
    expected_parts = tuple(
        part.casefold() for part in _NTE_LAUNCHER_RELATIVE_PATH.parts
    )
    actual_parts = tuple(
        part.casefold() for part in launcher_path.parts[-len(expected_parts) :]
    )
    if not launcher_path.is_absolute() or actual_parts != expected_parts:
        return None
    return launcher_path


def _yes_no(value: bool) -> str:
    return "是" if value else "否"


# 对齐 MaaEnd：专项内置致命日志片段（非用户 Success/Error 配置）；`Script.ErrorLog` 仅追加补充子串
_OKNTE_BUILTIN_FATAL: tuple[tuple[str, str], ...] = (
    ("connected:False", "OK-NTE 未连接游戏客户端"),
    ("Resolution Error", "OK-NTE 游戏分辨率不符合要求"),
    ("Timed out waiting for game process", "OK-NTE 等待游戏进程超时"),
    ("Timed out waiting for launcher process", "OK-NTE 等待启动器进程超时"),
)

# prepare 中 ErrorLog 经清洗后为空时回退（与 OkNteConfig 默认串一致）
_DEFAULT_OKNTE_ERROR_LOG = (
    "connected:False|Resolution Error|Timed out waiting for game process|"
    "Timed out waiting for launcher process"
)

_OKNTE_DAILY_TASK_INDEX = 2
_OKNTE_DAILY_LEGACY_ACTIVITY_KEY = "完成每日活跃度"
_OKNTE_DAILY_LEGACY_REQUIRED_SUCCESS = "完成每日活跃度"
_OKNTE_DAILY_ROUTINE_ACTIVITY_IDS = ("daily_anomaly", "daily_anomaly_hunter")
_OKNTE_DAILY_ROUTINE_CLAIM_SUCCESS = ("日常领取", "Daily Claim")
_OKNTE_DAILY_LEGACY_SUCCESS_RE = re.compile(
    r"DailyTask:info_set success\s*(?P<success>\[[^\r\n]*\])"
)
_OKNTE_DAILY_ROUTINE_SUCCESS_RE = re.compile(
    r"DailyRoutineTask:info_set success\s*(?P<success>\[[^\r\n]*\])"
)


def _split_args(raw: object) -> list[str]:
    value = str(raw or "").strip()
    return shlex.split(value, posix=False) if value else []


def _oknte_log_indicates_success(log: str, success_log: LogSignMatcher) -> bool:
    if (
        "Successfully Executed Task" in log
        or "任务执行完成" in log
        or "task completed" in log.lower()
    ):
        return True
    return success_log.search(log) is not None


def _parse_oknte_info_list(raw: str) -> list[str]:
    try:
        value = ast.literal_eval(raw)
        if isinstance(value, list):
            return [str(item) for item in value]
    except Exception:
        pass

    return [
        item.strip().strip("'\"") for item in raw.strip("[]").split(",") if item.strip()
    ]


def _oknte_daily_activity_enabled(config_dir: Path) -> bool:
    routine_path = config_dir / DAILY_ROUTINE_TASK_FILE
    if routine_path.is_file():
        try:
            data = json.loads(routine_path.read_text(encoding="utf-8"))
        except Exception:
            return True

        items = data.get("Routine Items") if isinstance(data, dict) else None
        if isinstance(items, list):
            return any(
                isinstance(item, dict)
                and item.get("id") in _OKNTE_DAILY_ROUTINE_ACTIVITY_IDS
                and bool(item.get("enabled"))
                for item in items
            )
        return True

    legacy_path = config_dir / LEGACY_DAILY_TASK_FILE
    if legacy_path.is_file():
        try:
            data = json.loads(legacy_path.read_text(encoding="utf-8"))
        except Exception:
            return True
        if isinstance(data, dict) and _OKNTE_DAILY_LEGACY_ACTIVITY_KEY in data:
            return bool(data[_OKNTE_DAILY_LEGACY_ACTIVITY_KEY])

    return True


def _oknte_daily_task_success_error(
    log: str,
    *,
    daily_activity_required: bool,
) -> str | None:
    routine_success_matches = _OKNTE_DAILY_ROUTINE_SUCCESS_RE.findall(log)
    if routine_success_matches:
        success_items = _parse_oknte_info_list(routine_success_matches[-1])
        if any(
            required in success_items for required in _OKNTE_DAILY_ROUTINE_CLAIM_SUCCESS
        ):
            return None
        return "OK-NTE 日常任务未完成日常领取"

    if not daily_activity_required:
        return None

    legacy_success_matches = _OKNTE_DAILY_LEGACY_SUCCESS_RE.findall(log)
    if not legacy_success_matches:
        return "OK-NTE 日常任务未确认完成每日活跃度"

    legacy_success_items = _parse_oknte_info_list(legacy_success_matches[-1])
    if _OKNTE_DAILY_LEGACY_REQUIRED_SUCCESS not in legacy_success_items:
        return "OK-NTE 日常任务未完成每日活跃度"
    return None


class AutoProxyTask(TaskExecuteBase):
    """OK-NTE 自动代理：拼 `-t N -e` 启动参数并监控日志"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: OkNteConfig,
        user_config: MultipleConfig[OkNteUserConfig],
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

        self.cur_user_item: UserItem = self.script_info.user_list[
            self.script_info.current_index
        ]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config: OkNteUserConfig = self.user_config[self.cur_user_uid]
        self.curdate = ""
        self.user_run_result_persisted = False
        self.daily_activity_required = True
        # log_box：用户级「是否采集节点详情」关闭时不创建（prepare 按配置启停）
        self.log_collect = None

    async def _reset_daily_proxy_count(self) -> None:
        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        if self.cur_user_config.get("Data", "LastProxyDate") != self.curdate:
            await self.cur_user_config.set("Data", "LastProxyDate", self.curdate)
            await self.cur_user_config.set("Data", "ProxyTimes", 0)

    async def check(self) -> str:
        if not Path(self.script_config.get("Info", "RootPath")).is_dir():
            return "请设置 OK-NTE 脚本路径"
        if not Path(self.script_config.get("Script", "ScriptPath")).is_file():
            return "请设置 OK-NTE 脚本路径"

        await self._reset_daily_proxy_count()
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

        if (
            self.script_config.get("Game", "Enabled")
            and self.script_config.get("Game", "Type") == "Client"
            and not Path(self.script_config.get("Game", "Path")).is_file()
        ):
            return "请设置异环游戏路径"
        if (
            self.script_config.get("Game", "Enabled")
            and self.script_config.get("Game", "Type") == "URL"
            and self.script_config.get("Game", "LaunchBeforeTask")
        ):
            if not str(self.script_config.get("Game", "URL") or "").strip():
                return "请设置异环游戏 URL"
            if not str(self.script_config.get("Game", "ProcessName") or "").strip():
                return "请设置异环游戏进程名称"
        return "Pass"

    async def prepare(self):
        self.oknte_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()

        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now()

        self.script_root_path = Path(self.script_config.get("Info", "RootPath"))
        self.script_exe_path = Path(self.script_config.get("Script", "ScriptPath"))
        self.script_target_process_info: ProcessInfo | None = None
        if self.script_config.get("Script", "IfTrackProcess"):
            track_name = (
                self.script_config.get("Script", "TrackProcessName") or "pythonw.exe"
            )
            track_exe = self.script_config.get("Script", "TrackProcessExe") or ""
            if not track_exe:
                track_exe = str(
                    self.script_root_path / "data/apps/ok-nte/python/pythonw.exe"
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
        # 成功/失败标志：按显式模式编译，Split 为存量「|」分隔关键字子串包含，
        # Regex 为整条正则；非法正则视为已配置但永不命中，不中断任务执行
        self.success_log = compile_log_signs(
            self.script_config.get("Script", "SuccessLog"),
            self.script_config.get("Script", "SuccessLogMode"),
        )
        self.error_log = compile_log_signs(
            self.script_config.get("Script", "ErrorLog"),
            self.script_config.get("Script", "ErrorLogMode"),
        )
        for name, matcher in (("成功", self.success_log), ("失败", self.error_log)):
            if matcher.invalid:
                logger.warning(f"OK-NTE {name}日志正则语法错误，该标志将不会命中")
        if not self.error_log.configured:
            self.error_log = compile_log_signs(
                _DEFAULT_OKNTE_ERROR_LOG, SIGN_MODE_SPLIT
            )
            logger.warning(
                "OK-NTE ErrorLog 去掉过宽容词后为空，已回退为内置默认失败关键词"
            )

        # ── log_box：节点日志采集推送（MAS 进程宿主，注入 sink 到 push_log）──
        # 受用户级「是否采集节点详情」开关控制：关闭时不创建（不读日志、不匹配、
        # 不处理），该用户 push_log 保持为空，报告聚合时自然不含其节点详情。
        # ok-nte 日志文本已是中文，无需前置翻译；open() 记录起始偏移，只采会话内新增。
        if self.cur_user_config.get("Notify", "PushLogEnabled"):
            self.log_collect = log_box.get_collect(
                paths=[self._resolve_log_path()],
                sink=self._append_push_log,
                start_from_end=True,
            )
            self.log_collect.open()
            for rule in OKNTE_PUSH_RULES:
                self.log_collect.collect(*rule)

        # 当前用户配置

        self.task_index = int(self.cur_user_config.get("Task", "TaskIndex"))
        self.exit_on_finish = bool(self.cur_user_config.get("Task", "ExitOnFinish"))

        extra_args = _split_args(self.script_config.get("Script", "Arguments"))

        self.oknte_args = ["-t", str(self.task_index)]
        if self.exit_on_finish:
            self.oknte_args.append("-e")
        self.oknte_args.extend(extra_args)

        # 游戏配置（对齐通用脚本逻辑）
        self.game_path = Path(self.script_config.get("Game", "Path"))
        self.game_url = self.script_config.get("Game", "URL")
        self.game_process_name = self.script_config.get("Game", "ProcessName")
        self.script_config_path = Path(self.script_config.get("Script", "ConfigPath"))

        self.run_book = False

    def _oknte_legacy_mas_config_dir(self) -> Path:
        return (
            Path.cwd() / "data" / self.script_info.script_id / "Default" / "ConfigFile"
        )

    def _oknte_mas_config_dir(self) -> Path:
        return (
            Path.cwd()
            / "data"
            / self.script_info.script_id
            / str(self.cur_user_uid)
            / "ConfigFile"
        )

    def _oknte_source_config_dir(self, mas_config_dir: Path) -> Path | None:
        candidates = [
            self._oknte_legacy_mas_config_dir(),
            self.script_config_path,
            self.script_root_path / "data" / "apps" / "ok-nte" / "working" / "configs",
            self.script_root_path / "configs",
        ]
        for config_dir in candidates:
            if not config_dir.is_dir():
                continue
            with suppress(OSError):
                if config_dir.resolve() == mas_config_dir.resolve():
                    continue
            return config_dir
        return None

    def _ensure_oknte_mas_config_dir(self) -> Path:
        mas_config_dir = self._oknte_mas_config_dir()
        if mas_config_dir.exists() and any(mas_config_dir.iterdir()):
            ensure_oknte_daily_routine_configs(mas_config_dir)
            return mas_config_dir

        mas_config_dir.mkdir(parents=True, exist_ok=True)
        if self.script_config.get("Script", "ConfigPathMode") == "File":
            if not self.script_config_path.is_file():
                raise FileNotFoundError("OK-NTE 配置文件未初始化，请先设置有效配置路径")
            shutil.copy(
                self.script_config_path,
                mas_config_dir / self.script_config_path.name,
            )
            ensure_oknte_daily_routine_configs(mas_config_dir)
            return mas_config_dir

        source_config_dir = self._oknte_source_config_dir(mas_config_dir)
        if source_config_dir is None:
            raise FileNotFoundError("OK-NTE 配置目录未初始化，请先设置有效配置路径")

        shutil.copytree(source_config_dir, mas_config_dir, dirs_exist_ok=True)
        ensure_oknte_daily_routine_configs(mas_config_dir)
        return mas_config_dir

    async def set_oknte(self) -> None:
        """将 MAS 侧 OK-NTE 任务配置下发到脚本 working 目录（对齐 General.set_general）。"""

        logger.info("开始配置 OK-NTE 运行参数: 自动代理")
        await System.kill_process(self.script_exe_path)

        mas_config_dir = self._ensure_oknte_mas_config_dir()
        self.daily_activity_required = _oknte_daily_activity_enabled(mas_config_dir)
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
        logger.info("OK-NTE 运行参数配置完成: 自动代理")

    async def update_config(self) -> None:
        """将脚本侧配置回写 MAS ConfigFile（对齐 General.update_config）。"""

        mas_config_dir = self._oknte_mas_config_dir()
        mas_config_dir.mkdir(parents=True, exist_ok=True)
        if self.script_config.get("Script", "ConfigPathMode") == "Folder":
            shutil.copytree(self.script_config_path, mas_config_dir, dirs_exist_ok=True)
        elif self.script_config.get("Script", "ConfigPathMode") == "File":
            shutil.copy(
                self.script_config_path,
                mas_config_dir / self.script_config_path.name,
            )
        logger.success("OK-NTE 配置文件已更新")

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

    def _append_push_log(self, log_type: str, text: str) -> None:
        """sink：把 log_box 采集结果写入当前用户的推送日志（供调度器聚合到报告）"""
        self.cur_user_item.push_log.append((log_type, text))

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
                f"正在检查异环客户端进程 ({_NTE_CLIENT_PROCESS})..."
            )
            if is_process_running(_NTE_CLIENT_PROCESS):
                logger.info("检测到异环客户端进程已在运行，跳过由 MAS 重复启动游戏")
                await self._push_dispatch_log("检测到客户端已在运行，跳过启动")
                return

            await self._push_dispatch_log("未检测到运行中的客户端，正在拉起游戏...")
            await self.game_manager.open_process(
                self.game_path,
                *_split_args(self.script_config.get("Game", "Arguments")),
            )
            wait_time = int(self.script_config.get("Game", "WaitTime"))
            await self._push_dispatch_log(f"正在等待游戏完成启动（{wait_time}s）...")
            await asyncio.sleep(wait_time)
            await self._push_dispatch_log("游戏启动完成")
            return

        if isinstance(self.game_manager, ProcessManager) and game_type == "URL":
            await self._push_dispatch_log("正在通过 URL 协议启动游戏...")
            game_url = str(self.game_url or "").strip()
            game_process_name = str(self.game_process_name or "").strip()
            if not game_url:
                raise RuntimeError("请设置异环游戏 URL")
            if not game_process_name:
                raise RuntimeError("请设置异环游戏进程名称")
            if is_process_running(game_process_name):
                logger.info(
                    f"检测到异环客户端进程已在运行，跳过启动: {game_process_name}"
                )
                await self._push_dispatch_log("检测到客户端已在运行，跳过启动")
                return
            await self.game_manager.open_protocol(
                game_url,
                ProcessInfo(name=game_process_name),
            )
            await asyncio.sleep(2)
            await self._push_dispatch_log("游戏启动指令已发送")
            return

    async def main_task(self):
        await self.prepare()
        await self._reset_daily_proxy_count()

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

            if self.cur_user_config.get("Info", "IfScriptBeforeTask"):
                await execute_script_task(
                    Path(self.cur_user_config.get("Info", "ScriptBeforeTask")),
                    "脚本前任务",
                )

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
                    await Publisher.send(
                        id=self.task_info.task_id,
                        type=protocol.TASK_NOTICE,
                        data=WSTaskNoticeData(
                            level="error", message=f"游戏启动失败: {e}"
                        ),
                    )
                    await self.kill_managed_process(
                        kill_game=self._mas_should_close_game_on_retry()
                    )
                    try:
                        await Notify.push_plyer(
                            "OK-NTE 自动代理出现异常！",
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

            await self.set_oknte()
            await self._push_dispatch_log(
                f"启动 OK-NTE: -t {self.task_index}"
                + (" -e" if self.exit_on_finish else "")
            )
            logger.info(
                f"启动 OK-NTE 进程: {self.script_exe_path} {' '.join(self.oknte_args)}"
            )

            await self.oknte_process_manager.open_process(
                self.script_exe_path,
                *self.oknte_args,
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
                self.script_info.log = "检测到 OK-NTE 已完成任务\n正在等待相关进程结束"
                # 对齐 MaaEnd：成功时先只结束 OK-NTE；是否关游戏由 Game.CloseOnFinish 在 final_task 决定
                await self._kill_oknte_process()
                if self.script_config.get("Script", "UpdateConfigMode") in (
                    "Success",
                    "Always",
                ):
                    await self.update_config()
                if self.cur_user_config.get("Info", "IfScriptAfterTask"):
                    await execute_script_task(
                        Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
                        "脚本后任务",
                    )
                await asyncio.sleep(3)
                break

            logger.warning(
                f"用户 {self.cur_user_item.name} - OK-NTE 代理异常: {self.cur_user_log.status}"
            )
            self.script_info.log = f"{self.cur_user_log.status}\n正在中止相关程序"
            await self.kill_managed_process(
                kill_game=self._mas_should_close_game_on_retry()
            )
            try:
                await Notify.push_plyer(
                    "OK-NTE 自动代理出现异常！",
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
            if self.cur_user_config.get("Info", "IfScriptAfterTask"):
                await execute_script_task(
                    Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
                    "脚本后任务",
                )
            if i + 1 < run_limit:
                self.script_info.log += f"\n将在稍后重试 ({i + 1}/{run_limit})"
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

        log_status = "OK-NTE 正常运行中"
        user_item_status: str | None = None

        for needle, msg in _OKNTE_BUILTIN_FATAL:
            if needle in log:
                log_status = msg
                user_item_status = "异常"
                break
        else:
            error_sign = self.error_log.search(log)
            if error_sign is not None:
                log_status = f"OK-NTE：{error_sign}"
                user_item_status = "异常"
            elif _oknte_log_indicates_success(log, self.success_log):
                daily_task_error = (
                    _oknte_daily_task_success_error(
                        log,
                        daily_activity_required=self.daily_activity_required,
                    )
                    if self.task_index == _OKNTE_DAILY_TASK_INDEX
                    else None
                )
                if daily_task_error:
                    log_status = daily_task_error
                    user_item_status = "异常"
                else:
                    log_status = "Success!"
                    user_item_status = "完成"
            elif not await self.oknte_process_manager.is_running():
                log_status = "OK-NTE 在完成任务前退出"
                user_item_status = "异常"
            elif self.is_log_stalled(
                latest_time, minutes=self.script_config.get("Run", "RunTimeLimit")
            ):
                log_status = "OK-NTE 运行超时"
                user_item_status = "异常"

        self.cur_user_log.status = log_status
        if user_item_status is not None:
            self.cur_user_item.status = user_item_status

        logger.debug(f"OK-NTE 日志分析结果: {self.cur_user_log.status}")
        if self.cur_user_log.status != "OK-NTE 正常运行中":
            logger.info(f"OK-NTE 任务结果: {self.cur_user_log.status}, 日志锁已释放")
            self.wait_event.set()

    async def final_task(self):
        # 结束时先清理进程与监控
        with suppress(Exception):
            await self.log_monitor.stop()
        if self.run_book and not self._mas_should_close_game_after_success():
            await self._kill_oknte_process()
        else:
            kill_game = (
                self._mas_should_close_game_after_success()
                if self.run_book
                else self._mas_should_close_game_on_retry()
            )
            await self.kill_managed_process(kill_game=kill_game)

        # log_box 收尾：冲刷残留、后置状态解析并完成推送（sink → cur_user_item.push_log）
        # 采集失败时记一笔日志，避免报告里节点信息缺失却无从排查；
        # 开关关闭（未创建）时 log_collect 为 None，一并在此兜底
        try:
            if self.log_collect is not None:
                self.log_collect.close(oknte_resolve)
        except Exception:
            logger.opt(exception=True).warning("OK-NTE log_box 收尾推送失败（oknte_resolve）")
            # 采集失败状态显式写入报告，避免节点详情缺失却仍呈现为正常结果
            self.cur_user_item.push_log.append(
                (LogType.NORMAL, "⚠️ 节点采集失败")
            )

        # 写入历史记录（对齐 General/SRC/MaaEnd 行为）
        user_logs_list = []
        for t, log_item in self.cur_user_item.log_record.items():
            dt = t.astimezone(UTC4)
            log_path = Config.build_history_log_path(
                script_name=self.script_info.name,
                user_name=self.cur_user_item.name,
                log_time=dt,
            )

            if log_item.status == "OK-NTE 正常运行中":
                log_item.status = "任务被用户手动中止"

            if len(log_item.content) == 0:
                log_item.content = ["未捕获到任何日志内容"]
                log_item.status = "未捕获到日志"

            await Config.save_general_log(log_path, log_item.content, log_item.status)
            user_logs_list.append(log_path.with_suffix(".json"))

        if user_logs_list:
            statistics = await Config.merge_statistic_info(user_logs_list)
            statistics["user_info"] = self.cur_user_item.name
            statistics["start_time"] = self.user_start_time.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            statistics["user_result"] = (
                "OK-NTE 任务全部完成" if self.run_book else self.cur_user_item.result
            )
            success_symbol = "√" if self.run_book else "X"

            try:
                await push_notification(
                    "统计信息",
                    f"{datetime.now().strftime('%m-%d')} |{success_symbol}|  {self.cur_user_item.name} 的 OK-NTE 自动代理统计报告",
                    statistics,
                    self.cur_user_config,
                )
            except Exception as e:
                logger.opt(exception=True).warning(f"推送通知时出现异常: {e}")
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error", message=f"推送通知时出现异常: {e}"
                    ),
                )

        await self._persist_user_run_result()

    async def _persist_user_run_result(self) -> None:
        if self.user_run_result_persisted:
            return
        self.user_run_result_persisted = True

        await self.cur_user_config.set(
            "Data", "LastTaskIndex", getattr(self, "task_index", 0)
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
            if self.cur_user_item.status != "异常":
                self.cur_user_item.status = "完成"
            logger.success(f"用户 {self.cur_user_uid} 的 OK-NTE 自动代理任务已完成")
        else:
            await self.cur_user_config.set("Data", "LastProxyStatus", "失败")
            if self.cur_user_item.status != "完成":
                self.cur_user_item.status = "异常"

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        if hasattr(self, "cur_user_log"):
            self.cur_user_log.status = f"OK-NTE 运行异常: {e}"
        logger.opt(exception=True).warning(f"OK-NTE 自动代理任务出现异常: {e}")
        if hasattr(self, "wait_event"):
            self.wait_event.set()
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(
                level="error", message=f"OK-NTE 自动代理任务出现异常: {e}"
            ),
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
                    "OK-NTE 运行异常",
                    f"用户 {self.cur_user_item.name}：{self.cur_user_log.status}",
                    "异常",
                    3,
                )
        except Exception:
            pass

    async def _kill_oknte_process(self) -> None:
        try:
            await self.oknte_process_manager.kill()
        except Exception as e:
            logger.opt(exception=True).warning(
                f"通过进程管理器中止 OK-NTE 进程失败: {e}"
            )
        try:
            await System.kill_process(self.script_exe_path)
        except Exception as e:
            logger.opt(exception=True).warning(f"中止 OK-NTE 主进程失败: {e}")
        track_exe = str(
            self.script_config.get("Script", "TrackProcessExe") or ""
        ).strip()
        if not track_exe:
            track_exe = str(
                self.script_root_path / "data/apps/ok-nte/python/pythonw.exe"
            )
        if track_exe:
            try:
                await System.kill_process(Path(track_exe))
            except Exception as e:
                logger.opt(exception=True).warning(f"中止 OK-NTE 追踪进程失败: {e}")
        try:
            launcher_path = _load_nte_launcher_path(self.script_config_path)
            if launcher_path is None:
                logger.warning("未找到有效的异环启动器路径，跳过进程清理")
            else:
                await System.kill_process(launcher_path, kill_tree=False)
        except Exception as e:
            logger.opt(exception=True).warning(f"中止异环启动器进程失败: {e}")

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
        except Exception as e:
            logger.opt(exception=True).warning(f"关闭游戏进程失败: {e}")

    async def kill_managed_process(self, *, kill_game: bool = True) -> None:
        """中止 OK-NTE；kill_game 为真时结束游戏（失败重试恒为真；成功收尾看 CloseOnFinish）"""
        await self._kill_oknte_process()
        if kill_game:
            await self._kill_game_process()
