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

"""MFW 运行环境确认的公共入口（宿主侧）。

「确认运行环境」= 在项目目录上备好 MaaFramework 运行池与 agent 环境，成功后给视图记
``envConfirmedFor``。更新编排里有三种用法，都走这里，不再各自延迟导入 manager 去调它的
私有方法：

- **更新前预检**（:func:`build_update_precheck`）：新载荷的 staging 登记之前真建一次环境，
  建不出来就丢掉新版本。运行前 / 运行后自动更新、手动更新、投影补齐共用。
- **切换后确认**（:func:`confirm_switched_environment`）：手动更新切完视图，在调用方自己的
  视图预约里确认一次再放手。
- **同组传播后的后台确认**：``view_update.confirm_environments_in_background`` 的线程里调
  :func:`prepare_environment`。

实现仍是 ``MaaFWEmbeddedManager._prepare_project_environment_sync``（静态方法：读
interface、解析运行池路由、进代理作用域、写环境缓存与 ``envConfirmedFor``）。这里在调用时
才导入 manager：manager 顶层导入了 ``view_heal`` → ``view_update`` → 本模块，提前导入会
成环。宽严口径（``lenient_health_check``）见 ``app/task/MaaFW/AGENTS.md``，缺省严格。
"""

from __future__ import annotations

import asyncio
import functools
import threading
from collections.abc import Callable, MutableMapping
from pathlib import Path
from typing import Any

from app.utils import get_logger

# 切换后确认失败的那行告警沿用手动更新的 logger 名（原先就在 ``api_service/update.py`` 里记）。
_update_logger = get_logger("MaaFW 项目更新")

PrepareEnvironment = Callable[..., bool]


def prepare_environment(
    project_path: Path,
    cancel_event: threading.Event,
    send_log: Callable[[str], None],
    **options: Any,
) -> bool:
    """在**工作线程**里备好 ``project_path`` 的运行环境，返回是否真做了准备（指纹命中为 False）。

    - ``cancel_event``：置位后正在跑的 uv / pip 子进程被终止；
    - ``send_log``：逐行进度（会从工作线程回调，调用方自己保证线程安全）。

    ``options`` 只认 ``MaaFWEmbeddedManager._prepare_project_environment_sync`` 的关键字参数，
    原样转交（没给的按那边的缺省）：

    - ``proxy_url``：脚本级解析出的代理，``None`` 表示没解析过、沿用全局，``""`` 表示直连；
    - ``agent_env_root`` / ``store_cache``：预检用（isolated_venv 建到池根下的预检目录、
      不写环境缓存），平时不传；
    - ``lenient_health_check`` / ``health_warnings_out``：只有运行前 / 运行后确认传。

    失败原样抛出，由调用方决定记日志还是当更新失败。
    """

    from app.task.MaaFW.embedded_manager import MaaFWEmbeddedManager

    return MaaFWEmbeddedManager._prepare_project_environment_sync(
        project_path, cancel_event, send_log, **options
    )


def bind_proxy(proxy_url: str | None) -> PrepareEnvironment:
    """把代理绑进 :func:`prepare_environment`，签名与 ``precheck.PrepareProjectEnvironment``
    一致（预检里的 uv / pip 子进程也走脚本级代理）。"""

    return functools.partial(prepare_environment, proxy_url=proxy_url)


def build_update_precheck(
    *,
    proxy_url: str | None,
    cancel_event: threading.Event,
    send_log: Callable[[str], None],
    pool_root: str | Path,
    failure: MutableMapping[str, Any],
    previous_version: str | None,
    project_name: str | None,
    memo_path_for: Callable[[str], Path] | None,
) -> Callable[[Path], bool]:
    """更新类操作的 ``post_validate``：登记前在新载荷的 staging 上真建一次运行环境。

    就是 ``precheck.build_precheck_validator``，只是 ``prepare`` 固定为绑好代理的
    :func:`prepare_environment`、``agent_env_root`` 固定为 ``pool_root`` 下的预检目录。

    - ``cancel_event``：预检里 uv / pip 的终止令牌（自动更新传用户停止的令牌，手动更新与
      投影补齐传一个不会置位的新令牌）；
    - ``failure``：预检失败时写进 ``{targetVersion, requirement, kind, reason, …}``；
    - ``memo_path_for``：按目标版本落预检备忘（组共有）；投影补齐没有新版本，传 None。

    要在调用时导入 ``precheck``：它会拉起 agent_env（只在真要预检时导入）。
    """

    from app.task.MaaFW.tools.embedded.precheck import (
        build_precheck_validator,
        precheck_agent_root,
    )

    return build_precheck_validator(
        prepare=bind_proxy(proxy_url),
        cancel_event=cancel_event,
        send_log=send_log,
        agent_env_root=precheck_agent_root(pool_root),
        failure=failure,
        previous_version=previous_version,
        project_name=project_name,
        memo_path_for=memo_path_for,
    )


async def confirm_switched_environment(
    project_path: Path,
    send_log: Callable[[str], None],
    *,
    proxy_url: str | None,
) -> bool:
    """视图刚切到新版本：在调用方持有的视图预约里确认一次运行环境（缺省严格），返回是否成功。

    前端随后那次 prepare 会被「环境已就绪」短路（页面记的路径没变），所以不能指望它接。
    确认失败不算更新失败：记一行告警、给 ``send_log`` 一句「运行前会再准备」，返回 False。
    """

    send_log("正在确认新版本的运行环境")
    try:
        await asyncio.to_thread(
            prepare_environment,
            project_path,
            threading.Event(),
            send_log,
            proxy_url=proxy_url,
        )
        send_log("运行环境已就绪")
        return True
    except Exception as exc:  # noqa: BLE001 - 确认失败不算更新失败，运行前还会再备
        _update_logger.warning(f"更新后确认运行环境失败: {exc}")
        send_log(f"运行环境确认失败（运行前会再准备）: {exc}")
        return False


__all__ = [
    "PrepareEnvironment",
    "bind_proxy",
    "build_update_precheck",
    "confirm_switched_environment",
    "prepare_environment",
]
