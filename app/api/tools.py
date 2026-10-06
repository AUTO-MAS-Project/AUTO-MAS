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
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""工具设置 API：请求/响应字段基于 ``Tools`` / ``GameSignAccount``，直接操作 ``Config.tools``。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.api import OutBase
from app.config.errors import ConfigAggregateError
from app.core import Config
from app.models.config import GameSignAccount, Tools
from app.tools.game_sign import (
    GameSignInProgressError,
    format_sign_results,
    run_all_sign_in,
)
from app.utils.constants import UTC8

router = APIRouter(prefix="/api/tools", tags=["工具设置"])


# ==================== 前端契约（PascalCase，与 Tools 模型逐字段互转） ====================


class ToolsConfig_ArknightsPC(BaseModel):
    Enabled: bool | None = Field(default=None, description="是否启用 ArknightsPC 工具")
    PauseKey: str | None = Field(default=None, description="暂停键位")
    SelectDeployedKey: str | None = Field(
        default=None, description="选中已部署干员键位"
    )
    UseSkillKey: str | None = Field(default=None, description="释放技能键位")
    RetreatKey: str | None = Field(default=None, description="撤退键位")
    NextFrameKey: str | None = Field(default=None, description="下一帧键位")
    AnotherQuitKey: str | None = Field(default=None, description="自定义退出、暂停键位")
    Status: str | None = Field(default=None, description="工具状态 Tag")


class ToolsConfig_GameSign(BaseModel):
    Enabled: bool | None = Field(default=None, description="是否启用游戏签到")
    NotifyEnabled: bool | None = Field(default=None, description="签到后是否发送通知")
    WindowStart: str | None = Field(default=None, description="签到窗口起点 HH:mm")
    WindowEnd: str | None = Field(default=None, description="签到窗口终点 HH:mm")
    RunOnStartup: bool | None = Field(default=None, description="启动时运行")
    ScheduledRun: bool | None = Field(default=None, description="定时运行")
    AutoStart: bool | None = Field(default=None, description="是否立即开始")
    LastSignDate: str | None = Field(default=None, description="上次签到日期")
    ScheduledTime: str | None = Field(default=None, description="今日计划签到时间")
    Status: str | None = Field(default=None, description="签到状态标签")
    Result: str | None = Field(default=None, description="签到结果 JSON")


class ToolsConfig(BaseModel):
    ArknightsPC: ToolsConfig_ArknightsPC | None = Field(
        default=None, description="明日方舟PC工具配置"
    )
    GameSign: ToolsConfig_GameSign | None = Field(
        default=None, description="游戏社区签到配置"
    )


class ToolsGetOut(OutBase):
    data: ToolsConfig = Field(..., description="工具配置数据")


class ToolsUpdateIn(BaseModel):
    data: ToolsConfig = Field(..., description="工具配置需要更新的数据")


class GameSignAccountGroupConfig(BaseModel):
    """游戏签到账号组配置"""

    Name: str | None = Field(default=None, description="账号组名称")
    Enabled: bool | None = Field(default=None, description="是否启用")
    MiyousheToken: str | None = Field(default=None, description="米游社登录凭证")
    KuroToken: str | None = Field(default=None, description="库街区登录凭证")
    SklandToken: str | None = Field(default=None, description="森空岛登录凭证")


class GameSignAccountCreateOut(OutBase):
    """游戏签到账号组创建响应"""

    accountId: str = Field(default="", description="账号组 UUID")
    data: GameSignAccountGroupConfig = Field(
        default_factory=GameSignAccountGroupConfig, description="账号组配置"
    )


class GameSignAccountsListOut(OutBase):
    """游戏签到账号组列表响应"""

    data: dict[str, Any] = Field(default_factory=dict, description="账号组列表")


class GameSignAccountGetIn(BaseModel):
    """游戏签到账号组查询请求"""

    accountId: str = Field(..., description="账号组 UUID")


class GameSignAccountUpdateIn(BaseModel):
    """游戏签到账号组更新请求"""

    accountId: str = Field(..., description="账号组 UUID")
    data: GameSignAccountGroupConfig = Field(..., description="账号组配置")


class GameSignAccountDeleteIn(BaseModel):
    """游戏签到账号组删除请求"""

    accountId: str = Field(..., description="账号组 UUID")


class GameSignAccountReorderIn(BaseModel):
    """游戏签到账号组排序请求"""

    order: list[str] = Field(..., description="账号组 UUID 顺序列表")


def _parse_hm(value: str) -> datetime:
    """解析前端 ``HH:mm`` → UTC8 datetime（锚定 2000-01-01）。"""
    return datetime.strptime(f"2000-01-01 {value}", "%Y-%m-%d %H:%M").replace(tzinfo=UTC8)


def _tools_config(tools: Tools) -> ToolsConfig:
    """工具模型（snake_case）→ 前端契约（PascalCase；Status/Result 为虚拟字段实时计算）。"""
    pc = tools.arknights_pc
    gs = tools.game_sign
    return ToolsConfig(
        ArknightsPC=ToolsConfig_ArknightsPC(
            Enabled=pc.enabled,
            PauseKey=pc.pause_key,
            SelectDeployedKey=pc.select_deployed_key,
            UseSkillKey=pc.use_skill_key,
            RetreatKey=pc.retreat_key,
            NextFrameKey=pc.next_frame_key,
            AnotherQuitKey=pc.another_quit_key,
            Status=pc.status,
        ),
        GameSign=ToolsConfig_GameSign(
            Enabled=gs.enabled,
            NotifyEnabled=gs.notify_enabled,
            WindowStart=gs.window_start.strftime("%H:%M"),
            WindowEnd=gs.window_end.strftime("%H:%M"),
            RunOnStartup=gs.run_on_startup,
            ScheduledRun=gs.scheduled_run,
            AutoStart=gs.auto_start,
            LastSignDate=gs.last_sign_date.isoformat(),
            ScheduledTime=gs.scheduled_time,
            Status=gs.status,
            Result=gs.result,
        ),
    )


def _tools_from_config(cfg: ToolsConfig) -> Tools:
    """前端契约（PascalCase）→ 工具模型；仅含前端给定字段（``update`` 只同步它们）。"""
    kwargs: dict[str, Any] = {}
    if cfg.ArknightsPC is not None:
        pc = cfg.ArknightsPC
        pc_kwargs: dict[str, Any] = {}
        if pc.Enabled is not None:
            pc_kwargs["enabled"] = pc.Enabled
        if pc.PauseKey is not None:
            pc_kwargs["pause_key"] = pc.PauseKey
        if pc.SelectDeployedKey is not None:
            pc_kwargs["select_deployed_key"] = pc.SelectDeployedKey
        if pc.UseSkillKey is not None:
            pc_kwargs["use_skill_key"] = pc.UseSkillKey
        if pc.RetreatKey is not None:
            pc_kwargs["retreat_key"] = pc.RetreatKey
        if pc.NextFrameKey is not None:
            pc_kwargs["next_frame_key"] = pc.NextFrameKey
        if pc.AnotherQuitKey is not None:
            pc_kwargs["another_quit_key"] = pc.AnotherQuitKey
        if pc_kwargs:
            kwargs["arknights_pc"] = Tools.ArknightsPc(**pc_kwargs)
    if cfg.GameSign is not None:
        gs = cfg.GameSign
        gs_kwargs: dict[str, Any] = {}
        if gs.Enabled is not None:
            gs_kwargs["enabled"] = gs.Enabled
        if gs.NotifyEnabled is not None:
            gs_kwargs["notify_enabled"] = gs.NotifyEnabled
        if gs.WindowStart is not None:
            gs_kwargs["window_start"] = _parse_hm(gs.WindowStart)
        if gs.WindowEnd is not None:
            gs_kwargs["window_end"] = _parse_hm(gs.WindowEnd)
        if gs.RunOnStartup is not None:
            gs_kwargs["run_on_startup"] = gs.RunOnStartup
        if gs.ScheduledRun is not None:
            gs_kwargs["scheduled_run"] = gs.ScheduledRun
        if gs.AutoStart is not None:
            gs_kwargs["auto_start"] = gs.AutoStart
        if gs.LastSignDate is not None:
            gs_kwargs["last_sign_date"] = date.fromisoformat(gs.LastSignDate)
        if gs.ScheduledTime is not None:
            gs_kwargs["scheduled_time"] = gs.ScheduledTime
        if gs_kwargs:
            kwargs["game_sign"] = Tools.GameSign(**gs_kwargs)
    return Tools.build(**kwargs)


def _account_group(account: GameSignAccount) -> GameSignAccountGroupConfig:
    """账号模型（info, snake_case）→ 前端契约（PascalCase；凭据明文）。"""
    info = account.info
    return GameSignAccountGroupConfig(
        Name=info.name,
        Enabled=info.enabled,
        MiyousheToken=info.miyoushe_token,
        KuroToken=info.kuro_token,
        SklandToken=info.skland_token,
    )


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
        return ToolsGetOut(data=_tools_config(Config.tools))
    except Exception as e:
        return ToolsGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=ToolsConfig(),
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
        await Config.tools.update(_tools_from_config(body.data))
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
        results = await run_all_sign_in(force=True)
        formatted = format_sign_results(results)
        # 合并结果（手动签到按 account_uid 替换旧数据）
        await Config.update_game_sign_results(formatted, replace=True)

        today = datetime.now(tz=UTC8).date()
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
    """获取所有游戏签到账号组（PascalCase 形状）。"""

    try:
        col = Config.tools.accounts
        data: dict[str, Any] = {"instances": []}
        for uid in col.keys():
            data["instances"].append({"uid": str(uid), "type": "GameSignAccount"})
            data[str(uid)] = {"GameSignAccount": _account_group(col[uid]).model_dump()}
    except Exception as e:
        return GameSignAccountsListOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data={},
        )
    return GameSignAccountsListOut(data=data)


@router.post(
    "/sign/account/add",
    tags=["GameSign"],
    summary="添加游戏签到账号组",
    response_model=GameSignAccountCreateOut,
    status_code=200,
)
async def add_game_sign_account() -> GameSignAccountCreateOut:
    """添加游戏签到账号组（新账号无历史结果，无需清空）。"""
    try:
        col = Config.tools.accounts
        uid = col.add(GameSignAccount)
        await col.commit()
        data = _account_group(col[uid])
    except Exception as e:
        return GameSignAccountCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            accountId="",
            data=GameSignAccountGroupConfig(),
        )
    return GameSignAccountCreateOut(accountId=str(uid), data=data)


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
    """获取游戏签到账号组详情（凭据明文，供编辑回显）。"""
    try:
        account = Config.tools.accounts[UUID(body.accountId)]
        account_data = _account_group(account)
    except Exception as e:
        return GameSignAccountCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            accountId=body.accountId,
            data=GameSignAccountGroupConfig(),
        )
    return GameSignAccountCreateOut(accountId=body.accountId, data=account_data)


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
    """更新游戏签到账号组；空凭据占位不写入；凭据变更时重置签到日。"""
    try:
        account = Config.tools.accounts[UUID(body.accountId)]
        # 扁平 PascalCase 契约 → info 组字段（只含前端给定的键）
        info: dict[str, Any] = {}
        if body.data.Name is not None:
            info["name"] = body.data.Name
        if body.data.Enabled is not None:
            info["enabled"] = body.data.Enabled
        changed = False
        for pascal, snake in (
            ("MiyousheToken", "miyoushe_token"),
            ("KuroToken", "kuro_token"),
            ("SklandToken", "skland_token"),
        ):
            value = getattr(body.data, pascal)
            if not value:  # 空 / None：占位符不写入
                continue
            if getattr(account.info, snake) == value:
                continue
            info[snake] = value
            changed = True
        if changed:
            info["last_sign_date"] = date(2000, 1, 1)
        await account.update(GameSignAccount.model_validate({"info": info}))
        if changed:
            Config._clear_game_sign_account_results(body.accountId)
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
    """删除游戏签到账号组（一并清除当天结果）。"""
    try:
        col = Config.tools.accounts
        col.remove(body.accountId)
        await col.commit()
        Config._clear_game_sign_account_results(body.accountId)
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
