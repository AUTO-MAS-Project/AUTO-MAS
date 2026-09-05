#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""微信 Claw/iLink 的扫码登录和出站消息服务。

用户只参与二维码登录。Bot Token、账号/用户 ID 都是协议层状态，
由本模块取得并保存，不作为设置页字段暴露给用户。

通知通道只在扫码或发送通知时请求 iLink，不在后台保持消息长轮询；
通知发送不需要会话上下文。
"""

from __future__ import annotations

import asyncio
import base64
import secrets
import uuid
from dataclasses import dataclass
from time import monotonic
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx

from app.utils import LazyProxy, get_logger
from app.utils.platform import secret as platform_secret

Config = LazyProxy("app.core", "Config")
logger = get_logger("微信Claw")

DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
DEFAULT_BOT_TYPE = "3"
CLIENT_VERSION = "132104"  # iLink 0x00MMNNPP, compatible with 2.4.8.
QR_SESSION_TTL_SECONDS = 5 * 60
QR_REQUEST_TIMEOUT_SECONDS = 15
QR_STATUS_TIMEOUT_SECONDS = 35
TEXT_CHUNK_LIMIT = 1800


@dataclass
class _QrSession:
    """内存中的一次二维码登录会话。"""

    session_id: str
    qrcode: str
    qr_url: str
    created_at: float
    poll_base_url: str = DEFAULT_BASE_URL
    state: str = "waiting"

    @property
    def expired(self) -> bool:
        return monotonic() - self.created_at >= QR_SESSION_TTL_SECONDS


@dataclass
class _RuntimeCredentials:
    """非 Windows 平台的进程内凭据缓存。

    AUTO-MAS 现有配置的密文实现依赖 Windows DPAPI。微信扫码本身不应因为
    开发环境运行在 macOS/Linux 而失败，因此这些平台只在当前进程保留凭据，
    不把 Token 降级写入明文配置文件。
    """

    token: str
    account_id: str
    user_id: str
    base_url: str


@dataclass(frozen=True)
class QrStartResult:
    """创建二维码后的公开结果。"""

    session_id: str
    qr_url: str


@dataclass(frozen=True)
class QrCheckResult:
    """二维码轮询后的公开结果。"""

    session_id: str
    state: str
    message: str
    connected: bool = False


@dataclass(frozen=True)
class WeixinStatus:
    """不包含任何凭据的绑定状态。"""

    enabled: bool
    connected: bool
    state: str
    message: str


class RemoteHTTPError(RuntimeError):
    """远端返回明确 HTTP 状态码的请求错误。"""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


def split_text(text: str, limit: int = TEXT_CHUNK_LIMIT) -> list[str]:
    """将文本按字符上限拆分，并尽量在换行处断开。

    iLink 的网关对过长文本可能返回业务失败；通知正文不能依赖模型自行分段，
    因此这里在协议适配层做确定性拆分。
    """

    if limit < 1:
        raise ValueError("文本分段长度必须大于 0")
    if not text:
        return [""]
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        boundary = remaining.rfind("\n", 0, limit + 1)
        if boundary <= 0:
            boundary = limit
        chunks.append(remaining[:boundary].rstrip("\n"))
        remaining = remaining[boundary:]
        remaining = remaining.lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


def _is_valid_https_url(value: str) -> bool:
    """只接受 iLink 返回的 HTTPS 网关地址。"""

    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme.lower() == "https" and bool(parsed.netloc)


def _safe_base_url(value: Any) -> str:
    """校验服务端返回的 baseurl，异常时回退官方网关。"""

    candidate = str(value or "").strip().rstrip("/")
    return candidate if _is_valid_https_url(candidate) else DEFAULT_BASE_URL


def _client_kwargs(timeout: float) -> dict[str, Any]:
    """生成统一 HTTP 客户端参数，避免环境代理劫持二维码/凭据请求。"""

    proxy = Config.proxy
    kwargs: dict[str, Any] = {"timeout": timeout, "trust_env": False}
    if proxy is not None:
        kwargs["proxy"] = proxy
    return kwargs


def _base_info() -> dict[str, str]:
    """构造符合上游约定的客户端标识。"""

    version = str(getattr(Config, "VERSION", "unknown")).lstrip("v")
    return {
        "channel_version": version,
        "bot_agent": f"AUTO-MAS/{version}",
    }


def _headers(token: str | None = None) -> dict[str, str]:
    """构造 iLink 公共请求头。"""

    uint32 = secrets.randbits(32)
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "X-WECHAT-UIN": base64.b64encode(str(uint32).encode("ascii")).decode("ascii"),
        "iLink-App-Id": "bot",
        "iLink-App-ClientVersion": CLIENT_VERSION,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _response_code(value: Any) -> int | None:
    """将网关返回的数字错误码统一为 int。"""

    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _error_code(response: dict[str, Any]) -> int | None:
    """兼容 ret/errcode 两种 iLink 错误码字段。"""

    ret = _response_code(response.get("ret"))
    if ret not in (None, 0):
        return ret
    return _response_code(response.get("errcode"))


class OpenClawWeixinManager:
    """单账号微信 Claw 通道管理器。"""

    def __init__(self) -> None:
        self._sessions: dict[str, _QrSession] = {}
        self._session_lock = asyncio.Lock()
        self._session_generation = 0
        self._config_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._credential_lock = asyncio.Lock()
        self._runtime_credentials: _RuntimeCredentials | None = None
        self._secret_storage_available: bool | None = None

    async def start(self) -> None:
        """初始化管理器；微信通知不保持后台连接，所有请求按需发起。"""

        return

    async def stop(self) -> None:
        """清理临时二维码会话；不会请求或等待远端连接。"""

        async with self._session_lock:
            self._sessions.clear()
            self._session_generation += 1

    def _enabled(self) -> bool:
        try:
            return bool(Config.get("Notify", "IfOpenClawWeixin"))
        except (AttributeError, RuntimeError):
            return False

    def _config_value(self, name: str, default: Any = "") -> Any:
        """读取配置；密文能力不可用时按未绑定处理。"""

        try:
            return Config.get("Notify", name)
        except Exception as exc:
            if platform_secret.is_secret_storage_error(exc):
                return default
            raise

    def _can_persist_secrets(self) -> bool:
        """确认是否可以沿用配置层的 DPAPI 密文存储。"""

        if self._secret_storage_available is not None:
            return self._secret_storage_available
        self._secret_storage_available = platform_secret.supports_secret_storage()
        return self._secret_storage_available

    def _credentials(self) -> tuple[str, str, str]:
        if self._runtime_credentials is not None:
            runtime = self._runtime_credentials
            return runtime.token, runtime.user_id, runtime.base_url

        token = str(self._config_value("OpenClawWeixinBotToken") or "").strip()
        user_id = str(self._config_value("OpenClawWeixinTargetUserId") or "").strip()
        base_url = _safe_base_url(self._config_value("OpenClawWeixinServerAddress"))
        return token, user_id, base_url

    def _account_id(self) -> str:
        if self._runtime_credentials is not None:
            return self._runtime_credentials.account_id
        return str(self._config_value("OpenClawWeixinAccountId") or "").strip()

    def status(self) -> WeixinStatus:
        """返回绑定状态，不回传 Token、用户 ID 或上下文内容。"""

        token, user_id, _ = self._credentials()
        account_id = self._account_id()
        enabled = self._enabled()
        # 只有能直接发送消息的凭据才算已绑定；仅有 Bot Token/账号 ID 时，
        # send() 仍会因为缺少收件人而失败，不能让前端显示为已绑定。
        connected = bool(token and user_id)
        if not connected:
            state = "disconnected"
            message = (
                "微信绑定信息不完整，请重新扫码绑定"
                if token or account_id or user_id
                else "请扫码绑定微信"
            )
        else:
            # 主动通知只依赖扫码返回的凭据，不要求额外的会话上下文。
            state = "connected"
            message = "微信已绑定，通知可以发送"
        return WeixinStatus(
            enabled=enabled,
            connected=connected,
            state=state,
            message=message,
        )

    async def start_login(self) -> QrStartResult:
        """获取二维码并创建一次短生命周期登录会话。"""

        async with self._session_lock:
            # 单账号只保留最后一次二维码，避免重复点击累积可用登录会话。
            self._sessions.clear()
            self._session_generation += 1
            generation = self._session_generation
            # 每次扫码都要求服务端返回完整凭据；本地残缺 Token 不参与新会话。
            body = {"local_token_list": []}

        # 二维码接口可能等待十几秒；网络请求必须在会话锁外执行，
        # 否则关闭二维码、重新绑定和解绑都会被阻塞。
        response = await self._request_json(
            "POST",
            f"{DEFAULT_BASE_URL}/ilink/bot/get_bot_qrcode?bot_type={DEFAULT_BOT_TYPE}",
            body=body,
            token=None,
            timeout=QR_REQUEST_TIMEOUT_SECONDS,
        )
        qrcode = str(response.get("qrcode") or "").strip()
        qr_url = str(response.get("qrcode_img_content") or "").strip()
        if not qrcode or not qr_url:
            raise RuntimeError("微信二维码响应缺少登录信息")
        session_id = uuid.uuid4().hex
        async with self._session_lock:
            if generation != self._session_generation:
                raise RuntimeError("微信二维码登录会话已关闭，请重新生成")
            self._sessions[session_id] = _QrSession(
                session_id=session_id,
                qrcode=qrcode,
                qr_url=qr_url,
                created_at=monotonic(),
            )
        return QrStartResult(session_id=session_id, qr_url=qr_url)

    async def check_login(
        self, session_id: str, verify_code: str | None = None
    ) -> QrCheckResult:
        """查询二维码状态，确认后自动保存账号凭据。"""

        async with self._session_lock:
            session = self._sessions.get(session_id)
            if session is None:
                return QrCheckResult(
                    session_id=session_id,
                    state="error",
                    message="二维码登录会话不存在，请重新生成",
                )
            if session.expired:
                self._sessions.pop(session_id, None)
                return QrCheckResult(
                    session_id=session_id,
                    state="expired",
                    message="二维码已过期，请重新生成",
                )
            generation = self._session_generation
            qrcode = session.qrcode
            poll_base_url = session.poll_base_url

        params = {"qrcode": qrcode}
        if verify_code and verify_code.strip():
            params["verify_code"] = verify_code.strip()
        endpoint = f"{poll_base_url}/ilink/bot/get_qrcode_status?{urlencode(params)}"
        try:
            response = await self._request_json(
                "GET",
                endpoint,
                body=None,
                token=None,
                timeout=QR_STATUS_TIMEOUT_SECONDS,
            )
        except RemoteHTTPError as exc:
            if 500 <= exc.status_code < 600:
                return QrCheckResult(
                    session_id=session_id,
                    state="waiting",
                    message=str(exc),
                )
            return QrCheckResult(
                session_id=session_id,
                state="error",
                message=str(exc),
            )
        except RuntimeError as exc:
            return QrCheckResult(
                session_id=session_id,
                state="waiting",
                message=str(exc),
            )

        async with self._session_lock:
            if (
                generation != self._session_generation
                or self._sessions.get(session_id) is not session
            ):
                return QrCheckResult(
                    session_id=session_id,
                    state="error",
                    message="二维码登录会话已关闭，请重新生成",
                )

        state = str(response.get("status") or "").strip().lower()
        if state in {"wait", "scaned"}:
            current_state = "scanned" if state == "scaned" else "waiting"
            async with self._session_lock:
                if (
                    generation != self._session_generation
                    or self._sessions.get(session_id) is not session
                ):
                    return QrCheckResult(
                        session_id=session_id,
                        state="error",
                        message="二维码登录会话已关闭，请重新生成",
                    )
                session.state = current_state
            return QrCheckResult(
                session_id=session_id,
                state=current_state,
                message=(
                    "已扫码，正在确认登录"
                    if current_state == "scanned"
                    else "请使用微信扫描二维码"
                ),
            )
        if state == "need_verifycode":
            async with self._session_lock:
                if (
                    generation != self._session_generation
                    or self._sessions.get(session_id) is not session
                ):
                    return QrCheckResult(
                        session_id=session_id,
                        state="error",
                        message="二维码登录会话已关闭，请重新生成",
                    )
                session.state = "need_verify_code"
            return QrCheckResult(
                session_id=session_id,
                state="need_verify_code",
                message="微信要求输入配对码，请填写手机上显示的数字",
            )
        if state == "verify_code_blocked":
            async with self._session_lock:
                if (
                    generation == self._session_generation
                    and self._sessions.get(session_id) is session
                ):
                    self._sessions.pop(session_id, None)
            return QrCheckResult(
                session_id=session_id,
                state="error",
                message="配对码错误次数过多，请重新获取二维码",
            )
        if state == "scaned_but_redirect":
            redirect_host = str(response.get("redirect_host") or "").strip()
            async with self._session_lock:
                if (
                    generation != self._session_generation
                    or self._sessions.get(session_id) is not session
                ):
                    return QrCheckResult(
                        session_id=session_id,
                        state="error",
                        message="二维码登录会话已关闭，请重新生成",
                    )
                if redirect_host:
                    session.poll_base_url = _safe_base_url(f"https://{redirect_host}")
                session.state = "scanned"
            return QrCheckResult(
                session_id=session_id,
                state="scanned",
                message="已扫码，正在切换登录服务并确认",
            )
        if state == "expired":
            async with self._session_lock:
                if (
                    generation == self._session_generation
                    and self._sessions.get(session_id) is session
                ):
                    self._sessions.pop(session_id, None)
            return QrCheckResult(
                session_id=session_id,
                state="expired",
                message="二维码已过期，请重新生成",
            )
        if state == "binded_redirect":
            async with self._session_lock:
                if (
                    generation != self._session_generation
                    or self._sessions.get(session_id) is not session
                ):
                    return QrCheckResult(
                        session_id=session_id,
                        state="error",
                        message="二维码登录会话已关闭，请重新生成",
                    )
                self._sessions.pop(session_id, None)
            if self.status().connected:
                return QrCheckResult(
                    session_id=session_id,
                    state="connected",
                    connected=True,
                    message="微信已绑定，无需重复登录",
                )
            return QrCheckResult(
                session_id=session_id,
                state="error",
                message="微信账号已绑定，但本地没有可用凭据，请重新扫码",
            )
        if state == "confirmed":
            bot_token = str(response.get("bot_token") or "").strip()
            account_id = str(response.get("ilink_bot_id") or "").strip()
            user_id = str(response.get("ilink_user_id") or "").strip()
            if not bot_token or not account_id or not user_id:
                async with self._session_lock:
                    if (
                        generation == self._session_generation
                        and self._sessions.get(session_id) is session
                    ):
                        self._sessions.pop(session_id, None)
                return QrCheckResult(
                    session_id=session_id,
                    state="error",
                    message="登录确认响应缺少账号或收件人信息，请重新扫码",
                )
            try:
                async with self._send_lock, self._credential_lock:
                    async with self._session_lock:
                        if (
                            generation != self._session_generation
                            or self._sessions.get(session_id) is not session
                        ):
                            return QrCheckResult(
                                session_id=session_id,
                                state="error",
                                message="二维码登录会话已关闭，请重新生成",
                            )
                        self._sessions.pop(session_id, None)
                    await self._save_credentials_locked(
                        token=bot_token,
                        account_id=account_id,
                        user_id=user_id,
                        base_url=response.get("baseurl"),
                    )
            except (ValueError, RuntimeError) as exc:
                return QrCheckResult(
                    session_id=session_id,
                    state="error",
                    message=f"微信登录凭据处理失败：{exc}",
                )
            async with self._session_lock:
                if generation != self._session_generation:
                    return QrCheckResult(
                        session_id=session_id,
                        state="error",
                        message="二维码登录会话已关闭，请重新生成",
                    )
            return QrCheckResult(
                session_id=session_id,
                state="connected",
                connected=True,
                message="微信扫码绑定成功",
            )

        return QrCheckResult(
            session_id=session_id,
            state="error",
            message=f"微信登录返回未知状态: {state or 'empty'}",
        )

    async def unbind(self) -> None:
        """解除绑定并清理所有协议层状态。"""

        # 先让二维码请求失效，不等待正在发送的消息或配置写入。
        await self._invalidate_qr_sessions()
        async with self._send_lock:
            await self._clear_binding_credentials()

    async def _clear_binding_state(self) -> None:
        """清理二维码、凭据和配置中的绑定信息。"""

        await self._invalidate_qr_sessions()
        await self._clear_binding_credentials()

    async def _invalidate_qr_sessions(self) -> None:
        """使正在进行的二维码请求失效，且不等待任何网络操作。"""

        async with self._session_lock:
            self._sessions.clear()
            self._session_generation += 1

    async def _clear_binding_credentials(self) -> None:
        """清理凭据及其配置；调用方不应持有会话锁。"""

        async with self._credential_lock:
            self._runtime_credentials = None
            config_values = {
                "IfOpenClawWeixin": False,
                "OpenClawWeixinAccountId": "",
                "OpenClawWeixinTargetUserId": "",
                "OpenClawWeixinServerAddress": DEFAULT_BASE_URL,
            }
            if self._can_persist_secrets():
                config_values.update(
                    {
                        "OpenClawWeixinBotToken": "",
                    }
                )
            async with self._config_lock:
                await Config.update({"Notify": config_values})

    async def send(self, title: str, content: str) -> None:
        """发送通知正文，必要时自动拆分长文本。"""

        async with self._send_lock:
            token, user_id, base_url = self._credentials()
            if not token or not user_id:
                await self._invalidate_binding(
                    reason="微信绑定信息不完整",
                )
                raise ValueError("微信绑定信息不完整，请重新扫码绑定")

            # 多段消息会附带序号前缀，预留前缀空间，确保最终单条消息仍不超过网关上限。
            chunks = split_text(content, max(1, TEXT_CHUNK_LIMIT - 16))
            for index, chunk in enumerate(chunks, start=1):
                if len(chunks) > 1:
                    chunk = f"[{index}/{len(chunks)}]\n{chunk}"
                message = {
                    "from_user_id": "",
                    "to_user_id": user_id,
                    "client_id": f"auto-mas-{uuid.uuid4().hex}",
                    "message_type": 2,
                    "message_state": 2,
                    "item_list": [{"type": 1, "text_item": {"text": chunk}}],
                }
                result = await self._request_json(
                    "POST",
                    f"{base_url}/ilink/bot/sendmessage",
                    body={"msg": message, "base_info": _base_info()},
                    token=token,
                    timeout=QR_REQUEST_TIMEOUT_SECONDS,
                )
                error_code = _error_code(result)
                if error_code not in (None, 0):
                    if error_code in {-2, -14}:
                        await self._invalidate_binding(
                            reason="微信登录状态已失效",
                        )
                        raise RuntimeError("微信登录状态已失效，请重新扫码绑定")
                    errmsg = result.get("errmsg") or "未知错误"
                    raise RuntimeError(
                        f"微信通知发送失败（ret={error_code}）：{errmsg}"
                    )
            logger.success(f"微信Claw通知推送成功: {title}")

    async def _save_credentials(
        self,
        *,
        token: str,
        account_id: str,
        user_id: str,
        base_url: Any,
    ) -> None:
        """将扫码结果保存到内部配置项，不进入公开设置 schema。"""

        async with self._send_lock, self._credential_lock:
            await self._save_credentials_locked(
                token=token,
                account_id=account_id,
                user_id=user_id,
                base_url=base_url,
            )

    async def _save_credentials_locked(
        self,
        *,
        token: str,
        account_id: str,
        user_id: str,
        base_url: Any,
    ) -> None:
        """在发送与凭据锁已取得时保存扫码返回的凭据。"""

        if not token.strip() or not account_id.strip() or not user_id.strip():
            raise ValueError("微信登录确认响应缺少账号或收件人信息")

        normalized = _RuntimeCredentials(
            token=token.strip(),
            account_id=account_id.strip(),
            user_id=user_id.strip(),
            base_url=_safe_base_url(base_url),
        )

        if not self._can_persist_secrets():
            # 非 Windows 不把 Bot Token 降级写入明文配置；
            # 公开的开关、账号和网关地址仍同步保存，方便当前 UI 正常工作。
            self._runtime_credentials = normalized
            async with self._config_lock:
                await Config.update(
                    {
                        "Notify": {
                            "OpenClawWeixinAccountId": normalized.account_id,
                            "OpenClawWeixinTargetUserId": normalized.user_id,
                            "OpenClawWeixinServerAddress": normalized.base_url,
                        }
                    }
                )
            logger.warning(
                "当前平台不支持 Windows DPAPI，微信凭据仅保存在本次运行内；"
                "应用重启后需要重新扫码"
            )
            return

        async with self._config_lock:
            await Config.update(
                {
                    "Notify": {
                        "OpenClawWeixinBotToken": normalized.token,
                        "OpenClawWeixinAccountId": normalized.account_id,
                        "OpenClawWeixinTargetUserId": normalized.user_id,
                        "OpenClawWeixinServerAddress": normalized.base_url,
                    }
                }
            )
        self._runtime_credentials = None

    async def _invalidate_binding(self, *, reason: str) -> None:
        """清理已失效的绑定，让状态接口与实际可发送能力一致。"""

        try:
            await self._clear_binding_state()
        except Exception as exc:
            logger.warning(f"{reason}，清理本地绑定状态失败: {exc}")
        else:
            logger.warning(f"{reason}，已清理微信绑定状态")

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        body: dict[str, Any] | None,
        token: str | None,
        timeout: float,
    ) -> dict[str, Any]:
        """发起 iLink 请求并统一解析 HTTP/JSON 错误。"""

        try:
            async with httpx.AsyncClient(**_client_kwargs(timeout)) as client:
                response = await client.request(
                    method,
                    url,
                    json=body,
                    headers=_headers(token),
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            # 不把二维码或会话令牌所在的完整 URL 带回前端或写入日志。
            raise RemoteHTTPError(
                exc.response.status_code,
                f"微信 iLink HTTP 请求失败（状态码 {exc.response.status_code}）",
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError("微信 iLink 网络请求失败") from exc
        except ValueError as exc:
            raise RuntimeError("微信 iLink 响应不是合法 JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("微信 iLink 响应格式无效")
        return payload


openclaw_weixin_manager = OpenClawWeixinManager()
