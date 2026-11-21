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

"""在一份待验证的项目目录上做一次性的运行环境准备与检查（宿主侧，agent 环境这一块）。

给更新预检用（``precheck.py``）：新载荷的 staging 登记之前真建一次运行环境，再对 Python
agent 做导入检查。这次准备的隔离 venv 不建在正式根里、不参与跨视图共用，也不写环境确认
缓存；放在运行池根下的预检目录（:func:`precheck_agent_root`）里一份 staging 专用的子目录，
:func:`trial_environment` 结束时连同引用记录、锁文件整个删掉。

用法::

    with trial_environment(root, precheck_agent_root(pool_root)) as trial:
        try:
            ...  # 调用方自己的检查
            trial.prepare_and_check(prepare, cancel_event, send_log)
        except Exception:
            ...  # 记失败原因；目录在离开 with 时才删
            raise
"""

from __future__ import annotations

import hashlib
import os
import shutil
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.task.MaaFW.tools.core.agent_env.import_check import (
    KIND_AGENT_MODULE_MISSING,
    MaaFWAgentImportMissingError,
    check_agent_plan_imports,
    describe_missing_agent_modules,
    log_agent_import_reports,
)
from app.utils import get_logger

# 这几行告警原先在 ``precheck.py`` 里记，沿用它的 logger 名。
logger = get_logger("MFW 更新预检")

# 预检期间 isolated_venv 类型的 Python agent 建在池根下这个独立目录（D6）：
# ``prepare_agent_envs`` 对隔离 venv 是先 rmtree 再重装，直接建在正式根会把
# 旧版本还能用的 venv 先删掉——预检失败后旧版本就没 agent 了。
PRECHECK_AGENT_ROOT_NAME = "precheck_agent_venvs"
# 预检根下每个 staging 一个子目录（见 ``precheck_staging_agent_root``）；名字取短，
# venv 里的 site-packages 路径本来就深，别为它多吃 Windows 的路径长度。
PRECHECK_STAGING_DIR_PREFIX = "s"


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


def precheck_staging_agent_root(
    agent_root: str | Path, project_path: str | Path
) -> Path:
    """预检根下这一份 staging 专用的子目录，本次预检的隔离 venv 建在它里面。

    正式根里的隔离 venv 按依赖清单 + maafw 版本 + 宿主身份跨视图共用（``venv_share``），
    预检不参与共用：staging 路径每次都带新的 uuid，按它分子目录，预检 venv 就和以前按
    staging 路径命名时一样每次都是新的——上次预检中途被杀、或没删干净留下的同依赖残留
    碰不到这次（那份残留在正式根的规则下会被判「要重建」，而预检根下的拒绝重建会让预检
    直接失败、这个版本的自动更新从此停住）；两个同依赖的预检同时跑，先结束的那个也删
    不到另一个正在用的那份。
    """

    key = str(Path(project_path).resolve())
    if os.name == "nt":
        key = key.lower()
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    return Path(agent_root) / f"{PRECHECK_STAGING_DIR_PREFIX}{digest}"


def cleanup_precheck_agent_venv(project_path: Path, agent_root: Path) -> None:
    """删掉预检根下本项目那份隔离 venv（成功失败都删）；根空了就顺手去掉。

    本次预检的隔离 venv、引用记录、锁文件都在这份 staging 专用的子目录里
    （``precheck_staging_agent_root``），整个删掉即可，不会碰到别的预检。
    """

    shutil.rmtree(
        precheck_staging_agent_root(agent_root, project_path), ignore_errors=True
    )
    try:
        agent_root.rmdir()
    except OSError:
        pass


def check_staging_agent_imports(
    root: Path,
    agent_env_root: Path,
    send_log: Callable[[str], None],
    *,
    previous_version: str | None = None,
) -> None:
    """在已建好运行环境的 staging 上查 Python agent 的导入；缺项目模块就 raise。

    解释器按与预检同一个 ``agent_env_root`` 定位（隔离 venv 此刻就建在那里）。
    读 interface、建计划、检查本身出任何别的错都只记日志、放行。
    """

    try:
        from app.task.MaaFW.tools.core.agent_env import MaaFWAgentEnvService
        from app.task.MaaFW.tools.core.interface import load_interface_model_cached

        interface = load_interface_model_cached(root)
        plans = MaaFWAgentEnvService().build_command_plans(
            root, interface, managed_env_root=agent_env_root
        )
        reports = check_agent_plan_imports(root, plans)
    except Exception as exc:  # noqa: BLE001 - 检查不了就不下结论
        logger.warning(f"agent 导入检查没能完成，放行：{exc}")
        send_log(f"[Agent 导入检查] 没能完成（{type(exc).__name__}），跳过")
        return
    missing = log_agent_import_reports(reports, send_log, blocking=True)
    if missing:
        raise MaaFWAgentImportMissingError(
            describe_missing_agent_modules(missing, previous_version), missing
        )


@dataclass(frozen=True)
class TrialEnvironment:
    """:func:`trial_environment` 交出的一次性环境：``agent_env_root`` 是本次专用的子目录。"""

    root: Path
    agent_env_root: Path

    def prepare_and_check(
        self,
        prepare: PrepareProjectEnvironment,
        cancel_event: threading.Event,
        send_log: Callable[[str], None],
        *,
        previous_version: str | None = None,
    ) -> None:
        """真建一次运行环境（不写环境缓存），再查 Python agent 的导入；建不出来或缺项目模块就 raise。

        ``prepare`` 是宿主的运行环境准备实现（``env_confirm.resolve_prepare_environment``）。
        已取消就不再查导入：调用方随后按取消收尾。
        """

        prepare(
            self.root,
            cancel_event,
            send_log,
            agent_env_root=self.agent_env_root,
            store_cache=False,
        )
        if not cancel_event.is_set():
            check_staging_agent_imports(
                self.root,
                self.agent_env_root,
                send_log,
                previous_version=previous_version,
            )


@contextmanager
def trial_environment(root: Path, agent_root: Path) -> Iterator[TrialEnvironment]:
    """在 ``agent_root``（预检根）下给 ``root`` 放一份一次性的 agent 环境目录，离开时删掉。"""

    trial = TrialEnvironment(
        root=root, agent_env_root=precheck_staging_agent_root(agent_root, root)
    )
    try:
        yield trial
    finally:
        cleanup_precheck_agent_venv(root, agent_root)


__all__ = [
    "KIND_AGENT_MODULE_MISSING",
    "PRECHECK_AGENT_ROOT_NAME",
    "MaaFWAgentImportMissingError",
    "PrepareProjectEnvironment",
    "TrialEnvironment",
    "check_staging_agent_imports",
    "cleanup_precheck_agent_venv",
    "precheck_agent_root",
    "precheck_staging_agent_root",
    "trial_environment",
]
