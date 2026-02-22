#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import uuid
import shlex
import shutil
import asyncio
import importlib.util
import sys
from types import ModuleType
from hashlib import sha1
from pathlib import Path
from contextlib import suppress
from datetime import datetime, timedelta

from app.core import Config, HookScope, hookable
from app.models.task import TaskExecuteBase, ScriptItem, LogRecord
from app.models.ConfigBase import MultipleConfig
from app.models.config import GeneralConfig, GeneralUserConfig
from app.models.emulator import DeviceBase
from app.services import Notify, System
from app.utils import get_logger, LogMonitor, ProcessManager, ProcessInfo, strptime
from app.utils.constants import UTC4
from .tools import execute_script_task

logger = get_logger("通用脚本自动代理")


def _load_hook_module_from_path(file_path: str) -> tuple[ModuleType | None, str | None]:
    """从 .py 文件路径动态加载模块。

    返回 (module, warning)。失败时 module 为 None，warning 为说明文本。
    """
    p = Path(file_path)
    if not p.exists() or not p.is_file():
        return None, "文件不存在或不是文件"
    if p.suffix.lower() != ".py":
        return None, "仅支持 .py 文件"

    try:
        resolved = p.resolve()
    except Exception:
        resolved = p

    # 生成稳定且尽量不冲突的模块名（避免重复 import 相互覆盖）
    digest = sha1(str(resolved).encode("utf-8", errors="ignore")).hexdigest()[:12]
    module_name = f"auto_mas_hook_{p.stem}_{digest}"

    # 每次任务运行都重新加载一份，避免被上次运行的模块状态污染。
    if module_name in sys.modules:
        sys.modules.pop(module_name, None)

    spec = importlib.util.spec_from_file_location(module_name, str(resolved))
    if spec is None or spec.loader is None:
        return None, "无法创建模块加载器"

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        return None, f"导入失败: {type(e).__name__}: {e}"

    return module, None


class AutoProxyTask(TaskExecuteBase):
    """自动代理模式"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: GeneralConfig,
        user_config: MultipleConfig[GeneralUserConfig],
        game_manager: ProcessManager | DeviceBase | None,
    ):
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
        self.check_result = "-"
        self._hook_scope: HookScope | None = None
        self._hook_warnings: list[str] = []

    async def _ensure_hook_scope_loaded(self) -> None:
        """加载并激活 HookScope（范围 A：覆盖整个 AutoProxyTask 生命周期）。

        - HookList 读取自脚本配置 Script.HookList
        - 按列表顺序加载每个 hook 文件
        - 任意 hook 加载/注册失败：记录 warning，继续下一个
        """
        if self._hook_scope is not None:
            return

        # Script.HookList：允许缺省/None
        hook_list = self.script_config.get("Script", "HookList")
        if hook_list in (None, ""):
            hook_paths: list[str] = []
        elif isinstance(hook_list, list):
            hook_paths = [str(p) for p in hook_list if str(p).strip()]
        else:
            # 允许用户误填为单个字符串
            hook_paths = [str(hook_list)]

        self._hook_warnings = []
        self._hook_scope = HookScope()
        await self._hook_scope.__aenter__()

        if not hook_paths:
            return

        for raw_path in hook_paths:
            module, warn = _load_hook_module_from_path(raw_path)
            if warn:
                msg = f"Hook 加载警告 [{raw_path}]: {warn}"
                self._hook_warnings.append(msg)
                logger.warning(msg)
                continue

            assert module is not None
            register = getattr(module, "register", None)
            if not callable(register):
                msg = f"Hook 加载警告 [{raw_path}]: 未找到可调用的 register(scope, target_cls)"
                self._hook_warnings.append(msg)
                logger.warning(msg)
                continue

            try:
                # 约定：register(scope, target_cls)
                register(self._hook_scope, self.__class__)
            except Exception as e:
                msg = f"Hook 注册警告 [{raw_path}]: {type(e).__name__}: {e}"
                self._hook_warnings.append(msg)
                logger.warning(msg)
                continue

    async def check(self) -> str:
        if self.script_config.get(
            "Run", "ProxyTimesLimit"
        ) != 0 and self.cur_user_config.get(
            "Data", "ProxyTimes"
        ) >= self.script_config.get("Run", "ProxyTimesLimit"):
            self.cur_user_item.status = "跳过"
            return "今日代理次数已达上限, 跳过该用户"

        if not (
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile"
        ).exists():
            self.cur_user_item.status = "异常"
            return (
                "未找到用户的通用脚本配置文件，请先在用户配置页完成 「通用配置」 步骤"
            )
        return "Pass"

    @hookable(name="AutoProxyTask.prepare", allow={"after", "error"})
    async def prepare(self):
        # HookScope 的加载与激活在 main_task 里进行（以便 hook 也能作用于本次 prepare 调用）。
        self.hook = self.script_config.get("Script", "HookList")
        self.general_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()
        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now()

        self.script_root_path = Path(self.script_config.get("Info", "RootPath"))
        self.script_path = Path(self.script_config.get("Script", "ScriptPath"))

        arguments_list = []
        path_list = []

        for argument in [
            part.strip()
            for part in str(self.script_config.get("Script", "Arguments")).split("|")
            if part.strip()
        ]:
            arg_parts = [
                part.strip() for part in argument.split("%", 1) if part.strip()
            ]

            path_list.append(
                (
                    self.script_path / arg_parts[0]
                    if len(arg_parts) > 1
                    else self.script_path
                ).resolve()
            )
            arguments_list.append(shlex.split(arg_parts[-1]))

        self.script_exe_path = path_list[0] if len(path_list) > 0 else self.script_path
        self.script_arguments = arguments_list[0] if len(arguments_list) > 0 else []
        self.script_set_arguments = arguments_list[1] if len(arguments_list) > 1 else []

        self.script_target_process_info = (
            ProcessInfo(
                name=self.script_config.get("Script", "TrackProcessName") or None,
                exe=self.script_config.get("Script", "TrackProcessExe") or None,
                cmdline=shlex.split(
                    self.script_config.get("Script", "TrackProcessCmdline"), posix=False
                )
                or None,
            )
            if self.script_config.get("Script", "IfTrackProcess")
            else None
        )

        self.script_config_path = Path(self.script_config.get("Script", "ConfigPath"))

        self.script_log_path = Path(self.script_config.get("Script", "LogPath"))
        self.log_format = self.script_config.get("Script", "LogPathFormat")
        if self.log_format:
            with suppress(ValueError):
                datetime.strptime(self.script_log_path.stem, self.log_format)
                self.log_format = f"{self.log_format}{self.script_log_path.suffix}"
        else:
            self.log_format = self.script_log_path.name

        self.game_path = Path(self.script_config.get("Game", "Path"))
        self.game_url = self.script_config.get("Game", "URL")
        self.game_process_name = self.script_config.get("Game", "ProcessName")
        self.log_time_range = (
            self.script_config.get("Script", "LogTimeStart") - 1,
            self.script_config.get("Script", "LogTimeEnd"),
        )
        self.success_log = (
            [
                _.strip()
                for _ in self.script_config.get("Script", "SuccessLog").split("|")
            ]
            if self.script_config.get("Script", "SuccessLog")
            else []
        )
        self.error_log = [
            _.strip() for _ in self.script_config.get("Script", "ErrorLog").split("|")
        ]
        self.general_log_monitor = LogMonitor(
            self.log_time_range,
            self.script_config.get("Script", "LogTimeFormat"),
            self.check_log,
        )

        async def Hook_AutoProxyTask_perpare(self):
            return self

        self = await Hook_AutoProxyTask_perpare(self)

        self.run_book = False

    async def main_task(self):
        """自动代理模式主逻辑"""

        # 初始化每日代理状态
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
                    data={
                        "Error": f"用户 {self.cur_user_item.name} 检查未通过: {self.check_result}"
                    },
                )
            return

        # 加载 hooks 并进入作用域（范围 A：直到 final_task/on_crash 退出）
        await self._ensure_hook_scope_loaded()

        await self.prepare()

        logger.info(f"开始代理用户: {self.cur_user_uid}")
        self.cur_user_item.status = "运行"

        for i in range(self.script_config.get("Run", "RunTimesLimit")):
            if self.run_book:
                break
            logger.info(
                f"用户 {self.cur_user_item.name} - 尝试次数: {i + 1}/{self.script_config.get('Run', 'RunTimesLimit')}"
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

            self.script_info.log = "正在启动游戏 / 模拟器"
            # 启动游戏/模拟器
            if self.game_manager is not None:
                try:
                    if isinstance(self.game_manager, ProcessManager):
                        if self.script_config.get("Game", "Type") == "URL":
                            logger.info(
                                f"启动游戏: {self.game_process_name}, 参数{self.game_url}"
                            )
                            await self.game_manager.open_protocol(
                                self.game_url, ProcessInfo(name=self.game_process_name)
                            )
                        else:
                            logger.info(
                                f"启动游戏: {self.game_path}, 参数: {self.script_config.get('Game','Arguments')}"
                            )
                            await self.game_manager.open_process(
                                self.game_path,
                                *str(self.script_config.get("Game", "Arguments")).split(
                                    " "
                                ),
                            )
                            self.script_info.log = f"正在等待游戏完成启动\n请等待{self.script_config.get('Game', 'WaitTime')}s"
                            await asyncio.sleep(
                                self.script_config.get("Game", "WaitTime")
                            )
                    elif isinstance(self.game_manager, DeviceBase):
                        logger.info(
                            f"启动模拟器: {self.script_config.get('Game', 'EmulatorIndex')}"
                        )
                        await self.game_manager.open(
                            self.script_config.get("Game", "EmulatorIndex")
                        )
                except Exception as e:
                    logger.exception(
                        f"用户: {self.cur_user_uid} - 游戏/模拟器启动失败: {e}"
                    )
                    await Config.send_websocket_message(
                        id=self.task_info.task_id,
                        type="Info",
                        data={"Error": f"启动游戏/模拟器时出现异常: {e}"},
                    )
                    self.cur_user_log.content = [
                        "游戏/模拟器启动失败, 通用脚本未实际运行, 无日志记录"
                    ]
                    self.cur_user_log.status = "模拟器启动失败"

                    if isinstance(self.game_manager, ProcessManager):
                        await self.game_manager.kill()
                    elif isinstance(self.game_manager, DeviceBase):
                        await self.game_manager.close(
                            self.script_config.get("Game", "EmulatorIndex")
                        )

                    await Notify.push_plyer(
                        "用户自动代理出现异常！",
                        f"用户 {self.cur_user_item.name} 自动代理时模拟器启动失败",
                        f"{self.cur_user_item.name}的自动代理出现异常",
                        3,
                    )
                    continue

            await self.set_general()
            logger.info(
                f"运行脚本任务: {self.script_exe_path}, 参数: {self.script_arguments}"
            )

            self.wait_event.clear()
            t = datetime.now()
            await self.general_process_manager.open_process(
                self.script_exe_path,
                *self.script_arguments,
                target_process=self.script_target_process_info,
            )

            # 等待日志文件生成
            self.script_info.log = "正在等待脚本日志文件生成"
            if_get_file = False
            while datetime.now() - t < timedelta(minutes=1):
                for log_file in self.script_log_path.parent.iterdir():
                    if log_file.is_file():
                        with suppress(ValueError):
                            if strptime(log_file.name, self.log_format, t) >= t:
                                self.script_log_path = log_file
                                logger.success(
                                    f"成功定位到日志文件: {self.script_log_path}"
                                )
                                if_get_file = True
                                break
                else:
                    await asyncio.sleep(1)

                if if_get_file:
                    break
            else:
                logger.error(f"用户: {self.cur_user_uid} - 未找到日志文件")
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={"Error": "未找到指定日志文件"},
                )
                self.cur_user_log.content = ["未找到日志文件, 无日志记录"]
                self.cur_user_log.status = "未找到日志文件"

                await self.close_script_process()
                await Notify.push_plyer(
                    "用户自动代理出现异常！",
                    f"用户 {self.cur_user_item.name} 自动代理时未找到日志文件",
                    f"{self.cur_user_item.name}的自动代理出现异常",
                    3,
                )
                continue

            await self.general_log_monitor.start_monitor_file(
                self.script_log_path, self.log_start_time
            )
            await self.wait_event.wait()
            await self.general_log_monitor.stop()

            if self.cur_user_log.status == "Success!":
                self.run_book = True
                logger.info(f"用户: {self.cur_user_uid} - 通用脚本进程完成代理任务")
                self.script_info.log = (
                    "检测到通用脚本进程完成代理任务\n正在等待相关程序结束"
                )

                # 中止相关程序
                await self.close_script_process()

                await asyncio.sleep(10)

                # 更新脚本配置文件
                if self.script_config.get("Script", "UpdateConfigMode") in (
                    "Success",
                    "Always",
                ):
                    await self.update_config()

            else:
                logger.error(
                    f"用户: {self.cur_user_uid} - 代理任务异常: {self.cur_user_log.status}"
                )
                self.script_info.log = f"{self.cur_user_log.status}\n正在中止相关程序"

                # 中止相关程序
                await self.close_script_process()

                await Notify.push_plyer(
                    "用户自动代理出现异常！",
                    f"用户 {self.cur_user_item.name} 的自动代理出现一次异常",
                    f"{self.cur_user_item.name}的自动代理出现异常",
                    3,
                )

                await asyncio.sleep(10)
                # 更新脚本配置文件
                if self.script_config.get("Script", "UpdateConfigMode") in (
                    "Failure",
                    "Always",
                ):
                    await self.update_config()

            # 执行任务后脚本
            if self.cur_user_config.get("Info", "IfScriptAfterTask"):
                await execute_script_task(
                    Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
                    "脚本后任务",
                )
            await asyncio.sleep(3)

    async def update_config(self):
        if self.script_config.get("Script", "ConfigPathMode") == "Folder":
            shutil.copytree(
                self.script_config_path,
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile",
                dirs_exist_ok=True,
            )
        elif self.script_config.get("Script", "ConfigPathMode") == "File":
            shutil.copy(
                self.script_config_path,
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile"
                / self.script_config_path.name,
            )
        logger.success("通用脚本配置文件已更新")

    async def close_script_process(self):
        logger.info(f"中止相关程序: {self.script_exe_path}")
        await self.general_process_manager.kill()
        await System.kill_process(self.script_exe_path)
        if self.game_manager is not None:
            logger.info("中止游戏/模拟器进程")
            if isinstance(self.game_manager, ProcessManager):
                await self.game_manager.kill()
                if self.script_config.get(
                    "Game", "Type"
                ) == "Client" and self.script_config.get("Game", "IfForceClose"):
                    await System.kill_process(self.game_path)
            elif isinstance(self.game_manager, DeviceBase):
                await self.game_manager.close(
                    self.script_config.get("Game", "EmulatorIndex"),
                )

    async def set_general(self) -> None:
        """配置通用脚本运行参数"""
        logger.info("开始配置脚本运行参数: 自动代理")

        # 配置前关闭可能未正常退出的脚本进程
        await System.kill_process(self.script_exe_path)

        # 导入配置文件
        if self.script_config.get("Script", "ConfigPathMode") == "Folder":
            shutil.copytree(
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile",
                self.script_config_path,
                dirs_exist_ok=True,
            )
        elif self.script_config.get("Script", "ConfigPathMode") == "File":
            shutil.copy(
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile"
                / self.script_config_path.name,
                self.script_config_path,
            )

        logger.info("脚本运行参数配置完成: 自动代理")

    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """日志回调"""

        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log

        for success_sign in self.success_log:
            if success_sign in log:
                self.cur_user_log.status = "Success!"
                break
        else:
            if datetime.now() - latest_time > timedelta(
                minutes=self.script_config.get("Run", "RunTimeLimit")
            ):
                self.cur_user_log.status = "脚本进程超时"
            else:
                for error_sign in self.error_log:
                    if error_sign in log:
                        self.cur_user_log.status = f"异常日志: {error_sign}"
                        break
                else:
                    if await self.general_process_manager.is_running():
                        self.cur_user_log.status = "通用脚本正常运行中"
                    elif self.success_log:
                        self.cur_user_log.status = "脚本在完成任务前退出"
                    else:
                        self.cur_user_log.status = "Success!"

        logger.debug(f"通用脚本日志分析结果: {self.cur_user_log.status}")
        if self.cur_user_log.status != "通用脚本正常运行中":
            logger.info(f"通用脚本任务结果: {self.cur_user_log.status}, 日志锁已释放")
            self.wait_event.set()

    async def final_task(self):
        if self.check_result != "Pass":
            return

        # 退出 HookScope，避免 ContextVar 泄漏到外层。
        if self._hook_scope is not None:
            try:
                await self._hook_scope.__aexit__(None, None, None)
            finally:
                self._hook_scope = None

        # 结束各子任务
        await self.general_log_monitor.stop()
        await self.general_process_manager.kill()
        await System.kill_process(self.script_exe_path)
        del self.general_process_manager
        del self.general_log_monitor
        if self.game_manager is not None:
            if isinstance(self.game_manager, ProcessManager):
                await self.game_manager.kill()
            elif isinstance(self.game_manager, DeviceBase):
                await self.game_manager.close(
                    self.script_config.get("Game", "EmulatorIndex"),
                )
            del self.game_manager

        user_logs_list = []
        for t, log_item in self.cur_user_item.log_record.items():
            dt = t.replace(tzinfo=datetime.now().astimezone().tzinfo).astimezone(UTC4)
            log_path = (
                Path.cwd()
                / f"history/{dt.strftime('%Y-%m-%d')}/{self.cur_user_item.name}/{dt.strftime('%H-%M-%S')}.log"
            )
            user_logs_list.append(log_path.with_suffix(".json"))

            if log_item.status == "通用脚本正常运行中":
                log_item.status = "任务被用户手动中止"

            if len(log_item.content) == 0:
                log_item.content = ["未捕获到任何日志内容"]
                log_item.status = "未捕获到日志"

            await Config.save_general_log(log_path, log_item.content, log_item.status)

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
            logger.success(f"用户 {self.cur_user_uid} 的自动代理任务已完成")
            await Notify.push_plyer(
                "成功完成一个自动代理任务！",
                f"已完成用户 {self.cur_user_item.name} 的自动代理任务",
                f"已完成 {self.cur_user_item.name} 的自动代理任务",
                3,
            )
        else:
            logger.error(f"用户 {self.cur_user_uid} 的自动代理任务未完成")
            self.cur_user_item.status = "异常"

    async def on_crash(self, e: Exception):
        # 崩溃时也要确保退出 HookScope
        if self._hook_scope is not None:
            try:
                await self._hook_scope.__aexit__(type(e), e, e.__traceback__)
            finally:
                self._hook_scope = None

        self.cur_user_item.status = "异常"
        logger.exception(f"自动代理任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"自动代理任务出现异常: {e}"},
        )
