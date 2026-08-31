#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   GameToken API compatibility knowledge:
#       nonebot-plugin-mystool Copyright (c) 2022 Ljzd-PRO (MIT License)
#       https://github.com/Ljzd-PRO/nonebot-plugin-mystool

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

扫码流程（GameToken 优先，Passport 回退）:
  1. GameToken/Passport 创建二维码，返回二维码 URL + ticket
  2. 轮询状态，GameToken 确认后兑换完整凭据，Passport 从响应头或响应体获取 cookies
  3. 保存时补充签到模块兼容的认证与 UID 别名

参考项目:
  - https://github.com/thesadru/genshin.py (2026-06 最新)
"""

import json
from http.cookies import CookieError, SimpleCookie
from urllib.parse import parse_qs, urlparse

import httpx

from app.core import Config
from app.utils.logger import get_logger
from app.utils.security import format_exception_reason

logger = get_logger("米游社扫码登录")

# ---- Passport QR 登录 API（对齐 genshin.py） ----

CREATE_QRCODE_URL = "https://passport-api.miyoushe.com/account/ma-cn-passport/web/createQRLogin"
CHECK_QRCODE_URL = "https://passport-api.miyoushe.com/account/ma-cn-passport/web/queryQRLoginStatus"
# ---- GameToken QR 登录 API（参考项目已确认的请求/响应形状） ----
GAME_TOKEN_CREATE_URL = "https://hk4e-sdk.mihoyo.com/hk4e_cn/combo/panda/qrcode/fetch"
GAME_TOKEN_CHECK_URL = "https://hk4e-sdk.mihoyo.com/hk4e_cn/combo/panda/qrcode/query"
GAME_TOKEN_STOKEN_URL = (
    "https://api-takumi.mihoyo.com/account/ma-cn-session/app/getTokenByGameToken"
)
GAME_TOKEN_COOKIE_URL = (
    "https://api-takumi.mihoyo.com/auth/api/getCookieAccountInfoByGameToken"
)
GAME_TOKEN_APP_ID = "2"
_GAME_TOKEN_TICKET_PREFIX = "game-token:"
# Passport 扫码不保证下发 stoken；缺少时用 login_ticket 换取多类型 Token 补全，
# 只有拿到 stoken 才能走不受验证码限制的小组件接口查询活跃度。
MULTI_TOKEN_URL = (
    "https://api-takumi.mihoyo.com/auth/api/getMultiTokenByLoginTicket"
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
    # login_ticket 仅用于缺少 stoken 时换取 stoken，不参与签到请求。
    "login_ticket",
)

_QR_V2_COOKIE_PAIRS = (
    ("cookie_token", "cookie_token_v2"),
    ("stoken", "stoken_v2"),
    ("ltoken", "ltoken_v2"),
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
    # 部分扫码响应只使用旧字段名，但值已经是 v2 格式；补出 v2 字段，
    # 使后续便笺查询可以识别完整认证形态。
    for source, target in _QR_V2_COOKIE_PAIRS:
        value = cookie_parts.get(source)
        if (
            not cookie_parts.get(target)
            and value
            and value.startswith("v2_")
        ):
            cookie_parts[target] = value
    for source, target in _QR_COOKIE_ALIASES.items():
        if not cookie_parts.get(target) and cookie_parts.get(source):
            cookie_parts[target] = cookie_parts[source]


async def _supplement_stoken(
    cookie_parts: dict[str, str], proxy: str | None = None
) -> None:
    """用 login_ticket 补全缺失的 stoken，失败时保持原有字段不变。

    Passport 扫码返回的 Cookie 字段并不稳定：同一条链路有时只下发 v1
    stoken，有时只给 cookie_token/ltoken。缺少 stoken_v2 时活跃度查询只能
    退回实时便笺并触发验证码风控，因此在这里做一次补全。

    Args:
        cookie_parts: 已从扫码响应解析出的 Cookie 字段，就地补全。
        proxy: 代理地址，与扫码请求保持一致。
    """
    login_ticket = cookie_parts.get("login_ticket")
    uid = next(
        (
            cookie_parts[key]
            for key in (
                "stuid",
                "stuid_v2",
                "ltuid",
                "ltuid_v2",
                "account_id",
                "account_id_v2",
                "login_uid",
            )
            if cookie_parts.get(key)
        ),
        "",
    )
    if not login_ticket or not uid:
        return

    try:
        async with httpx.AsyncClient(
            proxy=proxy or Config.proxy,
            trust_env=False,
        ) as client:
            resp = await client.get(
                MULTI_TOKEN_URL,
                params={
                    "login_ticket": login_ticket,
                    "token_types": "3",
                    "uid": uid,
                },
                timeout=10.0,
            )
        payload = resp.json()
    except (httpx.HTTPError, OSError, ValueError) as e:
        logger.warning(
            format_exception_reason(e, stage="补全 stoken 请求失败")
        )
        return

    if not isinstance(payload, dict) or payload.get("retcode") != 0:
        logger.warning("补全 stoken 失败：login_ticket 可能已过期")
        return

    data = payload.get("data")
    token_list = data.get("list") if isinstance(data, dict) else None
    if not isinstance(token_list, list):
        return
    for token_info in token_list:
        if not isinstance(token_info, dict):
            continue
        name = token_info.get("name")
        token = token_info.get("token")
        if not isinstance(token, str) or not token:
            continue
        if name in ("stoken", "stoken_v2"):
            cookie_parts.setdefault("stoken", token)
            if name == "stoken_v2" or token.startswith("v2_"):
                # v2 stoken 必须配套 mid，否则保存校验会直接拒绝。
                cookie_parts.setdefault("stoken_v2", token)
                mid = token_info.get("mid")
                if isinstance(mid, str) and mid:
                    cookie_parts.setdefault("mid", mid)
        elif name in ("ltoken", "ltoken_v2"):
            cookie_parts.setdefault("ltoken", token)
            if name == "ltoken_v2":
                cookie_parts.setdefault("ltoken_v2", token)
    # 上游可能返回空列表，只有确实补到 stoken 才记成功，避免误导排查。
    if cookie_parts.get("stoken_v2"):
        logger.info("已通过 login_ticket 补全 stoken_v2")
    elif cookie_parts.get("stoken"):
        logger.warning("login_ticket 仅返回 stoken_v1，未补全 stoken_v2")
    else:
        logger.warning("补全 stoken 未获得可用 Token")


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


def _has_complete_qr_credential(cookie_parts: dict[str, str]) -> bool:
    """确认便笺所需的 v2 会话 Token 与配套 mid 均已取得。"""

    return bool(
        cookie_parts.get("stoken_v2")
        and any(
            cookie_parts.get(key)
            for key in ("mid", "mid_v2", "ltmid_v2", "account_mid_v2")
        )
    )


def _serialize_cookie_parts(cookie_parts: dict[str, str]) -> str:
    """完整序列化 Cookie 字段，不裁剪字段和值。"""

    return "; ".join(
        f"{key}={value}" for key, value in cookie_parts.items() if value
    )


def _qr_headers(device: str) -> dict:
    """构建带 device_id 的请求头"""
    headers = QR_HEADERS.copy()
    headers["x-rpc-device_id"] = device
    return headers


def _game_token_qr_data(payload: object) -> tuple[str, str] | None:
    """从 GameToken 二维码响应中提取二维码 URL 和 ticket。"""

    if not isinstance(payload, dict):
        return None
    qr_url = str(payload.get("url") or "").strip()
    if not qr_url:
        return None
    parsed = urlparse(qr_url)
    path = parsed.path.lower()
    host = parsed.netloc.lower()
    known_sdk_qr = host == "hk4e-sdk.mihoyo.com" and (
        "/qrcode/" in path or path.endswith("/qrcode.html")
    )
    known_account_qr = (
        host == "user.mihoyo.com" and path == "/qr_code_in_game.html"
    )
    if parsed.scheme.lower() != "https" or not (
        known_sdk_qr or known_account_qr
    ):
        return None

    ticket = str(payload.get("ticket") or "").strip()
    if not ticket:
        ticket_values = parse_qs(parsed.query).get("ticket", [])
        ticket = str(ticket_values[0] if ticket_values else "").strip()
    if not ticket:
        return None
    return qr_url, ticket


async def _create_game_token_qr(
    device: str, proxy: str | None = None
) -> tuple[str, str] | None:
    """尝试创建参考项目使用的 GameToken 二维码。"""

    async with httpx.AsyncClient(
        proxy=proxy or Config.proxy,
        trust_env=False,
    ) as client:
        response = await client.post(
            GAME_TOKEN_CREATE_URL,
            json={"app_id": GAME_TOKEN_APP_ID, "device": device},
            timeout=15.0,
        )
        payload = response.json()
    if not isinstance(payload, dict) or payload.get("retcode") != 0:
        return None
    return _game_token_qr_data(payload.get("data"))


async def create_qr_login(proxy: str | None = None) -> dict:
    """创建米游社扫码登录二维码（GameToken 优先，Passport 回退）

    优先使用已确认的 GameToken 链路；其不可用时继续使用 Passport。

    Returns:
        {ticket, qr_url, device} 或 {error}
    """
    from uuid import uuid4

    device = str(uuid4())

    try:
        game_token_qr = await _create_game_token_qr(device, proxy)
    except (httpx.HTTPError, OSError, ValueError) as error:
        logger.debug(f"GameToken QR 不可用，回退 Passport: {type(error).__name__}")
        game_token_qr = None
    except Exception as error:
        logger.debug(f"GameToken QR 回退 Passport: {type(error).__name__}")
        game_token_qr = None

    if game_token_qr is not None:
        qr_url, game_token_ticket = game_token_qr
        logger.info("GameToken QR 创建成功")
        return {
            "ticket": f"{_GAME_TOKEN_TICKET_PREFIX}{game_token_ticket}",
            "qr_url": qr_url,
            "device": device,
        }

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


async def _check_game_token_qr_status(
    ticket: str, device: str, proxy: str | None = None,
) -> dict:
    """查询 GameToken 二维码并兑换为可保存的完整 Cookie。"""

    try:
        async with httpx.AsyncClient(
            proxy=proxy or Config.proxy,
            trust_env=False,
        ) as client:
            response = await client.post(
                GAME_TOKEN_CHECK_URL,
                json={
                    "app_id": GAME_TOKEN_APP_ID,
                    "device": device,
                    "ticket": ticket,
                },
                timeout=30.0,
            )
            data = response.json()
    except (httpx.HTTPError, OSError) as error:
        logger.warning(
            format_exception_reason(
                error,
                stage="查询 GameToken 扫码状态网络请求失败",
            )
        )
        return {
            "status": "Error",
            "error": "查询二维码状态网络请求失败，请检查网络或代理设置",
        }
    except ValueError:
        logger.warning("解析 GameToken 扫码状态响应失败")
        return {"status": "Error", "error": "二维码状态响应解析失败"}
    except Exception:
        logger.exception("查询 GameToken 扫码状态程序异常")
        return {"status": "Error", "error": "查询二维码状态失败，请稍后重试"}

    if not isinstance(data, dict):
        return {"status": "Error", "error": "二维码状态响应格式无效"}

    retcode = data.get("retcode", 0)
    response_message = data.get("message")
    if not isinstance(response_message, str):
        response_message = ""
    if retcode not in (0, "0"):
        if str(retcode) == "-106" or _is_expired_message(response_message):
            return {
                "status": "Expired",
                "message": response_message or QR_EXPIRED_MESSAGE,
            }
        return {"status": "Error", "error": response_message or "查询失败"}

    qr_data = data.get("data")
    if not isinstance(qr_data, dict):
        return {"status": "Error", "error": "二维码状态响应格式无效"}

    status = qr_data.get("stat")
    if status in ("Init", "Created"):
        return {"status": "Init"}
    if status == "Scanned":
        return {"status": "Scanned"}
    if status in ("Expired", "Canceled"):
        return {
            "status": status,
            "message": (
                QR_EXPIRED_MESSAGE
                if status == "Expired"
                else "登录已取消"
            ),
        }

    payload = qr_data.get("payload")
    raw_payload = payload.get("raw") if isinstance(payload, dict) else None
    if not isinstance(raw_payload, str) or not raw_payload.strip():
        return {
            "status": "Error",
            "error": "二维码确认响应缺少登录信息",
        }
    try:
        login_payload = json.loads(raw_payload)
    except (TypeError, ValueError):
        return {"status": "Error", "error": "二维码登录信息格式无效"}
    if not isinstance(login_payload, dict):
        return {"status": "Error", "error": "二维码登录信息格式无效"}

    uid = str(login_payload.get("uid") or "").strip()
    game_token = str(login_payload.get("token") or "").strip()
    if not uid or not game_token:
        return {"status": "Error", "error": "二维码确认响应缺少登录信息"}

    try:
        exchanged = await exchange_stoken(game_token, uid, proxy)
    except (httpx.HTTPError, OSError, ValueError) as error:
        logger.warning(
            format_exception_reason(
                error,
                stage="GameToken 换取完整凭据失败",
            )
        )
        return {
            "status": "Error",
            "error": "GameToken 换取完整凭据失败，请检查登录状态或网络",
        }
    except Exception:
        logger.exception("GameToken 换取完整凭据程序异常")
        return {
            "status": "Error",
            "error": "GameToken 换取完整凭据失败，请稍后重试",
        }
    finally:
        # GameToken 只在本次兑换中使用，不返回、不落盘。
        game_token = ""
        raw_payload = ""
        login_payload.clear()

    cookies_str = exchanged.get("cookies_str") if isinstance(exchanged, dict) else ""
    if not isinstance(cookies_str, str) or not cookies_str:
        return {"status": "Error", "error": "未获取到完整登录凭据"}
    cookie_parts = _parse_cookie_string(cookies_str)
    _add_qr_cookie_aliases(cookie_parts)
    if not _has_qr_auth_cookie(cookie_parts):
        return {"status": "Error", "error": "完整登录凭据缺少认证字段"}
    if not _has_qr_uid_cookie(cookie_parts):
        return {"status": "Error", "error": "完整登录凭据缺少用户 UID"}
    if not _has_complete_qr_credential(cookie_parts):
        return {
            "status": "Error",
            "error": "完整登录凭据缺少 stoken_v2 或配套 mid",
        }
    cookies_str = _serialize_cookie_parts(cookie_parts)
    logger.info("GameToken QR 确认成功，已换取完整凭据")
    return {"status": "Confirmed", "cookies_str": cookies_str}


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
    if isinstance(ticket, str) and ticket.startswith(_GAME_TOKEN_TICKET_PREFIX):
        return await _check_game_token_qr_status(
            ticket[len(_GAME_TOKEN_TICKET_PREFIX):],
            device,
            proxy,
        )

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
            # 缺少 stoken_v2 时先补全；已有 v1 stoken 也不能满足便笺认证。
            if not cookie_parts.get("stoken_v2"):
                await _supplement_stoken(cookie_parts, proxy)
            _add_qr_cookie_aliases(cookie_parts)
            # login_ticket 只用于换取 stoken，不参与签到请求，保存前移除。
            cookie_parts.pop("login_ticket", None)
            if not _has_complete_qr_credential(cookie_parts):
                return {
                    "status": "Error",
                    "error": "扫码凭据缺少 stoken_v2 或配套 mid，登录链路未完成",
                }
            cookies_str = _serialize_cookie_parts(cookie_parts)
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


def _extract_cookie_payload(
    payload: object, *, include_nested: bool = True, _depth: int = 0
) -> dict[str, str]:
    """从确认响应体提取已知 Cookie 字段，不记录或信任其它业务字段。"""
    if not isinstance(payload, dict):
        return {}

    cookie_parts: dict[str, str] = {}
    for key in _QR_COOKIE_FIELDS:
        value = payload.get(key)
        if isinstance(value, str) and value:
            cookie_parts[key] = value

    user_info = payload.get("user_info")
    if isinstance(user_info, dict):
        aid = user_info.get("aid") or user_info.get("account_id")
        mid = user_info.get("mid")
        if isinstance(aid, str) and aid:
            cookie_parts.setdefault("account_id_v2", aid)
            cookie_parts.setdefault("ltuid_v2", aid)
        if isinstance(mid, str) and mid:
            cookie_parts.setdefault("mid", mid)

    tokens = payload.get("tokens")
    if isinstance(tokens, dict):
        for name in _QR_COOKIE_FIELDS:
            token = tokens.get(name)
            if isinstance(token, str) and token:
                cookie_parts.setdefault(name, token)
    elif isinstance(tokens, list):
        for token_info in tokens:
            if not isinstance(token_info, dict):
                continue
            name = token_info.get("name")
            token = token_info.get("token")
            if name in _QR_COOKIE_FIELDS and isinstance(token, str) and token:
                cookie_parts.setdefault(name, token)

    for key in ("cookie", "cookies", "cookie_str", "cookies_str"):
        raw_value = payload.get(key)
        if isinstance(raw_value, str):
            for cookie_key, value in _parse_cookie_string(raw_value).items():
                cookie_parts.setdefault(cookie_key, value)
        elif isinstance(raw_value, dict):
            # 已知 Cookie 封套中的字符串字段均原样保留，避免后续新增字段
            # 因本地白名单未更新而在“全量”返回中丢失。
            for cookie_key, value in raw_value.items():
                if isinstance(cookie_key, str) and isinstance(value, str) and value:
                    cookie_parts.setdefault(cookie_key, value)
    if include_nested and _depth < 2:
        # Passport 的不同确认响应会把同一份 Cookie 放入已知业务封套中。
        # 只展开有限深度，兼容序列化 JSON 封套并避免扫描无关响应内容。
        for key in ("data", "result", "payload", "login_data"):
            nested = payload.get(key)
            if isinstance(nested, str):
                try:
                    nested = json.loads(nested)
                except (TypeError, ValueError):
                    nested = None
            if isinstance(nested, dict):
                for nested_key, nested_value in _extract_cookie_payload(
                    nested, include_nested=True, _depth=_depth + 1
                ).items():
                    cookie_parts.setdefault(nested_key, nested_value)
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
    """通过 GameToken 获取 stoken_v2/mid 和可选 cookie_token。"""

    token_value = str(game_token or "").strip()
    uid_value = str(uid or "").strip()
    if not token_value or not uid_value:
        raise ValueError("GameToken 登录信息为空")
    try:
        account_id = int(uid_value)
    except (TypeError, ValueError) as error:
        raise ValueError("GameToken 登录返回的 UID 无效") from error

    request_body = {
        "account_id": account_id,
        "game_token": token_value,
    }
    headers = {"x-rpc-app_id": "bll8iq97cem8"}

    try:
        async with httpx.AsyncClient(
            proxy=proxy or Config.proxy,
            trust_env=False,
        ) as client:
            response = await client.post(
                GAME_TOKEN_STOKEN_URL,
                headers=headers,
                json=request_body,
                timeout=30.0,
            )
            try:
                data = response.json()
            except ValueError as error:
                raise ValueError("GameToken 换取 stoken 接口返回无效 JSON") from error

            if (
                not isinstance(data, dict)
                or data.get("retcode") not in (0, "0")
            ):
                raise ValueError("GameToken 换取 stoken 失败")
            token_data = data.get("data")
            token_info = (
                token_data.get("token")
                if isinstance(token_data, dict)
                else None
            )
            user_info = (
                token_data.get("user_info")
                if isinstance(token_data, dict)
                else None
            )
            stoken_v2 = (
                token_info.get("token")
                if isinstance(token_info, dict)
                else None
            )
            mid = user_info.get("mid") if isinstance(user_info, dict) else None
            if not isinstance(stoken_v2, str) or not stoken_v2.strip():
                raise ValueError("GameToken 换取 stoken 响应缺少 stoken")
            if not isinstance(mid, str) or not mid.strip():
                raise ValueError("GameToken 换取 stoken 响应缺少 mid")

            stoken_v2 = stoken_v2.strip()
            mid = mid.strip()
            cookie_parts = {
                "stoken_v2": stoken_v2,
                "stoken": stoken_v2,
                "mid": mid,
                "mid_v2": mid,
                "ltmid_v2": mid,
                "account_mid_v2": mid,
                "stuid": uid_value,
                "stuid_v2": uid_value,
                "ltuid": uid_value,
                "ltuid_v2": uid_value,
                "account_id": uid_value,
                "account_id_v2": uid_value,
                "login_uid": uid_value,
            }

            # CookieToken 不是兑换 stoken 的必要条件；上游暂时不可用时，
            # 仍保留 stoken_v2 + mid 供签到模块派生。
            try:
                cookie_response = await client.post(
                    GAME_TOKEN_COOKIE_URL,
                    headers=headers,
                    json=request_body,
                    timeout=30.0,
                )
                cookie_data = cookie_response.json()
            except (httpx.HTTPError, OSError, ValueError):
                logger.debug("GameToken 获取 cookie_token 跳过")
            else:
                cookie_payload = cookie_data.get("data") if isinstance(
                    cookie_data, dict
                ) else None
                cookie_info = (
                    cookie_payload.get("token")
                    if isinstance(cookie_payload, dict)
                    else None
                )
                cookie_token = (
                    cookie_info.get("token")
                    if isinstance(cookie_info, dict)
                    else None
                )
                if (
                    isinstance(cookie_data, dict)
                    and cookie_data.get("retcode") in (0, "0")
                    and isinstance(cookie_token, str)
                    and cookie_token.strip()
                ):
                    cookie_token = cookie_token.strip()
                    cookie_parts["cookie_token"] = cookie_token
                    if cookie_token.startswith("v2_"):
                        cookie_parts["cookie_token_v2"] = cookie_token

            return {
                "cookies_str": _serialize_cookie_parts(cookie_parts)
            }
    finally:
        request_body["game_token"] = ""
        token_value = ""
