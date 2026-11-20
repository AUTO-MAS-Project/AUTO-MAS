"""按指定源码目录加载 Python 模块，保留原生扩展加载规则。"""

import importlib.abc
import importlib.machinery
import importlib.util
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType


class SourceLoader(importlib.machinery.SourceFileLoader):
    def get_code(self, fullname: str):
        """直接读取并编译插件源码，避免重载时复用旧的字节码缓存。"""
        source_path = self.get_filename(fullname)
        return self.source_to_code(self.get_data(source_path), source_path)


class SourceFinder(importlib.abc.MetaPathFinder):
    def __init__(self, package_name: str, package_dir: Path) -> None:
        """限定当前源码查找器负责的插件包名与源码目录。"""
        self.package_name = package_name
        self.package_dir = package_dir

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None = None,
        target: ModuleType | None = None,
    ):
        """仅为目标插件及其子模块生成源码加载规则，其他模块交给默认导入机制处理。"""
        if fullname != self.package_name and not fullname.startswith(
            f"{self.package_name}."
        ):
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if (
            spec is None
            or spec.origin is None
            or not isinstance(spec.loader, importlib.machinery.SourceFileLoader)
        ):
            return spec
        try:
            origin = Path(spec.origin).resolve()
            origin.relative_to(self.package_dir)
        except (OSError, ValueError):
            return spec
        return importlib.util.spec_from_file_location(
            fullname,
            origin,
            loader=SourceLoader(fullname, str(origin)),
            submodule_search_locations=spec.submodule_search_locations,
        )


def prefer_package_source(package_name: str, import_root: Path) -> None:
    """独立 worker 避免使用上一代插件写入的字节码缓存。"""
    sys.meta_path.insert(0, SourceFinder(package_name, import_root / package_name))
