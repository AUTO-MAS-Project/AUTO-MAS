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
import base64
import io
import json
import os
import re
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from PIL import Image, ImageOps

from app.utils import LazyProxy, get_logger

logger = get_logger("配置中心")

# 延迟加载 Config，避免 app.services 初始化期间触发 app.core 循环导入
Config = LazyProxy("app.core", "Config")


# ==================== 部署参数 ====================
# 新配置中心的后端地址、以及「通用脚本」对应的 project/category，在三个仓库里都没有写死的
# 生产值，统一收敛到这里；部署方用环境变量覆盖即可，不需要改代码。
# 默认指向数据管理中心（data.auto-mas.top）的 /api/v1。旧分享站是 /api/list/... 与
# /api/upload/...，两边路径完全不重叠，误指向旧站时只会得到明确的失败提示，不会误写旧服务。
#
# 命名对照：数据管理中心在 38f868b 起把 config 域整体改名为 file 域，同一个值在本项目里
# 叫 configKey / config_key（沿用桌面端与前端既有的 API 字段名），在数据中心侧叫 file_key。
# 线上格式一律按数据中心为准，转换只发生在本文件。
API_BASE_URL = os.environ.get(
    "AUTO_MAS_CONFIG_CENTER_API", "https://data.auto-mas.top/api/v1"
).rstrip("/")
# 分享站会把 API 跳到别的子域（data.auto-mas.top 307 到 data2.auto-mas.top）。httpx 跟随跨域
# 跳转时会删掉 Authorization，带令牌的请求跳过去就是 401，令牌随即被清，表现为登录后立刻掉线。
# 跳转目标是这个域名或其子域、且仍是 https 时补回令牌，跳到别处照旧不带。
TOKEN_REDIRECT_DOMAIN = "auto-mas.top"
PROJECT_KEY = os.environ.get("AUTO_MAS_CONFIG_CENTER_PROJECT", "auto-mas")
# 数据中心里通用脚本模板所在的分类键是 GeneralConfig，且该键大小写敏感：写成 general
# 不会报错，只会静默返回 0 条，模板列表就永远是空的。通用脚本模板都发布在这个分类下。
CATEGORY_KEY = os.environ.get("AUTO_MAS_CONFIG_CENTER_CATEGORY", "GeneralConfig")
# 外观包所在的分类键，同样大小写敏感。必须与 Electron 主进程
# frontend/electron/services/onlineAppearanceService.ts 里的 categoryKey 一致，
# 否则这里传上去的外观在主题商店里看不到。
APPEARANCE_CATEGORY_KEY = os.environ.get(
    "AUTO_MAS_CONFIG_CENTER_APPEARANCE_CATEGORY", "theme"
)

# 通用脚本配置实际只有几 KiB，2 MiB 足够留出余量，同时挡住异常的超大响应
MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024
REQUEST_TIMEOUT = 15.0
# 桌面令牌到期前留出的余量，避免上传到一半才失效
TOKEN_EXPIRE_MARGIN = timedelta(seconds=30)

# 外观包上传前的轻量校验，上限与 Electron 主进程 appearanceService.ts 的 APPEARANCE_LIMITS 一致；
# 完整校验（资源声明、图片格式、光标尺寸等）由 Electron 在上传对话框里先做过一遍。
APPEARANCE_MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
APPEARANCE_MAX_MANIFEST_BYTES = 256 * 1024
APPEARANCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
# 外观封面（主题商店列表里的预览图）上限，与 Electron 主进程取封面时的上限一致
COVER_MAX_BYTES = 2 * 1024 * 1024
# 封面来源图（包内 preview 或另选的图片）上限，与外观包单个文件上限一致；
# 实际作者包的预览图常有 2–3 MB，上传前统一缩成商店用的小图，列表翻页才不至于动辄几十 MB。
COVER_SOURCE_MAX_BYTES = 8 * 1024 * 1024
COVER_MAX_SIZE = (1280, 800)
COVER_MAX_SOURCE_PIXELS = 40_000_000
COVER_WEBP_QUALITY = (85, 70)
# 外观包体积远大于通用脚本配置，上传给更长的超时
UPLOAD_TIMEOUT = 120.0
# 「我的外观」按页取全；页数上限只防分享站分页异常时无限翻页
MY_FILES_PAGE_SIZE = 100
MY_FILES_MAX_PAGES = 50


class ConfigCenterError(RuntimeError):
    """配置中心交互失败，message 可直接展示给用户。

    status_code 沿用配置中心的 HTTP 状态；本地校验失败为 400，网络失败为 503，
    其余未细分的失败为 500。reason 是配置中心拒绝的类别（pendingLimit / conflict / tooLarge），
    供前端按类别给出本地化提示，其余情况为空。
    """

    def __init__(
        self, message: str, *, status_code: int = 500, reason: Optional[str] = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.reason = reason


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

        data = await self._request("GET", "/files", params=params)
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
        url = f"{API_BASE_URL}/files/{PROJECT_KEY}/{CATEGORY_KEY}/{config_key}/download"

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

        content = json.dumps(config, ensure_ascii=False).encode("utf-8")

        data = await self.upload_file(
            category_key=CATEGORY_KEY,
            display_name=display_name,
            description=description,
            change_note="来自 AUTO-MAS 桌面端分享",
            filename=f"{display_name}.json",
            content=content,
            content_type="application/json",
            conflict_message="该配置名称已被占用, 请换一个名称",
        )

        logger.success(f"配置已提交配置中心待审核: {display_name}")
        return data

    async def upload_file(
        self,
        *,
        category_key: str,
        display_name: str,
        description: str,
        change_note: str,
        filename: str,
        content: bytes,
        content_type: str,
        conflict_message: Optional[str] = None,
        too_large_message: Optional[str] = None,
        cover: Optional[Tuple[str, bytes, str]] = None,
    ) -> Dict[str, Any]:
        """以当前登录用户的身份在指定分类下新建一个文件, 首个版本进入待审核流程。

        Args:
            category_key: 配置中心分类键。
            display_name: 文件名称, 配置中心据此生成 file_key。
            description: 文件描述。
            change_note: 首个版本的变更说明。
            filename: 上传的源文件名。
            content: 文件内容。
            content_type: 文件 MIME 类型。
            conflict_message: 名称被占用 (409) 时展示的提示, 为空则用通用提示。
            too_large_message: 超过体积上限 (413) 时展示的提示, 为空则用通用提示。
            cover: 封面图片 (文件名, 内容, MIME), 作为 multipart 的 cover 部分一并上传。

        Returns:
            配置中心返回的文件信息, 含 id / file_key / version 等字段。

        Raises:
            ConfigCenterError: 未登录、登录已过期或上传被拒绝。
        """

        token = self._require_token()
        files: Dict[str, Any] = {"file": (filename, content, content_type)}
        if cover is not None:
            files["cover"] = cover

        return await self._request(
            "POST",
            "/user/files",
            token=token,
            files=files,
            data={
                "project_key": PROJECT_KEY,
                "category_key": category_key,
                "display_name": display_name,
                "description": description,
                "change_note": change_note,
            },
            conflict_message=conflict_message,
            too_large_message=too_large_message,
            timeout=UPLOAD_TIMEOUT,
        )

    async def upload_file_version(
        self,
        *,
        file_id: int,
        filename: str,
        content: bytes,
        content_type: str,
        change_note: str,
        conflict_message: Optional[str] = None,
        too_large_message: Optional[str] = None,
        cover: Optional[Tuple[str, bytes, str]] = None,
    ) -> Dict[str, Any]:
        """以当前登录用户的身份给自己已上传的文件提交新版本, 进入待审核流程。

        Args:
            file_id: 配置中心的文件 id。
            filename: 上传的源文件名。
            content: 文件内容。
            content_type: 文件 MIME 类型。
            change_note: 本版本的变更说明。
            conflict_message: 内容与已有版本相同 (409) 时展示的提示, 为空则用通用提示。
            too_large_message: 超过体积上限 (413) 时展示的提示, 为空则用通用提示。
            cover: 封面图片 (文件名, 内容, MIME), 作为 multipart 的 cover 部分一并上传;
                为空时由配置中心沿用之前版本的封面。

        Returns:
            配置中心返回的文件信息, 含 id / file_key / version 等字段。

        Raises:
            ConfigCenterError: 未登录、登录已过期或上传被拒绝。
        """

        token = self._require_token()
        files: Dict[str, Any] = {"file": (filename, content, content_type)}
        if cover is not None:
            files["cover"] = cover

        return await self._request(
            "POST",
            f"/user/files/{file_id}/versions",
            token=token,
            files=files,
            data={"change_note": change_note},
            conflict_message=conflict_message,
            too_large_message=too_large_message,
            timeout=UPLOAD_TIMEOUT,
        )

    # ==================== 外观包上传 ====================

    async def upload_appearance(
        self,
        *,
        zip_path: str,
        display_name: str,
        description: str,
        change_note: str,
        file_id: Optional[int],
        cover_path: Optional[str] = None,
        cover_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """把本地外观包上传到分享站; file_id 非空时给已上传的那个文件发新版本。

        Args:
            zip_path: 本地外观 ZIP 路径。
            display_name: 外观名称, 只在新建时使用。
            description: 外观描述, 只在首次上传时生效。
            change_note: 本次上传的变更说明。
            file_id: 已上传文件的 id, 为空表示新建。
            cover_path: 封面图片路径, cover_mode 为 custom 时使用。
            cover_mode: 封面来源, package 用包里 theme.json 的 preview, custom 用 cover_path,
                inherit 不发封面、由分享站沿用之前版本的封面 (只能用于新版本);
                为空时有 cover_path 按 custom, 否则按 package。

        Returns:
            fileId / fileKey / versionNo / reviewStatus / isNewFile / appearanceId 组成的字典。

        Raises:
            ConfigCenterError: 外观包不合法 (400)、未登录或上传被拒绝。
        """

        mode = cover_mode or ("custom" if cover_path else "package")
        if mode == "inherit" and file_id is None:
            raise ConfigCenterError(
                "只有发新版本时才能沿用分享站上的封面", status_code=400
            )

        # 第一步：本地轻量校验，不合法就不发任何请求
        appearance_id, content, cover = await asyncio.to_thread(
            self._read_appearance_package,
            zip_path,
            cover_path if mode == "custom" else None,
            mode != "inherit",
        )
        username = self._username
        filename = f"{appearance_id}.zip"
        too_large_message = "外观包超过分享站的体积上限"

        # 第二步：新建文件或追加版本
        if file_id is None:
            data = await self.upload_file(
                category_key=APPEARANCE_CATEGORY_KEY,
                display_name=display_name,
                description=description,
                change_note=change_note,
                filename=filename,
                content=content,
                content_type="application/zip",
                conflict_message="这个外观名称已被占用, 请换一个名称",
                too_large_message=too_large_message,
                cover=cover,
            )
        else:
            try:
                data = await self.upload_file_version(
                    file_id=file_id,
                    filename=filename,
                    content=content,
                    content_type="application/zip",
                    change_note=change_note,
                    conflict_message="外观包和封面都与分享站上的版本相同, 无需重复上传",
                    too_large_message=too_large_message,
                    cover=cover,
                )
            except ConfigCenterError as e:
                # 站上那个文件已经删了或不归这个账号：本机指向它的记录作废
                if e.status_code in (403, 404):
                    await self._forget_appearance_upload(username, file_id)
                raise

        version = data.get("version")
        version = version if isinstance(version, dict) else {}
        result = {
            "fileId": int(data.get("id") or file_id or 0),
            "fileKey": str(data.get("file_key") or ""),
            "versionNo": int(version.get("version_no") or 0),
            # 管理员上传直接通过；其余一律视为待审核
            "reviewStatus": (
                "approved" if version.get("review_status") == "approved" else "pending"
            ),
            "isNewFile": file_id is None,
            "appearanceId": appearance_id,
        }
        logger.success(
            f"外观包已上传分享站: {appearance_id} -> 文件 {result['fileId']} 版本 {result['versionNo']} ({result['reviewStatus']})"
        )

        # 第三步：记下这个账号把哪个外观传成了哪个文件，下次直接发新版本
        await self._save_appearance_upload(
            username,
            appearance_id,
            {
                "fileId": result["fileId"],
                "fileKey": result["fileKey"],
                "displayName": str(data.get("display_name") or display_name),
                "updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            },
        )

        return result

    def list_appearance_uploads(self) -> List[Dict[str, Any]]:
        """当前登录账号在本机留下的外观上传记录, 未登录时为空, 按更新时间从新到旧。"""

        status = self._build_status()
        if status.get("status") != "authorized":
            return []

        records = self._load_appearance_uploads().get(self._username, {})
        items: List[Dict[str, Any]] = []
        for appearance_id, record in records.items():
            if not isinstance(record, dict):
                logger.warning(f"外观上传记录格式错误, 已忽略: {appearance_id}")
                continue
            try:
                items.append(
                    {
                        "appearanceId": str(appearance_id),
                        "fileId": int(record["fileId"]),
                        "fileKey": str(record.get("fileKey") or ""),
                        "displayName": str(record.get("displayName") or ""),
                        "updatedAt": str(record.get("updatedAt") or ""),
                    }
                )
            except (KeyError, TypeError, ValueError):
                logger.warning(f"外观上传记录格式错误, 已忽略: {appearance_id}")

        items.sort(key=lambda item: item["updatedAt"], reverse=True)
        return items

    # ==================== 我的外观 ====================

    async def list_my_appearances(self) -> List[Dict[str, Any]]:
        """当前登录账号在分享站外观分类下的全部文件, 含待审核和被驳回的。

        作者自己删掉 (回收站里) 的不列出。

        Raises:
            ConfigCenterError: 未登录、登录已过期或分享站拒绝。
        """

        token = self._require_token()
        items: List[Dict[str, Any]] = []
        for page in range(1, MY_FILES_MAX_PAGES + 1):
            data = await self._request(
                "GET",
                "/user/files",
                token=token,
                params={
                    "project_key": PROJECT_KEY,
                    "category_key": APPEARANCE_CATEGORY_KEY,
                    "page": page,
                    "page_size": MY_FILES_PAGE_SIZE,
                },
            )
            page_items = data.get("items", []) or []
            items.extend(
                self._build_my_appearance(item)
                for item in page_items
                if isinstance(item, dict) and item.get("status") != "recycled"
            )
            pagination = data.get("pagination", {}) or {}
            if not pagination.get("has_next") or not page_items:
                break
        else:
            logger.warning(
                f"我的外观超过 {MY_FILES_MAX_PAGES} 页, 只取前 {len(items)} 个"
            )

        return items

    async def get_my_appearance_cover(
        self, file_id: int, version_no: Optional[int], *, inheritable: bool = False
    ) -> Dict[str, Any]:
        """取自己某个外观任一版本的封面 (含待审核和被驳回的版本)。

        Args:
            file_id: 分享站文件 id。
            version_no: 版本号, 为空表示最新版本; inheritable 为真时忽略。
            inheritable: 为真时取「不带封面发新版本时分享站会沿用的那张」:
                最近一个未被驳回 (已通过或待审核) 且带封面的版本。

        Returns:
            dataUrl (封面的 data URL) 与 versionNo (封面所在版本, 取最新版本时为空) 组成的字典。

        Raises:
            ConfigCenterError: 未登录、没有 (可沿用的) 封面 (404)、体积超限或不是图片。
        """

        token = self._require_token()
        if inheritable:
            version_no = await self._find_inheritable_cover_version(file_id, token)
            if version_no is None:
                raise ConfigCenterError("没有可以沿用的封面", status_code=404)
        data_url = await self._download_my_cover(file_id, version_no, token)
        return {"dataUrl": data_url, "versionNo": version_no}

    async def _find_inheritable_cover_version(
        self, file_id: int, token: str
    ) -> Optional[int]:
        """按分享站给普通用户上传沿用封面的规则, 找出会被沿用的封面所在版本。

        规则与分享站一致: 新版本不带封面时, 取最近一个未被驳回 (已通过或待审核) 且带封面的版本。
        作者给自己的文件发新版本走的就是这条规则。
        """

        versions = await self._request_data(
            "GET", f"/user/files/{file_id}/versions", token=token
        )
        candidates = [
            int(version["version_no"])
            for version in (versions if isinstance(versions, list) else [])
            if isinstance(version, dict)
            and version.get("review_status") in ("approved", "pending")
            and version.get("has_cover")
            and version.get("version_no") is not None
        ]
        return max(candidates, default=None)

    async def _download_my_cover(
        self, file_id: int, version_no: Optional[int], token: str
    ) -> str:
        """用拥有者封面端点下载封面并转成 data URL。"""

        params = {"version_no": version_no} if version_no else None
        path = f"/user/files/{file_id}/cover"

        async with self._client(REQUEST_TIMEOUT, token) as client:
            try:
                async with client.stream(
                    "GET",
                    f"{API_BASE_URL}{path}",
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                ) as response:
                    if response.status_code >= 400:
                        await response.aread()
                        raise self._failure_error(response, token, "获取封面失败")

                    chunks: List[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > COVER_MAX_BYTES:
                            raise ConfigCenterError(
                                f"封面超过 {COVER_MAX_BYTES // 1024 // 1024} MB"
                            )
                        chunks.append(chunk)
            except httpx.HTTPError as e:
                logger.warning(f"请求配置中心失败: GET {path} - {e}")
                raise ConfigCenterError(
                    f"无法连接配置中心: {e}", status_code=503
                ) from e

        data = b"".join(chunks)
        mime = self._sniff_image(data)
        if mime is None:
            raise ConfigCenterError("分享站返回的封面不是 PNG、JPEG 或 WebP 图片")
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"

    async def update_my_appearance_description(
        self, file_id: int, description: str
    ) -> Dict[str, Any]:
        """修改自己某个外观的描述, 分享站上免审核直接生效; 返回更新后的条目。

        Raises:
            ConfigCenterError: 未登录、不是自己的文件或分享站拒绝。
        """

        token = self._require_token()
        data = await self._request(
            "PUT",
            f"/user/files/{file_id}",
            token=token,
            json_body={"description": description},
        )
        return self._build_my_appearance(data)

    @staticmethod
    def _build_my_appearance(item: Dict[str, Any]) -> Dict[str, Any]:
        """把分享站的用户文件 (列表项或详情) 转成「我的外观」条目。

        列表项直接带 latest_review_status / latest_review_comment / latest_has_cover;
        详情没有这几个字段, 从 latest_version 里取。
        """

        latest = item.get("latest_version")
        latest = latest if isinstance(latest, dict) else {}
        review_status = item.get("latest_review_status", latest.get("review_status"))
        review_comment = item.get("latest_review_comment", latest.get("review_comment"))
        has_cover = item.get(
            "latest_has_cover", latest.get("has_cover", item.get("has_cover"))
        )
        published = item.get("published_version_no")

        return {
            "fileId": int(item.get("id") or 0),
            "fileKey": str(item.get("file_key") or ""),
            "displayName": str(item.get("display_name") or ""),
            "description": str(item.get("description") or ""),
            "status": str(item.get("status") or ""),
            "publishedVersionNo": int(published) if published is not None else None,
            "latestVersionNo": int(item.get("latest_version_no") or 0),
            "latestReviewStatus": (
                review_status
                if review_status in ("pending", "approved", "rejected")
                else None
            ),
            "latestReviewComment": str(review_comment or ""),
            "latestHasCover": bool(has_cover),
            "updatedAt": str(item.get("updated_at") or ""),
        }

    @staticmethod
    def _sniff_image(data: bytes) -> Optional[str]:
        """按文件头魔数认 PNG / JPEG / WebP, 返回 MIME; 都不是则为空。"""

        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "image/webp"
        return None

    @staticmethod
    def _detect_cover(data: bytes, source: str) -> Tuple[str, bytes, str]:
        """校验封面来源图并统一缩成商店用的封面, 返回 multipart 用的 (文件名, 内容, MIME)。

        来源图按文件头魔数只认 PNG / JPEG / WebP; 输出一律是长宽不超过 1280×800 的 WebP,
        保持原比例, 体积不超过 COVER_MAX_BYTES。

        Raises:
            ConfigCenterError: 体积超限、格式不对或无法解码, status_code 为 400。
        """

        if len(data) > COVER_SOURCE_MAX_BYTES:
            raise ConfigCenterError(
                f"{source}超过 {COVER_SOURCE_MAX_BYTES // 1024 // 1024} MB",
                status_code=400,
            )
        if ConfigCenterClient._sniff_image(data) is None:
            raise ConfigCenterError(
                f"{source}只支持 PNG、JPEG 或 WebP 图片", status_code=400
            )

        try:
            with Image.open(io.BytesIO(data)) as image:
                # 先看尺寸再解码，挡住小文件解出巨图的情况
                if image.width * image.height > COVER_MAX_SOURCE_PIXELS:
                    raise ConfigCenterError(f"{source}尺寸过大", status_code=400)
                image = ImageOps.exif_transpose(image)
                image = image.convert(
                    "RGBA" if image.mode in ("RGBA", "LA", "P") else "RGB"
                )
                image.thumbnail(COVER_MAX_SIZE, Image.Resampling.LANCZOS)
                for quality in COVER_WEBP_QUALITY:
                    buffer = io.BytesIO()
                    image.save(buffer, format="WEBP", quality=quality, method=4)
                    output = buffer.getvalue()
                    if len(output) <= COVER_MAX_BYTES:
                        return "cover.webp", output, "image/webp"
        except ConfigCenterError:
            raise
        except Exception as e:
            raise ConfigCenterError(f"{source}无法解码: {e}", status_code=400) from e

        raise ConfigCenterError(
            f"{source}压缩后仍超过 {COVER_MAX_BYTES // 1024 // 1024} MB",
            status_code=400,
        )

    @classmethod
    def _read_appearance_package(
        cls, zip_path: str, cover_path: Optional[str], need_cover: bool = True
    ) -> Tuple[str, bytes, Optional[Tuple[str, bytes, str]]]:
        """轻量校验外观 ZIP 并读出全部内容和封面。

        Args:
            zip_path: 本地外观 ZIP 路径。
            cover_path: 指定的封面图片路径, 为空时取 theme.json 的 preview。
            need_cover: 为 False 时不读封面 (沿用分享站上的封面), 返回的封面为空。

        Returns:
            (外观 id, ZIP 文件内容, 封面 (文件名, 内容, MIME) 或空)。

        Raises:
            ConfigCenterError: 校验不通过, status_code 为 400。
        """

        def invalid(message: str) -> ConfigCenterError:
            return ConfigCenterError(message, status_code=400)

        path = Path(zip_path)
        if not path.exists():
            raise invalid("外观包不存在")
        if not path.is_file():
            raise invalid("选择的路径不是文件")
        if path.suffix.lower() != ".zip":
            raise invalid("请选择 ZIP 外观包")
        if path.stat().st_size > APPEARANCE_MAX_ARCHIVE_BYTES:
            raise invalid(
                f"外观包超过 {APPEARANCE_MAX_ARCHIVE_BYTES // 1024 // 1024} MB, 无法上传"
            )

        try:
            with zipfile.ZipFile(path) as archive:
                try:
                    info = archive.getinfo("theme.json")
                except KeyError:
                    raise invalid("外观包根目录缺少 theme.json") from None
                if info.file_size > APPEARANCE_MAX_MANIFEST_BYTES:
                    raise invalid("theme.json 过大")
                raw_manifest = archive.read(info)

                try:
                    manifest = json.loads(raw_manifest.decode("utf-8-sig"))
                except (UnicodeDecodeError, json.JSONDecodeError) as e:
                    raise invalid("theme.json 不是有效的 JSON") from e
                if not isinstance(manifest, dict):
                    raise invalid("theme.json 不是有效的外观描述")
                if manifest.get("formatVersion") != 1:
                    raise invalid("不支持的外观包格式版本")
                appearance_id = manifest.get("id")
                if not isinstance(
                    appearance_id, str
                ) or not APPEARANCE_ID_PATTERN.match(appearance_id):
                    raise invalid("theme.json 里的外观 ID 无效")

                # 没指定封面时用包里 preview 指向的图；Electron 导入时路径不区分大小写，这里一致
                preview_data: Optional[bytes] = None
                preview = manifest.get("preview")
                if (
                    need_cover
                    and not cover_path
                    and isinstance(preview, str)
                    and preview
                ):
                    preview_info = next(
                        (
                            item
                            for item in archive.infolist()
                            if item.filename.lower() == preview.lower()
                            and not item.is_dir()
                        ),
                        None,
                    )
                    if preview_info is None:
                        raise invalid(f"外观包里缺少预览图: {preview}")
                    if preview_info.file_size > COVER_SOURCE_MAX_BYTES:
                        raise invalid(
                            f"外观包的预览图超过 {COVER_SOURCE_MAX_BYTES // 1024 // 1024} MB"
                        )
                    preview_data = archive.read(preview_info)
        except ConfigCenterError:
            raise
        except Exception as e:
            # 损坏、加密或用了不支持压缩方式的 ZIP 会抛出各式各样的异常，统一按包无效处理
            raise invalid(f"无法读取外观包: {e}") from e

        # 封面：指定图片优先，其次是包里的 preview
        cover: Optional[Tuple[str, bytes, str]] = None
        if need_cover:
            if cover_path:
                cover_file = Path(cover_path)
                if not cover_file.is_file():
                    raise invalid("预览图不存在或不是文件")
                if cover_file.stat().st_size > COVER_SOURCE_MAX_BYTES:
                    raise invalid(
                        f"预览图超过 {COVER_SOURCE_MAX_BYTES // 1024 // 1024} MB"
                    )
                cover = cls._detect_cover(cover_file.read_bytes(), "预览图")
            elif preview_data is not None:
                cover = cls._detect_cover(preview_data, "外观包的预览图")
            else:
                raise invalid("请提供预览图（外观包里没有 preview）")

        content = path.read_bytes()
        # 校验和读取之间文件被换掉时，以实际读到的大小为准再挡一次
        if len(content) > APPEARANCE_MAX_ARCHIVE_BYTES:
            raise invalid(
                f"外观包超过 {APPEARANCE_MAX_ARCHIVE_BYTES // 1024 // 1024} MB, 无法上传"
            )

        return appearance_id, content, cover

    def _load_appearance_uploads(self) -> Dict[str, Dict[str, Any]]:
        """读取本机外观上传记录, 损坏时按空处理。"""

        try:
            data = json.loads(Config.get("Data", "ShareAppearanceUploads"))
        except Exception as e:
            logger.warning(f"读取外观上传记录失败, 按空记录处理: {e}")
            return {}

        if not isinstance(data, dict):
            logger.warning("外观上传记录格式错误, 按空记录处理")
            return {}
        return {
            str(username): records
            for username, records in data.items()
            if isinstance(records, dict)
        }

    async def _save_appearance_upload(
        self, username: str, appearance_id: str, record: Dict[str, Any]
    ) -> None:
        """写入一条外观上传记录; 失败只记日志, 不影响已经成功的上传。"""

        if not username:
            logger.warning(f"未取得分享站用户名, 不记录外观上传: {appearance_id}")
            return

        data = self._load_appearance_uploads()
        data.setdefault(username, {})[appearance_id] = record
        try:
            await Config.set(
                "Data",
                "ShareAppearanceUploads",
                json.dumps(data, ensure_ascii=False),
            )
        except Exception as e:
            logger.warning(f"保存外观上传记录失败: {appearance_id}, {e}")

    async def _forget_appearance_upload(self, username: str, file_id: int) -> None:
        """删掉这个账号指向 file_id 的外观上传记录; 失败只记日志。"""

        data = self._load_appearance_uploads()
        records = data.get(username, {})
        stale = [
            appearance_id
            for appearance_id, record in records.items()
            if isinstance(record, dict) and str(record.get("fileId")) == str(file_id)
        ]
        if not stale:
            return
        for appearance_id in stale:
            del records[appearance_id]
        try:
            await Config.set(
                "Data",
                "ShareAppearanceUploads",
                json.dumps(data, ensure_ascii=False),
            )
            logger.info(f"分享站上已没有文件 {file_id}, 删除本机上传记录: {stale}")
        except Exception as e:
            logger.warning(f"删除外观上传记录失败: 文件 {file_id}, {e}")

    # ==================== 内部实现 ====================

    def _require_token(self) -> str:
        """取出仍然有效的桌面令牌。"""

        if not self._token or self._token_expires_at is None:
            raise ConfigCenterError(
                "尚未登录配置中心, 请先完成浏览器授权", status_code=401
            )
        if datetime.now() + TOKEN_EXPIRE_MARGIN >= self._token_expires_at:
            self._clear_token()
            raise ConfigCenterError(
                "配置中心登录状态已过期, 请重新授权", status_code=401
            )
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
            "configKey": str(item.get("file_key", "")),
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
        conflict_message: Optional[str] = None,
        too_large_message: Optional[str] = None,
        timeout: float = REQUEST_TIMEOUT,
    ) -> Dict[str, Any]:
        """调用配置中心接口并拆掉 {code, message, data} 信封, data 不是对象时按空对象处理。

        Raises:
            ConfigCenterError: 网络失败或配置中心返回错误。
        """

        result = await self._request_data(
            method,
            path,
            params=params,
            json_body=json_body,
            data=data,
            files=files,
            token=token,
            conflict_message=conflict_message,
            too_large_message=too_large_message,
            timeout=timeout,
        )
        return result if isinstance(result, dict) else {}

    @staticmethod
    def _client(timeout: float, token: Optional[str]) -> httpx.AsyncClient:
        """建立请求配置中心的客户端; 带令牌时, 跟随跳转到 auto-mas.top 的 https 地址仍带上令牌。

        首跳的令牌由调用方放进请求头; 这里只补 httpx 跨域跳转时删掉的那份。
        请求钩子每一跳都会调用, 307 / 308 的请求体 (含 multipart) 由 httpx 原样重发。
        """

        event_hooks = None
        if token:

            async def keep_token(request: httpx.Request) -> None:
                host = request.url.host
                if request.url.scheme != "https" or (
                    host != TOKEN_REDIRECT_DOMAIN
                    and not host.endswith(f".{TOKEN_REDIRECT_DOMAIN}")
                ):
                    return
                if "Authorization" not in request.headers:
                    logger.debug(f"配置中心请求跳转到 {host}, 补回令牌")
                request.headers["Authorization"] = f"Bearer {token}"

            event_hooks = {"request": [keep_token]}

        return httpx.AsyncClient(
            proxy=Config.proxy,
            follow_redirects=True,
            timeout=timeout,
            event_hooks=event_hooks,
        )

    async def _request_data(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        token: Optional[str] = None,
        conflict_message: Optional[str] = None,
        too_large_message: Optional[str] = None,
        timeout: float = REQUEST_TIMEOUT,
    ) -> Any:
        """调用配置中心接口, 原样返回信封里的 data (可能是对象、列表或空)。

        Raises:
            ConfigCenterError: 网络失败或配置中心返回错误。
        """

        headers = {"Authorization": f"Bearer {token}"} if token else None

        async with self._client(timeout, token) as client:
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
                raise ConfigCenterError(
                    f"无法连接配置中心: {e}", status_code=503
                ) from e

        if response.status_code >= 400:
            raise self._failure_error(
                response,
                token,
                "配置中心请求失败",
                conflict_message=conflict_message,
                too_large_message=too_large_message,
            )

        try:
            payload = response.json()
        except ValueError as e:
            raise ConfigCenterError("配置中心返回了无法解析的内容") from e

        if not isinstance(payload, dict):
            raise ConfigCenterError("配置中心返回了无法解析的内容")

        return payload.get("data")

    def _failure_error(
        self,
        response: httpx.Response,
        token: Optional[str],
        fallback: str,
        *,
        conflict_message: Optional[str] = None,
        too_large_message: Optional[str] = None,
    ) -> ConfigCenterError:
        """把配置中心的错误响应转成 ConfigCenterError; 带令牌的请求被拒 401 时丢弃令牌。"""

        # 服务端说令牌不认了就别再留着，否则界面会一直显示已登录
        if response.status_code == 401 and token:
            self._clear_token()

        reason: Optional[str] = None
        if response.status_code == 409:
            reason = "pendingLimit" if self._is_pending_limit(response) else "conflict"
        elif response.status_code == 413:
            reason = "tooLarge"

        return ConfigCenterError(
            self._describe_failure(
                response,
                fallback,
                conflict_message=conflict_message,
                too_large_message=too_large_message,
            ),
            status_code=response.status_code,
            reason=reason,
        )

    @staticmethod
    def _is_pending_limit(response: httpx.Response) -> bool:
        """409 是否为待审核数超限 (data 带 limit), 而不是端点自己的冲突。"""

        try:
            payload = response.json()
        except ValueError:
            return False
        detail = payload.get("data") if isinstance(payload, dict) else None
        return isinstance(detail, dict) and detail.get("limit") is not None

    @staticmethod
    def _describe_failure(
        response: httpx.Response,
        fallback: str,
        *,
        conflict_message: Optional[str] = None,
        too_large_message: Optional[str] = None,
    ) -> str:
        """把配置中心的错误响应整理成一句可展示的中文提示。

        Args:
            response: 配置中心的错误响应。
            fallback: 没有更具体提示时的前缀。
            conflict_message: 409 且不是待审核超限时展示的提示, 由调用方按端点语义给出。
            too_large_message: 413 时展示的提示, 由调用方按上传内容给出。
        """

        message = ""
        detail: Any = None
        try:
            payload = response.json()
            if isinstance(payload, dict):
                message = str(payload.get("message") or "")
                detail = payload.get("data")
        except ValueError:
            message = ""

        if response.status_code == 401:
            return "配置中心登录状态已失效, 请重新授权"
        if response.status_code == 409:
            # 上传端点的 409 有两种：待审核数超限（data 带 limit/current），以及端点自己的冲突
            # （新建时同名、追加版本时内容未变）。服务端消息是英文的，一律给中文提示
            if isinstance(detail, dict) and detail.get("limit") is not None:
                return f"待审核的上传已达上限（{detail.get('current', '?')}/{detail['limit']}）"
            return conflict_message or f"{fallback}: {message or response.status_code}"
        if response.status_code == 413:
            # 服务端消息是英文的，调用方给了提示就用调用方的
            return too_large_message or message or "配置文件超过配置中心的体积上限"
        if response.status_code == 429:
            return message or "操作过于频繁, 请稍后再试"

        return f"{fallback}: {message or response.status_code}"


ConfigCenter = ConfigCenterClient()
