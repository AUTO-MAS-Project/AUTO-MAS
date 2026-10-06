"""Plugin code loading and module cache cleanup."""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import sys
from contextlib import suppress
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

from app.plugin.base.plugin import BasePlugin
from app.plugin.errors import PluginPrecheckError
from app.plugin.types import PLUGIN_API_VERSION, PLUGIN_ATTR

if TYPE_CHECKING:
    from app.models.config import PluginRecord


class _SourceLoader(importlib.machinery.SourceFileLoader):
    def get_code(self, fullname: str):
        source_path = self.get_filename(fullname)
        return self.source_to_code(self.get_data(source_path), source_path)


class _SourceFinder(importlib.abc.MetaPathFinder):
    def __init__(self, package_name: str, package_dir: Path) -> None:
        self.package_name = package_name
        self.package_dir = package_dir

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None = None,
        target: ModuleType | None = None,
    ):
        if fullname != self.package_name and not fullname.startswith(
            f"{self.package_name}."
        ):
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if spec is None or spec.origin is None:
            return spec
        try:
            origin = Path(spec.origin).resolve()
            origin.relative_to(self.package_dir)
        except (OSError, ValueError):
            return spec
        return importlib.util.spec_from_file_location(
            fullname,
            origin,
            loader=_SourceLoader(fullname, str(origin)),
            submodule_search_locations=spec.submodule_search_locations,
        )


def clear(record: PluginRecord) -> None:
    """Remove target package modules that belong to the recorded source path."""
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
    package_dir = record._project_dir / import_name
    for name, module in list(sys.modules.items()):
        if name != import_name and not name.startswith(f"{import_name}."):
            continue
        if not isinstance(module, ModuleType):
            del sys.modules[name]
            continue
        module_file = getattr(module, "__file__", None)
        if module_file is None:
            if name == import_name:
                del sys.modules[name]
            continue
        try:
            Path(module_file).resolve().relative_to(package_dir)
        except (OSError, ValueError):
            continue
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

    finder: _SourceFinder | None = None
    if record.info.source == "local":
        # Development plugins bypass pyc through one temporary finder for entry and submodules.
        spec = importlib.util.spec_from_file_location(
            import_name,
            origin,
            loader=_SourceLoader(import_name, str(origin)),
            submodule_search_locations=spec.submodule_search_locations,
        )
        if spec is None:
            raise PluginPrecheckError(
                f"无法创建插件加载 spec: {import_name}",
                payload={"name": record.info.plugin_name, "import_name": import_name},
            )
        finder = _SourceFinder(import_name, package_dir)
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
    # 协议代际：仅比较主版本（与依赖 auto_mas_core>=6,<7 对齐）
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
