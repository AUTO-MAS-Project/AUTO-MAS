#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""BetterGI 正式版 DFS2 资源就绪探测（只读，不操作安装目录）。

GitHub Release 与 Kachina/Steambird 的 DFS2 资源分发并非原子操作。
官方完整安装包有内嵌资源回退能力；这里是自动托管的保守更新门禁，
不代替安装器校验，也不负责修复未确认安装。
"""

import httpx
from packaging.version import InvalidVersion, Version

from app.utils import get_logger

logger = get_logger("BetterGI 资源就绪")

# BetterGI Build/kachina.config.json 的正式版 Steambird 源；
# Kachina native/dfs.rs 使用 ?with_metadata=1 获取版本和文件索引。
_STABLE_DFS2_URL = "https://bgi-ota.cocogoat.cn/resource/BetterGI.Install.exe"


async def stable_resources_ready(
    target: Version, *, proxy: str | None
) -> tuple[bool, str]:
    """确认官方 DFS2 公布了与 GitHub 安装目标同版本的元数据和文件索引。

    网络故障、版本不匹配和元数据异常均视为暂未就绪。
    调用方只能在没有未完成安装标记时跳过升级、沿用旧版本。
    """
    try:
        async with httpx.AsyncClient(
            proxy=proxy, timeout=8, follow_redirects=True
        ) as client:
            response = await client.get(
                _STABLE_DFS2_URL, params={"with_metadata": "1"}
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        # 不记录服务端响应体、鉴权信息和可能带敏感参数的 URL。
        logger.warning(
            f"BetterGI 正式版 {target} DFS2 探测失败：{type(error).__name__}"
        )
        return False, "官方资源索引暂不可用"

    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        return False, "官方资源元数据尚未发布"

    data = payload["data"]
    metadata = data.get("metadata")
    index = data.get("index")
    if not isinstance(metadata, dict) or not isinstance(index, dict) or not index:
        return False, "官方资源元数据或文件索引尚未就绪"

    tag = metadata.get("tag_name")
    if not isinstance(tag, str):
        return False, "官方资源版本字段缺失"
    try:
        remote = Version(tag)
    except InvalidVersion:
        return False, "官方资源版本格式无效"
    if remote != target:
        logger.info(f"BetterGI 正式版 {target} 等待 DFS2 分发；当前为 {remote}")
        return False, f"官方资源版本暂为 {remote}"

    logger.debug(f"BetterGI 正式版 {target} DFS2 元数据与文件索引已就绪")
    return True, ""
