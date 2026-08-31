#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Awaitable, Callable

import httpx

from app.core import Config
from app.utils.logger import get_logger
from app.utils.security import format_exception_reason
from .game_sign_credentials import (
    is_community_credential_configured,
    parse_community_credential,
    validate_community_credential,
)
from .game_sign_contract import CommunitySignInProgressError, CommunitySignResult
from .game_sign_result import build_skland_sign_results

logger = get_logger("游戏社区签到")

_system_time_checked_at = 0.0
_SYSTEM_TIME_CHECK_INTERVAL = 300.0


@dataclass
class _CommunityProviderRun:
    """单个社区适配器的结果和需要回写的凭据。"""

    results: list[dict]
    platforms: tuple[str, ...]
    credential_updates: dict[str, str] = field(default_factory=dict)


CredentialUpdateCallback = Callable[[str, str], Awaitable[None]]
ProviderRunner = Callable[
    [str, str, str, CredentialUpdateCallback | None],
    Awaitable[_CommunityProviderRun],
]
PlatformResolver = Callable[[str], tuple[str, ...]]
ErrorGameResolver = Callable[[str], str]


@dataclass(frozen=True)
class _CommunitySignProvider:
    """以配置字段驱动的社区签到适配器描述。"""

    token_field: str
    log_name: str
    runner: ProviderRunner
    resolve_platforms: PlatformResolver
    error_game: ErrorGameResolver


GameSignInProgressError = CommunitySignInProgressError


@asynccontextmanager
async def game_sign_flow():
    """兼容旧调用方，转发到社区签到流程锁。"""

    from app.core.community_sign import community_sign_flow

    async with community_sign_flow():
        yield


async def _enter_game_sign_lock() -> bool:
    """兼容旧内部调用，获取社区签到执行锁。"""

    from app.core.community_sign import _enter_community_sign_lock

    return await _enter_community_sign_lock()


def _exit_game_sign_lock(acquired: bool) -> None:
    """兼容旧内部调用，释放社区签到执行锁。"""

    from app.core.community_sign import _exit_community_sign_lock

    _exit_community_sign_lock(acquired)


def _all_enabled_platforms_signed(
    results: list[dict],
    *,
    account_uid: str,
    enabled_platforms: list[str],
) -> bool:
    """兼容旧内部调用，判断账号的已配置平台是否全部完成。"""

    from app.core.community_sign import all_enabled_community_platforms_signed

    return all_enabled_community_platforms_signed(
        results,
        account_uid=account_uid,
        enabled_platforms=enabled_platforms,
    )


async def check_community_system_time() -> None:
    """检查系统时间偏差并提示用户，不阻断签到流程。

    时间源不可信或不可用时（服务退役、被劫持的网络等）仅记录日志；
    真正对时间敏感的只有米游社 DS 签名，其容差远大于此处阈值，
    因此偏差过大时也只告警，由具体平台的签到结果反映实际影响。
    """
    global _system_time_checked_at
    now = time.monotonic()
    if now - _system_time_checked_at < _SYSTEM_TIME_CHECK_INTERVAL:
        return
    # 无论时间服务成功与否，都缓存本次尝试，避免网络异常时每次签到重复等待。
    _system_time_checked_at = now

    try:
        async with httpx.AsyncClient(proxy=Config.proxy) as client:
            resp = await client.get(
                "https://worldtimeapi.org/api/timezone/Asia/Shanghai", timeout=5
            )
        api_time = resp.json().get("unixtime", 0)
        if not api_time:
            return
        local_time = time.time()
        offset = abs(api_time - local_time)
        if offset > 300:
            logger.warning(
                f"系统时间与网络时间偏差约 {offset:.0f} 秒，部分平台签到可能失败，建议校准系统时间"
            )
        elif offset > 30:
            logger.info(f"系统时间偏差 {offset:.0f} 秒，在可接受范围内")
    except Exception as e:
        logger.debug(f"时间校准跳过: {e}")


def _empty_platform_result(
    *, account_name: str, account_uid: str, platform: str
) -> dict:
    """为没有返回可签到角色的平台保留通知占位，不写入前端结果列表。"""

    return CommunitySignResult(
        account=account_name,
        account_uid=account_uid,
        game="",
        platform=platform,
        status="失败",
        reason="未获取到可签到角色",
        notification_only=True,
    ).to_legacy()


async def run_all_sign_in(force: bool = False) -> list[dict]:
    """兼容旧调用方，转发到社区签到核心编排。"""

    from app.core.community_sign import run_community_sign_in

    return await run_community_sign_in(force=force)


def _fixed_platforms(platform: str) -> PlatformResolver:
    return lambda _token: (platform,)


def _default_error_game(platform: str) -> str:
    return platform


def _taygedo_error_game(platform: str) -> str:
    # 未完成凭据/上游校验时没有可靠的游戏 ID，不把结果猜成某一款游戏。
    return "塔吉多社区" if platform == "塔吉多" else "云异环"


def _resolve_taygedo_platforms(raw_token: str) -> tuple[str, ...]:
    """根据塔吉多凭据字段确定实际启用的社区。"""

    try:
        credential = parse_community_credential("TaygedoToken", raw_token)
    except Exception:
        return ("塔吉多",)

    platforms = []
    if credential.has_any(
        "refreshToken",
        "refresh_token",
        "accessToken",
        "access_token",
    ):
        platforms.append("塔吉多")
    if credential.has_any("cloudToken", "cloud_token") and credential.has_any(
        "cloudUserId", "cloud_user_id"
    ):
        platforms.append("云异环")
    return tuple(platforms) or ("塔吉多",)


async def _run_skland_provider(
    token: str,
    account_name: str,
    account_uid: str,
    on_credential_update: CredentialUpdateCallback | None = None,
) -> _CommunityProviderRun:
    from .skland import skland_sign_in

    updated_token = ""

    async def capture_credential(value: str) -> None:
        nonlocal updated_token
        updated_token = str(value or "").strip()
        if updated_token and on_credential_update is not None:
            try:
                await on_credential_update("SklandToken", updated_token)
            except Exception as error:
                # 收尾 credential_updates 仍会重试，不能让回写故障掩盖签到结果。
                logger.warning(
                    f"[{account_name}] 森空岛凭据即时回写失败: {type(error).__name__}"
                )

    raw_result = await skland_sign_in(
        token,
        app_code="all",
        proxy=getattr(Config, "proxy", None),
        on_credential_update=capture_credential,
    )
    updates = {"SklandToken": updated_token} if updated_token else {}
    return _CommunityProviderRun(
        results=build_skland_sign_results(
            raw_result,
            account_name=account_name,
            account_uid=account_uid,
        ),
        platforms=("森空岛",),
        credential_updates=updates,
    )


async def _run_miyoushe_provider(
    token: str,
    _account_name: str,
    _account_uid: str,
    on_credential_update: CredentialUpdateCallback | None = None,
) -> _CommunityProviderRun:
    from .miyoushe import merge_miyoushe_cookie_update, miyoushe_sign_in

    updated_token = ""

    async def capture_credential(value: str) -> None:
        nonlocal updated_token
        candidate = str(value or "")
        if candidate:
            updated_token = merge_miyoushe_cookie_update(token, candidate)
            if updated_token and on_credential_update is not None:
                try:
                    await on_credential_update("MiyousheToken", updated_token)
                except Exception as error:
                    # 收尾 credential_updates 仍会重试，不能让回写故障掩盖签到结果。
                    logger.warning(
                        f"米游社凭据即时回写失败: {type(error).__name__}"
                    )

    results = await miyoushe_sign_in(
        token,
        on_credential_update=capture_credential,
    )
    updates = {"MiyousheToken": updated_token} if updated_token else {}
    return _CommunityProviderRun(
        results=results,
        platforms=("米游社",),
        credential_updates=updates,
    )


async def _run_kuro_provider(
    token: str,
    _account_name: str,
    _account_uid: str,
    _on_credential_update: CredentialUpdateCallback | None = None,
) -> _CommunityProviderRun:
    from .kuro import kuro_sign_in

    return _CommunityProviderRun(
        results=await kuro_sign_in(token),
        platforms=("库街区",),
    )


async def _run_taygedo_provider(
    token: str,
    _account_name: str,
    _account_uid: str,
    on_credential_update: CredentialUpdateCallback | None = None,
) -> _CommunityProviderRun:
    from .taygedo import (
        sign_taygedo,
        validate_taygedo_credential,
    )

    validate_taygedo_credential(token)

    # 刷新结果由 provider 先聚合，再交给社区签到编排统一回写；这样既能
    # 接住上游轮换后的 refreshToken，也能让下一次调用优先复用当前 accessToken。
    updated_token = ""

    async def capture_credential(value: str) -> None:
        nonlocal updated_token
        updated_token = str(value or "").strip()
        if updated_token and on_credential_update is not None:
            # 塔吉多内部会在刷新返回后立即调用此回调；不要在这里吞掉异常，
            # 让 sign_taygedo 保留收尾兜底机会。
            await on_credential_update("TaygedoToken", updated_token)

    community_results, _runtime_credential = await sign_taygedo(
        token,
        proxy=Config.proxy,
        on_credential_update=capture_credential,
    )
    return _CommunityProviderRun(
        results=community_results,
        platforms=(),
        credential_updates={"TaygedoToken": updated_token} if updated_token else {},
    )


def get_community_sign_providers() -> tuple[_CommunitySignProvider, ...]:
    """返回按通知顺序排列的签到适配器注册表。"""

    return _COMMUNITY_SIGN_PROVIDERS


def get_community_token_field(platform: str) -> str:
    """从兼容签到注册表读取社区凭据字段。"""

    for provider in get_community_sign_providers():
        if provider.log_name == platform:
            return provider.token_field
    raise ValueError(f"{platform}社区凭据字段尚未登记")


_COMMUNITY_SIGN_PROVIDERS = (
    _CommunitySignProvider(
        token_field="SklandToken",
        log_name="森空岛",
        runner=_run_skland_provider,
        resolve_platforms=_fixed_platforms("森空岛"),
        error_game=_default_error_game,
    ),
    _CommunitySignProvider(
        token_field="MiyousheToken",
        log_name="米游社",
        runner=_run_miyoushe_provider,
        resolve_platforms=_fixed_platforms("米游社"),
        error_game=_default_error_game,
    ),
    _CommunitySignProvider(
        token_field="KuroToken",
        log_name="库街区",
        runner=_run_kuro_provider,
        resolve_platforms=_fixed_platforms("库街区"),
        error_game=_default_error_game,
    ),
    _CommunitySignProvider(
        token_field="TaygedoToken",
        log_name="塔吉多",
        runner=_run_taygedo_provider,
        resolve_platforms=_resolve_taygedo_platforms,
        error_game=_taygedo_error_game,
    ),
)
COMMUNITY_TOKEN_FIELDS = tuple(
    provider.token_field for provider in _COMMUNITY_SIGN_PROVIDERS
)
# 历史名称只保留为兼容引用，注册表和字段清单仍各有唯一实例。
_ProviderRun = _CommunityProviderRun
_GameSignProvider = _CommunitySignProvider
_GAME_SIGN_PROVIDERS = _COMMUNITY_SIGN_PROVIDERS
GAME_SIGN_TOKEN_FIELDS = COMMUNITY_TOKEN_FIELDS


def read_community_token(account: object, field: str) -> str:
    """读取凭据字段，兼容旧版本尚未包含新增字段的账号对象。"""

    try:
        value = account.get("GameSignAccount", field)  # type: ignore[attr-defined]
    except (AttributeError, KeyError):
        return ""
    return value.strip() if isinstance(value, str) else str(value or "").strip()


def has_community_credentials(account: object) -> bool:
    """判断账号是否至少配置一个已注册社区凭据。"""

    return any(
        is_community_credential_configured(
            field,
            read_community_token(account, field),
        )
        for field in COMMUNITY_TOKEN_FIELDS
    )


def _provider_error_results(
    provider: _CommunitySignProvider,
    *,
    platforms: tuple[str, ...],
    account_name: str,
    account_uid: str,
    reason: str,
) -> list[dict]:
    return [
        CommunitySignResult(
            account=f"{account_name}/{platform}",
            account_uid=account_uid,
            game=provider.error_game(platform),
            platform=platform,
            status="失败",
            reason=reason,
        ).to_legacy()
        for platform in platforms
    ]


def _resolved_provider_platforms(
    provider: _CommunitySignProvider, token: str
) -> tuple[str, ...]:
    try:
        platforms = provider.resolve_platforms(token)
    except Exception as e:
        logger.debug(f"{provider.log_name} 凭据解析跳过: {e}")
        return ()
    return tuple(dict.fromkeys(platform for platform in platforms if platform))


def _decorate_provider_run(
    run: _CommunityProviderRun,
    *,
    fallback_platforms: tuple[str, ...],
    account_name: str,
    account_uid: str,
) -> _CommunityProviderRun:
    platforms = run.platforms or fallback_platforms
    normalized = []
    for raw_item in run.results:
        if not isinstance(raw_item, dict):
            continue
        normalized.append(
            CommunitySignResult.from_legacy(
                raw_item,
                fallback_account=account_name,
                fallback_uid=account_uid,
            ).to_legacy()
        )

    for platform in platforms:
        if not any(item.get("platform") == platform for item in normalized):
            normalized.append(
                _empty_platform_result(
                    account_name=account_name,
                    account_uid=account_uid,
                    platform=platform,
                )
            )

    return _CommunityProviderRun(
        results=normalized,
        platforms=platforms,
        credential_updates=dict(run.credential_updates),
    )


def _is_expected_provider_exception(error: Exception) -> bool:
    """判断可预期的凭据、上游或网络失败。"""

    if isinstance(
        error,
        (ValueError, httpx.HTTPError, TimeoutError, ConnectionError),
    ):
        return True
    if not isinstance(error, RuntimeError):
        return False

    message = str(error).lower()
    return any(
        hint in message
        for hint in (
            "token",
            "cookie",
            "凭据",
            "登录",
            "风控",
            "请求",
            "接口",
            "网络",
            "offline",
            "timeout",
            "timed out",
        )
    )


async def run_community_provider(
    provider: _CommunitySignProvider,
    token: str,
    *,
    account_name: str,
    account_uid: str,
    on_credential_update: CredentialUpdateCallback | None = None,
) -> _CommunityProviderRun:
    fallback_platforms = _resolved_provider_platforms(provider, token)
    logger.info(f"[{account_name}] 开始{provider.log_name}社区签到")
    credential_status = validate_community_credential(
        provider.token_field,
        token,
    )
    if not credential_status.locally_valid:
        reason = credential_status.reason or f"{provider.log_name}凭据格式无效"
        logger.warning(f"[{account_name}] {provider.log_name}凭据校验失败: {reason}")
        return _CommunityProviderRun(
            results=_provider_error_results(
                provider,
                platforms=fallback_platforms,
                account_name=account_name,
                account_uid=account_uid,
                reason=reason,
            ),
            platforms=fallback_platforms,
        )
    try:
        if on_credential_update is None:
            # 保留第三方/历史适配器的三参数 runner 兼容性；内置社区 runner
            # 均支持第四个回写回调。
            run = await provider.runner(token, account_name, account_uid)  # type: ignore[call-arg]
        else:
            run = await provider.runner(
                token,
                account_name,
                account_uid,
                on_credential_update,
            )
    except Exception as e:
        expected = _is_expected_provider_exception(e)
        reason = format_exception_reason(
            e,
            stage=f"{provider.log_name}社区签到失败",
            include_message=expected,
        )
        if expected:
            logger.warning(f"[{account_name}] {reason}")
        else:
            logger.exception(f"{provider.log_name}社区签到程序异常")
        return _CommunityProviderRun(
            results=_provider_error_results(
                provider,
                platforms=fallback_platforms,
                account_name=account_name,
                account_uid=account_uid,
                reason=reason,
            ),
            platforms=fallback_platforms,
        )
    return _decorate_provider_run(
        run,
        fallback_platforms=fallback_platforms,
        account_name=account_name,
        account_uid=account_uid,
    )


async def _run_all_sign_in(force: bool = False) -> list[dict]:
    """兼容旧内部调用，转发到社区签到核心编排。"""

    return await run_all_sign_in(force=force)


def merge_community_sign_results(
    existing: dict, formatted: dict, replace: bool = False
) -> dict:
    """将新签到结果合并到已有结果中

    Args:
        existing: 已有的 _game_sign_result_data
        formatted: 本次 format_community_sign_results 的新结果
        replace: 保留该参数以兼容现有调用；受影响账号均按 account_uid 替换旧数据。

    Returns:
        合并后的 _game_sign_result_data
    """
    if not existing:
        return formatted

    for platform, accounts in formatted.items():
        if platform not in existing:
            existing[platform] = accounts
        else:
            # 手动和自动签到都替换受影响账号，避免旧成功状态遮蔽新失败结果。
            new_uids = {g.get("account_uid") for g in accounts if g.get("account_uid")}
            if new_uids:
                existing[platform] = [
                    g
                    for g in existing[platform]
                    if g.get("account_uid") not in new_uids
                ]
            existing[platform].extend(accounts)

    return existing


def format_community_sign_results(results: list[dict]) -> dict:
    """将签到结果格式化为前端可展示的结构

    按平台分组，平台内按账号 UID 聚合

    Returns:
        {platform: [{account_alias, account_uid, games: [{account, game, status, reward, reason}]}]}
    """
    platforms: dict[str, dict[str, dict]] = {}

    for item in results:
        if item.get("_notification_only"):
            continue
        platform = item.get("platform", "未知")
        account = str(item.get("account", "未知"))
        account_uid = str(item.get("account_uid", ""))
        # 别名 = account 中 '/' 前的部分
        alias = account.split("/")[0] if "/" in account else account
        group_key = account_uid or f"alias:{alias}"

        if platform not in platforms:
            platforms[platform] = {}

        if group_key not in platforms[platform]:
            platforms[platform][group_key] = {
                "account_alias": alias,
                "account_uid": account_uid,
                "games": [],
            }

        platforms[platform][group_key]["games"].append(
            {
                "account": account,
                "game": item.get("game", "未知"),
                "status": item.get("status", "失败"),
                "reward": item.get("reward", ""),
                "reason": item.get("reason", ""),
            }
        )

    # 转为列表格式
    result = {}
    for platform, accounts in platforms.items():
        result[platform] = list(accounts.values())

    return result


# 旧模块继续暴露历史符号，实际签到调度由 app.core.community_sign 承载。
_check_system_time = check_community_system_time
_read_game_sign_token = read_community_token
has_game_sign_credentials = has_community_credentials
_run_provider = run_community_provider


def _game_sign_providers() -> tuple[_CommunitySignProvider, ...]:
    """兼容旧内部调用，返回历史注册表别名。"""

    return _GAME_SIGN_PROVIDERS


def merge_sign_results(
    existing: dict, formatted: dict, replace: bool = False
) -> dict:
    """兼容旧调用方，合并社区签到结果。"""

    return merge_community_sign_results(existing, formatted, replace=replace)


def format_sign_results(results: list[dict]) -> dict:
    """兼容旧调用方，格式化社区签到结果。"""

    return format_community_sign_results(results)
