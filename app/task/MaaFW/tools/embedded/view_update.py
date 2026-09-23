#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""MFW 项目更新的宿主侧编排：谱系锁 → 组同步 → 核心更新（下载 / 构建 / 预检 / 登记）→
切触发脚本 → 同步同组空闲脚本 → 它们的运行环境确认。

组 = 谱系 + ``Update.Channel``，同组永远挂同一个载荷。运行前 / 运行后自动更新
（``embedded_manager``）与手动 ``/maafw/update`` 共用这里；两边只在「触发脚本的视图
预约是谁拿着」「核心更新怎么调」上不同（``core_call`` 由调用方给）。

遍历 ``Config.ScriptConfig`` 只能在事件循环线程上做：同组候选（``GroupMember``）由
调用方算好传进来，这里只收列表。
"""

from __future__ import annotations

import asyncio
import dataclasses
import threading
import weakref
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.task.MaaFW.tools.core.automas_maafw_project_update import payloads
from app.task.MaaFW.tools.core.automas_maafw_project_update.blob_store import (
    RuntimeBlobStore,
)
from app.task.MaaFW.tools.core.automas_maafw_project_update.precheck_memo import (
    precheck_memo_path,
)
from app.task.MaaFW.tools.core.automas_maafw_project_update.updater import (
    MaaFWProjectUpdateError,
)
from app.task.MaaFW.tools.embedded.embedded_project import (
    SKIP_UNADOPTED,
    STAGING_DIR_NAME,
    EmbeddedProjectError,
    GroupMember,
    PropagationResult,
    ViewResult,
    embedded_project_dir,
    embedded_projects_root,
    payloads_root,
    propagate_payload,
    read_view_marker,
    switch_view,
)
from app.task.MaaFW.tools.embedded.project_path import (
    release_project_path_sync,
    try_reserve_project_path_sync,
)
from app.utils import get_logger

logger = get_logger("MFW 版本同步")

# 进程内的谱系锁：同一项目的两次更新串行，后者拿到锁时先同步到组、再查一次远端就会
# 发现「已是最新」，不再下载。只有一个后端进程写 data/mfw，worker 子进程不更新项目，
# 所以进程内锁就够（DurableFileLock 按线程重入，跨 await 持有时换了工作线程会失效）。
_LINEAGE_LOCKS: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, dict[str, asyncio.Lock]
] = weakref.WeakKeyDictionary()

CoreCall = Callable[
    [
        Path,
        payloads.PayloadTarget,
        Callable[[payloads.RegisterResult], Awaitable[None]],
    ],
    Awaitable[Any],
]


def lineage_update_lock(lineage: str) -> asyncio.Lock:
    """该谱系的更新锁（按事件循环分表：``asyncio.Lock`` 绑定创建它的循环）。"""

    locks = _LINEAGE_LOCKS.setdefault(asyncio.get_running_loop(), {})
    lock = locks.get(lineage)
    if lock is None:
        lock = locks[lineage] = asyncio.Lock()
    return lock


def memo_path_factory(lineage: str, base: Path | None = None) -> Callable[[str], Path]:
    """该谱系的预检备忘路径：``.payloads/<谱系>/precheck-<版本>.json``（组共有）。"""

    root = payloads_root(base)
    return lambda version: precheck_memo_path(root, lineage, version)


def payload_target_for(
    script_id: str,
    marker: dict[str, Any],
    channel: str,
    base: Path | None = None,
) -> payloads.PayloadTarget:
    root = payloads_root(base)
    lineage = str(marker["lineage"])
    staging_root = embedded_projects_root(base) / STAGING_DIR_NAME
    staging_root.mkdir(parents=True, exist_ok=True)
    return payloads.PayloadTarget(
        root=root,
        lineage=lineage,
        payload_id=str(marker["payload"]),
        channel=channel,
        by=str(script_id),
        staging_root=staging_root,
        blob_store=RuntimeBlobStore.default(base),
        private_paths=tuple(payloads.private_paths(root, lineage)),
    )


def latest_entry(
    lineage: str, channel: str, base: Path | None = None
) -> dict[str, Any] | None:
    try:
        entry = payloads.latest(payloads_root(base), lineage, channel)
    except payloads.PayloadError:
        return None
    if not entry:
        return None
    try:
        directory = payloads.payload_dir(payloads_root(base), lineage, str(entry["id"]))
    except payloads.PayloadError:
        return None
    return entry if directory.is_dir() else None


def public_source(entry: dict[str, Any] | None) -> str | None:
    """``latest`` 记的来源里对外可说的那部分：更新得来的是 mirrorchyan / github。"""

    source = (entry or {}).get("source") or {}
    if str(source.get("kind") or "") != "update":
        return None
    return str(source.get("ref") or "") or None


def _switch_sync(
    script_id: str,
    payload_id: str,
    lineage: str,
    *,
    reservation_held: bool,
    base: Path | None,
    switched_by: dict[str, Any] | None = None,
) -> ViewResult | None:
    """切一个视图；``reservation_held`` 为假时自己拿预约，拿不到返回 None（本轮不切）。"""

    view = embedded_project_dir(script_id, base)
    key: str | None = None
    if not reservation_held:
        key = try_reserve_project_path_sync(view)
        if key is None:
            return None
    try:
        return switch_view(
            script_id,
            payload_id,
            lineage=lineage,
            base=base,
            switched_by=switched_by,
        )
    finally:
        if key is not None:
            release_project_path_sync(key)


async def sync_view_to_group(
    script_id: str,
    channel: str,
    *,
    reservation_held: bool,
    base: Path | None = None,
) -> ViewResult | None:
    """§3.1 第 9 步：视图挂的载荷 ≠ ``latest[channel]`` 就切过去（升级、被动 pending、
    改渠道后的降级都是这一条）。该渠道还没有载荷就留在原地。返回切换结果，没切为 None。
    """

    view = embedded_project_dir(script_id, base)
    marker = await asyncio.to_thread(read_view_marker, view)
    if marker is None:
        return None
    lineage = str(marker["lineage"])
    entry = await asyncio.to_thread(latest_entry, lineage, channel, base)
    if entry is None or str(entry["id"]) == str(marker["payload"]):
        return None
    return await asyncio.to_thread(
        _switch_sync,
        script_id,
        str(entry["id"]),
        lineage,
        reservation_held=reservation_held,
        base=base,
    )


@dataclass
class ViewUpdateOutcome:
    """一次更新对触发脚本 S 的结果。``updated`` = S 的视图换了版本（组同步或新登记）。"""

    result: Any
    lineage: str
    payload_before: str
    payload_after: str
    version_before: str
    version_after: str
    group_synced: bool = False
    registered_id: str | None = None
    s_skipped_reason: str = ""
    propagation: PropagationResult | None = None
    log_lines: list[str] = field(default_factory=list)

    @property
    def updated(self) -> bool:
        return self.payload_after != self.payload_before


def describe_propagation(
    result: PropagationResult, members: Sequence[GroupMember]
) -> str | None:
    """「已同步 N 个脚本：…；M 个正在运行，跑完后切换」——只进任务 / 更新日志。"""

    names = {
        member.script_id: member.name or member.script_id[:8] for member in members
    }
    parts: list[str] = []
    if result.switched:
        parts.append(
            f"已同步 {len(result.switched)} 个脚本："
            + "、".join(f"「{names.get(sid, sid[:8])}」" for sid in result.switched)
        )
    pending = [
        sid for sid, reason in result.skipped.items() if reason != SKIP_UNADOPTED
    ]
    if pending:
        parts.append(f"{len(pending)} 个正在运行或被占用，下次运行前切换")
    if result.failed:
        parts.append(
            f"{len(result.failed)} 个同步失败（下次运行前再切）："
            + "、".join(f"「{names.get(sid, sid[:8])}」" for sid in result.failed)
        )
    return "；".join(parts) or None


def confirm_environments_in_background(
    members: Iterable[GroupMember], base: Path | None = None
) -> None:
    """被传播切换的脚本各起一个后台线程确认一次运行环境（持各自的视图预约）。

    切换只把文件摆好：``interfaceHash`` / ``requirementsHash`` 一变，isolated_venv 型
    项目的 venv 会整个重建（分钟级、要联网）。不在这里做就会落进它下次运行的 worker 里、
    游戏已经起来了。拿不到预约（它刚好开跑）就不确认——它自己的运行前确认会做。
    """

    for member in members:
        view = embedded_project_dir(member.script_id, base)

        def _run(view: Path = view, member: GroupMember = member) -> None:
            key = try_reserve_project_path_sync(view)
            if key is None:
                return
            try:
                from app.task.MaaFW.embedded_manager import MaaFWEmbeddedManager

                MaaFWEmbeddedManager._prepare_project_environment_sync(
                    view,
                    threading.Event(),
                    lambda line: logger.debug(f"[{member.script_id[:8]}] {line}"),
                    proxy_url=member.proxy_url,
                )
                logger.info(
                    f"脚本「{member.name or member.script_id[:8]}」切换版本后运行环境已确认"
                )
            except Exception as exc:  # noqa: BLE001 - 失败只记日志，运行前还会再备
                logger.warning(
                    f"脚本「{member.name or member.script_id[:8]}」切换版本后运行环境确认失败："
                    f"{exc}"
                )
            finally:
                release_project_path_sync(key)

        threading.Thread(
            target=_run, name=f"maafw-env-confirm:{view.name}", daemon=True
        ).start()


async def run_view_update(
    script_id: str,
    *,
    channel: str,
    members: Sequence[GroupMember],
    reservation_held: bool,
    send_log: Callable[[str], None],
    core_call: CoreCall,
    script_name: str = "",
    lock_timeout: float | None = None,
    base: Path | None = None,
) -> ViewUpdateOutcome:
    """§3.1 第 1–8 步。

    ``reservation_held``：调用方是否整段持有 S 视图的项目预约（手动更新持有；运行前 /
    运行后自动更新不持有，这里切 S 时自己拿，拿不到就本轮不切、记一行日志——载荷已登记，
    下次运行前的组同步会补上）。``lock_timeout``：等谱系锁的上限（手动更新给几秒，
    拿不到抛 ``project_lock_busy``；自动路径不限时）。``core_call(视图, 目标, 登记钩子)``
    调核心更新，返回它的结果。
    """

    view = embedded_project_dir(script_id, base)
    marker = await asyncio.to_thread(read_view_marker, view)
    if marker is None:
        raise EmbeddedProjectError("项目还没有登记版本（副本尚未采纳），无法更新")
    lineage = str(marker["lineage"])
    outcome = ViewUpdateOutcome(
        result=None,
        lineage=lineage,
        payload_before=str(marker["payload"]),
        payload_after=str(marker["payload"]),
        version_before=str(marker.get("version") or ""),
        version_after=str(marker.get("version") or ""),
    )

    def log(line: str) -> None:
        outcome.log_lines.append(line)
        send_log(line)

    lock = lineage_update_lock(lineage)
    try:
        if lock_timeout is None:
            await lock.acquire()
        else:
            await asyncio.wait_for(lock.acquire(), timeout=lock_timeout)
    except asyncio.TimeoutError as exc:
        raise MaaFWProjectUpdateError(
            "同一项目正在自动更新/预检中，请稍后再试", project_lock_busy=True
        ) from exc
    try:
        # 1. 先同步到组（不联网）：组里已有别的版本就先切过去，再照常发现。
        synced = await sync_view_to_group(
            script_id, channel, reservation_held=reservation_held, base=base
        )
        if synced is not None:
            outcome.group_synced = True
            log(f"已切到本项目当前版本 {synced.version}（与同组脚本一致）")
            marker = await asyncio.to_thread(read_view_marker, view) or marker
        target = await asyncio.to_thread(
            payload_target_for, script_id, marker, channel, base
        )

        async def after_register(registered: payloads.RegisterResult) -> None:
            outcome.registered_id = registered.payload_id
            goal = registered.latest_id
            current = await asyncio.to_thread(read_view_marker, view)
            if current is None or str(current["payload"]) != goal:
                switched = await asyncio.to_thread(
                    _switch_sync,
                    script_id,
                    goal,
                    lineage,
                    reservation_held=reservation_held,
                    base=base,
                )
                if switched is None:
                    outcome.s_skipped_reason = "项目正被占用，本次没切，下次运行前切换"
                    log(f"新版本已登记，{outcome.s_skipped_reason}")
                else:
                    log(f"已切到新版本 {switched.version}（{switched.elapsed:.1f} s）")
            propagation = await asyncio.to_thread(
                propagate_payload,
                lineage,
                channel,
                goal,
                list(members),
                switched_by={"scriptId": script_id, "name": script_name},
                exclude=[script_id],
                base=base,
            )
            outcome.propagation = propagation
            summary = describe_propagation(propagation, members)
            if summary:
                log(summary)
            switched_members = [
                member
                for member in members
                if member.script_id in set(propagation.switched)
            ]
            if switched_members:
                confirm_environments_in_background(switched_members, base)

        outcome.result = await core_call(view, target, after_register)
    finally:
        lock.release()

    final = await asyncio.to_thread(read_view_marker, view)
    if final is not None:
        outcome.payload_after = str(final["payload"])
        outcome.version_after = str(final.get("version") or "")
    outcome.result = _normalize_result(outcome, channel, base)
    return outcome


def _normalize_result(
    outcome: ViewUpdateOutcome, channel: str, base: Path | None
) -> Any:
    """``updated`` 的口径是「S 的视图换了版本」：组同步切过去也算，新版本登记了却没
    切过去（S 被占用）不算。``current / latest`` 是切换前后的版本；没下载时 ``source``
    取组 ``latest`` 记的来源。"""

    result = outcome.result
    if result is None or not dataclasses.is_dataclass(result):
        return result
    if outcome.updated:
        source = getattr(result, "source", None) or public_source(
            latest_entry(outcome.lineage, channel, base)
        )
        return dataclasses.replace(
            result,
            updated=True,
            checked=True,
            current_version=outcome.version_before,
            previous_version=outcome.version_before,
            latest_version=outcome.version_after,
            version_name=outcome.version_after,
            source=source,
            skipped_reason=None,
            message=(
                getattr(result, "message", "")
                if getattr(result, "updated", False)
                else f"MaaFW 项目已切到 {outcome.version_after}（组里已有的版本）"
            ),
        )
    if getattr(result, "updated", False):
        return dataclasses.replace(
            result,
            updated=False,
            message=f"新版本已登记，{outcome.s_skipped_reason or '本脚本尚未切换'}",
        )
    return result


__all__ = [
    "ViewUpdateOutcome",
    "confirm_environments_in_background",
    "describe_propagation",
    "latest_entry",
    "lineage_update_lock",
    "memo_path_factory",
    "payload_target_for",
    "public_source",
    "run_view_update",
    "sync_view_to_group",
]
