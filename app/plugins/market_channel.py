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


"""插件市场实时消息通道。

页面初始快照由 ``GET /api/plugins/market/snapshot`` 提供；主 WebSocket
只处理安装、卸载和安装状态查询，并推送对应的实时进度与结果。
"""

import asyncio
from pathlib import Path

from pydantic import ValidationError

from app.core.ws import Dispatcher, Publisher, protocol
from app.models.schema import (
    WSEnvelope,
    WSMarketErrorData,
    WSPluginInstalledSyncData,
    WSPluginInstallProgressData,
    WSPluginOperationResultData,
    WSPluginPackageRequestData,
)
from app.plugins import PluginManager
from app.plugins.market import collect_installed_distribution_names
from app.utils.logger import get_logger

logger = get_logger("插件市场通道")

_plugin_operation_lock = asyncio.Lock()
_registered = False


def _normalize_distribution_name(name: str) -> str:
    return str(name or "").strip().lower().replace("-", "_")


def _request_id(envelope: WSEnvelope) -> str | None:
    value = envelope.data.get("requestId")
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


async def _send_market_error(
    message: str,
    *,
    request_id: str | None = None,
) -> None:
    await Publisher.send(
        id=protocol.ID_PLUGIN_MARKET,
        type=protocol.MARKET_ERROR,
        data=WSMarketErrorData(requestId=request_id, message=message),
    )


def _parse_package_request(
    envelope: WSEnvelope,
) -> WSPluginPackageRequestData | None:
    try:
        request = WSPluginPackageRequestData.model_validate(envelope.data)
    except ValidationError:
        return None
    request.package = request.package.strip()
    request.requestId = request.requestId.strip() if request.requestId else None
    return request


async def _push_installed_sync(
    package_name: str,
    *,
    request_id: str | None = None,
) -> None:
    plugins_dir = Path.cwd() / "plugins"
    installed_names = collect_installed_distribution_names(plugins_dir=plugins_dir)
    normalized = _normalize_distribution_name(package_name)
    await Publisher.send(
        id=protocol.ID_PLUGIN_MARKET,
        type=protocol.PLUGIN_INSTALLED_SYNC,
        data=WSPluginInstalledSyncData(
            requestId=request_id,
            package=package_name,
            installed=normalized in installed_names,
        ),
    )


async def _handle_install_request(envelope: WSEnvelope) -> None:
    request = _parse_package_request(envelope)
    if request is None or not request.package:
        await _send_market_error(
            "安装请求缺少 package",
            request_id=_request_id(envelope),
        )
        return

    await Publisher.send(
        id=protocol.ID_PLUGIN_MARKET,
        type=protocol.PLUGIN_INSTALL_PROGRESS,
        data=WSPluginInstallProgressData(
            requestId=request.requestId,
            package=request.package,
            progress=5,
            stage="queued",
        ),
    )

    async with _plugin_operation_lock:
        await Publisher.send(
            id=protocol.ID_PLUGIN_MARKET,
            type=protocol.PLUGIN_INSTALL_PROGRESS,
            data=WSPluginInstallProgressData(
                requestId=request.requestId,
                package=request.package,
                progress=30,
                stage="installing",
            ),
        )
        try:
            await PluginManager.install_plugin_package(request.package)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            await Publisher.send(
                id=protocol.ID_PLUGIN_MARKET,
                type=protocol.PLUGIN_INSTALL_RESULT,
                data=WSPluginOperationResultData(
                    requestId=request.requestId,
                    status="error",
                    message=f"安装失败: {type(error).__name__}: {error}",
                    package=request.package,
                    success=False,
                ),
            )
        else:
            await Publisher.send(
                id=protocol.ID_PLUGIN_MARKET,
                type=protocol.PLUGIN_INSTALL_PROGRESS,
                data=WSPluginInstallProgressData(
                    requestId=request.requestId,
                    package=request.package,
                    progress=100,
                    stage="completed",
                ),
            )
            await Publisher.send(
                id=protocol.ID_PLUGIN_MARKET,
                type=protocol.PLUGIN_INSTALL_RESULT,
                data=WSPluginOperationResultData(
                    requestId=request.requestId,
                    message=f"安装成功: {request.package}",
                    package=request.package,
                    success=True,
                ),
            )

        await _push_installed_sync(
            request.package,
            request_id=request.requestId,
        )


async def _handle_uninstall_request(envelope: WSEnvelope) -> None:
    request = _parse_package_request(envelope)
    if request is None or not request.package:
        await _send_market_error(
            "卸载请求缺少 package",
            request_id=_request_id(envelope),
        )
        return

    async with _plugin_operation_lock:
        try:
            await PluginManager.uninstall_plugin_package(request.package)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            result = WSPluginOperationResultData(
                requestId=request.requestId,
                status="error",
                message=f"卸载失败: {type(error).__name__}: {error}",
                package=request.package,
                success=False,
            )
        else:
            result = WSPluginOperationResultData(
                requestId=request.requestId,
                message=f"卸载成功: {request.package}",
                package=request.package,
                success=True,
            )

        await Publisher.send(
            id=protocol.ID_PLUGIN_MARKET,
            type=protocol.PLUGIN_UNINSTALL_RESULT,
            data=result,
        )
        await _push_installed_sync(
            request.package,
            request_id=request.requestId,
        )


async def _handle_installed_request(envelope: WSEnvelope) -> None:
    request = _parse_package_request(envelope)
    if request is None or not request.package:
        await _send_market_error(
            "installed 查询缺少 package",
            request_id=_request_id(envelope),
        )
        return
    await _push_installed_sync(
        request.package,
        request_id=request.requestId,
    )


def register() -> None:
    """注册插件市场实时消息处理器（应用启动时调用一次）。"""

    global _registered
    if _registered:
        return
    _registered = True

    Dispatcher.register(
        protocol.ID_PLUGIN_MARKET,
        protocol.PLUGIN_INSTALL_REQUEST,
        _handle_install_request,
    )
    Dispatcher.register(
        protocol.ID_PLUGIN_MARKET,
        protocol.PLUGIN_UNINSTALL_REQUEST,
        _handle_uninstall_request,
    )
    Dispatcher.register(
        protocol.ID_PLUGIN_MARKET,
        protocol.PLUGIN_INSTALLED_REQUEST,
        _handle_installed_request,
    )
    logger.info("插件市场实时消息处理器已注册")
