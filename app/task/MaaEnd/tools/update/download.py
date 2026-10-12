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

import asyncio
import hashlib
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import aiofiles
import httpx

from app.utils.update_files import (
    file_md5,
    file_size,
    native_path,
    replace_file,
)

from . import package_index
from .common import (
    _CONNECT_TIMEOUT,
    _DOWNLOAD_CHUNK,
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
_MD5_CHUNK = 16 * 1024**2
_PART_ATTEMPTS = 3
"""单卷尝试次数：CDN 抖动与签名地址失效都在这里消化。"""
_MANIFEST_MAX_AGE = 60.0
"""清单最长复用时长（秒）。分卷地址带 `auth_key` 签名，按地址里的时间戳观测有效窗口约
2 分钟；这里取一半留余量，跨分钟的下载一定在新地址上做，不去赌边界。"""


def _hash_prefix(digest: Any, path: Path, limit: int) -> None:
    """续传前把已落盘的字节补进摘要。"""

    with open(native_path(path), "rb") as handle:
        read = 0
        while read < limit:
            block = handle.read(min(_MD5_CHUNK, limit - read))
            if not block:
                break
            digest.update(block)
            read += len(block)


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
        # 两条门槛任一到了就播一行。要两条都过才出声，慢链路上能十几分钟一行不出，
        # 前端那套「多久没新日志就算连接断了」的看门狗会把正常推进的更新判死并中止
        if self._downloaded < self._next_bytes and now < self._next_at:
            return
        self._next_bytes = self._downloaded + _PROGRESS_STEP
        self._next_at = now + _PROGRESS_INTERVAL
        # 速度取相邻两行之间的平均，不是相邻两个分块之间的抖动；窗口不足一秒就不报，
        # 那种样本只会给出一个几百 MB/s 的假数
        elapsed = now - self._sent_at
        speed = (
            f"，{(self._downloaded - self._sent_bytes) / elapsed / 1024**2:.1f} MB/s"
            if elapsed >= 1.0
            else ""
        )
        self._sent_bytes, self._sent_at = self._downloaded, now
        # 百分比按真实字节封顶显示：MD5 不符删掉重下那截确实流过网络，速度照全量算
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

    resume_from = max(file_size(temp), 0)
    if resume_from > size:
        temp.unlink(missing_ok=True)
        resume_from = 0
    digest = hashlib.md5()
    mode = "ab" if resume_from else "wb"
    headers = {"Range": f"bytes={resume_from}-"} if resume_from else {}
    # 服务端忽略 Range 时给回 200 与整份正文，这时必须从头覆盖写：追加会把新内容
    # 接在旧字节后面，静默写出坏文件
    async with client.stream("GET", url, headers=headers) as response:
        if response.status_code == 200 and resume_from:
            logger.warning("CDN 忽略了 Range，本卷从头重写")
            reporter.rewind(resume_from)
            resume_from = 0
            mode = "wb"
        response.raise_for_status()
        if mode == "ab":
            await asyncio.to_thread(_hash_prefix, digest, temp, resume_from)
        async with aiofiles.open(native_path(temp), mode) as sink:
            async for chunk in response.aiter_bytes(_DOWNLOAD_CHUNK):
                if not chunk:
                    continue
                await sink.write(chunk)
                digest.update(chunk)
                await reporter.add(len(chunk), part)
    return digest.hexdigest()


async def _download_release(
    release: Release,
    staging: Path,
    progress: ProgressFn | None,
    identity: InstallIdentity,
) -> list[Path]:
    """下载差量分卷，逐卷校验后改名；残留完整卷校验后可复用。

    暂存每轮尝试清理，但 Windows 句柄占用可能留下残卷。刷新地址时必须保持同一构建，
    各卷试满仍不完整则停止，不能将缺卷结果交给落地流程。"""

    files: list[Path] = []
    count = len(release.parts)
    # 落盘名取自 URL 末段：两卷同名就是互相覆盖，拼流会把一卷当两卷读。开局就判废，
    # 别等到落地阶段报「比服务端声明的短」——那时谁也说不清是哪一卷
    names = [_file_name_from_url(part.url) for part in release.parts]
    if len(set(names)) != count:
        raise EndfieldUpdateError("服务端给出的差量分卷有重名，无法区分两卷内容")
    reporter = _Reporter(progress, release.download_size, count)
    current = release
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT),
        follow_redirects=True,
    ) as client:
        for index, planned in enumerate(release.parts, start=1):
            target = staging / names[index - 1]
            if file_size(target) == planned.size and (
                not planned.md5
                or await asyncio.to_thread(file_md5, target) == planned.md5
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
                except (httpx.HTTPStatusError, httpx.TransportError) as error:
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
                if file_size(temp) != planned.size:
                    logger.warning(
                        f"{target.name} 体积不符（{file_size(temp)} != {planned.size}），重下"
                    )
                elif planned.md5 and digest != planned.md5:
                    logger.warning(
                        f"{target.name} 校验未通过（期望 {planned.md5} 实际 {digest}），重下"
                    )
                    # 坏文件必须删掉：留着它下一轮会从错的位置续传，越修越坏
                    temp.unlink(missing_ok=True)
                else:
                    replace_file(temp, target, clear_readonly=True)
                    files.append(target)
                    break
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
    """取一份新清单换回签名地址，并确认它描述的还是同一轮差量。

    必须用同一份身份重问：报目标版本会被服务端当成「已是最新」而回空差量，那样每次
    刷新都会误判成清单变了，整轮下载必然中止。
    """

    fresh = await _fetch_release(identity)
    if fresh.version != current.version:
        raise EndfieldUpdateError(
            f"下载期间服务端把最新版本换成了 {fresh.version}"
            f"（本轮目标 {current.version}）；混用两个构建的分卷会毁掉游戏目录，"
            "本轮更新中止，请重新发起"
        )
    if [part.md5 for part in fresh.parts] != [part.md5 for part in current.parts]:
        raise EndfieldUpdateError(
            f"下载期间服务端差量指纹发生变化（{len(current.parts)} 卷 → "
            f"{len(fresh.parts)} 卷），本轮更新中止，请重新发起"
        )
    return fresh


async def _prefetch_moves(
    client: httpx.AsyncClient,
    release: Release,
    report: ProgressFn,
) -> tuple[MoveJob, ...] | None:
    """在下载之前从远端读出包内的整文件清单，好把下载与落地的体积合成一次判定。

    只发几次小请求，不落下任何正文；读不到就返回 `None`，落地前那道门仍是权威判据。
    分卷地址带签名、有效窗口两分钟上下，这一步要在读盘核对基线之前做完。
    """

    await report("正在预取包内清单，先核对磁盘余量")
    doc = await package_index.fetch_member_json(
        client=client,
        volumes=[
            package_index.RemoteVolume(part.url, part.size) for part in release.parts
        ],
        cd_key=release.cd_key,
        member=_VERIFY_MANIFEST_MEMBER,
        max_plain_bytes=_MANIFEST_MAX_BYTES,
    )
    if doc is None:
        await report("未能预取到包内清单，本轮改为下载后再核对磁盘余量")
        return None
    entries = _move_entries(doc)
    await report(
        f"预取到包内整文件清单 {len(entries)} 条，按下载与落地的总量核对磁盘余量"
    )
    return entries


async def _prefetch_expanded(
    client: httpx.AsyncClient,
    release: Release,
    specs: Sequence[PatchJob],
) -> int:
    """下载前问一次「落地中途会展开多大的差量」：它只在包内总表里，清单不给。

    差量成员必须先整份解到暂存目录，hpatchz 才有输入文件可读；这一份与卷、与新临时文件
    是同时占盘的。只读总表，不取正文；问不到就返回 0，由固定余量兜。
    """

    if not specs:
        return 0
    sizes = await package_index.fetch_expanded_sizes(
        client=client,
        volumes=[
            package_index.RemoteVolume(part.url, part.size) for part in release.parts
        ],
        members=[spec.member for spec in specs],
    )
    return max(sizes.values(), default=0)
