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

"""差分清单与目标清单的合并，以及单个文件的取回与落盘。

    差分清单点名的文件
        ├─ 没有 original_file_name → 分片本身就是新内容（CopyOver）
        └─ 有 original_file_name  → 分片是 ldiff 数据，打到旧文件上（Patch）
                                        └─ 旧文件不可用 / 打补丁失败
                                             → 按主清单整文件重建（降级）

降级判据是「拿这份基线打不出可信的新文件」：米哈游的现网差分不支持从空文件重建，旧文件
缺了、尺寸变了、内容被改过，硬打要么直接失败、要么产出一个校验不过的坏文件。与其让一个
文件卡住整轮更新，不如把这个文件按主清单整份重下——多花的流量只落在这一个文件上。

单个文件一律先写到同目录的 ``<name>.mas-new``，校验通过再 ``os.replace`` 原子改名；中途
失败时原文件保持原样。
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence, Tuple

from app.services.gi_updater.api import request_bytes, stream_range_to
from app.services.gi_updater.common import UpdaterError, get_logger, safe_join
from app.services.gi_updater.sophon import (
    MAIN_MATCHING_FIELD,
    SophonAssetChunk,
    SophonAssetProperty,
    SophonPatchProto,
    decompress,
    inflate_file,
)

__all__ = [
    "METHOD_COPYOVER",
    "METHOD_PATCH",
    "AssetSummary",
    "BlobUrls",
    "PatchAsset",
    "apply_asset",
    "build_patch_assets",
    "md5_file",
    "remove_unused",
    "summarize_assets",
]

#: 分片本身就是新内容
METHOD_COPYOVER = "copyover"
#: 分片是 ldiff 数据，要打到旧文件上
METHOD_PATCH = "patch"

#: hpatchz 的等待预算：起步 60 秒，再按目标体积每秒 1 MiB 追加
_HPATCHZ_MIN_SECONDS = 60
_HPATCHZ_MIN_BYTES_PER_SECOND = 1 << 20


def _hpatchz_timeout(target_size: int) -> float:
    """这个文件打补丁最多等多久。

    每秒 1 MiB 是比真机慢一到两个数量级的保守估计，正常跑不会提前掐表；留着上限只为工具
    真挂住时仍能收工——掐早了要把整个文件重下一遍，已经花掉的差分片段白下，比多等一会儿
    贵得多。
    """
    return _HPATCHZ_MIN_SECONDS + target_size / _HPATCHZ_MIN_BYTES_PER_SECOND


@dataclass(frozen=True)
class BlobUrls:
    """一类资源取数据用到的两处基址。

    差分分片只能从**差分档案自己**的基址取，主包数据块只能从主清单的基址取；两边互不
    含对方的内容，取错边就是每个都 404。主资源与每一档语音各有自己的一对基址。
    """

    diff_prefix: str
    diff_compressed: bool
    main_prefix: str
    main_compressed: bool


@dataclass(frozen=True)
class PatchAsset:
    """一个文件本轮怎么处理。"""

    name: str
    target_size: int
    target_md5: str
    method: str
    #: 差分档案里的分片名：一个 blob 供许多文件共用，所以要带偏移取一段
    patch_name: str
    patch_offset: int
    patch_length: int
    #: 补丁源文件；CopyOver 时为空串
    original_name: str
    original_size: int
    original_md5: str
    #: 这一条属于哪一类资源（主资源或某个语音类别），报明细与判语音是否装过时要用
    category: str
    #: 取这一条数据要用的基址；不同类别的基址互不相同，所以挂在文件上而不是计划上
    urls: BlobUrls
    #: 主清单里该文件的全部数据块，整文件重建（降级）时用
    chunks: Tuple[SophonAssetChunk, ...] = ()

    @property
    def is_patch(self) -> bool:
        """是否走 hpatchz 打补丁（否则分片即新内容）。"""
        return self.method == METHOD_PATCH

    @property
    def is_voice(self) -> bool:
        """这一条是否属于语音包（主资源之外的类别）。"""
        return self.category != MAIN_MATCHING_FIELD


# --------------------------------------------------------------------------- #
# 清单合并
# --------------------------------------------------------------------------- #


def _pick_info(asset_property: Any, baseline: str) -> Any:
    """在差分条目里挑出本机基线对应的那份分片信息。

    差分清单为每个基线版本都存了一份；拿错基线会把别的版本的分片当成本次要下的量。
    """
    wanted = baseline.casefold()
    for info in asset_property.asset_infos:
        if info.version_tag.casefold() == wanted:
            return info
    return None


def build_patch_assets(
    patch_manifest: SophonPatchProto,
    target_assets: Sequence[SophonAssetProperty],
    baseline: str,
    category: str,
    urls: BlobUrls,
    protected: Sequence[str] = (),
) -> Tuple[List[PatchAsset], List[str]]:
    """把一类资源的差分清单与目标清单合并成待处理明细，并收集待删文件。

    以差分清单点名的文件为准，目标清单里未被点名的本轮不动。

    Args:
        category: 这一批属于哪一类资源（``game`` 或某个语音类别）。
        urls: 这一类资源自己的两处基址，跟着每条明细走。
        protected: 清单要求删除也必须留下的文件名，由安装层按这款游戏预设给。

    Raises:
        UpdaterError: 差分清单给本基线登了条目却没有分片坐标——照它下载会取到别处的内容，
            宁可停手。

    Note:
        差分清单点的是**目标版本的全部文件**，但只有「相对本基线确实要动」的那些才带上基线
        条目；条目为空就是「相对本基线没变」，既不下载也不写任何东西。把它们当成缺分片而
        停手，等于每一次真实更新都算不出计划；当成要整份重下，则会把一次增量放大成整个
        客户端的全量。
    """
    target_index = {
        asset.asset_name: asset for asset in target_assets if not asset.is_directory
    }
    assets: List[PatchAsset] = []

    for entry in patch_manifest.patch_assets:
        name = str(entry.asset_name)
        target = target_index.get(name)
        if target is None:
            # 差分点名但目标清单没有：文件被淘汰，交给待删清单处理
            continue
        info = _pick_info(entry, baseline)
        if info is None:
            continue
        if not info.chunks:
            raise UpdaterError(f"差分清单里 {name} 的基线 {baseline} 有条目却没有分片")
        chunk = info.chunks[0]
        assets.append(
            PatchAsset(
                name=name,
                target_size=target.asset_size,
                target_md5=target.asset_hash_md5,
                method=METHOD_PATCH if chunk.original_file_name else METHOD_COPYOVER,
                patch_name=chunk.patch_name,
                # 要下的长度是 PatchLength：PatchSize 是整个 blob 的大小，多个文件共用
                # 同一 blob，按文件累加会重复计数。CopyOver 时 PatchLength 就等于新文件
                # 的完整大小。
                patch_offset=chunk.patch_offset,
                patch_length=chunk.patch_length,
                original_name=chunk.original_file_name,
                original_size=chunk.original_file_length,
                original_md5=chunk.original_file_md5,
                category=category,
                urls=urls,
                chunks=tuple(target.asset_chunks),
            )
        )

    return assets, collect_removals(patch_manifest, set(target_index), set(protected))


def collect_removals(
    patch_manifest: SophonPatchProto, in_target: set, protected: set
) -> List[str]:
    """收集要删除的旧文件；目标清单里仍在用的必须留下。

    ``unused_assets`` 列的是「从某个基线升上来后不再被引用」的文件，跨基线混在一起，不能
    照单全删。比对大小写不敏感：Windows 上同一文件的大小写漂移不该被当成两个。
    """
    forbidden = {name.casefold() for name in protected}
    known = {name.casefold() for name in in_target}
    logger = get_logger()
    removed: List[str] = []
    for unused in patch_manifest.unused_assets:
        for info in unused.asset_infos:
            for item in info.assets:
                name = str(item.file_name)
                if not name or name.casefold() in known:
                    continue
                if (
                    "/" not in name
                    and "\\" not in name
                    and name.casefold() in forbidden
                ):
                    logger.warning("清单要求删除受保护的文件，已跳过: %s", name)
                    continue
                removed.append(name)
    return sorted(set(removed))


@dataclass(frozen=True)
class AssetSummary:
    """一轮更新的体量统计（磁盘门禁与进度分母都用它）。"""

    file_count: int = 0
    #: 本轮要从网络取的字节数：按分片段长度计；判为会降级的文件按整文件计
    download_size: int = 0
    patch_count: int = 0
    copyover_count: int = 0
    #: 单个文件更新后的最大体积——落盘峰值按它预留
    largest_target: int = 0
    #: 基线已不可用、预计要走整文件重下的文件数
    downgraded: int = 0
    #: 体积已与目标一致、预计不必下载的文件数（续传时给个人数感觉）
    ready: int = 0
    #: 其中属于语音包的文件数与要下的量（报明细用，让用户知道多出来的是语音）
    voice_count: int = 0
    voice_download: int = 0


def _stat_size(path: str) -> int:
    """读一个文件的大小；不存在时返回 ``-1``。"""
    try:
        return os.path.getsize(path)
    except OSError:
        return -1


#: 一个文件本轮的预判结论
_VERDICT_READY = "ready"  #: 目标尺寸已对上，本轮会被复核跳过
_VERDICT_FULL = "full"  #: 基线打不出补丁，预计按整文件重建
_VERDICT_DIFF = "diff"  #: 照差分取那一段


async def summarize_assets(
    assets: Sequence[PatchAsset], game_path: str
) -> AssetSummary:
    """把待处理明细压成体量统计。

    每个文件只看一次 ``getsize`` 序列，得出**一个**结论（按优先级）：

    :data:`_VERDICT_READY`
        目标文件的尺寸已经对上 —— 本轮会被 :func:`apply_asset` 的复核跳过，不计流量；
    :data:`_VERDICT_FULL`
        不是 ready、是补丁类、且基线文件的尺寸对不上 —— 预计打不出补丁，按整文件重建；
    :data:`_VERDICT_DIFF`
        其余 —— 照差分取那一段。

    一个文件只出一个结论：内容已经是本轮要的文件只计就绪，不会同时又被算成待下载。
    """

    def inspect(asset: PatchAsset) -> Tuple[str, int]:
        """给出这一个文件的结论与要从网络取的字节数。"""
        if _stat_size(safe_join(game_path, asset.name)) == asset.target_size:
            return _VERDICT_READY, 0
        if asset.is_patch and (
            _stat_size(safe_join(game_path, asset.original_name)) != asset.original_size
        ):
            return _VERDICT_FULL, asset.target_size
        return _VERDICT_DIFF, asset.patch_length

    verdicts = await asyncio.gather(
        *(asyncio.to_thread(inspect, asset) for asset in assets)
    )
    sizes = {id(asset): size for asset, (_, size) in zip(assets, verdicts)}
    voice = [asset for asset in assets if asset.is_voice]
    return AssetSummary(
        file_count=len(assets),
        download_size=sum(size for _, size in verdicts),
        patch_count=sum(1 for asset in assets if asset.is_patch),
        copyover_count=sum(1 for asset in assets if not asset.is_patch),
        largest_target=max((asset.target_size for asset in assets), default=0),
        downgraded=sum(1 for verdict, _ in verdicts if verdict == _VERDICT_FULL),
        ready=sum(1 for verdict, _ in verdicts if verdict == _VERDICT_READY),
        voice_count=len(voice),
        voice_download=sum(sizes[id(asset)] for asset in voice),
    )


# --------------------------------------------------------------------------- #
# 单文件落盘
# --------------------------------------------------------------------------- #


def md5_file(path: str) -> str:
    """算文件 MD5，返回 32 位小写十六进制串。"""
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        while block := handle.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _same_md5(wanted: str, actual: str) -> bool:
    """清单里的 MD5 与算出来的是否一致；清单没给 MD5 时按一致处理。"""
    return not wanted or actual == wanted.casefold()


async def _target_is_current(target: str, asset: PatchAsset) -> bool:
    """目标文件是否已经是本轮要更新到的内容。

    先比体积（近乎免费），一致才算整文件 MD5。这是中断后接着更新的依据：上次已落盘的文件
    本轮不必重做——不查就重做，原位补丁会拿新内容当旧文件打补丁，产物校验必败。
    """
    if await asyncio.to_thread(_stat_size, target) != asset.target_size:
        return False
    return await asyncio.to_thread(md5_file, target) == asset.target_md5.casefold()


def _run_hpatchz(exe: str, old: str, diff: str, out: str, timeout: float) -> None:
    """调 hpatchz 把差分打到旧文件上，产出新文件。

    Raises:
        UpdaterError: 找不到补丁工具、子进程非零退出或超时。
    """
    try:
        result = subprocess.run(
            [exe, "-f", old, diff, out], capture_output=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as error:
        raise UpdaterError(f"hpatchz 超时（{timeout:.0f} 秒）: {out}") from error
    except OSError as error:
        raise UpdaterError(f"无法运行 hpatchz（{exe}）: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise UpdaterError(f"hpatchz 失败（{result.returncode}）: {detail[-200:]}")


def _diff_url(asset: PatchAsset, urls: BlobUrls) -> str:
    """这个文件的差分片段所在差分档案的地址。"""
    return f"{urls.diff_prefix.rstrip('/')}/{asset.patch_name}"


async def _fetch_range_to_file(
    client: Any,
    url: str,
    offset: int,
    length: int,
    dest: str,
    scratch: str,
    *,
    compressed: bool,
    on_bytes: Optional[Callable[[int], None]] = None,
) -> Tuple[int, str]:
    """按 Range 把一段数据流式取回、按需解压后写进 ``dest``。

    ``scratch`` 是压缩形态下的中转文件，调用方给（放在本轮的中间产物目录里，整轮结束时
    连着删）。返回 ``(dest 的字节数, 它的 MD5)``。

    这么绕一圈是为了两件事：整段数据不攒在内存里，几百 MiB 的文件几路并发同时下也不会把
    驻留抬到数 GiB；解压与校验都在工作线程里做，主循环既不碰磁盘也不算哈希。

    ``on_bytes`` 每落一块就报一次网上取回的字节数，供执行层的心跳行取用。

    Raises:
        UpdaterError: 网络失败、长度不符，或解压失败。
    """
    if length <= 0:
        # 清单里的空文件：拼不出合法的 Range，直接落一个空文件
        await asyncio.to_thread(_write_bytes, dest, b"")
        return 0, await asyncio.to_thread(md5_file, dest)
    source = scratch if compressed else dest
    try:
        await stream_range_to(client, url, offset, length, source, on_bytes=on_bytes)
        if not compressed:
            return length, await asyncio.to_thread(md5_file, dest)
        return await asyncio.to_thread(inflate_file, scratch, dest)
    finally:
        if source != dest:
            with suppress(OSError):
                os.remove(source)


def _blob_input_name(blob_name: str, offset: int, suffix: str) -> str:
    """共用差分档案的中间输入文件名：对完整分片名取哈希，再带偏移。

    一份档案供许多文件共用，只取分片名尾巴会让不同档案的尾部相同名字撞成同一个临时文件，
    同批并发时互相覆盖对方的补丁输入，收尾还会删掉别人正在读的档案段。
    """
    digest = hashlib.md5(blob_name.encode("utf-8", "replace")).hexdigest()[:16]
    return f"{digest}_{offset}{suffix}"


async def _old_file_usable(game_path: str, asset: PatchAsset) -> bool:
    """旧文件能不能直接打补丁：存在、尺寸与内容都和差分基线一致。

    hpatchz 按差分头里的 oldDataSize/oldMd5 校验旧文件，而现网差分不支持从空文件重建：
    旧文件缺失时硬打必然报 oldDataSize 不符，内容被改过则产出校验不过的坏文件。两种情形
    都该降级整文件重下。
    """
    old = safe_join(game_path, asset.original_name)
    if await asyncio.to_thread(_stat_size, old) != asset.original_size:
        return False
    if not asset.original_md5:
        return True
    actual = await asyncio.to_thread(md5_file, old)
    return _same_md5(asset.original_md5, actual)


def _staging_name(target: str) -> str:
    """目标文件同级目录下的临时名。"""
    directory = os.path.dirname(target) or "."
    return os.path.join(directory, f"{os.path.basename(target)}.mas-new")


async def _replace_from(staging: str, target: str) -> None:
    """把已校验的临时文件原子换成目标文件。"""
    await asyncio.to_thread(os.makedirs, os.path.dirname(target) or ".", exist_ok=True)
    await asyncio.to_thread(os.replace, staging, target)


def _inflate_place(
    raw: bytes, handle: Any, offset: int, compressed: bool
) -> Tuple[int, str]:
    """按需解压一个数据块、算出校验和，并写到目标文件的指定位置。

    返回 ``(写出字节数, 块内容的 MD5)``。放在线程里做，主循环既不碰磁盘也不算哈希。
    """
    data = decompress(raw) if compressed else raw
    handle.seek(offset)
    handle.write(data)
    return len(data), hashlib.md5(data).hexdigest()


async def fetch_full_asset(
    client: Any,
    game_path: str,
    asset: PatchAsset,
    *,
    on_bytes: Optional[Callable[[int], None]] = None,
) -> int:
    """按主清单把这个文件整份重建出来（降级路径）。

    逐个数据块从主包 ``chunk_download`` 基址取回，解压、算校验、写进同一个临时文件都在
    工作线程里做；全部落位后校完整 MD5 再原子替换。

    Returns:
        从网络取回的字节数（按网线上的压缩后长度计）。

    Note:
        临时文件必须用可 ``seek`` 的写模式打开：追加模式会忽略 ``seek``，每块都接在文件
        末尾，拼出来的就是个尺寸对不上的坏文件。

    Raises:
        UpdaterError: 主清单里没有该文件的数据块、某块长度或 MD5 不符、或整文件校验不过。
    """
    if not asset.chunks:
        raise UpdaterError(f"主清单里没有 {asset.name} 的数据块，无法整文件重建")

    urls = asset.urls
    target = safe_join(game_path, asset.name)
    staging = _staging_name(target)
    await asyncio.to_thread(os.makedirs, os.path.dirname(target) or ".", exist_ok=True)
    fetched = 0
    try:
        with open(staging, "wb") as handle:
            for chunk in asset.chunks:
                url = f"{urls.main_prefix.rstrip('/')}/{chunk.chunk_name}"
                raw = await request_bytes(client, url)
                fetched += len(raw)
                if on_bytes is not None:
                    on_bytes(len(raw))
                # 解压、校验、落位都在同一个线程里；驻留量按一个数据块计，不随文件体积放大
                size, digest = await asyncio.to_thread(
                    _inflate_place,
                    raw,
                    handle,
                    chunk.chunk_on_file_offset,
                    urls.main_compressed,
                )
                if not _same_md5(chunk.chunk_decompressed_hash_md5, digest):
                    raise UpdaterError(
                        f"数据块 {chunk.chunk_name} 校验失败: {asset.name}"
                    )
                expected = chunk.chunk_size_decompressed or chunk.chunk_size
                if expected and size != expected:
                    raise UpdaterError(
                        f"数据块 {chunk.chunk_name} 长度不符"
                        f"（期望 {expected}，实际 {size}）"
                    )
        if not await asyncio.to_thread(_verify, staging, asset.target_md5):
            raise UpdaterError(f"整文件重建后校验失败: {asset.name}")
        await _replace_from(staging, target)
    finally:
        with suppress(OSError):
            if os.path.isfile(staging):
                os.remove(staging)
    return fetched


def _verify(path: str, md5_wanted: str) -> bool:
    """临时文件的 MD5 是否与清单一致。"""
    return _same_md5(md5_wanted, md5_file(path))


async def apply_asset(
    client: Any,
    game_path: str,
    temp_dir: str,
    asset: PatchAsset,
    *,
    hpatchz: Optional[str],
    logger: Any,
    on_bytes: Optional[Callable[[int], None]] = None,
) -> Tuple[int, bool]:
    """处理一个文件：取回 → 校验 → 同卷原子替换。

    取数据的基址跟着文件走（``asset.urls``）：主资源与每档语音各有一套，混在一张总表里
    按计划级基址取就会取到别类的分片。

    Args:
        hpatchz: ``hpatchz`` 路径；``None`` 表示手上没有补丁工具。
        logger: 用于记下每一次降级。
        on_bytes: 每从网上取回一块就报一次字节数，供执行层的心跳行取用。

    Returns:
        ``(从网络取回的字节数, 是否走了整文件降级)``；目标已是新内容时返回 ``(0, False)``。

    Raises:
        UpdaterError: 取回、打补丁或校验失败，且降级也没成——由调用方计成本轮失败文件。
    """
    urls = asset.urls
    target = safe_join(game_path, asset.name)
    if await _target_is_current(target, asset):
        return 0, False

    if not asset.is_patch:
        # CopyOver 的分片本身就是完整的新文件；patch_offset 是分片在差分档案里的偏移，
        # 不是目标文件里的偏移，拿它当目标偏移会写错位置。
        staging = _staging_name(target)
        try:
            _, digest = await _fetch_range_to_file(
                client,
                _diff_url(asset, urls),
                asset.patch_offset,
                asset.patch_length,
                staging,
                os.path.join(
                    temp_dir,
                    _blob_input_name(asset.patch_name, asset.patch_offset, ".raw"),
                ),
                compressed=urls.diff_compressed,
                on_bytes=on_bytes,
            )
            if not _same_md5(asset.target_md5, digest):
                raise UpdaterError(f"CopyOver 内容校验失败: {asset.name}")
            await _replace_from(staging, target)
        finally:
            with suppress(OSError):
                if os.path.isfile(staging):
                    os.remove(staging)
        return asset.patch_length, False

    if hpatchz is None or not await _old_file_usable(game_path, asset):
        logger.warning(
            "%s 的差分基线不可用（旧文件缺失、尺寸或内容不符，或没有补丁工具），"
            "降级为整文件下载",
            asset.name,
        )
        return await fetch_full_asset(client, game_path, asset, on_bytes=on_bytes), True

    old = safe_join(game_path, asset.original_name)
    staging = _staging_name(target)
    # 同一份差分档案供许多文件共用，临时名必须能区分到档案里的位置，见 _blob_input_name
    diff_path = os.path.join(
        temp_dir, _blob_input_name(asset.patch_name, asset.patch_offset, ".diff")
    )
    try:
        await _fetch_range_to_file(
            client,
            _diff_url(asset, urls),
            asset.patch_offset,
            asset.patch_length,
            diff_path,
            f"{diff_path}.raw",
            compressed=urls.diff_compressed,
            on_bytes=on_bytes,
        )
        try:
            await asyncio.to_thread(
                _run_hpatchz,
                hpatchz,
                old,
                diff_path,
                staging,
                _hpatchz_timeout(asset.target_size),
            )
        except UpdaterError as error:
            # 打不出可信的新文件：退回整文件重下，取回的差分片段照实计入流量
            logger.warning("%s 打补丁失败，降级为整文件下载: %s", asset.name, error)
            with suppress(OSError):
                if os.path.isfile(staging):
                    os.remove(staging)
            fetched = await fetch_full_asset(
                client, game_path, asset, on_bytes=on_bytes
            )
            return fetched + asset.patch_length, True
        if not await asyncio.to_thread(_verify, staging, asset.target_md5):
            raise UpdaterError(f"补丁结果校验失败: {asset.name}")
        await _replace_from(staging, target)
    finally:
        # 清残骸不能顶掉真正的失败原因（或取消），所以整段包住
        with suppress(OSError):
            if os.path.isfile(staging):
                os.remove(staging)
        with suppress(OSError):
            os.remove(diff_path)
    return asset.patch_length, False


def _write_bytes(path: str, data: bytes) -> None:
    """覆盖写一个文件。"""
    with open(path, "wb") as handle:
        handle.write(data)


async def remove_unused(game_path: str, removals: Sequence[str], logger: Any) -> int:
    """删掉本轮淘汰的旧文件，返回真正删掉的个数。"""
    removed = 0
    for name in removals:
        path = safe_join(game_path, name)
        if not await asyncio.to_thread(os.path.isfile, path):
            continue
        try:
            await asyncio.to_thread(os.remove, path)
            removed += 1
        except OSError as error:
            logger.warning("删除旧文件失败 %s: %s", name, error)
    return removed
