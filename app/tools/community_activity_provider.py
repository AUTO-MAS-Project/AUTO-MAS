#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file incorporates request knowledge from the following acknowledged
#   community projects:
#
#       nonebot-plugin-mystool Copyright © 2023-2025 Ljzd-PRO
#       https://github.com/Ljzd-PRO/nonebot-plugin-mystool
#
#       gxy12345/arknights-plugin
#       https://github.com/gxy12345/arknights-plugin

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


"""森空岛和米游社的只读活动请求适配器。

该模块只负责把凭据暂存于本次查询的内存、完成 provider 请求和返回 JSON。
活动解析由 ``community_activity_parser`` 负责，签到编排和配置保存不在本模块内。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import string
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import httpx

from .community_activity_transport import (
    CommunityActivityRequest,
    CommunityActivityTarget,
    CommunityActivityTransportError,
)
from .community_activity_roles import (
    CommunityActivityCapability,
    CommunityActivityRoleDiscovery,
    normalize_miyoushe_roles,
    normalize_skland_roles,
)

if TYPE_CHECKING:
    from .miyoushe import MiyousheSessionCapabilities

__all__ = [
    "CommunityActivityProvider",
    "build_community_activity_requester",
]


CredentialUpdate = Callable[[str], Awaitable[None]]

_ACTIVITY_REQUEST_TIMEOUT = 12.0
_MIYOUSHE_RECORD_SALT = "xV8v4Qu54lUKrEYFZkJhB8cuOh9Asafs"
_MIYOUSHE_WIDGET_SALT = "9ttJY72HxbjwWRNHJvn0n2AYue47nYsK"
_MIYOUSHE_DEVICE_FP_URL = (
    "https://public-data-api.mihoyo.com/device-fp/api/getFp"
)
_MIYOUSHE_DEVICE_LOGIN_URL = (
    "https://bbs-api.mihoyo.com/apihub/api/deviceLogin"
)
_MIYOUSHE_DEVICE_SAVE_URL = "https://bbs-api.mihoyo.com/apihub/api/saveDevice"
_MIYOUSHE_DEVICE_MODEL = "MI 8 SE"
_MIYOUSHE_DEVICE_NAME = "Xiaomi MI 8 SE"
_MIYOUSHE_ZZZ_DEVICE_NAME = "XiaomiMI 8 SE"
_MIYOUSHE_ZZZ_DEVICE_FP_SEED = "38d805c20d53d"
_MIYOUSHE_DEVICE_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 12; Unspecified Device) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Version/4.0 Chrome/103.0.5060.129 Mobile Safari/537.36 "
    "miHoYoBBS/2.99.1"
)
_MIYOUSHE_ZZZ_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 12; MI 8 SE Build/RQ3A.211001.001; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
    "Chrome/111.0.5563.116 Mobile Safari/537.36 miHoYoBBS/2.73.1"
)
_MIYOUSHE_RISK_CODES = frozenset({1034, 5003, 10035, 10041})


def _response_code(payload: Mapping[str, object]) -> int | None:
    for key in ("retcode", "code", "status"):
        value = payload.get(key)
        if isinstance(value, bool) or value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _response_json(
    response: httpx.Response,
    *,
    platform: str,
    game: str,
) -> Mapping[str, object]:
    """读取安全的 JSON 响应，不把 HTML 或请求正文带到错误文案。"""

    if response.status_code == 404:
        raise CommunityActivityTransportError(
            f"{platform}{game}角色数据不存在（HTTP 404）",
            status="unavailable",
        )
    if response.status_code in (401, 403, 429):
        raise CommunityActivityTransportError(
            f"{platform}{game}接口受到上游限制（HTTP {response.status_code}）",
            status="limited",
        )
    if response.status_code >= 500:
        raise CommunityActivityTransportError(
            f"{platform}{game}接口暂时不可用（HTTP {response.status_code}）",
            status="unavailable",
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise CommunityActivityTransportError(
            f"{platform}{game}接口返回非 JSON，可能触发风控",
            status="limited",
        ) from exc
    if not isinstance(payload, Mapping):
        raise CommunityActivityTransportError(
            f"{platform}{game}接口返回的数据结构无法识别",
            status="unavailable",
        )
    return payload


def _raise_business_error(
    payload: Mapping[str, object],
    *,
    platform: str,
    game: str,
) -> None:
    code = _response_code(payload)
    if code is None or code == 0:
        return
    limited = abs(code) in _MIYOUSHE_RISK_CODES or code in {
        -100,
        10000,
        10001,
    }
    status = "limited" if limited else "unavailable"
    raise CommunityActivityTransportError(
        f"{platform}{game}接口返回业务失败（业务码 {code}）",
        status=status,
    )


def _miyoushe_ds(
    *,
    query: str = "",
    widget: bool = False,
    data: bool = False,
    game: str = "",
) -> str:
    timestamp = str(int(time.time()))
    if data:
        from .miyoushe import SALT_DATA

        # 星铁 Widget 的参考实现调用 generate_ds(data={})，
        # 因而使用数据签名盐和空 body/query，而不是 iOS 无参盐。
        nonce = str(random.randint(100000, 200000))
        raw = f"salt={SALT_DATA}&t={timestamp}&r={nonce}&b=&q="
    else:
        if widget:
            nonce = "".join(
                random.choices(string.ascii_lowercase + string.digits, k=6)
            )
            raw = f"salt={_MIYOUSHE_WIDGET_SALT}&t={timestamp}&r={nonce}"
        elif game == "绝区零":
            # 绝区零参考实现的 CN 记录接口使用 xV8 盐和六位数字 nonce。
            nonce = str(random.randint(100000, 999999))
            raw = (
                f"salt={_MIYOUSHE_RECORD_SALT}&t={timestamp}&r={nonce}"
                f"&b=&q={query}"
            )
        elif query:
            # 记录接口的参数签名沿用参考实现的 4X 合同。
            nonce = str(random.randint(100000, 200000))
            raw = (
                f"salt={_MIYOUSHE_RECORD_SALT}&t={timestamp}&r={nonce}"
                f"&b=&q={query}"
            )
        else:
            nonce = "".join(
                random.choices(string.ascii_lowercase + string.digits, k=6)
            )
            raw = (
                f"salt={_MIYOUSHE_RECORD_SALT}&t={timestamp}&r={nonce}"
                f"&b=&q={query}"
            )
    return f"{timestamp},{nonce},{hashlib.md5(raw.encode()).hexdigest()}"


def _device_ds(body: str, *, game: str = "") -> str:
    from .miyoushe import SALT_DATA

    timestamp = str(int(time.time()))
    if game == "绝区零":
        nonce = str(random.randint(100000, 999999))
        salt = _MIYOUSHE_RECORD_SALT
    else:
        nonce = "".join(
            random.choices(string.ascii_lowercase + string.digits, k=6)
        )
        salt = SALT_DATA
    raw = f"salt={salt}&t={timestamp}&r={nonce}&b={body}&q="
    return f"{timestamp},{nonce},{hashlib.md5(raw.encode()).hexdigest()}"


def _device_fp_body(
    device_id: str,
    *,
    game: str = "",
    seed_id: str | None = None,
) -> dict[str, str]:
    is_zzz = game == "绝区零"
    normalized_device_id = device_id.lower()
    zzz_seed_id = (seed_id or str(uuid.uuid4())) if is_zzz else ""
    ext_fields = {
        "userAgent": _MIYOUSHE_ZZZ_USER_AGENT
        if is_zzz
        else _MIYOUSHE_DEVICE_USER_AGENT,
        "browserScreenSize": 243750,
        "maxTouchPoints": 5,
        "isTouchSupported": True,
        "browserLanguage": "zh-CN",
        "browserPlat": "Linux armv8l",
        "browserTimeZone": "Asia/Shanghai",
        "webGlRender": "Adreno (TM) 640",
        "webGlVendor": "Qualcomm",
        "numOfPlugins": 0,
        "listOfPlugins": "unknown",
        "screenRatio": 3,
        "deviceMemory": "4",
        "hardwareConcurrency": "8",
        "cpuClass": "unknown",
        "ifNotTrack": "unknown",
        "ifAdBlock": 0,
        "hasLiedResolution": 1,
        "hasLiedOs": 0,
        "hasLiedBrowser": 0,
    }
    if is_zzz:
        # ZZZ-Plugin 的 CN getFp 合同同时需要 Android 设备字段和一枚
        # 与实际 device_id 分离的 bbs/seed UUID；这里使用固定兼容设备
        # 描述，不读取或持久化本机设备信息。
        ext_fields.update(
            {
                "proxyStatus": 1,
                "isRoot": 0,
                "romCapacity": "768",
                "deviceName": _MIYOUSHE_DEVICE_MODEL,
                "productName": "MI 8 SE",
                "romRemain": "727",
                "hostname": "BuildHost",
                "screenSize": "1096x2434",
                "isTablet": 0,
                "aaid": zzz_seed_id,
                "model": _MIYOUSHE_DEVICE_MODEL,
                "brand": "Xiaomi",
                "hardware": "qcom",
                "deviceType": "MI 8 SE",
                "devId": "REL",
                "serialNumber": "unknown",
                "sdCapacity": 224845,
                "buildTime": "1692775759000",
                "buildUser": "BuildUser",
                "simState": 1,
                "ramRemain": "218344",
                "appUpdateTimeDiff": 1740498108042,
                "deviceInfo": "Xiaomi/MI 8 SE/MI 8 SE/MI 8 SE",
                "vaid": zzz_seed_id,
                "buildType": "user",
                "sdkVersion": "33",
                "ui_mode": "UI_MODE_TYPE_NORMAL",
                "isMockLocation": 0,
                "cpuType": "arm64-v8a",
                "isAirMode": 0,
                "ringMode": 2,
                "chargeStatus": 1,
                "manufacturer": "Xiaomi",
                "emulatorStatus": 0,
                "appMemory": "768",
                "osVersion": "12",
                "vendor": "unknown",
                "accelerometer": "-1.588236x6.8404818x6.999604",
                "sdRemain": 218214,
                "buildTags": "release-keys",
                "packageName": "com.mihoyo.hyperion",
                "networkType": "WiFi",
                "oaid": zzz_seed_id,
                "debugStatus": 1,
                "ramCapacity": "224845",
                "magnetometer": "-47.04375x51.3375x137.96251",
                "display": _MIYOUSHE_DEVICE_MODEL,
                "appInstallTimeDiff": 1740498108042,
                "packageVersion": "2.35.0",
                "gyroscope": "-0.22601996x-0.09453133x0.09040799",
                "batteryStatus": 88,
                "hasKeyboard": 0,
                "board": "qcom",
            }
        )
    body: dict[str, str] = {
        "seed_id": (
            zzz_seed_id
            if is_zzz
            else "".join(
                random.choices(string.ascii_lowercase + string.digits, k=16)
            )
        ),
        # ZZZ 参考实现的固定值只是 getFp 模板占位符；最终 noDs 请求会
        # 替换为当前账号设备 ID，设备登记和后续查询也使用同一设备值。
        "device_id": normalized_device_id,
        "platform": "2" if is_zzz else "5",
        "seed_time": str(int(time.time() * 1000)),
        "ext_fields": json.dumps(ext_fields, ensure_ascii=False),
        "app_name": "bbs_cn" if is_zzz else "account_cn",
        # getFp 需要一个本次申请用的种子；官方返回值才会用于后续请求。
        "device_fp": (
            _MIYOUSHE_ZZZ_DEVICE_FP_SEED
            if is_zzz
            else "".join(random.choices("0123456789abcdef", k=13))
        ),
    }
    if is_zzz:
        body["bbs_device_id"] = zzz_seed_id
    return body


def _miyoushe_v2_stoken(cookies: Mapping[str, str]) -> str:
    """读取小组件要求的 v2 stoken，兼容旧 Cookie 命名。"""

    stoken_v2 = str(cookies.get("stoken_v2") or "").strip()
    if stoken_v2:
        return stoken_v2
    stoken = str(cookies.get("stoken") or "").strip()
    return stoken if stoken.startswith("v2_") else ""


def _miyoushe_request_cookies(
    cookies: Mapping[str, str],
    *,
    require_v2_stoken: bool = False,
) -> dict[str, str]:
    """构建只用于本次请求的 Cookie 副本，不改变已保存凭据。"""

    result = dict(cookies)
    if require_v2_stoken:
        stoken_v2 = _miyoushe_v2_stoken(result)
        if stoken_v2:
            # 参考 BBSCookies.dict(v2_stoken=True, cookie_type=True)：
            # 请求字段使用 stoken，内部别名不随请求发送。
            result["stoken"] = stoken_v2
            result.pop("stoken_v1", None)
            result.pop("stoken_v2", None)
    return result


@dataclass
class CommunityActivityProvider:
    """为一个账号组执行只读活动请求。

    一个 provider 实例应覆盖一个账号组的全部游戏，以便在同一轮查询内共享
    森空岛刷新结果、米游社官方设备指纹和请求间隔。凭据默认只保留在内存中；
    ``on_credential_update`` 只有由调用方显式提供时才会收到刷新后的森空岛值。
    """

    platform: str
    raw_credential: str = field(repr=False)
    proxy: str | httpx.Proxy | None = None
    on_credential_update: CredentialUpdate | None = field(
        default=None, repr=False
    )
    miyoushe_request_interval: float = 1.2
    _credential: dict[str, str] | None = field(
        default=None, init=False, repr=False
    )
    _device_id: str = field(default="", init=False, repr=False)
    _device_fp: str = field(default="", init=False, repr=False)
    _miyoushe_device_fps: dict[str, str] = field(
        default_factory=dict, init=False, repr=False
    )
    _credential_ready: bool = field(default=False, init=False, repr=False)
    _credential_update_sent: bool = field(default=False, init=False, repr=False)
    _miyoushe_cookies: dict[str, str] | None = field(
        default=None, init=False, repr=False
    )
    _miyoushe_capabilities: MiyousheSessionCapabilities | None = field(
        default=None, init=False, repr=False
    )
    _state_lock: asyncio.Lock = field(
        default_factory=asyncio.Lock, init=False, repr=False
    )
    _miyoushe_rate_lock: asyncio.Lock = field(
        default_factory=asyncio.Lock, init=False, repr=False
    )
    _last_miyoushe_request: float | None = field(
        default=None, init=False, repr=False
    )

    def __post_init__(self) -> None:
        self.raw_credential = str(self.raw_credential or "").strip()

    async def request(self, request: CommunityActivityRequest) -> object:
        """执行一个已登记的请求规格并返回未解析的 JSON 对象。"""

        if request.target.platform != self.platform:
            raise ValueError(
                f"活动 provider 与目标平台不匹配：{request.target.platform}"
            )
        if self.platform == "森空岛":
            return await self._request_skland(request)
        if self.platform == "米游社":
            return await self._request_miyoushe(request)
        raise ValueError(f"{self.platform}活动 provider 尚未登记")

    async def discover_roles(
        self,
        *,
        account_uid: str,
        account_name: str,
    ) -> CommunityActivityRoleDiscovery:
        """在同一 provider 会话内读取账号组的游戏角色。"""

        if self.platform == "森空岛":
            return await self._discover_skland_roles(
                account_uid=account_uid,
                account_name=account_name,
            )
        if self.platform == "米游社":
            return await self._discover_miyoushe_roles(
                account_uid=account_uid,
                account_name=account_name,
            )
        raise ValueError(f"{self.platform}活动 provider 尚未登记")

    async def _discover_skland_roles(
        self,
        *,
        account_uid: str,
        account_name: str,
    ) -> CommunityActivityRoleDiscovery:
        from .skland import (
            SKLAND_BINDING_URL,
        )

        target = CommunityActivityTarget(
            account_uid=account_uid,
            account_name=account_name,
            platform="森空岛",
            game="角色绑定",
            role_uid="",
        )
        request = CommunityActivityRequest(
            target=target,
            source=SKLAND_BINDING_URL,
            method="GET",
            auth_scope="skland",
            signature_profile="skland_widget",
        )
        try:
            async with httpx.AsyncClient(
                proxy=self.proxy, trust_env=False
            ) as client:
                credential, device_id = await self._prepare_skland(
                    None,
                    client,
                )
                response = await client.get(
                    SKLAND_BINDING_URL,
                    headers=self._skland_request_headers(
                        request,
                        credential=credential,
                        device_id=device_id,
                    ),
                    timeout=_ACTIVITY_REQUEST_TIMEOUT,
                )
        except httpx.TimeoutException as exc:
            raise CommunityActivityTransportError(
                "森空岛角色列表请求超时", status="failed"
            ) from exc
        except httpx.HTTPError as exc:
            raise CommunityActivityTransportError(
                "森空岛角色列表网络请求失败", status="failed"
            ) from exc

        payload = _response_json(
            response,
            platform="森空岛",
            game="角色列表",
        )
        _raise_business_error(payload, platform="森空岛", game="角色列表")
        return normalize_skland_roles(payload)

    async def _discover_miyoushe_roles(
        self,
        *,
        account_uid: str,
        account_name: str,
    ) -> CommunityActivityRoleDiscovery:
        from .miyoushe import (
            BASE_HEADERS,
            ROLES_URL,
        )

        target = CommunityActivityTarget(
            account_uid=account_uid,
            account_name=account_name,
            platform="米游社",
            game="角色绑定",
            role_uid="",
        )
        request = CommunityActivityRequest(
            target=target,
            source=ROLES_URL,
            method="GET",
            auth_scope="miyoushe",
            signature_profile="miyoushe_params",
        )
        try:
            async with httpx.AsyncClient(
                proxy=self.proxy, trust_env=False
            ) as client:
                cookies, device_id, _ = await self._prepare_miyoushe(
                    request,
                    client,
                    require_activity=False,
                )
                await self._wait_miyoushe_request()
                headers = BASE_HEADERS.copy()
                headers.update(self._miyoushe_request_headers(
                    request,
                    device_id=device_id,
                    device_fp="",
                ))
                response = await client.get(
                    ROLES_URL,
                    headers=headers,
                    cookies=_miyoushe_request_cookies(
                        cookies,
                        require_v2_stoken=True,
                    ),
                    timeout=_ACTIVITY_REQUEST_TIMEOUT,
                )
        except httpx.TimeoutException as exc:
            raise CommunityActivityTransportError(
                "米游社角色列表请求超时", status="failed"
            ) from exc
        except httpx.HTTPError as exc:
            raise CommunityActivityTransportError(
                "米游社角色列表网络请求失败", status="failed"
            ) from exc

        payload = _response_json(
            response,
            platform="米游社",
            game="角色列表",
        )
        _raise_business_error(payload, platform="米游社", game="角色列表")
        discovery = normalize_miyoushe_roles(payload)
        capabilities = self._miyoushe_capabilities
        if capabilities is None or capabilities.activity_ready:
            return discovery
        return replace(
            discovery,
            activity_capability=CommunityActivityCapability(
                status="limited",
                reason=capabilities.activity_reason,
            ),
        )

    async def _request_skland(
        self, request: CommunityActivityRequest
    ) -> Mapping[str, object]:
        try:
            async with httpx.AsyncClient(
                proxy=self.proxy, trust_env=False
            ) as client:
                credential, device_id = await self._prepare_skland(
                    request.target,
                    client,
                )
                headers = self._skland_request_headers(
                    request,
                    credential=credential,
                    device_id=device_id,
                )
                response = await client.get(
                    request.source,
                    params=request.query,
                    headers=headers,
                    timeout=request.timeout,
                )
        except httpx.TimeoutException as exc:
            raise CommunityActivityTransportError(
                f"森空岛{request.target.game}接口请求超时", status="failed"
            ) from exc
        except httpx.HTTPError as exc:
            raise CommunityActivityTransportError(
                f"森空岛{request.target.game}接口网络请求失败", status="failed"
            ) from exc

        payload = _response_json(
            response,
            platform="森空岛",
            game=request.target.game,
        )
        _raise_business_error(
            payload,
            platform="森空岛",
            game=request.target.game,
        )
        return payload

    async def _prepare_skland(
        self,
        target: CommunityActivityTarget | None,
        client: httpx.AsyncClient,
    ) -> tuple[dict[str, str], str]:
        from .skland import (
            get_cached_device_id,
            prepare_skland_session_credential,
            refresh_skland_session_credential,
            serialize_skland_credential,
            validate_skland_credential,
        )

        async with self._state_lock:
            if self._credential is None:
                self._credential = validate_skland_credential(
                    self.raw_credential
                )
            if not self._device_id:
                cached_device_id = target.device_id if target else ""
                self._device_id = cached_device_id or await get_cached_device_id(
                    self.proxy, client=client
                )
            if not self._credential_ready:
                credential = self._credential
                if not credential["cred"] or not credential["token"]:
                    self._credential = await prepare_skland_session_credential(
                        client,
                        credential,
                        self._device_id,
                    )
                else:
                    try:
                        self._credential = await refresh_skland_session_credential(
                            client,
                            self._credential,
                            self._device_id,
                            timeout=_ACTIVITY_REQUEST_TIMEOUT,
                        )
                    except (
                        CommunityActivityTransportError,
                        httpx.HTTPError,
                        OSError,
                        ValueError,
                    ):
                        # 刷新失败不覆盖原凭据；本次查询继续用旧值，让活动接口
                        # 自己返回可见的失效或风控状态。
                        pass
                self._credential_ready = True
                if self.on_credential_update is not None:
                    serialized = serialize_skland_credential(self._credential)
                    if serialized != self.raw_credential:
                        await self._publish_credential_update(serialized)
            return dict(self._credential), self._device_id

    async def _publish_credential_update(self, serialized: str) -> None:
        if self._credential_update_sent or self.on_credential_update is None:
            return
        self._credential_update_sent = True
        try:
            await self.on_credential_update(serialized)
        except Exception:
            # 回写是调用方的可选持久化动作，不能改变只读查询结果。
            return

    @staticmethod
    def _skland_request_headers(
        request: CommunityActivityRequest,
        *,
        credential: Mapping[str, str],
        device_id: str,
    ) -> dict[str, str]:
        from .skland import build_skland_signed_headers

        profile = request.signature_profile
        platform = "3" if profile == "skland_endfield_web" else "1"
        version = "1.0.0" if profile == "skland_endfield_web" else "1.21.0"
        parsed = urlparse(request.source)
        headers = build_skland_signed_headers(
            credential["token"],
            path=parsed.path,
            body_or_query=request.query_string,
            device_id=device_id,
            headers=request.header_map,
            platform=platform,
            version=version,
        )
        headers["cred"] = credential["cred"]
        return headers

    async def _request_miyoushe(
        self, request: CommunityActivityRequest
    ) -> Mapping[str, object]:
        try:
            async with httpx.AsyncClient(
                proxy=self.proxy, trust_env=False
            ) as client:
                cookies, device_id, device_fp = await self._prepare_miyoushe(
                    request,
                    client,
                )
                request_cookies = _miyoushe_request_cookies(
                    cookies,
                    require_v2_stoken=True,
                )
                await self._wait_miyoushe_request()
                headers = self._miyoushe_request_headers(
                    request,
                    device_id=device_id,
                    device_fp=device_fp,
                )
                response = await client.get(
                    request.source,
                    params=request.query,
                    headers=headers,
                    cookies=request_cookies,
                    timeout=request.timeout,
                )
        except httpx.TimeoutException as exc:
            raise CommunityActivityTransportError(
                f"米游社{request.target.game}接口请求超时", status="failed"
            ) from exc
        except httpx.HTTPError as exc:
            raise CommunityActivityTransportError(
                f"米游社{request.target.game}接口网络请求失败", status="failed"
            ) from exc

        payload = _response_json(
            response,
            platform="米游社",
            game=request.target.game,
        )
        _raise_business_error(
            payload,
            platform="米游社",
            game=request.target.game,
        )
        return payload

    async def _prepare_miyoushe(
        self,
        request: CommunityActivityRequest,
        client: httpx.AsyncClient,
        *,
        require_activity: bool = True,
    ) -> tuple[dict[str, str], str, str]:
        from .miyoushe import (
            prepare_miyoushe_session,
            validate_miyoushe_cookie,
        )

        async with self._state_lock:
            if self._miyoushe_cookies is None:
                validate_miyoushe_cookie(self.raw_credential)
                session = prepare_miyoushe_session(self.raw_credential)
                self._miyoushe_cookies = dict(session.cookies)
                self._miyoushe_capabilities = session.capabilities
                self._device_id = session.device_id
            cookies = dict(self._miyoushe_cookies)
            capabilities = self._miyoushe_capabilities
            if (
                require_activity
                and capabilities is not None
                and not capabilities.activity_ready
            ):
                raise CommunityActivityTransportError(
                    capabilities.activity_reason,
                    status="limited",
                )
            game = request.target.game
            if game == "绝区零":
                device_id = request.target.device_id.strip()
                device_fp = request.target.device_fp.strip()
                # 历史配置中的真实设备对继续优先使用；没有配置时复用下方
                # 官方 getFp 和设备登记链路自动准备运行期设备信息。
                if device_id and device_fp:
                    return cookies, device_id, device_fp

            device_id = self._device_id
            device_fp = self._miyoushe_device_fps.get(game, "")
            if request.requires_device_fingerprint and not device_fp:
                device_fp = await self._acquire_device_fp(
                    client,
                    device_id,
                    game=game,
                    cookies=_miyoushe_request_cookies(
                        cookies,
                        require_v2_stoken=True,
                    ),
                )
                await self._register_device(
                    client,
                    device_id=device_id,
                    device_fp=device_fp,
                    cookies=_miyoushe_request_cookies(
                        cookies,
                        require_v2_stoken=True,
                    ),
                    game=game,
                )
                self._miyoushe_device_fps[game] = device_fp
            self._device_fp = device_fp
            return cookies, device_id, self._device_fp

    @staticmethod
    def _miyoushe_device_fp_headers(
        device_id: str,
        *,
        game: str,
        user_agent: str,
    ) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": user_agent,
        }
        if game == "绝区零":
            headers.update(
                {
                    "Accept": "application/json, text/plain, */*",
                    "Origin": "https://act.mihoyo.com",
                    "Referer": "https://act.mihoyo.com/",
                    "X-Requested-With": "com.mihoyo.hyperion",
                    "x-rpc-app_version": "2.73.1",
                    "x-rpc-channel": "mihoyo",
                    "x-rpc-client_type": "2",
                    "x-rpc-csm_source": "myself",
                    "x-rpc-device_id": device_id,
                    "x-rpc-device_model": _MIYOUSHE_DEVICE_MODEL,
                    "x-rpc-device_name": _MIYOUSHE_DEVICE_NAME,
                    "x-rpc-sys_version": "12",
                }
            )
        return headers

    async def _acquire_device_fp(
        self,
        client: httpx.AsyncClient,
        device_id: str,
        *,
        game: str = "",
        seed_id: str = "",
        cookies: Mapping[str, str] | None = None,
    ) -> str:
        user_agent = (
            _MIYOUSHE_ZZZ_USER_AGENT
            if game == "绝区零"
            else _MIYOUSHE_DEVICE_USER_AGENT
        )
        response = await client.post(
            _MIYOUSHE_DEVICE_FP_URL,
            json=_device_fp_body(
                device_id,
                game=game,
                seed_id=seed_id or None,
            ),
            headers=self._miyoushe_device_fp_headers(
                device_id,
                game=game,
                user_agent=user_agent,
            ),
            cookies=cookies,
            timeout=_ACTIVITY_REQUEST_TIMEOUT,
        )
        payload = _response_json(response, platform="米游社", game="设备指纹")
        _raise_business_error(payload, platform="米游社", game="设备指纹")
        data = payload.get("data")
        device_fp = data.get("device_fp") if isinstance(data, Mapping) else None
        if not isinstance(device_fp, str) or not device_fp.strip():
            raise CommunityActivityTransportError(
                "米游社官方设备指纹响应无效，无法确认设备状态",
                status="limited",
            )
        return device_fp.strip()

    async def _register_device(
        self,
        client: httpx.AsyncClient,
        *,
        device_id: str,
        device_fp: str,
        cookies: Mapping[str, str],
        game: str = "",
    ) -> None:
        is_zzz = game == "绝区零"
        app_version = "2.73.1" if is_zzz else "2.99.1"
        base_data = {
            "app_version": app_version,
            "device_id": device_id,
            "device_name": (
                _MIYOUSHE_ZZZ_DEVICE_NAME
                if is_zzz
                else _MIYOUSHE_DEVICE_NAME
            ),
            "os_version": "33" if is_zzz else "30",
            "platform": "Android",
        }
        base_headers = {
            "x-rpc-client_type": "2",
            "x-rpc-app_version": app_version,
            "x-rpc-sys_version": "12",
            "x-rpc-channel": "mihoyo" if is_zzz else "miyousheluodi",
            "x-rpc-device_id": device_id,
            "x-rpc-device_name": _MIYOUSHE_DEVICE_NAME,
            "x-rpc-device_model": _MIYOUSHE_DEVICE_MODEL,
            "x-rpc-device_fp": device_fp,
            "Referer": (
                "https://act.mihoyo.com/"
                if is_zzz
                else "https://app.mihoyo.com"
            ),
            "Content-Type": "application/json; charset=UTF-8",
            "User-Agent": (
                _MIYOUSHE_ZZZ_USER_AGENT
                if is_zzz
                else "okhttp/4.9.3"
            ),
        }
        if is_zzz:
            base_headers.update(
                {
                    "Accept": "application/json, text/plain, */*",
                    "Origin": "https://act.mihoyo.com",
                    "X-Requested-With": "com.mihoyo.hyperion",
                    "x-rpc-csm_source": "myself",
                }
            )
        # 登记是降低风控概率的辅助步骤；失败时保留官方 getFp 值继续查询，
        # 由真正的实时便笺响应决定最终是成功还是受限。两个登记接口各自
        # 重新计算 DS，避免复用已过时的请求签名。
        for url in (_MIYOUSHE_DEVICE_LOGIN_URL, _MIYOUSHE_DEVICE_SAVE_URL):
            try:
                data = {
                    **base_data,
                    "registration_id": "".join(
                        random.choices(
                            string.ascii_lowercase + string.digits, k=19
                        )
                    ),
                }
                body = json.dumps(data, separators=(",", ":"))
                headers = {
                    **base_headers,
                    "DS": _device_ds(body, game=game),
                }
                response = await client.post(
                    url,
                    headers=headers,
                    content=body,
                    cookies=cookies,
                    timeout=_ACTIVITY_REQUEST_TIMEOUT,
                )
                payload = _response_json(response, platform="米游社", game="设备登记")
                _raise_business_error(
                    payload,
                    platform="米游社",
                    game="设备登记",
                )
            except (
                CommunityActivityTransportError,
                httpx.HTTPError,
                OSError,
                ValueError,
            ):
                continue

    async def _wait_miyoushe_request(self) -> None:
        if self.miyoushe_request_interval <= 0:
            return
        async with self._miyoushe_rate_lock:
            now = time.monotonic()
            if self._last_miyoushe_request is not None:
                delay = self.miyoushe_request_interval - (
                    now - self._last_miyoushe_request
                )
                if delay > 0:
                    await asyncio.sleep(delay)
            self._last_miyoushe_request = time.monotonic()

    @staticmethod
    def _miyoushe_request_headers(
        request: CommunityActivityRequest,
        *,
        device_id: str,
        device_fp: str,
    ) -> dict[str, str]:
        profile = request.signature_profile
        headers = request.header_map
        if profile == "miyoushe_params":
            headers["DS"] = _miyoushe_ds(
                query=request.query_string,
                game=request.target.game,
            )
        elif profile == "miyoushe_ios":
            headers["DS"] = _miyoushe_ds(widget=True)
        elif profile == "miyoushe_data":
            headers["DS"] = _miyoushe_ds(data=True)
        else:
            raise CommunityActivityTransportError(
                "米游社当前请求规格未确认，不发起请求",
                status="limited",
            )
        headers.setdefault("x-rpc-app_version", "2.99.1")
        headers.setdefault("x-rpc-device_model", _MIYOUSHE_DEVICE_MODEL)
        headers.setdefault("x-rpc-device_name", _MIYOUSHE_DEVICE_NAME)
        headers.setdefault("User-Agent", _MIYOUSHE_DEVICE_USER_AGENT)
        if request.requires_device_id:
            headers["x-rpc-device_id"] = device_id
        else:
            headers.pop("x-rpc-device_id", None)
        if request.requires_device_fingerprint and device_fp:
            headers["x-rpc-device_fp"] = device_fp
        else:
            headers.pop("x-rpc-device_fp", None)
        if (
            request.target.game == "星穹铁道"
            and profile == "miyoushe_data"
        ):
            # 参考项目的星铁便笺走 iOS Widget 合同，不混入记录接口的
            # Android 设备头，避免上游返回通用 -10001。
            headers.update(
                {
                    "x-rpc-app_version": "2.63.1",
                    "x-rpc-channel": "appstore",
                    "x-rpc-page": "",
                    "x-rpc-device_fp": "",
                    "x-rpc-device_id": "",
                    "x-rpc-device_model": "iPhone10,2",
                    "x-rpc-device_name": "iPhone",
                    "x-rpc-sys_version": "16.2",
                    "Connection": "keep-alive",
                    "Host": "api-takumi-record.mihoyo.com",
                    "User-Agent": "WidgetExtension/231 CFNetwork/1390 Darwin/22.0.0",
                }
            )
        return headers


def build_community_activity_requester(
    platform: str,
    raw_credential: str,
    *,
    proxy: str | httpx.Proxy | None = None,
    on_credential_update: CredentialUpdate | None = None,
    miyoushe_request_interval: float = 1.2,
) -> Callable[[CommunityActivityRequest], Awaitable[object]]:
    """构造一个账号级 provider 请求函数，供活动 collector 注入。"""

    if platform not in {"森空岛", "米游社"}:
        raise ValueError(f"{platform}活动 provider 尚未登记")
    provider = CommunityActivityProvider(
        platform=platform,
        raw_credential=raw_credential,
        proxy=proxy,
        on_credential_update=on_credential_update,
        miyoushe_request_interval=miyoushe_request_interval,
    )
    return provider.request
