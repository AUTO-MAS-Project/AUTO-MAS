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

"""QQ 官方机器人扫码绑定、Token 管理和 C2C 出站消息服务。

用户只需要扫描 QQ 官方机器人提供的二维码。App ID、客户端密钥和目标用户
OpenID 都由官方扫码流程返回，并由本模块负责保存和换取短期访问令牌；这些
协议凭据不进入公开设置 schema。
"""

from __future__ import annotations

import asyncio
import base64
import secrets
import uuid
from dataclasses import dataclass
from time import monotonic
from typing import Any
from urllib.parse import quote

import httpx

from app.utils import LazyProxy, get_logger
from app.utils.platform import secret as platform_secret

Config = LazyProxy("app.core", "Config")
logger = get_logger("QQ官方机器人")

PORTAL_BASE_URL = "https://q.qq.com"
API_BASE_URL = "https://api.sgroup.qq.com"
TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
QR_CONNECT_URL = "https://q.qq.com/qqbot/openclaw/connect.html"
QR_SESSION_TTL_SECONDS = 5 * 60
QR_REQUEST_TIMEOUT_SECONDS = 15
API_REQUEST_TIMEOUT_SECONDS = 15
TEXT_CHUNK_LIMIT = 3800
USER_AGENT = "AUTO-MAS QQ Official Bot"


@dataclass
class _QrSession:
    """内存中的一次 QQ 官方机器人二维码登录会话。"""

    task_id: str
    aes_key: bytes
    created_at: float

    @property
    def expired(self) -> bool:
        return monotonic() - self.created_at >= QR_SESSION_TTL_SECONDS


@dataclass
class _RuntimeCredentials:
    """无法使用平台密文存储时，仅保留在本次进程内的凭据。"""

    app_id: str
    client_secret: str
    user_openid: str


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
class QQStatus:
    """不包含任何凭据的 QQ 绑定状态。"""

    enabled: bool
    connected: bool
    state: str
    message: str


def split_text(text: str, limit: int = TEXT_CHUNK_LIMIT) -> list[str]:
    """将通知文本按字符上限拆分，并尽量在换行处断开。"""

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
        remaining = remaining[boundary:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


def _as_int(value: Any) -> int | None:
    """把官方接口可能返回的数字字符串统一为整数。"""

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _client_kwargs(timeout: float) -> dict[str, Any]:
    """生成 HTTP 客户端参数，避免环境代理干扰官方接口。"""

    kwargs: dict[str, Any] = {
        "timeout": timeout,
        "trust_env": False,
        "follow_redirects": True,
    }
    proxy = Config.proxy
    if proxy is not None:
        kwargs["proxy"] = proxy
    return kwargs


def _headers(
    *, app_id: str | None = None, access_token: str | None = None
) -> dict[str, str]:
    """构造 QQ 官方接口公共请求头。"""

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    if access_token:
        headers["Authorization"] = f"QQBot {access_token}"
    if app_id:
        headers["X-Union-Appid"] = app_id
    return headers


def _business_code(payload: dict[str, Any]) -> int | None:
    """读取不同 QQ 接口使用的业务错误码字段。"""

    for name in ("code", "retcode", "errcode", "errno"):
        if name in payload:
            code = _as_int(payload.get(name))
            if code is not None:
                return code
    return None


def _business_message(payload: dict[str, Any]) -> str:
    """返回不包含凭据的官方错误描述。"""

    for name in ("message", "msg", "errmsg", "error_description"):
        value = payload.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "未知错误"


def _decrypt_client_secret(encrypted: str, key: bytes) -> str:
    """解密官方扫码返回的 AES-256-GCM 客户端密钥。"""

    if len(key) != 32:
        raise ValueError("QQ 登录会话密钥长度无效")
    try:
        raw = base64.b64decode(encrypted, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("QQ 登录返回的客户端密钥格式无效") from exc
    if len(raw) <= 12 + 16:
        raise ValueError("QQ 登录返回的客户端密钥长度无效")

    # pycryptodome 已是项目的直接依赖；延迟导入可让普通启动不引入密码学模块。
    from Crypto.Cipher import AES

    iv = raw[:12]
    ciphertext = raw[12:-16]
    tag = raw[-16:]
    try:
        cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
        secret = cipher.decrypt_and_verify(ciphertext, tag)
    except (ValueError, TypeError) as exc:
        raise ValueError("QQ 登录返回的客户端密钥无法解密") from exc
    try:
        result = secret.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ValueError("QQ 登录返回的客户端密钥编码无效") from exc
    if not result:
        raise ValueError("QQ 登录返回的客户端密钥为空")
    return result


class OpenClawQQManager:
    """单账号 QQ 官方机器人通知管理器。"""

    def __init__(self) -> None:
        self._sessions: dict[str, _QrSession] = {}
        self._session_lock = asyncio.Lock()
        self._session_generation = 0
        self._config_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._credential_lock = asyncio.Lock()
        self._hooks_bound = False
        self._runtime_credentials: _RuntimeCredentials | None = None
        self._secret_storage_available: bool | None = None
        self._access_token = ""
        self._access_token_expires_at = 0.0

    def bind_config_hooks(self) -> None:
        """绑定通知开关变化，关闭时立即丢弃本地访问令牌。"""

        if self._hooks_bound:
            return
        Config.bind("Notify", "IfOpenClawQQ", self._on_enabled_changed)
        self._hooks_bound = True

    async def start(self) -> None:
        """在后端启动时绑定配置钩子；访问令牌按需获取。"""

        self.bind_config_hooks()

    async def stop(self) -> None:
        """停止服务并清理短期访问令牌和临时二维码。"""

        async with self._session_lock:
            self._sessions.clear()
            self._session_generation += 1
        self._invalidate_access_token()

    async def _on_enabled_changed(self, enabled: Any) -> None:
        if not bool(enabled):
            self._invalidate_access_token()

    def _enabled(self) -> bool:
        try:
            return bool(Config.get("Notify", "IfOpenClawQQ"))
        except (AttributeError, RuntimeError):
            return False

    def _config_value(self, name: str, default: Any = "") -> Any:
        """读取内部配置；平台不支持密文时按未保存处理。"""

        try:
            return Config.get("Notify", name)
        except Exception as exc:
            if platform_secret.is_secret_storage_error(exc):
                return default
            raise

    def _can_persist_secrets(self) -> bool:
        """确认是否可以使用配置层的 Windows DPAPI 密文存储。"""

        if self._secret_storage_available is None:
            self._secret_storage_available = platform_secret.supports_secret_storage()
        return self._secret_storage_available

    def _credentials(self) -> tuple[str, str, str]:
        if self._runtime_credentials is not None:
            runtime = self._runtime_credentials
            return runtime.app_id, runtime.client_secret, runtime.user_openid
        return (
            str(self._config_value("OpenClawQQAppId") or "").strip(),
            str(self._config_value("OpenClawQQClientSecret") or "").strip(),
            str(self._config_value("OpenClawQQTargetOpenId") or "").strip(),
        )

    def status(self) -> QQStatus:
        """返回 QQ 绑定状态，不回传 App ID、Secret 或 OpenID。"""

        app_id, client_secret, user_openid = self._credentials()
        connected = bool(app_id and client_secret and user_openid)
        if connected:
            state = "connected"
            message = "QQ 官方机器人已绑定，通知可以发送"
        else:
            state = "disconnected"
            message = "请扫码绑定 QQ 官方机器人"
        return QQStatus(
            enabled=self._enabled(),
            connected=connected,
            state=state,
            message=message,
        )

    async def start_login(self) -> QrStartResult:
        """创建官方扫码绑定任务并返回二维码链接。"""

        async with self._session_lock:
            self._sessions.clear()
            self._session_generation += 1
            generation = self._session_generation
            aes_key = secrets.token_bytes(32)

        # 二维码接口可能等待十几秒；网络请求必须在会话锁外执行，
        # 否则关闭二维码、重新绑定和解绑都会被阻塞。
        response = await self._request_json(
            "POST",
            f"{PORTAL_BASE_URL}/lite/create_bind_task",
            body={"key": base64.b64encode(aes_key).decode("ascii")},
            headers=_headers(),
            timeout=QR_REQUEST_TIMEOUT_SECONDS,
        )
        if _business_code(response) not in (None, 0):
            raise RuntimeError(f"QQ 二维码创建失败：{_business_message(response)}")
        data = response.get("data")
        task_id = (
            str(data.get("task_id") or "").strip() if isinstance(data, dict) else ""
        )
        if not task_id:
            raise RuntimeError("QQ 二维码响应缺少绑定任务")

        session_id = uuid.uuid4().hex
        qr_url = f"{QR_CONNECT_URL}?task_id={quote(task_id, safe='')}&_wv=2"
        async with self._session_lock:
            if generation != self._session_generation:
                raise RuntimeError("QQ 二维码登录会话已关闭，请重新生成")
            self._sessions[session_id] = _QrSession(
                task_id=task_id,
                aes_key=aes_key,
                created_at=monotonic(),
            )
        return QrStartResult(session_id=session_id, qr_url=qr_url)

    async def check_login(self, session_id: str) -> QrCheckResult:
        """轮询扫码绑定任务，完成后保存官方机器人凭据。"""

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
            task_id = session.task_id
            aes_key = session.aes_key

        # 状态查询同样可能等待网络响应，不能在会话锁内轮询。
        try:
            response = await self._request_json(
                "POST",
                f"{PORTAL_BASE_URL}/lite/poll_bind_result",
                body={"task_id": task_id},
                headers=_headers(),
                timeout=QR_REQUEST_TIMEOUT_SECONDS,
            )
        except RuntimeError as exc:
            # 轮询失败通常是临时网络问题，让前端继续轮询并展示原因。
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

        if _business_code(response) not in (None, 0):
            return QrCheckResult(
                session_id=session_id,
                state="error",
                message=f"查询 QQ 登录状态失败：{_business_message(response)}",
            )
        data = response.get("data")
        data = data if isinstance(data, dict) else {}
        status = _as_int(data.get("status"))
        if status in (None, 0):
            return QrCheckResult(
                session_id=session_id,
                state="waiting",
                message="请使用 QQ 扫描二维码",
            )
        if status == 1:
            return QrCheckResult(
                session_id=session_id,
                state="scanned",
                message="已扫码，正在确认登录",
            )
        if status == 3:
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
        if status != 2:
            return QrCheckResult(
                session_id=session_id,
                state="error",
                message=f"QQ 登录返回未知状态：{status}",
            )

        app_id = str(data.get("bot_appid") or "").strip()
        encrypted_secret = str(data.get("bot_encrypt_secret") or "").strip()
        user_openid = str(data.get("user_openid") or "").strip()
        if not app_id or not encrypted_secret or not user_openid:
            async with self._session_lock:
                if (
                    generation == self._session_generation
                    and self._sessions.get(session_id) is session
                ):
                    self._sessions.pop(session_id, None)
            return QrCheckResult(
                session_id=session_id,
                state="error",
                message="登录确认响应缺少 QQ 机器人凭据，请重新扫码",
            )
        try:
            client_secret = _decrypt_client_secret(encrypted_secret, aes_key)
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
                    app_id=app_id,
                    client_secret=client_secret,
                    user_openid=user_openid,
                )
        except (ValueError, RuntimeError) as exc:
            async with self._session_lock:
                if (
                    generation == self._session_generation
                    and self._sessions.get(session_id) is session
                ):
                    self._sessions.pop(session_id, None)
            return QrCheckResult(
                session_id=session_id,
                state="error",
                message=f"QQ 登录凭据处理失败：{exc}",
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
            message="QQ 官方机器人扫码绑定成功",
        )

    async def unbind(self) -> None:
        """解除绑定并清理本地保存的 QQ 协议状态。"""

        # 先在锁内使所有正在进行的二维码请求失效，再在锁外清理配置。
        async with self._session_lock:
            self._sessions.clear()
            self._session_generation += 1
        async with self._send_lock, self._credential_lock:
            self._runtime_credentials = None
            self._invalidate_access_token()
            values = {
                "IfOpenClawQQ": False,
                "OpenClawQQAppId": "",
                "OpenClawQQTargetOpenId": "",
            }
            if self._can_persist_secrets():
                values["OpenClawQQClientSecret"] = ""
            async with self._config_lock:
                await Config.update({"Notify": values})

    async def send(self, title: str, content: str) -> None:
        """通过官方 C2C 接口发送通知，长文本自动拆分。"""

        async with self._send_lock:
            app_id, client_secret, user_openid = self._credentials()
            if not app_id or not client_secret or not user_openid:
                raise ValueError("请先在通知设置中扫码绑定 QQ 官方机器人")

            chunks = split_text(content, max(1, TEXT_CHUNK_LIMIT - 16))
            for index, chunk in enumerate(chunks, start=1):
                if len(chunks) > 1:
                    chunk = f"[{index}/{len(chunks)}]\n{chunk}"
                body = {"msg_type": 0, "msg_seq": index, "content": chunk}
                await self._send_message_with_token(
                    app_id=app_id,
                    client_secret=client_secret,
                    user_openid=user_openid,
                    body=body,
                )
            logger.success(f"QQ官方机器人通知推送成功: {title}")

    async def _send_message_with_token(
        self,
        *,
        app_id: str,
        client_secret: str,
        user_openid: str,
        body: dict[str, Any],
    ) -> None:
        """发送单段消息，并在访问令牌过期时无感重试一次。"""

        for attempt in range(2):
            access_token = await self._ensure_access_token(app_id, client_secret)
            endpoint = f"{API_BASE_URL}/v2/users/{quote(user_openid, safe='')}/messages"
            try:
                response = await self._request_json(
                    "POST",
                    endpoint,
                    body=body,
                    headers=_headers(app_id=app_id, access_token=access_token),
                    timeout=API_REQUEST_TIMEOUT_SECONDS,
                )
            except RuntimeError as exc:
                if attempt == 0 and _is_token_error(exc):
                    self._invalidate_access_token()
                    continue
                raise
            code = _business_code(response)
            if code not in (None, 0):
                if attempt == 0 and code in (401, 401001, 11200, 11201):
                    self._invalidate_access_token()
                    continue
                raise RuntimeError(f"QQ 通知发送失败：{_business_message(response)}")
            return

    async def _ensure_access_token(self, app_id: str, client_secret: str) -> str:
        """按需换取并缓存官方 access_token。"""

        now = monotonic()
        if self._access_token and self._access_token_expires_at > now + 60:
            return self._access_token

        response = await self._request_json(
            "POST",
            TOKEN_URL,
            body={"appId": app_id, "clientSecret": client_secret},
            headers=_headers(),
            timeout=API_REQUEST_TIMEOUT_SECONDS,
        )
        code = _business_code(response)
        if code not in (None, 0):
            raise RuntimeError(
                f"QQ access_token 获取失败：{_business_message(response)}"
            )
        access_token = str(response.get("access_token") or "").strip()
        if not access_token:
            raise RuntimeError("QQ access_token 响应缺少访问令牌")
        expires_in = _as_int(response.get("expires_in")) or 7200
        self._access_token = access_token
        self._access_token_expires_at = monotonic() + max(60, expires_in)
        return access_token

    def _invalidate_access_token(self) -> None:
        self._access_token = ""
        self._access_token_expires_at = 0.0

    async def _save_credentials(
        self, *, app_id: str, client_secret: str, user_openid: str
    ) -> None:
        """保存扫码返回的凭据，非 Windows 只保留本次运行所需数据。"""

        async with self._send_lock, self._credential_lock:
            await self._save_credentials_locked(
                app_id=app_id,
                client_secret=client_secret,
                user_openid=user_openid,
            )

    async def _save_credentials_locked(
        self, *, app_id: str, client_secret: str, user_openid: str
    ) -> None:
        """在发送与凭据锁已取得时保存扫码返回的凭据。"""

        normalized = _RuntimeCredentials(
            app_id=app_id.strip(),
            client_secret=client_secret.strip(),
            user_openid=user_openid.strip(),
        )
        values = {
            "IfOpenClawQQ": True,
            "OpenClawQQAppId": normalized.app_id,
            "OpenClawQQTargetOpenId": normalized.user_openid,
        }
        async with self._config_lock:
            if self._can_persist_secrets():
                try:
                    await Config.update(
                        {
                            "Notify": {
                                **values,
                                "OpenClawQQClientSecret": normalized.client_secret,
                            }
                        }
                    )
                except Exception as exc:
                    if not platform_secret.is_secret_storage_error(exc):
                        raise
                    self._secret_storage_available = False
            if not self._can_persist_secrets():
                await Config.update({"Notify": values})
                logger.warning(
                    "当前平台不支持 Windows DPAPI，QQ 凭据仅保存在本次运行内；"
                    "应用重启后需要重新扫码"
                )
            self._runtime_credentials = (
                None if self._can_persist_secrets() else normalized
            )
            self._invalidate_access_token()

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        body: dict[str, Any] | None,
        headers: dict[str, str],
        timeout: float,
    ) -> dict[str, Any]:
        """发起 QQ 请求并统一解析 HTTP/JSON 错误。"""

        try:
            async with httpx.AsyncClient(**_client_kwargs(timeout)) as client:
                response = await client.request(
                    method,
                    url,
                    json=body,
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"QQ 官方机器人 HTTP 请求失败（状态码 {exc.response.status_code}）"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError("QQ 官方机器人网络请求失败") from exc
        except ValueError as exc:
            raise RuntimeError("QQ 官方机器人响应不是合法 JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("QQ 官方机器人响应格式无效")
        return payload


def _is_token_error(error: RuntimeError) -> bool:
    """判断 HTTP 错误是否可能表示访问令牌失效。"""

    return "状态码 401" in str(error) or "状态码 403" in str(error)


openclaw_qq_manager = OpenClawQQManager()
