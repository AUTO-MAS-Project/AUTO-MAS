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
  2. queryQRLoginStatus  → POST 轮询状态，确认后从响应头获取 cookies
  3. cookies 中直接包含 stoken + mid

参考项目:
  - https://github.com/thesadru/genshin.py (2026-06 最新)
"""

import json
from http.cookies import SimpleCookie

import httpx

from app.core import Config
from app.utils.logger import get_logger

logger = get_logger("米游社扫码登录")

# ---- Passport QR 登录 API（对齐 genshin.py） ----

CREATE_QRCODE_URL = "https://passport-api.miyoushe.com/account/ma-cn-passport/web/createQRLogin"
CHECK_QRCODE_URL = "https://passport-api.miyoushe.com/account/ma-cn-passport/web/queryQRLoginStatus"

# ---- 请求头（对齐 genshin.py QRCODE_HEADERS） ----

QR_HEADERS = {
    "x-rpc-app_id": "bll8iq97cem8",
    "x-rpc-client_type": "4",
    "x-rpc-game_biz": "bbs_cn",
    "x-rpc-device_fp": "38d7fa104e5d7",
}


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
        logger.debug(f"QR create 响应: {data}")

        if data.get("retcode") != 0:
            return {"error": data.get("message", "创建二维码失败")}

        qr_data = data.get("data", {})
        qr_url = qr_data.get("url", "")
        ticket = qr_data.get("ticket", "")

        if not qr_url or not ticket:
            return {"error": f"返回数据缺少 url 或 ticket: {qr_data}"}

        logger.info(f"QR 创建成功, ticket={ticket[:8]}...")
        return {"ticket": ticket, "qr_url": qr_url, "device": device}
    except Exception as e:
        logger.error(f"创建扫码登录失败: {e}")
        return {"error": str(e)}


async def check_qr_status(
    ticket: str, device: str, proxy: str | None = None,
) -> dict:
    """轮询扫码登录状态

    POST /queryQRLoginStatus  body: {"ticket": ticket}

    确认后 cookies 直接在 Set-Cookie 响应头中返回。

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
        logger.debug(f"QR query 响应: retcode={data.get('retcode')}, data={data.get('data',{}).get('status','?')}")

        retcode = data.get("retcode", 0)

        if retcode != 0:
            return {"status": "Error", "error": data.get("message", "查询失败")}

        qr_data = data.get("data", {})
        status = qr_data.get("status", "Init")

        if status == "Init":
            return {"status": "Init"}
        elif status == "Scanned":
            return {"status": "Scanned"}
        else:
            # Confirmed — 从 Set-Cookie 响应头提取 cookies
            cookies_str = _extract_cookies_from_headers(resp)
            logger.info(f"QR 确认成功, 获取到 cookies: {bool(cookies_str)}")
            return {
                "status": "Confirmed",
                "cookies_str": cookies_str,
            }
    except json.JSONDecodeError as e:
        logger.error(f"解析扫码状态 JSON 失败: {e}")
        return {"status": "Error", "error": "响应解析失败"}
    except Exception as e:
        logger.error(f"查询扫码状态失败: {e}")
        return {"status": "Error", "error": str(e)}


def _extract_cookies_from_headers(resp: httpx.Response) -> str:
    """从响应头的 Set-Cookie 中提取 stoken 等 cookies

    对齐 genshin.py: 确认后服务器通过 Set-Cookie 返回 stoken、mid、cookie_token 等。
    """
    cookie_parts = {}
    for name, value in resp.headers.multi_items():
        if name.lower() == "set-cookie":
            # 解析每个 Set-Cookie 头
            sc = SimpleCookie()
            sc.load(value)
            for key, morsel in sc.items():
                cookie_parts[key] = morsel.value

    if not cookie_parts:
        return ""

    # 构造 cookie 字符串
    parts = [f"{k}={v}" for k, v in cookie_parts.items() if v]
    return "; ".join(parts)


async def exchange_stoken(
    game_token: str, uid: str, proxy: str | None = None,
) -> dict:
    """兼容接口：Passport 模式下此函数不被调用，cookies 直接从响应头获取。

    保留此函数以兼容 API 路由层的调用。
    """
    return {"error": "Passport 模式不需要 exchange_stoken，请直接使用 cookies_str"}
