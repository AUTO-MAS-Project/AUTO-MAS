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


"""旧游戏签到模块兼容层；社区运行时实现位于 community_sign_provider。"""

import time
from contextlib import asynccontextmanager

from .community_contract import CommunitySignInProgressError
from .community_sign_provider import (
    COMMUNITY_TOKEN_FIELDS,
    CredentialUpdateCallback,
    ErrorGameResolver,
    PlatformResolver,
    ProviderRunner,
    _COMMUNITY_SIGN_PROVIDERS,
    _CommunityProviderRun,
    _CommunitySignProvider,
    _decorate_provider_run,
    _default_error_game,
    _empty_platform_result,
    _fixed_platforms,
    _is_expected_provider_exception,
    _provider_error_results,
    _resolve_taygedo_platforms,
    _resolved_provider_platforms,
    _run_kuro_provider,
    _run_miyoushe_provider,
    _run_skland_provider,
    _run_taygedo_provider,
    _taygedo_error_game,
    check_community_system_time as _check_community_system_time_impl,
    format_community_sign_results,
    get_community_sign_providers,
    get_community_token_field,
    has_community_credentials,
    merge_community_sign_results,
    read_community_token,
    run_community_provider,
)

GameSignInProgressError = CommunitySignInProgressError

# 历史名称只保留为同一对象的兼容引用，不复制社区注册表或执行逻辑。
_ProviderRun = _CommunityProviderRun
_GameSignProvider = _CommunitySignProvider
_GAME_SIGN_PROVIDERS = _COMMUNITY_SIGN_PROVIDERS
GAME_SIGN_TOKEN_FIELDS = COMMUNITY_TOKEN_FIELDS
_read_game_sign_token = read_community_token
has_game_sign_credentials = has_community_credentials
_run_provider = run_community_provider


async def check_community_system_time() -> None:
    """兼容旧时间补丁入口，转发到社区时间校验实现。"""

    await _check_community_system_time_impl(time_source=time)


_check_system_time = check_community_system_time


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
    results: list[dict[str, object]],
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


async def run_all_sign_in(force: bool = False) -> list[dict[str, object]]:
    """兼容旧调用方，转发到社区签到核心编排。"""

    from app.core.community_sign import run_community_sign_in

    return await run_community_sign_in(force=force)


async def _run_all_sign_in(force: bool = False) -> list[dict[str, object]]:
    """兼容旧内部调用，转发到社区签到核心编排。"""

    return await run_all_sign_in(force=force)


def _game_sign_providers() -> tuple[_CommunitySignProvider, ...]:
    """兼容旧内部调用，返回社区注册表的同一实例。"""

    return _GAME_SIGN_PROVIDERS


def merge_sign_results(
    existing: dict[str, list[dict[str, object]]],
    formatted: dict[str, list[dict[str, object]]],
    replace: bool = False,
) -> dict[str, list[dict[str, object]]]:
    """兼容旧调用方，合并社区签到结果。"""

    return merge_community_sign_results(existing, formatted, replace=replace)


def format_sign_results(
    results: list[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    """兼容旧调用方，格式化社区签到结果。"""

    return format_community_sign_results(results)
