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


"""云原神签到协议适配，只返回本轮时长增量，不保存钱包数据。"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import uuid
from collections.abc import Mapping

import httpx

from app.core import Config
from app.utils.logger import get_logger
from app.utils.security import format_exception_reason

from .community_contract import CommunitySignResult


logger = get_logger("云原神签到")

_BASE_URL = "https://api-cloudgame.mihoyo.com/hk4e_cg_cn"
_WEB_LOGIN_URL = (
    "https://hk4e-sdk.mihoyo.com/hk4e_cn/combo/granter/login/webLogin"
)
_WALLET_URL = f"{_BASE_URL}/wallet/wallet/get"
_NOTIFICATIONS_URL = (
    f"{_BASE_URL}/gamer/api/listNotifications"
    "?status=NotificationStatusUnread&type=NotificationTypePopup&is_sort=true"
)
_ACK_NOTIFICATION_URL = f"{_BASE_URL}/gamer/api/ackNotification"
_APP_ID = 4
_CHANNEL_ID = 1
_GAME_BIZ = "hk4e_cn"
_APP_SIGN_KEY = b"d0d3a7342df2026a70f650b907800111"
_MIYOUSHE_COOKIE_FIELDS = frozenset(
    {
        "uni_web_token",
        "cookie_token",
        "cookie_token_v2",
        "stoken",
        "stoken_v2",
        "stuid",
        "stuid_v2",
        "ltuid",
        "ltuid_v2",
        "account_id",
        "account_id_v2",
    }
)
_AUTH_EXPIRED_RETCODES = frozenset({"-100", "10001"})


class CloudGenshinUnavailableError(ValueError):
    """当前米游社账号未开通或无法使用云原神。"""


class CloudGenshinAuthenticationError(ValueError):
    """米游社或云原神凭据已失效。"""


class CloudGenshinBusinessError(ValueError):
    """云原神接口返回了非认证类业务失败。"""


def validate_cloud_genshin_token(token: str) -> str:
    """校验并返回去除首尾空白的云原神 combo token。"""

    raw_value = str(token or "")
    if any(ord(character) < 32 or ord(character) == 127 for character in raw_value):
        raise ValueError("云原神 combo token 不应包含控制字符")
    value = raw_value.strip(" ")
    if not value:
        raise ValueError("云原神 combo token 不能为空")
    if len(value) < 20 or len(value) > 4096:
        raise ValueError("云原神 combo token 长度无效")
    return value


def parse_cloud_genshin_free_time(payload: Mapping[str, object]) -> int:
    """从钱包响应严格读取剩余免费时长，单位为秒。"""

    retcode = payload.get("retcode")
    if str(retcode).strip() in _AUTH_EXPIRED_RETCODES:
        raise CloudGenshinAuthenticationError("云原神登录凭据已失效")
    if retcode not in (0, "0", None) or payload.get("message") != "OK":
        code = retcode if isinstance(retcode, (int, str)) else "未知"
        raise CloudGenshinBusinessError(f"云原神钱包查询失败（错误码 {code}）")
    data = payload.get("data")
    free_time = data.get("free_time") if isinstance(data, Mapping) else None
    value = free_time.get("free_time") if isinstance(free_time, Mapping) else None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("云原神钱包 free_time 字段格式无效")
    return value


def format_cloud_genshin_duration(seconds: int) -> str:
    """将非负秒数格式化为稳定的中文时长。"""

    if seconds < 0:
        raise ValueError("云原神时长不能为负数")
    hours, remainder = divmod(seconds, 3600)
    minutes, trailing_seconds = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f"{hours} 小时")
    if minutes:
        parts.append(f"{minutes} 分钟")
    if trailing_seconds or not parts:
        parts.append(f"{trailing_seconds} 秒")
    return " ".join(parts)


def calculate_cloud_genshin_gain(before: int, after: int) -> int:
    """计算本轮新增时长；消费或未变化均归零。"""

    if (
        isinstance(before, bool)
        or not isinstance(before, int)
        or before < 0
        or isinstance(after, bool)
        or not isinstance(after, int)
        or after < 0
    ):
        raise ValueError("云原神钱包时长格式无效")
    return max(0, after - before)


def build_cloud_genshin_combo_token(combo_token: str, open_id: str) -> str:
    """将 Web 登录结果签名为云原神接口使用的完整 combo token。"""

    token = validate_cloud_genshin_token(combo_token)
    uid = str(open_id or "").strip()
    if not uid or any(ord(character) < 32 for character in uid):
        raise ValueError("云原神 Web 登录返回的 open_id 无效")
    message = (
        f"app_id={_APP_ID}&channel_id={_CHANNEL_ID}"
        f"&combo_token={token}&open_id={uid}"
    )
    signature = hmac.new(
        _APP_SIGN_KEY,
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return (
        f"ai={_APP_ID};ci={_CHANNEL_ID};oi={uid};ct={token};"
        f"si={signature};bi={_GAME_BIZ}"
    )


def _headers(token: str) -> dict[str, str]:
    """构造普通云原神查询头；设备字段仅属于 Web 登录换凭据链路。"""

    return {"x-rpc-combo_token": token}


async def _request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: Mapping[str, str],
    json_body: Mapping[str, object] | None = None,
    cookies: Mapping[str, str] | None = None,
) -> Mapping[str, object]:
    response = await client.request(
        method,
        url,
        headers=dict(headers),
        json=dict(json_body) if json_body is not None else None,
        cookies=dict(cookies) if cookies is not None else None,
        timeout=30.0,
    )
    text = response.text.strip()
    if not text:
        raise ValueError("云原神接口返回空响应，疑似被风控")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("云原神接口返回非 JSON 内容，疑似被风控") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("云原神接口返回数据格式无效")
    return payload


def _web_login_headers(device_id: str, device_fp: str) -> dict[str, str]:
    """构造米游社 Cookie 换取云原神临时凭据所需的浏览器请求头。"""

    return {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://ys.mihoyo.com",
        "Referer": "https://ys.mihoyo.com/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
        ),
        "x-rpc-channel_id": str(_CHANNEL_ID),
        "x-rpc-client_type": "22",
        "x-rpc-device_fp": device_fp,
        "x-rpc-device_id": device_id,
        "x-rpc-device_model": "Chrome%20140.0.0.0",
        "x-rpc-device_name": "Chrome",
        "x-rpc-device_os": "Windows%2010%2064-bit",
        "x-rpc-game_biz": _GAME_BIZ,
        "x-rpc-language": "zh-cn",
        "x-rpc-mdk_version": "2.24.0",
    }


async def _prepare_cloud_genshin_credential(
    client: httpx.AsyncClient,
    credential: str,
    *,
    proxy: str | None = None,
) -> tuple[str, bool, str]:
    """兼容历史 token，并按需从米游社 Cookie 换取本轮临时 token。"""

    value = validate_cloud_genshin_token(credential)

    from .miyoushe import (
        derive_miyoushe_cookie_token,
        prepare_miyoushe_session,
        validate_miyoushe_cookie,
    )

    session = prepare_miyoushe_session(value)
    if not _MIYOUSHE_COOKIE_FIELDS.intersection(session.cookies):
        return value, False, ""

    validate_miyoushe_cookie(value)
    cookies = dict(session.cookies)
    if not cookies.get("cookie_token"):
        cookie_token, derived_uid = await derive_miyoushe_cookie_token(
            stoken=cookies["stoken"],
            mid=cookies["mid"],
            stuid=session.uid,
            proxy=proxy,
        )
        cookies["cookie_token"] = cookie_token
        if derived_uid:
            session_uid = derived_uid
        else:
            session_uid = session.uid
    else:
        session_uid = session.uid

    device_id = str(cookies.get("_MHYUUID") or session.device_id).strip()
    device_fp = str(cookies.get("DEVICEFP") or "38d7fa104e5d7").strip()
    payload = await _request_json(
        client,
        "POST",
        _WEB_LOGIN_URL,
        headers=_web_login_headers(device_id, device_fp),
        json_body={"app_id": _APP_ID, "channel_id": _CHANNEL_ID},
        cookies=cookies,
    )
    if payload.get("retcode") not in (0, "0"):
        if str(payload.get("retcode")).strip() in _AUTH_EXPIRED_RETCODES:
            raise CloudGenshinAuthenticationError(
                "米游社凭据已失效，无法登录云原神"
            )
        # 云原神是米游社凭据的自动附加能力。除明确认证失效外，上游的
        # 业务拒绝通常表示账号未开通或不可用，不应拖累普通游戏签到。
        raise CloudGenshinUnavailableError("当前米游社账号无法使用云原神，已跳过")
    data = payload.get("data")
    combo_token = data.get("combo_token") if isinstance(data, Mapping) else None
    open_id = (
        data.get("open_id") if isinstance(data, Mapping) else None
    ) or session_uid
    if not isinstance(combo_token, str) or not combo_token.strip() or not open_id:
        raise ValueError("云原神 Web 登录返回数据不完整")
    return (
        build_cloud_genshin_combo_token(combo_token, str(open_id)),
        True,
        device_id or str(uuid.uuid3(uuid.NAMESPACE_URL, session_uid)),
    )


def _response_data(payload: Mapping[str, object], stage: str) -> Mapping[str, object]:
    retcode = payload.get("retcode")
    if str(retcode).strip() in _AUTH_EXPIRED_RETCODES:
        raise CloudGenshinAuthenticationError("云原神 combo token 已失效")
    if retcode not in (0, "0", None) or payload.get("message") != "OK":
        code = retcode if isinstance(retcode, (int, str)) else "未知"
        raise CloudGenshinBusinessError(f"{stage}失败（错误码 {code}）")
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise ValueError(f"{stage}返回数据格式无效")
    return data


async def _query_free_time(
    client: httpx.AsyncClient,
    headers: Mapping[str, str],
) -> int:
    payload = await _request_json(client, "GET", _WALLET_URL, headers=headers)
    return parse_cloud_genshin_free_time(payload)


async def _list_notification_ids(
    client: httpx.AsyncClient,
    headers: Mapping[str, str],
) -> tuple[str | int, ...]:
    payload = await _request_json(
        client,
        "GET",
        _NOTIFICATIONS_URL,
        headers=headers,
    )
    data = _response_data(payload, "查询云原神签到通知")
    notifications = data.get("list")
    if not isinstance(notifications, list):
        raise ValueError("云原神通知列表格式无效")
    result = []
    for item in notifications:
        if not isinstance(item, Mapping):
            continue
        notification_id = item.get("id")
        if isinstance(notification_id, bool) or not isinstance(
            notification_id, (str, int)
        ):
            continue
        if str(notification_id).strip():
            result.append(notification_id)
    return tuple(result)


async def _ack_notification(
    client: httpx.AsyncClient,
    headers: Mapping[str, str],
    notification_id: str | int,
) -> None:
    payload = await _request_json(
        client,
        "POST",
        _ACK_NOTIFICATION_URL,
        headers=headers,
        json_body={"id": notification_id},
    )
    _response_data(payload, "确认云原神签到通知")


def _result(
    account_name: str,
    account_uid: str,
    *,
    status: str,
    reward: str = "",
    reason: str = "",
    completed: bool = False,
    notification_only: bool = False,
) -> dict[str, object]:
    return CommunitySignResult(
        account=f"{account_name}/云原神",
        account_uid=account_uid,
        game="云原神",
        platform="米游社",
        status=status,
        reward=reward,
        reason=reason,
        completed=completed,
        notification_only=notification_only,
    ).to_legacy()


async def cloud_genshin_sign_in(
    token: str,
    *,
    account_name: str,
    account_uid: str,
    proxy: str | None = None,
) -> list[dict[str, object]]:
    """确认云原神签到通知并返回本轮新增免费时长。"""

    try:
        resolved_proxy = proxy if proxy is not None else Config.proxy
        async with httpx.AsyncClient(
            proxy=resolved_proxy,
            trust_env=False,
        ) as client:
            credential, from_miyoushe_cookie, _device_id = (
                await _prepare_cloud_genshin_credential(
                    client,
                    token,
                    proxy=resolved_proxy,
                )
            )
            headers = _headers(credential)
            try:
                before = await _query_free_time(client, headers)
                notification_ids = await _list_notification_ids(client, headers)
                for index, notification_id in enumerate(notification_ids):
                    await _ack_notification(
                        client,
                        headers,
                        notification_id,
                    )
                    if index + 1 < len(notification_ids):
                        await asyncio.sleep(1.0)
                if notification_ids:
                    await asyncio.sleep(1.0)
                after = await _query_free_time(client, headers)
            except CloudGenshinBusinessError as error:
                if from_miyoushe_cookie:
                    raise CloudGenshinUnavailableError(
                        "当前米游社账号无法使用云原神，已跳过"
                    ) from error
                raise

        gained = calculate_cloud_genshin_gain(before, after)
        return [
            _result(
                account_name,
                account_uid,
                status="成功" if gained else "已签到",
                reward=f"新增 {format_cloud_genshin_duration(gained)}",
            )
        ]
    except CloudGenshinUnavailableError as error:
        logger.info(f"[{account_name}] {error}")
        return [
            _result(
                account_name,
                account_uid,
                status="跳过",
                reason=str(error),
                completed=True,
                notification_only=True,
            )
        ]
    except Exception as error:
        expected = isinstance(
            error,
            (ValueError, httpx.HTTPError, TimeoutError, ConnectionError),
        )
        reason = format_exception_reason(
            error,
            stage="云原神签到失败",
            include_message=expected,
        )
        if expected:
            logger.warning(reason)
        else:
            logger.exception("云原神签到程序异常")
        return [
            _result(
                account_name,
                account_uid,
                status="失败",
                reason=reason,
            )
        ]
