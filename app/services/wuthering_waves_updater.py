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

"""由 MAS 自行完成鸣潮游戏更新：拉官方清单、下载、校验、覆写。

全程不依赖官方启动器界面，只读它记录的安装目录。协议要点（均经实测）：

- 入口 index.json 只有两个 URL 需要硬编码，其余路径一律从清单里取。
- CDN 上是未压缩的原始文件，下载完直接比 md5，没有解压步骤。
- 增量包 `.krpdiff` 是 HDiffPatch 目录差分（HDIFF19&zstd&fadler64），
  用上游 MIT 版 hpatchz 应用；olddir 可直接传游戏目录，
  hpatchz 按名字匹配且只读被引用的文件。
- 清单里的 dest 来自网络，落盘前必须做路径穿越校验。
"""

import asyncio
import hashlib
import json
import os
import shutil
import zipfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import aiofiles
import httpx

from app.services.wuthering_waves import (
    get_official_index_url,
    write_wuthering_waves_local_version,
)
from app.utils import get_logger

logger = get_logger("鸣潮更新")

# hpatchz 用于应用官方增量包。上游 sisong/HDiffPatch 为 MIT，与本项目 AGPL 兼容。
# 仓库不跟踪二进制，故首次需要增量更新时按需下载并校验后缓存。
_HPATCHZ_VERSION = "v5.1.3"
_HPATCHZ_URL = (
    "https://github.com/sisong/HDiffPatch/releases/download/"
    f"{_HPATCHZ_VERSION}/hdiffpatch_{_HPATCHZ_VERSION}_bin_windows64.zip"
)
_HPATCHZ_ZIP_SHA256 = "77f141386e5d8f785c1c846e10fbbc19b6c05aa00e3f59cc44670fb3f0e2ae94"
_HPATCHZ_MEMBER = "windows64/hpatchz.exe"
_HPATCHZ_CACHE_DIR = Path.cwd() / "environment/hpatchz"

# 暂存区放在安装目录内，确保与游戏目录同卷，move 才是原子改名而非跨卷复制。
_STAGING_DIR_NAME = "_mas_update"
_LOCAL_MANIFEST_NAME = "LocalGameResources.json"

_CHUNK_SIZE = 1024 * 1024
_DOWNLOAD_CONCURRENCY = 4
_HTTP_TIMEOUT = httpx.Timeout(30.0, connect=15.0)

# 整文件同步在大版本跨越时可达 ~88GB，等同重装。超过此阈值不自动下载，
# 改为抛错让上层通知用户，避免无人值守时静默烧掉巨量流量和数小时。
_FULL_SYNC_SIZE_LIMIT = 10 * 1024**3

ProgressHook = Callable[[str], Awaitable[None]]


@dataclass(frozen=True)
class ResourceEntry:
    """清单里的一个待下载对象（整文件或 .krpdiff 补丁包）。"""

    dest: str
    md5: str
    size: int
    # 逐项下载基址，存在时覆盖计划级 base_url（整文件走 zip/，补丁包走 resources/）。
    from_folder: str | None = None

    @property
    def is_patch_blob(self) -> bool:
        return self.dest.endswith((".krpdiff", ".krdiff"))


@dataclass(frozen=True)
class PatchGroup:
    """一个 .krpdiff 的应用指令。"""

    blob: str
    dst_files: tuple[ResourceEntry, ...]


@dataclass
class UpdatePlan:
    """一次更新需要下载什么、怎么落地。"""

    target_version: str
    # patch: 下载 krpdiff 后用 hpatchz 应用；full: 直接整文件覆写。
    kind: str
    base_url: str
    cdn_urls: tuple[str, ...]
    downloads: tuple[ResourceEntry, ...]
    groups: tuple[PatchGroup, ...] = ()
    delete_files: tuple[str, ...] = ()
    # 整文件基址（zip/）。某个 group 打补丁失败时据此整文件重下该组产物。
    whole_file_base_url: str = ""

    @property
    def download_size(self) -> int:
        return sum(entry.size for entry in self.downloads)


def safe_relative_path(dest: str) -> Path:
    """把清单里的 dest 转成可信的相对路径。

    dest 完全来自网络，直接拼进文件系统会被路径穿越攻击（历史上 okww
    因缺此校验清空过项目源码）。这里拒绝一切绝对路径、盘符和 .. 分量。
    """

    raw = (dest or "").strip().replace("\\", "/")
    if not raw:
        raise ValueError("清单条目缺少 dest")
    candidate = Path(raw)
    if candidate.is_absolute() or candidate.drive or candidate.root:
        raise ValueError(f"清单条目 dest 非法（绝对路径）: {dest}")
    parts = candidate.parts
    # "." / "./" 会被 pathlib 归一成空 parts，若放过则解析结果就是根目录本身，
    # 后续 os.replace 会直接冲掉整个游戏目录。
    if not parts:
        raise ValueError(f"清单条目 dest 非法（指向目录自身）: {dest}")
    if ".." in parts:
        raise ValueError(f"清单条目 dest 非法（含上跳分量）: {dest}")
    return candidate


def resolve_within(root: Path, dest: str) -> Path:
    """在 root 下解析 dest，并复查结果没有逃出 root。"""

    resolved = (root / safe_relative_path(dest)).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"清单条目 dest 逃出目标目录: {dest}")
    return resolved


def _file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        while block := handle.read(_CHUNK_SIZE):
            digest.update(block)
    return digest.hexdigest()


async def file_md5(path: Path) -> str:
    """在线程里算 md5，避免大文件阻塞事件循环。"""

    return await asyncio.to_thread(_file_md5, path)


def _entry_from(payload: dict[str, Any]) -> ResourceEntry:
    return ResourceEntry(
        dest=str(payload.get("dest") or ""),
        md5=str(payload.get("md5") or "").strip().lower(),
        size=int(payload.get("size") or 0),
        from_folder=(str(payload["fromFolder"]) if payload.get("fromFolder") else None),
    )


def select_cdn_urls(index: dict[str, Any]) -> tuple[str, ...]:
    """按 P 权重挑 CDN，但整个列表都保留为兜底。

    国际服的下载域名在部分网络下会全部连不上，所以必须能逐个换，
    不能只信第一个。K1/K2 是启用开关，P 为 0 的是最后兜底。
    """

    entries = [
        item
        for item in (index.get("default") or {}).get("cdnList") or []
        if isinstance(item, dict) and item.get("url")
    ]
    usable = [item for item in entries if item.get("K1") == 1 and item.get("K2") == 1]
    ordered = sorted(
        usable or entries, key=lambda item: int(item.get("P") or 0), reverse=True
    )
    urls = tuple(str(item["url"]).rstrip("/") + "/" for item in ordered)
    if not urls:
        raise ValueError("鸣潮官方更新接口未返回可用 CDN")
    return urls


async def _get_json(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    response = await client.get(url, headers={"Accept": "application/json"})
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"清单格式错误: {url}")
    return payload


async def _fetch_manifest(
    client: httpx.AsyncClient, cdn_urls: tuple[str, ...], rel_path: str
) -> dict[str, Any]:
    """逐个 CDN 取清单，全部失败才报错。"""

    last_error: Exception | None = None
    for cdn in cdn_urls:
        try:
            return await _get_json(client, cdn + rel_path.lstrip("/"))
        except (httpx.HTTPError, ValueError) as exc:
            last_error = exc
            logger.warning("从 {} 取清单失败，换下一个 CDN: {}", cdn, exc)
    raise RuntimeError(f"所有 CDN 均无法取得清单 {rel_path}") from last_error


async def _report(hook: ProgressHook | None, line: str) -> None:
    logger.info(line)
    if hook is not None:
        await hook(line)


def _read_local_manifest(install_dir: Path) -> dict[str, str]:
    """读本地全量清单，得到 dest -> md5。

    启动器维护着这份文件，有它就不必为了算差集去 hash 89GB。
    读不到时返回空表，调用方会退化成逐文件 hash。
    """

    path = install_dir / _LOCAL_MANIFEST_NAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    entries = payload.get("resource") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return {}
    table: dict[str, str] = {}
    for item in entries:
        if isinstance(item, dict) and item.get("dest") and item.get("md5"):
            table[str(item["dest"])] = str(item["md5"]).strip().lower()
    return table


async def _local_md5(
    install_dir: Path, entry: ResourceEntry, cached: dict[str, str]
) -> str | None:
    """取本地文件的 md5，优先用启动器清单缓存。

    缓存只在文件大小也吻合时才采信；大小不符说明缓存已过期，回落到实算。
    """

    try:
        path = resolve_within(install_dir, entry.dest)
    except ValueError:
        return None
    if not path.is_file():
        return None
    known = cached.get(entry.dest)
    if known and path.stat().st_size == entry.size:
        return known
    return await file_md5(path)


async def _plan_full_sync(
    install_dir: Path,
    remote_entries: list[ResourceEntry],
    *,
    target_version: str,
    base_url: str,
    cdn_urls: tuple[str, ...],
    on_progress: ProgressHook | None,
) -> UpdatePlan:
    """整文件同步：只下载 md5 与远端不符的文件（兼作修复）。"""

    cached = _read_local_manifest(install_dir)
    if not cached:
        await _report(on_progress, "本地清单不可用，正在逐文件校验（较慢）...")
    stale: list[ResourceEntry] = []
    for entry in remote_entries:
        if await _local_md5(install_dir, entry, cached) != entry.md5:
            stale.append(entry)
    return UpdatePlan(
        target_version=target_version,
        kind="full",
        base_url=base_url,
        cdn_urls=cdn_urls,
        downloads=tuple(stale),
    )


def _build_patch_plan(
    patch_manifest: dict[str, Any],
    *,
    target_version: str,
    base_url: str,
    cdn_urls: tuple[str, ...],
    whole_file_base_url: str = "",
) -> UpdatePlan:
    """把官方增量清单转成执行计划。"""

    downloads = tuple(
        _entry_from(item)
        for item in patch_manifest.get("resource") or []
        if isinstance(item, dict)
    )
    groups: list[PatchGroup] = []
    for item in patch_manifest.get("groupInfos") or []:
        if not isinstance(item, dict) or not item.get("dest"):
            continue
        groups.append(
            PatchGroup(
                blob=str(item["dest"]),
                dst_files=tuple(
                    _entry_from(dst)
                    for dst in item.get("dstFiles") or []
                    if isinstance(dst, dict)
                ),
            )
        )
    deletions = tuple(
        str(item)
        for item in patch_manifest.get("deleteFiles") or []
        if isinstance(item, str) and item.strip()
    )
    if not downloads:
        raise ValueError("鸣潮增量清单没有可下载条目")
    return UpdatePlan(
        target_version=target_version,
        kind="patch",
        base_url=base_url,
        cdn_urls=cdn_urls,
        downloads=downloads,
        groups=tuple(groups),
        delete_files=deletions,
        whole_file_base_url=whole_file_base_url,
    )


async def build_update_plan(
    client: httpx.AsyncClient,
    index: dict[str, Any],
    install_dir: Path,
    local_version: str,
    *,
    on_progress: ProgressHook | None = None,
) -> UpdatePlan:
    """优先走官方增量；本地版本不在 patchConfig 里时退化成整文件同步。"""

    default = index.get("default")
    if not isinstance(default, dict):
        raise ValueError("鸣潮官方更新接口缺少 default 段")
    config = default.get("config")
    if not isinstance(config, dict):
        raise ValueError("鸣潮官方更新接口缺少 default.config")
    target_version = str(default.get("version") or "").strip()
    if not target_version:
        raise ValueError("鸣潮官方更新接口缺少 default.version")

    cdn_urls = select_cdn_urls(index)

    for item in config.get("patchConfig") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("version") or "").strip() != local_version:
            continue
        index_file = str(item.get("indexFile") or "").strip()
        if not index_file:
            break
        await _report(
            on_progress, f"匹配到官方增量包: {local_version} -> {target_version}"
        )
        manifest = await _fetch_manifest(client, cdn_urls, index_file)
        return _build_patch_plan(
            manifest,
            target_version=target_version,
            base_url=str(item.get("baseUrl") or "").strip(),
            cdn_urls=cdn_urls,
            whole_file_base_url=(
                str(default.get("resourcesBasePath") or "").strip().rstrip("/") + "/"
            ),
        )

    await _report(
        on_progress,
        f"官方未提供 {local_version} 的增量包，改为按文件校验补全",
    )
    manifest = await _fetch_manifest(
        client, cdn_urls, str(config.get("indexFile") or "")
    )
    remote_entries = [
        _entry_from(item)
        for item in manifest.get("resource") or []
        if isinstance(item, dict)
    ]
    if not remote_entries:
        raise ValueError("鸣潮全量清单为空")
    return await _plan_full_sync(
        install_dir,
        remote_entries,
        target_version=target_version,
        base_url=str(default.get("resourcesBasePath") or "").strip().rstrip("/") + "/",
        cdn_urls=cdn_urls,
        on_progress=on_progress,
    )


def _entry_url(cdn: str, plan: UpdatePlan, entry: ResourceEntry) -> str:
    # dest 里含空格（如 "Wuthering Waves.exe"），必须编码后再请求。
    base = entry.from_folder if entry.from_folder else plan.base_url
    return cdn + quote(base.lstrip("/") + entry.dest, safe=":/")


async def _stream_to_file(
    client: httpx.AsyncClient, url: str, target: Path, expected_size: int
) -> None:
    """流式下载，支持断点续传。"""

    done = target.stat().st_size if target.is_file() else 0
    if done and done >= expected_size:
        # 长度已够，交给外层 md5 判定是留用还是重下。
        return
    headers = {"Range": f"bytes={done}-"} if done else {}
    async with client.stream("GET", url, headers=headers) as response:
        response.raise_for_status()
        # 请求了 Range 但服务端回 200，说明它整体重发了：必须覆盖而不是追加，
        # 否则会把新内容接在旧字节后面，静默写出坏文件。
        mode = "ab" if (done and response.status_code == 206) else "wb"
        target.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(target, mode) as handle:
            async for block in response.aiter_bytes(chunk_size=_CHUNK_SIZE):
                if block:
                    await handle.write(block)


async def _download_entry(
    client: httpx.AsyncClient,
    plan: UpdatePlan,
    entry: ResourceEntry,
    staging: Path,
    *,
    attempts: int = 2,
) -> Path:
    """下载单个条目到暂存区，md5 校验通过才算成功。"""

    target = resolve_within(staging, entry.dest)
    if target.is_file() and target.stat().st_size == entry.size:
        if await file_md5(target) == entry.md5:
            return target

    last_error: Exception | None = None
    for cdn in plan.cdn_urls:
        url = _entry_url(cdn, plan, entry)
        for attempt in range(attempts):
            try:
                await _stream_to_file(client, url, target, entry.size)
                actual = await file_md5(target)
                if actual == entry.md5:
                    return target
                last_error = ValueError(f"md5 不符: 期望 {entry.md5} 实际 {actual}")
                # 校验失败的残留必须删掉，否则下一轮续传会接在坏字节后面。
                target.unlink(missing_ok=True)
            except (httpx.HTTPError, OSError) as exc:
                last_error = exc
                logger.warning(
                    "下载 {} 失败({}/{}): {}", entry.dest, attempt + 1, attempts, exc
                )
        logger.warning("CDN {} 无法下载 {}，换下一个", cdn, entry.dest)
    raise RuntimeError(f"下载失败: {entry.dest} ({last_error})") from last_error


async def download_plan(
    client: httpx.AsyncClient,
    plan: UpdatePlan,
    staging: Path,
    *,
    on_progress: ProgressHook | None = None,
) -> None:
    """并发下载计划里的全部条目。"""

    total = len(plan.downloads)
    if not total:
        return
    semaphore = asyncio.Semaphore(_DOWNLOAD_CONCURRENCY)
    finished = 0
    lock = asyncio.Lock()

    async def worker(entry: ResourceEntry) -> None:
        nonlocal finished
        async with semaphore:
            await _download_entry(client, plan, entry, staging)
        async with lock:
            finished += 1
            await _report(
                on_progress, f"鸣潮更新下载中 {finished}/{total}: {entry.dest}"
            )

    await asyncio.gather(*(worker(entry) for entry in plan.downloads))


def _extract_hpatchz(zip_path: Path, target: Path) -> None:
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open(_HPATCHZ_MEMBER) as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst)


async def ensure_hpatchz(
    *, on_progress: ProgressHook | None = None, timeout: float = 120.0
) -> Path:
    """确保本地有 hpatchz，没有则下载并校验 sha256 后缓存。

    仓库不跟踪二进制，所以按需拉取。校验固定的 sha256 是必须的：
    这是个会被我们拿去改写游戏文件的可执行体，不能来源不明。
    """

    exe = _HPATCHZ_CACHE_DIR / "hpatchz.exe"
    if exe.is_file():
        return exe

    await _report(on_progress, f"正在获取增量补丁工具 hpatchz {_HPATCHZ_VERSION}...")
    _HPATCHZ_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = _HPATCHZ_CACHE_DIR / "hpatchz.zip"
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(_HPATCHZ_URL)
        response.raise_for_status()
        payload = response.content

    actual = hashlib.sha256(payload).hexdigest()
    if actual != _HPATCHZ_ZIP_SHA256:
        raise RuntimeError(
            f"hpatchz 校验失败: 期望 {_HPATCHZ_ZIP_SHA256} 实际 {actual}"
        )
    zip_path.write_bytes(payload)
    try:
        await asyncio.to_thread(_extract_hpatchz, zip_path, exe)
    finally:
        zip_path.unlink(missing_ok=True)
    logger.info("hpatchz 就绪: {}", exe)
    return exe


async def _run_hpatchz(exe: Path, old_dir: Path, blob: Path, out_dir: Path) -> None:
    """应用一个目录差分包。

    olddir 直接传游戏目录：hpatchz 按名字匹配、只读被引用的文件，
    多余文件既不影响结果也不产生额外开销（已实测）。
    """

    process = await asyncio.create_subprocess_exec(
        str(exe),
        "-f",
        f"{old_dir}{os.sep}",
        str(blob),
        f"{out_dir}{os.sep}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await process.communicate()
    if process.returncode != 0:
        detail = stdout.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(
            f"hpatchz 应用失败 (code={process.returncode}): {detail[-1] if detail else ''}"
        )


async def _commit_file(source: Path, install_dir: Path, entry: ResourceEntry) -> None:
    """校验后把文件移入游戏目录。

    先校验再移动：宁可这次更新失败，也不能把坏文件写进游戏目录。
    同卷下 os.replace 是原子改名，不存在写一半的中间态。
    """

    actual = await file_md5(source)
    if actual != entry.md5:
        raise RuntimeError(f"{entry.dest} 校验失败: 期望 {entry.md5} 实际 {actual}")
    target = resolve_within(install_dir, entry.dest)
    target.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(os.replace, source, target)


async def _commit_entries(
    staging: Path,
    install_dir: Path,
    entries: tuple[ResourceEntry, ...],
    *,
    on_progress: ProgressHook | None = None,
) -> None:
    total = len(entries)
    for done, entry in enumerate(entries, start=1):
        await _commit_file(resolve_within(staging, entry.dest), install_dir, entry)
        if done % 20 == 0 or done == total:
            await _report(on_progress, f"鸣潮更新覆写中 {done}/{total}")


async def _redownload_group(
    client: httpx.AsyncClient,
    plan: UpdatePlan,
    group: PatchGroup,
    staging: Path,
    install_dir: Path,
) -> None:
    """某个 group 打补丁失败时，整文件重下该组产物。

    hpatchz 要求源文件字节精确，用户改过游戏文件就会失败。
    远端清单带全量 md5，所以总能靠整文件重下自愈，不该让整次更新死掉。
    """

    if not plan.whole_file_base_url:
        raise RuntimeError("缺少整文件基址，无法回退重下")
    fallback = UpdatePlan(
        target_version=plan.target_version,
        kind="full",
        base_url=plan.whole_file_base_url,
        cdn_urls=plan.cdn_urls,
        downloads=group.dst_files,
    )
    await download_plan(client, fallback, staging)
    await _commit_entries(staging, install_dir, group.dst_files)


async def _apply_groups(
    client: httpx.AsyncClient,
    plan: UpdatePlan,
    staging: Path,
    install_dir: Path,
    *,
    on_progress: ProgressHook | None = None,
) -> None:
    """逐组应用增量补丁，失败的组回退成整文件重下。"""

    exe = await ensure_hpatchz(on_progress=on_progress)
    patched_root = staging / "_patched"
    total = len(plan.groups)
    for done, group in enumerate(plan.groups, start=1):
        blob = resolve_within(staging, group.blob)
        out_dir = patched_root / str(done)
        shutil.rmtree(out_dir, ignore_errors=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            await _run_hpatchz(exe, install_dir, blob, out_dir)
            for entry in group.dst_files:
                await _commit_file(
                    resolve_within(out_dir, entry.dest), install_dir, entry
                )
        except (RuntimeError, OSError, ValueError) as exc:
            logger.warning("{} 应用失败，回退整文件重下: {}", group.blob, exc)
            await _report(on_progress, f"补丁 {done}/{total} 应用失败，改为整文件下载")
            await _redownload_group(client, plan, group, staging, install_dir)
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)
        await _report(on_progress, f"鸣潮更新应用中 {done}/{total}")


async def _apply_deletions(install_dir: Path, plan: UpdatePlan) -> None:
    """删除官方标记的过期文件。只删文件，路径非法一律跳过。"""

    for dest in plan.delete_files:
        try:
            target = resolve_within(install_dir, dest)
        except ValueError as exc:
            logger.warning("跳过非法删除项: {}", exc)
            continue
        if target.is_file():
            await asyncio.to_thread(target.unlink, True)


def _check_disk_space(install_dir: Path, plan: UpdatePlan) -> None:
    """开工前查空间。峰值需要暂存 + 补丁产物同时在盘上。"""

    largest_group = max(
        (sum(entry.size for entry in group.dst_files) for group in plan.groups),
        default=0,
    )
    required = plan.download_size + largest_group
    free = shutil.disk_usage(install_dir).free
    if free < required:
        raise RuntimeError(
            f"磁盘空间不足: 需要约 {required / 1024**3:.1f}GB, "
            f"可用 {free / 1024**3:.1f}GB"
        )


async def update_wuthering_waves(
    install_dir: Path,
    resource: str,
    local_version: str,
    *,
    on_progress: ProgressHook | None = None,
    full_sync_limit: int = _FULL_SYNC_SIZE_LIMIT,
) -> str:
    """把鸣潮更新到官方最新版，全程由 MAS 自己完成。

    Args:
        install_dir: 游戏安装目录（含 launcherDownloadConfig.json）。
        resource: `官服` 或 `国际服`。
        local_version: 当前已装版本。
        on_progress: 进度回调，用于推送到调度台。
        full_sync_limit: 整文件同步的体积上限，超过则拒绝并报错。

    Returns:
        更新后的版本号。

    Raises:
        RuntimeError: 下载、校验、应用失败，或体积/空间超限。
    """

    index_url = get_official_index_url(resource)
    staging = install_dir / _STAGING_DIR_NAME
    staging.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(
        timeout=_HTTP_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": "AUTO-MAS/okww"},
    ) as client:
        index = await _get_json(client, index_url)
        plan = await build_update_plan(
            client, index, install_dir, local_version, on_progress=on_progress
        )

        if not plan.downloads:
            await _report(on_progress, f"鸣潮资源已与 {plan.target_version} 一致")
            write_wuthering_waves_local_version(install_dir, plan.target_version)
            shutil.rmtree(staging, ignore_errors=True)
            return plan.target_version

        size_gb = plan.download_size / 1024**3
        # 整文件同步在大版本跨越时接近重装，不该在无人值守时静默跑掉。
        if plan.kind == "full" and plan.download_size > full_sync_limit:
            raise RuntimeError(
                f"需整文件同步 {size_gb:.1f}GB（超过 "
                f"{full_sync_limit / 1024**3:.0f}GB 上限），已中止，请手动处理"
            )
        _check_disk_space(install_dir, plan)
        await _report(
            on_progress,
            f"开始更新鸣潮 {local_version} -> {plan.target_version}"
            f"（{plan.kind}, {size_gb:.2f}GB, {len(plan.downloads)} 项）",
        )
        await download_plan(client, plan, staging, on_progress=on_progress)

        if plan.kind == "patch":
            await _apply_groups(
                client, plan, staging, install_dir, on_progress=on_progress
            )
            whole_files = tuple(
                entry for entry in plan.downloads if not entry.is_patch_blob
            )
            await _commit_entries(
                staging, install_dir, whole_files, on_progress=on_progress
            )
        else:
            await _commit_entries(
                staging, install_dir, plan.downloads, on_progress=on_progress
            )

    await _apply_deletions(install_dir, plan)
    # 版本记录最后写：中断后下一轮会看到旧版本并重新规划，而不是误判已完成。
    write_wuthering_waves_local_version(install_dir, plan.target_version)
    shutil.rmtree(staging, ignore_errors=True)
    await _report(on_progress, f"鸣潮已更新至 {plan.target_version}")
    return plan.target_version
