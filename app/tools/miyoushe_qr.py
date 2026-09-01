#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""
米游社扫码登录模块（可选补丁）

本模块为独立功能，不影响签到核心逻辑。
可安全删除本文件及 app/api/qr_login.py、前端扫码按钮，
不会影响任何已有功能。

扫码流程（Passport 模式，参考 thesadru/genshin.py）:
  1. createQRLogin      → POST 获取二维码 URL + ticket
  2. queryQRLoginStatus  → POST 轮询状态，确认后从响应头或响应体获取 cookies
  3. cookies 中通常包含 cookie_token_v2、ltuid_v2 等 Passport 字段；
     保存时同时补充签到模块兼容的 cookie_token、stuid 等别名

参考项目:
  - https://github.com/thesadru/genshin.py (2026-06 最新)
"""

from http.cookies import CookieError, SimpleCookie

import httpx

from app.core import Config
from app.utils.logger import get_logger
from app.utils.security import format_exception_reason

logger = get_logger("米游社扫码登录")

# ---- Passport QR 登录 API（对齐 genshin.py） ----

CREATE_QRCODE_URL = (
    "https://passport-api.miyoushe.com/account/ma-cn-passport/web/createQRLogin"
)
CHECK_QRCODE_URL = (
    "https://passport-api.miyoushe.com/account/ma-cn-passport/web/queryQRLoginStatus"
)

# ---- 请求头（对齐 genshin.py QRCODE_HEADERS） ----

QR_HEADERS = {
    "x-rpc-app_id": "bll8iq97cem8",
    "x-rpc-client_type": "4",
    "x-rpc-game_biz": "bbs_cn",
    "x-rpc-device_fp": "38d7fa104e5d7",
}

QR_EXPIRED_MESSAGE = "二维码已过期或无效，请重新生成"

# Passport QR 登录目前返回 v2 Cookie。签到模块仍兼容旧字段，因此在
# 保存前补充旧字段别名，同时保留服务端返回的原始字段。
_QR_COOKIE_ALIASES = {
    "cookie_token_v2": "cookie_token",
    "stoken_v2": "stoken",
    "ltuid_v2": "stuid",
    "stuid_v2": "stuid",
    "account_id_v2": "account_id",
    "mid_v2": "mid",
    "ltmid_v2": "mid",
    "account_mid_v2": "mid",
    "ltoken_v2": "ltoken",
}

_QR_COOKIE_FIELDS = (
    "cookie_token",
    "cookie_token_v2",
    "stoken",
    "stoken_v2",
    "mid",
    "mid_v2",
    "ltmid_v2",
    "account_mid_v2",
    "ltoken",
    "ltoken_v2",
    "stuid",
    "stuid_v2",
    "ltuid",
    "ltuid_v2",
    "account_id",
    "account_id_v2",
    "login_uid",
)


def _is_expired_message(message: object) -> bool:
    """判断 Passport 错误消息是否表示二维码已经失效。"""
    if not isinstance(message, str):
        return False
    message = message.lower()
    return any(
        hint in message
        for hint in (
            "expired",
            "expire",
            "invalid qr",
            "二维码已过期",
            "二维码失效",
            "二维码无效",
        )
    )


def _add_qr_cookie_aliases(cookie_parts: dict[str, str]) -> None:
    """补全签到模块使用的旧 Cookie 字段名，不覆盖服务端原值。"""
    for source, target in _QR_COOKIE_ALIASES.items():
        if not cookie_parts.get(target) and cookie_parts.get(source):
            cookie_parts[target] = cookie_parts[source]


def _has_qr_auth_cookie(cookie_parts: dict[str, str]) -> bool:
    return any(
        cookie_parts.get(key)
        for key in ("cookie_token", "cookie_token_v2", "stoken", "stoken_v2")
    )


def _has_qr_uid_cookie(cookie_parts: dict[str, str]) -> bool:
    return any(
        cookie_parts.get(key)
        for key in (
            "stuid",
            "stuid_v2",
            "ltuid",
            "account_id",
            "login_uid",
            "ltuid_v2",
            "account_id_v2",
        )
    )


def _qr_headers(device: str) -> dict:
    """构建带 device_id 的请求头"""
    headers = QR_HEADERS.copy()
    headers["x-rpc-device_id"] = device
    return headers


async def create_qr_login(proxy: str | None = None) -> dict:
    """创建米游社扫码登录二维码（Passport 模式）

    POST /createQRLogin（无需 body）

    Returns:
        {ticket, qr_url, device} 或 {error}
    """
    from uuid import uuid4

    device = str(uuid4())

    try:
        headers = _qr_headers(device)
        async with httpx.AsyncClient(proxy=proxy or Config.proxy) as client:
            resp = await client.post(
                CREATE_QRCODE_URL,
                headers=headers,
                timeout=30.0,
            )
            data = resp.json()
        if not isinstance(data, dict):
            logger.error("创建二维码响应格式无效")
            return {"error": "服务器返回空响应，无法创建二维码"}

        qr_data = data.get("data")
        data_keys = sorted(qr_data) if isinstance(qr_data, dict) else []
        logger.debug(
            f"QR create 响应: retcode={data.get('retcode')}, data_keys={data_keys}"
        )

        if data.get("retcode") != 0:
            message = data.get("message")
            return {
                "error": message
                if isinstance(message, str) and message
                else "创建二维码失败"
            }

        if not isinstance(qr_data, dict):
            logger.error("创建二维码数据格式无效")
            return {"error": "服务器返回空响应，无法创建二维码"}
        qr_url = qr_data.get("url", "")
        ticket = qr_data.get("ticket", "")

        if not qr_url or not ticket:
            logger.error("创建二维码响应缺少必要字段")
            return {"error": "返回数据缺少二维码 url 或 ticket"}

        logger.info("QR 创建成功")
        return {"ticket": ticket, "qr_url": qr_url, "device": device}
    except (httpx.HTTPError, OSError) as e:
        logger.warning(format_exception_reason(e, stage="创建扫码登录网络请求失败"))
        return {"error": "创建二维码网络请求失败，请检查网络或代理设置"}
    except ValueError:
        logger.exception("创建扫码登录响应解析异常")
        return {"error": "二维码响应解析失败"}
    except Exception:
        logger.exception("创建扫码登录程序异常")
        return {"error": "创建二维码失败，请稍后重试"}


async def check_qr_status(
    ticket: str,
    device: str,
    proxy: str | None = None,
) -> dict:
    """轮询扫码登录状态

    POST /queryQRLoginStatus  body: {"ticket": ticket}

    确认后 cookies 通常在 Set-Cookie 响应头中返回，也兼容确认响应体字段。

    Returns:
        {status: "Init"|"Scanned"|"Confirmed"|"Expired"|"Error",
         cookies_str?, error?}
    """
    try:
        headers = _qr_headers(device)
        async with httpx.AsyncClient(proxy=proxy or Config.proxy) as client:
            resp = await client.post(
                CHECK_QRCODE_URL,
                headers=headers,
                json={"ticket": ticket},
                timeout=30.0,
            )
            data = resp.json()

        if not isinstance(data, dict):
            logger.warning("QR query 返回空响应，二维码视为已失效")
            return {"status": "Expired", "message": QR_EXPIRED_MESSAGE}

        retcode = data.get("retcode", 0)
        response_message = data.get("message")
        if not isinstance(response_message, str):
            response_message = ""
        qr_data = data.get("data")
        qr_status = qr_data.get("status") if isinstance(qr_data, dict) else None
        logger.debug(f"QR query 响应: retcode={retcode}, data={qr_status or '?'}")

        if retcode != 0:
            if _is_expired_message(response_message):
                return {
                    "status": "Expired",
                    "message": response_message or QR_EXPIRED_MESSAGE,
                }
            return {"status": "Error", "error": response_message or "查询失败"}

        if qr_data is None:
            return {"status": "Expired", "message": QR_EXPIRED_MESSAGE}
        if not isinstance(qr_data, dict):
            logger.error("二维码状态响应格式无效")
            return {"status": "Error", "error": "二维码状态响应格式无效"}

        status = qr_data.get("status")
        if not status:
            return {"status": "Expired", "message": QR_EXPIRED_MESSAGE}

        if status in ("Init", "Created"):
            return {"status": "Init"}
        if status == "Scanned":
            return {"status": "Scanned"}
        if status == "Confirmed":
            # Confirmed — 从响应头或确认响应体提取 cookies
            cookies_str = _extract_cookies_from_headers(resp, qr_data)
            cookie_parts = _parse_cookie_string(cookies_str)
            if not _has_qr_auth_cookie(cookie_parts):
                return {
                    "status": "Error",
                    "error": "扫码确认成功但响应未包含认证 Cookie (cookie_token 或 stoken)",
                }
            if not _has_qr_uid_cookie(cookie_parts):
                return {"status": "Error", "error": "扫码确认成功但响应未包含用户 UID"}
            logger.info(
                f"QR 确认成功, 获取到 cookies: {bool(cookies_str)}, "
                f"fields={sorted(cookie_parts)}"
            )
            return {
                "status": "Confirmed",
                "cookies_str": cookies_str,
            }
        if status in ("Expired", "Canceled"):
            if status == "Expired":
                return {"status": status, "message": QR_EXPIRED_MESSAGE}
            return {"status": status, "message": "登录已取消"}
        logger.error("收到未知扫码状态")
        return {
            "status": "Error",
            "error": f"未知扫码状态: {status}",
        }
    except (httpx.HTTPError, OSError) as e:
        logger.warning(format_exception_reason(e, stage="查询扫码状态网络请求失败"))
        return {
            "status": "Error",
            "error": "查询二维码状态网络请求失败，请检查网络或代理设置",
        }
    except ValueError:
        logger.exception("解析扫码状态 JSON 失败")
        return {"status": "Error", "error": "响应解析失败"}
    except Exception:
        logger.exception("查询扫码状态程序异常")
        return {"status": "Error", "error": "查询二维码状态失败，请稍后重试"}


def _extract_cookie_payload(payload: object) -> dict[str, str]:
    """从确认响应体提取已知 Cookie 字段，不记录或信任其它业务字段。"""
    if not isinstance(payload, dict):
        return {}

    cookie_parts: dict[str, str] = {}
    for key in _QR_COOKIE_FIELDS:
        value = payload.get(key)
        if isinstance(value, str) and value:
            cookie_parts[key] = value

    for key in ("cookie", "cookies", "cookie_str", "cookies_str"):
        raw_value = payload.get(key)
        if isinstance(raw_value, str):
            cookie_parts.update(_parse_cookie_string(raw_value))
        elif isinstance(raw_value, dict):
            for cookie_key in _QR_COOKIE_FIELDS:
                value = raw_value.get(cookie_key)
                if isinstance(value, str) and value:
                    cookie_parts.setdefault(cookie_key, value)
    return cookie_parts


def _extract_cookies_from_headers(
    resp: httpx.Response,
    payload: object = None,
) -> str:
    """从响应头的 Set-Cookie 中提取 stoken 等 cookies

    对齐 genshin.py: 确认后服务器通过 Set-Cookie 返回 v2 Passport 字段，
    同时补充签到模块兼容的旧字段别名。
    """
    cookie_parts: dict[str, str] = {}
    for value in resp.headers.get_list("set-cookie"):
        # 解析每个 Set-Cookie 头；忽略单个格式异常，避免丢掉其它 Cookie。
        sc = SimpleCookie()
        try:
            sc.load(value)
        except CookieError:
            logger.warning("忽略格式无效的 Set-Cookie 响应头")
            continue
        for key, morsel in sc.items():
            if morsel.value:
                cookie_parts[key] = morsel.value

    # httpx 的 CookieJar 是另一条解析路径。某些代理会重写响应头，
    # 因此从 CookieJar 补充缺失字段，但不覆盖上面的原始值。
    try:
        for key, value in resp.cookies.items():
            if value:
                cookie_parts.setdefault(key, value)
    except (RuntimeError, AttributeError):
        # 单元测试构造的 Response 可能没有 request，无法读取 CookieJar。
        pass

    # 某些 Passport 响应会把 Cookie 字段放在 data 中而不是 Set-Cookie。
    # 仅合并已知字段，并保留响应头中的值优先级。
    for key, value in _extract_cookie_payload(payload).items():
        cookie_parts.setdefault(key, value)

    if not cookie_parts:
        return ""

    _add_qr_cookie_aliases(cookie_parts)

    # 构造 cookie 字符串
    parts = [f"{k}={v}" for k, v in cookie_parts.items() if v]
    return "; ".join(parts)


def _parse_cookie_string(cookie_str: str) -> dict[str, str]:
    """解析 Cookie 字符串，仅用于校验扫码响应字段。"""
    cookies: dict[str, str] = {}
    for item in cookie_str.split(";"):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        if key.strip() and value.strip():
            cookies[key.strip()] = value.strip()
    return cookies


async def exchange_stoken(
    game_token: str,
    uid: str,
    proxy: str | None = None,
) -> dict:
    """兼容接口：Passport 模式下此函数不被调用，cookies 直接从响应头获取。

    保留此函数以兼容 API 路由层的调用。
    """
    return {"error": "Passport 模式不需要 exchange_stoken，请直接使用 cookies_str"}
