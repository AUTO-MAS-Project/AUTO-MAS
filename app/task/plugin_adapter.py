#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel

from app.models.task import ScriptItem, TaskExecuteBase

from app.core.plugins.context import PluginContext
from app.core.plugins.lifecycle_hooks import LifecycleHookRegistry
from app.core.plugins.log_pipeline import LogPipeline
from app.core.plugins.script_base import PluginScriptManager


def create_plugin_manager_factory(
    *,
    type_key: str,
    script_config_class: type[BaseModel],
    user_config_class: type[BaseModel],
    supported_modes: tuple[str, ...],
    hook_registry: LifecycleHookRegistry,
    log_pipeline_factory: Callable[[], LogPipeline],
    plugin_context: PluginContext | None = None,
    exe_path_key: str = "Info.Path",
    log_time_range: tuple[int, int] = (0, 19),
    log_time_format: str = "%Y-%m-%d %H:%M:%S",
    log_path_key: str | None = None,
    run_times_limit_key: str = "Run.RunTimesLimit",
    run_time_limit_key: str = "Run.RunTimeLimit",
) -> Callable[[ScriptItem], TaskExecuteBase]:
    """为 ``ScriptTypeProvider.manager_factory`` 创建工厂函数。

    返回的工厂在每次任务执行时被调用，接收 ``ScriptItem``，
    返回 ``PluginScriptManager`` 实例。
    """

    def factory(script_item: ScriptItem) -> TaskExecuteBase:
        pipeline = log_pipeline_factory()

        script_config: dict[str, Any] = {}
        user_configs: list[dict[str, Any]] = []

        try:
            from app.core import Config
            from app.models.plugin_script_config import PluginScriptConfig, PluginUserConfig
            import json
            import uuid as _uuid

            script_uid = _uuid.UUID(script_item.script_id)
            script_cfg: Any = Config.ScriptConfig[script_uid]

            if isinstance(script_cfg, PluginScriptConfig):
                raw = script_cfg.get("PluginData", "Config")
                script_config = json.loads(raw) if raw and raw != "{}" else {}

                for _uid, user_cfg in script_cfg.UserData.items():
                    if isinstance(user_cfg, PluginUserConfig):
                        raw_user = user_cfg.get("PluginData", "Config")
                        user_data = json.loads(raw_user) if raw_user and raw_user != "{}" else {}
                        user_configs.append(user_data)
            elif script_cfg is not None:
                if hasattr(script_cfg, "asdict"):
                    script_config = script_cfg.asdict()
                elif hasattr(script_cfg, "to_dict"):
                    script_config = script_cfg.to_dict()

                sub_info = script_config.get("SubConfigsInfo", {})
                if isinstance(sub_info, dict):
                    user_data_section = sub_info.get("UserData", {})
                    if isinstance(user_data_section, dict):
                        instances = user_data_section.get("instances", [])
                        if isinstance(instances, list):
                            user_configs = [
                                inst for inst in instances
                                if isinstance(inst, dict)
                            ]
        except Exception as _exc:
            from app.utils import get_logger as _get_logger
            _get_logger("插件脚本").opt(exception=True).error(
                f"加载插件脚本配置失败: {script_item.script_id}, {type(_exc).__name__}: {_exc}"
            )

        return PluginScriptManager(
            script_item,
            type_key=type_key,
            script_config=script_config,
            user_configs=user_configs,
            supported_modes=supported_modes,
            hook_registry=hook_registry,
            log_pipeline=pipeline,
            plugin_context=plugin_context,
            exe_path_key=exe_path_key,
            log_time_range=log_time_range,
            log_time_format=log_time_format,
            log_path_key=log_path_key,
            run_times_limit_key=run_times_limit_key,
            run_time_limit_key=run_time_limit_key,
        )

    return factory
