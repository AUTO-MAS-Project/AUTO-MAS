from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Callable

import psutil

from app.task.MaaFW.tools.core.automas_maafw_agent_env import prepare_agent_envs, write_agent_compat_shims
from app.task.MaaFW.tools.core.automas_maafw_agent_env.service import MaaFWAgentEnvService
from app.task.MaaFW.tools.core.automas_maafw_interface.models import MaaFWInterface
from app.task.MaaFW.tools.core.automas_maafw_runtime_pool import MaaFWRuntimePool, RuntimeInstaller

from .environment import (
    DEFAULT_RUNTIME_LEASE_TTL_SECONDS,
    MaaFWRunnerEnvironment,
    prepare_runner_environment,
    release_runner_environment,
)
from .models import MaaFWDeviceConfig, MaaFWRunnerJobPayload, MaaFWRunPlan, MaaFWRunResult
from .run_plan import build_maafw_run_plan
from .shared_agent import route_managed_python_agents_to_shared_runtime
from .worker_registry import (
    GLOBAL_MAAFW_WORKER_REGISTRY,
    MaaFWWorkerRegistry,
    MaaFWWorkerShutdownReport,
)


ProjectEnvironmentProgressCallback = Callable[[dict[str, Any]], None]
_PROJECT_ENVIRONMENT_INPUTS = (
    "interface.json",
    "interface.jsonc",
    ".auto_mas_maafw_project.json",
    "requirements.txt",
    "pyproject.toml",
    "uv.lock",
)


def project_environment_fingerprint(project_path: str | Path) -> str | None:
    """Hash the project inputs that determine the prepared Runner route."""

    root = Path(project_path).expanduser().resolve(strict=False)
    if not root.is_dir():
        return None

    digest = hashlib.sha256()
    found_interface = False
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
    return digest.hexdigest() if found_interface else None


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
        return


class MaaFWRunnerService:
    """maafw.runner.v1 service."""

    def __init__(self, *, worker_registry: MaaFWWorkerRegistry | None = None) -> None:
        self._worker_registry = worker_registry or GLOBAL_MAAFW_WORKER_REGISTRY

    def reopen_worker_registry(self) -> None:
        self._worker_registry.reopen()

    def register_worker(self, worker: Any) -> str | None:
        return self._worker_registry.register(worker)

    def unregister_worker(self, worker_id: str | None) -> None:
        self._worker_registry.unregister(worker_id)

    async def shutdown_workers(self) -> MaaFWWorkerShutdownReport:
        return await self._worker_registry.shutdown_all()

    def build_plan(
        self,
        project_path: str | Path,
        interface: MaaFWInterface | dict[str, Any],
        *,
        controller_name: str | None = None,
        resource_name: str | None = None,
        selected_preset: str | None = None,
        task_snapshot: dict[str, Any] | None = None,
        task_names: list[str] | None = None,
        task_options: dict[str, Any] | None = None,
        managed_env_root: str | Path | None = None,
    ) -> MaaFWRunPlan:
        return build_maafw_run_plan(
            project_path,
            self._coerce_interface(interface),
            controller_name=controller_name,
            resource_name=resource_name,
            selected_preset=selected_preset,
            task_snapshot=task_snapshot,
            task_names=task_names,
            task_options=task_options,
            managed_env_root=managed_env_root,
        )

    def create_job_payload(
        self,
        plan: MaaFWRunPlan | dict[str, Any],
        device_config: MaaFWDeviceConfig | dict[str, Any],
    ) -> MaaFWRunnerJobPayload:
        owner_pid = os.getpid()
        try:
            owner_create_time = psutil.Process(owner_pid).create_time()
        except psutil.Error:
            owner_create_time = None
        return MaaFWRunnerJobPayload(
            plan=plan if isinstance(plan, MaaFWRunPlan) else MaaFWRunPlan.model_validate(plan),
            deviceConfig=(
                device_config
                if isinstance(device_config, MaaFWDeviceConfig)
                else MaaFWDeviceConfig.model_validate(device_config)
            ),
            ownerPid=owner_pid,
            ownerCreateTime=owner_create_time,
        )

    def prepare_environment(
        self,
        project_path: str | Path,
        *,
        managed_env_root: str | Path | None = None,
        runtime_pool_root: str | Path | None = None,
        runtime_pool: MaaFWRuntimePool | None = None,
        runtime_installer: RuntimeInstaller | None = None,
        runtime_requirement: str | None = None,
        runtime_requirements: list[str] | tuple[str, ...] | None = None,
        runtime_id: str | None = None,
        runtime_pool_id: str | None = None,
        runtime_python_constraint: str | None = None,
        lease_owner: str = "automas-maafw-runner",
        lease_ttl_seconds: float | None = DEFAULT_RUNTIME_LEASE_TTL_SECONDS,
        import_paths: list[str | Path] | None = None,
        send_log: Callable[[str], None] | None = None,
        progress: ProjectEnvironmentProgressCallback | None = None,
    ) -> MaaFWRunnerEnvironment:
        return prepare_runner_environment(
            project_path,
            managed_env_root=managed_env_root,
            runtime_pool_root=runtime_pool_root,
            runtime_pool=runtime_pool,
            runtime_installer=runtime_installer,
            runtime_requirement=runtime_requirement,
            runtime_requirements=runtime_requirements,
            runtime_id=runtime_id,
            runtime_pool_id=runtime_pool_id,
            runtime_python_constraint=runtime_python_constraint,
            lease_owner=lease_owner,
            lease_ttl_seconds=lease_ttl_seconds,
            import_paths=import_paths or [],
            send_log=send_log,
            progress=progress,
        )

    def release_environment(
        self,
        environment: MaaFWRunnerEnvironment,
        *,
        runtime_pool: MaaFWRuntimePool | None = None,
    ) -> dict[str, Any] | None:
        return release_runner_environment(
            environment,
            runtime_pool=runtime_pool,
        )

    def prepare_project_environment(
        self,
        project_path: str | Path,
        interface: MaaFWInterface | dict[str, Any] | None,
        *,
        runtime_pool_root: str | Path | None = None,
        runtime_pool: MaaFWRuntimePool | None = None,
        runtime_installer: RuntimeInstaller | None = None,
        runtime_requirement: str | None = None,
        runtime_requirements: list[str] | tuple[str, ...] | None = None,
        runtime_id: str | None = None,
        runtime_pool_id: str | None = None,
        runtime_python_constraint: str | None = None,
        agent_env_root: str | Path | None = None,
        import_paths: list[str | Path] | None = None,
        send_log: Callable[[str], None] | None = None,
        bootstrap_python: str | None = None,
        install_agent_dependencies: bool = True,
        managed_shared_agent_dependencies_complete: bool | None = None,
        managed_python_agent_indexes: list[int] | tuple[int, ...] | None = None,
        progress: ProjectEnvironmentProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Prewarm the exact Runner pool identity and project Agent runtimes.

        The preflight lease is always released before returning. A later run
        resolves the same canonical requirements, reuses the prepared runtime,
        and acquires its own execution-scoped lease.
        """

        environment: MaaFWRunnerEnvironment | None = None
        try:
            input_fingerprint = project_environment_fingerprint(project_path)
            environment = self.prepare_environment(
                project_path,
                runtime_pool_root=runtime_pool_root,
                runtime_pool=runtime_pool,
                runtime_installer=runtime_installer,
                runtime_requirement=runtime_requirement,
                runtime_requirements=runtime_requirements,
                runtime_id=runtime_id,
                runtime_pool_id=runtime_pool_id,
                runtime_python_constraint=runtime_python_constraint,
                lease_owner=f"automas-maafw-preflight:{uuid.uuid4().hex}",
                lease_ttl_seconds=600,
                import_paths=import_paths,
                send_log=send_log,
                progress=progress,
            )
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
                    key: event[key]
                    for key in ("completed", "total")
                    if key in event
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
            shared_agents = route_managed_python_agents_to_shared_runtime(
                project_path,
                agent_plans,
                python_executable=environment.python_executable,
                dependencies_complete=(
                    managed_shared_agent_dependencies_complete
                ),
                managed_python_agent_indexes=managed_python_agent_indexes,
            )
            if shared_agents:
                shim_dir = write_agent_compat_shims(environment.venv_path)
                if send_log is not None:
                    send_log(
                        "[Python环境] 托管 Python Agent 复用共享 runtime: "
                        f"{environment.python_executable} "
                        f"(agents={len(shared_agents)}, shim={shim_dir})"
                    )
            agent_result = prepare_agent_envs(
                project_path,
                agent_plans,
                send_log=send_log,
                bootstrap_python=bootstrap_python,
                install_dependencies=install_agent_dependencies,
                progress=report_agent_progress,
            )
            if input_fingerprint is not None and (
                project_environment_fingerprint(project_path) != input_fingerprint
            ):
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
                    "maafwVersion": environment.maafw_version,
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
            if environment is not None:
                self.release_environment(environment, runtime_pool=runtime_pool)

    def write_job_file(
        self,
        payload: MaaFWRunnerJobPayload,
        work_dir: str | Path,
        *,
        job_name: str | None = None,
    ) -> Path:
        path = Path(work_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        name = job_name or f"maafw-runner-job-{uuid.uuid4().hex}.json"
        job_path = path / name
        job_path.write_text(
            json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return job_path

    def run_worker(
        self,
        payload: MaaFWRunnerJobPayload,
        *,
        work_dir: str | Path,
        worker_command: list[str] | None = None,
        send_log: Callable[[str], None] | None = None,
        timeout: float | None = None,
    ) -> MaaFWRunResult:
        log = send_log or (lambda _: None)
        job_path = self.write_job_file(payload, work_dir)
        command = worker_command or [
            sys.executable,
            "-m",
            "app.task.MaaFW.tools.core.automas_maafw_runner.worker",
        ]
        process = subprocess.Popen(
            [*command, str(job_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        worker_id = self.register_worker(process)
        result_payload: dict[str, Any] | None = None
        try:
            assert process.stdout is not None
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    log(line)
                    continue
                event_type = event.get("type")
                if event_type == "log":
                    log(str(event.get("message") or ""))
                elif event_type == "result" and isinstance(event.get("data"), dict):
                    result_payload = event["data"]
                elif event_type == "error":
                    log(str(event.get("message") or ""))
            process.wait(timeout=timeout)
        finally:
            if process.poll() is None:
                process.terminate()
            self.unregister_worker(worker_id)

        if result_payload is not None:
            return MaaFWRunResult.model_validate(result_payload)
        return MaaFWRunResult(
            success=False,
            projectName=payload.plan.projectName,
            controllerName=payload.plan.controllerName,
            resourceName=payload.plan.resourceName,
            errorMessage=f"MaaFW runner worker exited without result: {process.returncode}",
        )

    @staticmethod
    def _coerce_interface(interface: MaaFWInterface | dict[str, Any]) -> MaaFWInterface:
        if isinstance(interface, MaaFWInterface):
            return interface
        if hasattr(interface, "model_dump"):
            return MaaFWInterface.model_validate(interface.model_dump(mode="json", by_alias=True))
        return MaaFWInterface.model_validate(interface)
