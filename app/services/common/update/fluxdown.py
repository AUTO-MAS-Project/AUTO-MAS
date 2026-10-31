#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.
#
#   Contact: DLmaster_361@163.com

"""FluxDown CLI 多线程分段下载分发层。

根据宿主传入的下载选项选择走 FluxDown 还是回退到
``update_transport.download_file`` 的内置 httpx 实现，不持有宿主配置——
Mirror 酱源（临时授权 URL + 短期 token）在本文件里一律跳过 FluxDown，直接走 httpx。

宿主在每次下载尝试前构造选项，通过异步回调保存下载历史。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.services.common.update.transport import DownloadProgress
from app.services.common.update.transport import download_file as _httpx_download
from app.utils import fluxdown_cli as _utils_fluxdown_cli
from app.utils import get_logger

logger = get_logger("FluxDown")

# 用户重试多少次仍失败后，在失败提示里建议改用内置 httpx
_RESUMABLE_HINT_THRESHOLD = 3


@dataclass(frozen=True)
class FluxdownOptions:
    """一次下载尝试使用的默认选项，不持有宿主配置对象。"""

    downloader: str
    source: str
    cli_path: str
    segments: int
    server_mode: bool
    cli_search_dirs: tuple[Path, ...] = ()


HistoryWriter = Callable[[_utils_fluxdown_cli.FluxdownDownloadRecord], Awaitable[None]]


async def download_file(
    url: str,
    destination: Path,
    *,
    timeout: float,
    options: FluxdownOptions,
    write_history: HistoryWriter | None = None,
    proxy: httpx.Proxy | None = None,
    progress: DownloadProgress | None = None,
    downloader: str | None = None,
    source: str | None = None,
) -> int:
    """同一输出文件的下载、回退和清映射共用跨进程锁。"""
    async with _utils_fluxdown_cli.fluxdown_destination_lock(
        Path(options.cli_path), destination
    ):
        return await _download_file(
            url,
            destination,
            timeout=timeout,
            options=options,
            write_history=write_history,
            proxy=proxy,
            progress=progress,
            downloader=downloader,
            source=source,
        )


async def _download_file(
    url: str,
    destination: Path,
    *,
    timeout: float,
    options: FluxdownOptions,
    write_history: HistoryWriter | None = None,
    proxy: httpx.Proxy | None = None,
    progress: DownloadProgress | None = None,
    downloader: str | None = None,
    source: str | None = None,
) -> int:
    """根据宿主选项分发下载：FluxDown 或内置 httpx。

    FluxDown 链路：server 模式（断点续传）→ --local（仅 server 异常）→ httpx。
    server 任务级失败（超时/断网/任务 failed）保留 task 映射并抛
    :class:`FluxdownResumableError`，上层重试时自动 resume 续传，不会降级丢弃
    已下分段；连续重试仍失败由上层在最终失败提示里建议改用 httpx（见
    ``app/services/update.py``），--local 只兜 server 进程异常，不兜网络失败。

    ``downloader`` 参数允许上层绕过默认选项直接指定（"builtin" / "fluxdown"），
    用于"重试 N 次失败后改用 httpx"这类显式降级。

    ``source`` 为任务启动时冻结的来源，缺省才回落到本次选项的来源。
    来源随任务冻结，避免用户中途改设置后把短期授权 URL 交给 FluxDown。

    Mirror 酱源强制跳过 FluxDown（大小写不敏感）：Mirror 酱用临时授权 URL +
    CDN 多，FluxDown 的 Range 续传可能和短期 token 冲突。
    """
    explicit_builtin = downloader == "builtin"
    downloader = downloader or options.downloader
    frozen_source = source if source is not None else options.source
    segments = options.segments
    proxy_str = _proxy_to_str(proxy)

    # Mirror 酱或无 FluxDown 需求 → 直接走 httpx
    if (
        downloader != "fluxdown"
        or frozen_source.lower() == "mirrorchyan"
        or (proxy is not None and proxy.auth is not None)
    ):
        if downloader == "fluxdown":
            logger.info(
                "Mirror 酱源或认证代理使用内置 httpx 下载，避免凭据进入 CLI 参数"
            )
        # 无论是显式选内置还是配置默认走内置，只要此前可能经 FluxDown 下载过
        # 同一 (url, destination)，都需先确认旧 server 任务已停止再覆写；
        # 显式内置成功后再清理映射，避免残留任务在下次同 url 下载时被无谓 resume
        cli = _utils_fluxdown_cli.fluxdown_find_cli(
            options.cli_path, search_dirs=options.cli_search_dirs
        )
        if cli is not None:
            await _ensure_can_downgrade(
                cli,
                url,
                destination,
                segments=segments,
                proxy_str=proxy_str,
                action="改用内置 httpx 下载",
                write_history=write_history,
            )
        size = await _httpx_download(
            url, destination, timeout=timeout, proxy=proxy, progress=progress
        )
        if explicit_builtin:
            # 用户多次失败后显式选择 httpx 并下载成功：清掉 FluxDown 任务映射,
            # 避免残留任务在下次同 url 下载时被无谓 resume
            if cli is not None:
                _utils_fluxdown_cli.fluxdown_server_forget(cli, url, destination)
                logger.info(
                    "已按用户选择使用内置 httpx 完成下载,清理 FluxDown 任务映射"
                )
        return size

    # ---- FluxDown 路径 ----
    cli_path = _utils_fluxdown_cli.fluxdown_find_cli(
        options.cli_path, search_dirs=options.cli_search_dirs
    )
    if cli_path is None:
        # CLI 不存在 → 回退 httpx
        logger.warning("未找到 FluxDown CLI,回退内置 httpx 下载")
        return await _httpx_download(
            url, destination, timeout=timeout, proxy=proxy, progress=progress
        )

    try:
        return await _download_via_fluxdown(
            url=url,
            destination=destination,
            cli_path=cli_path,
            timeout=timeout,
            proxy=proxy,
            progress=progress,
            options=options,
            write_history=write_history,
        )
    except _utils_fluxdown_cli.FluxdownCancelUnconfirmed:
        # 取消时无法确认 FluxDown 任务已停止：文件所有权不明，绝不能回退 httpx
        # 覆写同一目标，原样抛给上层显式报告失败并保留映射待续传
        raise
    except FluxdownResumableError:
        # server 任务级失败（断网/超时/任务 failed）：task 已保留，**不降 httpx**
        # （httpx 从头下会浪费已下分段），原样抛给上层原地重试走 resume。
        raise
    except Exception as exc:
        # 其余 FluxDown 失败（--local 进程异常等）→ 回退 httpx，同时记录回退事件
        logger.warning(f"FluxDown 链路失败,回退内置 httpx: {exc}")
        # 与 --local 同一门槛：确认旧任务已停止/不存在才允许 httpx 覆写目标文件
        await _ensure_can_downgrade(
            cli_path,
            url,
            destination,
            segments=segments,
            proxy_str=proxy_str,
            action="回退内置 httpx",
            write_history=write_history,
        )
        await _append_history(
            _utils_fluxdown_cli.FluxdownDownloadRecord(
                url=url,
                destination=str(destination),
                size=0,
                duration_ms=0,
                segments=segments,
                proxy=proxy_str,
                checksum=None,
                status="fluxdown_fallback",
                error=f"FluxDown 失败，回退 httpx: {exc}",
            ),
            write_history=write_history,
        )
        return await _httpx_download(
            url, destination, timeout=timeout, proxy=proxy, progress=progress
        )


async def _download_via_fluxdown(
    url: str,
    destination: Path,
    cli_path: Path,
    timeout: float,
    proxy: httpx.Proxy | None,
    progress: DownloadProgress | None,
    *,
    options: FluxdownOptions,
    write_history: HistoryWriter | None,
) -> int:
    """FluxDown 下载：优先 server 模式（断点续传），仅 server 进程异常落 --local。

    server 任务级失败（超时/断网/任务 failed）抛 :class:`FluxdownResumableError`
    并保留 task 映射，上层重试自动 resume；server 不可用/启动失败/status 查询
    失败（进程级异常）才落 --local，且落 --local 前必须经
    :func:`_ensure_can_downgrade` 确认旧任务已停止。--local 不再兜网络失败，
    避免删掉已下分段。
    """
    segments = options.segments
    proxy_str = _proxy_to_str(proxy)
    server_on = options.server_mode

    if server_on and _utils_fluxdown_cli.fluxdown_server_available(
        cli_path, enabled=True
    ):
        try:
            size, record = await _utils_fluxdown_cli.fluxdown_server_download(
                url,
                destination,
                cli_exe=cli_path,
                segments=segments,
                proxy=proxy_str,
                timeout=timeout,
                progress=progress,
            )
            await _append_history(record, write_history=write_history)
            # 下载成功 → 清映射（MAS 后续哈希校验如失败会重下，重新 add）
            _utils_fluxdown_cli.fluxdown_server_forget(cli_path, url, destination)
            return size
        except _utils_fluxdown_cli.FluxdownCancelUnconfirmed:
            # 不能按"普通进程异常"降级 --local：daemon 可能仍在写目标文件
            raise
        except Exception as exc:
            msg = str(exc)
            # 进程级异常且旧任务已确认停止 → 安全落 --local 一次性下载；
            # "status 查询失败" 但任务未确认停止时 daemon 可能仍在写输出文件，
            # 落 --local 会双写，此时保留映射、按可续传中断抛出
            if "status 查询失败" in msg and "任务未确认停止" in msg:
                await _block_downgrade(
                    cli_path,
                    url,
                    destination,
                    segments=segments,
                    proxy_str=proxy_str,
                    detail=msg,
                    write_history=write_history,
                )
            if (
                "server 不可用" in msg
                or "status 查询失败" in msg
                or "cannot connect to" in msg
                or "is FluxDown running" in msg
            ):
                # 进程级异常也要过统一门槛：旧 daemon 可能仍在写同一目标文件
                await _ensure_can_downgrade(
                    cli_path,
                    url,
                    destination,
                    segments=segments,
                    proxy_str=proxy_str,
                    action="降级 --local 一次性下载",
                    write_history=write_history,
                )
                logger.warning(f"server 进程异常,降级 --local 一次性下载: {msg}")
            else:
                # 任务级失败（超时/断网/任务 failed/add probe 失败）→ 保留映射，抛可续传错误；
                # 累计中断次数，达到阈值后在错误信息里建议改用内置 httpx
                count = _utils_fluxdown_cli.fluxdown_server_mark_failure(
                    cli_path, url, destination
                )
                hint = (
                    "；已多次重试仍失败，可在设置中将下载器改为内置（httpx）后重试"
                    if count >= _RESUMABLE_HINT_THRESHOLD
                    else ""
                )
                logger.warning(
                    f"下载中断（第 {count} 次）,任务已保留,重试将断点续传: {msg}"
                )
                # 中断也记入历史（status=interrupted），成功续传后会有对应 success 记录
                await _append_history(
                    _utils_fluxdown_cli.FluxdownDownloadRecord(
                        url=url,
                        destination=str(destination),
                        size=0,
                        duration_ms=0,
                        segments=segments,
                        proxy=proxy_str,
                        checksum=None,
                        status="interrupted",
                        error=f"下载中断（第 {count} 次）,任务已保留可续传: {msg}",
                    ),
                    write_history=write_history,
                )
                raise FluxdownResumableError(f"{msg}{hint}") from exc
    elif not server_on:
        logger.info("FluxDown 断点续传服务已关闭,使用 --local 一次性下载")

    # --local 兜底（多线程，无续传）：仅在 server 进程异常或开关关闭时到达；
    # 落 --local 会删掉目标文件重写，必须先确认旧 server 任务已停止/不存在
    await _ensure_can_downgrade(
        cli_path,
        url,
        destination,
        segments=segments,
        proxy_str=proxy_str,
        action="降级 --local 一次性下载",
        write_history=write_history,
    )
    size, record = await _utils_fluxdown_cli.fluxdown_download(
        url,
        destination,
        cli_exe=cli_path,
        segments=segments,
        proxy=proxy_str,
        checksum=None,  # 让 MAS 自己做最终校验，FluxDown 只负责下载
        timeout=timeout,
        progress=progress,
    )
    await _append_history(record, write_history=write_history)
    return size


async def _can_downgrade(cli_path: Path, url: str, destination: Path) -> bool:
    """是否可安全降级改写目标文件：旧 FluxDown 任务已确认停止/不存在。

    统一 ``--local`` 与内置 httpx 两条降级路径的门槛，避免旧 daemon 仍在写
    同一目标时启动第二个写入者。
    """
    return await asyncio.to_thread(
        _utils_fluxdown_cli.fluxdown_server_task_safe_to_overwrite,
        cli_path,
        url,
        destination,
    )


async def _block_downgrade(
    cli_path: Path,
    url: str,
    destination: Path,
    *,
    segments: int,
    proxy_str: str | None,
    detail: str,
    write_history: HistoryWriter | None,
) -> None:
    """任务未确认停止：记一次失败、留中断记录并抛可续传错误，禁止启动新写入者。"""
    count = _utils_fluxdown_cli.fluxdown_server_mark_failure(cli_path, url, destination)
    hint = (
        "；已多次重试仍失败，可在设置中将下载器改为内置（httpx）后重试"
        if count >= _RESUMABLE_HINT_THRESHOLD
        else ""
    )
    logger.warning(f"server 任务未确认停止（第 {count} 次）, 保留映射待续传: {detail}")
    await _append_history(
        _utils_fluxdown_cli.FluxdownDownloadRecord(
            url=url,
            destination=str(destination),
            size=0,
            duration_ms=0,
            segments=segments,
            proxy=proxy_str,
            checksum=None,
            status="interrupted",
            error=f"server 任务未确认停止（第 {count} 次）: {detail}",
        ),
        write_history=write_history,
    )
    raise FluxdownResumableError(f"{detail}{hint}")


async def _ensure_can_downgrade(
    cli_path: Path,
    url: str,
    destination: Path,
    *,
    segments: int,
    proxy_str: str | None,
    action: str,
    write_history: HistoryWriter | None,
) -> None:
    """降级前的统一门槛：确认旧任务已停止才放行，否则记失败并抛可续传错误。"""
    if await _can_downgrade(cli_path, url, destination):
        return
    await _block_downgrade(
        cli_path,
        url,
        destination,
        segments=segments,
        proxy_str=proxy_str,
        detail=f"{action}时任务未确认停止",
        write_history=write_history,
    )


class FluxdownResumableError(RuntimeError):
    """FluxDown server 任务级失败（网络中断/超时/任务 failed），task 已保留可续传。

    上层应原地重试（同一 url+destination 会走 resume）；连续重试仍失败时
    在最终失败提示中建议改用内置 httpx 重新下载（downloader="builtin"），
    不要落 --local（会删掉已下载的分段文件）。
    """


def _proxy_to_str(proxy: httpx.Proxy | None) -> str | None:
    """仅返回不含凭据的代理端点，认证保留在 httpx.Proxy 中。"""
    if proxy is None:
        return None
    # CLI 无安全传递认证的入口；认证代理由 httpx 处理，此处仅用于记录端点。
    return str(proxy.url)


async def _append_history(
    record: _utils_fluxdown_cli.FluxdownDownloadRecord,
    *,
    write_history: HistoryWriter | None,
) -> None:
    """历史写入失败不影响下载；取消异常继续交给调用方处理。"""
    if write_history is None:
        return
    try:
        await write_history(record)
    except Exception as exc:
        logger.warning(f"写入下载历史失败: {type(exc).__name__}")
