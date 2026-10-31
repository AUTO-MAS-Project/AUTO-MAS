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


import traceback
from datetime import datetime
from inspect import isawaitable
from typing import (
    Dict,
    Literal,
)
from uuid import UUID

from fastapi import APIRouter, Body
from pydantic import (
    BaseModel,
    Field,
    SecretStr,
)

import app.models.config as _config_models
from app.config.wire import (
    ConfigInput,
    ConfigPayload,
    config_group_contract,
)
from app.core import Community, Config, Notify
from app.core.community.sign import CommunitySignInProgressError
from app.models.schema import OutBase
from app.tools.common.community.contracts import is_community_sign_completed
from app.utils import UTC8, format_exception_reason, get_logger

ToolsConfig = ConfigPayload[_config_models.ToolsConfig]
ToolsConfigInput = ConfigInput[_config_models.ToolsConfig]


class GameSignAccountGroupConfig(
    config_group_contract(
        _config_models.GameSignAccountGroup.GameSignAccountFields,
        name="GameSignAccountGroupConfig",
    )
):
    """账号组的纯接口投影。"""


class GameSignAccountGroupConfigInput(
    config_group_contract(
        _config_models.GameSignAccountGroup.GameSignAccountFields,
        name="GameSignAccountGroupConfigInput",
        mode="input",
    )
):
    """账号组的纯接口投影。"""


class TaygedoLoginIn(BaseModel):
    """塔吉多一次性账号密码登录请求。"""

    accountId: str = Field(..., description="账号组 UUID")
    phone: str = Field(..., min_length=1, description="塔吉多账号或手机号")
    password: SecretStr = Field(..., min_length=1, description="塔吉多账号密码")


class GameSignAccountCreateOut(OutBase):
    """游戏社区账号组创建响应"""

    accountId: str = Field(default="", description="账号组 UUID")
    data: GameSignAccountGroupConfig = Field(
        default_factory=GameSignAccountGroupConfig, description="账号组配置"
    )


class GameSignAccountInstanceOut(BaseModel):
    """游戏社区账号组顺序项。"""

    uid: str = Field(..., description="账号组 UUID")
    type: str = Field(..., description="账号组配置类型")


class GameSignAccountDataOut(BaseModel):
    """动态 UUID 键对应的游戏社区账号组数据。"""

    GameSignAccount: GameSignAccountGroupConfig = Field(..., description="账号组配置")


class GameSignAccountCollectionOut(BaseModel):
    """新配置集合的索引和成员文档。"""

    order: list[GameSignAccountInstanceOut] = Field(default_factory=list)
    data: Dict[str, GameSignAccountDataOut] = Field(default_factory=dict)


class GameSignAccountsListOut(OutBase):
    """游戏社区账号组列表响应"""

    data: GameSignAccountCollectionOut = Field(
        default_factory=GameSignAccountCollectionOut, description="账号组列表"
    )


class GameSignAccountUpdateIn(BaseModel):
    """游戏社区账号组更新请求"""

    accountId: str = Field(..., description="账号组 UUID")
    data: GameSignAccountGroupConfigInput = Field(..., description="账号组配置")


class GameSignAccountDeleteIn(BaseModel):
    """游戏社区账号组删除请求"""

    accountId: str = Field(..., description="账号组 UUID")


class GameSignAccountReorderIn(BaseModel):
    """游戏社区账号组排序请求"""

    order: list[str] = Field(..., description="账号组 UUID 顺序列表")


class CommunityActivityQueryIn(BaseModel):
    """游戏社区日常查询请求。"""

    accountIds: list[str] | None = Field(
        default=None,
        description="指定账号组 UUID 列表；为空时查询全部已配置账号组",
    )


class CommunityActivityTaskOut(BaseModel):
    """日常活动中的单项任务。"""

    name: str = Field(..., description="任务名称")
    completed: int = Field(..., description="已完成数量")
    target: int = Field(..., description="目标数量")
    status: str = Field(..., description="任务状态")
    period: str = Field(default="daily", description="任务周期")


class CommunityActivityResourceOut(BaseModel):
    """日常活动中的可用资源。"""

    name: str = Field(..., description="资源名称")
    current: int = Field(..., description="当前数量")
    target: int = Field(..., description="容量上限")
    status: str = Field(..., description="资源状态")


class CommunityActivitySnapshotOut(BaseModel):
    """单个游戏角色的日常活动快照。"""

    account: str = Field(..., description="账号组名称")
    accountUid: str = Field(..., description="账号组 UUID")
    game: str = Field(..., description="游戏名称")
    platform: str = Field(..., description="社区平台名称")
    status: Literal["success", "empty", "limited", "unavailable", "failed"] = Field(
        ..., description="活动查询状态"
    )
    completed: int | None = Field(default=None, description="已完成数量")
    target: int | None = Field(default=None, description="目标数量")
    tasks: list[CommunityActivityTaskOut] = Field(
        default_factory=list, description="每日任务"
    )
    resources: list[CommunityActivityResourceOut] = Field(
        default_factory=list, description="可用资源"
    )
    reason: str = Field(default="", description="失败或受限原因")
    updatedAt: str = Field(default="", description="查询时间")
    roleName: str = Field(default="", description="角色名称")
    roleUid: str = Field(default="", description="角色 UID")
    server: str = Field(default="", description="角色区服")
    source: str = Field(default="", description="已确认的数据来源路径")


class CommunityActivityOut(OutBase):
    """游戏社区日常活动查询响应。"""

    data: list[CommunityActivitySnapshotOut] = Field(
        default_factory=list, description="按账号和游戏拆分的活动快照"
    )


class ToolsGetOut(OutBase):
    data: ToolsConfig = Field(..., description="工具配置数据")


class ToolsUpdateIn(BaseModel):
    data: ToolsConfigInput = Field(..., description="工具配置需要更新的数据")


router = APIRouter(prefix="/api/tools", tags=["工具设置"])
logger = get_logger("游戏社区 API")
_MIYOUSHE_DEVICE_FIELDS = ("MiyousheDeviceId", "MiyousheDeviceFp")


def _log_community_api_error(stage: str, error: Exception) -> None:
    """记录脱敏诊断，社区 API 不把异常细节直接返回给前端。"""

    logger.warning(format_exception_reason(error, stage=stage, include_message=False))
    if error.__traceback__ is not None:
        # 保留定位信息，不记录局部变量、源码行或可能含凭据的异常原文。
        frames = traceback.extract_tb(error.__traceback__)
        logger.warning(
            "社区调用位置: "
            + " -> ".join(
                f"{frame.filename}:{frame.lineno} in {frame.name}" for frame in frames
            )
        )


def _normalize_miyoushe_device_fields(data: dict[str, object]) -> None:
    """规范历史设备字段；残缺旧值由 provider 自动设备链路接管。"""

    for field in _MIYOUSHE_DEVICE_FIELDS:
        if field not in data:
            continue
        value = data.get(field)
        data[field] = value.strip() if isinstance(value, str) else ""


def _get_community_account_field(account: object, field: str, default=None):
    """读取社区账号字段时兼容未包含新增字段的旧账号对象。"""

    try:
        return getattr(account.GameSignAccount, field)  # type: ignore[attr-defined]
    except (AttributeError, KeyError):
        return default


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
        _log_community_api_error("读取工具配置失败", e)
        return ToolsGetOut(
            code=500,
            status="error",
            message="读取工具配置失败，请稍后重试",
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
        _log_community_api_error("更新工具配置失败", e)
        return OutBase(
            code=500,
            status="error",
            message="更新工具配置失败，请稍后重试",
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
        from app.models.notification.community import community_notification_results
        from app.tools import community as _tool_community

        # 流程锁覆盖签到和结果落盘，通知在锁外发送，避免慢渠道阻塞后续操作。
        async with Community.community_sign_flow():
            results = await Community.run_community_sign_in(force=True)

            # 格式化并存储结果
            formatted = _tool_community.format_community_sign_results(results)
            # 合并结果（手动签到按 account_uid 替换旧数据）
            result_update = Config.update_community_results(formatted, replace=True)
            if isawaitable(result_update):
                await result_update

            # 标记今天已签到（仅当所有启用的用户都已签到时标记全局）
            today = datetime.now(tz=UTC8).strftime("%Y-%m-%d")
            all_signed = True
            for uid, account in Config.ToolsConfig.GameSign_Accounts.items():
                has_credentials = _tool_community.has_community_credentials(account)
                if _get_community_account_field(account, "Enabled") and has_credentials:
                    if (
                        account.GameSignAccount.LastSignDate.strftime("%Y-%m-%d")
                        != today
                    ):
                        all_signed = False
                        break
            if all_signed:
                await Config.ToolsConfig.update(
                    type(Config.ToolsConfig).model_validate(
                        {"GameSign": {"LastSignDate": datetime.now(tz=UTC8)}}
                    ),
                    check_visibility=False,
                )
        warning_messages = []
        if any(not is_community_sign_completed(result) for result in results):
            warning_messages.append("签到未全部完成，请查看签到结果")
        if results:
            failed_channels = await Notify.community.submit(
                community_notification_results(results)
            )
            if failed_channels:
                warning_messages.append(
                    f"部分通知发送失败：{'、'.join(failed_channels)}"
                )
        if warning_messages:
            return OutBase(status="warning", message="；".join(warning_messages))

    except CommunitySignInProgressError as e:
        _log_community_api_error("游戏社区签到并发冲突", e)
        return OutBase(
            code=409,
            status="error",
            message="游戏社区签到正在执行，请稍后重试",
        )
    except Exception as e:
        _log_community_api_error("游戏社区签到失败", e)
        return OutBase(
            code=500,
            status="error",
            message="游戏社区签到失败，请稍后重试",
        )
    return OutBase(message="签到完成")


@router.post(
    "/community/activity/query",
    tags=["Community"],
    summary="查询游戏社区日常活跃度",
    response_model=CommunityActivityOut,
    status_code=200,
)
async def query_community_activity(
    query: CommunityActivityQueryIn = Body(...),
) -> CommunityActivityOut:
    """查询游戏社区日常活动，不占用签到流程锁。"""

    if Config.ToolsConfig.GameSign.ActivityEnabled is False:
        return CommunityActivityOut(status="success", data=[])

    snapshots = ()
    try:
        snapshots = await Community.query_configured_community_activity(
            query.accountIds
        )
    except ValueError as exc:
        _log_community_api_error("游戏社区日常查询参数或凭据无效", exc)
        return CommunityActivityOut(
            code=400,
            status="error",
            message="游戏社区日常查询参数或凭据无效",
        )
    except Exception as exc:
        _log_community_api_error("游戏社区日常查询失败", exc)
        snapshots = Community.build_configured_community_activity_failures(
            query.accountIds,
        )
        if not snapshots:
            return CommunityActivityOut(
                code=500,
                status="error",
                message="游戏社区日常查询失败，请稍后重试",
            )

    return CommunityActivityOut(
        status="warning"
        if any(snapshot.status != "success" for snapshot in snapshots)
        else "success",
        message="部分游戏日常查询失败"
        if any(snapshot.status == "failed" for snapshot in snapshots)
        else "",
        data=[
            CommunityActivitySnapshotOut(
                account=snapshot.account,
                accountUid=snapshot.account_uid,
                game=snapshot.game,
                platform=snapshot.platform,
                status=snapshot.status,
                completed=snapshot.completed,
                target=snapshot.target,
                tasks=[
                    CommunityActivityTaskOut(**dict(task)) for task in snapshot.tasks
                ],
                resources=[
                    CommunityActivityResourceOut(**dict(resource))
                    for resource in snapshot.resources
                ],
                reason=snapshot.reason,
                updatedAt=snapshot.updated_at,
                roleName=snapshot.role_name,
                roleUid=snapshot.role_uid,
                server=snapshot.server,
                source=snapshot.source,
            )
            for snapshot in snapshots
        ],
    )


# ==================== 游戏社区账号组 CRUD ====================


@router.post(
    "/sign/account/list",
    tags=["GameSign"],
    summary="获取所有游戏社区账号组",
    response_model=GameSignAccountsListOut,
    status_code=200,
)
async def list_game_sign_accounts() -> GameSignAccountsListOut:
    """获取所有游戏社区账号组"""

    try:
        data = await Config.get_game_sign_accounts()
    except Exception as e:
        _log_community_api_error("获取游戏社区账号组失败", e)
        return GameSignAccountsListOut(
            code=500,
            status="error",
            message="获取游戏社区账号组失败，请稍后重试",
            data=GameSignAccountCollectionOut(),
        )
    return GameSignAccountsListOut(
        data=GameSignAccountCollectionOut.model_validate(data)
    )


@router.post(
    "/sign/account/add",
    tags=["GameSign"],
    summary="添加游戏社区账号组",
    response_model=GameSignAccountCreateOut,
    status_code=200,
)
async def add_game_sign_account() -> GameSignAccountCreateOut:
    """添加游戏社区账号组"""

    try:
        uid, config = await Config.add_game_sign_account()
        # 配置导出按组组织，账号接口继续使用原有扁平载荷。
        raw = config.model_dump(context={"audience": "api"})
        flat = raw.get("GameSignAccount", raw)
        data = GameSignAccountGroupConfig(**flat)
        # 新增账号无需清空结果，因为新账号没有历史结果
    except Exception as e:
        _log_community_api_error("添加游戏社区账号组失败", e)
        return GameSignAccountCreateOut(
            code=500,
            status="error",
            message="添加游戏社区账号组失败，请稍后重试",
            accountId="",
            data=GameSignAccountGroupConfig(**{}),
        )
    return GameSignAccountCreateOut(accountId=str(uid), data=data)


@router.post(
    "/sign/account/update",
    tags=["GameSign"],
    summary="更新游戏社区账号组配置",
    response_model=OutBase,
    status_code=200,
)
async def update_game_sign_account(
    account: GameSignAccountUpdateIn = Body(...),
) -> OutBase:
    """更新游戏社区账号组配置"""

    try:
        # 将账号接口的扁平载荷包装为配置分组。
        flat_data = account.data.model_dump(exclude_unset=True)
        _normalize_miyoushe_device_fields(flat_data)
        skland_token = flat_data.get("SklandToken")
        if isinstance(skland_token, str) and skland_token.strip():
            from app.tools.common.community.providers import skland as _tool_skland

            try:
                _tool_skland.validate_skland_credential(skland_token)
            except ValueError as exc:
                _log_community_api_error("森空岛凭据校验失败", exc)
                return OutBase(
                    code=400,
                    status="error",
                    message=str(exc),
                )
        cloud_genshin_token = flat_data.get("CloudGenshinToken")
        if isinstance(cloud_genshin_token, str) and cloud_genshin_token.strip():
            from app.tools.common.community.providers import (
                cloud_genshin as _tool_cloud_genshin,
            )

            try:
                flat_data["CloudGenshinToken"] = (
                    _tool_cloud_genshin.validate_cloud_genshin_token(
                        cloud_genshin_token
                    )
                )
            except ValueError as exc:
                _log_community_api_error("云原神凭据校验失败", exc)
                return OutBase(
                    code=400,
                    status="error",
                    message="云原神 combo token 格式无效，请检查后重试",
                )
        data = {"GameSignAccount": flat_data}
        await Config.update_game_sign_account(account.accountId, data)
    except Exception as e:
        _log_community_api_error("更新游戏社区账号组失败", e)
        return OutBase(
            code=500,
            status="error",
            message="更新游戏社区账号组失败，请稍后重试",
        )
    return OutBase()


@router.post(
    "/sign/account/delete",
    tags=["GameSign"],
    summary="删除游戏社区账号组",
    response_model=OutBase,
    status_code=200,
)
async def delete_game_sign_account(
    account: GameSignAccountDeleteIn = Body(...),
) -> OutBase:
    """删除游戏社区账号组"""

    try:
        await Config.delete_game_sign_account(account.accountId)
    except Exception as e:
        _log_community_api_error("删除游戏社区账号组失败", e)
        return OutBase(
            code=500,
            status="error",
            message="删除游戏社区账号组失败，请稍后重试",
        )
    return OutBase()


@router.post(
    "/sign/account/reorder",
    tags=["GameSign"],
    summary="调整游戏社区账号组顺序",
    response_model=OutBase,
    status_code=200,
)
async def reorder_game_sign_accounts(
    account: GameSignAccountReorderIn = Body(...),
) -> OutBase:
    """调整游戏社区账号组顺序"""

    try:
        await Config.reorder_game_sign_accounts(account.order)
    except Exception as e:
        _log_community_api_error("调整游戏社区账号组顺序失败", e)
        return OutBase(
            code=500,
            status="error",
            message="调整游戏社区账号组顺序失败，请稍后重试",
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
        from app.tools.common.community.providers import taygedo as _tool_taygedo

        account = Config.ToolsConfig.GameSign_Accounts[UUID(credential.accountId)]
        existing_token = str(account.GameSignAccount.TaygedoToken or "").strip()
        refreshed = await _tool_taygedo.login_taygedo_with_password(
            credential.phone.strip(),
            credential.password.get_secret_value(),
            existing_raw=existing_token,
            proxy=Config.proxy,
        )
        serialized = _tool_taygedo.serialize_taygedo_credential(refreshed)
        persisted = _tool_taygedo.parse_taygedo_credential(serialized)
        if any(
            not str(persisted.get(field) or "").strip()
            for field in ("accessToken", "refreshToken", "uid")
        ):
            raise ValueError("塔吉多登录未返回完整 Token")
        await Config.update_game_sign_account(
            credential.accountId,
            {
                "GameSignAccount": {
                    "TaygedoToken": serialized,
                }
            },
        )
    except ValueError as e:
        _log_community_api_error("塔吉多登录校验失败", e)
        return OutBase(
            code=400,
            status="error",
            message="塔吉多登录失败，请检查账号、密码或凭据格式",
        )
    except Exception as e:
        _log_community_api_error("塔吉多登录失败", e)
        return OutBase(
            code=500,
            status="error",
            message="塔吉多登录失败，请检查账号、密码、网络或风控状态",
        )

    return OutBase(message="塔吉多登录成功，Token 已保存")
