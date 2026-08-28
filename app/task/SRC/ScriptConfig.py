#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
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
from pathlib import Path

from app.core import Config
from app.models.task import TaskExecuteBase, ScriptItem
from app.models.ConfigBase import MultipleConfig
from app.models.config import SrcConfig, SrcUserConfig
from app.models.emulator import DeviceBase
from app.utils import get_logger, ProcessManager
from app.utils.io import read_file, write_file
from .tools import (
    kill_src_processes,
    poor_yaml_read,
    poor_yaml_write,
    promote_src_config_update,
    write_src_config_snapshot_state,
    read_src_webui_port,
    recover_src_user_config,
    save_src_user_config,
    stage_src_config_update,
    validate_src_installation,
    write_src_process_state,
)

logger = get_logger("SRC 脚本设置")


class ScriptConfigTask(TaskExecuteBase):
    """脚本设置模式"""

    wait_for_finalizer_on_cancel = True

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: SrcConfig,
        user_config: MultipleConfig[SrcUserConfig],
        emulator_manager: DeviceBase,
        *,
        src_installation_id: str,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.src_installation_id = src_installation_id
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.src_webui_port: int | None = None
        self.config_session_started = False
        self.process_cleanup_success = True
        self.prepared = False

    async def prepare(self):

        self.src_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()

        self.src_root_path = Path(self.script_config.get("Info", "Path"))
        self.src_set_path = self.src_root_path / "config"
        self.src_exe_path = self.src_root_path / "src.exe"
        self.src_process_state_path = (
            Path.cwd() / f"data/{self.script_info.script_id}/Temp.process.json"
        )
        self.temp_ready_path = (
            Path.cwd() / f"data/{self.script_info.script_id}/Temp.ready"
        )
        self.prepared = True

    async def main_task(self):

        await self.prepare()

        await self.set_src()
        self.src_webui_port = read_src_webui_port(self.src_set_path)
        validate_src_installation(
            self.src_root_path,
            self.src_installation_id,
        )
        write_src_process_state(
            self.src_process_state_path,
            script_id=self.script_info.script_id,
            src_root_path=self.src_root_path,
            webui_port=self.src_webui_port,
            installation_id=self.src_installation_id,
            config_user_id=None,
        )
        logger.info(f"启动MAA进程: {self.src_exe_path}")
        self.wait_event.clear()
        validate_src_installation(
            self.src_root_path,
            self.src_installation_id,
        )
        await self.src_process_manager.open_process(self.src_exe_path)
        write_src_config_snapshot_state(
            self.temp_ready_path,
            script_id=self.script_info.script_id,
            src_root_path=self.src_root_path,
            installation_id=self.src_installation_id,
            config_user_id=self.cur_user_item.user_id,
        )
        write_src_process_state(
            self.src_process_state_path,
            script_id=self.script_info.script_id,
            src_root_path=self.src_root_path,
            webui_port=self.src_webui_port,
            installation_id=self.src_installation_id,
            config_user_id=self.cur_user_item.user_id,
        )
        self.config_session_started = True
        await self.wait_event.wait()

    async def set_src(self):
        """配置SRC运行参数"""

        logger.info(f"开始配置MAA运行参数: 设置脚本 {self.cur_user_item.user_id}")

        cleanup_success = await kill_src_processes(
            self.src_process_manager,
            src_exe_path=self.src_exe_path,
            src_root_path=self.src_root_path,
            src_set_path=self.src_set_path,
            webui_port=self.src_webui_port,
            listener_wait_timeout=2.0,
            expected_installation_id=self.src_installation_id,
        )
        self.process_cleanup_success = cleanup_success
        if not cleanup_success:
            raise RuntimeError("未能完全中止 SRC 进程")
        validate_src_installation(
            self.src_root_path,
            self.src_installation_id,
        )

        config_path = (
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile"
        )
        recover_src_user_config(config_path)
        staging_path = stage_src_config_update(
            self.src_set_path,
            expected_installation_id=self.src_installation_id,
            overlay_path=config_path if config_path.exists() else None,
        )

        src_set = read_file(staging_path / "src.json")
        deploy_set = poor_yaml_read((staging_path / "deploy.yaml"))

        # 不直接运行任务
        deploy_set["Run"] = None

        # 模拟器基础配置
        src_set["Alas"]["Emulator"]["GameClient"] = "android"
        src_set["Alas"]["Emulator"]["GameLanguage"] = "cn"
        src_set["Alas"]["Emulator"]["AdbRestart"] = True

        # 错误处理方式
        src_set["Alas"]["Error"]["Restart"] = "game"

        # 任务间切换方式
        src_set["Alas"]["Optimization"]["WhenTaskQueueEmpty"] = "close_game"

        # 养成规划
        src_set["Dungeon"]["PlannerTarget"]["Enable"] = False

        write_file(staging_path / "src.json", src_set)
        poor_yaml_write(
            deploy_set,
            staging_path / "deploy.yaml",
            (
                staging_path / "deploy.template-cn.yaml"
                if (staging_path / "deploy.template-cn.yaml").exists()
                else None
            ),
        )
        promote_src_config_update(
            self.src_set_path,
            staging_path,
            expected_installation_id=self.src_installation_id,
        )
        logger.success(f"SRC运行参数配置完成: 设置脚本 {self.cur_user_item.user_id}")

    async def final_task(self):

        if not self.prepared:
            return

        cleanup_success = await kill_src_processes(
            self.src_process_manager,
            src_exe_path=self.src_exe_path,
            src_root_path=self.src_root_path,
            src_set_path=self.src_set_path,
            webui_port=self.src_webui_port,
            listener_wait_timeout=2.0,
            expected_installation_id=self.src_installation_id,
        )
        self.process_cleanup_success = cleanup_success
        if not cleanup_success:
            raise RuntimeError("未能完全中止 SRC 进程，请关闭 SRC 后重试脚本设置")

        if not self.config_session_started:
            return

        validate_src_installation(
            self.src_root_path,
            self.src_installation_id,
        )

        config_path = (
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/ConfigFile"
        )
        self.process_cleanup_success = False
        save_src_user_config(
            self.src_set_path,
            config_path,
            preserve_commit_marker=True,
            expected_installation_id=self.src_installation_id,
        )
        write_src_process_state(
            self.src_process_state_path,
            script_id=self.script_info.script_id,
            src_root_path=self.src_root_path,
            webui_port=self.src_webui_port,
            installation_id=self.src_installation_id,
            config_user_id=None,
        )
        recover_src_user_config(config_path)
        self.process_cleanup_success = True

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"脚本设置任务出现异常: {e}")
        try:
            await asyncio.wait_for(
                Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={"Error": f"脚本设置任务出现异常: {e}"},
                ),
                timeout=5,
            )
        except Exception as report_error:
            logger.opt(exception=True).warning(
                f"上报 SRC 脚本设置异常失败: {report_error}"
            )
