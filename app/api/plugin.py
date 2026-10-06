#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""新插件系统 HTTP API（单文件）。

面：
- ``/api/plugin_registry`` — 注册表查询 / Trigger 开闸
- ``/api/plugin_catalog`` — 目录（市场）查询 / 透传 update / 全量刷新
- ``/api/plugin_config`` — 插件自有配置查改（凭证 = ``PluginRecord.uid``，与注册表相同）
- ``/api/plugin/list`` — 已加载插件运行时列表
- ``/api/plugin/<名>/…`` — 插件声明式 HTTP 网关（须最后挂载，避免抢路径）
"""

from __future__ import annotations

import inspect
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from app.config import CollectionOrderItem
from app.config.errors import ConfigAggregateError
from app.core import Config
from app.core.plugin_manager import Plugin
from app.models.config import PluginMeta, PluginRecord
from app.api import OutBase
from app.plugin.types import PluginState
from app.utils import get_logger

# ── 子路由（按挂载顺序：具体配置面 → list → 通配网关）──
_registry = APIRouter(prefix="/api/plugin_registry", tags=["插件注册表配置"])
_catalog = APIRouter(prefix="/api/plugin_catalog", tags=["插件目录配置"])
_config = APIRouter(prefix="/api/plugin_config", tags=["插件自有配置"])
_runtime = APIRouter(prefix="/api/plugin", tags=["插件系统"])
_gateway = APIRouter(tags=["插件声明式服务"])

_REGISTRY_TRIGGERS = ("enable", "disable", "reload", "uninstall")
logger = get_logger("插件 API")

# ==================== 注册表 plugin_registry ====================


class PluginRegistryGetIn(BaseModel):
    recordId: Optional[str] = Field(default=None, description="PluginRecord.uid；缺省全部")


class PluginRegistryGetOut(OutBase):
    order: list[CollectionOrderItem] = Field(default_factory=list)
    data: dict[str, PluginRecord] = Field(default_factory=dict)


class PluginRegistryUpdateIn(BaseModel):
    recordId: str = Field(..., description="PluginRecord.uid")
    data: PluginRecord = Field(..., description="补丁；服务端剔除非 Trigger")


@_registry.post(
    "/get",
    tags=["Get"],
    summary="查询插件注册表配置",
    response_model=PluginRegistryGetOut,
)
async def get_plugin_registry(
    body: PluginRegistryGetIn = Body(...),
) -> PluginRegistryGetOut:
    try:
        col = Config.plugin_registry
        uids = [UUID(body.recordId)] if body.recordId else list(col.keys())
        return PluginRegistryGetOut(
            order=[
                CollectionOrderItem(uid=uid, type=type(col[uid]).__name__)
                for uid in uids
            ],
            data={str(uid): col[uid] for uid in uids},
        )
    except Exception as e:
        return PluginRegistryGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {e}",
            order=[],
            data={},
        )


@_registry.post(
    "/update",
    tags=["Update"],
    summary="修改插件注册表项（仅 enable/disable/reload/uninstall Trigger）",
    response_model=OutBase,
)
async def update_plugin_registry(body: PluginRegistryUpdateIn = Body(...)) -> OutBase:
    try:
        # 仅透传四 Trigger，剔除非开闸字段；冷态读 Trigger 属性恒为 False，须取原值
        sent = body.data.info.model_dump(include=set(_REGISTRY_TRIGGERS))
        payload: dict[str, Any] = {
            "info": {name: True for name in _REGISTRY_TRIGGERS if sent.get(name)}
        }
        if not payload["info"]:
            return OutBase(message="无 Trigger 可执行")
        patch = PluginRecord.model_validate(payload)
        await Config.plugin_registry[UUID(body.recordId)].update(patch)
    except ConfigAggregateError as e:
        return OutBase(code=500, status="error", message=str(e))
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()


# ==================== 目录 plugin_catalog ====================


class PluginCatalogGetIn(BaseModel):
    metaId: Optional[str] = Field(default=None, description="PluginMeta.uid；缺省全部")


class PluginCatalogGetOut(OutBase):
    order: list[CollectionOrderItem] = Field(default_factory=list)
    data: dict[str, PluginMeta] = Field(default_factory=dict)


class PluginCatalogUpdateIn(BaseModel):
    metaId: str = Field(..., description="PluginMeta.uid")
    data: PluginMeta = Field(..., description="补丁；透传全部字段，不做白名单过滤")


class PluginCatalogRefreshIn(BaseModel):
    """全量刷新；无 TAG 筛选（前端本地过滤）。"""


@_catalog.post(
    "/get", tags=["Get"], summary="查询插件目录配置", response_model=PluginCatalogGetOut
)
async def get_plugin_catalog(
    body: PluginCatalogGetIn = Body(...),
) -> PluginCatalogGetOut:
    try:
        col = Config.plugin_catalog
        uids = [UUID(body.metaId)] if body.metaId else list(col.keys())
        return PluginCatalogGetOut(
            order=[
                CollectionOrderItem(uid=uid, type=type(col[uid]).__name__)
                for uid in uids
            ],
            data={str(uid): col[uid] for uid in uids},
        )
    except Exception as e:
        return PluginCatalogGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {e}",
            order=[],
            data={},
        )


@_catalog.post(
    "/update",
    tags=["Update"],
    summary="修改目录项（透传全部字段）",
    response_model=OutBase,
)
async def update_plugin_catalog(body: PluginCatalogUpdateIn = Body(...)) -> OutBase:
    try:
        await Config.plugin_catalog[UUID(body.metaId)].update(body.data)
    except ConfigAggregateError as e:
        return OutBase(code=500, status="error", message=str(e))
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()


@_catalog.post(
    "/refresh",
    tags=["Action"],
    summary="从索引全量刷新目录并写入配置（读列表请再调 get）",
    response_model=OutBase,
)
async def refresh_plugin_catalog(
    body: PluginCatalogRefreshIn = Body(default_factory=PluginCatalogRefreshIn),
) -> OutBase:
    try:
        await Plugin.refresh_market()
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()


# ==================== 自有配置 plugin_config ====================


class PluginConfigGetIn(BaseModel):
    recordId: str = Field(
        ..., description="PluginRecord.uid（与 /api/plugin_registry 相同；靠端点区分）"
    )


class PluginConfigGetOut(OutBase):
    data: Any = Field(default=None, description="配置实例；未启用或无配置则为 null")


class PluginConfigUpdateIn(BaseModel):
    recordId: str = Field(..., description="PluginRecord.uid")
    data: dict[str, Any] = Field(
        default_factory=dict, description="热补丁；走 entry.update"
    )


@_config.post(
    "/get",
    tags=["Get"],
    summary="查询插件自有配置（与注册表同一 uid）",
    response_model=PluginConfigGetOut,
)
async def get_plugin_config(body: PluginConfigGetIn = Body(...)) -> PluginConfigGetOut:
    try:
        record = Config.plugin_registry[UUID(body.recordId)]
        cfg = record._config
        if cfg is None:
            return PluginConfigGetOut(data=None)
        return PluginConfigGetOut(data=cfg)
    except KeyError:
        return PluginConfigGetOut(
            code=404, status="error", message="未找到对应插件配置", data=None
        )
    except Exception as e:
        return PluginConfigGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {e}",
            data=None,
        )


@_config.post(
    "/update",
    tags=["Update"],
    summary="修改插件自有配置（与注册表同一 uid）",
    response_model=OutBase,
)
async def update_plugin_config(body: PluginConfigUpdateIn = Body(...)) -> OutBase:
    try:
        record = Config.plugin_registry[UUID(body.recordId)]
        cfg = record._config
        if cfg is None:
            return OutBase(code=400, status="error", message="插件未启用或无自有配置")
        # 用同类型冷态补丁；失败由 ConfigAggregateError 上抛
        patch = type(cfg).model_validate(body.data)
        await cfg.update(patch)
    except KeyError:
        return OutBase(code=404, status="error", message="未找到对应插件配置")
    except ConfigAggregateError as e:
        return OutBase(code=500, status="error", message=str(e))
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()


# ==================== 运行时列表 /api/plugin/list ====================


class PluginListItem(BaseModel):
    name: str
    state: str
    enabled: bool
    is_core: bool = False
    is_local: bool = False
    version: Optional[str] = None
    distribution: Optional[str] = None
    source: Optional[str] = None
    description: str = ""
    requires: list[str] = Field(default_factory=list)
    wants: list[str] = Field(default_factory=list)
    last_error: Optional[str] = None


class PluginListOut(OutBase):
    data: list[PluginListItem] = Field(default_factory=list)


@_runtime.post(
    "/list",
    tags=["Get"],
    summary="列出已加载插件（运行时）",
    response_model=PluginListOut,
)
async def list_plugins() -> PluginListOut:
    try:
        items: list[PluginListItem] = []
        for slot in Plugin.list_plugins():
            info = slot.info
            items.append(
                PluginListItem(
                    name=info.plugin_name,
                    state=info.state.value,
                    enabled=info.state == PluginState.ENABLED,
                    is_core=info.is_core,
                    is_local=info.is_local,
                    version=info.version or None,
                    distribution=info.package_name or None,
                    source=info.source or None,
                    description="",
                    requires=list(info.requires),
                    wants=list(info.wants),
                    last_error=info.last_error or None,
                )
            )
        return PluginListOut(data=items)
    except Exception as e:
        return PluginListOut(code=1, status="error", message=str(e), data=[])


# ==================== 声明式 HTTP 网关 ====================


@_gateway.api_route(
    "/api/plugin/{plugin_name}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    include_in_schema=False,
)
async def dispatch_plugin_http(
    plugin_name: str, path: str, request: Request
) -> Response:
    """按插件名 + 相对路径匹配 ``HttpRegistry`` 中的声明路由。"""
    # 退出密封后一律 503，不再按挂载表分发
    if not Plugin.http.accepting:
        return JSONResponse(
            status_code=503,
            content={"detail": "插件系统正在退出，已拒绝外部请求"},
        )
    mount = Plugin.http.get(plugin_name)
    if mount is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"插件未挂载 HTTP: {plugin_name}"},
        )
    rel = "/" + path.strip("/")
    if rel != "/":
        rel = rel.rstrip("/") or "/"
    method = request.method.upper()
    handler = None
    for decl in mount.routes:
        decl_path = decl.path if decl.path.startswith("/") else f"/{decl.path}"
        decl_path = decl_path.rstrip("/") or "/"
        if decl_path == rel and method in decl.methods:
            handler = decl.handler
            break
    if handler is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"未找到路由: {method} {mount.prefix}{rel}"},
        )
    try:
        # 优先注入 Request；无参则直接调用
        try:
            sig = inspect.signature(handler)
            if "request" in sig.parameters or any(
                p.annotation is Request for p in sig.parameters.values()
            ):
                result = handler(request)
            elif len(sig.parameters) == 0:
                result = handler()
            else:
                result = handler(request)
            if inspect.isawaitable(result):
                result = await result
        except (TypeError, ValueError):
            result = handler(request)
            if inspect.isawaitable(result):
                result = await result
        if isinstance(result, Response):
            return result
        if isinstance(result, (dict, list)) or result is None:
            return JSONResponse(content=result)
        return PlainTextResponse(content=str(result))
    except Exception as exc:
        logger.exception(f"插件 HTTP 处理失败: {plugin_name} {rel}")
        return JSONResponse(
            status_code=500,
            content={"detail": f"{type(exc).__name__}: {exc}"},
        )


# ── 聚合出口：main 只 include 本 router；网关放最后避免抢 /api/plugin/* ──
router = APIRouter()
router.include_router(_registry)
router.include_router(_catalog)
router.include_router(_config)
router.include_router(_runtime)
router.include_router(_gateway)
