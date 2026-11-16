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
import tomllib
from ipaddress import ip_address
from typing import (
    List,
    Optional,
)
from urllib.parse import urlsplit

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import (
    BaseModel,
    Field,
)

from app.core import Config
from app.models.schema import OutBase
from app.services.common.update import fluxdown_install as _fluxdown_install
from app.utils import fluxdown_cli as _utils_fluxdown_cli
from app.utils import get_logger


class CoreUpgradePrecheckIn(BaseModel):
    version: str
    project: str = Field(min_length=1, description="目标版本的完整 pyproject.toml")
    lockfile: str = Field(min_length=1, description="同一目标版本的 uv.lock")
    python_version: str = Field(
        pattern=r"^\d+\.\d+\.\d+$",
        description="目标版本 .python-version 中的精确 Python 版本",
    )


class CoreUpgradeConflict(BaseModel):
    plugin_name: str
    distribution: str
    required: str
    proposed: str
    message: str


class CoreUpgradePrecheckOut(OutBase):
    compatible: bool | None = Field(
        description="true 表示兼容，false 表示依赖无解，null 表示检查未完成"
    )
    conflicts: list[CoreUpgradeConflict] = Field(default_factory=list)


class FluxdownCandidateOut(BaseModel):
    """一个候选 FluxDown 可执行文件。"""

    path: str = Field(..., description="可执行文件完整路径")
    is_portable_cli: bool = Field(
        ..., description="是否为带 portable 标记的 CLI 便携版"
    )
    has_cli: bool = False
    has_server: bool = False
    has_desktop: bool = False
    complete: bool = False
    missing: str = ""


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


@router.post("/precheck", response_model=CoreUpgradePrecheckOut, tags=["Get"])
async def precheck_core_upgrade(
    body: CoreUpgradePrecheckIn, request: Request
) -> CoreUpgradePrecheckOut:
    """在插件状态锁内检查目标 core 版本与插件依赖是否兼容，返回准入结论和冲突明细供前端决策。"""
    from dataclasses import asdict

    from packaging.specifiers import SpecifierSet

    from app.core import Plugin
    from app.plugin.errors import PluginError
    from app.plugin.uv import precheck_core_bump
    from app.plugin.uv.precheck import locked_dependencies
    from app.utils.common.tools import to_pep440

    owner = asyncio.current_task()
    assert owner is not None

    async def cancel_on_disconnect() -> None:
        """请求断开时取消所属预检，让锁等待和解析进程沿原调用栈完成回收。"""
        while not await request.is_disconnected():
            await asyncio.sleep(0.1)
        owner.cancel()

    watcher = asyncio.create_task(cancel_on_disconnect())
    try:
        async with Plugin._hold():
            project = tomllib.loads(body.project)["project"]
            if project["version"] != to_pep440(body.version) or not SpecifierSet(
                project["requires-python"]
            ).contains(body.python_version):
                raise ValueError("目标版本或 Python 声明不一致")
            dependencies = await locked_dependencies(
                project=body.project,
                lockfile=body.lockfile,
                python_version=body.python_version,
            )
            # 导入失败的包仍保留在共享环境中，预检不能只使用成功加载的运行时列表。
            conflicts = await precheck_core_bump(
                body.version,
                plugins=Config.plugin_registry.values(),
                dependencies=dependencies,
                python_version=body.python_version,
            )
    except (PluginError, ValueError, KeyError, TypeError, OSError):
        logger.exception("目标运行环境兼容性检查未完成")
        return CoreUpgradePrecheckOut(
            code=503,
            status="error",
            message="兼容性检查未完成，请检查网络、插件文件及目标版本信息后重试",
            compatible=None,
        )
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
    return CoreUpgradePrecheckOut(
        compatible=not conflicts,
        conflicts=[CoreUpgradeConflict(**asdict(item)) for item in conflicts],
    )


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
            _utils_fluxdown_cli.fluxdown_detect,
            configured,
            managed_dir=Config.data_path / "fluxdown" / "bin",
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
