from __future__ import annotations

import inspect
import importlib.metadata as importlib_metadata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from pydantic import BaseModel

from app.models.ConfigBase import (
    BoolValidator,
    ConfigBase,
    ConfigItem,
    DateTimeValidator,
    EncryptValidator,
    FileValidator,
    FolderValidator,
    JSONValidator,
    MultipleOptionsValidator,
    MultipleUIDValidator,
    OptionsValidator,
    RangeValidator,
    UUIDValidator,
    ValidatorBase,
    VirtualConfigValidator,
)
from app.models.task import ScriptItem
from app.utils import get_logger

from app.plugins.pypi_site import ensure_pypi_site_packages_on_syspath


logger = get_logger("脚本类型注册表")

TASK_MODES = ("AutoProxy", "ManualReview", "ScriptConfig")
SCRIPT_TYPE_ENTRY_POINT_GROUPS = ("auto_mas.script_types", "automas.script_types")
LEGACY_SCRIPT_TYPE_METADATA = (
    {
        "type_key": "MAA",
        "display_name": "MAA脚本",
        "script_class_name": "MaaConfig",
        "user_class_name": "MaaUserConfig",
        "supported_modes": ("AutoProxy", "ManualReview", "ScriptConfig"),
        "icon": "MAA",
        "editor_kind": "builtin:maa",
        "is_builtin": True,
    },
    {
        "type_key": "SRC",
        "display_name": "SRC脚本",
        "script_class_name": "SrcConfig",
        "user_class_name": "SrcUserConfig",
        "supported_modes": ("AutoProxy", "ManualReview", "ScriptConfig"),
        "icon": "SRC",
        "editor_kind": "builtin:src",
        "is_builtin": True,
    },
    {
        "type_key": "MaaEnd",
        "display_name": "MaaEnd脚本",
        "script_class_name": "MaaEndConfig",
        "user_class_name": "MaaEndUserConfig",
        "supported_modes": ("AutoProxy", "ManualReview", "ScriptConfig"),
        "icon": "MaaEnd",
        "editor_kind": "builtin:maaend",
        "is_builtin": True,
    },
    {
        "type_key": "General",
        "display_name": "通用脚本",
        "script_class_name": "GeneralConfig",
        "user_class_name": "GeneralUserConfig",
        "supported_modes": ("AutoProxy", "ScriptConfig"),
        "icon": "General",
        "editor_kind": "builtin:general",
        "is_builtin": True,
    },
)
LEGACY_SCRIPT_TYPE_BY_SCRIPT_CLASS = {
    item["script_class_name"]: item for item in LEGACY_SCRIPT_TYPE_METADATA
}
LEGACY_SCRIPT_TYPE_BY_USER_CLASS = {
    item["user_class_name"]: item for item in LEGACY_SCRIPT_TYPE_METADATA
}


@dataclass(slots=True)
class ScriptTypeProvider:
    """脚本类型提供者。"""

    type_key: str
    display_name: str
    script_config_class: type[Any]
    user_config_class: type[Any]
    supported_modes: tuple[str, ...]
    manager_factory: Callable[[ScriptItem], Any]
    script_schema: dict[str, Any] | None = None
    user_schema: dict[str, Any] | None = None
    icon: str | None = None
    docs_url: str | None = None
    editor_kind: str = "schema"
    legacy_config_class_name: str | None = None
    legacy_user_config_class_name: str | None = None
    is_builtin: bool = False
    bind_related_config: Callable[[Any], None] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def build_script_schema(self) -> dict[str, Any]:
        """返回脚本配置的表单描述。"""

        if self.script_schema is None:
            self.script_schema = build_config_schema(self.script_config_class)
        return self.script_schema

    def build_user_schema(self) -> dict[str, Any]:
        """返回用户配置的表单描述。"""

        if self.user_schema is None:
            self.user_schema = build_config_schema(self.user_config_class)
        return self.user_schema

    def create_manager(self, script_item: ScriptItem) -> Any:
        """创建脚本对应的运行管理器。"""

        return self.manager_factory(script_item)


class ScriptTypeRegistry:
    """统一管理脚本类型提供者。"""

    def __init__(self) -> None:
        self._providers: dict[str, ScriptTypeProvider] = {}
        self._providers_by_script_class: dict[str, ScriptTypeProvider] = {}
        self._providers_by_user_class: dict[str, ScriptTypeProvider] = {}
        self._provider_owners: dict[str, str | None] = {}
        self._bootstrapped = False

    def register(self, provider: ScriptTypeProvider, owner: str | None = None) -> None:
        """注册脚本类型提供者。"""

        type_key = str(provider.type_key or "").strip()
        if not type_key:
            raise ValueError("脚本类型键不能为空")
        if type_key in self._providers:
            raise ValueError(f"脚本类型 {type_key} 已存在")
        if not issubclass(provider.script_config_class, (ConfigBase, BaseModel)):
            raise TypeError("script_config_class 必须继承 ConfigBase 或 pydantic.BaseModel")
        if not issubclass(provider.user_config_class, (ConfigBase, BaseModel)):
            raise TypeError("user_config_class 必须继承 ConfigBase 或 pydantic.BaseModel")
        if not callable(provider.manager_factory):
            raise TypeError("manager_factory 必须可调用")

        invalid_modes = [mode for mode in provider.supported_modes if mode not in TASK_MODES]
        if invalid_modes:
            raise ValueError(f"脚本类型 {type_key} 包含非法模式: {invalid_modes}")

        script_class_name = provider.script_config_class.__name__
        user_class_name = provider.user_config_class.__name__
        if script_class_name in self._providers_by_script_class:
            raise ValueError(f"脚本配置类 {script_class_name} 已被其他脚本类型占用")
        if user_class_name in self._providers_by_user_class:
            raise ValueError(f"用户配置类 {user_class_name} 已被其他脚本类型占用")

        provider.type_key = type_key
        provider.legacy_config_class_name = (
            provider.legacy_config_class_name or provider.script_config_class.__name__
        )
        provider.legacy_user_config_class_name = (
            provider.legacy_user_config_class_name or provider.user_config_class.__name__
        )

        self._providers[type_key] = provider
        self._providers_by_script_class[script_class_name] = provider
        self._providers_by_user_class[user_class_name] = provider
        self._provider_owners[type_key] = owner

    def unregister(self, type_key: str, owner: str | None = None) -> bool:
        """按类型键注销脚本类型提供者。"""

        provider = self._providers.get(type_key)
        if provider is None:
            return False

        current_owner = self._provider_owners.get(type_key)
        if owner is not None and current_owner != owner:
            return False

        self._providers.pop(type_key, None)
        self._providers_by_script_class.pop(provider.script_config_class.__name__, None)
        self._providers_by_user_class.pop(provider.user_config_class.__name__, None)
        self._provider_owners.pop(type_key, None)
        return True

    def unregister_by_owner(self, owner: str) -> list[str]:
        """按 owner 批量注销脚本类型提供者。"""

        removed: list[str] = []
        for type_key, current_owner in list(self._provider_owners.items()):
            if current_owner != owner:
                continue
            if self.unregister(type_key, owner=owner):
                removed.append(type_key)
        return removed

    def get(self, type_key: str) -> ScriptTypeProvider:
        """根据脚本类型键获取提供者。"""

        if type_key not in self._providers:
            raise KeyError(f"未注册的脚本类型: {type_key}")
        return self._providers[type_key]

    def get_by_script_config(self, config: ConfigBase | type[ConfigBase] | str) -> ScriptTypeProvider:
        """根据脚本配置类解析提供者。"""

        class_name = _resolve_class_name(config)
        provider = self._providers_by_script_class.get(class_name)
        if provider is None:
            raise KeyError(f"未注册的脚本配置类: {class_name}")
        return provider

    def get_by_user_config(self, config: ConfigBase | type[ConfigBase] | str) -> ScriptTypeProvider:
        """根据用户配置类解析提供者。"""

        class_name = _resolve_class_name(config)
        provider = self._providers_by_user_class.get(class_name)
        if provider is None:
            raise KeyError(f"未注册的用户配置类: {class_name}")
        return provider

    def list(self) -> list[ScriptTypeProvider]:
        """按注册顺序返回全部提供者。"""

        return list(self._providers.values())

    def list_builtin(self) -> list[ScriptTypeProvider]:
        """返回内建脚本类型。"""

        return [provider for provider in self._providers.values() if provider.is_builtin]

    def get_owner(self, type_key: str) -> str | None:
        """获取脚本类型提供者的 owner。"""

        return self._provider_owners.get(type_key)

    def bootstrap(self, plugins_dir: Path | None = None) -> None:
        """完成内建与第三方脚本类型注册。"""

        if self._bootstrapped:
            return

        self._register_builtin_providers()
        self._load_entry_point_providers(plugins_dir)
        self._bootstrapped = True

    def _register_builtin_providers(self) -> None:
        """注册内建脚本类型。"""

        from app.models.config import (
            GeneralConfig,
            GeneralUserConfig,
            MaaEndConfig,
            MaaEndUserConfig,
            SrcConfig,
            SrcUserConfig,
        )

        def _lazy_manager(module_path: str, class_name: str) -> Callable[[ScriptItem], Any]:
            def _factory(script_item: ScriptItem) -> Any:
                module = __import__(module_path, fromlist=[class_name])
                manager_class = getattr(module, class_name)
                return manager_class(script_item)

            return _factory

        providers = [
            ScriptTypeProvider(
                type_key="SRC",
                display_name="SRC脚本",
                script_config_class=SrcConfig,
                user_config_class=SrcUserConfig,
                supported_modes=("AutoProxy", "ManualReview", "ScriptConfig"),
                manager_factory=_lazy_manager("app.task.SRC.manager", "SrcManager"),
                icon="SRC",
                editor_kind="builtin:src",
                is_builtin=True,
            ),
            ScriptTypeProvider(
                type_key="MaaEnd",
                display_name="MaaEnd脚本",
                script_config_class=MaaEndConfig,
                user_config_class=MaaEndUserConfig,
                supported_modes=("AutoProxy", "ManualReview", "ScriptConfig"),
                manager_factory=_lazy_manager("app.task.MaaEnd.manager", "MaaEndManager"),
                icon="MaaEnd",
                editor_kind="builtin:maaend",
                is_builtin=True,
            ),
            ScriptTypeProvider(
                type_key="General",
                display_name="通用脚本",
                script_config_class=GeneralConfig,
                user_config_class=GeneralUserConfig,
                supported_modes=("AutoProxy", "ScriptConfig"),
                manager_factory=_lazy_manager("app.task.general.manager", "GeneralManager"),
                icon="General",
                editor_kind="builtin:general",
                is_builtin=True,
            ),
        ]

        for provider in providers:
            self.register(provider)

    def _load_entry_point_providers(self, plugins_dir: Path | None = None) -> None:
        """从本地插件环境加载第三方脚本类型。"""

        site_dir = ensure_pypi_site_packages_on_syspath(plugins_dir)
        seen: set[tuple[str, str, str]] = set()

        for dist in importlib_metadata.distributions(path=[str(site_dir)]):
            for ep in getattr(dist, "entry_points", []):
                if ep.group not in SCRIPT_TYPE_ENTRY_POINT_GROUPS:
                    continue
                entry_key = (ep.group, ep.name, ep.value)
                if entry_key in seen:
                    continue
                seen.add(entry_key)

                try:
                    loaded = ep.load()
                    providers = _normalize_entry_point_provider(loaded)
                    for provider in providers:
                        self.register(provider)
                    logger.info(f"已加载脚本类型入口点: {ep.name}")
                except Exception as exc:
                    logger.warning(
                        f"加载脚本类型入口点失败: {ep.name} ({type(exc).__name__}: {exc})"
                    )


def build_config_schema(config_class: type[Any]) -> dict[str, Any]:
    """从 ConfigBase 或 Pydantic BaseModel 配置类生成通用表单描述。"""

    if inspect.isclass(config_class) and issubclass(config_class, BaseModel) and not issubclass(config_class, ConfigBase):
        from app.plugins.schema import PluginSchemaManager
        schema_manager = PluginSchemaManager()
        fields = schema_manager._build_schema_from_model("__inline__", config_class)
        return fields

    config = config_class()
    groups: list[dict[str, Any]] = []

    for group_name, fields in config._config_item_index.items():
        group_fields = [_serialize_config_item(item) for item in fields.values()]
        if group_fields:
            groups.append(
                {
                    "key": group_name,
                    "label": group_name,
                    "fields": group_fields,
                }
            )

    return {"groups": groups}


def strip_sub_configs(data: dict[str, Any]) -> dict[str, Any]:
    """去除内部子配置索引，避免通用编辑接口误传。"""

    result = dict(data)
    result.pop("SubConfigsInfo", None)
    return result


def build_descriptor(provider: ScriptTypeProvider) -> dict[str, Any]:
    """构建可供接口返回的脚本类型描述。"""

    return {
        "type_key": provider.type_key,
        "display_name": provider.display_name,
        "icon": provider.icon,
        "docs_url": provider.docs_url,
        "editor_kind": provider.editor_kind,
        "supported_modes": list(provider.supported_modes),
        "script_schema": provider.build_script_schema(),
        "user_schema": provider.build_user_schema(),
        "legacy_config_class_name": provider.legacy_config_class_name,
        "legacy_user_config_class_name": provider.legacy_user_config_class_name,
        "is_builtin": provider.is_builtin,
    }


def build_legacy_fallback_provider_by_script_config(
    config: ConfigBase | type[ConfigBase] | str,
) -> ScriptTypeProvider | None:
    """按脚本配置类名构造离线回退 provider。"""

    return _build_legacy_fallback_provider(
        _resolve_class_name(config),
        LEGACY_SCRIPT_TYPE_BY_SCRIPT_CLASS,
    )


def build_legacy_fallback_provider_by_user_config(
    config: ConfigBase | type[ConfigBase] | str,
) -> ScriptTypeProvider | None:
    """按用户配置类名构造离线回退 provider。"""

    return _build_legacy_fallback_provider(
        _resolve_class_name(config),
        LEGACY_SCRIPT_TYPE_BY_USER_CLASS,
    )


def apply_script_type_registry_to_global_config(global_config: Any) -> None:
    """把注册表中的脚本类型同步到全局配置容器。"""

    from app.models.plugin_script_config import PluginScriptConfig

    _bind_builtin_script_config_models(global_config)
    script_type_registry.bootstrap()

    global_config.ScriptConfig.sub_config_type["PluginScriptConfig"] = PluginScriptConfig

    for provider in script_type_registry.list():
        if provider.is_builtin:
            global_config.ScriptConfig.sub_config_type[provider.script_config_class.__name__] = (
                provider.script_config_class
            )
        if provider.bind_related_config is not None:
            provider.bind_related_config(global_config)


def validate_script_type_registry(global_config: Any) -> list[str]:
    """校验当前已加载脚本配置是否都存在对应 provider。"""

    from app.models.plugin_script_config import PluginScriptConfig

    missing: list[str] = []
    for script_id, script_config in global_config.ScriptConfig.items():
        if isinstance(script_config, PluginScriptConfig):
            type_key = str(script_config.get("Meta", "PluginTypeKey") or "").strip()
            if not type_key:
                continue
            try:
                script_type_registry.get(type_key)
            except KeyError:
                script_name = str(script_config.get("Info", "Name") or "").strip()
                label = script_name or str(script_id)
                logger.warning(
                    "插件脚本类型 provider 未加载: "
                    f"script_id={script_id}, script_name={label}, type_key={type_key}"
                )
            continue

        try:
            provider = script_type_registry.get_by_script_config(script_config)
        except KeyError:
            fallback_provider = build_legacy_fallback_provider_by_script_config(script_config)
            if fallback_provider is not None:
                script_name = ""
                try:
                    script_name = str(script_config.get("Info", "Name") or "").strip()
                except Exception:
                    script_name = ""
                label = script_name or str(script_id)
                logger.warning(
                    "脚本类型 provider 未启用，启动时将以离线模式保留该脚本: "
                    f"script_id={script_id}, script_name={label}, "
                    f"type={fallback_provider.type_key}, config_class={type(script_config).__name__}"
                )
                continue
            script_name = ""
            try:
                script_name = str(script_config.get("Info", "Name") or "").strip()
            except Exception:
                script_name = ""
            label = script_name or str(script_id)
            missing.append(
                f"script_id={script_id}, script_name={label}, config_class={type(script_config).__name__}"
            )
            continue

        if provider.script_config_class is not type(script_config):
            script_name = ""
            try:
                script_name = str(script_config.get("Info", "Name") or "").strip()
            except Exception:
                script_name = ""
            label = script_name or str(script_id)
            missing.append(
                f"script_id={script_id}, script_name={label}, provider={provider.type_key}, "
                f"config_class={type(script_config).__name__}"
            )

    return missing


def _normalize_entry_point_provider(loaded: Any) -> list[ScriptTypeProvider]:
    """归一化入口点返回值。"""

    candidate = loaded() if inspect.isclass(loaded) or callable(loaded) else loaded
    if isinstance(candidate, ScriptTypeProvider):
        return [candidate]
    if isinstance(candidate, Iterable) and not isinstance(candidate, (str, bytes, dict)):
        providers = list(candidate)
        if not all(isinstance(provider, ScriptTypeProvider) for provider in providers):
            raise TypeError("脚本类型入口点返回值必须是 ScriptTypeProvider 或其列表")
        return providers
    raise TypeError("脚本类型入口点返回值必须是 ScriptTypeProvider 或其列表")


def _build_legacy_fallback_provider(
    class_name: str,
    mapping: dict[str, dict[str, Any]],
) -> ScriptTypeProvider | None:
    """根据遗留元数据构造只读回退 provider。"""

    metadata = mapping.get(class_name)
    if metadata is None:
        return None

    script_config_class, user_config_class = _resolve_legacy_config_classes(
        str(metadata["script_class_name"]),
        str(metadata["user_class_name"]),
    )

    return ScriptTypeProvider(
        type_key=str(metadata["type_key"]),
        display_name=str(metadata["display_name"]),
        script_config_class=script_config_class,
        user_config_class=user_config_class,
        supported_modes=tuple(metadata["supported_modes"]),
        manager_factory=_make_unavailable_manager_factory(str(metadata["type_key"])),
        script_schema=build_config_schema(script_config_class),
        user_schema=build_config_schema(user_config_class),
        icon=metadata.get("icon"),
        docs_url=metadata.get("docs_url"),
        editor_kind=str(metadata.get("editor_kind") or "schema"),
        legacy_config_class_name=script_config_class.__name__,
        legacy_user_config_class_name=user_config_class.__name__,
        is_builtin=bool(metadata.get("is_builtin", False)),
        metadata={"available": False, "source": "legacy-fallback"},
    )


def _bind_builtin_script_config_models(global_config: Any) -> None:
    """预绑定宿主内建脚本配置模型，确保配置可以在 provider 激活前完成加载。"""

    from app.models.config import (
        GeneralConfig,
        GeneralUserConfig,
        MaaConfig,
        MaaEndConfig,
        MaaEndUserConfig,
        MaaUserConfig,
        SrcConfig,
        SrcUserConfig,
    )

    builtin_script_types = (
        GeneralConfig,
        MaaConfig,
        MaaEndConfig,
        SrcConfig,
    )
    for config_class in builtin_script_types:
        global_config.ScriptConfig.sub_config_type[config_class.__name__] = config_class

    GeneralConfig.related_config["EmulatorConfig"] = global_config.EmulatorConfig
    MaaConfig.related_config["EmulatorConfig"] = global_config.EmulatorConfig
    MaaEndConfig.related_config["EmulatorConfig"] = global_config.EmulatorConfig
    SrcConfig.related_config["EmulatorConfig"] = global_config.EmulatorConfig
    MaaUserConfig.related_config["PlanConfig"] = global_config.PlanConfig

    _ = GeneralUserConfig
    _ = MaaEndUserConfig
    _ = SrcUserConfig


def _resolve_class_name(config: Any) -> str:
    """统一解析配置类名。"""

    if isinstance(config, str):
        return config
    if inspect.isclass(config):
        return config.__name__
    return type(config).__name__


def _resolve_legacy_config_classes(
    script_class_name: str,
    user_class_name: str,
) -> tuple[type[ConfigBase], type[ConfigBase]]:
    """解析遗留脚本类型回退所需的配置类。"""

    from app.models.config import (
        GeneralConfig,
        GeneralUserConfig,
        MaaConfig,
        MaaEndConfig,
        MaaEndUserConfig,
        MaaUserConfig,
        SrcConfig,
        SrcUserConfig,
    )

    script_classes: dict[str, type[ConfigBase]] = {
        "GeneralConfig": GeneralConfig,
        "MaaConfig": MaaConfig,
        "MaaEndConfig": MaaEndConfig,
        "SrcConfig": SrcConfig,
    }
    user_classes: dict[str, type[ConfigBase]] = {
        "GeneralUserConfig": GeneralUserConfig,
        "MaaEndUserConfig": MaaEndUserConfig,
        "MaaUserConfig": MaaUserConfig,
        "SrcUserConfig": SrcUserConfig,
    }

    script_config_class = script_classes.get(script_class_name)
    user_config_class = user_classes.get(user_class_name)
    if script_config_class is None or user_config_class is None:
        raise KeyError(
            f"未找到遗留脚本类型回退配置类: script={script_class_name}, user={user_class_name}"
        )
    return script_config_class, user_config_class


def _make_unavailable_manager_factory(type_key: str) -> Callable[[ScriptItem], Any]:
    """为离线回退 provider 生成不可执行的 manager 工厂。"""

    def _factory(script_item: ScriptItem) -> Any:
        _ = script_item
        raise RuntimeError(f"脚本类型 {type_key} 当前未启用，无法创建任务管理器")

    return _factory


def _serialize_config_item(item: ConfigItem) -> dict[str, Any]:
    """把配置项序列化成前端可消费的字段描述。"""

    schema: dict[str, Any] = {
        "key": f"{item.group}.{item.name}",
        "group": item.group,
        "name": item.name,
        "label": item.name,
        "default": item.getValue(),
        "required": False,
        "readonly": isinstance(item.validator, VirtualConfigValidator),
        "sensitive": isinstance(item.validator, EncryptValidator),
    }

    _apply_validator_schema(schema, item.validator, item.getValue())
    return schema


def _apply_validator_schema(
    schema: dict[str, Any], validator: ValidatorBase, default_value: Any
) -> None:
    """根据验证器补充字段类型元数据。"""

    if isinstance(validator, OptionsValidator):
        schema["type"] = "select"
        schema["options"] = [{"label": str(option), "value": option} for option in validator.options]
        return

    if isinstance(validator, MultipleOptionsValidator):
        schema["type"] = "multiselect"
        schema["options"] = [{"label": str(option), "value": option} for option in validator.options]
        return

    if isinstance(validator, BoolValidator):
        schema["type"] = "boolean"
        return

    if isinstance(validator, RangeValidator):
        schema["type"] = "number"
        schema["min"] = validator.min
        schema["max"] = validator.max
        schema["step"] = 1 if isinstance(default_value, int) else 0.1
        return

    if isinstance(validator, JSONValidator):
        schema["type"] = "json"
        schema["json_type"] = "array" if validator.type is list else "object"
        return

    if isinstance(validator, EncryptValidator):
        schema["type"] = "password"
        return

    if isinstance(validator, FolderValidator):
        schema["type"] = "folder"
        return

    if isinstance(validator, FileValidator):
        schema["type"] = "file"
        return

    if isinstance(validator, DateTimeValidator):
        schema["type"] = "datetime"
        schema["format"] = validator.date_format
        return

    if isinstance(validator, MultipleUIDValidator):
        schema["type"] = "related-id"
        schema["default"] = validator.default
        return

    if isinstance(validator, UUIDValidator):
        schema["type"] = "uuid"
        return

    if isinstance(validator, VirtualConfigValidator):
        schema["type"] = "readonly"
        return

    if isinstance(default_value, bool):
        schema["type"] = "boolean"
        return

    if isinstance(default_value, (int, float)):
        schema["type"] = "number"
        return

    if isinstance(default_value, list):
        schema["type"] = "list"
        return

    if isinstance(default_value, dict):
        schema["type"] = "json"
        schema["json_type"] = "object"
        return

    schema["type"] = "string"


script_type_registry = ScriptTypeRegistry()
