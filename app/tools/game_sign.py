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


import asyncio
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from typing import Awaitable, Callable

import httpx

from app.core import Config
from app.utils.constants import UTC8
from app.utils.logger import get_logger
from app.utils.security import format_exception_reason

from .game_sign_result import build_skland_sign_results

logger = get_logger("游戏社区签到")

_game_sign_lock = asyncio.Lock()
_game_sign_flow_lock = asyncio.Lock()
_game_sign_lock_owner: ContextVar[asyncio.Task | None] = ContextVar(
    "game_sign_lock_owner", default=None
)
_system_time_checked_at = 0.0
_SYSTEM_TIME_CHECK_INTERVAL = 300.0


@dataclass
class _ProviderRun:
    """单个社区适配器的结果和需要回写的凭据。"""

    results: list[dict]
    platforms: tuple[str, ...]
    credential_updates: dict[str, str] = field(default_factory=dict)


ProviderRunner = Callable[[str, str, str], Awaitable[_ProviderRun]]
PlatformResolver = Callable[[str], tuple[str, ...]]
ErrorGameResolver = Callable[[str], str]


@dataclass(frozen=True)
class _GameSignProvider:
    """以配置字段驱动的社区签到适配器描述。"""

    token_field: str
    log_name: str
    runner: ProviderRunner
    resolve_platforms: PlatformResolver
    error_game: ErrorGameResolver


class GameSignInProgressError(RuntimeError):
    """游戏社区签到已在执行。"""


@asynccontextmanager
async def game_sign_flow():
    """保护签到请求及结果落盘，通知由调用方在锁外发送。"""

    if _game_sign_flow_lock.locked():
        raise GameSignInProgressError("游戏社区签到正在执行，请稍后重试")

    await _game_sign_flow_lock.acquire()
    try:
        yield
    finally:
        _game_sign_flow_lock.release()


async def _enter_game_sign_lock() -> bool:
    """获取全局签到锁；同一任务嵌套调用时复用已持有的锁。"""

    current_task = asyncio.current_task()
    if current_task is not None and _game_sign_lock_owner.get() is current_task:
        return False

    if _game_sign_lock.locked():
        raise GameSignInProgressError("游戏社区签到正在执行，请稍后重试")

    await _game_sign_lock.acquire()
    _game_sign_lock_owner.set(current_task)
    return True


def _exit_game_sign_lock(acquired: bool) -> None:
    if not acquired:
        return
    _game_sign_lock_owner.set(None)
    _game_sign_lock.release()


def _all_enabled_platforms_signed(
    results: list[dict],
    *,
    account_uid: str,
    enabled_platforms: list[str],
) -> bool:
    """判断账号的全部已配置平台结果是否均已完成。"""

    if not enabled_platforms:
        return False

    for platform in enabled_platforms:
        platform_results = [
            result
            for result in results
            if result.get("account_uid") == account_uid
            and result.get("platform") == platform
        ]
        if not platform_results or any(
            result.get("status") not in ("成功", "已签到")
            and not result.get("_completed")
            for result in platform_results
        ):
            return False

    return True


async def _check_system_time() -> None:
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

    return {
        "account": account_name,
        "account_uid": account_uid,
        "game": "",
        "platform": platform,
        "status": "失败",
        "reward": "",
        "reason": "未获取到可签到角色",
        "_notification_only": True,
    }


async def run_all_sign_in(force: bool = False) -> list[dict]:
    """协调执行游戏社区签到，避免重复签到和重复通知。"""
    # 时间检查只提供告警，不应阻塞真实签到或占用签到锁。
    time_check_task = asyncio.create_task(_check_system_time())
    acquired = False
    try:
        acquired = await _enter_game_sign_lock()
        return await _run_all_sign_in(force=force)
    finally:
        _exit_game_sign_lock(acquired)
        if not time_check_task.done():
            time_check_task.cancel()
        await asyncio.gather(time_check_task, return_exceptions=True)


def _fixed_platforms(platform: str) -> PlatformResolver:
    return lambda _token: (platform,)


def _default_error_game(platform: str) -> str:
    return platform


def _taygedo_error_game(platform: str) -> str:
    return "幻塔社区" if platform == "塔吉多" else "云异环"


def _resolve_taygedo_platforms(raw_token: str) -> tuple[str, ...]:
    """根据塔吉多凭据字段确定实际启用的社区。"""

    try:
        from .taygedo import parse_taygedo_credential

        credential = parse_taygedo_credential(raw_token)
    except Exception:
        return ("塔吉多",)

    platforms = []
    if credential.get("refreshToken") or credential.get("accessToken"):
        platforms.append("塔吉多")
    if credential.get("cloudToken") and credential.get("cloudUserId"):
        platforms.append("云异环")
    return tuple(platforms) or ("塔吉多",)


async def _run_skland_provider(
    token: str, account_name: str, account_uid: str
) -> _ProviderRun:
    from .skland import skland_sign_in

    updated_token = ""

    async def capture_credential(value: str) -> None:
        nonlocal updated_token
        updated_token = str(value or "").strip()

    raw_result = await skland_sign_in(
        token,
        app_code="all",
        proxy=getattr(Config, "proxy", None),
        on_credential_update=capture_credential,
    )
    updates = {"SklandToken": updated_token} if updated_token else {}
    return _ProviderRun(
        results=build_skland_sign_results(
            raw_result,
            account_name=account_name,
            account_uid=account_uid,
        ),
        platforms=("森空岛",),
        credential_updates=updates,
    )


async def _run_miyoushe_provider(
    token: str, _account_name: str, _account_uid: str
) -> _ProviderRun:
    from .miyoushe import miyoushe_sign_in

    updated_token = ""

    async def capture_credential(value: str) -> None:
        nonlocal updated_token
        updated_token = str(value or "").strip()

    results = await miyoushe_sign_in(
        token,
        on_credential_update=capture_credential,
    )
    updates = {"MiyousheToken": updated_token} if updated_token else {}
    return _ProviderRun(
        results=results,
        platforms=("米游社",),
        credential_updates=updates,
    )


async def _run_kuro_provider(
    token: str, _account_name: str, _account_uid: str
) -> _ProviderRun:
    from .kuro import kuro_sign_in

    return _ProviderRun(
        results=await kuro_sign_in(token),
        platforms=("库街区",),
    )


async def _run_taygedo_provider(
    token: str, _account_name: str, _account_uid: str
) -> _ProviderRun:
    from .taygedo import (
        parse_taygedo_credential,
        serialize_taygedo_credential,
        sign_taygedo,
    )

    credential = parse_taygedo_credential(token)
    has_community = bool(
        credential.get("refreshToken") or credential.get("accessToken")
    )
    has_cloud = bool(credential.get("cloudToken") and credential.get("cloudUserId"))
    if not has_community and not has_cloud:
        raise ValueError(
            "塔吉多凭据缺少 refreshToken/accessToken 或 cloudToken/cloudUserId"
        )

    sign_results, refreshed_credential = await sign_taygedo(
        token,
        proxy=Config.proxy,
    )
    refreshed_token = serialize_taygedo_credential(refreshed_credential)
    updates = (
        {"TaygedoToken": refreshed_token}
        if refreshed_token and refreshed_token != str(token).strip()
        else {}
    )
    return _ProviderRun(
        results=sign_results,
        platforms=(),
        credential_updates=updates,
    )


def _game_sign_providers() -> tuple[_GameSignProvider, ...]:
    """返回按通知顺序排列的签到适配器注册表。"""

    return _GAME_SIGN_PROVIDERS


_GAME_SIGN_PROVIDERS = (
    _GameSignProvider(
        token_field="SklandToken",
        log_name="森空岛",
        runner=_run_skland_provider,
        resolve_platforms=_fixed_platforms("森空岛"),
        error_game=_default_error_game,
    ),
    _GameSignProvider(
        token_field="MiyousheToken",
        log_name="米游社",
        runner=_run_miyoushe_provider,
        resolve_platforms=_fixed_platforms("米游社"),
        error_game=_default_error_game,
    ),
    _GameSignProvider(
        token_field="KuroToken",
        log_name="库街区",
        runner=_run_kuro_provider,
        resolve_platforms=_fixed_platforms("库街区"),
        error_game=_default_error_game,
    ),
    _GameSignProvider(
        token_field="TaygedoToken",
        log_name="塔吉多",
        runner=_run_taygedo_provider,
        resolve_platforms=_resolve_taygedo_platforms,
        error_game=_taygedo_error_game,
    ),
)
GAME_SIGN_TOKEN_FIELDS = tuple(
    provider.token_field for provider in _GAME_SIGN_PROVIDERS
)


def _read_game_sign_token(account: object, field: str) -> str:
    """读取凭据字段，兼容旧版本尚未包含新增字段的账号对象。"""

    try:
        value = account.get("GameSignAccount", field)  # type: ignore[attr-defined]
    except (AttributeError, KeyError):
        return ""
    return value.strip() if isinstance(value, str) else str(value or "").strip()


def has_game_sign_credentials(account: object) -> bool:
    """判断账号是否至少配置一个已注册社区凭据。"""

    return any(
        _read_game_sign_token(account, field) for field in GAME_SIGN_TOKEN_FIELDS
    )


def _provider_error_results(
    provider: _GameSignProvider,
    *,
    platforms: tuple[str, ...],
    account_name: str,
    account_uid: str,
    reason: str,
) -> list[dict]:
    return [
        {
            "account": f"{account_name}/{platform}",
            "account_uid": account_uid,
            "game": provider.error_game(platform),
            "platform": platform,
            "status": "失败",
            "reward": "",
            "reason": reason,
        }
        for platform in platforms
    ]


def _resolved_provider_platforms(
    provider: _GameSignProvider, token: str
) -> tuple[str, ...]:
    try:
        platforms = provider.resolve_platforms(token)
    except Exception as e:
        logger.debug(f"{provider.log_name} 凭据解析跳过: {e}")
        return ()
    return tuple(dict.fromkeys(platform for platform in platforms if platform))


def _decorate_provider_run(
    run: _ProviderRun,
    *,
    fallback_platforms: tuple[str, ...],
    account_name: str,
    account_uid: str,
) -> _ProviderRun:
    platforms = run.platforms or fallback_platforms
    normalized = []
    for raw_item in run.results:
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        if not item.get("account") or item.get("account") == "未知用户":
            item["account"] = account_name
        item["account_uid"] = account_uid
        normalized.append(item)

    for platform in platforms:
        if not any(item.get("platform") == platform for item in normalized):
            normalized.append(
                _empty_platform_result(
                    account_name=account_name,
                    account_uid=account_uid,
                    platform=platform,
                )
            )

    return _ProviderRun(
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


async def _run_provider(
    provider: _GameSignProvider,
    token: str,
    *,
    account_name: str,
    account_uid: str,
) -> _ProviderRun:
    fallback_platforms = _resolved_provider_platforms(provider, token)
    logger.info(f"[{account_name}] 开始{provider.log_name}签到")
    try:
        run = await provider.runner(token, account_name, account_uid)
    except Exception as e:
        expected = _is_expected_provider_exception(e)
        reason = format_exception_reason(
            e,
            stage=f"{provider.log_name}签到失败",
            include_message=expected,
        )
        if expected:
            logger.warning(f"[{account_name}] {reason}")
        else:
            logger.exception(f"{provider.log_name}签到程序异常")
        return _ProviderRun(
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
    """执行所有已配置平台的签到。

    平台由凭据字段注册表驱动。同一账号的独立社区并发执行，适配器内部
    仍自行控制请求间隔和风控策略；凭据刷新结果在并发任务完成后统一落盘。
    """
    results = []
    today = datetime.now(tz=UTC8).strftime("%Y-%m-%d")

    providers = _game_sign_providers()
    for uid, account in Config.ToolsConfig.GameSign_Accounts.items():
        account_name = account.get("GameSignAccount", "Name") or "默认账号"
        account_enabled = account.get("GameSignAccount", "Enabled")
        account_uid = str(uid)

        # 跳过已禁用的用户
        if not account_enabled:
            continue

        # 非强制模式：跳过今日已签到的用户
        if not force:
            user_last_sign = account.get("GameSignAccount", "LastSignDate")
            if user_last_sign == today:
                logger.debug(f"[{account_name}] 今日已签到，跳过")
                continue

        tokens = {
            provider.token_field: _read_game_sign_token(account, provider.token_field)
            for provider in providers
        }
        configured = [
            provider for provider in providers if tokens.get(provider.token_field)
        ]
        if not configured:
            continue

        # 不同社区互不依赖，按注册顺序并发执行，完成后仍按固定顺序合并结果。
        provider_runs = await asyncio.gather(
            *(
                _run_provider(
                    provider,
                    tokens[provider.token_field],
                    account_name=account_name,
                    account_uid=account_uid,
                )
                for provider in configured
            )
        )
        enabled_platforms = []
        for provider, run in zip(configured, provider_runs):
            for platform in run.platforms:
                if platform not in enabled_platforms:
                    enabled_platforms.append(platform)
            results.extend(run.results)
            for token_field, updated_token in run.credential_updates.items():
                if not updated_token or updated_token == tokens.get(token_field, ""):
                    continue
                try:
                    await account.set("GameSignAccount", token_field, updated_token)
                except Exception as e:
                    logger.warning(f"[{account_name}] 保存{token_field}失败: {e}")

        # 自动签到每天只尝试一次。失败也要记住当天的尝试，避免后续 MAS 任务反复请求；
        # 手动签到使用 force=True，仍只在所有已配置平台完成后更新日期。
        all_platforms_signed = _all_enabled_platforms_signed(
            results,
            account_uid=account_uid,
            enabled_platforms=enabled_platforms,
        )
        should_mark_signed = bool(enabled_platforms) and (
            not force or all_platforms_signed
        )
        if should_mark_signed:
            try:
                # 多账号串行签到可能跨越 0 点，写入时重新取当前日期，
                # 避免把新一天的签到记成旧日期导致次日误判。
                sign_date = datetime.now(tz=UTC8).strftime("%Y-%m-%d")
                await account.set("GameSignAccount", "LastSignDate", sign_date)
            except Exception as e:
                logger.warning(f"[{account_name}] 保存签到完成日期失败: {e}")

    if not results:
        logger.info("没有配置任何签到平台")

    return results


def merge_sign_results(existing: dict, formatted: dict, replace: bool = False) -> dict:
    """将新签到结果合并到已有结果中

    Args:
        existing: 已有的 _game_sign_result_data
        formatted: 本次 format_sign_results 的新结果
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


def format_sign_results(results: list[dict]) -> dict:
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
