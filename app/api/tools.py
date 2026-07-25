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


from fastapi import APIRouter, Body
from datetime import datetime
from app.core import Config
from app.models.schema import (
    ToolsGetOut,
    ToolsConfig,
    OutBase,
    ToolsUpdateIn,
    GameSignAccountCreateOut,
    GameSignAccountGroupConfig,
    GameSignAccountGetIn,
    GameSignAccountUpdateIn,
    GameSignAccountDeleteIn,
    GameSignAccountReorderIn,
    GameSignAccountsListOut,
)

router = APIRouter(prefix="/api/tools", tags=["工具设置"])


@router.post(
    "/get",
    tags=["Get"],
    summary="查询工具配置",
    response_model=ToolsGetOut,
    status_code=200,
)
async def get_tools() -> ToolsGetOut:
    """获取工具设置"""

    try:
        data = await Config.get_tools()
    except Exception as e:
        return ToolsGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=ToolsConfig(**{}),
        )
    return ToolsGetOut(data=ToolsConfig(**data))


@router.post(
    "/update",
    tags=["Update"],
    summary="更新工具配置",
    response_model=OutBase,
    status_code=200,
)
async def update_tools(script: ToolsUpdateIn = Body(...)) -> OutBase:
    """更新工具配置"""

    try:
        data = script.data.model_dump(exclude_unset=True)
        await Config.update_tools(data)

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
    """手动触发游戏社区签到"""

    try:
        from app.tools.game_sign import run_all_sign_in, format_sign_results
        from app.tools.game_sign import merge_sign_results

        results = await run_all_sign_in(force=True)

        # 格式化并存储结果
        formatted = format_sign_results(results)
        # 合并结果（手动签到按 account_uid 替换旧数据）
        Config.ToolsConfig._game_sign_result_data = merge_sign_results(
            Config.ToolsConfig._game_sign_result_data, formatted, replace=True
        )

        # 标记今天已签到（仅当所有启用的用户都已签到时标记全局）
        today = datetime.now().strftime("%Y-%m-%d")
        all_signed = True
        for uid, account in Config.ToolsConfig.GameSign_Accounts.items():
            if account.get("GameSignAccount", "Enabled"):
                if account.get("GameSignAccount", "LastSignDate") != today:
                    all_signed = False
                    break
        if all_signed:
            await Config.ToolsConfig.set("GameSign", "LastSignDate", today)
        # 清除计划时间
        await Config.ToolsConfig.set("GameSign", "ScheduledTime", "")

    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


# ==================== 游戏签到账号组 CRUD ====================


@router.post(
    "/sign/account/list",
    tags=["GameSign"],
    summary="获取所有游戏签到账号组",
    response_model=GameSignAccountsListOut,
    status_code=200,
)
async def list_game_sign_accounts() -> GameSignAccountsListOut:
    """获取所有游戏签到账号组"""

    try:
        data = await Config.get_game_sign_accounts()
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
    """添加游戏签到账号组"""

    try:
        uid, config = await Config.add_game_sign_account()
        # toDict() 返回 {"GameSignAccount": {fields}}，需提取嵌套字典
        raw = await config.toDict()
        flat = raw.get("GameSignAccount", raw)
        data = GameSignAccountGroupConfig(**flat)
        # 新增账号无需清空结果，因为新账号没有历史结果
    except Exception as e:
        return GameSignAccountCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            accountId="",
            data=GameSignAccountGroupConfig(**{}),
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
    account: GameSignAccountGetIn = Body(...),
) -> GameSignAccountCreateOut:
    """获取游戏签到账号组详情"""

    try:
        raw = await Config.get_game_sign_account(account.accountId)
        # toDict() 返回 {"GameSignAccount": {fields}}，需提取嵌套字典
        flat = raw.get("GameSignAccount", raw)
        account_data = GameSignAccountGroupConfig(**flat)
    except Exception as e:
        return GameSignAccountCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            accountId=account.accountId,
            data=GameSignAccountGroupConfig(**{}),
        )
    return GameSignAccountCreateOut(accountId=account.accountId, data=account_data)


@router.post(
    "/sign/account/update",
    tags=["GameSign"],
    summary="更新游戏签到账号组配置",
    response_model=OutBase,
    status_code=200,
)
async def update_game_sign_account(
    account: GameSignAccountUpdateIn = Body(...),
) -> OutBase:
    """更新游戏签到账号组配置"""

    try:
        # GameSignAccountGroupConfig 是扁平格式，需包装为 {group: {name: value}} 传给 ConfigBase.set
        flat_data = account.data.model_dump(exclude_unset=True)
        data = {"GameSignAccount": flat_data}
        await Config.update_game_sign_account(account.accountId, data)
        # Token 变更后只清空该账号的签到结果
        token_fields = {"MiyousheToken", "KuroToken", "SklandToken"}
        if token_fields & set(flat_data.keys()):
            result = Config.ToolsConfig._game_sign_result_data
            account_uid = str(account.accountId)
            for platform in list(result.keys()):
                result[platform] = [
                    group for group in result[platform]
                    if group.get("account_uid") != account_uid
                ]
                if not result[platform]:
                    del result[platform]
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
    account: GameSignAccountDeleteIn = Body(...),
) -> OutBase:
    """删除游戏签到账号组"""

    try:
        await Config.delete_game_sign_account(account.accountId)
        # 删除账号后清理该用户的签到结果
        account_uid = str(account.accountId)
        result = Config.ToolsConfig._game_sign_result_data
        for platform in list(result.keys()):
            result[platform] = [
                group for group in result[platform]
                if group.get("account_uid") != account_uid
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
    account: GameSignAccountReorderIn = Body(...),
) -> OutBase:
    """调整游戏签到账号组顺序"""

    try:
        await Config.reorder_game_sign_accounts(account.order)
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()
