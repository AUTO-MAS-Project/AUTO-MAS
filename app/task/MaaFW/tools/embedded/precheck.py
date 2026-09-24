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
（``precheck_memo.py``），之后每次运行前由 ``precheck_gate.py`` 轻探一次再决定要不要重试。

这里只负责构造回调。回调跑在工作线程里，不拿锁、不 await。运行前自动更新
（``embedded_manager``）与手动更新（``/maafw/update``）共用同一份逻辑，两边只在
「要不要读备忘」上不同（手动不读，见 precheck_gate）。
"""

from __future__ import annotations

import shutil
import threading
from collections.abc import Callable, MutableMapping
from pathlib import Path
from typing import Any, Protocol

from app.task.MaaFW.tools.core.agent_env.planner import (
    compute_isolated_venv_path,
)
from app.task.MaaFW.tools.core.project_update.precheck_memo import (
    classify_precheck_failure,
    write_runtime_precheck,
)
from app.utils import get_logger

logger = get_logger("MFW 更新预检")

# 预检期间 isolated_venv 类型的 Python agent 建在池根下这个独立目录（D6）：
# ``prepare_agent_envs`` 对隔离 venv 是先 rmtree 再重装，直接建在正式根会把
# 旧版本还能用的 venv 先删掉——预检失败后旧版本就没 agent 了。
PRECHECK_AGENT_ROOT_NAME = "precheck_agent_venvs"


class PrepareProjectEnvironment(Protocol):
    def __call__(
        self,
        project_path: Path,
        cancel_event: threading.Event,
        send_log: Callable[[str], None],
        *,
        agent_env_root: Path | None = None,
        store_cache: bool = True,
    ) -> bool: ...


def precheck_agent_root(pool_root: str | Path) -> Path:
    return Path(pool_root) / PRECHECK_AGENT_ROOT_NAME


def cleanup_precheck_agent_venv(project_path: Path, agent_root: Path) -> None:
    """删掉预检根下本项目那份隔离 venv（成功失败都删）；根空了就顺手去掉。"""

    venv_path = compute_isolated_venv_path(project_path, managed_env_root=agent_root)
    shutil.rmtree(venv_path, ignore_errors=True)
    try:
        agent_root.rmdir()
    except OSError:
        pass


def _resolve_requirement(project_path: Path) -> str | None:
    """项目此刻（已是新版本）要钉的 maafw requirement；只进备忘字段。"""

    try:
        # 要读项目自带的 DLL，逻辑在 runner 包里；它会拉起 runtime_pool，
        # 所以只在真要写备忘时才导入。
        from app.task.MaaFW.tools.core.runner.environment import (
            resolve_project_maafw_requirement,
        )

        return resolve_project_maafw_requirement(project_path)
    except Exception:  # noqa: BLE001 - 解析不出来就记 "maafw"，不盖住预检原因
        return None


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

    ``prepare`` 是宿主的 ``_prepare_project_environment_sync``（不要绕过它直接
    new ``MaaFWRunnerService``：route、``import_paths=[SOURCE_ROOT]``、interface
    重读都在里面）。失败时把 ``{targetVersion, requirement, kind, reason, …}``
    写进 ``failure``，按 ``memo_path_for(目标版本)`` 落备忘（谱系 + 版本，组共有），
    然后原样 raise 让原因进异常文本；用户取消（``cancel_event`` 已置位）时既不写
    备忘也不填 ``failure``。D4：不按「requirement 为 None」短路，一律走同一套 prepare。
    """

    def validate(root: Path) -> bool:
        send_log("正在新版本上预检运行环境（建不出来就丢弃新版本，继续当前版本）")
        try:
            prepare(
                root,
                cancel_event,
                send_log,
                agent_env_root=agent_env_root,
                store_cache=False,
            )
        except Exception as exc:
            if cancel_event.is_set():
                raise
            info = classify_precheck_failure(
                root, exc, requirement=_resolve_requirement(root)
            )
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
        finally:
            cleanup_precheck_agent_venv(root, agent_env_root)
        send_log("运行环境预检通过，登记新版本")
        return True

    return validate


__all__ = [
    "PRECHECK_AGENT_ROOT_NAME",
    "PrepareProjectEnvironment",
    "build_precheck_validator",
    "cleanup_precheck_agent_venv",
    "precheck_agent_root",
]
