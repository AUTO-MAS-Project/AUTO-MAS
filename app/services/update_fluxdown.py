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

根据 ``GlobalConfig.Update.Downloader`` 选择走 FluxDown 还是回退到
``update_transport.download_file`` 的内置 httpx 实现，不持有 Mirror 酱逻辑——
Mirror 酱源（临时授权 URL + 短期 token）在本文件里一律跳过 FluxDown，直接走 httpx。

调用方替换方式：
    # 原来：
    from app.services.update_transport import download_file
    size = await download_file(url, dest, timeout=...)

    # 现在：
    from app.services.update_fluxdown import download_file
    size = await download_file(url, dest, timeout=...)
    # 签名完全一致，内部自动按配置分发
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import httpx

from app.core import Config
from app.models.config.setting import FluxdownRecord
from app.services.update_transport import DownloadProgress
from app.services.update_transport import download_file as _httpx_download
from app.utils.fluxdown_cli import (
    FluxdownCancelUnconfirmed,
    FluxdownDownloadRecord,
    fluxdown_download,
    fluxdown_find_cli,
    fluxdown_server_available,
    fluxdown_server_download,
    fluxdown_server_forget,
    fluxdown_server_mark_failure,
    fluxdown_server_task_safe_to_overwrite,
)
from app.utils.logger import get_logger

logger = get_logger("FluxDown")

# 用户重试多少次仍失败后，在失败提示里建议改用内置 httpx
_RESUMABLE_HINT_THRESHOLD = 3


async def download_file(
    url: str,
    destination: Path,
    *,
    timeout: float,
    proxy: httpx.Proxy | None = None,
    progress: DownloadProgress | None = None,
    downloader: str | None = None,
    source: str | None = None,
) -> int:
    """根据 ``Update.Downloader`` 分发下载：FluxDown 或内置 httpx。

    FluxDown 链路：server 模式（断点续传）→ --local（仅 server 异常）→ httpx。
    server 任务级失败（超时/断网/任务 failed）保留 task 映射并抛
    :class:`FluxdownResumableError`，上层重试时自动 resume 续传，不会降级丢弃
    已下分段；连续重试仍失败由上层在最终失败提示里建议改用 httpx（见
    ``app/services/update.py``），--local 只兜 server 进程异常，不兜网络失败。

    ``downloader`` 参数允许上层绕过配置直接指定（"builtin" / "fluxdown"），
    用于"重试 N 次失败后改用 httpx"这类显式降级。

    ``source`` 为任务启动时冻结的来源，缺省才回落到 ``Update.Source`` 的实时
    配置。来源随任务冻结，避免用户中途改设置后把短期授权 URL 交给 FluxDown。

    Mirror 酱源强制跳过 FluxDown（大小写不敏感）：Mirror 酱用临时授权 URL +
    CDN 多，FluxDown 的 Range 续传可能和短期 token 冲突。
    """
    explicit_builtin = downloader == "builtin"
    downloader = downloader or Config.setting.Update.Downloader
    # 入参优先；只有调用方未冻结来源时才读实时配置
    frozen_source = (
        source if source is not None else str(Config.setting.Update.Source or "")
    )
    segments = int(Config.setting.Update.FluxdownSegments)
    proxy_str = _proxy_to_str(proxy)

    # Mirror 酱或无 FluxDown 需求 → 直接走 httpx
    if downloader != "fluxdown" or frozen_source.lower() == "mirrorchyan":
        if downloader == "fluxdown":
            logger.info("Mirror 酱源跳过 FluxDown,走内置 httpx 下载")
        # 无论是显式选内置还是配置默认走内置，只要此前可能经 FluxDown 下载过
        # 同一 (url, destination)，都需先确认旧 server 任务已停止再覆写；
        # 显式内置成功后再清理映射，避免残留任务在下次同 url 下载时被无谓 resume
        cli = fluxdown_find_cli(str(Config.setting.Update.FluxdownPath or ""))
        if cli is not None:
            await _ensure_can_downgrade(
                cli,
                url,
                destination,
                segments=segments,
                proxy_str=proxy_str,
                action="改用内置 httpx 下载",
            )
        size = await _httpx_download(
            url, destination, timeout=timeout, proxy=proxy, progress=progress
        )
        if explicit_builtin:
            # 用户多次失败后显式选择 httpx 并下载成功：清掉 FluxDown 任务映射,
            # 避免残留任务在下次同 url 下载时被无谓 resume
            if cli is not None:
                fluxdown_server_forget(cli, url, destination)
                logger.info(
                    "已按用户选择使用内置 httpx 完成下载,清理 FluxDown 任务映射"
                )
        return size

    # ---- FluxDown 路径 ----
    cli_path = fluxdown_find_cli(str(Config.setting.Update.FluxdownPath or ""))
    if cli_path is None:
        # CLI 不存在 → 回退 httpx
        logger.warning("未找到 FluxDown CLI,回退内置 httpx 下载")
        return await _httpx_download(
            url, destination, timeout=timeout, proxy=proxy, progress=progress
        )

    try:
        return await _download_via_fluxdown(
            url, destination, cli_path, timeout, proxy, progress
        )
    except FluxdownCancelUnconfirmed:
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
        )
        await _append_history(
            FluxdownDownloadRecord(
                url=url,
                destination=str(destination),
                size=0,
                duration_ms=0,
                segments=segments,
                proxy=proxy_str,
                checksum=None,
                status="fluxdown_fallback",
                error=f"FluxDown 失败，回退 httpx: {exc}",
            )
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
) -> int:
    """FluxDown 下载：优先 server 模式（断点续传），仅 server 进程异常落 --local。

    server 任务级失败（超时/断网/任务 failed）抛 :class:`FluxdownResumableError`
    并保留 task 映射，上层重试自动 resume；server 不可用/启动失败/status 查询
    失败（进程级异常）才落 --local，且落 --local 前必须经
    :func:`_ensure_can_downgrade` 确认旧任务已停止。--local 不再兜网络失败，
    避免删掉已下分段。
    """
    segments = int(Config.setting.Update.FluxdownSegments)
    proxy_str = _proxy_to_str(proxy)
    server_on = bool(Config.setting.Update.FluxdownServerMode)

    if server_on and fluxdown_server_available(cli_path, enabled=True):
        try:
            size, record = await fluxdown_server_download(
                url,
                destination,
                cli_exe=cli_path,
                segments=segments,
                proxy=proxy_str,
                timeout=timeout,
                progress=progress,
            )
            await _append_history(record)
            # 下载成功 → 清映射（MAS 后续哈希校验如失败会重下，重新 add）
            fluxdown_server_forget(cli_path, url, destination)
            return size
        except FluxdownCancelUnconfirmed:
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
                )
                logger.warning(f"server 进程异常,降级 --local 一次性下载: {msg}")
            else:
                # 任务级失败（超时/断网/任务 failed/add probe 失败）→ 保留映射，抛可续传错误；
                # 累计中断次数，达到阈值后在错误信息里建议改用内置 httpx
                count = fluxdown_server_mark_failure(cli_path, url, destination)
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
                    FluxdownDownloadRecord(
                        url=url,
                        destination=str(destination),
                        size=0,
                        duration_ms=0,
                        segments=segments,
                        proxy=proxy_str,
                        checksum=None,
                        status="interrupted",
                        error=f"下载中断（第 {count} 次）,任务已保留可续传: {msg}",
                    )
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
    )
    size, record = await fluxdown_download(
        url,
        destination,
        cli_exe=cli_path,
        segments=segments,
        proxy=proxy_str,
        checksum=None,  # 让 MAS 自己做最终校验，FluxDown 只负责下载
        timeout=timeout,
        progress=progress,
    )
    await _append_history(record)
    return size


async def _can_downgrade(cli_path: Path, url: str, destination: Path) -> bool:
    """是否可安全降级改写目标文件：旧 FluxDown 任务已确认停止/不存在。

    统一 ``--local`` 与内置 httpx 两条降级路径的门槛，避免旧 daemon 仍在写
    同一目标时启动第二个写入者。
    """
    return await asyncio.to_thread(
        fluxdown_server_task_safe_to_overwrite, cli_path, url, destination
    )


async def _block_downgrade(
    cli_path: Path,
    url: str,
    destination: Path,
    *,
    segments: int,
    proxy_str: str | None,
    detail: str,
) -> None:
    """任务未确认停止：记一次失败、留中断记录并抛可续传错误，禁止启动新写入者。"""
    count = fluxdown_server_mark_failure(cli_path, url, destination)
    hint = (
        "；已多次重试仍失败，可在设置中将下载器改为内置（httpx）后重试"
        if count >= _RESUMABLE_HINT_THRESHOLD
        else ""
    )
    logger.warning(f"server 任务未确认停止（第 {count} 次）, 保留映射待续传: {detail}")
    await _append_history(
        FluxdownDownloadRecord(
            url=url,
            destination=str(destination),
            size=0,
            duration_ms=0,
            segments=segments,
            proxy=proxy_str,
            checksum=None,
            status="interrupted",
            error=f"server 任务未确认停止（第 {count} 次）: {detail}",
        )
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
    )


class FluxdownResumableError(RuntimeError):
    """FluxDown server 任务级失败（网络中断/超时/任务 failed），task 已保留可续传。

    上层应原地重试（同一 url+destination 会走 resume）；连续重试仍失败时
    在最终失败提示中建议改用内置 httpx 重新下载（downloader="builtin"），
    不要落 --local（会删掉已下载的分段文件）。
    """


def _proxy_to_str(proxy: httpx.Proxy | None) -> str | None:
    """httpx.Proxy → 字符串（FluxDown CLI --proxy 参数需要）。"""
    if proxy is None:
        return None
    try:
        return str(proxy.url)
    except Exception:
        return None


_HISTORY_LOCK = threading.Lock()


async def _append_history(record: FluxdownDownloadRecord) -> None:
    """把下载记录追加到 Update.LastUpdateHistory，保留最近 50 条。

    配置模型返回内部列表引用：必须先复制再追加，否则原地 append 后
    提交时可能因值未变化跳过落盘，重启后历史丢失。
    """
    try:
        with _HISTORY_LOCK:
            history = list(Config.setting.Update.LastUpdateHistory or [])
            history.append(FluxdownRecord(**record.to_dict()))
            await Config.setting.update(
                type(Config.setting).model_validate(
                    {"Update": {"LastUpdateHistory": history[-50:]}}
                ),
                check_visibility=False,
            )
    except Exception:
        # 历史写入失败不能阻塞主流程
        pass
