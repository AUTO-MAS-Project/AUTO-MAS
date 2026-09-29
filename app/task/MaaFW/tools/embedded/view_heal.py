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

"""旧投影规则建的载荷按当前规则补齐一次：宿主侧编排（运行前检查与手动检查更新触发）。

检查、取回、重建、登记都在核心包 ``project_update/projection_heal``；这里只是把它挂到
``view_update.run_view_update`` 上：谱系锁 → 组同步 → 检查 / 补齐 / 登记 → 切触发脚本 →
同组空闲脚本立即切并确认运行环境（运行中的跑完再切）。不用查的载荷（按当前规则建的、
查过的）在拿锁之前读两个 JSON 就返回。

结果记在**载荷清单**里（``projectionCheck``），同一载荷全组只查一次；补齐后的载荷清单记
当前规则版本，以后切过去的视图、从它克隆的脚本都不用再查。重建失败时取回的文件直接放进
触发脚本的视图兜底（v5.6.0 热修 #1110 的做法：它们成了视图私有文件，换版本时照常带过去，
新载荷里有同路径文件时以载荷为准），失败记进清单、有限次重试。#1110 在视图标记里记的
``projectionHeal`` 不再读写：视图换载荷时标记整个换掉，它自然消失。
"""

from __future__ import annotations

import asyncio
import functools
import threading
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx

from app.task.MaaFW.tools.core.project_update.projection_heal import (
    HealOutcome,
    heal_due,
    heal_payload,
    write_missing_files,
)
from app.task.MaaFW.tools.core.project_update.updater import MaaFWProjectUpdateError
from app.task.MaaFW.tools.embedded.embedded_project import (
    GroupMember,
    embedded_project_dir,
    payloads_root,
    read_view_marker,
)
from app.task.MaaFW.tools.embedded.view_update import latest_entry, run_view_update
from app.utils import get_logger

logger = get_logger("MFW 投影补齐")


def projection_heal_due(script_id: str, channel: str, base: Path | None = None) -> bool:
    """这个脚本所在组挂的载荷要不要按当前投影规则检查 / 补齐（读两个 JSON，不联网）。"""

    try:
        marker = read_view_marker(embedded_project_dir(script_id, base))
        if marker is None:
            return False
        lineage = str(marker["lineage"])
        entry = latest_entry(lineage, channel, base)
        payload_id = str(entry["id"]) if entry else str(marker["payload"])
        return heal_due(payloads_root(base), lineage, payload_id, channel)
    except Exception as exc:  # noqa: BLE001 - 判断不了就当不用查，不挡运行
        logger.warning(f"MFW 投影补齐判断失败（{script_id[:8]}）：{exc}")
        return False


def _precheck(
    interface_model: Any, *, proxy_url: str | None, send_log: Callable[[str], None]
) -> Callable[[Path], Any]:
    """补齐后的载荷要预检时用的回调（只在取回的文件会影响运行环境时才被调）：与更新同一个
    ``build_precheck_validator``，只是不写预检备忘——备忘按「目标版本」拦更新，这里没有
    新版本。"""

    def validate(staging: Path) -> Any:
        from app.task.MaaFW.embedded_manager import MaaFWEmbeddedManager
        from app.task.MaaFW.tools.core.runtime_pool import MaaFWRuntimePoolService
        from app.task.MaaFW.tools.embedded.precheck import (
            build_precheck_validator,
            precheck_agent_root,
        )
        from app.task.MaaFW.tools.embedded.runtime_route import (
            runtime_pool_route_from_service,
        )

        route = runtime_pool_route_from_service(MaaFWRuntimePoolService())
        return build_precheck_validator(
            prepare=functools.partial(
                MaaFWEmbeddedManager._prepare_project_environment_sync,
                proxy_url=proxy_url,
            ),
            cancel_event=threading.Event(),
            send_log=send_log,
            agent_env_root=precheck_agent_root(route.root),
            failure={},
            previous_version=getattr(interface_model, "version", None),
            project_name=getattr(interface_model, "name", None),
            memo_path_for=None,
        )(staging)

    return validate


async def heal_projection(
    script_id: str,
    *,
    channel: str,
    members: Sequence[GroupMember] | Callable[[], Sequence[GroupMember]],
    reservation_held: bool,
    send_log: Callable[[str], None],
    proxy: httpx.Proxy | None = None,
    proxy_url: str | None = None,
    shell_hint: str = "",
    script_name: str = "",
    lock_timeout: float | None = None,
    base: Path | None = None,
    cache_root: Path | None = None,
    post_validate: Callable[[Path], Any] | None = None,
) -> HealOutcome | None:
    """检查并按需补齐本脚本所在组的载荷；不用查时返回 None（不拿锁、不联网）。

    ``reservation_held`` / ``lock_timeout`` 与 :func:`run_view_update` 同义；拿不到谱系锁
    （同项目正在更新）就这次不查。返回的 ``HealOutcome.switched`` 表示本脚本的视图换了
    载荷。**从不抛异常**（取消除外）：失败只记日志，照常用当前版本运行。
    ``post_validate`` 给测试替换预检；缺省按更新的预检建。
    """

    if not await asyncio.to_thread(projection_heal_due, script_id, channel, base):
        return None

    async def core_call(view_path: Path, target: Any, after_register: Any) -> Any:
        try:
            from app.task.MaaFW.tools.core.interface.loader import (
                load_interface_model_cached,
            )

            interface_model = await asyncio.to_thread(
                load_interface_model_cached, view_path
            )
        except Exception as exc:  # noqa: BLE001 - 只有 GitHub 比对要它，缺了那条路不走
            logger.warning(f"MFW 投影补齐读取 interface 失败：{exc}")
            interface_model = None

        def fallback(contents: Mapping[str, bytes]) -> int:
            # 只往正挂着这个载荷的视图里放（组同步没切过去的视图不碰）。
            marker = read_view_marker(view_path)
            if marker is None or str(marker["payload"]) != target.payload_id:
                return 0
            return write_missing_files(view_path, contents)

        return await heal_payload(
            target,
            after_register,
            interface_model=interface_model,
            proxy=proxy,
            shell_hint=shell_hint,
            post_validate=post_validate
            or _precheck(interface_model, proxy_url=proxy_url, send_log=send_log),
            send_log=send_log,
            cache_root=cache_root,
            fallback=fallback,
        )

    try:
        outcome = await run_view_update(
            script_id,
            channel=channel,
            members=members,
            reservation_held=reservation_held,
            send_log=send_log,
            core_call=core_call,
            script_name=script_name,
            lock_timeout=lock_timeout,
            base=base,
            switch_label="补齐后的版本",
        )
    except MaaFWProjectUpdateError as exc:
        if not exc.project_lock_busy:
            logger.warning(f"MFW 投影补齐失败（{script_id[:8]}）：{exc}")
        else:
            logger.info(f"MFW 投影补齐：同项目正在更新，这次不查（{script_id[:8]}）")
        return None
    except Exception as exc:  # noqa: BLE001 - 补齐失败不挡运行
        logger.opt(exception=True).warning(
            f"MFW 投影补齐失败（{script_id[:8]}）：{exc}"
        )
        return None
    result = outcome.result
    if not isinstance(result, HealOutcome):
        result = HealOutcome("skipped", version=outcome.version_after)
    result.switched = outcome.updated
    return result


__all__ = ["heal_projection", "projection_heal_due"]
