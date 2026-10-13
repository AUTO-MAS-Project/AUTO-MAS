"""插件市场：索引元数据刷新并写入 ``Config.plugin_catalog``。

只信索引 JSON（不先装包）；门禁与展示 i18n 由 ``parse_to_plugin_meta`` 判定。
候选枚举用包名启发缩小扫描面，**不以包名前缀作门禁**。
"""

from __future__ import annotations

import asyncio
import html
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.core.config import Config
from app.models.config import PluginMeta
from app.plugin.runtime.metadata import parse_to_plugin_meta
from app.plugin.uv.ops import candidates, mark_ok
from app.utils import get_logger

logger = get_logger("插件市场")

_SIMPLE_ANCHOR = re.compile(r">(?P<name>[^<]+)</a>", re.IGNORECASE)
_NAME_HINTS = ("automas", "auto-mas", "auto_mas")
_FETCH_CONCURRENCY = 8
_SIMPLE_TIMEOUT = 45.0


def _norm(name: str) -> str:
    return str(name or "").strip().lower().replace("_", "-")


async def refresh() -> None:
    """全量刷新：枚举候选 → 解析 PluginMeta → 整表删光再 add。

    整次枚举在拿到可写结果前失败则上抛，**不改**已有 catalog；单包失败跳过。
    写回不做字段白名单、不 ``update`` 旧实例（避开刷新字段限制）。
    """
    col = Config.plugin_catalog
    # 已有目录 + 已装包名作种子（simple 启发扫不到时仍能刷新）
    seed: dict[str, str] = {}
    for meta in col.values():
        text = str(meta.info.package_name or "").strip()
        if text:
            seed.setdefault(_norm(text), text)
    for record in Config.plugin_registry.values():
        text = str(record.info.package_name or "").strip()
        if text:
            seed.setdefault(_norm(text), text)

    mirror_list = candidates()
    timeout = httpx.Timeout(_SIMPLE_TIMEOUT)

    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=True, proxy=Config.proxy
    ) as client:

        async def list_simple(simple_url: str) -> list[str]:
            names: list[str] = []
            seen: set[str] = set()
            async with client.stream(
                "GET",
                simple_url,
                headers={"User-Agent": "AUTO-MAS-PluginMarket/2.0"},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    match = _SIMPLE_ANCHOR.search(line)
                    if not match:
                        continue
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
            return names

        async def fetch_info(package: str) -> dict[str, Any] | None:
            last_err = ""
            for mirror in mirror_list:
                parsed = urlparse(mirror.rstrip("/") + "/")
                path = parsed.path.rstrip("/")
                root = f"{parsed.scheme}://{parsed.netloc}"
                url = (
                    f"{root}/pypi/{package}/json"
                    if path.endswith("/simple")
                    else urljoin(f"{root}/", f"pypi/{package}/json")
                )
                try:
                    response = await client.get(
                        url, headers={"User-Agent": "AUTO-MAS-PluginMarket/2.0"}
                    )
                    if response.status_code != 200:
                        last_err = f"{url} → {response.status_code}"
                        continue
                    data = response.json()
                    if isinstance(data, dict) and isinstance(data.get("info"), dict):
                        await mark_ok(mirror)
                        return data
                    last_err = f"{url} 非 JSON info"
                except Exception as exc:
                    last_err = f"{url}: {exc}"
            logger.debug(f"市场 JSON 元数据失败: {package}: {last_err}")
            return None

        # ── Simple 枚举（首选失败则换镜像）──
        hinted: list[str] = []
        last_exc: Exception | None = None
        for mirror in mirror_list:
            try:
                hinted = await list_simple(mirror)
                await mark_ok(mirror)
                break
            except Exception as exc:
                last_exc = exc
                hinted = []
        if not hinted and not seed:
            raise last_exc or RuntimeError("无法读取 PyPI simple 索引")

        pkgs = sorted({*seed.values(), *hinted}, key=str.lower)
        sem = asyncio.Semaphore(_FETCH_CONCURRENCY)
        drafts: dict[str, PluginMeta] = {}

        async def one(name: str) -> None:
            async with sem:
                payload = await fetch_info(name)
            if payload is None:
                return
            draft = parse_to_plugin_meta(payload)
            if draft is None or not draft.info.package_name:
                return
            drafts[_norm(draft.info.package_name)] = draft

        await asyncio.gather(*[one(name) for name in pkgs])

    # ── 成功得到结果集后再改配置：删光 → 按包名排序 add（空集则仅清空）──
    for uid in list(col.keys()):
        col.remove(uid)
    for draft in sorted(
        drafts.values(), key=lambda item: _norm(item.info.package_name)
    ):
        col.add(
            PluginMeta,
            payload={"info": draft.info.model_dump(mode="python")},
        )
    await col.commit()
