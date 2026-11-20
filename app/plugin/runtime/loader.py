"""Plugin code loading and module cache cleanup."""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import sys
from contextlib import suppress
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

from app.plugin.base.plugin import BasePlugin
from app.plugin.errors import PluginPrecheckError
from app.plugin.types import PLUGIN_API_VERSION, PLUGIN_ATTR
from app.utils.common.source_import import SourceFinder, SourceLoader

if TYPE_CHECKING:
    from app.models.config import PluginRecord


def clear(record: PluginRecord) -> None:
    """清理当前来源及实际已加载实现的模块，确保来源切换时不残留旧子模块。"""
    import_name = str(record.info.import_name or "").strip()
    if not import_name:
        raise PluginPrecheckError(
            f"插件缺少 import_name: {record.info.plugin_name}",
            payload={"name": record.info.plugin_name},
        )
    roots: set[tuple[str, Path]] = set()
    if record._project_dir is not None:
        roots.add((import_name, (record._project_dir / import_name).resolve()))
    cls = record._plugin_cls
    if cls is not None:
        for loaded_name in {import_name, cls.__module__.split(".", 1)[0]}:
            loaded = sys.modules.get(loaded_name)
            # PLUGIN 必须确实指向本项已加载的类，不能清理 SDK 基类或其他宿主模块。
            if (
                isinstance(loaded, ModuleType)
                and getattr(loaded, PLUGIN_ATTR, None) is cls
            ):
                loaded_file = getattr(loaded, "__file__", None)
                if loaded_file is not None:
                    roots.add((loaded_name, Path(loaded_file).resolve().parent))
    if not roots:
        raise PluginPrecheckError(
            f"插件 {import_name} 缺少来源路径",
            payload={"name": record.info.plugin_name},
        )
    for name, module in list(sys.modules.items()):
        directories = [
            directory
            for prefix, directory in roots
            if name == prefix or name.startswith(f"{prefix}.")
        ]
        if not directories:
            continue
        if not isinstance(module, ModuleType):
            del sys.modules[name]
            continue
        module_file = getattr(module, "__file__", None)
        if module_file is None:
            if any(name == prefix for prefix, _ in roots):
                del sys.modules[name]
            continue
        try:
            module_path = Path(module_file).resolve()
            belongs = any(
                module_path.is_relative_to(directory) for directory in directories
            )
        except (OSError, ValueError):
            continue
        if belongs:
            del sys.modules[name]


def load(record: PluginRecord) -> type[BasePlugin]:
    """Load the plugin entry class from the source root in the record."""
    import_name = str(record.info.import_name or "").strip()
    if not import_name:
        raise PluginPrecheckError(
            f"插件缺少 import_name: {record.info.plugin_name}",
            payload={"name": record.info.plugin_name},
        )
    if record._project_dir is None:
        raise PluginPrecheckError(
            f"插件 {import_name} 缺少来源路径",
            payload={"name": record.info.plugin_name},
        )
    load_search_root = record._project_dir.resolve()
    package_dir = (load_search_root / import_name).resolve()
    if not load_search_root.is_dir() or not package_dir.is_dir():
        raise PluginPrecheckError(
            f"插件包目录不存在: {package_dir}",
            payload={"name": record.info.plugin_name},
        )

    importlib.invalidate_caches()
    clear(record)
    spec = importlib.machinery.PathFinder.find_spec(
        import_name, [str(load_search_root)]
    )
    if spec is None:
        raise PluginPrecheckError(
            f"无法从 {load_search_root} 找到插件包 {import_name}",
            payload={"name": record.info.plugin_name, "import_name": import_name},
        )
    if spec.origin is None or spec.loader is None:
        raise PluginPrecheckError(
            f"插件 {import_name} 不支持 namespace package，请提供包含 __init__.py 的普通包",
            payload={"name": record.info.plugin_name, "import_name": import_name},
        )
    try:
        origin = Path(spec.origin).resolve()
        origin.relative_to(package_dir)
    except (OSError, ValueError) as exc:
        raise PluginPrecheckError(
            f"插件 {import_name} 的入口不在 {package_dir} 内",
            payload={"name": record.info.plugin_name, "import_name": import_name},
        ) from exc

    finder: SourceFinder | None = None
    if record.info.source == "local":
        # Development plugins bypass pyc through one temporary finder for entry and submodules.
        spec = importlib.util.spec_from_file_location(
            import_name,
            origin,
            loader=SourceLoader(import_name, str(origin)),
            submodule_search_locations=spec.submodule_search_locations,
        )
        if spec is None:
            raise PluginPrecheckError(
                f"无法创建插件加载 spec: {import_name}",
                payload={"name": record.info.plugin_name, "import_name": import_name},
            )
        finder = SourceFinder(import_name, package_dir)
        sys.meta_path.insert(0, finder)

    module_loader = spec.loader
    if module_loader is None:
        raise PluginPrecheckError(
            f"插件 {import_name} 缺少可执行加载器",
            payload={"name": record.info.plugin_name, "import_name": import_name},
        )
    try:
        module = importlib.util.module_from_spec(spec)
        sys.modules[import_name] = module
        module_loader.exec_module(module)
    except Exception as exc:
        clear(record)
        missing_name = getattr(exc, "name", None)
        if (
            record.info.source == "local"
            and isinstance(exc, ModuleNotFoundError)
            and isinstance(missing_name, str)
        ):
            outside_path = (load_search_root / missing_name.split(".", 1)[0]).resolve()
            try:
                outside_path.relative_to(load_search_root)
                outside_path.relative_to(package_dir)
            except (OSError, ValueError):
                if outside_path.exists() or outside_path.with_suffix(".py").is_file():
                    raise PluginPrecheckError(
                        f"插件 {import_name} 的代码必须全部位于 {package_dir} 内，检测到包外模块 {missing_name}",
                        payload={
                            "name": record.info.plugin_name,
                            "module": missing_name,
                        },
                    ) from exc
        raise PluginPrecheckError(
            f"无法导入插件包: {import_name}",
            payload={"name": record.info.plugin_name, "import_name": import_name},
        ) from exc
    finally:
        if finder is not None:
            with suppress(ValueError):
                sys.meta_path.remove(finder)

    cls = getattr(module, PLUGIN_ATTR, None)
    if cls is None:
        clear(record)
        raise PluginPrecheckError(
            f"包 `{import_name}` 未导出 {PLUGIN_ATTR}",
            payload={"name": record.info.plugin_name, "import_name": import_name},
        )
    if not isinstance(cls, type) or not issubclass(cls, BasePlugin):
        clear(record)
        raise PluginPrecheckError(
            f"`{import_name}.{PLUGIN_ATTR}` 须为 BasePlugin 子类",
            payload={"name": record.info.plugin_name, "import_name": import_name},
        )

    declared_api = getattr(module, "PLUGIN_API_VERSION", None)
    # 协议主版本独立于 SDK 的宿主发行版本范围。
    if declared_api is not None:
        expected_major = str(PLUGIN_API_VERSION).split(".", 1)[0]
        actual_major = str(declared_api).split(".", 1)[0]
        if actual_major != expected_major:
            clear(record)
            raise PluginPrecheckError(
                f"插件 {import_name} 的协议主版本 {declared_api} "
                f"与当前 {PLUGIN_API_VERSION} 不兼容",
                payload={
                    "name": record.info.plugin_name,
                    "import_name": import_name,
                    "expected": PLUGIN_API_VERSION,
                    "actual": str(declared_api),
                },
            )

    record.info.requires = list(getattr(cls, "requires", []) or [])
    record.info.wants = list(getattr(cls, "wants", []) or [])
    return cls
