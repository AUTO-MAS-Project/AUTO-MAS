#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2026 AUTO-MAS Team

import sys
import importlib.metadata as importlib_metadata
from pathlib import Path
from typing import List


ENTRY_POINT_GROUPS = ("auto_mas.plugins", "automas.plugins")


def get_pypi_root(plugins_dir: Path | None = None) -> Path:
    """
    返回插件本地 PyPI 工作根目录路径。

    Args:
        plugins_dir (Path | None): 插件根目录；为 None 时使用当前工作目录下的 plugins。

    Returns:
        Path: plugins/pypi 目录路径。
    """
    base_plugins_dir = plugins_dir or (Path.cwd() / "plugins")
    return base_plugins_dir / "pypi"


def get_pypi_site_packages_dir(plugins_dir: Path | None = None) -> Path:
    """
    返回插件本地 PyPI 的 site-packages 目录路径。

    Args:
        plugins_dir (Path | None): 插件根目录；为 None 时使用默认 plugins 目录。

    Returns:
        Path: plugins/pypi/site-packages 目录路径。
    """
    return get_pypi_root(plugins_dir) / "site-packages"


def ensure_pypi_site_packages_on_syspath(plugins_dir: Path | None = None) -> Path:
    """
    确保插件 site-packages 目录存在并加入当前进程的 sys.path。

    Args:
        plugins_dir (Path | None): 插件根目录；为 None 时使用默认 plugins 目录。

    Returns:
        Path: 最终加入 sys.path 的 site-packages 目录路径。
    """
    site_dir = get_pypi_site_packages_dir(plugins_dir)
    site_dir.mkdir(parents=True, exist_ok=True)

    normalized = str(site_dir.resolve())
    if normalized not in sys.path:
        sys.path.insert(0, normalized)

    return site_dir


def iter_plugin_entry_points(plugins_dir: Path | None = None) -> List[importlib_metadata.EntryPoint]:
    """
    枚举本地插件 site-packages 中声明的插件入口点。

    Args:
        plugins_dir (Path | None): 插件根目录；为 None 时使用默认 plugins 目录。

    Returns:
        List[importlib_metadata.EntryPoint]: 去重后的插件入口点列表。
    """
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
