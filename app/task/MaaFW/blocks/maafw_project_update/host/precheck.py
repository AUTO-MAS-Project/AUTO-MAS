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

"""新版本登记前的运行环境预检：挂在更新流程的 ``post_validate`` 上。

MaaEnd v2.29.0 打包了 MaaFramework v5.14.0-beta.1，binding 被钉成
``maafw==5.14.0b1`` 而 PyPI 上没有——更新成功、环境建不出来、任务每次必挂。
所以新载荷在 staging 里建好、登记之前先**真建**一次运行环境（不 dry-run；把自带
Python 里的 binding 钉回原生库版本也就发生在这一步，写的是 staging）：建不出来
就丢掉 staging、所有视图继续跑当前版本，并按谱系 + 目标版本写备忘
（``precheck_memo.py``），之后每次运行前由 ``precheck_gate.py`` 按失败类别决定要不要重试
（缺 binding 轻探一次；网络类与其它原因各自冷却一段时间后再试）。

环境建好之后再对 Python agent 做一次导入静态检查（``agent_env/import_check.py``）：
MaaFgo v2.0.03 漏装了 ``agent/battle/runtime/``，解释器能 ``import maa``，agent 一启动却
``ModuleNotFoundError``。启动时必然 import 的项目模块不在就同样丢弃新版本；第三方包缺失等
只记日志。检查自身出任何意外都放行（宁可漏报，不可误拒）。

建环境、导入检查、临时 agent 目录的放置与回收归 agent 环境一侧（``env_trial.py`` 的
``trial_environment``）；这里只查新版本自带的原生库能不能加载、记失败原因与备忘、构造回调。
回调跑在工作线程里，不拿锁、不 await。运行前自动更新
（``project_session``）与手动更新（``/maafw/update``）共用同一份逻辑，两边只在
「要不要读备忘」上不同（手动不读，见 precheck_gate）。
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, MutableMapping
from pathlib import Path
from typing import Any

from app.task.MaaFW.blocks.maafw_agent_env.host.env_trial import (
    KIND_AGENT_MODULE_MISSING,
    MaaFWAgentImportMissingError,
    PrepareProjectEnvironment,
    trial_environment,
)
from app.task.MaaFW.blocks.maafw_project_update.core.project_update.precheck_memo import (
    classify_precheck_failure,
    write_runtime_precheck,
)
from app.utils import get_logger

logger = get_logger("MFW 更新预检")


def _resolve_requirement(project_path: Path) -> str | None:
    """项目此刻（已是新版本）要钉的 maafw requirement；只进备忘字段。"""

    try:
        # 要读项目自带的 DLL，逻辑在原生库识别库（tools/core/native）里；只在真要写备忘时才导入。
        from app.task.MaaFW.blocks.maafw_native.requirement import (
            resolve_project_maafw_requirement,
        )

        return resolve_project_maafw_requirement(project_path)
    except Exception:  # noqa: BLE001 - 解析不出来就记 "maafw"，不盖住预检原因
        return None


class MaaFWNativeLoadError(RuntimeError):
    """新版本里 runner 要用的 MaaFramework 原生库在干净进程里都加载不了。"""


def check_staging_native_runtime(root: Path, send_log: Callable[[str], None]) -> None:
    """在独立子进程里加载一次 staging 里 runner 会用的 ``MaaFramework.dll``；确定加载不了
    就 raise。

    agent 那一侧的检查用的是项目自带 Python 里的 maafw，碰不到 runner 用的这份原生库：
    MAA_bbb v1.13.20 的差量更新把 runner 换到了只有几个 DLL 的 ``runtimes/win-x64``，预检
    照样通过，切过去以后每次运行都报 ``Could not find module ... (or one of its
    dependencies)``。只在 Windows 上查；找不到原生库、子进程起不来或超时都放行
    （宁可漏报，不可误拒），只有子进程明确报「加载失败」才拒。
    """

    if os.name != "nt":
        return
    try:
        from app.task.MaaFW.blocks.maafw_native.project_runtime import (
            NATIVE_LOAD_FAILED,
            NATIVE_LOAD_OK,
            probe_native_runtime_load,
            project_maafw_runtime_path,
        )

        runtime = project_maafw_runtime_path(root)
    except Exception as exc:  # noqa: BLE001 - 定位不了就不下结论
        logger.warning(f"定位新版本的 MaaFramework 原生库失败，放行：{exc}")
        return
    if runtime is None:
        return
    verdict, detail = probe_native_runtime_load(runtime)
    try:
        location = runtime.relative_to(root).as_posix()
    except ValueError:
        location = str(runtime)
    if verdict == NATIVE_LOAD_FAILED:
        raise MaaFWNativeLoadError(
            f"新版本自带的 MaaFramework（{location}/）加载不了：{detail}。"
            "多半是这个目录里缺了依赖的 DLL"
        )
    if verdict != NATIVE_LOAD_OK:
        logger.warning(f"MaaFramework 原生库加载检查没能完成，放行：{detail}")
        send_log("[原生库检查] 没能完成，跳过")
        return
    send_log(f"[原生库检查] {location}/MaaFramework.dll 加载正常")


def build_precheck_validator(
    *,
    prepare: PrepareProjectEnvironment,
    cancel_event: threading.Event,
    send_log: Callable[[str], None],
    agent_env_root: Path,
    failure: MutableMapping[str, Any],
    previous_version: str | None = None,
    project_name: str | None = None,
    memo_path_for: Callable[[str], Path] | None = None,
) -> Callable[[Path], bool]:
    """构造 ``post_validate`` 回调（收新载荷的 staging 路径）。

    ``prepare`` 是宿主的 ``project_environment.prepare_project_environment_sync``（不要绕过它直接调
    ``agent_env.project_env.prepare_project_environment``：route、代理、interface
    重读都在里面）。``agent_env_root`` 是预检根（``env_trial.precheck_agent_root``）。失败时把 ``{targetVersion, requirement, kind, reason, …}``
    写进 ``failure``，按 ``memo_path_for(目标版本)`` 落备忘（谱系 + 版本，组共有），
    然后原样 raise 让原因进异常文本；用户取消（``cancel_event`` 已置位）时既不写
    备忘也不填 ``failure``。D4：不按「requirement 为 None」短路，一律走同一套 prepare。
    """

    def validate(root: Path) -> bool:
        send_log("正在检查新版本的运行环境（准备不出来就放弃这次更新，继续用当前版本）")
        # 预检 venv 不参与跨视图共用：建在这份 staging 专用的子目录里，离开 with 时删掉
        # （失败原因与备忘先记完再删）
        with trial_environment(root, agent_env_root) as trial:
            try:
                # 原生库加载只要一两秒，放在建环境前面：加载不了就不必再建
                check_staging_native_runtime(root, send_log)
                # 已取消就不再查导入：核心包随后按取消收尾
                trial.prepare_and_check(
                    prepare,
                    cancel_event,
                    send_log,
                    previous_version=previous_version,
                )
            except Exception as exc:
                if cancel_event.is_set():
                    raise
                info = classify_precheck_failure(
                    root, exc, requirement=_resolve_requirement(root)
                )
                if isinstance(exc, MaaFWAgentImportMissingError):
                    # 备忘里仍按 other 记（冷却一天才自动再试），这里只给文案分支用
                    info["kind"] = KIND_AGENT_MODULE_MISSING
                if previous_version:
                    info["previousVersion"] = str(previous_version)
                if project_name:
                    info["projectName"] = str(project_name)
                failure.clear()
                failure.update(info)
                if memo_path_for is not None and info.get("targetVersion"):
                    try:
                        write_runtime_precheck(
                            memo_path_for(str(info["targetVersion"])), info
                        )
                    except Exception as memo_error:  # noqa: BLE001
                        logger.warning(f"写运行环境预检备忘失败：{memo_error}")
                raise
        send_log("新版本运行环境检查通过")
        return True

    return validate


__all__ = [
    "MaaFWNativeLoadError",
    "build_precheck_validator",
    "check_staging_native_runtime",
]
