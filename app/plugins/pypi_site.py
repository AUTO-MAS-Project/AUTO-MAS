#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2026 AUTO-MAS Team

import sys
import json
import site
import importlib.metadata as importlib_metadata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
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


_site_packages_initialized: Path | None = None
_site_packages_initialized_mtime_ns: int | None = None

# 入口点扫描缓存: 以 site-packages 目录 mtime 为失效依据。
# uv/pip 安装或卸载分发包会在该目录下增删 .dist-info 目录, 从而更新目录 mtime。
_entry_points_cache: Dict[str, tuple[int, List[importlib_metadata.EntryPoint]]] = {}


def _site_dir_mtime_ns(site_dir: Path) -> int:
    try:
        return site_dir.stat().st_mtime_ns
    except OSError:
        return -1


def invalidate_entry_points_cache() -> None:
    """清除插件入口点与 editable 导入路径缓存。"""
    global _site_packages_initialized_mtime_ns
    _entry_points_cache.clear()
    _site_packages_initialized_mtime_ns = None


def ensure_pypi_site_packages_on_syspath(plugins_dir: Path | None = None) -> Path:
    """
    确保插件 site-packages 目录存在并加入当前进程的 sys.path。

    Args:
        plugins_dir (Path | None): 插件根目录；为 None 时使用默认 plugins 目录。

    Returns:
        Path: 最终加入 sys.path 的 site-packages 目录路径。
    """
    global _site_packages_initialized, _site_packages_initialized_mtime_ns
    site_dir = get_pypi_site_packages_dir(plugins_dir)
    site_dir.mkdir(parents=True, exist_ok=True)
    site_dir_mtime_ns = _site_dir_mtime_ns(site_dir)
    if (
        _site_packages_initialized == site_dir
        and _site_packages_initialized_mtime_ns == site_dir_mtime_ns
    ):
        return site_dir

    normalized = str(site_dir.resolve())
    site.addsitedir(normalized)

    _move_sys_path_to_front(Path(normalized))
    for editable_path in reversed(_iter_editable_import_paths(site_dir)):
        _move_sys_path_to_front(editable_path)

    _site_packages_initialized = site_dir
    _site_packages_initialized_mtime_ns = site_dir_mtime_ns
    return site_dir


def _move_sys_path_to_front(path: Path) -> None:
    normalized = str(path.resolve())
    while normalized in sys.path:
        sys.path.remove(normalized)
    sys.path.insert(0, normalized)


def _iter_editable_import_paths(site_dir: Path) -> List[Path]:
    paths: list[Path] = []
    seen: set[str] = set()
    for dist in importlib_metadata.distributions(path=[str(site_dir)]):
        project_path = _resolve_dist_editable_project_path(dist)
        if project_path is None:
            continue
        import_path = project_path / "src" if (project_path / "src").exists() else project_path
        normalized = str(import_path.resolve())
        if normalized in seen:
            continue
        seen.add(normalized)
        paths.append(import_path)
    return paths


def get_plugin_import_paths(plugins_dir: Path | None = None) -> List[Path]:
    """
    返回插件 site-packages 及 editable 安装的导入路径列表。

    用于为子进程构造 PYTHONPATH，使其能像主进程一样导入插件包及其依赖。
    顺序与 ensure_pypi_site_packages_on_syspath 保持一致：editable 安装的
    src 目录在前，插件 site-packages 在后。

    Args:
        plugins_dir (Path | None): 插件根目录；为 None 时使用默认 plugins 目录。

    Returns:
        List[Path]: 导入路径列表（仅返回已存在的路径）。
    """
    site_dir = get_pypi_site_packages_dir(plugins_dir)
    paths: list[Path] = []
    if site_dir.is_dir():
        paths.extend(_iter_editable_import_paths(site_dir))
        paths.append(site_dir)
    return paths


def iter_plugin_entry_points(plugins_dir: Path | None = None) -> List[importlib_metadata.EntryPoint]:
    """
    枚举本地插件 site-packages 中声明的插件入口点。

    Args:
        plugins_dir (Path | None): 插件根目录；为 None 时使用默认 plugins 目录。

    Returns:
        List[importlib_metadata.EntryPoint]: 去重后的插件入口点列表。
    """
    site_dir = ensure_pypi_site_packages_on_syspath(plugins_dir)
    cache_key = str(site_dir)
    mtime = _site_dir_mtime_ns(site_dir)
    cached = _entry_points_cache.get(cache_key)
    if cached is not None and cached[0] == mtime:
        return list(cached[1])

    candidates: list[tuple[bool, importlib_metadata.EntryPoint]] = []

    for dist in importlib_metadata.distributions(path=[str(site_dir)]):
        if _is_broken_editable_distribution(dist):
            continue
        is_editable = _resolve_dist_editable_project_path(dist) is not None
        for ep in getattr(dist, "entry_points", []):
            if ep.group not in ENTRY_POINT_GROUPS:
                continue
            candidates.append((is_editable, ep))

    result: list[importlib_metadata.EntryPoint] = []
    seen: set[tuple[str, str, str]] = set()
    for _, ep in sorted(candidates, key=lambda item: not item[0]):
        key = (ep.group, ep.name, ep.value)
        if key in seen:
            continue
        seen.add(key)
        result.append(ep)

    _entry_points_cache[cache_key] = (mtime, list(result))
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

    dir_info = data.get("dir_info")
    if not isinstance(dir_info, dict) or dir_info.get("editable") is not True:
        return None

    url = str(data.get("url") or "").strip()
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
