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

"""微信 Claw/iLink 的扫码登录、会话维护和出站消息服务。

用户只参与二维码登录。Bot Token、账号/用户 ID 和 Context Token 都是协议层状态，
由本模块取得并保存，不作为设置页字段暴露给用户。
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
UPDATE_REQUEST_TIMEOUT_SECONDS = 45
UPDATE_RETRY_DELAY_SECONDS = 5
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
    context_token: str = ""


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
    context_ready: bool = False


@dataclass(frozen=True)
class WeixinStatus:
    """不包含任何凭据的绑定状态。"""

    enabled: bool
    connected: bool
    state: str
    context_ready: bool
    message: str


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
        self._config_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._updates_task: asyncio.Task[None] | None = None
        self._updates_stop = asyncio.Event()
        self._updates_buf = ""
        self._hooks_bound = False
        self._runtime_credentials: _RuntimeCredentials | None = None
        self._secret_storage_available: bool | None = None

    def bind_config_hooks(self) -> None:
        """绑定通知开关变化，使扫码后或运行期启用都能启动收消息循环。"""

        if self._hooks_bound:
            return
        Config.bind("Notify", "IfOpenClawWeixin", self._on_enabled_changed)
        self._hooks_bound = True

    async def start(self) -> None:
        """在后端启动时恢复已绑定账号的上下文轮询。"""

        self.bind_config_hooks()
        if self._enabled() and self._has_token():
            self._start_updates_task()

    async def stop(self) -> None:
        """停止后台轮询。"""

        await self._stop_updates_task()

    async def _on_enabled_changed(self, enabled: Any) -> None:
        if bool(enabled) and self._has_token():
            self._start_updates_task()
        else:
            await self._stop_updates_task()

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

    def _context_token(self) -> str:
        if self._runtime_credentials is not None:
            return self._runtime_credentials.context_token
        return str(self._config_value("OpenClawWeixinContextToken") or "").strip()

    def _has_token(self) -> bool:
        token, _, _ = self._credentials()
        return bool(token)

    def status(self) -> WeixinStatus:
        """返回绑定状态，不回传 Token、用户 ID 或上下文内容。"""

        token, user_id, _ = self._credentials()
        account_id = self._account_id()
        enabled = self._enabled()
        # 只有能直接发送消息的凭据才算已绑定；仅有 Bot Token/账号 ID 时，
        # send() 仍会因为缺少收件人而失败，不能让前端显示为已绑定。
        connected = bool(token and user_id)
        context_ready = bool(token and user_id and self._context_token())
        if not connected:
            state = "disconnected"
            message = (
                "微信绑定信息不完整，请重新扫码绑定"
                if token or account_id or user_id
                else "请扫码绑定微信"
            )
        else:
            # 主动通知允许在没有上下文令牌时发送；上下文令牌只用于复用会话，
            # 由后台收到消息后自动缓存，不应变成用户必须填写的配置项。
            state = "connected"
            message = "微信已绑定，通知可以发送"
        return WeixinStatus(
            enabled=enabled,
            connected=connected,
            state=state,
            context_ready=context_ready,
            message=message,
        )

    async def start_login(self) -> QrStartResult:
        """获取二维码并创建一次短生命周期登录会话。"""

        async with self._session_lock:
            # 单账号只保留最后一次二维码，避免重复点击累积可用登录会话。
            self._sessions.clear()
            old_token, old_user_id, _ = self._credentials()
            # 已绑定时点击“重新绑定”应真正进入新的扫码流程；仅在旧配置不完整
            # 时携带旧 Token，让服务端仍可识别历史绑定并返回 binded_redirect。
            local_token_list = (
                []
                if old_token and (self._account_id() or old_user_id)
                else ([old_token] if old_token else [])
            )
            body = {"local_token_list": local_token_list}
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
        """轮询二维码状态，确认后自动保存账号凭据。"""

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

            params = {"qrcode": session.qrcode}
            if verify_code and verify_code.strip():
                params["verify_code"] = verify_code.strip()
            endpoint = f"{session.poll_base_url}/ilink/bot/get_qrcode_status?{urlencode(params)}"
            try:
                response = await self._request_json(
                    "GET",
                    endpoint,
                    body=None,
                    token=None,
                    timeout=QR_STATUS_TIMEOUT_SECONDS,
                )
            except RuntimeError as exc:
                return QrCheckResult(
                    session_id=session_id,
                    state="waiting",
                    message=str(exc),
                )

            state = str(response.get("status") or "").strip().lower()
            if state in {"wait", "scaned"}:
                session.state = "scanned" if state == "scaned" else "waiting"
                return QrCheckResult(
                    session_id=session_id,
                    state=session.state,
                    message=(
                        "已扫码，正在确认登录"
                        if session.state == "scanned"
                        else "请使用微信扫描二维码"
                    ),
                )
            if state == "need_verifycode":
                session.state = "need_verify_code"
                return QrCheckResult(
                    session_id=session_id,
                    state="need_verify_code",
                    message="微信要求输入配对码，请填写手机上显示的数字",
                )
            if state == "verify_code_blocked":
                self._sessions.pop(session_id, None)
                return QrCheckResult(
                    session_id=session_id,
                    state="error",
                    message="配对码错误次数过多，请重新获取二维码",
                )
            if state == "scaned_but_redirect":
                redirect_host = str(response.get("redirect_host") or "").strip()
                if redirect_host:
                    session.poll_base_url = _safe_base_url(f"https://{redirect_host}")
                session.state = "scanned"
                return QrCheckResult(
                    session_id=session_id,
                    state="scanned",
                    message="已扫码，正在切换登录服务并确认",
                )
            if state == "expired":
                self._sessions.pop(session_id, None)
                return QrCheckResult(
                    session_id=session_id,
                    state="expired",
                    message="二维码已过期，请重新生成",
                )
            if state == "binded_redirect":
                if self._has_token():
                    self._sessions.pop(session_id, None)
                    if self._enabled():
                        self._start_updates_task()
                    return QrCheckResult(
                        session_id=session_id,
                        state="connected",
                        connected=True,
                        context_ready=self.status().context_ready,
                        message="微信已绑定，无需重复登录",
                    )
                self._sessions.pop(session_id, None)
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
                    self._sessions.pop(session_id, None)
                    return QrCheckResult(
                        session_id=session_id,
                        state="error",
                        message="登录确认响应缺少账号或收件人信息，请重新扫码",
                    )
                await self._save_credentials(
                    token=bot_token,
                    account_id=account_id,
                    user_id=user_id,
                    base_url=response.get("baseurl"),
                )
                self._sessions.pop(session_id, None)
                if self._enabled():
                    self._start_updates_task()
                return QrCheckResult(
                    session_id=session_id,
                    state="connected",
                    connected=True,
                    context_ready=self.status().context_ready,
                    message="微信扫码绑定成功",
                )

            return QrCheckResult(
                session_id=session_id,
                state="error",
                message=f"微信登录返回未知状态: {state or 'empty'}",
            )

    async def unbind(self) -> None:
        """解除绑定并清理所有协议层状态。"""

        await self._clear_binding_state(stop_updates=True)

    async def _clear_binding_state(self, *, stop_updates: bool) -> None:
        """清理二维码、凭据和配置中的绑定信息。"""

        if stop_updates:
            await self._stop_updates_task()
        async with self._session_lock:
            self._sessions.clear()
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
                    "OpenClawWeixinContextToken": "",
                }
            )
        # 会话轮询在自身检测到失效时会走这里；先摘掉任务引用，避免
        # IfOpenClawWeixin 的异步配置钩子尝试等待当前任务自身。
        if self._updates_task is asyncio.current_task():
            self._updates_task = None
        async with self._config_lock:
            await Config.update({"Notify": config_values})
        self._updates_buf = ""

    async def send(self, title: str, content: str) -> None:
        """发送通知正文，必要时自动拆分长文本。"""

        async with self._send_lock:
            token, user_id, base_url = self._credentials()
            if not token or not user_id:
                await self._invalidate_binding(
                    stop_updates=True,
                    reason="微信绑定信息不完整",
                )
                raise ValueError("微信绑定信息不完整，请重新扫码绑定")
            if self._enabled():
                self._start_updates_task()

            context_token = self._context_token()
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
                if context_token:
                    message["context_token"] = context_token
                result = await self._request_json(
                    "POST",
                    f"{base_url}/ilink/bot/sendmessage",
                    body={"msg": message, "base_info": _base_info()},
                    token=token,
                    timeout=QR_REQUEST_TIMEOUT_SECONDS,
                )
                error_code = _error_code(result)
                if error_code == -2 and context_token:
                    # iLink 的主动发送可以不带 context_token。上下文过期时先
                    # 清理旧令牌并自动重试一次，避免把协议维护工作推给用户。
                    await self._clear_context_token()
                    context_token = ""
                    message.pop("context_token", None)
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
                            stop_updates=True,
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

        if not token.strip() or not account_id.strip() or not user_id.strip():
            raise ValueError("微信登录确认响应缺少账号或收件人信息")

        normalized = _RuntimeCredentials(
            token=token.strip(),
            account_id=account_id.strip(),
            user_id=user_id.strip(),
            base_url=_safe_base_url(base_url),
        )

        if not self._can_persist_secrets():
            # 非 Windows 不把 Bot Token/Context Token 降级写入明文配置；
            # 公开的开关、账号和网关地址仍同步保存，方便当前 UI 正常工作。
            self._runtime_credentials = normalized
            async with self._config_lock:
                await Config.update(
                    {
                        "Notify": {
                            "IfOpenClawWeixin": True,
                            "OpenClawWeixinAccountId": normalized.account_id,
                            "OpenClawWeixinTargetUserId": normalized.user_id,
                            "OpenClawWeixinServerAddress": normalized.base_url,
                        }
                    }
                )
            self._updates_buf = ""
            logger.warning(
                "当前平台不支持 Windows DPAPI，微信凭据仅保存在本次运行内；"
                "应用重启后需要重新扫码"
            )
            return

        async with self._config_lock:
            await Config.update(
                {
                    "Notify": {
                        "IfOpenClawWeixin": True,
                        "OpenClawWeixinBotToken": normalized.token,
                        "OpenClawWeixinAccountId": normalized.account_id,
                        "OpenClawWeixinTargetUserId": normalized.user_id,
                        "OpenClawWeixinContextToken": "",
                        "OpenClawWeixinServerAddress": normalized.base_url,
                    }
                }
            )
        self._runtime_credentials = None
        self._updates_buf = ""

    async def _invalidate_binding(
        self, *, stop_updates: bool, reason: str
    ) -> None:
        """清理已失效的绑定，让状态接口与实际可发送能力一致。"""

        try:
            await self._clear_binding_state(stop_updates=stop_updates)
        except Exception as exc:
            logger.warning(f"{reason}，清理本地绑定状态失败: {exc}")
        else:
            logger.warning(f"{reason}，已清理微信绑定状态")

    async def _clear_context_token(self) -> None:
        if self._runtime_credentials is not None:
            self._runtime_credentials.context_token = ""
            return
        async with self._config_lock:
            try:
                await Config.set("Notify", "OpenClawWeixinContextToken", "")
            except Exception as exc:
                if not platform_secret.is_secret_storage_error(exc):
                    raise

    def _start_updates_task(self) -> None:
        if not self._has_token():
            return
        if self._updates_task is not None and not self._updates_task.done():
            return
        self._updates_stop = asyncio.Event()
        self._updates_task = asyncio.create_task(
            self._run_updates(), name="openclaw-weixin-updates"
        )

    async def _stop_updates_task(self) -> None:
        task = self._updates_task
        self._updates_task = None
        if task is None or task.done():
            return
        self._updates_stop.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _run_updates(self) -> None:
        """长轮询消息，只提取上下文令牌，不介入 AUTO-MAS 对话。"""

        while not self._updates_stop.is_set():
            token, target_user_id, base_url = self._credentials()
            if not token:
                return
            try:
                result = await self._request_json(
                    "POST",
                    f"{base_url}/ilink/bot/getupdates",
                    body={
                        "get_updates_buf": self._updates_buf,
                        "base_info": _base_info(),
                    },
                    token=token,
                    timeout=UPDATE_REQUEST_TIMEOUT_SECONDS,
                )
                error_code = _error_code(result)
                if error_code == -14:
                    self._updates_buf = ""
                    await self._clear_context_token()
                    await self._invalidate_binding(
                        stop_updates=False,
                        reason="微信 iLink 会话已过期",
                    )
                    return
                elif error_code not in (None, 0):
                    raise RuntimeError(
                        f"微信消息轮询失败（ret={error_code}）：{result.get('errmsg') or '未知错误'}"
                    )
                new_buf = result.get("get_updates_buf")
                if isinstance(new_buf, str):
                    self._updates_buf = new_buf
                for message in result.get("msgs") or []:
                    if isinstance(message, dict):
                        await self._capture_context(message, target_user_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(f"微信消息轮询失败，将稍后重试: {exc}")
                await self._sleep_or_stop(UPDATE_RETRY_DELAY_SECONDS)

    async def _capture_context(
        self, message: dict[str, Any], target_user_id: str
    ) -> None:
        context_token = str(message.get("context_token") or "").strip()
        from_user_id = str(message.get("from_user_id") or "").strip()
        message_type = _response_code(message.get("message_type"))
        if not context_token or not from_user_id:
            return
        # 只从用户入站消息获取上下文，避免机器人自己的回执覆盖目标会话。
        if message_type is not None and message_type != 1:
            return
        if target_user_id and from_user_id and from_user_id != target_user_id:
            return
        await self._config_lock.acquire()
        try:
            current_context = self._context_token()
            if current_context != context_token:
                if self._runtime_credentials is not None:
                    self._runtime_credentials.context_token = context_token
                else:
                    try:
                        await Config.set(
                            "Notify", "OpenClawWeixinContextToken", context_token
                        )
                    except Exception as exc:
                        if not platform_secret.is_secret_storage_error(exc):
                            raise
            if not target_user_id and from_user_id:
                if self._runtime_credentials is not None:
                    self._runtime_credentials.user_id = from_user_id
                else:
                    await Config.set(
                        "Notify", "OpenClawWeixinTargetUserId", from_user_id
                    )
        finally:
            self._config_lock.release()

    async def _sleep_or_stop(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._updates_stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

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
            raise RuntimeError(
                f"微信 iLink HTTP 请求失败（状态码 {exc.response.status_code}）"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError("微信 iLink 网络请求失败") from exc
        except ValueError as exc:
            raise RuntimeError("微信 iLink 响应不是合法 JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("微信 iLink 响应格式无效")
        return payload


openclaw_weixin_manager = OpenClawWeixinManager()
