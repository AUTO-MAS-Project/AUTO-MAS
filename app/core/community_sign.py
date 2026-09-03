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


"""游戏社区签到核心编排，平台请求仍由唯一 provider 注册表承载。"""

import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import datetime

from app.tools.community_sign_provider import (
    check_community_system_time,
    get_community_sign_providers,
    read_community_token,
    run_community_provider,
)
from app.tools.community_contract import CommunitySignInProgressError, CommunitySignResult
from app.tools.community_credentials import is_community_credential_configured
from app.utils.constants import UTC8
from app.utils.logger import get_logger

from .config import Config

__all__ = [
    "CommunitySignInProgressError",
    "all_enabled_community_platforms_signed",
    "community_sign_flow",
    "run_community_sign_in",
]


logger = get_logger("游戏社区签到")

_community_sign_lock = asyncio.Lock()
_community_sign_flow_lock = asyncio.Lock()
_community_sign_lock_owner: ContextVar[asyncio.Task | None] = ContextVar(
    "community_sign_lock_owner", default=None
)


@asynccontextmanager
async def community_sign_flow():
    """保护签到请求及结果落盘，通知由调用方在锁外发送。"""

    if _community_sign_flow_lock.locked():
        raise CommunitySignInProgressError("游戏社区签到正在执行，请稍后重试")

    await _community_sign_flow_lock.acquire()
    try:
        yield
    finally:
        _community_sign_flow_lock.release()


async def _enter_community_sign_lock() -> bool:
    """获取全局签到锁；同一任务嵌套调用时复用已持有的锁。"""

    current_task = asyncio.current_task()
    if current_task is not None and _community_sign_lock_owner.get() is current_task:
        return False

    if _community_sign_lock.locked():
        raise CommunitySignInProgressError("游戏社区签到正在执行，请稍后重试")

    await _community_sign_lock.acquire()
    _community_sign_lock_owner.set(current_task)
    return True


def _exit_community_sign_lock(acquired: bool) -> None:
    if not acquired:
        return
    _community_sign_lock_owner.set(None)
    _community_sign_lock.release()


def all_enabled_community_platforms_signed(
    results: list[dict[str, object]],
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


async def run_community_sign_in(force: bool = False) -> list[dict[str, object]]:
    """协调执行游戏社区签到，避免重复签到和重复通知。"""

    # 时间检查只提供告警，不应阻塞真实签到或占用签到锁。
    time_check_task = asyncio.create_task(check_community_system_time())
    acquired = False
    try:
        acquired = await _enter_community_sign_lock()
        return await _run_configured_community_sign_in(force=force)
    finally:
        _exit_community_sign_lock(acquired)
        if not time_check_task.done():
            time_check_task.cancel()
        await asyncio.gather(time_check_task, return_exceptions=True)


async def _run_configured_community_sign_in(
    force: bool = False,
) -> list[dict[str, object]]:
    """执行所有已配置平台的签到。

    平台由凭据字段注册表驱动。同一账号的独立社区并发执行，适配器内部
    仍自行控制请求间隔和风控策略；凭据刷新结果优先即时回写，收尾阶段再统一兜底。
    """

    results: list[dict[str, object]] = []
    today = datetime.now(tz=UTC8).strftime("%Y-%m-%d")

    providers = get_community_sign_providers()
    for uid, account in Config.ToolsConfig.GameSign_Accounts.items():
        account_name = account.get("GameSignAccount", "Name") or "默认账号"
        account_enabled = account.get("GameSignAccount", "Enabled")
        account_uid = str(uid)

        # 跳过已禁用的用户。
        if not account_enabled:
            continue

        # 非强制模式：跳过今日已签到的用户。
        if not force:
            user_last_sign = account.get("GameSignAccount", "LastSignDate")
            if user_last_sign == today:
                logger.debug(f"[{account_name}] 今日已签到，跳过")
                continue

        tokens = {
            provider.token_field: read_community_token(
                account, provider.token_field
            )
            for provider in providers
        }
        runtime_tokens = dict(tokens)
        miyoushe_token = tokens.get("MiyousheToken", "")
        if is_community_credential_configured("MiyousheToken", miyoushe_token):
            # 云原神只在本轮从米游社 Cookie 换取临时凭据；旧字段继续作为
            # 没有米游社凭据时的兼容后备，不回写临时 token。
            runtime_tokens["CloudGenshinToken"] = miyoushe_token
        configured = [
            provider
            for provider in providers
            if is_community_credential_configured(
                provider.token_field,
                runtime_tokens.get(provider.token_field, ""),
            )
        ]
        if not configured:
            continue

        credential_update_lock = asyncio.Lock()
        credential_update_failures: dict[str, str] = {}
        credential_update_platforms: dict[str, tuple[str, ...]] = {}

        async def save_credential_update(
            field: str,
            value: str,
            *,
            retry: bool,
        ) -> bool:
            """保存轮换凭据；失败时保留旧值并返回可展示的稳定状态。"""

            updated_token = str(value or "").strip()
            if not updated_token or updated_token == tokens.get(field, ""):
                return True

            attempts = 2 if retry else 1
            for attempt in range(attempts):
                try:
                    # 直接 set 不重置 LastSignDate；刷新凭据不应改变签到去重语义。
                    await account.set("GameSignAccount", field, updated_token)
                except Exception as error:
                    if attempt + 1 < attempts:
                        logger.warning(
                            f"[{account_name}] 保存{field}失败，将重试: {type(error).__name__}"
                        )
                        continue
                    reason = "刷新凭据已生成，但保存失败，请稍后重试或重新登录"
                    credential_update_failures[field] = reason
                    logger.warning(
                        f"[{account_name}] 保存{field}失败: {type(error).__name__}"
                    )
                    return False
                else:
                    tokens[field] = updated_token
                    credential_update_failures.pop(field, None)
                    return True
            return False

        async def persist_credential_update(field: str, value: str) -> None:
            """在社区运行期间写穿轮换凭据，失败时交给收尾兜底。"""

            if not str(value or "").strip():
                return
            async with credential_update_lock:
                saved = await save_credential_update(field, value, retry=False)
                if not saved:
                    # 让内置 provider 保留其既有收尾兜底，同时由本层记录失败状态。
                    raise RuntimeError(f"{field}凭据保存失败")

        # 不同社区互不依赖，按注册顺序并发执行，完成后仍按固定顺序合并结果。
        provider_runs = await asyncio.gather(
            *(
                run_community_provider(
                    provider,
                    runtime_tokens[provider.token_field],
                    account_name=account_name,
                    account_uid=account_uid,
                    on_credential_update=persist_credential_update,
                )
                for provider in configured
            )
        )
        enabled_platforms: list[str] = []
        for provider, run in zip(configured, provider_runs):
            for platform in run.platforms:
                if platform not in enabled_platforms:
                    enabled_platforms.append(platform)
            results.extend(run.results)
            for field, updated_token in run.credential_updates.items():
                credential_update_platforms[field] = run.platforms or (provider.log_name,)
                if not updated_token or updated_token == tokens.get(field, ""):
                    continue
                async with credential_update_lock:
                    await save_credential_update(field, updated_token, retry=True)

        for field, reason in credential_update_failures.items():
            platforms = credential_update_platforms.get(field, (field,))
            provider = next(
                (item for item in configured if item.token_field == field),
                None,
            )
            provider_name = provider.log_name if provider is not None else field
            results.extend(
                CommunitySignResult(
                    account=f"{account_name}/{platform}",
                    account_uid=account_uid,
                    game=f"{provider_name}凭据",
                    platform=platform,
                    status="失败",
                    reason=reason,
                ).to_legacy()
                for platform in platforms
            )

        # 自动签到每天只尝试一次。失败也要记住当天的尝试，避免后续 MAS 任务反复请求；
        # 手动签到使用 force=True，仍只在所有已配置平台完成后更新日期。
        all_platforms_signed = all_enabled_community_platforms_signed(
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
            except Exception as error:
                logger.warning(f"[{account_name}] 保存签到完成日期失败: {error}")

    if not results:
        logger.info("没有配置任何社区平台")

    return results
