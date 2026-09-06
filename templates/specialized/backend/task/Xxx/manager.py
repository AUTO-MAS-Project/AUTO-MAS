"""Xxx 专项调度器。"""

from __future__ import annotations

import shutil
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from app.core import Config, EmulatorManager
from app.models.ConfigBase import MultipleConfig
from app.models.config import XxxConfig, XxxUserConfig
from app.models.emulator import DeviceBase
from app.models.task import ScriptItem, TaskExecuteBase, UserItem
from app.services import Notify
from app.utils import ProcessManager, get_logger
from .AutoProxy import AutoProxyTask
from .ScriptConfig import ScriptConfigTask


logger = get_logger("专项显示名称调度器")

METHOD_BOOK: dict[str, type[AutoProxyTask | ScriptConfigTask]] = {
    "AutoProxy": AutoProxyTask,
    "ScriptConfig": ScriptConfigTask,
}


class XxxManager(TaskExecuteBase):
    """协调脚本锁、用户列表、任务子类和脚本直控配置快照。"""

    def __init__(self, script_info: ScriptItem) -> None:
        super().__init__()
        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.check_result = "-"
        self.script_config: XxxConfig | None = None
        self.user_config: MultipleConfig[XxxUserConfig] | None = None
        self.script_config_path: Path | None = None
        self.temp_path: Path | None = None
        self.external_config_exists = False
        self.external_config_snapshot_ready = False
        self.emulator_manager: DeviceBase | None = None
        self.game_process_manager: ProcessManager | None = None
        self.begin_time = ""

    async def check(self) -> str:
        """检查任务模式、脚本类型和游戏配置。"""

        if self.task_info.mode not in METHOD_BOOK:
            return "当前专项不支持该任务模式"

        script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        if not isinstance(script_config, XxxConfig):
            return "脚本配置类型错误，请重新选择专项脚本"

        if (
            script_config.get("Script", "IfTrackProcess")
            and not script_config.get("Script", "TrackProcessName")
            and not script_config.get("Script", "TrackProcessExe")
            and not script_config.get("Script", "TrackProcessCmdline")
        ):
            return "请至少填写一项目标进程信息"

        if not script_config.get("Game", "Enabled"):
            return "Pass"
        game_type = script_config.get("Game", "Type")
        if game_type == "Emulator" and (
            script_config.get("Game", "EmulatorId") == "-"
            or script_config.get("Game", "EmulatorIndex") in ("", "-")
        ):
            return "请完成模拟器配置"
        if game_type == "Client" and not Path(script_config.get("Game", "Path")).exists():
            return "请设置游戏或启动器路径"
        if game_type == "URL" and not (
            script_config.get("Game", "URL")
            and script_config.get("Game", "ProcessName")
        ):
            return "请填写游戏 URL 和进程名称"
        return "Pass"

    def _remove_path(self, path: Path) -> None:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()

    def _copy_path_atomic(self, source: Path, destination: Path, mode: str) -> None:
        """恢复直控配置时先写临时路径，再替换目标。"""

        if mode == "Folder":
            temporary = destination.with_name(destination.name + ".tmp")
            shutil.rmtree(temporary, ignore_errors=True)
            temporary.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, temporary, dirs_exist_ok=True)
            self._remove_path(destination)
            temporary.rename(destination)
            return

        temporary = destination.with_name(destination.name + ".tmp")
        if temporary.exists():
            temporary.unlink()
        temporary.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, temporary)
        temporary.replace(destination)

    def _snapshot_external_config(self) -> None:
        """保存脚本直控配置，隔离多个用户之间的配置变更。"""

        if self.script_config is None or self.script_config_path is None:
            return
        self.temp_path = Path.cwd() / "data" / self.script_info.script_id / "Temp" / "manager"
        shutil.rmtree(self.temp_path, ignore_errors=True)
        self.external_config_exists = self.script_config_path.exists()
        self.temp_path.mkdir(parents=True, exist_ok=True)
        if self.external_config_exists:
            if self.script_config.get("Script", "ConfigPathMode") == "Folder":
                shutil.copytree(self.script_config_path, self.temp_path, dirs_exist_ok=True)
            else:
                shutil.copy2(self.script_config_path, self.temp_path / "config.temp")
        self.external_config_snapshot_ready = True

    def _restore_external_config(self) -> None:
        if (
            not self.external_config_snapshot_ready
            or self.script_config is None
            or self.script_config_path is None
            or self.temp_path is None
        ):
            return
        self._remove_path(self.script_config_path)
        if not self.external_config_exists:
            return
        if self.script_config.get("Script", "ConfigPathMode") == "Folder":
            self._copy_path_atomic(self.temp_path, self.script_config_path, "Folder")
        else:
            self._copy_path_atomic(
                self.temp_path / "config.temp", self.script_config_path, "File"
            )

    def _cleanup_external_config_snapshot(self) -> None:
        if self.temp_path is not None:
            shutil.rmtree(self.temp_path, ignore_errors=True)
        self.external_config_snapshot_ready = False

    def _user_uses_mas_config(self) -> bool:
        if self.user_config is None:
            return True
        user_id = self.script_info.user_list[self.script_info.current_index].user_id
        if user_id == "Default":
            return True
        return bool(self.user_config[uuid.UUID(user_id)].get("Info", "IfUseMasConfig"))

    async def prepare(self) -> None:
        """锁定脚本并构建本次任务的用户列表。"""

        script_uid = uuid.UUID(self.script_info.script_id)
        await Config.ScriptConfig[script_uid].lock()
        self.script_config = Config.ScriptConfig[script_uid]
        self.user_config = MultipleConfig([XxxUserConfig])
        await self.user_config.load(await self.script_config.UserData.toDict())
        self.script_config_path = Path(self.script_config.get("Script", "ConfigPath"))

        if self.script_config.get("Game", "Enabled"):
            game_type = self.script_config.get("Game", "Type")
            if game_type == "Emulator":
                self.emulator_manager = await EmulatorManager.get_emulator_instance(
                    self.script_config.get("Game", "EmulatorId")
                )
            elif game_type in ("Client", "URL"):
                self.game_process_manager = ProcessManager()

        if self.task_info.mode == "ScriptConfig":
            self.script_info.user_list = [
                UserItem(
                    user_id=self.task_info.user_id or "Default",
                    name="",
                    status="等待",
                )
            ]
        else:
            self.script_info.user_list = [
                UserItem(user_id=str(uid), name=config.get("Info", "Name"), status="等待")
                for uid, config in self.user_config.items()
                if config.get("Info", "Status") and config.get("Info", "RemainedDay") != 0
            ]
        self._snapshot_external_config()
        logger.info(f"专项用户列表加载完成: {len(self.script_info.user_list)}")

    async def main_task(self) -> None:
        self.check_result = await self.check()
        if self.check_result != "Pass":
            self.script_info.status = "异常"
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": self.check_result},
            )
            return

        self.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await self.prepare()
        if self.script_config is None or self.user_config is None:
            raise RuntimeError("专项配置未初始化")

        for self.script_info.current_index in range(len(self.script_info.user_list)):
            use_mas_config = self._user_uses_mas_config()
            user_id = self.script_info.user_list[self.script_info.current_index].user_id
            logger.info(
                f"用户 {user_id} 配置来源: {'MAS 独立配置' if use_mas_config else '脚本直控配置'}"
            )
            if not use_mas_config:
                self._restore_external_config()

            task = METHOD_BOOK[self.task_info.mode](
                self.script_info,
                self.script_config,
                self.user_config,
                (
                    self.emulator_manager
                    if self.script_config.get("Game", "Type") == "Emulator"
                    else self.game_process_manager
                )
                if self.script_config.get("Game", "Enabled")
                else None,
            )
            try:
                await self.spawn(task)
            finally:
                if not use_mas_config:
                    self._snapshot_external_config()

    async def final_task(self) -> None:
        """解锁、写回用户数据并聚合脚本状态。"""

        if self.check_result != "Pass":
            self.script_info.status = "异常"
            return

        self._restore_external_config()
        self._cleanup_external_config_snapshot()
        script_uid = uuid.UUID(self.script_info.script_id)
        script_config = Config.ScriptConfig[script_uid]
        if script_config.is_locked:
            await script_config.unlock()

        # unlock-then-write：ConfigBase 在锁定状态下拒绝 load。
        if self.task_info.mode == "AutoProxy" and self.user_config is not None:
            await script_config.UserData.load(await self.user_config.toDict())
            await Config.ScriptConfig.save()

        has_error = any(user.status == "异常" for user in self.script_info.user_list)
        has_success = any(user.status == "完成" for user in self.script_info.user_list)
        self.script_info.status = "异常" if has_error else "完成"
        await Notify.push_plyer(
            "专项自动代理任务已结束",
            f"已完成用户数: {sum(user.status == '完成' for user in self.script_info.user_list)}，"
            f"异常用户数: {sum(user.status == '异常' for user in self.script_info.user_list)}",
            self.script_info.result,
            10 if has_success else 3,
        )

    async def on_crash(self, error: Exception) -> None:
        self.script_info.status = "异常"
        logger.opt(exception=True).warning(f"专项调度任务出现异常: {error}")
        try:
            self._restore_external_config()
            self._cleanup_external_config_snapshot()
        except Exception as restore_error:
            logger.warning(f"恢复专项脚本配置失败: {restore_error}")
        try:
            script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
            if script_config.is_locked:
                await script_config.unlock()
        except Exception as unlock_error:
            logger.warning(f"解锁专项脚本配置失败: {unlock_error}")
        with suppress(Exception):
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": f"专项调度任务出现异常: {error}"},
            )
