"""起 worker 用的运行环境：向 agent 环境借、还运行池里的环境，再拼出 worker 的环境变量。

运行池（base venv、binding、native）归 agent 环境那一块管（``agent_env/runtime_lease.py``）。
这里是运行这边唯一的接缝：:func:`prepare_runner_environment` 借一次
（``borrow_runtime_environment``，拿回解释器路径、binding 版本与目录、给 worker 的环境变量等
普通数据），用 :func:`build_runner_environment` 拼出 worker 的 ``PYTHONPATH`` 等；
:func:`release_runner_environment` 按借到的标识还回去。借的时候连同运行计划里声明的 agent
一起交过去，agent 环境顺带算好 agent 命令计划，:func:`worker_run_plan` 把它填进下发给 worker 的计划。
"""

from __future__ import annotations

import os
import sys
import sysconfig
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable

from app.task.MaaFW.blocks.maafw_agent_env.core.agent_env.runtime_lease import (
    DEFAULT_RUNTIME_LEASE_TTL_SECONDS,
    EnvironmentProgressCallback,
    borrow_runtime_environment,
    return_runtime_environment,
)
from app.task.MaaFW.blocks.maafw_agent_env.core.runtime_pool.host_environment import (
    strip_host_python_environment,
)

if TYPE_CHECKING:
    from app.task.MaaFW.blocks.maafw_agent_env.core.runtime_pool import (
        ExtraPackagesInstaller,
        MaaFWRuntimePool,
        RuntimeInstaller,
    )
    from app.task.MaaFW.blocks.maafw_interface.interface.agent_command import (
        MaaFWAgentCommandPlan,
    )
    from app.task.MaaFW.blocks.maafw_interface.interface.models import MaaFWAgent
    from app.task.MaaFW.blocks.maafw_interface.runner.models import MaaFWRunPlan


@dataclass(frozen=True)
class MaaFWRunnerEnvironment:
    python_executable: Path
    venv_path: Path
    env: dict[str, str]
    packages: tuple[str, ...]
    maafw_version: str | None
    runtime_id: str | None = None
    maafw_requirement: str | None = None
    runtime_pool_root: Path | None = None
    runtime_pool_id: str | None = None
    lease_id: str | None = None
    #: 按版本存放的 binding 目录、其版本、以及池里的官方原生库目录（项目自带 DLL 时为 None）。
    binding_dir: Path | None = None
    binding_version: str | None = None
    native_dir: Path | None = None
    #: 借环境时 agent 环境按声明算出的 agent 命令计划（``MaaFWRuntimeLease.agent_plans``）。
    agent_plans: tuple[MaaFWAgentCommandPlan, ...] = ()


def prepare_runner_environment(
    project_path: str | Path,
    *,
    managed_env_root: str | Path | None = None,
    runtime_pool_root: str | Path | None = None,
    runtime_pool: MaaFWRuntimePool | None = None,
    runtime_installer: RuntimeInstaller | None = None,
    extras_installer: ExtraPackagesInstaller | None = None,
    runtime_pool_id: str | None = None,
    lease_owner: str = "automas-maafw-runner",
    lease_ttl_seconds: float | None = DEFAULT_RUNTIME_LEASE_TTL_SECONDS,
    import_paths: Iterable[str | Path] = (),
    send_log: Callable[[str], None] | None = None,
    progress: EnvironmentProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
    agents: Sequence[MaaFWAgent] | None = None,
    agent_env_root: str | Path | None = None,
) -> MaaFWRunnerEnvironment:
    """向 agent 环境借一份运行环境，拼好 worker 的环境变量。

    借的规则（base venv、binding、取消、租约）见 ``agent_env.runtime_lease.borrow_runtime_environment``；
    ``import_paths`` 只决定 worker 的 ``PYTHONPATH``（binding 目录之后）。``agents`` 是运行计划的
    ``declaredAgents``，借到的 ``agent_plans`` 交给 :func:`worker_run_plan`。用完交给
    :func:`release_runner_environment`。
    """

    lease = borrow_runtime_environment(
        project_path,
        agents=agents,
        agent_env_root=agent_env_root,
        managed_env_root=managed_env_root,
        runtime_pool_root=runtime_pool_root,
        runtime_pool=runtime_pool,
        runtime_installer=runtime_installer,
        extras_installer=extras_installer,
        runtime_pool_id=runtime_pool_id,
        lease_owner=lease_owner,
        lease_ttl_seconds=lease_ttl_seconds,
        send_log=send_log,
        progress=progress,
        cancel_event=cancel_event,
    )
    try:
        env = build_runner_environment(
            lease.venv_path,
            import_paths=import_paths,
            binding_dir=lease.binding_dir,
            extra_env=lease.worker_env,
        )
        return MaaFWRunnerEnvironment(
            python_executable=lease.python_executable,
            venv_path=lease.venv_path,
            env=env,
            packages=lease.packages,
            maafw_version=lease.maafw_version,
            runtime_id=lease.runtime_id,
            maafw_requirement=lease.maafw_requirement,
            runtime_pool_root=lease.runtime_pool_root,
            runtime_pool_id=lease.runtime_pool_id,
            lease_id=lease.lease_id,
            binding_dir=lease.binding_dir,
            binding_version=lease.binding_version,
            native_dir=lease.native_dir,
            agent_plans=lease.agent_plans,
        )
    except Exception:
        return_runtime_environment(
            runtime_pool_root=lease.runtime_pool_root,
            runtime_id=lease.runtime_id,
            lease_id=lease.lease_id,
            binding_version=lease.binding_version,
            runtime_pool=runtime_pool,
        )
        raise


def release_runner_environment(
    environment: MaaFWRunnerEnvironment,
    *,
    runtime_pool: MaaFWRuntimePool | None = None,
) -> dict[str, Any] | None:
    """Release the execution lease held by a prepared runner environment."""

    return return_runtime_environment(
        runtime_pool_root=environment.runtime_pool_root,
        runtime_id=environment.runtime_id,
        lease_id=environment.lease_id,
        binding_version=environment.binding_version,
        runtime_pool=runtime_pool,
    )


def worker_run_plan(
    plan: MaaFWRunPlan,
    environment: MaaFWRunnerEnvironment,
    *,
    agent_plans: Sequence[MaaFWAgentCommandPlan] | None = None,
) -> MaaFWRunPlan:
    """下发给 worker 的计划：``plan`` 的深拷贝，填上 agent 命令计划，``PI_CLIENT_MAAFW_VERSION``
    换成这次实际加载的 binding 版本（借不出版本时保留建计划时的值）。

    ``agent_plans`` 缺省取 ``environment.agent_plans``；调用方要沿用早先算好的一份（同一账号
    这一轮的重试）时显式传。``plan`` 本身不改。
    """

    runner_plan = plan.model_copy(deep=True)
    source = environment.agent_plans if agent_plans is None else agent_plans
    runner_plan.agents = [agent.model_copy(deep=True) for agent in source]
    if environment.maafw_version:
        runner_plan.piEnv["PI_CLIENT_MAAFW_VERSION"] = (
            f"v{environment.maafw_version.lstrip('v')}"
        )
    return runner_plan


def build_runner_environment(
    venv_path: str | Path,
    *,
    import_paths: Iterable[str | Path] = (),
    binding_dir: str | Path | None = None,
    extra_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """worker 子进程的环境变量。

    ``binding_dir`` 排在 ``PYTHONPATH`` 最前：base venv 里没有 ``maa``，``SOURCE_ROOT``
    与基解释器目录也没有，所以 ``import maa`` 落到它。``extra_env`` 是借运行环境时 agent
    环境给的键（``MaaFWRuntimeLease.worker_env``）：``MAAFW_BINARY_PATH`` 指到副本自带的
    ``maafw/`` 或池里的 native 目录（``maa/__init__.py`` 读它）——worker 与 binding 自检共用
    这几个键的拼法（``binding_environment_variables``），自检过了 worker 就一定能起；另有
    agent pip 约束文件的目录。最后盖上去。
    """

    # 宿主的 PYTHONPATH / PYTHONWARNINGS 等一律不进 worker：worker 能 import 什么只由
    # import_paths 决定（剔除名单与运行池 / agent 共用，见 host_environment 模块）。
    env = strip_host_python_environment()

    venv = Path(venv_path).resolve()
    scripts_dir = venv / ("Scripts" if os.name == "nt" else "bin")
    resolved_import_paths = [
        str(Path(path).resolve()) for path in import_paths if Path(path).exists()
    ]
    if binding_dir is not None:
        resolved_import_paths.insert(0, str(Path(binding_dir).resolve()))

    env["VIRTUAL_ENV"] = str(venv)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # `python -m` 会把 cwd 插到 sys.path[0]，排在 PYTHONPATH 之前。受 Runtime 监督时
    # cwd 是 <app-root>，那里还躺着安装包自带的旧 app/ 包（只随整包安装更新），会把
    # PYTHONPATH 里的源码根整个盖掉，worker 于是跑上一个版本的引擎代码。这里禁掉 cwd
    # 前置，让 import_paths 说了算；worker 的 cwd 仍是 <app-root>，因为运行池、更新
    # 缓存等用户数据都按它解析。运行池的解释器约束是 3.12/3.13，该变量必然生效。
    env["PYTHONSAFEPATH"] = "1"
    env["PATH"] = f"{scripts_dir}{os.pathsep}{env.get('PATH', '')}"
    if resolved_import_paths:
        env["PYTHONPATH"] = os.pathsep.join(resolved_import_paths)
    else:
        env.pop("PYTHONPATH", None)
    if extra_env:
        env.update(extra_env)
    return env


def prefer_active_venv_site_packages(
    site_packages: str | Path | None = None,
) -> Path | None:
    """Keep the project Runner packages ahead of shared plugin dependencies."""

    raw_path = site_packages or sysconfig.get_path("purelib")
    if not raw_path:
        return None

    active_site_packages = Path(raw_path).resolve()
    normalized_path = str(active_site_packages)
    sys.path[:] = [
        item for item in sys.path if _normalized_sys_path(item) != normalized_path
    ]
    sys.path.insert(0, normalized_path)
    return active_site_packages


def _normalized_sys_path(path: str) -> str:
    try:
        return str(Path(path).resolve())
    except (OSError, RuntimeError):
        return path
