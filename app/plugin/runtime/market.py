"""插件市场：索引元数据刷新并写入 ``Config.plugin_catalog``。

优先读取数据站预生成目录，PyPI JSON 与镜像标准元数据作为兜底（不先装包）。
兜底枚举用包名启发缩小扫描面，不以包名前缀作门禁。
"""

from __future__ import annotations

import asyncio
import html
import os
import re
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
from .catalog_protocol import ENTRY_FIELDS, package_key, validate_entries

logger = get_logger("插件市场")

_SIMPLE_ANCHOR = re.compile(r">(?P<name>[^<]+)</a>", re.IGNORECASE)
_NAME_HINTS = ("automas", "auto-mas", "auto_mas")
_FETCH_CONCURRENCY = 8
_SIMPLE_TIMEOUT = 45.0
_PYPI = "https://pypi.org"
_CATALOG_URL = "https://data.auto-mas.top/api/v1/files/auto-mas/Client/plugins/download"
_ATTEMPTS = 3
# 开发用：刚发到 PyPI 的插件，数据站目录和 PyPI 总索引都可能还没收录。默认不设（不补）；
# 设为逗号分隔的发行包名时，刷新目录逐个读 PyPI 单包元数据补进目录，插件中心才能看到并安装。
_EXTRA_PACKAGES_ENV = "AUTO_MAS_PLUGIN_EXTRA_PACKAGES"


def _extra_packages() -> list[str]:
    """读取需要按包名补进目录的发行包，规范化后去重。"""
    text = os.environ.get(_EXTRA_PACKAGES_ENV, "")
    return list(
        dict.fromkeys(package_key(item) for item in text.split(",") if item.strip())
    )


async def _extra_drafts(present: set[str]) -> list[PluginMeta]:
    """按包名从 PyPI 读取目录里还没有的插件；读不到只记日志，不影响本次刷新。"""
    names = [name for name in _extra_packages() if name not in present]
    if not names:
        return []
    drafts: list[PluginMeta] = []
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(15.0), follow_redirects=True, proxy=Config.proxy
    ) as client:
        for name in names:
            try:
                response = await client.get(
                    f"{_PYPI}/pypi/{name}/json",
                    headers={"User-Agent": "AUTO-MAS-PluginMarket/2.0"},
                )
                response.raise_for_status()
                draft = parse_to_plugin_meta(response.json())
            except (httpx.HTTPError, ValueError) as error:
                logger.warning(f"按包名补充插件目录失败：{name}: {error}")
                continue
            if draft is None:
                logger.warning(f"按包名补充插件目录跳过：{name} 不是插件发行包")
                continue
            drafts.append(draft)
    if drafts:
        logger.info(
            f"按包名从 PyPI 补充插件目录：{', '.join(d.info.package_name for d in drafts)}"
        )
    return drafts


async def refresh() -> None:
    """依次读取数据站、官方源和镜像源，首个完整结果作为本次目录的唯一依据。"""
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
            drafts += await _extra_drafts(
                {package_key(item.info.package_name) for item in drafts}
            )
            await _replace_catalog(drafts)
            catalog.store_cache(cache, snapshot)
            logger.info(f"数据站插件目录刷新完成：{len(drafts)} 个插件")
            return
    await _refresh_pypi()


def _install_target(meta: PluginMeta) -> tuple[str, str, str]:
    """以发行包、插件和版本绑定安装入口，展示元数据变更不影响安装交接。"""
    info = meta.info
    return package_key(info.package_name), info.plugin_name, info.version


async def _replace_catalog(drafts: list[PluginMeta]) -> None:
    """原子同步完整目录，保留相同安装目标的 UID。"""
    col = Config.plugin_catalog
    async with config_manager.transaction():
        current = {_install_target(item): item for item in col.values()}
        order = []
        for draft in sorted(drafts, key=_install_target):
            entry = current.get(_install_target(draft))
            info = draft.info.model_dump(mode="python", include=ENTRY_FIELDS)
            if entry is None:
                order.append(col.add(PluginMeta, payload={"info": info}))
                continue
            if entry.info.model_dump(mode="python", include=ENTRY_FIELDS) != info:
                await entry.update(draft, check_visibility=False)
            order.append(entry.uid)

        previous_order = list(col.keys())
        if order != previous_order:
            retained = set(order)
            for uid in previous_order:
                if uid not in retained:
                    col.remove(uid)
            col.set_order(order)
            await col.commit()


async def _refresh_pypi() -> None:
    """逐级读取官方源及候选镜像，任一候选读取失败便放弃本级结果。

    总索引只补充新包名；失败后仍独立查询已知包。全部来源失败才保留旧目录，
    首个查询完整的来源直接替换目录，包括空结果，不与其他来源或旧版本混合。
    """
    col = Config.plugin_catalog
    # 已有目录 + 已装包名作种子（simple 启发扫不到时仍能刷新）
    seed: set[str] = set()
    for meta in col.values():
        text = str(meta.info.package_name or "").strip()
        if text:
            seed.add(package_key(text))
    for record in Config.plugin_registry.values():
        if record.info.is_core:
            continue
        text = str(record.info.package_name or "").strip()
        if text:
            seed.add(package_key(text))
    seed.update(_extra_packages())

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
                                key = package_key(name)
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
                    if package_key(str(data["info"].get("name", ""))) != package:
                        raise ValueError(f"{package}: PyPI 返回的发行包身份不一致")
                    return data
            return None

        last_error: Exception | None = None
        for source in [f"{_PYPI}/simple/", *mirrors]:
            try:
                try:
                    hinted = await list_simple(source)
                except (httpx.HTTPError, ValueError) as error:
                    # 发现新包失败不等于单包接口失效；无已知候选时才无法继续本级查询。
                    logger.debug(f"市场索引暂不可用：{source}: {type(error).__name__}")
                    if not seed:
                        raise
                    hinted = []
                names = sorted(seed | {package_key(name) for name in hinted})
                sem = asyncio.Semaphore(_FETCH_CONCURRENCY)

                async def one(name: str) -> PluginMeta | None:
                    """仅从本级来源读取候选元数据，明确不存在或不符合市场门禁的包不入目录。"""
                    async with sem:
                        payload = (
                            await fetch_pypi(name)
                            if source == f"{_PYPI}/simple/"
                            else await market_index.fetch_metadata(
                                client, source, name, proxy=proxy
                            )
                        )
                    if payload is None:
                        return None
                    return parse_to_plugin_meta(payload)

                # 收齐本级结果再切源，避免遗留请求或复用较高优先级来源的半份目录。
                results = await asyncio.gather(
                    *(one(name) for name in names), return_exceptions=True
                )
                drafts: list[PluginMeta] = []
                for result in results:
                    if isinstance(result, BaseException):
                        raise result
                    if result is not None:
                        drafts.append(result)
                validate_entries(
                    [
                        {key: getattr(item.info, key) for key in ENTRY_FIELDS}
                        for item in drafts
                    ]
                )
            except (
                httpx.HTTPError,
                ValueError,
                BadZipFile,
                EOFError,
                OSError,
            ) as error:
                last_error = error
                logger.warning(
                    f"市场来源读取未完成，尝试下一来源：{source}: {type(error).__name__}"
                )
                continue

            # 来源读取与提交分开：提交失败直接上抛，不能伪装成来源不可用再覆盖一次。
            await _replace_catalog(drafts)
            logger.info(f"插件市场刷新完成：{len(drafts)} 个插件，来源：{source}")
            return

    raise RuntimeError(
        f"插件市场全部来源读取失败，已保留原目录：{last_error}"
    ) from last_error
