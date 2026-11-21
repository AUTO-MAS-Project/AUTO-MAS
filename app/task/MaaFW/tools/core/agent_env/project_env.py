"""准备与确认一个项目的运行环境（运行池 base + binding，加上项目的 agent 环境）。

宿主的运行前 / 运行后确认、更新预检、编辑页手动准备都走 :func:`prepare_project_environment`
（宿主侧入口是 ``MaaFWEmbeddedManager._prepare_project_environment_sync`` 与
``api_service/agent_env``）。它借一次运行环境、备好 agent、记下项目输入指纹，返回前一定把
租约还掉；之后真跑时 worker 按同一套推导借到同一份 base 与 binding。
"""

from __future__ import annotations

import hashlib
import logging
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

from packaging.version import InvalidVersion, Version

from ..interface.models import MaaFWInterface
from ..native.project_runtime import probe_bundled_maafw_version
from ..runtime_pool import MaaFWRuntimePool, RuntimeInstaller
from .env import prepare_agent_envs, project_python_maafw_version
from .runtime_lease import (
    MaaFWRuntimeLease,
    borrow_runtime_environment,
    return_runtime_lease,
)
from .service import MaaFWAgentEnvService

ProjectEnvironmentProgressCallback = Callable[[dict[str, Any]], None]

logger = logging.getLogger("automas.maafw.agent_env.project_env")
_PROJECT_ENVIRONMENT_INPUTS = (
    "interface.json",
    "interface.jsonc",
    ".auto_mas_maafw_project.json",
    "requirements.txt",
    "pyproject.toml",
    "uv.lock",
)


def project_environment_fingerprint(
    project_path: str | Path, *, include_binding: bool = True
) -> str | None:
    """Hash the project inputs that determine the prepared Runner route.

    ``include_binding=False`` 只算项目文件、不算自带解释器里的 binding 版本：准备流程
    用它判断「准备期间变的是不是只有我们自己钉回的 binding」。

    项目自带原生库的版本也进指纹：运行池的 binding 按它钉（``resolve_project_maafw_requirement``
    的第一优先级），项目更新只换了 DLL、interface / requirements 没动时，旧指纹会
    命中上一个版本的 binding。
    """

    root = Path(project_path).expanduser().resolve(strict=False)
    if not root.is_dir():
        return None

    digest = hashlib.sha256()
    found_interface = False
    bundled_version = probe_bundled_maafw_version(root)
    digest.update(f"bundled-maafw:{bundled_version or ''}\0".encode("utf-8"))
    for relative_name in _PROJECT_ENVIRONMENT_INPUTS:
        candidate = root / relative_name
        if not candidate.is_file():
            digest.update(f"missing:{relative_name}\0".encode("utf-8"))
            continue
        if relative_name in {"interface.json", "interface.jsonc"}:
            found_interface = True
        try:
            content = candidate.read_bytes()
        except OSError:
            return None
        digest.update(relative_name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    # 项目自带解释器里的 maafw binding 版本也是输入：agent 的部署脚本会在运行期改写它，
    # 不算进来的话准备结果会被缓存沿用，钉回 binding 的那一步永远不再跑。
    if include_binding:
        for site in sorted(root.glob("python/Lib/site-packages/maafw-*.dist-info")):
            digest.update(b"project-python-binding\0")
            digest.update(site.name.encode("utf-8"))
    return digest.hexdigest() if found_interface else None


def _only_binding_repinned(
    project_path: str | Path, files_fingerprint: str | None
) -> bool:
    """准备期间项目文件一个没变、只有自带解释器里的 maafw binding 变成了与自带原生库
    一致的版本——这正是 ``_repin_project_python_binding`` 干的事，不是别人动了项目。

    钉回本身会改 ``python/Lib/site-packages/maafw-*.dist-info``，而它又是指纹的输入，
    不认这一条的话「binding 版本漂了」的项目第一次准备必定被当成并发改动拒绝，第二次
    才过（M9A v4.9.0 自带 5.12.3 的 binding 配 5.13.0 的原生库，出厂就是这样）。
    """

    if (
        project_environment_fingerprint(project_path, include_binding=False)
        != files_fingerprint
    ):
        return False
    root = Path(project_path)
    installed = project_python_maafw_version(root / "python" / "python.exe")
    native = probe_bundled_maafw_version(root)
    if not installed or not native:
        return False
    try:
        return Version(installed) == Version(native)
    except InvalidVersion:
        return installed == native


def _report_project_progress(
    callback: ProjectEnvironmentProgressCallback | None,
    stage: str,
    status: str,
    message: str,
    *,
    percent: float | None = None,
    **payload: Any,
) -> None:
    if callback is None:
        return
    event: dict[str, Any] = {
        "stage": stage,
        "status": status,
        "message": message,
        **payload,
    }
    if percent is not None:
        event["percent"] = percent
    try:
        callback(event)
    except Exception:
        # 进度只是旁观者，不能拖垮准备流程；但要留痕，否则回调里的
        # ``no running event loop`` 这类错误就此消失。
        logger.warning("MaaFW 环境准备进度回调失败: stage=%s", stage, exc_info=True)


def prepare_project_environment(
    project_path: str | Path,
    interface: MaaFWInterface | dict[str, Any] | None,
    *,
    runtime_pool_root: str | Path | None = None,
    runtime_pool: MaaFWRuntimePool | None = None,
    runtime_installer: RuntimeInstaller | None = None,
    runtime_pool_id: str | None = None,
    agent_env_root: str | Path | None = None,
    send_log: Callable[[str], None] | None = None,
    bootstrap_python: str | None = None,
    install_agent_dependencies: bool = True,
    progress: ProjectEnvironmentProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
    lenient_health_check: bool = False,
) -> dict[str, Any]:
    """Prewarm the exact Runner pool identity and project Agent runtimes.

    ``lenient_health_check``：项目自带 Python 的健康检查「报错照跑」，只有宿主运行前 / 运行后
    的环境确认传；缺省严格（更新预检、编辑页手动准备等），见 ``agent_env.prepare_agent_envs``。
    放行的原因在结果的 ``agents.healthWarnings``。

    The preflight lease is always released before returning. A later run
    resolves the same canonical requirements, reuses the prepared runtime,
    and acquires its own execution-scoped lease.

    ``cancel_event`` reaches the runtime install step only: setting it kills
    the running uv subprocess. Agent venv preparation is not interruptible,
    so a caller that cancels should wait for the thread with a bounded grace
    period rather than assume it stops at once.
    """

    lease: MaaFWRuntimeLease | None = None
    try:
        input_fingerprint = project_environment_fingerprint(project_path)
        files_fingerprint = project_environment_fingerprint(
            project_path, include_binding=False
        )
        lease = borrow_runtime_environment(
            project_path,
            runtime_pool_root=runtime_pool_root,
            runtime_pool=runtime_pool,
            runtime_installer=runtime_installer,
            runtime_pool_id=runtime_pool_id,
            lease_owner=f"automas-maafw-preflight:{uuid.uuid4().hex}",
            lease_ttl_seconds=600,
            send_log=send_log,
            progress=progress,
            cancel_event=cancel_event,
        )
        environment = lease
        _report_project_progress(
            progress,
            "preparing_agents",
            "running",
            "正在准备 MaaFW Agent 环境",
            percent=75.0,
            runtime_id=environment.runtime_id,
        )

        def report_agent_progress(event: dict[str, object]) -> None:
            raw_percent = event.get("percent")
            agent_percent: float | None = None
            overall_percent: float | None = None
            if isinstance(raw_percent, (int, float)):
                agent_percent = min(100.0, max(0.0, float(raw_percent)))
                overall_percent = 75.0 + agent_percent * 0.2
            details = {
                key: event[key] for key in ("completed", "total") if key in event
            }
            if agent_percent is not None:
                details["agent_percent"] = agent_percent
            _report_project_progress(
                progress,
                "preparing_agents",
                str(event.get("status") or "running"),
                str(event.get("message") or "正在准备 MaaFW Agent 环境"),
                percent=overall_percent,
                runtime_id=environment.runtime_id,
                **details,
            )

        agent_service = MaaFWAgentEnvService()
        agent_plans = agent_service.build_command_plans(
            project_path,
            interface,
            managed_env_root=agent_env_root,
        )
        agent_result = prepare_agent_envs(
            project_path,
            agent_plans,
            send_log=send_log,
            bootstrap_python=bootstrap_python,
            install_dependencies=install_agent_dependencies,
            progress=report_agent_progress,
            # 项目没自带原生库时，agent 的 maafw 钉成 runner 刚解析出的确切版本。
            runner_maafw_version=environment.maafw_version,
            lenient_health_check=lenient_health_check,
        )
        output_fingerprint = project_environment_fingerprint(project_path)
        if input_fingerprint is not None and output_fingerprint != input_fingerprint:
            # 准备自己把副本里的 binding 钉回原生库版本时指纹必然变：这不是并发改动，
            # 结果按准备后的指纹缓存，下次打开页面才能命中
            if _only_binding_repinned(project_path, files_fingerprint):
                input_fingerprint = output_fingerprint
            else:
                raise RuntimeError(
                    "MaaFW 项目环境输入在准备期间发生变化；拒绝缓存旧运行环境"
                )
        result = {
            "status": "ready",
            "runtime": {
                "runtimeId": environment.runtime_id,
                "poolId": environment.runtime_pool_id,
                "pythonExecutable": str(environment.python_executable),
                "venvPath": str(environment.venv_path),
                "packages": list(environment.packages),
                "maafwRequirement": environment.maafw_requirement,
                # 就是 binding 的版本（runner_task 拿它填 PI_CLIENT_MAAFW_VERSION）
                "maafwVersion": environment.maafw_version,
                "bindingDir": (
                    str(environment.binding_dir)
                    if environment.binding_dir is not None
                    else None
                ),
                "bindingVersion": environment.binding_version,
                "nativeDir": (
                    str(environment.native_dir)
                    if environment.native_dir is not None
                    else None
                ),
            },
            "agents": agent_result.model_dump(mode="json"),
        }
        if input_fingerprint is not None:
            result["projectFingerprint"] = input_fingerprint
        _report_project_progress(
            progress,
            "completed",
            "ready",
            "MaaFW 项目运行环境准备完成",
            percent=100.0,
            runtime_id=environment.runtime_id,
        )
        return result
    except Exception as exc:
        _report_project_progress(
            progress,
            "failed",
            "failed",
            f"MaaFW 项目运行环境准备失败: {exc}",
        )
        raise
    finally:
        if lease is not None:
            return_runtime_lease(lease, runtime_pool=runtime_pool)


__all__ = [
    "ProjectEnvironmentProgressCallback",
    "prepare_project_environment",
    "project_environment_fingerprint",
]
