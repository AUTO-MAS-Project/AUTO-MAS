#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2026 AUTO-MAS Team

from __future__ import annotations

import inspect
import os
import types
from collections.abc import Callable as AbcCallable
from pathlib import Path
from typing import Any, Dict, Literal, Optional, Union, get_args, get_origin

_HEADER = "# 此文件由 AUTO-MAS 自动生成，请勿手动修改。\n"


def is_dev_stub_generation_enabled() -> bool:
    """判断是否启用开发环境的插件上下文 stub 自动生成。

    规则：
    - 当环境变量 AUTO_MAS_DEV 的值为 1/true/yes/on（忽略大小写）时返回 True。
    - 其余情况返回 False。

    Returns:
        bool: 是否启用开发环境 stub 生成。
    """
    raw = str(os.getenv("AUTO_MAS_DEV", "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def generate_plugin_context_stubs(output_dir: Optional[Path] = None) -> Dict[str, Any]:
    """生成插件开发可用的 .pyi 类型提示文件。

    该方法会基于核心上下文类的真实签名进行反射，并输出稳定排序的 .pyi 文件，
    用于插件开发时为 ``ctx`` 提供补全、签名和文档提示。

    Args:
        output_dir (Optional[Path]): 输出目录；为空时使用默认目录。

    Returns:
        Dict[str, Any]: 生成摘要，包含输出目录、变更文件和未变更文件。

    Raises:
        OSError: 目标目录创建失败或写入文件失败时抛出。
    """
    target_dir = output_dir or (Path.cwd() / "plugins" / "_generated")
    target_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "__init__.pyi": _render_init_stub(),
        "context.pyi": _render_context_stub(),
        "runtime_api.pyi": _render_runtime_api_stub(),
        "cache_store.pyi": _render_cache_store_stub(),
    }

    changed_files: list[str] = []
    unchanged_files: list[str] = []

    for file_name, content in files.items():
        target_file = target_dir / file_name
        current = ""
        if target_file.exists():
            current = target_file.read_text(encoding="utf-8")

        if current == content:
            unchanged_files.append(file_name)
            continue

        target_file.write_text(content, encoding="utf-8")
        changed_files.append(file_name)

    return {
        "output_dir": str(target_dir),
        "changed_files": changed_files,
        "unchanged_files": unchanged_files,
        "generated_files": list(files.keys()),
    }


def _render_init_stub() -> str:
    lines = [
        _HEADER.rstrip("\n"),
        "",
        "from .cache_store import JsonPluginCache, PluginCacheManager",
        "from .context import PluginContext, RuntimeFacade",
        "from .runtime_api import RuntimeAPI",
        "",
        "__all__ = [",
        '    "PluginContext",',
        '    "RuntimeFacade",',
        '    "RuntimeAPI",',
        '    "PluginCacheManager",',
        '    "JsonPluginCache",',
        "]",
        "",
    ]
    return "\n".join(lines)


def _render_context_stub() -> str:
    plugin_context_cls, runtime_facade_cls, _runtime_api_cls, plugin_config_proxy_cls, service_facade_cls, server_facade_cls = (
        _load_stub_target_classes()
    )

    class_attrs = {
        "plugin_name": "str",
        "instance_id": "str",
        "config": plugin_config_proxy_cls.__name__,
        "logger": "Any",
        "events": "Any",
        "runtime_api": "RuntimeAPI",
        "runtime": runtime_facade_cls.__name__,
        "service": service_facade_cls.__name__,
        "server": server_facade_cls.__name__,
        "cache": "PluginCacheManager",
    }
    runtime_facade_attrs = {"_api": "RuntimeAPI"}

    lines = [
        _HEADER.rstrip("\n"),
        "",
        "from typing import Any, Callable, Dict, Optional",
        "",
        "from .cache_store import PluginCacheManager",
        "from .context import PluginConfigProxy, ServiceFacade",
        "from .runtime_api import RuntimeAPI",
        "from .server import PluginServerFacade",
        "",
    ]
    lines.extend(_render_class_stub(plugin_context_cls, class_attrs))
    lines.append("")
    lines.extend(_render_class_stub(service_facade_cls, {}))
    lines.append("")
    lines.extend(_render_class_stub(runtime_facade_cls, runtime_facade_attrs))
    lines.append("")
    return "\n".join(lines)


def _render_runtime_api_stub() -> str:
    _plugin_context_cls, _runtime_facade_cls, runtime_api_cls, _plugin_config_proxy_cls, _service_facade_cls, _server_facade_cls = (
        _load_stub_target_classes()
    )

    lines = [
        _HEADER.rstrip("\n"),
        "",
        "from pathlib import Path",
        "from typing import Any, Callable, Dict, Optional",
        "",
    ]
    lines.extend(_render_class_stub(runtime_api_cls, {}))
    lines.append("")
    return "\n".join(lines)


def _render_cache_store_stub() -> str:
    json_plugin_cache_cls, plugin_cache_manager_cls = _load_cache_classes()

    cache_attrs = {
        "cache_name": "str",
        "file_path": "Path",
        "limit": "int",
        "limit_mode": "LimitMode",
    }
    manager_attrs = {
        "plugin_name": "str",
        "instance_id": "str",
        "logger": "Any",
    }

    lines = [
        _HEADER.rstrip("\n"),
        "",
        "from pathlib import Path",
        "from typing import Any, Dict, Literal",
        "",
        'LimitMode = Literal["count", "bytes"]',
        'CacheBackendType = Literal["json", "database"]',
        'LimitUnit = Literal["b", "kb", "mb", "gb"]',
        "",
    ]
    lines.extend(_render_class_stub(json_plugin_cache_cls, cache_attrs))
    lines.append("")
    lines.extend(_render_class_stub(plugin_cache_manager_cls, manager_attrs))
    lines.append("")
    return "\n".join(lines)


def _load_stub_target_classes() -> tuple[type, type, type, type, type, type]:
    """延迟加载生成上下文 stub 所需的核心类。"""
    from app.core.plugins.context import PluginConfigProxy, PluginContext, RuntimeFacade, ServiceFacade
    from app.core.plugins.runtime_api import RuntimeAPI
    from app.core.plugins.server import PluginServerFacade

    return PluginContext, RuntimeFacade, RuntimeAPI, PluginConfigProxy, ServiceFacade, PluginServerFacade


def _load_cache_classes() -> tuple[type, type]:
    """延迟加载缓存模块中的类，避免模块导入阶段触发循环依赖。"""
    from app.core.plugins.cache_store import JsonPluginCache, PluginCacheManager

    return JsonPluginCache, PluginCacheManager


def _render_class_stub(cls: type, attrs: Dict[str, str]) -> list[str]:
    """渲染单个类的 .pyi 声明代码。

    Args:
        cls (type): 目标类对象。
        attrs (Dict[str, str]): 需要额外声明的实例属性映射。

    Returns:
        list[str]: 该类对应的 .pyi 行列表。
    """
    lines: list[str] = [f"class {cls.__name__}:"]
    doc = _clean_doc(getattr(cls, "__doc__", None))
    if doc:
        lines.append(f'    """{doc}"""')

    if attrs:
        for attr_name in sorted(attrs.keys()):
            lines.append(f"    {attr_name}: {attrs[attr_name]}")
        lines.append("")

    callable_members: list[tuple[str, Any, str]] = []
    for name, member in cls.__dict__.items():
        if name.startswith("_") and name not in {"__init__", "__getattr__"}:
            continue

        if isinstance(member, property):
            callable_members.append((name, member, "property"))
            continue

        if isinstance(member, staticmethod):
            callable_members.append((name, member.__func__, "staticmethod"))
            continue

        if isinstance(member, classmethod):
            callable_members.append((name, member.__func__, "classmethod"))
            continue

        if inspect.isfunction(member):
            callable_members.append((name, member, "method"))

    if not callable_members:
        lines.append("    ...")
        return lines

    for name, member, member_type in callable_members:
        if member_type == "property":
            lines.extend(_render_property_stub(name, member))
        else:
            lines.extend(_render_function_stub(name, member, member_type))
        lines.append("")

    if lines[-1] == "":
        lines.pop()
    return lines


def _render_property_stub(name: str, prop: property) -> list[str]:
    """渲染 property 的 .pyi 声明。

    Args:
        name (str): 属性名。
        prop (property): property 对象。

    Returns:
        list[str]: property 对应声明行。
    """
    fget = prop.fget
    if fget is None:
        return ["    @property", f"    def {name}(self) -> Any: ..."]

    return_type = _format_annotation(
        fget.__annotations__.get("return", inspect.Signature.empty)
    )
    doc = _clean_doc(getattr(fget, "__doc__", None))
    lines = ["    @property", f"    def {name}(self) -> {return_type}:"]
    if doc:
        lines.append(f'        """{doc}"""')
    lines.append("        ...")
    return lines


def _render_function_stub(name: str, func: Any, member_type: str) -> list[str]:
    """渲染方法或函数的 .pyi 声明。

    Args:
        name (str): 方法名。
        func (Any): 方法函数对象。
        member_type (str): 成员类型，支持 method/classmethod/staticmethod。

    Returns:
        list[str]: 方法声明行。
    """
    signature = inspect.signature(func)
    params = _format_parameters(signature)
    return_type = _format_annotation(signature.return_annotation)
    is_async = inspect.iscoroutinefunction(func)
    prefix = "async def" if is_async else "def"

    lines: list[str] = []
    if member_type == "classmethod":
        lines.append("    @classmethod")
    elif member_type == "staticmethod":
        lines.append("    @staticmethod")

    lines.append(f"    {prefix} {name}({params}) -> {return_type}:")

    doc = _clean_doc(getattr(func, "__doc__", None))
    if doc:
        lines.append(f'        """{doc}"""')

    lines.append("        ...")
    return lines


def _format_parameters(signature: inspect.Signature) -> str:
    """将函数签名参数转换为 .pyi 兼容字符串。"""
    chunks: list[str] = []
    inserted_kw_marker = False

    for param in signature.parameters.values():
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            text = f"*{param.name}: {_format_annotation(param.annotation)}"
            chunks.append(text)
            inserted_kw_marker = True
            continue

        if param.kind == inspect.Parameter.VAR_KEYWORD:
            text = f"**{param.name}: {_format_annotation(param.annotation)}"
            chunks.append(text)
            continue

        if param.kind == inspect.Parameter.KEYWORD_ONLY and not inserted_kw_marker:
            chunks.append("*")
            inserted_kw_marker = True

        text = param.name
        ann = _format_annotation(param.annotation)
        should_emit_annotation = not (
            param.name in {"self", "cls"}
            and param.annotation is inspect.Signature.empty
        )
        if ann and should_emit_annotation:
            text += f": {ann}"
        if param.default is not inspect.Signature.empty:
            text += " = ..."
        chunks.append(text)

    return ", ".join(chunks)


def _format_annotation(annotation: Any) -> str:
    """将注解对象转换为 .pyi 友好文本。"""
    if annotation is inspect.Signature.empty:
        return "Any"

    if isinstance(annotation, str):
        return annotation

    if annotation is None or annotation is type(None):
        return "None"

    if annotation is Any:
        return "Any"

    origin = get_origin(annotation)
    if origin in {types.UnionType, Union}:
        args = get_args(annotation)
        if args:
            return " | ".join(_format_annotation(arg) for arg in args)

    if origin is Literal:
        literal_args = ", ".join(repr(arg) for arg in get_args(annotation))
        return f"Literal[{literal_args}]"

    if origin in {AbcCallable}:
        args = get_args(annotation)
        if not args:
            return "Callable[..., Any]"
        callable_params = args[0]
        callable_return = args[1] if len(args) > 1 else Any
        if callable_params is Ellipsis:
            return f"Callable[..., {_format_annotation(callable_return)}]"
        elif isinstance(callable_params, (list, tuple)):
            params_text = ", ".join(_format_annotation(arg) for arg in callable_params)
        else:
            params_text = _format_annotation(callable_params)
        return f"Callable[[{params_text}], {_format_annotation(callable_return)}]"

    if origin is not None:
        origin_name = _format_origin_name(origin)
        args = get_args(annotation)
        if args:
            args_text = ", ".join(_format_annotation(arg) for arg in args)
            return f"{origin_name}[{args_text}]"
        return origin_name

    module_name = getattr(annotation, "__module__", "")
    qualname = getattr(annotation, "__qualname__", None)
    if module_name == "builtins" and qualname:
        return qualname
    if qualname:
        return qualname
    return "Any"


def _format_origin_name(origin: Any) -> str:
    """格式化泛型 origin 名称。"""
    module_name = getattr(origin, "__module__", "")
    qualname = getattr(origin, "__qualname__", None) or getattr(origin, "__name__", None)
    if module_name == "builtins" and qualname:
        return qualname
    if qualname:
        return qualname
    return "Any"


def _clean_doc(doc: Optional[str]) -> str:
    """提取 docstring 的首段文本并清理空白。"""
    if not doc:
        return ""

    text = inspect.cleandoc(doc).strip()
    if not text:
        return ""

    first_block = text.split("\n\n", maxsplit=1)[0].replace('"""', "'''")
    return first_block


def main() -> None:
    """独立执行入口：按当前环境变量决定是否生成插件上下文 stub。

    Returns:
        None

    Raises:
        OSError: 当生成目录创建或文件写入失败时抛出。
    """
    if not is_dev_stub_generation_enabled():
        print("AUTO_MAS_DEV 未开启，已跳过插件上下文类型提示生成。")
        return

    result = generate_plugin_context_stubs()
    print(
        "插件上下文类型提示生成完成: "
        f"changed={len(result.get('changed_files', []))}, "
        f"unchanged={len(result.get('unchanged_files', []))}, "
        f"dir={result.get('output_dir', '')}"
    )


if __name__ == "__main__":
    main()
