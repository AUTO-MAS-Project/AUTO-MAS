#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""装配更新器与下载入口，连接宿主配置和下载历史，后续转交给前端，后端仅抽象出下载逻辑"""

from pathlib import Path

import httpx

from app.config import config_manager
from app.core import Config
from app.models.config.setting import FluxdownRecord
from app.services import update as _service_update
from app.services.common.update import fluxdown as _service_update_fluxdown
from app.services.common.update import transport as _service_update_transport
from app.utils import fluxdown_cli as _utils_fluxdown_cli


async def _write_history(record: _utils_fluxdown_cli.FluxdownDownloadRecord) -> None:
    """串行追加历史并保留最近 50 条，复制列表后整体提交。"""
    # 读、改、提交共用配置事务，避免并发下载覆盖历史，也不持线程锁等待异步提交。
    async with config_manager.transaction():
        # 旧版本记录也去除 userinfo，避免下次保存继续保留历史代理凭据。
        history = [
            FluxdownRecord(
                **_utils_fluxdown_cli.FluxdownDownloadRecord(
                    **item.model_dump()
                ).to_dict()
            )
            for item in (Config.setting.Update.LastUpdateHistory or [])
        ]
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
    progress: _service_update_transport.DownloadProgress | None = None,
    downloader: str | None = None,
    source: str | None = None,
) -> int:
    """每次尝试读取默认选项，保留任务冻结的来源与显式下载器覆盖。"""
    update = Config.setting.Update
    return await _service_update_fluxdown.download_file(
        url,
        destination,
        timeout=timeout,
        proxy=proxy,
        progress=progress,
        downloader=downloader,
        source=source,
        options=_service_update_fluxdown.FluxdownOptions(
            downloader=update.Downloader,
            source=str(update.Source or ""),
            cli_path=str(update.FluxdownPath or ""),
            segments=int(update.FluxdownSegments),
            server_mode=bool(update.FluxdownServerMode),
            cli_search_dirs=(
                Config.install_path / "res" / "fluxdown-cli",
                Config.resource_path / "fluxdown-cli",
            ),
        ),
        write_history=_write_history,
    )


Updater = _service_update.UpdateHandler(download=download_file)


__all__ = ["Updater"]
