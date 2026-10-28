#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""运行前下载 MAA 官方完整包；校验、解压和安装交给 MAA。

Mirror 酱仅提供版本元数据，不申请临时下载地址、不消耗 CDK 下载额度。
包从对应 GitHub Release 获取，复用 MAS 下载器的续传、回退和历史记录。
待安装字段复用现有透传入口；不修改上游更新器，也不解析更新包内容。
"""

import asyncio
import time
from pathlib import Path

from app.core import Config
from app.core.update import download_file
from app.models.config import MaaConfig
from app.services.update_fluxdown import FluxdownResumableError
from app.services.update_transport import DownloadProgress, request_mirror_resource
from app.utils import fluxdown_cli as _utils_fluxdown_cli
from app.utils import get_logger

from .software_package import (
    has_delegated_update_failure,
    read_pending_update,
    write_pending_update,
)
from .software_update import (
    compare_versions,
    parse_version,
    read_installed_release,
    resolve_update_channel,
)
from .update_credentials import use_maa_fluxdown_update

logger = get_logger("MAA 更新下载代理")
_QUERY_TTL = 10 * 60
_latest_versions: dict[tuple[str, str], tuple[float, str]] = {}


async def prepare_maa_fluxdown_update(
    maa_root: Path,
    *,
    config: MaaConfig,
    config_dir: Path,
    progress: DownloadProgress | None = None,
) -> str | None:
    """下载并登记官方包，返回目标版本；失败或不接管时返回 None。

    调用方持有安装访问锁，且须在启动账号任务前调用官方 update_maa()。
    下载失败保留分段供 FluxDown 续传；主动取消继续向上传播。
    """
    if not use_maa_fluxdown_update(
        config, config_dirs=[config_dir, maa_root / "config"]
    ):
        return None
    try:
        release = read_installed_release(maa_root)
        if release is None or has_delegated_update_failure(maa_root):
            return None
        current, arch = release
        channel = resolve_update_channel(current, [config_dir, maa_root / "config"])
        if channel is None:
            return None
        # 原生下载或上次中断留下的包仍走已有交接流程，不覆盖它的登记。
        _, pending = read_pending_update(maa_root)
        if pending and (maa_root / pending).is_file():
            logger.info("MAA 已有待安装包，保留原生更新登记")
            return None
        key = (arch, channel)
        cached = _latest_versions.get(key)
        if cached and time.monotonic() - cached[0] < _QUERY_TTL:
            latest = cached[1]
        else:
            logger.info(f"正在通过 Mirror 酱检查 MAA 更新（{channel}/{arch}）")
            query_started = time.monotonic()
            payload = await request_mirror_resource(
                "MAA",
                params={"os": "win", "arch": arch, "channel": channel},
                proxy=Config.proxy,
                timeout=10,
            )
            data = payload.get("data")
            latest = data.get("version_name") if isinstance(data, dict) else None
            if not isinstance(latest, str) or parse_version(latest) is None:
                raise ValueError("Mirror 酱未返回可识别的 MAA 版本")
            # 较慢的旧响应不能覆盖并发请求已经确认的较新版本。
            newer = _latest_versions.get(key)
            if (
                newer
                and newer[0] >= query_started
                and compare_versions(parse_version(newer[1]), parse_version(latest)) > 0
            ):
                latest = newer[1]
            else:
                _latest_versions[key] = (time.monotonic(), latest)
        target_version, current_version = parse_version(latest), parse_version(current)
        if target_version is None or current_version is None:
            raise ValueError("无法比较 MAA 版本")
        if compare_versions(target_version, current_version) <= 0:
            logger.info(f"MAA 已是最新版本（{current}，{channel} 通道）")
            return None

        # 官方完整包的规范名称；版本经过 SemVer 解析，不接受路径或任意 URL。
        tag = latest if latest.startswith("v") else f"v{latest}"
        filename = f"MAA-{tag}-win-{arch}.zip"
        destination = maa_root / filename
        part = maa_root / f"{filename}.part"
        url = f"https://github.com/MaaAssistantArknights/MaaAssistantArknights/releases/download/{tag}/{filename}"
        logger.info(f"开始下载 MAA {latest}，完成后交给官方更新器安装")
        for attempt in range(3):
            if not use_maa_fluxdown_update(
                config, config_dirs=[config_dir, maa_root / "config"]
            ):
                logger.info("MAA 更新来源已变更，保留 Mirror 酱或原生更新路径")
                return None
            try:
                await download_file(
                    url,
                    part,
                    timeout=30 * 60,
                    proxy=Config.proxy,
                    progress=progress,
                    downloader="fluxdown",
                    source="GitHub",
                )
                break
            except FluxdownResumableError:
                if attempt == 2:
                    raise
                logger.warning("MAA 更新下载中断，正在重试续传")
                await asyncio.sleep(1)
        # 仅在下载器确认完成后发布文件；未确认停止的任务仍保留 .part 所有权。
        if not use_maa_fluxdown_update(
            config, config_dirs=[config_dir, maa_root / "config"]
        ):
            logger.info("下载期间更新来源已变更，保留文件但不登记安装")
            return None
        part.replace(destination)
        write_pending_update(
            maa_root, version=latest, package=str(destination.resolve())
        )
        logger.info(f"MAA {latest} 下载完成，已交接本地更新包")
        return latest
    except asyncio.CancelledError:
        raise
    except _utils_fluxdown_cli.FluxdownCancelUnconfirmed:
        raise  # 用户已取消但 daemon 尚未确认停止，不能继续启动脚本。
    except Exception as error:
        logger.warning(f"MAA 更新下载代理失败，保留原生更新流程: {error}")
        return None
