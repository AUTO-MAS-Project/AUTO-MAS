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
import uuid
from collections.abc import Mapping

import httpx

from app.core import Config
from app.utils.logger import get_logger
from app.utils.security import format_exception_reason

from .community_contract import CommunitySignResult


logger = get_logger("云原神签到")

_BASE_URL = "https://api-cloudgame.mihoyo.com/hk4e_cg_cn"
_WALLET_URL = f"{_BASE_URL}/wallet/wallet/get"
_NOTIFICATIONS_URL = (
    f"{_BASE_URL}/gamer/api/listNotifications"
    "?status=NotificationStatusUnread&type=NotificationTypePopup&is_sort=true"
)
_ACK_NOTIFICATION_URL = f"{_BASE_URL}/gamer/api/ackNotification"


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

    if payload.get("retcode") not in (0, None) or payload.get("message") != "OK":
        retcode = payload.get("retcode")
        code = retcode if isinstance(retcode, (int, str)) else "未知"
        raise ValueError(f"云原神钱包查询失败（错误码 {code}）")
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


def _headers(token: str) -> dict[str, str]:
    device_id = str(uuid.uuid3(uuid.NAMESPACE_URL, f"cloud-genshin:{token}"))
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Connection": "Keep-Alive",
        "Content-Type": "application/json;charset=utf-8",
        "Origin": "https://ys.mihoyo.com",
        "Referer": "https://ys.mihoyo.com/",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
        ),
        "x-rpc-app_id": "4",
        "x-rpc-app_version": "6.0.0",
        "x-rpc-cg_game_biz": "hk4e_cn",
        "x-rpc-channel": "mihoyo",
        "x-rpc-client_type": "17",
        "x-rpc-combo_token": token,
        "x-rpc-cps": "mac_mihoyo",
        "x-rpc-device_id": device_id,
        "x-rpc-device_model": "Macintosh",
        "x-rpc-device_name": "Apple Macintosh",
        "x-rpc-language": "zh-cn",
        "x-rpc-op_biz": "clgm_cn",
        "x-rpc-sys_version": "Mac OS 10.15.7",
        "x-rpc-vendor_id": "2",
    }


async def _request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: Mapping[str, str],
    json_body: Mapping[str, object] | None = None,
) -> Mapping[str, object]:
    response = await client.request(
        method,
        url,
        headers=dict(headers),
        json=dict(json_body) if json_body is not None else None,
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


def _response_data(payload: Mapping[str, object], stage: str) -> Mapping[str, object]:
    if payload.get("retcode") in (-100, 10001):
        raise ValueError("云原神 combo token 已失效")
    if payload.get("retcode") not in (0, None) or payload.get("message") != "OK":
        retcode = payload.get("retcode")
        code = retcode if isinstance(retcode, (int, str)) else "未知"
        raise ValueError(f"{stage}失败（错误码 {code}）")
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
) -> dict[str, object]:
    return CommunitySignResult(
        account=f"{account_name}/云原神",
        account_uid=account_uid,
        game="云原神",
        platform="米游社",
        status=status,
        reward=reward,
        reason=reason,
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
        credential = validate_cloud_genshin_token(token)
        headers = _headers(credential)
        resolved_proxy = proxy if proxy is not None else Config.proxy
        async with httpx.AsyncClient(
            proxy=resolved_proxy,
            trust_env=False,
        ) as client:
            before = await _query_free_time(client, headers)
            notification_ids = await _list_notification_ids(client, headers)
            for index, notification_id in enumerate(notification_ids):
                await _ack_notification(client, headers, notification_id)
                if index + 1 < len(notification_ids):
                    await asyncio.sleep(1.0)
            if notification_ids:
                await asyncio.sleep(1.0)
            after = await _query_free_time(client, headers)

        gained = calculate_cloud_genshin_gain(before, after)
        return [
            _result(
                account_name,
                account_uid,
                status="成功" if gained else "已签到",
                reward=f"新增 {format_cloud_genshin_duration(gained)}",
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
