#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file incorporates protocol references covered by the following
#   copyright and permission notice:
#
#       nonebot-plugin-mystool Copyright © 2023-2025 Ljzd-PRO
#       https://github.com/Ljzd-PRO/nonebot-plugin-mystool

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


"""米游社米游币每日任务，复用平台层准备好的 Cookie 和设备身份。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import string
import time
from collections.abc import Mapping
from dataclasses import dataclass

import httpx

from app.core import Config
from app.utils.logger import get_logger
from app.utils.security import format_exception_reason

from .community_contract import CommunitySignResult


logger = get_logger("米游币每日任务")

_SIGN_URL = "https://bbs-api.mihoyo.com/apihub/app/api/signIn"
_POSTS_URL = (
    "https://bbs-api.miyoushe.com/post/api/feeds/posts"
    "?fresh_action=1&gids=5&is_first_initialize=false&last_id="
)
_READ_URL = "https://bbs-api.miyoushe.com/post/api/getPostFull?post_id={}"
_LIKE_URL = "https://bbs-api.miyoushe.com/post/api/post/upvote"
_SHARE_URL = (
    "https://bbs-api.miyoushe.com/apihub/api/getShareConf"
    "?entity_id={}&entity_type=1"
)
_MISSIONS_URL = (
    "https://api-takumi.mihoyo.com/apihub/wapi/getMissions?point_sn=myb"
)
_MISSION_STATE_URL = (
    "https://api-takumi.mihoyo.com/apihub/wapi/getUserMissionsState?point_sn=myb"
)

_SALT_ANDROID = "BIPaooxbWZW02fGHZL1If26mYCljPgst"
_SALT_DATA = "t0qEgfub6cvueAPgR5m9aQWWVciEer7v"
_TASK_ORDER = (
    "continuous_sign",
    "view_post_0",
    "post_up_0",
    "share_post_0",
)
_TASK_LABELS = {
    "continuous_sign": "讨论区签到",
    "view_post_0": "阅读帖子",
    "post_up_0": "点赞帖子",
    "share_post_0": "分享帖子",
}


@dataclass(frozen=True)
class MiyousheCoinMission:
    """服务端已确认的单项米游币任务进度。"""

    key: str
    name: str
    points: int
    threshold: int
    happened_times: int

    @property
    def remaining(self) -> int:
        """返回本轮仍需完成的次数。"""

        return max(0, self.threshold - self.happened_times)


@dataclass(frozen=True)
class _MiyoushePost:
    post_id: str
    liked: bool


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"米游币任务字段 {field} 格式无效")
    return value


def build_miyoushe_coin_task_plan(
    missions: object,
    states: object,
) -> tuple[MiyousheCoinMission, ...]:
    """按白名单合并任务定义与账号进度，未知任务不会被执行。"""

    if not isinstance(missions, list) or not isinstance(states, list):
        raise ValueError("米游币任务列表格式无效")

    progress: dict[str, int] = {}
    for raw_state in states:
        if not isinstance(raw_state, Mapping):
            continue
        key = raw_state.get("mission_key")
        if key not in _TASK_ORDER:
            continue
        progress[str(key)] = _nonnegative_int(
            raw_state.get("happened_times"),
            f"{key}.happened_times",
        )

    definitions: dict[str, MiyousheCoinMission] = {}
    for raw_mission in missions:
        if not isinstance(raw_mission, Mapping):
            continue
        key = raw_mission.get("mission_key")
        if key not in _TASK_ORDER or key in definitions:
            continue
        key_text = str(key)
        threshold = _nonnegative_int(
            raw_mission.get("threshold"),
            f"{key_text}.threshold",
        )
        if threshold == 0:
            raise ValueError(f"米游币任务 {key_text} 的目标次数无效")
        name = raw_mission.get("name")
        definitions[key_text] = MiyousheCoinMission(
            key=key_text,
            name=str(name).strip() if isinstance(name, str) else _TASK_LABELS[key_text],
            points=_nonnegative_int(
                raw_mission.get("points"),
                f"{key_text}.points",
            ),
            threshold=threshold,
            happened_times=progress.get(key_text, 0),
        )

    plan = tuple(definitions[key] for key in _TASK_ORDER if key in definitions)
    if not plan:
        raise ValueError("未发现已确认的米游币每日任务")
    return plan


def _android_ds() -> str:
    timestamp = str(int(time.time()))
    nonce = "".join(random.sample(string.ascii_lowercase + string.digits, 6))
    digest = hashlib.md5(
        f"salt={_SALT_ANDROID}&t={timestamp}&r={nonce}".encode()
    ).hexdigest()
    return f"{timestamp},{nonce},{digest}"


def _data_ds(body: str) -> str:
    timestamp = str(int(time.time()))
    nonce = str(random.randint(100000, 200000))
    digest = hashlib.md5(
        f"salt={_SALT_DATA}&t={timestamp}&r={nonce}&b={body}&q=".encode()
    ).hexdigest()
    return f"{timestamp},{nonce},{digest}"


def _android_headers(device_id: str, *, ds: str = "") -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip",
        "Connection": "Keep-Alive",
        "Content-Type": "application/json;charset=utf-8",
        "Referer": "https://app.mihoyo.com",
        "User-Agent": "okhttp/4.9.3",
        "x-rpc-app_version": "2.63.1",
        "x-rpc-channel": "miyousheluodi",
        "x-rpc-client_type": "2",
        "x-rpc-device_id": device_id,
        "x-rpc-device_model": "MI 8 SE",
        "x-rpc-device_name": "Xiaomi MI 8 SE",
        "x-rpc-sys_version": "11",
    }
    if ds:
        headers["DS"] = ds
    return headers


def _mission_headers() -> dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "zh-CN,zh-Hans;q=0.9",
        "Connection": "keep-alive",
        "Origin": "https://webstatic.mihoyo.com",
        "Referer": "https://webstatic.mihoyo.com/",
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 15_4 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) miHoYoBBS/2.55.1"
        ),
    }


def _post_headers(device_id: str) -> dict[str, str]:
    return {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "zh-CN,zh-Hans;q=0.9",
        "Connection": "keep-alive",
        "Referer": "https://app.mihoyo.com",
        "User-Agent": "Hyperion/275 CFNetwork/1402.0.8 Darwin/22.2.0",
        "x-rpc-app_version": "2.63.1",
        "x-rpc-channel": "appstore",
        "x-rpc-client_type": "1",
        "x-rpc-device_id": device_id,
        "x-rpc-device_name": "iPhone",
        "x-rpc-sys_version": "16.2",
    }


def _response_data(payload: Mapping[str, object], stage: str) -> Mapping[str, object]:
    retcode = payload.get("retcode", 0)
    if retcode in (-100, 10001):
        raise ValueError("米游社登录凭据已失效")
    if retcode == 1034:
        raise ValueError("米游币任务触发人机验证")
    if retcode not in (0, None):
        code = retcode if isinstance(retcode, (int, str)) else "未知"
        raise ValueError(f"{stage}失败（错误码 {code}）")
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise ValueError(f"{stage}返回数据格式无效")
    return data


async def _request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: Mapping[str, str],
    cookies: Mapping[str, str],
    content: str | None = None,
    json_body: Mapping[str, object] | None = None,
) -> Mapping[str, object]:
    response = await client.request(
        method,
        url,
        headers=dict(headers),
        cookies=dict(cookies),
        content=content,
        json=dict(json_body) if json_body is not None else None,
        timeout=30.0,
    )
    text = response.text.strip()
    if not text:
        raise ValueError("米游币接口返回空响应，疑似被风控")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("米游币接口返回非 JSON 内容，疑似被风控") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("米游币接口返回数据格式无效")
    return payload


async def _load_task_state(
    client: httpx.AsyncClient,
    cookies: Mapping[str, str],
) -> tuple[tuple[MiyousheCoinMission, ...], int]:
    missions_payload = await _request_json(
        client,
        "GET",
        _MISSIONS_URL,
        headers=_mission_headers(),
        cookies=cookies,
    )
    missions_data = _response_data(missions_payload, "获取米游币任务定义")
    state_payload = await _request_json(
        client,
        "GET",
        _MISSION_STATE_URL,
        headers=_mission_headers(),
        cookies=cookies,
    )
    state_data = _response_data(state_payload, "获取米游币任务状态")
    plan = build_miyoushe_coin_task_plan(
        missions_data.get("missions"),
        state_data.get("states"),
    )
    total_points = _nonnegative_int(state_data.get("total_points"), "total_points")
    return plan, total_points


async def _load_posts(
    client: httpx.AsyncClient,
    cookies: Mapping[str, str],
    device_id: str,
) -> tuple[_MiyoushePost, ...]:
    payload = await _request_json(
        client,
        "GET",
        _POSTS_URL,
        headers=_post_headers(device_id),
        cookies=cookies,
    )
    data = _response_data(payload, "获取米游社帖子")
    raw_posts = data.get("list")
    if not isinstance(raw_posts, list):
        raise ValueError("米游社帖子列表格式无效")

    posts = []
    for raw_item in raw_posts:
        if not isinstance(raw_item, Mapping):
            continue
        post = raw_item.get("post")
        if not isinstance(post, Mapping):
            continue
        post_id = post.get("post_id")
        if not isinstance(post_id, (str, int)) or not str(post_id).strip():
            continue
        operation = raw_item.get("self_operation")
        attitude = operation.get("attitude") if isinstance(operation, Mapping) else 0
        posts.append(_MiyoushePost(str(post_id), attitude not in (0, None, False)))
    if not posts:
        raise ValueError("米游社综合分区没有可用帖子")
    return tuple(posts)


async def _wait_task_interval() -> None:
    await asyncio.sleep(random.uniform(1.0, 2.0))


async def _run_sign(
    client: httpx.AsyncClient,
    cookies: Mapping[str, str],
    device_id: str,
) -> None:
    body = json.dumps({"gids": "5"}, separators=(",", ":"))
    payload = await _request_json(
        client,
        "POST",
        _SIGN_URL,
        headers=_android_headers(device_id, ds=_data_ds(body)),
        cookies=cookies,
        content=body,
    )
    if payload.get("retcode") == 1008:
        return
    _response_data(payload, "米游社讨论区签到")


async def _run_reads(
    client: httpx.AsyncClient,
    cookies: Mapping[str, str],
    device_id: str,
    posts: tuple[_MiyoushePost, ...],
    count: int,
) -> None:
    if len(posts) < count:
        raise ValueError("米游社综合分区可阅读帖子数量不足")
    for index, post in enumerate(posts[:count]):
        payload = await _request_json(
            client,
            "GET",
            _READ_URL.format(post.post_id),
            headers=_android_headers(device_id, ds=_android_ds()),
            cookies=cookies,
        )
        _response_data(payload, "阅读米游社帖子")
        if index + 1 < count:
            await _wait_task_interval()


async def _run_likes(
    client: httpx.AsyncClient,
    cookies: Mapping[str, str],
    device_id: str,
    posts: tuple[_MiyoushePost, ...],
    count: int,
) -> None:
    candidates = tuple(post for post in posts if not post.liked)
    if len(candidates) < count:
        raise ValueError("米游社综合分区可点赞帖子数量不足")
    for index, post in enumerate(candidates[:count]):
        payload = await _request_json(
            client,
            "POST",
            _LIKE_URL,
            headers=_android_headers(device_id, ds=_android_ds()),
            cookies=cookies,
            json_body={"is_cancel": False, "post_id": post.post_id},
        )
        _response_data(payload, "点赞米游社帖子")
        if index + 1 < count:
            await _wait_task_interval()


async def _run_share(
    client: httpx.AsyncClient,
    cookies: Mapping[str, str],
    device_id: str,
    post: _MiyoushePost,
) -> None:
    payload = await _request_json(
        client,
        "GET",
        _SHARE_URL.format(post.post_id),
        headers=_android_headers(device_id, ds=_android_ds()),
        cookies=cookies,
    )
    _response_data(payload, "分享米游社帖子")


def _result(
    account_name: str,
    account_uid: str,
    *,
    status: str,
    reward: str = "",
    reason: str = "",
) -> dict[str, object]:
    return CommunitySignResult(
        account=f"{account_name or account_uid}/米游社",
        account_uid=account_uid,
        game="米游币任务",
        platform="米游社",
        status=status,
        reward=reward,
        reason=reason,
    ).to_legacy()


async def run_miyoushe_coin_tasks(
    cookies: Mapping[str, str],
    *,
    account_name: str = "",
    account_uid: str,
    device_id: str,
    proxy: str | None = None,
) -> dict[str, object]:
    """按账号级服务端进度完成四类已确认米游币任务。"""

    resolved_proxy = proxy if proxy is not None else Config.proxy
    try:
        async with httpx.AsyncClient(
            proxy=resolved_proxy,
            trust_env=False,
        ) as client:
            plan, points_before = await _load_task_state(client, cookies)
            pending = tuple(task for task in plan if task.remaining)
            if not pending:
                return _result(
                    account_name,
                    account_uid,
                    status="已签到",
                    reward="新增 0 米游币",
                )

            posts: tuple[_MiyoushePost, ...] | None = None
            for task in pending:
                if task.key == "continuous_sign":
                    await _run_sign(client, cookies, device_id)
                else:
                    if posts is None:
                        posts = await _load_posts(client, cookies, device_id)
                    if task.key == "view_post_0":
                        await _run_reads(
                            client,
                            cookies,
                            device_id,
                            posts,
                            task.remaining,
                        )
                    elif task.key == "post_up_0":
                        await _run_likes(
                            client,
                            cookies,
                            device_id,
                            posts,
                            task.remaining,
                        )
                    elif task.key == "share_post_0":
                        await _run_share(client, cookies, device_id, posts[0])
                await _wait_task_interval()

            final_plan, points_after = await _load_task_state(client, cookies)
            incomplete = tuple(task.name for task in final_plan if task.remaining)
            gained = max(0, points_after - points_before)
            if incomplete:
                return _result(
                    account_name,
                    account_uid,
                    status="失败",
                    reward=f"新增 {gained} 米游币" if gained else "",
                    reason=f"米游币任务未全部完成：{'、'.join(incomplete)}",
                )
            return _result(
                account_name,
                account_uid,
                status="成功",
                reward=f"新增 {gained} 米游币",
            )
    except Exception as error:
        expected = isinstance(
            error,
            (ValueError, httpx.HTTPError, TimeoutError, ConnectionError),
        )
        reason = format_exception_reason(
            error,
            stage="米游币任务失败",
            include_message=expected,
        )
        if expected:
            logger.warning(reason)
        else:
            logger.exception("米游币任务程序异常")
        return _result(account_name, account_uid, status="失败", reason=reason)
