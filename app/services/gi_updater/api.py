#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""HYP Connect 与 Sophon 端点访问：客户端由调用方注入，响应按处收敛。

只认四件事：

    getGameBranches   主分支与预下载分支的 package_id / password / tag
    getBuild          目标版本主清单与数据块基址（只收 GET）
    getPatchBuild     差分清单位置（只收 POST，且分片基址取它自己的 diff_download）
    清单与数据块       直接按地址取字节

响应不建模型、就地窄取值：官方在同一个字段上会给数字也会给字符串，缺项与形态变化都
只落在用到的那一条路径上，逐处收敛能把「协议变了」的影响面压到最小。
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from app.services.gi_updater.common import UpdaterError
from app.services.gi_updater.presets import PresetConfig
from app.services.gi_updater.sophon import MAIN_MATCHING_FIELD, decompress

__all__ = [
    "ManifestRef",
    "PackageInfo",
    "blob_url",
    "fetch_branches",
    "fetch_main_manifest_refs",
    "fetch_manifest_bytes",
    "fetch_patch_manifest_refs",
    "fetch_range",
    "mask_url_password",
    "new_client",
    "request_bytes",
    "request_json",
    "stream_range_to",
]

#: 元数据接口的单次超时（秒）
DEFAULT_TIMEOUT = 30.0
#: 单个数据块：体积远大于清单，但不能让用户干等
_CHUNK_TIMEOUT = 120.0
#: 整份清单：条目多、体积大，走的是慢速 CDN
_MANIFEST_TIMEOUT = 300.0

DEFAULT_USER_AGENT = "HYPContainer/1.16.1.361 (windows 11) collapse-python-updater/1.0"

_PASSWORD_QUERY_RE = re.compile(r"(?i)([?&]password=)[^&]*")


def mask_url_password(url: str) -> str:
    """把地址里的 ``password=`` 换成 ``***``，供日志与异常文本使用。

    分支密码是启动器内置的公开常量、不是用户凭据；打码只为免得每次排障都满屏回显。
    """
    return _PASSWORD_QUERY_RE.sub(r"\1***", url)


def new_client() -> httpx.AsyncClient:
    """新建一个本次流程用完即关的异步客户端。"""
    return httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": DEFAULT_USER_AGENT},
    )


# --------------------------------------------------------------------------- #
# 传输
# --------------------------------------------------------------------------- #


async def request_json(
    client: httpx.AsyncClient, url: str, *, method: str = "GET"
) -> dict:
    """发一次请求并检查官方响应包封。

    Raises:
        UpdaterError: 网络失败、非 200、响应不是 JSON 对象、或 ``retcode`` 非 0。
    """
    try:
        response = await client.request(method, url)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as error:
        raise UpdaterError(
            f"{method} 请求失败 {mask_url_password(url)}: {error}"
        ) from error
    except ValueError as error:
        raise UpdaterError(f"响应不是合法 JSON: {mask_url_password(url)}") from error

    if not isinstance(payload, dict):
        # 包封按对象解析；数组与标量都说明协议变了，不让它变成下游的 AttributeError
        raise UpdaterError(f"响应不是 JSON 对象: {mask_url_password(url)}")
    retcode = payload.get("retcode")
    # 同一个字段会给数字也会给文字，两种都按 0 放行；没给这个字段也放行
    if retcode is not None and str(retcode) != "0":
        raise UpdaterError(
            f"接口返回 retcode={retcode} message={payload.get('message')!r}: "
            f"{mask_url_password(url)}"
        )
    return payload


def data_mapping(payload: dict) -> dict:
    """取响应里的 ``data`` 映射；缺失时为空字典，形态不对即报错。"""
    data = payload.get("data")
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise UpdaterError(f"响应 data 不是对象: {type(data).__name__}")
    return data


async def request_bytes(
    client: httpx.AsyncClient, url: str, *, timeout: float | None = None
) -> bytes:
    """取一份原始字节（清单与整份重建用的数据块）。

    ``timeout`` 指「连续多久没有字节到达」的上限，不是整个下载的时限。

    Note:
        留空时**不能**把这个参数原样传下去：网络库把显式的空值理解成「关闭全部超时」，
        连客户端默认那一档也一起抹掉，卡死的连接就再也等不出结果。没指定就不传，让它
        沿用客户端默认。

    Raises:
        UpdaterError: 网络失败或非 200。
    """
    options: dict[str, Any] = {} if timeout is None else {"timeout": timeout}
    try:
        response = await client.get(url, **options)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise UpdaterError(f"下载失败 {url}: {error}") from error
    return response.content


async def fetch_range(
    client: httpx.AsyncClient, url: str, offset: int, length: int
) -> bytes:
    """按 Range 取一段数据。

    取回的就是原样内容，不再解压：差分分片段是 ldiff 数据，CopyOver 段是完整新文件。
    整段落在内存里，所以几百 MiB 的那几档要走 :func:`stream_range_to`。

    Raises:
        UpdaterError: 网络失败，或回来的长度不等于要的 ``length``（CDN 忽略 Range 时
            会整份回，那种情况下游会拿错内容）。
    """
    if length <= 0:
        # 空文件在清单里是真会出现的；拼出 bytes=N-(N-1) 是个非法请求头
        return b""
    headers = {"Range": f"bytes={offset}-{offset + length - 1}"}
    try:
        response = await client.get(url, headers=headers, timeout=_CHUNK_TIMEOUT)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise UpdaterError(f"取分片失败 {url}: {error}") from error
    data = response.content
    if len(data) != length:
        raise UpdaterError(f"分片长度不符 {url}: 期望 {length} 实际 {len(data)}")
    return data


#: 流式落盘的攒块大小：每攒够这么多字节才回一次主循环之外的写
_STREAM_FLUSH_BYTES = 1 << 20


async def stream_range_to(
    client: httpx.AsyncClient,
    url: str,
    offset: int,
    length: int,
    path: str,
    *,
    on_bytes: Callable[[int], None] | None = None,
) -> int:
    """按 Range 把一段数据**流式**写进 ``path``，返回收到的字节数。

    与 :func:`fetch_range` 的差别只在内存：整段不攒在内存里，几百 MiB 的文件几路并发同时
    下也不会把驻留量抬到数 GiB。解压与校验由调用方在写完之后用工作线程做。

    ``on_bytes`` 每攒够一块就报一次网上到达的字节数，供上层的心跳行取用（一批文件要
    几分钟才全部完成，界面需要更密的动静）。

    Raises:
        UpdaterError: 网络失败、非 200，或回来的长度不等于要的 ``length``（口径与
            :func:`fetch_range` 一致）。
    """
    headers = {"Range": f"bytes={offset}-{offset + length - 1}"}
    received = 0
    buffer = bytearray()
    try:
        with open(path, "wb") as handle:
            async with client.stream(
                "GET", url, headers=headers, timeout=_CHUNK_TIMEOUT
            ) as response:
                response.raise_for_status()
                async for block in response.aiter_bytes():
                    buffer += block
                    if len(buffer) >= _STREAM_FLUSH_BYTES:
                        await asyncio.to_thread(_write_all, handle, bytes(buffer))
                        received += len(buffer)
                        if on_bytes is not None:
                            on_bytes(len(buffer))
                        buffer.clear()
            if buffer:
                await asyncio.to_thread(_write_all, handle, bytes(buffer))
                received += len(buffer)
                if on_bytes is not None:
                    on_bytes(len(buffer))
    except httpx.HTTPError as error:
        raise UpdaterError(f"取分片失败 {url}: {error}") from error
    if received != length:
        raise UpdaterError(f"分片长度不符 {url}: 期望 {length} 实际 {received}")
    return received


def _write_all(handle, data: bytes) -> None:  # noqa: ANN001
    """把一块数据写进已打开的文件（在线程里跑，主循环不碰磁盘）。"""
    handle.write(data)


def blob_url(prefix: str, name: str) -> str:
    """按接口给的基址拼一个清单或数据块的地址。"""
    return f"{prefix.rstrip('/')}/{name}"


# --------------------------------------------------------------------------- #
# 窄取值：一处一个形状，取不到就当场说清楚是哪一处
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PackageInfo:
    """一个分支（主 / 预下载）定位一次 getBuild 所需的三元组。"""

    package_id: str
    password: str
    tag: str


def _package_info(branch: Any, preset: PresetConfig) -> PackageInfo:
    """把 ``getGameBranches`` 的分支条目收敛成 :class:`PackageInfo`。

    Raises:
        UpdaterError: 缺 ``package_id`` 或 ``password``——没有这两样问不到清单。
    """
    package_id = str(branch.get("package_id") or "")
    password = str(branch.get("password") or "")
    if not package_id or not password:
        raise UpdaterError(f"{preset.profile_name}：分支条目缺少 package_id/password")
    return PackageInfo(
        package_id=package_id, password=password, tag=str(branch.get("tag") or "")
    )


def _find_branch_entry(entries: Any, preset: PresetConfig) -> dict:
    """在 ``game_branches[]`` 里挑出本预设那一款。

    一个 launcher 分组下挂着多款游戏，URL 上的 ``game_ids[]`` 只是请服务端少发几条，最终
    仍以本地比对为准。先按 ``game_id`` 精确命中：同一 biz 可能占多条不同 id，只比 biz 会
    挑到别的发行版。

    Raises:
        UpdaterError: 一款都对不上。此时宁可按「问不出」放行，也不能拿别款游戏的
            ``package_id`` 继续算计划——``getBuild`` 会照样返回那份清单，往下就是往这个
            客户端目录里写别人的文件。
    """
    by_biz = None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        game = entry.get("game")
        if not isinstance(game, dict):
            continue
        if preset.game_id and str(game.get("id") or "") == preset.game_id:
            return entry
        if (
            by_biz is None
            and preset.launcher_biz_name
            and str(game.get("biz") or "") == preset.launcher_biz_name
        ):
            by_biz = entry
    if by_biz is not None:
        return by_biz
    raise UpdaterError(f"{preset.profile_name}：分支响应里没有这款游戏的条目")


async def fetch_branches(
    client: httpx.AsyncClient, preset: PresetConfig
) -> tuple[PackageInfo, PackageInfo | None]:
    """取主分支与预下载分支。

    Returns:
        ``(主分支, 预下载分支或 None)``。

    Raises:
        UpdaterError: 接口异常、响应里没有这款游戏的分支、或主分支缺字段。
    """
    payload = await request_json(client, preset.game_branches_url)
    entries = data_mapping(payload).get("game_branches") or []
    if not entries:
        raise UpdaterError(f"{preset.profile_name}：getGameBranches 没有返回分支")
    entry = _find_branch_entry(entries, preset)
    main = entry.get("main")
    if not isinstance(main, dict):
        raise UpdaterError(f"{preset.profile_name}：分支里没有 main")
    # 预下载只在这同一款游戏的条目里找，不跨条目兜底
    preload = entry.get("pre_download")
    return (
        _package_info(main, preset),
        _package_info(preload, preset) if isinstance(preload, dict) else None,
    )


@dataclass(frozen=True)
class ManifestRef:
    """一份清单的位置，以及它配套数据块的基址。"""

    manifest_id: str
    manifest_url_prefix: str
    manifest_compressed: bool
    chunk_url_prefix: str
    chunk_compressed: bool


def _index_entries(payload: dict) -> dict[str, dict]:
    """把一个清单响应里的 ``manifests[]`` 按 ``matching_field`` 归成表。

    一次 ``getBuild`` / ``getPatchBuild`` 会并列返回主资源与每档语音的清单条目，各自带着
    自己的 ``category_id`` 与两处下载基址，所以两类接口都各请求一次就够，不必按类别反复问。
    """
    indexed: dict[str, dict] = {}
    for entry in data_mapping(payload).get("manifests") or []:
        if isinstance(entry, dict) and entry.get("matching_field"):
            indexed[str(entry["matching_field"]).casefold()] = entry
    return indexed


async def fetch_main_manifest_refs(
    client: httpx.AsyncClient, preset: PresetConfig, package: PackageInfo
) -> dict[str, ManifestRef]:
    """取目标版本各类资源的主清单位置（只收 GET）。

    Returns:
        ``matching_field``（小写）-> 清单位置；至少应含 ``game``。

    Raises:
        UpdaterError: 接口异常，或响应里没有 ``game`` 清单。
    """
    urls = preset.launcher_resource_chunks_url
    payload = await request_json(
        client, f"{urls.main_url}{_query(preset, package, with_tag=True)}"
    )
    entries = _index_entries(payload)
    if MAIN_MATCHING_FIELD not in entries:
        raise UpdaterError(
            f"{preset.profile_name}：主清单里没有 matching_field=game 的条目"
        )
    return {
        field: _manifest_ref(entry, from_diff=False) for field, entry in entries.items()
    }


async def fetch_patch_manifest_refs(
    client: httpx.AsyncClient, preset: PresetConfig, package: PackageInfo, baseline: str
) -> dict[str, ManifestRef]:
    """取各类资源的差分清单位置（只收 POST）。

    只登记「本机基线在它的 ``stats`` 里有键」的那几类：官方没给这个基线的差分（响应里没有
    该条目，或 ``stats`` 里没有这个基线键）时，这一类直接不入选，由调用方决定退回全量比对
    还是本轮不动。

    Raises:
        UpdaterError: 接口异常，或某类条目读不出地址。
    """
    urls = preset.launcher_resource_chunks_url
    payload = await request_json(
        client,
        f"{urls.patch_url}{_query(preset, package, with_tag=False)}",
        method="POST",
    )
    refs: dict[str, ManifestRef] = {}
    for field, entry in _index_entries(payload).items():
        # 基线版本不在查询串上：每份差分清单的 stats 直接以基线版本为键
        baselines = entry.get("stats") or {}
        if any(str(tag).casefold() == baseline.casefold() for tag in baselines):
            refs[field] = _manifest_ref(entry, from_diff=True)
    return refs


def _manifest_ref(entry: dict, *, from_diff: bool) -> ManifestRef:
    """把一个清单条目收敛成 :class:`ManifestRef`。
    Raises:
        UpdaterError: 缺清单 id 或任一基址。
    """
    manifest = entry.get("manifest") or {}
    download = entry.get("manifest_download") or {}
    chunks = (
        entry.get("diff_download") if from_diff else entry.get("chunk_download")
    ) or {}
    ref = ManifestRef(
        manifest_id=str(manifest.get("id") or ""),
        manifest_url_prefix=str(download.get("url_prefix") or ""),
        manifest_compressed=bool(download.get("compression")),
        chunk_url_prefix=str(chunks.get("url_prefix") or ""),
        chunk_compressed=bool(chunks.get("compression")),
    )
    if not ref.manifest_id or not ref.manifest_url_prefix or not ref.chunk_url_prefix:
        raise UpdaterError("清单条目缺少清单 id 或下载地址")
    return ref


def _query(preset: PresetConfig, package: PackageInfo, *, with_tag: bool) -> str:
    """拼 getBuild 系端点的查询串；两个端点同形，差分不带 ``tag``。"""
    url = (
        f"?plat_app={preset.launcher_biz_name}&branch=main"
        f"&password={package.password}&package_id={package.package_id}"
    )
    # tag 只用接口原样返回的串，形态上的讲究见 GameVersion.sophon_tag
    return f"{url}&tag={package.tag}" if with_tag and package.tag else url


async def fetch_manifest_bytes(client: httpx.AsyncClient, ref: ManifestRef) -> bytes:
    """下载并解压一份清单，返回 protobuf 字节。"""
    raw = await request_bytes(
        client,
        blob_url(ref.manifest_url_prefix, ref.manifest_id),
        timeout=_MANIFEST_TIMEOUT,
    )
    return decompress(raw) if ref.manifest_compressed else raw
