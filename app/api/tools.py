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

"""工具设置 API：请求/响应字段基于 ``Tools`` / ``GameSignAccount``，直接操作 ``Config.tools``。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.config import CollectionOrderItem
from app.config.errors import ConfigAggregateError
from app.core import Config
from app.models.config import GameSignAccount, Tools
from app.models.schema import OutBase

router = APIRouter(prefix="/api/tools", tags=["工具设置"])

CREDENTIAL_FIELDS = ("miyoushe_token", "kuro_token", "skland_token")
CREDENTIAL_REDACTION = "******"


# ==================== 字段（基于 ConfigEntry） ====================


class ToolsGetOut(OutBase):
    data: Tools = Field(default_factory=Tools, description="工具配置")


class ToolsUpdateIn(BaseModel):
    data: Tools = Field(..., description="工具配置补丁（Wire 形状）")


class GameSignAccountCreateOut(OutBase):
    accountId: str = Field(default="", description="账号组 UUID")
    data: GameSignAccount = Field(
        default_factory=GameSignAccount, description="账号组配置"
    )


class GameSignAccountGetIn(BaseModel):
    accountId: str = Field(..., description="账号组 UUID")


class GameSignAccountsListOut(OutBase):
    order: list[CollectionOrderItem] = Field(
        default_factory=list, description="账号组顺序"
    )
    data: dict[str, GameSignAccount] = Field(
        default_factory=dict, description="账号组数据，key 为 uid"
    )


class GameSignAccountUpdateIn(BaseModel):
    accountId: str = Field(..., description="账号组 UUID")
    data: GameSignAccount = Field(..., description="账号组补丁（Wire 形状）")


class GameSignAccountDeleteIn(BaseModel):
    accountId: str = Field(..., description="账号组 UUID")


class GameSignAccountReorderIn(BaseModel):
    order: list[str] = Field(..., description="账号组 UUID 顺序列表")


# ==================== 工具配置 ====================


@router.post(
    "/get",
    tags=["Get"],
    summary="查询工具配置",
    response_model=ToolsGetOut,
    status_code=200,
)
async def get_tools() -> ToolsGetOut:
    """获取工具设置。"""
    try:
        return ToolsGetOut(data=Config.tools)
    except Exception as e:
        return ToolsGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=Tools(),
        )


@router.post(
    "/update",
    tags=["Update"],
    summary="更新工具配置",
    response_model=OutBase,
    status_code=200,
)
async def update_tools(body: ToolsUpdateIn = Body(...)) -> OutBase:
    """更新工具配置（仅 Group 字段；账号组走独立端点）。"""
    try:
        await Config.tools.update(body.data)
    except ConfigAggregateError as e:
        return OutBase(code=500, status="error", message=str(e))
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/sign",
    tags=["Action"],
    summary="手动触发游戏社区签到",
    response_model=OutBase,
    status_code=200,
)
async def manual_game_sign() -> OutBase:
    """手动触发游戏社区签到。"""
    try:
        from app.tools.game_sign import (
            GameSignInProgressError,
            format_sign_results,
            merge_sign_results,
            run_all_sign_in,
        )

        results = await run_all_sign_in(force=True)
        formatted = format_sign_results(results)
        Config.tools._game_sign_result_data = merge_sign_results(
            Config.tools._game_sign_result_data, formatted, replace=True
        )

        today = datetime.now().strftime("%Y-%m-%d")
        all_signed = True
        for account in Config.tools.accounts.values():
            if account.info.enabled and account.info.last_sign_date != today:
                all_signed = False
                break
        if all_signed:
            Config.tools.game_sign.last_sign_date = today
        Config.tools.game_sign.scheduled_time = ""
        await Config.tools.commit()

        if results and Config.tools.game_sign.notify_enabled:
            from app.tools.game_sign_notify import push_game_sign_notification

            failed_channels = await push_game_sign_notification(results)
            if failed_channels:
                return OutBase(
                    status="warning",
                    message=f"签到完成，但部分通知发送失败：{'、'.join(failed_channels)}",
                )

    except GameSignInProgressError as e:
        return OutBase(code=409, status="error", message=str(e))
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase(message="签到完成")


# ==================== 游戏签到账号组 ====================


@router.post(
    "/sign/account/list",
    tags=["GameSign"],
    summary="获取所有游戏签到账号组",
    response_model=GameSignAccountsListOut,
    status_code=200,
)
async def list_game_sign_accounts() -> GameSignAccountsListOut:
    """获取所有游戏签到账号组（凭据脱敏）。"""
    try:
        col = Config.tools.accounts
        data: dict[str, GameSignAccount] = {}
        for uid in col.keys():
            wire = col[uid].model_dump()
            info = dict(wire.get("info") or {})
            for field in CREDENTIAL_FIELDS:
                info[field] = CREDENTIAL_REDACTION if info.get(field) else ""
            wire["info"] = info
            data[str(uid)] = GameSignAccount.model_validate(wire)
        return GameSignAccountsListOut(
            order=[
                CollectionOrderItem(uid=uid, type=type(col[uid]).__name__)
                for uid in col.keys()
            ],
            data=data,
        )
    except Exception as e:
        return GameSignAccountsListOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            order=[],
            data={},
        )


@router.post(
    "/sign/account/add",
    tags=["GameSign"],
    summary="添加游戏签到账号组",
    response_model=GameSignAccountCreateOut,
    status_code=200,
)
async def add_game_sign_account() -> GameSignAccountCreateOut:
    """添加游戏签到账号组。"""
    try:
        col = Config.tools.accounts
        uid = col.add(GameSignAccount)
        await col.commit()
        wire = col[uid].model_dump()
        info = dict(wire.get("info") or {})
        for field in CREDENTIAL_FIELDS:
            info[field] = CREDENTIAL_REDACTION if info.get(field) else ""
        wire["info"] = info
        return GameSignAccountCreateOut(
            accountId=str(uid), data=GameSignAccount.model_validate(wire)
        )
    except Exception as e:
        return GameSignAccountCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            accountId="",
            data=GameSignAccount(),
        )


@router.post(
    "/sign/account/get",
    tags=["GameSign"],
    summary="获取游戏签到账号组详情",
    response_model=GameSignAccountCreateOut,
    status_code=200,
)
async def get_game_sign_account(
    body: GameSignAccountGetIn = Body(...),
) -> GameSignAccountCreateOut:
    """获取游戏签到账号组详情（凭据脱敏）。"""
    try:
        wire = Config.tools.accounts[UUID(body.accountId)].model_dump()
        info = dict(wire.get("info") or {})
        for field in CREDENTIAL_FIELDS:
            info[field] = CREDENTIAL_REDACTION if info.get(field) else ""
        wire["info"] = info
        return GameSignAccountCreateOut(
            accountId=body.accountId, data=GameSignAccount.model_validate(wire)
        )
    except Exception as e:
        return GameSignAccountCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            accountId=body.accountId,
            data=GameSignAccount(),
        )


@router.post(
    "/sign/account/update",
    tags=["GameSign"],
    summary="更新游戏签到账号组配置",
    response_model=OutBase,
    status_code=200,
)
async def update_game_sign_account(
    body: GameSignAccountUpdateIn = Body(...),
) -> OutBase:
    """更新游戏签到账号组；占位符凭据不写入；凭据变更时重置签到日。"""
    try:
        account = Config.tools.accounts[UUID(body.accountId)]
        dump = body.data.model_dump(exclude_unset=True)
        info = dump.get("info")
        credential_changed = False
        if isinstance(info, dict):
            for field in CREDENTIAL_FIELDS:
                if info.get(field) == CREDENTIAL_REDACTION:
                    info.pop(field)
            credential_changed = any(
                field in info and info[field] != getattr(account.info, field)
                for field in CREDENTIAL_FIELDS
            )
            if credential_changed:
                info["last_sign_date"] = "2000-01-01"
        await account.update(GameSignAccount.model_validate(dump))
        if credential_changed:
            result = Config.tools._game_sign_result_data
            for platform in list(result):
                result[platform] = [
                    group
                    for group in result[platform]
                    if group.get("account_uid") != body.accountId
                ]
                if not result[platform]:
                    del result[platform]
    except ConfigAggregateError as e:
        return OutBase(code=500, status="error", message=str(e))
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/sign/account/delete",
    tags=["GameSign"],
    summary="删除游戏签到账号组",
    response_model=OutBase,
    status_code=200,
)
async def delete_game_sign_account(
    body: GameSignAccountDeleteIn = Body(...),
) -> OutBase:
    """删除游戏签到账号组。"""
    try:
        col = Config.tools.accounts
        col.remove(body.accountId)
        await col.commit()
        result = Config.tools._game_sign_result_data
        for platform in list(result):
            result[platform] = [
                group
                for group in result[platform]
                if group.get("account_uid") != body.accountId
            ]
            if not result[platform]:
                del result[platform]
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/sign/account/reorder",
    tags=["GameSign"],
    summary="调整游戏签到账号组顺序",
    response_model=OutBase,
    status_code=200,
)
async def reorder_game_sign_accounts(
    body: GameSignAccountReorderIn = Body(...),
) -> OutBase:
    """调整游戏签到账号组顺序。"""
    try:
        col = Config.tools.accounts
        col.set_order(list(map(UUID, body.order)))
        await col.commit()
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()
