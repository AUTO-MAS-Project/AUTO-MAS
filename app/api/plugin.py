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
- ``/api/plugin_registry`` — 注册表查询；插件命令统一经 Operations 提交
- ``/api/plugin_catalog`` — 目录（市场）查询 / 透传 update / 全量刷新
- ``/api/plugin_config`` — 插件自有配置查改（凭证 = ``PluginRecord.uid``，与注册表相同）
- ``/api/plugin/list`` — 已加载插件运行时列表
- ``/api/plugin/<名>/…`` — 插件声明式 HTTP 网关（须最后挂载，避免抢路径）
"""

from __future__ import annotations

import inspect
from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from app.config import CollectionOrderItem
from app.config.errors import ConfigAggregateError
from app.config.fields.hints import UiHintsMap, UiTablesList
from app.config.wire import ConfigInput, ConfigPayload
from app.core import Config
from app.core.i18n import AppLocale
from app.core.plugin import Plugin
from app.models.config import PluginMeta, PluginRecord
from app.models.schema import ComboBoxItem, ComboBoxOut, OutBase
from app.plugin.errors import PluginBusyError
from app.plugin.http import PLUGIN_GATEWAY_PATH
from app.plugin.types import PluginState, plugin_locale
from app.utils import get_logger


class PluginPlanOptionsIn(BaseModel):
    type: str | None = Field(
        default=None, description="计划配置类型名；缺省返回全部插件计划"
    )


class PluginGameDevicesIn(BaseModel):
    gameId: UUID


class PluginRegistryGetIn(BaseModel):
    recordId: Optional[str] = Field(
        default=None, description="PluginRecord.uid；缺省全部"
    )


class PluginConfigUi(BaseModel):
    hints: UiHintsMap = Field(default_factory=dict)
    tables: UiTablesList = Field(default_factory=list)


class PluginRegistryDocument(ConfigPayload[PluginRecord]):
    """沿用配置字段投影，并显式保留命令目标身份及运行时 UI 属性。"""

    uid: UUID
    ui: PluginConfigUi
    disableImpact: list[Literal["scripts", "games"]] = Field(default_factory=list)


class PluginCatalogDocument(ConfigPayload[PluginMeta]):
    """市场条目的配置投影，包含安装操作的显隐和可编辑属性。"""

    uid: UUID
    ui: PluginConfigUi


class PluginRegistryGetOut(OutBase):
    order: list[CollectionOrderItem] = Field(default_factory=list)
    # 插件注册表条目包含运行时子类和后端 UI 声明，响应按 wire 数据透传。
    data: dict[str, PluginRegistryDocument] = Field(default_factory=dict)


class PluginCatalogGetIn(BaseModel):
    metaId: Optional[str] = Field(default=None, description="PluginMeta.uid；缺省全部")


class PluginCatalogGetOut(OutBase):
    order: list[CollectionOrderItem] = Field(default_factory=list)
    data: dict[str, PluginCatalogDocument] = Field(default_factory=dict)


class PluginCatalogUpdateIn(BaseModel):
    metaId: str = Field(..., description="PluginMeta.uid")
    data: ConfigInput[PluginMeta] = Field(
        ..., description="补丁；透传全部字段，不做白名单过滤"
    )


class PluginCatalogRefreshIn(BaseModel):
    """全量刷新；无 TAG 筛选（前端本地过滤）。"""


class PluginConfigGetIn(BaseModel):
    recordId: str = Field(
        ..., description="PluginRecord.uid（与 /api/plugin_registry 相同；靠端点区分）"
    )


class PluginConfigDocument(BaseModel):
    """动态配置组透传，公共 UI 声明保持可生成的契约。"""

    model_config = ConfigDict(extra="allow")
    uid: UUID
    ui: PluginConfigUi


class PluginConfigGetOut(OutBase):
    data: PluginConfigDocument | None = None


class PluginConfigUpdateIn(BaseModel):
    recordId: str = Field(..., description="PluginRecord.uid")
    data: dict[str, Any] = Field(
        default_factory=dict, description="热补丁；走 entry.update"
    )


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


class PluginRuntimeListOut(OutBase):
    data: list[PluginListItem] = Field(default_factory=list)


# ── 子路由（按挂载顺序：具体配置面 → list → 通配网关）──
_registry = APIRouter(prefix="/api/plugin_registry", tags=["插件注册表配置"])
_catalog = APIRouter(prefix="/api/plugin_catalog", tags=["插件目录配置"])
_config = APIRouter(prefix="/api/plugin_config", tags=["插件自有配置"])
_runtime = APIRouter(prefix="/api/plugin", tags=["插件系统"])
_gateway = APIRouter(tags=["插件声明式服务"])

logger = get_logger("插件 API")

# ==================== 注册表 plugin_registry ====================


@_registry.post(
    "/get",
    tags=["Get"],
    summary="查询插件注册表配置",
    response_model=PluginRegistryGetOut,
)
async def get_plugin_registry(
    body: PluginRegistryGetIn = Body(...),
) -> PluginRegistryGetOut:
    """读取单个或全部已安装插件记录，按配置 API 格式返回条目顺序与展示数据。"""
    try:
        col = Config.plugin_registry
        uids = [UUID(body.recordId)] if body.recordId else list(col.keys())
        return PluginRegistryGetOut(
            order=[
                CollectionOrderItem(uid=uid, type=type(col[uid]).__name__)
                for uid in uids
            ],
            data={
                str(uid): PluginRegistryDocument.model_validate(
                    {
                        "uid": uid,
                        "disableImpact": Plugin.disable_impact(col[uid]),
                        **col[uid].model_dump(mode="json", context={"audience": "api"}),
                    }
                )
                for uid in uids
            },
        )
    except Exception as e:
        return PluginRegistryGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {e}",
            order=[],
            data={},
        )


# ==================== 目录 plugin_catalog ====================


@_catalog.post(
    "/get", tags=["Get"], summary="查询插件目录配置", response_model=PluginCatalogGetOut
)
async def get_plugin_catalog(
    body: PluginCatalogGetIn = Body(...),
) -> PluginCatalogGetOut:
    """读取单个或全部市场插件条目，返回展示顺序、版本及安装操作所需的配置数据。"""
    try:
        col = Config.plugin_catalog
        uids = [UUID(body.metaId)] if body.metaId else list(col.keys())
        return PluginCatalogGetOut(
            order=[
                CollectionOrderItem(uid=uid, type=type(col[uid]).__name__)
                for uid in uids
            ],
            data={
                str(uid): PluginCatalogDocument.model_validate(
                    {
                        "uid": uid,
                        **col[uid].model_dump(mode="json", context={"audience": "api"}),
                    }
                )
                for uid in uids
            },
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
async def update_plugin_catalog(
    body: PluginCatalogUpdateIn = Body(...),
) -> OutBase:
    """按目录配置类型校验并保存局部补丁，命令身份由独立操作入口提供。"""
    try:
        await Config.plugin_catalog[UUID(body.metaId)].update(
            PluginMeta.model_validate(body.data.model_dump(exclude_unset=True))
        )
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
    """请求插件管理器重新拉取市场目录，将刷新结果转换为统一接口响应。"""
    try:
        await Plugin.refresh_market()
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()


# ==================== 自有配置 plugin_config ====================


@_config.post(
    "/get",
    tags=["Get"],
    summary="查询插件自有配置（凭注册表项定位）",
    response_model=PluginConfigGetOut,
)
async def get_plugin_config(body: PluginConfigGetIn = Body(...)) -> PluginConfigGetOut:
    """读取已安装插件的专属配置，未声明配置时返回空值，记录不存在时返回未找到错误。"""
    try:
        record = Config.plugin_registry[UUID(body.recordId)]
        cfg = record._config
        if cfg is None:
            return PluginConfigGetOut(data=None)
        return PluginConfigGetOut(
            data=PluginConfigDocument.model_validate(
                {
                    "uid": cfg.uid,
                    **cfg.model_dump(mode="json", context={"audience": "api"}),
                }
            )
        )
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
    summary="修改插件自有配置（凭注册表项定位）",
    response_model=OutBase,
)
async def update_plugin_config(
    body: PluginConfigUpdateIn = Body(...),
) -> OutBase:
    """按插件实际配置类型校验并保存局部补丁，返回配置更新结果。"""
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


@_runtime.post(
    "/list",
    tags=["Get"],
    summary="列出已加载插件（运行时）",
    response_model=PluginRuntimeListOut,
)
async def list_plugins() -> PluginRuntimeListOut:
    """汇总已发现插件的运行状态、版本、来源和依赖，供前端插件管理页展示。"""
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
        return PluginRuntimeListOut(data=items)
    except Exception as e:
        return PluginRuntimeListOut(code=1, status="error", message=str(e), data=[])


@_runtime.post("/options/games", response_model=ComboBoxOut)
async def plugin_game_options() -> ComboBoxOut:
    """将宿主已登记的游戏配置转换为插件配置控件可选择的标签与标识。"""
    return ComboBoxOut(
        data=[
            ComboBoxItem(label=entry.info.name, value=str(uid))
            for uid, entry in Config.GameConfig.items()
        ]
    )


@_runtime.post("/options/devices", response_model=ComboBoxOut)
async def plugin_device_options(body: PluginGameDevicesIn) -> ComboBoxOut:
    """按游戏标识读取设备列表并转换为选项，游戏不存在时返回空列表。"""
    game = Config.GameConfig.get(body.gameId)
    return ComboBoxOut(
        data=[]
        if game is None
        else [
            ComboBoxItem(label=entry.info.name, value=str(uid))
            for uid, entry in game.devices.items()
        ]
    )


@_runtime.post("/options/plans", response_model=ComboBoxOut)
async def plugin_plan_options(
    body: PluginPlanOptionsIn = Body(default_factory=PluginPlanOptionsIn),
) -> ComboBoxOut:
    """按已登记计划类型筛选选项，不另登记专项消费方标识。"""
    from app.models.config import PlanEntry

    plan_type = PlanEntry
    if body.type is not None:
        declared = Config.PlanConfig.entry_types.get(body.type)
        if declared is None or not issubclass(declared, PlanEntry):
            return ComboBoxOut(
                code=400, status="error", message="计划配置类型不存在", data=[]
            )
        plan_type = declared
    return ComboBoxOut(
        data=[
            ComboBoxItem(label=entry.info.name, value=str(uid))
            for uid, entry in Config.PlanConfig.items()
            if isinstance(entry, plan_type)
        ]
    )


# ==================== 声明式 HTTP 网关 ====================


@_gateway.api_route(
    PLUGIN_GATEWAY_PATH,
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
        # 参数约定在进入业务前绑定，异常处理不包含任何二次试调用。
        signature = inspect.signature(handler)
        args = () if not signature.parameters else (request,)
        signature.bind(*args)
        result = handler(*args)
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, Response):
            return result
        if isinstance(result, (dict, list)) or result is None:
            return JSONResponse(content=result)
        return PlainTextResponse(content=str(result))
    except PluginBusyError:
        return JSONResponse(status_code=503, content={"detail": "插件正在释放"})
    except Exception as exc:
        logger.exception(f"插件 HTTP 处理失败: {plugin_name} {rel}")
        return JSONResponse(
            status_code=500,
            content={"detail": f"{type(exc).__name__}: {exc}"},
        )


# ── 聚合出口：main 只 include 本 router；网关放最后避免抢 /api/plugin/* ──
async def _locale_scope(locale: AppLocale = Query("zh-CN")):
    """为本次插件接口调用设置语言上下文，并在请求结束或异常时恢复原语言。"""
    token = plugin_locale.set(locale)
    try:
        yield
    finally:
        plugin_locale.reset(token)


router = APIRouter(dependencies=[Depends(_locale_scope)])
router.include_router(_registry)
router.include_router(_catalog)
router.include_router(_config)
router.include_router(_runtime)
router.include_router(_gateway)
