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

"""资源包加载失败后与官方发行包核对、清掉旧版本残留：宿主侧编排（``runner_task`` 触发）。

核对、清理、登记都在核心包 ``project_update/release_check``；这里与投影补齐（``view_heal``）
一样挂到 ``view_update.run_view_update`` 上：谱系锁 → 组同步 → 核对 / 建清理后的载荷 / 登记 →
切触发脚本 → 同组空闲脚本立即切并确认运行环境（运行中的跑完再切）。

放在这里而不是 ``embedded_manager``：触发点是某个用户某次尝试的资源加载失败，在
``runner_task`` 的重试循环里，那时它正持着本视图的项目预约（``reservation_held=True``）；
``tools/embedded`` 是宿主与核心包之间唯一的接缝，核心包不碰宿主，worker 的导入闭包不受影响。
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import httpx

from app.task.MaaFW.tools.core.project_update.payloads import read_project_interface
from app.task.MaaFW.tools.core.project_update.projection_heal import (
    needs_environment_precheck,
)
from app.task.MaaFW.tools.core.project_update.release_check import (
    CleanOutcome,
    check_and_clean,
    payload_check_state,
)
from app.task.MaaFW.tools.core.project_update.updater import MaaFWProjectUpdateError
from app.task.MaaFW.tools.embedded.embedded_project import (
    ENV_CONFIRMED_FIELD,
    GroupMember,
    effective_channel,
    embedded_project_dir,
    mark_env_confirmed,
    payloads_root,
    read_view_marker,
)
from app.task.MaaFW.tools.embedded.update_credentials import resolve_update_proxy_url
from app.task.MaaFW.tools.embedded.view_update import latest_entry, run_view_update
from app.utils import get_logger

logger = get_logger("MFW 发行包核对")

# 日志里最多列几个清掉的文件。
_LOG_ITEMS = 5
# 同项目正在更新时等谱系锁的上限（与投影补齐在运行前检查里同一量级）：等不到就这次不查。
LOCK_TIMEOUT_SECONDS = 10.0
NEXT_UPDATE_HINT = "项目下次更新时会自动清掉不属于新版本的文件"


def release_group_members(script_id: str) -> list[GroupMember]:
    """同组候选：除自己外的 MFW 家族脚本（事件循环线程上抄出来；运行中的标 ``busy``）。
    与 ``api_service.common.maafw_group_members`` 同一口径。"""

    from app.core import Config
    from app.models.config import MaaFWConfig

    members: list[GroupMember] = []
    for uid, config in Config.ScriptConfig.items():
        if not isinstance(config, MaaFWConfig) or str(uid) == script_id:
            continue
        members.append(
            GroupMember(
                script_id=str(uid),
                channel=effective_channel(str(uid), config),
                busy=bool(getattr(config, "is_locked", False)),
                name=str(config.Info.Name or ""),
                proxy_url=resolve_update_proxy_url(config) or None,
            )
        )
    return members


def _state(script_id: str, channel: str, base: Path | None) -> tuple[str, dict]:
    marker = read_view_marker(embedded_project_dir(script_id, base))
    if marker is None:
        return "missing", {}
    lineage = str(marker["lineage"])
    entry = latest_entry(lineage, channel, base)
    payload_id = str(entry["id"]) if entry else str(marker["payload"])
    return payload_check_state(payloads_root(base), lineage, payload_id)


def describe_removed(removed: Sequence[str]) -> str:
    """「a、b、c」，多了「a、b、c、d、e 等 N 个」。"""

    shown = "、".join(removed[:_LOG_ITEMS])
    return shown if len(removed) <= _LOG_ITEMS else f"{shown} 等 {len(removed)} 个"


def describe_outcome(outcome: CleanOutcome) -> str:
    """给用户日志的一句话（``cleaned`` 之外的情况都说明不会再重试）。"""

    version = outcome.version or "当前版本"
    if outcome.status in {"cleaned", "repointed"}:
        return (
            f"项目里有 {len(outcome.removed)} 个文件不属于 {version} 的官方发行包"
            f"（多半是旧版本留下的）：{describe_removed(outcome.removed)}；"
            "已从本项目的副本中清掉"
        )
    if outcome.status in {"clean", "verified"}:
        return (
            f"已与 {version} 的官方发行包核对，项目里没有多余的文件，资源加载失败不是旧版本"
            "残留造成的"
        )
    if outcome.status == "failed":
        return (
            f"项目里有 {len(outcome.removed)} 个文件不属于 {version} 的官方发行包："
            f"{describe_removed(outcome.removed)}，但清理失败（{outcome.reason}）；"
            f"{NEXT_UPDATE_HINT}"
        )
    reason = outcome.reason or "没有可用的比对依据"
    return f"没能与官方发行包核对项目文件（{reason}）；{NEXT_UPDATE_HINT}"


async def check_view_release(
    script_id: str,
    *,
    channel: str,
    members: Sequence[GroupMember] | Callable[[], Sequence[GroupMember]],
    send_log: Callable[[str], None],
    proxy: httpx.Proxy | None = None,
    shell_hint: str = "",
    script_name: str = "",
    lock_timeout: float | None = LOCK_TIMEOUT_SECONDS,
    base: Path | None = None,
    cache_root: Path | None = None,
    cancel_event: threading.Event | None = None,
) -> CleanOutcome:
    """本脚本视图挂的载荷还没核对过发行包就核对一次，有残留就清掉并切过去。

    调用方持有本视图的项目预约。**从不抛异常**（取消除外）。返回的 ``switched`` 表示本脚本的
    视图换了载荷——只有这时立刻重跑才有意义。
    """

    try:
        state, record = await asyncio.to_thread(_state, script_id, channel, base)
    except Exception as exc:  # noqa: BLE001 - 判断不了就当查不了
        logger.warning(f"MFW 发行包核对判断失败（{script_id[:8]}）：{exc}")
        return CleanOutcome("unavailable", reason=str(exc))
    if state == "verified":
        return CleanOutcome("verified")
    if state in {"not_due", "missing"}:
        return CleanOutcome(
            "skipped",
            reason=str(record.get("reason") or ""),
            permanent=bool(record.get("permanent")),
        )

    view = embedded_project_dir(script_id, base)
    before = await asyncio.to_thread(read_view_marker, view)

    async def core_call(_view: Path, target: Any, after_register: Any) -> Any:
        try:
            interface = await asyncio.to_thread(
                read_project_interface, target.directory()
            )
        except Exception as exc:  # noqa: BLE001 - 读不出 interface 就没法找发行包
            return CleanOutcome("unavailable", reason=f"读不了 interface.json：{exc}")
        send_log(
            f"正在与 {interface.get('version') or '当前版本'} 的官方发行包核对项目文件"
        )
        return await check_and_clean(
            target,
            after_register,
            interface=interface,
            proxy=proxy,
            shell_hint=shell_hint,
            cache_root=cache_root,
        )

    try:
        updated = await run_view_update(
            script_id,
            channel=channel,
            members=members,
            reservation_held=True,
            send_log=send_log,
            core_call=core_call,
            script_name=script_name,
            lock_timeout=lock_timeout,
            base=base,
            switch_label="清理后的版本",
            cancel_event=cancel_event,
        )
    except MaaFWProjectUpdateError as exc:
        if exc.project_lock_busy:
            return CleanOutcome("unavailable", reason="同项目正在更新，这次没有核对")
        if exc.cancelled:
            return CleanOutcome("skipped", reason="已停止")
        logger.warning(f"MFW 发行包核对失败（{script_id[:8]}）：{exc}")
        return CleanOutcome("unavailable", reason=str(exc))
    except Exception as exc:  # noqa: BLE001 - 核对失败只是不清理
        logger.opt(exception=True).warning(
            f"MFW 发行包核对失败（{script_id[:8]}）：{exc}"
        )
        return CleanOutcome("unavailable", reason=f"{type(exc).__name__}: {exc}")
    result = updated.result
    if not isinstance(result, CleanOutcome):
        result = CleanOutcome("skipped", version=updated.version_after)
    result.switched = updated.updated
    if (
        result.switched
        and before is not None
        and str(before.get(ENV_CONFIRMED_FIELD) or "") == str(before["payload"])
        and not needs_environment_precheck(result.removed)
    ):
        # 只拿掉了资源目录里的文件、没动运行环境的输入：旧载荷确认过的运行环境对新载荷同样
        # 成立，记上，免得下次运行前再确认一遍（运行中拿不到预约时还会被说成「正在切换版本」）。
        await asyncio.to_thread(mark_env_confirmed, view, updated.payload_after)
    return result


__all__ = [
    "NEXT_UPDATE_HINT",
    "check_view_release",
    "describe_outcome",
    "describe_removed",
    "release_group_members",
]
