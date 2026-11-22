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

"""项目运行环境的准备与确认（宿主侧，项目更新这一块）。

「确认运行环境」= 在项目目录上备好 MaaFramework 运行池与 agent 环境（``agent_env.project_env``），
成功后写环境缓存、给视图记 ``envConfirmedFor``。运行前 / 运行后确认、更新前预检、切换后确认、
同组传播后的后台确认都经 ``env_confirm`` 取到这里的 :func:`prepare_project_environment_sync`
（``env_confirm`` 按模块属性取，测试可以在这里打补丁）。

顶层只有轻量导入：运行池与 agent 环境只在函数体里导入（这个函数本来就在工作线程里跑，与原先
管理器里的那份同一做法）。日志沿用「MFW 内置运行」这个 logger 名。
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from app.core import Config
from app.utils import get_logger

logger = get_logger("MFW 内置运行")


def prepare_project_environment_sync(
    project_path: Path,
    cancel_event: threading.Event,
    send_log: Callable[[str], None],
    *,
    agent_env_root: Path | None = None,
    store_cache: bool = True,
    proxy_url: str | None = None,
    lenient_health_check: bool = False,
    health_warnings_out: list[str] | None = None,
) -> bool:
    """在工作线程里备好这个项目的运行环境，返回是否真做了准备。

    ``health_warnings_out``：给了就把「报错照跑」放行的原因追加进去，调用方据此决定收尾
    那句日志怎么写（返回值的含义不变，其它调用方不受影响）。

    先比指纹：项目没更新过、上次准备的环境也还在盘上，就只是一次哈希加
    几个 stat，直接跳过。

    更新事务的提交前预检也走这里（``tools/embedded/precheck.py``），只是
    把 isolated_venv 的 agent 建到 ``agent_env_root``（池根下的预检目录）
    并且 ``store_cache=False`` 不写环境缓存（D6）。手动更新的 API 路径没有
    manager 实例，也用同一份逻辑。

    ``proxy_url`` 是托管级解析出来的代理（``None`` 表示没解析过，沿用
    全局），给池里的 uv / pip 与 agent venv 的安装用。

    ``lenient_health_check``：项目自带 Python 的健康检查「报错照跑」，只有运行前 / 运行后的
    环境确认（``_ensure_project_environment``）传；预检、手动更新、同组传播后的确认都不传
    （缺省严格，见 ``agent_env.prepare_agent_envs``）。放行过的这次不写环境缓存、不记
    ``envConfirmedFor``：下次照样重查，编辑页也不会因此显示「已就绪」。
    """

    # 与 API 侧同理：这几个模块会拉起 runtime_pool 与 agent_env，只在真要
    # 用时导入。
    from app.task.MaaFW.blocks.maafw_interface.interface import (
        load_interface_model_cached,
    )
    from app.task.MaaFW.tools.core.agent_env.project_env import (
        prepare_project_environment,
        project_environment_fingerprint,
    )
    from app.task.MaaFW.tools.core.runtime_pool.host_environment import (
        subprocess_proxy_scope,
    )
    from app.task.MaaFW.tools.embedded.embedded_project import (
        mark_env_confirmed,
        read_view_marker,
    )
    from app.task.MaaFW.tools.embedded.env_cache import (
        load_prepared_environment,
        store_prepared_environment,
    )
    from app.task.MaaFW.tools.embedded.runtime_route import (
        resolve_runtime_pool_route,
    )

    # 视图挂的载荷在算指纹之前记下：确认成功后只给这个载荷记 ``envConfirmedFor``
    # （调用方持有视图预约，期间换不了；来源目录 / staging 没有标记，不记）。
    marker = read_view_marker(project_path) if store_cache else None
    confirmed_for = str(marker["payload"]) if marker is not None else None

    def _confirmed() -> None:
        if confirmed_for is None:
            return
        try:
            mark_env_confirmed(project_path, confirmed_for)
        except OSError as exc:
            logger.warning(f"MFW 记录运行环境确认失败（下次运行前再确认）：{exc}")

    fingerprint = project_environment_fingerprint(project_path)
    if load_prepared_environment(project_path, fingerprint) is not None:
        _confirmed()
        return False

    interface = load_interface_model_cached(project_path)
    route = resolve_runtime_pool_route()
    # 代理作用域按线程登记，必须在这个同步函数体内进入：池的 uv / pip 子进程
    # 与 agent venv 的安装都从 strip_host_python_environment 拿到用户在 MAS
    # 里填的代理（§2.4）。预检回调与运行前确认都经过这里。
    with subprocess_proxy_scope(
        proxy_url if proxy_url is not None else Config.proxy_url
    ):
        result = prepare_project_environment(
            project_path,
            interface,
            runtime_pool_root=route.root,
            runtime_pool_id=route.pool_id,
            agent_env_root=agent_env_root,
            send_log=send_log,
            cancel_event=cancel_event,
            lenient_health_check=lenient_health_check,
        )
    agents = result.get("agents")
    health_warnings = agents.get("healthWarnings") if isinstance(agents, dict) else None
    if health_warnings:
        if health_warnings_out is not None:
            health_warnings_out.extend(str(item) for item in health_warnings)
        send_log(
            "运行环境检查没通过、按「报错照跑」放行，这次不记为「运行环境已就绪」，"
            "下次运行前再查"
        )
        return True
    if store_cache:
        store_prepared_environment(
            project_path,
            str(result.get("projectFingerprint") or "") or fingerprint,
            result,
        )
        _confirmed()
    return True


__all__ = ["prepare_project_environment_sync"]
