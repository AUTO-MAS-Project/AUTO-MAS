"""Xxx 原生配置会话任务。"""

from __future__ import annotations

import asyncio
import shutil
import uuid
from contextlib import suppress
from pathlib import Path

from app.core import Config
from app.models.ConfigBase import MultipleConfig
from app.models.config import XxxConfig, XxxUserConfig
from app.models.emulator import DeviceBase
from app.models.task import ScriptItem, TaskExecuteBase
from app.services import System
from app.utils import ProcessManager, get_logger
from .AutoProxy import _split_script_arguments


logger = get_logger("专项显示名称配置")


class ScriptConfigTask(TaskExecuteBase):
    """启动上游配置界面，停止任务时把配置保存回用户副本。"""

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
        self.use_mas_config = True
        if self.cur_user_item.user_id != "Default":
            self.use_mas_config = bool(
                self.user_config[uuid.UUID(self.cur_user_item.user_id)].get(
                    "Info", "IfUseMasConfig"
                )
            )

        self.general_process_manager: ProcessManager | None = None
        self.wait_event: asyncio.Event | None = None
        self.script_path: Path | None = None
        self.script_set_exe_path: Path | None = None
        self.script_set_arguments: list[str] = []
        self.script_config_path: Path | None = None
        self.configuration_started = False

    def _user_config_path(self) -> Path:
        if self.cur_user_item.user_id == "Default":
            return Path.cwd() / "data" / self.script_info.script_id / "Default" / "ConfigFile"
        return (
            Path.cwd()
            / "data"
            / self.script_info.script_id
            / self.cur_user_item.user_id
            / "ConfigFile"
        )

    def _user_config_source_path(self) -> Path:
        user_path = self._user_config_path()
        if self.script_config.get("Script", "ConfigPathMode") == "Folder":
            return user_path
        return user_path / Path(self.script_config.get("Script", "ConfigPath")).name

    def _remove_path(self, path: Path) -> None:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()

    def _copy_path_atomic(self, source: Path, destination: Path, mode: str) -> None:
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

    async def prepare(self) -> None:
        self.general_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()
        self.script_path = Path(self.script_config.get("Script", "ScriptPath"))
        argument_paths, argument_lists = _split_script_arguments(
            self.script_config.get("Script", "Arguments"), self.script_path
        )
        self.script_set_exe_path = (
            argument_paths[1] if len(argument_paths) > 1 else self.script_path
        )
        self.script_set_arguments = argument_lists[1] if len(argument_lists) > 1 else []
        self.script_config_path = Path(self.script_config.get("Script", "ConfigPath"))

    async def set_script_config(self) -> None:
        """配置会话启动前导入用户副本。"""

        if self.script_config_path is None:
            return
        await System.kill_process(self.script_set_exe_path)
        if not self.use_mas_config:
            logger.info("脚本直控配置：跳过导入用户配置")
            return
        source = self._user_config_source_path()
        if not source.exists():
            logger.info("用户副本尚未创建，沿用脚本当前配置并在会话结束时保存")
            return
        self._copy_path_atomic(
            source,
            self.script_config_path,
            self.script_config.get("Script", "ConfigPathMode"),
        )

    async def main_task(self) -> None:
        await self.prepare()
        await self.set_script_config()
        if (
            self.general_process_manager is None
            or self.script_set_exe_path is None
            or self.wait_event is None
        ):
            raise RuntimeError("专项配置会话未完成初始化")
        logger.info(
            f"启动专项配置会话: {self.script_set_exe_path}, 参数: {self.script_set_arguments}"
        )
        await self.general_process_manager.open_process(
            self.script_set_exe_path,
            *self.script_set_arguments,
        )
        self.configuration_started = True
        await self.wait_event.wait()

    async def final_task(self) -> None:
        """停止原生配置进程并按模式保存用户副本。"""

        if self.general_process_manager is not None:
            try:
                await self.general_process_manager.kill()
            except Exception as error:
                logger.warning(f"停止专项配置进程失败: {error}")
        if self.script_set_exe_path is not None:
            try:
                await System.kill_process(self.script_set_exe_path)
            except Exception as error:
                logger.warning(f"清理专项配置进程失败: {error}")

        if (
            not self.configuration_started
            or not self.use_mas_config
            or self.script_config_path is None
        ):
            logger.info("脚本直控配置：跳过保存用户副本")
            return
        self._copy_path_atomic(
            self.script_config_path,
            self._user_config_source_path(),
            self.script_config.get("Script", "ConfigPathMode"),
        )
        logger.success("专项配置已保存到用户副本")

    async def on_crash(self, error: Exception) -> None:
        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"专项配置会话出现异常: {error}")
        if self.script_set_exe_path is not None:
            try:
                await System.kill_process(self.script_set_exe_path)
            except Exception as cleanup_error:
                logger.warning(f"清理专项配置进程失败: {cleanup_error}")
        with suppress(Exception):
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": f"专项配置会话出现异常: {error}"},
            )
