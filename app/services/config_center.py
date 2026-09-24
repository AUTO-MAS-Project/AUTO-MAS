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
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.utils import LazyProxy, get_logger

logger = get_logger("配置中心")

# 延迟加载 Config，避免 app.services 初始化期间触发 app.core 循环导入
Config = LazyProxy("app.core", "Config")


# ==================== 部署参数 ====================
# 新配置中心的后端地址、以及「通用脚本」对应的 project/category，在三个仓库里都没有写死的
# 生产值，统一收敛到这里；部署方用环境变量覆盖即可，不需要改代码。
# 默认值沿用分享站域名加新后端的 /api/v1 前缀：新旧接口路径完全不重叠（旧站是
# /api/list/... 与 /api/upload/...），指向旧站时只会得到明确的失败提示，不会误写旧服务。
API_BASE_URL = os.environ.get(
    "AUTO_MAS_CONFIG_CENTER_API", "https://share.auto-mas.top/api/v1"
).rstrip("/")
PROJECT_KEY = os.environ.get("AUTO_MAS_CONFIG_CENTER_PROJECT", "auto-mas")
CATEGORY_KEY = os.environ.get("AUTO_MAS_CONFIG_CENTER_CATEGORY", "general")

# 通用脚本配置实际只有几 KiB，2 MiB 足够留出余量，同时挡住异常的超大响应
MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024
REQUEST_TIMEOUT = 15.0
# 桌面令牌到期前留出的余量，避免上传到一半才失效
TOKEN_EXPIRE_MARGIN = timedelta(seconds=30)


class ConfigCenterError(RuntimeError):
    """配置中心交互失败，message 可直接展示给用户。"""


class ConfigCenterClient:
    """新版 AUTO-MAS 配置中心的客户端，兼管桌面端授权状态。

    设备码与桌面令牌只保存在内存中：不写入配置文件、不进日志、不进 URL 查询串，
    进程退出即失效。
    """

    def __init__(self) -> None:

        ## 设备授权会话（等待用户在浏览器里确认时才有值）
        self._device_code: Optional[str] = None
        self._device_expires_at: Optional[datetime] = None
        self._user_code: str = ""
        self._verification_uri: str = ""
        self._poll_interval: int = 5

        ## 授权完成后的桌面令牌
        self._token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._username: str = ""
        self._display_name: str = ""

        self._lock = asyncio.Lock()

    # ==================== 模板浏览 ====================

    async def list_templates(
        self, page: int, page_size: int, keyword: Optional[str]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """拉取已发布的通用脚本配置列表。

        Args:
            page: 页码, 从 1 开始。
            page_size: 每页条数。
            keyword: 搜索关键字, 为空表示不过滤。

        Returns:
            (配置条目列表, 分页信息)。
        """

        params: Dict[str, Any] = {
            "project_key": PROJECT_KEY,
            "category_key": CATEGORY_KEY,
            "page": page,
            "page_size": page_size,
        }
        if keyword:
            params["keyword"] = keyword

        data = await self._request("GET", "/configs", params=params)
        items = [self._build_template_item(_) for _ in data.get("items", []) or []]
        pagination = data.get("pagination", {}) or {}

        return items, {
            "page": int(pagination.get("page", page)),
            "pageSize": int(pagination.get("page_size", page_size)),
            "total": int(pagination.get("total", len(items))),
            "hasNext": bool(pagination.get("has_next", False)),
        }

    async def download_template(
        self, config_key: str, version_no: Optional[int]
    ) -> Dict[str, Any]:
        """下载指定配置的已发布版本并解析为通用脚本配置字典。

        Args:
            config_key: 配置中心的配置标识。
            version_no: 版本号, 为空表示已发布的最新版本。

        Returns:
            解析后的配置字典。

        Raises:
            ConfigCenterError: 下载失败、体积超限或内容不是通用脚本配置。
        """

        params = {"version_no": version_no} if version_no else None
        url = (
            f"{API_BASE_URL}/configs/{PROJECT_KEY}/{CATEGORY_KEY}/{config_key}/download"
        )

        async with httpx.AsyncClient(
            proxy=Config.proxy, follow_redirects=True, timeout=REQUEST_TIMEOUT
        ) as client:
            try:
                async with client.stream("GET", url, params=params) as response:
                    if response.status_code != 200:
                        await response.aread()
                        raise ConfigCenterError(
                            self._describe_failure(response, "下载配置失败")
                        )

                    chunks: List[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_DOWNLOAD_BYTES:
                            raise ConfigCenterError(
                                f"配置文件超过 {MAX_DOWNLOAD_BYTES // 1024 // 1024} MB, 已终止下载"
                            )
                        chunks.append(chunk)
            except httpx.HTTPError as e:
                logger.warning(f"下载配置失败: {e}")
                raise ConfigCenterError(f"无法连接配置中心: {e}") from e

        try:
            data = json.loads(b"".join(chunks).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ConfigCenterError("配置文件不是有效的 JSON, 无法导入") from e

        if not isinstance(data, dict) or not isinstance(data.get("Script"), dict):
            raise ConfigCenterError("配置文件不是通用脚本配置, 无法导入")

        # 分享站上的文件可能是从网页端手工上传的，里面还带着用户数据，导入时一律丢掉
        data.pop("SubConfigsInfo", None)

        return data

    # ==================== 设备授权 ====================

    async def start_authorization(self) -> Dict[str, Any]:
        """向配置中心申请设备码, 返回给前端用于引导用户到浏览器授权。"""

        async with self._lock:
            data = await self._request(
                "POST", "/auth/device/code", json_body={"client_name": "AUTO-MAS"}
            )

            device_code = str(data.get("device_code", ""))
            if not device_code:
                raise ConfigCenterError("配置中心未返回设备码")

            self._device_code = device_code
            self._user_code = str(data.get("user_code", ""))
            self._verification_uri = str(
                data.get("verification_uri_complete")
                or data.get("verification_uri")
                or ""
            )
            self._poll_interval = max(int(data.get("interval", 5) or 5), 1)
            expires_in = max(int(data.get("expires_in", 600) or 600), 1)
            self._device_expires_at = datetime.now() + timedelta(seconds=expires_in)

            logger.info(f"已申请配置中心设备授权码: {self._user_code}")

            return {
                "userCode": self._user_code,
                "verificationUri": self._verification_uri,
                "expiresIn": expires_in,
                "interval": self._poll_interval,
            }

    async def poll_authorization(self) -> Dict[str, Any]:
        """轮询一次授权结果。

        Returns:
            status 为 pending / authorized / denied / expired / idle 的状态字典。
        """

        async with self._lock:
            if not self._device_code:
                return self._build_status()

            if (
                self._device_expires_at is not None
                and datetime.now() >= self._device_expires_at
            ):
                self._reset_device_session()
                return {"status": "expired", "message": "授权码已过期, 请重新发起授权"}

            device_code = self._device_code

        # 网络请求放在锁外：轮询最长要等一个超时，期间用户点「取消」不该被卡住
        data = await self._request(
            "POST", "/auth/device/token", json_body={"device_code": device_code}
        )

        async with self._lock:
            # 等待期间用户可能已取消或重新发起，本次结果就作废
            if self._device_code != device_code:
                return self._build_status()

            status = str(data.get("status", "pending"))

            if status == "authorized":
                self._token = str(data.get("access_token", ""))
                expires_in = max(int(data.get("expires_in", 1800) or 1800), 1)
                self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)
                self._username = str(data.get("username", ""))
                self._display_name = str(data.get("display_name") or self._username)
                self._reset_device_session()
                logger.success(f"配置中心授权成功: {self._username}")
                return self._build_status()

            if status in ("denied", "expired"):
                self._reset_device_session()
                message = (
                    "已在浏览器中拒绝本次授权"
                    if status == "denied"
                    else "授权码已过期, 请重新发起授权"
                )
                return {"status": status, "message": message}

            if status == "slow_down":
                self._poll_interval = max(int(data.get("interval", 5) or 5), 1) + 1

            return {
                "status": "pending",
                "userCode": self._user_code,
                "verificationUri": self._verification_uri,
                "interval": self._poll_interval,
            }

    async def cancel_authorization(self) -> None:
        """用户主动取消授权等待。"""

        async with self._lock:
            if self._device_code:
                logger.info("用户取消了配置中心授权")
            self._reset_device_session()

    def get_status(self) -> Dict[str, Any]:
        """返回当前授权状态, 供前端渲染分享弹窗。"""

        return self._build_status()

    # ==================== 上传 ====================

    async def upload_config(
        self, display_name: str, description: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """以当前登录用户的身份提交一份新配置, 进入配置中心的待审核流程。

        Args:
            display_name: 配置名称。
            description: 配置描述。
            config: 已完成脱敏的通用脚本配置字典。

        Returns:
            配置中心返回的配置信息。

        Raises:
            ConfigCenterError: 未登录、登录已过期或上传被拒绝。
        """

        token = self._require_token()
        content = json.dumps(config, ensure_ascii=False).encode("utf-8")

        data = await self._request(
            "POST",
            "/user/configs",
            token=token,
            files={"file": (f"{display_name}.json", content, "application/json")},
            data={
                "project_key": PROJECT_KEY,
                "category_key": CATEGORY_KEY,
                "display_name": display_name,
                "description": description,
                "change_note": "来自 AUTO-MAS 桌面端分享",
            },
        )

        logger.success(f"配置已提交配置中心待审核: {display_name}")
        return data

    # ==================== 内部实现 ====================

    def _require_token(self) -> str:
        """取出仍然有效的桌面令牌。"""

        if not self._token or self._token_expires_at is None:
            raise ConfigCenterError("尚未登录配置中心, 请先完成浏览器授权")
        if datetime.now() + TOKEN_EXPIRE_MARGIN >= self._token_expires_at:
            self._clear_token()
            raise ConfigCenterError("配置中心登录状态已过期, 请重新授权")
        return self._token

    def _clear_token(self) -> None:
        """丢弃桌面令牌与登录用户信息。"""

        self._token = None
        self._token_expires_at = None
        self._username = ""
        self._display_name = ""

    def _build_status(self) -> Dict[str, Any]:
        """把内存中的授权状态整理成前端可直接使用的形状。"""

        if self._token and self._token_expires_at is not None:
            if datetime.now() + TOKEN_EXPIRE_MARGIN < self._token_expires_at:
                return {
                    "status": "authorized",
                    "username": self._username,
                    "displayName": self._display_name,
                    "expiresIn": int(
                        (self._token_expires_at - datetime.now()).total_seconds()
                    ),
                }
            self._clear_token()

        if self._device_code:
            return {
                "status": "pending",
                "userCode": self._user_code,
                "verificationUri": self._verification_uri,
                "interval": self._poll_interval,
            }

        return {"status": "idle"}

    def _reset_device_session(self) -> None:
        """清空未完成的设备授权会话。"""

        self._device_code = None
        self._device_expires_at = None
        self._user_code = ""
        self._verification_uri = ""

    def _build_template_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """把配置中心的列表项转成前端使用的形状。

        名称、描述、作者都是外部数据, 这里只做类型收敛, 渲染侧按纯文本处理。
        """

        return {
            "projectKey": str(item.get("project_key", PROJECT_KEY)),
            "categoryKey": str(item.get("category_key", CATEGORY_KEY)),
            "configKey": str(item.get("config_key", "")),
            "displayName": str(item.get("display_name", "")),
            "description": str(item.get("description") or ""),
            "ownerUsername": str(item.get("owner_username") or ""),
            "publishedVersionNo": item.get("published_version_no"),
            "publishedAt": str(item.get("published_at") or ""),
            "updatedAt": str(item.get("updated_at") or ""),
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """调用配置中心接口并拆掉 {code, message, data} 信封。

        Raises:
            ConfigCenterError: 网络失败或配置中心返回错误。
        """

        headers = {"Authorization": f"Bearer {token}"} if token else None

        async with httpx.AsyncClient(
            proxy=Config.proxy, follow_redirects=True, timeout=REQUEST_TIMEOUT
        ) as client:
            try:
                response = await client.request(
                    method,
                    f"{API_BASE_URL}{path}",
                    params=params,
                    json=json_body,
                    data=data,
                    files=files,
                    headers=headers,
                )
            except httpx.HTTPError as e:
                logger.warning(f"请求配置中心失败: {method} {path} - {e}")
                raise ConfigCenterError(f"无法连接配置中心: {e}") from e

        if response.status_code >= 400:
            # 服务端说令牌不认了就别再留着，否则界面会一直显示已登录
            if response.status_code == 401 and token:
                self._clear_token()
            raise ConfigCenterError(
                self._describe_failure(response, "配置中心请求失败")
            )

        try:
            payload = response.json()
        except ValueError as e:
            raise ConfigCenterError("配置中心返回了无法解析的内容") from e

        if not isinstance(payload, dict):
            raise ConfigCenterError("配置中心返回了无法解析的内容")

        result = payload.get("data")
        return result if isinstance(result, dict) else {}

    @staticmethod
    def _describe_failure(response: httpx.Response, fallback: str) -> str:
        """把配置中心的错误响应整理成一句可展示的中文提示。"""

        message = ""
        try:
            payload = response.json()
            if isinstance(payload, dict):
                message = str(payload.get("message") or "")
        except ValueError:
            message = ""

        if response.status_code == 401:
            return "配置中心登录状态已失效, 请重新授权"
        if response.status_code == 409:
            # 这个端点上的 409 只可能是同名配置已存在，服务端消息是英文的，直接给中文提示
            return "该配置名称已被占用, 请换一个名称"
        if response.status_code == 413:
            return message or "配置文件超过配置中心的体积上限"
        if response.status_code == 429:
            return message or "操作过于频繁, 请稍后再试"

        return f"{fallback}: {message or response.status_code}"


ConfigCenter = ConfigCenterClient()
