"""读取数据站预生成目录，并缓存已校验文档以支持条件请求。"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.utils import get_logger

from .catalog_protocol import MAX_BYTES, validate_catalog, write_document

logger = get_logger("插件目录")


@dataclass(frozen=True)
class CatalogSnapshot:
    """保存目录来源、条件请求标识和已校验的完整业务文档。"""

    url: str
    etag: str
    document: dict


def _read_cache(path: Path, url: str) -> CatalogSnapshot | None:
    """读取同一公开地址的有效缓存；缓存损坏只失去条件请求优化，不代替网络刷新。"""
    if not path.is_file():
        return None
    try:
        content = path.read_bytes()
        if len(content) > MAX_BYTES + 16384:
            raise ValueError("cached catalog exceeds size limit")
        raw = json.loads(content)
        if not isinstance(raw, dict) or raw.get("url") != url:
            return None
        etag = raw.get("etag")
        if not isinstance(etag, str):
            raise ValueError("invalid cached ETag")
        return CatalogSnapshot(url, etag, validate_catalog(raw.get("document")))
    except (OSError, ValueError) as error:
        logger.debug(f"忽略不可用目录缓存：{type(error).__name__}")
        return None


async def fetch_catalog(
    client: httpx.AsyncClient, url: str, cache: Path
) -> CatalogSnapshot:
    """短时读取并完整校验数据站目录，304 只可复用同来源的有效本地文档。"""
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        raise ValueError("插件目录地址必须是无凭据的 HTTPS URL")
    previous = _read_cache(cache, url)
    headers = {"User-Agent": "AUTO-MAS-PluginMarket/3.0", "Accept": "application/json"}
    if previous is not None and previous.etag:
        headers["If-None-Match"] = previous.etag
    async with client.stream("GET", url, headers=headers) as response:
        if response.status_code == 304:
            if previous is None:
                raise ValueError("数据站返回 304，但没有可用目录缓存")
            return previous
        response.raise_for_status()
        content = bytearray()
        async for part in response.aiter_bytes():
            content.extend(part)
            if len(content) > MAX_BYTES:
                raise ValueError("插件目录超过 8 MB")
        document = validate_catalog(json.loads(content.decode("utf-8-sig")))
        return CatalogSnapshot(url, response.headers.get("ETag", ""), document)


def store_cache(path: Path, snapshot: CatalogSnapshot) -> None:
    """在目录提交成功后原子保存缓存；缓存写入失败不改变已完成刷新的业务结果。"""
    try:
        write_document(path, asdict(snapshot))
    except OSError as error:
        logger.warning(f"插件目录已刷新，缓存未保存：{type(error).__name__}")
