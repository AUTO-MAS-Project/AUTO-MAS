import shutil
import uuid
from pathlib import Path

from app.core import Config
from app.models.ConfigBase import MultipleConfig
from app.models.config import MaaEndConfig, MaaEndUserConfig
from app.models.task import ScriptItem, TaskExecuteBase, UserItem
from app.utils import get_logger

from .ScriptConfig import ScriptConfigTask


logger = get_logger("MaaEnd 调度器")

METHOD_BOOK: dict[str, type[ScriptConfigTask]] = {
    "ScriptConfig": ScriptConfigTask,
}


class MaaEndManager(TaskExecuteBase):
    """MaaEnd 控制器"""

    def __init__(self, script_info: ScriptItem):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info

        self.check_result = "-"

        self.prepared_ok = False
        self.config_locked = False
        self.backup_created = False

        self.script_config: MaaEndConfig | None = None
        self.user_config = MultipleConfig([MaaEndUserConfig])

        self.maaend_config_dir = Path()
        self.temp_path = Path()
        self.backup_path = Path()

    async def check(self) -> str:
        if self.task_info.mode not in METHOD_BOOK:
            return "不支持的任务模式, 请检查任务配置！"

        script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        if not isinstance(script_config, MaaEndConfig):
            return "脚本配置类型错误, 不是 MaaEnd 脚本类型"

        maaend_root_path = Path(script_config.get("Info", "Path"))
        maaend_exe_path = maaend_root_path / "MaaEnd.exe"
        if not maaend_exe_path.exists():
            return f"MaaEnd.exe文件不存在, 请检查MaaEnd路径设置！({maaend_exe_path})"

        return "Pass"

    async def prepare(self):
        await Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].lock()
        self.config_locked = True

        self.script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        await self.user_config.load(await self.script_config.UserData.toDict())

        if not isinstance(self.script_config, MaaEndConfig):
            raise RuntimeError("脚本配置类型错误, 不是 MaaEnd 脚本类型")

        self.maaend_config_dir = Path(self.script_config.get("Info", "Path")) / "config"
        self.temp_path = Path.cwd() / f"data/{self.script_info.script_id}/Temp"
        self.backup_path = self.temp_path / "MaaEndConfigBackup"

        self.temp_path.mkdir(parents=True, exist_ok=True)
        if self.backup_path.exists():
            shutil.rmtree(self.backup_path, ignore_errors=True)

        if self.maaend_config_dir.exists():
            shutil.copytree(self.maaend_config_dir, self.backup_path, dirs_exist_ok=True)
            self.backup_created = True

        if self.task_info.mode == "ScriptConfig":
            self.script_info.user_list = [
                UserItem(user_id=self.task_info.user_id or "Default", name="", status="等待")
            ]

        self.prepared_ok = True

    async def main_task(self):
        self.check_result = await self.check()
        if self.check_result != "Pass":
            logger.error(f"未通过配置检查: {self.check_result}")
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": self.check_result},
            )
            return

        await self.prepare()

        if not isinstance(self.script_config, MaaEndConfig):
            raise RuntimeError("脚本配置类型错误, 不是 MaaEnd 脚本类型")

        for self.script_info.current_index in range(len(self.script_info.user_list)):
            task = METHOD_BOOK[self.task_info.mode](
                self.script_info,
                self.script_config,
                self.user_config,
            )
            await self.spawn(task)

    async def final_task(self):
        if self.check_result != "Pass":
            self.script_info.status = "异常"

        if self.config_locked:
            await Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].unlock()
            self.config_locked = False

        if self.prepared_ok and isinstance(self.script_config, MaaEndConfig):
            await Config.ScriptConfig[
                uuid.UUID(self.script_info.script_id)
            ].UserData.load(await self.user_config.toDict())

        if self.backup_created and self.backup_path.exists():
            if self.maaend_config_dir.exists():
                shutil.rmtree(self.maaend_config_dir, ignore_errors=True)
            shutil.copytree(self.backup_path, self.maaend_config_dir, dirs_exist_ok=True)

        if self.backup_path.exists():
            shutil.rmtree(self.backup_path, ignore_errors=True)
        if self.temp_path.exists() and not any(self.temp_path.iterdir()):
            self.temp_path.rmdir()

        if self.script_info.status != "异常":
            self.script_info.status = "完成"


    async def on_crash(self, e: Exception):
        self.script_info.status = "异常"
        logger.exception(f"MaaEnd 任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"MaaEnd 任务出现异常: {e}"},
        )
