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


"""社区日常查询的 provider 请求规格和独立执行边界。"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Literal
from urllib.parse import urlencode

from app.utils.constants import UTC8

from .community_activity_parser import parse_activity_snapshot
from .community_contract import ActivityState, CommunityActivitySnapshot

__all__ = [
    "CommunityActivityRequest",
    "CommunityActivityTarget",
    "CommunityActivityTransportError",
    "ActivitySignatureProfile",
    "build_community_activity_requests",
    "collect_community_activity",
]


ActivityRequester = Callable[["CommunityActivityRequest"], Awaitable[object]]
ActivityAuthScope = Literal["skland", "miyoushe"]
ActivitySignatureProfile = Literal[
    "skland_widget",
    "skland_endfield_web",
    "miyoushe_params",
    "miyoushe_ios",
    "miyoushe_data",
]

SKLAND_BASE_URL = "https://zonai.skland.com"
MIYOUSHE_RECORD_BASE_URL = "https://api-takumi-record.mihoyo.com"


class CommunityActivityTransportError(RuntimeError):
    """provider 请求失败时供适配器传递的安全原因。"""

    def __init__(
        self,
        reason: str,
        *,
        status: Literal["limited", "unavailable", "failed"] = "failed",
    ) -> None:
        safe_reason = _normalize_transport_reason(reason, status=status)
        super().__init__(safe_reason)
        self.reason = safe_reason
        self.status = status


def _normalize_transport_reason(
    reason: object,
    *,
    status: Literal["limited", "unavailable", "failed"],
) -> str:
    """压缩适配器文案，拒绝明显的键值型敏感字段。"""

    text = " ".join(str(reason or "").split())
    if re.search(
        r"(?i)(?:token|cookie|authorization|cred|device[_-]?(?:id|fp))\s*[:=]",
        text,
    ):
        text = "社区活动接口受到上游限制" if status == "limited" else "社区活动接口请求失败"
    if not text:
        text = "社区活动接口受到上游限制" if status == "limited" else "社区活动接口请求失败"
    return text[:240]


@dataclass(frozen=True)
class CommunityActivityTarget:
    """一次社区活动查询所需的账号/角色脱敏上下文。"""

    account_uid: str
    account_name: str
    platform: str
    game: str
    role_uid: str
    server: str = ""
    role_name: str = ""
    user_id: str = ""
    device_id: str = field(default="", repr=False)
    device_fp: str = field(default="", repr=False)

    def role_metadata(self) -> dict[str, str]:
        """返回传给解析器的角色元数据，不包含凭据或设备字段。"""

        return {
            "name": self.role_name,
            "roleId": self.role_uid,
            "serverName": self.server,
        }


@dataclass(frozen=True)
class CommunityActivityRequest:
    """不携带认证值的单次 provider 请求规格。"""

    target: CommunityActivityTarget
    source: str
    method: Literal["GET"]
    params: tuple[tuple[str, str], ...] = ()
    headers: tuple[tuple[str, str], ...] = ()
    auth_scope: ActivityAuthScope = "miyoushe"
    signature_profile: ActivitySignatureProfile = "miyoushe_data"
    requires_ds: bool = False
    requires_device_id: bool = False
    requires_device_fingerprint: bool = False
    timeout: float = 30.0

    @property
    def query(self) -> dict[str, str]:
        """返回供 HTTP 客户端使用的查询参数副本。"""

        return dict(self.params)

    @property
    def header_map(self) -> dict[str, str]:
        """返回供 HTTP 客户端使用的公开请求头副本。"""

        return dict(self.headers)

    @property
    def query_string(self) -> str:
        """返回用于签名计算的 URL 编码查询串。"""

        return urlencode(self.params)


def _required(value: str, name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"社区活动请求缺少 {name}")
    return normalized


def _pairs(*values: tuple[str, object]) -> tuple[tuple[str, str], ...]:
    return tuple((name, str(value)) for name, value in values if str(value).strip())


def _headers(
    target: CommunityActivityTarget,
    *values: tuple[str, str],
    include_device: bool = True,
) -> tuple[tuple[str, str], ...]:
    headers = {name: value for name, value in values if value}
    if include_device and target.device_id:
        headers["x-rpc-device_id"] = target.device_id
    if include_device and target.device_fp:
        headers["x-rpc-device_fp"] = target.device_fp
    return tuple(headers.items())


def _skland_headers(target: CommunityActivityTarget) -> tuple[tuple[str, str], ...]:
    return _headers(
        target,
        ("os", "iOS"),
        ("platform", "2"),
        ("manufacturer", "Apple"),
        ("nid", "1"),
        ("vName", "0.1.1"),
        include_device=False,
    )


def _miyoushe_bbs_headers(
    target: CommunityActivityTarget,
    *,
    tool_version: str = "v4.2.2-ys",
    page: str = "v4.2.2-ys_#/ys/daily",
) -> tuple[tuple[str, str], ...]:
    return _headers(
        target,
        ("Accept", "application/json, text/plain, */*"),
        ("Origin", "https://webstatic.mihoyo.com"),
        ("Referer", "https://webstatic.mihoyo.com/"),
        ("x-rpc-client_type", "5"),
        ("x-rpc-tool_version", tool_version),
        ("x-rpc-page", page),
    )


def _miyoushe_widget_headers(
    target: CommunityActivityTarget,
    *,
    client_type: str,
) -> tuple[tuple[str, str], ...]:
    return _headers(
        target,
        ("Accept", "*/*"),
        ("Accept-Encoding", "gzip, deflate, br"),
        ("Accept-Language", "zh-CN,zh-Hans;q=0.9"),
        ("Referer", "https://app.mihoyo.com"),
        ("x-rpc-client_type", client_type),
        ("x-rpc-channel", "appstore"),
    )


def _miyoushe_zzz_headers(
    target: CommunityActivityTarget,
) -> tuple[tuple[str, str], ...]:
    """复用绝区零参考插件的 CN 记录接口请求头。"""

    return _headers(
        target,
        ("Accept", "application/json, text/plain, */*"),
        ("Origin", "https://act.mihoyo.com"),
        ("Referer", "https://act.mihoyo.com/"),
        (
            "User-Agent",
            "Mozilla/5.0 (Linux; Android 12; "
            "MI 8 SE Build/RQ3A.211001.001; wv) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
            "Chrome/111.0.5563.116 Mobile Safari/537.36 "
            "miHoYoBBS/2.73.1",
        ),
        ("x-rpc-app_version", "2.73.1"),
        ("x-rpc-channel", "mihoyo"),
        ("x-rpc-client_type", "2"),
        ("x-rpc-csm_source", "myself"),
        ("x-rpc-sys_version", "12"),
        ("X-Requested-With", "com.mihoyo.hyperion"),
        ("Connection", "keep-alive"),
    )


def build_community_activity_requests(
    target: CommunityActivityTarget,
    *,
    timestamp: int | None = None,
) -> tuple[CommunityActivityRequest, ...]:
    """按已确认的 provider 接口生成一款游戏的请求规格。

    规格不包含 Cookie、Token、Authorization 或请求体；认证签名由调用方的
    provider 适配器在执行请求时注入。原神和星穹铁道保留记录接口失败后的
    Widget/记录接口回退。

    Args:
        target: 当前账号组和游戏角色的脱敏上下文。
        timestamp: 兼容调用方的可选查询时间戳；当前已确认的森空岛请求不使用它。

    Returns:
        按优先级排列的单次请求规格。

    Raises:
        ValueError: 目标缺少该 provider 必需的角色字段。
    """

    role_uid = _required(target.role_uid, "角色 UID")
    if target.platform == "森空岛" and target.game == "明日方舟":
        query_timestamp = timestamp if timestamp is not None else int(time.time())
        return (
            CommunityActivityRequest(
                target=target,
                source=f"{SKLAND_BASE_URL}/api/v1/game/player/info",
                method="GET",
                params=_pairs(("uid", role_uid), ("ts", query_timestamp)),
                headers=_skland_headers(target),
                auth_scope="skland",
                signature_profile="skland_widget",
                requires_device_id=False,
            ),
        )

    if target.platform == "森空岛" and target.game == "终末地":
        server = _required(target.server or "1", "终末地 serverId")
        return (
            CommunityActivityRequest(
                target=target,
                source=f"{SKLAND_BASE_URL}/web/v1/game/endfield/card/detail",
                method="GET",
                params=_pairs(
                    ("roleId", role_uid),
                    ("serverId", server),
                    # 已确认成功记录只携带 roleId/serverId；userId 不属于
                    # 当前角色卡合同，不能混入签名查询串。
                ),
                headers=_headers(
                    target,
                    ("Accept", "*/*"),
                    ("Origin", "https://game.skland.com"),
                    ("Referer", "https://game.skland.com/"),
                    ("X-Requested-With", "com.hypergryph.skland"),
                    ("sk-game-role", f"3_{role_uid}_{server}"),
                ),
                auth_scope="skland",
                signature_profile="skland_endfield_web",
                requires_device_id=True,
            ),
        )

    if target.platform != "米游社":
        raise ValueError(f"{target.platform}{target.game}尚未登记活动请求")

    server = _required(target.server, "米游社角色区服")
    role_params = _pairs(("role_id", role_uid), ("server", server))
    if target.game == "原神":
        return (
            CommunityActivityRequest(
                target=target,
                source=(
                    f"{MIYOUSHE_RECORD_BASE_URL}"
                    "/game_record/app/genshin/api/dailyNote"
                ),
                method="GET",
                params=role_params,
                headers=_miyoushe_bbs_headers(target),
                auth_scope="miyoushe",
                signature_profile="miyoushe_params",
                requires_ds=True,
                requires_device_id=True,
                requires_device_fingerprint=True,
            ),
            CommunityActivityRequest(
                target=target,
                source=(
                    f"{MIYOUSHE_RECORD_BASE_URL}"
                    "/game_record/genshin/aapi/widget/v2"
                ),
                method="GET",
                headers=_miyoushe_widget_headers(target, client_type="1"),
                auth_scope="miyoushe",
                signature_profile="miyoushe_ios",
                requires_ds=True,
                requires_device_id=True,
                requires_device_fingerprint=True,
            ),
        )

    if target.game == "星穹铁道":
        return (
            CommunityActivityRequest(
                target=target,
                source=(
                    f"{MIYOUSHE_RECORD_BASE_URL}"
                    "/game_record/app/hkrpg/aapi/widget"
                ),
                method="GET",
                headers=_miyoushe_widget_headers(target, client_type="2"),
                auth_scope="miyoushe",
                signature_profile="miyoushe_data",
                requires_ds=True,
                requires_device_id=False,
                requires_device_fingerprint=False,
            ),
            CommunityActivityRequest(
                target=target,
                source=(
                    f"{MIYOUSHE_RECORD_BASE_URL}"
                    "/game_record/app/hkrpg/api/note"
                ),
                method="GET",
                params=role_params,
                headers=_miyoushe_bbs_headers(
                    target,
                    tool_version="v4.51.1",
                    page="v4.51.1_#/rpg",
                ),
                auth_scope="miyoushe",
                signature_profile="miyoushe_params",
                requires_ds=True,
                requires_device_id=True,
                requires_device_fingerprint=True,
            ),
        )

    if target.game == "绝区零":
        return (
            CommunityActivityRequest(
                target=target,
                source=(
                    f"{MIYOUSHE_RECORD_BASE_URL}"
                    "/event/game_record_zzz/api/zzz/note"
                ),
                method="GET",
                params=role_params,
                headers=_miyoushe_zzz_headers(target),
                auth_scope="miyoushe",
                signature_profile="miyoushe_params",
                requires_ds=True,
                requires_device_id=True,
                requires_device_fingerprint=True,
            ),
        )

    raise ValueError(f"米游社{target.game}尚未登记活动请求")


def _failed_snapshot(
    target: CommunityActivityTarget,
    *,
    status: ActivityState,
    reason: str,
    source: str = "",
) -> CommunityActivitySnapshot:
    return CommunityActivitySnapshot(
        account=target.account_name,
        account_uid=target.account_uid,
        game=target.game,
        platform=target.platform,
        status=status,
        reason=reason,
        updated_at=datetime.now(tz=UTC8).isoformat(),
        role_name=target.role_name,
        role_uid=target.role_uid,
        server=target.server,
        source=source,
    )


def _transport_failure(
    error: Exception,
) -> tuple[ActivityState, str]:
    if isinstance(error, CommunityActivityTransportError):
        return error.status, error.reason
    if isinstance(error, asyncio.TimeoutError):
        return "failed", "社区活动接口请求超时"
    return "failed", "社区活动接口请求失败"


async def _collect_one(
    target: CommunityActivityTarget,
    requester: ActivityRequester,
    *,
    semaphore: asyncio.Semaphore,
    timestamp: int | None,
) -> CommunityActivitySnapshot:
    async with semaphore:
        try:
            requests = build_community_activity_requests(target, timestamp=timestamp)
        except (ValueError, CommunityActivityTransportError) as exc:
            if isinstance(exc, CommunityActivityTransportError):
                status, reason = exc.status, exc.reason
            else:
                status, reason = "unavailable", str(exc)
            return _failed_snapshot(
                target,
                status=status,
                reason=reason,
            )

        last_snapshot: CommunityActivitySnapshot | None = None
        for request in requests:
            try:
                payload = await asyncio.wait_for(
                    requester(request),
                    timeout=request.timeout,
                )
                snapshot = parse_activity_snapshot(
                    payload,
                    account_uid=target.account_uid,
                    account_name=target.account_name,
                    platform=target.platform,
                    game=target.game,
                    role=target.role_metadata(),
                )
            except Exception as exc:
                status, reason = _transport_failure(exc)
                snapshot = _failed_snapshot(
                    target,
                    status=status,
                    reason=reason,
                    source=request.source,
                )

            if snapshot.status == "success" and snapshot.source != request.source:
                snapshot = replace(snapshot, source=request.source)
            if last_snapshot is None or _activity_failure_priority(
                snapshot.status
            ) >= _activity_failure_priority(last_snapshot.status):
                last_snapshot = snapshot
            if snapshot.status == "success":
                return snapshot

        return last_snapshot or _failed_snapshot(
            target,
            status="failed",
            reason="社区活动接口未返回结果",
        )


def _activity_failure_priority(status: ActivityState) -> int:
    """回退时保留更具体的受限/不可用原因。"""

    return {
        "limited": 3,
        "unavailable": 2,
        "failed": 1,
        "empty": 0,
        "success": 4,
    }.get(status, 1)


async def collect_community_activity(
    targets: Iterable[CommunityActivityTarget],
    requester: ActivityRequester,
    *,
    max_concurrency: int = 4,
    timestamp: int | None = None,
) -> tuple[CommunityActivitySnapshot, ...]:
    """独立并发查询多款游戏，保证单款失败不取消其他游戏。

    该函数只使用本地活动查询 semaphore，不获取签到锁、不调用签到入口，也不
    负责保存凭据。调用方若需要防止重复点击，应在 `community_activity_flow()`
    边界内调用本函数。

    Args:
        targets: 待查询的账号/角色集合。
        requester: provider 适配器提供的异步请求函数；认证值只能在其内部注入。
        max_concurrency: 活动查询自身的并发上限。
        timestamp: 传给森空岛 Widget 的可选固定时间戳。

    Returns:
        与输入顺序一致的独立游戏快照。

    Raises:
        ValueError: 并发上限小于 1。
    """

    if max_concurrency < 1:
        raise ValueError("社区活动查询并发上限必须大于 0")

    target_list = tuple(targets)
    semaphore = asyncio.Semaphore(max_concurrency)
    return tuple(
        await asyncio.gather(
            *(
                _collect_one(
                    target,
                    requester,
                    semaphore=semaphore,
                    timestamp=timestamp,
                )
                for target in target_list
            )
        )
    )
