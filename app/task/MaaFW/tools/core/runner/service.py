from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import psutil

from app.task.MaaFW.tools.core.interface.models import MaaFWAgent, MaaFWInterface

from .environment import (
    DEFAULT_RUNTIME_LEASE_TTL_SECONDS,
    MaaFWRunnerEnvironment,
    prepare_runner_environment,
    release_runner_environment,
)
from .models import (
    MaaFWDeviceConfig,
    MaaFWRunnerJobPayload,
    MaaFWRunPlan,
)
from .run_plan import build_maafw_run_plan
from .worker_registry import GLOBAL_MAAFW_WORKER_REGISTRY, MaaFWWorkerRegistry

if TYPE_CHECKING:
    from app.task.MaaFW.tools.core.runtime_pool import (
        MaaFWRuntimePool,
        RuntimeInstaller,
    )

ProjectEnvironmentProgressCallback = Callable[[dict[str, Any]], None]


class MaaFWRunnerService:
    """maafw.runner.v1 service."""

    def __init__(self, *, worker_registry: MaaFWWorkerRegistry | None = None) -> None:
        self._worker_registry = worker_registry or GLOBAL_MAAFW_WORKER_REGISTRY

    def register_worker(self, worker: Any) -> str | None:
        return self._worker_registry.register(worker)

    def unregister_worker(self, worker_id: str | None) -> None:
        self._worker_registry.unregister(worker_id)

    def build_plan(
        self,
        project_path: str | Path,
        interface: MaaFWInterface | dict[str, Any],
        *,
        controller_name: str | None = None,
        resource_name: str | None = None,
        selected_preset: str | None = None,
        task_snapshot: dict[str, Any] | None = None,
        task_ids: list[str] | None = None,
        task_options: dict[str, Any] | None = None,
        global_options: dict[str, Any] | None = None,
        script_hotkeys: dict[str, dict[str, str]] | None = None,
        secret_inputs: Any = None,
        no_default_fallback_inputs: Any = None,
        excluded_task_reasons: dict[str, str] | None = None,
    ) -> MaaFWRunPlan:
        return build_maafw_run_plan(
            project_path,
            self._coerce_interface(interface),
            controller_name=controller_name,
            resource_name=resource_name,
            selected_preset=selected_preset,
            task_snapshot=task_snapshot,
            task_ids=task_ids,
            task_options=task_options,
            global_options=global_options,
            script_hotkeys=script_hotkeys,
            secret_inputs=secret_inputs,
            no_default_fallback_inputs=no_default_fallback_inputs,
            excluded_task_reasons=excluded_task_reasons,
        )

    def create_job_payload(
        self,
        plan: MaaFWRunPlan | dict[str, Any],
        device_config: MaaFWDeviceConfig | dict[str, Any],
        *,
        failure_screenshot_dir: str | Path | None = None,
        failure_screenshot_prefix: str = "",
        task_start_not_before: float | None = None,
        task_start_gate_mode: str = "screen",
        run_deadline_at: float | None = None,
        task_time_limit_seconds: int = 0,
        task_time_limit_overrides: dict[str, int] | None = None,
        loop_guard: bool = False,
    ) -> MaaFWRunnerJobPayload:
        owner_pid = os.getpid()
        try:
            owner_create_time = psutil.Process(owner_pid).create_time()
        except psutil.Error:
            owner_create_time = None
        return MaaFWRunnerJobPayload(
            plan=plan
            if isinstance(plan, MaaFWRunPlan)
            else MaaFWRunPlan.model_validate(plan),
            deviceConfig=(
                device_config
                if isinstance(device_config, MaaFWDeviceConfig)
                else MaaFWDeviceConfig.model_validate(device_config)
            ),
            ownerPid=owner_pid,
            ownerCreateTime=owner_create_time,
            failureScreenshotDir=(
                str(failure_screenshot_dir)
                if failure_screenshot_dir is not None
                else None
            ),
            failureScreenshotPrefix=failure_screenshot_prefix,
            taskStartNotBefore=task_start_not_before,
            taskStartGateMode=task_start_gate_mode,
            runDeadlineAt=run_deadline_at,
            taskTimeLimitSeconds=task_time_limit_seconds,
            taskTimeLimitOverrides=task_time_limit_overrides,
            loopGuard=bool(loop_guard),
        )

    def prepare_environment(
        self,
        project_path: str | Path,
        *,
        managed_env_root: str | Path | None = None,
        runtime_pool_root: str | Path | None = None,
        runtime_pool: MaaFWRuntimePool | None = None,
        runtime_installer: RuntimeInstaller | None = None,
        runtime_pool_id: str | None = None,
        lease_owner: str = "automas-maafw-runner",
        lease_ttl_seconds: float | None = DEFAULT_RUNTIME_LEASE_TTL_SECONDS,
        import_paths: list[str | Path] | None = None,
        send_log: Callable[[str], None] | None = None,
        progress: ProjectEnvironmentProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
        agents: list[MaaFWAgent] | None = None,
        agent_env_root: str | Path | None = None,
    ) -> MaaFWRunnerEnvironment:
        return prepare_runner_environment(
            project_path,
            managed_env_root=managed_env_root,
            runtime_pool_root=runtime_pool_root,
            runtime_pool=runtime_pool,
            runtime_installer=runtime_installer,
            runtime_pool_id=runtime_pool_id,
            lease_owner=lease_owner,
            lease_ttl_seconds=lease_ttl_seconds,
            import_paths=import_paths or [],
            send_log=send_log,
            progress=progress,
            cancel_event=cancel_event,
            agents=agents,
            agent_env_root=agent_env_root,
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

    @staticmethod
    def _coerce_interface(interface: MaaFWInterface | dict[str, Any]) -> MaaFWInterface:
        if isinstance(interface, MaaFWInterface):
            return interface
        if hasattr(interface, "model_dump"):
            return MaaFWInterface.model_validate(
                interface.model_dump(mode="json", by_alias=True)
            )
        return MaaFWInterface.model_validate(interface)
