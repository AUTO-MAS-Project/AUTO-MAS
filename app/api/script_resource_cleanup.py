#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

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


from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from app.core import Config
from app.utils import get_logger


logger = get_logger("脚本资源回收")

_MAAFW_MANAGED_ENVIRONMENT_SERVICE = "maafw.managed.environment.v1"
_BACKGROUND_CLEANUP_TASKS: set[asyncio.Task[None]] = set()


async def _collect_managed_resources_in_background() -> None:
    """Run the potentially expensive Managed GC after deletion has returned.

    Script deletion is already committed before this task is scheduled.  The
    collection is idempotent and will be retried by the next Managed
    operation, so waiting for a full Project Store/Runtime Pool inventory here
    only makes the delete endpoint look hung to the user.
    """

    try:
        from app.plugins.manager import PluginManager

        service = PluginManager.service.get(_MAAFW_MANAGED_ENVIRONMENT_SERVICE)
        collect = getattr(service, "collect_unreferenced_resources", None)
        if not callable(collect):
            raise RuntimeError(
                "Managed 环境服务未提供 collect_unreferenced_resources()"
            )
        result = collect()
        if not isinstance(result, Awaitable):
            raise RuntimeError(
                "Managed 环境服务的 collect_unreferenced_resources() 必须返回 awaitable"
            )
        await result
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # Deletion is already committed. Collection is idempotent and retries
        # after the next Managed run, crash, upgrade or deletion.
        logger.warning(f"MaaFWManaged 脚本删除后资源回收暂未完成: {exc}")


def _schedule_managed_resource_cleanup() -> None:
    task = asyncio.create_task(_collect_managed_resources_in_background())
    _BACKGROUND_CLEANUP_TASKS.add(task)

    def discard(completed: asyncio.Task[None]) -> None:
        _BACKGROUND_CLEANUP_TASKS.discard(completed)

    task.add_done_callback(discard)


async def delete_script_with_resource_cleanup(script_id: str) -> None:
    """Delete one script and reconcile resources owned by its former type."""

    # Config.del_script resolves the type while holding the same write scope that
    # commits deletion, so this decision cannot race with script conversion/update.
    try:
        deleted_type = await Config.del_script(script_id)
    except KeyError:
        # The delete menu can be clicked twice before the list refreshes. The
        # first request already committed the deletion, so make the duplicate
        # request idempotent instead of surfacing a misleading 500.
        logger.info(f"脚本已删除，重复删除请求按成功处理: {script_id}")
        return
    try:
        from app.core.maafw_agent_env_state import invalidate_maafw_agent_env_state

        await asyncio.to_thread(
            invalidate_maafw_agent_env_state,
            script_id,
        )
    except Exception as exc:
        # The sidecar is only a cache; a damaged or unwritable cache must never
        # turn a committed script deletion into an API failure.
        logger.warning(f"MaaFW 运行环境状态清理暂未完成: {exc}")
    if deleted_type != "MaaFWManaged":
        return

    # Do not make the delete response wait for a full resource inventory and
    # GC pass.  The task keeps a strong reference until completion and logs a
    # best-effort failure without changing the committed deletion result.
    _schedule_managed_resource_cleanup()


__all__ = ["delete_script_with_resource_cleanup"]
