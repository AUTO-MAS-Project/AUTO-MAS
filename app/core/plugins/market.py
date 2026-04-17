#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2026 AUTO-MAS Team

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

import httpx
import importlib.metadata as importlib_metadata

from app.utils.logger import get_logger

from .pypi_site import get_pypi_site_packages_dir


logger = get_logger("插件市场")

# 统一前缀 tag 变量：当前要求同时支持 automas_plugin_xxx 与 automas_xxx
PYPI_MARKET_PREFIX_TAGS: tuple[str, ...] = ("automas_plugin_", "automas_")

# 额外候选名（可手动扩展），会经过 PyPI JSON 接口二次校验。
PYPI_MARKET_SEED_PROJECTS: tuple[str, ...] = ()

PYPI_PROJECT_JSON_ENDPOINT = "https://pypi.org/pypi/{project}/json"
PYPI_TIMEOUT_SECONDS = 12.0
PYPI_FETCH_CONCURRENCY = 8
LOCAL_PROJECT_NAME_PATTERN = re.compile(r'^\s*name\s*=\s*"(?P<name>[^"]+)"\s*$', re.MULTILINE)


def _normalize_package_name(package_name: str) -> str:
    """规范化包名，兼容 PyPI 的 `_` 与 `-` 等价规则。"""
    return str(package_name or "").strip().lower().replace("-", "_")


def _match_prefix_tag(package_name: str) -> str | None:
    normalized = _normalize_package_name(package_name)
    for prefix in PYPI_MARKET_PREFIX_TAGS:
        if normalized.startswith(_normalize_package_name(prefix)):
            return prefix
    return None


def _iter_local_pyproject_paths(plugins_dir: Path | None = None) -> list[Path]:
    base_dir = plugins_dir or (Path.cwd() / "plugins")
    if not base_dir.exists() or not base_dir.is_dir():
        return []

    result: list[Path] = []
    for child in base_dir.iterdir():
        if not child.is_dir():
            continue
        pyproject = child / "pyproject.toml"
        if pyproject.exists() and pyproject.is_file():
            result.append(pyproject)

    return result


def _collect_local_project_names(plugins_dir: Path | None = None) -> set[str]:
    names: set[str] = set()
    for pyproject in _iter_local_pyproject_paths(plugins_dir=plugins_dir):
        try:
            text = pyproject.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        matched = LOCAL_PROJECT_NAME_PATTERN.search(text)
        project_name = matched.group("name").strip() if matched else ""
        if project_name:
            names.add(project_name)
    return names


def collect_installed_distribution_names(plugins_dir: Path | None = None) -> set[str]:
    """读取插件专用 site-packages 的 distribution 名。"""
    target_dir = get_pypi_site_packages_dir(plugins_dir)
    if not target_dir.exists():
        return set()

    names: set[str] = set()
    for dist in importlib_metadata.distributions(path=[str(target_dir)]):
        dist_name = str(getattr(dist, "name", "") or "").strip()
        if not dist_name:
            continue
        names.add(_normalize_package_name(dist_name))

    return names


def _build_installed_map(packages: Iterable[str], installed_names: set[str]) -> dict[str, bool]:
    return {
        package: _normalize_package_name(package) in installed_names
        for package in packages
    }


def collect_market_candidate_project_names(plugins_dir: Path | None = None) -> list[str]:
    """收集候选包名（本地插件 + 已安装 + 可选种子），并按前缀过滤。"""
    names: set[str] = set(PYPI_MARKET_SEED_PROJECTS)
    names.update(_collect_local_project_names(plugins_dir=plugins_dir))
    names.update(collect_installed_distribution_names(plugins_dir=plugins_dir))

    filtered = [name for name in names if _match_prefix_tag(name)]
    return sorted(filtered, key=_normalize_package_name)


async def _fetch_project_metadata(
    client: httpx.AsyncClient,
    project_name: str,
) -> dict[str, Any] | None:
    url = PYPI_PROJECT_JSON_ENDPOINT.format(project=quote(project_name, safe=""))
    try:
        response = await client.get(
            url,
            headers={"User-Agent": "AUTO-MAS-PluginMarket/1.0"},
        )
    except Exception as error:
        logger.warning(f"读取 PyPI 项目失败: project={project_name}, error={type(error).__name__}: {error}")
        return None

    if response.status_code == 404:
        return None

    try:
        response.raise_for_status()
        payload = response.json()
    except Exception as error:
        logger.warning(
            f"解析 PyPI 项目 JSON 失败: project={project_name}, error={type(error).__name__}: {error}"
        )
        return None

    if not isinstance(payload, dict):
        return None

    info = payload.get("info")
    if not isinstance(info, dict):
        return None

    package_name = str(info.get("name") or project_name).strip()
    prefix_tag = _match_prefix_tag(package_name)
    if prefix_tag is None:
        return None

    summary = str(info.get("summary") or "").strip()
    version = str(info.get("version") or "").strip()
    project_url = f"https://pypi.org/project/{quote(package_name, safe='')}/"

    return {
        "package": package_name,
        "version": version,
        "summary": summary,
        "project_url": project_url,
        "prefix_tag": prefix_tag,
    }


async def _fetch_market_items_from_candidates(candidates: list[str]) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(PYPI_FETCH_CONCURRENCY)

    async with httpx.AsyncClient(timeout=PYPI_TIMEOUT_SECONDS, follow_redirects=True) as client:
        async def worker(name: str) -> dict[str, Any] | None:
            async with semaphore:
                return await _fetch_project_metadata(client, name)

        results = await asyncio.gather(*(worker(name) for name in candidates), return_exceptions=True)

    dedup: dict[str, dict[str, Any]] = {}
    for result in results:
        if isinstance(result, Exception) or result is None:
            continue
        normalized = _normalize_package_name(result["package"])
        if normalized not in dedup:
            dedup[normalized] = result

    return sorted(dedup.values(), key=lambda x: _normalize_package_name(x["package"]))


async def fetch_market_snapshot(
    plugins_dir: Path | None = None,
    per_prefix_limit: int = 0,
) -> dict[str, Any]:
    """构建插件市场快照。"""
    _ = per_prefix_limit
    candidates = collect_market_candidate_project_names(plugins_dir=plugins_dir)
    items = await _fetch_market_items_from_candidates(candidates)
    installed_names = collect_installed_distribution_names(plugins_dir=plugins_dir)
    installed_map = _build_installed_map((item["package"] for item in items), installed_names)

    return {
        "schema_version": 1,
        "prefix_tags": list(PYPI_MARKET_PREFIX_TAGS),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
        "installed_map": installed_map,
        "total": len(items),
    }
