#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""脚本更新的统一异步入口与下载策略；适配器负责版本判断和安装。"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import ParamSpec, TypeVar

import httpx

from app.core import Config
from app.core.update import download_file
from app.services.update_transport import BuiltinDownload, DownloadProgress
from app.utils import get_logger

logger = get_logger("脚本更新")
P = ParamSpec("P")
T = TypeVar("T")


@dataclass(frozen=True)
class ScriptUpdateRequest:
    """一次更新操作的调度身份；不携带凭据、配置或预先启动的协程。"""

    script_id: str
    script_type: str
    engine: str | None = None


async def run_script_update(
    request: ScriptUpdateRequest,
    operation: Callable[P, Awaitable[T]],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """所有脚本更新共用的异步入口，完整等待检查、下载及安装结束。

    后续队列在此调度尚未调用的 operation；各适配器继续负责目录锁、安装
    安全边界和失败回退。异常和取消原样交还调用方，不在此启动后台任务，
    也不提前释放安装目录的使用权。
    """
    logger.debug(f"开始脚本更新：{request.script_type} {request.engine or ''}")
    return await operation(*args, **kwargs)


def script_downloader(source: str) -> str:
    """FluxDown 只决定 GitHub 包的下载方式，不决定是否接管更新。"""
    return (
        "fluxdown"
        if source.casefold() == "github" and Config.setting.Update.FluxdownTakeoverAll
        else "builtin"
    )


async def download_script_package(
    url: str,
    destination: Path,
    *,
    source: str,
    timeout: float,
    proxy: httpx.Proxy | None = None,
    progress: DownloadProgress | None = None,
    http_download: BuiltinDownload | None = None,
) -> int:
    """复用 MAS 下载器与网络代理，取消后等待后台写入权收敛。

    来源在本次下载开始时冻结。Mirror 酱始终使用内置下载器；认证代理的
    安全回退仍由下载分发层处理。调用方只在本函数成功后校验、发布和安装。
    """
    return await download_file(
        url,
        destination,
        timeout=timeout,
        proxy=proxy if proxy is not None else Config.proxy,
        progress=progress,
        source=source,
        downloader=script_downloader(source),
        http_download=http_download,
    )
