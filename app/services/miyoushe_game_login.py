#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later
#
#   API protocol reference: Starward (MIT License)
#   Copyright (c) 2023 Scighost
#   https://github.com/Scighost/Starward

"""使用现有米游社会话获取原神官服角色和一次性登录票据。"""

from dataclasses import dataclass
from typing import Literal

import httpx
from pydantic import SecretStr

from app.services.community_http import create_community_client
from app.services.telemetry import private_operation

_VERIFY_URL = "https://passport-api.mihoyo.com/account/ma-cn-session/app/verify"
_COOKIE_URL = "https://api-takumi.mihoyo.com/auth/api/getCookieAccountInfoBySToken"
_ROLES_URL = "https://passport-api.mihoyo.com/binding/api/getUserGameRolesByCookieToken"
_TICKET_URL = "https://passport-api.mihoyo.com/account/ma-cn-verifier/app/createAuthTicketByGameBiz"

# Starward GameAuthLoginService.cs；公开示例确认可省略设备信息：
# https://github.com/Scighost/Starward/issues/1100
_PASSPORT_HEADERS = {
    "x-rpc-app_id": "ddxf5dufpuyo",
    "x-rpc-client_type": "3",
    "x-rpc-game_biz": "hyp_cn",
}

LoginFailureReason = Literal[
    "account_missing",
    "credential_incomplete",
    "credential_invalid",
    "unsupported_region",
    "role_not_owned",
    "network_error",
    "upstream_rejected",
    "invalid_response",
]
_FAILURE_MESSAGES: dict[LoginFailureReason, str] = {
    "account_missing": "未找到绑定的米游社社区账号",
    "credential_incomplete": "米游社凭据不完整，请重新扫码登录",
    "credential_invalid": "米游社凭据无法验证，请重新扫码登录",
    "unsupported_region": "米游社网页登录仅支持原神官服",
    "role_not_owned": "所选原神角色已不属于绑定的米游社账号",
    "network_error": "米游社登录请求失败，请稍后重试",
    "upstream_rejected": "米游社拒绝登录请求，请重新扫码或稍后重试",
    "invalid_response": "米游社登录响应无法识别，请稍后重试",
}


class MiyousheGameLoginError(ValueError):
    """只包含固定原因与文案，不保存上游异常或请求响应。"""

    def __init__(self, reason: LoginFailureReason) -> None:
        self.reason = reason
        self.code = (
            404
            if reason == "account_missing"
            else 502
            if reason in ("network_error", "upstream_rejected", "invalid_response")
            else 400
        )
        super().__init__(_FAILURE_MESSAGES[reason])


@dataclass(frozen=True)
class GenshinLoginRole:
    uid: str
    region: Literal["cn_gf01"]
    nickname: str = ""
    region_name: str = ""


@dataclass(frozen=True)
class _LoginResult:
    roles: tuple[GenshinLoginRole, ...]
    ticket: SecretStr | None = None


async def _request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs,
) -> dict[str, object]:
    # 原始 HTTP 异常、响应正文和局部凭据只留在 private_operation 内。
    try:
        request = client.build_request(method, url, timeout=30.0, **kwargs)
        response = await client.send(request)
        response.raise_for_status()
    except Exception:
        raise MiyousheGameLoginError("network_error") from None
    try:
        payload = response.json()
    except Exception:
        raise MiyousheGameLoginError("invalid_response") from None
    if not isinstance(payload, dict) or "retcode" not in payload:
        raise MiyousheGameLoginError("invalid_response")
    if payload["retcode"] != 0:
        raise MiyousheGameLoginError("upstream_rejected")
    return payload


def _response_data(payload: dict[str, object]) -> dict[str, object]:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise MiyousheGameLoginError("invalid_response")
    return data


async def _run_session_requests(
    cookie: SecretStr,
    *,
    role_uid: str | None,
    role_region: str,
    proxy: str | None,
) -> _LoginResult:
    from app.tools.miyoushe import BASE_HEADERS, prepare_miyoushe_session

    session = prepare_miyoushe_session(cookie.get_secret_value())
    stoken = session.cookies.get("stoken_v2") or session.cookies.get("stoken", "")
    mid = session.cookies.get("mid", "")
    if (
        not session.uid.isascii()
        or not session.uid.isdecimal()
        or int(session.uid) <= 0
        or not stoken.startswith("v2_")
        or not mid
    ):
        raise MiyousheGameLoginError("credential_incomplete")
    if role_uid is not None and role_region != "cn_gf01":
        raise MiyousheGameLoginError("unsupported_region")

    async with create_community_client(proxy=proxy) as client:
        identity = _response_data(
            await _request_json(
                client,
                "POST",
                _VERIFY_URL,
                headers=_PASSPORT_HEADERS,
                json={
                    "token": {"token_type": 1, "token": stoken},
                    # 身份查询不轮换凭据，后续仍使用同一 stoken/mid：
                    # MihoyoBBSAutoSigner 7c6c9c84 TrayApp/stoken_login.py fetch_stuid。
                    "refresh": False,
                    "mid": mid,
                },
            )
        ).get("user_info")
        if (
            not isinstance(identity, dict)
            or str(identity.get("aid", "")) != session.uid
            or identity.get("mid") != mid
        ):
            raise MiyousheGameLoginError("credential_invalid")

        # 每次从已验证的 stoken 派生 Cookie，避免混用另一账号的旧 cookie_token。
        cookie_data = _response_data(
            await _request_json(
                client,
                "GET",
                _COOKIE_URL,
                headers={**BASE_HEADERS, "x-rpc-device_id": session.device_id},
                cookies={"stoken": stoken, "mid": mid, "stuid": session.uid},
            )
        )
        cookie_token = cookie_data.get("cookie_token")
        if (
            not isinstance(cookie_token, str)
            or not cookie_token
            or str(cookie_data.get("uid", "")) != session.uid
        ):
            raise MiyousheGameLoginError("credential_invalid")
        cookies = session.cookies.copy()
        cookies.update(
            {
                "cookie_token": cookie_token,
                "cookie_token_v2": cookie_token,
                "account_id": session.uid,
                "account_id_v2": session.uid,
                "ltuid": session.uid,
                "ltuid_v2": session.uid,
            }
        )
        role_list = _response_data(
            await _request_json(
                client,
                "GET",
                _ROLES_URL,
                params={"game_biz": "hk4e_cn"},
                headers={"Referer": "https://act.mihoyo.com/"},
                cookies=cookies,
            )
        ).get("list")
        if not isinstance(role_list, list):
            raise MiyousheGameLoginError("invalid_response")
        roles: list[GenshinLoginRole] = []
        for role in role_list:
            if not isinstance(role, dict):
                raise MiyousheGameLoginError("invalid_response")
            if role.get("game_biz") != "hk4e_cn" or role.get("region") != "cn_gf01":
                continue
            uid = str(role.get("game_uid", ""))
            nickname = role.get("nickname") or ""
            region_name = role.get("region_name") or ""
            if (
                not uid.isascii()
                or not uid.isdecimal()
                or not isinstance(nickname, str)
                or not isinstance(region_name, str)
            ):
                raise MiyousheGameLoginError("invalid_response")
            roles.append(
                GenshinLoginRole(
                    uid=uid,
                    region="cn_gf01",
                    nickname=nickname,
                    region_name=region_name,
                )
            )
        if role_uid is None:
            return _LoginResult(roles=tuple(roles))
        if not any(
            role.uid == role_uid and role.region == role_region for role in roles
        ):
            raise MiyousheGameLoginError("role_not_owned")
        ticket = _response_data(
            await _request_json(
                client,
                "POST",
                _TICKET_URL,
                headers=_PASSPORT_HEADERS,
                json={
                    "game_biz": "hk4e_cn",
                    "stoken": stoken,
                    "uid": int(session.uid),
                    "mid": mid,
                },
            )
        ).get("ticket")
        if (
            not isinstance(ticket, str)
            or not ticket
            or len(ticket) > 4096
            or any(
                character.isspace() or ord(character) < 32 or ord(character) == 127
                for character in ticket
            )
        ):
            raise MiyousheGameLoginError("invalid_response")
        return _LoginResult(roles=tuple(roles), ticket=SecretStr(ticket))


async def _run_private_session(
    cookie: SecretStr,
    *,
    role_uid: str | None,
    role_region: str,
    proxy: str | None,
) -> _LoginResult:
    reason: LoginFailureReason = "network_error"
    with private_operation():
        try:
            return await _run_session_requests(
                cookie,
                role_uid=role_uid,
                role_region=role_region,
                proxy=proxy,
            )
        except MiyousheGameLoginError as error:
            reason = error.reason
        except Exception:
            pass
    # 新异常在 except 和私密请求栈之外抛出，不携带原 traceback/context。
    raise MiyousheGameLoginError(reason) from None


async def fetch_genshin_roles(
    cookie: str | SecretStr,
    *,
    proxy: str | None = None,
) -> tuple[GenshinLoginRole, ...]:
    """校验当前登录凭据并返回绑定的原神官服角色，不返回凭据。"""

    cookie = cookie if isinstance(cookie, SecretStr) else SecretStr(cookie)
    result = await _run_private_session(
        cookie, role_uid=None, role_region="cn_gf01", proxy=proxy
    )
    return result.roles


async def request_genshin_login_ticket(
    cookie: str | SecretStr,
    *,
    role_uid: str,
    role_region: str,
    proxy: str | None = None,
) -> SecretStr:
    """验证角色归属后换取账号级一次性票据，仅供后台启动游戏使用。

    票据不指定角色；启动流程仍须通过脚本公开入口确认实际登录的角色 UID。
    """

    cookie = cookie if isinstance(cookie, SecretStr) else SecretStr(cookie)
    result = await _run_private_session(
        cookie, role_uid=role_uid, role_region=role_region, proxy=proxy
    )
    if result.ticket is None:
        raise MiyousheGameLoginError("invalid_response")
    return result.ticket
