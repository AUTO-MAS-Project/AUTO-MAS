#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""从已保存的社区账号读取米游社凭据，供角色选择和后台登录使用。"""

from dataclasses import dataclass
from uuid import UUID

from pydantic import SecretStr

from app.services.miyoushe_game_login import (
    GenshinLoginRole,
    MiyousheGameLoginError,
    fetch_genshin_roles,
    request_genshin_login_ticket,
)


@dataclass(frozen=True)
class GenshinLoginAccount:
    uid: str
    name: str
    has_credentials: bool


def list_genshin_login_accounts() -> tuple[GenshinLoginAccount, ...]:
    """只返回账号名与配置状态，凭据不进入角色选择接口。"""

    from app.core import Config
    from app.tools.community_sign_provider import read_community_token

    try:
        return tuple(
            GenshinLoginAccount(
                uid=str(uid),
                name=str(account.get("GameSignAccount", "Name") or "用户"),
                has_credentials=bool(read_community_token(account, "MiyousheToken")),
            )
            for uid, account in Config.ToolsConfig.GameSign_Accounts.items()
        )
    except Exception:
        # 配置或解密异常也只通过固定原因离开凭据边界。
        pass
    raise MiyousheGameLoginError("credential_invalid") from None


def _read_login_cookie(account_uid: UUID | str) -> SecretStr:
    from app.core import Config
    from app.tools.community_sign_provider import read_community_token

    reason = "account_missing"
    try:
        account = Config.ToolsConfig.GameSign_Accounts[UUID(str(account_uid))]
    except (KeyError, ValueError):
        pass
    else:
        try:
            return SecretStr(read_community_token(account, "MiyousheToken"))
        except Exception:
            reason = "credential_invalid"
    if reason == "account_missing":
        raise MiyousheGameLoginError("account_missing") from None
    raise MiyousheGameLoginError("credential_invalid") from None


async def fetch_configured_genshin_roles(
    account_uid: UUID | str,
) -> tuple[GenshinLoginRole, ...]:
    from app.core import Config

    return await fetch_genshin_roles(
        _read_login_cookie(account_uid), proxy=Config.proxy
    )


async def request_configured_genshin_login_ticket(
    account_uid: UUID | str,
    *,
    role_uid: str,
    role_region: str,
) -> SecretStr:
    """票据仅在内存中交给游戏启动流程，不通过 HTTP 返回。"""

    from app.core import Config

    return await request_genshin_login_ticket(
        _read_login_cookie(account_uid),
        role_uid=role_uid,
        role_region=role_region,
        proxy=Config.proxy,
    )
