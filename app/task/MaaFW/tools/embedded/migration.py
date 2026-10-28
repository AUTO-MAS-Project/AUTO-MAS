#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""老 MFW 副本的启动迁移；只接收脚本查询和进程启动时刻。"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from app.models.config import MaaFWConfig
from app.utils import get_logger

from .embedded_project import (
    MIGRATION_SWITCHED_BY,
    GroupMember,
    adopt_view,
    copy_is_healthy,
    effective_channel,
    embedded_project_dir,
    imported_source_path,
    read_view_marker,
    release_held_reservations,
    set_migration_active,
    settle_adopted_latest,
)
from .project_path import release_project_path, try_reserve_project_path
from .update_credentials import resolve_update_proxy_url
from .view_update import confirm_environments_in_background, sync_view_to_group

logger = get_logger("MFW 迁移")

type ScriptConfigs = Callable[[], Sequence[tuple[str, MaaFWConfig]]]


@dataclass(frozen=True)
class _MigrationEntry:
    member: GroupMember
    source: str


async def _finish_file_work[T](work: Awaitable[T]) -> T:
    """取消时等文件操作收尾，再交还预约与迁移状态；不承载配置提交。"""

    task = asyncio.ensure_future(work)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        with suppress(Exception):
            task.result()
        raise


async def migrate_embedded_copies_to_payloads(
    *, script_configs: ScriptConfigs, process_started_at: float
) -> None:
    """逐副本采纳、统一组版本，再清理旧更新状态；失败留给下次启动重试。

    宿主在调用前确认脚本表完整加载。配置与渠道在事件循环上读取，工作线程只
    消费路径和标量。全程不写配置；后台执行期间运行前检查按 migration_active
    识别视图正在切换，任何退出路径都清除此状态。
    """

    set_migration_active(True)
    held: dict[str, str] = {}
    try:
        entries = [
            _MigrationEntry(
                member=GroupMember(
                    script_id=uid,
                    channel=effective_channel(uid, config),
                    name=str(config.Info.Name or uid[:8]),
                    proxy_url=resolve_update_proxy_url(config) or None,
                ),
                source=imported_source_path(config) or str(config.Info.Path or ""),
            )
            for uid, config in script_configs()
        ]
        pending = [
            entry
            for entry in entries
            if copy_is_healthy(embedded_project_dir(entry.member.script_id))
            and read_view_marker(embedded_project_dir(entry.member.script_id)) is None
        ]
        started = time.monotonic()
        adopted = 0
        failed = 0
        for entry in pending:
            member = entry.member
            script_id, name = member.script_id, member.name
            view = embedded_project_dir(script_id)
            config = dict(script_configs()).get(script_id)
            if config is None:
                continue
            if config.is_locked:
                failed += 1
                logger.warning(f"MFW 副本迁移：脚本「{name}」正在运行，下次启动再试")
                continue
            key = await try_reserve_project_path(view)
            if key is None:
                failed += 1
                logger.warning(
                    f"MFW 副本迁移：脚本「{name}」的副本正被占用，下次启动再试"
                )
                continue
            began = time.monotonic()
            try:
                if config.is_locked:
                    failed += 1
                    continue
                if await asyncio.to_thread(read_view_marker, view) is not None:
                    # 后台开跑前，运行前检查可能已经就地采纳过它。
                    continue
                result = await _finish_file_work(
                    asyncio.to_thread(
                        adopt_view,
                        script_id,
                        channel=member.channel,
                        source=entry.source,
                    )
                )
                adopted += 1
                logger.info(
                    f"MFW 副本迁移：脚本「{name}」已登记为 {result.version}（{result.payload_id}），"
                    f"私有文件 {result.carried} 个，采纳用时 {time.monotonic() - began:.1f} s"
                )
            except Exception as exc:  # noqa: BLE001 - 逐副本隔离，不写成功标记
                failed += 1
                logger.opt(exception=True).warning(
                    f"MFW 副本迁移：脚本「{name}」采纳失败，下次启动再试：{exc}"
                )
            finally:
                await release_project_path(key)
        # 全部登记完才定同版本 latest，避免「同版本保留先来的」受脚本顺序影响。
        # 没有待采纳副本也要收尾：上次可能在最后一份采纳后、统一之前退出。
        await _finish_file_work(
            asyncio.to_thread(
                settle_adopted_latest, members=[entry.member for entry in entries]
            )
        )
        await _unify_views_to_group(entries, script_configs=script_configs, held=held)
        logger.info(
            f"MFW 副本迁移完成：采纳 {adopted} 个、失败 {failed} 个、"
            f"统一到组版本 {len(held)} 个，用时 {time.monotonic() - started:.1f} s"
        )
        members = [entry.member for entry in entries if entry.member.script_id in held]
        # 同步移交，无 await 空档；确认函数负责已接手及线程启动失败时的全部释放。
        handed = dict(held)
        held.clear()
        confirm_environments_in_background(members, held=handed)
        # 失败副本还要靠 committed 记录和包内清单识别原文件，其余作废记录照收。
        await _finish_file_work(
            asyncio.to_thread(
                _discard_legacy_update_state,
                keep_adoption_baseline=bool(failed),
                process_started_at=process_started_at,
            )
        )
    finally:
        # 中途失败或取消时，不能漏掉前面已切换、尚未交给确认线程的预约。
        release_held_reservations(held)
        set_migration_active(False)


async def _unify_views_to_group(
    entries: list[_MigrationEntry],
    *,
    script_configs: ScriptConfigs,
    held: dict[str, str],
) -> None:
    """逐视图切到谱系 + 渠道的 latest，切过的预约交由调用方移交或释放。"""

    for entry in entries:
        member = entry.member
        script_id, name = member.script_id, member.name
        # 用户之间不持视图预约；运行中的脚本还须按配置锁跳过，在事件循环上查。
        config = dict(script_configs()).get(script_id)
        if config is None:
            continue
        if config.is_locked:
            logger.info(
                f"MFW 副本迁移：脚本「{name}」正在运行，统一到组版本留给它跑完后再做"
            )
            continue
        key = await try_reserve_project_path(embedded_project_dir(script_id))
        if key is None:
            continue
        result = None
        try:
            if config.is_locked:
                continue
            result = await _finish_file_work(
                sync_view_to_group(
                    script_id,
                    member.channel,
                    reservation_held=True,
                    # 确认期间开跑会按「正在切换版本」跳过，下次运行说明迁移换过版本。
                    switched_by=MIGRATION_SWITCHED_BY,
                )
            )
        except Exception as exc:  # noqa: BLE001 - 留在原版本，下次运行前再同步
            logger.warning(f"MFW 副本迁移：脚本「{name}」统一到组版本失败：{exc}")
        finally:
            if result is None:
                await release_project_path(key)
        if result is not None:
            held[script_id] = key
            logger.info(
                f"MFW 副本迁移：脚本「{name}」{result.from_payload} → {result.payload_id}"
            )


def _discard_legacy_update_state(
    *, keep_adoption_baseline: bool, process_started_at: float
) -> None:
    """收掉旧原地更新的作废记录。

    只删进程启动前的更新流水；尚有未采纳副本时保留 committed 记录及它们指向的
    包内清单。全部采纳后才清掉视图状态目录内的旧清单和预检备忘，local-modified
    中为用户留下的原文件始终保留。
    """

    operations = Path.cwd() / "data" / "maafw_update_operations"
    if operations.is_dir():
        for record in operations.iterdir():
            state_file = record / "state.json"
            try:
                if state_file.stat().st_mtime >= process_started_at:
                    continue
                status = json.loads(state_file.read_text(encoding="utf-8")).get(
                    "status"
                )
            except (OSError, ValueError, AttributeError):
                continue
            if status == "committed" and keep_adoption_baseline:
                continue
            try:
                shutil.rmtree(record)
            except OSError as exc:
                logger.warning(f"清理作废的更新记录失败: {record} - {exc}")
    if keep_adoption_baseline:
        return
    state_root = Path.cwd() / "data" / "maafw_project_state"
    if state_root.is_dir():
        for state_dir in state_root.iterdir():
            if not state_dir.is_dir():
                continue
            for child in state_dir.iterdir():
                if child.name == "local-modified":
                    continue
                try:
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink()
                except OSError as exc:
                    logger.warning(f"清理老的更新状态失败: {child} - {exc}")
