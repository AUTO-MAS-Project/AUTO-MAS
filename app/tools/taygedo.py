#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file incorporates API compatibility knowledge from the following
#   projects. Password login is adapted for one-time local use; SMS login is
#   intentionally not used here:
#       taygedo-auto-attendance Copyright © 2026 zzstar101
#       NTE-Auto-Sign Copyright © 2026 Candy-QAQ
#       https://github.com/zzstar101/taygedo-auto-attendance
#       https://github.com/Candy-QAQ/NTE-Auto-Sign
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published
#   by the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""塔吉多社区签到和云异环时长服务。

凭据字段支持两种形式：完整 JSON 对象，或只包含 refreshToken 的纯文本。
JSON 形式与公开参考项目的账号结构兼容，可选携带 cloudToken/cloudUserId。
账号密码只用于一次性换取 Token，不会写入本地配置；本模块不实现短信或未经验证的二维码登录。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import string
import time
from collections.abc import Mapping
from typing import Any

import httpx
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from app.utils.logger import get_logger
from app.utils.security import format_exception_reason

logger = get_logger("塔吉多签到")

TAYGEDO_BASE_URL = "https://bbs-api.tajiduo.com"
LAOHU_BASE_URL = "https://user.laohu.com"
REFRESH_TOKEN_URL = f"{TAYGEDO_BASE_URL}/usercenter/api/refreshToken"
USER_CENTER_LOGIN_URL = f"{TAYGEDO_BASE_URL}/usercenter/api/login"
GAME_ROLES_URL = f"{TAYGEDO_BASE_URL}/usercenter/api/v2/getGameRoles"
GAME_RECORD_CARDS_URL = f"{TAYGEDO_BASE_URL}/apihub/api/getGameRecordCard"
APP_SIGNIN_URL = f"{TAYGEDO_BASE_URL}/apihub/api/signin"
GAME_SIGNIN_STATE_URL = f"{TAYGEDO_BASE_URL}/apihub/awapi/signin/state"
GAME_SIGNIN_URL = f"{TAYGEDO_BASE_URL}/apihub/awapi/sign"
CLOUD_USER_INFO_URL = "https://user.laohu.com/cloud/game/getUserInfo"

DEFAULT_GAME_ID = "1289"
TAYGEDO_GAME_IDS = ("1256", "1257", "1289")
TAYGEDO_GAME_NAMES = {
    "1256": "幻塔",
    "1257": "异环",
    "1289": "异环",
}
APP_VERSION = "1.1.0"
# 用户中心刷新接口仍使用 1.1.0；角色卡、角色列表和社区接口使用当前原生协议版本。
TAYGEDO_NATIVE_APP_VERSION = "1.2.5"
TAYGEDO_COMMUNITY_IDS = ("1", "2")
TAYGEDO_COMMUNITY_NAMES = {
    "1": "幻塔社区",
    "2": "异环社区",
}
APP_USER_AGENT = "okhttp/4.12.0"
TAYGEDO_LOGIN_APP_ID = "10551"
TAYGEDO_LOGIN_APP_VERSION = "1.2.5"
TAYGEDO_LOGIN_DS_SECRET = "pUds3dfMkl"

LAOHU_SECRET = "89155cc4e8634ec5b1b6364013b23e3e"
LAOHU_APP_ID = "10550"
LAOHU_CHANNEL_ID = "1"
LAOHU_VERSION_CODE = "17"
LAOHU_SDK_VERSION = "4.327.0"
LAOHU_DEVICE_MODEL = "Pixel 6"
LAOHU_DEVICE_SYS = "14"
LAOHU_USER_AGENT = (
    "LaohuSDK/4.327.0 (android os 14;mobile manufacturer Google; model Pixel 6)"
)
LAOHU_LOGIN_URL = f"{LAOHU_BASE_URL}/openApi/secureLogin"

CLOUD_APP_ID = "10597"
CLOUD_APP_KEY = "f1b7f11fc3774f898e387368cce4da04"
CLOUD_CHANNEL_ID = "9"
CLOUD_BID = "com.pwrd.cloud.yh.laohu"
CLOUD_SDK_VERSION = "1.34.0"
CLOUD_APP_VERSION = "1.1.0"


def _is_expected_taygedo_exception(error: Exception) -> bool:
    """判断可预期的凭据、上游或网络失败。"""

    return isinstance(
        error,
        (ValueError, httpx.HTTPError, TimeoutError, ConnectionError),
    )


def _log_taygedo_exception(stage: str, error: Exception) -> str:
    """按异常类型记录塔吉多失败，并返回安全的非空原因。"""

    expected = _is_expected_taygedo_exception(error)
    reason = format_exception_reason(
        error,
        stage=stage,
        include_message=expected,
    )
    if expected:
        logger.warning(reason)
    else:
        logger.exception(f"{stage}程序异常")
    return reason


def parse_taygedo_credential(raw: str) -> dict[str, Any]:
    """解析纯 refreshToken 或参考项目兼容的 JSON 凭据。"""

    text = str(raw or "").strip()
    if not text:
        return {}

    if text.startswith("{"):
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("塔吉多凭据 JSON 格式无效") from exc
        if not isinstance(value, dict):
            raise ValueError("塔吉多凭据必须是 JSON 对象")
        credential = dict(value)
    else:
        credential = {"refreshToken": text}

    aliases = {
        "refresh_token": "refreshToken",
        "access_token": "accessToken",
        "device_id": "deviceId",
        "cloud_token": "cloudToken",
        "cloud_user_id": "cloudUserId",
        "cloud_device_id": "cloudDeviceId",
        "role_name": "roleName",
    }
    for source, target in aliases.items():
        if target not in credential and credential.get(source) is not None:
            credential[target] = credential[source]

    for key in (
        "refreshToken",
        "accessToken",
        "uid",
        "deviceId",
        "gameId",
        "cloudToken",
        "cloudUserId",
        "cloudDeviceId",
        "cloudRemainingDuration",
        "roleName",
    ):
        if credential.get(key) is not None:
            credential[key] = str(credential[key]).strip()

    if isinstance(credential.get("roleIds"), str):
        credential["roleIds"] = [
            part.strip() for part in credential["roleIds"].split(",") if part.strip()
        ]

    # 丢弃不在已知游戏集合中的旧元数据，避免刷新凭据时复用未知角色名。
    if (
        credential.get("gameId") not in (None, "")
        and credential["gameId"] not in TAYGEDO_GAME_IDS
    ):
        credential.pop("gameId", None)
        credential.pop("roleName", None)
        credential.pop("roleIds", None)

    return credential


def serialize_taygedo_credential(credential: Mapping[str, Any]) -> str:
    """以稳定、可再次导入的 JSON 保存凭据，不写入日志。"""

    persisted: dict[str, Any] = {}
    for key in (
        "refreshToken",
        "accessToken",
        "uid",
        "deviceId",
        "gameId",
        "roleName",
        "cloudToken",
        "cloudUserId",
        "cloudDeviceId",
        "cloudRemainingDuration",
    ):
        value = credential.get(key)
        if value not in (None, ""):
            persisted[key] = str(value)
    role_ids = credential.get("roleIds")
    if isinstance(role_ids, list) and role_ids:
        persisted["roleIds"] = [str(item) for item in role_ids if str(item).strip()]
    return json.dumps(persisted, ensure_ascii=False, separators=(",", ":"))


async def login_taygedo_with_password(
    phone: str,
    password: str,
    *,
    existing_raw: str = "",
    device_id: str | None = None,
    proxy: str | None = None,
) -> dict[str, Any]:
    """一次性使用账号密码换取塔吉多访问凭据，不保存密码。"""

    phone_value = str(phone or "").strip()
    password_value = str(password or "")
    if not phone_value:
        raise ValueError("塔吉多账号或手机号为空")
    if not password_value:
        raise ValueError("塔吉多密码为空")

    try:
        credential = parse_taygedo_credential(existing_raw)
    except ValueError:
        # 新登录成功后会覆盖旧凭据，旧的损坏 JSON 不应阻断重新登录。
        credential = {}
    login_device_id = str(
        device_id or credential.get("deviceId") or _stable_device_id(phone_value)
    ).strip()

    async with httpx.AsyncClient(proxy=proxy, trust_env=False) as client:
        laohu_token, laohu_user_id = await _laohu_password_login(
            client,
            phone_value,
            password_value,
            login_device_id,
        )
        user_center = await _user_center_login(
            client,
            laohu_token,
            laohu_user_id,
            login_device_id,
        )

    credential.update(
        {
            "accessToken": user_center["accessToken"],
            "refreshToken": user_center["refreshToken"],
            "uid": user_center["uid"],
            "deviceId": login_device_id,
            "gameId": credential.get("gameId") or DEFAULT_GAME_ID,
            # Laohu 登录凭据同时用于云异环每日首次登录时长查询。
            "cloudToken": laohu_token,
            "cloudUserId": laohu_user_id,
            "cloudDeviceId": login_device_id,
        }
    )
    try:
        return await _attach_role_name(credential, proxy=proxy)
    except Exception as exc:
        # 角色名只用于展示，不能让已获得的登录凭据丢失。
        logger.debug(f"塔吉多登录后角色信息获取跳过: {type(exc).__name__}")
        return credential


async def _laohu_password_login(
    client: httpx.AsyncClient,
    phone: str,
    password: str,
    device_id: str,
) -> tuple[str, str]:
    data = _laohu_android_base_params(device_id, str(int(time.time() * 1000)))
    data.update(
        {
            "password": _aes_base64_encode(password),
            "username": _aes_base64_encode(phone),
        }
    )
    response = await client.post(
        LAOHU_LOGIN_URL,
        headers={
            "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
            "user-agent": LAOHU_USER_AGENT,
            "robot-auth-type": "2",
        },
        data=_signed_laohu_data(data),
        timeout=30.0,
    )
    payload = _read_login_json(response, "塔吉多账号密码登录")
    result = payload.get("result")
    user_id = ""
    token = ""
    if isinstance(result, dict):
        token = str(result.get("token") or "").strip()
        user_id = str(result.get("userId") or "").strip()
    if (
        not response.is_success
        or not _is_code(payload.get("code"), 0)
        or not token
        or not user_id
    ):
        raise _login_api_error("塔吉多账号密码登录", response, payload)
    return token, user_id


async def _user_center_login(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    device_id: str,
) -> dict[str, str]:
    attempt = await _request_user_center_login(
        client,
        token,
        user_id,
        device_id,
        compat=False,
    )
    if (
        _is_code(attempt[1].get("code"), 1)
        and str(attempt[1].get("message") or attempt[1].get("msg") or "").strip()
        == "系统错误"
    ):
        compatible = await _request_user_center_login(
            client,
            token,
            user_id,
            device_id,
            compat=True,
        )
        if compatible[0].is_success and _is_code(compatible[1].get("code"), 0):
            attempt = compatible

    response, payload = attempt
    data = payload.get("data")
    if (
        not response.is_success
        or not _is_code(payload.get("code"), 0)
        or not isinstance(data, dict)
    ):
        raise _login_api_error("塔吉多用户中心登录", response, payload)
    access_token = str(data.get("accessToken") or "").strip()
    refresh_token = str(data.get("refreshToken") or "").strip()
    uid = str(data.get("uid") or "").strip()
    if not access_token or not refresh_token or not uid:
        raise ValueError("塔吉多用户中心登录未返回完整 Token")
    return {
        "accessToken": access_token,
        "refreshToken": refresh_token,
        "uid": uid,
    }


async def _request_user_center_login(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    device_id: str,
    *,
    compat: bool,
) -> tuple[httpx.Response, dict[str, Any]]:
    if compat:
        headers = {
            "authorization": "",
            "appversion": APP_VERSION,
            "platform": "android",
            "uid": "10000000",
            "deviceid": device_id,
            "content-type": "application/x-www-form-urlencoded",
            "user-agent": APP_USER_AGENT,
        }
    else:
        headers = {
            "accept": "application/json, text/plain, */*",
            "authorization": "",
            "appVersion": TAYGEDO_LOGIN_APP_VERSION,
            "platform": "android",
            "uid": "0",
            "debug-uid": "3",
            "deviceId": device_id,
            "ds": _make_login_ds(),
            "content-type": "application/x-www-form-urlencoded",
            "user-agent": APP_USER_AGENT,
        }
    response = await client.post(
        USER_CENTER_LOGIN_URL,
        headers=headers,
        data={
            "token": token,
            "userIdentity": user_id,
            "appId": TAYGEDO_LOGIN_APP_ID,
        },
        timeout=30.0,
    )
    return response, _read_login_json(response, "塔吉多用户中心登录")


def _laohu_android_base_params(device_id: str, timestamp: str) -> dict[str, str]:
    return {
        "adm": "",
        "appId": LAOHU_APP_ID,
        "bid": "com.pwrd.htassistant",
        "channelId": LAOHU_CHANNEL_ID,
        "deviceId": device_id,
        "deviceModel": LAOHU_DEVICE_MODEL,
        "deviceName": LAOHU_DEVICE_MODEL,
        "deviceSys": LAOHU_DEVICE_SYS,
        "deviceType": LAOHU_DEVICE_MODEL,
        "idfa": "",
        "mac": "",
        "sdkVersion": LAOHU_SDK_VERSION,
        "t": timestamp,
        "version": LAOHU_VERSION_CODE,
    }


def _signed_laohu_data(data: Mapping[str, str]) -> dict[str, str]:
    signed = dict(data)
    signed["sign"] = _md5_join(data, LAOHU_SECRET)
    return signed


def _aes_base64_encode(value: str) -> str:
    key = LAOHU_SECRET[-16:].encode("utf-8")
    cipher = AES.new(key, AES.MODE_ECB)
    return base64.b64encode(
        cipher.encrypt(pad(value.encode("utf-8"), AES.block_size))
    ).decode("ascii")


def _make_login_ds() -> str:
    timestamp = str(int(time.time()))
    alphabet = string.ascii_letters + string.digits
    nonce = "".join(secrets.choice(alphabet) for _ in range(8))
    signature = hashlib.md5(
        f"{timestamp}{nonce}{TAYGEDO_LOGIN_APP_VERSION}{TAYGEDO_LOGIN_DS_SECRET}".encode(
            "utf-8"
        )
    ).hexdigest()
    return f"{timestamp},{nonce},{signature}"


def _read_login_json(response: httpx.Response, endpoint: str) -> dict[str, Any]:
    try:
        data = response.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"{endpoint}返回了无效 JSON（HTTP {response.status_code}）"
        ) from exc
    if not isinstance(data, dict):
        raise ValueError(f"{endpoint}返回格式无效（HTTP {response.status_code}）")
    return data


def _is_code(value: Any, expected: int) -> bool:
    """兼容上游以数字或字符串返回状态码。"""

    return str(value).strip() == str(expected)


def _login_api_error(
    endpoint: str,
    response: httpx.Response,
    data: Mapping[str, Any],
) -> ValueError:
    # 不带响应正文，防止上游错误内容回显用户身份或认证数据。
    message = str(data.get("msg") or data.get("message") or "请求失败").strip()
    code = data.get("code", "unknown")
    return ValueError(
        f"{endpoint}失败（HTTP {response.status_code}，code={code}）：{message}"
    )


async def refresh_taygedo_credential(
    raw: str,
    *,
    proxy: str | None = None,
) -> dict[str, Any]:
    """用已有 refreshToken 获取最新 accessToken，并返回可保存凭据。"""

    credential = parse_taygedo_credential(raw)
    refresh_token = str(credential.get("refreshToken") or "").strip()
    if not refresh_token:
        raise ValueError("塔吉多凭据缺少 refreshToken")

    async with httpx.AsyncClient(proxy=proxy, trust_env=False) as client:
        response = await client.post(
            REFRESH_TOKEN_URL,
            headers={
                "authorization": refresh_token,
                "deviceid": str(
                    credential.get("deviceId") or _stable_device_id(refresh_token)
                ),
                "appversion": APP_VERSION,
                "content-type": "application/x-www-form-urlencoded",
                "user-agent": APP_USER_AGENT,
            },
            timeout=30.0,
        )
    data = _read_json(response, "塔吉多刷新 Token")
    if not _is_code(data.get("code"), 0) or not isinstance(data.get("data"), dict):
        raise _api_error("塔吉多刷新 Token", response, data)

    refreshed = data["data"]
    if not refreshed.get("accessToken") or not refreshed.get("refreshToken"):
        raise ValueError("塔吉多刷新接口未返回完整 token")
    credential["accessToken"] = str(refreshed["accessToken"])
    credential["refreshToken"] = str(refreshed["refreshToken"])
    if refreshed.get("uid") is not None:
        credential["uid"] = str(refreshed["uid"])
    credential.setdefault("gameId", DEFAULT_GAME_ID)
    credential.setdefault("deviceId", _stable_device_id(credential["refreshToken"]))

    try:
        return await _attach_role_name(credential, proxy=proxy)
    except Exception as exc:
        # 角色名只用于通知展示，不能阻断有效 refreshToken 的社区签到。
        logger.debug(f"塔吉多角色信息获取跳过: {exc}")
        return credential


async def sign_taygedo(
    raw: str,
    *,
    proxy: str | None = None,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """执行塔吉多社区、应用内游戏签到和云异环时长查询。"""

    credential = parse_taygedo_credential(raw)
    refresh_error_reason: str | None = None
    if credential.get("refreshToken"):
        try:
            credential = await refresh_taygedo_credential(raw, proxy=proxy)
        except Exception as exc:
            # 塔吉多 refreshToken 失效时仍继续查询同一凭据中的云异环时长。
            refresh_error_reason = _log_taygedo_exception(
                "塔吉多刷新 Token 失败",
                exc,
            )

    results: list[dict[str, str]] = []
    access_token = str(credential.get("accessToken") or "").strip()
    uid = str(credential.get("uid") or "").strip()
    device_id = str(credential.get("deviceId") or "").strip()
    account = str(credential.get("roleName") or uid or "未知用户")

    community_task: asyncio.Task[list[tuple[str, str, str, str]]] | None = None
    game_task: asyncio.Task[list[dict[str, str]]] | None = None
    cloud_task: asyncio.Task[dict[str, int | None]] | None = None
    cloud_token = str(credential.get("cloudToken") or "").strip()
    cloud_user_id = str(credential.get("cloudUserId") or "").strip()
    cloud_account = account if account != "未知用户" else cloud_user_id
    cloud_before = _to_optional_int(credential.get("cloudRemainingDuration"))

    async def cancel_pending_tasks() -> None:
        pending_tasks = [
            task
            for task in (community_task, game_task, cloud_task)
            if task is not None and not task.done()
        ]
        for task in pending_tasks:
            task.cancel()
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)

    # 云异环每日首次登录时长与两个签到接口互不依赖，并发发起以缩短等待时间。
    if cloud_token and cloud_user_id:
        cloud_device_id = str(
            credential.get("cloudDeviceId")
            or device_id
            or _stable_device_id(cloud_user_id)
        )
        cloud_task = asyncio.create_task(
            get_cloud_duration(
                cloud_token,
                cloud_user_id,
                cloud_device_id,
                proxy=proxy,
            )
        )

    if access_token and uid:
        request_device_id = device_id or _stable_device_id(access_token)
        cached_roles = credential.pop("_gameRoles", None)
        cached_lookup_complete = credential.pop("_gameRolesComplete", None)
        if not isinstance(cached_roles, list):
            cached_roles = None
        # 社区签到和应用内游戏签到互不依赖，同时发起以减少整体等待时间。
        community_task = asyncio.create_task(
            _community_sign(
                access_token,
                uid,
                request_device_id,
                proxy=proxy,
            )
        )
        game_task = asyncio.create_task(
            _sign_taygedo_games(
                access_token,
                uid,
                request_device_id,
                account,
                proxy=proxy,
                roles=cached_roles,
                lookup_complete=(
                    bool(cached_lookup_complete) if cached_roles is not None else None
                ),
            )
        )

        try:
            community_results = await community_task
        except asyncio.CancelledError:
            await cancel_pending_tasks()
            raise
        except Exception as exc:
            failure_reason = _log_taygedo_exception("塔吉多社区签到异常", exc)
            if refresh_error_reason is not None:
                failure_reason = f"{refresh_error_reason}; {failure_reason}"
            community_results = [
                (
                    TAYGEDO_COMMUNITY_NAMES[community_id],
                    "失败",
                    failure_reason,
                    "",
                )
                for community_id in TAYGEDO_COMMUNITY_IDS
            ]
        for community_name, status, reason, reward in community_results:
            results.append(
                {
                    "account": account,
                    "game": community_name,
                    "platform": "塔吉多",
                    "status": status,
                    "reward": reward,
                    "reason": reason,
                }
            )

        try:
            results.extend(await game_task)
        except asyncio.CancelledError:
            await cancel_pending_tasks()
            raise
        except Exception as exc:
            reason = _log_taygedo_exception("塔吉多应用内游戏签到异常", exc)
            results.append(
                {
                    "account": account,
                    "game": "应用内游戏",
                    "platform": "塔吉多",
                    "status": "失败",
                    "reward": "",
                    "reason": reason,
                }
            )
    elif refresh_error_reason is not None:
        results.extend(
            {
                "account": account,
                "game": TAYGEDO_COMMUNITY_NAMES[community_id],
                "platform": "塔吉多",
                "status": "失败",
                "reward": "",
                "reason": refresh_error_reason,
            }
            for community_id in TAYGEDO_COMMUNITY_IDS
        )
    elif access_token or credential.get("refreshToken"):
        results.extend(
            {
                "account": account,
                "game": TAYGEDO_COMMUNITY_NAMES[community_id],
                "platform": "塔吉多",
                "status": "失败",
                "reward": "",
                "reason": "刷新后缺少 uid 或 accessToken",
            }
            for community_id in TAYGEDO_COMMUNITY_IDS
        )

    if cloud_task is not None:
        try:
            duration = await cloud_task
            cloud_verified, cloud_completed, cloud_reason = _verify_cloud_duration(
                before=cloud_before,
                duration=duration,
            )
            cloud_already_claimed = (
                duration.get("gave") is not None and duration["gave"] <= 0
            )
            if duration.get("remained") is not None:
                credential["cloudRemainingDuration"] = str(duration["remained"])
            results.append(
                {
                    "account": cloud_account,
                    "game": "云异环",
                    "platform": "云异环",
                    "status": (
                        "成功"
                        if cloud_verified
                        else "已签到"
                        if cloud_already_claimed
                        else "失败"
                    ),
                    # 返回剩余时长不等于确认了每日首登奖励；未确认时不把时长混入失败通知。
                    "reward": (
                        _format_duration(duration)
                        if cloud_verified or cloud_already_claimed
                        else ""
                    ),
                    "reason": cloud_reason,
                    "_completed": cloud_completed or cloud_already_claimed,
                }
            )
        except asyncio.CancelledError:
            await cancel_pending_tasks()
            raise
        except Exception as exc:
            reason = _log_taygedo_exception("云异环时长查询异常", exc)
            results.append(
                {
                    "account": cloud_account,
                    "game": "云异环",
                    "platform": "云异环",
                    "status": "失败",
                    "reward": "",
                    "reason": reason,
                }
            )

    return results, credential


async def _sign_taygedo_games(
    access_token: str,
    uid: str,
    device_id: str,
    account: str,
    *,
    proxy: str | None,
    roles: list[dict[str, str]] | None = None,
    lookup_complete: bool | None = None,
) -> list[dict[str, str]]:
    """遍历塔吉多绑定游戏并执行每日游戏签到。"""

    if roles is None:
        roles, lookup_complete = await _get_taygedo_game_roles_with_status(
            access_token,
            uid,
            device_id,
            proxy=proxy,
        )
    elif lookup_complete is None:
        lookup_complete = True
    assert lookup_complete is not None
    if not roles:
        if lookup_complete:
            logger.info("塔吉多未绑定应用内游戏，跳过游戏签到")
            return []
        logger.warning("塔吉多游戏角色接口未完成，应用内游戏签到跳过")
        return [
            {
                "account": f"{account}/应用内游戏",
                "game": "应用内游戏",
                "platform": "塔吉多",
                "status": "失败",
                "reward": "",
                "reason": "游戏角色接口获取失败，无法确认应用内游戏签到",
            }
        ]

    async def sign_role(
        role: dict[str, str], client: httpx.AsyncClient
    ) -> dict[str, str]:
        game_id = role["gameId"]
        role_id = role["roleId"]
        role_name = role.get("roleName") or role_id
        game_name = role.get("gameName") or TAYGEDO_GAME_NAMES.get(game_id, game_id)
        # 角色卡是本次结果的权威名称，不能继续沿用旧凭据中的异环别名。
        role_account = f"{role_name}/{role_name}({role_id})"
        try:
            state = await _get_game_sign_state(
                access_token,
                game_id,
                client=client,
                proxy=proxy,
            )
            if _is_game_signed(state):
                status = "已签到"
            else:
                status = await _submit_game_sign(
                    access_token,
                    game_id,
                    role_id,
                    client=client,
                    proxy=proxy,
                )
            return {
                "account": role_account,
                "game": game_name,
                "platform": "塔吉多",
                "status": status,
                "reward": "",
                "reason": "",
            }
        except Exception as exc:
            reason = _log_taygedo_exception("塔吉多应用内游戏签到异常", exc)
            return {
                "account": role_account,
                "game": game_name,
                "platform": "塔吉多",
                "status": "失败",
                "reward": "",
                "reason": reason,
            }

    async with httpx.AsyncClient(proxy=proxy, trust_env=False) as client:
        results = list(
            await asyncio.gather(*(sign_role(role, client) for role in roles))
        )

    if not lookup_complete:
        results.append(
            {
                "account": f"{account}/应用内游戏",
                "game": "应用内游戏",
                "platform": "塔吉多",
                "status": "失败",
                "reward": "",
                "reason": "部分游戏角色接口获取失败，无法确认全部应用内游戏签到",
            }
        )
    return results


async def _get_taygedo_game_roles(
    access_token: str,
    uid: str,
    device_id: str,
    *,
    proxy: str | None,
) -> list[dict[str, str]]:
    """兼容旧调用方，仅返回已发现的绑定角色列表。"""

    roles, _ = await _get_taygedo_game_roles_with_status(
        access_token,
        uid,
        device_id,
        proxy=proxy,
    )
    return roles


async def _get_taygedo_game_roles_with_status(
    access_token: str,
    uid: str,
    device_id: str,
    *,
    proxy: str | None,
) -> tuple[list[dict[str, str]], bool]:
    """读取带游戏归属的角色卡，旧接口仅作为兼容回退。"""

    async with httpx.AsyncClient(proxy=proxy, trust_env=False) as client:
        # 角色卡响应带有明确 gameId，是区分幻塔和异环的唯一可靠来源。
        try:
            response = await client.get(
                GAME_RECORD_CARDS_URL,
                params={"uid": uid},
                headers=_native_headers(access_token, uid, device_id),
                timeout=30.0,
            )
            data = _read_json(response, "塔吉多游戏角色卡")
            raw_cards = data.get("data")
            if not _is_code(data.get("code"), 0) or not _is_game_record_cards_payload(
                raw_cards
            ):
                raise ValueError("角色卡响应格式无效")
            roles = [
                role
                for raw_role in _extract_role_records(raw_cards)
                if (role := _normalise_game_role(raw_role))
            ]
            if roles:
                return _deduplicate_game_roles(roles), True
            # 角色卡可能只返回未绑定的空卡，继续查询角色列表获取已绑定角色。
        except Exception as exc:
            logger.debug(f"获取塔吉多游戏角色卡跳过: {type(exc).__name__}")

        roles: list[dict[str, str]] = []
        failed_game_ids: set[str] = set()

        async def load_roles(
            game_id: str,
        ) -> tuple[list[dict[str, str]], bool]:
            try:
                response = await client.get(
                    GAME_ROLES_URL,
                    params={"gameId": game_id},
                    headers=_native_headers(access_token, uid, device_id),
                    timeout=30.0,
                )
                data = _read_json(response, f"塔吉多角色({game_id})")
                if not _is_code(data.get("code"), 0):
                    return [], False
                # getGameRoles 的响应只返回 roleId/roleName，游戏归属由本次查询参数决定。
                roles = [
                    role
                    for raw_role in _extract_role_records(data.get("data"))
                    if (
                        role := _normalise_game_role(
                            raw_role,
                            expected_game_id=game_id,
                        )
                    )
                ]
                return roles, True
            except Exception as exc:
                logger.debug(f"获取塔吉多游戏角色 {game_id} 跳过: {type(exc).__name__}")
                return [], False

        # 旧接口按请求参数返回角色；最终按角色 ID 去重，避免重复映射到多个游戏。
        role_batches = await asyncio.gather(
            *(load_roles(game_id) for game_id in TAYGEDO_GAME_IDS)
        )
        for game_id, (batch, query_ok) in zip(TAYGEDO_GAME_IDS, role_batches):
            roles.extend(batch)
            if not query_ok:
                failed_game_ids.add(game_id)

    return _deduplicate_game_roles(roles), not failed_game_ids


def _is_game_record_cards_payload(value: Any) -> bool:
    """判断角色卡响应是否是可解析的列表或包装对象。"""

    if isinstance(value, list):
        return True
    if not isinstance(value, dict):
        return False
    return any(
        key in value
        for key in (
            "gameId",
            "game_id",
            "gameID",
            "gameName",
            "bindRoleInfo",
            "roles",
            "cards",
            "list",
            "roleList",
            "data",
        )
    )


def _extract_role_records(
    value: Any, fallback_game_id: str = ""
) -> list[dict[str, Any]]:
    """兼容角色卡、roles、cards、list 和 bindRoleInfo 的返回结构。"""

    if isinstance(value, list):
        records: list[dict[str, Any]] = []
        for item in value:
            records.extend(_extract_role_records(item, fallback_game_id))
        return records
    if not isinstance(value, dict):
        return []

    game_id = str(
        value.get("gameId")
        or value.get("game_id")
        or value.get("gameID")
        or fallback_game_id
    ).strip()
    records: list[dict[str, Any]] = []
    bind_role = value.get("bindRoleInfo")
    if isinstance(bind_role, str):
        try:
            bind_role = json.loads(bind_role)
        except json.JSONDecodeError:
            bind_role = None
    if bind_role not in (None, ""):
        bind_records = _extract_role_records(bind_role, game_id)
        if game_id:
            # 角色卡的 gameId 是游戏归属的权威字段，不能被嵌套旧字段覆盖。
            for record in bind_records:
                record["gameId"] = game_id
        if value.get("gameName"):
            for record in bind_records:
                record.setdefault("gameName", value["gameName"])
        records.extend(bind_records)
    if any(value.get(key) not in (None, "") for key in ("roleId", "role_id", "roleID")):
        records.append({**value, "gameId": game_id})

    for key in ("roles", "cards", "list", "roleList", "data"):
        if key in value:
            child_records = _extract_role_records(value[key], game_id)
            if game_id:
                for record in child_records:
                    record["gameId"] = game_id
            records.extend(child_records)
    for key in ("roleInfo", "role"):
        if key in value:
            child_records = _extract_role_records(value[key], game_id)
            if game_id:
                for record in child_records:
                    record["gameId"] = game_id
            records.extend(child_records)
    return records


def _normalise_game_role(
    raw_role: Mapping[str, Any],
    fallback_game_id: str = "",
    *,
    expected_game_id: str | None = None,
    require_reported_game_id: bool = False,
) -> dict[str, str] | None:
    reported_game_id = str(
        raw_role.get("gameId")
        or raw_role.get("game_id")
        or raw_role.get("gameID")
        or ""
    ).strip()
    if expected_game_id and reported_game_id and reported_game_id != expected_game_id:
        return None
    if require_reported_game_id and not reported_game_id:
        return None
    game_id = str(expected_game_id or reported_game_id or fallback_game_id).strip()
    role_id = str(
        raw_role.get("roleId")
        or raw_role.get("role_id")
        or raw_role.get("roleID")
        or ""
    ).strip()
    if game_id not in TAYGEDO_GAME_IDS or not role_id:
        return None
    role_name = next(
        (
            str(raw_role.get(key)).strip()
            for key in ("roleName", "role_name", "nickname", "characterName", "name")
            if raw_role.get(key) not in (None, "")
        ),
        "",
    )
    return {
        "gameId": game_id,
        # 服务端偶尔会沿用上一个子社区的 gameName，gameId 才是角色归属依据。
        "gameName": TAYGEDO_GAME_NAMES.get(
            game_id,
            str(raw_role.get("gameName") or game_id).strip(),
        ),
        "roleId": role_id,
        "roleName": role_name,
    }


def _deduplicate_game_roles(roles: list[dict[str, str]]) -> list[dict[str, str]]:
    # 角色 ID 在塔吉多账号下是全局唯一的，避免旧接口在多个 gameId 查询中
    # 重复返回同一角色时，把一个角色错误展示为多个游戏角色。
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for role in roles:
        role_id = role.get("roleId", "")
        if not role_id or role_id in seen:
            continue
        seen.add(role_id)
        unique.append(role)
    return unique


async def _get_game_sign_state(
    access_token: str,
    game_id: str,
    *,
    client: httpx.AsyncClient | None = None,
    proxy: str | None,
) -> dict[str, Any]:
    if client is None:
        async with httpx.AsyncClient(proxy=proxy, trust_env=False) as owned_client:
            return await _get_game_sign_state(
                access_token,
                game_id,
                client=owned_client,
                proxy=proxy,
            )

    response = await client.get(
        GAME_SIGNIN_STATE_URL,
        params={"gameId": game_id},
        headers=_h5_headers(access_token),
        timeout=30.0,
    )
    data = _read_json(response, f"塔吉多游戏签到状态({game_id})")
    if not _is_code(data.get("code"), 0) or not isinstance(data.get("data"), dict):
        raise _api_error(f"塔吉多游戏签到状态({game_id})", response, data)
    return data["data"]


def _is_game_signed(state: Mapping[str, Any]) -> bool:
    """读取不同版本接口返回的“今日已签到”字段。"""

    for key in (
        "todaySign",
        "todaySigned",
        "isSign",
        "isSigned",
        "signed",
        "alreadySigned",
    ):
        value = state.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str) and value.strip().lower() in {
            "1",
            "true",
            "yes",
            "signed",
            "already",
        }:
            return True
    return False


async def _submit_game_sign(
    access_token: str,
    game_id: str,
    role_id: str,
    *,
    client: httpx.AsyncClient | None = None,
    proxy: str | None,
) -> str:
    if client is None:
        async with httpx.AsyncClient(proxy=proxy, trust_env=False) as owned_client:
            return await _submit_game_sign(
                access_token,
                game_id,
                role_id,
                client=owned_client,
                proxy=proxy,
            )

    response = await client.post(
        GAME_SIGNIN_URL,
        headers={
            **_h5_headers(access_token),
            "content-type": "application/x-www-form-urlencoded",
        },
        data={"gameId": game_id, "roleId": role_id},
        timeout=30.0,
    )
    data = _read_json(response, f"塔吉多游戏签到({game_id})")
    message = str(data.get("msg") or data.get("message") or "").strip()
    if _is_code(data.get("code"), 0):
        return "成功"
    if str(data.get("code")) == "5052" or _is_already_signed(message):
        return "已签到"
    raise _api_error(f"塔吉多游戏签到({game_id})", response, data)


def _native_headers(access_token: str, uid: str, device_id: str) -> dict[str, str]:
    return {
        "accept": "application/json, text/plain, */*",
        "authorization": access_token,
        "uid": uid,
        "deviceid": device_id,
        "appversion": TAYGEDO_NATIVE_APP_VERSION,
        "platform": "android",
        "ds": _make_login_ds(),
        "user-agent": APP_USER_AGENT,
    }


def _h5_headers(access_token: str) -> dict[str, str]:
    return {
        "accept": "application/json",
        "authorization": access_token,
        "origin": "https://webstatic.tajiduo.com",
        "referer": "https://webstatic.tajiduo.com/",
        "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Tajiduo/1.2.2",
    }


async def get_cloud_duration(
    cloud_token: str,
    cloud_user_id: str,
    device_id: str,
    *,
    proxy: str | None = None,
) -> dict[str, int | None]:
    """查询云异环时长，不调用短信登录或领取接口。"""

    params = {
        "appId": CLOUD_APP_ID,
        "deviceId": device_id,
        "deviceType": "Pixel 8",
        "deviceName": "Pixel 8",
        "t": str(int(time.time())),
        "channelId": CLOUD_CHANNEL_ID,
        "deviceModel": "Pixel 8",
        "deviceSys": "14",
        "version": CLOUD_APP_VERSION,
        "sdkVersion": CLOUD_SDK_VERSION,
        "network": "wifi",
        "bid": CLOUD_BID,
        "provider": "0",
        "idfa": "",
        "userId": cloud_user_id,
        "token": cloud_token,
    }
    params["sign"] = _md5_join(params, CLOUD_APP_KEY)

    async with httpx.AsyncClient(proxy=proxy, trust_env=False) as client:
        response = await client.post(
            CLOUD_USER_INFO_URL,
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "user-agent": "okhttp/3.12.1",
            },
            data=params,
            timeout=30.0,
        )
    data = _read_json(response, "云异环时长")
    if not _is_code(data.get("code"), 0) or not isinstance(data.get("result"), dict):
        raise _api_error("云异环时长", response, data)
    result = data["result"]
    return {
        "gave": _to_optional_int(result.get("perDayFirstLoginGiveDuration")),
        "remained": _to_optional_int(result.get("remainedDuration")),
    }


def _verify_cloud_duration(
    *,
    before: int | None,
    duration: Mapping[str, int | None],
) -> tuple[bool, bool, str]:
    """验证云异环每日首登时长，避免把用户消耗误判为签到成功。"""

    gave = duration.get("gave")
    remained = duration.get("remained")
    if gave is None or remained is None:
        return False, False, "服务端未返回完整时长，无法确认每日首登奖励"

    if gave <= 0:
        return False, True, "今日未检测到新增的每日首登时长"
    if before is None:
        # 首次运行没有历史快照时，服务端明确返回 gave > 0 已足以确认本次赠送。
        # 后续运行仍必须校验剩余时长的增长量，避免用户自行消耗被误判为成功。
        return (
            True,
            True,
            "",
        )

    delta = remained - before
    if delta > 0:
        # 服务端的 gave 表示本次首登奖励；剩余时长可能在查询前后被用户消耗，
        # 因此只要求快照确实增长，不再要求增量必须与奖励值严格相等。
        return True, True, ""
    if delta == 0:
        return False, True, "剩余时长未增加，无法确认每日首登奖励"
    return False, True, f"剩余时长减少 {abs(delta)} 分钟，未确认每日首登奖励"


async def _attach_role_name(
    credential: dict[str, Any],
    *,
    proxy: str | None,
) -> dict[str, Any]:
    access_token = str(credential.get("accessToken") or "").strip()
    uid = str(credential.get("uid") or "").strip()
    if not access_token or not uid:
        return credential

    # 角色查询失败或返回空列表时不能继续使用旧凭据中的游戏名。
    credential.pop("gameId", None)
    credential.pop("roleName", None)
    credential.pop("roleIds", None)
    device_id = str(credential.get("deviceId") or _stable_device_id(access_token))
    roles, lookup_complete = await _get_taygedo_game_roles_with_status(
        access_token,
        uid,
        device_id,
        proxy=proxy,
    )
    credential["_gameRoles"] = roles
    credential["_gameRolesComplete"] = lookup_complete
    if not roles:
        if lookup_complete:
            credential.pop("gameId", None)
            credential.pop("roleName", None)
            credential.pop("roleIds", None)
        return credential
    first = next((role for role in roles if role.get("roleName")), roles[0])
    credential["gameId"] = first["gameId"]
    if first.get("roleName"):
        credential["roleName"] = first["roleName"]
    if first.get("roleId"):
        credential["roleIds"] = [first["roleId"]]
    return credential


async def _community_sign(
    access_token: str,
    uid: str,
    device_id: str,
    *,
    proxy: str | None,
) -> list[tuple[str, str, str, str]]:
    """并发执行塔吉多应用社区和异环社区签到。"""

    async with httpx.AsyncClient(proxy=proxy, trust_env=False) as client:

        async def sign_community(community_id: str) -> tuple[str, str, str, str]:
            community_name = TAYGEDO_COMMUNITY_NAMES.get(community_id, community_id)
            try:
                response = await client.post(
                    APP_SIGNIN_URL,
                    headers={
                        **_native_headers(access_token, uid, device_id),
                        "content-type": "application/x-www-form-urlencoded",
                    },
                    data={"communityId": community_id},
                    timeout=30.0,
                )
                data = _read_json(response, f"{community_name}签到")
                message = str(data.get("msg") or data.get("message") or "").strip()
                if _is_code(data.get("code"), 0):
                    # 社区签到接口会同时返回经验、塔塔币等社区奖励，签到通知不展示这些字段。
                    return community_name, "成功", "", ""
                if _is_already_signed(message):
                    return community_name, "已签到", "", ""
                return (
                    community_name,
                    "失败",
                    message or f"HTTP {response.status_code}",
                    "",
                )
            except Exception as exc:
                reason = _log_taygedo_exception(
                    f"{community_name}签到异常",
                    exc,
                )
                return community_name, "失败", reason, ""

        return list(
            await asyncio.gather(
                *(
                    sign_community(community_id)
                    for community_id in TAYGEDO_COMMUNITY_IDS
                )
            )
        )


def _read_json(response: httpx.Response, endpoint: str) -> dict[str, Any]:
    try:
        data = response.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"{endpoint}返回了无效 JSON（HTTP {response.status_code}）"
        ) from exc
    if not isinstance(data, dict):
        raise ValueError(f"{endpoint}返回格式无效（HTTP {response.status_code}）")
    return data


def _api_error(
    endpoint: str, response: httpx.Response, data: Mapping[str, Any]
) -> ValueError:
    message = str(data.get("msg") or data.get("message") or "请求失败").strip()
    return ValueError(f"{endpoint}失败（HTTP {response.status_code}）：{message}")


def _is_already_signed(message: str) -> bool:
    return any(
        marker in message for marker in ("已签到", "已经签到", "签到过", "重复签到")
    )


def _format_duration(duration: Mapping[str, int | None]) -> str:
    parts = []
    gave = duration.get("gave")
    remained = duration.get("remained")
    if gave is not None and gave > 0:
        parts.append(f"每日首登{gave}分钟")
    if remained is not None:
        parts.append(f"剩余{remained}分钟")
    return ",".join(parts) or "时长查询成功"


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _stable_device_id(seed: str) -> str:
    digest = hashlib.sha256(str(seed).encode("utf-8")).hexdigest().upper()
    return digest[:32]


def _md5_join(data: Mapping[str, str], secret: str) -> str:
    values = "".join(str(data[key]) for key in sorted(data))
    return hashlib.md5(f"{values}{secret}".encode("utf-8")).hexdigest()
