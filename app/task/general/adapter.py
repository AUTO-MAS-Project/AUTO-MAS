from __future__ import annotations

import shutil
import json
from datetime import datetime
from pathlib import Path

from app.models.ConfigBase import MultipleConfig
from app.models.task import UserItem
from app.plugins import ScriptAdapterHooks, ScriptAdapterRuntime
from app.utils import ProcessManager, get_logger
from app.utils.constants import TASK_MODE_ZH
from .schema import GeneralConfig, GeneralUserConfig

logger = get_logger("通用脚本适配")


class GeneralAdapterHooks(ScriptAdapterHooks):
    """通用脚本的统一适配钩子。"""

    async def check(self, runtime: ScriptAdapterRuntime) -> str:
        if runtime.mode not in ("AutoProxy", "ScriptConfig"):
            return "不支持的任务模式, 请检查任务配置！"

        script_config = await runtime.build_script_model()
        runtime.script_config = script_config

        if (
            script_config.get("Script", "IfTrackProcess")
            and not script_config.get("Script", "TrackProcessName")
            and not script_config.get("Script", "TrackProcessExe")
            and not script_config.get("Script", "TrackProcessCmdline")
        ):
            return "开启追踪子进程后, 需至少填写一项追踪进程信息！"

        if script_config.get("Game", "Enabled"):
            game_type = script_config.get("Game", "Type")
            if game_type == "Emulator" and (
                script_config.get("Game", "EmulatorId") == "-"
                or script_config.get("Game", "EmulatorIndex") in ("", "-")
            ):
                return "未完成模拟器配置, 请检查脚本配置中的模拟器设置！"
            if game_type == "Client" and not Path(
                script_config.get("Game", "Path")
            ).exists():
                return "未完成游戏配置, 请检查脚本配置中的游戏设置！"
            if game_type == "URL" and (
                not script_config.get("Game", "URL")
                or not script_config.get("Game", "ProcessName")
            ):
                return "未完成URL配置, 请检查脚本配置中的URL和进程名称设置！"

        return "Pass"

    async def prepare(self, runtime: ScriptAdapterRuntime) -> None:
        from app.core.emulator_manager import EmulatorManager

        storage_script_config = runtime.get_storage_script_config()
        await storage_script_config.lock()

        script_config = await runtime.build_script_model()
        runtime.script_config = script_config
        runtime.storage_script_config = storage_script_config
        runtime.user_config = MultipleConfig([GeneralUserConfig])

        user_payload = {"instances": []}
        for user_uid, user_data in await runtime.read_user_data_pairs():
            runtime_user = GeneralUserConfig()
            await runtime_user.load(user_data)
            user_payload["instances"].append(
                {"uid": user_uid, "type": GeneralUserConfig.__name__}
            )
            user_payload[user_uid] = await runtime_user.toDict()
        await runtime.user_config.load(user_payload)
        logger.success(f"{runtime.script_info.script_id}已锁定, 通用脚本配置提取完成")

        script_config_path = Path(script_config.get("Script", "ConfigPath"))
        temp_path = Path.cwd() / f"data/{runtime.script_info.script_id}/Temp"
        runtime.extra["script_config_path"] = script_config_path
        runtime.extra["temp_path"] = temp_path

        if script_config.get("Game", "Enabled"):
            game_type = script_config.get("Game", "Type")
            if game_type == "Emulator":
                runtime.extra["game_manager"] = (
                    await EmulatorManager.get_emulator_instance(
                        script_config.get("Game", "EmulatorId")
                    )
                )
            elif game_type in ("Client", "URL"):
                runtime.extra["game_manager"] = ProcessManager()

        logger.info(f"记录通用脚本配置文件: {script_config_path}")
        temp_path.mkdir(parents=True, exist_ok=True)
        if script_config_path.exists():
            if script_config.get("Script", "ConfigPathMode") == "Folder":
                shutil.copytree(script_config_path, temp_path, dirs_exist_ok=True)
            elif script_config.get("Script", "ConfigPathMode") == "File":
                shutil.copy(script_config_path, temp_path / "config.temp")

        if runtime.mode == "ScriptConfig":
            runtime.script_info.user_list = [
                UserItem(
                    user_id=runtime.task_info.user_id or "Default",
                    name="",
                    status="等待",
                )
            ]
        else:
            runtime.script_info.user_list = [
                UserItem(
                    user_id=str(uid),
                    name=config.get("Info", "Name"),
                    status="等待",
                )
                for uid, config in runtime.user_config.items()
                if config.get("Info", "Status")
                and config.get("Info", "RemainedDay") != 0
            ]
        logger.info(
            f"用户列表加载完成, 已筛选用户数: {len(runtime.script_info.user_list)}"
        )

    def run_auto_proxy(self, runtime: ScriptAdapterRuntime, user_index: int):
        from .AutoProxy import AutoProxyTask

        _ = user_index
        return AutoProxyTask(
            runtime.script_info,
            runtime.script_config,
            runtime.user_config,
            runtime.extra.get("game_manager"),
        )

    def run_script_config(self, runtime: ScriptAdapterRuntime, user_index: int):
        from .ScriptConfig import ScriptConfigTask

        _ = user_index
        return ScriptConfigTask(
            runtime.script_info,
            runtime.script_config,
            runtime.user_config,
            runtime.extra.get("game_manager"),
        )

    async def finalize(self, runtime: ScriptAdapterRuntime) -> None:
        from app.core.config import Config
        from app.services.notification import Notify
        from .tools.notify import push_notification

        if runtime.check_result != "Pass":
            runtime.script_info.status = "异常"
            return

        script_config: GeneralConfig | None = runtime.script_config
        storage_script_config = runtime.get_storage_script_config()
        if script_config is None:
            runtime.script_info.status = "异常"
            return

        logger.info("通用脚本任务已结束, 开始执行后续操作")
        await storage_script_config.unlock()
        logger.success(f"已解锁脚本配置 {runtime.script_info.script_id}")

        if runtime.mode == "AutoProxy":
            for user_uid, user_config in runtime.user_config.items():
                storage_user_config = storage_script_config.UserData[user_uid]
                payload = await user_config.toDict(if_decrypt=False)
                payload.pop("SubConfigsInfo", None)
                await storage_user_config.set(
                    "PluginData",
                    "Config",
                    json.dumps(payload, ensure_ascii=False),
                )
                await storage_user_config.set(
                    "Info",
                    "Name",
                    user_config.get("Info", "Name"),
                )

            error_user = [
                user.name for user in runtime.script_info.user_list if user.status == "异常"
            ]
            over_user = [
                user.name for user in runtime.script_info.user_list if user.status == "完成"
            ]
            wait_user = [
                user.name for user in runtime.script_info.user_list if user.status == "等待"
            ]

            title = (
                f"{datetime.now().strftime('%m-%d')} | "
                f"{runtime.script_info.name or '空白'}的{TASK_MODE_ZH[runtime.mode]}任务报告"
            )
            result = {
                "title": f"{TASK_MODE_ZH[runtime.mode]}任务报告",
                "script_name": runtime.script_info.name or "空白",
                "start_time": runtime.begin_time,
                "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "completed_count": len(over_user),
                "uncompleted_count": len(error_user) + len(wait_user),
                "result": runtime.script_info.result,
            }

            await Notify.push_plyer(
                title.replace("报告", "已完成！"),
                (
                    f"已完成用户数: {len(over_user)}, "
                    f"未完成用户数: {len(error_user) + len(wait_user)}"
                ),
                (
                    f"已完成用户数: {len(over_user)}, "
                    f"未完成用户数: {len(error_user) + len(wait_user)}"
                ),
                10,
            )
            try:
                await push_notification("代理结果", title, result, None)
            except Exception as error:
                logger.exception(f"推送代理结果时出现异常: {error}")
                await Config.send_websocket_message(
                    id=runtime.task_info.task_id,
                    type="Info",
                    data={"Error": f"推送代理结果时出现异常: {error}"},
                )

        script_config_path: Path | None = runtime.extra.get("script_config_path")
        temp_path: Path | None = runtime.extra.get("temp_path")
        if script_config_path is None or temp_path is None:
            runtime.script_info.status = "完成"
            return

        if script_config.get("Script", "ConfigPathMode") == "Folder" and temp_path.exists():
            logger.info(f"复原通用脚本配置文件: {temp_path}")
            shutil.rmtree(script_config_path, ignore_errors=True)
            shutil.copytree(temp_path, script_config_path, dirs_exist_ok=True)
            shutil.rmtree(temp_path, ignore_errors=True)
        elif (
            script_config.get("Script", "ConfigPathMode") == "File"
            and (temp_path / "config.temp").exists()
        ):
            logger.info(f"复原通用脚本配置文件: {temp_path / 'config.temp'}")
            shutil.copy(temp_path / "config.temp", script_config_path)
            shutil.rmtree(temp_path, ignore_errors=True)

        runtime.script_info.status = "完成"

    async def on_crash(self, runtime: ScriptAdapterRuntime, error: Exception) -> None:
        from app.core.config import Config

        runtime.script_info.status = "异常"
        logger.exception(f"通用脚本任务出现异常: {error}")
        await Config.send_websocket_message(
            id=runtime.task_info.task_id,
            type="Info",
            data={"Error": f"通用脚本任务出现异常: {error}"},
        )
