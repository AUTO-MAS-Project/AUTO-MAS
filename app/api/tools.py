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
from inspect import isawaitable
from uuid import UUID

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
    SklandLoginIn,
    TaygedoLoginIn,
)
from app.utils.constants import UTC8

router = APIRouter(prefix="/api/tools", tags=["工具设置"])


def _has_game_sign_credential(account: object, field: str) -> bool:
    """读取签到凭据时兼容未包含新增字段的旧账号对象。"""

    try:
        return bool(account.get("GameSignAccount", field))  # type: ignore[attr-defined]
    except (AttributeError, KeyError):
        return False


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
        from app.tools.game_sign import (
            GameSignInProgressError,
            format_sign_results,
            game_sign_flow,
            run_all_sign_in,
        )

        async with game_sign_flow():
            results = await run_all_sign_in(force=True)

            # 格式化并存储结果
            formatted = format_sign_results(results)
            # 合并结果（手动签到按 account_uid 替换旧数据）
            result_update = Config.update_game_sign_results(formatted, replace=True)
            if isawaitable(result_update):
                await result_update

            # 标记今天已签到（仅当所有启用的用户都已签到时标记全局）
            today = datetime.now(tz=UTC8).strftime("%Y-%m-%d")
            all_signed = True
            for uid, account in Config.ToolsConfig.GameSign_Accounts.items():
                has_credentials = any(
                    _has_game_sign_credential(account, field)
                    for field in (
                        "MiyousheToken",
                        "KuroToken",
                        "SklandToken",
                        "TaygedoToken",
                    )
                )
                if account.get("GameSignAccount", "Enabled") and has_credentials:
                    if account.get("GameSignAccount", "LastSignDate") != today:
                        all_signed = False
                        break
            if all_signed:
                await Config.ToolsConfig.set("GameSign", "LastSignDate", today)
            if results and Config.ToolsConfig.get("GameSign", "NotifyEnabled"):
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


@router.post(
    "/sign/account/taygedo/login",
    tags=["GameSign"],
    summary="塔吉多账号密码登录",
    response_model=OutBase,
    status_code=200,
)
async def login_taygedo(
    credential: TaygedoLoginIn = Body(...),
) -> OutBase:
    """一次性使用账号密码换取并保存塔吉多 Token，不保存密码。"""

    try:
        from app.tools.taygedo import (
            login_taygedo_with_password,
            parse_taygedo_credential,
            serialize_taygedo_credential,
        )

        account = Config.ToolsConfig.GameSign_Accounts[UUID(credential.accountId)]
        existing_token = str(
            account.get("GameSignAccount", "TaygedoToken") or ""
        ).strip()
        refreshed = await login_taygedo_with_password(
            credential.phone.strip(),
            credential.password.get_secret_value(),
            existing_raw=existing_token,
            proxy=Config.proxy,
        )
        serialized = serialize_taygedo_credential(refreshed)
        persisted = parse_taygedo_credential(serialized)
        if any(
            not str(persisted.get(field) or "").strip()
            for field in ("accessToken", "refreshToken", "uid")
        ):
            raise ValueError("濉斿悏澶氱櫥褰曟湭杩斿洖瀹屾暣 Token")
        await Config.update_game_sign_account(
            credential.accountId,
            {
                "GameSignAccount": {
                    "TaygedoToken": serialized,
                }
            },
        )
    except ValueError as e:
        return OutBase(code=400, status="error", message=f"塔吉多登录失败：{e}")
    except Exception:
        # 不把请求对象、异常堆栈或上游响应内容写入日志，避免泄露密码。
        return OutBase(
            code=500,
            status="error",
            message="塔吉多登录失败，请检查账号、密码、网络或风控状态",
        )

    return OutBase(message="塔吉多登录成功，Token 已保存")


@router.post(
    "/sign/account/skland/login",
    tags=["GameSign"],
    summary="森空岛手机号密码登录",
    response_model=OutBase,
    status_code=200,
)
async def login_skland(
    credential: SklandLoginIn = Body(...),
) -> OutBase:
    """一次性使用手机号和密码换取并保存森空岛凭据，不保存密码。"""

    try:
        from app.tools.skland import (
            login_skland_with_password,
            parse_skland_credential,
        )

        account = Config.ToolsConfig.GameSign_Accounts[UUID(credential.accountId)]
        serialized = await login_skland_with_password(
            credential.phone.strip(),
            credential.password.get_secret_value(),
            proxy=Config.proxy,
        )
        parsed = parse_skland_credential(serialized)
        if any(
            not str(parsed.get(field) or "").strip()
            for field in ("oauthToken", "token", "cred")
        ):
            raise ValueError("森空岛登录未返回完整凭据")
        await Config.update_game_sign_account(
            credential.accountId,
            {"GameSignAccount": {"SklandToken": serialized}},
        )
    except ValueError as e:
        return OutBase(code=400, status="error", message=f"森空岛登录失败：{e}")
    except Exception:
        # 不把请求对象、异常堆栈或上游响应内容写入日志，避免泄露密码。
        return OutBase(
            code=500,
            status="error",
            message="森空岛登录失败，请检查手机号、密码、网络或风控状态",
        )

    return OutBase(message="森空岛登录成功，Token 已保存")
