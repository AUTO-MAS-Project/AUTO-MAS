#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 ClozyA
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file incorporates work covered by the following copyright and
#   permission notice:
#
#       skland-checkin-ghaction Copyright © 2023 Yanstory
#       https://github.com/Yanstory/skland-checkin-ghaction
#
#       skland-daily-attendance Copyright © 2023-2025 enpitsuLin
#       https://github.com/enpitsuLin/skland-daily-attendance

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


import asyncio
import base64
import gzip
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict
from urllib import parse

import httpx
from Crypto.Cipher import AES, DES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad

from app.utils.constants import BROWSER_ENV, DES_RULE, SKLAND_SM_CONFIG, UTC8
from app.utils.logger import get_logger
from app.utils.security import format_exception_reason

from .skland_response import is_skland_already_signed

_skland_sign_lock = asyncio.Lock()
_device_id_lock = asyncio.Lock()
_cached_device_id: str | None = None
_cache_time: datetime | None = None

SKLAND_APP_CODE = "4ca99fa6b56cc2ba"
SKLAND_GRANT_CODE_URL = "https://as.hypergryph.com/user/oauth2/v2/grant"
SKLAND_PASSWORD_LOGIN_URL = (
    "https://as.hypergryph.com/user/auth/v1/token_by_phone_password"
)
SKLAND_CRED_CODE_URL = "https://zonai.skland.com/web/v1/user/auth/generate_cred_by_code"
SKLAND_REFRESH_URL = "https://zonai.skland.com/web/v1/auth/refresh"
SKLAND_BINDING_URL = "https://zonai.skland.com/api/v1/game/player/binding"
SKLAND_ARKNIGHTS_SIGN_URL = "https://zonai.skland.com/api/v1/game/attendance"
SKLAND_ENDFIELD_SIGN_URL = "https://zonai.skland.com/web/v1/game/endfield/attendance"
SKLAND_SIGN_INTERVAL = 1.0

logger = get_logger("森空岛签到任务")


def _get_arknights_game_id(character: dict[str, object]) -> object:
    """读取方舟绑定对象的游戏 ID，兼容旧响应中的 channelMasterId。"""

    return character.get("gameId") or character.get("channelMasterId")


def _create_skland_client(proxy: str | None = None) -> httpx.AsyncClient:
    """创建不继承本地环境代理的森空岛 HTTP 客户端。"""

    return httpx.AsyncClient(proxy=proxy, trust_env=False)


def _parse_json_object(response: httpx.Response) -> dict[str, object]:
    """解析森空岛响应，并拒绝空值或非对象 JSON。"""

    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("森空岛接口返回格式无效")
    return payload


def parse_skland_credential(raw: str | dict[str, object]) -> dict[str, str]:
    """解析森空岛旧 Token 或统一凭据 JSON。"""

    payload: dict[str, object] = {}
    raw_value = raw if isinstance(raw, dict) else str(raw or "").strip()
    if isinstance(raw_value, dict):
        payload = raw_value
    elif raw_value:
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, dict):
                payload = parsed
            else:
                payload = {"oauthToken": raw_value}
        except (TypeError, json.JSONDecodeError):
            payload = {"oauthToken": raw_value}

    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("content"), str):
        payload = {"oauthToken": data["content"], **payload}

    cred = str(payload.get("cred") or "").strip()
    sign_token = str(
        payload.get("signToken")
        or payload.get("sign_token")
        or (payload.get("token") if cred else "")
        or ""
    ).strip()
    oauth_token = str(
        payload.get("oauthToken")
        or payload.get("oauth_token")
        or payload.get("accessToken")
        or payload.get("access_token")
        or (payload.get("token") if not cred else "")
        or sign_token
        or ""
    ).strip()
    user_id = str(payload.get("userId") or payload.get("uid") or "").strip()
    return {
        "oauthToken": oauth_token,
        "token": sign_token,
        "cred": cred,
        "userId": user_id,
    }


def validate_skland_credential(raw: str | dict[str, object]) -> dict[str, str]:
    """校验旧纯 Token 或统一凭据 JSON 的明显格式错误。"""

    if isinstance(raw, dict):
        payload = raw
    else:
        raw_value = str(raw or "").strip()
        if not raw_value:
            raise ValueError("森空岛凭据不能为空")
        if raw_value[:1] in {"{", "[", '"'}:
            try:
                parsed = json.loads(raw_value)
            except json.JSONDecodeError as exc:
                raise ValueError("森空岛凭据 JSON 格式无效") from exc
            if not isinstance(parsed, dict):
                raise ValueError("森空岛凭据必须是 JSON 对象或旧版纯 Token")
            payload = parsed
        else:
            if any(character.isspace() for character in raw_value):
                raise ValueError("森空岛 Token 不应包含空格或换行")
            payload = {"oauthToken": raw_value}

    for key in (
        "oauthToken",
        "oauth_token",
        "accessToken",
        "access_token",
        "signToken",
        "sign_token",
        "token",
        "cred",
    ):
        value = payload.get(key)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"森空岛凭据字段 {key} 必须是字符串")

    data = payload.get("data")
    if data is not None and not isinstance(data, dict):
        raise ValueError("森空岛凭据 data 字段格式无效")
    if isinstance(data, dict):
        content = data.get("content")
        if content is not None and not isinstance(content, str):
            raise ValueError("森空岛凭据 data.content 必须是字符串")

    credential = parse_skland_credential(payload)
    for field in ("oauthToken", "token", "cred"):
        if any(character.isspace() for character in credential[field]):
            raise ValueError(f"森空岛凭据字段 {field} 不应包含空格或换行")
    if bool(credential["cred"]) != bool(credential["token"]):
        raise ValueError("森空岛统一凭据必须同时包含 cred 和 token")
    if not credential["oauthToken"] and not credential["cred"]:
        raise ValueError("森空岛凭据缺少 OAuth Token 或 cred/token")
    return credential


def serialize_skland_credential(credential: dict[str, object]) -> str:
    """序列化森空岛凭据，不写入手机号、密码等登录信息。"""

    normalized = parse_skland_credential(credential)
    oauth_token = normalized["oauthToken"]
    sign_token = normalized["token"]
    cred = normalized["cred"]
    user_id = normalized["userId"]
    if not cred and not sign_token:
        return oauth_token

    payload: dict[str, str] = {}
    if oauth_token:
        payload["oauthToken"] = oauth_token
    if sign_token:
        payload["token"] = sign_token
    if cred:
        payload["cred"] = cred
    if user_id:
        payload["userId"] = user_id
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def md5_hash(data: str) -> str:
    """MD5哈希"""
    return hashlib.md5(data.encode()).hexdigest()


def get_sm_id() -> str:
    """生成数美ID"""
    now = time.localtime()
    _time = time.strftime("%Y%m%d%H%M%S", now)
    uid = str(uuid.uuid4())
    uid_md5 = md5_hash(uid)
    v = f"{_time}{uid_md5}00"
    smsk_web = md5_hash(f"smsk_web_{v}")[:14]
    return f"{v}{smsk_web}0"


def get_tn(obj: dict[str, object]) -> str:
    """计算tn值"""
    sorted_keys = sorted(obj.keys())
    result_list = []

    for key in sorted_keys:
        v = obj[key]
        if isinstance(v, (int, float)):
            v = str(int(v * 10000))
        elif isinstance(v, dict):
            v = get_tn(v)
        else:
            v = str(v)
        result_list.append(v)

    return "".join(result_list)


def encrypt_rsa(message: str, public_key_str: str) -> str:
    """RSA加密"""
    try:
        formatted_key = "\n".join(
            [public_key_str[i : i + 64] for i in range(0, len(public_key_str), 64)]
        )
        public_key_pem = (
            f"-----BEGIN PUBLIC KEY-----\n{formatted_key}\n-----END PUBLIC KEY-----"
        )
        key = RSA.import_key(public_key_pem)
        cipher = PKCS1_v1_5.new(key)
        encrypted = cipher.encrypt(message.encode())
        return base64.b64encode(encrypted).decode()
    except Exception as e:
        raise Exception(f"RSA加密失败: {e}")


def encrypt_des(message: str, key: str) -> str:
    """DES ECB 加密"""
    key_bytes = key.encode()[:8].ljust(8, b"\0")
    message_bytes = str(message).encode()
    while len(message_bytes) % 8 != 0:
        message_bytes += b"\0"
    cipher = DES.new(key_bytes, DES.MODE_ECB)
    encrypted = cipher.encrypt(message_bytes)
    return base64.b64encode(encrypted).decode()


def gzip_compress_object(obj: dict[str, object]) -> str:
    """GZIP压缩对象"""
    json_str = json.dumps(obj, separators=(", ", ": "))
    compressed = gzip.compress(json_str.encode())
    compressed_bytes = bytearray(compressed)
    if len(compressed_bytes) > 9:
        compressed_bytes[9] = 19
    return base64.b64encode(compressed_bytes).decode()


def encrypt_aes(message: str, key: str) -> str:
    """AES CBC加密"""
    iv = b"0102030405060708"
    key_bytes = key.encode()[:16].ljust(16, b"\0")
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
    padded_data = pad(message.encode(), AES.block_size)
    encrypted = cipher.encrypt(padded_data)
    return encrypted.hex()


def encrypt_object_by_des_rules(
    obj: dict[str, object], rules: dict[str, dict[str, object]]
) -> dict[str, object]:
    """根据DES规则加密对象"""
    result = {}

    for key, value in obj.items():
        if key in rules:
            rule = rules[key]
            if rule["is_encrypt"] == 1:
                encrypted_value = encrypt_des(str(value), rule["key"])
                result[rule["obfuscated_name"]] = encrypted_value
            else:
                result[rule["obfuscated_name"]] = value
        else:
            result[key] = value

    return result


async def get_device_id(
    proxy: str | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> str:
    """获取设备ID"""
    uid = str(uuid.uuid4())
    pri_id = md5_hash(uid)[:16]
    ep = encrypt_rsa(uid, SKLAND_SM_CONFIG["publicKey"])

    browser = BROWSER_ENV.copy()
    browser.update(
        {
            "vpw": str(uuid.uuid4()),
            "svm": int(time.time() * 1000),
            "trees": str(uuid.uuid4()),
            "pmf": int(time.time() * 1000),
        }
    )

    des_target = {
        **browser,
        "protocol": 102,
        "organization": SKLAND_SM_CONFIG["organization"],
        "appId": SKLAND_SM_CONFIG["appId"],
        "os": "web",
        "version": "3.0.0",
        "sdkver": "3.0.0",
        "box": "",
        "rtype": "all",
        "smid": get_sm_id(),
        "subVersion": "1.0.0",
        "time": 0,
    }
    des_target["tn"] = md5_hash(get_tn(des_target))

    des_result = encrypt_object_by_des_rules(des_target, DES_RULE)
    gzip_result = gzip_compress_object(des_result)
    aes_result = encrypt_aes(gzip_result, pri_id)

    body = {
        "appId": "default",
        "compress": 2,
        "data": aes_result,
        "encode": 5,
        "ep": ep,
        "organization": SKLAND_SM_CONFIG["organization"],
        "os": "web",
    }

    devices_info_url = f"{SKLAND_SM_CONFIG['protocol']}://{SKLAND_SM_CONFIG['apiHost']}{SKLAND_SM_CONFIG['apiPath']}"

    async def request(active_client: httpx.AsyncClient) -> str:
        response = await active_client.post(
            devices_info_url,
            json=body,
            headers={"Content-Type": "application/json"},
            timeout=30.0,
        )
        resp = _parse_json_object(response)

        if resp.get("code") != 1100:
            raise Exception(f"设备ID计算失败: {resp}")

        detail = resp.get("detail")
        if not isinstance(detail, dict) or not detail.get("deviceId"):
            raise ValueError("设备ID响应格式无效")
        return f"B{detail['deviceId']}"

    if client is not None:
        return await request(client)
    async with _create_skland_client(proxy) as owned_client:
        return await request(owned_client)


async def get_cached_device_id(
    proxy: str | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> str:
    """获取缓存的设备ID"""
    global _cached_device_id, _cache_time

    now = datetime.now()
    if (
        _cached_device_id is None
        or _cache_time is None
        or (now - _cache_time) > timedelta(hours=1)
    ):
        async with _device_id_lock:
            now = datetime.now()
            if (
                _cached_device_id is None
                or _cache_time is None
                or (now - _cache_time) > timedelta(hours=1)
            ):
                _cached_device_id = await get_device_id(proxy, client=client)
                _cache_time = datetime.now()

    return _cached_device_id


class SklandCredentialExpiredError(RuntimeError):
    """森空岛当前 cred 已失效，需要刷新或重新授权。"""


def _is_expected_skland_exception(error: Exception) -> bool:
    """判断可预期的凭据、上游或网络失败。"""

    return isinstance(
        error,
        (
            SklandCredentialExpiredError,
            ValueError,
            httpx.HTTPError,
            TimeoutError,
            ConnectionError,
        ),
    )


def _log_skland_exception(stage: str, error: Exception) -> str:
    """按异常类型记录森空岛失败，并返回安全的非空原因。"""

    expected = _is_expected_skland_exception(error)
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


def _hypergryph_headers(device_id: str) -> dict[str, str]:
    """构造鹰角通行证接口所需的客户端标识请求头。"""

    return {
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 12; SM-A5560 Build/V417IR; wv) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
            "Chrome/101.0.4951.61 Safari/537.36; SKLand/1.52.1"
        ),
        "dId": device_id,
        "x-requested-with": "com.hypergryph.skland",
    }


async def _get_grant_code(
    client: httpx.AsyncClient,
    token_value: str,
    device_id: str,
) -> str:
    """使用鹰角 OAuth Token 获取森空岛授权码。"""

    response = await client.post(
        SKLAND_GRANT_CODE_URL,
        json={"appCode": SKLAND_APP_CODE, "token": token_value, "type": 0},
        headers=_hypergryph_headers(device_id),
    )
    response_data = _parse_json_object(response)
    if response_data.get("status") != 0:
        message = str(
            response_data.get("msg") or response_data.get("message") or ""
        ).strip()
        if "grantv2req.token" in message.lower() and "'max'" in message.lower():
            message = "OAuth Token 格式或长度无效，请重新登录获取"
        raise ValueError(f"获得森空岛认证代码失败: {message or '上游拒绝请求'}")
    data = response_data.get("data")
    if not isinstance(data, dict) or not data.get("code"):
        raise ValueError("森空岛认证代码响应格式无效")
    return str(data["code"])


async def _get_cred_by_code(
    client: httpx.AsyncClient,
    grant_code: str,
    device_id: str,
) -> dict[str, object]:
    """使用授权码获取森空岛 cred 和接口签名 Token。"""

    web_headers = {
        "content-type": "application/json",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        ),
        "referer": "https://www.skland.com/",
        "origin": "https://www.skland.com",
        "dId": device_id,
        "platform": "3",
        "timestamp": str(int(time.time())),
        "vName": "1.0.0",
    }
    response = await client.post(
        SKLAND_CRED_CODE_URL,
        json={"code": grant_code, "kind": 1},
        headers=web_headers,
    )
    response_data = _parse_json_object(response)
    if response_data.get("code") != 0:
        raise ValueError(
            f"获得森空岛 cred 失败: {response_data.get('message') or '上游拒绝请求'}"
        )
    data = response_data.get("data")
    if not isinstance(data, dict) or not data.get("token") or not data.get("cred"):
        raise ValueError("森空岛 cred 响应格式无效")
    return data


def build_skland_signed_headers(
    sign_token: str,
    *,
    path: str,
    body_or_query: str,
    device_id: str,
    headers: dict[str, str],
    platform: str = "1",
    version: str = "1.21.0",
) -> dict[str, str]:
    """为森空岛 API 请求生成统一签名头，不修改输入字典。"""

    timestamp = str(int(time.time() * 1000 - 2000))[:-3]
    signature_headers = {
        "platform": platform,
        "timestamp": timestamp,
        "dId": device_id,
        "vName": version,
    }
    signature_text = path + body_or_query + timestamp + json.dumps(
        signature_headers,
        separators=(",", ":"),
    )
    digest = hashlib.md5(
        hmac.new(
            sign_token.encode("utf-8"),
            signature_text.encode("utf-8"),
            hashlib.sha256,
        )
        .hexdigest()
        .encode("utf-8")
    ).hexdigest()
    result = dict(headers)
    result.update(signature_headers)
    result["sign"] = digest
    result.pop("token", None)
    return result


def _skland_credential_headers(
    cred: str,
    sign_token: str = "",
) -> dict[str, str]:
    """构造森空岛凭据请求头，兼容既有 iOS 客户端标识。"""

    headers = {
        "cred": cred,
        "User-Agent": "Skland/1.21.0 (com.hypergryph.skland; build:102100065; iOS 17.6.0; ) Alamofire/5.7.1",
        "Accept-Encoding": "gzip",
        "Connection": "keep-alive",
        "Content-Type": "application/json",
    }
    if sign_token:
        headers["token"] = sign_token
    return headers


async def prepare_skland_session_credential(
    client: httpx.AsyncClient,
    raw_credential: str | dict[str, object],
    device_id: str,
) -> dict[str, str]:
    """解析森空岛凭据，并在缺少 cred/token 时完成 OAuth 授权。"""

    # 直调签到历史上允许凭据同时携带 OAuth Token 和不完整缓存；
    # 此时丢弃缓存并重新授权。活动入口仍会在调用本函数前执行严格校验。
    credential = parse_skland_credential(raw_credential)
    if credential["cred"] and credential["token"]:
        return credential
    if not credential["oauthToken"]:
        raise ValueError("森空岛登录凭据为空")
    grant_code = await _get_grant_code(
        client,
        credential["oauthToken"],
        device_id,
    )
    cred_data = await _get_cred_by_code(client, grant_code, device_id)
    return parse_skland_credential(
        {
            "oauthToken": credential["oauthToken"],
            "token": cred_data.get("token"),
            "cred": cred_data.get("cred"),
            "userId": cred_data.get("userId"),
        }
    )


async def refresh_skland_session_credential(
    client: httpx.AsyncClient,
    credential: dict[str, str],
    device_id: str,
    *,
    timeout: float | None = None,
) -> dict[str, str]:
    """使用当前 cred 刷新森空岛接口签名 Token。"""

    if not credential["cred"] or not credential["token"]:
        raise ValueError("森空岛缺少可刷新的 cred")
    headers = build_skland_signed_headers(
        credential["token"],
        path="/web/v1/auth/refresh",
        body_or_query="",
        device_id=device_id,
        headers=_skland_credential_headers(
            credential["cred"],
            credential["token"],
        ),
    )
    if timeout is None:
        response = await client.get(SKLAND_REFRESH_URL, headers=headers)
    else:
        response = await client.get(
            SKLAND_REFRESH_URL,
            headers=headers,
            timeout=timeout,
        )
    response_data = _parse_json_object(response)
    if response_data.get("code") != 0:
        raise ValueError(
            f"森空岛凭据刷新失败: {response_data.get('message') or '上游拒绝请求'}"
        )
    data = response_data.get("data")
    if not isinstance(data, dict) or not data.get("token"):
        raise ValueError("森空岛凭据刷新响应格式无效")
    return parse_skland_credential({**credential, "token": data["token"]})


async def login_skland_with_password(
    phone: str,
    password: str,
    *,
    proxy: str | None = None,
) -> str:
    """一次性使用手机号和密码获取并校验森空岛凭据。"""

    phone_value = str(phone or "").strip()
    password_value = str(password or "")
    if not phone_value or not password_value:
        raise ValueError("手机号和密码不能为空")

    async with _create_skland_client(proxy) as client:
        device_id = await get_cached_device_id(proxy, client=client)
        response = await client.post(
            SKLAND_PASSWORD_LOGIN_URL,
            json={"phone": phone_value, "password": password_value},
            headers=_hypergryph_headers(device_id),
        )
        response_data = _parse_json_object(response)
        if response_data.get("status") != 0:
            message = response_data.get("msg") or response_data.get("message")
            raise ValueError(f"森空岛账号密码登录失败: {message or '上游拒绝请求'}")
        data = response_data.get("data")
        if not isinstance(data, dict) or not data.get("token"):
            raise ValueError("森空岛登录响应未返回有效 Token")

        oauth_token = str(data["token"])
        grant_code = await _get_grant_code(client, oauth_token, device_id)
        cred_data = await _get_cred_by_code(client, grant_code, device_id)

    return serialize_skland_credential(
        {
            "oauthToken": oauth_token,
            "token": cred_data.get("token"),
            "cred": cred_data.get("cred"),
            "userId": cred_data.get("userId"),
        }
    )


async def skland_sign_in(
    token: str,
    app_code: str = "arknights",
    proxy: str | None = None,
    *,
    on_credential_update: Callable[[str], Awaitable[None]] | None = None,
) -> dict[str, object]:
    """串行执行森空岛签到，协调旧用户链路与工具链路。"""

    async with _skland_sign_lock:
        return await _run_skland_sign_in(
            token,
            app_code=app_code,
            proxy=proxy,
            on_credential_update=on_credential_update,
        )


async def _run_skland_sign_in(
    token: str,
    app_code: str = "arknights",
    proxy: str | None = None,
    *,
    on_credential_update: Callable[[str], Awaitable[None]] | None = None,
) -> dict[str, object]:
    """森空岛签到"""

    binding_url = SKLAND_BINDING_URL
    arknights_sign_url = SKLAND_ARKNIGHTS_SIGN_URL
    endfield_sign_url = SKLAND_ENDFIELD_SIGN_URL

    client: httpx.AsyncClient | None = None
    device_id = ""

    async def get_sign_header(url: str, method, body, old_header, sign_token):
        """获取带签名的请求头"""
        p = parse.urlparse(url)

        assert client is not None
        current_device_id = device_id or await get_cached_device_id(
            proxy, client=client
        )
        if method.lower() == "get":
            body_or_query = p.query or ""
        else:
            body_or_query = json.dumps(body) if body else ""
        return build_skland_signed_headers(
            sign_token,
            path=p.path,
            body_or_query=body_or_query,
            device_id=current_device_id,
            headers=old_header,
        )

    def copy_header(cred, token=None):
        """复制请求头并添加cred和token"""
        return _skland_credential_headers(cred, token or "")

    async def get_binding_list(cred, sign_token, app_code_override: str | None = None):
        """查询已绑定的角色列表

        Args:
            app_code_override: 覆盖外层 app_code，用于 all 模式下按游戏过滤
        """
        code = app_code_override if app_code_override else app_code
        assert client is not None
        v = []
        response = await client.get(
            binding_url,
            headers=await get_sign_header(
                binding_url,
                "get",
                None,
                copy_header(cred, sign_token),
                sign_token,
            ),
        )
        if response.status_code == 401:
            raise SklandCredentialExpiredError("森空岛凭据已失效")
        rsp = _parse_json_object(response)
        if not response.is_success or rsp.get("code") != 0:
            message = str(rsp.get("message") or "")
            if "未登录" in message:
                raise SklandCredentialExpiredError("森空岛凭据已失效")
            reason = message or f"HTTP {response.status_code}"
            raise ValueError(f"森空岛角色列表请求失败: {reason}")
        data = rsp.get("data")
        if isinstance(data, list):
            binding_groups = data
        elif isinstance(data, dict):
            binding_groups = data.get("list")
            if binding_groups is None and data.get("appCode"):
                binding_groups = [data]
            elif binding_groups is None and isinstance(data.get("bindingList"), list):
                # 兼容部分版本直接返回单个 app 的绑定列表。
                binding_groups = [{"appCode": code, "bindingList": data["bindingList"]}]
            elif binding_groups is None and isinstance(data.get("binding_list"), list):
                binding_groups = [
                    {"appCode": code, "binding_list": data["binding_list"]}
                ]
        else:
            binding_groups = None
        if not isinstance(binding_groups, list):
            raise ValueError("森空岛角色列表响应缺少绑定列表")
        for item in binding_groups:
            if not isinstance(item, dict):
                continue
            item_app_code = item.get("appCode") or item.get("app_code")
            if item_app_code != code:
                continue
            binding_list = item.get("bindingList")
            if binding_list is None and isinstance(item.get("binding_list"), list):
                binding_list = item["binding_list"]
            binding_list = binding_list or []
            if not isinstance(binding_list, list):
                raise ValueError("森空岛角色绑定列表响应格式无效")
            v.extend(entry for entry in binding_list if isinstance(entry, dict))
        return v

    async def check_attendance_today(cred, sign_token, uid, game_id) -> bool:
        """检查今天是否已经签到"""
        query_url = f"{arknights_sign_url}?uid={uid}&gameId={game_id}"

        try:
            assert client is not None
            response = await client.get(
                query_url,
                headers=await get_sign_header(
                    query_url,
                    "get",
                    None,
                    copy_header(cred, sign_token),
                    sign_token,
                ),
            )
            rsp = _parse_json_object(response)

            if rsp.get("code") != 0:
                logger.warning(f"检查签到状态失败: {rsp.get('message')}")
                return False

            data = rsp.get("data") or {}
            records = data.get("records", []) if isinstance(data, dict) else []
            now = datetime.now(tz=UTC8)
            today = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

            record_list = records if isinstance(records, list) else []
            for record in record_list:
                if not isinstance(record, dict):
                    continue
                record_time = int(record.get("ts", 0))
                if record_time >= today:
                    return True

            return False
        except Exception as e:
            _log_skland_exception("检查森空岛签到状态失败", e)
            return False

    async def sign_for_arknights(cred, sign_token) -> dict[str, object]:
        """方舟签到"""
        characters = await get_binding_list(
            cred, sign_token, app_code_override="arknights"
        )
        result = {"成功": [], "重复": [], "失败": [], "总计": len(characters)}

        attendance_states = await asyncio.gather(
            *(
                check_attendance_today(
                    cred,
                    sign_token,
                    character.get("uid", ""),
                    _get_arknights_game_id(character),
                )
                for character in characters
            )
        )

        for index, character in enumerate(characters):
            nick_name = character.get("nickName", "")
            channel_name = character.get("channelName", "森空岛")
            uid = character.get("uid", "")
            # 统一 account 格式: 别名/昵称(uid)
            character_name = (
                f"{nick_name}/{nick_name}({uid})"
                if uid
                else f"{nick_name}/{channel_name}"
            )
            game_id = _get_arknights_game_id(character)

            if attendance_states[index]:
                result["重复"].append(character_name)
                logger.info(f"{character_name} 今天已经签到过了")
                continue

            body = {
                "gameId": game_id,
                "uid": uid,
            }

            try:
                assert client is not None
                sign_headers = await get_sign_header(
                    arknights_sign_url,
                    "post",
                    body,
                    copy_header(cred, sign_token),
                    sign_token,
                )
                response = await client.post(
                    arknights_sign_url,
                    headers=sign_headers,
                    content=json.dumps(body),
                )
                rsp = _parse_json_object(response)

                if rsp.get("code") != 0:
                    if is_skland_already_signed(rsp):
                        result["重复"].append(character_name)
                        logger.info(f"{character_name} 重复签到")
                    else:
                        result["失败"].append(character_name)
                        logger.warning(
                            f"{character_name} 签到失败: {rsp.get('message')}"
                        )
                else:
                    result["成功"].append(character_name)
                    logger.info(f"{character_name} 签到成功")

            except Exception as e:
                result["失败"].append(character_name)
                _log_skland_exception("明日方舟签到失败", e)

            if index < len(characters) - 1:
                await asyncio.sleep(SKLAND_SIGN_INTERVAL)

        return result

    async def do_sign_for_endfield(
        cred, sign_token, role: dict[str, object]
    ) -> dict[str, object]:
        headers = await get_sign_header(
            endfield_sign_url,
            "post",
            "",  # 终末地签到不发 body，签名计算使用空字符串
            copy_header(cred, sign_token),
            sign_token,
        )
        headers.update(
            {
                "Content-Type": "application/json",
                "sk-game-role": f"3_{role['roleId']}_{role['serverId']}",
                "referer": "https://game.skland.com/",
                "origin": "https://game.skland.com/",
            }
        )

        assert client is not None
        response = await client.post(endfield_sign_url, headers=headers)
        return _parse_json_object(response)

    async def sign_for_endfield(cred, sign_token) -> dict[str, object]:
        """终末地签到"""
        characters = await get_binding_list(
            cred, sign_token, app_code_override="endfield"
        )
        role_items = []
        for character in characters:
            roles = character.get("roles") or []
            if not isinstance(roles, list):
                roles = []
            roles = [role for role in roles if isinstance(role, dict)]
            game_name = character.get("gameName")
            channel_name = character.get("channelName")
            for role in roles:
                nickname = str(role.get("nickname") or "").strip()
                role_id = role.get("roleId", "")
                # 统一 account 格式: 别名/昵称(角色ID)
                character_name = (
                    f"{nickname}/{nickname}({role_id})"
                    if role_id
                    else f"{nickname}/{channel_name}"
                )
                role_items.append((character, role, character_name, game_name))

        result = {"成功": [], "重复": [], "失败": [], "总计": len(role_items)}

        for index, (_character, role, character_name, game_name) in enumerate(
            role_items
        ):
            try:
                rsp = await do_sign_for_endfield(cred, sign_token, role)
                if rsp.get("code") != 0:
                    if is_skland_already_signed(rsp):
                        result["重复"].append(character_name)
                        logger.info(f"{character_name} 重复签到")
                    else:
                        result["失败"].append(character_name)
                        logger.warning(
                            f"{character_name} 签到失败: {rsp.get('message')}"
                        )
                else:
                    data = rsp.get("data") or {}
                    if not isinstance(data, dict):
                        data = {}
                    award_ids = data.get("awardIds", [])
                    resource_map = data.get("resourceInfoMap", {})
                    awards = []
                    award_list = award_ids if isinstance(award_ids, list) else []
                    for award in award_list:
                        if not isinstance(award, dict):
                            continue
                        award_id = award.get("id")
                        if (
                            award_id
                            and isinstance(resource_map, dict)
                            and award_id in resource_map
                        ):
                            resource = resource_map[award_id]
                            if isinstance(resource, dict) and resource.get("name"):
                                awards.append(
                                    f"{resource['name']}x{resource.get('count', 1)}"
                                )
                    if awards:
                        logger.info(
                            f"[{game_name}] {character_name} 签到成功: {'、'.join(awards)}"
                        )
                    result["成功"].append(character_name)
                    logger.info(f"{character_name} 签到成功")
            except Exception as e:
                result["失败"].append(character_name)
                _log_skland_exception("终末地签到失败", e)

            if index < len(role_items) - 1:
                await asyncio.sleep(SKLAND_SIGN_INTERVAL)

        return result

    async def run_sign(credential: dict[str, str]) -> dict[str, object]:
        cred = credential["cred"]
        sign_token = credential["token"]
        if not cred or not sign_token:
            raise ValueError("森空岛凭据不完整")
        if app_code == "all":
            # 两个游戏的角色绑定彼此独立；单个游戏接口异常时保留另一侧结果。
            try:
                ar = await sign_for_arknights(cred, sign_token)
            except SklandCredentialExpiredError:
                raise
            except Exception as exc:
                reason = _log_skland_exception("明日方舟角色列表/签到失败", exc)
                ar = {"成功": [], "重复": [], "失败": [reason], "总计": 0}
            try:
                ef = await sign_for_endfield(cred, sign_token)
            except SklandCredentialExpiredError:
                raise
            except Exception as exc:
                reason = _log_skland_exception("终末地角色列表/签到失败", exc)
                ef = {"成功": [], "重复": [], "失败": [reason], "总计": 0}
            return {"arknights": ar, "endfield": ef}
        if app_code == "endfield":
            return await sign_for_endfield(cred, sign_token)
        return await sign_for_arknights(cred, sign_token)

    try:
        async with _create_skland_client(proxy) as shared_client:
            client = shared_client
            device_id = await get_cached_device_id(proxy, client=client)
            credential = await prepare_skland_session_credential(
                client,
                token,
                device_id,
            )
            try:
                result = await run_sign(credential)
            except SklandCredentialExpiredError:
                try:
                    credential = await refresh_skland_session_credential(
                        client,
                        credential,
                        device_id,
                    )
                except Exception as exc:
                    if not _is_expected_skland_exception(exc):
                        raise
                    if not credential["oauthToken"]:
                        raise
                    credential = await prepare_skland_session_credential(
                        client,
                        credential["oauthToken"],
                        device_id,
                    )
                result = await run_sign(credential)

        serialized = serialize_skland_credential(credential)
        if (
            on_credential_update is not None
            and serialized
            and serialized != str(token or "").strip()
        ):
            try:
                await on_credential_update(serialized)
            except Exception as e:
                _log_skland_exception("森空岛凭据回写失败", e)
        return result
    except Exception as e:
        reason = _log_skland_exception("森空岛签到失败", e)
        return {"成功": [], "重复": [], "失败": [reason], "总计": 0}
