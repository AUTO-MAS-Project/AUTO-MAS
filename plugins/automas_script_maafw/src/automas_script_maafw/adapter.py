from __future__ import annotations

import asyncio
import copy
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from app.core import Config
from app.models.ConfigBase import ConfigBase, JSONValidator, MultipleConfig
from app.models.config import MaaFWConfig, MaaFWUserConfig
from app.models.task import ScriptItem, TaskExecuteBase, UserItem
from app.plugins import ScriptAdapterHooks, ScriptAdapterRuntime
from app.utils import get_logger
from automas_maafw_interface.loader import MaaFWInterfaceLoadError
from automas_maafw_interface.service import MaaFWInterfaceService
from automas_maafw_project_update.service import MaaFWProjectUpdateService

from .runner_task import MaaFWPluginAutoProxyTask
from .schema import build_source_config


LegacyConfigT = TypeVar("LegacyConfigT", bound=ConfigBase)


logger = get_logger("MaaFW 插件适配")


class MaaFWAdapterHooks(ScriptAdapterHooks):
    """MaaFW script adapter backed by PluginScriptConfig."""

    async def check(self, runtime: ScriptAdapterRuntime) -> str:
        if runtime.mode != "AutoProxy":
            return "MaaFW 插件当前仅支持 AutoProxy 模式"

        script_data = await runtime.storage.read_script_data()
        script_config = await _load_legacy_script_config(script_data)
        raw_project_path = str(script_config.get("Info", "Path") or "").strip()
        if not raw_project_path:
            return "请设置 MaaFW 项目路径"

        project_path = Path(raw_project_path)
        if not project_path.exists():
            return "请设置 MaaFW 项目路径"

        try:
            interface = MaaFWInterfaceService().load(project_path)
        except MaaFWInterfaceLoadError as exc:
            return f"无法读取 MaaFW interface，请检查项目路径: {exc}"

        if not interface.controller:
            return "MaaFW interface 未声明 controller，请检查项目目录"
        if not interface.resource:
            return "MaaFW interface 未声明 resource，请检查项目目录"
        if not interface.task:
            return "MaaFW interface 未声明 task，请检查项目目录"

        emulator_id = script_config.get("Emulator", "Id")
        emulator_index = script_config.get("Emulator", "Index")
        if emulator_id != "-" and emulator_index in ("", "-"):
            return "请在 MaaFW 脚本配置中选择模拟器实例"
        return "Pass"

    async def prepare(self, runtime: ScriptAdapterRuntime) -> None:
        await runtime.storage.lock()

        script_data = await runtime.storage.read_script_data()
        script_config = await _load_legacy_script_config(script_data)
        user_config = await _load_legacy_user_config(runtime)

        runtime.script_config = script_config
        runtime.user_config = user_config
        runtime.extra["maafw_project_update_logs"] = []

        await self._update_project_before_run(runtime, script_config)

        emulator_manager = None
        emulator_id = script_config.get("Emulator", "Id")
        if emulator_id != "-":
            emulator_manager = await runtime.initialize_emulator_manager(emulator_id)
        runtime.emulator_manager = emulator_manager

        runtime.script_info.user_list = [
            UserItem(
                user_id=str(uid),
                name=config.get("Info", "Name"),
                status="等待",
            )
            for uid, config in user_config.items()
            if config.get("Info", "Status")
            and config.get("Info", "RemainedDay") != 0
        ]
        self._emit_log(
            runtime,
            f"MaaFW 插件用户列表加载完成，已筛选用户数: {len(runtime.script_info.user_list)}",
        )

    def run_auto_proxy(self, runtime: ScriptAdapterRuntime) -> TaskExecuteBase:
        if runtime.script_config is None or runtime.user_config is None:
            raise RuntimeError("MaaFW 插件配置尚未准备")
        return MaaFWPluginAutoProxyTask(
            runtime.script_info,
            runtime.script_config,
            runtime.user_config,
            runtime.emulator_manager,
            list(runtime.extra.get("maafw_project_update_logs") or []),
        )

    async def finalize(self, runtime: ScriptAdapterRuntime) -> None:
        previous_status = runtime.script_info.status
        try:
            if runtime.user_config is not None and runtime.mode == "AutoProxy":
                # prepare() 锁定了整棵配置树（含 UserData），写回前必须先解锁，
                # 否则 PluginUserConfig.set() 会抛出 "配置已锁定, 无法修改"
                await runtime.storage.unlock()
                await runtime.storage.save_user_models(runtime.user_config)
        finally:
            await runtime.storage.unlock()

        if previous_status == "异常" or runtime.check_result not in ("-", "", "Pass"):
            runtime.script_info.status = "异常"
            return

        error_user = [u.name for u in runtime.script_info.user_list if u.status == "异常"]
        over_user = [u.name for u in runtime.script_info.user_list if u.status == "完成"]
        if error_user:
            runtime.script_info.status = "异常"
        elif over_user:
            runtime.script_info.status = "完成"
        else:
            runtime.script_info.status = "跳过"

    async def on_crash(self, runtime: ScriptAdapterRuntime, error: Exception) -> None:
        try:
            await runtime.storage.unlock()
        except Exception:
            pass
        await super().on_crash(runtime, error)

    async def _update_project_before_run(
        self,
        runtime: ScriptAdapterRuntime,
        script_config: MaaFWConfig,
    ) -> None:
        if not script_config.get("Update", "IfAutoUpdate"):
            self._emit_log(runtime, "MaaFW 项目运行前自动更新已关闭")
            return

        project_path = Path(script_config.get("Info", "Path")).resolve()
        try:
            interface_model = MaaFWInterfaceService().load(project_path)
        except MaaFWInterfaceLoadError as exc:
            self._emit_log(runtime, f"MaaFW 项目更新跳过，interface 读取失败: {exc}")
            return

        script_data = await runtime.storage.read_script_data()
        source_config = build_source_config(script_data)
        mirror_cdk = (
            script_config.get("Update", "MirrorChyanCDK")
            or Config.get("Update", "MirrorChyanCDK")
        )
        channel = script_config.get("Update", "Channel") or Config.get("Update", "Channel")
        try:
            update_result = await MaaFWProjectUpdateService().update_if_needed(
                project_path,
                interface_model,
                mirror_cdk=mirror_cdk,
                channel=channel,
                proxy=Config.proxy,
                send_log=lambda message: self._emit_log(runtime, message),
                source_config=source_config,
            )
            if update_result.updated:
                refreshed_interface = MaaFWInterfaceService().load(
                    project_path,
                    force_reload=True,
                )
                self._emit_log(runtime, "MaaFW project updated, preparing agent Python env")
                agent_prepare_logs: list[str] = []
                try:
                    await asyncio.to_thread(
                        _prepare_maafw_agent_python_envs,
                        project_path,
                        refreshed_interface,
                        send_log=agent_prepare_logs.append,
                    )
                finally:
                    for log_line in agent_prepare_logs:
                        self._emit_log(runtime, log_line)
        except Exception as exc:
            self._emit_log(runtime, f"MaaFW 项目更新失败，继续使用当前目录: {exc}")

    @staticmethod
    def _emit_log(runtime: ScriptAdapterRuntime, message: str) -> None:
        """把 adapter 关键操作日志同时写入后端日志与 UI 通道。

        UI 侧由 task_manager 广播 script_info.log（task.log 事件），因此这里
        除了 logger.info，还要追加到共享缓冲并刷新 script_info.log，
        否则用户在脚本管理页看不到插件适配阶段的进度。
        """
        logger.info(message)
        logs = runtime.extra.setdefault("maafw_project_update_logs", [])
        if isinstance(logs, list):
            logs.extend(_format_update_log_lines(message))
            runtime.script_info.log = "".join(logs[-80:])


async def _load_legacy_script_config(payload: dict[str, Any]) -> MaaFWConfig:
    return await _load_legacy_config(MaaFWConfig(), payload)


async def _load_legacy_user_config(
    runtime: ScriptAdapterRuntime,
) -> MultipleConfig[MaaFWUserConfig]:
    collection = MultipleConfig([MaaFWUserConfig])
    source: dict[str, Any] = {"instances": []}
    for user_id, payload in await runtime.storage.read_user_data_pairs():
        uid = str(uuid.UUID(user_id))
        source["instances"].append({"uid": uid, "type": "MaaFWUserConfig"})
        source[uid] = _normalize_legacy_json_fields(MaaFWUserConfig(), payload)
    await collection.load(source)
    return collection


async def _load_legacy_config(
    config: LegacyConfigT,
    payload: dict[str, Any],
) -> LegacyConfigT:
    await config.load(_normalize_legacy_json_fields(config, payload))
    return config


def _normalize_legacy_json_fields(
    config: ConfigBase,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Convert plugin form JSON values back to legacy ConfigBase strings."""

    normalized = copy.deepcopy(payload)
    for group, items in config._config_item_index.items():
        group_data = normalized.get(group)
        if not isinstance(group_data, dict):
            continue
        for name, item in items.items():
            validator = item.validator
            value = group_data.get(name)
            if isinstance(validator, JSONValidator) and isinstance(
                value,
                validator.type,
            ):
                group_data[name] = json.dumps(value, ensure_ascii=False)
    return normalized


def _format_update_log_lines(message: str) -> list[str]:
    now = datetime.now().strftime("%H:%M:%S")
    return [f"[{now}] {line}\n" for line in str(message).splitlines() or [""]]


def _prepare_maafw_agent_python_envs(
    project_path: Path,
    interface_model: Any,
    *,
    send_log: Any = None,
) -> None:
    from automas_maafw_agent_env.service import MaaFWAgentEnvService

    MaaFWAgentEnvService().prepare_env(
        project_path,
        interface_model,
        send_log=send_log,
    )


def build_legacy_script_item(script_item: ScriptItem) -> ScriptItem:
    return script_item
