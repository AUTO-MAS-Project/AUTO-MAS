"""插件市场：索引元数据刷新并写入 ``Config.plugin_catalog``。

优先读取数据站预生成目录，PyPI JSON 与镜像标准元数据作为兜底（不先装包）。
兜底枚举用包名启发缩小扫描面，不以包名前缀作门禁。
"""

from __future__ import annotations

import asyncio
import html
import os
import re
from email.message import Message
from typing import Any
from zipfile import BadZipFile

import httpx

from app.config import config_manager
from app.core.config import Config
from app.models.config import PluginMeta
from app.plugin.runtime.metadata import parse_to_plugin_meta
from app.plugin.uv.ops import candidates
from app.utils import get_logger

from . import catalog, market_index
from .catalog_protocol import ENTRY_FIELDS, package_key

logger = get_logger("插件市场")

_SIMPLE_ANCHOR = re.compile(r">(?P<name>[^<]+)</a>", re.IGNORECASE)
_NAME_HINTS = ("automas", "auto-mas", "auto_mas")
_FETCH_CONCURRENCY = 8
_SIMPLE_TIMEOUT = 45.0
_PYPI = "https://pypi.org"
_CATALOG_URL = "https://data.auto-mas.top/api/v1/files/auto-mas/Client/plugins/download"
_ATTEMPTS = 3


def _norm(name: str) -> str:
    """规范化发行包名称的大小写和分隔符，供市场条目去重与匹配。"""
    return str(name or "").strip().lower().replace("_", "-")


async def refresh() -> None:
    """优先读取数据站完整目录；未配置或读取失败时才扫描 PyPI 与镜像。"""
    url = os.environ.get("AUTO_MAS_PLUGIN_INDEX_URL", _CATALOG_URL).strip()
    if url:
        cache = Config.data_path / "plugin-market-cache.json"
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(5.0), follow_redirects=True, proxy=Config.proxy
            ) as client:
                snapshot = await catalog.fetch_catalog(client, url, cache)
        except (httpx.HTTPError, OSError, ValueError) as error:
            logger.warning(
                f"数据站插件目录不可用，改用发行源检索：{type(error).__name__}"
            )
        else:
            drafts = [
                PluginMeta.build(info=entry) for entry in snapshot.document["plugins"]
            ]
            await _replace_catalog(drafts)
            catalog.store_cache(cache, snapshot)
            logger.info(f"数据站插件目录刷新完成：{len(drafts)} 个插件")
            return
    await _refresh_pypi()


async def _replace_catalog(drafts: list[PluginMeta]) -> None:
    """完整目录校验后原子替换集合，内容相同时保留条目身份与已有 UI 操作目标。"""
    col = Config.plugin_catalog
    drafts = sorted(drafts, key=lambda item: package_key(item.info.package_name))
    current = sorted(col.values(), key=lambda item: package_key(item.info.package_name))
    if [{key: getattr(item.info, key) for key in ENTRY_FIELDS} for item in current] == [
        {key: getattr(item.info, key) for key in ENTRY_FIELDS} for item in drafts
    ]:
        return
    async with config_manager.transaction():
        for uid in list(col.keys()):
            col.remove(uid)
        for draft in drafts:
            col.add(PluginMeta, payload={"info": draft.info.model_dump(mode="python")})
        await col.commit()


async def _refresh_pypi() -> None:
    """从 PyPI 或镜像索引枚举候选，完整读取元数据成功后再替换目录。

    安装镜像仅提供 Simple 下载索引，不要求实现 PyPI 专用的 JSON 元数据接口。
    已知插件读取失败或全部候选读取失败时保留旧目录并报错；未知候选失败记录后跳过。
    404 或有效但非插件的包不入目录。
    写回不做字段白名单、不 ``update`` 旧实例（避开刷新字段限制）。
    """
    col = Config.plugin_catalog
    # 已有目录 + 已装包名作种子（simple 启发扫不到时仍能刷新）
    seed: set[str] = set()
    for meta in col.values():
        text = str(meta.info.package_name or "").strip()
        if text:
            seed.add(_norm(text))
    for record in Config.plugin_registry.values():
        if record.info.is_core:
            continue
        text = str(record.info.package_name or "").strip()
        if text:
            seed.add(_norm(text))

    timeout = httpx.Timeout(_SIMPLE_TIMEOUT)
    proxy = Config.proxy
    mirrors = [url for url in candidates() if url.rstrip("/") != f"{_PYPI}/simple"]

    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=True, proxy=proxy
    ) as client:

        async def list_simple(simple_url: str) -> list[str]:
            """读取包索引的 simple 页面，提取并按规范化名称去重发行包列表。"""
            names: list[str] = []
            seen: set[str] = set()
            for attempt in range(_ATTEMPTS):
                names.clear()
                seen.clear()
                try:
                    async with client.stream(
                        "GET",
                        simple_url,
                        headers={
                            "User-Agent": "AUTO-MAS-PluginMarket/2.0",
                            "Accept": "application/vnd.pypi.simple.v1+html",
                        },
                    ) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            for match in _SIMPLE_ANCHOR.finditer(line):
                                name = html.unescape(match.group("name")).strip()
                                name = name.rstrip("/").split("/")[-1]
                                key = _norm(name)
                                if (
                                    not name
                                    or key in seen
                                    or not any(hint in key for hint in _NAME_HINTS)
                                ):
                                    continue
                                seen.add(key)
                                names.append(name)
                    break
                except httpx.TransportError:
                    if attempt == _ATTEMPTS - 1:
                        raise
                    await asyncio.sleep(0.5 * (attempt + 1))
            return names

        async def fetch_pypi(package: str) -> dict[str, Any] | None:
            """读取官方包元数据，短暂传输失败最多尝试三次，真实下架返回 None。"""
            for attempt in range(_ATTEMPTS):
                try:
                    response = await client.get(
                        f"{_PYPI}/pypi/{package}/json",
                        headers={"User-Agent": "AUTO-MAS-PluginMarket/2.0"},
                    )
                except httpx.TransportError:
                    if attempt == _ATTEMPTS - 1:
                        raise
                    await asyncio.sleep(0.5 * (attempt + 1))
                else:
                    if response.status_code == 404:
                        return None
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data, dict) or not isinstance(
                        data.get("info"), dict
                    ):
                        raise ValueError(f"{package}: PyPI 响应缺少 info 元数据")
                    return data
            return None

        hinted: set[str] = set()
        index_errors: list[Exception] = []
        use_pypi_json = False
        mirror_index_read = False
        # 官方与镜像可能各自缓存旧索引，合并官方及一个可用镜像的候选，不能只取首个成功源。
        for source in [f"{_PYPI}/simple/", *mirrors]:
            try:
                hinted.update(await list_simple(source))
                if source == f"{_PYPI}/simple/":
                    use_pypi_json = True
                else:
                    mirror_index_read = True
                    break
            except (httpx.HTTPError, ValueError) as exc:
                index_errors.append(exc)
                logger.debug(f"市场索引暂不可用：{source}: {type(exc).__name__}")
        if not use_pypi_json and not mirror_index_read:
            index_error = index_errors[-1]
            raise RuntimeError(
                f"插件市场索引读取失败，已保留原目录：{type(index_error).__name__}: "
                f"{str(index_error) or repr(index_error.__cause__)}"
            ) from index_error

        async def fetch_info(package: str) -> dict[str, Any] | Message[Any, Any] | None:
            """官方 JSON 不可用时读取镜像真实发行元数据，不臆造镜像的 JSON API。"""
            error: Exception | None = None
            if use_pypi_json:
                try:
                    payload = await fetch_pypi(package)
                    if payload is not None:
                        return payload
                except (httpx.HTTPError, ValueError) as exc:
                    error = exc
            for simple in mirrors:
                try:
                    metadata = await market_index.fetch_metadata(
                        client, simple, package, proxy=proxy
                    )
                    if metadata is not None:
                        return metadata
                except (httpx.HTTPError, ValueError, BadZipFile, EOFError) as exc:
                    error = exc
            if error is not None:
                raise error
            return None

        pkgs = sorted({*seed, *(_norm(name) for name in hinted)})
        sem = asyncio.Semaphore(_FETCH_CONCURRENCY)
        drafts: dict[str, PluginMeta] = {}

        async def one(name: str) -> None:
            """在并发限制内读取单个发行包，将通过市场声明校验的元数据加入候选结果。"""
            async with sem:
                payload = await fetch_info(name)
            if payload is None:
                return
            draft = parse_to_plugin_meta(payload)
            if draft is None or not draft.info.package_name:
                return
            drafts[_norm(draft.info.package_name)] = draft

        # 收齐结果再关闭客户端，避免一个请求失败时中断其他仍在执行的请求。
        results = await asyncio.gather(
            *[one(name) for name in pkgs], return_exceptions=True
        )
        errors = [
            (name, result)
            for name, result in zip(pkgs, results, strict=True)
            if isinstance(result, BaseException)
        ]
        if errors and (not drafts or any(name in seed for name, _ in errors)):
            error = errors[0][1]
            raise RuntimeError(
                f"插件市场元数据读取失败（{len(errors)} 个包），已保留原目录："
                f"{type(error).__name__}: {str(error) or repr(error.__cause__)}"
            ) from error
        for name, error in errors:
            logger.warning(f"未能识别市场候选 {name}，暂时跳过：{type(error).__name__}")

    # 仅完整读取成功才发布结果；提交失败时由配置事务恢复旧目录。
    await _replace_catalog(list(drafts.values()))
    logger.info(f"插件市场刷新完成：{len(drafts)} 个插件")
