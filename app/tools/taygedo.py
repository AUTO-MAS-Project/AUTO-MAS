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

logger = get_logger("塔吉多签到")

TAYGEDO_BASE_URL = "https://bbs-api.tajiduo.com"
LAOHU_BASE_URL = "https://user.laohu.com"
REFRESH_TOKEN_URL = f"{TAYGEDO_BASE_URL}/usercenter/api/refreshToken"
USER_CENTER_LOGIN_URL = f"{TAYGEDO_BASE_URL}/usercenter/api/login"
GAME_ROLES_URL = f"{TAYGEDO_BASE_URL}/usercenter/api/v2/getGameRoles"
APP_SIGNIN_URL = f"{TAYGEDO_BASE_URL}/apihub/api/signin"
CLOUD_USER_INFO_URL = "https://user.laohu.com/cloud/game/getUserInfo"

DEFAULT_GAME_ID = "1289"
APP_VERSION = "1.1.0"
APP_SIGN_COMMUNITY_ID = "1"
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
        "roleName",
    ):
        if credential.get(key) is not None:
            credential[key] = str(credential[key]).strip()

    if isinstance(credential.get("roleIds"), str):
        credential["roleIds"] = [
            part.strip()
            for part in credential["roleIds"].split(",")
            if part.strip()
        ]

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
        device_id
        or credential.get("deviceId")
        or _stable_device_id(phone_value)
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
    if not response.is_success or not _is_code(payload.get("code"), 0) or not token or not user_id:
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
    if not response.is_success or not _is_code(payload.get("code"), 0) or not isinstance(data, dict):
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
    return base64.b64encode(cipher.encrypt(pad(value.encode("utf-8"), AES.block_size))).decode(
        "ascii"
    )


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
        raise ValueError(f"{endpoint}返回了无效 JSON（HTTP {response.status_code}）") from exc
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
    return ValueError(f"{endpoint}失败（HTTP {response.status_code}，code={code}）：{message}")


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
    if data.get("code") != 0 or not isinstance(data.get("data"), dict):
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
    """执行塔吉多社区签到和可选的云异环时长查询。"""

    credential = parse_taygedo_credential(raw)
    refresh_error: Exception | None = None
    if credential.get("refreshToken"):
        try:
            credential = await refresh_taygedo_credential(raw, proxy=proxy)
        except Exception as exc:
            # 塔吉多 refreshToken 失效时仍继续查询同一凭据中的云异环时长。
            refresh_error = exc

    results: list[dict[str, str]] = []
    access_token = str(credential.get("accessToken") or "").strip()
    uid = str(credential.get("uid") or "").strip()
    device_id = str(credential.get("deviceId") or "").strip()
    account = str(credential.get("roleName") or uid or "未知用户")

    if refresh_error is not None:
        results.append(
            {
                "account": account,
                "game": "塔吉多社区",
                "platform": "塔吉多",
                "status": "失败",
                "reward": "",
                "reason": str(refresh_error),
            }
        )
    elif access_token and uid:
        try:
            status, reason, reward = await _community_sign(
                access_token,
                uid,
                device_id or _stable_device_id(access_token),
                proxy=proxy,
            )
            results.append(
                {
                    "account": account,
                    "game": "塔吉多社区",
                    "platform": "塔吉多",
                    "status": status,
                    "reward": reward,
                    "reason": reason,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "account": account,
                    "game": "塔吉多社区",
                    "platform": "塔吉多",
                    "status": "失败",
                    "reward": "",
                    "reason": str(exc),
                }
            )
    elif access_token or credential.get("refreshToken"):
        results.append(
            {
                "account": account,
                "game": "塔吉多社区",
                "platform": "塔吉多",
                "status": "失败",
                "reward": "",
                "reason": "刷新后缺少 uid 或 accessToken",
            }
        )

    cloud_token = str(credential.get("cloudToken") or "").strip()
    cloud_user_id = str(credential.get("cloudUserId") or "").strip()
    if cloud_token and cloud_user_id:
        cloud_device_id = str(
            credential.get("cloudDeviceId")
            or device_id
            or _stable_device_id(cloud_user_id)
        )
        cloud_account = account if account != "未知用户" else cloud_user_id
        try:
            duration = await get_cloud_duration(
                cloud_token,
                cloud_user_id,
                cloud_device_id,
                proxy=proxy,
            )
            results.append(
                {
                    "account": cloud_account,
                    "game": "云异环",
                    "platform": "云异环",
                    "status": "成功",
                    "reward": _format_duration(duration),
                    "reason": "",
                }
            )
        except Exception as exc:
            results.append(
                {
                    "account": cloud_account,
                    "game": "云异环",
                    "platform": "云异环",
                    "status": "失败",
                    "reward": "",
                    "reason": str(exc),
                }
            )

    return results, credential


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
    if data.get("code") != 0 or not isinstance(data.get("result"), dict):
        raise _api_error("云异环时长", response, data)
    result = data["result"]
    return {
        "gave": _to_int(result.get("perDayFirstLoginGiveDuration")),
        "remained": _to_optional_int(result.get("remainedDuration")),
    }


async def _attach_role_name(
    credential: dict[str, Any],
    *,
    proxy: str | None,
) -> dict[str, Any]:
    access_token = str(credential.get("accessToken") or "").strip()
    uid = str(credential.get("uid") or "").strip()
    if not access_token or not uid:
        return credential

    device_id = str(credential.get("deviceId") or _stable_device_id(access_token))
    game_id = str(credential.get("gameId") or DEFAULT_GAME_ID)
    async with httpx.AsyncClient(proxy=proxy, trust_env=False) as client:
        response = await client.get(
            GAME_ROLES_URL,
            params={"gameId": game_id},
            headers={
                "platform": "android",
                "authorization": access_token,
                "uid": uid,
                "deviceid": device_id,
                "appversion": APP_VERSION,
                "user-agent": APP_USER_AGENT,
            },
            timeout=30.0,
        )
    data = _read_json(response, "塔吉多角色")
    if data.get("code") != 0 or not isinstance(data.get("data"), dict):
        return credential
    roles = data["data"].get("roles")
    if not isinstance(roles, list) or not roles:
        return credential
    first = roles[0]
    if isinstance(first, dict):
        if first.get("roleName"):
            credential["roleName"] = str(first["roleName"])
        if first.get("roleId"):
            credential["roleIds"] = [str(first["roleId"])]
    return credential


async def _community_sign(
    access_token: str,
    uid: str,
    device_id: str,
    *,
    proxy: str | None,
) -> tuple[str, str, str]:
    async with httpx.AsyncClient(proxy=proxy, trust_env=False) as client:
        response = await client.post(
            APP_SIGNIN_URL,
            headers={
                "authorization": access_token,
                "uid": uid,
                "deviceid": device_id,
                "appversion": APP_VERSION,
                "content-type": "application/x-www-form-urlencoded",
                "user-agent": APP_USER_AGENT,
            },
            data={"communityId": APP_SIGN_COMMUNITY_ID},
            timeout=30.0,
        )
    data = _read_json(response, "塔吉多社区签到")
    message = str(data.get("msg") or data.get("message") or "").strip()
    if data.get("code") == 0:
        reward = _format_community_reward(data.get("data"))
        return "成功", "", reward
    if _is_already_signed(message):
        return "已签到", "", ""
    return "失败", message or f"HTTP {response.status_code}", ""


def _read_json(response: httpx.Response, endpoint: str) -> dict[str, Any]:
    try:
        data = response.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{endpoint}返回了无效 JSON（HTTP {response.status_code}）") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{endpoint}返回格式无效（HTTP {response.status_code}）")
    return data


def _api_error(endpoint: str, response: httpx.Response, data: Mapping[str, Any]) -> ValueError:
    message = str(data.get("msg") or data.get("message") or "请求失败").strip()
    return ValueError(f"{endpoint}失败（HTTP {response.status_code}）：{message}")


def _is_already_signed(message: str) -> bool:
    return any(marker in message for marker in ("已签到", "已经签到", "签到过", "重复签到"))


def _format_community_reward(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    parts = []
    if value.get("exp") is not None:
        parts.append(f"经验{value['exp']}")
    if value.get("goldCoin") is not None:
        parts.append(f"金币{value['goldCoin']}")
    return ",".join(parts)


def _format_duration(duration: Mapping[str, int | None]) -> str:
    parts = []
    gave = duration.get("gave")
    remained = duration.get("remained")
    if gave is not None:
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
