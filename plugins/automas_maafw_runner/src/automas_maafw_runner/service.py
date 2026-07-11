from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Callable

from automas_maafw_interface.models import MaaFWInterface

from .environment import MaaFWRunnerEnvironment, prepare_runner_environment
from .models import MaaFWDeviceConfig, MaaFWRunnerJobPayload, MaaFWRunPlan, MaaFWRunResult
from .run_plan import build_maafw_run_plan


class MaaFWRunnerService:
    """maafw.runner.v1 service."""

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
        return MaaFWRunnerJobPayload(
            plan=plan if isinstance(plan, MaaFWRunPlan) else MaaFWRunPlan.model_validate(plan),
            deviceConfig=(
                device_config
                if isinstance(device_config, MaaFWDeviceConfig)
                else MaaFWDeviceConfig.model_validate(device_config)
            ),
        )

    def prepare_environment(
        self,
        project_path: str | Path,
        *,
        managed_env_root: str | Path | None = None,
        import_paths: list[str | Path] | None = None,
        send_log: Callable[[str], None] | None = None,
    ) -> MaaFWRunnerEnvironment:
        return prepare_runner_environment(
            project_path,
            managed_env_root=managed_env_root,
            import_paths=import_paths or [],
            send_log=send_log,
        )

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
        command = worker_command or [sys.executable, "-m", "automas_maafw_runner.worker"]
        process = subprocess.Popen(
            [*command, str(job_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
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
