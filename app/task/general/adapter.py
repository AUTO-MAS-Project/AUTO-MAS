from __future__ import annotations

import shutil
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.ConfigBase import MultipleConfig
from app.models.task import UserItem
from app.plugins import ScriptAdapterHooks, ScriptAdapterRuntime
from app.plugins.schema_utils import (
    SchemaDecorationContext,
    append_schema_field,
    set_schema_field_options,
    set_schema_field_state,
)
from app.utils import ProcessManager, get_logger
from app.utils.constants import TASK_MODE_ZH

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
        provider = runtime._resolve_provider()
        runtime.user_config = MultipleConfig([provider.user_config_class])
        for user_uid, user_model in await runtime.build_user_models():
            uid = uuid.UUID(user_uid)
            runtime.user_config.order.append(uid)
            runtime.user_config.data[uid] = user_model
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
        from app.core.ws import Publisher, protocol
        from app.models.schema import WSTaskNoticeData
        from app.services.notification import Notify
        from .tools.notify import push_notification

        if runtime.check_result != "Pass":
            runtime.script_info.status = "异常"
            return

        script_config = runtime.script_config
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
                await Publisher.send(
                    id=runtime.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error", message=f"推送代理结果时出现异常: {error}"
                    ),
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

    async def decorate_script_schema(
        self,
        schema: dict[str, Any],
        config_data: dict[str, Any],
        ctx: SchemaDecorationContext,
    ) -> dict[str, Any]:
        script_group = config_data.get("Script")
        if not isinstance(script_group, dict):
            script_group = {}
        if not bool(script_group.get("IfTrackProcess")):
            track_help = "开启“追踪子进程”后，这些字段才会参与运行时判断。"
            for field_key in (
                "Script.TrackProcessName",
                "Script.TrackProcessExe",
                "Script.TrackProcessCmdline",
            ):
                set_schema_field_state(
                    schema, field_key, readonly=True, help_text=track_help
                )

        game_group = config_data.get("Game")
        if not isinstance(game_group, dict):
            game_group = {}
        game_enabled = bool(game_group.get("Enabled"))
        game_type = str(game_group.get("Type") or "Emulator")
        if not game_enabled:
            game_help = "启用游戏联动后，这些字段才会在运行时生效。"
            for field_key in (
                "Game.Type",
                "Game.Path",
                "Game.URL",
                "Game.ProcessName",
                "Game.Arguments",
                "Game.WaitTime",
                "Game.IfForceClose",
                "Game.EmulatorId",
                "Game.EmulatorIndex",
            ):
                set_schema_field_state(
                    schema, field_key, readonly=True, help_text=game_help
                )
            return schema

        set_schema_field_options(
            schema, "Game.EmulatorId", await ctx.get_emulator_combox()
        )
        emulator_id = str(game_group.get("EmulatorId") or "")
        emulator_index_options: list[dict[str, Any]] = [
            {"label": "未选择", "value": "-"}
        ]
        if emulator_id and emulator_id != "-":
            try:
                scanned = await ctx.get_emulator_devices_combox(emulator_id)
                if scanned:
                    emulator_index_options = scanned
            except Exception as exc:
                logger.warning(
                    f"获取通用脚本模拟器实例失败: {type(exc).__name__}: {exc}"
                )
        set_schema_field_options(
            schema, "Game.EmulatorIndex", emulator_index_options
        )

        if game_type != "Emulator":
            set_schema_field_state(
                schema, "Game.EmulatorId",
                readonly=True, help_text="仅在“模拟器”类型下使用。",
            )
            set_schema_field_state(
                schema, "Game.EmulatorIndex",
                readonly=True, help_text="仅在“模拟器”类型下使用。",
            )
        if game_type != "Client":
            set_schema_field_state(
                schema, "Game.Path",
                readonly=True, help_text="仅在“客户端”类型下使用。",
            )
        if game_type != "URL":
            set_schema_field_state(
                schema, "Game.URL",
                readonly=True, help_text="仅在“URL”类型下使用。",
            )
            set_schema_field_state(
                schema, "Game.ProcessName",
                readonly=True, help_text="仅在“URL”类型下使用。",
            )

        return schema

    async def decorate_user_schema(
        self,
        schema: dict[str, Any],
        config_data: dict[str, Any],
        ctx: SchemaDecorationContext,
    ) -> dict[str, Any]:
        info_group = config_data.get("Info")
        if not isinstance(info_group, dict):
            info_group = {}
        if not bool(info_group.get("IfScriptBeforeTask")):
            set_schema_field_state(
                schema, "Info.ScriptBeforeTask",
                readonly=True, help_text="开启“任务前脚本”后才可选择文件。",
            )
        if not bool(info_group.get("IfScriptAfterTask")):
            set_schema_field_state(
                schema, "Info.ScriptAfterTask",
                readonly=True, help_text="开启“任务后脚本”后才可选择文件。",
            )

        notify_group = config_data.get("Notify")
        if not isinstance(notify_group, dict):
            notify_group = {}
        notify_enabled = bool(notify_group.get("Enabled"))
        if not notify_enabled:
            notify_help = "启用通知后，这些字段才会在运行时生效。"
            for field_key in (
                "Notify.IfSendStatistic",
                "Notify.IfSendMail",
                "Notify.ToAddress",
                "Notify.IfServerChan",
                "Notify.ServerChanKey",
            ):
                set_schema_field_state(
                    schema, field_key, readonly=True, help_text=notify_help
                )
        else:
            if not bool(notify_group.get("IfSendMail")):
                set_schema_field_state(
                    schema, "Notify.ToAddress",
                    readonly=True, help_text="开启“邮件通知”后才可填写。",
                )
            if not bool(notify_group.get("IfServerChan")):
                set_schema_field_state(
                    schema, "Notify.ServerChanKey",
                    readonly=True, help_text="开启“Server酱通知”后才可填写。",
                )

        append_schema_field(
            schema,
            "Action",
            {
                "key": "Action.GeneralConfig",
                "group": "Action",
                "name": "GeneralConfig",
                "label": "通用配置",
                "type": "button",
                "icon": "SettingOutlined",
                "help": "启动该用户的脚本配置会话，完成后点击保存配置结束会话。",
                "button": {
                    "label": "通用配置",
                    "path": "/api/dispatch/start",
                    "method": "POST",
                    "payload": {
                        "taskId": "{{userId}}",
                        "mode": "ScriptConfig",
                    },
                    "refresh": True,
                    "session": {
                        "response_task_id_key": "taskId",
                        "stop_path": "/api/dispatch/stop",
                        "stop_method": "POST",
                        "stop_payload": {
                            "taskId": "{{session.websocketId}}",
                        },
                        "overlay_title": "正在进行通用配置",
                        "overlay_description": (
                            "当前正在进行该用户的通用配置，请在配置界面完成相关设置。\n"
                            "配置完成后，请点击“保存配置”按钮结束配置会话。"
                        ),
                        "stop_label": "保存配置",
                        "start_message": "已开始配置用户 {{userName}} 的通用设置",
                        "success_message": "用户 {{userName}} 的配置已完成",
                        "stop_message": "用户 {{userName}} 的通用配置已保存",
                        "timeout_ms": 1800000,
                        "timeout_auto_stop": True,
                        "timeout_message": (
                            "用户 {{userName}} 的配置会话已超时（30分钟），"
                            "正在自动保存配置..."
                        ),
                    },
                },
            },
        )

        return schema

    async def on_crash(self, runtime: ScriptAdapterRuntime, error: Exception) -> None:
        from app.core.ws import Publisher, protocol
        from app.models.schema import WSTaskNoticeData

        runtime.script_info.status = "异常"
        logger.exception(f"通用脚本任务出现异常: {error}")
        await Publisher.send(
            id=runtime.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(
                level="error", message=f"通用脚本任务出现异常: {error}"
            ),
        )
