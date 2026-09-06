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


import asyncio
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from app.core import Config
from app.core.ws import Publisher, protocol
from app.models.config import MaaEndConfig, MaaEndUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.emulator import DeviceBase, DeviceInfo
from app.models.schema import WSTaskNoticeData
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase
from app.services import Notify, System
from app.task.general.tools import execute_script_task
from app.utils import LogMonitor, ProcessManager, get_logger, is_process_running
from app.utils.constants import (
    MAAEND_AUTO_COLLECT_MODES,
    MAAEND_AUTO_COLLECT_ROUTE_OPTIONS,
    MAAEND_AUTO_COLLECT_SCHEDULE_OPTIONS,
    MAAEND_AUTO_COLLECT_TASK,
    MAAEND_DELIVERY_TASK,
    MAAEND_RUN_MOOD_BOOK,
    MAAEND_TASKS,
    UTC4,
)
from app.utils.io import read_file, write_file

from .resource_loader import (
    load_maaend_interface_i18n,
    load_maaend_task_i18n,
)
from .ScriptConfig import maaend_config_mode, maaend_mas_config_dir
from .tools import login, push_notification, replace_account_switch_task

logger = get_logger("MaaEnd 自动代理")

_MAAEND_ACCOUNT_SWITCH_TASK = "AccountSwitch"


def _task_enabled_for_mode(task_name: object, enabled: object, mode: str) -> bool:
    """按送货/日常/自动采集阶段筛选 MaaEnd 任务。"""

    name = str(task_name)
    if mode == "Delivery":
        return bool(enabled) and name in {
            MAAEND_DELIVERY_TASK,
            _MAAEND_ACCOUNT_SWITCH_TASK,
        }
    if mode == "AutoCollect":
        return bool(enabled) and name in {
            MAAEND_AUTO_COLLECT_TASK,
            _MAAEND_ACCOUNT_SWITCH_TASK,
        }
    if mode == "Routine":
        return bool(enabled) and name not in {
            MAAEND_DELIVERY_TASK,
            MAAEND_AUTO_COLLECT_TASK,
        }
    raise ValueError(f"未知 MaaEnd 运行模式: {mode}")


def _select_auto_collect_routes(
    mode: str,
    routes: list[str],
    common_routes: list[str],
    now: datetime,
) -> dict[str, list[str]]:
    """按东四区日期选择本轮需要执行的自动采集路线。"""

    cycle_index = now.date().toordinal() % 3

    def select_routes(option_name: str, selected: list[str]) -> list[str]:
        selected_set = set(selected)
        return [
            route
            for index, route in enumerate(MAAEND_AUTO_COLLECT_ROUTE_OPTIONS[option_name])
            if route in selected_set
            and (
                mode == "Concentrated" and cycle_index == 0
                or mode == "Distributed" and index % 3 == cycle_index
            )
        ]

    return {
        "AutoCollectRoutes": select_routes("AutoCollectRoutes", routes),
        "AutoCollectCommonRoutes": select_routes(
            "AutoCollectCommonRoutes", common_routes
        ),
    }


class AutoProxyTask(TaskExecuteBase):
    """MaaEnd 自动代理模式"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: MaaEndConfig,
        user_config: MultipleConfig[MaaEndUserConfig],
        emulator_manager: DeviceBase | None,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.emulator_manager = emulator_manager
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config = self.user_config[self.cur_user_uid]
        self.check_result = "-"
        self.account_switch_task_name = ""
        self.color_match_failed_message: str | None = None
        self.retryable = True
        self.mode = "Routine"
        self.run_book: dict[str, bool] = {mode: False for mode in MAAEND_RUN_MOOD_BOOK}
        self.task_dict: dict[str, dict[str, bool]] | None = None
        self.unique_task: dict[str, str] = {}
        self.maaend_config_file: Path | None = None
        self.account_switch_mode: str | None = None
        self.auto_collect_run_at: datetime | None = None
        self.auto_collect_routes: dict[str, list[str]] = {
            option_name: [] for option_name in MAAEND_AUTO_COLLECT_ROUTE_OPTIONS
        }

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

        account_id = str(self.cur_user_config.get("Info", "Id")).strip()
        if (
            self.script_config.get("Run", "AccountSwitchMethod") == "MAAEND"
            and account_id
        ):
            if len(account_id) < 4 or not account_id[-4:].isdigit():
                self.cur_user_item.status = "异常"
                return (
                    "MAAEND 内置账号切换需要账号末四位为数字，"
                    "请检查账号ID或改用 MAS 自建账号切换"
                )

        config_mode = maaend_config_mode(self.cur_user_config.get("Info", "Mode"))
        if config_mode == "直控":
            config_file = (
                Path.cwd() / f"data/{self.script_info.script_id}/Temp/mxu-MaaEnd.json"
            )
        else:
            config_file = (
                maaend_mas_config_dir(
                    self.script_info.script_id,
                    str(self.cur_user_uid),
                    config_mode,
                )
                / "mxu-MaaEnd.json"
            )
        self.maaend_config_file = config_file
        if not config_file.exists():
            self.cur_user_item.status = "异常"
            return "未找到 MaaEnd 配置文件, 请先完成「MaaEnd 配置」步骤"

        return "Pass"

    async def prepare(self):

        self.maaend_process_manager = ProcessManager()
        if self.emulator_manager is None:
            self.game_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()
        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now()

        self.maaend_root_path = Path(self.script_config.get("Info", "Path"))
        self.maaend_exe_path = self.maaend_root_path / "MaaEnd.exe"
        self.maaend_set_path = self.maaend_root_path / "config"
        self.maaend_cache_path = self.maaend_root_path / "cache"
        self.maaend_log_path = self.maaend_root_path / "debug/maa.log"

        self.maaend_log_monitor = LogMonitor(
            (1, 23), "%Y-%m-%d %H:%M:%S.%f", self.check_log
        )

        if self.cur_user_config.get("Info", "IfQuickConfig"):
            auto_collect_mode = self.cur_user_config.get("Task", "AutoCollectMode")
            if auto_collect_mode not in MAAEND_AUTO_COLLECT_MODES:
                auto_collect_mode = MAAEND_AUTO_COLLECT_MODES[0]
            self.auto_collect_run_at = datetime.now(tz=UTC4)
            self.auto_collect_routes = _select_auto_collect_routes(
                auto_collect_mode,
                list(self.cur_user_config.get("Task", "AutoCollectRoutes") or []),
                list(
                    self.cur_user_config.get("Task", "AutoCollectCommonRoutes") or []
                ),
                self.auto_collect_run_at,
            )

        mode_enabled = {
            mode: self._mode_has_enabled_tasks(mode) for mode in MAAEND_RUN_MOOD_BOOK
        }
        self.account_switch_mode = next(
            (mode for mode, enabled in mode_enabled.items() if enabled),
            None,
        )
        self.run_book = {mode: not enabled for mode, enabled in mode_enabled.items()}

    def _source_maaend_tasks(self) -> list[dict[str, object]] | None:
        """读取当前用户所选 MaaEnd 实例的任务列表。"""

        if self.maaend_config_file is None:
            return None
        try:
            source_config = read_file(self.maaend_config_file)
        except (OSError, TypeError, ValueError):
            return None
        if not isinstance(source_config, dict):
            return None

        instances = source_config.get("instances")
        if not isinstance(instances, list) or not instances:
            return None

        selected_instance = None
        for instance in instances:
            if not isinstance(instance, dict):
                continue
            if instance.get("id") == "automas" or instance.get("name") == "AUTO-MAS":
                selected_instance = instance
                break
            if instance.get("id") == source_config.get("lastActiveInstanceId"):
                selected_instance = instance
                break
        if selected_instance is None:
            selected_instance = instances[0]
        tasks = selected_instance.get("tasks")
        if not isinstance(tasks, list):
            return None
        return [task for task in tasks if isinstance(task, dict)]

    def _mode_has_enabled_tasks(self, mode: str) -> bool:
        """判断某阶段是否有任务，空阶段直接视为完成。"""

        if self.cur_user_config.get("Info", "IfQuickConfig"):
            if mode == "Delivery":
                return bool(self.cur_user_config.get("Task", "IfSeizeDeliveryJobs"))
            if mode == "AutoCollect":
                return bool(
                    self.cur_user_config.get("Task", "IfAutoCollect")
                    and any(self.auto_collect_routes.values())
                )
            return any(
                bool(self.cur_user_config.get("Task", f"If{task_name}"))
                for task_name in MAAEND_TASKS
            )

        tasks = self._source_maaend_tasks()
        if tasks is None:
            # 配置读取失败时交给 MaaEnd 执行并由日志判定，避免误跳过用户任务。
            return True
        if mode == "Delivery":
            return any(
                str(task.get("taskName", "")) == MAAEND_DELIVERY_TASK
                and bool(task.get("enabled", False))
                for task in tasks
            )
        if mode == "AutoCollect":
            return any(
                str(task.get("taskName", "")) == MAAEND_AUTO_COLLECT_TASK
                and bool(task.get("enabled", False))
                for task in tasks
            )
        return any(
            _task_enabled_for_mode(
                task.get("taskName"), task.get("enabled", False), mode
            )
            for task in tasks
            if not str(task.get("taskName", "")).startswith("__MXU_")
            and str(task.get("taskName", "")) != _MAAEND_ACCOUNT_SWITCH_TASK
        )

    async def main_task(self):
        """自动代理模式主逻辑"""

        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        if self.cur_user_config.get("Data", "LastProxyDate") != self.curdate:
            await self.cur_user_config.set("Data", "LastProxyDate", self.curdate)
            await self.cur_user_config.set("Data", "ProxyTimes", 0)

        self.check_result = await self.check()
        if self.check_result != "Pass":
            if self.cur_user_item.status == "异常":
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error",
                        message=f"用户 {self.cur_user_item.name} 检查未通过: {self.check_result}",
                    ),
                )
            return

        await self.prepare()

        logger.info(f"开始代理用户 {self.cur_user_uid}")
        self.cur_user_item.status = "运行"

        run_times_limit = self.script_config.get("Run", "RunTimesLimit")
        maaend_update_retry_used = False
        i = 0
        mode_order = list(MAAEND_RUN_MOOD_BOOK)
        mode_index = 0
        while mode_index < len(mode_order):
            self.mode = mode_order[mode_index]
            if self.run_book[self.mode]:
                mode_index += 1
                i = 0
                maaend_update_retry_used = False
                self.task_dict = None
                continue
            if i >= run_times_limit:
                logger.warning(
                    f"用户: {self.cur_user_uid} - {MAAEND_RUN_MOOD_BOOK[self.mode]}阶段重试次数已耗尽"
                )
                mode_index += 1
                i = 0
                maaend_update_retry_used = False
                self.task_dict = None
                continue
            i += 1
            self.retryable = True
            logger.info(
                f"用户 {self.cur_user_item.name} - {MAAEND_RUN_MOOD_BOOK[self.mode]}"
                f"阶段尝试次数: {i}/{run_times_limit}"
            )
            self.log_start_time = datetime.now()
            self.cur_user_item.log_record[self.log_start_time] = self.cur_user_log = (
                LogRecord()
            )

            # 执行任务前脚本
            if self.cur_user_config.get("Info", "IfScriptBeforeTask"):
                await execute_script_task(
                    Path(self.cur_user_config.get("Info", "ScriptBeforeTask")),
                    "脚本前任务",
                )

            self.script_info.log = "正在启动游戏..."
            # 启动游戏
            try:
                if self.emulator_manager is None:
                    if is_process_running("Endfield.exe"):
                        logger.info(
                            "检测到终末地客户端进程已在运行，跳过由 MAS 重复启动游戏"
                        )
                        self.script_info.log = "检测到游戏已在运行，跳过启动游戏"
                    else:
                        logger.info(
                            f"启动终末地: {self.script_config.get('Game', 'Path')} - {self.script_config.get('Game', 'Arguments')}"
                        )
                        await self.game_process_manager.open_process(
                            self.script_config.get("Game", "Path"),
                            *str(self.script_config.get("Game", "Arguments")).split(
                                " "
                            ),
                        )
                        await asyncio.sleep(self.script_config.get("Game", "WaitTime"))
                    emulator_info = None
                else:
                    logger.info(
                        f"启动模拟器: {self.script_config.get('Game', 'EmulatorIndex')}"
                    )
                    emulator_info = await self.emulator_manager.open(
                        self.script_config.get("Game", "EmulatorIndex"),
                        "com.hypergryph.endfield",
                    )
            except Exception as e:
                await self.handle_pre_maaend_error("模拟器启动失败", e)
                continue

            self.script_info.log = (
                "正在启动游戏...\n游戏启动成功\n正在登录「明日方舟：终末地」..."
            )

            account_id = str(self.cur_user_config.get("Info", "Id")).strip()
            account_switch_method = self.script_config.get("Run", "AccountSwitchMethod")
            if account_switch_method == "MAS":
                try:
                    if account_id:
                        await login(account_id, emulator_info)
                    logger.info(f"用户 {self.cur_user_item.user_id} 登录成功")
                except RuntimeError as e:
                    await self.handle_pre_maaend_error(
                        "「明日方舟：终末地」登录失败", e
                    )
                    continue
                self.script_info.log = (
                    "正在启动游戏...\n游戏启动成功\n正在登录「明日方舟：终末地」\n"
                    "「明日方舟：终末地」登录成功"
                )
            else:
                if account_id:
                    logger.info(
                        f"用户 {self.cur_user_item.user_id} 将由 MAAEND 内置任务切换账号"
                    )
                    self.script_info.log = (
                        "正在启动游戏...\n游戏启动成功\n将由 MAAEND 执行账号切换"
                    )
                else:
                    logger.info(
                        f"用户 {self.cur_user_item.user_id} 未配置账号，跳过账号切换"
                    )
                    self.script_info.log = (
                        "正在启动游戏...\n游戏启动成功\n未配置账号，跳过账号切换"
                    )

            await self.set_maaend(emulator_info)

            logger.info(f"运行脚本任务: {self.maaend_exe_path}")
            self.wait_event.clear()
            await self.maaend_process_manager.open_process(
                self.maaend_exe_path,
                "--autostart",
                "--instance",
                self.maaend_instance_name,
                "--quit-after-run",
                stdout=asyncio.subprocess.PIPE,
            )
            await asyncio.sleep(3)  # 等待 MaaEnd 启动完成
            # 静默模式隐藏 MaaEnd 窗口
            if Config.get("Function", "IfSilence"):
                if await self.maaend_process_manager.minimize_window():
                    logger.success("静默模式: 成功隐藏 MaaEnd 窗口")
                else:
                    logger.warning("静默模式: 隐藏 MaaEnd 窗口失败")
            if self.emulator_manager is None:
                if await self.game_process_manager.activate_window():
                    logger.success("前置 Endfield 窗口成功")
                else:
                    logger.warning("前置 Endfield 窗口失败")

            await asyncio.sleep(1)
            if isinstance(
                self.maaend_process_manager.main_process, asyncio.subprocess.Process
            ):
                await self.maaend_log_monitor.start_monitor_process(
                    self.maaend_process_manager.main_process, "stdout"
                )
                if self.maaend_log_monitor.task is not None:
                    self.maaend_log_monitor.task.add_done_callback(
                        lambda _: self.wait_event.set()
                    )
            maaend_update_monitor_task = asyncio.create_task(
                self.monitor_maaend_update_download()
            )
            await self.wait_event.wait()
            if (
                self.maaend_log_monitor.task is not None
                and self.maaend_log_monitor.task.done()
            ):
                await self.check_log(
                    self.maaend_log_monitor.log_contents,
                    self.maaend_log_monitor.latest_time,
                    if_stream_end=True,
                )
            maaend_update_monitor_task.cancel()
            try:
                await maaend_update_monitor_task
            except asyncio.CancelledError:
                pass
            await self.maaend_log_monitor.stop()

            if self.cur_user_log.status == "Success!":
                self.run_book[self.mode] = True
                self.script_info.log = (
                    f"检测到 MaaEnd 完成{MAAEND_RUN_MOOD_BOOK[self.mode]}任务\n"
                    "正在等待相关程序结束"
                )

                # 中止相关程序
                await self.maaend_process_manager.kill()
                await System.kill_process(self.maaend_exe_path)

                mode_index += 1
                i = 0
                maaend_update_retry_used = False
                self.task_dict = None

            else:
                if self.cur_user_log.status == "MaaEnd 正在更新":
                    logger.info(
                        f"MaaEnd 更新流程已退出，准备自动重试{MAAEND_RUN_MOOD_BOOK[self.mode]}阶段"
                    )
                    self.script_info.log = "MaaEnd 更新完成，正在自动重试当前阶段"

                    # MaaEnd 更新后只重启脚本本体，保留 Endfield 进程减少重试成本。
                    await self.maaend_process_manager.kill()
                    await System.kill_process(self.maaend_exe_path)

                    if not maaend_update_retry_used:
                        maaend_update_retry_used = True
                        i -= 1
                        await asyncio.sleep(3)
                        continue

                    logger.warning("MaaEnd 更新后已自动重试一次，跳过后续重试")
                    i = run_times_limit
                    continue

                logger.warning(
                    f"用户: {self.cur_user_uid} - 代理任务异常: {self.cur_user_log.status}"
                )
                self.script_info.log = f"{self.cur_user_log.status}\n正在中止相关程序"

                # 中止相关程序
                await self.kill_managed_process()

                await Notify.push_plyer(
                    "用户自动代理出现异常！",
                    f"用户 {self.cur_user_item.name} 的自动代理出现一次异常",
                    f"{self.cur_user_item.name}的自动代理出现异常",
                    3,
                )

                if not self.retryable:
                    logger.info("检测到游戏画面参数错误，跳过后续重试")
                    i = run_times_limit

        if self.cur_user_config.get("Info", "IfScriptAfterTask"):
            await execute_script_task(
                Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
                "脚本后任务",
            )

    async def handle_pre_maaend_error(
        self, error_message: str, e: Exception | None = None
    ):

        if e is None:
            logger.warning(f"用户: {self.cur_user_uid} - {error_message}")
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=error_message),
            )
        else:
            logger.opt(exception=True).warning(
                f"用户: {self.cur_user_uid} - {error_message}: {e}"
            )
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=f"{error_message}: {e}"),
            )
        self.cur_user_log.content = [f"{error_message}, 无日志记录"]
        self.cur_user_log.status = error_message

        await self.kill_managed_process()

        await Notify.push_plyer(
            "用户自动代理出现异常！",
            f"用户 {self.cur_user_item.name} 自动代理时{error_message}",
            f"{self.cur_user_item.name}的自动代理出现异常",
            3,
        )

    async def kill_managed_process(self) -> None:
        """中止关联进程"""

        try:
            logger.info(f"中止 MaaEnd 进程: {self.maaend_exe_path}")
            await self.maaend_process_manager.kill()
            await System.kill_process(self.maaend_exe_path)
        except Exception as e:
            logger.opt(exception=True).warning(f"中止 MaaEnd 进程失败: {e}")
        try:
            if self.emulator_manager is None:
                logger.info("中止终末地进程")
                await self.game_process_manager.kill()
                await System.kill_process(self.script_config.get("Game", "Path"))
            else:
                logger.info("中止模拟器进程")
                await self.emulator_manager.close(
                    self.script_config.get("Game", "EmulatorIndex")
                )
        except Exception as e:
            logger.opt(exception=True).warning(f"关闭模拟器失败: {e}")

    async def set_maaend(self, device_info: DeviceInfo | None) -> None:
        """写入 MaaEnd 运行前配置"""

        logger.info("开始配置 MaaEnd 运行参数: 自动代理")

        # 配置前关闭可能未正常退出的脚本进程
        await self.maaend_process_manager.kill()
        await System.kill_process(self.maaend_exe_path)

        maaend_local_config = None
        if (self.maaend_set_path / "mxu-MaaEnd.json").exists():
            maaend_local_config = read_file(self.maaend_set_path / "mxu-MaaEnd.json")

        config_mode = maaend_config_mode(self.cur_user_config.get("Info", "Mode"))
        maaend_config_path = (
            Path.cwd() / f"data/{self.script_info.script_id}/Temp"
            if config_mode == "直控"
            else maaend_mas_config_dir(
                self.script_info.script_id,
                str(self.cur_user_uid),
                config_mode,
            )
        )
        maaend_config_file = maaend_config_path / "mxu-MaaEnd.json"
        if not maaend_config_file.exists():
            raise FileNotFoundError(
                "未找到 MaaEnd 配置文件, 请先完成「MaaEnd 配置」步骤"
            )

        shutil.rmtree(self.maaend_set_path, ignore_errors=True)
        shutil.copytree(maaend_config_path, self.maaend_set_path)
        maaend_set = read_file(self.maaend_set_path / "mxu-MaaEnd.json")
        for field in ("version", "interfaceTaskSnapshot"):
            maaend_set.pop(field, None)
            if maaend_local_config is not None and field in maaend_local_config:
                maaend_set[field] = maaend_local_config[field]

        settings = maaend_set.get("settings")
        if isinstance(settings, dict):
            settings.pop("welcomeShownHash", None)

        if maaend_local_config is not None:
            local_settings = maaend_local_config.get("settings")
            if (
                isinstance(local_settings, dict)
                and "welcomeShownHash" in local_settings
            ):
                maaend_set.setdefault("settings", {})["welcomeShownHash"] = (
                    local_settings["welcomeShownHash"]
                )

        instances = maaend_set.get("instances")
        if not isinstance(instances, list) or len(instances) == 0:
            raise ValueError(
                "MaaEnd 配置文件中未找到可运行实例，请先完成「MaaEnd 配置」步骤"
            )

        maaend_instance = None
        for instance in instances:
            if instance.get("id") == "automas" or instance.get("name") == "AUTO-MAS":
                maaend_instance = instance
                break
            if instance.get("id") == maaend_set.get("lastActiveInstanceId"):
                maaend_instance = instance
                break
        if maaend_instance is None:
            maaend_instance = instances[0]
        self.maaend_instance_name = (
            maaend_instance.get("name")
            or maaend_instance.get("customName")
            or "AUTO-MAS"
        )
        if device_info is not None:
            from app.core import MaaFWManager

            maaend_instance["savedDevice"] = {
                "adbDeviceName": (await MaaFWManager.convert_adb(device_info)).name
            }
        maaend_tasks = maaend_instance["tasks"]

        account_id = str(self.cur_user_config.get("Info", "Id")).strip()
        account_switch_method = self.script_config.get("Run", "AccountSwitchMethod")
        replace_account_switch_task(
            tasks=maaend_tasks,
            account_id=(account_id if account_switch_method == "MAAEND" else ""),
            controller_type=str(self.script_config.get("Game", "ControllerType")),
            task_id=f"mas{self.cur_user_uid.hex[:4]}",
        )

        # 加载 i18n 配置
        settings = maaend_set["settings"]
        if settings["language"] == "system":
            settings["language"] = "zh-CN"
        maaend_i18n = await asyncio.to_thread(
            load_maaend_task_i18n,
            self.maaend_root_path,
            str(settings["language"]),
        )
        maaend_interface_i18n = await asyncio.to_thread(
            load_maaend_interface_i18n,
            self.maaend_root_path,
            str(settings["language"]),
        )
        self.account_switch_task_name = maaend_i18n["AccountSwitch"]
        self.color_match_failed_message = maaend_interface_i18n[
            "task.SceneManager.focus.color_match_failed_prefix"
        ]

        if_quick_config = self.cur_user_config.get("Info", "IfQuickConfig")

        def get_task_book_name(task: dict[str, object]) -> str:
            if not if_quick_config:
                return str(
                    task.get("customName")
                    or maaend_i18n.get(str(task["taskName"]), str(task["taskName"]))
                )
            return maaend_i18n.get(str(task["taskName"]), str(task["taskName"]))

        sanity_task_key = {}
        sanity_task_type = ""
        target_task_name = ""
        if if_quick_config:
            sanity_task_key, _ = self.cur_user_config.get_effective_sanity_task_key()
            sanity_task_type = sanity_task_key["SanityTaskType"]
            target_task_name = (
                "AutoEssence" if sanity_task_type == "Essence" else "ProtocolSpace"
            )

        if self.task_dict is None:
            # 首次运行时按 MAS 配置生成本轮任务表，后续重试只收束这张表
            self.task_dict = {}
            sanity_configured = False
            sanity_switch_enabled = if_quick_config and self.cur_user_config.get(
                "Task", "IfSanity"
            )
            target_sanity_task_exists = any(
                task.get("taskName") == target_task_name for task in maaend_tasks
            )
            sanity_missing = sanity_switch_enabled and not target_sanity_task_exists
            sanity_managed = if_quick_config and (
                not sanity_switch_enabled or target_sanity_task_exists
            )

            for task in maaend_tasks:
                task_name_value = str(task.get("taskName"))
                if task_name_value.startswith("__MXU_"):
                    continue

                task_enabled = bool(task.get("enabled", False))
                if if_quick_config:
                    if task_name_value in ("ProtocolSpace", "AutoEssence"):
                        if sanity_managed:
                            task_enabled = (
                                sanity_switch_enabled
                                and task_name_value == target_task_name
                                and not sanity_configured
                            )
                            if task_enabled:
                                sanity_configured = True
                    elif task_name_value == MAAEND_DELIVERY_TASK:
                        task_enabled = self.cur_user_config.get(
                            "Task", f"If{MAAEND_DELIVERY_TASK}"
                        )
                    elif task_name_value == MAAEND_AUTO_COLLECT_TASK:
                        task_enabled = bool(
                            self.cur_user_config.get("Task", "IfAutoCollect")
                            and any(self.auto_collect_routes.values())
                        )
                    elif task_name_value in MAAEND_TASKS:
                        task_enabled = self.cur_user_config.get(
                            "Task", f"If{task_name_value}"
                        )

                task_enabled = _task_enabled_for_mode(
                    task_name_value, task_enabled, self.mode
                )
                if (
                    task_name_value == _MAAEND_ACCOUNT_SWITCH_TASK
                    and self.mode != self.account_switch_mode
                ):
                    task_enabled = False

                task_name = get_task_book_name(task)
                if task_name not in self.task_dict:
                    self.task_dict[task_name] = {}
                self.task_dict[task_name][task["id"]] = task_enabled

            if sanity_missing:
                warning_message = (
                    f"用户 {self.cur_user_item.name} 当前 MaaEnd 配置中缺少 {target_task_name} 任务，"
                    "已跳过理智任务快速配置"
                )
                logger.warning(warning_message)
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(level="warning", message=warning_message),
                )

        # 按本轮任务表写回 MaaEnd 运行配置
        for task in maaend_tasks:
            task_name_value = str(task.get("taskName"))
            if task_name_value.startswith("__MXU_"):
                continue

            task_name = get_task_book_name(task)
            if task_name in self.task_dict and task["id"] in self.task_dict[task_name]:
                task["enabled"] = self.task_dict[task_name][task["id"]]

            if not task.get("enabled", False):
                continue

            if if_quick_config and task_name_value == MAAEND_DELIVERY_TASK:
                task.setdefault("optionValues", {})
                task["optionValues"]["SeizeDeliveryJobsReward"] = {
                    "type": "input",
                    "values": {
                        "Reward": str(
                            self.cur_user_config.get("Task", "SeizeDeliveryJobsReward")
                        )
                    },
                }
                task["optionValues"]["SeizeDeliveryJobsCommissionSource"] = {
                    "type": "select",
                    "caseName": self.cur_user_config.get(
                        "Task", "SeizeDeliveryJobsCommissionSource"
                    ),
                }
            elif if_quick_config and task_name_value == MAAEND_AUTO_COLLECT_TASK:
                task.setdefault("optionValues", {})
                task["optionValues"]["AutoCollectSchedule"] = {
                    "type": "checkbox",
                    "caseNames": list(MAAEND_AUTO_COLLECT_SCHEDULE_OPTIONS),
                }
                for option_name, route_names in self.auto_collect_routes.items():
                    task["optionValues"][option_name] = {
                        "type": "checkbox",
                        "caseNames": route_names,
                    }
            elif (
                if_quick_config
                and task_name_value == target_task_name
                and target_task_name == "ProtocolSpace"
            ):
                task.setdefault("optionValues", {})
                task["optionValues"]["ProtocolSpaceTab"] = {
                    "type": "select",
                    "caseName": sanity_task_type,
                }
                for option in (
                    "OperatorProgression",
                    "WeaponProgression",
                    "CrisisDrills",
                ):
                    task["optionValues"][option] = {
                        "type": "select",
                        "caseName": sanity_task_key[option],
                    }
                reward_option = sanity_task_key.get("RewardsSetOption")
                if reward_option == "RewardsSetA":
                    if sanity_task_type == "OperatorProgression":
                        if sanity_task_key["OperatorProgression"] == "OperatorEXP":
                            task["optionValues"]["OperatorEXPRewardsSetOption"] = {
                                "type": "select",
                                "caseName": "CognitiveCarriers",
                            }
                        elif sanity_task_key["OperatorProgression"] == "Promotions":
                            task["optionValues"]["PromotionsRewardsSetOption"] = {
                                "type": "select",
                                "caseName": "Protoset",
                            }
                        elif sanity_task_key["OperatorProgression"] == "SkillUp":
                            task["optionValues"]["SkillUpRewardsSetOption"] = {
                                "type": "select",
                                "caseName": "Protohedron",
                            }
                    elif (
                        sanity_task_type == "WeaponProgression"
                        and sanity_task_key["WeaponProgression"] == "WeaponTune"
                    ):
                        task["optionValues"]["WeaponTuneRewardsSetOption"] = {
                            "type": "select",
                            "caseName": "HeavyCastDie",
                        }
                elif reward_option == "RewardsSetB":
                    if sanity_task_type == "OperatorProgression":
                        if sanity_task_key["OperatorProgression"] == "OperatorEXP":
                            task["optionValues"]["OperatorEXPRewardsSetOption"] = {
                                "type": "select",
                                "caseName": "AdvancedCombatRecord",
                            }
                        elif sanity_task_key["OperatorProgression"] == "Promotions":
                            task["optionValues"]["PromotionsRewardsSetOption"] = {
                                "type": "select",
                                "caseName": "Protodisk",
                            }
                        elif sanity_task_key["OperatorProgression"] == "SkillUp":
                            task["optionValues"]["SkillUpRewardsSetOption"] = {
                                "type": "select",
                                "caseName": "Protoprism",
                            }
                    elif (
                        sanity_task_type == "WeaponProgression"
                        and sanity_task_key["WeaponProgression"] == "WeaponTune"
                    ):
                        task["optionValues"]["WeaponTuneRewardsSetOption"] = {
                            "type": "select",
                            "caseName": "CastDie",
                        }
            elif (
                if_quick_config
                and task_name_value == target_task_name
                and target_task_name == "AutoEssence"
            ):
                task.setdefault("optionValues", {})
                task["optionValues"].pop("AutoEssenceSpecifiedLocation", None)
                task["optionValues"]["AutoEssenceChooseLocation"] = {
                    "type": "checkbox",
                    "caseNames": [sanity_task_key["AutoEssenceSpecifiedLocation"]],
                }

        write_file(self.maaend_set_path / "mxu-MaaEnd.json", maaend_set)
        logger.success("MaaEnd 运行参数配置完成: 自动代理")

    def has_maaend_local_install_file(self) -> bool:
        """检测 MaaEnd 本地更新缓存中是否存在下载中的安装文件。"""

        try:
            if not self.maaend_cache_path.exists():
                return False
            for cache_file in self.maaend_cache_path.glob("*.downloading"):
                if cache_file.is_file():
                    logger.info(f"检测到 MaaEnd 本地安装文件正在下载: {cache_file}")
                    return True
        except OSError as e:
            logger.warning(f"检测 MaaEnd 本地安装文件失败: {e}")
        return False

    async def monitor_maaend_update_download(self) -> None:
        """低频检测 MaaEnd 更新下载状态，不中断 MaaEnd 自身更新流程。"""

        if_maaend_updating = False
        while not self.wait_event.is_set():
            if not if_maaend_updating and self.has_maaend_local_install_file():
                self.cur_user_log.content = ["检测到 MaaEnd 本地安装文件正在下载"]
                self.cur_user_log.status = "MaaEnd 正在更新"
                self.script_info.log = "检测到 MaaEnd 正在更新，正在等待更新进程退出"
                if_maaend_updating = True

            if if_maaend_updating and not await self.maaend_process_manager.is_running():
                logger.info("MaaEnd 更新进程已退出，后台检测释放日志锁")
                self.wait_event.set()
                return

            await asyncio.sleep(5)

    async def check_log(
        self,
        log_content: list[str],
        latest_time: datetime,
        if_stream_end: bool = False,
    ) -> None:
        """日志回调"""

        if self.cur_user_log.status == "MaaEnd 正在更新":
            if log_content:
                self.cur_user_log.content = log_content
            if if_stream_end:
                logger.info("MaaEnd 更新进程已退出，日志锁已释放")
                self.wait_event.set()
            elif self.is_log_stalled(
                latest_time,
                minutes=self.script_config.get("Run", "RunTimeLimit"),
                key="update_download",
            ):
                logger.warning("MaaEnd 更新进程超时，日志锁已释放")
                self.cur_user_log.status = "MaaEnd 更新超时"
                self.wait_event.set()
            return

        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log
        if "资源加载失败" in log:
            self.cur_user_log.status = "MaaEnd 资源加载失败"
        elif "快捷键开始任务：失败" in log:
            self.cur_user_log.status = "MaaEnd 任务启动失败"
        elif "resolution check failed" in log:
            self.cur_user_log.status = "游戏分辨率设置错误，请重设分辨率比例为16:9"
            self.retryable = False
        elif self.color_match_failed_message and self.color_match_failed_message in log:
            self.cur_user_log.status = "MaaEnd 颜色识别失败，请关闭滤镜或 HDR"
            self.retryable = False
        elif f"任务失败: {self.account_switch_task_name}" in log:
            self.cur_user_log.status = "MaaEnd 账号切换失败"
        elif if_stream_end:
            if self.task_dict is None:
                self.cur_user_log.status = "MaaEnd 未加载任何任务"
            else:
                try:
                    task_name = ""
                    task_index = {
                        k: {"index": 0, "list": list(v.keys())}
                        for k, v in self.task_dict.items()
                    }
                    for log_line in self.cur_user_log.content:
                        match = re.search(r"任务开始:\s*(.+)", log_line)
                        task_name = match.group(1) if match else task_name
                        if (
                            task_name in self.task_dict
                            and f"任务完成: {task_name}" in log_line
                        ):
                            self.task_dict[task_name][
                                task_index[task_name]["list"][
                                    task_index[task_name]["index"]
                                ]
                            ] = False
                            task_index[task_name]["index"] += 1
                        elif f"任务失败: {task_name}" in log_line:
                            task_index[task_name]["index"] += 1

                    unfinished_tasks = {}
                    for task_name, task_status in self.task_dict.items():
                        task_ids = [
                            task_id
                            for task_id, enabled in task_status.items()
                            if enabled
                        ]
                        if task_ids:
                            unfinished_tasks[task_name] = task_ids

                    if unfinished_tasks:
                        logger.info(f"MaaEnd 未完成任务列表: {unfinished_tasks}")
                        self.cur_user_log.status = (
                            f"MaaEnd 部分任务执行失败: {'、'.join(unfinished_tasks)}"
                        )
                    else:
                        self.cur_user_log.status = "Success!"
                except Exception:
                    self.cur_user_log.status = "MaaEnd 任务执行情况解析失败"

        elif self.is_log_stalled(
            latest_time, minutes=self.script_config.get("Run", "RunTimeLimit")
        ):
            self.cur_user_log.status = "MaaEnd 进程超时"
        else:
            self.cur_user_log.status = "MaaEnd 正常运行中"

        logger.debug(f"MaaEnd 日志分析结果: {self.cur_user_log.status}")
        if self.cur_user_log.status != "MaaEnd 正常运行中":
            logger.info(f"MaaEnd 任务结果: {self.cur_user_log.status}, 日志锁已释放")
            self.wait_event.set()

    async def final_task(self):

        if self.check_result != "Pass":
            return

        await self.maaend_log_monitor.stop()
        if (
            self.script_info.current_index == len(self.script_info.user_list) - 1
            and all(self.run_book.values())
            and not self.script_config.get("Game", "CloseOnFinish")
        ):
            try:
                logger.info(f"中止 MaaEnd 进程: {self.maaend_exe_path}")
                await self.maaend_process_manager.kill()
                await System.kill_process(self.maaend_exe_path)
            except Exception as e:
                logger.opt(exception=True).warning(f"中止 MaaEnd 进程失败: {e}")
        else:
            await self.kill_managed_process()

        user_logs_list = []
        for t, log_item in self.cur_user_item.log_record.items():
            dt = t.astimezone(UTC4)
            log_path = Config.build_history_log_path(
                script_name=self.script_info.name,
                user_name=self.cur_user_item.name,
                log_time=dt,
            )

            if log_item.status == "MaaEnd 正常运行中":
                log_item.status = "任务被用户手动中止"

            if len(log_item.content) == 0:
                log_item.content = ["未捕获到任何日志内容"]
                log_item.status = "未捕获到日志"

            if log_item.status == "MaaEnd 正在更新":
                continue

            await Config.save_maaend_log(log_path, log_item.content, log_item.status)
            user_logs_list.append(log_path.with_suffix(".json"))

        latest_log_status = (
            next(reversed(self.cur_user_item.log_record.values())).status
            if self.cur_user_item.log_record
            else ""
        )
        if_maaend_updating = latest_log_status == "MaaEnd 正在更新"
        update_log_times = [
            t
            for t, log_item in self.cur_user_item.log_record.items()
            if log_item.status == "MaaEnd 正在更新"
        ]
        for t in update_log_times:
            self.cur_user_item.log_record.pop(t, None)

        statistics = await Config.merge_statistic_info(user_logs_list)
        statistics["user_info"] = self.cur_user_item.name
        statistics["start_time"] = self.user_start_time.strftime("%Y-%m-%d %H:%M:%S")
        statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        statistics["user_result"] = (
            "代理任务全部完成"
            if all(self.run_book.values())
            else self.cur_user_item.result
        )

        success_symbol = "√" if all(self.run_book.values()) else "X"

        if user_logs_list:
            try:
                await push_notification(
                    "统计信息",
                    f"{datetime.now().strftime('%m-%d')} |{success_symbol}|  {self.cur_user_item.name} 的自动代理统计报告",
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

        if all(self.run_book.values()):
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
            logger.success(f"用户 {self.cur_user_uid} 的自动代理任务已完成")
            await Notify.push_plyer(
                "成功完成一个自动代理任务！",
                f"已完成用户 {self.cur_user_item.name} 的 MaaEnd 自动代理任务",
                f"已完成 {self.cur_user_item.name} 的 MaaEnd 自动代理任务",
                3,
            )
        elif if_maaend_updating:
            logger.info(f"用户 {self.cur_user_uid} 的 MaaEnd 正在更新")
            self.cur_user_item.status = "MaaEnd 正在更新"
        else:
            await self.cur_user_config.set("Data", "LastProxyStatus", "失败")
            logger.warning(f"用户 {self.cur_user_uid} 的自动代理任务未完成")
            self.cur_user_item.status = "异常"

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"自动代理任务出现异常: {e}")
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=f"自动代理任务出现异常: {e}"),
        )
