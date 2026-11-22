#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""M9A 托管的配置回调与恢复池：保存账号、恢复账号字段时整理受管任务（启动 / 切号 / 关闭）。

- :func:`build_m9a_config_handler`：通用 MFW 的配置回调（中立模块 ``MaaFW/seams/config_handler``）
  只换掉 ``prepare_user_update`` 一项，换成 :func:`prepare_m9a_user_update`；其余（读取前准备、新账号默认
  队列、复制托管克隆视图、删除托管清理视图与运行池对账）原样。
- :func:`prepare_m9a_user_update`：先整理（:func:`settle_m9a_user_update`）、再加密，两步都在线程里做，先后
  与通用的 ``user_update.prepare_user_update`` 相同。
- ``M9A_RESTORE_POOLS``：mas 池用 ``MaaFW/seams/restore_service`` 公开的部件拼，恢复那一步换成
  :func:`restore_m9a_mas`（只整理、不加密，照旧）；native 池原样带上 ``NATIVE_POOL``。

整理的口径是 ``managed.py`` 的规则（实现在 ``arrange.settle_m9a_snapshot``），这里只是外壳：从配置里取出
interface、生效的资源名、登录方式和账号 ``Info``，调它，再把结果并回要写的数据。配置一律经 ``config_view`` 读写。

**启动期就会被导入**（``builtin_registration`` 调 ``create_config_handler()`` 时，``registration.build_handler``
现导入本模块），所以顶层只放轻量导入；``M9A_RESTORE_POOLS`` 是按需建的模块属性（第一次取时才导入恢复服务），
启动期不拉起它。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.utils import get_logger

if TYPE_CHECKING:
    from app.models.script_contracts import ScriptConfigHandler
    from app.utils.common.config.restore import ConfigRestorePool, RestoreContext

# 沿用删掉风味（第 11 步）之前的 logger 名，app.log 的检索习惯不变
logger = get_logger("MaaFW 特调")


def _settle_modules() -> tuple[Any, Any, Any]:
    """整理要用的三个模块（``config_view``、``arrange``、interface 读取）；在事件循环上先导入一次，
    线程里再取就只是查缓存。"""

    from app.task.M9A import arrange, config_view
    from app.task.MaaFW.blocks.maafw_interface.interface import loader

    return config_view, arrange, loader


def settle_m9a_user_update(
    script_id: str,
    script_config: Any,
    user_config: Any,
    data: dict[str, Any],
) -> bool:
    """写账号配置前：``data`` 带 ``Task.TaskSnapshot`` 时按 ``managed.py`` 整理，原地改 ``data``。

    ``data`` 是 ``{分组: {字段: 值}}``（``update_user`` 与配置恢复的形状）。快照是 JSON 串就写回
    JSON 串、是字典就写回字典；要一并改的 ``Info`` 字段并进 ``data["Info"]``。返回有没有改动。
    读不到 interface、快照解析不了都原样放行：运行期还会按同一口径再处理一遍。
    """

    config_view, arrange, loader = _settle_modules()
    task = data.get("Task")
    if not isinstance(task, dict) or "TaskSnapshot" not in task:
        return False
    raw = task["TaskSnapshot"]
    try:
        snapshot = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return False
    if not isinstance(snapshot, dict):
        return False

    try:
        root = Path(config_view.project_root(script_id, script_config))
        if not root.is_dir():
            return False
        interface_model = loader.load_interface_model_cached(root)
    except Exception as exc:  # noqa: BLE001 - 读不出 interface 不该挡住保存
        logger.debug(f"保存任务配置时读取 interface 失败，未按特调整理：{exc}")
        return False

    _, resource_name = config_view.settle_selection(script_config, interface_model)
    incoming_info = data.get("Info") if isinstance(data.get("Info"), dict) else {}
    user_info = config_view.settle_user_info(user_config, incoming_info)
    try:
        settled, info_updates = arrange.settle_m9a_snapshot(
            interface_model,
            snapshot,
            resource_name=resource_name,
            login_mode=config_view.login_mode(script_config),
            user_info=user_info,
        )
    except Exception as exc:  # noqa: BLE001 - 整理失败按原样保存
        logger.warning(f"MaaFW 特调整理任务快照失败，按原样保存：{exc}")
        return False

    changed = False
    if settled != snapshot:
        task["TaskSnapshot"] = (
            json.dumps(settled, ensure_ascii=False) if isinstance(raw, str) else settled
        )
        changed = True
    if info_updates:
        info = data.get("Info")
        if not isinstance(info, dict):
            info = data["Info"] = {}
        info.update(info_updates)
        changed = True
    return changed


async def prepare_m9a_user_update(
    script: Any, user: Any, *, data: dict[str, Any]
) -> None:
    """保存账号前原地准备快照补丁：先收归受管任务及账号，再加密任务和全局表里的密码。

    配置的 stage / commit 留在调用方（``Config.update_user``）。
    """

    task_data = data.get("Task")
    if not isinstance(task_data, dict) or "TaskSnapshot" not in task_data:
        return

    # 整理要用的模块先在事件循环上导入，线程里不冷导入
    config_view, _, _ = _settle_modules()
    script_id = str(config_view.script_uid(script))
    await asyncio.to_thread(
        settle_m9a_user_update,
        script_id=script_id,
        script_config=script,
        user_config=user,
        data=data,
    )
    task_data["TaskSnapshot"] = await asyncio.to_thread(
        config_view.seal_task_snapshot,
        script_id,
        script,
        task_data["TaskSnapshot"],
    )


async def restore_m9a_mas(ctx: RestoreContext, ts: str) -> None:
    """mas 池的恢复：回填账号字段侧车；老备份里可能还有受管任务，与保存同一口径整理（不加密）。"""

    import uuid

    from app.task.M9A import config_view
    from app.task.MaaFW.seams import backup_archive, restore_service

    restore_service.user_guard(ctx)
    user = config_view.user_collection(ctx.script_config)[uuid.UUID(ctx.user_id)]
    # 恢复前把当前字段终态存底（force），误恢复可找回
    backup_archive.archive_mas_backup(
        ctx.script_id, ctx.user_id, config_view.overlay_values(user), force=True
    )
    restored = backup_archive.restore_mas_backup(ctx.script_id, ctx.user_id, ts)
    if restored:
        overlay = backup_archive.group_overlay(restored)
        _settle_modules()
        await asyncio.to_thread(
            settle_m9a_user_update, ctx.script_id, ctx.script_config, user, overlay
        )
        await config_view.replace_user_fields(user, overlay)


def _build_restore_pools() -> list[ConfigRestorePool]:
    from app.task.MaaFW.seams import restore_service
    from app.utils.common.config.restore import ConfigRestorePool

    return [
        ConfigRestorePool(
            key="mas",
            kind="user",
            mas_base="sidecar_only",
            files=restore_service.mas_files,
            backup_root=restore_service.mas_root,
            preview=restore_service.preview_mas,
            restore=restore_m9a_mas,
        ),
        restore_service.NATIVE_POOL,
    ]


def build_m9a_config_handler() -> ScriptConfigHandler:
    """M9A 的配置回调：通用 MFW 那份（按 ``M9AConfig`` 与 M9A 属主造）只换掉保存前准备。"""

    from dataclasses import replace

    from app.models.config import M9AConfig
    from app.task.M9A.registration import M9A_OWNER
    from app.task.MaaFW.seams.config_handler import (
        build_maafw_config_handler,
    )

    return replace(
        build_maafw_config_handler(M9AConfig, owner=M9A_OWNER),
        prepare_user_update=prepare_m9a_user_update,
    )


def __getattr__(name: str) -> Any:
    # ``M9A_RESTORE_POOLS`` 按需建：恢复服务只在真要恢复时才导入（宿主取恢复池也是按需的）
    if name == "M9A_RESTORE_POOLS":
        pools = _build_restore_pools()
        globals()[name] = pools
        return pools
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# M9A_RESTORE_POOLS 是按需建的模块属性（见上面的 __getattr__），不列进 __all__
__all__ = [
    "build_m9a_config_handler",
    "prepare_m9a_user_update",
    "restore_m9a_mas",
    "settle_m9a_user_update",
]
