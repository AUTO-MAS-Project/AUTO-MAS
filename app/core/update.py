#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""装配更新器与下载入口，连接宿主配置和下载历史。"""

from pathlib import Path

import httpx

from app.config import config_manager
from app.core import Config
from app.models.config.setting import FluxdownRecord
from app.services.update import UpdateHandler
from app.services.update_fluxdown import FluxdownOptions
from app.services.update_fluxdown import download_file as _download_file
from app.services.update_transport import DownloadProgress
from app.utils import fluxdown_cli as _utils_fluxdown_cli


async def _write_history(record: _utils_fluxdown_cli.FluxdownDownloadRecord) -> None:
    """串行追加历史并保留最近 50 条，复制列表后整体提交。"""
    # 读、改、提交共用配置事务，避免并发下载覆盖历史，也不持线程锁等待异步提交。
    async with config_manager.transaction():
        history = list(Config.setting.Update.LastUpdateHistory or [])
        history.append(FluxdownRecord(**record.to_dict()))
        await Config.setting.update(
            type(Config.setting).model_validate(
                {"Update": {"LastUpdateHistory": history[-50:]}}
            ),
            check_visibility=False,
        )


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
    """每次尝试读取默认选项，保留任务冻结的来源与显式下载器覆盖。"""
    update = Config.setting.Update
    return await _download_file(
        url,
        destination,
        timeout=timeout,
        proxy=proxy,
        progress=progress,
        downloader=downloader,
        source=source,
        options=FluxdownOptions(
            downloader=update.Downloader,
            source=str(update.Source or ""),
            cli_path=str(update.FluxdownPath or ""),
            segments=int(update.FluxdownSegments),
            server_mode=bool(update.FluxdownServerMode),
        ),
        write_history=_write_history,
    )


Updater = UpdateHandler(download=download_file)
