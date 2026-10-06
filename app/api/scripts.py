#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

"""脚本配置 API（``Config.ScriptConfig``）。"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.config import CollectionOrderItem
from app.config.errors import ConfigAggregateError
from app.core import Config
from app.models.config import ScriptEntry, UserEntry
from app.api import OutBase
from app.utils import get_logger

router = APIRouter(prefix="/api/scripts", tags=["脚本配置"])
logger = get_logger("脚本配置 API")


class ScriptCreateOut(OutBase):
    scriptId: str = Field(default="", description="新脚本 uid")
    data: ScriptEntry = Field(default_factory=ScriptEntry)


class ScriptGetIn(BaseModel):
    scriptId: Optional[str] = Field(default=None, description="缺省全部")


class ScriptGetOut(OutBase):
    order: list[CollectionOrderItem] = Field(default_factory=list)
    data: dict[str, ScriptEntry] = Field(default_factory=dict)


class ScriptUpdateIn(BaseModel):
    scriptId: str
    # 插件子类字段在基类上会被静默丢弃，补丁收原始结构、按实例真实类型校验
    data: dict[str, Any] = Field(..., description="补丁：只传要改的字段")


class ScriptDeleteIn(BaseModel):
    scriptId: str


class ScriptReorderIn(BaseModel):
    indexList: list[str]


class UserCreateOut(OutBase):
    userId: str = Field(default="")
    data: UserEntry = Field(default_factory=UserEntry)


class UserGetIn(BaseModel):
    scriptId: str
    userId: Optional[str] = None


class UserGetOut(OutBase):
    order: list[CollectionOrderItem] = Field(default_factory=list)
    data: dict[str, UserEntry] = Field(default_factory=dict)


class UserUpdateIn(BaseModel):
    scriptId: str
    userId: str
    data: dict[str, Any] = Field(..., description="补丁：只传要改的字段")


class UserDeleteIn(BaseModel):
    scriptId: str
    userId: str


class UserReorderIn(BaseModel):
    scriptId: str
    indexList: list[str]


class ScriptCreateIn(BaseModel):
    type: str = Field(default="", description="Entry 类名；仅一种可选类型时可省略")


class ScriptTypesOut(OutBase):
    data: list[dict[str, str]] = Field(default_factory=list)


@router.post("/types", tags=["Get"], summary="可选脚本类型", response_model=ScriptTypesOut)
async def list_script_types() -> ScriptTypesOut:
    try:
        rows = Config.ScriptConfig.list_entry_types()
        by_type: dict[str, str] = {}
        try:
            from app.core.i18n import i18n
            from app.core.plugin_manager import Plugin

            messages = await i18n.get_messages()
            # uid → 注册项拿 plugin_name；展示名走包内 i18n
            for uid, decl in Plugin.script_types.items():
                record = Config.plugin_registry.get(uid)
                plugin_name = record.info.plugin_name if record is not None else ""
                node: object = messages
                for part in ("plugins", plugin_name, "script", "display_name"):
                    if not isinstance(node, dict):
                        node = ""
                        break
                    node = node.get(part, "")
                label = node if isinstance(node, str) else ""
                by_type[decl.entry_type.__name__] = label or decl.entry_type.__name__
        except Exception:
            by_type = {}
        for row in rows:
            row["display_name"] = by_type.get(row["name"], row["name"])
        return ScriptTypesOut(data=rows)
    except Exception as e:
        return ScriptTypesOut(
            code=500, status="error", message=f"{type(e).__name__}: {e}", data=[]
        )


@router.post("/add", tags=["Add"], summary="添加脚本", response_model=ScriptCreateOut)
async def add_script(body: ScriptCreateIn = Body(default_factory=ScriptCreateIn)) -> ScriptCreateOut:
    try:
        col = Config.ScriptConfig
        names = [row["name"] for row in col.list_entry_types()]
        type_name = body.type or (names[0] if len(names) == 1 else "")
        if not type_name:
            return ScriptCreateOut(
                code=400,
                status="error",
                message="须指定 type（先读 /api/scripts/types）",
                scriptId="",
                data=ScriptEntry(),
            )
        if type_name not in names:
            return ScriptCreateOut(
                code=400,
                status="error",
                message=f"不支持的脚本类型: {type_name}",
                scriptId="",
                data=ScriptEntry(),
            )
        uid = col.add(type_name)
        await col.commit()
        return ScriptCreateOut(scriptId=str(uid), data=col[uid])
    except Exception as e:
        return ScriptCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {e}",
            scriptId="",
            data=ScriptEntry(),
        )


@router.post("/get", tags=["Get"], summary="查询脚本", response_model=ScriptGetOut)
async def get_scripts(body: ScriptGetIn = Body(...)) -> ScriptGetOut:
    try:
        col = Config.ScriptConfig
        uids = [UUID(body.scriptId)] if body.scriptId else list(col.keys())
        return ScriptGetOut(
            order=[
                CollectionOrderItem(uid=uid, type=type(col[uid]).__name__)
                for uid in uids
            ],
            data={str(uid): col[uid] for uid in uids},
        )
    except Exception as e:
        return ScriptGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {e}",
            order=[],
            data={},
        )


@router.post("/update", tags=["Update"], summary="更新脚本", response_model=OutBase)
async def update_script(body: ScriptUpdateIn = Body(...)) -> OutBase:
    try:
        entry = Config.ScriptConfig[UUID(body.scriptId)]
        await entry.update(type(entry).model_validate(body.data))
    except ConfigAggregateError as e:
        return OutBase(code=500, status="error", message=str(e))
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()


@router.post("/delete", tags=["Delete"], summary="删除脚本", response_model=OutBase)
async def delete_script(body: ScriptDeleteIn = Body(...)) -> OutBase:
    try:
        col = Config.ScriptConfig
        col.remove(body.scriptId)
        await col.commit()
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()


@router.post("/order", tags=["Update"], summary="脚本排序", response_model=OutBase)
async def order_scripts(body: ScriptReorderIn = Body(...)) -> OutBase:
    try:
        col = Config.ScriptConfig
        col.set_order([UUID(x) for x in body.indexList])
        await col.commit()
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()


# ── 嵌套用户 /user ──


@router.post(
    "/user/add", tags=["Add"], summary="添加用户", response_model=UserCreateOut
)
async def add_user(body: UserGetIn = Body(...)) -> UserCreateOut:
    try:
        users = Config.ScriptConfig[UUID(body.scriptId)].users
        # 用户类型由脚本类类体收窄，每种脚本只登记一种用户类
        uid = users.add(users.list_entry_types()[0]["name"])
        await users.commit()
        return UserCreateOut(userId=str(uid), data=users[uid])
    except Exception as e:
        return UserCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {e}",
            userId="",
            data=UserEntry(),
        )


@router.post("/user/get", tags=["Get"], summary="查询用户", response_model=UserGetOut)
async def get_users(body: UserGetIn = Body(...)) -> UserGetOut:
    try:
        users = Config.ScriptConfig[UUID(body.scriptId)].users
        uids = [UUID(body.userId)] if body.userId else list(users.keys())
        return UserGetOut(
            order=[
                CollectionOrderItem(uid=uid, type=type(users[uid]).__name__)
                for uid in uids
            ],
            data={str(uid): users[uid] for uid in uids},
        )
    except Exception as e:
        return UserGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {e}",
            order=[],
            data={},
        )


@router.post(
    "/user/update", tags=["Update"], summary="更新用户", response_model=OutBase
)
async def update_user(body: UserUpdateIn = Body(...)) -> OutBase:
    try:
        user = Config.ScriptConfig[UUID(body.scriptId)].users[UUID(body.userId)]
        await user.update(type(user).model_validate(body.data))
    except ConfigAggregateError as e:
        return OutBase(code=500, status="error", message=str(e))
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()


@router.post(
    "/user/delete", tags=["Delete"], summary="删除用户", response_model=OutBase
)
async def delete_user(body: UserDeleteIn = Body(...)) -> OutBase:
    try:
        users = Config.ScriptConfig[UUID(body.scriptId)].users
        # 删用户钩子：清本地 data/（框架点；无专项路径时仅打日志）
        logger.info(
            f"删除用户 {body.userId}（脚本 {body.scriptId}）；data/ 清理由订阅扩展"
        )
        users.remove(body.userId)
        await users.commit()
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()


@router.post(
    "/user/order", tags=["Update"], summary="用户排序", response_model=OutBase
)
async def order_users(body: UserReorderIn = Body(...)) -> OutBase:
    try:
        users = Config.ScriptConfig[UUID(body.scriptId)].users
        users.set_order([UUID(x) for x in body.indexList])
        await users.commit()
    except Exception as e:
        return OutBase(code=500, status="error", message=f"{type(e).__name__}: {e}")
    return OutBase()
