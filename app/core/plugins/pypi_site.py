#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2026 AUTO-MAS Team

import sys
import json
import site
import importlib.metadata as importlib_metadata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, cast
from urllib.parse import urlparse, unquote
from urllib.request import url2pathname


ENTRY_POINT_GROUPS = ("auto_mas.plugins", "automas.plugins")


@dataclass
class InstalledPluginEntryPoint:
    """已安装插件入口点快照。"""

    name: str
    group: str
    value: str
    distribution: str | None
    version: str | None
    editable_project_path: Path | None


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
    # 使用 addsitedir 以确保 editable 安装生成的 .pth 文件被解析。
    # 仅插入 sys.path 不会触发 .pth 处理，可能导致 entry point 模块不可导入。
    site.addsitedir(normalized)

    # 维持插件目录优先级，避免被全局环境同名包覆盖。
    if normalized in sys.path:
        sys.path.remove(normalized)
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
        if _is_broken_editable_distribution(dist):
            continue
        for ep in getattr(dist, "entry_points", []):
            if ep.group not in ENTRY_POINT_GROUPS:
                continue
            key = (ep.group, ep.name, ep.value)
            if key in seen:
                continue
            seen.add(key)
            result.append(ep)

    return result


def _resolve_dist_editable_project_path(dist: importlib_metadata.Distribution) -> Optional[Path]:
    """解析分发包对应的 editable 本地工程路径。

    Args:
        dist (importlib_metadata.Distribution): 目标分发对象。

    Returns:
        Optional[Path]: 可解析时返回工程根目录路径；否则返回 None。
    """
    try:
        direct_url_path = Path(str(dist.locate_file("direct_url.json")))
        if not direct_url_path.exists():
            return _resolve_dist_editable_project_path_from_pth(dist)
        data = json.loads(direct_url_path.read_text(encoding="utf-8"))
    except Exception:
        return _resolve_dist_editable_project_path_from_pth(dist)

    if not isinstance(data, dict):
        return None

    direct_url_data = cast(dict[str, Any], data)
    url = str(direct_url_data.get("url") or "").strip()
    parsed = urlparse(url)
    if parsed.scheme != "file":
        return None

    raw_path = unquote(parsed.path or "")
    if parsed.netloc:
        raw_path = f"//{parsed.netloc}{raw_path}"
    local_path = Path(url2pathname(raw_path)).resolve()
    return _normalize_editable_project_path(local_path)


def _normalize_editable_project_path(candidate: Path) -> Optional[Path]:
    """规范化 editable 源路径到插件工程根目录。"""
    if not candidate.exists():
        return None

    resolved = candidate.resolve()
    if (resolved / "pyproject.toml").exists():
        return resolved

    if resolved.name == "src" and (resolved.parent / "pyproject.toml").exists():
        return resolved.parent

    return resolved


def _resolve_dist_editable_project_path_from_pth(
    dist: importlib_metadata.Distribution,
) -> Optional[Path]:
    """从 pip editable 生成的 __editable__.pth 回退解析工程路径。"""
    dist_name = str(getattr(dist, "name", "") or "").strip()
    dist_version = str(getattr(dist, "version", "") or "").strip()
    if not dist_name or not dist_version:
        return None

    normalized_name = dist_name.replace("-", "_")
    pth_file = Path(str(dist.locate_file(f"__editable__.{normalized_name}-{dist_version}.pth")))
    if not pth_file.exists():
        return None

    try:
        content = pth_file.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    for line in content.splitlines():
        text = str(line or "").strip()
        if not text or text.startswith("#"):
            continue
        return _normalize_editable_project_path(Path(text))

    return None


def _is_broken_editable_distribution(dist: importlib_metadata.Distribution) -> bool:
    """判断分发是否为损坏的 editable 安装（源码路径不存在）。"""
    dist_name = str(getattr(dist, "name", "") or "").strip()
    dist_version = str(getattr(dist, "version", "") or "").strip()
    if not dist_name or not dist_version:
        return False

    normalized_name = dist_name.replace("-", "_")
    pth_file = Path(str(dist.locate_file(f"__editable__.{normalized_name}-{dist_version}.pth")))
    if not pth_file.exists():
        return False

    try:
        content = pth_file.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return True

    for line in content.splitlines():
        text = str(line or "").strip()
        if not text or text.startswith("#"):
            continue
        return not Path(text).exists()

    return True


def resolve_entry_point_editable_project_path(
    entry_point: importlib_metadata.EntryPoint,
) -> Optional[Path]:
    """解析单个插件入口点对应的 editable 本地工程路径。

    Args:
        entry_point (importlib_metadata.EntryPoint): 插件入口点。

    Returns:
        Optional[Path]: 可解析时返回本地工程路径；不可解析时返回 None。
    """
    dist = getattr(entry_point, "dist", None)
    if dist is None:
        return None
    return _resolve_dist_editable_project_path(dist)


def get_installed_plugin_entry_points(
    plugins_dir: Path | None = None,
) -> Dict[str, list[InstalledPluginEntryPoint]]:
    """读取本地 site-packages 中的插件入口点快照并按插件名分组。

    Args:
        plugins_dir (Path | None): 插件根目录；为 None 时使用默认 plugins 目录。

    Returns:
        Dict[str, list[InstalledPluginEntryPoint]]: 键为入口点名称，值为该名称对应的入口点信息列表。
    """
    result: Dict[str, list[InstalledPluginEntryPoint]] = {}
    for ep in iter_plugin_entry_points(plugins_dir):
        dist = getattr(ep, "dist", None)
        info = InstalledPluginEntryPoint(
            name=str(getattr(ep, "name", "") or "").strip(),
            group=str(getattr(ep, "group", "") or "").strip(),
            value=str(getattr(ep, "value", "") or "").strip(),
            distribution=getattr(dist, "name", None),
            version=getattr(dist, "version", None),
            editable_project_path=_resolve_dist_editable_project_path(dist) if dist is not None else None,
        )
        if not info.name:
            continue
        result.setdefault(info.name, []).append(info)

    return result
