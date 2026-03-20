#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2026 AUTO-MAS Team

import sys
import importlib.metadata as importlib_metadata
from pathlib import Path
from typing import List


ENTRY_POINT_GROUPS = ("auto_mas.plugins", "automas.plugins")


def get_pypi_root(plugins_dir: Path | None = None) -> Path:
    """获取插件 PyPI 根目录路径。"""
    base_plugins_dir = plugins_dir or (Path.cwd() / "plugins")
    return base_plugins_dir / "pypi"


def get_pypi_site_packages_dir(plugins_dir: Path | None = None) -> Path:
    """获取插件 PyPI site-packages 目录路径。"""
    return get_pypi_root(plugins_dir) / "site-packages"


def ensure_pypi_site_packages_on_syspath(plugins_dir: Path | None = None) -> Path:
    """确保 plugins/pypi/site-packages 目录存在并加入 sys.path。"""
    site_dir = get_pypi_site_packages_dir(plugins_dir)
    site_dir.mkdir(parents=True, exist_ok=True)

    normalized = str(site_dir.resolve())
    if normalized not in sys.path:
        sys.path.insert(0, normalized)

    return site_dir


def iter_plugin_entry_points(plugins_dir: Path | None = None) -> List[importlib_metadata.EntryPoint]:
    """仅扫描 plugins/pypi/site-packages 下分发包的插件入口点。"""
    site_dir = ensure_pypi_site_packages_on_syspath(plugins_dir)
    result: list[importlib_metadata.EntryPoint] = []
    seen: set[tuple[str, str, str]] = set()

    for dist in importlib_metadata.distributions(path=[str(site_dir)]):
        for ep in getattr(dist, "entry_points", []):
            if ep.group not in ENTRY_POINT_GROUPS:
                continue
            key = (ep.group, ep.name, ep.value)
            if key in seen:
                continue
            seen.add(key)
            result.append(ep)

    return result
