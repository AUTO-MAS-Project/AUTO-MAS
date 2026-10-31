#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
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


import asyncio
import os
import secrets
from ipaddress import ip_address
from typing import (
    Dict,
    List,
    Optional,
)
from urllib.parse import urlsplit

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import (
    BaseModel,
    Field,
)

from app.core import Config, Updater
from app.models.schema import OutBase, UpdateDownloadSnapshot
from app.services.common.update import fluxdown_install as _fluxdown_install
from app.utils import fluxdown_cli as _utils_fluxdown_cli
from app.utils import get_logger


class UpdateCheckIn(BaseModel):
    current_version: str = Field(..., description="当前前端版本号")
    if_force: bool = Field(default=False, description="是否强制拉取更新信息")


class UpdateCheckOut(OutBase):
    if_need_update: bool = Field(..., description="是否需要更新前端")
    latest_version: str = Field(..., description="最新前端版本号")
    update_info: Dict[str, Dict[str, List[str]]] = Field(
        ...,
        description="版本更新信息：版本号 -> 分类 -> 条目，只含比当前版本新的版本段，按版本号降序",
    )


class FluxdownCandidateOut(BaseModel):
    """一个候选 FluxDown 可执行文件。"""

    path: str = Field(..., description="可执行文件完整路径")
    is_portable_cli: bool = Field(
        ..., description="是否为带 portable 标记的 CLI 便携版"
    )


class FluxdownDetectOut(OutBase):
    """FluxDown 全盘检测结果。"""

    path: Optional[str] = Field(
        None, description="择优后的 FluxDown 路径；未找到为 None"
    )
    is_portable_cli: bool = Field(False, description="选中项是否为 CLI 便携版")
    only_full_warning: bool = Field(
        False,
        description="设备上没有任何 CLI 便携版、选中项是全量版时为 True（前端显示污染风险警告）",
    )
    scanned_drives: List[str] = Field(default_factory=list, description="扫描过的盘符")
    candidates: List[FluxdownCandidateOut] = Field(
        default_factory=list, description="全部候选，按择优顺序，最多 8 条"
    )


class FluxdownReleaseOut(OutBase):
    """FluxDown 最新 Release 的直链信息，供设置页展示。"""

    version: str = Field("", description="版本号（不含 v 前缀）")
    tag: str = Field("", description="Release tag")
    cli_url: str = Field("", description="CLI 包 GitHub 直链")
    server_url: str = Field("", description="Server 包 GitHub 直链")
    release_page: str = Field("", description="GitHub Release 页面")
    mirrors: List[str] = Field(
        default_factory=list, description="可用下载镜像标识，按推荐顺序"
    )


class FluxdownInstallIn(BaseModel):
    mirror: str = Field(
        default="auto",
        description="下载镜像：auto / official / ghproxy / ghfast / github",
    )


class FluxdownInstallOut(OutBase):
    """MAS 代为下载并安装 FluxDown 的结果。"""

    version: str = Field("", description="已安装版本")
    path: str = Field("", description="安装目录，已写入 Update.FluxdownPath")
    cli_size: int = Field(0, description="CLI 包字节数")
    server_size: int = Field(0, description="Server 包字节数")


router = APIRouter(prefix="/api/update", tags=["软件更新"])
logger = get_logger("软件更新 API")


@router.get(
    "/download/status",
    tags=["Get"],
    summary="获取更新下载初始快照",
    response_model=UpdateDownloadSnapshot,
    status_code=200,
)
async def get_update_download_status() -> UpdateDownloadSnapshot:
    """返回当前下载权威状态；WS 只承载后续进度与终态事件。"""

    return Updater.get_download_snapshot()


@router.post(
    "/check",
    tags=["Get"],
    summary="检查更新",
    response_model=UpdateCheckOut,
    status_code=200,
)
async def check_update(version: UpdateCheckIn = Body(...)) -> UpdateCheckOut:

    try:
        if_need, latest_version, update_info = await Updater.check_update(
            current_version=version.current_version, if_force=version.if_force
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"check_update失败: {type(e).__name__}: {e}")
        return UpdateCheckOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            if_need_update=False,
            latest_version="",
            update_info={},
        )
    return UpdateCheckOut(
        if_need_update=if_need, latest_version=latest_version, update_info=update_info
    )


@router.post(
    "/download",
    tags=["Action"],
    summary="下载更新",
    response_model=OutBase,
    status_code=200,
)
async def download_update(
    target_version: str | None = Query(default=None, alias="version"),
    downloader: str | None = Query(default=None),
) -> OutBase:

    try:
        if not await Updater.start_download(
            target_version=target_version, downloader=downloader
        ):
            return OutBase(
                code=409,
                status="error",
                message="已有更新任务在进行中, 请勿重复操作",
            )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"download_update失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/cancel-download",
    tags=["Action"],
    summary="取消下载更新",
    response_model=OutBase,
    status_code=200,
)
async def cancel_update_download() -> OutBase:

    try:
        if not await Updater.cancel_download():
            return OutBase(
                code=409, status="error", message="当前没有正在进行中的下载任务"
            )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"cancel_update_download失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500,
            status="error",
            message=f"取消更新下载失败: {type(e).__name__}: {str(e)}",
        )
    return OutBase()


@router.post(
    "/switch-to-cnb",
    tags=["Action"],
    summary="切换下载源到 CNB",
    response_model=OutBase,
    status_code=200,
)
async def switch_update_download_to_cnb() -> OutBase:

    try:
        if not await Updater.switch_to_cnb():
            return OutBase(
                code=409,
                status="error",
                message="当前无法切换到 CNB 下载源, 请确认正在从 GitHub 源下载",
            )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"switch_update_download_to_cnb失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500,
            status="error",
            message=f"切换至 CNB 源失败: {type(e).__name__}: {str(e)}",
        )
    return OutBase()


@router.post(
    "/install",
    tags=["Action"],
    summary="安装更新",
    response_model=OutBase,
    status_code=200,
)
async def install_update() -> OutBase:

    try:
        task = asyncio.create_task(Updater.install_update())
        Config.temp_task.append(task)
        task.add_done_callback(lambda t: Config.temp_task.remove(t))
    except Exception as e:
        logger.opt(exception=True).warning(
            f"install_update失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.get(
    "/fluxdown/detect",
    tags=["Get"],
    summary="全盘检测 FluxDown 并择优推荐",
    response_model=FluxdownDetectOut,
    status_code=200,
)
async def detect_fluxdown() -> FluxdownDetectOut:
    """CLI 便携版优先，其次同盘、就近、新目录；无 CLI 只有全量版时提示污染风险。"""

    try:
        configured = str(Config.setting.Update.FluxdownPath or "")
        result = await asyncio.to_thread(
            _utils_fluxdown_cli.fluxdown_detect, configured
        )
        return FluxdownDetectOut(**result)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"detect_fluxdown失败: {type(e).__name__}: {e}"
        )
        return FluxdownDetectOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )


@router.get(
    "/fluxdown/release",
    tags=["Get"],
    summary="获取 FluxDown 最新 Release 直链",
    response_model=FluxdownReleaseOut,
    status_code=200,
)
async def get_fluxdown_release() -> FluxdownReleaseOut:
    """用于设置页展示 CLI / Server 两个包的 GitHub 下载链接。"""

    try:
        release = await _fluxdown_install.fetch_latest_release(proxy=Config.proxy)
        return FluxdownReleaseOut(
            version=release.version,
            tag=release.tag,
            cli_url=release.cli_url,
            server_url=release.server_url,
            release_page=_fluxdown_install.RELEASE_PAGE,
            mirrors=list(_fluxdown_install.SUPPORTED_MIRRORS),
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_fluxdown_release失败: {type(e).__name__}: {e}"
        )
        return FluxdownReleaseOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            release_page=_fluxdown_install.RELEASE_PAGE,
            mirrors=list(_fluxdown_install.SUPPORTED_MIRRORS),
        )


def _require_local_install(request: Request) -> None:
    """验证主进程持有的安装凭据；回环和 Origin 检查仅作额外限制。"""

    token = os.environ.get("AUTO_MAS_INSTALL_TOKEN", "")
    authorization = request.headers.get("authorization", "")
    if not token or not secrets.compare_digest(
        authorization.encode(), f"Bearer {token}".encode()
    ):
        raise HTTPException(
            status_code=403,
            detail="安装请求未授权，请在 MAS 桌面客户端启动或重启后端后安装",
        )

    def is_local(host: str | None) -> bool:
        if host == "localhost":
            return True
        try:
            return ip_address(host or "").is_loopback
        except ValueError:
            return False

    origin = request.headers.get("origin")
    try:
        source = urlsplit(origin) if origin not in (None, "null") else None
        local_origin = source is None or (
            source.scheme in ("http", "https") and is_local(source.hostname)
        )
    except ValueError:
        local_origin = False
    if (
        request.client is None
        or not is_local(request.client.host)
        or not is_local(request.url.hostname)
        or not local_origin
    ):
        raise HTTPException(status_code=403, detail="FluxDown 安装仅允许本机客户端")


@router.post(
    "/fluxdown/install",
    dependencies=[Depends(_require_local_install)],
    tags=["Get"],
    summary="由 MAS 下载并安装 FluxDown CLI 与 Server",
    response_model=FluxdownInstallOut,
    status_code=200,
)
async def install_fluxdown(
    payload: FluxdownInstallIn = Body(...),
) -> FluxdownInstallOut:
    """静默下载两个发布包，校验后解压到 MAS 数据目录并写入 FluxdownPath。"""

    try:
        result = await _fluxdown_install.install_fluxdown(
            payload.mirror, proxy=Config.proxy
        )
        return FluxdownInstallOut(**result)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"install_fluxdown失败: {type(e).__name__}: {e}"
        )
        return FluxdownInstallOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
