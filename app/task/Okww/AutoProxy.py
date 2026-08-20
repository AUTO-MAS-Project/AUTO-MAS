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
import json
import shlex
import shutil
import uuid
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path

from app.core import Config
from app.models.task import TaskExecuteBase, ScriptItem, UserItem, LogRecord
from app.models.ConfigBase import MultipleConfig
from app.models.config import OkwwConfig, OkwwUserConfig
from app.services import Notify, System
from app.services.wuthering_waves import (
    WutheringWavesUpdateInfo,
    check_wuthering_waves_update,
    resolve_wuthering_waves_process_path,
    wait_wuthering_waves_update,
)
from app.utils import get_logger, ProcessManager, ProcessInfo, is_process_running
from app.utils.io import write_file
from app.utils.LogMonitor import LogMonitor
from app.utils.constants import UTC4
from app.utils.OCR.OCRtool import OCRTool
from app.task.general.tools import execute_script_task

from .tools import push_notification

logger = get_logger("OK-WW 自动代理")

# 鸣潮 PC 客户端窗口进程名固定，MAS 接管启动前据此避免重复拉起
_WUWA_CLIENT_PROCESS = "Client-Win64-Shipping.exe"
_WUWA_LAUNCHER_PROCESS = "launcher.exe"
_WUWA_LAUNCHER_TITLE_BY_RESOURCE = {
    "官服": "鸣潮",
    "国际服": "Wuthering Waves",
}


# ── okww 专项硬编码（不存 ConfigItem，随 MAS 版本同步）──────────────
# 对齐 MaaEnd：专项内置日志片段，Okww 不向用户暴露成功/失败日志关键词配置。
_OKWW_BUILTIN_FATAL: tuple[tuple[str, str], ...] = (
    ("connected:False", "OK-WW 未连接游戏客户端"),
    ("游戏更新成功, 游戏即将重启", "游戏更新成功，即将重启任务"),
    ("info_set 错误", "OK-WW 流程产生错误，请检查游戏状态"),
)
_OKWW_SUCCESS_LOG = "Window closed exit_event.is_set"

# ok-ww 项目结构固定相对路径（从 RootPath 派生，不依赖用户存储值）
# ⚠️ 与前端 OkwwScriptEdit.vue 的 OKWW_EXE_NAME 保持同步，改这里时需同步改前端
_OKWW_REL_EXE = "ok-ww.exe"
_OKWW_REL_APP_JSON = "data/apps/ok-ww/app.json"
_OKWW_REL_CONFIG_DIR = "data/apps/ok-ww/working/configs"
_OKWW_REL_LOG_FILE = "data/apps/ok-ww/working/logs/ok-script.log"
_OKWW_REL_PYTHONW = "data/apps/ok-ww/python/pythonw.exe"
_OKWW_TRACK_PROCESS_NAME = "pythonw.exe"
_OKWW_PROFILE_BY_RESOURCE = {"官服": "China", "国际服": "Global"}
_OKWW_UPDATE_METHOD = "AUTO_UPDATE"
_OKWW_LOG_TIME_START = 1
_OKWW_LOG_TIME_END = 23
_OKWW_LOG_TIME_FORMAT = "%Y-%m-%d %H:%M:%S,%f"


def _split_args(raw: object) -> list[str]:
    value = str(raw or "").strip()
    return shlex.split(value, posix=False) if value else []


def _okww_config_mode(raw: object) -> str:
    mode = str(raw or "脚本")
    return {"简洁": "脚本", "详细": "用户"}.get(mode, mode)


def _okww_mas_config_dir(script_id: str, user_id: str, mode: str) -> Path:
    mode = _okww_config_mode(mode)
    if mode == "直控":
        raise ValueError("直控配置不使用 MAS 全量配置目录")
    owner = "Default" if mode == "脚本" else user_id
    return Path.cwd() / "data" / script_id / owner / "ConfigFile"


def _update_json(path: Path, values: dict[str, object]) -> None:
    data: object = {}
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"OK-WW 配置文件格式错误: {path.name}")
    data.update(values)
    write_file(path, data)


def _configure_okww_launcher(
    script_root_path: Path, resource: str | None = None
) -> None:
    app_json_path = script_root_path / _OKWW_REL_APP_JSON
    if not app_json_path.is_file():
        return

    app_config = json.loads(app_json_path.read_text(encoding="utf-8"))
    if not isinstance(app_config, dict):
        raise ValueError("OK-WW app.json 格式错误")

    profile = app_config.get("current_profile")
    if resource is not None:
        profile = _OKWW_PROFILE_BY_RESOURCE.get(resource)
        if profile is None:
            raise ValueError(f"不支持的 OK-WW 游戏资源: {resource}")
    available_profiles = {
        item.get("name")
        for item in (app_config.get("profiles") or [])
        if isinstance(item, dict)
    }
    if (
        resource is not None
        and available_profiles
        and profile not in available_profiles
    ):
        raise ValueError(f"当前 OK-WW 安装不支持{resource}资源")
    changed = False
    if "auto_start" not in app_config:
        app_config["auto_start"] = True
        changed = True
    if "update_method" not in app_config:
        app_config["update_method"] = _OKWW_UPDATE_METHOD
        changed = True
    if resource is not None and app_config.get("current_profile") != profile:
        app_config["current_profile"] = profile
        changed = True
    if not changed:
        return

    write_file(app_json_path, app_config)
    logger.info("已补齐 OK-WW 启动器默认设置")


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
        self.cur_user_config: OkwwUserConfig = self.user_config[self.cur_user_uid]
        self.cur_user_log: LogRecord | None = None
        self.launcher_path: Path | None = None
        self.game_process_path: Path | None = None
        self.okww_process_manager: ProcessManager | None = None
        self.launcher_process_manager: ProcessManager | None = None
        self.wait_event: asyncio.Event | None = None
        self.script_root_path: Path | None = None
        self.script_exe_path: Path | None = None
        self.script_target_process_info: ProcessInfo | None = None
        self.script_log_path: Path | None = None
        self.log_monitor: LogMonitor | None = None
        self.script_config_path: Path | None = None

    async def check(self) -> str:
        root = Path(self.script_config.get("Info", "RootPath"))
        if not root.is_dir():
            return "请设置ok-ww脚本路径"
        if not (root / _OKWW_REL_EXE).is_file():
            return "请设置ok-ww脚本路径"
        if not (root / _OKWW_REL_APP_JSON).is_file():
            return "请设置ok-ww脚本路径"
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

        if self.script_config.get("Game", "Enabled"):
            launcher_path = Path(
                str(self.script_config.get("Game", "Path") or "").strip()
            )
            self.launcher_path = launcher_path
            try:
                self.game_process_path = resolve_wuthering_waves_process_path(
                    launcher_path
                )
            except (FileNotFoundError, ValueError) as e:
                return str(e)

        config_mode = _okww_config_mode(self.cur_user_config.get("Info", "Mode"))
        if config_mode == "直控":
            config_dir = root / _OKWW_REL_CONFIG_DIR
            if not config_dir.is_dir() or not any(
                item.is_file() for item in config_dir.rglob("*")
            ):
                return "未找到 OK-WW 脚本原有配置，请先在 OK-WW 中保存设置"
        else:
            try:
                await Config.ensure_okww_user_config(
                    script_id=self.script_info.script_id,
                    user_id=str(self.cur_user_uid),
                    mode=config_mode,
                )
            except FileNotFoundError as e:
                logger.warning(f"初始化 OK-WW 用户默认配置失败: {e}")
                return str(e)
            except (OSError, TypeError, ValueError) as e:
                logger.warning(f"初始化 OK-WW 用户默认配置失败: {e}")
                return "无法读取 OK-WW 默认配置，请检查 OK-WW 脚本路径"
        return "Pass"

    async def prepare(self):
        self.okww_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()

        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now()

        # ── 所有 Script 路径从 RootPath 实时派生，不依赖 ConfigItem 存储值 ──
        self.script_root_path = Path(self.script_config.get("Info", "RootPath"))
        self.script_exe_path = self.script_root_path / _OKWW_REL_EXE

        self.script_target_process_info = ProcessInfo(
            name=_OKWW_TRACK_PROCESS_NAME,
            exe=str(self.script_root_path / _OKWW_REL_PYTHONW),
            cmdline=None,
        )

        self.script_log_path = self.script_root_path / _OKWW_REL_LOG_FILE

        self.log_time_range = (_OKWW_LOG_TIME_START - 1, _OKWW_LOG_TIME_END)
        self.log_time_format = _OKWW_LOG_TIME_FORMAT
        self.log_monitor = LogMonitor(
            self.log_time_range,
            self.log_time_format,
            self.check_log,
        )

        self.task_index = int(self.cur_user_config.get("Task", "TaskIndex"))
        self.okww_args = ["-t", str(self.task_index), "-e"]

        self.script_config_path = self.script_root_path / _OKWW_REL_CONFIG_DIR

        self.run_book = False

    def _okww_mas_config_dir(self) -> Path:
        return _okww_mas_config_dir(
            self.script_info.script_id,
            str(self.cur_user_uid),
            _okww_config_mode(self.cur_user_config.get("Info", "Mode")),
        )

    def _apply_mas_overrides(self) -> None:
        _update_json(
            self.script_config_path / "Basic Options.json",
            {"Exit App when Game Exits": True},
        )
        if not self.cur_user_config.get("Info", "IfQuickConfig"):
            return
        _update_json(
            self.script_config_path / "DailyTask.json",
            {
                "Which to Farm": self.cur_user_config.get("Task", "WhichToFarm"),
                "Which Tacet Suppression to Farm": self.cur_user_config.get(
                    "Task", "WhichTacetSuppressionToFarm"
                ),
                "Which Forgery Challenge to Farm": self.cur_user_config.get(
                    "Task", "WhichForgeryChallengeToFarm"
                ),
                "Material Selection": self.cur_user_config.get(
                    "Task", "MaterialSelection"
                ),
                "Farm Nightmare Nest for Daily Echo": self.cur_user_config.get(
                    "Task", "FarmNightmareNestForDailyEcho"
                ),
                "Additional Tasks to Run After Daily Task": self.cur_user_config.get(
                    "Task", "AdditionalTasks"
                ),
            },
        )

    async def set_okww(self) -> None:
        """将 MAS 侧 OK-WW 任务配置下发到脚本 working 目录（对齐 General.set_general）。"""

        logger.info("开始配置 OK-WW 运行参数: 自动代理")
        await System.kill_process(self.script_exe_path)
        _configure_okww_launcher(
            self.script_root_path,
            str(self.cur_user_config.get("Info", "Resource")),
        )

        config_mode = _okww_config_mode(self.cur_user_config.get("Info", "Mode"))
        if config_mode != "直控":
            mas_config_dir = self._okww_mas_config_dir()
            tmp_dst = self.script_config_path.with_name(
                self.script_config_path.name + ".tmp"
            )
            shutil.rmtree(tmp_dst, ignore_errors=True)
            shutil.copytree(mas_config_dir, tmp_dst, dirs_exist_ok=True)
            shutil.rmtree(self.script_config_path, ignore_errors=True)
            tmp_dst.rename(self.script_config_path)
        self._apply_mas_overrides()
        logger.info("OK-WW 运行参数配置完成: 自动代理")

    async def _push_dispatch_log(self, line: str) -> None:
        """向调度台追加流程日志（赋值 script_info.log 会触发 WebSocket 推送）。"""

        prev = self.script_info.log
        self.script_info.log = f"{prev}\n{line}" if prev else line
        await asyncio.sleep(0)

    async def _click_wuthering_waves_launcher_text(
        self,
        text: str,
        *,
        alternatives: tuple[str, ...] = (),
        retry_times: int = 30,
        interval: float = 2,
    ) -> bool:
        """通过 OCR 点击官方启动器上的指定文字。"""

        title = _WUWA_LAUNCHER_TITLE_BY_RESOURCE.get(
            str(self.cur_user_config.get("Info", "Resource")), "鸣潮"
        )
        for candidate in (text, *alternatives):
            if await asyncio.to_thread(
                OCRTool.click_txt,
                text=candidate,
                title=title,
                interval=interval,
                retry_times=retry_times,
            ):
                return True
        return False

    async def _start_wuthering_waves_launcher(self) -> None:
        """启动官方启动器，下载过程和结果由启动器自身负责。"""

        if self.launcher_path is None:
            raise RuntimeError("未设置鸣潮官方启动器路径")
        if is_process_running(_WUWA_LAUNCHER_PROCESS):
            logger.info("检测到鸣潮官方启动器已运行，复用现有进程")
            return

        self.launcher_process_manager = ProcessManager()
        await self.launcher_process_manager.open_process(self.launcher_path)
        await asyncio.sleep(3)

    async def _trigger_wuthering_waves_launcher_update(
        self, update_info: WutheringWavesUpdateInfo
    ) -> None:
        """只触发官方启动器按钮，不接管包体下载、覆盖和校验。"""

        await self._start_wuthering_waves_launcher()
        if update_info.update_available:
            if self.launcher_path is None or update_info.release_version is None:
                raise RuntimeError("鸣潮官方更新缺少启动器路径或目标版本")
            clicked = await self._click_wuthering_waves_launcher_text(
                "更新",
                alternatives=("更新游戏", "Update", "Update Game"),
                retry_times=45,
            )
            if not clicked:
                raise RuntimeError("未能通过 OCR 找到鸣潮官方启动器的更新按钮")
            logger.info(
                "已通过官方启动器触发鸣潮更新: {} -> {}",
                update_info.current_version or "未知",
                update_info.release_version or "未知",
            )
            await self._push_dispatch_log("等待鸣潮官方启动器完成下载与解压...")
            await wait_wuthering_waves_update(
                self.launcher_path,
                update_info.release_version,
            )
            return

        clicked = await self._click_wuthering_waves_launcher_text(
            "预下载", alternatives=("Pre-download",), retry_times=45
        )
        if not clicked:
            logger.info("未通过 OCR 找到预下载按钮，可能已在下载或已完成")
            return
        confirmed = await self._click_wuthering_waves_launcher_text(
            "确定下载", alternatives=("Confirm Download",), retry_times=15
        )
        if not confirmed:
            logger.info("未通过 OCR 找到预下载确认按钮，交由启动器继续当前流程")
            return
        logger.info(
            "已通过官方启动器触发鸣潮预下载: {} -> {}；下载过程由启动器负责",
            update_info.current_version or "未知",
            update_info.predownload_version or "未知",
        )

    async def _check_and_trigger_wuthering_waves_update(self) -> None:
        """检查官方版本信息，必要时触发启动器 OCR 更新流程。"""

        if self.launcher_path is None:
            return
        resource = str(self.cur_user_config.get("Info", "Resource"))
        try:
            update_info = await check_wuthering_waves_update(
                self.launcher_path,
                resource,
            )
        except Exception as e:
            # 官方接口不可用时不阻断原有游戏启动流程。
            logger.warning(f"鸣潮官方更新检查失败，将继续启动游戏: {e}")
            return
        if not update_info.should_start_launcher:
            return
        await self._trigger_wuthering_waves_launcher_update(update_info)

    async def _mas_launch_game_before_task(self) -> None:
        """检查并触发官方启动器更新，然后启动鸣潮客户端。"""

        if isinstance(self.game_manager, ProcessManager):
            await self._check_and_trigger_wuthering_waves_update()
            if is_process_running(_WUWA_CLIENT_PROCESS):
                try:
                    await self.game_manager.search_process(
                        self._game_process_info(),
                        datetime.now() + timedelta(seconds=3),
                    )
                except RuntimeError:
                    logger.info("检测到其他鸣潮客户端进程，继续启动已配置的游戏")
                else:
                    logger.info(
                        "检测到已配置的鸣潮客户端进程正在运行，跳过重复启动"
                    )
                    return

            await self.game_manager.open_process(
                self.game_process_path,
                *_split_args(self.script_config.get("Game", "Arguments")),
            )
            wait_time = max(int(self.script_config.get("Game", "WaitTime")), 0)
            if wait_time:
                await self._push_dispatch_log(f"等待游戏启动（{wait_time} 秒）...")
                await asyncio.sleep(wait_time)

    def _game_process_info(self) -> ProcessInfo:
        return ProcessInfo(
            name=_WUWA_CLIENT_PROCESS,
            exe=str(self.game_process_path),
        )

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

            # 启用游戏配置时始终由 MAS 拉起游戏
            if (
                self.script_config.get("Game", "Enabled")
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
                        kill_game=self._game_management_enabled()
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
                f"启动 OK-WW: -t {self.task_index} -e"
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
                self.script_log_path, self.log_start_time
            )

            self.wait_event.clear()
            await self.wait_event.wait()
            await self.log_monitor.stop()

            if self.cur_user_log.status == "Success!":
                self.run_book = True
                self.script_info.log = (
                    "检测到 OK-WW 已完成任务\n正在等待 OK-WW 自行退出"
                )
                # 等待 OK-WW 自然退出（-e 标志使其任务完成后自行关闭游戏并退出）
                await self._wait_okww_exit(timeout=30)
                if self.cur_user_config.get("Info", "IfScriptAfterTask"):
                    await execute_script_task(
                        Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
                        "脚本后任务",
                    )
                await asyncio.sleep(3)
                break

            logger.warning(
                f"用户 {self.cur_user_item.name} - OK-WW 代理异常: {self.cur_user_log.status}"
            )
            self.script_info.log = (
                f"{self.cur_user_log.status}\n正在中止相关程序"
            )
            await self.kill_managed_process(
                kill_game=self._game_management_enabled()
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

    def _game_management_enabled(self) -> bool:
        return bool(self.script_config.get("Game", "Enabled"))

    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """按内置日志判定结果，未见成功日志便退出则视为异常。"""
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
            if _OKWW_SUCCESS_LOG in log:
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
        # 结束时先清理进程与监控；任务结束后始终关闭游戏（由 Game.Enabled 总开关控制）
        if self.log_monitor is not None:
            with suppress(Exception):
                await self.log_monitor.stop()
        await self.kill_managed_process(kill_game=self._game_management_enabled())

        # 写入历史记录（对齐 General/SRC/MaaEnd 行为）
        statistic_paths: list[Path] = []
        for t, log_item in self.cur_user_item.log_record.items():
            dt = t.replace(tzinfo=datetime.now().astimezone().tzinfo).astimezone(UTC4)
            log_path = Config.build_history_log_path(
                script_name=self.script_info.name,
                user_name=self.cur_user_item.name,
                log_time=dt,
            )

            if log_item.status == "OK-WW 正常运行中":
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
                    f"{self.cur_user_item.name} 的 OK-WW 自动代理统计报告",
                    statistics,
                    self.cur_user_config,
                )
            except Exception as e:
                logger.opt(exception=True).warning(
                    f"推送 OK-WW 用户统计通知时出现异常: {e}"
                )

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
        if self.cur_user_log is not None:
            self.cur_user_log.status = f"OK-WW 运行异常: {e}"
        logger.opt(exception=True).warning(f"OK-WW 自动代理任务出现异常: {e}")
        if self.wait_event is not None:
            self.wait_event.set()
        with suppress(Exception):
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": f"OK-WW 自动代理任务出现异常: {e}"},
            )
        with suppress(Exception):
            await self.kill_managed_process(
                kill_game=self._game_management_enabled()
            )
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
                    "OK-WW 运行异常",
                    f"用户 {self.cur_user_item.name}：{self.cur_user_log.status}",
                    "异常",
                    3,
                )
        except Exception:
            pass

    async def _wait_okww_exit(self, *, timeout: int = 30) -> None:
        """等待 OK-WW 自然退出（-e 触发），超时后兜底强杀。"""
        deadline = datetime.now() + timedelta(seconds=timeout)
        while datetime.now() < deadline:
            if not await self.okww_process_manager.is_running():
                logger.info("OK-WW 已自行退出")
                return
            await asyncio.sleep(1)
        logger.warning(f"OK-WW 未在 {timeout}s 内自行退出，兜底强杀")
        await self._kill_okww_process()

    async def _kill_okww_process(self) -> None:
        if self.okww_process_manager is not None:
            try:
                await self.okww_process_manager.kill()
            except Exception as e:
                logger.opt(exception=True).warning(f"通过进程管理器中止 OK-WW 进程失败: {e}")
        if self.script_exe_path is not None:
            try:
                await System.kill_process(self.script_exe_path)
            except Exception as e:
                logger.opt(exception=True).warning(f"中止 OK-WW 主进程失败: {e}")
        if self.script_root_path is not None:
            track_exe = self.script_root_path / _OKWW_REL_PYTHONW
            try:
                await System.kill_process(track_exe)
            except Exception as e:
                logger.opt(exception=True).warning(f"中止 OK-WW 追踪进程失败: {e}")

    async def _kill_game_process(self) -> None:
        """结束游戏：任务结束/失败/异常时始终触发（由 Game.Enabled 总开关控制）"""
        if isinstance(self.game_manager, ProcessManager):
            if (
                self.game_process_path is not None
                and self.game_manager.target_process is None
            ):
                try:
                    await self.game_manager.search_process(
                        self._game_process_info(),
                        datetime.now() + timedelta(seconds=1),
                    )
                except RuntimeError:
                    logger.debug("未找到待关闭的鸣潮客户端进程")
            try:
                await self.game_manager.kill()
            except Exception as e:
                logger.opt(exception=True).warning(f"通过进程管理器关闭鸣潮客户端失败: {e}")
        if self.game_process_path is not None:
            try:
                await System.kill_process(self.game_process_path)
            except Exception as e:
                logger.opt(exception=True).warning(f"兜底强杀鸣潮客户端失败: {e}")

    async def kill_managed_process(self, *, kill_game: bool = True) -> None:
        """中止 ok-ww；kill_game 为真时结束游戏"""
        await self._kill_okww_process()
        if kill_game:
            await self._kill_game_process()
