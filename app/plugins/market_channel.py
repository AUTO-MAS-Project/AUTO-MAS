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


"""插件市场消息通道

经主 WebSocket 连接处理插件市场业务（id=PluginMarket）：
市场快照查询、插件安装/卸载、安装状态同步。
"""

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.ws import Dispatcher, Publisher, protocol
from app.models.schema import WSEnvelope
from app.plugins import PluginManager
from app.plugins.market import (
    fetch_market_snapshot,
    collect_installed_distribution_names,
)
from app.utils.logger import get_logger

logger = get_logger("插件市场通道")

_plugin_operation_lock = asyncio.Lock()
_registered = False


def _normalize_distribution_name(name: str) -> str:
    return str(name or "").strip().lower().replace("-", "_")


async def _send_market_message(
    type: str,
    *,
    request_id: Optional[str] = None,
    status: str = "success",
    message: str = "",
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    await Publisher.send(
        id=protocol.ID_PLUGIN_MARKET,
        type=type,
        data={
            "requestId": request_id,
            "status": status,
            "message": message,
            "payload": payload or {},
        },
    )


async def _push_installed_sync(
    package_name: str,
    *,
    request_id: Optional[str] = None,
) -> None:
    plugins_dir = Path.cwd() / "plugins"
    installed_names = collect_installed_distribution_names(plugins_dir=plugins_dir)
    normalized = _normalize_distribution_name(package_name)
    await _send_market_message(
        protocol.PLUGIN_INSTALLED_SYNC,
        request_id=request_id,
        payload={
            "package": package_name,
            "installed": normalized in installed_names,
        },
    )


def _request_id(envelope: WSEnvelope) -> Optional[str]:
    value = str(envelope.data.get("requestId") or "").strip()
    return value or None


async def _handle_snapshot_request(envelope: WSEnvelope) -> None:
    request_id = _request_id(envelope)
    try:
        limit = int(envelope.data.get("perPrefixLimit") or 60)
        snapshot = await fetch_market_snapshot(
            plugins_dir=Path.cwd() / "plugins",
            per_prefix_limit=max(1, min(limit, 200)),
        )
        await _send_market_message(
            protocol.MARKET_SNAPSHOT_RESPONSE,
            request_id=request_id,
            payload=snapshot,
        )
    except Exception as error:
        logger.error(f"构建插件市场快照失败: {type(error).__name__}: {error}")
        await _send_market_message(
            protocol.MARKET_ERROR,
            request_id=request_id,
            status="error",
            message=f"构建插件市场快照失败: {type(error).__name__}: {error}",
        )


async def _handle_install_request(envelope: WSEnvelope) -> None:
    request_id = _request_id(envelope)
    package_name = str(envelope.data.get("package") or "").strip()
    if not package_name:
        await _send_market_message(
            protocol.MARKET_ERROR,
            request_id=request_id,
            status="error",
            message="安装请求缺少 package",
        )
        return

    await _send_market_message(
        protocol.PLUGIN_INSTALL_PROGRESS,
        request_id=request_id,
        payload={"package": package_name, "progress": 5, "stage": "queued"},
    )

    async with _plugin_operation_lock:
        await _send_market_message(
            protocol.PLUGIN_INSTALL_PROGRESS,
            request_id=request_id,
            payload={"package": package_name, "progress": 30, "stage": "installing"},
        )
        try:
            await PluginManager.install_plugin_package(package_name)
            await _send_market_message(
                protocol.PLUGIN_INSTALL_PROGRESS,
                request_id=request_id,
                payload={"package": package_name, "progress": 100, "stage": "completed"},
            )
            await _send_market_message(
                protocol.PLUGIN_INSTALL_RESULT,
                request_id=request_id,
                payload={"package": package_name, "success": True},
                message=f"安装成功: {package_name}",
            )
        except Exception as error:
            await _send_market_message(
                protocol.PLUGIN_INSTALL_RESULT,
                request_id=request_id,
                status="error",
                payload={"package": package_name, "success": False},
                message=f"安装失败: {type(error).__name__}: {error}",
            )
        finally:
            await _push_installed_sync(package_name, request_id=request_id)


async def _handle_uninstall_request(envelope: WSEnvelope) -> None:
    request_id = _request_id(envelope)
    package_name = str(envelope.data.get("package") or "").strip()
    if not package_name:
        await _send_market_message(
            protocol.MARKET_ERROR,
            request_id=request_id,
            status="error",
            message="卸载请求缺少 package",
        )
        return

    async with _plugin_operation_lock:
        try:
            await PluginManager.uninstall_plugin_package(package_name)
            await _send_market_message(
                protocol.PLUGIN_UNINSTALL_RESULT,
                request_id=request_id,
                payload={"package": package_name, "success": True},
                message=f"卸载成功: {package_name}",
            )
        except Exception as error:
            await _send_market_message(
                protocol.PLUGIN_UNINSTALL_RESULT,
                request_id=request_id,
                status="error",
                payload={"package": package_name, "success": False},
                message=f"卸载失败: {type(error).__name__}: {error}",
            )
        finally:
            await _push_installed_sync(package_name, request_id=request_id)


async def _handle_installed_request(envelope: WSEnvelope) -> None:
    request_id = _request_id(envelope)
    package_name = str(envelope.data.get("package") or "").strip()
    if not package_name:
        await _send_market_message(
            protocol.MARKET_ERROR,
            request_id=request_id,
            status="error",
            message="installed 查询缺少 package",
        )
        return
    await _push_installed_sync(package_name, request_id=request_id)


def register() -> None:
    """注册插件市场消息处理器（应用启动时调用一次）。"""
    global _registered
    if _registered:
        return
    _registered = True

    Dispatcher.register(
        protocol.ID_PLUGIN_MARKET,
        protocol.MARKET_SNAPSHOT_REQUEST,
        _handle_snapshot_request,
    )
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
    logger.info("插件市场消息处理器已注册")
