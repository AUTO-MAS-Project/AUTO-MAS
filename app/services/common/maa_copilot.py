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

"""作业站公开数据与快照缓存；不接触账号凭据或 MAA 私有配置。"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import logging
import math
import re
import time
from pathlib import Path
from typing import Any, Callable, Literal
from urllib.parse import parse_qs, urlparse

import httpx

CopilotScope = Literal["all", "author", "set", "copilot"]
API_BASE = "https://prts.maa.plus"
SNAPSHOT_URLS = (
    "https://data.auto-mas.top/api/v1/files/auto-mas/Client/maa-copilot-json-gz/download",
    "https://raw.githubusercontent.com/AUTO-MAS-Project/AUTO-MAS-Copilot-Data/"
    "refs/heads/data/maa-copilot.json.gz",
)
CACHE_TTL = 86400
PAGE_SIZE = 50
SNAPSHOT_VERSION = 2
MODULE_ORDER_URL = (
    "https://raw.githubusercontent.com/ZOOT-Plus/zoot-plus-frontend/"
    "dev/src/models/generated/operators.json"
)


def normalize_source(scope: CopilotScope, query: str) -> str:
    """只提取编号，不请求用户提供的任意 URL。"""
    if scope == "all":
        return ""
    query = query.strip()
    if query.isdecimal() and int(query) > 0:
        return str(int(query))
    match = re.fullmatch(r"(maa|prts)://(set/|s)?([0-9]+)", query)
    if match and scope in {"set", "copilot"} and int(match[3]) > 0:
        scheme, marker, identifier = match.groups()
        if marker and scope != "set":
            raise ValueError("这是作业集分享码，请切换到作业集范围")
        if scheme == "prts" and not marker and scope != "copilot":
            raise ValueError("这是单份作业分享码，请切换到单个作业范围")
        return str(int(identifier))
    parsed = urlparse(query)
    if parsed.scheme == "https" and parsed.hostname in {"prts.plus", "www.prts.plus"}:
        # 官网列表通过 op / opset 参数打开详情，也兼容独立详情页和旧链接。
        keys = {
            "set": ("opset", "id"),
            "copilot": ("op", "id"),
            "author": ("userId", "uploaderId", "id"),
        }[scope]
        for key in keys:
            value = parse_qs(parsed.query).get(key, [""])[0]
            if value.isdecimal() and int(value) > 0:
                return str(int(value))
        parts = parsed.path.strip("/").split("/")
        if parts and parts[-1].isdecimal() and int(parts[-1]) > 0:
            return str(int(parts[-1]))
    raise ValueError("请输入作业站编号或有效的作业站分享链接")


def normalize_assignment(record: dict[str, Any]) -> dict[str, Any]:
    """快照只保存分析所需字段，不保存战斗动作或评论。"""
    try:
        content = record.get("content", {})
        content = json.loads(content) if isinstance(content, str) else content
        if not isinstance(content, dict):
            content = {}
    except ValueError:
        content = {}

    def slots(raw: object) -> list[dict[str, Any]]:
        return (
            [
                {
                    k: item[k]
                    for k in ("name", "role", "skill", "requirements")
                    if k in item
                }
                for item in raw
                if isinstance(item, dict)
            ]
            if isinstance(raw, list)
            else []
        )

    doc = content.get("doc")
    doc = doc if isinstance(doc, dict) else {}
    groups = content.get("groups")
    groups = groups if isinstance(groups, list) else []
    return {
        "id": int(record["id"]),
        "title": str(doc.get("title") or content.get("stage_name") or record["id"]),
        "stage": str(content.get("stage_name") or ""),
        "author": str(record.get("uploader") or ""),
        "authorId": str(record.get("uploader_id") or ""),
        "type": str(record.get("type") or "PRTS"),
        "protocolVersion": content.get("version"),
        "opers": slots(content.get("opers")),
        "groups": [slots(g.get("opers")) for g in groups if isinstance(g, dict)],
    }


async def attach_module_orders(
    client: httpx.AsyncClient, assignments: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """v2 模组编号是干员模组列表下标，将官网迁移所用目录随快照保存。"""
    legacy = [
        job
        for job in assignments
        if job["protocolVersion"] == 2
        and any(
            isinstance(slot.get("requirements"), dict)
            and type(slot["requirements"].get("module")) is int
            and slot["requirements"]["module"] > 0
            for slot in job["opers"] + [s for g in job["groups"] for s in g]
        )
    ]
    if not legacy:
        return assignments
    response = await client.get(MODULE_ORDER_URL)
    response.raise_for_status()
    operators = response.json().get("OPERATORS")
    if not isinstance(operators, list):
        raise ValueError("作业站旧版模组目录格式不兼容")
    by_name: dict[str, list[dict[str, Any]]] = {}
    for op in operators:
        if (
            isinstance(op, dict)
            and op.get("id")
            and isinstance(op.get("modules"), list)
        ):
            by_name.setdefault(op.get("name", ""), []).append(op)
    for job in legacy:
        names = {
            slot.get("name")
            for slot in job["opers"] + [s for g in job["groups"] for s in g]
        }
        job["moduleOrders"] = {
            op["id"]: op["modules"] for name in names for op in by_name.get(name, [])
        }
    return assignments


async def request_data(client: httpx.AsyncClient, path: str, **params: Any) -> Any:
    """仅访问固定作业站，限流或短暂故障时有界重试。"""
    for attempt in range(3):
        try:
            response = await client.get(f"{API_BASE}{path}", params=params)
            response.raise_for_status()
            payload = response.json()
            if payload.get("status_code") != 200 or payload.get("data") is None:
                raise ValueError("作业站未返回有效数据，请稍后重试")
            return payload["data"]
        except (httpx.HTTPError, ValueError):
            if attempt == 2:
                raise
            await asyncio.sleep(2**attempt)


async def fetch_assignments(
    client: httpx.AsyncClient,
    *,
    scope: CopilotScope = "all",
    query: str = "",
    progress: Callable[[int, int], None] | None = None,
) -> list[dict[str, Any]]:
    """完整翻页，不设固定页数上限；查询返回的元数据已包含干员要求。"""
    params: dict[str, Any] = {"limit": PAGE_SIZE, "desc": True, "orderBy": "id"}
    if scope == "author":
        params["uploaderId"] = query
    elif scope == "set":
        group = await request_data(client, "/set/get", id=query)
        ids = group.get("copilot_ids") or []
        if not ids:
            return []
        # 大作业集拆批，避免长 URL；最终去重仍按作业编号。
        entries = []
        for offset in range(0, len(ids), PAGE_SIZE):
            data = await request_data(
                client,
                "/copilot/query",
                page=1,
                copilotIds=",".join(map(str, ids[offset : offset + PAGE_SIZE])),
                **params,
            )
            entries.extend(normalize_assignment(item) for item in data["data"])
            if progress:
                progress(len(entries), len(ids))
        return await attach_module_orders(
            client, list({item["id"]: item for item in entries}.values())
        )
    elif scope == "copilot":
        params["copilotIds"] = query

    if scope == "copilot":
        data = await request_data(client, "/copilot/query", page=1, **params)
        return await attach_module_orders(
            client, [normalize_assignment(item) for item in data["data"]]
        )

    # 先记录最新编号与总数，再正序翻页。之后的新投稿不会挤动已有页面。
    # 删除等变化仍可能令 offset 跳行，完整性不符时重试，绝不返回半份数据。
    for attempt in range(3):
        anchor = await request_data(client, "/copilot/query", page=1, **params)
        total = int(anchor["total"])
        if not total and not anchor["data"]:
            return []
        anchor_ids = {int(item["id"]) for item in anchor["data"]}
        if total < 1 or not anchor_ids:
            raise ValueError("作业站分页数据不完整，请稍后重试")
        upper_id = max(anchor_ids)
        ascending = {**params, "desc": False}
        entries: dict[int, dict[str, Any]] = {}
        last_page = math.ceil(total / PAGE_SIZE)
        for page in range(1, last_page + 1, 3):
            pages = await asyncio.gather(
                *(
                    request_data(client, "/copilot/query", page=i, **ascending)
                    for i in range(page, min(page + 3, last_page + 1))
                )
            )
            for result in pages:
                for item in result["data"]:
                    if int(item["id"]) <= upper_id:
                        entries[int(item["id"])] = normalize_assignment(item)
            if progress:
                progress(len(entries), total)
            await asyncio.sleep(0.15)
        if len(entries) == total and anchor_ids <= entries.keys():
            return await attach_module_orders(
                client,
                sorted(entries.values(), key=lambda item: item["id"], reverse=True),
            )
        if attempt < 2:
            await asyncio.sleep(2**attempt)
    raise ValueError("作业站分页发生变化或数据不完整，请重新同步；已有缓存未覆盖")


def read_snapshot(content: bytes) -> dict[str, Any]:
    payload = json.loads(gzip.decompress(content))
    if payload.get("version") != SNAPSHOT_VERSION or not isinstance(
        payload.get("assignments"), list
    ):
        raise ValueError("作业快照格式不兼容，请重新同步")
    if len(payload["assignments"]) != payload.get("count"):
        raise ValueError("作业快照不完整，请重新同步")
    return payload


def write_snapshot(
    path: Path,
    assignments: list[dict[str, Any]],
    *,
    updated_at: int | None = None,
    data_source: Literal["data-center", "github", "copilot", "unknown"] = "unknown",
) -> dict[str, Any]:
    payload = {
        "version": SNAPSHOT_VERSION,
        "updatedAt": int(time.time()) if updated_at is None else updated_at,
        "checkedAt": int(time.time()),
        "dataSource": data_source,
        "count": len(assignments),
        "assignments": assignments,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(
        gzip.compress(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(),
            mtime=0,
        )
    )
    temporary.replace(path)
    return payload


class CopilotRepository:
    """公开数据的共享后台同步；失败保留上一份完整缓存，半成品不参与分析。"""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.snapshots: dict[str, dict[str, Any]] = {}
        self.states: dict[str, dict[str, Any]] = {}
        self.tasks: dict[str, asyncio.Task[None]] = {}

    def key(self, scope: CopilotScope, query: str) -> str:
        return f"{scope}-{hashlib.sha256(query.encode()).hexdigest()[:16]}"

    def cached(self, scope: CopilotScope, query: str) -> dict[str, Any] | None:
        key = self.key(scope, query)
        if key not in self.snapshots:
            path = self.cache_dir / f"{key}.json.gz"
            if path.exists():
                try:
                    self.snapshots[key] = read_snapshot(path.read_bytes())
                except (ValueError, OSError, EOFError):
                    # 损坏缓存不可用；下一次同步完整替换，不伪装成空数据。
                    self.states.setdefault(key, {})["error"] = (
                        "本地作业缓存损坏，请重新同步"
                    )
        return self.snapshots.get(key)

    def status(self, scope: CopilotScope, query: str) -> dict[str, Any]:
        cached = self.cached(scope, query)
        state = self.states.get(self.key(scope, query), {})
        return {
            "running": state.get("running", False),
            "loaded": state.get("loaded", 0),
            "total": state.get("total", 0),
            "count": cached["count"] if cached else 0,
            "updatedAt": cached["updatedAt"] if cached else 0,
            "downloadedAt": cached.get("checkedAt", 0) if cached else 0,
            "dataSource": cached.get("dataSource", "unknown") if cached else "unknown",
            "available": cached is not None,
            "error": state.get("error", ""),
        }

    async def load(
        self, scope: CopilotScope, query: str, *, refresh: bool, proxy: str | None
    ) -> dict[str, Any]:
        key = self.key(scope, query)
        cached = self.cached(scope, query)
        if key not in self.tasks or self.tasks[key].done():
            if (
                refresh
                or cached is None
                or time.time() - cached.get("checkedAt", cached["updatedAt"])
                > CACHE_TTL
            ):
                self.states[key] = {
                    "running": True,
                    "loaded": 0,
                    "total": 0,
                    "error": "",
                }
                self.tasks[key] = asyncio.create_task(
                    self._sync(scope, query, proxy=proxy, use_snapshot=not refresh)
                )
        return self.status(scope, query)

    async def _sync(
        self, scope: CopilotScope, query: str, *, proxy: str | None, use_snapshot: bool
    ) -> None:
        key = self.key(scope, query)
        state = self.states[key]
        try:
            async with httpx.AsyncClient(
                proxy=proxy or None, timeout=40, follow_redirects=True
            ) as client:
                payload = None
                data_source = "copilot"
                if scope == "all" and use_snapshot:
                    for snapshot_url in SNAPSHOT_URLS:
                        try:
                            response = await client.get(snapshot_url)
                            response.raise_for_status()
                            candidate = read_snapshot(response.content)
                            if (
                                candidate["count"] > 0
                                and time.time() - candidate["updatedAt"] < CACHE_TTL * 3
                            ):
                                payload = candidate
                                data_source = (
                                    "data-center"
                                    if snapshot_url == SNAPSHOT_URLS[0]
                                    else "github"
                                )
                                break
                        except (httpx.HTTPError, ValueError, OSError, EOFError):
                            pass  # 下载站不可达时尝试 GitHub，再回退完整在线拉取。
                if payload is None:

                    def progress(loaded: int, total: int) -> None:
                        state.update(loaded=loaded, total=total)

                    entries = await fetch_assignments(
                        client, scope=scope, query=query, progress=progress
                    )
                    if scope == "all" and not entries:
                        raise ValueError("全站数据为空，拒绝覆盖完整缓存")
                    payload = {
                        "version": SNAPSHOT_VERSION,
                        "updatedAt": int(time.time()),
                        "count": len(entries),
                        "assignments": entries,
                    }
                path = self.cache_dir / f"{key}.json.gz"
                # 压缩与写盘不阻塞 HTTP 事件循环。
                payload = await asyncio.to_thread(
                    write_snapshot,
                    path,
                    payload["assignments"],
                    updated_at=payload["updatedAt"],
                    data_source=data_source,
                )
                self.snapshots[key] = payload
                state.update(loaded=payload["count"], total=payload["count"], error="")
        except Exception as exc:
            logging.getLogger("作业站同步").warning(
                "公开作业数据同步失败: %s", type(exc).__name__
            )
            state["error"] = "作业同步失败，请检查网络后重新同步；已有完整缓存仍可分析"
        finally:
            state["running"] = False
