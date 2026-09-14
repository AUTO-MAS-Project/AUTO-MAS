#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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

"""森空岛练度数据源适配器（异步驱动层，方案 §3.1/决策 38）。

职责链：装载凭据 → 会话准备/刷新（token 轮换回写账号组）→
player/info 整表拉取 → 解析为练度映射 → 进程级 TTL 缓存。
HTTP 与缓存都在本模块（异步层），SklandProgressionProvider 保持同步
查表，快照经 ProviderContext 注入；内核与 local/manual 适配器零改动。

凭据本体只存签到域（GameSignAccountGroup.SklandToken），本模块经调用方
注入的 load_credential / save_credential 回调读写，不直接依赖 Config
（可测试性优先；签到域凭据引用见决策 38）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Mapping

import httpx

from app.tools.community_activity_roles import (
    CommunityActivityRole,
    normalize_skland_roles,
)
from app.tools.skland import (
    SklandCredentialExpiredError,
    create_skland_client,
    fetch_skland_binding_payload,
    fetch_skland_player_info,
    get_cached_device_id,
    prepare_skland_session_credential,
    refresh_skland_session_credential,
    serialize_skland_credential,
    skland_sign_lock,
)
from app.utils import get_logger

from .providers import parse_player_info_payload
from .types import Progression

logger = get_logger("森空岛练度源")

SKLAND_CACHE_TTL_SECONDS = 300  # 预览复用窗口；注入前以 force=True 强刷（决策 38）
SKLAND_FAILURE_TTL_SECONDS = 60  # 失败负缓存：预览连点时不反复打外部接口


@dataclass(frozen=True)
class SklandAccountRef:
    """绑定引用：签到账号组 UUID + 绑定角色的游戏 uid（非森空岛 userId）。"""

    account_uid: str
    game_uid: str


CredentialLoader = Callable[[str], Awaitable[str | None]]
CredentialSaver = Callable[[str, str], Awaitable[None]]

# 进程级缓存：键 (账号组 uid, 游戏 uid) → (过期时刻, 快照或 None)。
# None 为失败负缓存，避免凭据失效/断网期间每次预览都打外部接口。
_cache: dict[
    tuple[str, str], tuple[float, tuple[Mapping[str, Progression], int] | None]
] = {}


async def fetch_skland_progression(
    ref: SklandAccountRef,
    *,
    load_credential: CredentialLoader,
    save_credential: CredentialSaver | None = None,
    proxy: str | None = None,
    force: bool = False,
    now: float | None = None,
) -> tuple[Mapping[str, Progression], int] | None:
    """取绑定角色的整表练度（带 TTL 缓存）；不可用时返回 None（fail-open）。

    Args:
        ref: 绑定引用（账号组 UUID + 游戏 uid）。
        load_credential: 按账号组 uid 取 SklandToken 原文（解密后）。
        save_credential: token 轮换后回写账号组（不传则只跳过回写）。
        proxy: 出网代理；force=True 跳过缓存强拉（注入前用）；now 仅测试注入。

    Returns:
        (练度映射, 拉取时刻 epoch 秒)；凭据缺失/失效/网络失败返回 None，
        由调用方决定降级（provider 链短路落 local）。
    """

    current = time.time() if now is None else now
    key = (ref.account_uid, ref.game_uid)
    if not force:
        cached = _cache.get(key)
        if cached is not None and cached[0] > current:
            return cached[1]

    def put(value: tuple[Mapping[str, Progression], int] | None) -> None:
        ttl = (
            SKLAND_CACHE_TTL_SECONDS
            if value is not None
            else SKLAND_FAILURE_TTL_SECONDS
        )
        _cache[key] = (current + ttl, value)

    # 与签到流程共用同一把流程锁：签名 token 存在两个独立轮换写者（签到
    # 编排与本驱动层），并发刷新会把对方刚回写的 token 作废（评审备忘）
    async with skland_sign_lock:
        try:
            raw = await load_credential(ref.account_uid)
            if not raw:
                put(None)
                return None

            async with create_skland_client(proxy=proxy) as client:
                device_id = await get_cached_device_id(proxy, client=client)
                credential = await _prepare_and_refresh_credential(
                    client,
                    raw=raw,
                    account_uid=ref.account_uid,
                    device_id=device_id,
                    save_credential=save_credential,
                )
                payload = await fetch_skland_player_info(
                    client,
                    cred=credential["cred"],
                    sign_token=credential["token"],
                    uid=ref.game_uid,
                    device_id=device_id,
                    proxy=proxy,
                )
        except SklandCredentialExpiredError:
            logger.warning(
                f"森空岛凭据已失效，练度源降级为本地档案（{ref.account_uid}）"
            )
            put(None)
            return None
        except Exception as e:  # fail-open 契约：任何失败（含设备 ID 接口的裸
            # Exception）一律降级 None，调用方链短路落 local，绝不炸注入/预览
            logger.warning(f"森空岛练度拉取/凭据回写失败，降级为本地档案: {e}")
            put(None)
            return None

        progressions = parse_player_info_payload(payload)
        if not progressions:
            # 接口 code==0 但解析不出任何干员：形状漂移或数据异常。按失败
            # 负缓存处理，避免空练度被当成功缓存后静默短路成 local，与
            # "新号无练度"不可区分、无从排查
            logger.warning(
                f"森空岛练度数据为空，按拉取失败降级本地档案（{ref.account_uid}）"
            )
            put(None)
            return None
        captured_at = int(current)
        put((progressions, captured_at))
        return progressions, captured_at


async def _prepare_and_refresh_credential(
    client: httpx.AsyncClient,
    *,
    raw: str,
    account_uid: str,
    device_id: str,
    save_credential: CredentialSaver | None,
) -> dict[str, str]:
    """准备会话凭据并刷新签名 token；轮换后回写账号组（决策 38）。

    练度拉取与角色列表两条编排共用；`raw` 为账号组中已解密的存量凭据，
    与刷新结果序列化不同即视为轮换、执行回写。
    """

    credential = await prepare_skland_session_credential(client, raw, device_id)
    credential = await refresh_skland_session_credential(client, credential, device_id)
    serialized = serialize_skland_credential(credential)
    if save_credential is not None and serialized != raw:
        await save_credential(account_uid, serialized)
    return credential


async def fetch_skland_role_entries(
    account_uid: str,
    *,
    load_credential: CredentialLoader,
    save_credential: CredentialSaver | None = None,
    proxy: str | None = None,
) -> tuple[CommunityActivityRole, ...]:
    """拉取账号组在明日方舟的角色条目（绑定下拉用，方案 T4.4）。

    只需账号组引用，不需要已选游戏 uid——角色列表正是 uid 的来源。
    解析复用便签的 normalize_skland_roles（覆盖无 appCode 分组等响应
    变体）；与练度拉取共用同一把签到流程锁；凭据缺失返回空元组，
    上游失败抛错由调用方转错误提示。
    """

    async with skland_sign_lock:
        raw = await load_credential(account_uid)
        if not raw:
            return []

        async with create_skland_client(proxy=proxy) as client:
            device_id = await get_cached_device_id(proxy, client=client)
            credential = await _prepare_and_refresh_credential(
                client,
                raw=raw,
                account_uid=account_uid,
                device_id=device_id,
                save_credential=save_credential,
            )
            # 复用便签的角色归一化：覆盖无 appCode 分组等响应变体（评审跟进项）
            payload = await fetch_skland_binding_payload(
                client,
                cred=credential["cred"],
                sign_token=credential["token"],
                device_id=device_id,
                proxy=proxy,
            )
            return normalize_skland_roles(payload).roles_for_game("明日方舟")


def clear_skland_progression_cache() -> None:
    """清空进程级缓存（测试用；生产路径靠 TTL 自然过期）。"""

    _cache.clear()


__all__ = [
    "CredentialLoader",
    "CredentialSaver",
    "SklandAccountRef",
    "SKLAND_CACHE_TTL_SECONDS",
    "clear_skland_progression_cache",
    "fetch_skland_progression",
    "fetch_skland_role_entries",
]
