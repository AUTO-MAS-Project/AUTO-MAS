from __future__ import annotations

import json
import uuid
import inspect
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import NoneType, UnionType
from typing import TYPE_CHECKING, Any, Callable, Literal, Sequence, get_args, get_origin

from pydantic import BaseModel

if TYPE_CHECKING:
    from .schema_utils import SchemaDecorationContext

from app.models.ConfigBase import (
    BoolValidator,
    ConfigBase,
    ConfigItem,
    DateTimeValidator,
    FileValidator,
    FolderValidator,
    JSONValidator,
    MultipleUIDValidator,
    OptionsValidator,
    RangeValidator,
    StringValidator,
    URLValidator,
    UserNameValidator,
    ValidatorBase,
    VirtualConfigValidator,
)
from app.models.task import ScriptItem, TaskExecuteBase, TaskItem
from app.utils import get_logger

from .context import PluginContext

logger = get_logger("脚本适配框架")


def _is_configbase_class(config_class: type[Any]) -> bool:
    return isinstance(config_class, type) and issubclass(config_class, ConfigBase)


def _field_extra(field_info: Any) -> dict[str, Any]:
    extra = field_info.json_schema_extra
    return dict(extra) if isinstance(extra, dict) else {}


def _field_default(field_info: Any) -> Any:
    if field_info.default_factory is not None:
        return field_info.default_factory()
    if field_info.is_required():
        return None
    return field_info.default


def _annotation_without_none(annotation: Any) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (UnionType, getattr(__import__("typing"), "Union")):
        non_none = [arg for arg in args if arg not in (None, NoneType, type(None))]
        if len(non_none) == 1:
            return non_none[0]
    return annotation


def _literal_values(annotation: Any) -> list[Any] | None:
    annotation = _annotation_without_none(annotation)
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is Literal:
        return list(args)
    return None


def _list_literal_values(annotation: Any) -> list[Any] | None:
    annotation = _annotation_without_none(annotation)
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is list and args:
        return _literal_values(args[0])
    return None


def _schema_type(annotation: Any, extra: dict[str, Any]) -> str:
    ui_type = extra.get("type") or extra.get("ui_type")
    if isinstance(ui_type, str) and ui_type:
        return ui_type

    annotation = _annotation_without_none(annotation)
    origin = get_origin(annotation)
    if _literal_values(annotation) is not None:
        return "select"
    if _list_literal_values(annotation) is not None:
        return "multiselect"
    if annotation is bool:
        return "boolean"
    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    if origin is list:
        return "list"
    if origin is dict or annotation is dict:
        return "json"
    return "string"


def _field_constraints(field_info: Any) -> dict[str, Any]:
    constraints: dict[str, Any] = {}
    for item in field_info.metadata or []:
        for name in (
            "gt",
            "ge",
            "lt",
            "le",
            "multiple_of",
            "min_length",
            "max_length",
            "pattern",
        ):
            value = getattr(item, name, None)
            if value is not None:
                constraints[name] = value
    return constraints


def _schema_options(annotation: Any, extra: dict[str, Any]) -> list[Any] | None:
    options = extra.get("options")
    if isinstance(options, list):
        return options
    values = _literal_values(annotation) or _list_literal_values(annotation)
    if values is None:
        return None
    return [{"label": str(value), "value": value} for value in values]


def _config_validator(
    group: str,
    name: str,
    annotation: Any,
    extra: dict[str, Any],
    default: Any,
    related_config: dict[str, Any],
    virtual_handlers: dict[str, Callable[[ConfigBase], Any]],
) -> ValidatorBase:
    field_key = f"{group}.{name}"
    if field_key in virtual_handlers:
        return VirtualConfigValidator(lambda: str(virtual_handlers[field_key](related_config["_self"])))

    validator_name = str(extra.get("validator") or "").strip()
    if validator_name == "username":
        return UserNameValidator()

    ui_type = str(extra.get("type") or extra.get("ui_type") or "").strip()
    field_format = str(extra.get("format") or "").strip()
    constraints = _field_constraints(type("FieldProxy", (), {"metadata": []})())
    _ = constraints

    if ui_type == "related-id":
        return MultipleUIDValidator(
            extra.get("related_default", default),
            related_config,
            str(extra.get("related_config") or ""),
        )
    if ui_type == "folder" or extra.get("path_kind") == "folder":
        return FolderValidator()
    if ui_type in {"file", "path"} or extra.get("path_kind") == "file":
        return FileValidator()
    if ui_type == "datetime":
        return DateTimeValidator(str(extra.get("date_format") or extra.get("format") or "%Y-%m-%d"))
    if field_format == "url":
        return URLValidator(default=str(default or ""))

    annotation = _annotation_without_none(annotation)
    values = _literal_values(annotation)
    list_values = _list_literal_values(annotation)
    if values:
        return OptionsValidator(values)
    if list_values:
        from app.models.ConfigBase import MultipleOptionsValidator

        return MultipleOptionsValidator(list_values)
    if annotation is bool:
        return BoolValidator()
    if annotation in (int, float):
        ge = extra.get("ge")
        le = extra.get("le")
        if ge is None:
            ge = extra.get("min")
        if le is None:
            le = extra.get("max")
        if ge is not None and le is not None:
            return RangeValidator(ge, le)
        return RangeValidator(-999999, 999999)
    if get_origin(annotation) is dict or annotation is dict:
        return JSONValidator(dict)
    if get_origin(annotation) is list or annotation is list:
        return JSONValidator(list)
    return StringValidator()


@dataclass(slots=True)
class ScriptAdapterRuntime:
    """脚本适配运行时上下文。"""

    definition: "ScriptAdapterDefinition"
    script_info: ScriptItem
    task_info: TaskItem
    script_uid: uuid.UUID
    type_key: str
    mode: str
    plugin_context: PluginContext | None = None
    script_config: Any = None
    user_config: Any = None
    storage_script_config: Any = None
    begin_time: str = ""
    check_result: str = "Pass"
    extra: dict[str, Any] = field(default_factory=dict)

    def build_action_context(self) -> dict[str, Any]:
        """构建可供前端 schema action 使用的上下文字段。"""

        return {
            "scriptId": str(self.script_uid),
            "typeKey": self.type_key,
            "mode": self.mode,
            "taskId": self.task_info.task_id,
            "userId": self.task_info.user_id,
        }

    def get_storage_script_config(self) -> Any:
        """返回当前脚本在主配置容器中的存储对象。"""

        from app.core import Config as RuntimeConfig

        if self.storage_script_config is None:
            self.storage_script_config = RuntimeConfig.ScriptConfig[self.script_uid]
        return self.storage_script_config

    async def read_script_data(self) -> dict[str, Any]:
        """读取脚本配置的表单态数据。"""

        from app.core import Config as RuntimeConfig
        from app.core.script_types import strip_sub_configs
        from app.models.plugin_script_config import PluginScriptConfig

        storage = self.get_storage_script_config()
        if isinstance(storage, PluginScriptConfig):
            raw = storage.get("PluginData", "Config")
            data = json.loads(raw) if raw and raw != "{}" else {}
            normalized = RuntimeConfig._normalize_configbase_payload_for_form(
                self.definition.script_config_class,
                data,
            )
            if _is_configbase_class(self.definition.script_config_class):
                normalized = strip_sub_configs(normalized)
            return normalized

        payload = await storage.toDict()
        normalized = RuntimeConfig._normalize_configbase_payload_for_form(
            self.definition.script_config_class,
            strip_sub_configs(payload),
        )
        if _is_configbase_class(self.definition.script_config_class):
            normalized = strip_sub_configs(normalized)
        return normalized

    async def read_user_data_pairs(self) -> list[tuple[str, dict[str, Any]]]:
        """读取当前脚本下全部用户配置的表单态数据。"""

        from app.core import Config as RuntimeConfig
        from app.core.script_types import strip_sub_configs
        from app.models.plugin_script_config import PluginUserConfig

        storage = self.get_storage_script_config()
        pairs: list[tuple[str, dict[str, Any]]] = []
        for user_uid, user_config in storage.UserData.items():
            if isinstance(user_config, PluginUserConfig):
                raw = user_config.get("PluginData", "Config")
                data = json.loads(raw) if raw and raw != "{}" else {}
                normalized = RuntimeConfig._normalize_configbase_payload_for_form(
                    self.definition.user_config_class,
                    data,
                )
                if _is_configbase_class(self.definition.user_config_class):
                    normalized = strip_sub_configs(normalized)
            else:
                payload = await user_config.toDict()
                normalized = RuntimeConfig._normalize_configbase_payload_for_form(
                    self.definition.user_config_class,
                    strip_sub_configs(payload),
                )
                if _is_configbase_class(self.definition.user_config_class):
                    normalized = strip_sub_configs(normalized)
            pairs.append((str(user_uid), normalized))
        return pairs

    async def build_script_model(self) -> Any:
        """按声明的 schema 类型重建脚本配置模型。"""

        data = await self.read_script_data()
        if _is_configbase_class(self.definition.script_config_class):
            config = self.definition.script_config_class()
            await config.load(data)
            return config
        return self.definition.script_config_class.model_validate(data)

    async def build_user_models(self) -> list[tuple[str, Any]]:
        """按声明的 schema 类型重建用户配置模型列表。"""

        pairs = await self.read_user_data_pairs()
        result: list[tuple[str, Any]] = []
        for user_uid, data in pairs:
            if _is_configbase_class(self.definition.user_config_class):
                config = self.definition.user_config_class()
                await config.load(data)
                result.append((user_uid, config))
            else:
                result.append(
                    (user_uid, self.definition.user_config_class.model_validate(data))
                )
        return result


class ScriptAdapterHooks:
    """专项脚本适配运行时钩子。"""

    async def check(self, runtime: ScriptAdapterRuntime) -> str:
        return "Pass"

    async def prepare(self, runtime: ScriptAdapterRuntime) -> None:
        _ = runtime

    async def finalize(self, runtime: ScriptAdapterRuntime) -> None:
        _ = runtime

    async def on_crash(self, runtime: ScriptAdapterRuntime, error: Exception) -> None:
        runtime.script_info.status = "异常"
        logger.opt(exception=True).error(
            f"脚本适配 {runtime.type_key} 运行异常: {type(error).__name__}: {error}"
        )

    def run_auto_proxy(
        self, runtime: ScriptAdapterRuntime, user_index: int
    ) -> TaskExecuteBase:
        _ = runtime, user_index
        raise RuntimeError("当前适配未实现 AutoProxy 模式")

    def run_script_config(
        self, runtime: ScriptAdapterRuntime, user_index: int
    ) -> TaskExecuteBase:
        _ = runtime, user_index
        raise RuntimeError("当前适配未实现 ScriptConfig 模式")

    def run_manual_review(
        self, runtime: ScriptAdapterRuntime, user_index: int
    ) -> TaskExecuteBase:
        _ = runtime, user_index
        raise RuntimeError("当前适配未实现 ManualReview 模式")

    async def decorate_script_schema(
        self,
        schema: dict[str, Any],
        config_data: dict[str, Any],
        ctx: "SchemaDecorationContext",
    ) -> dict[str, Any]:
        _ = config_data, ctx
        return schema

    async def decorate_user_schema(
        self,
        schema: dict[str, Any],
        config_data: dict[str, Any],
        ctx: "SchemaDecorationContext",
    ) -> dict[str, Any]:
        _ = config_data, ctx
        return schema


class BaseAdapterManager(TaskExecuteBase):
    """统一的专项脚本外层调度器。"""

    def __init__(
        self,
        script_info: ScriptItem,
        *,
        definition: "ScriptAdapterDefinition",
        hooks: ScriptAdapterHooks,
        plugin_context: PluginContext | None = None,
    ) -> None:
        super().__init__()
        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.definition = definition
        self.hooks = hooks
        self.runtime = ScriptAdapterRuntime(
            definition=definition,
            script_info=script_info,
            task_info=script_info.task_info,
            script_uid=uuid.UUID(script_info.script_id),
            type_key=definition.type_key,
            mode=script_info.task_info.mode,
            plugin_context=plugin_context,
        )

    def _create_user_task(self, user_index: int) -> TaskExecuteBase:
        mode = self.runtime.mode
        if mode == "AutoProxy":
            return self.hooks.run_auto_proxy(self.runtime, user_index)
        if mode == "ScriptConfig":
            return self.hooks.run_script_config(self.runtime, user_index)
        if mode == "ManualReview":
            return self.hooks.run_manual_review(self.runtime, user_index)
        raise RuntimeError(f"不支持的任务模式: {mode}")

    async def _report_check_failure(self) -> None:
        from app.core import Config as RuntimeConfig

        self.runtime.script_info.status = "异常"
        await RuntimeConfig.send_websocket_message(
            id=self.runtime.task_info.task_id,
            type="Info",
            data={"Error": self.runtime.check_result},
        )

    async def main_task(self) -> None:
        if self.runtime.mode not in self.definition.supported_modes:
            self.runtime.check_result = f"不支持的任务模式: {self.runtime.mode}"
            await self._report_check_failure()
            return

        result = await self.hooks.check(self.runtime)
        if result not in (None, "", True, "Pass"):
            self.runtime.check_result = str(result)
            await self._report_check_failure()
            return

        self.runtime.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.runtime.script_info.status = "运行中"
        await self.hooks.prepare(self.runtime)

        for user_index in range(len(self.runtime.script_info.user_list)):
            self.runtime.script_info.current_index = user_index
            task = self._create_user_task(user_index)
            await self.spawn(task)

    async def final_task(self) -> None:
        await self.hooks.finalize(self.runtime)

    async def on_crash(self, error: Exception) -> None:
        await self.hooks.on_crash(self.runtime, error)


@dataclass(slots=True)
class ScriptAdapterDefinition:
    """脚本适配声明。"""

    type_key: str
    display_name: str
    script_config_class: type[Any]
    user_config_class: type[Any]
    hooks_factory: Callable[[], ScriptAdapterHooks]
    supported_modes: tuple[str, ...] = ("AutoProxy", "ScriptConfig")
    icon: str | None = None
    docs_url: str | None = None
    editor_kind: str = "schema"
    legacy_config_class_name: str | None = None
    legacy_user_config_class_name: str | None = None
    is_builtin: bool = False
    bind_related_config: Callable[[Any], None] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def build_provider(
        self,
        *,
        owner: str | None = None,
        plugin_context: PluginContext | None = None,
    ) -> Any:
        """构建脚本类型 provider。"""

        from app.core.script_types import ScriptTypeProvider

        def _factory(script_item: ScriptItem) -> TaskExecuteBase:
            return BaseAdapterManager(
                script_item,
                definition=self,
                hooks=self.hooks_factory(),
                plugin_context=plugin_context,
            )

        provider = ScriptTypeProvider(
            type_key=self.type_key,
            display_name=self.display_name,
            script_config_class=self.script_config_class,
            user_config_class=self.user_config_class,
            supported_modes=self.supported_modes,
            manager_factory=_factory,
            icon=self.icon,
            docs_url=self.docs_url,
            editor_kind=self.editor_kind,
            legacy_config_class_name=self.legacy_config_class_name,
            legacy_user_config_class_name=self.legacy_user_config_class_name,
            is_builtin=self.is_builtin,
            bind_related_config=self.bind_related_config,
            metadata=dict(self.metadata),
        )
        if owner is not None:
            provider.metadata.setdefault("adapter_owner", owner)
        provider.metadata.setdefault("adapter_kind", "script_adapter")
        provider.metadata["hooks_factory"] = self.hooks_factory
        return provider


class ScriptAdapterPlugin:
    """用于专项适配插件的基类。"""

    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def build_script_adapters(self) -> Sequence[ScriptAdapterDefinition]:
        return ()

    async def on_start(self) -> None:
        from app.core import Config as RuntimeConfig
        from app.core.script_types import script_type_registry

        registered: list[str] = []
        for definition in self.build_script_adapters():
            if definition.bind_related_config is not None:
                definition.bind_related_config(RuntimeConfig)
            provider = definition.build_provider(
                owner=self.ctx.instance_id,
                plugin_context=self.ctx,
            )
            script_type_registry.register(provider, owner=self.ctx.instance_id)
            registered.append(definition.type_key)

        self.ctx.logger.info(f"已注册脚本适配: {registered}")

    async def on_stop(self, reason: str) -> None:
        _ = reason
        from app.core.script_types import script_type_registry

        removed = script_type_registry.unregister_by_owner(self.ctx.instance_id)
        self.ctx.logger.info(f"已注销脚本适配: {removed}")

    async def on_unload(self) -> None:
        from app.core.script_types import script_type_registry

        removed = script_type_registry.unregister_by_owner(self.ctx.instance_id)
        self.ctx.logger.info(f"已卸载脚本适配: {removed}")
