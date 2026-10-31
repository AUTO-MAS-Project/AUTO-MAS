#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""运行前下载 MAA 官方 OTA / 完整包；解压和安装交给 MAA。

无 CDK 时使用 MAA 官方发行清单，包从对应 GitHub Release 获取。
下载器独立跟随全局 FluxDown 接管开关，复用 MAS 的续传、回退和历史记录。
待安装字段复用现有透传入口；不修改上游更新器，也不解析更新包内容。
"""

import asyncio
import time
from pathlib import Path

import httpx

from app.core import Config
from app.core.update import download_file
from app.models.config import MaaConfig
from app.services.common.update import fluxdown as _service_update_fluxdown
from app.services.common.update import transport as _service_update_transport
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
)
from .update_credentials import use_maa_github_update

logger = get_logger("MAA 更新下载代理")
_latest_versions: dict[tuple[str, str], tuple[float, str]] = {}


async def request_maa_release(channel: str) -> dict:
    """读取与 MAA 本体一致的公开发行清单。"""
    async with httpx.AsyncClient(
        proxy=Config.proxy, timeout=10, follow_redirects=True
    ) as client:
        response = await client.get(
            f"https://api.maa.plus/MaaAssistantArknights/api/version/{channel}.json"
        )
        response.raise_for_status()
        release = response.json()
    if (
        not isinstance(release, dict)
        or parse_version(release.get("version", "")) is None
    ):
        raise ValueError("MAA 未返回可识别的发行版本")
    return release


async def query_latest_maa_version(
    arch: str, channel: str, *, github: bool = False
) -> str:
    """每次启动前重新查询；仅用并发结果防止慢响应覆盖较新版本。"""
    if github:
        return (await request_maa_release(channel))["version"]
    key = (arch, channel)
    logger.info(f"正在通过 Mirror 酱检查 MAA 更新（{channel}/{arch}）")
    query_started = time.monotonic()
    payload = await _service_update_transport.request_mirror_resource(
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
    return latest


async def _select_package(current: str, latest: str, arch: str, channel: str) -> str:
    """只选与已安装基线精确匹配的官方 OTA；没有该资产时回退完整包。"""
    tag = latest if latest.startswith("v") else f"v{latest}"
    baseline = current if current.startswith("v") else f"v{current}"
    full = f"MAA-{tag}-win-{arch}.zip"
    ota = f"MAAComponent-OTA-{baseline}_{tag}-win-{arch}.zip"
    release = await request_maa_release(channel)
    if release.get("version") != latest:
        raise RuntimeError("MAA 发行版本在查询期间发生变化，请重新运行")
    for asset in release.get("details", {}).get("assets", []):
        if asset.get("name", "").lower() == ota.lower():
            return ota
    return full


async def prepare_maa_fluxdown_update(
    maa_root: Path,
    *,
    config: MaaConfig,
    config_dir: Path,
    progress: _service_update_transport.DownloadProgress | None = None,
) -> str | None:
    """下载并登记官方包；无更新返回当前版本，不接管返回 None，失败阻止启动。

    调用方持有安装访问锁，且须在启动账号任务前调用官方 update_maa()。
    下载失败保留分段供 FluxDown 续传；主动取消继续向上传播。
    """
    if not use_maa_github_update(config, config_dirs=[config_dir, maa_root / "config"]):
        return None
    try:
        release = read_installed_release(maa_root)
        if release is None or has_delegated_update_failure(maa_root):
            raise RuntimeError("无法确认 MAA 安装状态，请先在 MAA 内完成修复")
        current, arch = release
        channel = config.Update.Channel
        # 原生下载或上次中断留下的包仍走已有交接流程，不覆盖它的登记。
        _, pending = read_pending_update(maa_root)
        if pending and (maa_root / pending).is_file():
            logger.info("MAA 已有待安装包，保留原生更新登记")
            raise RuntimeError("MAA 仍有未安装的更新包，请先完成安装")
        latest = await query_latest_maa_version(arch, channel, github=True)
        target_version, current_version = parse_version(latest), parse_version(current)
        if target_version is None or current_version is None:
            raise ValueError("无法比较 MAA 版本")
        if compare_versions(target_version, current_version) <= 0:
            if compare_versions(target_version, current_version) < 0:
                raise RuntimeError(
                    "当前 MAA 高于所选通道的最新版本，请切换通道或先手动安装该通道版本"
                )
            logger.info(f"MAA 已是最新版本（{current}，{channel} 通道）")
            return current

        # 只使用官方规范包名，不接受清单中的任意下载 URL。
        tag = latest if latest.startswith("v") else f"v{latest}"
        filename = await _select_package(current, latest, arch, channel)
        destination = maa_root / filename
        part = maa_root / f"{filename}.part"
        url = f"https://github.com/MaaAssistantArknights/MaaAssistantArknights/releases/download/{tag}/{filename}"
        logger.info(f"开始下载 MAA {latest}，完成后交给官方更新器安装")
        for attempt in range(3):
            if not use_maa_github_update(
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
                    downloader=(
                        "fluxdown"
                        if Config.setting.Update.FluxdownTakeoverAll
                        else "builtin"
                    ),
                    source="GitHub",
                )
                break
            except _service_update_fluxdown.FluxdownResumableError:
                if attempt == 2:
                    raise
                logger.warning("MAA 更新下载中断，正在重试续传")
                await asyncio.sleep(1)
        # 仅在下载器确认完成后发布文件；未确认停止的任务仍保留 .part 所有权。
        if not use_maa_github_update(
            config, config_dirs=[config_dir, maa_root / "config"]
        ):
            logger.info("下载期间更新来源已变更，保留文件但不登记安装")
            return None
        part.replace(destination)
        # 启动应用路径不再核对 OTA 的基线；登记前由持安装锁的调用方复核。
        if read_installed_release(maa_root) != release:
            raise RuntimeError("下载期间 MAA 安装版本发生变化，请重新运行")
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
        raise RuntimeError(f"MAA 更新准备失败: {error}") from error
