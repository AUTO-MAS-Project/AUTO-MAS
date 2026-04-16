from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar, cast

if TYPE_CHECKING:
    _ClsT = TypeVar("_ClsT")
from .base import MultipleConfig
from .fields import (
    OnDeleteCallback,
    RefDeleteAction,
    RefField,
    VirtualDependency,
    VirtualField,
    VirtualFieldGetter,
    VirtualFieldSetter,
)
from .types import EncryptedFieldMarker


@dataclass(frozen=True, slots=True)
class SubConfigSpec:
    """子配置挂载描述。"""

    types: tuple[type[Any], ...]
    singleton: bool = False


def _normalize_sub_config_spec(value: Any) -> SubConfigSpec:
    """将多种子配置声明形式统一规整为 ``SubConfigSpec``。

    支持以下输入：
    - 已构造的 ``SubConfigSpec``
    - ``list[type]`` / ``tuple[type, ...]``（表示多实例子配置集合）
    - 单个 ``type``（会转为仅含一个类型的多实例声明）

    Args:
        value: 装饰器参数中声明的子配置描述。

    Returns:
        规范化后的 ``SubConfigSpec``。

    Raises:
        TypeError: 传入类型不受支持时抛出。
    """

    if isinstance(value, SubConfigSpec):
        return value

    if isinstance(value, list):
        return SubConfigSpec(types=tuple(cast(list[type[Any]], value)), singleton=False)

    if isinstance(value, tuple):
        return SubConfigSpec(types=cast(tuple[type[Any], ...], value), singleton=False)

    if isinstance(value, type):
        return SubConfigSpec(types=(value,), singleton=False)

    raise TypeError(f"不支持的子配置声明类型: {type(value)!r}")


def ref(
    target: str,
    *,
    default: Any,
    allow_values: tuple[Any, ...] = (),
    on_delete: RefDeleteAction = "set_default",
    on_delete_callback: OnDeleteCallback | str | None = None,
) -> RefField:
    """创建引用字段元数据（RefField 语法糖）。"""

    return RefField(
        target=target,
        default=default,
        allow_values=allow_values,
        on_delete=on_delete,
        on_delete_callback=on_delete_callback,
    )


def virtual(
    getter: VirtualFieldGetter | str,
    *,
    setter: VirtualFieldSetter | str | None = None,
    depends_on: tuple[VirtualDependency, ...] = (),
) -> VirtualField:
    """创建虚拟字段元数据（VirtualField 语法糖）。"""

    return VirtualField(getter=getter, setter=setter, depends_on=depends_on)


def encrypted() -> EncryptedFieldMarker:
    """创建加密字段标记（EncryptedFieldMarker 语法糖）。"""

    return EncryptedFieldMarker()


def singleton(config_type: type[Any]) -> SubConfigSpec:
    """声明单例子配置。"""

    return SubConfigSpec(types=(config_type,), singleton=True)


def sub_configs(**configs: Any):
    """声明配置类上的子配置挂载信息。

    该装饰器仅负责“记录元数据”，实际实例化发生在 ``@config`` 注入的
    ``model_post_init`` 阶段。

    Example:
        ``@sub_configs(UserData=[UserConfig], Tools=singleton(ToolsConfig))``

    Args:
        **configs: 属性名到子配置声明的映射。

    Returns:
        类装饰器，返回原类并附加 ``__config_sub_configs__`` 元数据。
    """

    normalized = {
        name: _normalize_sub_config_spec(spec) for name, spec in configs.items()
    }

    def _decorator(cls: type[Any]) -> type[Any]:
        inherited = dict(getattr(cls, "__config_sub_configs__", {}))
        inherited.update(normalized)
        setattr(cls, "__config_sub_configs__", inherited)
        return cls

    return _decorator


def relates_to(**targets: str):
    """声明配置类的引用目标映射。

    该映射用于在实例初始化时把 ``related_config`` 中的逻辑别名指向
    实例属性上的 ``MultipleConfig`` 容器。

    Example:
        ``@relates_to(PlanConfig="PlanConfig", ScriptConfig="ScriptConfig")``

    Args:
        **targets: 逻辑别名 -> 实例属性名。

    Returns:
        类装饰器，返回原类并附加 ``__config_relates_to__`` 元数据。
    """

    def _decorator(cls: type[Any]) -> type[Any]:
        inherited = dict(getattr(cls, "__config_relates_to__", {}))
        inherited.update(targets)
        setattr(cls, "__config_relates_to__", inherited)
        return cls

    return _decorator


def _init_sub_configs(instance: Any) -> None:
    """根据 ``__config_sub_configs__`` 元数据初始化子配置属性。

    行为规则：
    - 若实例已存在同名属性，则跳过（避免覆盖手工注入对象）；
    - ``singleton=True`` 时直接构造单个子配置实例；
    - 否则构造 ``MultipleConfig`` 容器。

    Args:
        instance: 当前配置对象实例。
    """

    instance_type = cast(type[Any], type(instance))
    specs: dict[str, SubConfigSpec] = dict(
        cast(
            dict[str, SubConfigSpec],
            getattr(instance_type, "__config_sub_configs__", {}),
        )
    )

    for name, spec in specs.items():
        if hasattr(instance, name):
            continue

        if spec.singleton:
            setattr(instance, name, spec.types[0]())
        else:
            setattr(instance, name, MultipleConfig(list(spec.types)))


def _init_related_targets(instance: Any) -> None:
    """将关系映射写入类级 ``related_config``。

    仅当目标属性是 ``MultipleConfig`` 时才会写入，避免错误类型污染
    引用解析表。

    Args:
        instance: 当前配置对象实例。
    """

    instance_type = cast(type[Any], type(instance))
    mapping: dict[str, str] = dict(
        cast(dict[str, str], getattr(instance_type, "__config_relates_to__", {}))
    )
    related = getattr(instance_type, "related_config", None)
    if not isinstance(related, dict):
        return

    for alias, attr_name in mapping.items():
        target = getattr(instance, attr_name, None)
        if isinstance(target, MultipleConfig):
            related[alias] = target


if TYPE_CHECKING:
    def config(cls: _ClsT) -> _ClsT: ...  # type: ignore[misc]
else:
    def config(cls: type[Any]) -> type[Any]:
        """配置类总装饰器：在 ``model_post_init`` 阶段完成运行期装配。

        装配顺序：
        1. 初始化子配置（``_init_sub_configs``）；
        2. 建立引用目标映射（``_init_related_targets``）；
        3. 调用原有 ``model_post_init``（如果存在）。

        这样可以确保原有后置初始化逻辑执行时，子配置和引用关系已可用。

        Args:
            cls: 被装饰的配置类。

        Returns:
            注入初始化逻辑后的原类。
        """

        original_model_post_init = getattr(cls, "model_post_init", None)

        def _model_post_init(self: Any, context: Any) -> None:
            _init_sub_configs(self)
            _init_related_targets(self)

            if callable(original_model_post_init):
                original_model_post_init(self, context)

        setattr(cls, "model_post_init", _model_post_init)
        return cls


__all__ = [
    "SubConfigSpec",
    "ref",
    "virtual",
    "encrypted",
    "singleton",
    "sub_configs",
    "relates_to",
    "config",
]
