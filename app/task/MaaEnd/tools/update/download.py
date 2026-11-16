#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""终末地差量分卷下载、续传、签名地址刷新与进度播报。"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Sequence
from pathlib import Path

import httpx

from app.services.common.update import transport as _service_update_transport
from app.utils import update_files as _utils_update_files

from . import package_index
from .common import (
    _CONNECT_TIMEOUT,
    _MANIFEST_MAX_BYTES,
    _READ_TIMEOUT,
    _TEMP_SUFFIX,
    _VERIFY_MANIFEST_MEMBER,
    EndfieldUpdateError,
    InstallIdentity,
    MoveJob,
    PatchJob,
    ProgressFn,
    Release,
    logger,
)
from .protocol import _fetch_release, _file_name_from_url, _move_entries

_PROGRESS_STEP = 512 * 1024**2
_PROGRESS_INTERVAL = 10.0
"""进度按「每 `_PROGRESS_STEP` 或每 `_PROGRESS_INTERVAL`」两者先到者播报一次：一轮下载
只出十几行，也给调度台日志留足余量，不让它撞上前端的截断线。"""
_PART_ATTEMPTS = 3
"""单卷尝试次数：CDN 抖动与签名地址失效都在这里消化。"""
_MANIFEST_MAX_AGE = 60.0
"""清单最长复用时长（秒）。分卷地址带 `auth_key` 签名，按地址里的时间戳观测有效窗口约
2 分钟；这里取一半留余量，跨分钟的下载一定在新地址上做，不去赌边界。"""


class _Reporter:
    """累计跨卷进度并按 `_PROGRESS_STEP` / `_PROGRESS_INTERVAL` 节流播报。"""

    def __init__(self, progress: ProgressFn | None, total: int, count: int) -> None:
        self._progress = progress
        self._total = total
        self._count = count
        self._downloaded = 0
        self._next_bytes = 0
        self._next_at = 0.0
        self._sent_bytes = 0
        self._sent_at = time.monotonic()

    def rewind(self, size: int) -> None:
        """把已计入但即将被覆盖重写的字节退回总量。

        「Range 被忽略 → 从头重写」这条路上，之前那次尝试计过的部分马上会被重新写
        一遍，不回收就会播报出超过总量的进度。
        """

        self._downloaded = max(self._downloaded - size, 0)
        self._next_bytes = self._downloaded
        self._next_at = 0.0
        # 速度窗口跟着重新起算：不退这一步，续传后第一行会把退回的字节当成没下的量
        self._sent_bytes = self._downloaded
        self._sent_at = time.monotonic()

    async def add(self, size: int, part: int) -> None:
        self._downloaded += size
        now = time.monotonic()
        if self._progress is None:
            return
        # 按两次播报之间的下载量计算平均速度，不足一秒时不显示。
        if self._downloaded < self._next_bytes and now < self._next_at:
            return
        self._next_bytes = self._downloaded + _PROGRESS_STEP
        self._next_at = now + _PROGRESS_INTERVAL
        # 按两次播报之间的下载量计算平均速度，不足一秒时不显示。
        elapsed = now - self._sent_at
        speed = (
            f"，{(self._downloaded - self._sent_bytes) / elapsed / 1024**2:.1f} MB/s"
            if elapsed >= 1.0
            else ""
        )
        self._sent_bytes, self._sent_at = self._downloaded, now
        # 显示进度最多为 100%，重复字节不算
        shown = min(self._downloaded, self._total)
        percent = shown / self._total * 100 if self._total else 0.0
        await self._progress(
            f"正在下载游戏更新包 {shown / 1024**3:.2f}/"
            f"{self._total / 1024**3:.2f} GB"
            f"（{percent:.1f}%，第 {part}/{self._count} 卷{speed}）"
        )


async def _download_part(
    client: httpx.AsyncClient,
    url: str,
    size: int,
    temp: Path,
    reporter: _Reporter,
    part: int,
) -> str:
    """顺序下载单卷并返回 MD5，支持 Range 续传。

    不分片并发：CDN 忽略 Range 时多会话可能拼出长度正确但内容重复的坏文件。"""

    digest = hashlib.md5()

    async def report(size: int) -> None:
        if size < 0:
            logger.warning("CDN 忽略了 Range，本卷从头重写")
            reporter.rewind(-size)
        else:
            await reporter.add(size, part)

    await _service_update_transport.download_resumable(
        client, url, temp, expected_size=size, on_bytes=report, digest=digest
    )
    return digest.hexdigest()


async def _download_release(
    release: Release,
    staging: Path,
    progress: ProgressFn | None,
    identity: InstallIdentity,
    reusable: Sequence[Path | None] | None = None,
) -> list[Path]:
    """下载差量分卷，逐卷校验后改名；残留完整卷校验后可复用。

    暂存每轮尝试清理，但 Windows 句柄占用可能留下残卷。刷新地址时必须保持同一构建，
    各卷试满仍不完整则停止，不能将缺卷结果交给落地流程。

    体积相符的既有分卷先比 MD5 决定复用，不重下：`reusable` 是开局按续传状态认出来的
    槽位（与本轮清单对齐），预先给上的直接采信，不再重复读一遍几十 GB 去算 MD5。中途换
    新签名地址或某一卷重下时同样兜住。"""

    files: list[Path] = []
    count = len(release.parts)
    # 落盘名取自 URL 末段：两卷同名就是互相覆盖，拼流会把一卷当两卷读。开局就判废，
    # 别等到落地阶段报「比服务端声明的短」——那时谁也说不清是哪一卷
    names = [_file_name_from_url(part.url) for part in release.parts]
    if len(set(names)) != count:
        raise EndfieldUpdateError("服务端给出的差量分卷有重名，无法区分两卷内容")
    reporter = _Reporter(progress, release.download_size, count)
    # 槽位只在与本轮清单等长时才算数：短了说明调用方没按状态认出来，按「没有可复用的」
    # 处理，不要在这里按下标取到越界
    if reusable is not None and len(reusable) != count:
        logger.warning(
            f"续传槽位有 {len(reusable)} 个，与本轮 {count} 卷对不上，本轮不复用暂存分卷"
        )
        reusable = None
    current = release
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT),
        follow_redirects=True,
    ) as client:
        for index, planned in enumerate(release.parts, start=1):
            target = staging / names[index - 1]
            claimed = reusable[index - 1] if reusable is not None else None
            if (
                claimed is not None
                and _utils_update_files.file_size(claimed) == planned.size
            ):
                logger.info(f"复用上轮已下好的分卷: {target.name}")
                await reporter.add(planned.size, index)
                files.append(claimed)
                continue
            if await _utils_update_files.file_matches(
                target, size=planned.size, md5=planned.md5 or None
            ):
                logger.info(f"复用已下载的分卷: {target.name}")
                await reporter.add(planned.size, index)
                files.append(target)
                continue
            temp = target.with_name(target.name + _TEMP_SUFFIX)
            part = planned
            for attempt in range(1, _PART_ATTEMPTS + 1):
                if time.monotonic() - current.fetched_at > _MANIFEST_MAX_AGE:
                    current = await _refresh_plan(identity, current)
                    part = current.parts[index - 1]
                try:
                    digest = await _download_part(
                        client, part.url, planned.size, temp, reporter, index
                    )
                except (
                    httpx.HTTPStatusError,
                    httpx.TransportError,
                    ValueError,
                ) as error:
                    if isinstance(error, httpx.HTTPStatusError):
                        status = error.response.status_code
                        if status not in (401, 403, 404, 410):
                            raise
                        logger.warning(f"{target.name} 返回 {status}，换签名地址重试")
                    else:
                        logger.warning(
                            f"{target.name} 传输中断（{type(error).__name__}: {error}），"
                            "换签名地址续传"
                        )
                    # 签名失效或断流时换新地址，保留已落盘字节供续传。
                    current = await _refresh_plan(identity, current)
                    part = current.parts[index - 1]
                    continue
                if await _utils_update_files.file_matches(
                    temp, size=planned.size, md5=planned.md5 or None, actual_md5=digest
                ):
                    _utils_update_files.replace_file(temp, target, clear_readonly=True)
                    files.append(target)
                    break
                actual_size = _utils_update_files.file_size(temp)
                logger.warning(
                    f"{target.name} 校验未通过：体积 {actual_size}/{planned.size}，"
                    f"MD5 {digest}/{planned.md5 or '未提供'}，重试"
                )
                # 不完整的文件留给续传，大小正确但内容错误的文件必须重下。
                if actual_size == planned.size:
                    temp.unlink(missing_ok=True)
            else:
                # 含「每次都是签名无效/过期」这条路：`continue` 也会走到这里，绝不放过
                # 少一卷的静默结果——拼流少一卷会写成半新半旧的包，比不更新更坏
                raise EndfieldUpdateError(
                    f"{target.name} 试满 {_PART_ATTEMPTS} 次仍未拿到完好的一卷，"
                    "请检查网络后重试"
                )
    if len(files) != len(release.parts):
        raise EndfieldUpdateError(
            f"差量卷应有 {len(release.parts)} 卷，实际只拿到 {len(files)} 卷"
        )
    return files


async def _refresh_plan(identity: InstallIdentity, current: Release) -> Release:
    """保证下载期间，没有服务端版本号变化"""

    fresh = await _fetch_release(identity)
    if fresh.version != current.version:
        raise EndfieldUpdateError(
            f"下载期间服务端把最新版本换成了 {fresh.version}"
            f"（本轮目标 {current.version}）；版本不一致，"
            "本轮更新中止，请重新发起"
        )
    if [part.md5 for part in fresh.parts] != [part.md5 for part in current.parts]:
        raise EndfieldUpdateError(
            f"下载期间服务端差量指纹发生变化（{len(current.parts)} 卷 → "
            f"{len(fresh.parts)} 卷），本轮更新中止"
        )
    return fresh


async def _prefetch_package(
    client: httpx.AsyncClient,
    release: Release,
    specs: Sequence[PatchJob],
    report: ProgressFn,
) -> tuple[tuple[MoveJob, ...] | None, dict[str, int] | None]:
    """预读整文件清单与各差量成员的展开体积；未知结果保留为 None。

    一次中央目录读取同时取出清单与全部成员体积：整包是单条 zip 的纯字节切片，分两次问要
    把同一份总表读两遍。展开体积按成员名给整份，取哪几条由调用方按本轮还要做的条目筛。
    """
    await report("正在预读包内清单，估算磁盘空间")
    doc, sizes = await package_index.fetch_package_metadata(
        client=client,
        volumes=[
            package_index.RemoteVolume(part.url, part.size) for part in release.parts
        ],
        cd_key=release.cd_key,
        member=_VERIFY_MANIFEST_MEMBER,
        members=[spec.member for spec in specs],
        max_plain_bytes=_MANIFEST_MAX_BYTES,
    )
    moves = _move_entries(doc) if doc is not None else None
    if moves is None or sizes is None:
        await report("未能完整预估更新空间，下载后再核对实际大小")
    else:
        await report(f"预读到整文件清单 {len(moves)} 条，核对下载与更新所需空间")
    return moves, sizes
