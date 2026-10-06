#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

"""游戏配置 API（``Config.GameConfig``）。"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.config import CollectionOrderItem
from app.config.errors import ConfigAggregateError
from app.core import Config
from app.core.game_manager import GameManager
from app.models.config import GameEntry
from app.api import OutBase

router = APIRouter(prefix="/api/games", tags=["游戏配置"])


class GameCreateOut(OutBase):
    gameId: str = Field(default="")
    data: GameEntry = Field(default_factory=GameEntry)


class GameGetIn(BaseModel):
    gameId: Optional[str] = None


class GameGetOut(OutBase):
    order: list[CollectionOrderItem] = Field(default_factory=list)
    data: dict[str, GameEntry] = Field(default_factory=dict)


class GameUpdateIn(BaseModel):
    gameId: str
    # 插件子类字段在基类上会被静默丢弃，补丁收原始结构、按实例真实类型校验
    data: dict[str, Any] = Field(..., description="补丁：只传要改的字段")


class GameDeleteIn(BaseModel):
    gameId: str


class GameReorderIn(BaseModel):
    indexList: list[str]


class InstancesGetIn(BaseModel):
    gameId: str


class InstanceUpdateIn(BaseModel):
    gameId: str
    deviceId: str
    data: dict[str, Any] = Field(
        ..., description="补丁：只传要改的字段；启动/关闭等 Trigger 写 True 开闸"
    )


class InstancesGetOut(OutBase):
    """设备配置列表，读游戏的 devices Collection。"""

    data: list[dict[str, Any]] = Field(default_factory=list)


class SearchOut(OutBase):
    """已启用插件搜索结果的目录，键为未激活配置 uid。"""

    data: dict[str, dict[str, Any]] = Field(default_factory=dict)


class SearchAddIn(BaseModel):
    uid: str = Field(description="搜索目录中的配置 uid")


class GameCreateIn(BaseModel):
    type: str = Field(default="", description="Entry 类名；仅一种可选类型时可省略")


class GameTypesOut(OutBase):
    data: list[dict[str, str]] = Field(default_factory=list)


@router.post("/types", tags=["Get"], summary="可选游戏类型", response_model=GameTypesOut)
async def list_game_types() -> GameTypesOut:
    try:
        rows = Config.GameConfig.list_entry_types()
        by_type: dict[str, str] = {}
        try:
            from app.core.i18n import i18n
            from app.core.plugin_manager import Plugin

            messages = await i18n.get_messages()
            # uid → 注册项拿 plugin_name；展示名走包内 i18n
            for uid, decl in Plugin.game_types.items():
                record = Config.plugin_registry.get(uid)
                plugin_name = (
                    record.info.plugin_name if record is not None else ""
                )
                node: object = messages
                for part in (
                    "plugins",
                    plugin_name,
                    "game",
                    "display_name",
                ):
                    if not isinstance(node, dict):
                        node = ""
                        break
                    node = node.get(part, "")
                label = node if isinstance(node, str) else ""
                by_type[decl.game_class.__name__] = (
                    label or decl.game_class.__name__
                )
        except Exception:
            by_type = {}
        for row in rows:
            row["display_name"] = by_type.get(row["name"], row["name"])
        return GameTypesOut(data=rows)
    except Exception as e:
        return GameTypesOut(
            code=500, status="error", message=f"{type(e).__name__}: {e}", data=[]
        )


@router.post("/add", tags=["Add"], summary="添加游戏", response_model=GameCreateOut)
async def add_game(body: GameCreateIn = Body(default_factory=GameCreateIn)) -> GameCreateOut:
    try:
        col = Config.GameConfig
        names = [row["name"] for row in col.list_entry_types()]
        type_name = body.type or (names[0] if len(names) == 1 else "")
        if not type_name:
            return GameCreateOut(
                code=400,
                status="error",
                message="须指定 type（先读 /api/games/types）",
                gameId="",
                data=GameEntry(),
            )
        if type_name not in names:
            return GameCreateOut(
                code=400,
                status="error",
                message=f"不支持的游戏类型: {type_name}",
                gameId="",
                data=GameEntry(),
            )
        uid = col.add(type_name)
        await col.commit()
        return GameCreateOut(gameId=str(uid), data=col[uid])
    except Exception as e:
        return GameCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {e}",
            gameId="",
            data=GameEntry(),
        )


@router.post("/get", tags=["Get"], summary="查询游戏", response_model=GameGetOut)
async def get_games(body: GameGetIn = Body(...)) -> GameGetOut:
    try:
        col = Config.GameConfig
        uids = [UUID(body.gameId)] if body.gameId else list(col.keys())
        return GameGetOut(
            order=[
                CollectionOrderItem(uid=uid, type=type(col[uid]).__name__)
                for uid in uids
            ],
            data={str(uid): col[uid] for uid in uids},
        )
    except Exception as e:
        return GameGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {e}",
            order=[],
            data={},
        )


@router.post("/update", tags=["Update"], summary="更新游戏", response_model=OutBase)
async def update_game(body: GameUpdateIn = Body(...)) -> OutBase:
    try:
        entry = Config.GameConfig[UUID(body.gameId)]
        await entry.update(type(entry).model_validate(body.data))
    except ConfigAggregateError as e:
        return OutBase(code=500, status="error", message=str(e))
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()


@router.post("/delete", tags=["Delete"], summary="删除游戏", response_model=OutBase)
async def delete_game(body: GameDeleteIn = Body(...)) -> OutBase:
    try:
        col = Config.GameConfig
        col.remove(UUID(body.gameId))
        await col.commit()
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()


@router.post("/order", tags=["Update"], summary="游戏排序", response_model=OutBase)
async def order_games(body: GameReorderIn = Body(...)) -> OutBase:
    try:
        col = Config.GameConfig
        col.set_order([UUID(x) for x in body.indexList])
        await col.commit()
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()


@router.post(
    "/instances/get",
    tags=["Get"],
    summary="查询游戏设备",
    response_model=InstancesGetOut,
)
async def get_instances(body: InstancesGetIn = Body(...)) -> InstancesGetOut:
    try:
        game = Config.GameConfig[UUID(body.gameId)]
        rows = []
        for dev in game.devices.values():
            row = dev.model_dump(mode="json")
            row["uid"] = str(dev.uid)
            rows.append(row)
        return InstancesGetOut(data=rows)
    except Exception as e:
        return InstancesGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {e}",
            data=[],
        )


@router.post(
    "/instances/update", tags=["Update"], summary="更新游戏设备", response_model=OutBase
)
async def update_instance(body: InstanceUpdateIn = Body(...)) -> OutBase:
    try:
        dev = Config.GameConfig[UUID(body.gameId)].devices[UUID(body.deviceId)]
        await dev.update(type(dev).model_validate(body.data))
    except ConfigAggregateError as e:
        return OutBase(code=500, status="error", message=str(e))
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()


@router.post(
    "/search",
    tags=["Get"],
    summary="搜索可加载游戏",
    response_model=SearchOut,
)
async def search_games() -> SearchOut:
    try:
        return SearchOut(data=await GameManager.search())
    except Exception as e:
        return SearchOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {e}",
            data={},
        )


@router.post(
    "/search/add",
    tags=["Add"],
    summary="将搜索结果写入游戏配置",
    response_model=GameCreateOut,
)
async def add_searched_game(body: SearchAddIn = Body(...)) -> GameCreateOut:
    try:
        entry = await GameManager.add_found(UUID(body.uid))
        return GameCreateOut(gameId=str(entry.uid), data=entry)
    except KeyError as e:
        return GameCreateOut(
            code=400,
            status="error",
            message=str(e),
            gameId="",
            data=GameEntry(),
        )
    except ValueError as e:
        return GameCreateOut(
            code=400,
            status="error",
            message=str(e),
            gameId="",
            data=GameEntry(),
        )
    except Exception as e:
        return GameCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {e}",
            gameId="",
            data=GameEntry(),
        )
