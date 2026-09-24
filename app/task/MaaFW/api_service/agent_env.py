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

"""``/maafw/agent-env/prepare`` 背后的业务：预备 Runner 运行时与各 agent 的 Python 环境。"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.core import Config
from app.models.schema import (
    MaaFWAgentEnvInfo,
    MaaFWAgentEnvPrepareData,
    WSMaaFWEnvPrepareProgressData,
)
from app.task.MaaFW.api_service.common import (
    MaaFWApiReply,
    maafw_effective_root,
    maafw_script_config,
)
from app.task.MaaFW.api_service.embedded import embedded_summary_lines
from app.task.MaaFW.tools.core.interface.loader import (
    MaaFWInterfaceLoadError,
    load_interface_model_cached,
)
from app.task.MaaFW.tools.embedded.update_credentials import (
    resolve_update_proxy_url,
)
from app.utils import get_logger
from app.utils.paths import SOURCE_ROOT
from app.utils.security import sanitize_log_message

_maafw_env_logger = get_logger("MFW 运行环境")


def _maafw_agent_env_prepare_data(
    root_path: Path,
    result: Mapping[str, Any],
    logs: list[str],
    *,
    cached: bool,
    previously_prepared: bool = False,
) -> MaaFWAgentEnvPrepareData:
    """把 ``prepare_project_environment()`` 的结果摊平成响应体。

    缓存命中与实际准备两条路共用，免得两边的字段各写一份、慢慢长歪。
    """

    runtime = result.get("runtime")
    runtime = runtime if isinstance(runtime, Mapping) else {}
    agent_payload = result.get("agents")
    agent_payload = agent_payload if isinstance(agent_payload, Mapping) else {}
    raw_plans = agent_payload.get("plans")
    raw_plans = raw_plans if isinstance(raw_plans, list) else []

    agents = [
        MaaFWAgentEnvInfo(
            childExec=str(plan.get("childExec") or ""),
            executable=str(plan.get("executable") or ""),
            runtimeKind=plan.get("runtimeKind"),
            isolatedVenvPath=plan.get("isolatedVenvPath"),
            fallbackReason=plan.get("fallbackReason"),
        )
        for plan in raw_plans
        if isinstance(plan, Mapping)
    ]

    return MaaFWAgentEnvPrepareData(
        path=str(root_path),
        agentCount=len(agents),
        agents=agents,
        logs=logs,
        runtimeId=runtime.get("runtimeId"),
        poolId=runtime.get("poolId"),
        pythonExecutable=runtime.get("pythonExecutable"),
        venvPath=runtime.get("venvPath"),
        maafwVersion=runtime.get("maafwVersion"),
        cached=cached,
        previouslyPrepared=previously_prepared,
        preparedAt=result.get("preparedAt"),
    )


async def prepare_agent_env(
    script_id: str | None, path: str, force: bool
) -> MaaFWApiReply:
    """按项目 interface 预备运行环境；项目输入指纹没变且环境还在时直接还回上次结果。

    ``force`` 跳过这层缓存（用户手动重试）。
    """

    # 这些模块会拉起 runtime_pool 与 agent_env，放在函数内延迟导入，
    # 避免所有 API 请求都为它们付出导入成本。
    from app.core.ws import protocol as ws_protocol
    from app.core.ws.publisher import Publisher
    from app.task.MaaFW.tools.core.runner.service import (
        MaaFWRunnerService,
        project_environment_fingerprint,
    )
    from app.task.MaaFW.tools.core.runtime_pool import (
        MaaFWRuntimePoolService,
    )
    from app.task.MaaFW.tools.core.runtime_pool.host_environment import (
        subprocess_proxy_scope,
    )
    from app.task.MaaFW.tools.embedded.env_cache import (
        has_prepared_environment,
        load_prepared_environment,
        store_prepared_environment,
    )
    from app.task.MaaFW.tools.embedded.project_path import (
        release_project_path,
        try_reserve_project_path,
    )
    from app.task.MaaFW.tools.embedded.runtime_route import (
        runtime_pool_route_from_service,
    )

    logs: list[str] = []
    # 准备过程可能持续数分钟（首次要下载 MaaFramework），全程把阶段、百分比
    # 与新增日志行推给前端。progress_id 留空时只落日志、不推送。
    progress_id = str(script_id or "").strip()
    loop = asyncio.get_running_loop()

    def publish_progress(event: dict) -> None:
        if not progress_id:
            return
        data = WSMaaFWEnvPrepareProgressData(
            stage=str(event.get("stage") or ""),
            status=str(event.get("status") or "running"),
            message=str(event.get("message") or ""),
            percent=event.get("percent"),
            log=event.get("log"),
        )
        # 准备跑在工作线程里，回调要跨回事件循环才能发 WS
        asyncio.run_coroutine_threadsafe(
            Publisher.send(
                id=progress_id,
                type=ws_protocol.MAAFW_ENV_PREPARE_PROGRESS,
                data=data,
            ),
            loop,
        )

    def append_log(line: str) -> None:
        logs.append(line)
        publish_progress(
            {
                "stage": "log",
                "status": "running",
                "message": line,
                "log": line,
            }
        )

    root_path, error = await maafw_effective_root(script_id, path)
    if root_path is None:
        return MaaFWApiReply.error(400, error)
    if not root_path.is_dir():
        return MaaFWApiReply.error(400, "MFW 项目路径不是有效目录，请检查项目目录")

    # 与运行、更新共用同一把项目锁：同一目录同时准备/运行会互相踩。
    reservation_key = await try_reserve_project_path(root_path)
    if reservation_key is None:
        return MaaFWApiReply.error(
            409,
            "该 MFW 项目正在运行、更新或准备环境，请稍后重试",
            MaaFWAgentEnvPrepareData(path=str(root_path), logs=logs),
        )

    try:
        # 目录字段只显示副本位置，「项目跑在导入副本上」这件事只在日志里交代
        if progress_id:
            for line in await asyncio.to_thread(embedded_summary_lines, progress_id):
                append_log(line)
        # 指纹哈希的是 interface / requirements / uv.lock 这些「脚本更新了没」
        # 的输入，所以项目一更新缓存自然失效。放在拿到项目锁之后：此刻没人在
        # 更新这个目录，算出来的指纹不会是半个更新中间态。
        fingerprint = await asyncio.to_thread(
            project_environment_fingerprint, root_path
        )
        # 界面要分「首次准备完成」和「运行环境更新完成」两句话，在写入新缓存前先看一眼
        previously_prepared = await asyncio.to_thread(
            has_prepared_environment, root_path
        )
        if not force:
            cached_result = await asyncio.to_thread(
                load_prepared_environment, root_path, fingerprint
            )
            if cached_result is not None:
                prepared_at = str(cached_result.get("preparedAt") or "")
                append_log(
                    "项目文件自上次准备以来没有变化，沿用已就绪的运行环境"
                    + (f"（上次准备于 {prepared_at}）" if prepared_at else "")
                )
                # 命中时不推 ready 进度：没有进度可言，而那条 WS 与本次响应
                # 抢着写同一行提示，谁后到谁说了算——推了反而会把响应里带
                # MaaFramework 版本号的那句盖成一句干巴巴的「已就绪」。
                return MaaFWApiReply(
                    message="MFW 运行环境已就绪",
                    data=_maafw_agent_env_prepare_data(
                        root_path, cached_result, logs, cached=True
                    ),
                )

        try:
            interface = await asyncio.to_thread(load_interface_model_cached, root_path)
        except MaaFWInterfaceLoadError as exc:
            return MaaFWApiReply.error(
                400,
                f"MFW interface 读取失败: {exc}",
                MaaFWAgentEnvPrepareData(path=str(root_path), logs=logs),
            )

        route = await asyncio.to_thread(
            lambda: runtime_pool_route_from_service(MaaFWRuntimePoolService())
        )
        # 这个端点按请求里的 path 定位项目、不经脚本配置（见 MaaFW/AGENTS.md），
        # 所以代理只在 scriptId 能解析到一份 MFW 脚本配置时才按脚本级取；
        # 编辑页新建项目还没有脚本时落回全局。
        proxy_url = Config.proxy_url
        if progress_id:
            try:
                proxy_url = resolve_update_proxy_url(maafw_script_config(progress_id))
            except (KeyError, ValueError, TypeError):
                pass

        def _prepare_with_proxy() -> dict[str, Any]:
            # 代理作用域按线程登记，必须在 to_thread 的目标函数体内进入，
            # uv / pip 子进程环境才带上用户在 MAS 里填的代理。
            with subprocess_proxy_scope(proxy_url):
                return MaaFWRunnerService().prepare_project_environment(
                    root_path,
                    interface,
                    runtime_pool_root=route.root,
                    runtime_pool_id=route.pool_id,
                    # worker 子进程跑在隔离 venv 里，代码要靠 PYTHONPATH 找到本仓；
                    # 受监督时 cwd 是 <app-root>，源码在 <app-root>/repo/，只能用源码根
                    import_paths=[SOURCE_ROOT],
                    send_log=append_log,
                    progress=publish_progress,
                )

        try:
            result = await asyncio.to_thread(_prepare_with_proxy)
        except Exception as exc:
            # 失败原因此前只活在响应体与 WS 事件里，两边都不落盘：用户报障时
            # app.log 里一行都没有，只能对着界面截图猜。准备过程的逐行日志
            # （pip 的 stderr 就在里面）一并记下来，别再丢。
            _maafw_env_logger.error(f"MFW 运行环境准备失败: {exc}")
            if logs:
                detail = "\n".join(sanitize_log_message(str(line)) for line in logs)
                _maafw_env_logger.error(f"MFW 运行环境准备日志:\n{detail}")
            publish_progress(
                {
                    "stage": "failed",
                    "status": "failed",
                    "message": f"MFW 运行环境准备失败: {exc}",
                }
            )
            return MaaFWApiReply.error(
                500,
                f"MFW 运行环境准备失败: {exc}",
                MaaFWAgentEnvPrepareData(path=str(root_path), logs=logs),
            )
        # 用准备流程自己回报的指纹：它在准备前后各算了一次，确认这期间项目文件
        # 没被动过；本地这份只在它没回报时兜底。
        # 写在项目锁内：写完才放行下一个准备/更新请求，免得它读到半份缓存。
        await asyncio.to_thread(
            store_prepared_environment,
            root_path,
            str(result.get("projectFingerprint") or "") or fingerprint,
            result,
        )
    finally:
        await release_project_path(reservation_key)

    publish_progress(
        {
            "stage": "ready",
            "status": "success",
            "message": "MFW 运行环境已就绪",
            "percent": 100.0,
        }
    )
    return MaaFWApiReply(
        message="MFW 运行环境已就绪",
        data=_maafw_agent_env_prepare_data(
            root_path,
            result,
            logs,
            cached=False,
            previously_prepared=previously_prepared,
        ),
    )
