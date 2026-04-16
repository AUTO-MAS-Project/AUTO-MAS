#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

"""DSL v2 统一类型导出模块（与 dsl.py / dsl_v2.py 同级）。"""

from copy import deepcopy
from typing import Annotated, Any, Generic, TypeVar

from . import dsl_v2 as _dsl

# 统一导出：插件侧推荐只 import 这个模块。
ConfigModel = _dsl.PluginConfigModel
SchemaModelAdapter = _dsl.SchemaModelAdapter

# 描述元数据与辅助函数
Desc = _dsl.Desc
describe = _dsl.describe

# 预定义类型（从 dsl_v2 迁移到 plgType）
Switch = Annotated[
    bool,
    _dsl.TypePreset(schema_type="boolean", ui={"widget": "switch"}),
]
String = Annotated[
    str,
    _dsl.TypePreset(schema_type="string", ui={"widget": "input"}),
]
Password = Annotated[
    str,
    _dsl.TypePreset(schema_type="string", format="password", ui={"widget": "password"}),
]
Number = Annotated[
    float,
    _dsl.TypePreset(schema_type="number", ui={"widget": "number"}),
]
PathText = Annotated[
    str,
    _dsl.TypePreset(
        schema_type="string",
        format="path",
        codec="path",
        ui={"widget": "path"},
    ),
]
StringList = Annotated[
    list[str],
    _dsl.TypePreset(schema_type="list", item_type="string", ui={"widget": "list"}),
]
KeyValueStr = Annotated[
    dict[str, str],
    _dsl.TypePreset(
        schema_type="key_value",
        item_type="string",
        ui={"widget": "key_value"},
    ),
]


U = TypeVar("U")


class TableOf(Generic[U]):
    """表格类型包装：TableOf[RowModel]。"""

    def __class_getitem__(cls, item: Any) -> Any:
        return _dsl.preset(
            list[item],
            schema_type="table",
            item_type="object",
            widget="table",
        )


class D:
    """描述语法糖。

    - 稳定写法：Annotated[T, D("描述")]
    - 实验写法：D[T, "描述"]（运行时可用，部分静态类型器会报无效类型表达式）
    """

    def __class_getitem__(cls, item: Any) -> Any:
        if not isinstance(item, tuple) or len(item) != 2:
            raise TypeError("D[...] 需要两个参数：D[Type, '描述文本']")
        py_type, text = item
        if not isinstance(text, str):
            raise TypeError("D[Type, text] 中 text 必须是字符串")
        return Annotated[py_type, Desc(text)]


class A:
    """注解语法糖：A[Type, "描述文本"]。

    说明：
    - 首个参数可为 plgType 预定义类型，也可为 Python 内置类型（如 str/int/list[str]）
    - 返回 Annotated[Type, Desc("...")]，供 dsl_v2 自动提取 description
    """

    def __class_getitem__(cls, item: Any) -> Any:
        if not isinstance(item, tuple) or len(item) != 2:
            raise TypeError("A[...] 需要两个参数：A[Type, '描述文本']")
        py_type, text = item
        if not isinstance(text, str):
            raise TypeError("A[Type, text] 中 text 必须是字符串")
        return Annotated[py_type, Desc(text)]


def extra(field: str | None = None, /, **ui: Any):
    """类装饰器：为字段追加前端扩展元数据。

    用法 1（推荐）:
        @extra("enable", group="basic", order=1)

    用法 2（批量）:
        @extra(enable={"group": "basic"}, title={"placeholder": "请输入"})
    """

    if field is None:
        mapping: dict[str, dict[str, Any]] = {}
        for name, payload in ui.items():
            if isinstance(payload, dict):
                mapping[name] = deepcopy(payload)
            else:
                raise TypeError("@extra(enable=...) 的值必须是字典")
    else:
        if not isinstance(field, str) or not field.strip():
            raise TypeError("@extra(field, ...) 的 field 必须是非空字符串")
        mapping = {field: deepcopy(ui)}

    def _decorator(config_cls):
        attr_name = _dsl.FIELD_UI_EXTRA_ATTR
        existing = getattr(config_cls, attr_name, {})
        if not isinstance(existing, dict):
            existing = {}
        merged = deepcopy(existing)
        for field_name, payload in mapping.items():
            current = merged.get(field_name, {})
            if not isinstance(current, dict):
                current = {}
            current.update(deepcopy(payload))
            merged[field_name] = current
        setattr(config_cls, attr_name, merged)
        return config_cls

    return _decorator


__all__ = [
    "ConfigModel",
    "SchemaModelAdapter",
    "Desc",
    "describe",
    "D",
    "A",
    "extra",
    "Switch",
    "String",
    "Password",
    "Number",
    "PathText",
    "StringList",
    "KeyValueStr",
    "TableOf",
]
