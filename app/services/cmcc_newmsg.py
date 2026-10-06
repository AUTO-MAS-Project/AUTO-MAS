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

"""中国移动新消息（5G 消息）出站通知服务。"""

from __future__ import annotations

import asyncio
import json
import secrets
from typing import Any

import websockets

from .openclaw_common import split_text

SERVER_URL = "wss://5gvas01.cmicmaap.com/gtw-ai/openclaw/ws/msg"
PROTOCOL_VERSION = "2.0"
AUTH_TIMEOUT_SECONDS = 10
OPEN_TIMEOUT_SECONDS = 10
CLOSE_TIMEOUT_SECONDS = 5
TEXT_CHUNK_LIMIT = 2000


class CMCCNewMsgError(RuntimeError):
    """中国移动新消息认证或协议错误。"""


def _safe_reason(reason: Any, api_key: str) -> str:
    """返回不包含 API Key 的服务端错误描述。"""

    text = str(reason or "未知错误").strip()
    return text.replace(api_key, "***")[:300]


async def _receive_message(connection: Any) -> dict[str, Any]:
    """接收并解析一条协议消息。"""

    raw = await connection.recv()
    try:
        message = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise CMCCNewMsgError("中国移动新消息服务返回了无效响应") from exc
    if not isinstance(message, dict):
        raise CMCCNewMsgError("中国移动新消息服务返回了无效响应")
    return message


async def _authenticate(connection: Any, api_key: str) -> None:
    """发送认证帧并等待服务端确认。"""

    await connection.send(
        json.dumps({"type": "auth", "apiKey": api_key, "version": PROTOCOL_VERSION})
    )
    try:
        async with asyncio.timeout(AUTH_TIMEOUT_SECONDS):
            while True:
                message = await _receive_message(connection)
                message_type = message.get("type")
                if message_type == "auth_ok":
                    return
                if message_type in {"auth_failed", "error"}:
                    reason = _safe_reason(message.get("message"), api_key)
                    raise CMCCNewMsgError(f"中国移动新消息认证失败: {reason}")
    except TimeoutError as exc:
        raise CMCCNewMsgError("中国移动新消息认证超时") from exc


async def send_cmcc_newmsg(
    *, api_key: str, content: str, proxy: str | None = None
) -> tuple[str, ...]:
    """通过中国移动新消息通道提交纯文本通知。

    API Key 同时作为认证凭据与目标标识，这是中国移动公开 Channel 的当前
    协议约定。返回值仅表示消息帧已提交到认证连接，不代表终端已经送达。

    Args:
        api_key: 中国移动新消息 Channel API Key。
        content: 待发送的纯文本通知正文。
        proxy: 可选 WebSocket 代理地址。

    Returns:
        tuple[str, ...]: 已提交消息的 ID。

    Raises:
        ValueError: API Key 为空或格式不正确。
        CMCCNewMsgError: 连接、认证或协议交互失败。
    """

    api_key = api_key.strip()
    if not api_key.startswith(("ak_", "app_")):
        raise ValueError("中国移动新消息 API Key 格式不正确")

    try:
        async with websockets.connect(
            SERVER_URL,
            additional_headers={"X-API-Key": api_key},
            proxy=proxy,
            open_timeout=OPEN_TIMEOUT_SECONDS,
            close_timeout=CLOSE_TIMEOUT_SECONDS,
            ping_interval=None,
        ) as connection:
            await _authenticate(connection, api_key)
            message_ids = []
            for chunk in split_text(content, TEXT_CHUNK_LIMIT):
                message_id = f"automas_{secrets.token_hex(12)}"
                await connection.send(
                    json.dumps(
                        {
                            "type": "send",
                            "apiKey": api_key,
                            "to": api_key,
                            "content": chunk,
                            "messageId": message_id,
                        },
                        ensure_ascii=False,
                    )
                )
                message_ids.append(message_id)
    except CMCCNewMsgError:
        raise
    except Exception as exc:
        raise CMCCNewMsgError(
            f"连接中国移动新消息服务失败: {type(exc).__name__}"
        ) from exc

    return tuple(message_ids)
